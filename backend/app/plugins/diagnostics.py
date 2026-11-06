from __future__ import annotations

import ast
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import tomllib
from functools import partial
from pathlib import Path
from typing import Any, ClassVar

import yaml

from app.plugins.contracts import PluginManifest
from app.plugins.worker_lifecycle import run_thread

logger = logging.getLogger(__name__)


class DiagnosticsPlugin:
    manifest = PluginManifest(
        plugin_id="diagnostics",
        display_name="Workspace Diagnostics",
        description="Yerel workspace içinde salt okunur statik hata taraması.",
        actions=("scan",),
    )

    supported_suffixes: ClassVar[frozenset[str]] = frozenset({".py", ".json", ".toml", ".yaml", ".yml"})
    excluded_directories: ClassVar[frozenset[str]] = frozenset({
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "env",
        "node_modules",
        "dist",
        "build",
        "out",
        ".next",
        ".cache",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        "models",
        "ai-runtimes",
        "packages",
        "vendor",
        "target",
    })
    excluded_name_fragments = ("secret", "credential", "token")
    max_files = 5000
    max_file_bytes = 1_000_000
    max_total_bytes = 100_000_000
    max_scan_seconds = 120
    max_diagnostics = 500
    ruff_batch_size = 100

    def __init__(self, root: Path | str | None = None) -> None:
        configured_root = root or os.getenv("DIAGNOSTICS_ROOT", "/workspace")
        self.root = Path(configured_root).expanduser().resolve()

    async def invoke(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action != "scan":
            raise ValueError(f"Unsupported diagnostics action: {action}")
        return await run_thread(partial(self._scan_workspace), logger)

    def _scan_workspace(self) -> dict[str, Any]:
        if not self.root.is_dir():
            raise ValueError("Diagnostics workspace is unavailable.")

        findings: list[dict[str, Any]] = []
        python_files: list[Path] = []
        scanned_files = 0
        skipped_large_files = 0
        total_bytes = 0
        truncated = False
        deadline = time.monotonic() + self.max_scan_seconds

        for directory, child_directories, file_names in os.walk(self.root, followlinks=False):
            if time.monotonic() >= deadline:
                truncated = True
                break
            child_directories[:] = [
                name
                for name in child_directories
                if name.casefold() not in self.excluded_directories
                and not (Path(directory) / name).is_symlink()
            ]
            for file_name in file_names:
                if time.monotonic() >= deadline:
                    truncated = True
                    break
                path = Path(directory) / file_name
                if path.suffix.casefold() not in self.supported_suffixes:
                    continue
                if any(fragment in file_name.casefold() for fragment in self.excluded_name_fragments):
                    continue
                try:
                    if path.is_symlink():
                        continue
                    size = path.stat().st_size
                except OSError:
                    continue
                if size > self.max_file_bytes:
                    skipped_large_files += 1
                    continue
                if scanned_files >= self.max_files or total_bytes + size > self.max_total_bytes:
                    truncated = True
                    break

                try:
                    text = path.read_text(encoding="utf-8-sig")
                except (OSError, UnicodeError):
                    continue

                scanned_files += 1
                total_bytes += size
                relative_path = path.relative_to(self.root).as_posix()
                findings.extend(self._parse_file(path.suffix.casefold(), relative_path, text))
                if path.suffix.casefold() == ".py":
                    python_files.append(path)
                if len(findings) >= self.max_diagnostics:
                    findings = findings[: self.max_diagnostics]
                    truncated = True
                    break
            if truncated:
                break

        if python_files and len(findings) < self.max_diagnostics:
            ruff_findings = self._run_ruff(python_files, deadline)
            findings.extend(ruff_findings)
            if any(item["code"] == "DIAGNOSTICS-TIMEOUT" for item in ruff_findings):
                truncated = True
        findings = sorted(
            findings[: self.max_diagnostics],
            key=lambda item: (
                {"error": 0, "warning": 1, "info": 2}.get(item["severity"], 3),
                item["path"],
                item["line"] or 0,
                item["column"] or 0,
            ),
        )
        return {
            "workspace": ".",
            "read_only": True,
            "scanned_files": scanned_files,
            "skipped_large_files": skipped_large_files,
            "truncated": truncated,
            "summary": {
                "errors": sum(item["severity"] == "error" for item in findings),
                "warnings": sum(item["severity"] == "warning" for item in findings),
                "total": len(findings),
            },
            "diagnostics": findings,
        }

    @staticmethod
    def _parse_file(suffix: str, relative_path: str, text: str) -> list[dict[str, Any]]:
        try:
            if suffix == ".py":
                ast.parse(text, filename=relative_path)
            elif suffix == ".json":
                json.loads(text)
            elif suffix == ".toml":
                tomllib.loads(text)
            elif suffix in {".yaml", ".yml"}:
                list(yaml.safe_load_all(text))
        except SyntaxError as exc:
            return [
                {
                    "path": relative_path,
                    "line": exc.lineno,
                    "column": exc.offset,
                    "severity": "error",
                    "code": "PY-SYNTAX",
                    "message": exc.msg,
                }
            ]
        except json.JSONDecodeError as exc:
            return [
                {
                    "path": relative_path,
                    "line": exc.lineno,
                    "column": exc.colno,
                    "severity": "error",
                    "code": "JSON-SYNTAX",
                    "message": exc.msg,
                }
            ]
        except tomllib.TOMLDecodeError as exc:
            return [
                {
                    "path": relative_path,
                    "line": getattr(exc, "lineno", None),
                    "column": getattr(exc, "colno", None),
                    "severity": "error",
                    "code": "TOML-SYNTAX",
                    "message": str(exc).split(" (at line ", maxsplit=1)[0],
                }
            ]
        except yaml.YAMLError as exc:
            mark = getattr(exc, "problem_mark", None)
            problem = getattr(exc, "problem", None) or "Invalid YAML document."
            return [
                {
                    "path": relative_path,
                    "line": mark.line + 1 if mark else None,
                    "column": mark.column + 1 if mark else None,
                    "severity": "error",
                    "code": "YAML-SYNTAX",
                    "message": problem,
                }
            ]
        return []

    def _run_ruff(self, files: list[Path], deadline: float) -> list[dict[str, Any]]:
        if shutil.which("ruff") is None:
            try:
                import importlib.util

                if importlib.util.find_spec("ruff") is None:
                    return [
                        {
                            "path": "",
                            "line": None,
                            "column": None,
                            "severity": "warning",
                            "code": "RUFF-UNAVAILABLE",
                            "message": "Ruff is unavailable; Python syntax was checked, but lint diagnostics were skipped.",
                        }
                    ]
            except (ImportError, ValueError):
                return [
                    {
                        "path": "",
                        "line": None,
                        "column": None,
                        "severity": "warning",
                        "code": "RUFF-UNAVAILABLE",
                        "message": "Ruff availability could not be determined; Python syntax was checked, but lint diagnostics were skipped.",
                    }
                ]

        findings: list[dict[str, Any]] = []
        for start in range(0, len(files), self.ruff_batch_size):
            remaining_seconds = deadline - time.monotonic()
            if remaining_seconds <= 0:
                findings.append(
                    {
                        "path": "",
                        "line": None,
                        "column": None,
                        "severity": "warning",
                        "code": "DIAGNOSTICS-TIMEOUT",
                        "message": "Analysis reached its time limit; completed findings are still available.",
                    }
                )
                break
            batch = files[start : start + self.ruff_batch_size]
            command = [
                sys.executable,
                "-m",
                "ruff",
                "check",
                "--isolated",
                "--no-cache",
                "--select",
                "E4,E7,E9,F",
                "--output-format",
                "json",
                *(str(path.relative_to(self.root)) for path in batch),
            ]
            try:
                result = subprocess.run(
                    command,
                    cwd=self.root,
                    capture_output=True,
                    text=True,
                    timeout=min(20, remaining_seconds),
                    check=False,
                    shell=False,
                )
            except subprocess.TimeoutExpired:
                findings.append(
                    {
                        "path": "",
                        "line": None,
                        "column": None,
                        "severity": "warning",
                        "code": "DIAGNOSTICS-TIMEOUT",
                        "message": "Analysis reached its time limit; completed findings are still available.",
                    }
                )
                break
            except OSError:
                findings.append(
                    {
                        "path": "",
                        "line": None,
                        "column": None,
                        "severity": "warning",
                        "code": "RUFF-FAILED",
                        "message": "Ruff did not finish; parser diagnostics are still available.",
                    }
                )
                break
            if result.returncode not in {0, 1}:
                findings.append(
                    {
                        "path": "",
                        "line": None,
                        "column": None,
                        "severity": "warning",
                        "code": "RUFF-FAILED",
                        "message": "Ruff could not analyze this workspace batch.",
                    }
                )
                continue
            try:
                ruff_results = json.loads(result.stdout or "[]")
            except json.JSONDecodeError:
                findings.append(
                    {
                        "path": "",
                        "line": None,
                        "column": None,
                        "severity": "warning",
                        "code": "RUFF-INVALID-OUTPUT",
                        "message": "Ruff returned invalid diagnostic output; lint findings may be incomplete.",
                    }
                )
                continue
            if not isinstance(ruff_results, list) or any(
                not isinstance(item, dict)
                or not isinstance(item.get("filename", ""), str)
                or (item.get("location") is not None and not isinstance(item["location"], dict))
                for item in ruff_results
            ):
                findings.append(
                    {
                        "path": "",
                        "line": None,
                        "column": None,
                        "severity": "warning",
                        "code": "RUFF-INVALID-OUTPUT",
                        "message": "Ruff returned an unexpected diagnostic structure; lint findings may be incomplete.",
                    }
                )
                continue
            for item in ruff_results:
                filename = Path(item.get("filename", ""))
                try:
                    filename_path = filename if filename.is_absolute() else self.root / filename
                    relative_path = filename_path.resolve().relative_to(self.root).as_posix()
                except (OSError, ValueError):
                    relative_path = filename.as_posix()
                location = item.get("location") or {}
                findings.append(
                    {
                        "path": relative_path,
                        "line": location.get("row"),
                        "column": location.get("column"),
                        "severity": "warning",
                        "code": item.get("code") or "RUFF",
                        "message": item.get("message", "Lint finding."),
                    }
                )
                if len(findings) >= self.max_diagnostics:
                    return findings[: self.max_diagnostics]
        return findings