"""Single-owner UVC observation service.

Exactly one VideoCapture reads Tail2 UVC. Snapshot, host_uvc photo, host_uvc
record, candidate detection and the read-only page all consume this one stream.
Real frames stay under the private output directory; they are never written to
the public trace.
"""
from __future__ import annotations

import hashlib
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

BACKENDS = {"dshow", "msmf", "v4l2", "any"}


def resolve_dshow_index(device_name: str, lister: Callable[[], list[str]] | None = None) -> int:
    if not device_name:
        raise ValueError("device name required")
    if lister is None:
        try:
            from pygrabber.dshow_graph import FilterGraph
        except Exception as exc:
            raise RuntimeError("device-name binding needs pygrabber; install the vision extra") from exc
        lister = lambda: FilterGraph().get_input_devices()
    names = lister()
    matches = [index for index, name in enumerate(names) if name == device_name]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise RuntimeError(f"no DirectShow device named {device_name!r}; saw {names}")
    raise RuntimeError(f"multiple DirectShow devices named {device_name!r}; resolve manually")


class FrameSource(Protocol):
    def open(self) -> None: ...
    def read(self) -> tuple[bool, Any]: ...
    def release(self) -> None: ...
    def describe(self) -> dict[str, Any]: ...


class UvcFrameSource:
    def __init__(self, index: int | None = None, backend: str = "dshow", width: int | None = None,
                 height: int | None = None, device_name: str | None = None):
        if backend not in BACKENDS:
            raise ValueError("unsupported capture backend")
        if index is None and not device_name:
            raise ValueError("explicit index or device_name required")
        if index is not None and device_name:
            raise ValueError("provide index or device_name, not both")
        if index is not None and (isinstance(index, bool) or not isinstance(index, int) or index < 0):
            raise ValueError("explicit nonnegative camera index required")
        if device_name and backend not in {"dshow", "any"}:
            raise ValueError("device_name binding requires the dshow backend")
        if (width is None) != (height is None):
            raise ValueError("width and height must be set together")
        if width is not None and (width <= 0 or height <= 0):
            raise ValueError("positive frame size required")
        self.index = index
        self.backend = backend
        self.width = width
        self.height = height
        self.device_name = device_name
        self.backend_name = ""
        self._cap = None

    def open(self) -> None:
        import cv2

        if self.device_name:
            self.index = resolve_dshow_index(self.device_name)
        chosen = {"dshow": cv2.CAP_DSHOW, "msmf": cv2.CAP_MSMF, "v4l2": cv2.CAP_V4L2, "any": cv2.CAP_ANY}[self.backend]
        cap = cv2.VideoCapture(self.index, chosen)
        if not cap.isOpened():
            raise RuntimeError(
                "UVC device did not open; verify the explicit index/backend and that no other "
                "consumer (for example OBSBOT Center) holds the camera"
            )
        if self.width and self.height:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._cap = cap
        self.backend_name = cap.getBackendName()

    def read(self) -> tuple[bool, Any]:
        if self._cap is None:
            raise RuntimeError("frame source not opened")
        ok, frame = self._cap.read()
        return bool(ok and frame is not None), frame

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def describe(self) -> dict[str, Any]:
        return {"kind": "uvc", "index": self.index, "backend": self.backend,
                "backend_name": self.backend_name, "device_name": self.device_name,
                "requested": [self.width, self.height]}


def default_encoder(frame: Any, max_width: int | None = None) -> bytes:
    import cv2

    image = frame
    if max_width:
        height, width = frame.shape[:2]
        if width > max_width:
            scale = max_width / width
            image = cv2.resize(frame, (max_width, max(1, round(height * scale))))
    ok, buffer = cv2.imencode(".jpg", image)
    if not ok:
        raise RuntimeError("JPEG encode failed")
    return buffer.tobytes()


def default_writer(path: Path, width: int, height: int, fps: float):
    import cv2

    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not writer.isOpened():
        raise RuntimeError("video writer did not open")
    return writer


@dataclass(frozen=True)
class Latest:
    seq: int
    frame: Any
    received_mono: float
    width: int
    height: int


class ObservationService:
    def __init__(self, source: FrameSource, output_dir: Path, *, encoder: Callable[..., bytes] = default_encoder,
                 preview_width: int = 640, writer_factory: Callable[..., Any] = default_writer,
                 detector: Callable[[Any, int, int], list[dict]] | None = None,
                 detector_interval_s: float = 0.5, max_frame_age_s: float = 2.0,
                 clock: Callable[[], float] = time.monotonic):
        if preview_width <= 0 or detector_interval_s <= 0 or max_frame_age_s <= 0:
            raise ValueError("invalid service timing/width")
        self.source = source
        self.output_dir = Path(output_dir)
        self.encoder = encoder
        self.preview_width = preview_width
        self.writer_factory = writer_factory
        self.detector = detector
        self.detector_interval_s = detector_interval_s
        self.max_frame_age_s = max_frame_age_s
        self.clock = clock
        self.stream_session = uuid.uuid4().hex
        self.camera_epoch = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._latest: Latest | None = None
        self._seq = 0
        self._read_errors = 0
        self._last_read_error: str | None = None
        self._candidates: list[dict] = []
        self._candidate_seq = -1
        self._writer = None
        self._writer_info: dict | None = None
        self._last_detect_mono = 0.0
        self._observations = 0
        self._photos = 0
        self._records = 0
        self._consecutive_errors = 0
        self._reconnects = 0

    def start(self, *, wait_s: float = 5.0) -> None:
        self.source.open()
        self._thread = threading.Thread(target=self._run, name="uvc-reader", daemon=True)
        self._thread.start()
        deadline = self.clock() + wait_s
        while self.clock() < deadline:
            with self._lock:
                if self._latest is not None:
                    return
            time.sleep(0.02)
        raise RuntimeError("no usable UVC frame within the wait window")

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        try:
            self.record_stop(silent=True)
        finally:
            self.source.release()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                ok, frame = self.source.read()
            except Exception as exc:
                self._mark_read_error(str(exc))
                self._maybe_reconnect()
                time.sleep(0.05)
                continue
            if not ok:
                self._mark_read_error("camera returned no frame")
                self._maybe_reconnect()
                time.sleep(0.05)
                continue
            now = self.clock()
            height, width = frame.shape[:2]
            detect = False
            with self._lock:
                self._seq += 1
                self._latest = Latest(self._seq, frame, now, width, height)
                self._last_read_error = None
                self._consecutive_errors = 0
                writer = self._writer
                info = self._writer_info
                if self.detector is not None and (now - self._last_detect_mono) >= self.detector_interval_s:
                    self._last_detect_mono = now
                    detect = True
            if writer is not None:
                try:
                    writer.write(frame)
                    with self._lock:
                        if self._writer_info is info and info is not None:
                            info["frames"] += 1
                except Exception as exc:
                    self._mark_read_error(f"writer: {exc}")
            if detect:
                try:
                    found = self.detector(frame, width, height)
                except Exception:
                    found = []
                with self._lock:
                    self._candidates = list(found)
                    self._candidate_seq = self._seq

    def _mark_read_error(self, message: str) -> None:
        with self._lock:
            self._read_errors += 1
            self._consecutive_errors += 1
            self._last_read_error = message

    def _maybe_reconnect(self) -> None:
        with self._lock:
            attempts = self._consecutive_errors
        if attempts < 10 or attempts % 20 != 0:
            return
        try:
            self.source.release()
        except Exception:
            pass
        try:
            self.source.open()
        except Exception as exc:
            with self._lock:
                self._last_read_error = f"reconnect failed: {exc}"
            return
        with self._lock:
            self.camera_epoch += 1
            self.stream_session = uuid.uuid4().hex
            self._reconnects += 1
            self._consecutive_errors = 0
            self._last_read_error = None
            self._candidates = []
            self._candidate_seq = -1

    def _require_latest(self) -> Latest:
        with self._lock:
            if self._latest is None:
                raise RuntimeError("no observation available")
            return self._latest

    def age_s(self) -> float:
        latest = self._require_latest()
        return self.clock() - latest.received_mono

    def snapshot(self, *, write: bool = True) -> dict:
        latest = self._require_latest()
        observation_id = uuid.uuid4().hex
        frame_file = None
        if write:
            directory = self.output_dir / "observations" / observation_id
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / "frame.jpg"
            path.write_bytes(self.encoder(latest.frame))
            frame_file = str(path)
        with self._lock:
            detector = self.detector
            self._observations += 1
        candidates = ([dict(c) for c in detector(latest.frame, latest.width, latest.height)]
                      if detector else [])
        age = self.clock() - latest.received_mono
        return {"observation_id": observation_id, "stream_session": self.stream_session,
                "camera_epoch": self.camera_epoch, "frame_seq": latest.seq,
                "width": latest.width, "height": latest.height,
                "received_mono": latest.received_mono, "age_s": age,
                "fresh": age <= self.max_frame_age_s, "source": self.source.describe(),
                "frame_file": frame_file, "candidates": candidates,
                "candidate_frame_seq": latest.seq,
                "provider": "host_detector" if detector else None,
                "note": "candidates are computed on this exact frame; host receipt time is not sensor exposure time"}

    def capture_photo(self, *, timeout: float = 2.0) -> dict:
        if timeout <= 0:
            raise ValueError("positive timeout required")
        with self._lock:
            start_seq = self._seq
        deadline = self.clock() + timeout
        latest = None
        while self.clock() < deadline:
            with self._lock:
                if self._seq > start_seq and self._latest is not None:
                    latest = self._latest
                    break
            time.sleep(0.01)
        if latest is None:
            raise TimeoutError("no frame arrived after the capture request; no photo produced")
        media_id = uuid.uuid4().hex
        observation_id = uuid.uuid4().hex
        directory = self.output_dir / "photos"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{media_id}.jpg"
        data = self.encoder(latest.frame)
        path.write_bytes(data)
        manifest = directory / f"{media_id}.json"
        manifest.write_text(_json({"media_id": media_id, "provider": "host_uvc",
                                   "captured_observation_id": observation_id,
                                   "frame_seq": latest.seq, "captured_mono": latest.received_mono,
                                   "sha256": hashlib.sha256(data).hexdigest(),
                                   "note": "frame taken strictly after the capture request"}))
        with self._lock:
            self._photos += 1
        return {"media_id": media_id, "provider": "host_uvc", "path_ref": str(path),
                "manifest_ref": str(manifest), "captured_observation_id": observation_id,
                "frame_seq": latest.seq, "captured_mono": latest.received_mono,
                "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                "finalized": True, "accessible": path.stat().st_size == len(data)}

    def record_start(self, *, fps: float = 30.0) -> dict:
        if not 0 < fps <= 240:
            raise ValueError("invalid fps")
        with self._lock:
            if self._writer is not None:
                raise RuntimeError("a recording is already active")
            latest = self._latest
        if latest is None:
            raise RuntimeError("no observation available")
        recording_id = uuid.uuid4().hex
        directory = self.output_dir / "recordings"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{recording_id}.mp4"
        writer = self.writer_factory(path, latest.width, latest.height, fps)
        with self._lock:
            self._writer = writer
            self._writer_info = {"recording_id": recording_id, "path": path, "fps": fps,
                                 "width": latest.width, "height": latest.height, "frames": 0}
        return {"recording_id": recording_id, "provider": "host_uvc", "path_ref": str(path),
                "started": True, "finalized": False, "accessible": False}

    def record_stop(self, *, silent: bool = False) -> dict | None:
        with self._lock:
            writer = self._writer
            info = self._writer_info
            self._writer = None
            self._writer_info = None
        if writer is None:
            if silent:
                return None
            raise RuntimeError("no active recording")
        error = None
        try:
            writer.release()
        except Exception as exc:
            error = str(exc)
        path = Path(info["path"])
        finalized = error is None and path.exists() and path.stat().st_size > 0
        with self._lock:
            self._records += 1
        return {"recording_id": info["recording_id"], "provider": "host_uvc",
                "path_ref": str(path), "frames": info["frames"], "fps": info["fps"],
                "finalized": finalized, "accessible": finalized, "error": error}

    def preview_jpeg(self) -> bytes:
        latest = self._require_latest()
        return self.encoder(latest.frame, self.preview_width)

    def candidates(self) -> list[dict]:
        with self._lock:
            return [dict(c) for c in self._candidates]

    def status(self) -> dict:
        with self._lock:
            latest = self._latest
            recording = dict(self._writer_info) if self._writer_info else None
            status = {"stream_session": self.stream_session, "camera_epoch": self.camera_epoch,
                      "frames": latest.seq if latest else 0,
                      "width": latest.width if latest else None,
                      "height": latest.height if latest else None,
                      "last_frame_age_s": (self.clock() - latest.received_mono) if latest else None,
                      "read_errors": self._read_errors, "last_read_error": self._last_read_error,
                      "reconnects": self._reconnects,
                      "candidate_count": len(self._candidates),
                      "observations": self._observations, "photos": self._photos,
                      "records": self._records, "source": self.source.describe()}
        status["recording"] = recording
        return status


def _json(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, indent=2)
