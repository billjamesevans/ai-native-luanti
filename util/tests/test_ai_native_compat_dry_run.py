import contextlib
import io
import json
import pathlib
import sys
import tempfile
import unittest


UTIL_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(UTIL_DIR))

from ai_native_compat_dry_run import build_report, main


class CompatibilityDryRunTests(unittest.TestCase):
    def setUp(self):
        self.fixture_root = pathlib.Path(__file__).resolve().parent / "fixtures" / "compat"

    def assert_safety_flags(self, report):
        self.assertTrue(report["safety"]["no_assets_copied"])
        self.assertTrue(report["safety"]["no_world_mutation"])
        self.assertTrue(report["safety"]["source_paths_redacted"])
        self.assertTrue(report["safety"]["user_rights_required"])

    def test_bedrock_manifest_report_has_safety_and_unsupported_rows(self):
        source = self.fixture_root / "bedrock_pack"

        report = build_report(source)

        self.assertIn("report_version", report)
        self.assertIn("source", report)
        self.assertEqual(report["report_version"], 1)
        self.assertEqual(report["mode"], "dry_run")
        self.assertEqual(report["source"]["source_class"], "bedrock_resource_pack")
        self.assertEqual(report["source"]["path_policy"], "external_reference")
        self.assertEqual(report["source"]["license_status"], "user_supplied")
        self.assert_safety_flags(report)

        features = {item["feature"]: item for item in report["unsupported_features"]}
        self.assertEqual(
            features["entity.behavior_script"]["reason"],
            "behavior_script_not_supported",
        )
        self.assertEqual(features["entity.ai_goal"]["reason"], "entity_ai_not_supported")
        self.assertNotIn(str(source), json.dumps(report))
        self.assertTrue(
            all("import.assets" in action["required_capabilities"]
                for action in report["planned_actions"])
        )

    def test_java_pack_report_classifies_metadata_and_language_assets(self):
        source = self.fixture_root / "java_pack"

        report = build_report(source)

        self.assertIn("source", report)
        self.assertIn("summary", report)
        self.assertEqual(report["source"]["source_class"], "java_resource_pack")
        self.assertEqual(report["summary"]["risk_level"], "low")
        self.assert_safety_flags(report)
        sections = {section["name"]: section for section in report["sections"]}
        self.assertEqual(sections["metadata"]["status"], "supported")
        self.assertEqual(sections["models"]["status"], "partial")
        self.assertEqual(report["summary"]["estimated_world_mutations"]["node_writes"], 0)

    def test_cli_writes_json_report_and_summary(self):
        source = self.fixture_root / "bedrock_pack"
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = pathlib.Path(tmpdir) / "report.json"
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                exit_code = main([str(source), "--output", str(output_path), "--summary"])

            self.assertEqual(exit_code, 0)
            report = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(report["mode"], "dry_run")
            self.assertIn("risk=", stdout.getvalue())
            self.assertIn("unsupported=", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
