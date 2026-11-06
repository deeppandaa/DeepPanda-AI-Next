"""Create a bounded, transient SQLite snapshot using a caller-supplied connection."""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Generator
from contextlib import contextmanager

from app.legacy_memory_target_rehearsal import MAX_TARGET_SNAPSHOT_BYTES

SNAPSHOT_TIMEOUT_SECONDS = 15
BACKUP_PAGES = 16


@contextmanager
def snapshot_connection(source: sqlite3.Connection) -> Generator[sqlite3.Connection, None, None]:
    if source.in_transaction:
        raise ValueError("Snapshot requires a source connection without an active transaction.")
    started = time.monotonic()
    destination = sqlite3.connect(":memory:")
    try:
        page_size = source.execute("PRAGMA main.page_size").fetchone()[0]
        page_count = source.execute("PRAGMA main.page_count").fetchone()[0]
        if page_count * page_size > MAX_TARGET_SNAPSHOT_BYTES:
            raise ValueError("Target snapshot exceeds the 64 MiB limit.")
        if time.monotonic() - started > SNAPSHOT_TIMEOUT_SECONDS:
            raise TimeoutError("Target snapshot exceeded the backup time limit.")

        def progress(_status: int, _remaining: int, total: int) -> None:
            if time.monotonic() - started > SNAPSHOT_TIMEOUT_SECONDS:
                raise TimeoutError("Target snapshot exceeded the backup time limit.")
            if total * page_size > MAX_TARGET_SNAPSHOT_BYTES:
                raise ValueError("Target snapshot exceeds the 64 MiB limit.")

        source.backup(destination, pages=BACKUP_PAGES, progress=progress, name="main", sleep=0.05)
        destination.execute("PRAGMA temp_store=MEMORY")
        final_size = (
            destination.execute("PRAGMA main.page_count").fetchone()[0]
            * destination.execute("PRAGMA main.page_size").fetchone()[0]
        )
        if not 0 < final_size <= MAX_TARGET_SNAPSHOT_BYTES:
            raise ValueError("Target snapshot exceeds the 64 MiB limit.")
        yield destination
    finally:
        destination.close()
