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
            "doc/ai-native-runtime/operator-alpha-release-runbook.md",
            "doc/ai-native-runtime/clean-ai-runtime-install.md",
            "doc/ai-native-runtime/public-safe-sample-data-policy.md",
            "doc/ai-native-runtime/release-notes-template.md",
            "doc/ai-native-runtime/project-operating-loop.md",
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
        self.assertTrue(report["safety"]["clean_profile_package_verified"])
        operating_loop = report["project_operating_loop"]
        self.assertEqual(
            [item["issue"] for item in operating_loop["ranked_next_issue_queue"]],
            ["#253", "#254", "#255", "#256", "#257"],
        )
        self.assertEqual(
            operating_loop["public_boundary"]["excluded_content"],
            ["spacebase", "themepark", "disneyland100"],
        )
        self.assertEqual(
            operating_loop["public_boundary"]["fork_lane"],
            "side-by-side ai_runtime alpha lane",
        )
        cadence_names = [entry["name"] for entry in operating_loop["cadence"]]
        self.assertEqual(
            cadence_names,
            ["pre_pr_local_gate", "benchmark_review", "pi_promotion"],
        )
        checklist = report["release_candidate_checklist"]
        self.assertEqual(
            checklist["candidate_id_source"]["command"],
            ["git", "rev-parse", "--short", "HEAD"],
        )
        phase_names = [phase["name"] for phase in checklist["phases"]]
        self.assertEqual(
            phase_names,
            [
                "clean_checkout_package",
                "local_runtime_evidence",
                "compatibility_and_parity_review",
                "pi_side_by_side_promotion",
                "release_closeout",
            ],
        )
        pi_phase = next(
            phase for phase in checklist["phases"]
            if phase["name"] == "pi_side_by_side_promotion"
        )
        self.assertEqual(
            pi_phase["deploy_boundary"],
            {
                "family_service": "luanti-family.service",
                "family_port": "30000/udp",
                "fork_service": "ai-native-luanti-test.service",
                "fork_port": "30001/udp",
                "mode": "side_by_side_test_service_only",
            },
        )
        self.assertIn(
            "spacebase",
            checklist["public_boundary"]["excluded_content"],
        )
        self.assertIn(
            "copied proprietary assets",
            checklist["public_boundary"]["private_artifacts_not_committed"],
        )
        self.assertEqual(report["clean_profile_package"]["status"], "pass")
        self.assertEqual(report["clean_profile_package"]["profile"]["gameid"], "ai_runtime")
        self.assertTrue(
            report["clean_profile_package"]["safety"]["startup_inventory_matches_default_runtime"]
        )
        self.assertTrue(report["clean_profile_package"]["safety"]["profile_code_fixture_free"])
        command_plan = {
            step["step"]: step["command"]
            for step in report["alpha_package"]["fresh_checkout_command_plan"]
        }
        self.assertEqual(
            command_plan["configure_server_release"][:5],
            ["cmake", "-S", ".", "-B", "build/server-release"],
        )
        self.assertEqual(
            command_plan["smoke_test_runtime"],
            ["bin/luantiserver", "--run-unittests", "--test-module", "TestAIRuntime"],
        )
        self.assertEqual(
            command_plan["run_one_command_verifier"],
            report["alpha_package"]["one_command_local_verifier"],
        )
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
            "operator-alpha-release-runbook.md",
            "clean-ai-runtime-install.md",
            "public-safe-sample-data-policy.md",
            "release-notes-template.md",
            "project-operating-loop.md",
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
            self.assertTrue(report["safety"]["clean_profile_package_verified"])
            self.assertIn("release_candidate_checklist", report)


if __name__ == "__main__":
    unittest.main()
