from __future__ import annotations

import asyncio
import json
import unittest
from typing import Any
from unittest.mock import patch

import httpx
from app.main import create_app
from app.plugins.gateway import PluginGateway
from app.plugins.multi_agent import (
    MultiAgentApprovalRequired,
    MultiAgentPlugin,
    MultiAgentProviderError,
)


class FakeGateway:
    def __init__(
        self, models: list[str] | None = None, fail_at: int | None = None
    ) -> None:
        self.models = models or ["qwen2.5-coder:7b"]
        self.fail_at = fail_at
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    async def invoke(
        self, plugin_id: str, action: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        self.calls.append((plugin_id, action, payload))
        if (plugin_id, action) == ("ollama", "models"):
            return {"models": [{"name": name} for name in self.models]}
        if (plugin_id, action) == ("ollama", "chat"):
            stage = len([call for call in self.calls if call[1] == "chat"])
            if self.fail_at == stage:
                raise httpx.ConnectError("unavailable")
            return {
                "model": payload["model"],
                "done": True,
                "done_reason": "stop",
                "message": {"content": json.dumps({"content": f"stage {stage}"})},
            }
        raise AssertionError(f"Unexpected gateway action: {plugin_id}/{action}")


class MultiAgentPluginTests(unittest.TestCase):
    def test_requires_explicit_approval(self) -> None:
        plugin = MultiAgentPlugin(FakeGateway())  # type: ignore[arg-type]

        async def exercise() -> None:
            with self.assertRaises(MultiAgentApprovalRequired):
                await plugin.invoke("run", {"request": "Plan a safe implementation"})

        asyncio.run(exercise())

    def test_runs_five_local_roles_without_tools(self) -> None:
        gateway = FakeGateway()
        plugin = MultiAgentPlugin(gateway)  # type: ignore[arg-type]

        result = asyncio.run(
            plugin.invoke(
                "run",
                {
                    "approved": True,
                    "request": "Design a small feature and its tests.",
                },
            )
        )

        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["local_only"])
        self.assertEqual(result["tools_used"], [])
        self.assertEqual(
            [stage["id"] for stage in result["stages"]],
            [
                "planner",
                "researcher",
                "developer",
                "reviewer",
                "synthesizer",
            ],
        )
        self.assertEqual(result["answer"], "stage 5")
        chat_calls = [call for call in gateway.calls if call[1] == "chat"]
        self.assertEqual(len(chat_calls), 5)
        self.assertTrue(
            all(call[2]["model"] == "qwen2.5-coder:7b" for call in chat_calls)
        )
        self.assertTrue(all(call[2]["format"] == "json" for call in chat_calls))
        self.assertTrue(
            all(call[2]["max_output_tokens"] == 1_024 for call in chat_calls)
        )
        self.assertIn("güvenilmeyen veri", chat_calls[0][2]["system_prompt"])
        self.assertIn("Önceki ajan notları", chat_calls[-1][2]["message"])

    def test_rejects_uninstalled_or_cloud_models(self) -> None:
        plugin = MultiAgentPlugin(FakeGateway(models=["qwen2.5-coder:7b"]))  # type: ignore[arg-type]

        async def exercise(model: str) -> None:
            with self.assertRaises(MultiAgentProviderError):
                await plugin.invoke(
                    "run", {"approved": True, "request": "Plan", "model": model}
                )

        asyncio.run(exercise("missing:latest"))
        asyncio.run(exercise("remote:cloud"))

    def test_stops_when_a_stage_fails(self) -> None:
        gateway = FakeGateway(fail_at=3)
        plugin = MultiAgentPlugin(gateway)  # type: ignore[arg-type]

        async def exercise() -> None:
            with self.assertRaisesRegex(MultiAgentProviderError, "Çözüm taslağı"):
                await plugin.invoke("run", {"approved": True, "request": "Plan"})

        asyncio.run(exercise())
        self.assertEqual(len([call for call in gateway.calls if call[1] == "chat"]), 3)

    def test_incomplete_or_invalid_stage_never_runs_later_stages(self) -> None:
        cases = [
            {"message": {"content": '{"content":"unverified"}'}},
            {"done": False, "message": {"content": '{"content":"partial"}'}},
            {"done": True, "done_reason": "length", "message": {"content": '{"content":"cut"}'}},
            {"done": True, "done_reason": "stop", "message": {"content": '{"content":"ok","extra":true}'}},
            {"done": True, "done_reason": "stop", "message": {"content": json.dumps({"content": "x" * 6001})}},
            {"done": True, "done_reason": "stop", "message": {"content": '{"content":"   "}'}},
            {"done": True, "done_reason": "stop", "message": {"content": "not json"}},
            {"done": True, "done_reason": "tool_calls", "message": {"content": '{"content":"ok"}'}},
        ]
        for index, response in enumerate(cases):
            with self.subTest(case=index):
                gateway = FakeGateway()
                plugin = MultiAgentPlugin(gateway)  # type: ignore[arg-type]
                invoke = gateway.invoke

                async def invalid_stage(plugin_id, action, payload, invoke=invoke, response=response):
                    result = await invoke(plugin_id, action, payload)
                    return response if action == "chat" else result

                with (
                    patch.object(gateway, "invoke", side_effect=invalid_stage),
                    self.assertRaises(MultiAgentProviderError),
                ):
                    asyncio.run(plugin.invoke("run", {"approved": True, "request": "Plan"}))
                self.assertEqual(len([call for call in gateway.calls if call[1] == "chat"]), 1)

    def test_api_maps_missing_approval(self) -> None:
        gateway = PluginGateway()
        gateway.register(MultiAgentPlugin(FakeGateway()))  # type: ignore[arg-type]
        app = create_app(gateway)

        async def exercise() -> int:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/plugins/multi_agent/actions/run",
                    json={"payload": {"request": "Plan"}},
                )
                return response.status_code

        self.assertEqual(asyncio.run(exercise()), 403)

    def test_automatic_routing_uses_each_role_area_and_reports_selected_models(
        self,
    ) -> None:
        gateway = FakeGateway(
            models=["planner-model", "source-model", "coder-model", "answer-model"]
        )
        plugin = MultiAgentPlugin(gateway)  # type: ignore[arg-type]
        selections = {
            "planning": "planner-model",
            "source_grounded": "source-model",
            "code_change": "coder-model",
            "answer": "answer-model",
        }
        with patch.object(
            plugin.model_routing,
            "choose",
            side_effect=lambda area, requested, catalog: requested or selections[area],
        ) as choose:
            result = asyncio.run(
                plugin.invoke("run", {"approved": True, "request": "Design a parser."})
            )
        self.assertEqual(
            [call.args[0] for call in choose.call_args_list],
            ["planning", "source_grounded", "code_change", "code_change", "answer"],
        )
        self.assertEqual(
            [stage["model"] for stage in result["stages"]],
            [
                "planner-model",
                "source-model",
                "coder-model",
                "coder-model",
                "answer-model",
            ],
        )
        self.assertIsNone(result["model"])
        self.assertEqual(result["routing_mode"], "area_priority")
        self.assertEqual(result["models_by_role"]["reviewer"], "coder-model")
        self.assertTrue(all(stage["description"] for stage in result["stages"]))

    def test_explicit_single_model_overrides_every_role(self) -> None:
        gateway = FakeGateway(models=["chosen", "other"])
        plugin = MultiAgentPlugin(gateway)  # type: ignore[arg-type]
        result = asyncio.run(
            plugin.invoke(
                "run", {"approved": True, "request": "Plan", "model": "chosen"}
            )
        )
        self.assertEqual(result["model"], "chosen")
        self.assertEqual(result["routing_mode"], "explicit")
        self.assertTrue(all(stage["model"] == "chosen" for stage in result["stages"]))

    def test_roles_describe_routing_without_inference_or_approval(self) -> None:
        gateway = FakeGateway()
        plugin = MultiAgentPlugin(gateway)  # type: ignore[arg-type]
        result = asyncio.run(plugin.invoke("roles", {}))
        self.assertEqual(len(result["roles"]), 5)
        self.assertEqual(result["roles"][1]["routing_area"], "source_grounded")
        self.assertEqual(result["tools_used"], [])
        self.assertEqual([call[1] for call in gateway.calls], ["models"])


if __name__ == "__main__":
    unittest.main()
