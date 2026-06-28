import json
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
CLI = ROOT / "util" / "ai_native_runtime_gap_scorecard.py"
DOC = ROOT / "doc" / "ai-native-runtime" / "benchmark-baseline-retention.md"
README = ROOT / "doc" / "ai-native-runtime" / "README.md"

PRIVATE_PATTERNS = re.compile(
    r"minecraftpi|192\.168|spacebase|themepark|showcase100|disneyland100|"
    r"sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY|private_prompt|asset_payload|/Users/|/opt/|bill@",
    re.I,
)


class RuntimeGapScorecardTests(unittest.TestCase):
    def write_json(self, path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def write_accepted_baseline(
        self,
        output_root,
        hardware_class,
        *,
        startup_ms=200.0,
        max_rss_kb=28000,
        mapblock_rows=0,
        warning_count=1,
        failure_notes=None,
        include_clean_profile=True,
        include_player_probe=False,
    ):
        accepted = pathlib.Path(output_root) / hardware_class / "accepted"
        reports = {
            "mutation": "mutation-benchmark-report.json",
            "demo_entity": "generic-demo-entity-benchmark-report.json",
        }
        if include_clean_profile:
            reports["clean_profile"] = "clean-profile-benchmark-summary.json"

        self.write_json(
            accepted / "accepted-baseline-manifest.json",
            {
                "schema_version": 1,
                "generated_at": "2026-06-28T00:00:00Z",
                "luanti_commit": f"{hardware_class}-commit",
                "hardware_class": hardware_class,
                "game_profile": "ai_runtime" if include_clean_profile else "sample-synthetic",
                "source_label": f"reviewed-{hardware_class}",
                "source_capture": f"local/benchmarks/{hardware_class}/2026-06-28/example",
                "reports": reports,
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
                            "node_writes_per_step": 8,
                            "rollback_records": 1,
                            "warnings": [],
                            "errors": [],
                        },
                    },
                    {
                        "scenario_id": "repair_mutation_rollback",
                        "metrics": {
                            "node_writes_per_step": 4,
                            "rollback_records": 1,
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
                        "scenario_id": "movement_patrol",
                        "metrics": {
                            "entity_count": 4,
                            "active_peak": 4,
                            "remaining_entities": 0,
                            "warnings": [],
                            "errors": [],
                        },
                    }
                ],
            },
        )
        if include_clean_profile:
            self.write_json(
                accepted / "clean-profile-benchmark-summary.json",
                {
                    "schema_version": 1,
                    "runner_version": "ai-native-clean-profile-benchmark:v1",
                    "generated_at": "2026-06-28T00:00:00Z",
                    "luanti_commit": f"{hardware_class}-commit",
                    "hardware_class": hardware_class,
                    "overall_status": "pass" if not failure_notes else "fail",
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
                            "listening": not failure_notes,
                            "time_to_listen_ms": startup_ms,
                            "startup_timeout_seconds": 15.0,
                        },
                        "steady_tick_behavior": {
                            "sample_seconds": 3.0,
                            "observed_uptime_seconds": 3.5,
                            "process_exited_unexpectedly": False,
                            "server_log_warning_count": warning_count,
                            "server_log_error_count": 0,
                            "note": "Idle clean-profile server sample; player-load tick probes remain follow-on work.",
                        },
                        "map_chunk_workload": {
                            "world_backend": "sqlite3",
                            "map_sqlite_bytes": 12288,
                            "mapblock_rows": mapblock_rows,
                            "inspection_status": "ok",
                        },
                        "entity_runtime_operations": {
                            "scenario_count": 1,
                            "max_entity_count": 4,
                            "max_active_peak": 4,
                            "max_remaining_entities": 0,
                            "warnings": 0,
                            "errors": 0,
                        },
                        "mutation_write_throughput": {
                            "scenario_count": 2,
                            "total_node_writes": 0,
                            "max_node_writes_per_step": 8,
                            "total_rollback_records": 2,
                            "warnings": 0,
                            "errors": 0,
                        },
                        "memory": {
                            "max_rss_kb": max_rss_kb,
                            "rss_sample_count": 30,
                        },
                        "failure_notes": failure_notes or [],
                    },
                    "failure_notes": failure_notes or [],
                },
            )
            if include_player_probe:
                clean_profile_path = accepted / "clean-profile-benchmark-summary.json"
                clean_profile = json.loads(clean_profile_path.read_text(encoding="utf-8"))
                clean_profile["comparison_summary"]["player_load_tick_probe"] = {
                    "probe_status": "pass",
                    "probe_kind": "server_process_liveness",
                    "probe_duration_seconds": 3.0,
                    "sample_count": 30,
                    "synthetic_player_count": 0,
                    "headless_player_supported": False,
                    "server_stayed_listening": True,
                    "p95_sample_interval_ms": 100.0,
                    "max_sample_interval_ms": 120.0,
                    "server_log_warning_count": warning_count,
                    "server_log_error_count": 0,
                    "limitations": [
                        "No headless-player client load path is wired yet; this probe measures bounded server-process liveness."
                    ],
                }
                self.write_json(clean_profile_path, clean_profile)
        return accepted

    def run_scorecard(self, output_root, *extra_args, check=True):
        completed = subprocess.run(
            [
                sys.executable,
                str(CLI),
                "--output-root",
                str(output_root),
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

    def test_scorecard_reads_two_clean_profile_lanes_and_writes_public_safe_report(self):
        self.assertTrue(CLI.is_file(), f"missing {CLI}")
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            self.write_accepted_baseline(
                output_root,
                "local-mac",
                startup_ms=195.0,
                include_player_probe=True,
            )
            self.write_accepted_baseline(
                output_root,
                "low-power-server",
                startup_ms=62.0,
                max_rss_kb=24000,
                include_player_probe=True,
            )
            report_path = pathlib.Path(tmpdir) / "runtime-gap-scorecard.json"

            completed = self.run_scorecard(output_root, "--output", str(report_path))

            self.assertIn("runtime-gap-scorecard.json", completed.stdout)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["schema_version"], 1)
            self.assertEqual(report["runner_version"], "ai-native-runtime-gap-scorecard:v1")
            self.assertEqual(report["overall_status"], "gap-scorecard-ready")
            self.assertEqual(report["hardware_classes"], ["local-mac", "low-power-server"])
            self.assertFalse(report["run_context"]["requires_private_world"])
            self.assertFalse(report["run_context"]["requires_private_assets"])
            self.assertFalse(report["run_context"]["requires_live_pi"])
            self.assertFalse(report["run_context"]["requires_model_network"])

            evidence_by_hardware = {
                lane["hardware_class"]: lane for lane in report["measured_evidence"]
            }
            self.assertEqual(set(evidence_by_hardware), {"local-mac", "low-power-server"})
            for lane in evidence_by_hardware.values():
                for section in (
                    "startup",
                    "clean_profile_server_health",
                    "player_load_tick_probe",
                    "mutation_write_throughput",
                    "demo_entity_runtime_cost",
                    "map_chunk_workload",
                    "memory",
                    "failure_notes",
                ):
                    self.assertIn(section, lane["measurements"])
                self.assertEqual(lane["accepted_baseline"]["logical_dir"].split("/")[-1], "accepted")

            self.assertTrue(report["target_bands"])
            self.assertTrue(all(item["source"] == "project-target" for item in report["target_bands"]))
            self.assertNotIn("target_bands", report["measured_evidence"][0])

            gap_ids = [gap["id"] for gap in report["ranked_gaps"]]
            self.assertNotIn("player_load_tick_probe", gap_ids)
            self.assertIn("headless_player_load_probe", gap_ids)
            self.assertIn("non_empty_map_chunk_workload", gap_ids)
            self.assertIn("mutation_total_write_measurement", gap_ids)
            self.assertLess(
                gap_ids.index("headless_player_load_probe"),
                gap_ids.index("mutation_total_write_measurement"),
            )

            serialized = json.dumps(report, sort_keys=True)
            self.assertNotIn(str(output_root), serialized)
            self.assertNotRegex(serialized, PRIVATE_PATTERNS)

    def test_scorecard_refuses_missing_required_hardware_lane(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            self.write_accepted_baseline(output_root, "local-mac")

            completed = self.run_scorecard(output_root, check=False)

            self.assertEqual(completed.returncode, 2)
            self.assertIn("accepted baseline missing for low-power-server", completed.stderr)
            self.assertIn("ai_native_benchmark_promote.py", completed.stderr)

    def test_scorecard_refuses_incomplete_clean_profile_baseline(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            self.write_accepted_baseline(output_root, "local-mac")
            self.write_accepted_baseline(output_root, "low-power-server", include_clean_profile=False)

            completed = self.run_scorecard(output_root, check=False)

            self.assertEqual(completed.returncode, 2)
            self.assertIn("clean_profile report missing for low-power-server", completed.stderr)
            self.assertIn("clean-profile-benchmark-summary.json", completed.stderr)

    def test_scorecard_keeps_probe_gap_when_clean_profile_has_no_probe_section(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            self.write_accepted_baseline(output_root, "local-mac")
            self.write_accepted_baseline(output_root, "low-power-server")
            report_path = pathlib.Path(tmpdir) / "runtime-gap-scorecard.json"

            self.run_scorecard(output_root, "--output", str(report_path))

            report = json.loads(report_path.read_text(encoding="utf-8"))
            gap_ids = [gap["id"] for gap in report["ranked_gaps"]]
            self.assertIn("player_load_tick_probe", gap_ids)
            for lane in report["measured_evidence"]:
                probe = lane["measurements"]["player_load_tick_probe"]
                self.assertEqual(probe["probe_status"], "missing")
                self.assertIn("evidence_gap", probe)

    def test_docs_explain_scorecard_loop_and_privacy_boundary(self):
        for doc in (DOC, README):
            self.assertTrue(doc.is_file(), f"missing {doc}")
        combined = "\n".join(
            path.read_text(encoding="utf-8") for path in (DOC, README)
        )
        for phrase in (
            "util/ai_native_runtime_gap_scorecard.py",
            "runtime-gap-scorecard.json",
            "local/benchmarks/local-mac/accepted/",
            "local/benchmarks/low-power-server/accepted/",
            "clean-profile runtime gap scorecard",
            "player-load/server-step probe",
            "startup",
            "mutation throughput",
            "demo entity/runtime cost",
            "map/chunk workload",
            "memory",
            "failure notes",
            "Minecraft-parity target bands",
            "proprietary Minecraft code or assets",
            "headless-player",
            "privacy scan",
        ):
            self.assertIn(phrase, combined)
        self.assertNotRegex(combined, PRIVATE_PATTERNS)


if __name__ == "__main__":
    unittest.main()
