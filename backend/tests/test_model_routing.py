from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from app.model_routing import ModelRoutingPreferences, ModelRoutingUnavailableError


class ModelRoutingPreferencesTests(unittest.TestCase):
    def test_selects_first_installed_model_in_area_priority(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "priorities.json"
            path.write_text(
                json.dumps(
                    {
                        "area_priorities": {
                            "planning": ["missing:latest", "gemma:7b", "qwen3.6:latest"]
                        },
                    }
                ),
                encoding="utf-8",
            )
            preferences = ModelRoutingPreferences(path)

            selected = preferences.choose(
                "planning",
                None,
                {
                    "default_model": "qwen3.6:latest",
                    "models": [
                        {"name": "nomic-embed-text:latest"},
                        {"name": "qwen3.6:latest"},
                        {"name": "gemma:7b"},
                    ],
                },
            )

        self.assertEqual(selected, "gemma:7b")

    def test_explicit_user_model_overrides_benchmark_priority(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "priorities.json"
            path.write_text(
                json.dumps({"area_priorities": {"answer": ["qwen3.6:latest"]}}),
                encoding="utf-8",
            )
            selected = ModelRoutingPreferences(path).choose(
                "answer",
                "deepseek-coder:6.7b",
                {"models": [{"name": "qwen3.6:latest"}]},
            )

        self.assertEqual(selected, "deepseek-coder:6.7b")

    def test_invalid_or_missing_preferences_fall_back_to_installed_default(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "missing.json"
            selected = ModelRoutingPreferences(path).choose(
                "code_change",
                None,
                {
                    "default_model": "qwen3.6:latest",
                    "models": [
                        {"name": "qwen3.6:latest"},
                        {"name": "nomic-embed-text:latest"},
                    ],
                },
            )

        self.assertEqual(selected, "qwen3.6:latest")

    def test_skips_cloud_and_embedding_models_and_fails_visibly_when_empty(
        self,
    ) -> None:
        preferences = ModelRoutingPreferences(Path("nonexistent-routing-file.json"))

        with self.assertRaises(ModelRoutingUnavailableError):
            preferences.choose(
                "answer",
                None,
                {
                    "default_model": "nomic-embed-text:latest",
                    "models": [
                        {"name": "remote:cloud"},
                        {"name": "nomic-embed-text:latest"},
                        {"name": "renamed-vector-model", "capabilities": ["embedding"]},
                    ],
                },
            )

    def test_unknown_area_is_rejected(self) -> None:
        preferences = ModelRoutingPreferences(Path("nonexistent-routing-file.json"))

        with self.assertRaisesRegex(ValueError, "Unknown model routing area"):
            preferences.choose("unknown", None, {})

    def test_async_resolver_uses_installed_area_priority(self) -> None:
        class FakeGateway:
            calls = 0

            async def invoke(
                self, plugin_id: str, action: str, payload: dict[str, Any]
            ) -> dict[str, Any]:
                self.calls += 1
                return {
                    "default_model": "qwen3.6:latest",
                    "models": [{"name": "gemma:7b"}, {"name": "qwen3.6:latest"}],
                }

        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "priorities.json"
            path.write_text(
                json.dumps(
                    {
                        "area_priorities": {
                            "source_grounded": ["gemma:7b", "qwen3.6:latest"]
                        },
                    }
                ),
                encoding="utf-8",
            )
            preferences = ModelRoutingPreferences(path)
            gateway = FakeGateway()

            selected = asyncio.run(
                preferences.resolve(gateway, "source_grounded", None)
            )  # type: ignore[arg-type]

        self.assertEqual(selected, "gemma:7b")
        self.assertEqual(gateway.calls, 1)

    def test_async_resolver_preserves_explicit_model_without_catalog_call(self) -> None:
        class FakeGateway:
            async def invoke(self, *_: Any) -> Any:
                raise AssertionError(
                    "An explicit model should not require catalog lookup."
                )

        preferences = ModelRoutingPreferences(Path("nonexistent-routing-file.json"))

        selected = asyncio.run(
            preferences.resolve(FakeGateway(), "planning", "deepseek-coder:6.7b")
        )  # type: ignore[arg-type]

        self.assertEqual(selected, "deepseek-coder:6.7b")

    def test_measured_routing_excludes_unhealthy_stale_and_unmeasured_candidates(
        self,
    ) -> None:
        profiles = {
            "failed": {
                "kind": "chat",
                "status": "unavailable",
                "areas": {"answer": {"eligible": True, "status": "healthy"}},
            },
            "stale": {
                "kind": "chat",
                "status": "healthy",
                "digest": "old",
                "areas": {"answer": {"eligible": True, "status": "healthy"}},
            },
            "good": {
                "kind": "chat",
                "status": "healthy",
                "areas": {"answer": {"eligible": True, "status": "healthy"}},
            },
        }
        preferences = ModelRoutingPreferences(Path("unused.json"))
        data = {
            "area_priorities": {"answer": ["failed", "stale", "unmeasured", "good"]},
            "model_profiles": profiles,
        }
        catalog = {
            "default_model": "failed",
            "models": [
                {"name": name, "digest": "new"}
                for name in ("failed", "stale", "unmeasured", "good")
            ],
        }
        with patch.object(preferences, "report", return_value=data):
            self.assertEqual(preferences.choose("answer", None, catalog), "good")
            catalog["models"].pop()
            with self.assertRaisesRegex(
                ModelRoutingUnavailableError, "healthy measured"
            ):
                preferences.choose("answer", None, catalog)
            self.assertEqual(preferences.choose("answer", "failed", catalog), "failed")

    def test_catalog_profiles_mark_stale_digest_without_mutating_input(self) -> None:
        preferences = ModelRoutingPreferences(Path("unused.json"))
        data = {
            "model_profiles": {
                "model": {
                    "kind": "chat",
                    "status": "healthy",
                    "digest": "old",
                    "areas": {"answer": {"eligible": True, "status": "healthy"}},
                }
            },
            "area_priorities": {"answer": ["model"]},
        }
        catalog = {
            "models": [
                {"name": "model", "digest": "new"},
                {"name": "nomic-embed-text:latest"},
            ]
        }
        with patch.object(preferences, "report", return_value=data):
            result = preferences.describe_catalog(catalog)
        self.assertNotIn("evaluation", catalog["models"][0])
        self.assertEqual(result["models"][0]["evaluation"]["status"], "stale")
        self.assertFalse(
            result["models"][0]["evaluation"]["areas"]["answer"]["eligible"]
        )
        self.assertEqual(result["models"][1]["evaluation"]["kind"], "embedding")
        self.assertEqual(result["models"][1]["evaluation"]["status"], "untested")
        self.assertEqual(result["routing"]["available_priorities"]["answer"], [])


if __name__ == "__main__":
    unittest.main()
