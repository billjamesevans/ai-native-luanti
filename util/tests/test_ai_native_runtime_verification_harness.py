import importlib.util
import json
import pathlib
import re
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
CLI = ROOT / "util" / "ai_native_runtime_verify.py"
DOC = ROOT / "doc" / "ai-native-runtime" / "synthetic-runtime-smoke.md"
README = ROOT / "doc" / "ai-native-runtime" / "README.md"

PRIVATE_PATTERNS = re.compile(
    r"minecraftpi|192\.168|spacebase|themepark|showcase100|disneyland100|"
    r"sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY|private_prompt|asset_payload|/Users/",
    re.I,
)


def load_harness_module():
    assert CLI.is_file(), f"missing {CLI}"
    spec = importlib.util.spec_from_file_location("ai_native_runtime_verify", CLI)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AIRuntimeVerificationHarnessTests(unittest.TestCase):
    def test_success_manifest_is_bounded_private_safe_and_records_artifacts(self):
        harness = load_harness_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            args = harness.parse_args(
                [
                    "--output-root",
                    str(output_root),
                    "--hardware-class",
                    "local-mac",
                    "--date",
                    "2026-06-28",
                    "--luanti-commit",
                    "verify-success",
                    "--server-bin",
                    "bin/luantiserver",
                ]
            )
            runs = iter(
                [
                    harness.CommandRun(0, 0.10, "utility tests ok", ""),
                    harness.CommandRun(
                        0,
                        0.20,
                        "local/benchmarks/local-mac/2026-06-28/verify-success/benchmark-gate-manifest.json\n",
                        "",
                    ),
                    harness.CommandRun(0, 0.30, "TestAIRuntime passed", ""),
                ]
            )

            status, manifest_path, manifest = harness.run_harness(
                args,
                runner=lambda _step: next(runs),
                now_fn=lambda: "2026-06-28T12:00:00Z",
            )

            self.assertEqual(status, 0)
            self.assertTrue(manifest_path.is_file())
            self.assertEqual(manifest["schema_version"], 1)
            self.assertEqual(manifest["overall_status"], "pass")
            self.assertEqual(manifest["hardware_class"], "local-mac")
            self.assertEqual(manifest["luanti_commit"], "verify-success")
            self.assertEqual(manifest["game_profile"], "sample-synthetic")
            self.assertEqual(
                manifest["logical_run_dir"],
                "local/benchmarks/local-mac/2026-06-28/verify-success",
            )
            self.assertEqual(
                [step["id"] for step in manifest["steps"]],
                [
                    "utility_contract_tests",
                    "branch_benchmark_gate",
                    "ai_runtime_focused_tests",
                ],
            )
            self.assertEqual(manifest["failure_reasons"], [])
            self.assertEqual(
                manifest["artifact_paths"]["benchmark_gate_manifest"],
                "local/benchmarks/local-mac/2026-06-28/verify-success/benchmark-gate-manifest.json",
            )
            self.assertNotIn("clean_profile_summary", manifest["artifact_paths"])
            self.assertFalse(manifest["run_context"]["requires_private_world"])
            self.assertFalse(manifest["run_context"]["requires_private_assets"])
            self.assertFalse(manifest["run_context"]["requires_live_pi"])
            self.assertFalse(manifest["run_context"]["requires_model_network"])

            serialized = json.dumps(manifest, sort_keys=True)
            self.assertLess(len(serialized), 12000)
            self.assertNotIn(str(output_root), serialized)
            self.assertNotRegex(serialized, PRIVATE_PATTERNS)

    def test_clean_profile_mode_records_profile_artifact_without_losing_gate_manifest(self):
        harness = load_harness_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            args = harness.parse_args(
                [
                    "--output-root",
                    str(output_root),
                    "--hardware-class",
                    "local-mac",
                    "--date",
                    "2026-06-28",
                    "--luanti-commit",
                    "verify-clean-profile",
                    "--server-bin",
                    "bin/luantiserver",
                    "--game-profile",
                    "ai_runtime",
                ]
            )
            steps = harness.build_steps(args)
            gate_step = steps[1]
            self.assertIn("--game-profile", gate_step.actual_command)
            self.assertIn("ai_runtime", gate_step.actual_command)
            self.assertIn("--server-bin", gate_step.actual_command)
            self.assertIn("bin/luantiserver", gate_step.manifest_command)

            runs = iter(
                [
                    harness.CommandRun(0, 0.10, "utility tests ok", ""),
                    harness.CommandRun(
                        0,
                        0.20,
                        "local/benchmarks/local-mac/2026-06-28/verify-clean-profile/benchmark-gate-manifest.json\n",
                        "",
                    ),
                    harness.CommandRun(0, 0.30, "TestAIRuntime passed", ""),
                ]
            )

            status, _, manifest = harness.run_harness(
                args,
                runner=lambda _step: next(runs),
                now_fn=lambda: "2026-06-28T12:02:00Z",
            )

            self.assertEqual(status, 0)
            self.assertEqual(manifest["game_profile"], "ai_runtime")
            self.assertEqual(
                manifest["artifact_paths"]["benchmark_gate_manifest"],
                "local/benchmarks/local-mac/2026-06-28/verify-clean-profile/benchmark-gate-manifest.json",
            )
            self.assertEqual(
                manifest["artifact_paths"]["clean_profile_summary"],
                "local/benchmarks/local-mac/2026-06-28/verify-clean-profile/clean-profile-benchmark-summary.json",
            )
            self.assertIn("clean-profile verification", " ".join(manifest["notes"]))

            serialized = json.dumps(manifest, sort_keys=True)
            self.assertNotIn(str(output_root), serialized)
            self.assertNotRegex(serialized, PRIVATE_PATTERNS)

    def test_failed_command_writes_manifest_with_sanitized_failure_reason(self):
        harness = load_harness_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            args = harness.parse_args(
                [
                    "--output-root",
                    str(output_root),
                    "--hardware-class",
                    "local-mac",
                    "--date",
                    "2026-06-28",
                    "--luanti-commit",
                    "verify-failure",
                    "--server-bin",
                    "bin/luantiserver",
                ]
            )
            runs = iter(
                [
                    harness.CommandRun(0, 0.10, "utility tests ok", ""),
                    harness.CommandRun(
                        1,
                        0.20,
                        "",
                        "benchmark failed near /Users/billevans/private and minecraftpi.home",
                    ),
                    harness.CommandRun(0, 0.30, "TestAIRuntime passed", ""),
                ]
            )

            status, manifest_path, manifest = harness.run_harness(
                args,
                runner=lambda _step: next(runs),
                now_fn=lambda: "2026-06-28T12:01:00Z",
            )

            self.assertEqual(status, 1)
            self.assertTrue(manifest_path.is_file())
            self.assertEqual(manifest["overall_status"], "fail")
            self.assertEqual(manifest["steps"][1]["id"], "branch_benchmark_gate")
            self.assertEqual(manifest["steps"][1]["status"], "fail")
            self.assertEqual(manifest["steps"][1]["returncode"], 1)
            self.assertTrue(
                any(
                    "branch_benchmark_gate exited with status 1" in reason
                    for reason in manifest["failure_reasons"]
                )
            )

            serialized = json.dumps(manifest, sort_keys=True)
            self.assertNotRegex(serialized, PRIVATE_PATTERNS)

    def test_docs_place_one_command_harness_after_gate_and_smoke_workflow(self):
        body = DOC.read_text(encoding="utf-8")
        readme = README.read_text(encoding="utf-8")
        for phrase in (
            "util/ai_native_runtime_verify.py",
            "ai-runtime-verification-manifest.json",
            "after the branch benchmark gate and `/ai_runtime_smoke`",
            "--game-profile ai_runtime",
            "clean-profile-benchmark-summary.json",
            "local/benchmarks/<hardware-class>/<date>/<commit>/",
            "no live server",
            "no model-network",
            "pre-PR",
        ):
            self.assertIn(phrase, body)
        self.assertIn("util/ai_native_runtime_verify.py", readme)
        self.assertNotRegex(body, PRIVATE_PATTERNS)


if __name__ == "__main__":
    unittest.main()
