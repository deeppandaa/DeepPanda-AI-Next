from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from app.plugins.ollama import OllamaPlugin


class OllamaPluginTests(unittest.TestCase):
    def test_embed_forwards_bounded_local_embedding_batch(self) -> None:
        class FakeResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, object]:
                return {"embeddings": [[0.1, 0.2], [0.3, 0.4]]}

        class FakeClient:
            request_body: dict[str, object] | None = None

            def __init__(self, **_: object) -> None:
                pass

            async def __aenter__(self) -> FakeClient:
                return self

            async def __aexit__(self, *_: object) -> None:
                return None

            async def post(self, path: str, json: dict[str, object]) -> FakeResponse:
                FakeClient.request_body = json
                return FakeResponse()

        async def invoke() -> dict[str, object]:
            with patch("app.plugins.ollama.httpx.AsyncClient", FakeClient):
                return await OllamaPlugin().invoke("embed", {
                    "model": "nomic-embed-text:latest",
                    "input": ["first text", "second text"],
                })

        result = asyncio.run(invoke())
        self.assertEqual(FakeClient.request_body, {
            "model": "nomic-embed-text:latest",
            "input": ["first text", "second text"],
        })
        self.assertEqual(result["dimensions"], 2)
        self.assertEqual(len(result["embeddings"]), 2)

    def test_embed_rejects_cloud_models_and_oversized_batches(self) -> None:
        plugin = OllamaPlugin()

        async def exercise(payload: dict[str, object]) -> None:
            await plugin.invoke("embed", payload)

        with self.assertRaisesRegex(ValueError, "Only local"):
            asyncio.run(exercise({"model": "remote:cloud", "input": ["text"]}))
        with self.assertRaisesRegex(ValueError, "1 to 64"):
            asyncio.run(exercise({"model": "nomic-embed-text", "input": ["text"] * 65}))

    def test_chat_forwards_json_format_and_system_prompt(self) -> None:
        class FakeResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, object]:
                return {"message": {"content": "{}"}}

        class FakeClient:
            request_bodies: list[dict[str, object]] = []

            def __init__(self, **_: object) -> None:
                pass

            async def __aenter__(self) -> FakeClient:
                return self

            async def __aexit__(self, *_: object) -> None:
                return None

            async def post(self, path: str, json: dict[str, object]) -> FakeResponse:
                FakeClient.request_bodies.append(json)
                return FakeResponse()

        async def invoke() -> dict[str, object]:
            with patch("app.plugins.ollama.httpx.AsyncClient", FakeClient):
                return await OllamaPlugin().invoke("chat", {
                    "message": "Draft steps",
                    "model": "qwen3.8:latest",
                    "system_prompt": "Return JSON only.",
                    "format": "json",
                    "think": False,
                })

        asyncio.run(invoke())
        request_body = FakeClient.request_bodies[-1]
        self.assertEqual(request_body["format"], "json")
        self.assertEqual(request_body["options"], {"num_predict": 700, "temperature": 0.2})
        self.assertFalse(request_body["think"])
        self.assertEqual(request_body["model"], "qwen3.8:latest")
        messages = request_body["messages"]
        self.assertEqual(messages[0], {"role": "system", "content": "Return JSON only."})
        self.assertEqual(messages[1], {"role": "user", "content": "Draft steps"})

    def test_normal_chat_does_not_force_json_format(self) -> None:
        class FakeResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, object]:
                return {"message": {"content": "Hello"}}

        class FakeClient:
            request_bodies: list[dict[str, object]] = []

            def __init__(self, **_: object) -> None:
                pass

            async def __aenter__(self) -> FakeClient:
                return self

            async def __aexit__(self, *_: object) -> None:
                return None

            async def post(self, path: str, json: dict[str, object]) -> FakeResponse:
                FakeClient.request_bodies.append(json)
                return FakeResponse()

        async def invoke() -> dict[str, object]:
            with patch("app.plugins.ollama.httpx.AsyncClient", FakeClient):
                return await OllamaPlugin().invoke("chat", {"message": "Hello"})

        asyncio.run(invoke())
        self.assertNotIn("format", FakeClient.request_bodies[-1])

    def test_chat_forwards_json_response_schema(self) -> None:
        class FakeResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, object]:
                return {"message": {"content": "{}"}}

        class FakeClient:
            request_body: dict[str, object] | None = None

            def __init__(self, **_: object) -> None:
                pass

            async def __aenter__(self) -> FakeClient:
                return self

            async def __aexit__(self, *_: object) -> None:
                return None

            async def post(self, path: str, json: dict[str, object]) -> FakeResponse:
                FakeClient.request_body = json
                return FakeResponse()

        schema = {
            "type": "object",
            "properties": {"evidence": {"type": "array"}},
            "required": ["evidence"],
        }

        async def invoke() -> dict[str, object]:
            with patch("app.plugins.ollama.httpx.AsyncClient", FakeClient):
                return await OllamaPlugin().invoke("chat", {
                    "message": "Return cited JSON",
                    "format": "json",
                    "response_schema": schema,
                })

        asyncio.run(invoke())
        self.assertEqual(FakeClient.request_body["format"], schema)

    def test_json_chat_output_budget_is_bounded(self) -> None:
        class FakeResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, object]:
                return {"message": {"content": "{}"}}

        class FakeClient:
            request_body: dict[str, object] | None = None

            def __init__(self, **_: object) -> None:
                pass

            async def __aenter__(self) -> FakeClient:
                return self

            async def __aexit__(self, *_: object) -> None:
                return None

            async def post(self, path: str, json: dict[str, object]) -> FakeResponse:
                FakeClient.request_body = json
                return FakeResponse()

        async def invoke(payload: dict[str, object]) -> None:
            with patch("app.plugins.ollama.httpx.AsyncClient", FakeClient):
                await OllamaPlugin().invoke("chat", payload)

        asyncio.run(invoke({"message": "Return JSON", "format": "json", "max_output_tokens": 4096}))
        self.assertEqual(FakeClient.request_body["options"], {"num_predict": 4096, "temperature": 0.2})
        asyncio.run(invoke({"message": "Return JSON", "format": "json", "max_context_tokens": 8192}))
        self.assertEqual(FakeClient.request_body["options"], {
            "num_predict": 700,
            "temperature": 0.2,
            "num_ctx": 8192,
        })
        with self.assertRaisesRegex(ValueError, "1 to 4096"):
            asyncio.run(invoke({"message": "Return JSON", "format": "json", "max_output_tokens": 4097}))
        with self.assertRaisesRegex(ValueError, "1024 to 32768"):
            asyncio.run(invoke({"message": "Return JSON", "format": "json", "max_context_tokens": 32769}))


if __name__ == "__main__":
    unittest.main()