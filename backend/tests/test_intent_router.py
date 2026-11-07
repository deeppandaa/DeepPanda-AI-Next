from __future__ import annotations

import asyncio
import json
import unittest
from typing import Any

import httpx
from app.main import create_app
from app.plugins.contracts import PluginManifest
from app.plugins.gateway import PluginGateway
from app.plugins.intent_router import IntentRouterPlugin, IntentRouterProviderError
from app.plugins.workflows import WorkflowsPlugin


class IntentRouterPluginTests(unittest.TestCase):
    class FakeGateway:
        def __init__(self, result: dict[str, Any] | None = None) -> None:
            self.calls: list[tuple[str, str, dict[str, Any]]] = []
            self.result = result or {
                "intent": "learn",
                "confidence": 0.94,
                "rationale": "The message states a reusable project preference.",
                "next_step": "Review the note and approve it before saving.",
                "requires_local_tools": False,
                "learning_proposal": {
                    "title": "Preferred runtime",
                    "content": "Use Python 3.12 for this project.",
                    "project": "AI-Next",
                    "category": "preferences",
                },
            }

        async def invoke(self, plugin_id: str, action: str, payload: dict[str, Any]) -> Any:
            self.calls.append((plugin_id, action, payload))
            if (plugin_id, action) == ("ollama", "models"):
                return {
                    "default_model": "qwen3.6:latest",
                    "models": [{"name": "qwen3.6:latest"}, {"name": "nomic-embed-text:latest"}],
                }
            if (plugin_id, action) == ("ollama", "chat"):
                return {"message": {"content": json.dumps(self.result)}}
            if plugin_id == "memory":
                raise AssertionError("Intent routing must not write memory.")
            raise AssertionError(f"Unexpected gateway action: {plugin_id}/{action}")

    def test_learn_intent_returns_reviewable_note_without_saving(self) -> None:
        gateway = self.FakeGateway()
        plugin = IntentRouterPlugin(gateway)  # type: ignore[arg-type]

        result = asyncio.run(plugin.invoke("route", {
            "message": "Remember that this project uses Python 3.12.",
        }))

        self.assertEqual(result["intent"], "learn")
        self.assertEqual(result["routing_status"], "ready")
        self.assertEqual(result["learning_proposal"]["title"], "Preferred runtime")
        self.assertFalse(result["saved"])
        self.assertFalse(result["executed"])
        self.assertEqual([call[:2] for call in gateway.calls], [
            ("ollama", "models"), ("ollama", "chat"),
        ])
        chat_payload = gateway.calls[-1][2]
        self.assertFalse(chat_payload["think"])
        self.assertIn("intent", chat_payload["response_schema"]["required"])
        self.assertIn("even when the user also asks to remember", chat_payload["system_prompt"])

    def test_non_learn_intents_never_return_a_memory_proposal(self) -> None:
        result_data = {
            "intent": "action_request",
            "confidence": 0.8,
            "rationale": "The user requested a file change.",
            "next_step": "Create a task plan and request approval.",
            "requires_local_tools": False,
            "learning_proposal": {
                "title": "Ignore this",
                "content": "Do not save me.",
                "project": "",
                "category": "general",
            },
        }
        plugin = IntentRouterPlugin(self.FakeGateway(result_data))  # type: ignore[arg-type]

        result = asyncio.run(plugin.invoke("route", {"message": "Change the code."}))

        self.assertEqual(result["intent"], "action_request")
        self.assertIsNone(result["learning_proposal"])

    def test_router_rejects_embedding_models_and_bad_intents(self) -> None:
        gateway = self.FakeGateway()
        plugin = IntentRouterPlugin(gateway)  # type: ignore[arg-type]

        async def exercise() -> None:
            with self.assertRaisesRegex(ValueError, "chat model"):
                await plugin.invoke("route", {"message": "hello", "model": "nomic-embed-text:latest"})
            gateway.result["intent"] = "execute"
            with self.assertRaisesRegex(IntentRouterProviderError, "unknown intent"):
                await plugin.invoke("route", {"message": "hello"})

        asyncio.run(exercise())

    def test_route_api_returns_a_proposal_without_memory_plugin(self) -> None:
        class FakeRouter:
            manifest = PluginManifest("intent_router", "Intent Router", "test", ("route",))

            async def invoke(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
                return {
                    "intent": "learn",
                    "confidence": 0.9,
                    "rationale": "Reusable fact.",
                    "next_step": "Review before saving.",
                    "learning_proposal": {"title": "Runtime", "content": "Python 3.12", "project": "", "category": "general"},
                    "saved": False,
                    "executed": False,
                }

        gateway = PluginGateway()
        gateway.register(FakeRouter())  # type: ignore[arg-type]
        app = create_app(gateway)

        async def send() -> httpx.Response:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.post("/api/chat/route", json={"message": "Remember Python 3.12."})

        response = asyncio.run(send())

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["saved"])
        self.assertEqual(response.json()["learning_proposal"]["title"], "Runtime")

    def test_chat_automatically_routes_and_returns_a_learning_proposal_without_saving(self) -> None:
        route_result = {
            "intent": "learn",
            "confidence": 0.91,
            "rationale": "The user gave a reusable project preference.",
            "next_step": "Review the note before saving.",
            "requires_local_tools": False,
            "learning_proposal": {
                "title": "Runtime preference",
                "content": "Use Python 3.12.",
                "project": "AI-Next",
                "category": "preferences",
            },
        }

        class FakeOllama:
            manifest = PluginManifest("ollama", "Ollama", "test", ("models", "chat"))

            async def invoke(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
                if action == "models":
                    return {"default_model": "qwen3.6:latest", "models": [{"name": "qwen3.6:latest"}]}
                if payload.get("format") == "json":
                    return {"message": {"content": json.dumps(route_result)}}
                return {"model": "qwen3.6:latest", "message": {"content": "I will use Python 3.12."}}

        class FakeSessions:
            manifest = PluginManifest("sessions", "Sessions", "test", ("create", "context", "append_turn"))

            async def invoke(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
                if action == "create":
                    return {"session_id": "route-session", "title": payload["title"]}
                if action == "context":
                    return {"session_id": payload["session_id"], "messages": []}
                return {"session_id": payload["session_id"], "saved_messages": 2}

        gateway = PluginGateway()
        gateway.register(FakeOllama())  # type: ignore[arg-type]
        gateway.register(FakeSessions())  # type: ignore[arg-type]
        gateway.register(WorkflowsPlugin())
        gateway.register(IntentRouterPlugin(gateway))
        app = create_app(gateway)

        async def send() -> httpx.Response:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.post("/api/chat", json={"message": "Remember Python 3.12."})

        response = asyncio.run(send())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["intent_route"]["intent"], "learn")
        self.assertFalse(response.json()["intent_route"]["saved"])
        self.assertFalse(response.json()["intent_route"]["executed"])
        self.assertEqual(response.json()["message"]["content"], "I will use Python 3.12.")


if __name__ == "__main__":
    unittest.main()