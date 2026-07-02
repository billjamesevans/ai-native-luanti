import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "util" / "ai_native_agent_studio_review_packet.py"


def load_module():
    spec = importlib.util.spec_from_file_location("ai_native_agent_studio_review_packet_test", SCRIPT)
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
                    "tools_enabled": ["select_build_option", "plan_build_actions"],
                },
                {
                    "created_at": "2026-07-02T12:00:01Z",
                    "agent_id": "nova_agent:PromptEvalLive",
                    "task_id": "ai-agent-build-planner:nova_trace:12",
                    "source_trace_id": "nova_trace:12",
                    "ok": True,
                    "agentic_execution": True,
                    "selected_option_id": "generated_openrealm_lakeside_village",
                    "planned_node_writes": 96,
                    "required_tool_calls_satisfied": True,
                    "tool_decision_source": "agents_sdk_generated_tool_completion",
                    "web_search_available": True,
                    "world_mutation_authority": "luanti",
                    "direct_world_mutation": False,
                    "tools_enabled": ["propose_build_option", "plan_build_actions"],
                },
            ],
        },
        "public_safe": True,
    }


class StudioReviewPacketTests(unittest.TestCase):
    def test_builds_review_packet_from_status_trace(self):
        module = load_module()
        packet = module.build_review_packet(
            status_payload(),
            trace_id="nova_trace:11",
            generated_at="2026-07-02T12:30:00Z",
        )

        self.assertEqual(packet["artifact_kind"], "openrealm_studio_agent_review_packet")
        self.assertEqual(packet["source"]["source_trace_id"], "nova_trace:11")
        self.assertEqual(packet["source"]["selected_option_id"], "fire")
        self.assertEqual(packet["expected"]["build_kind"], "fire")
        self.assertEqual(packet["expected"]["build_material_name"], "fire")
        self.assertEqual(packet["expected"]["planned_node_writes"], 1)
        self.assertEqual(packet["expected"]["selected_candidate_id"], "fire")
        self.assertIn("case=fire_only_strict", packet["operator_feedback_command"])
        self.assertTrue(packet["safety"]["public_safe_output"])

    def test_cli_writes_review_packet_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            status_file = root / "status.json"
            packet_file = root / "review-packet.json"
            status_file.write_text(json.dumps(status_payload()) + "\n", encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--status-json",
                    str(status_file),
                    "--trace-id",
                    "nova_trace:11",
                    "--output",
                    str(packet_file),
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
            packet = json.loads(packet_file.read_text(encoding="utf-8"))

            self.assertEqual(summary["status"], "ready")
            self.assertEqual(summary["source_trace_id"], "nova_trace:11")
            self.assertEqual(summary["selected_option_id"], "fire")
            self.assertEqual(summary["case_hint"], "fire_only_strict")
            self.assertEqual(packet["expected"]["build_kind"], "fire")

    def test_cli_rejects_private_status_payload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            status = status_payload()
            status["adapter_log"]["recent_traces"][0]["credentials"] = {"kind": "redacted"}
            status_file = root / "status.json"
            packet_file = root / "review-packet.json"
            status_file.write_text(json.dumps(status) + "\n", encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--status-json",
                    str(status_file),
                    "--output",
                    str(packet_file),
                ],
                cwd=ROOT,
                check=False,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertIn("status payload is not public-safe", completed.stderr)
            self.assertFalse(packet_file.exists())


if __name__ == "__main__":
    unittest.main()
