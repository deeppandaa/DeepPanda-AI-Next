from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from desktop.api import ApiClient
from desktop.config import SETTINGS_FILE, Settings
from desktop.context import AppContext, error_text
from desktop.tasks import run_background
from desktop.widgets import StatusLabel


class SettingsPage(QWidget):
    def __init__(self, ctx: AppContext, on_saved: Callable[[], None]) -> None:
        super().__init__()
        self.ctx = ctx
        self.on_saved = on_saved
        layout = QVBoxLayout(self)
        title = QLabel("Ayarlar")
        title.setObjectName("formTitle")
        layout.addWidget(title)
        form = QFormLayout()
        self.api_url = QLineEdit()
        self.web_url = QLineEdit()
        self.db_manager_url = QLineEdit()
        self.project_dir = QLineEdit()
        self.extra_mcp = QLineEdit()
        self.extra_mcp.setPlaceholderText("Ek mcp.json yolları (; ile ayır)")
        self.include_vscode = QCheckBox("VS Code / GitHub Copilot mcp.json sunucularını da kullan")
        self.timeout = QSpinBox()
        self.timeout.setRange(30, 7200)
        self.timeout.setSuffix(" sn")
        form.addRow("API adresi", self.api_url)
        form.addRow("Web arayüzü adresi", self.web_url)
        form.addRow("DB yöneticisi adresi", self.db_manager_url)
        form.addRow("Proje klasörü (docker compose)", self.project_dir)
        form.addRow("Ek MCP yapılandırmaları", self.extra_mcp)
        form.addRow("", self.include_vscode)
        form.addRow("İstek zaman aşımı", self.timeout)
        layout.addLayout(form)
        row = QHBoxLayout()
        save = QPushButton("Kaydet")
        save.setObjectName("primary")
        save.clicked.connect(self.save)
        test = QPushButton("API bağlantısını test et")
        test.clicked.connect(self.test)
        row.addWidget(save)
        row.addWidget(test)
        row.addStretch(1)
        layout.addLayout(row)
        self.status = StatusLabel(f"Ayar dosyası: {SETTINGS_FILE}")
        layout.addWidget(self.status)
        layout.addStretch(1)
        self.load(ctx.settings)

    def load(self, settings: Settings) -> None:
        self.api_url.setText(settings.api_url)
        self.web_url.setText(settings.web_url)
        self.db_manager_url.setText(settings.db_manager_url)
        self.project_dir.setText(settings.project_dir)
        self.extra_mcp.setText(settings.extra_mcp_configs)
        self.include_vscode.setChecked(settings.include_vscode_mcp)
        self.timeout.setValue(settings.request_timeout)

    def current(self) -> Settings:
        return Settings(
            api_url=self.api_url.text().strip().rstrip("/") or Settings.api_url,
            web_url=self.web_url.text().strip().rstrip("/") or Settings.web_url,
            db_manager_url=self.db_manager_url.text().strip().rstrip("/") or Settings.db_manager_url,
            project_dir=self.project_dir.text().strip() or Settings.project_dir,
            extra_mcp_configs=self.extra_mcp.text().strip(),
            include_vscode_mcp=self.include_vscode.isChecked(),
            request_timeout=self.timeout.value(),
        )

    def save(self) -> None:
        settings = self.current()
        settings.save()
        self.ctx.apply_settings(settings)
        self.on_saved()
        self.status.set("Ayarlar kaydedildi.", "ok")

    def test(self) -> None:
        settings = self.current()
        client = ApiClient(settings.api_url, 10)
        run_background(client.health, lambda result: self.status.set(f"API yanıt verdi: {result}", "ok"),
                       lambda error: self.status.set(error_text(error), "error"))
