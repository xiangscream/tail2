# Tail2 SDK Media Surface (Wave C, C0 census)

2026-09-21 · branch `feature/sdk-sweep-c` · baseline `main @ 9d14848d1ecd944f541fbdc724c9865fcff7e64b`

Source: the completeness-gated census (`docs/Tail2_SDK_CENSUS.md`, 490 symbols,
unmatched 0) plus header signatures. **Doc applicability is a hint, not a Tail2
support claim** — Wave A/B proved it wrong in both directions repeatedly
(`cameraSetPowerCtrlActionR` is documented `tail air` yet powers off a Tail2).

Uniform evidence standard for Wave C:

```
Request → SDK acceptance → Expected Effect Predicate → Evidence → Verdict
```

Media-specific predicate ladder (never collapse these):

```
request accepted
  → operation state actually changed
  → media actually produced
  → artifact finalized
  → artifact accessible
```

`rc=0` never upgrades a row above `ACCEPTED_UNPROVEN`.

## 1. Stream IDs (`DevMediaStreamId`, doc applicability = tail2)

| id | stream | media_operation reachable | notes / prerequisite |
|---|---|---|---|
| 0 | Auto | yes | device picks a stream; ambiguous, use only as a probe |
| 1 | Record | yes | needs storage (SD) for artifact-level closure |
| 2 | Capture | yes | getter already known to fail on Tail2 (M0) |
| 3 | Live | yes | network/output target required |
| 4 | Rtsp | yes | network prerequisite |
| 5 | Ndi | yes | network prerequisite; boot-time enable is persistent |
| 6 | Srt | yes | network prerequisite + address/key (local only) |
| 7 | Uvc | yes | the stream the MVP already owns |
| 8 | Kcp | yes | other transport, low product value |
| 9 | Hdmi | yes | physical sink required for effect |
| 10 | Sdi | yes | physical sink required |
| 16 | RecordSub | yes | sub-stream, see 1 |
| 17 | LiveSub | yes | see 3 |
| 18 | NdiSub | yes | see 5 |

## 2. Operation / config families

| family | Tail2-claimed symbols | other-product symbols (test anyway) |
|---|---|---|
| stream operation | `cameraSet/GetMediaOperateParamR` (tail2) | — |
| record encode | `cameraSet/GetRecordEncodeParamR` (tail2) | `cameraSetRecordResolutionR`, `cameraGet/SetRecordSplitSizeR`, `cameraGet/SetMainVideoEncoderFormatR`, `cameraGet/SetMainVideoBitrateLevelR` (tailair) |
| output encode | `cameraSet/GetOutputEncodeParamR` (tail2) | `cameraSetNdiRtspResolutionR`, `cameraGet/SetNdiRtspBitrateLevelR`, `cameraGet/SetNdiRtspEncoderFormatR` (tailair) |
| live encode | `cameraGetLiveEncodeParamR` (tail2, **getter only → setter `NO_PUBLIC_PATH`**) | — |
| codec enum | `DevVideoEncoderFormat` (tail2+tailair): Auto/H264/H265/MJPEG/AV1/NdiFull | — |
| resolution enum | `DevVideoResType` (generic, 24 values incl. 4K/1080p/720p variants) | — |
| split / bit level | `DevVideoSplitSizeType`, `DevVideoBitLevelType` | — |
| selector | `cameraGet/SetSelectNdiOrRtspR` (tailair) | `cameraSetBootNdiEnabledR` (**persistent → DEFERRED_UNSAFE**) |
| physical output | `cameraGet/SetHdmiInfoR` (tailair) | `DevMediaParamSdiMode`, `DevMediaParamSdi` |

## 3. Storage / artifact retrieval

| path | symbol | applicability | disposition |
|---|---|---|---|
| device file download | `startFileDownloadAsync`, `setFileDownloadCallback`, `localFilePath`, `localFileMiniPath` | meet+tiny | **not documented for Tail2** → artifact retrieval for device-native record is `NO_PUBLIC_PATH` until proven |
| MTP / SD info | `MtpFileType`, `MtpFileInfo`, `SDCardStatus` | generic | readback probes only |
| split size | `cameraGet/SetRecordSplitSizeR` | tailair | reversible write + readback |

Policy: **no writable storage medium ⇒ do not call it UNSUPPORTED.** Record/capture
failures without storage are `prerequisite_unmet → evidence_insufficient`.
Never format/delete user media.

## 4. Status / callback paths

| path | applicability | Wave B status |
|---|---|---|
| ordinary `DevStatusCallback` | generic | **works (~2 s cadence)** — preferred evidence channel |
| `FastDevStatusCallback` | generic | **never delivered on Tail2** (Wave B) |
| `DevRecordStatus` / `DevLiveStreamStatus` enums | tailair | readback only until a media op is active |
| `cameraStatus()` union | generic | callable, **layout unparsed** (no documented Tail2 payload) |
| media event notify | `DevEventNotifyCallback` (tailair) | not exercised; payload contract unknown |

Authoritative-evidence rule: when a callback and a getter disagree, prefer the one
that can be tied to an artifact/stream observation; record both.

## 5. Planned C1–C5 experiments (each with an expected-effect predicate)

| wave | experiment | predicate |
|---|---|---|
| C1 | record/output encode get→set→readback→restore | typed readback matches after a bounded settle; record settling time |
| C1 | live encode getter | readback only; no setter ⇒ `NO_PUBLIC_PATH` |
| C2 | `Record` start → status/readback → artifact → stop | recording state changes + artifact exists and reopens; needs storage |
| C2 | `Capture` start → new artifact after request | new artifact appears after the request (getter known to fail) |
| C3 | UVC closed → native op; UVC open → native op; native active → UVC open; stop → UVC recovery | one resource succeeds while the other loses availability or cannot transition; record frame availability/fps/epoch |
| C4 | RTSP/NDI select + config readback; receiver actually receives | receiver bytes/frames, not `rc=0` |
| C4 | SRT config path | address/key local only; receiver-based predicate; network-unmet ⇒ `prerequisite_unmet` |
| C4 | HDMI/SDI getters + reversible config | readback closed loop; no sink ⇒ at most `READBACK_VERIFIED` |
| C5 | media operation vs ordinary callback | callback count + timestamp tied to the operation; media-specific callback delivery vs unknown payload |

## 6. Probe ops required for C1–C2 (to add next, no Primitive API)

`media.encode.record.get/set`, `media.encode.output.get/set`, `media.encode.live.get`,
`media.op.get/set` (stream, operation), `media.split.get/set`, plus reusing
`record.start/stop`, `capture.device`, `status.callbacks.get`.

## 7. Explicitly out of scope for Wave C

- PowerOff/Reboot lifecycle (already verified; not repeated).
- Any new Primitive API or Runtime feature; the object-loss watchdog stays a
  registered requirement only.
- Purchasing/attaching sinks (HDMI/SDI capture) for completeness.
