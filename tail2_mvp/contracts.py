"""Small testable pieces of the future capability contract.

No hardware driver lives here. Coordinate/freshness checks do not establish
candidate identity or physical completion; those require current observations.
"""
from dataclasses import dataclass, field
from math import isfinite
from typing import Any


@dataclass(frozen=True)
class Box:
    x1: float
    y1: float
    x2: float
    y2: float

    def __post_init__(self) -> None:
        coords = (self.x1, self.y1, self.x2, self.y2)
        if any(isinstance(v, bool) or not isinstance(v, (int, float))
               or not isfinite(v) or not 0 <= v <= 1 for v in coords):
            raise ValueError("normalized finite coordinates required")
        if self.x1 >= self.x2 or self.y1 >= self.y2:
            raise ValueError("positive-area box required")

    def mirrored_x(self) -> "Box":
        return Box(1 - self.x2, self.y1, 1 - self.x1, self.y2)

    def sdk_args(self) -> dict[str, float]:
        return dict(x1=self.x1, y1=self.y1, x2=self.x2, y2=self.y2)


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    category: str
    box: Box
    provider: str

    def __post_init__(self) -> None:
        if not self.candidate_id or not self.provider:
            raise ValueError("candidate id and provider required")
        if self.category not in {"human", "animal", "common"}:
            raise ValueError("unsupported category")


@dataclass(frozen=True)
class Observation:
    observation_id: str
    stream_session: str
    camera_epoch: int
    width: int
    height: int
    received_mono: float
    candidates: tuple[Candidate, ...] = ()
    mapping_verified: bool = False
    sensor_timestamp: float | None = None

    def __post_init__(self) -> None:
        if (not self.observation_id or not self.stream_session or self.width <= 0
                or self.height <= 0 or self.camera_epoch < 0
                or not isfinite(self.received_mono)):
            raise ValueError("invalid observation metadata")
        ids = [c.candidate_id for c in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("candidate IDs must be unique within an observation")


def selection_request(obs: Observation, candidate_id: str, *, stream_session: str,
                      camera_epoch: int, now_mono: float, max_age_s: float) -> dict:
    """Create an M0 request only after caller's calibration and freshness checks.

    A finite max_age is a local policy, not a claim about camera/USB latency.
    M1 must also reacquire moving targets between model observation and selection.
    """
    if not obs.mapping_verified:
        raise ValueError("UVC-to-SDK coordinate mapping is unverified")
    if obs.stream_session != stream_session or obs.camera_epoch != camera_epoch:
        raise ValueError("observation invalidated by stream/camera change")
    if not isfinite(now_mono) or not isfinite(max_age_s) or max_age_s <= 0:
        raise ValueError("invalid age policy")
    age = now_mono - obs.received_mono
    if age < 0 or age > max_age_s:
        raise ValueError("observation stale or from incompatible clock")
    candidate = next((c for c in obs.candidates if c.candidate_id == candidate_id), None)
    if candidate is None:
        raise ValueError("candidate does not belong to this observation")
    return {"op": "target.select", "args": {"class": candidate.category, **candidate.box.sdk_args()},
            "observation_id": obs.observation_id, "candidate_id": candidate_id}


@dataclass
class EvidenceState:
    requested: dict[str, Any] = field(default_factory=dict)
    sdk_reported: dict[str, Any] = field(default_factory=dict)
    visual_check: dict[str, Any] | None = None

    def request(self, key: str, value: Any) -> None:
        self.requested[key] = value
        self.visual_check = None  # A new command invalidates an earlier visual verdict.

    def report(self, values: dict[str, Any], source: str, received_mono: float) -> None:
        self.sdk_reported = {"values": values, "source": source, "received_mono": received_mono}

    def verify_visual(self, observation_id: str, verdict: str) -> None:
        if not observation_id or verdict not in {"satisfied", "unsatisfied", "uncertain"}:
            raise ValueError("explicit visual evidence required")
        self.visual_check = {"observation_id": observation_id, "verdict": verdict}


def dispatch_outcome(response: dict) -> str:
    """Return protocol/dispatch outcome; never infer physical completion."""
    if response.get("transport_error"):
        return "indeterminate"
    if response.get("ok") is not True:
        return "rejected"
    return "accepted_unverified"
