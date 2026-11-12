from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import Mock, patch

from PySide6.QtWidgets import QApplication

from desktop.chat_context import ChatCancelled
from desktop.cline import (
    CLINE,
    ClineClient,
    ClineError,
    ClineRpcError,
    command,
    login,
    session_models,
)
from desktop.config import PROJECT_ROOT, Settings
from desktop.context import AppContext
from desktop.page_chat import ChatPage
from desktop.page_settings import SettingsPage

SERVER = r"""
import json,sys,time
scenario = sys.argv[1]
selected_model = 'model-a'
def model_config():
    return {'id':'model-selector','category':'model','type':'select','currentValue':selected_model,
            'options':[{'group':'provider','name':'Provider','options':[
            {'value':'model-a','name':'Model A'},{'value':'model-b','name':'Model B'}]}]}
def send(payload):
    print(json.dumps({'jsonrpc':'2.0', **payload}), flush=True)
for line in sys.stdin:
    request = json.loads(line)
    method = request.get('method')
    if method == 'initialize':
        if scenario == 'timeout':
            time.sleep(20)
        if scenario == 'invalid':
            print('not json', flush=True)
            continue
        send({'id':request['id'], 'result':{'protocolVersion':1, 'agentInfo':{'name':'fixture'}}})
    elif method == 'session/new':
        if scenario == 'auth':
            print('PRIVATE_CREDENTIAL_MUST_NOT_LEAK', file=sys.stderr, flush=True)
            send({'id':request['id'], 'error':{'code':-32000, 'message':'PRIVATE_CREDENTIAL_MUST_NOT_LEAK'}})
            continue
        session={'sessionId':'sample', 'modes': {'availableModes':[{'id':'plan'},{'id':'act'}]}}
        if scenario.startswith('config'):
            session['configOptions'] = [model_config(),{
                'id':'auto','category':'_custom','type':'select','currentValue':'off',
                'options':[{'value':'on','name':'Auto approve on'}]}]
        if scenario == 'legacy':
            session['models']={'currentModelId':selected_model,'availableModels':[
                {'modelId':'model-a','name':'Model A'},{'modelId':'model-b','name':'Model B'}]}
        send({'id':request['id'], 'result':session})
    elif method == 'session/set_config_option':
        if request['params']['configId'] != 'model-selector':
            raise RuntimeError('Client tried changing non-model config')
        if scenario != 'config_ignored':
            selected_model=request['params']['value']
        send({'id':request['id'], 'result':{'configOptions':[model_config()]}})
    elif method == 'session/set_model':
        selected_model=request['params']['modelId']
        send({'id':request['id'], 'result':{}})
    elif method == 'session/set_mode':
        send({'id':request['id'], 'result':{}})
    elif method == 'session/prompt':
        if scenario == 'billing':
            send({'id':request['id'],'error':{'code':-32603,
                'message':'Provider insufficient balance PRIVATE_CREDENTIAL_MUST_NOT_LEAK'}})
            continue
        if scenario == 'client_fs':
            send({'id':100, 'method':'fs/write_text_file', 'params':{'path':'never-written'}})
            response = json.loads(sys.stdin.readline())
            text = 'blocked' if response['error']['code'] == -32601 else 'unsafe'
        elif scenario in ('allow', 'deny', 'read'):
            send({'id':100, 'method':'session/request_permission', 'params':{
                'sessionId':'sample', 'toolCall':{'title':'edit sample','kind':'read' if scenario=='read' else 'edit'},
                'options':[{'optionId':'always','kind':'allow_always'},{'optionId':'once','kind':'allow_once'}]}})
            response = json.loads(sys.stdin.readline())['result']['outcome']
            text = response.get('optionId', response['outcome'])
        else:
            text = 'x'*64001 if scenario=='large' else (
                selected_model if scenario.startswith('config') or scenario=='legacy' else 'CLINE_READY')
        send({'method':'session/update', 'params':{
            'sessionId':'sample', 'update':{'sessionUpdate':'tool_call','toolCallId':'tool1',
            'title':'Fixture Read','kind':'read','status':'pending'}}})
        send({'method':'session/update', 'params':{
            'sessionId':'sample', 'update':{'sessionUpdate':'tool_call_update','toolCallId':'tool1',
            'status':'completed','content':[]}}})
        send({'method':'session/update', 'params':{
            'sessionId':'sample', 'update':{'sessionUpdate':'agent_message_chunk',
            'content':{'type':'text','text':text}}}})
        send({'id':request['id'], 'result':{'stopReason':'end_turn'}})
"""


@unittest.skipUnless(os.name == "nt", "Windows Cline integration")
class ClineProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.cancelled = Event()
        self.events = []
        self.approve = Mock(return_value=True)

    def run_client(
        self, scenario: str, *, prompt: str | None = "hello", mode: str = "agent",
        timeout: float = 5, check_session: bool = False, model: str | None = None,
    ) -> dict:
        client = ClineClient(self.cancelled, self.events.append, self.approve, timeout=timeout, root=self.root)
        with patch("desktop.cline.command", return_value=[sys.executable, "-u", "-c", SERVER, scenario]):
            result = client.run(self.root, prompt, mode, check_session=check_session, model=model)
        self.assertIsNotNone(client.process)
        self.assertIsNotNone(client.process.poll())
        return result

    def test_initialization_is_not_claimed_as_authenticated(self) -> None:
        result = self.run_client("normal", prompt=None)
        self.assertEqual(result["protocol"], 1)
        self.assertFalse(result["authentication_verified"])
        self.approve.assert_not_called()

    def test_real_transport_streams_and_closes_process(self) -> None:
        result = self.run_client("normal")
        self.assertEqual(result["answer"], "CLINE_READY")
        self.assertIn({"type": "token", "content": "CLINE_READY"}, self.events)
        self.assertEqual(result["tools_used"], [{"name": "Cline / Fixture Read", "status": "completed"}])
        self.assertTrue(any(event.get("result", {}).get("status") == "completed" for event in self.events))
        self.assertTrue(result["model_response_verified"])

    def test_session_probe_never_prompts_or_claims_authenticated_response(self) -> None:
        result = self.run_client("config", prompt=None, check_session=True)
        self.assertTrue(result["session_ready"])
        self.assertFalse(result["authentication_verified"])
        self.assertFalse(result["model_response_verified"])
        self.assertEqual(result["models"], [{"id": "model-a", "name": "Model A"}, {"id": "model-b", "name": "Model B"}])
        self.assertEqual(result["current_model"], "model-a")
        self.assertFalse(self.events)
        self.approve.assert_not_called()

    def test_probe_session_error_is_explicit_not_a_ready_fallback(self) -> None:
        result = self.run_client("auth", prompt=None, check_session=True)
        self.assertTrue(result["installed"])
        self.assertFalse(result["session_ready"])
        self.assertEqual(result["error_code"], -32000)
        self.assertEqual(result["error_method"], "session/new")
        self.assertNotIn("PRIVATE_CREDENTIAL", json.dumps(result))

    def test_probe_rejects_prompt_before_starting_a_process(self) -> None:
        with patch("desktop.cline.subprocess.Popen") as spawn, self.assertRaises(ValueError):
            self.run_client("config", check_session=True)
        spawn.assert_not_called()

    def test_bad_model_identifier_is_rejected_before_starting_process(self) -> None:
        for model in ("", "x" * 501):
            with self.subTest(model=len(model)), patch("desktop.cline.subprocess.Popen") as spawn, self.assertRaises(ValueError):
                self.run_client("config", model=model)
            spawn.assert_not_called()

    def test_model_selection_uses_advertised_config_or_legacy_method(self) -> None:
        for scenario in ("config", "legacy"):
            with self.subTest(scenario=scenario):
                result = self.run_client(scenario, model="model-b")
                self.assertEqual(result["model"], "model-b")
                self.assertEqual(result["answer"], "model-b")

    def test_unknown_model_or_unconfirmed_change_never_sends_prompt(self) -> None:
        for scenario, model in (("config", "not-advertised"), ("config_ignored", "model-b")):
            with self.subTest(scenario=scenario), self.assertRaises(ClineError):
                self.run_client(scenario, model=model)
        self.assertFalse(self.events)

    def test_malformed_model_catalog_and_duplicate_ids_are_rejected(self) -> None:
        for models in (
            {"availableModels": ["bad"]},
            {"availableModels": [{"modelId": "a", "name": "A"}, {"modelId": "a", "name": "A"}]},
            {"availableModels": [{"modelId": "", "name": "A"}]},
        ):
            with self.subTest(models=models), self.assertRaises(ClineError):
                session_models({"models": models})
        with self.assertRaises(ClineError):
            session_models({"configOptions": [{"category": "model", "type": "select", "id": "x",
                                               "options": [{"options": ["bad"]}]}]})

    def test_permission_is_once_only_and_denial_is_forwarded(self) -> None:
        self.assertEqual(self.run_client("allow")["answer"], "once")
        self.assertEqual(self.approve.call_count, 1)
        self.approve.return_value = False
        self.assertEqual(self.run_client("deny")["answer"], "cancelled")

    def test_ask_and_plan_reject_edit_even_if_ui_would_approve(self) -> None:
        for mode in ("ask", "plan"):
            with self.subTest(mode=mode):
                self.assertEqual(self.run_client("allow", mode=mode)["answer"], "cancelled")
        self.approve.assert_not_called()

    def test_plan_read_still_requires_user_approval(self) -> None:
        self.assertEqual(self.run_client("read", mode="plan")["answer"], "once")
        self.approve.assert_called_once()

    def test_no_client_filesystem_execution_is_advertised_or_performed(self) -> None:
        self.assertEqual(self.run_client("client_fs")["answer"], "blocked")
        self.assertFalse((self.root / "never-written").exists())

    def test_auth_failure_does_not_expose_raw_error_or_credentials(self) -> None:
        with self.assertRaises(ClineError) as error:
            self.run_client("auth")
        self.assertIn("-32000", str(error.exception))
        self.assertNotIn("PRIVATE_CREDENTIAL", str(error.exception))

    def test_billing_error_is_actionable_without_raw_provider_message(self) -> None:
        with self.assertRaises(ClineRpcError) as error:
            self.run_client("billing")
        self.assertEqual(error.exception.reason, "billing")
        self.assertEqual(error.exception.method, "session/prompt")
        self.assertIn("bakiye", str(error.exception))
        self.assertNotIn("PRIVATE_CREDENTIAL", str(error.exception))

    def test_only_known_error_signals_are_classified_and_never_echoed(self) -> None:
        for message, reason in (
            ("invalid api key PRIVATE_CREDENTIAL", "authentication"),
            ("insufficient credits PRIVATE_CREDENTIAL", "billing"),
            ("unknown provider PRIVATE_CREDENTIAL", "unknown"),
            (None, "unknown"),
        ):
            with self.subTest(reason=reason):
                error = ClineRpcError("session/prompt", -32603, message)
                self.assertEqual(error.reason, reason)
                self.assertNotIn("PRIVATE_CREDENTIAL", str(error))

    def test_timeout_malformed_output_and_size_limits_stop_the_process(self) -> None:
        for scenario, timeout in (("timeout", 0.3), ("invalid", 5), ("large", 5)):
            with self.subTest(scenario=scenario), self.assertRaises(ClineError):
                self.run_client(scenario, timeout=timeout)

    def test_cancel_during_stream_does_not_return_success(self) -> None:
        def emit(event: dict) -> None:
            if event["type"] == "token":
                self.cancelled.set()
        client = ClineClient(self.cancelled, emit, self.approve, timeout=5, root=self.root)
        with (
            patch("desktop.cline.command", return_value=[sys.executable, "-u", "-c", SERVER, "normal"]),
            self.assertRaises(ChatCancelled),
        ):
            client.run(self.root, "hello")
        self.assertIsNotNone(client.process.poll())

    def test_login_uses_isolated_state_and_no_inherited_provider_secrets(self) -> None:
        with (
            patch("desktop.cline.command", return_value=["cline.exe", "--config", "isolated"]),
            patch.dict(os.environ, {"CLINE_API_KEY": "PRIVATE_CREDENTIAL", "ANTHROPIC_API_KEY": "PRIVATE_CREDENTIAL"}),
            patch("desktop.cline.subprocess.Popen") as spawn,
        ):
            login(self.root)
        args, kwargs = spawn.call_args
        self.assertEqual(args[0][-2:], ["auth", "cline"])
        self.assertNotIn("CLINE_API_KEY", kwargs["env"])
        self.assertNotIn("ANTHROPIC_API_KEY", kwargs["env"])
        self.assertNotIn("shell", kwargs)

    def test_missing_installation_and_private_workspace_are_explicit_errors(self) -> None:
        with self.assertRaises(ClineError):
            command(self.root)
        client = ClineClient(self.cancelled, self.events.append, self.approve, root=self.root)
        private = self.root / ".tools"
        private.mkdir()
        with self.assertRaises(ValueError):
            client.run(private, "hello")

    @unittest.skipUnless(
        (PROJECT_ROOT / ".tools" / "cline" / "node_modules" / "@cline" / "cli-windows-x64" / "bin" / "cline.exe").exists(),
        "Optional native Cline CLI not installed",
    )
    def test_installed_native_cline_really_negotiates_acp_without_a_prompt(self) -> None:
        result = ClineClient(self.cancelled, self.events.append, self.approve, timeout=25).run(self.root)
        self.assertEqual(result["agent"], "cline")
        self.assertFalse(result["authentication_verified"])


class ClineChatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.real_save_settings = Settings.save
        saved = patch.object(Settings, "save")
        self.save_settings = saved.start()
        self.addCleanup(saved.stop)
        self.context = AppContext(Settings())
        self.context.api = Mock()
        self.page = ChatPage(self.context)
        self.addCleanup(self.page.deleteLater)
        self.page.model_box.addItem("Cline", CLINE)
        self.page.model_box.setCurrentIndex(0)
        self.page.input.setPlainText("hello")

    def test_cloud_refusal_never_starts_a_worker_or_discards_message(self) -> None:
        with patch("desktop.page_chat.confirm", return_value=False), patch("desktop.page_chat.run_background") as run:
            self.page.send()
        run.assert_not_called()
        self.assertEqual(self.page.input.toPlainText(), "hello")
        self.assertFalse(self.page.messages)

    def test_attachments_are_not_implicitly_forwarded_to_cline(self) -> None:
        self.page.attachments.append(Path(__file__))
        with patch("desktop.page_chat.run_background") as run:
            self.page.send()
        run.assert_not_called()

    def test_completed_cline_answer_is_saved_in_shared_history(self) -> None:
        client = Mock()
        client.run.return_value = {"answer": "done"}
        self.context.api.create_session.return_value = {"session_id": "saved"}
        result = self.page._cline_turn("hello", PROJECT_ROOT, "ask", client)
        self.assertEqual(result["session_id"], "saved")
        self.assertEqual(self.context.api.action.call_args.args[1], "append_turn")
        self.assertEqual(self.context.api.action.call_args.args[2]["assistant_message"], "done")

    def test_explicit_model_is_forwarded_and_actual_model_reported(self) -> None:
        client = Mock()
        client.run.return_value = {"answer": "done", "model": "actual-model", "model_response_verified": True}
        self.context.api.create_session.return_value = {"session_id": "saved"}
        result = self.page._cline_turn("hello", PROJECT_ROOT, "ask", client, model="actual-model")
        self.assertEqual(client.run.call_args.kwargs["model"], "actual-model")
        self.assertEqual(result["model"], "Cline / actual-model")
        self.assertTrue(result["cline_verification"]["model_response_verified"])

    def test_workspace_and_model_preferences_are_saved_without_credentials(self) -> None:
        with patch("desktop.page_chat.QFileDialog.getExistingDirectory", return_value=str(PROJECT_ROOT / "projects")):
            self.page._cline_folder()
        self.page.cline_model_box.addItem("Model B", "model-b")
        self.page.cline_model_box.setCurrentIndex(1)
        self.assertEqual(self.context.settings.cline_workspace, str(PROJECT_ROOT / "projects"))
        self.assertEqual(self.context.settings.cline_model, "model-b")
        self.assertEqual(self.save_settings.call_count, 2)

    def test_general_settings_save_preserves_cline_preferences(self) -> None:
        self.context.settings.cline_model = "model-b"
        self.context.settings.cline_workspace = str(PROJECT_ROOT / "projects" / "stok_demo")
        page = SettingsPage(self.context, Mock())
        self.addCleanup(page.deleteLater)
        result = page.current()
        self.assertEqual(result.cline_model, "model-b")
        self.assertEqual(result.cline_workspace, self.context.settings.cline_workspace)

    def test_cline_preferences_roundtrip_in_local_ini_without_account_secrets(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            target = Path(directory) / "settings.ini"
            with patch("desktop.config.SETTINGS_FILE", target):
                settings = Settings(cline_workspace=str(PROJECT_ROOT / "projects" / "stok_demo"), cline_model="model-b")
                self.real_save_settings(settings)
                loaded = Settings.load()
            self.assertEqual(loaded.cline_workspace, str(PROJECT_ROOT / "projects" / "stok_demo"))
            self.assertEqual(loaded.cline_model, "model-b")
            self.assertNotIn("api_key", target.read_text().casefold())
            self.save_settings.assert_not_called()

    def test_readiness_ui_populates_models_without_resetting_saved_choice(self) -> None:
        self.context.settings.cline_model = "missing-model"
        client = Mock()
        result = {"session_ready": True, "models": [{"id": "model-a", "name": "Model A"}],
                  "current_model": "model-a"}
        with (
            patch("desktop.page_chat.confirm", return_value=True),
            patch("desktop.page_chat.ClineClient", return_value=client),
            patch("desktop.page_chat.run_background") as run,
        ):
            self.page._cline_check()
            self.assertTrue(self.page.busy)
            run.call_args.args[1](result)
        self.assertFalse(self.page.busy)
        self.assertIsNone(self.page.cancelled)
        self.assertEqual(self.page.cline_model_box.currentData(), "missing-model")
        self.assertIn("gerçek model yanıtı doğrulanmadı", self.page.cline_connection.text())
        self.save_settings.assert_not_called()

    def test_readiness_ui_shows_session_error_not_success(self) -> None:
        with (
            patch("desktop.page_chat.confirm", return_value=True),
            patch("desktop.page_chat.run_background") as run,
        ):
            self.page._cline_check()
            run.call_args.args[1]({"session_ready": False, "error": "session/new -32000"})
        self.assertIn("oturumu hazır değil", self.page.cline_connection.text())
        self.assertFalse(self.page.busy)

    def test_readiness_cancellation_does_not_add_conversation_or_clear_input(self) -> None:
        with (
            patch("desktop.page_chat.confirm", return_value=True),
            patch("desktop.page_chat.run_background") as run,
        ):
            self.page._cline_check()
            self.page.stop()
            self.assertTrue(self.page.cancelled.is_set())
            run.call_args.args[2](ChatCancelled("cancelled"))
        self.assertFalse(self.page.busy)
        self.assertFalse(self.page.messages)
        self.assertEqual(self.page.input.toPlainText(), "hello")

    def test_live_response_test_refusal_does_not_call_provider(self) -> None:
        with patch("desktop.page_chat.confirm", return_value=False), patch("desktop.page_chat.run_background") as run:
            self.page._cline_test_response()
        run.assert_not_called()
        self.assertFalse(self.page.busy)

    def test_live_response_test_requires_exact_expected_output(self) -> None:
        for answer, verified, tools, success in (("CLINE_CONNECTION_OK", True, [], True),
                                               ("other", True, [], False),
                                               ("CLINE_CONNECTION_OK", False, [], False),
                                               ("CLINE_CONNECTION_OK", True, [{"name": "read"}], False)):
            with (
                self.subTest(answer=answer, verified=verified),
                patch("desktop.page_chat.confirm", return_value=True),
                patch("desktop.page_chat.run_background") as run,
            ):
                self.page._cline_test_response()
                run.call_args.args[1]({"answer": answer, "model_response_verified": verified,
                                       "model": "model-a", "tools_used": tools})
            self.assertEqual("GEÇTİ" in self.page.cline_connection.text(), success)
            self.assertFalse(self.page.messages)
            self.assertEqual(self.page.input.toPlainText(), "hello")

    def test_live_response_test_uses_empty_folder_no_history_and_no_tool_permissions(self) -> None:
        client = Mock()
        def response(workspace, *_args, **_kwargs):
            self.assertTrue(workspace.is_dir())
            self.assertEqual(list(workspace.iterdir()), [])
            return {"answer": "CLINE_CONNECTION_OK", "model_response_verified": True}
        client.run.side_effect = response
        with (
            patch("desktop.page_chat.confirm", return_value=True),
            patch("desktop.page_chat.ClineClient", return_value=client) as factory,
            patch("desktop.page_chat.run_background") as run,
        ):
            self.page._cline_test_response()
            result = run.call_args.args[0]()
            run.call_args.args[1](result)
        args = client.run.call_args.args
        self.assertFalse(args[0].exists())
        self.assertTrue(args[0].is_relative_to(PROJECT_ROOT / "projects"))
        self.assertNotIn("Previous conversation", args[1])
        self.assertEqual(args[2], "ask")
        self.assertFalse(factory.call_args.args[2]("command", {}))
        self.context.api.action.assert_not_called()

    def test_live_response_failure_shows_billing_block_and_does_not_save_history(self) -> None:
        with patch("desktop.page_chat.confirm", return_value=True), patch("desktop.page_chat.run_background") as run:
            self.page._cline_test_response()
            run.call_args.args[2](ClineRpcError("session/prompt", -32603, "insufficient balance"))
        self.assertIn("bakiye", self.page.cline_connection.text())
        self.assertFalse(self.page.busy)
        self.assertIsNone(self.page.cancelled)
        self.assertFalse(self.page.messages)

    def test_failed_cline_turn_is_not_saved_as_success(self) -> None:
        client = Mock()
        client.run.side_effect = ClineError("not authenticated")
        with self.assertRaises(ClineError):
            self.page._cline_turn("hello", PROJECT_ROOT, "ask", client)
        self.context.api.create_session.assert_not_called()
        self.context.api.action.assert_not_called()

    def test_long_history_is_explicitly_truncated_before_prompting(self) -> None:
        self.page.session_id = "existing"
        self.context.api.action.return_value = {"messages": [{"role": "user", "content": "x" * 30000}]}
        client = Mock()
        client.run.return_value = {"answer": "done"}
        self.page._cline_turn("hello", PROJECT_ROOT, "ask", client)
        prompt = client.run.call_args.args[1]
        self.assertIn("bağlamı kesildi", prompt)
        self.assertLess(len(prompt), 48000)

    def test_pinned_package_lock_uses_only_official_registry(self) -> None:
        manifest = json.loads((PROJECT_ROOT / "tools" / "cline" / "package.json").read_text())
        lock = json.loads((PROJECT_ROOT / "tools" / "cline" / "package-lock.json").read_text())
        self.assertEqual(manifest["dependencies"], {"@cline/cli-windows-x64": "3.0.74"})
        package = lock["packages"]["node_modules/@cline/cli-windows-x64"]
        self.assertTrue(package["resolved"].startswith("https://registry.npmjs.org/"))
        self.assertTrue(package["integrity"].startswith("sha512-"))
