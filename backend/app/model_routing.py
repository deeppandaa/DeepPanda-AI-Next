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


class ModelRoutingPreferences:
    areas: ClassVar[frozenset[str]] = frozenset({
        "intent", "answer", "planning", "source_grounded", "learning", "code_change",
    })

    def __init__(self, path: str | Path | None = None) -> None:
        self.brain_model = os.getenv("DEEPPANDA_BRAIN_MODEL", "").strip()
        if self.brain_model and (
            not re.fullmatch(r"qwen[a-zA-Z0-9_.-]*(?::[a-zA-Z0-9_.-]+)?", self.brain_model)
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
            return None
        priorities = self._area_priorities(area)
        for candidate in priorities:
            if candidate in installed:
                return candidate
        default_model = catalog.get("default_model") if isinstance(catalog, dict) else None
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

    def _area_priorities(self, area: str) -> list[str]:
        try:
            preferences = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except json.JSONDecodeError:
            logger.warning(
                "Model routing preferences %s contain invalid JSON; using the installed default model.",
                self.path,
                exc_info=True,
            )
            return []
        except OSError:
            logger.warning(
                "Could not read model routing preferences %s; using the installed default model.",
                self.path,
                exc_info=True,
            )
            return []
        area_priorities = preferences.get("area_priorities") if isinstance(preferences, dict) else None
        candidates = area_priorities.get(area) if isinstance(area_priorities, dict) else None
        if not isinstance(candidates, list):
            return []
        return [candidate for candidate in candidates if isinstance(candidate, str) and candidate.strip()]

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
            if "embed" in normalized.casefold() or normalized.casefold().endswith(("-cloud", ":cloud")):
                continue
            if normalized not in names:
                names.append(normalized)
        return names