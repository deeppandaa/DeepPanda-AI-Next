from __future__ import annotations

import asyncio
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from app.main import create_app
from app.plugins.gateway import PluginGateway
from app.plugins.jobs import JobApprovalRequired, JobsPlugin


class JobsPluginTests(unittest.TestCase):
    def test_stale_worker_recovery_requires_approval_and_closes_orphaned_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plugin = JobsPlugin(Path(directory) / "jobs.db")

            async def exercise() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
                running = await plugin.invoke("create", {"kind": "research", "input": {}, "approved": True})
                await plugin.invoke("claim", {"job_id": running["job_id"], "worker_id": "worker-a"})
                cancellation = await plugin.invoke("create", {"kind": "media", "input": {}, "approved": True})
                await plugin.invoke("claim", {"job_id": cancellation["job_id"], "worker_id": "worker-b"})
                await plugin.invoke("cancel", {"job_id": cancellation["job_id"], "approved": True})
                stale_time = (datetime.now(UTC) - timedelta(hours=1)).isoformat(timespec="seconds")
                with plugin._connection() as connection:
                    connection.execute("UPDATE jobs SET updated_at=?", (stale_time,))
                with self.assertRaises(JobApprovalRequired):
                    await plugin.invoke("recover_stale", {"stale_after_seconds": 60})
                recovered = await plugin.invoke("recover_stale", {
                    "stale_after_seconds": 60,
                    "approved": True,
                })
                failed_job = await plugin.invoke("get", {"job_id": running["job_id"]})
                cancelled_job = await plugin.invoke("get", {"job_id": cancellation["job_id"]})
                return recovered, failed_job, cancelled_job

            recovered, failed_job, cancelled_job = asyncio.run(exercise())

        self.assertEqual(recovered["recovered_count"], 2)
        self.assertEqual(failed_job["job"]["status"], "failed")
        self.assertEqual(failed_job["job"]["events"][-1]["event"], "lease_expired")
        self.assertEqual(cancelled_job["job"]["status"], "cancelled")
        self.assertEqual(cancelled_job["job"]["events"][-1]["event"], "cancelled")

    def test_api_approval_and_gateway_routes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plugin = JobsPlugin(Path(directory) / "jobs.db")
            gateway = PluginGateway()
            gateway.register(plugin)
            app = create_app(gateway)

            async def exercise_api() -> tuple[httpx.Response, httpx.Response, httpx.Response, httpx.Response, httpx.Response, httpx.Response]:
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    denied = await client.post(
                        "/api/plugins/jobs/actions/create",
                        json={"payload": {"kind": "research", "input": {}}},
                    )
                    created = await client.post(
                        "/api/plugins/jobs/actions/create",
                        json={"payload": {"kind": "research", "input": {"query": "local"}, "approved": True}},
                    )
                    job_id = created.json()["job_id"]
                    unapproved_cancel = await client.post(
                        "/api/plugins/jobs/actions/cancel",
                        json={"payload": {"job_id": job_id}},
                    )
                    unapproved_recovery = await client.post(
                        "/api/plugins/jobs/actions/recover_stale",
                        json={"payload": {"stale_after_seconds": 60}},
                    )
                    recovery = await client.post(
                        "/api/plugins/jobs/actions/recover_stale",
                        json={"payload": {"stale_after_seconds": 60, "approved": True}},
                    )
                    listed = await client.post(
                        "/api/plugins/jobs/actions/list",
                        json={"payload": {"limit": 10}},
                    )
                    return denied, created, unapproved_cancel, unapproved_recovery, recovery, listed

            denied, created, unapproved_cancel, unapproved_recovery, recovery, listed = asyncio.run(exercise_api())

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(created.status_code, 200)
        self.assertEqual(unapproved_cancel.status_code, 403)
        self.assertEqual(unapproved_recovery.status_code, 403)
        self.assertEqual(recovery.json()["recovered_count"], 0)
        self.assertEqual(listed.json()["jobs"][0]["job_id"], created.json()["job_id"])

    def test_create_requires_approval_and_persists_across_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "jobs.db"
            plugin = JobsPlugin(database_path)
            with self.assertRaises(JobApprovalRequired):
                asyncio.run(plugin.invoke("create", {"kind": "research", "input": {"question": "local"}}))

            created = asyncio.run(plugin.invoke("create", {
                "kind": "research",
                "input": {"question": "local sources"},
                "approved": True,
            }))
            restored = asyncio.run(JobsPlugin(database_path).invoke("get", {"job_id": created["job_id"]}))

        self.assertEqual(restored["job"]["status"], "queued")
        self.assertEqual(restored["job"]["input"], {"question": "local sources"})
        self.assertEqual(restored["job"]["events"][0]["event"], "created")

    def test_worker_claim_progress_and_completion_are_audited(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plugin = JobsPlugin(Path(directory) / "jobs.db")

            async def exercise() -> dict[str, object]:
                job = await plugin.invoke("create", {"kind": "media", "input": {}, "approved": True})
                started = await plugin.invoke("claim", {"job_id": job["job_id"], "worker_id": "worker-a"})
                progress = await plugin.invoke("progress", {
                    "job_id": job["job_id"],
                    "worker_id": "worker-a",
                    "progress": 40,
                    "message": "Extracted audio",
                })
                completed = await plugin.invoke("complete", {
                    "job_id": job["job_id"],
                    "worker_id": "worker-a",
                    "result": {"artifact": "audio.wav"},
                })
                return started, progress, completed, await plugin.invoke("get", {"job_id": job["job_id"]})

            started, progress, completed, restored = asyncio.run(exercise())

        self.assertEqual(started["status"], "running")
        self.assertEqual(progress["progress"], 40)
        self.assertEqual(completed["status"], "succeeded")
        self.assertEqual(restored["job"]["result"], {"artifact": "audio.wav"})
        self.assertEqual([event["event"] for event in restored["job"]["events"]], [
            "created", "claimed", "progress", "completed",
        ])

    def test_running_job_cancel_is_observed_by_worker_and_retry_is_new_job(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plugin = JobsPlugin(Path(directory) / "jobs.db")

            async def exercise() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
                job = await plugin.invoke("create", {"kind": "research", "input": {"q": "x"}, "approved": True})
                await plugin.invoke("claim", {"job_id": job["job_id"], "worker_id": "worker-a"})
                requested = await plugin.invoke("cancel", {"job_id": job["job_id"], "approved": True})
                observed = await plugin.invoke("progress", {
                    "job_id": job["job_id"],
                    "worker_id": "worker-a",
                    "progress": 50,
                    "message": "Cancellation observed",
                })
                retry = await plugin.invoke("retry", {"job_id": job["job_id"], "approved": True})
                return requested, observed, retry

            requested, observed, retry = asyncio.run(exercise())

        self.assertEqual(requested["status"], "cancel_requested")
        self.assertEqual(observed["status"], "cancelled")
        self.assertEqual(retry["status"], "queued")
        self.assertNotEqual(retry["job_id"], requested["job_id"])
        self.assertEqual(retry["parent_job_id"], requested["job_id"])

    def test_progress_requires_worker_ownership_and_is_monotonic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plugin = JobsPlugin(Path(directory) / "jobs.db")

            async def exercise() -> None:
                job = await plugin.invoke("create", {"kind": "media", "input": {}, "approved": True})
                await plugin.invoke("claim", {"job_id": job["job_id"], "worker_id": "worker-a"})
                with self.assertRaises(ValueError):
                    await plugin.invoke("progress", {
                        "job_id": job["job_id"],
                        "worker_id": "worker-b",
                        "progress": 20,
                    })
                await plugin.invoke("progress", {
                    "job_id": job["job_id"],
                    "worker_id": "worker-a",
                    "progress": 30,
                })
                with self.assertRaises(ValueError):
                    await plugin.invoke("progress", {
                        "job_id": job["job_id"],
                        "worker_id": "worker-a",
                        "progress": 20,
                    })

            asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()