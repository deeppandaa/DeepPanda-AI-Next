from __future__ import annotations

import json
from typing import Any

import httpx
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from desktop.context import AppContext, confirm, error_text
from desktop.tasks import run_background
from desktop.widgets import StatusLabel, mono_font


class DatabasePage(QWidget):
    """Read-only SQL browser for the SQLite databases in the API's /data volume, plus the sqlite-web manager."""

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.manager_url = ctx.settings.db_manager_url
        layout = QVBoxLayout(self)
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Veritabanı"))
        self.db_box = QComboBox()
        self.db_box.setMinimumWidth(220)
        self.db_box.currentIndexChanged.connect(lambda _index: self.load_tables())
        bar.addWidget(self.db_box)
        for text, slot in (("Yenile", self.refresh), ("Bütünlük kontrolü", self.check), ("Yedek al", self.backup),
                           ("Yöneticiyi aç (sqlite-web)", self.open_manager)):
            button = QPushButton(text)
            button.clicked.connect(slot)
            bar.addWidget(button)
        bar.addStretch(1)
        layout.addLayout(bar)

        self.tables = QTreeWidget()
        self.tables.setHeaderLabels(["Tablo / sütun", "Tür / satır"])
        self.tables.itemDoubleClicked.connect(self._table_clicked)

        editor_panel = QWidget()
        editor_layout = QVBoxLayout(editor_panel)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        self.sql = QPlainTextEdit()
        self.sql.setFont(mono_font())
        self.sql.setPlaceholderText("SELECT * FROM memories LIMIT 50   (salt okunur; Ctrl+Enter çalıştırır)")
        self.sql.setFixedHeight(120)
        editor_layout.addWidget(self.sql)
        run_row = QHBoxLayout()
        run = QPushButton("Sorguyu çalıştır")
        run.setObjectName("primary")
        run.clicked.connect(self.run_query)
        run_row.addWidget(run)
        run_row.addWidget(QLabel("Satır sınırı"))
        self.limit = QSpinBox()
        self.limit.setRange(1, 500)
        self.limit.setValue(200)
        run_row.addWidget(self.limit)
        run_row.addStretch(1)
        editor_layout.addLayout(run_row)
        self.grid = QTableWidget(0, 0)
        self.grid.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.grid.setAlternatingRowColors(True)
        editor_layout.addWidget(self.grid, 1)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.tables)
        splitter.addWidget(editor_panel)
        splitter.setSizes([300, 900])
        layout.addWidget(splitter, 1)
        self.status = StatusLabel("Tabloya çift tıklayınca örnek sorgu hazırlanır.")
        layout.addWidget(self.status)
        QShortcut(QKeySequence("Ctrl+Return"), self.sql, activated=self.run_query)

    def activate(self) -> None:
        if self.db_box.count() == 0:
            self.refresh()

    def refresh(self) -> None:
        def done(result: dict[str, Any]) -> None:
            self.manager_url = self.ctx.settings.db_manager_url or result.get("manager_url") or self.manager_url
            current = self.db_box.currentData()
            self.db_box.blockSignals(True)
            self.db_box.clear()
            for database in result.get("databases", []):
                size_kb = int(database.get("size_bytes", 0)) // 1024
                self.db_box.addItem(f"{database['name']}  ({database.get('tables', '?')} tablo, {size_kb} KB)", database["name"])
            index = self.db_box.findData(current)
            self.db_box.setCurrentIndex(max(index, 0))
            self.db_box.blockSignals(False)
            self.status.set(f"{self.db_box.count()} veritabanı · klasör: {result.get('data_dir')}", "ok")
            self.load_tables()

        self.ctx.call_action(self, "database", "overview", {}, on_done=done)

    def load_tables(self) -> None:
        database = self.db_box.currentData()
        if not database:
            return

        def done(result: dict[str, Any]) -> None:
            self.tables.clear()
            for table in result.get("tables", []):
                parent = QTreeWidgetItem([table["name"], f"{table.get('rows', 0)} satır"])
                parent.setData(0, Qt.ItemDataRole.UserRole, table["name"])
                for column in table.get("columns", []):
                    flags = " · PK" if column.get("primary_key") else ""
                    parent.addChild(QTreeWidgetItem([column["name"], f"{column.get('type', '')}{flags}"]))
                self.tables.addTopLevelItem(parent)
            self.tables.resizeColumnToContents(0)

        self.ctx.call_action(self, "database", "tables", {"database": database}, on_done=done)

    def _table_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        table = item.data(0, Qt.ItemDataRole.UserRole)
        if table:
            quoted = '"' + str(table).replace('"', '""') + '"'
            self.sql.setPlainText(f"SELECT * FROM {quoted} LIMIT 100")
            self.run_query()

    def run_query(self) -> None:
        database, sql = self.db_box.currentData(), self.sql.toPlainText().strip()
        if not database or not sql:
            self.status.set("Veritabanı seç ve bir SELECT sorgusu yaz.", "warn")
            return
        self.status.set("Sorgu çalışıyor…", "busy")

        def done(result: dict[str, Any]) -> None:
            columns, rows = result.get("columns", []), result.get("rows", [])
            self.grid.clear()
            self.grid.setColumnCount(len(columns))
            self.grid.setRowCount(len(rows))
            self.grid.setHorizontalHeaderLabels(columns)
            for row_index, row in enumerate(rows):
                for column_index, value in enumerate(row):
                    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
                    item = QTableWidgetItem(text[:2000])
                    item.setToolTip(text[:4000])
                    self.grid.setItem(row_index, column_index, item)
            self.grid.resizeColumnsToContents()
            more = " (daha fazla satır var)" if result.get("truncated") else ""
            self.status.set(f"{len(rows)} satır · {result.get('elapsed_ms')} ms{more}", "ok")

        self.ctx.call_action(self, "database", "query", {"database": database, "sql": sql, "limit": self.limit.value()},
                             on_done=done, on_error=lambda error: self.status.set(error_text(error), "error"))

    def check(self) -> None:
        database = self.db_box.currentData()
        if database:
            self.ctx.call_action(self, "database", "check", {"database": database}, on_done=lambda result: self.status.set(
                "Bütünlük: sorun yok." if result.get("ok") else "Bütünlük sorunları: " + "; ".join(result.get("messages", [])),
                "ok" if result.get("ok") else "error"))

    def backup(self) -> None:
        database = self.db_box.currentData()
        if database:
            self.ctx.call_action(
                self, "database", "backup", {"database": database},
                approval=f"{database} için /data/db-backups altına yedek alınsın mı?",
                on_done=lambda result: self.status.set(f"Yedek alındı: {result.get('backup')}", "ok"),
            )

    def open_manager(self) -> None:
        url = self.ctx.settings.db_manager_url or self.manager_url

        def reachable() -> bool:
            try:
                return httpx.get(url, timeout=3).status_code < 500
            except httpx.HTTPError:
                return False

        def after_probe(ok: bool) -> None:
            if ok:
                self.ctx.open_url(url)
                return
            if not confirm(self, "Veritabanı yöneticisi (sqlite-web) çalışmıyor. Docker'da başlatılsın mı?\n"
                                 "(docker compose --profile manager up -d db-manager — varsayılan salt okunur)"):
                return
            self.status.set("db-manager başlatılıyor…", "busy")

            def started(result: dict[str, Any]) -> None:
                if result["ok"]:
                    self.status.set("db-manager başlatıldı.", "ok")
                    self.ctx.open_url(url)
                else:
                    self.status.set(result["output"][-600:], "error")

            self.ctx.run_command(["docker", "compose", "--profile", "manager", "up", "-d", "db-manager"], started)

        run_background(reachable, after_probe, lambda _error: after_probe(False))
