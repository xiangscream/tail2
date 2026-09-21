# Tail2 SDK Truth Map (v2 — Wave A measured)

2026-09-21 · branch `feature/sdk-sweep-a` · baselines:

- repo: `main @ 385fe55005c9e3b075fb454f18ffb9a789e9aab4`
- SDK package: `libdev_v2.1.0_8`
- `include/dev/dev.hpp` SHA256: `d6f12cd9ab50c696b5a2cf9224dda3fc72245e17408bf52dd98d631cb7f74f2d`
- machine census: `docs/Tail2_SDK_CENSUS.md` (480 symbols, `tools/sdk_census.py`)
- device: Tail2, firmware 7.2.9.41, UVC, Windows x64 build, operator present, OBSBOT Center closed
- raw evidence: `.local/sdk-sweep/waveA-log.md`, `.local/sdk-sweep/*.png` (local only)

## 0. Status vocabulary

| status | meaning |
|---|---|
| `VERIFIED` | physical / visual / state behavior reproduced on Tail2 |
| `READBACK_VERIFIED` | getter / status path proven; write behavior not implied |
| `ACCEPTED_UNPROVEN` | SDK accepted the request; physical / visual result not proven |
| `CONSTRAINED` | works only under documented runtime conditions |
| `UNSUPPORTED_TAIL2` | declared elsewhere but not usable on Tail2 |
| `NO_PUBLIC_PATH` | enum / hint exists but no complete public API contract |
| `DEFERRED_UNSAFE` | relevant but destructive or unsafe to exercise automatically |
| `NOT_PRODUCT_RELEVANT` | present in SDK but irrelevant to the Agent Camera MVP |
| `PENDING_WAVE_<X>` | not yet measured; must carry an explicit reason |

Evidence levels: `static` · `rc` · `readback` · `physical` · `visual` · `artifact`.
`rc=0` never upgrades a row above `ACCEPTED_UNPROVEN`.

**Standing correction from Wave A:** SDK doc applicability is *not* product truth in
either direction. The entire native gimbal family is documented `tailair+tiny` yet
most of it is `VERIFIED` on Tail2; conversely `cameraGetZoomAbsoluteR` omits Tail2
in its doc and works.

## 1. Wave A results summary

| finding | consequence for the later Primitive Layer |
|---|---|
| **Absolute look exists on Tail2** (`aiSetGimbalMotorAngleR`, `gimbalSetSpeedPositionR`) with exact readback | `Look` no longer has to be a slow ±10 dps rate hack; a real absolute/look primitive is possible |
| Absolute look is **contended by AI tracking** while `ai_main_mode=2` | `Look` must own AI state explicitly: absolute control requires AI off, or an agreed arbitration |
| **Native speed + native stop** exist; stop settles to ±0.01° vs legacy ≈0.4° | stop path can be upgraded; native speed pan sign is **inverted** vs legacy |
| `aiGetGimbalStateR` / `aiGetGimbalParaR` give real Tail2 readback (limits, reverse, euler+motor+velocity) | limits/reverse become enforceable, not guessed |
| `ai_sub_mode` reflects `aiSetTargetZoomTypeR` | framing *intent* is readback-verifiable even when not visible |
| `aiSetTargetViewTypeR` and three zoom-family writers return rc=0 with no effect observed | must never be promoted on `rc=0`; the runtime needs per-capability **expected-effect predicates**, not a universal no-op rule |
| Offset values (15/17) stay 0.0 even under PRO+Track+Composition | "composition offset" is not a Tail2 primitive |
| No zoom/view getter exists | framing readback stays state-only (`ai_sub_mode`) → `NO_PUBLIC_PATH` for values |

## 2. Wave A truth tables

### A1. Native Gimbal / Look

| symbol | doc applicability | current_truth | evidence | notes |
|---|---|---|---|---|
| `aiSetGimbalMotorAngleR(pitch,yaw,roll)` | tailair+tiny | **VERIFIED** | rc + readback + visual (3 reps) | pitch −90..90, yaw −180..180, roll ignored (`-1000` default). Readback exact on both legacy attitude and native motor angles. |
| `gimbalSetSpeedPositionR(roll,pitch,yaw,s_roll,s_pitch,s_yaw)` | tailair+tiny | **VERIFIED** | rc + readback | second absolute-position path (with per-axis speeds); commanded 5/10 landed exactly |
| `aiSetGimbalSpeedCtrlR(pitch,pan,roll)` | tailair+tiny | **VERIFIED** | rc + readback + visual | continuous speed; pan=+5 for ~1 s → yaw −5.5. **pan sign is inverted vs legacy** (`gimbalSpeedCtrlR` pan+ → yaw+). |
| `aiSetGimbalStop()` | tailair+tiny | **VERIFIED** | rc + readback (3 samples) | residual ≤0.01°, no overshoot; cleaner than legacy zero-speed (≈0.4°) |
| `gimbalSpeedCtrlR` (legacy, in production) | tailair+tiny | **VERIFIED** (baseline) | rc + physical | 2×{pan 5 dps, 500 ms} → yaw +4.69; AI-off prerequisite |
| `gimbalGetAttitudeInfoR` (legacy) | tailair+tiny | **VERIFIED** | readback | ≈ motor angles; intermittent `rc=-1` |
| `aiGetGimbalStateR` | tailair+tiny | **READBACK_VERIFIED** | readback | euler + motor + angular velocity. motor = commanded absolute; euler = motor + boot offset (yaw ≈ −14.2°, pitch ≈ +0.4° at rest) |
| `aiGetGimbalParaR(type, float&)` | tail2 (+tailair) | **READBACK_VERIFIED** | readback | PanMin −180 / PanMax 180 / PitchMin −90 / PitchMax 90 / PanReverse 0 / PresetSpeed 1.0 / RollBias 0. **Trap:** the `bool&` overload returns `rc=0` with `false` for every type — must use the float overload. |
| `aiSetGimbalParaR(type, value)` | tail2 (+tailair) | `PENDING_WAVE_B` | static | not exercised this wave (writes limits/reverse); read path proven |
| `aiGetGimbalBootPosR` | tailair+tiny | **READBACK_VERIFIED** | readback | returns id 0, roll/pitch/yaw 0, zoom 1.0 |
| `aiTrgGimbalBootPosR` | tailair+tiny | `PENDING_WAVE_B` | static | not exercised (gimbal motion to a stored pose) |
| `aiGetGimbalPresetListR` | tailair+tiny | **READBACK_VERIFIED** | readback | `len=0` — no presets on this device, so preset recall is untestable |
| `aiSetGimbalYawDirReverseR` | tailair+tiny | **ACCEPTED_UNPROVEN** (no effect observed under tested preconditions) | rc + readback + visual | rc=0; `PanReverse` readback stayed 0; panning direction unchanged on both the absolute and native-speed paths. Possible reboot requirement — not pursued. |
| `aiSetGimbalBootPosR`, `aiRstGimbalBootPosR`, `gimbalRstPosR` | tailair+tiny | **DEFERRED_UNSAFE** | static | persistent/factory-reset writes; not exercised |
| `cameraSetPanTiltAbsolute/Relative` | meet | `NOT_PRODUCT_RELEVANT` | static | other product |

### A2. Tail2 AI Control 0–23

`aiGetControlParaR` / `aiSetControlParaR` are Tail2-claimed and fully readable.
Write→readback→restore was run for all 23 writable parameters (target=Human).

| # | parameter | writable | readback reflects write | verdict |
|---|---|---|---|---|
| 0 | Motion (bool) | yes | yes | `READBACK_VERIFIED` |
| 1 | ForeTrack (bool) | yes | yes | `READBACK_VERIFIED` |
| 2 | Composition (bool) | yes | yes | `READBACK_VERIFIED` (visual effect `PENDING_WAVE_B`) |
| 3 | TrackerType (0/1) | yes | yes | `READBACK_VERIFIED` |
| 4 | GimCtrlMode (Normal/PRO) | yes | yes | `READBACK_VERIFIED` |
| 5 | GimCtrlSpeedMode | yes | 0–4 only | **CONSTRAINED**: `Custom=100` not accepted; 0,1,2,4 all accepted |
| 6 | PanGainAdaptive (bool) | yes | yes | `READBACK_VERIFIED` |
| 7 | PanGainValue (float) | yes | yes | `READBACK_VERIFIED` (float32 precision) |
| 8 | PanLocked (bool) | yes | yes | `READBACK_VERIFIED` |
| 9 | PitchGainAdaptive (bool) | yes | yes | `READBACK_VERIFIED` |
| 10 | PitchGainValue (float) | yes | yes | `READBACK_VERIFIED` |
| 11 | PitchLocked (bool) | yes | yes | `READBACK_VERIFIED` |
| 12 | AutoZoomCustomized (int) | yes | yes | `READBACK_VERIFIED` |
| 13 | AutoZoomMode (int) | yes | yes | `READBACK_VERIFIED` |
| 14 | OffsetAdaptiveX (bool) | yes | yes | `READBACK_VERIFIED` (nothing to adapt — see 15) |
| 15 | OffsetX (float) | accepted | **no (stays 0.0)** | **UNSUPPORTED_TAIL2** — tested under `GimCtrlMode=PRO` + Track + Composition; value never stored |
| 16 | OffsetAdaptiveY (bool) | yes | yes | `READBACK_VERIFIED` |
| 17 | OffsetY (float) | accepted | **no (stays 0.0)** | **UNSUPPORTED_TAIL2** (same preconditions as 15) |
| 18 | LimitAutoSelection (bool) | yes | yes | `READBACK_VERIFIED` |
| 19 | LimitPanMin | yes | yes | `READBACK_VERIFIED` (−100→−120→−100) |
| 20 | LimitPanMax | yes | yes | `READBACK_VERIFIED` (100→120→100) |
| 21 | LimitPitchMin | yes | yes | `READBACK_VERIFIED` (−30→−40→−30) |
| 22 | LimitPitchMax | yes | yes | `READBACK_VERIFIED` (30→40→30) |
| 23 | AutoZoomSpeed (int 1–10) | yes | yes | `READBACK_VERIFIED` (3→10→3) |

Behavioral/visual effects of 2/4/5/8/11/13/18–23 need a moving target and a
tracking session → `PENDING_WAVE_B`. Nothing was left unrestored: the full
original snapshot was re-read after the sweep and matched.

### A3. Target View / Target Zoom

| symbol | doc applicability | current_truth | evidence | notes |
|---|---|---|---|---|
| `aiSetTargetZoomTypeR` | tail2 | **READBACK_VERIFIED** (state); visual `ACCEPTED_UNPROVEN` (bbox scale/cx/cy not measured) | rc + `ai_sub_mode` + visual | `-1/0 → sub 0`, `1 → 1`, `2 → 2`, `3 → 3`, `4/5/6/99 → 4` (Human Normal/FullBody/HalfBody/CloseUp/CustomAutoZoom). **Full-body vs close-up frames were visually identical** in 2 samples at 640×480; digital zoom readback stayed 1.0. |
| `aiSetTargetViewTypeR` | tail2 | **ACCEPTED_UNPROVEN** (no effect observed under tested preconditions) | rc + `ai_sub_mode` + zoom | all 12 documented values (`Ignored=-2 … Trace=9`) returned rc=0 and left `ai_sub_mode=0` and zoom 1.0 unchanged. Insufficient evidence for a hard `no-op` claim: the expected-effect predicate (frame-bound bbox scale/cx/cy under Track) was not fully instrumented. |
| framing/value getters | — | **NO_PUBLIC_PATH** | static | no `aiGetTargetZoomTypeR` / `aiGetTargetViewTypeR` in the public headers; only `ai_sub_mode` state |
| `aiSetSelectedTargetR` | tail2 | **VERIFIED** (M1B) | rc + physical + visual | box/center/largest; identity is device-decided; a human box with no detectable face/head produced no actuation (completed, zero gimbal delta over 3 samples) |
| `DevTargetZoomType` / `DevTargetViewType` / `DevCustomizedZoomType` | data | `READBACK_VERIFIED` via sub_mode (zoom only) | — | enum bodies in `docs/Tail2_SDK_CENSUS.md` |

### A4. Zoom family

| symbol | doc applicability | current_truth | evidence | notes |
|---|---|---|---|---|
| `cameraSetZoomAbsoluteR(zoom, speed)` | meet+tail2+tailair+tiny | **VERIFIED** | rc + readback + visual | **slow asynchronous ramp**: 1.0→1.11 in ~5 s at speed 5 (~0.025/s); getter lags; do not treat the next readback as final |
| `cameraGetZoomAbsoluteR` | meet+tailair+tiny (no tail2) | **READBACK_VERIFIED** | readback | normalized ≥1.0 |
| `cameraGetRangeZoomAbsoluteR` | meet+tailair+tiny | **READBACK_VERIFIED** | readback | `{min 0, max 100, step 1, default 0, valid true}` — unit space does **not** match the normalized zoom readback; unresolved |
| `cameraSetZoomStopR` | tail air | **UNSUPPORTED_TAIL2** (measured no effect on fw 7.2.9.41) | rc + readback | rc=0; the zoom kept ramping after the command (1.10 → 1.15 → 1.23). Documented for another product; no working condition found. Must not be used as a stop. |
| `cameraSetZoomWithSpeedRelativeR(step,speed,step_mode,in)` | tailair | **UNSUPPORTED_TAIL2** (measured no effect on fw 7.2.9.41) | rc + readback | rc=0; relative-in from 1.0 left zoom at 1.0 for 7.5 s. No working condition found. |
| `cameraSetZoomWithSpeedAbsoluteR(ratio,speed)` | tailair+tiny | **UNSUPPORTED_TAIL2** (measured no effect on fw 7.2.9.41) | rc + readback | rc=0; ratio=150 from 1.0 left zoom at 1.0 for 6 s. No working condition found. |
| `aiSetAiAutoZoomR(enabled)` | tailair+tiny | **ACCEPTED_UNPROVEN** | rc | rc=0 both ways; no readback path and no isolated visual test |
| digital zoom (`ZoomParamType{…DIGITAL_ZOOM}`) | generic | **NO_PUBLIC_PATH** | static | enum exists; no located setter |

## 2.5 Evidence standard: Expected Effect Predicate

Statuses in this map are assigned against a **per-capability expected effect**, not a
generic `rc == 0 and getter unchanged => no-op` rule. A single generic rule would
manufacture false negatives as easily as false positives.

| capability | expected effect predicate |
|---|---|
| offset write | typed readback of the value (and, if supported, a frame-bound composition shift) |
| zoom write | zoom time-series changes toward the target, slope non-zero |
| zoom stop | slope converges to 0 within a bounded window |
| gimbal move | angle / angular-velocity readback changes toward the command |
| pan/pitch lock | pan/pitch response to a moving target is suppressed |
| framing / view | frame-bound bbox scale / cx / cy change under Track |
| gesture | event + state transition + physical response |

If evidence is insufficient to evaluate the predicate, the row must be
`ACCEPTED_UNPROVEN` — never a bare `no-op` claim. Wave A rows that cite
"no effect observed" also name the preconditions that were tested. This predicate
set is the seed of the later mid-layer **Outcome Verifier**.


## 3. Other families — static disposition (Waves B/C/D input)

| family | Tail2 disposition | notable symbols | next wave |
|---|---|---|---|
| gesture / hand / remote | declared Tail2-class in project docs; census applicability generic | `DevGestureParaType`, `DevGestureTrackParaType` | B1 |
| iq (focus / WB / exposure) | declared Tail2; census applicability mostly generic | `cameraSetAutoFocusModeR`, `cameraSetAFCTrackModeR`, `cameraGetFocusAbsolute`, `cameraGet/SetWhiteBalanceR` | B2 |
| preset (gimbal / zone / boot) | gimbal preset family `tailair+tiny`; **list is empty on this device**; zone preset = `tiny` | `aiGetGimbalPresetListR`, `aiTrgGimbalPresetR`, `aiAdd/Del/UpdGimbalPresetR`, `aiGetZonePreset*` | B3 |
| status / callback | `DevEventNotifyCallback` doc = `tailair`; `cameraStatus()` union layout for Tail2 unparsed | `nextRefreshDevStatus`, `fastNextRefreshDevStatus`, `cameraStatus`, `DevStatusCallback`, `FastDevStatusCallback`, `Devices::setDevChangedCallback` | B4 |
| media / output | Tail2-claimed for `cameraSet/GetMediaOperateParamR`; UVC-vs-record relation not expressed by SDK | record/live/RTSP/NDI/SRT, `DevMediaStreamId`, encode params | C |
| storage / mtp / file | file download doc = meet+tiny2 series; Tail2 retrieval undocumented | `startFileDownloadAsync`, `localFilePath`, `MtpFileType` | C/D |
| audio | TWS/earbud families are other-product; MVP uses host audio | `DevTWS*`, `DevAudio*` | D |
| network | device network config, irrelevant to USB MVP | `DevIpProtoType`, `NetworkInterfaceType`, `DevEthernetState` | D |
| power / upgrade | destructive or lifecycle | `DevPowerCtrlActionType`, `UpgradeResult/UpgradeState` | D (`DEFERRED_UNSAFE`) |

## 4. Explicit closure classes (Wave D seed)

| class | items | reason |
|---|---|---|
| `NO_PUBLIC_PATH` | candidate notification (`DevCDCNotifyTypeAiTarget`); device-side real-time tracking-box readback; framing value getters; digital-zoom enable without a located setter | enum/hint only |
| `UNSUPPORTED_TAIL2` | `cameraSetZoomStopR`, `cameraSetZoomWithSpeedRelativeR`, `cameraSetZoomWithSpeedAbsoluteR` (measured no effect on fw 7.2.9.41); offset values `OffsetX/OffsetY` (15/17, write not stored under PRO+Track+Composition); `cameraSetPanTilt*`; `cameraSetRoiTarget`; `aiSetSelectTargetR`(tiny) | measured no effect **and** no working condition found; some also documented for other products |
| `CONSTRAINED` | `aiSetGimbalMotorAngleR` under Track (AI contends); `gim_ctrl_speed_mode` Custom=100 | a working condition **is** known and stated; behaviour differs from the plain path |
| `DEFERRED_UNSAFE` | `aiRstGimbalBootPosR`, `gimbalRstPosR`, `aiSetGimbalBootPosR`, format/delete/erase/upgrade/download/restore families | destructive or persistent writes |
| `NOT_PRODUCT_RELEVANT` | TWS/earbuds, HDMI/SDI output, network config, remote-custom keys, zone presets | not part of the Agent Camera MVP |


## 6. Wave B measured results (behavioral + gesture/IQ/preset/status)

Statuses use the same expected-effect standard. `evidence_insufficient` rows are
listed explicitly rather than being guessed as no-ops.

| symbol / item | current_truth | evidence | notes |
|---|---|---|---|
| `aiSetControlParaR` PanLocked (8) | **VERIFIED** | gimbal time-series, 2 reps | yaw_span 0.00 vs baseline 21.63/19.09; pitch still moves |
| `aiSetControlParaR` PitchLocked (11) | **VERIFIED** | gimbal time-series, 2 reps | pitch_span 0.00 vs baseline 11.24/12.39; yaw still moves |
| `aiSetControlParaR` GimCtrlSpeedMode (5) | `evidence_insufficient` | settled position only | no settled difference; needs a transient predicate |
| `aiSetControlParaR` TrackerType/Limits (3,19–22) | `evidence_insufficient` | settled position only | ±15 limits did not visibly clamp a one-shot reframe |
| Motion / ForeTrack / Composition / Gains / AutoZoom* | `evidence_insufficient` | — | need a reliable motion source + frame-bound metrics |
| box select in Normal mode | **READBACK_VERIFIED** | attitude | one-shot reframe; it does **not** enter Track (`ai_main_mode` stays 0) |
| object target leaving frame | **CONSTRAINED / hazard** | attitude + LED | device parks in mode 2 / sub 20 and hunts to limits (yaw −135°); needs a watchdog |
| `aiGet/SetGestureParaR` (9 params) | **READBACK_VERIFIED** | read/write/restore | defaults: Gesture/TargetSelection/Zoom/Record/Snapshot/Rolling = true; DynamicZoom/Mirror = false; ZoomFactor 1.0 |
| `aiGet/SetGestureTrackParaR` (9 params) | **READBACK_VERIFIED** | read/write/restore | Pan ±45 / Pitch ±30 / HandType 0 / TrackSpeed 5 / Pan+Pitch enabled / Rest 3s |
| gesture ownership vs Agent | `evidence_insufficient` | — | no physical gesture performed; gestures are enabled by default ⇒ live competing intent source |
| `cameraGet/SetAutoFocusModeR` | **READBACK_VERIFIED** | read/write/restore | 1 = AFC |
| `cameraGet/SetAFCTrackModeR` | **READBACK_VERIFIED** | read/write/restore | 3 = Foreground |
| `cameraGetFocusAbsolute` | **READBACK_VERIFIED** | readback | focus 0, auto_focus true |
| `cameraGet/SetWhiteBalanceR` | **VERIFIED** | read/write + **visual** | tungsten preset produced a strong blue cast |
| `cameraGet/SetWdrR` | `READBACK_VERIFIED` (async) | readback | readback lags several seconds after a revert |
| `aiGetGimbalBootPosR` | **READBACK_VERIFIED** | readback | id 0, pose 0/0/0, zoom 1.0 |
| `aiTrgGimbalBootPosR` | **VERIFIED** | readback | from yaw 10 / pitch 5 → exactly 0/0 |
| `aiSetGimbalParaR` PanReverse (4) | **READBACK_VERIFIED** | read/write/restore | distinct from `aiSetGimbalYawDirReverseR` (which had no effect) |
| `aiSetGimbalParaR` PresetSpeed (5) | **CONSTRAINED** | readback | 0.5 accepted, 2.0 silently ignored (readback stays 1.0) |
| gimbal para limits (0–3) | **CONSTRAINED** | readback + physical | stored and read back, but do **not** clamp `aiSetGimbalMotorAngleR` |
| `DevStatusCallback` | **VERIFIED** | event count/age | ~2 s cadence; 10 events after `nextRefreshDevStatus` |
| `FastDevStatusCallback` | **UNSUPPORTED_TAIL2** | event count | 0 events in 50 s+ including fast refresh |
| `cameraStatus()` | `ACCEPTED_UNPROVEN` | callable | returns the union; **layout not parsed** (no documented Tail2 payload) |
| `Devices::setDevChangedCallback` | `ACCEPTED_UNPROVEN` | registration | registered; hotplug not exercised |
| `aiGetLimitedZoneTrack*R` (6 getters) | **UNSUPPORTED_TAIL2** | rc | all rc = −1 |
| `aiSetLimitedZoneTrack*R` | `evidence_insufficient` | rc | rc = 0 with no readback and no observed effect |

## 5. Open items handed to Wave B

1. Behavioral effect of AI control 2/4/5/8/11/13/18–23 under a moving target (does
   `Composition`, `PanLocked`, `GimCtrlMode=PRO` actually change tracking?).
2. `aiSetGimbalParaR` writes (limits / PanReverse / PresetSpeed) with readback restore.
3. `aiTrgGimbalBootPosR` (gimbal motion to the stored pose) and whether boot-position
   set/reset can be made safe with a saved pose.
4. Whether `aiSetGimbalYawDirReverseR` needs a reboot, and whether it affects a
   layer other than the SDK paths tested.
5. Gesture family, focus/WB, presets, status callbacks (Wave B scope).
