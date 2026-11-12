from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from desktop.context import AppContext, error_text
from desktop.forms import FormWidget, load_groups
from desktop.tasks import run_background
from desktop.widgets import ResultView, StatusLabel, mono_font

ADVANCED = "__advanced__"


class AdvancedRunner(QWidget):
    """Runs any plugin action with a JSON payload, so nothing the API offers is out of reach."""

    result_ready = Signal(str, str, object)

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.plugins: list[dict[str, Any]] = []
        layout = QVBoxLayout(self)
        title = QLabel("Gelişmiş: herhangi bir eklenti eylemi")
        title.setObjectName("formTitle")
        layout.addWidget(title)
        form = QFormLayout()
        self.plugin_box = QComboBox()
        self.plugin_box.currentIndexChanged.connect(self._plugin_changed)
        self.action_box = QComboBox()
        self.description = QLabel()
        self.description.setWordWrap(True)
        self.description.setObjectName("hint")
        self.payload = QPlainTextEdit("{}")
        self.payload.setFont(mono_font())
        self.payload.setFixedHeight(160)
        form.addRow("Eklenti", self.plugin_box)
        form.addRow("", self.description)
        form.addRow("Eylem", self.action_box)
        form.addRow("Payload (JSON)", self.payload)
        layout.addLayout(form)
        row = QHBoxLayout()
        load = QPushButton("Eklentileri yükle")
        load.clicked.connect(self.load)
        run = QPushButton("Çalıştır")
        run.setObjectName("primary")
        run.clicked.connect(self.run)
        row.addWidget(load)
        row.addWidget(run)
        row.addStretch(1)
        layout.addLayout(row)
        self.status = StatusLabel("Onay gerektiren eylemlerde tek bir onay sorulur.")
        layout.addWidget(self.status)
        self.result = ResultView(ctx)
        layout.addWidget(self.result, 1)

    def load(self) -> None:
        def done(plugins: list[dict[str, Any]]) -> None:
            self.plugins = sorted(plugins, key=lambda item: item["id"])
            self.plugin_box.clear()
            for plugin in self.plugins:
                self.plugin_box.addItem(f"{plugin['id']} — {plugin.get('name', '')}", plugin["id"])
            self.status.set(f"{len(self.plugins)} eklenti yüklendi.", "ok")

        run_background(self.ctx.api.plugins, done, lambda error: self.status.set(error_text(error), "error"))

    def _plugin_changed(self, index: int) -> None:
        self.action_box.clear()
        if 0 <= index < len(self.plugins):
            plugin = self.plugins[index]
            self.description.setText(plugin.get("description", ""))
            self.action_box.addItems(list(plugin.get("actions", [])))

    def run(self) -> None:
        plugin, action = self.plugin_box.currentData(), self.action_box.currentText()
        if not plugin or not action:
            self.status.set("Önce eklentileri yükleyip eylem seç.", "warn")
            return
        try:
            payload = json.loads(self.payload.toPlainText() or "{}")
            if not isinstance(payload, dict):
                raise ValueError
        except ValueError:
            self.status.set("Payload bir JSON nesnesi olmalı.", "error")
            return
        self.status.set("Çalışıyor…", "busy")
        self.ctx.call_action(
            self, plugin, action, payload,
            on_done=lambda result: (
                self.status.set("Tamamlandı.", "ok"), self.result.show_result(result),
                self.result_ready.emit(plugin, action, result),
            ),
            on_error=lambda error: self.status.set(error_text(error), "error"),
        )


class ToolsPage(QWidget):
    result_ready = Signal(str, str, object)

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.groups = load_groups()
        self.forms: dict[str, QWidget] = {}

        left = QWidget()
        left_layout = QVBoxLayout(left)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Araç ara…")
        self.search.textChanged.connect(self._filter)
        left_layout.addWidget(self.search)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.currentItemChanged.connect(self._select)
        self.tree.itemClicked.connect(self._toggle_group)
        left_layout.addWidget(self.tree, 1)

        self.stack = QStackedWidget()
        placeholder = QLabel("Soldan bir araç seç.\n\nOnay gerektiren işlemlerde yalnızca bir kez sorulur.")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setObjectName("hint")
        self.stack.addWidget(placeholder)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(self.stack)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 900])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)
        self._populate()

    def _populate(self) -> None:
        seen: set[str] = set()
        for group in self.groups:
            parent = QTreeWidgetItem([group["label"]])
            parent.setFlags(parent.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            for index, form in enumerate(group.get("forms", [])):
                key = f"{group['id']}:{index}"
                # Web tool groups and the curated desktop groups overlap for a few actions; show each action once.
                signature = f"{form['plugin']}.{form['action']}"
                if signature in seen and form["plugin"] not in {"reports", "prompt_library"}:
                    continue
                seen.add(signature)
                child = QTreeWidgetItem([form["title"]])
                child.setData(0, Qt.ItemDataRole.UserRole, (key, form))
                child.setToolTip(0, signature)
                parent.addChild(child)
            if parent.childCount():
                self.tree.addTopLevelItem(parent)
        advanced = QTreeWidgetItem(["Gelişmiş"])
        runner = QTreeWidgetItem(["Herhangi bir eklenti eylemi"])
        runner.setData(0, Qt.ItemDataRole.UserRole, (ADVANCED, None))
        advanced.addChild(runner)
        self.tree.addTopLevelItem(advanced)
        if self.tree.topLevelItemCount():
            self.tree.topLevelItem(0).setExpanded(True)

    @staticmethod
    def _toggle_group(item: QTreeWidgetItem, _column: int) -> None:
        if item.childCount():
            item.setExpanded(not item.isExpanded())

    def form_specs(self) -> list[dict[str, Any]]:
        specs = []
        for top in range(self.tree.topLevelItemCount()):
            parent = self.tree.topLevelItem(top)
            for child in range(parent.childCount()):
                _key, spec = parent.child(child).data(0, Qt.ItemDataRole.UserRole)
                if spec is not None:
                    specs.append(spec)
        return specs

    def select_plugin(self, plugin: str) -> bool:
        self.search.clear()
        for top in range(self.tree.topLevelItemCount()):
            parent = self.tree.topLevelItem(top)
            for index in range(parent.childCount()):
                child = parent.child(index)
                _key, spec = child.data(0, Qt.ItemDataRole.UserRole)
                if spec is not None and spec["plugin"] == plugin:
                    parent.setExpanded(True)
                    self.tree.setCurrentItem(child)
                    self.tree.scrollToItem(child)
                    return True
        return False

    def _select(self, item: QTreeWidgetItem | None, _previous: QTreeWidgetItem | None = None) -> None:
        if item is None:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        key, spec = data
        widget = self.forms.get(key)
        if widget is None:
            if key == ADVANCED:
                inner: QWidget = AdvancedRunner(self.ctx)
                inner.load()
            else:
                inner = FormWidget(self.ctx, spec)
            inner.result_ready.connect(self.result_ready.emit)
            widget = QScrollArea()
            widget.setWidgetResizable(True)
            widget.setWidget(inner)
            self.forms[key] = widget
            self.stack.addWidget(widget)
        self.stack.setCurrentWidget(widget)

    def _filter(self, text: str) -> None:
        needle = text.strip().lower()
        for top in range(self.tree.topLevelItemCount()):
            parent = self.tree.topLevelItem(top)
            visible = 0
            for child_index in range(parent.childCount()):
                child = parent.child(child_index)
                match = not needle or needle in child.text(0).lower() or needle in parent.text(0).lower() \
                    or needle in (child.toolTip(0) or "").lower()
                child.setHidden(not match)
                visible += int(match)
            parent.setHidden(visible == 0)
            parent.setExpanded(bool(needle) and visible > 0)
