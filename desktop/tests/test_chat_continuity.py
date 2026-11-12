from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QListWidgetItem, QTreeWidgetItem

from desktop.chat_continuity import ChatContinuity
from desktop.config import Settings
from desktop.context import AppContext
from desktop.page_chat import ChatPage


class ChatContinuityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.file = self.root / "example.txt"
        self.file.write_text("CONTENT_MUST_NOT_BE_SAVED")
        self.store = ChatContinuity(self.root / "saved")
        self.page = ChatPage(AppContext(Settings(include_vscode_mcp=False)))
        self.page.continuity = self.store
        self.addCleanup(self.page.deleteLater)
        self.server = self.page.ctx.settings.api_url

    def open_session(self, session: str) -> None:
        item = QListWidgetItem(session)
        item.setData(Qt.ItemDataRole.UserRole, session)
        with patch("desktop.page_chat.run_background") as run:
            self.page._open_session(item)
        run.call_args.args[1]({"messages": [
            {"role": "user", "content": "question"}, {"role": "assistant", "content": "answer"},
        ]})

    def test_paths_only_roundtrip_is_scoped_to_api_and_session(self) -> None:
        self.store.save(self.server, "../arbitrary-session", [self.file])
        enabled, paths, warnings = self.store.load(self.server, "../arbitrary-session")
        self.assertTrue(enabled)
        self.assertEqual(paths, [self.file])
        self.assertFalse(warnings)
        record = self.store.location(self.server, "../arbitrary-session")
        self.assertEqual(record.parent, self.store.root)
        self.assertNotIn("CONTENT_MUST_NOT_BE_SAVED", record.read_text())
        self.assertFalse(self.store.load(self.server, "other")[0])
        self.assertFalse(self.store.load("http://other", "../arbitrary-session")[0])

    def test_missing_private_and_invalid_records_are_not_silently_restored(self) -> None:
        self.store.save(self.server, "one", [self.file])
        self.file.unlink()
        enabled, paths, warnings = self.store.load(self.server, "one")
        self.assertTrue(enabled)
        self.assertFalse(paths)
        self.assertTrue(warnings)
        record = self.store.location(self.server, "one")
        record.write_text(json.dumps({"version": 1, "paths": [str(self.root / ".env")]}))
        self.assertTrue(self.store.load(self.server, "one")[2])
        for data in ({"version": 2, "paths": []}, {"version": 1, "paths": ["relative.txt"]}):
            record.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                self.store.load(self.server, "one")

    def test_default_and_refusal_do_not_write_paths(self) -> None:
        self.page.session_id = "one"
        self.page.add_paths([self.file])
        self.assertFalse(self.store.root.exists())
        with patch("desktop.page_chat.confirm", return_value=False):
            self.page.remember_paths.setChecked(True)
        self.assertFalse(self.page.remember_paths.isChecked())
        self.assertFalse(self.store.root.exists())

    def test_optin_restore_forget_and_new_chat_keep_other_session_record(self) -> None:
        self.page.session_id = "one"
        self.page.add_paths([self.file])
        with patch("desktop.page_chat.confirm", return_value=True):
            self.page.remember_paths.setChecked(True)
        self.page.new_chat()
        self.assertFalse(self.page.remember_paths.isChecked())
        self.assertFalse(self.page.attachments)
        self.assertTrue(self.store.load(self.server, "one")[0])
        self.page.tool_context = [{"result": "not-restored"}]
        self.page.trace.addTopLevelItem(QTreeWidgetItem(["old"]))
        self.open_session("one")
        self.assertTrue(self.page.remember_paths.isChecked())
        self.assertEqual(self.page.attachments, [self.file])
        self.assertFalse(self.page.tool_context)
        self.assertEqual(self.page.trace.topLevelItemCount(), 0)
        self.assertEqual(self.page.last_question, "question")
        self.assertEqual(self.page.last_answer, "answer")
        self.page.remember_paths.setChecked(False)
        self.assertFalse(self.store.load(self.server, "one")[0])

    def test_new_session_answer_saves_optin_and_failure_stays_visible(self) -> None:
        self.page.add_paths([self.file])
        with patch("desktop.page_chat.confirm", return_value=True):
            self.page.remember_paths.setChecked(True)
        with patch.object(self.page, "refresh_sessions"):
            self.page._answer({"session_id": "new", "message": {"content": "reply"}})
        self.assertEqual(self.store.load(self.server, "new")[1], [self.file])
        with (
            patch.object(self.store, "save", side_effect=OSError("disk unavailable")),
            patch.object(self.page, "refresh_sessions"),
        ):
            self.page._answer({"session_id": "new", "message": {"content": "reply"}})
        self.assertIn("disk unavailable", self.page.status.text())

    def test_removed_attachment_updates_record_and_busy_disables_optin(self) -> None:
        self.page.session_id = "one"
        self.page.add_paths([self.file])
        with patch("desktop.page_chat.confirm", return_value=True):
            self.page.remember_paths.setChecked(True)
        self.page.attachment_list.setCurrentRow(0)
        self.page.remove_attachment()
        self.assertEqual(self.store.load(self.server, "one")[1], [])
        self.page._set_busy(True)
        self.assertFalse(self.page.remember_paths.isEnabled())

    def test_session_deletion_also_forgets_local_paths(self) -> None:
        self.store.save(self.server, "one", [self.file])
        self.page.session_id = "one"
        item = QListWidgetItem("one")
        item.setData(Qt.ItemDataRole.UserRole, "one")
        self.page.session_list.addItem(item)
        self.page.session_list.setCurrentItem(item)
        with (
            patch("desktop.page_chat.confirm", return_value=True),
            patch("desktop.page_chat.run_background") as run,
            patch.object(self.page, "refresh_sessions"),
        ):
            self.page.delete_session()
            run.call_args.args[1]({"deleted": True})
        self.assertFalse(self.store.load(self.server, "one")[0])
        self.assertIsNone(self.page.session_id)

    def test_corrupt_store_does_not_prevent_conversation_loading_or_hide_error(self) -> None:
        self.store.root.mkdir()
        self.store.location(self.server, "broken").write_text("not json")
        self.open_session("broken")
        self.assertEqual(self.page.session_id, "broken")
        self.assertEqual(self.page.last_answer, "answer")
        self.assertFalse(self.page.attachments)
        self.assertIn("yüklenemedi", self.page.status.text())

    def enable_tools(self) -> None:
        with patch("desktop.page_chat.confirm", return_value=True):
            self.page.remember_tools.setChecked(True)

    def test_tools_default_off_and_refusal_never_save_or_collect_summaries(self) -> None:
        self.page.session_id = "one"
        self.page._show_tool_result({"name": "workspace.read", "status": "completed", "result": "PRIVATE"})
        self.assertFalse(self.page.tool_summaries)
        with patch("desktop.page_chat.confirm", return_value=False):
            self.page.remember_tools.setChecked(True)
        self.assertFalse(self.page.remember_tools.isChecked())
        self.assertFalse(self.store.root.exists())

    def test_tool_summary_roundtrip_never_contains_output_arguments_or_model_context(self) -> None:
        self.page.session_id = "one"
        self.enable_tools()
        self.page._show_tool_result({
            "name": "workspace.read", "status": "completed", "result": {
                "content": "PRIVATE_OUTPUT", "arguments": {"secret": "PRIVATE_ARGUMENT"},
            },
        })
        record = self.store.summary_location(self.server, "one")
        raw = record.read_text()
        self.assertNotIn("PRIVATE_OUTPUT", raw)
        self.assertNotIn("PRIVATE_ARGUMENT", raw)
        self.assertEqual(self.store.load_summaries(self.server, "one")[1], [
            {"name": "workspace.read", "status": "completed"},
        ])
        self.page.new_chat()
        self.assertFalse(self.page.remember_tools.isChecked())
        self.assertFalse(self.page.tool_summaries)
        self.open_session("one")
        self.assertTrue(self.page.remember_tools.isChecked())
        self.assertEqual(self.page.summary_view.topLevelItemCount(), 1)
        self.assertEqual(self.page.tool_context, [])
        self.assertEqual(len(self.page.messages), 2)
        self.assertFalse(self.page.remember_paths.isChecked())
        self.assertFalse(self.store.load_summaries("http://different", "one")[0])
        self.page.remember_tools.setChecked(False)
        self.assertFalse(record.exists())
        self.assertEqual(self.page.summary_view.topLevelItemCount(), 0)

    def test_credentials_are_excluded_and_cap_reports_omitted_count(self) -> None:
        self.page.session_id = "one"
        self.enable_tools()
        for action in ("save_key", "remove_key", "delete_key", "auth", "login"):
            self.page._record_tool_summary(f"api:cloud_providers / cloud_providers.{action}", "completed")
        self.assertFalse(self.page.tool_summaries)
        for index in range(103):
            self.page._record_tool_summary(f"test.tool_{index}", "failed")
        enabled, items, omitted = self.store.load_summaries(self.server, "one")
        self.assertTrue(enabled)
        self.assertEqual(len(items), 100)
        self.assertEqual(omitted, 3)
        self.assertEqual(items[0]["name"], "test.tool_3")
        self.assertIn("3 eski özet", self.page.summary_view.topLevelItem(0).text(0))

    def test_corrupt_and_oversized_summaries_do_not_break_session_or_restore_tools(self) -> None:
        self.store.root.mkdir()
        record = self.store.summary_location(self.server, "one")
        for data in (
            {"version": 1, "items": [{"name": "tool", "status": "completed", "result": "PRIVATE"}], "omitted": 0},
            {"version": 1, "items": [], "omitted": -1},
            {"version": 1, "items": [], "omitted": True},
            {"version": 1, "items": [{"name": "tool", "status": "pending"}], "omitted": 0},
        ):
            record.write_text(json.dumps(data))
            self.open_session("one")
            self.assertFalse(self.page.remember_tools.isChecked())
            self.assertEqual(self.page.tool_context, [])
            self.assertIn("özetleri yüklenemedi", self.page.status.text())
        record.write_text("x" * 128001)
        with self.assertRaises(ValueError):
            self.store.load_summaries(self.server, "one")

    def test_first_completed_turn_saves_pending_summaries_and_errors_remain_visible(self) -> None:
        self.enable_tools()
        self.page._record_tool_summary("workspace.read", "failed")
        self.assertFalse(self.store.root.exists())
        with patch.object(self.page, "refresh_sessions"):
            self.page._answer({"session_id": "new", "message": {"content": "reply"}})
        self.assertEqual(self.store.load_summaries(self.server, "new")[1][0]["status"], "failed")
        with patch.object(self.store, "save_summaries", side_effect=OSError("disk unavailable")):
            self.page._set_busy(True)
            self.page._on_turn_event((self.page._generation, {
                "type": "progress", "message": "done",
                "result": {"name": "test.tool", "status": "completed", "result": "PRIVATE"},
            }))
        self.assertIn("disk unavailable", self.page.status.text())
        self.assertFalse(self.page.remember_tools.isEnabled())

    def test_deletion_attempts_both_local_stores_even_if_path_deletion_fails(self) -> None:
        self.page.session_id = "one"
        self.enable_tools()
        item = QListWidgetItem("one")
        item.setData(Qt.ItemDataRole.UserRole, "one")
        self.page.session_list.addItem(item)
        self.page.session_list.setCurrentItem(item)
        with (
            patch("desktop.page_chat.confirm", return_value=True),
            patch("desktop.page_chat.run_background") as run,
            patch.object(self.page, "refresh_sessions"),
            patch.object(self.store, "forget", side_effect=OSError("path cleanup failed")),
        ):
            self.page.delete_session()
            run.call_args.args[1]({"deleted": True})
        self.assertFalse(self.store.load_summaries(self.server, "one")[0])
        self.assertIsNone(self.page.session_id)
        self.assertIn("path cleanup failed", self.page.status.text())

    def test_summary_and_path_consent_are_independent(self) -> None:
        self.page.session_id = "one"
        self.page.add_paths([self.file])
        with patch("desktop.page_chat.confirm", return_value=True):
            self.page.remember_paths.setChecked(True)
        self.enable_tools()
        self.page._record_tool_summary("workspace.read", "completed")
        self.page.remember_paths.setChecked(False)
        self.assertTrue(self.store.load_summaries(self.server, "one")[0])
        with patch("desktop.page_chat.confirm", return_value=True):
            self.page.remember_paths.setChecked(True)
        self.page.remember_tools.setChecked(False)
        self.assertTrue(self.store.load(self.server, "one")[0])
        self.assertTrue(self.file.exists())

    def test_failed_manual_package_is_displayed_and_retained_as_failed(self) -> None:
        self.page.session_id = "one"
        self.enable_tools()
        self.page._capture_tool_result("windows_host", "project_package", {
            "status": "failed", "packaged": False, "stderr": "PRIVATE_BUILD_OUTPUT",
        })
        self.assertEqual(self.page.tool_context[0]["status"], "failed")
        self.assertIn("başarısız", self.page.status.text())
        summaries = self.store.load_summaries(self.server, "one")[1]
        self.assertEqual(summaries, [{"name": "windows_host.project_package", "status": "failed"}])
        self.assertNotIn("PRIVATE_BUILD_OUTPUT", self.store.summary_location(self.server, "one").read_text())

    def test_completed_events_survive_later_cancel_and_save_error_is_not_hidden(self) -> None:
        from desktop.chat_agent import ChatCancelled

        self.page.session_id = "one"
        self.enable_tools()
        self.page._record_tool_summary("workspace.read", "completed")
        with patch.object(self.page, "refresh_sessions"):
            self.page._failed(ChatCancelled())
        self.assertEqual(self.store.load_summaries(self.server, "one")[1][0]["status"], "completed")
        with (
            patch.object(self.store, "save_summaries", side_effect=OSError("disk unavailable")),
            patch.object(self.page, "refresh_sessions"),
        ):
            self.page._record_tool_summary("workspace.write", "failed")
            self.page._failed(ChatCancelled())
        self.assertIn("disk unavailable", self.page.status.text())
