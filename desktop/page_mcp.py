from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from desktop.config import ensure_backend_importable
from desktop.context import CREATE_NO_WINDOW, AppContext, confirm, error_text
from desktop.tasks import run_background
from desktop.widgets import ResultView, StatusLabel, mono_font

ensure_backend_importable()
from app.plugins import mcp_bridge
from app.plugins.integration_errors import IntegrationUnavailableError


def ensure_github_token() -> None:
    """Copilot's GitHub MCP server needs a token; reuse the GitHub CLI login silently (kept in memory only)."""
    if os.getenv("GITHUB_TOKEN") or shutil.which("gh") is None:
        return
    try:
        completed = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=15,
                                   check=False, creationflags=CREATE_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        return
    token = completed.stdout.strip()
    if completed.returncode == 0 and token:
        os.environ["GITHUB_TOKEN"] = token


def schema_template(schema: Any) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(schema, dict):
        return {}, []
    properties = schema.get("properties") or {}
    required = [name for name in schema.get("required", []) if name in properties]
    defaults = {"string": "", "integer": 0, "number": 0, "boolean": False, "array": [], "object": {}}
    template = {}
    for name in required:
        spec = properties.get(name) or {}
        kind = spec.get("type")
        if isinstance(kind, list):
            kind = next((item for item in kind if item != "null"), "string")
        template[name] = spec.get("default", (spec.get("enum") or [None])[0] or defaults.get(kind, ""))
    optional = [name for name in properties if name not in required]
    return template, optional


class McpPage(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.servers: dict[str, dict[str, Any]] = {}
        self.tools: dict[str, list[dict[str, Any]]] = {}
        self.current_tool: dict[str, Any] | None = None

        left = QWidget()
        left_layout = QVBoxLayout(left)
        title = QLabel("MCP sunucuları")
        title.setObjectName("sectionTitle")
        left_layout.addWidget(title)
        self.server_list = QListWidget()
        self.server_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.server_list.currentItemChanged.connect(lambda item, _prev: self._server_selected(item))
        left_layout.addWidget(self.server_list, 1)
        refresh = QPushButton("Yapılandırmayı yeniden oku")
        refresh.clicked.connect(self.load_servers)
        left_layout.addWidget(refresh)
        hint = QLabel("Kaynak: VS Code/Copilot mcp.json + proje mcp-servers.json.\nAraçlar bu bilgisayarda çalışır.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        left_layout.addWidget(hint)

        middle = QWidget()
        middle_layout = QVBoxLayout(middle)
        self.tool_filter = QLineEdit()
        self.tool_filter.setPlaceholderText("Araç ara…")
        self.tool_filter.textChanged.connect(self._filter_tools)
        middle_layout.addWidget(self.tool_filter)
        self.tool_list = QListWidget()
        self.tool_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tool_list.currentItemChanged.connect(lambda item, _prev: self._tool_selected(item))
        middle_layout.addWidget(self.tool_list, 1)
        load_tools = QPushButton("Araçları getir")
        load_tools.clicked.connect(self.load_tools)
        middle_layout.addWidget(load_tools)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.tool_title = QLabel("Bir sunucu ve araç seç")
        self.tool_title.setObjectName("formTitle")
        right_layout.addWidget(self.tool_title)
        self.tool_description = QLabel()
        self.tool_description.setWordWrap(True)
        self.tool_description.setObjectName("hint")
        self.tool_description.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        right_layout.addWidget(self.tool_description)
        self.arguments = QPlainTextEdit("{}")
        self.arguments.setFont(mono_font())
        self.arguments.setFixedHeight(150)
        right_layout.addWidget(QLabel("Argümanlar (JSON)"))
        right_layout.addWidget(self.arguments)
        row = QHBoxLayout()
        self.run_button = QPushButton("Aracı çalıştır")
        self.run_button.setObjectName("primary")
        self.run_button.clicked.connect(self.call_tool)
        row.addWidget(self.run_button)
        row.addStretch(1)
        right_layout.addLayout(row)
        self.status = StatusLabel()
        right_layout.addWidget(self.status)
        self.result = ResultView(ctx)
        right_layout.addWidget(self.result, 1)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        for widget in (left, middle, right):
            splitter.addWidget(widget)
        splitter.setSizes([260, 300, 700])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

    def activate(self) -> None:
        if not self.servers:
            self.load_servers()

    def _prepare(self, entry: dict[str, Any]) -> dict[str, Any]:
        prepared = dict(entry)
        if mcp_bridge.server_transport(prepared) == "stdio":
            prepared.setdefault("cwd", self.ctx.settings.project_dir)
            if prepared.get("command") in {"python", "python3"} and str(prepared.get("_source", "")).endswith("mcp-servers.json"):
                prepared["command"] = sys.executable
        return prepared

    def load_servers(self) -> None:
        paths = self.ctx.settings.mcp_config_paths()

        def work() -> tuple[dict[str, dict[str, Any]], list[str]]:
            ensure_github_token()
            servers: dict[str, dict[str, Any]] = {}
            problems: list[str] = []
            # One unreadable config (e.g. a locked VS Code mcp.json) must not hide the servers from the others.
            for path in paths:
                try:
                    servers.update(mcp_bridge.load_server_configs([path]))
                except IntegrationUnavailableError as exc:
                    problems.append(str(exc))
            return {name: self._prepare(entry) for name, entry in servers.items()}, problems

        def done(loaded: tuple[dict[str, dict[str, Any]], list[str]]) -> None:
            servers, problems = loaded
            self.servers = servers
            self.tools.clear()
            self.server_list.clear()
            for name, entry in sorted(servers.items()):
                info = mcp_bridge.describe_server(name, entry)
                mark = "●" if info["available"] else "○"
                item = QListWidgetItem(f"{mark} {name}  ·  {info['transport']}")
                item.setData(Qt.ItemDataRole.UserRole, name)
                item.setToolTip(f"{info['target']}\n{info['source']}\n{info['reason']}".strip())
                self.server_list.addItem(item)
            if problems:
                self.status.set(f"{len(servers)} MCP sunucusu bulundu. Atlanan: {' · '.join(problems)}", "warn")
            else:
                self.status.set(f"{len(servers)} MCP sunucusu bulundu ({', '.join(str(path) for path in paths)}).", "ok")

        run_background(work, done, lambda error: self.status.set(error_text(error), "error"))

    def _server_name(self) -> str | None:
        item = self.server_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _server_selected(self, item: QListWidgetItem | None) -> None:
        self.tool_list.clear()
        self.current_tool = None
        if item is None:
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        info = mcp_bridge.describe_server(name, self.servers[name])
        self.tool_title.setText(name)
        self.tool_description.setText(f"{info['target']}\n{info['reason']}".strip())
        if name in self.tools:
            self._show_tools(name)
        elif info["available"]:
            self.load_tools()

    def load_tools(self) -> None:
        name = self._server_name()
        if not name:
            self.status.set("Önce bir MCP sunucusu seç.", "warn")
            return
        entry = self.servers[name]
        info = mcp_bridge.describe_server(name, entry)
        if not info["available"]:
            self.status.set(f"{name}: {info['reason']}", "error")
            return
        self.status.set(f"{name} araçları alınıyor… (ilk bağlantı biraz sürebilir)", "busy")

        def done(tools: list[dict[str, Any]]) -> None:
            self.tools[name] = tools
            if self._server_name() == name:
                self._show_tools(name)
            self.status.set(f"{name}: {len(tools)} araç.", "ok")

        run_background(lambda: asyncio.run(mcp_bridge.list_tools(entry)), done,
                       lambda error: self.status.set(f"{name}: {error_text(error)}", "error"))

    def _show_tools(self, name: str) -> None:
        self.tool_list.clear()
        for tool in sorted(self.tools.get(name, []), key=lambda item: item["name"]):
            item = QListWidgetItem(("🔒 " if not tool.get("read_only") else "👁 ") + tool["name"])
            item.setData(Qt.ItemDataRole.UserRole, tool)
            item.setToolTip(tool.get("description", "")[:600])
            self.tool_list.addItem(item)
        self._filter_tools(self.tool_filter.text())

    def _filter_tools(self, text: str) -> None:
        needle = text.strip().lower()
        for index in range(self.tool_list.count()):
            item = self.tool_list.item(index)
            tool = item.data(Qt.ItemDataRole.UserRole) or {}
            haystack = f"{tool.get('name', '')} {tool.get('description', '')}".lower()
            item.setHidden(bool(needle) and needle not in haystack)

    def _tool_selected(self, item: QListWidgetItem | None) -> None:
        if item is None:
            return
        tool = item.data(Qt.ItemDataRole.UserRole)
        self.current_tool = tool
        template, optional = schema_template(tool.get("input_schema"))
        self.tool_title.setText(f"{self._server_name()} › {tool['name']}")
        extra = f"\n\nİsteğe bağlı alanlar: {', '.join(optional)}" if optional else ""
        mode = "Salt okunur araç (onay sorulmaz)." if tool.get("read_only") else "Değişiklik yapabilir; çalıştırmadan önce bir kez onay sorulur."
        self.tool_description.setText(f"{tool.get('description', '')[:1500]}\n\n{mode}{extra}")
        self.arguments.setPlainText(json.dumps(template, ensure_ascii=False, indent=2))

    def call_tool(self) -> None:
        name, tool = self._server_name(), self.current_tool
        if not name or not tool:
            self.status.set("Önce bir araç seç.", "warn")
            return
        try:
            arguments = json.loads(self.arguments.toPlainText() or "{}")
            if not isinstance(arguments, dict):
                raise ValueError
        except ValueError:
            self.status.set("Argümanlar bir JSON nesnesi olmalı.", "error")
            return
        if not tool.get("read_only") and not confirm(self, f"{name} › {tool['name']} çalıştırılsın mı?"):
            self.status.set("Onay verilmedi; araç çalıştırılmadı.", "warn")
            return
        entry = self.servers[name]
        self.run_button.setEnabled(False)
        self.status.set("Araç çalışıyor…", "busy")

        def done(result: dict[str, Any]) -> None:
            self.run_button.setEnabled(True)
            texts = [block.get("text", "") for block in result.get("content", []) if block.get("type") == "text"]
            self.status.set("Araç hata döndürdü." if result.get("is_error") else "Tamamlandı.",
                            "error" if result.get("is_error") else "ok")
            if texts and not result.get("structured"):
                self.result.show_text(self._pretty_text("\n\n".join(texts)))
            else:
                self.result.show_result(result)

        def failed(error: Exception) -> None:
            self.run_button.setEnabled(True)
            self.status.set(error_text(error), "error")

        run_background(lambda: asyncio.run(mcp_bridge.call_tool(entry, tool["name"], arguments)), done, failed)

    @staticmethod
    def _pretty_text(text: str) -> str:
        try:
            return json.dumps(json.loads(text), ensure_ascii=False, indent=2)
        except ValueError:
            return text
