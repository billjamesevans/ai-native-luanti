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
    r"sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY|private_prompt|asset_payload|/Users/|/opt/|bill@",
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
                    "memory": {
                        "max_rss_kb": 28000,
                        "rss_sample_count": 30,
                    },
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
                    "memory",
                    "cpu",
                    "latency",
                ],
            )
            lane = report["measured_facts"][0]
            results = {item["dimension_id"]: item for item in lane["dimension_results"]}
            self.assertEqual(results["startup"]["status"], "measured")
            self.assertEqual(results["player_join_liveness"]["status"], "proxy_only")
            self.assertEqual(results["server_step_stability"]["status"], "measured")
            self.assertEqual(results["mapblock_chunk_churn"]["status"], "evidence_gap")
            self.assertEqual(results["entity_load"]["status"], "partial")
            self.assertEqual(results["world_edit_throughput"]["status"], "evidence_gap")
            self.assertEqual(results["memory"]["status"], "measured")
            self.assertEqual(results["cpu"]["status"], "evidence_gap")
            self.assertEqual(results["latency"]["status"], "proxy_only")

            gap_ids = {item["dimension_id"] for item in report["qualitative_minecraft_parity_gaps"]}
            self.assertIn("player_join_liveness", gap_ids)
            self.assertIn("mapblock_chunk_churn", gap_ids)
            self.assertIn("entity_load", gap_ids)
            self.assertIn("world_edit_throughput", gap_ids)
            self.assertIn("cpu", gap_ids)
            self.assertIn("latency", gap_ids)
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
            )
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
            gap_ids = {item["dimension_id"] for item in report["qualitative_minecraft_parity_gaps"]}
            self.assertNotIn("player_join_liveness", gap_ids)
            self.assertNotIn("mapblock_chunk_churn", gap_ids)
            self.assertNotIn("entity_load", gap_ids)
            self.assertNotIn("world_edit_throughput", gap_ids)
            self.assertIn("cpu", gap_ids)
            self.assertIn("latency", gap_ids)

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
            "memory",
            "CPU",
            "latency",
            "measured facts",
            "qualitative Minecraft-parity gaps",
            "proprietary Minecraft code or assets",
            "operator-supplied external references",
            "local/benchmarks",
        ):
            self.assertIn(phrase, combined)
        self.assertNotRegex(combined, PRIVATE_PATTERNS)


if __name__ == "__main__":
    unittest.main()
