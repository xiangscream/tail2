"""Bounded device discovery, last-good state with freshness, and UVC conflict hints."""
from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable

TAIL2_PRODUCT_TYPE = 11
KNOWN_UVC_CONSUMERS = ("obsbot_center.exe", "obsbot_main.exe")


@dataclass
class LastGood:
    stale_after_s: float = 3.0
    value: Any = None
    source_mono: float | None = None
    error: str | None = None
    updates: int = field(default=0)

    def update(self, value: Any, source_mono: float) -> None:
        self.value = value
        self.source_mono = source_mono
        self.error = None
        self.updates += 1

    def fail(self, error: Any) -> None:
        self.error = str(error)

    def read(self, now_mono: float) -> dict:
        if self.value is None or self.source_mono is None:
            return {"value": None, "stale": True, "source_mono": None, "age_s": None,
                    "error": self.error, "updates": self.updates}
        age = now_mono - self.source_mono
        return {"value": self.value, "stale": age > self.stale_after_s or self.error is not None,
                "source_mono": self.source_mono, "age_s": age, "error": self.error,
                "updates": self.updates}


def discover_tail2(request: Callable[[str, dict], dict], *, timeout: float = 15.0,
                   interval: float = 1.0, per_call_wait_ms: int = 1500,
                   clock: Callable[[], float] = time.monotonic,
                   sleep: Callable[[float], None] = time.sleep) -> dict:
    if timeout <= 0 or interval < 0 or per_call_wait_ms < 0:
        raise ValueError("invalid discovery parameters")
    deadline = clock() + timeout
    last_error: str | None = None
    while True:
        try:
            response = request("device.list", {"wait_ms": per_call_wait_ms})
            devices = response.get("result", {}).get("devices", []) if response.get("ok") else []
            for device in devices:
                if device.get("product_type") == TAIL2_PRODUCT_TYPE and device.get("eligible"):
                    return device
        except Exception as exc:
            last_error = str(exc)
        if clock() >= deadline:
            raise TimeoutError(f"no eligible Tail2 UVC device within {timeout}s; last_error={last_error}")
        sleep(interval)


def list_windows_processes() -> list[str]:
    if sys.platform != "win32":
        return []
    try:
        output = subprocess.check_output(["tasklist", "/fo", "csv", "/nh"], text=True, timeout=5,
                                         errors="replace")
    except (OSError, subprocess.SubprocessError):
        return []
    names = []
    for line in output.splitlines():
        if line.startswith('"'):
            names.append(line.split('","', 1)[0].strip('"').lower())
    return names


def detect_uvc_conflicts(list_processes: Callable[[], list[str]] = list_windows_processes,
                         known: tuple[str, ...] = KNOWN_UVC_CONSUMERS) -> list[str]:
    running = {name.lower() for name in list_processes()}
    return sorted(name for name in known if name in running)
