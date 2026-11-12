from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, ClassVar

import httpx
from app.plugins.gateway import (
    PluginActionNotFoundError,
    PluginGateway,
    PluginNotFoundError,
)

logger = logging.getLogger(__name__)


class ModelRoutingUnavailableError(ValueError):
    """No installed model satisfies the automatic routing health requirements."""


class ModelRoutingPreferences:
    areas: ClassVar[frozenset[str]] = frozenset(
        {
            "intent",
            "answer",
            "planning",
            "source_grounded",
            "learning",
            "code_change",
        }
    )

    def __init__(self, path: str | Path | None = None) -> None:
        self.brain_model = os.getenv("DEEPPANDA_BRAIN_MODEL", "").strip()
        if self.brain_model and (
            not re.fullmatch(
                r"qwen[a-zA-Z0-9_.-]*(?::[a-zA-Z0-9_.-]+)?", self.brain_model
            )
            or self.brain_model.casefold().endswith((":cloud", "-cloud"))
        ):
            raise ValueError("DEEPPANDA_BRAIN_MODEL must name a local Qwen model.")
        configured_path = path or os.getenv("MODEL_ROUTING_PREFERENCES")
        if configured_path is None:
            data_root = Path(os.getenv("AI_DATA_DIR", "/data")).expanduser()
            configured_path = data_root / "model-area-priorities.json"
        self.path = Path(configured_path).expanduser().resolve()

    def choose(
        self,
        area: str,
        requested_model: str | None,
        catalog: dict[str, Any] | None,
    ) -> str | None:
        if area not in self.areas:
            raise ValueError(f"Unknown model routing area: {area}")
        if isinstance(requested_model, str) and requested_model.strip():
            return requested_model.strip()
        if self.brain_model:
            return self.brain_model

        installed = self._installed_chat_models(catalog)
        if not installed:
            raise ModelRoutingUnavailableError(
                f"No installed local chat model is available for {area}."
            )
        preferences = self.report()
        profiles = preferences.get("model_profiles")
        priorities = self._area_priorities(area, preferences)
        measured = isinstance(profiles, dict)
        for candidate in priorities:
            if candidate in installed and (
                not measured or self._eligible(candidate, area, profiles, catalog)
            ):
                return candidate
        if measured:
            raise ModelRoutingUnavailableError(
                f"No healthy measured installed model is available for {area}. "
                "Check the model benchmark/status or select an explicit local model."
            )
        default_model = (
            catalog.get("default_model") if isinstance(catalog, dict) else None
        )
        if isinstance(default_model, str) and default_model in installed:
            return default_model
        return installed[0]

    async def resolve(
        self,
        gateway: PluginGateway,
        area: str,
        requested_model: str | None,
    ) -> str | None:
        if isinstance(requested_model, str) and requested_model.strip():
            return self.choose(area, requested_model, None)
        if self.brain_model:
            return self.choose(area, None, None)
        try:
            catalog = await gateway.invoke("ollama", "models", {})
        except (PluginNotFoundError, PluginActionNotFoundError, httpx.HTTPError):
            catalog = None
        return self.choose(area, None, catalog)

    def report(self) -> dict[str, Any]:
        """Return persisted benchmark preferences without opening the full response report."""
        try:
            preferences = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError:
            logger.warning(
                "Model routing preferences %s contain invalid JSON; using the installed default model.",
                self.path,
                exc_info=True,
            )
            return {}
        except OSError:
            logger.warning(
                "Could not read model routing preferences %s; using the installed default model.",
                self.path,
                exc_info=True,
            )
            return {}
        return preferences if isinstance(preferences, dict) else {}

    def _area_priorities(
        self, area: str, preferences: dict[str, Any] | None = None
    ) -> list[str]:
        if preferences is None:
            preferences = self.report()
        area_priorities = preferences.get("area_priorities")
        candidates = (
            area_priorities.get(area) if isinstance(area_priorities, dict) else None
        )
        if not isinstance(candidates, list):
            return []
        return [
            candidate
            for candidate in candidates
            if isinstance(candidate, str) and candidate.strip()
        ]

    @staticmethod
    def _eligible(
        name: str,
        area: str,
        profiles: dict[str, Any],
        catalog: dict[str, Any] | None,
    ) -> bool:
        profile = profiles.get(name)
        if (
            not isinstance(profile, dict)
            or profile.get("kind") != "chat"
            or profile.get("status") not in {"healthy", "degraded"}
        ):
            return False
        areas = profile.get("areas", {})
        details = areas.get(area, {}) if isinstance(areas, dict) else {}
        if (
            not isinstance(details, dict)
            or details.get("eligible") is not True
            or details.get("status") != "healthy"
        ):
            return False
        models = catalog.get("models", []) if isinstance(catalog, dict) else []
        current = next(
            (
                item
                for item in models
                if isinstance(item, dict)
                and (item.get("name") or item.get("model")) == name
            ),
            {},
        )
        return not (
            profile.get("digest")
            and current.get("digest")
            and profile["digest"] != current["digest"]
        )

    def describe_catalog(self, catalog: dict[str, Any]) -> dict[str, Any]:
        """Attach compact measured health/topic profiles for API and desktop clients."""
        preferences = self.report()
        profiles = preferences.get("model_profiles", {})
        if not isinstance(profiles, dict):
            profiles = {}
        result = dict(catalog)
        models = []
        for item in catalog.get("models", []):
            if not isinstance(item, dict):
                continue
            entry = dict(item)
            name = entry.get("name") or entry.get("model")
            profile = profiles.get(name) if isinstance(name, str) else None
            if isinstance(profile, dict):
                evaluation = dict(profile)
                if (
                    profile.get("digest")
                    and entry.get("digest")
                    and profile["digest"] != entry["digest"]
                ):
                    evaluation.update(
                        status="stale",
                        description="Model içeriği ölçümden sonra değişti; yeniden test gerekli.",
                        failure_reason="Installed digest differs from the measured digest.",
                        areas={
                            area: {**details, "eligible": False, "status": "stale"}
                            for area, details in profile.get("areas", {}).items()
                        },
                    )
            else:
                embedding = "embed" in str(name).casefold() or (
                    "embedding" in entry.get("capabilities", [])
                    and "completion" not in entry.get("capabilities", [])
                )
                evaluation = {
                    "kind": "embedding" if embedding else "chat",
                    "status": "untested",
                    "description": "Bu kurulu model için ölçülmüş profil yok.",
                    "failure_reason": None,
                    "areas": {},
                }
            entry["evaluation"] = evaluation
            models.append(entry)
        result["models"] = models
        result["routing"] = {
            key: preferences.get(key)
            for key in (
                "generated_at",
                "area_priorities",
                "area_descriptions",
                "source",
                "note",
                "benchmark_report",
                "ranking_policy",
            )
        }
        result["routing"]["brain_model_override"] = self.brain_model or None
        result["routing"]["available_priorities"] = {
            area: [
                candidate
                for candidate in self._area_priorities(area, preferences)
                if candidate in self._installed_chat_models(catalog)
                and (
                    not isinstance(preferences.get("model_profiles"), dict)
                    or self._eligible(candidate, area, profiles, catalog)
                )
            ]
            for area in sorted(self.areas)
        }
        return result

    @staticmethod
    def _installed_chat_models(catalog: dict[str, Any] | None) -> list[str]:
        models = catalog.get("models", []) if isinstance(catalog, dict) else []
        names = []
        for item in models:
            if not isinstance(item, dict):
                continue
            name = item.get("name") or item.get("model")
            if not isinstance(name, str) or not name.strip():
                continue
            normalized = name.strip()
            if "embed" in normalized.casefold() or normalized.casefold().endswith(
                ("-cloud", ":cloud")
            ):
                continue
            capabilities = item.get("capabilities", [])
            if "embedding" in capabilities and "completion" not in capabilities:
                continue
            if normalized not in names:
                names.append(normalized)
        return names
