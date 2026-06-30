import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
REVIEW = ROOT / "util" / "ai_native_agent_review_queue.py"


def load_review_module():
    spec = importlib.util.spec_from_file_location("ai_native_agent_review_queue_test", REVIEW)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def candidate_queue_payload(*, attention=True):
    candidates = [
        {
            "candidate_id": "agent-eval-candidate:fire",
            "source_kind": "disposable_live_ai_runtime_nova_auto_apply_probe",
            "prompt": "build a fire",
            "case_hint": "build_fire",
            "review_status": "candidate_ready",
            "ready_for_prompt_eval": True,
            "ready_for_adapter_contract_eval": False,
            "expected": {
                "action": "build",
                "build_kind": "fire",
                "build_material_name": "fire",
                "planned_node_writes": 1,
                "forbidden_extra_structure": True,
            },
            "observed": {
                "live_probe_case_id": "fire_simple",
                "tool_decision_source": "agents_sdk_function_tool",
                "required_tool_calls_satisfied": True,
            },
        },
    ]
    source_summary = {
        "candidates_total": 1,
        "manual_review_required": 0,
        "ready_for_prompt_eval": 1,
        "ready_for_adapter_contract_eval": 0,
        "adapter_contract_failures_active": 0,
        "adapter_contract_failures_resolved": 1,
        "verified_live_probe_cases_read": 5,
        "operator_feedback_events_read": 0,
        "operator_labels_applied": 0,
    }
    if attention:
        candidates.extend([
            {
                "candidate_id": "agent-eval-candidate:unknown",
                "source_kind": "agents_sdk_request_response",
                "prompt": "build something cool",
                "case_hint": "manual_review_required",
                "priority": "normal",
                "review_status": "manual_review_required",
                "ready_for_prompt_eval": False,
                "ready_for_adapter_contract_eval": False,
                "expected": {},
                "observed": {
                    "selected_option_id": "platform",
                    "tool_decision_source": "agents_sdk_function_tool",
                    "required_tool_calls_satisfied": True,
                },
            },
            {
                "candidate_id": "agent-eval-candidate:contract",
                "source_kind": "agents_sdk_request_response",
                "prompt": "build me a tower",
                "case_hint": "generated_tower_wall",
                "priority": "high",
                "review_status": "manual_review_required",
                "ready_for_prompt_eval": False,
                "ready_for_adapter_contract_eval": True,
                "adapter_contract_review_status": "adapter_contract_regression",
                "expected": {
                    "action": "build",
                    "build_kind": "wall",
                    "build_material_name": "stone",
                    "planned_node_writes": 16,
                },
                "observed": {
                    "selected_option_id": "generated_tower_wall",
                    "tool_decision_source": "adapter_fallback_after_agent_missing_required_tool",
                    "required_tool_calls_satisfied": False,
                    "missing_required_tool_calls": ["propose_build_option"],
                },
            },
        ])
        source_summary.update({
            "candidates_total": 3,
            "manual_review_required": 2,
            "ready_for_prompt_eval": 1,
            "ready_for_adapter_contract_eval": 1,
            "adapter_contract_failures_active": 1,
        })
    return {
        "schema_version": 1,
        "artifact_kind": "ai_native_agent_eval_candidate_queue",
        "generated_at": "2026-06-30T16:20:00Z",
        "status": "ready",
        "source_summary": source_summary,
        "candidates": candidates,
        "safety": {"public_safe_output": True, "no_world_mutation": True},
    }


def case_pack_payload():
    return {
        "schema_version": 1,
        "artifact_kind": "ai_native_agent_prompt_eval_case_pack",
        "generated_at": "2026-06-30T16:21:00Z",
        "status": "ready",
        "summary": {
            "cases_total": 1,
            "ready_for_runtime_prompt_eval": 1,
            "requires_maintainer_review_before_default_gate": True,
        },
        "cases": [
            {
                "case_id": "promoted_build_fire",
                "case_hint": "build_fire",
                "prompt": "build a fire",
                "expected": {
                    "action": "build",
                    "build_kind": "fire",
                    "build_material_name": "fire",
                    "planned_node_writes": 1,
                },
            }
        ],
        "safety": {"public_safe_output": True, "no_world_mutation": True},
    }


class AgentReviewQueueTests(unittest.TestCase):
    def test_builds_attention_review_queue_from_manual_and_contract_items(self):
        module = load_review_module()

        report = module.build_review_queue(
            candidate_queue_payload(attention=True),
            case_pack_payload(),
            generated_at="2026-06-30T16:25:00Z",
            candidate_queue_path="memory/queue.json",
            case_pack_path="memory/cases.json",
        )

        self.assertEqual(report["artifact_kind"], "ai_native_agent_review_queue")
        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["summary"]["review_items_total"], 2)
        self.assertEqual(report["summary"]["action_items_total"], 2)
        self.assertEqual(
            [item["action"] for item in report["action_items"]],
            ["run_adapter_contract_eval", "review_and_label_manual_candidates"],
        )
        self.assertEqual(report["review_items"][0]["review_reason"], "adapter_contract_eval_required")
        self.assertEqual(
            report["review_items"][0]["observed"]["missing_required_tool_calls"],
            ["propose_build_option"],
        )
        self.assertTrue(report["safety"]["public_safe_output"])
        self.assertFalse(report["bounds"]["truncated"])

    def test_clean_verified_queue_is_ready(self):
        module = load_review_module()

        report = module.build_review_queue(
            candidate_queue_payload(attention=False),
            case_pack_payload(),
            generated_at="2026-06-30T16:25:00Z",
        )

        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["summary"]["review_items_total"], 0)
        self.assertEqual(report["summary"]["action_items_total"], 0)
        self.assertEqual(report["case_pack"]["case_hints"], ["build_fire"])

    def test_resolved_adapter_contract_evidence_is_not_manual_review_backlog(self):
        module = load_review_module()
        queue = candidate_queue_payload(attention=False)
        queue["candidates"].append({
            "candidate_id": "agent-eval-candidate:resolved-timeout",
            "source_kind": "agents_sdk_request_response",
            "prompt": "build a small shelter",
            "case_hint": "model_adapter_review",
            "priority": "high",
            "review_status": "needs_operator_label",
            "adapter_contract_review_status": "adapter_contract_resolved",
            "adapter_contract_resolution": {
                "status": "resolved_by_later_pass",
                "resolved_by_candidate_id": "agent-eval-candidate:later-pass",
                "required_tool_calls_satisfied": True,
            },
            "ready_for_prompt_eval": False,
            "ready_for_adapter_contract_eval": False,
            "expected": {"operator_must_label_expected_answer": True},
            "observed": {
                "selected_option_id": "generated_shelter_floor",
                "tool_decision_source": "offline_adapter_fallback_after_agent_timeout",
                "required_tool_calls_satisfied": False,
                "missing_required_tool_calls": [
                    "recall_build_prompt_memory",
                    "select_build_option",
                    "plan_build_actions",
                    "propose_build_option",
                ],
            },
        })
        queue["source_summary"]["candidates_total"] = 2
        queue["source_summary"]["manual_review_required"] = 0
        queue["source_summary"]["adapter_contract_failures_resolved"] = 2

        report = module.build_review_queue(
            queue,
            case_pack_payload(),
            generated_at="2026-06-30T16:25:00Z",
        )

        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["summary"]["review_items_total"], 0)
        self.assertEqual(report["summary"]["action_items_total"], 0)
        self.assertEqual(report["summary"]["adapter_contract_failures_resolved"], 2)

    def test_duplicate_ready_candidates_do_not_create_refresh_attention(self):
        module = load_review_module()
        queue = candidate_queue_payload(attention=False)
        duplicate = json.loads(json.dumps(queue["candidates"][0]))
        duplicate["candidate_id"] = "agent-eval-candidate:fire-retry"
        queue["candidates"].append(duplicate)
        queue["source_summary"]["candidates_total"] = 2
        queue["source_summary"]["ready_for_prompt_eval"] = 2

        report = module.build_review_queue(
            queue,
            case_pack_payload(),
            generated_at="2026-06-30T16:25:00Z",
        )

        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["summary"]["ready_for_prompt_eval"], 2)
        self.assertEqual(report["summary"]["unique_ready_for_prompt_eval"], 1)
        self.assertEqual(report["summary"]["action_items_total"], 0)

    def test_cli_writes_review_queue(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            candidate_queue = root / "queue.json"
            case_pack = root / "case-pack.json"
            output = root / "review.json"
            candidate_queue.write_text(json.dumps(candidate_queue_payload(attention=True)), encoding="utf-8")
            case_pack.write_text(json.dumps(case_pack_payload()), encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(REVIEW),
                    "--root",
                    str(root),
                    "--candidate-queue",
                    str(candidate_queue),
                    "--case-pack",
                    str(case_pack),
                    "--output",
                    str(output),
                    "--generated-at",
                    "2026-06-30T16:25:00Z",
                ],
                cwd=ROOT,
                check=False,
                text=True,
                capture_output=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            summary = json.loads(completed.stdout)
            report = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(summary["review_queue_status"], "attention")
        self.assertEqual(summary["review_items_total"], 2)
        self.assertEqual(report["status"], "attention")
        self.assertEqual(report["summary"]["ready_for_adapter_contract_eval"], 1)


if __name__ == "__main__":
    unittest.main()
