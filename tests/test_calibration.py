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

    def seed(self, store, mapping):
        for position, (x, y) in mapping.items():
            store.add_sample(position, "obs", x, y)

    def test_derives_identity(self):
        store = CalibrationStore()
        store.set_profile(calibration_id="c")
        self.seed(store, self.IDENTITY)
        profile = store.verify()
        self.assertTrue(profile.verified)
        self.assertFalse(profile.mirror_x)
        self.assertEqual(profile.rotation_deg, 0)

    def test_derives_mirror(self):
        store = CalibrationStore()
        store.set_profile(calibration_id="c")
        mirrored = dict(self.IDENTITY)
        mirrored["left"], mirrored["right"] = (0.8, 0.5), (0.2, 0.5)
        self.seed(store, mirrored)
        self.assertTrue(store.verify().mirror_x)

    def test_rejects_non_monotonic(self):
        store = CalibrationStore()
        store.set_profile(calibration_id="c")
        bad = dict(self.IDENTITY)
        bad["left"] = (0.6, 0.5)
        self.seed(store, bad)
        with self.assertRaises(ValueError):
            store.verify()

    def test_reconnect_invalidates(self):
        store = CalibrationStore()
        store.set_profile(calibration_id="c")
        self.seed(store, self.IDENTITY)
        store.verify()
        store.bind_camera_epoch(0)
        store.bind_camera_epoch(1)
        self.assertFalse(store.profile().verified)
