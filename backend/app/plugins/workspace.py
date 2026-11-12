from __future__ import annotations

import difflib
import hashlib
import json
import logging
import os
import shutil
import subprocess
import uuid
from functools import partial
from pathlib import Path, PureWindowsPath
from typing import Any, ClassVar

from app.plugins.contracts import PluginManifest
from app.plugins.worker_lifecycle import run_thread

logger = logging.getLogger(__name__)


class WorkspaceWriteApprovalRequired(Exception):
    pass


class WorkspaceCommandApprovalRequired(Exception):
    pass


def _is_private_environment_file(name: str) -> bool:
    lowered = name.casefold()
    return lowered.endswith(".env") or (lowered.startswith(".env.") and lowered != ".env.example")


class WorkspacePlugin:
    manifest = PluginManifest(
        plugin_id="workspace",
        display_name="Workspace Tools",
        description=(
            "Yalnız proje çalışma alanında göreli yollarla dosya okuma, onaylı yazma ve allowlist komutları. "
            "Windows masaüstü ve diğer mutlak host yollarına erişmez."
        ),
        actions=("list", "read", "preview_write", "write", "rollback", "run"),
    )

    excluded_directories: ClassVar[frozenset[str]] = frozenset(
        {
            ".git", ".hg", ".svn", ".venv", ".tools", "venv", "env", "node_modules", "dist", "build", "out",
            ".next", ".cache", "__pycache__", ".pytest_cache", ".ruff_cache", "models", "ai-runtimes",
            "packages", "vendor", "target", "data", "runtimes", "_tmp", "_arsiv",
        }
    )
    allowed_commands: ClassVar[frozenset[str]] = frozenset({"python", "py", "pytest", "ruff", "git", "node", "npm", "ffmpeg"})
    max_read_bytes = 1_000_000
    max_write_bytes = 1_000_000
    max_list_entries = 2_000
    max_timeout_seconds = 120

    def __init__(self, root: str | Path | None = None, backup_root: str | Path | None = None) -> None:
        self.root = Path(root or os.getenv("WORKSPACE_ROOT", "/workspace")).expanduser().resolve()
        default_backup = Path(os.getenv("AI_DATA_DIR", "/data")).expanduser() / "workspace-backups"
        self.backup_root = Path(backup_root or default_backup).expanduser().resolve()
        if self.backup_root == self.root or self.root in self.backup_root.parents:
            raise ValueError("Backup root must be outside the workspace.")

    async def invoke(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "list":
            return self._list(payload)
        if action == "read":
            return self._read(payload)
        if action == "preview_write":
            return self._preview_write(payload)
        if action == "write":
            return self._write(payload)
        if action == "rollback":
            return self._rollback(payload)
        if action == "run":
            return await run_thread(partial(self._run, payload), logger)
        raise ValueError(f"Unsupported workspace action: {action}")

    def _safe_path(self, relative_path: Any) -> Path:
        if not self.root.is_dir():
            raise ValueError("Workspace root is unavailable.")
        if not isinstance(relative_path, str) or not relative_path.strip():
            raise ValueError("path must be a non-empty relative path.")
        raw_path = Path(relative_path)
        windows_path = PureWindowsPath(relative_path)
        if raw_path.is_absolute() or raw_path.drive or windows_path.drive or windows_path.root:
            raise ValueError("Absolute or drive-qualified paths are not allowed.")
        if os.name != "nt" and "\\" in relative_path:
            raise ValueError("Workspace paths must use forward slashes on this platform.")
        if ".." in raw_path.parts:
            raise ValueError("Parent-directory traversal is not allowed.")
        if any(part.casefold() in self.excluded_directories for part in raw_path.parts):
            raise ValueError("This workspace path is excluded from agent access.")
        if _is_private_environment_file(raw_path.name):
            raise ValueError("Environment secret files are excluded from agent access.")
        target = self.root / raw_path
        current = self.root
        for part in raw_path.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError("Symbolic-link targets are excluded from agent access.")
        target = target.resolve()
        if target != self.root and self.root not in target.parents:
            raise ValueError("Path escapes the configured workspace.")
        return target

    def _list(self, payload: dict[str, Any]) -> dict[str, Any]:
        relative = payload.get("path", ".")
        directory = self._safe_path(relative)
        if not directory.is_dir():
            raise ValueError("path must identify a workspace directory.")
        entries: list[dict[str, Any]] = []
        truncated = False
        for current, child_directories, file_names in os.walk(directory, followlinks=False):
            child_directories[:] = [
                name
                for name in child_directories
                if name.casefold() not in self.excluded_directories and not (Path(current) / name).is_symlink()
            ]
            for name in sorted([*child_directories, *file_names]):
                full_path = Path(current) / name
                if full_path.is_symlink():
                    continue
                if _is_private_environment_file(name):
                    continue
                entries.append(
                    {
                        "path": full_path.relative_to(self.root).as_posix(),
                        "kind": "directory" if full_path.is_dir() else "file",
                    }
                )
                if len(entries) >= self.max_list_entries:
                    truncated = True
                    break
            if truncated:
                break
        return {"entries": entries, "truncated": truncated}

    def _read(self, payload: dict[str, Any]) -> dict[str, Any]:
        target = self._safe_path(payload.get("path"))
        if not target.is_file():
            raise ValueError("path must identify a workspace file.")
        if target.stat().st_size > self.max_read_bytes:
            raise ValueError("File exceeds the workspace read limit.")
        return {
            "path": target.relative_to(self.root).as_posix(),
            "content": target.read_text(encoding="utf-8", errors="replace"),
        }

    def _preview_write(self, payload: dict[str, Any]) -> dict[str, Any]:
        target = self._safe_path(payload.get("path"))
        content = self._content(payload)
        if target.exists() and not target.is_file():
            raise ValueError("Write target must be a file.")
        before_bytes = target.read_bytes() if target.exists() else None
        before = before_bytes.decode("utf-8", errors="replace") if before_bytes is not None else ""
        diff = "".join(
            difflib.unified_diff(
                before.splitlines(keepends=True),
                content.splitlines(keepends=True),
                fromfile=f"a/{target.relative_to(self.root).as_posix()}",
                tofile=f"b/{target.relative_to(self.root).as_posix()}",
            )
        )
        return {
            "path": target.relative_to(self.root).as_posix(),
            "diff": diff,
            "status": "modified" if before_bytes is not None else "new",
            "expected_sha256": hashlib.sha256(before_bytes).hexdigest() if before_bytes is not None else None,
        }

    def _write(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("approved") is not True:
            raise WorkspaceWriteApprovalRequired("Writing workspace files requires approved=true.")
        target = self._safe_path(payload.get("path"))
        content = self._content(payload)
        if target.exists() and not target.is_file():
            raise ValueError("Write target must be a file.")
        if "expected_sha256" in payload:
            expected_sha256 = payload["expected_sha256"]
            if expected_sha256 is not None and (
                not isinstance(expected_sha256, str) or len(expected_sha256) != 64
            ):
                raise ValueError("expected_sha256 must be a SHA-256 digest or null.")
            current_sha256 = hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None
            if current_sha256 != expected_sha256:
                raise ValueError("Workspace file changed after preview; create a new preview before writing.")

        backup_id = uuid.uuid4().hex
        backup_directory = self.backup_root / backup_id
        backup_directory.mkdir(parents=True, exist_ok=False)
        if target.exists():
            relative = target.relative_to(self.root)
            backup_file = backup_directory / "original"
            shutil.copy2(target, backup_file)
            metadata = {
                "path": relative.as_posix(),
                "existed": True,
                "sha256": hashlib.sha256(backup_file.read_bytes()).hexdigest(),
            }
        else:
            metadata = {"path": target.relative_to(self.root).as_posix(), "existed": False}
        (backup_directory / "manifest.json").write_text(json.dumps(metadata), encoding="utf-8")

        target.parent.mkdir(parents=True, exist_ok=True)
        temporary_file = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary_file.write_text(content, encoding="utf-8")
            os.replace(temporary_file, target)
        finally:
            if temporary_file.exists():
                temporary_file.unlink()
        written_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
        metadata["written_sha256"] = written_sha256
        (backup_directory / "manifest.json").write_text(json.dumps(metadata), encoding="utf-8")
        return {
            "path": target.relative_to(self.root).as_posix(),
            "backup_id": backup_id,
            "written": True,
            "written_sha256": written_sha256,
        }

    def _rollback(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("approved") is not True:
            raise WorkspaceWriteApprovalRequired("Rollback requires approved=true.")
        backup_id = payload.get("backup_id")
        try:
            backup_id = uuid.UUID(str(backup_id)).hex
        except (ValueError, AttributeError) as exc:
            raise ValueError("backup_id must be a valid backup identifier.") from exc
        backup_directory = (self.backup_root / backup_id).resolve()
        if self.backup_root not in backup_directory.parents:
            raise ValueError("Invalid backup location.")
        metadata_path = backup_directory / "manifest.json"
        if not metadata_path.is_file():
            raise ValueError("Workspace backup not found.")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        target = self._safe_path(metadata["path"])
        written_sha256 = metadata.get("written_sha256")
        if written_sha256 and target.exists():
            if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != written_sha256:
                raise ValueError("Workspace file changed since this backup; refusing to overwrite newer edits.")
        if metadata["existed"]:
            backup_file = backup_directory / "original"
            if hashlib.sha256(backup_file.read_bytes()).hexdigest() != metadata["sha256"]:
                raise ValueError("Workspace backup integrity check failed.")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_file, target)
            return {"path": metadata["path"], "restored": True}
        if target.exists():
            target.unlink()
        return {"path": metadata["path"], "restored": True, "removed_created_file": True}

    def _run(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("approved") is not True:
            raise WorkspaceCommandApprovalRequired("Running commands requires approved=true.")
        command = payload.get("command")
        if not isinstance(command, list) or not command or not all(isinstance(part, str) for part in command):
            raise ValueError("command must be a non-empty string list.")
        executable_name = command[0].casefold()
        if Path(command[0]).name != command[0] or "/" in command[0] or "\\" in command[0]:
            raise ValueError("Command executable must be an allowlisted PATH name, not a file path.")
        executable = executable_name
        if executable.endswith(".exe"):
            executable = executable[:-4]
        if executable not in self.allowed_commands:
            raise ValueError("Command executable is not allowlisted.")
        resolved_executable = shutil.which(command[0])
        if resolved_executable is None:
            raise ValueError("Allowlisted command executable is not installed.")
        timeout = payload.get("timeout_seconds", 60)
        if isinstance(timeout, bool) or not isinstance(timeout, int):
            raise TypeError("timeout_seconds must be an integer.")
        timeout = max(1, min(timeout, self.max_timeout_seconds))
        result = subprocess.run(
            [resolved_executable, *command[1:]],
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            check=False,
        )
        return {
            "passed": result.returncode == 0,
            "returncode": result.returncode,
            "command": command,
            "stdout": result.stdout[-12_000:],
            "stderr": result.stderr[-12_000:],
        }

    def _content(self, payload: dict[str, Any]) -> str:
        content = payload.get("content")
        if not isinstance(content, str):
            raise ValueError("content must be a string.")
        if len(content.encode("utf-8")) > self.max_write_bytes:
            raise ValueError("Write content exceeds the workspace limit.")
        return content