"""Minimal M1 runtime assembly.

Wires CapabilityRuntime -> Tail2Adapter -> Observer -> RuntimeSession -> bridge.
Callers only use capability names; the SDK never appears above the adapter.
A session rebuild is hooked to Observer.invalidate so epoch-bound state
(observations, calibration, target/ROI, track/framing) is dropped.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from .adapter import Tail2Adapter
from .calibration import CalibrationStore
from .observer import Observer
from .runtime import CapabilityRequest, CapabilityResult, CapabilityRuntime, ResourceOwnership, StateRegistry
from .session import RuntimeSession


class RuntimeHarness:
    def __init__(self, service, bridge_factory: Callable[[], object], trace, *,
                 calibration_dir: Path | None = None, control: bool = False, legacy: bool = False,
                 conflicts: list[str] | None = None, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep, allow_control_writes: bool = False):
        self.clock = clock
        self.state = StateRegistry(clock=clock)
        self.ownership = ResourceOwnership()
        self.session = RuntimeSession(bridge_factory, state=self.state, ownership=self.ownership)
        calibration = CalibrationStore(calibration_dir) if calibration_dir else None
        self.observer = Observer(service, self.session.bridge, trace, calibration=calibration,
                                 control=control, legacy=legacy, conflicts=conflicts, clock=clock,
                                 allow_control_writes=allow_control_writes, session=self.session)
        self.session.set_rebuild_hook(
            lambda epoch: self.observer.invalidate(f"session rebuild epoch={epoch}"))
        self.runtime = CapabilityRuntime(clock=clock, state=self.state, ownership=self.ownership)
        self.adapter = Tail2Adapter(self.observer, sleep=sleep)
        self.adapter.install(self.runtime)

    def call(self, capability: str, args: dict | None = None, *, observation_id: str | None = None,
             deadline_s: float | None = None, task_id: str = "", caller: str = "script") -> CapabilityResult:
        request = CapabilityRequest(capability=capability, args=args or {},
                                    observation_id=observation_id, deadline_s=deadline_s,
                                    task_id=task_id or "", caller=caller)
        return self.runtime.execute(request)

    def call_dict(self, capability: str, **kwargs) -> dict:
        return self.call(capability, **kwargs).to_dict()


def run_capability(args) -> int:
    import json
    import os
    import sys
    import threading
    from pathlib import Path

    from .bridge import Bridge
    from .events import Trace
    from .observation_service import ObservationService, UvcFrameSource
    from .state import detect_uvc_conflicts, discover_tail2
    from .status import StatusServer

    conflicts = detect_uvc_conflicts()
    if conflicts:
        print("UVC conflict warning (close these before capture): " + ", ".join(conflicts), file=sys.stderr)
    with Trace(args.trace) as trace:
        source = UvcFrameSource(args.index, args.backend, args.width, args.height,
                                device_name=getattr(args, "device_name", None))
        service = ObservationService(source, args.out, detector=None, preview_width=args.preview_width)
        service.start()
        command = [str(args.bridge.resolve())]
        if args.allow_control:
            command.append("--allow-control")
        if args.allow_legacy_probes:
            command.append("--allow-legacy-probes")
        bridge_factory = lambda: Bridge(command, trace)
        harness = RuntimeHarness(service, bridge_factory, trace, calibration_dir=Path(args.out) / "calibration",
                                 control=args.allow_control, legacy=args.allow_legacy_probes, conflicts=conflicts,
                                 allow_control_writes=getattr(args, "allow_control_writes", False))
        serial = args.serial or os.environ.get("TAIL2_DEVICE_SN")
        if serial:
            device = discover_tail2(harness.session.request, timeout=args.discover_timeout,
                                    per_call_wait_ms=args.per_call_wait_ms)
            serial = device.get("sn") or serial
            opened = harness.session.request("device.open", {"sn": serial})
            if not opened.get("ok"):
                raise RuntimeError(opened.get("error", "device.open failed"))
        server = StatusServer(args.trace, args.port, preview=service.preview_jpeg, overlay=harness.observer.overlay)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        print(f"Capability runtime ready. Read-only page: http://127.0.0.1:{server.server_port}", file=sys.stderr)
        print("Commands are JSON lines: {capability, args, observation_id, deadline_s, task_id}.", file=sys.stderr)
        try:
            for line in sys.stdin:
                if not line.strip():
                    continue
                try:
                    request = json.loads(line)
                    if request.get("capability") == "shutdown":
                        print(json.dumps({"execution": "completed", "capability": "shutdown"}, ensure_ascii=False),
                              flush=True)
                        break
                    result = harness.call(request["capability"], request.get("args"),
                                          observation_id=request.get("observation_id"),
                                          deadline_s=request.get("deadline_s"),
                                          task_id=request.get("task_id", ""),
                                          caller=request.get("caller", "script"))
                    print(json.dumps(result.to_dict(), ensure_ascii=False), flush=True)
                except Exception as exc:
                    print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), flush=True)
        finally:
            server.shutdown()
            server.server_close()
            harness.session.close()
            service.stop()
    return 0
