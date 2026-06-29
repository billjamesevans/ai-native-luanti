import json
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
CLI = ROOT / "util" / "ai_native_benchmark_compare.py"
DOC = ROOT / "doc" / "ai-native-runtime" / "benchmark-baseline-retention.md"
README = ROOT / "doc" / "ai-native-runtime" / "README.md"

PRIVATE_PATTERNS = re.compile(
    r"minecraftpi|192\.168|spacebase|themepark|showcase100|disneyland100|"
    r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY|private_prompt|asset_payload",
    re.I,
)


def mutation_report(commit, max_lag_ms, warnings=None, errors=None, rollback_records=1):
    return {
        "schema_version": 1,
        "generated_at": "2026-06-27T00:00:00Z",
        "luanti_commit": commit,
        "hardware_class": "local-mac",
        "run_context": {
            "mode": "measured",
            "requires_private_world": False,
            "requires_private_assets": False,
            "requires_live_pi": False,
        },
        "scenarios": [
            {
                "scenario_id": "small_build_rollback",
                "category": "build",
                "description": "Synthetic build benchmark.",
                "entry_point": {},
                "fixture": {
                    "synthetic": True,
                    "requires_live_world": False,
                    "requires_private_assets": False,
                },
                "metrics": {
                    "avg_step_ms": 10.0,
                    "p95_step_ms": 15.0,
                    "max_lag_ms": max_lag_ms,
                    "node_writes_per_step": 8,
                    "rollback_records": rollback_records,
                    "warnings": warnings or [],
                    "errors": errors or [],
                },
            }
        ],
        "regression_gates": [],
    }


def demo_entity_report(commit, max_lag_ms, warnings=None, errors=None):
    return {
        "schema_version": 1,
        "generated_at": "2026-06-27T00:00:00Z",
        "fixture_id": "generic_demo_entity:benchmark:v1",
        "entity_name": "ai_demo_benchmark:helper",
        "luanti_commit": commit,
        "hardware_class": "local-mac",
        "run_context": {
            "mode": "measured",
            "requires_private_world": False,
            "requires_private_assets": False,
            "requires_live_pi": False,
        },
        "runtime_counters": {
            "entities_by_type": {
                "ai_demo_benchmark:helper": 0,
            }
        },
        "scenarios": [
            {
                "scenario_id": "entity_count_small",
                "status": "success",
                "changed": 0,
                "metrics": {
                    "entity_count": 4,
                    "active_peak": 4,
                    "remaining_entities": 0,
                    "avg_step_ms": 0.2,
                    "p95_step_ms": 0.3,
                    "max_lag_ms": max_lag_ms,
                    "node_writes": 0,
                    "warnings": warnings or [],
                    "errors": errors or [],
                },
            }
        ],
    }


class BenchmarkRetentionPolicyTests(unittest.TestCase):
    def run_compare(self, baseline, branch):
        self.assertTrue(CLI.is_file(), f"missing {CLI}")
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = pathlib.Path(tmpdir)
            baseline_path = tmp / "baseline.json"
            branch_path = tmp / "branch.json"
            output_path = tmp / "comparison.json"
            baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
            branch_path.write_text(json.dumps(branch), encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    "--baseline",
                    str(baseline_path),
                    "--branch",
                    str(branch_path),
                    "--output",
                    str(output_path),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertTrue(output_path.is_file(), completed.stderr)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            serialized = json.dumps(payload, sort_keys=True)
            self.assertNotIn(tmpdir, serialized)
            self.assertNotRegex(serialized, PRIVATE_PATTERNS)
            return completed.returncode, payload

    def test_public_policy_doc_covers_retention_regression_and_privacy(self):
        self.assertTrue(DOC.is_file(), f"missing {DOC}")
        body = DOC.read_text(encoding="utf-8")
        readme = README.read_text(encoding="utf-8")

        for phrase in (
            "committed synthetic examples",
            "local measured reports",
            "local/benchmarks/",
            "util/ai_native_benchmark_compare.py",
            "must not merge",
            "average step",
            "p95 step",
            "max lag",
            "node writes",
            "entity counts",
            "entity_scale_16",
            "max_entity_count",
            "entity_scale_runtime_probe",
            "rollback records",
            "warnings",
            "errors",
            "backup-first",
            "private worlds",
            "local paths",
            "secrets",
            "player-private data",
        ):
            self.assertIn(phrase, body)

        self.assertIn("benchmark-baseline-retention.md", readme)
        self.assertNotRegex(body, PRIVATE_PATTERNS)

    def test_compare_passes_when_branch_stays_within_threshold(self):
        code, payload = self.run_compare(
            mutation_report("baseline", max_lag_ms=10.0),
            mutation_report("branch", max_lag_ms=10.8),
        )

        self.assertEqual(code, 0)
        self.assertEqual(payload["overall_status"], "pass")
        self.assertEqual(payload["report_family"], "mutation")
        self.assertEqual(payload["baseline_ref"]["luanti_commit"], "baseline")
        self.assertEqual(payload["branch_ref"]["luanti_commit"], "branch")

    def test_compare_records_branch_only_scenarios_as_additive_coverage(self):
        baseline = mutation_report("baseline", max_lag_ms=10.0)
        branch = mutation_report("branch", max_lag_ms=10.0)
        branch["scenarios"].append(
            {
                "scenario_id": "first_party_agent_product_loop_approval",
                "category": "agent_product_loop",
                "metrics": {
                    "avg_step_ms": 1.0,
                    "p95_step_ms": 1.1,
                    "max_lag_ms": 1.2,
                    "node_writes_per_step": 0,
                    "node_writes": 0,
                    "rollback_records": 0,
                    "warnings": [],
                    "errors": [],
                },
            }
        )

        code, payload = self.run_compare(baseline, branch)

        self.assertEqual(code, 0)
        self.assertEqual(payload["overall_status"], "pass")
        self.assertIn("first_party_agent_product_loop_approval", payload["branch_only_scenarios"])
        additive_gates = [
            gate
            for gate in payload["gates"]
            if gate["scenario_id"] == "first_party_agent_product_loop_approval"
        ]
        self.assertEqual(len(additive_gates), 1)
        self.assertEqual(additive_gates[0]["metric"], "scenario_presence")
        self.assertEqual(additive_gates[0]["status"], "pass")

    def test_compare_fails_when_branch_drops_baseline_scenario(self):
        baseline = mutation_report("baseline", max_lag_ms=10.0)
        branch = mutation_report("branch", max_lag_ms=10.0)
        branch["scenarios"] = []

        code, payload = self.run_compare(baseline, branch)

        self.assertEqual(code, 1)
        self.assertEqual(payload["overall_status"], "fail")
        self.assertIn("small_build_rollback", payload["baseline_only_scenarios"])
        self.assertTrue(
            any(
                gate["scenario_id"] == "small_build_rollback"
                and gate["metric"] == "scenario_presence"
                and gate["status"] == "fail"
                for gate in payload["gates"]
            )
        )

    def test_compare_fails_when_max_lag_regresses(self):
        code, payload = self.run_compare(
            mutation_report("baseline", max_lag_ms=10.0),
            mutation_report("branch", max_lag_ms=12.0),
        )

        self.assertEqual(code, 1)
        self.assertEqual(payload["overall_status"], "fail")
        failed = [gate for gate in payload["gates"] if gate["status"] == "fail"]
        self.assertTrue(any(gate["metric"] == "max_lag_ms" for gate in failed))
        self.assertTrue(any("must not merge" in gate["merge_rule"] for gate in failed))

    def test_compare_fails_on_new_warnings_and_missing_rollback_records(self):
        code, payload = self.run_compare(
            mutation_report("baseline", max_lag_ms=10.0, rollback_records=1),
            mutation_report(
                "branch",
                max_lag_ms=10.0,
                warnings=["new safety warning"],
                rollback_records=0,
            ),
        )

        self.assertEqual(code, 1)
        failed_metrics = {gate["metric"] for gate in payload["gates"] if gate["status"] == "fail"}
        self.assertIn("warnings", failed_metrics)
        self.assertIn("rollback_records", failed_metrics)

    def test_compare_supports_demo_entity_reports(self):
        code, payload = self.run_compare(
            demo_entity_report("baseline", max_lag_ms=0.4),
            demo_entity_report("branch", max_lag_ms=0.42),
        )

        self.assertEqual(code, 0)
        self.assertEqual(payload["overall_status"], "pass")
        self.assertEqual(payload["report_family"], "demo_entity")
        compared_metrics = {gate["metric"] for gate in payload["gates"]}
        self.assertIn("entity_count", compared_metrics)
        self.assertIn("node_writes", compared_metrics)


if __name__ == "__main__":
    unittest.main()
