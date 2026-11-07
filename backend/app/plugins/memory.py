from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.legacy_memory_browser import browse_legacy_memory
from app.plugins.contracts import PluginManifest
from app.plugins.worker_lifecycle import run_thread

logger = logging.getLogger(__name__)


class MemoryWriteApprovalRequired(Exception):
    pass


class MemoryProposalNotFoundError(Exception):
    pass


PERSONAL_DOCUMENT_PATTERN = re.compile(r"(?i)\b(?:cv|resume|curriculum vitae|cover letter|özgeçmiş|ön yazı)\b")
SECRET_VALUE_PATTERN = re.compile(
    r"(?i)\b(?:[a-z0-9_]*(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password|parola|şifre|bearer)[a-z0-9_]*)"
    r"\s*[:=]\s*[\"']?([^\s\"'`]{8,})"
)
TOKEN_PATTERN = re.compile(
    r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}|xox[baprs]-[A-Za-z0-9-]{20,}|AKIA[0-9A-Z]{16})\b"
)


def memory_rejection_reason(text: str) -> str:
    if PERSONAL_DOCUMENT_PATTERN.search(text):
        return "personal_document"
    if SECRET_VALUE_PATTERN.search(text) or TOKEN_PATTERN.search(text):
        return "credential_like_content"
    return ""


class MemoryPlugin:
    manifest = PluginManifest(
        plugin_id="memory",
        display_name="Local Memory",
        description="Onaylı notları yerel SQLite veritabanında saklar, arar ve öğrenme önerilerini onay kuyruğunda tutar.",
        actions=(
            "remember", "search", "timeline", "taxonomy", "export", "import", "preview_source", "delete_source",
            "propose", "proposals", "approve_proposal", "reject_proposal", "legacy_list", "legacy_get",
        ),
    )
    max_portable_memories = 5_000
    max_portable_bytes = 10_000_000
    max_pending_proposals = 50
    proposal_categories = frozenset(
        {"preference", "project_fact", "procedure", "research", "task_history", "library_knowledge", "agent_workflow", "general"}
    )

    def __init__(self, database_path: str | Path | None = None) -> None:
        if database_path is None:
            data_root = Path(os.getenv("AI_DATA_DIR", "/data")).expanduser()
            database_path = data_root / "memory.db"
        self.database_path = Path(database_path).expanduser().resolve()
        self.proposal_ttl_seconds = max(60, int(os.getenv("MEMORY_PROPOSAL_TTL_SECONDS", str(7 * 24 * 60 * 60))))

    async def invoke(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action in {"legacy_list", "legacy_get"}:
            return await run_thread(lambda: browse_legacy_memory(self.database_path, action, payload), logger)
        if action == "remember":
            return self._remember(payload)
        if action == "search":
            return self._search(payload)
        if action == "timeline":
            return self._timeline(payload)
        if action == "taxonomy":
            return self._taxonomy()
        if action == "export":
            return self._export(payload)
        if action == "import":
            return self._import(payload)
        if action == "preview_source":
            return self._preview_source(payload)
        if action == "delete_source":
            return self._delete_source(payload)
        if action == "propose":
            return self._propose(payload)
        if action == "proposals":
            return self._proposals()
        if action == "approve_proposal":
            return self._approve_proposal(payload)
        if action == "reject_proposal":
            return self._reject_proposal(payload)
        raise ValueError(f"Unsupported memory action: {action}")

    def _connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                project TEXT NOT NULL,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL
            )
            """
        )
        columns = {row[1] for row in connection.execute("PRAGMA table_info(memories)").fetchall()}
        if "source" not in columns:
            connection.execute("ALTER TABLE memories ADD COLUMN source TEXT NOT NULL DEFAULT 'manual'")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_memories_project_created ON memories(project, created_at DESC)"
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_memories_source ON memories(source)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category)")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_proposals (
                proposal_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                expires_at REAL NOT NULL,
                project TEXT NOT NULL,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                source TEXT NOT NULL,
                reason TEXT NOT NULL
            )
            """
        )
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

    def _remember(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("approved") is not True:
            raise MemoryWriteApprovalRequired("Saving memory requires approved=true.")

        title = self._required_text(payload, "title", 200)
        content = self._required_text(payload, "content", 10_000)
        project = self._optional_text(payload, "project", 200)
        category = self._optional_text(payload, "category", 80) or "general"
        source = self._optional_text(payload, "source", 200) or "manual"
        created_at = datetime.now(UTC).isoformat(timespec="seconds")

        with self._connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO memories (created_at, project, category, title, content, source)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (created_at, project, category, title, content, source),
            )
            memory_id = cursor.lastrowid
        return {"status": "saved", "id": memory_id, "created_at": created_at}

    def _search(self, payload: dict[str, Any]) -> dict[str, Any]:
        query = self._required_text(payload, "query", 500)
        project = self._optional_text(payload, "project", 200)
        category = self._optional_text(payload, "category", 80)
        source = self._optional_text(payload, "source", 200)
        limit = self._limit(payload.get("limit"), default=10, maximum=50)
        pattern = f"%{query}%"
        sql = "SELECT id, created_at, project, category, title, content, source FROM memories WHERE (title LIKE ? OR content LIKE ?)"
        parameters: list[Any] = [pattern, pattern]
        if project:
            sql += " AND project = ?"
            parameters.append(project)
        if category:
            sql += " AND category = ?"
            parameters.append(category)
        if source:
            sql += " AND source = ?"
            parameters.append(source)
        sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
        parameters.append(limit)
        with self._connection() as connection:
            rows = connection.execute(sql, parameters).fetchall()
        return {"memories": [dict(row) for row in rows]}

    def _timeline(self, payload: dict[str, Any]) -> dict[str, Any]:
        project = self._optional_text(payload, "project", 200)
        limit = self._limit(payload.get("limit"), default=20, maximum=100)
        sql = "SELECT id, created_at, project, category, title, content, source FROM memories"
        parameters: list[Any] = []
        if project:
            sql += " WHERE project = ?"
            parameters.append(project)
        sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
        parameters.append(limit)
        with self._connection() as connection:
            rows = connection.execute(sql, parameters).fetchall()
        return {"memories": [dict(row) for row in rows]}

    def _taxonomy(self) -> dict[str, list[str]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT DISTINCT category,project,source FROM memories ORDER BY category,project,source"
            ).fetchall()
        return {
            "categories": sorted({row["category"] for row in rows if row["category"]}),
            "projects": sorted({row["project"] for row in rows if row["project"]}),
            "sources": sorted({row["source"] for row in rows if row["source"]}),
        }

    def _export(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("approved") is not True:
            raise MemoryWriteApprovalRequired("Exporting memory requires approved=true.")
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT id,created_at,project,category,title,content,source FROM memories ORDER BY id LIMIT ?",
                (self.max_portable_memories + 1,),
            ).fetchall()
        if len(rows) > self.max_portable_memories:
            raise ValueError(f"Memory export exceeds the {self.max_portable_memories}-entry limit.")
        export = {
            "format": "deep-panda-memory-v1",
            "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "memories": [dict(row) for row in rows],
        }
        if len(json.dumps(export, ensure_ascii=False).encode("utf-8")) > self.max_portable_bytes:
            raise ValueError(f"Memory export exceeds the {self.max_portable_bytes}-byte limit.")
        return export

    def _import(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("approved") is not True:
            raise MemoryWriteApprovalRequired("Importing memories requires approved=true.")
        if payload.get("format") != "deep-panda-memory-v1":
            raise ValueError("Unsupported memory import format.")
        memories = payload.get("memories")
        if not isinstance(memories, list) or len(memories) > self.max_portable_memories:
            raise ValueError(f"memories must be a list with at most {self.max_portable_memories} entries.")
        encoded = json.dumps(memories, ensure_ascii=False, allow_nan=False).encode("utf-8")
        if len(encoded) > self.max_portable_bytes:
            raise ValueError(f"Memory import exceeds the {self.max_portable_bytes}-byte limit.")
        normalized: list[tuple[str, str, str, str, str]] = []
        for index, item in enumerate(memories):
            if not isinstance(item, dict):
                raise ValueError(f"memories[{index}] must be an object.")
            title = self._required_text(item, "title", 200)
            content = self._required_text(item, "content", 10_000)
            project = self._optional_text(item, "project", 200)
            category = self._optional_text(item, "category", 80) or "general"
            source = self._optional_text(item, "source", 200) or "import"
            normalized.append((title, content, project, category, source))

        imported = 0
        duplicates = 0
        now = datetime.now(UTC).isoformat(timespec="seconds")
        with self._connection() as connection:
            existing = {
                (row["title"], row["content"], row["project"], row["category"], row["source"])
                for row in connection.execute("SELECT title,content,project,category,source FROM memories")
            }
            seen = set(existing)
            for entry in normalized:
                if entry in seen:
                    duplicates += 1
                    continue
                title, content, project, category, source = entry
                connection.execute(
                    "INSERT INTO memories(created_at,project,category,title,content,source) VALUES(?,?,?,?,?,?)",
                    (now, project, category, title, content, source),
                )
                seen.add(entry)
                imported += 1
        return {"status": "imported", "imported": imported, "duplicates": duplicates}

    def _preview_source(self, payload: dict[str, Any]) -> dict[str, Any]:
        source = self._required_text(payload, "source", 200)
        with self._connection() as connection:
            count = connection.execute("SELECT COUNT(*) FROM memories WHERE source=?", (source,)).fetchone()[0]
            rows = connection.execute(
                "SELECT id,created_at,project,category,title,content,source FROM memories WHERE source=? ORDER BY id LIMIT 100",
                (source,),
            ).fetchall()
        return {"source": source, "count": count, "memories": [dict(row) for row in rows]}

    def _delete_source(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("approved") is not True:
            raise MemoryWriteApprovalRequired("Deleting a memory source requires approved=true.")
        source = self._required_text(payload, "source", 200)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT id,created_at,project,category,title,content,source FROM memories WHERE source=? ORDER BY id LIMIT ?",
                (source, self.max_portable_memories + 1),
            ).fetchall()
            if len(rows) > self.max_portable_memories:
                raise ValueError(f"Source deletion exceeds the {self.max_portable_memories}-entry backup limit.")
            memories = [dict(row) for row in rows]
            backup = {
                "format": "deep-panda-memory-v1",
                "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "source": source,
                "memories": memories,
            }
            encoded_backup = json.dumps(backup, ensure_ascii=False).encode("utf-8")
            if len(encoded_backup) > self.max_portable_bytes:
                raise ValueError(f"Source deletion backup exceeds the {self.max_portable_bytes}-byte limit.")
            backup_dir = self.database_path.parent / "memory-backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_path = backup_dir / f"source-{uuid.uuid4().hex}.json"
            temporary_path = backup_path.with_suffix(".tmp")
            temporary_path.write_bytes(encoded_backup)
            os.replace(temporary_path, backup_path)
            connection.execute("DELETE FROM memories WHERE source=?", (source,))
        return {"source": source, "deleted": len(memories), "backup_path": str(backup_path)}

    def _propose(self, payload: dict[str, Any]) -> dict[str, Any]:
        content = self._required_text(payload, "content", 10_000)
        title = self._optional_text(payload, "title", 200) or " ".join(content.split())[:80]
        project = self._optional_text(payload, "project", 200)
        category = self._optional_text(payload, "category", 80) or "general"
        if category not in self.proposal_categories:
            category = "general"
        source = self._optional_text(payload, "source", 200) or "agent"
        reason = self._optional_text(payload, "reason", 500)
        rejection = memory_rejection_reason(f"{title}\n{content}")
        if rejection:
            return {"status": "not_saved", "reason": rejection}
        now = time.time()
        proposal_id = uuid.uuid4().hex
        with self._connection() as connection:
            connection.execute("DELETE FROM memory_proposals WHERE expires_at <= ?", (now,))
            duplicate = connection.execute(
                "SELECT proposal_id FROM memory_proposals WHERE content=? AND project=? AND category=?",
                (content, project, category),
            ).fetchone()
            if duplicate is not None:
                return {"status": "approval_required", "proposal_id": duplicate["proposal_id"], "duplicate": True}
            overflow = connection.execute("SELECT COUNT(*) FROM memory_proposals").fetchone()[0] - self.max_pending_proposals + 1
            if overflow > 0:
                connection.execute(
                    "DELETE FROM memory_proposals WHERE proposal_id IN (SELECT proposal_id FROM memory_proposals ORDER BY expires_at LIMIT ?)",
                    (overflow,),
                )
            connection.execute(
                "INSERT INTO memory_proposals VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    proposal_id, datetime.now(UTC).isoformat(timespec="seconds"), now + self.proposal_ttl_seconds,
                    project, category, title, content, source, reason,
                ),
            )
        return {"status": "approval_required", "proposal_id": proposal_id, "expires_in": self.proposal_ttl_seconds}

    def _proposals(self) -> dict[str, Any]:
        now = time.time()
        with self._connection() as connection:
            connection.execute("DELETE FROM memory_proposals WHERE expires_at <= ?", (now,))
            rows = connection.execute("SELECT * FROM memory_proposals ORDER BY created_at DESC").fetchall()
        return {
            "proposals": [
                {**{key: row[key] for key in row.keys() if key != "expires_at"}, "expires_in": max(0, int(row["expires_at"] - now))}
                for row in rows
            ]
        }

    def _approve_proposal(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("approved") is not True:
            raise MemoryWriteApprovalRequired("Approving a learning proposal requires approved=true.")
        proposal_id = self._required_text(payload, "proposal_id", 64)
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM memory_proposals WHERE proposal_id=? AND expires_at > ?", (proposal_id, time.time()),
            ).fetchone()
            if row is None:
                raise MemoryProposalNotFoundError("Learning proposal was not found or has expired.")
            connection.execute("DELETE FROM memory_proposals WHERE proposal_id=?", (proposal_id,))
            if memory_rejection_reason(f"{row['title']}\n{row['content']}"):
                return {"status": "not_saved", "proposal_id": proposal_id, "reason": "unsafe_content"}
            created_at = datetime.now(UTC).isoformat(timespec="seconds")
            cursor = connection.execute(
                "INSERT INTO memories(created_at,project,category,title,content,source) VALUES(?,?,?,?,?,?)",
                (created_at, row["project"], row["category"], row["title"], row["content"], row["source"]),
            )
        return {"status": "saved", "proposal_id": proposal_id, "id": cursor.lastrowid, "created_at": created_at}

    def _reject_proposal(self, payload: dict[str, Any]) -> dict[str, Any]:
        proposal_id = self._required_text(payload, "proposal_id", 64)
        with self._connection() as connection:
            deleted = connection.execute("DELETE FROM memory_proposals WHERE proposal_id=?", (proposal_id,)).rowcount
        if not deleted:
            raise MemoryProposalNotFoundError("Learning proposal was not found or has expired.")
        return {"status": "rejected", "proposal_id": proposal_id}

    @staticmethod
    def _required_text(payload: dict[str, Any], key: str, max_length: int) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > max_length:
            raise ValueError(f"{key} must be a non-empty string up to {max_length} characters.")
        return value.strip()

    @classmethod
    def _optional_text(cls, payload: dict[str, Any], key: str, max_length: int) -> str:
        value = payload.get(key, "")
        if value is None or value == "":
            return ""
        return cls._required_text(payload, key, max_length)

    @staticmethod
    def _limit(value: Any, default: int, maximum: int) -> int:
        if value is None:
            return default
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("limit must be an integer.")
        return max(1, min(value, maximum))