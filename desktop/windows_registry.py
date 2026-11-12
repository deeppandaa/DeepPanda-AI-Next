from __future__ import annotations

import base64
import re
from typing import Any

try:
    import winreg
except ImportError:
    winreg = None


def registry_target(key: str, name: str = "", view: str = "64", *, writing: bool = False) -> dict[str, str]:
    if not isinstance(key, str) or "\x00" in key or "/" in key:
        raise ValueError("Kayıt yolu HKCU\\Software\\... veya HKLM\\SOFTWARE\\... olmalıdır.")
    hive, separator, path = key.partition("\\")
    hive = {"HKEY_CURRENT_USER": "HKCU", "HKEY_LOCAL_MACHINE": "HKLM"}.get(hive.upper(), hive.upper())
    parts = path.split("\\")
    if hive not in {"HKCU", "HKLM"} or not separator or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Yalnız açık HKCU / HKLM anahtarları desteklenir.")
    if parts[0].casefold() != "software" or len(parts) < 2:
        raise ValueError("SAM, SECURITY, SYSTEM ve donanım kovanları yönetilmez; Software altında hedef seçin.")
    if not isinstance(name, str) or "\x00" in name or len(name) > 255 or view not in {"32", "64"}:
        raise ValueError("Kayıt değeri adı veya 32/64 görünümü geçersiz.")
    lowered = (path + "\\" + name).casefold()
    if any(word in lowered for word in ("password", "credential", "secret", "token", "\\dpapi", "\\protect")):
        raise ValueError("Kimlik bilgisi / gizli anahtar kayıtları bu araçtan dışlanır.")
    if writing and (
        len(parts) < 3 or parts[1].casefold() in {"classes", "policies"}
        or path.casefold().startswith(("software\\microsoft\\windows", "software\\microsoft\\.netframework"))
        or any(word in lowered for word in (
            "launchpermission", "accesspermission", "security", "defender", "\\run", "\\winlogon",
            "debugger", "image file execution", "appinit", "autorun", "shellex",
        ))
    ):
        raise ValueError("Önyükleme, güvenlik, otomatik çalıştırma ve COM/DCOM izinleri otomatik değiştirilmez.")
    return {"key": hive + "\\" + path, "name": name, "view": view}


def _handle(target: dict[str, Any]) -> tuple[Any, str, int]:
    if winreg is None:
        raise OSError("Windows kayıt defteri bu platformda yok.")
    hive, path = target["key"].split("\\", 1)
    root = winreg.HKEY_CURRENT_USER if hive == "HKCU" else winreg.HKEY_LOCAL_MACHINE
    flags = winreg.KEY_WOW64_64KEY if target["view"] == "64" else winreg.KEY_WOW64_32KEY
    return root, path, flags


def registry_snapshot(target: dict[str, Any]) -> dict[str, Any]:
    root, path, flags = _handle(target)
    assert winreg is not None
    try:
        handle = winreg.OpenKey(root, path, 0, winreg.KEY_READ | flags)
    except FileNotFoundError:
        return {"key_exists": False, "exists": False}
    with handle:
        try:
            data, kind = winreg.QueryValueEx(handle, target["name"])
        except FileNotFoundError:
            return {"key_exists": True, "exists": False}
    if isinstance(data, bytes):
        data = {"base64": base64.b64encode(data).decode("ascii")}
    if len(str(data)) > 65_536:
        raise ValueError("Kayıt değeri 64K önizleme sınırını aşıyor.")
    return {"key_exists": True, "exists": True, "type": kind, "data": data}


def registry_data(payload: dict[str, Any]) -> dict[str, Any]:
    assert winreg is not None
    kind = payload.get("value_type", "REG_SZ")
    data: Any = payload.get("data", "")
    if "\x00" in data:
        raise ValueError("Kayıt metninde NUL karakteri olamaz.")
    if kind in {"REG_DWORD", "REG_QWORD"}:
        if not re.fullmatch(r"(?:[0-9]+|0[xX][0-9a-fA-F]+)", data):
            raise ValueError("DWORD/QWORD verisi negatif olmayan tamsayı veya 0x... olmalıdır.")
        data = int(data, 16 if data.lower().startswith("0x") else 10)
        if data >= 2 ** (32 if kind == "REG_DWORD" else 64):
            raise ValueError("Kayıt tamsayısı tür sınırını aşıyor.")
    elif kind == "REG_MULTI_SZ":
        data = data.splitlines()
        if "" in data:
            raise ValueError("MULTI_SZ içinde boş ara satır olamaz; boş liste için veriyi boş bırakın.")
    return {"key_exists": True, "exists": True, "type": getattr(winreg, kind), "data": data}


def missing_registry_keys(target: dict[str, Any]) -> list[str]:
    root, path, flags = _handle(target)
    assert winreg is not None
    missing = []
    while path:
        try:
            with winreg.OpenKey(root, path, 0, winreg.KEY_READ | flags):
                break
        except FileNotFoundError:
            missing.append(path)
            path = path.rpartition("\\")[0]
    return missing


def restore_registry(target: dict[str, Any], state: dict[str, Any], missing: list[str] | None = None) -> None:
    root, path, flags = _handle(target)
    assert winreg is not None
    if state["exists"]:
        data = state["data"]
        if isinstance(data, dict):
            data = base64.b64decode(data["base64"], validate=True)
        with winreg.CreateKeyEx(root, path, 0, winreg.KEY_SET_VALUE | flags) as handle:
            winreg.SetValueEx(handle, target["name"], 0, state["type"], data)
            winreg.FlushKey(handle)
    else:
        with winreg.OpenKey(root, path, 0, winreg.KEY_SET_VALUE | flags) as handle:
            winreg.DeleteValue(handle, target["name"])
        for key in missing or []:
            with winreg.OpenKey(root, key, 0, winreg.KEY_READ | flags) as handle:
                children, values, _changed = winreg.QueryInfoKey(handle)
            if children or values:
                raise ValueError("Yeni anahtara başka veri eklenmiş; bu anahtar silinmedi.")
            winreg.DeleteKeyEx(root, key, flags, 0)
