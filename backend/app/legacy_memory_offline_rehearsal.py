"""Rehearse against a quiescent, standalone SQLite target without importing data."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import zipfile
from pathlib import Path
from typing import Any

from app.legacy_memory_snapshot import snapshot_connection
from app.legacy_memory_target_rehearsal import rehearse_target_connection


def _require_no_sidecars(path: Path) -> None:
    if any(Path(f"{path}{suffix}").exists() for suffix in ("-wal", "-shm", "-journal")):
        raise ValueError("Target has SQLite sidecars; use a quiescent, checkpointed standalone database.")


def _require_rollback_mode(path: Path) -> None:
    with path.open("rb") as file:
        header = file.read(20)
    if len(header) < 20 or header[:16] != b"SQLite format 3\x00":
        raise ValueError("Target is not a valid SQLite database.")
    if header[18:20] != b"\x01\x01":
        raise ValueError("Target must use rollback journal mode, not WAL.")


def rehearse_offline_target(
    archive: Path, database_index: int, expected_sha256: str, target_path: Path, *, target_stopped: bool
) -> dict[str, Any]:
    if target_stopped is not True:
        raise ValueError("Explicit confirmation that all target writers are stopped is required.")
    target_path = target_path.resolve(strict=True)
    if not target_path.is_file():
        raise ValueError("Target must be an existing SQLite file.")
    _require_no_sidecars(target_path)
    _require_rollback_mode(target_path)
    connection = sqlite3.connect(f"{target_path.as_uri()}?mode=ro", uri=True, timeout=1)
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
        with snapshot_connection(connection) as snapshot:
            _require_no_sidecars(target_path)
            report = rehearse_target_connection(
                archive, database_index, expected_sha256, snapshot, compare_application_memories=True
            )
        _require_no_sidecars(target_path)
    finally:
        connection.close()
    report["mode"] = "offline_read_only_target_rehearsal"
    report["limitations"].append(
        "Quiescence is caller-confirmed, not enforced; other writers can invalidate this report."
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--database-index", type=int, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument(
        "--confirm-target-stopped", action="store_true",
        help="Confirm all target writers are stopped and will remain stopped for the entire rehearsal.",
    )
    args = parser.parse_args()
    try:
        report = rehearse_offline_target(
            args.archive, args.database_index, args.expected_sha256, args.target,
            target_stopped=args.confirm_target_stopped,
        )
    except (OSError, ValueError, TypeError, sqlite3.Error, zipfile.BadZipFile, RuntimeError) as exc:
        print(f"Offline target rehearsal failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
