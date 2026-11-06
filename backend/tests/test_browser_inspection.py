from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import httpx

from app.main import create_app
from app.plugins.gateway import PluginGateway
from app.plugins.browser_inspection import (
    BrowserInspectionApprovalRequired,
    BrowserInspectionPlugin,
)


class BrowserInspectionPluginTests(unittest.TestCase):
    def test_inspection_requires_approval(self) -> None:
        plugin = BrowserInspectionPlugin()

        async def exercise() -> None:
            with self.assertRaises(BrowserInspectionApprovalRequired):
                await plugin.invoke("inspect", {"url": "http://web:80/"})

        asyncio.run(exercise())

    def test_api_maps_unapproved_inspection_to_forbidden(self) -> None:
        gateway = PluginGateway()
        gateway.register(BrowserInspectionPlugin())
        app = create_app(gateway)

        async def exercise() -> int:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/plugins/browser/actions/inspect",
                    json={"payload": {"url": "http://web/"}},
                )
                return response.status_code

        self.assertEqual(asyncio.run(exercise()), 403)

    def test_host_allowlist_and_private_dns_are_enforced(self) -> None:
        async def unlisted() -> None:
            plugin = BrowserInspectionPlugin(allowed_hosts={"example.com"})
            with self.assertRaisesRegex(ValueError, "BROWSER_ALLOWED_HOSTS"):
                await plugin.invoke("inspect", {"approved": True, "url": "http://evil.example/"})

        asyncio.run(unlisted())
        private_result = [(None, None, None, None, ("10.0.0.5", 0))]
        plugin = BrowserInspectionPlugin(allowed_hosts={"example.com"})
        with patch("app.plugins.browser_inspection.socket.getaddrinfo", return_value=private_result):
            with self.assertRaisesRegex(ValueError, "private or non-public"):
                asyncio.run(plugin.invoke("inspect", {"approved": True, "url": "https://example.com/"}))

    def test_snapshot_is_get_only_and_blocks_unlisted_subresources(self) -> None:
        class FakeRequest:
            def __init__(self, url: str, method: str = "GET") -> None:
                self.url = url
                self.method = method

        class FakeRoute:
            def __init__(self, url: str, method: str = "GET") -> None:
                self.request = FakeRequest(url, method)
                self.aborted = False
                self.continued = False

            async def abort(self) -> None:
                self.aborted = True

            async def continue_(self) -> None:
                self.continued = True

        class FakePage:
            url = "http://web:80/"

            def __init__(self, context: FakeContext) -> None:
                self.context = context

            async def goto(self, url: str, **_: object) -> SimpleNamespace:
                self.url = url
                self.context.tracking_route = FakeRoute("https://tracking.example/pixel")
                await self.context.route_handler(self.context.tracking_route)
                self.context.post_route = FakeRoute("http://web:80/submit", "POST")
                await self.context.route_handler(self.context.post_route)
                return SimpleNamespace(status=200)

            async def title(self) -> str:
                return "Local app"

            def locator(self, _: str) -> SimpleNamespace:
                return SimpleNamespace(inner_text=lambda **__: asyncio.sleep(0, result="Local application snapshot"))

        class FakeContext:
            def __init__(self) -> None:
                self.route_handler = None
                self.tracking_route = None
                self.post_route = None
                self.closed = False
                self.options = None

            async def route(self, _pattern: str, handler: object) -> None:
                self.route_handler = handler

            async def new_page(self) -> FakePage:
                return FakePage(self)

            async def close(self) -> None:
                self.closed = True

        class FakeBrowser:
            def __init__(self) -> None:
                self.context = FakeContext()
                self.closed = False

            async def new_context(self, **options: object) -> FakeContext:
                self.context.options = options
                return self.context

            async def close(self) -> None:
                self.closed = True

        class FakeChromium:
            def __init__(self) -> None:
                self.browser = FakeBrowser()

            async def launch(self, **_: object) -> FakeBrowser:
                return self.browser

        class FakePlaywright:
            def __init__(self) -> None:
                self.chromium = FakeChromium()

        class FakeManager:
            def __init__(self, playwright: FakePlaywright) -> None:
                self.playwright = playwright

            async def __aenter__(self) -> FakePlaywright:
                return self.playwright

            async def __aexit__(self, *_: object) -> None:
                return None

        playwright = FakePlaywright()
        plugin = BrowserInspectionPlugin()

        async def exercise() -> dict[str, object]:
            with patch("app.plugins.browser_inspection.async_playwright", return_value=FakeManager(playwright)):
                return await plugin.invoke("inspect", {"approved": True, "url": "http://web:80/"})

        result = asyncio.run(exercise())
        self.assertEqual(result["status"], "inspected")
        self.assertTrue(result["read_only"])
        self.assertEqual(result["interactions_performed"], 0)
        self.assertEqual(result["blocked_requests"], 2)
        self.assertFalse(playwright.chromium.browser.context.options["java_script_enabled"])
        self.assertFalse(playwright.chromium.browser.context.options["accept_downloads"])
        self.assertTrue(playwright.chromium.browser.context.closed)
        self.assertTrue(playwright.chromium.browser.closed)


if __name__ == "__main__":
    unittest.main()