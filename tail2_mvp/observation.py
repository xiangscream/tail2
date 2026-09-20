"""Single-shot UVC probe. No cloud upload, SDK selection, or image auto-publication."""
import hashlib
import json
import multiprocessing as mp
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _capture_worker(config: dict, out: str, pipe) -> None:
    cap = None
    try:
        import cv2
        backends = {"dshow": cv2.CAP_DSHOW, "msmf": cv2.CAP_MSMF,
                    "v4l2": cv2.CAP_V4L2, "any": cv2.CAP_ANY}
        cap = cv2.VideoCapture(config["index"], backends[config["backend"]])
        if not cap.isOpened():
            raise RuntimeError("camera did not open; verify explicit device index and backend")
        frame = None
        for _ in range(5):
            ok, frame = cap.read()
            if not ok or frame is None or not frame.size:
                raise RuntimeError("camera returned no usable frame")
        received = time.monotonic()
        height, width = frame.shape[:2]
        directory = Path(out)
        image = directory / "frame.jpg"
        if not cv2.imwrite(str(image), frame):
            raise RuntimeError("cannot write observation image")
        candidates = []
        if config["human_candidates"]:
            # Bench baseline only. HOG margin is NOT calibrated probability.
            scale = min(1.0, 960 / width)
            small = cv2.resize(frame, (max(1, round(width * scale)), max(1, round(height * scale))))
            hog = cv2.HOGDescriptor()
            hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
            if small.shape[0] >= 128 and small.shape[1] >= 64:
                boxes, weights = hog.detectMultiScale(small, winStride=(8, 8), padding=(8, 8), scale=1.05)
                h, w = small.shape[:2]
                for i, ((x, y, bw, bh), weight) in enumerate(zip(boxes, weights)):
                    bbox = [max(0.0, x/w), max(0.0, y/h), min(1.0, (x+bw)/w), min(1.0, (y+bh)/h)]
                    if bbox[0] < bbox[2] and bbox[1] < bbox[3]:
                        candidates.append({"candidate_id": f"human-{i+1}", "class": "human",
                            "bbox": bbox, "provider": "opencv_hog_bench", "detector_margin": float(weight)})
        result = {"observation_id": directory.name, "stream_session": config["stream_session"],
                  "camera_epoch": 0, "frame_file": "frame.jpg", "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                  "width": width, "height": height, "received_mono": received,
                  "host_time_utc": datetime.now(timezone.utc).isoformat(), "sensor_timestamp": None,
                  "uvc_index": config["index"], "backend": cap.getBackendName(),
                  "device_binding": "UNVERIFIED", "sdk_mapping": "UNVERIFIED",
                  "transform": {"host_mirrored": False, "host_rotation": 0, "host_crop": None},
                  "candidates": candidates,
                  "note": "Host receipt time is not sensor exposure time; candidate IDs are observation-local."}
        temp = directory / "observation.tmp"
        temp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, directory / "observation.json")
        pipe.send({"ok": True, "manifest": str(directory / "observation.json")})
    except Exception as exc:
        pipe.send({"ok": False, "error": str(exc)})
    finally:
        if cap is not None:
            cap.release()
        pipe.close()


def capture_snapshot(index: int, backend: str, directory: Path, *, human_candidates: bool = False,
                     timeout: float = 20) -> Path:
    if isinstance(index, bool) or not isinstance(index, int) or index < 0:
        raise ValueError("explicit nonnegative camera index required")
    if backend not in {"dshow", "msmf", "v4l2", "any"} or not 0 < timeout <= 60:
        raise ValueError("invalid capture settings")
    target = directory.resolve() / uuid.uuid4().hex
    target.mkdir(parents=True, exist_ok=False)
    context = mp.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    config = {"index": index, "backend": backend, "human_candidates": human_candidates,
              "stream_session": uuid.uuid4().hex}
    process = context.Process(target=_capture_worker, args=(config, str(target), child), daemon=True)
    process.start(); child.close()
    try:
        if not parent.poll(timeout):
            raise TimeoutError("UVC probe timed out; no observation confirmed")
        try:
            result = parent.recv()
        except EOFError as exc:
            raise RuntimeError("UVC worker exited without a result") from exc
        if not result.get("ok"):
            raise RuntimeError(result.get("error", "capture failed"))
        return Path(result["manifest"])
    finally:
        process.join(timeout=1)
        if process.is_alive():
            process.terminate(); process.join(timeout=2)
        if process.is_alive():
            process.kill(); process.join(timeout=2)
        parent.close()
