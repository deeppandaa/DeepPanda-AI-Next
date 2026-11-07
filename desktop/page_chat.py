from __future__ import annotations

from datetime import datetime
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from desktop.api import ApiError
from desktop.context import AppContext, confirm, error_text
from desktop.tasks import run_background
from desktop.widgets import StatusLabel

OPENJARVIS = "__openjarvis__"
EMBEDDING_HINTS = ("embed", "bge", "minilm", "nomic")


def _local_time(value: Any) -> str:
    text = str(value or "")
    try:
        return datetime.fromisoformat(text).astimezone().strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return text[:16]


class ChatPage(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.session_id: str | None = None
        self.messages: list[dict[str, str]] = []
        self.last_question = ""
        self.last_answer = ""
        self.suggested: list[str] = []
        self.busy = False

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_sessions())
        splitter.addWidget(self._build_conversation())
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([240, 900])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self.send)
        QShortcut(QKeySequence("Ctrl+Enter"), self, activated=self.send)
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self.new_chat)

    # ---------- layout ----------
    def _build_sessions(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        title = QLabel("Sohbetler")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        new_button = QPushButton("+ Yeni sohbet")
        new_button.setObjectName("primary")
        new_button.clicked.connect(self.new_chat)
        layout.addWidget(new_button)
        self.session_list = QListWidget()
        self.session_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.session_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.session_list.itemClicked.connect(self._open_session)
        layout.addWidget(self.session_list, 1)
        row = QHBoxLayout()
        refresh = QPushButton("Yenile")
        refresh.clicked.connect(self.refresh_sessions)
        delete = QPushButton("Sil")
        delete.clicked.connect(self.delete_session)
        row.addWidget(refresh)
        row.addWidget(delete)
        layout.addLayout(row)
        return panel

    def _build_conversation(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        top = QHBoxLayout()
        top.addWidget(QLabel("Model"))
        self.model_box = QComboBox()
        self.model_box.setMinimumWidth(260)
        top.addWidget(self.model_box, 1)
        top.addWidget(QLabel("Mod"))
        self.workflow_box = QComboBox()
        self.workflow_box.addItem("Standart", "standard")
        top.addWidget(self.workflow_box)
        reload_models = QPushButton("↻")
        reload_models.setToolTip("Model listesini yenile")
        reload_models.setFixedWidth(36)
        reload_models.clicked.connect(self.refresh_models)
        top.addWidget(reload_models)
        layout.addLayout(top)

        self.transcript = QTextBrowser()
        self.transcript.setOpenExternalLinks(True)
        self.transcript.setObjectName("transcript")
        layout.addWidget(self.transcript, 1)

        self.suggestion_row = QWidget()
        suggestion_layout = QHBoxLayout(self.suggestion_row)
        suggestion_layout.setContentsMargins(0, 0, 0, 0)
        self.suggestion_label = QLabel()
        self.suggestion_label.setWordWrap(True)
        ask_other = QPushButton("Başka yapay zekâya sor")
        ask_other.clicked.connect(self.ask_other_ai)
        suggestion_layout.addWidget(self.suggestion_label, 1)
        suggestion_layout.addWidget(ask_other)
        self.suggestion_row.hide()
        layout.addWidget(self.suggestion_row)

        self.input = QPlainTextEdit()
        self.input.setPlaceholderText("Mesajını yaz…  (Ctrl+Enter gönderir)")
        self.input.setFixedHeight(110)
        layout.addWidget(self.input)
        bottom = QHBoxLayout()
        self.status = StatusLabel()
        bottom.addWidget(self.status, 1)
        self.send_button = QPushButton("Gönder")
        self.send_button.setObjectName("primary")
        self.send_button.clicked.connect(self.send)
        bottom.addWidget(self.send_button)
        layout.addLayout(bottom)
        return panel

    # ---------- data loading ----------
    def activate(self) -> None:
        if self.model_box.count() == 0:
            self.refresh_models()
            self.refresh_sessions()
            self._load_workflows()

    def refresh_models(self) -> None:
        current = self.model_box.currentData()
        self.model_box.clear()
        self.model_box.addItem("Otomatik (en uygun yerel model)", None)

        def load() -> dict[str, Any]:
            out: dict[str, Any] = {"ollama": [], "default": None, "cloud": [], "errors": []}
            try:
                data = self.ctx.api.models()
                out["default"] = data.get("default_model")
                for model in data.get("models", []):
                    name = model.get("name") or model.get("model")
                    if name and not any(hint in name.lower() for hint in EMBEDDING_HINTS):
                        details = model.get("details") or {}
                        out["ollama"].append((name, details.get("parameter_size", "")))
            except ApiError as exc:
                out["errors"].append(f"Ollama: {exc.detail}")
            try:
                out["cloud"] = self.ctx.api.action("cloud_providers", "catalog", {}).get("providers", [])
            except ApiError:
                out["cloud"] = []
            return out

        def done(data: dict[str, Any]) -> None:
            for name, size in data["ollama"]:
                label = f"Yerel: {name}" + (f"  ({size})" if size else "")
                if name == data["default"]:
                    label += "  ★"
                self.model_box.addItem(label, name)
            self.model_box.addItem("OpenJarvis (WSL ajanı)", OPENJARVIS)
            self.model_box.addItem("FreeLLMAPI (otomatik)", "freellmapi:auto")
            for provider in data["cloud"]:
                state = "" if provider.get("configured") else "  (oturum yok)"
                self.model_box.addItem(f"Bulut: {provider.get('name', provider['id'])}{state}", f"cloud:{provider['id']}")
            index = self.model_box.findData(current)
            self.model_box.setCurrentIndex(max(index, 0))
            if data["errors"]:
                self.status.set("; ".join(data["errors"]), "warn")

        run_background(load, done, lambda error: self.status.set(error_text(error), "error"))

    def _load_workflows(self) -> None:
        def done(result: Any) -> None:
            workflows = result.get("workflows", []) if isinstance(result, dict) else []
            if workflows:
                self.workflow_box.clear()
                for item in workflows:
                    self.workflow_box.addItem(str(item.get("name") or item.get("id")), item.get("id"))

        run_background(lambda: self.ctx.api.action("workflows", "catalog", {}), done, lambda _error: None)

    def refresh_sessions(self) -> None:
        def done(result: dict[str, Any]) -> None:
            self.session_list.clear()
            for session in result.get("sessions", []):
                when = _local_time(session.get("updated_at"))
                count = session.get("message_count", 0)
                item = QListWidgetItem(f"{session.get('title') or 'Sohbet'}\n{when} · {count} mesaj")
                item.setData(Qt.ItemDataRole.UserRole, session["session_id"])
                item.setToolTip(f"{session.get('message_count', 0)} mesaj")
                self.session_list.addItem(item)
                if session["session_id"] == self.session_id:
                    item.setSelected(True)

        run_background(lambda: self.ctx.api.sessions(100), done, lambda error: self.status.set(error_text(error), "error"))

    def _open_session(self, item: QListWidgetItem) -> None:
        session_id = item.data(Qt.ItemDataRole.UserRole)

        def done(result: dict[str, Any]) -> None:
            self.session_id = session_id
            self.messages = [
                {"role": message["role"], "content": message["content"], "meta": ""}
                for message in result.get("messages", [])
            ]
            self.suggestion_row.hide()
            self._render()
            self.status.set("Sohbet yüklendi.", "ok")

        run_background(lambda: self.ctx.api.session_messages(session_id), done, lambda e: self.status.set(error_text(e), "error"))

    def new_chat(self) -> None:
        self.session_id = None
        self.messages = []
        self.suggestion_row.hide()
        self.session_list.clearSelection()
        self._render()
        self.input.setFocus()

    def delete_session(self) -> None:
        item = self.session_list.currentItem()
        if item is None:
            self.status.set("Silmek için soldan bir sohbet seç.", "warn")
            return
        if not confirm(self, "Seçili sohbet ve tüm mesajları silinsin mi?"):
            return
        session_id = item.data(Qt.ItemDataRole.UserRole)

        def done(_result: Any) -> None:
            if self.session_id == session_id:
                self.new_chat()
            self.refresh_sessions()
            self.status.set("Sohbet silindi.", "ok")

        run_background(lambda: self.ctx.api.delete_session(session_id, True), done, lambda e: self.status.set(error_text(e), "error"))

    # ---------- sending ----------
    def insert_text(self, text: str) -> None:
        self.input.setPlainText(text)
        self.input.moveCursor(QTextCursor.MoveOperation.End)
        self.input.setFocus()

    def send(self) -> None:
        text = self.input.toPlainText().strip()
        if not text or self.busy:
            return
        model = self.model_box.currentData()
        workflow = self.workflow_box.currentData() or "standard"
        self.input.clear()
        self.messages.append({"role": "user", "content": text, "meta": ""})
        self.last_question = text
        self.suggestion_row.hide()
        self._render(pending=True)
        self._set_busy(True)
        if model == OPENJARVIS:
            run_background(lambda: self._openjarvis_turn(text), self._answer, self._failed)
        else:
            session_id = self.session_id
            run_background(lambda: self.ctx.api.chat(text, model, workflow, session_id), self._answer, self._failed)

    def _openjarvis_turn(self, text: str) -> dict[str, Any]:
        api = self.ctx.api
        session_id = self.session_id or api.create_session(text[:80])["session_id"]
        history = api.action("sessions", "context", {"session_id": session_id}).get("messages", [])
        result = api.action("openjarvis", "chat", {"message": text, "messages": history})
        api.action("sessions", "append_turn", {
            "session_id": session_id, "title": text[:80], "user_message": text, "assistant_message": result["answer"],
        })
        return {"message": {"content": result["answer"]}, "model": f"OpenJarvis · {result.get('model', '')}",
                "session_id": session_id}

    def _answer(self, result: dict[str, Any]) -> None:
        self._set_busy(False)
        if result.get("status") == "auth_required":
            self.messages.pop()
            self._render()
            self._ask_key(result.get("auth") or {}, retry_text=self.last_question)
            return
        content = (result.get("message") or {}).get("content", "")
        meta = str(result.get("model") or "")
        route = result.get("intent_route") or {}
        if route.get("intent"):
            meta += f" · {route['intent']}"
        tools = [tool.get("name", "") for tool in result.get("tools_used") or [] if tool.get("status") == "completed"]
        if tools:
            meta += " · araç: " + ", ".join(tools)
        self.messages.append({"role": "assistant", "content": content, "meta": meta})
        self.last_answer = content
        new_session = result.get("session_id")
        if new_session and new_session != self.session_id:
            self.session_id = new_session
        self._render()
        self.refresh_sessions()
        suggestion = result.get("cloud_suggestion")
        if suggestion:
            self.suggested = [provider["id"] for provider in suggestion.get("providers", [])][:3]
            names = ", ".join(provider.get("name", provider["id"]) for provider in suggestion.get("providers", [])[:3])
            self.suggestion_label.setText(f"{suggestion.get('reason', '')}  ({names})")
            self.suggestion_row.show()
        self.status.set("Yanıt alındı.", "ok")

    def _failed(self, error: Exception) -> None:
        self._set_busy(False)
        if isinstance(error, ApiError) and error.status == 401 and isinstance(error.body, dict) and error.body.get("auth"):
            self.messages.pop()
            self._render()
            self._ask_key(error.body["auth"], retry_text=self.last_question)
            return
        self.messages.append({"role": "error", "content": error_text(error), "meta": ""})
        self._render()
        self.status.set(error_text(error), "error")

    def _ask_key(self, auth: dict[str, Any], retry_text: str) -> None:
        provider = auth.get("provider")
        name = auth.get("provider_name", provider)
        links = " · ".join(url for url in (auth.get("key_url"), auth.get("signup_url")) if url)
        key, ok = QInputDialog.getText(
            self, f"{name} oturumu",
            f"{auth.get('question', '')}\n\nAnahtar adresi: {links}\n\nAPI anahtarını yapıştır (yalnızca bu bilgisayarda saklanır):",
            QLineEdit.EchoMode.Password,
        )
        if not ok or not key.strip() or not provider:
            self.status.set(f"{name} için anahtar girilmedi; istek gönderilmedi.", "warn")
            return

        def saved(_result: Any) -> None:
            self.status.set(f"{name} anahtarı kaydedildi; soru tekrar gönderiliyor.", "ok")
            self.refresh_models()
            self.input.setPlainText(retry_text)
            self.send()

        self.ctx.call_action(self, "cloud_providers", "save_key", {"provider": provider, "api_key": key.strip()}, on_done=saved)

    def ask_other_ai(self) -> None:
        if not self.suggested or not self.last_question:
            return
        payload = {"providers": self.suggested, "task": "info", "message": self.last_question,
                   "previous_answer": self.last_answer[:40_000]}
        self._set_busy(True)
        self.suggestion_row.hide()

        def done(result: dict[str, Any]) -> None:
            self._set_busy(False)
            for item in result.get("results", []):
                if item.get("status") == "ok":
                    self.messages.append({"role": "assistant", "content": item["content"],
                                          "meta": f"{item.get('provider_name')} · {item.get('model')}"})
                elif item.get("status") == "auth_required":
                    self.messages.append({"role": "error", "content": item.get("question", "Oturum gerekli."), "meta": ""})
                else:
                    self.messages.append({"role": "error", "content": f"{item.get('provider_name')}: {item.get('error')}", "meta": ""})
            self._render()

        def failed(error: Exception) -> None:
            self._set_busy(False)
            self.status.set(error_text(error), "error")

        self.ctx.call_action(self, "cloud_providers", "consult", payload, on_done=done, on_error=failed)

    # ---------- rendering ----------
    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.send_button.setEnabled(not busy)
        self.send_button.setText("Düşünüyor…" if busy else "Gönder")
        if busy:
            self.status.set("Yanıt bekleniyor…", "busy")

    def _render(self, pending: bool = False) -> None:
        parts: list[str] = []
        for message in self.messages:
            if message["role"] == "user":
                header = "#### 🧑 Sen"
            elif message["role"] == "error":
                header = "#### ⚠️ Hata"
            else:
                header = "#### 🐼 DeepPanda" + (f"  \n<sub>{message['meta']}</sub>" if message.get("meta") else "")
            parts.append(f"{header}\n\n{message['content']}")
        if pending:
            parts.append("#### 🐼 DeepPanda\n\n_düşünüyor…_")
        if not parts:
            parts.append("### Merhaba!\n\nBir soru yaz ya da soldan eski bir sohbeti aç. "
                         "Model kutusundan yerel Qwen 2.5, OpenJarvis veya bulut modellerini seçebilirsin.")
        self.transcript.setMarkdown("\n\n---\n\n".join(parts))
        bar = self.transcript.verticalScrollBar()
        bar.setValue(bar.maximum())
