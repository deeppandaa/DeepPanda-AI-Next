from __future__ import annotations

import logging
import os
import re
import sqlite3
import time
from functools import partial
from pathlib import Path
from typing import Any

from app.plugins.contracts import PluginManifest
from app.plugins.integration_errors import IntegrationNotFoundError, require_approval
from app.plugins.worker_lifecycle import run_thread

logger = logging.getLogger(__name__)

_DB_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,120}\.(?:db|sqlite3?)")
_READ_PREFIX = re.compile(r"^\s*(?:--[^\n]*\n\s*)*(select|with|explain|values)\b", re.IGNORECASE)
_DENIED_ACTIONS = frozenset({
    sqlite3.SQLITE_ATTACH,
    sqlite3.SQLITE_DETACH,
    sqlite3.SQLITE_PRAGMA,
    sqlite3.SQLITE_INSERT,
    sqlite3.SQLITE_UPDATE,
    sqlite3.SQLITE_DELETE,
    sqlite3.SQLITE_CREATE_TABLE,
    sqlite3.SQLITE_DROP_TABLE,
    sqlite3.SQLITE_ALTER_TABLE,
    sqlite3.SQLITE_TRANSACTION,
})


class DatabasePlugin:
    """Read-only inspector for the SQLite databases every plugin keeps under AI_DATA_DIR."""

    manifest = PluginManifest(
        plugin_id="database",
        display_name="Veritabanı (SQL)",
        description="AI_DATA_DIR altındaki SQLite veritabanlarını listeler, tabloları gösterir, salt-okunur SQL çalıştırır ve onaylı yedek alır.",
        actions=("overview", "tables", "query", "check", "backup"),
    )

    max_rows = 500

    def __init__(self, data_dir: str | Path | None = None) -> None:
        self.data_dir = Path(data_dir or os.getenv("AI_DATA_DIR", "/data")).expanduser().resolve()
        self.manager_url = os.getenv("DB_MANAGER_URL", "http://127.0.0.1:8789")

    async def invoke(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        handlers = {
            "overview": self.overview,
            "tables": self.tables,
            "query": self.query,
            "check": self.check,
            "backup": self.backup,
        }
        handler = handlers.get(action)
        if handler is None:
            raise ValueError(f"Unsupported database action: {action}")
        return await run_thread(partial(handler, payload), logger)

    def overview(self, _payload: dict[str, Any] | None = None) -> dict[str, Any]:
        databases = []
        if self.data_dir.is_dir():
            for path in sorted(self.data_dir.iterdir()):
                if not path.is_file() or path.is_symlink() or not _DB_NAME.fullmatch(path.name):
                    continue
                entry: dict[str, Any] = {
                    "name": path.name,
                    "size_bytes": path.stat().st_size,
                    "modified": int(path.stat().st_mtime),
                }
                try:
                    with self._connect(path) as connection:
                        entry["tables"] = len(self._table_names(connection))
                        entry["journal_mode"] = connection.execute("PRAGMA journal_mode").fetchone()[0]
                except sqlite3.Error as exc:
                    entry["error"] = str(exc)
                databases.append(entry)
        return {
            "data_dir": str(self.data_dir),
            "databases": databases,
            "manager_url": self.manager_url,
            "manager_hint": "docker compose --profile manager up -d db-manager",
        }

    def tables(self, payload: dict[str, Any]) -> dict[str, Any]:
        path = self._database_path(payload.get("database"))
        with self._connect(path) as connection:
            tables = []
            for name in self._table_names(connection):
                quoted = _quote_identifier(name)
                columns = [
                    {"name": row[1], "type": row[2], "not_null": bool(row[3]), "primary_key": bool(row[5])}
                    for row in connection.execute(f"PRAGMA table_info({quoted})")
                ]
                rows = connection.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0]
                tables.append({"name": name, "rows": rows, "columns": columns})
        return {"database": path.name, "tables": tables}

    def query(self, payload: dict[str, Any]) -> dict[str, Any]:
        path = self._database_path(payload.get("database"))
        sql = payload.get("sql")
        if not isinstance(sql, str) or not sql.strip() or len(sql) > 20_000:
            raise ValueError("sql must be non-empty text up to 20000 characters.")
        if not _READ_PREFIX.match(sql):
            raise ValueError("Yalnızca SELECT, WITH, EXPLAIN veya VALUES sorguları çalıştırılabilir.")
        limit = payload.get("limit", 200)
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= self.max_rows:
            raise ValueError(f"limit must be an integer between 1 and {self.max_rows}.")
        started = time.monotonic()
        with self._connect(path) as connection:
            connection.set_authorizer(_read_only_authorizer)
            try:
                cursor = connection.execute(sql)
            except sqlite3.Warning as exc:
                raise ValueError("Tek seferde yalnızca bir SQL ifadesi çalıştırılabilir.") from exc
            except sqlite3.DatabaseError as exc:
                raise ValueError(f"SQL hatası: {exc}") from exc
            columns = [item[0] for item in cursor.description or []]
            rows = [[_json_value(value) for value in row] for row in cursor.fetchmany(limit + 1)]
        truncated = len(rows) > limit
        return {
            "database": path.name,
            "columns": columns,
            "rows": rows[:limit],
            "truncated": truncated,
            "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
        }

    def check(self, payload: dict[str, Any]) -> dict[str, Any]:
        path = self._database_path(payload.get("database"))
        with self._connect(path) as connection:
            result = [row[0] for row in connection.execute("PRAGMA quick_check(20)")]
        return {"database": path.name, "ok": result == ["ok"], "messages": result}

    def backup(self, payload: dict[str, Any]) -> dict[str, Any]:
        path = self._database_path(payload.get("database"))
        require_approval(payload, "Veritabanı yedeği almak için açık onay gerekir.")
        backup_dir = self.data_dir / "db-backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        target = backup_dir / f"{path.stem}-{time.strftime('%Y%m%d-%H%M%S')}{path.suffix}"
        destination = sqlite3.connect(target)
        try:
            with self._connect(path) as source:
                source.backup(destination)
        finally:
            destination.close()
        return {"database": path.name, "backup": str(target), "size_bytes": target.stat().st_size}

    def _database_path(self, name: Any) -> Path:
        if not isinstance(name, str) or not _DB_NAME.fullmatch(name):
            raise ValueError("database must be a database file name such as memory.db.")
        path = (self.data_dir / name).resolve()
        if path.parent != self.data_dir or not path.is_file() or path.is_symlink():
            raise IntegrationNotFoundError(f"Veritabanı bulunamadı: {name}")
        return path

    @staticmethod
    def _connect(path: Path) -> _ClosingConnection:
        connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=5)
        connection.execute("PRAGMA query_only = ON")
        return _ClosingConnection(connection)

    @staticmethod
    def _table_names(connection: sqlite3.Connection) -> list[str]:
        return [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]


class _ClosingConnection:
    """sqlite3.Connection's context manager only commits; this one also closes."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def __enter__(self) -> sqlite3.Connection:
        return self._connection

    def __exit__(self, *_exc: object) -> None:
        self._connection.close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)


def _read_only_authorizer(action: int, _arg1: Any, _arg2: Any, _db: Any, _trigger: Any) -> int:
    return sqlite3.SQLITE_DENY if action in _DENIED_ACTIONS else sqlite3.SQLITE_OK


def _quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _json_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return f"<{len(value)} bayt BLOB>"
    if isinstance(value, str) and len(value) > 4_000:
        return value[:4_000] + "…"
    return value
