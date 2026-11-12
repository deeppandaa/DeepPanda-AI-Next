from __future__ import annotations

import sys
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from desktop.api import ApiError
from desktop.config import Settings
from desktop.context import AppContext
from desktop.page_catalog import CatalogPage
from desktop.page_chat import ChatPage
from desktop.page_database import DatabasePage
from desktop.page_jobs import JobsPage
from desktop.page_mcp import McpPage
from desktop.page_settings import SettingsPage
from desktop.page_system import SystemPage
from desktop.page_tools import ToolsPage
from desktop.tasks import run_background

STYLE = """
* { font-family: 'Segoe UI'; font-size: 10pt; color: #e6e9ef; }
QMainWindow, QWidget { background: #16181d; }
QLabel, QCheckBox { background: transparent; }
QListWidget#nav { background: #101216; border: none; padding: 8px 4px; outline: 0; show-decoration-selected: 1;
  selection-background-color: #2b5ce6; }
QListWidget#nav::item { padding: 10px 12px; border-radius: 6px; margin: 2px 4px; }
QListWidget#nav::item:selected { background: #2b5ce6; color: white; }
QListWidget#nav::item:hover:!selected { background: #1f232b; }
QLabel#brand { font-size: 13pt; font-weight: 600; padding: 14px 12px 6px 12px; background: #101216; }
QLabel#formTitle, QLabel#sectionTitle { font-size: 12pt; font-weight: 600; }
QLabel#hint { color: #8b93a4; }
QLabel#status[kind="ok"], QLabel#cardState[kind="ok"] { color: #4ade80; }
QLabel#status[kind="error"], QLabel#cardState[kind="error"] { color: #f87171; }
QLabel#status[kind="warn"], QLabel#cardState[kind="warn"] { color: #fbbf24; }
QLabel#status[kind="busy"] { color: #93c5fd; }
QLabel#cardTitle { color: #8b93a4; font-size: 9pt; }
QLabel#cardState { font-size: 12pt; font-weight: 600; }
QFrame#card { background: #1d2027; border: 1px solid #2a2f3a; border-radius: 8px; }
QLineEdit, QPlainTextEdit, QTextBrowser, QComboBox, QSpinBox, QDoubleSpinBox, QListWidget, QTreeWidget, QTableWidget {
  background: #1d2027; border: 1px solid #2a2f3a; border-radius: 6px; padding: 4px; selection-background-color: #2b5ce6; }
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border-color: #2b5ce6; }
QTextBrowser#transcript { padding: 10px 14px; font-size: 10.5pt; }
QListWidget { outline: 0; }
QListWidget::item { padding: 5px 4px; border-radius: 4px; }
QListWidget::item:selected { background: #2b5ce6; color: white; }
QPushButton { background: #262b35; border: 1px solid #323846; border-radius: 6px; padding: 6px 12px; }
QPushButton:hover { background: #2f3542; }
QPushButton:disabled { color: #6b7280; }
QPushButton#primary { background: #2b5ce6; border-color: #2b5ce6; color: white; font-weight: 600; }
QPushButton#primary:hover { background: #3a6bf0; }
QPushButton#link { background: transparent; border: 1px solid #2b5ce6; color: #93c5fd; padding: 3px 8px; }
QHeaderView::section { background: #1d2027; border: none; border-bottom: 1px solid #2a2f3a; padding: 4px; }
QTableWidget { alternate-background-color: #1a1d23; gridline-color: #2a2f3a; }
QStatusBar { background: #101216; }
QSplitter::handle { background: #16181d; width: 4px; }
QScrollArea { border: none; }
QToolTip { background: #262b35; color: #e6e9ef; border: 1px solid #323846; }
"""

PAGES = [
    ("chat", "💬  Sohbet"),
    ("tools", "🧰  Araçlar"),
    ("catalog", "📚  Gelişmiş araçlar"),
    ("jobs", "⏱  İşler"),
    ("database", "🗄  Veritabanı"),
    ("mcp", "🔌  MCP / Copilot"),
    ("system", "🖥  Sistem"),
    ("settings", "⚙  Ayarlar"),
]


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle("DeepPanda Kontrol Merkezi")
        self.resize(1360, 860)

        self.pages: dict[str, QWidget] = {
            "chat": ChatPage(ctx),
            "tools": ToolsPage(ctx),
            "catalog": CatalogPage(ctx, self._open_plugin),
            "jobs": JobsPage(ctx),
            "database": DatabasePage(ctx),
            "mcp": McpPage(ctx),
            "system": SystemPage(ctx),
        }
        self.pages["settings"] = SettingsPage(ctx, self._settings_saved)

        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setFixedWidth(200)
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.nav.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.stack = QStackedWidget()
        for key, label in PAGES:
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.nav.addItem(item)
            self.stack.addWidget(self.pages[key])
        self.nav.currentRowChanged.connect(self._page_changed)

        side = QWidget()
        side.setFixedWidth(200)
        column = QVBoxLayout(side)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        brand = QLabel("🐼 DeepPanda")
        brand.setObjectName("brand")
        column.addWidget(brand)
        column.addWidget(self.nav, 1)

        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(side)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        self.health_label = QLabel("API: …")
        self.statusBar().addPermanentWidget(self.health_label)
        ctx.notify = self.notify
        ctx.navigate = self.navigate
        ctx.insert_into_chat = self._insert_into_chat

        self.health_timer = QTimer(self)
        self.health_timer.setInterval(30_000)
        self.health_timer.timeout.connect(self.check_health)
        self.health_timer.start()
        self.nav.setCurrentRow(0)
        QTimer.singleShot(200, self.check_health)

    def closeEvent(self, event: QCloseEvent) -> None:
        chat = self.pages["chat"]
        if isinstance(chat, ChatPage) and chat.busy:
            self.health_timer.stop()
            chat.stop()
            event.ignore()
            QTimer.singleShot(200, self.close)
            return
        self.health_timer.stop()
        if isinstance(chat, ChatPage) and chat.mcp_runtime is not None:
            event.ignore()
            chat.release_mcp(self.close)
            return
        super().closeEvent(event)

    def _page_changed(self, row: int) -> None:
        if row < 0:
            return
        previous = self.stack.currentWidget()
        if hasattr(previous, "deactivate"):
            previous.deactivate()
        page = self.pages[PAGES[row][0]]
        self.stack.setCurrentWidget(page)
        if hasattr(page, "activate"):
            page.activate()

    def navigate(self, key: str) -> None:
        for row, (page_key, _label) in enumerate(PAGES):
            if page_key == key:
                self.nav.setCurrentRow(row)
                return

    def _insert_into_chat(self, text: str) -> None:
        self.navigate("chat")
        self.pages["chat"].insert_text(text)

    def _open_plugin(self, plugin: str) -> None:
        self.navigate("tools")
        page = self.pages["tools"]
        if isinstance(page, ToolsPage) and not page.select_plugin(plugin):
            self.notify(f"{plugin} için hazır form yok; Gelişmiş bölümünden eylem seç.", "warn")

    def notify(self, text: str, kind: str = "info") -> None:
        colors = {"error": "#f87171", "warn": "#fbbf24", "ok": "#4ade80"}
        self.statusBar().setStyleSheet(f"QStatusBar {{ color: {colors.get(kind, '#e6e9ef')}; }}")
        self.statusBar().showMessage(text, 10_000)

    def check_health(self) -> None:
        def done(_result: Any) -> None:
            self.health_label.setText("API: ● bağlı")
            self.health_label.setStyleSheet("color: #4ade80; padding-right: 8px;")

        def failed(error: Exception) -> None:
            detail = error.detail if isinstance(error, ApiError) else str(error)
            self.health_label.setText("API: ○ bağlı değil")
            self.health_label.setToolTip(detail)
            self.health_label.setStyleSheet("color: #f87171; padding-right: 8px;")

        run_background(self.ctx.api.health, done, failed)

    def _settings_saved(self) -> None:
        self.check_health()
        self.notify("Ayarlar kaydedildi.", "ok")


def main(argv: list[str] | None = None) -> int:
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("DeepPanda Kontrol Merkezi")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = MainWindow(AppContext(Settings.load()))
    window.show()
    return app.exec()
