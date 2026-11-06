from __future__ import annotations

import os
from typing import Any

import httpx

from app.plugins.contracts import PluginManifest


class FreeLLMAPIProviderError(Exception):
    pass


class FreeLLMAPIPlugin:
    manifest = PluginManifest(
        plugin_id="freellmapi",
        display_name="FreeLLMAPI",
        description="Opt-in OpenAI-compatible gateway for chat completions only.",
        actions=("chat",),
    )

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        enabled: bool | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = (
            base_url or os.getenv("FREELLMAPI_BASE_URL", "http://freellmapi:3001/v1")
        ).rstrip("/")
        self.api_key = api_key if api_key is not None else os.getenv("FREELLMAPI_API_KEY", "")
        self.model = model or os.getenv("FREELLMAPI_CHAT_MODEL", "auto")
        self.enabled = (
            enabled
            if enabled is not None
            else os.getenv("FREELLMAPI_CHAT_ENABLED", "false").casefold() == "true"
        )
        self.transport = transport

    async def invoke(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action != "chat":
            raise ValueError(f"Unsupported FreeLLMAPI action: {action}")
        if not self.enabled:
            raise FreeLLMAPIProviderError("FreeLLMAPI chat routing is disabled.")
        if not self.api_key:
            raise FreeLLMAPIProviderError("FreeLLMAPI is enabled but no API key is configured.")

        message = payload.get("message")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("message must be non-empty text.")
        messages = payload.get("messages", [])
        if not isinstance(messages, list) or any(
            not isinstance(item, dict)
            or item.get("role") not in {"user", "assistant"}
            or not isinstance(item.get("content"), str)
            for item in messages
        ):
            raise ValueError("messages must contain only user/assistant text messages.")

        chat_messages: list[dict[str, str]] = []
        system_prompt = payload.get("system_prompt")
        if isinstance(system_prompt, str) and system_prompt.strip():
            chat_messages.append({"role": "system", "content": system_prompt})
        chat_messages.extend(messages)
        chat_messages.append({"role": "user", "content": message})
        request_model = payload.get("model") or self.model
        if not isinstance(request_model, str) or not request_model.strip() or len(request_model) > 200:
            raise ValueError("model must be non-empty text up to 200 characters.")

        timeout = httpx.Timeout(180.0, connect=5.0)
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            transport=self.transport,
        ) as client:
            response = await client.post(
                "/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": request_model, "messages": chat_messages, "stream": False},
            )
            response.raise_for_status()
            try:
                result = response.json()
            except ValueError as exc:
                raise FreeLLMAPIProviderError("FreeLLMAPI returned invalid JSON.") from exc

        choices = result.get("choices") if isinstance(result, dict) else None
        choice = choices[0] if isinstance(choices, list) and choices else None
        assistant_message = choice.get("message") if isinstance(choice, dict) else None
        content = assistant_message.get("content") if isinstance(assistant_message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise FreeLLMAPIProviderError("FreeLLMAPI returned no text chat completion.")

        normalized: dict[str, Any] = {
            "model": result.get("model", request_model),
            "message": {"role": "assistant", "content": content},
            "done": True,
            "done_reason": choice.get("finish_reason") if isinstance(choice, dict) else None,
            "provider": "freellmapi",
        }
        usage = result.get("usage")
        if isinstance(usage, dict):
            normalized["usage"] = usage
        return normalized