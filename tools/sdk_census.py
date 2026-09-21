"""Static census of the locally supplied OBSBOT SDK.

Local-only raw output goes to ``.local/sdk-sweep/``. This tool never copies
proprietary header bodies or prose into the repository: it records symbol
names, high-level signatures, enum member names/values and our own
classification.

Usage:
    python tools/sdk_census.py --sdk "<path to libdev root>" [--out .local/sdk-sweep]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath

HEADER_SUFFIXES = (".h", ".hpp", ".hh", ".hxx", ".h++", ".inl")
SOURCE_SUFFIXES = (".c", ".cc", ".cpp", ".cxx", ".c++")
DOC_SUFFIXES = (".md", ".txt", ".rst", ".html", ".htm", ".pdf")
DOC_NAMES = ("readme", "license", "licence", "changelog", "changes", "notice", "version")
BINARY_SUFFIXES = (".dll", ".lib", ".so", ".dylib", ".pdb", ".exe", ".a", ".obj", ".exp", ".zip")
BUILD_SUFFIXES = (".cmake", ".mk", ".pc", ".json", ".xml", ".yml", ".yaml", ".toml", ".cfg")
BUILD_NAMES = ("cmakelists", "makefile", "meson.build", "package")
SAMPLE_DIR_HINTS = ("sample", "example", "demo", "app")

DESTRUCTIVE_WORDS = frozenset((
    "format", "delete", "erase", "reset", "rst", "upgrade", "download", "restore",
    "factory", "clear", "remove", "unbind", "rename", "attack",
))
GETTER_WORDS = frozenset(("get", "is", "has", "query", "read", "next", "fastnext", "list"))
WRITE_WORDS = frozenset(("set", "update", "config", "apply", "save", "add", "enable", "disable"))
COMMAND_WORDS = frozenset(("trg", "trigger", "start", "stop", "ctrl", "switch"))

FAMILY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("media.output", ("rtsp", "ndi", "srt", "hdmi", "live", "stream")),
    ("media", ("record", "capture", "video", "media", "uvc", "encode", "photo")),
    ("storage", ("mtp", "sdcard", "file", "storage", "download", "upload")),
    ("iq", ("whitebalance", "wb", "exposure", "shutter", "aperture", "iso", "gamma",
            "night", "wdr", "style", "image", "ae", "afc", "autofocus", "focus")),
    ("audio", ("audio", "buzzer", "sound", "tws", "voice", "mic")),
    ("gesture", ("gesture", "hand", "remote")),
    ("track", ("track", "aimain", "aisub", "foretrack")),
    ("target", ("target", "select", "zoom", "framing", "roi")),
    ("gimbal", ("gimbal", "attitude", "motor", "pan", "pitch", "yaw")),
    ("network", ("wifi", "bluetooth", "bt", "ip", "ethernet", "network", "net")),
    ("power", ("power", "battery", "charge", "usb")),
    ("upgrade", ("upgrade", "firmware", "fw")),
    ("status", ("status", "event", "notify", "callback", "cdc", "refresh")),
    ("preset", ("preset", "bootpos", "boot")),
    ("device", ("dev", "device")),
    ("camera", ("camera",)),
    ("ai", ("ai",)),
)

APPLICABILITY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("tail2", ("tail2", "tail 2", "tail2s", "tail 2s")),
    ("tailair", ("tail air", "tailair")),
    ("tiny", ("tiny",)),
    ("meet", ("meet",)),
    ("me", ("obsbotprodme",)),
    ("hdmibox", ("hdmi box", "hdmibox")),
    ("ndibox", ("ndi box", "ndibox")),
)

def _words(name: str) -> list[str]:
    """Split a camelCase / PascalCase SDK symbol into lowercase words."""
    parts = re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+", name)
    return [part.lower() for part in parts]


def _strip_comment(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text)
    text = re.sub(r"//.*$", " ", text)
    return text


def _comment_text(raw: str) -> str | None:
    """Return the comment text when a line is (or starts as) a comment."""
    stripped = raw.strip()
    if stripped.startswith(("/**", "/*", "///", "//", "*")):
        return stripped
    return None


def _doc_product_hint(doc: str) -> str:
    low = doc.lower()
    hits = [label for label, keys in APPLICABILITY_RULES if any(k in low for k in keys)]
    if not hits:
        return "generic"
    return "+".join(sorted(hits))


def _family(name: str, doc: str) -> str:
    low = (name + " " + doc).lower()
    for label, keys in FAMILY_RULES:
        if any(k in low for k in keys):
            return label
    return "other"


def _risk(name: str) -> str:
    words = _words(name)
    if any(word in DESTRUCTIVE_WORDS for word in words):
        return "destructive"
    if any(word in GETTER_WORDS for word in words):
        return "read_only"
    if any(word in WRITE_WORDS for word in words):
        return "reversible_write"
    if any(word in COMMAND_WORDS for word in words):
        return "command"
    return "unknown"


def _clean_statement(statement: str) -> str:
    """Drop leading access specifiers so 'public: typedef ...' parses."""
    return re.sub(r"^(?:(?:public|private|protected)\s*:\s*)+", "", statement).strip()


def _split_statements(lines: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Join continued C++ statements (a declaration may span several lines)."""
    out: list[tuple[int, str]] = []
    buffer = ""
    start = 0
    for number, raw in lines:
        code = _strip_comment(raw).strip()
        if not code:
            continue
        if not buffer:
            start = number
        buffer = (buffer + " " + code).strip()
        if buffer.endswith(";") or buffer.endswith("{") or buffer.endswith("}"):
            out.append((start, _clean_statement(re.sub(r"\s+", " ", buffer))))
            buffer = ""
    if buffer:
        out.append((start, _clean_statement(re.sub(r"\s+", " ", buffer))))
    return out


def _parse_enum(lines: list[tuple[int, str]], index: int, doc: str,
                scope: str | None) -> tuple[dict, int]:
    number, raw = lines[index]
    header = _strip_comment(raw).strip()
    is_class = header.startswith("enum class")
    match = re.match(r"enum\s+(?:class\s+)?(\w+)?\s*(?::\s*([\w:]+))?\s*\{", header)
    name = match.group(1) if match and match.group(1) else f"<anonymous:{number}>"
    underlying = match.group(2) if match else None
    members: list[dict] = []
    body = header.split("{", 1)[1] if "{" in header else ""
    consumed = index + 1
    while True:
        if "}" in body:
            body = body.split("}", 1)[0]
            break
        if consumed >= len(lines):
            break
        current = _strip_comment(lines[consumed][1]).strip()
        body += " " + current
        consumed += 1
    for entry in body.split(","):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split("=", 1)
        member = parts[0].strip()
        if not member:
            continue
        value = parts[1].strip() if len(parts) > 1 else None
        members.append({"name": member, "value": value})
    return ({"kind": "enum", "scope": scope, "name": name, "enum_class": is_class,
             "underlying": underlying, "members": members, "line": number,
             "family": _family(name, ""), "applicability_hint": _doc_product_hint(doc)},
            consumed)


def _parse_struct(lines: list[tuple[int, str]], index: int, doc: str,
                  scope: str | None) -> tuple[dict, int]:
    number, raw = lines[index]
    header = _strip_comment(raw).strip()
    match = re.match(r"(?:typedef\s+)?(struct|union)\s*(\w+)?\s*\{", header)
    tag = match.group(1) if match else "struct"
    name = match.group(2) if match and match.group(2) else None
    is_typedef = header.startswith("typedef")
    depth = 1
    consumed = index + 1
    fields: list[str] = []
    pending = ""
    while consumed < len(lines) and depth > 0:
        code = _strip_comment(lines[consumed][1]).strip()
        consumed += 1
        if not code:
            continue
        for char in code:
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
        if depth <= 0:
            if name is None:
                alias = re.search(r"\}\s*(\w+)\s*;", code)
                if alias:
                    name = alias.group(1)
            continue
        if depth == 1:
            pending = (pending + " " + code).strip()
            if pending.endswith(";"):
                fields.append(re.sub(r"\s+", " ", pending).rstrip(";").strip())
                pending = ""
    if name is None:
        name = f"<anonymous:{number}>"
    return ({"kind": tag, "scope": scope, "name": name, "typedef": is_typedef,
             "fields": fields, "line": number, "family": _family(name, ""),
             "applicability_hint": _doc_product_hint(doc)}, consumed)


def _parse_typedef_function(statement: str, doc: str, scope: str | None,
                            line: int) -> dict | None:
    match = re.match(r"typedef\s+std::function<.*>\s*(\w+)\s*;", statement)
    if not match:
        return None
    return {"kind": "callback", "scope": scope, "name": match.group(1),
            "signature": statement.rstrip(";"), "line": line,
            "family": _family(match.group(1), ""),
            "applicability_hint": _doc_product_hint(doc)}


def _parse_method(statement: str, doc: str, scope: str | None, line: int) -> dict | None:
    if statement.startswith(("typedef", "using", "enum", "struct", "union", "class",
                             "friend", "template", "public:", "private:", "protected:")):
        return None
    body = statement
    for stop in ("{",):
        if body.endswith(stop):
            body = body[:-1].strip()
    body = body.rstrip(";").strip()
    if "(" not in body or ")" not in body:
        return None
    if "=" in body.split("(", 1)[0]:
        return None
    match = re.match(r"(?:\w[\w:<>,*&\s]*?\s+)?(\w+)\s*\((.*)\)\s*(const)?\s*$", body)
    if not match:
        return None
    name = match.group(1)
    return {"kind": "function", "scope": scope, "name": name,
            "signature": re.sub(r"\s+", " ", body), "line": line,
            "family": _family(name, ""), "applicability_hint": _doc_product_hint(doc)}


def _parse_class(lines: list[tuple[int, str]], index: int, doc: str,
                 scope: str | None) -> tuple[list[dict], int]:
    number, raw = lines[index]
    header = _strip_comment(raw).strip()
    if "{" not in header:
        return [], index + 1
    head = header.split("{", 1)[0].split(":", 1)[0]
    identifiers = re.findall(r"[A-Za-z_]\w*", head)
    if not identifiers or identifiers[0] != "class" or len(identifiers) < 2:
        return [], index + 1
    name = identifiers[-1]
    qualified = f"{scope}::{name}" if scope else name
    entries: list[dict] = [{"kind": "class", "scope": scope, "name": name,
                            "line": number, "family": _family(name, ""),
                            "applicability_hint": _doc_product_hint(doc)}]
    depth = header.count("{") - header.count("}")
    consumed = index + 1
    pending_doc = ""
    pending: list[tuple[int, str]] = []
    while consumed < len(lines) and depth > 0:
        line_number, line_raw = lines[consumed]
        text = _comment_text(line_raw)
        if text is not None:
            pending_doc = (pending_doc + " " + text).strip()
            consumed += 1
            continue
        code = _strip_comment(line_raw).strip()
        if not code:
            consumed += 1
            continue
        if code.startswith("enum"):
            parsed, consumed = _parse_enum(lines, consumed, pending_doc, qualified)
            entries.append(parsed)
            pending_doc = ""
            continue
        if code.startswith(("struct", "union")) or code.startswith("typedef struct"):
            parsed, consumed = _parse_struct(lines, consumed, pending_doc, qualified)
            entries.append(parsed)
            pending_doc = ""
            continue
        for char in code:
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
        if depth <= 0:
            break
        pending.append((line_number, line_raw))
        if code.endswith(";") or code.endswith("}"):
            statements = _split_statements(pending)
            for stmt_line, statement in statements:
                parsed = (_parse_typedef_function(statement, pending_doc, qualified, stmt_line)
                          or _parse_method(statement, pending_doc, qualified, stmt_line))
                if parsed:
                    entries.append(parsed)
            pending = []
            pending_doc = ""
        consumed += 1
    return entries, consumed


def _classify(relative: PurePosixPath) -> str:
    name = relative.name.lower()
    suffix = relative.suffix.lower()
    parents = [part.lower() for part in relative.parts[:-1]]
    in_sample = any(any(hint in part for hint in SAMPLE_DIR_HINTS) for part in parents)
    if ".so." in name or (not suffix and any(k in part for part in parents
                                             for k in ("release", "debug"))):
        return "binary"
    if suffix in HEADER_SUFFIXES:
        return "header"
    if suffix in SOURCE_SUFFIXES:
        return "sample_source" if in_sample else "source"
    if any(key in name for key in BUILD_NAMES) or suffix in BUILD_SUFFIXES:
        return "build"
    if suffix in DOC_SUFFIXES or any(key in name for key in DOC_NAMES):
        return "doc"
    if suffix in BINARY_SUFFIXES:
        return "binary"
    if suffix in BUILD_SUFFIXES:
        return "build"
    return "other"


def discover(root: Path) -> list[dict]:
    """Walk the whole SDK root and classify every file. The public surface is
    discovered, never assumed: the inventory is the proof of what exists."""
    root = root.resolve()
    entries: list[dict] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = PurePosixPath(path.relative_to(root).as_posix())
        kind = _classify(relative)
        entry = {"path": str(relative), "type": kind, "bytes": path.stat().st_size,
                 "parsed": False, "skip_reason": ""}
        if kind in ("header", "source", "sample_source", "doc", "build"):
            entry["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            if kind == "doc":
                entry["skip_reason"] = "inventory only: proprietary prose is not parsed or copied"
            elif kind == "build":
                entry["skip_reason"] = "build metadata: inventoried, not parsed"
        else:
            entry["skip_reason"] = "binary artifact" if kind == "binary" else "unclassified"
        entries.append(entry)
    return entries


def _parse_unit(lines: list[tuple[int, str]], relative: str) -> list[dict]:
    entries: list[dict] = []
    index = 0
    doc = ""
    while index < len(lines):
        _, raw = lines[index]
        comment = _comment_text(raw)
        if comment is not None:
            doc = (doc + " " + comment).strip()
            index += 1
            continue
        code = _strip_comment(raw).strip()
        if code.startswith("enum"):
            parsed, index = _parse_enum(lines, index, doc, None)
            entries.append(parsed)
            doc = ""
            continue
        if code.startswith(("struct", "union")) or code.startswith("typedef struct"):
            parsed, index = _parse_struct(lines, index, doc, None)
            entries.append(parsed)
            doc = ""
            continue
        if code.startswith("class ") and ";" not in code:
            parsed, index = _parse_class(lines, index, doc, None)
            entries.extend(parsed)
            doc = ""
            continue
        index += 1
    for entry in entries:
        entry["file"] = relative
        entry.setdefault("family", "other")
        entry["risk"] = _risk(entry["name"]) if entry["kind"] in ("function", "callback") else "data"
    return entries


REFERENCE_RE = re.compile(r"\b((?:ai|camera|gimbal|dev|mtp|wifi|bt|upgrade)[A-Z]\w+)\s*\(")


def referenced_symbols(text: str) -> list[str]:
    return sorted(set(REFERENCE_RE.findall(text)))


def census(root: Path) -> dict:
    root = root.resolve()
    inventory = discover(root)
    symbols: list[dict] = []
    files: dict[str, dict] = {}
    for entry in inventory:
        if entry["type"] not in ("header", "source", "sample_source"):
            continue
        path = root / entry["path"]
        text = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        record = {"sha256": entry["sha256"], "lines": len(text), "type": entry["type"]}
        if entry["type"] == "header":
            parsed = _parse_unit(list(enumerate(text, 1)), entry["path"])
            symbols.extend(parsed)
            record["parsed"] = True
            record["symbols"] = len(parsed)
        else:
            record["parsed"] = False
            record["skip_reason"] = "sample source: symbol references extracted, body not parsed"
            record["referenced_symbols"] = referenced_symbols("\n".join(text))
        files[entry["path"]] = record
        entry["parsed"] = record["parsed"]
        if record.get("skip_reason"):
            entry["skip_reason"] = record["skip_reason"]
        if entry["type"] == "header":
            entry["symbols"] = record["symbols"]
    families: dict[str, int] = {}
    kinds: dict[str, int] = {}
    for entry in symbols:
        families[entry["family"]] = families.get(entry["family"], 0) + 1
        kinds[entry["kind"]] = kinds.get(entry["kind"], 0) + 1
    by_type: dict[str, int] = {}
    for entry in inventory:
        by_type[entry["type"]] = by_type.get(entry["type"], 0) + 1
    return {"package_label": root.name, "files": files, "inventory": inventory,
            "totals": {"symbols": len(symbols), "families": families, "kinds": kinds,
                       "by_type": by_type},
            "symbols": symbols}


def summarize(data: dict) -> str:
    lines = ["# SDK census (sanitized)", "", f"package: {data['package_label']}", "",
             f"symbols: {data['totals']['symbols']}",
             "files by type: " + ", ".join(f"{k}={v}" for k, v in sorted(data["totals"]["by_type"].items())),
             "", "## kinds", ""]
    for kind, count in sorted(data["totals"]["kinds"].items()):
        lines.append(f"- {kind}: {count}")
    lines += ["", "## families", ""]
    for family, count in sorted(data["totals"]["families"].items()):
        lines.append(f"- {family}: {count}")
    return "\n".join(lines) + "\n"


def _inventory_section(data: dict) -> list[str]:
    lines = ["", "## Discovery inventory (surface proof)", "",
             "The scanner walks the whole SDK root instead of a fixed file list, so this",
             "table is the evidence for what the public surface actually contains.", "",
             "| type | count |", "|---|---|"]
    for kind, count in sorted(data["totals"]["by_type"].items()):
        lines.append(f"| {kind} | {count} |")
    for group, label in (("header", "Headers (parsed)"),
                         ("sample_source", "Sample / example sources"),
                         ("source", "Other sources"),
                         ("doc", "Docs / readme (inventory only)"),
                         ("build", "Build metadata")):
        items = [entry for entry in data["inventory"] if entry["type"] == group]
        if not items:
            continue
        lines += ["", f"### {label}", "", "| path | sha256 (16) | parsed | skip reason |", "|---|---|---|---|"]
        for entry in items:
            lines.append(f"| `{entry['path']}` | `{entry.get('sha256', '')[:16]}…` | "
                         f"{entry.get('parsed', False)} | {entry.get('skip_reason') or '—'} |")
    binaries = [entry for entry in data["inventory"] if entry["type"] == "binary"]
    if binaries:
        aggregates: dict[str, list[int]] = {}
        for entry in binaries:
            suffix = PurePosixPath(entry["path"]).suffix.lower() or "(none)"
            bucket = aggregates.setdefault(suffix, [0, 0])
            bucket[0] += 1
            bucket[1] += entry["bytes"]
        lines += ["", "### Binary artifacts (aggregated, not parsed)", "",
                  "| suffix | count | total bytes |", "|---|---|---|"]
        for suffix, (count, total) in sorted(aggregates.items()):
            lines.append(f"| {suffix} | {count} | {total} |")
    others = [entry for entry in data["inventory"] if entry["type"] == "other"]
    if others:
        lines += ["", "### Other files", "",
                  "| path | bytes | skip reason |", "|---|---|---|"]
        for entry in others:
            lines.append(f"| `{entry['path']}` | {entry['bytes']} | {entry.get('skip_reason') or '—'} |")
    return lines


def sanitized_markdown(data: dict) -> str:
    lines = [
        "# Tail2 SDK Census (sanitized)",
        "",
        "Generated by `tools/sdk_census.py`, which **discovers** the SDK surface by walking",
        "the package root. Contains symbol names, kinds, our risk/applicability",
        "classification, enum member counts and a file inventory only: no proprietary",
        "header bodies, sample bodies, docs prose or binaries.",
        "",
        f"- package label: `{data['package_label']}`",
        f"- symbols: {data['totals']['symbols']}",
        "",
        "Applicability comes from the SDK's own doc comments where they name products",
        "(`tail2`, `tailair`, `tiny`, `meet`, ...); `generic` means the doc does not say.",
        "Presence in the header is **not** evidence that Tail2 firmware accepts or honors it.",
    ]
    lines += _inventory_section(data)
    lines += ["", "## Totals by kind", "", "| kind | count |", "|---|---|"]
    for kind, count in sorted(data["totals"]["kinds"].items()):
        lines.append(f"| {kind} | {count} |")
    lines += ["", "## Totals by family", "", "| family | count |", "|---|---|"]
    for family, count in sorted(data["totals"]["families"].items()):
        lines.append(f"| {family} | {count} |")
    families: dict[str, list[dict]] = {}
    for entry in data["symbols"]:
        families.setdefault(entry["family"], []).append(entry)
    for family in sorted(families):
        entries = sorted(families[family], key=lambda item: (item["kind"], item["name"]))
        lines += ["", f"## family: {family}", "",
                  "| symbol | kind | risk | applicability | size | file |",
                  "|---|---|---|---|---|---|"]
        for entry in entries:
            size = ""
            if entry["kind"] == "enum":
                size = f"{len(entry.get('members', []))} members"
            elif entry["kind"] in ("struct", "union"):
                size = f"{len(entry.get('fields', []))} fields"
            lines.append(f"| `{entry['name']}` | {entry['kind']} | {entry.get('risk', 'data')} | "
                         f"{entry['applicability_hint']} | {size} | `{entry.get('file', '')}` |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sdk", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path(".local/sdk-sweep"))
    parser.add_argument("--sanitize", type=Path,
                        help="also write the sanitized census markdown to this path")
    args = parser.parse_args()
    data = census(args.sdk)
    args.out.mkdir(parents=True, exist_ok=True)
    raw = args.out / "sdk-census.json"
    raw.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    summary = args.out / "sdk-census-summary.md"
    summary.write_text(summarize(data), encoding="utf-8")
    if args.sanitize:
        args.sanitize.parent.mkdir(parents=True, exist_ok=True)
        args.sanitize.write_text(sanitized_markdown(data), encoding="utf-8")
    print(raw)
    print(summary)
    if args.sanitize:
        print(args.sanitize)
    print(json.dumps(data["totals"]["by_type"], ensure_ascii=False))
    print(json.dumps(data["totals"]["kinds"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
