import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
READINESS = ROOT / "util" / "ai_native_agents_sdk_sidecar_readiness.py"


def load_readiness_module():
    spec = importlib.util.spec_from_file_location("agents_sdk_sidecar_readiness", READINESS)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class AgentsSdkSidecarReadinessTests(unittest.TestCase):
    def tool_powers(self):
        return [
            {
                "name": "summarize_runtime_capabilities",
                "kind": "function_tool",
                "direct_world_mutation": False,
            },
            {
                "name": "classify_world_action",
                "kind": "function_tool",
                "direct_world_mutation": False,
            },
            {
                "name": "WebSearchTool",
                "kind": "hosted_tool",
                "direct_world_mutation": False,
            },
        ]

    def test_offline_smoke_passes_without_credentials(self):
        module = load_readiness_module()

        report = module.run_readiness(mode="offline-smoke")

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["report_kind"], "ai_native_agents_sdk_sidecar_readiness")
        self.assertTrue(report["checks"]["offline_smoke"])
        self.assertTrue(report["checks"]["no_provider_credentials_required"])
        self.assertTrue(report["checks"]["no_forbidden_payload_keys"])
        self.assertEqual(report["response"]["response_kind"], "ai_native_model_adapter_response")
        self.assertEqual(report["response"]["adapter_name"], "openai-agents-sdk-model-adapter")
        self.assertFalse(report["response"]["agentic_execution"])
        self.assertTrue(report["checks"]["bounded_response"])
        self.assertTrue(report["checks"]["tool_powers_declared"])
        self.assertTrue(report["checks"]["no_direct_world_mutation_tools"])
        self.assertEqual(report["response"]["world_mutation_authority"], "luanti")
        self.assertIn("WebSearchTool", {power["name"] for power in report["response"]["tool_powers"]})

    def test_managed_http_sidecar_passes_on_loopback(self):
        module = load_readiness_module()

        report = module.run_readiness(mode="managed-http", port=0, timeout_seconds=5)

        self.assertEqual(report["status"], "pass", report)
        self.assertTrue(report["loopback_endpoint"])
        self.assertTrue(report["checks"]["health_endpoint"])
        self.assertTrue(report["checks"]["model_adapter_endpoint"])
        self.assertFalse(report["checks"]["live_agent_execution"])
        self.assertTrue(report["checks"]["tool_powers_declared"])
        self.assertTrue(report["checks"]["no_direct_world_mutation_tools"])
        self.assertEqual(report["health"]["contract"], "provider_neutral_v1")
        self.assertEqual(report["response"]["adapter_contract"], "provider_neutral_v1")
        self.assertEqual(report["health"]["world_mutation_authority"], "luanti")
        self.assertIn("WebSearchTool", {power["name"] for power in report["health"]["tool_powers"]})

    def test_rejects_non_loopback_endpoint(self):
        module = load_readiness_module()

        report = module.run_readiness(
            mode="existing-http",
            endpoint="https://example.com/v1/model-adapter",
        )

        self.assertEqual(report["status"], "fail")
        self.assertFalse(report["checks"]["loopback_endpoint"])
        self.assertEqual(report["violations"][0]["kind"], "endpoint_not_loopback")

    def test_require_live_agent_fails_for_offline_smoke(self):
        module = load_readiness_module()

        report = module.run_readiness(mode="offline-smoke", require_live_agent=True)

        self.assertEqual(report["status"], "fail")
        self.assertTrue(report["checks"]["offline_smoke"])
        self.assertFalse(report["checks"]["live_agent_execution"])
        self.assertEqual(report["violations"][0]["kind"], "live_agent_requires_http")

    def test_existing_http_live_agent_passes_with_agentic_execution(self):
        module = load_readiness_module()
        tool_powers = self.tool_powers()

        def fake_http_json(method, url, payload=None, *, timeout_seconds):
            if method == "GET":
                return 200, {
                    "service": "ai-native-luanti-agents-sdk-model-adapter",
                    "status": "ready",
                    "agents_sdk_available": True,
                    "openai_api_key_present": True,
                    "web_search_tool_available": True,
                    "tool_powers": tool_powers,
                    "world_mutation_authority": "luanti",
                    "adapter_name": "openai-agents-sdk-model-adapter",
                    "contract": "provider_neutral_v1",
                }
            return 200, {
                "ok": True,
                "response_kind": "ai_native_model_adapter_response",
                "adapter_contract": "provider_neutral_v1",
                "adapter_name": "openai-agents-sdk-model-adapter",
                "message": "Live public-safe guidance.",
                "response": {
                    "agentic_execution": True,
                    "web_search_available": True,
                    "web_search_used": True,
                    "tools_enabled": [
                        "summarize_runtime_capabilities",
                        "classify_world_action",
                        "WebSearchTool",
                    ],
                    "tool_powers": tool_powers,
                    "world_mutation_authority": "luanti",
                },
            }

        fake_agent_module = mock.Mock()
        fake_agent_module.sample_request.return_value = {
            "request_kind": "ai_native_model_adapter_request",
            "public_prompt": "public prompt",
        }

        with mock.patch.object(module, "_http_json", side_effect=fake_http_json), \
                mock.patch.object(module, "_load_agent_module", return_value=fake_agent_module):
            report = module.run_readiness(
                mode="existing-http",
                endpoint="http://127.0.0.1:8766/v1/model-adapter",
                require_live_agent=True,
                live_public_prompt="public live probe",
            )

        self.assertEqual(report["status"], "pass", report)
        self.assertTrue(report["live_agent_required"])
        self.assertTrue(report["checks"]["provider_credentials_present"])
        self.assertTrue(report["checks"]["agents_sdk_available"])
        self.assertTrue(report["checks"]["web_search_tool_available"])
        self.assertTrue(report["checks"]["live_agent_execution"])
        self.assertTrue(report["checks"]["live_web_lookup_available"])
        self.assertTrue(report["checks"]["bounded_response"])
        self.assertEqual(report["response"]["world_mutation_authority"], "luanti")

    def test_cli_writes_output_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output = pathlib.Path(tmpdir) / "readiness.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(READINESS),
                    "--mode",
                    "offline-smoke",
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                check=False,
                text=True,
                capture_output=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["report_kind"], "ai_native_agents_sdk_sidecar_readiness")


if __name__ == "__main__":
    unittest.main()
