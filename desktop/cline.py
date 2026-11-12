from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from desktop.chat_agent import compact_result
from desktop.chat_context import check_cancelled, validate_attachment_path
from desktop.config import PROJECT_ROOT
from desktop.python_runner import ProcessJob, execution_environment
from desktop.windows_host import WindowsHost

CLINE = "__cline__"
VERSION = "3.0.74"


class ClineError(RuntimeError):
    pass


class ClineRpcError(ClineError):
    def __init__(self, method: str, code: Any, message: Any = None) -> None:
        self.method = method
        self.code = code if isinstance(code, int) and not isinstance(code, bool) else None
        self.reason = "unknown"
        hint = "Cline girişini, seçili modeli ve sağlayıcı durumunu kontrol edin; işlem tamamlanmadı."
        text = message.casefold() if isinstance(message, str) else ""
        if any(value in text for value in ("insufficient balance", "insufficient credits", "out of credits", "payment required")):
            self.reason = "billing"
            hint = (
                "Sağlayıcı bakiye/ödeme yetersizliği bildirdi. Cline hesabındaki krediyi ve kişisel/kurum "
                "faturalandırma seçimini Cline üzerinden kontrol edin; otomatik ödeme veya model değişimi yapılmadı."
            )
        elif any(value in text for value in ("unauthorized", "authentication required", "sign in required", "invalid api key")):
            self.reason = "authentication"
            hint = "Sağlayıcı kimlik doğrulama hatası bildirdi; resmî Cline girişini yenileyin. Anahtarı sohbete yazmayın."
        super().__init__(f"Cline ACP {method} hata kodu {self.code}. "
                         + hint)


def session_models(session: dict[str, Any]) -> dict[str, Any]:
    configs = session.get("configOptions", [])
    if not isinstance(configs, list):
        raise ClineError("Cline model yapılandırma şeması geçersiz.")
    for config in configs:
        if not isinstance(config, dict):
            raise ClineError("Cline model yapılandırma şeması geçersiz.")
        if config.get("category") != "model" or config.get("type") != "select":
            continue
        choices = config.get("options", [])
        if not isinstance(choices, list):
            raise ClineError("Cline model seçenekleri geçersiz.")
        flattened = []
        for choice in choices:
            if not isinstance(choice, dict):
                raise ClineError("Cline model seçeneği geçersiz.")
            if "options" in choice:
                if not isinstance(choice["options"], list):
                    raise ClineError("Cline model grubu geçersiz.")
                flattened.extend(choice["options"])
            else:
                flattened.append(choice)
        if any(not isinstance(item, dict) for item in flattened):
            raise ClineError("Cline model grubu seçeneği geçersiz.")
        models = [{"id": item.get("value"), "name": item.get("name")} for item in flattened]
        config_id = config.get("id")
        current = config.get("currentValue")
        method = "session/set_config_option"
        break
    else:
        legacy = session.get("models", {})
        if not isinstance(legacy, dict) or not isinstance(legacy.get("availableModels", []), list):
            raise ClineError("Cline model listesi geçersiz.")
        if any(not isinstance(item, dict) for item in legacy.get("availableModels", [])):
            raise ClineError("Cline model seçeneği geçersiz.")
        models = [{"id": item.get("modelId"), "name": item.get("name")}
                  for item in legacy.get("availableModels", [])]
        config_id = None
        current = legacy.get("currentModelId")
        method = "session/set_model"
    if len(models) > 2000 or any(
        not isinstance(item["id"], str) or not 1 <= len(item["id"]) <= 500
        or not isinstance(item["name"], str) or not 1 <= len(item["name"]) <= 500 for item in models
    ) or len({item["id"] for item in models}) != len(models):
        raise ClineError("Cline model listesi kimlik/boyut sınırlarını aşıyor.")
    if current is not None and (not isinstance(current, str) or len(current) > 500):
        raise ClineError("Cline seçili model kimliği geçersiz.")
    if method == "session/set_config_option" and (not isinstance(config_id, str) or not 1 <= len(config_id) <= 500):
        raise ClineError("Cline model yapılandırma kimliği geçersiz.")
    return {"models": models, "current_model": current, "model_method": method, "model_config_id": config_id}


def command(root: Path = PROJECT_ROOT) -> list[str]:
    exe = root / ".tools" / "cline" / "node_modules" / "@cline" / "cli-windows-x64" / "bin" / "cline.exe"
    if os.name != "nt" or not exe.is_file():
        raise ClineError("Yerel Windows Cline CLI bulunamadı. Önce setup-cline.ps1 çalıştırın.")
    if WindowsHost.is_admin():
        raise ClineError("Cline için Qt normal kullanıcı olarak açılmalıdır; otomatik yetki yükseltme yapılmaz.")
    state = root / ".tools" / "cline-state"
    return [str(exe), "--config", str(state / "config"), "--data-dir", str(state / "data")]


def login(root: Path = PROJECT_ROOT) -> dict[str, Any]:
    args = command(root)
    env = execution_environment(root)
    env["PATH"] = os.environ.get("PATH", env["PATH"])
    process = subprocess.Popen(
        [*args, "auth", "cline"], cwd=root, env=env,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )
    return {"pid": process.pid, "message": "Cline giriş penceresi açıldı; hesabınızı orada bağlayın. Şifre/anahtar sohbete girilmez."}


class ClineClient:
    def __init__(
        self, cancelled: threading.Event, emit: Callable[[dict[str, Any]], None],
        approve: Callable[[str, dict[str, Any]], bool], *, timeout: float = 600,
        root: Path = PROJECT_ROOT,
    ) -> None:
        self.cancelled, self.emit, self.approve = cancelled, emit, approve
        self.timeout, self.root = timeout, root
        self.process: subprocess.Popen[bytes] | None = None
        self.incoming: queue.Queue[dict[str, Any] | Exception | None] = queue.Queue(maxsize=256)
        self.stopped = threading.Event()
        self.sequence = 0
        self.session_id: str | None = None
        self.mode = "ask"
        self.answer = ""
        self.tools: dict[str, dict[str, Any]] = {}

    def _enqueue(self, item: dict[str, Any] | Exception | None) -> None:
        while not self.stopped.is_set():
            try:
                self.incoming.put(item, timeout=0.1)
                return
            except queue.Full:
                continue

    def _read(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        try:
            while not self.stopped.is_set():
                line = self.process.stdout.readline(1_000_001)
                if not line:
                    self._enqueue(None)
                    return
                if len(line) > 1_000_000:
                    raise ClineError("Cline protokol iletisi 1 MB sınırını aştı.")
                payload = json.loads(line)
                if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0":
                    raise ClineError("Cline geçersiz ACP iletisi gönderdi.")
                self._enqueue(payload)
        except (OSError, ValueError, RecursionError, ClineError) as exc:
            self._enqueue(exc)

    def _drain_errors(self) -> None:
        assert self.process is not None and self.process.stderr is not None
        while self.process.stderr.read(4096):
            pass

    def _send(self, payload: dict[str, Any]) -> None:
        assert self.process is not None and self.process.stdin is not None
        self.process.stdin.write((json.dumps({"jsonrpc": "2.0", **payload}, ensure_ascii=False) + "\n").encode())
        self.process.stdin.flush()

    def _permission(self, params: dict[str, Any]) -> dict[str, Any]:
        tool = params.get("toolCall", {})
        options = params.get("options", [])
        if not isinstance(tool, dict) or not isinstance(options, list) or any(
            not isinstance(option, dict) for option in options
        ):
            raise ClineError("Cline izin şeması geçersiz.")
        allow = next((option for option in options if option.get("kind") == "allow_once"), None)
        permitted_mode = self.mode == "agent" or tool.get("kind") in {"read", "search"}
        approved = False
        if self.session_id is None or params.get("sessionId") != self.session_id:
            raise ClineError("Cline izin isteği etkin oturumla eşleşmiyor.")
        if len(json.dumps(params, ensure_ascii=False)) > 48000:
            self.emit({"type": "progress", "message": "Cline izin önizlemesi boyut sınırını aştı; işlem reddedildi.",
                       "status": "error"})
        elif allow is not None and permitted_mode:
            approved = self.approve("Cline / " + str(tool.get("title", "Araç izni"))[:180], {
                "workspace": self.workspace, "tool": tool,
                "warning": "Bu yalnız bu çağrı için izindir; Cline sandbox değildir. İşlem etkileri otomatik geri alınmaz.",
            })
        check_cancelled(self.cancelled)
        if approved and allow is not None:
            return {"outcome": {"outcome": "selected", "optionId": allow["optionId"]}}
        return {"outcome": {"outcome": "cancelled"}}

    def _notification(self, params: dict[str, Any]) -> None:
        if self.session_id is None:
            return
        if params.get("sessionId") != self.session_id:
            raise ClineError("Cline bildirimi etkin oturumla eşleşmiyor.")
        update = params.get("update", {})
        if not isinstance(update, dict):
            raise ClineError("Cline bildirim şeması geçersiz.")
        kind = update.get("sessionUpdate")
        if kind == "agent_message_chunk":
            content = update.get("content", {})
            text = content.get("text") if content.get("type") == "text" else None
            if isinstance(text, str):
                if len(self.answer) + len(text) > 64000:
                    raise ClineError("Cline yanıtı 64.000 karakter sınırını aştı; işlem durduruldu.")
                self.answer += text
                self.emit({"type": "token", "content": text})
        elif kind in {"tool_call", "tool_call_update"}:
            tool_id = update.get("toolCallId")
            if not isinstance(tool_id, str):
                raise ClineError("Cline araç kimliği geçersiz.")
            if tool_id not in self.tools and len(self.tools) >= 64:
                raise ClineError("Cline 64 araç çağrısı sınırına ulaştı; önceki etkiler geri alınmadı.")
            prior = self.tools.get(tool_id, {})
            item = {
                "name": "Cline / " + str(update.get("title", prior.get("title", tool_id)))[:180],
                "title": update.get("title", prior.get("title", tool_id)),
                "status": update.get("status", prior.get("status", "running")),
                "result": compact_result(update),
            }
            self.tools[tool_id] = item
            self.emit({"type": "progress", "message": item["name"], "status": item["status"], "result": item})

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.sequence += 1
        request_id = self.sequence
        self._send({"id": request_id, "method": method, "params": params})
        while True:
            check_cancelled(self.cancelled)
            if time.monotonic() >= self.deadline:
                raise ClineError("Cline süre sınırına ulaştı; süreçler kapatıldı. Önceki etkiler geri alınmadı.")
            try:
                payload = self.incoming.get(timeout=0.1)
            except queue.Empty:
                continue
            if payload is None:
                raise ClineError("Cline ACP bağlantısı yanıt tamamlanmadan kapandı; Cline girişini/kurulumunu kontrol edin.")
            if isinstance(payload, Exception):
                raise ClineError(f"Cline ACP okunamadı: {payload}") from payload
            if "method" in payload:
                params = payload.get("params", {})
                if not isinstance(params, dict):
                    raise ClineError("Cline ACP parametreleri nesne değil.")
                if "id" in payload:
                    if payload["method"] == "session/request_permission":
                        result = self._permission(params)
                        self._send({"id": payload["id"], "result": result})
                    else:
                        self._send({"id": payload["id"], "error": {
                            "code": -32601, "message": "Client file/terminal methods are not supported.",
                        }})
                elif payload["method"] == "session/update":
                    self._notification(params)
                continue
            if payload.get("id") != request_id:
                raise ClineError("Cline beklenmeyen ACP yanıt kimliği gönderdi.")
            if "error" in payload:
                error = payload["error"]
                if not isinstance(error, dict):
                    raise ClineError("Cline ACP hata şeması geçersiz.")
                raise ClineRpcError(method, error.get("code"), error.get("message"))
            result = payload.get("result")
            if not isinstance(result, dict):
                raise ClineError("Cline ACP sonucu nesne değil.")
            return result

    def run(
        self, workspace: Path, prompt: str | None = None, mode: str = "ask", *,
        check_session: bool = False, model: str | None = None,
    ) -> dict[str, Any]:
        if mode not in {"ask", "plan", "agent"}:
            raise ValueError("Geçersiz Cline modu.")
        validate_attachment_path(workspace)
        if not workspace.is_dir():
            raise ValueError("Cline için mevcut bir çalışma klasörü seçin.")
        if prompt is not None and (not prompt.strip() or len(prompt) > 48000):
            raise ValueError("Cline istemi boş olamaz ve 48.000 karakteri aşamaz.")
        if model is not None and (not isinstance(model, str) or not 1 <= len(model) <= 500):
            raise ValueError("Cline model kimliği geçersiz.")
        if check_session and prompt is not None:
            raise ValueError("Cline oturum kontrolü model istemi gönderemez.")
        self.workspace, self.mode = str(workspace), mode
        self.deadline = time.monotonic() + self.timeout
        args = command(self.root)
        env = execution_environment(self.root)
        env["PATH"] = os.environ.get("PATH", env["PATH"])
        job = ProcessJob()
        readers: list[threading.Thread] = []
        finished = False
        try:
            check_cancelled(self.cancelled)
            self.process = subprocess.Popen(
                [*args, "--acp", "--auto-approve", "false", "--cwd", str(workspace)],
                cwd=workspace, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            try:
                job.assign(self.process.pid)
            except OSError:
                self.process.kill()
                self.process.wait(timeout=10)
                raise
            readers = [threading.Thread(target=target, daemon=True) for target in (self._read, self._drain_errors)]
            for reader in readers:
                reader.start()
            initialized = self._request("initialize", {
                "protocolVersion": 1, "clientInfo": {"name": "deeppanda-qt", "version": "1.0.0"},
                "clientCapabilities": {"fs": {"readTextFile": False, "writeTextFile": False}, "terminal": False},
            })
            if initialized.get("protocolVersion") != 1:
                raise ClineError("Cline ACP protokol sürümü desteklenmiyor.")
            probe = {"installed": True, "protocol": 1, "version": VERSION,
                     "authentication_verified": False, "session_ready": False, "model_response_verified": False,
                     "agent": initialized.get("agentInfo", {}).get("name")}
            if prompt is None and not check_session:
                finished = True
                return probe
            try:
                session = self._request("session/new", {"cwd": str(workspace), "mcpServers": []})
            except ClineRpcError as exc:
                if not check_session:
                    raise
                finished = True
                return {**probe, "error": str(exc), "error_code": exc.code, "error_method": exc.method,
                        "error_reason": exc.reason}
            self.session_id = session.get("sessionId")
            if not isinstance(self.session_id, str) or not self.session_id:
                raise ClineError("Cline oturum kimliği döndürmedi.")
            catalog = session_models(session)
            if check_session:
                finished = True
                return {**probe, **catalog, "session_ready": True}
            actual_model = catalog["current_model"]
            if model is not None:
                if model not in {item["id"] for item in catalog["models"]}:
                    raise ClineError("Seçilen Cline modeli yeni oturum kataloğunda yok; bağlantıyı/model listesini yenileyin.")
                if catalog["model_method"] == "session/set_config_option":
                    response = self._request("session/set_config_option", {
                        "sessionId": self.session_id, "configId": catalog["model_config_id"], "value": model,
                    })
                    changed = session_models(response)
                    if changed["current_model"] != model:
                        raise ClineError("Cline istenen model seçimini doğrulamadı; istem gönderilmedi.")
                else:
                    self._request("session/set_model", {"sessionId": self.session_id, "modelId": model})
                actual_model = model
            mode_id = "act" if mode == "agent" else "plan"
            available_modes = (session.get("modes") or {}).get("availableModes", [])
            if not any(item.get("id") == mode_id for item in available_modes):
                raise ClineError("Cline gerekli Plan/Act modunu bildirmedi; güvenli biçimde durduruldu.")
            self._request("session/set_mode", {"sessionId": self.session_id, "modeId": mode_id})
            result = self._request("session/prompt", {
                "sessionId": self.session_id, "prompt": [{"type": "text", "text": prompt}],
            })
            if result.get("stopReason") != "end_turn" or not self.answer.strip():
                raise ClineError(f"Cline turu tamamlanmadı: {result.get('stopReason')}. Önceki etkiler geri alınmadı.")
            finished = True
            return {"answer": self.answer, "cline_session_id": self.session_id, "provider": "cline",
                    "model": actual_model, "authentication_verified": True, "model_response_verified": True,
                    "tools_used": [{"name": item["name"], "status": item["status"]} for item in self.tools.values()]}
        finally:
            self.stopped.set()
            if finished and self.process is not None and self.process.stdin is not None:
                self.process.stdin.close()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
            job.close()
            if self.process is not None:
                self.process.wait(timeout=10)
            for reader in readers:
                reader.join(timeout=2)
            if self.process is not None:
                for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
                    if stream is not None:
                        stream.close()
