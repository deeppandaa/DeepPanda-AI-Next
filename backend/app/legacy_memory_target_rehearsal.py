"""Rehearse a legacy archive against an explicitly supplied SQLite snapshot in memory."""

from __future__ import annotations

import io
import sqlite3
from pathlib import Path
from typing import Any

from app.legacy_memory_rehearsal import load_archive_records
from app.legacy_memory_store import (
    LegacyMemory,
    create_legacy_tables,
    read_legacy_memory,
    store_legacy_batch,
)

MAX_TARGET_SNAPSHOT_BYTES = 64 * 1024 * 1024
ARCHIVE_TABLES = ("legacy_memory_records", "legacy_memory_chunks")
MAX_APPLICATION_MEMORIES = 10_000


def _compare_application_memories(
    connection: sqlite3.Connection, records: list[LegacyMemory]
) -> dict[str, int]:
    if not connection.execute(
        "SELECT 1 FROM sqlite_schema WHERE type='table' AND name='memories'"
    ).fetchone():
        raise ValueError("Target application memories table is missing.")
    required = {"content", "created_at", "category", "project", "source"}
    columns = {row[1] for row in connection.execute("PRAGMA table_info(memories)")}
    if not required.issubset(columns):
        raise ValueError("Target application memories schema is incomplete.")
    rows = connection.execute(
        "SELECT content,created_at,category,project,source FROM memories LIMIT ?",
        (MAX_APPLICATION_MEMORIES + 1,),
    ).fetchall()
    if len(rows) > MAX_APPLICATION_MEMORIES:
        raise ValueError("Target application memories exceed the comparison limit.")
    if any(not isinstance(value, str) for row in rows for value in row):
        raise ValueError("Target application memory fields must be text.")
    content = {row[0] for row in rows}
    fields = set(rows)
    content_matches = sum(record.note in content for record in records)
    field_matches = sum(
        (record.note, record.created_at, record.category, record.project, record.source) in fields
        for record in records
    )
    return {
        "target_records": len(rows),
        "source_records_with_equal_content": content_matches,
        "source_records_with_equal_compared_fields": field_matches,
    }


def _validate_archive_schema(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        "SELECT name, type, sql FROM sqlite_schema WHERE name IN (?, ?)", ARCHIVE_TABLES
    ).fetchall()
    if not rows:
        return
    if len(rows) != len(ARCHIVE_TABLES) or any(row[1] != "table" for row in rows):
        raise ValueError("Target legacy archive schema is incomplete.")
    reference = sqlite3.connect(":memory:")
    try:
        reference.execute("PRAGMA foreign_keys=ON")
        reference.execute("BEGIN")
        create_legacy_tables(reference)
        expected = dict(reference.execute(
            "SELECT name, sql FROM sqlite_schema WHERE type='table' AND name IN (?, ?)", ARCHIVE_TABLES
        ).fetchall())
    finally:
        reference.close()
    if {row[0]: row[2] for row in rows} != expected:
        raise ValueError("Target legacy archive schema differs from the supported schema.")
    if connection.execute(
        "SELECT 1 FROM sqlite_schema WHERE type='trigger' AND tbl_name IN (?, ?) LIMIT 1", ARCHIVE_TABLES
    ).fetchone():
        raise ValueError("Target legacy archive tables have unsupported triggers.")


def rehearse_target_snapshot(
    archive: Path, database_index: int, expected_sha256: str, target_snapshot: bytes,
    *, compare_application_memories: bool = False,
) -> dict[str, Any]:
    if not isinstance(expected_sha256, str) or not expected_sha256:
        raise ValueError("Expected source SHA-256 is required.")
    if not isinstance(target_snapshot, bytes) or not 0 < len(target_snapshot) <= MAX_TARGET_SNAPSHOT_BYTES:
        raise ValueError("Target snapshot must be SQLite bytes within the 64 MiB limit.")
    if not isinstance(compare_application_memories, bool):
        raise TypeError("Application memory comparison must be a boolean.")
    target = sqlite3.connect(":memory:")
    try:
        target.deserialize(target_snapshot)
        return rehearse_target_connection(
            archive, database_index, expected_sha256, target,
            compare_application_memories=compare_application_memories,
        )
    finally:
        target.close()


def rehearse_target_connection(
    archive: Path | io.BytesIO, database_index: int, expected_sha256: str, target: sqlite3.Connection,
    *, compare_application_memories: bool = False,
) -> dict[str, Any]:
    if not isinstance(expected_sha256, str) or not expected_sha256:
        raise ValueError("Expected source SHA-256 is required.")
    if not isinstance(compare_application_memories, bool):
        raise TypeError("Application memory comparison must be a boolean.")
    if target.in_transaction:
        raise ValueError("Target snapshot must not have an active transaction.")
    databases = target.execute("PRAGMA database_list").fetchall()
    if any(row[1] == "main" and row[2] for row in databases):
        raise ValueError("Target rehearsal requires an in-memory database.")
    digest, _, records = load_archive_records(archive, database_index, expected_sha256)
    try:
        target.execute("PRAGMA trusted_schema=OFF")
        target.execute("PRAGMA foreign_keys=ON")
        if target.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("Target snapshot integrity check failed.")
        if target.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Target snapshot foreign key check failed.")
        _validate_archive_schema(target)
        target.execute("BEGIN")
        create_legacy_tables(target)
        initial_count = target.execute("SELECT COUNT(*) FROM legacy_memory_records").fetchone()[0]
        outcome = store_legacy_batch(target, digest, records)
        verified = sum(read_legacy_memory(target, digest, record.legacy_id) == record for record in records)
        if verified != len(records):
            raise ValueError("Stored source records failed verification.")
        if target.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("Rehearsal target integrity check failed.")
        if target.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Rehearsal target foreign key check failed.")
        application_comparison = (
            _compare_application_memories(target, records) if compare_application_memories else None
        )
        result: dict[str, Any] = {
            "mode": "in_memory_target_snapshot_rehearsal",
            "database_index": database_index,
            "source_sha256": digest,
            "source_records": len(records),
            "existing_archive_records": initial_count,
            "would_store": outcome["stored"],
            "identical_existing": outcome["duplicates"],
            "verified": verified,
            "limitations": [
                "Only the supplied target snapshot was examined; the current live target may differ.",
                "Existing application memories are not modified.",
                "Content comparisons omit title and ID, do not normalize values, and do not establish identity.",
                "No data was persisted, imported, or merged across source snapshots.",
                "A successful rehearsal does not authorize or guarantee a future import.",
            ],
        }
        if application_comparison is not None:
            result["application_memory_comparison"] = application_comparison
        else:
            result["limitations"].append("Existing application memories were not compared.")
        return result
    finally:
        if target.in_transaction:
            target.rollback()
