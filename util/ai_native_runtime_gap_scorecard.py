#!/usr/bin/env python3
"""Build a public-safe AI-native runtime gap scorecard from accepted baselines."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER_VERSION = "ai-native-runtime-gap-scorecard:v1"
DEFAULT_HARDWARE_CLASSES = ("local-mac", "low-power-server")
REQUIRED_CLEAN_PROFILE_SECTIONS = (
    "startup",
    "steady_tick_behavior",
    "map_chunk_workload",
    "entity_runtime_operations",
    "mutation_write_throughput",
    "first_party_agent_product_loop",
    "ai_runtime_scale_gate",
    "memory",
    "failure_notes",
)
PRIVATE_PATTERNS = re.compile(
    r"minecraftpi|192\.168|spacebase|themepark|showcase100|disneyland100|"
    r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY|private_prompt|asset_payload|"
    r"/Users/|/opt/|bill@",
    re.I,
)


class ScorecardError(RuntimeError):
    pass


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


def summarize_mutation_report(report: dict) -> dict:
    return {
        "scenario_count": len(report.get("scenarios", [])),
        "total_node_writes": sum_metric(report, "node_writes"),
        "max_node_writes_per_step": max_metric(report, "node_writes_per_step"),
        "total_rollback_records": sum_metric(report, "rollback_records"),
        "warnings": count_metric_items(report, "warnings"),
        "errors": count_metric_items(report, "errors"),
    }


def summarize_demo_report(report: dict) -> dict:
    return {
        "scenario_count": len(report.get("scenarios", [])),
        "max_entity_count": max_metric(report, "entity_count"),
        "max_active_peak": max_metric(report, "active_peak"),
        "max_remaining_entities": max_metric(report, "remaining_entities"),
        "warnings": count_metric_items(report, "warnings"),
        "errors": count_metric_items(report, "errors"),
    }


def require_public_context(hardware_class: str, payload_name: str, payload: dict) -> None:
    run_context = payload.get("run_context") or {}
    for flag in (
        "requires_private_world",
        "requires_private_assets",
        "requires_live_pi",
        "requires_model_network",
    ):
        if run_context.get(flag) is True:
            raise ScorecardError(f"{payload_name} for {hardware_class} has {flag}=true")


def load_accepted_lane(output_root: Path, hardware_class: str) -> dict:
    accepted_dir = output_root / hardware_class / "accepted"
    manifest_path = accepted_dir / "accepted-baseline-manifest.json"
    if not manifest_path.is_file():
        raise ScorecardError(
            f"accepted baseline missing for {hardware_class}; "
            "run util/ai_native_benchmark_promote.py after reviewing a clean-profile capture."
        )

    manifest = load_json(manifest_path)
    if (manifest.get("run_context") or {}).get("mode") != "accepted-local-baseline":
        raise ScorecardError(
            f"accepted baseline manifest for {hardware_class} is not mode=accepted-local-baseline; "
            "rerun util/ai_native_benchmark_promote.py."
        )
    if manifest.get("hardware_class") != hardware_class:
        raise ScorecardError(
            f"accepted baseline hardware class mismatch for {hardware_class}: "
            f"{manifest.get('hardware_class')!r}"
        )
    require_public_context(hardware_class, "accepted baseline manifest", manifest)

    reports = manifest.get("reports") or {}
    clean_profile_name = reports.get("clean_profile")
    if clean_profile_name != "clean-profile-benchmark-summary.json":
        raise ScorecardError(
            f"clean_profile report missing for {hardware_class}; expected "
            "clean-profile-benchmark-summary.json in accepted baseline. "
            "Rerun util/ai_native_benchmark_promote.py from a capture using --game-profile ai_runtime."
        )

    required_reports = {
        "mutation": reports.get("mutation", "mutation-benchmark-report.json"),
        "demo_entity": reports.get("demo_entity", "generic-demo-entity-benchmark-report.json"),
        "clean_profile": clean_profile_name,
    }
    loaded_reports = {}
    for report_name, filename in required_reports.items():
        path = accepted_dir / filename
        if not path.is_file():
            raise ScorecardError(f"{report_name} report missing for {hardware_class}: {filename}")
        loaded_reports[report_name] = load_json(path)
        require_public_context(hardware_class, report_name, loaded_reports[report_name])

    clean_profile = loaded_reports["clean_profile"]
    if clean_profile.get("overall_status") != "pass":
        raise ScorecardError(f"clean_profile summary for {hardware_class} is not pass")
    if (clean_profile.get("game_profile") or {}).get("gameid") != "ai_runtime":
        raise ScorecardError(f"clean_profile summary for {hardware_class} is not gameid=ai_runtime")
    comparison_summary = clean_profile.get("comparison_summary") or {}
    missing_sections = [
        section for section in REQUIRED_CLEAN_PROFILE_SECTIONS if section not in comparison_summary
    ]
    if missing_sections:
        raise ScorecardError(
            f"clean_profile summary incomplete for {hardware_class}; missing: "
            f"{', '.join(missing_sections)}"
        )

    return {
        "accepted_dir": accepted_dir,
        "manifest": manifest,
        "mutation": loaded_reports["mutation"],
        "demo_entity": loaded_reports["demo_entity"],
        "clean_profile": clean_profile,
    }


def measurement_status(lane: dict) -> str:
    measurements = lane["measurements"]
    health = measurements["clean_profile_server_health"]
    if measurements["failure_notes"]:
        return "needs-attention"
    if health["server_log_error_count"] > 0 or health["process_exited_unexpectedly"]:
        return "needs-attention"
    if health["actionable_server_log_warning_count"] > 0:
        return "watch"
    return "ready"


def player_probe_measurement(summary: dict) -> dict:
    probe = summary.get("player_load_tick_probe")
    if probe:
        return dict(probe)
    return {
        "probe_status": "missing",
        "probe_kind": "not_recorded",
        "sample_count": 0,
        "synthetic_player_count": 0,
        "headless_player_supported": False,
        "server_stayed_listening": None,
        "evidence_gap": "clean-profile summary has no player-load/server-step probe",
    }


def server_step_workload_measurement(summary: dict) -> dict:
    workload = summary.get("server_step_workload")
    if workload:
        return dict(workload)
    return {
        "workload_status": "missing",
        "workload_kind": "not_recorded",
        "attempted_sample_count": 0,
        "completed_sample_count": 0,
        "failed_sample_count": 0,
        "evidence_gap": "clean-profile summary has no bounded server-step workload",
    }


def cpu_measurement(summary: dict) -> dict:
    cpu = summary.get("cpu")
    if cpu:
        return dict(cpu)
    return {
        "sample_status": "missing",
        "cpu_sample_count": 0,
        "process_cpu_time_delta_seconds": None,
        "observed_wall_time_seconds": None,
        "avg_process_cpu_percent": None,
        "max_interval_cpu_percent": None,
        "sample_methods": [],
        "limitations": ["clean-profile summary has no CPU sampling evidence"],
    }


def first_party_agent_product_loop_measurement(summary: dict) -> dict:
    product_loop = summary.get("first_party_agent_product_loop")
    if product_loop:
        return dict(product_loop)
    return {
        "product_loop_status": "missing",
        "scenario_id": "first_party_agent_product_loop_approval",
        "approval_plan_count": 0,
        "approved_task_count": 0,
        "guide_command_checked": 0,
        "tasks_command_checked": 0,
        "cancel_command_checked": 0,
        "audit_review_checked": 0,
        "rollback_review_checked": 0,
        "defender_command_checked": 0,
        "import_preview_checked": 0,
        "blocked_or_unsafe_outcomes": None,
        "warning_count": 0,
        "error_count": 0,
        "evidence_gap": "clean-profile summary has no first-party agent product-loop evidence",
    }


def ai_runtime_scale_gate_measurement(summary: dict) -> dict:
    scale_gate = summary.get("ai_runtime_scale_gate")
    if scale_gate:
        return dict(scale_gate)
    return {
        "scale_gate_status": "missing",
        "gate_kind": "ai_runtime_multi_player_multi_agent_scale",
        "synthetic_disposable_only": None,
        "required_synthetic_player_count": 2,
        "required_concurrent_task_count": 2,
        "evidence_gap": "clean-profile summary has no multi-player and agent scale gate",
    }


def build_lane_evidence(hardware_class: str, accepted: dict) -> dict:
    manifest = accepted["manifest"]
    clean_profile = accepted["clean_profile"]
    summary = clean_profile["comparison_summary"]
    mutation_summary = dict(summary.get("mutation_write_throughput") or {})
    demo_summary = dict(summary.get("entity_runtime_operations") or {})
    if not mutation_summary:
        mutation_summary = summarize_mutation_report(accepted["mutation"])
    if not demo_summary:
        demo_summary = summarize_demo_report(accepted["demo_entity"])

    steady = summary["steady_tick_behavior"]
    startup = summary["startup"]
    failure_notes = list(clean_profile.get("failure_notes") or summary.get("failure_notes") or [])
    total_warning_count = steady.get("server_log_warning_count", 0)
    expected_warning_count = steady.get("expected_server_log_warning_count", 0)
    actionable_warning_count = steady.get(
        "actionable_server_log_warning_count",
        total_warning_count,
    )
    measurements = {
        "startup": {
            "listening": startup.get("listening"),
            "time_to_listen_ms": startup.get("time_to_listen_ms"),
            "startup_timeout_seconds": startup.get("startup_timeout_seconds"),
        },
        "clean_profile_server_health": {
            "overall_status": clean_profile.get("overall_status"),
            "process_exited_unexpectedly": steady.get("process_exited_unexpectedly"),
            "server_log_warning_count": total_warning_count,
            "expected_server_log_warning_count": expected_warning_count,
            "actionable_server_log_warning_count": actionable_warning_count,
            "expected_warning_kinds": list(steady.get("expected_warning_kinds") or []),
            "server_log_error_count": steady.get("server_log_error_count", 0),
            "idle_sample_seconds": steady.get("sample_seconds"),
            "observed_uptime_seconds": steady.get("observed_uptime_seconds"),
            "evidence_gap": "headless player load remains follow-on work",
        },
        "server_step_workload": server_step_workload_measurement(summary),
        "player_load_tick_probe": player_probe_measurement(summary),
        "mutation_write_throughput": mutation_summary,
        "first_party_agent_product_loop": first_party_agent_product_loop_measurement(summary),
        "ai_runtime_scale_gate": ai_runtime_scale_gate_measurement(summary),
        "demo_entity_runtime_cost": demo_summary,
        "map_chunk_workload": summary["map_chunk_workload"],
        "memory": summary["memory"],
        "cpu": cpu_measurement(summary),
        "failure_notes": failure_notes,
    }
    lane = {
        "hardware_class": hardware_class,
        "accepted_baseline": {
            "logical_dir": f"local/benchmarks/{hardware_class}/accepted",
            "luanti_commit": manifest.get("luanti_commit"),
            "source_label": manifest.get("source_label"),
            "source_capture": manifest.get("source_capture"),
        },
        "game_profile": clean_profile.get("game_profile") or {"gameid": "ai_runtime"},
        "measurements": measurements,
    }
    lane["status"] = measurement_status(lane)
    return lane


def target_bands() -> list[dict]:
    return [
        {
            "id": "startup_time",
            "metric": "startup.time_to_listen_ms",
            "target_by_hardware_class": {
                "local-mac": "<=500",
                "low-power-server": "<=1000",
            },
            "source": "project-target",
            "rationale": "Fast clean-profile startup keeps agent iteration and server restarts practical.",
        },
        {
            "id": "clean_profile_health",
            "metric": "clean_profile_server_health",
            "target": "listening=true, error_count=0, no unexpected process exit",
            "source": "project-target",
            "rationale": "The base AI runtime profile must be stable before compatibility/import expands.",
        },
        {
            "id": "player_load_tick_probe",
            "metric": "player_load_tick_probe",
            "target": "probe_status=pass with at least 2 connected headless synthetic players",
            "source": "project-target",
            "rationale": "Clean-profile runtime evidence needs multi-player load before compatibility/import workloads expand.",
        },
        {
            "id": "ai_runtime_scale_gate",
            "metric": "ai_runtime_scale_gate",
            "target": "scale_gate_status=pass with at least 2 synthetic players and 2 concurrent first-party tasks",
            "source": "project-target",
            "rationale": "Agent runtime work should prove multi-player and multi-agent evidence before alpha promotion.",
        },
        {
            "id": "map_chunk_workload",
            "metric": "map_chunk_workload",
            "target": "non-empty probe coverage with bounded sqlite growth",
            "source": "project-target",
            "rationale": "Minecraft-parity work needs real map/chunk evidence, not only empty-world startup.",
        },
        {
            "id": "mutation_throughput",
            "metric": "mutation_write_throughput",
            "target": "bounded node writes with rollback records before broader build tasks",
            "source": "project-target",
            "rationale": "AI build and repair work should scale through measured safe mutations.",
        },
        {
            "id": "entity_runtime_cost",
            "metric": "demo_entity_runtime_cost",
            "target": "larger helper-entity loads with zero cleanup residue",
            "source": "project-target",
            "rationale": "Agent helpers and future creatures need repeatable entity-runtime evidence.",
        },
        {
            "id": "memory",
            "metric": "memory.max_rss_kb",
            "target_by_hardware_class": {
                "local-mac": "<=65536",
                "low-power-server": "<=65536",
            },
            "source": "project-target",
            "rationale": "Low base memory keeps room for agents, mods, and imported content.",
        },
        {
            "id": "cpu",
            "metric": "cpu.avg_process_cpu_percent",
            "target_by_hardware_class": {
                "local-mac": "measured",
                "low-power-server": "measured",
            },
            "source": "project-target",
            "rationale": "Agent runtime work should expose process CPU cost before compatibility/import expands.",
        },
    ]


def build_gap(gap_id: str, priority: int, title: str, evidence: list[str], next_action: str) -> dict:
    return {
        "rank": priority,
        "id": gap_id,
        "status": "evidence_gap",
        "title": title,
        "evidence": evidence,
        "next_action": next_action,
    }


def measured_gap(gap_id: str, priority: int, title: str, evidence: list[str], next_action: str) -> dict:
    gap = build_gap(gap_id, priority, title, evidence, next_action)
    gap["status"] = "measured_gap"
    return gap


def has_complete_headless_player_evidence(probe: dict) -> bool:
    if probe.get("probe_status") != "pass":
        return False
    if not probe.get("headless_player_supported"):
        return False
    synthetic = probe.get("synthetic_player_count") or 0
    attempted = probe.get("attempted_synthetic_player_count")
    connected = probe.get("connected_synthetic_player_count")
    if attempted is None:
        attempted = synthetic
    if connected is None:
        connected = synthetic
    cleanup_status = probe.get("cleanup_status")
    return (
        synthetic >= 2
        and attempted >= 2
        and connected >= attempted
        and cleanup_status in (None, "complete", "terminated")
    )


def build_ranked_gaps(lanes: list[dict]) -> list[dict]:
    gaps = []
    if any(lane["measurements"]["failure_notes"] for lane in lanes):
        gaps.append(
            build_gap(
                "clean_profile_failure_notes",
                1,
                "Resolve accepted clean-profile failure notes",
                [
                    f"{lane['hardware_class']}: {', '.join(lane['measurements']['failure_notes'])}"
                    for lane in lanes
                    if lane["measurements"]["failure_notes"]
                ],
                "Refresh accepted clean-profile baselines only after failure notes are eliminated.",
            )
        )

    player_probes = [
        lane["measurements"]["player_load_tick_probe"]
        for lane in lanes
    ]
    server_step_workloads = [
        lane["measurements"]["server_step_workload"]
        for lane in lanes
    ]
    if any(workload.get("workload_status") == "missing" for workload in server_step_workloads):
        gaps.append(
            build_gap(
                "server_step_workload",
                2,
                "Add bounded server-step workload evidence",
                [
                    f"{lane['hardware_class']}: "
                    f"{lane['measurements']['server_step_workload'].get('evidence_gap')}"
                    for lane in lanes
                    if lane["measurements"]["server_step_workload"].get("workload_status") == "missing"
                ],
                "Refresh clean-profile captures with server_step_workload evidence.",
            )
        )
    elif any(workload.get("workload_status") != "pass" for workload in server_step_workloads):
        gaps.append(
            measured_gap(
                "server_step_workload_failure",
                2,
                "Fix failing bounded server-step workload",
                [
                    f"{lane['hardware_class']}: workload_status="
                    f"{lane['measurements']['server_step_workload'].get('workload_status')}, "
                    f"failed_sample_count="
                    f"{lane['measurements']['server_step_workload'].get('failed_sample_count')}"
                    for lane in lanes
                    if lane["measurements"]["server_step_workload"].get("workload_status") != "pass"
                ],
                "Stabilize clean-profile server-step sampling before heavier player-load probes.",
            )
        )
    if any(probe.get("probe_status") == "missing" for probe in player_probes):
        gaps.append(
            build_gap(
                "player_load_tick_probe",
                2,
                "Add player-load and server-step probes",
                [
                    f"{lane['hardware_class']}: "
                    f"{lane['measurements']['player_load_tick_probe'].get('evidence_gap')}"
                    for lane in lanes
                    if lane["measurements"]["player_load_tick_probe"].get("probe_status") == "missing"
                ],
                "Add a bounded synthetic player/tick workload to clean-profile capture.",
            )
        )
    elif any(probe.get("probe_status") != "pass" for probe in player_probes):
        gaps.append(
            measured_gap(
                "player_load_tick_probe_failure",
                2,
                "Fix failing player-load/server-step probe",
                [
                    f"{lane['hardware_class']}: probe_status="
                    f"{lane['measurements']['player_load_tick_probe'].get('probe_status')}"
                    for lane in lanes
                    if lane["measurements"]["player_load_tick_probe"].get("probe_status") != "pass"
                ],
                "Stabilize clean-profile sampling before adding heavier runtime workloads.",
            )
        )
    elif any(not has_complete_headless_player_evidence(probe) for probe in player_probes):
        gaps.append(
            measured_gap(
                "headless_player_load_probe",
                2,
                "Add true synthetic player load after server-step liveness is measured",
                [
                    f"{lane['hardware_class']}: synthetic_player_count="
                    f"{lane['measurements']['player_load_tick_probe'].get('synthetic_player_count')}, "
                    f"attempted_synthetic_player_count="
                    f"{lane['measurements']['player_load_tick_probe'].get('attempted_synthetic_player_count')}, "
                    f"connected_synthetic_player_count="
                    f"{lane['measurements']['player_load_tick_probe'].get('connected_synthetic_player_count')}, "
                    f"headless_player_supported="
                    f"{lane['measurements']['player_load_tick_probe'].get('headless_player_supported')}"
                    for lane in lanes
                ],
                "Wire a public-safe headless-client or synthetic player path and keep this server-step probe as the base liveness signal.",
            )
        )

    scale_gates = [
        lane["measurements"]["ai_runtime_scale_gate"]
        for lane in lanes
    ]
    if any(scale_gate.get("scale_gate_status") != "pass" for scale_gate in scale_gates):
        gaps.append(
            measured_gap(
                "ai_runtime_scale_gate",
                3,
                "Prove multi-player and multi-agent scale gate",
                [
                    f"{lane['hardware_class']}: scale_gate_status="
                    f"{lane['measurements']['ai_runtime_scale_gate'].get('scale_gate_status')}, "
                    f"required_synthetic_player_count="
                    f"{lane['measurements']['ai_runtime_scale_gate'].get('required_synthetic_player_count')}, "
                    f"required_concurrent_task_count="
                    f"{lane['measurements']['ai_runtime_scale_gate'].get('required_concurrent_task_count')}"
                    for lane in lanes
                    if lane["measurements"]["ai_runtime_scale_gate"].get("scale_gate_status") != "pass"
                ],
                "Refresh accepted clean-profile captures with ai_runtime_scale_gate=pass.",
            )
        )

    if any(
        (lane["measurements"]["map_chunk_workload"].get("mapblock_rows") or 0) == 0
        for lane in lanes
    ):
        gaps.append(
            build_gap(
                "non_empty_map_chunk_workload",
                4,
                "Measure non-empty map/chunk workload",
                [
                    f"{lane['hardware_class']}: mapblock_rows="
                    f"{lane['measurements']['map_chunk_workload'].get('mapblock_rows')}"
                    for lane in lanes
                ],
                "Add a disposable mapgen or node-write probe that records mapblock rows and sqlite growth.",
            )
        )

    if any(
        (lane["measurements"]["demo_entity_runtime_cost"].get("max_entity_count") or 0) < 16
        for lane in lanes
    ):
        gaps.append(
            build_gap(
                "entity_scale_runtime_probe",
                5,
                "Scale demo entity runtime coverage",
                [
                    f"{lane['hardware_class']}: max_entity_count="
                    f"{lane['measurements']['demo_entity_runtime_cost'].get('max_entity_count')}"
                    for lane in lanes
                ],
                "Add a larger helper-entity scenario before shipping creature or vehicle plugins.",
            )
        )

    if any(
        (lane["measurements"]["mutation_write_throughput"].get("total_node_writes") or 0) == 0
        for lane in lanes
    ):
        gaps.append(
            build_gap(
                "mutation_total_write_measurement",
                6,
                "Record total node writes in mutation reports",
                [
                    f"{lane['hardware_class']}: total_node_writes="
                    f"{lane['measurements']['mutation_write_throughput'].get('total_node_writes')}"
                    for lane in lanes
                ],
                "Extend mutation scenarios to report total writes, not only per-step write budgets.",
            )
        )

    if any(
        lane["measurements"]["cpu"].get("sample_status") != "measured"
        for lane in lanes
    ):
        gaps.append(
            build_gap(
                "clean_profile_cpu_sampling",
                7,
                "Add clean-profile CPU sampling evidence",
                [
                    f"{lane['hardware_class']}: sample_status="
                    f"{lane['measurements']['cpu'].get('sample_status')}, "
                    f"cpu_sample_count="
                    f"{lane['measurements']['cpu'].get('cpu_sample_count')}"
                    for lane in lanes
                    if lane["measurements"]["cpu"].get("sample_status") != "measured"
                ],
                "Refresh accepted clean-profile captures with bounded process CPU sampling.",
            )
        )

    if any(
        (
            lane["measurements"]["clean_profile_server_health"].get(
                "actionable_server_log_warning_count"
            )
            or 0
        )
        > 0
        for lane in lanes
    ):
        gaps.append(
            build_gap(
                "server_log_warning_cleanup",
                8,
                "Classify or eliminate clean-profile warnings",
                [
                    f"{lane['hardware_class']}: actionable_warning_count="
                    f"{lane['measurements']['clean_profile_server_health'].get('actionable_server_log_warning_count')}, "
                    f"total_warning_count="
                    f"{lane['measurements']['clean_profile_server_health'].get('server_log_warning_count')}"
                    for lane in lanes
                ],
                "Split expected startup warnings from actionable warnings in clean-profile capture.",
            )
        )

    return sorted(gaps, key=lambda item: item["rank"])


def build_scorecard(output_root: Path, hardware_classes: list[str]) -> dict:
    lanes = [
        build_lane_evidence(hardware_class, load_accepted_lane(output_root, hardware_class))
        for hardware_class in hardware_classes
    ]
    return {
        "schema_version": 1,
        "runner_version": RUNNER_VERSION,
        "generated_at": utc_now(),
        "overall_status": "gap-scorecard-ready",
        "hardware_classes": hardware_classes,
        "run_context": {
            "mode": "accepted-clean-profile-gap-scorecard",
            "requires_private_world": False,
            "requires_private_assets": False,
            "requires_live_pi": False,
            "requires_model_network": False,
        },
        "target_policy": {
            "summary": (
                "Minecraft-parity target bands are project targets, not measurements copied "
                "from proprietary Minecraft code, assets, server jars, or benchmark data."
            ),
            "measured_evidence_is_separate": True,
        },
        "target_bands": target_bands(),
        "measured_evidence": lanes,
        "ranked_gaps": build_ranked_gaps(lanes),
        "privacy_scan": {
            "status": "passed",
            "scope": "scorecard JSON payload",
            "blocked_patterns": [
                "private hosts",
                "private network addresses",
                "local absolute paths",
                "secrets",
                "provider prompts",
                "private showcase names",
            ],
        },
        "notes": [
            "Scorecard reads accepted clean-profile baselines only.",
            "Generated scorecards are local benchmark artifacts by default.",
            "Compatibility/import expansion should wait for the ranked runtime gaps to close.",
        ],
    }


def scan_public_payload(payload: dict) -> list[str]:
    serialized = json.dumps(payload, sort_keys=True)
    return sorted({match.group(0) for match in PRIVATE_PATTERNS.finditer(serialized)})


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Build a clean-profile runtime gap scorecard from accepted local baselines."
    )
    parser.add_argument(
        "--output-root",
        default=str(ROOT / "local" / "benchmarks"),
        help="Benchmark retention root. Default: local/benchmarks.",
    )
    parser.add_argument(
        "--hardware-class",
        action="append",
        choices=DEFAULT_HARDWARE_CLASSES,
        help="Hardware class to include. Repeatable. Default: local-mac and low-power-server.",
    )
    parser.add_argument(
        "--output",
        help="Output JSON path. Default: <output-root>/runtime-gap-scorecard.json.",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    output_root = Path(args.output_root)
    hardware_classes = args.hardware_class or list(DEFAULT_HARDWARE_CLASSES)
    try:
        scorecard = build_scorecard(output_root, list(hardware_classes))
        private_matches = scan_public_payload(scorecard)
        if private_matches:
            raise ScorecardError(
                "scorecard privacy scan failed: " + ", ".join(private_matches)
            )
        output_path = Path(args.output) if args.output else output_root / "runtime-gap-scorecard.json"
        write_json(output_path, scorecard)
    except (FileNotFoundError, json.JSONDecodeError, ScorecardError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
