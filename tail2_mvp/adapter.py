"""Thin Tail2 adapter: map product capabilities onto the supervised Observer.

The adapter is the only place that knows device quirks (Track entry, AI toggle,
REOBSERVE). It translates observer output into CapabilityResult evidence and
raises runtime-level signals (ReobserveRequired, Constrained, UnsupportedCapability)
so callers never see SDK details.

Contract rules enforced here:
- The first-class ``request.observation_id`` is authoritative. If ``args`` also
  carries an observation_id and it differs, the request is rejected. The adapter
  injects the first-class value into the device call.
- Deadlines are cooperative: the remaining time is passed to the observer / bridge
  so a slow synchronous SDK call times out at the bridge and quarantines the
  session; it is not a hard interrupt guarantee.
"""
from __future__ import annotations

from typing import Any, Callable

from .runtime import (
    CapabilityRejected, CapabilityRequest, Constrained, Execution, ReobserveRequired,
    UnsupportedCapability,
)

FRAMING_MODES = {"normal", "full_body", "half_body", "close_up"}
MIN_TIMEOUT = 0.05
MAX_TIMEOUT = 60.0


class Tail2Adapter:
    def __init__(self, observer, *, clock: Callable[[], float] | None = None):
        self.observer = observer
        self._clock = clock

    def install(self, runtime) -> None:
        runtime.register("observe.snapshot", self._snapshot)
        runtime.register("candidates.list", self._candidates)
        runtime.register("target.select", self._target_select, resources=("device_writer",))
        runtime.register("target.clear", self._target_clear, resources=("device_writer",))
        runtime.register("track.start", self._track_start, resources=("device_writer",))
        runtime.register("track.status", self._status)
        runtime.register("framing.set", self._framing_set, resources=("device_writer",))
        runtime.register("look.nudge", self._look_nudge, resources=("device_writer", "look"))
        runtime.register("look.stop", self._look_stop, resources=("device_writer", "look"))
        runtime.register("look.status", self._status)
        runtime.register("capture.photo", self._capture_photo, resources=("media",))
        runtime.register("record.start", self._record_start, resources=("media",))
        runtime.register("record.stop", self._record_stop, resources=("media",))
        runtime.register("position.list", self._position_list)
        runtime.register("position.recall", self._position_recall, resources=("device_writer",))
        runtime.register("status.get", self._status)

    def _remaining(self, token, deadline) -> float | None:
        if token is not None:
            token.raise_if_cancelled()
        if deadline is None:
            return None
        deadline.raise_if_expired()
        return max(MIN_TIMEOUT, min(MAX_TIMEOUT, deadline.remaining()))

    def _call(self, op: str, args: dict | None, token, deadline) -> dict:
        timeout = self._remaining(token, deadline)
        return self.observer.handle({"op": op, "args": args or {}}, timeout=timeout)

    def _observation(self, request: CapabilityRequest, *, required: bool) -> str | None:
        arg_obs = request.args.get("observation_id")
        if arg_obs is not None and request.observation_id and arg_obs != request.observation_id:
            raise CapabilityRejected("observation_id in args conflicts with request.observation_id")
        observation_id = request.observation_id or arg_obs
        if required and not observation_id:
            raise CapabilityRejected("observation_id required for this capability")
        return observation_id

    def _snapshot(self, request, token, deadline) -> dict:
        response = self._call("snapshot", {"write": request.args.get("write", True)}, token, deadline)
        self._raise_on_error(response)
        return {"execution": Execution.COMPLETED, "requested": {"write": request.args.get("write", True)},
                "payload": {"observation": response.get("result")}}

    def _candidates(self, request, token, deadline) -> dict:
        response = self._call("candidates", {}, token, deadline)
        self._raise_on_error(response)
        return {"execution": Execution.COMPLETED,
                "payload": {"observation_id": request.observation_id,
                            "candidates": response.get("result", {}).get("candidates", [])}}

    def _target_select(self, request, token, deadline) -> dict:
        observation_id = self._observation(request, required=True)
        args = {k: v for k, v in request.args.items() if k != "observation_id"}
        args["observation_id"] = observation_id
        response = self._call("target.select", args, token, deadline)
        if not response.get("ok") and response.get("code") == "REOBSERVE_REQUIRED":
            raise ReobserveRequired(response.get("error", "reobserve required"),
                                    continuation_id=request.task_id, requested=args)
        if not response.get("ok") and "not in Track" in str(response.get("error", "")):
            raise ReobserveRequired("device not in Track runtime; reobserve after entering Track",
                                    continuation_id=request.task_id, requested=args)
        self._raise_on_error(response)
        result = response.get("result", {})
        return {"execution": Execution.COMPLETED, "requested": args,
                "sdk_reported": {"side_effects": result.get("side_effects"),
                                 "calibration": result.get("calibration")},
                "payload": {"target": result, "observation_id": observation_id}}

    def _target_clear(self, request, token, deadline) -> dict:
        response = self._call("target.clear", {}, token, deadline)
        self._raise_on_error(response)
        return {"execution": Execution.COMPLETED, "requested": {"cleared": True},
                "sdk_reported": response.get("result", {})}

    def _track_start(self, request, token, deadline) -> dict:
        selection = request.args.get("selection", "center")
        if selection not in ("center", "largest"):
            raise Constrained("track.start selection must be center or largest")
        response = self._call("track.enter", {"selection": selection}, token, deadline)
        self._raise_on_error(response)
        entered = response.get("result", {})
        if entered.get("entered") and entered.get("reobserve_required"):
            raise ReobserveRequired("entered Track runtime; camera may have moved; reobserve",
                                    continuation_id=request.task_id, requested={"selection": selection})
        return {"execution": Execution.COMPLETED, "requested": {"selection": selection},
                "sdk_reported": entered}

    def _framing_set(self, request, token, deadline) -> dict:
        mode = request.args.get("mode")
        if mode not in FRAMING_MODES:
            raise UnsupportedCapability(f"framing mode {mode!r} not supported (centered scale only)")
        response = self._call("framing.set", {"mode": mode}, token, deadline)
        self._raise_on_error(response)
        return {"execution": Execution.COMPLETED, "requested": {"mode": mode},
                "sdk_reported": {"applied": True, "source": "sdkhint"}, "visual_check": None}

    def _look_nudge(self, request, token, deadline) -> dict:
        response = self._call("look.nudge", request.args, token, deadline)
        self._raise_on_error(response)
        return {"execution": Execution.COMPLETED, "requested": request.args,
                "sdk_reported": response.get("result", {})}

    def _look_stop(self, request, token, deadline) -> dict:
        response = self._call("look.stop", {}, token, deadline)
        self._raise_on_error(response)
        return {"execution": Execution.COMPLETED, "requested": {"stopped": True},
                "sdk_reported": response.get("result", {})}

    def _capture_photo(self, request, token, deadline) -> dict:
        response = self._call("capture.photo", {"timeout": request.args.get("timeout", 2.0)}, token, deadline)
        self._raise_on_error(response)
        return {"execution": Execution.COMPLETED, "requested": {"provider": "host_uvc"},
                "artifact": response.get("result")}

    def _record_start(self, request, token, deadline) -> dict:
        response = self._call("record.start", {"fps": request.args.get("fps", 30.0)}, token, deadline)
        self._raise_on_error(response)
        return {"execution": Execution.COMPLETED, "requested": {"provider": "host_uvc"},
                "artifact": response.get("result")}

    def _record_stop(self, request, token, deadline) -> dict:
        response = self._call("record.stop", {}, token, deadline)
        self._raise_on_error(response)
        artifact = response.get("result") or {}
        execution = Execution.COMPLETED if artifact.get("finalized") else Execution.INDETERMINATE
        return {"execution": execution, "requested": {"stopped": True}, "artifact": artifact}

    def _position_list(self, request, token, deadline) -> dict:
        response = self._call("position.list", {}, token, deadline)
        self._raise_on_error(response)
        return {"execution": Execution.COMPLETED, "requested": {}, "sdk_reported": response.get("result", {})}

    def _position_recall(self, request, token, deadline) -> dict:
        if "id" not in request.args:
            raise Constrained("position.recall needs an explicit preset id")
        response = self._call("position.recall", {"id": request.args["id"]}, token, deadline)
        self._raise_on_error(response)
        return {"execution": Execution.COMPLETED, "requested": {"id": request.args["id"]},
                "sdk_reported": response.get("result", {})}

    def _status(self, request, token, deadline) -> dict:
        response = self._call("status", {}, token, deadline)
        self._raise_on_error(response)
        return {"execution": Execution.COMPLETED, "requested": {}, "sdk_reported": response.get("result", {})}

    @staticmethod
    def _raise_on_error(response: dict) -> None:
        if response.get("ok"):
            return
        error = str(response.get("error", "capability failed"))
        if response.get("code") == "REOBSERVE_REQUIRED":
            raise ReobserveRequired(error, continuation_id="unknown")
        raise CapabilityRejected(error)
