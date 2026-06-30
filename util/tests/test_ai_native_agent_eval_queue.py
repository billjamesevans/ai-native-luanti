import importlib.util
import json
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
QUEUE = ROOT / "util" / "ai_native_agent_eval_queue.py"
README = ROOT / "doc" / "ai-native-runtime" / "README.md"
OPERATING_LOOP = ROOT / "doc" / "ai-native-runtime" / "project-operating-loop.md"
ADAPTER_DOC = ROOT / "doc" / "ai-native-runtime" / "agents-sdk-model-adapter.md"

PRIVATE_PATTERNS = re.compile(
    r"minecraftpi|192\.168|spacebase|themepark|showcase100|disneyland100|"
    r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY|private_prompt|asset_payload|/Users/",
    re.I,
)
DOC_PRIVATE_PATTERNS = re.compile(
    r"minecraftpi|192\.168|spacebase|themepark|showcase100|disneyland100|"
    r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}|/Users/",
    re.I,
)


def load_queue_module():
    assert QUEUE.is_file(), f"missing {QUEUE}"
    spec = importlib.util.spec_from_file_location("ai_native_agent_eval_queue", QUEUE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def agents_sdk_log_entry(prompt="build me a fire and only a fire"):
    return {
        "schema_version": 1,
        "event_kind": "ai_native_agents_sdk_request_response",
        "created_at": "2026-06-30T12:00:00Z",
        "adapter_name": "openai-agents-sdk-model-adapter",
        "request": {
            "request_kind": "ai_native_model_adapter_request",
            "adapter_contract": "provider_neutral_v1",
            "agent_id": "nova_agent:Eval:guide",
            "owner": "Eval",
            "task_id": "ai-agent-eval:model",
            "public_prompt": prompt,
            "context": {
                "surface_id": "guide",
                "capabilities": "world.read,http.llm",
            },
            "safety": {"public_safe_request": True},
            "bounds": {"max_response_bytes": 4000},
        },
        "response": {
            "response_kind": "ai_native_model_adapter_response",
            "adapter_contract": "provider_neutral_v1",
            "ok": True,
            "message": "Use the fire primitive only after Luanti preview approval.",
            "adapter_name": "openai-agents-sdk-model-adapter",
            "elapsed_us": 42,
            "response": {
                "agentic_execution": True,
                "tools_enabled": ["recommend_build_option", "classify_world_action"],
                "world_mutation_authority": "luanti",
            },
        },
    }


def nova_trace_line(prompt="build a wall of tnt"):
    payload = {
        "schema_version": 1,
        "event_kind": "nova_request_trace",
        "event": "completed",
        "trace": {
            "trace_id": "nova_trace:99",
            "owner": "Eval",
            "agent_id": "nova_agent:Eval:builder",
            "action": "build",
            "route": "deterministic_build_parser",
            "public_prompt": prompt,
            "completed_us": 123456,
            "response": {
                "ok": True,
                "status": "pending_approval",
                "action": "build",
                "build_kind": "wall",
                "build_material_name": "tnt",
                "planned_node_writes": 12,
                "approval_id": "approval:tnt",
            },
        },
    }
    return "[ai_agent_plugin] request_trace=" + json.dumps(payload, sort_keys=True)


def nova_agent_log_entry(prompt="build a wall of tnt"):
    return {
        "ts": "2026-06-30T12:10:00Z",
        "player": "Eval",
        "prompt": prompt,
        "model": "gpt-5-nano",
        "source": "agents_sdk",
        "ok": True,
        "label": "tnt wall",
        "message": "Building a tnt wall.",
        "correction_source": "prompt_contract",
        "contract_satisfied": True,
        "prompt_contract": {
            "intent": "build",
            "material": "tnt",
            "contract_kind": "tnt_wall",
            "contract_required": True,
        },
        "actions": [
            {
                "type": "fill_box",
                "material": "tnt",
                "offset": {"x": 0, "y": 1, "z": 0},
                "size": {"x": 15, "y": 5, "z": 1},
            }
        ],
        "tool_trace": [
            {"tool_name": "analyze_build_intent", "result": {"contract_kind": "tnt_wall"}},
            {"tool_name": "validate_plan_contract", "result": {"contract_satisfied": False}},
        ],
    }


class AgentEvalQueueTests(unittest.TestCase):
    def test_builds_public_safe_eval_candidates_from_sidecar_and_nova_logs(self):
        module = load_queue_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            sidecar_log = root / "agents-sdk-model-adapter.jsonl"
            nova_agent_log = root / "nova-agent-requests.jsonl"
            action_log = root / "debug.log"
            sidecar_log.write_text(json.dumps(agents_sdk_log_entry()) + "\n", encoding="utf-8")
            nova_agent_log.write_text(json.dumps(nova_agent_log_entry()) + "\n", encoding="utf-8")
            action_log.write_text(nova_trace_line() + "\n", encoding="utf-8")

            payload = module.build_eval_candidate_queue(
                agents_sdk_logs=[sidecar_log],
                nova_agent_logs=[nova_agent_log],
                action_logs=[action_log],
                generated_at="2026-06-30T12:30:00Z",
            )

        self.assertEqual(payload["artifact_kind"], "ai_native_agent_eval_candidate_queue")
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["source_summary"]["agents_sdk_log_entries_read"], 1)
        self.assertEqual(payload["source_summary"]["nova_agent_log_entries_read"], 1)
        self.assertEqual(payload["source_summary"]["nova_request_traces_read"], 1)
        self.assertEqual(payload["source_summary"]["candidates_total"], 3)
        self.assertEqual(payload["source_summary"]["ready_for_prompt_eval"], 3)
        self.assertTrue(payload["safety"]["public_safe_output"])
        self.assertFalse(PRIVATE_PATTERNS.search(json.dumps(payload, sort_keys=True)))

        fire = next(candidate for candidate in payload["candidates"] if candidate["case_hint"] == "fire_only_strict")
        self.assertTrue(fire["ready_for_prompt_eval"])
        self.assertEqual(fire["expected"]["build_kind"], "fire")
        self.assertEqual(fire["expected"]["build_material_name"], "fire")
        self.assertEqual(fire["expected"]["planned_node_writes"], 1)
        self.assertTrue(fire["expected"]["forbidden_extra_structure"])

        tnt_sources = {
            candidate["source_kind"]: candidate
            for candidate in payload["candidates"]
            if candidate["case_hint"] == "tnt_wall"
        }
        self.assertIn("nova_request_trace", tnt_sources)
        self.assertIn("nova_agent_sidecar_request_response", tnt_sources)
        trace_tnt = tnt_sources["nova_request_trace"]
        self.assertEqual(trace_tnt["expected"]["build_kind"], "wall")
        self.assertEqual(trace_tnt["expected"]["build_material_name"], "tnt")
        self.assertEqual(trace_tnt["expected"]["planned_node_writes"], 12)
        self.assertFalse(trace_tnt["expected"]["danger_refusal_allowed"])
        sidecar_tnt = tnt_sources["nova_agent_sidecar_request_response"]
        self.assertEqual(sidecar_tnt["observed"]["contract_kind"], "tnt_wall")
        self.assertTrue(sidecar_tnt["observed"]["contract_satisfied"])
        self.assertEqual(sidecar_tnt["observed"]["correction_source"], "prompt_contract")
        self.assertEqual(sidecar_tnt["observed"]["build_kind"], "wall")
        self.assertEqual(sidecar_tnt["observed"]["build_material_name"], "tnt")
        self.assertEqual(sidecar_tnt["observed"]["planned_node_writes"], 75)
        self.assertEqual(
            sidecar_tnt["observed"]["tool_trace_names"],
            ["analyze_build_intent", "validate_plan_contract"],
        )

    def test_private_entries_are_skipped_and_not_retained(self):
        module = load_queue_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            sidecar_log = root / "agents-sdk-model-adapter.jsonl"
            private_entry = agents_sdk_log_entry("explain this private path")
            private_entry["request"]["context"]["private_prompt"] = "must not be retained"
            sidecar_log.write_text(json.dumps(private_entry) + "\n", encoding="utf-8")

            payload = module.build_eval_candidate_queue(
                agents_sdk_logs=[sidecar_log],
                generated_at="2026-06-30T12:30:00Z",
            )

        raw = json.dumps(payload, sort_keys=True)
        self.assertEqual(payload["status"], "empty")
        self.assertEqual(payload["source_summary"]["entries_skipped_private"], 1)
        self.assertEqual(payload["source_summary"]["candidates_total"], 0)
        self.assertNotIn("must not be retained", raw)
        self.assertNotIn("private_prompt", raw)
        self.assertTrue(payload["violations"])
        self.assertTrue(payload["safety"]["public_safe_output"])

    def test_agents_sdk_candidate_uses_player_request_and_tool_trace(self):
        module = load_queue_module()
        entry = agents_sdk_log_entry(
            "AI-native Luanti model adapter request.\nplayer_request: build me a fire and only a fire"
        )
        entry["request"]["context"].update({
            "intent": "build_planning",
            "player_request": "build me a fire and only a fire",
            "candidate_summary": "fire:fire:fire:1|platform:platform:stone:9",
        })
        entry["response"]["response"].update({
            "selected_option_id": "fire",
            "tool_decision_source": "agents_sdk_function_tool",
            "tool_trace": [
                {"tool_name": "recall_build_prompt_memory"},
                {"tool_name": "recommend_build_option"},
            ],
            "tool_decisions": {
                "build_option": {
                    "selected_option_id": "fire",
                    "decision_source": "reviewed_prompt_memory",
                    "memory_match": {
                        "memory_available": True,
                        "matched_case_id": "promoted_fire_only_strict_123",
                    },
                },
            },
        })

        candidate = module.candidate_from_agents_sdk_entry(entry)

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["prompt"], "build me a fire and only a fire")
        self.assertEqual(candidate["prompt_source"], "context.player_request")
        self.assertEqual(candidate["case_hint"], "fire_only_strict")
        self.assertEqual(candidate["observed"]["selected_option_id"], "fire")
        self.assertEqual(candidate["observed"]["tool_decision_source"], "agents_sdk_function_tool")
        self.assertEqual(candidate["observed"]["build_option_decision_source"], "reviewed_prompt_memory")
        self.assertEqual(candidate["observed"]["build_option_selected_option_id"], "fire")
        self.assertTrue(candidate["observed"]["memory_available"])
        self.assertEqual(
            candidate["observed"]["tool_trace_names"],
            ["recall_build_prompt_memory", "recommend_build_option"],
        )

    def test_agents_sdk_candidate_extracts_embedded_player_request_from_wrapper_prompt(self):
        module = load_queue_module()
        entry = agents_sdk_log_entry(
            "\n".join(
                [
                    "Plan a Luanti build request using only the listed executable options.",
                    "Luanti will enforce capabilities, approval, rollback, and world mutation.",
                    "Player request: build a small shelter",
                    "Options:",
                    "- fire: Single fire kind=fire material=fire planned_writes=1",
                ]
            )
        )

        candidate = module.candidate_from_agents_sdk_entry(entry)

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["prompt"], "build a small shelter")
        self.assertEqual(candidate["prompt_source"], "request.public_prompt.player_request")
        self.assertNotEqual(candidate["case_hint"], "fire_only_strict")
        self.assertFalse(candidate["ready_for_prompt_eval"])

    def test_nova_agent_log_candidate_records_contract_and_correction(self):
        module = load_queue_module()

        candidate = module.candidate_from_nova_agent_log_entry(nova_agent_log_entry())

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["source_kind"], "nova_agent_sidecar_request_response")
        self.assertEqual(candidate["case_hint"], "tnt_wall")
        self.assertEqual(candidate["priority"], "high")
        self.assertEqual(candidate["route"], "agents_sdk")
        self.assertEqual(candidate["action"], "build")
        self.assertEqual(candidate["observed_status"], "corrected")
        self.assertEqual(candidate["observed_reason"], "prompt_contract")
        self.assertEqual(candidate["observed"]["contract_kind"], "tnt_wall")
        self.assertTrue(candidate["observed"]["contract_satisfied"])
        self.assertEqual(candidate["observed"]["planned_node_writes"], 75)
        self.assertEqual(candidate["expected"]["planned_node_writes"], 12)

    def test_cli_writes_candidate_queue(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            sidecar_log = root / "agents-sdk-model-adapter.jsonl"
            nova_agent_log = root / "nova-agent-requests.jsonl"
            output = root / "candidate-queue.json"
            sidecar_log.write_text(json.dumps(agents_sdk_log_entry("build a fire")) + "\n", encoding="utf-8")
            nova_agent_log.write_text(json.dumps(nova_agent_log_entry()) + "\n", encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(QUEUE),
                    "--root",
                    str(root),
                    "--agents-sdk-log",
                    str(sidecar_log),
                    "--nova-agent-log",
                    str(nova_agent_log),
                    "--output",
                    str(output),
                    "--generated-at",
                    "2026-06-30T12:30:00Z",
                ],
                cwd=ROOT,
                check=False,
                text=True,
                capture_output=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "ready")
            self.assertEqual(payload["source_summary"]["nova_agent_log_entries_read"], 1)
            self.assertEqual(
                {candidate["case_hint"] for candidate in payload["candidates"]},
                {"build_fire", "tnt_wall"},
            )

    def test_docs_include_agent_improvement_loop(self):
        bodies = [path.read_text(encoding="utf-8") for path in (README, OPERATING_LOOP, ADAPTER_DOC)]
        combined = "\n".join(bodies)
        self.assertIn("ai_native_agent_eval_queue.py", combined)
        self.assertIn("Agent Improvement Loop", combined)
        self.assertIn("agents-sdk-model-adapter.jsonl", combined)
        loop_sections = []
        for body in bodies:
            if "## Agent Improvement Loop" not in body:
                continue
            section = body.split("## Agent Improvement Loop", 1)[1]
            section = section.split("\n## ", 1)[0]
            loop_sections.append(section)
        self.assertGreaterEqual(len(loop_sections), 2)
        self.assertNotRegex("\n".join(loop_sections), DOC_PRIVATE_PATTERNS)


if __name__ == "__main__":
    unittest.main()
