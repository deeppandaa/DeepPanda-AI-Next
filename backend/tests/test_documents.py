import asyncio
import base64
import sqlite3
import tempfile
import unittest
from pathlib import Path

import httpx

from app.main import create_app
from app.plugins.gateway import PluginGateway
from app.plugins.documents import DocumentUploadApprovalRequired, DocumentsPlugin


class DocumentsPluginTests(unittest.TestCase):
    def test_preview_reconstructs_indexed_text_with_a_bounded_response(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data_root = Path(directory) / "data"
            plugin = DocumentsPlugin(data_root)
            raw = ("Document preview text.\n" * 3_000).encode("utf-8")

            async def exercise_plugin() -> tuple[dict[str, object], dict[str, object], Path]:
                ingested = await plugin.invoke("ingest", {
                    "approved": True,
                    "filename": "preview.txt",
                    "content_base64": base64.b64encode(raw).decode("ascii"),
                })
                preview = await plugin.invoke("preview", {"document_id": ingested["document_id"]})
                listed = await plugin.invoke("list", {})
                return preview, listed, data_root / "documents" / f"{ingested['document_id']}.txt"

            preview, listed, stored_path = asyncio.run(exercise_plugin())
            self.assertTrue(stored_path.is_file())

        self.assertEqual(preview["filename"], "preview.txt")
        self.assertEqual(len(preview["content"]), 50_000)
        self.assertEqual(preview["content"], raw.decode("utf-8")[:50_000])
        self.assertTrue(preview["truncated"])
        self.assertEqual(len(listed["documents"]), 1)

    def test_document_delete_requires_approval_and_removes_file_and_index(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data_root = Path(directory) / "data"
            gateway = PluginGateway()
            gateway.register(DocumentsPlugin(data_root))
            app = create_app(gateway)
            raw = b"Private indexed document content"

            async def exercise_api() -> tuple[httpx.Response, httpx.Response, httpx.Response, httpx.Response, httpx.Response, Path]:
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    ingest = await client.post(
                        "/api/plugins/documents/actions/ingest",
                        json={"payload": {
                            "approved": True,
                            "filename": "private.txt",
                            "content_base64": base64.b64encode(raw).decode("ascii"),
                        }},
                    )
                    document_id = ingest.json()["document_id"]
                    stored_path = data_root / "documents" / f"{document_id}.txt"
                    denied = await client.post(
                        "/api/plugins/documents/actions/delete",
                        json={"payload": {"document_id": document_id}},
                    )
                    self.assertTrue(stored_path.is_file())
                    still_searchable = await client.post(
                        "/api/plugins/documents/actions/search",
                        json={"payload": {"query": "indexed document"}},
                    )
                    deleted = await client.post(
                        "/api/plugins/documents/actions/delete",
                        json={"payload": {"document_id": document_id, "approved": True}},
                    )
                    listed = await client.post(
                        "/api/plugins/documents/actions/list",
                        json={"payload": {"limit": 100}},
                    )
                    search_after = await client.post(
                        "/api/plugins/documents/actions/search",
                        json={"payload": {"query": "indexed document"}},
                    )
                    return denied, still_searchable, deleted, listed, search_after, stored_path

            denied, still_searchable, deleted, listed, search_after, stored_path = asyncio.run(exercise_api())
            self.assertFalse(stored_path.exists())

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(still_searchable.json()["count"], 1)
        self.assertEqual(deleted.status_code, 200)
        self.assertTrue(deleted.json()["deleted"])
        self.assertEqual(listed.json()["documents"], [])
        self.assertEqual(search_after.json()["count"], 0)

    def test_document_file_is_restored_if_index_delete_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data_root = Path(directory) / "data"
            plugin = DocumentsPlugin(data_root)
            raw = b"Keep file if database deletion fails"
            ingested = asyncio.run(plugin.invoke("ingest", {
                "approved": True,
                "filename": "keep.txt",
                "content_base64": base64.b64encode(raw).decode("ascii"),
            }))
            stored_path = data_root / "documents" / f"{ingested['document_id']}.txt"
            with plugin._connection() as connection:
                connection.execute(
                    "CREATE TRIGGER reject_document_delete BEFORE DELETE ON documents "
                    "BEGIN SELECT RAISE(ABORT, 'delete rejected'); END"
                )

            with self.assertRaisesRegex(sqlite3.IntegrityError, "delete rejected"):
                asyncio.run(plugin.invoke("delete", {"document_id": ingested["document_id"], "approved": True}))

            self.assertEqual(stored_path.read_bytes(), raw)
            self.assertEqual(asyncio.run(plugin.invoke("list", {}))["documents"][0]["document_id"], ingested["document_id"])

    def test_asset_route_serves_only_an_ingested_document(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data_root = Path(directory) / "data"
            plugin = DocumentsPlugin(data_root)
            gateway = PluginGateway()
            gateway.register(plugin)
            app = create_app(gateway)
            raw = b"Private local document text"

            async def exercise_api() -> tuple[httpx.Response, httpx.Response]:
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    ingest = await client.post(
                        "/api/plugins/documents/actions/ingest",
                        json={"payload": {
                            "approved": True,
                            "filename": "source.txt",
                            "content_base64": base64.b64encode(raw).decode("ascii"),
                        }},
                    )
                    document_id = ingest.json()["document_id"]
                    download = await client.get(f"/api/plugins/documents/assets/{document_id}")
                    return ingest, download

            ingest, download = asyncio.run(exercise_api())

        self.assertEqual(ingest.status_code, 200)
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.content, raw)

    def test_ingest_requires_approval_and_does_not_create_storage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data_root = Path(directory) / "data"
            plugin = DocumentsPlugin(data_root)
            payload = {
                "filename": "notes.txt",
                "content_base64": base64.b64encode(b"Local-first agent notes").decode("ascii"),
            }

            with self.assertRaises(DocumentUploadApprovalRequired):
                asyncio.run(plugin.invoke("ingest", payload))

            self.assertFalse(data_root.exists())

    def test_approved_text_ingest_is_searchable_with_source_offsets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data_root = Path(directory) / "data"
            plugin = DocumentsPlugin(data_root)
            payload = {
                "approved": True,
                "filename": "architecture.md",
                "content_base64": base64.b64encode(b"Use a central gateway for every plugin.").decode("ascii"),
            }

            ingested = asyncio.run(plugin.invoke("ingest", payload))
            result = asyncio.run(plugin.invoke("search", {"query": "central gateway"}))

        self.assertEqual(ingested["status"], "indexed")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["results"][0]["filename"], "architecture.md")
        self.assertEqual(result["results"][0]["start_char"], 0)
        self.assertIn("/api/plugins/documents/assets/", result["results"][0]["source_url"])

    def test_upload_rejects_unsupported_and_oversized_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plugin = DocumentsPlugin(Path(directory) / "data", max_upload_bytes=10)
            with self.assertRaises(ValueError):
                asyncio.run(plugin.invoke("ingest", {
                    "approved": True,
                    "filename": "image.exe",
                    "content_base64": base64.b64encode(b"x").decode("ascii"),
                }))
            with self.assertRaises(ValueError):
                asyncio.run(plugin.invoke("ingest", {
                    "approved": True,
                    "filename": "large.txt",
                    "content_base64": base64.b64encode(b"x" * 11).decode("ascii"),
                }))


if __name__ == "__main__":
    unittest.main()