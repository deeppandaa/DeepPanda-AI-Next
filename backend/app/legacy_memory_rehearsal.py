"""Rehearse one explicitly selected legacy ZIP database entirely in memory."""

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

from app.legacy_memory_preview import (
    archive_database_entries,
    read_archive_database,
)
from app.legacy_memory_store import (
    MAX_BATCH_RECORDS,
    LegacyMemory,
    create_legacy_tables,
    read_legacy_memory,
    store_legacy_batch,
)


def load_archive_records(
    path: Path | io.BytesIO, database_index: int, expected_sha256: str | None = None
) -> tuple[str, int, list[LegacyMemory]]:
    if not isinstance(database_index, int) or isinstance(database_index, bool) or database_index < 1:
        raise ValueError("Database index must be a positive integer.")
    if expected_sha256 is not None and not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("Expected SHA-256 must be 64 lowercase hexadecimal characters.")
    with zipfile.ZipFile(path) as archive:
        entries = archive_database_entries(archive)
        if database_index > len(entries):
            raise ValueError("Database index exceeds the candidate count.")
        data = read_archive_database(archive, entries[database_index - 1])

    digest = hashlib.sha256(data).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError("Selected database SHA-256 does not match the expected value.")
    source = sqlite3.connect(":memory:")
    try:
        source.deserialize(data)
        source.execute("PRAGMA query_only=ON")
        source.execute("PRAGMA trusted_schema=OFF")
        if source.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("Source SQLite integrity check failed.")
        if not source.execute(
            "SELECT 1 FROM sqlite_schema WHERE type='table' AND name='memories'"
        ).fetchone():
            raise ValueError("Legacy memories table is missing.")
        expected = {"id", "note", "created_at", "category", "project", "source"}
        if not expected.issubset({row[1] for row in source.execute("PRAGMA table_info(memories)")}):
            raise ValueError("Legacy memories schema is missing required columns.")
        rows = source.execute(
            "SELECT id,note,created_at,category,project,source FROM memories LIMIT ?",
            (MAX_BATCH_RECORDS + 1,),
        ).fetchall()
        if len(rows) > MAX_BATCH_RECORDS:
            raise ValueError("Source exceeds the batch record limit.")
        records = [LegacyMemory(*row) for row in rows]
        return digest, len(entries), records
    finally:
        source.close()


def rehearse_archive(path: Path, database_index: int, expected_sha256: str | None = None) -> dict[str, Any]:
    digest, candidate_count, records = load_archive_records(path, database_index, expected_sha256)
    target = sqlite3.connect(":memory:")
    try:
        target.execute("PRAGMA foreign_keys=ON")
        target.execute("BEGIN")
        create_legacy_tables(target)
        initial = store_legacy_batch(target, digest, records)
        retry = store_legacy_batch(target, digest, records)
        verified = sum(read_legacy_memory(target, digest, record.legacy_id) == record for record in records)
        if verified != len(records):
            raise ValueError("Reconstructed records do not match the source.")
        chunks = target.execute("SELECT COUNT(*) FROM legacy_memory_chunks").fetchone()[0]
        if target.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("Rehearsal SQLite integrity check failed.")
        if target.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Rehearsal foreign key check failed.")
        target.rollback()
        return {
            "mode": "in_memory_rehearsal",
            "database_index": database_index,
            "source_sha256": digest,
            "candidate_count": candidate_count,
            "records": len(records),
            "chunks": chunks,
            "verified": verified,
            "first_pass": initial,
            "retry": retry,
            "target_integrity": "ok",
            "foreign_key_violations": 0,
            "limitations": [
                "No source, production database or persistent output was written.",
                "This does not compare the production target or merge snapshots.",
                "The archive tables are not integrated with application memory.",
            ],
        }
    finally:
        target.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--database-index", type=int, required=True, help="1-based candidate number from the preview")
    parser.add_argument("--expected-sha256", help="Database SHA-256 shown in the preview")
    args = parser.parse_args()
    try:
        report = rehearse_archive(args.archive, args.database_index, args.expected_sha256)
    except (OSError, ValueError, TypeError, sqlite3.Error, zipfile.BadZipFile, RuntimeError) as exc:
        print(f"Rehearsal failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
