import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
REFRESH = ROOT / "util" / "ai_native_agent_memory_refresh.py"


def load_refresh_module():
    spec = importlib.util.spec_from_file_location("ai_native_agent_memory_refresh_test", REFRESH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_planning_sidecar_entry():
    return {
        "schema_version": 1,
        "event_kind": "ai_native_agents_sdk_request_response",
        "created_at": "2026-06-30T12:00:00Z",
        "adapter_name": "openai-agents-sdk-model-adapter",
        "request": {
            "request_kind": "ai_native_model_adapter_request",
            "adapter_contract": "provider_neutral_v1",
            "agent_id": "nova_agent:Eval:builder",
            "owner": "Eval",
            "task_id": "ai-agent-eval:model",
            "public_prompt": "AI-native Luanti model adapter request.",
            "context": {
                "surface_id": "guide",
                "intent": "build_planning",
                "player_request": "build me a fire and only a fire",
                "candidate_summary": "fire:fire:fire:1|platform:platform:stone:9",
            },
            "safety": {"public_safe_request": True},
            "bounds": {"max_response_bytes": 4000},
        },
        "response": {
            "response_kind": "ai_native_model_adapter_response",
            "adapter_contract": "provider_neutral_v1",
            "ok": True,
            "message": "Selected the fire-only option.",
            "adapter_name": "openai-agents-sdk-model-adapter",
            "response": {
                "agentic_execution": True,
                "tools_enabled": ["recall_build_prompt_memory", "select_build_option", "recommend_build_option"],
                "tool_decision_source": "agents_sdk_function_tool",
                "selected_option_id": "fire",
                "tool_trace": [
                    {"tool_name": "recall_build_prompt_memory"},
                    {"tool_name": "select_build_option"},
                ],
                "tool_decisions": {
                    "build_option": {
                        "selected_option_id": "fire",
                        "decision_source": "agent_selected_build_option",
                        "memory_match": {
                            "memory_available": False,
                            "matched_case_id": None,
                        },
                    },
                },
                "world_mutation_authority": "luanti",
            },
        },
    }


def missing_required_tool_sidecar_entry():
    entry = build_planning_sidecar_entry()
    entry["request"]["context"].update({
        "player_request": "build me a tower",
        "candidate_summary": "platform:platform:default:4|wall:wall:default:12",
    })
    entry["response"]["message"] = "Fell back after missing required tool trace."
    entry["response"]["response"].update({
        "selected_option_id": "generated_tower_wall",
        "tool_decision_source": "adapter_fallback_after_agent_missing_required_tool",
        "required_tool_calls": [
            "recall_build_prompt_memory",
            "select_build_option",
            "propose_build_option",
        ],
        "missing_required_tool_calls": ["propose_build_option"],
        "required_tool_calls_satisfied": False,
        "tool_trace": [
            {"tool_name": "recall_build_prompt_memory"},
            {"tool_name": "select_build_option"},
        ],
        "tool_decisions": {
            "build_option": {
                "selected_option_id": "generated_tower_wall",
                "decision_source": "agent_selected_generated_build_option",
                "generated_option_status": "ready",
                "direct_world_mutation": False,
            },
        },
    })
    return entry


def nova_agent_log_entry():
    return {
        "ts": "2026-06-30T13:05:00Z",
        "player": "Eval",
        "prompt": "build a wall of tnt",
        "model": "gpt-5-nano",
        "source": "agents_sdk",
        "ok": True,
        "label": "tnt wall",
        "message": "Building a tnt wall.",
        "correction_source": "prompt_contract",
        "contract_satisfied": True,
        "prompt_contract": {
            "contract_kind": "tnt_wall",
            "contract_required": True,
        },
        "actions": [
            {
                "type": "fill_box",
                "material": "tnt",
                "size": {"x": 15, "y": 5, "z": 1},
            }
        ],
        "tool_trace": [
            {"tool_name": "analyze_build_intent"},
            {"tool_name": "validate_plan_contract"},
        ],
    }


def operator_labels_payload(prompt="build a bridge"):
    return {
        "schema_version": 1,
        "artifact_kind": "ai_native_agent_eval_operator_labels",
        "labels": [
            {
                "label_id": "reviewed_stone_bridge_platform",
                "prompt": prompt,
                "case_hint": "stone_bridge_platform",
                "expected": {
                    "action": "build",
                    "build_kind": "platform",
                    "build_material_name": "stone",
                    "planned_node_writes": 12,
                    "route": "agentic_build_planner",
                },
            }
        ],
    }


def operator_feedback_line(prompt="build a bridge"):
    payload = {
        "schema_version": 1,
        "event_kind": "ai_agent_operator_feedback",
        "feedback": {
            "feedback_id": "operator_feedback:11",
            "owner": "Eval",
            "agent_id": "nova_agent:Eval:guide",
            "source_trace_id": "nova_trace:11",
            "prompt": prompt,
            "case_hint": "stone_bridge_platform",
            "expected": {
                "action": "build",
                "build_kind": "platform",
                "build_material_name": "stone",
                "planned_node_writes": 12,
                "route": "agentic_build_planner",
            },
            "review": {
                "operator_reviewed": True,
                "review_source": "ai_agent_feedback_chatcommand",
                "no_world_mutation": True,
            },
        },
        "safety": {
            "public_safe_output": True,
            "operator_reviewed": True,
            "no_world_mutation": True,
            "no_raw_assets": True,
            "no_provider_prompts": True,
            "no_family_world_coordinates": True,
        },
    }
    return "[ai_agent_plugin] operator_feedback=" + json.dumps(payload, sort_keys=True)


def nova_request_trace_line(prompt="build a bridge"):
    payload = {
        "schema_version": 1,
        "event_kind": "nova_request_trace",
        "event": "completed",
        "trace": {
            "trace_id": "nova_trace:11",
            "owner": "Eval",
            "agent_id": "nova_agent:Eval:builder",
            "action": "build",
            "route": "agentic_build_planner",
            "public_prompt": prompt,
            "completed_us": 123456,
            "response": {
                "ok": True,
                "status": "pending_approval",
                "action": "build",
                "build_kind": "platform",
                "build_material_name": "stone",
                "planned_node_writes": 12,
                "adapter_tool_trace_names": None,
            },
        },
    }
    return "[ai_agent_plugin] request_trace=" + json.dumps(payload, sort_keys=True)


class AgentMemoryRefreshTests(unittest.TestCase):
    def test_builds_queue_and_case_pack_from_sidecar_player_request(self):
        module = load_refresh_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            sidecar_log = root / "agents-sdk-model-adapter.jsonl"
            sidecar_log.write_text(json.dumps(build_planning_sidecar_entry()) + "\n", encoding="utf-8")

            queue, pack = module.build_memory_artifacts(
                agents_sdk_logs=[sidecar_log],
                generated_at="2026-06-30T13:00:00Z",
                candidate_queue_source_path="local/benchmarks/ai-agent-eval-candidate-queue.json",
            )

        self.assertEqual(queue["status"], "ready")
        self.assertEqual(queue["source_summary"]["ready_for_prompt_eval"], 1)
        self.assertEqual(queue["candidates"][0]["prompt"], "build me a fire and only a fire")
        self.assertEqual(queue["candidates"][0]["prompt_source"], "context.player_request")
        self.assertEqual(pack["status"], "ready")
        self.assertEqual(pack["summary"]["cases_total"], 1)
        self.assertEqual(pack["cases"][0]["prompt"], "build me a fire and only a fire")
        self.assertEqual(pack["cases"][0]["expected"]["build_kind"], "fire")
        self.assertEqual(pack["source"]["candidate_queue_path"], "local/benchmarks/ai-agent-eval-candidate-queue.json")

    def test_builds_queue_and_case_pack_from_nova_agent_log(self):
        module = load_refresh_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            nova_agent_log = root / "nova-agent-requests.jsonl"
            nova_agent_log.write_text(json.dumps(nova_agent_log_entry()) + "\n", encoding="utf-8")

            queue, pack = module.build_memory_artifacts(
                nova_agent_logs=[nova_agent_log],
                generated_at="2026-06-30T13:00:00Z",
                candidate_queue_source_path="local/benchmarks/ai-agent-eval-candidate-queue.json",
            )

        self.assertEqual(queue["status"], "ready")
        self.assertEqual(queue["source_summary"]["nova_agent_log_entries_read"], 1)
        self.assertEqual(queue["source_summary"]["ready_for_prompt_eval"], 1)
        self.assertEqual(queue["candidates"][0]["source_kind"], "nova_agent_sidecar_request_response")
        self.assertEqual(queue["candidates"][0]["observed"]["contract_kind"], "tnt_wall")
        self.assertEqual(pack["status"], "ready")
        self.assertEqual(pack["summary"]["cases_total"], 1)
        self.assertEqual(pack["cases"][0]["case_hint"], "tnt_wall")
        self.assertEqual(pack["cases"][0]["expected"]["build_kind"], "wall")
        self.assertEqual(pack["cases"][0]["expected"]["build_material_name"], "tnt")

    def test_refresh_summarizes_adapter_contract_failures_without_prompt_promotion(self):
        module = load_refresh_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            sidecar_log = root / "agents-sdk-model-adapter.jsonl"
            sidecar_log.write_text(json.dumps(missing_required_tool_sidecar_entry()) + "\n", encoding="utf-8")

            queue, pack = module.build_memory_artifacts(
                agents_sdk_logs=[sidecar_log],
                generated_at="2026-06-30T13:00:00Z",
                candidate_queue_source_path="local/benchmarks/ai-agent-eval-candidate-queue.json",
            )

        self.assertEqual(queue["status"], "ready")
        self.assertEqual(queue["source_summary"]["ready_for_adapter_contract_eval"], 1)
        self.assertEqual(queue["source_summary"]["adapter_contract_failures"], 1)
        self.assertTrue(queue["candidates"][0]["ready_for_adapter_contract_eval"])
        self.assertEqual(pack["status"], "empty")
        self.assertEqual(pack["summary"]["cases_total"], 0)

    def test_refresh_applies_operator_labels_to_unknown_prompts(self):
        module = load_refresh_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            sidecar_log = root / "agents-sdk-model-adapter.jsonl"
            operator_labels = root / "operator-labels.json"
            entry = build_planning_sidecar_entry()
            entry["request"]["context"]["player_request"] = "build a bridge"
            sidecar_log.write_text(json.dumps(entry) + "\n", encoding="utf-8")
            operator_labels.write_text(json.dumps(operator_labels_payload()), encoding="utf-8")

            queue, pack = module.build_memory_artifacts(
                agents_sdk_logs=[sidecar_log],
                operator_label_files=[operator_labels],
                generated_at="2026-06-30T13:00:00Z",
                candidate_queue_source_path="local/benchmarks/ai-agent-eval-candidate-queue.json",
            )

        self.assertEqual(queue["status"], "ready")
        self.assertEqual(queue["source_summary"]["operator_labels_read"], 1)
        self.assertEqual(queue["source_summary"]["operator_labels_applied"], 1)
        self.assertEqual(queue["source_summary"]["ready_for_prompt_eval"], 1)
        self.assertEqual(queue["candidates"][0]["review_status"], "operator_labeled_candidate_ready")
        self.assertEqual(pack["status"], "ready")
        self.assertEqual(pack["summary"]["cases_total"], 1)
        self.assertEqual(pack["cases"][0]["case_hint"], "stone_bridge_platform")
        self.assertEqual(pack["cases"][0]["promotion"]["mode"], "operator_label_overlay")

    def test_refresh_harvests_operator_feedback_from_action_log(self):
        module = load_refresh_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            sidecar_log = root / "agents-sdk-model-adapter.jsonl"
            action_log = root / "debug.log"
            entry = build_planning_sidecar_entry()
            entry["request"]["context"]["player_request"] = "build a bridge"
            sidecar_log.write_text(json.dumps(entry) + "\n", encoding="utf-8")
            action_log.write_text(operator_feedback_line("build a bridge") + "\n", encoding="utf-8")

            queue, pack = module.build_memory_artifacts(
                agents_sdk_logs=[sidecar_log],
                action_logs=[action_log],
                from_operator_feedback=True,
                generated_at="2026-06-30T13:30:00Z",
                candidate_queue_source_path="local/benchmarks/ai-agent-eval-candidate-queue.json",
            )

        self.assertEqual(queue["status"], "ready")
        self.assertEqual(queue["source_summary"]["operator_feedback_events_read"], 1)
        self.assertEqual(queue["source_summary"]["operator_feedback_labels_generated"], 1)
        self.assertEqual(queue["source_summary"]["operator_labels_read"], 1)
        self.assertEqual(queue["source_summary"]["operator_labels_applied"], 1)
        self.assertEqual(queue["candidates"][0]["review_status"], "operator_labeled_candidate_ready")
        self.assertEqual(queue["candidates"][0]["expected"]["build_kind"], "platform")
        self.assertEqual(pack["status"], "ready")
        self.assertEqual(pack["summary"]["cases_total"], 1)
        self.assertEqual(pack["cases"][0]["case_hint"], "stone_bridge_platform")

    def test_refresh_tolerates_live_action_log_null_tool_traces(self):
        module = load_refresh_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            action_log = root / "debug.log"
            action_log.write_text(
                nova_request_trace_line("build a bridge")
                + "\n"
                + operator_feedback_line("build a bridge")
                + "\n",
                encoding="utf-8",
            )

            queue, pack = module.build_memory_artifacts(
                action_logs=[action_log],
                from_operator_feedback=True,
                generated_at="2026-06-30T13:45:00Z",
                candidate_queue_source_path="local/benchmarks/ai-agent-eval-candidate-queue.json",
            )

        self.assertEqual(queue["status"], "ready")
        self.assertEqual(queue["source_summary"]["nova_request_traces_read"], 1)
        self.assertEqual(queue["source_summary"]["operator_feedback_events_read"], 1)
        self.assertEqual(queue["source_summary"]["operator_feedback_labels_generated"], 1)
        self.assertEqual(queue["source_summary"]["operator_labels_applied"], 1)
        self.assertEqual(queue["candidates"][0]["observed"]["adapter_tool_trace_names"], [])
        self.assertEqual(pack["status"], "ready")
        self.assertEqual(pack["summary"]["cases_total"], 1)
        self.assertEqual(pack["cases"][0]["case_hint"], "stone_bridge_platform")

    def test_cli_writes_refresh_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            sidecar_log = root / "agents-sdk-model-adapter.jsonl"
            nova_agent_log = root / "nova-agent-requests.jsonl"
            operator_labels = root / "operator-labels.json"
            candidate_queue = root / "ai-agent-eval-candidate-queue.json"
            case_pack = root / "ai-agent-prompt-eval-case-pack.json"
            sidecar_log.write_text(json.dumps(build_planning_sidecar_entry()) + "\n", encoding="utf-8")
            nova_agent_log.write_text(json.dumps(nova_agent_log_entry()) + "\n", encoding="utf-8")
            operator_labels.write_text(json.dumps(operator_labels_payload()), encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(REFRESH),
                    "--root",
                    str(root),
                    "--agents-sdk-log",
                    str(sidecar_log),
                    "--nova-agent-log",
                    str(nova_agent_log),
                    "--operator-labels",
                    str(operator_labels),
                    "--candidate-queue-output",
                    str(candidate_queue),
                    "--case-pack-output",
                    str(case_pack),
                    "--generated-at",
                    "2026-06-30T13:00:00Z",
                ],
                cwd=ROOT,
                check=False,
                text=True,
                capture_output=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            summary = json.loads(completed.stdout)
            self.assertEqual(summary["case_pack_status"], "ready")
            self.assertEqual(summary["cases_total"], 2)
            self.assertEqual(summary["adapter_contract_failures"], 0)
            self.assertEqual(summary["ready_for_adapter_contract_eval"], 0)
            self.assertEqual(summary["operator_labels_read"], 1)
            self.assertEqual(summary["operator_labels_applied"], 0)
            self.assertEqual(json.loads(candidate_queue.read_text(encoding="utf-8"))["status"], "ready")
            self.assertEqual(json.loads(case_pack.read_text(encoding="utf-8"))["summary"]["cases_total"], 2)

    def test_cli_harvests_operator_feedback_from_action_log(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            sidecar_log = root / "agents-sdk-model-adapter.jsonl"
            action_log = root / "debug.log"
            candidate_queue = root / "ai-agent-eval-candidate-queue.json"
            case_pack = root / "ai-agent-prompt-eval-case-pack.json"
            entry = build_planning_sidecar_entry()
            entry["request"]["context"]["player_request"] = "build a bridge"
            sidecar_log.write_text(json.dumps(entry) + "\n", encoding="utf-8")
            action_log.write_text(operator_feedback_line("build a bridge") + "\n", encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(REFRESH),
                    "--root",
                    str(root),
                    "--agents-sdk-log",
                    str(sidecar_log),
                    "--action-log",
                    str(action_log),
                    "--from-operator-feedback",
                    "--candidate-queue-output",
                    str(candidate_queue),
                    "--case-pack-output",
                    str(case_pack),
                    "--generated-at",
                    "2026-06-30T13:30:00Z",
                ],
                cwd=ROOT,
                check=False,
                text=True,
                capture_output=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            summary = json.loads(completed.stdout)
            queue = json.loads(candidate_queue.read_text(encoding="utf-8"))
            pack = json.loads(case_pack.read_text(encoding="utf-8"))

            self.assertEqual(summary["case_pack_status"], "ready")
            self.assertEqual(summary["operator_feedback_events_read"], 1)
            self.assertEqual(summary["operator_feedback_labels_generated"], 1)
            self.assertEqual(summary["operator_labels_applied"], 1)
            self.assertEqual(queue["candidates"][0]["review_status"], "operator_labeled_candidate_ready")
            self.assertEqual(pack["summary"]["cases_total"], 1)


if __name__ == "__main__":
    unittest.main()
