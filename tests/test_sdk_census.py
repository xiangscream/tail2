"""Offline tests for the SDK census parser.

Uses a synthetic header layout only; never reads or embeds the proprietary SDK.
"""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("sdk_census", Path(__file__).resolve().parents[1] / "tools" / "sdk_census.py")
sdk_census = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sdk_census)

SYNTHETIC_DEV_HPP = """\
#pragma once

/// product type.
enum ProductType {
\tProdTiny,
\tProdTail2 = 16,
\tProdTail2S,
};

/// zoom mode.
enum class ZoomMode : uint32_t {
\tModeAny,
\tModeUnknown,
};

/// download result.
enum ResState {
\tkErr = -4,
\tkOk = 0,
};

/// camera status payload.
typedef struct {
\tuint8_t id;
\tint32_t value;
} StatusPayload;

struct NamedInfo {
\tint a;
\tint b;
};

class Export Device {
public:
\t/** @brief Only for meet series and tiny2 series. */
\ttypedef std::function<void(void *param, uint32_t file_type,
\t\t\t   int32_t result, void *rev_param)>
\t\tFileDownloadCallback;

\t/** @brief Get firmware version. */
\tint getFwVersion(char *out);

\t/** @brief Set the motor angle. Only for tail air and tiny. */
\tint aiSetGimbalMotorAngleR(float angle);

\t/** @brief Set the zoom. */
\tint cameraSetZoomAbsoluteR(float zoom);

\t/** @brief Read the gimbal preset list. */
\tint aiGetGimbalPresetListR(void *out);

\t/** @brief Reset the boot position. */
\tint aiRstGimbalBootPosR(void);

\t/** @brief Format the SD card. */
\tint cameraFormatSdR(void);
};
"""


def make_root() -> Path:
    temp = tempfile.TemporaryDirectory()
    root = Path(temp.name)
    (root / "include" / "dev").mkdir(parents=True)
    (root / "include" / "util").mkdir(parents=True)
    (root / "include" / "dev" / "dev.hpp").write_text(SYNTHETIC_DEV_HPP, encoding="utf-8")
    (root / "include" / "dev" / "devs.hpp").write_text("class Export Devices {\n};\n", encoding="utf-8")
    (root / "include" / "util" / "comm.hpp").write_text("#define LIB_MAJOR_VER 1\n", encoding="utf-8")
    return root


class CensusParserTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "include" / "dev").mkdir(parents=True)
        (self.root / "include" / "util").mkdir(parents=True)
        (self.root / "include" / "dev" / "dev.hpp").write_text(SYNTHETIC_DEV_HPP, encoding="utf-8")
        (self.root / "include" / "dev" / "devs.hpp").write_text("class Devices {\n};\n", encoding="utf-8")
        (self.root / "include" / "util" / "comm.hpp").write_text("#define LIB_MAJOR_VER 1\n", encoding="utf-8")
        self.data = sdk_census.census(self.root)
        self.by = {entry["name"]: entry for entry in self.data["symbols"]}

    def test_enum_members_and_explicit_values(self):
        enum = self.by["ProductType"]
        self.assertEqual(enum["kind"], "enum")
        names = [m["name"] for m in enum["members"]]
        self.assertEqual(names, ["ProdTiny", "ProdTail2", "ProdTail2S"])
        values = {m["name"]: m["value"] for m in enum["members"]}
        self.assertEqual(values["ProdTail2"], "16")
        self.assertIsNone(values["ProdTiny"])

    def test_scoped_enum_underlying_type(self):
        enum = self.by["ZoomMode"]
        self.assertTrue(enum["enum_class"])
        self.assertEqual(enum["underlying"], "uint32_t")

    def test_typedef_struct_alias_is_named(self):
        struct = self.by["StatusPayload"]
        self.assertTrue(struct["typedef"])
        self.assertEqual(len(struct["fields"]), 2)

    def test_named_struct_fields(self):
        struct = self.by["NamedInfo"]
        self.assertEqual(struct["kind"], "struct")
        self.assertEqual([f.split()[-1] for f in struct["fields"]], ["a", "b"])

    def test_multiline_function_typedef_becomes_callback(self):
        callback = self.by["FileDownloadCallback"]
        self.assertEqual(callback["kind"], "callback")
        self.assertEqual(callback["scope"], "Device")

    def test_methods_captured_with_scope(self):
        method = self.by["aiSetGimbalMotorAngleR"]
        self.assertEqual(method["kind"], "function")
        self.assertEqual(method["scope"], "Device")
        self.assertIn("float", method["signature"])

    def test_applicability_hint_from_doc_comment(self):
        self.assertEqual(self.by["aiSetGimbalMotorAngleR"]["applicability_hint"], "tailair+tiny")
        self.assertEqual(self.by["FileDownloadCallback"]["applicability_hint"], "meet+tiny")
        self.assertEqual(self.by["aiGetGimbalPresetListR"]["applicability_hint"], "generic")

    def test_risk_word_boundaries_not_substrings(self):
        self.assertEqual(sdk_census._risk("cameraSetZoomAbsoluteR"), "reversible_write")
        self.assertEqual(sdk_census._risk("aiGetGimbalPresetListR"), "read_only")
        self.assertEqual(sdk_census._risk("aiRstGimbalBootPosR"), "destructive")
        self.assertEqual(sdk_census._risk("cameraFormatSdR"), "destructive")
        self.assertEqual(sdk_census._risk("getFwVersion"), "read_only")

    def test_totals_and_hash_recorded(self):
        self.assertGreaterEqual(self.data["totals"]["symbols"], 10)
        self.assertIn("include/dev/dev.hpp", self.data["files"])
        self.assertEqual(len(self.data["files"]["include/dev/dev.hpp"]["sha256"]), 64)

    def test_summary_contains_no_symbol_prose(self):
        summary = sdk_census.summarize(self.data)
        self.assertIn("symbols:", summary)
        self.assertNotIn("Only for", summary)


if __name__ == "__main__":
    unittest.main()


class DiscoveryTests(unittest.TestCase):
    """The scanner must discover the surface, not assume a fixed file list."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        for relative in ("include/dev", "include/extra", "OBSBOT_Sample", "docs",
                         "linux/x86_64-release", "windows/win64-release"):
            (root / relative).mkdir(parents=True)
        (root / "include/dev/dev.hpp").write_text(SYNTHETIC_DEV_HPP, encoding="utf-8")
        (root / "include/extra/nested.h").write_text("enum ExtraEnum { A, B };\n", encoding="utf-8")
        (root / "OBSBOT_Sample/main.cpp").write_text(
            "int main(){ aiSetEnabledR(true); return 0; }\n", encoding="utf-8")
        (root / "OBSBOT_Sample/CMakeLists.txt").write_text("project(x)\n", encoding="utf-8")
        (root / "docs/readme.md").write_text("# private notes\n", encoding="utf-8")
        (root / "linux/x86_64-release/libdev.so.1").write_bytes(b"\x7fELF")
        (root / "windows/win64-release/libdev.dll").write_bytes(b"MZ")
        self.data = sdk_census.census(root)
        self.inv = {entry["path"]: entry for entry in self.data["inventory"]}

    def test_fixed_file_list_is_gone(self):
        self.assertFalse(hasattr(sdk_census, "HEADERS"))
        self.assertTrue(hasattr(sdk_census, "discover"))

    def test_nested_header_is_discovered(self):
        self.assertIn("include/extra/nested.h", self.inv)
        self.assertEqual(self.inv["include/extra/nested.h"]["type"], "header")
        self.assertIn("ExtraEnum", {entry["name"] for entry in self.data["symbols"]})

    def test_sample_source_recorded_not_parsed_as_surface(self):
        entry = self.inv["OBSBOT_Sample/main.cpp"]
        self.assertEqual(entry["type"], "sample_source")
        self.assertFalse(entry["parsed"])
        refs = self.data["files"]["OBSBOT_Sample/main.cpp"]["referenced_symbols"]
        self.assertIn("aiSetEnabledR", refs)
        self.assertNotIn("main", {entry["name"] for entry in self.data["symbols"]})

    def test_doc_inventoried_with_hash_and_skip_reason(self):
        entry = self.inv["docs/readme.md"]
        self.assertEqual(entry["type"], "doc")
        self.assertEqual(len(entry["sha256"]), 64)
        self.assertIn("inventory only", entry["skip_reason"])
        self.assertNotIn("readme.md", self.data["files"])

    def test_versioned_shared_object_is_binary(self):
        self.assertEqual(self.inv["linux/x86_64-release/libdev.so.1"]["type"], "binary")

    def test_build_file_classified(self):
        self.assertEqual(self.inv["OBSBOT_Sample/CMakeLists.txt"]["type"], "build")

    def test_surface_bounded_by_discovery(self):
        self.assertEqual(self.data["totals"]["by_type"]["header"], 2)
        self.assertEqual(self.data["totals"]["by_type"]["sample_source"], 1)
        self.assertEqual(self.data["totals"]["by_type"]["binary"], 2)

    def test_sanitized_inventory_lists_headers_without_prose(self):
        markdown = sdk_census.sanitized_markdown(self.data)
        self.assertIn("Discovery inventory", markdown)
        self.assertIn("include/extra/nested.h", markdown)
        self.assertNotIn("Only for", markdown)


BOUNDARY_HEADER = """\
#pragma once

DEV_EXPORT void dev_set_log_handler(int handler, void *param);

PRINTFATTR(2, 3)
void dlog(int level, const char *format, ...);

#pragma pack(1)
int cameraSetPowerCtrlActionR(int action);
#pragma pack()

class Export Device {
public:
\t#pragma pack(1)
\tint cameraSetPAEEvBiasR(int32_t ev_bias);
\t#pragma pack()

\ttypedef union {
\t\tstruct { int a; } tail_air;
\t\tstruct { int b; } tail2;
\t} CameraStatus;
};
"""


class ParserCompletenessTests(unittest.TestCase):
    """Regressions for doc-comment / declaration-boundary misses."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / "include/dev").mkdir(parents=True)
        (root / "include/util").mkdir(parents=True)
        (root / "include/dev/dev.hpp").write_text(BOUNDARY_HEADER, encoding="utf-8")
        (root / "include/dev/devs.hpp").write_text("class Devices {\n};\n", encoding="utf-8")
        (root / "include/util/comm.hpp").write_text("#define X 1\n", encoding="utf-8")
        self.data = sdk_census.census(root)
        self.names = {entry["name"] for entry in self.data["symbols"]}

    def test_pragma_lines_do_not_glue_to_declarations(self):
        self.assertIn("cameraSetPowerCtrlActionR", self.names)
        self.assertIn("cameraSetPAEEvBiasR", self.names)

    def test_attribute_macro_prefix_is_stripped(self):
        self.assertIn("dlog", self.names)

    def test_export_macro_prefixed_function_is_parsed(self):
        self.assertIn("dev_set_log_handler", self.names)

    def test_typedef_union_inside_class_is_parsed(self):
        self.assertIn("CameraStatus", self.names)

    def test_all_headers_report_complete(self):
        self.assertTrue(self.data["complete"])
        for item in self.data["completeness"].values():
            self.assertEqual(item["unmatched_candidates"], [])

    def test_candidate_pass_ignores_define_macros(self):
        candidates = sdk_census.candidate_declarations("#define dlog(x) x\nint real(int a);\n")
        self.assertNotIn("dlog", candidates["function"])
        self.assertIn("real", candidates["function"])

    def test_typedef_aliases_are_not_nested_members(self):
        aliases = sdk_census._typedef_aliases("typedef union {\n struct { int a; } tail_air;\n} CameraStatus;\n")
        self.assertEqual(aliases, {"CameraStatus"})

    def test_completeness_gate_flags_unmatched(self):
        report = sdk_census.completeness_report("int foo(int a);\n", set())
        self.assertFalse(report["complete"])
        self.assertEqual(report["unmatched_candidates"][0]["name"], "foo")

    def test_completeness_gate_accepts_parsed(self):
        self.assertTrue(sdk_census.completeness_report("int foo(int a);\n", {"foo"})["complete"])

    def test_allowlist_marks_unmatched_as_allowed(self):
        sdk_census.CANDIDATE_ALLOWLIST["foo"] = "synthetic allowlist entry"
        self.addCleanup(sdk_census.CANDIDATE_ALLOWLIST.pop, "foo", None)
        report = sdk_census.completeness_report("int foo(int a);\n", set())
        self.assertTrue(report["complete"])
        self.assertEqual(report["allowlisted"][0]["reason"], "synthetic allowlist entry")
