import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "util" / "ai_native_agents_sdk_bridge_contract.py"
AGENT = ROOT / "tools" / "agents_sdk_model_adapter" / "agent.py"


class AgentsSdkBridgeContractTests(unittest.TestCase):
    def test_contract_validator_passes(self):
        spec = importlib.util.spec_from_file_location("agents_sdk_bridge_contract", CONTRACT)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        result = module.validate_contract()

        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["violations"], [])
        self.assertEqual(result["bridge_dir"], "tools/agents_sdk_model_adapter")

    def test_offline_smoke_returns_provider_neutral_response(self):
        spec = importlib.util.spec_from_file_location("agents_sdk_agent", AGENT)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        response = module.run_model_adapter_request(module.sample_request(), force_offline=True)

        self.assertTrue(response["ok"])
        self.assertEqual(response["response_kind"], "ai_native_model_adapter_response")
        self.assertEqual(response["adapter_name"], "openai-agents-sdk-model-adapter")
        self.assertFalse(response["response"]["agentic_execution"])
        self.assertIn("WebSearchTool", response["response"]["tools_enabled"])
        self.assertIn("recommend_build_option", response["response"]["tools_enabled"])
        self.assertEqual(response["response"]["world_mutation_authority"], "luanti")
        tool_powers = response["response"]["tool_powers"]
        self.assertIn("WebSearchTool", {power["name"] for power in tool_powers})
        self.assertIn("recommend_build_option", {power["name"] for power in tool_powers})
        self.assertTrue(all(power["direct_world_mutation"] is False for power in tool_powers))

    def test_build_option_recommender_is_read_only_and_bounded(self):
        spec = importlib.util.spec_from_file_location("agents_sdk_agent", AGENT)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        result = module.recommend_build_option_payload(
            "platform:platform:default:4|marker:marker:default:1|tnt_wall:wall:tnt:12",
            "build something dramatic with tnt",
        )

        self.assertEqual(result["selected_option_id"], "tnt_wall")
        self.assertEqual(result["candidate_count"], 3)
        self.assertTrue(result["requires_preview"])
        self.assertTrue(result["requires_approval"])
        self.assertTrue(result["requires_rollback"])
        self.assertFalse(result["direct_world_mutation"])
        self.assertEqual(result["policy"], "luanti_executes_only_after_player_approval")

    def test_build_planning_response_exposes_structured_tool_decision(self):
        spec = importlib.util.spec_from_file_location("agents_sdk_agent", AGENT)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        request = module.sample_request()
        request["public_prompt"] = "\n".join([
            "Plan a Luanti build request using only the listed executable options.",
            "Player request: build a wall of tnt",
            "Options:",
            "- platform: Small platform kind=platform material=default planned_writes=4",
            "- tnt_wall: Small TNT wall kind=wall material=tnt planned_writes=12",
        ])
        request["context"] = {
            "surface_id": "builder",
            "intent": "build_planning",
            "player_request": "build a wall of tnt",
            "candidate_summary": "platform:platform:default:4|tnt_wall:wall:tnt:12",
        }

        response = module.run_model_adapter_request(request, force_offline=True)

        self.assertTrue(response["ok"])
        nested = response["response"]
        self.assertFalse(nested["agentic_execution"])
        self.assertEqual(nested["selected_option_id"], "tnt_wall")
        self.assertEqual(
            nested["tool_decisions"]["build_option"]["selected_option_id"],
            "tnt_wall",
        )
        self.assertFalse(nested["tool_decisions"]["build_option"]["direct_world_mutation"])

    def test_request_response_log_is_public_safe_jsonl(self):
        spec = importlib.util.spec_from_file_location("agents_sdk_agent", AGENT)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = pathlib.Path(tmpdir) / "agents-sdk-model-adapter.jsonl"
            old_log_path = os.environ.get("AI_NATIVE_AGENT_LOG_PATH")
            os.environ["AI_NATIVE_AGENT_LOG_PATH"] = str(log_path)
            try:
                request = module.sample_request()
                request["context"]["private_prompt"] = "must-not-log"
                request["context"]["api_key"] = "must-not-log"
                response = module.run_model_adapter_request(request, force_offline=True)
            finally:
                if old_log_path is None:
                    os.environ.pop("AI_NATIVE_AGENT_LOG_PATH", None)
                else:
                    os.environ["AI_NATIVE_AGENT_LOG_PATH"] = old_log_path

            self.assertTrue(response["ok"])
            lines = log_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            entry = json.loads(lines[0])
            raw_entry = json.dumps(entry, sort_keys=True)
            self.assertEqual(entry["event_kind"], "ai_native_agents_sdk_request_response")
            self.assertEqual(entry["adapter_name"], "openai-agents-sdk-model-adapter")
            self.assertEqual(entry["request"]["request_kind"], "ai_native_model_adapter_request")
            self.assertEqual(entry["response"]["response_kind"], "ai_native_model_adapter_response")
            self.assertNotIn("must-not-log", raw_entry)
            self.assertNotIn("OPENAI_API_KEY", raw_entry)
            self.assertNotIn("private_prompt", raw_entry)
            self.assertNotIn("api_key", entry["request"]["context"])

    def test_cli_contract_passes(self):
        completed = subprocess.run(
            [sys.executable, str(CONTRACT)],
            cwd=ROOT,
            check=False,
            text=True,
            capture_output=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn('"status": "pass"', completed.stdout)


if __name__ == "__main__":
    unittest.main()
