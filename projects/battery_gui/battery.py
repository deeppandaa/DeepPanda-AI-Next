import ctypes
from ctypes import wintypes, Structure, pointer

class SYSTEM_POWER_STATUS(Structure):
    _fields_ = [
        ("ACLineStatus", wintypes.BYTE),
        ("BatteryFlag", wintypes.BYTE),
        ("BatteryLifePercent", wintypes.BYTE),
        ("SystemStatusFlag", wintypes.BYTE),
        ("BatteryLifeTime", wintypes.DWORD),
        ("BatteryFullLifeTime", wintypes.DWORD),
    ]

def format_status(ac, flags, percent, remaining):
    if remaining == 0xFFFFFFFF:
        remaining = None
    if ac == 255 or flags == 255:
        return {"percent": None, "status": "Bilinmiyor", "is_charging": False, "ac_connected": False, "remaining": remaining}
    if flags == 128:
        return {"percent": 0, "status": "Pil Yok", "is_charging": False, "ac_connected": False, "remaining": remaining}
    is_charging = bool(flags & 0x08)
    if is_charging:
        status = "Şarj Ediliyor"
    elif ac == 1:
        status = "AC Gücü"
    else:
        status = "Pil ile Çalışıyor"
    pct_val = None if percent == 255 else percent
    # If percent is unknown (255), treat the overall status as unknown per test expectation
    if percent == 255:
        return {"percent": None, "status": "Bilinmiyor", "is_charging": False, "ac_connected": ac == 1, "remaining": remaining}
    return {"percent": pct_val, "status": status, "is_charging": is_charging, "ac_connected": ac == 1, "remaining": remaining}

def read_status():
    kernel32 = ctypes.windll.kernel32
    func = kernel32.GetSystemPowerStatus
    func.argtypes = [ctypes.POINTER(SYSTEM_POWER_STATUS)]
    func.restype = wintypes.BOOL
    sps = SYSTEM_POWER_STATUS()
    if not func(pointer(sps)):
        raise OSError('GetSystemPowerStatus failed')
    return format_status(sps.ACLineStatus, sps.BatteryFlag, sps.BatteryLifePercent, sps.BatteryLifeTime)
