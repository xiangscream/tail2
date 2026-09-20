"""UVC pixel/normalized coordinates to Tail2 SDK ROI.

The transform is empirical: it is only trusted once a real left/center/right and
top/middle/bottom calibration has been recorded. An unverified calibration must
not be used to send a target ROI.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .contracts import Box

ROTATIONS = (0, 180)


@dataclass(frozen=True)
class RoiCalibration:
    calibration_id: str
    verified: bool = False
    mirror_x: bool = False
    rotation_deg: int = 0
    crop: tuple[float, float, float, float] | None = None
    zoom: float = 1.0
    note: str = ""
    samples: tuple = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.calibration_id:
            raise ValueError("calibration_id required")
        if self.rotation_deg not in ROTATIONS:
            raise ValueError("only 0/180 rotation is modelled; 90/270 needs a separate mapping")
        if self.zoom <= 0:
            raise ValueError("positive zoom required")
        if self.crop is not None:
            x0, y0, x1, y1 = self.crop
            if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
                raise ValueError("crop must be an increasing sub-rectangle of the unit square")

    @classmethod
    def unverified(cls, note: str = "not calibrated on device") -> "RoiCalibration":
        return cls(calibration_id="unverified", verified=False, note=note)

    def _window(self) -> tuple[float, float, float, float] | None:
        if self.crop is not None:
            return self.crop
        if self.zoom > 1.0:
            half = 0.5 / self.zoom
            return (0.5 - half, 0.5 - half, 0.5 + half, 0.5 + half)
        return None

    def to_sdk(self, box: Box) -> dict:
        if not self.verified:
            raise ValueError("UVC to SDK ROI mapping is not verified; do not send a target ROI")
        x1, y1, x2, y2 = box.x1, box.y1, box.x2, box.y2
        window = self._window()
        if window is not None:
            x0, y0, wx, wy = window
            x1, x2 = x0 + x1 * (wx - x0), x0 + x2 * (wx - x0)
            y1, y2 = y0 + y1 * (wy - y0), y0 + y2 * (wy - y0)
        if self.rotation_deg == 180:
            x1, x2 = 1 - x2, 1 - x1
            y1, y2 = 1 - y2, 1 - y1
        if self.mirror_x:
            x1, x2 = 1 - x2, 1 - x1
        x1, y1 = max(0.0, min(1.0, x1)), max(0.0, min(1.0, y1))
        x2, y2 = max(0.0, min(1.0, x2)), max(0.0, min(1.0, y2))
        if x1 >= x2 or y1 >= y2:
            raise ValueError("calibrated ROI has no positive area")
        return {"x1": x1, "y1": y1, "x2": x2, "y2": y2}

    def describe(self) -> dict:
        return {"calibration_id": self.calibration_id, "verified": self.verified,
                "mirror_x": self.mirror_x, "rotation_deg": self.rotation_deg,
                "crop": list(self.crop) if self.crop else None, "zoom": self.zoom,
                "note": self.note, "samples": len(self.samples)}
