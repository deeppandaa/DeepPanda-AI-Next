"""Stage a selected archive in a caller-owned transaction without committing it."""

from __future__ import annotations

import io
import re
import sqlite3
from pathlib import Path

from app.legacy_memory_browser import MAX_RECORD_CHARS, MAX_SCAN_BYTES
from app.legacy_memory_rehearsal import load_archive_records
from app.legacy_memory_store import (
    MAX_BATCH_RECORDS,
    create_legacy_tables,
    read_legacy_memory,
    store_legacy_batch,
)
from app.legacy_memory_target_rehearsal import _validate_archive_schema


def stage_legacy_archive(
    connection: sqlite3.Connection,
    archive: Path | io.BytesIO,
    database_index: int,
    expected_sha256: str,
    expected_records: int,
) -> dict[str, int | str]:
    """Stage and verify the batch; the caller owns the transaction and its outcome."""
    if not connection.in_transaction:
        raise ValueError("An existing target transaction is required.")
    if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        raise ValueError("Foreign key enforcement must be enabled.")
    if connection.execute("PRAGMA trusted_schema").fetchone()[0] != 0:
        raise ValueError("Trusted schema must be disabled.")
    if any(row[1] not in {"main", "temp"} for row in connection.execute("PRAGMA database_list")):
        raise ValueError("Attached databases are not supported.")
    if connection.execute(
        "SELECT 1 FROM sqlite_temp_schema WHERE name IN (?, ?) "
        "OR (type='trigger' AND tbl_name IN (?, ?)) LIMIT 1",
        ("legacy_memory_records", "legacy_memory_chunks", "legacy_memory_records", "legacy_memory_chunks"),
    ).fetchone():
        raise ValueError("Temporary objects cannot shadow legacy archive tables.")
    if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("Expected source SHA-256 must be 64 lowercase hexadecimal characters.")
    if type(expected_records) is not int or not 1 <= expected_records <= MAX_BATCH_RECORDS:
        raise ValueError("Expected source record count is invalid.")

    digest, _, records = load_archive_records(archive, database_index, expected_sha256)
    if len(records) != expected_records:
        raise ValueError("Source record count does not match the expected count.")
    if any(
        type(record.legacy_id) is not int or abs(record.legacy_id) > 2**53 - 1
        or not isinstance(record.note, str) or len(record.note) > MAX_RECORD_CHARS
        for record in records
    ):
        raise ValueError("Source records exceed the legacy browser limits.")
    if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
        raise ValueError("Target integrity check failed.")
    if connection.execute("PRAGMA foreign_key_check").fetchall():
        raise ValueError("Target foreign key check failed.")
    _validate_archive_schema(connection)

    connection.execute("SAVEPOINT legacy_archive_stage")
    try:
        create_legacy_tables(connection)
        outcome = store_legacy_batch(connection, digest, records)
        if any(read_legacy_memory(connection, digest, record.legacy_id) != record for record in records):
            raise ValueError("Staged source records failed verification.")
        count = connection.execute("SELECT COUNT(*) FROM legacy_memory_records").fetchone()[0]
        size = connection.execute(
            "SELECT COALESCE(SUM(length(CAST(content AS BLOB))), 0) FROM legacy_memory_chunks"
        ).fetchone()[0]
        if count > MAX_BATCH_RECORDS or size > MAX_SCAN_BYTES:
            raise ValueError("Staged archive exceeds the legacy browser limits.")
        if connection.execute(
            "SELECT 1 FROM legacy_memory_records WHERE legacy_id NOT BETWEEN ? AND ? LIMIT 1",
            (-(2**53 - 1), 2**53 - 1),
        ).fetchone():
            raise ValueError("Staged archive contains an ID outside the legacy browser limits.")
        for source, record_id in connection.execute(
            "SELECT source_digest, legacy_id FROM legacy_memory_records"
        ):
            record = read_legacy_memory(connection, source, record_id)
            if (
                not isinstance(record.note, str) or len(record.note) > MAX_RECORD_CHARS
                or not isinstance(record.created_at, str)
                or any(value is not None and not isinstance(value, str)
                       for value in (record.category, record.project, record.source))
            ):
                raise ValueError("Staged archive contains a record outside the legacy browser limits.")
        if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("Staged target integrity check failed.")
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Staged target foreign key check failed.")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK TO legacy_archive_stage")
            connection.execute("RELEASE legacy_archive_stage")
        raise
    connection.execute("RELEASE legacy_archive_stage")
    return {
        "source_sha256": digest,
        "source_records": len(records),
        "stored": outcome["stored"],
        "duplicates": outcome["duplicates"],
        "verified": len(records),
    }
