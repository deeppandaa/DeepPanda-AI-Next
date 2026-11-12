from __future__ import annotations

import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlparse

from PySide6.QtWidgets import QApplication

from desktop.api import ApiError
from desktop.app import MainWindow
from desktop.config import Settings
from desktop.context import AppContext
from desktop.forms import FormWidget
from desktop.page_catalog import CatalogPage
from desktop.page_tools import ToolsPage
from desktop.tool_catalog import TOOLS


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication(["catalog-test", "-platform", "offscreen"])

    def setUp(self) -> None:
        self.ctx = AppContext(Settings(include_vscode_mcp=False))
        self.ctx.navigate = Mock()
        self.ctx.open_url = Mock()
        self.open_plugin = Mock()
        self.page = CatalogPage(self.ctx, self.open_plugin)
        self.addCleanup(self.page.deleteLater)

    def test_all_entries_have_sources_requirements_and_permission_notes(self) -> None:
        self.assertEqual(len(TOOLS), 15)
        self.assertEqual(len({entry.id for entry in TOOLS}), len(TOOLS))
        for entry in TOOLS:
            with self.subTest(entry=entry.id):
                source = urlparse(entry.source)
                self.assertEqual(source.scheme, "https")
                self.assertIn(source.netloc, {"github.com", "docs.docker.com"})
                self.assertTrue(entry.capabilities)
                self.assertTrue(entry.prerequisites)
                self.assertTrue(entry.permissions)
                self.assertIn(entry.page, {"tools", "mcp", "database"})

    def test_catalog_is_usable_offline_without_claiming_tools_are_connected(self) -> None:
        self.assertEqual(self.page.table.rowCount(), 15)
        self.assertIsNone(self.page.plugin_ids)
        for entry in TOOLS:
            self.assertEqual(self.page._entry_status(entry), "Kontrol edilmedi" if entry.plugin else "MCP'de doğrula")

    def test_combined_category_kind_and_capability_search(self) -> None:
        self.page.category.setCurrentIndex(self.page.category.findData("Tarayıcı ve test"))
        self.page.kind.setCurrentIndex(self.page.kind.findData("MCP sunucusu"))
        self.assertEqual({entry.id for entry in self.page.visible_entries}, {"playwright", "chrome-devtools"})
        self.page.search.setText("PERFORMANS")
        self.assertEqual([entry.id for entry in self.page.visible_entries], ["chrome-devtools"])
        self.assertIn("--no-usage-statistics", self.page.details.toPlainText())

    def test_empty_filter_disables_actions_and_recovers(self) -> None:
        self.page.search.setText("no-such-tool")
        self.assertEqual(self.page.table.rowCount(), 0)
        self.assertFalse(self.page.open_button.isEnabled())
        self.assertFalse(self.page.source_button.isEnabled())
        self.assertIn("eşleşen araç yok", self.page.details.toPlainText())
        self.page.search.clear()
        self.assertEqual(self.page.table.rowCount(), 15)
        self.assertTrue(self.page.open_button.isEnabled())

    def test_links_and_navigation_do_not_install_or_run_tools(self) -> None:
        self.page.search.setText("graphify")
        self.assertEqual(self.page.source_button.toolTip(), "https://github.com/safishamsi/graphify")
        self.page.source_button.click()
        self.ctx.open_url.assert_called_once_with("https://github.com/safishamsi/graphify")
        self.page.open_button.click()
        self.open_plugin.assert_called_once_with("graphify")
        self.page.search.setText("Chrome")
        self.page.open_button.click()
        self.ctx.navigate.assert_called_once_with("mcp")
        self.page.search.setText("DeepPanda SQL")
        self.page.open_button.click()
        self.ctx.navigate.assert_called_with("database")

    def test_refresh_checks_plugin_registration_only(self) -> None:
        self.page.search.setText("graphify")
        with patch("desktop.page_catalog.run_background", side_effect=lambda _fn, done, _fail: done([
            {"id": "graphify"}, {"id": "skills"},
        ])):
            self.page.refresh()
        self.assertFalse(self.page.loading)
        self.assertTrue(self.page.refresh_button.isEnabled())
        self.assertIn("API'de kayıtlı", self.page.details.toPlainText())
        self.assertEqual(self.page.selected_entry().id, "graphify")
        self.page.search.setText("OpenJarvis")
        self.assertIn("API'de bulunamadı", self.page.details.toPlainText())
        self.page.search.setText("GitHub")
        self.assertIn("MCP'de doğrula", self.page.details.toPlainText())

    def test_failed_refresh_invalidates_old_status_but_keeps_catalog(self) -> None:
        self.page.plugin_ids = {"skills"}
        with patch("desktop.page_catalog.run_background", side_effect=lambda _fn, _done, fail: fail(ApiError(0, "offline"))):
            self.page.refresh()
        self.assertIsNone(self.page.plugin_ids)
        self.assertEqual(self.page.table.rowCount(), 15)
        self.assertIn("offline", self.page.status.text())
        self.assertEqual(self.page.status.property("kind"), "error")
        self.assertTrue(self.page.refresh_button.isEnabled())

    def test_refresh_does_not_stack_requests(self) -> None:
        with patch("desktop.page_catalog.run_background") as background:
            self.page.activate()
            self.page.refresh()
            self.page.activate()
        self.assertEqual(background.call_count, 1)

    def test_builtin_entries_have_working_forms(self) -> None:
        tools = ToolsPage(self.ctx)
        self.addCleanup(tools.deleteLater)
        for entry in TOOLS:
            if entry.page == "tools":
                with self.subTest(entry=entry.id):
                    self.assertTrue(tools.select_plugin(entry.plugin))
                    self.assertEqual(tools.tree.currentItem().toolTip(0).split(".")[0], entry.plugin)
        self.assertFalse(tools.select_plugin("missing-plugin"))

    def test_existing_forms_still_construct(self) -> None:
        tools = ToolsPage(self.ctx)
        self.addCleanup(tools.deleteLater)
        specs = tools.form_specs()
        from desktop.windows_host import HOST_FORMS
        self.assertEqual(len(specs), 107 + len(HOST_FORMS))
        for spec in specs:
            with self.subTest(plugin=spec["plugin"], action=spec["action"]):
                widget = FormWidget(self.ctx, spec)
                self.assertIsNotNone(widget.run_button)
                widget.deleteLater()

    def test_main_navigation_opens_catalog_and_selected_plugin(self) -> None:
        with (
            patch("desktop.app.QTimer.singleShot"),
            patch("desktop.app.run_background"),
            patch("desktop.page_chat.run_background"),
            patch("desktop.context.run_background"),
            patch("desktop.page_catalog.run_background"),
        ):
            window = MainWindow(self.ctx)
            self.addCleanup(window.deleteLater)
            self.addCleanup(window.close)
            window.health_timer.stop()
            window.navigate("catalog")
            catalog = window.pages["catalog"]
            self.assertIsInstance(catalog, CatalogPage)
            self.assertIs(window.stack.currentWidget(), catalog)
            catalog.search.setText("replica")
            catalog.open_button.click()
            self.assertIs(window.stack.currentWidget(), window.pages["tools"])
            self.assertTrue(window.pages["tools"].tree.currentItem().toolTip(0).startswith("skills."))


if __name__ == "__main__":
    unittest.main()
