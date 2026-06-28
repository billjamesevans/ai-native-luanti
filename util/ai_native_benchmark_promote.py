#!/usr/bin/env python3
"""Promote a reviewed local benchmark capture to the accepted baseline lane."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


REPORT_FILES = {
    "mutation": "mutation-benchmark-report.json",
    "demo_entity": "generic-demo-entity-benchmark-report.json",
}
OPTIONAL_REPORT_FILES = {
    "clean_profile": "clean-profile-benchmark-summary.json",
}
PRIVATE_CONTEXT_FLAGS = (
    "requires_private_world",
    "requires_private_assets",
    "requires_live_pi",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def count_items(value) -> int:
    if value is None:
        return 0
    if isinstance(value, list):
        return len(value)
    return 1


def report_errors(report_name: str, report: dict) -> list[str]:
    errors = []
    run_context = report.get("run_context") or {}
    for flag in PRIVATE_CONTEXT_FLAGS:
        if run_context.get(flag) is True:
            errors.append(f"{report_name}: {flag}=true")

    for scenario in report.get("scenarios", []):
        scenario_id = scenario.get("scenario_id", "unknown")
        metrics = scenario.get("metrics") or {}
        if count_items(metrics.get("warnings")) > 0:
            errors.append(f"{report_name}:{scenario_id}: warnings present")
        if count_items(metrics.get("errors")) > 0:
            errors.append(f"{report_name}:{scenario_id}: errors present")
    return errors


def clean_profile_errors(report: dict) -> list[str]:
    errors = []
    if report.get("overall_status") != "pass":
        errors.append("clean_profile: overall_status must be pass")
    if (report.get("game_profile") or {}).get("gameid") != "ai_runtime":
        errors.append("clean_profile: game_profile.gameid must be ai_runtime")
    if report.get("failure_notes"):
        errors.append("clean_profile: failure_notes present")
    run_context = report.get("run_context") or {}
    for flag in (*PRIVATE_CONTEXT_FLAGS, "requires_model_network"):
        if run_context.get(flag) is True:
            errors.append(f"clean_profile: {flag}=true")
    return errors


def load_capture(capture_dir: Path):
    manifest_path = capture_dir / "benchmark-capture-manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"missing capture manifest: {manifest_path}")
    manifest = load_json(manifest_path)
    report_files = dict(REPORT_FILES)
    declared_reports = manifest.get("reports") or {}
    for report_name, filename in OPTIONAL_REPORT_FILES.items():
        if declared_reports.get(report_name) == filename:
            report_files[report_name] = filename

    reports = {}
    for report_name, filename in report_files.items():
        path = capture_dir / filename
        if not path.is_file():
            raise FileNotFoundError(f"missing {report_name} report: {path}")
        reports[report_name] = load_json(path)
    return manifest, reports, report_files


def validate_capture(manifest: dict, reports: dict) -> list[str]:
    errors = []
    hardware_class = manifest.get("hardware_class")
    if not hardware_class:
        errors.append("manifest: hardware_class missing")
    for report_name, report in reports.items():
        report_hardware = report.get("hardware_class")
        if report_hardware != hardware_class:
            errors.append(
                f"{report_name}: hardware_class mismatch "
                f"({report_hardware!r} != {hardware_class!r})"
            )
        if report_name == "clean_profile":
            errors.extend(clean_profile_errors(report))
        else:
            errors.extend(report_errors(report_name, report))
    return errors


def build_manifest(source_manifest: dict, source_label: str, report_files: dict) -> dict:
    return {
        "schema_version": 1,
        "generated_at": utc_now(),
        "luanti_commit": source_manifest.get("luanti_commit"),
        "hardware_class": source_manifest.get("hardware_class"),
        "game_profile": source_manifest.get("game_profile", "sample-synthetic"),
        "source_label": source_label,
        "source_capture": source_manifest.get("logical_run_dir"),
        "reports": dict(report_files),
        "run_context": {
            "mode": "accepted-local-baseline",
            "requires_private_world": False,
            "requires_private_assets": False,
            "requires_live_pi": False,
            "requires_model_network": False,
        },
        "notes": [
            "Accepted baseline is local-only and ignored by Git.",
            "Promotion refused reports with private/live state, warnings, or errors.",
        ],
    }


def promote_capture(capture_dir: Path, output_root: Path, source_label: str) -> Path:
    manifest, reports, report_files = load_capture(capture_dir)
    validation_errors = validate_capture(manifest, reports)
    if validation_errors:
        raise ValueError("\n".join(validation_errors))

    hardware_class = manifest["hardware_class"]
    accepted_dir = output_root / hardware_class / "accepted"
    accepted_dir.mkdir(parents=True, exist_ok=True)
    for _, filename in report_files.items():
        shutil.copyfile(capture_dir / filename, accepted_dir / filename)
    write_json(
        accepted_dir / "accepted-baseline-manifest.json",
        build_manifest(manifest, source_label, report_files),
    )
    return accepted_dir


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Promote a reviewed local AI benchmark capture to the accepted baseline lane."
    )
    parser.add_argument("--capture-dir", required=True, help="Local benchmark capture directory.")
    parser.add_argument(
        "--output-root",
        required=True,
        help="Benchmark retention root, usually local/benchmarks.",
    )
    parser.add_argument(
        "--source-label",
        required=True,
        help="Reviewed source label or short operator note for the accepted baseline.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        accepted_dir = promote_capture(
            Path(args.capture_dir),
            Path(args.output_root),
            args.source_label,
        )
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(accepted_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
