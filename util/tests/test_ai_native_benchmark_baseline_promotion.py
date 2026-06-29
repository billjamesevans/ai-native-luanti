import json
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
CAPTURE_CLI = ROOT / "util" / "ai_native_benchmark_capture.py"
PROMOTE_CLI = ROOT / "util" / "ai_native_benchmark_promote.py"
DOC = ROOT / "doc" / "ai-native-runtime" / "benchmark-baseline-retention.md"

PRIVATE_PATTERNS = re.compile(
    r"minecraftpi|192\.168|spacebase|themepark|showcase100|disneyland100|"
    r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY|private_prompt|asset_payload",
    re.I,
)


class BenchmarkBaselinePromotionTests(unittest.TestCase):
    def capture(self, output_root, commit="test-commit"):
        completed = subprocess.run(
            [
                sys.executable,
                str(CAPTURE_CLI),
                "--output-root",
                str(output_root),
                "--hardware-class",
                "local-mac",
                "--date",
                "2026-06-27",
                "--luanti-commit",
                commit,
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return output_root / "local-mac" / "2026-06-27" / commit

    def promote(self, capture_dir, output_root, check=True):
        self.assertTrue(PROMOTE_CLI.is_file(), f"missing {PROMOTE_CLI}")
        completed = subprocess.run(
            [
                sys.executable,
                str(PROMOTE_CLI),
                "--capture-dir",
                str(capture_dir),
                "--output-root",
                str(output_root),
                "--source-label",
                "reviewed-clean",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if check:
            self.assertEqual(completed.returncode, 0, completed.stderr)
        return completed

    def clean_profile_payload(self, comparison_summary=None):
        summary = {
            "server_step_workload": {
                "workload_status": "pass",
                "workload_kind": "server_step_liveness",
                "attempted_sample_count": 3,
                "completed_sample_count": 3,
                "failed_sample_count": 0,
            },
            "player_load_tick_probe": {
                "probe_status": "pass",
                "probe_kind": "headless_client_load",
                "headless_player_supported": True,
                "synthetic_player_count": 2,
                "attempted_synthetic_player_count": 2,
                "connected_synthetic_player_count": 2,
                "completed_synthetic_player_count": 2,
                "client_launch_failure_count": 0,
                "cleanup_status": "complete",
                "latency_proxy_supported": True,
                "latency_probe_kind": "headless_join_log_observation",
                "join_latency_proxy_ms": {
                    "sample_count": 2,
                    "min": 100.0,
                    "p50": 100.0,
                    "p95": 100.0,
                    "max": 100.0,
                    "avg": 100.0,
                },
            },
            "map_chunk_workload": {
                "workload_status": "pass",
                "workload_kind": "synthetic_sqlite_mapblock_churn",
                "mapblock_rows": 4,
                "mapblock_rows_created": 4,
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
            "cpu": {
                "sample_status": "measured",
                "cpu_sample_count": 3,
                "process_cpu_time_delta_seconds": 0.03,
                "observed_wall_time_seconds": 0.3,
                "avg_process_cpu_percent": 10.0,
                "max_interval_cpu_percent": 15.0,
                "sample_methods": ["ps_time"],
                "limitations": [],
            },
        }
        if comparison_summary:
            summary.update(comparison_summary)
        return {
            "schema_version": 1,
            "runner_version": "ai-native-clean-profile-benchmark:v1",
            "luanti_commit": "test-commit",
            "hardware_class": "local-mac",
            "overall_status": "pass",
            "game_profile": {"gameid": "ai_runtime"},
            "run_context": {
                "requires_private_world": False,
                "requires_private_assets": False,
                "requires_live_pi": False,
                "requires_model_network": False,
            },
            "comparison_summary": summary,
            "failure_notes": [],
        }

    def add_clean_profile_capture(self, capture_dir, clean_profile=None):
        manifest_path = capture_dir / "benchmark-capture-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["game_profile"] = "ai_runtime"
        manifest["reports"]["clean_profile"] = "clean-profile-benchmark-summary.json"
        manifest["profile_statuses"] = {"clean_profile": "pass"}
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        (capture_dir / "clean-profile-benchmark-summary.json").write_text(
            json.dumps(clean_profile or self.clean_profile_payload()),
            encoding="utf-8",
        )

    def test_promotes_clean_capture_to_ignored_accepted_baseline(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            capture_dir = self.capture(output_root)

            self.promote(capture_dir, output_root)

            accepted_dir = output_root / "local-mac" / "accepted"
            manifest_path = accepted_dir / "accepted-baseline-manifest.json"
            self.assertTrue(manifest_path.is_file())
            self.assertTrue((accepted_dir / "mutation-benchmark-report.json").is_file())
            self.assertTrue((accepted_dir / "generic-demo-entity-benchmark-report.json").is_file())

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], 1)
            self.assertEqual(manifest["hardware_class"], "local-mac")
            self.assertEqual(manifest["luanti_commit"], "test-commit")
            self.assertEqual(manifest["source_label"], "reviewed-clean")
            self.assertEqual(
                manifest["source_capture"],
                "local/benchmarks/local-mac/2026-06-27/test-commit",
            )
            self.assertEqual(
                manifest["reports"]["mutation"],
                "mutation-benchmark-report.json",
            )
            self.assertEqual(
                manifest["reports"]["demo_entity"],
                "generic-demo-entity-benchmark-report.json",
            )

            serialized = json.dumps(manifest, sort_keys=True)
            self.assertNotIn(str(output_root), serialized)
            self.assertNotRegex(serialized, PRIVATE_PATTERNS)

        ignored = subprocess.run(
            [
                "git",
                "check-ignore",
                "-q",
                "local/benchmarks/local-mac/accepted/accepted-baseline-manifest.json",
            ],
            cwd=ROOT,
            check=False,
        )
        self.assertEqual(ignored.returncode, 0)

    def test_promoted_baseline_can_drive_future_capture_comparison(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            capture_dir = self.capture(output_root, commit="baseline-commit")
            self.promote(capture_dir, output_root)

            accepted_dir = output_root / "local-mac" / "accepted"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(CAPTURE_CLI),
                    "--output-root",
                    str(output_root),
                    "--hardware-class",
                    "local-mac",
                    "--date",
                    "2026-06-28",
                    "--luanti-commit",
                    "branch-commit",
                    "--mutation-baseline",
                    str(accepted_dir / "mutation-benchmark-report.json"),
                    "--demo-entity-baseline",
                    str(accepted_dir / "generic-demo-entity-benchmark-report.json"),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            branch_dir = output_root / "local-mac" / "2026-06-28" / "branch-commit"
            branch_manifest = json.loads(
                (branch_dir / "benchmark-capture-manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(branch_manifest["comparison_statuses"]["mutation"], "pass")
            self.assertEqual(branch_manifest["comparison_statuses"]["demo_entity"], "pass")

    def test_promotes_clean_profile_summary_when_capture_contains_it(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            capture_dir = self.capture(output_root)
            self.add_clean_profile_capture(capture_dir)

            self.promote(capture_dir, output_root)

            accepted_dir = output_root / "local-mac" / "accepted"
            accepted_manifest = json.loads(
                (accepted_dir / "accepted-baseline-manifest.json").read_text(encoding="utf-8")
            )
            self.assertTrue((accepted_dir / "clean-profile-benchmark-summary.json").is_file())
            self.assertEqual(
                accepted_manifest["reports"]["clean_profile"],
                "clean-profile-benchmark-summary.json",
            )

    def test_refuses_clean_profile_without_passing_workload_evidence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            capture_dir = self.capture(output_root)
            clean_profile = self.clean_profile_payload(comparison_summary={})
            clean_profile["comparison_summary"] = {}
            self.add_clean_profile_capture(capture_dir, clean_profile)

            completed = self.promote(capture_dir, output_root, check=False)

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("server_step_workload missing", completed.stderr)

            clean_profile["comparison_summary"]["server_step_workload"] = {
                "workload_status": "fail",
                "workload_kind": "server_step_liveness",
                "attempted_sample_count": 2,
                "completed_sample_count": 1,
                "failed_sample_count": 1,
            }
            (capture_dir / "clean-profile-benchmark-summary.json").write_text(
                json.dumps(clean_profile),
                encoding="utf-8",
            )

            completed = self.promote(capture_dir, output_root, check=False)

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("server_step_workload status must be pass", completed.stderr)

    def test_refuses_clean_profile_without_headless_latency_and_mapblock_evidence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            capture_dir = self.capture(output_root)
            clean_profile = self.clean_profile_payload()
            clean_profile["comparison_summary"]["player_load_tick_probe"] = {
                "probe_status": "pass",
                "probe_kind": "server_process_liveness",
                "headless_player_supported": False,
                "synthetic_player_count": 0,
            }
            clean_profile["comparison_summary"]["map_chunk_workload"] = {
                "workload_status": "pass",
                "workload_kind": "synthetic_sqlite_mapblock_churn",
                "mapblock_rows": 0,
                "mapblock_rows_created": 0,
            }
            self.add_clean_profile_capture(capture_dir, clean_profile)

            completed = self.promote(capture_dir, output_root, check=False)

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("player_load_tick_probe kind must be headless_client_load", completed.stderr)
            self.assertIn("headless_player_supported must be true", completed.stderr)
            self.assertIn("latency_proxy_supported must be true", completed.stderr)
            self.assertIn("join_latency_proxy_ms.sample_count must be positive", completed.stderr)
            self.assertIn("mapblock_rows_created must be positive", completed.stderr)

    def test_refuses_clean_profile_without_cpu_evidence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            capture_dir = self.capture(output_root)
            clean_profile = self.clean_profile_payload()
            del clean_profile["comparison_summary"]["cpu"]
            self.add_clean_profile_capture(capture_dir, clean_profile)

            completed = self.promote(capture_dir, output_root, check=False)

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("cpu missing", completed.stderr)

            clean_profile["comparison_summary"]["cpu"] = {
                "sample_status": "not_measured",
                "cpu_sample_count": 1,
                "avg_process_cpu_percent": None,
                "max_interval_cpu_percent": None,
            }
            self.add_clean_profile_capture(capture_dir, clean_profile)

            completed = self.promote(capture_dir, output_root, check=False)

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("cpu sample_status must be measured", completed.stderr)
            self.assertIn("cpu_sample_count must be at least 2", completed.stderr)

    def test_refuses_clean_profile_without_first_party_product_loop_evidence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            capture_dir = self.capture(output_root)
            clean_profile = self.clean_profile_payload()
            del clean_profile["comparison_summary"]["first_party_agent_product_loop"]
            self.add_clean_profile_capture(capture_dir, clean_profile)

            completed = self.promote(capture_dir, output_root, check=False)

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("first_party_agent_product_loop missing", completed.stderr)

            clean_profile = self.clean_profile_payload(
                comparison_summary={
                    "first_party_agent_product_loop": {
                        "product_loop_status": "evidence_gap",
                        "scenario_id": "first_party_agent_product_loop_approval",
                        "approval_plan_count": 1,
                        "approved_task_count": 1,
                        "guide_command_checked": 1,
                        "tasks_command_checked": 1,
                        "cancel_command_checked": 1,
                        "audit_review_checked": 1,
                        "rollback_review_checked": 1,
                        "defender_command_checked": 1,
                        "import_preview_checked": 1,
                        "blocked_or_unsafe_outcomes": 1,
                        "queued_task_count": 1,
                        "completed_task_count": 1,
                        "rollback_records": 1,
                        "warning_count": 0,
                        "error_count": 0,
                    },
                }
            )
            self.add_clean_profile_capture(capture_dir, clean_profile)

            completed = self.promote(capture_dir, output_root, check=False)

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("first_party_agent_product_loop status must be pass", completed.stderr)
            self.assertIn("approval_plan_count must be at least 2", completed.stderr)
            self.assertIn("approved_task_count must be at least 2", completed.stderr)
            self.assertIn("blocked_or_unsafe_outcomes must be 0", completed.stderr)
            self.assertIn("queued_task_count must be at least 2", completed.stderr)
            self.assertIn("completed_task_count must be at least 2", completed.stderr)
            self.assertIn("rollback_records must be at least 2", completed.stderr)

    def test_refuses_private_or_warning_reports(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            capture_dir = self.capture(output_root)
            mutation_report = capture_dir / "mutation-benchmark-report.json"
            payload = json.loads(mutation_report.read_text(encoding="utf-8"))
            payload["run_context"]["requires_private_world"] = True
            payload["scenarios"][0]["metrics"]["warnings"] = ["review this before accepting"]
            mutation_report.write_text(json.dumps(payload), encoding="utf-8")

            completed = self.promote(capture_dir, output_root, check=False)

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("requires_private_world", completed.stderr)
            self.assertIn("warnings", completed.stderr)
            self.assertFalse((output_root / "local-mac" / "accepted").exists())

    def test_docs_explain_promotion_loop(self):
        body = DOC.read_text(encoding="utf-8")
        for phrase in (
            "util/ai_native_benchmark_promote.py",
            "accepted-baseline-manifest.json",
            "local/benchmarks/<hardware-class>/accepted/",
            "reviewed clean capture",
            "same-hardware baseline",
            "must not promote",
            "warnings",
            "errors",
            "requires_private_world",
            "requires_live_pi",
            "clean-profile-benchmark-summary.json",
            "first_party_agent_product_loop",
            "backup-first",
        ):
            self.assertIn(phrase, body)
        self.assertNotRegex(body, PRIVATE_PATTERNS)


if __name__ == "__main__":
    unittest.main()
