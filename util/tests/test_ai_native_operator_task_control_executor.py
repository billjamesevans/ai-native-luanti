import importlib.util
import json
import pathlib
import re
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
CLI = ROOT / "util" / "ai_native_operator_task_control_executor.py"
DOC = ROOT / "doc" / "ai-native-runtime" / "operator-status-package.md"
README = ROOT / "doc" / "ai-native-runtime" / "README.md"
PRIVATE_PATTERNS = re.compile(
    r"/Users/|minecraftpi|192\.168|spacebase|themepark|showcase100|"
    r"disneyland100|(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY|"
    r"private_prompt|asset_payload",
    re.I,
)


def load_executor_module():
    assert CLI.is_file(), f"missing {CLI}"
    spec = importlib.util.spec_from_file_location("ai_native_operator_task_control_executor", CLI)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _task_decision(
    *,
    decision_id,
    target_id,
    approval_kind,
    safe_next_action,
    decision_status="approved",
    prerequisites_required=None,
    prerequisites_acknowledged=None,
    capabilities=None,
):
    required = prerequisites_required or ["inspect_task_status", "confirm_task_owner_and_capabilities"]
    acknowledged = prerequisites_acknowledged if prerequisites_acknowledged is not None else list(required)
    return {
        "decision_id": decision_id,
        "decision_status": decision_status,
        "target_kind": "task",
        "target_id": target_id,
        "target_status": "running" if approval_kind == "task_cancel_retry_review" else "blocked",
        "safe_next_action": safe_next_action,
        "approval_kind": approval_kind,
        "required_capabilities": capabilities or ["task.inspect", "task.cancel.review"],
        "prerequisites_required": required,
        "prerequisites_acknowledged": acknowledged,
        "operator_note": "synthetic task-control execution",
        "references": {"task_ids": [target_id], "rollback_records": [], "source_artifacts": []},
        "approval_required": True,
        "dry_run_only": True,
        "will_mutate": False,
        "mutation_performed": False,
        "receipt_only": True,
    }


def sample_receipt():
    return {
        "schema_version": 1,
        "receipt_kind": "ai_native_operator_action_approval_receipt",
        "status": "attention",
        "generated_at": "2026-06-29T03:00:00Z",
        "source_plan": {
            "plan_kind": "ai_native_operator_action_approval_plan",
            "status": "attention",
            "generated_at": "2026-06-29T02:00:00Z",
            "source_report_path": "/Users/billevans/private/themepark/operator-control-report.json",
            "path": "local/benchmarks/run/ai-runtime-operator-action-approval-plan.json",
        },
        "operator_decisions": {
            "mode": "receipt_only",
            "operator_id": "operator:task-control",
            "mutation_performed": False,
            "decisions_total": 5,
            "approved_total": 4,
            "denied_total": 1,
            "needs_review_total": 0,
            "truncated": False,
        },
        "summary": {
            "decisions_total": 5,
            "source_actions_total": 5,
            "by_decision_status": {"approved": 4, "denied": 1},
            "by_target_kind": {"task": 3, "rollback": 1, "import_promotion": 1},
            "by_approval_kind": {
                "task_cancel_retry_review": 1,
                "task_retry_review": 2,
                "rollback_execution_review": 1,
                "import_apply_review": 1,
            },
            "attention_required": True,
        },
        "decisions": [
            _task_decision(
                decision_id="decision:cancel-running",
                target_id="task:running",
                approval_kind="task_cancel_retry_review",
                safe_next_action="inspect_task_before_action",
                capabilities=["task.inspect", "task.cancel.review"],
            ),
            _task_decision(
                decision_id="decision:retry-blocked",
                target_id="task:repair-blocked",
                approval_kind="task_retry_review",
                safe_next_action="review_blocked_task_before_retry",
                prerequisites_required=["inspect_blocked_result", "confirm_retry_budget"],
                capabilities=["task.inspect", "task.retry.review"],
            ),
            _task_decision(
                decision_id="decision:denied",
                target_id="task:denied",
                approval_kind="task_retry_review",
                safe_next_action="review_blocked_task_before_retry",
                decision_status="denied",
                prerequisites_required=["inspect_blocked_result", "confirm_retry_budget"],
                capabilities=["task.inspect", "task.retry.review"],
            ),
            {
                "decision_id": "decision:rollback-rejected",
                "decision_status": "approved",
                "target_kind": "rollback",
                "target_id": "rollback:record-one",
                "target_status": "available",
                "safe_next_action": "review_rollback_record_before_execution",
                "approval_kind": "rollback_execution_review",
                "required_capabilities": ["rollback.review", "rollback.execute.review"],
                "prerequisites_required": ["inspect_rollback_record", "confirm_rollback_scope"],
                "prerequisites_acknowledged": ["inspect_rollback_record", "confirm_rollback_scope"],
                "operator_note": "should not execute",
                "references": {"task_ids": [], "rollback_records": ["rollback:record-one"], "source_artifacts": []},
                "approval_required": True,
                "dry_run_only": True,
                "will_mutate": False,
                "mutation_performed": False,
                "receipt_only": True,
            },
            {
                "decision_id": "decision:import-rejected",
                "decision_status": "approved",
                "target_kind": "import_promotion",
                "target_id": "promotion:ready",
                "target_status": "ready",
                "safe_next_action": "review_promotion_package_before_apply",
                "approval_kind": "import_apply_review",
                "required_capabilities": ["import.promotion.review", "import.apply.review"],
                "prerequisites_required": ["inspect_promotion_package", "confirm_operator_approval"],
                "prerequisites_acknowledged": ["inspect_promotion_package", "confirm_operator_approval"],
                "operator_note": "should not execute",
                "references": {"task_ids": [], "rollback_records": [], "source_artifacts": ["promotion:ready"]},
                "approval_required": True,
                "dry_run_only": True,
                "will_mutate": False,
                "mutation_performed": False,
                "receipt_only": True,
            },
        ],
        "safety": {
            "public_safe_output": True,
            "dry_run_only": True,
            "approval_required": True,
            "receipt_only": True,
            "no_mutating_actions": True,
            "no_world_mutation": True,
            "no_rollback_execution": True,
            "no_import_promotion_execution": True,
            "no_raw_assets": True,
            "no_provider_prompts": True,
            "no_family_world_coordinates": True,
        },
        "bounds": {
            "max_bytes": 22000,
            "output_bytes": 5000,
            "truncated": False,
        },
    }


def sample_task_state():
    return {
        "schema_version": 1,
        "state_kind": "ai_native_synthetic_task_control_state",
        "generated_at": "2026-06-29T03:00:00Z",
        "runtime_context": {
            "mode": "synthetic_task_control",
            "requires_live_pi": False,
            "requires_private_world": False,
            "world_mutation_performed": False,
        },
        "tasks": [
            {"task_id": "task:running", "status": "running", "owner": "agent:one", "retry_count": 0},
            {
                "task_id": "task:repair-blocked",
                "status": "blocked",
                "owner": "agent:one",
                "blocked_reason": "rollback_metadata_unavailable",
                "retry_count": 0,
            },
            {"task_id": "task:denied", "status": "blocked", "owner": "agent:one", "retry_count": 0},
        ],
        "safety": {
            "synthetic_only": True,
            "public_safe_output": True,
            "no_world_mutation": True,
        },
    }


class AIOperatorTaskControlExecutorTests(unittest.TestCase):
    def assert_public_safe(self, payload):
        encoded = json.dumps(payload, sort_keys=True)
        self.assertLessEqual(len(encoded.encode("utf-8")), payload["bounds"]["max_bytes"])
        self.assertNotRegex(encoded, PRIVATE_PATTERNS)

    def test_executes_approved_task_cancel_and_retry_only(self):
        executor = load_executor_module()

        result = executor.build_execution_result(
            sample_receipt(),
            sample_task_state(),
            generated_at="2026-06-29T03:05:00Z",
            source_path="local/benchmarks/run/ai-runtime-operator-action-approval-receipt.json",
            executor_capabilities=["task.inspect", "task.cancel", "task.retry"],
            max_bytes=36000,
        )

        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["execution_kind"], "ai_native_operator_action_execution_result")
        self.assertEqual(result["status"], "attention")
        self.assertEqual(result["source_receipt"]["receipt_kind"], "ai_native_operator_action_approval_receipt")
        self.assertEqual(
            result["source_receipt"]["path"],
            "local/benchmarks/run/ai-runtime-operator-action-approval-receipt.json",
        )
        self.assertEqual(result["operator_actions"]["mode"], "receipt_gated_task_control")
        self.assertTrue(result["operator_actions"]["task_state_mutation_performed"])
        self.assertFalse(result["operator_actions"]["world_mutation_performed"])
        self.assertEqual(result["summary"]["decisions_total"], 5)
        self.assertEqual(result["summary"]["executed_total"], 2)
        self.assertEqual(result["summary"]["rejected_total"], 3)
        self.assertEqual(result["summary"]["skipped_total"], 0)

        by_decision = {item["decision_id"]: item for item in result["results"]}
        self.assertEqual(by_decision["decision:cancel-running"]["status"], "executed")
        self.assertEqual(by_decision["decision:cancel-running"]["before_status"], "running")
        self.assertEqual(by_decision["decision:cancel-running"]["after_status"], "cancelled")
        self.assertEqual(by_decision["decision:cancel-running"]["operation"], "task.cancel")
        self.assertEqual(by_decision["decision:retry-blocked"]["status"], "executed")
        self.assertEqual(by_decision["decision:retry-blocked"]["before_status"], "blocked")
        self.assertEqual(by_decision["decision:retry-blocked"]["after_status"], "queued")
        self.assertEqual(by_decision["decision:retry-blocked"]["operation"], "task.retry")
        self.assertEqual(by_decision["decision:denied"]["status"], "rejected")
        self.assertEqual(by_decision["decision:denied"]["reason"], "decision_not_approved")
        self.assertEqual(by_decision["decision:rollback-rejected"]["status"], "rejected")
        self.assertEqual(by_decision["decision:rollback-rejected"]["reason"], "unsupported_approval_kind")
        self.assertEqual(by_decision["decision:import-rejected"]["reason"], "unsupported_approval_kind")

        final = {task["task_id"]: task for task in result["task_state_after"]["tasks"]}
        self.assertEqual(final["task:running"]["status"], "cancelled")
        self.assertEqual(final["task:repair-blocked"]["status"], "queued")
        self.assertEqual(final["task:repair-blocked"]["retry_count"], 1)
        self.assertEqual(final["task:denied"]["status"], "blocked")
        self.assertGreater(result["safety"]["redactions_applied"], 0)
        self.assert_public_safe(result)

    def test_missing_executor_capability_rejects_without_task_state_change(self):
        executor = load_executor_module()
        result = executor.build_execution_result(
            sample_receipt(),
            sample_task_state(),
            generated_at="2026-06-29T03:05:00Z",
            executor_capabilities=["task.inspect"],
        )

        by_decision = {item["decision_id"]: item for item in result["results"]}
        self.assertEqual(by_decision["decision:cancel-running"]["status"], "rejected")
        self.assertEqual(by_decision["decision:cancel-running"]["reason"], "missing_executor_capability")
        self.assertEqual(by_decision["decision:retry-blocked"]["reason"], "missing_executor_capability")
        final = {task["task_id"]: task for task in result["task_state_after"]["tasks"]}
        self.assertEqual(final["task:running"]["status"], "running")
        self.assertEqual(final["task:repair-blocked"]["status"], "blocked")
        self.assert_public_safe(result)

    def test_missing_prerequisite_rejects_approved_task_action(self):
        executor = load_executor_module()
        receipt = sample_receipt()
        receipt["decisions"][1]["prerequisites_acknowledged"] = ["inspect_blocked_result"]

        result = executor.build_execution_result(
            receipt,
            sample_task_state(),
            generated_at="2026-06-29T03:05:00Z",
            executor_capabilities=["task.inspect", "task.cancel", "task.retry"],
        )

        by_decision = {item["decision_id"]: item for item in result["results"]}
        self.assertEqual(by_decision["decision:retry-blocked"]["status"], "rejected")
        self.assertEqual(by_decision["decision:retry-blocked"]["reason"], "missing_acknowledged_prerequisite")
        final = {task["task_id"]: task for task in result["task_state_after"]["tasks"]}
        self.assertEqual(final["task:repair-blocked"]["status"], "blocked")
        self.assert_public_safe(result)

    def test_stale_receipt_is_rejected_before_execution(self):
        executor = load_executor_module()

        with self.assertRaisesRegex(ValueError, "stale"):
            executor.build_execution_result(
                sample_receipt(),
                sample_task_state(),
                generated_at="2026-06-29T04:30:00Z",
                max_receipt_age_seconds=60,
            )

    def test_private_receipt_content_is_rejected_before_execution(self):
        executor = load_executor_module()
        receipt = sample_receipt()
        receipt["decisions"][0]["operator_note"] = "inspect /Users/billevans/private/spacebase"

        with self.assertRaisesRegex(ValueError, "private"):
            executor.build_execution_result(
                receipt,
                sample_task_state(),
                generated_at="2026-06-29T03:05:00Z",
            )

    def test_mutating_safe_next_action_is_rejected_before_execution(self):
        executor = load_executor_module()
        receipt = sample_receipt()
        receipt["decisions"][0]["safe_next_action"] = "execute_rollback_now"

        with self.assertRaisesRegex(ValueError, "mutating"):
            executor.build_execution_result(
                receipt,
                sample_task_state(),
                generated_at="2026-06-29T03:05:00Z",
            )

    def test_oversized_receipt_is_rejected_before_execution(self):
        executor = load_executor_module()
        receipt = sample_receipt()
        receipt["bounds"]["output_bytes"] = 30000

        with self.assertRaisesRegex(ValueError, "source receipt exceeds"):
            executor.build_execution_result(receipt, sample_task_state())

    def test_sample_task_state_for_empty_receipt_produces_empty_result(self):
        executor = load_executor_module()
        receipt = sample_receipt()
        receipt["status"] = "ready"
        receipt["decisions"] = []
        receipt["summary"]["decisions_total"] = 0
        receipt["operator_decisions"]["decisions_total"] = 0

        state = executor.sample_task_state_for_receipt(receipt)
        result = executor.build_execution_result(receipt, state, generated_at="2026-06-29T03:05:00Z")

        self.assertEqual(state["tasks"], [])
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["summary"]["decisions_total"], 0)
        self.assertFalse(result["operator_actions"]["task_state_mutation_performed"])
        self.assert_public_safe(result)

    def test_cli_writes_json_and_text_execution_results(self):
        executor = load_executor_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            receipt_path = pathlib.Path(tmpdir) / "approval-receipt.json"
            state_path = pathlib.Path(tmpdir) / "task-state.json"
            json_output = pathlib.Path(tmpdir) / "execution-result.json"
            text_output = pathlib.Path(tmpdir) / "execution-result.txt"
            receipt_path.write_text(json.dumps(sample_receipt()), encoding="utf-8")
            state_path.write_text(json.dumps(sample_task_state()), encoding="utf-8")

            json_exit = executor.main([
                "--input",
                str(receipt_path),
                "--state",
                str(state_path),
                "--output",
                str(json_output),
                "--generated-at",
                "2026-06-29T03:05:00Z",
                "--capability",
                "task.inspect",
                "--capability",
                "task.cancel",
                "--capability",
                "task.retry",
                "--format",
                "json",
            ])
            text_exit = executor.main([
                "--input",
                str(receipt_path),
                "--state",
                str(state_path),
                "--output",
                str(text_output),
                "--generated-at",
                "2026-06-29T03:05:00Z",
                "--capability",
                "task.inspect",
                "--capability",
                "task.cancel",
                "--capability",
                "task.retry",
                "--format",
                "text",
            ])

            self.assertEqual(json_exit, 0)
            self.assertEqual(text_exit, 0)
            result = json.loads(json_output.read_text(encoding="utf-8"))
            text = text_output.read_text(encoding="utf-8")
            self.assertEqual(result["execution_kind"], "ai_native_operator_action_execution_result")
            self.assertIn("ai_native_operator_action_execution_result", text)
            self.assertIn("receipt_gated_task_control", text)
            self.assertIn("task.cancel", text)
            self.assertNotRegex(text, PRIVATE_PATTERNS)
            self.assert_public_safe(result)

    def test_docs_describe_receipt_gated_task_control_executor(self):
        readme = README.read_text(encoding="utf-8")
        doc = DOC.read_text(encoding="utf-8")

        self.assertIn("ai_native_operator_task_control_executor.py", readme)
        self.assertIn("ai-runtime-operator-action-execution-result.json", doc)
        self.assertIn("receipt-gated task control executor", doc)
        self.assertIn("task cancel/retry only", doc)
        self.assertIn("no rollback execution", doc)
        self.assertIn("no import promotion execution", doc)
        self.assertIn("no world mutation", doc)


if __name__ == "__main__":
    unittest.main()
