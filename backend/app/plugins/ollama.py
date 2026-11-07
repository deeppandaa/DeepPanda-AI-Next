from __future__ import annotations

import os
import re
from typing import Any

import httpx

from app.plugins.contracts import PluginManifest


class OllamaApprovalRequired(Exception):
    pass


class OllamaProviderError(Exception):
    pass


class OllamaPlugin:
    manifest = PluginManifest(
        plugin_id="ollama",
        display_name="Ollama",
        description="Yerel Ollama modelleriyle sohbet, görsel analiz, model listeleme ve onaylı model indirme.",
        actions=("models", "chat", "embed", "pull"),
    )

    def __init__(self, base_url: str | None = None, default_model: str | None = None) -> None:
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")).rstrip("/")
        self.default_model = default_model or os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")

    async def invoke(self, action: str, payload: dict[str, Any]) -> Any:
        timeout = httpx.Timeout(600.0, connect=5.0)
        async with httpx.AsyncClient(base_url=self.base_url, timeout=timeout) as client:
            if action == "models":
                response = await client.get("/api/tags")
                response.raise_for_status()
                catalog = self._decode(response)
                return {
                    "default_model": self.default_model,
                    "models": catalog.get("models", []),
                }
            if action == "pull":
                if payload.get("approved") is not True:
                    raise OllamaApprovalRequired("Downloading an Ollama model requires approved=true.")
                model = payload.get("model")
                if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,150}(?::[A-Za-z0-9._-]{1,80})?", model):
                    raise ValueError("model must be a valid Ollama model name.")
                if model.casefold().endswith(("-cloud", ":cloud")):
                    raise ValueError("Only local Ollama models can be pulled.")
                response = await client.post(
                    "/api/pull", json={"model": model, "stream": False}, timeout=httpx.Timeout(7_200.0, connect=5.0),
                )
                response.raise_for_status()
                result = self._decode(response)
                return {"model": model, "status": result.get("status", "unknown")}
            if action == "embed":
                model = payload.get("model")
                input_value = payload.get("input")
                if not isinstance(model, str) or not model.strip() or len(model) > 200:
                    raise ValueError("model must name an installed local embedding model.")
                if model.casefold().endswith(("-cloud", ":cloud")):
                    raise ValueError("Only local Ollama embedding models are allowed.")
                inputs = [input_value] if isinstance(input_value, str) else input_value
                if (
                    not isinstance(inputs, list)
                    or not 1 <= len(inputs) <= 64
                    or any(not isinstance(text, str) or not text.strip() or len(text) > 2_000 for text in inputs)
                ):
                    raise ValueError("input must contain 1 to 64 non-empty strings up to 2000 characters each.")
                response = await client.post("/api/embed", json={"model": model, "input": inputs})
                response.raise_for_status()
                result = self._decode(response)
                embeddings = result.get("embeddings")
                if not isinstance(embeddings, list) or len(embeddings) != len(inputs):
                    raise ValueError("Ollama returned an invalid embedding batch.")
                if any(not isinstance(vector, list) or not vector or any(not isinstance(value, (int, float)) for value in vector) for vector in embeddings):
                    raise ValueError("Ollama returned an invalid embedding vector.")
                dimensions = len(embeddings[0])
                if any(len(vector) != dimensions for vector in embeddings):
                    raise ValueError("Ollama returned inconsistent embedding dimensions.")
                return {"model": model, "embeddings": embeddings, "dimensions": dimensions}
            if action == "chat":
                messages = payload.get("messages", [])
                if not isinstance(messages, list) or any(
                    not isinstance(item, dict)
                    or item.get("role") not in {"system", "user", "assistant", "tool"}
                    or not isinstance(item.get("content", ""), str)
                    for item in messages
                ):
                    raise ValueError("messages must contain valid chat messages.")
                messages = list(messages)
                system_prompt = payload.get("system_prompt")
                if isinstance(system_prompt, str) and system_prompt.strip():
                    messages.insert(0, {"role": "system", "content": system_prompt})
                message = payload.get("message")
                if message is not None:
                    if not isinstance(message, str) or not message.strip():
                        raise ValueError("message must be non-empty text when supplied.")
                    user_message: dict[str, Any] = {"role": "user", "content": message}
                elif not messages:
                    raise ValueError("message or messages must be provided.")
                images = payload.get("images")
                if images is not None and message is None:
                    raise ValueError("images require a new user message.")
                if images is not None:
                    if (
                        not isinstance(images, list)
                        or not 1 <= len(images) <= 4
                        or any(not isinstance(image, str) or not image or len(image) > 15_000_000 for image in images)
                    ):
                        raise ValueError("images must contain 1 to 4 base64 strings.")
                    user_message["images"] = images
                if message is not None:
                    messages.append(user_message)
                request_body = {
                    "model": payload.get("model") or self.default_model,
                    "messages": messages,
                    "stream": False,
                }
                tools = payload.get("tools")
                if tools is not None:
                    if not isinstance(tools, list) or any(not isinstance(tool, dict) for tool in tools):
                        raise ValueError("tools must be a list of function tool definitions.")
                    request_body["tools"] = tools
                if payload.get("format") == "json":
                    max_output_tokens = payload.get("max_output_tokens", 700)
                    if (
                        isinstance(max_output_tokens, bool)
                        or not isinstance(max_output_tokens, int)
                        or not 1 <= max_output_tokens <= 4_096
                    ):
                        raise ValueError("max_output_tokens must be an integer from 1 to 4096.")
                    response_schema = payload.get("response_schema")
                    if response_schema is not None and not isinstance(response_schema, dict):
                        raise ValueError("response_schema must be a JSON Schema object.")
                    request_body["format"] = response_schema or "json"
                    options: dict[str, int | float] = {
                        "num_predict": max_output_tokens,
                        "temperature": 0.2,
                    }
                    max_context_tokens = payload.get("max_context_tokens")
                    if max_context_tokens is not None:
                        if (
                            isinstance(max_context_tokens, bool)
                            or not isinstance(max_context_tokens, int)
                            or not 1_024 <= max_context_tokens <= 32_768
                        ):
                            raise ValueError("max_context_tokens must be an integer from 1024 to 32768.")
                        options["num_ctx"] = max_context_tokens
                    request_body["options"] = options
                    think = payload.get("think")
                    if think is not None:
                        if not isinstance(think, bool):
                            raise TypeError("think must be a boolean when supplied with JSON chat.")
                        request_body["think"] = think
                response = await client.post("/api/chat", json=request_body)
                response.raise_for_status()
                result = self._decode(response)
                result.pop("thinking", None)
                return result
        raise ValueError(f"Unsupported Ollama action: {action}")

    @staticmethod
    def _decode(response: httpx.Response) -> dict[str, Any]:
        try:
            result = response.json()
        except ValueError as exc:
            raise OllamaProviderError("Ollama returned invalid JSON.") from exc
        if not isinstance(result, dict):
            raise OllamaProviderError("Ollama returned an invalid response object.")
        return result