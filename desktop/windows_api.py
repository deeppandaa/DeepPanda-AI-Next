from __future__ import annotations

import os
import subprocess
from threading import Event
from typing import Any

from desktop.api import ApiClient, ApiError
from desktop.config import ensure_backend_importable
from desktop.windows_host import HostError, WindowsHost

ensure_backend_importable()
from app.plugins.windows_host import WindowsHostPlugin


class DesktopApiClient(ApiClient):
    def __init__(self, base_url: str, timeout: float = 600.0) -> None:
        super().__init__(base_url, timeout)
        self.windows_host = WindowsHost()

    def plugins(self) -> list[dict[str, Any]]:
        plugins = [item for item in super().plugins() if item["id"] != "windows_host"]
        manifest = WindowsHostPlugin.manifest
        plugins.append({
            "id": manifest.plugin_id, "name": manifest.display_name,
            "description": ("Bu Qt istemcisinde doğrudan host erişimi etkindir. " if os.name == "nt" else "Bu platformda Windows host erişimi yoktur. ") + manifest.description,
            "actions": list(manifest.actions),
        })
        return plugins

    def action(self, plugin: str, action: str, payload: dict[str, Any] | None = None, timeout: float | None = None) -> Any:
        if plugin != "windows_host":
            return super().action(plugin, action, payload, timeout)
        return self.host_action(action, payload)

    def host_action(
        self, action: str, payload: dict[str, Any] | None = None, *, cancelled: Event | None = None,
    ) -> Any:
        try:
            if cancelled is not None:
                return self.windows_host.invoke(action, payload or {}, cancelled=cancelled)
            return self.windows_host.invoke(action, payload or {})
        except HostError as exc:
            raise ApiError(exc.status, str(exc)) from exc
        except FileNotFoundError as exc:
            raise ApiError(404, str(exc)) from exc
        except PermissionError as exc:
            raise ApiError(403, f"Windows erişimi reddetti; yetki otomatik yükseltilmez: {exc}") from exc
        except (ValueError, KeyError) as exc:
            raise ApiError(422, str(exc)) from exc
        except subprocess.TimeoutExpired as exc:
            raise ApiError(504, "Windows işlemi zaman aşımına uğradı; etkisi oluşmuş olabilir. Yeniden çalıştırmadan önce durumu inceleyin.") from exc
        except OSError as exc:
            raise ApiError(503, f"Windows host işlemi tamamlanamadı: {exc}") from exc
