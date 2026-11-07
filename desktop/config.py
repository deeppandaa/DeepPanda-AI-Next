from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSettings

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
SETTINGS_FILE = PROJECT_ROOT / "desktop" / "settings.ini"


@dataclass
class Settings:
    api_url: str = "http://127.0.0.1:8787"
    web_url: str = "http://127.0.0.1:8788"
    db_manager_url: str = "http://127.0.0.1:8789"
    project_dir: str = str(PROJECT_ROOT)
    extra_mcp_configs: str = ""
    include_vscode_mcp: bool = True
    request_timeout: int = 600

    @classmethod
    def load(cls) -> Settings:
        store = QSettings(str(SETTINGS_FILE), QSettings.Format.IniFormat)
        defaults = cls()
        values = {}
        for name, default in defaults.__dict__.items():
            raw = store.value(name, default)
            if isinstance(default, bool):
                values[name] = raw if isinstance(raw, bool) else str(raw).lower() in {"1", "true", "yes", "on"}
            elif isinstance(default, int):
                try:
                    values[name] = int(raw)
                except (TypeError, ValueError):
                    values[name] = default
            else:
                values[name] = str(raw) if raw is not None else default
        return cls(**values)

    def save(self) -> None:
        store = QSettings(str(SETTINGS_FILE), QSettings.Format.IniFormat)
        for name, value in self.__dict__.items():
            store.setValue(name, value)
        store.sync()

    def mcp_config_paths(self) -> list[Path]:
        paths: list[Path] = []
        if self.include_vscode_mcp:
            appdata = os.getenv("APPDATA")
            if appdata:
                paths.append(Path(appdata) / "Code" / "User" / "mcp.json")
        paths.append(Path(self.project_dir) / "mcp-servers.json")
        for item in self.extra_mcp_configs.split(os.pathsep):
            if item.strip():
                paths.append(Path(item.strip()).expanduser())
        return paths


def ensure_backend_importable() -> None:
    """Lets the desktop client reuse pure helpers from backend/app (e.g. the MCP bridge) on the host."""
    backend = str(BACKEND_DIR)
    if backend not in sys.path:
        sys.path.insert(0, backend)
