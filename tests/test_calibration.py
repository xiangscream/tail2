import unittest

from tail2_mvp.calibration import RoiCalibration
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
