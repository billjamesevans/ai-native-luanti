import importlib.util
import json
import pathlib
import re
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
CLI = ROOT / "util" / "ai_native_operator_action_approval_plan.py"
DOC = ROOT / "doc" / "ai-native-runtime" / "operator-status-package.md"
README = ROOT / "doc" / "ai-native-runtime" / "README.md"
PRIVATE_PATTERNS = re.compile(
    r"/Users/|minecraftpi|192\.168|spacebase|themepark|showcase100|"
    r"disneyland100|(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY|"
    r"private_prompt|asset_payload",
    re.I,
)


def load_plan_module():
    assert CLI.is_file(), f"missing {CLI}"
    spec = importlib.util.spec_from_file_location("ai_native_operator_action_approval_plan", CLI)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sample_operator_control_report():
    return {
        "schema_version": 1,
        "report_kind": "ai_native_operator_control_report",
        "status": "attention",
        "generated_at": "2026-06-29T01:00:00Z",
        "source_package": {
            "package_kind": "ai_native_operator_status_package",
            "status": "attention",
            "generated_at": "2026-06-29T00:00:00Z",
            "path": "/Users/billevans/private/spacebase/operator-status.json",
        },
        "operator_control": {
            "surface_kind": "read_only_task_rollback_control",
            "action_mode": "dry_run_only",
            "mutation_performed": False,
            "recommendations_total": 6,
            "truncated": False,
        },
        "summary": {
            "items_total": 6,
            "source_recommendations_total": 6,
            "by_target_kind": {
                "task": 2,
                "rollback": 1,
                "import_review": 1,
                "import_promotion": 1,
                "benchmark_gate": 1,
            },
            "by_status": {
                "blocked": 2,
                "available": 1,
                "ready": 1,
                "fail": 1,
                "running": 1,
            },
            "by_safe_next_action": {},
            "attention_required": True,
        },
        "items": [
            {
                "target_kind": "task",
                "target_id": "task:/Users/billevans/private/themepark:running",
                "status": "running",
                "safe_next_action": "inspect_task_before_action",
                "dry_run_only": True,
                "will_mutate": False,
            },
            {
                "target_kind": "task",
                "target_id": "task:repair-blocked",
                "status": "blocked",
                "safe_next_action": "review_blocked_task_before_retry",
                "dry_run_only": True,
                "will_mutate": False,
            },
            {
                "target_kind": "rollback",
                "target_id": "rollback:record-one",
                "status": "available",
                "safe_next_action": "review_rollback_record_before_execution",
                "dry_run_only": True,
                "will_mutate": False,
            },
            {
                "target_kind": "import_review",
                "target_id": "review:asset_payload:blocked",
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
                "target_id": "gate:low-power:REDACTED_KEY_FIXTURE",
                "status": "fail",
                "safe_next_action": "review_benchmark_failure",
                "dry_run_only": True,
                "will_mutate": False,
            },
        ],
        "safety": {
            "public_safe_output": True,
            "dry_run_only": True,
            "no_mutating_actions": True,
            "no_world_mutation": True,
            "no_raw_assets": True,
            "no_provider_prompts": True,
            "no_family_world_coordinates": True,
        },
        "bounds": {
            "max_bytes": 16000,
            "output_bytes": 2200,
            "truncated": False,
        },
    }


class AIOperatorActionApprovalPlanTests(unittest.TestCase):
    def assert_public_safe(self, payload):
        encoded = json.dumps(payload, sort_keys=True)
        self.assertLessEqual(len(encoded.encode("utf-8")), payload["bounds"]["max_bytes"])
        self.assertNotRegex(encoded, PRIVATE_PATTERNS)

    def test_build_plan_groups_task_rollback_import_and_benchmark_candidates(self):
        plan_module = load_plan_module()

        plan = plan_module.build_plan(
            sample_operator_control_report(),
            generated_at="2026-06-29T02:00:00Z",
            source_path="local/benchmarks/run/ai-runtime-operator-control-report.json",
            max_bytes=32000,
        )

        self.assertEqual(plan["schema_version"], 1)
        self.assertEqual(plan["plan_kind"], "ai_native_operator_action_approval_plan")
        self.assertEqual(plan["status"], "attention")
        self.assertEqual(plan["source_report"]["report_kind"], "ai_native_operator_control_report")
        self.assertEqual(
            plan["source_report"]["path"],
            "local/benchmarks/run/ai-runtime-operator-control-report.json",
        )
        self.assertEqual(plan["operator_actions"]["mode"], "approval_required")
        self.assertFalse(plan["operator_actions"]["mutation_performed"])
        self.assertEqual(plan["operator_actions"]["candidate_actions_total"], 6)
        self.assertEqual(plan["summary"]["actions_total"], 6)
        self.assertEqual(plan["summary"]["by_target_kind"]["task"], 2)
        self.assertEqual(plan["summary"]["by_target_kind"]["rollback"], 1)
        self.assertEqual(plan["summary"]["by_safe_next_action"]["review_benchmark_failure"], 1)
        self.assertTrue(plan["summary"]["attention_required"])
        self.assertEqual(len(plan["approval_groups"]), 6)

        by_action = {item["safe_next_action"]: item for item in plan["approval_groups"]}
        self.assertIn("task.cancel.review", by_action["inspect_task_before_action"]["required_capabilities"])
        self.assertIn("task.retry.review", by_action["review_blocked_task_before_retry"]["required_capabilities"])
        self.assertIn(
            "rollback.execute.review",
            by_action["review_rollback_record_before_execution"]["required_capabilities"],
        )
        self.assertEqual(
            by_action["review_rollback_record_before_execution"]["references"]["rollback_records"],
            ["rollback:record-one"],
        )
        self.assertEqual(
            by_action["review_promotion_package_before_apply"]["references"]["source_artifacts"],
            ["promotion:ready"],
        )
        self.assertEqual(
            by_action["review_benchmark_failure"]["blocked_reasons"],
            ["benchmark_gate_failed"],
        )
        for item in plan["approval_groups"]:
            self.assertTrue(item["dry_run_only"])
            self.assertFalse(item["will_mutate"])
            self.assertFalse(item["supported"] is False and not item["unsupported_reasons"])
            self.assertIn("prerequisites", item)
            self.assertIn("required_capabilities", item)
            self.assertIn("references", item)
        self.assertGreater(plan["safety"]["redactions_applied"], 0)
        self.assert_public_safe(plan)

    def test_unknown_safe_next_action_is_held_for_manual_review(self):
        plan_module = load_plan_module()
        report = sample_operator_control_report()
        report["items"] = [
            {
                "target_kind": "custom",
                "target_id": "custom:one",
                "status": "ready",
                "safe_next_action": "review_custom_extension",
                "dry_run_only": True,
                "will_mutate": False,
            }
        ]
        report["summary"]["items_total"] = 1
        report["operator_control"]["recommendations_total"] = 1

        plan = plan_module.build_plan(report, generated_at="2026-06-29T02:00:00Z")

        self.assertEqual(plan["status"], "attention")
        self.assertEqual(plan["summary"]["unsupported_actions"], 1)
        self.assertFalse(plan["approval_groups"][0]["supported"])
        self.assertEqual(plan["approval_groups"][0]["unsupported_reasons"], ["unsupported_safe_next_action"])
        self.assertIn("manual_operator_review", plan["approval_groups"][0]["prerequisites"])
        self.assert_public_safe(plan)

    def test_empty_operator_control_report_writes_empty_approval_plan(self):
        plan_module = load_plan_module()
        report = sample_operator_control_report()
        report["status"] = "ready"
        report["items"] = []
        report["summary"]["items_total"] = 0
        report["operator_control"]["recommendations_total"] = 0

        plan = plan_module.build_plan(report, generated_at="2026-06-29T02:00:00Z")

        self.assertEqual(plan["status"], "ready")
        self.assertEqual(plan["operator_actions"]["candidate_actions_total"], 0)
        self.assertEqual(plan["approval_groups"], [])
        self.assertFalse(plan["summary"]["attention_required"])
        self.assert_public_safe(plan)

    def test_mutating_recommendation_is_rejected(self):
        plan_module = load_plan_module()
        report = sample_operator_control_report()
        report["items"][0]["dry_run_only"] = False
        report["items"][0]["will_mutate"] = True
        report["items"][0]["safe_next_action"] = "execute_rollback_now"

        with self.assertRaisesRegex(ValueError, "mutating"):
            plan_module.build_plan(report)

    def test_oversized_source_report_is_rejected_before_planning(self):
        plan_module = load_plan_module()
        report = sample_operator_control_report()
        report["bounds"]["output_bytes"] = 20000
        report["bounds"]["max_bytes"] = 16000

        with self.assertRaisesRegex(ValueError, "source report exceeds"):
            plan_module.build_plan(report)

    def test_cli_writes_json_and_text_approval_plans(self):
        plan_module = load_plan_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = pathlib.Path(tmpdir) / "operator-control-report.json"
            json_output = pathlib.Path(tmpdir) / "approval-plan.json"
            text_output = pathlib.Path(tmpdir) / "approval-plan.txt"
            input_path.write_text(json.dumps(sample_operator_control_report()), encoding="utf-8")

            json_exit = plan_module.main([
                "--input",
                str(input_path),
                "--output",
                str(json_output),
                "--generated-at",
                "2026-06-29T02:00:00Z",
                "--format",
                "json",
            ])
            text_exit = plan_module.main([
                "--input",
                str(input_path),
                "--output",
                str(text_output),
                "--generated-at",
                "2026-06-29T02:00:00Z",
                "--format",
                "text",
            ])

            self.assertEqual(json_exit, 0)
            self.assertEqual(text_exit, 0)
            plan = json.loads(json_output.read_text(encoding="utf-8"))
            text = text_output.read_text(encoding="utf-8")
            self.assertEqual(plan["plan_kind"], "ai_native_operator_action_approval_plan")
            self.assertIn("ai_native_operator_action_approval_plan", text)
            self.assertIn("approval_required", text)
            self.assertIn("rollback.execute.review", text)
            self.assertNotRegex(text, PRIVATE_PATTERNS)
            self.assert_public_safe(plan)

    def test_docs_describe_operator_action_approval_plan_adapter(self):
        readme = README.read_text(encoding="utf-8")
        doc = DOC.read_text(encoding="utf-8")

        self.assertIn("ai_native_operator_action_approval_plan.py", readme)
        self.assertIn("ai-runtime-operator-action-approval-plan.json", doc)
        self.assertIn("operator action approval plan", doc)
        self.assertIn("approval-plan artifacts", doc)
        self.assertIn("non-mutating", doc)
        self.assertIn("task cancel/retry", doc)
        self.assertIn("rollback execution review", doc)


if __name__ == "__main__":
    unittest.main()
