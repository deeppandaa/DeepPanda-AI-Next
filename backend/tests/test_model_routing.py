from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from app.model_routing import ModelRoutingPreferences


class ModelRoutingPreferencesTests(unittest.TestCase):
    def test_selects_first_installed_model_in_area_priority(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "priorities.json"
            path.write_text(json.dumps({
                "area_priorities": {"planning": ["missing:latest", "gemma:7b", "qwen3.6:latest"]},
            }), encoding="utf-8")
            preferences = ModelRoutingPreferences(path)

            selected = preferences.choose("planning", None, {
                "default_model": "qwen3.6:latest",
                "models": [
                    {"name": "nomic-embed-text:latest"},
                    {"name": "qwen3.6:latest"},
                    {"name": "gemma:7b"},
                ],
            })

        self.assertEqual(selected, "gemma:7b")

    def test_explicit_user_model_overrides_benchmark_priority(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "priorities.json"
            path.write_text(json.dumps({"area_priorities": {"answer": ["qwen3.6:latest"]}}), encoding="utf-8")
            selected = ModelRoutingPreferences(path).choose(
                "answer", "deepseek-coder:6.7b", {"models": [{"name": "qwen3.6:latest"}]}
            )

        self.assertEqual(selected, "deepseek-coder:6.7b")

    def test_invalid_or_missing_preferences_fall_back_to_installed_default(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "missing.json"
            selected = ModelRoutingPreferences(path).choose("code_change", None, {
                "default_model": "qwen3.6:latest",
                "models": [{"name": "qwen3.6:latest"}, {"name": "nomic-embed-text:latest"}],
            })

        self.assertEqual(selected, "qwen3.6:latest")

    def test_skips_cloud_and_embedding_models_and_returns_none_when_empty(self) -> None:
        preferences = ModelRoutingPreferences(Path("nonexistent-routing-file.json"))

        selected = preferences.choose("answer", None, {
            "default_model": "nomic-embed-text:latest",
            "models": [
                {"name": "remote:cloud"},
                {"name": "nomic-embed-text:latest"},
            ],
        })

        self.assertIsNone(selected)

    def test_unknown_area_is_rejected(self) -> None:
        preferences = ModelRoutingPreferences(Path("nonexistent-routing-file.json"))

        with self.assertRaisesRegex(ValueError, "Unknown model routing area"):
            preferences.choose("unknown", None, {})

    def test_async_resolver_uses_installed_area_priority(self) -> None:
        class FakeGateway:
            calls = 0

            async def invoke(self, plugin_id: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
                self.calls += 1
                return {
                    "default_model": "qwen3.6:latest",
                    "models": [{"name": "gemma:7b"}, {"name": "qwen3.6:latest"}],
                }

        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "priorities.json"
            path.write_text(json.dumps({
                "area_priorities": {"source_grounded": ["gemma:7b", "qwen3.6:latest"]},
            }), encoding="utf-8")
            preferences = ModelRoutingPreferences(path)
            gateway = FakeGateway()

            selected = asyncio.run(preferences.resolve(gateway, "source_grounded", None))  # type: ignore[arg-type]

        self.assertEqual(selected, "gemma:7b")
        self.assertEqual(gateway.calls, 1)

    def test_async_resolver_preserves_explicit_model_without_catalog_call(self) -> None:
        class FakeGateway:
            async def invoke(self, *_: Any) -> Any:
                raise AssertionError("An explicit model should not require catalog lookup.")

        preferences = ModelRoutingPreferences(Path("nonexistent-routing-file.json"))

        selected = asyncio.run(preferences.resolve(FakeGateway(), "planning", "deepseek-coder:6.7b"))  # type: ignore[arg-type]

        self.assertEqual(selected, "deepseek-coder:6.7b")


if __name__ == "__main__":
    unittest.main()