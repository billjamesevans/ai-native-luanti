#!/usr/bin/env python3
"""Run a public-safe compatibility import pilot in a disposable ai_runtime world."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ai_native_compat_dry_run as compat


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "util" / "tests" / "fixtures" / "compat" / "public_structure" / "open_platform.ai-structure.json"
PILOT_ARTIFACT_NAME = "ai-runtime-compat-import-staging-pilot-result.json"
PILOT_STATUS_NAME = "ai-runtime-compat-import-staging-pilot-status.json"
PILOT_MOD_NAME = "ai_compat_import_staging_pilot"
DEFAULT_MAX_BYTES = 30000

PRIVATE_PATTERNS = (
    re.compile(r"/Users/[^\s\"']+"),
    re.compile(r"\bminecraftpi(?:\.home)?\b", re.I),
    re.compile(r"\b192\.168(?:\.\d{1,3}){2}\b"),
    re.compile(r"\bspacebase|themepark|showcase100|disneyland100\b", re.I),
    re.compile(r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"\bOPENAI_API_KEY\b"),
    re.compile(r"\bprivate_prompt\b"),
    re.compile(r"\basset_payload\b"),
    re.compile(r"\braw_asset_payload\b"),
    re.compile(r"\bpayload_bytes\b"),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def lua_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def reserve_udp_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


def resolve_path(root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return root / path


def import_action_index(report: dict) -> int:
    for index, action in enumerate(report.get("planned_actions") or []):
        if action.get("action") == "import_structure":
            return index
    raise ValueError("public-safe structure report has no import_structure action")


def build_apply_request(report: dict) -> dict:
    index = import_action_index(report)
    action = report["planned_actions"][index]
    inventory_hash = report["source"]["content_hashes"][0]["value"]
    return {
        "request_version": 1,
        "mode": "apply_plan",
        "report_id": "public-safe-structure-staging-pilot",
        "report_version": report["report_version"],
        "source_reference": {
            "reference_type": "mounted_fixture",
            "redacted_id": report["source"]["source_id"],
            "inventory_hash": inventory_hash,
        },
        "approved_actions": [{
            "action_index": index,
            "action": action["action"],
            "status": action["status"],
        }],
        "target_world": {
            "world_id": "disposable-staging-world",
            "staging": True,
            "disposable": True,
        },
        "operator": "server",
        "agent_id": "compat_import:server",
        "budget": {
            "max_media_files": 10,
            "max_entity_definitions": 5,
            "max_node_writes_total": 5,
            "max_node_writes_per_step": 2,
            "max_mapblock_churn_total": 3,
            "max_manual_review_items": 3,
            "max_wall_time_ms": 5000,
        },
        "rollback_policy": {
            "policy": "chunked",
            "metadata_required": True,
        },
    }


def build_pilot_context(fixture: Path, generated_at: str) -> dict:
    if not fixture.is_file():
        raise FileNotFoundError(fixture)
    with tempfile.TemporaryDirectory() as tmpdir:
        discovery_root = Path(tmpdir) / "sources"
        discovery_root.mkdir(parents=True)
        shutil.copyfile(fixture, discovery_root / fixture.name)
        discovery = compat.build_import_inventory_discovery_report(discovery_root)
    discovery_errors = compat.validate_import_inventory_discovery_report(discovery)
    if discovery_errors:
        raise ValueError(discovery_errors[0])

    report = compat.build_report(fixture)
    report_errors = compat.validate_report(report)
    if report_errors:
        raise ValueError(report_errors[0])
    request = build_apply_request(report)
    apply_plan = compat.build_apply_plan(report, request)
    smoke = compat.build_adapter_apply_smoke(report, request)
    review = compat.review_adapter_apply_smoke(smoke)
    package = compat.build_structure_import_promotion_package(report, request, smoke, review)

    apply_task = smoke["apply_tasks"][0]
    rollback_task = smoke["rollback_tasks"][0]
    expected = smoke["mutation_cost_expected"]
    return {
        "schema_version": 1,
        "context_kind": "ai_native_compat_import_staging_pilot_context",
        "generated_at": generated_at,
        "fixture": {
            "format_kind": "ai_native_public_structure",
            "source_id": report["source"]["source_id"],
            "public_safe": True,
        },
        "inventory": {
            "status": discovery["status"],
            "ready": discovery["readiness"]["compatibility_import_inventory_ready"],
            "sources_total": discovery["summary"]["sources_total"],
            "required_capabilities": discovery["summary"]["required_capabilities"],
        },
        "dry_run": {
            "report_id": request["report_id"],
            "report_version": report["report_version"],
            "source_id": report["source"]["source_id"],
            "source_class": report["source"]["source_class"],
            "license_status": report["source"]["license_status"],
            "planned_actions_count": len(report["planned_actions"]),
            "import_action_index": apply_task["action_index"],
            "estimated_world_mutations": report["summary"]["estimated_world_mutations"],
            "apply_plan_status": apply_plan["status"],
        },
        "operator_review": {
            "smoke_status": smoke["status"],
            "review_status": review["status"],
            "machine_promotable": review["machine_gate"]["promotable"],
            "promotion_status": package["status"],
        },
        "apply_task": apply_task,
        "rollback_task": rollback_task,
        "expected": {
            "node_writes": expected["node_writes"],
            "mapblock_churn": expected["mapblock_churn"],
            "placement_count": apply_task["placement_count"],
            "chunk_size": apply_task["chunk_size"],
            "chunk_count": apply_task["chunk_count"],
            "manual_review_items": expected["manual_review_items"],
        },
    }


def write_probe_world(world_dir: Path, context: dict, generated_at: str, max_bytes: int) -> None:
    if world_dir.exists():
        shutil.rmtree(world_dir)
    mod_dir = world_dir / "worldmods" / PILOT_MOD_NAME
    mod_dir.mkdir(parents=True, exist_ok=True)
    (world_dir / "world.mt").write_text(
        "\n".join([
            "gameid = ai_runtime",
            "backend = sqlite3",
            "player_backend = sqlite3",
            "auth_backend = sqlite3",
            "",
        ]),
        encoding="utf-8",
    )
    (mod_dir / "mod.conf").write_text(f"name = {PILOT_MOD_NAME}\n", encoding="utf-8")
    context_json = json.dumps(context, separators=(",", ":"), sort_keys=True)
    (mod_dir / "init.lua").write_text(
        "\n".join([
            "local output_path = core.get_worldpath() .. " + lua_string("/" + PILOT_ARTIFACT_NAME),
            "local status_path = core.get_worldpath() .. " + lua_string("/" + PILOT_STATUS_NAME),
            "local generated_at = " + lua_string(generated_at),
            f"local max_bytes = {int(max_bytes)}",
            "local context = core.parse_json(" + lua_string(context_json) + ")",
            "if type(context) ~= \"table\" then error(\"pilot context failed to parse\") end",
            "local test_node = \"ai_runtime_test:stone\"",
            "local offset = { x = 0, y = 12, z = 120 }",
            "local rollback_storage = {}",
            "local structure_writes = 0",
            "",
            "core.register_node(\":\" .. test_node, {",
            "  description = \"AI Runtime Compat Pilot Stone\",",
            "  tiles = {\"blank.png\"},",
            "  groups = {cracky = 3},",
            "})",
            "",
            "core.register_ai_agent({",
            "  agent_id = \"compat_import:server\",",
            "  display_name = \"Compat Import Server\",",
            "  owner = \"server\",",
            "  plugin = \"compat_import\",",
            "  capabilities = {",
            "    [\"import.assets\"] = true,",
            "    [\"world.place\"] = true,",
            "    [\"world.batch\"] = true,",
            "  },",
            "})",
            "",
            "core.register_ai_agent({",
            "  agent_id = \"compat_rollback:runtime\",",
            "  display_name = \"Compat Rollback Runtime\",",
            "  owner = \"server\",",
            "  plugin = \"compat_import\",",
            "  capabilities = {",
            "    [\"rollback.execute\"] = true,",
            "    [\"admin.override\"] = true,",
            "    [\"world.place\"] = true,",
            "    [\"world.batch\"] = true,",
            "  },",
            "})",
            "",
            "local function write_status(status, reason)",
            "  core.safe_file_write(status_path, core.write_json({",
            "    status = status,",
            "    reason = reason,",
            "    execution_path = \"disposable_live_ai_runtime_compat_import_staging_pilot\",",
            "  }))",
            "end",
            "",
            "local function shifted_pos(pos, x_extra)",
            "  return {",
            "    x = pos.x + offset.x + (x_extra or 0),",
            "    y = pos.y + offset.y,",
            "    z = pos.z + offset.z,",
            "  }",
            "end",
            "",
            "local function shifted_placements(placements, x_extra)",
            "  local shifted = {}",
            "  for index, placement in ipairs(placements or {}) do",
            "    shifted[index] = {",
            "      pos = shifted_pos(placement.pos, x_extra),",
            "      node_name = placement.node_name,",
            "      param1 = placement.param1 or 0,",
            "      param2 = placement.param2 or 0,",
            "    }",
            "  end",
            "  return shifted",
            "end",
            "",
            "local function get_probe_node(pos)",
            "  return (core.get_node_or_nil and core.get_node_or_nil(pos)) or core.get_node(pos)",
            "end",
            "",
            "local function set_probe_node(pos, node)",
            "  structure_writes = structure_writes + 1",
            "  return core.set_node(pos, node)",
            "end",
            "",
            "local function persist_probe_record(record)",
            "  local storage_ref = \"rollback://compat-staging-pilot/\" .. record.record_id",
            "  rollback_storage[storage_ref] = record",
            "  return { ok = true, storage_ref = storage_ref }",
            "end",
            "",
            "local function rollback_refs_for_operation(operation_label)",
            "  local refs = {}",
            "  for storage_ref, record in pairs(rollback_storage) do",
            "    if operation_label == nil or record.operation_label == operation_label then",
            "      refs[#refs + 1] = storage_ref",
            "    end",
            "  end",
            "  table.sort(refs)",
            "  return refs",
            "end",
            "",
            "local function inspect_probe_record(storage_ref)",
            "  return rollback_storage[storage_ref]",
            "end",
            "",
            "local function configure_probe_rollback_storage()",
            "  core.ai_rollback_storage.configure({",
            "    enabled = true,",
            "    inspect_record = inspect_probe_record,",
            "    persist_record = persist_probe_record,",
            "  })",
            "end",
            "",
            "configure_probe_rollback_storage()",
            "",
            "local function reset_nodes(placements)",
            "  if core.load_area then",
            "    core.load_area({ x = -2, y = 10, z = 118 }, { x = 420, y = 14, z = 122 })",
            "  end",
            "  for _, placement in ipairs(placements) do",
            "    core.set_node(placement.pos, { name = \"air\" })",
            "  end",
            "end",
            "",
            "local function task_status(task_id)",
            "  local task = core.get_ai_task(task_id)",
            "  return task and task.status or \"missing\"",
            "end",
            "",
            "local function is_final(status)",
            "  return status == \"completed\" or status == \"blocked\"",
            "    or status == \"unsafe\" or status == \"failed\" or status == \"cancelled\"",
            "end",
            "",
            "local function step_until_final(task_id, max_steps)",
            "  local steps = 0",
            "  while steps < max_steps and not is_final(task_status(task_id)) do",
            "    core.step_ai_tasks()",
            "    steps = steps + 1",
            "  end",
            "  return task_status(task_id), steps",
            "end",
            "",
            "local function count_verified_nodes(placements, expected_name)",
            "  local count = 0",
            "  for _, placement in ipairs(placements) do",
            "    local node = get_probe_node(placement.pos)",
            "    if node and node.name == expected_name then",
            "      count = count + 1",
            "    end",
            "  end",
            "  return count",
            "end",
            "",
            "local function check_param_round_trip(placement)",
            "  local node = get_probe_node(placement.pos)",
            "  return node and node.name == placement.node_name",
            "    and node.param1 == (placement.param1 or 0)",
            "    and node.param2 == (placement.param2 or 0)",
            "end",
            "",
            "local function base_apply_options(placements, x_extra)",
            "  local task = context.apply_task",
            "  return {",
            "    agent_id = task.agent_id,",
            "    owner = task.owner,",
            "    task_id = \"compat-staging-pilot:gate:\" .. tostring(x_extra or 0),",
            "    world_id = task.world_id,",
            "    target_world = task.target_world,",
            "    staging = true,",
            "    explicit_approval = true,",
            "    allow_mutation = true,",
            "    rollback_policy = \"chunked\",",
            "    placements = placements,",
            "    get_node = get_probe_node,",
            "    set_node = set_probe_node,",
            "    max_node_writes_per_step = #placements,",
            "    max_mapblock_churn_total = context.expected.mapblock_churn,",
            "    source_reference = task.source_reference,",
            "    persist_record = persist_probe_record,",
            "  }",
            "end",
            "",
            "local function run_gate(name, x_extra, mutate_options, expected_reason)",
            "  local placements = shifted_placements(context.apply_task.placements, x_extra)",
            "  reset_nodes(placements)",
            "  local before = structure_writes",
            "  local options = base_apply_options(placements, x_extra)",
            "  for key, value in pairs(mutate_options or {}) do",
            "    if value == \"__nil\" then",
            "      options[key] = nil",
            "    else",
            "      options[key] = value",
            "    end",
            "  end",
            "  local result = core.ai_import_ops.apply_structure(placements, options)",
            "  return {",
            "    name = name,",
            "    status = result.status,",
            "    reason = result.reason,",
            "    changed = result.changed or 0,",
            "    expected_reason = expected_reason,",
            "    writes_attempted = structure_writes - before,",
            "    passed = result.status == \"blocked\"",
            "      and result.reason == expected_reason",
            "      and (result.changed or 0) == 0",
            "      and structure_writes == before,",
            "  }",
            "end",
            "",
            "local function run_pilot()",
            "  local apply_task = context.apply_task",
            "  local rollback_task = context.rollback_task",
            "  local placements = shifted_placements(apply_task.placements, 0)",
            "  reset_nodes(placements)",
            "",
            "  local gates = {",
            "    missing_approval = run_gate(\"missing_approval\", 128, {",
            "      explicit_approval = false,",
            "    }, \"approval_required\"),",
            "    missing_rollback_policy = run_gate(\"missing_rollback_policy\", 192, {",
            "      rollback_policy = \"__nil\",",
            "    }, \"rollback_policy_not_mutating\"),",
            "    unsafe_private_payload = run_gate(\"unsafe_private_payload\", 256, {",
            "      private_payload = { rejected = true },",
            "    }, \"payload_rejected\"),",
            "    non_staging_target = run_gate(\"non_staging_target\", 320, {",
            "      world_id = \"family_voxelibre\",",
            "      target_world = { world_id = \"family_voxelibre\", staging = false },",
            "      staging = false,",
            "    }, \"staging_target_required\"),",
            "    over_budget = run_gate(\"over_budget\", 384, {",
            "      max_node_writes_per_step = 1,",
            "    }, \"node_write_budget_exceeded\"),",
            "  }",
            "",
            "  structure_writes = 0",
            "  reset_nodes(placements)",
            "  core.ai_import_ops.queue_chunked_structure_apply_task({",
            "    task_id = apply_task.task_id,",
            "    agent_id = apply_task.agent_id,",
            "    owner = apply_task.owner,",
            "    report_id = apply_task.report_id,",
            "    action_index = apply_task.action_index,",
            "    world_id = apply_task.world_id,",
            "    target_world = apply_task.target_world,",
            "    staging = apply_task.staging,",
            "    explicit_approval = apply_task.explicit_approval,",
            "    allow_mutation = apply_task.allow_mutation,",
            "    rollback_policy = apply_task.rollback_policy,",
            "    placements = placements,",
            "    get_node = get_probe_node,",
            "    set_node = set_probe_node,",
            "    chunk_size = apply_task.chunk_size,",
            "    max_node_writes_total = apply_task.max_node_writes_total,",
            "    max_node_writes_per_step = apply_task.max_node_writes_per_step,",
            "    max_mapblock_churn_total = apply_task.max_mapblock_churn_total,",
            "    max_wall_time_ms = apply_task.max_wall_time_ms,",
            "    source_reference = apply_task.source_reference,",
            "    persist_record = persist_probe_record,",
            "  })",
            "  local apply_status, apply_steps = step_until_final(apply_task.task_id, 8)",
            "  local completed_apply = core.get_ai_task(apply_task.task_id)",
            "  local apply_summary = core.ai_import_ops.build_apply_summary({",
            "    apply_id = \"apply-runtime:compat-staging-pilot\",",
            "    report_id = apply_task.report_id,",
            "    task_ids = { apply_task.task_id },",
            "    approved_actions = {",
            "      { action_index = apply_task.action_index, action = \"import_structure\" },",
            "    },",
            "    rollback_policy = apply_task.rollback_policy,",
            "  })",
            "  local node_count_after_apply = count_verified_nodes(placements, test_node)",
            "  local param_round_trip = check_param_round_trip(placements[2])",
            "",
            "  local apply_rollback_refs = rollback_refs_for_operation(nil)",
            "  local apply_rollback_ref_count = #apply_rollback_refs",
            "  configure_probe_rollback_storage()",
            "  local rollback_plan = core.ai_import_ops.plan_structure_rollback({",
            "    agent_id = apply_task.agent_id,",
            "    owner = apply_task.owner,",
            "    rollback_refs = apply_rollback_refs,",
            "  })",
            "",
            "  local rollback_records_before = 0",
            "  for _ in pairs(rollback_storage) do rollback_records_before = rollback_records_before + 1 end",
            "  core.ai_import_ops.queue_chunked_structure_rollback_task({",
            "    task_id = rollback_task.task_id,",
            "    agent_id = rollback_task.agent_id,",
            "    owner = rollback_task.owner,",
            "    source_task_id = apply_task.task_id,",
            "    rollback_refs = apply_rollback_refs,",
            "    world_id = rollback_task.world_id,",
            "    target_world = rollback_task.target_world,",
            "    staging = rollback_task.staging,",
            "    explicit_approval = rollback_task.explicit_approval,",
            "    allow_mutation = rollback_task.allow_mutation,",
            "    rollback_policy = rollback_task.rollback_policy,",
            "    reverse_order = rollback_task.reverse_order,",
            "    get_node = get_probe_node,",
            "    set_node = set_probe_node,",
            "    max_node_writes_total = rollback_task.max_node_writes_total,",
            "    max_node_writes_per_step = rollback_task.max_node_writes_per_step,",
            "    max_mapblock_churn_total = rollback_task.max_mapblock_churn_total,",
            "    max_wall_time_ms = rollback_task.max_wall_time_ms,",
            "  })",
            "  local rollback_status, rollback_steps = step_until_final(rollback_task.task_id, 8)",
            "  local completed_rollback = core.get_ai_task(rollback_task.task_id)",
            "  local nodes_reverted = count_verified_nodes(placements, \"air\")",
            "  local rollback_records_after = 0",
            "  for _ in pairs(rollback_storage) do rollback_records_after = rollback_records_after + 1 end",
            "",
            "  local all_gates_passed = true",
            "  for _, gate in pairs(gates) do",
            "    all_gates_passed = all_gates_passed and gate.passed == true",
            "  end",
            "",
            "  local payload = {",
            "    schema_version = 1,",
            "    live_result_kind = \"ai_native_compat_import_staging_pilot_result\",",
            "    generated_at = generated_at,",
            "    runtime_context = {",
            "      mode = \"disposable_live_ai_runtime_compat_import_staging_pilot\",",
            "      gameid = \"ai_runtime\",",
            "      requires_live_pi = false,",
            "      requires_private_world = false,",
            "      requires_private_assets = false,",
            "      requires_model_network = false,",
            "      world_mutation_performed = true,",
            "      world_mutation_scope = \"disposable_synthetic_ai_runtime_staging_world\",",
            "    },",
            "    workflow = {",
            "      inventory = context.inventory,",
            "      dry_run = context.dry_run,",
            "      operator_review = context.operator_review,",
            "      apply = {",
            "        task_id = apply_task.task_id,",
            "        task_status = apply_status,",
            "        step_count = apply_steps,",
            "        progress_current = completed_apply and completed_apply.progress.current or 0,",
            "        progress_total = completed_apply and completed_apply.progress.total or 0,",
            "        apply_summary_status = apply_summary.status,",
            "        completed_task_count = #apply_summary.completed_tasks,",
            "        node_writes_actual = apply_summary.mutation_cost_actual.node_writes,",
            "        mapblock_churn_actual = apply_summary.mutation_cost_actual.mapblock_churn,",
            "        rollback_record_count = #apply_summary.rollback_records,",
            "        node_writes_verified = node_count_after_apply,",
            "        param_round_trip_checked = param_round_trip,",
            "      },",
            "      rollback = {",
            "        plan_status = rollback_plan.status,",
            "        apply_rollback_ref_count = apply_rollback_ref_count,",
            "        plan_record_count = #(rollback_plan.rollback_records or {}),",
            "        planned_node_writes = rollback_plan.metrics.planned_node_writes,",
            "        planned_mapblock_churn = rollback_plan.metrics.mapblock_churn,",
            "        task_id = rollback_task.task_id,",
            "        task_status = rollback_status,",
            "        step_count = rollback_steps,",
            "        progress_current = completed_rollback and completed_rollback.progress.current or 0,",
            "        progress_total = completed_rollback and completed_rollback.progress.total or 0,",
            "        nodes_reverted = nodes_reverted,",
            "        rollback_execution_records = rollback_records_after - rollback_records_before,",
            "      },",
            "    },",
            "    refusal_gates = gates,",
            "    benchmark_coverage = {",
            "      status = \"pass\",",
            "      expected_node_writes = context.expected.node_writes,",
            "      actual_node_writes = apply_summary.mutation_cost_actual.node_writes,",
            "      expected_mapblock_churn = context.expected.mapblock_churn,",
            "      actual_mapblock_churn = apply_summary.mutation_cost_actual.mapblock_churn,",
            "      expected_apply_chunks = context.expected.chunk_count,",
            "      actual_apply_chunks = completed_apply and completed_apply.progress.total or 0,",
            "      max_node_writes_total = apply_task.max_node_writes_total,",
            "      max_node_writes_per_step = apply_task.max_node_writes_per_step,",
            "      max_mapblock_churn_total = apply_task.max_mapblock_churn_total,",
            "      over_budget_refused = gates.over_budget and gates.over_budget.passed == true,",
            "      mapblock_churn_recorded = apply_summary.mutation_cost_actual.mapblock_churn >= context.expected.mapblock_churn,",
            "    },",
            "    safety = {",
            "      public_safe_output = true,",
            "      disposable_live_world_only = true,",
            "      staging_target_only = true,",
            "      world_mutation_performed = true,",
            "      world_mutation_scope = \"disposable_synthetic_ai_runtime_staging_world\",",
            "      rollback_execution_performed = true,",
            "      import_promotion_execution_performed = false,",
            "      assets_copied = false,",
            "      no_raw_assets = true,",
            "      no_provider_prompts = true,",
            "      no_family_world_coordinates = true,",
            "      no_live_family_world_mutation = true,",
            "      all_refusal_gates_passed = all_gates_passed,",
            "    },",
            "    bounds = { max_bytes = max_bytes, output_bytes = 0, truncated = false },",
            "  }",
            "  payload.bounds.output_bytes = #core.write_json(payload)",
            "  return payload",
            "end",
            "",
            "core.register_on_mods_loaded(function()",
            "  core.after(0, function()",
            "    local ok, payload_or_error = pcall(run_pilot)",
            "    if not ok then",
            "      write_status(\"fail\", tostring(payload_or_error))",
            "      core.request_shutdown(\"compat import staging pilot failed\", false, 0)",
            "      return",
            "    end",
            "    local payload = payload_or_error",
            "    if payload.bounds.output_bytes > max_bytes then",
            "      write_status(\"fail\", \"pilot result exceeds max bytes\")",
            "      core.request_shutdown(\"compat import staging pilot failed\", false, 0)",
            "      return",
            "    end",
            "    if not core.safe_file_write(output_path, core.write_json(payload)) then",
            "      write_status(\"fail\", \"pilot result artifact write failed\")",
            "      core.request_shutdown(\"compat import staging pilot failed\", false, 0)",
            "      return",
            "    end",
            "    write_status(\"pass\", \"compat import staging pilot captured\")",
            "    core.request_shutdown(\"compat import staging pilot complete\", false, 0)",
            "  end)",
            "end)",
            "",
        ]),
        encoding="utf-8",
    )


def read_status(world_dir: Path) -> dict:
    status_path = world_dir / PILOT_STATUS_NAME
    if not status_path.is_file():
        return {"status": "fail", "reason": "pilot status missing"}
    try:
        return json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "fail", "reason": f"pilot status unreadable: {type(exc).__name__}"}


def _artifact_has_private_content(payload: dict) -> bool:
    raw = json.dumps(payload, sort_keys=True)
    return any(pattern.search(raw) for pattern in PRIVATE_PATTERNS)


def _require_bool(mapping: dict, field: str, expected: bool = True) -> None:
    if mapping.get(field) is not expected:
        raise ValueError(f"compat import staging pilot {field} is not {expected}")


def validate_live_result(payload: dict, max_bytes: int = DEFAULT_MAX_BYTES) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("compat import staging pilot result must be an object")
    if payload.get("live_result_kind") != "ai_native_compat_import_staging_pilot_result":
        raise ValueError("compat import staging pilot result kind is invalid")
    if _artifact_has_private_content(payload):
        raise ValueError("compat import staging pilot result contains private content")

    runtime_context = payload.get("runtime_context")
    if not isinstance(runtime_context, dict):
        raise ValueError("compat import staging pilot runtime_context missing or invalid")
    if runtime_context.get("mode") != "disposable_live_ai_runtime_compat_import_staging_pilot":
        raise ValueError("compat import staging pilot runtime mode is invalid")
    for flag in (
        "requires_live_pi",
        "requires_private_world",
        "requires_private_assets",
        "requires_model_network",
    ):
        if runtime_context.get(flag) is not False:
            raise ValueError(f"compat import staging pilot {flag} must be false")
    _require_bool(runtime_context, "world_mutation_performed")
    if runtime_context.get("world_mutation_scope") != "disposable_synthetic_ai_runtime_staging_world":
        raise ValueError("compat import staging pilot mutation scope is invalid")

    workflow = payload.get("workflow") if isinstance(payload.get("workflow"), dict) else {}
    inventory = workflow.get("inventory") if isinstance(workflow.get("inventory"), dict) else {}
    dry_run = workflow.get("dry_run") if isinstance(workflow.get("dry_run"), dict) else {}
    review = (
        workflow.get("operator_review")
        if isinstance(workflow.get("operator_review"), dict)
        else {}
    )
    apply = workflow.get("apply") if isinstance(workflow.get("apply"), dict) else {}
    rollback = workflow.get("rollback") if isinstance(workflow.get("rollback"), dict) else {}

    if inventory.get("status") != "ready_for_import_preview" or inventory.get("ready") is not True:
        raise ValueError("compat import staging pilot inventory was not ready")
    if inventory.get("sources_total") != 1:
        raise ValueError("compat import staging pilot inventory source count is invalid")
    if "import.assets" not in (inventory.get("required_capabilities") or []):
        raise ValueError("compat import staging pilot inventory capability evidence missing")

    if dry_run.get("source_class") != "structure":
        raise ValueError("compat import staging pilot dry-run source class is invalid")
    if dry_run.get("license_status") != "user_supplied":
        raise ValueError("compat import staging pilot dry-run license status is invalid")
    if dry_run.get("apply_plan_status") != "planned":
        raise ValueError("compat import staging pilot apply plan did not remain inert")
    estimated = dry_run.get("estimated_world_mutations") or {}
    if estimated.get("node_writes") != 5 or estimated.get("mapblock_churn") != 3:
        raise ValueError("compat import staging pilot dry-run mutation estimate is invalid")

    if review.get("smoke_status") != "ready":
        raise ValueError("compat import staging pilot smoke was not ready")
    if review.get("review_status") != "ready":
        raise ValueError("compat import staging pilot operator review was not ready")
    if review.get("machine_promotable") is not True:
        raise ValueError("compat import staging pilot was not machine promotable")
    if review.get("promotion_status") != "ready_for_operator_promotion":
        raise ValueError("compat import staging pilot promotion evidence was not ready")

    if apply.get("task_status") != "completed":
        raise ValueError("compat import staging pilot apply task did not complete")
    if apply.get("apply_summary_status") != "completed":
        raise ValueError("compat import staging pilot apply summary did not complete")
    for field, expected in (
        ("progress_current", 3),
        ("progress_total", 3),
        ("node_writes_actual", 5),
        ("mapblock_churn_actual", 3),
        ("rollback_record_count", 3),
        ("node_writes_verified", 5),
    ):
        if apply.get(field) != expected:
            raise ValueError(f"compat import staging pilot apply {field} is invalid")
    _require_bool(apply, "param_round_trip_checked")

    if rollback.get("plan_status") != "success":
        raise ValueError("compat import staging pilot rollback plan did not pass")
    for field, expected in (
        ("apply_rollback_ref_count", 3),
        ("plan_record_count", 3),
        ("planned_node_writes", 5),
        ("task_status", "completed"),
        ("progress_current", 3),
        ("progress_total", 3),
        ("nodes_reverted", 5),
        ("rollback_execution_records", 3),
    ):
        if rollback.get(field) != expected:
            raise ValueError(f"compat import staging pilot rollback {field} is invalid")
    if rollback.get("planned_mapblock_churn", 0) < 3:
        raise ValueError("compat import staging pilot rollback mapblock churn missing")

    gates = payload.get("refusal_gates") if isinstance(payload.get("refusal_gates"), dict) else {}
    expected_gates = {
        "missing_approval": "approval_required",
        "missing_rollback_policy": "rollback_policy_not_mutating",
        "unsafe_private_payload": "payload_rejected",
        "non_staging_target": "staging_target_required",
        "over_budget": "node_write_budget_exceeded",
    }
    for gate_name, expected_reason in expected_gates.items():
        gate = gates.get(gate_name)
        if not isinstance(gate, dict):
            raise ValueError(f"compat import staging pilot gate {gate_name} missing")
        if gate.get("passed") is not True:
            raise ValueError(f"compat import staging pilot gate {gate_name} did not pass")
        if gate.get("status") != "blocked" or gate.get("reason") != expected_reason:
            raise ValueError(f"compat import staging pilot gate {gate_name} reason is invalid")
        if gate.get("changed") != 0 or gate.get("writes_attempted") != 0:
            raise ValueError(f"compat import staging pilot gate {gate_name} mutated")

    benchmark = (
        payload.get("benchmark_coverage")
        if isinstance(payload.get("benchmark_coverage"), dict)
        else {}
    )
    if benchmark.get("status") != "pass":
        raise ValueError("compat import staging pilot benchmark coverage did not pass")
    for field, expected in (
        ("expected_node_writes", 5),
        ("actual_node_writes", 5),
        ("expected_mapblock_churn", 3),
        ("actual_mapblock_churn", 3),
        ("expected_apply_chunks", 3),
        ("actual_apply_chunks", 3),
        ("max_node_writes_total", 5),
        ("max_node_writes_per_step", 2),
        ("max_mapblock_churn_total", 3),
    ):
        if benchmark.get(field) != expected:
            raise ValueError(f"compat import staging pilot benchmark {field} is invalid")
    _require_bool(benchmark, "over_budget_refused")
    _require_bool(benchmark, "mapblock_churn_recorded")

    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    for field in (
        "public_safe_output",
        "disposable_live_world_only",
        "staging_target_only",
        "world_mutation_performed",
        "rollback_execution_performed",
        "no_raw_assets",
        "no_provider_prompts",
        "no_family_world_coordinates",
        "no_live_family_world_mutation",
        "all_refusal_gates_passed",
    ):
        _require_bool(safety, field)
    for field in ("import_promotion_execution_performed", "assets_copied"):
        if safety.get(field) is not False:
            raise ValueError(f"compat import staging pilot safety {field} must be false")
    if safety.get("world_mutation_scope") != "disposable_synthetic_ai_runtime_staging_world":
        raise ValueError("compat import staging pilot safety mutation scope is invalid")

    bounds = payload.get("bounds") if isinstance(payload.get("bounds"), dict) else {}
    output_bytes = bounds.get("output_bytes")
    declared_max = bounds.get("max_bytes", max_bytes)
    if not isinstance(output_bytes, int) or not isinstance(declared_max, int):
        raise ValueError("compat import staging pilot bounds are invalid")
    if output_bytes > declared_max or output_bytes > max_bytes:
        raise ValueError("compat import staging pilot output exceeds max bytes")

    return {
        "compat_import_staging_pilot_status": "pass",
        "compat_import_staging_pilot_output_bytes": output_bytes,
        "compat_import_inventory_ready": True,
        "compat_import_dry_run_source_class": dry_run["source_class"],
        "compat_import_operator_review_ready": True,
        "compat_import_apply_status": apply["task_status"],
        "compat_import_node_writes": apply["node_writes_actual"],
        "compat_import_mapblock_churn": apply["mapblock_churn_actual"],
        "compat_import_apply_chunks": apply["progress_total"],
        "compat_import_rollback_records": apply["rollback_record_count"],
        "compat_import_rollback_refs": rollback["apply_rollback_ref_count"],
        "compat_import_rollback_plan_records": rollback["plan_record_count"],
        "compat_import_rollback_execution_records": rollback["rollback_execution_records"],
        "compat_import_refusal_gates": len(expected_gates),
        "compat_import_world_mutation": True,
        "compat_import_mutation_scope": "disposable_synthetic_ai_runtime_staging_world",
    }


def run_probe(args) -> int:
    root = resolve_path(Path.cwd(), args.root).resolve()
    server_bin = resolve_path(root, args.server_bin)
    output = resolve_path(root, args.output)
    fixture = resolve_path(root, args.fixture)
    output.parent.mkdir(parents=True, exist_ok=True)

    try:
        context = build_pilot_context(fixture, args.generated_at)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"compat import staging pilot context invalid: {type(exc).__name__}", file=sys.stderr)
        return 1

    world_dir = output.parent / "compat-import-staging-pilot-world"
    write_probe_world(world_dir, context, args.generated_at, args.max_bytes)

    port = args.port or reserve_udp_port()
    log_path = world_dir / "debug.log"
    config_path = world_dir / "pilot.conf"
    config_path.write_text(
        "\n".join([
            "server_name = AI Native Compat Import Staging Pilot",
            "name = compat_import_staging_pilot",
            "secure.enable_security = true",
            "creative_mode = false",
            "enable_damage = false",
            "",
        ]),
        encoding="utf-8",
    )
    command = [
        str(server_bin),
        "--world",
        str(world_dir),
        "--gameid",
        "ai_runtime",
        "--port",
        str(port),
        "--config",
        str(config_path),
        "--logfile",
        str(log_path),
        "--color",
        "never",
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
            timeout=args.timeout,
        )
    except subprocess.TimeoutExpired:
        print("compat import staging pilot timed out", file=sys.stderr)
        return 1
    if completed.returncode != 0:
        print("compat import staging pilot server exited with non-zero status", file=sys.stderr)
        if completed.stderr.strip():
            print(completed.stderr.strip()[-1200:], file=sys.stderr)
        return 1

    status = read_status(world_dir)
    if status.get("status") != "pass":
        print(
            f"compat import staging pilot failed: {status.get('reason', 'unknown')}",
            file=sys.stderr,
        )
        return 1

    world_artifact = world_dir / PILOT_ARTIFACT_NAME
    if not world_artifact.is_file():
        print("compat import staging pilot artifact missing", file=sys.stderr)
        return 1
    try:
        payload = json.loads(world_artifact.read_text(encoding="utf-8"))
        validate_live_result(payload, max_bytes=args.max_bytes)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"compat import staging pilot artifact invalid: {type(exc).__name__}", file=sys.stderr)
        return 1
    shutil.copyfile(world_artifact, output)
    print("compat import staging pilot captured")
    return 0


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Capture public-safe inventory-to-staging apply evidence from a disposable ai_runtime world."
    )
    parser.add_argument("--root", default=".", help="Luanti source checkout root.")
    parser.add_argument("--server-bin", default="bin/luantiserver", help="Server binary to launch.")
    parser.add_argument("--fixture", default=str(FIXTURE.relative_to(ROOT)), help="Public-safe structure fixture.")
    parser.add_argument("--output", required=True, help="Output JSON artifact path.")
    parser.add_argument("--generated-at", default=utc_now(), help="generated_at value for the pilot.")
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES, help="Output byte budget.")
    parser.add_argument("--timeout", type=float, default=20.0, help="Seconds to wait for pilot shutdown.")
    parser.add_argument("--port", type=int, help="Optional UDP port for the disposable server.")
    return parser.parse_args(argv)


def main(argv=None):
    return run_probe(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
