from __future__ import annotations

import asyncio
import base64
import binascii
import json
import os
import re
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from app.plugins.contracts import PluginManifest
from app.plugins.gateway import PluginGateway


class RepoWatchApprovalRequired(Exception):
    pass


class RepoWatchNotFoundError(Exception):
    pass


class RepoWatchRateLimitError(Exception):
    pass


class RepoWatchProviderError(Exception):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


class RepoWatchPlugin:
    manifest = PluginManifest(
        plugin_id="repo_watch",
        display_name="GitHub Repository Watch",
        description="Allowlist içindeki public GitHub depolarının release ve commit metadata'sını kontrol eder.",
        actions=("add", "list", "check", "snapshot_readme", "snapshot_files", "remove", "polling_status", "configure_polling"),
    )
    max_checks_per_hour = 20
    repo_cooldown_seconds = 60
    min_poll_interval_minutes = 5
    max_poll_interval_minutes = 1440
    default_poll_interval_minutes = 60
    max_response_bytes = 256_000
    max_snapshot_files = 5
    max_snapshot_file_bytes = 1_000_000
    max_snapshot_total_bytes = 3_000_000
    snapshot_extensions = frozenset({".md", ".txt", ".json", ".toml", ".yaml", ".yml", ".ts", ".tsx", ".js", ".mjs", ".c", ".h", ".cpp", ".hpp", ".rs", ".py"})
    repository_pattern = re.compile(r"([A-Za-z0-9-]{1,39})/([A-Za-z0-9._-]{1,100})\Z")
    sha_pattern = re.compile(r"[0-9a-fA-F]{40,64}\Z")

    def __init__(
        self,
        database_path: str | Path | None = None,
        client_factory: Callable[..., Any] = httpx.AsyncClient,
        clock: Callable[[], datetime] | None = None,
        gateway: PluginGateway | None = None,
    ) -> None:
        if database_path is None:
            data_root = Path(os.getenv("AI_DATA_DIR", "/data")).expanduser()
            database_path = data_root / "repo_watch.db"
        self.database_path = Path(database_path).expanduser().resolve()
        self.client_factory = client_factory
        self.clock = clock or (lambda: datetime.now(UTC))
        self.gateway = gateway
        self._polling_lock = asyncio.Lock()

    async def invoke(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "add":
            return self._add(payload)
        if action == "list":
            return self._list()
        if action == "remove":
            return self._remove(payload)
        if action == "polling_status":
            return self._polling_status()
        if action == "configure_polling":
            return self._configure_polling(payload)
        if action == "check":
            return await self._check(payload)
        if action == "snapshot_readme":
            return await self._snapshot_readme(payload)
        if action == "snapshot_files":
            return await self._snapshot_files(payload)
        raise ValueError(f"Unsupported repo watch action: {action}")

    def _connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute(
            "CREATE TABLE IF NOT EXISTS watched_repositories ("
            "repository TEXT PRIMARY KEY, owner TEXT NOT NULL, name TEXT NOT NULL, added_at TEXT NOT NULL, "
            "checked_at TEXT, release_tag TEXT, release_title TEXT, release_url TEXT, "
            "commit_sha TEXT, commit_message TEXT, commit_url TEXT, readme_sha TEXT, "
            "readme_document_id TEXT, readme_source_url TEXT)"
        )
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(watched_repositories)")}
        for column in ("readme_sha", "readme_document_id", "readme_source_url"):
            if column not in columns:
                connection.execute(f"ALTER TABLE watched_repositories ADD COLUMN {column} TEXT")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS repository_check_attempts ("
            "attempt_id INTEGER PRIMARY KEY AUTOINCREMENT, repository TEXT NOT NULL, attempted_at TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_repo_check_attempts_time ON repository_check_attempts(attempted_at)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS repository_poll_settings ("
            "singleton INTEGER PRIMARY KEY CHECK(singleton=1), enabled INTEGER NOT NULL DEFAULT 0, "
            "interval_minutes INTEGER NOT NULL DEFAULT 60, next_run_at TEXT, last_started_at TEXT, "
            "last_completed_at TEXT, last_error TEXT, last_check_count INTEGER NOT NULL DEFAULT 0, "
            "last_changes TEXT NOT NULL DEFAULT '[]', last_polled_repository TEXT)"
        )
        settings_columns = {row["name"] for row in connection.execute("PRAGMA table_info(repository_poll_settings)")}
        for column, definition in (
            ("last_check_count", "INTEGER NOT NULL DEFAULT 0"),
            ("last_changes", "TEXT NOT NULL DEFAULT '[]'"),
            ("last_polled_repository", "TEXT"),
        ):
            if column not in settings_columns:
                connection.execute(f"ALTER TABLE repository_poll_settings ADD COLUMN {column} {definition}")
        connection.execute(
            "INSERT OR IGNORE INTO repository_poll_settings(singleton,enabled,interval_minutes) VALUES(1,0,?)",
            (self.default_poll_interval_minutes,),
        )
        connection.commit()
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

    def _add(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_approval(payload, "Adding a watched repository")
        repository, owner, name = self._repository(payload.get("repository"))
        now = self._now().isoformat(timespec="seconds")
        with self._connection() as connection:
            inserted = connection.execute(
                "INSERT OR IGNORE INTO watched_repositories(repository,owner,name,added_at) VALUES(?,?,?,?)",
                (repository, owner, name, now),
            ).rowcount == 1
            row = connection.execute(
                "SELECT repository,owner,name,added_at,checked_at,release_tag,release_title,release_url,"
                "commit_sha,commit_message,commit_url FROM watched_repositories WHERE repository=?",
                (repository,),
            ).fetchone()
        return {"repository": dict(row), "added": inserted}

    def _list(self) -> dict[str, Any]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT repository,owner,name,added_at,checked_at,release_tag,release_title,release_url,"
                "commit_sha,commit_message,commit_url FROM watched_repositories ORDER BY repository"
            ).fetchall()
        return {"repositories": [dict(row) for row in rows]}

    def _remove(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_approval(payload, "Removing a watched repository")
        repository, _, _ = self._repository(payload.get("repository"))
        with self._connection() as connection:
            result = connection.execute("DELETE FROM watched_repositories WHERE repository=?", (repository,))
            if result.rowcount == 0:
                raise RepoWatchNotFoundError("Repository is not in the watch allowlist.")
        return {"repository": repository, "removed": True}

    def _polling_status(self) -> dict[str, Any]:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT enabled,interval_minutes,next_run_at,last_started_at,last_completed_at,last_error,"
                "last_check_count,last_changes,last_polled_repository "
                "FROM repository_poll_settings WHERE singleton=1"
            ).fetchone()
        result = dict(row)
        result["enabled"] = bool(result["enabled"])
        result["last_changes"] = json.loads(result["last_changes"])
        return result

    def _configure_polling(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_approval(payload, "Changing recurring repository polling")
        enabled = payload.get("enabled")
        interval = payload.get("interval_minutes", self.default_poll_interval_minutes)
        if not isinstance(enabled, bool):
            raise TypeError("enabled must be a boolean.")
        if isinstance(interval, bool) or not isinstance(interval, int):
            raise TypeError("interval_minutes must be an integer.")
        if not self.min_poll_interval_minutes <= interval <= self.max_poll_interval_minutes:
            raise ValueError(
                f"interval_minutes must be between {self.min_poll_interval_minutes} and "
                f"{self.max_poll_interval_minutes}."
            )
        next_run = (self._now() + timedelta(minutes=interval)).isoformat(timespec="seconds") if enabled else None
        with self._connection() as connection:
            connection.execute(
                "UPDATE repository_poll_settings SET enabled=?,interval_minutes=?,next_run_at=?,last_error=NULL "
                "WHERE singleton=1",
                (int(enabled), interval, next_run),
            )
        return self._polling_status()

    async def run_polling_cycle(self) -> dict[str, Any]:
        async with self._polling_lock:
            initial = self._polling_status()
            if not initial["enabled"]:
                return initial
            started_at = self._now().isoformat(timespec="seconds")
            with self._connection() as connection:
                connection.execute(
                    "UPDATE repository_poll_settings SET last_started_at=?,last_error=NULL WHERE singleton=1",
                    (started_at,),
                )

            checked_count = 0
            changes: list[str] = []
            last_error = None
            repositories = self._list()["repositories"]
            cursor = initial["last_polled_repository"]
            if cursor and repositories:
                next_index = next(
                    (index + 1 for index, item in enumerate(repositories) if item["repository"] == cursor),
                    0,
                )
                repositories = repositories[next_index:] + repositories[:next_index]
            for entry in repositories:
                if not self._polling_status()["enabled"]:
                    break
                try:
                    result = await self._check({"repository": entry["repository"], "approved": True})
                    checked_count += 1
                    with self._connection() as connection:
                        connection.execute(
                            "UPDATE repository_poll_settings SET last_polled_repository=? WHERE singleton=1",
                            (entry["repository"],),
                        )
                    if result["release_changed"] or result["commit_changed"]:
                        changes.append(entry["repository"])
                except RepoWatchRateLimitError as exc:
                    last_error = str(exc)
                    break
                except (RepoWatchNotFoundError, RepoWatchProviderError) as exc:
                    last_error = str(exc)[:500]

            completed_at = self._now().isoformat(timespec="seconds")
            current = self._polling_status()
            next_run = (
                (self._now() + timedelta(minutes=current["interval_minutes"])).isoformat(timespec="seconds")
                if current["enabled"]
                else None
            )
            with self._connection() as connection:
                connection.execute(
                    "UPDATE repository_poll_settings SET last_completed_at=?,next_run_at=?,last_error=?,"
                    "last_check_count=?,last_changes=? WHERE singleton=1",
                    (completed_at, next_run, last_error, checked_count, json.dumps(changes),),
                )
            return self._polling_status()

    async def polling_worker(self) -> None:
        while True:
            status = self._polling_status()
            if not status["enabled"]:
                await asyncio.sleep(30)
                continue
            next_run = status["next_run_at"]
            delay = 0
            if next_run:
                delay = max(0, (datetime.fromisoformat(next_run) - self._now()).total_seconds())
            if delay > 0:
                await asyncio.sleep(min(delay, 30))
                continue
            try:
                await self.run_polling_cycle()
            except (OSError, RepoWatchProviderError, RepoWatchNotFoundError, RepoWatchRateLimitError, sqlite3.Error, ValueError) as exc:
                completed_at = self._now().isoformat(timespec="seconds")
                current = self._polling_status()
                next_run = (
                    (self._now() + timedelta(minutes=current["interval_minutes"])).isoformat(timespec="seconds")
                    if current["enabled"]
                    else None
                )
                with self._connection() as connection:
                    connection.execute(
                        "UPDATE repository_poll_settings SET last_completed_at=?,next_run_at=?,last_error=? "
                        "WHERE singleton=1",
                        (completed_at, next_run, str(exc)[:500]),
                    )

    async def _check(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_approval(payload, "Checking public repository metadata")
        repository, owner, name = self._repository(payload.get("repository"))
        previous, local_remaining = self._reserve_check(repository)
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "DeepPanda-AI-Next-Repo-Watch",
        }
        timeout = httpx.Timeout(10.0, connect=5.0)
        async with self.client_factory(
            base_url="https://api.github.com",
            headers=headers,
            timeout=timeout,
            follow_redirects=False,
        ) as client:
            release_data = await self._get_json(client, f"/repos/{owner}/{name}/releases/latest", allow_not_found=True)
            commit_data = await self._get_json(client, f"/repos/{owner}/{name}/commits?per_page=1")

        release = self._normalize_release(owner, name, release_data)
        commit = self._normalize_commit(owner, name, commit_data)
        now = self._now().isoformat(timespec="seconds")
        release_changed = previous["checked_at"] is not None and previous["release_tag"] != release["tag"]
        commit_changed = previous["checked_at"] is not None and previous["commit_sha"] != commit["sha"]
        with self._connection() as connection:
            connection.execute(
                "UPDATE watched_repositories SET checked_at=?,release_tag=?,release_title=?,release_url=?,"
                "commit_sha=?,commit_message=?,commit_url=? WHERE repository=?",
                (
                    now,
                    release["tag"],
                    release["title"],
                    release["url"],
                    commit["sha"],
                    commit["message"],
                    commit["url"],
                    repository,
                ),
            )
        return {
            "repository": repository,
            "checked_at": now,
            "baseline": previous["checked_at"] is None,
            "release_changed": release_changed,
            "commit_changed": commit_changed,
            "release": release,
            "latest_commit": commit,
            "rate_limit": {
                "local_remaining_this_hour": local_remaining,
                "max_per_hour": self.max_checks_per_hour,
                "repository_cooldown_seconds": self.repo_cooldown_seconds,
            },
        }

    async def _snapshot_readme(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_approval(payload, "Indexing a public repository README")
        if self.gateway is None:
            raise RepoWatchProviderError("The document index is unavailable.", status_code=503)
        repository, owner, name = self._repository(payload.get("repository"))
        previous, local_remaining = self._reserve_check(repository)
        timeout = httpx.Timeout(15.0, connect=5.0)
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "DeepPanda-AI-Next-Repo-Watch",
        }
        async with self.client_factory(
            base_url="https://api.github.com",
            headers=headers,
            timeout=timeout,
            follow_redirects=False,
        ) as client:
            readme = await self._get_json(client, f"/repos/{owner}/{name}/readme", max_bytes=1_500_000)
        if not isinstance(readme, dict) or readme.get("type") != "file":
            raise RepoWatchProviderError("GitHub did not return a README file.")
        path = self._clean_text(readme.get("path"), 255)
        if not path or not path.rsplit("/", 1)[-1].casefold().startswith("readme"):
            raise RepoWatchProviderError("GitHub returned an unexpected README path.")
        blob_sha = readme.get("sha")
        encoded = readme.get("content")
        if not isinstance(blob_sha, str) or not self.sha_pattern.fullmatch(blob_sha):
            raise RepoWatchProviderError("GitHub returned an invalid README blob identifier.")
        if readme.get("encoding") != "base64" or not isinstance(encoded, str):
            raise RepoWatchProviderError("GitHub returned an unsupported README encoding.")
        try:
            raw = base64.b64decode("".join(encoded.split()), validate=True)
        except (ValueError, binascii.Error) as exc:
            raise RepoWatchProviderError("GitHub returned invalid README content.") from exc
        if not raw or len(raw) > 1_000_000:
            raise RepoWatchProviderError("README must be between 1 byte and 1 MB.")
        if previous["readme_sha"] == blob_sha:
            return {
                "repository": repository,
                "already_indexed": True,
                "document_id": previous["readme_document_id"],
                "source_url": previous["readme_source_url"],
                "blob_sha": blob_sha,
                "rate_limit": {"local_remaining_this_hour": local_remaining, "max_per_hour": self.max_checks_per_hour},
            }
        try:
            readme_text = raw.decode("utf-8-sig", errors="replace")
        except UnicodeDecodeError as exc:
            raise RepoWatchProviderError("README is not valid UTF-8 text.") from exc
        safe_path = "/".join(quote(part, safe="") for part in path.split("/"))
        source_url = f"https://github.com/{owner}/{name}/blob/{blob_sha}/{safe_path}"
        prefix = f"Source: {source_url}\nRepository: {repository}\nGitHub blob: {blob_sha}\n\n"
        indexed_bytes = (prefix + readme_text).encode("utf-8")
        if len(indexed_bytes) > 1_100_000:
            raise RepoWatchProviderError("README plus source metadata exceeds the indexing limit.")
        filename = f"{owner}-{name}-README.md"[:255]
        document = await self.gateway.invoke(
            "documents",
            "ingest",
            {
                "approved": True,
                "filename": filename,
                "content_base64": base64.b64encode(indexed_bytes).decode("ascii"),
            },
        )
        with self._connection() as connection:
            connection.execute(
                "UPDATE watched_repositories SET readme_sha=?,readme_document_id=?,readme_source_url=? WHERE repository=?",
                (blob_sha, document["document_id"], source_url, repository),
            )
        return {
            "repository": repository,
            "already_indexed": False,
            "document_id": document["document_id"],
            "filename": filename,
            "source_url": source_url,
            "blob_sha": blob_sha,
            "indexed_characters": document["extracted_characters"],
            "rate_limit": {"local_remaining_this_hour": local_remaining, "max_per_hour": self.max_checks_per_hour},
        }

    async def _snapshot_files(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_approval(payload, "Indexing selected public repository files")
        if self.gateway is None:
            raise RepoWatchProviderError("The document index is unavailable.", status_code=503)
        repository, owner, name = self._repository(payload.get("repository"))
        raw_paths = payload.get("paths")
        if not isinstance(raw_paths, list) or not 1 <= len(raw_paths) <= self.max_snapshot_files:
            raise ValueError(f"paths must contain 1 to {self.max_snapshot_files} explicit file paths.")
        paths = [self._snapshot_path(value) for value in raw_paths]
        if len(set(paths)) != len(paths):
            raise ValueError("paths must not contain duplicates.")
        self._reserve_check(repository)
        timeout = httpx.Timeout(15.0, connect=5.0)
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "DeepPanda-AI-Next-Repo-Watch",
        }
        snapshots = []
        total_bytes = 0
        async with self.client_factory(
            base_url="https://api.github.com",
            headers=headers,
            timeout=timeout,
            follow_redirects=False,
        ) as client:
            for path in paths:
                encoded_path = "/".join(quote(part, safe="") for part in path.split("/"))
                item = await self._get_json(
                    client,
                    f"/repos/{owner}/{name}/contents/{encoded_path}",
                    max_bytes=1_500_000,
                )
                if not isinstance(item, dict) or item.get("type") != "file" or item.get("path") != path:
                    raise RepoWatchProviderError("GitHub returned an unexpected file for the selected path.")
                blob_sha = item.get("sha")
                encoded = item.get("content")
                if not isinstance(blob_sha, str) or not self.sha_pattern.fullmatch(blob_sha):
                    raise RepoWatchProviderError("GitHub returned an invalid file blob identifier.")
                if item.get("encoding") != "base64" or not isinstance(encoded, str):
                    raise RepoWatchProviderError("GitHub returned an unsupported file encoding.")
                try:
                    raw = base64.b64decode("".join(encoded.split()), validate=True)
                except (ValueError, binascii.Error) as exc:
                    raise RepoWatchProviderError("GitHub returned invalid file content.") from exc
                total_bytes += len(raw)
                if not raw or len(raw) > self.max_snapshot_file_bytes:
                    raise RepoWatchProviderError(f"Each selected file must be between 1 byte and {self.max_snapshot_file_bytes} bytes.")
                if total_bytes > self.max_snapshot_total_bytes:
                    raise RepoWatchProviderError(f"Selected files exceed the {self.max_snapshot_total_bytes}-byte total limit.")
                try:
                    text = raw.decode("utf-8-sig", errors="strict")
                except UnicodeDecodeError as exc:
                    raise RepoWatchProviderError("Selected files must be UTF-8 text; binary files are not accepted.") from exc
                snapshots.append((path, blob_sha.lower(), raw, text))

        indexed = []
        with self._connection() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS repository_snapshot_files ("
                "repository TEXT NOT NULL, path TEXT NOT NULL, blob_sha TEXT NOT NULL, "
                "document_id TEXT NOT NULL, source_url TEXT NOT NULL, indexed_at TEXT NOT NULL, "
                "PRIMARY KEY(repository,path))"
            )
        for path, blob_sha, _, text in snapshots:
            with self._connection() as connection:
                previous = connection.execute(
                    "SELECT blob_sha,document_id,source_url FROM repository_snapshot_files "
                    "WHERE repository=? AND path=?",
                    (repository, path),
                ).fetchone()
            if previous is not None and previous["blob_sha"] == blob_sha:
                indexed.append({
                    "path": path,
                    "blob_sha": blob_sha,
                    "document_id": previous["document_id"],
                    "source_url": previous["source_url"],
                    "already_indexed": True,
                })
                continue
            source_url = f"https://github.com/{owner}/{name}/blob/{blob_sha}/{path}"
            prefix = f"Source: {source_url}\nRepository: {repository}\nPath: {path}\nGitHub blob: {blob_sha}\n\n"
            content = (prefix + text).encode("utf-8")
            if len(content) > self.max_snapshot_file_bytes + 1_000:
                raise RepoWatchProviderError("File plus source metadata exceeds the indexing limit.")
            filename = f"{owner}-{name}-{Path(path).name}"[:255]
            document = await self.gateway.invoke(
                "documents",
                "ingest",
                {"approved": True, "filename": filename, "content_base64": base64.b64encode(content).decode("ascii")},
            )
            now = self._now().isoformat(timespec="seconds")
            with self._connection() as connection:
                connection.execute(
                    "INSERT INTO repository_snapshot_files(repository,path,blob_sha,document_id,source_url,indexed_at) "
                    "VALUES(?,?,?,?,?,?) ON CONFLICT(repository,path) DO UPDATE SET "
                    "blob_sha=excluded.blob_sha,document_id=excluded.document_id,"
                    "source_url=excluded.source_url,indexed_at=excluded.indexed_at",
                    (repository, path, blob_sha, document["document_id"], source_url, now),
                )
            indexed.append({
                "path": path,
                "blob_sha": blob_sha,
                "document_id": document["document_id"],
                "source_url": source_url,
                "already_indexed": False,
            })
        return {"repository": repository, "indexed_files": indexed, "total_bytes": total_bytes}

    def _reserve_check(self, repository: str, *, enforce_cooldown: bool = True) -> tuple[dict[str, Any], int]:
        now = self._now()
        cutoff = (now - timedelta(hours=1)).isoformat(timespec="seconds")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM repository_check_attempts WHERE attempted_at<?", (cutoff,))
            row = connection.execute(
                "SELECT checked_at,release_tag,commit_sha,readme_sha,readme_document_id,readme_source_url "
                "FROM watched_repositories WHERE repository=?",
                (repository,),
            ).fetchone()
            if row is None:
                raise RepoWatchNotFoundError("Repository must be added to the allowlist before checking it.")
            attempts = connection.execute(
                "SELECT COUNT(*) FROM repository_check_attempts WHERE attempted_at>=?", (cutoff,)
            ).fetchone()[0]
            if attempts >= self.max_checks_per_hour:
                raise RepoWatchRateLimitError(f"Local repository checks are limited to {self.max_checks_per_hour} per hour.")
            last_attempt = connection.execute(
                "SELECT attempted_at FROM repository_check_attempts WHERE repository=? ORDER BY attempt_id DESC LIMIT 1",
                (repository,),
            ).fetchone()
            if enforce_cooldown and last_attempt is not None:
                last_time = datetime.fromisoformat(last_attempt["attempted_at"])
                elapsed = (now - last_time).total_seconds()
                if elapsed < self.repo_cooldown_seconds:
                    wait = max(1, int(self.repo_cooldown_seconds - elapsed))
                    raise RepoWatchRateLimitError(f"Wait {wait} seconds before checking this repository again.")
            connection.execute(
                "INSERT INTO repository_check_attempts(repository,attempted_at) VALUES(?,?)",
                (repository, now.isoformat(timespec="seconds")),
            )
            return dict(row), self.max_checks_per_hour - attempts - 1

    async def _get_json(
        self,
        client: Any,
        path: str,
        *,
        allow_not_found: bool = False,
        max_bytes: int | None = None,
    ) -> Any:
        try:
            response = await client.get(path)
        except httpx.HTTPError as exc:
            raise RepoWatchProviderError("Could not reach the public GitHub API.") from exc
        if response.status_code in {403, 429}:
            reset = response.headers.get("X-RateLimit-Reset")
            retry_after = response.headers.get("Retry-After")
            detail = "GitHub rate limit reached."
            if retry_after and retry_after.isdigit():
                detail += f" Retry after {retry_after} seconds."
            elif reset and reset.isdigit():
                detail += f" Retry after Unix time {reset}."
            raise RepoWatchProviderError(detail, status_code=429)
        if response.status_code == 404 and allow_not_found:
            return None
        if response.status_code >= 400:
            raise RepoWatchProviderError("GitHub could not return metadata for this public repository.")
        content = response.content
        if len(content) > (max_bytes or self.max_response_bytes):
            raise RepoWatchProviderError("GitHub metadata response exceeded the size limit.")
        try:
            return response.json()
        except (ValueError, TypeError) as exc:
            raise RepoWatchProviderError("GitHub returned invalid metadata JSON.") from exc

    def _normalize_release(self, owner: str, name: str, value: Any) -> dict[str, str] | None:
        if value is None:
            return None
        if not isinstance(value, dict):
            raise RepoWatchProviderError("GitHub returned an invalid release record.")
        tag = self._clean_text(value.get("tag_name"), 100)
        if not tag:
            raise RepoWatchProviderError("GitHub release metadata is missing its tag.")
        title = self._clean_text(value.get("name"), 200) or tag
        return {"tag": tag, "title": title, "url": f"https://github.com/{owner}/{name}/releases/latest"}

    def _normalize_commit(self, owner: str, name: str, value: Any) -> dict[str, str]:
        if not isinstance(value, list) or not value or not isinstance(value[0], dict):
            raise RepoWatchProviderError("GitHub returned no valid commit metadata.")
        item = value[0]
        sha = item.get("sha")
        commit = item.get("commit")
        if not isinstance(sha, str) or not self.sha_pattern.fullmatch(sha) or not isinstance(commit, dict):
            raise RepoWatchProviderError("GitHub returned an invalid commit record.")
        message = self._clean_text(commit.get("message"), 500)
        if not message:
            message = "(commit message unavailable)"
        return {
            "sha": sha.lower(),
            "message": message,
            "url": f"https://github.com/{owner}/{name}/commit/{sha.lower()}",
        }

    @classmethod
    def _repository(cls, value: Any) -> tuple[str, str, str]:
        if not isinstance(value, str) or len(value) > 140:
            raise ValueError("repository must be owner/repository.")
        match = cls.repository_pattern.fullmatch(value.strip())
        if not match or match.group(2) in {".", ".."}:
            raise ValueError("repository must be a GitHub owner/repository identifier.")
        owner, name = match.groups()
        return f"{owner}/{name}", owner, name

    @classmethod
    def _snapshot_path(cls, value: Any) -> str:
        if not isinstance(value, str) or not value.strip() or len(value) > 300:
            raise ValueError("Each path must be a non-empty repository-relative path up to 300 characters.")
        path = value.strip()
        parts = path.split("/")
        if path.startswith("/") or "\\" in path or any(part in {"", ".", ".."} for part in parts):
            raise ValueError("Paths must be normalized repository-relative file paths without traversal.")
        if Path(parts[-1]).suffix.casefold() not in cls.snapshot_extensions:
            raise ValueError("Only supported UTF-8 text and source file extensions can be indexed.")
        return path

    @staticmethod
    def _require_approval(payload: dict[str, Any], action: str) -> None:
        if payload.get("approved") is not True:
            raise RepoWatchApprovalRequired(f"{action} requires approved=true.")

    @staticmethod
    def _clean_text(value: Any, limit: int) -> str:
        if not isinstance(value, str):
            return ""
        return " ".join(value.split())[:limit]

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)