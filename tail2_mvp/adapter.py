"""Thin Tail2 adapter: map product capabilities onto the supervised Observer.

The adapter is the only place that knows device quirks (Track entry, AI toggle,
REOBSERVE). It translates observer output into CapabilityResult evidence and
raises runtime-level signals (ReobserveRequired, Constrained, UnsupportedCapability)
so callers never see SDK details.
"""
from __future__ import annotations

from typing import Any, Callable

from .runtime import (
    CapabilityRejected, CapabilityRequest, Constrained, Execution, ReobserveRequired,
    UnsupportedCapability,
)

FRAMING_MODES = {"normal", "full_body", "half_body", "close_up"}


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
        runtime.register("task.cancel", lambda request, token, deadline: {"execution": Execution.COMPLETED})

    def _call(self, op: str, args: dict | None = None) -> dict:
        return self.observer.handle({"op": op, "args": args or {}})

    def _snapshot(self, request: CapabilityRequest, token, deadline) -> dict:
        response = self._call("snapshot", {"write": request.args.get("write", True)})
        self._raise_on_error(response)
        return {"execution": Execution.COMPLETED, "requested": {"write": request.args.get("write", True)},
                "payload": {"observation": response.get("result")}}

    def _candidates(self, request: CapabilityRequest, token, deadline) -> dict:
        response = self._call("candidates")
        self._raise_on_error(response)
        return {"execution": Execution.COMPLETED,
                "payload": {"observation_id": request.observation_id,
                            "candidates": response.get("result", {}).get("candidates", [])}}

    def _target_select(self, request: CapabilityRequest, token, deadline) -> dict:
        response = self._call("target.select", request.args)
        if not response.get("ok") and response.get("code") == "REOBSERVE_REQUIRED":
            raise ReobserveRequired(response.get("error", "reobserve required"),
                                    continuation_id=request.task_id, requested=request.args)
        if not response.get("ok") and "not in Track" in str(response.get("error", "")):
            raise ReobserveRequired("device not in Track runtime; reobserve after entering Track",
                                    continuation_id=request.task_id, requested=request.args)
        self._raise_on_error(response)
        result = response.get("result", {})
        return {"execution": Execution.COMPLETED, "requested": request.args,
                "sdk_reported": {"side_effects": result.get("side_effects"),
                                 "calibration": result.get("calibration")},
                "payload": {"target": result}}

    def _target_clear(self, request: CapabilityRequest, token, deadline) -> dict:
        response = self._call("target.clear")
        self._raise_on_error(response)
        return {"execution": Execution.COMPLETED, "requested": {"cleared": True},
                "sdk_reported": response.get("result", {})}

    def _track_start(self, request: CapabilityRequest, token, deadline) -> dict:
        selection = request.args.get("selection", "center")
        if selection not in ("center", "largest"):
            raise Constrained("track.start selection must be center or largest")
        response = self._call("track.enter", {"selection": selection})
        self._raise_on_error(response)
        entered = response.get("result", {})
        if entered.get("entered") and entered.get("reobserve_required"):
            raise ReobserveRequired("entered Track runtime; camera may have moved; reobserve",
                                    continuation_id=request.task_id, requested={"selection": selection})
        return {"execution": Execution.COMPLETED, "requested": {"selection": selection},
                "sdk_reported": entered}

    def _framing_set(self, request: CapabilityRequest, token, deadline) -> dict:
        mode = request.args.get("mode")
        if mode not in FRAMING_MODES:
            raise UnsupportedCapability(f"framing mode {mode!r} not supported (centered scale only)")
        response = self._call("framing.set", {"mode": mode})
        self._raise_on_error(response)
        return {"execution": Execution.COMPLETED, "requested": {"mode": mode},
                "sdk_reported": {"applied": True, "source": "sdkhint"},
                "visual_check": None}

    def _look_nudge(self, request: CapabilityRequest, token, deadline) -> dict:
        response = self._call("look.nudge", request.args)
        self._raise_on_error(response)
        return {"execution": Execution.COMPLETED, "requested": request.args,
                "sdk_reported": response.get("result", {})}

    def _look_stop(self, request: CapabilityRequest, token, deadline) -> dict:
        response = self._call("look.stop")
        self._raise_on_error(response)
        return {"execution": Execution.COMPLETED, "requested": {"stopped": True},
                "sdk_reported": response.get("result", {})}

    def _capture_photo(self, request: CapabilityRequest, token, deadline) -> dict:
        response = self._call("capture.photo", {"timeout": request.args.get("timeout", 2.0)})
        self._raise_on_error(response)
        return {"execution": Execution.COMPLETED, "requested": {"provider": "host_uvc"},
                "artifact": response.get("result")}

    def _record_start(self, request: CapabilityRequest, token, deadline) -> dict:
        response = self._call("record.start", {"fps": request.args.get("fps", 30.0)})
        self._raise_on_error(response)
        return {"execution": Execution.COMPLETED, "requested": {"provider": "host_uvc"},
                "artifact": response.get("result")}

    def _record_stop(self, request: CapabilityRequest, token, deadline) -> dict:
        response = self._call("record.stop")
        self._raise_on_error(response)
        artifact = response.get("result") or {}
        execution = Execution.COMPLETED if artifact.get("finalized") else Execution.INDETERMINATE
        return {"execution": execution, "requested": {"stopped": True}, "artifact": artifact}

    def _position_list(self, request: CapabilityRequest, token, deadline) -> dict:
        response = self._call("position.list")
        self._raise_on_error(response)
        return {"execution": Execution.COMPLETED, "requested": {}, "sdk_reported": response.get("result", {})}

    def _position_recall(self, request: CapabilityRequest, token, deadline) -> dict:
        if "id" not in request.args:
            raise Constrained("position.recall needs an explicit preset id")
        response = self._call("position.recall", {"id": request.args["id"]})
        self._raise_on_error(response)
        return {"execution": Execution.COMPLETED, "requested": {"id": request.args["id"]},
                "sdk_reported": response.get("result", {})}

    def _status(self, request: CapabilityRequest, token, deadline) -> dict:
        response = self._call("status")
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
