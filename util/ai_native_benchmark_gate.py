#!/usr/bin/env python3
"""Run the local AI-native branch benchmark gate against an accepted baseline."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import ai_native_benchmark_capture


ROOT = Path(__file__).resolve().parents[1]
REPORT_KEYS = ("mutation", "demo_entity")
REPORT_DEFAULTS = {
    "mutation": "mutation-benchmark-report.json",
    "demo_entity": "generic-demo-entity-benchmark-report.json",
}


class GateError(Exception):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def logical_benchmark_path(hardware_class: str, *parts: str) -> str:
    return "/".join(["local", "benchmarks", hardware_class, *parts])


def require_accepted_baseline(output_root: Path, hardware_class: str) -> tuple[Path, dict]:
    accepted_dir = output_root / hardware_class / "accepted"
    manifest_path = accepted_dir / "accepted-baseline-manifest.json"
    if not manifest_path.is_file():
        raise GateError(
            "accepted baseline missing for "
            f"{hardware_class}; run util/ai_native_benchmark_promote.py after reviewing "
            "a clean local capture."
        )

    manifest = load_json(manifest_path)
    run_context = manifest.get("run_context") or {}
    if run_context.get("mode") != "accepted-local-baseline":
        raise GateError(
            "accepted baseline manifest is not mode=accepted-local-baseline; "
            "rerun util/ai_native_benchmark_promote.py with a reviewed clean capture."
        )
    if manifest.get("hardware_class") != hardware_class:
        raise GateError(
            "accepted baseline hardware class mismatch "
            f"({manifest.get('hardware_class')!r} != {hardware_class!r})."
        )

    reports = manifest.get("reports") or {}
    missing = []
    for report_key in REPORT_KEYS:
        filename = reports.get(report_key) or REPORT_DEFAULTS[report_key]
        if not (accepted_dir / filename).is_file():
            missing.append(filename)
    if missing:
        raise GateError(
            "accepted baseline reports are incomplete; rerun "
            f"util/ai_native_benchmark_promote.py. Missing: {', '.join(missing)}"
        )
    return accepted_dir, manifest


def comparison_failure_reasons(comparison_statuses: dict) -> list[str]:
    reasons = []
    for report_key in REPORT_KEYS:
        status = comparison_statuses.get(report_key)
        if status != "pass":
            reasons.append(f"{report_key} comparison status is {status or 'missing'}")
    return reasons


def profile_failure_reasons(args, profile_statuses: dict) -> list[str]:
    if args.game_profile != "ai_runtime":
        return []
    status = profile_statuses.get("clean_profile")
    if status != "pass":
        return [f"clean_profile status is {status or 'missing'}"]
    return []


def build_gate_manifest(
    args,
    accepted_manifest: dict,
    capture_manifest: dict,
    capture_status: int,
    failure_reasons: list[str],
) -> dict:
    date_part = ai_native_benchmark_capture.path_part(args.date)
    commit_part = ai_native_benchmark_capture.path_part(args.luanti_commit)
    comparison_statuses = capture_manifest.get("comparison_statuses") or {}
    profile_statuses = capture_manifest.get("profile_statuses") or {}
    overall_status = "fail" if failure_reasons or capture_status != 0 else "pass"

    if capture_status not in (0, 1):
        failure_reasons = [*failure_reasons, f"capture exited with status {capture_status}"]

    return {
        "schema_version": 1,
        "generated_at": utc_now(),
        "hardware_class": args.hardware_class,
        "game_profile": args.game_profile,
        "logical_run_dir": logical_benchmark_path(args.hardware_class, date_part, commit_part),
        "overall_status": overall_status,
        "branch_ref": {
            "luanti_commit": args.luanti_commit,
            "run_mode": (capture_manifest.get("run_context") or {}).get("mode"),
            "game_profile": capture_manifest.get("game_profile"),
        },
        "accepted_baseline": {
            "logical_dir": logical_benchmark_path(args.hardware_class, "accepted"),
            "luanti_commit": accepted_manifest.get("luanti_commit"),
            "source_label": accepted_manifest.get("source_label"),
            "source_capture": accepted_manifest.get("source_capture"),
            "reports": accepted_manifest.get("reports") or {},
        },
        "reports": capture_manifest.get("reports") or {},
        "comparisons": capture_manifest.get("comparisons") or {},
        "comparison_statuses": comparison_statuses,
        "profile_statuses": profile_statuses,
        "failure_reasons": failure_reasons,
        "run_context": {
            "mode": "branch-benchmark-gate",
            "requires_private_world": False,
            "requires_private_assets": False,
            "requires_live_pi": False,
            "requires_model_network": False,
        },
        "low_power_backup_confirmed": args.confirm_low_power_backup,
        "notes": [
            "Gate captures synthetic local reports and compares them with the accepted baseline.",
            "Generated gate artifacts remain local-only and ignored by Git.",
        ],
    }


def run_gate(args) -> int:
    output_root = Path(args.output_root)
    accepted_dir, accepted_manifest = require_accepted_baseline(output_root, args.hardware_class)
    accepted_reports = accepted_manifest.get("reports") or {}

    capture_args = [
        "--output-root",
        str(output_root),
        "--hardware-class",
        args.hardware_class,
        "--date",
        args.date,
        "--luanti-commit",
        args.luanti_commit,
        "--mutation-baseline",
        str(accepted_dir / accepted_reports.get("mutation", REPORT_DEFAULTS["mutation"])),
        "--demo-entity-baseline",
        str(accepted_dir / accepted_reports.get("demo_entity", REPORT_DEFAULTS["demo_entity"])),
    ]
    if args.game_profile == "ai_runtime":
        capture_args += [
            "--game-profile",
            "ai_runtime",
            "--server-bin",
            args.server_bin,
            "--profile-sample-seconds",
            str(args.profile_sample_seconds),
            "--profile-startup-timeout",
            str(args.profile_startup_timeout),
        ]
        if args.profile_port:
            capture_args += ["--profile-port", str(args.profile_port)]
        if args.headless_player_command:
            capture_args += [
                "--headless-player-command",
                args.headless_player_command,
                "--headless-player-count",
                str(args.headless_player_count),
                "--headless-player-timeout",
                str(args.headless_player_timeout),
            ]
    if args.confirm_low_power_backup:
        capture_args.append("--confirm-low-power-backup")

    capture_status = ai_native_benchmark_capture.main(capture_args)
    date_part = ai_native_benchmark_capture.path_part(args.date)
    commit_part = ai_native_benchmark_capture.path_part(args.luanti_commit)
    run_dir = output_root / args.hardware_class / date_part / commit_part
    capture_manifest = load_json(run_dir / "benchmark-capture-manifest.json")
    failure_reasons = [
        *comparison_failure_reasons(capture_manifest.get("comparison_statuses") or {}),
        *profile_failure_reasons(args, capture_manifest.get("profile_statuses") or {}),
    ]
    gate_manifest = build_gate_manifest(
        args,
        accepted_manifest,
        capture_manifest,
        capture_status,
        failure_reasons,
    )
    write_json(run_dir / "benchmark-gate-manifest.json", gate_manifest)
    print(gate_manifest["logical_run_dir"] + "/benchmark-gate-manifest.json")
    return 0 if gate_manifest["overall_status"] == "pass" else 1


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Run a local branch benchmark smoke gate against an accepted baseline."
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
        help="Hardware lane for the branch gate.",
    )
    parser.add_argument(
        "--date",
        default=ai_native_benchmark_capture.utc_date(),
        help="Run date segment for the local benchmark path.",
    )
    parser.add_argument(
        "--luanti-commit",
        default=ai_native_benchmark_capture.default_commit(),
        help="Commit or label for the branch build under benchmark.",
    )
    parser.add_argument(
        "--game-profile",
        choices=("sample-synthetic", "ai_runtime"),
        default="sample-synthetic",
        help="Optional clean server profile to launch during capture.",
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
        "--headless-player-command",
        help=(
            "Optional command template for disposable synthetic players during "
            "clean-profile capture. Supported placeholders: {host}, {port}, "
            "{name}, {server_log}, {duration_seconds}."
        ),
    )
    parser.add_argument(
        "--headless-player-count",
        type=int,
        default=2,
        help="Synthetic player command instances to launch when --headless-player-command is supplied.",
    )
    parser.add_argument(
        "--headless-player-timeout",
        type=float,
        default=2.0,
        help="Seconds to wait while cleaning up each synthetic player process.",
    )
    parser.add_argument(
        "--confirm-low-power-backup",
        action="store_true",
        help="Required for low-power-server gates to confirm backup-first readiness.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        return run_gate(args)
    except (GateError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
