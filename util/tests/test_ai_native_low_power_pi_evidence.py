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
                "player_load_probe_kind": "headless_client_load",
                "headless_player_supported": True,
                "attempted_synthetic_player_count": 2,
                "connected_synthetic_player_count": 2,
                "completed_synthetic_player_count": 2,
                "latency_proxy_supported": True,
                "latency_probe_kind": "headless_join_log_observation",
                "join_latency_proxy_sample_count": 2,
                "scale_gate_status": "pass",
                "scale_gate_required_synthetic_player_count": 2,
                "scale_gate_required_concurrent_task_count": 2,
                "server_step_workload": {
                    "status": "pass",
                    "kind": "synthetic_server_step_samples",
                    "attempted_sample_count": 4,
                    "completed_sample_count": 4,
                    "failed_sample_count": 0,
                },
                "server_step_attempted_samples": 4,
                "server_step_completed_samples": 4,
                "server_step_failed_samples": 0,
                "actionable_warning_count": 0,
                "server_log_error_count": 0,
                "cpu_status": "measured",
                "cpu_sample_count": 3,
                "avg_process_cpu_percent": 14.5,
                "max_interval_cpu_percent": 42.0,
                "rss_sample_count": 3,
                "max_rss_kb": 196608,
            },
            "compat_import_staging_pilot_evidence": {
                "compat_import_staging_pilot_status": "pass",
                "compat_import_inventory_ready": True,
                "compat_import_node_writes": 4,
                "compat_import_mapblock_churn": 1,
                "compat_import_refusal_gates": [
                    "max_node_writes_total",
                    "max_mapblock_churn_total",
                ],
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
                "fork_restart_count=0",
                "fork_active_enter_timestamp=Mon 2026-06-29 10:00:00 UTC",
                "raw_private_path=/opt/ai-native-luanti/src/bin/luantiserver",
                "raw_private_target=minecraftpi.home 192.168.230.60",
            ] + self.default_studio_status_lines()
        )

    def default_studio_status_lines(self):
        return [
            "studio_status_present=true",
            "studio_status_health=available",
            "studio_schema_version=1",
            "studio_public_safe=true",
            "studio_live_bridge=true",
            "studio_direct_world_mutation_by_ai=false",
            "studio_services_all_active=true",
            "studio_quality_gate_status=pass",
            "studio_quality_gate_attention_total=0",
            "studio_quality_gate_violations_total=0",
            "studio_quality_gate_live_prompt_eval_status=pass",
            "studio_quality_gate_live_review_gate_health=pass",
            "studio_live_review_gate_status=pass",
            "studio_live_review_gate_health=pass",
            "studio_live_review_gate_source_trace_id=nova_trace:11",
            "studio_live_review_gate_selected_option_id=fire",
            "studio_live_review_gate_checks_passed=3",
            "studio_live_review_gate_checks_total=3",
            "studio_live_review_gate_violations_total=0",
            "studio_live_review_gate_public_safe_output=true",
            "studio_live_review_gate_unsafe_payload_rejected=false",
            "studio_live_review_gate_no_world_mutation=true",
            "studio_live_review_gate_no_raw_assets=true",
            "studio_live_review_gate_no_provider_prompts=true",
            "studio_live_review_gate_no_family_world_coordinates=true",
            "studio_prompt_eval_health=pass",
            "studio_prompt_eval_status=pass",
            "studio_prompt_eval_cases_total=12",
            "studio_prompt_eval_cases_passed=12",
            "studio_prompt_eval_cases_failed=0",
            "studio_prompt_eval_golden_prompts_total=9",
            "studio_prompt_eval_golden_prompts_passed=9",
            "studio_prompt_eval_golden_prompts_failed=0",
            "studio_prompt_eval_agentic_tool_cases=10",
            "studio_prompt_eval_agentic_tool_cases_required=10",
            "studio_adapter_present=true",
            "studio_adapter_release_health=pass",
            "studio_adapter_current_health=attention",
            "studio_adapter_recent_window_health=attention",
            "studio_adapter_history_health=attention",
            "studio_adapter_latest_ok=true",
            "studio_adapter_recent_window_entries=50",
            "studio_adapter_recent_successes=49",
            "studio_adapter_recent_failures=1",
            "studio_adapter_recent_timeouts=0",
            "studio_adapter_failures=29",
            "studio_adapter_timeouts=35",
            "studio_adapter_latest_source_trace_id=nova_trace:9",
            "studio_adapter_latest_selected_option_id=generated_openrealm_lakeside_village",
            "studio_adapter_latest_tool_count=9",
            "studio_adapter_latest_planned_node_writes=96",
            "studio_adapter_latest_web_search_available=true",
            "studio_adapter_latest_agentic_execution=true",
            "studio_adapter_latest_required_tool_calls_satisfied=true",
            "studio_adapter_latest_world_mutation_authority=luanti",
            "studio_adapter_latest_direct_world_mutation=false",
            "studio_runtime_proofs_health=pass",
            "studio_runtime_proofs_nova_status=pass",
            "studio_runtime_proofs_nova_cases_total=3",
            "studio_runtime_proofs_nova_cases_passed=3",
            "studio_runtime_proofs_nova_cases_failed=0",
            "studio_runtime_proofs_compat_status=pass",
            "studio_runtime_proofs_compat_refusal_gates_passed=4",
            "studio_runtime_proofs_compat_refusal_gates_total=4",
        ]

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
    def test_named_soak_targets_default_to_recommended_cadence(self):
        module = load_module()

        quick = module.parse_args(["--ssh-target", "bill@minecraftpi.home"])
        one_hour = module.parse_args([
            "--ssh-target",
            "bill@minecraftpi.home",
            "--soak-target",
            "one-hour",
        ])
        overnight = module.parse_args([
            "--ssh-target",
            "bill@minecraftpi.home",
            "--soak-target",
            "overnight",
        ])

        self.assertEqual((quick.soak_iterations, quick.soak_interval_seconds), (1, 0.0))
        self.assertEqual((one_hour.soak_iterations, one_hour.soak_interval_seconds), (13, 300.0))
        self.assertEqual((overnight.soak_iterations, overnight.soak_interval_seconds), (17, 1800.0))

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
            attempt_copy = pathlib.Path(tmpdir).parent / manifest["artifact_paths"]["attempt_copy"]
            attempt_copy_exists = attempt_copy.is_file()
            attempt_copy_name = attempt_copy.name

        self.assertEqual(exit_code, 0)
        self.assertTrue(output_path.name.endswith("pi-low-power-evidence.json"))
        self.assertIn("artifact_paths", manifest)
        self.assertIn("latest", manifest["artifact_paths"])
        self.assertIn("attempt_copy", manifest["artifact_paths"])
        self.assertTrue(attempt_copy_exists)
        self.assertNotEqual(attempt_copy_name, output_path.name)
        self.assertIn("quick", attempt_copy_name)
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
        self.assertEqual(manifest["service_boundary"]["fork_test_service"]["restart_count"], 0)
        self.assertTrue(manifest["backup_evidence"]["backup_first_confirmed"])
        self.assertTrue(manifest["runtime_verification_evidence"]["clean_profile_status"] == "pass")
        self.assertEqual(
            manifest["runtime_verification_evidence"]["player_load_probe_status"],
            "pass",
        )
        self.assertEqual(
            manifest["runtime_verification_evidence"]["player_load_probe_kind"],
            "headless_client_load",
        )
        self.assertEqual(
            manifest["runtime_verification_evidence"]["attempted_synthetic_player_count"],
            2,
        )
        self.assertEqual(
            manifest["runtime_verification_evidence"]["connected_synthetic_player_count"],
            2,
        )
        self.assertTrue(
            manifest["runtime_verification_evidence"]["latency_proxy_supported"],
        )
        self.assertEqual(
            manifest["runtime_verification_evidence"]["latency_probe_kind"],
            "headless_join_log_observation",
        )
        self.assertEqual(
            manifest["runtime_verification_evidence"]["join_latency_proxy_sample_count"],
            2,
        )
        self.assertEqual(
            manifest["runtime_verification_evidence"]["scale_gate_status"],
            "pass",
        )
        self.assertEqual(
            manifest["runtime_verification_evidence"]["scale_gate_required_synthetic_player_count"],
            2,
        )
        self.assertEqual(
            manifest["runtime_verification_evidence"]["scale_gate_required_concurrent_task_count"],
            2,
        )
        self.assertEqual(
            manifest["runtime_verification_evidence"]["server_step_workload_status"],
            "pass",
        )
        self.assertEqual(
            manifest["runtime_verification_evidence"]["compat_import_staging_pilot_status"],
            "pass",
        )
        self.assertTrue(
            manifest["runtime_verification_evidence"]["compat_import_inventory_ready"],
        )
        self.assertEqual(
            manifest["runtime_verification_evidence"]["compat_import_node_writes"],
            4,
        )
        self.assertEqual(
            manifest["runtime_verification_evidence"]["avg_process_cpu_percent"],
            14.5,
        )
        self.assertEqual(
            manifest["runtime_verification_evidence"]["max_interval_cpu_percent"],
            42.0,
        )
        self.assertEqual(
            manifest["runtime_verification_evidence"]["max_rss_mb"],
            192.0,
        )
        self.assertTrue(manifest["studio_status_evidence"]["present"])
        self.assertTrue(manifest["studio_status_evidence"]["public_safe"])
        self.assertTrue(manifest["studio_status_evidence"]["services_all_active"])
        self.assertFalse(manifest["studio_status_evidence"]["direct_world_mutation_by_ai"])
        self.assertEqual(manifest["studio_status_evidence"]["quality_gate"]["status"], "pass")
        self.assertEqual(
            manifest["studio_status_evidence"]["live_review_gate"]["current_health"],
            "pass",
        )
        self.assertEqual(
            manifest["studio_status_evidence"]["live_review_gate"]["selected_option_id"],
            "fire",
        )
        self.assertEqual(
            manifest["studio_status_evidence"]["prompt_eval"]["cases_passed"],
            12,
        )
        self.assertEqual(
            manifest["studio_status_evidence"]["prompt_eval"]["golden_prompts_passed"],
            9,
        )
        self.assertEqual(
            manifest["studio_status_evidence"]["adapter_log"]["release_health"],
            "pass",
        )
        self.assertEqual(
            manifest["studio_status_evidence"]["adapter_log"]["latest"]["selected_option_id"],
            "generated_openrealm_lakeside_village",
        )
        self.assertTrue(
            manifest["studio_status_evidence"]["adapter_log"]["latest"]["web_search_available"],
        )
        self.assertEqual(
            manifest["studio_status_evidence"]["runtime_proofs"]["current_health"],
            "pass",
        )
        self.assertEqual(manifest["soak_evidence"]["iterations_requested"], 1)
        self.assertEqual(manifest["soak_evidence"]["iterations_completed"], 1)
        self.assertEqual(manifest["soak_evidence"]["iterations_passed"], 1)
        self.assertEqual(
            manifest["soak_evidence"]["resource_maxima"]["avg_process_cpu_percent"],
            14.5,
        )
        self.assertEqual(
            manifest["soak_evidence"]["resource_maxima"]["max_rss_mb"],
            192.0,
        )
        self.assertEqual(
            manifest["soak_evidence"]["resource_budgets"]["max_fork_restarts"],
            0,
        )
        self.assertEqual(
            manifest["soak_evidence"]["samples"][0]["failure_reasons"],
            [],
        )
        self.assertIn(
            "clean_profile_summary",
            manifest["soak_evidence"]["samples"][0]["artifact_keys"],
        )
        self.assertEqual(manifest["soak_evidence"]["target"]["name"], "quick")
        self.assertTrue(manifest["soak_evidence"]["target"]["duration_met"])
        self.assertEqual(manifest["soak_evidence"]["target"]["next_target"], "one-hour")
        self.assertEqual(manifest["ranked_follow_up_issue_seeds"], [])
        self.assertEqual(manifest["failure_reasons"], [])
        self.assertNotRegex(json.dumps(manifest, sort_keys=True), PRIVATE_PATTERNS)

    def test_attempt_copy_can_be_disabled_for_latest_only_runs(self):
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
                    "--no-retain-attempt-copy",
                ]
            )
            fake_runner = FakeRunner(module)

            exit_code, output_path, manifest = module.run(
                args,
                runner=fake_runner,
                now_fn=lambda: "2026-06-29T10:00:00Z",
            )
            output_exists = output_path.is_file()

        self.assertEqual(exit_code, 0)
        self.assertTrue(output_exists)
        self.assertIn("latest", manifest["artifact_paths"])
        self.assertNotIn("attempt_copy", manifest["artifact_paths"])
        self.assertNotRegex(json.dumps(manifest, sort_keys=True), PRIVATE_PATTERNS)

    def test_remote_verifier_requires_headless_player_probe(self):
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

            module.run(args, runner=fake_runner, now_fn=lambda: "2026-06-29T10:00:00Z")

        verify_commands = [
            " ".join(command)
            for command in fake_runner.calls
            if "ai_native_runtime_verify.py" in " ".join(command)
        ]
        self.assertTrue(verify_commands)
        command = verify_commands[0]
        self.assertIn("--headless-player-command", command)
        self.assertIn("--headless-player-count 2", command)
        self.assertIn("--require-headless-player-probe", command)
        self.assertIn("video_driver = null", command)
        self.assertIn("bin/luanti", command)

    def test_accepts_flattened_clean_profile_status_from_runtime_verifier(self):
        module = load_module()
        remote_manifest = FakeRunner(module).default_remote_manifest()
        remote_manifest["clean_profile_evidence"] = {
            "overall_status": "pass",
            "server_step_workload_status": "pass",
            "player_load_probe_status": "pass",
            "player_load_probe_kind": "headless_client_load",
            "headless_player_supported": True,
            "attempted_synthetic_player_count": 2,
            "connected_synthetic_player_count": 2,
            "completed_synthetic_player_count": 2,
            "latency_proxy_supported": True,
            "latency_probe_kind": "headless_join_log_observation",
            "join_latency_proxy_sample_count": 2,
            "scale_gate_status": "pass",
            "scale_gate_required_synthetic_player_count": 2,
            "scale_gate_required_concurrent_task_count": 2,
            "actionable_warning_count": 0,
            "server_log_error_count": 0,
            "cpu_status": "measured",
            "cpu_sample_count": 3,
            "avg_process_cpu_percent": 14.5,
            "max_interval_cpu_percent": 42.0,
            "rss_sample_count": 3,
            "max_rss_kb": 196608,
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

    def test_manifest_fails_when_headless_player_evidence_is_missing(self):
        module = load_module()
        remote_manifest = FakeRunner(module).default_remote_manifest()
        remote_manifest["clean_profile_evidence"].update(
            {
                "player_load_probe_kind": "server_process_liveness",
                "headless_player_supported": False,
                "attempted_synthetic_player_count": 0,
                "connected_synthetic_player_count": 0,
                "completed_synthetic_player_count": 0,
                "latency_proxy_supported": False,
                "latency_probe_kind": "not_measured",
                "join_latency_proxy_sample_count": 0,
            }
        )

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

        self.assertEqual(exit_code, 2)
        self.assertIn("headless_player_probe_not_measured", manifest["failure_reasons"])
        self.assertIn("headless_player_latency_not_measured", manifest["failure_reasons"])
        self.assertNotRegex(json.dumps(manifest, sort_keys=True), PRIVATE_PATTERNS)

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
                ] + FakeRunner(module).default_studio_status_lines()
            )
            fake_runner = FakeRunner(module, service_output=service_output)

            exit_code, _, manifest = module.run(args, runner=fake_runner, now_fn=lambda: "2026-06-29T10:00:00Z")

        self.assertEqual(exit_code, 2)
        self.assertEqual(manifest["overall_status"], "fail")
        self.assertIn("backup_first_confirmation_missing", manifest["failure_reasons"])
        self.assertIn("fork_test_service_not_active", manifest["failure_reasons"])
        self.assertIn("fork_test_udp_port_not_listening", manifest["failure_reasons"])
        self.assertNotRegex(json.dumps(manifest, sort_keys=True), PRIVATE_PATTERNS)

    def test_soak_runner_repeats_verifier_and_enforces_resource_budgets(self):
        module = load_module()
        remote_manifest = FakeRunner(module).default_remote_manifest()
        remote_manifest["clean_profile_evidence"].update(
            {
                "avg_process_cpu_percent": 91.0,
                "max_interval_cpu_percent": 180.0,
                "max_rss_kb": 1536000,
                "actionable_warning_count": 1,
                "server_log_error_count": 1,
            }
        )
        service_output = "\n".join(
            [
                "family_service_active=active",
                "fork_service_active=active",
                "family_udp_listening=true",
                "fork_udp_listening=true",
                "fork_version=Luanti 5.17.0-dev-26eb426dc (Linux)",
                "fork_commit=26eb426dc",
                "fork_restart_count=2",
                "fork_active_enter_timestamp=Mon 2026-06-29 10:00:00 UTC",
            ] + FakeRunner(module).default_studio_status_lines()
        )
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
                    "--soak-iterations",
                    "2",
                    "--max-avg-cpu-percent",
                    "80",
                    "--max-interval-cpu-percent",
                    "120",
                    "--max-rss-mb",
                    "512",
                    "--max-actionable-warning-count",
                    "0",
                    "--max-server-log-error-count",
                    "0",
                    "--max-fork-restarts",
                    "0",
                ]
            )
            fake_runner = FakeRunner(
                module,
                remote_manifest=remote_manifest,
                service_output=service_output,
            )

            exit_code, _, manifest = module.run(args, runner=fake_runner, now_fn=lambda: "2026-06-29T10:00:00Z")

        verify_commands = [
            command for command in fake_runner.calls
            if "ai_native_runtime_verify.py" in " ".join(command)
        ]
        self.assertEqual(len(verify_commands), 2)
        self.assertEqual(exit_code, 2)
        self.assertEqual(manifest["soak_evidence"]["iterations_requested"], 2)
        self.assertEqual(manifest["soak_evidence"]["iterations_completed"], 2)
        self.assertEqual(manifest["soak_evidence"]["resource_maxima"]["max_rss_mb"], 1500.0)
        self.assertIn("fork_restart_budget_exceeded", manifest["failure_reasons"])
        self.assertIn("avg_cpu_budget_exceeded", manifest["failure_reasons"])
        self.assertIn("max_cpu_budget_exceeded", manifest["failure_reasons"])
        self.assertIn("memory_rss_budget_exceeded", manifest["failure_reasons"])
        self.assertIn("actionable_warning_budget_exceeded", manifest["failure_reasons"])
        self.assertIn("server_log_error_budget_exceeded", manifest["failure_reasons"])
        self.assertEqual(
            [issue["severity"] for issue in manifest["ranked_follow_up_issue_seeds"][:3]],
            ["P1", "P1", "P2"],
        )
        self.assertEqual(
            manifest["ranked_follow_up_issue_seeds"][0]["source_failure"],
            "fork_restart_budget_exceeded",
        )
        self.assertNotRegex(json.dumps(manifest, sort_keys=True), PRIVATE_PATTERNS)

    def test_manifest_fails_when_studio_live_review_gate_is_not_passing(self):
        module = load_module()
        service_lines = FakeRunner(module).default_service_output().splitlines()
        service_output = "\n".join(
            "studio_live_review_gate_health=fail"
            if line == "studio_live_review_gate_health=pass"
            else line
            for line in service_lines
        )

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
            fake_runner = FakeRunner(module, service_output=service_output)

            exit_code, _, manifest = module.run(
                args,
                runner=fake_runner,
                now_fn=lambda: "2026-06-29T10:00:00Z",
            )

        self.assertEqual(exit_code, 2)
        self.assertEqual(manifest["studio_status_evidence"]["live_review_gate"]["current_health"], "fail")
        self.assertIn("studio_live_review_gate_not_pass", manifest["failure_reasons"])
        self.assertEqual(
            manifest["ranked_follow_up_issue_seeds"][0]["source_failure"],
            "studio_live_review_gate_not_pass",
        )
        self.assertNotRegex(json.dumps(manifest, sort_keys=True), PRIVATE_PATTERNS)

    def test_one_hour_soak_target_requires_elapsed_duration(self):
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
                    "--soak-target",
                    "one-hour",
                    "--soak-iterations",
                    "2",
                    "--soak-interval-seconds",
                    "0",
                ]
            )
            fake_runner = FakeRunner(module)
            monotonic_values = iter([100.0, 220.0])

            exit_code, _, manifest = module.run(
                args,
                runner=fake_runner,
                now_fn=lambda: "2026-06-29T10:00:00Z",
                monotonic_fn=lambda: next(monotonic_values),
            )

        self.assertEqual(exit_code, 2)
        self.assertEqual(manifest["soak_evidence"]["target"]["name"], "one-hour")
        self.assertEqual(
            manifest["soak_evidence"]["target"]["minimum_duration_seconds"],
            3600.0,
        )
        self.assertEqual(manifest["soak_evidence"]["target"]["elapsed_seconds"], 120.0)
        self.assertFalse(manifest["soak_evidence"]["target"]["duration_met"])
        self.assertEqual(manifest["soak_evidence"]["target"]["next_target"], "overnight")
        self.assertIn("soak_target_duration_not_met", manifest["failure_reasons"])
        self.assertEqual(
            manifest["ranked_follow_up_issue_seeds"][0]["source_failure"],
            "soak_target_duration_not_met",
        )
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
        self.assertEqual(
            manifest["soak_evidence"]["samples"][0]["failure_reasons"],
            ["branch_benchmark_gate exited with status 1"],
        )
        self.assertIn(
            "benchmark_gate_manifest",
            manifest["soak_evidence"]["samples"][0]["artifact_keys"],
        )
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
        self.assertIn("--soak-iterations", alpha_gate)
        self.assertIn("--soak-target one-hour", alpha_gate)
        self.assertIn("--soak-target overnight", alpha_gate)
        self.assertIn("max_avg_cpu_percent", alpha_gate)
        self.assertIn("max_rss_mb", alpha_gate)

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
