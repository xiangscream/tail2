import unittest

from tail2_mvp.calibration import CalibrationStore, RoiCalibration
from tail2_mvp.contracts import Box


class CalibrationTests(unittest.TestCase):
    def test_unverified_blocks_mapping(self):
        with self.assertRaises(ValueError):
            RoiCalibration.unverified().to_sdk(Box(0.1, 0.1, 0.2, 0.2))

    def test_identity(self):
        cal = RoiCalibration("c", verified=True)
        self.assertEqual(cal.to_sdk(Box(0.1, 0.2, 0.4, 0.9)),
                         {"x1": 0.1, "y1": 0.2, "x2": 0.4, "y2": 0.9})

    def test_mirror_x(self):
        cal = RoiCalibration("c", verified=True, mirror_x=True)
        roi = cal.to_sdk(Box(0.1, 0.2, 0.4, 0.9))
        self.assertAlmostEqual(roi["x1"], 0.6)
        self.assertAlmostEqual(roi["x2"], 0.9)
        self.assertAlmostEqual(roi["y1"], 0.2)

    def test_crop_expands(self):
        cal = RoiCalibration("c", verified=True, crop=(0.25, 0.25, 0.75, 0.75))
        roi = cal.to_sdk(Box(0.0, 0.0, 1.0, 1.0))
        self.assertAlmostEqual(roi["x1"], 0.25)
        self.assertAlmostEqual(roi["x2"], 0.75)

    def test_zoom_center_crop(self):
        cal = RoiCalibration("c", verified=True, zoom=2.0)
        roi = cal.to_sdk(Box(0.0, 0.0, 1.0, 1.0))
        self.assertAlmostEqual(roi["x1"], 0.25)
        self.assertAlmostEqual(roi["x2"], 0.75)

    def test_rotation_180(self):
        cal = RoiCalibration("c", verified=True, rotation_deg=180)
        roi = cal.to_sdk(Box(0.1, 0.2, 0.4, 0.9))
        self.assertAlmostEqual(roi["x1"], 0.6)
        self.assertAlmostEqual(roi["y1"], 0.1)

    def test_invalid_parameters(self):
        with self.assertRaises(ValueError):
            RoiCalibration("c", rotation_deg=90)
        with self.assertRaises(ValueError):
            RoiCalibration("c", crop=(0.5, 0.5, 0.5, 0.6))
        with self.assertRaises(ValueError):
            RoiCalibration("c", zoom=0)

    def test_describe(self):
        cal = RoiCalibration("c", verified=True, note="left/center/right")
        described = cal.describe()
        self.assertTrue(described["verified"])
        self.assertEqual(described["note"], "left/center/right")


class CalibrationStoreTests(unittest.TestCase):
    IDENTITY = {"left": (0.2, 0.5), "center": (0.5, 0.5), "right": (0.8, 0.5),
                "top": (0.5, 0.2), "middle": (0.5, 0.5), "bottom": (0.5, 0.8)}
    ROI = {"x1": 0.1, "y1": 0.1, "x2": 0.2, "y2": 0.2}

    def seed(self, store, geometry=None, outcomes=True):
        for position, (x, y) in (geometry or self.IDENTITY).items():
            store.add_geometry_sample(position, "obs", x, y)
        for position in ("left", "center", "right", "top", "middle", "bottom"):
            store.record_outcome(position, "obs", [0.1, 0.1, 0.2, 0.2], self.ROI, outcomes)

    def test_verify_requires_sdk_outcomes(self):
        store = CalibrationStore()
        store.set_profile(calibration_id="c")
        for position, (x, y) in self.IDENTITY.items():
            store.add_geometry_sample(position, "obs", x, y)
        with self.assertRaises(ValueError):
            store.verify()  # geometry alone cannot verify

    def test_verify_with_passing_outcomes(self):
        store = CalibrationStore()
        store.set_profile(calibration_id="c")
        self.seed(store)
        profile = store.verify()
        self.assertTrue(profile.verified)
        self.assertEqual(len(profile.outcomes), 4)

    def test_verify_rejects_failed_outcome(self):
        store = CalibrationStore()
        store.set_profile(calibration_id="c")
        self.seed(store, outcomes=True)
        store.record_outcome("right", "obs", [0.1, 0.1, 0.2, 0.2], self.ROI, False, "wrong target")
        with self.assertRaises(ValueError):
            store.verify()

    def test_geometry_sanity_still_checked(self):
        store = CalibrationStore()
        store.set_profile(calibration_id="c")
        bad = dict(self.IDENTITY)
        bad["left"] = (0.6, 0.5)
        self.seed(store, geometry=bad)
        with self.assertRaises(ValueError):
            store.verify()

    def test_reconnect_invalidates(self):
        store = CalibrationStore()
        store.set_profile(calibration_id="c")
        self.seed(store)
        store.verify()
        store.bind_camera_epoch(0)
        store.bind_camera_epoch(1)
        self.assertFalse(store.profile().verified)
