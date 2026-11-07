from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from desktop.context import AppContext, error_text
from desktop.widgets import ResultView, StatusLabel

COLUMNS = [("job_id", "İş"), ("kind", "Tür"), ("status", "Durum"), ("progress", "İlerleme"),
           ("updated_at", "Güncellendi"), ("error", "Hata")]
STATUS_TR = {"queued": "sırada", "running": "çalışıyor", "cancel_requested": "iptal isteniyor",
             "completed": "tamamlandı", "failed": "başarısız", "cancelled": "iptal edildi"}


class JobsPage(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.loading = False
        layout = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.filter_box = QComboBox()
        self.filter_box.addItem("Tümü", None)
        for key, label in STATUS_TR.items():
            self.filter_box.addItem(label.capitalize(), key)
        self.filter_box.currentIndexChanged.connect(lambda _index: self.refresh())
        bar.addWidget(self.filter_box)
        for text, slot in (("Yenile", self.refresh), ("Ayrıntı", self.details), ("İptal et", self.cancel),
                           ("Yeniden dene", self.retry), ("Takılı işleri kurtar", self.recover)):
            button = QPushButton(text)
            button.clicked.connect(slot)
            bar.addWidget(button)
        self.auto = QCheckBox("Otomatik yenile (5 sn)")
        self.auto.setChecked(True)
        bar.addWidget(self.auto)
        bar.addStretch(1)
        layout.addLayout(bar)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels([label for _key, label in COLUMNS])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(len(COLUMNS) - 1, QHeaderView.ResizeMode.Stretch)
        self.table.doubleClicked.connect(lambda _index: self.details())
        self.result = ResultView(ctx)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.table)
        splitter.addWidget(self.result)
        splitter.setSizes([400, 260])
        layout.addWidget(splitter, 1)
        self.status = StatusLabel()
        layout.addWidget(self.status)

        self.timer = QTimer(self)
        self.timer.setInterval(5000)
        self.timer.timeout.connect(self._tick)

    def activate(self) -> None:
        self.refresh()
        self.timer.start()

    def deactivate(self) -> None:
        self.timer.stop()

    def _tick(self) -> None:
        if self.auto.isChecked() and self.isVisible() and not self.loading:
            self.refresh(quiet=True)

    def refresh(self, quiet: bool = False) -> None:
        payload: dict[str, Any] = {"limit": 100}
        if self.filter_box.currentData():
            payload["status"] = self.filter_box.currentData()
        self.loading = True

        def done(result: dict[str, Any]) -> None:
            self.loading = False
            selected = self.selected_job()
            jobs = result.get("jobs", [])
            self.table.setRowCount(len(jobs))
            for row, job in enumerate(jobs):
                for column, (key, _label) in enumerate(COLUMNS):
                    value = job.get(key)
                    if key == "status":
                        value = STATUS_TR.get(str(value), value)
                    elif key == "progress" and isinstance(value, (int, float)):
                        value = f"%{round(value * 100 if value <= 1 else value)}"
                    item = QTableWidgetItem("" if value is None else str(value))
                    item.setData(Qt.ItemDataRole.UserRole, job.get("job_id"))
                    self.table.setItem(row, column, item)
                if job.get("job_id") == selected:
                    self.table.selectRow(row)
            self.table.resizeColumnsToContents()
            if not quiet:
                self.status.set(f"{len(jobs)} iş listelendi.", "ok")

        def failed(error: Exception) -> None:
            self.loading = False
            self.status.set(error_text(error), "error")

        self.ctx.call_action(self, "jobs", "list", payload, on_done=done, on_error=failed)

    def selected_job(self) -> str | None:
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _need_job(self) -> str | None:
        job_id = self.selected_job()
        if job_id is None:
            self.status.set("Önce tablodan bir iş seç.", "warn")
        return job_id

    def details(self) -> None:
        job_id = self._need_job()
        if job_id:
            self.ctx.call_action(self, "jobs", "get", {"job_id": job_id}, on_done=self.result.show_result)

    def cancel(self) -> None:
        job_id = self._need_job()
        if job_id:
            self.ctx.call_action(self, "jobs", "cancel", {"job_id": job_id}, approval="Seçili iş iptal edilsin mi?",
                                 on_done=lambda result: (self.result.show_result(result), self.refresh()))

    def retry(self) -> None:
        job_id = self._need_job()
        if job_id:
            self.ctx.call_action(self, "jobs", "retry", {"job_id": job_id}, approval="Seçili iş yeniden denensin mi?",
                                 on_done=lambda result: (self.result.show_result(result), self.refresh()))

    def recover(self) -> None:
        self.ctx.call_action(
            self, "jobs", "recover_stale", {"stale_after_seconds": 900},
            approval="15 dakikadır ilerlemeyen işler kurtarılsın mı?",
            on_done=lambda result: (self.result.show_result(result), self.refresh()),
        )
