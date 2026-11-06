from __future__ import annotations

import base64
import binascii
import hashlib
import json
import logging
import math
import os
import platform
import threading
import time
from pathlib import Path
from typing import Any, ClassVar

from cryptography.exceptions import InvalidSignature

from app.plugins.contracts import PluginManifest

logger = logging.getLogger(__name__)


class LicenseDependencyError(Exception):
    pass


class LicenseApprovalRequired(Exception):
    pass


class LicenseStateError(Exception):
    pass


class LicensingPlugin:
    """Offline Ed25519 (VANA1) license verification with a 30-day trial, ported from LocalQwenAgent."""

    manifest = PluginManifest(
        plugin_id="licensing",
        display_name="Offline License",
        description="VANA1 Ed25519 imzalı lisans anahtarlarını çevrimdışı doğrular; 30 günlük deneme ve saat geri alma tespiti.",
        actions=("status", "activate", "deactivate"),
    )

    PUBLIC_KEY_B64: ClassVar[str] = "ME0q7xA4vxeUvLcZ3m/gakNnXRMLyXWDHsQdLce0YnM="
    PREFIX: ClassVar[str] = "VANA1"
    TRIAL_SECONDS: ClassVar[int] = 30 * 24 * 60 * 60
    PLAN_DURATIONS: ClassVar[dict[str, int]] = {"quarterly": 90 * 24 * 60 * 60, "annual": 365 * 24 * 60 * 60}
    max_key_chars: ClassVar[int] = 8_000

    def __init__(
        self,
        state_dir: str | Path | None = None,
        machine_id: str = "",
        public_key_b64: str = "",
        clock: Any = None,
    ) -> None:
        if state_dir is None:
            state_dir = Path(os.getenv("AI_DATA_DIR", "/data")).expanduser() / "license"
        self.state_dir = Path(state_dir).expanduser().resolve()
        self.license_path = self.state_dir / "license.json"
        self.trial_path = self.state_dir / "trial_state.json"
        self.machine_id = (machine_id or os.getenv("DEEPPANDA_MACHINE_ID", "") or self._persistent_machine_id()).strip().upper()
        self._public_key_b64 = public_key_b64 or os.getenv("LICENSE_PUBLIC_KEY_B64", "") or self.PUBLIC_KEY_B64
        self._public_key: Any = None
        self._clock = clock or time.time
        self._lock = threading.Lock()

    async def invoke(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "status":
            return self.status()
        if action == "activate":
            return self.activate(payload)
        if action == "deactivate":
            if payload.get("approved") is not True:
                raise LicenseApprovalRequired("Removing the license requires approved=true.")
            with self._lock:
                self.license_path.unlink(missing_ok=True)
            return {**self.status(), "deactivated": True}
        raise ValueError(f"Unsupported licensing action: {action}")

    def is_active(self) -> bool:
        try:
            return bool(self.status().get("active"))
        except (LicenseStateError, LicenseDependencyError):
            logger.exception("License status could not be checked.")
            return False

    def installation_id(self) -> str:
        return "-".join(self.machine_id[index:index + 4] for index in range(0, len(self.machine_id), 4))

    def verify_key(self, license_key: str, now: float | None = None) -> dict[str, Any]:
        public_key = self._load_public_key()
        try:
            prefix, payload_part, signature_part = str(license_key or "").strip().split(".", 2)
            if prefix != self.PREFIX:
                raise ValueError("prefix")
            payload_bytes = self._b64_decode(payload_part)
            public_key.verify(self._b64_decode(signature_part), payload_bytes)
            payload = json.loads(payload_bytes.decode("utf-8"))
        except (ValueError, UnicodeError, binascii.Error, InvalidSignature):
            return {"status": "invalid", "active": False, "message": "Lisans anahtarı veya imzası geçersiz."}
        try:
            version = int(payload.get("version", 0)) if isinstance(payload, dict) else 0
        except (TypeError, ValueError):
            version = 0
        if version != 1:
            return {"status": "invalid", "active": False, "message": "Desteklenmeyen lisans sürümü."}
        if str(payload.get("machine_id", "")).upper() != self.machine_id:
            return {"status": "wrong_machine", "active": False, "message": "Lisans başka bir kuruluma ait."}
        plan = str(payload.get("plan", ""))
        if plan not in self.PLAN_DURATIONS:
            return {"status": "invalid", "active": False, "message": "Geçersiz lisans planı."}
        expires_at = payload.get("expires_at")
        issued_at = payload.get("issued_at")
        try:
            valid_expiry = (
                expires_at is not None
                and issued_at is not None
                and float(expires_at) > float(issued_at)
                and float(expires_at) <= float(issued_at) + self.PLAN_DURATIONS[plan] + 60
            )
        except (TypeError, ValueError):
            valid_expiry = False
        if not valid_expiry:
            return {"status": "invalid", "active": False, "message": "Lisans bitiş tarihi planla uyuşmuyor."}
        current = float(now if now is not None else self._clock())
        if current > float(expires_at):
            return {"status": "expired", "active": False, "plan": plan, "message": "Lisansın süresi doldu.", "expires_at": expires_at}
        return {
            "status": "valid",
            "active": True,
            "message": "Lisans geçerli.",
            "plan": plan,
            "customer": str(payload.get("customer", ""))[:200],
            "license_id": str(payload.get("license_id", ""))[:200],
            "issued_at": issued_at,
            "expires_at": expires_at,
            "remaining_days": max(0, int(float(expires_at) - current) + 86399) // 86400,
        }

    def activate(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("approved") is not True:
            raise LicenseApprovalRequired("Activating the license requires approved=true.")
        key = payload.get("license_key")
        if not isinstance(key, str) or not key.strip() or len(key) > self.max_key_chars:
            raise ValueError(f"license_key must be a non-empty string up to {self.max_key_chars} characters.")
        key = key.strip()
        result = self.verify_key(key)
        if not result["active"]:
            return {**result, "installation_id": self.installation_id()}
        with self._lock:
            self._trial_status(float(self._clock()))
            self._atomic_write(self.license_path, {"license_key": key})
        return {**result, "installation_id": self.installation_id(), "message": "Lisans etkinleştirildi."}

    def status(self) -> dict[str, Any]:
        current = float(self._clock())
        with self._lock:
            if self.license_path.is_file():
                try:
                    stored = json.loads(self.license_path.read_text(encoding="utf-8"))
                    result = self.verify_key(str(stored.get("license_key", "")), now=current)
                except (OSError, ValueError, AttributeError):
                    result = {"status": "invalid", "active": False, "message": "Lisans dosyası okunamadı."}
                return {**result, "installation_id": self.installation_id()}
            return self._trial_status(current)

    def _trial_status(self, now: float) -> dict[str, Any]:
        first_seen = last_seen = now
        try:
            raw = self.trial_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raw = None
        except UnicodeError:
            return self._invalid_trial_state()
        except OSError as exc:
            raise LicenseStateError("Deneme kaydı okunamadı; veri dizini izinlerini kontrol edin.") from exc
        if raw is not None:
            try:
                state = json.loads(raw)
                if not isinstance(state, dict) or state.get("machine_id") != self.machine_id:
                    return self._invalid_trial_state()
                first_seen = float(state["first_seen"])
                last_seen = float(state["last_seen"])
            except (ValueError, KeyError, TypeError, OverflowError):
                return self._invalid_trial_state()
            if not (math.isfinite(first_seen) and math.isfinite(last_seen) and 0 <= first_seen <= last_seen):
                return self._invalid_trial_state()
        if now + 3600 < last_seen:
            return {
                "status": "clock_rollback",
                "active": False,
                "plan": "trial",
                "message": "Sistem saati geri alınmış; deneme doğrulanamadı.",
                "installation_id": self.installation_id(),
            }
        last_seen = max(last_seen, now)
        self._atomic_write(self.trial_path, {"machine_id": self.machine_id, "first_seen": first_seen, "last_seen": last_seen})
        expires_at = first_seen + self.TRIAL_SECONDS
        remaining = max(0, int(expires_at - now))
        return {
            "status": "trial" if remaining else "expired",
            "active": bool(remaining),
            "plan": "trial",
            "message": "30 günlük deneme aktif." if remaining else "30 günlük deneme sona erdi.",
            "first_seen": first_seen,
            "expires_at": expires_at,
            "remaining_seconds": remaining,
            "remaining_days": (remaining + 86399) // 86400,
            "installation_id": self.installation_id(),
        }

    def _invalid_trial_state(self) -> dict[str, Any]:
        logger.warning("Invalid trial state; the existing record has not been reset.")
        return {
            "status": "invalid_state",
            "active": False,
            "plan": "trial",
            "message": "Deneme kaydı bozuk veya başka kuruluma ait; kayıt sıfırlanmadı.",
            "installation_id": self.installation_id(),
        }

    def _load_public_key(self) -> Any:
        if self._public_key is None:
            try:
                from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                    Ed25519PublicKey,
                )
            except ImportError as exc:
                raise LicenseDependencyError("The cryptography package is required for license verification.") from exc
            self._public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(self._public_key_b64, validate=True))
        return self._public_key

    def _atomic_write(self, path: Path, value: dict[str, Any]) -> None:
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
            temporary.replace(path)
        except OSError as exc:
            raise LicenseStateError("Lisans durumu kaydedilemedi; veri dizini izinlerini kontrol edin.") from exc

    @staticmethod
    def _b64_decode(value: str) -> bytes:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

    def _persistent_machine_id(self) -> str:
        """Pin the first computed fingerprint so container rebuilds keep the same installation id."""
        path = self.state_dir / "machine_id"
        try:
            stored = path.read_text(encoding="utf-8").strip().upper()
        except FileNotFoundError:
            stored = None
        except (OSError, UnicodeError) as exc:
            raise LicenseStateError("Kalıcı kurulum kimliği okunamadı; kayıt değiştirilmedi.") from exc
        if stored is not None:
            if len(stored) != 64 or any(char not in "0123456789ABCDEF" for char in stored):
                raise LicenseStateError("Kalıcı kurulum kimliği bozuk; kayıt değiştirilmedi.")
            return stored
        fingerprint = self._machine_fingerprint()
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(fingerprint, encoding="utf-8")
        except OSError as exc:
            raise LicenseStateError("Kalıcı kurulum kimliği kaydedilemedi.") from exc
        return fingerprint

    @staticmethod
    def _machine_fingerprint() -> str:
        components = [platform.node(), platform.machine()]
        machine_id_file = Path("/etc/machine-id")
        if os.name == "nt":
            try:
                import winreg

                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\Microsoft\Cryptography",
                    0,
                    winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0),
                ) as key:
                    components.append(str(winreg.QueryValueEx(key, "MachineGuid")[0]))
            except OSError:
                pass
        elif machine_id_file.is_file():
            try:
                components.append(machine_id_file.read_text(encoding="utf-8").strip())
            except OSError:
                pass
        value = "|".join(item.strip().lower() for item in components if item)
        return hashlib.sha256(value.encode("utf-8")).hexdigest().upper()
