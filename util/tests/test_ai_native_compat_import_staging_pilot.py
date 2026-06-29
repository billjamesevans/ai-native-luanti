import copy
import importlib.util
import json
import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
CLI = ROOT / "util" / "ai_native_compat_import_staging_pilot.py"
FIXTURE = ROOT / "util" / "tests" / "fixtures" / "compat" / "public_structure" / "open_platform.ai-structure.json"

PRIVATE_PATTERNS = re.compile(
    r"minecraftpi|192\.168|spacebase|themepark|showcase100|disneyland100|"
    r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY|private_prompt|"
    r"asset_payload|raw_asset_payload|payload_bytes|/Users/",
    re.I,
)


def load_pilot_module():
    assert CLI.is_file(), f"missing {CLI}"
    spec = importlib.util.spec_from_file_location(
        "ai_native_compat_import_staging_pilot",
        CLI,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sample_payload():
    payload = {
        "schema_version": 1,
        "live_result_kind": "ai_native_compat_import_staging_pilot_result",
        "generated_at": "2026-06-29T00:00:00Z",
        "runtime_context": {
            "mode": "disposable_live_ai_runtime_compat_import_staging_pilot",
            "gameid": "ai_runtime",
            "requires_live_pi": False,
            "requires_private_world": False,
            "requires_private_assets": False,
            "requires_model_network": False,
            "world_mutation_performed": True,
            "world_mutation_scope": "disposable_synthetic_ai_runtime_staging_world",
        },
        "workflow": {
            "inventory": {
                "status": "ready_for_import_preview",
                "ready": True,
                "sources_total": 1,
                "required_capabilities": ["import.assets", "world.batch", "world.place"],
            },
            "dry_run": {
                "report_id": "public-safe-structure-staging-pilot",
                "report_version": 1,
                "source_id": "open_platform.ai-structure.json",
                "source_class": "structure",
                "license_status": "user_supplied",
                "planned_actions_count": 2,
                "import_action_index": 0,
                "estimated_world_mutations": {
                    "node_writes": 5,
                    "mapblock_churn": 3,
                    "media_files": 0,
                    "entity_definitions": 0,
                    "manual_review_items": 1,
                },
                "apply_plan_status": "planned",
            },
            "operator_review": {
                "smoke_status": "ready",
                "review_status": "ready",
                "machine_promotable": True,
                "promotion_status": "ready_for_operator_promotion",
            },
            "apply": {
                "task_id": "compat:public-safe-structure-staging-pilot:0:apply-smoke",
                "task_status": "completed",
                "step_count": 3,
                "progress_current": 3,
                "progress_total": 3,
                "apply_summary_status": "completed",
                "completed_task_count": 1,
                "node_writes_actual": 5,
                "mapblock_churn_actual": 3,
                "rollback_record_count": 3,
                "node_writes_verified": 5,
                "param_round_trip_checked": True,
            },
            "rollback": {
                "plan_status": "success",
                "apply_rollback_ref_count": 3,
                "plan_record_count": 3,
                "planned_node_writes": 5,
                "planned_mapblock_churn": 3,
                "task_id": "compat:public-safe-structure-staging-pilot:0:rollback-smoke",
                "task_status": "completed",
                "step_count": 3,
                "progress_current": 3,
                "progress_total": 3,
                "nodes_reverted": 5,
                "rollback_execution_records": 3,
            },
        },
        "refusal_gates": {
            "missing_approval": {
                "name": "missing_approval",
                "status": "blocked",
                "reason": "approval_required",
                "expected_reason": "approval_required",
                "changed": 0,
                "writes_attempted": 0,
                "passed": True,
            },
            "missing_rollback_policy": {
                "name": "missing_rollback_policy",
                "status": "blocked",
                "reason": "rollback_policy_not_mutating",
                "expected_reason": "rollback_policy_not_mutating",
                "changed": 0,
                "writes_attempted": 0,
                "passed": True,
            },
            "unsafe_private_payload": {
                "name": "unsafe_private_payload",
                "status": "blocked",
                "reason": "payload_rejected",
                "expected_reason": "payload_rejected",
                "changed": 0,
                "writes_attempted": 0,
                "passed": True,
            },
            "non_staging_target": {
                "name": "non_staging_target",
                "status": "blocked",
                "reason": "staging_target_required",
                "expected_reason": "staging_target_required",
                "changed": 0,
                "writes_attempted": 0,
                "passed": True,
            },
            "over_budget": {
                "name": "over_budget",
                "status": "blocked",
                "reason": "node_write_budget_exceeded",
                "expected_reason": "node_write_budget_exceeded",
                "changed": 0,
                "writes_attempted": 0,
                "passed": True,
            },
        },
        "benchmark_coverage": {
            "status": "pass",
            "expected_node_writes": 5,
            "actual_node_writes": 5,
            "expected_mapblock_churn": 3,
            "actual_mapblock_churn": 3,
            "expected_apply_chunks": 3,
            "actual_apply_chunks": 3,
            "max_node_writes_total": 5,
            "max_node_writes_per_step": 2,
            "max_mapblock_churn_total": 3,
            "over_budget_refused": True,
            "mapblock_churn_recorded": True,
        },
        "safety": {
            "public_safe_output": True,
            "disposable_live_world_only": True,
            "staging_target_only": True,
            "world_mutation_performed": True,
            "world_mutation_scope": "disposable_synthetic_ai_runtime_staging_world",
            "rollback_execution_performed": True,
            "import_promotion_execution_performed": False,
            "assets_copied": False,
            "no_raw_assets": True,
            "no_provider_prompts": True,
            "no_family_world_coordinates": True,
            "no_live_family_world_mutation": True,
            "all_refusal_gates_passed": True,
        },
        "bounds": {
            "max_bytes": 30000,
            "output_bytes": 0,
            "truncated": False,
        },
    }
    payload["bounds"]["output_bytes"] = len(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    )
    return payload


class CompatImportStagingPilotTests(unittest.TestCase):
    def test_build_pilot_context_uses_public_safe_inventory_dry_run_and_review(self):
        pilot = load_pilot_module()

        context = pilot.build_pilot_context(FIXTURE, "2026-06-29T00:00:00Z")

        self.assertEqual(
            context["context_kind"],
            "ai_native_compat_import_staging_pilot_context",
        )
        self.assertEqual(context["inventory"]["status"], "ready_for_import_preview")
        self.assertTrue(context["inventory"]["ready"])
        self.assertEqual(context["dry_run"]["source_class"], "structure")
        self.assertEqual(context["dry_run"]["license_status"], "user_supplied")
        self.assertEqual(context["operator_review"]["smoke_status"], "ready")
        self.assertEqual(context["operator_review"]["review_status"], "ready")
        self.assertTrue(context["operator_review"]["machine_promotable"])
        self.assertEqual(
            context["operator_review"]["promotion_status"],
            "ready_for_operator_promotion",
        )
        self.assertEqual(context["apply_task"]["chunk_count"], 3)
        self.assertEqual(context["apply_task"]["placement_count"], 5)
        self.assertEqual(context["expected"]["mapblock_churn"], 3)
        serialized = json.dumps(context)
        self.assertIsNone(PRIVATE_PATTERNS.search(serialized))

    def test_validate_live_result_accepts_complete_public_safe_pilot(self):
        pilot = load_pilot_module()

        evidence = pilot.validate_live_result(sample_payload())

        self.assertEqual(evidence["compat_import_staging_pilot_status"], "pass")
        self.assertEqual(evidence["compat_import_node_writes"], 5)
        self.assertEqual(evidence["compat_import_mapblock_churn"], 3)
        self.assertEqual(evidence["compat_import_refusal_gates"], 5)

    def test_validate_live_result_rejects_missing_refusal_gate(self):
        pilot = load_pilot_module()
        payload = sample_payload()
        del payload["refusal_gates"]["missing_rollback_policy"]

        with self.assertRaisesRegex(ValueError, "missing_rollback_policy"):
            pilot.validate_live_result(payload)

    def test_validate_live_result_rejects_private_or_raw_payload_terms(self):
        pilot = load_pilot_module()
        payload = sample_payload()
        payload["workflow"]["dry_run"]["source_id"] = "asset_payload"

        with self.assertRaisesRegex(ValueError, "private content"):
            pilot.validate_live_result(payload)

    def test_validate_live_result_rejects_non_staging_gate_mutation(self):
        pilot = load_pilot_module()
        payload = sample_payload()
        payload["refusal_gates"]["non_staging_target"]["writes_attempted"] = 1

        with self.assertRaisesRegex(ValueError, "non_staging_target mutated"):
            pilot.validate_live_result(payload)

    def test_validate_live_result_rejects_mutation_budget_drift(self):
        pilot = load_pilot_module()
        payload = sample_payload()
        payload["benchmark_coverage"]["actual_mapblock_churn"] = 2

        with self.assertRaisesRegex(ValueError, "actual_mapblock_churn"):
            pilot.validate_live_result(payload)

    def test_validate_live_result_does_not_mutate_input_payload(self):
        pilot = load_pilot_module()
        payload = sample_payload()
        original = copy.deepcopy(payload)

        pilot.validate_live_result(payload)

        self.assertEqual(payload, original)


if __name__ == "__main__":
    unittest.main()
