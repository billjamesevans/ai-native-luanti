import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
QUALITY_GATE = ROOT / "util" / "ai_native_agent_quality_gate.py"
COMPAT_PILOT_TEST = ROOT / "util" / "tests" / "test_ai_native_compat_import_staging_pilot.py"


def load_quality_gate_module():
    spec = importlib.util.spec_from_file_location("ai_native_agent_quality_gate_test", QUALITY_GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def compat_import_staging_pilot_payload(**overrides):
    spec = importlib.util.spec_from_file_location(
        "ai_native_compat_import_staging_pilot_fixture",
        COMPAT_PILOT_TEST,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    payload = module.sample_payload()
    payload.update(overrides)
    return payload


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


def live_prompt_eval_payload(**overrides):
    payload = {
        "schema_version": 1,
        "live_result_kind": "ai_native_agent_prompt_eval_live_result",
        "generated_at": "2026-06-30T18:00:00Z",
        "runtime_context": {
            "mode": "disposable_live_ai_runtime_agent_prompt_eval_probe",
            "gameid": "ai_runtime",
            "command": "/ai_agent_eval",
            "adapter_mode": "agents_sdk_sidecar",
            "requires_live_pi": False,
            "requires_private_world": False,
            "requires_private_assets": False,
            "requires_model_network": True,
            "world_mutation_performed": False,
            "world_mutation_scope": "read_only_prompt_eval_pending_approval_cleanup",
        },
        "command": {
            "fire_case_status": "pass",
            "fire_case_ok": True,
            "fire_case_count": 0,
            "registered": True,
            "server_privilege_required": True,
        },
        "prompt_eval": {
            "status": "pass",
            "ok": True,
            "owner": "PromptEvalLive",
            "cases_total": 5,
            "cases_passed": 5,
            "cases_failed": 0,
            "case_ids": {
                "build_fire": True,
                "fire_only_strict": True,
                "tnt_wall": True,
                "agentic_build_planner": True,
                "model": True,
            },
            "cases": [
                {
                    "case_id": "build_fire",
                    "status": "pass",
                    "ok": True,
                    "prompt": "build a fire",
                    "route": "agentic_build_planner",
                    "build_kind": "fire",
                    "build_material_name": "fire",
                    "planned_node_writes": 1,
                    "selected_candidate_id": "fire",
                    "adapter_selected_candidate_id": "fire",
                    "model_selected_candidate_id": "fire",
                    "candidate_count": 4,
                    "adapter_tool_decision_source": "agents_sdk_function_tool",
                    "adapter_required_tool_calls": [
                        "recall_build_prompt_memory",
                        "select_build_option",
                        "plan_build_actions",
                    ],
                    "adapter_missing_required_tool_calls": [],
                    "adapter_required_tool_calls_satisfied": True,
                    "adapter_tool_trace_names": [
                        "recall_build_prompt_memory",
                        "select_build_option",
                        "plan_build_actions",
                    ],
                    "adapter_build_action_plan_status": "ready",
                    "adapter_build_action_plan_step_count": 3,
                    "adapter_build_action_plan_world_mutation_authority": "luanti",
                },
                {
                    "case_id": "fire_only_strict",
                    "status": "pass",
                    "ok": True,
                    "prompt": "build me a fire and only a fire",
                    "route": "agentic_build_planner",
                    "build_kind": "fire",
                    "build_material_name": "fire",
                    "planned_node_writes": 1,
                    "selected_candidate_id": "fire",
                    "adapter_selected_candidate_id": "fire",
                    "model_selected_candidate_id": "fire",
                    "candidate_count": 4,
                    "adapter_tool_decision_source": "agents_sdk_function_tool",
                    "adapter_required_tool_calls": [
                        "recall_build_prompt_memory",
                        "select_build_option",
                        "plan_build_actions",
                    ],
                    "adapter_missing_required_tool_calls": [],
                    "adapter_required_tool_calls_satisfied": True,
                    "adapter_tool_trace_names": [
                        "recall_build_prompt_memory",
                        "select_build_option",
                        "plan_build_actions",
                    ],
                    "adapter_build_action_plan_status": "ready",
                    "adapter_build_action_plan_step_count": 3,
                    "adapter_build_action_plan_world_mutation_authority": "luanti",
                },
                {
                    "case_id": "tnt_wall",
                    "status": "pass",
                    "ok": True,
                    "prompt": "build a wall of tnt",
                    "route": "agentic_build_planner",
                    "build_kind": "wall",
                    "build_material_name": "tnt",
                    "planned_node_writes": 12,
                    "selected_candidate_id": "tnt_wall",
                    "adapter_selected_candidate_id": "tnt_wall",
                    "model_selected_candidate_id": "tnt_wall",
                    "candidate_count": 5,
                    "adapter_tool_decision_source": "agents_sdk_function_tool",
                    "adapter_required_tool_calls": [
                        "recall_build_prompt_memory",
                        "select_build_option",
                        "plan_build_actions",
                    ],
                    "adapter_missing_required_tool_calls": [],
                    "adapter_required_tool_calls_satisfied": True,
                    "adapter_tool_trace_names": [
                        "recall_build_prompt_memory",
                        "select_build_option",
                        "plan_build_actions",
                    ],
                    "adapter_build_action_plan_status": "ready",
                    "adapter_build_action_plan_step_count": 4,
                    "adapter_build_action_plan_world_mutation_authority": "luanti",
                },
                {
                    "case_id": "agentic_build_planner",
                    "status": "pass",
                    "ok": True,
                    "prompt": "build a small lookout wall",
                    "route": "agentic_build_planner",
                    "build_kind": "wall",
                    "build_material_name": "stone",
                    "planned_node_writes": 8,
                    "selected_candidate_id": "generated_stone_wall",
                    "adapter_selected_candidate_id": "generated_stone_wall",
                    "model_selected_candidate_id": "generated_stone_wall",
                    "candidate_count": 3,
                    "adapter_tool_decision_source": "agents_sdk_function_tool",
                    "adapter_required_tool_calls": [
                        "recall_build_prompt_memory",
                        "select_build_option",
                        "plan_build_actions",
                    ],
                    "adapter_missing_required_tool_calls": [],
                    "adapter_required_tool_calls_satisfied": True,
                    "adapter_tool_trace_names": [
                        "recall_build_prompt_memory",
                        "select_build_option",
                        "plan_build_actions",
                    ],
                    "adapter_build_action_plan_status": "ready",
                    "adapter_build_action_plan_step_count": 4,
                    "adapter_build_action_plan_world_mutation_authority": "luanti",
                },
                {
                    "case_id": "model",
                    "status": "pass",
                    "ok": True,
                    "prompt": "what can you plan with tools next?",
                    "route": "model_adapter_async",
                },
            ],
            "metrics": {},
            "safety": {},
        },
        "summary": {
            "cases_total": 5,
            "cases_passed": 5,
            "cases_failed": 0,
            "build_fire_checked": True,
            "fire_only_strict_checked": True,
            "tnt_wall_checked": True,
            "agentic_build_planner_checked": True,
            "model_checked": True,
            "model_adapter_requests": 5,
            "model_adapter_successes": 5,
            "model_adapter_failures": 0,
            "model_adapter_timeouts": 0,
        },
        "safety": {
            "public_safe_output": True,
            "disposable_live_world_only": True,
            "read_only_prompt_eval": True,
            "pending_approvals_discarded": True,
            "world_mutation_performed": False,
            "no_world_mutation": True,
            "no_raw_assets": True,
            "no_provider_prompts": True,
            "no_family_world_coordinates": True,
            "no_private_prompt_retained": True,
        },
        "bounds": {"max_bytes": 22000, "output_bytes": 3000, "truncated": False},
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

    def test_live_prompt_eval_pass_is_recorded(self):
        module = load_quality_gate_module()

        report = module.build_quality_gate(
            candidate_queue=candidate_queue_payload(),
            case_pack=case_pack_payload(),
            review=review_queue_payload(),
            adapter_eval=adapter_eval_payload(),
            live_prompt_eval=live_prompt_eval_payload(),
            generated_at="2026-06-30T18:05:00Z",
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["live_prompt_eval_status"], "pass")
        self.assertEqual(report["summary"]["live_prompt_eval_cases_total"], 5)
        self.assertEqual(report["summary"]["live_prompt_eval_model_adapter_requests"], 5)
        self.assertEqual(report["summary"]["live_prompt_eval_agentic_tool_cases"], 4)
        self.assertEqual(report["summary"]["live_prompt_eval_agentic_tool_cases_required"], 4)

    def test_live_prompt_eval_failure_fails_gate(self):
        module = load_quality_gate_module()

        failed_live_eval = live_prompt_eval_payload(
            summary={
                **live_prompt_eval_payload()["summary"],
                "cases_passed": 4,
                "cases_failed": 1,
                "model_adapter_failures": 1,
            }
        )
        report = module.build_quality_gate(
            candidate_queue=candidate_queue_payload(),
            case_pack=case_pack_payload(),
            review=review_queue_payload(),
            adapter_eval=adapter_eval_payload(),
            live_prompt_eval=failed_live_eval,
            generated_at="2026-06-30T18:05:00Z",
        )

        self.assertEqual(report["status"], "fail")
        self.assertTrue(any(item["kind"] == "live_prompt_eval_not_passing" for item in report["violations"]))

    def test_compat_import_staging_pilot_pass_is_recorded(self):
        module = load_quality_gate_module()

        report = module.build_quality_gate(
            candidate_queue=candidate_queue_payload(),
            case_pack=case_pack_payload(),
            review=review_queue_payload(),
            adapter_eval=adapter_eval_payload(),
            live_prompt_eval=live_prompt_eval_payload(),
            compat_import_pilot=compat_import_staging_pilot_payload(),
            generated_at="2026-06-30T18:05:00Z",
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["compat_import_staging_pilot_status"], "pass")
        self.assertEqual(report["summary"]["compat_import_node_writes"], 18)
        self.assertEqual(report["summary"]["compat_import_mapblock_churn"], 10)
        self.assertEqual(report["summary"]["compat_import_refusal_gates"], 5)
        self.assertEqual(
            report["summary"]["compat_import_mutation_scope"],
            "disposable_synthetic_ai_runtime_staging_world",
        )

    def test_compat_import_staging_pilot_failure_fails_gate(self):
        module = load_quality_gate_module()
        failed_pilot = compat_import_staging_pilot_payload()
        failed_pilot["benchmark_coverage"]["actual_node_writes"] = 17

        report = module.build_quality_gate(
            candidate_queue=candidate_queue_payload(),
            case_pack=case_pack_payload(),
            review=review_queue_payload(),
            adapter_eval=adapter_eval_payload(),
            live_prompt_eval=live_prompt_eval_payload(),
            compat_import_pilot=failed_pilot,
            generated_at="2026-06-30T18:05:00Z",
        )

        self.assertEqual(report["status"], "fail")
        self.assertTrue(any(
            item["kind"] == "compat_import_staging_pilot_not_passing"
            for item in report["violations"]
        ))

    def test_review_queue_attention_is_reported_but_not_deploy_blocking(self):
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

        self.assertEqual(report["status"], "pass")
        self.assertTrue(any(item["kind"] == "manual_review_required" for item in report["attention"]))
        self.assertEqual(report["summary"]["attention_total"], 3)
        self.assertEqual(report["summary"]["blocking_attention_total"], 0)
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
        self.assertEqual(report["summary"]["blocking_attention_total"], 1)

    def test_cli_writes_quality_gate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            candidate_queue = root / "candidate-queue.json"
            case_pack = root / "case-pack.json"
            review_queue = root / "review-queue.json"
            adapter_eval = root / "adapter-contract-eval.json"
            live_eval = root / "live-prompt-eval.json"
            compat_pilot = root / "compat-import-staging-pilot.json"
            output = root / "quality-gate.json"
            candidate_queue.write_text(json.dumps(candidate_queue_payload()), encoding="utf-8")
            case_pack.write_text(json.dumps(case_pack_payload()), encoding="utf-8")
            review_queue.write_text(json.dumps(review_queue_payload()), encoding="utf-8")
            adapter_eval.write_text(json.dumps(adapter_eval_payload()), encoding="utf-8")
            live_eval.write_text(json.dumps(live_prompt_eval_payload()), encoding="utf-8")
            compat_pilot.write_text(json.dumps(compat_import_staging_pilot_payload()), encoding="utf-8")

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
                    "--live-prompt-eval",
                    str(live_eval),
                    "--compat-import-staging-pilot",
                    str(compat_pilot),
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
        self.assertEqual(summary["live_prompt_eval_status"], "pass")
        self.assertEqual(summary["compat_import_staging_pilot_status"], "pass")
        self.assertEqual(report["status"], "pass")


if __name__ == "__main__":
    unittest.main()
