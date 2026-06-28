#!/usr/bin/env python3
"""Audit AI-native runtime MVP coverage against the public MVP spec."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER_VERSION = "ai-native-mvp-audit:v1"
DEFAULT_SCORECARD = ROOT / "local" / "benchmarks" / "runtime-gap-scorecard.json"
DEFAULT_OUTPUT = ROOT / "local" / "benchmarks" / "ai-native-mvp-audit.json"

PRIVATE_PATTERNS = re.compile(
    r"minecraftpi|192\.168|spacebase|themepark|showcase100|disneyland100|"
    r"sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY|private_prompt|asset_payload|"
    r"/Users/|/opt/|bill@",
    re.I,
)


class MvpAuditError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise MvpAuditError(f"required input missing: {logical_path(path)}") from exc
    except json.JSONDecodeError as exc:
        raise MvpAuditError(f"invalid JSON input: {logical_path(path)}") from exc


def write_json(path: Path, payload: dict) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=False) + "\n"
    assert_public_safe(rendered)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")


def assert_public_safe(text: str) -> None:
    match = PRIVATE_PATTERNS.search(text)
    if match:
        raise MvpAuditError(f"public-safety check failed on token: {match.group(0)!r}")


def logical_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        if path.name == "runtime-gap-scorecard.json":
            return "local/benchmarks/runtime-gap-scorecard.json"
        if path.name:
            return path.name
        return "<external-path>"


def read_repo_text(source: str) -> str:
    path = ROOT / source
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def text_has_all(source: str, needles: list[str]) -> tuple[bool, list[str]]:
    text = read_repo_text(source)
    missing = [needle for needle in needles if needle not in text]
    return not missing, missing


def evidence_from_contains(source: str, label: str, needles: list[str]) -> dict:
    ok, missing = text_has_all(source, needles)
    evidence = {
        "kind": "source_text",
        "source": source,
        "check": label,
        "status": "pass" if ok else "missing",
    }
    if missing:
        evidence["missing_tokens"] = len(missing)
    return evidence


def evidence_manual(kind: str, source: str, label: str, status: str) -> dict:
    return {
        "kind": kind,
        "source": source,
        "check": label,
        "status": status,
    }


AUDIT_ITEMS = [
    {
        "id": "fork-builds-locally",
        "requirement": "The fork builds locally and has a repeatable pre-PR verification path.",
        "category": "already_proven",
        "verification_strength": "proven",
        "mvp_spec_refs": [
            "Acceptance Criteria: The fork builds locally.",
            "Testing: Build, repair, inspect, and entity-load benchmarks.",
        ],
        "evidence_specs": [
            (
                "util/ai_native_runtime_verify.py",
                "One-command verifier runs utility contracts, benchmark gate, and TestAIRuntime.",
                [
                    "utility_contract_tests",
                    "branch_benchmark_gate",
                    "ai_runtime_focused_tests",
                    "TestAIRuntime",
                ],
            ),
            (
                "doc/ai-native-runtime/README.md",
                "Runtime README exposes the pre-PR verification command.",
                ["python3 util/ai_native_runtime_verify.py --hardware-class local-mac"],
            ),
        ],
    },
    {
        "id": "agent-identity-capabilities",
        "requirement": "Agent identity and capabilities are registered through a first-party runtime path.",
        "category": "implemented_but_weakly_verified",
        "verification_strength": "weak",
        "mvp_spec_refs": [
            "Agent Identity: stable id, display name, owner, plugin, capabilities, limits, state.",
            "Acceptance Criteria: Agent identity and capabilities are registered through a first-party runtime path.",
        ],
        "evidence_specs": [
            (
                "builtin/game/ai_runtime.lua",
                "Runtime implements registration, lookup, and capability checks.",
                [
                    "function core.register_ai_agent",
                    "function core.get_ai_agent",
                    "function core.check_agent_capability",
                    "admin.override",
                ],
            ),
            (
                "builtin/game/tests/test_ai_runtime.lua",
                "Focused runtime tests exercise registration and capability denial.",
                ["core.register_ai_agent", "core.check_agent_capability", "missing_capability"],
            ),
        ],
        "note": "The API exists and is unit-tested; cross-profile/server-admin policy coverage is still thin.",
    },
    {
        "id": "queued-inspect-place-remove",
        "requirement": "A queued task can inspect, place, and remove nodes through safe operations.",
        "category": "already_proven",
        "verification_strength": "proven",
        "mvp_spec_refs": [
            "Task Queue: Long-running work must be queued, sliced, and cancellable.",
            "Safe World Operations: inspect_area, place_node, remove_node, batch_place, batch_remove.",
            "Acceptance Criteria: A queued task can inspect, place, and remove nodes through safe operations.",
        ],
        "evidence_specs": [
            (
                "builtin/game/ai_runtime.lua",
                "Runtime exposes queued tasks and safe world operation APIs.",
                [
                    "function core.queue_ai_task",
                    "function core.step_ai_tasks",
                    "function core.ai_world_ops.inspect_area",
                    "function core.ai_world_ops.place_node",
                    "function core.ai_world_ops.remove_node",
                    "function core.ai_world_ops.batch_place",
                    "function core.ai_world_ops.batch_remove",
                ],
            ),
            (
                "builtin/game/tests/test_ai_runtime.lua",
                "Runtime tests exercise inspect, place, remove, batch place, and batch remove.",
                [
                    "core.ai_world_ops.place_node",
                    "core.ai_world_ops.inspect_area",
                    "core.ai_world_ops.remove_node",
                    "core.ai_world_ops.batch_place",
                    "core.ai_world_ops.batch_remove",
                ],
            ),
        ],
    },
    {
        "id": "structured-action-results",
        "requirement": "Every operation returns structured action results.",
        "category": "already_proven",
        "verification_strength": "proven",
        "mvp_spec_refs": [
            "Action Result: ok, status, operation, agent_id, task_id, changed, examined, skipped, reason, message, samples, metrics.",
            "Acceptance Criteria: Every operation returns structured action results.",
        ],
        "evidence_specs": [
            (
                "builtin/game/ai_runtime.lua",
                "Runtime centralizes action-result construction and finalization.",
                ["make_action_result", "finish_action_result", "samples = {}", "metrics = {"],
            ),
            (
                "builtin/game/tests/test_ai_runtime.lua",
                "Focused tests assert the action-result schema.",
                ["local function assert_action_result", "result.changed", "result.examined", "result.metrics"],
            ),
        ],
    },
    {
        "id": "task-cancellation",
        "requirement": "Tasks can be cancelled.",
        "category": "already_proven",
        "verification_strength": "proven",
        "mvp_spec_refs": [
            "Task statuses: cancelled.",
            "Acceptance Criteria: Tasks can be cancelled.",
        ],
        "evidence_specs": [
            (
                "builtin/game/ai_runtime.lua",
                "Runtime implements owner/admin cancellation.",
                ["function core.cancel_ai_task", "cancel_denied", "tasks_cancelled"],
            ),
            (
                "builtin/game/tests/test_ai_runtime.lua",
                "Focused tests cancel queued and running tasks.",
                ["task:queued-cancel", "task:running-cancel", "queued_cancel.status == \"cancelled\""],
            ),
        ],
    },
    {
        "id": "protected-unsafe-skips",
        "requirement": "Protected and unsafe operations are skipped and reported.",
        "category": "already_proven",
        "verification_strength": "proven",
        "mvp_spec_refs": [
            "Safety Gates: protected areas, unbreakable nodes, liquids and hazards, player proximity, area bounds.",
            "Acceptance Criteria: Protected and unsafe operations are skipped and reported.",
        ],
        "evidence_specs": [
            (
                "builtin/game/ai_runtime.lua",
                "Safe world ops classify blocked and unsafe skips.",
                ["protected_area", "unbreakable_node", "hazard_node", "unsafe_operations"],
            ),
            (
                "builtin/game/tests/test_ai_runtime.lua",
                "Focused tests cover protected, unbreakable, hazard, and sample reporting.",
                ["protected_area", "unbreakable_node", "hazard_node", "samples"],
            ),
        ],
    },
    {
        "id": "runtime-metrics",
        "requirement": "Metrics expose queue length, task duration, and node-write counts.",
        "category": "implemented_but_weakly_verified",
        "verification_strength": "weak",
        "mvp_spec_refs": [
            "Action Result: metrics include elapsed time, server-step slice used, and write counts.",
            "Acceptance Criteria: Metrics expose queue length, task duration, and node-write counts.",
        ],
        "evidence_specs": [
            (
                "builtin/game/ai_runtime.lua",
                "Runtime exposes queue, write, audit, model, and entity counters.",
                ["function core.get_ai_runtime_metrics", "queue_length", "node_writes", "task_reported_node_writes"],
            ),
            (
                "doc/ai-native-runtime/metrics-audit-api.md",
                "Metrics docs describe operator snapshots and adapter metrics.",
                ["core.get_ai_runtime_metrics()", "queue_length", "node_writes", "elapsed_us"],
            ),
        ],
        "note": "Queue and write metrics are strong; explicit task-duration aggregation remains weaker than per-result elapsed_us.",
    },
    {
        "id": "first-party-deterministic-plugin",
        "requirement": "A first-party agent plugin can run deterministic local actions without direct ad hoc world writes.",
        "category": "already_proven",
        "verification_strength": "proven",
        "mvp_spec_refs": [
            "First Plugin: deterministic local actions before LLM fallback.",
            "Acceptance Criteria: A first-party agent plugin can run deterministic local actions without direct ad hoc world writes.",
        ],
        "evidence_specs": [
            (
                "builtin/game/ai_agent_plugin.lua",
                "Plugin queues deterministic commands through runtime APIs.",
                [
                    "function plugin.handle_command",
                    "core.queue_ai_task",
                    "core.ai_world_ops.batch_place",
                    "core.ai_world_ops.place_node",
                    "core.ai_world_ops.remove_node",
                ],
            ),
            (
                "builtin/game/tests/test_ai_runtime.lua",
                "Focused tests exercise light, build, repair, cancel, tasks, and model fallback.",
                [
                    "core.ai_agent_plugin.handle_command",
                    "place 2 lights",
                    "build marker",
                    "repair",
                    "set_model_adapter",
                ],
            ),
            (
                "doc/ai-native-runtime/first-party-agent-plugin.md",
                "Plugin docs declare no raw world writes or private showcase commands.",
                ["does not call raw", "Implemented deterministic commands", "hard-coded showcase builders"],
            ),
        ],
    },
    {
        "id": "first-party-follow-come-product-behavior",
        "requirement": "First-party follow and come behavior should become real bounded movement/pathing, not only state updates.",
        "category": "missing_first_party_plugin_behavior",
        "verification_strength": "missing",
        "mvp_spec_refs": [
            "First Plugin: status, task listing, cancellation, follow, come, build, repair, and light commands.",
            "Safe World Operations: move_agent(agent_id, target, options).",
        ],
        "evidence_specs": [
            (
                "doc/ai-native-runtime/first-party-agent-plugin.md",
                "Current limits explicitly say follow/come only update state.",
                ["Follow and come commands update state only", "movement/pathing is a later slice"],
            ),
            (
                "builtin/game/ai_agent_plugin.lua",
                "Plugin follow/come handlers currently record state and target positions.",
                ["mode = \"follow\"", "mode = \"come\"", "target_pos = default_pos(context)"],
            ),
        ],
    },
    {
        "id": "lag-pausing-budget-enforcement",
        "requirement": "Tasks should enforce server-step, node-write, wall-clock, and lag-based pause budgets.",
        "category": "already_proven",
        "verification_strength": "proven",
        "mvp_spec_refs": [
            "Task Queue: constrained by server-step budget, node-write budget, and wall-clock budget.",
            "Task Queue: pause when server lag exceeds configured thresholds.",
            "Testing: Lag-based pausing.",
        ],
        "evidence_specs": [
            (
                "builtin/game/ai_runtime.lua",
                "Runtime enforces manual pause, automatic lag pause, node-write budgets, and wall-clock budgets.",
                [
                    "function core.set_ai_task_queue_paused",
                    "function core.set_ai_task_queue_lag_monitor",
                    "max_node_writes_per_step",
                    "max_wall_time_ms",
                    "lag_threshold_exceeded",
                    "wall_clock_budget_exceeded",
                ],
            ),
            (
                "builtin/game/tests/test_ai_runtime.lua",
                "Focused runtime tests cover automatic lag pause/resume and wall-clock budget stop.",
                ["task:auto-lag-paused", "task:wall-clock-budget", "wall_clock_budget_exceeded"],
            ),
            (
                "doc/ai-native-runtime/task-queue-api.md",
                "Task queue docs describe lag monitor and wall-clock budget behavior.",
                [
                    "budget.max_wall_time_ms",
                    "core.set_ai_task_queue_lag_monitor",
                    "lag_threshold_exceeded",
                ],
            ),
        ],
    },
    {
        "id": "player-teleport-and-combat-capabilities",
        "requirement": "player.teleport.self, player.teleport.other, and combat.defend need safe runtime APIs and tests.",
        "category": "missing_runtime_behavior",
        "verification_strength": "missing",
        "mvp_spec_refs": [
            "Capabilities: player.teleport.self, player.teleport.other, combat.defend.",
            "Safe World Operations: move_agent(agent_id, target, options).",
        ],
        "evidence_specs": [
            (
                "doc/ai-native-runtime/mvp-spec.md",
                "Spec includes teleport and defensive combat capabilities.",
                ["player.teleport.self", "player.teleport.other", "combat.defend"],
            ),
            (
                "builtin/game/ai_runtime.lua",
                "No dedicated player teleport or combat-defend runtime API is present yet.",
                ["core.ai_entity_ops.move", "entity.control"],
            ),
        ],
    },
    {
        "id": "model-and-import-capability-boundaries",
        "requirement": "http.llm and import.assets should have first-class runtime capability names and execution gates.",
        "category": "missing_runtime_behavior",
        "verification_strength": "missing",
        "mvp_spec_refs": [
            "Capabilities: http.llm and import.assets.",
            "Non-Goals: Do not implement Minecraft compatibility/import in this milestone.",
        ],
        "evidence_specs": [
            (
                "builtin/game/ai_runtime.lua",
                "Model adapter metrics and audits exist, but no http.llm task gate is first-class.",
                ["function core.record_ai_model_adapter_result", "model_adapter_requests", "model.adapter"],
            ),
            (
                "util/ai_native_compat_dry_run.py",
                "Compatibility planning records import.assets as inert dry-run capability evidence.",
                ["import.assets", "dry_run", "planned_actions"],
            ),
        ],
    },
    {
        "id": "compatibility-import-deferred",
        "requirement": "Minecraft compatibility/import stays deferred until runtime safety is stronger.",
        "category": "compatibility_import_deferral",
        "verification_strength": "deferred",
        "mvp_spec_refs": [
            "Non-Goals: Do not implement Minecraft compatibility/import in this milestone.",
            "Mission: Compatibility and import tooling comes after the runtime can safely inspect, modify, repair, and explain world changes.",
        ],
        "evidence_specs": [
            (
                "doc/ai-native-runtime/mvp-spec.md",
                "MVP spec explicitly defers compatibility/import.",
                ["Do not implement Minecraft compatibility/import in this milestone"],
            ),
            (
                "doc/ai-native-runtime/README.md",
                "Runtime README states compatibility/import comes after AI-native runtime safety.",
                ["Compatibility and import tooling comes after the runtime"],
            ),
        ],
    },
]


FOLLOW_ON_ISSUES = [
    {
        "id": "mvp-first-party-agent-plugin-runtime",
        "priority": 1,
        "title": "Promote first-party follow and come commands from state updates to bounded runtime behavior",
        "category": "missing_first_party_plugin_behavior",
        "source_acceptance_ids": ["first-party-follow-come-product-behavior"],
        "why_now": "Player-visible agent behavior should prove the runtime can safely move or guide an agent, not only mutate nodes.",
    },
    {
        "id": "mvp-player-teleport-combat-runtime",
        "priority": 2,
        "title": "Add safe player teleport and defensive-combat capability runtime slices",
        "category": "missing_runtime_behavior",
        "source_acceptance_ids": ["player-teleport-and-combat-capabilities"],
        "why_now": "These capabilities are in the MVP set and need explicit admin/default-deny semantics before broader gameplay agents.",
    },
    {
        "id": "mvp-model-import-capability-runtime",
        "priority": 3,
        "title": "Align http.llm and import.assets capability gates with runtime task execution",
        "category": "missing_runtime_behavior",
        "source_acceptance_ids": ["model-and-import-capability-boundaries"],
        "why_now": "The model/import boundaries exist as docs and dry-run planning, but the runtime needs first-class gates before compatibility/import expands.",
    },
    {
        "id": "mvp-runtime-task-duration-metrics",
        "priority": 4,
        "title": "Expose task-duration metrics in the operator runtime snapshot",
        "category": "implemented_but_weakly_verified",
        "source_acceptance_ids": ["runtime-metrics"],
        "why_now": "Per-result elapsed_us exists, but the MVP calls for task duration at the metrics layer.",
    },
    {
        "id": "mvp-agent-policy-profile",
        "priority": 5,
        "title": "Add clean-profile policy tests for first-party agent capability grants",
        "category": "implemented_but_weakly_verified",
        "source_acceptance_ids": ["agent-identity-capabilities"],
        "why_now": "Registration and capability checks are unit-tested; server-profile policy needs stronger verification.",
    },
]


def validate_scorecard(scorecard: dict) -> dict:
    if scorecard.get("runner_version") != "ai-native-runtime-gap-scorecard:v1":
        raise MvpAuditError("expected ai-native-runtime-gap-scorecard:v1 input")
    if scorecard.get("overall_status") != "gap-scorecard-ready":
        raise MvpAuditError("MVP audit requires a clean runtime gap scorecard")
    ranked_gaps = scorecard.get("ranked_gaps") or []
    if ranked_gaps:
        raise MvpAuditError("MVP audit requires a clean runtime gap scorecard before requirement audit")

    lanes = scorecard.get("lanes") or []
    lane_classes = sorted(
        lane.get("hardware_class")
        for lane in lanes
        if isinstance(lane, dict) and lane.get("hardware_class")
    )
    return {
        "status": "pass",
        "logical_path": "local/benchmarks/runtime-gap-scorecard.json",
        "runner_version": scorecard.get("runner_version"),
        "overall_status": scorecard.get("overall_status"),
        "ranked_gap_count": len(ranked_gaps),
        "hardware_classes": lane_classes or sorted(scorecard.get("hardware_classes") or []),
    }


def build_acceptance_item(spec: dict) -> dict:
    evidence = [
        evidence_from_contains(source, label, needles)
        for source, label, needles in spec["evidence_specs"]
    ]
    status = "pass"
    if any(item["status"] == "missing" for item in evidence):
        status = "evidence-gap"
    result = {
        "id": spec["id"],
        "requirement": spec["requirement"],
        "category": spec["category"],
        "verification_strength": spec["verification_strength"],
        "status": status,
        "mvp_spec_refs": list(spec["mvp_spec_refs"]),
        "evidence": evidence,
    }
    if spec.get("note"):
        result["note"] = spec["note"]
    return result


def summarize_categories(items: list[dict]) -> dict:
    counts = {}
    for item in items:
        counts[item["category"]] = counts.get(item["category"], 0) + 1
    return counts


def build_report(scorecard_path: Path) -> dict:
    scorecard = load_json(scorecard_path)
    scorecard_prerequisite = validate_scorecard(scorecard)
    acceptance_audit = [build_acceptance_item(item) for item in AUDIT_ITEMS]
    category_counts = summarize_categories(acceptance_audit)
    has_unproven = any(
        item["category"]
        in {
            "implemented_but_weakly_verified",
            "missing_runtime_behavior",
            "missing_first_party_plugin_behavior",
        }
        for item in acceptance_audit
    )

    return {
        "runner_version": RUNNER_VERSION,
        "generated_at": utc_now(),
        "overall_status": "mvp-gaps-open" if has_unproven else "mvp-ready",
        "scope": {
            "mvp_spec": "doc/ai-native-runtime/mvp-spec.md",
            "issue": "Issue #94",
            "boundary": "public-safe engine/runtime audit; private worlds, family content, live hostnames, provider prompts, copied assets, and proprietary Minecraft content excluded",
        },
        "scorecard_prerequisite": scorecard_prerequisite,
        "category_counts": category_counts,
        "acceptance_audit": acceptance_audit,
        "follow_on_issues": FOLLOW_ON_ISSUES,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scorecard",
        default=str(DEFAULT_SCORECARD),
        help="Path to runtime-gap-scorecard.json. Default: local/benchmarks/runtime-gap-scorecard.json.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Path for MVP audit JSON. Default: local/benchmarks/ai-native-mvp-audit.json.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        report = build_report(Path(args.scorecard))
        output = Path(args.output)
        write_json(output, report)
    except MvpAuditError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"Wrote {logical_path(output)}")
    print(
        "MVP audit status: "
        f"{report['overall_status']} "
        f"({len(report['acceptance_audit'])} requirements, "
        f"{len(report['follow_on_issues'])} follow-on issues)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
