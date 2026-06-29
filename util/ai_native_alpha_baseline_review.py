#!/usr/bin/env python3
"""Review accepted alpha baselines and the Minecraft-parity report."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ai_native_minecraft_parity_harness
import ai_native_runtime_gap_scorecard


ROOT = Path(__file__).resolve().parents[1]
REVIEW_KIND = "ai_native_alpha_baseline_review"
DEFAULT_HARDWARE_CLASSES = ("local-mac", "low-power-server")
REQUIRED_GAP_AREAS = ("engine_runtime", "first_party_plugin", "game_content", "operator_experience")


class ReviewError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def logical_path(output_root: Path, path: Path) -> str:
    try:
        relative = path.relative_to(output_root)
    except ValueError:
        return path.name
    return str(Path("local/benchmarks") / relative)


def numeric(value) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def check(name: str, ok: bool, failures: list[str], detail: str | None = None) -> dict:
    if not ok:
        failures.append(f"{name}: {detail or 'failed'}")
    result = {"name": name, "status": "pass" if ok else "fail"}
    if detail:
        result["detail"] = detail
    return result


def review_lane(output_root: Path, hardware_class: str) -> dict:
    failures: list[str] = []
    accepted = ai_native_runtime_gap_scorecard.load_accepted_lane(output_root, hardware_class)
    lane = ai_native_runtime_gap_scorecard.build_lane_evidence(hardware_class, accepted)
    measurements = lane["measurements"]
    manifest = accepted["manifest"]
    clean_profile = accepted["clean_profile"]
    mutation = measurements["mutation_write_throughput"]
    demo = measurements["demo_entity_runtime_cost"]
    product_loop = measurements["first_party_agent_product_loop"]
    scale_gate = measurements["ai_runtime_scale_gate"]
    cpu = measurements["cpu"]
    workload = measurements["server_step_workload"]
    player_probe = measurements["player_load_tick_probe"]
    map_chunk = measurements["map_chunk_workload"]

    checks = [
        check(
            "accepted_baseline_manifest",
            (manifest.get("run_context") or {}).get("mode") == "accepted-local-baseline"
            and manifest.get("hardware_class") == hardware_class,
            failures,
            manifest.get("source_label"),
        ),
        check(
            "clean_profile",
            clean_profile.get("overall_status") == "pass"
            and (clean_profile.get("game_profile") or {}).get("gameid") == "ai_runtime"
            and not (clean_profile.get("failure_notes") or []),
            failures,
            clean_profile.get("overall_status"),
        ),
        check(
            "mutation_report",
            numeric(mutation.get("total_node_writes")) > 0
            and numeric(mutation.get("total_rollback_records")) > 0
            and numeric(mutation.get("warnings")) == 0
            and numeric(mutation.get("errors")) == 0,
            failures,
            (
                f"writes={mutation.get('total_node_writes')} "
                f"rollback_records={mutation.get('total_rollback_records')}"
            ),
        ),
        check(
            "demo_entity_scale",
            numeric(demo.get("max_entity_count")) >= 16
            and numeric(demo.get("max_active_peak")) >= 16
            and numeric(demo.get("max_remaining_entities")) == 0,
            failures,
            (
                f"max_entity_count={demo.get('max_entity_count')} "
                f"remaining={demo.get('max_remaining_entities')}"
            ),
        ),
        check(
            "first_party_agent_product_loop",
            ai_native_minecraft_parity_harness.has_first_party_agent_product_loop_evidence(
                product_loop
            ),
            failures,
            product_loop.get("product_loop_status"),
        ),
        check(
            "cpu",
            cpu.get("sample_status") == "measured"
            and numeric(cpu.get("cpu_sample_count")) >= 2
            and cpu.get("avg_process_cpu_percent") is not None
            and cpu.get("max_interval_cpu_percent") is not None,
            failures,
            f"samples={cpu.get('cpu_sample_count')}",
        ),
        check(
            "server_step_workload",
            workload.get("workload_status") == "pass"
            and numeric(workload.get("completed_sample_count")) > 0
            and numeric(workload.get("failed_sample_count")) == 0,
            failures,
            (
                f"completed={workload.get('completed_sample_count')} "
                f"failed={workload.get('failed_sample_count')}"
            ),
        ),
        check(
            "player_load_tick_probe",
            player_probe.get("probe_status") == "pass"
            and player_probe.get("probe_kind") == "headless_client_load"
            and player_probe.get("headless_player_supported") is True
            and numeric(player_probe.get("attempted_synthetic_player_count")) >= 2
            and numeric(player_probe.get("connected_synthetic_player_count"))
            >= numeric(player_probe.get("attempted_synthetic_player_count")),
            failures,
            player_probe.get("probe_kind"),
        ),
        check(
            "ai_runtime_scale_gate",
            scale_gate.get("scale_gate_status") == "pass"
            and scale_gate.get("synthetic_disposable_only") is True
            and numeric(scale_gate.get("required_synthetic_player_count")) >= 2
            and numeric(scale_gate.get("required_concurrent_task_count")) >= 2,
            failures,
            scale_gate.get("scale_gate_status"),
        ),
        check(
            "join_latency_proxy",
            player_probe.get("latency_proxy_supported") is True
            and player_probe.get("latency_probe_kind") == "headless_join_log_observation"
            and numeric((player_probe.get("join_latency_proxy_ms") or {}).get("sample_count")) > 0,
            failures,
            player_probe.get("latency_probe_kind"),
        ),
        check(
            "map_chunk_workload",
            map_chunk.get("workload_status") == "pass"
            and numeric(map_chunk.get("mapblock_rows_created")) > 0,
            failures,
            f"rows_created={map_chunk.get('mapblock_rows_created')}",
        ),
    ]

    return {
        "hardware_class": hardware_class,
        "status": "pass" if not failures else "fail",
        "accepted_baseline": lane["accepted_baseline"],
        "checks": checks,
        "failure_reasons": failures,
    }


def latest_passing_low_power_evidence(output_root: Path) -> Path | None:
    candidates = []
    for path in (output_root / "low-power-server").glob("*/*/pi-low-power-evidence.json"):
        try:
            payload = load_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("overall_status") == "pass":
            candidates.append((payload.get("generated_at", ""), path, payload))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], str(item[1])))
    return candidates[-1][1]


def review_low_power_pi_evidence(output_root: Path) -> dict:
    path = latest_passing_low_power_evidence(output_root)
    if path is None:
        return {
            "status": "fail",
            "failure_reasons": ["no passing pi-low-power-evidence.json found"],
        }
    payload = load_json(path)
    failures: list[str] = []
    runtime = payload.get("runtime_verification_evidence") or {}
    service = payload.get("service_boundary") or {}
    family = service.get("family_service") or {}
    fork = service.get("fork_test_service") or {}
    backup = payload.get("backup_evidence") or {}
    safety = payload.get("safety") or {}

    checks = [
        check("overall_status", payload.get("overall_status") == "pass", failures),
        check(
            "backup_first",
            backup.get("backup_first_confirmed") is True and backup.get("sha256_recorded") is True,
            failures,
        ),
        check(
            "family_service_boundary",
            family.get("active") is True
            and family.get("udp_listening") is True
            and family.get("port") == 30000,
            failures,
        ),
        check(
            "fork_test_service_boundary",
            fork.get("active") is True
            and fork.get("udp_listening") is True
            and fork.get("port") == 30001,
            failures,
        ),
        check(
            "headless_player_evidence",
            runtime.get("player_load_probe_status") == "pass"
            and runtime.get("player_load_probe_kind") == "headless_client_load"
            and runtime.get("headless_player_supported") is True
            and numeric(runtime.get("attempted_synthetic_player_count")) >= 2
            and numeric(runtime.get("connected_synthetic_player_count"))
            >= numeric(runtime.get("attempted_synthetic_player_count"))
            and runtime.get("latency_probe_kind") == "headless_join_log_observation"
            and numeric(runtime.get("join_latency_proxy_sample_count")) > 0,
            failures,
            runtime.get("player_load_probe_kind"),
        ),
        check(
            "public_safe_manifest",
            safety.get("public_safe_output") is True
            and safety.get("private_target_redacted") is True
            and safety.get("remote_paths_redacted") is True
            and safety.get("no_family_content") is True
            and safety.get("no_copied_assets") is True
            and safety.get("no_provider_prompts") is True,
            failures,
        ),
    ]
    return {
        "status": "pass" if not failures else "fail",
        "logical_path": logical_path(output_root, path),
        "generated_at": payload.get("generated_at"),
        "luanti_commit": payload.get("luanti_commit"),
        "checks": checks,
        "failure_reasons": failures,
    }


def review_parity_report(output_root: Path, hardware_classes: list[str]) -> dict:
    path = output_root / "minecraft-parity-comparison-report.json"
    if not path.is_file():
        return {
            "status": "fail",
            "failure_reasons": ["minecraft-parity-comparison-report.json missing"],
        }
    report = load_json(path)
    failures: list[str] = []
    serialized = json.dumps(report, sort_keys=True)
    if ai_native_minecraft_parity_harness.PRIVATE_PATTERNS.search(serialized):
        failures.append("privacy scan failed for minecraft parity report")
    actions = report.get("actionable_scorecard")
    gap_summary = report.get("gap_summary_by_area") or {}
    no_actions_expected = all(
        (gap_summary.get(area) or {}).get("scorecard_status") == "pass"
        for area in REQUIRED_GAP_AREAS
    )
    ranks = [item.get("rank") for item in actions or []]
    checks = [
        check(
            "overall_status",
            report.get("overall_status") == "minecraft-parity-report-ready",
            failures,
        ),
        check(
            "hardware_classes",
            report.get("hardware_classes") == hardware_classes,
            failures,
            ",".join(report.get("hardware_classes") or []),
        ),
        check(
            "public_safe_source_policy",
            (report.get("source_policy") or {}).get("uses_proprietary_minecraft_code_or_assets")
            is False
            and (report.get("source_policy") or {}).get("uses_copied_server_jars_or_game_data")
            is False
            and (report.get("run_context") or {}).get("requires_private_world") is False
            and (report.get("run_context") or {}).get("requires_private_assets") is False
            and (report.get("run_context") or {}).get("requires_live_pi") is False,
            failures,
        ),
        check(
            "ranked_next_actions",
            isinstance(actions, list)
            and (ranks == list(range(1, len(ranks) + 1)))
            and (len(actions) > 0 or no_actions_expected),
            failures,
            f"count={len(actions or [])}",
        ),
        check(
            "gap_summary_by_area",
            all(area in gap_summary for area in REQUIRED_GAP_AREAS),
            failures,
        ),
    ]
    return {
        "status": "pass" if not failures else "fail",
        "logical_path": "local/benchmarks/minecraft-parity-comparison-report.json",
        "generated_at": report.get("generated_at"),
        "actionable_scorecard_count": len(actions or []),
        "gap_summary_by_area": gap_summary,
        "checks": checks,
        "failure_reasons": failures,
    }


def build_review(output_root: Path, hardware_classes: list[str]) -> dict:
    lane_reviews = []
    failures = []
    for hardware_class in hardware_classes:
        try:
            lane_review = review_lane(output_root, hardware_class)
        except (ai_native_runtime_gap_scorecard.ScorecardError, OSError, json.JSONDecodeError) as exc:
            lane_review = {
                "hardware_class": hardware_class,
                "status": "fail",
                "failure_reasons": [str(exc)],
            }
        lane_reviews.append(lane_review)
        failures.extend(f"{hardware_class}: {reason}" for reason in lane_review["failure_reasons"])

    low_power_evidence = review_low_power_pi_evidence(output_root)
    failures.extend(
        f"low_power_pi_evidence: {reason}"
        for reason in low_power_evidence.get("failure_reasons", [])
    )

    parity_report = review_parity_report(output_root, hardware_classes)
    failures.extend(
        f"minecraft_parity: {reason}" for reason in parity_report.get("failure_reasons", [])
    )

    payload = {
        "schema_version": 1,
        "review_kind": REVIEW_KIND,
        "generated_at": utc_now(),
        "overall_status": "pass" if not failures else "fail",
        "hardware_classes": hardware_classes,
        "run_context": {
            "mode": "accepted-alpha-baseline-review",
            "requires_private_world": False,
            "requires_private_assets": False,
            "requires_live_pi": False,
            "requires_model_network": False,
        },
        "lane_reviews": lane_reviews,
        "low_power_pi_evidence": low_power_evidence,
        "minecraft_parity": parity_report,
        "safety": {
            "public_safe_output": True,
            "accepted_baselines_are_local_only": True,
            "no_private_worlds": True,
            "no_copied_assets": True,
            "no_provider_prompts": True,
            "family_server_preserved_as_proving_ground": True,
        },
        "failure_reasons": failures,
    }
    serialized = json.dumps(payload, sort_keys=True)
    if ai_native_minecraft_parity_harness.PRIVATE_PATTERNS.search(serialized):
        raise ReviewError("privacy scan failed for alpha baseline review")
    return payload


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Review accepted alpha benchmark baselines and Minecraft-parity evidence."
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
        help="Hardware class to include. Defaults to local-mac and low-power-server.",
    )
    parser.add_argument(
        "--output",
        help="Review artifact path. Defaults to <output-root>/alpha-baseline-review.json.",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    output_root = Path(args.output_root)
    hardware_classes = args.hardware_class or list(DEFAULT_HARDWARE_CLASSES)
    output = Path(args.output) if args.output else output_root / "alpha-baseline-review.json"
    try:
        review = build_review(output_root, hardware_classes)
        write_json(output, review)
    except (ReviewError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(output)
    return 0 if review["overall_status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
