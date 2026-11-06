from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from typing import Any

import httpx

from app.main import create_app
from app.plugins.gateway import PluginGateway
from app.plugins.knowledge import KnowledgeApprovalRequired, KnowledgePlugin


class KnowledgePluginTests(unittest.TestCase):
    document_id = "b" * 32

    class FakeGateway:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, dict[str, Any]]] = []

        async def invoke(self, plugin_id: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
            self.calls.append((plugin_id, action, payload))
            if (plugin_id, action) == ("documents", "preview"):
                text = (
                    "Source: https://github.com/morluto/rea/blob/abc/src/main.ts\n"
                    "Repository: morluto/rea\nPath: src/main.ts\nGitHub blob: abc\n\n"
                    + ("export const startup = true;\n" * 80)
                )
                return {
                    "document_id": KnowledgePluginTests.document_id,
                    "filename": "morluto-rea-main.ts",
                    "extension": ".ts",
                    "content": text,
                }
            if (plugin_id, action) == ("ollama", "embed"):
                texts = payload["input"]
                return {
                    "model": payload["model"],
                    "dimensions": 768,
                    "embeddings": [[0.25] * 768 for _ in texts],
                }
            raise AssertionError(f"Unexpected gateway action: {plugin_id}/{action}")

    class FakeQdrant:
        def __init__(self) -> None:
            self.collections: set[str] = set()
            self.points: dict[str, Any] = {}
            self.deleted = False
            self.closed = False

        async def get_collections(self) -> Any:
            return SimpleNamespace(collections=[SimpleNamespace(name=name) for name in self.collections])

        async def create_collection(self, collection_name: str, vectors_config: Any) -> bool:
            self.collections.add(collection_name)
            return True

        async def delete(self, collection_name: str, points_selector: Any, wait: bool = True) -> Any:
            self.deleted = True
            document_id = points_selector.filter.must[0].match.value
            self.points = {
                point_id: point for point_id, point in self.points.items()
                if point.payload.get("document_id") != document_id
            }
            return SimpleNamespace(operation_id=1)

        async def upsert(self, collection_name: str, points: list[Any], wait: bool = True) -> Any:
            self.points.update({str(point.id): point for point in points})
            return SimpleNamespace(operation_id=2)

        async def query_points(self, collection_name: str, query: list[float], limit: int, **_: Any) -> Any:
            results = [
                SimpleNamespace(id=point.id, score=0.91, payload=point.payload)
                for point in list(self.points.values())[:limit]
            ]
            return SimpleNamespace(points=results)

        async def close(self) -> None:
            self.closed = True

    def test_index_requires_explicit_approval(self) -> None:
        gateway = self.FakeGateway()
        plugin = KnowledgePlugin(gateway, client_factory=lambda **_: self.FakeQdrant())  # type: ignore[arg-type]

        async def exercise() -> None:
            with self.assertRaises(KnowledgeApprovalRequired):
                await plugin.invoke("index", {"document_id": self.document_id})

        asyncio.run(exercise())
        self.assertEqual(gateway.calls, [])

    def test_api_maps_unapproved_index_and_delete_to_forbidden(self) -> None:
        gateway = PluginGateway()
        gateway.register(KnowledgePlugin(gateway, client_factory=lambda **_: self.FakeQdrant()))  # type: ignore[arg-type]
        app = create_app(gateway)

        async def exercise() -> tuple[int, int]:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                indexed = await client.post(
                    "/api/plugins/knowledge/actions/index",
                    json={"payload": {"document_id": self.document_id}},
                )
                deleted = await client.post(
                    "/api/plugins/knowledge/actions/delete",
                    json={"payload": {"document_id": self.document_id}},
                )
                return indexed.status_code, deleted.status_code

        self.assertEqual(asyncio.run(exercise()), (403, 403))

    def test_index_is_idempotent_and_search_returns_source_chunk_metadata(self) -> None:
        gateway = self.FakeGateway()
        client = self.FakeQdrant()
        plugin = KnowledgePlugin(gateway, client_factory=lambda **_: client)  # type: ignore[arg-type]

        async def exercise() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
            first = await plugin.invoke("index", {"document_id": self.document_id, "approved": True})
            second = await plugin.invoke("index", {"document_id": self.document_id, "approved": True})
            searched = await plugin.invoke("search", {"query": "startup entrypoint", "limit": 4})
            return first, second, searched

        first, second, searched = asyncio.run(exercise())

        self.assertGreater(first["chunks"], 1)
        self.assertEqual(second["chunks"], first["chunks"])
        self.assertEqual(len(client.points), first["chunks"])
        self.assertEqual(searched["count"], min(4, first["chunks"]))
        self.assertEqual(searched["results"][0]["document_id"], self.document_id)
        self.assertTrue(searched["results"][0]["source_url"].startswith("https://github.com/morluto/rea/blob/"))
        self.assertIn("export const startup", searched["results"][0]["text"])
        self.assertTrue(all(call[0] == "ollama" and call[1] == "embed" for call in gateway.calls if call[0] == "ollama"))

    def test_delete_requires_approval_and_removes_only_selected_document(self) -> None:
        client = self.FakeQdrant()
        client.collections.add(KnowledgePlugin.collection_name)
        client.points["one"] = SimpleNamespace(payload={"document_id": self.document_id})
        client.points["two"] = SimpleNamespace(payload={"document_id": "c" * 32})
        plugin = KnowledgePlugin(self.FakeGateway(), client_factory=lambda **_: client)  # type: ignore[arg-type]

        async def exercise() -> None:
            with self.assertRaises(KnowledgeApprovalRequired):
                await plugin.invoke("delete", {"document_id": self.document_id})
            await plugin.invoke("delete", {"document_id": self.document_id, "approved": True})

        asyncio.run(exercise())
        self.assertTrue(client.deleted)
        self.assertEqual(set(client.points), {"two"})


if __name__ == "__main__":
    unittest.main()