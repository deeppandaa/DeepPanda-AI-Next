import asyncio
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import httpx
from app.main import create_app
from app.plugins.gateway import PluginGateway
from app.plugins.memory import MemoryPlugin, MemoryWriteApprovalRequired


class MemoryPluginTests(unittest.TestCase):
    def test_existing_database_without_source_column_migrates_in_place(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "memory.db"
            connection = sqlite3.connect(database)
            connection.execute(
                "CREATE TABLE memories (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, "
                "project TEXT NOT NULL, category TEXT NOT NULL, title TEXT NOT NULL, content TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO memories(created_at,project,category,title,content) VALUES(?,?,?,?,?)",
                ("2026-01-01T00:00:00+00:00", "Legacy", "general", "Old note", "Keep this record."),
            )
            connection.commit()
            connection.close()

            result = asyncio.run(MemoryPlugin(database).invoke("search", {"query": "Old note", "source": "manual"}))

        self.assertEqual(len(result["memories"]), 1)
        self.assertEqual(result["memories"][0]["source"], "manual")

    def test_source_filters_and_taxonomy_are_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plugin = MemoryPlugin(Path(directory) / "memory.db")
            first = asyncio.run(plugin.invoke("remember", {
                "approved": True,
                "title": "Research finding",
                "content": "DuckDuckGo candidates need source citations.",
                "project": "AI-Next",
                "category": "research",
                "source": "research:job-1",
            }))
            asyncio.run(plugin.invoke("remember", {
                "approved": True,
                "title": "Other note",
                "content": "Unrelated project note.",
                "project": "Legacy",
                "category": "general",
                "source": "manual",
            }))
            filtered = asyncio.run(plugin.invoke("search", {
                "query": "citations",
                "project": "AI-Next",
                "category": "research",
                "source": "research:job-1",
            }))
            taxonomy = asyncio.run(plugin.invoke("taxonomy", {}))

        self.assertEqual(filtered["memories"][0]["id"], first["id"])
        self.assertEqual(filtered["memories"][0]["source"], "research:job-1")
        self.assertIn("research", taxonomy["categories"])
        self.assertIn("AI-Next", taxonomy["projects"])
        self.assertIn("research:job-1", taxonomy["sources"])

    def test_export_import_requires_approval_and_deduplicates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plugin = MemoryPlugin(Path(directory) / "memory.db")
            source_note = {
                "title": "Portable note",
                "content": "Keep the source attribution.",
                "project": "AI-Next",
                "category": "research",
                "source": "research:job-2",
            }
            asyncio.run(plugin.invoke("remember", {"approved": True, **source_note}))
            with self.assertRaises(MemoryWriteApprovalRequired):
                asyncio.run(plugin.invoke("export", {}))
            exported = asyncio.run(plugin.invoke("export", {"approved": True}))
            with self.assertRaises(MemoryWriteApprovalRequired):
                asyncio.run(plugin.invoke("import", exported))
            imported = asyncio.run(plugin.invoke("import", {"approved": True, **exported}))
            again = asyncio.run(plugin.invoke("import", {"approved": True, **exported}))
            timeline = asyncio.run(plugin.invoke("timeline", {}))

        self.assertEqual(exported["format"], "deep-panda-memory-v1")
        self.assertEqual(imported["imported"], 0)
        self.assertEqual(again["duplicates"], 1)
        self.assertEqual(len(timeline["memories"]), 1)
        self.assertEqual(timeline["memories"][0]["source"], "research:job-2")

    def test_source_delete_requires_approval_and_creates_backup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plugin = MemoryPlugin(Path(directory) / "memory.db")
            saved = asyncio.run(plugin.invoke("remember", {
                "approved": True,
                "title": "Source note",
                "content": "A source-bound memory.",
                "project": "AI-Next",
                "category": "research",
                "source": "research:job-3",
            }))
            preview = asyncio.run(plugin.invoke("preview_source", {"source": "research:job-3"}))
            with self.assertRaises(MemoryWriteApprovalRequired):
                asyncio.run(plugin.invoke("delete_source", {"source": "research:job-3"}))
            deleted = asyncio.run(plugin.invoke("delete_source", {
                "source": "research:job-3",
                "approved": True,
            }))
            remaining = asyncio.run(plugin.invoke("timeline", {}))

            backup = Path(deleted["backup_path"])
            backup_payload = json.loads(backup.read_text(encoding="utf-8"))
            self.assertTrue(backup.is_file())
            restored_plugin = MemoryPlugin(Path(directory) / "restored-memory.db")
            restored = asyncio.run(restored_plugin.invoke("import", {"approved": True, **backup_payload}))
            restored_timeline = asyncio.run(restored_plugin.invoke("timeline", {}))

        self.assertEqual(preview["count"], 1)
        self.assertEqual(deleted["deleted"], 1)
        self.assertEqual(backup_payload["memories"][0]["id"], saved["id"])
        self.assertEqual(remaining["memories"], [])
        self.assertEqual(restored["imported"], 1)
        self.assertEqual(restored_timeline["memories"][0]["source"], "research:job-3")

    def test_api_enforces_memory_approval_and_validates_search_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "memory.db"
            gateway = PluginGateway()
            gateway.register(MemoryPlugin(database))
            app = create_app(gateway)

            async def send_requests() -> tuple[httpx.Response, httpx.Response, httpx.Response]:
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    denied = await client.post(
                        "/api/plugins/memory/actions/remember",
                        json={"payload": {"title": "No consent", "content": "Do not save."}},
                    )
                    invalid = await client.post(
                        "/api/plugins/memory/actions/search",
                        json={"payload": {"query": "note", "limit": "many"}},
                    )
                    approved = await client.post(
                        "/api/plugins/memory/actions/remember",
                        json={"payload": {"approved": True, "title": "Approved", "content": "Save locally."}},
                    )
                    return denied, invalid, approved

            denied_response, invalid_response, approved_response = asyncio.run(send_requests())

        self.assertEqual(denied_response.status_code, 403)
        self.assertEqual(invalid_response.status_code, 422)
        self.assertEqual(approved_response.status_code, 200)

    def test_memory_write_requires_explicit_approval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "memory.db"
            plugin = MemoryPlugin(database)

            with self.assertRaises(MemoryWriteApprovalRequired):
                asyncio.run(plugin.invoke("remember", {"title": "Decision", "content": "Keep data local."}))

            self.assertFalse(database.exists())

    def test_approved_memory_can_be_searched_and_listed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "memory.db"
            plugin = MemoryPlugin(database)
            saved = asyncio.run(plugin.invoke("remember", {
                "approved": True,
                "title": "Offline runtime",
                "content": "Keep model files in a local persistent volume.",
                "project": "AI-Next",
                "category": "architecture",
            }))

            search = asyncio.run(plugin.invoke("search", {"query": "persistent volume"}))
            timeline = asyncio.run(plugin.invoke("timeline", {"project": "AI-Next"}))
            filtered = asyncio.run(plugin.invoke("timeline", {"project": "other"}))
            reopened = MemoryPlugin(database)
            persistent = asyncio.run(reopened.invoke("search", {"query": "offline runtime"}))

        self.assertEqual(saved["status"], "saved")
        self.assertEqual(search["memories"][0]["project"], "AI-Next")
        self.assertEqual(timeline["memories"][0]["title"], "Offline runtime")
        self.assertEqual(filtered["memories"], [])
        self.assertEqual(persistent["memories"][0]["id"], saved["id"])


if __name__ == "__main__":
    unittest.main()