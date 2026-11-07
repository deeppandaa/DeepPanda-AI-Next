from __future__ import annotations

import io
import logging
import os
import re
import shutil
import tarfile
from functools import partial
from pathlib import Path, PurePosixPath
from typing import Any

import httpx
import yaml

from app.plugins.contracts import PluginManifest
from app.plugins.gateway import PluginGateway
from app.plugins.integration_errors import (
    IntegrationNotFoundError,
    IntegrationUnavailableError,
    require_approval,
)
from app.plugins.worker_lifecycle import run_thread

logger = logging.getLogger(__name__)

_REPO = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}")
_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./-]{0,99}")
_SKILL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,160}")

RECOMMENDED_SOURCES = (
    {"repo": "Jakeschincariol/replica-skill", "ref": "HEAD", "license": "MIT",
     "description": "Replica paketi: recon, architect, design, backend, build, test, diff, deploy, launch becerileri."},
    {"repo": "safishamsi/graphify", "ref": "v3", "license": "MIT",
     "description": "graphify: kod tabanından bilgi grafiği çıkarma becerisi (graph.json + GRAPH_REPORT.md)."},
)


def parse_skill_file(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    metadata: dict[str, Any] = {}
    body = text
    if text.startswith("---"):
        parts = text.split("\n---", 1)
        if len(parts) == 2:
            try:
                loaded = yaml.safe_load(parts[0][3:])
            except yaml.YAMLError:
                loaded = None
            if isinstance(loaded, dict):
                metadata = loaded
            body = parts[1].lstrip("-").lstrip("\n")
    name = metadata.get("name") if isinstance(metadata.get("name"), str) else path.parent.name
    description = metadata.get("description") if isinstance(metadata.get("description"), str) else ""
    return {"name": name.strip(), "description": " ".join(description.split())[:1_000], "body": body}


class SkillsPlugin:
    """Discovers SKILL.md skill packs (replica-skill, graphify, ...) and applies them with the local model."""

    manifest = PluginManifest(
        plugin_id="skills",
        display_name="Beceriler (SKILL.md)",
        description="replica-skill gibi SKILL.md beceri paketlerini listeler, içeriğini gösterir, yerel Qwen ile uygular ve onaylı kurar.",
        actions=("list", "get", "apply", "install", "sources"),
    )

    max_archive_bytes = 50_000_000
    max_files = 5_000
    max_body_chars = 24_000

    def __init__(self, gateway: PluginGateway | None = None, roots: list[Path] | None = None) -> None:
        self.gateway = gateway
        data_dir = Path(os.getenv("AI_DATA_DIR", "/data")).expanduser()
        self.install_root = (data_dir / "skills").resolve()
        if roots is None:
            configured = os.getenv("SKILLS_DIRS", "")
            roots = [Path(item).expanduser() for item in configured.split(os.pathsep) if item.strip()]
            roots = roots or [self.install_root, Path("/workspace/skills")]
        self.roots = [root.resolve() for root in roots]

    async def invoke(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "sources":
            return {"sources": list(RECOMMENDED_SOURCES), "install_root": str(self.install_root)}
        if action == "list":
            return await run_thread(self.list_skills, logger)
        if action == "get":
            skill = await run_thread(partial(self.get_skill, payload.get("skill")), logger)
            return skill
        if action == "apply":
            return await self.apply(payload)
        if action == "install":
            require_approval(payload, "Beceri paketi indirip kurmak için açık onay gerekir.")
            return await self.install(payload)
        raise ValueError(f"Unsupported skills action: {action}")

    def discover(self) -> dict[str, dict[str, Any]]:
        skills: dict[str, dict[str, Any]] = {}
        for root in self.roots:
            if not root.is_dir():
                continue
            for skill_file in sorted(root.rglob("SKILL.md")):
                relative = skill_file.relative_to(root)
                if len(relative.parts) > 5 or any(part.startswith(".") for part in relative.parts[:-1]):
                    continue
                try:
                    parsed = parse_skill_file(skill_file)
                except OSError:
                    continue
                pack = relative.parts[0] if len(relative.parts) > 2 else root.name
                skill_id = f"{pack}:{parsed['name']}"
                if skill_id in skills:
                    continue
                skills[skill_id] = {**parsed, "id": skill_id, "pack": pack, "path": str(skill_file)}
        return skills

    def list_skills(self) -> dict[str, Any]:
        skills = self.discover()
        return {
            "roots": [str(root) for root in self.roots],
            "skills": [
                {key: value for key, value in skill.items() if key != "body"}
                for skill in skills.values()
            ],
        }

    def get_skill(self, skill_id: Any) -> dict[str, Any]:
        if not isinstance(skill_id, str) or not _SKILL_ID.fullmatch(skill_id):
            raise ValueError("skill must be a skill id from the list action (pack:name).")
        skills = self.discover()
        skill = skills.get(skill_id) or next(
            (item for item in skills.values() if item["name"] == skill_id), None
        )
        if skill is None:
            raise IntegrationNotFoundError(f"Beceri bulunamadı: {skill_id}")
        folder = Path(skill["path"]).parent
        files = sorted(
            str(path.relative_to(folder)).replace("\\", "/")
            for path in folder.rglob("*") if path.is_file() and path.name != "SKILL.md"
        )[:200]
        return {**skill, "body": skill["body"][: self.max_body_chars * 2], "files": files}

    async def apply(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.gateway is None:
            raise IntegrationUnavailableError("Beceri uygulamak için yerel model geçidi gerekir.")
        message = payload.get("message")
        if not isinstance(message, str) or not message.strip() or len(message) > 20_000:
            raise ValueError("message must be non-empty text up to 20000 characters.")
        skill = await run_thread(partial(self.get_skill, payload.get("skill")), logger)
        system_prompt = (
            "Aşağıdaki beceri talimatlarını uygula. Talimatlar araç/komut çalıştırmanı isterse bunu yapma; "
            "bunun yerine kullanıcıya atılacak adımları ve komutları açıkça yaz. Türkçe yanıt ver.\n\n"
            f"# Beceri: {skill['name']}\n{skill['body'][: self.max_body_chars]}"
        )
        request: dict[str, Any] = {"message": message, "system_prompt": system_prompt}
        model = payload.get("model")
        if isinstance(model, str) and model.strip():
            request["model"] = model.strip()
        result = await self.gateway.invoke("ollama", "chat", request)
        content = ""
        if isinstance(result, dict):
            message_obj = result.get("message")
            content = message_obj.get("content", "") if isinstance(message_obj, dict) else ""
        return {"skill": skill["id"], "model": result.get("model") if isinstance(result, dict) else None, "answer": content}

    async def install(self, payload: dict[str, Any]) -> dict[str, Any]:
        repo = payload.get("repo", RECOMMENDED_SOURCES[0]["repo"])
        ref = payload.get("ref", "HEAD")
        if not isinstance(repo, str) or not _REPO.fullmatch(repo) or ".." in repo:
            raise ValueError("repo must look like owner/name.")
        if not isinstance(ref, str) or not _REF.fullmatch(ref) or ".." in ref:
            raise ValueError("ref must be a branch, tag or commit.")
        url = f"https://codeload.github.com/{repo}/tar.gz/{ref}"
        async with (
            httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0), follow_redirects=True) as client,
            client.stream("GET", url) as response,
        ):
            if response.status_code == 404:
                raise IntegrationNotFoundError(f"GitHub deposu veya ref bulunamadı: {repo}@{ref}")
            response.raise_for_status()
            buffer = io.BytesIO()
            async for chunk in response.aiter_bytes():
                buffer.write(chunk)
                if buffer.tell() > self.max_archive_bytes:
                    raise ValueError("Arşiv 50 MB sınırını aşıyor.")
        target = self.install_root / repo.split("/", 1)[1]
        count = await run_thread(partial(self._extract, buffer.getvalue(), target), logger)
        skills = [skill for skill in self.discover().values() if skill["path"].startswith(str(target))]
        return {"repo": repo, "ref": ref, "path": str(target), "files": count, "skills": [skill["id"] for skill in skills]}

    def _extract(self, archive: bytes, target: Path) -> int:
        staging = target.with_name(target.name + ".partial")
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)
        count = 0
        total = 0
        try:
            with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as bundle:
                for member in bundle:
                    if not member.isfile():
                        continue
                    parts = PurePosixPath(member.name).parts[1:]
                    if not parts or any(part in {"", ".", ".."} or part.startswith("/") for part in parts):
                        continue
                    if parts[0] in {".git", ".github"}:
                        continue
                    count += 1
                    total += member.size
                    if count > self.max_files or total > self.max_archive_bytes * 2:
                        raise ValueError("Arşiv dosya/boyut sınırını aşıyor.")
                    destination = staging.joinpath(*parts)
                    if not destination.resolve().is_relative_to(staging.resolve()):
                        continue
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    source = bundle.extractfile(member)
                    if source is None:
                        continue
                    with source, destination.open("wb") as handle:
                        shutil.copyfileobj(source, handle)
            if target.exists():
                shutil.rmtree(target)
            staging.rename(target)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return count
