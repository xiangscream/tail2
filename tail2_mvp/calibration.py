"""UVC pixel/normalized coordinates to Tail2 SDK ROI, with verified calibration.

A profile declares a mapping hypothesis (identity / mirror / rotation / crop /
zoom). It is only usable once every required position has a recorded SDK
selection outcome: the ROI actually sent to the device and whether the device
selected the target at that position. UVC-only samples are kept as a geometry
sanity check and cannot decide the transform on their own.
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
    geometry: tuple = field(default_factory=tuple)
    outcomes: tuple = field(default_factory=tuple)
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

    def to_sdk(self, box: Box, *, require_verified: bool = True) -> dict:
        if require_verified and not self.verified:
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
                "note": self.note, "geometry_samples": len(self.geometry),
                "outcomes": len(self.outcomes), "camera_epoch": self.camera_epoch,
                "width": self.width, "height": self.height}


class CalibrationStore:
    def __init__(self, directory: Path | None = None):
        self.directory = Path(directory) if directory else None
        self._profile = RoiCalibration.unverified()
        self._geometry: dict[str, dict] = {}
        self._outcomes: dict[str, dict] = {}
        self._camera_epoch: int | None = None

    @property
    def calibration_id(self) -> str:
        return self._profile.calibration_id

    def profile(self) -> RoiCalibration:
        return self._profile

    def set_profile(self, *, calibration_id: str, mirror_x: bool = False, rotation_deg: int = 0,
                    crop=None, zoom: float = 1.0, note: str = "", camera_epoch: int | None = None,
                    width: int | None = None, height: int | None = None) -> RoiCalibration:
        self._geometry = {}
        self._outcomes = {}
        self._profile = RoiCalibration(
            calibration_id=calibration_id, verified=False, mirror_x=bool(mirror_x),
            rotation_deg=int(rotation_deg), crop=tuple(crop) if crop else None, zoom=float(zoom),
            note=note, camera_epoch=camera_epoch, width=width, height=height)
        return self._profile

    def add_geometry_sample(self, position: str, observation_id: str, x: float, y: float) -> dict:
        self._require_position(position)
        if not observation_id:
            raise ValueError("observation_id required for a geometry sample")
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            raise ValueError("sample point must be normalized")
        self._geometry[position] = {"observation_id": observation_id, "x": float(x), "y": float(y)}
        return {"position": position, "geometry": sorted(self._geometry), "outcomes": sorted(self._outcomes)}

    def record_outcome(self, position: str, observation_id: str, uvc_bbox, sdk_roi: dict,
                       selected: bool, note: str = "") -> dict:
        self._require_position(position)
        if not observation_id:
            raise ValueError("observation_id required for a selection outcome")
        if not isinstance(sdk_roi, dict) or not all(k in sdk_roi for k in ("x1", "y1", "x2", "y2")):
            raise ValueError("sdk_roi must contain x1/y1/x2/y2")
        self._outcomes[position] = {"observation_id": observation_id,
                                    "uvc_bbox": list(uvc_bbox), "sdk_roi": sdk_roi,
                                    "selected": bool(selected), "note": note}
        return {"position": position, "selected": bool(selected),
                "geometry": sorted(self._geometry), "outcomes": sorted(self._outcomes)}

    def verify(self) -> RoiCalibration:
        missing_outcomes = [p for p in REQUIRED_POSITIONS if p not in self._outcomes]
        if missing_outcomes:
            raise ValueError(f"cannot verify: missing SDK selection outcomes {missing_outcomes}")
        failed = [p for p in REQUIRED_POSITIONS if not self._outcomes[p]["selected"]]
        if failed:
            raise ValueError(f"cannot verify: failed SDK selection outcomes {failed}")
        self._check_geometry()
        recorded = tuple((p, dict(self._outcomes[p])) for p in REQUIRED_POSITIONS)
        geometry = tuple((p, dict(self._geometry[p])) for p in REQUIRED_POSITIONS if p in self._geometry)
        self._profile = replace(self._profile, verified=True, outcomes=recorded, geometry=geometry)
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

    def _require_position(self, position: str) -> None:
        if position not in REQUIRED_POSITIONS:
            raise ValueError(f"position must be one of {REQUIRED_POSITIONS}")

    def _check_geometry(self) -> None:
        if not self._geometry:
            return
        xs = {p: self._geometry[p]["x"] for p in self._geometry}
        ys = {p: self._geometry[p]["y"] for p in self._geometry}
        if all(p in xs for p in ("left", "center", "right")):
            if not (xs["left"] < xs["center"] < xs["right"] or xs["left"] > xs["center"] > xs["right"]):
                raise ValueError("geometry sanity: left/center/right not monotonic")
        if all(p in ys for p in ("top", "middle", "bottom")):
            if not (ys["top"] < ys["middle"] < ys["bottom"] or ys["top"] > ys["middle"] > ys["bottom"]):
                raise ValueError("geometry sanity: top/middle/bottom not monotonic")

    def _persist(self) -> None:
        if not self.directory:
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{self._profile.calibration_id}.json"
        path.write_text(json.dumps(self._profile.describe()
                                   | {"geometry": self._geometry, "selection_outcomes": self._outcomes},
                                   ensure_ascii=False, indent=2), encoding="utf-8")
