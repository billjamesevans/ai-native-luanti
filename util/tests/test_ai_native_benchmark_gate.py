import json
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
CAPTURE_CLI = ROOT / "util" / "ai_native_benchmark_capture.py"
PROMOTE_CLI = ROOT / "util" / "ai_native_benchmark_promote.py"
GATE_CLI = ROOT / "util" / "ai_native_benchmark_gate.py"
DOC = ROOT / "doc" / "ai-native-runtime" / "benchmark-baseline-retention.md"

PRIVATE_PATTERNS = re.compile(
    r"minecraftpi|192\.168|spacebase|themepark|showcase100|disneyland100|"
    r"sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY|private_prompt|asset_payload|/Users/",
    re.I,
)


class BenchmarkGateTests(unittest.TestCase):
    def capture(self, output_root, commit="baseline-commit"):
        completed = subprocess.run(
            [
                sys.executable,
                str(CAPTURE_CLI),
                "--output-root",
                str(output_root),
                "--hardware-class",
                "local-mac",
                "--date",
                "2026-06-27",
                "--luanti-commit",
                commit,
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return output_root / "local-mac" / "2026-06-27" / commit

    def promote(self, capture_dir, output_root):
        completed = subprocess.run(
            [
                sys.executable,
                str(PROMOTE_CLI),
                "--capture-dir",
                str(capture_dir),
                "--output-root",
                str(output_root),
                "--source-label",
                "reviewed-clean",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def run_gate(self, output_root, commit="branch-commit", check=True):
        self.assertTrue(GATE_CLI.is_file(), f"missing {GATE_CLI}")
        completed = subprocess.run(
            [
                sys.executable,
                str(GATE_CLI),
                "--output-root",
                str(output_root),
                "--hardware-class",
                "local-mac",
                "--date",
                "2026-06-28",
                "--luanti-commit",
                commit,
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if check:
            self.assertEqual(completed.returncode, 0, completed.stderr)
        gate_path = output_root / "local-mac" / "2026-06-28" / commit / "benchmark-gate-manifest.json"
        gate = None
        if gate_path.is_file():
            gate = json.loads(gate_path.read_text(encoding="utf-8"))
        return completed, gate_path, gate

    def test_gate_passes_against_promoted_accepted_baseline(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            self.promote(self.capture(output_root), output_root)

            completed, gate_path, gate = self.run_gate(output_root)

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(gate_path.is_file())
            self.assertEqual(gate["schema_version"], 1)
            self.assertEqual(gate["overall_status"], "pass")
            self.assertEqual(gate["hardware_class"], "local-mac")
            self.assertEqual(gate["branch_ref"]["luanti_commit"], "branch-commit")
            self.assertEqual(gate["accepted_baseline"]["source_label"], "reviewed-clean")
            self.assertEqual(gate["comparison_statuses"]["mutation"], "pass")
            self.assertEqual(gate["comparison_statuses"]["demo_entity"], "pass")
            self.assertEqual(gate["failure_reasons"], [])
            self.assertEqual(
                gate["logical_run_dir"],
                "local/benchmarks/local-mac/2026-06-28/branch-commit",
            )

            serialized = json.dumps(gate, sort_keys=True)
            self.assertNotIn(str(output_root), serialized)
            self.assertNotRegex(serialized, PRIVATE_PATTERNS)

    def test_gate_fails_when_branch_regresses_accepted_baseline(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            self.promote(self.capture(output_root), output_root)
            accepted_report = output_root / "local-mac" / "accepted" / "mutation-benchmark-report.json"
            payload = json.loads(accepted_report.read_text(encoding="utf-8"))
            payload["scenarios"][0]["metrics"]["max_lag_ms"] = 0.001
            accepted_report.write_text(json.dumps(payload), encoding="utf-8")

            completed, _, gate = self.run_gate(output_root, check=False)

            self.assertEqual(completed.returncode, 1)
            self.assertIsNotNone(gate)
            self.assertEqual(gate["overall_status"], "fail")
            self.assertEqual(gate["comparison_statuses"]["mutation"], "fail")
            self.assertEqual(gate["comparison_statuses"]["demo_entity"], "pass")
            self.assertTrue(
                any("mutation" in reason and "fail" in reason for reason in gate["failure_reasons"])
            )

    def test_gate_refuses_missing_accepted_baseline(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            completed, gate_path, gate = self.run_gate(output_root, check=False)

            self.assertEqual(completed.returncode, 2)
            self.assertIn("accepted baseline", completed.stderr)
            self.assertIn("ai_native_benchmark_promote.py", completed.stderr)
            self.assertFalse(gate_path.exists())
            self.assertIsNone(gate)

    def test_gate_refuses_unpromoted_accepted_baseline_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            accepted_dir = output_root / "local-mac" / "accepted"
            accepted_dir.mkdir(parents=True)
            (accepted_dir / "accepted-baseline-manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "hardware_class": "local-mac",
                        "run_context": {
                            "mode": "sample-synthetic",
                            "requires_private_world": False,
                            "requires_private_assets": False,
                            "requires_live_pi": False,
                        },
                        "reports": {
                            "mutation": "mutation-benchmark-report.json",
                            "demo_entity": "generic-demo-entity-benchmark-report.json",
                        },
                    }
                ),
                encoding="utf-8",
            )

            completed, gate_path, gate = self.run_gate(output_root, check=False)

            self.assertEqual(completed.returncode, 2)
            self.assertIn("accepted-local-baseline", completed.stderr)
            self.assertIn("ai_native_benchmark_promote.py", completed.stderr)
            self.assertFalse(gate_path.exists())
            self.assertIsNone(gate)

    def test_docs_explain_gate_loop_and_backup_boundary(self):
        body = DOC.read_text(encoding="utf-8")
        for phrase in (
            "util/ai_native_benchmark_gate.py",
            "benchmark-gate-manifest.json",
            "promotion -> branch gate loop",
            "local/benchmarks/<hardware-class>/accepted/",
            "exit nonzero",
            "no live server",
            "backup-first",
        ):
            self.assertIn(phrase, body)
        self.assertNotRegex(body, PRIVATE_PATTERNS)


if __name__ == "__main__":
    unittest.main()
