#!/usr/bin/env python3
"""Capture local AI-native benchmark reports into the ignored local workflow."""

from __future__ import annotations

import argparse
import json
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import ai_native_benchmark_compare
import ai_native_mutation_benchmarks


ROOT = Path(__file__).resolve().parents[1]
RUNNER_VERSION = "ai-native-benchmark-capture:v2"
CLEAN_PROFILE_RUNNER_VERSION = "ai-native-clean-profile-benchmark:v1"
DEMO_ENTITY_EXAMPLE = (
    ROOT
    / "doc"
    / "ai-native-runtime"
    / "examples"
    / "generic-demo-entity-benchmark-report.example.json"
)
PROFILE_LOG_FAILURE_PATTERNS = re.compile(r"Mapgen alias .* invalid|testnodes:", re.I)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def path_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", value)


def default_commit() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
        return completed.stdout.strip() or "unknown"
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def count_items(value) -> int:
    if value is None:
        return 0
    if isinstance(value, list):
        return len(value)
    return 1


def max_metric(report: dict, metric_name: str):
    values = []
    for scenario in report.get("scenarios", []):
        value = (scenario.get("metrics") or {}).get(metric_name)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            values.append(value)
    return max(values) if values else None


def sum_metric(report: dict, metric_name: str) -> float:
    total = 0.0
    for scenario in report.get("scenarios", []):
        value = (scenario.get("metrics") or {}).get(metric_name)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            total += value
    return total


def count_metric_items(report: dict, metric_name: str) -> int:
    return sum(
        count_items((scenario.get("metrics") or {}).get(metric_name))
        for scenario in report.get("scenarios", [])
    )


def sample_interval_stats(sample_times: list[float]) -> dict:
    if len(sample_times) < 2:
        value = 0.0 if sample_times else None
        return {
            "p95_sample_interval_ms": value,
            "max_sample_interval_ms": value,
            "avg_sample_interval_ms": value,
        }
    intervals = [
        round((sample_times[index] - sample_times[index - 1]) * 1000, 3)
        for index in range(1, len(sample_times))
    ]
    ordered = sorted(intervals)
    p95_index = min(len(ordered) - 1, int((len(ordered) * 0.95) + 0.999999) - 1)
    return {
        "p95_sample_interval_ms": ordered[p95_index],
        "max_sample_interval_ms": max(intervals),
        "avg_sample_interval_ms": round(sum(intervals) / len(intervals), 3),
    }


def build_player_load_tick_probe(
    args,
    listening: bool,
    sample_times: list[float],
    failure_notes: list[str],
    log_warning_count: int,
    log_error_count: int,
) -> dict:
    intervals = sample_interval_stats(sample_times)
    server_stayed_listening = listening and "server_exited_during_profile_sample" not in failure_notes
    return {
        "probe_status": "pass" if server_stayed_listening and log_error_count == 0 else "fail",
        "probe_kind": "server_process_liveness",
        "probe_duration_seconds": (
            round(sample_times[-1] - sample_times[0], 3)
            if len(sample_times) >= 2
            else 0.0
        ),
        "requested_sample_seconds": args.profile_sample_seconds,
        "sample_count": len(sample_times),
        "synthetic_player_count": 0,
        "headless_player_supported": False,
        "server_stayed_listening": server_stayed_listening,
        "server_log_warning_count": log_warning_count,
        "server_log_error_count": log_error_count,
        "p95_sample_interval_ms": intervals["p95_sample_interval_ms"],
        "max_sample_interval_ms": intervals["max_sample_interval_ms"],
        "avg_sample_interval_ms": intervals["avg_sample_interval_ms"],
        "limitations": [
            "No headless-player client load path is wired yet; this probe measures bounded server-process liveness during clean-profile sampling.",
        ],
    }


def resolve_server_bin(server_bin: str) -> str:
    path = Path(server_bin)
    if path.is_absolute():
        return str(path)
    return str(ROOT / path)


def manifest_server_bin(server_bin: str) -> str:
    path = Path(server_bin)
    if not path.is_absolute():
        return path.as_posix()
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return "<server-bin>"


def free_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def sample_rss_kb(pid: int) -> int | None:
    try:
        completed = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(pid)],
            check=False,
            text=True,
            capture_output=True,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    value = completed.stdout.strip().split()
    if not value:
        return None
    try:
        return int(value[0])
    except ValueError:
        return None


def inspect_map_workload(world_dir: Path) -> dict:
    map_db = world_dir / "map.sqlite"
    result = {
        "world_backend": "sqlite3",
        "map_sqlite_bytes": map_db.stat().st_size if map_db.is_file() else 0,
        "mapblock_rows": 0,
        "inspection_status": "missing_map_database",
    }
    if not map_db.is_file():
        return result

    try:
        with sqlite3.connect(map_db) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            if "blocks" in tables:
                result["mapblock_rows"] = int(conn.execute("SELECT COUNT(*) FROM blocks").fetchone()[0])
                result["inspection_status"] = "ok"
            else:
                result["inspection_status"] = "missing_blocks_table"
    except sqlite3.Error as exc:
        result["inspection_status"] = f"sqlite_error:{exc.__class__.__name__}"
    return result


def summarize_entity_report(report: dict) -> dict:
    return {
        "report_family": "demo_entity",
        "scenario_count": len(report.get("scenarios", [])),
        "max_entity_count": max_metric(report, "entity_count"),
        "max_active_peak": max_metric(report, "active_peak"),
        "max_remaining_entities": max_metric(report, "remaining_entities"),
        "warnings": count_metric_items(report, "warnings"),
        "errors": count_metric_items(report, "errors"),
    }


def summarize_mutation_report(report: dict) -> dict:
    return {
        "report_family": "mutation",
        "scenario_count": len(report.get("scenarios", [])),
        "total_node_writes": sum_metric(report, "node_writes"),
        "max_node_writes_per_step": max_metric(report, "node_writes_per_step"),
        "total_rollback_records": sum_metric(report, "rollback_records"),
        "warnings": count_metric_items(report, "warnings"),
        "errors": count_metric_items(report, "errors"),
    }


def write_profile_world(world_dir: Path) -> None:
    world_dir.mkdir(parents=True, exist_ok=True)
    (world_dir / "world.mt").write_text(
        "\n".join(
            [
                "gameid = ai_runtime",
                "backend = sqlite3",
                "player_backend = sqlite3",
                "auth_backend = sqlite3",
                "mod_storage_backend = sqlite3",
                "creative_mode = true",
                "enable_damage = false",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_profile_config(config_path: Path, port: int) -> None:
    config_path.write_text(
        "\n".join(
            [
                "server_name = AI Runtime Clean Profile Benchmark",
                "server_announce = false",
                "server_announce_send_players = false",
                f"port = {port}",
                "ipv6_server = true",
                "max_users = 2",
                "creative_mode = true",
                "enable_damage = false",
                "sqlite_synchronous = 2",
                "",
            ]
        ),
        encoding="utf-8",
    )


def read_text_if_exists(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def capture_clean_profile_summary(args, mutation_report: dict, demo_entity_report: dict) -> dict:
    profile_start = time.monotonic()
    failure_notes = []
    rss_samples = []
    port = args.profile_port or free_udp_port()
    listen_phrase = 'Server for gameid="ai_runtime" listening'
    listening = False
    exit_status = None
    startup_ms = None
    uptime_seconds = 0.0
    log_text = ""
    probe_sample_times = []

    with tempfile.TemporaryDirectory(prefix="ai-runtime-profile-") as tmpdir:
        temp_root = Path(tmpdir)
        world_dir = temp_root / "world"
        config_path = temp_root / "profile.conf"
        log_path = temp_root / "server.log"
        write_profile_world(world_dir)
        write_profile_config(config_path, port)

        command = [
            resolve_server_bin(args.server_bin),
            "--gameid",
            "ai_runtime",
            "--world",
            str(world_dir),
            "--config",
            str(config_path),
            "--logfile",
            str(log_path),
        ]
        try:
            proc = subprocess.Popen(
                command,
                cwd=ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
        except OSError as exc:
            failure_notes.append(f"server_launch_failed:{exc.__class__.__name__}")
            proc = None

        if proc is not None:
            deadline = time.monotonic() + args.profile_startup_timeout
            while time.monotonic() < deadline:
                rss = sample_rss_kb(proc.pid)
                if rss is not None:
                    rss_samples.append(rss)
                log_text = read_text_if_exists(log_path)
                if listen_phrase in log_text:
                    listening = True
                    startup_ms = round((time.monotonic() - profile_start) * 1000, 3)
                    break
                exit_status = proc.poll()
                if exit_status is not None:
                    break
                time.sleep(0.05)

            if not listening:
                failure_notes.append("server_did_not_reach_listening_state")

            sample_deadline = time.monotonic() + max(args.profile_sample_seconds, 0.0)
            while listening and time.monotonic() < sample_deadline:
                probe_sample_times.append(time.monotonic())
                exit_status = proc.poll()
                if exit_status is not None:
                    failure_notes.append("server_exited_during_profile_sample")
                    break
                rss = sample_rss_kb(proc.pid)
                if rss is not None:
                    rss_samples.append(rss)
                time.sleep(0.1)

            if proc.poll() is None:
                proc.terminate()
                try:
                    exit_status = proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    exit_status = proc.wait(timeout=5)
                    failure_notes.append("server_required_kill_after_timeout")
            else:
                exit_status = proc.returncode

            uptime_seconds = round(time.monotonic() - profile_start, 3)
            log_text = read_text_if_exists(log_path)

        log_warning_count = len(re.findall(r"\bWARNING\b", log_text))
        log_error_count = len(re.findall(r"\bERROR\b", log_text))
        if log_error_count:
            failure_notes.append("server_log_contains_errors")
        if PROFILE_LOG_FAILURE_PATTERNS.search(log_text):
            failure_notes.append("profile_log_contains_devtest_or_invalid_mapgen_alias")

        map_workload = inspect_map_workload(world_dir)

    startup = {
        "listening": listening,
        "time_to_listen_ms": startup_ms,
        "startup_timeout_seconds": args.profile_startup_timeout,
    }
    steady_tick_behavior = {
        "sample_seconds": args.profile_sample_seconds,
        "observed_uptime_seconds": uptime_seconds,
        "process_exited_unexpectedly": "server_exited_during_profile_sample" in failure_notes,
        "server_log_warning_count": log_warning_count,
        "server_log_error_count": log_error_count,
        "note": "Idle clean-profile server sample; player-load tick probe records bounded process liveness.",
    }
    player_load_tick_probe = build_player_load_tick_probe(
        args,
        listening,
        probe_sample_times,
        failure_notes,
        log_warning_count,
        log_error_count,
    )
    memory = {
        "max_rss_kb": max(rss_samples) if rss_samples else None,
        "rss_sample_count": len(rss_samples),
    }
    entity_runtime = summarize_entity_report(demo_entity_report)
    mutation_writes = summarize_mutation_report(mutation_report)

    comparison_summary = {
        "startup": startup,
        "steady_tick_behavior": steady_tick_behavior,
        "player_load_tick_probe": player_load_tick_probe,
        "map_chunk_workload": map_workload,
        "entity_runtime_operations": entity_runtime,
        "mutation_write_throughput": mutation_writes,
        "memory": memory,
        "failure_notes": failure_notes,
    }

    return {
        "schema_version": 1,
        "runner_version": CLEAN_PROFILE_RUNNER_VERSION,
        "generated_at": utc_now(),
        "luanti_commit": args.luanti_commit,
        "hardware_class": args.hardware_class,
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
        "server_launch": {
            "gameid": "ai_runtime",
            "command": [
                manifest_server_bin(args.server_bin),
                "--gameid",
                "ai_runtime",
                "--world",
                "<temp-world>",
                "--config",
                "<temp-config>",
                "--logfile",
                "<temp-log>",
            ],
            "port": port,
            "exit_status": exit_status,
        },
        "overall_status": "fail" if failure_notes else "pass",
        "comparison_summary": comparison_summary,
        "failure_notes": failure_notes,
        "notes": [
            "Clean-profile benchmarks start a disposable local ai_runtime world.",
            "The report stores logical profile metadata only, not temporary paths or live server state.",
        ],
    }


def capture_mutation_report(hardware_class: str, luanti_commit: str) -> dict:
    args = argparse.Namespace(
        hardware_class=hardware_class,
        luanti_commit=luanti_commit,
        sample_synthetic=True,
    )
    return ai_native_mutation_benchmarks.build_report(args)


def capture_demo_entity_report(hardware_class: str, luanti_commit: str) -> dict:
    report = json.loads(DEMO_ENTITY_EXAMPLE.read_text(encoding="utf-8"))
    report["generated_at"] = utc_now()
    report["luanti_commit"] = luanti_commit
    report["hardware_class"] = hardware_class
    report["run_context"] = {
        "mode": "sample-synthetic",
        "requires_private_world": False,
        "requires_private_assets": False,
        "requires_live_pi": False,
    }
    return report


def compare_if_requested(baseline_path: str | None, branch_report: dict, output_path: Path) -> str | None:
    if not baseline_path:
        return None
    baseline = ai_native_benchmark_compare.load_json(Path(baseline_path))
    comparison = ai_native_benchmark_compare.compare_reports(
        baseline,
        branch_report,
        max_regression=0.10,
    )
    write_json(output_path, comparison)
    return comparison["overall_status"]


def build_manifest(
    args,
    logical_run_dir: str,
    comparison_statuses: dict[str, str],
    profile_statuses: dict[str, str],
) -> dict:
    comparisons = {}
    if args.mutation_baseline:
        comparisons["mutation"] = "mutation-comparison.json"
    if args.demo_entity_baseline:
        comparisons["demo_entity"] = "demo-entity-comparison.json"

    reports = {
        "mutation": "mutation-benchmark-report.json",
        "demo_entity": "generic-demo-entity-benchmark-report.json",
    }
    if args.game_profile == "ai_runtime":
        reports["clean_profile"] = "clean-profile-benchmark-summary.json"

    return {
        "schema_version": 1,
        "runner_version": RUNNER_VERSION,
        "generated_at": utc_now(),
        "luanti_commit": args.luanti_commit,
        "hardware_class": args.hardware_class,
        "game_profile": args.game_profile,
        "logical_run_dir": logical_run_dir,
        "run_context": {
            "mode": "sample-synthetic+clean-profile"
            if args.game_profile == "ai_runtime"
            else "sample-synthetic",
            "requires_private_world": False,
            "requires_private_assets": False,
            "requires_live_pi": False,
            "requires_model_network": False,
        },
        "reports": reports,
        "comparisons": comparisons,
        "comparison_statuses": comparison_statuses,
        "profile_statuses": profile_statuses,
        "low_power_backup_confirmed": args.confirm_low_power_backup,
        "notes": [
            "Default capture uses synthetic local reports and requires no live server.",
            "Clean-profile capture uses a disposable ai_runtime world when requested.",
            "Measured reports remain local and ignored by Git.",
        ],
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Capture local AI-native benchmark reports under local/benchmarks."
    )
    parser.add_argument(
        "--output-root",
        default=str(ROOT / "local" / "benchmarks"),
        help="Benchmark retention root. Default: local/benchmarks.",
    )
    parser.add_argument(
        "--hardware-class",
        choices=("local-mac", "low-power-server"),
        default="local-mac",
        help="Hardware lane for the captured reports.",
    )
    parser.add_argument(
        "--date",
        default=utc_date(),
        help="Run date segment for the local benchmark path.",
    )
    parser.add_argument(
        "--luanti-commit",
        default=default_commit(),
        help="Commit or label for the engine build under benchmark.",
    )
    parser.add_argument(
        "--mutation-baseline",
        help="Accepted mutation benchmark baseline report to compare against.",
    )
    parser.add_argument(
        "--demo-entity-baseline",
        help="Accepted demo entity benchmark baseline report to compare against.",
    )
    parser.add_argument(
        "--game-profile",
        choices=("sample-synthetic", "ai_runtime"),
        default="sample-synthetic",
        help="Optional clean server profile to launch alongside synthetic reports.",
    )
    parser.add_argument(
        "--server-bin",
        default="bin/luantiserver",
        help="Server binary used when --game-profile ai_runtime is selected.",
    )
    parser.add_argument(
        "--profile-sample-seconds",
        type=float,
        default=3.0,
        help="Seconds to keep the disposable ai_runtime server alive after startup.",
    )
    parser.add_argument(
        "--profile-startup-timeout",
        type=float,
        default=15.0,
        help="Seconds to wait for the ai_runtime server listening log line.",
    )
    parser.add_argument(
        "--profile-port",
        type=int,
        help="Optional UDP port for the disposable ai_runtime profile launch.",
    )
    parser.add_argument(
        "--confirm-low-power-backup",
        action="store_true",
        help="Required for low-power-server capture to confirm backup-first readiness.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.hardware_class == "low-power-server" and not args.confirm_low_power_backup:
        print(
            "low-power-server capture requires backup-first confirmation; "
            "rerun with --confirm-low-power-backup after the target is backed up.",
            file=sys.stderr,
        )
        return 2

    date_part = path_part(args.date)
    commit_part = path_part(args.luanti_commit)
    run_dir = Path(args.output_root) / args.hardware_class / date_part / commit_part
    logical_run_dir = "/".join([
        "local",
        "benchmarks",
        args.hardware_class,
        date_part,
        commit_part,
    ])

    mutation_report = capture_mutation_report(args.hardware_class, args.luanti_commit)
    demo_entity_report = capture_demo_entity_report(args.hardware_class, args.luanti_commit)
    write_json(run_dir / "mutation-benchmark-report.json", mutation_report)
    write_json(run_dir / "generic-demo-entity-benchmark-report.json", demo_entity_report)

    profile_statuses = {}
    if args.game_profile == "ai_runtime":
        clean_profile_summary = capture_clean_profile_summary(
            args,
            mutation_report,
            demo_entity_report,
        )
        write_json(run_dir / "clean-profile-benchmark-summary.json", clean_profile_summary)
        profile_statuses["clean_profile"] = clean_profile_summary["overall_status"]

    comparison_statuses = {}
    mutation_status = compare_if_requested(
        args.mutation_baseline,
        mutation_report,
        run_dir / "mutation-comparison.json",
    )
    if mutation_status:
        comparison_statuses["mutation"] = mutation_status
    demo_status = compare_if_requested(
        args.demo_entity_baseline,
        demo_entity_report,
        run_dir / "demo-entity-comparison.json",
    )
    if demo_status:
        comparison_statuses["demo_entity"] = demo_status

    manifest = build_manifest(args, logical_run_dir, comparison_statuses, profile_statuses)
    write_json(run_dir / "benchmark-capture-manifest.json", manifest)
    print(logical_run_dir)

    if any(status == "fail" for status in comparison_statuses.values()):
        return 1
    if any(status == "fail" for status in profile_statuses.values()):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
