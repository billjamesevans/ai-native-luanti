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
FIRST_PARTY_AGENT_PRODUCT_LOOP_THRESHOLDS = {
    "approval_plan_count": 2,
    "approved_task_count": 2,
    "guide_command_checked": 1,
    "tasks_command_checked": 1,
    "cancel_command_checked": 1,
    "audit_review_checked": 1,
    "rollback_review_checked": 1,
    "defender_command_checked": 1,
    "import_preview_checked": 1,
}


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


def numeric_metric(value) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    return 0


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
    comparison_summary = report.get("comparison_summary") or {}
    workload = comparison_summary.get("server_step_workload")
    if not isinstance(workload, dict):
        errors.append("clean_profile: server_step_workload missing")
    else:
        if workload.get("workload_status") != "pass":
            errors.append("clean_profile: server_step_workload status must be pass")
        if (workload.get("attempted_sample_count") or 0) <= 0:
            errors.append("clean_profile: server_step_workload attempted_sample_count must be positive")
        if (workload.get("completed_sample_count") or 0) <= 0:
            errors.append("clean_profile: server_step_workload completed_sample_count must be positive")
        if (workload.get("failed_sample_count") or 0) != 0:
            errors.append("clean_profile: server_step_workload failed_sample_count must be 0")
    player_probe = comparison_summary.get("player_load_tick_probe")
    if not isinstance(player_probe, dict):
        errors.append("clean_profile: player_load_tick_probe missing")
    else:
        attempted = player_probe.get("attempted_synthetic_player_count") or 0
        connected = player_probe.get("connected_synthetic_player_count") or 0
        if player_probe.get("probe_status") != "pass":
            errors.append("clean_profile: player_load_tick_probe status must be pass")
        if player_probe.get("probe_kind") != "headless_client_load":
            errors.append("clean_profile: player_load_tick_probe kind must be headless_client_load")
        if player_probe.get("headless_player_supported") is not True:
            errors.append("clean_profile: headless_player_supported must be true")
        if attempted <= 0:
            errors.append("clean_profile: attempted_synthetic_player_count must be positive")
        if connected <= 0:
            errors.append("clean_profile: connected_synthetic_player_count must be positive")
        if connected != attempted:
            errors.append("clean_profile: connected synthetic players must equal attempted synthetic players")
        if player_probe.get("latency_proxy_supported") is not True:
            errors.append("clean_profile: latency_proxy_supported must be true")
        if player_probe.get("latency_probe_kind") != "headless_join_log_observation":
            errors.append("clean_profile: latency_probe_kind must be headless_join_log_observation")
        join_latency = player_probe.get("join_latency_proxy_ms") or {}
        if (join_latency.get("sample_count") or 0) <= 0:
            errors.append("clean_profile: join_latency_proxy_ms.sample_count must be positive")
    map_workload = comparison_summary.get("map_chunk_workload")
    if not isinstance(map_workload, dict):
        errors.append("clean_profile: map_chunk_workload missing")
    else:
        if map_workload.get("workload_status") != "pass":
            errors.append("clean_profile: map_chunk_workload status must be pass")
        if map_workload.get("workload_kind") != "synthetic_sqlite_mapblock_churn":
            errors.append(
                "clean_profile: map_chunk_workload kind must be synthetic_sqlite_mapblock_churn"
            )
        if (map_workload.get("mapblock_rows_created") or 0) <= 0:
            errors.append("clean_profile: mapblock_rows_created must be positive")
    cpu = comparison_summary.get("cpu")
    if not isinstance(cpu, dict):
        errors.append("clean_profile: cpu missing")
    else:
        if cpu.get("sample_status") != "measured":
            errors.append("clean_profile: cpu sample_status must be measured")
        if (cpu.get("cpu_sample_count") or 0) < 2:
            errors.append("clean_profile: cpu_sample_count must be at least 2")
        if cpu.get("avg_process_cpu_percent") is None:
            errors.append("clean_profile: avg_process_cpu_percent is required")
        if cpu.get("max_interval_cpu_percent") is None:
            errors.append("clean_profile: max_interval_cpu_percent is required")
    product_loop = comparison_summary.get("first_party_agent_product_loop")
    if not isinstance(product_loop, dict):
        errors.append("clean_profile: first_party_agent_product_loop missing")
    else:
        if product_loop.get("product_loop_status") != "pass":
            errors.append("clean_profile: first_party_agent_product_loop status must be pass")
        for metric, threshold in FIRST_PARTY_AGENT_PRODUCT_LOOP_THRESHOLDS.items():
            if numeric_metric(product_loop.get(metric)) < threshold:
                errors.append(
                    f"clean_profile: first_party_agent_product_loop {metric} "
                    f"must be at least {threshold}"
                )
        if product_loop.get("blocked_or_unsafe_outcomes") != 0:
            errors.append(
                "clean_profile: first_party_agent_product_loop "
                "blocked_or_unsafe_outcomes must be 0"
            )
        if numeric_metric(product_loop.get("warning_count")) != 0:
            errors.append("clean_profile: first_party_agent_product_loop warning_count must be 0")
        if numeric_metric(product_loop.get("error_count")) != 0:
            errors.append("clean_profile: first_party_agent_product_loop error_count must be 0")
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
