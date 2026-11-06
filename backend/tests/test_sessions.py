import asyncio
import tempfile
import unittest
from pathlib import Path

import httpx

from app.main import create_app
from app.plugins.contracts import PluginManifest
from app.plugins.gateway import PluginGateway
from app.plugins.sessions import SessionDeleteApprovalRequired, SessionsPlugin
from app.plugins.workflows import WorkflowsPlugin


class FakeOllama:
    manifest = PluginManifest("ollama", "Ollama", "Fake model", ("chat",))

    async def invoke(self, action: str, payload: dict[str, object]) -> dict[str, object]:
        return {"model": "fake", "message": {"content": "stored answer"}}


class SessionsPluginTests(unittest.TestCase):
    def test_chat_api_persists_session_and_requires_delete_approval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            gateway = PluginGateway()
            gateway.register(FakeOllama())
            gateway.register(WorkflowsPlugin())
            gateway.register(SessionsPlugin(Path(directory) / "chat.db"))
            app = create_app(gateway)

            async def exercise_api() -> tuple[httpx.Response, httpx.Response, httpx.Response, httpx.Response]:
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    chat = await client.post("/api/chat", json={"message": "question"})
                    session_id = chat.json()["session_id"]
                    messages = await client.get(f"/api/chat/sessions/{session_id}/messages")
                    denied = await client.request(
                        "DELETE",
                        f"/api/chat/sessions/{session_id}",
                        json={"approved": False},
                    )
                    deleted = await client.request(
                        "DELETE",
                        f"/api/chat/sessions/{session_id}",
                        json={"approved": True},
                    )
                    return chat, messages, denied, deleted

            chat, messages, denied, deleted = asyncio.run(exercise_api())

        self.assertEqual(chat.status_code, 200)
        self.assertEqual([item["role"] for item in messages.json()["messages"]], ["user", "assistant"])
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(deleted.status_code, 200)

    def test_sessions_keep_histories_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plugin = SessionsPlugin(Path(directory) / "chat.db")
            first = asyncio.run(plugin.invoke("append_turn", {
                "session_id": "session-a",
                "user_message": "question A",
                "assistant_message": "answer A",
            }))
            asyncio.run(plugin.invoke("append_turn", {
                "session_id": "session-b",
                "user_message": "question B",
                "assistant_message": "answer B",
            }))
            history = asyncio.run(plugin.invoke("messages", {"session_id": first["session_id"]}))
            context = asyncio.run(plugin.invoke("context", {"session_id": first["session_id"], "limit": 1}))

        self.assertEqual([item["content"] for item in history["messages"]], ["question A", "answer A"])
        self.assertEqual([item["content"] for item in context["messages"]], ["answer A"])

    def test_session_delete_requires_explicit_approval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plugin = SessionsPlugin(Path(directory) / "chat.db")
            result = asyncio.run(plugin.invoke("append_turn", {
                "session_id": "session-a",
                "user_message": "question",
                "assistant_message": "answer",
            }))

            with self.assertRaises(SessionDeleteApprovalRequired):
                asyncio.run(plugin.invoke("delete", {"session_id": result["session_id"]}))

            sessions = asyncio.run(plugin.invoke("list", {}))

        self.assertEqual(len(sessions["sessions"]), 1)

    def test_approved_delete_removes_session_and_messages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plugin = SessionsPlugin(Path(directory) / "chat.db")
            result = asyncio.run(plugin.invoke("append_turn", {
                "session_id": "session-a",
                "user_message": "question",
                "assistant_message": "answer",
            }))

            deleted = asyncio.run(plugin.invoke("delete", {
                "session_id": result["session_id"],
                "approved": True,
            }))
            messages = asyncio.run(plugin.invoke("messages", {"session_id": result["session_id"]}))

        self.assertTrue(deleted["deleted"])
        self.assertEqual(messages["messages"], [])


if __name__ == "__main__":
    unittest.main()