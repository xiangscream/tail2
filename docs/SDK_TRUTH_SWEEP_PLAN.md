# Tail2 SDK Truth Sweep Plan

2026-09-21

## 0. Why this phase exists

M0/M0.5/M1A/M1B have already proven the main Observation → Target → Track runtime chain, but the Tail2 SDK surface is still only partially characterized. Before freezing the Embodied Capability / Primitive Layer, the project will do one complete SDK resource census and a controlled truth sweep.

The goal is **not** to wrap every SDK function as a capability. The goal is to know what Tail2 can actually do, what it cannot do, what is unsafe or unavailable, and which combinations have product value.

Until this sweep closes, M1C/M1D primitive expansion is paused.

Authorized SDK baseline:

- package: `libdev_v2.1.0_8`
- `include/dev/dev.hpp` SHA256: `d6f12cd9ab50c696b5a2cf9224dda3fc72245e17408bf52dd98d631cb7f74f2d`
- proprietary SDK files, binaries, raw private logs and device serials remain local and are never committed.

## 1. Definition of done

The sweep is complete when every public SDK capability family has an explicit disposition for Tail2:

- `VERIFIED`: physical / visual / state behavior reproduced on Tail2.
- `READBACK_VERIFIED`: getter / status path is proven, but no write behavior is implied.
- `ACCEPTED_UNPROVEN`: SDK accepted the request, but physical / visual result is not proven.
- `CONSTRAINED`: works only under documented runtime conditions.
- `UNSUPPORTED_TAIL2`: declared elsewhere but not usable on Tail2.
- `NO_PUBLIC_PATH`: enum / hint exists, but no complete public API contract exists.
- `DEFERRED_UNSAFE`: relevant but destructive or unsafe to exercise automatically.
- `NOT_PRODUCT_RELEVANT`: present in SDK but not relevant to the Agent Camera / Tail2 MVP.

No high-value Tail2 family may remain as a bare `[U]` without a reason.

## 2. Phase 0: complete static SDK census

Before new device writes, inventory the **entire authorized SDK resource**, not only the APIs already known from `dev.hpp`.

Inspect:

- public headers such as `dev.hpp`, `devs.hpp`, `comm.hpp` and related included public headers;
- enums, structs, callbacks and event payload declarations;
- shipped examples / docs if present in the package;
- current probes in `native/main.cpp`;
- current project truth docs.

Produce a sanitized census. Do not copy proprietary header bodies or large comments into the repo. Recording symbol names, signatures at a high level, product applicability, enum names, ranges and our own observations is acceptable.

For every relevant public API/symbol, capture:

| Field | Meaning |
|---|---|
| capability_family | Observation / Target / Track / Framing / Gimbal / Media / IQ / Gesture / Status / Device / Preset / etc. |
| sdk_symbol | API / enum / callback name |
| tail2_applicability | explicit / generic / other-product / unknown |
| kind | getter / setter / command / callback / enum / data |
| risk | read_only / reversible_write / stateful_config / destructive |
| current_truth | one of the statuses above |
| evidence | static / readback / physical / visual / artifact |
| prerequisites | mode, AI state, UVC state, storage, etc. |
| restore_path | how the experiment returns the device to baseline |
| primitive_value | high / medium / low / none |
| notes | side effects, ambiguity, missing payload, timing |

Recommended implementation:

- add or extend a **local-only** scanner such as `tools/sdk_census.py` that reads the private SDK path supplied at runtime;
- raw scanner output goes to `.local/sdk-sweep/`;
- commit only sanitized summaries.

## 3. Experiment protocol

Every write experiment follows the same protocol:

```text
PRE-STATE
  ↓
read original values / capture Observation
  ↓
ONE controlled write
  ↓
SDK return
  ↓
readback
  ↓
physical / visual / artifact evidence
  ↓
side-effect inspection
  ↓
restore original state
  ↓
POST-STATE
```

Rules:

1. One variable at a time. No broad blind parameter scan.
2. Use documented enum/range/type only. Never invent arbitrary numeric values.
3. Read original state before a reversible write whenever a getter exists.
4. Restore after every experiment and verify restoration.
5. A setter returning `rc=0` is never sufficient for `VERIFIED`.
6. Important behavior should be reproduced at least twice; architecture-changing behavior should be reproduced three times when practical.
7. If a write causes an abnormal LED / stuck state / loss of control, stop the wave, recover the device, document the transition and do not continue mixing writes.
8. Do not kill OBSBOT Center automatically. Detect conflicts and ask the operator to close it.
9. Real images, video, serials and verbose raw SDK logs remain under `.local/`.
10. Destructive operations are not exercised merely for completeness.

## 4. Wave A: architecture-changing camera/body controls

These are highest priority because they can materially change the later Primitive Layer design.

### A1. Native Tail2 Gimbal / Look

Explore and classify:

- `aiSetGimbalMotorAngleR`
- `aiSetGimbalSpeedCtrlR`
- `aiSetGimbalStop`
- `aiSetGimbalBootPosR / aiGetGimbalBootPosR / aiTrgGimbalBootPosR / aiRstGimbalBootPosR`
- `aiSetGimbalParaR / aiGetGimbalParaR`
- `aiSetGimbalYawDirReverseR`
- existing legacy `gimbalSpeedCtrlR / gimbalGetAttitudeInfoR` as comparison baseline.

Questions:

- Is there a reliable absolute-look path?
- Units, sign, range and axis order?
- Does an absolute command preserve / suspend AI tracking?
- Is native stop more reliable than legacy zero-speed?
- Can angle / speed / limits be read back?
- What is the recovery path after manual control?

### A2. Tail2 AI Control 0–23

The current Normal-vs-Track dump proved that these values do not encode Track state, but most write semantics remain unknown.

Systematically characterize, with documented types/ranges only:

- Motion / ForeTrack
- Composition
- TrackerType
- GimCtrlMode / GimCtrlSpeedMode
- PanGainAdaptive / PanGainValue
- PanLocked
- PitchGainAdaptive / PitchGainValue
- PitchLocked
- AutoZoomCustomized / AutoZoomMode
- OffsetAdaptiveX / OffsetX
- OffsetAdaptiveY / OffsetY
- LimitAutoSelection
- LimitPan/Pitch Min/Max
- AutoZoomSpeed

Do not re-run known-negative Offset experiments blindly. Instead test whether they require a specific precondition such as Track submode, AutoZoom, Composition, target class or Pro control mode.

### A3. Target View / Target Zoom

Explore all Tail2-relevant values of:

- `aiSetTargetViewTypeR`
- `aiSetTargetZoomTypeR`
- `DevTargetViewType`
- `DevTargetZoomType`

Separate:

- request accepted;
- AI submode readback;
- zoom readback;
- visible scale/composition change;
- target-selection side effects.

### A4. Zoom family

Explore:

- absolute zoom (existing verified baseline);
- relative zoom with speed;
- zoom stop;
- auto zoom enable/disable;
- any documented digital-zoom control path;
- zoom range/readback timing and asynchronous completion.

The output of Wave A must say what future `Look` and `Framing` are physically capable of. Do **not** package new primitives yet.

## 5. Wave B: Agent-native interaction and device platform capabilities

### B1. Gesture / Gesture Tracking

Inventory and test safe reversible settings:

- gesture enable;
- target selection gesture;
- zoom / snapshot / rolling / mirror gestures;
- gesture tracking Pan/Pitch ranges;
- hand type;
- track speed;
- Pan/Pitch enabled;
- rest time.

Main question: how do gesture controls interact with Agent ownership, Track state and manual Look?

### B2. Focus / IQ

Explore Tail2-supported:

- autofocus mode;
- AFC Track mode;
- focus absolute/readback;
- white balance getter/setter;
- relevant config ranges.

Main question: can the later camera primitive express focus/clarity intent, or should IQ remain an adapter-local policy?

### B3. Preset / Boot Position / Gimbal configuration

Read paths first:

- preset list/info/name;
- recall where a valid ID exists;
- preset speed;
- boot position read/trigger.

State-changing add/update/delete operations require explicit read-before/restore planning. Do not delete user presets.

### B4. Device lifecycle / state / callback surface

Explore:

- `nextRefreshDevStatus / fastNextRefreshDevStatus`;
- `cameraStatus()` with safe typed parsing;
- `DevStatusCallback / FastDevStatusCallback`;
- `Devices::setDevChangedCallback`;
- event-notify callbacks only where Tail2 applicability is supported;
- online / USB / storage / media / battery or other Tail2-relevant status fields.

Goal: determine whether polling can later be replaced by event-driven state for any capability.

## 6. Wave C: media and output surface

Keep host UVC as the MVP default. This wave is about truth, not changing the product decision.

Explore safely:

- Tail2 record/output/live encode getters and setters;
- stream IDs and mode prerequisites;
- media state readback;
- UVC vs Record / Live / RTSP / NDI / SRT behavior;
- capture/record behavior with storage available only if the operator has a safe test medium;
- media event notification if a documented Tail2 path exists.

Do not infer file availability from `rc=0`. Artifact existence and accessibility are separate evidence.

Do not change persistent output configuration without a restore plan.

## 7. Wave D: closure / unsupported / deferred

At the end, explicitly classify:

- APIs documented for Tail Air / Tiny / Meet but not Tail2;
- native candidate / target notification paths with incomplete public payload contracts;
- tracking-box / identity readback absence;
- file download paths not documented for Tail2;
- destructive operations that were intentionally not run;
- capabilities with no product relevance.

This is part of completion. “Not tested because unsafe / not applicable” is a valid truth state; silent omission is not.

## 8. Deliverables

By the end of the full sweep:

1. `docs/Tail2_SDK_TRUTH_MAP.md`  
   The authoritative sanitized capability truth map.
2. `docs/Tail2_SDK_EXPERIMENT_MATRIX.md`  
   Experiment IDs, preconditions, evidence, restore results and verdicts.
3. Update `docs/Tail2_CAPABILITY_MAP.md` so stale `[U]/[A]` claims are removed or justified.
4. Update `docs/SDK_FINDINGS.md` to current M1-era truth.
5. Per-wave handoff reports under `docs/handoff/inbox/`.
6. Tests for every new probe parser/allowlist/state contract.
7. Public-check remains clean; private SDK and raw evidence stay local.

## 9. Git workflow

Use normal mainline Git:

```text
main
  ↓
feature/sdk-sweep-a
  ↓
PR + CI + review
  ↓
main
  ↓
feature/sdk-sweep-b
  ↓
...
```

Do not create another long-lived stage integration branch.

Each wave starts from the exact current `main` HEAD and returns directly to `main`.

## 10. Primitive-layer freeze gate

Do **not** begin the Pro-level Primitive Layer freeze until:

- Phase 0 census covers the full SDK resource;
- Wave A is fully closed;
- Wave B is closed for all high/medium primitive-value capabilities;
- Wave C has a clear truth state even where host_uvc remains preferred;
- Wave D explicitly records unsupported/deferred gaps;
- there are no architecture-significant APIs left as unexplained `[U]`.

Only then do we ask:

> Given the complete Tail2 physical capability boundary, which semantics become stable Primitives, which become Solvers, which remain Adapter policy, which are Agent orchestration, and which slots should later be replaceable by a learned Photographer Policy?
