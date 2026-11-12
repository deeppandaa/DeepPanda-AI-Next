from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from desktop.api import ApiClient
from desktop.config import SETTINGS_FILE, Settings
from desktop.context import AppContext, confirm, error_text
from desktop.tasks import run_background
from desktop.widgets import StatusLabel


class SettingsPage(QWidget):
    def __init__(self, ctx: AppContext, on_saved: Callable[[], None]) -> None:
        super().__init__()
        self.ctx = ctx
        self.on_saved = on_saved
        layout = QVBoxLayout(self)
        title = QLabel("Ayarlar")
        title.setObjectName("formTitle")
        layout.addWidget(title)
        form = QFormLayout()
        self.api_url = QLineEdit()
        self.web_url = QLineEdit()
        self.db_manager_url = QLineEdit()
        self.project_dir = QLineEdit()
        self.extra_mcp = QLineEdit()
        self.extra_mcp.setPlaceholderText("Ek mcp.json yolları (; ile ayır)")
        self.include_vscode = QCheckBox("VS Code / GitHub Copilot mcp.json sunucularını da kullan")
        self.timeout = QSpinBox()
        self.timeout.setRange(30, 7200)
        self.timeout.setSuffix(" sn")
        self.program_review_model = QLineEdit()
        self.program_review_model.setPlaceholderText("Kapalı; örnek: qwen2.5-coder:7b")
        self.program_review_model.setToolTip(
            "Kurulu farklı yerel model başarısız testi bağımsız inceler. "
            "İlk başarılı testten sonra ayrı onaylı ikinci test yapılır. "
            "Kaynaklar yerel API'ye gönderilir; görüşler kanıt veya yürütme izni değildir."
        )
        form.addRow("API adresi", self.api_url)
        form.addRow("Web arayüzü adresi", self.web_url)
        form.addRow("DB yöneticisi adresi", self.db_manager_url)
        form.addRow("Proje klasörü (docker compose)", self.project_dir)
        form.addRow("Ek MCP yapılandırmaları", self.extra_mcp)
        form.addRow("", self.include_vscode)
        form.addRow("İstek zaman aşımı", self.timeout)
        form.addRow("Program ikinci ajan modeli", self.program_review_model)
        layout.addLayout(form)
        row = QHBoxLayout()
        save = QPushButton("Kaydet")
        save.setObjectName("primary")
        save.clicked.connect(self.save)
        test = QPushButton("API bağlantısını test et")
        test.clicked.connect(self.test)
        row.addWidget(save)
        row.addWidget(test)
        row.addStretch(1)
        layout.addLayout(row)
        nvidia_title = QLabel("NVIDIA NIM API")
        nvidia_title.setObjectName("sectionTitle")
        layout.addWidget(nvidia_title)
        info = QLabel(
            "Anahtarı sohbete değil aşağıdaki maskeli alana girin. Anahtar mevcut API sunucusunun "
            "yerel sağlayıcı deposunda saklanır (Qt INI dosyasında değil; şifreli kasa değildir). "
            "Deneme/kota/ücret koşullarını NVIDIA hesabınızdan kontrol edin."
        )
        info.setWordWrap(True)
        layout.addWidget(info)
        nvidia_form = QFormLayout()
        self.nvidia_key = QLineEdit()
        self.nvidia_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.nvidia_key.setPlaceholderText("NVIDIA API anahtarı (kaydedilince alan temizlenir)")
        self.nvidia_model = QComboBox()
        self.nvidia_model.setEditable(True)
        self.nvidia_model.addItem("meta/llama-3.1-8b-instruct")
        nvidia_form.addRow("API anahtarı", self.nvidia_key)
        nvidia_form.addRow("Model ID", self.nvidia_model)
        layout.addLayout(nvidia_form)
        nvidia_row = QHBoxLayout()
        self._nvidia_busy = False
        self._nvidia_buttons: list[QPushButton] = []
        for label, callback in (
            ("NVIDIA API sayfasını aç", lambda: self.ctx.open_url("https://build.nvidia.com/")),
            ("Anahtar + modeli kaydet", self.save_nvidia),
            ("Kayıtlı modelleri getir", self.nvidia_models),
            ("Kısa yanıt testi", self.test_nvidia),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            self._nvidia_buttons.append(button)
            nvidia_row.addWidget(button)
        layout.addLayout(nvidia_row)
        self.nvidia_status = StatusLabel("Henüz NVIDIA bağlantısı doğrulanmadı.")
        layout.addWidget(self.nvidia_status)
        self.status = StatusLabel(f"Ayar dosyası: {SETTINGS_FILE}")
        layout.addWidget(self.status)
        layout.addStretch(1)
        self.load(ctx.settings)

    def load(self, settings: Settings) -> None:
        self.api_url.setText(settings.api_url)
        self.web_url.setText(settings.web_url)
        self.db_manager_url.setText(settings.db_manager_url)
        self.project_dir.setText(settings.project_dir)
        self.extra_mcp.setText(settings.extra_mcp_configs)
        self.include_vscode.setChecked(settings.include_vscode_mcp)
        self.timeout.setValue(settings.request_timeout)
        self.program_review_model.setText(settings.program_review_model)

    def current(self) -> Settings:
        return replace(
            self.ctx.settings,
            api_url=self.api_url.text().strip().rstrip("/") or Settings.api_url,
            web_url=self.web_url.text().strip().rstrip("/") or Settings.web_url,
            db_manager_url=self.db_manager_url.text().strip().rstrip("/") or Settings.db_manager_url,
            project_dir=self.project_dir.text().strip() or Settings.project_dir,
            extra_mcp_configs=self.extra_mcp.text().strip(),
            include_vscode_mcp=self.include_vscode.isChecked(),
            request_timeout=self.timeout.value(),
            program_review_model=self.program_review_model.text().strip(),
        )

    def save(self) -> None:
        settings = self.current()
        settings.save()
        self.ctx.apply_settings(settings)
        self.on_saved()
        self.status.set("Ayarlar kaydedildi.", "ok")

    def test(self) -> None:
        settings = self.current()
        client = ApiClient(settings.api_url, 10)
        run_background(client.health, lambda result: self.status.set(f"API yanıt verdi: {result}", "ok"),
                       lambda error: self.status.set(error_text(error), "error"))

    def _nvidia_failed(self, error: Exception) -> None:
        self.nvidia_status.set(error_text(error), "error")

    def _nvidia_call(self, action: str, payload: dict[str, Any], on_done: Callable[[Any], None]) -> None:
        def finish() -> None:
            self._nvidia_busy = False
            for widget in [*self._nvidia_buttons, self.nvidia_key, self.nvidia_model]:
                widget.setEnabled(True)

        def done(result: Any) -> None:
            finish()
            on_done(result)

        def failed(error: Exception) -> None:
            finish()
            self._nvidia_failed(error)

        self._nvidia_busy = True
        for widget in [*self._nvidia_buttons, self.nvidia_key, self.nvidia_model]:
            widget.setEnabled(False)
        self.nvidia_status.set("NVIDIA işlemi sürüyor...", "busy")
        self.ctx.call_action(
            self, "cloud_providers", action, payload, on_done=done, on_error=failed,
        )

    def save_nvidia(self) -> None:
        if self._nvidia_busy:
            return
        key, model = self.nvidia_key.text().strip(), self.nvidia_model.currentText().strip()
        if not key or not model:
            self.nvidia_status.set("NVIDIA anahtarı ve model ID gerekli; hiçbir istek gönderilmedi.", "warn")
            return
        if not confirm(
            self, "NVIDIA anahtarı ve model tercihi mevcut API sunucusunda saklansın mı?",
            details=f"API sunucusu: {self.ctx.settings.api_url}\nModel: {model}\n"
            "Anahtar sohbete/geçmişe veya Qt ayarlarına yazılmaz. Bu işlem NVIDIA'ya model istemi göndermez.",
        ):
            return

        def saved(_result: Any) -> None:
            self.nvidia_key.clear()
            self.nvidia_status.set(
                "NVIDIA anahtarı/modeli kaydedildi; gerçek yanıt henüz doğrulanmadı. "
                "Sohbette model listesini yenileyip Bulut: NVIDIA NIM seçebilirsiniz.", "ok",
            )

        self._nvidia_call(
            "save_key", {"provider": "nvidia", "api_key": key, "model": model}, saved,
        )

    def nvidia_models(self) -> None:
        if self._nvidia_busy:
            return
        if not confirm(
            self, "Kayıtlı NVIDIA anahtarıyla model kataloğu sorgulansın mı?",
            details="Yalnız NVIDIA model listesi istenir; sohbet, ekler ve proje dosyaları gönderilmez.",
        ):
            return

        def loaded(result: dict[str, Any]) -> None:
            if result.get("status") == "auth_required":
                self.nvidia_status.set("NVIDIA anahtarı kayıtlı değil; önce anahtarı kaydedin.", "warn")
                return
            selected = result.get("default_model") or self.nvidia_model.currentText().strip()
            self.nvidia_model.clear()
            self.nvidia_model.addItems(result["models"])
            self.nvidia_model.setCurrentText(selected)
            self.nvidia_status.set(
                f"NVIDIA kataloğu: {len(result['models'])} model. Gerçek yanıt henüz doğrulanmadı. "
                "Model tercihini kalıcı değiştirmek için anahtarla birlikte kaydedin.", "info",
            )

        self._nvidia_call("models", {"provider": "nvidia"}, loaded)

    def test_nvidia(self) -> None:
        if self._nvidia_busy:
            return
        model = self.nvidia_model.currentText().strip()
        if not model:
            self.nvidia_status.set("Test için model ID gerekli.", "warn")
            return
        if not confirm(
            self, "Seçili NVIDIA modeline sabit kısa yanıt testi gönderilsin mi? Kota/ücret uygulanabilir.",
            details=f"Model: {model}\nYalnız NVIDIA_CONNECTION_OK yanıtını isteyen sabit istem gönderilir. "
            "Sohbet geçmişi, dosyalar, ekler veya araç sonuçları gönderilmez; araç çalıştırılmaz.",
        ):
            return

        def tested(result: dict[str, Any]) -> None:
            passed = (
                result.get("done") is True
                and result.get("done_reason") == "stop"
                and result.get("message", {}).get("content", "").strip() == "NVIDIA_CONNECTION_OK"
            )
            self.nvidia_status.set(
                "NVIDIA gerçek kısa yanıt testi GEÇTİ." if passed
                else "NVIDIA testi geçmedi; tamamlanmış beklenen sabit çıktı alınamadı.",
                "ok" if passed else "warn",
            )

        self._nvidia_call(
            "chat",
            {"provider": "nvidia", "model": model, "message": "Reply exactly NVIDIA_CONNECTION_OK. Do not use tools."},
            tested,
        )
