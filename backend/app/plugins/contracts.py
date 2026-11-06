from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class PluginManifest:
    plugin_id: str
    display_name: str
    description: str
    actions: tuple[str, ...]


class Plugin(Protocol):
    manifest: PluginManifest

    async def invoke(self, action: str, payload: dict[str, Any]) -> Any: ...


@runtime_checkable
class WorkerPlugin(Protocol):
    async def drain_workers(self) -> None: ...