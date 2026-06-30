import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
FEEDBACK = ROOT / "util" / "ai_native_agent_feedback_packet.py"


def load_feedback_module():
    spec = importlib.util.spec_from_file_location("ai_native_agent_feedback_packet_test", FEEDBACK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sidecar_entry(prompt="build a bridge"):
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
                "surface_id": "builder",
                "intent": "build_planning",
                "player_request": prompt,
                "candidate_summary": "platform:platform:stone:12|fire:fire:fire:1",
            },
            "safety": {"public_safe_request": True},
            "bounds": {"max_response_bytes": 4000},
        },
        "response": {
            "response_kind": "ai_native_model_adapter_response",
            "adapter_contract": "provider_neutral_v1",
            "ok": True,
            "message": "Generated a build plan.",
            "adapter_name": "openai-agents-sdk-model-adapter",
            "response": {
                "agentic_execution": True,
                "tools_enabled": [
                    "recall_build_prompt_memory",
                    "select_build_option",
                    "propose_build_option",
                ],
                "tool_decision_source": "agents_sdk_function_tool",
                "selected_option_id": "generated_bridge_platform",
                "tool_trace": [
                    {"tool_name": "recall_build_prompt_memory"},
                    {"tool_name": "propose_build_option"},
                    {"tool_name": "select_build_option"},
                ],
                "tool_decisions": {
                    "build_option": {
                        "selected_option_id": "generated_bridge_platform",
                        "decision_source": "agent_selected_generated_build_option",
                    },
                },
                "world_mutation_authority": "luanti",
            },
        },
    }


class AgentFeedbackPacketTests(unittest.TestCase):
    def test_builds_feedback_packet_from_log_and_reviewed_expectation(self):
        module = load_feedback_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            sidecar_log = root / "agents-sdk-model-adapter.jsonl"
            candidate_queue_output = root / "candidate-queue.json"
            operator_label_output = root / "operator-labels.json"
            case_pack_output = root / "case-pack.json"
            sidecar_log.write_text(json.dumps(sidecar_entry("build a bridge")) + "\n", encoding="utf-8")
            expected = module.operator_label.expected_build_behavior(
                build_kind="platform",
                build_material_name="stone",
                planned_node_writes=12,
                route="agentic_build_planner",
            )

            candidate_queue, label_artifact, case_pack, summary = module.build_feedback_packet(
                root=root,
                agents_sdk_logs=[sidecar_log],
                nova_agent_logs=[],
                action_logs=[],
                candidate_queue_output=candidate_queue_output,
                operator_label_output=operator_label_output,
                case_pack_output=case_pack_output,
                candidate_id=None,
                prompt="build a bridge",
                source_kind=None,
                case_hint="stone_bridge_platform",
                label_id=None,
                expected=expected,
                allow_unmatched=False,
                generated_at="2026-06-30T14:00:00Z",
                max_candidates=20,
                max_candidate_queue_bytes=32000,
                max_cases=10,
                max_case_pack_bytes=24000,
            )

            self.assertEqual(summary["status"], "ready")
            self.assertEqual(summary["operator_labels_applied"], 1)
            self.assertEqual(summary["cases_total"], 1)
            self.assertEqual(candidate_queue["candidates"][0]["review_status"], "operator_labeled_candidate_ready")
            self.assertEqual(label_artifact["labels"][0]["expected"]["build_kind"], "platform")
            self.assertEqual(case_pack["cases"][0]["case_hint"], "stone_bridge_platform")
            self.assertTrue(candidate_queue_output.is_file())
            self.assertTrue(operator_label_output.is_file())
            self.assertTrue(case_pack_output.is_file())

    def test_missing_candidate_fails_without_writing_outputs(self):
        module = load_feedback_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            sidecar_log = root / "agents-sdk-model-adapter.jsonl"
            candidate_queue_output = root / "candidate-queue.json"
            operator_label_output = root / "operator-labels.json"
            case_pack_output = root / "case-pack.json"
            sidecar_log.write_text(json.dumps(sidecar_entry("build a bridge")) + "\n", encoding="utf-8")
            expected = module.operator_label.expected_build_behavior(
                build_kind="wall",
                build_material_name="tnt",
                planned_node_writes=12,
            )

            with self.assertRaises(module.operator_label.OperatorLabelError):
                module.build_feedback_packet(
                    root=root,
                    agents_sdk_logs=[sidecar_log],
                    nova_agent_logs=[],
                    action_logs=[],
                    candidate_queue_output=candidate_queue_output,
                    operator_label_output=operator_label_output,
                    case_pack_output=case_pack_output,
                    candidate_id=None,
                    prompt="build a wall of tnt",
                    source_kind=None,
                    case_hint="tnt_wall",
                    label_id=None,
                    expected=expected,
                    allow_unmatched=False,
                    generated_at="2026-06-30T14:00:00Z",
                    max_candidates=20,
                    max_candidate_queue_bytes=32000,
                    max_cases=10,
                    max_case_pack_bytes=24000,
                )

            self.assertFalse(candidate_queue_output.exists())
            self.assertFalse(operator_label_output.exists())
            self.assertFalse(case_pack_output.exists())

    def test_cli_writes_feedback_packet(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            sidecar_log = root / "agents-sdk-model-adapter.jsonl"
            candidate_queue_output = root / "candidate-queue.json"
            operator_label_output = root / "operator-labels.json"
            case_pack_output = root / "case-pack.json"
            sidecar_log.write_text(json.dumps(sidecar_entry("build a bridge")) + "\n", encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(FEEDBACK),
                    "--root",
                    str(root),
                    "--agents-sdk-log",
                    str(sidecar_log),
                    "--prompt",
                    "build a bridge",
                    "--case-hint",
                    "stone_bridge_platform",
                    "--build-kind",
                    "platform",
                    "--build-material-name",
                    "stone",
                    "--planned-node-writes",
                    "12",
                    "--route",
                    "agentic_build_planner",
                    "--candidate-queue-output",
                    str(candidate_queue_output),
                    "--operator-label-output",
                    str(operator_label_output),
                    "--case-pack-output",
                    str(case_pack_output),
                    "--generated-at",
                    "2026-06-30T14:00:00Z",
                ],
                cwd=ROOT,
                check=False,
                text=True,
                capture_output=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            summary = json.loads(completed.stdout)
            queue = json.loads(candidate_queue_output.read_text(encoding="utf-8"))
            labels = json.loads(operator_label_output.read_text(encoding="utf-8"))
            pack = json.loads(case_pack_output.read_text(encoding="utf-8"))

        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["operator_label_matched"])
        self.assertEqual(queue["source_summary"]["operator_labels_applied"], 1)
        self.assertEqual(labels["artifact_kind"], "ai_native_agent_eval_operator_labels")
        self.assertEqual(pack["summary"]["cases_total"], 1)


if __name__ == "__main__":
    unittest.main()
