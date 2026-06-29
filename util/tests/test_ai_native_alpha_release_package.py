import importlib.util
import json
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
CLI = ROOT / "util" / "ai_native_alpha_release_gate.py"
README = ROOT / "doc" / "ai-native-runtime" / "README.md"
PR_TEMPLATE = ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md"


def load_gate_module():
    assert CLI.is_file(), f"missing {CLI}"
    spec = importlib.util.spec_from_file_location("ai_native_alpha_release_gate", CLI)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AIAlphaReleasePackageTests(unittest.TestCase):
    def test_alpha_package_docs_and_templates_exist(self):
        expected_paths = [
            "doc/ai-native-runtime/alpha-release-gate.md",
            "doc/ai-native-runtime/clean-ai-runtime-install.md",
            "doc/ai-native-runtime/public-safe-sample-data-policy.md",
            "doc/ai-native-runtime/release-notes-template.md",
            ".github/ISSUE_TEMPLATE/ai_runtime.yml",
            ".github/ISSUE_TEMPLATE/agent_plugin.yml",
            ".github/ISSUE_TEMPLATE/benchmark.yml",
            ".github/ISSUE_TEMPLATE/compat_import.yml",
            "util/ai_native_alpha_release_gate.py",
        ]

        missing = [path for path in expected_paths if not (ROOT / path).is_file()]

        self.assertEqual(missing, [])

    def test_alpha_gate_reports_public_release_package_ready(self):
        gate = load_gate_module()

        report = gate.build_report(ROOT)

        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["alpha_package"]["one_command_local_verifier"], [
            "python3",
            "util/ai_native_runtime_verify.py",
            "--hardware-class",
            "local-mac",
            "--game-profile",
            "ai_runtime",
        ])
        self.assertEqual(report["violations"], [])
        self.assertTrue(report["safety"]["public_sample_data_only"])
        self.assertTrue(report["safety"]["family_content_excluded"])
        self.assertTrue(report["safety"]["pi_side_by_side_only"])
        self.assertTrue(report["safety"]["release_notes_separate_engine_plugins_family_content"])
        self.assertEqual(
            {
                template["kind"]: template["status"]
                for template in report["issue_templates"]
            },
            {
                "runtime": "present",
                "agent": "present",
                "benchmark": "present",
                "compat_import": "present",
            },
        )

    def test_readme_and_pr_template_expose_alpha_gate(self):
        readme = README.read_text(encoding="utf-8")
        pr_template = PR_TEMPLATE.read_text(encoding="utf-8")

        for link in [
            "alpha-release-gate.md",
            "clean-ai-runtime-install.md",
            "public-safe-sample-data-policy.md",
            "release-notes-template.md",
        ]:
            self.assertIn(link, readme)

        self.assertIn("python3 util/ai_native_alpha_release_gate.py", readme)
        self.assertIn("python3 util/ai_native_runtime_verify.py --hardware-class local-mac --game-profile ai_runtime", pr_template)
        self.assertIn("spacebase", pr_template)
        self.assertIn("themepark", pr_template)
        self.assertIn("disneyland100", pr_template)
        self.assertIn("family-server content", pr_template)

    def test_cli_writes_machine_readable_report(self):
        gate = load_gate_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            output = pathlib.Path(tmpdir) / "alpha-release-gate.json"

            exit_code = gate.main(["--root", str(ROOT), "--output", str(output)])

            self.assertEqual(exit_code, 0)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "pass")
            self.assertTrue(report["safety"]["public_sample_data_only"])


if __name__ == "__main__":
    unittest.main()
