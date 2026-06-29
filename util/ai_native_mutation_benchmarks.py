#!/usr/bin/env python3
"""Generate AI-native mutation benchmark report fixtures."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


SCENARIOS = [
    {
        "scenario_id": "small_build_rollback",
        "category": "build",
        "description": "Queue a small synthetic build task through rollback-backed safe world operations.",
        "entry_point": {
            "command": "bin/luantiserver --run-unittests --test-module TestAIRuntime",
            "runtime_path": "builtin/game/build_agent.lua",
            "server_action": "core.build_agent.define_task -> core.queue_ai_task",
        },
        "fixture": {
            "synthetic": True,
            "requires_live_world": False,
            "requires_private_assets": False,
            "node_count": 8,
            "world_ref": "world:synthetic-benchmark",
        },
    },
    {
        "scenario_id": "repair_scan_readonly",
        "category": "repair_scan",
        "description": "Inspect bounded synthetic terrain damage without changing nodes.",
        "entry_point": {
            "command": "bin/luantiserver --run-unittests --test-module TestAIRuntime",
            "runtime_path": "builtin/game/repair_agent.lua",
            "server_action": "core.repair_agent.plan_area",
        },
        "fixture": {
            "synthetic": True,
            "requires_live_world": False,
            "requires_private_assets": False,
            "node_count": 27,
            "world_ref": "world:synthetic-benchmark",
        },
    },
    {
        "scenario_id": "repair_mutation_rollback",
        "category": "repair_mutation",
        "description": "Apply a bounded synthetic repair plan after rollback metadata is persisted.",
        "entry_point": {
            "command": "bin/luantiserver --run-unittests --test-module TestAIRuntime",
            "runtime_path": "builtin/game/repair_agent.lua",
            "server_action": "core.repair_agent.queue_apply_task",
        },
        "fixture": {
            "synthetic": True,
            "requires_live_world": False,
            "requires_private_assets": False,
            "node_count": 4,
            "world_ref": "world:synthetic-benchmark",
        },
    },
    {
        "scenario_id": "rollback_record_write",
        "category": "rollback",
        "description": "Measure rollback record creation overhead without applying a world mutation.",
        "entry_point": {
            "command": "bin/luantiserver --run-unittests --test-module TestAIRuntime",
            "runtime_path": "builtin/game/ai_runtime.lua",
            "server_action": "core.write_ai_rollback_record",
        },
        "fixture": {
            "synthetic": True,
            "requires_live_world": False,
            "requires_private_assets": False,
            "node_count": 16,
            "world_ref": "world:synthetic-benchmark",
        },
    },
    {
        "scenario_id": "compat_structure_chunked_apply",
        "category": "compat_structure",
        "description": "Apply a synthetic reviewed structure fixture through chunked compatibility import tasks.",
        "entry_point": {
            "command": "bin/luantiserver --run-unittests --test-module TestAIRuntime",
            "runtime_path": "builtin/game/ai_runtime.lua",
            "server_action": "core.ai_import_ops.queue_chunked_structure_apply_task",
        },
        "fixture": {
            "synthetic": True,
            "requires_live_world": False,
            "requires_private_assets": False,
            "node_count": 5,
            "world_ref": "world:synthetic-compat-staging",
        },
    },
]

SAMPLE_METRICS = {
    "small_build_rollback": {
        "avg_step_ms": 1.8,
        "p95_step_ms": 2.4,
        "max_lag_ms": 3.0,
        "node_writes": 8,
        "node_writes_per_step": 8,
        "mapblock_churn": 1,
        "skipped_positions": 0,
        "rollback_records": 1,
        "ai_runtime_counters": {
            "queued_tasks": 1,
            "completed_tasks": 1,
            "blocked_tasks": 0,
            "rollback_write_attempts": 1,
            "rollback_write_failures": 0,
        },
        "warnings": [],
        "errors": [],
    },
    "repair_scan_readonly": {
        "avg_step_ms": 1.1,
        "p95_step_ms": 1.5,
        "max_lag_ms": 2.0,
        "node_writes": 0,
        "node_writes_per_step": 0,
        "mapblock_churn": 0,
        "skipped_positions": 2,
        "rollback_records": 0,
        "ai_runtime_counters": {
            "queued_tasks": 1,
            "completed_tasks": 1,
            "blocked_tasks": 0,
            "rollback_write_attempts": 0,
            "rollback_write_failures": 0,
        },
        "warnings": [],
        "errors": [],
    },
    "repair_mutation_rollback": {
        "avg_step_ms": 1.6,
        "p95_step_ms": 2.2,
        "max_lag_ms": 2.9,
        "node_writes": 3,
        "node_writes_per_step": 4,
        "mapblock_churn": 1,
        "skipped_positions": 1,
        "rollback_records": 1,
        "ai_runtime_counters": {
            "queued_tasks": 1,
            "completed_tasks": 1,
            "blocked_tasks": 0,
            "rollback_write_attempts": 1,
            "rollback_write_failures": 0,
        },
        "warnings": [],
        "errors": [],
    },
    "rollback_record_write": {
        "avg_step_ms": 0.7,
        "p95_step_ms": 1.0,
        "max_lag_ms": 1.4,
        "node_writes": 0,
        "node_writes_per_step": 0,
        "mapblock_churn": 0,
        "skipped_positions": 0,
        "rollback_records": 1,
        "ai_runtime_counters": {
            "queued_tasks": 0,
            "completed_tasks": 0,
            "blocked_tasks": 0,
            "rollback_write_attempts": 1,
            "rollback_write_failures": 0,
        },
        "warnings": [],
        "errors": [],
    },
    "compat_structure_chunked_apply": {
        "avg_step_ms": 2.1,
        "p95_step_ms": 2.8,
        "max_lag_ms": 3.4,
        "node_writes": 5,
        "node_writes_per_step": 2,
        "mapblock_churn": 5,
        "skipped_positions": 0,
        "rollback_records": 3,
        "ai_runtime_counters": {
            "queued_tasks": 1,
            "completed_tasks": 1,
            "blocked_tasks": 0,
            "rollback_write_attempts": 3,
            "rollback_write_failures": 0,
        },
        "warnings": [],
        "errors": [],
    },
}

PLANNED_METRICS = {
    "avg_step_ms": None,
    "p95_step_ms": None,
    "max_lag_ms": None,
    "node_writes": None,
    "node_writes_per_step": None,
    "mapblock_churn": None,
    "skipped_positions": None,
    "rollback_records": None,
    "ai_runtime_counters": {
        "queued_tasks": None,
        "completed_tasks": None,
        "blocked_tasks": None,
        "rollback_write_attempts": None,
        "rollback_write_failures": None,
    },
    "warnings": [],
    "errors": [],
}

REGRESSION_GATES = [
    {
        "metric": "errors",
        "condition": "must be empty",
        "merge_rule": "must not merge with runtime errors",
    },
    {
        "metric": "warnings",
        "condition": "must not introduce new safety warnings against the baseline",
        "merge_rule": "must not merge until reviewed",
    },
    {
        "metric": "max_lag_ms",
        "condition": "must stay within 10 percent of the accepted baseline for the same hardware_class",
        "merge_rule": "must not merge without an explicit benchmark exception",
    },
    {
        "metric": "node_writes_per_step",
        "condition": "must stay inside the scenario write budget",
        "merge_rule": "must not merge if bounded writes are bypassed",
    },
    {
        "metric": "mapblock_churn",
        "condition": "must be measured for structure and map/chunk mutation scenarios",
        "merge_rule": "must not merge if mapblock churn is missing",
    },
    {
        "metric": "node_writes",
        "condition": "must record total writes for mutating scenarios",
        "merge_rule": "must not merge if total node writes are missing",
    },
    {
        "metric": "rollback_records",
        "condition": "mutating scenarios must write rollback metadata before node writes",
        "merge_rule": "must not merge if rollback records are missing",
    },
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def copy_json(value):
    return json.loads(json.dumps(value))


def build_report(args):
    scenarios = []
    for scenario in SCENARIOS:
        item = copy_json(scenario)
        if args.sample_synthetic:
            item["metrics"] = copy_json(SAMPLE_METRICS[item["scenario_id"]])
        else:
            item["metrics"] = copy_json(PLANNED_METRICS)
        scenarios.append(item)

    return {
        "schema_version": 1,
        "generated_at": utc_now(),
        "luanti_commit": args.luanti_commit,
        "hardware_class": args.hardware_class,
        "run_context": {
            "mode": "sample-synthetic" if args.sample_synthetic else "planned",
            "requires_private_world": False,
            "requires_private_assets": False,
            "requires_live_pi": False,
        },
        "scenarios": scenarios,
        "regression_gates": copy_json(REGRESSION_GATES),
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate an AI-native mutation benchmark report skeleton or synthetic sample."
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path where the JSON benchmark report will be written.",
    )
    parser.add_argument(
        "--hardware-class",
        choices=("local-mac", "low-power-server"),
        required=True,
        help="Hardware lane for the report.",
    )
    parser.add_argument(
        "--luanti-commit",
        required=True,
        help="Commit or label for the engine build under benchmark.",
    )
    parser.add_argument(
        "--sample-synthetic",
        action="store_true",
        help="Fill metrics with deterministic sample values instead of null planned fields.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    report = build_report(args)
    output.write_text(json.dumps(report, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
