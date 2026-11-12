from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from desktop.config import Settings
from desktop.context import AppContext
from desktop.page_settings import SettingsPage


class ProgramReviewSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_default_is_off_and_model_timeout_roundtrip_preserves_existing_choices(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch(
            "desktop.config.SETTINGS_FILE", Path(temporary) / "settings.ini",
        ):
            settings = Settings(cline_model="preserved", program_review_model="qwen2.5-coder:7b", request_timeout=660)
            settings.save()
            loaded = Settings.load()
        self.assertEqual(Settings().program_review_model, "")
        self.assertEqual(loaded.program_review_model, settings.program_review_model)
        self.assertEqual(loaded.request_timeout, 660)
        self.assertEqual(loaded.cline_model, "preserved")

    def test_ui_load_and_current_preserve_unrelated_provider_settings(self) -> None:
        settings = Settings(cline_model="preserved", program_review_model="qwen2.5-coder:7b")
        page = SettingsPage(AppContext(settings), lambda: None)
        self.addCleanup(page.deleteLater)
        self.assertEqual(page.program_review_model.text(), "qwen2.5-coder:7b")
        page.program_review_model.setText("  deepseek-coder:6.7b  ")
        page.timeout.setValue(660)
        current = page.current()
        self.assertEqual(current.program_review_model, "deepseek-coder:6.7b")
        self.assertEqual(current.cline_model, "preserved")
        self.assertEqual(current.request_timeout, 660)
