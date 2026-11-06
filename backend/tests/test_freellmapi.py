from __future__ import annotations

import asyncio
import json
import unittest

import httpx
from app.plugins.freellmapi import FreeLLMAPIPlugin, FreeLLMAPIProviderError


class FreeLLMAPIPluginTests(unittest.TestCase):
    def test_chat_sends_only_text_and_normalizes_openai_response(self) -> None:
        captured: dict[str, object] = {}

        def handle(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["authorization"] = request.headers.get("Authorization")
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json={
                "model": "google/gemini-flash",
                "choices": [{
                    "message": {"role": "assistant", "content": "Hello"},
                    "finish_reason": "stop",
                }],
                "usage": {"prompt_tokens": 12, "completion_tokens": 1},
            })

        plugin = FreeLLMAPIPlugin(
            base_url="http://gateway:3001/v1",
            api_key="test-key",
            model="auto",
            enabled=True,
            transport=httpx.MockTransport(handle),
        )
        result = asyncio.run(plugin.invoke("chat", {
            "model": "auto",
            "system_prompt": "Stay concise.",
            "messages": [{"role": "user", "content": "Prior question"}],
            "message": "Hello?",
        }))

        self.assertEqual(captured["url"], "http://gateway:3001/v1/chat/completions")
        self.assertEqual(captured["authorization"], "Bearer test-key")
        self.assertEqual(captured["body"], {
            "model": "auto",
            "messages": [
                {"role": "system", "content": "Stay concise."},
                {"role": "user", "content": "Prior question"},
                {"role": "user", "content": "Hello?"},
            ],
            "stream": False,
        })
        self.assertEqual(result["model"], "google/gemini-flash")
        self.assertEqual(result["message"]["content"], "Hello")
        self.assertEqual(result["provider"], "freellmapi")

    def test_disabled_gateway_fails_closed(self) -> None:
        plugin = FreeLLMAPIPlugin(api_key="test-key", enabled=False)

        with self.assertRaisesRegex(FreeLLMAPIProviderError, "disabled"):
            asyncio.run(plugin.invoke("chat", {"message": "hello"}))

    def test_enabled_gateway_without_key_fails_closed(self) -> None:
        plugin = FreeLLMAPIPlugin(api_key="", enabled=True)

        with self.assertRaisesRegex(FreeLLMAPIProviderError, "no API key"):
            asyncio.run(plugin.invoke("chat", {"message": "hello"}))

    def test_non_text_history_is_rejected(self) -> None:
        plugin = FreeLLMAPIPlugin(api_key="test-key", enabled=True)

        with self.assertRaisesRegex(ValueError, "text messages"):
            asyncio.run(plugin.invoke("chat", {
                "message": "hello",
                "messages": [{"role": "user", "content": [{"type": "image"}]}],
            }))


if __name__ == "__main__":
    unittest.main()