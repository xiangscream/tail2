import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from tail2_mvp.events import Trace
from tail2_mvp.observation_service import ObservationService, UvcFrameSource, resolve_dshow_index


class FakeFrame:
    def __init__(self, seq, width=64, height=48):
        self.seq = seq
        self.shape = (height, width, 3)


class FakeSource:
    def __init__(self, frames=None):
        self.frames = frames
        self.count = 0
        self.opened = False
        self.open_calls = 0
        self._lock = threading.Lock()

    def open(self):
        self.opened = True
        self.open_calls += 1

    def read(self):
        with self._lock:
            if self.frames is not None and self.count >= self.frames:
                return False, None
            self.count += 1
            return True, FakeFrame(self.count)

    def release(self):
        self.opened = False

    def describe(self):
        return {"kind": "fake", "count": self.count}


def encoder(frame, max_width=None):
    return b"J" + bytes([frame.seq % 256])


class FakeWriter:
    def __init__(self, path, width, height, fps):
        self.path = Path(path)
        self.frames = 0
        self.released = False

    def write(self, frame):
        self.frames += 1

    def release(self):
        self.released = True
        self.path.write_bytes(b"video" + bytes([self.frames % 256]))


def wait_for(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class DropSource:
    def __init__(self, drop_after=5):
        self.drop_after = drop_after
        self.opened = 0
        self.alive = False
        self.count = 0

    def open(self):
        self.opened += 1
        self.alive = True
        self.count = 0

    def read(self):
        if not self.alive:
            return False, None
        self.count += 1
        if self.count > self.drop_after:
            self.alive = False
            return False, None
        return True, FakeFrame(self.count)

    def release(self):
        self.alive = False

    def describe(self):
        return {"kind": "drop", "opened": self.opened}


class SourceBindingTests(unittest.TestCase):
    def test_resolve_by_name(self):
        names = ["Integrated Camera", "OBSBOT Tail 2 Camera", "OBSBOT Virtual Camera"]
        self.assertEqual(resolve_dshow_index("OBSBOT Tail 2 Camera", lister=lambda: names), 1)
        with self.assertRaises(RuntimeError):
            resolve_dshow_index("Missing Camera", lister=lambda: names)
        with self.assertRaises(RuntimeError):
            resolve_dshow_index("Dup", lister=lambda: ["Dup", "Dup"])

    def test_source_requires_index_or_name(self):
        with self.assertRaises(ValueError):
            UvcFrameSource(backend="dshow")
        with self.assertRaises(ValueError):
            UvcFrameSource(index=1, backend="dshow", device_name="x")
        with self.assertRaises(ValueError):
            UvcFrameSource(index=-1, backend="dshow")

    def test_source_describe_includes_name(self):
        source = UvcFrameSource(backend="dshow", device_name="OBSBOT Tail 2 Camera")
        described = source.describe()
        self.assertEqual(described["device_name"], "OBSBOT Tail 2 Camera")
        self.assertIsNone(described["index"])


class ServiceTests(unittest.TestCase):
    def make(self, source=None, **kwargs):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        source = source or FakeSource()
        service = ObservationService(source, Path(temp.name), encoder=encoder,
                                     writer_factory=FakeWriter, **kwargs)
        service.start()
        self.addCleanup(service.stop)
        return service, source, Path(temp.name)

    def test_single_source_and_snapshot(self):
        service, source, out = self.make()
        first = service.snapshot()
        second = service.snapshot()
        self.assertEqual(source.open_calls, 1)
        self.assertNotEqual(first["observation_id"], second["observation_id"])
        self.assertTrue(Path(first["frame_file"]).exists())
        self.assertTrue(first["fresh"])
        self.assertEqual(first["width"], 64)
        self.assertEqual(first["height"], 48)

    def test_photo_is_strictly_after_request(self):
        service, _, _ = self.make()
        before = service.snapshot()["frame_seq"]
        artifact = service.capture_photo(timeout=2.0)
        self.assertGreater(artifact["frame_seq"], before)
        self.assertTrue(artifact["finalized"])
        self.assertTrue(artifact["accessible"])
        self.assertEqual(Path(artifact["path_ref"]).stat().st_size, artifact["size_bytes"])
        manifest = json.loads(Path(artifact["manifest_ref"]).read_text())
        self.assertEqual(manifest["captured_observation_id"], artifact["captured_observation_id"])

    def test_photo_timeout_without_new_frames(self):
        service, _, _ = self.make(source=FakeSource(frames=5))
        wait_for(lambda: service.status()["frames"] >= 5)
        with self.assertRaises(TimeoutError):
            service.capture_photo(timeout=0.2)

    def test_record_lifecycle(self):
        service, _, _ = self.make()
        started = service.record_start(fps=15)
        self.assertTrue(started["started"])
        wait_for(lambda: service.status()["recording"]["frames"] > 0)
        stopped = service.record_stop()
        self.assertTrue(stopped["finalized"])
        self.assertTrue(stopped["accessible"])
        self.assertGreater(stopped["frames"], 0)
        self.assertTrue(Path(stopped["path_ref"]).exists())

    def test_detector_candidates(self):
        detector = lambda frame, width, height: [{"candidate_id": "c1", "class": "human",
                                                  "bbox": [0.1, 0.1, 0.2, 0.2], "provider": "test"}]
        service, _, _ = self.make(detector=detector, detector_interval_s=0.01)
        self.assertTrue(wait_for(lambda: service.candidates()))
        self.assertEqual(service.candidates()[0]["candidate_id"], "c1")
        self.assertEqual(service.snapshot()["provider"], "host_detector")

    def test_status_shape(self):
        service, _, _ = self.make()
        status = service.status()
        self.assertIsNone(status["recording"])
        self.assertEqual(status["source"]["kind"], "fake")
        self.assertGreaterEqual(status["frames"], 1)

    def test_reconnects_after_camera_drop(self):
        source = DropSource(drop_after=5)
        service, _, _ = self.make(source=source)
        self.assertTrue(wait_for(lambda: service.status()["reconnects"] >= 1, timeout=6))
        self.assertGreaterEqual(service.status()["camera_epoch"], 1)
        self.assertGreaterEqual(source.opened, 2)


class ObserverTests(unittest.TestCase):
    def make(self, control=True, verified=True):
        from tail2_mvp.calibration import CalibrationStore
        from tail2_mvp.observer import Observer

        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        detector = lambda frame, width, height: [
            {"candidate_id": "p1", "class": "human", "bbox": [0.1, 0.2, 0.4, 0.9], "provider": "test"}]
        service = ObservationService(FakeSource(), Path(temp.name), encoder=encoder,
                                     writer_factory=FakeWriter, detector=detector)
        service.start()
        self.addCleanup(service.stop)
        trace = Trace(Path(temp.name) / "trace")
        self.addCleanup(trace.close)
        bridge = FakeBridge()
        store = CalibrationStore(Path(temp.name) / "cal")
        store.set_profile(calibration_id="cal", camera_epoch=service.camera_epoch)
        if verified:
            seed = {"left": (0.2, 0.5), "center": (0.5, 0.5), "right": (0.8, 0.5),
                    "top": (0.5, 0.2), "middle": (0.5, 0.5), "bottom": (0.5, 0.8)}
            for position, (x, y) in seed.items():
                store.add_geometry_sample(position, "seed", x, y)
            for position in seed:
                store.record_outcome(position, "seed", [0.1, 0.1, 0.2, 0.2],
                                     {"x1": 0.1, "y1": 0.1, "x2": 0.2, "y2": 0.2}, True, "seed")
            store.verify()
        observer = Observer(service, bridge, trace, control=control, legacy=True, calibration=store)
        return observer, bridge

    def test_target_select_requires_observation(self):
        from tail2_mvp.observations import ReobserveRequired

        observer, _ = self.make()
        with self.assertRaises(ReobserveRequired):
            observer.handle({"op": "target.select", "args": {"x1": 0.1, "y1": 0.1, "x2": 0.2, "y2": 0.2}})

    def test_target_select_maps_roi_from_observation(self):
        observer, bridge = self.make()
        snap = observer.handle({"op": "snapshot"})
        result = observer.handle({"op": "target.select", "args": {
            "observation_id": snap["observation_id"], "x1": 0.1, "y1": 0.2, "x2": 0.4, "y2": 0.9}})
        self.assertEqual(result["requested_roi_sdk"], [0.1, 0.2, 0.4, 0.9])
        self.assertIn("UNVERIFIED", result["side_effects"])
        self.assertEqual(bridge.calls[-1][0], "target.select")
        self.assertEqual(bridge.calls[-1][1]["x2"], 0.4)

    def test_candidate_ref_uses_observed_bbox(self):
        observer, _ = self.make()
        snap = observer.handle({"op": "snapshot"})
        result = observer.handle({"op": "target.select", "args": {
            "observation_id": snap["observation_id"], "candidate_id": "p1"}})
        self.assertEqual(result["requested_roi"], [0.1, 0.2, 0.4, 0.9])

    def test_unknown_candidate_rejected(self):
        from tail2_mvp.observations import ReobserveRequired

        observer, _ = self.make()
        snap = observer.handle({"op": "snapshot"})
        with self.assertRaises(ReobserveRequired):
            observer.handle({"op": "target.select", "args": {
                "observation_id": snap["observation_id"], "candidate_id": "nope"}})

    def test_epoch_change_invalidates_reference(self):
        from tail2_mvp.observations import ReobserveRequired

        observer, _ = self.make()
        snap = observer.handle({"op": "snapshot"})
        observer.service.camera_epoch += 1
        with self.assertRaises(ReobserveRequired):
            observer.handle({"op": "target.select", "args": {
                "observation_id": snap["observation_id"], "x1": 0.1, "y1": 0.1, "x2": 0.2, "y2": 0.2}})

    def test_target_select_requires_control(self):
        observer, _ = self.make(control=False)
        snap = observer.handle({"op": "snapshot"})
        with self.assertRaises(RuntimeError):
            observer.handle({"op": "target.select", "args": {
                "observation_id": snap["observation_id"], "x1": 0.1, "y1": 0.1, "x2": 0.2, "y2": 0.2}})

    def test_unverified_calibration_blocks_selection(self):
        observer, _ = self.make(verified=False)
        snap = observer.handle({"op": "snapshot"})
        with self.assertRaises(ValueError):
            observer.handle({"op": "target.select", "args": {
                "observation_id": snap["observation_id"], "x1": 0.1, "y1": 0.1, "x2": 0.2, "y2": 0.2}})

    def test_calibration_cannot_self_verify(self):
        observer, _ = self.make(verified=False)
        described = observer.handle({"op": "calibration.profile",
                                     "args": {"calibration_id": "x", "verified": True}})
        self.assertFalse(described["verified"])

    def test_calibration_verify_requires_sdk_outcomes(self):
        observer, _ = self.make(verified=False)
        with self.assertRaises(ValueError):
            observer.handle({"op": "calibration.verify"})
        snap = observer.handle({"op": "snapshot"})
        positions = {"left": (0.2, 0.5), "center": (0.5, 0.5), "right": (0.8, 0.5),
                     "top": (0.5, 0.2), "middle": (0.5, 0.5), "bottom": (0.5, 0.8)}
        for position, (x, y) in positions.items():
            observer.handle({"op": "calibration.sample", "args": {
                "position": position, "observation_id": snap["observation_id"], "x": x, "y": y}})
        with self.assertRaises(ValueError):
            observer.handle({"op": "calibration.verify"})
        for position in positions:
            observer.handle({"op": "calibration.outcome", "args": {
                "position": position, "observation_id": snap["observation_id"],
                "uvc_bbox": [0.1, 0.1, 0.2, 0.2],
                "sdk_roi": {"x1": 0.1, "y1": 0.1, "x2": 0.2, "y2": 0.2}, "selected": True}})
        self.assertTrue(observer.handle({"op": "calibration.verify"})["verified"])

    def test_ai_control_set_disabled_by_default(self):
        observer, _ = self.make()
        with self.assertRaises(RuntimeError):
            observer.handle({"op": "ai.control.set", "args": {"para": 2, "value": 1}})

    def test_gimbal_last_good_and_stale(self):
        observer, bridge = self.make()
        bridge.result = {"ok": True, "result": {"roll_deg": 0.3, "pitch_deg": 0.0, "yaw_deg": 3.6}, "sdk_calls": []}
        observer.handle({"op": "look.status", "args": {}})
        self.assertEqual(observer.status()["gimbal"]["value"]["yaw_deg"], 3.6)
        self.assertFalse(observer.status()["gimbal"]["stale"])
        bridge.result = {"ok": False, "error": "SDK operation rejected", "sdk_calls": []}
        observer.handle({"op": "look.status", "args": {}})
        gimbal = observer.status()["gimbal"]
        self.assertTrue(gimbal["stale"])
        self.assertEqual(gimbal["value"]["yaw_deg"], 3.6)

    def test_overlay_has_no_tracking_claim(self):
        observer, _ = self.make()
        overlay = observer.overlay()
        self.assertIn("not a native device tracking box", overlay["notes"][0])
        self.assertIsNone(overlay["requested_roi"])


class ObservationStoreTests(unittest.TestCase):
    def test_validate_and_membership(self):
        from tail2_mvp.observations import ObservationRecord, ObservedCandidate, ObservationStore, ReobserveRequired

        store = ObservationStore()
        record = ObservationRecord("o1", 5, 2, "s1", 100.0, 640, 480, "cal",
                                   "host_detector", (ObservedCandidate("c1", "human", (0.1, 0.1, 0.2, 0.2), "t"),))
        store.put(record)
        self.assertEqual(store.validate("o1", stream_session="s1", camera_epoch=2, now_mono=100.4,
                                        max_age_s=1, calibration_id="cal").observation_id, "o1")
        self.assertEqual(record.candidate("c1").candidate_id, "c1")
        with self.assertRaises(ReobserveRequired):
            store.validate("o1", stream_session="s2", camera_epoch=2, now_mono=100.4, max_age_s=1, calibration_id="cal")
        with self.assertRaises(ReobserveRequired):
            store.validate("o1", stream_session="s1", camera_epoch=3, now_mono=100.4, max_age_s=1, calibration_id="cal")
        with self.assertRaises(ReobserveRequired):
            store.validate("o1", stream_session="s1", camera_epoch=2, now_mono=200.0, max_age_s=1, calibration_id="cal")
        with self.assertRaises(ReobserveRequired):
            store.validate("o1", stream_session="s1", camera_epoch=2, now_mono=100.4, max_age_s=1, calibration_id="other")
        with self.assertRaises(ReobserveRequired):
            record.candidate("missing")

    def test_capacity_eviction(self):
        from tail2_mvp.observations import ObservationRecord, ObservationStore

        store = ObservationStore(capacity=1)
        store.put(ObservationRecord("a", 1, 0, "s", 0.0, 1, 1, "c", None))
        store.put(ObservationRecord("b", 2, 0, "s", 0.0, 1, 1, "c", None))
        self.assertIsNone(store.get("a"))
        self.assertIsNotNone(store.get("b"))


class FakeBridge:
    def __init__(self):
        self.calls = []
        self.result = {"ok": True, "result": {"dispatch": "accepted"}, "sdk_calls": []}

    def request(self, op, args=None, timeout=20):
        self.calls.append((op, args or {}))
        if op == "device.status":
            return {"ok": True, "result": {"ai_main_mode_raw": 2, "ai_sub_mode_raw": 0,
                                           "record_operation_raw": 2}, "sdk_calls": []}
        return self.result
