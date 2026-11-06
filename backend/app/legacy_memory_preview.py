"""Read-only, aggregate preview of legacy SQLite memories inside a ZIP archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MAX_DATABASE_BYTES = 32 * 1024 * 1024
MAX_DATABASES = 8
CHUNK_SIZE = 10_000
DATABASE_SUFFIXES = (".db", ".sqlite", ".sqlite3")


@dataclass(frozen=True)
class PreviewChunk:
    legacy_id: int
    index: int
    count: int
    created_at: str
    content: str


def split_preview(legacy_id: int, note: str, created_at: str) -> tuple[PreviewChunk, ...]:
    if not isinstance(legacy_id, int) or isinstance(legacy_id, bool):
        raise TypeError("Legacy memory ID must be an integer.")
    if not isinstance(note, str) or not note.strip():
        raise ValueError("Legacy memory note must be nonempty text.")
    if not isinstance(created_at, str) or not created_at.strip():
        raise ValueError("Legacy memory timestamp must be nonempty text.")
    count = (len(note) + CHUNK_SIZE - 1) // CHUNK_SIZE
    return tuple(
        PreviewChunk(legacy_id, index, count, created_at, note[offset : offset + CHUNK_SIZE])
        for index, offset in enumerate(range(0, len(note), CHUNK_SIZE))
    )


def reassemble_preview(chunks: tuple[PreviewChunk, ...]) -> tuple[str, str]:
    if not chunks:
        raise ValueError("Memory chunks are missing.")
    first = chunks[0]
    if first.count != len(chunks):
        raise ValueError("Memory chunk count does not match.")
    for index, chunk in enumerate(chunks):
        if (
            chunk.legacy_id != first.legacy_id
            or chunk.index != index
            or chunk.count != first.count
            or chunk.created_at != first.created_at
            or not 1 <= len(chunk.content) <= CHUNK_SIZE
        ):
            raise ValueError("Memory chunk sequence is inconsistent.")
    return "".join(chunk.content for chunk in chunks), first.created_at


def _fingerprint(row: tuple[Any, ...]) -> bytes:
    encoded = repr(row).encode("utf-8")
    return hashlib.sha256(encoded).digest()


def preview_database(data: bytes) -> tuple[dict[str, int], set[bytes]]:
    if not data or len(data) > MAX_DATABASE_BYTES:
        raise ValueError("Database size is outside the preview limit.")
    connection = sqlite3.connect(":memory:")
    try:
        connection.deserialize(data)
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
        if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("SQLite integrity check failed.")
        expected = {"id", "note", "created_at", "category", "project", "source"}
        columns = {row[1] for row in connection.execute("PRAGMA table_info(memories)")}
        if not expected.issubset(columns):
            raise ValueError("Legacy memories schema is missing required columns.")

        report = {
            "memories": 0,
            "long_notes": 0,
            "proposed_chunks": 0,
            "invalid_notes": 0,
            "invalid_metadata_rows": 0,
            "chunks_changed_by_current_import_strip": 0,
            "chunks_rejected_by_current_import": 0,
            "missing_or_nontext_timestamps": 0,
            "invalid_or_duplicate_ids": 0,
            "roundtrip_verified": 0,
        }
        fingerprints: set[bytes] = set()
        ids: set[int] = set()
        for legacy_id, note, created_at, category, project, source in connection.execute(
            "SELECT id,note,created_at,category,project,source FROM memories"
        ):
            row = (note, created_at, category, project, source)
            report["memories"] += 1
            fingerprints.add(_fingerprint(row))
            valid_id = isinstance(legacy_id, int) and not isinstance(legacy_id, bool) and legacy_id not in ids
            if valid_id:
                ids.add(legacy_id)
            else:
                report["invalid_or_duplicate_ids"] += 1
            if not isinstance(created_at, str) or not created_at.strip():
                report["missing_or_nontext_timestamps"] += 1
            metadata = ((category, 80), (project, 200), (source, 200))
            if any(
                value is not None
                and value != ""
                and (not isinstance(value, str) or not value.strip() or len(value) > limit)
                for value, limit in metadata
            ):
                report["invalid_metadata_rows"] += 1
            if not isinstance(note, str) or not note.strip():
                report["invalid_notes"] += 1
                continue
            chunks = [note[offset : offset + CHUNK_SIZE] for offset in range(0, len(note), CHUNK_SIZE)]
            report["long_notes"] += len(chunks) > 1
            report["proposed_chunks"] += len(chunks)
            report["chunks_changed_by_current_import_strip"] += sum(chunk != chunk.strip() for chunk in chunks)
            report["chunks_rejected_by_current_import"] += sum(not chunk.strip() for chunk in chunks)
            if valid_id and isinstance(created_at, str) and created_at.strip():
                linked = split_preview(legacy_id, note, created_at)
                if reassemble_preview(linked) != (note, created_at):
                    raise ValueError("Memory reconstruction verification failed.")
                report["roundtrip_verified"] += 1
        return report, fingerprints
    finally:
        connection.close()


def archive_database_entries(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    entries = [
        entry for entry in archive.infolist()
        if not entry.is_dir() and entry.filename.lower().endswith(DATABASE_SUFFIXES)
    ]
    if not 1 <= len(entries) <= MAX_DATABASES:
        raise ValueError("Archive must contain between one and eight SQLite candidates.")
    if len({entry.filename for entry in entries}) != len(entries):
        raise ValueError("Archive contains duplicate database entry names.")
    return entries


def read_archive_database(archive: zipfile.ZipFile, entry: zipfile.ZipInfo) -> bytes:
    if entry.flag_bits & 1 or not 0 < entry.file_size <= MAX_DATABASE_BYTES:
        raise ValueError("Encrypted or oversized database entry cannot be read.")
    names = {item.filename for item in archive.infolist() if not item.is_dir()}
    if any(entry.filename + suffix in names for suffix in ("-wal", "-journal")):
        raise ValueError("Database has a WAL or journal sidecar; standalone inspection is unsafe.")
    return archive.read(entry)


def preview_archive(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        entries = archive_database_entries(archive)
        reports: list[dict[str, Any]] = []
        fingerprints: list[set[bytes]] = []
        for entry in entries:
            data = read_archive_database(archive, entry)
            report, hashes = preview_database(data)
            reports.append({"source_sha256": hashlib.sha256(data).hexdigest(), **report})
            fingerprints.append(hashes)
    overlaps = [
        {"database_a": left + 1, "database_b": right + 1, "matching_field_sets": len(fingerprints[left] & fingerprints[right])}
        for left in range(len(fingerprints))
        for right in range(left + 1, len(fingerprints))
    ]
    return {
        "mode": "read_only_preview",
        "database_reports": reports,
        "overlaps": overlaps,
        "limitations": [
            "No records are migrated and no conversion output is produced.",
            "In-memory links are scoped to one database; persistence and timestamp format are not validated.",
            "Title creation and target schema compatibility are not validated.",
            "Current memory import strips whitespace and replaces timestamps.",
            "Overlap compares note, timestamp, category, project and source only.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="Local ZIP archive containing legacy SQLite databases")
    args = parser.parse_args()
    try:
        report = preview_archive(args.archive)
    except ValueError as exc:
        print(f"Preview failed: {exc}", file=sys.stderr)
        return 1
    except (OSError, sqlite3.Error, zipfile.BadZipFile, RuntimeError) as exc:
        print(f"Preview failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
