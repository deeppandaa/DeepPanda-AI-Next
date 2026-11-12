from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from desktop.context import AppContext, error_text
from desktop.tasks import run_background
from desktop.tool_catalog import RESEARCHED_ON, TOOLS, ToolEntry
from desktop.widgets import StatusLabel


class CatalogPage(QWidget):
    def __init__(self, ctx: AppContext, open_plugin: Callable[[str], None]) -> None:
        super().__init__()
        self.ctx = ctx
        self.open_plugin = open_plugin
        self.plugin_ids: set[str] | None = None
        self.checked = False
        self.loading = False
        self.visible_entries: list[ToolEntry] = []
        layout = QVBoxLayout(self)
        hint = QLabel(
            f"Resmî kaynak araştırması: {RESEARCHED_ON}. Liste çevrimdışı açılır; otomatik kurulum veya izin verme yapmaz.\n"
            "API kaydı, servisin/modelin hazır olduğu anlamına gelmez. MCP bağlantıları MCP / Copilot ekranında doğrulanır."
        )
        hint.setWordWrap(True)
        hint.setObjectName("hint")
        layout.addWidget(hint)
        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Araç, yetenek veya kullanım alanı ara…")
        self.search.textChanged.connect(self._populate)
        bar.addWidget(self.search, 1)
        self.category = QComboBox()
        self.category.addItem("Tüm kategoriler", "")
        for category in sorted({entry.category for entry in TOOLS}):
            self.category.addItem(category, category)
        self.category.currentIndexChanged.connect(self._populate)
        bar.addWidget(self.category)
        self.kind = QComboBox()
        self.kind.addItem("Tüm bağlantılar", "")
        for kind in ("API eklentisi", "MCP sunucusu"):
            self.kind.addItem(kind, kind)
        self.kind.currentIndexChanged.connect(self._populate)
        bar.addWidget(self.kind)
        self.refresh_button = QPushButton("API kaydını kontrol et")
        self.refresh_button.clicked.connect(self.refresh)
        bar.addWidget(self.refresh_button)
        layout.addLayout(bar)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Araç", "Kategori", "Bağlantı", "Kayıt durumu"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._show_entry)
        self.details = QTextBrowser()
        self.details.setOpenLinks(False)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.table)
        splitter.addWidget(self.details)
        splitter.setSizes([350, 300])
        layout.addWidget(splitter, 1)
        actions = QHBoxLayout()
        self.open_button = QPushButton("İlgili ekranı aç")
        self.open_button.setObjectName("primary")
        self.open_button.clicked.connect(self.open_selected)
        actions.addWidget(self.open_button)
        self.source_button = QPushButton("Resmî kaynak")
        self.source_button.clicked.connect(self.open_source)
        actions.addWidget(self.source_button)
        self.count = QLabel()
        actions.addWidget(self.count)
        actions.addStretch(1)
        layout.addLayout(actions)
        self.status = StatusLabel("API kaydı henüz kontrol edilmedi; katalog kullanıma açık.")
        layout.addWidget(self.status)
        self._populate()

    def activate(self) -> None:
        if not self.checked:
            self.refresh()

    def selected_entry(self) -> ToolEntry | None:
        row = self.table.currentRow()
        return self.visible_entries[row] if 0 <= row < len(self.visible_entries) else None

    def _entry_status(self, entry: ToolEntry) -> str:
        if not entry.plugin:
            return "MCP'de doğrula"
        if self.plugin_ids is None:
            return "Kontrol edilmedi"
        return "API'de kayıtlı" if entry.plugin in self.plugin_ids else "API'de bulunamadı"

    def _populate(self) -> None:
        selected = self.selected_entry()
        self.table.blockSignals(True)
        self.visible_entries = [
            entry for entry in TOOLS
            if entry.matches(self.search.text())
            and (not self.category.currentData() or entry.category == self.category.currentData())
            and (not self.kind.currentData() or entry.kind == self.kind.currentData())
        ]
        self.table.clearContents()
        self.table.setRowCount(len(self.visible_entries))
        selected_row = 0
        for row, entry in enumerate(self.visible_entries):
            for column, value in enumerate((entry.name, entry.category, entry.kind, self._entry_status(entry))):
                self.table.setItem(row, column, QTableWidgetItem(value))
            if selected is not None and selected.id == entry.id:
                selected_row = row
        if self.visible_entries:
            self.table.selectRow(selected_row)
        self.table.blockSignals(False)
        self.count.setText(f"{len(self.visible_entries)} / {len(TOOLS)} araç")
        self._show_entry()

    def _show_entry(self) -> None:
        entry = self.selected_entry()
        self.open_button.setEnabled(entry is not None)
        self.source_button.setEnabled(entry is not None)
        self.source_button.setToolTip(entry.source if entry is not None else "")
        if entry is None:
            self.details.setPlainText("Bu filtreyle eşleşen araç yok.")
            return
        capabilities = "\n".join(f"- {item}" for item in entry.capabilities)
        self.details.setMarkdown(
            f"## {entry.name}\n\n{entry.summary}\n\n"
            f"**Bağlantı:** {entry.kind} · {self._entry_status(entry)}\n\n"
            f"### Yetenekler\n{capabilities}\n\n"
            f"### Gereksinimler\n{entry.prerequisites}\n\n"
            f"### İzin ve veri sınırları\n{entry.permissions}\n\n"
            f"Resmî kaynak ve kurulum belgesi alttaki düğmede. İnceleme: {RESEARCHED_ON}"
        )

    def refresh(self) -> None:
        if self.loading:
            return
        self.loading = True
        self.checked = True
        self.plugin_ids = None
        self.refresh_button.setEnabled(False)
        self._populate()
        self.status.set("API eklenti kayıtları kontrol ediliyor…", "busy")

        def finish() -> None:
            self.loading = False
            self.refresh_button.setEnabled(True)
            self._populate()

        def done(plugins: list[dict[str, Any]]) -> None:
            self.plugin_ids = {plugin["id"] for plugin in plugins}
            finish()
            self.status.set("API kayıtları güncellendi. Haricî servis ve MCP bağlantı testi yapılmadı.", "ok")

        def failed(error: Exception) -> None:
            finish()
            self.status.set(f"API kaydı doğrulanamadı: {error_text(error)}. Çevrimdışı katalog korunuyor.", "error")

        run_background(self.ctx.api.plugins, done, failed)

    def open_selected(self) -> None:
        entry = self.selected_entry()
        if entry is not None:
            if entry.plugin and entry.page == "tools":
                self.open_plugin(entry.plugin)
            else:
                self.ctx.navigate(entry.page)

    def open_source(self) -> None:
        entry = self.selected_entry()
        if entry is not None:
            self.ctx.open_url(entry.source)
