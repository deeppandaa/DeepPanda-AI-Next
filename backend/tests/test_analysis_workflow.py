from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx

from app.main import create_app
from app.plugins.gateway import PluginGateway
from app.plugins.analysis_workflow import (
    AnalysisWorkflowApprovalRequired,
    AnalysisWorkflowPlugin,
    AnalysisWorkflowProviderError,
)


class AnalysisWorkflowPluginTests(unittest.TestCase):
    document_id = "a" * 32

    class FakeGateway:
        def __init__(self, report: str | None = None, models: list[str] | None = None) -> None:
            self.report = report or json.dumps({
                "summary": "The file exports a startup entrypoint.",
                "findings": [{
                    "title": "Dynamic runtime selection",
                    "severity": "info",
                    "evidence": "L0006: export const entrypoint = true;",
                    "analysis": "The entrypoint selects a deferred or eager runtime based on configuration.",
                    "recommendation": "Review the runtime-specific configuration before enabling optional providers.",
                }],
            })
            self.models = models or ["gemma:7b", "deepseek-coder:6.7b"]
            self.calls: list[tuple[str, str, dict[str, Any]]] = []

        async def invoke(self, plugin_id: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
            self.calls.append((plugin_id, action, payload))
            if (plugin_id, action) == ("documents", "preview"):
                return {
                    "document_id": AnalysisWorkflowPluginTests.document_id,
                    "filename": "morluto-rea-main.ts",
                    "extension": ".ts",
                    "content": (
                        "Source: https://github.com/morluto/rea/blob/abc/src/main.ts\n"
                        "Repository: morluto/rea\nPath: src/main.ts\nGitHub blob: abc\n\n"
                        "export const entrypoint = true;\n"
                    ),
                    "indexed_characters": 140,
                }
            if (plugin_id, action) == ("ollama", "models"):
                return {"models": [{"name": name} for name in self.models]}
            if (plugin_id, action) == ("ollama", "chat"):
                return {"model": payload["model"], "message": {"content": self.report}}
            raise AssertionError(f"Unexpected gateway action: {plugin_id}/{action}")

    def test_analysis_requires_explicit_approval(self) -> None:
        plugin = AnalysisWorkflowPlugin(self.FakeGateway())  # type: ignore[arg-type]

        async def exercise() -> None:
            with self.assertRaises(AnalysisWorkflowApprovalRequired):
                await plugin.invoke("run", {
                    "document_id": self.document_id,
                    "question": "Review the entrypoint",
                    "model": "gemma:7b",
                })

        asyncio.run(exercise())

    def test_api_registers_analysis_and_maps_missing_approval(self) -> None:
        gateway = PluginGateway()
        gateway.register(AnalysisWorkflowPlugin(gateway))
        app = create_app(gateway)

        async def exercise() -> int:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/plugins/analysis/actions/run",
                    json={"payload": {"document_id": self.document_id, "question": "review", "model": "gemma:7b"}},
                )
                return response.status_code

        self.assertEqual(asyncio.run(exercise()), 403)

    def test_langgraph_inspects_analyzes_and_returns_attributed_report(self) -> None:
        gateway = self.FakeGateway()
        plugin = AnalysisWorkflowPlugin(gateway)  # type: ignore[arg-type]

        async def exercise() -> dict[str, Any]:
            return await plugin.invoke("run", {
                "approved": True,
                "document_id": self.document_id,
                "question": "Summarize the entrypoint and review trust boundaries.",
                "model": "gemma:7b",
            })

        report = asyncio.run(exercise())

        self.assertEqual(report["status"], "analyzed")
        self.assertTrue(report["static_only"])
        self.assertEqual(report["model"], "gemma:7b")
        self.assertEqual(report["source"]["document_id"], self.document_id)
        self.assertIn("github.com/morluto/rea/blob/abc/src/main.ts", report["source"]["url"])
        self.assertEqual(report["findings"][0]["severity"], "info")
        self.assertEqual(report["unverified_findings"], 0)
        self.assertEqual(report["findings"][0]["evidence"], "L0006: export const entrypoint = true;")
        self.assertEqual([call[:2] for call in gateway.calls], [
            ("documents", "preview"), ("ollama", "models"), ("ollama", "chat"),
        ])
        system_prompt = gateway.calls[-1][2]["system_prompt"]
        self.assertIn("untrusted data", system_prompt)
        self.assertIn("execute code", system_prompt)
        self.assertIn("0006 export const entrypoint", gateway.calls[-1][2]["message"])

    def test_analysis_uses_source_grounded_priority_when_model_is_automatic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            preferences_path = Path(directory) / "model-area-priorities.json"
            preferences_path.write_text(json.dumps({
                "area_priorities": {"source_grounded": ["deepseek-coder:6.7b", "gemma:7b"]},
            }), encoding="utf-8")
            with patch.dict(os.environ, {"MODEL_ROUTING_PREFERENCES": str(preferences_path)}):
                gateway = self.FakeGateway(models=["gemma:7b", "deepseek-coder:6.7b"])
                plugin = AnalysisWorkflowPlugin(gateway)  # type: ignore[arg-type]
                report = asyncio.run(plugin.invoke("run", {
                    "approved": True,
                    "document_id": self.document_id,
                    "question": "Summarize the entrypoint.",
                }))

        self.assertEqual(report["model"], "deepseek-coder:6.7b")
        self.assertEqual(gateway.calls[-1][2]["model"], "deepseek-coder:6.7b")

    def test_findings_without_exact_in_range_source_quotes_are_omitted(self) -> None:
        report_data = {
            "summary": "The model proposed an unsupported claim.",
            "findings": [{
                "title": "Unsupported issue",
                "severity": "high",
                "evidence": "Lines 138-144: untrusted arguments cause injection.",
                "analysis": "The cited behavior is not present in the selected source.",
                "recommendation": "Review the actual implementation.",
            }],
        }
        plugin = AnalysisWorkflowPlugin(self.FakeGateway(report=json.dumps(report_data)))  # type: ignore[arg-type]

        async def exercise() -> dict[str, Any]:
            return await plugin.invoke("run", {
                "approved": True,
                "document_id": self.document_id,
                "question": "Review the entrypoint",
                "model": "gemma:7b",
            })

        report = asyncio.run(exercise())
        self.assertEqual(report["findings"], [])
        self.assertEqual(report["unverified_findings"], 1)

    def test_analysis_rejects_uninstalled_and_cloud_models(self) -> None:
        plugin = AnalysisWorkflowPlugin(self.FakeGateway(models=["gemma:7b", "remote:cloud"]))  # type: ignore[arg-type]

        async def exercise(model: str) -> None:
            with self.assertRaisesRegex(ValueError, "installed local"):
                await plugin.invoke("run", {
                    "approved": True,
                    "document_id": self.document_id,
                    "question": "Review the entrypoint",
                    "model": model,
                })

        asyncio.run(exercise("missing:latest"))
        asyncio.run(exercise("remote:cloud"))

    def test_invalid_model_report_is_rejected(self) -> None:
        plugin = AnalysisWorkflowPlugin(self.FakeGateway(report="not-json"))  # type: ignore[arg-type]

        async def exercise() -> None:
            with self.assertRaises(AnalysisWorkflowProviderError):
                await plugin.invoke("run", {
                    "approved": True,
                    "document_id": self.document_id,
                    "question": "Review the entrypoint",
                    "model": "gemma:7b",
                })

        asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()