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
from app.plugins.contracts import PluginManifest
from app.plugins.gateway import PluginGateway
from app.plugins.task_assistant import (
    TaskAssistantApprovalRequired,
    TaskAssistantPlugin,
    TaskAssistantProviderError,
)


class TaskAssistantPluginTests(unittest.TestCase):
    class FakeGateway:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, dict[str, Any]]] = []
            self.task = {
                "task_id": "a" * 32,
                "request": "Fix the parsing edge case.",
                "approved": True,
                "steps": [{"step_index": 0, "title": "Add bounded parsing", "status": "in_progress"}],
            }
            self.source = {"path": "src/parser.py", "content": "def parse(value):\n    return value\n"}
            self.sources: dict[str, dict[str, str]] = {}
            self.model_response = {
                "message": {
                    "content": json.dumps({
                        "summary": "Add a None guard.",
                        "start_line": 2,
                        "original_lines": ["    return value"],
                        "replacement_lines": ["    if value is None:", "        return None", "    return value"],
                        "path": "other.py",
                    })
                }
            }

        async def invoke(self, plugin_id: str, action: str, payload: dict[str, Any]) -> Any:
            self.calls.append((plugin_id, action, payload))
            if (plugin_id, action) == ("tasks", "get"):
                return {"task": self.task}
            if (plugin_id, action) == ("workspace", "read"):
                return self.sources.get(payload["path"], self.source)
            if (plugin_id, action) == ("ollama", "models"):
                return {
                    "default_model": "qwen3.6:latest",
                    "models": [
                        {"name": "qwen3.6:latest"},
                        {"name": "gemma:7b"},
                        {"name": "nomic-embed-text:latest"},
                    ],
                }
            if (plugin_id, action) == ("ollama", "chat"):
                return self.model_response
            raise AssertionError(f"Unexpected gateway action: {plugin_id}/{action}")

    def test_proposal_reads_one_selected_file_and_never_writes_or_executes(self) -> None:
        gateway = self.FakeGateway()
        plugin = TaskAssistantPlugin(gateway)  # type: ignore[arg-type]

        async def exercise() -> dict[str, Any]:
            return await plugin.invoke("propose_change", {
                "approved": True,
                "task_id": "a" * 32,
                "step_index": 0,
                "path": "src/parser.py",
                "context_paths": ["pyproject.toml"],
                "instruction": "Handle None input.",
            })

        proposal = asyncio.run(exercise())

        self.assertEqual(proposal["path"], "src/parser.py")
        self.assertEqual(proposal["context_paths"], ["pyproject.toml"])
        self.assertEqual(proposal["model"], "qwen3.6:latest")
        self.assertIn("if value is None", proposal["content"])
        self.assertEqual(proposal["line_range"], {"start": 2, "end": 2})
        self.assertFalse(proposal["written"])
        self.assertFalse(proposal["executed"])
        self.assertEqual([call[:2] for call in gateway.calls], [
            ("tasks", "get"), ("workspace", "read"), ("workspace", "read"),
            ("ollama", "models"), ("ollama", "chat"),
        ])
        prompt = gateway.calls[-1][2]["system_prompt"]
        self.assertIn("untrusted data", prompt)
        self.assertIn("Do not execute code or commands", prompt)
        self.assertEqual(gateway.calls[-1][2]["max_output_tokens"], 4_096)
        self.assertEqual(gateway.calls[-1][2]["max_context_tokens"], 16_384)
        self.assertFalse(gateway.calls[-1][2]["think"])
        model_context = json.loads(gateway.calls[-1][2]["message"])
        self.assertEqual(model_context["supporting_files"][0]["path"], "pyproject.toml")
        self.assertEqual(model_context["supporting_files"][0]["content"], "1: def parse(value):\n2:     return value")
        self.assertEqual([call[2]["path"] for call in gateway.calls if call[0] == "workspace"], [
            "src/parser.py", "pyproject.toml",
        ])

    def test_proposal_requires_approval_and_active_step(self) -> None:
        gateway = self.FakeGateway()
        plugin = TaskAssistantPlugin(gateway)  # type: ignore[arg-type]
        payload = {"task_id": "a" * 32, "step_index": 0, "path": "src/parser.py"}

        async def exercise() -> None:
            with self.assertRaises(TaskAssistantApprovalRequired):
                await plugin.invoke("propose_change", payload)
            gateway.task["steps"][0]["status"] = "pending"
            with self.assertRaisesRegex(ValueError, "in-progress"):
                await plugin.invoke("propose_change", {**payload, "approved": True})

        asyncio.run(exercise())
        self.assertFalse(any(action == "chat" for _, action, _ in gateway.calls))

    def test_proposal_requires_an_installed_non_embedding_local_model(self) -> None:
        gateway = self.FakeGateway()
        plugin = TaskAssistantPlugin(gateway)  # type: ignore[arg-type]
        payload = {"approved": True, "task_id": "a" * 32, "step_index": 0, "path": "src/parser.py"}

        async def exercise() -> None:
            with self.assertRaises(TaskAssistantProviderError):
                await plugin.invoke("propose_change", {**payload, "model": "missing:latest"})
            with self.assertRaisesRegex(ValueError, "Embedding-only"):
                await plugin.invoke("propose_change", {**payload, "model": "nomic-embed-text:latest"})

        asyncio.run(exercise())
        self.assertFalse(any(action == "chat" for _, action, _ in gateway.calls))

    def test_code_change_proposal_uses_area_priority_when_model_is_automatic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            preferences_path = Path(directory) / "model-area-priorities.json"
            preferences_path.write_text(json.dumps({
                "area_priorities": {"code_change": ["gemma:7b", "qwen3.6:latest"]},
            }), encoding="utf-8")
            with patch.dict(os.environ, {"MODEL_ROUTING_PREFERENCES": str(preferences_path)}):
                gateway = self.FakeGateway()
                plugin = TaskAssistantPlugin(gateway)  # type: ignore[arg-type]
                proposal = asyncio.run(plugin.invoke("propose_change", {
                    "approved": True,
                    "task_id": "a" * 32,
                    "step_index": 0,
                    "path": "src/parser.py",
                }))

        self.assertEqual(proposal["model"], "gemma:7b")
        self.assertEqual(gateway.calls[-1][2]["model"], "gemma:7b")

    def test_proposal_rejects_oversized_source_context(self) -> None:
        gateway = self.FakeGateway()
        gateway.source["content"] = "x" * (TaskAssistantPlugin.max_context_characters + 1)
        plugin = TaskAssistantPlugin(gateway)  # type: ignore[arg-type]

        async def exercise() -> None:
            with self.assertRaisesRegex(ValueError, "model context limit"):
                await plugin.invoke("propose_change", {
                    "approved": True, "task_id": "a" * 32, "step_index": 0, "path": "src/parser.py",
                })

        asyncio.run(exercise())
        self.assertFalse(any(action == "chat" for _, action, _ in gateway.calls))

    def test_proposal_rejects_duplicate_or_excess_context_paths(self) -> None:
        gateway = self.FakeGateway()
        plugin = TaskAssistantPlugin(gateway)  # type: ignore[arg-type]
        base = {"approved": True, "task_id": "a" * 32, "step_index": 0, "path": "src/parser.py"}

        async def exercise() -> None:
            with self.assertRaisesRegex(ValueError, "unique"):
                await plugin.invoke("propose_change", {**base, "context_paths": ["src/parser.py"]})
            with self.assertRaisesRegex(ValueError, "at most"):
                await plugin.invoke("propose_change", {**base, "context_paths": ["a", "b", "c", "d"]})

        asyncio.run(exercise())
        self.assertFalse(any(action == "chat" for _, action, _ in gateway.calls))

    def test_api_routes_proposals_and_requires_explicit_approval(self) -> None:
        class FakeTasks:
            manifest = PluginManifest("tasks", "Tasks", "test", ("get",))

            async def invoke(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
                return {"task": {
                    "task_id": "a" * 32,
                    "request": "Fix parser",
                    "approved": True,
                    "steps": [{"step_index": 0, "title": "Handle None", "status": "in_progress"}],
                }}

        class FakeWorkspace:
            manifest = PluginManifest("workspace", "Workspace", "test", ("read",))

            async def invoke(self, action: str, payload: dict[str, Any]) -> dict[str, str]:
                return {"path": payload["path"], "content": "def parse(value): return value\n"}

        class FakeOllama:
            manifest = PluginManifest("ollama", "Ollama", "test", ("models", "chat"))

            async def invoke(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
                if action == "models":
                    return {"default_model": "qwen3.6:latest", "models": [{"name": "qwen3.6:latest"}]}
                return {"message": {"content": json.dumps({
                    "summary": "Add a None guard.",
                    "start_line": 1,
                    "original_lines": ["def parse(value): return value"],
                    "replacement_lines": ["def parse(value):", "    return None if value is None else value"],
                })}}

        gateway = PluginGateway()
        gateway.register(FakeTasks())  # type: ignore[arg-type]
        gateway.register(FakeWorkspace())  # type: ignore[arg-type]
        gateway.register(FakeOllama())  # type: ignore[arg-type]
        gateway.register(TaskAssistantPlugin(gateway))
        app = create_app(gateway)

        async def exercise_api() -> tuple[httpx.Response, httpx.Response]:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                payload = {"task_id": "a" * 32, "step_index": 0, "path": "src/parser.py"}
                denied = await client.post(
                    "/api/plugins/task_assistant/actions/propose_change", json={"payload": payload}
                )
                approved = await client.post(
                    "/api/plugins/task_assistant/actions/propose_change",
                    json={"payload": {**payload, "approved": True}},
                )
                return denied, approved

        denied, approved = asyncio.run(exercise_api())

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(approved.status_code, 200)
        self.assertFalse(approved.json()["written"])
        self.assertIn("return None", approved.json()["content"])

    def test_proposal_rejects_line_ranges_that_do_not_match_source(self) -> None:
        gateway = self.FakeGateway()
        plugin = TaskAssistantPlugin(gateway)  # type: ignore[arg-type]
        payload = {"approved": True, "task_id": "a" * 32, "step_index": 0, "path": "src/parser.py"}

        async def exercise() -> None:
            gateway.model_response["message"]["content"] = json.dumps({
                "summary": "No match", "start_line": 1,
                "original_lines": ["not present"], "replacement_lines": ["change"],
            })
            with self.assertRaisesRegex(TaskAssistantProviderError, "do not match"):
                await plugin.invoke("propose_change", payload)
            gateway.model_response["message"]["content"] = json.dumps({
                "summary": "Invalid range", "start_line": 3,
                "original_lines": ["missing"], "replacement_lines": ["changed"],
            })
            with self.assertRaisesRegex(TaskAssistantProviderError, "range exceeds"):
                await plugin.invoke("propose_change", payload)
            gateway.model_response = {"done_reason": "length", "message": {"content": "{"}}
            with self.assertRaisesRegex(TaskAssistantProviderError, "truncated"):
                await plugin.invoke("propose_change", payload)

        asyncio.run(exercise())

    def test_markdown_evidence_can_cite_a_supporting_file(self) -> None:
        gateway = self.FakeGateway()
        target_line = "## Install"
        evidence_line = "The installer checks `docker version` before retrying."
        gateway.source = {"path": "README-OFFLINE.md", "content": f"{target_line}\n"}
        gateway.sources["installer.ps1"] = {"path": "installer.ps1", "content": f"{evidence_line}\n"}
        gateway.model_response["message"]["content"] = json.dumps({
            "summary": "Add sourced troubleshooting.",
            "start_line": 1,
            "original_lines": [target_line],
            "replacement_lines": [target_line, "- Check `docker version` before retrying."],
            "evidence": [{
                "replacement_line": 2,
                "path": "installer.ps1",
                "line": 1,
            }],
        })
        plugin = TaskAssistantPlugin(gateway)  # type: ignore[arg-type]

        proposal = asyncio.run(plugin.invoke("propose_change", {
            "approved": True,
            "task_id": "a" * 32,
            "step_index": 0,
            "path": "README-OFFLINE.md",
            "context_paths": ["installer.ps1"],
        }))

        self.assertIn("Check `docker version`", proposal["content"])
        self.assertEqual(proposal["evidence"][0]["quote"], evidence_line)
        self.assertEqual(proposal["evidence"][0]["start_line"], 1)
        self.assertEqual(proposal["evidence"][0]["replacement_line"], 2)
        request_schema = next(
            call[2]["response_schema"] for call in gateway.calls if call[1] == "chat"
        )
        self.assertIn("evidence", request_schema["required"])
        self.assertEqual(
            request_schema["properties"]["evidence"]["items"]["properties"]["path"]["enum"],
            ["README-OFFLINE.md", "installer.ps1"],
        )

    def test_markdown_proposal_requires_matching_evidence_and_rejects_unsupported_literals(self) -> None:
        gateway = self.FakeGateway()
        source_line = "The installer checks `docker version` before retrying."
        gateway.source = {"path": "README-OFFLINE.md", "content": f"## Install\n{source_line}\n"}
        gateway.model_response["message"]["content"] = json.dumps({
            "summary": "Add sourced troubleshooting.",
            "start_line": 2,
            "original_lines": [source_line],
            "replacement_lines": [source_line, "- Check `docker version` before retrying."],
            "evidence": [{
                "replacement_line": 2,
                "path": "README-OFFLINE.md",
                "line": 2,
            }],
        })
        plugin = TaskAssistantPlugin(gateway)  # type: ignore[arg-type]
        payload = {
            "approved": True,
            "task_id": "a" * 32,
            "step_index": 0,
            "path": "README-OFFLINE.md",
        }

        proposal = asyncio.run(plugin.invoke("propose_change", payload))
        self.assertIn("Check `docker version`", proposal["content"])

        gateway.model_response["message"]["content"] = json.dumps({
            "summary": "Add uncited text.",
            "start_line": 2,
            "original_lines": [source_line],
            "replacement_lines": [source_line, "- Check the engine before retrying."],
            "evidence": [],
        })
        with self.assertRaisesRegex(TaskAssistantProviderError, "source evidence items"):
            asyncio.run(plugin.invoke("propose_change", payload))

        gateway.model_response["message"]["content"] = json.dumps({
            "summary": "Add an invalid replacement citation.",
            "start_line": 2,
            "original_lines": [source_line],
            "replacement_lines": [source_line, "- Check the engine before retrying."],
            "evidence": [{
                "replacement_line": 3,
                "path": "README-OFFLINE.md",
                "line": 2,
            }],
        })
        with self.assertRaisesRegex(TaskAssistantProviderError, "reference a replacement line"):
            asyncio.run(plugin.invoke("propose_change", payload))

        gateway.model_response["message"]["content"] = json.dumps({
            "summary": "Add an out-of-range citation.",
            "start_line": 2,
            "original_lines": [source_line],
            "replacement_lines": [source_line, "- Check the engine before retrying."],
            "evidence": [{
                "replacement_line": 2,
                "path": "README-OFFLINE.md",
                "line": 99,
            }],
        })
        with self.assertRaisesRegex(TaskAssistantProviderError, "line exceeds"):
            asyncio.run(plugin.invoke("propose_change", payload))

        gateway.model_response["message"]["content"] = json.dumps({
            "summary": "Add unsupported recovery advice.",
            "start_line": 2,
            "original_lines": [source_line],
            "replacement_lines": [source_line, '- The status indicator shows "Running".'],
            "evidence": [{
                "replacement_line": 2,
                "path": "README-OFFLINE.md",
                "line": 2,
            }],
        })
        with self.assertRaisesRegex(TaskAssistantProviderError, "technical literal"):
            asyncio.run(plugin.invoke("propose_change", payload))

        gateway.model_response["message"]["content"] = json.dumps({
            "summary": "Add an unsupported command.",
            "start_line": 2,
            "original_lines": [source_line],
            "replacement_lines": [source_line, "- Inspect `docker run --rm alpine ls /mnt/.ollama/models`."],
            "evidence": [{
                "replacement_line": 2,
                "path": "README-OFFLINE.md",
                "line": 2,
            }],
        })
        with self.assertRaisesRegex(TaskAssistantProviderError, "command or technical literal"):
            asyncio.run(plugin.invoke("propose_change", payload))


if __name__ == "__main__":
    unittest.main()