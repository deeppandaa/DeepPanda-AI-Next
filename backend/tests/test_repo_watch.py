from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, ClassVar, Self
from unittest.mock import patch

import httpx

from app.main import create_app
from app.plugins.gateway import PluginGateway
from app.plugins.repo_watch import RepoWatchApprovalRequired, RepoWatchPlugin, RepoWatchRateLimitError


class RepoWatchPluginTests(unittest.TestCase):
    def test_add_requires_approval_and_rejects_non_repository_identifiers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plugin = RepoWatchPlugin(Path(directory) / "watch.db")

            async def exercise() -> None:
                with self.assertRaises(RepoWatchApprovalRequired):
                    await plugin.invoke("add", {"repository": "owner/repo"})
                with self.assertRaisesRegex(ValueError, "owner/repository"):
                    await plugin.invoke("add", {"repository": "https://example.com/owner/repo", "approved": True})
                added = await plugin.invoke("add", {"repository": "owner/repo", "approved": True})
                duplicate = await plugin.invoke("add", {"repository": "owner/repo", "approved": True})
                return added, duplicate

            added, duplicate = asyncio.run(exercise())
            listed = asyncio.run(plugin.invoke("list", {}))

        self.assertEqual(len(listed["repositories"]), 1)
        self.assertTrue(added["added"])
        self.assertFalse(duplicate["added"])

    def test_check_returns_public_metadata_and_persists_change_baseline(self) -> None:
        class FakeResponse:
            def __init__(self, value: Any, status_code: int = 200) -> None:
                self.value = value
                self.status_code = status_code
                self.headers: dict[str, str] = {}
                self.content = json.dumps(value).encode()

            def json(self) -> Any:
                return self.value

        class FakeClient:
            request_paths: list[str] = []
            release = {"tag_name": "v1.2", "name": "Stable release"}
            commit = {"sha": "a" * 40, "commit": {"message": "Fix parser\nwith bounds"}}

            def __init__(self, **_: Any) -> None:
                pass

            async def __aenter__(self) -> FakeClient:
                return self

            async def __aexit__(self, *_: Any) -> None:
                return None

            async def get(self, path: str) -> FakeResponse:
                self.request_paths.append(path)
                if path.endswith("/releases/latest"):
                    return FakeResponse(self.release)
                return FakeResponse([self.commit])

        clock_value = datetime(2026, 1, 1, tzinfo=UTC)
        plugin = RepoWatchPlugin(
            Path(tempfile.gettempdir()) / f"repo-watch-{id(self)}.db",
            client_factory=FakeClient,
            clock=lambda: clock_value,
        )

        async def exercise() -> tuple[dict[str, Any], dict[str, Any]]:
            await plugin.invoke("add", {"repository": "owner/repo", "approved": True})
            first = await plugin.invoke("check", {"repository": "owner/repo", "approved": True})
            with self.assertRaises(RepoWatchRateLimitError):
                await plugin.invoke("check", {"repository": "owner/repo", "approved": True})
            return first, await plugin.invoke("list", {})

        try:
            first, listed = asyncio.run(exercise())
        finally:
            plugin.database_path.unlink(missing_ok=True)

        self.assertTrue(first["baseline"])
        self.assertFalse(first["release_changed"])
        self.assertFalse(first["commit_changed"])
        self.assertEqual(first["release"]["tag"], "v1.2")
        self.assertEqual(first["latest_commit"]["message"], "Fix parser with bounds")
        self.assertEqual(len(FakeClient.request_paths), 2)
        self.assertEqual(listed["repositories"][0]["commit_sha"], "a" * 40)

    def test_hourly_limit_is_persistent_and_blocks_extra_checks(self) -> None:
        class FakeClock:
            value = datetime(2026, 1, 1, tzinfo=UTC)

            def __call__(self) -> datetime:
                return self.value

        class FakeResponse:
            status_code = 200
            headers: ClassVar[dict[str, str]] = {}
            content = b"{}"

            def json(self) -> dict[str, Any]:
                return {"tag_name": "v1", "name": "Release"}

        class FakeClient:
            def __init__(self, **_: Any) -> None:
                pass

            async def __aenter__(self) -> FakeClient:
                return self

            async def __aexit__(self, *_: Any) -> None:
                return None

            async def get(self, path: str) -> FakeResponse:
                if path.endswith("/commits?per_page=1"):
                    response = FakeResponse()
                    response.json = lambda: [{"sha": "b" * 40, "commit": {"message": "Initial"}}]
                    return response
                return FakeResponse()

        with tempfile.TemporaryDirectory() as directory:
            plugin = RepoWatchPlugin(Path(directory) / "watch.db", FakeClient, FakeClock())
            plugin.max_checks_per_hour = 1

            async def exercise() -> None:
                await plugin.invoke("add", {"repository": "owner/one", "approved": True})
                await plugin.invoke("add", {"repository": "owner/two", "approved": True})
                await plugin.invoke("check", {"repository": "owner/one", "approved": True})
                with self.assertRaisesRegex(RepoWatchRateLimitError, "per hour"):
                    await plugin.invoke("check", {"repository": "owner/two", "approved": True})

            asyncio.run(exercise())

    def test_check_reports_release_and_commit_changes(self) -> None:
        class FakeClock:
            value = datetime(2026, 1, 1, tzinfo=UTC)

            def __call__(self) -> datetime:
                return self.value

        class FakeResponse:
            status_code = 200
            headers: dict[str, str] = {}

            def __init__(self, value: Any) -> None:
                self.value = value
                self.content = json.dumps(value).encode()

            def json(self) -> Any:
                return self.value

        class FakeClient:
            release_tag = "v1"
            commit_sha = "a" * 40

            def __init__(self, **_: Any) -> None:
                pass

            async def __aenter__(self) -> FakeClient:
                return self

            async def __aexit__(self, *_: Any) -> None:
                return None

            async def get(self, path: str) -> FakeResponse:
                if path.endswith("/releases/latest"):
                    return FakeResponse({"tag_name": self.release_tag, "name": "Release"})
                return FakeResponse([{"sha": self.commit_sha, "commit": {"message": "Update"}}])

        with tempfile.TemporaryDirectory() as directory:
            clock = FakeClock()
            plugin = RepoWatchPlugin(Path(directory) / "watch.db", FakeClient, clock)

            async def exercise() -> tuple[dict[str, Any], dict[str, Any]]:
                await plugin.invoke("add", {"repository": "owner/repo", "approved": True})
                baseline = await plugin.invoke("check", {"repository": "owner/repo", "approved": True})
                FakeClient.release_tag = "v2"
                FakeClient.commit_sha = "b" * 40
                clock.value += timedelta(seconds=plugin.repo_cooldown_seconds + 1)
                changed = await plugin.invoke("check", {"repository": "owner/repo", "approved": True})
                return baseline, changed

            baseline, changed = asyncio.run(exercise())

        self.assertTrue(baseline["baseline"])
        self.assertTrue(changed["release_changed"])
        self.assertTrue(changed["commit_changed"])
        self.assertEqual(changed["release"]["tag"], "v2")

    def test_api_registers_watcher_and_enforces_approval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            gateway = PluginGateway()
            gateway.register(RepoWatchPlugin(Path(directory) / "watch.db"))
            app = create_app(gateway)

            async def exercise() -> tuple[int, int, int]:
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client:
                    denied = await client.post(
                        "/api/plugins/repo_watch/actions/add",
                        json={"payload": {"repository": "owner/repo"}},
                    )
                    listed = await client.post(
                        "/api/plugins/repo_watch/actions/list", json={"payload": {}}
                    )
                    snapshot_denied = await client.post(
                        "/api/plugins/repo_watch/actions/snapshot_readme",
                        json={"payload": {"repository": "owner/repo"}},
                    )
                    files_denied = await client.post(
                        "/api/plugins/repo_watch/actions/snapshot_files",
                        json={"payload": {"repository": "owner/repo", "paths": ["src/main.ts"]}},
                    )
                    return denied.status_code, listed.status_code, snapshot_denied.status_code, files_denied.status_code

            denied_status, list_status, snapshot_denied_status, files_denied_status = asyncio.run(exercise())

        self.assertEqual(denied_status, 403)
        self.assertEqual(list_status, 200)
        self.assertEqual(snapshot_denied_status, 403)
        self.assertEqual(files_denied_status, 403)

    def test_api_exposes_polling_status_and_requires_approval_to_configure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            gateway = PluginGateway()
            gateway.register(RepoWatchPlugin(Path(directory) / "watch.db"))
            app = create_app(gateway)

            async def exercise() -> tuple[httpx.Response, httpx.Response, httpx.Response]:
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client:
                    status = await client.post(
                        "/api/plugins/repo_watch/actions/polling_status", json={"payload": {}}
                    )
                    denied = await client.post(
                        "/api/plugins/repo_watch/actions/configure_polling",
                        json={"payload": {"enabled": True, "interval_minutes": 15}},
                    )
                    enabled = await client.post(
                        "/api/plugins/repo_watch/actions/configure_polling",
                        json={"payload": {"approved": True, "enabled": True, "interval_minutes": 15}},
                    )
                    return status, denied, enabled

            status, denied, enabled = asyncio.run(exercise())

        self.assertEqual(status.status_code, 200)
        self.assertFalse(status.json()["enabled"])
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(enabled.status_code, 200)
        self.assertTrue(enabled.json()["enabled"])

    def test_readme_snapshot_requires_approval_indexes_source_and_skips_duplicate_blob(self) -> None:
        readme_raw = b"# Local project\n\nDocument this public repository.\n"
        blob_sha = "c" * 40

        class FakeResponse:
            status_code = 200
            headers: dict[str, str] = {}

            def __init__(self) -> None:
                self.value = {
                    "type": "file",
                    "path": "README.md",
                    "sha": blob_sha,
                    "encoding": "base64",
                    "content": base64.b64encode(readme_raw).decode("ascii")[:12] + "\n" + base64.b64encode(readme_raw).decode("ascii")[12:],
                }
                self.content = json.dumps(self.value).encode()

            def json(self) -> dict[str, Any]:
                return self.value

        class FakeClient:
            def __init__(self, **_: Any) -> None:
                pass

            async def __aenter__(self) -> FakeClient:
                return self

            async def __aexit__(self, *_: Any) -> None:
                return None

            async def get(self, path: str) -> FakeResponse:
                if path != "/repos/owner/repo/readme":
                    raise AssertionError(f"Unexpected GitHub request path: {path}")
                return FakeResponse()

        class FakeGateway:
            calls: list[dict[str, Any]] = []

            async def invoke(self, plugin_id: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
                self.calls.append({"plugin_id": plugin_id, "action": action, "payload": payload})
                return {"document_id": "d" * 32, "extracted_characters": 100}

        class FakeClock:
            value = datetime(2026, 1, 1, tzinfo=UTC)

            def __call__(self) -> datetime:
                return self.value

        with tempfile.TemporaryDirectory() as directory:
            gateway = FakeGateway()
            clock = FakeClock()
            plugin = RepoWatchPlugin(
                Path(directory) / "watch.db",
                client_factory=FakeClient,
                clock=clock,
                gateway=gateway,  # type: ignore[arg-type]
            )

            async def exercise() -> tuple[dict[str, Any], dict[str, Any]]:
                await plugin.invoke("add", {"repository": "owner/repo", "approved": True})
                with self.assertRaises(RepoWatchApprovalRequired):
                    await plugin.invoke("snapshot_readme", {"repository": "owner/repo"})
                first = await plugin.invoke("snapshot_readme", {"repository": "owner/repo", "approved": True})
                clock.value += timedelta(seconds=plugin.repo_cooldown_seconds + 1)
                second = await plugin.invoke("snapshot_readme", {"repository": "owner/repo", "approved": True})
                return first, second

            first, second = asyncio.run(exercise())

        self.assertFalse(first["already_indexed"])
        self.assertEqual(first["document_id"], "d" * 32)
        self.assertTrue(first["source_url"].startswith("https://github.com/owner/repo/blob/"))
        self.assertTrue(second["already_indexed"])
        self.assertEqual(len(gateway.calls), 1)
        self.assertEqual(gateway.calls[0]["plugin_id"], "documents")
        payload = gateway.calls[0]["payload"]
        indexed_content = base64.b64decode(payload["content_base64"]).decode("utf-8")
        self.assertIn(first["source_url"], indexed_content)
        self.assertIn(readme_raw.decode(), indexed_content)

    def test_selected_file_snapshot_is_bounded_attributed_and_sha_deduplicated(self) -> None:
        content_by_path = {
            "src/main.ts": b"export const safe = true;\n",
            "package.json": b'{"name":"fixture","scripts":{"test":"vitest run"}}',
        }
        sha_by_path = {path: hashlib.sha1(content).hexdigest() for path, content in content_by_path.items()}

        class FakeClock:
            value = datetime(2026, 1, 1, tzinfo=UTC)

            def __call__(self) -> datetime:
                return self.value

        class FakeResponse:
            status_code = 200
            headers: dict[str, str] = {}

            def __init__(self, path: str) -> None:
                content = content_by_path[path]
                self.value = {
                    "type": "file",
                    "path": path,
                    "sha": sha_by_path[path],
                    "encoding": "base64",
                    "content": base64.b64encode(content).decode("ascii"),
                }
                self.content = json.dumps(self.value).encode()

            def json(self) -> dict[str, Any]:
                return self.value

        class FakeClient:
            def __init__(self, **_: Any) -> None:
                pass

            async def __aenter__(self) -> FakeClient:
                return self

            async def __aexit__(self, *_: Any) -> None:
                return None

            async def get(self, endpoint: str) -> FakeResponse:
                prefix = "/repos/owner/repo/contents/"
                path = endpoint.removeprefix(prefix)
                if path not in content_by_path:
                    raise AssertionError(f"Unexpected GitHub API path: {endpoint}")
                return FakeResponse(path)

        class FakeGateway:
            calls: list[dict[str, Any]] = []

            async def invoke(self, plugin_id: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
                self.calls.append({"plugin_id": plugin_id, "action": action, "payload": payload})
                return {"document_id": f"{len(self.calls):032x}", "extracted_characters": 100}

        with tempfile.TemporaryDirectory() as directory:
            clock = FakeClock()
            gateway = FakeGateway()
            plugin = RepoWatchPlugin(
                Path(directory) / "watch.db",
                client_factory=FakeClient,
                clock=clock,
                gateway=gateway,  # type: ignore[arg-type]
            )

            async def exercise() -> tuple[dict[str, Any], dict[str, Any]]:
                await plugin.invoke("add", {"repository": "owner/repo", "approved": True})
                with self.assertRaisesRegex(ValueError, "traversal"):
                    await plugin.invoke("snapshot_files", {
                        "repository": "owner/repo", "paths": ["../package.json"], "approved": True,
                    })
                with self.assertRaisesRegex(ValueError, "extensions"):
                    await plugin.invoke("snapshot_files", {
                        "repository": "owner/repo", "paths": ["native/installer.exe"], "approved": True,
                    })
                first = await plugin.invoke("snapshot_files", {
                    "repository": "owner/repo",
                    "paths": list(content_by_path),
                    "approved": True,
                })
                clock.value += timedelta(seconds=plugin.repo_cooldown_seconds + 1)
                second = await plugin.invoke("snapshot_files", {
                    "repository": "owner/repo",
                    "paths": list(content_by_path),
                    "approved": True,
                })
                return first, second

            first, second = asyncio.run(exercise())

        self.assertEqual(len(first["indexed_files"]), 2)
        self.assertTrue(all(not item["already_indexed"] for item in first["indexed_files"]))
        self.assertTrue(all(item["already_indexed"] for item in second["indexed_files"]))
        self.assertEqual(len(gateway.calls), 2)
        for call in gateway.calls:
            self.assertEqual(call["plugin_id"], "documents")
            indexed_content = base64.b64decode(call["payload"]["content_base64"]).decode("utf-8")
            self.assertIn("https://github.com/owner/repo/blob/", indexed_content)

    def test_polling_is_disabled_by_default_approved_bounded_and_persistent(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "watch.db"
            plugin = RepoWatchPlugin(database, clock=lambda: now)
            initial = asyncio.run(plugin.invoke("polling_status", {}))

            async def configure() -> dict[str, Any]:
                with self.assertRaises(RepoWatchApprovalRequired):
                    await plugin.invoke("configure_polling", {"enabled": True, "interval_minutes": 15})
                with self.assertRaisesRegex(ValueError, "between"):
                    await plugin.invoke(
                        "configure_polling", {"approved": True, "enabled": True, "interval_minutes": 4}
                    )
                with self.assertRaisesRegex(ValueError, "between"):
                    await plugin.invoke(
                        "configure_polling", {"approved": True, "enabled": True, "interval_minutes": 1441}
                    )
                return await plugin.invoke(
                    "configure_polling", {"approved": True, "enabled": True, "interval_minutes": 15}
                )

            configured = asyncio.run(configure())
            restarted = RepoWatchPlugin(database, clock=lambda: now)
            persisted = asyncio.run(restarted.invoke("polling_status", {}))

        self.assertFalse(initial["enabled"])
        self.assertEqual(initial["interval_minutes"], 60)
        self.assertTrue(configured["enabled"])
        self.assertEqual(configured["next_run_at"], "2026-01-01T00:15:00+00:00")
        self.assertEqual(persisted["interval_minutes"], 15)
        self.assertTrue(persisted["enabled"])

    def test_polling_cycle_checks_only_allowlisted_metadata_and_persists_changes(self) -> None:
        class FakeClock:
            value = datetime(2026, 1, 1, tzinfo=UTC)

            def __call__(self) -> datetime:
                return self.value

        class FakeResponse:
            status_code = 200
            headers: dict[str, str] = {}

            def __init__(self, value: Any) -> None:
                self.value = value
                self.content = json.dumps(value).encode()

            def json(self) -> Any:
                return self.value

        class FakeClient:
            release_tag = "v1"
            commit_sha = "a" * 40
            paths: ClassVar[list[str]] = []

            def __init__(self, **_: Any) -> None:
                pass

            async def __aenter__(self) -> Self:
                return self

            async def __aexit__(self, *_: object) -> None:
                return None

            async def get(self, path: str) -> FakeResponse:
                self.paths.append(path)
                if path.endswith("/releases/latest"):
                    return FakeResponse({"tag_name": self.release_tag, "name": "Release"})
                return FakeResponse([{"sha": self.commit_sha, "commit": {"message": "Update"}}])

        with tempfile.TemporaryDirectory() as directory:
            clock = FakeClock()
            FakeClient.paths.clear()
            plugin = RepoWatchPlugin(Path(directory) / "watch.db", FakeClient, clock)

            async def exercise() -> dict[str, Any]:
                await plugin.invoke("add", {"repository": "owner/repo", "approved": True})
                await plugin.invoke("configure_polling", {
                    "approved": True, "enabled": True, "interval_minutes": 5,
                })
                first = await plugin.run_polling_cycle()
                self.assertEqual(first["last_check_count"], 1)
                FakeClient.release_tag = "v2"
                FakeClient.commit_sha = "b" * 40
                clock.value += timedelta(seconds=plugin.repo_cooldown_seconds + 1)
                return await plugin.run_polling_cycle()

            status = asyncio.run(exercise())

        self.assertEqual(status["last_changes"], ["owner/repo"])
        self.assertEqual(status["last_check_count"], 1)
        self.assertEqual(FakeClient.paths, [
            "/repos/owner/repo/releases/latest",
            "/repos/owner/repo/commits?per_page=1",
            "/repos/owner/repo/releases/latest",
            "/repos/owner/repo/commits?per_page=1",
        ])

    def test_default_app_cancels_polling_worker_and_custom_gateway_skips_it(self) -> None:
        async def exercise() -> None:
            calls = 0
            stopped = asyncio.Event()

            async def fake_worker(_: RepoWatchPlugin) -> None:
                nonlocal calls
                calls += 1
                try:
                    await asyncio.Future()
                finally:
                    stopped.set()

            with patch.object(RepoWatchPlugin, "polling_worker", fake_worker):
                app = create_app()
                async with app.router.lifespan_context(app):
                    await asyncio.sleep(0)
                    self.assertEqual(calls, 1)
                self.assertTrue(stopped.is_set())

                custom_app = create_app(PluginGateway())
                async with custom_app.router.lifespan_context(custom_app):
                    await asyncio.sleep(0)
                    self.assertEqual(calls, 1)

        asyncio.run(exercise())

    def test_polling_cursor_rotates_after_hourly_limit(self) -> None:
        class FakeClock:
            value = datetime(2026, 1, 1, tzinfo=UTC)

            def __call__(self) -> datetime:
                return self.value

        class FakeResponse:
            status_code = 200
            headers: ClassVar[dict[str, str]] = {}
            content = b"{}"

            def json(self) -> Any:
                return {"tag_name": "v1", "name": "Release"} if self._release else [
                    {"sha": "a" * 40, "commit": {"message": "Update"}}
                ]

            def __init__(self, release: bool) -> None:
                self._release = release

        class FakeClient:
            release_repositories: ClassVar[list[str]] = []

            def __init__(self, **_: Any) -> None:
                pass

            async def __aenter__(self) -> Self:
                return self

            async def __aexit__(self, *_: object) -> None:
                return None

            async def get(self, path: str) -> FakeResponse:
                if path.endswith("/releases/latest"):
                    self.release_repositories.append(path.split("/")[3])
                    return FakeResponse(True)
                return FakeResponse(False)

        with tempfile.TemporaryDirectory() as directory:
            clock = FakeClock()
            FakeClient.release_repositories.clear()
            plugin = RepoWatchPlugin(Path(directory) / "watch.db", FakeClient, clock)
            plugin.max_checks_per_hour = 2

            async def exercise() -> tuple[dict[str, Any], dict[str, Any]]:
                for name in ("one", "two", "three"):
                    await plugin.invoke("add", {"repository": f"owner/{name}", "approved": True})
                await plugin.invoke("configure_polling", {
                    "approved": True, "enabled": True, "interval_minutes": 5,
                })
                first = await plugin.run_polling_cycle()
                clock.value += timedelta(hours=1, seconds=1)
                second = await plugin.run_polling_cycle()
                return first, second

            first, second = asyncio.run(exercise())

        self.assertEqual(first["last_check_count"], 2)
        self.assertIn("per hour", first["last_error"])
        self.assertEqual(second["last_check_count"], 2)
        self.assertEqual(FakeClient.release_repositories, ["one", "three", "two", "one"])
        self.assertEqual(second["last_polled_repository"], "owner/one")


if __name__ == "__main__":
    unittest.main()