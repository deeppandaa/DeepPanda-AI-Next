from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox, QWidget

from desktop.api import ApiClient, ApiError
from desktop.config import Settings
from desktop.tasks import run_background

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def confirm(parent: QWidget | None, text: str, title: str = "Onay") -> bool:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle(title)
    box.setText(text)
    yes = box.addButton("Evet, devam et", QMessageBox.ButtonRole.AcceptRole)
    box.addButton("Vazgeç", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(yes)
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

        def work() -> dict[str, Any]:
            executable = shutil.which(args[0])
            if executable is None:
                return {"ok": False, "code": -1, "output": f"Komut bulunamadı: {args[0]}"}
            try:
                completed = subprocess.run(
                    [executable, *args[1:]],
                    check=False,
                    cwd=project_dir,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout,
                    env={**os.environ, **(env or {})},
                    creationflags=CREATE_NO_WINDOW,
                )
            except subprocess.TimeoutExpired:
                return {"ok": False, "code": -1, "output": f"Zaman aşımı ({timeout} sn): {' '.join(args)}"}
            except OSError as exc:
                return {"ok": False, "code": -1, "output": str(exc)}
            output = (completed.stdout or "") + (completed.stderr or "")
            return {"ok": completed.returncode == 0, "code": completed.returncode, "output": output.strip()}

        run_background(work, on_done, lambda error: on_done({"ok": False, "code": -1, "output": error_text(error)}))
