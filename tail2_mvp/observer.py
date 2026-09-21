"""Supervised M0.5 observer.

One Observation Service owns Tail2 UVC; the native bridge owns SDK control.
Target selection must reference the frame the caller actually observed; the
adapter never replaces it with a fresh snapshot. Calibration is only usable
after a persisted on-device sample set is verified.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

from .bridge import Bridge
from .calibration import CalibrationStore
from .contracts import Box
from .events import Trace
from .observation_service import ObservationService, UvcFrameSource
from .observations import ObservationStore, ReobserveRequired, record_from_snapshot
from .state import LastGood, detect_uvc_conflicts, discover_tail2
from .status import StatusServer

TARGET_CLASSES = {"human", "animal", "common"}
FRAMING_MODES = {"full_body", "half_body", "close_up", "normal"}


def hog_detector(frame, width: int, height: int) -> list[dict]:
    import cv2

    scale = min(1.0, 960 / width)
    small = cv2.resize(frame, (max(1, round(width * scale)), max(1, round(height * scale))))
    hog = cv2.HOGDescriptor()
    hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
    boxes, weights = hog.detectMultiScale(small, winStride=(8, 8), padding=(8, 8), scale=1.05)
    height_small, width_small = small.shape[:2]
    found = []
    for index, ((x, y, box_w, box_h), weight) in enumerate(zip(boxes, weights)):
        bbox = [max(0.0, x / width_small), max(0.0, y / height_small),
                min(1.0, (x + box_w) / width_small), min(1.0, (y + box_h) / height_small)]
        if bbox[0] < bbox[2] and bbox[1] < bbox[3]:
            found.append({"candidate_id": f"human-{index + 1}", "class": "human", "bbox": bbox,
                          "provider": "opencv_hog_bench", "detector_margin": float(weight)})
    return found


def face_detector(frame, width: int, height: int) -> list[dict]:
    import cv2

    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = cascade.detectMultiScale(gray, 1.1, 5, minSize=(max(24, width // 40), max(24, height // 40)))
    found = []
    for index, (x, y, box_w, box_h) in enumerate(faces):
        found.append({"candidate_id": f"face-{index + 1}", "class": "human",
                      "bbox": [x / width, y / height, (x + box_w) / width, (y + box_h) / height],
                      "provider": "opencv_face_bench", "detector_margin": None})
    return found


class Observer:
    def __init__(self, service: ObservationService, bridge: Bridge, trace: Trace, *,
                 calibration: CalibrationStore | None = None, control: bool = False, legacy: bool = False,
                 conflicts: list[str] | None = None, clock=time.monotonic, gimbal_stale_s: float = 3.0,
                 allow_control_writes: bool = False, session=None):
        self.service = service
        self.bridge = bridge
        self.session = session
        self.trace = trace
        self.calibration = calibration or CalibrationStore()
        self.observations = ObservationStore()
        self.control = control
        self.legacy = legacy
        self.allow_control_writes = allow_control_writes
        self.conflicts = conflicts or []
        self.clock = clock
        self.gimbal = LastGood(stale_after_s=gimbal_stale_s)
        self.requested_roi: list[float] | None = None
        self.requested_roi_sdk: list[float] | None = None
        self.selected: dict | None = None
        self.track = {"requested": None, "sdk_reported": None}
        self.framing = {"requested": None, "sdk_reported": None, "visual_check": None}
        self.ai_status: dict = {}
        self._last_epoch = service.camera_epoch
        self._call_timeout: float | None = None
        self._handle_lock = threading.Lock()
        self._lock = threading.Lock()

    def _require_control(self) -> None:
        if not self.control:
            raise RuntimeError("control disabled: restart with --allow-control")

    def _require_legacy(self) -> None:
        if not self.legacy:
            raise RuntimeError("legacy probe disabled: restart with --allow-legacy-probes")

    def _call(self, op: str, args: dict | None = None, timeout: float | None = None) -> dict:
        resolved = timeout if timeout is not None else self._call_timeout
        if resolved is None:
            resolved = 20.0
        resolved = max(0.05, min(60.0, resolved))
        if self.session is not None:
            return self.session.request(op, args or {}, timeout=resolved)
        return self.bridge.request(op, args or {}, timeout=resolved)

    def _record_ai(self, result: dict) -> None:
        with self._lock:
            self.ai_status = {k: result.get(k) for k in
                              ("ai_main_mode_raw", "ai_sub_mode_raw", "record_operation_raw")}

    def _sync_epoch(self) -> None:
        epoch = self.service.camera_epoch
        if epoch != self._last_epoch:
            self._last_epoch = epoch
            self.calibration.bind_camera_epoch(epoch)
            with self._lock:
                self.requested_roi = None
                self.requested_roi_sdk = None
                self.selected = None

    def check_observation(self, observation_id: str):
        self._sync_epoch()
        return self.observations.validate(observation_id, stream_session=self.service.stream_session,
                                          camera_epoch=self.service.camera_epoch, now_mono=self.clock(),
                                          max_age_s=self.service.max_frame_age_s,
                                          calibration_id=self.calibration.calibration_id)

    def invalidate(self, reason: str = "session rebuild") -> None:
        self.observations.clear()
        self.calibration.invalidate(reason)
        with self._lock:
            self.requested_roi = None
            self.requested_roi_sdk = None
            self.selected = None
            self.track = {"requested": None, "sdk_reported": {"invalidated": reason}}
            self.framing = {"requested": None, "sdk_reported": {"invalidated": reason},
                            "visual_check": None}

    def snapshot(self, args: dict | None = None) -> dict:
        self._sync_epoch()
        write = bool((args or {}).get("write", True))
        snapshot = self.service.snapshot(write=write)
        record = record_from_snapshot(snapshot, calibration_id=self.calibration.calibration_id,
                                      provider=snapshot.get("provider"))
        self.observations.put(record)
        snapshot = dict(snapshot)
        snapshot["calibration_id"] = record.calibration_id
        return snapshot

    def calibration_profile(self, args: dict) -> dict:
        profile = self.calibration.set_profile(
            calibration_id=args.get("calibration_id", "on-device"),
            mirror_x=bool(args.get("mirror_x", False)),
            rotation_deg=int(args.get("rotation_deg", 0)),
            crop=args.get("crop"),
            zoom=float(args.get("zoom", 1.0)),
            note=args.get("note", ""),
            camera_epoch=self.service.camera_epoch,
            width=self.service.status().get("width"), height=self.service.status().get("height"))
        return profile.describe()

    def _read_ai_mode(self):
        response = self._call("device.status")
        if response.get("ok") and isinstance(response.get("result"), dict):
            self._record_ai(response["result"])
            return response["result"].get("ai_main_mode_raw")
        return None

    def _enter_track(self, selection: str = "center", target_class: str = "human",
                     attempts: int = 20) -> dict:
        self.track_set({"enabled": True})
        snapshot = self.service.snapshot(write=False)
        response = self._call("target.select", {"class": target_class, "selection": selection,
                                                "observation_id": snapshot["observation_id"]})
        if not response.get("ok"):
            raise RuntimeError(response.get("error", "track enter rejected"))
        mode = None
        for _ in range(attempts):
            mode = self._read_ai_mode()
            if mode == 2:
                break
            time.sleep(0.3)
        return {"selection": selection, "class": target_class, "ai_main_mode": mode,
                "entered": mode == 2, "reobserve_required": True}

    def track_enter(self, args: dict) -> dict:
        self._require_control()
        selection = args.get("selection", "center")
        if selection not in ("center", "largest"):
            raise ValueError("track.enter selection must be center or largest")
        target_class = args.get("class", "human")
        if target_class not in TARGET_CLASSES:
            raise ValueError("unsupported target class")
        return self._enter_track(selection, target_class)

    def _observe_target(self, attempts: int = 10):
        for _ in range(attempts):
            snapshot = self.service.snapshot(write=False)
            candidates = snapshot.get("candidates", [])
            if candidates:
                candidate = max(candidates, key=lambda c: (c["bbox"][2] - c["bbox"][0]) * (c["bbox"][3] - c["bbox"][1]))
                return candidate, snapshot
            time.sleep(0.5)
        return None, None

    def calibration_geometry(self, args: dict) -> dict:
        observation_id = args.get("observation_id")
        if not observation_id:
            raise ValueError("observation_id required; take a snapshot at the known position first")
        record = self.observations.validate(
            observation_id, stream_session=self.service.stream_session,
            camera_epoch=self.service.camera_epoch, now_mono=self.clock(),
            max_age_s=self.service.max_frame_age_s, calibration_id=self.calibration.calibration_id)
        candidate_id = args.get("candidate_id")
        if candidate_id:
            candidate = record.candidate(candidate_id)
            x = (candidate.bbox[0] + candidate.bbox[2]) / 2
            y = (candidate.bbox[1] + candidate.bbox[3]) / 2
        else:
            x, y = float(args["x"]), float(args["y"])
        return self.calibration.add_geometry_sample(args["position"], observation_id, x, y)

    def calibration_validate(self, args: dict) -> dict:
        self._require_control()
        position = args["position"]
        self._require_calibration_verified(require=False)
        mode = self._read_ai_mode()
        entered = None
        if mode != 2:
            entered = self._enter_track(args.get("enter", "center"))
            mode = entered["ai_main_mode"]
        if mode != 2:
            raise RuntimeError("could not enter Track runtime (ai_main_mode != 2); place target and retry")
        candidate, snapshot = self._observe_target()
        if not candidate:
            raise RuntimeError("no target observed after entering Track; reobserve and retry")
        bbox = tuple(candidate["bbox"])
        roi = self.calibration.profile().to_sdk(Box(*bbox), require_verified=False)
        payload = {"class": candidate.get("class", "human"), "selection": "box",
                   "observation_id": snapshot["observation_id"], **roi}
        response = self._call("target.select", payload)
        if not response.get("ok"):
            raise RuntimeError(response.get("error", "box rejected"))
        cx0 = (bbox[0] + bbox[2]) / 2
        cy0 = (bbox[1] + bbox[3]) / 2
        samples = []
        end = self.clock() + float(args.get("settle_s", 3.0))
        while self.clock() < end:
            time.sleep(0.5)
            follow, _ = self._observe_target(attempts=1)
            samples.append({"cx": round((follow["bbox"][0] + follow["bbox"][2]) / 2, 3),
                            "cy": round((follow["bbox"][1] + follow["bbox"][3]) / 2, 3)} if follow else None)
        return {"position": position, "observation_id": snapshot["observation_id"], "uvc_bbox": list(bbox),
                "sdk_roi": roi, "entered_track": entered, "ai_main_mode": mode,
                "cx_before": round(cx0, 3), "cy_before": round(cy0, 3), "samples": samples,
                "note": "record the SDK selection outcome via calibration.outcome after visual check"}

    def calibration_outcome(self, args: dict) -> dict:
        position = args["position"]
        observation_id = args.get("observation_id")
        uvc_bbox = args.get("uvc_bbox")
        sdk_roi = args.get("sdk_roi")
        if not observation_id or not uvc_bbox or not sdk_roi:
            raise ValueError("observation_id, uvc_bbox and sdk_roi are required")
        return self.calibration.record_outcome(position, observation_id, uvc_bbox, sdk_roi,
                                               bool(args.get("selected")), args.get("note", ""))

    def _require_calibration_verified(self, *, require: bool = True) -> None:
        if require and not self.calibration.profile().verified:
            raise ValueError("calibration is not verified")

    def target_select(self, args: dict) -> dict:
        self._require_control()
        self._sync_epoch()
        observation_id = args.get("observation_id")
        if not observation_id:
            raise ReobserveRequired("observation_id required; observe a frame before selecting")
        record = self.observations.validate(
            observation_id, stream_session=self.service.stream_session,
            camera_epoch=self.service.camera_epoch, now_mono=self.clock(),
            max_age_s=self.service.max_frame_age_s, calibration_id=self.calibration.calibration_id)
        selection = args.get("selection", "box")
        target_class = args.get("class", "human")
        if target_class not in TARGET_CLASSES:
            raise ValueError("unsupported target class")
        payload = {"class": target_class, "selection": selection}
        candidate_id = args.get("candidate_id")
        if selection == "box":
            if candidate_id:
                candidate = record.candidate(candidate_id)
                bbox = candidate.bbox
                target_class = candidate.category
                payload["class"] = target_class
            else:
                for key in ("x1", "y1", "x2", "y2"):
                    if key not in args:
                        raise ValueError(f"missing {key} or candidate_id")
                bbox = (float(args["x1"]), float(args["y1"]), float(args["x2"]), float(args["y2"]))
            box = Box(*bbox)
            roi = self.calibration.profile().to_sdk(box)
            payload.update(roi)
            self.requested_roi = list(bbox)
            self.requested_roi_sdk = [roi["x1"], roi["y1"], roi["x2"], roi["y2"]]
            self.selected = {"observation_id": observation_id, "candidate_id": candidate_id,
                             "class": target_class, "roi": roi, "frame_seq": record.frame_seq}
        elif selection == "clicked":
            payload["x"] = float(args["x"])
            payload["y"] = float(args["y"])
        if selection == "box":
            mode = self._read_ai_mode()
            if mode != 2:
                raise RuntimeError("device is not in Track runtime; call track.enter (center/largest), "
                                   "wait for ai_main_mode=2, REOBSERVE, then Box on the new frame")
        response = self._call("target.select", payload)
        if not response.get("ok"):
            raise RuntimeError(response.get("error", "target.select rejected"))
        self.framing["visual_check"] = None
        return {"dispatch": "accepted", "selection": selection, "observation_id": observation_id,
                "frame_seq": record.frame_seq, "requested_roi": self.requested_roi,
                "requested_roi_sdk": self.requested_roi_sdk, "calibration": self.calibration.profile().describe(),
                "sdk": response,
                "side_effects": "UNVERIFIED: check whether tracking/zoom changed; SDK rc=0 is not visual proof"}

    def target_clear(self) -> dict:
        self._require_control()
        response = self._call("target.clear")
        if not response.get("ok"):
            raise RuntimeError(response.get("error", "target.clear rejected"))
        self.requested_roi = None
        self.requested_roi_sdk = None
        self.selected = None
        return {"dispatch": "accepted", "sdk": response}

    def track_set(self, args: dict) -> dict:
        self._require_control()
        enabled = bool(args.get("enabled"))
        response = self._call("track.set", {"enabled": enabled})
        self.track["requested"] = enabled
        self.track["sdk_reported"] = response.get("result") if response.get("ok") else {"error": response.get("error")}
        return {"dispatch": "accepted" if response.get("ok") else "rejected", "sdk": response}

    def track_mode(self, args: dict) -> dict:
        self._require_control()
        self._require_legacy()
        mode = int(args.get("mode", 1))
        enabled = bool(args.get("enabled", True))
        response = self._call("ai.track_mode", {"mode": mode, "enabled": enabled})
        self.track["requested"] = {"mode": mode, "enabled": enabled}
        self.track["sdk_reported"] = response.get("result") if response.get("ok") else {"error": response.get("error")}
        return {"dispatch": "accepted" if response.get("ok") else "rejected", "sdk": response}

    def framing_set(self, args: dict) -> dict:
        self._require_control()
        mode = args.get("mode")
        if mode not in FRAMING_MODES:
            raise ValueError("unsupported framing mode")
        response = self._call("framing.set", {"mode": mode})
        self.framing["requested"] = mode
        self.framing["sdk_reported"] = response.get("result") if response.get("ok") else {"error": response.get("error")}
        self.framing["visual_check"] = None
        return {"dispatch": "accepted" if response.get("ok") else "rejected", "requested": mode,
                "sdk": response, "note": "SDK acceptance is not visual composition"}

    def look(self, op: str, args: dict) -> dict:
        self._require_control()
        self._require_legacy()
        response = self._call(op, args)
        if op == "look.status":
            result = response.get("result") if response.get("ok") else None
            if result:
                self.gimbal.update({"roll_deg": result.get("roll_deg"), "pitch_deg": result.get("pitch_deg"),
                                    "yaw_deg": result.get("yaw_deg")}, self.clock())
            else:
                self.gimbal.fail(response.get("error", "look.status failed"))
        return response

    def status(self) -> dict:
        self._sync_epoch()
        with self._lock:
            return {"service": self.service.status(), "calibration": self.calibration.profile().describe(),
                    "requested_roi": self.requested_roi, "requested_roi_sdk": self.requested_roi_sdk,
                    "selected": self.selected, "track": self.track, "framing": self.framing,
                    "ai": self.ai_status, "gimbal": self.gimbal.read(self.clock()),
                    "conflicts": self.conflicts}

    def overlay(self) -> dict:
        service = self.service.status()
        with self._lock:
            return {"frame": {"width": service["width"], "height": service["height"],
                              "seq": service["frames"], "age_s": service["last_frame_age_s"]},
                    "candidates": self.service.candidates(), "requested_roi": self.requested_roi,
                    "requested_roi_sdk": self.requested_roi_sdk, "calibration": self.calibration.profile().describe(),
                    "gimbal": self.gimbal.read(self.clock()), "track": self.track,
                    "framing": self.framing, "ai": self.ai_status, "service": service,
                    "conflicts": self.conflicts,
                    "notes": ["requested_roi is not a native device tracking box"]}

    def handle(self, request: dict, *, timeout: float | None = None) -> dict:
        with self._handle_lock:
            self._call_timeout = timeout
            try:
                return self._dispatch(request)
            finally:
                self._call_timeout = None

    def _dispatch(self, request: dict) -> dict:
        op = request.get("op")
        args = request.get("args") or {}
        if op == "snapshot":
            return self.snapshot(args)
        if op == "candidates":
            return {"provider": "host_detector", "candidates": self.service.candidates()}
        if op == "calibration.profile":
            return self.calibration_profile(args)
        if op == "calibration.sample":
            return self.calibration_geometry(args)
        if op == "calibration.validate":
            return self.calibration_validate(args)
        if op == "calibration.outcome":
            return self.calibration_outcome(args)
        if op == "calibration.verify":
            return self.calibration.verify().describe()
        if op == "calibration.get":
            return self.calibration.profile().describe()
        if op == "track.enter":
            return self.track_enter(args)
        if op == "status":
            return self.status()
        if op == "device.status":
            response = self._call("device.status")
            if not response.get("ok"):
                raise RuntimeError(response.get("error", "device.status failed"))
            self._record_ai(response["result"])
            return response["result"]
        if op == "target.select":
            return self.target_select(args)
        if op == "target.clear":
            return self.target_clear()
        if op == "track.set":
            return self.track_set(args)
        if op == "track.mode":
            return self.track_mode(args)
        if op == "framing.set":
            return self.framing_set(args)
        if op in ("look.stop", "look.nudge", "look.status"):
            return self.look(op, args)
        if op == "capture.photo":
            return self.service.capture_photo(timeout=float(args.get("timeout", 2.0)))
        if op == "record.start":
            return self.service.record_start(fps=float(args.get("fps", 30.0)))
        if op == "record.stop":
            return self.service.record_stop()
        if op == "position.list":
            self._require_legacy()
            response = self._call("position.list")
            if not response.get("ok"):
                raise RuntimeError(response.get("error", "position.list failed"))
            return response.get("result", {})
        if op == "position.recall":
            self._require_control()
            self._require_legacy()
            if "id" not in args:
                raise ValueError("id required")
            response = self._call("position.recall", {"id": int(args["id"])})
            if not response.get("ok"):
                raise RuntimeError(response.get("error", "position.recall failed"))
            return response.get("result", {})
        if op in ("ai.select_biggest", "ai.select_central"):
            self._require_control()
            self._require_legacy()
            response = self._call(op, {"type": int(args.get("type", 0))})
            return {"dispatch": "accepted" if response.get("ok") else "rejected", "sdk": response}
        if op in ("zoom.set", "zoom.get", "zoom.range", "ai.auto_zoom"):
            self._require_control()
            if op in ("zoom.set", "ai.auto_zoom"):
                self._require_legacy()
            response = self._call(op, args)
            if not response.get("ok"):
                raise RuntimeError(response.get("error", f"{op} rejected"))
            return response.get("result", {})
        if op == "ai.control.get":
            self._require_control()
            self._require_legacy()
            response = self._call(op, args)
            if not response.get("ok"):
                raise RuntimeError(response.get("error", "ai.control.get rejected"))
            return response.get("result", {})
        if op == "ai.control.set":
            self._require_control()
            self._require_legacy()
            if not self.allow_control_writes:
                raise RuntimeError("ai.control.set disabled by default; restart with --allow-control-writes")
            response = self._call(op, args)
            if not response.get("ok"):
                raise RuntimeError(response.get("error", "ai.control.set rejected"))
            return response.get("result", {})
        if op in ("camera.face_ae", "camera.exposure_mode", "camera.ev_bias", "ai.offset", "ai.offset.get"):
            self._require_control()
            self._require_legacy()
            response = self._call(op, args)
            if not response.get("ok"):
                raise RuntimeError(response.get("error", f"{op} rejected"))
            return response.get("result", {})
        raise ValueError("unsupported observer op")


def _gimbal_poll(observer: "Observer", stop_event: threading.Event, interval: float) -> None:
    while not stop_event.is_set():
        try:
            observer.look("look.status", {})
        except Exception:
            pass
        try:
            response = observer._call("device.status")
            if response.get("ok"):
                observer._record_ai(response["result"])
        except Exception:
            pass
        stop_event.wait(interval)


def _emit(result: dict) -> None:
    print(json.dumps(result, ensure_ascii=False), flush=True)


def _execute(observer: "Observer", request: dict) -> dict:
    try:
        return {"ok": True, "op": request.get("op"), "result": observer.handle(request)}
    except ReobserveRequired as exc:
        return {"ok": False, "op": request.get("op"), "error": str(exc), "code": "REOBSERVE_REQUIRED"}
    except Exception as exc:
        return {"ok": False, "op": request.get("op"), "error": str(exc)}


def _stdin_loop(observer: "Observer") -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
        except ValueError as exc:
            _emit({"ok": False, "error": str(exc)})
            continue
        _emit(_execute(observer, request))
        if request.get("op") == "shutdown":
            return


def _command_file_loop(observer: "Observer", path: Path, stop_event: threading.Event) -> None:
    response_path = Path(str(path) + ".responses.jsonl")
    processed = 0
    while not stop_event.is_set():
        if path.exists():
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            while processed < len(lines):
                line = lines[processed].strip()
                processed += 1
                if not line:
                    continue
                try:
                    request = json.loads(line)
                except ValueError as exc:
                    record = {"ok": False, "error": str(exc)}
                    request = {}
                else:
                    record = _execute(observer, request)
                with response_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                if request.get("op") == "shutdown":
                    return
        stop_event.wait(0.3)


def run_observer(args) -> int:
    conflicts = detect_uvc_conflicts()
    if conflicts:
        print("UVC conflict warning (close these before capture): " + ", ".join(conflicts), file=sys.stderr)
    stop_event = threading.Event()
    with Trace(args.trace) as trace:
        detector = hog_detector if args.detect else None
        if getattr(args, "detect_face", False):
            detector = face_detector
        source = UvcFrameSource(args.index, args.backend, args.width, args.height,
                                device_name=getattr(args, "device_name", None))
        service = ObservationService(source, args.out, detector=detector, preview_width=args.preview_width)
        service.start()
        command = [str(args.bridge.resolve())]
        if args.allow_control:
            command.append("--allow-control")
        if args.allow_legacy_probes:
            command.append("--allow-legacy-probes")
        with Bridge(command, trace) as bridge:
            serial = args.serial or os.environ.get("TAIL2_DEVICE_SN")
            if serial:
                device = discover_tail2(bridge.request, timeout=args.discover_timeout,
                                        per_call_wait_ms=args.per_call_wait_ms)
                serial = device.get("sn") or serial
                opened = bridge.request("device.open", {"sn": serial})
                if not opened.get("ok"):
                    raise RuntimeError(opened.get("error", "device.open failed"))
            calibration = CalibrationStore(Path(args.out) / "calibration")
            observer = Observer(service, bridge, trace, calibration=calibration, control=args.allow_control,
                                legacy=args.allow_legacy_probes, conflicts=conflicts,
                                allow_control_writes=getattr(args, "allow_control_writes", False))
            server = StatusServer(args.trace, args.port, preview=service.preview_jpeg, overlay=observer.overlay)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            print(f"Observation Service ready. Read-only page: http://127.0.0.1:{server.server_port}", file=sys.stderr)
            if getattr(args, "gimbal_poll_s", 0) and args.allow_control and args.allow_legacy_probes:
                threading.Thread(target=_gimbal_poll, args=(observer, stop_event, args.gimbal_poll_s),
                                 daemon=True).start()
            try:
                if args.command_file:
                    _command_file_loop(observer, Path(args.command_file), stop_event)
                else:
                    _stdin_loop(observer)
            finally:
                stop_event.set()
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                service.stop()
    return 0
