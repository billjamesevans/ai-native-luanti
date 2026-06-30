import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
QUALITY_GATE = ROOT / "util" / "ai_native_agent_quality_gate.py"


def load_quality_gate_module():
    spec = importlib.util.spec_from_file_location("ai_native_agent_quality_gate_test", QUALITY_GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def candidate_queue_payload(**overrides):
    payload = {
        "schema_version": 1,
        "artifact_kind": "ai_native_agent_eval_candidate_queue",
        "generated_at": "2026-06-30T18:00:00Z",
        "status": "ready",
        "source_summary": {
            "candidates_total": 9,
            "ready_for_prompt_eval": 9,
            "ready_for_adapter_contract_eval": 0,
            "manual_review_required": 0,
            "adapter_contract_failures_active": 0,
            "adapter_contract_failures_resolved": 1,
            "verified_live_probe_cases_read": 30,
            "operator_feedback_events_read": 61,
            "operator_labels_applied": 4,
        },
        "candidates": [],
        "violations": [],
        "safety": {"public_safe_output": True, "no_world_mutation": True},
    }
    payload.update(overrides)
    return payload


def case_pack_payload(**overrides):
    payload = {
        "schema_version": 1,
        "artifact_kind": "ai_native_agent_prompt_eval_case_pack",
        "generated_at": "2026-06-30T18:00:00Z",
        "status": "ready",
        "summary": {
            "cases_total": 6,
            "ready_for_runtime_prompt_eval": 6,
            "requires_maintainer_review_before_default_gate": True,
        },
        "cases": [],
        "violations": [],
        "safety": {"public_safe_output": True, "no_world_mutation": True},
    }
    payload.update(overrides)
    return payload


def review_queue_payload(**overrides):
    payload = {
        "schema_version": 1,
        "artifact_kind": "ai_native_agent_review_queue",
        "generated_at": "2026-06-30T18:00:00Z",
        "status": "ready",
        "summary": {
            "action_items_total": 0,
            "adapter_contract_failures_active": 0,
            "adapter_contract_failures_resolved": 1,
            "candidates_total": 9,
            "case_pack_cases_total": 6,
            "case_pack_unique_cases_total": 6,
            "manual_review_required": 0,
            "operator_feedback_events_read": 61,
            "operator_labels_applied": 4,
            "ready_for_adapter_contract_eval": 0,
            "ready_for_prompt_eval": 9,
            "review_items_retained": 0,
            "review_items_total": 0,
            "unique_ready_for_prompt_eval": 6,
            "verified_live_probe_cases_read": 30,
        },
        "action_items": [],
        "review_items": [],
        "violations": [],
        "safety": {"public_safe_output": True, "no_world_mutation": True},
    }
    payload.update(overrides)
    return payload


def adapter_eval_payload(**overrides):
    payload = {
        "schema_version": 1,
        "artifact_kind": "ai_native_agent_adapter_contract_eval_result",
        "generated_at": "2026-06-30T18:00:00Z",
        "status": "empty",
        "summary": {
            "source_candidates_total": 9,
            "selected_candidates_total": 0,
            "replayed_total": 0,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
        },
        "cases": [],
        "violations": [],
        "safety": {"public_safe_output": True, "no_world_mutation": True},
    }
    payload.update(overrides)
    return payload


class AgentQualityGateTests(unittest.TestCase):
    def test_ready_artifacts_pass_quality_gate(self):
        module = load_quality_gate_module()

        report = module.build_quality_gate(
            candidate_queue=candidate_queue_payload(),
            case_pack=case_pack_payload(),
            review=review_queue_payload(),
            adapter_eval=adapter_eval_payload(),
            generated_at="2026-06-30T18:05:00Z",
        )

        self.assertEqual(report["artifact_kind"], "ai_native_agent_quality_gate")
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["attention"], [])
        self.assertEqual(report["violations"], [])
        self.assertTrue(report["safety"]["public_safe_output"])

    def test_review_queue_attention_keeps_gate_attention_not_fail(self):
        module = load_quality_gate_module()

        review = review_queue_payload(
            status="attention",
            summary={
                **review_queue_payload()["summary"],
                "action_items_total": 1,
                "review_items_total": 1,
                "manual_review_required": 1,
            },
            action_items=[{"action": "review_and_label_manual_candidates"}],
            review_items=[{"candidate_id": "agent-eval-candidate:manual"}],
        )
        candidate = candidate_queue_payload()
        candidate["source_summary"]["manual_review_required"] = 1
        report = module.build_quality_gate(
            candidate_queue=candidate,
            case_pack=case_pack_payload(),
            review=review,
            adapter_eval=adapter_eval_payload(),
            generated_at="2026-06-30T18:05:00Z",
        )

        self.assertEqual(report["status"], "attention")
        self.assertTrue(any(item["kind"] == "manual_review_required" for item in report["attention"]))
        self.assertEqual(report["violations"], [])

    def test_adapter_contract_eval_failure_fails_gate(self):
        module = load_quality_gate_module()

        report = module.build_quality_gate(
            candidate_queue=candidate_queue_payload(),
            case_pack=case_pack_payload(),
            review=review_queue_payload(),
            adapter_eval=adapter_eval_payload(
                status="fail",
                summary={
                    "source_candidates_total": 9,
                    "selected_candidates_total": 1,
                    "replayed_total": 1,
                    "passed": 0,
                    "failed": 1,
                    "skipped": 0,
                },
            ),
            generated_at="2026-06-30T18:05:00Z",
        )

        self.assertEqual(report["status"], "fail")
        self.assertTrue(any(item["kind"] == "adapter_contract_eval_not_passing" for item in report["violations"]))

    def test_missing_adapter_replay_for_ready_contract_candidate_is_attention(self):
        module = load_quality_gate_module()
        candidate = candidate_queue_payload()
        candidate["source_summary"]["ready_for_adapter_contract_eval"] = 1

        report = module.build_quality_gate(
            candidate_queue=candidate,
            case_pack=case_pack_payload(),
            review=review_queue_payload(),
            generated_at="2026-06-30T18:05:00Z",
        )

        self.assertEqual(report["status"], "attention")
        self.assertTrue(any(item["kind"] == "adapter_contract_replay_missing" for item in report["attention"]))

    def test_cli_writes_quality_gate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            candidate_queue = root / "candidate-queue.json"
            case_pack = root / "case-pack.json"
            review_queue = root / "review-queue.json"
            adapter_eval = root / "adapter-contract-eval.json"
            output = root / "quality-gate.json"
            candidate_queue.write_text(json.dumps(candidate_queue_payload()), encoding="utf-8")
            case_pack.write_text(json.dumps(case_pack_payload()), encoding="utf-8")
            review_queue.write_text(json.dumps(review_queue_payload()), encoding="utf-8")
            adapter_eval.write_text(json.dumps(adapter_eval_payload()), encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(QUALITY_GATE),
                    "--root",
                    str(root),
                    "--candidate-queue",
                    str(candidate_queue),
                    "--case-pack",
                    str(case_pack),
                    "--review-queue",
                    str(review_queue),
                    "--adapter-contract-eval",
                    str(adapter_eval),
                    "--output",
                    str(output),
                    "--generated-at",
                    "2026-06-30T18:05:00Z",
                ],
                cwd=ROOT,
                check=False,
                text=True,
                capture_output=True,
            )
            summary = json.loads(completed.stdout)
            report = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(summary["quality_gate_status"], "pass")
        self.assertEqual(report["status"], "pass")


if __name__ == "__main__":
    unittest.main()
