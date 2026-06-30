import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
QUEUE = ROOT / "util" / "ai_native_agent_eval_queue.py"
REFRESH = ROOT / "util" / "ai_native_agent_memory_refresh.py"
OPERATOR_LABEL = ROOT / "util" / "ai_native_agent_operator_label.py"


def load_module(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
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
                "surface_id": "guide",
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
                    "recommend_build_option",
                ],
                "tool_decision_source": "agents_sdk_function_tool",
                "selected_option_id": "generated_bridge_platform",
                "tool_trace": [
                    {"tool_name": "recall_build_prompt_memory"},
                    {"tool_name": "select_build_option"},
                ],
                "tool_decisions": {
                    "build_option": {
                        "selected_option_id": "generated_bridge_platform",
                        "decision_source": "agent_selected_generated_build_option",
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


class AgentOperatorLabelTests(unittest.TestCase):
    def setUp(self):
        self.queue = load_module(QUEUE, "ai_native_agent_eval_queue_operator_test")
        self.refresh = load_module(REFRESH, "ai_native_agent_memory_refresh_operator_test")
        self.operator = load_module(OPERATOR_LABEL, "ai_native_agent_operator_label_test")

    def test_builds_label_artifact_and_promotes_candidate_by_prompt(self):
        candidate_queue = self.queue.build_eval_candidate_queue(
            agents_sdk_logs=[],
            operator_label_payloads=[],
            generated_at="2026-06-30T12:00:00Z",
        )
        candidate = self.queue.candidate_from_agents_sdk_entry(sidecar_entry("build a bridge"))
        candidate_queue["candidates"] = [candidate]
        candidate_queue["status"] = "ready"

        expected = self.operator.expected_build_behavior(
            build_kind="platform",
            build_material_name="stone",
            planned_node_writes=12,
            route="agentic_build_planner",
        )
        artifact = self.operator.build_operator_label_artifact(
            candidate_queue=candidate_queue,
            candidate_queue_path="local/ai-agent-eval-candidate-queue.json",
            prompt="build a bridge",
            source_kind="agents_sdk_request_response",
            case_hint="stone_bridge_platform",
            expected=expected,
            generated_at="2026-06-30T12:05:00Z",
        )

        labelled = self.queue.build_eval_candidate_queue(
            operator_label_payloads=[artifact],
            generated_at="2026-06-30T12:10:00Z",
        )
        labelled["candidates"] = [candidate]
        self.queue.apply_operator_labels(labelled["candidates"], [artifact], labelled["violations"])

        self.assertEqual(artifact["artifact_kind"], "ai_native_agent_eval_operator_labels")
        self.assertEqual(artifact["source"]["matched"], True)
        self.assertEqual(artifact["labels"][0]["case_hint"], "stone_bridge_platform")
        self.assertEqual(labelled["candidates"][0]["review_status"], "operator_labeled_candidate_ready")
        self.assertEqual(labelled["candidates"][0]["expected"]["build_kind"], "platform")
        self.assertEqual(labelled["candidates"][0]["expected"]["planned_node_writes"], 12)

    def test_operator_label_file_feeds_memory_refresh_case_pack(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            sidecar_log = root / "agents-sdk-model-adapter.jsonl"
            candidate_queue_path = root / "candidate-queue.json"
            operator_labels_path = root / "operator-labels.json"
            sidecar_log.write_text(json.dumps(sidecar_entry("build a bridge")) + "\n", encoding="utf-8")

            candidate_queue = self.queue.build_eval_candidate_queue(
                agents_sdk_logs=[sidecar_log],
                generated_at="2026-06-30T12:00:00Z",
            )
            candidate_queue_path.write_text(json.dumps(candidate_queue), encoding="utf-8")
            expected = self.operator.expected_build_behavior(
                build_kind="platform",
                build_material_name="stone",
                planned_node_writes=12,
                route="agentic_build_planner",
            )
            artifact = self.operator.build_operator_label_artifact(
                candidate_queue=candidate_queue,
                candidate_queue_path="candidate-queue.json",
                prompt="build a bridge",
                case_hint="stone_bridge_platform",
                expected=expected,
                generated_at="2026-06-30T12:05:00Z",
            )
            operator_labels_path.write_text(json.dumps(artifact), encoding="utf-8")

            queue, pack = self.refresh.build_memory_artifacts(
                agents_sdk_logs=[sidecar_log],
                operator_label_files=[operator_labels_path],
                generated_at="2026-06-30T12:10:00Z",
                candidate_queue_source_path="candidate-queue.json",
            )

        self.assertEqual(queue["source_summary"]["operator_labels_applied"], 1)
        self.assertEqual(queue["candidates"][0]["review_status"], "operator_labeled_candidate_ready")
        self.assertEqual(pack["status"], "ready")
        self.assertEqual(pack["summary"]["cases_total"], 1)
        self.assertEqual(pack["cases"][0]["promotion"]["mode"], "operator_label_overlay")

    def test_rejects_missing_candidate_without_override(self):
        candidate_queue = self.queue.build_eval_candidate_queue(generated_at="2026-06-30T12:00:00Z")
        expected = self.operator.expected_build_behavior(
            build_kind="wall",
            build_material_name="tnt",
            planned_node_writes=12,
        )

        with self.assertRaises(self.operator.OperatorLabelError):
            self.operator.build_operator_label_artifact(
                candidate_queue=candidate_queue,
                candidate_queue_path="candidate-queue.json",
                prompt="build a wall of tnt",
                case_hint="tnt_wall",
                expected=expected,
            )

    def test_rejects_private_queue_and_invalid_expected_behavior(self):
        private_queue = {
            "artifact_kind": "ai_native_agent_eval_candidate_queue",
            "candidates": [{"candidate_id": "c1", "prompt": "/Users/private/build a bridge"}],
        }

        with self.assertRaises(self.operator.OperatorLabelError):
            self.operator.build_operator_label_artifact(
                candidate_queue=private_queue,
                candidate_queue_path="candidate-queue.json",
                candidate_id="c1",
                expected={
                    "action": "build",
                    "build_kind": "platform",
                    "build_material_name": "stone",
                },
            )

        with self.assertRaises(self.operator.OperatorLabelError):
            self.operator.expected_build_behavior(
                build_kind="platform",
                build_material_name="stone",
                planned_node_writes=10001,
            )

    def test_cli_writes_operator_label_artifact(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            sidecar_log = root / "agents-sdk-model-adapter.jsonl"
            candidate_queue = root / "candidate-queue.json"
            output = root / "operator-labels.json"
            sidecar_log.write_text(json.dumps(sidecar_entry("build a bridge")) + "\n", encoding="utf-8")
            queue_payload = self.queue.build_eval_candidate_queue(
                agents_sdk_logs=[sidecar_log],
                generated_at="2026-06-30T12:00:00Z",
            )
            candidate_queue.write_text(json.dumps(queue_payload), encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(OPERATOR_LABEL),
                    "--root",
                    str(root),
                    "--candidate-queue",
                    str(candidate_queue),
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
                    "--output",
                    str(output),
                    "--generated-at",
                    "2026-06-30T12:05:00Z",
                ],
                cwd=ROOT,
                check=False,
                text=True,
                capture_output=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            summary = json.loads(completed.stdout)
            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["matched"])
        self.assertEqual(payload["labels"][0]["expected"]["build_material_name"], "stone")
        self.assertEqual(payload["labels"][0]["expected"]["planned_node_writes"], 12)


if __name__ == "__main__":
    unittest.main()
