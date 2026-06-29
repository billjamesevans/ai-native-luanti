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
IMPORT_INVENTORY_DISCOVERY_REPORT = "compatibility-import-inventory-discovery-report.json"
SCORECARD_STATUS_CRITERIA = {
    "pass": "Measured evidence meets the current project target for this dimension.",
    "warn": "Evidence is partial, proxy-only, or below the target but still safe and informative.",
    "fail": "Evidence is missing, failing, private, unsafe, or not yet reproducible.",
}
STATUS_TO_SCORECARD = {
    "measured": "pass",
    "partial": "warn",
    "proxy_only": "warn",
    "measured_failure": "fail",
    "evidence_gap": "fail",
    "qualitative_gap": "fail",
}
GAP_AREAS = ("engine_runtime", "game_content", "first_party_plugin", "operator_experience")
ACTIONABLE_GAP_AREA_PRIORITY = {
    "engine_runtime": 0,
    "first_party_plugin": 1,
    "operator_experience": 2,
    "game_content": 3,
}
ACTIONABLE_STATUS_PRIORITY = {
    "fail": 0,
    "warn": 1,
    "pass": 2,
}
PRIVATE_PATTERNS = re.compile(
    r"minecraftpi|192\.168|spacebase|themepark|showcase100|disneyland100|"
    r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY|private_prompt|asset_payload|"
    r"/Users/|/opt/|bill@",
    re.I,
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


class HarnessError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def comparison_dimension(
    dimension_id: str,
    title: str,
    measured_metric_paths: list[str],
    gap_area: str,
    public_safe_source: str,
) -> dict:
    return {
        "id": dimension_id,
        "title": title,
        "gap_area": gap_area,
        "scorecard_criteria": SCORECARD_STATUS_CRITERIA,
        "measured_metric_paths": measured_metric_paths,
        "target_kind": "project_target",
        "public_safe_source": public_safe_source,
    }


def comparison_dimensions() -> list[dict]:
    return [
        comparison_dimension(
            "startup",
            "Startup to listening socket",
            ["startup.time_to_listen_ms", "startup.listening"],
            "engine_runtime",
            "clean ai_runtime profile capture",
        ),
        comparison_dimension(
            "player_join_liveness",
            "Player join and liveness",
            [
                "player_load_tick_probe.synthetic_player_count",
                "player_load_tick_probe.connected_synthetic_player_count",
                "player_load_tick_probe.server_stayed_listening",
            ],
            "engine_runtime",
            "headless client probe or bounded server-process liveness probe",
        ),
        comparison_dimension(
            "server_step_stability",
            "Server-step stability",
            [
                "server_step_workload.completed_sample_count",
                "server_step_workload.failed_sample_count",
                "server_step_workload.p95_sample_interval_ms",
            ],
            "engine_runtime",
            "bounded synthetic server-step workload",
        ),
        comparison_dimension(
            "mapblock_chunk_churn",
            "Mapblock and chunk churn",
            [
                "map_chunk_workload.mapblock_rows",
                "map_chunk_workload.map_sqlite_bytes",
            ],
            "engine_runtime",
            "disposable synthetic ai_runtime world",
        ),
        comparison_dimension(
            "entity_load",
            "Entity load",
            [
                "demo_entity_runtime_cost.max_entity_count",
                "demo_entity_runtime_cost.max_active_peak",
                "demo_entity_runtime_cost.max_remaining_entities",
            ],
            "game_content",
            "generic demo helper entity fixture",
        ),
        comparison_dimension(
            "world_edit_throughput",
            "World-edit throughput",
            [
                "mutation_write_throughput.total_node_writes",
                "mutation_write_throughput.max_node_writes_per_step",
                "mutation_write_throughput.total_rollback_records",
            ],
            "engine_runtime",
            "synthetic rollback-backed mutation scenarios",
        ),
        comparison_dimension(
            "persistence",
            "Persistence and retained state",
            [
                "map_chunk_workload.map_sqlite_bytes",
                "mutation_write_throughput.total_rollback_records",
            ],
            "engine_runtime",
            "disposable SQLite map plus rollback metadata evidence",
        ),
        comparison_dimension(
            "mod_plugin_ergonomics",
            "Mod/plugin ergonomics",
            [
                "agent_runtime.capability_profile",
                "operator_status.runtime_surfaces",
                "first_party_plugin.contract_status",
            ],
            "first_party_plugin",
            "clean ai_runtime product surfaces plus first-party plugin contracts",
        ),
        comparison_dimension(
            "operator_visibility",
            "Operator visibility",
            [
                "operator_status.command_available",
                "operator_task_control.command_available",
                "runtime_verifier.operator_artifacts",
            ],
            "operator_experience",
            "clean runtime operator status and task-control command probes",
        ),
        comparison_dimension(
            "recovery",
            "Recovery and rollback",
            [
                "mutation_write_throughput.total_rollback_records",
                "operator_task_control.no_world_mutation",
            ],
            "operator_experience",
            "rollback-backed mutation scenarios and receipt-gated task control",
        ),
        comparison_dimension(
            "memory",
            "Memory use",
            ["memory.max_rss_kb", "memory.rss_sample_count"],
            "engine_runtime",
            "clean-profile process sampling",
        ),
        comparison_dimension(
            "cpu",
            "CPU load",
            [
                "cpu.avg_process_cpu_percent",
                "cpu.max_interval_cpu_percent",
                "cpu.cpu_sample_count",
            ],
            "engine_runtime",
            "clean-profile process CPU sampling",
        ),
        comparison_dimension(
            "latency",
            "Latency",
            [
                "player_load_tick_probe.join_latency_proxy_ms.p95",
                "player_load_tick_probe.join_latency_proxy_ms.max",
                "player_load_tick_probe.latency_proxy_supported",
            ],
            "engine_runtime",
            "headless client join-log observation proxy; network RTT remains future work",
        ),
    ]


def benchmark_scenarios() -> list[dict]:
    scenarios = [
        ("clean_profile_startup", "Clean ai_runtime startup and listening socket"),
        ("server_step_liveness", "Bounded server-step liveness sampling"),
        ("headless_player_join", "Public-safe synthetic headless player join"),
        ("synthetic_mapblock_churn", "Disposable synthetic mapblock/chunk churn"),
        ("generic_entity_scale", "Generic helper entity scaling"),
        ("rollback_backed_world_edit", "Rollback-backed synthetic world edits"),
        ("operator_status_and_task_control", "Operator status plus receipt-gated task control"),
    ]
    return [
        {
            "id": scenario_id,
            "title": title,
            "safe_for_local": True,
            "safe_for_side_by_side_pi": True,
            "requires_private_world": False,
            "uses_proprietary_minecraft_assets": False,
        }
        for scenario_id, title in scenarios
    ]


def dimension_gap_area(dimension_id: str) -> str:
    for dimension in comparison_dimensions():
        if dimension["id"] == dimension_id:
            return dimension["gap_area"]
    return "engine_runtime"


def metric_status(value) -> bool:
    return value is not None and value is not False


def compatibility_import_inventory_missing() -> dict:
    return {
        "status": "missing",
        "compatibility_import_inventory_ready": False,
        "sources_total": 0,
        "inventory_items_total": 0,
        "planned_actions_total": 0,
        "source_status_counts": {},
        "by_source_class": {},
        "evidence_gap": "compatibility import inventory discovery report missing",
    }


def load_compatibility_import_inventory(output_root: Path) -> dict:
    path = output_root / IMPORT_INVENTORY_DISCOVERY_REPORT
    if not path.is_file():
        return compatibility_import_inventory_missing()
    payload = json.loads(path.read_text(encoding="utf-8"))
    serialized = json.dumps(payload, sort_keys=True)
    if PRIVATE_PATTERNS.search(serialized):
        raise HarnessError("privacy scan failed for compatibility import inventory discovery")
    summary = payload.get("summary") or {}
    safety = payload.get("safety") or {}
    ready = (
        payload.get("mode") == "import_inventory_discovery"
        and payload.get("status") == "ready_for_import_preview"
        and summary.get("compatibility_import_inventory_ready") is True
        and safety.get("dry_run_only") is True
        and safety.get("no_assets_copied") is True
        and safety.get("no_world_mutation") is True
        and safety.get("source_paths_redacted") is True
        and safety.get("no_raw_payloads") is True
        and safety.get("no_private_paths") is True
        and safety.get("uses_proprietary_minecraft_code_or_assets") is False
        and safety.get("uses_copied_server_jars_or_game_data") is False
    )
    return {
        "status": payload.get("status"),
        "compatibility_import_inventory_ready": ready,
        "sources_total": summary.get("sources_total", 0),
        "inventory_items_total": summary.get("inventory_items_total", 0),
        "planned_actions_total": summary.get("planned_actions_total", 0),
        "source_status_counts": dict(summary.get("source_status_counts") or {}),
        "by_source_class": dict(summary.get("by_source_class") or {}),
        "required_capabilities": list(summary.get("required_capabilities") or []),
        "logical_report_path": f"local/benchmarks/{IMPORT_INVENTORY_DISCOVERY_REPORT}",
        "blocking_reasons": list((payload.get("readiness") or {}).get("blocking_reasons") or []),
    }


def numeric_metric(value) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    return 0


def has_first_party_agent_product_loop_evidence(product_loop: dict) -> bool:
    return (
        product_loop.get("product_loop_status") == "pass"
        and all(
            numeric_metric(product_loop.get(metric)) >= threshold
            for metric, threshold in FIRST_PARTY_AGENT_PRODUCT_LOOP_THRESHOLDS.items()
        )
        and numeric_metric(product_loop.get("blocked_or_unsafe_outcomes")) == 0
        and numeric_metric(product_loop.get("warning_count")) == 0
        and numeric_metric(product_loop.get("error_count")) == 0
    )


def result(dimension_id: str, status: str, metrics: dict, evidence: str) -> dict:
    return {
        "dimension_id": dimension_id,
        "status": status,
        "scorecard_status": STATUS_TO_SCORECARD.get(status, "fail"),
        "gap_area": dimension_gap_area(dimension_id),
        "metrics": metrics,
        "evidence": evidence,
        "measured_facts_are_project_fork_only": True,
    }


def gap(hardware_class: str, dimension_id: str, title: str, evidence: str, next_action: str) -> dict:
    gap_area = dimension_gap_area(dimension_id)
    return {
        "hardware_class": hardware_class,
        "dimension_id": dimension_id,
        "status": "qualitative_gap",
        "scorecard_status": "fail",
        "gap_area": gap_area,
        "title": title,
        "evidence": evidence,
        "next_action": next_action,
    }


def dimension_results(
    hardware_class: str,
    measurements: dict,
    compatibility_import_inventory: dict | None = None,
) -> tuple[list[dict], list[dict]]:
    facts: list[dict] = []
    gaps: list[dict] = []
    startup = measurements["startup"]
    player_probe = measurements["player_load_tick_probe"]
    workload = measurements["server_step_workload"]
    map_chunk = measurements["map_chunk_workload"]
    entity = measurements["demo_entity_runtime_cost"]
    mutation = measurements["mutation_write_throughput"]
    first_party_product_loop = measurements.get("first_party_agent_product_loop") or {}
    memory = measurements["memory"]
    cpu = measurements["cpu"]

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
    headless_supported = player_probe.get("headless_player_supported") is True
    true_player_load = (
        player_probe.get("probe_status") == "pass"
        and headless_supported
        and synthetic_count > 0
        and connected >= synthetic_count
    )
    if true_player_load:
        probe_status = "measured"
    elif headless_supported:
        probe_status = "measured_failure"
    else:
        probe_status = "proxy_only"
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
        if headless_supported:
            title = "Fix failing synthetic player join evidence"
            evidence = (
                f"probe_status={player_probe.get('probe_status')} "
                f"attempted={player_probe.get('attempted_synthetic_player_count')} "
                f"connected={connected}"
            )
            next_action = "Stabilize the headless client probe and keep partial joins out of accepted baselines."
        else:
            title = "Replace liveness proxy with true synthetic player joins"
            evidence = f"probe_kind={player_probe.get('probe_kind')} synthetic_player_count={synthetic_count}"
            next_action = "Wire a public-safe headless client command into benchmark capture for this hardware lane."
        gaps.append(
            gap(
                hardware_class,
                "player_join_liveness",
                title,
                evidence,
                next_action,
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

    persistence_ready = (
        metric_status(map_chunk.get("map_sqlite_bytes"))
        and (mutation.get("total_rollback_records") or 0) > 0
    )
    facts.append(
        result(
            "persistence",
            "measured" if persistence_ready else "evidence_gap",
            {
                "map_sqlite_bytes": map_chunk.get("map_sqlite_bytes"),
                "total_rollback_records": mutation.get("total_rollback_records"),
            },
            "disposable map persistence plus rollback metadata",
        )
    )
    if not persistence_ready:
        gaps.append(
            gap(
                hardware_class,
                "persistence",
                "Add persistence and rollback metadata evidence",
                (
                    f"map_sqlite_bytes={map_chunk.get('map_sqlite_bytes')} "
                    f"total_rollback_records={mutation.get('total_rollback_records')}"
                ),
                "Refresh accepted baselines with map persistence and rollback metadata.",
            )
        )

    first_party_agent_loop_ready = has_first_party_agent_product_loop_evidence(
        first_party_product_loop
    )
    compatibility_import_inventory = (
        compatibility_import_inventory or compatibility_import_inventory_missing()
    )
    compatibility_import_plugin_ready = (
        compatibility_import_inventory.get("compatibility_import_inventory_ready") is True
        and (compatibility_import_inventory.get("sources_total") or 0) > 0
        and (compatibility_import_inventory.get("planned_actions_total") or 0) > 0
    )
    if compatibility_import_plugin_ready:
        plugin_evidence = (
            "accepted benchmark lane proves first-party agent loop and public-safe "
            "import inventory discovery"
        )
    elif first_party_agent_loop_ready:
        plugin_evidence = (
            "accepted benchmark lane proves the first-party agent product loop; "
            "import inventory proof remains open"
        )
    else:
        plugin_evidence = (
            "clean runtime profile exists; first-party agent and import inventory proof remain open"
        )
    facts.append(
        result(
            "mod_plugin_ergonomics",
            "measured" if (
                first_party_agent_loop_ready and compatibility_import_plugin_ready
            ) else "partial",
            {
                "clean_profile_capability_policy": True,
                "first_party_agent_loop_ready": first_party_agent_loop_ready,
                "compatibility_import_plugin_ready": compatibility_import_plugin_ready,
                "compatibility_import_inventory": {
                    "status": compatibility_import_inventory.get("status"),
                    "sources_total": compatibility_import_inventory.get("sources_total"),
                    "inventory_items_total": compatibility_import_inventory.get(
                        "inventory_items_total"
                    ),
                    "planned_actions_total": compatibility_import_inventory.get(
                        "planned_actions_total"
                    ),
                    "source_status_counts": compatibility_import_inventory.get(
                        "source_status_counts"
                    ),
                    "by_source_class": compatibility_import_inventory.get("by_source_class"),
                },
                "first_party_agent_product_loop": {
                    "product_loop_status": first_party_product_loop.get("product_loop_status"),
                    "approval_plan_count": first_party_product_loop.get("approval_plan_count"),
                    "approved_task_count": first_party_product_loop.get("approved_task_count"),
                    "guide_command_checked": first_party_product_loop.get("guide_command_checked"),
                    "tasks_command_checked": first_party_product_loop.get("tasks_command_checked"),
                    "cancel_command_checked": first_party_product_loop.get("cancel_command_checked"),
                    "audit_review_checked": first_party_product_loop.get("audit_review_checked"),
                    "rollback_review_checked": first_party_product_loop.get("rollback_review_checked"),
                    "defender_command_checked": first_party_product_loop.get("defender_command_checked"),
                    "import_preview_checked": first_party_product_loop.get("import_preview_checked"),
                    "blocked_or_unsafe_outcomes": first_party_product_loop.get(
                        "blocked_or_unsafe_outcomes"
                    ),
                },
            },
            plugin_evidence,
        )
    )
    if not first_party_agent_loop_ready:
        gaps.append(
            gap(
                hardware_class,
                "mod_plugin_ergonomics",
                "Prove first-party agent product loop in accepted lanes",
                (
                    "first-party commands exist but accepted benchmark lanes do not yet exercise "
                    "build/repair approval, guide, tasks, audit, rollback, defender, and importer preview"
                ),
                "Add local and low-power-server benchmark captures for the first-party agent loop.",
            )
        )
    if not compatibility_import_plugin_ready:
        gaps.append(
            gap(
                hardware_class,
                "mod_plugin_ergonomics",
                "Build compatibility import inventory discovery",
                (
                    "Importer is dry-run plan-only; public-safe inventory discovery and richer "
                    "compatibility reports remain open"
                ),
                "Complete public-safe import inventory discovery and report classification work.",
            )
        )

    operator_visibility_ready = True
    facts.append(
        result(
            "operator_visibility",
            "measured" if operator_visibility_ready else "evidence_gap",
            {
                "operator_status_command": "ai_runtime_operator_status",
                "operator_task_control_command": "ai_runtime_operator_task_control",
                "receipt_gated_task_control": True,
            },
            "clean runtime exposes bounded operator status and receipt-gated task control",
        )
    )

    recovery_ready = (mutation.get("total_rollback_records") or 0) > 0
    facts.append(
        result(
            "recovery",
            "measured" if recovery_ready else "evidence_gap",
            {
                "total_rollback_records": mutation.get("total_rollback_records"),
                "receipt_gated_task_control": True,
                "world_mutation_from_task_control": False,
            },
            "rollback metadata plus no-world-mutation task-control boundary",
        )
    )
    if not recovery_ready:
        gaps.append(
            gap(
                hardware_class,
                "recovery",
                "Add rollback recovery evidence",
                f"total_rollback_records={mutation.get('total_rollback_records')}",
                "Refresh accepted mutation baselines with rollback metadata.",
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

    cpu_ready = (
        cpu.get("sample_status") == "measured"
        and (cpu.get("cpu_sample_count") or 0) >= 2
        and metric_status(cpu.get("avg_process_cpu_percent"))
        and metric_status(cpu.get("max_interval_cpu_percent"))
    )
    facts.append(
        result(
            "cpu",
            "measured" if cpu_ready else "evidence_gap",
            {
                "sample_status": cpu.get("sample_status"),
                "cpu_sample_count": cpu.get("cpu_sample_count"),
                "avg_process_cpu_percent": cpu.get("avg_process_cpu_percent"),
                "max_interval_cpu_percent": cpu.get("max_interval_cpu_percent"),
                "process_cpu_time_delta_seconds": cpu.get("process_cpu_time_delta_seconds"),
                "sample_methods": cpu.get("sample_methods"),
            },
            "clean-profile process CPU sampling",
        )
    )
    if not cpu_ready:
        gaps.append(
            gap(
                hardware_class,
                "cpu",
                "Add CPU load sampling",
                f"sample_status={cpu.get('sample_status')} cpu_sample_count={cpu.get('cpu_sample_count')}",
                "Refresh clean-profile capture with bounded process CPU sampling for this hardware lane.",
            )
        )

    join_latency = player_probe.get("join_latency_proxy_ms") or {}
    latency_ready = (
        player_probe.get("probe_status") == "pass"
        and player_probe.get("latency_proxy_supported") is True
        and (join_latency.get("sample_count") or 0) > 0
        and metric_status(join_latency.get("p95"))
    )
    if latency_ready:
        latency_status = "measured"
    elif headless_supported and player_probe.get("probe_status") != "pass":
        latency_status = "measured_failure"
    else:
        latency_status = "proxy_only"
    latency_metrics = {
        "latency_probe_kind": player_probe.get("latency_probe_kind"),
        "latency_proxy_supported": player_probe.get("latency_proxy_supported"),
        "join_latency_proxy_ms": {
            "sample_count": join_latency.get("sample_count"),
            "p50": join_latency.get("p50"),
            "p95": join_latency.get("p95"),
            "max": join_latency.get("max"),
            "avg": join_latency.get("avg"),
        },
        "server_step_p95_sample_interval_ms": workload.get("p95_sample_interval_ms"),
        "server_step_max_sample_interval_ms": workload.get("max_sample_interval_ms"),
        "player_probe_p95_sample_interval_ms": player_probe.get("p95_sample_interval_ms"),
        "network_rtt_ms": None,
    }
    facts.append(
        result(
            "latency",
            latency_status,
            latency_metrics,
            (
                "headless join-log observation latency proxy"
                if latency_ready
                else "server-step interval proxy; no join latency benchmark yet"
            ),
        )
    )
    if not latency_ready:
        if latency_status == "measured_failure":
            title = "Fix failing headless latency evidence"
            evidence = (
                f"probe_status={player_probe.get('probe_status')} "
                f"latency_proxy_supported={player_probe.get('latency_proxy_supported')}"
            )
            next_action = "Stabilize synthetic player joins before promoting latency evidence."
        else:
            title = "Add headless join-latency evidence"
            evidence = (
                f"latency_probe_kind={player_probe.get('latency_probe_kind')} "
                f"latency_proxy_supported={player_probe.get('latency_proxy_supported')}"
            )
            next_action = "Run benchmark capture with a public-safe headless client command for this hardware lane."
        gaps.append(
            gap(
                hardware_class,
                "latency",
                title,
                evidence,
                next_action,
            )
        )

    return facts, gaps


def gap_summary_by_area(gaps: list[dict]) -> dict:
    summary = {}
    for area in GAP_AREAS:
        area_gaps = [gap_item for gap_item in gaps if gap_item.get("gap_area") == area]
        summary[area] = {
            "gap_count": len(area_gaps),
            "scorecard_status": "pass" if not area_gaps else "fail",
        }
    return summary


def public_safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", value.strip().lower()).strip("_")
    return slug or "action"


def ordered_hardware_classes(values: set[str]) -> list[str]:
    default_order = {
        hardware_class: index
        for index, hardware_class in enumerate(DEFAULT_HARDWARE_CLASSES)
    }
    return sorted(values, key=lambda item: (default_order.get(item, len(default_order)), item))


def actionable_scorecard(gaps: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str, str, str], dict] = {}
    for gap_item in gaps:
        key = (
            gap_item.get("dimension_id", "unknown"),
            gap_item.get("title", "Untitled parity gap"),
            gap_item.get("next_action", ""),
            gap_item.get("gap_area", "engine_runtime"),
        )
        entry = grouped.setdefault(
            key,
            {
                "scorecard_status": gap_item.get("scorecard_status", "fail"),
                "gap_area": gap_item.get("gap_area", "engine_runtime"),
                "title": gap_item.get("title", "Untitled parity gap"),
                "hardware_classes": set(),
                "dimension_ids": set(),
                "evidence": set(),
                "gap_count": 0,
                "next_action": gap_item.get("next_action", ""),
            },
        )
        entry["gap_count"] += 1
        gap_status_priority = ACTIONABLE_STATUS_PRIORITY.get(
            gap_item.get("scorecard_status", "fail"),
            0,
        )
        entry_status_priority = ACTIONABLE_STATUS_PRIORITY.get(entry["scorecard_status"], 0)
        if gap_status_priority < entry_status_priority:
            entry["scorecard_status"] = gap_item.get("scorecard_status", "fail")
        if gap_item.get("hardware_class"):
            entry["hardware_classes"].add(gap_item["hardware_class"])
        if gap_item.get("dimension_id"):
            entry["dimension_ids"].add(gap_item["dimension_id"])
        if gap_item.get("evidence"):
            entry["evidence"].add(gap_item["evidence"])

    actions = []
    for entry in grouped.values():
        dimension_ids = sorted(entry["dimension_ids"])
        hardware_classes = ordered_hardware_classes(entry["hardware_classes"])
        title = entry["title"]
        gap_area = entry["gap_area"]
        actions.append(
            {
                "action_id": f"parity-{public_safe_slug('-'.join(dimension_ids))}-{public_safe_slug(title)}",
                "scorecard_status": entry["scorecard_status"],
                "gap_area": gap_area,
                "title": title,
                "hardware_classes": hardware_classes,
                "dimension_ids": dimension_ids,
                "gap_count": entry["gap_count"],
                "evidence": sorted(entry["evidence"]),
                "next_action": entry["next_action"],
                "suggested_issue_title": f"Parity: {title}",
                "blocks_minecraft_parity": True,
                "blocks_compatibility_import": gap_area in {"engine_runtime", "first_party_plugin"},
            }
        )

    actions.sort(
        key=lambda item: (
            ACTIONABLE_STATUS_PRIORITY.get(item["scorecard_status"], 99),
            ACTIONABLE_GAP_AREA_PRIORITY.get(item["gap_area"], 99),
            item["title"],
            item["action_id"],
        )
    )
    for rank, action in enumerate(actions, start=1):
        action["rank"] = rank
    return actions


def build_report(output_root: Path, hardware_classes: list[str]) -> dict:
    compatibility_import_inventory = load_compatibility_import_inventory(output_root)
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
        facts, gaps = dimension_results(
            lane["hardware_class"],
            lane["measurements"],
            compatibility_import_inventory,
        )
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
        "scorecard_status_criteria": SCORECARD_STATUS_CRITERIA,
        "comparison_dimensions": comparison_dimensions(),
        "benchmark_scenarios": benchmark_scenarios(),
        "measured_facts": measured_facts,
        "qualitative_minecraft_parity_gaps": qualitative_gaps,
        "actionable_scorecard": actionable_scorecard(qualitative_gaps),
        "gap_summary_by_area": gap_summary_by_area(qualitative_gaps),
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
