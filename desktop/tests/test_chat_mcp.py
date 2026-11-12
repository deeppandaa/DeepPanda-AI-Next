from __future__ import annotations

import asyncio
import ctypes
import json
import os
import sys
import threading
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import anyio
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QListWidgetItem

from desktop.api import ApiClient, ApiError
from desktop.app import MainWindow
from desktop.chat_agent import ChatAgent
from desktop.chat_context import ChatCancelled
from desktop.chat_mcp import ChatMcpRuntime
from desktop.config import Settings
from desktop.context import AppContext
from desktop.page_chat import ChatPage


class LiveMcpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = ChatMcpRuntime()
        self.addCleanup(self.runtime.close)
        self.entry = {
            "command": sys.executable,
            "args": ["-B", "-u", str(Path(__file__).with_name("mcp_state_fixture.py"))],
        }

    def agent_turn(self, value: str, *, runtime=None, approve=True, slow=False, entry=None, emit=None, cancel=None):
        api = Mock(spec=ApiClient)
        api.plugins.return_value = []
        api.stream_chat.return_value = {"message": {"content": "done"}, "tools_used": []}
        api.plan_tool.side_effect = [
            {"tool": "mcp:fixture", "arguments": {}, "reason": "first"},
            {"tool": "remember", "arguments": {"value": value, "slow": slow}, "reason": "requested"},
            {"tool": None, "arguments": {}, "reason": "done"},
        ]
        approval = Mock(return_value=approve)
        agent = ChatAgent(
            api, Settings(include_vscode_mcp=False), cancel or threading.Event(), emit or (lambda _: None),
            approval, mcp_runtime=runtime,
        )
        agent._servers = Mock(return_value={"fixture": entry or self.entry})
        result = agent.run(
            message="Remember", model=None, workflow="standard", session_id="test",
            paths=[], mode="agent", tool_results=[], context_cloud_approved=False,
        )
        return result, approval

    @staticmethod
    def evidence(events):
        results = [e["result"]["result"] for e in events if "result" in e]
        return [r["structured"] or json.loads(r["content"][0]["text"]) for r in results]

    def assert_process_exited(self, pid):
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.OpenProcess(0x00100000, False, pid)
        if handle:
            try:
                self.assertEqual(kernel.WaitForSingleObject(handle, 5000), 0)
            finally:
                kernel.CloseHandle(handle)

    def test_owner_task_survives_turns_and_closes_anyio_scopes_on_same_task(self) -> None:
        owners = []
        closed = []

        async def first(state):
            owners.append(asyncio.current_task())
            await state.stack.enter_async_context(anyio.create_task_group())
            state.stack.push_async_callback(on_close)
            state.sessions["fixture"] = (object(), [], {})
            return []

        async def second(state):
            owners.append(asyncio.current_task())
            self.assertIn("fixture", state.sessions)
            return []

        async def on_close():
            self.assertIs(asyncio.current_task(), owners[0])
            closed.append(True)

        self.runtime.run(first)
        self.runtime.run(second)
        self.assertIs(owners[0], owners[1])
        self.assertEqual(closed, [])
        self.runtime.close()
        self.assertEqual(closed, [True])
        self.assertTrue(self.runtime.closed.is_set())
        with self.assertRaises(OSError):
            self.runtime.run(first)

    @unittest.skipUnless(os.name == "nt", "Windows process exit check")
    def test_real_stdio_state_survives_two_agents_but_not_another_chat_and_process_exits(self) -> None:
        events = []
        first, approval_one = self.agent_turn("one", runtime=self.runtime, emit=events.append)
        second, approval_two = self.agent_turn("two", runtime=self.runtime, emit=events.append)
        one = first["tools_used"][0]
        self.assertEqual(one["status"], "completed")
        result, _ = self.agent_turn("three", runtime=self.runtime)
        self.assertEqual(result["tools_used"][0]["status"], "completed")
        approval_one.assert_called_once()
        approval_two.assert_called_once()
        self.assertEqual(second["tools_used"][0]["status"], "completed")

        async def inspect(state):
            return [{"count": len(state.sessions)}]
        self.assertEqual(self.runtime.run(inspect), [{"count": 1}])
        evidence = self.evidence(events)
        self.assertEqual([item["count"] for item in evidence], [1, 2])
        self.assertEqual(evidence[0]["pid"], evidence[1]["pid"])
        self.runtime.close()
        self.assert_process_exited(evidence[0]["pid"])
        fresh = ChatMcpRuntime()
        try:
            events = []
            self.agent_turn("new chat", runtime=fresh, emit=events.append)
            evidence = self.evidence(events)
            self.assertEqual(evidence[-1]["count"], 1)
            pid = evidence[-1]["pid"]
        finally:
            fresh.close()
        self.assert_process_exited(pid)

    def test_real_default_still_opens_fresh_session_each_turn(self) -> None:
        for value in ("one", "two"):
            events = []
            self.agent_turn(value, emit=events.append)
            evidence = self.evidence(events)
            self.assertEqual(evidence[-1]["count"], 1)
        self.assertIsNone(self.runtime._thread)

    def test_actual_retained_state_and_config_change_do_not_silently_restart(self) -> None:
        events = []
        self.agent_turn("one", runtime=self.runtime, emit=events.append)
        self.agent_turn("two", runtime=self.runtime, emit=events.append)
        evidence = self.evidence(events)
        self.assertEqual([item["count"] for item in evidence], [1, 2])
        self.assertEqual(evidence[0]["pid"], evidence[1]["pid"])
        with self.assertRaisesRegex(ValueError, "yapılandırması değişti"):
            self.agent_turn("three", runtime=self.runtime, entry={**self.entry, "env": {"FIXTURE_MARKER": "changed"}})
        events.clear()
        self.agent_turn("fresh after explicit new turn", runtime=self.runtime, emit=events.append)
        evidence = self.evidence(events)
        self.assertEqual(evidence[-1]["count"], 1)

    def test_rejection_executes_no_tool_and_releases_retained_connections(self) -> None:
        self.agent_turn("one", runtime=self.runtime)
        with patch("desktop.chat_agent.mcp_bridge.session_call_tool", new_callable=AsyncMock) as call:
            result, approval = self.agent_turn("no", runtime=self.runtime, approve=False)
        call.assert_not_called()
        approval.assert_called_once()
        self.assertEqual(result["tools_used"][0]["status"], "failed")

        async def inspect(state):
            return [{"count": len(state.sessions)}]
        self.assertEqual(self.runtime.run(inspect), [{"count": 0}])

    def test_real_inflight_cancellation_releases_owner_contexts_without_retry(self) -> None:
        cancelled = threading.Event()
        self.agent_turn("one", runtime=self.runtime)

        def approval(_title, _arguments):
            threading.Timer(0.3, cancelled.set).start()
            return True

        api = Mock(spec=ApiClient)
        api.plugins.return_value = []
        api.plan_tool.side_effect = [
            {"tool": "mcp:fixture"},
            {"tool": "remember", "arguments": {"value": "slow", "slow": True}},
        ]
        agent = ChatAgent(
            api, Settings(include_vscode_mcp=False), cancelled, lambda _: None, approval,
            mcp_runtime=self.runtime,
        )
        agent._servers = Mock(return_value={"fixture": self.entry})
        with self.assertRaises(ChatCancelled):
            agent._tools("slow", None, "", [], [])
        api.stream_chat.assert_not_called()
        self.runtime.close()
        self.assertTrue(self.runtime.closed.is_set())

    def test_idle_expiry_is_bounded_and_next_turn_requires_reenable(self) -> None:
        async def empty(_state):
            return []
        with patch("desktop.chat_mcp.IDLE_SECONDS", 0.05):
            self.runtime.run(empty)
            self.assertTrue(self.runtime.closed.wait(2))
        with self.assertRaisesRegex(OSError, "yeniden onaylayın"):
            self.runtime.run(empty)

    @unittest.skipUnless(os.name == "nt", "Windows process exit check")
    def test_idle_expiry_closes_actual_stdio_process(self) -> None:
        events = []
        with patch("desktop.chat_mcp.IDLE_SECONDS", 0.1):
            self.agent_turn("idle", runtime=self.runtime, emit=events.append)
            self.assertTrue(self.runtime.closed.wait(10))
        self.assert_process_exited(self.evidence(events)[-1]["pid"])

    def test_owner_errors_are_reported_and_contexts_reset(self) -> None:
        closed = []

        @asynccontextmanager
        async def context():
            try:
                yield
            finally:
                closed.append(True)

        async def failed(state):
            await state.stack.enter_async_context(context())
            raise ApiError(502, "fixture transport failure")
        with self.assertRaises(ApiError):
            self.runtime.run(failed)
        self.assertEqual(closed, [True])

    def test_retained_server_limit_blocks_fifth_without_opening_it(self) -> None:
        async def seed(state):
            state.sessions.update({str(index): (object(), [], {}) for index in range(4)})
            return []
        self.runtime.run(seed)
        with patch("desktop.chat_agent.mcp_bridge.open_session", new_callable=AsyncMock) as opened:
            result, _ = self.agent_turn("fifth", runtime=self.runtime)
        opened.assert_not_called()
        self.assertEqual(result["tools_used"][0]["status"], "failed")

    def test_failed_tool_is_not_replayed_and_next_turn_gets_fresh_state(self) -> None:
        self.agent_turn("one", runtime=self.runtime)
        with patch("desktop.chat_agent.mcp_bridge.session_call_tool", new_callable=AsyncMock, return_value={
            "is_error": True, "content": [{"text": "fixture failure"}],
        }) as call:
            result, _ = self.agent_turn("failed", runtime=self.runtime)
        call.assert_awaited_once()
        self.assertEqual(result["tools_used"][0]["status"], "failed")
        events = []
        self.agent_turn("new explicit request", runtime=self.runtime, emit=events.append)
        self.assertEqual(self.evidence(events)[-1]["count"], 1)

    def test_real_transport_disconnect_is_reported_without_replaying_call(self) -> None:
        runtime = ChatMcpRuntime()
        try:
            self.agent_turn("one", runtime=runtime)
            events = []
            try:
                result, approval = self.agent_turn("disconnect-fixture", runtime=runtime, emit=events.append)
            except OSError:
                self.assertTrue(runtime.closed.wait(2))
            else:
                self.assertEqual(result["tools_used"][0]["status"], "failed")
                approval.assert_called_once()
            started = [e for e in events if "arguments" in e]
            self.assertEqual(len(started), 1)
        finally:
            if runtime._error is not None:
                with self.assertRaises(OSError):
                    runtime.close()
            else:
                runtime.close()

    def test_ask_mode_does_not_start_live_runtime(self) -> None:
        api = Mock(spec=ApiClient)
        api.stream_chat.return_value = {"message": {"content": "answer"}}
        agent = ChatAgent(
            api, Settings(), threading.Event(), lambda _: None, Mock(), mcp_runtime=self.runtime,
        )
        agent.run(
            message="question", model=None, workflow="standard", session_id=None,
            paths=[], mode="ask", tool_results=[], context_cloud_approved=False,
        )
        self.assertIsNone(self.runtime._thread)
        api.plan_tool.assert_not_called()


class LiveMcpUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.page = ChatPage(AppContext(Settings(include_vscode_mcp=False)))
        self.addCleanup(self.page.deleteLater)

    def enable(self) -> ChatMcpRuntime:
        with patch("desktop.page_chat.confirm", return_value=True):
            self.page.keep_mcp.setChecked(True)
        runtime = self.page.mcp_runtime
        self.assertIsNotNone(runtime)
        self.addCleanup(runtime.close)
        return runtime

    def finish_close(self, run) -> None:
        args = run.call_args.args
        result = args[0]()
        args[1](result)

    def test_default_refusal_and_enable_never_start_server_or_persist_preference(self) -> None:
        self.assertFalse(self.page.keep_mcp.isChecked())
        self.assertIsNone(self.page.mcp_runtime)
        with patch("desktop.page_chat.confirm", return_value=False):
            self.page.keep_mcp.setChecked(True)
        self.assertFalse(self.page.keep_mcp.isChecked())
        runtime = self.enable()
        self.assertIsNone(runtime._thread)
        self.assertFalse(self.page.remember_paths.isChecked())
        self.assertFalse(self.page.remember_tools.isChecked())
        self.page._set_busy(True)
        self.assertFalse(self.page.keep_mcp.isEnabled())
        self.page._set_busy(False)

    def test_optout_and_new_chat_wait_for_close_before_reusing_ui(self) -> None:
        for operation in (lambda: self.page.keep_mcp.setChecked(False), self.page.new_chat):
            runtime = self.enable()
            with patch("desktop.page_chat.run_background") as run:
                operation()
            self.assertTrue(self.page.busy)
            self.assertIs(self.page.mcp_runtime, runtime)
            self.finish_close(run)
            self.assertTrue(runtime.closed.is_set())
            self.assertFalse(self.page.keep_mcp.isChecked())
            self.assertIsNone(self.page.mcp_runtime)
            self.assertFalse(self.page.busy)

    def test_open_session_closes_old_runtime_before_loading_messages(self) -> None:
        runtime = self.enable()
        item = QListWidgetItem("other")
        with patch("desktop.page_chat.run_background") as run:
            self.page._open_session(item)
            close = run.call_args.args
            close[1](close[0]())
            self.assertTrue(runtime.closed.is_set())
            self.assertIsNone(self.page.mcp_runtime)
            self.assertFalse(self.page.keep_mcp.isChecked())
            self.assertNotEqual(run.call_args.args[0], close[0])

    def test_cancelled_turn_releases_runtime_then_reports_cancel(self) -> None:
        runtime = self.enable()
        with patch("desktop.page_chat.run_background") as run:
            self.page._failed(ChatCancelled())
        with patch.object(self.page, "refresh_sessions"):
            self.finish_close(run)
        self.assertTrue(runtime.closed.is_set())
        self.assertFalse(self.page.busy)
        self.assertIn("durduruldu", self.page.status.text())

    def test_deleting_active_chat_releases_runtime_before_clearing_it(self) -> None:
        runtime = self.enable()
        self.page.session_id = "selected"
        item = QListWidgetItem("selected")
        item.setData(Qt.ItemDataRole.UserRole, "selected")
        self.page.session_list.addItem(item)
        self.page.session_list.setCurrentItem(item)
        self.page.continuity = Mock()
        with (
            patch("desktop.page_chat.confirm", return_value=True),
            patch("desktop.page_chat.run_background") as run,
            patch.object(self.page, "refresh_sessions"),
        ):
            self.page.delete_session()
            run.call_args.args[1]({"deleted": True})
            self.assertTrue(self.page.busy)
            self.finish_close(run)
        self.assertIsNone(self.page.session_id)
        self.assertTrue(runtime.closed.is_set())
        self.assertFalse(self.page.keep_mcp.isChecked())

    def test_api_change_releases_connections_without_sending_message(self) -> None:
        runtime = self.enable()
        self.page.ctx.settings.api_url = "http://different.invalid"
        self.page.input.setPlainText("message")
        with patch("desktop.page_chat.run_background") as run:
            self.page.send()
        self.assertTrue(self.page.busy)
        self.assertEqual(self.page.input.toPlainText(), "message")
        self.finish_close(run)
        self.assertTrue(runtime.closed.is_set())
        self.assertFalse(self.page.messages)

    def test_close_failure_is_visible_and_blocks_session_transition(self) -> None:
        runtime = self.enable()
        with patch("desktop.page_chat.run_background") as run:
            self.page.new_chat()
        run.call_args.args[2](OSError("fixture close failure"))
        self.assertIs(self.page.mcp_runtime, runtime)
        self.assertIn("fixture close failure", self.page.status.text())
        self.assertFalse(self.page.busy)
        self.assertTrue(self.page.keep_mcp.isChecked())
        with patch("desktop.page_chat.confirm") as confirm:
            self.page._keep_mcp_changed(True)
        confirm.assert_not_called()
        self.assertIs(self.page.mcp_runtime, runtime)

    def test_window_close_waits_for_live_connections_and_completes_after_cleanup(self) -> None:
        with patch("desktop.app.ChatPage.activate"), patch.object(MainWindow, "check_health"):
            window = MainWindow(AppContext(Settings(include_vscode_mcp=False)))
        self.addCleanup(window.deleteLater)
        chat = window.pages["chat"]
        runtime = ChatMcpRuntime()
        self.addCleanup(runtime.close)
        chat.mcp_runtime = runtime
        event = Mock()
        with patch("desktop.page_chat.run_background") as run:
            window.closeEvent(event)
        event.ignore.assert_called_once()
        self.assertTrue(chat.busy)
        self.finish_close(run)
        self.assertTrue(runtime.closed.is_set())
        self.assertIsNone(chat.mcp_runtime)
