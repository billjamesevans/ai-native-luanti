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


class AgentEvalQueueTests(unittest.TestCase):
    def test_builds_public_safe_eval_candidates_from_sidecar_and_nova_logs(self):
        module = load_queue_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            sidecar_log = root / "agents-sdk-model-adapter.jsonl"
            action_log = root / "debug.log"
            sidecar_log.write_text(json.dumps(agents_sdk_log_entry()) + "\n", encoding="utf-8")
            action_log.write_text(nova_trace_line() + "\n", encoding="utf-8")

            payload = module.build_eval_candidate_queue(
                agents_sdk_logs=[sidecar_log],
                action_logs=[action_log],
                generated_at="2026-06-30T12:30:00Z",
            )

        self.assertEqual(payload["artifact_kind"], "ai_native_agent_eval_candidate_queue")
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["source_summary"]["agents_sdk_log_entries_read"], 1)
        self.assertEqual(payload["source_summary"]["nova_request_traces_read"], 1)
        self.assertEqual(payload["source_summary"]["candidates_total"], 2)
        self.assertEqual(payload["source_summary"]["ready_for_prompt_eval"], 2)
        self.assertTrue(payload["safety"]["public_safe_output"])
        self.assertFalse(PRIVATE_PATTERNS.search(json.dumps(payload, sort_keys=True)))

        by_hint = {candidate["case_hint"]: candidate for candidate in payload["candidates"]}
        fire = by_hint["fire_only_strict"]
        self.assertTrue(fire["ready_for_prompt_eval"])
        self.assertEqual(fire["expected"]["build_kind"], "fire")
        self.assertEqual(fire["expected"]["build_material_name"], "fire")
        self.assertEqual(fire["expected"]["planned_node_writes"], 1)
        self.assertTrue(fire["expected"]["forbidden_extra_structure"])

        tnt = by_hint["tnt_wall"]
        self.assertEqual(tnt["source_kind"], "nova_request_trace")
        self.assertEqual(tnt["expected"]["build_kind"], "wall")
        self.assertEqual(tnt["expected"]["build_material_name"], "tnt")
        self.assertEqual(tnt["expected"]["planned_node_writes"], 12)
        self.assertFalse(tnt["expected"]["danger_refusal_allowed"])

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

    def test_cli_writes_candidate_queue(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            sidecar_log = root / "agents-sdk-model-adapter.jsonl"
            output = root / "candidate-queue.json"
            sidecar_log.write_text(json.dumps(agents_sdk_log_entry("build a fire")) + "\n", encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(QUEUE),
                    "--root",
                    str(root),
                    "--agents-sdk-log",
                    str(sidecar_log),
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
            self.assertEqual(payload["candidates"][0]["case_hint"], "build_fire")

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
