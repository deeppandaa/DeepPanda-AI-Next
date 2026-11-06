import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from app.main import create_app
from app.plugins.contracts import PluginManifest
from app.plugins.gateway import PluginGateway
from app.plugins.intent_router import IntentRouterPlugin
from app.plugins.workflows import WorkflowNotFoundError, WorkflowsPlugin


class WorkflowsPluginTests(unittest.TestCase):
    def test_chat_can_opt_in_to_freellmapi_without_changing_local_intent_routing(self) -> None:
        route_result = {
            "intent": "answer",
            "confidence": 0.9,
            "rationale": "Direct question.",
            "next_step": "Answer directly.",
            "learning_proposal": None,
        }

        class FakeOllama:
            manifest = PluginManifest("ollama", "Ollama", "Fake model", ("models", "chat"))

            async def invoke(self, action: str, payload: dict[str, object]) -> dict[str, object]:
                if action == "models":
                    return {
                        "default_model": "qwen3.6:latest",
                        "models": [{"name": "qwen3.6:latest"}],
                    }
                if payload.get("format") == "json":
                    return {"message": {"content": json.dumps(route_result)}}
                raise AssertionError("Chat completion should use FreeLLMAPI when opted in.")

        class FakeFreeLLMAPI:
            manifest = PluginManifest("freellmapi", "FreeLLMAPI", "Fake gateway", ("chat",))

            def __init__(self) -> None:
                self.received: list[dict[str, object]] = []
                self.models: list[str] = []

            async def invoke(self, action: str, payload: dict[str, object]) -> dict[str, object]:
                self.received.append(payload)
                self.models.append(str(payload["model"]))
                return {"model": "served-model", "message": {"content": "Cloud response"}}

        class FakeSessions:
            manifest = PluginManifest("sessions", "Sessions", "test", ("create", "context", "append_turn"))

            async def invoke(self, action: str, payload: dict[str, object]) -> dict[str, object]:
                if action == "create":
                    return {"session_id": "cloud-session", "title": payload["title"]}
                if action == "context":
                    return {"session_id": payload["session_id"], "messages": []}
                return {"session_id": payload["session_id"], "saved_messages": 2}

        with patch.dict(os.environ, {
            "FREELLMAPI_CHAT_ENABLED": "true",
            "FREELLMAPI_CHAT_MODEL": "auto",
        }):
            gateway = PluginGateway()
            gateway.register(FakeOllama())
            cloud = FakeFreeLLMAPI()
            gateway.register(cloud)
            gateway.register(WorkflowsPlugin())
            gateway.register(FakeSessions())
            gateway.register(IntentRouterPlugin(gateway))
            app = create_app(gateway)

            async def send_requests() -> tuple[httpx.Response, httpx.Response]:
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client:
                    automatic = await client.post("/api/chat", json={"message": "Hello"})
                    explicit = await client.post("/api/chat", json={
                        "message": "Hello again",
                        "model": "freellmapi:google/gemini-flash",
                    })
                    return automatic, explicit

            automatic, explicit = asyncio.run(send_requests())

        self.assertEqual(automatic.status_code, 200)
        self.assertEqual(automatic.json()["intent_route"]["model"], "qwen3.6:latest")
        self.assertEqual(automatic.json()["intent_route"]["completion_provider"], "freellmapi")
        self.assertEqual(automatic.json()["intent_route"]["completion_model"], "freellmapi:auto")
        self.assertEqual(automatic.json()["message"]["content"], "Cloud response")
        self.assertEqual(cloud.received[0]["message"], "Hello")
        self.assertEqual(explicit.status_code, 200)
        self.assertEqual(explicit.json()["intent_route"]["model"], "qwen3.6:latest")
        self.assertEqual(explicit.json()["intent_route"]["completion_model"], "freellmapi:google/gemini-flash")
        self.assertEqual(cloud.models, ["auto", "google/gemini-flash"])

    def test_chat_uses_area_priority_and_explicit_model_override(self) -> None:
        route_result = {
            "intent": "plan",
            "confidence": 0.9,
            "rationale": "The user asked for a plan.",
            "next_step": "Review the plan.",
            "learning_proposal": None,
        }

        class FakeOllama:
            manifest = PluginManifest("ollama", "Ollama", "Fake model", ("models", "chat"))

            def __init__(self) -> None:
                self.chat_payloads: list[dict[str, object]] = []

            async def invoke(self, action: str, payload: dict[str, object]) -> dict[str, object]:
                if action == "models":
                    return {
                        "default_model": "qwen3.6:latest",
                        "models": [{"name": name} for name in (
                            "qwen3.6:latest", "gemma:7b", "deepseek-coder:6.7b",
                        )],
                    }
                self.chat_payloads.append(payload)
                if payload.get("format") == "json":
                    return {"message": {"content": json.dumps(route_result)}}
                return {"model": payload["model"], "message": {"content": "Plan response"}}

        class FakeSessions:
            manifest = PluginManifest("sessions", "Sessions", "test", ("create", "context", "append_turn"))

            async def invoke(self, action: str, payload: dict[str, object]) -> dict[str, object]:
                if action == "create":
                    return {"session_id": "routing-session", "title": payload["title"]}
                if action == "context":
                    return {"session_id": payload["session_id"], "messages": []}
                return {"session_id": payload["session_id"], "saved_messages": 2}

        with tempfile.TemporaryDirectory() as directory:
            preferences_path = Path(directory) / "model-area-priorities.json"
            preferences_path.write_text(json.dumps({
                "area_priorities": {
                    "intent": ["qwen3.6:latest"],
                    "planning": ["gemma:7b", "qwen3.6:latest"],
                },
            }), encoding="utf-8")
            with patch.dict(os.environ, {"MODEL_ROUTING_PREFERENCES": str(preferences_path)}):
                gateway = PluginGateway()
                model = FakeOllama()
                gateway.register(model)
                gateway.register(WorkflowsPlugin())
                gateway.register(FakeSessions())
                gateway.register(IntentRouterPlugin(gateway))
                app = create_app(gateway)

                async def send_requests() -> tuple[httpx.Response, httpx.Response]:
                    async with httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=app), base_url="http://test"
                    ) as client:
                        automatic = await client.post("/api/chat", json={"message": "Plan this task."})
                        explicit = await client.post("/api/chat", json={
                            "message": "Plan this task.",
                            "model": "deepseek-coder:6.7b",
                        })
                        return automatic, explicit

                automatic, explicit = asyncio.run(send_requests())

        self.assertEqual(automatic.status_code, 200)
        self.assertEqual(automatic.json()["intent_route"]["completion_area"], "planning")
        self.assertEqual(automatic.json()["intent_route"]["completion_model"], "gemma:7b")
        self.assertEqual(automatic.json()["model"], "gemma:7b")
        self.assertEqual(explicit.status_code, 200)
        self.assertEqual(explicit.json()["model"], "deepseek-coder:6.7b")

    def test_selected_workflow_reaches_model_as_system_prompt(self) -> None:
        class FakeOllama:
            manifest = PluginManifest("ollama", "Ollama", "Fake model", ("chat",))

            def __init__(self) -> None:
                self.received: dict[str, object] = {}

            async def invoke(self, action: str, payload: dict[str, object]) -> dict[str, object]:
                self.received = payload
                return {"message": {"content": "ok"}}

        class FakeSessions:
            manifest = PluginManifest("sessions", "Sessions", "Fake sessions", ("create", "context", "append_turn"))

            async def invoke(self, action: str, payload: dict[str, object]) -> dict[str, object]:
                if action == "create":
                    return {"session_id": "test-session", "title": payload["title"]}
                if action == "context":
                    return {"session_id": payload["session_id"], "messages": []}
                return {"session_id": payload["session_id"], "saved_messages": 2}

        gateway = PluginGateway()
        model = FakeOllama()
        gateway.register(model)
        gateway.register(WorkflowsPlugin())
        gateway.register(FakeSessions())
        app = create_app(gateway)

        async def send_request() -> httpx.Response:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                return await client.post("/api/chat", json={"message": "fix this", "workflow": "debug"})

        response = asyncio.run(send_request())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["session_id"], "test-session")
        self.assertEqual(response.json()["intent_route"]["routing_status"], "unavailable")
        self.assertIn("tekrar üretim", str(model.received["system_prompt"]).lower())

    def test_catalog_lists_original_local_workflows(self) -> None:
        plugin = WorkflowsPlugin()

        result = asyncio.run(plugin.invoke("catalog", {}))

        workflow_ids = {workflow["id"] for workflow in result["workflows"]}
        self.assertIn("plan", workflow_ids)
        self.assertIn("debug", workflow_ids)
        self.assertIn("review", workflow_ids)

    def test_get_returns_mode_instructions(self) -> None:
        plugin = WorkflowsPlugin()

        result = asyncio.run(plugin.invoke("get", {"mode": "debug"}))

        self.assertEqual(result["mode"], "debug")
        self.assertIn("tekrar üretim", result["instructions"].lower())

    def test_unknown_workflow_is_rejected(self) -> None:
        plugin = WorkflowsPlugin()

        with self.assertRaises(WorkflowNotFoundError):
            asyncio.run(plugin.invoke("get", {"mode": "unrestricted"}))


if __name__ == "__main__":
    unittest.main()