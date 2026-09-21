"""Inspect the locally supplied SDK without copying headers into the repository."""
import argparse
import hashlib
import json
from pathlib import Path

SYMBOLS = {
    "target.select": "aiSetSelectedTargetR",
    "framing.set": "aiSetTargetZoomTypeR",
    "media.control": "cameraSetMediaOperateParamR",
    "media.query": "cameraGetMediaOperateParamR",
    "track.compatibility_probe": "aiSetEnabledR",
    "look.compatibility_probe": "gimbalSpeedCtrlR",
    "look.query": "gimbalGetAttitudeInfoR",
    "position.list": "aiGetGimbalPresetListR",
    "position.save": "aiAddGimbalPresetR",
    "position.recall": "aiTrgGimbalPresetR",
    "status.query": "aiGetAiStatusR",
    "candidates.declaration_only": "DevCDCNotifyTypeAiTarget",
}


def audit(root: Path) -> dict:
    header=root/"include/dev/dev.hpp"
    text=header.read_text(encoding="utf-8-sig").splitlines()
    return {"package_label": root.name, "header_sha256": hashlib.sha256(header.read_bytes()).hexdigest(),
            "hardware_tested": False, "native_candidates": "UNKNOWN",
            "symbols": {name: {"symbol": symbol,"declaration_lines": [i for i,line in enumerate(text,1) if symbol in line]}
                        for name,symbol in SYMBOLS.items()},
            "note":"Declaration presence does not establish firmware/UVC support, payload semantics, or completion."}


if __name__=="__main__":
    p=argparse.ArgumentParser(); p.add_argument("--sdk",type=Path,required=True); p.add_argument("--out",type=Path,default=Path(".local/sdk-audit.json"))
    a=p.parse_args(); result=audit(a.sdk.resolve()); a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8"); print(a.out)
