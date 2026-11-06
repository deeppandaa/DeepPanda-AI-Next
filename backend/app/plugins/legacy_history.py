from __future__ import annotations

import hashlib
import io
import logging
import zipfile
from functools import partial
from typing import Any

from app.legacy_memory_preview import archive_database_entries, read_archive_database
from app.legacy_task_history import read_history
from app.plugins.contracts import PluginManifest
from app.plugins.worker_lifecycle import run_thread

MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
logger = logging.getLogger(__name__)


class LegacyHistoryApprovalRequired(Exception):
    pass


class LegacyHistoryPlugin:
    manifest = PluginManifest(
        "legacy_history", "Eski görev geçmişi", "Geçici arşivden salt okunur görev incelemesi.",
        ("candidates", "list", "detail"),
    )

    async def invoke(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("approved") is not True:
            raise LegacyHistoryApprovalRequired("Arşivin yerel incelenmesi için açık onay gerekir.")
        archive = payload.get("archive")
        if not isinstance(archive, bytes) or not 0 < len(archive) <= MAX_ARCHIVE_BYTES:
            raise ValueError("Arşiv boş veya 64 MiB sınırını aşıyor.")
        if action == "candidates":
            return await run_thread(partial(self._candidates, archive), logger)
        if action not in {"list", "detail"}:
            raise ValueError("Bilinmeyen geçmiş işlemi.")
        index = payload.get("database_index")
        digest = payload.get("source_sha256")
        task_id = payload.get("task_id") if action == "detail" else None
        if not isinstance(index, int) or isinstance(index, bool):
            raise TypeError("Veritabanı numarası geçersiz.")
        if not isinstance(digest, str):
            raise TypeError("Veritabanı hash değeri gerekli.")
        if action == "detail" and (not isinstance(task_id, str) or not task_id):
            raise ValueError("Görev kimliği gerekli.")
        return await run_thread(partial(read_history, io.BytesIO(archive), index, digest, task_id), logger)

    @staticmethod
    def _candidates(data: bytes) -> dict[str, Any]:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive_database_entries(archive)
            candidates = [
                {"database_index": index, "source_sha256": hashlib.sha256(read_archive_database(archive, entry)).hexdigest()}
                for index, entry in enumerate(entries, 1)
            ]
        return {"candidates": candidates}
