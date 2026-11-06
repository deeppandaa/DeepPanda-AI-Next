from __future__ import annotations

import base64
import hashlib
import io
import mimetypes
import os
import re
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

from app.plugins.contracts import PluginManifest


class DocumentUploadApprovalRequired(Exception):
    pass


class DocumentDeleteApprovalRequired(Exception):
    pass


class DocumentNotFoundError(Exception):
    pass


class DocumentsPlugin:
    manifest = PluginManifest(
        plugin_id="documents",
        display_name="Local Documents",
        description="Onaylı belge yükleme, yerel metin çıkarma ve kaynaklı chunk araması.",
        actions=("ingest", "search", "list", "asset", "preview", "delete"),
    )

    supported_extensions: ClassVar[frozenset[str]] = frozenset(
        {".pdf", ".docx", ".pptx", ".xlsx", ".xlsm", ".txt", ".md", ".py", ".json", ".ts", ".tsx"}
    )
    max_preview_chars: ClassVar[int] = 50_000

    def __init__(
        self,
        data_dir: str | Path | None = None,
        max_upload_bytes: int = 20_000_000,
        max_extracted_chars: int = 2_000_000,
        chunk_chars: int = 4_000,
        chunk_overlap: int = 400,
    ) -> None:
        self.data_dir = Path(data_dir or os.getenv("AI_DATA_DIR", "/data")).expanduser().resolve()
        self.documents_dir = self.data_dir / "documents"
        self.database_path = self.data_dir / "documents.db"
        self.max_upload_bytes = max_upload_bytes
        self.max_extracted_chars = max_extracted_chars
        self.chunk_chars = chunk_chars
        self.chunk_overlap = min(chunk_overlap, max(0, chunk_chars - 1))

    async def invoke(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "ingest":
            return self._ingest(payload)
        if action == "search":
            return self._search(payload)
        if action == "list":
            return self._list(payload)
        if action == "asset":
            return self._asset(payload)
        if action == "preview":
            return self._preview(payload)
        if action == "delete":
            return self._delete(payload)
        raise ValueError(f"Unsupported documents action: {action}")

    def _connect(self) -> sqlite3.Connection:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                document_id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                relative_path TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                extension TEXT NOT NULL,
                extracted_characters INTEGER NOT NULL,
                indexed_characters INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS document_chunks (
                document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
                chunk_index INTEGER NOT NULL,
                start_char INTEGER NOT NULL,
                end_char INTEGER NOT NULL,
                content TEXT NOT NULL,
                PRIMARY KEY(document_id, chunk_index)
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_document_chunks_doc ON document_chunks(document_id, chunk_index)")
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _ingest(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("approved") is not True:
            raise DocumentUploadApprovalRequired("Document ingestion requires approved=true.")
        filename = self._text(payload.get("filename"), "filename", 255)
        safe_name = Path(filename.replace("\\", "/")).name
        extension = Path(safe_name).suffix.casefold()
        if extension not in self.supported_extensions:
            raise ValueError("Unsupported document type.")
        encoded = payload.get("content_base64")
        if not isinstance(encoded, str):
            raise ValueError("content_base64 must be a base64 string.")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise ValueError("content_base64 is invalid.") from exc
        if not raw:
            raise ValueError("Uploaded document is empty.")
        if len(raw) > self.max_upload_bytes:
            raise ValueError("Document exceeds the upload size limit.")

        text = self._extract(raw, extension)[: self.max_extracted_chars]
        document_id = uuid.uuid4().hex
        stored_name = f"{document_id}{extension}"
        self.documents_dir.mkdir(parents=True, exist_ok=True)
        stored_path = self.documents_dir / stored_name
        temporary_path = self.documents_dir / f".{stored_name}.tmp"
        temporary_path.write_bytes(raw)
        os.replace(temporary_path, stored_path)
        digest = hashlib.sha256(raw).hexdigest()
        created_at = datetime.now(UTC).isoformat(timespec="seconds")
        chunks = self._chunk_text(text)
        try:
            with self._connection() as connection:
                connection.execute(
                    """
                    INSERT INTO documents(document_id, filename, relative_path, sha256, extension,
                        extracted_characters, indexed_characters, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (document_id, safe_name, f"documents/{stored_name}", digest, extension, len(text), len(text), created_at),
                )
                connection.executemany(
                    "INSERT INTO document_chunks(document_id, chunk_index, start_char, end_char, content) VALUES (?, ?, ?, ?, ?)",
                    [(document_id, index, start, end, content) for index, (start, end, content) in enumerate(chunks)],
                )
        except Exception:
            stored_path.unlink(missing_ok=True)
            raise
        return {
            "status": "indexed",
            "document_id": document_id,
            "filename": safe_name,
            "sha256": digest,
            "extracted_characters": len(text),
            "indexed_chunks": len(chunks),
            "truncated": len(text) >= self.max_extracted_chars,
            "created_at": created_at,
        }

    def _extract(self, raw: bytes, extension: str) -> str:
        if extension in {".txt", ".md", ".py", ".json", ".ts", ".tsx"}:
            return raw.decode("utf-8-sig", errors="replace")
        if extension == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(raw))
            return "\n".join(page.extract_text() or "" for page in reader.pages[:500])
        if extension == ".docx":
            from docx import Document

            document = Document(io.BytesIO(raw))
            return "\n".join(paragraph.text for paragraph in document.paragraphs)
        if extension == ".pptx":
            from pptx import Presentation

            presentation = Presentation(io.BytesIO(raw))
            return "\n".join(
                shape.text for slide in presentation.slides for shape in slide.shapes if hasattr(shape, "text")
            )
        if extension in {".xlsx", ".xlsm"}:
            from openpyxl import load_workbook

            workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
            try:
                rows = []
                for sheet in workbook.worksheets:
                    rows.append(f"[{sheet.title}]")
                    rows.extend(" | ".join(str(cell.value or "") for cell in row) for row in sheet.iter_rows())
                return "\n".join(rows)
            finally:
                workbook.close()
        return ""

    def _chunk_text(self, text: str) -> list[tuple[int, int, str]]:
        chunks: list[tuple[int, int, str]] = []
        start = 0
        while start < len(text):
            end = min(start + self.chunk_chars, len(text))
            chunks.append((start, end, text[start:end]))
            if end == len(text):
                break
            start = end - self.chunk_overlap
        return chunks

    def _search(self, payload: dict[str, Any]) -> dict[str, Any]:
        query = self._text(payload.get("query"), "query", 500)
        limit = self._limit(payload.get("limit"), default=4, maximum=10)
        terms = list(dict.fromkeys(term.casefold() for term in re.findall(r"[\w-]{3,}", query)))[:20]
        if not terms:
            return {"query": query, "count": 0, "results": []}
        clauses = " OR ".join("c.content LIKE ? ESCAPE '!'" for _ in terms)
        patterns = [f"%{self._escape_like(term)}%" for term in terms]
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT d.document_id,d.filename,c.chunk_index,c.start_char,c.end_char,c.content "
                "FROM document_chunks c JOIN documents d ON d.document_id=c.document_id "
                f"WHERE {clauses} LIMIT 500",
                patterns,
            ).fetchall()
        ranked = sorted(
            rows,
            key=lambda row: sum(row["content"].casefold().count(term) for term in terms),
            reverse=True,
        )
        results = [
            {
                "document_id": row["document_id"],
                "filename": row["filename"],
                "chunk_index": row["chunk_index"],
                "start_char": row["start_char"],
                "end_char": row["end_char"],
                "content": row["content"],
                "source_url": f"/api/plugins/documents/assets/{row['document_id']}",
            }
            for row in ranked[:limit]
        ]
        return {"query": query, "count": len(results), "results": results}

    def _list(self, payload: dict[str, Any]) -> dict[str, Any]:
        limit = self._limit(payload.get("limit"), default=100, maximum=500)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT document_id,filename,sha256,extension,extracted_characters,indexed_characters,created_at "
                "FROM documents ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return {"documents": [dict(row) for row in rows]}

    @staticmethod
    def _escape_like(value: str) -> str:
        return value.replace("!", "!!").replace("%", "!%").replace("_", "!_")

    @staticmethod
    def _text(value: Any, key: str, max_length: int) -> str:
        if not isinstance(value, str) or not value.strip() or len(value) > max_length:
            raise ValueError(f"{key} must be a non-empty string up to {max_length} characters.")
        return value.strip()

    @staticmethod
    def _limit(value: Any, default: int, maximum: int) -> int:
        if value is None:
            return default
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("limit must be an integer.")
        return max(1, min(value, maximum))

    def _asset(self, payload: dict[str, Any]) -> dict[str, Any]:
        document_id = payload.get("document_id")
        if not isinstance(document_id, str) or not re.fullmatch(r"[a-f0-9]{32}", document_id):
            raise DocumentNotFoundError("Document was not found.")
        with self._connection() as connection:
            row = connection.execute(
                "SELECT filename, relative_path, extension FROM documents WHERE document_id = ?",
                (document_id,),
            ).fetchone()
        if row is None:
            raise DocumentNotFoundError("Document was not found.")
        target = self._stored_path(row["relative_path"])
        if not target.is_file():
            raise DocumentNotFoundError("Document was not found.")
        media_type = mimetypes.guess_type(row["filename"])[0] or "application/octet-stream"
        return {"path": str(target), "filename": row["filename"], "media_type": media_type}

    def _preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        document_id = payload.get("document_id")
        if not isinstance(document_id, str) or not re.fullmatch(r"[a-f0-9]{32}", document_id):
            raise DocumentNotFoundError("Document was not found.")
        with self._connection() as connection:
            document = connection.execute(
                "SELECT filename,relative_path,extension,indexed_characters FROM documents WHERE document_id=?",
                (document_id,),
            ).fetchone()
            if document is None:
                raise DocumentNotFoundError("Document was not found.")
            source = self._stored_path(document["relative_path"])
            if not source.is_file():
                raise DocumentNotFoundError("Document was not found.")
            chunks = connection.execute(
                "SELECT start_char,end_char,content FROM document_chunks WHERE document_id=? ORDER BY chunk_index",
                (document_id,),
            ).fetchall()

        parts: list[str] = []
        collected = 0
        previous_end = 0
        for chunk in chunks:
            overlap = max(0, previous_end - chunk["start_char"])
            text = chunk["content"][overlap:]
            remaining = self.max_preview_chars - collected
            if remaining <= 0:
                break
            parts.append(text[:remaining])
            collected += min(len(text), remaining)
            previous_end = chunk["end_char"]
        content = "".join(parts)
        return {
            "document_id": document_id,
            "filename": document["filename"],
            "extension": document["extension"],
            "content": content,
            "indexed_characters": document["indexed_characters"],
            "truncated": document["indexed_characters"] > len(content),
        }

    def _delete(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("approved") is not True:
            raise DocumentDeleteApprovalRequired("Deleting a document requires approved=true.")
        document_id = payload.get("document_id")
        if not isinstance(document_id, str) or not re.fullmatch(r"[a-f0-9]{32}", document_id):
            raise DocumentNotFoundError("Document was not found.")

        tombstone: Path | None = None
        target: Path | None = None
        try:
            with self._connection() as connection:
                row = connection.execute(
                    "SELECT filename,relative_path FROM documents WHERE document_id=?",
                    (document_id,),
                ).fetchone()
                if row is None:
                    raise DocumentNotFoundError("Document was not found.")
                target = self._stored_path(row["relative_path"])
                if target.exists():
                    if not target.is_file():
                        raise DocumentNotFoundError("Document was not found.")
                    tombstone = target.with_name(f".{target.name}.{uuid.uuid4().hex}.deleting")
                    os.replace(target, tombstone)
                cursor = connection.execute("DELETE FROM documents WHERE document_id=?", (document_id,))
                if cursor.rowcount != 1:
                    raise DocumentNotFoundError("Document was not found.")
        except Exception:
            if tombstone is not None and target is not None and tombstone.exists() and not target.exists():
                os.replace(tombstone, target)
            raise

        if tombstone is not None:
            tombstone.unlink(missing_ok=True)
        return {"document_id": document_id, "filename": row["filename"], "deleted": True}

    def _stored_path(self, relative_path: str) -> Path:
        relative = Path(relative_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise DocumentNotFoundError("Document was not found.")
        candidate = self.data_dir / relative
        if candidate.is_symlink():
            raise DocumentNotFoundError("Document was not found.")
        target = candidate.resolve()
        if self.documents_dir.resolve() not in target.parents:
            raise DocumentNotFoundError("Document was not found.")
        return target