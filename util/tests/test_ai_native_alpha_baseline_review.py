import json
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
REVIEW_CLI = ROOT / "util" / "ai_native_alpha_baseline_review.py"
PARITY_CLI = ROOT / "util" / "ai_native_minecraft_parity_harness.py"
DOC = ROOT / "doc" / "ai-native-runtime" / "benchmark-baseline-retention.md"
README = ROOT / "doc" / "ai-native-runtime" / "README.md"

PRIVATE_PATTERNS = re.compile(
    r"minecraftpi|192\.168|spacebase|themepark|showcase100|disneyland100|"
    r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY|private_prompt|asset_payload|/Users/|/opt/|bill@",
    re.I,
)


class AlphaBaselineReviewTests(unittest.TestCase):
    def write_json(self, path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def write_accepted_baseline(self, output_root, hardware_class):
        accepted = pathlib.Path(output_root) / hardware_class / "accepted"
        self.write_json(
            accepted / "accepted-baseline-manifest.json",
            {
                "schema_version": 1,
                "generated_at": "2026-06-29T00:00:00Z",
                "luanti_commit": f"{hardware_class}-commit",
                "hardware_class": hardware_class,
                "game_profile": "ai_runtime",
                "source_label": f"reviewed-{hardware_class}-alpha",
                "source_capture": f"local/benchmarks/{hardware_class}/2026-06-29/alpha",
                "reports": {
                    "mutation": "mutation-benchmark-report.json",
                    "demo_entity": "generic-demo-entity-benchmark-report.json",
                    "clean_profile": "clean-profile-benchmark-summary.json",
                },
                "run_context": {
                    "mode": "accepted-local-baseline",
                    "requires_private_world": False,
                    "requires_private_assets": False,
                    "requires_live_pi": False,
                    "requires_model_network": False,
                },
            },
        )
        self.write_json(
            accepted / "mutation-benchmark-report.json",
            {
                "schema_version": 1,
                "luanti_commit": f"{hardware_class}-commit",
                "hardware_class": hardware_class,
                "run_context": {
                    "mode": "sample-synthetic",
                    "requires_private_world": False,
                    "requires_private_assets": False,
                    "requires_live_pi": False,
                },
                "scenarios": [
                    {
                        "scenario_id": "small_build_rollback",
                        "metrics": {
                            "node_writes": 8,
                            "node_writes_per_step": 8,
                            "rollback_records": 1,
                            "warnings": [],
                            "errors": [],
                        },
                    },
                    {
                        "scenario_id": "first_party_agent_product_loop_approval",
                        "metrics": {
                            "node_writes": 2,
                            "node_writes_per_step": 1,
                            "rollback_records": 2,
                            "warnings": [],
                            "errors": [],
                        },
                    },
                ],
            },
        )
        self.write_json(
            accepted / "generic-demo-entity-benchmark-report.json",
            {
                "schema_version": 1,
                "fixture_id": "generic_demo_entity:benchmark:v1",
                "luanti_commit": f"{hardware_class}-commit",
                "hardware_class": hardware_class,
                "run_context": {
                    "mode": "sample-synthetic",
                    "requires_private_world": False,
                    "requires_private_assets": False,
                    "requires_live_pi": False,
                },
                "scenarios": [
                    {
                        "scenario_id": "entity_scale_16",
                        "metrics": {
                            "entity_count": 16,
                            "active_peak": 16,
                            "remaining_entities": 0,
                            "warnings": [],
                            "errors": [],
                        },
                    }
                ],
            },
        )
        self.write_json(
            accepted / "clean-profile-benchmark-summary.json",
            {
                "schema_version": 1,
                "runner_version": "ai-native-clean-profile-benchmark:v1",
                "generated_at": "2026-06-29T00:00:00Z",
                "luanti_commit": f"{hardware_class}-commit",
                "hardware_class": hardware_class,
                "overall_status": "pass",
                "game_profile": {
                    "gameid": "ai_runtime",
                    "profile_path": "games/ai_runtime",
                    "profile_kind": "public-safe-ai-runtime",
                },
                "run_context": {
                    "mode": "clean-profile-local-server",
                    "requires_private_world": False,
                    "requires_private_assets": False,
                    "requires_live_pi": False,
                    "requires_model_network": False,
                },
                "comparison_summary": {
                    "startup": {
                        "listening": True,
                        "time_to_listen_ms": 220.0,
                        "startup_timeout_seconds": 15.0,
                    },
                    "steady_tick_behavior": {
                        "sample_seconds": 3.0,
                        "observed_uptime_seconds": 3.2,
                        "process_exited_unexpectedly": False,
                        "server_log_warning_count": 0,
                        "expected_server_log_warning_count": 0,
                        "actionable_server_log_warning_count": 0,
                        "expected_warning_kinds": [],
                        "server_log_error_count": 0,
                    },
                    "server_step_workload": {
                        "workload_status": "pass",
                        "workload_kind": "server_step_liveness",
                        "attempted_sample_count": 30,
                        "completed_sample_count": 30,
                        "failed_sample_count": 0,
                        "p95_sample_interval_ms": 100.0,
                        "max_sample_interval_ms": 120.0,
                    },
                    "player_load_tick_probe": {
                        "probe_status": "pass",
                        "probe_kind": "headless_client_load",
                        "synthetic_player_count": 2,
                        "attempted_synthetic_player_count": 2,
                        "connected_synthetic_player_count": 2,
                        "completed_synthetic_player_count": 2,
                        "headless_player_supported": True,
                        "server_stayed_listening": True,
                        "client_exit_statuses": [0, 0],
                        "client_launch_failure_count": 0,
                        "cleanup_status": "complete",
                        "latency_probe_kind": "headless_join_log_observation",
                        "latency_proxy_supported": True,
                        "join_latency_proxy_ms": {
                            "sample_count": 2,
                            "min": 80.0,
                            "p50": 80.0,
                            "p95": 80.0,
                            "max": 80.0,
                            "avg": 80.0,
                        },
                    },
                    "map_chunk_workload": {
                        "workload_status": "pass",
                        "workload_kind": "synthetic_sqlite_mapblock_churn",
                        "world_backend": "sqlite3",
                        "map_sqlite_bytes": 12288,
                        "mapblock_rows": 256,
                        "mapblock_rows_created": 4,
                        "inspection_status": "ok",
                    },
                    "entity_runtime_operations": {
                        "scenario_count": 1,
                        "max_entity_count": 16,
                        "max_active_peak": 16,
                        "max_remaining_entities": 0,
                        "warnings": 0,
                        "errors": 0,
                    },
                    "mutation_write_throughput": {
                        "scenario_count": 2,
                        "total_node_writes": 10,
                        "max_node_writes_per_step": 8,
                        "total_rollback_records": 3,
                        "warnings": 0,
                        "errors": 0,
                    },
                    "first_party_agent_product_loop": {
                        "product_loop_status": "pass",
                        "scenario_id": "first_party_agent_product_loop_approval",
                        "approval_plan_count": 2,
                        "approved_task_count": 2,
                        "guide_command_checked": 1,
                        "tasks_command_checked": 1,
                        "cancel_command_checked": 1,
                        "audit_review_checked": 1,
                        "rollback_review_checked": 1,
                        "defender_command_checked": 1,
                        "import_preview_checked": 1,
                        "blocked_or_unsafe_outcomes": 0,
                        "queued_task_count": 2,
                        "completed_task_count": 2,
                        "blocked_task_count": 0,
                        "node_writes": 2,
                        "node_writes_per_step": 1,
                        "mapblock_churn": 1,
                        "rollback_records": 2,
                        "avg_task_duration_ms": 2.3,
                        "p95_task_duration_ms": 3.0,
                        "max_task_lag_ms": 3.6,
                        "warning_count": 0,
                        "error_count": 0,
                    },
                    "ai_runtime_scale_gate": {
                        "scale_gate_status": "pass",
                        "gate_kind": "ai_runtime_multi_player_multi_agent_scale",
                        "synthetic_disposable_only": True,
                        "required_synthetic_player_count": 2,
                        "required_concurrent_task_count": 2,
                        "requirements": {
                            "multi_player_headless_load": True,
                            "concurrent_first_party_tasks": True,
                            "bounded_task_durations": True,
                            "bounded_write_and_rollback": True,
                            "bounded_entity_lane": True,
                            "server_step_clean": True,
                            "resource_samples_present": True,
                            "no_warnings_or_errors": True,
                        },
                    },
                    "memory": {
                        "max_rss_kb": 28000,
                        "rss_sample_count": 30,
                    },
                    "cpu": {
                        "sample_status": "measured",
                        "cpu_sample_count": 30,
                        "process_cpu_time_delta_seconds": 0.12,
                        "observed_wall_time_seconds": 3.0,
                        "avg_process_cpu_percent": 4.0,
                        "max_interval_cpu_percent": 9.5,
                        "sample_methods": ["ps_time"],
                        "limitations": [],
                    },
                    "failure_notes": [],
                },
                "failure_notes": [],
            },
        )

    def write_import_inventory_discovery_report(self, output_root):
        self.write_json(
            pathlib.Path(output_root) / "compatibility-import-inventory-discovery-report.json",
            {
                "mode": "import_inventory_discovery",
                "status": "ready_for_import_preview",
                "summary": {
                    "compatibility_import_inventory_ready": True,
                    "sources_total": 1,
                    "inventory_items_total": 2,
                    "planned_actions_total": 1,
                    "source_status_counts": {"supported": 1},
                    "by_source_class": {"java_resource_pack": 1},
                    "required_capabilities": ["import.assets"],
                },
                "readiness": {"blocking_reasons": []},
                "safety": {
                    "dry_run_only": True,
                    "no_assets_copied": True,
                    "no_world_mutation": True,
                    "source_paths_redacted": True,
                    "no_raw_payloads": True,
                    "no_private_paths": True,
                    "uses_proprietary_minecraft_code_or_assets": False,
                    "uses_copied_server_jars_or_game_data": False,
                },
            },
        )

    def write_low_power_evidence(self, output_root):
        self.write_json(
            pathlib.Path(output_root)
            / "low-power-server"
            / "2026-06-29"
            / "low-power-commit"
            / "pi-low-power-evidence.json",
            {
                "schema_version": 1,
                "hardware_class": "low-power-server",
                "luanti_commit": "low-power-commit",
                "generated_at": "2026-06-29T00:00:00Z",
                "overall_status": "pass",
                "backup_evidence": {
                    "backup_first_confirmed": True,
                    "sha256_recorded": True,
                },
                "service_boundary": {
                    "family_service": {
                        "active": True,
                        "udp_listening": True,
                        "port": 30000,
                    },
                    "fork_test_service": {
                        "active": True,
                        "udp_listening": True,
                        "port": 30001,
                        "commit": "low-power-commit",
                    },
                },
                "runtime_verification_evidence": {
                    "player_load_probe_status": "pass",
                    "player_load_probe_kind": "headless_client_load",
                    "headless_player_supported": True,
                    "attempted_synthetic_player_count": 2,
                    "connected_synthetic_player_count": 2,
                    "completed_synthetic_player_count": 2,
                    "latency_probe_kind": "headless_join_log_observation",
                    "join_latency_proxy_sample_count": 2,
                },
                "safety": {
                    "public_safe_output": True,
                    "private_target_redacted": True,
                    "remote_paths_redacted": True,
                    "no_family_content": True,
                    "no_copied_assets": True,
                    "no_provider_prompts": True,
                },
            },
        )

    def prepare_output_root(self, output_root):
        for hardware_class in ("local-mac", "low-power-server"):
            self.write_accepted_baseline(output_root, hardware_class)
        self.write_import_inventory_discovery_report(output_root)
        self.write_low_power_evidence(output_root)
        completed = subprocess.run(
            [
                sys.executable,
                str(PARITY_CLI),
                "--output-root",
                str(output_root),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_review_passes_for_public_safe_accepted_alpha_lanes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            self.prepare_output_root(output_root)
            report_path = pathlib.Path(tmpdir) / "alpha-baseline-review.json"

            completed = subprocess.run(
                [
                    sys.executable,
                    str(REVIEW_CLI),
                    "--output-root",
                    str(output_root),
                    "--output",
                    str(report_path),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            review = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(review["review_kind"], "ai_native_alpha_baseline_review")
            self.assertEqual(review["overall_status"], "pass")
            self.assertEqual(review["hardware_classes"], ["local-mac", "low-power-server"])
            self.assertEqual(review["low_power_pi_evidence"]["status"], "pass")
            self.assertEqual(review["minecraft_parity"]["status"], "pass")
            self.assertEqual(review["minecraft_parity"]["actionable_scorecard_count"], 0)
            self.assertEqual(
                {lane["hardware_class"]: lane["status"] for lane in review["lane_reviews"]},
                {"local-mac": "pass", "low-power-server": "pass"},
            )
            self.assertNotRegex(json.dumps(review, sort_keys=True), PRIVATE_PATTERNS)

    def test_review_fails_when_low_power_accepted_lane_loses_headless_probe(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            self.prepare_output_root(output_root)
            clean_profile_path = (
                output_root
                / "low-power-server"
                / "accepted"
                / "clean-profile-benchmark-summary.json"
            )
            clean_profile = json.loads(clean_profile_path.read_text(encoding="utf-8"))
            probe = clean_profile["comparison_summary"]["player_load_tick_probe"]
            probe["probe_kind"] = "server_process_liveness"
            probe["headless_player_supported"] = False
            self.write_json(clean_profile_path, clean_profile)
            report_path = pathlib.Path(tmpdir) / "alpha-baseline-review.json"

            completed = subprocess.run(
                [
                    sys.executable,
                    str(REVIEW_CLI),
                    "--output-root",
                    str(output_root),
                    "--output",
                    str(report_path),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 1, completed.stderr)
            review = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(review["overall_status"], "fail")
            failures = "\n".join(review["failure_reasons"])
            self.assertIn("low-power-server: player_load_tick_probe", failures)

    def test_docs_cover_alpha_baseline_review_and_low_power_promotion(self):
        combined = "\n".join(path.read_text(encoding="utf-8") for path in (DOC, README))
        for phrase in (
            "util/ai_native_alpha_baseline_review.py",
            "alpha-baseline-review.json",
            "local/benchmarks/low-power-server/accepted/",
            "pi-low-power-evidence.json",
            "Minecraft-parity harness",
            "backup-first",
            "private worlds",
            "copied assets",
        ):
            self.assertIn(phrase, combined)
        self.assertNotRegex(combined, PRIVATE_PATTERNS)


if __name__ == "__main__":
    unittest.main()
