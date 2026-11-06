from __future__ import annotations

import json
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


class TaskApprovalRequired(Exception):
    pass


class TaskNotFoundError(Exception):
    pass


class TasksPlugin:
    manifest = PluginManifest(
        plugin_id="tasks",
        display_name="Coding Task Plans",
        description="Onaylı görev planları, adım evidence'ı ve yerel audit geçmişi.",
        actions=(
            "create",
            "list",
            "get",
            "approve",
            "update_step",
            "record_workspace_write",
            "record_workspace_rollback",
            "record_test_run",
            "verify",
        ),
    )

    step_statuses: ClassVar[frozenset[str]] = frozenset({"pending", "in_progress", "completed", "blocked"})
    max_steps: ClassVar[int] = 50

    def __init__(self, database_path: str | Path | None = None) -> None:
        if database_path is None:
            data_root = Path(os.getenv("AI_DATA_DIR", "/data")).expanduser()
            database_path = data_root / "tasks.db"
        self.database_path = Path(database_path).expanduser().resolve()

    async def invoke(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "create":
            return self._create(payload)
        if action == "list":
            return self._list(payload)
        if action == "get":
            return self._get(payload)
        if action == "approve":
            return self._approve(payload)
        if action == "update_step":
            return self._update_step(payload)
        if action == "record_workspace_write":
            return self._record_workspace_write(payload)
        if action == "record_workspace_rollback":
            return self._record_workspace_rollback(payload)
        if action == "record_test_run":
            return self._record_test_run(payload)
        if action == "verify":
            return self._verify(payload)
        raise ValueError(f"Unsupported tasks action: {action}")

    def _connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS task_records (
                task_id TEXT PRIMARY KEY,
                request TEXT NOT NULL,
                intent TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL CHECK(status IN ('plan_only', 'approved', 'in_progress', 'completed', 'blocked')),
                approved INTEGER NOT NULL DEFAULT 0 CHECK(approved IN (0, 1)),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS task_steps (
                task_id TEXT NOT NULL REFERENCES task_records(task_id) ON DELETE CASCADE,
                step_index INTEGER NOT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending', 'in_progress', 'completed', 'blocked')),
                evidence TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL,
                PRIMARY KEY(task_id, step_index)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS task_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL REFERENCES task_records(task_id) ON DELETE CASCADE,
                step_index INTEGER,
                action TEXT NOT NULL,
                detail TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_task_records_updated ON task_records(updated_at)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_task_events_task ON task_events(task_id, event_id)")
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

    def _create(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = self._text(payload.get("request"), "request", 20_000)
        raw_steps = payload.get("steps")
        if not isinstance(raw_steps, list) or not raw_steps or len(raw_steps) > self.max_steps:
            raise ValueError(f"steps must contain 1 to {self.max_steps} items.")
        steps = [self._text(step, f"steps[{index}]", 300) for index, step in enumerate(raw_steps)]
        intent = payload.get("intent", "coding")
        if not isinstance(intent, str) or len(intent) > 80:
            raise ValueError("intent must be a string up to 80 characters.")

        task_id = uuid.uuid4().hex
        now = self._now()
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO task_records(task_id, request, intent, status, approved, created_at, updated_at) "
                "VALUES (?, ?, ?, 'plan_only', 0, ?, ?)",
                (task_id, request, intent.strip(), now, now),
            )
            connection.executemany(
                "INSERT INTO task_steps(task_id, step_index, title, status, updated_at) "
                "VALUES (?, ?, ?, 'pending', ?)",
                [(task_id, index, title, now) for index, title in enumerate(steps)],
            )
            self._event(connection, task_id, None, "plan_created", {"steps": len(steps)}, now)
        return {"task_id": task_id, "request": request, "intent": intent.strip(), "status": "plan_only", "approved": False, "steps": steps, "created_at": now}

    def _list(self, payload: dict[str, Any]) -> dict[str, Any]:
        limit = self._limit(payload.get("limit"), default=50, maximum=100)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT t.task_id,t.request,t.intent,t.status,t.approved,t.created_at,t.updated_at,"
                "COUNT(s.step_index) AS step_count,"
                "SUM(CASE WHEN s.status='completed' THEN 1 ELSE 0 END) AS completed_steps "
                "FROM task_records t LEFT JOIN task_steps s ON s.task_id=t.task_id "
                "GROUP BY t.task_id ORDER BY t.updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return {"tasks": [dict(row) for row in rows]}

    def _get(self, payload: dict[str, Any]) -> dict[str, Any]:
        task_id = self._task_id(payload.get("task_id"))
        with self._connection() as connection:
            task = connection.execute("SELECT * FROM task_records WHERE task_id = ?", (task_id,)).fetchone()
            if task is None:
                raise TaskNotFoundError("Task was not found.")
            steps = connection.execute(
                "SELECT step_index,title,status,evidence,updated_at FROM task_steps "
                "WHERE task_id = ? ORDER BY step_index",
                (task_id,),
            ).fetchall()
            events = connection.execute(
                "SELECT event_id,step_index,action,detail,created_at FROM task_events "
                "WHERE task_id = ? ORDER BY event_id",
                (task_id,),
            ).fetchall()
        task_data = dict(task)
        task_data["approved"] = bool(task_data["approved"])
        task_data["steps"] = [dict(row) for row in steps]
        task_data["events"] = [{**dict(row), "detail": json.loads(row["detail"])} for row in events]
        return {"task": task_data}

    def _approve(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("approved") is not True:
            raise TaskApprovalRequired("Approving a task plan requires approved=true.")
        task_id = self._task_id(payload.get("task_id"))
        now = self._now()
        with self._connection() as connection:
            task = connection.execute("SELECT status,approved FROM task_records WHERE task_id = ?", (task_id,)).fetchone()
            if task is None:
                raise TaskNotFoundError("Task was not found.")
            if task["status"] != "plan_only":
                raise ValueError("Only a plan awaiting approval can be approved.")
            connection.execute(
                "UPDATE task_records SET status='approved',approved=1,updated_at=? WHERE task_id=?",
                (now, task_id),
            )
            self._event(connection, task_id, None, "plan_approved", {}, now)
        return {"task_id": task_id, "status": "approved", "approved": True, "updated_at": now}

    def _update_step(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("approved") is not True:
            raise TaskApprovalRequired("Updating a task step requires approved=true.")
        task_id = self._task_id(payload.get("task_id"))
        step_index = payload.get("step_index")
        if isinstance(step_index, bool) or not isinstance(step_index, int) or step_index < 0:
            raise ValueError("step_index must be a non-negative integer.")
        status = payload.get("status")
        if not isinstance(status, str) or status not in self.step_statuses:
            raise ValueError("status must be pending, in_progress, completed, or blocked.")
        evidence = payload.get("evidence", "")
        if not isinstance(evidence, str) or len(evidence) > 1_000:
            raise ValueError("evidence must be a string up to 1000 characters.")
        evidence = evidence.strip()
        if status in {"completed", "blocked"} and not evidence:
            raise ValueError(f"evidence is required when a step is {status}.")

        now = self._now()
        with self._connection() as connection:
            task = connection.execute("SELECT approved,status FROM task_records WHERE task_id = ?", (task_id,)).fetchone()
            if task is None:
                raise TaskNotFoundError("Task was not found.")
            if not task["approved"]:
                raise TaskApprovalRequired("The task plan must be approved before updating its steps.")
            if task["status"] == "completed":
                raise ValueError("A closed task cannot be updated.")
            step = connection.execute(
                "SELECT title,status FROM task_steps WHERE task_id=? AND step_index=?",
                (task_id, step_index),
            ).fetchone()
            if step is None:
                raise TaskNotFoundError("Task step was not found.")
            allowed_transitions = {
                "pending": {"in_progress", "blocked"},
                "in_progress": {"completed", "blocked"},
                "blocked": {"in_progress"},
                "completed": set(),
            }
            if status not in allowed_transitions[step["status"]]:
                raise ValueError(f"Invalid task step transition: {step['status']} -> {status}.")
            connection.execute(
                "UPDATE task_steps SET status=?,evidence=?,updated_at=? WHERE task_id=? AND step_index=?",
                (status, evidence, now, task_id, step_index),
            )
            remaining = connection.execute(
                "SELECT status FROM task_steps WHERE task_id=? ORDER BY step_index",
                (task_id,),
            ).fetchall()
            task_status = self._task_status([row["status"] for row in remaining])
            connection.execute(
                "UPDATE task_records SET status=?,updated_at=? WHERE task_id=?",
                (task_status, now, task_id),
            )
            self._event(connection, task_id, step_index, "step_updated", {"status": status, "evidence": evidence}, now)
        return {
            "task_id": task_id,
            "step_index": step_index,
            "title": step["title"],
            "status": status,
            "evidence": evidence,
            "task_status": task_status,
            "updated_at": now,
        }

    def _record_workspace_write(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("approved") is not True:
            raise TaskApprovalRequired("Recording a workspace write requires approved=true.")
        task_id = self._task_id(payload.get("task_id"))
        step_index = self._step_index(payload.get("step_index"))
        backup_id = self._backup_id(payload.get("backup_id"))
        path = self._text(payload.get("path"), "path", 500)
        now = self._now()
        with self._connection() as connection:
            task = connection.execute("SELECT approved FROM task_records WHERE task_id=?", (task_id,)).fetchone()
            if task is None:
                raise TaskNotFoundError("Task was not found.")
            if not task["approved"]:
                raise TaskApprovalRequired("The task plan must be approved before recording workspace writes.")
            step = connection.execute(
                "SELECT status FROM task_steps WHERE task_id=? AND step_index=?",
                (task_id, step_index),
            ).fetchone()
            if step is None:
                raise TaskNotFoundError("Task step was not found.")
            if step["status"] != "in_progress":
                raise ValueError("Workspace writes can only be attached to an in-progress task step.")
            existing = connection.execute(
                "SELECT detail FROM task_events WHERE task_id=? AND action='workspace_write'",
                (task_id,),
            ).fetchall()
            if any(json.loads(row["detail"]).get("backup_id") == backup_id for row in existing):
                raise ValueError("This workspace backup is already attached to the task.")
            detail = {"backup_id": backup_id, "path": path}
            self._event(connection, task_id, step_index, "workspace_write", detail, now)
            connection.execute("UPDATE task_records SET updated_at=? WHERE task_id=?", (now, task_id))
        return {"task_id": task_id, "step_index": step_index, **detail, "recorded": True, "created_at": now}

    def _record_workspace_rollback(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("approved") is not True:
            raise TaskApprovalRequired("Recording a workspace rollback requires approved=true.")
        task_id = self._task_id(payload.get("task_id"))
        backup_id = self._backup_id(payload.get("backup_id"))
        now = self._now()
        with self._connection() as connection:
            task = connection.execute("SELECT approved FROM task_records WHERE task_id=?", (task_id,)).fetchone()
            if task is None:
                raise TaskNotFoundError("Task was not found.")
            if not task["approved"]:
                raise TaskApprovalRequired("The task plan must be approved before recording a rollback.")
            events = connection.execute(
                "SELECT action,step_index,detail FROM task_events WHERE task_id=? "
                "AND action IN ('workspace_write','workspace_rollback')",
                (task_id,),
            ).fetchall()
            write = None
            already_rolled_back = False
            for event in events:
                detail = json.loads(event["detail"])
                if detail.get("backup_id") != backup_id:
                    continue
                if event["action"] == "workspace_write":
                    write = event
                elif event["action"] == "workspace_rollback":
                    already_rolled_back = True
            if write is None:
                raise ValueError("Workspace backup is not recorded on this task.")
            if already_rolled_back:
                raise ValueError("This task backup is already marked as rolled back.")
            detail = json.loads(write["detail"])
            rollback_detail = {"backup_id": backup_id, "path": detail["path"]}
            self._event(connection, task_id, write["step_index"], "workspace_rollback", rollback_detail, now)
            connection.execute("UPDATE task_records SET updated_at=? WHERE task_id=?", (now, task_id))
        return {
            "task_id": task_id,
            "step_index": write["step_index"],
            **rollback_detail,
            "recorded": True,
            "created_at": now,
        }

    def _record_test_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("approved") is not True:
            raise TaskApprovalRequired("Recording a test run requires approved=true.")
        task_id = self._task_id(payload.get("task_id"))
        step_index = self._step_index(payload.get("step_index"))
        command = payload.get("command")
        if (
            not isinstance(command, list)
            or not command
            or len(command) > 20
            or any(not isinstance(part, str) or not part.strip() or len(part) > 500 for part in command)
        ):
            raise ValueError("command must contain 1 to 20 non-empty strings up to 500 characters each.")
        passed = payload.get("passed")
        if not isinstance(passed, bool):
            raise TypeError("passed must be a boolean.")
        returncode = payload.get("returncode")
        if isinstance(returncode, bool) or not isinstance(returncode, int):
            raise TypeError("returncode must be an integer.")
        output = payload.get("output", "")
        if not isinstance(output, str) or len(output) > 4_000:
            raise ValueError("output must be a string up to 4000 characters.")
        now = self._now()
        detail = {"command": command, "passed": passed, "returncode": returncode, "output": output}
        with self._connection() as connection:
            task = connection.execute("SELECT approved FROM task_records WHERE task_id=?", (task_id,)).fetchone()
            if task is None:
                raise TaskNotFoundError("Task was not found.")
            if not task["approved"]:
                raise TaskApprovalRequired("The task plan must be approved before recording test runs.")
            step = connection.execute(
                "SELECT status FROM task_steps WHERE task_id=? AND step_index=?",
                (task_id, step_index),
            ).fetchone()
            if step is None:
                raise TaskNotFoundError("Task step was not found.")
            if step["status"] != "in_progress":
                raise ValueError("Test runs can only be attached to an in-progress task step.")
            self._event(connection, task_id, step_index, "test_run", detail, now)
            connection.execute("UPDATE task_records SET updated_at=? WHERE task_id=?", (now, task_id))
        return {"task_id": task_id, "step_index": step_index, **detail, "recorded": True, "created_at": now}

    def _verify(self, payload: dict[str, Any]) -> dict[str, Any]:
        task = self._get(payload)["task"]
        events = task["events"]
        steps = task["steps"]
        reasons = []
        incomplete_steps = [step["step_index"] for step in steps if step["status"] != "completed"]
        if not task["approved"]:
            reasons.append("Task plan has not been approved.")
        if incomplete_steps:
            reasons.append("One or more task steps are not completed.")

        latest_write_by_backup: dict[str, int] = {}
        rolled_back_backups: set[str] = set()
        test_runs = []
        workspace_change_event_ids = []
        for event in events:
            detail = event["detail"]
            if event["action"] == "workspace_write":
                latest_write_by_backup[detail["backup_id"]] = event["event_id"]
                workspace_change_event_ids.append(event["event_id"])
            elif event["action"] == "workspace_rollback":
                rolled_back_backups.add(detail["backup_id"])
                workspace_change_event_ids.append(event["event_id"])
            elif event["action"] == "test_run":
                test_runs.append(event)

        active_writes = [
            event_id
            for backup_id, event_id in latest_write_by_backup.items()
            if backup_id not in rolled_back_backups
        ]
        passing_runs = [event for event in test_runs if event["detail"].get("passed") is True]
        latest_test = test_runs[-1] if test_runs else None
        latest_passing_run = passing_runs[-1] if passing_runs else None
        requires_tests = task["intent"].casefold() in {"coding", "engineering", "software"} or bool(active_writes)

        if requires_tests and not passing_runs:
            reasons.append("No successful test run is recorded.")
        if latest_test is not None and latest_test["detail"].get("passed") is not True:
            reasons.append("The latest recorded test run failed.")
        latest_workspace_change = max(workspace_change_event_ids) if workspace_change_event_ids else None
        if latest_workspace_change is not None and (
            latest_passing_run is None or latest_passing_run["event_id"] < latest_workspace_change
        ):
            reasons.append("A successful test run after the latest workspace write or rollback is required.")

        return {
            "task_id": task["task_id"],
            "verified": not reasons,
            "reasons": reasons,
            "evidence": {
                "approved": task["approved"],
                "completed_steps": len(steps) - len(incomplete_steps),
                "total_steps": len(steps),
                "incomplete_step_indexes": incomplete_steps,
                "test_run_count": len(test_runs),
                "passing_test_run_count": len(passing_runs),
                "active_workspace_write_count": len(active_writes),
                "latest_passing_test_event_id": latest_passing_run["event_id"] if latest_passing_run else None,
                "latest_workspace_change_event_id": latest_workspace_change,
            },
        }

    @staticmethod
    def _task_status(step_statuses: list[str]) -> str:
        if step_statuses and all(status == "completed" for status in step_statuses):
            return "completed"
        if "blocked" in step_statuses:
            return "blocked"
        if "in_progress" in step_statuses:
            return "in_progress"
        return "approved"

    @staticmethod
    def _event(
        connection: sqlite3.Connection,
        task_id: str,
        step_index: int | None,
        action: str,
        detail: dict[str, Any],
        created_at: str,
    ) -> None:
        connection.execute(
            "INSERT INTO task_events(task_id,step_index,action,detail,created_at) VALUES (?,?,?,?,?)",
            (task_id, step_index, action, json.dumps(detail, ensure_ascii=False), created_at),
        )

    @staticmethod
    def _task_id(value: Any) -> str:
        if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{32}", value):
            raise ValueError("task_id must be a valid task identifier.")
        return value

    @staticmethod
    def _step_index(value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("step_index must be a non-negative integer.")
        return value

    @staticmethod
    def _backup_id(value: Any) -> str:
        if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{32}", value):
            raise ValueError("backup_id must be a valid workspace backup identifier.")
        return value

    @staticmethod
    def _text(value: Any, key: str, max_length: int) -> str:
        if not isinstance(value, str) or not value.strip() or len(value) > max_length:
            raise ValueError(f"{key} must be a non-empty string up to {max_length} characters.")
        return value.strip()

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