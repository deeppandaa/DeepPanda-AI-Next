from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox, QWidget

from desktop import host_commands
from desktop.api import ApiError
from desktop.config import Settings
from desktop.host_commands import run_host_command
from desktop.tasks import run_background
from desktop.windows_api import DesktopApiClient as ApiClient
from desktop.windows_host import HOST_MUTATIONS, HOST_PRIVATE_READS

CREATE_NO_WINDOW = host_commands.CREATE_NO_WINDOW

def confirm(parent: QWidget | None, text: str, title: str = "Onay", *, details: str | None = None) -> bool:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle(title)
    box.setText(text)
    yes = box.addButton("Evet, devam et", QMessageBox.ButtonRole.AcceptRole)
    no = box.addButton("Vazgeç", QMessageBox.ButtonRole.RejectRole)
    if details is not None:
        box.setDetailedText(details)
    box.setDefaultButton(no if details is not None else yes)
    box.exec()
    return box.clickedButton() is yes


def error_text(error: Exception) -> str:
    if isinstance(error, ApiError):
        return error.detail if error.status == 0 else f"{error.status} · {error.detail}"
    return str(error) or error.__class__.__name__


class AppContext:
    """Shared services for all pages: settings, API client, notifications and the approval flow."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.api = ApiClient(settings.api_url, settings.request_timeout)
        self.notify: Callable[[str, str], None] = lambda _text, _kind="info": None
        self.navigate: Callable[[str], None] = lambda _page: None
        self.insert_into_chat: Callable[[str], None] = lambda _text: None

    def apply_settings(self, settings: Settings) -> None:
        self.settings = settings
        self.api = ApiClient(settings.api_url, settings.request_timeout)

    def call_action(
        self,
        parent: QWidget | None,
        plugin: str,
        action: str,
        payload: dict[str, Any] | None = None,
        *,
        approval: str | None = None,
        on_done: Callable[[Any], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        timeout: float | None = None,
    ) -> bool:
        """Runs a plugin action in the background. Asks at most once for approval:
        up front when the action is known to need it, otherwise only if the API answers 403."""
        body = dict(payload or {})
        if plugin == "windows_host" and action in HOST_MUTATIONS:
            def previewed(preview: dict[str, Any]) -> None:
                if not confirm(
                    parent, f"Windows host › {action}\nHedef: {preview['target']}\n"
                    "Ayrıntılardaki önizleme ve uyarıları inceleyin. Bu işlem uygulansın mı?",
                    details=json.dumps(preview, ensure_ascii=False, indent=2),
                ):
                    failed(ApiError(403, "Onay verilmedi; işlem yapılmadı."))
                    return
                run_background(
                    lambda: self.api.action(plugin, action, {"plan_id": preview["plan_id"], "approved": True}),
                    done, failed,
                )

            def failed(error: Exception) -> None:
                self.notify(error_text(error), "error")
                if on_error is not None:
                    on_error(error)

            def done(result: Any) -> None:
                if on_done is not None:
                    on_done(result)

            run_background(
                lambda: self.api.action(plugin, "preview", {"action": action, "arguments": body}),
                previewed, failed,
            )
            return True
        if plugin == "windows_host" and action in HOST_PRIVATE_READS:
            if not confirm(parent, f"Bu host verisi okunsun mu?\n{body}",
                           details=json.dumps(body, ensure_ascii=False, indent=2)):
                self.notify("Onay verilmedi; işlem yapılmadı.", "warn")
                return False
            body["approved"] = True
            approval = None
        if approval:
            if not confirm(parent, approval):
                self.notify("Onay verilmedi; işlem yapılmadı.", "warn")
                return False
            body["approved"] = True

        def attempt() -> Any:
            return self.api.action(plugin, action, body, timeout=timeout)

        def failed(error: Exception) -> None:
            if isinstance(error, ApiError) and error.needs_approval and body.get("approved") is not True:
                if confirm(parent, f"{error.detail}\n\n{plugin} › {action} çalıştırılsın mı?"):
                    body["approved"] = True
                    run_background(attempt, done, failed)
                    return
                self.notify("Onay verilmedi; işlem yapılmadı.", "warn")
                if on_error is not None:
                    on_error(ApiError(403, "Onay verilmedi."))
                return
            self.notify(error_text(error), "error")
            if on_error is not None:
                on_error(error)

        def done(result: Any) -> None:
            if on_done is not None:
                on_done(result)

        run_background(attempt, done, failed)
        return True

    def open_url(self, url: str) -> None:
        QDesktopServices.openUrl(QUrl(url))

    def run_command(
        self,
        args: list[str],
        on_done: Callable[[dict[str, Any]], None],
        timeout: int = 1800,
        env: dict[str, str] | None = None,
    ) -> None:
        """Runs a host command (docker, gh ...) in the project directory without a console window."""
        project_dir = self.settings.project_dir
        run_background(
            lambda: run_host_command(args, project_dir, timeout, env),
            on_done, lambda error: on_done({"ok": False, "code": -1, "output": error_text(error)}),
        )
