from __future__ import annotations

import ctypes
import importlib.util
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import uuid
from functools import partial
from pathlib import Path
from typing import Any, ClassVar

import httpx

from app.plugins.contracts import PluginManifest
from app.plugins.gateway import (
    PluginActionNotFoundError,
    PluginGateway,
    PluginNotFoundError,
)
from app.plugins.local_models import (
    image_model_path,
    models_dir,
    piper_model_path,
    runtimes_dir,
    video_model_path,
)
from app.plugins.worker_lifecycle import run_thread

logger = logging.getLogger(__name__)


class SystemPlugin:
    manifest = PluginManifest(
        plugin_id="system",
        display_name="System Readiness",
        description="Donanım, yerel model kataloğu, isteğe bağlı bağımlılıklar ve kurulum hazırlığını salt okunur raporlar.",
        actions=("hardware", "model_assets", "readiness"),
    )

    optional_modules: ClassVar[dict[str, str]] = {
        "reportlab": "PDF rapor",
        "pypdf": "PDF ekleme",
        "pytesseract": "OCR",
        "faster_whisper": "Konuşma tanıma",
        "piper": "Metinden sese",
        "torch": "Görsel/video üretimi",
        "diffusers": "Görsel/video üretimi",
        "cryptography": "Lisans doğrulama",
        "PIL": "Görsel düzenleme",
    }
    min_gguf_bytes: ClassVar[int] = 100 * 1024 * 1024
    max_catalog_entries: ClassVar[int] = 200

    def __init__(self, gateway: PluginGateway) -> None:
        self.gateway = gateway

    async def invoke(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "hardware":
            return await run_thread(partial(self.hardware), logger)
        if action == "model_assets":
            return await run_thread(partial(self.model_assets), logger)
        if action == "readiness":
            return await self.readiness()
        raise ValueError(f"Unsupported system action: {action}")

    def hardware(self) -> dict[str, Any]:
        total, available = self._memory()
        return {
            "platform": sys.platform,
            "cpu_count": os.cpu_count() or 0,
            "ram_total_mb": total // (1024 * 1024),
            "ram_available_mb": available // (1024 * 1024),
            "gpu": self._gpu(),
            "recommended_context": 16_384 if available >= 32 * 1024**3 else 8_192 if available >= 8 * 1024**3 else 4_096,
        }

    @staticmethod
    def _memory() -> tuple[int, int]:
        if sys.platform == "win32":
            class MemoryStatus(ctypes.Structure):
                _fields_: ClassVar[list[tuple[str, Any]]] = [
                    ("length", ctypes.c_ulong), ("memory_load", ctypes.c_ulong),
                    ("total", ctypes.c_ulonglong), ("available", ctypes.c_ulonglong),
                    ("total_page", ctypes.c_ulonglong), ("available_page", ctypes.c_ulonglong),
                    ("total_virtual", ctypes.c_ulonglong), ("available_virtual", ctypes.c_ulonglong),
                    ("available_extended", ctypes.c_ulonglong),
                ]

            memory = MemoryStatus()
            memory.length = ctypes.sizeof(MemoryStatus)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):  # type: ignore[attr-defined]
                return int(memory.total), int(memory.available)
            return 0, 0
        values: dict[str, int] = {}
        try:
            for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
                key, _, rest = line.partition(":")
                parts = rest.split()
                if parts and parts[0].isdigit():
                    values[key] = int(parts[0]) * 1024
        except OSError:
            return 0, 0
        return values.get("MemTotal", 0), values.get("MemAvailable", values.get("MemFree", 0))

    @staticmethod
    def _gpu() -> dict[str, Any]:
        nvidia = shutil.which("nvidia-smi")
        if not nvidia:
            return {"available": False, "name": "", "memory_mb": 0, "error": None}
        try:
            output = subprocess.run(
                [nvidia, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5, check=True, shell=False,
            ).stdout.splitlines()[0]
            name, memory_mb = (part.strip() for part in output.split(",", 1))
            return {"available": True, "name": name, "memory_mb": int(memory_mb), "error": None}
        except (OSError, subprocess.SubprocessError, ValueError, IndexError) as exc:
            logger.exception("Could not query NVIDIA GPU status.")
            return {
                "available": False,
                "name": "",
                "memory_mb": 0,
                "error": f"{type(exc).__name__}: {exc}"[:500],
            }

    def model_assets(self) -> dict[str, Any]:
        models_root = models_dir()
        runtimes_root = runtimes_dir()
        entries: list[dict[str, Any]] = []
        for root in (models_root, runtimes_root / "models"):
            if not root.is_dir():
                continue
            for path in sorted(root.rglob("*.gguf")):
                if len(entries) >= self.max_catalog_entries:
                    break
                try:
                    size = path.stat().st_size
                except OSError:
                    continue
                if size < self.min_gguf_bytes:
                    continue
                name = path.stem.lower().replace("_", "-")
                container_path = self._container_path(path)
                safe_name = re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,59}", name)
                safe_path = re.fullmatch(r"/(?:models|runtimes)/(?:[A-Za-z0-9._-]+/)*[A-Za-z0-9._-]+", container_path)
                if safe_name and safe_path:
                    modelfile = f"/tmp/deeppanda-{uuid.uuid4().hex}.Modelfile"
                    import_command = (
                        f"docker compose exec -T ollama sh -c \"set -C; printf 'FROM {container_path}\\n' "
                        f"> {modelfile} && ollama create {name} -f {modelfile} && rm {modelfile}\""
                    )
                    import_error = None
                else:
                    import_command = None
                    import_error = (
                        "Import command unavailable: the model name or path contains unsupported "
                        "characters, starts with a non-alphanumeric character, or exceeds 60 characters."
                    )
                entries.append({
                    "kind": "gguf", "name": path.name, "path": str(path), "size_mb": size // (1024 * 1024),
                    "ollama_import": import_command, "ollama_import_error": import_error,
                })
        for root in (models_root, runtimes_root / "models"):
            if not root.is_dir():
                continue
            for adapter in sorted(root.rglob("adapter_config.json")):
                if len(entries) >= self.max_catalog_entries:
                    break
                entries.append({"kind": "lora", "name": adapter.parent.name, "path": str(adapter.parent), "base_model": self._adapter_base(adapter)})
        if models_root.is_dir():
            for config in sorted(models_root.glob("*/config.json")) + sorted(models_root.glob("*/model_index.json")):
                if len(entries) >= self.max_catalog_entries:
                    break
                entries.append({"kind": "huggingface", "name": config.parent.name, "path": str(config.parent)})
        ollama_store = runtimes_root / "OllamaModels" / "manifests"
        ollama_manifests = []
        if ollama_store.is_dir():
            for manifest in sorted(ollama_store.rglob("*")):
                if manifest.is_file() and len(ollama_manifests) < self.max_catalog_entries:
                    relative = manifest.relative_to(ollama_store).parts
                    if len(relative) >= 2:
                        model = relative[-2]
                        namespace = relative[-3] if len(relative) >= 3 else ""
                        prefix = "" if namespace in {"", "library"} else f"{namespace}/"
                        ollama_manifests.append(f"{prefix}{model}:{relative[-1]}")
        return {
            "models_dir": {"path": str(models_root), "present": models_root.is_dir()},
            "runtimes_dir": {"path": str(runtimes_root), "present": runtimes_root.is_dir()},
            "specialized": {
                "piper_voice": {"path": str(piper_model_path()), "present": piper_model_path().is_file()},
                "image_model": {"path": str(image_model_path()), "present": image_model_path().is_dir()},
                "video_model": {"path": str(video_model_path()), "present": video_model_path().is_dir()},
            },
            "assets": entries,
            "ollama_store_models": ollama_manifests,
        }

    @staticmethod
    def _container_path(path: Path) -> str:
        try:
            return "/models/" + path.relative_to(models_dir()).as_posix()
        except ValueError:
            try:
                return "/runtimes/" + path.relative_to(runtimes_dir()).as_posix()
            except ValueError:
                return path.as_posix()

    @staticmethod
    def _adapter_base(path: Path) -> str:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return ""
        return str(data.get("base_model_name_or_path", ""))[:300] if isinstance(data, dict) else ""

    async def readiness(self) -> dict[str, Any]:
        modules, binaries, features = await run_thread(partial(self._readiness_capabilities), logger)
        required = [
            os.getenv("OLLAMA_MODEL", "qwen3.6:latest"),
            "nomic-embed-text:latest",
        ]
        installed: list[str] = []
        ollama_error = ""
        try:
            catalog = await self.gateway.invoke("ollama", "models", {})
            installed = [str(item.get("name", "")) for item in catalog.get("models", []) if isinstance(item, dict)]
        except (PluginNotFoundError, PluginActionNotFoundError, httpx.HTTPError) as exc:
            ollama_error = str(exc)[:300] or exc.__class__.__name__
        installed_set = set(installed)
        missing = [
            model for model in required
            if model not in installed_set and f"{model}:latest" not in installed_set and model.removesuffix(":latest") not in installed_set
        ]
        actions = [{"type": "ollama_pull", "model": model, "approval_required": True} for model in missing]
        return {
            "ready": not ollama_error and not missing,
            "ollama": {"available": not ollama_error, "error": ollama_error, "installed": installed, "required": required, "missing": missing},
            "modules": modules,
            "binaries": binaries,
            "features": features,
            "actions": actions,
        }

    @classmethod
    def _readiness_capabilities(cls) -> tuple[dict[str, bool], dict[str, bool], dict[str, bool]]:
        modules = {name: importlib.util.find_spec(name) is not None for name in cls.optional_modules}
        binaries = {name: shutil.which(name) is not None for name in ("ffmpeg", "tesseract", "nvidia-smi")}
        if os.getenv("TESSERACT_CMD"):
            binaries["tesseract"] = Path(os.environ["TESSERACT_CMD"]).is_file()
        features = {
            "pdf_reports": modules["reportlab"],
            "ocr": modules["pytesseract"] and binaries["tesseract"],
            "speech_to_text": modules["faster_whisper"] and binaries["ffmpeg"],
            "text_to_speech": modules["piper"] and piper_model_path().is_file(),
            "image_generation": modules["torch"] and modules["diffusers"] and image_model_path().is_dir(),
            "video_editing": binaries["ffmpeg"],
            "licensing": modules["cryptography"],
        }
        return modules, binaries, features
