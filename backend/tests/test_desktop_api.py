from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from desktop.api import ACTION_TIMEOUTS, ApiClient, ApiError


class DesktopApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.requests: list[httpx.Request] = []
        transport = httpx.MockTransport(self.respond)
        client = httpx.Client
        client_patch = patch("desktop.api.httpx.Client", side_effect=lambda **kwargs: client(transport=transport, **kwargs))
        client_patch.start()
        self.addCleanup(client_patch.stop)
        self.api = ApiClient("http://test", timeout=600)
        self.error: httpx.HTTPError | None = None
        self.status = 200
        self.body = {"ok": True}

    def respond(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return httpx.Response(self.status, json=self.body)

    def test_long_actions_use_full_budget_and_preserve_approval_payload(self) -> None:
        for (plugin, action), timeout in ACTION_TIMEOUTS.items():
            with self.subTest(plugin=plugin):
                result = self.api.action(plugin, action, {"approved": True})
                self.assertEqual(result, {"ok": True})
                request = self.requests[-1]
                self.assertEqual(request.extensions["timeout"]["read"], timeout)
                self.assertEqual(request.extensions["timeout"]["connect"], 5)
                self.assertEqual(json.loads(request.content), {"payload": {"approved": True}})
        self.assertEqual(len(self.requests), 2)

    def test_multi_agent_budget_covers_catalog_and_five_stages(self) -> None:
        self.assertGreater(ACTION_TIMEOUTS[("multi_agent", "run")], 6 * 600)
        self.assertGreater(ACTION_TIMEOUTS[("ollama", "pull")], 7200)

    def test_short_requests_and_normal_actions_keep_existing_limits(self) -> None:
        self.api.health()
        self.api.plugins()
        self.api.models()
        self.api.action("memory", "search", {"query": "test"})
        self.assertEqual([request.extensions["timeout"]["read"] for request in self.requests], [5, 15, 20, 600])

    def test_explicit_timeout_overrides_long_operation_default(self) -> None:
        self.api.action("multi_agent", "run", timeout=12)
        self.assertEqual(self.requests[-1].extensions["timeout"]["read"], 12)

    def test_larger_configured_timeout_is_respected(self) -> None:
        self.api.timeout = 8000
        self.api.action("ollama", "pull")
        self.assertEqual(self.requests[-1].extensions["timeout"]["read"], 8000)

    def test_read_timeout_warns_about_server_work_without_retry(self) -> None:
        self.error = httpx.ReadTimeout("slow model")
        with self.assertRaises(ApiError) as exc:
            self.api.action("multi_agent", "run", {"approved": True})
        self.assertEqual(exc.exception.status, 0)
        self.assertIn("3660", exc.exception.detail)
        self.assertIn("devam ediyor olabilir", exc.exception.detail)
        self.assertEqual(len(self.requests), 1)
        self.assertIs(exc.exception.__cause__, self.error)

    def test_connect_timeout_has_distinct_diagnostic(self) -> None:
        self.error = httpx.ConnectTimeout("blocked")
        with self.assertRaises(ApiError) as exc:
            self.api.health()
        self.assertIn("5 saniyede", exc.exception.detail)
        self.assertEqual(len(self.requests), 1)

    def test_connection_error_still_raises_api_error(self) -> None:
        self.error = httpx.ConnectError("unavailable")
        with self.assertRaises(ApiError) as exc:
            self.api.health()
        self.assertEqual(exc.exception.status, 0)
        self.assertIn("unavailable", exc.exception.detail)

    def test_approval_error_is_not_swallowed_or_retried(self) -> None:
        self.status = 403
        self.body = {"detail": "Approval required"}
        with self.assertRaises(ApiError) as exc:
            self.api.action("multi_agent", "run")
        self.assertTrue(exc.exception.needs_approval)
        self.assertEqual(exc.exception.detail, "Approval required")
        self.assertEqual(len(self.requests), 1)

    def test_web_proxy_matches_long_operation_budgets(self) -> None:
        config = (Path(__file__).resolve().parents[2] / "frontend" / "nginx.conf").read_text(encoding="utf-8")
        for (plugin, action), timeout in ACTION_TIMEOUTS.items():
            route = f"/api/plugins/{plugin}/actions/{action}"
            block = re.search(r"location = " + re.escape(route) + r"\s*\{([^}]+)\}", config)
            self.assertIsNotNone(block)
            assert block is not None
            self.assertIn(f"proxy_read_timeout {int(timeout)}s;", block[1])
            self.assertIn("proxy_connect_timeout 5s;", block[1])
            self.assertIn("proxy_pass http://api:8000;", block[1])


if __name__ == "__main__":
    unittest.main()
