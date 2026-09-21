import unittest

from tail2_mvp.state import LastGood, detect_uvc_conflicts, discover_tail2


class LastGoodTests(unittest.TestCase):
    def test_update_then_stale(self):
        state = LastGood(stale_after_s=2.0)
        state.update({"yaw": 3.6}, 100.0)
        fresh = state.read(101.0)
        self.assertFalse(fresh["stale"])
        self.assertEqual(fresh["value"], {"yaw": 3.6})
        stale = state.read(105.0)
        self.assertTrue(stale["stale"])
        self.assertEqual(stale["value"], {"yaw": 3.6})

    def test_error_keeps_last_value(self):
        state = LastGood()
        state.update({"yaw": 1.0}, 10.0)
        state.fail("rc=-1")
        read = state.read(10.1)
        self.assertTrue(read["stale"])
        self.assertEqual(read["error"], "rc=-1")
        self.assertEqual(read["value"], {"yaw": 1.0})

    def test_no_value_is_stale_unknown(self):
        read = LastGood().read(1.0)
        self.assertIsNone(read["value"])
        self.assertTrue(read["stale"])


class DiscoveryTests(unittest.TestCase):
    def test_finds_eligible_tail2(self):
        calls = {"n": 0}
        clock = {"t": 0.0}

        def request(op, args):
            calls["n"] += 1
            if calls["n"] < 3:
                return {"ok": True, "result": {"devices": []}}
            return {"ok": True, "result": {"devices": [{"product_type": 11, "eligible": True, "sn": "S"}]}}

        device = discover_tail2(request, timeout=10, interval=0.1, clock=lambda: clock["t"],
                                sleep=lambda s: clock.__setitem__("t", clock["t"] + s))
        self.assertEqual(device["sn"], "S")
        self.assertEqual(calls["n"], 3)

    def test_ignores_ineligible_and_non_tail2(self):
        def request(op, args):
            return {"ok": True, "result": {"devices": [{"product_type": 11, "eligible": False},
                                                        {"product_type": 5, "eligible": True}]}}

        clock = {"t": 0.0}
        with self.assertRaises(TimeoutError):
            discover_tail2(request, timeout=1, interval=0.5, clock=lambda: clock["t"],
                           sleep=lambda s: clock.__setitem__("t", clock["t"] + s))

    def test_request_error_then_timeout(self):
        def request(op, args):
            raise RuntimeError("bridge down")

        clock = {"t": 0.0}
        with self.assertRaises(TimeoutError):
            discover_tail2(request, timeout=1, interval=0.5, clock=lambda: clock["t"],
                           sleep=lambda s: clock.__setitem__("t", clock["t"] + s))

    def test_conflict_detection(self):
        found = detect_uvc_conflicts(list_processes=lambda: ["OBSBOT_Center.exe", "chrome.exe"])
        self.assertEqual(found, ["obsbot_center.exe"])
        self.assertEqual(detect_uvc_conflicts(list_processes=lambda: []), [])
