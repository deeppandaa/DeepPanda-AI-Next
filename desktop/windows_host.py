from __future__ import annotations

import base64
import copy
import ctypes
import difflib
import hashlib
import json
import logging
import os
import platform
import re
import socket
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from desktop.chat_context import (
    ChatCancelled,
    _excluded,
    check_cancelled,
    validate_attachment_path,
)
from desktop.config import PROJECT_ROOT, ensure_backend_importable
from desktop.program_projects import ACTIONS as PROJECT_ACTIONS
from desktop.program_projects import ProgramProjects
from desktop.python_runner import run_python
from desktop.tool_schema import form_schema
from desktop.windows_registry import (
    missing_registry_keys,
    registry_data,
    registry_snapshot,
    registry_target,
    restore_registry,
)

ensure_backend_importable()
from app.plugins.windows_host import (
    HOST_FORMS,
    HOST_MUTATIONS,
    HOST_PRIVATE_READS,
    HOST_READ_ONLY,
)

logger = logging.getLogger(__name__)
MAX_FILE_BYTES = 1_000_000
CRITICAL_CLASSES = {
    "system", "computer", "processor", "firmware", "diskdrive", "scsiadapter", "hdc",
    "volume", "net", "display", "keyboard", "mouse", "hidclass", "battery", "securitydevices",
}
SCRIPTS = {
    "system_info": "Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,BuildNumber,OSArchitecture,LastBootUpTime,TotalVisibleMemorySize,FreePhysicalMemory",
    "devices": "$items=Get-CimInstance Win32_PnPEntity; if($p.usb_only){$items=$items|Where-Object {$_.PNPDeviceID -like 'USB\\*'}}; $items|Where-Object {([string]$_.Name+' '+$_.PNPDeviceID).IndexOf([string]$p.query,[StringComparison]::OrdinalIgnoreCase) -ge 0}|Select-Object -First ($p.limit+1) Name,PNPDeviceID,PNPClass,Service,Status,ConfigManagerErrorCode,Present",
    "device": "Get-CimInstance Win32_PnPEntity|Where-Object {$_.PNPDeviceID -eq $p.instance_id}|Select-Object Name,PNPDeviceID,PNPClass,Service,Status,ConfigManagerErrorCode,Present",
    "ports": "Get-CimInstance Win32_SerialPort|Where-Object {([string]$_.Name+' '+$_.DeviceID).IndexOf([string]$p.query,[StringComparison]::OrdinalIgnoreCase) -ge 0}|Select-Object -First ($p.limit+1) Name,DeviceID,PNPDeviceID,Status",
    "drivers": "Get-CimInstance Win32_PnPSignedDriver|Where-Object {([string]$_.DeviceName+' '+$_.InfName).IndexOf([string]$p.query,[StringComparison]::OrdinalIgnoreCase) -ge 0}|Select-Object -First ($p.limit+1) DeviceName,DeviceID,InfName,DriverVersion,DriverDate,DriverProviderName,IsSigned",
    "driver_users": "Get-CimInstance Win32_PnPSignedDriver|Where-Object {$_.InfName -eq $p.inf_name}|Select-Object -First 201 DeviceID,DeviceName,InfName",
    "com_list": "Get-CimInstance Win32_DCOMApplication|Where-Object {([string]$_.Name+' '+$_.AppID).IndexOf([string]$p.query,[StringComparison]::OrdinalIgnoreCase) -ge 0}|Select-Object -First ($p.limit+1) Name,AppID",
    "dcom_events": "$events=@(Get-WinEvent -FilterHashtable @{ProviderName='Microsoft-Windows-DistributedCOM';StartTime=(Get-Date).AddDays(-7)} -MaxEvents ($p.limit+1) -ErrorAction SilentlyContinue -ErrorVariable eventErrors); if($eventErrors -and $eventErrors[0].FullyQualifiedErrorId -notlike 'NoMatchingEventsFound*'){throw $eventErrors[0]}; $events|Select-Object TimeCreated,Id,LevelDisplayName,Message",
    "signatures": "$p.paths|ForEach-Object {Get-AuthenticodeSignature -LiteralPath $_}|Select-Object Path,@{Name='Status';Expression={$_.Status.ToString()}}",
}


class HostError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


class WindowsHost:
    def __init__(self, storage: Path | None = None) -> None:
        self.storage = storage or PROJECT_ROOT / "data" / "windows-host"
        self._plans: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._specs = {spec["action"]: spec for spec in HOST_FORMS}
        self.projects = ProgramProjects(PROJECT_ROOT, self._atomic)

    @staticmethod
    def is_admin() -> bool:
        return os.name == "nt" and bool(ctypes.windll.shell32.IsUserAnAdmin())

    def _run(self, executable: str, args: list[str], *, data: str | None = None, timeout: int = 45) -> dict[str, Any]:
        path = Path(os.environ["SystemRoot"]) / "System32" / executable
        completed = subprocess.run(
            [str(path), *args], input=data, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        output = (completed.stdout or "") + (completed.stderr or "")
        if completed.returncode not in {0, 3010}:
            raise HostError(502, f"Windows komutu başarısız ({completed.returncode}); otomatik tekrar yok.\n{output[:16000]}")
        return {"output": output[:32000], "truncated": len(output) > 32000,
                "reboot_required": completed.returncode == 3010}

    def _ps(self, operation: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        script = (
            "$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue';"
            "[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false);"
            "$p=ConvertFrom-Json ([Console]::In.ReadToEnd());"
            f"$result=@(& {{{SCRIPTS[operation]}}});ConvertTo-Json -InputObject $result -Depth 6 -Compress"
        )
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        result = self._run(
            r"WindowsPowerShell\v1.0\powershell.exe",
            ["-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            data=json.dumps(payload, ensure_ascii=True),
        )
        if result["truncated"]:
            raise HostError(502, "Windows envanter çıktısı sınırı aştı; filtreyi daraltın.")
        value = json.loads(result["output"])
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise HostError(502, "Windows aracı geçerli JSON envanteri döndürmedi.")
        return value

    def _parameters(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        spec = self._specs.get(action)
        if spec is None:
            raise ValueError("Bilinmeyen Windows host eylemi.")
        data = dict(payload)
        for field in spec["fields"]:
            if field["name"] not in data and "value" in field:
                data[field["name"]] = int(field["value"]) if field.get("type") == "number" else field["value"]
        try:
            Draft202012Validator(form_schema(spec)).validate(data)
        except ValidationError as exc:
            raise ValueError(f"Windows araç argümanı geçersiz: {exc.message}") from exc
        return data

    @staticmethod
    def _target(path: str) -> Path:
        target = Path(path)
        if not target.is_absolute() or ".." in target.parts or str(target).startswith("\\\\") or any(":" in part for part in target.parts[1:]):
            raise ValueError("Yerel diskte mutlak dosya yolu gerekir; UNC, aygıt yolu ve ADS desteklenmez.")
        if any(part != part.rstrip(" .") for part in target.parts[1:]):
            raise ValueError("Nokta veya boşlukla biten Windows yol takma adları kabul edilmez.")
        if any(part.casefold() in {".ssh", ".aws", ".azure", ".gnupg", ".kube", "system volume information"} for part in target.parts):
            raise ValueError("Gizli / sistem yolu dışlanmıştır.")
        for key in ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramData", "APPDATA", "LOCALAPPDATA"):
            if os.environ.get(key) and target.is_relative_to(Path(os.environ[key])):
                raise ValueError("Windows, program veya özel uygulama dizinlerine genel dosya erişimi verilmez.")
        if not target.exists() and not target.parent.is_dir():
            raise ValueError("Hedefin üst klasörü mevcut olmalıdır; üst klasörler otomatik oluşturulmaz.")
        validate_attachment_path(target if target.exists() else target.parent)
        if target.name.casefold().endswith(".env") or target.name.casefold().startswith(".env.") or target.suffix.casefold() in {".pem", ".key", ".pfx", ".p12", ".kdbx"}:
            raise ValueError("Gizli dosya hedefi dışlanmıştır.")
        return target

    @staticmethod
    def _file(path: str) -> Path:
        target = WindowsHost._target(path)
        if target.exists() and (not target.is_file() or target.stat().st_nlink > 1):
            raise ValueError("Hedef tek bağlantılı normal dosya olmalıdır.")
        return target

    @staticmethod
    def _directory(path: str) -> Path:
        target = WindowsHost._target(path)
        if _excluded(target):
            raise ValueError("Gizli veya çalışma zamanı yolu klasör hedefi olamaz.")
        return target

    def _file_state(self, path: str) -> dict[str, Any]:
        target = self._file(path)
        if not target.exists():
            return {"exists": False}
        with target.open("rb") as stream:
            raw = stream.read(MAX_FILE_BYTES + 1)
        if len(raw) > MAX_FILE_BYTES:
            raise ValueError("Host dosyası 1 MB okuma/yazma sınırını aşıyor.")
        return {"exists": True, "sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw), "base64": base64.b64encode(raw).decode("ascii")}

    @staticmethod
    def _atomic(path: Path, raw: bytes) -> None:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def _save(self, record: dict[str, Any]) -> None:
        self.storage.mkdir(parents=True, exist_ok=True)
        self._atomic(self.storage / (record["id"] + ".json"), json.dumps(record, ensure_ascii=False).encode("utf-8"))

    def _record(self, operation_id: str) -> dict[str, Any]:
        if not re.fullmatch(r"[a-f0-9]{32}", operation_id):
            raise ValueError("İşlem kimliği geçersiz.")
        record = json.loads((self.storage / (operation_id + ".json")).read_text(encoding="utf-8"))
        if not isinstance(record, dict) or record.get("id") != operation_id:
            raise ValueError("Yedek işlem kimliği dosyayla eşleşmiyor.")
        return record

    def _device(self, instance_id: str) -> dict[str, Any]:
        rows = self._ps("device", {"instance_id": instance_id})
        if len(rows) != 1:
            raise ValueError("Tam Instance ID ile tek bir aygıt bulunmalıdır; envanteri yenileyin.")
        row = rows[0]
        if (
            str(row.get("PNPClass", "")).casefold() in CRITICAL_CLASSES
            or str(row.get("Service", "")).casefold() in {"usbhub", "usbhub3", "usbccgp"}
            or "ROOT_HUB" in instance_id.upper() or not row.get("PNPClass")
        ):
            raise ValueError("Kritik aygıt, USB hub veya birleşik aygıt otomatik değiştirilemez.")
        return row

    def _package(self, path: str) -> dict[str, str]:
        inf = self._file(path)
        if inf.suffix.casefold() != ".inf" or not inf.is_file():
            raise ValueError("Yerel, mevcut bir .inf dosyası gerekir.")
        files = {}
        total = 0
        for index, child in enumerate(inf.parent.rglob("*")):
            if index >= 512:
                raise ValueError("Sürücü paketi 512 giriş sınırını aşıyor; yalıtılmış paket klasörü seçin.")
            validate_attachment_path(child)
            if child.is_file():
                self._file(str(child))
                total += child.stat().st_size
                if total > 256_000_000:
                    raise ValueError("Sürücü paketi 256 MB sınırını aşıyor.")
                with child.open("rb") as stream:
                    files[str(child.relative_to(inf.parent))] = hashlib.file_digest(stream, "sha256").hexdigest()
        if not any(Path(name).suffix.casefold() == ".cat" for name in files):
            raise ValueError("Sürücü paketinde imzalı .cat kataloğu bulunmalıdır.")
        return files

    def _snapshot(self, action: str, data: dict[str, Any]) -> Any:
        if action in PROJECT_ACTIONS:
            if self.is_admin():
                raise HostError(403, "Program proje araçlarını normal kullanıcı Qt ile kullanın; yönetici çalıştırması kapalıdır.")
            return self.projects.snapshot(action, data)
        if action == "python_run":
            target = self._file(data["path"])
            if target.suffix.casefold() != ".py" or not target.is_file():
                raise ValueError("Çalıştırma için mevcut, normal bir .py dosyası gerekir.")
            if self.is_admin():
                raise HostError(403, "Python çalıştırma yükseltilmiş Qt sürecinde kapalıdır; normal kullanıcı olarak açın.")
            state = self._file_state(data["path"])
            raw = base64.b64decode(state["base64"])
            source = raw.decode("utf-8-sig")
            try:
                compile(source, str(target), "exec")
            except SyntaxError as exc:
                raise ValueError(f"Python sözdizimi hatası: {exc}") from exc
            manifest = json.loads((PROJECT_ROOT / "tools" / "python-runtime.json").read_text(encoding="utf-8"))
            base = PROJECT_ROOT / "runtimes" / ("python-" + manifest["version"]) / "tools"
            executable = base / "python.exe"
            with executable.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if digest != manifest["executableSha256"]:
                raise ValueError("Proje Python yorumlayıcı hash'i doğrulanamadı; çalıştırma reddedildi.")
            return {"script": state, "interpreter": str(executable), "interpreter_sha256": digest}
        if action == "directory_create":
            return {"exists": self._directory(data["path"]).exists()}
        if action.startswith("file_"):
            return self._file_state(data["path"])
        if action.startswith("registry_"):
            target = registry_target(data["key"], data.get("name", ""), data.get("view", "64"), writing=action != "registry_read")
            return registry_snapshot(target)
        if action.startswith("device_") and action != "device_scan":
            return self._device(data["instance_id"])
        if action == "driver_install":
            return self._package(data["path"])
        if action == "driver_remove":
            inf = data["inf_name"].lower()
            if not re.fullmatch(r"oem[0-9]+\.inf", inf):
                raise ValueError("Yalnız tam oemNN.inf paket adı desteklenir.")
            users = self._ps("driver_users", {"inf_name": inf})
            if users:
                raise ValueError("Bu paket aygıtlara bağlı; /force veya /uninstall ile zorla kaldırılmaz.")
            raw = (Path(os.environ["SystemRoot"]) / "INF" / inf).read_bytes()
            return {"sha256": hashlib.sha256(raw).hexdigest()}
        if action == "rollback":
            record = self._record(data["operation_id"])
            if record["status"] != "completed" or record["action"] not in {"file_write", "file_delete", "registry_set", "registry_delete"}:
                raise ValueError("Yalnız tamamlanmış dosya / kayıt değeri işlemleri otomatik geri alınabilir.")
            current = self._snapshot(record["action"], record["arguments"])
            if current != record["after"]:
                raise HostError(409, "Hedef işlemden sonra değişmiş; başka değişikliklerin üzerine geri alınmadı.")
            return {"record": hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest(), "target": current}
        return None

    def preview(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action not in HOST_MUTATIONS:
            raise ValueError("Bu eylem önizlemeli değişiklik değildir.")
        with self._lock:
            data = self._parameters(action, payload)
            before = self._snapshot(action, data)
            warnings = ["Otomatik yeniden başlatma veya UAC yükseltmesi yapılmaz."]
            reversible = action in {"file_write", "file_delete", "registry_set", "registry_delete"}
            admin = action.startswith(("device_", "driver_")) or (
                action.startswith("registry_") and registry_target(data["key"])["key"].startswith("HKLM\\")
            )
            extra: dict[str, Any] = {}
            original = None
            if action in PROJECT_ACTIONS:
                extra.update(self.projects.preview(action, data))
                warnings.append("Program oluşturmak/test etmek başarı garantisi değildir; test çıkışını inceleyin.")
            if action == "python_run":
                source = base64.b64decode(before["script"]["base64"]).decode("utf-8-sig")
                extra.update(
                    source_preview=source[:16000], source_truncated=len(source) > 16000,
                    interpreter=before["interpreter"], interpreter_sha256=before["interpreter_sha256"],
                    cwd=str(Path(data["path"]).parent), arguments=data.get("arguments", []),
                    timeout=data["timeout"], output_bytes_per_stream=32000,
                )
                warnings.append(
                    "Bu bir sandbox değildir: kod mevcut kullanıcı yetkileriyle dosya, ağ ve sistem API'lerine "
                    "erişebilir; etkileri geri alınmaz. Yalnız güvendiğiniz kodu onaylayın. "
                    "Sağlayıcı anahtarları ortamdan aktarılmaz ancak kod kullanıcı dosyalarına erişebilir. "
                    "Yorumlayıcı yalnız temel Python paketlerini kullanır; paket kurulumu yapılmaz. "
                    "Durdurma en geç süre sınırında uygulanır; süreç ağacı normal bitişte de kapatılır."
                )
            if action == "directory_create":
                if before["exists"]:
                    raise ValueError("Hedef zaten var; mevcut dosya veya klasör değiştirilmez.")
                warnings.append("Yalnız tek boş klasör oluşturulur; üst klasör önceden mevcut olmalıdır.")
            if action == "file_write":
                raw = data["content"].encode("utf-8")
                if len(raw) > MAX_FILE_BYTES:
                    raise ValueError("UTF-8 dosya içeriği 1 MB sınırını aşıyor.")
                old = base64.b64decode(before["base64"]).decode("utf-8") if before["exists"] else ""
                diff = "".join(difflib.unified_diff(old.splitlines(True), data["content"].splitlines(True), "before", "after"))
                extra.update(diff=diff[:16000], diff_truncated=len(diff) > 16000)
            if action in {"file_delete", "registry_delete"} and not before["exists"]:
                raise ValueError("Kaldırılacak dosya / değer mevcut değil.")
            if action == "registry_set":
                extra["proposed_value"] = registry_data(data)
            if action == "network_check":
                host = data["host"]
                if not re.fullmatch(r"[A-Za-z0-9_.:-]+", host) or not host.strip(".:"):
                    raise ValueError("Sunucu adı veya IP girin; URL, kullanıcı bilgisi ve sorgu kabul edilmez.")
                warnings.append("Onaydan sonra DNS ve TCP bağlantısı kurulur; dosya, parola veya HTTP gövdesi gönderilmez.")
            if not reversible:
                warnings.append("Bu işlem otomatik geri alınamaz.")
            if action == "driver_remove":
                warnings.append("Sürücü kaldırılmadan önce paket dışa aktarılır.")
            if action == "driver_install":
                warnings.append("Windows imza/sertifika doğrulaması ağa erişebilir; imza zorlaması kapatılmaz.")
            if action == "rollback":
                original = self._record(data["operation_id"])
                admin = original["action"].startswith("registry_") and original["arguments"]["key"].upper().startswith(("HKLM\\", "HKEY_LOCAL_MACHINE\\"))
                extra["original_action"] = original["action"]
                extra["original_target"] = original["arguments"].get("path") or original["arguments"].get("key")
                extra["restore"] = {key: value for key, value in original["before"].items() if key != "base64"}
            plan_id = uuid.uuid4().hex
            now = time.time()
            self._plans = {key: value for key, value in self._plans.items() if value["expires"] > now}
            if len(self._plans) >= 64:
                raise HostError(429, "Bekleyen önizleme sınırı doldu; önceki önizlemelerin süresinin dolmasını bekleyin.")
            self._plans[plan_id] = {"id": plan_id, "action": action, "arguments": copy.deepcopy(data),
                                    "before": before, "expires": now + 600, "admin": admin}
            if original is not None:
                self._plans[plan_id]["rollback_record"] = copy.deepcopy(original)
            public_before = {key: value for key, value in before.items() if key != "base64"} if isinstance(before, dict) else before
            if action == "python_run":
                public_before = {**before, "script": {key: value for key, value in before["script"].items() if key != "base64"}}
            if action == "project_update":
                public_before = {key: value for key, value in before.items() if key != "previous_content"}
            if action == "rollback":
                public_before = {**before, "target": {key: value for key, value in before["target"].items() if key != "base64"}}
            return {"plan_id": plan_id, "action": action,
                    "target": {key: value for key, value in data.items() if key not in {"content", "data", "files"}},
                    "before": public_before, "requires_administrator": admin, "reversible": reversible,
                    "expires_in_seconds": 600, "warnings": warnings, **extra}

    def _perform(
        self, plan: dict[str, Any], *, cancelled: threading.Event | None = None,
    ) -> dict[str, Any]:
        action, data = plan["action"], plan["arguments"]
        if action in PROJECT_ACTIONS:
            result = self.projects.perform(action, data, plan["before"], cancelled=cancelled)
            marker = self.projects.marker(data["project"])
            if marker.is_file():
                project_record = json.loads(marker.read_text(encoding="utf-8"))
                criteria = project_record.get("criteria")
                if isinstance(criteria, str):
                    result["criteria"] = criteria
                criteria_hash = project_record.get("criteria_request_sha256")
                if isinstance(criteria_hash, str):
                    result["criteria_request_sha256"] = criteria_hash
            plan["execution"] = result
            self._save(plan)
            if action == "project_environment" and not result["environment_ready"] and not result.get("cancelled"):
                raise HostError(502, f"Proje ortamı kurulamadı; otomatik tekrar yok. Ayrı ortam kısmen oluşmuş olabilir.\n{result}")
            return result
        if action == "python_run":
            result = run_python(
                Path(plan["before"]["interpreter"]), self._file(data["path"]),
                plan["before"]["script"]["base64"], data.get("arguments", []), data["timeout"], PROJECT_ROOT,
                cancelled=cancelled,
            )
            plan["execution"] = result
            self._save(plan)
            if not result.get("cancelled") and (result["timed_out"] or result["exit_code"] != 0):
                raise HostError(
                    504 if result["timed_out"] else 502,
                    f"Python çalıştırma başarısız: exit={result['exit_code']}, timeout={result['timed_out']}. "
                    "Yan etkiler geri alınmadı; otomatik tekrar yok.\n"
                    f"stdout:\n{result['stdout']}\nstderr:\n{result['stderr']}",
                )
            return result
        if action == "directory_create":
            target = self._directory(data["path"])
            target.mkdir()
            if not validate_attachment_path(target).is_dir():
                raise HostError(409, "Klasör oluşturuldu ancak doğrulanamadı; hedefi inceleyin.")
            return {"path": str(target)}
        if action == "file_write":
            self._atomic(self._file(data["path"]), data["content"].encode("utf-8"))
        elif action == "file_delete":
            self._file(data["path"]).unlink()
        elif action.startswith("registry_"):
            target = registry_target(data["key"], data.get("name", ""), data.get("view", "64"), writing=True)
            plan["missing_keys"] = missing_registry_keys(target)
            self._save(plan)
            restore_registry(target, registry_data(data) if action == "registry_set" else {"exists": False})
        elif action == "rollback":
            original = plan["rollback_record"]
            args, before = original["arguments"], original["before"]
            if original["action"].startswith("file_"):
                target_file = self._file(args["path"])
                if before["exists"]:
                    self._atomic(target_file, base64.b64decode(before["base64"], validate=True))
                else:
                    target_file.unlink()
            else:
                target_reg = registry_target(args["key"], args.get("name", ""), args.get("view", "64"), writing=True)
                restore_registry(target_reg, before, original.get("missing_keys"))
            if self._snapshot(original["action"], args) != before:
                raise HostError(409, "Geri alınan hedefin eski durumu doğrulanamadı.")
            original["status"] = "rolled_back"
            self._save(original)
        elif action == "network_check":
            started = time.monotonic()
            with socket.create_connection((data["host"], data["port"]), timeout=5) as connection:
                peer = connection.getpeername()[0]
            return {"connected": True, "peer": peer, "elapsed_ms": round((time.monotonic() - started) * 1000),
                    "note": "TCP bağlantısıdır; TLS/HTTP veya hizmet sağlığı doğrulaması değildir."}
        elif action.startswith("device_"):
            args = ["/scan-devices"] if action == "device_scan" else [
                "/" + action.removeprefix("device_") + "-device", data["instance_id"],
            ]
            result = self._run("pnputil.exe", args, timeout=120)
            if action in {"device_enable", "device_disable"}:
                state = self._ps("device", {"instance_id": data["instance_id"]})
                if not state or (state[0]["ConfigManagerErrorCode"] == 22) != (action == "device_disable"):
                    raise HostError(502, "Komut döndü fakat aygıt durumu doğrulanamadı; etki oluşmuş olabilir, envanteri yenileyin.")
                result["state_after"] = state
            return result
        elif action == "driver_install":
            folder = Path(data["path"]).parent
            cats = [str(folder / name) for name in plan["before"] if Path(name).suffix.casefold() == ".cat"]
            signatures = self._ps("signatures", {"paths": cats})
            if len(signatures) != len(cats) or any(item["Status"] != "Valid" for item in signatures):
                raise ValueError("Sürücü kataloğunun geçerli imzası doğrulanamadı; kurulum yapılmadı.")
            return self._run("pnputil.exe", ["/add-driver", data["path"], "/install"], timeout=180)
        elif action == "driver_remove":
            backup = self.storage / (plan["id"] + "-driver")
            backup.mkdir()
            self._run("pnputil.exe", ["/export-driver", data["inf_name"], str(backup)], timeout=120)
            if not any(backup.rglob("*.inf")):
                raise HostError(502, "Sürücü yedeğinde INF bulunamadı; paket kaldırılmadı.")
            result = self._run("pnputil.exe", ["/delete-driver", data["inf_name"]], timeout=120)
            result["driver_backup"] = str(backup)
            return result
        else:
            raise ValueError("Uygulanamayan Windows host eylemi.")
        return {}

    def apply(
        self, action: str, payload: dict[str, Any], *, cancelled: threading.Event | None = None,
    ) -> dict[str, Any]:
        if cancelled is not None:
            check_cancelled(cancelled)
        if payload.get("approved") is not True:
            raise HostError(403, "Hedef önizlemesi için açık kullanıcı onayı gerekir.")
        if set(payload) != {"plan_id", "approved"}:
            raise ValueError("Uygulama yalnız önizlemenin plan_id değerini kabul eder; argüman değiştirilemez.")
        if not isinstance(payload["plan_id"], str) or not re.fullmatch(r"[a-f0-9]{32}", payload["plan_id"]):
            raise ValueError("Önizleme kimliği geçersiz.")
        with self._lock:
            plan = self._plans.get(payload["plan_id"])
            if plan is None or plan["expires"] < time.time() or plan["action"] != action:
                raise HostError(409, "Önizleme yok, süresi dolmuş veya eylem değişmiş; yeniden önizleyin.")
            if plan["admin"] and not self.is_admin():
                raise HostError(403, "Bu işlem yönetici yetkisi gerektirir. UAC otomatik aşılmaz; Qt'yi bilinçli olarak yönetici açıp yeniden önizleyin.")
            if self._snapshot(action, plan["arguments"]) != plan["before"]:
                raise HostError(409, "Hedef önizlemeden sonra değişmiş; işlem yapılmadı.")
            if cancelled is not None:
                check_cancelled(cancelled)
            self._plans.pop(plan["id"])
            plan = copy.deepcopy(plan)
            plan["status"] = "pending"
            self._save(plan)
            try:
                result = self._perform(plan, cancelled=cancelled)
                if result.get("cancelled"):
                    raise ChatCancelled(
                        "Python işlemi iptal edildi; başlatılan süreç ağacı kapatıldı. "
                        "Önceki dosya değişiklikleri veya kısmi ortam kurulumu geri alınmadı; otomatik tekrar yok."
                    )
                if action in {"file_write", "file_delete", "registry_set", "registry_delete"}:
                    plan["after"] = self._snapshot(action, plan["arguments"])
                    if action == "file_write" and plan["after"].get("sha256") != hashlib.sha256(plan["arguments"]["content"].encode("utf-8")).hexdigest():
                        raise HostError(409, "Yazılan dosya içeriği doğrulanamadı; hedefi inceleyin.")
                    if action == "registry_set" and plan["after"] != registry_data(plan["arguments"]):
                        raise HostError(409, "Yazılan kayıt değeri doğrulanamadı; hedefi inceleyin.")
                    if action.endswith("_delete") and plan["after"]["exists"]:
                        raise HostError(409, "Hedefin kaldırıldığı doğrulanamadı.")
                failed = (action == "project_test" and not result["passed"]) or (
                    action == "project_package" and not result["packaged"]
                )
                plan["status"] = "failed" if failed else "completed"
            except ChatCancelled as exc:
                plan["status"] = "cancelled"
                plan["error"] = str(exc)
                self._save(plan)
                logger.info("Windows host operation cancelled: %s (%s)", action, plan["id"])
                raise
            except (OSError, ValueError, HostError, subprocess.SubprocessError) as exc:
                plan["status"] = "failed"
                plan["error"] = str(exc)
                self._save(plan)
                logger.exception("Windows host operation failed: %s (%s)", action, plan["id"])
                raise
            self._save(plan)
            return {"status": plan["status"], "operation_id": plan["id"], "action": action,
                    "reversible": "after" in plan, **result}

    def invoke(
        self, action: str, payload: dict[str, Any], *, cancelled: threading.Event | None = None,
    ) -> dict[str, Any]:
        if cancelled is not None:
            check_cancelled(cancelled)
        if os.name != "nt":
            raise HostError(503, "Bu araç yalnız Windows Qt hostunda kullanılabilir.")
        if action == "preview":
            if set(payload) != {"action", "arguments"} or not isinstance(payload["arguments"], dict) or not isinstance(payload["action"], str):
                raise ValueError("Önizleme action ve arguments alanlarını gerektirir.")
            return self.preview(payload["action"], payload["arguments"])
        if action in HOST_MUTATIONS:
            return self.apply(action, payload, cancelled=cancelled)
        if action not in HOST_READ_ONLY:
            raise ValueError("Bilinmeyen Windows host eylemi.")
        if action in HOST_PRIVATE_READS:
            if payload.get("approved") is not True:
                raise HostError(403, f"Host verisini okumak için hedefe özel onay gerekir: {payload.get('path') or payload.get('key')}")
            payload = {key: value for key, value in payload.items() if key != "approved"}
        data = self._parameters(action, payload)
        if action == "status":
            return {"available": True, "is_administrator": self.is_admin(), "platform": platform.platform(),
                    "execution_location": "Windows Qt host", "automatic_elevation": False,
                    "actions": list(self._specs), "backup_directory": str(self.storage)}
        if action == "file_read":
            state = self._file_state(data["path"])
            if not state["exists"]:
                raise FileNotFoundError(data["path"])
            return {"path": data["path"], "sha256": state["sha256"],
                    "content": base64.b64decode(state["base64"]).decode("utf-8")}
        if action == "registry_read":
            target = registry_target(data["key"], data.get("name", ""), data.get("view", "64"))
            return {**target, **registry_snapshot(target)}
        if action == "driver_packages":
            return self._run("pnputil.exe", ["/enum-drivers"])
        if action == "com_info":
            clsid = "{" + str(uuid.UUID(data["clsid"].strip("{}"))).upper() + "}"
            entries = []
            for hive in ("HKCU", "HKLM"):
                for view in ("64", "32"):
                    base = hive + "\\Software\\Classes\\CLSID\\" + clsid
                    values = {
                        label: registry_snapshot(registry_target(base + suffix, name, view))
                        for label, suffix, name in (
                            ("name", "", ""), ("appid", "", "AppID"), ("progid", "\\ProgID", ""),
                            ("inproc_server", "\\InprocServer32", ""), ("local_server", "\\LocalServer32", ""),
                        )
                    }
                    appid_data = values["appid"].get("data")
                    appid_settings: dict[str, Any] = {"status": "AppID kaydı yok"}
                    if isinstance(appid_data, str):
                        try:
                            appid = "{" + str(uuid.UUID(appid_data.strip("{}"))).upper() + "}"
                        except ValueError:
                            appid_settings = {"status": "AppID GUID değil; takip edilmedi"}
                        else:
                            appid_path = hive + "\\Software\\Classes\\AppID\\" + appid
                            appid_settings = {
                                "key": appid_path,
                                "local_service": registry_snapshot(registry_target(appid_path, "LocalService", view)),
                                "dll_surrogate": registry_snapshot(registry_target(appid_path, "DllSurrogate", view)),
                                "custom_launch_permission": registry_snapshot(registry_target(appid_path, "LaunchPermission", view))["exists"],
                                "custom_access_permission": registry_snapshot(registry_target(appid_path, "AccessPermission", view))["exists"],
                            }
                    entries.append({"hive": hive, "view": view, "values": values,
                                    "appid_settings": appid_settings})
            return {"clsid": clsid, "registrations": entries,
                    "note": "COM nesnesi etkinleştirilmedi; DCOM 10016 tek başına otomatik izin düzeltme nedeni değildir."}
        rows = self._ps(action, {"query": "", "limit": 50, **data})
        limit = data.get("limit", 50)
        return {"items": rows[:limit], "truncated": len(rows) > limit, "read_only": True}
