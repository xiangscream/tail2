import threading
import time
import unittest

from tail2_mvp.bridge import BridgeError
from tail2_mvp.runtime import (
    CancelToken, Cancelled, CapabilityError, CapabilityRequest, CapabilityRuntime, Constrained,
    Deadline, DeadlineExceeded, Execution, ReobserveRequired, ResourceBusy, ResourceOwnership,
    StateRegistry, UnsupportedCapability,
)
from tail2_mvp.session import RuntimeSession


class ContractTests(unittest.TestCase):
    def test_request_defaults_and_validation(self):
        request = CapabilityRequest("observe.snapshot")
        self.assertTrue(request.request_id)
        self.assertEqual(request.task_id, request.request_id)
        with self.assertRaises(ValueError):
            CapabilityRequest("")
        with self.assertRaises(ValueError):
            CapabilityRequest("look.nudge", deadline_s=0)
        with self.assertRaises(ValueError):
            CapabilityRequest("look.nudge", deadline_s=99999)

    def test_state_registry_last_good_and_stale(self):
        clock = {"t": 100.0}
        registry = StateRegistry(clock=lambda: clock["t"])
        registry.set("look", {"yaw": 3.6}, source="gimbal")
        fresh = registry.read("look", stale_after_s=2)
        self.assertFalse(fresh["stale"])
        self.assertEqual(fresh["value"], {"yaw": 3.6})
        clock["t"] = 110.0
        self.assertTrue(registry.read("look", stale_after_s=2)["stale"])
        registry.fail("look", "rc=-1")
        failed = registry.read("look", stale_after_s=1000)
        self.assertTrue(failed["stale"])
        self.assertEqual(failed["error"], "rc=-1")
        self.assertEqual(failed["value"], {"yaw": 3.6})
        registry.mark_unsupported("offset", "no getter")
        unsupported = registry.read("offset", stale_after_s=1000)
        self.assertTrue(unsupported["unsupported"])
        self.assertTrue(unsupported["stale"])
        self.assertEqual(registry.read("missing", stale_after_s=1)["value"], None)

    def test_ownership_busy_and_clear(self):
        ownership = ResourceOwnership()
        ownership.acquire("device_writer", "task1")
        with self.assertRaises(ResourceBusy):
            ownership.acquire("device_writer", "task2")
        ownership.acquire("device_writer", "task1")
        ownership.release("device_writer", "task2")
        self.assertEqual(ownership.owner("device_writer"), "task1")
        ownership.release("device_writer", "task1")
        self.assertIsNone(ownership.owner("device_writer"))
        ownership.acquire("look", "task1")
        ownership.clear()
        self.assertEqual(ownership.held(), {})

    def test_cancel_and_deadline(self):
        token = CancelToken()
        token.raise_if_cancelled()
        token.cancel()
        self.assertTrue(token.cancelled)
        with self.assertRaises(Cancelled):
            token.raise_if_cancelled()
        clock = {"t": 0.0}
        deadline = Deadline(5, clock=lambda: clock["t"])
        deadline.raise_if_expired()
        clock["t"] = 6.0
        with self.assertRaises(DeadlineExceeded):
            deadline.raise_if_expired()


class CapabilityRuntimeTests(unittest.TestCase):
    def make(self):
        runtime = CapabilityRuntime(clock=time.monotonic)
        return runtime

    def test_unsupported_capability(self):
        runtime = self.make()
        result = runtime.execute(CapabilityRequest("nope"))
        self.assertEqual(result.execution, Execution.UNSUPPORTED)
        self.assertEqual(result.errors[0].code, "unsupported")

    def test_completed_evidence_separation(self):
        runtime = self.make()

        def handler(request, token, deadline):
            return {"execution": Execution.COMPLETED, "requested": {"mode": "full_body"},
                    "sdk_reported": {"mode": "full_body", "source": "typed", "stale": False},
                    "visual_check": {"observation_id": "obs2", "verdict": "satisfied"},
                    "artifact": {"media_id": "m1", "finalized": True}}

        runtime.register("framing.set", handler)
        result = runtime.execute(CapabilityRequest("framing.set", args={"mode": "full_body"}, observation_id="obs2"))
        self.assertEqual(result.execution, Execution.COMPLETED)
        self.assertEqual(result.requested["mode"], "full_body")
        self.assertEqual(result.sdk_reported["mode"], "full_body")
        self.assertEqual(result.visual_check["verdict"], "satisfied")
        self.assertEqual(result.artifact["media_id"], "m1")

    def test_reobserve_is_a_continuation_not_failure(self):
        runtime = self.make()

        def handler(request, token, deadline):
            raise ReobserveRequired("entered Track; camera moved", continuation_id="cont-1",
                                    requested={"candidate_id": "c1"})

        runtime.register("target.select", handler)
        result = runtime.execute(CapabilityRequest("target.select"))
        self.assertEqual(result.execution, Execution.REOBSERVE_REQUIRED)
        self.assertEqual(result.continuation_id, "cont-1")
        self.assertEqual(result.requested["candidate_id"], "c1")

    def test_deadline_side_effecting_is_indeterminate(self):
        runtime = self.make()
        runtime.register("look.nudge", lambda r, t, d: (_ for _ in ()).throw(DeadlineExceeded()))
        result = runtime.execute(CapabilityRequest("look.nudge", deadline_s=1))
        self.assertEqual(result.execution, Execution.INDETERMINATE)

    def test_deadline_read_only_is_failed(self):
        runtime = self.make()
        runtime.register("status.get", lambda r, t, d: (_ for _ in ()).throw(DeadlineExceeded()))
        result = runtime.execute(CapabilityRequest("status.get", deadline_s=1))
        self.assertEqual(result.execution, Execution.FAILED)

    def test_handler_exception_is_indeterminate_for_writes(self):
        runtime = self.make()
        runtime.register("record.start", lambda r, t, d: (_ for _ in ()).throw(RuntimeError("boom")))
        result = runtime.execute(CapabilityRequest("record.start"))
        self.assertEqual(result.execution, Execution.INDETERMINATE)
        self.assertEqual(result.errors[0].code, "failed")

    def test_constrained_and_unsupported_exceptions(self):
        runtime = self.make()
        runtime.register("framing.set", lambda r, t, d: (_ for _ in ()).throw(Constrained("too close")))
        runtime.register("position.recall", lambda r, t, d: (_ for _ in ()).throw(UnsupportedCapability("no presets")))
        self.assertEqual(runtime.execute(CapabilityRequest("framing.set")).execution, Execution.CONSTRAINED)
        self.assertEqual(runtime.execute(CapabilityRequest("position.recall")).execution, Execution.UNSUPPORTED)

    def test_single_writer_resource_and_release(self):
        runtime = self.make()
        seen = []

        def handler(request, token, deadline):
            seen.append(runtime.ownership.owner("device_writer"))
            return {"execution": Execution.COMPLETED}

        runtime.register("target.select", handler, resources=("device_writer",))
        result = runtime.execute(CapabilityRequest("target.select", task_id="task1"))
        self.assertEqual(result.execution, Execution.COMPLETED)
        self.assertEqual(seen, ["task1"])
        self.assertIsNone(runtime.ownership.owner("device_writer"))

    def test_resource_busy_is_failed(self):
        runtime = self.make()
        runtime.ownership.acquire("device_writer", "other")
        runtime.register("target.select", lambda r, t, d: {"execution": Execution.COMPLETED},
                         resources=("device_writer",))
        result = runtime.execute(CapabilityRequest("target.select", task_id="mine"))
        self.assertEqual(result.execution, Execution.FAILED)
        self.assertEqual(result.errors[0].code, "busy")
        self.assertEqual(runtime.ownership.owner("device_writer"), "other")

    def test_cancel_marks_cancelled(self):
        runtime = self.make()
        started = threading.Event()

        def handler(request, token, deadline):
            started.set()
            for _ in range(200):
                token.raise_if_cancelled()
                time.sleep(0.005)
            return {"execution": Execution.COMPLETED}

        runtime.register("look.nudge", handler)
        outcome = {}

        def run():
            outcome["result"] = runtime.execute(CapabilityRequest("look.nudge", task_id="t1"))

        thread = threading.Thread(target=run)
        thread.start()
        started.wait(2)
        self.assertTrue(runtime.cancel("t1"))
        thread.join(3)
        self.assertEqual(outcome["result"].execution, Execution.CANCELLED)

    def test_single_writer_serializes(self):
        runtime = self.make()
        active = {"n": 0, "max": 0}
        lock = threading.Lock()

        def handler(request, token, deadline):
            with lock:
                active["n"] += 1
                active["max"] = max(active["max"], active["n"])
            time.sleep(0.05)
            with lock:
                active["n"] -= 1
            return {"execution": Execution.COMPLETED}

        runtime.register("status.get", handler)
        threads = [threading.Thread(target=lambda: runtime.execute(CapabilityRequest("status.get"))) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(active["max"], 1)

    def test_cancel_unknown_and_cancel_all(self):
        runtime = self.make()
        self.assertFalse(runtime.cancel("nope"))
        runtime.register("status.get", lambda r, t, d: {"execution": Execution.COMPLETED})
        self.assertEqual(runtime.cancel_all(), 0)


class FakeBridge:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.calls = []
        self.closed = False

    def request(self, op, args=None, timeout=20):
        if self.fail:
            raise BridgeError("session dead")
        self.calls.append(op)
        return {"ok": True, "result": {}}

    def close(self):
        self.closed = True


class SessionTests(unittest.TestCase):
    def test_rebuild_on_transport_failure(self):
        bridges = []

        def factory():
            bridge = FakeBridge()
            bridges.append(bridge)
            return bridge

        state = StateRegistry()
        state.set("target", {"candidate_id": "c1"})
        ownership = ResourceOwnership()
        ownership.acquire("device_writer", "task1")
        epochs = []
        session = RuntimeSession(factory, state=state, ownership=ownership, on_rebuild=epochs.append)
        self.assertEqual(session.request("device.status")["ok"], True)
        bridges[0].fail = True
        with self.assertRaises(BridgeError):
            session.request("device.status")
        self.assertEqual(session.camera_epoch, 1)
        self.assertEqual(session.rebuilds, 1)
        self.assertEqual(epochs, [1])
        self.assertTrue(bridges[0].closed)
        self.assertEqual(state.read("target", stale_after_s=1)["value"], None)
        self.assertEqual(ownership.held(), {})
        self.assertEqual(session.request("device.status")["ok"], True)

    def test_explicit_rebuild_bumps_epoch(self):
        session = RuntimeSession(lambda: FakeBridge())
        self.assertEqual(session.camera_epoch, 0)
        self.assertEqual(session.rebuild(), 1)
        self.assertEqual(session.rebuild("manual"), 2)
        session.close()
