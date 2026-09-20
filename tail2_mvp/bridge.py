"""Single-flight supervised JSONL client. A timeout is not a physical stop."""
import json
import math
import subprocess
import threading
import uuid
from pathlib import Path
from queue import Queue, Empty, Full
from typing import Sequence

from .events import Trace


class BridgeError(RuntimeError):
    pass


class Bridge:
    def __init__(self, command: Sequence[str], trace: Trace):
        if not command:
            raise ValueError("explicit executable required")
        self.trace = trace
        self.queue: Queue = Queue(maxsize=128)
        self.lock = threading.Lock()
        self.dead = False
        self.seen: set[str] = set()
        self.err = (trace.directory / "native-stderr.log").open("ab")
        try:
            self.proc = subprocess.Popen(list(command), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=self.err, text=True, encoding="utf-8", errors="strict",
                                         bufsize=1, shell=False)
        except Exception:
            self.err.close()
            raise
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _put(self, item) -> bool:
        try:
            self.queue.put(item, timeout=0.5)
            return True
        except Full:
            return False

    def _read(self) -> None:
        try:
            while True:
                line = self.proc.stdout.readline(1024 * 1024 + 1)
                if not line:
                    self._put(BridgeError("bridge exited")); return
                if len(line) > 1024 * 1024 or not line.endswith("\n"):
                    self._put(BridgeError("invalid protocol line size")); return
                try:
                    response = json.loads(line)
                except ValueError:
                    self._put(BridgeError("non-JSON stdout from native bridge")); return
                if not isinstance(response, dict) or not isinstance(response.get("id"), str):
                    self._put(BridgeError("invalid response schema")); return
                if not self._put(response):
                    return
        except (OSError, UnicodeError, ValueError) as exc:
            self._put(BridgeError(str(exc)))

    def request(self, op: str, args: dict | None = None, *, timeout: float = 20,
                request_id: str | None = None) -> dict:
        if not isinstance(op, str) or not op or not math.isfinite(timeout) or not 0 < timeout <= 60:
            raise ValueError("invalid request")
        if args is not None and not isinstance(args, dict):
            raise ValueError("args must be an object")
        with self.lock:
            if self.dead:
                raise BridgeError("bridge quarantined/closed; verify physical state before reopening")
            rid = request_id or uuid.uuid4().hex
            if not isinstance(rid, str) or not rid or len(rid) > 128 or rid in self.seen:
                raise ValueError("invalid or duplicate request id")
            req = {"id": rid, "op": op, "args": args or {}}
            encoded = json.dumps(req, ensure_ascii=False, allow_nan=False) + "\n"
            if len(encoded.encode("utf-8")) > 65536:
                raise ValueError("request too large")
            self.seen.add(rid)
            self.trace.emit("probe.request", req)
            try:
                self.proc.stdin.write(encoded)
                self.proc.stdin.flush()
                response = self.queue.get(timeout=timeout)
                if isinstance(response, Exception):
                    raise response
                if response["id"] != rid or not isinstance(response.get("ok"), bool):
                    raise BridgeError("response correlation/schema mismatch")
                self.trace.emit("probe.response", response)
                return response
            except (Empty, OSError, UnicodeError, BridgeError) as exc:
                self.trace.emit("probe.transport_error", {"request_id": rid, "op": op,
                    "execution": "indeterminate", "error": str(exc) or "timeout",
                    "physical_stop_confirmed": False})
                self.close()  # Terminate only the process we own, never other applications.
                raise BridgeError("transport failed; action may have occurred; inspect device before retry") from exc

    def close(self) -> None:
        if self.dead:
            return
        self.dead = True
        # Closing is process isolation. It does not send or confirm a device stop.
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill(); self.proc.wait(timeout=2)
        self.reader.join(timeout=1)
        for stream in (self.proc.stdin, self.proc.stdout):
            if stream:
                stream.close()
        self.err.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
