"""Pre-publication guard for tracked source only. Not a complete secret scanner."""
import pathlib
import re
import subprocess

root=pathlib.Path(__file__).resolve().parents[1]
paths=subprocess.check_output(["git","ls-files","-z"],cwd=root).decode().split("\0")
blocked=[]
for p in filter(None,paths):
    parts=pathlib.PurePosixPath(p)
    if any(x in {"vendor","private",".local","build","include"} for x in parts.parts) or parts.suffix.lower() in {
        ".dll",".lib",".so",".dylib",".pdb",".exe",".jpg",".jpeg",".png",".mp4",".wav",".zip",".jsonl"}:
        blocked.append(p); continue
    text=(root/p).read_text(encoding="utf-8")
    patterns=[r"-----BEGIN [A-Z ]*PRIVATE KEY-----", r"\bgh[pousr]_[A-Za-z0-9]{30,}\b", r"\bsk-[A-Za-z0-9_-]{24,}\b"]
    if any(re.search(x,text) for x in patterns): blocked.append(p)
if blocked: raise SystemExit("Review before publication: "+", ".join(blocked))
print("Tracked-source publication check passed; manual review still required.")
