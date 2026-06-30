import importlib.util
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pathlib
import re
import subprocess
import sys
import tempfile
import threading
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
QUEUE = ROOT / "util" / "ai_native_agent_eval_queue.py"
CONTRACT_EVAL = ROOT / "util" / "ai_native_agent_adapter_contract_eval.py"
README = ROOT / "doc" / "ai-native-runtime" / "README.md"
OPERATING_LOOP = ROOT / "doc" / "ai-native-runtime" / "project-operating-loop.md"
ADAPTER_DOC = ROOT / "doc" / "ai-native-runtime" / "agents-sdk-model-adapter.md"

PRIVATE_PATTERNS = re.compile(
    r"minecraftpi|192\.168|spacebase|themepark|showcase100|disneyland100|"
    r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY|private_prompt|asset_payload|/Users/",
    re.I,
)


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def missing_required_tool_entry():
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
            "task_id": "adapter-contract-eval",
            "public_prompt": "Player request: build me a tower",
            "context": {
                "surface_id": "builder",
                "intent": "build_planning",
                "player_request": "build me a tower",
                "candidate_summary": "platform:platform:default:4|wall:wall:default:12",
            },
            "safety": {"public_safe_request": True},
            "bounds": {"max_response_bytes": 4000},
        },
        "response": {
            "response_kind": "ai_native_model_adapter_response",
            "adapter_contract": "provider_neutral_v1",
            "ok": True,
            "adapter_name": "openai-agents-sdk-model-adapter",
            "response": {
                "agentic_execution": True,
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
                        "decision_source": "offline_adapter_fallback",
                        "generated_option_status": "ready",
                        "direct_world_mutation": False,
                    },
                },
                "world_mutation_authority": "luanti",
            },
        },
    }


def candidate_queue_payload():
    queue = load_module(QUEUE, "adapter_contract_eval_queue_fixture")
    with tempfile.TemporaryDirectory() as tmpdir:
        path = pathlib.Path(tmpdir) / "agents-sdk.jsonl"
        path.write_text(json.dumps(missing_required_tool_entry()) + "\n", encoding="utf-8")
        return queue.build_eval_candidate_queue(
            agents_sdk_logs=[path],
            generated_at="2026-06-30T14:00:00Z",
        )


def fixed_good_response(request):
    return {
        "schema_version": 1,
        "response_kind": "ai_native_model_adapter_response",
        "adapter_contract": "provider_neutral_v1",
        "ok": True,
        "adapter_name": "openai-agents-sdk-model-adapter",
        "response": {
            "agentic_execution": True,
            "selected_option_id": "generated_tower_wall",
            "tool_decision_source": "agents_sdk_function_tool",
            "required_tool_calls": [
                "recall_build_prompt_memory",
                "select_build_option",
                "propose_build_option",
            ],
            "missing_required_tool_calls": [],
            "required_tool_calls_satisfied": True,
            "tool_trace": [
                {"tool_name": "recall_build_prompt_memory"},
                {"tool_name": "propose_build_option"},
                {"tool_name": "select_build_option"},
            ],
            "tool_decisions": {
                "build_option": {
                    "selected_option_id": "generated_tower_wall",
                    "decision_source": "agent_selected_generated_build_option",
                },
            },
            "world_mutation_authority": "luanti",
        },
    }


def fixed_bad_response(request):
    response = fixed_good_response(request)
    response["response"]["tool_decision_source"] = "adapter_fallback_after_agent_missing_required_tool"
    response["response"]["missing_required_tool_calls"] = ["propose_build_option"]
    response["response"]["required_tool_calls_satisfied"] = False
    return response


def fixed_local_fast_path_response(request):
    response = fixed_good_response(request)
    response["response"]["tool_decision_source"] = "local_agent_tool_contract_fast_path"
    response["response"]["local_tool_contract_reason"] = "agents_sdk_model_timeout"
    response["response"]["agent_model_timeout"] = True
    return response


class AgentAdapterContractEvalTests(unittest.TestCase):
    def test_replays_ready_adapter_contract_candidate_successfully(self):
        module = load_module(CONTRACT_EVAL, "ai_native_agent_adapter_contract_eval_success")

        report = module.build_adapter_contract_eval(
            candidate_queue_payload(),
            generated_at="2026-06-30T14:10:00Z",
            request_runner=fixed_good_response,
        )

        self.assertEqual(report["artifact_kind"], "ai_native_agent_adapter_contract_eval_result")
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["selected_candidates_total"], 1)
        self.assertEqual(report["summary"]["passed"], 1)
        case = report["cases"][0]
        self.assertTrue(case["ok"])
        self.assertEqual(case["response"]["selected_option_id"], "generated_tower_wall")
        self.assertEqual(case["response"]["missing_required_tool_calls"], [])
        self.assertTrue(case["checks"]["required_tool_calls_present"])
        self.assertFalse(PRIVATE_PATTERNS.search(json.dumps(report, sort_keys=True)))

    def test_replay_accepts_local_tool_contract_fast_path(self):
        module = load_module(CONTRACT_EVAL, "ai_native_agent_adapter_contract_eval_local_fast_path")

        report = module.build_adapter_contract_eval(
            candidate_queue_payload(),
            generated_at="2026-06-30T14:10:00Z",
            request_runner=fixed_local_fast_path_response,
        )

        self.assertEqual(report["status"], "pass")
        case = report["cases"][0]
        self.assertTrue(case["ok"])
        self.assertEqual(
            case["response"]["tool_decision_source"],
            "local_agent_tool_contract_fast_path",
        )
        self.assertIn(
            "local_agent_tool_contract_fast_path",
            case["expected"]["tool_decision_sources"],
        )

    def test_replay_failure_reports_missing_required_tool(self):
        module = load_module(CONTRACT_EVAL, "ai_native_agent_adapter_contract_eval_failure")

        report = module.build_adapter_contract_eval(
            candidate_queue_payload(),
            generated_at="2026-06-30T14:10:00Z",
            request_runner=fixed_bad_response,
        )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["summary"]["failed"], 1)
        case = report["cases"][0]
        self.assertIn("missing_required_tool_calls_empty", case["failures"])
        self.assertIn("required_tool_calls_satisfied", case["failures"])
        self.assertIn("tool_decision_source", case["failures"])

    def test_non_loopback_endpoint_is_rejected_before_replay(self):
        module = load_module(CONTRACT_EVAL, "ai_native_agent_adapter_contract_eval_endpoint")

        report = module.build_adapter_contract_eval(
            candidate_queue_payload(),
            endpoint="https://example.com/v1/model-adapter",
            generated_at="2026-06-30T14:10:00Z",
            request_runner=fixed_good_response,
        )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["summary"]["replayed_total"], 0)
        self.assertEqual(report["violations"][0]["kind"], "endpoint_not_loopback")

    def test_candidate_without_replay_request_is_skipped(self):
        module = load_module(CONTRACT_EVAL, "ai_native_agent_adapter_contract_eval_missing_replay")
        queue = candidate_queue_payload()
        queue["candidates"][0].pop("adapter_replay_request", None)

        report = module.build_adapter_contract_eval(
            queue,
            generated_at="2026-06-30T14:10:00Z",
            request_runner=fixed_good_response,
        )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["summary"]["skipped"], 1)
        self.assertEqual(report["cases"][0]["reason"], "adapter_replay_request_missing")

    def test_cli_replays_against_loopback_http_endpoint(self):
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                self.rfile.read(length)
                payload = json.dumps(fixed_good_response({}), sort_keys=True).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, fmt, *args):
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                root = pathlib.Path(tmpdir)
                queue_path = root / "candidate-queue.json"
                output = root / "adapter-contract-eval.json"
                queue_path.write_text(json.dumps(candidate_queue_payload()), encoding="utf-8")
                completed = subprocess.run(
                    [
                        sys.executable,
                        str(CONTRACT_EVAL),
                        "--root",
                        str(root),
                        "--candidate-queue",
                        str(queue_path),
                        "--output",
                        str(output),
                        "--endpoint",
                        f"http://127.0.0.1:{server.server_port}/v1/model-adapter",
                        "--generated-at",
                        "2026-06-30T14:10:00Z",
                    ],
                    cwd=ROOT,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                report = json.loads(output.read_text(encoding="utf-8")) if output.exists() else None
        finally:
            server.shutdown()
            server.server_close()

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIsNotNone(report)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["replayed_total"], 1)

    def test_docs_include_adapter_contract_eval_runner(self):
        combined = "\n".join(path.read_text(encoding="utf-8") for path in (README, OPERATING_LOOP, ADAPTER_DOC))
        self.assertIn("ai_native_agent_adapter_contract_eval.py", combined)
        self.assertIn("ready_for_adapter_contract_eval", combined)


if __name__ == "__main__":
    unittest.main()
