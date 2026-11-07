from __future__ import annotations

import traceback
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot


class _Relay(QObject):
    """Lives in the GUI thread so worker results are always delivered there (queued connection)."""

    finished = Signal(object)
    failed = Signal(object)

    def __init__(self, on_done: Callable[[Any], None] | None, on_error: Callable[[Exception], None] | None) -> None:
        super().__init__()
        self._on_done = on_done
        self._on_error = on_error
        self.finished.connect(self._deliver_done)
        self.failed.connect(self._deliver_error)

    @Slot(object)
    def _deliver_done(self, result: Any) -> None:
        _ACTIVE.discard(self)
        if self._on_done is not None:
            self._on_done(result)

    @Slot(object)
    def _deliver_error(self, error: Exception) -> None:
        _ACTIVE.discard(self)
        if self._on_error is not None:
            self._on_error(error)


class _Job(QRunnable):
    def __init__(self, fn: Callable[[], Any], relay: _Relay) -> None:
        super().__init__()
        self.fn = fn
        self.relay = relay

    def run(self) -> None:
        try:
            result = self.fn()
        except Exception as exc:  # noqa: BLE001 - every failure is shown to the user
            exc.__dict__.setdefault("trace", traceback.format_exc())
            self.relay.failed.emit(exc)
        else:
            self.relay.finished.emit(result)


_ACTIVE: set[_Relay] = set()


def run_background(
    fn: Callable[[], Any],
    on_done: Callable[[Any], None] | None = None,
    on_error: Callable[[Exception], None] | None = None,
) -> None:
    relay = _Relay(on_done, on_error)
    _ACTIVE.add(relay)
    QThreadPool.globalInstance().start(_Job(fn, relay))
