"""CLI for M0 supervised experiments; no model or automatic workflow is attached."""
import argparse
import json
import os
import sys
from pathlib import Path
from .bridge import Bridge, BridgeError
from .events import Trace
from .observation import capture_snapshot
from .observer import run_observer
from .status import serve


def probe(args) -> None:
    executable = args.bridge.resolve(strict=True)
    command = [str(executable)]
    if args.allow_control:
        command.append("--allow-control")
    if args.allow_legacy_probes:
        command.append("--allow-legacy-probes")
    with Trace(args.trace) as trace, Bridge(command, trace) as bridge:
        for op, data in [("hello", {}), ("device.list", {})]:
            print(json.dumps(bridge.request(op, data), ensure_ascii=False), flush=True)
        serial = os.environ.get("TAIL2_DEVICE_SN")
        if serial:
            print(json.dumps(bridge.request("device.open", {"sn": serial}), ensure_ascii=False), flush=True)
        print("M0 supervised probe. Enter JSON {op,args}; EOF exits. No automatic hardware test sequence.", file=sys.stderr)
        print("Before exit, stop tracking/motion and recording explicitly as appropriate. Process exit does not confirm physical stop.", file=sys.stderr)
        for line in sys.stdin:
            if not line.strip():
                continue
            try:
                request = json.loads(line)
                if not isinstance(request, dict) or set(request) - {"op", "args"}:
                    raise ValueError("expected only op and args")
                result = bridge.request(request["op"], request.get("args", {}))
                print(json.dumps(result, ensure_ascii=False), flush=True)
                if request["op"] == "shutdown":
                    break
            except (ValueError, KeyError, TypeError) as exc:
                print(f"Invalid command: {exc}", file=sys.stderr)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    b = sub.add_parser("probe"); b.add_argument("--bridge", type=Path, required=True)
    b.add_argument("--trace", type=Path, required=True)
    b.add_argument("--allow-control", action="store_true")
    b.add_argument("--allow-legacy-probes", action="store_true")
    s = sub.add_parser("snapshot"); s.add_argument("--index", type=int, required=True)
    s.add_argument("--backend", choices=["dshow", "msmf", "v4l2", "any"], required=True)
    s.add_argument("--out", type=Path, default=Path(".local/observations"))
    s.add_argument("--human-candidates", action="store_true"); s.add_argument("--timeout", type=float, default=20)
    w = sub.add_parser("status"); w.add_argument("--trace", type=Path, required=True)
    w.add_argument("--port", type=int, default=0)
    o = sub.add_parser("observe", help="single-owner UVC observation service plus supervised SDK control")
    o.add_argument("--bridge", type=Path, required=True)
    o.add_argument("--trace", type=Path, required=True)
    o.add_argument("--index", type=int)
    o.add_argument("--backend", choices=["dshow", "msmf", "v4l2", "any"], required=True)
    o.add_argument("--device-name")
    o.add_argument("--out", type=Path, default=Path(".local/service"))
    o.add_argument("--serial")
    o.add_argument("--detect", action="store_true")
    o.add_argument("--detect-face", action="store_true")
    o.add_argument("--width", type=int)
    o.add_argument("--height", type=int)
    o.add_argument("--preview-width", type=int, default=640)
    o.add_argument("--port", type=int, default=0)
    o.add_argument("--discover-timeout", type=float, default=15.0)
    o.add_argument("--per-call-wait-ms", type=int, default=1500)
    o.add_argument("--command-file", type=Path)
    o.add_argument("--gimbal-poll-s", type=float, default=0.0)
    o.add_argument("--allow-control", action="store_true")
    o.add_argument("--allow-legacy-probes", action="store_true")
    a = p.parse_args()
    try:
        if a.command == "probe":
            probe(a)
        elif a.command == "snapshot":
            print(capture_snapshot(a.index, a.backend, a.out, human_candidates=a.human_candidates, timeout=a.timeout))
        elif a.command == "observe":
            if not 0 <= a.port <= 65535:
                p.error("port out of range")
            if a.index is None and not a.device_name:
                p.error("provide --index or --device-name")
            return run_observer(a)
        else:
            if not 0 <= a.port <= 65535:
                p.error("port out of range")
            serve(a.trace, a.port)
        return 0
    except (BridgeError, RuntimeError, OSError, ValueError) as exc:
        print(f"M0 stopped: {exc}", file=sys.stderr); return 1
    except KeyboardInterrupt:
        print("Host interrupted. Physical device state is unconfirmed; inspect the device.", file=sys.stderr); return 130


if __name__ == "__main__":
    raise SystemExit(main())
