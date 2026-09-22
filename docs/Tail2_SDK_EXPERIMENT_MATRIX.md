# Tail2 SDK Experiment Matrix (Wave A)

2026-09-21 · branch `feature/sdk-sweep-a` · mirrors `docs/Tail2_SDK_TRUTH_MAP.md`

## Protocol (mandatory, per write)

```text
PRE-STATE
  ↓  read original values / capture Observation
ONE controlled write
  ↓
SDK return (rc)
  ↓
readback (typed getter)
  ↓
physical / visual / artifact evidence
  ↓
side-effect inspection
  ↓
restore original state
  ↓
POST-STATE
```

Rules: one variable at a time · documented enum/range/type only, never invented
numbers · read before write whenever a getter exists · restore and verify ·
`rc=0` is never `VERIFIED` · repeat 2× (3× for architecture-changing results) ·
on abnormal LED / stuck state / loss of control: stop the wave, recover, record
the transition · never auto-kill OBSBOT Center · no destructive APIs · real
images / raw logs / serials stay under `.local/`.

Verdict column is intentionally empty until the device run. All rows start at
`PENDING_WAVE_A`.

## Preconditions for the whole wave

| id | precondition |
|---|---|
| P0 | operator present; device powered; OBSBOT Center **closed** by the operator, not by us |
| P1 | identify the currently free control path (SDK vs device-side tracking); record AI/LED state before each experiment |
| P2 | UVC single owner is held by the observation service; frame capture available for visual evidence |
| P3 | known-good restore primitives verified first: `gimbalSpeedCtrlR(0,0,0)`, `aiSetEnabledR(true)`, `aiStopGimbal` equivalent, `cameraSetZoomAbsoluteR(previous)`, `target.clear` |

## A1 — Native Gimbal / Look

| id | symbol | precondition | one write | readback | physical / visual evidence | side effects to inspect | restore | reps | verdict |
|---|---|---|---|---|---|---|---|---|---|
| A1-E01 | `aiGetGimbalParaR` ×7 | any | none (read) | Pan/Pitch Min/Max, PanReverse, PresetSpeed, RollBias | — | none | — | 3 | |
| A1-E02 | `gimbalGetAttitudeInfoR` | AI off | none (read) | roll/pitch/yaw | compare against frame content | intermittent `rc=-1` rate | — | 3 | |
| A1-E03 | `aiGetGimbalStateR` | AI off | none (read) | typed struct | — | richer than legacy attitude? | — | 2 | |
| A1-E04 | `aiSetGimbalMotorAngleR` | AI off, attitude read | documented single axis, small angle | attitude after settle | frame shift direction/magnitude | LED, AI mode, limit behaviour | command opposite angle / legacy speed back | 3 | |
| A1-E05 | `aiSetGimbalSpeedCtrlR` | AI off | documented speed on one axis | attitude before/after | frame shift vs legacy at same value | does it suspend AI like legacy? | zero speed | 3 | |
| A1-E06 | `aiSetGimbalStop` | gimbal moving from E05 | stop command | attitude settle curve | residual angle | stuck state / LED | zero speed | 3 | |
| A1-E07 | legacy `gimbalSpeedCtrlR` (baseline) | AI off | ±10 dps, ≤500 ms | attitude | known-good reference | residual ≈0.4° | zero speed | 2 | |
| A1-E08 | `aiGetGimbalPresetListR` (read baseline) | any | none | list length | — | still len=0? | — | 2 | |
| A1-E09 | `aiGetGimbalBootPosR` | any | none (read) | boot pose | — | — | — | 2 | |
| A1-E10 | `aiSetGimbalYawDirReverseR` | AI off, attitude read | toggle | readback if available | frame pan direction flips | does it affect Track direction? | toggle back | 2 | |
| A1-E11 | `gimbalSetSpeedPositionR` | AI off | documented position/speed move | attitude | frame change | AI state | legacy return | 2 | |
| A1-E12 | ownership test | **Track active, following** | absolute/speed command | AI mode readback | does tracking resume/stop? frame | LED transition (yellow/purple seen in M1B) | `aiSetEnabledR(true)` + reobserve | 3 | |

## A2 — AI Control 0–23

Shared template: precondition = Track active unless noted; read original with
`aiGetControlParaR`; write one parameter of documented type; read back; capture a
frame before/after; restore original. Ids map 1:1 to `DevControlParaType` index.

| id | # | parameter | precondition / note | verdict |
|---|---|---|---|---|
| A2-E01 | 0 | Motion (bool) | Track | |
| A2-E02 | 1 | ForeTrack (bool) | Track, target then occlusion | |
| A2-E03 | 2 | Composition (bool) | Track; measured via target cx offset | |
| A2-E04 | 3 | TrackerType (Normal/LimitArea) | Track; prerequisite for 19–22 | |
| A2-E05 | 4 | GimCtrlMode (Normal/PRO) | Track; **gate candidate** for offsets/auto-zoom | |
| A2-E06 | 5 | GimCtrlSpeedMode (…/Custom=100) | AI off and on, compare | |
| A2-E07 | 6 | PanGainAdaptive (bool) | Track | |
| A2-E08 | 7 | PanGainValue (float) | Track, documented range | |
| A2-E09 | 8 | PanLocked (bool) | Track, moving target | |
| A2-E10 | 9 | PitchGainAdaptive (bool) | Track | |
| A2-E11 | 10 | PitchGainValue (float) | Track | |
| A2-E12 | 11 | PitchLocked (bool) | Track, moving target | |
| A2-E13 | 12 | AutoZoomCustomized (int) | Track | |
| A2-E14 | 13 | AutoZoomMode (int) | Track | |
| A2-E15 | 14 | OffsetAdaptiveX (bool) | needs a precondition (Composition / AutoZoom / PRO) | |
| A2-E16 | 15 | OffsetX (float) | same; M0.5 negative, do not blind-repeat | |
| A2-E17 | 16 | OffsetAdaptiveY (bool) | same | |
| A2-E18 | 17 | OffsetY (float) | same; M0.5 negative | |
| A2-E19 | 18 | LimitAutoSelection (bool) | TrackerType=LimitArea | |
| A2-E20 | 19 | LimitPanMin (float) | TrackerType=LimitArea | |
| A2-E21 | 20 | LimitPanMax (float) | TrackerType=LimitArea | |
| A2-E22 | 21 | LimitPitchMin (float) | TrackerType=LimitArea | |
| A2-E23 | 22 | LimitPitchMax (float) | TrackerType=LimitArea | |
| A2-E24 | 23 | AutoZoomSpeed (int 1–10) | Track, AutoZoom on | |

## A3 — Target View / Target Zoom

| id | symbol | precondition | one write | readback | visual evidence | side effects | restore | reps | verdict |
|---|---|---|---|---|---|---|---|---|---|
| A3-E01 | `aiSetTargetViewTypeR` | Track, target locked | one documented `DevTargetViewType` value | AI sub mode + zoom | framing change | target re-selection / zoom change | set previous value | 3 | |
| A3-E02 | `aiSetTargetViewTypeR` | same | remaining Tail2-relevant values, one per run | same | same | same | same | 2 each | |
| A3-E03 | `aiSetTargetZoomTypeR` | Track, target locked | one `DevTargetZoomType` (Normal baseline first) | AI sub mode + `cameraGetZoomAbsoluteR` | scale change | zoom side effect | previous type + zoom | 3 | |
| A3-E04 | `aiSetTargetZoomTypeR` | same | `Customized` + `DevCustomizedZoomType` member | same | same | same | same | 2 | |
| A3-E05 | target side-effect probe | Track | re-issue `Box` after A3 writes | requested ROI vs frame | target still locked? | silent no-op check | re-observe + re-box | 2 | |

## A4 — Zoom family

| id | symbol | precondition | one write | readback | visual evidence | side effects | restore | reps | verdict |
|---|---|---|---|---|---|---|---|---|---|
| A4-E01 | `cameraGetZoomAbsoluteR` + `cameraGetRangeZoomAbsoluteR` | any | none | zoom value + range | — | latency of getter | — | 3 | |
| A4-E02 | `cameraSetZoomAbsoluteR` | AI off, zoom value read | one documented step | zoom after settle | target scale | AI mode, framing | previous zoom | 3 | |
| A4-E03 | `cameraSetZoomWithSpeedRelativeR` | same | one documented relative step | zoom after settle | scale direction | completion timing | previous zoom | 3 | |
| A4-E04 | `cameraSetZoomWithSpeedAbsoluteR` | same | one documented step | zoom after settle | scale | completion timing | previous zoom | 2 | |
| A4-E05 | `cameraSetZoomStopR` | zoom moving from E04 | stop | zoom settle | motion stops | residual scale | previous zoom | 3 | |
| A4-E06 | `aiSetAiAutoZoomR` | Track active | enable, then disable | AI mode + zoom | auto framing behaviour | interaction with `AutoZoomMode`/`AutoZoomSpeed` | disable | 2 | |
| A4-E07 | `ZoomParamType` digital zoom | only if a setter is located | — | — | — | — | — | 0 | |

## Wave A results (executed 2026-09-21, Tail2 fw 7.2.9.41)

Raw evidence: `.local/sdk-sweep/waveA-log.md` + `.local/sdk-sweep/*.png`.

| id | verdict | evidence |
|---|---|---|
| A1-E01 | `READBACK_VERIFIED` | float overload required; Pan ±180, Pitch ±90, PanReverse 0, PresetSpeed 1.0, RollBias 0. Bool overload returns rc=0/false for every type. |
| A1-E02 | `VERIFIED` | legacy attitude ≈ motor angles, intermittent `rc=-1` behaviour unchanged |
| A1-E03 | `READBACK_VERIFIED` | euler + motor + angular velocity; motor = commanded |
| A1-E04 | **`VERIFIED` (architecture-changing, 3 reps)** | `pitch 10 / yaw 20` → legacy 10.0/20.0, motor 10.0/20.0; `-10/-20` → −10/−20; `+15/0` → 15/0; visual confirmed |
| A1-E05 | `VERIFIED` | native speed pan=5 ≈ −5.5°/s; **pan sign inverted vs legacy** |
| A1-E06 | `VERIFIED` | native stop residual ≤0.01° over 1.5 s |
| A1-E07 | `VERIFIED` | legacy 2×{5 dps, 500 ms} → yaw +4.69 (baseline) |
| A1-E08 | `READBACK_VERIFIED` | preset list len 0 → recall untestable |
| A1-E09 | `READBACK_VERIFIED` | id 0, pose 0/0/0, zoom 1.0 |
| A1-E10 | `ACCEPTED_UNPROVEN` (no effect observed under tested preconditions) | PanReverse readback unchanged; direction unchanged on absolute and native-speed paths |
| A1-E11 | `VERIFIED` | `gimbalSetSpeedPositionR(0,5,10, speeds 5)` → 5.0/9.98 |
| A1-E12 | `CONSTRAINED` | under Track the absolute command is contended: yaw −23.95 → −19.18, never reached 25; `ai_main_mode` stayed 2; target stayed framed |
| A2-E01…E24 | see truth map table | 23/24 writable (bool needs numeric 0/1); 5 `CONSTRAINED` (0–4 only); 15/17 `UNSUPPORTED_TAIL2` under PRO+Track+Composition |
| A3-E01/E02 | `ACCEPTED_UNPROVEN` (no effect observed under tested preconditions) | 12 view values rc=0, `ai_sub_mode` and zoom unchanged |
| A3-E03/E04 | `READBACK_VERIFIED` (state) / visual `ACCEPTED_UNPROVEN` | sub_mode 0/1/2/3/4 mapping; full-body vs close-up frames identical |
| A3-E05 | not run | no target re-selection side effect observed to chase |
| A4-E01 | `READBACK_VERIFIED` | zoom ≥1.0; range `{0,100,1,0,valid}` (unit space unresolved) |
| A4-E02 | **`VERIFIED`** | 1.0→1.11 in ~5 s at speed 5 (slow async ramp), readback lags, restore verified |
| A4-E03 | `UNSUPPORTED_TAIL2` (measured no effect on fw 7.2.9.41) | relative-in from 1.0 left zoom at 1.0 for 7.5 s |
| A4-E04 | `UNSUPPORTED_TAIL2` (measured no effect on fw 7.2.9.41) | ratio=150 from 1.0 left zoom at 1.0 for 6 s |
| A4-E05 | `UNSUPPORTED_TAIL2` (measured no effect on fw 7.2.9.41) | zoom kept ramping after `cameraSetZoomStopR` (1.10→1.15→1.23) |
| A4-E06 | `ACCEPTED_UNPROVEN` | enable/disable rc=0; no readback path |
| A4-E07 | `NO_PUBLIC_PATH` | no digital-zoom setter located |

Evidence standard: verdicts use the per-capability expected-effect predicate
(`docs/Tail2_SDK_TRUTH_MAP.md` §2.5); `UNSUPPORTED_TAIL2` here means *measured no
effect on this firmware and no working condition found* — not merely `rc=0`.

Restore status: every exercised write was restored and re-read; the final device
state was `ai_main_mode=0`, `ai_sub_mode=0`, zoom 1.0, gimbal 0/0, gimbal params at
defaults, target cleared.

## Recording

Raw evidence → `.local/sdk-sweep/` (frames, raw return payloads, LED notes).
Sanitized verdicts → `docs/Tail2_SDK_TRUTH_MAP.md` rows + per-wave handoff in
`docs/handoff/inbox/`. Any row still `PENDING_WAVE_A` after the device run must
carry an explicit reason (device refused / not fixable / unsafe / deferred).


## Wave B results (executed 2026-09-21, Tail2 fw 7.2.9.41)

Raw evidence: `.local/sdk-sweep/waveB-log.md`.

| id | verdict | evidence |
|---|---|---|
| B0 locks (PanLocked/PitchLocked) | **VERIFIED** (2 reps each) | yaw_span 0.00 vs baseline ~20 (pan); pitch_span 0.00 vs ~12 (pitch) |
| B0 speed mode / limit area | `evidence_insufficient` | settled-position predicate cannot see speed or limits |
| B0 external perturbation under Track | invalid predicate | native-speed push absorbed by the AI (`push_delta ≈ 0`, 6 trials) |
| B1 gesture config | **READBACK_VERIFIED** | 18 params writable + readback + restored |
| B1 gesture ownership | `evidence_insufficient` | no physical gesture performed |
| B2 autofocus / AFC / focus getter | **READBACK_VERIFIED** | write → readback → restore |
| B2 white balance | **VERIFIED** | tungsten preset → strong visual blue cast |
| B2 WDR | `READBACK_VERIFIED` (async) | readback lags several seconds |
| B3 boot position trigger | **VERIFIED** | yaw 10 / pitch 5 → exactly 0/0 |
| B3 PresetSpeed | **CONSTRAINED** | 0.5 accepted, 2.0 ignored |
| B3 gimbal limits | **CONSTRAINED** | stored, not enforced on absolute look |
| B4 DevStatusCallback | **VERIFIED** | ~2 s cadence after refresh |
| B4 FastDevStatusCallback | **UNSUPPORTED_TAIL2** | never fired |
| B4 cameraStatus / hotplug | `ACCEPTED_UNPROVEN` | callable / registered, payload + hotplug unverified |
| LimitedZoneTrack getters | **UNSUPPORTED_TAIL2** | rc −1 |
| LimitedZoneTrack setters | `evidence_insufficient` | rc 0, no readback, no effect |

Safety note: object targets that leave the frame park the device in mode 2 / sub 20
and hunt to the gimbal limits (yaw −135°; operator saw the yellow LED). Recovery:
`target.clear` → `look.stop` → `aiSetGimbalMotorAngleR(0,0)` → `aiSetEnabledR(true)`.
A watchdog is required before any object-tracking product behaviour.

| `cameraSetPowerCtrlActionR(PowerOff)` | **VERIFIED** | device gone from PnP + SDK list (doc says tail air) |
