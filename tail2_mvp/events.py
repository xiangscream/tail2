"""Private local event log and atomic read model for a read-only observer."""
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock


class Trace:
    def __init__(self, directory: Path):
        self.directory = directory.resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.directory / "writer.lock"
        try:
            fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise RuntimeError("trace already has a writer; choose a new run directory") from exc
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
        self.run_id = uuid.uuid4().hex
        self.sequence = 0
        self.lock = Lock()
        self.closed = False
        self.state = {"stage": "M0 supervised probe", "agent": "not_connected",
                      "hardware_verified": False, "requested": None,
                      "sdk_reported": None, "visual_check": None, "last_event": None}
        self.emit("run.start", {"stage": "M0", "agent": "not_connected"})

    def emit(self, kind: str, data: dict) -> dict:
        with self.lock:
            if self.closed:
                raise RuntimeError("trace closed")
            self.sequence += 1
            event = {"run_id": self.run_id, "sequence": self.sequence,
                     "time": datetime.now(timezone.utc).isoformat(),
                     "monotonic_ns": time.monotonic_ns(), "kind": kind, "data": data}
            line = json.dumps(event, ensure_ascii=False, allow_nan=False)
            with (self.directory / "events.jsonl").open("a", encoding="utf-8") as f:
                f.write(line + "\n")
            if kind == "probe.request":
                self.state["requested"] = data
                self.state["visual_check"] = None
            if kind == "probe.response":
                self.state["sdk_reported"] = {"response": data, "received_at": event["time"]}
            self.state.update(run_id=self.run_id, last_event=event)
            temp = self.directory / "state.tmp"
            temp.write_text(json.dumps(self.state, ensure_ascii=False, allow_nan=False), encoding="utf-8")
            os.replace(temp, self.directory / "state.json")
            return event

    def close(self) -> None:
        with self.lock:
            if not self.closed:
                self.closed = True
                self.lock_path.unlink(missing_ok=True)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def read_events(directory: Path, limit: int = 200) -> list:
    path = directory / "events.jsonl"
    if not path.exists():
        return []
    # Never load an unbounded private trace into the web process.
    with path.open("rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        start = max(0, size - 1024 * 1024)
        f.seek(start)
        if start:
            f.readline()
        data = f.read(1024 * 1024)
    result = []
    for line in data.splitlines():
        try:
            result.append(json.loads(line))
        except (ValueError, UnicodeError):
            pass  # A concurrently written final line can be incomplete.
    return result[-min(max(limit, 1), 500):]


def read_state(directory: Path) -> dict:
    try:
        path = directory / "state.json"
        if path.stat().st_size > 1024 * 1024:
            return {"error": "state too large"}
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"stage": "M0", "agent": "not_connected", "hardware_verified": False,
                "requested": None, "sdk_reported": None, "visual_check": None}
