import json
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
CLI = ROOT / "util" / "ai_native_benchmark_capture.py"
DOC = ROOT / "doc" / "ai-native-runtime" / "benchmark-baseline-retention.md"

PRIVATE_PATTERNS = re.compile(
    r"minecraftpi|192\.168|spacebase|themepark|showcase100|disneyland100|"
    r"sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY|private_prompt|asset_payload",
    re.I,
)


class BenchmarkCaptureRunnerTests(unittest.TestCase):
    def run_capture(self, *extra_args, output_root, check=True):
        self.assertTrue(CLI.is_file(), f"missing {CLI}")
        output = pathlib.Path(output_root)
        completed = subprocess.run(
            [
                sys.executable,
                str(CLI),
                "--output-root",
                str(output),
                "--hardware-class",
                "local-mac",
                "--date",
                "2026-06-27",
                "--luanti-commit",
                "test-commit",
                *extra_args,
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if check:
            self.assertEqual(completed.returncode, 0, completed.stderr)
        run_dir = output / "local-mac" / "2026-06-27" / "test-commit"
        manifest_path = run_dir / "benchmark-capture-manifest.json"
        manifest = None
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return completed, output, run_dir, manifest

    def test_runner_writes_local_reports_and_private_safe_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            _, output, run_dir, manifest = self.run_capture(output_root=output_root)

            self.assertIsNotNone(manifest)
            self.assertEqual(manifest["schema_version"], 1)
            self.assertEqual(manifest["hardware_class"], "local-mac")
            self.assertEqual(manifest["luanti_commit"], "test-commit")
            self.assertEqual(
                manifest["logical_run_dir"],
                "local/benchmarks/local-mac/2026-06-27/test-commit",
            )
            self.assertFalse(manifest["run_context"]["requires_private_world"])
            self.assertFalse(manifest["run_context"]["requires_private_assets"])
            self.assertFalse(manifest["run_context"]["requires_live_pi"])

            mutation_report = run_dir / manifest["reports"]["mutation"]
            demo_report = run_dir / manifest["reports"]["demo_entity"]
            self.assertTrue(mutation_report.is_file())
            self.assertTrue(demo_report.is_file())
            self.assertEqual(output.name, "benchmarks")

            serialized = json.dumps(manifest, sort_keys=True)
            self.assertNotIn(str(output), serialized)
            self.assertNotRegex(serialized, PRIVATE_PATTERNS)

    def test_runner_writes_comparisons_when_baselines_are_supplied(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            _, _, baseline_dir, baseline_manifest = self.run_capture(output_root=output_root)
            self.assertIsNotNone(baseline_manifest)
            mutation_baseline = baseline_dir / baseline_manifest["reports"]["mutation"]
            demo_baseline = baseline_dir / baseline_manifest["reports"]["demo_entity"]

            completed, _, run_dir, manifest = self.run_capture(
                "--mutation-baseline",
                str(mutation_baseline),
                "--demo-entity-baseline",
                str(demo_baseline),
                output_root=output_root,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIsNotNone(manifest)
            self.assertIn("mutation", manifest["comparisons"])
            self.assertIn("demo_entity", manifest["comparisons"])
            mutation_comparison = run_dir / manifest["comparisons"]["mutation"]
            demo_comparison = run_dir / manifest["comparisons"]["demo_entity"]
            self.assertTrue(mutation_comparison.is_file())
            self.assertTrue(demo_comparison.is_file())
            self.assertEqual(
                json.loads(mutation_comparison.read_text(encoding="utf-8"))["overall_status"],
                "pass",
            )
            self.assertEqual(
                json.loads(demo_comparison.read_text(encoding="utf-8"))["overall_status"],
                "pass",
            )

    def test_low_power_server_requires_backup_confirmation(self):
        self.assertTrue(CLI.is_file(), f"missing {CLI}")
        with tempfile.TemporaryDirectory() as tmpdir:
            output = pathlib.Path(tmpdir) / "local" / "benchmarks"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    "--output-root",
                    str(output),
                    "--hardware-class",
                    "low-power-server",
                    "--date",
                    "2026-06-27",
                    "--luanti-commit",
                    "test-commit",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("backup-first", completed.stderr)

    def test_docs_and_gitignore_cover_capture_workflow(self):
        body = DOC.read_text(encoding="utf-8")
        for phrase in (
            "util/ai_native_benchmark_capture.py",
            "local/benchmarks/<hardware-class>/<date>/<commit>/",
            "mutation-benchmark-report.json",
            "generic-demo-entity-benchmark-report.json",
            "benchmark-capture-manifest.json",
            "same-hardware baseline",
            "backup-first",
            "no live server",
        ):
            self.assertIn(phrase, body)
        self.assertNotRegex(body, PRIVATE_PATTERNS)

        ignored = subprocess.run(
            [
                "git",
                "check-ignore",
                "-q",
                "local/benchmarks/local-mac/2026-06-27/test-commit/report.json",
            ],
            cwd=ROOT,
            check=False,
        )
        self.assertEqual(ignored.returncode, 0)


if __name__ == "__main__":
    unittest.main()
