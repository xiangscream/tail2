import unittest

from tail2_mvp.adapter import Tail2Adapter
from tail2_mvp.runtime import CapabilityRequest, CapabilityRuntime, Execution


class FakeObserver:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def handle(self, request):
        self.calls.append(request)
        op = request.get("op")
        if op not in self.responses:
            return {"op": op, "ok": False, "error": f"no fake for {op}"}
        value = self.responses[op]
        if isinstance(value, dict) and "ok" in value:
            return value
        return {"op": op, "ok": True, "result": value}


def build(responses):
    runtime = CapabilityRuntime()
    observer = FakeObserver(responses)
    Tail2Adapter(observer).install(runtime)
    return runtime, observer


class AdapterTests(unittest.TestCase):
    def test_snapshot_payload(self):
        runtime, _ = build({"snapshot": {"observation_id": "o1", "frame_seq": 5}})
        result = runtime.execute(CapabilityRequest("observe.snapshot"))
        self.assertEqual(result.execution, Execution.COMPLETED)
        self.assertEqual(result.payload["observation"]["observation_id"], "o1")

    def test_target_select_normal_requires_reobserve(self):
        runtime, _ = build({"target.select": {"ok": False,
            "error": "device is not in Track runtime; call track.enter ... REOBSERVE ...",
            "code": "REOBSERVE_REQUIRED"}})
        result = runtime.execute(CapabilityRequest("target.select", task_id="t1",
                                                   args={"observation_id": "o1", "candidate_id": "c1"}))
        self.assertEqual(result.execution, Execution.REOBSERVE_REQUIRED)
        self.assertEqual(result.continuation_id, "t1")

    def test_target_select_in_track_reports_side_effects(self):
        runtime, _ = build({"target.select": {"ok": True, "result": {
            "dispatch": "accepted", "side_effects": "UNVERIFIED", "calibration": {"verified": True},
            "requested_roi_sdk": [0.1, 0.2, 0.3, 0.4]}}})
        result = runtime.execute(CapabilityRequest("target.select", args={"candidate_id": "c1"}))
        self.assertEqual(result.execution, Execution.COMPLETED)
        self.assertIn("side_effects", result.sdk_reported)
        self.assertEqual(result.payload["target"]["requested_roi_sdk"], [0.1, 0.2, 0.3, 0.4])

    def test_track_start_requires_reobserve(self):
        runtime, _ = build({"track.enter": {"ok": True, "result": {
            "selection": "center", "ai_main_mode": 2, "entered": True, "reobserve_required": True}}})
        result = runtime.execute(CapabilityRequest("track.start", task_id="t2", args={"selection": "center"}))
        self.assertEqual(result.execution, Execution.REOBSERVE_REQUIRED)
        self.assertEqual(result.continuation_id, "t2")

    def test_framing_invalid_mode_unsupported(self):
        runtime, _ = build({})
        result = runtime.execute(CapabilityRequest("framing.set", args={"mode": "left_third"}))
        self.assertEqual(result.execution, Execution.UNSUPPORTED)

    def test_framing_applied_is_not_visual_satisfaction(self):
        runtime, _ = build({"framing.set": {"ok": True, "result": {"dispatch": "accepted"}}})
        result = runtime.execute(CapabilityRequest("framing.set", args={"mode": "full_body"}))
        self.assertEqual(result.execution, Execution.COMPLETED)
        self.assertEqual(result.sdk_reported["applied"], True)
        self.assertIsNone(result.visual_check)

    def test_record_stop_unfinalized_indeterminate(self):
        runtime, _ = build({"record.stop": {"ok": True, "result": {"finalized": False, "path_ref": "x"}}})
        result = runtime.execute(CapabilityRequest("record.stop"))
        self.assertEqual(result.execution, Execution.INDETERMINATE)

    def test_position_recall_needs_id(self):
        runtime, _ = build({})
        result = runtime.execute(CapabilityRequest("position.recall", args={}))
        self.assertEqual(result.execution, Execution.CONSTRAINED)

    def test_observer_error_maps_to_failed(self):
        runtime, _ = build({"capture.photo": {"ok": False, "error": "camera busy"}})
        result = runtime.execute(CapabilityRequest("capture.photo"))
        self.assertEqual(result.execution, Execution.FAILED)
        self.assertEqual(result.errors[0].code, "rejected")

    def test_look_ownership_blocks_concurrent_writer(self):
        runtime, _ = build({"look.nudge": {"ok": True, "result": {"dispatch": "accepted"}}})
        runtime.ownership.acquire("look", "other-task")
        result = runtime.execute(CapabilityRequest("look.nudge", task_id="mine", args={"pan_dps": 1}))
        self.assertEqual(result.execution, Execution.FAILED)
        self.assertEqual(result.errors[0].code, "busy")
