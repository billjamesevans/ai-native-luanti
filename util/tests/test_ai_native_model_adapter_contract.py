import importlib.util
import json
import pathlib
import re
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
CLI = ROOT / "util" / "ai_native_model_adapter_contract.py"
DOC = ROOT / "doc" / "ai-native-runtime" / "model-adapter-contract.md"
README = ROOT / "doc" / "ai-native-runtime" / "README.md"
REQUEST_EXAMPLE = ROOT / "doc" / "ai-native-runtime" / "examples" / "model-adapter-request.example.json"
RESPONSE_EXAMPLE = ROOT / "doc" / "ai-native-runtime" / "examples" / "model-adapter-response.example.json"
REQUEST_SCHEMA = ROOT / "doc" / "ai-native-runtime" / "schemas" / "model-adapter-request.schema.json"
RESPONSE_SCHEMA = ROOT / "doc" / "ai-native-runtime" / "schemas" / "model-adapter-response.schema.json"

PRIVATE_PATTERNS = re.compile(
    r"minecraftpi|192\.168|spacebase|themepark|showcase100|disneyland100|"
    r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY|private_prompt|"
    r"asset_payload|raw_provider_response|/Users/",
    re.I,
)


def load_contract_module():
    assert CLI.is_file(), f"missing {CLI}"
    spec = importlib.util.spec_from_file_location("ai_native_model_adapter_contract", CLI)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AIModelAdapterContractTests(unittest.TestCase):
    def test_contract_artifacts_exist_and_are_linked(self):
        for path in [CLI, DOC, REQUEST_EXAMPLE, RESPONSE_EXAMPLE, REQUEST_SCHEMA, RESPONSE_SCHEMA]:
            self.assertTrue(path.is_file(), f"missing {path}")

        readme = README.read_text(encoding="utf-8")
        self.assertIn("model-adapter-contract.md", readme)
        self.assertIn("python3 util/ai_native_model_adapter_contract.py", readme)

    def test_examples_are_public_safe_and_provider_neutral(self):
        request = json.loads(REQUEST_EXAMPLE.read_text(encoding="utf-8"))
        response = json.loads(RESPONSE_EXAMPLE.read_text(encoding="utf-8"))
        combined = json.dumps({"request": request, "response": response}, sort_keys=True)

        self.assertNotRegex(combined, PRIVATE_PATTERNS)
        self.assertEqual(request["schema_version"], 1)
        self.assertEqual(request["request_kind"], "ai_native_model_adapter_request")
        self.assertEqual(request["adapter_contract"], "provider_neutral_v1")
        self.assertNotIn("prompt", request)
        self.assertNotIn("private_prompt", request)
        self.assertTrue(request["safety"]["public_safe_request"])
        self.assertFalse(request["safety"]["private_input_retained"])
        self.assertTrue(request["safety"]["no_provider_credentials"])
        self.assertEqual(request["bounds"]["max_response_bytes"], 4000)
        self.assertEqual(response["schema_version"], 1)
        self.assertEqual(response["response_kind"], "ai_native_model_adapter_response")
        self.assertTrue(response["ok"])
        self.assertIn("message", response)
        self.assertNotIn("raw_provider_response", response)
        self.assertNotIn("private_payload", response)

    def test_contract_verifier_reports_ready(self):
        contract = load_contract_module()

        report = contract.build_report(ROOT)

        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["violations"], [])
        self.assertTrue(report["safety"]["provider_neutral"])
        self.assertTrue(report["safety"]["public_safe_examples"])
        self.assertTrue(report["safety"]["no_raw_provider_payloads"])
        self.assertEqual(
            report["contract"]["runtime_entrypoint"],
            "core.ai_model_ops.request",
        )
        self.assertEqual(
            report["contract"]["agent_plugin_entrypoint"],
            "core.ai_agent_plugin.set_model_adapter",
        )

    def test_cli_writes_machine_readable_report(self):
        contract = load_contract_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            output = pathlib.Path(tmpdir) / "model-adapter-contract.json"

            exit_code = contract.main(["--root", str(ROOT), "--output", str(output)])

            self.assertEqual(exit_code, 0)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "pass")


if __name__ == "__main__":
    unittest.main()
