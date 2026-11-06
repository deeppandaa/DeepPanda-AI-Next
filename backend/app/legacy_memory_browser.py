"""Read-only browsing of explicitly imported, isolated legacy memory records."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.legacy_memory_store import MAX_BATCH_RECORDS, read_legacy_memory
from app.legacy_memory_target_rehearsal import _validate_archive_schema

MAX_RECORD_CHARS = 1_000_000
MAX_SCAN_BYTES = 64 * 1024 * 1024
MAX_PAGE = 25


class LegacyMemoryNotFound(LookupError):
    pass


class LegacyMemoryUnavailable(RuntimeError):
    pass


def browse_legacy_memory(path: Path, action: str, payload: dict[str, Any]) -> dict[str, Any]:
    if action not in {"legacy_list", "legacy_get"}:
        raise ValueError("Invalid legacy memory action.")
    query = ""
    offset = 0
    digest = ""
    legacy_id = 0
    if action == "legacy_list":
        query = payload.get("query", "")
        offset = payload.get("offset", 0)
        if not isinstance(query, str) or len(query) > 200:
            raise ValueError("Search query must be text of at most 200 characters.")
        if type(offset) is not int or not 0 <= offset <= MAX_BATCH_RECORDS:
            raise ValueError("Invalid result offset.")
    else:
        digest = payload.get("source_digest")
        legacy_id = payload.get("legacy_id")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("Invalid source digest.")
        if type(legacy_id) is not int or abs(legacy_id) > 2**53 - 1:
            raise TypeError("Invalid legacy memory ID.")
    try:
        connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=5)
        try:
            connection.execute("PRAGMA query_only=ON")
            connection.execute("PRAGMA trusted_schema=OFF")
            connection.execute("BEGIN")
            _validate_archive_schema(connection)
            existing = connection.execute(
                "SELECT COUNT(*) FROM sqlite_schema WHERE type='table' AND name='legacy_memory_records'"
            ).fetchone()[0]
            if not existing:
                if action == "legacy_get":
                    raise LegacyMemoryNotFound("Legacy memory was not found.")
                return {"status": "not_imported", "records": [], "next_offset": None}

            scanned_bytes = 0

            def read_record(source: str, record_id: int) -> dict[str, Any]:
                nonlocal scanned_bytes
                if type(record_id) is not int or abs(record_id) > 2**53 - 1:
                    raise LegacyMemoryUnavailable("Legacy memory ID exceeds the browser limit.")
                lengths = connection.execute(
                    "SELECT COALESCE(SUM(length(CAST(content AS BLOB))), 0) FROM legacy_memory_chunks "
                    "WHERE source_digest=? AND legacy_id=?", (source, record_id),
                ).fetchone()[0]
                if lengths > MAX_RECORD_CHARS * 4:
                    raise LegacyMemoryUnavailable("Legacy memory exceeds the display limit.")
                scanned_bytes += lengths
                if scanned_bytes > MAX_SCAN_BYTES:
                    raise LegacyMemoryUnavailable("Legacy memory archive exceeds the scanning limit.")
                try:
                    record = read_legacy_memory(connection, source, record_id)
                except LookupError as exc:
                    raise LegacyMemoryNotFound("Legacy memory was not found.") from exc
                if len(record.note) > MAX_RECORD_CHARS:
                    raise LegacyMemoryUnavailable("Legacy memory exceeds the display limit.")
                return {"source_digest": source, **asdict(record)}

            if action == "legacy_get":
                return {"status": "available", "record": read_record(digest, legacy_id)}

            identities = connection.execute(
                "SELECT source_digest, legacy_id FROM legacy_memory_records "
                "ORDER BY source_digest, legacy_id LIMIT ?", (MAX_BATCH_RECORDS + 1,),
            ).fetchall()
            if len(identities) > MAX_BATCH_RECORDS:
                raise LegacyMemoryUnavailable("Legacy memory archive exceeds the browsing limit.")
            records = []
            matched = 0
            for source, record_id in identities:
                record = read_record(source, record_id)
                if query.casefold() not in record["note"].casefold():
                    continue
                if offset <= matched < offset + MAX_PAGE:
                    records.append({**record, "note": record["note"][:300]})
                matched += 1
            return {
                "status": "available", "records": records,
                "next_offset": offset + MAX_PAGE if matched > offset + MAX_PAGE else None,
            }
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise LegacyMemoryUnavailable("Legacy memory database is unavailable or invalid.") from exc
