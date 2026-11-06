"""Explicit offline import into a stopped SQLite database with a separate backup."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sqlite3
import sys
import zipfile
from pathlib import Path
from typing import Any

from app.legacy_memory_offline_rehearsal import (
    _require_no_sidecars,
    _require_rollback_mode,
)
from app.legacy_memory_rehearsal import load_archive_records
from app.legacy_memory_stage import stage_legacy_archive
from app.legacy_memory_store import read_legacy_memory
from app.legacy_memory_target_rehearsal import MAX_TARGET_SNAPSHOT_BYTES

MAX_ARCHIVE_BYTES = 64 * 1024 * 1024


class OfflineImportError(RuntimeError):
    """Import failed; its message states whether commit might have occurred."""


def _check_database(connection: sqlite3.Connection) -> None:
    if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
        raise ValueError("Database integrity check failed.")
    if connection.execute("PRAGMA foreign_key_check").fetchall():
        raise ValueError("Database foreign key check failed.")


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _create_backup(connection: sqlite3.Connection, backup: Path) -> str:
    page_size = connection.execute("PRAGMA main.page_size").fetchone()[0]
    page_count = connection.execute("PRAGMA main.page_count").fetchone()[0]
    if not 0 < page_size * page_count <= MAX_TARGET_SNAPSHOT_BYTES:
        raise ValueError("Target exceeds the 64 MiB backup limit or is empty.")
    snapshot = connection.serialize(name="main")
    if not 0 < len(snapshot) <= MAX_TARGET_SNAPSHOT_BYTES:
        raise ValueError("Target exceeds the 64 MiB backup limit or is empty.")
    digest = hashlib.sha256(snapshot).hexdigest()
    descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write(snapshot)
        output.flush()
        os.fsync(output.fileno())
    if _hash_file(backup) != digest:
        raise ValueError("Backup file verification failed.")
    _require_no_sidecars(backup)
    connection = sqlite3.connect(f"{backup.resolve().as_uri()}?mode=ro", uri=True, timeout=1)
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
        _check_database(connection)
        restored = sqlite3.connect(":memory:")
        try:
            connection.backup(restored)
            _check_database(restored)
        finally:
            restored.close()
    finally:
        connection.close()
    return digest


def import_offline(
    archive_path: Path,
    database_index: int,
    expected_sha256: str,
    expected_records: int,
    target_path: Path,
    backup_path: Path,
    *,
    target_stopped: bool,
    approved: bool,
) -> dict[str, Any]:
    if target_stopped is not True or approved is not True:
        raise ValueError("Explicit confirmation of stopped writers and import approval is required.")
    if target_path.is_symlink() or backup_path.is_symlink():
        raise ValueError("Target and backup must not be symbolic links.")
    target = target_path.resolve(strict=True)
    if not target.is_file():
        raise ValueError("Target must be an existing SQLite file.")
    backup = backup_path.resolve()
    if not backup.parent.is_dir():
        raise ValueError("Backup parent directory must already exist.")
    if backup.exists():
        raise FileExistsError("Backup already exists; choose a new path.")
    if backup in {Path(f"{target}{suffix}") for suffix in ("-wal", "-shm", "-journal")}:
        raise ValueError("Backup path must not be a target SQLite sidecar.")
    _require_no_sidecars(backup)
    with archive_path.open("rb") as source:
        archive_bytes = source.read(MAX_ARCHIVE_BYTES + 1)
    if not archive_bytes or len(archive_bytes) > MAX_ARCHIVE_BYTES:
        raise ValueError("Archive exceeds the 64 MiB limit or is empty.")
    archive = io.BytesIO(archive_bytes)
    if not isinstance(expected_sha256, str) or not expected_sha256:
        raise ValueError("Expected source SHA-256 is required.")
    digest, _, records = load_archive_records(archive, database_index, expected_sha256)
    if type(expected_records) is not int or expected_records < 1 or len(records) != expected_records:
        raise ValueError("Source record count does not match the expected count.")
    _require_no_sidecars(target)
    _require_rollback_mode(target)
    connection = sqlite3.connect(f"{target.as_uri()}?mode=rw", uri=True, timeout=1)
    commit_attempted = False
    try:
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("BEGIN EXCLUSIVE")
        _require_no_sidecars(target)
        if connection.execute("PRAGMA journal_mode").fetchone()[0].lower() != "delete":
            raise ValueError("Target must use DELETE rollback journal mode.")
        _check_database(connection)
        backup_digest = _create_backup(connection, backup)
        _require_no_sidecars(target)
        if _hash_file(backup) != backup_digest:
            raise ValueError("Backup changed during verification.")
        outcome = stage_legacy_archive(connection, archive, database_index, expected_sha256, expected_records)
        commit_attempted = True
        connection.commit()
    except Exception as exc:
        if connection.in_transaction:
            try:
                connection.rollback()
            except sqlite3.Error as rollback_error:
                raise OfflineImportError(
                    f"Rollback failed; target state must be inspected. Backup may remain at {backup}. "
                    f"Original error: {type(exc).__name__}: {exc}; "
                    f"rollback error: {type(rollback_error).__name__}: {rollback_error}"
                ) from exc
        state = "Commit was attempted; target state must be inspected" if commit_attempted else "No commit was attempted"
        raise OfflineImportError(f"{state}. Backup may remain at {backup}. {type(exc).__name__}: {exc}") from exc
    finally:
        connection.close()

    try:
        check = sqlite3.connect(f"{target.as_uri()}?mode=ro", uri=True, timeout=1)
        try:
            check.execute("PRAGMA query_only=ON")
            check.execute("PRAGMA trusted_schema=OFF")
            check.execute("BEGIN")
            _check_database(check)
            if any(read_legacy_memory(check, digest, record.legacy_id) != record for record in records):
                raise ValueError("Committed records do not match the selected source.")
        finally:
            check.close()
    except Exception as exc:
        raise OfflineImportError(
            f"Commit succeeded but post-commit verification failed; inspect target and backup at {backup}. "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    return {
        "mode": "offline_import",
        "source_sha256": digest,
        "source_records": len(records),
        "stored": outcome["stored"],
        "duplicates": outcome["duplicates"],
        "verified_after_commit": len(records),
        "backup_path": str(backup),
        "backup_sha256": backup_digest,
        "limitations": [
            "Stopped writers and backup access restrictions must be ensured by the operator.",
            "A pre-import backup does not contain changes made after it was created.",
            "No automatic restoration or service restart was performed.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--database-index", type=int, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--expected-records", type=int, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--confirm-all-writers-stopped", action="store_true")
    parser.add_argument("--approve-import", action="store_true")
    args = parser.parse_args()
    try:
        report = import_offline(
            args.archive, args.database_index, args.expected_sha256, args.expected_records,
            args.target, args.backup,
            target_stopped=args.confirm_all_writers_stopped, approved=args.approve_import,
        )
    except (OSError, ValueError, TypeError, sqlite3.Error, zipfile.BadZipFile, RuntimeError) as exc:
        print(f"Offline import failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
