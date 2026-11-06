from __future__ import annotations

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
from app.plugins.tasks import TaskApprovalRequired, TasksPlugin
from app.plugins.workspace import WorkspacePlugin


class TasksPluginTests(unittest.TestCase):
    def test_draft_endpoint_uses_planning_priority_when_model_is_automatic(self) -> None:
        class DraftModel:
            manifest = PluginManifest("ollama", "Test Model", "test", ("models", "chat"))

            def __init__(self) -> None:
                self.chat_payload: dict[str, object] | None = None

            async def invoke(self, action: str, payload: dict[str, object]) -> dict[str, object]:
                if action == "models":
                    return {
                        "default_model": "qwen3.6:latest",
                        "models": [{"name": "qwen3.6:latest"}, {"name": "gemma:7b"}],
                    }
                self.chat_payload = payload
                return {"model": payload["model"], "message": {"content": '{"steps":["Inspect","Test"]}'}}

        with tempfile.TemporaryDirectory() as directory:
            priorities_path = Path(directory) / "model-area-priorities.json"
            priorities_path.write_text(json.dumps({
                "area_priorities": {"planning": ["gemma:7b", "qwen3.6:latest"]},
            }), encoding="utf-8")
            with patch.dict(os.environ, {"MODEL_ROUTING_PREFERENCES": str(priorities_path)}):
                gateway = PluginGateway()
                model = DraftModel()
                gateway.register(model)
                app = create_app(gateway)

                async def send() -> httpx.Response:
                    async with httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=app), base_url="http://test"
                    ) as client:
                        return await client.post("/api/tasks/draft", json={"request": "Plan a change"})

                response = asyncio.run(send())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["model"], "gemma:7b")
        self.assertEqual(model.chat_payload["model"], "gemma:7b")

    def test_draft_endpoint_uses_gateway_model_without_persisting_plan(self) -> None:
        class DraftModel:
            manifest = PluginManifest("ollama", "Test Model", "test", ("chat",))

            def __init__(self) -> None:
                self.payload: dict[str, object] | None = None

            async def invoke(self, action: str, payload: dict[str, object]) -> dict[str, object]:
                self.payload = payload
                return {"message": {"content": '{"steps":["Inspect parser", "Add regression test"]}'}}

        with tempfile.TemporaryDirectory() as directory:
            gateway = PluginGateway()
            tasks = TasksPlugin(Path(directory) / "tasks.db")
            model = DraftModel()
            gateway.register(tasks)
            gateway.register(model)
            app = create_app(gateway)

            async def exercise_api() -> tuple[httpx.Response, dict[str, object]]:
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    response = await client.post(
                        "/api/tasks/draft",
                        json={"request": "Fix parser edge cases", "model": "qwen3.8:latest"},
                    )
                stored = await tasks.invoke("list", {})
                return response, stored

            response, stored = asyncio.run(exercise_api())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["steps"], ["Inspect parser", "Add regression test"])
        self.assertEqual(model.payload["model"], "qwen3.8:latest")
        self.assertEqual(model.payload["message"], "Fix parser edge cases")
        self.assertFalse(model.payload["think"])
        self.assertEqual(model.payload["max_output_tokens"], 2_048)
        self.assertEqual(model.payload["max_context_tokens"], 8_192)
        self.assertIn("steps", model.payload["response_schema"]["required"])
        self.assertEqual(stored["tasks"], [])

    def test_draft_endpoint_rejects_malformed_model_output(self) -> None:
        class DraftModel:
            manifest = PluginManifest("ollama", "Test Model", "test", ("chat",))

            async def invoke(self, action: str, payload: dict[str, object]) -> dict[str, object]:
                return {"message": {"content": "not a JSON task plan"}}

        gateway = PluginGateway()
        gateway.register(DraftModel())
        app = create_app(gateway)

        async def exercise_api() -> httpx.Response:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                return await client.post("/api/tasks/draft", json={"request": "Plan a parser fix"})

        response = asyncio.run(exercise_api())
        self.assertEqual(response.status_code, 502)

    def test_draft_endpoint_reports_truncated_model_output(self) -> None:
        class DraftModel:
            manifest = PluginManifest("ollama", "Test Model", "test", ("chat",))

            async def invoke(self, action: str, payload: dict[str, object]) -> dict[str, object]:
                return {"done_reason": "length", "message": {"content": "{"}}

        gateway = PluginGateway()
        gateway.register(DraftModel())
        app = create_app(gateway)

        async def exercise_api() -> httpx.Response:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.post("/api/tasks/draft", json={"request": "Plan a parser fix"})

        response = asyncio.run(exercise_api())

        self.assertEqual(response.status_code, 502)
        selfIn = response.json()["detail"]
        self.assertIn("token sınırında kesildi", selfIn)

    def test_plan_and_step_progress_require_approval_and_record_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            gateway = PluginGateway()
            gateway.register(TasksPlugin(Path(directory) / "tasks.db"))
            app = create_app(gateway)

            async def exercise_api() -> tuple[httpx.Response, ...]:
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    created = await client.post(
                        "/api/plugins/tasks/actions/create",
                        json={"payload": {"request": "Fix the parser", "steps": ["Add regression test", "Fix parsing"]}},
                    )
                    task_id = created.json()["task_id"]
                    unapproved_step = await client.post(
                        "/api/plugins/tasks/actions/update_step",
                        json={"payload": {
                            "task_id": task_id,
                            "step_index": 0,
                            "status": "in_progress",
                            "approved": True,
                        }},
                    )
                    approved = await client.post(
                        "/api/plugins/tasks/actions/approve",
                        json={"payload": {"task_id": task_id, "approved": True}},
                    )
                    started = await client.post(
                        "/api/plugins/tasks/actions/update_step",
                        json={"payload": {
                            "task_id": task_id,
                            "step_index": 0,
                            "status": "in_progress",
                            "approved": True,
                        }},
                    )
                    completed = await client.post(
                        "/api/plugins/tasks/actions/update_step",
                        json={"payload": {
                            "task_id": task_id,
                            "step_index": 0,
                            "status": "completed",
                            "evidence": "Regression test passes.",
                            "approved": True,
                        }},
                    )
                    history = await client.post(
                        "/api/plugins/tasks/actions/get",
                        json={"payload": {"task_id": task_id}},
                    )
                    return created, unapproved_step, approved, started, completed, history

            created, unapproved_step, approved, started, completed, history = asyncio.run(exercise_api())

        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["status"], "plan_only")
        self.assertEqual(unapproved_step.status_code, 403)
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(started.status_code, 200)
        self.assertEqual(completed.status_code, 200)
        task = history.json()["task"]
        self.assertEqual(task["steps"][0]["status"], "completed")
        self.assertEqual(task["steps"][0]["evidence"], "Regression test passes.")
        self.assertEqual(len(task["events"]), 4)

    def test_completed_step_requires_evidence_and_cannot_be_reopened(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plugin = TasksPlugin(Path(directory) / "tasks.db")

            async def exercise_plugin() -> tuple[dict[str, object], dict[str, object]]:
                created = await plugin.invoke("create", {"request": "Task", "steps": ["Step"]})
                task_id = created["task_id"]
                await plugin.invoke("approve", {"task_id": task_id, "approved": True})
                await plugin.invoke(
                    "update_step",
                    {"task_id": task_id, "step_index": 0, "status": "in_progress", "approved": True},
                )
                with self.assertRaises(ValueError):
                    await plugin.invoke(
                        "update_step",
                        {"task_id": task_id, "step_index": 0, "status": "completed", "approved": True},
                    )
                await plugin.invoke(
                    "update_step",
                    {
                        "task_id": task_id,
                        "step_index": 0,
                        "status": "completed",
                        "evidence": "Passed",
                        "approved": True,
                    },
                )
                with self.assertRaises(ValueError):
                    await plugin.invoke(
                        "update_step",
                        {"task_id": task_id, "step_index": 0, "status": "in_progress", "approved": True},
                    )
                return created, await plugin.invoke("get", {"task_id": task_id})

            created, result = asyncio.run(exercise_plugin())

        self.assertEqual(result["task"]["status"], "completed")
        self.assertTrue(created["task_id"])

    def test_blocked_step_can_be_retried_and_completed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plugin = TasksPlugin(Path(directory) / "tasks.db")

            async def exercise_plugin() -> dict[str, object]:
                created = await plugin.invoke("create", {"request": "Task", "steps": ["Step"]})
                task_id = created["task_id"]
                await plugin.invoke("approve", {"task_id": task_id, "approved": True})
                await plugin.invoke(
                    "update_step",
                    {"task_id": task_id, "step_index": 0, "status": "in_progress", "approved": True},
                )
                await plugin.invoke(
                    "update_step",
                    {
                        "task_id": task_id,
                        "step_index": 0,
                        "status": "blocked",
                        "evidence": "Waiting for a dependency.",
                        "approved": True,
                    },
                )
                await plugin.invoke(
                    "update_step",
                    {"task_id": task_id, "step_index": 0, "status": "in_progress", "approved": True},
                )
                await plugin.invoke(
                    "update_step",
                    {
                        "task_id": task_id,
                        "step_index": 0,
                        "status": "completed",
                        "evidence": "Dependency resolved; tests pass.",
                        "approved": True,
                    },
                )
                return await plugin.invoke("get", {"task_id": task_id})

            result = asyncio.run(exercise_plugin())

        self.assertEqual(result["task"]["status"], "completed")
        self.assertEqual(result["task"]["steps"][0]["evidence"], "Dependency resolved; tests pass.")

    def test_plan_and_evidence_survive_plugin_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "tasks.db"
            first_plugin = TasksPlugin(database_path)

            async def create_and_complete() -> str:
                created = await first_plugin.invoke("create", {"request": "Task", "steps": ["Step"]})
                task_id = created["task_id"]
                await first_plugin.invoke("approve", {"task_id": task_id, "approved": True})
                await first_plugin.invoke(
                    "update_step",
                    {"task_id": task_id, "step_index": 0, "status": "in_progress", "approved": True},
                )
                await first_plugin.invoke(
                    "update_step",
                    {
                        "task_id": task_id,
                        "step_index": 0,
                        "status": "completed",
                        "evidence": "Verified after restart.",
                        "approved": True,
                    },
                )
                return task_id

            task_id = asyncio.run(create_and_complete())
            result = asyncio.run(TasksPlugin(database_path).invoke("get", {"task_id": task_id}))

        self.assertEqual(result["task"]["status"], "completed")
        self.assertEqual(result["task"]["steps"][0]["evidence"], "Verified after restart.")
        self.assertEqual(len(result["task"]["events"]), 4)

    def test_test_run_audit_requires_approval_and_records_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plugin = TasksPlugin(Path(directory) / "tasks.db")

            async def exercise_plugin() -> dict[str, object]:
                created = await plugin.invoke("create", {"request": "Test parser", "steps": ["Add tests"]})
                task_id = created["task_id"]
                await plugin.invoke("approve", {"task_id": task_id, "approved": True})
                await plugin.invoke(
                    "update_step",
                    {"task_id": task_id, "step_index": 0, "status": "in_progress", "approved": True},
                )
                payload = {
                    "task_id": task_id,
                    "step_index": 0,
                    "command": ["python", "-m", "unittest"],
                    "passed": True,
                    "returncode": 0,
                    "output": "Ran 3 tests: OK",
                }
                with self.assertRaises(TaskApprovalRequired):
                    await plugin.invoke("record_test_run", payload)
                payload["approved"] = True
                await plugin.invoke("record_test_run", payload)
                return await plugin.invoke("get", {"task_id": task_id})

            result = asyncio.run(exercise_plugin())

        test_event = next(event for event in result["task"]["events"] if event["action"] == "test_run")
        self.assertTrue(test_event["detail"]["passed"])
        self.assertEqual(test_event["detail"]["command"], ["python", "-m", "unittest"])

    def test_approved_workspace_test_run_is_attached_to_active_step(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            gateway = PluginGateway()
            tasks = TasksPlugin(Path(directory) / "tasks.db")
            workspace = WorkspacePlugin(Path(directory) / "workspace", Path(directory) / "backups")
            workspace.root.mkdir()
            gateway.register(tasks)
            gateway.register(workspace)
            app = create_app(gateway)

            async def exercise_api() -> tuple[
                httpx.Response, httpx.Response, httpx.Response, httpx.Response, httpx.Response
            ]:
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    created = await client.post(
                        "/api/plugins/tasks/actions/create",
                        json={"payload": {"request": "Test task", "steps": ["Add parser tests"]}},
                    )
                    task_id = created.json()["task_id"]
                    await client.post(
                        "/api/plugins/tasks/actions/approve",
                        json={"payload": {"task_id": task_id, "approved": True}},
                    )
                    await client.post(
                        "/api/plugins/tasks/actions/update_step",
                        json={"payload": {
                            "task_id": task_id,
                            "step_index": 0,
                            "status": "in_progress",
                            "approved": True,
                        }},
                    )
                    preview = await client.post(
                        "/api/plugins/workspace/actions/preview_write",
                        json={"payload": {"path": "sample.py", "content": "print('task-test-ok')\n"}},
                    )
                    write = await client.post(
                        "/api/plugins/workspace/actions/write",
                        json={"payload": {
                            "approved": True,
                            "path": "sample.py",
                            "content": "print('task-test-ok')\n",
                            "expected_sha256": preview.json()["expected_sha256"],
                        }},
                    )
                    write_audit = await client.post(
                        "/api/plugins/tasks/actions/record_workspace_write",
                        json={"payload": {
                            "task_id": task_id,
                            "step_index": 0,
                            "path": "sample.py",
                            "backup_id": write.json()["backup_id"],
                            "approved": True,
                        }},
                    )
                    run = await client.post(
                        "/api/plugins/workspace/actions/run",
                        json={"payload": {"approved": True, "command": ["python", "sample.py"]}},
                    )
                    result = run.json()
                    audit = await client.post(
                        "/api/plugins/tasks/actions/record_test_run",
                        json={"payload": {
                            "task_id": task_id,
                            "step_index": 0,
                            "command": result["command"],
                            "passed": result["passed"],
                            "returncode": result["returncode"],
                            "output": result["stdout"],
                            "approved": True,
                        }},
                    )
                    completed = await client.post(
                        "/api/plugins/tasks/actions/update_step",
                        json={"payload": {
                            "task_id": task_id,
                            "step_index": 0,
                            "status": "completed",
                            "evidence": "Approved sample.py executed and the recorded Python test command passed.",
                            "approved": True,
                        }},
                    )
                    verification = await client.post(
                        "/api/plugins/tasks/actions/verify",
                        json={"payload": {"task_id": task_id}},
                    )
                    history = await client.post(
                        "/api/plugins/tasks/actions/get",
                        json={"payload": {"task_id": task_id}},
                    )
                    return write_audit, audit, completed, verification, history

            write_audit, audit, completed, verification, history = asyncio.run(exercise_api())

        self.assertEqual(write_audit.status_code, 200)
        self.assertEqual(audit.status_code, 200)
        self.assertEqual(completed.status_code, 200)
        test_event = next(event for event in history.json()["task"]["events"] if event["action"] == "test_run")
        self.assertTrue(test_event["detail"]["passed"])
        self.assertIn("task-test-ok", test_event["detail"]["output"])
        self.assertEqual(history.json()["task"]["status"], "completed")
        self.assertEqual(verification.status_code, 200)
        self.assertTrue(verification.json()["verified"])

    def test_verify_action_is_read_only_and_exposed_through_the_api(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            gateway = PluginGateway()
            gateway.register(TasksPlugin(Path(directory) / "tasks.db"))
            app = create_app(gateway)

            async def exercise_api() -> tuple[httpx.Response, httpx.Response]:
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client:
                    created = await client.post(
                        "/api/plugins/tasks/actions/create",
                        json={"payload": {"request": "Test verification", "steps": ["Add tests"]}},
                    )
                    task_id = created.json()["task_id"]
                    verification = await client.post(
                        "/api/plugins/tasks/actions/verify",
                        json={"payload": {"task_id": task_id}},
                    )
                    history = await client.post(
                        "/api/plugins/tasks/actions/get",
                        json={"payload": {"task_id": task_id}},
                    )
                    return verification, history

            verification, history = asyncio.run(exercise_api())

        self.assertEqual(verification.status_code, 200)
        self.assertFalse(verification.json()["verified"])
        self.assertFalse(history.json()["task"]["approved"])
        self.assertEqual(history.json()["task"]["steps"][0]["status"], "pending")

    def test_verify_rejects_completed_coding_task_without_passing_tests(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plugin = TasksPlugin(Path(directory) / "tasks.db")

            async def exercise() -> dict[str, object]:
                created = await plugin.invoke("create", {"request": "Implement parser fix", "steps": ["Implement change"]})
                task_id = created["task_id"]
                await plugin.invoke("approve", {"task_id": task_id, "approved": True})
                await plugin.invoke("update_step", {
                    "task_id": task_id, "step_index": 0, "status": "in_progress", "approved": True,
                })
                await plugin.invoke("update_step", {
                    "task_id": task_id,
                    "step_index": 0,
                    "status": "completed",
                    "evidence": "Implementation was written.",
                    "approved": True,
                })
                return await plugin.invoke("verify", {"task_id": task_id})

            result = asyncio.run(exercise())

        self.assertFalse(result["verified"])
        self.assertIn("No successful test run is recorded.", result["reasons"])

    def test_verify_requires_pass_after_latest_write_and_all_steps_completed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plugin = TasksPlugin(Path(directory) / "tasks.db")

            async def exercise() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
                created = await plugin.invoke("create", {
                    "request": "Implement a tested parser fix", "steps": ["Write change", "Recheck after edits"],
                })
                task_id = created["task_id"]
                await plugin.invoke("approve", {"task_id": task_id, "approved": True})
                await plugin.invoke("update_step", {
                    "task_id": task_id, "step_index": 0, "status": "in_progress", "approved": True,
                })
                await plugin.invoke("record_workspace_write", {
                    "task_id": task_id, "step_index": 0, "path": "parser.py", "backup_id": "a" * 32,
                    "approved": True,
                })
                await plugin.invoke("record_test_run", {
                    "task_id": task_id, "step_index": 0, "command": ["python", "-m", "unittest"],
                    "passed": True, "returncode": 0, "output": "OK", "approved": True,
                })
                await plugin.invoke("update_step", {
                    "task_id": task_id, "step_index": 0, "status": "completed",
                    "evidence": "Initial tests passed.", "approved": True,
                })
                incomplete = await plugin.invoke("verify", {"task_id": task_id})
                await plugin.invoke("update_step", {
                    "task_id": task_id, "step_index": 1, "status": "in_progress", "approved": True,
                })
                await plugin.invoke("record_workspace_write", {
                    "task_id": task_id, "step_index": 1, "path": "parser.py", "backup_id": "b" * 32,
                    "approved": True,
                })
                stale = await plugin.invoke("verify", {"task_id": task_id})
                await plugin.invoke("record_test_run", {
                    "task_id": task_id, "step_index": 1, "command": ["python", "-m", "unittest"],
                    "passed": True, "returncode": 0, "output": "OK after latest edit", "approved": True,
                })
                await plugin.invoke("update_step", {
                    "task_id": task_id, "step_index": 1, "status": "completed",
                    "evidence": "Latest tests passed.", "approved": True,
                })
                verified = await plugin.invoke("verify", {"task_id": task_id})
                return incomplete, stale, verified

            incomplete, stale, verified = asyncio.run(exercise())

        self.assertFalse(incomplete["verified"])
        self.assertIn("One or more task steps are not completed.", incomplete["reasons"])
        self.assertFalse(stale["verified"])
        self.assertIn("A successful test run after the latest workspace write or rollback is required.", stale["reasons"])
        self.assertTrue(verified["verified"])
        self.assertEqual(verified["evidence"]["passing_test_run_count"], 2)

    def test_verify_requires_a_new_test_after_workspace_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plugin = TasksPlugin(Path(directory) / "tasks.db")

            async def exercise() -> dict[str, object]:
                created = await plugin.invoke("create", {"request": "Fix parser", "steps": ["Write and test"]})
                task_id = created["task_id"]
                await plugin.invoke("approve", {"task_id": task_id, "approved": True})
                await plugin.invoke("update_step", {
                    "task_id": task_id, "step_index": 0, "status": "in_progress", "approved": True,
                })
                backup_id = "c" * 32
                await plugin.invoke("record_workspace_write", {
                    "task_id": task_id, "step_index": 0, "path": "parser.py", "backup_id": backup_id,
                    "approved": True,
                })
                await plugin.invoke("record_test_run", {
                    "task_id": task_id, "step_index": 0, "command": ["python", "-m", "unittest"],
                    "passed": True, "returncode": 0, "output": "OK", "approved": True,
                })
                await plugin.invoke("update_step", {
                    "task_id": task_id, "step_index": 0, "status": "completed",
                    "evidence": "Tests passed.", "approved": True,
                })
                await plugin.invoke("record_workspace_rollback", {
                    "task_id": task_id, "backup_id": backup_id, "approved": True,
                })
                return await plugin.invoke("verify", {"task_id": task_id})

            result = asyncio.run(exercise())

        self.assertFalse(result["verified"])
        self.assertIn("A successful test run after the latest workspace write or rollback is required.", result["reasons"])

    def test_workspace_change_is_previewed_approved_audited_and_rollbackable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            root.mkdir()
            target = root / "note.txt"
            target.write_text("before", encoding="utf-8")
            gateway = PluginGateway()
            gateway.register(TasksPlugin(Path(directory) / "tasks.db"))
            gateway.register(WorkspacePlugin(root, Path(directory) / "backups"))
            app = create_app(gateway)

            async def exercise_api() -> tuple[httpx.Response, ...]:
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    created = await client.post(
                        "/api/plugins/tasks/actions/create",
                        json={"payload": {"request": "Update note", "steps": ["Edit note"]}},
                    )
                    task_id = created.json()["task_id"]
                    await client.post(
                        "/api/plugins/tasks/actions/approve",
                        json={"payload": {"task_id": task_id, "approved": True}},
                    )
                    await client.post(
                        "/api/plugins/tasks/actions/update_step",
                        json={"payload": {
                            "task_id": task_id,
                            "step_index": 0,
                            "status": "in_progress",
                            "approved": True,
                        }},
                    )
                    preview = await client.post(
                        "/api/plugins/workspace/actions/preview_write",
                        json={"payload": {"path": "note.txt", "content": "after"}},
                    )
                    self.assertIn("-before", preview.json()["diff"])
                    self.assertEqual(target.read_text(encoding="utf-8"), "before")
                    write = await client.post(
                        "/api/plugins/workspace/actions/write",
                        json={"payload": {
                            "approved": True,
                            "path": "note.txt",
                            "content": "after",
                            "expected_sha256": preview.json()["expected_sha256"],
                        }},
                    )
                    audit = await client.post(
                        "/api/plugins/tasks/actions/record_workspace_write",
                        json={"payload": {
                            "task_id": task_id,
                            "step_index": 0,
                            "path": "note.txt",
                            "backup_id": write.json()["backup_id"],
                            "approved": True,
                        }},
                    )
                    duplicate_audit = await client.post(
                        "/api/plugins/tasks/actions/record_workspace_write",
                        json={"payload": {
                            "task_id": task_id,
                            "step_index": 0,
                            "path": "note.txt",
                            "backup_id": write.json()["backup_id"],
                            "approved": True,
                        }},
                    )
                    unapproved_rollback_record = await client.post(
                        "/api/plugins/tasks/actions/record_workspace_rollback",
                        json={"payload": {
                            "task_id": task_id,
                            "backup_id": write.json()["backup_id"],
                        }},
                    )
                    rolled_back = await client.post(
                        "/api/plugins/workspace/actions/rollback",
                        json={"payload": {"approved": True, "backup_id": write.json()["backup_id"]}},
                    )
                    rollback_audit = await client.post(
                        "/api/plugins/tasks/actions/record_workspace_rollback",
                        json={"payload": {
                            "task_id": task_id,
                            "backup_id": write.json()["backup_id"],
                            "approved": True,
                        }},
                    )
                    duplicate_rollback_audit = await client.post(
                        "/api/plugins/tasks/actions/record_workspace_rollback",
                        json={"payload": {
                            "task_id": task_id,
                            "backup_id": write.json()["backup_id"],
                            "approved": True,
                        }},
                    )
                    history = await client.post(
                        "/api/plugins/tasks/actions/get",
                        json={"payload": {"task_id": task_id}},
                    )
                    return audit, duplicate_audit, unapproved_rollback_record, rolled_back, rollback_audit, duplicate_rollback_audit, history

            audit, duplicate_audit, unapproved_rollback_record, rolled_back, rollback_audit, duplicate_rollback_audit, history = asyncio.run(exercise_api())
            self.assertEqual(target.read_text(encoding="utf-8"), "before")

        self.assertEqual(audit.status_code, 200)
        self.assertEqual(duplicate_audit.status_code, 422)
        self.assertEqual(unapproved_rollback_record.status_code, 403)
        self.assertEqual(rolled_back.status_code, 200)
        self.assertEqual(rollback_audit.status_code, 200)
        self.assertEqual(duplicate_rollback_audit.status_code, 422)
        events = history.json()["task"]["events"]
        self.assertIn("workspace_write", [event["action"] for event in events])
        self.assertIn("workspace_rollback", [event["action"] for event in events])


if __name__ == "__main__":
    unittest.main()