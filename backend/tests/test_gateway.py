import asyncio
import unittest

from app.main import create_app
from app.plugins.contracts import PluginManifest
from app.plugins.gateway import (
    PluginActionNotFoundError,
    PluginGateway,
    PluginNotFoundError,
)


class FakePlugin:
    manifest = PluginManifest("sample", "Sample", "Test plugin", ("echo",))

    async def invoke(self, action: str, payload: dict[str, str]) -> dict[str, str]:
        return {"action": action, **payload}


class PluginGatewayTests(unittest.TestCase):
    def test_default_app_registers_all_active_plugins_with_unique_actions(self) -> None:
        gateway = create_app().state.plugin_gateway
        plugin_actions = {plugin["id"]: plugin["actions"] for plugin in gateway.list_plugins()}

        self.assertEqual(set(plugin_actions), {
            "analysis", "binary_analysis", "browser", "codegraph", "diagnostics", "freellmapi",
            "documents", "intent_router", "jobs", "knowledge", "memory", "ollama",
            "repo_watch", "research", "sessions", "task_assistant", "tasks", "workflows", "workspace",
        })
        self.assertTrue(all(actions for actions in plugin_actions.values()))
        self.assertTrue(all(len(actions) == len(set(actions)) for actions in plugin_actions.values()))

    def test_gateway_dispatches_registered_plugin(self) -> None:
        gateway = PluginGateway()
        gateway.register(FakePlugin())

        result = asyncio.run(gateway.invoke("sample", "echo", {"value": "ok"}))

        self.assertEqual(result, {"action": "echo", "value": "ok"})

    def test_gateway_rejects_unknown_plugin(self) -> None:
        gateway = PluginGateway()

        with self.assertRaises(PluginNotFoundError):
            asyncio.run(gateway.invoke("missing", "echo"))

    def test_gateway_rejects_unregistered_action(self) -> None:
        gateway = PluginGateway()
        gateway.register(FakePlugin())

        with self.assertRaises(PluginActionNotFoundError):
            asyncio.run(gateway.invoke("sample", "delete"))

    def test_gateway_rejects_duplicate_plugin_ids(self) -> None:
        gateway = PluginGateway()
        gateway.register(FakePlugin())

        with self.assertRaisesRegex(ValueError, "already registered"):
            gateway.register(FakePlugin())


if __name__ == "__main__":
    unittest.main()