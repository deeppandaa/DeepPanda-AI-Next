from __future__ import annotations

import asyncio
import logging
import queue
import threading
import time
from collections.abc import Awaitable, Callable
from concurrent.futures import Future
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any

from desktop.api import ApiError
from desktop.chat_context import ChatCancelled
from desktop.config import ensure_backend_importable

ensure_backend_importable()
from app.plugins.integration_errors import IntegrationUnavailableError

logger = logging.getLogger(__name__)
IDLE_SECONDS = 600
MAX_SERVERS = 4


@dataclass
class McpState:
    stack: AsyncExitStack
    sessions: dict[str, tuple[Any, list[dict[str, Any]], dict[str, str]]] = field(default_factory=dict)
    configuration: str | None = None

    async def reset(self) -> None:
        await self.stack.aclose()
        self.sessions.clear()
        self.configuration = None


Turn = Callable[[McpState], Awaitable[list[dict[str, Any]]]]


class ChatMcpRuntime:
    """Keep MCP contexts on one owner task; never serialize a live session."""

    def __init__(self) -> None:
        self._requests: queue.Queue[tuple[Turn, Future[list[dict[str, Any]]]] | None] = queue.Queue()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stopping = False
        self.closed = threading.Event()
        self._error: BaseException | None = None
        self._active: Future[list[dict[str, Any]]] | None = None

    def run(self, turn: Turn) -> list[dict[str, Any]]:
        future: Future[list[dict[str, Any]]] = Future()
        with self._lock:
            if self._stopping or self.closed.is_set():
                raise OSError("Canlı MCP oturumu kapandı/süresi doldu; tercihi kapatıp yeniden onaylayın.")
            self._requests.put((turn, future))
            if self._thread is None:
                self._thread = threading.Thread(target=self._main, name="chat-mcp-owner", daemon=True)
                self._thread.start()
        return future.result()

    def close(self) -> None:
        with self._lock:
            if not self._stopping:
                self._stopping = True
                self._requests.put(None)
            thread = self._thread
            if thread is None:
                self.closed.set()
        if thread is not None:
            thread.join(timeout=20)
            if thread.is_alive():
                raise OSError("Canlı MCP kapanışı henüz tamamlanmadı; sunucu/bağlantı durumunu inceleyin.")
        if self._error is not None:
            raise OSError("Canlı MCP oturumu veya kapanışı başarısız oldu; oturum yeniden kullanılamaz.") from self._error

    def _main(self) -> None:
        try:
            asyncio.run(self._serve())
        except (ExceptionGroup, asyncio.CancelledError, OSError, ValueError, RuntimeError,
                ApiError, IntegrationUnavailableError, ChatCancelled) as exc:
            self._error = exc
            logger.error("Live MCP owner failed (%s); session will not be reused.", type(exc).__name__)
        finally:
            if self._active is not None and not self._active.done() and self._error is None:
                self._error = RuntimeError("MCP owner exited before completing its request.")
                logger.error("Live MCP owner exited with an unfinished request; session will not be reused.")
            with self._lock:
                self._stopping = True
                self.closed.set()
            error = OSError("Canlı MCP oturumu kapandı; işlem tamamlanmadı ve otomatik tekrarlanmadı.")
            if self._active is not None and not self._active.done():
                self._active.set_exception(error)
            while True:
                try:
                    request = self._requests.get_nowait()
                except queue.Empty:
                    break
                if request is not None and not request[1].done():
                    request[1].set_exception(error)

    async def _serve(self) -> None:
        async with AsyncExitStack() as stack:
            state = McpState(stack)
            idle_since = time.monotonic()
            while True:
                try:
                    request = self._requests.get_nowait()
                except queue.Empty:
                    if time.monotonic() - idle_since >= IDLE_SECONDS:
                        return
                    await asyncio.sleep(0.05)
                    continue
                if request is None:
                    return
                turn, self._active = request
                try:
                    result = await turn(state)
                except (ApiError, IntegrationUnavailableError, ChatCancelled, OSError, ValueError, RuntimeError) as exc:
                    await state.reset()
                    # Consumers may clear traceback frames; never expose this still-running owner frame.
                    self._active.set_exception(exc.with_traceback(None))
                else:
                    self._active.set_result(result)
                self._active = None
                idle_since = time.monotonic()
