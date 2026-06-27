#!/usr/bin/env python3
"""Capture local AI-native benchmark reports into the ignored local workflow."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import ai_native_benchmark_compare
import ai_native_mutation_benchmarks


ROOT = Path(__file__).resolve().parents[1]
DEMO_ENTITY_EXAMPLE = (
    ROOT
    / "doc"
    / "ai-native-runtime"
    / "examples"
    / "generic-demo-entity-benchmark-report.example.json"
)


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


def build_manifest(args, logical_run_dir: str, comparison_statuses: dict[str, str]) -> dict:
    comparisons = {}
    if args.mutation_baseline:
        comparisons["mutation"] = "mutation-comparison.json"
    if args.demo_entity_baseline:
        comparisons["demo_entity"] = "demo-entity-comparison.json"

    return {
        "schema_version": 1,
        "generated_at": utc_now(),
        "luanti_commit": args.luanti_commit,
        "hardware_class": args.hardware_class,
        "logical_run_dir": logical_run_dir,
        "run_context": {
            "mode": "sample-synthetic",
            "requires_private_world": False,
            "requires_private_assets": False,
            "requires_live_pi": False,
        },
        "reports": {
            "mutation": "mutation-benchmark-report.json",
            "demo_entity": "generic-demo-entity-benchmark-report.json",
        },
        "comparisons": comparisons,
        "comparison_statuses": comparison_statuses,
        "low_power_backup_confirmed": args.confirm_low_power_backup,
        "notes": [
            "Default capture uses synthetic local reports and requires no live server.",
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

    manifest = build_manifest(args, logical_run_dir, comparison_statuses)
    write_json(run_dir / "benchmark-capture-manifest.json", manifest)
    print(logical_run_dir)

    if any(status == "fail" for status in comparison_statuses.values()):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
