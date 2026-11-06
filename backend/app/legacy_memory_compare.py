"""Compare two explicitly selected legacy snapshots without writing or merging them."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import zipfile
from pathlib import Path
from typing import Any

from app.legacy_memory_rehearsal import load_archive_records
from app.legacy_memory_store import (
    LegacyMemory,
    create_legacy_tables,
    store_legacy_batch,
)


def compare_snapshots(
    archive: Path, left_index: int, left_sha256: str, right_index: int, right_sha256: str
) -> dict[str, Any]:
    if not isinstance(left_sha256, str) or not isinstance(right_sha256, str):
        raise TypeError("Both expected SHA-256 values are required.")
    if left_index == right_index:
        raise ValueError("Select two different database candidates.")
    left_digest, left_count, left = load_archive_records(archive, left_index, left_sha256)
    right_digest, right_count, right = load_archive_records(archive, right_index, right_sha256)
    if left_count != right_count:
        raise ValueError("Archive candidate count changed during comparison.")
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("BEGIN")
        create_legacy_tables(connection)
        store_legacy_batch(connection, left_digest, left)
        store_legacy_batch(connection, right_digest, right)
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Comparison foreign key check failed.")
        if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("Comparison integrity check failed.")
    finally:
        connection.close()

    left_by_id: dict[int, LegacyMemory] = {record.legacy_id: record for record in left}
    right_by_id: dict[int, LegacyMemory] = {record.legacy_id: record for record in right}
    common = left_by_id.keys() & right_by_id.keys()
    equal = sum(left_by_id[key] == right_by_id[key] for key in common)
    return {
        "mode": "read_only_snapshot_comparison",
        "left": {"database_index": left_index, "source_sha256": left_digest, "records": len(left)},
        "right": {"database_index": right_index, "source_sha256": right_digest, "records": len(right)},
        "same_id_identical": equal,
        "same_id_different": len(common) - equal,
        "left_only_id": len(left_by_id.keys() - right_by_id.keys()),
        "right_only_id": len(right_by_id.keys() - left_by_id.keys()),
        "limitations": [
            "No records are merged, imported or written to a persistent target.",
            "Equality includes ID, full note, timestamp, category, project and source.",
            "Records with different IDs are not treated as duplicates.",
            "No production target was examined; source hashes do not prove authenticity.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--left-index", type=int, required=True)
    parser.add_argument("--left-sha256", required=True)
    parser.add_argument("--right-index", type=int, required=True)
    parser.add_argument("--right-sha256", required=True)
    args = parser.parse_args()
    try:
        report = compare_snapshots(
            args.archive, args.left_index, args.left_sha256, args.right_index, args.right_sha256
        )
    except (OSError, ValueError, TypeError, sqlite3.Error, zipfile.BadZipFile, RuntimeError) as exc:
        print(f"Snapshot comparison failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
