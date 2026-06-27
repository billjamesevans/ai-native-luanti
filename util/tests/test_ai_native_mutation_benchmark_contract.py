import json
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
CLI = ROOT / "util" / "ai_native_mutation_benchmarks.py"
SCHEMA = ROOT / "doc" / "ai-native-runtime" / "schemas" / "ai-runtime-mutation-benchmark-report.schema.json"
EXAMPLE = ROOT / "doc" / "ai-native-runtime" / "examples" / "mutation-benchmark-report.example.json"
DOC = ROOT / "doc" / "ai-native-runtime" / "mutation-benchmark-scenarios.md"
README = ROOT / "doc" / "ai-native-runtime" / "README.md"

EXPECTED_SCENARIOS = {
    "small_build_rollback",
    "repair_scan_readonly",
    "repair_mutation_rollback",
    "rollback_record_write",
}

REQUIRED_REPORT_FIELDS = {
    "schema_version",
    "generated_at",
    "luanti_commit",
    "hardware_class",
    "run_context",
    "scenarios",
    "regression_gates",
}

REQUIRED_SCENARIO_FIELDS = {
    "scenario_id",
    "category",
    "description",
    "entry_point",
    "fixture",
    "metrics",
}

REQUIRED_METRICS = {
    "avg_step_ms",
    "p95_step_ms",
    "max_lag_ms",
    "node_writes_per_step",
    "skipped_positions",
    "rollback_records",
    "ai_runtime_counters",
    "warnings",
    "errors",
}

PRIVATE_PATTERNS = re.compile(
    r"minecraftpi|192\.168|spacebase|themepark|showcase100|disneyland100|asset_payload|prompt",
    re.I,
)


class MutationBenchmarkContractTests(unittest.TestCase):
    def load_json(self, path):
        with self.subTest(path=path.name):
            self.assertTrue(path.is_file(), f"missing {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def assert_report_contract(self, report):
        self.assertTrue(REQUIRED_REPORT_FIELDS.issubset(report))
        self.assertEqual(report["schema_version"], 1)
        self.assertIn(report["hardware_class"], {"local-mac", "low-power-server"})
        self.assertFalse(report["run_context"]["requires_private_world"])
        self.assertFalse(report["run_context"]["requires_private_assets"])
        self.assertFalse(report["run_context"]["requires_live_pi"])

        scenario_ids = {scenario["scenario_id"] for scenario in report["scenarios"]}
        self.assertEqual(EXPECTED_SCENARIOS, scenario_ids)

        for scenario in report["scenarios"]:
            with self.subTest(scenario=scenario["scenario_id"]):
                self.assertTrue(REQUIRED_SCENARIO_FIELDS.issubset(scenario))
                self.assertTrue(REQUIRED_METRICS.issubset(scenario["metrics"]))
                self.assertTrue(scenario["fixture"]["synthetic"])
                self.assertFalse(scenario["fixture"]["requires_live_world"])
                self.assertFalse(scenario["fixture"]["requires_private_assets"])
                self.assertNotEqual(scenario["entry_point"]["command"], "")

    def test_schema_declares_required_benchmark_report_fields(self):
        schema = self.load_json(SCHEMA)

        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertTrue(REQUIRED_REPORT_FIELDS.issubset(schema["required"]))
        scenario_required = set(schema["$defs"]["scenario"]["required"])
        self.assertTrue(REQUIRED_SCENARIO_FIELDS.issubset(scenario_required))
        metric_required = set(schema["$defs"]["metrics"]["required"])
        self.assertTrue(REQUIRED_METRICS.issubset(metric_required))
        self.assertFalse(schema.get("additionalProperties", True))

    def test_example_report_matches_contract_without_private_payloads(self):
        report = self.load_json(EXAMPLE)
        self.assert_report_contract(report)

        serialized = json.dumps(report, sort_keys=True)
        self.assertNotRegex(serialized, PRIVATE_PATTERNS)

    def test_cli_writes_runnable_public_safe_report(self):
        self.assertTrue(CLI.is_file(), f"missing {CLI}")
        with tempfile.TemporaryDirectory() as tmpdir:
            output = pathlib.Path(tmpdir) / "mutation-benchmark-report.json"
            subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    "--output",
                    str(output),
                    "--hardware-class",
                    "local-mac",
                    "--luanti-commit",
                    "test-commit",
                    "--sample-synthetic",
                ],
                cwd=ROOT,
                check=True,
                text=True,
                capture_output=True,
            )
            report = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(report["luanti_commit"], "test-commit")
        self.assert_report_contract(report)
        self.assertNotRegex(json.dumps(report, sort_keys=True), PRIVATE_PATTERNS)

    def test_public_documentation_covers_entry_points_and_regression_gates(self):
        self.assertTrue(DOC.is_file(), f"missing {DOC}")
        body = DOC.read_text(encoding="utf-8")
        readme = README.read_text(encoding="utf-8")

        for phrase in (
            "util/ai_native_mutation_benchmarks.py",
            "small_build_rollback",
            "repair_scan_readonly",
            "repair_mutation_rollback",
            "rollback_record_write",
            "average step",
            "p95 step",
            "max lag",
            "must not merge",
            "local-mac",
            "low-power-server",
        ):
            self.assertIn(phrase, body)

        self.assertIn("mutation-benchmark-scenarios.md", readme)
        self.assertNotRegex(body, PRIVATE_PATTERNS)


if __name__ == "__main__":
    unittest.main()
