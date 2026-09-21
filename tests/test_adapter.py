import tempfile
import unittest
from pathlib import Path

from tail2_mvp.adapter import Tail2Adapter
from tail2_mvp.events import Trace
from tail2_mvp.harness import RuntimeHarness
from tail2_mvp.runtime import (
    CancelToken, CapabilityRejected, CapabilityRequest, CapabilityRuntime, Execution,
    ReobserveRequired,
)


class FakeObserver:
    def __init__(self, responses, *, stale=False):
        self.responses = responses
        self.calls = []
        self._stale = stale

    def check_observation(self, observation_id):
        if self._stale:
            raise ReobserveRequired("observation stale", "cont-1")
        return {"observation_id": observation_id}

    def handle(self, request, *, timeout=None):
        self.calls.append({"request": request, "timeout": timeout})
        op = request.get("op")
        if op not in self.responses:
            raise CapabilityRejected(f"no fake for {op}")
        value = self.responses[op]
        return value() if callable(value) else value


def build(responses, *, stale=False):
    runtime = CapabilityRuntime()
    observer = FakeObserver(responses, stale=stale)
    Tail2Adapter(observer, sleep=lambda _s: None).install(runtime)
    return runtime, observer


def status(mode, requested=True):
    return {"device.status": {"ai_main_mode_raw": mode, "ai_sub_mode_raw": 0},
            "status": {"track": {"requested": requested}}}


TRACK_ENTER = {"entered": True, "ai_main_mode": 2, "reobserve_required": True}


class TargetTrackTests(unittest.TestCase):
    def test_target_select_normal_prepares_track_and_reobserves(self):
        runtime, observer = build({**status(0), "track.enter": TRACK_ENTER})
        result = runtime.execute(CapabilityRequest("target.select", task_id="t1", observation_id="oA",
                                                   args={"candidate_id": "cA"}))
        self.assertEqual(result.execution, Execution.REOBSERVE_REQUIRED)
        self.assertEqual(result.continuation_id, "t1")
        self.assertEqual(result.payload["reason"], "track_runtime_entered")
        self.assertEqual(result.payload["previous_observation_id"], "oA")
        self.assertEqual(result.payload["required_next"], "reobserve_and_reground")
        self.assertEqual([c["request"]["op"] for c in observer.calls],
                         ["device.status", "status", "track.enter"])

    def test_target_select_in_track_boxes(self):
        runtime, observer = build({**status(2), "target.select": {
            "dispatch": "accepted", "side_effects": "UNVERIFIED", "calibration": {"verified": True},
            "requested_roi_sdk": [0.1, 0.2, 0.3, 0.4]}})
        result = runtime.execute(CapabilityRequest("target.select", observation_id="oA",
                                                   args={"candidate_id": "cA"}))
        self.assertEqual(result.execution, Execution.COMPLETED)
        self.assertEqual(result.payload["observation_id"], "oA")
        self.assertEqual(result.payload["follow_health"], "unknown")
        self.assertEqual(observer.calls[-1]["request"]["args"]["observation_id"], "oA")
        self.assertEqual(result.sdk_reported["side_effects"], "UNVERIFIED")

    def test_stale_reference_touches_no_device(self):
        runtime, observer = build(status(0), stale=True)
        result = runtime.execute(CapabilityRequest("target.select", observation_id="oX",
                                                   args={"candidate_id": "cX"}))
        self.assertEqual(result.execution, Execution.REOBSERVE_REQUIRED)
        self.assertEqual(observer.calls, [])

    def test_target_select_requires_first_class_observation(self):
        runtime, observer = build({})
        result = runtime.execute(CapabilityRequest("target.select", args={"candidate_id": "c1"}))
        self.assertEqual(result.execution, Execution.FAILED)
        self.assertEqual(result.errors[0].code, "rejected")
        self.assertEqual(observer.calls, [])

    def test_target_select_conflicting_observation_rejected(self):
        runtime, observer = build({})
        result = runtime.execute(CapabilityRequest("target.select", observation_id="o1",
                                                   args={"observation_id": "o2", "candidate_id": "c1"}))
        self.assertEqual(result.execution, Execution.FAILED)
        self.assertEqual(observer.calls, [])

    def test_track_start_returns_continuation(self):
        runtime, _ = build({"track.enter": TRACK_ENTER})
        result = runtime.execute(CapabilityRequest("track.start", task_id="t2",
                                                   args={"selection": "center", "class": "common"}))
        self.assertEqual(result.execution, Execution.REOBSERVE_REQUIRED)
        self.assertEqual(result.payload["reason"], "track_runtime_entered")

    def test_track_status_mode_two_is_not_following(self):
        runtime, _ = build(status(2))
        track = runtime.execute(CapabilityRequest("track.status")).payload["track"]
        self.assertEqual(track["runtime_mode"], "track")
        self.assertEqual(track["ai_requested"], "enabled")
        self.assertEqual(track["follow_health"], "unknown")

    def test_track_status_unknown_mode(self):
        runtime, _ = build({"device.status": {}, "status": {"track": {"requested": None}}})
        track = runtime.execute(CapabilityRequest("track.status")).payload["track"]
        self.assertEqual(track["runtime_mode"], "unknown")
        self.assertEqual(track["ai_requested"], "unknown")
        self.assertTrue(track["stale"])

    def test_motion_evidence_does_not_claim_following(self):
        seq = iter([-1.0, -1.4, -0.6, -0.2])

        def look():
            return {"result": {"yaw_deg": next(seq)}}

        runtime, _ = build({**status(2), "look.status": look})
        result = runtime.execute(CapabilityRequest("track.motion_evidence", args={"samples": 4, "min_yaw_deg": 0.5}))
        self.assertEqual(result.execution, Execution.COMPLETED)
        self.assertIsNone(result.visual_check)
        self.assertEqual(result.payload["motion_evidence"]["verdict"], "gimbal_response_observed")
        self.assertEqual(result.payload["track"]["follow_health"], "unknown")

    def test_motion_evidence_requires_track(self):
        runtime, _ = build(status(0))
        result = runtime.execute(CapabilityRequest("track.motion_evidence"))
        self.assertEqual(result.execution, Execution.FAILED)

    def test_task_cancel_cancels_all_requests_in_task(self):
        runtime, _ = build({})
        tokens = []
        with runtime._lock:
            for _ in range(3):
                token = CancelToken()
                tokens.append(token)
                runtime._by_task.setdefault("taskX", []).append(token)
        result = runtime.execute(CapabilityRequest("task.cancel", args={"task_id": "taskX"}))
        self.assertEqual(result.payload["cancelled_count"], 3)
        self.assertTrue(all(t.cancelled for t in tokens))


class FakeService:
    def __init__(self):
        self.camera_epoch = 0
        self.stream_session = "s1"
        self.max_frame_age_s = 2.0

    def status(self):
        return {"frames": 1, "width": 640, "height": 480, "last_frame_age_s": 0.0,
                "source": {"kind": "fake"}, "candidates": []}

    def candidates(self):
        return []

    def snapshot(self, *, write=True):
        return {"observation_id": "o1", "stream_session": "s1", "camera_epoch": 0, "frame_seq": 1,
                "width": 640, "height": 480, "received_mono": 0.0, "candidates": [],
                "provider": None, "fresh": True, "age_s": 0.0}


class FakeClosableBridge:
    def __init__(self):
        self.closed = False

    def request(self, op, args=None, timeout=20):
        return {"ok": True, "result": {}}

    def close(self):
        self.closed = True


class HarnessTests(unittest.TestCase):
    def make(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        trace = Trace(Path(temp.name) / "trace")
        self.addCleanup(trace.close)
        return RuntimeHarness(FakeService(), lambda: FakeClosableBridge(), trace,
                              calibration_dir=Path(temp.name) / "cal")

    def test_assembly_serves_status_and_track(self):
        harness = self.make()
        self.assertEqual(harness.call("status.get").execution, Execution.COMPLETED)
        track = harness.call("track.status").payload["track"]
        self.assertEqual(track["runtime_mode"], "unknown")
        self.assertIn("observe.snapshot", harness.runtime.capabilities())

    def test_session_rebuild_invalidates_and_reobserves(self):
        harness = self.make()
        snapshot = harness.call("observe.snapshot").payload["observation"]
        observation_id = snapshot["observation_id"]
        harness.session.rebuild()
        self.assertEqual(harness.session.camera_epoch, 1)
        result = harness.call("target.select", args={"candidate_id": "c1"}, observation_id=observation_id)
        self.assertEqual(result.execution, Execution.REOBSERVE_REQUIRED)
