from __future__ import annotations

import os
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

from app.chat_context import MAX_CHAT_TEXT_CHARS
from app.plugins.contracts import PluginManifest


class SessionDeleteApprovalRequired(Exception):
    pass


class SessionsPlugin:
    manifest = PluginManifest(
        plugin_id="sessions",
        display_name="Chat Sessions",
        description="Sohbetleri oturum kimliğiyle yerel SQLite'ta saklar.",
        actions=("list", "create", "append_turn", "messages", "context", "delete"),
    )

    default_context_messages: ClassVar[int] = 20
    max_context_messages: ClassVar[int] = 40

    def __init__(self, database_path: str | Path | None = None) -> None:
        if database_path is None:
            data_root = Path(os.getenv("AI_DATA_DIR", "/data")).expanduser()
            database_path = data_root / "memory.db"
        self.database_path = Path(database_path).expanduser().resolve()

    async def invoke(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "list":
            return self._list(payload)
        if action == "create":
            return self._create(payload)
        if action == "append_turn":
            return self._append_turn(payload)
        if action == "messages":
            return self._messages(payload)
        if action == "context":
            return self._context(payload)
        if action == "delete":
            return self._delete(payload)
        raise ValueError(f"Unsupported session action: {action}")

    def _connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_sessions (
                session_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id, message_id)"
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

    def _create(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = str(uuid.uuid4())
        title = self._text(payload.get("title", "Yeni sohbet"), "title", 200)
        now = self._now()
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO chat_sessions(session_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (session_id, title, now, now),
            )
        return {"session_id": session_id, "title": title, "created_at": now}

    def _append_turn(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = self._text(payload.get("session_id", ""), "session_id", 80)
        user_message = self._text(payload.get("user_message", ""), "user_message", 20_000)
        assistant_message = self._text(
            payload.get("assistant_message", ""), "assistant_message", MAX_CHAT_TEXT_CHARS,
        )
        title = self._text(payload.get("title", user_message[:80]), "title", 200)
        now = self._now()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO chat_sessions(session_id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET updated_at = excluded.updated_at
                """,
                (session_id, title, now, now),
            )
            connection.executemany(
                "INSERT INTO chat_messages(session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (
                    (session_id, "user", user_message, now),
                    (session_id, "assistant", assistant_message, now),
                ),
            )
        return {"session_id": session_id, "saved_messages": 2, "updated_at": now}

    def _list(self, payload: dict[str, Any]) -> dict[str, Any]:
        limit = self._limit(payload.get("limit"), default=20, maximum=100)
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT s.session_id, s.title, s.created_at, s.updated_at,
                    (SELECT COUNT(*) FROM chat_messages m WHERE m.session_id = s.session_id) AS message_count
                FROM chat_sessions s ORDER BY s.updated_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return {"sessions": [dict(row) for row in rows]}

    def _messages(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = self._text(payload.get("session_id", ""), "session_id", 80)
        limit = self._limit(payload.get("limit"), default=100, maximum=200)
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT message_id, session_id, role, content, created_at
                FROM chat_messages WHERE session_id = ? ORDER BY message_id DESC LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        messages = [dict(row) for row in reversed(rows)]
        return {"session_id": session_id, "messages": messages}

    def _context(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = self._text(payload.get("session_id", ""), "session_id", 80)
        limit = self._limit(payload.get("limit"), default=self.default_context_messages, maximum=self.max_context_messages)
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT role, content FROM chat_messages
                WHERE session_id = ? ORDER BY message_id DESC LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        messages = [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]
        return {"session_id": session_id, "messages": messages}

    def _delete(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("approved") is not True:
            raise SessionDeleteApprovalRequired("Deleting a session requires approved=true.")
        session_id = self._text(payload.get("session_id", ""), "session_id", 80)
        with self._connection() as connection:
            cursor = connection.execute("DELETE FROM chat_sessions WHERE session_id = ?", (session_id,))
        return {"session_id": session_id, "deleted": cursor.rowcount > 0}

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

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat(timespec="seconds")