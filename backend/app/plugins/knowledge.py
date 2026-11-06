from __future__ import annotations

import hashlib
import os
import re
import uuid
from typing import Any, Callable

from qdrant_client import AsyncQdrantClient, models

from app.plugins.contracts import PluginManifest
from app.plugins.gateway import PluginGateway


class KnowledgeApprovalRequired(Exception):
    pass


class KnowledgeProviderError(Exception):
    pass


class KnowledgePlugin:
    manifest = PluginManifest(
        plugin_id="knowledge",
        display_name="Local Vector Knowledge",
        description="Onaylı belge snapshot'larını yerel Ollama embeddingleriyle Qdrant'ta arar.",
        actions=("index", "search", "delete"),
    )
    collection_name = "repo_knowledge_nomic_768"
    embedding_dimensions = 768
    embedding_model = "nomic-embed-text:latest"
    max_document_chars = 50_000
    chunk_chars = 1_000
    chunk_overlap = 120
    max_chunks = 64

    def __init__(
        self,
        gateway: PluginGateway,
        qdrant_url: str | None = None,
        client_factory: Callable[..., Any] = AsyncQdrantClient,
    ) -> None:
        self.gateway = gateway
        self.qdrant_url = (qdrant_url or os.getenv("QDRANT_URL", "http://qdrant:6333")).rstrip("/")
        self.client_factory = client_factory

    async def invoke(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            if action == "index":
                return await self._index(payload)
            if action == "search":
                return await self._search(payload)
            if action == "delete":
                return await self._delete(payload)
            raise ValueError(f"Unsupported knowledge action: {action}")
        except (KnowledgeApprovalRequired, TypeError, ValueError):
            raise
        except Exception as exc:
            raise KnowledgeProviderError("Local embedding or Qdrant operation failed.") from exc

    async def _index(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_approval(payload, "Indexing a document")
        document_id = self._document_id(payload.get("document_id"))
        preview = await self.gateway.invoke("documents", "preview", {"document_id": document_id})
        content = preview.get("content") if isinstance(preview, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise ValueError("The indexed document has no readable text.")
        if len(content) > self.max_document_chars:
            raise ValueError(f"Documents must be at most {self.max_document_chars} characters to index.")
        filename = preview.get("filename")
        if not isinstance(filename, str) or not filename:
            raise ValueError("The indexed document is missing its filename.")
        extension = preview.get("extension")
        if not isinstance(extension, str) or extension.casefold() not in {
            ".md", ".txt", ".json", ".toml", ".yaml", ".yml", ".ts", ".tsx", ".js", ".mjs",
            ".c", ".h", ".cpp", ".hpp", ".rs", ".py",
        }:
            raise ValueError("Only indexed UTF-8 text and source-code documents can be vectorized.")
        source_match = re.search(r"^Source:\s+(https://\S+)", content, re.MULTILINE)
        source_url = source_match.group(1) if source_match else f"/api/plugins/documents/assets/{document_id}"
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        chunks = self._chunks(content)
        embedding_result = await self.gateway.invoke(
            "ollama",
            "embed",
            {"model": self.embedding_model, "input": [chunk[2] for chunk in chunks]},
        )
        vectors = embedding_result.get("embeddings") if isinstance(embedding_result, dict) else None
        dimensions = embedding_result.get("dimensions") if isinstance(embedding_result, dict) else None
        if dimensions != self.embedding_dimensions or not isinstance(vectors, list) or len(vectors) != len(chunks):
            raise ValueError(
                f"Embedding model must return {self.embedding_dimensions}-dimension vectors for every chunk."
            )

        client = self.client_factory(url=self.qdrant_url)
        try:
            await self._ensure_collection(client)
            selector = models.FilterSelector(
                filter=models.Filter(
                    must=[models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id))]
                )
            )
            await client.delete(collection_name=self.collection_name, points_selector=selector, wait=True)
            points = []
            for index, ((start, end, text), vector) in enumerate(zip(chunks, vectors, strict=True)):
                point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{document_id}:{digest}:{index}"))
                points.append(models.PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "document_id": document_id,
                        "filename": filename,
                        "source_url": source_url,
                        "sha256": digest,
                        "chunk_index": index,
                        "start_char": start,
                        "end_char": end,
                        "text": text,
                        "embedding_model": self.embedding_model,
                    },
                ))
            await client.upsert(collection_name=self.collection_name, points=points, wait=True)
        finally:
            await client.close()
        return {
            "status": "indexed",
            "document_id": document_id,
            "filename": filename,
            "source_url": source_url,
            "sha256": digest,
            "embedding_model": self.embedding_model,
            "dimensions": self.embedding_dimensions,
            "chunks": len(chunks),
        }

    async def _search(self, payload: dict[str, Any]) -> dict[str, Any]:
        query = payload.get("query")
        if not isinstance(query, str) or not query.strip() or len(query) > 1_000:
            raise ValueError("query must be a non-empty string up to 1000 characters.")
        limit = payload.get("limit", 5)
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("limit must be an integer.")
        limit = max(1, min(limit, 10))
        embedding_result = await self.gateway.invoke(
            "ollama", "embed", {"model": self.embedding_model, "input": [query.strip()]}
        )
        vectors = embedding_result.get("embeddings") if isinstance(embedding_result, dict) else None
        if (
            not isinstance(vectors, list)
            or len(vectors) != 1
            or embedding_result.get("dimensions") != self.embedding_dimensions
        ):
            raise ValueError("The local embedding model returned an invalid query vector.")
        client = self.client_factory(url=self.qdrant_url)
        try:
            await self._ensure_collection(client)
            result = await client.query_points(
                collection_name=self.collection_name,
                query=vectors[0],
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
            matches = [
                {
                    "score": point.score,
                    "document_id": point.payload.get("document_id"),
                    "filename": point.payload.get("filename"),
                    "source_url": point.payload.get("source_url"),
                    "sha256": point.payload.get("sha256"),
                    "chunk_index": point.payload.get("chunk_index"),
                    "start_char": point.payload.get("start_char"),
                    "end_char": point.payload.get("end_char"),
                    "text": point.payload.get("text"),
                }
                for point in result.points
                if isinstance(point.payload, dict)
            ]
        finally:
            await client.close()
        return {"query": query.strip(), "embedding_model": self.embedding_model, "count": len(matches), "results": matches}

    async def _delete(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_approval(payload, "Deleting a document from vector memory")
        document_id = self._document_id(payload.get("document_id"))
        client = self.client_factory(url=self.qdrant_url)
        try:
            await self._ensure_collection(client)
            selector = models.FilterSelector(
                filter=models.Filter(
                    must=[models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id))]
                )
            )
            result = await client.delete(collection_name=self.collection_name, points_selector=selector, wait=True)
        finally:
            await client.close()
        return {"document_id": document_id, "deleted": True, "operation": str(result.operation_id)}

    async def _ensure_collection(self, client: Any) -> None:
        collections = await client.get_collections()
        names = {collection.name for collection in collections.collections}
        if self.collection_name not in names:
            await client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=self.embedding_dimensions,
                    distance=models.Distance.COSINE,
                ),
            )

    @classmethod
    def _chunks(cls, content: str) -> list[tuple[int, int, str]]:
        chunks = []
        start = 0
        while start < len(content) and len(chunks) < cls.max_chunks:
            end = min(start + cls.chunk_chars, len(content))
            chunks.append((start, end, content[start:end]))
            if end == len(content):
                break
            start = end - cls.chunk_overlap
        return chunks

    @staticmethod
    def _document_id(value: Any) -> str:
        if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{32}", value):
            raise ValueError("document_id must be a valid indexed document identifier.")
        return value

    @staticmethod
    def _require_approval(payload: dict[str, Any], action: str) -> None:
        if payload.get("approved") is not True:
            raise KnowledgeApprovalRequired(f"{action} requires approved=true.")