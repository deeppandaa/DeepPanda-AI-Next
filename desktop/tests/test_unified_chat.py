from __future__ import annotations

import asyncio
import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path
from threading import Event, Thread
from unittest.mock import AsyncMock, Mock, patch

import anyio
import httpx
from jsonschema import Draft202012Validator
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QListWidgetItem

from desktop.api import ApiClient, ApiError
from desktop.app import MainWindow
from desktop.chat_agent import (
    ChatAgent,
    api_tool_definitions,
    compact_result,
    form_schema,
    mcp_tool_definitions,
    tool_pages,
    validate_model_arguments,
)
from desktop.chat_context import (
    MAX_CONTEXT_CHARS,
    ChatCancelled,
    bounded_context,
    collect_attachments,
    validate_attachment_path,
)
from desktop.config import Settings
from desktop.context import AppContext
from desktop.forms import DRAFT, load_groups
from desktop.host_commands import API_LOGS, COMPOSE_STATUS
from desktop.page_chat import ChatPage
from desktop.windows_host import HOST_FORMS


class AttachmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_folder_routes_content_without_reading_private_runtime_or_environment(self) -> None:
        (self.root / "source.py").write_text("answer = 42", encoding="utf-8")
        (self.root / ".env.example").write_text("EXAMPLE=yes", encoding="utf-8")
        (self.root / ".freellmapi.env").write_text("PRIVATE", encoding="utf-8")
        (self.root / "data").mkdir()
        (self.root / "data" / "backup.json").write_text("PRIVATE", encoding="utf-8")
        bundle = collect_attachments([self.root], Event())
        self.assertEqual({item["filename"] for item in bundle.files}, {"source.py", ".env.example"})
        self.assertTrue(bundle.warnings)
        self.assertNotIn("PRIVATE", "\n".join(base64.b64decode(item["content_base64"]).decode() for item in bundle.files))

    def test_explicit_secret_path_is_rejected(self) -> None:
        path = self.root / ".ai-next-cloud.env"
        path.write_text("PRIVATE", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Gizli"):
            validate_attachment_path(path)

    def test_size_limits_are_checked_before_read_and_folder_omissions_are_visible(self) -> None:
        path = self.root / "large.txt"
        path.write_bytes(b"0123456789")
        with patch("desktop.chat_context.MAX_FILE_BYTES", 5):
            with self.assertRaises(ValueError):
                collect_attachments([path], Event())
            (self.root / "small.txt").write_text("ok", encoding="utf-8")
            bundle = collect_attachments([self.root], Event())
        self.assertEqual(len(bundle.files), 1)
        self.assertTrue(any("large.txt" in item for item in bundle.warnings))

    def test_cancelled_scan_does_not_read_files(self) -> None:
        stop = Event()
        stop.set()
        with self.assertRaises(ChatCancelled):
            collect_attachments([self.root], stop)

    def test_duplicate_inputs_are_not_uploaded_twice_and_context_truncation_is_explicit(self) -> None:
        path = self.root / "source.py"
        path.write_text("x = 1", encoding="utf-8")
        bundle = collect_attachments([path, self.root], Event())
        self.assertEqual(len(bundle.files), 1)
        context = bounded_context(["x" * (MAX_CONTEXT_CHARS + 100)])
        self.assertEqual(len(context), MAX_CONTEXT_CHARS)
        self.assertIn("kesildi", context)

    def test_linked_path_is_rejected_before_reading(self) -> None:
        path = self.root / "link.txt"
        path.write_text("x", encoding="utf-8")
        with (
            patch("desktop.chat_context._linked", return_value=True),
            self.assertRaisesRegex(ValueError, "junction"),
        ):
            validate_attachment_path(path)


class AgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.api = Mock(spec=ApiClient)
        self.api.plugins.return_value = [{
            "id": "workspace", "name": "Workspace", "description": "Workspace files",
            "actions": ["read", "write"],
        }]
        self.api.stream_chat.return_value = {"message": {"content": "done"}, "tools_used": []}
        self.events: list[dict] = []
        self.approve = Mock(return_value=False)
        self.agent = ChatAgent(
            self.api, Settings(include_vscode_mcp=False), Event(), self.events.append, self.approve,
        )
        self.server_patch = patch.object(self.agent, "_servers", return_value={})
        self.mock_servers = self.server_patch.start()
        self.addCleanup(self.server_patch.stop)

    def run_agent(self, mode: str = "agent") -> dict:
        return self.agent.run(
            message="read a file", model=None, workflow="standard", session_id="existing",
            paths=[], mode=mode, tool_results=[], context_cloud_approved=False,
        )

    def plans(self, action: str, arguments: dict) -> None:
        self.api.plan_tool.side_effect = [
            {"tool": "api:workspace", "arguments": {}, "reason": "files"},
            {"tool": f"workspace.{action}", "arguments": arguments, "reason": "requested"},
            {"tool": None, "arguments": {}, "reason": "done"},
        ]

    def test_read_only_tool_result_reaches_chat_without_approval(self) -> None:
        self.plans("read", {"path": "README.md"})
        self.api.action.return_value = {"content": "real evidence"}
        result = self.run_agent()
        self.approve.assert_not_called()
        self.api.action.assert_called_once_with("workspace", "read", {"path": "README.md"})
        payload = self.api.stream_chat.call_args.args[0]
        self.assertEqual(payload["tool_results"][0]["result"]["content"], "real evidence")
        self.assertEqual(result["tools_used"][0]["status"], "completed")

    def test_web_hardware_tool_is_read_only_and_result_reaches_chat(self) -> None:
        self.api.plugins.return_value = [{
            "id": "system", "name": "System", "description": "System", "actions": ["hardware"],
        }]
        self.api.plan_tool.side_effect = [
            {"tool": "api:system", "arguments": {}, "reason": "hardware"},
            {"tool": "system.hardware", "arguments": {}, "reason": "requested"},
            {"tool": None, "arguments": {}, "reason": "done"},
        ]
        self.api.action.return_value = {"cpu_count": 8}
        self.run_agent()
        self.approve.assert_not_called()
        self.api.action.assert_called_once_with("system", "hardware", {})
        self.assertEqual(self.api.stream_chat.call_args.args[0]["tool_results"][0]["result"]["cpu_count"], 8)
        definitions = api_tool_definitions(self.api.plugins.return_value[0])
        self.assertIn("API çalışma ortamının CPU/RAM/GPU", definitions[0]["description"])

    def test_qt_system_status_uses_only_the_fixed_host_command(self) -> None:
        self.api.plan_tool.side_effect = [
            {"tool": "desktop:system", "arguments": {}, "reason": "status"},
            {"tool": "desktop_system.compose_status", "arguments": {}, "reason": "status"},
            {"tool": None, "arguments": {}, "reason": "done"},
        ]
        with patch("desktop.chat_agent.run_host_command", return_value={"ok": True, "code": 0, "output": "running"}) as run:
            self.run_agent()
        run.assert_called_once_with(list(COMPOSE_STATUS), self.agent.settings.project_dir)
        self.approve.assert_not_called()
        result = self.api.stream_chat.call_args.args[0]["tool_results"][0]
        self.assertEqual(result["result"]["output"], "running")

    def test_qt_system_logs_require_approval_and_never_accept_arbitrary_commands(self) -> None:
        with patch("desktop.chat_agent.run_host_command") as run:
            with self.assertRaisesRegex(ApiError, "onaylanmadı"):
                self.agent._desktop_action("desktop_system.api_logs", {})
            run.assert_not_called()
            self.approve.return_value = True
            run.return_value = {"ok": True, "code": 0, "output": "logs"}
            self.assertEqual(self.agent._desktop_action("desktop_system.api_logs", {})["output"], "logs")
            run.assert_called_once_with(list(API_LOGS), self.agent.settings.project_dir)
            with self.assertRaises(ValueError):
                self.agent._desktop_action("desktop_system.api_logs", {"command": ["arbitrary"]})
            with self.assertRaises(ValueError):
                self.agent._desktop_action("desktop_system.delete_everything", {})
            run.return_value = {"ok": False, "code": 1, "output": "Docker unavailable"}
            with self.assertRaisesRegex(ApiError, "Docker unavailable"):
                self.agent._desktop_action("desktop_system.compose_status", {})

    def test_qt_draft_is_discovered_and_dispatched_without_creating_a_task(self) -> None:
        self.api.plugins.return_value = [{
            "id": "tasks", "name": "Tasks", "description": "Tasks", "actions": ["create", "list"],
        }]
        self.api.plan_tool.side_effect = [
            {"tool": "api:tasks", "arguments": {}, "reason": "plan"},
            {"tool": "tasks.draft", "arguments": {"request": "Testleri planla"}, "reason": "draft"},
            {"tool": None, "arguments": {}, "reason": "done"},
        ]
        self.api.draft_task.return_value = {"steps": ["Testleri incele"]}
        self.run_agent()
        self.api.draft_task.assert_called_once_with("Testleri planla", None)
        self.api.action.assert_not_called()
        self.approve.assert_not_called()
        self.assertEqual(self.api.stream_chat.call_args.args[0]["tool_results"][0]["result"]["steps"], ["Testleri incele"])
        group = self.api.plan_tool.call_args_list[0].args[1][0]
        self.assertIn("draft:", group["description"])
        with self.assertRaisesRegex(ValueError, "yerel"):
            self.agent._api_action("tasks", "draft", {"request": "test", "model": "qwen:cloud"}, [])

    def test_qt_database_and_job_pages_have_real_argument_schemas(self) -> None:
        database = api_tool_definitions({
            "id": "database", "actions": ["overview", "tables", "query", "check", "backup"],
        })
        query = next(tool for tool in database if tool["name"] == "database.query")["parameters"]
        validator = Draft202012Validator(query)
        self.assertTrue(validator.is_valid({"database": "example.db", "sql": "SELECT 1", "limit": 1}))
        self.assertFalse(validator.is_valid({"db_name": "example.db", "sql": "SELECT 1"}))
        jobs = api_tool_definitions({"id": "jobs", "actions": ["list", "get", "cancel", "retry", "recover_stale"]})
        get_schema = next(tool for tool in jobs if tool["name"] == "jobs.get")["parameters"]
        self.assertFalse(Draft202012Validator(get_schema).is_valid({}))
        self.assertTrue(Draft202012Validator(get_schema).is_valid({"job_id": "a" * 32}))

    def test_every_visible_form_has_a_matching_planner_schema_or_secret_is_excluded(self) -> None:
        for group in load_groups():
            for form in group["forms"]:
                plugin = "tasks" if form["plugin"] == DRAFT else form["plugin"]
                action = form["action"]
                definitions = api_tool_definitions({"id": plugin, "actions": [] if plugin == "tasks" and action == "draft" else [action]})
                matching = [tool for tool in definitions if tool["name"] == f"{plugin}.{action}"]
                is_secret = any(field.get("type") == "password" and field.get("required") for field in form.get("fields", []))
                with self.subTest(tool=f"{plugin}.{action}"):
                    if is_secret:
                        self.assertEqual(matching, [])
                    else:
                        self.assertEqual(len(matching), 1)
                        self.assertEqual(matching[0]["parameters"], form_schema(form))

    def test_internal_actions_without_schemas_are_not_offered(self) -> None:
        definitions = api_tool_definitions({"id": "jobs", "actions": ["complete", "claim", "get"]})
        self.assertEqual([tool["name"] for tool in definitions], ["jobs.get"])

    def test_explicit_model_download_requires_approval(self) -> None:
        with self.assertRaisesRegex(ApiError, "onaylanmadı"):
            self.agent._api_action("ollama", "pull", {"model": "qwen2.5-coder:7b"}, [])
        self.api.action.assert_not_called()
        self.approve.return_value = True
        self.agent._api_action("ollama", "pull", {"model": "qwen2.5-coder:7b"}, [])
        self.api.action.assert_called_once_with("ollama", "pull", {"model": "qwen2.5-coder:7b", "approved": True})

    def test_web_memory_import_uses_only_the_chosen_file_and_requires_approval(self) -> None:
        backup = {"format": "deep-panda-memory-v1", "memories": [{"title": "Note", "content": "text"}], "approved": False}
        files = [{
            "filename": "memory.json", "label": "memory.json",
            "content_base64": base64.b64encode(json.dumps(backup).encode()).decode(),
        }]
        with self.assertRaisesRegex(ApiError, "onaylanmadı"):
            self.agent._api_action("memory", "import", {"attachment_index": 0}, files)
        self.api.action.assert_not_called()
        self.approve.return_value = True
        self.api.action.return_value = {"imported": 1}
        self.assertEqual(self.agent._api_action("memory", "import", {"attachment_index": 0}, files), {"imported": 1})
        self.api.action.assert_called_once_with("memory", "import", {**backup, "approved": True})
        preview = self.approve.call_args.args[1]
        self.assertEqual(preview["memory_count"], 1)
        self.assertNotIn("memories", preview)
        with self.assertRaisesRegex(ValueError, "seçtiği"):
            self.agent._api_action("memory", "import", {"attachment_index": 2}, files)

    def test_password_form_is_not_offered_to_the_model(self) -> None:
        definitions = api_tool_definitions({
            "id": "cloud_providers", "actions": ["save_key", "catalog"],
        })
        self.assertEqual([tool["name"] for tool in definitions], ["cloud_providers.catalog"])

    def test_selected_file_is_attached_to_the_actual_approved_web_tool(self) -> None:
        self.approve.return_value = True
        files = [{"filename": "image.png", "content_base64": "aW1hZ2U=", "label": "image.png"}]
        self.api.action.return_value = {"text": "found"}
        self.agent._api_action("ocr", "extract", {"attachment_index": 0, "language": "tur"}, files)
        self.api.action.assert_called_once_with("ocr", "extract", {
            "filename": "image.png", "content_base64": "aW1hZ2U=", "language": "tur", "approved": True,
        })
        with self.assertRaisesRegex(ValueError, "seçmediği"):
            self.agent._api_action("ocr", "extract", {"attachment_index": 1}, files)

    def test_tool_results_remain_in_planner_context_when_attachment_context_is_large(self) -> None:
        self.plans("read", {"path": "README.md"})
        self.api.action.return_value = {"content": "unique tool evidence"}
        self.agent._tools("read a file", None, "x" * MAX_CONTEXT_CHARS, [], [])
        second_group_context = self.api.plan_tool.call_args_list[-1].args[2]
        self.assertIn("unique tool evidence", second_group_context)
        self.assertIn("kesildi", second_group_context)

    def test_write_never_runs_when_approval_is_rejected(self) -> None:
        self.plans("write", {"path": "example.py", "content": "changed"})
        self.api.action.return_value = {"diff": "+changed", "expected_sha256": None}
        result = self.run_agent()
        self.api.action.assert_called_once_with("workspace", "preview_write", {"path": "example.py", "content": "changed"})
        self.approve.assert_called_once()
        self.assertEqual(result["tools_used"][0]["status"], "failed")

    def test_explicit_windows_target_cannot_be_substituted_with_workspace_path(self) -> None:
        cases = [
            (r"C:\Users\emre\Desktop\DeepPanda_Ajan_Test\toplama.py", "toplama.py"),
            ("c:/Users/My Test/Demo.PY", "demo.py"),
            (r"C:\Users\emre\Desktop\reports\today.py", "reports/today.py"),
        ]
        for requested, proposed in cases:
            with self.subTest(requested=requested, proposed=proposed):
                self.api.reset_mock()
                self.approve.reset_mock()
                self.approve.return_value = True
                self.plans("write", {"path": proposed, "content": "changed"})
                self.api.action.side_effect = [
                    {"diff": "+changed", "expected_sha256": None}, {"written": True},
                ]
                result = self.agent.run(
                    message=f"Windows masaüstündeki {requested} dosyasını oluştur.",
                    model=None, workflow="standard", session_id="existing", paths=[],
                    mode="agent", tool_results=[], context_cloud_approved=False,
                )
                self.api.action.assert_not_called()
                self.approve.assert_not_called()
                self.assertEqual(result["tools_used"][0]["status"], "failed")
                error = self.api.stream_chat.call_args.args[0]["tool_results"][0]["result"]["error"]
                self.assertIn("Windows", error)
                self.assertIn("workspace", error)

    def test_windows_path_in_request_does_not_block_unrelated_workspace_file(self) -> None:
        self.plans("write", {"path": "example.py", "content": "changed"})
        self.approve.return_value = True
        self.api.action.side_effect = [
            {"diff": "+changed", "expected_sha256": None}, {"written": True},
        ]
        result = self.agent.run(
            message=r"Workspace example.py dosyasını oluştur; kaynak C:\data\notes.txt.",
            model=None, workflow="standard", session_id="existing", paths=[],
            mode="agent", tool_results=[], context_cloud_approved=False,
        )
        self.assertEqual(result["tools_used"][0]["status"], "completed")
        self.assertEqual(self.api.action.call_count, 2)

    def test_windows_path_with_longer_filename_does_not_match_workspace_target(self) -> None:
        self.plans("write", {"path": "example.py", "content": "changed"})
        self.approve.return_value = True
        self.api.action.side_effect = [
            {"diff": "+changed", "expected_sha256": None}, {"written": True},
        ]
        result = self.agent.run(
            message=r"Workspace example.py dosyasını oluştur; kaynak C:\data\example.py.bak.",
            model=None, workflow="standard", session_id="existing", paths=[],
            mode="agent", tool_results=[], context_cloud_approved=False,
        )
        self.assertEqual(result["tools_used"][0]["status"], "completed")
        self.assertEqual(self.api.action.call_count, 2)

    def test_approval_is_scoped_to_the_actual_call(self) -> None:
        self.plans("write", {"path": "example.py", "content": "changed"})
        self.approve.return_value = True
        self.api.action.side_effect = [
            {"diff": "+changed", "expected_sha256": None},
            {"status": "written"},
        ]
        self.run_agent()
        self.assertEqual(self.api.action.call_count, 2)
        self.api.action.assert_called_with(
            "workspace", "write", {"path": "example.py", "content": "changed", "expected_sha256": None, "approved": True},
        )
        self.assertIn("diff", self.approve.call_args.args[1])

    def test_workspace_file_is_not_rewritten_in_the_same_agent_turn(self) -> None:
        self.api.plan_tool.side_effect = [
            {"tool": "api:workspace", "arguments": {}, "reason": "first"},
            {"tool": "workspace.write", "arguments": {"path": "src/example.py", "content": "first"}, "reason": "first"},
            {"tool": "api:workspace", "arguments": {}, "reason": "second"},
            {"tool": "workspace.write", "arguments": {"path": "src/./example.py", "content": "second"}, "reason": "second"},
            {"tool": None, "arguments": {}, "reason": "done"},
        ]
        self.approve.return_value = True
        self.api.action.side_effect = [
            {"diff": "+first", "expected_sha256": None}, {"written": True},
            {"diff": "+second", "expected_sha256": None}, {"written": True},
        ]
        self.run_agent()
        self.assertEqual(self.api.action.call_count, 2)
        self.approve.assert_called_once()
        self.assertTrue(any("tekrar yazılmadı" in event.get("message", "") for event in self.events))

    def test_windows_host_file_is_not_rewritten_in_the_same_agent_turn(self) -> None:
        self.api.plugins.return_value = [{
            "id": "windows_host", "name": "Windows host", "description": "Windows files",
            "actions": ["file_write"],
        }]
        self.api.plan_tool.side_effect = [
            {"tool": "api:windows_host", "arguments": {}, "reason": "first"},
            {"tool": "windows_host.file_write", "arguments": {"path": r"C:\Users\Example\file.py", "content": "first"}, "reason": "first"},
            {"tool": "api:windows_host", "arguments": {}, "reason": "second"},
            {"tool": "windows_host.file_write", "arguments": {"path": "c:/users/example/file.py", "content": "second"}, "reason": "second"},
            {"tool": None, "arguments": {}, "reason": "done"},
        ]
        self.approve.return_value = True
        self.api.action.side_effect = [
            {"plan_id": "first"}, {"status": "completed"},
            {"plan_id": "second"}, {"status": "completed"},
        ]
        self.run_agent()
        self.assertEqual(self.api.action.call_count, 2)
        self.approve.assert_called_once()
        self.assertTrue(any("tekrar yazılmadı" in event.get("message", "") for event in self.events))

    def test_distinct_workspace_files_can_be_written_in_one_turn(self) -> None:
        self.api.plan_tool.side_effect = [
            {"tool": "api:workspace", "arguments": {}, "reason": "first"},
            {"tool": "workspace.write", "arguments": {"path": "one.py", "content": "first"}, "reason": "first"},
            {"tool": "api:workspace", "arguments": {}, "reason": "second"},
            {"tool": "workspace.write", "arguments": {"path": "two.py", "content": "second"}, "reason": "second"},
            {"tool": None, "arguments": {}, "reason": "done"},
        ]
        self.approve.return_value = True
        self.api.action.side_effect = [
            {"diff": "+first", "expected_sha256": None}, {"written": True},
            {"diff": "+second", "expected_sha256": None}, {"written": True},
        ]
        self.run_agent()
        self.assertEqual(self.api.action.call_count, 4)
        self.assertEqual(self.approve.call_count, 2)

    def test_workspace_file_can_be_rewritten_in_a_new_agent_turn(self) -> None:
        self.api.plan_tool.side_effect = [
            {"tool": "api:workspace", "arguments": {}, "reason": "first"},
            {"tool": "workspace.write", "arguments": {"path": "one.py", "content": "first"}, "reason": "first"},
            {"tool": None, "arguments": {}, "reason": "done"},
            {"tool": "api:workspace", "arguments": {}, "reason": "second"},
            {"tool": "workspace.write", "arguments": {"path": "one.py", "content": "second"}, "reason": "second"},
            {"tool": None, "arguments": {}, "reason": "done"},
        ]
        self.approve.return_value = True
        self.api.action.side_effect = [
            {"diff": "+first", "expected_sha256": None}, {"written": True},
            {"diff": "+second", "expected_sha256": "a" * 64}, {"written": True},
        ]
        self.run_agent()
        self.run_agent()
        self.assertEqual(self.api.action.call_count, 4)
        self.assertEqual(self.approve.call_count, 2)

    def test_model_cannot_supply_approval_or_file_bytes(self) -> None:
        for key in ("approved", "content_base64"):
            with self.subTest(key=key):
                self.plans("write", {key: True})
                with self.assertRaises(ValueError):
                    self.run_agent()
        self.api.action.assert_not_called()
        for arguments in ({"nested": {"approved": True}}, {"items": [{"content_base64": "forged"}]}):
            with self.assertRaisesRegex(ValueError, "onayını"):
                validate_model_arguments(arguments)

    def test_ask_and_plan_do_not_call_agent_tools(self) -> None:
        for mode in ("ask", "plan"):
            self.run_agent(mode)
        self.api.plugins.assert_not_called()
        self.api.plan_tool.assert_not_called()
        self.assertEqual(self.api.stream_chat.call_args.args[0]["workflow"], "plan")

    def test_cancellation_after_planning_prevents_another_request(self) -> None:
        def cancel_plan(*_args):
            self.agent.cancelled.set()
            return {"tool": "api:workspace", "arguments": {}, "reason": "files"}

        self.api.plan_tool.side_effect = cancel_plan
        with self.assertRaises(ChatCancelled):
            self.run_agent()
        self.api.plan_tool.assert_called_once()
        self.api.action.assert_not_called()
        self.api.stream_chat.assert_not_called()

    def test_attachment_identity_does_not_change_filename_or_hide_actual_tools(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / "Dockerfile"
            path.write_text("FROM scratch", encoding="utf-8")
            self.api.analyze_attachments.return_value = {
                "context": "FROM scratch", "results": [{
                    "filename": "Dockerfile", "label": "00-Dockerfile",
                    "tool": "text.preview", "status": "completed", "summary": "FROM scratch",
                }],
            }
            reply = self.agent.run(
                message="explain", model=None, workflow="standard", session_id=None,
                paths=[path], mode="ask", tool_results=[], context_cloud_approved=False,
            )
        upload = self.api.analyze_attachments.call_args.args[0][0]
        self.assertEqual(upload["filename"], "Dockerfile")
        self.assertEqual(upload["label"], "00-Dockerfile")
        self.assertEqual(reply["tools_used"][0]["name"], "text.preview")
        event = next(event for event in self.events if isinstance(event.get("result"), dict))
        self.assertEqual(event["result"]["status"], "completed")
        self.assertIn("text.preview", event["result"]["name"])
        self.assertEqual(event["result"]["result"]["summary"], "FROM scratch")

    def test_eight_escaped_results_fit_the_real_backend_contract(self) -> None:
        from app.chat_context import ChatContextRequest

        results = [
            {"name": "x" * 200, "status": "completed", "result": compact_result({"data": "\\\"" * 20_000})}
            for _ in range(8)
        ]
        request = ChatContextRequest(tool_results=results)
        self.assertEqual(len(request.tool_results), 8)
        self.assertLessEqual(len(json.dumps(results, ensure_ascii=False)), 48_000)
        self.assertTrue(all(item["result"]["truncated"] for item in results))

    def test_oversized_results_fail_before_streaming(self) -> None:
        with self.assertRaisesRegex(ValueError, "48.000"):
            self.agent.run(
                message="question", model=None, workflow="standard", session_id=None,
                paths=[], mode="ask", context_cloud_approved=False,
                tool_results=[{"name": "tool", "status": "completed", "result": "x" * 49_000}],
            )
        self.api.stream_chat.assert_not_called()

    def test_tool_error_is_recorded_and_not_retried(self) -> None:
        self.plans("read", {"path": "missing.py"})
        self.api.action.side_effect = ApiError(404, "not found")
        self.run_agent()
        self.assertEqual(self.api.action.call_count, 1)
        result = self.api.stream_chat.call_args.args[0]["tool_results"][0]
        self.assertEqual(result["status"], "failed")
        self.assertIn("not found", result["result"]["error"])

    def test_mcp_steps_share_one_session_and_close_it_in_the_owning_task(self) -> None:
        self.mock_servers.return_value = {"thinking": {"command": sys.executable}}
        self.approve.return_value = True
        self.api.plan_tool.side_effect = [
            {"tool": "mcp:thinking", "arguments": {}, "reason": "first"},
            {"tool": "think", "arguments": {"thought": "one"}, "reason": "first"},
            {"tool": "mcp:thinking", "arguments": {}, "reason": "second"},
            {"tool": "think", "arguments": {"thought": "two"}, "reason": "second"},
            {"tool": None, "arguments": {}, "reason": "done"},
        ]
        history: list[str] = []
        closed: list[bool] = []
        session = object()

        async def open_session(stack, _entry):
            owner = asyncio.current_task()
            await stack.enter_async_context(anyio.create_task_group())

            async def close():
                self.assertIs(asyncio.current_task(), owner)
                closed.append(True)
            stack.push_async_callback(close)
            return session

        async def session_call(actual_session, _tool, arguments):
            self.assertIs(actual_session, session)
            history.append(arguments["thought"])
            return {"is_error": False, "structured": {"history_length": len(history)}}

        with (
            patch("desktop.chat_agent.mcp_bridge.open_session", side_effect=open_session) as opened,
            patch("desktop.chat_agent.mcp_bridge.session_tools", new_callable=AsyncMock, return_value=[{
                "name": "think", "description": "Reason", "input_schema": {
                    "type": "object", "properties": {"thought": {"type": "string"}}, "required": ["thought"],
                },
            }]) as listed,
            patch("desktop.chat_agent.mcp_bridge.session_call_tool", side_effect=session_call) as called,
        ):
            self.run_agent()
        self.assertEqual(opened.call_count, 1)
        self.assertEqual(listed.call_count, 1)
        self.assertEqual(called.call_count, 2)
        self.assertEqual(self.approve.call_count, 2)
        self.assertEqual(history, ["one", "two"])
        self.assertEqual(closed, [True])
        results = self.api.stream_chat.call_args.args[0]["tool_results"]
        self.assertEqual([item["result"]["structured"]["history_length"] for item in results], [1, 2])

    def test_switching_mcp_servers_preserves_each_session_and_closes_in_reverse_order(self) -> None:
        self.mock_servers.return_value = {
            "first": {"command": sys.executable, "server_id": "first"},
            "second": {"command": sys.executable, "server_id": "second"},
        }
        self.approve.return_value = True
        self.api.plan_tool.side_effect = [
            {"tool": "mcp:first", "arguments": {}, "reason": "one"},
            {"tool": "think", "arguments": {"thought": "one"}, "reason": "one"},
            {"tool": "mcp:second", "arguments": {}, "reason": "two"},
            {"tool": "think", "arguments": {"thought": "two"}, "reason": "two"},
            {"tool": "mcp:first", "arguments": {}, "reason": "three"},
            {"tool": "think", "arguments": {"thought": "three"}, "reason": "three"},
        ]
        histories = {"first": [], "second": []}
        closed: list[str] = []

        async def open_session(stack, entry):
            owner = asyncio.current_task()
            await stack.enter_async_context(anyio.create_task_group())
            server = entry["server_id"]

            async def close():
                self.assertIs(asyncio.current_task(), owner)
                closed.append(server)
            stack.push_async_callback(close)
            return server

        async def call(server, _tool, arguments):
            histories[server].append(arguments["thought"])
            return {"is_error": False, "structured": {"count": len(histories[server])}}

        with (
            patch("desktop.chat_agent.mcp_bridge.open_session", side_effect=open_session) as opened,
            patch("desktop.chat_agent.mcp_bridge.session_tools", new_callable=AsyncMock, return_value=[{
                "name": "think", "input_schema": {"type": "object"},
            }]),
            patch("desktop.chat_agent.mcp_bridge.session_call_tool", side_effect=call),
        ):
            self.run_agent()
        self.assertEqual(opened.call_count, 2)
        self.assertEqual(histories, {"first": ["one", "three"], "second": ["two"]})
        self.assertEqual(closed, ["second", "first"])
        results = self.api.stream_chat.call_args.args[0]["tool_results"]
        self.assertEqual([item["result"]["structured"]["count"] for item in results], [1, 1, 2])

    def test_mcp_rejection_and_connection_failures_are_reported_without_execution(self) -> None:
        self.mock_servers.return_value = {"thinking": {"command": sys.executable}}
        self.api.plan_tool.side_effect = [
            {"tool": "mcp:thinking", "arguments": {}, "reason": "reason"},
            {"tool": "think", "arguments": {}, "reason": "reason"},
        ]
        with (
            patch("desktop.chat_agent.mcp_bridge.open_session", new_callable=AsyncMock, return_value=object()),
            patch("desktop.chat_agent.mcp_bridge.session_tools", new_callable=AsyncMock, return_value=[{
                "name": "think", "input_schema": {"type": "object"},
            }]),
            patch("desktop.chat_agent.mcp_bridge.session_call_tool", new_callable=AsyncMock) as called,
        ):
            self.run_agent()
        called.assert_not_called()
        self.assertEqual(self.api.stream_chat.call_args.args[0]["tool_results"][0]["status"], "failed")

        from mcp.shared.exceptions import McpError
        from mcp.types import ErrorData

        self.api.plan_tool.side_effect = [{"tool": "mcp:thinking", "arguments": {}, "reason": "reason"}]
        failure = ExceptionGroup("transport", [ExceptionGroup("nested", [McpError(ErrorData(
            code=-32000, message="connection closed",
        ))])])
        with patch("desktop.chat_agent.mcp_bridge.open_session", new_callable=AsyncMock, side_effect=failure):
            self.run_agent()
        result = self.api.stream_chat.call_args.args[0]["tool_results"][0]
        self.assertEqual(result["status"], "failed")
        self.assertIn("connection closed", result["result"]["error"])

    def test_mcp_cancel_closes_the_session_in_the_owning_task(self) -> None:
        self.mock_servers.return_value = {"thinking": {"command": sys.executable}}
        self.approve.return_value = True
        self.api.plan_tool.side_effect = [
            {"tool": "mcp:thinking", "arguments": {}, "reason": "reason"},
            {"tool": "think", "arguments": {}, "reason": "reason"},
        ]
        closed: list[bool] = []

        async def open_session(stack, _entry):
            owner = asyncio.current_task()
            await stack.enter_async_context(anyio.create_task_group())

            async def close():
                self.assertIs(asyncio.current_task(), owner)
                closed.append(True)
            stack.push_async_callback(close)
            return object()

        async def blocking_call(*_args):
            self.agent.cancelled.set()
            await asyncio.sleep(10)

        with (
            patch("desktop.chat_agent.mcp_bridge.open_session", side_effect=open_session),
            patch("desktop.chat_agent.mcp_bridge.session_tools", new_callable=AsyncMock, return_value=[{
                "name": "think", "input_schema": {"type": "object"},
            }]),
            patch("desktop.chat_agent.mcp_bridge.session_call_tool", side_effect=blocking_call),
            self.assertRaises(ChatCancelled),
        ):
            self.run_agent()
        self.assertEqual(closed, [True])
        self.api.stream_chat.assert_not_called()

    def test_cancellation_waits_for_a_running_synchronous_action(self) -> None:
        self.plans("read", {"path": "README.md"})
        started, release = Event(), Event()
        errors: list[Exception] = []

        def action(*_args):
            started.set()
            self.assertTrue(release.wait(5))
            return {"content": "finished"}

        def run():
            try:
                self.run_agent()
            except ChatCancelled as exc:
                errors.append(exc)

        self.api.action.side_effect = action
        worker = Thread(target=run)
        worker.start()
        self.assertTrue(started.wait(5))
        self.agent.cancelled.set()
        worker.join(timeout=0.2)
        self.assertTrue(worker.is_alive())
        release.set()
        worker.join(timeout=5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(errors), 1)

    def test_large_mcp_catalog_is_paged_without_losing_tools_or_colliding_aliases(self) -> None:
        from app.chat_planning import ToolPlanRequest

        discovered = [{
            "name": f"tool_{index:03d}", "description": f"Capability {index}",
            "input_schema": {"type": "object", "properties": {}},
        } for index in range(229)]
        discovered.extend([
            {"name": "mcp_tool_229", "input_schema": {"type": "object"}},
            {"name": "tool@special", "input_schema": {"type": "object"}},
            {"name": "unusable", "input_schema": {"$ref": "https://example.invalid/schema"}},
        ])
        definitions, originals, invalid = mcp_tool_definitions(discovered)
        self.assertEqual(len(definitions), 231)
        self.assertEqual(len(invalid), 1)
        self.assertEqual(len(set(originals)), len(originals))
        special_alias = next(alias for alias, original in originals.items() if original == "tool@special")
        self.assertNotEqual(special_alias, "mcp_tool_229")
        pages = tool_pages(definitions, "tool")
        self.assertGreater(len(pages), 1)
        self.assertEqual({definition["name"] for page in pages for definition in page}, set(originals))
        for page in pages:
            ToolPlanRequest(message="test", tools=page)
            self.assertLessEqual(len(page), 64)

    def test_large_mcp_page_selection_can_execute_an_original_aliased_name(self) -> None:
        self.mock_servers.return_value = {"rea@local": {"command": sys.executable}}
        self.approve.return_value = True
        discovered = [{
            "name": f"tool_{index:03d}", "description": f"Capability {index}",
            "input_schema": {"type": "object", "properties": {}},
        } for index in range(150)] + [{
            "name": "special@target", "description": "Special target", "input_schema": {"type": "object"},
        }]
        definitions, originals, _invalid = mcp_tool_definitions(discovered)
        target = next(alias for alias, original in originals.items() if original == "special@target")

        def plan(_message, tools, _context, _model):
            names = [tool["name"] for tool in tools]
            if names[0].startswith("api:"):
                return {"tool": "mcp:server_0" if self.api.action.call_count == 0 else None,
                        "arguments": {}, "reason": "group"}
            if names[0].startswith("page:"):
                page = next(tool for tool in tools if target in tool["description"])
                return {"tool": page["name"], "arguments": {}, "reason": "page"}
            return {"tool": target, "arguments": {}, "reason": "target"}

        self.api.plan_tool.side_effect = plan

        async def call(_session, name, _arguments):
            self.assertEqual(name, "special@target")
            self.api.action()
            return {"is_error": False, "content": [{"text": "success"}]}

        with (
            patch("desktop.chat_agent.mcp_bridge.open_session", new_callable=AsyncMock, return_value=object()),
            patch("desktop.chat_agent.mcp_bridge.session_tools", new_callable=AsyncMock, return_value=discovered),
            patch("desktop.chat_agent.mcp_bridge.session_call_tool", side_effect=call),
        ):
            self.run_agent()
        result = self.api.stream_chat.call_args.args[0]["tool_results"][0]
        self.assertEqual(result["status"], "completed")
        self.assertIn("special@target", result["name"])
        self.assertGreater(len(tool_pages(definitions, "read a file")), 1)

    def test_all_existing_forms_provide_model_schemas_without_approval_or_passwords(self) -> None:
        for group in load_groups():
            for form in group["forms"]:
                with self.subTest(tool=f"{form['plugin']}.{form['action']}"):
                    schema = form_schema(form)
                    self.assertNotIn("approved", schema["properties"])
                    self.assertNotIn("content_base64", schema["properties"])
                    for field in form.get("fields", []):
                        if field.get("type") == "password":
                            self.assertNotIn(field["name"], schema["properties"])
        self.assertEqual(len(api_tool_definitions(self.api.plugins.return_value[0])), 2)

    def test_form_schemas_preserve_json_lines_and_input_constraints(self) -> None:
        schema = form_schema({"fields": [
            {"name": "report", "type": "json"},
            {"name": "sources", "type": "lines", "required": True, "maxLines": 2, "maxLineLength": 5},
            {"name": "language", "pattern": "[A-Za-z]+", "required": True},
        ]})
        validator = Draft202012Validator(schema)
        self.assertTrue(validator.is_valid({"report": [1, "two"], "sources": ["a"], "language": "tr"}))
        self.assertFalse(validator.is_valid({"sources": ["a", "b", "c"], "language": "tr"}))
        self.assertFalse(validator.is_valid({"sources": ["a"], "language": "tr-TR"}))


class StreamingClientTests(unittest.TestCase):
    def test_real_events_are_delivered_and_final_result_is_returned(self) -> None:
        events = [
            {"type": "progress", "message": "working"}, {"type": "token", "content": "Hello"},
            {"type": "result", "result": {"message": {"content": "Hello"}}},
        ]
        transport = httpx.MockTransport(lambda _request: httpx.Response(
            200, text="\n".join(json.dumps(item) for item in events),
        ))
        client = ApiClient("http://test")
        emitted: list[dict] = []
        connection = httpx.Client(transport=transport, base_url="http://test")
        self.addCleanup(connection.close)
        with patch("desktop.api.httpx.Client", return_value=connection):
            result = client.stream_chat({"message": "hello"}, Event(), emitted.append)
        self.assertEqual(result["message"]["content"], "Hello")
        self.assertEqual([item["type"] for item in emitted], ["progress", "token"])

    def test_stop_and_incomplete_stream_are_not_success_results(self) -> None:
        for stop_after_token in (True, False):
            stop = Event()
            transport = httpx.MockTransport(lambda _request: httpx.Response(
                200, text='{"type":"token","content":"part"}\n{"type":"heartbeat"}\n',
            ))
            connection = httpx.Client(transport=transport, base_url="http://test")
            self.addCleanup(connection.close)
            expected = ChatCancelled if stop_after_token else ApiError
            with patch("desktop.api.httpx.Client", return_value=connection), self.assertRaises(expected):
                ApiClient("http://test").stream_chat(
                    {}, stop,
                    lambda _event, event=stop, should_stop=stop_after_token: event.set() if should_stop else None,
                )

    def test_stream_error_keeps_http_status_and_auth_body(self) -> None:
        event = {"type": "error", "status": 401, "detail": "login", "body": {"auth": {"provider": "example"}}}
        transport = httpx.MockTransport(lambda _request: httpx.Response(200, text=json.dumps(event)))
        connection = httpx.Client(transport=transport, base_url="http://test")
        self.addCleanup(connection.close)
        with patch("desktop.api.httpx.Client", return_value=connection), self.assertRaises(ApiError) as raised:
            ApiClient("http://test").stream_chat({}, Event(), lambda _event: None)
        self.assertEqual(raised.exception.status, 401)
        self.assertEqual(raised.exception.body["auth"]["provider"], "example")


class UnifiedChatUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication(["unified-chat-tests", "-platform", "offscreen"])

    def setUp(self) -> None:
        self.ctx = AppContext(Settings(include_vscode_mcp=False))
        self.page = ChatPage(self.ctx)
        self.addCleanup(self.page.deleteLater)

    def test_unified_tools_panel_keeps_every_existing_form(self) -> None:
        self.assertEqual(len(self.page.tools_page.form_specs()), 107 + len(HOST_FORMS))
        self.assertEqual(self.page.tool_panel.count(), 2)
        self.assertEqual(self.page.agent_mode.currentData(), "agent")

    def test_tools_results_become_explicit_next_turn_context(self) -> None:
        self.page._capture_tool_result("workspace", "read", {"content": "actual"})
        self.assertEqual(self.page.tool_context[0]["result"]["content"], "actual")
        self.assertIn("actual", self.page.transcript.toPlainText())
        self.page._capture_tool_result("cloud_providers", "save_key", {"secret": "never include"})
        self.assertEqual(len(self.page.tool_context), 1)

    def test_automatic_tool_results_and_failures_are_shown_in_the_conversation(self) -> None:
        self.page._set_busy(True)
        for status, value in (("completed", "actual result"), ("failed", "tool failure")):
            self.page._on_turn_event((self.page._generation, {
                "type": "progress", "message": "tool", "result": {
                    "name": "api:system / system.hardware", "status": status, "result": {"value": value},
                },
            }))
        self.assertIn("actual result", self.page.transcript.toPlainText())
        self.assertIn("tool failure", self.page.transcript.toPlainText())
        self.assertEqual(len([message for message in self.page.messages if message["role"] == "tool"]), 2)
        self.assertEqual(self.page.tool_context, [])

    def test_truncated_selected_context_is_visible_after_the_answer(self) -> None:
        with patch.object(self.page, "refresh_sessions"):
            self.page._answer({
                "message": {"content": "answer"},
                "context_used": {"selected_context_truncated": True},
            })
        self.assertIn("bağlam kesildi", self.page.status.text())
        self.assertIn("bağlam kesildi", self.page.messages[-1]["meta"])

    def test_passing_self_tests_show_unverified_requirements_not_green_completion(self) -> None:
        with patch.object(self.page, "refresh_sessions"):
            self.page._answer({
                "message": {"content": "All done"},
                "program_verification": {"tests_passed": True, "requirements_status": "not_verified"},
            })
        self.assertIn("gereksinimler henüz bağımsız doğrulanmadı", self.page.status.text())
        self.assertEqual(self.page.status.property("kind"), "warn")
        with patch.object(self.page, "refresh_sessions"):
            self.page._answer({
                "message": {"content": "All done"},
                "program_verification": {"tests_passed": False, "requirements_status": "not_verified"},
            })
        self.assertIn("başarısız", self.page.status.text())
        self.assertEqual(self.page.status.property("kind"), "error")

    def test_package_failure_is_not_hidden_by_passing_tests(self) -> None:
        with patch.object(self.page, "refresh_sessions"):
            self.page._answer({
                "message": {"content": "All done"},
                "program_verification": {"tests_passed": True},
                "package_verification": {"verified": False},
            })
        self.assertIn("paketleme başarısız", self.page.status.text())
        self.assertEqual(self.page.status.property("kind"), "error")

    def test_active_turn_cannot_switch_session_and_stop_preserves_partial_answer(self) -> None:
        self.page.session_id = "old"
        self.page.cancelled = Event()
        self.page._set_busy(True)
        self.page.new_chat()
        self.assertEqual(self.page.session_id, "old")
        self.page._on_turn_event((self.page._generation, {"type": "token", "content": "partial"}))
        self.page.stop()
        self.assertTrue(self.page.cancelled.is_set())
        with patch("desktop.page_chat.run_background"):
            self.page._failed(ChatCancelled("cancel"))
        self.assertFalse(self.page.busy)
        self.assertIn("partial", self.page.transcript.toPlainText())

    def test_stale_session_load_and_stale_stream_event_do_not_overwrite_new_conversation(self) -> None:
        callbacks = []
        with patch("desktop.page_chat.run_background", side_effect=lambda _fn, done, _fail: callbacks.append(done)):
            item = QListWidgetItem("old")
            from PySide6.QtCore import Qt
            item.setData(Qt.ItemDataRole.UserRole, "old")
            self.page._open_session(item)
        self.page.new_chat()
        callbacks[0]({"messages": [{"role": "user", "content": "stale"}]})
        self.assertEqual(self.page.messages, [])
        self.page._set_busy(True)
        self.page._on_turn_event((self.page._generation - 1, {"type": "token", "content": "stale"}))
        self.assertEqual(self.page._partial_answer, "")

    def test_send_snapshots_context_and_uses_the_cancellable_controller(self) -> None:
        self.page.input.setPlainText("question")
        callbacks = []
        with patch("desktop.page_chat.run_background", side_effect=lambda fn, done, fail: callbacks.append((fn, done, fail))):
            self.page.send()
        self.assertTrue(self.page.busy)
        self.assertFalse(self.page.session_list.isEnabled())
        self.assertTrue(self.page.stop_button.isEnabled())
        with patch("desktop.page_chat.ChatAgent.run", return_value={"message": {"content": "ok"}}) as run:
            callbacks[0][0]()
        self.assertEqual(run.call_args.kwargs["message"], "question")
        self.assertEqual(run.call_args.kwargs["mode"], "agent")

    def test_catalog_evaluation_and_measured_priorities_are_shown(self) -> None:
        self.ctx.api = Mock(spec=ApiClient)
        self.ctx.api.models.return_value = {
            "models": [{"name": "example:7b", "evaluation": {
                "status": "healthy", "description": "Measured coding strength",
                "max_observed_load_seconds": 43.5,
            }}],
            "routing": {"available_priorities": {"answer": ["example:7b"]}},
        }
        self.ctx.api.action.return_value = {"providers": []}
        with patch("desktop.page_chat.run_background", side_effect=lambda fn, done, _fail: done(fn())):
            self.page.refresh_models()
        self.assertIn("Yanıt: example:7b", self.page.model_details.text())
        self.page.model_box.setCurrentIndex(self.page.model_box.findData("example:7b"))
        self.assertIn("Measured coding strength", self.page.model_details.text())
        self.assertIn("43.5", self.page.model_details.text())

    def test_window_close_cancels_then_waits_for_chat_worker(self) -> None:
        with (
            patch("desktop.app.QTimer.singleShot"),
            patch("desktop.app.run_background"),
            patch("desktop.page_chat.run_background"),
        ):
            window = MainWindow(self.ctx)
            self.addCleanup(window.deleteLater)
            chat = window.pages["chat"]
            chat.cancelled = Event()
            chat._set_busy(True)
            event = QCloseEvent()
            window.closeEvent(event)
            self.assertFalse(event.isAccepted())
            self.assertTrue(chat.cancelled.is_set())
            chat._set_busy(False)
            event = QCloseEvent()
            window.closeEvent(event)
            self.assertTrue(event.isAccepted())
