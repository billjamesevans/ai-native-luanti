import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "util" / "ai_native_agent_live_review_gate.py"
LIVE_REVIEW_TEST = ROOT / "util" / "tests" / "test_ai_native_agent_live_review_loop.py"


def load_fixture_module():
    spec = importlib.util.spec_from_file_location("ai_native_agent_live_review_loop_fixture", LIVE_REVIEW_TEST)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LiveReviewGateTests(unittest.TestCase):
    def test_cli_passes_review_gate(self):
        fixtures = load_fixture_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            status_file = root / "status.json"
            agents_log = root / "agents-sdk-model-adapter.jsonl"
            output_dir = root / "artifacts"
            gate_output = root / "gate-result.json"
            status_file.write_text(json.dumps(fixtures.status_payload()) + "\n", encoding="utf-8")
            agents_log.write_text(json.dumps(fixtures.agents_sdk_log_entry()) + "\n", encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--root",
                    str(root),
                    "--status-json",
                    str(status_file),
                    "--agents-sdk-log",
                    str(agents_log),
                    "--trace-id",
                    "nova_trace:11",
                    "--output-dir",
                    str(output_dir),
                    "--artifact-prefix",
                    "trace11",
                    "--gate-output",
                    str(gate_output),
                    "--generated-at",
                    "2026-07-02T12:30:00Z",
                ],
                cwd=ROOT,
                check=False,
                text=True,
                capture_output=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            gate = json.loads(completed.stdout)
            persisted = json.loads(gate_output.read_text(encoding="utf-8"))

            self.assertEqual(gate["status"], "pass")
            self.assertEqual(persisted["status"], "pass")
            self.assertEqual(gate["artifact_kind"], "openrealm_live_review_gate_result")
            self.assertEqual(gate["source_trace_id"], "nova_trace:11")
            self.assertEqual(gate["case_hint"], "fire_only_strict")
            self.assertTrue(all(gate["checks"].values()))
            self.assertEqual(gate["violations"], [])
            self.assertTrue((output_dir / "trace11-studio-review-packet.json").is_file())
            self.assertTrue((output_dir / "trace11-candidate-queue.json").is_file())
            self.assertTrue((output_dir / "trace11-operator-labels.json").is_file())
            self.assertTrue((output_dir / "trace11-case-pack.json").is_file())

    def test_cli_rejects_unsafe_status_before_gate_output(self):
        fixtures = load_fixture_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            status = fixtures.status_payload()
            status["adapter_log"]["recent_traces"][0]["credentials"] = {"kind": "redacted"}
            status_file = root / "status.json"
            agents_log = root / "agents-sdk-model-adapter.jsonl"
            output_dir = root / "artifacts"
            gate_output = root / "gate-result.json"
            status_file.write_text(json.dumps(status) + "\n", encoding="utf-8")
            agents_log.write_text(json.dumps(fixtures.agents_sdk_log_entry()) + "\n", encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--root",
                    str(root),
                    "--status-json",
                    str(status_file),
                    "--agents-sdk-log",
                    str(agents_log),
                    "--output-dir",
                    str(output_dir),
                    "--artifact-prefix",
                    "trace11",
                    "--gate-output",
                    str(gate_output),
                ],
                cwd=ROOT,
                check=False,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertIn("status payload is not public-safe", completed.stderr)
            self.assertFalse(gate_output.exists())
            self.assertFalse(output_dir.exists())


if __name__ == "__main__":
    unittest.main()
