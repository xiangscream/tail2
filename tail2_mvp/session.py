"""Bridge session life-cycle.

A transport failure quarantines the SDK bridge. The runtime isolates the failed
session and rebuilds it explicitly, bumping the camera epoch and clearing
frame-bound state so stale targets/ROIs cannot survive reconnect.
"""
from __future__ import annotations

import threading
from typing import Callable

from .bridge import BridgeError
from .runtime import ResourceOwnership, StateRegistry

EPOCH_BOUND_STATE = ("observation", "target", "track", "framing", "look", "media", "orientation")


class RuntimeSession:
    def __init__(self, factory: Callable[[], object], *, state: StateRegistry | None = None,
                 ownership: ResourceOwnership | None = None,
                 on_rebuild: Callable[[int], None] | None = None):
        self._factory = factory
        self._bridge = factory()
        self.state = state
        self.ownership = ownership
        self._on_rebuild = on_rebuild
        self.camera_epoch = 0
        self.rebuilds = 0
        self._lock = threading.Lock()

    @property
    def bridge(self):
        with self._lock:
            return self._bridge

    def request(self, op: str, args: dict | None = None, *, timeout: float = 20):
        with self._lock:
            bridge = self._bridge
        try:
            return bridge.request(op, args or {}, timeout=timeout)
        except BridgeError:
            self.rebuild("bridge transport failure")
            raise

    def rebuild(self, reason: str = "explicit") -> int:
        with self._lock:
            try:
                self._bridge.close()
            except Exception:
                pass
            self._bridge = self._factory()
            self.camera_epoch += 1
            self.rebuilds += 1
            epoch = self.camera_epoch
        if self.ownership:
            self.ownership.clear()
        if self.state:
            self.state.clear(*EPOCH_BOUND_STATE)
        if self._on_rebuild:
            self._on_rebuild(epoch)
        return epoch

    def close(self) -> None:
        with self._lock:
            try:
                self._bridge.close()
            except Exception:
                pass

    def set_rebuild_hook(self, callback: Callable[[int], None]) -> None:
        self._on_rebuild = callback
