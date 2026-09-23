"""Wave D closure table.

Assigns an explicit disposition to every function/callback in the Tail2-relevant
families, so that no architecture-significant symbol is left as a bare [U].

Inputs: the sanitized census JSON (local) and the measured results encoded below
(which mirror docs/Tail2_SDK_TRUTH_MAP.md). Emits sanitized markdown.

Usage: python tools/closure_table.py --census .local/sdk-sweep/sdk-census.json
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

# Measured on Tail2 (fw 7.2.9.41) during Waves A/B/C. status -> basis
MEASURED: dict[str, tuple[str, str]] = {
    # A1 gimbal / look
    "aiSetGimbalMotorAngleR": ("VERIFIED", "rc + readback + visual, 3 reps"),
    "gimbalSetSpeedPositionR": ("VERIFIED", "rc + readback"),
    "aiSetGimbalSpeedCtrlR": ("VERIFIED", "rc + readback + visual"),
    "aiSetGimbalStop": ("VERIFIED", "residual <= 0.01 deg"),
    "gimbalSpeedCtrlR": ("VERIFIED", "legacy baseline, rc + physical"),
    "gimbalGetAttitudeInfoR": ("VERIFIED", "readback (intermittent rc=-1)"),
    "aiGetGimbalStateR": ("READBACK_VERIFIED", "euler + motor + velocity"),
    "aiGetGimbalParaR": ("READBACK_VERIFIED", "float overload; bool overload is a trap"),
    "aiSetGimbalParaR": ("CONSTRAINED", "PanReverse ok; PresetSpeed 0.5 ok / 2.0 ignored; limits stored not enforced"),
    "aiGetGimbalBootPosR": ("READBACK_VERIFIED", "id 0, pose 0/0/0"),
    "aiTrgGimbalBootPosR": ("VERIFIED", "yaw10/pitch5 -> exactly 0/0"),
    "aiGetGimbalPresetListR": ("READBACK_VERIFIED", "len 0"),
    "aiSetGimbalYawDirReverseR": ("ACCEPTED_UNPROVEN", "rc=0, no readback/visual effect"),
    # A2 ai control
    "aiGetControlParaR": ("READBACK_VERIFIED", "all 24 params"),
    "aiSetControlParaR": ("VERIFIED", "23/24 writable + readback; Pan/PitchLocked verified behaviourally"),
    # A3 target / view / zoom
    "aiSetSelectedTargetR": ("VERIFIED", "rc + physical + visual"),
    "aiSetTargetZoomTypeR": ("READBACK_VERIFIED", "ai_sub_mode reflects; visual unchanged"),
    "aiSetTargetViewTypeR": ("ACCEPTED_UNPROVEN", "12 values rc=0, no state/visual effect"),
    "aiSetSelectBiggestTarget": ("ACCEPTED_UNPROVEN", "rc=0, doc=tailair"),
    "aiSetSelectCentralTarget": ("ACCEPTED_UNPROVEN", "rc=0, doc=tailair"),
    "aiSetAiAutoZoomR": ("ACCEPTED_UNPROVEN", "rc=0, no readback"),
    "aiSetAiTrackModeEnabledR": ("ACCEPTED_UNPROVEN", "rc=0, does not change ai_main_mode"),
    "aiSetEnabledR": ("VERIFIED", "AI on/off behaviour"),
    "aiGetAiStatusR": ("READBACK_VERIFIED", "ai_main_mode / ai_sub_mode"),
    "cameraSetZoomAbsoluteR": ("VERIFIED", "rc + readback + visual (slow async ramp)"),
    "cameraGetZoomAbsoluteR": ("VERIFIED", "readback"),
    "cameraGetRangeZoomAbsoluteR": ("VERIFIED", "readback"),
    "cameraSetZoomStopR": ("UNSUPPORTED_TAIL2", "measured no effect"),
    "cameraSetZoomWithSpeedRelativeR": ("UNSUPPORTED_TAIL2", "measured no effect"),
    "cameraSetZoomWithSpeedAbsoluteR": ("UNSUPPORTED_TAIL2", "measured no effect"),
    # B1 gesture
    "aiGetGestureParaR": ("READBACK_VERIFIED", "9 params"),
    "aiSetGestureParaR": ("READBACK_VERIFIED", "writable + readback"),
    "aiGetGestureTrackParaR": ("READBACK_VERIFIED", "9 params"),
    "aiSetGestureTrackParaR": ("READBACK_VERIFIED", "writable + readback"),
    # B2 iq
    "cameraGetAutoFocusModeR": ("READBACK_VERIFIED", "readback"),
    "cameraSetAutoFocusModeR": ("READBACK_VERIFIED", "writable + readback"),
    "cameraGetAFCTrackModeR": ("READBACK_VERIFIED", "readback"),
    "cameraSetAFCTrackModeR": ("READBACK_VERIFIED", "writable + readback"),
    "cameraGetFocusAbsolute": ("READBACK_VERIFIED", "focus + auto_focus"),
    "cameraGetWhiteBalanceR": ("READBACK_VERIFIED", "readback"),
    "cameraSetWhiteBalanceR": ("VERIFIED", "readback + strong visual (tungsten blue cast)"),
    "cameraGetRangeWhiteBalanceR": ("READBACK_VERIFIED", "readback"),
    "cameraGetWdrR": ("READBACK_VERIFIED", "readback (async)"),
    "cameraSetWdrR": ("READBACK_VERIFIED", "writable, readback lags seconds"),
    "cameraSetFaceAER": ("ACCEPTED_UNPROVEN", "probe op exists, not closed"),
    "cameraSetExposureModeR": ("ACCEPTED_UNPROVEN", "probe op exists, not closed"),
    "cameraSetPAEEvBiasR": ("ACCEPTED_UNPROVEN", "probe op exists, not closed"),
    # B3 preset / boot / gimbal config (covered above)
    # B4 status / callbacks
    "setDevStatusCallbackFunc": ("VERIFIED", "~2 s cadence after nextRefreshDevStatus"),
    "enableDevStatusCallback": ("VERIFIED", "required to arm the callback"),
    "setFastDevStatusCallbackFunc": ("UNSUPPORTED_TAIL2", "0 events in 50 s+"),
    "setDevChangedCallback": ("ACCEPTED_UNPROVEN", "registered, 1 initial event; hotplug not exercised"),
    "cameraStatus": ("ACCEPTED_UNPROVEN", "callable; union layout undocumented"),
    "cameraGetCameraStatusU": ("ACCEPTED_UNPROVEN", "callable; union layout undocumented"),
    "nextRefreshDevStatus": ("VERIFIED", "triggers the ordinary callback"),
    "fastNextRefreshDevStatus": ("ACCEPTED_UNPROVEN", "callable; fast callback never fires"),
    # C1/C2 media
    "cameraGetRecordEncodeParamR": ("READBACK_VERIFIED", "4K/60Mbps/H264; fps is milli-fps"),
    "cameraSetRecordEncodeParamR": ("CONSTRAINED", "bitrate validated per resolution; encode_format ignored"),
    "cameraGetOutputEncodeParamR": ("READBACK_VERIFIED", "night_flag changes readback"),
    "cameraSetOutputEncodeParamR": ("CONSTRAINED", "bitrate validated per resolution"),
    "cameraGetLiveEncodeParamR": ("READBACK_VERIFIED", "1080p/4Mbps; no public setter"),
    "cameraGetRecordSplitSizeR": ("VERIFIED", "readback"),
    "cameraSetRecordSplitSizeR": ("VERIFIED", "5 -> 2 -> 5"),
    "cameraGetMediaOperateParamR": ("READBACK_VERIFIED", "per-stream readback"),
    "cameraSetMediaOperateParamR": ("CONSTRAINED", "accepted; Record state stays Stop (storage prerequisite)"),
    # C4 output
    "cameraGetSelectNdiOrRtspR": ("READBACK_VERIFIED", "select 0"),
    "cameraSetSelectNdiOrRtspR": ("UNSUPPORTED_TAIL2", "rc=0, readback unchanged"),
    "cameraGetNdiRtspBitrateLevelR": ("READBACK_VERIFIED", "contract anomaly: returns 60000000 for an enum out-param"),
    "cameraSetNdiRtspBitrateLevelR": ("UNSUPPORTED_TAIL2", "rc=0, readback unchanged"),
    "cameraGetNdiRtspEncoderFormatR": ("READBACK_VERIFIED", "format 1"),
    "cameraSetNdiRtspEncoderFormatR": ("UNSUPPORTED_TAIL2", "rc=0, readback unchanged"),
    "cameraGetHdmiInfoR": ("READBACK_VERIFIED", "all fields 0"),
    "cameraSetHdmiInfoR": ("UNSUPPORTED_TAIL2", "rc=0, readback unchanged"),
    "cameraSetNdiRtspResolutionR": ("ACCEPTED_UNPROVEN", "no getter; not exercised"),
    # lifecycle
    "cameraSetPowerCtrlActionR": ("VERIFIED", "PowerOff removes the device from PnP + SDK list"),
    "sysMgSetIndicatorStateR": ("ACCEPTED_UNPROVEN", "not exercised"),
    # limited zone (sample-discovered family)
    "aiGetLimitedZoneTrackEnabledR": ("UNSUPPORTED_TAIL2", "rc -1"),
    "aiGetLimitedZoneTrackAutoSelectR": ("UNSUPPORTED_TAIL2", "rc -1"),
    "aiGetLimitedZoneTrackYawMinR": ("UNSUPPORTED_TAIL2", "rc -1"),
    "aiGetLimitedZoneTrackYawMaxR": ("UNSUPPORTED_TAIL2", "rc -1"),
    "aiGetLimitedZoneTrackPitchMinR": ("UNSUPPORTED_TAIL2", "rc -1"),
    "aiGetLimitedZoneTrackPitchMaxR": ("UNSUPPORTED_TAIL2", "rc -1"),
    "aiSetLimitedZoneTrackEnabledR": ("evidence_insufficient", "rc=0, no readback, no effect"),
    "aiSetLimitedZoneTrackAutoSelectR": ("evidence_insufficient", "rc=0, no readback"),
    "aiSetLimitedZoneTrackYawMinR": ("evidence_insufficient", "rc=0, no readback"),
    "aiSetLimitedZoneTrackYawMaxR": ("evidence_insufficient", "rc=0, no readback"),
    "aiSetLimitedZoneTrackPitchMinR": ("evidence_insufficient", "rc=0, no readback"),
    "aiSetLimitedZoneTrackPitchMaxR": ("evidence_insufficient", "rc=0, no readback"),
    "aiSetTrackingModeR": ("evidence_insufficient", "probe op added, not closed"),
    "aiSetZoneTrackStateR": ("evidence_insufficient", "probe op added, not closed"),
    "aiSetZoneTrackGimbalEnabledR": ("evidence_insufficient", "probe op added, not closed"),
}

# Product-form-factor families that are outside the Agent Camera MVP.
NOT_RELEVANT_HINTS = ("tws", "wirelessmic", "bluetooth", "wifi", "ethernet", "network",
                      "upgrade", "firmware", "zone preset", "hdmi box", "ndi box", "kcp")
# Destructive / persistent families never exercised.
DESTRUCTIVE_OK = {"aiRstGimbalBootPosR", "gimbalRstPosR", "aiRstLimitedZoneTrackInitPosR",
                  "aiRstLimitedZoneTrackYawMinR", "aiRstLimitedZoneTrackYawMaxR",
                  "aiRstLimitedZoneTrackPitchMinR", "aiRstLimitedZoneTrackPitchMaxR",
                  "cameraSetRestoreFactorySettingsR", "sysMgClearIndicatorStateR"}

HIGH_FAMILIES = ("gimbal", "target", "track", "ai", "camera", "media", "media.output",
                 "iq", "gesture", "preset", "status", "power")


def disposition(entry: dict) -> tuple[str, str]:
    name = entry["name"]
    if name in MEASURED:
        return MEASURED[name]
    if entry.get("risk") == "destructive":
        return "DEFERRED_UNSAFE", "destructive; not exercised by policy"
    low = (name + " " + entry.get("applicability_hint", "")).lower()
    if any(h in low for h in NOT_RELEVANT_HINTS):
        return "NOT_PRODUCT_RELEVANT", "outside the Agent Camera MVP (other product form factor / platform)"
    if "tail2" in entry.get("applicability_hint", ""):
        return "ACCEPTED_UNPROVEN", "Tail2-claimed in the header; not exercised by this sweep"
    if entry.get("risk") == "read_only":
        return "DOC_OTHER_PRODUCT", "documented for another product, not exercised (read path unproven on Tail2)"
    return "DOC_OTHER_PRODUCT", "documented for another product, not exercised (no Tail2 support claim)"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--census", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    data = json.loads(args.census.read_text(encoding="utf-8"))
    rows: dict[str, list[dict]] = {}
    for entry in data["symbols"]:
        if entry["kind"] not in ("function", "callback"):
            continue
        if entry["family"] not in HIGH_FAMILIES:
            continue
        status, basis = disposition(entry)
        rows.setdefault(entry["family"], []).append({**entry, "status": status, "basis": basis})
    lines = ["| symbol | kind | risk | doc applicability | Wave D disposition | basis |",
             "|---|---|---|---|---|---|"]
    counts: dict[str, int] = {}
    for family in sorted(rows):
        for entry in sorted(rows[family], key=lambda item: item["name"]):
            counts[entry["status"]] = counts.get(entry["status"], 0) + 1
            lines.append(f"| `{entry['name']}` | {entry['kind']} | {entry['risk']} | "
                         f"{entry['applicability_hint']} | {entry['status']} | {entry['basis']} |")
    markdown = "\n".join(lines) + "\n"
    print("dispositions:", json.dumps(counts, sort_keys=True))
    if args.out:
        args.out.write_text(markdown, encoding="utf-8")
        print("wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
