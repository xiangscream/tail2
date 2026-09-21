"""Capability Runtime foundation contract.

A capability is a product-level primitive (observation, target, track, framing,
look, media, status, stop). Callers never touch the vendor SDK. This module owns
lifecycle, evidence separation, single-writer scheduling, resource ownership,
cancellation and deadlines. It performs no device action by itself; adapters do.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class Execution(str, Enum):
    ACCEPTED = "accepted"
    RUNNING = "running"
    REOBSERVE_REQUIRED = "reobserve_required"
    COMPLETED = "completed"
    CONSTRAINED = "constrained"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INDETERMINATE = "indeterminate"


SIDE_EFFECTING = {
    "target.select", "target.clear", "track.start", "track.stop", "framing.set",
    "look.nudge", "look.stop", "capture.photo", "record.start", "record.stop",
    "position.recall", "task.cancel", "device.stop_all",
}


class RuntimeError_(RuntimeError):
    pass


class Cancelled(RuntimeError_):
    pass


class DeadlineExceeded(RuntimeError_):
    pass


class ReobserveRequired(RuntimeError_):
    def __init__(self, reason: str, continuation_id: str, requested: dict | None = None):
        super().__init__(reason)
        self.reason = reason
        self.continuation_id = continuation_id
        self.requested = requested or {}


class ResourceBusy(RuntimeError_):
    pass


class CapabilityRejected(RuntimeError_):
    pass


@dataclass(frozen=True)
class CapabilityError:
    code: str
    message: str
    retryable: bool = False
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message,
                "retryable": self.retryable, "detail": self.detail}


@dataclass(frozen=True)
class CapabilityRequest:
    capability: str
    args: dict = field(default_factory=dict)
    request_id: str = ""
    task_id: str = ""
    observation_id: str | None = None
    deadline_s: float | None = None
    caller: str = "unknown"

    def __post_init__(self):
        if not self.capability:
            raise ValueError("capability required")
        if self.deadline_s is not None and (self.deadline_s <= 0 or self.deadline_s > 3600):
            raise ValueError("invalid deadline")
        object.__setattr__(self, "request_id", self.request_id or uuid.uuid4().hex)
        object.__setattr__(self, "task_id", self.task_id or self.request_id)


@dataclass
class CapabilityResult:
    request_id: str
    task_id: str
    capability: str
    execution: Execution
    requested: dict = field(default_factory=dict)
    sdk_reported: dict = field(default_factory=dict)
    visual_check: dict | None = None
    artifact: dict | None = None
    errors: list[CapabilityError] = field(default_factory=list)
    continuation_id: str | None = None
    payload: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"request_id": self.request_id, "task_id": self.task_id, "capability": self.capability,
                "execution": self.execution.value, "requested": self.requested,
                "sdk_reported": self.sdk_reported, "visual_check": self.visual_check,
                "artifact": self.artifact, "errors": [e.to_dict() for e in self.errors],
                "continuation_id": self.continuation_id, "payload": self.payload}


class CancelToken:
    def __init__(self):
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise Cancelled("cancelled")


class Deadline:
    def __init__(self, seconds: float, clock: Callable[[], float] = time.monotonic):
        self._at = clock() + seconds
        self._clock = clock

    def expired(self) -> bool:
        return self._clock() >= self._at

    def remaining(self) -> float:
        return max(0.0, self._at - self._clock())

    def raise_if_expired(self) -> None:
        if self.expired():
            raise DeadlineExceeded("deadline exceeded")


@dataclass
class StateEntry:
    value: Any = None
    source: str = "none"
    source_mono: float | None = None
    error: str | None = None
    unsupported: bool = False
    updates: int = 0


class StateRegistry:
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self._state: dict[str, StateEntry] = {}

    def set(self, key: str, value: Any, source: str = "sdk") -> StateEntry:
        with self._lock:
            previous = self._state.get(key)
            entry = StateEntry(value=value, source=source, source_mono=self._clock(),
                               error=None, unsupported=False,
                               updates=(previous.updates + 1) if previous else 1)
            self._state[key] = entry
            return entry

    def fail(self, key: str, error: Any) -> StateEntry:
        with self._lock:
            entry = self._state.get(key) or StateEntry()
            entry.error = str(error)
            self._state[key] = entry
            return entry

    def mark_unsupported(self, key: str, note: str = "unsupported") -> StateEntry:
        with self._lock:
            entry = StateEntry(value=None, source="unsupported", source_mono=self._clock(),
                               unsupported=True, error=note)
            self._state[key] = entry
            return entry

    def read(self, key: str, *, stale_after_s: float) -> dict:
        with self._lock:
            entry = self._state.get(key)
        if entry is None:
            return {"value": None, "source": "none", "age_s": None, "stale": True,
                    "error": None, "unsupported": False, "updates": 0}
        age = None if entry.source_mono is None else self._clock() - entry.source_mono
        stale = entry.value is None or entry.unsupported or entry.error is not None or \
            (age is not None and age > stale_after_s)
        return {"value": entry.value, "source": entry.source, "age_s": age, "stale": stale,
                "error": entry.error, "unsupported": entry.unsupported, "updates": entry.updates}

    def clear(self, *keys: str) -> None:
        with self._lock:
            for key in keys:
                self._state.pop(key, None)

    def keys(self) -> list[str]:
        with self._lock:
            return sorted(self._state)


class ResourceOwnership:
    def __init__(self):
        self._lock = threading.Lock()
        self._owner: dict[str, str] = {}

    def acquire(self, resource: str, owner: str) -> None:
        with self._lock:
            current = self._owner.get(resource)
            if current is not None and current != owner:
                raise ResourceBusy(f"{resource} is owned by {current}")
            self._owner[resource] = owner

    def release(self, resource: str, owner: str) -> None:
        with self._lock:
            if self._owner.get(resource) == owner:
                del self._owner[resource]

    def release_all(self, owner: str) -> None:
        with self._lock:
            for resource in [r for r, o in self._owner.items() if o == owner]:
                del self._owner[resource]

    def owner(self, resource: str) -> str | None:
        with self._lock:
            return self._owner.get(resource)

    def clear(self) -> None:
        with self._lock:
            self._owner.clear()

    def held(self) -> dict[str, str]:
        with self._lock:
            return dict(self._owner)


class SingleWriter:
    def __init__(self):
        self._lock = threading.RLock()

    def run(self, fn: Callable[[], Any], token: CancelToken | None = None):
        with self._lock:
            if token is not None:
                token.raise_if_cancelled()
            return fn()


class CapabilityRuntime:
    def __init__(self, *, clock: Callable[[], float] = time.monotonic,
                 state: StateRegistry | None = None, ownership: ResourceOwnership | None = None):
        self._clock = clock
        self.state = state or StateRegistry(clock=clock)
        self.ownership = ownership or ResourceOwnership()
        self._handlers: dict[str, Callable[[CapabilityRequest, CancelToken, Deadline | None], Any]] = {}
        self._resources: dict[str, tuple[str, ...]] = {}
        self._writer = SingleWriter()
        self._lock = threading.Lock()
        self._tokens: dict[str, CancelToken] = {}

    def register(self, capability: str, handler, *, resources: tuple[str, ...] = ()) -> None:
        if not capability:
            raise ValueError("capability required")
        with self._lock:
            self._handlers[capability] = handler
            self._resources[capability] = tuple(resources)

    def capabilities(self) -> list[str]:
        with self._lock:
            return sorted(self._handlers)

    def active_requests(self) -> list[str]:
        with self._lock:
            return sorted(self._tokens)

    def cancel(self, identifier: str) -> bool:
        with self._lock:
            token = self._tokens.get(identifier)
        if token is None:
            return False
        token.cancel()
        return True

    def cancel_all(self) -> int:
        with self._lock:
            tokens = list(self._tokens.values())
        for token in tokens:
            token.cancel()
        return len(tokens)

    def execute(self, request: CapabilityRequest) -> CapabilityResult:
        with self._lock:
            handler = self._handlers.get(request.capability)
            resources = self._resources.get(request.capability, ())
        if handler is None:
            return self._result(request, Execution.UNSUPPORTED,
                                errors=[CapabilityError("unsupported", f"no handler for {request.capability}")])
        token = CancelToken()
        owner = request.task_id
        with self._lock:
            self._tokens[owner] = token
            self._tokens[request.request_id] = token
        deadline = Deadline(request.deadline_s, self._clock) if request.deadline_s else None
        acquired: list[str] = []
        side_effecting = request.capability in SIDE_EFFECTING
        try:
            for resource in resources:
                self.ownership.acquire(resource, owner)
                acquired.append(resource)
            if deadline:
                deadline.raise_if_expired()

            def run():
                return handler(request, token, deadline)

            output = self._writer.run(run, token)
            return self._from_output(request, output)
        except ReobserveRequired as exc:
            return self._result(request, Execution.REOBSERVE_REQUIRED, requested=exc.requested,
                                continuation_id=exc.continuation_id,
                                errors=[CapabilityError("reobserve_required", str(exc))])
        except Cancelled:
            return self._result(request, Execution.CANCELLED, errors=[CapabilityError("cancelled", "cancelled")])
        except DeadlineExceeded:
            execution = Execution.INDETERMINATE if side_effecting else Execution.FAILED
            return self._result(request, execution, errors=[CapabilityError("deadline", "deadline exceeded")])
        except ResourceBusy as exc:
            return self._result(request, Execution.FAILED, errors=[CapabilityError("busy", str(exc))])
        except CapabilityRejected as exc:
            return self._result(request, Execution.FAILED, errors=[CapabilityError("rejected", str(exc))])
        except UnsupportedCapability as exc:
            return self._result(request, Execution.UNSUPPORTED, errors=[CapabilityError("unsupported", str(exc))])
        except Constrained as exc:
            return self._result(request, Execution.CONSTRAINED, errors=[CapabilityError("constrained", str(exc))])
        except Exception as exc:
            execution = Execution.INDETERMINATE if side_effecting else Execution.FAILED
            return self._result(request, execution, errors=[CapabilityError("failed", str(exc))])
        finally:
            for resource in acquired:
                self.ownership.release(resource, owner)
            with self._lock:
                self._tokens.pop(request.request_id, None)
                if self._tokens.get(owner) is token:
                    self._tokens.pop(owner, None)

    def _from_output(self, request: CapabilityRequest, output: Any) -> CapabilityResult:
        if isinstance(output, CapabilityResult):
            return output
        data = output or {}
        return self._result(request, data.get("execution", Execution.COMPLETED),
                            requested=data.get("requested"), sdk_reported=data.get("sdk_reported"),
                            visual_check=data.get("visual_check"), artifact=data.get("artifact"),
                            errors=data.get("errors"), continuation_id=data.get("continuation_id"),
                            payload=data.get("payload"))

    def _result(self, request: CapabilityRequest, execution: Execution, *,
                requested=None, sdk_reported=None, visual_check=None, artifact=None,
                errors=None, continuation_id=None, payload=None) -> CapabilityResult:
        return CapabilityResult(request_id=request.request_id, task_id=request.task_id,
                                capability=request.capability, execution=execution,
                                requested=requested or {}, sdk_reported=sdk_reported or {},
                                visual_check=visual_check, artifact=artifact,
                                errors=list(errors or []), continuation_id=continuation_id,
                                payload=payload or {})


class UnsupportedCapability(RuntimeError_):
    pass


class Constrained(RuntimeError_):
    pass
