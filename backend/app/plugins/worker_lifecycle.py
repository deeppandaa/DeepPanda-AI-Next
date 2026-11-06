from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.plugins.gateway import PluginGateway, drain_tasks

T = TypeVar("T")
WorkerRegistry = set[asyncio.Task[None]] | dict[str, asyncio.Task[None]]
HEARTBEAT_INTERVAL_SECONDS = 15


async def _heartbeat(gateway: PluginGateway, worker: dict[str, str], logger: logging.Logger, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), HEARTBEAT_INTERVAL_SECONDS)
            return
        except TimeoutError:
            pass
        try:
            result = await gateway.invoke("jobs", "heartbeat", worker)
            if result["status"] not in {"running", "cancel_requested"}:
                return
        except Exception:
            logger.exception("Could not renew worker heartbeat for %s.", worker["job_id"])


def start_worker(
    factory: Callable[[], Awaitable[None]], registry: WorkerRegistry,
    gateway: PluginGateway, worker: dict[str, str], logger: logging.Logger, name: str,
) -> None:
    started = False

    async def run() -> None:
        nonlocal started
        started = True
        stop = asyncio.Event()
        heartbeat = asyncio.create_task(_heartbeat(gateway, worker, logger, stop), name=f"heartbeat-{worker['job_id']}")
        try:
            await factory()
        finally:
            stop.set()
            cancelled: asyncio.CancelledError | None = None
            while True:
                try:
                    await asyncio.shield(heartbeat)
                    break
                except asyncio.CancelledError as exc:
                    if heartbeat.cancelled():
                        raise
                    cancelled = exc
            if cancelled is not None:
                raise cancelled

    def register(task: asyncio.Task[None]) -> None:
        if isinstance(registry, dict):
            registry[worker["job_id"]] = task
        else:
            registry.add(task)

    def remove(task: asyncio.Task[None]) -> None:
        if isinstance(registry, dict):
            if registry.get(worker["job_id"]) is task:
                del registry[worker["job_id"]]
        else:
            registry.discard(task)

    def finished(task: asyncio.Task[None]) -> None:
        if task.cancelled() and not started:
            finalizer = asyncio.create_task(
                persist_cancellation(gateway, worker, logger), name=f"prestart-cancel-{worker['job_id']}",
            )
            register(finalizer)
            finalizer.add_done_callback(remove)
        remove(task)

    task = asyncio.create_task(run(), name=name)
    register(task)
    task.add_done_callback(finished)


async def drain_registered_workers(registry: WorkerRegistry) -> None:
    seen: set[asyncio.Task[None]] = set()
    errors: list[BaseException] = []
    while True:
        snapshot = set(registry.values()) if isinstance(registry, dict) else set(registry)
        pending = snapshot - seen
        if not pending:
            break
        seen.update(pending)
        try:
            await drain_tasks(pending)
        except BaseExceptionGroup as exc:
            errors.extend(exc.exceptions)
        # Already-done tasks can be gathered before their queued registry callbacks run.
        await asyncio.sleep(0)
    if errors:
        raise BaseExceptionGroup("Background worker drain failed.", errors)


async def run_thread(
    function: Callable[[], T], logger: logging.Logger, on_cancel: Callable[[T], None] | None = None,
) -> T:
    task = asyncio.create_task(asyncio.to_thread(function), name="local-worker-thread")
    cancelled: asyncio.CancelledError | None = None
    while True:
        try:
            result = await asyncio.shield(task)
            break
        except asyncio.CancelledError as exc:
            if task.cancelled():
                raise
            cancelled = exc
        except Exception as exc:
            if cancelled is None:
                raise
            logger.exception("Local worker thread failed after cancellation.")
            raise cancelled from exc
    if cancelled is not None:
        if on_cancel is not None:
            on_cancel(result)
        raise cancelled
    return result


async def persist_cancellation(gateway: PluginGateway, worker: dict[str, str], logger: logging.Logger) -> None:
    async def record() -> None:
        try:
            result = await gateway.invoke("jobs", "cancel", {"job_id": worker["job_id"], "approved": True})
            if result["status"] == "cancel_requested":
                await gateway.invoke("jobs", "fail", {**worker, "error": "Worker task cancelled."})
        except Exception:
            logger.exception("Could not persist worker cancellation for %s.", worker["job_id"])

    task = asyncio.create_task(record(), name=f"cancel-worker-{worker['job_id']}")
    while True:
        try:
            await asyncio.shield(task)
            return
        except asyncio.CancelledError:
            if task.cancelled():
                raise
