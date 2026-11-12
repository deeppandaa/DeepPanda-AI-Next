import unittest
from battery import format_status, read_status

class TestFormatStatus(unittest.TestCase):
    def test_charging(self):
        res = format_status(1, 8, 50, 3600)
        self.assertEqual(res['percent'], 50)
        self.assertEqual(res['status'], 'Şarj Ediliyor')
        self.assertTrue(res['is_charging'])
        self.assertTrue(res['ac_connected'])

    def test_ac_power(self):
        res = format_status(1, 0, 80, 7200)
        self.assertEqual(res['percent'], 80)
        self.assertEqual(res['status'], 'AC Gücü')
        self.assertFalse(res['is_charging'])
        self.assertTrue(res['ac_connected'])

    def test_battery_only(self):
        res = format_status(0, 1, 30, 1800)
        self.assertEqual(res['percent'], 30)
        self.assertEqual(res['status'], 'Pil ile Çalışıyor')
        self.assertFalse(res['is_charging'])
        self.assertFalse(res['ac_connected'])

    def test_no_battery(self):
        res = format_status(0, 128, 0, 0)
        self.assertEqual(res['percent'], 0)
        self.assertEqual(res['status'], 'Pil Yok')
        self.assertFalse(res['is_charging'])

    def test_unknown_flags(self):
        res = format_status(255, 255, 255, 0xFFFFFFFF)
        self.assertIsNone(res['percent'])
        self.assertEqual(res['status'], 'Bilinmiyor')
        self.assertFalse(res['is_charging'])
        self.assertFalse(res['ac_connected'])

    def test_unknown_ac(self):
        res = format_status(255, 1, 50, 3600)
        self.assertIsNone(res['percent'])
        self.assertEqual(res['status'], 'Bilinmiyor')

    def test_unknown_percent(self):
        res = format_status(1, 1, 255, 3600)
        self.assertIsNone(res['percent'])
        self.assertEqual(res['status'], 'Bilinmiyor')

    def test_unknown_remaining(self):
        res = format_status(1, 1, 50, 0xFFFFFFFF)
        self.assertEqual(res['percent'], 50)
        self.assertIsNone(res['remaining'])

class TestReadStatus(unittest.TestCase):
    def test_success(self):
        import ctypes
        from ctypes import wintypes, Structure, byref, POINTER

        class MockSps(Structure):
            _fields_ = [("ACLineStatus", wintypes.BYTE), ("BatteryFlag", wintypes.BYTE),
                        ("BatteryLifePercent", wintypes.BYTE), ("SystemStatusFlag", wintypes.BYTE),
                        ("BatteryLifeTime", wintypes.DWORD), ("BatteryFullLifeTime", wintypes.DWORD)]

        original = ctypes.windll.kernel32.GetSystemPowerStatus
        original_argtypes = original.argtypes
        original_restype = original.restype

        def mock_get(sps_ptr):
            # sps_ptr is a POINTER(SYSTEM_POWER_STATUS)
            # Mutate the contents via byref or pointer access
            ctypes.memset(ctypes.addressof(sps_ptr.contents), 0, ctypes.sizeof(MockSps))
            sps_ptr.contents.ACLineStatus = 1
            sps_ptr.contents.BatteryFlag = 8
            sps_ptr.contents.BatteryLifePercent = 50
            sps_ptr.contents.SystemStatusFlag = 0
            sps_ptr.contents.BatteryLifeTime = 3600
            sps_ptr.contents.BatteryFullLifeTime = 7200
            return True

        try:
            ctypes.windll.kernel32.GetSystemPowerStatus.argtypes = [POINTER(MockSps)]
            ctypes.windll.kernel32.GetSystemPowerStatus.restype = wintypes.BOOL
            ctypes.windll.kernel32.GetSystemPowerStatus = mock_get

            res = read_status()
            self.assertEqual(res['percent'], 50)
            self.assertEqual(res['status'], 'Şarj Ediliyor')
        finally:
            ctypes.windll.kernel32.GetSystemPowerStatus.argtypes = original_argtypes
            ctypes.windll.kernel32.GetSystemPowerStatus.restype = original_restype
            ctypes.windll.kernel32.GetSystemPowerStatus = original

if __name__ == '__main__':
    unittest.main()