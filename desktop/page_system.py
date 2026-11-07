from __future__ import annotations

import json
from typing import Any

import httpx
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desktop.api import ApiError
from desktop.context import AppContext, confirm, error_text
from desktop.tasks import run_background
from desktop.widgets import StatusLabel, mono_font

PRIMARY_MODEL = "qwen2.5-coder:7b"
CARDS = [("api", "API"), ("ollama", "Ollama / Qwen 2.5"), ("openjarvis", "OpenJarvis"),
         ("graphify", "graphify"), ("db_manager", "DB yöneticisi"), ("web", "Web arayüzü")]


class StatusCard(QFrame):
    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        heading = QLabel(title)
        heading.setObjectName("cardTitle")
        self.state = QLabel("…")
        self.state.setObjectName("cardState")
        self.detail = QLabel("")
        self.detail.setWordWrap(True)
        self.detail.setObjectName("hint")
        layout.addWidget(heading)
        layout.addWidget(self.state)
        layout.addWidget(self.detail)

    def set(self, ok: bool | None, state: str, detail: str = "") -> None:
        self.state.setProperty("kind", "ok" if ok else ("warn" if ok is None else "error"))
        self.state.setText(("● " if ok else "○ ") + state)
        self.state.style().unpolish(self.state)
        self.state.style().polish(self.state)
        self.detail.setText(detail)


class SystemPage(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        layout = QVBoxLayout(self)
        grid = QGridLayout()
        self.cards: dict[str, StatusCard] = {}
        for index, (key, title) in enumerate(CARDS):
            card = StatusCard(title)
            self.cards[key] = card
            grid.addWidget(card, index // 3, index % 3)
        layout.addLayout(grid)

        rows = [
            [("Durumu yenile", self.refresh), ("Yığını başlat", self.compose_up), ("Konteyner durumu", self.compose_ps),
             ("API günlükleri", self.api_logs)],
            [("Qwen 2.5 modelini indir", self.pull_model), ("API'yi yeniden derle", self.rebuild_api),
             ("Web arayüzünü aç", self.open_web), ("Tanılama taraması", self.diagnostics)],
        ]
        for buttons in rows:
            row = QHBoxLayout()
            for text, slot in buttons:
                button = QPushButton(text)
                button.clicked.connect(slot)
                row.addWidget(button)
            row.addStretch(1)
            layout.addLayout(row)
        self.status = StatusLabel()
        layout.addWidget(self.status)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(mono_font())
        self.log.setPlaceholderText("Docker ve sistem çıktıları burada görünür.")
        layout.addWidget(self.log, 1)

    def activate(self) -> None:
        self.refresh()

    # ---------- status ----------
    def refresh(self) -> None:
        api, settings = self.ctx.api, self.ctx.settings

        def probe(url: str) -> bool:
            try:
                return httpx.get(url, timeout=3).status_code < 500
            except httpx.HTTPError:
                return False

        def work() -> dict[str, Any]:
            out: dict[str, Any] = {}
            try:
                api.health()
                out["api"] = (True, "çalışıyor", api.base_url)
            except ApiError as exc:
                out["api"] = (False, "ulaşılamıyor", exc.detail)
                for key in ("ollama", "openjarvis", "graphify"):
                    out[key] = (None, "API kapalı", "")
            if out["api"][0]:
                try:
                    models = api.models()
                    names = [item.get("name") or item.get("model") for item in models.get("models", [])]
                    has_primary = PRIMARY_MODEL in names
                    out["ollama"] = (has_primary, f"{len(names)} model",
                                     f"Varsayılan: {models.get('default_model')}"
                                     + ("" if has_primary else f"\n{PRIMARY_MODEL} yok → 'Qwen 2.5 modelini indir'"))
                except ApiError as exc:
                    out["ollama"] = (False, "ulaşılamıyor", exc.detail)
                try:
                    jarvis = api.action("openjarvis", "status", {})
                    out["openjarvis"] = (bool(jarvis.get("reachable")), "bağlı" if jarvis.get("reachable") else "kapalı",
                                         ", ".join(jarvis.get("models", [])) or jarvis.get("hint", ""))
                except ApiError as exc:
                    out["openjarvis"] = (False, "hata", exc.detail)
                try:
                    graph = api.action("graphify", "status", {})
                    out["graphify"] = (bool(graph.get("exists")), "grafik hazır" if graph.get("exists") else "grafik yok",
                                       graph.get("hint") or graph.get("graph_path", ""))
                except ApiError as exc:
                    out["graphify"] = (False, "hata", exc.detail)
            manager = probe(settings.db_manager_url)
            out["db_manager"] = (manager or None, "çalışıyor" if manager else "kapalı (isteğe bağlı)", settings.db_manager_url)
            web = probe(settings.web_url)
            out["web"] = (web or None, "çalışıyor" if web else "kapalı (isteğe bağlı)", settings.web_url)
            return out

        self.status.set("Durum kontrol ediliyor…", "busy")

        def done(out: dict[str, Any]) -> None:
            for key, value in out.items():
                self.cards[key].set(*value)
            self.status.set("Durum güncellendi.", "ok")

        run_background(work, done, lambda error: self.status.set(error_text(error), "error"))

    # ---------- docker ----------
    def _run(self, title: str, args: list[str], after: Any = None) -> None:
        self.status.set(f"{title}…", "busy")
        self.log.appendPlainText(f"$ {' '.join(args)}")

        def done(result: dict[str, Any]) -> None:
            self.log.appendPlainText((result["output"] or "(çıktı yok)") + "\n")
            self.status.set(f"{title}: {'tamam' if result['ok'] else 'başarısız (kod ' + str(result['code']) + ')'}",
                            "ok" if result["ok"] else "error")
            if result["ok"] and after is not None:
                after()

        self.ctx.run_command(args, done)

    def compose_up(self) -> None:
        if confirm(self, "Docker yığını başlatılsın mı? (api, ollama, freellmapi, redis, qdrant)\n"
                         "Eksik imajlar varsa indirilir/derlenir; mevcut veriler korunur."):
            self._run("Yığın başlatılıyor", ["docker", "compose", "up", "-d"], self.refresh)

    def compose_ps(self) -> None:
        self._run("Konteyner durumu", ["docker", "compose", "--profile", "web", "--profile", "manager", "ps"])

    def api_logs(self) -> None:
        self._run("API günlükleri", ["docker", "compose", "logs", "--tail", "200", "api"])

    def rebuild_api(self) -> None:
        if confirm(self, "API imajı yeniden derlenip yalnızca api konteyneri yenilensin mi?\n"
                         "(Veriler ai_data biriminde korunur; birkaç dakika sürebilir.)"):
            self._run("API derleniyor", ["docker", "compose", "build", "api"],
                      lambda: self._run("API yeniden başlatılıyor", ["docker", "compose", "up", "-d", "api"], self.refresh))

    def open_web(self) -> None:
        url = self.ctx.settings.web_url

        def reachable() -> bool:
            try:
                return httpx.get(url, timeout=3).status_code < 500
            except httpx.HTTPError:
                return False

        def after(ok: bool) -> None:
            if ok:
                self.ctx.open_url(url)
            elif confirm(self, "Web arayüzü kapalı. Docker'da başlatılıp açılsın mı?\n(docker compose --profile web up -d web)"):
                self._run("Web arayüzü başlatılıyor", ["docker", "compose", "--profile", "web", "up", "-d", "web"],
                          lambda: self.ctx.open_url(url))

        run_background(reachable, after, lambda _error: after(False))

    # ---------- api actions ----------
    def pull_model(self) -> None:
        self.status.set(f"{PRIMARY_MODEL} indiriliyor (birkaç GB; uzun sürebilir)…", "busy")
        self.ctx.call_action(
            self, "ollama", "pull", {"model": PRIMARY_MODEL},
            approval=f"{PRIMARY_MODEL} Ollama'ya indirilsin mi? (~4.7 GB)",
            timeout=7200,
            on_done=lambda result: (self.log.appendPlainText(str(result)), self.status.set("Model hazır.", "ok"), self.refresh()),
            on_error=lambda error: self.status.set(error_text(error), "error"),
        )

    def diagnostics(self) -> None:
        self.status.set("Tanılama çalışıyor…", "busy")

        def done(result: Any) -> None:
            self.log.appendPlainText(json.dumps(result, ensure_ascii=False, indent=2)[:20_000])
            self.status.set("Tanılama tamamlandı.", "ok")

        run_background(self.ctx.api.diagnostics_scan, done, lambda error: self.status.set(error_text(error), "error"))
