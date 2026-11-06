from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, ClassVar

from app.plugins.contracts import PluginManifest
from app.plugins.gateway import PluginGateway


class JobApprovalRequired(Exception):
    pass


class JobNotFoundError(Exception):
    pass


class JobsPlugin:
    manifest = PluginManifest(
        plugin_id="jobs",
        display_name="Background Jobs",
        description="Kalıcı job state, progress events, cooperative cancel ve onaylı retry.",
        actions=("create", "list", "get", "claim", "heartbeat", "progress", "complete", "fail", "cancel", "retry", "recovery_candidates", "recover_stale", "record_memory"),
    )

    terminal_statuses: ClassVar[frozenset[str]] = frozenset({"cancelled", "succeeded", "failed"})
    max_input_bytes: ClassVar[int] = 50_000
    max_result_bytes: ClassVar[int] = 50_000
    max_events: ClassVar[int] = 500

    def __init__(self, database_path: str | Path | None = None, gateway: PluginGateway | None = None) -> None:
        self.gateway = gateway
        if database_path is None:
            data_root = Path(os.getenv("AI_DATA_DIR", "/data")).expanduser()
            database_path = data_root / "jobs.db"
        self.database_path = Path(database_path).expanduser().resolve()

    async def invoke(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        actions = {
            "create": self._create,
            "list": self._list,
            "get": self._get,
            "claim": self._claim,
            "heartbeat": self._heartbeat,
            "progress": self._progress,
            "complete": self._complete,
            "fail": self._fail,
            "cancel": self._cancel,
            "retry": self._retry,
            "recovery_candidates": self._recovery_candidates,
            "recover_stale": self._recover_stale,
            "record_memory": self._record_memory,
        }
        handler = actions.get(action)
        if handler is None:
            raise ValueError(f"Unsupported jobs action: {action}")
        result = handler(payload)
        if action == "retry" and self.gateway is not None:
            consumer = {
                "media_video": "media", "evaluation": "evaluation",
                "research": "research", "github_research": "research",
            }.get(result["kind"])
            if consumer is not None:
                await self.gateway.invoke(consumer, "resume_job", {"approved": True, "job_id": result["job_id"]})
                result["status"] = "running"
        return result

    def _connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                parent_job_id TEXT REFERENCES jobs(job_id),
                kind TEXT NOT NULL,
                input_json TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN (
                    'queued','running','cancel_requested','cancelled','succeeded','failed'
                )),
                progress INTEGER NOT NULL DEFAULT 0 CHECK(progress BETWEEN 0 AND 100),
                worker_id TEXT NOT NULL DEFAULT '',
                result_json TEXT NOT NULL DEFAULT 'null',
                error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS job_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
                event TEXT NOT NULL,
                detail_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_jobs_updated ON jobs(updated_at)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_job_events_job ON job_events(job_id,event_id)")
        return connection

    @contextmanager
    def _connection(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            if write:
                connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _create(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("approved") is not True:
            raise JobApprovalRequired("Creating a background job requires approved=true.")
        kind = payload.get("kind")
        if not isinstance(kind, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{1,39}", kind):
            raise ValueError("kind must be a lowercase job type identifier (2-40 characters).")
        job_input = payload.get("input", {})
        if not isinstance(job_input, dict):
            raise TypeError("input must be a JSON object.")
        input_json = self._json(job_input, self.max_input_bytes, "input")
        job_id = uuid.uuid4().hex
        with self._connection(write=True) as connection:
            now = self._now()
            connection.execute(
                "INSERT INTO jobs(job_id,kind,input_json,status,created_at,updated_at) VALUES (?,?,?,'queued',?,?)",
                (job_id, kind, input_json, now, now),
            )
            self._event(connection, job_id, "created", {"kind": kind}, now)
        return {"job_id": job_id, "kind": kind, "input": job_input, "status": "queued", "progress": 0, "created_at": now}

    def _list(self, payload: dict[str, Any]) -> dict[str, Any]:
        limit = self._limit(payload.get("limit"), default=50, maximum=100)
        status = payload.get("status")
        query = "SELECT job_id,parent_job_id,kind,status,progress,worker_id,error,created_at,updated_at FROM jobs"
        values: list[Any] = []
        if status is not None:
            if status not in {"queued", "running", "cancel_requested", *self.terminal_statuses}:
                raise ValueError("status is not a known job state.")
            query += " WHERE status=?"
            values.append(status)
        query += " ORDER BY updated_at DESC LIMIT ?"
        values.append(limit)
        with self._connection() as connection:
            rows = connection.execute(query, values).fetchall()
        return {"jobs": [dict(row) for row in rows]}

    def _get(self, payload: dict[str, Any]) -> dict[str, Any]:
        job_id = self._job_id(payload.get("job_id"))
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if row is None:
                raise JobNotFoundError("Job was not found.")
            events = connection.execute(
                "SELECT event_id,event,detail_json,created_at FROM job_events WHERE job_id=? ORDER BY event_id",
                (job_id,),
            ).fetchall()
        job = dict(row)
        job["input"] = json.loads(job.pop("input_json"))
        job["result"] = json.loads(job.pop("result_json"))
        job["events"] = [
            {"event_id": event["event_id"], "event": event["event"], "detail": json.loads(event["detail_json"]), "created_at": event["created_at"]}
            for event in events
        ]
        return {"job": job}

    def _claim(self, payload: dict[str, Any]) -> dict[str, Any]:
        job_id = self._job_id(payload.get("job_id"))
        worker_id = self._text(payload.get("worker_id"), "worker_id", 100)
        with self._connection(write=True) as connection:
            now = self._now()
            job = self._job(connection, job_id)
            if job["status"] != "queued":
                raise ValueError("Only queued jobs can be claimed.")
            connection.execute(
                "UPDATE jobs SET status='running',worker_id=?,updated_at=? WHERE job_id=?",
                (worker_id, now, job_id),
            )
            self._event(connection, job_id, "claimed", {"worker_id": worker_id}, now)
        return {"job_id": job_id, "status": "running", "worker_id": worker_id, "updated_at": now}

    def _heartbeat(self, payload: dict[str, Any]) -> dict[str, Any]:
        job_id = self._job_id(payload.get("job_id"))
        worker_id = self._text(payload.get("worker_id"), "worker_id", 100)
        with self._connection(write=True) as connection:
            job = self._job(connection, job_id)
            if job["worker_id"] != worker_id:
                raise ValueError("Job is owned by a different worker.")
            if job["status"] not in self.terminal_statuses:
                self._owned_job(connection, job_id, worker_id)
                connection.execute(
                    "UPDATE jobs SET updated_at=? WHERE job_id=? AND worker_id=? "
                    "AND status IN ('running','cancel_requested')",
                    (self._now(), job_id, worker_id),
                )
            job = self._job(connection, job_id)
        return {"job_id": job_id, "status": job["status"], "updated_at": job["updated_at"]}

    def _progress(self, payload: dict[str, Any]) -> dict[str, Any]:
        job_id = self._job_id(payload.get("job_id"))
        worker_id = self._text(payload.get("worker_id"), "worker_id", 100)
        progress = payload.get("progress")
        if isinstance(progress, bool) or not isinstance(progress, int) or not 0 <= progress <= 99:
            raise ValueError("progress must be an integer from 0 to 99; use complete for 100.")
        message = payload.get("message", "")
        if not isinstance(message, str) or len(message) > 500:
            raise ValueError("message must be a string up to 500 characters.")
        with self._connection(write=True) as connection:
            now = self._now()
            job = self._owned_job(connection, job_id, worker_id)
            if job["status"] == "cancel_requested":
                connection.execute(
                    "UPDATE jobs SET status='cancelled',updated_at=? WHERE job_id=?",
                    (now, job_id),
                )
                self._event(connection, job_id, "cancelled", {"worker_id": worker_id, "observed_by_worker": True}, now)
                return {"job_id": job_id, "status": "cancelled", "progress": job["progress"], "updated_at": now}
            if progress < job["progress"]:
                raise ValueError("progress cannot move backwards.")
            connection.execute("UPDATE jobs SET progress=?,updated_at=? WHERE job_id=?", (progress, now, job_id))
            self._event(connection, job_id, "progress", {"progress": progress, "message": message}, now)
        return {"job_id": job_id, "status": "running", "progress": progress, "updated_at": now}

    def _complete(self, payload: dict[str, Any]) -> dict[str, Any]:
        job_id = self._job_id(payload.get("job_id"))
        worker_id = self._text(payload.get("worker_id"), "worker_id", 100)
        result = payload.get("result")
        result_json = self._json(result, self.max_result_bytes, "result")
        with self._connection(write=True) as connection:
            now = self._now()
            job = self._owned_job(connection, job_id, worker_id)
            if job["status"] == "cancel_requested":
                connection.execute("UPDATE jobs SET status='cancelled',updated_at=? WHERE job_id=?", (now, job_id))
                self._event(connection, job_id, "cancelled", {"worker_id": worker_id, "observed_by_worker": True}, now)
                return {"job_id": job_id, "status": "cancelled", "updated_at": now}
            connection.execute(
                "UPDATE jobs SET status='succeeded',progress=100,result_json=?,updated_at=? WHERE job_id=?",
                (result_json, now, job_id),
            )
            self._event(connection, job_id, "completed", {"result": json.loads(result_json)}, now)
        return {"job_id": job_id, "status": "succeeded", "progress": 100, "updated_at": now}

    def _fail(self, payload: dict[str, Any]) -> dict[str, Any]:
        job_id = self._job_id(payload.get("job_id"))
        worker_id = self._text(payload.get("worker_id"), "worker_id", 100)
        error = payload.get("error")
        if not isinstance(error, str) or not error.strip() or len(error) > 2_000:
            raise ValueError("error must be a non-empty string up to 2000 characters.")
        with self._connection(write=True) as connection:
            now = self._now()
            job = self._owned_job(connection, job_id, worker_id)
            if job["status"] == "cancel_requested":
                connection.execute("UPDATE jobs SET status='cancelled',updated_at=? WHERE job_id=?", (now, job_id))
                self._event(connection, job_id, "cancelled", {"worker_id": worker_id, "observed_by_worker": True}, now)
                return {"job_id": job_id, "status": "cancelled", "updated_at": now}
            connection.execute("UPDATE jobs SET status='failed',error=?,updated_at=? WHERE job_id=?", (error, now, job_id))
            self._event(connection, job_id, "failed", {"error": error}, now)
        return {"job_id": job_id, "status": "failed", "error": error, "updated_at": now}

    def _cancel(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("approved") is not True:
            raise JobApprovalRequired("Cancelling a background job requires approved=true.")
        job_id = self._job_id(payload.get("job_id"))
        with self._connection(write=True) as connection:
            now = self._now()
            job = self._job(connection, job_id)
            if job["status"] == "queued":
                status = "cancelled"
            elif job["status"] == "running":
                status = "cancel_requested"
            elif job["status"] == "cancel_requested":
                return {"job_id": job_id, "status": "cancel_requested", "updated_at": job["updated_at"]}
            else:
                raise ValueError("Terminal jobs cannot be cancelled.")
            connection.execute("UPDATE jobs SET status=?,updated_at=? WHERE job_id=?", (status, now, job_id))
            self._event(connection, job_id, status, {"approved": True}, now)
        return {"job_id": job_id, "status": status, "updated_at": now}

    def _retry(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("approved") is not True:
            raise JobApprovalRequired("Retrying a background job requires approved=true.")
        parent_id = self._job_id(payload.get("job_id"))
        job_id = uuid.uuid4().hex
        with self._connection(write=True) as connection:
            now = self._now()
            parent = self._job(connection, parent_id)
            if parent["status"] not in {"failed", "cancelled"}:
                raise ValueError("Only failed or cancelled jobs can be retried.")
            connection.execute(
                "INSERT INTO jobs(job_id,parent_job_id,kind,input_json,status,created_at,updated_at) "
                "VALUES (?,?,?,?, 'queued',?,?)",
                (job_id, parent_id, parent["kind"], parent["input_json"], now, now),
            )
            self._event(connection, job_id, "retry_created", {"parent_job_id": parent_id}, now)
            self._event(connection, parent_id, "retried_as", {"job_id": job_id}, now)
        return {"job_id": job_id, "parent_job_id": parent_id, "kind": parent["kind"], "status": "queued", "progress": 0, "created_at": now}

    @staticmethod
    def _stale_window(payload: dict[str, Any]) -> tuple[int, str, str]:
        lease_seconds = payload.get("stale_after_seconds", 900)
        if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int):
            raise TypeError("stale_after_seconds must be an integer.")
        lease_seconds = max(60, min(lease_seconds, 604_800))
        now = datetime.now(UTC)
        cutoff = (now - timedelta(seconds=lease_seconds)).isoformat(timespec="seconds")
        now_text = now.isoformat(timespec="seconds")
        return lease_seconds, cutoff, now_text

    @staticmethod
    def _stale_jobs(connection: sqlite3.Connection, cutoff: str, limit: int | None = None) -> list[sqlite3.Row]:
        query = (
            "SELECT job_id,kind,status,progress,worker_id,updated_at,COUNT(*) OVER () AS candidate_count FROM jobs "
            "WHERE status IN ('running','cancel_requested') AND updated_at < ? ORDER BY updated_at,job_id"
        )
        parameters: list[Any] = [cutoff]
        if limit is not None:
            query += " LIMIT ?"
            parameters.append(limit)
        return connection.execute(query, parameters).fetchall()

    def _recovery_candidates(self, payload: dict[str, Any]) -> dict[str, Any]:
        lease_seconds, cutoff, now_text = self._stale_window(payload)
        limit = self._limit(payload.get("limit"), default=50, maximum=100)
        with self._connection() as connection:
            rows = self._stale_jobs(connection, cutoff, limit)
        candidates = [
            {key: row[key] for key in ("job_id", "kind", "status", "progress", "worker_id", "updated_at")}
            | {"recovery_status": "cancelled" if row["status"] == "cancel_requested" else "failed"}
            for row in rows
        ]
        return {
            "candidate_count": rows[0]["candidate_count"] if rows else 0,
            "lease_seconds": lease_seconds, "cutoff": cutoff, "observed_at": now_text, "jobs": candidates,
        }

    def _recover_stale(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("approved") is not True:
            raise JobApprovalRequired("Recovering stale jobs requires approved=true.")
        lease_seconds, cutoff, now_text = self._stale_window(payload)
        recovered: list[dict[str, str]] = []
        with self._connection(write=True) as connection:
            jobs = self._stale_jobs(connection, cutoff)
            for job in jobs:
                if job["status"] == "cancel_requested":
                    status = "cancelled"
                    event = "cancelled"
                    detail = {"reason": "Cancellation completed during stale-job recovery."}
                else:
                    status = "failed"
                    event = "lease_expired"
                    detail = {
                        "reason": "Worker lease expired; job was not automatically retried.",
                        "worker_id": job["worker_id"],
                    }
                    connection.execute(
                        "UPDATE jobs SET status='failed',error=?,updated_at=? WHERE job_id=?",
                        (detail["reason"], now_text, job["job_id"]),
                    )
                if status == "cancelled":
                    connection.execute(
                        "UPDATE jobs SET status='cancelled',updated_at=? WHERE job_id=?",
                        (now_text, job["job_id"]),
                    )
                self._event(connection, job["job_id"], event, detail, now_text)
                recovered.append({"job_id": job["job_id"], "status": status})
        return {"recovered_count": len(recovered), "lease_seconds": lease_seconds, "jobs": recovered}

    def _record_memory(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("approved") is not True:
            raise JobApprovalRequired("Recording a research memory requires approved=true.")
        job_id = self._job_id(payload.get("job_id"))
        memory_id = payload.get("memory_id")
        if isinstance(memory_id, bool) or not isinstance(memory_id, int) or memory_id <= 0:
            raise ValueError("memory_id must be a positive integer.")
        with self._connection(write=True) as connection:
            now = self._now()
            job = self._job(connection, job_id)
            if job["status"] != "succeeded" or job["kind"] not in {"research", "github_research"}:
                raise ValueError("Only completed research jobs can be saved to memory.")
            events = connection.execute(
                "SELECT detail_json FROM job_events WHERE job_id=? AND event='memory_saved' ORDER BY event_id",
                (job_id,),
            ).fetchall()
            if events:
                detail = json.loads(events[0]["detail_json"])
                return {"job_id": job_id, "memory_id": detail["memory_id"], "saved": True, "already_saved": True}
            self._event(connection, job_id, "memory_saved", {"memory_id": memory_id}, now)
            connection.execute("UPDATE jobs SET updated_at=? WHERE job_id=?", (now, job_id))
        return {"job_id": job_id, "memory_id": memory_id, "saved": True, "already_saved": False}

    def _job(self, connection: sqlite3.Connection, job_id: str) -> sqlite3.Row:
        job = connection.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if job is None:
            raise JobNotFoundError("Job was not found.")
        return job

    def _owned_job(self, connection: sqlite3.Connection, job_id: str, worker_id: str) -> sqlite3.Row:
        job = self._job(connection, job_id)
        if job["worker_id"] != worker_id:
            raise ValueError("Job is owned by a different worker.")
        if job["status"] not in {"running", "cancel_requested"}:
            raise ValueError("Job is not running.")
        return job

    def _event(self, connection: sqlite3.Connection, job_id: str, event: str, detail: dict[str, Any], created_at: str) -> None:
        connection.execute(
            "INSERT INTO job_events(job_id,event,detail_json,created_at) VALUES (?,?,?,?)",
            (job_id, event, json.dumps(detail, ensure_ascii=False), created_at),
        )
        connection.execute(
            "DELETE FROM job_events WHERE job_id=? AND event_id NOT IN "
            "(SELECT event_id FROM job_events WHERE job_id=? ORDER BY event_id DESC LIMIT ?)",
            (job_id, job_id, self.max_events),
        )

    @staticmethod
    def _job_id(value: Any) -> str:
        if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{32}", value):
            raise ValueError("job_id must be a valid job identifier.")
        return value

    @staticmethod
    def _text(value: Any, key: str, max_length: int) -> str:
        if not isinstance(value, str) or not value.strip() or len(value) > max_length:
            raise ValueError(f"{key} must be a non-empty string up to {max_length} characters.")
        return value.strip()

    @staticmethod
    def _json(value: Any, max_bytes: int, key: str) -> str:
        try:
            result = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be JSON serializable.") from exc
        if len(result.encode("utf-8")) > max_bytes:
            raise ValueError(f"{key} exceeds the {max_bytes}-byte limit.")
        return result

    @staticmethod
    def _limit(value: Any, default: int, maximum: int) -> int:
        if value is None:
            return default
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("limit must be an integer.")
        return max(1, min(value, maximum))

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat(timespec="seconds")