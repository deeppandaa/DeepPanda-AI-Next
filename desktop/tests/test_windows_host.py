from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from threading import Event
from unittest.mock import Mock, patch

from app.plugins.integration_errors import IntegrationUnavailableError
from app.plugins.windows_host import (
    HOST_FORMS,
    HOST_MUTATIONS,
    HOST_PRIVATE_READS,
    WindowsHostPlugin,
)
from PySide6.QtWidgets import QApplication

from desktop.api import ApiClient, ApiError
from desktop.chat_agent import (
    READ_ONLY_ACTIONS,
    ChatAgent,
    api_tool_definitions,
    group_description,
)
from desktop.chat_context import ChatCancelled
from desktop.config import Settings
from desktop.context import AppContext
from desktop.forms import FormWidget
from desktop.windows_api import DesktopApiClient
from desktop.windows_host import HostError, WindowsHost
from desktop.windows_registry import registry_data, registry_snapshot, registry_target


class HostTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.host = WindowsHost(self.root / "state")
        self.path = self.root / "fixture.txt"
        self.path.write_bytes(b"before\n")

    def apply_plan(self, action: str, data: dict) -> dict:
        preview = self.host.preview(action, data)
        return self.host.apply(action, {"plan_id": preview["plan_id"], "approved": True})

    def test_file_preview_is_immutable_and_requires_approval(self) -> None:
        preview = self.host.preview("file_write", {"path": str(self.path), "content": "after\n"})
        self.assertIn("-before", preview["diff"])
        self.assertIn("+after", preview["diff"])
        self.assertEqual(self.path.read_text(), "before\n")
        preview["target"]["path"] = str(self.root / "other.txt")
        with self.assertRaises(HostError):
            self.host.apply("file_write", {"plan_id": preview["plan_id"]})
        result = self.host.apply("file_write", {"plan_id": preview["plan_id"], "approved": True})
        self.assertEqual(self.path.read_text(), "after\n")
        self.assertFalse((self.root / "other.txt").exists())
        self.assertTrue(result["reversible"])
        with self.assertRaises(HostError):
            self.host.apply("file_write", {"plan_id": preview["plan_id"], "approved": True})

    def test_changed_expired_or_forged_target_cannot_be_applied(self) -> None:
        preview = self.host.preview("file_write", {"path": str(self.path), "content": "after"})
        with self.assertRaises(ValueError):
            self.host.apply("file_write", {"plan_id": preview["plan_id"], "approved": True, "path": "other"})
        with self.assertRaises(HostError):
            self.host.apply("file_delete", {"plan_id": preview["plan_id"], "approved": True})
        self.path.write_text("concurrent")
        with self.assertRaisesRegex(HostError, "değişmiş"):
            self.host.apply("file_write", {"plan_id": preview["plan_id"], "approved": True})
        self.host._plans[preview["plan_id"]]["expires"] = 0
        with self.assertRaisesRegex(HostError, "süresi"):
            self.host.apply("file_write", {"plan_id": preview["plan_id"], "approved": True})
        self.assertEqual(self.path.read_text(), "concurrent")

    def test_write_delete_create_and_persistent_rollback(self) -> None:
        for action, content in (("file_write", "after\n"), ("file_delete", None)):
            with self.subTest(action=action):
                args = {"path": str(self.path)}
                if content is not None:
                    args["content"] = content
                result = self.apply_plan(action, args)
                self.host = WindowsHost(self.root / "state")
                self.apply_plan("rollback", {"operation_id": result["operation_id"]})
                self.assertEqual(self.path.read_text(), "before\n")
        new = self.root / "new.txt"
        result = self.apply_plan("file_write", {"path": str(new), "content": ""})
        self.assertEqual(new.read_bytes(), b"")
        self.apply_plan("rollback", {"operation_id": result["operation_id"]})
        self.assertFalse(new.exists())

    def test_create_directory_requires_approval_and_never_replaces_existing_targets(self) -> None:
        target = self.root / "created-directory"
        preview = self.host.preview("directory_create", {"path": str(target)})
        self.assertEqual(preview["before"], {"exists": False})
        self.assertFalse(preview["reversible"])
        self.assertFalse(target.exists())
        preview["target"]["path"] = str(self.root / "other-directory")
        with self.assertRaises(HostError):
            self.host.apply("directory_create", {"plan_id": preview["plan_id"], "approved": False})
        self.assertFalse(target.exists())
        result = self.host.apply("directory_create", {"plan_id": preview["plan_id"], "approved": True})
        self.assertEqual(result["status"], "completed")
        self.assertFalse(result["reversible"])
        self.assertTrue(target.is_dir())
        self.assertEqual(list(target.iterdir()), [])
        self.assertFalse((self.root / "other-directory").exists())
        with self.assertRaises(HostError):
            self.host.apply("directory_create", {"plan_id": preview["plan_id"], "approved": True})
        with self.assertRaises(ValueError):
            self.host.preview("directory_create", {"path": str(target)})
        with self.assertRaises(ValueError):
            self.host.preview("directory_create", {"path": str(self.path)})

    def test_create_directory_rejects_target_changes_and_missing_or_private_parents(self) -> None:
        target = self.root / "concurrent-directory"
        preview = self.host.preview("directory_create", {"path": str(target)})
        target.mkdir()
        with self.assertRaisesRegex(HostError, "değişmiş"):
            self.host.apply("directory_create", {"plan_id": preview["plan_id"], "approved": True})
        self.assertEqual(list(target.iterdir()), [])
        with self.assertRaises((ValueError, OSError)):
            self.host.preview("directory_create", {"path": str(self.root / "missing-parent" / "child")})
        self.assertFalse((self.root / "missing-parent").exists())
        with self.assertRaises(ValueError):
            self.host.preview("directory_create", {"path": str(self.root / ".tools")})
        self.assertFalse((self.root / ".tools").exists())

    def test_create_directory_rejects_linked_parents(self) -> None:
        parent = self.root / "linked-parent"
        parent.mkdir()
        target = parent / "child"
        with (
            patch("desktop.chat_context._linked", side_effect=lambda path: path == parent),
            self.assertRaisesRegex(ValueError, "bağlantı"),
        ):
            self.host.preview("directory_create", {"path": str(target)})
        self.assertFalse(target.exists())

    def test_create_directory_revalidates_parent_and_protected_paths(self) -> None:
        parent = self.root / "parent"
        parent.mkdir()
        target = parent / "child"
        preview = self.host.preview("directory_create", {"path": str(target)})
        with (
            patch("desktop.chat_context._linked", side_effect=lambda path: path == parent),
            self.assertRaisesRegex(ValueError, "bağlantı"),
        ):
            self.host.apply("directory_create", {"plan_id": preview["plan_id"], "approved": True})
        self.assertFalse(target.exists())
        with patch.dict(os.environ, {"SystemRoot": str(parent)}), self.assertRaisesRegex(ValueError, "Windows"):
            self.host.preview("directory_create", {"path": str(target)})

    def test_rollback_does_not_overwrite_later_edits(self) -> None:
        result = self.apply_plan("file_write", {"path": str(self.path), "content": "after"})
        self.path.write_text("new work")
        with self.assertRaisesRegex(HostError, "değişmiş"):
            self.host.preview("rollback", {"operation_id": result["operation_id"]})

    def test_rollback_refuses_journal_changes_after_approval_preview(self) -> None:
        result = self.apply_plan("file_write", {"path": str(self.path), "content": "after"})
        preview = self.host.preview("rollback", {"operation_id": result["operation_id"]})
        self.assertNotIn("base64", preview["before"]["target"])
        record = self.host._record(result["operation_id"])
        record["before"]["sha256"] = "tampered"
        self.host._save(record)
        with self.assertRaisesRegex(HostError, "değişmiş"):
            self.host.apply("rollback", {"plan_id": preview["plan_id"], "approved": True})
        self.assertEqual(self.path.read_text(), "after")

    @unittest.skipUnless(os.name == "nt", "Native isolated HKCU fixture requires Windows")
    def test_registry_live_types_delete_and_missing_key_rollback(self) -> None:
        import winreg
        key = "HKCU\\Software\\DeepPandaHostTest" + uuid.uuid4().hex + "\\Nested"
        target = registry_target(key, "Fixture")
        self.assertFalse(registry_snapshot(target)["key_exists"])
        def cleanup() -> None:
            for path in (key.split("\\", 1)[1], key.split("\\", 1)[1].rpartition("\\")[0]):
                try:
                    winreg.DeleteKeyEx(winreg.HKEY_CURRENT_USER, path, winreg.KEY_WOW64_64KEY)
                except FileNotFoundError:
                    pass
        self.addCleanup(cleanup)
        for kind, text, expected in (
            ("REG_SZ", "  original\n", "  original\n"),
            ("REG_DWORD", "42", 42),
            ("REG_QWORD", "4294967296", 4294967296),
            ("REG_MULTI_SZ", "one\ntwo", ["one", "two"]),
        ):
            with self.subTest(kind=kind):
                result = self.apply_plan("registry_set", {**target, "value_type": kind, "data": text})
                self.assertEqual(registry_snapshot(target)["data"], expected)
                deleted = self.apply_plan("registry_delete", target)
                self.assertFalse(registry_snapshot(target)["exists"])
                self.apply_plan("rollback", {"operation_id": deleted["operation_id"]})
                self.assertEqual(registry_snapshot(target)["data"], expected)
                self.apply_plan("rollback", {"operation_id": result["operation_id"]})
                self.assertFalse(registry_snapshot(target)["key_exists"])

    def test_driver_signature_and_package_change_prevent_install(self) -> None:
        package = self.root / "package"
        package.mkdir()
        inf = package / "fixture.inf"
        cat = package / "fixture.cat"
        inf.write_bytes(b"fixture")
        cat.write_bytes(b"not a signed catalog")
        with patch.object(self.host, "is_admin", return_value=True), patch.object(self.host, "_run") as run:
            preview = self.host.preview("driver_install", {"path": str(inf)})
            cat.write_bytes(b"changed")
            with self.assertRaisesRegex(HostError, "değişmiş"):
                self.host.apply("driver_install", {"plan_id": preview["plan_id"], "approved": True})
            run.assert_not_called()
            preview = self.host.preview("driver_install", {"path": str(inf)})
            with (
                patch.object(self.host, "_ps", return_value=[{"Status": "NotSigned"}]),
                self.assertLogs("desktop.windows_host", level="ERROR"),
                self.assertRaisesRegex(ValueError, "imzası"),
            ):
                self.host.apply("driver_install", {"plan_id": preview["plan_id"], "approved": True})
            run.assert_not_called()
            preview = self.host.preview("driver_install", {"path": str(inf)})
            run.return_value = {"reboot_required": False}
            with patch.object(self.host, "_ps", return_value=[{"Status": "Valid"}]):
                self.host.apply("driver_install", {"plan_id": preview["plan_id"], "approved": True})
            run.assert_called_once_with("pnputil.exe", ["/add-driver", str(inf), "/install"], timeout=180)

    def test_driver_removal_requires_successful_export_first(self) -> None:
        self.host.storage.mkdir()
        for export_ok in (False, True):
            calls = []
            def execute(_executable: str, args: list[str], *, recorded: list[str] = calls, allow_export: bool = export_ok, **_kwargs: object) -> dict:
                recorded.append(args[0])
                if args[0] == "/export-driver":
                    if not allow_export:
                        raise HostError(502, "export failed")
                    (Path(args[2]) / "fixture.inf").write_bytes(b"backup")
                return {"reboot_required": False}
            plan = {"id": uuid.uuid4().hex, "action": "driver_remove", "arguments": {"inf_name": "oem42.inf"}}
            with self.subTest(export_ok=export_ok), patch.object(self.host, "_run", side_effect=execute):
                if export_ok:
                    result = self.host._perform(plan)
                    self.assertTrue(Path(result["driver_backup"]).is_dir())
                    self.assertEqual(calls, ["/export-driver", "/delete-driver"])
                else:
                    with self.assertRaises(HostError):
                        self.host._perform(plan)
                    self.assertEqual(calls, ["/export-driver"])

    def test_private_paths_traversal_and_oversized_content_are_rejected(self) -> None:
        for path in (self.root / ".env", self.root / "key.pem", self.root / ".." / "outside.txt"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.host.preview("file_write", {"path": str(path), "content": "data"})
        with self.assertRaises(ValueError):
            self.host.preview("file_write", {"path": str(self.path), "content": "x" * 1_000_001})
        with self.assertRaises(ValueError):
            self.host.preview("file_delete", {"path": str(self.root)})
        private = self.root / "fixture.env"
        private.write_bytes(b"owned test fixture")
        with self.assertRaises(ValueError):
            self.host.preview("file_delete", {"path": str(private) + "."})
        with self.assertRaises(ValueError):
            self.host.preview("file_write", {"path": str(private) + " ", "content": "not written"})
        self.assertEqual(private.read_bytes(), b"owned test fixture")

    @unittest.skipUnless(os.name == "nt", "Public host dispatch requires Windows")
    def test_host_reads_need_target_specific_approval(self) -> None:
        with self.assertRaises(HostError):
            self.host.invoke("file_read", {"path": str(self.path)})
        result = self.host.invoke("file_read", {"path": str(self.path), "approved": True})
        self.assertEqual(result["content"], "before\n")
        self.assertNotIn(("windows_host", "file_read"), READ_ONLY_ACTIONS)
        self.assertNotIn(("windows_host", "registry_read"), READ_ONLY_ACTIONS)
        self.assertIn(("windows_host", "devices"), READ_ONLY_ACTIONS)

    def test_graphify_read_only_query_matches_actual_plugin_action(self) -> None:
        self.assertIn(("graphify", "query"), READ_ONLY_ACTIONS)
        self.assertNotIn(("graphify", "search"), READ_ONLY_ACTIONS)

    def test_network_is_not_contacted_during_preview_or_without_approval(self) -> None:
        connection = Mock()
        connection.__enter__ = Mock(return_value=connection)
        connection.__exit__ = Mock(return_value=False)
        connection.getpeername.return_value = ("127.0.0.1", 443)
        with patch("desktop.windows_host.socket.create_connection", return_value=connection) as connect:
            preview = self.host.preview("network_check", {"host": "localhost", "port": 443})
            connect.assert_not_called()
            with self.assertRaises(HostError):
                self.host.apply("network_check", {"plan_id": preview["plan_id"], "approved": False})
            connect.assert_not_called()
            result = self.host.apply("network_check", {"plan_id": preview["plan_id"], "approved": True})
            self.assertTrue(result["connected"])
            connect.assert_called_once_with(("localhost", 443), timeout=5)
        with self.assertRaises(ValueError):
            self.host.preview("network_check", {"host": "https://user:password@example.com"})

    def test_critical_devices_and_in_use_drivers_cannot_be_changed(self) -> None:
        for row in ({"PNPClass": "DiskDrive"}, {"PNPClass": "Net"}, {"PNPClass": "USB", "Service": "USBHUB3"}):
            with self.subTest(row=row), patch.object(self.host, "_ps", return_value=[row]), self.assertRaises(ValueError):
                self.host.preview("device_remove", {"instance_id": "USB\\fixture"})
        with patch.object(self.host, "_ps", return_value=[{"DeviceID": "in-use"}]), self.assertRaisesRegex(ValueError, "bağlı"):
            self.host.preview("driver_remove", {"inf_name": "oem42.inf"})

    def test_device_mutation_needs_admin_and_never_uses_force_or_reboot(self) -> None:
        state = {"PNPClass": "Ports", "PNPDeviceID": "USB\\fixture", "ConfigManagerErrorCode": 0}
        with patch.object(self.host, "_ps", return_value=[state]), patch.object(self.host, "_run") as run:
            preview = self.host.preview("device_restart", {"instance_id": "USB\\fixture"})
            with patch.object(self.host, "is_admin", return_value=False), self.assertRaisesRegex(HostError, "yönetici"):
                self.host.apply("device_restart", {"plan_id": preview["plan_id"], "approved": True})
            run.assert_not_called()
            run.return_value = {"reboot_required": False}
            with patch.object(self.host, "is_admin", return_value=True):
                self.host.apply("device_restart", {"plan_id": preview["plan_id"], "approved": True})
            run.assert_called_once_with("pnputil.exe", ["/restart-device", "USB\\fixture"], timeout=120)

    def test_parameter_text_is_stdin_data_not_powershell_code(self) -> None:
        hostile = "'; Write-Host BAD; #"
        with patch.object(self.host, "_run", return_value={"output": "[]", "truncated": False}) as run:
            self.host._ps("devices", {"query": hostile, "limit": 1})
        import base64
        encoded = run.call_args.args[1][-1]
        script = base64.b64decode(encoded).decode("utf-16-le")
        self.assertNotIn(hostile, script)
        self.assertEqual(json.loads(run.call_args.kwargs["data"])["query"], hostile)

    def test_registry_targets_block_system_security_and_persistence_keys(self) -> None:
        for key in (
            r"HKLM\SAM", r"HKLM\SYSTEM\CurrentControlSet", r"HKCU\Software\Classes\CLSID\example",
            r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run", r"HKCU\Software\Vendor\Security",
        ):
            with self.subTest(key=key), self.assertRaises(ValueError):
                registry_target(key, writing=True)
        self.assertEqual(registry_target(r"HKEY_CURRENT_USER\Software\Vendor\App")["key"], r"HKCU\Software\Vendor\App")
        with self.assertRaises(ValueError):
            registry_target(r"HKCU\Software\Vendor\App", "Password")
        if os.name == "nt":
            self.assertEqual(registry_data({"value_type": "REG_DWORD", "data": "0x2a"})["data"], 42)
            with self.assertRaises(ValueError):
                registry_data({"value_type": "REG_DWORD", "data": str(2**32)})
            with self.assertRaises(ValueError):
                registry_data({"value_type": "REG_MULTI_SZ", "data": "one\x00two"})
            with self.assertRaises(ValueError):
                registry_data({"value_type": "REG_MULTI_SZ", "data": "one\n\ntwo"})


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication(["windows-host-tests", "-platform", "offscreen"])

    def test_package_form_does_not_label_failed_result_as_success(self) -> None:
        spec = next(form for form in HOST_FORMS if form["action"] == "project_package")
        form = FormWidget(AppContext(Settings()), {"plugin": "windows_host", **spec})
        self.addCleanup(form.deleteLater)
        with patch.object(form.status, "set") as status:
            form._done({"status": "failed", "packaged": False})
        self.assertEqual(status.call_args.args[1], "error")
        self.assertIn("başarısız", status.call_args.args[0])

    def test_http_plugin_never_performs_windows_actions(self) -> None:
        plugin = WindowsHostPlugin()
        self.assertFalse(asyncio.run(plugin.invoke("status", {}))["available"])
        for action in plugin.manifest.actions:
            if action != "status":
                with self.subTest(action=action), self.assertRaises(IntegrationUnavailableError):
                    asyncio.run(plugin.invoke(action, {"approved": True}))

    def test_normal_entry_point_imports_without_backend_pythonpath(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-c", "import desktop.app"],
            cwd=Path(__file__).resolve().parents[2],
            env={key: value for key, value in os.environ.items() if key != "PYTHONPATH"},
            capture_output=True, text=True, timeout=30, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_desktop_client_does_not_send_host_payload_to_http(self) -> None:
        client = DesktopApiClient("http://test")
        with patch.object(client.windows_host, "invoke", return_value={"available": True}) as invoke, patch.object(ApiClient, "action") as http:
            client.action("windows_host", "status", {})
            invoke.assert_called_once_with("status", {})
            http.assert_not_called()
            client.action("workspace", "list", {})
            http.assert_called_once()

    def test_agent_passes_its_cancel_event_to_local_python_execution_only(self) -> None:
        client = DesktopApiClient("http://test")
        cancelled = Event()
        agent = ChatAgent(client, Settings(), cancelled, lambda _: None, Mock(return_value=True))
        with (
            patch.object(client, "action", return_value={"plan_id": "owned"}) as action,
            patch.object(client, "host_action", return_value={"exit_code": 0}) as host_action,
        ):
            for name in ("python_run", "project_environment", "project_test", "project_package"):
                with self.subTest(action=name):
                    agent._api_action("windows_host", name, {}, [])
                    host_action.assert_called_with(
                        name, {"plan_id": "owned", "approved": True}, cancelled=cancelled,
                    )
            agent._api_action("windows_host", "directory_create", {}, [])
            action.assert_called_with("windows_host", "directory_create", {"plan_id": "owned", "approved": True})

    def test_cancellable_host_call_stays_local_and_does_not_convert_cancellation_to_http_error(self) -> None:
        client = DesktopApiClient("http://test")
        cancelled = Event()
        with (
            patch.object(client.windows_host, "invoke", side_effect=ChatCancelled("cancelled")) as invoke,
            patch.object(ApiClient, "action") as http,
            self.assertRaises(ChatCancelled),
        ):
            client.host_action("python_run", {"plan_id": "owned", "approved": True}, cancelled=cancelled)
        invoke.assert_called_once_with("python_run", {"plan_id": "owned", "approved": True}, cancelled=cancelled)
        http.assert_not_called()

    def test_directory_creation_is_discoverable_and_not_read_only(self) -> None:
        manifest = WindowsHostPlugin.manifest
        definitions = api_tool_definitions({"id": "windows_host", "actions": list(manifest.actions)})
        definition = next(item for item in definitions if item["name"] == "windows_host.directory_create")
        self.assertEqual(definition["parameters"]["required"], ["path"])
        self.assertNotIn(("windows_host", "directory_create"), READ_ONLY_ACTIONS)
        self.assertIn("directory_create", HOST_MUTATIONS)

    def test_python_execution_requires_separate_preview_and_is_never_read_only(self) -> None:
        manifest = WindowsHostPlugin.manifest
        definitions = api_tool_definitions({"id": "windows_host", "actions": list(manifest.actions)})
        definition = next(item for item in definitions if item["name"] == "windows_host.python_run")
        self.assertIn("path", definition["parameters"]["required"])
        self.assertNotIn(("windows_host", "python_run"), READ_ONLY_ACTIONS)
        self.assertIn("python_run", HOST_MUTATIONS)
        api = Mock(spec=ApiClient)
        api.action.return_value = {"plan_id": "owned", "target": {"path": "fixture.py"}}
        approve = Mock(return_value=False)
        agent = ChatAgent(api, Settings(), Event(), lambda _: None, approve)
        with self.assertRaises(ApiError):
            agent._api_action("windows_host", "python_run", {"path": "fixture.py"}, [])
        api.action.assert_called_once_with(
            "windows_host", "preview", {"action": "python_run", "arguments": {"path": "fixture.py"}},
        )
        approve.return_value = True
        agent._api_action("windows_host", "python_run", {"path": "fixture.py"}, [])
        api.action.assert_called_with("windows_host", "python_run", {"plan_id": "owned", "approved": True})

    def test_planner_distinguishes_host_paths_from_project_paths(self) -> None:
        from app.plugins.workspace import WorkspacePlugin

        host = WindowsHostPlugin.manifest
        workspace = WorkspacePlugin.manifest
        plugins = [
            {"id": item.plugin_id, "name": item.display_name, "description": item.description,
             "actions": list(item.actions)}
            for item in (host, workspace)
        ]
        self.assertIn("masaüstü dahil mutlak Windows yollarında", group_description(plugins[0]))
        self.assertIn("yalnız proje çalışma alanında göreli yollarla", group_description(plugins[1]).lower())
        definitions = api_tool_definitions(plugins[1])
        write = next(item for item in definitions if item["name"] == "workspace.write")
        self.assertIn("göreli", write["parameters"]["properties"]["path"]["description"])

    def test_chat_directory_creation_uses_preview_and_target_specific_approval(self) -> None:
        api = Mock(spec=ApiClient)
        api.action.return_value = {"plan_id": "owned", "target": {"path": "fixture"}}
        approve = Mock(return_value=False)
        agent = ChatAgent(api, Settings(), Event(), lambda _: None, approve)
        with self.assertRaises(ApiError):
            agent._api_action("windows_host", "directory_create", {"path": "fixture"}, [])
        api.action.assert_called_once_with(
            "windows_host", "preview", {"action": "directory_create", "arguments": {"path": "fixture"}},
        )
        approve.return_value = True
        agent._api_action("windows_host", "directory_create", {"path": "fixture"}, [])
        api.action.assert_called_with("windows_host", "directory_create", {"plan_id": "owned", "approved": True})

    def test_chat_mutation_uses_exact_approved_preview_and_can_cancel(self) -> None:
        api = Mock(spec=ApiClient)
        api.action.return_value = {"plan_id": "owned", "target": "fixture"}
        approved = Mock(return_value=False)
        agent = ChatAgent(api, Settings(), Event(), lambda _: None, approved)
        with self.assertRaises(ApiError):
            agent._api_action("windows_host", "file_delete", {"path": "fixture"}, [])
        api.action.assert_called_once_with("windows_host", "preview", {"action": "file_delete", "arguments": {"path": "fixture"}})
        approved.return_value = True
        agent._api_action("windows_host", "file_delete", {"path": "fixture"}, [])
        api.action.assert_called_with("windows_host", "file_delete", {"plan_id": "owned", "approved": True})
        agent.cancelled.set()
        api.action.reset_mock()
        with self.assertRaises(ChatCancelled):
            agent._api_action("windows_host", "file_delete", {"path": "fixture"}, [])
        api.action.assert_not_called()

    def test_manual_tools_also_preview_before_confirmation(self) -> None:
        ctx = AppContext(Settings())
        ctx.api = Mock(spec=ApiClient)
        ctx.api.action.side_effect = [{"plan_id": "owned", "target": {"path": "fixture"}}, {"status": "completed"}]
        result = Mock()
        with (
            patch("desktop.context.confirm", return_value=True) as confirm,
            patch("desktop.context.run_background", side_effect=lambda fn, done, _fail: done(fn())),
        ):
            ctx.call_action(None, "windows_host", "file_delete", {"path": "fixture"}, on_done=result)
        confirm.assert_called_once()
        self.assertIn("details", confirm.call_args.kwargs)
        self.assertEqual(ctx.api.action.call_count, 2)
        ctx.api.action.assert_called_with("windows_host", "file_delete", {"plan_id": "owned", "approved": True})
        result.assert_called_once_with({"status": "completed"})

    def test_manual_host_file_content_preserves_whitespace_and_can_be_empty(self) -> None:
        spec = next(item for item in HOST_FORMS if item["action"] == "file_write")
        widget = FormWidget(AppContext(Settings()), spec)
        self.addCleanup(widget.deleteLater)
        widget.inputs["path"].setText(r"F:\chosen\fixture.txt")
        for text in ("  first\n  second\n", ""):
            widget.inputs["content"].setPlainText(text)
            self.assertEqual(widget.build_payload()["content"], text)
        self.assertTrue(all(item.get("approval") for item in HOST_FORMS if item["action"] in HOST_MUTATIONS | HOST_PRIVATE_READS))
