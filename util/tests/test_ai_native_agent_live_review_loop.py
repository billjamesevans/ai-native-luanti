import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "util" / "ai_native_agent_live_review_loop.py"


def load_module():
    spec = importlib.util.spec_from_file_location("ai_native_agent_live_review_loop_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def status_payload():
    return {
        "schema_version": 1,
        "generated_at": "2026-07-02T12:00:00Z",
        "adapter_log": {
            "present": True,
            "current_health": "pass",
            "recent_traces": [
                {
                    "created_at": "2026-07-02T12:00:00Z",
                    "agent_id": "nova_agent:PromptEvalLive",
                    "task_id": "ai-agent-build-planner:nova_trace:11",
                    "source_trace_id": "nova_trace:11",
                    "ok": True,
                    "agentic_execution": True,
                    "selected_option_id": "fire",
                    "planned_node_writes": 1,
                    "required_tool_calls_satisfied": True,
                    "tool_decision_source": "agents_sdk_repair_function_tool",
                    "web_search_available": True,
                    "world_mutation_authority": "luanti",
                    "direct_world_mutation": False,
                },
            ],
        },
        "public_safe": True,
    }


def agents_sdk_log_entry(prompt="build only a fire"):
    return {
        "schema_version": 1,
        "event_kind": "ai_native_agents_sdk_request_response",
        "created_at": "2026-07-02T12:00:00Z",
        "adapter_name": "openai-agents-sdk-model-adapter",
        "request": {
            "request_kind": "ai_native_model_adapter_request",
            "adapter_contract": "provider_neutral_v1",
            "agent_id": "nova_agent:PromptEvalLive",
            "owner": "PromptEvalLive",
            "task_id": "ai-agent-build-planner:nova_trace:11",
            "public_prompt": "Plan a Luanti build request.\nPlayer request: build only a fire",
            "context": {
                "surface_id": "builder",
                "intent": "build_planning",
                "player_request": prompt,
                "candidate_summary": "fire:fire:fire:1|platform:platform:stone:4",
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
                    "inspect_build_site_context",
                    "recall_build_prompt_memory",
                    "select_build_option",
                    "plan_build_actions",
                ],
                "tool_decision_source": "agents_sdk_function_tool",
                "selected_option_id": "fire",
                "required_tool_calls_satisfied": True,
                "missing_required_tool_calls": [],
                "world_mutation_authority": "luanti",
                "tool_trace": [
                    {"tool_name": "inspect_build_site_context"},
                    {"tool_name": "recall_build_prompt_memory"},
                    {"tool_name": "select_build_option"},
                    {"tool_name": "plan_build_actions"},
                ],
                "tool_decisions": {
                    "build_option": {
                        "selected_option_id": "fire",
                        "selected_planned_node_writes": 1,
                        "decision_source": "agent_selected_build_option",
                    },
                    "build_action_plan": {
                        "status": "ready",
                        "selected_option_id": "fire",
                        "step_count": 4,
                        "world_mutation_authority": "luanti",
                        "build_kind": "fire",
                        "build_material_name": "fire",
                        "planned_node_writes": 1,
                    },
                },
            },
        },
    }


class LiveReviewLoopTests(unittest.TestCase):
    def test_cli_builds_review_loop_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            status_file = root / "status.json"
            agents_log = root / "agents-sdk-model-adapter.jsonl"
            output_dir = root / "artifacts"
            status_file.write_text(json.dumps(status_payload()) + "\n", encoding="utf-8")
            agents_log.write_text(json.dumps(agents_sdk_log_entry()) + "\n", encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--root",
                    str(root),
                    "--status-json",
                    str(status_file),
                    "--agents-sdk-log",
                    str(agents_log),
                    "--trace-id",
                    "nova_trace:11",
                    "--output-dir",
                    str(output_dir),
                    "--artifact-prefix",
                    "trace11",
                    "--generated-at",
                    "2026-07-02T12:30:00Z",
                ],
                cwd=ROOT,
                check=False,
                text=True,
                capture_output=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            summary = json.loads(completed.stdout)
            review_packet = json.loads((output_dir / "trace11-studio-review-packet.json").read_text())
            candidate_queue = json.loads((output_dir / "trace11-candidate-queue.json").read_text())
            operator_labels = json.loads((output_dir / "trace11-operator-labels.json").read_text())
            case_pack = json.loads((output_dir / "trace11-case-pack.json").read_text())

            self.assertEqual(summary["status"], "ready")
            self.assertEqual(summary["source_trace_id"], "nova_trace:11")
            self.assertEqual(summary["selected_option_id"], "fire")
            self.assertEqual(summary["case_hint"], "fire_only_strict")
            self.assertEqual(review_packet["artifact_kind"], "openrealm_studio_agent_review_packet")
            self.assertEqual(candidate_queue["status"], "ready")
            self.assertEqual(operator_labels["labels"][0]["case_hint"], "fire_only_strict")
            self.assertEqual(case_pack["summary"]["cases_total"], 1)

    def test_cli_rejects_private_status_without_outputs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            status = status_payload()
            status["adapter_log"]["recent_traces"][0]["credentials"] = {"kind": "redacted"}
            status_file = root / "status.json"
            agents_log = root / "agents-sdk-model-adapter.jsonl"
            output_dir = root / "artifacts"
            status_file.write_text(json.dumps(status) + "\n", encoding="utf-8")
            agents_log.write_text(json.dumps(agents_sdk_log_entry()) + "\n", encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--root",
                    str(root),
                    "--status-json",
                    str(status_file),
                    "--agents-sdk-log",
                    str(agents_log),
                    "--output-dir",
                    str(output_dir),
                    "--artifact-prefix",
                    "trace11",
                ],
                cwd=ROOT,
                check=False,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertIn("status payload is not public-safe", completed.stderr)
            self.assertFalse(output_dir.exists())


if __name__ == "__main__":
    unittest.main()
