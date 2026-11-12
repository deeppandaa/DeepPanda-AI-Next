from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from app.plugins.cloud_providers import (
    CloudProviderAuthRequired,
    CloudProviderError,
    CloudProvidersPlugin,
    detect_requested_provider,
)


class NvidiaProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.store = Path(temporary.name) / "providers.json"
        self.requests: list[httpx.Request] = []
        self.environment = patch.dict("os.environ", {"NVIDIA_API_KEY": "", "NVIDIA_MODEL": ""})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def plugin(self, status: int = 200) -> CloudProvidersPlugin:
        def handle(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            if status != 200:
                return httpx.Response(status, json={"error": "PRIVATE_PROVIDER_ERROR"})
            if request.url.path.endswith("/models"):
                return httpx.Response(200, json={"data": [{"id": "test/model"}, {"id": "test/model"}]})
            return httpx.Response(200, json={
                "model": "test/model",
                "choices": [{"message": {"content": "NVIDIA_CONNECTION_OK"}, "finish_reason": "stop"}],
            })
        return CloudProvidersPlugin(self.store, transport=httpx.MockTransport(handle))

    def save(self, plugin: CloudProvidersPlugin) -> dict:
        return asyncio.run(plugin.invoke("save_key", {
            "provider": "nvidia", "api_key": "test-nvidia-not-a-real-key", "model": "test/model",
        }))

    def test_catalog_and_missing_credentials_never_send_network_request(self) -> None:
        plugin = self.plugin()
        catalog = asyncio.run(plugin.invoke("catalog", {}))
        entry = next(item for item in catalog["providers"] if item["id"] == "nvidia")
        self.assertFalse(entry["configured"])
        self.assertEqual(entry["model"], "meta/llama-3.1-8b-instruct")
        models = asyncio.run(plugin.invoke("models", {"provider": "nvidia"}))
        self.assertEqual(models["status"], "auth_required")
        with self.assertRaises(CloudProviderAuthRequired):
            asyncio.run(plugin.invoke("chat", {"provider": "nvidia", "message": "hello"}))
        self.assertFalse(self.requests)

    def test_save_models_chat_and_remove_use_shared_provider_contract(self) -> None:
        plugin = self.plugin()
        saved = self.save(plugin)
        self.assertTrue(saved["configured"])
        self.assertNotIn("api_key", saved)
        models = asyncio.run(plugin.invoke("models", {"provider": "nvidia"}))
        self.assertEqual(models["models"], ["test/model"])
        self.assertEqual(str(self.requests[-1].url), "https://integrate.api.nvidia.com/v1/models")
        result = asyncio.run(plugin.invoke("chat", {"provider": "nvidia", "message": "hello"}))
        request = self.requests[-1]
        self.assertEqual(str(request.url), "https://integrate.api.nvidia.com/v1/chat/completions")
        self.assertEqual(request.headers["Authorization"], "Bearer test-nvidia-not-a-real-key")
        self.assertEqual(json.loads(request.content), {
            "model": "test/model", "messages": [{"role": "user", "content": "hello"}], "stream": False,
        })
        self.assertEqual(result["provider"], "nvidia")
        self.assertEqual(result["message"]["content"], "NVIDIA_CONNECTION_OK")
        self.assertTrue(asyncio.run(plugin.invoke("remove_key", {"provider": "nvidia"}))["removed"])
        with self.assertRaises(CloudProviderAuthRequired):
            asyncio.run(plugin.invoke("chat", {"provider": "nvidia", "message": "hello"}))

    def test_auth_quota_and_provider_failures_are_explicit_and_sanitized(self) -> None:
        for status in (401, 403, 402, 429, 500):
            with self.subTest(status=status):
                plugin = self.plugin(status)
                self.save(plugin)
                with self.assertRaises(CloudProviderError) as error:
                    asyncio.run(plugin.invoke("chat", {"provider": "nvidia", "message": "hello"}))
                self.assertIn("NVIDIA NIM", str(error.exception))
                self.assertNotIn("PRIVATE_PROVIDER_ERROR", str(error.exception))
                self.assertNotIn("test-nvidia-not-a-real-key", str(error.exception))

    def test_environment_credentials_and_explicit_provider_routing(self) -> None:
        with patch.dict("os.environ", {"NVIDIA_API_KEY": "test-env-not-a-real-key", "NVIDIA_MODEL": "env/model"}):
            plugin = self.plugin()
            result = asyncio.run(plugin.invoke("chat", {"provider": "nvidia", "message": "hello"}))
            self.assertTrue(result["done"])
            self.assertEqual(json.loads(self.requests[-1].content)["model"], "env/model")
        self.assertEqual(detect_requested_provider("nvidia'ya sor bunu"), "nvidia")
        self.assertEqual(detect_requested_provider("nim kullan"), "nvidia")
        self.assertIsNone(detect_requested_provider("nvidia GPU sürücüsü nedir"))
