import asyncio
import sys
import tempfile
import unittest
from pathlib import Path

import httpx

from app.main import create_app
from app.plugins.gateway import PluginGateway
from app.plugins.workspace import WorkspaceCommandApprovalRequired, WorkspacePlugin, WorkspaceWriteApprovalRequired


class WorkspacePluginTests(unittest.TestCase):
    def test_api_routes_workspace_actions_and_enforces_approval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            root.mkdir()
            (root / "note.txt").write_text("before", encoding="utf-8")
            gateway = PluginGateway()
            gateway.register(WorkspacePlugin(root, Path(directory) / "backups"))
            app = create_app(gateway)

            async def exercise_api() -> tuple[httpx.Response, httpx.Response, httpx.Response]:
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    preview = await client.post(
                        "/api/plugins/workspace/actions/preview_write",
                        json={"payload": {"path": "note.txt", "content": "after"}},
                    )
                    denied = await client.post(
                        "/api/plugins/workspace/actions/write",
                        json={"payload": {"path": "note.txt", "content": "after"}},
                    )
                    written = await client.post(
                        "/api/plugins/workspace/actions/write",
                        json={"payload": {"approved": True, "path": "note.txt", "content": "after"}},
                    )
                    return preview, denied, written

            preview_response, denied_response, written_response = asyncio.run(exercise_api())
            self.assertEqual((root / "note.txt").read_text(encoding="utf-8"), "after")

        self.assertEqual(preview_response.status_code, 200)
        self.assertEqual(denied_response.status_code, 403)
        self.assertEqual(written_response.status_code, 200)

    def test_reads_workspace_files_and_rejects_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            root.mkdir()
            (root / "note.txt").write_text("local content", encoding="utf-8")
            plugin = WorkspacePlugin(root, Path(directory) / "backups")

            result = asyncio.run(plugin.invoke("read", {"path": "note.txt"}))
            with self.assertRaises(ValueError):
                asyncio.run(plugin.invoke("read", {"path": "../outside.txt"}))

        self.assertEqual(result["content"], "local content")

    def test_preview_does_not_write_and_write_requires_approval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            root.mkdir()
            target = root / "note.txt"
            target.write_text("before", encoding="utf-8")
            plugin = WorkspacePlugin(root, Path(directory) / "backups")

            preview = asyncio.run(plugin.invoke("preview_write", {"path": "note.txt", "content": "after"}))
            with self.assertRaises(WorkspaceWriteApprovalRequired):
                asyncio.run(plugin.invoke("write", {"path": "note.txt", "content": "after"}))
            self.assertIn("-before", preview["diff"])
            self.assertEqual(target.read_text(encoding="utf-8"), "before")

    def test_write_rejects_content_changed_since_preview(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            root.mkdir()
            target = root / "note.txt"
            target.write_text("before", encoding="utf-8")
            plugin = WorkspacePlugin(root, Path(directory) / "backups")
            preview = asyncio.run(plugin.invoke("preview_write", {"path": "note.txt", "content": "approved"}))
            target.write_text("external edit", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "changed after preview"):
                asyncio.run(plugin.invoke("write", {
                    "approved": True,
                    "path": "note.txt",
                    "content": "approved",
                    "expected_sha256": preview["expected_sha256"],
                }))

            self.assertEqual(target.read_text(encoding="utf-8"), "external edit")

    def test_rollback_refuses_to_overwrite_a_later_workspace_edit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            root.mkdir()
            target = root / "note.txt"
            target.write_text("original", encoding="utf-8")
            plugin = WorkspacePlugin(root, Path(directory) / "backups")
            preview = asyncio.run(plugin.invoke("preview_write", {"path": "note.txt", "content": "agent edit"}))
            write = asyncio.run(plugin.invoke("write", {
                "approved": True,
                "path": "note.txt",
                "content": "agent edit",
                "expected_sha256": preview["expected_sha256"],
            }))
            target.write_text("later user edit", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "changed since this backup"):
                asyncio.run(plugin.invoke("rollback", {"approved": True, "backup_id": write["backup_id"]}))

            self.assertEqual(target.read_text(encoding="utf-8"), "later user edit")

    def test_approved_write_can_be_rolled_back(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            root.mkdir()
            target = root / "note.txt"
            target.write_text("original", encoding="utf-8")
            plugin = WorkspacePlugin(root, Path(directory) / "backups")

            result = asyncio.run(plugin.invoke("write", {
                "approved": True,
                "path": "note.txt",
                "content": "updated",
            }))
            rolled_back = asyncio.run(plugin.invoke("rollback", {
                "approved": True,
                "backup_id": result["backup_id"],
            }))
            self.assertEqual(target.read_text(encoding="utf-8"), "original")
            self.assertTrue(rolled_back["restored"])

    def test_rollback_removes_a_file_created_by_the_approved_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            root.mkdir()
            target = root / "new.txt"
            plugin = WorkspacePlugin(root, Path(directory) / "backups")

            result = asyncio.run(plugin.invoke("write", {
                "approved": True,
                "path": "new.txt",
                "content": "created",
            }))
            rolled_back = asyncio.run(plugin.invoke("rollback", {
                "approved": True,
                "backup_id": result["backup_id"],
            }))

            self.assertFalse(target.exists())
            self.assertTrue(rolled_back["removed_created_file"])

    def test_commands_require_approval_and_run_without_shell(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            root.mkdir()
            plugin = WorkspacePlugin(root, Path(directory) / "backups")

            with self.assertRaises(WorkspaceCommandApprovalRequired):
                asyncio.run(plugin.invoke("run", {"command": ["python", "--version"]}))
            with self.assertRaises(ValueError):
                asyncio.run(plugin.invoke("run", {
                    "approved": True,
                    "command": [sys.executable, "--version"],
                }))

            result = asyncio.run(plugin.invoke("run", {
                "approved": True,
                "command": ["python", "-c", "print('workspace-ok')"],
            }))

        self.assertTrue(result["passed"])
        self.assertIn("workspace-ok", result["stdout"])


if __name__ == "__main__":
    unittest.main()