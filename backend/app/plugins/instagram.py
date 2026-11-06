from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import re
from typing import Any, ClassVar
from urllib.parse import urlparse

import httpx

from app.plugins.contracts import PluginManifest


class InstagramApprovalRequired(Exception):
    pass


class InstagramConfigurationError(Exception):
    pass


class InstagramApiError(Exception):
    pass


class InstagramPlugin:
    manifest = PluginManifest(
        plugin_id="instagram",
        display_name="Instagram Publishing",
        description="Instagram Graph API ile onaylı görsel/Reel yayınlama ve mesaj gönderme.",
        actions=("status", "publish_image", "publish_video", "send_message"),
    )

    max_caption_chars: ClassVar[int] = 2_200
    max_message_chars: ClassVar[int] = 2_000
    reel_poll_attempts: ClassVar[int] = 12

    def __init__(
        self,
        access_token: str | None = None,
        user_id: str | None = None,
        graph_version: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        poll_interval: float = 5.0,
    ) -> None:
        self.access_token = access_token if access_token is not None else os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
        self.user_id = user_id if user_id is not None else os.getenv("INSTAGRAM_USER_ID", "")
        self.graph_version = graph_version or os.getenv("INSTAGRAM_GRAPH_VERSION", "v23.0")
        self.transport = transport
        self.poll_interval = poll_interval

    async def invoke(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "status":
            return {"configured": bool(self.access_token and self.user_id), "graph_version": self.graph_version}
        if action == "publish_image":
            return await self._publish(payload, "image_url", {})
        if action == "publish_video":
            return await self._publish(payload, "video_url", {"media_type": "REELS"})
        if action == "send_message":
            return await self._send_message(payload)
        raise ValueError(f"Unsupported instagram action: {action}")

    def _client(self) -> httpx.AsyncClient:
        if not self.access_token or not re.fullmatch(r"\d{1,40}", self.user_id or ""):
            raise InstagramConfigurationError("INSTAGRAM_ACCESS_TOKEN and a numeric INSTAGRAM_USER_ID must be configured.")
        if not re.fullmatch(r"v\d{1,3}\.\d{1,3}", self.graph_version):
            raise InstagramConfigurationError("INSTAGRAM_GRAPH_VERSION must look like v23.0.")
        return httpx.AsyncClient(
            base_url=f"https://graph.facebook.com/{self.graph_version}", timeout=httpx.Timeout(30.0, connect=10.0), transport=self.transport,
        )

    async def _publish(self, payload: dict[str, Any], url_key: str, extra: dict[str, str]) -> dict[str, Any]:
        if payload.get("approved") is not True:
            raise InstagramApprovalRequired("Publishing to Instagram requires approved=true.")
        media_url = self._public_url(payload.get(url_key), url_key)
        caption = payload.get("caption", "")
        if not isinstance(caption, str) or len(caption) > self.max_caption_chars:
            raise ValueError(f"caption must be a string up to {self.max_caption_chars} characters.")
        async with self._client() as client:
            container = await self._post(client, f"/{self.user_id}/media", {**extra, url_key: media_url, "caption": caption})
            creation_id = str(container.get("id", ""))
            if not creation_id:
                raise InstagramApiError("Instagram did not return a media container id.")
            status_code = "FINISHED"
            if extra.get("media_type") == "REELS":
                status_code = "IN_PROGRESS"
                for attempt in range(self.reel_poll_attempts):
                    status = await self._get(client, f"/{creation_id}", {"fields": "status_code"})
                    status_code = str(status.get("status_code", status_code))
                    if status_code in {"FINISHED", "ERROR", "EXPIRED"}:
                        break
                    if attempt + 1 < self.reel_poll_attempts:
                        await asyncio.sleep(self.poll_interval)
                if status_code != "FINISHED":
                    raise InstagramApiError(f"Instagram Reel is not ready: {status_code}")
            published = await self._post(client, f"/{self.user_id}/media_publish", {"creation_id": creation_id})
        return {"status": "published", "creation_id": creation_id, "container_status": status_code, "media_id": published.get("id")}

    async def _send_message(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("approved") is not True:
            raise InstagramApprovalRequired("Sending an Instagram message requires approved=true.")
        recipient = payload.get("recipient_id")
        text = payload.get("text")
        if not isinstance(recipient, str) or not re.fullmatch(r"\d{1,40}", recipient.strip()):
            raise ValueError("recipient_id must be a numeric Instagram-scoped id.")
        if not isinstance(text, str) or not text.strip() or len(text) > self.max_message_chars:
            raise ValueError(f"text must be a non-empty string up to {self.max_message_chars} characters.")
        async with self._client() as client:
            response = await self._post(
                client, f"/{self.user_id}/messages",
                {"recipient": json.dumps({"id": recipient.strip()}), "message": json.dumps({"text": text}, ensure_ascii=False)},
            )
        message_id = response.get("message_id")
        if not isinstance(message_id, str) or not message_id:
            raise InstagramApiError("Instagram did not confirm the sent message.")
        return {"status": "sent", "message_id": message_id}

    async def _post(self, client: httpx.AsyncClient, path: str, data: dict[str, str]) -> dict[str, Any]:
        return self._decode(await self._request(client.post(path, data={**data, "access_token": self.access_token})))

    async def _get(self, client: httpx.AsyncClient, path: str, params: dict[str, str]) -> dict[str, Any]:
        return self._decode(await self._request(client.get(path, params={**params, "access_token": self.access_token})))

    async def _request(self, request: Any) -> httpx.Response:
        try:
            return await request
        except httpx.HTTPError as exc:
            raise InstagramApiError(f"Instagram Graph API connection failed: {exc.__class__.__name__}") from exc

    def _decode(self, response: httpx.Response) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError:
            raise InstagramApiError(f"Instagram Graph API returned invalid JSON ({response.status_code}).") from None
        if response.is_error or not isinstance(body, dict):
            message = body.get("error", {}).get("message", "") if isinstance(body, dict) and isinstance(body.get("error"), dict) else ""
            raise InstagramApiError(f"Instagram Graph API error ({response.status_code}): {self._redact(message)[:500]}")
        return body

    def _redact(self, text: str) -> str:
        return text.replace(self.access_token, "***") if self.access_token else text

    @staticmethod
    def _public_url(value: Any, key: str) -> str:
        if not isinstance(value, str) or len(value) > 2_000:
            raise ValueError(f"{key} must be a public https URL.")
        parsed = urlparse(value.strip())
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not host or host in {"localhost"} or host.endswith((".local", ".internal")):
            raise ValueError(f"{key} must be a public https URL reachable by Instagram.")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            return value.strip()
        if not address.is_global:
            raise ValueError(f"{key} must be a public https URL reachable by Instagram.")
        return value.strip()
