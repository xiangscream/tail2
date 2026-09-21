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
        self.assertIn("include/dev/dev.hpp", self.data["headers"])
        self.assertEqual(len(self.data["headers"]["include/dev/dev.hpp"]["sha256"]), 64)

    def test_summary_contains_no_symbol_prose(self):
        summary = sdk_census.summarize(self.data)
        self.assertIn("symbols:", summary)
        self.assertNotIn("Only for", summary)


if __name__ == "__main__":
    unittest.main()
