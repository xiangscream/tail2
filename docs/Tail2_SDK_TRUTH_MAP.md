# Tail2 SDK Truth Map v1.0 (frozen — Wave A + B + C measured, Wave D closed)

2026-09-21 · branches `feature/sdk-sweep-a`, `feature/sdk-sweep-b` · baselines:

- repo: `main @ 385fe55005c9e3b075fb454f18ffb9a789e9aab4` (Wave A, merged) · `main @ 84607df1a7fb6412e710a103244bb859d0843b7e` (Wave B)
- SDK package: `libdev_v2.1.0_8`
- `include/dev/dev.hpp` SHA256: `d6f12cd9ab50c696b5a2cf9224dda3fc72245e17408bf52dd98d631cb7f74f2d`
- machine census: `docs/Tail2_SDK_CENSUS.md` (**490 symbols**, `tools/sdk_census.py`) with a
  provable **candidate-vs-parsed completeness gate**: dev.hpp 427/427, devs.hpp 27/27,
  comm.hpp 4/4, unmatched 0. Declarations are no longer trusted by symbol count alone.
- device: Tail2, firmware 7.2.9.41, UVC, Windows x64 build, operator present, OBSBOT Center closed
- raw evidence: `.local/sdk-sweep/waveA-log.md`, `.local/sdk-sweep/waveB-log.md` (local only)
- Wave C media surface + measured results: `docs/Tail2_SDK_MEDIA_SURFACE.md`
- Wave D closure table (generated): `tools/closure_table.py` (Appendix A below)

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


## 5. Wave B measured results (behavioral + gesture/IQ/preset/status)

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
| `cameraSetPowerCtrlActionR(DevPowerCtrlPowerOff)` | **VERIFIED** | physical | documented `tail air` but powers the Tail2 off: camera disappears from PnP and the SDK list. Reboot/Suspend untested. |
## 6. Remaining evidence gaps / Wave C-D carry-over

Accepted as **evidence_insufficient** for Wave B (reason recorded, not "unmeasured"):
`Composition`, `ForeTrack`, `Gains`, `AutoZoom`, `GimCtrlSpeedMode` behaviour,
`LimitArea` behaviour, hotplug callback reliability, gesture physical ownership.

1. Behavioral effect of AI control 2/4/5/8/11/13/18–23 under a moving target (does
   `Composition`, `GimCtrlMode=PRO` actually change tracking?). `PanLocked`/`PitchLocked`
   are already VERIFIED in §5.
2. `aiSetGimbalParaR` writes (limits / PanReverse / PresetSpeed) with readback restore.
3. `aiTrgGimbalBootPosR` (gimbal motion to the stored pose) and whether boot-position
   set/reset can be made safe with a saved pose.
4. Whether `aiSetGimbalYawDirReverseR` needs a reboot, and whether it affects a
   layer other than the SDK paths tested.
5. Gesture family, focus/WB, presets, status callbacks (Wave B scope).

## 7. Runtime requirements registered by this sweep (not implemented here)

- **Object-loss watchdog (hard requirement, from Wave B).** A Common-class target that
  leaves the frame parks the device in `ai_main_mode=2 / ai_sub_mode=20` and keeps
  searching until the gimbal reaches its limits (measured yaw −135°, pitch 55°; the
  operator saw the yellow LED). The Runtime must have a target-loss timeout /
  out-of-frame watchdog → `target.clear` → gimbal stop → recover to a known pose → state
  and evidence update. Registered as a requirement only: the Truth Sweep does not build
  primitives.
- **Gesture as a competing intent source (from Wave B).** Gesture / TargetSelection /
  Zoom / Record / Snapshot / Rolling are enabled by default, so gestures are a live
  intent source running in parallel with the Agent. Runtime must arbitrate explicitly.
- **B1b (deferred, pre-Primitive-Freeze):** a short real-human gesture session to measure
  how a gesture acquires Track / Gimbal / Zoom ownership. Not a Wave C blocker.

## 8. Wave C measured results (Media / Output / UVC coexistence)

| symbol / item | current_truth | evidence | notes |
|---|---|---|---|
| `cameraGet{Record,Output,Live}EncodeParamR` | **READBACK_VERIFIED** | typed readback | fps is milli-fps; `night_flag` changes the output readback |
| `cameraSet{Record,Output}EncodeParamR` | **CONSTRAINED** | read/write/restore | bitrate validated per resolution (4K@20 ignored, 1080p@10 → 20); `encode_format` write not reflected |
| `cameraGetLiveEncodeParamR` | **READBACK_VERIFIED** | typed readback | no public setter ⇒ live encode write `NO_PUBLIC_PATH` |
| `cameraGet/SetRecordSplitSizeR` | **VERIFIED** | read/write/restore | 5 → 2 → 5 |
| `cameraGetMediaOperateParamR` | **READBACK_VERIFIED** | per-stream readback | Uvc=Start; Record/Live/Rtsp/Ndi/Srt=Stop; Capture rc −1; Hdmi/Sdi/sub=Auto; Auto rc −1 |
| `cameraSetMediaOperateParamR` (Record, Start) | `no_effect_observed` / `prerequisite_unmet` | readback | state stays Stop; storage prerequisite unmet ⇒ not `UNSUPPORTED` |
| UVC coexistence | **CONSTRAINED** | frames + readback | no conflict observed while native ops were merely accepted; native-active case unreachable |
| `cameraGetSelectNdiOrRtspR` / `NdiRtspEncoderFormatR` | **READBACK_VERIFIED** | readback | select 0, format 1 |
| `cameraGetNdiRtspBitrateLevelR` | **contract anomaly** | readback | returned 60000000 for an enum-typed (`DevVideoBitLevelType`) out-param |
| `cameraSetSelectNdiOrRtspR` / `NdiRtspBitrateLevelR` / `NdiRtspEncoderFormatR` / `HdmiInfoR` | `no_effect_observed` | read/write/restore | rc=0, readback unchanged (doc = tailair) |
| `cameraGetHdmiInfoR` | **READBACK_VERIFIED** | readback | all fields 0 |
| SDI / SRT configuration | **NO_PUBLIC_PATH** | static | enums only, no getter/setter functions |
| device-native artifact retrieval | **NO_PUBLIC_PATH** | static | download family documented meet+tiny |
| media state via callback | `evidence_insufficient` | event count | ordinary callback ~2 s; `CameraStatus` union layout undocumented ⇒ getter authoritative |
| long media experiments | **CONSTRAINED (link risk)** | observation | USB enumeration failed / device dropped twice (once after PowerOff, once mid media read); recovered by physical re-plug |

## 9. Wave D closure

Every function/callback in the Tail2-relevant families (gimbal, target, track, ai,
camera, media, media.output, iq, gesture, preset, status, power) now carries an
explicit disposition. **No architecture-significant symbol is left as a bare `[U]`.**

| disposition | count | meaning |
|---|---|---|
| `VERIFIED` | 23 | physical / visual / state behaviour reproduced on Tail2 |
| `READBACK_VERIFIED` | 38 | getter / status path proven |
| `CONSTRAINED` | 5 | works only under stated conditions |
| `ACCEPTED_UNPROVEN` | 16 | rc accepted or Tail2-claimed, not proven |
| `UNSUPPORTED_TAIL2` | 14 | measured no effect / rejected |
| `evidence_insufficient` | 9 | predicate could not be evaluated (reason recorded) |
| `DEFERRED_UNSAFE` | 15 | destructive / persistent; not exercised by policy |
| `DOC_OTHER_PRODUCT` | 140 | documented for another product, not exercised — **not** a support claim |
| `NOT_PRODUCT_RELEVANT` | 2 | outside the Agent Camera MVP |
| total | 262 | |

`DOC_OTHER_PRODUCT` is deliberately **not** called `UNSUPPORTED_TAIL2`: Wave A/B/C
proved doc applicability wrong in both directions (the whole native gimbal family is
documented `tailair+tiny` yet works; `cameraSetPowerCtrlActionR` is documented
`tail air` yet powers a Tail2 off). Claiming "unsupported" without measurement would
repeat that mistake in the opposite direction. These remain explicitly flagged gaps.

### Closure classes required by the plan

| class | items |
|---|---|
| documented for Tail Air / Tiny / Meet but not Tail2 | the `DOC_OTHER_PRODUCT` set (Appendix A) |
| incomplete public payload contract | `DevCDCNotifyTypeAiTarget` (candidate notification), device-side tracking-box/identity readback, media event payload, `CameraStatus` union layout |
| tracking-box / identity readback absence | confirmed absent: no native tracking box, identity is device-decided |
| file download not documented for Tail2 | `startFileDownloadAsync`, `setFileDownloadCallback`, `localFilePath`, `localFileMiniPath` (meet+tiny) |
| destructive operations intentionally not run | the `DEFERRED_UNSAFE` set (factory reset, gimbal reset, boot position write, zone reset, indicator clear, file delete/format/upgrade/download) |
| capabilities with no product relevance | TWS/earbuds, network configuration, HDMI/NDI boxes, zone presets |

### Primitive-layer freeze gate (plan §10)

- [x] Phase 0 census covers the full SDK resource (completeness gate, unmatched 0)
- [x] Wave A closed
- [x] Wave B closed for high/medium primitive-value capabilities
- [x] Wave C has a clear truth state even where host_uvc remains preferred
- [x] Wave D explicitly records unsupported / deferred gaps
- [x] no architecture-significant API left as an unexplained `[U]`
- [ ] B1b real-human gesture session (deferred, pre-freeze)
- [ ] optional C4 receiver-level verification (needs a network sink)

### Appendix A — full closure table

| symbol | kind | risk | doc applicability | Wave D disposition | basis |
|---|---|---|---|---|---|
| `aiDelAutoGroupModeR` | function | unknown | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `aiGetAutoOffsetEnable` | function | read_only | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `aiGetControlParaR` | function | read_only | tail2 | READBACK_VERIFIED | all 24 params |
| `aiGetControlParaR` | function | read_only | generic | READBACK_VERIFIED | all 24 params |
| `aiGetControlParaR` | function | read_only | generic | READBACK_VERIFIED | all 24 params |
| `aiGetHorizontalOffset` | function | read_only | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `aiGetVerticalOffset` | function | read_only | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `aiSetAutoOffset` | function | reversible_write | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `aiSetButtonSwitchR` | function | reversible_write | generic | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `aiSetControlParaR` | function | reversible_write | tail2 | VERIFIED | 23/24 writable + readback; Pan/PitchLocked verified behaviourally |
| `aiSetControlParaR` | function | reversible_write | generic | VERIFIED | 23/24 writable + readback; Pan/PitchLocked verified behaviourally |
| `aiSetControlParaR` | function | reversible_write | generic | VERIFIED | 23/24 writable + readback; Pan/PitchLocked verified behaviourally |
| `aiSetEnabledR` | function | reversible_write | tailair+tiny | VERIFIED | AI on/off behaviour |
| `aiSetHorizontalOffset` | function | reversible_write | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `aiSetVerticalOffset` | function | reversible_write | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `setTailAirWhiteList` | function | read_only | generic | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `cameraGetAntiFlickR` | function | read_only | meet+tailair+tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `cameraGetConfigRange` | function | read_only | tail2 | ACCEPTED_UNPROVEN | Tail2-claimed in the header; not exercised by this sweep |
| `cameraGetDelayTimeInTimelapse` | function | read_only | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `cameraGetModuleActiveR` | function | read_only | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `cameraGetRangeAntiFlickR` | function | read_only | meet+tailair+tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `cameraGetRotationDegree` | function | read_only | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `cameraGetWatermarkAttributeR` | function | read_only | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `cameraSetAiModeU` | function | reversible_write | tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetAntiFlickR` | function | reversible_write | meet+tailair+tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetBgColorU` | function | reversible_write | meet | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetBgEnableU` | function | reversible_write | meet | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetBgModeU` | function | reversible_write | meet | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetButtonModeU` | function | reversible_write | meet | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetCancelDelayActionInTimelapse` | function | reversible_write | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetCustomizeButtonActionU` | function | reversible_write | meet | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetDelayTimeInTimelapse` | function | reversible_write | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetFovU` | function | reversible_write | meet+tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetKcpPreviewResolutionR` | function | reversible_write | tailair | NOT_PRODUCT_RELEVANT | outside the Agent Camera MVP (other product form factor / platform) |
| `cameraSetLedCtrlU` | function | reversible_write | tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetMaskLevelU` | function | reversible_write | meet | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetResourceActionU` | function | reversible_write | meet+tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetRestoreFactorySettingsR` | function | destructive | generic | DEFERRED_UNSAFE | destructive; not exercised by policy |
| `cameraSetRotationDegree` | function | reversible_write | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetSuspendTimeU` | function | reversible_write | meet+tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetVerticalModeU` | function | reversible_write | tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetWatermarkAttributeR` | function | reversible_write | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `aiGetGestureParaR` | function | read_only | tail2 | READBACK_VERIFIED | 9 params |
| `aiGetGestureParaR` | function | read_only | generic | READBACK_VERIFIED | 9 params |
| `aiGetGestureTrackParaR` | function | read_only | tail2 | READBACK_VERIFIED | 9 params |
| `aiGetGestureTrackParaR` | function | read_only | generic | READBACK_VERIFIED | 9 params |
| `aiGetGestureTrackParaR` | function | read_only | generic | READBACK_VERIFIED | 9 params |
| `aiSetGestureCtrlR` | function | reversible_write | generic | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `aiSetGestureParaR` | function | reversible_write | tail2 | READBACK_VERIFIED | writable + readback |
| `aiSetGestureParaR` | function | reversible_write | generic | READBACK_VERIFIED | writable + readback |
| `aiSetGestureTrackParaR` | function | reversible_write | tail2 | READBACK_VERIFIED | writable + readback |
| `aiSetGestureTrackParaR` | function | reversible_write | generic | READBACK_VERIFIED | writable + readback |
| `aiSetGestureTrackParaR` | function | reversible_write | generic | READBACK_VERIFIED | writable + readback |
| `dev_get_log_handler` | function | read_only | generic | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `dev_set_log_handler` | function | reversible_write | generic | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `aiAddGimbalPresetR` | function | reversible_write | tailair+tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `aiDelGimbalPresetR` | function | unknown | tailair+tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `aiGetGimbalBootPosR` | function | read_only | tailair+tiny | READBACK_VERIFIED | id 0, pose 0/0/0 |
| `aiGetGimbalParaR` | function | read_only | tail2 | READBACK_VERIFIED | float overload; bool overload is a trap |
| `aiGetGimbalParaR` | function | read_only | tail2+tailair | READBACK_VERIFIED | float overload; bool overload is a trap |
| `aiGetGimbalPresetInfoWithIdR` | function | read_only | tailair+tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `aiGetGimbalPresetListR` | function | read_only | tailair+tiny | READBACK_VERIFIED | len 0 |
| `aiGetGimbalPresetNameWithIdR` | function | read_only | tailair+tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `aiGetGimbalStateR` | function | read_only | tailair+tiny | READBACK_VERIFIED | euler + motor + velocity |
| `aiRstGimbalBootPosR` | function | destructive | tailair+tiny | DEFERRED_UNSAFE | destructive; not exercised by policy |
| `aiSetGimbalBootPosR` | function | reversible_write | tailair+tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `aiSetGimbalMotorAngleR` | function | reversible_write | tailair+tiny | VERIFIED | rc + readback + visual, 3 reps |
| `aiSetGimbalParaR` | function | reversible_write | tail2 | CONSTRAINED | PanReverse ok; PresetSpeed 0.5 ok / 2.0 ignored; limits stored not enforced |
| `aiSetGimbalParaR` | function | reversible_write | tail2+tailair | CONSTRAINED | PanReverse ok; PresetSpeed 0.5 ok / 2.0 ignored; limits stored not enforced |
| `aiSetGimbalPresetNameWithIdR` | function | reversible_write | tailair+tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `aiSetGimbalSpeedCtrlR` | function | reversible_write | tailair+tiny | VERIFIED | rc + readback + visual |
| `aiSetGimbalStop` | function | reversible_write | tailair+tiny | VERIFIED | residual <= 0.01 deg |
| `aiSetGimbalYawDirReverseR` | function | reversible_write | tailair+tiny | ACCEPTED_UNPROVEN | rc=0, no readback/visual effect |
| `aiTrgGimbalBootPosR` | function | command | tailair+tiny | VERIFIED | yaw10/pitch5 -> exactly 0/0 |
| `aiTrgGimbalPresetR` | function | command | tailair+tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `aiUpdGimbalPresetR` | function | unknown | tailair+tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetPanTiltAbsolute` | function | reversible_write | meet | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetPanTiltRelative` | function | reversible_write | meet | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `gimbalGetAttitudeInfoR` | function | read_only | tailair+tiny | VERIFIED | readback (intermittent rc=-1) |
| `gimbalRstPosR` | function | destructive | tailair+tiny | DEFERRED_UNSAFE | destructive; not exercised by policy |
| `gimbalSetSpeedPositionR` | function | reversible_write | tailair+tiny | VERIFIED | rc + readback |
| `gimbalSpeedCtrlR` | function | command | tailair+tiny | VERIFIED | legacy baseline, rc + physical |
| `cameraGetAAEEvBiasR` | function | read_only | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `cameraGetAELockR` | function | read_only | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `cameraGetAFCTrackModeR` | function | read_only | tail2 | READBACK_VERIFIED | readback |
| `cameraGetAutoFocusModeR` | function | read_only | tail2+tailair | READBACK_VERIFIED | readback |
| `cameraGetExposureAbsolute` | function | read_only | meet+tailair+tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `cameraGetExposureModeR` | function | read_only | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `cameraGetFaceAER` | function | read_only | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `cameraGetFocusAbsolute` | function | read_only | meet+tail2+tailair+tiny | READBACK_VERIFIED | focus + auto_focus |
| `cameraGetFocusPosR` | function | read_only | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `cameraGetISOLimitR` | function | read_only | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `cameraGetImageBrightnessR` | function | read_only | meet+tailair+tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `cameraGetImageContrastR` | function | read_only | meet+tailair+tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `cameraGetImageHueR` | function | read_only | meet+tailair+tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `cameraGetImageSaturationR` | function | read_only | meet+tailair+tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `cameraGetImageSharpR` | function | read_only | meet+tailair+tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `cameraGetMAEIsoR` | function | read_only | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `cameraGetMAEShutterR` | function | read_only | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `cameraGetPAEEvBiasR` | function | read_only | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `cameraGetRangeExposureAbsolute` | function | read_only | meet+tailair+tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `cameraGetRangeFocusAbsolute` | function | read_only | meet+tailair+tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `cameraGetRangeImageBrightnessR` | function | read_only | meet+tailair+tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `cameraGetRangeImageContrastR` | function | read_only | meet+tailair+tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `cameraGetRangeImageHueR` | function | read_only | meet+tailair+tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `cameraGetRangeImageSaturationR` | function | read_only | meet+tailair+tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `cameraGetRangeImageSharpR` | function | read_only | meet+tailair+tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `cameraGetRangeMAEIsoR` | function | read_only | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `cameraGetRangePAEEvBiasR` | function | read_only | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `cameraGetRangeWhiteBalanceR` | function | read_only | meet+tailair+tiny | READBACK_VERIFIED | readback |
| `cameraGetSAEShutterR` | function | read_only | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `cameraGetWdrListR` | function | read_only | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `cameraGetWdrR` | function | read_only | tailair | READBACK_VERIFIED | readback (async) |
| `cameraGetWhiteBalanceListR` | function | read_only | meet+tailair+tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `cameraGetWhiteBalanceR` | function | read_only | meet+tailair+tiny | READBACK_VERIFIED | readback |
| `cameraGetWhiteBalanceR` | function | read_only | tail2 | READBACK_VERIFIED | readback |
| `cameraSetAAEApertureR` | function | reversible_write | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetAAEEvBiasR` | function | reversible_write | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetAELockR` | function | reversible_write | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetAFCTrackModeR` | function | reversible_write | tail2+tailair | READBACK_VERIFIED | writable + readback |
| `cameraSetAutoFocusModeR` | function | reversible_write | tail2+tailair | READBACK_VERIFIED | writable + readback |
| `cameraSetExposureAbsolute` | function | reversible_write | meet+tailair+tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetExposureModeR` | function | reversible_write | tailair | ACCEPTED_UNPROVEN | probe op exists, not closed |
| `cameraSetFaceAER` | function | reversible_write | generic | ACCEPTED_UNPROVEN | probe op exists, not closed |
| `cameraSetFaceFocusR` | function | reversible_write | generic | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetFocusAbsolute` | function | reversible_write | meet+tailair+tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetFocusPosR` | function | reversible_write | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetISOLimitR` | function | reversible_write | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetImageBrightnessR` | function | reversible_write | meet+tailair+tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetImageContrastR` | function | reversible_write | meet+tailair+tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetImageFlipHorizonU` | function | reversible_write | meet+tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetImageHueR` | function | reversible_write | meet+tailair+tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetImageSaturationR` | function | reversible_write | meet+tailair+tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetImageSharpR` | function | reversible_write | meet+tailair+tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetImageStyleR` | function | reversible_write | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetMAEApertureR` | function | reversible_write | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetMAEIsoR` | function | reversible_write | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetMAEShutterR` | function | reversible_write | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetPAEEvBiasR` | function | reversible_write | tailair | ACCEPTED_UNPROVEN | probe op exists, not closed |
| `cameraSetSAEEvBiasR` | function | reversible_write | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetSAEShutterR` | function | reversible_write | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetWdrR` | function | reversible_write | meet+tailair+tiny | READBACK_VERIFIED | writable, readback lags seconds |
| `cameraSetWhiteBalanceR` | function | reversible_write | meet+tailair+tiny | VERIFIED | readback + strong visual (tungsten blue cast) |
| `cameraSetWhiteBalanceR` | function | reversible_write | tail2 | VERIFIED | readback + strong visual (tungsten blue cast) |
| `UvcParamRange` | function | unknown | generic | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `VideoFormatInfo` | function | destructive | generic | DEFERRED_UNSAFE | destructive; not exercised by policy |
| `VideoFormatInfo` | function | destructive | generic | DEFERRED_UNSAFE | destructive; not exercised by policy |
| `aiSetVideoCenter` | function | reversible_write | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraGetMainVideoBitrateLevelR` | function | read_only | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `cameraGetMainVideoEncoderFormatR` | function | destructive | tailair | DEFERRED_UNSAFE | destructive; not exercised by policy |
| `cameraGetMediaOperateParamR` | function | read_only | tail2 | READBACK_VERIFIED | per-stream readback |
| `cameraGetOutputEncodeParamR` | function | read_only | tail2 | READBACK_VERIFIED | night_flag changes readback |
| `cameraGetRecordEncodeParamR` | function | read_only | tail2 | READBACK_VERIFIED | 4K/60Mbps/H264; fps is milli-fps |
| `cameraGetRecordSplitSizeR` | function | read_only | tailair | VERIFIED | readback |
| `cameraSetMainVideoBitrateLevelR` | function | reversible_write | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetMainVideoEncoderFormatR` | function | destructive | tailair | DEFERRED_UNSAFE | destructive; not exercised by policy |
| `cameraSetMediaModeU` | function | reversible_write | meet | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetMediaOperateParamR` | function | reversible_write | tail2 | CONSTRAINED | accepted; Record state stays Stop (storage prerequisite) |
| `cameraSetOutputEncodeParamR` | function | reversible_write | tail2 | CONSTRAINED | bitrate validated per resolution |
| `cameraSetPhotoFormatR` | function | destructive | tailair | DEFERRED_UNSAFE | destructive; not exercised by policy |
| `cameraSetPhotoQualityR` | function | reversible_write | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetRecordEncodeParamR` | function | reversible_write | tail2 | CONSTRAINED | bitrate validated per resolution; encode_format ignored |
| `cameraSetRecordResolutionR` | function | reversible_write | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetRecordSplitSizeR` | function | reversible_write | tailair | VERIFIED | 5 -> 2 -> 5 |
| `cameraSetTakePhotosR` | function | reversible_write | tailair+tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetVideoRecordR` | function | reversible_write | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `startNetworkScanImmediately` | function | command | generic | NOT_PRODUCT_RELEVANT | outside the Agent Camera MVP (other product form factor / platform) |
| `uvcVersion` | function | unknown | generic | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `videoFormatInfo` | function | destructive | generic | DEFERRED_UNSAFE | destructive; not exercised by policy |
| `aiSetGestureCtrlIndividualR` | function | reversible_write | tailair+tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraGetHdmiInfoR` | function | read_only | tailair | READBACK_VERIFIED | all fields 0 |
| `cameraGetLiveEncodeParamR` | function | read_only | tail2 | READBACK_VERIFIED | 1080p/4Mbps; no public setter |
| `cameraGetNdiRtspBitrateLevelR` | function | read_only | tailair | READBACK_VERIFIED | contract anomaly: returns 60000000 for an enum out-param |
| `cameraGetNdiRtspEncoderFormatR` | function | destructive | tailair | READBACK_VERIFIED | format 1 |
| `cameraGetSelectNdiOrRtspR` | function | read_only | tailair | READBACK_VERIFIED | select 0 |
| `cameraSetBootNdiEnabledR` | function | reversible_write | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetDisableSleepWithoutStreamU` | function | reversible_write | meet | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetHdmiInfoR` | function | reversible_write | tailair | UNSUPPORTED_TAIL2 | rc=0, readback unchanged |
| `cameraSetNdiRtspBitrateLevelR` | function | reversible_write | tailair | UNSUPPORTED_TAIL2 | rc=0, readback unchanged |
| `cameraSetNdiRtspEncoderFormatR` | function | destructive | tailair | UNSUPPORTED_TAIL2 | rc=0, readback unchanged |
| `cameraSetNdiRtspResolutionR` | function | reversible_write | tailair | ACCEPTED_UNPROVEN | no getter; not exercised |
| `cameraSetSelectNdiOrRtspR` | function | reversible_write | tailair | UNSUPPORTED_TAIL2 | rc=0, readback unchanged |
| `sysMgClearIndicatorStateR` | function | destructive | tail2+tailair | DEFERRED_UNSAFE | destructive; not exercised by policy |
| `sysMgSetIndicatorStateR` | function | reversible_write | tail2+tailair | ACCEPTED_UNPROVEN | not exercised |
| `cameraSetPowerCtrlActionR` | function | reversible_write | tailair | VERIFIED | PowerOff removes the device from PnP + SDK list |
| `aiAddZonePresetR` | function | reversible_write | tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `aiDelZonePresetR` | function | unknown | tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `aiGetZonePresetInfoWithIdR` | function | read_only | tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `aiGetZonePresetListR` | function | read_only | tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `aiGetZonePresetNameWithIdR` | function | read_only | tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `aiSetZonePresetNameWithIdR` | function | reversible_write | tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `aiTrgZonePresetR` | function | command | tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `aiUpdZonePresetUpdateR` | function | reversible_write | tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetBootModeU` | function | reversible_write | tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `DevConfigRangeCallback` | callback | reversible_write | generic | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `DevEventNotifyCallback` | callback | unknown | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `DevStatusCallback` | callback | unknown | generic | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `FastDevStatusCallback` | callback | unknown | generic | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `RxDataCallback` | callback | unknown | generic | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `RxDataWithLenCallback` | callback | unknown | generic | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `aiGetAiStatusR` | function | read_only | tailair+tiny | READBACK_VERIFIED | ai_main_mode / ai_sub_mode |
| `cameraGetBootStatus` | function | read_only | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `cameraGetCameraStatusU` | function | read_only | generic | ACCEPTED_UNPROVEN | callable; union layout undocumented |
| `cameraSetBootStatus` | function | reversible_write | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetDevRunStatusR` | function | reversible_write | generic | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraStatus` | function | unknown | generic | ACCEPTED_UNPROVEN | callable; union layout undocumented |
| `devChangedCallback` | callback | unknown | generic | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `devCheckPermisionCallback` | callback | unknown | generic | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `devConnectFailedCallback` | callback | unknown | generic | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `devSnInfoCallback` | callback | unknown | generic | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `devWakeUpCallback` | callback | unknown | generic | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `enableDevStatusCallback` | function | reversible_write | generic | VERIFIED | required to arm the callback |
| `fastNextRefreshDevStatus` | function | read_only | generic | ACCEPTED_UNPROVEN | callable; fast callback never fires |
| `nextRefreshDevStatus` | function | read_only | generic | VERIFIED | triggers the ordinary callback |
| `setDevChangedCallback` | function | reversible_write | generic | ACCEPTED_UNPROVEN | registered, 1 initial event; hotplug not exercised |
| `setDevConnectFailedCallback` | function | reversible_write | generic | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `setDevEventNotifyCallbackFunc` | function | reversible_write | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `setDevStatusCallbackFunc` | function | reversible_write | generic | VERIFIED | ~2 s cadence after nextRefreshDevStatus |
| `setFastDevStatusCallbackFunc` | function | reversible_write | generic | UNSUPPORTED_TAIL2 | 0 events in 50 s+ |
| `aiDelSelectedTargetR` | function | unknown | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `aiSetAiAutoZoomR` | function | reversible_write | tailair+tiny | ACCEPTED_UNPROVEN | rc=0, no readback |
| `aiSetSelectBiggestTarget` | function | reversible_write | tailair | ACCEPTED_UNPROVEN | rc=0, doc=tailair |
| `aiSetSelectCentralTarget` | function | reversible_write | tailair | ACCEPTED_UNPROVEN | rc=0, doc=tailair |
| `aiSetSelectTargetByBox` | function | reversible_write | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `aiSetSelectedTargetR` | function | reversible_write | tail2 | VERIFIED | rc + physical + visual |
| `aiSetTargetSelectR` | function | reversible_write | tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `aiSetTargetViewTypeR` | function | reversible_write | tail2 | ACCEPTED_UNPROVEN | 12 values rc=0, no state/visual effect |
| `aiSetTargetZoomTypeR` | function | reversible_write | tail2 | READBACK_VERIFIED | ai_sub_mode reflects; visual unchanged |
| `cameraGetRangeZoomAbsoluteR` | function | read_only | meet+tailair+tiny | VERIFIED | readback |
| `cameraGetZoomAbsoluteR` | function | read_only | meet+tailair+tiny | VERIFIED | readback |
| `cameraSetAutoFramingModeU` | function | reversible_write | meet | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetRoiTarget` | function | reversible_write | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `cameraSetZoomAbsoluteR` | function | reversible_write | meet+tail2+tailair+tiny | VERIFIED | rc + readback + visual (slow async ramp) |
| `cameraSetZoomStopR` | function | reversible_write | tailair | UNSUPPORTED_TAIL2 | measured no effect |
| `cameraSetZoomWithSpeedAbsoluteR` | function | reversible_write | tailair+tiny | UNSUPPORTED_TAIL2 | measured no effect |
| `cameraSetZoomWithSpeedRelativeR` | function | reversible_write | tailair | UNSUPPORTED_TAIL2 | measured no effect |
| `normalizedZoom` | function | unknown | generic | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `aiGetLimitedZoneTrackAutoSelectR` | function | read_only | tiny | UNSUPPORTED_TAIL2 | rc -1 |
| `aiGetLimitedZoneTrackEnabledR` | function | read_only | tiny | UNSUPPORTED_TAIL2 | rc -1 |
| `aiGetLimitedZoneTrackInitPosR` | function | read_only | tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (read path unproven on Tail2) |
| `aiGetLimitedZoneTrackPitchMaxR` | function | read_only | tiny | UNSUPPORTED_TAIL2 | rc -1 |
| `aiGetLimitedZoneTrackPitchMinR` | function | read_only | tiny | UNSUPPORTED_TAIL2 | rc -1 |
| `aiGetLimitedZoneTrackYawMaxR` | function | read_only | tiny | UNSUPPORTED_TAIL2 | rc -1 |
| `aiGetLimitedZoneTrackYawMinR` | function | read_only | tiny | UNSUPPORTED_TAIL2 | rc -1 |
| `aiRstLimitedZoneTrackInitPosR` | function | destructive | tiny | DEFERRED_UNSAFE | destructive; not exercised by policy |
| `aiRstLimitedZoneTrackPitchMaxR` | function | destructive | tiny | DEFERRED_UNSAFE | destructive; not exercised by policy |
| `aiRstLimitedZoneTrackPitchMinR` | function | destructive | tiny | DEFERRED_UNSAFE | destructive; not exercised by policy |
| `aiRstLimitedZoneTrackYawMaxR` | function | destructive | tiny | DEFERRED_UNSAFE | destructive; not exercised by policy |
| `aiRstLimitedZoneTrackYawMinR` | function | destructive | tiny | DEFERRED_UNSAFE | destructive; not exercised by policy |
| `aiSetAiTrackModeEnabledR` | function | reversible_write | tail2+tailair+tiny | ACCEPTED_UNPROVEN | rc=0, does not change ai_main_mode |
| `aiSetLimitedZoneTrackAutoSelectR` | function | reversible_write | tiny | evidence_insufficient | rc=0, no readback |
| `aiSetLimitedZoneTrackEnabledR` | function | reversible_write | tiny | evidence_insufficient | rc=0, no readback, no effect |
| `aiSetLimitedZoneTrackInitPosR` | function | reversible_write | tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `aiSetLimitedZoneTrackPitchMaxR` | function | reversible_write | tiny | evidence_insufficient | rc=0, no readback |
| `aiSetLimitedZoneTrackPitchMinR` | function | reversible_write | tiny | evidence_insufficient | rc=0, no readback |
| `aiSetLimitedZoneTrackYawMaxR` | function | reversible_write | tiny | evidence_insufficient | rc=0, no readback |
| `aiSetLimitedZoneTrackYawMinR` | function | reversible_write | tiny | evidence_insufficient | rc=0, no readback |
| `aiSetTrackSpeedTypeR` | function | reversible_write | tailair | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
| `aiSetTrackingModeR` | function | reversible_write | tiny | evidence_insufficient | probe op added, not closed |
| `aiSetZoneTrackGimbalEnabledR` | function | reversible_write | tiny | evidence_insufficient | probe op added, not closed |
| `aiSetZoneTrackStateR` | function | reversible_write | tailair+tiny | evidence_insufficient | probe op added, not closed |
| `aiTrgLimitedZoneTrackInitPosR` | function | command | tiny | DOC_OTHER_PRODUCT | documented for another product, not exercised (no Tail2 support claim) |
