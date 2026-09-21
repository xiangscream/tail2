# Verification — 2026-09-20

## Executed locally in this development session

Environment: Linux x86_64, GCC 14.2, CMake 3.31.6, Python 3.13.5. Native build used the supplied private libdev Linux library and matching headers.

```sh
cmake -S native -B build -DLIBDEV_ROOT=/path/to/private/libdev_v2.1.0_8
cmake --build build -j2
TAIL2_PROBE="$PWD/build/tail2_probe" python -m unittest discover -s tests -v
```

Result: **29 tests passed**. This includes 23 Python tests and 6 compiled-native protocol tests. The six native tests link the actual SDK but do not operate a Tail2.

Coverage: normalized ROI validation; observation/session/epoch/freshness checks; requested, SDK-reported and visual evidence separation; acknowledgment classification; JSONL request correlation, timeout quarantine and contaminated stdout; read-only HTTP state/events, hostile Host/Origin and write/path rejection; native hello, static UNKNOWN candidates, malformed requests, duplicate IDs, no selected device and shutdown; trace writer exclusion and run separation.

Final repeat: 29 tests passed in 4.374 seconds. `python -m tail2_mvp --help` also ran successfully. The local tested source hashes for native/main.cpp, all Python modules, status.html and both test files were compared with the staged GitHub tree and matched.

The Windows build helper is supplied but has **not** been executed on Windows here. The CI matrix is configured for Windows/Linux and Python 3.11/3.12. CI without the private SDK skips the six native tests; the local result above must not be reported as Windows or hardware validation.

## Host and browser limits

This container has no `/sys/bus/usb/devices`. A compiled `device.list` request was explicitly tested and returned a guarded JSON error before SDK initialization, with no SDK calls. Real USB discovery was not run.

Browser screenshot validation could not run because the Playwright Chromium executable was absent. The HTTP behavior tests passed. No visual browser-QA claim is made.

USB/UVC capture, target selection, tracking, framing, gimbal motion, native media, presets and firmware status have **not** been validated on a real camera here. The snapshot tool is implemented; no real Tail2 image was captured.

## Implementation boundary

- M0 is a supervised raw probe plus testable contract foundations, not the completed M1 capability scheduler.
- No cloud model, credentials, visual Agent loop or application framework is attached.
- `position.save` refuses persistent writes pending preset semantics and ownership.
- Native candidates return UNKNOWN from static inspection; no undocumented notification payload is decoded.
- Successful writes report accepted/unverified. No physical or artifact completion is fabricated.
- A bounded gimbal nudge sends zero after normal SDK return. A blocked SDK call has no independent hardware stop guarantee; an operator must supervise.
- Closing or killing the host process does not confirm the device stopped.
- Host frame receipt time is not sensor exposure time. Coordinate mapping and device binding remain hardware calibration tasks.

## Publication

Only original source, tests and project documentation belong in this repository. SDK, binaries, real images, videos, raw device logs and credentials are excluded. Run `python tools/public_check.py` on tracked/staged files, then review the diff manually; it is a basic guard, not a complete secret scanner.

Hardware results belong in a redacted handoff report with exact commit, environment, steps and observed outcome. Pending entries require that evidence before being changed to passed.
