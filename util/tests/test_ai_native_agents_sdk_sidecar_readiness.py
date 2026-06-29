import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


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

    def test_managed_http_sidecar_passes_on_loopback(self):
        module = load_readiness_module()

        report = module.run_readiness(mode="managed-http", port=0, timeout_seconds=5)

        self.assertEqual(report["status"], "pass", report)
        self.assertTrue(report["loopback_endpoint"])
        self.assertTrue(report["checks"]["health_endpoint"])
        self.assertTrue(report["checks"]["model_adapter_endpoint"])
        self.assertEqual(report["health"]["contract"], "provider_neutral_v1")
        self.assertEqual(report["response"]["adapter_contract"], "provider_neutral_v1")

    def test_rejects_non_loopback_endpoint(self):
        module = load_readiness_module()

        report = module.run_readiness(
            mode="existing-http",
            endpoint="https://example.com/v1/model-adapter",
        )

        self.assertEqual(report["status"], "fail")
        self.assertFalse(report["checks"]["loopback_endpoint"])
        self.assertEqual(report["violations"][0]["kind"], "endpoint_not_loopback")

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
