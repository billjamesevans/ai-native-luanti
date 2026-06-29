import importlib.util
import pathlib
import subprocess
import sys
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
        self.assertEqual(response["response"]["world_mutation_authority"], "luanti")
        tool_powers = response["response"]["tool_powers"]
        self.assertIn("WebSearchTool", {power["name"] for power in tool_powers})
        self.assertTrue(all(power["direct_world_mutation"] is False for power in tool_powers))

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
