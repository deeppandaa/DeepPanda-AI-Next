from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from typing import Any

from app.plugins.gateway import PluginGateway
from fastapi import HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
EventSink = Callable[[dict[str, Any]], Awaitable[None]]
_sink: ContextVar[EventSink | None] = ContextVar("chat_event_sink", default=None)
_completion: ContextVar[bool] = ContextVar("chat_completion_stream", default=False)


async def emit(event: dict[str, Any]) -> None:
    sink = _sink.get()
    if sink is not None:
        await sink(event)


async def progress(stage: str, detail: str) -> None:
    await emit({"type": "progress", "stage": stage, "message": detail, "detail": detail})


def completion_streaming() -> bool:
    return _sink.get() is not None and _completion.get()


class ChatProgressGateway(PluginGateway):
    def __init__(self, gateway: PluginGateway) -> None:
        self.gateway = gateway

    async def invoke(self, plugin_id: str, action: str, payload: dict[str, Any] | None = None) -> Any:
        if (plugin_id, action) != ("ollama", "chat"):
            await progress("tool", f"{plugin_id}.{action}: running")
        return await self.gateway.invoke(plugin_id, action, payload)


@contextmanager
def completion_scope() -> Iterator[None]:
    token = _completion.set(True)
    try:
        yield
    finally:
        _completion.reset(token)


def error_event(status: int, detail: Any, body: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "type": "error",
        "status": status,
        "detail": detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False),
        "body": body if body is not None else {"detail": detail},
    }


async def stream_chat(
    run: Callable[[], Awaitable[Any]], heartbeat_seconds: float = 1.0,
) -> AsyncIterator[bytes]:
    """A bounded producer cancelled by StreamingResponse when the client disconnects."""
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=32)

    async def produce() -> None:
        token = _sink.set(queue.put)
        try:
            result = await run()
            if isinstance(result, JSONResponse):
                body = json.loads(bytes(result.body))
                await queue.put(error_event(result.status_code, body.get("detail", "Chat failed."), body))
            else:
                await queue.put({"type": "result", "result": result})
        except HTTPException as exc:
            await queue.put(error_event(exc.status_code, exc.detail))
        except Exception:
            logger.exception("Chat stream failed.")
            await queue.put(error_event(500, "Internal chat error."))
        finally:
            _sink.reset(token)

    task = asyncio.create_task(produce(), name="chat-stream")
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=heartbeat_seconds)
            except TimeoutError:
                event = {"type": "heartbeat"}
            yield (json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
            if event["type"] in {"result", "error"}:
                break
    finally:
        if not task.done():
            task.cancel()
        with suppress(asyncio.CancelledError):
            await task
