import importlib.util
import json
import pathlib
import re
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
CLI = ROOT / "util" / "ai_native_operator_control_report.py"
DOC = ROOT / "doc" / "ai-native-runtime" / "operator-status-package.md"
README = ROOT / "doc" / "ai-native-runtime" / "README.md"
PRIVATE_PATTERNS = re.compile(
    r"/Users/|minecraftpi|192\.168|spacebase|themepark|showcase100|"
    r"disneyland100|(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY|"
    r"private_prompt|asset_payload",
    re.I,
)


def load_report_module():
    assert CLI.is_file(), f"missing {CLI}"
    spec = importlib.util.spec_from_file_location("ai_native_operator_control_report", CLI)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sample_operator_package():
    return {
        "schema_version": 1,
        "package_kind": "ai_native_operator_status_package",
        "status": "attention",
        "generated_at": "2026-06-29T00:00:00Z",
        "runtime_context": {
            "game_profile": "ai_runtime",
            "source": "live_command",
            "mutation_performed": False,
        },
        "operator_control": {
            "surface_kind": "read_only_task_rollback_control",
            "action_mode": "dry_run_only",
            "mutation_performed": False,
            "recommendations_total": 5,
            "summaries": [
                {
                    "target_kind": "task",
                    "target_id": "task:/Users/billevans/private/spacebase",
                    "status": "running",
                    "safe_next_action": "inspect_task_before_action",
                    "dry_run_only": True,
                    "will_mutate": False,
                },
                {
                    "target_kind": "rollback",
                    "target_id": "rollback:one",
                    "status": "available",
                    "safe_next_action": "review_rollback_record_before_execution",
                    "dry_run_only": True,
                    "will_mutate": False,
                },
                {
                    "target_kind": "import_review",
                    "target_id": "review:asset:blocked",
                    "status": "blocked",
                    "safe_next_action": "review_import_blocker",
                    "dry_run_only": True,
                    "will_mutate": False,
                },
                {
                    "target_kind": "import_promotion",
                    "target_id": "promotion:ready",
                    "status": "ready",
                    "safe_next_action": "review_promotion_package_before_apply",
                    "dry_run_only": True,
                    "will_mutate": False,
                },
                {
                    "target_kind": "benchmark_gate",
                    "target_id": "gate:low-power",
                    "status": "fail",
                    "safe_next_action": "review_benchmark_failure",
                    "dry_run_only": True,
                    "will_mutate": False,
                },
            ],
            "truncated": False,
        },
        "safety": {"public_safe_output": True},
        "bounds": {
            "max_bytes": 24000,
            "output_bytes": 2000,
            "truncated": False,
        },
    }


class AIOperatorControlReportTests(unittest.TestCase):
    def assert_public_safe(self, payload):
        encoded = json.dumps(payload, sort_keys=True)
        self.assertLessEqual(len(encoded.encode("utf-8")), payload["bounds"]["max_bytes"])
        self.assertNotRegex(encoded, PRIVATE_PATTERNS)

    def test_build_report_summarizes_dry_run_recommendations(self):
        report_module = load_report_module()

        report = report_module.build_report(
            sample_operator_package(),
            generated_at="2026-06-29T01:00:00Z",
            source_path="local/benchmarks/run/ai-runtime-operator-status-live.json",
            max_bytes=24000,
        )

        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["report_kind"], "ai_native_operator_control_report")
        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["source_package"]["package_kind"], "ai_native_operator_status_package")
        self.assertEqual(report["source_package"]["path"], "local/benchmarks/run/ai-runtime-operator-status-live.json")
        self.assertEqual(report["operator_control"]["surface_kind"], "read_only_task_rollback_control")
        self.assertEqual(report["operator_control"]["action_mode"], "dry_run_only")
        self.assertFalse(report["operator_control"]["mutation_performed"])
        self.assertEqual(report["operator_control"]["recommendations_total"], 5)
        self.assertEqual(report["summary"]["items_total"], 5)
        self.assertEqual(report["summary"]["by_target_kind"]["task"], 1)
        self.assertEqual(report["summary"]["by_target_kind"]["rollback"], 1)
        self.assertEqual(report["summary"]["by_status"]["blocked"], 1)
        self.assertEqual(report["summary"]["by_safe_next_action"]["review_import_blocker"], 1)
        self.assertTrue(report["summary"]["attention_required"])
        self.assertEqual(len(report["items"]), 5)
        for item in report["items"]:
            self.assertTrue(item["dry_run_only"])
            self.assertFalse(item["will_mutate"])
            self.assertIn("target_kind", item)
            self.assertIn("target_id", item)
            self.assertIn("status", item)
            self.assertIn("safe_next_action", item)
        self.assertGreater(report["safety"]["redactions_applied"], 0)
        self.assert_public_safe(report)

    def test_empty_live_lua_summaries_are_reported_as_empty_items(self):
        report_module = load_report_module()
        package = sample_operator_package()
        package["status"] = "ready"
        package["operator_control"]["recommendations_total"] = 0
        package["operator_control"]["summaries"] = None

        report = report_module.build_report(package, generated_at="2026-06-29T01:00:00Z")

        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["operator_control"]["recommendations_total"], 0)
        self.assertEqual(report["items"], [])
        self.assertFalse(report["summary"]["attention_required"])
        self.assert_public_safe(report)

    def test_mutating_recommendation_is_rejected(self):
        report_module = load_report_module()
        package = sample_operator_package()
        package["operator_control"]["summaries"][0]["dry_run_only"] = False
        package["operator_control"]["summaries"][0]["will_mutate"] = True
        package["operator_control"]["summaries"][0]["safe_next_action"] = "cancel_task_now"

        with self.assertRaisesRegex(ValueError, "mutating"):
            report_module.build_report(package)

    def test_cli_writes_json_and_human_readable_reports(self):
        report_module = load_report_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = pathlib.Path(tmpdir) / "operator-status.json"
            json_output = pathlib.Path(tmpdir) / "operator-report.json"
            text_output = pathlib.Path(tmpdir) / "operator-report.txt"
            input_path.write_text(json.dumps(sample_operator_package()), encoding="utf-8")

            json_exit = report_module.main([
                "--input",
                str(input_path),
                "--output",
                str(json_output),
                "--generated-at",
                "2026-06-29T01:00:00Z",
                "--format",
                "json",
            ])
            text_exit = report_module.main([
                "--input",
                str(input_path),
                "--output",
                str(text_output),
                "--generated-at",
                "2026-06-29T01:00:00Z",
                "--format",
                "text",
            ])

            self.assertEqual(json_exit, 0)
            self.assertEqual(text_exit, 0)
            report = json.loads(json_output.read_text(encoding="utf-8"))
            text = text_output.read_text(encoding="utf-8")
            self.assertEqual(report["report_kind"], "ai_native_operator_control_report")
            self.assertIn("ai_native_operator_control_report", text)
            self.assertIn("dry_run_only", text)
            self.assertIn("review_import_blocker", text)
            self.assertNotRegex(text, PRIVATE_PATTERNS)
            self.assert_public_safe(report)

    def test_docs_describe_operator_control_report_adapter(self):
        readme = README.read_text(encoding="utf-8")
        doc = DOC.read_text(encoding="utf-8")

        self.assertIn("ai_native_operator_control_report.py", readme)
        self.assertIn("ai-runtime-operator-control-report.json", doc)
        self.assertIn("operator-control report adapter", doc)
        self.assertIn("human-readable", doc)
        self.assertIn("dry-run-only", doc)
        self.assertIn("safe next actions", doc)


if __name__ == "__main__":
    unittest.main()
