import importlib.util
import json
import pathlib
import re
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
CLI = ROOT / "util" / "ai_native_operator_action_approval_receipt.py"
DOC = ROOT / "doc" / "ai-native-runtime" / "operator-status-package.md"
README = ROOT / "doc" / "ai-native-runtime" / "README.md"
PRIVATE_PATTERNS = re.compile(
    r"/Users/|minecraftpi|192\.168|spacebase|themepark|showcase100|"
    r"disneyland100|sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY|"
    r"private_prompt|asset_payload",
    re.I,
)


def load_receipt_module():
    assert CLI.is_file(), f"missing {CLI}"
    spec = importlib.util.spec_from_file_location("ai_native_operator_action_approval_receipt", CLI)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _references(bucket, value):
    refs = {"task_ids": [], "rollback_records": [], "source_artifacts": []}
    refs[bucket] = [value]
    return refs


def sample_approval_plan():
    return {
        "schema_version": 1,
        "plan_kind": "ai_native_operator_action_approval_plan",
        "status": "attention",
        "generated_at": "2026-06-29T02:00:00Z",
        "source_report": {
            "report_kind": "ai_native_operator_control_report",
            "status": "attention",
            "generated_at": "2026-06-29T01:00:00Z",
            "path": "/Users/billevans/private/showcase100/operator-control-report.json",
        },
        "operator_actions": {
            "mode": "approval_required",
            "mutation_performed": False,
            "candidate_actions_total": 5,
            "truncated": False,
        },
        "summary": {
            "actions_total": 5,
            "source_items_total": 5,
            "by_target_kind": {"task": 2, "rollback": 1, "import_promotion": 1, "benchmark_gate": 1},
            "by_status": {"running": 1, "blocked": 1, "available": 1, "ready": 1, "fail": 1},
            "by_safe_next_action": {},
            "attention_required": True,
            "unsupported_actions": 0,
        },
        "approval_groups": [
            {
                "target_kind": "task",
                "target_id": "task:running",
                "status": "running",
                "safe_next_action": "inspect_task_before_action",
                "approval_kind": "task_cancel_retry_review",
                "approval_required": True,
                "dry_run_only": True,
                "will_mutate": False,
                "supported": True,
                "unsupported_reasons": [],
                "blocked_reasons": [],
                "required_capabilities": ["task.inspect", "task.cancel.review"],
                "prerequisites": ["inspect_task_status", "confirm_task_owner_and_capabilities"],
                "references": _references("task_ids", "task:running"),
            },
            {
                "target_kind": "task",
                "target_id": "task:repair-blocked",
                "status": "blocked",
                "safe_next_action": "review_blocked_task_before_retry",
                "approval_kind": "task_retry_review",
                "approval_required": True,
                "dry_run_only": True,
                "will_mutate": False,
                "supported": True,
                "unsupported_reasons": [],
                "blocked_reasons": ["task_blocked"],
                "required_capabilities": ["task.inspect", "task.retry.review"],
                "prerequisites": ["inspect_blocked_result", "confirm_retry_budget"],
                "references": _references("task_ids", "task:repair-blocked"),
            },
            {
                "target_kind": "rollback",
                "target_id": "rollback:record-one",
                "status": "available",
                "safe_next_action": "review_rollback_record_before_execution",
                "approval_kind": "rollback_execution_review",
                "approval_required": True,
                "dry_run_only": True,
                "will_mutate": False,
                "supported": True,
                "unsupported_reasons": [],
                "blocked_reasons": [],
                "required_capabilities": ["rollback.review", "rollback.execute.review"],
                "prerequisites": ["inspect_rollback_record", "confirm_rollback_scope"],
                "references": _references("rollback_records", "rollback:record-one"),
            },
            {
                "target_kind": "import_promotion",
                "target_id": "promotion:ready",
                "status": "ready",
                "safe_next_action": "review_promotion_package_before_apply",
                "approval_kind": "import_apply_review",
                "approval_required": True,
                "dry_run_only": True,
                "will_mutate": False,
                "supported": True,
                "unsupported_reasons": [],
                "blocked_reasons": [],
                "required_capabilities": ["import.promotion.review", "import.apply.review"],
                "prerequisites": ["inspect_promotion_package", "confirm_operator_approval"],
                "references": _references("source_artifacts", "promotion:ready"),
            },
            {
                "target_kind": "benchmark_gate",
                "target_id": "gate:low-power",
                "status": "fail",
                "safe_next_action": "review_benchmark_failure",
                "approval_kind": "benchmark_failure_review",
                "approval_required": True,
                "dry_run_only": True,
                "will_mutate": False,
                "supported": True,
                "unsupported_reasons": [],
                "blocked_reasons": ["benchmark_gate_failed"],
                "required_capabilities": ["benchmark.review"],
                "prerequisites": ["inspect_benchmark_gate_manifest", "compare_accepted_baseline"],
                "references": _references("source_artifacts", "gate:low-power"),
            },
        ],
        "safety": {
            "public_safe_output": True,
            "dry_run_only": True,
            "approval_required": True,
            "no_mutating_actions": True,
            "no_world_mutation": True,
            "no_task_mutation": True,
            "no_rollback_execution": True,
            "no_import_promotion_execution": True,
            "no_raw_assets": True,
            "no_provider_prompts": True,
            "no_family_world_coordinates": True,
        },
        "bounds": {
            "max_bytes": 20000,
            "output_bytes": 4500,
            "truncated": False,
        },
    }


def sample_decision_document():
    return {
        "schema_version": 1,
        "decision_kind": "ai_native_operator_action_decision",
        "generated_at": "2026-06-29T02:05:00Z",
        "operator_id": "operator:local-review",
        "source_plan_generated_at": "2026-06-29T02:00:00Z",
        "max_plan_age_seconds": 600,
        "decisions": [
            {
                "target_kind": "task",
                "target_id": "task:running",
                "safe_next_action": "inspect_task_before_action",
                "decision_status": "denied",
                "prerequisites_acknowledged": ["inspect_task_status"],
                "operator_note": "leave running",
            },
            {
                "target_kind": "task",
                "target_id": "task:repair-blocked",
                "safe_next_action": "review_blocked_task_before_retry",
                "decision_status": "approved",
                "prerequisites_acknowledged": ["inspect_blocked_result", "confirm_retry_budget"],
                "operator_note": "retry after review",
            },
            {
                "target_kind": "rollback",
                "target_id": "rollback:record-one",
                "safe_next_action": "review_rollback_record_before_execution",
                "decision_status": "approved",
                "prerequisites_acknowledged": ["inspect_rollback_record", "confirm_rollback_scope"],
                "operator_note": "reviewed rollback scope",
            },
            {
                "target_kind": "import_promotion",
                "target_id": "promotion:ready",
                "safe_next_action": "review_promotion_package_before_apply",
                "decision_status": "needs_review",
                "prerequisites_acknowledged": ["inspect_promotion_package"],
                "operator_note": "needs another operator",
            },
            {
                "target_kind": "benchmark_gate",
                "target_id": "gate:low-power",
                "safe_next_action": "review_benchmark_failure",
                "decision_status": "approved",
                "prerequisites_acknowledged": [
                    "inspect_benchmark_gate_manifest",
                    "compare_accepted_baseline",
                ],
                "operator_note": "acknowledge follow-up",
            },
        ],
    }


class AIOperatorActionApprovalReceiptTests(unittest.TestCase):
    def assert_public_safe(self, payload):
        encoded = json.dumps(payload, sort_keys=True)
        self.assertLessEqual(len(encoded.encode("utf-8")), payload["bounds"]["max_bytes"])
        self.assertNotRegex(encoded, PRIVATE_PATTERNS)

    def test_build_receipt_records_approved_denied_and_needs_review_decisions(self):
        receipt_module = load_receipt_module()

        receipt = receipt_module.build_receipt(
            sample_approval_plan(),
            sample_decision_document(),
            generated_at="2026-06-29T02:05:00Z",
            source_path="local/benchmarks/run/ai-runtime-operator-action-approval-plan.json",
            max_bytes=36000,
        )

        self.assertEqual(receipt["schema_version"], 1)
        self.assertEqual(receipt["receipt_kind"], "ai_native_operator_action_approval_receipt")
        self.assertEqual(receipt["status"], "attention")
        self.assertEqual(receipt["source_plan"]["plan_kind"], "ai_native_operator_action_approval_plan")
        self.assertEqual(
            receipt["source_plan"]["path"],
            "local/benchmarks/run/ai-runtime-operator-action-approval-plan.json",
        )
        self.assertEqual(receipt["operator_decisions"]["mode"], "receipt_only")
        self.assertFalse(receipt["operator_decisions"]["mutation_performed"])
        self.assertEqual(receipt["operator_decisions"]["decisions_total"], 5)
        self.assertEqual(receipt["operator_decisions"]["approved_total"], 3)
        self.assertEqual(receipt["operator_decisions"]["denied_total"], 1)
        self.assertEqual(receipt["operator_decisions"]["needs_review_total"], 1)
        self.assertEqual(receipt["summary"]["by_target_kind"]["task"], 2)
        self.assertEqual(receipt["summary"]["by_decision_status"]["approved"], 3)
        self.assertTrue(receipt["summary"]["attention_required"])
        self.assertEqual(len(receipt["decisions"]), 5)

        by_target = {item["target_id"]: item for item in receipt["decisions"]}
        self.assertEqual(by_target["task:running"]["decision_status"], "denied")
        self.assertEqual(by_target["task:repair-blocked"]["decision_status"], "approved")
        self.assertIn("task.retry.review", by_target["task:repair-blocked"]["required_capabilities"])
        self.assertEqual(
            by_target["rollback:record-one"]["approval_kind"],
            "rollback_execution_review",
        )
        self.assertIn(
            "rollback.execute.review",
            by_target["rollback:record-one"]["required_capabilities"],
        )
        self.assertEqual(by_target["promotion:ready"]["decision_status"], "needs_review")
        self.assertEqual(
            by_target["gate:low-power"]["references"]["source_artifacts"],
            ["gate:low-power"],
        )
        for item in receipt["decisions"]:
            self.assertTrue(item["dry_run_only"])
            self.assertFalse(item["will_mutate"])
            self.assertFalse(item["mutation_performed"])
            self.assertIn("prerequisites_required", item)
            self.assertIn("prerequisites_acknowledged", item)
            self.assertIn("required_capabilities", item)
        self.assertGreater(receipt["safety"]["redactions_applied"], 0)
        self.assert_public_safe(receipt)

    def test_sample_decision_document_marks_plan_entries_as_needs_review(self):
        receipt_module = load_receipt_module()
        plan = sample_approval_plan()

        decision = receipt_module.sample_decision_document(
            plan,
            generated_at="2026-06-29T02:05:00Z",
        )
        receipt = receipt_module.build_receipt(
            plan,
            decision,
            generated_at="2026-06-29T02:05:00Z",
        )

        self.assertEqual(decision["decision_kind"], "ai_native_operator_action_decision")
        self.assertEqual(receipt["operator_decisions"]["approved_total"], 0)
        self.assertEqual(receipt["operator_decisions"]["needs_review_total"], 5)
        self.assertEqual(receipt["status"], "attention")
        self.assert_public_safe(receipt)

    def test_empty_plan_writes_empty_receipt(self):
        receipt_module = load_receipt_module()
        plan = sample_approval_plan()
        plan["status"] = "ready"
        plan["approval_groups"] = []
        plan["summary"]["actions_total"] = 0
        plan["operator_actions"]["candidate_actions_total"] = 0
        decision = receipt_module.sample_decision_document(plan, generated_at="2026-06-29T02:05:00Z")

        receipt = receipt_module.build_receipt(plan, decision, generated_at="2026-06-29T02:05:00Z")

        self.assertEqual(receipt["status"], "ready")
        self.assertEqual(receipt["decisions"], [])
        self.assertEqual(receipt["operator_decisions"]["decisions_total"], 0)
        self.assert_public_safe(receipt)

    def test_missing_plan_entry_is_rejected(self):
        receipt_module = load_receipt_module()
        decision = sample_decision_document()
        decision["decisions"][0]["target_id"] = "task:missing"

        with self.assertRaisesRegex(ValueError, "missing plan entry"):
            receipt_module.build_receipt(sample_approval_plan(), decision)

    def test_unsupported_plan_entry_is_rejected(self):
        receipt_module = load_receipt_module()
        plan = sample_approval_plan()
        plan["approval_groups"][0]["supported"] = False
        plan["approval_groups"][0]["unsupported_reasons"] = ["unsupported_safe_next_action"]

        with self.assertRaisesRegex(ValueError, "unsupported"):
            receipt_module.build_receipt(plan, sample_decision_document())

    def test_stale_plan_is_rejected(self):
        receipt_module = load_receipt_module()
        decision = sample_decision_document()
        decision["generated_at"] = "2026-06-29T03:30:00Z"
        decision["max_plan_age_seconds"] = 60

        with self.assertRaisesRegex(ValueError, "stale"):
            receipt_module.build_receipt(
                sample_approval_plan(),
                decision,
                generated_at="2026-06-29T03:30:00Z",
            )

    def test_private_decision_content_is_rejected(self):
        receipt_module = load_receipt_module()
        decision = sample_decision_document()
        decision["decisions"][0]["operator_note"] = "check /Users/billevans/private/themepark"

        with self.assertRaisesRegex(ValueError, "private"):
            receipt_module.build_receipt(sample_approval_plan(), decision)

    def test_approved_decision_requires_all_prerequisites_acknowledged(self):
        receipt_module = load_receipt_module()
        decision = sample_decision_document()
        decision["decisions"][1]["prerequisites_acknowledged"] = ["inspect_blocked_result"]

        with self.assertRaisesRegex(ValueError, "prerequisites"):
            receipt_module.build_receipt(sample_approval_plan(), decision)

    def test_mutating_safe_next_action_is_rejected(self):
        receipt_module = load_receipt_module()
        plan = sample_approval_plan()
        plan["approval_groups"][0]["safe_next_action"] = "execute_rollback_now"

        with self.assertRaisesRegex(ValueError, "mutating"):
            receipt_module.build_receipt(plan, sample_decision_document())

    def test_oversized_plan_is_rejected_before_receipt(self):
        receipt_module = load_receipt_module()
        plan = sample_approval_plan()
        plan["bounds"]["output_bytes"] = 25000
        plan["bounds"]["max_bytes"] = 20000

        with self.assertRaisesRegex(ValueError, "source plan exceeds"):
            receipt_module.build_receipt(plan, sample_decision_document())

    def test_cli_writes_json_and_text_receipts(self):
        receipt_module = load_receipt_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = pathlib.Path(tmpdir) / "approval-plan.json"
            decision_path = pathlib.Path(tmpdir) / "decision.json"
            json_output = pathlib.Path(tmpdir) / "receipt.json"
            text_output = pathlib.Path(tmpdir) / "receipt.txt"
            plan_path.write_text(json.dumps(sample_approval_plan()), encoding="utf-8")
            decision_path.write_text(json.dumps(sample_decision_document()), encoding="utf-8")

            json_exit = receipt_module.main([
                "--input",
                str(plan_path),
                "--decision",
                str(decision_path),
                "--output",
                str(json_output),
                "--generated-at",
                "2026-06-29T02:05:00Z",
                "--format",
                "json",
            ])
            text_exit = receipt_module.main([
                "--input",
                str(plan_path),
                "--decision",
                str(decision_path),
                "--output",
                str(text_output),
                "--generated-at",
                "2026-06-29T02:05:00Z",
                "--format",
                "text",
            ])

            self.assertEqual(json_exit, 0)
            self.assertEqual(text_exit, 0)
            receipt = json.loads(json_output.read_text(encoding="utf-8"))
            text = text_output.read_text(encoding="utf-8")
            self.assertEqual(receipt["receipt_kind"], "ai_native_operator_action_approval_receipt")
            self.assertIn("ai_native_operator_action_approval_receipt", text)
            self.assertIn("receipt_only", text)
            self.assertIn("rollback_execution_review", text)
            self.assertNotRegex(text, PRIVATE_PATTERNS)
            self.assert_public_safe(receipt)

    def test_docs_describe_operator_action_approval_receipt_adapter(self):
        readme = README.read_text(encoding="utf-8")
        doc = DOC.read_text(encoding="utf-8")

        self.assertIn("ai_native_operator_action_approval_receipt.py", readme)
        self.assertIn("ai-runtime-operator-action-approval-receipt.json", doc)
        self.assertIn("operator action approval receipt", doc)
        self.assertIn("receipt artifacts", doc)
        self.assertIn("approval/denial", doc)
        self.assertIn("receipt-only", doc)
        self.assertIn("no rollback execution", doc)


if __name__ == "__main__":
    unittest.main()
