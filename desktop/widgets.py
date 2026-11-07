from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desktop.context import AppContext


def pretty(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def mono_font() -> QFont:
    font = QFont("Cascadia Mono")
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPointSize(10)
    return font


def collect_links(value: Any, downloads: list[tuple[str, str]], jobs: list[str]) -> None:
    if isinstance(value, list):
        for item in value:
            collect_links(item, downloads, jobs)
    elif isinstance(value, dict):
        for key, item in value.items():
            if key == "download_url" and isinstance(item, str) and item.startswith("/api/"):
                downloads.append((item, str(value.get("filename") or value.get("asset_id") or item)))
            elif key == "job_id" and isinstance(item, str):
                jobs.append(item)
            else:
                collect_links(item, downloads, jobs)


class StatusLabel(QLabel):
    def __init__(self, text: str = "") -> None:
        super().__init__(text)
        self.setWordWrap(True)
        self.setObjectName("status")

    def set(self, text: str, kind: str = "info") -> None:
        self.setProperty("kind", kind)
        self.setText(text)
        self.style().unpolish(self)
        self.style().polish(self)


class ResultView(QWidget):
    """JSON result + quick buttons for downloads, jobs and prompt templates (same affordances as the web UI)."""

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.links = QHBoxLayout()
        self.links.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addLayout(self.links)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setFont(mono_font())
        self.text.setPlaceholderText("Sonuç burada görünür.")
        layout.addWidget(self.text, 1)

    def clear(self) -> None:
        self.text.clear()
        while self.links.count():
            item = self.links.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

    def show_result(self, result: Any) -> None:
        self.clear()
        downloads: list[tuple[str, str]] = []
        jobs: list[str] = []
        collect_links(result, downloads, jobs)
        for url, name in downloads[:8]:
            self._button(f"İndir: {name}", lambda _=False, u=url: self.ctx.open_url(self.ctx.api.url(u)))
        if jobs:
            self._button("İşleri izle", lambda _=False: self.ctx.navigate("jobs"))
        for prompt in self._prompts(result)[:10]:
            title = str(prompt.get("title", "Şablon"))[:40]
            content = prompt.get("content")
            if isinstance(content, str) and content:
                self._button(f"Sohbete ekle: {title}", lambda _=False, c=content: self.ctx.insert_into_chat(c))
        self.text.setPlainText(pretty(result))

    def show_text(self, text: str) -> None:
        self.clear()
        self.text.setPlainText(text)

    @staticmethod
    def _prompts(result: Any) -> list[dict[str, Any]]:
        if not isinstance(result, dict):
            return []
        prompts = result.get("prompts")
        if isinstance(prompts, list):
            return [item for item in prompts if isinstance(item, dict) and not item.get("preview")]
        prompt = result.get("prompt")
        return [prompt] if isinstance(prompt, dict) else []

    def _button(self, text: str, slot: Any) -> None:
        button = QPushButton(text)
        button.setObjectName("link")
        button.clicked.connect(slot)
        self.links.addWidget(button)
