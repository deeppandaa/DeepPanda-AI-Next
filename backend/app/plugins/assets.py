from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import re
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

from app.plugins.contracts import PluginManifest


class AssetApprovalRequired(Exception):
    pass


class AssetNotFoundError(Exception):
    pass


class AssetsPlugin:
    """Local catalog for generated and uploaded media/report artifacts."""

    manifest = PluginManifest(
        plugin_id="assets",
        display_name="Local Assets",
        description="Üretilen rapor, ses, görsel ve video dosyalarının yerel kataloğu.",
        actions=("store", "staging_dir", "list", "get", "asset", "delete"),
    )

    kinds: ClassVar[frozenset[str]] = frozenset({"report", "audio", "image", "video", "document", "other"})
    max_store_bytes: ClassVar[int] = 500_000_000
    max_metadata_bytes: ClassVar[int] = 20_000

    def __init__(self, data_dir: str | Path | None = None) -> None:
        self.data_dir = Path(data_dir or os.getenv("AI_DATA_DIR", "/data")).expanduser().resolve()
        self.assets_dir = self.data_dir / "assets"
        self.staging_path = self.assets_dir / "staging"
        self.database_path = self.data_dir / "assets.db"

    async def invoke(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        handlers = {
            "store": self._store,
            "staging_dir": self._staging_dir,
            "list": self._list,
            "get": self._get,
            "asset": self._asset,
            "delete": self._delete,
        }
        handler = handlers.get(action)
        if handler is None:
            raise ValueError(f"Unsupported assets action: {action}")
        return handler(payload)

    def _connect(self) -> sqlite3.Connection:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS assets (
                asset_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                filename TEXT NOT NULL,
                relative_path TEXT NOT NULL,
                media_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                sha256 TEXT NOT NULL,
                source TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_assets_kind_created ON assets(kind, created_at DESC)")
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _staging_dir(self, _: dict[str, Any]) -> dict[str, Any]:
        self.staging_path.mkdir(parents=True, exist_ok=True)
        return {"path": str(self.staging_path)}

    def _store(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("approved") is not True:
            raise AssetApprovalRequired("Storing an asset requires approved=true.")
        kind = payload.get("kind")
        if kind not in self.kinds:
            raise ValueError(f"kind must be one of: {', '.join(sorted(self.kinds))}.")
        filename = self._text(payload.get("filename"), "filename", 200)
        safe_name = re.sub(r"[^\w.\- ]+", "_", Path(filename.replace("\\", "/")).name).strip() or "asset"
        extension = Path(safe_name).suffix.casefold()
        if not re.fullmatch(r"\.[a-z0-9]{1,8}", extension):
            raise ValueError("filename must have a short alphanumeric extension.")
        source = self._text(payload.get("source", "generated"), "source", 80)
        metadata = payload.get("metadata") or {}
        if not isinstance(metadata, dict):
            raise TypeError("metadata must be an object.")
        metadata_json = json.dumps(metadata, ensure_ascii=False, default=str)
        if len(metadata_json.encode("utf-8")) > self.max_metadata_bytes:
            raise ValueError("metadata is too large.")
        media_type = payload.get("media_type") or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
        if not isinstance(media_type, str) or len(media_type) > 100:
            raise ValueError("media_type must be a short string.")

        asset_id = uuid.uuid4().hex
        stored_name = f"{asset_id}{extension}"
        target_dir = self.assets_dir / kind
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / stored_name
        staged = payload.get("staged_path")
        if staged is not None:
            source_path = self._staged_file(staged)
            if source_path.stat().st_size > self.max_store_bytes:
                raise ValueError("Asset exceeds the storage size limit.")
            os.replace(source_path, target)
        else:
            encoded = payload.get("content_base64")
            if not isinstance(encoded, str):
                raise ValueError("Either staged_path or content_base64 is required.")
            try:
                raw = base64.b64decode(encoded, validate=True)
            except (ValueError, base64.binascii.Error) as exc:
                raise ValueError("content_base64 is invalid.") from exc
            if not raw or len(raw) > self.max_store_bytes:
                raise ValueError("Asset must be non-empty and within the storage size limit.")
            temporary = target_dir / f".{stored_name}.tmp"
            temporary.write_bytes(raw)
            os.replace(temporary, target)

        digest = self._sha256(target)
        size = target.stat().st_size
        created_at = datetime.now(UTC).isoformat(timespec="seconds")
        try:
            with self._connection() as connection:
                connection.execute(
                    "INSERT INTO assets(asset_id,kind,filename,relative_path,media_type,size_bytes,sha256,source,metadata_json,created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (asset_id, kind, safe_name, f"assets/{kind}/{stored_name}", media_type, size, digest, source, metadata_json, created_at),
                )
        except Exception:
            target.unlink(missing_ok=True)
            raise
        return {
            "asset_id": asset_id,
            "kind": kind,
            "filename": safe_name,
            "media_type": media_type,
            "size_bytes": size,
            "sha256": digest,
            "source": source,
            "metadata": metadata,
            "created_at": created_at,
            "download_url": f"/api/assets/{asset_id}",
        }

    def _list(self, payload: dict[str, Any]) -> dict[str, Any]:
        limit = payload.get("limit", 50)
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("limit must be an integer.")
        limit = max(1, min(limit, 200))
        kind = payload.get("kind")
        sql = "SELECT * FROM assets"
        values: list[Any] = []
        if kind:
            if kind not in self.kinds:
                raise ValueError("Unknown asset kind.")
            sql += " WHERE kind=?"
            values.append(kind)
        sql += " ORDER BY created_at DESC, asset_id LIMIT ?"
        values.append(limit)
        with self._connection() as connection:
            rows = connection.execute(sql, values).fetchall()
        return {"assets": [self._public(row) for row in rows]}

    def _get(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"asset": self._public(self._row(payload.get("asset_id")))}

    def _asset(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = self._row(payload.get("asset_id"))
        path = self._stored_path(row["relative_path"])
        if not path.is_file():
            raise AssetNotFoundError("Asset file is missing.")
        return {"path": str(path), "filename": row["filename"], "media_type": row["media_type"]}

    def _delete(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("approved") is not True:
            raise AssetApprovalRequired("Deleting an asset requires approved=true.")
        row = self._row(payload.get("asset_id"))
        path = self._stored_path(row["relative_path"])
        with self._connection() as connection:
            connection.execute("DELETE FROM assets WHERE asset_id=?", (row["asset_id"],))
        path.unlink(missing_ok=True)
        return {"asset_id": row["asset_id"], "deleted": True}

    def _row(self, asset_id: Any) -> sqlite3.Row:
        if not isinstance(asset_id, str) or not re.fullmatch(r"[0-9a-f]{32}", asset_id):
            raise AssetNotFoundError("Asset was not found.")
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM assets WHERE asset_id=?", (asset_id,)).fetchone()
        if row is None:
            raise AssetNotFoundError("Asset was not found.")
        return row

    def _staged_file(self, value: Any) -> Path:
        if not isinstance(value, str) or not value:
            raise ValueError("staged_path must be a string.")
        candidate = Path(value).expanduser().resolve()
        staging = self.staging_path.resolve()
        if staging not in candidate.parents or not candidate.is_file() or candidate.is_symlink():
            raise ValueError("staged_path must be a regular file inside the asset staging directory.")
        return candidate

    def _stored_path(self, relative_path: str) -> Path:
        path = (self.data_dir / relative_path).resolve()
        if self.assets_dir.resolve() not in path.parents:
            raise AssetNotFoundError("Asset path is outside the asset store.")
        return path

    @staticmethod
    def _public(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item.pop("relative_path", None)
        item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
        item["download_url"] = f"/api/assets/{item['asset_id']}"
        return item

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1_048_576), b""):
                digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def _text(value: Any, key: str, max_length: int) -> str:
        if not isinstance(value, str) or not value.strip() or len(value) > max_length:
            raise ValueError(f"{key} must be a non-empty string up to {max_length} characters.")
        return value.strip()
