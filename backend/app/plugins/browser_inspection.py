from __future__ import annotations

import ipaddress
import logging
import os
import socket
from typing import Any
from urllib.parse import urlsplit

from playwright.async_api import async_playwright

from app.plugins.contracts import PluginManifest

logger = logging.getLogger(__name__)


class BrowserInspectionApprovalRequired(Exception):
    pass


class BrowserInspectionProviderError(Exception):
    pass


class BrowserInspectionPlugin:
    manifest = PluginManifest(
        plugin_id="browser",
        display_name="Read-only Browser Inspection",
        description="Onaylı allowlist web sayfalarını headless Chromium ile salt-okunur snapshot eder.",
        actions=("inspect",),
    )
    max_url_chars = 2_048
    max_text_chars = 10_000
    navigation_timeout_ms = 15_000
    local_hosts = frozenset({"localhost", "127.0.0.1", "::1", "web", "host.docker.internal"})

    def __init__(self, allowed_hosts: set[str] | None = None) -> None:
        configured = allowed_hosts
        if configured is None:
            configured = {
                host.strip().casefold()
                for host in os.getenv("BROWSER_ALLOWED_HOSTS", "localhost,127.0.0.1,::1,web,host.docker.internal").split(",")
                if host.strip()
            }
        self.allowed_hosts = configured | set(self.local_hosts)

    async def invoke(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action != "inspect":
            raise ValueError(f"Unsupported browser inspection action: {action}")
        if payload.get("approved") is not True:
            raise BrowserInspectionApprovalRequired("Browser inspection requires approved=true.")
        url = payload.get("url")
        if not isinstance(url, str) or not url.strip() or len(url) > self.max_url_chars:
            raise ValueError(f"url must be a non-empty URL up to {self.max_url_chars} characters.")
        url = url.strip()
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Only credential-free HTTP(S) URLs can be inspected.")
        hostname = parsed.hostname.casefold().rstrip(".")
        if hostname not in self.allowed_hosts:
            raise ValueError("Browser target host is not in BROWSER_ALLOWED_HOSTS.")
        self._validate_dns(hostname)

        blocked_requests = 0
        try:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage"],
                )
                context = await browser.new_context(
                    accept_downloads=False,
                    service_workers="block",
                    java_script_enabled=False,
                )

                async def guard_request(route: Any) -> None:
                    nonlocal blocked_requests
                    request = route.request
                    target = urlsplit(request.url)
                    request_host = (target.hostname or "").casefold().rstrip(".")
                    if request.method not in {"GET", "HEAD"} or request_host not in self.allowed_hosts:
                        blocked_requests += 1
                        await route.abort()
                        return
                    await route.continue_()

                await context.route("**/*", guard_request)
                page = await context.new_page()
                try:
                    response = await page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=self.navigation_timeout_ms,
                    )
                    final_url = page.url
                    final_host = (urlsplit(final_url).hostname or "").casefold().rstrip(".")
                    if final_host not in self.allowed_hosts:
                        raise ValueError("Browser navigation left the configured host allowlist.")
                    title = await page.title()
                    text_error = None
                    try:
                        text = await page.locator("body").inner_text(timeout=3_000)
                    except Exception as exc:
                        logger.warning("Could not extract text from inspected page %s.", final_url, exc_info=True)
                        text = ""
                        text_error = f"{type(exc).__name__}: {exc}"[:500]
                    normalized = "\n".join(line.rstrip() for line in text.splitlines()).strip()
                    return {
                        "status": "inspected",
                        "read_only": True,
                        "requested_url": url,
                        "final_url": final_url,
                        "http_status": response.status if response else None,
                        "title": title[:300],
                        "text": normalized[: self.max_text_chars],
                        "text_truncated": len(normalized) > self.max_text_chars,
                        "text_error": text_error,
                        "blocked_requests": blocked_requests,
                        "interactions_performed": 0,
                    }
                finally:
                    await context.close()
                    await browser.close()
        except (ValueError, BrowserInspectionApprovalRequired):
            raise
        except Exception as exc:
            raise BrowserInspectionProviderError("Headless browser inspection failed.") from exc

    @classmethod
    def _validate_dns(cls, hostname: str) -> None:
        if hostname in cls.local_hosts:
            return
        try:
            addresses = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise ValueError("Browser target hostname did not resolve.") from exc
        if not addresses:
            raise ValueError("Browser target hostname did not resolve.")
        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            if not ip.is_global:
                raise ValueError("Browser target hostname resolves to a private or non-public IP.")