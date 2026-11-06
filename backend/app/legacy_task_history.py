"""View historical tasks directly from a selected local legacy ZIP, without executing them."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sqlite3
import sys
import zipfile
from pathlib import Path
from typing import Any

from app.legacy_memory_preview import archive_database_entries, read_archive_database

MAX_TASKS = 100
MAX_STEPS = 500
MAX_TEXT_BYTES = 200_000
TASK_COLUMNS = (
    "task_id", "request", "intent", "plan", "approved", "status", "commands",
    "changed_files", "tests", "result", "created_at", "updated_at",
)
STEP_COLUMNS = ("task_id", "step_index", "title", "status", "evidence", "updated_at")


def _validate_fields(row: sqlite3.Row, columns: tuple[str, ...]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for column in columns:
        value = row[column]
        if value is not None and not isinstance(value, (str, int)):
            raise ValueError(f"Unexpected type in historical {column}.")
        if isinstance(value, str) and len(value.encode("utf-8")) > MAX_TEXT_BYTES:
            raise ValueError(f"Historical {column} exceeds the display limit.")
        result[column] = value
    return result


def _require_table(connection: sqlite3.Connection, table: str, columns: tuple[str, ...]) -> None:
    if not connection.execute(
        "SELECT 1 FROM sqlite_schema WHERE type='table' AND name=?", (table,)
    ).fetchone():
        raise ValueError(f"Historical {table} table is missing.")
    existing = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
    if not set(columns).issubset(existing):
        raise ValueError(f"Historical {table} schema is incomplete.")


def read_history(
    archive_path: Path | io.BytesIO, database_index: int, expected_sha256: str, task_id: str | None = None
) -> dict[str, Any]:
    if not isinstance(database_index, int) or isinstance(database_index, bool) or database_index < 1:
        raise ValueError("Database index must be a positive integer.")
    if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("Expected SHA-256 must be 64 lowercase hexadecimal characters.")
    if task_id is not None and (not isinstance(task_id, str) or not task_id or len(task_id) > 200):
        raise ValueError("Task ID must be nonempty text up to 200 characters.")
    with zipfile.ZipFile(archive_path) as archive:
        entries = archive_database_entries(archive)
        if database_index > len(entries):
            raise ValueError("Database index exceeds the candidate count.")
        data = read_archive_database(archive, entries[database_index - 1])
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected_sha256:
        raise ValueError("Selected database SHA-256 does not match the expected value.")
    connection = sqlite3.connect(":memory:")
    try:
        connection.deserialize(data)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
        if [tuple(row) for row in connection.execute("PRAGMA integrity_check")] != [("ok",)]:
            raise ValueError("Source SQLite integrity check failed.")
        _require_table(connection, "task_records", TASK_COLUMNS)
        result: dict[str, Any] = {
            "mode": "historical_read_only",
            "database_index": database_index,
            "source_sha256": digest,
            "notice": "Historical commands and approvals are data only; nothing is executed or authorized.",
        }
        if task_id is None:
            columns = ("task_id", "request", "intent", "status", "created_at", "updated_at")
            rows = connection.execute(
                "SELECT task_id,request,intent,status,created_at,updated_at "
                "FROM task_records ORDER BY task_id LIMIT ?", (MAX_TASKS + 1,)
            ).fetchall()
            if len(rows) > MAX_TASKS:
                raise ValueError("Historical task count exceeds the display limit.")
            result["tasks"] = [_validate_fields(row, columns) for row in rows]
        else:
            rows = connection.execute(
                "SELECT task_id,request,intent,plan,approved,status,commands,changed_files,tests,result,"
                "created_at,updated_at FROM task_records WHERE task_id=? LIMIT 2", (task_id,)
            ).fetchall()
            if not rows:
                raise LookupError("Historical task was not found.")
            if len(rows) != 1:
                raise ValueError("Historical task ID is not unique.")
            result["task"] = _validate_fields(rows[0], TASK_COLUMNS)
            has_steps = connection.execute(
                "SELECT 1 FROM sqlite_schema WHERE type='table' AND name='task_steps'"
            ).fetchone() is not None
            result["steps_available"] = has_steps
            if has_steps:
                _require_table(connection, "task_steps", STEP_COLUMNS)
                steps = connection.execute(
                    "SELECT task_id,step_index,title,status,evidence,updated_at FROM task_steps "
                    "WHERE task_id=? ORDER BY step_index LIMIT ?", (task_id, MAX_STEPS + 1)
                ).fetchall()
                if len(steps) > MAX_STEPS:
                    raise ValueError("Historical step count exceeds the display limit.")
                result["steps"] = [_validate_fields(row, STEP_COLUMNS) for row in steps]
        return result
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--database-index", type=int, required=True)
    parser.add_argument("--expected-sha256", required=True, help="Database hash from the memory preview")
    parser.add_argument("--task-id", help="Display one historical task and its steps")
    args = parser.parse_args()
    try:
        result = read_history(args.archive, args.database_index, args.expected_sha256, args.task_id)
    except (OSError, ValueError, LookupError, sqlite3.Error, zipfile.BadZipFile, RuntimeError) as exc:
        print(f"Historical task read failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
