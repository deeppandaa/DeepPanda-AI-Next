from __future__ import annotations

import os
from typing import Any

import httpx

from app.plugins.contracts import PluginManifest
from app.plugins.integration_errors import IntegrationUnavailableError


class OpenJarvisPlugin:
    """Talks to a local OpenJarvis `jarvis serve` instance through its OpenAI-compatible API."""

    manifest = PluginManifest(
        plugin_id="openjarvis",
        display_name="OpenJarvis",
        description="Yerel OpenJarvis (jarvis serve) ajanına durum, model listesi ve sohbet bağlantısı.",
        actions=("status", "models", "chat"),
    )

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("OPENJARVIS_BASE_URL", "http://host.docker.internal:8010/v1")).rstrip("/")
        self.api_key = api_key if api_key is not None else os.getenv("OPENJARVIS_API_KEY", "")
        self.default_model = os.getenv("OPENJARVIS_MODEL", "")
        self.transport = transport

    def _client(self, timeout: float) -> httpx.AsyncClient:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        return httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=httpx.Timeout(timeout, connect=3.0),
            transport=self.transport,
        )

    async def invoke(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "status":
            try:
                models = await self._models()
            except IntegrationUnavailableError as exc:
                return {"reachable": False, "base_url": self.base_url, "error": str(exc),
                        "hint": "WSL Ubuntu içinde: jarvis serve --host 0.0.0.0 --port 8010"}
            return {"reachable": True, "base_url": self.base_url, "models": models}
        if action == "models":
            return {"base_url": self.base_url, "models": await self._models()}
        if action == "chat":
            return await self._chat(payload)
        raise ValueError(f"Unsupported OpenJarvis action: {action}")

    async def _models(self) -> list[str]:
        try:
            async with self._client(10.0) as client:
                response = await client.get("/models")
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise IntegrationUnavailableError(f"OpenJarvis'e ulaşılamıyor ({self.base_url}): {exc}") from exc
        items = data.get("data", []) if isinstance(data, dict) else []
        return [str(item.get("id")) for item in items if isinstance(item, dict) and item.get("id")]

    async def _chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        message = payload.get("message")
        if not isinstance(message, str) or not message.strip() or len(message) > 20_000:
            raise ValueError("message must be non-empty text up to 20000 characters.")
        history = payload.get("messages", [])
        if not isinstance(history, list) or any(
            not isinstance(item, dict)
            or item.get("role") not in {"user", "assistant", "system"}
            or not isinstance(item.get("content"), str)
            for item in history
        ):
            raise ValueError("messages must contain only system/user/assistant text messages.")
        messages = [*history, {"role": "user", "content": message}]
        model = payload.get("model") or self.default_model
        if not model:
            models = await self._models()
            if not models:
                raise IntegrationUnavailableError("OpenJarvis model listesi boş.")
            model = models[0]
        try:
            async with self._client(600.0) as client:
                response = await client.post(
                    "/chat/completions", json={"model": model, "messages": messages, "stream": False}
                )
                response.raise_for_status()
                result = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise IntegrationUnavailableError(f"OpenJarvis sohbeti başarısız: {exc}") from exc
        choices = result.get("choices") if isinstance(result, dict) else None
        choice = choices[0] if isinstance(choices, list) and choices else {}
        content = (choice.get("message") or {}).get("content") if isinstance(choice, dict) else None
        if not isinstance(content, str):
            raise IntegrationUnavailableError("OpenJarvis metin yanıtı döndürmedi.")
        return {"model": result.get("model", model), "answer": content, "provider": "openjarvis"}
