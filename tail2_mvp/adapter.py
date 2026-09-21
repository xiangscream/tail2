"""Thin Tail2 adapter: map product capabilities onto the supervised Observer.

The adapter is the only place that knows device quirks (Track entry, AI toggle,
REOBSERVE). It translates observer output into CapabilityResult evidence and
raises runtime-level signals (ReobserveRequired, Constrained, UnsupportedCapability)
so callers never see SDK details.

Contract rules enforced here:
- The first-class ``request.observation_id`` is authoritative. If ``args`` also
  carries an observation_id and it differs, the request is rejected. The adapter
  injects the first-class value into the device call.
- Target/Track is a two-step device model: enter Track runtime first, then Box the
  concrete target. Entering Track moves the camera, so the adapter returns
  REOBSERVE_REQUIRED with a continuation payload instead of boxing the old frame.
- An observation is validated (frame/e freshness/epoch/calibration) before any
  device write, so a stale reference produces zero device writes.
- Deadlines are cooperative: the remaining time is passed to the observer / bridge
  so a slow synchronous SDK call times out at the bridge and quarantines the
  session; it is not a hard interrupt guarantee.
"""
from __future__ import annotations

import time
from typing import Callable

from .runtime import (
    CapabilityRejected, CapabilityRequest, Cancelled, Constrained, DeadlineExceeded, Execution,
    ReobserveRequired, UnsupportedCapability,
)

FRAMING_MODES = {"normal", "full_body", "half_body", "close_up"}
SELECTIONS = {"center", "largest"}
TARGET_CLASSES = {"human", "animal", "common"}
MIN_TIMEOUT = 0.05
MAX_TIMEOUT = 60.0
TRACK_ENTER_CONTINUATION = "reobserve_and_reground"


class Tail2Adapter:
    def __init__(self, observer, *, clock: Callable[[], float] | None = None,
                 sleep: Callable[[float], None] = time.sleep, follow_poll_s: float = 0.3):
        self.observer = observer
        self._clock = clock or time.monotonic
        self._sleep = sleep
        self._follow_poll_s = follow_poll_s
        self.follow_health = "unknown"

    def install(self, runtime) -> None:
        runtime.register("observe.snapshot", self._snapshot)
        runtime.register("candidates.list", self._candidates)
        runtime.register("target.select", self._target_select, resources=("device_writer",))
        runtime.register("target.clear", self._target_clear, resources=("device_writer",))
        runtime.register("track.start", self._track_start, resources=("device_writer",))
        runtime.register("track.status", self._track_status)
        runtime.register("track.verify_follow", self._track_verify_follow, resources=("look",))
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

    def _call(self, op: str, args: dict | None, token, deadline):
        timeout = self._remaining(token, deadline)
        try:
            return self.observer.handle({"op": op, "args": args or {}}, timeout=timeout)
        except (ReobserveRequired, CapabilityRejected, Cancelled, DeadlineExceeded):
            raise
        except UnsupportedCapability:
            raise
        except ValueError as exc:
            raise CapabilityRejected(str(exc))
        except RuntimeError as exc:
            message = str(exc)
            if "Track" in message:
                raise ReobserveRequired(message, continuation_id="unknown",
                                        payload={"reason": "not_in_track",
                                                 "required_next": TRACK_ENTER_CONTINUATION})
            raise CapabilityRejected(message)

    def _observation(self, request: CapabilityRequest, *, required: bool) -> str | None:
        arg_obs = request.args.get("observation_id")
        if arg_obs is not None and request.observation_id and arg_obs != request.observation_id:
            raise CapabilityRejected("observation_id in args conflicts with request.observation_id")
        observation_id = request.observation_id or arg_obs
        if required and not observation_id:
            raise CapabilityRejected("observation_id required for this capability")
        return observation_id

    def _device_track(self, token, deadline) -> dict:
        status = self._call("status", {}, token, deadline) or {}
        ai = status.get("ai", {}) or {}
        mode = ai.get("ai_main_mode_raw")
        runtime_mode = "track" if mode == 2 else "normal" if mode == 0 else "unknown"
        requested = (status.get("track", {}) or {}).get("requested")
        ai_requested = "enabled" if requested is True else "disabled" if requested is False else "unknown"
        return {"runtime_mode": runtime_mode, "ai_requested": ai_requested,
                "follow_health": self.follow_health, "ai_main_mode_raw": mode,
                "source": "sdk" if mode is not None else "unknown", "stale": mode is None}

    def _snapshot(self, request, token, deadline) -> dict:
        observation = self._call("snapshot", {"write": request.args.get("write", True)}, token, deadline)
        return {"execution": Execution.COMPLETED, "requested": {"write": request.args.get("write", True)},
                "payload": {"observation": observation}}

    def _candidates(self, request, token, deadline) -> dict:
        result = self._call("candidates", {}, token, deadline) or {}
        return {"execution": Execution.COMPLETED,
                "payload": {"observation_id": request.observation_id,
                            "candidates": result.get("candidates", [])}}

    def _target_select(self, request, token, deadline) -> dict:
        observation_id = self._observation(request, required=True)
        args = {k: v for k, v in request.args.items() if k != "observation_id"}
        args["observation_id"] = observation_id
        target_class = args.get("class", "human")
        if target_class not in TARGET_CLASSES:
            raise CapabilityRejected("unsupported target class")
        self.observer.check_observation(observation_id)
        state = self._device_track(token, deadline)
        if state["runtime_mode"] != "track":
            self._call("track.enter", {"selection": "center", "class": target_class}, token, deadline)
            self.follow_health = "unknown"
            raise ReobserveRequired(
                "entered Track runtime; camera may have moved; reobserve before boxing",
                continuation_id=request.task_id, requested=args,
                payload={"reason": "track_runtime_entered", "target_ref": args.get("candidate_id"),
                         "previous_observation_id": observation_id, "required_next": TRACK_ENTER_CONTINUATION})
        result = self._call("target.select", args, token, deadline) or {}
        return {"execution": Execution.COMPLETED, "requested": args,
                "sdk_reported": {"side_effects": result.get("side_effects"),
                                 "calibration": result.get("calibration")},
                "payload": {"target": result, "observation_id": observation_id,
                            "follow_health": self.follow_health}}

    def _target_clear(self, request, token, deadline) -> dict:
        result = self._call("target.clear", {}, token, deadline) or {}
        self.follow_health = "unknown"
        return {"execution": Execution.COMPLETED, "requested": {"cleared": True}, "sdk_reported": result}

    def _track_start(self, request, token, deadline) -> dict:
        selection = request.args.get("selection", "center")
        target_class = request.args.get("class", "human")
        if selection not in SELECTIONS:
            raise Constrained("track.start selection must be center or largest")
        if target_class not in TARGET_CLASSES:
            raise CapabilityRejected("unsupported target class")
        entered = self._call("track.enter", {"selection": selection, "class": target_class}, token, deadline) or {}
        self.follow_health = "unknown"
        if entered.get("entered") and entered.get("reobserve_required"):
            raise ReobserveRequired(
                "entered Track runtime; camera may have moved; reobserve",
                continuation_id=request.task_id, requested={"selection": selection, "class": target_class},
                payload={"reason": "track_runtime_entered", "target_ref": None,
                         "previous_observation_id": request.observation_id,
                         "required_next": TRACK_ENTER_CONTINUATION})
        return {"execution": Execution.COMPLETED, "requested": {"selection": selection},
                "sdk_reported": entered, "payload": {"track": self._device_track(token, deadline)}}

    def _track_status(self, request, token, deadline) -> dict:
        return {"execution": Execution.COMPLETED, "requested": {},
                "payload": {"track": self._device_track(token, deadline)}}

    def _track_verify_follow(self, request, token, deadline) -> dict:
        state = self._device_track(token, deadline)
        if state["runtime_mode"] != "track":
            raise CapabilityRejected("follow verification requires Track runtime")
        samples = int(request.args.get("samples", 5))
        min_yaw_deg = float(request.args.get("min_yaw_deg", 0.5))
        yaws = []
        lost = 0
        for _ in range(max(1, samples)):
            self._remaining(token, deadline)
            response = self._call("look.status", {}, token, deadline)
            inner = response.get("result", {}) if isinstance(response, dict) else {}
            if isinstance(inner, dict) and inner.get("yaw_deg") is not None:
                yaws.append(float(inner["yaw_deg"]))
            else:
                lost += 1
            self._sleep(self._follow_poll_s)
        span = (max(yaws) - min(yaws)) if len(yaws) >= 2 else 0.0
        if len(yaws) >= 2 and span >= min_yaw_deg and lost == 0:
            self.follow_health = "observed_following"
            verdict = "observed_following"
        elif lost > len(yaws):
            self.follow_health = "degraded"
            verdict = "degraded"
        else:
            verdict = "unknown"
        return {"execution": Execution.COMPLETED, "requested": {"min_yaw_deg": min_yaw_deg},
                "visual_check": {"verdict": verdict, "yaw_span_deg": span, "samples": len(yaws), "lost": lost},
                "payload": {"track": self._device_track(token, deadline)}}

    def _framing_set(self, request, token, deadline) -> dict:
        mode = request.args.get("mode")
        if mode not in FRAMING_MODES:
            raise UnsupportedCapability(f"framing mode {mode!r} not supported (centered scale only)")
        self._call("framing.set", {"mode": mode}, token, deadline)
        return {"execution": Execution.COMPLETED, "requested": {"mode": mode},
                "sdk_reported": {"applied": True, "source": "sdkhint"}, "visual_check": None}

    def _look_nudge(self, request, token, deadline) -> dict:
        result = self._call("look.nudge", request.args, token, deadline)
        return {"execution": Execution.COMPLETED, "requested": request.args, "sdk_reported": result or {}}

    def _look_stop(self, request, token, deadline) -> dict:
        result = self._call("look.stop", {}, token, deadline)
        return {"execution": Execution.COMPLETED, "requested": {"stopped": True}, "sdk_reported": result or {}}

    def _capture_photo(self, request, token, deadline) -> dict:
        artifact = self._call("capture.photo", {"timeout": request.args.get("timeout", 2.0)}, token, deadline)
        return {"execution": Execution.COMPLETED, "requested": {"provider": "host_uvc"}, "artifact": artifact}

    def _record_start(self, request, token, deadline) -> dict:
        artifact = self._call("record.start", {"fps": request.args.get("fps", 30.0)}, token, deadline)
        return {"execution": Execution.COMPLETED, "requested": {"provider": "host_uvc"}, "artifact": artifact}

    def _record_stop(self, request, token, deadline) -> dict:
        artifact = self._call("record.stop", {}, token, deadline) or {}
        execution = Execution.COMPLETED if artifact.get("finalized") else Execution.INDETERMINATE
        return {"execution": execution, "requested": {"stopped": True}, "artifact": artifact}

    def _position_list(self, request, token, deadline) -> dict:
        return {"execution": Execution.COMPLETED, "requested": {},
                "sdk_reported": self._call("position.list", {}, token, deadline) or {}}

    def _position_recall(self, request, token, deadline) -> dict:
        if "id" not in request.args:
            raise Constrained("position.recall needs an explicit preset id")
        result = self._call("position.recall", {"id": request.args["id"]}, token, deadline)
        return {"execution": Execution.COMPLETED, "requested": {"id": request.args["id"]},
                "sdk_reported": result or {}}

    def _status(self, request, token, deadline) -> dict:
        status = self._call("status", {}, token, deadline) or {}
        return {"execution": Execution.COMPLETED, "requested": {}, "sdk_reported": status,
                "payload": {"track": self._device_track(token, deadline)}}
