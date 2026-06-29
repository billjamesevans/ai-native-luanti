import json
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
CLI = ROOT / "util" / "ai_native_minecraft_parity_harness.py"
DOC = ROOT / "doc" / "ai-native-runtime" / "minecraft-parity-benchmark-harness.md"
README = ROOT / "doc" / "ai-native-runtime" / "README.md"

PRIVATE_PATTERNS = re.compile(
    r"minecraftpi|192\.168|spacebase|themepark|showcase100|disneyland100|"
    r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY|private_prompt|asset_payload|/Users/|/opt/|bill@",
    re.I,
)


class MinecraftParityHarnessTests(unittest.TestCase):
    def write_json(self, path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def write_accepted_baseline(
        self,
        output_root,
        hardware_class="local-mac",
        *,
        headless_players=False,
        mapblock_rows=0,
        entity_count=4,
        total_node_writes=0,
        cpu_evidence=False,
        first_party_loop=False,
    ):
        accepted = pathlib.Path(output_root) / hardware_class / "accepted"
        self.write_json(
            accepted / "accepted-baseline-manifest.json",
            {
                "schema_version": 1,
                "generated_at": "2026-06-28T00:00:00Z",
                "luanti_commit": f"{hardware_class}-commit",
                "hardware_class": hardware_class,
                "game_profile": "ai_runtime",
                "source_label": f"reviewed-{hardware_class}",
                "source_capture": f"local/benchmarks/{hardware_class}/2026-06-28/example",
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
                            "node_writes": total_node_writes,
                            "node_writes_per_step": 8,
                            "rollback_records": 1,
                            "warnings": [],
                            "errors": [],
                        },
                    }
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
                        "scenario_id": "entity_scale",
                        "metrics": {
                            "entity_count": entity_count,
                            "active_peak": entity_count,
                            "remaining_entities": 0,
                            "warnings": [],
                            "errors": [],
                        },
                    }
                ],
            },
        )
        probe = {
            "probe_status": "pass",
            "probe_kind": "server_process_liveness",
            "sample_count": 30,
            "synthetic_player_count": 0,
            "headless_player_supported": False,
            "server_stayed_listening": True,
            "p95_sample_interval_ms": 100.0,
            "max_sample_interval_ms": 120.0,
            "latency_probe_kind": "not_measured",
            "latency_proxy_supported": False,
            "join_latency_proxy_ms": {
                "sample_count": 0,
                "min": None,
                "p50": None,
                "p95": None,
                "max": None,
                "avg": None,
            },
            "limitations": ["headless-player client load is not wired in this fixture"],
        }
        if headless_players:
            probe.update(
                {
                    "probe_kind": "headless_client_load",
                    "synthetic_player_count": 2,
                    "attempted_synthetic_player_count": 2,
                    "connected_synthetic_player_count": 2,
                    "completed_synthetic_player_count": 2,
                    "headless_player_supported": True,
                    "client_exit_statuses": [0, 0],
                    "client_launch_failure_count": 0,
                    "cleanup_status": "complete",
                    "latency_probe_kind": "headless_join_log_observation",
                    "latency_proxy_supported": True,
                    "join_latency_proxy_ms": {
                        "sample_count": 2,
                        "min": 80.0,
                        "p50": 80.0,
                        "p95": 120.0,
                        "max": 120.0,
                        "avg": 100.0,
                    },
                    "limitations": [],
                }
            )
        self.write_json(
            accepted / "clean-profile-benchmark-summary.json",
            {
                "schema_version": 1,
                "runner_version": "ai-native-clean-profile-benchmark:v1",
                "generated_at": "2026-06-28T00:00:00Z",
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
                    "player_load_tick_probe": probe,
                    "map_chunk_workload": {
                        "world_backend": "sqlite3",
                        "map_sqlite_bytes": 12288,
                        "mapblock_rows": mapblock_rows,
                        "inspection_status": "ok",
                    },
                    "entity_runtime_operations": {
                        "scenario_count": 1,
                        "max_entity_count": entity_count,
                        "max_active_peak": entity_count,
                        "max_remaining_entities": 0,
                        "warnings": 0,
                        "errors": 0,
                    },
                    "mutation_write_throughput": {
                        "scenario_count": 1,
                        "total_node_writes": total_node_writes,
                        "max_node_writes_per_step": 8,
                        "total_rollback_records": 1,
                        "warnings": 0,
                        "errors": 0,
                    },
                    "first_party_agent_product_loop": {
                        "product_loop_status": "pass" if first_party_loop else "missing",
                        "scenario_id": "first_party_agent_product_loop_approval",
                        "approval_plan_count": 2 if first_party_loop else 0,
                        "approved_task_count": 2 if first_party_loop else 0,
                        "guide_command_checked": 1 if first_party_loop else 0,
                        "tasks_command_checked": 1 if first_party_loop else 0,
                        "cancel_command_checked": 1 if first_party_loop else 0,
                        "audit_review_checked": 1 if first_party_loop else 0,
                        "rollback_review_checked": 1 if first_party_loop else 0,
                        "defender_command_checked": 1 if first_party_loop else 0,
                        "import_preview_checked": 1 if first_party_loop else 0,
                        "blocked_or_unsafe_outcomes": 0 if first_party_loop else None,
                        "queued_task_count": 2 if first_party_loop else 0,
                        "completed_task_count": 2 if first_party_loop else 0,
                        "blocked_task_count": 0,
                        "node_writes": 2 if first_party_loop else 0,
                        "node_writes_per_step": 1 if first_party_loop else 0,
                        "mapblock_churn": 1 if first_party_loop else 0,
                        "rollback_records": 2 if first_party_loop else 0,
                        "avg_task_duration_ms": 2.3 if first_party_loop else None,
                        "p95_task_duration_ms": 3.0 if first_party_loop else None,
                        "max_task_lag_ms": 3.6 if first_party_loop else None,
                        "warning_count": 0,
                        "error_count": 0,
                    },
                    "ai_runtime_scale_gate": {
                        "scale_gate_status": "pass" if first_party_loop else "missing",
                        "gate_kind": "ai_runtime_multi_player_multi_agent_scale",
                        "synthetic_disposable_only": True if first_party_loop else None,
                        "required_synthetic_player_count": 2,
                        "required_concurrent_task_count": 2,
                        "requirements": {
                            "multi_player_headless_load": bool(first_party_loop),
                            "concurrent_first_party_tasks": bool(first_party_loop),
                            "bounded_task_durations": bool(first_party_loop),
                            "bounded_write_and_rollback": bool(first_party_loop),
                            "bounded_entity_lane": bool(first_party_loop),
                            "server_step_clean": bool(first_party_loop),
                            "resource_samples_present": bool(first_party_loop),
                            "no_warnings_or_errors": bool(first_party_loop),
                        },
                    },
                    "memory": {
                        "max_rss_kb": 28000,
                        "rss_sample_count": 30,
                    },
                    **({
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
                    } if cpu_evidence else {}),
                    "failure_notes": [],
                },
                "failure_notes": [],
            },
        )

    def run_harness(self, output_root, *extra_args, check=True):
        completed = subprocess.run(
            [
                sys.executable,
                str(CLI),
                "--output-root",
                str(output_root),
                "--hardware-class",
                "local-mac",
                *extra_args,
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if check:
            self.assertEqual(completed.returncode, 0, completed.stderr)
        return completed

    def write_import_inventory_discovery_report(self, output_root):
        self.write_json(
            pathlib.Path(output_root) / "compatibility-import-inventory-discovery-report.json",
            {
                "report_version": 1,
                "mode": "import_inventory_discovery",
                "status": "ready_for_import_preview",
                "summary": {
                    "compatibility_import_inventory_ready": True,
                    "sources_total": 4,
                    "inventory_items_total": 9,
                    "planned_actions_total": 6,
                    "by_source_class": {
                        "java_resource_pack": 1,
                        "luanti_mod": 1,
                        "schematic": 1,
                        "world": 1,
                    },
                    "source_status_counts": {
                        "supported": 1,
                        "partial": 2,
                        "unsupported": 0,
                        "skipped": 0,
                        "blocked": 1,
                    },
                    "inventory_classification_counts": {
                        "supported": 4,
                        "partial": 0,
                        "unsupported": 1,
                        "skipped": 0,
                        "blocked": 4,
                    },
                    "required_capabilities": ["import.assets"],
                },
                "readiness": {
                    "compatibility_import_inventory_ready": True,
                    "blocking_reasons": [],
                },
                "sources": [
                    {
                        "source_id": "source:java_pack",
                        "source_class": "java_resource_pack",
                        "status": "partial",
                        "inventory_count": 2,
                        "planned_actions_count": 2,
                        "required_capabilities": ["import.assets"],
                        "report_path": "001-source-java_pack.json",
                    },
                    {
                        "source_id": "source:luanti_mod",
                        "source_class": "luanti_mod",
                        "status": "supported",
                        "inventory_count": 2,
                        "planned_actions_count": 1,
                        "required_capabilities": ["import.assets"],
                        "report_path": "002-source-luanti_mod.json",
                    },
                ],
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

    def write_agent_tool_power_readiness_report(self, output_root):
        tool_powers = [
            {
                "name": "summarize_runtime_capabilities",
                "kind": "function_tool",
                "direct_world_mutation": False,
                "requires_openai_api_key": False,
            },
            {
                "name": "classify_world_action",
                "kind": "function_tool",
                "direct_world_mutation": False,
                "requires_openai_api_key": False,
            },
            {
                "name": "WebSearchTool",
                "kind": "hosted_tool",
                "direct_world_mutation": False,
                "requires_openai_api_key": True,
            },
        ]
        self.write_json(
            pathlib.Path(output_root) / "agents-sdk-sidecar-readiness.json",
            {
                "schema_version": 1,
                "report_kind": "ai_native_agents_sdk_sidecar_readiness",
                "status": "pass",
                "mode": "managed-http",
                "checks": {
                    "tool_powers_declared": True,
                    "no_direct_world_mutation_tools": True,
                },
                "health": {
                    "status": "degraded",
                    "agents_sdk_available": False,
                    "openai_api_key_present": False,
                    "world_mutation_authority": "luanti",
                    "tool_powers": tool_powers,
                },
                "response": {
                    "web_search_available": False,
                    "world_mutation_authority": "luanti",
                    "tool_powers": tool_powers,
                },
            },
        )

    def test_harness_writes_public_safe_comparison_report_with_required_dimensions(self):
        self.assertTrue(CLI.is_file(), f"missing {CLI}")
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            self.write_accepted_baseline(output_root)
            report_path = pathlib.Path(tmpdir) / "minecraft-parity.json"

            completed = self.run_harness(output_root, "--output", str(report_path))

            self.assertIn("minecraft-parity.json", completed.stdout)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["schema_version"], 1)
            self.assertEqual(report["runner_version"], "ai-native-minecraft-parity-harness:v1")
            self.assertEqual(report["overall_status"], "minecraft-parity-report-ready")
            self.assertFalse(report["source_policy"]["uses_proprietary_minecraft_code_or_assets"])
            self.assertFalse(report["source_policy"]["uses_copied_server_jars_or_game_data"])
            self.assertTrue(report["source_policy"]["measured_facts_are_separate_from_project_targets"])
            self.assertTrue(report["accepted_baseline_policy"]["same_hardware_required"])
            self.assertTrue(
                report["accepted_baseline_policy"]["missing_or_mismatched_baselines_fail_report"]
            )
            self.assertEqual(
                report["accepted_baseline_policy"]["accepted_lanes_required"],
                ["local/benchmarks/local-mac/accepted/"],
            )
            self.assertEqual(
                report["retention"]["logical_default_output"],
                "local/benchmarks/minecraft-parity-comparison-report.json",
            )

            dimension_ids = [item["id"] for item in report["comparison_dimensions"]]
            self.assertEqual(
                dimension_ids,
                [
                    "startup",
                    "player_join_liveness",
                    "server_step_stability",
                    "mapblock_chunk_churn",
                    "entity_load",
                    "world_edit_throughput",
                    "persistence",
                    "mod_plugin_ergonomics",
                    "agent_tool_powers",
                    "operator_visibility",
                    "recovery",
                    "memory",
                    "cpu",
                    "latency",
                ],
            )
            self.assertEqual(set(report["target_bands"]), set(dimension_ids))
            for dimension in report["comparison_dimensions"]:
                self.assertIn(
                    dimension["gap_area"],
                    {
                        "engine_runtime",
                        "game_content",
                        "first_party_plugin",
                        "operator_experience",
                    },
                )
                self.assertEqual(
                    set(dimension["scorecard_criteria"]),
                    {"pass", "warn", "fail"},
                )
                self.assertEqual(
                    dimension["target_band"],
                    report["target_bands"][dimension["id"]],
                )
            self.assertEqual(
                report["scorecard_status_criteria"],
                {
                    "pass": "Measured evidence meets the current project target for this dimension.",
                    "warn": "Evidence is partial, proxy-only, or below the target but still safe and informative.",
                    "fail": "Evidence is missing, failing, private, unsafe, or not yet reproducible.",
                },
            )
            scenario_ids = [item["id"] for item in report["benchmark_scenarios"]]
            self.assertEqual(
                scenario_ids,
                [
                    "clean_profile_startup",
                    "server_step_liveness",
                    "headless_player_join",
                    "synthetic_mapblock_churn",
                    "generic_entity_scale",
                    "rollback_backed_world_edit",
                    "agents_sdk_tool_power_probe",
                    "operator_status_and_task_control",
                ],
            )
            for scenario in report["benchmark_scenarios"]:
                self.assertTrue(scenario["safe_for_local"])
                self.assertTrue(scenario["safe_for_side_by_side_pi"])
                self.assertFalse(scenario["requires_private_world"])
                self.assertFalse(scenario["uses_proprietary_minecraft_assets"])
            lane = report["measured_facts"][0]
            results = {item["dimension_id"]: item for item in lane["dimension_results"]}
            for result in results.values():
                self.assertIn("target_band", result)
                self.assertIn("target_band_passed", result["metrics"])
            self.assertEqual(results["startup"]["status"], "measured")
            self.assertEqual(results["startup"]["scorecard_status"], "pass")
            self.assertEqual(results["player_join_liveness"]["status"], "proxy_only")
            self.assertEqual(results["player_join_liveness"]["scorecard_status"], "warn")
            self.assertEqual(results["server_step_stability"]["status"], "measured")
            self.assertEqual(results["mapblock_chunk_churn"]["status"], "evidence_gap")
            self.assertEqual(results["mapblock_chunk_churn"]["scorecard_status"], "fail")
            self.assertEqual(results["entity_load"]["status"], "partial")
            self.assertEqual(results["entity_load"]["scorecard_status"], "warn")
            self.assertEqual(results["world_edit_throughput"]["status"], "evidence_gap")
            self.assertEqual(results["persistence"]["status"], "measured")
            self.assertEqual(results["mod_plugin_ergonomics"]["status"], "partial")
            self.assertFalse(
                results["mod_plugin_ergonomics"]["metrics"]["first_party_agent_loop_ready"]
            )
            self.assertFalse(
                results["mod_plugin_ergonomics"]["metrics"]["compatibility_import_plugin_ready"]
            )
            self.assertEqual(results["agent_tool_powers"]["status"], "evidence_gap")
            self.assertEqual(results["agent_tool_powers"]["scorecard_status"], "fail")
            self.assertFalse(
                results["agent_tool_powers"]["metrics"]["tool_powers_declared"]
            )
            self.assertEqual(results["operator_visibility"]["status"], "measured")
            self.assertEqual(results["recovery"]["status"], "measured")
            self.assertEqual(results["memory"]["status"], "measured")
            self.assertEqual(results["cpu"]["status"], "evidence_gap")
            self.assertEqual(results["latency"]["status"], "proxy_only")

            gap_ids = {item["dimension_id"] for item in report["qualitative_minecraft_parity_gaps"]}
            self.assertIn("player_join_liveness", gap_ids)
            self.assertIn("mapblock_chunk_churn", gap_ids)
            self.assertIn("entity_load", gap_ids)
            self.assertIn("world_edit_throughput", gap_ids)
            self.assertIn("mod_plugin_ergonomics", gap_ids)
            self.assertIn("agent_tool_powers", gap_ids)
            self.assertIn("cpu", gap_ids)
            self.assertIn("latency", gap_ids)
            self.assertEqual(
                set(report["gap_summary_by_area"]),
                {
                    "engine_runtime",
                    "game_content",
                    "first_party_plugin",
                    "operator_experience",
                },
            )
            for gap in report["qualitative_minecraft_parity_gaps"]:
                self.assertIn("gap_area", gap)
                self.assertIn("scorecard_status", gap)
            self.assertIn("actionable_scorecard", report)
            self.assertGreater(len(report["actionable_scorecard"]), 0)
            first_action = report["actionable_scorecard"][0]
            self.assertEqual(first_action["rank"], 1)
            self.assertIn("action_id", first_action)
            self.assertIn(first_action["scorecard_status"], {"fail", "warn"})
            self.assertIn("hardware_classes", first_action)
            self.assertIn("dimension_ids", first_action)
            self.assertIn("next_action", first_action)
            self.assertIn("suggested_issue_title", first_action)
            self.assertTrue(first_action["blocks_minecraft_parity"])
            self.assertEqual(
                len(report["ranked_improvement_targets"]),
                len(report["actionable_scorecard"]),
            )
            first_target = report["ranked_improvement_targets"][0]
            self.assertEqual(first_target["rank"], first_action["rank"])
            self.assertEqual(first_target["target_id"], first_action["action_id"])
            self.assertIn(
                first_target["priority"],
                {"critical", "high", "medium", "low"},
            )
            self.assertIn(
                first_target["owner_lane"],
                {
                    "engine_runtime_hardening",
                    "agent_plugin_and_import_productization",
                    "operator_control_plane",
                    "game_content_parity",
                },
            )
            self.assertEqual(first_target["dimension_ids"], first_action["dimension_ids"])
            self.assertEqual(first_target["current_evidence"], first_action["evidence"])
            self.assertEqual(first_target["next_action"], first_action["next_action"])
            self.assertIn("target_bands", first_target)
            self.assertIn("done_when", first_target)
            self.assertGreater(len(first_target["done_when"]), 0)
            self.assertEqual(
                report["improvement_target_summary"]["target_count"],
                len(report["ranked_improvement_targets"]),
            )
            self.assertIn("issue_seeds", report)
            self.assertEqual(len(report["issue_seeds"]), len(report["actionable_scorecard"]))
            first_seed = report["issue_seeds"][0]
            self.assertEqual(first_seed["issue_key"], first_action["action_id"])
            self.assertEqual(first_seed["title"], first_action["suggested_issue_title"])
            self.assertEqual(first_seed["rank"], first_action["rank"])
            self.assertEqual(first_seed["dimension_ids"], first_action["dimension_ids"])
            self.assertIn("minecraft-parity", first_seed["labels"])
            self.assertIn("benchmark", first_seed["labels"])
            self.assertIn("next_action", first_seed)
            self.assertIn("acceptance", first_seed)
            self.assertGreater(len(first_seed["acceptance"]), 0)
            self.assertEqual(
                first_seed["created_from"]["report"],
                "local/benchmarks/minecraft-parity-comparison-report.json",
            )
            self.assertFalse(first_seed["public_safety"]["requires_private_world"])
            self.assertFalse(first_seed["public_safety"]["requires_private_assets"])
            self.assertFalse(
                first_seed["public_safety"]["uses_proprietary_minecraft_assets"]
            )
            self.assertFalse(
                first_seed["public_safety"]["uses_copied_server_jars_or_game_data"]
            )
            self.assertTrue(
                first_seed["public_safety"]["dry_run_or_synthetic_evidence_only"]
            )
            self.assertEqual(
                report["issue_seed_summary"]["issue_seed_count"],
                len(report["issue_seeds"]),
            )
            serialized = json.dumps(report, sort_keys=True)
            self.assertNotIn(str(output_root), serialized)
            self.assertNotRegex(serialized, PRIVATE_PATTERNS)

    def test_harness_clears_measured_runtime_gaps_when_accepted_baseline_has_evidence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            self.write_accepted_baseline(
                output_root,
                headless_players=True,
                mapblock_rows=256,
                entity_count=16,
                total_node_writes=11,
                cpu_evidence=True,
            )
            self.write_agent_tool_power_readiness_report(output_root)
            report_path = pathlib.Path(tmpdir) / "minecraft-parity.json"

            self.run_harness(output_root, "--output", str(report_path))

            report = json.loads(report_path.read_text(encoding="utf-8"))
            results = {
                item["dimension_id"]: item
                for item in report["measured_facts"][0]["dimension_results"]
            }
            self.assertEqual(results["player_join_liveness"]["status"], "measured")
            self.assertEqual(results["mapblock_chunk_churn"]["status"], "measured")
            self.assertEqual(results["entity_load"]["status"], "measured")
            self.assertEqual(results["world_edit_throughput"]["status"], "measured")
            self.assertEqual(results["persistence"]["status"], "measured")
            self.assertEqual(results["operator_visibility"]["status"], "measured")
            self.assertEqual(results["recovery"]["status"], "measured")
            self.assertEqual(results["cpu"]["status"], "measured")
            self.assertEqual(results["cpu"]["metrics"]["avg_process_cpu_percent"], 4.0)
            self.assertEqual(results["latency"]["status"], "measured")
            self.assertEqual(
                results["latency"]["metrics"]["latency_probe_kind"],
                "headless_join_log_observation",
            )
            self.assertEqual(
                results["latency"]["metrics"]["join_latency_proxy_ms"]["p95"],
                120.0,
            )
            gap_ids = {item["dimension_id"] for item in report["qualitative_minecraft_parity_gaps"]}
            self.assertNotIn("player_join_liveness", gap_ids)
            self.assertNotIn("mapblock_chunk_churn", gap_ids)
            self.assertNotIn("entity_load", gap_ids)
            self.assertNotIn("world_edit_throughput", gap_ids)
            self.assertNotIn("cpu", gap_ids)
            self.assertNotIn("latency", gap_ids)
            self.assertEqual(len(report["actionable_scorecard"]), 2)
            self.assertEqual(
                sorted(item["title"] for item in report["actionable_scorecard"]),
                [
                    "Build compatibility import inventory discovery",
                    "Prove first-party agent scale gate in accepted lanes",
                ],
            )

    def test_harness_flags_measured_metrics_outside_target_band_as_ranked_gap(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            self.write_accepted_baseline(
                output_root,
                headless_players=True,
                mapblock_rows=256,
                entity_count=16,
                total_node_writes=11,
                cpu_evidence=True,
                first_party_loop=True,
            )
            self.write_import_inventory_discovery_report(output_root)
            self.write_agent_tool_power_readiness_report(output_root)
            clean_profile_path = (
                output_root / "local-mac" / "accepted" / "clean-profile-benchmark-summary.json"
            )
            clean_profile = json.loads(clean_profile_path.read_text(encoding="utf-8"))
            clean_profile["comparison_summary"]["startup"]["time_to_listen_ms"] = 20000.0
            self.write_json(clean_profile_path, clean_profile)
            report_path = pathlib.Path(tmpdir) / "minecraft-parity.json"

            self.run_harness(output_root, "--output", str(report_path))

            report = json.loads(report_path.read_text(encoding="utf-8"))
            results = {
                item["dimension_id"]: item
                for item in report["measured_facts"][0]["dimension_results"]
            }
            startup = results["startup"]
            self.assertEqual(startup["status"], "partial")
            self.assertEqual(startup["scorecard_status"], "warn")
            self.assertFalse(startup["metrics"]["target_band_passed"])
            self.assertEqual(startup["target_band"]["time_to_listen_ms_max"], 15000)
            actions = report["actionable_scorecard"]
            self.assertEqual(len(actions), 1)
            self.assertEqual(actions[0]["dimension_ids"], ["startup"])
            self.assertEqual(actions[0]["title"], "Startup target band is not met")

    def test_harness_rejects_mismatched_same_hardware_baseline(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            self.write_accepted_baseline(output_root)
            manifest_path = (
                output_root / "local-mac" / "accepted" / "accepted-baseline-manifest.json"
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["hardware_class"] = "low-power-server"
            self.write_json(manifest_path, manifest)

            completed = self.run_harness(output_root, check=False)

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("accepted baseline hardware class mismatch", completed.stderr)

    def test_harness_clears_first_party_loop_gap_when_accepted_baseline_has_product_loop_evidence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            self.write_accepted_baseline(
                output_root,
                headless_players=True,
                mapblock_rows=256,
                entity_count=16,
                total_node_writes=11,
                cpu_evidence=True,
                first_party_loop=True,
            )
            self.write_agent_tool_power_readiness_report(output_root)
            report_path = pathlib.Path(tmpdir) / "minecraft-parity.json"
            completed = self.run_harness(output_root, "--output", str(report_path))
            self.assertEqual(completed.returncode, 0, completed.stderr)

            report = json.loads(report_path.read_text(encoding="utf-8"))
            lane = report["measured_facts"][0]
            results = {item["dimension_id"]: item for item in lane["dimension_results"]}
            self.assertTrue(
                results["mod_plugin_ergonomics"]["metrics"]["first_party_agent_loop_ready"]
            )
            self.assertFalse(
                results["mod_plugin_ergonomics"]["metrics"]["compatibility_import_plugin_ready"]
            )
            self.assertEqual(len(report["actionable_scorecard"]), 1)
            self.assertEqual(
                report["actionable_scorecard"][0]["title"],
                "Build compatibility import inventory discovery",
            )

    def test_harness_clears_import_inventory_gap_when_discovery_report_is_ready(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            self.write_accepted_baseline(
                output_root,
                headless_players=True,
                mapblock_rows=256,
                entity_count=16,
                total_node_writes=11,
                cpu_evidence=True,
                first_party_loop=True,
            )
            self.write_import_inventory_discovery_report(output_root)
            self.write_agent_tool_power_readiness_report(output_root)
            report_path = pathlib.Path(tmpdir) / "minecraft-parity.json"

            self.run_harness(output_root, "--output", str(report_path))

            report = json.loads(report_path.read_text(encoding="utf-8"))
            results = {
                item["dimension_id"]: item
                for item in report["measured_facts"][0]["dimension_results"]
            }
            plugin = results["mod_plugin_ergonomics"]
            self.assertTrue(plugin["metrics"]["first_party_agent_loop_ready"])
            self.assertTrue(plugin["metrics"]["compatibility_import_plugin_ready"])
            self.assertEqual(
                plugin["metrics"]["compatibility_import_inventory"]["status"],
                "ready_for_import_preview",
            )
            self.assertEqual(results["agent_tool_powers"]["status"], "measured")
            self.assertTrue(results["agent_tool_powers"]["metrics"]["target_band_passed"])
            self.assertEqual(report["actionable_scorecard"], [])
            self.assertEqual(report["ranked_improvement_targets"], [])
            self.assertEqual(report["improvement_target_summary"]["target_count"], 0)
            self.assertEqual(report["improvement_target_summary"]["scorecard_status"], "pass")
            self.assertEqual(report["issue_seeds"], [])
            self.assertEqual(report["issue_seed_summary"]["issue_seed_count"], 0)
            self.assertEqual(report["issue_seed_summary"]["scorecard_status"], "pass")
            self.assertEqual(
                report["gap_summary_by_area"]["first_party_plugin"]["scorecard_status"],
                "pass",
            )

    def test_harness_marks_partial_headless_evidence_as_measured_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            self.write_accepted_baseline(
                output_root,
                headless_players=True,
                mapblock_rows=256,
                entity_count=16,
                total_node_writes=11,
                cpu_evidence=True,
            )
            clean_profile_path = (
                output_root / "local-mac" / "accepted" / "clean-profile-benchmark-summary.json"
            )
            clean_profile = json.loads(clean_profile_path.read_text(encoding="utf-8"))
            probe = clean_profile["comparison_summary"]["player_load_tick_probe"]
            probe.update(
                {
                    "probe_status": "partial",
                    "synthetic_player_count": 1,
                    "connected_synthetic_player_count": 1,
                    "completed_synthetic_player_count": 1,
                    "client_exit_statuses": [0, 7],
                    "join_latency_proxy_ms": {
                        "sample_count": 1,
                        "min": 80.0,
                        "p50": 80.0,
                        "p95": 80.0,
                        "max": 80.0,
                        "avg": 80.0,
                    },
                }
            )
            self.write_json(clean_profile_path, clean_profile)
            report_path = pathlib.Path(tmpdir) / "minecraft-parity.json"

            self.run_harness(output_root, "--output", str(report_path))

            report = json.loads(report_path.read_text(encoding="utf-8"))
            results = {
                item["dimension_id"]: item
                for item in report["measured_facts"][0]["dimension_results"]
            }
            self.assertEqual(results["player_join_liveness"]["status"], "measured_failure")
            self.assertEqual(results["latency"]["status"], "measured_failure")
            gaps = {
                item["dimension_id"]: item
                for item in report["qualitative_minecraft_parity_gaps"]
            }
            self.assertIn("Fix failing synthetic player join evidence", gaps["player_join_liveness"]["title"])
            self.assertIn("Fix failing headless latency evidence", gaps["latency"]["title"])

    def test_issue_seeds_group_same_gap_across_hardware_lanes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            for hardware_class in ("local-mac", "low-power-server"):
                self.write_accepted_baseline(
                    output_root,
                    hardware_class=hardware_class,
                    headless_players=True,
                    mapblock_rows=256,
                    entity_count=16,
                    total_node_writes=11,
                    cpu_evidence=True,
                )
            self.write_agent_tool_power_readiness_report(output_root)
            report_path = pathlib.Path(tmpdir) / "minecraft-parity.json"

            self.run_harness(
                output_root,
                "--hardware-class",
                "local-mac",
                "--hardware-class",
                "low-power-server",
                "--output",
                str(report_path),
            )

            report = json.loads(report_path.read_text(encoding="utf-8"))
            scale_gate_seeds = [
                seed
                for seed in report["issue_seeds"]
                if seed["title"] == "Parity: Prove first-party agent scale gate in accepted lanes"
            ]
            self.assertEqual(len(scale_gate_seeds), 1)
            seed = scale_gate_seeds[0]
            self.assertEqual(seed["hardware_classes"], ["local-mac", "low-power-server"])
            self.assertEqual(seed["dimension_ids"], ["mod_plugin_ergonomics"])
            self.assertIn("gap-area:first-party-plugin", seed["labels"])
            self.assertIn("dimension:mod-plugin-ergonomics", seed["labels"])
            self.assertIn("status:fail", seed["labels"])
            self.assertGreaterEqual(len(seed["acceptance"]), 5)
            self.assertIn("mod_plugin_ergonomics", "\n".join(seed["acceptance"]))
            self.assertEqual(
                report["issue_seed_summary"]["by_hardware_class"]["local-mac"],
                len(report["issue_seeds"]),
            )
            self.assertEqual(
                report["issue_seed_summary"]["by_hardware_class"]["low-power-server"],
                len(report["issue_seeds"]),
            )

    def test_actionable_scorecard_groups_same_gap_across_hardware_lanes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            for hardware_class in ("local-mac", "low-power-server"):
                self.write_accepted_baseline(
                    output_root,
                    hardware_class=hardware_class,
                    headless_players=True,
                    mapblock_rows=256,
                    entity_count=16,
                    total_node_writes=11,
                    cpu_evidence=True,
                )
            self.write_agent_tool_power_readiness_report(output_root)
            report_path = pathlib.Path(tmpdir) / "minecraft-parity.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(CLI),
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

            report = json.loads(report_path.read_text(encoding="utf-8"))
            plugin_actions = [
                item for item in report["actionable_scorecard"]
                if item["dimension_ids"] == ["mod_plugin_ergonomics"]
            ]
            self.assertEqual(len(plugin_actions), 2)
            for action in plugin_actions:
                self.assertEqual(
                    action["hardware_classes"],
                    ["local-mac", "low-power-server"],
                )
                self.assertEqual(action["gap_count"], 2)

    def test_docs_explain_public_safe_harness_and_retention(self):
        for doc in (DOC, README):
            self.assertTrue(doc.is_file(), f"missing {doc}")
        combined = "\n".join(path.read_text(encoding="utf-8") for path in (DOC, README))
        for phrase in (
            "util/ai_native_minecraft_parity_harness.py",
            "minecraft-parity-comparison-report.json",
            "startup",
            "player join/liveness",
            "server-step stability",
            "mapblock/chunk churn",
            "entity load",
            "world-edit throughput",
            "persistence",
            "mod/plugin ergonomics",
            "agent tool powers",
            "tool_powers",
            "Agents SDK sidecar readiness report",
            "operator visibility",
            "recovery",
            "memory",
            "CPU",
            "latency",
            "pass/warn/fail",
            "engine/runtime gaps",
            "game-content or plugin gaps",
            "safe to run locally and on the Pi side-by-side service",
            "measured facts",
            "qualitative Minecraft-parity gaps",
            "ranked improvement targets",
            "issue_seeds",
            "issue_seed_summary",
            "follow-up issue seeds",
            "proprietary Minecraft code or assets",
            "operator-supplied external references",
            "local/benchmarks",
        ):
            self.assertIn(phrase, combined)
        self.assertNotRegex(combined, PRIVATE_PATTERNS)


if __name__ == "__main__":
    unittest.main()
