"""Frame-bound observation store.

A candidate ref must belong to the frame the caller actually observed. Target
selection validates stream_session / camera_epoch / freshness / calibration and
candidate membership before anything is sent to the device. It never replaces
the observed frame with a fresh snapshot.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from math import isfinite
from typing import Any


class ReobserveRequired(RuntimeError):
    """The reference is stale, from another epoch/session, or has no such candidate."""


@dataclass(frozen=True)
class ObservedCandidate:
    candidate_id: str
    category: str
    bbox: tuple[float, float, float, float]
    provider: str

    def as_dict(self) -> dict:
        return {"candidate_id": self.candidate_id, "class": self.category,
                "bbox": list(self.bbox), "provider": self.provider}


@dataclass(frozen=True)
class ObservationRecord:
    observation_id: str
    frame_seq: int
    camera_epoch: int
    stream_session: str
    received_mono: float
    width: int
    height: int
    calibration_id: str
    provider: str | None
    candidates: tuple[ObservedCandidate, ...] = field(default_factory=tuple)

    def candidate(self, candidate_id: str) -> ObservedCandidate:
        for candidate in self.candidates:
            if candidate.candidate_id == candidate_id:
                return candidate
        raise ReobserveRequired(f"candidate {candidate_id!r} does not belong to {self.observation_id}")


class ObservationStore:
    def __init__(self, capacity: int = 64):
        if capacity <= 0:
            raise ValueError("positive capacity required")
        self.capacity = capacity
        self._items: dict[str, ObservationRecord] = {}
        self._order: list[str] = []

    def put(self, record: ObservationRecord) -> ObservationRecord:
        if record.observation_id in self._items:
            raise ValueError("duplicate observation id")
        self._items[record.observation_id] = record
        self._order.append(record.observation_id)
        while len(self._order) > self.capacity:
            self._items.pop(self._order.pop(0), None)
        return record

    def get(self, observation_id: str) -> ObservationRecord | None:
        return self._items.get(observation_id)

    def validate(self, observation_id: str, *, stream_session: str, camera_epoch: int,
                 now_mono: float, max_age_s: float, calibration_id: str) -> ObservationRecord:
        record = self.get(observation_id)
        if record is None:
            raise ReobserveRequired("unknown or evicted observation")
        if record.stream_session != stream_session:
            raise ReobserveRequired("stream session changed since observation")
        if record.camera_epoch != camera_epoch:
            raise ReobserveRequired("camera epoch changed since observation")
        age = now_mono - record.received_mono
        if not isfinite(age) or age < 0 or age > max_age_s:
            raise ReobserveRequired("observation is stale")
        if record.calibration_id != calibration_id:
            raise ReobserveRequired("calibration changed since observation")
        return record


def record_from_snapshot(snapshot: dict, *, calibration_id: str, provider: str | None) -> ObservationRecord:
    candidates = tuple(ObservedCandidate(c["candidate_id"], c.get("class", "common"),
                                         tuple(c["bbox"]), c.get("provider", "unknown"))
                       for c in snapshot.get("candidates", []))
    return ObservationRecord(
        observation_id=snapshot["observation_id"], frame_seq=snapshot["frame_seq"],
        camera_epoch=snapshot["camera_epoch"], stream_session=snapshot["stream_session"],
        received_mono=snapshot["received_mono"], width=snapshot["width"], height=snapshot["height"],
        calibration_id=calibration_id, provider=provider, candidates=candidates)
