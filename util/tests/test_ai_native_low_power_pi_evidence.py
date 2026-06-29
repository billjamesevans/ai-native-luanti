import importlib.util
import json
import pathlib
import re
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
CLI = ROOT / "util" / "ai_native_low_power_pi_evidence.py"
README = ROOT / "doc" / "ai-native-runtime" / "README.md"
ALPHA_GATE = ROOT / "doc" / "ai-native-runtime" / "alpha-release-gate.md"

PRIVATE_PATTERNS = re.compile(
    r"minecraftpi|192\.168|/opt/ai-native-luanti|/Users/|"
    r"spacebase|themepark|showcase100|disneyland100|"
    r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY|private_prompt|asset_payload",
    re.I,
)


def load_module():
    assert CLI.is_file(), f"missing {CLI}"
    spec = importlib.util.spec_from_file_location("ai_native_low_power_pi_evidence", CLI)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeRunner:
    def __init__(self, module, *, service_output=None, remote_manifest=None, verify_returncode=0):
        self.module = module
        self.calls = []
        self.remote_manifest = remote_manifest or self.default_remote_manifest()
        self.service_output = service_output or self.default_service_output()
        self.verify_returncode = verify_returncode

    def default_remote_manifest(self):
        return {
            "schema_version": 1,
            "overall_status": "pass",
            "hardware_class": "low-power-server",
            "game_profile": "ai_runtime",
            "luanti_commit": "26eb426dc",
            "logical_run_dir": "local/benchmarks/low-power-server/2026-06-29/26eb426dc",
            "artifact_paths": {
                "verification_manifest": (
                    "local/benchmarks/low-power-server/2026-06-29/26eb426dc/"
                    "ai-runtime-verification-manifest.json"
                ),
                "clean_profile_summary": (
                    "local/benchmarks/low-power-server/2026-06-29/26eb426dc/"
                    "clean-profile-benchmark-summary.json"
                ),
            },
            "product_profile_evidence": {
                "status": "pass",
                "game_profile": "ai_runtime",
                "no_private_content": True,
                "dev_surfaces_disabled_by_default": True,
                "test_fixtures_explicit_only": True,
                "runtime_surfaces_available": True,
                "failure_count": 0,
            },
            "clean_profile_evidence": {
                "overall_status": "pass",
                "gameid": "ai_runtime",
                "requires_private_world": False,
                "requires_private_assets": False,
                "player_load_probe_status": "pass",
                "player_load_probe_kind": "server_process_liveness",
                "server_step_workload": {
                    "status": "pass",
                    "kind": "synthetic_server_step_samples",
                    "attempted_sample_count": 4,
                    "completed_sample_count": 4,
                    "failed_sample_count": 0,
                },
            },
            "failure_reasons": [],
        }

    def default_service_output(self):
        return "\n".join(
            [
                "family_service_active=active",
                "fork_service_active=active",
                "family_udp_listening=true",
                "fork_udp_listening=true",
                "fork_version=Luanti 5.17.0-dev-26eb426dc (Linux)",
                "fork_commit=26eb426dc",
                "raw_private_path=/opt/ai-native-luanti/src/bin/luantiserver",
                "raw_private_target=minecraftpi.home 192.168.230.60",
            ]
        )

    def __call__(self, command, *, timeout=None):
        self.calls.append(command)
        command_text = " ".join(command)
        if "ai_native_runtime_verify.py" in command_text:
            return self.module.CommandRun(
                returncode=self.verify_returncode,
                stdout="local/benchmarks/low-power-server/run/"
                "ai-runtime-verification-manifest.json\n",
            )
        if "cat " in command_text:
            if "cd /opt/ai-native-luanti/src" not in command_text:
                return self.module.CommandRun(returncode=1, stderr="missing remote repo cwd")
            return self.module.CommandRun(
                returncode=0,
                stdout=json.dumps(self.remote_manifest),
            )
        return self.module.CommandRun(returncode=0, stdout=self.service_output)


class LowPowerPiEvidenceTests(unittest.TestCase):
    def test_collects_public_safe_low_power_manifest_from_remote_verifier_and_services(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            args = module.parse_args(
                [
                    "--ssh-target",
                    "bill@minecraftpi.home",
                    "--output-root",
                    tmpdir,
                    "--date",
                    "2026-06-29",
                    "--confirm-backup-first",
                    "--backup-artifact-label",
                    "raspberrypi_luanti_20260629-044624.tgz",
                    "--backup-sha256",
                    "73b521f2ee21274f37f1a5a6ab1840a1b9b3e2d39430461af5831a13210e7628",
                ]
            )
            fake_runner = FakeRunner(module)

            exit_code, output_path, manifest = module.run(args, runner=fake_runner, now_fn=lambda: "2026-06-29T10:00:00Z")

        self.assertEqual(exit_code, 0)
        self.assertTrue(output_path.name.endswith("pi-low-power-evidence.json"))
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["evidence_kind"], "ai_native_low_power_pi_evidence")
        self.assertEqual(manifest["overall_status"], "pass")
        self.assertEqual(manifest["hardware_class"], "low-power-server")
        self.assertEqual(manifest["game_profile"], "ai_runtime")
        self.assertEqual(manifest["luanti_commit"], "26eb426dc")
        self.assertEqual(manifest["service_boundary"]["family_service"]["port"], 30000)
        self.assertEqual(manifest["service_boundary"]["fork_test_service"]["port"], 30001)
        self.assertTrue(manifest["service_boundary"]["family_service"]["active"])
        self.assertTrue(manifest["service_boundary"]["fork_test_service"]["active"])
        self.assertTrue(manifest["service_boundary"]["family_service"]["udp_listening"])
        self.assertTrue(manifest["service_boundary"]["fork_test_service"]["udp_listening"])
        self.assertTrue(manifest["backup_evidence"]["backup_first_confirmed"])
        self.assertTrue(manifest["runtime_verification_evidence"]["clean_profile_status"] == "pass")
        self.assertEqual(
            manifest["runtime_verification_evidence"]["player_load_probe_status"],
            "pass",
        )
        self.assertEqual(
            manifest["runtime_verification_evidence"]["server_step_workload_status"],
            "pass",
        )
        self.assertEqual(manifest["failure_reasons"], [])
        self.assertNotRegex(json.dumps(manifest, sort_keys=True), PRIVATE_PATTERNS)

    def test_accepts_flattened_clean_profile_status_from_runtime_verifier(self):
        module = load_module()
        remote_manifest = FakeRunner(module).default_remote_manifest()
        remote_manifest["clean_profile_evidence"] = {
            "overall_status": "pass",
            "server_step_workload_status": "pass",
            "player_load_probe_status": "pass",
            "player_load_probe_kind": "server_process_liveness",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            args = module.parse_args(
                [
                    "--ssh-target",
                    "bill@minecraftpi.home",
                    "--output-root",
                    tmpdir,
                    "--date",
                    "2026-06-29",
                    "--confirm-backup-first",
                    "--backup-sha256",
                    "73b521f2ee21274f37f1a5a6ab1840a1b9b3e2d39430461af5831a13210e7628",
                ]
            )
            fake_runner = FakeRunner(module, remote_manifest=remote_manifest)

            exit_code, _, manifest = module.run(args, runner=fake_runner, now_fn=lambda: "2026-06-29T10:00:00Z")

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            manifest["runtime_verification_evidence"]["server_step_workload_status"],
            "pass",
        )

    def test_manifest_fails_when_backup_confirmation_or_side_by_side_service_is_missing(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            args = module.parse_args(
                [
                    "--ssh-target",
                    "bill@minecraftpi.home",
                    "--output-root",
                    tmpdir,
                    "--date",
                    "2026-06-29",
                ]
            )
            service_output = "\n".join(
                [
                    "family_service_active=active",
                    "fork_service_active=inactive",
                    "family_udp_listening=true",
                    "fork_udp_listening=false",
                    "fork_version=Luanti 5.17.0-dev-26eb426dc (Linux)",
                    "fork_commit=26eb426dc",
                ]
            )
            fake_runner = FakeRunner(module, service_output=service_output)

            exit_code, _, manifest = module.run(args, runner=fake_runner, now_fn=lambda: "2026-06-29T10:00:00Z")

        self.assertEqual(exit_code, 2)
        self.assertEqual(manifest["overall_status"], "fail")
        self.assertIn("backup_first_confirmation_missing", manifest["failure_reasons"])
        self.assertIn("fork_test_service_not_active", manifest["failure_reasons"])
        self.assertIn("fork_test_udp_port_not_listening", manifest["failure_reasons"])
        self.assertNotRegex(json.dumps(manifest, sort_keys=True), PRIVATE_PATTERNS)

    def test_reads_remote_manifest_even_when_remote_verifier_exits_nonzero(self):
        module = load_module()
        remote_manifest = FakeRunner(module).default_remote_manifest()
        remote_manifest["overall_status"] = "fail"
        remote_manifest["artifact_paths"]["benchmark_gate_manifest"] = (
            "local/benchmarks/low-power-server/2026-06-29/26eb426dc/benchmark-gate-manifest.json"
        )
        remote_manifest["failure_reasons"] = ["branch_benchmark_gate exited with status 1"]

        with tempfile.TemporaryDirectory() as tmpdir:
            args = module.parse_args(
                [
                    "--ssh-target",
                    "bill@minecraftpi.home",
                    "--output-root",
                    tmpdir,
                    "--date",
                    "2026-06-29",
                    "--confirm-backup-first",
                    "--backup-sha256",
                    "73b521f2ee21274f37f1a5a6ab1840a1b9b3e2d39430461af5831a13210e7628",
                ]
            )
            fake_runner = FakeRunner(module, remote_manifest=remote_manifest, verify_returncode=1)

            exit_code, _, manifest = module.run(args, runner=fake_runner, now_fn=lambda: "2026-06-29T10:00:00Z")

        self.assertEqual(exit_code, 2)
        self.assertEqual(manifest["overall_status"], "fail")
        self.assertIn("remote_low_power_verifier_not_pass", manifest["failure_reasons"])
        self.assertIn("remote_low_power_verifier_command_failed", manifest["failure_reasons"])
        self.assertNotIn("product_profile_hygiene_not_pass", manifest["failure_reasons"])
        self.assertNotIn("clean_profile_evidence_not_pass", manifest["failure_reasons"])
        self.assertIn(
            "benchmark_gate_manifest",
            manifest["runtime_verification_evidence"]["artifact_paths"],
        )
        self.assertTrue(manifest["runtime_verification_evidence"]["product_profile_no_private_content"])
        self.assertNotRegex(json.dumps(manifest, sort_keys=True), PRIVATE_PATTERNS)

    def test_cli_and_docs_expose_low_power_pi_lane(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_runner = FakeRunner(module)
            exit_code = module.main(
                [
                    "--ssh-target",
                    "bill@minecraftpi.home",
                    "--output-root",
                    tmpdir,
                    "--date",
                    "2026-06-29",
                    "--confirm-backup-first",
                    "--backup-sha256",
                    "73b521f2ee21274f37f1a5a6ab1840a1b9b3e2d39430461af5831a13210e7628",
                ],
                runner=fake_runner,
                now_fn=lambda: "2026-06-29T10:00:00Z",
            )

        self.assertEqual(exit_code, 0)
        readme = README.read_text(encoding="utf-8")
        alpha_gate = ALPHA_GATE.read_text(encoding="utf-8")
        self.assertIn("ai_native_low_power_pi_evidence.py", readme)
        self.assertIn("ai_native_low_power_pi_evidence.py", alpha_gate)
        self.assertIn("--confirm-backup-first", alpha_gate)

    def test_reads_relative_remote_manifest_path_from_remote_repo(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            args = module.parse_args(
                [
                    "--ssh-target",
                    "bill@minecraftpi.home",
                    "--output-root",
                    tmpdir,
                    "--date",
                    "2026-06-29",
                    "--confirm-backup-first",
                    "--backup-sha256",
                    "73b521f2ee21274f37f1a5a6ab1840a1b9b3e2d39430461af5831a13210e7628",
                ]
            )
            fake_runner = FakeRunner(module)

            exit_code, _, manifest = module.run(args, runner=fake_runner, now_fn=lambda: "2026-06-29T10:00:00Z")

        cat_commands = [
            " ".join(command)
            for command in fake_runner.calls
            if "cat local/benchmarks/low-power-server/run/ai-runtime-verification-manifest.json" in " ".join(command)
        ]
        self.assertTrue(cat_commands)
        self.assertIn("cd /opt/ai-native-luanti/src", cat_commands[0])
        self.assertEqual(exit_code, 0)
        self.assertEqual(manifest["overall_status"], "pass")


if __name__ == "__main__":
    unittest.main()
