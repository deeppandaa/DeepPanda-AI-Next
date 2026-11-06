from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Iterable
from typing import Any, ClassVar

from app.plugins.contracts import Plugin, WorkerPlugin


class PluginError(Exception):
    pass


class PluginNotFoundError(PluginError):
    pass


class PluginActionNotFoundError(PluginError):
    pass


class PluginShuttingDownError(PluginError, RuntimeError):
    pass


async def drain_tasks(tasks: Iterable[Awaitable[None]]) -> None:
    results = await asyncio.gather(*tasks, return_exceptions=True)
    errors = [result for result in results if isinstance(result, BaseException)]
    if errors:
        raise BaseExceptionGroup("Background worker drain failed.", errors)


class PluginGateway:
    """The only dispatch point between application services and plugins."""

    _work_actions: ClassVar[dict[str, frozenset[str]]] = {
        "media": frozenset({"start_video", "resume_job", "generate_image", "edit_image", "edit_video", "analyze"}),
        "evaluation": frozenset({"run", "resume_job"}),
        "speech": frozenset({"synthesize", "transcribe"}),
        "ocr": frozenset({"status", "extract"}),
        "system": frozenset({"hardware", "model_assets", "readiness"}),
        "codegraph": frozenset({"build"}),
        "diagnostics": frozenset({"scan"}),
        "workspace": frozenset({"run"}),
        "research": frozenset({"start", "start_github", "resume_job"}),
        "jobs": frozenset({"create", "retry"}),
        "prompt_library": frozenset({"sync", "local_search", "online_search", "online_get"}),
        "legacy_history": frozenset({"candidates", "list", "detail"}),
        "memory": frozenset({"legacy_list", "legacy_get"}),
    }

    def __init__(self) -> None:
        self._plugins: dict[str, Plugin] = {}
        self._closing = False
        self._starting: dict[asyncio.Task[Any], int] = {}
        self._starts_drained = asyncio.Event()
        self._starts_drained.set()
        self._shutdown_task: asyncio.Task[None] | None = None

    def begin_shutdown(self) -> None:
        self._closing = True

    async def shutdown(self) -> None:
        self.begin_shutdown()
        if self._shutdown_task is None:
            self._shutdown_task = asyncio.create_task(self._drain(), name="plugin-worker-drain")
        cancelled: asyncio.CancelledError | None = None
        while True:
            try:
                await asyncio.shield(self._shutdown_task)
                break
            except asyncio.CancelledError as exc:
                if self._shutdown_task.cancelled():
                    raise
                # Defer caller cancellation until workers have persisted results and cleaned files.
                cancelled = exc
        if cancelled is not None:
            raise cancelled

    async def _drain(self) -> None:
        await self._starts_drained.wait()
        await drain_tasks(
            plugin.drain_workers() for plugin in self._plugins.values() if isinstance(plugin, WorkerPlugin)
        )

    def register(self, plugin: Plugin) -> None:
        plugin_id = plugin.manifest.plugin_id
        if plugin_id in self._plugins:
            raise ValueError(f"Plugin already registered: {plugin_id}")
        self._plugins[plugin_id] = plugin

    def list_plugins(self) -> list[dict[str, Any]]:
        return [
            {
                "id": plugin.manifest.plugin_id,
                "name": plugin.manifest.display_name,
                "description": plugin.manifest.description,
                "actions": list(plugin.manifest.actions),
            }
            for plugin in self._plugins.values()
        ]

    async def invoke(self, plugin_id: str, action: str, payload: dict[str, Any] | None = None) -> Any:
        plugin = self._plugins.get(plugin_id)
        if plugin is None:
            raise PluginNotFoundError(plugin_id)
        if action not in plugin.manifest.actions:
            raise PluginActionNotFoundError(f"{plugin_id}:{action}")
        if action not in self._work_actions.get(plugin_id, frozenset()):
            return await plugin.invoke(action, payload or {})
        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("Plugin work requires an asyncio task.")
        # Nested dispatch belongs to the already admitted starter, not to new workers.
        if self._closing and task not in self._starting:
            raise PluginShuttingDownError("Application is shutting down; new work is not accepted.")
        self._starting[task] = self._starting.get(task, 0) + 1
        self._starts_drained.clear()
        try:
            return await plugin.invoke(action, payload or {})
        finally:
            self._starting[task] -= 1
            if self._starting[task] == 0:
                del self._starting[task]
            if not self._starting:
                self._starts_drained.set()