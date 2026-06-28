#!/usr/bin/env python3
"""Build a public-safe Minecraft-parity comparison report from local benchmarks."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import ai_native_runtime_gap_scorecard as scorecard


ROOT = Path(__file__).resolve().parents[1]
RUNNER_VERSION = "ai-native-minecraft-parity-harness:v1"
DEFAULT_HARDWARE_CLASSES = ("local-mac", "low-power-server")
PRIVATE_PATTERNS = re.compile(
    r"minecraftpi|192\.168|spacebase|themepark|showcase100|disneyland100|"
    r"sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY|private_prompt|asset_payload|"
    r"/Users/|/opt/|bill@",
    re.I,
)


class HarnessError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def comparison_dimensions() -> list[dict]:
    return [
        {
            "id": "startup",
            "title": "Startup to listening socket",
            "measured_metric_paths": ["startup.time_to_listen_ms", "startup.listening"],
            "target_kind": "project_target",
            "public_safe_source": "clean ai_runtime profile capture",
        },
        {
            "id": "player_join_liveness",
            "title": "Player join and liveness",
            "measured_metric_paths": [
                "player_load_tick_probe.synthetic_player_count",
                "player_load_tick_probe.connected_synthetic_player_count",
                "player_load_tick_probe.server_stayed_listening",
            ],
            "target_kind": "project_target",
            "public_safe_source": "headless client probe or bounded server-process liveness probe",
        },
        {
            "id": "server_step_stability",
            "title": "Server-step stability",
            "measured_metric_paths": [
                "server_step_workload.completed_sample_count",
                "server_step_workload.failed_sample_count",
                "server_step_workload.p95_sample_interval_ms",
            ],
            "target_kind": "project_target",
            "public_safe_source": "bounded synthetic server-step workload",
        },
        {
            "id": "mapblock_chunk_churn",
            "title": "Mapblock and chunk churn",
            "measured_metric_paths": [
                "map_chunk_workload.mapblock_rows",
                "map_chunk_workload.map_sqlite_bytes",
            ],
            "target_kind": "project_target",
            "public_safe_source": "disposable synthetic ai_runtime world",
        },
        {
            "id": "entity_load",
            "title": "Entity load",
            "measured_metric_paths": [
                "demo_entity_runtime_cost.max_entity_count",
                "demo_entity_runtime_cost.max_active_peak",
                "demo_entity_runtime_cost.max_remaining_entities",
            ],
            "target_kind": "project_target",
            "public_safe_source": "generic demo helper entity fixture",
        },
        {
            "id": "world_edit_throughput",
            "title": "World-edit throughput",
            "measured_metric_paths": [
                "mutation_write_throughput.total_node_writes",
                "mutation_write_throughput.max_node_writes_per_step",
                "mutation_write_throughput.total_rollback_records",
            ],
            "target_kind": "project_target",
            "public_safe_source": "synthetic rollback-backed mutation scenarios",
        },
        {
            "id": "memory",
            "title": "Memory use",
            "measured_metric_paths": ["memory.max_rss_kb", "memory.rss_sample_count"],
            "target_kind": "project_target",
            "public_safe_source": "clean-profile process sampling",
        },
        {
            "id": "cpu",
            "title": "CPU load",
            "measured_metric_paths": [],
            "target_kind": "project_target",
            "public_safe_source": "not yet measured by accepted clean-profile captures",
        },
        {
            "id": "latency",
            "title": "Latency",
            "measured_metric_paths": [
                "server_step_workload.p95_sample_interval_ms",
                "player_load_tick_probe.p95_sample_interval_ms",
            ],
            "target_kind": "project_target",
            "public_safe_source": "server-step interval proxy; network RTT remains future work",
        },
    ]


def metric_status(value) -> bool:
    return value is not None and value is not False


def result(dimension_id: str, status: str, metrics: dict, evidence: str) -> dict:
    return {
        "dimension_id": dimension_id,
        "status": status,
        "metrics": metrics,
        "evidence": evidence,
        "measured_facts_are_project_fork_only": True,
    }


def gap(hardware_class: str, dimension_id: str, title: str, evidence: str, next_action: str) -> dict:
    return {
        "hardware_class": hardware_class,
        "dimension_id": dimension_id,
        "status": "qualitative_gap",
        "title": title,
        "evidence": evidence,
        "next_action": next_action,
    }


def dimension_results(hardware_class: str, measurements: dict) -> tuple[list[dict], list[dict]]:
    facts: list[dict] = []
    gaps: list[dict] = []
    startup = measurements["startup"]
    player_probe = measurements["player_load_tick_probe"]
    workload = measurements["server_step_workload"]
    map_chunk = measurements["map_chunk_workload"]
    entity = measurements["demo_entity_runtime_cost"]
    mutation = measurements["mutation_write_throughput"]
    memory = measurements["memory"]

    startup_ready = startup.get("listening") is True and metric_status(startup.get("time_to_listen_ms"))
    facts.append(
        result(
            "startup",
            "measured" if startup_ready else "evidence_gap",
            {
                "listening": startup.get("listening"),
                "time_to_listen_ms": startup.get("time_to_listen_ms"),
                "startup_timeout_seconds": startup.get("startup_timeout_seconds"),
            },
            "clean-profile startup capture",
        )
    )
    if not startup_ready:
        gaps.append(
            gap(
                hardware_class,
                "startup",
                "Startup listening evidence is incomplete",
                f"listening={startup.get('listening')} time_to_listen_ms={startup.get('time_to_listen_ms')}",
                "Refresh accepted clean-profile capture and keep startup evidence in the local baseline lane.",
            )
        )

    synthetic_count = player_probe.get("synthetic_player_count") or 0
    connected = player_probe.get("connected_synthetic_player_count")
    if connected is None:
        connected = synthetic_count
    true_player_load = (
        player_probe.get("probe_status") == "pass"
        and player_probe.get("headless_player_supported") is True
        and synthetic_count > 0
        and connected >= synthetic_count
    )
    probe_status = "measured" if true_player_load else "proxy_only"
    facts.append(
        result(
            "player_join_liveness",
            probe_status,
            {
                "probe_status": player_probe.get("probe_status"),
                "probe_kind": player_probe.get("probe_kind"),
                "synthetic_player_count": synthetic_count,
                "connected_synthetic_player_count": connected,
                "headless_player_supported": player_probe.get("headless_player_supported"),
                "server_stayed_listening": player_probe.get("server_stayed_listening"),
            },
            "headless client load when available; otherwise server-process liveness proxy",
        )
    )
    if not true_player_load:
        gaps.append(
            gap(
                hardware_class,
                "player_join_liveness",
                "Replace liveness proxy with true synthetic player joins",
                f"probe_kind={player_probe.get('probe_kind')} synthetic_player_count={synthetic_count}",
                "Wire a public-safe headless client command into benchmark capture for this hardware lane.",
            )
        )

    workload_ready = (
        workload.get("workload_status") == "pass"
        and (workload.get("completed_sample_count") or 0) > 0
        and (workload.get("failed_sample_count") or 0) == 0
    )
    facts.append(
        result(
            "server_step_stability",
            "measured" if workload_ready else "evidence_gap",
            {
                "workload_status": workload.get("workload_status"),
                "completed_sample_count": workload.get("completed_sample_count"),
                "failed_sample_count": workload.get("failed_sample_count"),
                "p95_sample_interval_ms": workload.get("p95_sample_interval_ms"),
                "max_sample_interval_ms": workload.get("max_sample_interval_ms"),
            },
            "bounded clean-profile server-step workload",
        )
    )
    if not workload_ready:
        gaps.append(
            gap(
                hardware_class,
                "server_step_stability",
                "Server-step workload evidence is missing or failing",
                f"workload_status={workload.get('workload_status')}",
                "Refresh clean-profile capture with passing server-step workload samples.",
            )
        )

    map_ready = (map_chunk.get("mapblock_rows") or 0) > 0
    facts.append(
        result(
            "mapblock_chunk_churn",
            "measured" if map_ready else "evidence_gap",
            {
                "world_backend": map_chunk.get("world_backend"),
                "map_sqlite_bytes": map_chunk.get("map_sqlite_bytes"),
                "mapblock_rows": map_chunk.get("mapblock_rows"),
                "inspection_status": map_chunk.get("inspection_status"),
            },
            "disposable clean-profile map/chunk inspection",
        )
    )
    if not map_ready:
        gaps.append(
            gap(
                hardware_class,
                "mapblock_chunk_churn",
                "Add non-empty mapblock/chunk churn evidence",
                f"mapblock_rows={map_chunk.get('mapblock_rows')}",
                "Add a public-safe mapgen or chunk-touch probe to benchmark capture.",
            )
        )

    entity_ready = (entity.get("max_entity_count") or 0) >= 16 and (
        entity.get("max_remaining_entities") or 0
    ) == 0
    facts.append(
        result(
            "entity_load",
            "measured" if entity_ready else "partial",
            {
                "max_entity_count": entity.get("max_entity_count"),
                "max_active_peak": entity.get("max_active_peak"),
                "max_remaining_entities": entity.get("max_remaining_entities"),
                "warnings": entity.get("warnings"),
                "errors": entity.get("errors"),
            },
            "generic demo helper entity benchmark",
        )
    )
    if not entity_ready:
        gaps.append(
            gap(
                hardware_class,
                "entity_load",
                "Scale entity-load evidence",
                f"max_entity_count={entity.get('max_entity_count')} remaining={entity.get('max_remaining_entities')}",
                "Refresh accepted baselines with the scale-16 generic helper entity scenario.",
            )
        )

    mutation_ready = (mutation.get("total_node_writes") or 0) > 0
    facts.append(
        result(
            "world_edit_throughput",
            "measured" if mutation_ready else "evidence_gap",
            {
                "total_node_writes": mutation.get("total_node_writes"),
                "max_node_writes_per_step": mutation.get("max_node_writes_per_step"),
                "total_rollback_records": mutation.get("total_rollback_records"),
                "warnings": mutation.get("warnings"),
                "errors": mutation.get("errors"),
            },
            "synthetic rollback-backed mutation benchmark",
        )
    )
    if not mutation_ready:
        gaps.append(
            gap(
                hardware_class,
                "world_edit_throughput",
                "Record real total node-write throughput",
                f"total_node_writes={mutation.get('total_node_writes')}",
                "Extend mutation reports so accepted baselines include nonzero total writes.",
            )
        )

    memory_ready = metric_status(memory.get("max_rss_kb"))
    facts.append(
        result(
            "memory",
            "measured" if memory_ready else "evidence_gap",
            {
                "max_rss_kb": memory.get("max_rss_kb"),
                "rss_sample_count": memory.get("rss_sample_count"),
            },
            "clean-profile process memory sampling",
        )
    )
    if not memory_ready:
        gaps.append(
            gap(
                hardware_class,
                "memory",
                "Add memory sampling evidence",
                f"max_rss_kb={memory.get('max_rss_kb')}",
                "Refresh clean-profile capture with process RSS sampling enabled.",
            )
        )

    facts.append(
        result(
            "cpu",
            "evidence_gap",
            {},
            "accepted clean-profile capture does not yet record CPU load",
        )
    )
    gaps.append(
        gap(
            hardware_class,
            "cpu",
            "Add CPU load sampling",
            "accepted clean-profile capture has no CPU metrics",
            "Add bounded CPU sampling to benchmark capture for local and low-power lanes.",
        )
    )

    latency_metrics = {
        "server_step_p95_sample_interval_ms": workload.get("p95_sample_interval_ms"),
        "server_step_max_sample_interval_ms": workload.get("max_sample_interval_ms"),
        "player_probe_p95_sample_interval_ms": player_probe.get("p95_sample_interval_ms"),
        "network_rtt_ms": None,
    }
    facts.append(
        result(
            "latency",
            "proxy_only",
            latency_metrics,
            "server-step interval proxy; no network RTT benchmark yet",
        )
    )
    gaps.append(
        gap(
            hardware_class,
            "latency",
            "Add true client/server latency evidence",
            "network_rtt_ms is not measured by accepted clean-profile capture",
            "Add a public-safe headless client latency probe after synthetic player joins are stable.",
        )
    )

    return facts, gaps


def build_report(output_root: Path, hardware_classes: list[str]) -> dict:
    lanes = [
        scorecard.build_lane_evidence(
            hardware_class,
            scorecard.load_accepted_lane(output_root, hardware_class),
        )
        for hardware_class in hardware_classes
    ]
    measured_facts = []
    qualitative_gaps = []
    for lane in lanes:
        facts, gaps = dimension_results(lane["hardware_class"], lane["measurements"])
        measured_facts.append(
            {
                "hardware_class": lane["hardware_class"],
                "accepted_baseline": lane["accepted_baseline"],
                "game_profile": lane["game_profile"],
                "dimension_results": facts,
            }
        )
        qualitative_gaps.extend(gaps)

    report = {
        "schema_version": 1,
        "runner_version": RUNNER_VERSION,
        "generated_at": utc_now(),
        "overall_status": "minecraft-parity-report-ready",
        "hardware_classes": hardware_classes,
        "run_context": {
            "mode": "public-safe-minecraft-parity-comparison",
            "requires_private_world": False,
            "requires_private_assets": False,
            "requires_live_pi": False,
            "requires_model_network": False,
        },
        "source_policy": {
            "uses_proprietary_minecraft_code_or_assets": False,
            "uses_copied_server_jars_or_game_data": False,
            "operator_supplied_external_references_allowed": True,
            "measured_facts_are_separate_from_project_targets": True,
        },
        "comparison_dimensions": comparison_dimensions(),
        "measured_facts": measured_facts,
        "qualitative_minecraft_parity_gaps": qualitative_gaps,
        "retention": {
            "logical_default_output": "local/benchmarks/minecraft-parity-comparison-report.json",
            "same_lane_as": "local/benchmarks/<hardware-class>/accepted/",
            "committed": False,
        },
        "privacy_scan": {
            "status": "passed",
            "scope": "report JSON payload",
        },
    }
    serialized = json.dumps(report, sort_keys=True)
    if PRIVATE_PATTERNS.search(serialized):
        raise HarnessError("privacy scan failed for Minecraft-parity comparison report")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a public-safe Minecraft-parity comparison report from local baselines."
    )
    parser.add_argument(
        "--output-root",
        default=str(ROOT / "local" / "benchmarks"),
        help="Benchmark retention root, usually local/benchmarks.",
    )
    parser.add_argument(
        "--hardware-class",
        action="append",
        choices=DEFAULT_HARDWARE_CLASSES,
        help="Hardware class to include. Defaults to both accepted lanes.",
    )
    parser.add_argument(
        "--output",
        help="Report output path. Defaults to <output-root>/minecraft-parity-comparison-report.json.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_root = Path(args.output_root)
    hardware_classes = args.hardware_class or list(DEFAULT_HARDWARE_CLASSES)
    output = Path(args.output) if args.output else output_root / "minecraft-parity-comparison-report.json"
    try:
        report = build_report(output_root, hardware_classes)
        write_json(output, report)
    except (HarnessError, scorecard.ScorecardError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
