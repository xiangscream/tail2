"""UVC pixel/normalized coordinates to Tail2 SDK ROI, with trusted calibration.

A profile is only usable once it is verified from a persisted on-device sample
set. Ordinary commands (and therefore an Agent) cannot declare verification on
their own. Reconnect or a condition change invalidates the profile.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path

from .contracts import Box

ROTATIONS = (0, 180)
REQUIRED_POSITIONS = ("left", "center", "right", "top", "middle", "bottom")


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
    camera_epoch: int | None = None
    width: int | None = None
    height: int | None = None

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
                "note": self.note, "samples": len(self.samples),
                "camera_epoch": self.camera_epoch, "width": self.width, "height": self.height}


class CalibrationStore:
    def __init__(self, directory: Path | None = None):
        self.directory = Path(directory) if directory else None
        self._profile = RoiCalibration.unverified()
        self._samples: dict[str, dict] = {}
        self._camera_epoch: int | None = None

    @property
    def calibration_id(self) -> str:
        return self._profile.calibration_id

    def profile(self) -> RoiCalibration:
        return self._profile

    def set_profile(self, *, calibration_id: str, mirror_x: bool = False, rotation_deg: int = 0,
                    crop=None, zoom: float = 1.0, note: str = "", camera_epoch: int | None = None,
                    width: int | None = None, height: int | None = None) -> RoiCalibration:
        self._samples = {}
        self._profile = RoiCalibration(
            calibration_id=calibration_id, verified=False, mirror_x=bool(mirror_x),
            rotation_deg=int(rotation_deg), crop=tuple(crop) if crop else None, zoom=float(zoom),
            note=note, camera_epoch=camera_epoch, width=width, height=height)
        return self._profile

    def add_sample(self, position: str, observation_id: str, x: float, y: float) -> dict:
        if position not in REQUIRED_POSITIONS:
            raise ValueError(f"position must be one of {REQUIRED_POSITIONS}")
        if not observation_id:
            raise ValueError("observation_id required for a calibration sample")
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            raise ValueError("sample point must be normalized")
        self._samples[position] = {"observation_id": observation_id, "x": float(x), "y": float(y)}
        return {"position": position, "recorded": True, "samples": sorted(self._samples)}

    def verify(self) -> RoiCalibration:
        missing = [position for position in REQUIRED_POSITIONS if position not in self._samples]
        if missing:
            raise ValueError(f"cannot verify: missing samples {missing}")
        xs = {position: self._samples[position]["x"] for position in REQUIRED_POSITIONS}
        ys = {position: self._samples[position]["y"] for position in REQUIRED_POSITIONS}
        left, center, right = xs["left"], xs["center"], xs["right"]
        top, middle, bottom = ys["top"], ys["middle"], ys["bottom"]
        horizontal = left < center < right or left > center > right
        vertical = top < middle < bottom or top > middle > bottom
        if not horizontal or min(abs(left - center), abs(center - right)) < 0.05:
            raise ValueError("horizontal samples must be monotonic left/center/right with >0.05 separation")
        if not vertical or min(abs(top - middle), abs(middle - bottom)) < 0.05:
            raise ValueError("vertical samples must be monotonic top/middle/bottom with >0.05 separation")
        mirror_x = left > right
        rotation_deg = 180 if top > bottom else 0
        recorded = tuple((position, dict(self._samples[position])) for position in REQUIRED_POSITIONS)
        self._profile = replace(self._profile, verified=True, mirror_x=mirror_x,
                                rotation_deg=rotation_deg, samples=recorded)
        self._persist()
        return self._profile

    def invalidate(self, reason: str) -> RoiCalibration:
        if self._profile.verified:
            self._profile = replace(self._profile, verified=False, note=reason)
        return self._profile

    def bind_camera_epoch(self, camera_epoch: int) -> None:
        if self._camera_epoch is None:
            self._camera_epoch = camera_epoch
            if self._profile.camera_epoch is None:
                self._profile = replace(self._profile, camera_epoch=camera_epoch)
            return
        if camera_epoch != self._camera_epoch:
            self._camera_epoch = camera_epoch
            self.invalidate("camera epoch changed; recalibrate before sending ROI")

    def _persist(self) -> None:
        if not self.directory:
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{self._profile.calibration_id}.json"
        path.write_text(json.dumps(self._profile.describe() | {"samples": self._samples},
                                   ensure_ascii=False, indent=2), encoding="utf-8")
