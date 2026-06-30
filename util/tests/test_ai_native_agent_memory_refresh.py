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
                "tools_enabled": ["recall_build_prompt_memory", "recommend_build_option"],
                "tool_decision_source": "agents_sdk_function_tool",
                "selected_option_id": "fire",
                "tool_trace": [
                    {"tool_name": "recall_build_prompt_memory"},
                    {"tool_name": "recommend_build_option"},
                ],
                "tool_decisions": {
                    "build_option": {
                        "selected_option_id": "fire",
                        "decision_source": "agent_build_option_tool",
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

    def test_cli_writes_refresh_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            sidecar_log = root / "agents-sdk-model-adapter.jsonl"
            candidate_queue = root / "ai-agent-eval-candidate-queue.json"
            case_pack = root / "ai-agent-prompt-eval-case-pack.json"
            sidecar_log.write_text(json.dumps(build_planning_sidecar_entry()) + "\n", encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(REFRESH),
                    "--root",
                    str(root),
                    "--agents-sdk-log",
                    str(sidecar_log),
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
            self.assertEqual(summary["cases_total"], 1)
            self.assertEqual(json.loads(candidate_queue.read_text(encoding="utf-8"))["status"], "ready")
            self.assertEqual(json.loads(case_pack.read_text(encoding="utf-8"))["summary"]["cases_total"], 1)


if __name__ == "__main__":
    unittest.main()
