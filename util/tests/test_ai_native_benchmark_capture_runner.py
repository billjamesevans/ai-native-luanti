import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
CLI = ROOT / "util" / "ai_native_benchmark_capture.py"
DOC = ROOT / "doc" / "ai-native-runtime" / "benchmark-baseline-retention.md"
sys.path.insert(0, str(ROOT / "util"))
import ai_native_benchmark_capture as benchmark_capture

PRIVATE_PATTERNS = re.compile(
    r"minecraftpi|192\.168|spacebase|themepark|showcase100|disneyland100|"
    r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY|private_prompt|asset_payload",
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

    def write_fake_profile_server(self, tmpdir, warning_line=None):
        server = pathlib.Path(tmpdir) / "fake_luantiserver.py"
        warning_literal = repr(warning_line)
        server.write_text(
            f"""#!/usr/bin/env python3
import pathlib
import signal
import sys
import time

warning_line = {warning_literal}
args = sys.argv[1:]
logfile = pathlib.Path(args[args.index("--logfile") + 1])
gameid = args[args.index("--gameid") + 1]
port = "30000"
config = pathlib.Path(args[args.index("--config") + 1])
for line in config.read_text(encoding="utf-8").splitlines():
    if line.startswith("port ="):
        port = line.split("=", 1)[1].strip()
logfile.parent.mkdir(parents=True, exist_ok=True)
lines = [
    f'2026-06-28 00:00:00: ACTION[Main]: Server for gameid="{{gameid}}" listening on [::]:{{port}}.\\n',
]
if warning_line:
    lines.append(warning_line + "\\n")
logfile.write_text("".join(lines), encoding="utf-8")
signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
while True:
    time.sleep(0.05)
""",
            encoding="utf-8",
        )
        os.chmod(server, 0o755)
        return server

    def write_fake_headless_player(self, tmpdir):
        client = pathlib.Path(tmpdir) / "fake_headless_player.py"
        client.write_text(
            """#!/usr/bin/env python3
import argparse
import pathlib
import sys
import time

parser = argparse.ArgumentParser()
parser.add_argument("--server-log", required=True)
parser.add_argument("--name", required=True)
parser.add_argument("--duration", type=float, default=0.02)
parser.add_argument("--fail-suffix")
args = parser.parse_args()

if args.fail_suffix and args.name.endswith(args.fail_suffix):
    sys.exit(7)

log_path = pathlib.Path(args.server_log)
with log_path.open("a", encoding="utf-8") as handle:
    handle.write(f'2026-06-28 00:00:01: ACTION[Server]: {args.name} joins game.\\n')
time.sleep(max(args.duration, 0.0))
sys.exit(0)
""",
            encoding="utf-8",
        )
        os.chmod(client, 0o755)
        return client

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

    def test_runner_writes_clean_profile_summary_for_ai_runtime(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            fake_server = self.write_fake_profile_server(tmpdir)

            completed, output, run_dir, manifest = self.run_capture(
                "--game-profile",
                "ai_runtime",
                "--server-bin",
                str(fake_server),
                "--profile-sample-seconds",
                "0.1",
                "--profile-startup-timeout",
                "2",
                output_root=output_root,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIsNotNone(manifest)
            self.assertEqual(manifest["runner_version"], "ai-native-benchmark-capture:v2")
            self.assertEqual(manifest["game_profile"], "ai_runtime")
            self.assertEqual(manifest["reports"]["clean_profile"], "clean-profile-benchmark-summary.json")

            summary_path = run_dir / manifest["reports"]["clean_profile"]
            self.assertTrue(summary_path.is_file())
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["runner_version"], "ai-native-clean-profile-benchmark:v1")
            self.assertEqual(summary["luanti_commit"], "test-commit")
            self.assertEqual(summary["hardware_class"], "local-mac")
            self.assertEqual(summary["game_profile"]["gameid"], "ai_runtime")
            self.assertEqual(summary["server_launch"]["gameid"], "ai_runtime")
            self.assertEqual(summary["overall_status"], "pass")
            self.assertEqual(summary["failure_notes"], [])
            self.assertEqual(
                summary["comparison_summary"]["mutation_write_throughput"]["unsafe_operations"],
                0,
            )
            for key in (
                "startup",
                "steady_tick_behavior",
                "server_step_workload",
                "player_load_tick_probe",
                "map_chunk_workload",
                "entity_runtime_operations",
                "mutation_write_throughput",
                "memory",
                "cpu",
                "failure_notes",
            ):
                self.assertIn(key, summary["comparison_summary"])
            probe = summary["comparison_summary"]["player_load_tick_probe"]
            self.assertEqual(probe["probe_status"], "pass")
            self.assertEqual(probe["probe_kind"], "server_process_liveness")
            self.assertEqual(probe["synthetic_player_count"], 0)
            self.assertFalse(probe["headless_player_supported"])
            self.assertFalse(probe["latency_proxy_supported"])
            self.assertEqual(probe["latency_probe_kind"], "not_measured")
            self.assertEqual(probe["join_latency_proxy_ms"]["sample_count"], 0)
            self.assertTrue(probe["server_stayed_listening"])
            self.assertGreaterEqual(probe["sample_count"], 1)
            self.assertIn("p95_sample_interval_ms", probe)
            self.assertIn("max_sample_interval_ms", probe)
            self.assertTrue(probe["limitations"])
            workload = summary["comparison_summary"]["server_step_workload"]
            self.assertEqual(workload["workload_status"], "pass")
            self.assertEqual(workload["workload_kind"], "server_step_liveness")
            self.assertGreaterEqual(workload["attempted_sample_count"], 1)
            self.assertGreaterEqual(workload["completed_sample_count"], 1)
            self.assertEqual(workload["failed_sample_count"], 0)
            self.assertIn("p95_sample_interval_ms", workload)
            self.assertIn("max_sample_interval_ms", workload)
            map_workload = summary["comparison_summary"]["map_chunk_workload"]
            self.assertEqual(map_workload["workload_status"], "pass")
            self.assertEqual(map_workload["workload_kind"], "synthetic_sqlite_mapblock_churn")
            self.assertTrue(map_workload["synthetic"])
            self.assertGreater(map_workload["mapblock_rows"], 0)
            self.assertEqual(map_workload["mapblock_rows_after"], map_workload["mapblock_rows"])
            self.assertGreater(map_workload["mapblock_rows_created"], 0)
            self.assertGreaterEqual(map_workload["map_sqlite_bytes_growth"], 0)
            self.assertGreaterEqual(map_workload["workload_duration_ms"], 0)
            self.assertEqual(map_workload["warning_count"], 0)
            self.assertEqual(map_workload["error_count"], 0)
            cpu = summary["comparison_summary"]["cpu"]
            self.assertIn(cpu["sample_status"], ("measured", "not_measured"))
            self.assertIn("cpu_sample_count", cpu)
            self.assertIn("process_cpu_time_delta_seconds", cpu)
            self.assertIn("avg_process_cpu_percent", cpu)
            self.assertIn("max_interval_cpu_percent", cpu)
            self.assertIn("sample_methods", cpu)

            serialized = json.dumps({"manifest": manifest, "summary": summary}, sort_keys=True)
            self.assertNotIn(str(output), serialized)
            self.assertNotRegex(serialized, PRIVATE_PATTERNS)

    def test_synthetic_mapblock_workload_adds_rows_when_spawn_blocks_exist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            world_dir = pathlib.Path(tmpdir) / "world"
            map_db = world_dir / "map.sqlite"
            map_db.parent.mkdir(parents=True)
            import sqlite3

            with sqlite3.connect(map_db) as conn:
                conn.execute(
                    "CREATE TABLE blocks ("
                    "x INTEGER, y INTEGER, z INTEGER, data BLOB NOT NULL, "
                    "PRIMARY KEY (x, z, y))"
                )
                for index in range(4):
                    conn.execute(
                        "INSERT INTO blocks (x, y, z, data) VALUES (?, ?, ?, ?)",
                        (index, 0, 0, b"preexisting-mapgen-row"),
                    )
                conn.commit()

            workload = benchmark_capture.run_synthetic_mapblock_workload(world_dir)

            self.assertEqual(workload["workload_status"], "pass")
            self.assertEqual(workload["mapblock_rows_before"], 4)
            self.assertEqual(workload["mapblock_rows_after"], 8)
            self.assertEqual(workload["mapblock_rows_created"], 4)
            self.assertEqual(workload["error_count"], 0)

    def test_runner_records_supported_headless_player_probe(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            fake_server = self.write_fake_profile_server(tmpdir)
            fake_client = self.write_fake_headless_player(tmpdir)

            completed, output, run_dir, manifest = self.run_capture(
                "--game-profile",
                "ai_runtime",
                "--server-bin",
                str(fake_server),
                "--profile-sample-seconds",
                "0.15",
                "--profile-startup-timeout",
                "2",
                "--headless-player-command",
                f"{sys.executable} {fake_client} --server-log {{server_log}} --name {{name}} --duration {{duration_seconds}}",
                "--headless-player-count",
                "2",
                output_root=output_root,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIsNotNone(manifest)
            summary_path = run_dir / manifest["reports"]["clean_profile"]
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["overall_status"], "pass")
            self.assertEqual(summary["failure_notes"], [])

            probe = summary["comparison_summary"]["player_load_tick_probe"]
            self.assertEqual(probe["probe_status"], "pass")
            self.assertEqual(probe["probe_kind"], "headless_client_load")
            self.assertTrue(probe["headless_player_supported"])
            self.assertEqual(probe["attempted_synthetic_player_count"], 2)
            self.assertEqual(probe["connected_synthetic_player_count"], 2)
            self.assertEqual(probe["synthetic_player_count"], 2)
            self.assertEqual(probe["completed_synthetic_player_count"], 2)
            self.assertEqual(probe["client_launch_failure_count"], 0)
            self.assertIn(probe["cleanup_status"], ("complete", "terminated"))
            self.assertTrue(probe["latency_proxy_supported"])
            self.assertEqual(probe["latency_probe_kind"], "headless_join_log_observation")
            latency = probe["join_latency_proxy_ms"]
            self.assertEqual(latency["sample_count"], 2)
            self.assertGreaterEqual(latency["min"], 0)
            self.assertGreaterEqual(latency["p50"], 0)
            self.assertGreaterEqual(latency["p95"], 0)
            self.assertGreaterEqual(latency["max"], latency["min"])
            self.assertGreaterEqual(latency["avg"], 0)
            self.assertIn("p95_sample_interval_ms", probe)
            self.assertIn("max_sample_interval_ms", probe)

            serialized = json.dumps({"manifest": manifest, "summary": summary}, sort_keys=True)
            self.assertNotIn(str(output), serialized)
            self.assertNotIn(str(fake_client), serialized)
            self.assertNotRegex(serialized, PRIVATE_PATTERNS)

    def test_runner_classifies_known_clean_profile_warning_as_expected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            fake_server = self.write_fake_profile_server(
                tmpdir,
                '2026-06-28 00:00:00: WARNING[Main]: No SHA256 known for builtin file "/tmp/profile/builtin/game/demo_entity_benchmark.lua"',
            )

            completed, _, run_dir, manifest = self.run_capture(
                "--game-profile",
                "ai_runtime",
                "--server-bin",
                str(fake_server),
                "--profile-sample-seconds",
                "0.1",
                "--profile-startup-timeout",
                "2",
                output_root=output_root,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            summary_path = run_dir / manifest["reports"]["clean_profile"]
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            steady = summary["comparison_summary"]["steady_tick_behavior"]
            self.assertEqual(steady["server_log_warning_count"], 1)
            self.assertEqual(steady["expected_server_log_warning_count"], 1)
            self.assertEqual(steady["actionable_server_log_warning_count"], 0)
            self.assertEqual(
                steady["expected_warning_kinds"],
                ["run_in_place_builtin_sha_missing"],
            )
            probe = summary["comparison_summary"]["player_load_tick_probe"]
            self.assertEqual(probe["server_log_warning_count"], 1)
            self.assertEqual(probe["expected_server_log_warning_count"], 1)
            self.assertEqual(probe["actionable_server_log_warning_count"], 0)

    def test_runner_classifies_run_in_place_sha_mismatch_warnings_as_expected(self):
        log_text = "\n".join(
            [
                '2026-06-29 00:00:00: WARNING[Main]: SHA256 of builtin file "/tmp/profile/builtin/game/init.lua" does not match.',
                "2026-06-29 00:00:00: WARNING[Main]: Expected: abc123",
                "2026-06-29 00:00:00: WARNING[Main]: Found:    def456",
                '2026-06-29 00:00:00: WARNING[Main]: SHA256 of builtin file "/tmp/profile/builtin/game/ai_runtime.lua" does not match.',
                "2026-06-29 00:00:00: WARNING[Main]: Expected: abc123",
                "2026-06-29 00:00:00: WARNING[Main]: Found:    def456",
                '2026-06-29 00:00:00: WARNING[Main]: SHA256 of builtin file "/tmp/profile/builtin/game/ai_agent_plugin.lua" does not match.',
                "2026-06-29 00:00:00: WARNING[Main]: Expected: 2c1cfd9a215fdbddbc7623f6e2fe66f64c25981008898e27517c460e8545520f",
                "2026-06-29 00:00:00: WARNING[Main]: Found:    230ac1afe3db3743f363341b73e87c5cc3ad585a8d2fd5e2d05e0781f941003e",
                '2026-06-29 00:00:00: WARNING[Main]: No SHA256 known for builtin file "/tmp/profile/builtin/game/ai_operator_task_control.lua"',
            ]
        )

        summary = benchmark_capture.classify_profile_log_warnings(log_text)

        self.assertEqual(summary["server_log_warning_count"], 10)
        self.assertEqual(summary["expected_server_log_warning_count"], 10)
        self.assertEqual(summary["actionable_server_log_warning_count"], 0)
        self.assertEqual(
            summary["expected_warning_kinds"],
            [
                "run_in_place_builtin_sha_changed",
                "run_in_place_builtin_sha_missing",
            ],
        )

    def test_runner_marks_partial_headless_player_probe_as_failed_profile(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = pathlib.Path(tmpdir) / "local" / "benchmarks"
            fake_server = self.write_fake_profile_server(tmpdir)
            fake_client = self.write_fake_headless_player(tmpdir)

            completed, _, run_dir, manifest = self.run_capture(
                "--game-profile",
                "ai_runtime",
                "--server-bin",
                str(fake_server),
                "--profile-sample-seconds",
                "0.15",
                "--profile-startup-timeout",
                "2",
                "--headless-player-command",
                f"{sys.executable} {fake_client} --server-log {{server_log}} --name {{name}} --duration {{duration_seconds}} --fail-suffix 2",
                "--headless-player-count",
                "2",
                output_root=output_root,
                check=False,
            )

            self.assertEqual(completed.returncode, 1)
            self.assertIsNotNone(manifest)
            self.assertEqual(manifest["profile_statuses"]["clean_profile"], "fail")
            summary_path = run_dir / manifest["reports"]["clean_profile"]
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["overall_status"], "fail")
            self.assertIn("headless_player_probe_incomplete", summary["failure_notes"])

            probe = summary["comparison_summary"]["player_load_tick_probe"]
            self.assertEqual(probe["probe_status"], "partial")
            self.assertEqual(probe["probe_kind"], "headless_client_load")
            self.assertTrue(probe["headless_player_supported"])
            self.assertEqual(probe["attempted_synthetic_player_count"], 2)
            self.assertEqual(probe["connected_synthetic_player_count"], 1)
            self.assertEqual(probe["synthetic_player_count"], 1)
            self.assertEqual(probe["client_launch_failure_count"], 0)
            self.assertTrue(probe["latency_proxy_supported"])
            self.assertEqual(probe["join_latency_proxy_ms"]["sample_count"], 1)
            self.assertIn(7, probe["client_exit_statuses"])

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
            "clean-profile-benchmark-summary.json",
            "player_load_tick_probe",
            "server-step",
            "--headless-player-command",
            "headless_client_load",
            "expected_server_log_warning_count",
            "actionable_server_log_warning_count",
            "expected_warning_kinds",
            "-DENABLE_SOUND=FALSE",
            "video_driver = null",
            "bin/luanti --config",
            "libsdl2-dev",
            "reviewed-local-headless-client",
            "reviewed-low-power-headless-client",
            "benchmark-capture-manifest.json",
            "same-hardware baseline",
            "--game-profile ai_runtime",
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
