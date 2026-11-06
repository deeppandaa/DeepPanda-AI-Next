"""Storage primitives for a future, explicitly approved legacy memory import.

These functions do not open databases, commit transactions, or expose an API.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

from app.legacy_memory_preview import PreviewChunk, reassemble_preview, split_preview

MAX_BATCH_RECORDS = 5_000


@dataclass(frozen=True)
class LegacyMemory:
    legacy_id: int
    note: str
    created_at: str
    category: str | None
    project: str | None
    source: str | None


def create_legacy_tables(connection: sqlite3.Connection) -> None:
    """Create isolated archive tables inside the caller's transaction."""
    if not connection.in_transaction:
        raise ValueError("An explicit transaction is required.")
    if not connection.execute("PRAGMA foreign_keys").fetchone()[0]:
        raise ValueError("Foreign key enforcement must be enabled.")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS legacy_memory_records (
            source_digest TEXT NOT NULL,
            legacy_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            category TEXT,
            project TEXT,
            source TEXT,
            note_digest TEXT NOT NULL,
            chunk_count INTEGER NOT NULL CHECK(chunk_count > 0),
            PRIMARY KEY(source_digest, legacy_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS legacy_memory_chunks (
            source_digest TEXT NOT NULL,
            legacy_id INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL CHECK(chunk_index >= 0),
            content TEXT NOT NULL,
            PRIMARY KEY(source_digest, legacy_id, chunk_index),
            FOREIGN KEY(source_digest, legacy_id)
                REFERENCES legacy_memory_records(source_digest, legacy_id) ON DELETE CASCADE
        )
        """
    )


def _validate_source(source_digest: str) -> None:
    if not isinstance(source_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", source_digest):
        raise ValueError("Source digest must be a lowercase SHA-256 digest.")


def _note_digest(note: str) -> str:
    return hashlib.sha256(note.encode("utf-8")).hexdigest()


def read_legacy_memory(connection: sqlite3.Connection, source_digest: str, legacy_id: int) -> LegacyMemory:
    _validate_source(source_digest)
    if not isinstance(legacy_id, int) or isinstance(legacy_id, bool):
        raise TypeError("Legacy memory ID must be an integer.")
    row = connection.execute(
        "SELECT created_at,category,project,source,note_digest,chunk_count "
        "FROM legacy_memory_records WHERE source_digest=? AND legacy_id=?",
        (source_digest, legacy_id),
    ).fetchone()
    if row is None:
        raise LookupError("Legacy memory was not found.")
    created_at, category, project, source, expected_digest, count = row
    parts = connection.execute(
        "SELECT chunk_index,content FROM legacy_memory_chunks "
        "WHERE source_digest=? AND legacy_id=? ORDER BY chunk_index",
        (source_digest, legacy_id),
    ).fetchall()
    chunks = tuple(PreviewChunk(legacy_id, index, count, created_at, content) for index, content in parts)
    note, timestamp = reassemble_preview(chunks)
    if _note_digest(note) != expected_digest:
        raise ValueError("Legacy memory content checksum does not match.")
    return LegacyMemory(legacy_id, note, timestamp, category, project, source)


def store_legacy_memory(connection: sqlite3.Connection, source_digest: str, record: LegacyMemory) -> str:
    """Store one record atomically; duplicate identity must have identical data."""
    if not connection.in_transaction:
        raise ValueError("An explicit transaction is required.")
    if not connection.execute("PRAGMA foreign_keys").fetchone()[0]:
        raise ValueError("Foreign key enforcement must be enabled.")
    _validate_source(source_digest)
    for value in (record.category, record.project, record.source):
        if value is not None and not isinstance(value, str):
            raise TypeError("Legacy metadata must be text or null.")
    chunks = split_preview(record.legacy_id, record.note, record.created_at)
    existing = connection.execute(
        "SELECT 1 FROM legacy_memory_records WHERE source_digest=? AND legacy_id=?",
        (source_digest, record.legacy_id),
    ).fetchone()
    if existing is not None:
        if read_legacy_memory(connection, source_digest, record.legacy_id) != record:
            raise ValueError("Legacy memory identity conflicts with existing data.")
        return "duplicate"
    connection.execute("SAVEPOINT legacy_memory_record")
    try:
        connection.execute(
            "INSERT INTO legacy_memory_records VALUES (?,?,?,?,?,?,?,?)",
            (source_digest, record.legacy_id, record.created_at, record.category, record.project, record.source,
             _note_digest(record.note), len(chunks)),
        )
        connection.executemany(
            "INSERT INTO legacy_memory_chunks VALUES (?,?,?,?)",
            ((source_digest, record.legacy_id, chunk.index, chunk.content) for chunk in chunks),
        )
        if read_legacy_memory(connection, source_digest, record.legacy_id) != record:
            raise ValueError("Stored legacy memory failed verification.")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK TO legacy_memory_record")
            connection.execute("RELEASE legacy_memory_record")
        raise
    connection.execute("RELEASE legacy_memory_record")
    return "stored"


def store_legacy_batch(
    connection: sqlite3.Connection, source_digest: str, records: Sequence[LegacyMemory]
) -> dict[str, int]:
    """Stage a bounded batch atomically within the caller's existing transaction."""
    if not connection.in_transaction:
        raise ValueError("An explicit transaction is required.")
    if not connection.execute("PRAGMA foreign_keys").fetchone()[0]:
        raise ValueError("Foreign key enforcement must be enabled.")
    _validate_source(source_digest)
    if len(records) > MAX_BATCH_RECORDS:
        raise ValueError("Legacy batch exceeds the record limit.")
    if any(not isinstance(record, LegacyMemory) for record in records):
        raise TypeError("All batch records must be LegacyMemory instances.")
    ids = [record.legacy_id for record in records]
    if any(not isinstance(value, int) or isinstance(value, bool) for value in ids):
        raise TypeError("Legacy memory IDs must be integers.")
    if len(set(ids)) != len(ids):
        raise ValueError("Legacy batch contains duplicate IDs.")
    stored = 0
    duplicates = 0
    connection.execute("SAVEPOINT legacy_memory_batch")
    try:
        for record in records:
            result = store_legacy_memory(connection, source_digest, record)
            if result == "stored":
                stored += 1
            else:
                duplicates += 1
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK TO legacy_memory_batch")
            connection.execute("RELEASE legacy_memory_batch")
        raise
    connection.execute("RELEASE legacy_memory_batch")
    return {"stored": stored, "duplicates": duplicates}
