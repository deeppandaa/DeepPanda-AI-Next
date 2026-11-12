from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from PySide6.QtWidgets import QApplication, QLineEdit

from desktop.api import ApiError
from desktop.config import Settings
from desktop.context import AppContext
from desktop.page_settings import SettingsPage


class NvidiaSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.ctx = AppContext(Settings())
        self.ctx.call_action = Mock()
        self.ctx.open_url = Mock()
        self.page = SettingsPage(self.ctx, Mock())
        self.addCleanup(self.page.deleteLater)

    def test_key_is_masked_and_never_part_of_qt_settings(self) -> None:
        self.page.nvidia_key.setText("test-private-key")
        self.assertEqual(self.page.nvidia_key.echoMode(), QLineEdit.EchoMode.Password)
        self.assertNotIn("test-private-key", repr(self.page.current()))

    def test_empty_input_and_refusal_make_no_api_call(self) -> None:
        self.page.save_nvidia()
        self.ctx.call_action.assert_not_called()
        self.page.nvidia_key.setText("test-private-key")
        with patch("desktop.page_settings.confirm", return_value=False):
            self.page.save_nvidia()
            self.page.nvidia_models()
            self.page.test_nvidia()
        self.ctx.call_action.assert_not_called()

    def test_save_has_explicit_provider_model_and_clears_field_only_on_success(self) -> None:
        self.page.nvidia_key.setText("test-private-key")
        self.page.nvidia_model.setCurrentText("test/model")
        with patch("desktop.page_settings.confirm", return_value=True):
            self.page.save_nvidia()
        call = self.ctx.call_action.call_args
        self.assertEqual(call.args[1:3], ("cloud_providers", "save_key"))
        self.assertEqual(call.args[3], {"provider": "nvidia", "api_key": "test-private-key", "model": "test/model"})
        self.assertTrue(self.page.nvidia_key.text())
        call.kwargs["on_done"]({})
        self.assertFalse(self.page.nvidia_key.text())

    def test_models_use_saved_credentials_and_saved_default(self) -> None:
        with patch("desktop.page_settings.confirm", return_value=True):
            self.page.nvidia_models()
        call = self.ctx.call_action.call_args
        self.assertEqual(call.args[3], {"provider": "nvidia"})
        call.kwargs["on_done"]({"models": ["one/model", "two/model"], "default_model": "two/model"})
        self.assertEqual(self.page.nvidia_model.currentText(), "two/model")
        self.assertIn("2 model", self.page.nvidia_status.text())

    def test_missing_key_and_api_error_are_not_reported_as_connected(self) -> None:
        with patch("desktop.page_settings.confirm", return_value=True):
            self.page.nvidia_models()
        call = self.ctx.call_action.call_args
        call.kwargs["on_done"]({"status": "auth_required"})
        self.assertIn("kayıtlı değil", self.page.nvidia_status.text())
        call.kwargs["on_error"](ApiError(401, "Anahtar reddedildi"))
        self.assertIn("reddedildi", self.page.nvidia_status.text())

    def test_live_test_sends_fixed_text_only_and_requires_completed_exact_output(self) -> None:
        with patch("desktop.page_settings.confirm", return_value=True):
            self.page.test_nvidia()
        call = self.ctx.call_action.call_args
        self.assertEqual(call.args[1:3], ("cloud_providers", "chat"))
        self.assertEqual(set(call.args[3]), {"provider", "model", "message"})
        self.assertIn("NVIDIA_CONNECTION_OK", call.args[3]["message"])
        for content, done, reason, passed in (
            ("NVIDIA_CONNECTION_OK", True, "stop", True),
            ("different", True, "stop", False),
            ("NVIDIA_CONNECTION_OK", True, "length", False),
            ("NVIDIA_CONNECTION_OK", False, "stop", False),
        ):
            with self.subTest(content=content, done=done, reason=reason):
                call.kwargs["on_done"]({"message": {"content": content}, "done": done, "done_reason": reason})
                self.assertEqual("GEÇTİ" in self.page.nvidia_status.text(), passed)

    def test_inflight_request_prevents_duplicate_charge_and_restores_controls_on_error(self) -> None:
        with patch("desktop.page_settings.confirm", return_value=True):
            self.page.test_nvidia()
            self.page.test_nvidia()
            self.page.nvidia_models()
            self.page.save_nvidia()
        self.ctx.call_action.assert_called_once()
        self.assertTrue(self.page._nvidia_busy)
        self.assertFalse(self.page.nvidia_model.isEnabled())
        self.ctx.call_action.call_args.kwargs["on_error"](ApiError(429, "Kota aşıldı"))
        self.assertFalse(self.page._nvidia_busy)
        self.assertTrue(self.page.nvidia_model.isEnabled())
        self.assertTrue(all(button.isEnabled() for button in self.page._nvidia_buttons))
