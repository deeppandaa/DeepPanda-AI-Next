from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtWidgets import QApplication

from desktop.config import Settings
from desktop.context import AppContext
from desktop.page_system import SystemPage


class LocalToolsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication(["local-tools-test", "-platform", "offscreen"])

    def setUp(self) -> None:
        self.settings = Settings(include_vscode_mcp=False)
        self.ctx = AppContext(self.settings)
        self.ctx.run_command = Mock()
        self.page = SystemPage(self.ctx)
        self.addCleanup(self.page.deleteLater)

    def test_project_and_generated_config_are_both_loaded_without_user_config(self) -> None:
        root = Path(self.settings.project_dir)
        self.assertEqual(self.settings.mcp_config_paths(), [
            root / "mcp-servers.json", root / ".tools" / "mcp-servers.json",
        ])

    def test_user_supplied_config_remains_last_in_precedence(self) -> None:
        self.settings.extra_mcp_configs = os.pathsep.join(("one.json", "two.json"))
        self.assertEqual(self.settings.mcp_config_paths()[-2:], [Path("one.json"), Path("two.json")])

    def test_install_requires_one_confirmation_and_uses_project_script(self) -> None:
        with patch("desktop.page_system.confirm", return_value=True) as confirm:
            self.page.install_local_tools()
        confirm.assert_called_once()
        command = self.ctx.run_command.call_args.args[0]
        self.assertEqual(command, [
            "powershell.exe", "-NoProfile", "-NonInteractive", "-File",
            str(Path(self.settings.project_dir) / "setup-tools.ps1"),
        ])
        self.ctx.run_command.assert_called_once()

    def test_declined_install_does_not_run_any_command(self) -> None:
        with patch("desktop.page_system.confirm", return_value=False):
            self.page.install_local_tools()
        self.ctx.run_command.assert_not_called()

    def test_verification_does_not_reinstall_packages(self) -> None:
        with patch("desktop.page_system.confirm", return_value=True):
            self.page.verify_local_tools()
        self.assertEqual(self.ctx.run_command.call_args.args[0][-1], "-VerifyOnly")

    def test_failed_setup_is_explicit_in_log_and_status(self) -> None:
        with patch("desktop.page_system.confirm", return_value=True):
            self.page.install_local_tools()
        done = self.ctx.run_command.call_args.args[1]
        done({"ok": False, "code": 1, "output": "checksum mismatch"})
        self.assertEqual(self.page.status.property("kind"), "error")
        self.assertIn("checksum mismatch", self.page.log.toPlainText())


if __name__ == "__main__":
    unittest.main()
