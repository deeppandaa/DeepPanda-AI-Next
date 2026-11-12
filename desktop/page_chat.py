from __future__ import annotations

import html
import json
import re
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from threading import Event
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import (
    QDragEnterEvent,
    QDropEvent,
    QKeySequence,
    QShortcut,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from desktop.api import ApiError
from desktop.chat_agent import ChatAgent, compact_result
from desktop.chat_context import (
    ChatCancelled,
    check_cancelled,
    validate_attachment_path,
)
from desktop.chat_continuity import ChatContinuity
from desktop.chat_mcp import ChatMcpRuntime
from desktop.cline import CLINE, ClineClient
from desktop.cline import login as cline_login
from desktop.config import PROJECT_ROOT
from desktop.context import AppContext, confirm, error_text
from desktop.page_mcp import McpPage
from desktop.page_tools import ToolsPage
from desktop.tasks import run_background
from desktop.widgets import StatusLabel

OPENJARVIS = "__openjarvis__"
EMBEDDING_HINTS = ("embed", "bge", "minilm", "nomic")


@dataclass
class Approval:
    title: str
    arguments: dict[str, Any]
    ready: Event = field(default_factory=Event)
    accepted: bool = False


class ChatEditor(QPlainTextEdit):
    files_dropped = Signal(object)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls() and all(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        if event.mimeData().hasUrls():
            if all(url.isLocalFile() for url in event.mimeData().urls()):
                self.files_dropped.emit([Path(url.toLocalFile()) for url in event.mimeData().urls()])
                event.acceptProposedAction()
            else:
                event.ignore()
            return
        super().dropEvent(event)


def _local_time(value: Any) -> str:
    text = str(value or "")
    try:
        return datetime.fromisoformat(text).astimezone().strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return text[:16]


class ChatPage(QWidget):
    turn_event = Signal(object)
    approval_requested = Signal(object)

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.session_id: str | None = None
        self.messages: list[dict[str, str]] = []
        self.last_question = ""
        self.last_answer = ""
        self.suggested: list[str] = []
        self.busy = False
        self.attachments: list[Path] = []
        self.continuity = ChatContinuity(PROJECT_ROOT / "data" / "chat-continuity")
        self.tool_summaries: list[dict[str, str]] = []
        self.omitted_summaries = 0
        self._continuity_error = ""
        self.mcp_runtime: ChatMcpRuntime | None = None
        self._mcp_api_url = ""
        self.tool_context: list[dict[str, Any]] = []
        self.model_profiles: dict[str, Any] = {}
        self.routing: dict[str, Any] = {}
        self.cline_workspace = Path(ctx.settings.cline_workspace)
        self._cline_model_refresh = False
        self.cancelled: Event | None = None
        self._generation = 0
        self._session_load_id = 0
        self._partial_answer = ""
        self._backup_id: str | None = None
        self._backup_path = ""
        self.turn_event.connect(self._on_turn_event)
        self.approval_requested.connect(self._show_approval)
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(50)
        self._render_timer.timeout.connect(lambda: self._render(pending=self.busy))
        self._mcp_timer = QTimer(self)
        self._mcp_timer.setInterval(1000)
        self._mcp_timer.timeout.connect(self._check_mcp_runtime)
        self._mcp_timer.start()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_sessions())
        splitter.addWidget(self._build_conversation())
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([240, 900])
        self.tool_panel = QTabWidget()
        self.tools_page = ToolsPage(ctx)
        self.mcp_page = McpPage(ctx)
        self.tools_page.result_ready.connect(self._capture_tool_result)
        self.mcp_page.result_ready.connect(self._capture_tool_result)
        self.tool_panel.addTab(self.tools_page, "Yerleşik araçlar")
        self.tool_panel.addTab(self.mcp_page, "MCP / Copilot")
        self.tool_panel.hide()
        self.tool_panel.currentChanged.connect(
            lambda index: self.mcp_page.activate() if index == 1 else None
        )
        splitter.addWidget(self.tool_panel)
        self.splitter = splitter
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self.send)
        QShortcut(QKeySequence("Ctrl+Enter"), self, activated=self.send)
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self.new_chat)
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self.choose_files)
        QShortcut(QKeySequence("Ctrl+Shift+O"), self, activated=self.choose_folder)
        QShortcut(QKeySequence("Escape"), self, activated=self.stop)

    # ---------- layout ----------
    def _build_sessions(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        title = QLabel("Sohbetler")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        self.new_button = QPushButton("+ Yeni sohbet")
        self.new_button.setObjectName("primary")
        self.new_button.clicked.connect(self.new_chat)
        layout.addWidget(self.new_button)
        self.session_search = QLineEdit()
        self.session_search.setPlaceholderText("Sohbetlerde ara…")
        self.session_search.textChanged.connect(self._filter_sessions)
        layout.addWidget(self.session_search)
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
        self.model_box.currentIndexChanged.connect(self._model_details)
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
        self.model_details = QLabel("Otomatik seçim, ölçülmüş konu önceliklerini kullanır.")
        self.model_details.setWordWrap(True)
        self.model_details.setObjectName("hint")
        layout.addWidget(self.model_details)
        self.cline_controls = QWidget()
        cline_layout = QVBoxLayout(self.cline_controls)
        cline_layout.setContentsMargins(0, 0, 0, 0)
        cline_row = QHBoxLayout()
        login = QPushButton("Cline hesabını bağla")
        login.clicked.connect(self._cline_login)
        folder = QPushButton("Cline klasörü seç")
        folder.clicked.connect(self._cline_folder)
        self.cline_path = QLabel(str(self.cline_workspace))
        self.cline_path.setWordWrap(True)
        cline_row.addWidget(login)
        cline_row.addWidget(folder)
        cline_row.addWidget(self.cline_path, 1)
        cline_layout.addLayout(cline_row)
        cline_options = QHBoxLayout()
        check = QPushButton("Cline bağlantısını doğrula")
        check.clicked.connect(self._cline_check)
        self.cline_model_box = QComboBox()
        self.cline_model_box.addItem("Hesapta seçili model (varsayılan)", None)
        if self.ctx.settings.cline_model:
            self.cline_model_box.addItem(
                self.ctx.settings.cline_model + " (katalog henüz doğrulanmadı)", self.ctx.settings.cline_model,
            )
            self.cline_model_box.setCurrentIndex(1)
        self.cline_model_box.currentIndexChanged.connect(self._cline_model_changed)
        cline_options.addWidget(check)
        test = QPushButton("Cline kısa yanıt testi")
        test.clicked.connect(self._cline_test_response)
        cline_options.addWidget(test)
        cline_options.addWidget(self.cline_model_box, 1)
        cline_layout.addLayout(cline_options)
        self.cline_connection = QLabel("Cline hesabı/oturumu henüz doğrulanmadı.")
        self.cline_connection.setWordWrap(True)
        cline_layout.addWidget(self.cline_connection)
        self.cline_controls.hide()
        layout.addWidget(self.cline_controls)
        controls = QHBoxLayout()
        self.agent_mode = QComboBox()
        self.agent_mode.addItem("Ajan · araçları otomatik seç", "agent")
        self.agent_mode.addItem("Sor · ekleri oku, araç çağırma", "ask")
        self.agent_mode.addItem("Planla · çalıştırmadan planla", "plan")
        controls.addWidget(self.agent_mode, 1)
        tools_button = QPushButton("Araçlar / MCP")
        tools_button.clicked.connect(self.toggle_tools)
        controls.addWidget(tools_button)
        copy_button = QPushButton("Kopyala")
        copy_button.clicked.connect(lambda: QApplication.clipboard().setText(self.last_answer))
        controls.addWidget(copy_button)
        self.retry_button = QPushButton("Düzenle / tekrar sor")
        self.retry_button.clicked.connect(self.edit_last_question)
        controls.addWidget(self.retry_button)
        export_button = QPushButton("Dışa aktar")
        export_button.clicked.connect(self.export_chat)
        controls.addWidget(export_button)
        layout.addLayout(controls)
        self.rollback_button = QPushButton("Son dosya değişikliğini geri al")
        self.rollback_button.clicked.connect(self.rollback_last_change)
        self.rollback_button.setEnabled(False)
        self.rollback_button.hide()
        layout.addWidget(self.rollback_button)

        self.transcript = QTextBrowser()
        self.transcript.setOpenExternalLinks(True)
        self.transcript.setObjectName("transcript")
        layout.addWidget(self.transcript, 1)
        self.trace = QTreeWidget()
        self.trace.setHeaderLabels(["İşlem adımları / araç çıktısı"])
        self.trace.setMaximumHeight(150)
        self.trace.hide()
        layout.addWidget(self.trace)
        self.summary_view = QTreeWidget()
        self.summary_view.setHeaderLabels(["Yerel araç özetleri · çıktı içermez / yeniden çalıştırılmaz"])
        self.summary_view.setMaximumHeight(120)
        self.summary_view.hide()
        layout.addWidget(self.summary_view)

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

        self.remember_paths = QCheckBox("Bu sohbetin ek yollarını bu bilgisayarda hatırla")
        self.remember_paths.setToolTip(
            "İsteğe bağlıdır. Yalnız dosya/klasör yolları saklanır; içerikler ve araç izleri saklanmaz. "
            "Yeniden açınca içerik okunmaz; sonraki Gönder işleminde güncel dosyalar kullanılır."
        )
        self.remember_paths.toggled.connect(self._remember_paths_changed)
        layout.addWidget(self.remember_paths)
        self.remember_tools = QCheckBox("Bu sohbetin araç adlarını ve durumlarını yerelde hatırla")
        self.remember_tools.setToolTip(
            "Ayrı onayla yalnız bu andan sonraki son 100 araç adı/durumu saklanır. "
            "Çıktı/argüman/komut kaydedilmez; modele bağlam veya çalıştırma izni verilmez."
        )
        self.remember_tools.toggled.connect(self._remember_tools_changed)
        layout.addWidget(self.remember_tools)
        self.keep_mcp = QCheckBox("MCP oturumlarını bu açık sohbette mesajlar arasında tut")
        self.keep_mcp.setToolTip(
            "Varsayılan kapalı; diske kaydedilmez. Her araç çağrısı yine onay ister. "
            "10 dakika boşta kalma/yeni sohbet/oturum değişimi/iptal/kapanış bağlantıları kapatır."
        )
        self.keep_mcp.toggled.connect(self._keep_mcp_changed)
        layout.addWidget(self.keep_mcp)
        self.mcp_live_status = QLabel("Canlı MCP sürekliliği kapalı.")
        self.mcp_live_status.setWordWrap(True)
        self.mcp_live_status.setObjectName("hint")
        layout.addWidget(self.mcp_live_status)
        attachment_row = QHBoxLayout()
        self.file_button = QPushButton("+ Dosya")
        self.file_button.clicked.connect(self.choose_files)
        self.folder_button = QPushButton("+ Klasör")
        self.folder_button.clicked.connect(self.choose_folder)
        self.remove_attachment_button = QPushButton("Seçili eki kaldır")
        self.remove_attachment_button.clicked.connect(self.remove_attachment)
        attachment_row.addWidget(self.file_button)
        attachment_row.addWidget(self.folder_button)
        attachment_row.addWidget(self.remove_attachment_button)
        self.context_label = QLabel("Ek yok · araç sonucu yok")
        self.context_label.setObjectName("hint")
        attachment_row.addWidget(self.context_label, 1)
        layout.addLayout(attachment_row)
        self.attachment_list = QListWidget()
        self.attachment_list.setMaximumHeight(75)
        self.attachment_list.hide()
        layout.addWidget(self.attachment_list)
        self.input = ChatEditor()
        self.input.files_dropped.connect(self.add_paths)
        self.input.setPlaceholderText("Mesajını yaz veya dosya/klasör sürükle…  Ctrl+Enter gönder · /help")
        self.input.setFixedHeight(110)
        layout.addWidget(self.input)
        bottom = QHBoxLayout()
        self.status = StatusLabel()
        bottom.addWidget(self.status, 1)
        self.send_button = QPushButton("Gönder")
        self.send_button.setObjectName("primary")
        self.send_button.clicked.connect(self.send)
        self.stop_button = QPushButton("Durdur")
        self.stop_button.clicked.connect(self.stop)
        self.stop_button.setEnabled(False)
        bottom.addWidget(self.stop_button)
        bottom.addWidget(self.send_button)
        layout.addLayout(bottom)
        return panel

    def choose_files(self) -> None:
        if not self.busy:
            paths, _selected = QFileDialog.getOpenFileNames(self, "Sohbete dosya ekle")
            self.add_paths([Path(path) for path in paths])

    def choose_folder(self) -> None:
        if not self.busy:
            path = QFileDialog.getExistingDirectory(self, "Sohbete klasör ekle")
            if path:
                self.add_paths([Path(path)])

    def add_paths(self, paths: list[Path]) -> None:
        if self.busy:
            self.status.set("Ekleri değiştirmeden önce isteği durdurun.", "warn")
            return
        try:
            validated = [validate_attachment_path(path) for path in paths]
            merged = list(dict.fromkeys([*self.attachments, *validated]))
            if len(merged) > 32:
                raise ValueError("En fazla 32 dosya/klasör seçilebilir.")
        except (ValueError, OSError) as exc:
            self.status.set(str(exc), "error")
            return
        self.attachments = merged
        self._update_context()
        self.status.set("Ekler yalnız Gönder'e basınca okunur; klasör sınırları işlem günlüğünde gösterilir.", "info")
        self._save_paths()

    def remove_attachment(self) -> None:
        if self.busy:
            return
        index = self.attachment_list.currentRow()
        if index >= 0:
            self.attachments.pop(index)
            self._update_context()
            self._save_paths()

    def _set_remember_paths(self, checked: bool) -> None:
        self.remember_paths.blockSignals(True)
        self.remember_paths.setChecked(checked)
        self.remember_paths.blockSignals(False)

    def _remember_paths_changed(self, checked: bool) -> None:
        if checked and not confirm(
            self, "Bu sohbetin ek dosya/klasör yolları yerel olarak hatırlansın mı?",
            details="Yollar hassas klasör adları içerebilir. İçerik, araç sonucu veya MCP oturumu saklanmaz. "
            "Sohbet yeniden açılınca yollar tekrar doğrulanır; Gönder güncel içerikleri okur. "
            "İşareti kaldırmak bu sohbetin yerel yol kaydını siler.",
        ):
            self._set_remember_paths(False)
            return
        self._save_paths()

    def _save_paths(self) -> None:
        if not self.session_id:
            return
        try:
            if self.remember_paths.isChecked():
                self.continuity.save(self.ctx.settings.api_url, self.session_id, self.attachments)
            else:
                self.continuity.forget(self.ctx.settings.api_url, self.session_id)
        except (OSError, ValueError) as exc:
            self.status.set("Ek yolları kaydedilemedi/silinemedi: " + str(exc), "error")

    def _set_remember_tools(self, checked: bool) -> None:
        self.remember_tools.blockSignals(True)
        self.remember_tools.setChecked(checked)
        self.remember_tools.blockSignals(False)

    def _set_keep_mcp(self, checked: bool) -> None:
        self.keep_mcp.blockSignals(True)
        self.keep_mcp.setChecked(checked)
        self.keep_mcp.blockSignals(False)

    def _keep_mcp_changed(self, checked: bool) -> None:
        if not checked:
            self.release_mcp()
            return
        if self.mcp_runtime is not None:
            self.status.set("Mevcut canlı MCP bağlantılarını kapatmadan yeni oturum açılamaz.", "warn")
            return
        if not confirm(
            self, "MCP bağlantıları bu açık sohbette mesajlar arasında açık tutulsun mu?",
            details="Sunucu/tarayıcı durumu ve başlatılmış süreçler bellekte yaşayabilir; "
            "bu bir araç çağrısı izni değildir. Her çağrı yine ayrı onay ister. "
            "En fazla dört sunucu, son ajan araç turundan sonra 10 dakika boşta kalma sınırı. "
            "İşareti kaldırma, yeni sohbet, sohbet açma/silme, iptal ve pencere kapanışı bağlantıları kapatır. "
            "Kimlik bilgisi değiştirirken önce kapatın; açık bağlantı önceki yetkilendirmeyi kullanabilir. "
            "Sunucuda başlatılmış uzak işlemler veya harici tarayıcı yan etkileri geri alınmaz. "
            "Diskten/önceki uygulama açılışından geri yüklenmez; Cline ve manuel MCP panelini kapsamaz.",
        ):
            self._set_keep_mcp(False)
            return
        self.mcp_runtime = ChatMcpRuntime()
        self._mcp_api_url = self.ctx.settings.api_url
        self.mcp_live_status.setText("Canlı MCP açık · yalnız bu sohbet · her çağrı ayrı onay · 10 dk boşta sınırı.")

    def release_mcp(self, after: Callable[[], object] | None = None) -> None:
        runtime = self.mcp_runtime
        if runtime is None:
            self._set_keep_mcp(False)
            if after is not None:
                after()
            return
        self.cancelled = None
        self._set_busy(True)
        self.mcp_live_status.setText("Canlı MCP bağlantıları kapatılıyor…")

        def done(_result: Any) -> None:
            self.mcp_runtime = None
            self._mcp_api_url = ""
            self._set_keep_mcp(False)
            self._set_busy(False)
            self.mcp_live_status.setText("Canlı MCP bağlantıları kapatıldı; uzak yan etkiler geri alınmadı.")
            if after is not None:
                after()
            else:
                self.status.set("Canlı MCP bağlantıları kapatıldı.", "info")

        def failed(error: Exception) -> None:
            if runtime.closed.is_set():
                self.mcp_runtime = None
                self._mcp_api_url = ""
                self._set_keep_mcp(False)
            else:
                self._set_keep_mcp(True)
            self._set_busy(False)
            self.mcp_live_status.setText("Canlı MCP kapanışı başarısız; bağlantı/süreç durumunu inceleyin.")
            self.status.set(error_text(error), "error")

        run_background(runtime.close, done, failed)

    def _check_mcp_runtime(self) -> None:
        runtime = self.mcp_runtime
        if runtime is not None and runtime.closed.is_set() and not self.busy:
            self.release_mcp()
            self.mcp_live_status.setText("Canlı MCP süresi doldu veya bağlantı kapandı; yeniden onay gerekir.")

    def _remember_tools_changed(self, checked: bool) -> None:
        if checked and not confirm(
            self, "Bu andan sonraki araç adları ve durumları bu sohbet için yerelde saklansın mı?",
            details="Araç adları özel sunucu/işlem adları içerebilir. Yalnız son 100 ad/durum tutulur; "
            "eski özetlerin çıkarıldığı sayıyla belirtilir. Çıktı, argüman, komut ve kimlik bilgisi "
            "işlemleri kaydedilmez. Modele gönderilmez ve yeniden çalıştırılmaz. "
            "İşareti kaldırmak bu sohbetin yerel araç özetlerini siler.",
        ):
            self._set_remember_tools(False)
            return
        self.tool_summaries.clear()
        self.omitted_summaries = 0
        self._render_summaries()
        self._save_summaries()

    def _save_summaries(self) -> None:
        if not self.session_id:
            return
        try:
            if self.remember_tools.isChecked():
                self.continuity.save_summaries(
                    self.ctx.settings.api_url, self.session_id, self.tool_summaries, self.omitted_summaries,
                )
            else:
                self.continuity.forget_summaries(self.ctx.settings.api_url, self.session_id)
        except (OSError, ValueError) as exc:
            self._continuity_error = "Araç özetleri kaydedilemedi/silinemedi: " + str(exc)
            self.status.set(self._continuity_error, "error")
        else:
            self._continuity_error = ""

    def _render_summaries(self) -> None:
        self.summary_view.clear()
        if self.omitted_summaries:
            self.summary_view.addTopLevelItem(QTreeWidgetItem([f"{self.omitted_summaries} eski özet sınır nedeniyle çıkarıldı."]))
        for item in self.tool_summaries:
            self.summary_view.addTopLevelItem(QTreeWidgetItem([f"{item['name']} · {item['status']}"]))
        self.summary_view.setVisible(bool(self.tool_summaries or self.omitted_summaries))

    def _record_tool_summary(self, name: str, status: str) -> None:
        if not self.remember_tools.isChecked() or status not in {"completed", "failed", "cancelled"}:
            return
        if re.search(r"(?:^|[^a-z0-9_])(?:save_key|delete_key|remove_key|login|auth)(?:$|[^a-z0-9_])", name.casefold()):
            return
        if not 1 <= len(name) <= 200 or any(ord(char) < 32 for char in name):
            self._continuity_error = "Araç adı yerel özet biçimine uymadı; saklanmadı."
            self.status.set(self._continuity_error, "warn")
            return
        self.tool_summaries.append({"name": name, "status": status})
        if len(self.tool_summaries) > 100:
            self.tool_summaries.pop(0)
            self.omitted_summaries += 1
        self._render_summaries()
        self._save_summaries()

    def _update_context(self) -> None:
        self.attachment_list.clear()
        for path in self.attachments:
            item = QListWidgetItem(path.name)
            item.setToolTip(str(path))
            self.attachment_list.addItem(item)
        self.attachment_list.setVisible(bool(self.attachments))
        self.context_label.setText(f"{len(self.attachments)} ek · {len(self.tool_context)} araç sonucu")

    def toggle_tools(self) -> None:
        visible = not self.tool_panel.isVisible()
        self.tool_panel.setVisible(visible)
        self.splitter.setSizes([200, 720, 600 if visible else 0])

    def _capture_tool_result(self, plugin: str, action: str, result: Any) -> None:
        if action in {"save_key", "delete_key"}:
            self.status.set("Kimlik bilgisi işleminin sonucu model bağlamına eklenmedi.", "info")
            return
        name = f"{plugin}.{action}"
        failed = isinstance(result, dict) and (
            result.get("is_error") or (plugin == "windows_host" and result.get("status") == "failed")
        )
        status = "failed" if failed else "completed"
        item = {"name": name, "status": status, "result": compact_result(result)}
        if len(self.tool_context) >= 5:
            self.status.set("Beş araç sonucu sınırı dolu; yeni sohbet açın. Son çıktı araç panelinde kaldı.", "warn")
            return
        self.tool_context.append(item)
        self._remember_backup(name, result)
        self._show_tool_result(item)
        self._update_context()
        if not self._continuity_error:
            self.status.set(
                "Araç başarısız; gerçek çıktı sonraki mesajın bağlamına eklendi." if failed
                else "Gerçek araç çıktısı sonraki mesajın bağlamına eklendi.",
                "error" if failed else "info",
            )

    def _show_tool_result(self, item: dict[str, Any]) -> None:
        name, status = str(item["name"]), str(item["status"])
        self.messages.append({
            "role": "tool", "content": f"**{html.escape(name)}** · {status}\n\n"
            f"<pre>{html.escape(json.dumps(item['result'], ensure_ascii=False, indent=2))}</pre>", "meta": "",
        })
        self._render(pending=self.busy)
        self._record_tool_summary(name, status)

    def _filter_sessions(self, text: str) -> None:
        for index in range(self.session_list.count()):
            item = self.session_list.item(index)
            item.setHidden(text.casefold() not in item.text().casefold())

    def _model_details(self) -> None:
        name = self.model_box.currentData()
        self.cline_controls.setVisible(name == CLINE)
        profile = self.model_profiles.get(name)
        if profile:
            description = str(profile.get("description", "Ölçüm açıklaması yok."))
            cold = profile.get("max_observed_load_seconds")
            suffix = f" · Ölçülen en uzun yükleme: {cold:g} sn" if isinstance(cold, (float, int)) else ""
            self.model_details.setText(f"{profile.get('status', 'untested')} · {description}{suffix}")
        elif name == OPENJARVIS:
            self.model_details.setText("OpenJarvis: sunucuda sohbet. Bu panelde yalnız Sor modu; ek/araç akışı desteklenmiyor.")
        elif name == CLINE:
            self.model_details.setText(
                "Cline hesabı / ACP: model Cline girişinde seçilir. Bulut/kullanım ücreti olabilir; "
                "İzin istekleri tek çağrılıktır; bazı okumalar ayrıca sorulmayabilir. "
                "Sor/Plan düzenleme ve komut izinlerini reddeder. "
                "Klasör/model tercihi yerelde saklanır; Cline sandbox değildir."
            )
        elif name is None:
            areas = self.routing.get("available_priorities", {})
            labels = {"answer": "Yanıt", "intent": "Yönlendirme", "planning": "Plan",
                      "source_grounded": "Kaynak", "learning": "Öğrenme", "code_change": "Kod"}
            leaders = [f"{labels.get(area, area)}: {models[0]}" for area, models in areas.items() if models]
            self.model_details.setText(" · ".join(leaders) or "Otomatik: konu öncelikleri henüz yüklenmedi.")
        else:
            self.model_details.setText("Açık model seçimi otomatik öncelikleri geçersiz kılar; ölçüm bilgisi yoksa üstünlük varsayılmaz.")

    def edit_last_question(self) -> None:
        if self.last_question and not self.busy:
            self.insert_text(self.last_question)
            self.status.set("Düzenleyip Gönder'e basın. Önceki konuşma değiştirilmez; yeni bir tur eklenir.", "info")

    def export_chat(self) -> None:
        if not self.messages:
            self.status.set("Dışa aktarılacak mesaj yok.", "warn")
            return
        filename, _selected = QFileDialog.getSaveFileName(
            self, "Sohbeti dışa aktar", "deeppanda-sohbet.md", "Markdown (*.md)",
        )
        if not filename:
            return
        text = "\n\n---\n\n".join(f"## {message['role']}\n\n{message['content']}" for message in self.messages)
        try:
            Path(filename).write_text(text, encoding="utf-8")
        except OSError as exc:
            self.status.set(f"Sohbet kaydedilemedi: {exc}", "error")
        else:
            self.status.set(f"Sohbet kaydedildi: {filename}", "ok")

    def _remember_backup(self, name: str, result: Any) -> None:
        if name.endswith("workspace.write") and isinstance(result, dict) and isinstance(result.get("backup_id"), str):
            self._backup_id = result["backup_id"]
            self._backup_path = str(result.get("path", ""))
            self.rollback_button.show()
            self.rollback_button.setEnabled(not self.busy)

    def rollback_last_change(self) -> None:
        if not self._backup_id or self.busy:
            return
        self._set_busy(True)

        def done(result: Any) -> None:
            self._backup_id = None
            self._set_busy(False)
            self._capture_tool_result("workspace", "rollback", result)

        def failed(error: Exception) -> None:
            self._set_busy(False)
            self.status.set(error_text(error), "error")

        if not self.ctx.call_action(
            self, "workspace", "rollback", {"backup_id": self._backup_id},
            approval=f"{self._backup_path} dosyasının son onaylı değişikliği yedekten geri alınsın mı?",
            on_done=done, on_error=failed,
        ):
            self._set_busy(False)

    def _command(self, text: str) -> bool:
        command, _separator, rest = text.partition(" ")
        if command in {"/ask", "/plan", "/agent"}:
            self.agent_mode.setCurrentIndex(self.agent_mode.findData(command[1:]))
            self.input.setPlainText(rest)
            if rest.strip():
                self.send()
            return True
        if text == "/tools":
            self.toggle_tools()
            self.input.clear()
            return True
        if text == "/clear":
            self.new_chat()
            self.input.clear()
            return True
        if text == "/help":
            self.status.set(
                "/ask soru · /plan istek · /agent istek · /tools · /clear. "
                "Ctrl+O dosya, Ctrl+Shift+O klasör, Ctrl+Enter gönder, Esc durdur. "
                "Ajan en fazla üç araç adımı uygular; riskli işlemler açık onay ister.", "info",
            )
            return True
        return False

    def stop(self) -> None:
        if self.busy and self.cancelled is not None:
            self.cancelled.set()
            self.stop_button.setEnabled(False)
            self.status.set(
                "İptal istendi. Model akışı kapatılıyor; yerel Python çalıştırma/test/ortam süreç ağacı sonlandırılıyor. "
                "Diğer eşzamanlı araçlar güvenli dönüşünde durur. Önceki değişiklikler geri alınmaz.", "warn",
            )

    def _request_approval(
        self, generation: int, cancelled: Event, title: str, arguments: dict[str, Any],
    ) -> bool:
        check_cancelled(cancelled)
        request = Approval(title, arguments)
        self.approval_requested.emit((generation, request))
        while not request.ready.wait(0.1):
            check_cancelled(cancelled)
        check_cancelled(cancelled)
        return request.accepted

    def _show_approval(self, value: tuple[int, Approval]) -> None:
        generation, request = value
        if generation != self._generation or self.cancelled is None or self.cancelled.is_set():
            request.ready.set()
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Araç çağrısını onayla")
        dialog.resize(640, 450)
        layout = QVBoxLayout(dialog)
        label = QLabel(request.title)
        label.setWordWrap(True)
        layout.addWidget(label)
        preview = QPlainTextEdit(json.dumps(request.arguments, ensure_ascii=False, indent=2))
        preview.setReadOnly(True)
        layout.addWidget(preview, 1)
        buttons = QDialogButtonBox()
        buttons.addButton("Onayla ve çalıştır", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton("Vazgeç", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        timer = QTimer(dialog)
        timer.setInterval(100)
        timer.timeout.connect(lambda: dialog.reject() if self.cancelled and self.cancelled.is_set() else None)
        timer.start()
        request.accepted = dialog.exec() == QDialog.DialogCode.Accepted
        request.ready.set()
        dialog.deleteLater()

    def _on_turn_event(self, value: tuple[int, dict[str, Any]]) -> None:
        generation, event = value
        if generation != self._generation or not self.busy:
            return
        if event["type"] == "token":
            content = event.get("content")
            if isinstance(content, str):
                self._partial_answer += content
                if not self._render_timer.isActive():
                    self._render_timer.start()
        elif event["type"] == "progress":
            message = str(event.get("message", "İşlem sürüyor"))
            self.status.set(message, "busy")
            item = QTreeWidgetItem([message])
            details = {key: value for key, value in event.items() if key not in {"type", "message"}}
            if details:
                QTreeWidgetItem(item, [json.dumps(details, ensure_ascii=False, indent=2)])
            result = event.get("result")
            if isinstance(result, dict) and result.get("status") == "completed":
                self._remember_backup(str(result.get("name", "")), result.get("result"))
            if (
                isinstance(result, dict) and isinstance(result.get("name"), str)
                and result.get("status") in {"completed", "failed"} and "result" in result
            ):
                self._show_tool_result(result)
            self.trace.addTopLevelItem(item)
            while self.trace.topLevelItemCount() > 100:
                self.trace.takeTopLevelItem(0)
            self.trace.show()
            self.trace.scrollToItem(item)
            if self._continuity_error:
                self.status.set(self._continuity_error, "error")

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
            out: dict[str, Any] = {"ollama": [], "default": None, "cloud": [], "errors": [], "profiles": {}, "routing": {}}
            try:
                data = self.ctx.api.models()
                out["default"] = data.get("default_model")
                out["routing"] = data.get("routing") or {}
                for model in data.get("models", []):
                    name = model.get("name") or model.get("model")
                    if name and not any(hint in name.lower() for hint in EMBEDDING_HINTS):
                        details = model.get("details") or {}
                        out["ollama"].append((name, details.get("parameter_size", "")))
                        out["profiles"][name] = model.get("evaluation") or {}
            except ApiError as exc:
                out["errors"].append(f"Ollama: {exc.detail}")
            try:
                out["cloud"] = self.ctx.api.action("cloud_providers", "catalog", {}).get("providers", [])
            except ApiError as exc:
                out["errors"].append(f"Bulut kataloğu: {exc.detail}")
                out["cloud"] = []
            return out

        def done(data: dict[str, Any]) -> None:
            self.model_profiles = data["profiles"]
            self.routing = data["routing"]
            for name, size in data["ollama"]:
                label = f"Yerel: {name}" + (f"  ({size})" if size else "")
                if name == data["default"]:
                    label += "  ★"
                self.model_box.addItem(label, name)
                profile = self.model_profiles.get(name)
                if profile:
                    self.model_box.setItemData(
                        self.model_box.count() - 1, json.dumps(profile, ensure_ascii=False, indent=2),
                        Qt.ItemDataRole.ToolTipRole,
                    )
            self.model_box.addItem("OpenJarvis (yerel ajan)", OPENJARVIS)
            self.model_box.addItem("Cline (hesabım / ACP)", CLINE)
            self.model_box.addItem("FreeLLMAPI (otomatik)", "freellmapi:auto")
            for provider in data["cloud"]:
                state = "" if provider.get("configured") else "  (oturum yok)"
                self.model_box.addItem(f"Bulut: {provider.get('name', provider['id'])}{state}", f"cloud:{provider['id']}")
            index = self.model_box.findData(current)
            self.model_box.setCurrentIndex(max(index, 0))
            self._model_details()
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

        run_background(
            lambda: self.ctx.api.action("workflows", "catalog", {}), done,
            lambda error: self.status.set(f"Çalışma modları: {error_text(error)}", "warn"),
        )

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
            self._filter_sessions(self.session_search.text())

        run_background(lambda: self.ctx.api.sessions(100), done, lambda error: self.status.set(error_text(error), "error"))

    def _open_session(self, item: QListWidgetItem) -> None:
        if self.busy:
            return
        if self.mcp_runtime is not None:
            selected = item.clone()
            self.release_mcp(lambda: self._open_session(selected))
            return
        session_id = item.data(Qt.ItemDataRole.UserRole)
        self._session_load_id += 1
        load_id = self._session_load_id

        def done(result: dict[str, Any]) -> None:
            if load_id != self._session_load_id or self.busy:
                return
            self.session_id = session_id
            self.messages = [
                {"role": message["role"], "content": message["content"], "meta": ""}
                for message in result.get("messages", [])
            ]
            self.suggestion_row.hide()
            self.attachments.clear()
            self.tool_context.clear()
            self.trace.clear()
            self.trace.hide()
            self._backup_id, self._backup_path = None, ""
            self.rollback_button.hide()
            self.last_question = next((m["content"] for m in reversed(self.messages) if m["role"] == "user"), "")
            self.last_answer = next((m["content"] for m in reversed(self.messages) if m["role"] == "assistant"), "")
            self._set_remember_paths(False)
            warning = ""
            try:
                remembered, paths, warnings = self.continuity.load(self.ctx.settings.api_url, session_id)
                self._set_remember_paths(remembered)
                self.attachments = paths
                if remembered:
                    warning = " Ek yolları geri yüklendi; içerikler Gönder'e basılana kadar okunmaz."
                if warnings:
                    warning += "\n" + "\n".join(warnings)
            except (OSError, ValueError) as exc:
                warning = " Yerel ek yolları yüklenemedi: " + str(exc)
            self._set_remember_tools(False)
            self.tool_summaries.clear()
            self.omitted_summaries = 0
            self._continuity_error = ""
            try:
                enabled, summaries, omitted = self.continuity.load_summaries(self.ctx.settings.api_url, session_id)
                self._set_remember_tools(enabled)
                self.tool_summaries, self.omitted_summaries = summaries, omitted
                if summaries:
                    warning += " Yerel araç özetleri yüklendi; yeniden çalıştırılmadı ve model bağlamına eklenmedi."
            except (OSError, ValueError) as exc:
                warning += " Yerel araç özetleri yüklenemedi: " + str(exc)
            self._render_summaries()
            self._update_context()
            self._render()
            self.status.set("Sohbet yüklendi." + warning, "warn" if warning else "ok")

        run_background(lambda: self.ctx.api.session_messages(session_id), done, lambda e: self.status.set(error_text(e), "error"))

    def new_chat(self) -> None:
        if self.busy:
            self.status.set("Önce çalışan isteği durdurun.", "warn")
            return
        if self.mcp_runtime is not None:
            self.release_mcp(self.new_chat)
            return
        self._session_load_id += 1
        self.session_id = None
        self._set_remember_paths(False)
        self._set_remember_tools(False)
        self.tool_summaries.clear()
        self.omitted_summaries = 0
        self._continuity_error = ""
        self._render_summaries()
        self.messages = []
        self.last_question = ""
        self.last_answer = ""
        self.attachments.clear()
        self.tool_context.clear()
        self._backup_id, self._backup_path = None, ""
        self.rollback_button.hide()
        self.trace.clear()
        self.trace.hide()
        self._update_context()
        self.suggestion_row.hide()
        self.session_list.clearSelection()
        self._render()
        self.input.setFocus()

    def delete_session(self) -> None:
        if self.busy:
            self.status.set("Çalışan sohbet bitmeden oturum silinemez.", "warn")
            return
        item = self.session_list.currentItem()
        if item is None:
            self.status.set("Silmek için soldan bir sohbet seç.", "warn")
            return
        if not confirm(self, "Seçili sohbet ve tüm mesajları silinsin mi?"):
            return
        session_id = item.data(Qt.ItemDataRole.UserRole)

        def done(_result: Any) -> None:
            warning = ""
            try:
                self.continuity.forget(self.ctx.settings.api_url, session_id)
            except OSError as exc:
                warning = "Sohbet silindi fakat yerel ek yolu kaydı silinemedi: " + str(exc)
            try:
                self.continuity.forget_summaries(self.ctx.settings.api_url, session_id)
            except OSError as exc:
                warning += " Yerel araç özeti silinemedi: " + str(exc)
            if self.session_id == session_id:
                self.new_chat()
            self.refresh_sessions()
            self.status.set(warning or "Sohbet silindi.", "error" if warning else "ok")

        run_background(lambda: self.ctx.api.delete_session(session_id, True), done, lambda e: self.status.set(error_text(e), "error"))

    # ---------- sending ----------
    def _cline_folder(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Cline çalışma klasörü", str(self.cline_workspace))
        if not directory:
            return
        try:
            validate_attachment_path(Path(directory))
        except ValueError as exc:
            self.status.set(str(exc), "error")
            return
        self.cline_workspace = Path(directory)
        self.cline_path.setText(directory)
        self.ctx.settings.cline_workspace = directory
        self.ctx.settings.save()
        self.cline_connection.setText("Çalışma klasörü değişti; Cline bağlantısını yeniden doğrulayın.")

    def _cline_model_changed(self) -> None:
        if self._cline_model_refresh:
            return
        self.ctx.settings.cline_model = self.cline_model_box.currentData() or ""
        self.ctx.settings.save()
        self.cline_connection.setText("Model tercihi kaydedildi; sonraki turda yeni katalogla doğrulanacak.")

    def _cline_check(self) -> None:
        if self.busy or not confirm(
            self, "Cline ACP bağlantısı ve yeni oturum/model kataloğu kontrol edilsin mi?\n"
            "Modele mesaj/geçmiş gönderilmez ve dosya/komut izinleri verilmez. "
            "Cline kendi sağlayıcı/katalog bağlantısını kurabilir; bu gerçek model yanıtı doğrulaması değildir.",
            details=str(self.cline_workspace),
        ):
            return
        self.cancelled = Event()
        self._set_busy(True)
        client = ClineClient(self.cancelled, lambda _event: None, lambda *_args: False, timeout=45)

        def done(result: dict[str, Any]) -> None:
            self.cancelled = None
            self._set_busy(False)
            if not result.get("session_ready"):
                message = "ACP çalışıyor; Cline oturumu hazır değil. " + result.get("error", "")
                self.cline_connection.setText(message)
                self.status.set(message, "warn")
                return
            selected = self.ctx.settings.cline_model
            self._cline_model_refresh = True
            try:
                self.cline_model_box.clear()
                self.cline_model_box.addItem("Hesapta seçili model (varsayılan)", None)
                for item in result["models"]:
                    self.cline_model_box.addItem(item["name"], item["id"])
                index = self.cline_model_box.findData(selected) if selected else 0
                if index < 0:
                    self.cline_model_box.addItem(selected + " (bu katalogda yok)", selected)
                    index = self.cline_model_box.count() - 1
                self.cline_model_box.setCurrentIndex(index)
            finally:
                self._cline_model_refresh = False
            message = (
                f"Cline oturumu hazır; {len(result['models'])} model. "
                f"Hesapta seçili: {result.get('current_model') or 'bildirilmedi'}. "
                "Henüz gerçek model yanıtı doğrulanmadı."
            )
            if selected and selected not in {item["id"] for item in result["models"]}:
                message += " Kaydedilmiş model bu katalogda yok; yeni model seçin."
            self.cline_connection.setText(message)
            self.status.set(message, "info")

        def failed(error: Exception) -> None:
            self.cancelled = None
            self._set_busy(False)
            self.cline_connection.setText("Cline doğrulaması tamamlanamadı: " + error_text(error))
            self.status.set(error_text(error), "warn" if isinstance(error, ChatCancelled) else "error")

        workspace = self.cline_workspace
        run_background(lambda: client.run(workspace, check_session=True), done, failed)

    def _cline_test_response(self) -> None:
        if self.busy or not confirm(
            self, "Seçili Cline modeline yalnız CLINE_CONNECTION_OK yanıtını isteyen sabit test mesajı gönderilsin mi?\n"
            "Boş geçici klasör kullanılır; sohbet geçmişi/ekler gönderilmez ve bütün araç izinleri reddedilir. "
            "Sağlayıcı ücretlendirebilir. Bu test ödeme yapmaz veya bakiye yüklemez.",
            details="Model: " + (self.cline_model_box.currentData() or "Cline hesabında seçili model"),
        ):
            return
        self.cancelled = Event()
        self._set_busy(True)
        model = self.cline_model_box.currentData()
        client = ClineClient(self.cancelled, lambda _event: None, lambda *_args: False, timeout=90)

        def work() -> dict[str, Any]:
            projects = PROJECT_ROOT / "projects"
            projects.mkdir(exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="cline-check-", dir=projects) as directory:
                return client.run(
                    Path(directory), "Reply exactly CLINE_CONNECTION_OK. Do not read files or use tools.",
                    "ask", model=model,
                )

        def done(result: dict[str, Any]) -> None:
            self.cancelled = None
            self._set_busy(False)
            verified = result.get("model_response_verified") is True
            expected = result.get("answer", "").strip() == "CLINE_CONNECTION_OK"
            no_tools = not result.get("tools_used")
            if not verified:
                message = "Cline kısa yanıt testi doğrulanamadı; tamamlanmış model yanıtı yok."
            elif not expected:
                message = "Cline model yanıtı alındı fakat beklenen sabit test çıktısı eşleşmedi; test geçmedi."
            elif not no_tools:
                message = "Cline model yanıtı alındı fakat araç çağrısı bildirildi; araçsız kısa yanıt testi geçmedi."
            else:
                message = "Cline gerçek kısa yanıt testi GEÇTİ. Model: " + (result.get("model") or "hesapta seçili model")
            self.cline_connection.setText(message)
            self.status.set(message, "ok" if verified and expected and no_tools else "warn")

        def failed(error: Exception) -> None:
            self.cancelled = None
            self._set_busy(False)
            message = "Cline gerçek yanıt testi tamamlanamadı: " + error_text(error)
            self.cline_connection.setText(message)
            self.status.set(message, "warn" if isinstance(error, ChatCancelled) else "error")

        run_background(work, done, failed)

    def _cline_login(self) -> None:
        if confirm(self, "Cline'ın resmî hesap giriş terminali açılsın mı?\n"
                         "Hesabını bu pencerede/tarayıcıda bağla ve model seç. Şifre veya anahtarı sohbete yazma. "
                         "Proje içindeki ayrı Cline profili kullanılır; VS Code kimlik bilgileri kopyalanmaz."):
            self.cline_connection.setText("Giriş tamamlandıktan sonra Cline bağlantısını doğrula düğmesine basın.")
            run_background(cline_login, lambda result: self.status.set(result["message"], "info"),
                           lambda error: self.status.set(error_text(error), "error"))

    def insert_text(self, text: str) -> None:
        self.input.setPlainText(text)
        self.input.moveCursor(QTextCursor.MoveOperation.End)
        self.input.setFocus()

    def send(self) -> None:
        text = self.input.toPlainText().strip()
        if not text or self.busy:
            return
        if self._command(text):
            return
        if self.mcp_runtime is not None and self._mcp_api_url != self.ctx.settings.api_url:
            self.release_mcp()
            self.status.set("API adresi değişti; canlı MCP kapatılıyor. Mesaj gönderilmedi.", "warn")
            return
        model = self.model_box.currentData()
        workflow = self.workflow_box.currentData() or "standard"
        if model == OPENJARVIS and (self.attachments or self.tool_context or self.agent_mode.currentData() != "ask"):
            self.status.set("OpenJarvis için eksiz Sor modunu veya araç akışı için yerel bir model seçin.", "warn")
            return
        has_context = bool(self.attachments or self.tool_context)
        if model == CLINE and has_context:
            self.status.set("Cline için ek/araç bağlamını kaldırıp Cline çalışma klasörünü seçin.", "warn")
            return
        if model == CLINE and (not self.cline_workspace.is_dir() or len(text) > 20000):
            self.status.set("Cline için mevcut bir klasör ve en fazla 20.000 karakterlik mesaj gerekir.", "warn")
            return
        if model == CLINE:
            try:
                validate_attachment_path(self.cline_workspace)
            except ValueError as exc:
                self.status.set(str(exc), "error")
                return
        if model == CLINE and not confirm(
            self, "Mesajın ve bu sohbetin son mesajları Cline hesabındaki model sağlayıcısına gönderilecek. "
            "Cline seçilen klasörde dosya okuyabilir; okudukları sağlayıcıya aktarılabilir. Kullanım ücretli olabilir. "
            "Bu bir sandbox değildir; dosya/komut izinleri ayrıca sorulur. Devam edilsin mi?",
            details=str(self.cline_workspace),
        ):
            self.status.set("Cline veri aktarımı onaylanmadı; istek gönderilmedi.", "warn")
            return
        cloud_approved = False
        if model and str(model).startswith(("cloud:", "freellmapi:")) and (has_context or self.agent_mode.currentData() == "agent"):
            cloud_approved = confirm(
                self, "Seçilen dosya içerikleri ve araç sonuçları bu bulut sağlayıcısına gönderilebilir. Devam edilsin mi?",
            )
            if not cloud_approved:
                self.status.set("Buluta bağlam aktarımı onaylanmadı.", "warn")
                return
        self._generation += 1
        generation = self._generation
        self._partial_answer = ""
        self.trace.clear()
        self.trace.hide()
        self.cancelled = Event()
        cancelled = self.cancelled
        self.input.clear()
        self.messages.append({"role": "user", "content": text, "meta": ""})
        self.last_question = text
        self.suggestion_row.hide()
        self._render(pending=True)
        self._set_busy(True)
        if model == OPENJARVIS:
            run_background(lambda: self._openjarvis_turn(text), self._answer, self._failed)
        elif model == CLINE:
            workspace, mode = self.cline_workspace, self.agent_mode.currentData()
            cline_model = self.cline_model_box.currentData()
            client = ClineClient(
                cancelled, lambda event: self.turn_event.emit((generation, event)),
                lambda title, arguments: self._request_approval(generation, cancelled, title, arguments),
                timeout=self.ctx.settings.request_timeout,
            )
            run_background(
                lambda: self._cline_turn(text, workspace, mode, client, model=cline_model),
                lambda result: self._answer(result) if generation == self._generation else None,
                lambda error: self._failed(error) if generation == self._generation else None,
            )
        else:
            agent = ChatAgent(
                self.ctx.api, self.ctx.settings, cancelled,
                lambda event: self.turn_event.emit((generation, event)),
                lambda title, arguments: self._request_approval(generation, cancelled, title, arguments),
                mcp_runtime=self.mcp_runtime,
            )
            options = {
                "message": text, "model": model, "workflow": workflow, "session_id": self.session_id,
                "paths": list(self.attachments), "mode": self.agent_mode.currentData(),
                "tool_results": list(self.tool_context), "context_cloud_approved": cloud_approved,
            }
            run_background(
                lambda: agent.run(**options),
                lambda result: self._answer(result) if generation == self._generation else None,
                lambda error: self._failed(error) if generation == self._generation else None,
            )

    def _cline_turn(
        self, text: str, workspace: Path, mode: str, client: ClineClient, *, model: str | None = None,
    ) -> dict[str, Any]:
        api = self.ctx.api
        history = api.action("sessions", "context", {"session_id": self.session_id}).get("messages", []) if self.session_id else []
        context = json.dumps(history[-10:], ensure_ascii=False)
        if len(context) > 24000:
            context = context[:24000] + "\n[Önceki sohbet bağlamı kesildi.]"
        result = client.run(workspace, "Previous conversation:\n" + context + "\nCurrent request:\n" + text, mode, model=model)
        session_id = self.session_id or api.create_session(text[:80])["session_id"]
        api.action("sessions", "append_turn", {
            "session_id": session_id, "title": text[:80], "user_message": text, "assistant_message": result["answer"],
        })
        return {"message": {"content": result["answer"]}, "model": "Cline / " + (result.get("model") or "hesapta seçili model"),
                "session_id": session_id, "tools_used": result.get("tools_used", []),
                "cline_verification": {"model_response_verified": result.get("model_response_verified") is True}}

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
        self._render_timer.stop()
        self._partial_answer = ""
        self.cancelled = None
        self._set_busy(False)
        if result.get("status") == "auth_required":
            self.messages.pop()
            self._render()
            self._ask_key(result.get("auth") or {}, retry_text=self.last_question)
            return
        content = (result.get("message") or {}).get("content", "")
        meta = str(result.get("model") or "")
        truncated_context = bool((result.get("context_used") or {}).get("selected_context_truncated"))
        if truncated_context:
            meta += " · seçili bağlam kesildi"
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
        verification = result.get("program_verification")
        package_verification = result.get("package_verification")
        if package_verification and not package_verification["verified"]:
            self.status.set("EXE paketleme başarısız / doğrulanamadı.", "error")
        elif verification:
            self.status.set(
                "Testler geçti; gereksinimler henüz bağımsız doğrulanmadı."
                if verification["tests_passed"] else "Program testleri başarısız / doğrulanamadı.",
                "warn" if verification["tests_passed"] else "error",
            )
        elif package_verification:
            self.status.set("Paketleme geçti; gereksinimler henüz bağımsız doğrulanmadı.", "warn")
        elif truncated_context:
            self.status.set("Yanıt alındı; araç sonuçlarını korumak için seçili bağlam kesildi.", "warn")
        else:
            self.status.set("Yanıt alındı.", "ok")
        if (result.get("cline_verification") or {}).get("model_response_verified") is True:
            self.cline_connection.setText("Gerçek Cline model yanıtı alındı: " + str(result["model"]))
        self._save_paths()
        self._save_summaries()

    def _failed(self, error: Exception) -> None:
        if self.mcp_runtime is not None:
            self.release_mcp(lambda: self._failed(error))
            return
        self._render_timer.stop()
        self.cancelled = None
        self._set_busy(False)
        if isinstance(error, ChatCancelled):
            if self._partial_answer:
                self.messages.append({"role": "assistant", "content": self._partial_answer, "meta": "İptal · tamamlanmamış yanıt"})
            self._partial_answer = ""
            self._render()
            message = "İstek durduruldu. Önceki dosya değişiklikleri ve kısmi kurulumlar geri alınmadı."
            if self._continuity_error:
                message += "\n" + self._continuity_error
            self.status.set(message, "warn")
            self.refresh_sessions()
            return
        self._partial_answer = ""
        if isinstance(error, ApiError) and error.status == 401 and isinstance(error.body, dict) and error.body.get("auth"):
            self.messages.pop()
            self._render()
            self._ask_key(error.body["auth"], retry_text=self.last_question)
            return
        self.messages.append({"role": "error", "content": error_text(error), "meta": ""})
        self._render()
        message = error_text(error)
        if self._continuity_error:
            message += "\n" + self._continuity_error
        self.status.set(message, "error")

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
        self.stop_button.setEnabled(busy and self.cancelled is not None and self.model_box.currentData() != OPENJARVIS)
        self.rollback_button.setEnabled(not busy and self._backup_id is not None)
        for control in (
            self.new_button, self.session_list, self.model_box, self.workflow_box,
            self.agent_mode, self.file_button, self.folder_button, self.remove_attachment_button,
            self.tool_panel, self.retry_button,
            self.cline_controls,
            self.remember_paths,
            self.remember_tools,
            self.keep_mcp,
        ):
            control.setEnabled(not busy)
        if busy:
            self.status.set("Yanıt bekleniyor…", "busy")

    def _render(self, pending: bool = False) -> None:
        parts: list[str] = []
        for message in self.messages:
            if message["role"] == "user":
                header = "#### 🧑 Sen"
            elif message["role"] == "error":
                header = "#### ⚠️ Hata"
            elif message["role"] == "tool":
                header = "#### Araç sonucu"
            else:
                header = "#### 🐼 DeepPanda" + (f"  \n<sub>{html.escape(message['meta'])}</sub>" if message.get("meta") else "")
            parts.append(f"{header}\n\n{message['content']}")
        if pending:
            parts.append(f"#### 🐼 DeepPanda\n\n{self._partial_answer or '_işlem sürüyor…_'}")
        if not parts:
            parts.append("### Birlikte ne yapalım?\n\nDosya veya klasör ekle, ne istediğini yaz. "
                         "**Ajan** uygun araçları seçer; değişiklik ve dış erişim önce onayına sunulur. "
                         "**Sor** yalnız ekleri yorumlar, **Planla** eylem yürütmez.\n\n"
                         "`/help` · Ctrl+O dosya · Ctrl+Shift+O klasör · Ctrl+Enter gönder · Esc durdur")
        self.transcript.setMarkdown("\n\n---\n\n".join(parts))
        bar = self.transcript.verticalScrollBar()
        bar.setValue(bar.maximum())
