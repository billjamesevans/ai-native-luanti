#!/usr/bin/env python3
"""Probe the first-party agent product loop in a disposable ai_runtime world."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIVE_ARTIFACT_NAME = "ai-runtime-agent-product-loop-live-result.json"
LIVE_RESULT_NAME = "ai-runtime-agent-product-loop-live-probe-result.json"
PROBE_MOD_NAME = "ai_agent_product_loop_live_probe"
DEFAULT_MAX_BYTES = 26000

PRIVATE_PATTERNS = (
    re.compile(r"/Users/[^\s\"']+"),
    re.compile(r"\bminecraftpi(?:\.home)?\b", re.I),
    re.compile(r"\b192\.168(?:\.\d{1,3}){2}\b"),
    re.compile(r"\bspacebase|themepark|showcase100|disneyland100\b", re.I),
    re.compile(r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"\bOPENAI_API_KEY\b"),
    re.compile(r"\bprivate_prompt\b"),
    re.compile(r"\basset_payload\b"),
)


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


def write_probe_world(world_dir: Path, generated_at: str, max_bytes: int) -> None:
    if world_dir.exists():
        shutil.rmtree(world_dir)
    mod_dir = world_dir / "worldmods" / PROBE_MOD_NAME
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
    (mod_dir / "mod.conf").write_text(f"name = {PROBE_MOD_NAME}\n", encoding="utf-8")
    (mod_dir / "init.lua").write_text(
        "\n".join([
            "local output_path = core.get_worldpath() .. " + lua_string("/" + LIVE_ARTIFACT_NAME),
            "local result_path = core.get_worldpath() .. " + lua_string("/" + LIVE_RESULT_NAME),
            "local generated_at = " + lua_string(generated_at),
            f"local max_bytes = {int(max_bytes)}",
            "local world_id = \"agent-product-loop-live-world\"",
            "local hazard_node = \"ai_agent_product_loop_probe:hazard\"",
            "local marker_node = \"ai_runtime_base:cobble\"",
            "",
            "core.register_node(\":\" .. hazard_node, {",
            "  description = \"AI Agent Product Loop Probe Hazard\",",
            "  tiles = {\"blank.png\"},",
            "  groups = { hazard = 1 },",
            "})",
            "",
            "local function write_result(status, reason)",
            "  core.safe_file_write(result_path, core.write_json({",
            "    status = status,",
            "    reason = reason,",
            "    execution_path = \"disposable_live_ai_runtime_agent_product_loop_probe\",",
            "  }))",
            "end",
            "",
            "local function pos(x)",
            "  return { x = x, y = 12, z = 120 }",
            "end",
            "",
            "local function copy_pos(target_pos)",
            "  return { x = target_pos.x, y = target_pos.y, z = target_pos.z }",
            "end",
            "",
            "local build_pos = pos(0)",
            "local repair_pos = pos(2)",
            "local cancel_pos = pos(4)",
            "local retry_pos = pos(6)",
            "local follow_pos = pos(8)",
            "",
            "local clean_capabilities = {",
            "  [\"world.read\"] = true,",
            "  [\"world.place\"] = true,",
            "  [\"world.remove\"] = true,",
            "  [\"entity.spawn\"] = true,",
            "  [\"entity.control\"] = true,",
            "  [\"task.cancel\"] = true,",
            "  [\"http.llm\"] = true,",
            "}",
            "",
            "local function configure_agent_plugin(profile, capabilities)",
            "  core.ai_agent_plugin.configure({",
            "    capability_profile = profile or \"clean\",",
            "    light_node = marker_node,",
            "    marker_node = marker_node,",
            "    repair_nodes = { [hazard_node] = true },",
            "    max_lights = 4,",
            "    capabilities = capabilities or clean_capabilities,",
            "  })",
            "end",
            "",
            "local function reset_probe_nodes()",
            "  if core.load_area then",
            "    core.load_area({ x = -2, y = 10, z = 118 }, { x = 8, y = 14, z = 122 })",
            "  end",
            "  core.set_node(build_pos, { name = \"air\" })",
            "  core.set_node(repair_pos, { name = hazard_node })",
            "  core.set_node(cancel_pos, { name = \"air\" })",
            "  core.set_node({ x = cancel_pos.x, y = cancel_pos.y + 1, z = cancel_pos.z }, { name = \"air\" })",
            "  core.set_node(retry_pos, { name = \"air\" })",
            "end",
            "",
            "local rollback_records = {}",
            "local function persist_probe_record(record)",
            "  rollback_records[record.record_id] = record",
            "  return { ok = true, storage_ref = \"rollback://agent-product-loop-live/\" .. record.record_id }",
            "end",
            "",
            "local retry_persist_attempts = 0",
            "local function persist_retry_record(record)",
            "  retry_persist_attempts = retry_persist_attempts + 1",
            "  if retry_persist_attempts == 1 then",
            "    return false",
            "  end",
            "  return persist_probe_record(record)",
            "end",
            "",
            "local function live_context(target_pos)",
            "  return {",
            "    pos = target_pos,",
            "    world_id = world_id,",
            "    persist_record = persist_probe_record,",
            "  }",
            "end",
            "",
            "local function node_name(target_pos)",
            "  local node = core.get_node_or_nil and core.get_node_or_nil(target_pos) or core.get_node(target_pos)",
            "  return node and node.name or \"unknown\"",
            "end",
            "",
            "local function handle(name, message, context)",
            "  local result = core.ai_agent_plugin.handle_command(name, message, context or {})",
            "  if type(result) ~= \"table\" then",
            "    error(\"agent command did not return a table: \" .. tostring(message))",
            "  end",
            "  return result",
            "end",
            "",
            "local function task_status(task_id)",
            "  local task = core.get_ai_task(task_id)",
            "  return task and task.status or \"missing\"",
            "end",
            "",
            "local function last_reason(task_id)",
            "  local task = core.get_ai_task(task_id)",
            "  return task and task.last_result and task.last_result.reason or nil",
            "end",
            "",
            "local function is_final(status)",
            "  return status == \"completed\" or status == \"cancelled\"",
            "    or status == \"blocked\" or status == \"unsafe\" or status == \"failed\"",
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
            "local function count_statuses(task_ids)",
            "  local counts = {}",
            "  for _, task_id in ipairs(task_ids) do",
            "    local status = task_status(task_id)",
            "    counts[status] = (counts[status] or 0) + 1",
            "  end",
            "  return counts",
            "end",
            "",
            "local function count_bad_final_tasks(task_ids)",
            "  local total = 0",
            "  for _, task_id in ipairs(task_ids) do",
            "    local status = task_status(task_id)",
            "    if status == \"blocked\" or status == \"unsafe\" or status == \"failed\" then",
            "      total = total + 1",
            "    end",
            "  end",
            "  return total",
            "end",
            "",
            "local function run_probe()",
            "  configure_agent_plugin(\"clean\", clean_capabilities)",
            "  reset_probe_nodes()",
            "  local task_ids = {}",
            "",
            "  local build_preview = handle(\"BuilderLive\", \"build plan\", live_context(build_pos))",
            "  local build_pending = handle(\"BuilderLive\", \"build marker\", live_context(build_pos))",
            "  local build_pending_review = handle(\"BuilderLive\", \"pending plan\", {})",
            "  local build_edit = handle(\"BuilderLive\", \"edit plan platform width 2 depth 2\", live_context(build_pos))",
            "  local build_approved = handle(\"BuilderLive\", \"approve\", {})",
            "  task_ids[#task_ids + 1] = build_approved.task_id",
            "  local build_status = step_until_final(build_approved.task_id, 3)",
            "",
            "  local repair_preview = handle(\"RepairLive\", \"repair plan\", live_context(repair_pos))",
            "  local repair_pending = handle(\"RepairLive\", \"repair\", live_context(repair_pos))",
            "  local repair_pending_review = handle(\"RepairLive\", \"pending plan\", {})",
            "  local repair_edit = handle(\"RepairLive\", \"plan edit radius 0\", live_context(repair_pos))",
            "  local repair_approved = handle(\"RepairLive\", \"approve\", {})",
            "  task_ids[#task_ids + 1] = repair_approved.task_id",
            "  local repair_status = step_until_final(repair_approved.task_id, 3)",
            "",
            "  local cancel_queued = handle(\"CancelLive\", \"place 2 lights\", live_context(cancel_pos))",
            "  task_ids[#task_ids + 1] = cancel_queued.task_id",
            "  local cancel_before = task_status(cancel_queued.task_id)",
            "  local cancel_reply = handle(\"CancelLive\", \"cancel\", {})",
            "  local cancel_after = task_status(cancel_queued.task_id)",
            "",
            "  local retry_context = live_context(retry_pos)",
            "  retry_context.persist_record = persist_retry_record",
            "  local retry_pending = handle(\"RetryLive\", \"build marker\", retry_context)",
            "  local retry_approved = handle(\"RetryLive\", \"approve\", {})",
            "  task_ids[#task_ids + 1] = retry_approved.task_id",
            "  local retry_blocked_status = step_until_final(retry_approved.task_id, 3)",
            "  local retry_blocked_reason = last_reason(retry_approved.task_id)",
            "  local retry_result = core.retry_ai_task(retry_approved.task_id, \"RetryLive\")",
            "  local retry_final_status = step_until_final(retry_approved.task_id, 3)",
            "",
            "  local follow_player_pos = copy_pos(follow_pos)",
            "  local follow_player = {",
            "    get_pos = function() return copy_pos(follow_player_pos) end,",
            "  }",
            "  local follow_reply = handle(\"FollowLive\", \"follow 2\", {",
            "    get_player_by_name = function(name)",
            "      if name == \"FollowLive\" then return follow_player end",
            "      return nil",
            "    end,",
            "    max_follow_steps = 2,",
            "    max_follow_step_distance = 2,",
            "    max_follow_total_distance = 6,",
            "    max_follow_stop_distance = 0,",
            "  })",
            "  task_ids[#task_ids + 1] = follow_reply.task_id",
            "  core.step_ai_tasks()",
            "  follow_player_pos = { x = follow_pos.x + 2, y = follow_pos.y, z = follow_pos.z }",
            "  local follow_status = step_until_final(follow_reply.task_id, 3)",
            "  local follow_task = core.get_ai_task(follow_reply.task_id)",
            "  local follow_result = follow_task and follow_task.last_result or {}",
            "  local follow_entity = follow_result.entity or {}",
            "  local follow_metrics = follow_result.metrics or {}",
            "",
            "  local guide_reply = handle(\"BuilderLive\", \"guide\", {})",
            "  local tasks_reply = handle(\"BuilderLive\", \"tasks\", {})",
            "  local audit_reply = handle(\"BuilderLive\", \"audit\", {})",
            "  local build_rollback_reply = handle(\"BuilderLive\", \"rollback\", {})",
            "  local repair_rollback_reply = handle(\"RepairLive\", \"rollback\", {})",
            "  local targeted_audit_reply = handle(\"BuilderLive\", \"audit \" .. build_approved.task_id, {})",
            "  local targeted_rollback_reply = handle(\"BuilderLive\", \"rollback \" .. build_approved.task_id, {})",
            "  local targeted_rollback_record_id = nil",
            "  if targeted_rollback_reply.rollback_records and targeted_rollback_reply.rollback_records[1] then",
            "    targeted_rollback_record_id = targeted_rollback_reply.rollback_records[1].rollback_record_id",
            "  end",
            "  local targeted_rollback_record_reply = { status = \"blocked\", rollback_records = {} }",
            "  if targeted_rollback_record_id then",
            "    targeted_rollback_record_reply = handle(\"BuilderLive\", \"rollback \" .. targeted_rollback_record_id, {})",
            "  end",
            "  local surface_by_id = {}",
            "  for _, surface in ipairs(guide_reply.product_surfaces or {}) do",
            "    surface_by_id[surface.surface_id] = surface",
            "  end",
            "  local function surface_agent_checked(surface_id)",
            "    local agents = guide_reply.surface_agents or {}",
            "    local agent = agents[surface_id] or {}",
            "    return agent.agent_id == \"nova_agent:BuilderLive:\" .. surface_id",
            "  end",
            "  local function surface_required_granted(surface_id)",
            "    local surface = surface_by_id[surface_id] or {}",
            "    return surface.required_capabilities_granted == true",
            "  end",
            "  local function surface_default_grant(surface_id)",
            "    local surface = surface_by_id[surface_id] or {}",
            "    return surface.default_clean_profile_grant",
            "  end",
            "",
            "  configure_agent_plugin(\"operator\", {",
            "    [\"combat.defend\"] = true,",
            "    [\"task.cancel\"] = true,",
            "  })",
            "  local defended = false",
            "  local defender_pos = pos(10)",
            "  local defender_player = {",
            "    get_pos = function() return defender_pos end,",
            "    set_pos = function() return true end,",
            "    get_attach = function() return nil end,",
            "  }",
            "  local defend_reply = handle(\"DefenderLive\", \"defend\", {",
            "    get_player_by_name = function(name)",
            "      if name == \"DefenderLive\" then return defender_player end",
            "      return nil",
            "    end,",
            "    hostiles = {",
            "      {",
            "        entity_id = \"hostile:agent-product-loop-live\",",
            "        entity_name = \"ai_runtime_probe:hostile\",",
            "        pos = { x = defender_pos.x + 1, y = defender_pos.y, z = defender_pos.z },",
            "      },",
            "    },",
            "    attack_entity = function() defended = true; return true end,",
            "    max_defend_distance = 8,",
            "  })",
            "  task_ids[#task_ids + 1] = defend_reply.task_id",
            "  local defend_status = step_until_final(defend_reply.task_id, 3)",
            "",
            "  configure_agent_plugin(\"operator\", {",
            "    [\"import.assets\"] = true,",
            "    [\"task.cancel\"] = true,",
            "  })",
            "  local import_reply = handle(\"ImporterLive\", \"import plan\", {",
            "    import_plan = {",
            "      source = {",
            "        source_id = \"agent-product-loop-live-inventory\",",
            "        source_class = \"synthetic_resource_pack\",",
            "        inventory = {",
            "          {",
            "            entry_id = \"entry:agent-product-loop-live:1\",",
            "            source_path = \"textures/agent_product_loop_live.png\",",
            "            source_kind = \"texture\",",
            "            classification = \"mapped\",",
            "            reason = \"metadata_reference_only\",",
            "            required_capabilities = { \"import.assets\" },",
            "          },",
            "        },",
            "        content_hashes = {",
            "          {",
            "            algorithm = \"sha256\",",
            "            value = string.rep(\"2\", 64),",
            "            purpose = \"synthetic live product loop inventory hash\",",
            "          },",
            "        },",
            "      },",
            "      dry_run = true,",
            "      planned_actions = {",
            "        {",
            "          action = \"map_texture\",",
            "          status = \"partial\",",
            "          required_capabilities = { \"import.assets\" },",
            "          provenance = {",
            "            source_id = \"agent-product-loop-live-inventory\",",
            "            inventory_refs = { \"entry:agent-product-loop-live:1\" },",
            "            classification = \"mapped\",",
            "          },",
            "          mutation_cost = { node_writes = 0, media_files = 1, manual_review_items = 1 },",
            "        },",
            "      },",
            "    },",
            "  })",
            "  task_ids[#task_ids + 1] = import_reply.task_id",
            "  local import_status = step_until_final(import_reply.task_id, 3)",
            "",
            "  local operator_status_snapshot = {",
            "    status = \"unavailable\",",
            "    tasks_total = 0,",
            "    completed_tasks = 0,",
            "    cancelled_tasks = 0,",
            "    rollback_records_available = 0,",
            "    import_reviews_total = 0,",
            "    operator_control_recommendations_total = 0,",
            "    public_safe_output = false,",
            "  }",
            "  if type(core.build_ai_operator_status_package) == \"function\" then",
            "    local package = core.build_ai_operator_status_package({",
            "      generated_at = generated_at,",
            "      max_bytes = 12000,",
            "    })",
            "    local task_counts = package.tasks and package.tasks.counts or {}",
            "    operator_status_snapshot = {",
            "      status = package.status,",
            "      tasks_total = task_counts.total or 0,",
            "      completed_tasks = task_counts.completed or 0,",
            "      cancelled_tasks = task_counts.cancelled or 0,",
            "      rollback_records_available = package.rollback and package.rollback.records_available or 0,",
            "      import_reviews_total = package.imports and package.imports.reviews_total or 0,",
            "      operator_control_recommendations_total = package.operator_control and package.operator_control.recommendations_total or 0,",
            "      public_safe_output = package.safety and package.safety.public_safe_output == true,",
            "    }",
            "  end",
            "",
            "  configure_agent_plugin(\"clean\", clean_capabilities)",
            "",
            "  local build_rollback_count = #(build_rollback_reply.rollback_records or {})",
            "  local repair_rollback_count = #(repair_rollback_reply.rollback_records or {})",
            "  local rollback_count = build_rollback_count + repair_rollback_count",
            "  local audit_count = #(audit_reply.audit_events or {})",
            "  local targeted_audit_count = #(targeted_audit_reply.audit_events or {})",
            "  local targeted_rollback_count = #(targeted_rollback_reply.rollback_records or {})",
            "  local targeted_rollback_record_count = #(targeted_rollback_record_reply.rollback_records or {})",
            "  local final_bad = count_bad_final_tasks(task_ids)",
            "",
            "  local payload = {",
            "    schema_version = 1,",
            "    live_result_kind = \"ai_native_agent_product_loop_live_result\",",
            "    generated_at = generated_at,",
            "    runtime_context = {",
            "      mode = \"disposable_live_ai_runtime_agent_product_loop_probe\",",
            "      gameid = \"ai_runtime\",",
            "      requires_live_pi = false,",
            "      requires_private_world = false,",
            "      requires_private_assets = false,",
            "      requires_model_network = false,",
            "      world_mutation_performed = true,",
            "      world_mutation_scope = \"disposable_synthetic_ai_runtime_world\",",
            "    },",
            "    workflow = {",
            "      build = {",
            "        preview_status = build_preview.status,",
            "        pending_status = build_pending.status,",
            "        pending_review_status = build_pending_review.status,",
            "        approval_id = build_pending.approval_id,",
            "        edit_status = build_edit.status,",
            "        edit_approval_id = build_edit.approval_id,",
            "        edit_build_kind = build_edit.build_kind,",
            "        edit_build_width = build_edit.build_width,",
            "        edit_build_depth = build_edit.build_depth,",
            "        edit_planned_node_writes = build_edit.planned_node_writes,",
            "        approved_status = build_approved.status,",
            "        task_id = build_approved.task_id,",
            "        task_status = build_status,",
            "        node_after = node_name(build_pos),",
            "        rollback_record_count = build_rollback_count,",
            "      },",
            "      repair = {",
            "        preview_status = repair_preview.status,",
            "        pending_status = repair_pending.status,",
            "        pending_review_status = repair_pending_review.status,",
            "        approval_id = repair_pending.approval_id,",
            "        edit_status = repair_edit.status,",
            "        edit_approval_id = repair_edit.approval_id,",
            "        edit_repair_radius = repair_edit.repair_radius,",
            "        edit_candidate_count = repair_edit.candidate_count,",
            "        approved_status = repair_approved.status,",
            "        task_id = repair_approved.task_id,",
            "        task_status = repair_status,",
            "        node_after = node_name(repair_pos),",
            "        rollback_record_count = repair_rollback_count,",
            "      },",
            "      task_control = {",
            "        cancel_checked = cancel_after == \"cancelled\",",
            "        cancel_before_status = cancel_before,",
            "        cancel_after_status = cancel_after,",
            "        cancel_command_status = cancel_reply.status,",
            "        retry_checked = retry_final_status == \"completed\",",
            "        retry_blocked_status = retry_blocked_status,",
            "        retry_blocked_reason = retry_blocked_reason,",
            "        retry_result_status = retry_result.status,",
            "        retry_final_status = retry_final_status,",
            "      },",
            "      navigation = {",
            "        follow_status = follow_reply.status,",
            "        follow_task_id = follow_reply.task_id,",
            "        follow_task_status = follow_status,",
            "        follow_entity_name = follow_entity.entity_name,",
            "        follow_distance_moved = follow_metrics.distance_moved or 0,",
            "        follow_total_distance_moved = follow_metrics.total_distance_moved or 0,",
            "        follow_node_writes = follow_metrics.node_writes or 0,",
            "        follow_pathfinder_used = follow_metrics.pathfinder_used == true,",
            "      },",
            "      targeted_reviews = {",
            "        audit_status = targeted_audit_reply.status,",
            "        audit_target_kind = targeted_audit_reply.target_kind,",
            "        audit_target_id = targeted_audit_reply.target_id,",
            "        audit_event_count = targeted_audit_count,",
            "        rollback_status = targeted_rollback_reply.status,",
            "        rollback_target_kind = targeted_rollback_reply.target_kind,",
            "        rollback_target_id = targeted_rollback_reply.target_id,",
            "        rollback_record_count = targeted_rollback_count,",
            "        rollback_record_id = targeted_rollback_record_id,",
            "        rollback_record_status = targeted_rollback_record_reply.status,",
            "        rollback_record_target_kind = targeted_rollback_record_reply.target_kind,",
            "        rollback_record_target_id = targeted_rollback_record_reply.target_id,",
            "        rollback_record_review_count = targeted_rollback_record_count,",
            "        no_rollback_execution = targeted_rollback_reply.no_rollback_execution == true",
            "          and targeted_rollback_record_reply.no_rollback_execution == true,",
            "      },",
            "      surfaces = {",
            "        guide_command_checked = guide_reply.status == \"success\" and guide_reply.surfaces.builder == true,",
            "        product_surface_catalog_checked = #(guide_reply.product_surfaces or {}) == 5,",
            "        builder_surface_agent_checked = surface_agent_checked(\"builder\")",
            "          and surface_required_granted(\"builder\"),",
            "        repair_surface_agent_checked = surface_agent_checked(\"repair\")",
            "          and surface_required_granted(\"repair\"),",
            "        guide_surface_agent_checked = surface_agent_checked(\"guide\")",
            "          and surface_required_granted(\"guide\"),",
            "        defender_clean_grant_absent = surface_agent_checked(\"defender\")",
            "          and surface_default_grant(\"defender\") == \"not_granted\"",
            "          and not surface_required_granted(\"defender\"),",
            "        importer_clean_grant_absent = surface_agent_checked(\"importer\")",
            "          and surface_default_grant(\"importer\") == \"not_granted\"",
            "          and not surface_required_granted(\"importer\"),",
            "        tasks_command_checked = tasks_reply.status == \"success\",",
            "        audit_review_checked = audit_count > 0,",
            "        rollback_review_checked = rollback_count >= 2,",
            "        pending_plan_review_checked = build_pending_review.status == \"success\"",
            "          and repair_pending_review.status == \"success\",",
            "        plan_edit_checked = build_edit.status == \"success\"",
            "          and repair_edit.status == \"success\"",
            "          and build_edit.approval_id == build_pending.approval_id",
            "          and repair_edit.approval_id == repair_pending.approval_id",
            "          and build_edit.build_kind == \"platform\"",
            "          and build_edit.build_width == 2",
            "          and build_edit.build_depth == 2",
            "          and repair_edit.repair_radius == 0,",
            "        targeted_audit_review_checked = targeted_audit_reply.status == \"success\"",
            "          and targeted_audit_reply.target_kind == \"task\"",
            "          and targeted_audit_reply.target_id == build_approved.task_id",
            "          and targeted_audit_count > 0,",
            "        targeted_rollback_review_checked = targeted_rollback_reply.status == \"success\"",
            "          and targeted_rollback_reply.target_kind == \"task\"",
            "          and targeted_rollback_reply.target_id == build_approved.task_id",
            "          and targeted_rollback_reply.no_rollback_execution == true",
            "          and targeted_rollback_count > 0,",
            "        targeted_rollback_record_review_checked = targeted_rollback_record_id ~= nil",
            "          and targeted_rollback_record_reply.status == \"success\"",
            "          and targeted_rollback_record_reply.target_kind == \"rollback\"",
            "          and targeted_rollback_record_reply.target_id == targeted_rollback_record_id",
            "          and targeted_rollback_record_reply.no_rollback_execution == true",
            "          and targeted_rollback_record_count > 0,",
            "        follow_command_checked = follow_reply.status == \"queued\"",
            "          and follow_status == \"completed\"",
            "          and follow_entity.entity_name == \"ai_runtime_base:helper\"",
            "          and (follow_metrics.distance_moved or 0) > 0",
            "          and (follow_metrics.node_writes or 0) == 0,",
            "        defender_command_checked = defend_status == \"completed\" and defended == true,",
            "        import_preview_checked = import_status == \"completed\",",
            "        operator_status_checked = operator_status_snapshot.status == \"ready\"",
            "          and operator_status_snapshot.tasks_total >= 6",
            "          and operator_status_snapshot.rollback_records_available >= 2",
            "          and operator_status_snapshot.import_reviews_total >= 1,",
            "      },",
            "    },",
            "    operator_status_snapshot = operator_status_snapshot,",
            "    summary = {",
            "      preview_plan_count = 2,",
            "      pending_plan_review_count = 2,",
            "      plan_edit_count = 2,",
            "      approval_plan_count = 2,",
            "      approved_task_count = 2,",
            "      task_count = #task_ids,",
            "      task_status_counts = count_statuses(task_ids),",
            "      rollback_record_count = rollback_count,",
            "      audit_event_count = audit_count,",
            "      targeted_audit_review_count = targeted_audit_count > 0 and 1 or 0,",
            "      targeted_rollback_review_count = (targeted_rollback_count > 0 and 1 or 0)",
            "        + (targeted_rollback_record_count > 0 and 1 or 0),",
            "      follow_command_count = follow_status == \"completed\" and 1 or 0,",
            "      node_writes_verified = 5,",
            "      transient_blocked_outcomes = retry_blocked_status == \"blocked\" and 1 or 0,",
            "      final_blocked_or_unsafe_outcomes = final_bad,",
            "    },",
            "    safety = {",
            "      public_safe_output = true,",
            "      disposable_live_world_only = true,",
            "      world_mutation_performed = true,",
            "      world_mutation_scope = \"disposable_synthetic_ai_runtime_world\",",
            "      rollback_execution_performed = false,",
            "      import_promotion_execution_performed = false,",
            "      assets_copied = false,",
            "      no_raw_assets = true,",
            "      no_provider_prompts = true,",
            "      no_family_world_coordinates = true,",
            "    },",
            "    bounds = { max_bytes = max_bytes, output_bytes = 0, truncated = false },",
            "  }",
            "  payload.bounds.output_bytes = #core.write_json(payload)",
            "  return payload",
            "end",
            "",
            "core.register_on_mods_loaded(function()",
            "  core.after(0, function()",
            "  local ok, payload_or_error = pcall(run_probe)",
            "  if not ok then",
            "    write_result(\"fail\", tostring(payload_or_error))",
            "    core.request_shutdown(\"agent product loop live probe failed\", false, 0)",
            "    return",
            "  end",
            "  local payload = payload_or_error",
            "  if payload.bounds.output_bytes > max_bytes then",
            "    write_result(\"fail\", \"live result exceeds max bytes\")",
            "    core.request_shutdown(\"agent product loop live probe failed\", false, 0)",
            "    return",
            "  end",
            "  if not core.safe_file_write(output_path, core.write_json(payload)) then",
            "    write_result(\"fail\", \"live result artifact write failed\")",
            "    core.request_shutdown(\"agent product loop live probe failed\", false, 0)",
            "    return",
            "  end",
            "  write_result(\"pass\", \"first-party agent product loop captured\")",
            "  core.request_shutdown(\"agent product loop live probe complete\", false, 0)",
            "  end)",
            "end)",
            "",
        ]),
        encoding="utf-8",
    )


def read_result(world_dir: Path) -> dict:
    result_path = world_dir / LIVE_RESULT_NAME
    if not result_path.is_file():
        return {"status": "fail", "reason": "probe result missing"}
    try:
        return json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "fail", "reason": f"probe result unreadable: {type(exc).__name__}"}


def _artifact_has_private_content(payload: dict) -> bool:
    raw = json.dumps(payload, sort_keys=True)
    return any(pattern.search(raw) for pattern in PRIVATE_PATTERNS)


def _require_bool(mapping: dict, field: str, expected: bool = True) -> None:
    if mapping.get(field) is not expected:
        raise ValueError(f"agent product loop {field} is not {expected}")


def validate_live_result(payload: dict, max_bytes: int = DEFAULT_MAX_BYTES) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("agent product loop result must be an object")
    if payload.get("live_result_kind") != "ai_native_agent_product_loop_live_result":
        raise ValueError("agent product loop result kind is invalid")
    if _artifact_has_private_content(payload):
        raise ValueError("agent product loop result contains private content")

    runtime_context = payload.get("runtime_context")
    if not isinstance(runtime_context, dict):
        raise ValueError("agent product loop runtime_context missing or invalid")
    if runtime_context.get("mode") != "disposable_live_ai_runtime_agent_product_loop_probe":
        raise ValueError("agent product loop runtime mode is invalid")
    for flag in (
        "requires_live_pi",
        "requires_private_world",
        "requires_private_assets",
        "requires_model_network",
    ):
        if runtime_context.get(flag) is not False:
            raise ValueError(f"agent product loop {flag} must be false")
    if runtime_context.get("world_mutation_performed") is not True:
        raise ValueError("agent product loop must perform disposable world mutation")
    if runtime_context.get("world_mutation_scope") != "disposable_synthetic_ai_runtime_world":
        raise ValueError("agent product loop mutation scope is invalid")

    workflow = payload.get("workflow") if isinstance(payload.get("workflow"), dict) else {}
    build = workflow.get("build") if isinstance(workflow.get("build"), dict) else {}
    repair = workflow.get("repair") if isinstance(workflow.get("repair"), dict) else {}
    task_control = (
        workflow.get("task_control")
        if isinstance(workflow.get("task_control"), dict)
        else {}
    )
    navigation = (
        workflow.get("navigation")
        if isinstance(workflow.get("navigation"), dict)
        else {}
    )
    targeted_reviews = (
        workflow.get("targeted_reviews")
        if isinstance(workflow.get("targeted_reviews"), dict)
        else {}
    )
    surfaces = workflow.get("surfaces") if isinstance(workflow.get("surfaces"), dict) else {}

    for name, section in (("build", build), ("repair", repair)):
        if section.get("preview_status") != "success":
            raise ValueError(f"agent product loop {name} preview did not pass")
        if section.get("pending_status") != "pending_approval":
            raise ValueError(f"agent product loop {name} did not require approval")
        if section.get("pending_review_status") != "success":
            raise ValueError(f"agent product loop {name} pending review did not pass")
        if section.get("edit_status") != "success":
            raise ValueError(f"agent product loop {name} plan edit did not pass")
        if section.get("edit_approval_id") != section.get("approval_id"):
            raise ValueError(f"agent product loop {name} plan edit changed approval id")
        if section.get("approved_status") != "queued":
            raise ValueError(f"agent product loop {name} approval did not queue")
        if section.get("task_status") != "completed":
            raise ValueError(f"agent product loop {name} task did not complete")
        if not isinstance(section.get("approval_id"), str) or not section["approval_id"]:
            raise ValueError(f"agent product loop {name} approval id missing")
        if not isinstance(section.get("task_id"), str) or not section["task_id"]:
            raise ValueError(f"agent product loop {name} task id missing")
        if not isinstance(section.get("rollback_record_count"), int) or section["rollback_record_count"] < 1:
            raise ValueError(f"agent product loop {name} rollback evidence missing")
    if build.get("node_after") != "ai_runtime_base:cobble":
        raise ValueError("agent product loop build node result is invalid")
    if build.get("edit_build_kind") != "platform":
        raise ValueError("agent product loop build edit did not switch to platform")
    if build.get("edit_build_width") != 2 or build.get("edit_build_depth") != 2:
        raise ValueError("agent product loop build edit dimensions are invalid")
    if build.get("edit_planned_node_writes") != 4:
        raise ValueError("agent product loop build edit write plan is invalid")
    if repair.get("node_after") != "air":
        raise ValueError("agent product loop repair node result is invalid")
    if repair.get("edit_repair_radius") != 0:
        raise ValueError("agent product loop repair edit radius is invalid")
    if not isinstance(repair.get("edit_candidate_count"), int) or repair["edit_candidate_count"] < 1:
        raise ValueError("agent product loop repair edit candidate evidence missing")

    _require_bool(task_control, "cancel_checked")
    if task_control.get("cancel_before_status") != "queued":
        raise ValueError("agent product loop cancel target was not queued")
    if task_control.get("cancel_after_status") != "cancelled":
        raise ValueError("agent product loop cancel target was not cancelled")
    _require_bool(task_control, "retry_checked")
    if task_control.get("retry_blocked_status") != "blocked":
        raise ValueError("agent product loop did not prove blocked retry setup")
    if task_control.get("retry_result_status") != "queued":
        raise ValueError("agent product loop retry did not requeue")
    if task_control.get("retry_final_status") != "completed":
        raise ValueError("agent product loop retry did not complete")

    if navigation.get("follow_status") != "queued":
        raise ValueError("agent product loop follow command did not queue")
    if navigation.get("follow_task_status") != "completed":
        raise ValueError("agent product loop follow task did not complete")
    if navigation.get("follow_entity_name") != "ai_runtime_base:helper":
        raise ValueError("agent product loop follow did not use clean helper entity")
    if not isinstance(navigation.get("follow_distance_moved"), (int, float)) or navigation["follow_distance_moved"] <= 0:
        raise ValueError("agent product loop follow movement evidence missing")
    if not isinstance(navigation.get("follow_total_distance_moved"), (int, float)) or navigation["follow_total_distance_moved"] <= 0:
        raise ValueError("agent product loop follow total movement evidence missing")
    if navigation.get("follow_node_writes") != 0:
        raise ValueError("agent product loop follow mutated nodes")

    if targeted_reviews.get("audit_status") != "success":
        raise ValueError("agent product loop targeted audit did not pass")
    if targeted_reviews.get("audit_target_kind") != "task":
        raise ValueError("agent product loop targeted audit target kind is invalid")
    if targeted_reviews.get("audit_target_id") != build.get("task_id"):
        raise ValueError("agent product loop targeted audit target id is invalid")
    if not isinstance(targeted_reviews.get("audit_event_count"), int) or targeted_reviews["audit_event_count"] < 1:
        raise ValueError("agent product loop targeted audit evidence missing")
    if targeted_reviews.get("rollback_status") != "success":
        raise ValueError("agent product loop targeted rollback review did not pass")
    if targeted_reviews.get("rollback_target_kind") != "task":
        raise ValueError("agent product loop targeted rollback target kind is invalid")
    if targeted_reviews.get("rollback_target_id") != build.get("task_id"):
        raise ValueError("agent product loop targeted rollback target id is invalid")
    if not isinstance(targeted_reviews.get("rollback_record_count"), int) or targeted_reviews["rollback_record_count"] < 1:
        raise ValueError("agent product loop targeted rollback evidence missing")
    rollback_record_id = targeted_reviews.get("rollback_record_id")
    if not isinstance(rollback_record_id, str) or not rollback_record_id:
        raise ValueError("agent product loop targeted rollback record id missing")
    if targeted_reviews.get("rollback_record_status") != "success":
        raise ValueError("agent product loop targeted rollback-record review did not pass")
    if targeted_reviews.get("rollback_record_target_kind") != "rollback":
        raise ValueError("agent product loop targeted rollback-record target kind is invalid")
    if targeted_reviews.get("rollback_record_target_id") != rollback_record_id:
        raise ValueError("agent product loop targeted rollback-record target id is invalid")
    if (
        not isinstance(targeted_reviews.get("rollback_record_review_count"), int)
        or targeted_reviews["rollback_record_review_count"] < 1
    ):
        raise ValueError("agent product loop targeted rollback-record evidence missing")
    _require_bool(targeted_reviews, "no_rollback_execution")

    for field in (
        "guide_command_checked",
        "product_surface_catalog_checked",
        "builder_surface_agent_checked",
        "repair_surface_agent_checked",
        "guide_surface_agent_checked",
        "defender_clean_grant_absent",
        "importer_clean_grant_absent",
        "tasks_command_checked",
        "audit_review_checked",
        "rollback_review_checked",
        "pending_plan_review_checked",
        "plan_edit_checked",
        "targeted_audit_review_checked",
        "targeted_rollback_review_checked",
        "targeted_rollback_record_review_checked",
        "follow_command_checked",
        "defender_command_checked",
        "import_preview_checked",
        "operator_status_checked",
    ):
        _require_bool(surfaces, field)

    operator_status_snapshot = (
        payload.get("operator_status_snapshot")
        if isinstance(payload.get("operator_status_snapshot"), dict)
        else {}
    )
    if operator_status_snapshot.get("status") != "ready":
        raise ValueError("agent product loop operator status snapshot is not ready")
    if operator_status_snapshot.get("public_safe_output") is not True:
        raise ValueError("agent product loop operator status snapshot is not public-safe")
    for field, minimum in (
        ("tasks_total", 6),
        ("completed_tasks", 5),
        ("cancelled_tasks", 1),
        ("rollback_records_available", 2),
        ("import_reviews_total", 1),
        ("operator_control_recommendations_total", 1),
    ):
        value = operator_status_snapshot.get(field)
        if not isinstance(value, int) or value < minimum:
            raise ValueError(f"agent product loop operator status {field} is too low")

    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    expected_counts = {
        "preview_plan_count": 2,
        "pending_plan_review_count": 2,
        "plan_edit_count": 2,
        "approval_plan_count": 2,
        "approved_task_count": 2,
        "rollback_record_count": 2,
        "targeted_audit_review_count": 1,
        "targeted_rollback_review_count": 2,
        "follow_command_count": 1,
        "node_writes_verified": 5,
        "transient_blocked_outcomes": 1,
        "final_blocked_or_unsafe_outcomes": 0,
    }
    for field, minimum in expected_counts.items():
        value = summary.get(field)
        if not isinstance(value, int):
            raise ValueError(f"agent product loop summary {field} is invalid")
        if field == "final_blocked_or_unsafe_outcomes":
            if value != 0:
                raise ValueError("agent product loop has blocked/unsafe final outcomes")
        elif value < minimum:
            raise ValueError(f"agent product loop summary {field} is too low")
    if not isinstance(summary.get("audit_event_count"), int) or summary["audit_event_count"] < 1:
        raise ValueError("agent product loop audit evidence missing")

    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    for field in (
        "public_safe_output",
        "disposable_live_world_only",
        "world_mutation_performed",
        "no_raw_assets",
        "no_provider_prompts",
        "no_family_world_coordinates",
    ):
        _require_bool(safety, field)
    if safety.get("world_mutation_scope") != "disposable_synthetic_ai_runtime_world":
        raise ValueError("agent product loop safety mutation scope is invalid")
    for field in (
        "rollback_execution_performed",
        "import_promotion_execution_performed",
        "assets_copied",
    ):
        if safety.get(field) is not False:
            raise ValueError(f"agent product loop safety {field} must be false")

    bounds = payload.get("bounds") if isinstance(payload.get("bounds"), dict) else {}
    output_bytes = bounds.get("output_bytes")
    declared_max = bounds.get("max_bytes", max_bytes)
    if not isinstance(output_bytes, int) or not isinstance(declared_max, int):
        raise ValueError("agent product loop bounds are invalid")
    if output_bytes > declared_max or output_bytes > max_bytes:
        raise ValueError("agent product loop output exceeds max bytes")

    return {
        "agent_product_loop_live_status": "pass",
        "agent_product_loop_live_output_bytes": output_bytes,
        "agent_product_loop_preview_plans": summary["preview_plan_count"],
        "agent_product_loop_pending_plan_reviews": summary["pending_plan_review_count"],
        "agent_product_loop_plan_edits": summary["plan_edit_count"],
        "agent_product_loop_approval_plans": summary["approval_plan_count"],
        "agent_product_loop_approved_tasks": summary["approved_task_count"],
        "agent_product_loop_rollback_records": summary["rollback_record_count"],
        "agent_product_loop_audit_events": summary["audit_event_count"],
        "agent_product_loop_targeted_audit_reviews": summary["targeted_audit_review_count"],
        "agent_product_loop_targeted_rollback_reviews": summary["targeted_rollback_review_count"],
        "agent_product_loop_follow_commands": summary["follow_command_count"],
        "agent_product_loop_cancel_checked": True,
        "agent_product_loop_retry_checked": True,
        "agent_product_loop_follow_checked": True,
        "agent_product_loop_follow_helper_entity": navigation["follow_entity_name"],
        "agent_product_loop_operator_status_checked": True,
        "agent_product_loop_pending_plan_review_checked": True,
        "agent_product_loop_plan_edit_checked": True,
        "agent_product_loop_targeted_audit_review_checked": True,
        "agent_product_loop_targeted_rollback_review_checked": True,
        "agent_product_loop_targeted_rollback_record_review_checked": True,
        "agent_product_loop_product_surface_catalog_checked": True,
        "agent_product_loop_builder_surface_agent_checked": True,
        "agent_product_loop_repair_surface_agent_checked": True,
        "agent_product_loop_guide_surface_agent_checked": True,
        "agent_product_loop_defender_clean_grant_absent": True,
        "agent_product_loop_importer_clean_grant_absent": True,
        "agent_product_loop_operator_status_tasks": operator_status_snapshot["tasks_total"],
        "agent_product_loop_operator_status_rollbacks": operator_status_snapshot["rollback_records_available"],
        "agent_product_loop_operator_status_import_reviews": operator_status_snapshot["import_reviews_total"],
        "agent_product_loop_final_blocked_or_unsafe": summary["final_blocked_or_unsafe_outcomes"],
        "agent_product_loop_world_mutation": True,
        "agent_product_loop_mutation_scope": "disposable_synthetic_ai_runtime_world",
    }


def run_probe(args) -> int:
    root = resolve_path(Path.cwd(), args.root).resolve()
    server_bin = resolve_path(root, args.server_bin)
    output = resolve_path(root, args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    world_dir = output.parent / "agent-product-loop-live-world"
    write_probe_world(world_dir, args.generated_at, args.max_bytes)

    port = args.port or reserve_udp_port()
    log_path = world_dir / "debug.log"
    config_path = world_dir / "probe.conf"
    config_path.write_text(
        "\n".join([
            "server_name = AI Native Agent Product Loop Live Probe",
            "name = agent_product_loop_probe",
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
        print("agent product loop live probe timed out", file=sys.stderr)
        return 1
    if completed.returncode != 0:
        print("agent product loop live server exited with non-zero status", file=sys.stderr)
        if completed.stderr.strip():
            print(completed.stderr.strip()[-1200:], file=sys.stderr)
        return 1

    result = read_result(world_dir)
    if result.get("status") != "pass":
        reason = result.get("reason", "unknown")
        print(f"agent product loop live probe failed: {reason}", file=sys.stderr)
        return 1

    world_artifact = world_dir / LIVE_ARTIFACT_NAME
    if not world_artifact.is_file():
        print("agent product loop live artifact missing", file=sys.stderr)
        return 1
    try:
        payload = json.loads(world_artifact.read_text(encoding="utf-8"))
        validate_live_result(payload, max_bytes=args.max_bytes)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"agent product loop live artifact invalid: {type(exc).__name__}", file=sys.stderr)
        return 1
    shutil.copyfile(world_artifact, output)
    print("agent product loop live probe captured")
    return 0


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Capture the first-party agent product loop from a disposable ai_runtime world."
    )
    parser.add_argument("--root", default=".", help="Luanti source checkout root.")
    parser.add_argument("--server-bin", default="bin/luantiserver", help="Server binary to launch.")
    parser.add_argument("--output", required=True, help="Output JSON artifact path.")
    parser.add_argument("--generated-at", required=True, help="generated_at value for the probe.")
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES, help="Output byte budget.")
    parser.add_argument("--timeout", type=float, default=20.0, help="Seconds to wait for probe shutdown.")
    parser.add_argument("--port", type=int, help="Optional UDP port for the disposable server.")
    return parser.parse_args(argv)


def main(argv=None):
    return run_probe(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
