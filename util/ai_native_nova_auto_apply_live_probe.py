#!/usr/bin/env python3
"""Probe Nova auto-applied builds in a disposable ai_runtime world."""

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
LIVE_ARTIFACT_NAME = "ai-runtime-nova-auto-apply-live-result.json"
LIVE_RESULT_NAME = "ai-runtime-nova-auto-apply-live-probe-result.json"
PROBE_MOD_NAME = "nova_auto_apply_live_probe"
DEFAULT_MAX_BYTES = 36000

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


def write_probe_world(
    world_dir: Path,
    generated_at: str,
    max_bytes: int,
    adapter_endpoint: str | None,
) -> None:
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
    mod_conf = f"name = {PROBE_MOD_NAME}\n"
    if adapter_endpoint:
        mod_conf += "depends = ai_runtime_agents_sdk_bridge\n"
    (mod_dir / "mod.conf").write_text(mod_conf, encoding="utf-8")
    adapter_mode = "agents_sdk_sidecar" if adapter_endpoint else "mock_async_adapter"
    (mod_dir / "init.lua").write_text(
        "\n".join([
            "local output_path = core.get_worldpath() .. " + lua_string("/" + LIVE_ARTIFACT_NAME),
            "local result_path = core.get_worldpath() .. " + lua_string("/" + LIVE_RESULT_NAME),
            "local generated_at = " + lua_string(generated_at),
            f"local max_bytes = {int(max_bytes)}",
            "local adapter_mode = " + lua_string(adapter_mode),
            "local finished = false",
            "",
            "local cases = {",
            "  {",
            "    case_id = \"fire_only_strict\",",
            "    owner = \"AutoApplyFireProbe\",",
            "    prompt = \"build me a fire and only a fire\",",
            "    pos = { x = 20, y = 10, z = 20 },",
            "    expected_candidate = \"fire\",",
            "    expected_kind = \"fire\",",
            "    expected_material = \"fire\",",
            "    expected_node = \"ai_runtime_base:fire\",",
            "    expected_writes = 1,",
            "    count_radius = 2,",
            "  },",
            "  {",
            "    case_id = \"fire_simple\",",
            "    owner = \"AutoApplySimpleFireProbe\",",
            "    prompt = \"build a fire\",",
            "    pos = { x = 32, y = 10, z = 20 },",
            "    expected_candidate = \"fire\",",
            "    expected_kind = \"fire\",",
            "    expected_material = \"fire\",",
            "    expected_node = \"ai_runtime_base:fire\",",
            "    expected_writes = 1,",
            "    count_radius = 2,",
            "  },",
            "  {",
            "    case_id = \"fire_me_simple\",",
            "    owner = \"AutoApplyMeFireProbe\",",
            "    prompt = \"build me a fire\",",
            "    pos = { x = 44, y = 10, z = 20 },",
            "    expected_candidate = \"fire\",",
            "    expected_kind = \"fire\",",
            "    expected_material = \"fire\",",
            "    expected_node = \"ai_runtime_base:fire\",",
            "    expected_writes = 1,",
            "    count_radius = 2,",
            "  },",
            "  {",
            "    case_id = \"tnt_wall\",",
            "    owner = \"AutoApplyTntProbe\",",
            "    prompt = \"build a wall of tnt\",",
            "    pos = { x = 60, y = 10, z = 20 },",
            "    expected_candidate = \"tnt_wall\",",
            "    expected_kind = \"wall\",",
            "    expected_material = \"tnt\",",
            "    expected_node = \"ai_runtime_base:tnt\",",
            "    expected_writes = 12,",
            "    count_radius = 5,",
            "  },",
            "  {",
            "    case_id = \"generated_dimensioned_wall\",",
            "    owner = \"AutoApplyGeneratedWallProbe\",",
            "    prompt = \"build a 6 wide 2 high lookout wall\",",
            "    pos = { x = 82, y = 10, z = 20 },",
            "    expected_candidate = \"generated_dimensioned_wall\",",
            "    expected_kind = \"wall\",",
            "    expected_material = \"stone\",",
            "    expected_node = \"ai_runtime_base:stone\",",
            "    expected_writes = 12,",
            "    expected_width = 6,",
            "    expected_height = 2,",
            "    requires_generated_option = true,",
            "    expected_tool_trace_names = {",
            "      \"recall_build_prompt_memory\",",
            "      \"select_build_option\",",
            "      \"propose_build_option\",",
            "      \"select_build_option\",",
            "      \"plan_build_actions\",",
            "    },",
            "    count_radius = 7,",
            "  },",
            "}",
            "",
            "local results = {}",
            "local default_tool_trace_names = {",
            "  \"recall_build_prompt_memory\",",
            "  \"select_build_option\",",
            "  \"plan_build_actions\",",
            "}",
            "",
            "local function clone_pos(pos)",
            "  return { x = pos.x, y = pos.y, z = pos.z }",
            "end",
            "",
            "local function summarize_reply(reply)",
            "  reply = reply or {}",
            "  return {",
            "    ok = reply.ok == true,",
            "    action = reply.action,",
            "    status = reply.status,",
            "    reason = reply.reason,",
            "    message = reply.message,",
            "    task_id = reply.task_id,",
            "    approval_id = reply.approval_id,",
            "    approved_action = reply.approved_action,",
            "    auto_applied_approval = reply.auto_applied_approval == true,",
            "    auto_apply_policy = reply.auto_apply_policy,",
            "    planner_mode = reply.planner_mode,",
            "    selected_candidate_id = reply.selected_candidate_id,",
            "    adapter_selected_candidate_id = reply.adapter_selected_candidate_id,",
            "    model_selected_candidate_id = reply.model_selected_candidate_id,",
            "    selection_source = reply.selection_source,",
            "    build_kind = reply.build_kind,",
            "    build_width = reply.build_width,",
            "    build_height = reply.build_height,",
            "    build_material_name = reply.build_material_name,",
            "    build_material_node = reply.build_material_node,",
            "    planned_node_writes = reply.planned_node_writes,",
            "    candidate_count = reply.candidate_count,",
            "    adapter_tool_decision_source = reply.adapter_tool_decision_source,",
            "    adapter_agent_repair_attempted = reply.adapter_agent_repair_attempted,",
            "    adapter_agent_repair_succeeded = reply.adapter_agent_repair_succeeded,",
            "    adapter_agent_repair_reason = reply.adapter_agent_repair_reason,",
            "    adapter_initial_missing_required_tool_calls =",
            "      reply.adapter_initial_missing_required_tool_calls,",
            "    adapter_required_tool_calls_satisfied = reply.adapter_required_tool_calls_satisfied,",
            "    adapter_missing_required_tool_calls = reply.adapter_missing_required_tool_calls,",
            "    adapter_tool_trace_names = reply.adapter_tool_trace_names,",
            "    adapter_build_action_plan_status = reply.adapter_build_action_plan_status,",
            "    adapter_build_action_plan_step_count = reply.adapter_build_action_plan_step_count,",
            "    adapter_build_action_plan_world_mutation_authority =",
            "      reply.adapter_build_action_plan_world_mutation_authority,",
            "    generated_build_option_status = reply.generated_build_option_status,",
            "    generated_build_option_reason = reply.generated_build_option_reason,",
            "    generated_candidate_id = reply.generated_candidate_id,",
            "    agentic_tool_success_required = reply.agentic_tool_success_required,",
            "  }",
            "end",
            "",
            "local function summarize_trace(trace)",
            "  trace = trace or {}",
            "  return {",
            "    trace_id = trace.trace_id,",
            "    route = trace.route,",
            "    action = trace.action,",
            "    public_prompt = trace.public_prompt,",
            "    response = summarize_reply(trace.response or {}),",
            "  }",
            "end",
            "",
            "local function summarize_task(task)",
            "  task = task or {}",
            "  local result = task.last_result or {}",
            "  return {",
            "    task_id = task.task_id,",
            "    status = task.status,",
            "    reason = task.reason,",
            "    last_result = {",
            "      ok = result.ok == true,",
            "      status = result.status,",
            "      reason = result.reason,",
            "      changed = result.changed,",
            "      rollback_record_id = result.rollback_record_id,",
            "      rollback_storage_ref = result.rollback_storage_ref,",
            "      metrics = result.metrics,",
            "    },",
            "  }",
            "end",
            "",
            "local function write_result(status, reason)",
            "  core.safe_file_write(result_path, core.write_json({",
            "    status = status,",
            "    reason = reason,",
            "    execution_path = \"disposable_live_ai_runtime_nova_auto_apply_probe\",",
            "  }))",
            "end",
            "",
            "local function shutdown(reason)",
            "  core.after(0.25, function()",
            "    core.request_shutdown(reason, false, 0)",
            "  end)",
            "end",
            "",
            "local function write_payload(status, reason)",
            "  local passed = 0",
            "  for _, case in ipairs(results) do",
            "    if case.ok == true then",
            "      passed = passed + 1",
            "    end",
            "  end",
            "  local payload = {",
            "    schema_version = 1,",
            "    live_result_kind = \"ai_native_nova_auto_apply_live_result\",",
            "    generated_at = generated_at,",
            "    status = status,",
            "    ok = status == \"pass\",",
            "    reason = reason,",
            "    runtime_context = {",
            "      mode = \"disposable_live_ai_runtime_nova_auto_apply_probe\",",
            "      gameid = \"ai_runtime\",",
            "      adapter_mode = adapter_mode,",
            "      command = \"/nova\",",
            "      requires_live_pi = false,",
            "      requires_private_world = false,",
            "      requires_private_assets = false,",
            "      requires_model_network = adapter_mode == \"agents_sdk_sidecar\",",
            "      world_mutation_performed = true,",
            "      world_mutation_scope = \"disposable_synthetic_ai_runtime_world\",",
            "    },",
            "    summary = {",
            "      cases_total = #cases,",
            "      cases_passed = passed,",
            "      cases_failed = #results - passed,",
            "      fire_only_strict_checked = false,",
            "      fire_simple_checked = false,",
            "      fire_me_simple_checked = false,",
            "      tnt_wall_checked = false,",
            "      generated_dimensioned_wall_checked = false,",
            "      agentic_build_planner_checked = true,",
            "      auto_apply_checked = true,",
            "      rollback_checked = true,",
            "    },",
            "    cases = results,",
            "    safety = {",
            "      public_safe_output = true,",
            "      disposable_live_world_only = true,",
            "      world_mutation_performed = true,",
            "      world_mutation_scope = \"disposable_synthetic_ai_runtime_world\",",
            "      world_mutation_authority = \"luanti\",",
            "      no_raw_assets = true,",
            "      no_provider_prompts = true,",
            "      no_family_world_coordinates = true,",
            "      no_private_prompt_retained = true,",
            "    },",
            "    bounds = { max_bytes = max_bytes, output_bytes = 0, truncated = false },",
            "  }",
            "  for _, case in ipairs(results) do",
            "    if case.case_id == \"fire_only_strict\" and case.ok == true then",
            "      payload.summary.fire_only_strict_checked = true",
            "    elseif case.case_id == \"fire_simple\" and case.ok == true then",
            "      payload.summary.fire_simple_checked = true",
            "    elseif case.case_id == \"fire_me_simple\" and case.ok == true then",
            "      payload.summary.fire_me_simple_checked = true",
            "    elseif case.case_id == \"tnt_wall\" and case.ok == true then",
            "      payload.summary.tnt_wall_checked = true",
            "    elseif case.case_id == \"generated_dimensioned_wall\"",
            "        and case.ok == true then",
            "      payload.summary.generated_dimensioned_wall_checked = true",
            "    end",
            "  end",
            "  payload.bounds.output_bytes = #core.write_json(payload)",
            "  if payload.bounds.output_bytes > max_bytes then",
            "    payload.bounds.truncated = true",
            "    for _, case in ipairs(payload.cases) do",
            "      case.trace = nil",
            "    end",
            "    payload.bounds.output_bytes = #core.write_json(payload)",
            "  end",
            "  return payload",
            "end",
            "",
            "local function finish(status, reason)",
            "  if finished then",
            "    return",
            "  end",
            "  finished = true",
            "  local payload = write_payload(status, reason)",
            "  if payload.bounds.output_bytes > max_bytes then",
            "    write_result(\"fail\", \"nova auto-apply artifact exceeded max bytes\")",
            "    shutdown(\"nova auto-apply live probe failed\")",
            "    return",
            "  end",
            "  if not core.safe_file_write(output_path, core.write_json(payload)) then",
            "    write_result(\"fail\", \"nova auto-apply artifact write failed\")",
            "    shutdown(\"nova auto-apply live probe failed\")",
            "    return",
            "  end",
            "  write_result(status, reason)",
            "  shutdown(reason)",
            "end",
            "",
            "local function fail(case_result, reason)",
            "  case_result.status = \"fail\"",
            "  case_result.reason = reason",
            "  results[#results + 1] = case_result",
            "  finish(\"fail\", reason)",
            "end",
            "",
            "local function bounds(center, radius)",
            "  return { x = center.x - radius, y = center.y - radius, z = center.z - radius },",
            "    { x = center.x + radius, y = center.y + radius, z = center.z + radius }",
            "end",
            "",
            "local function prepare_area(center, radius)",
            "  for x = -radius, radius do",
            "    for y = -radius, radius do",
            "      for z = -radius, radius do",
            "        core.set_node({ x = center.x + x, y = center.y + y, z = center.z + z },",
            "          { name = \"air\" })",
            "      end",
            "    end",
            "  end",
            "end",
            "",
            "local function count_node(center, radius, node_name)",
            "  local count = 0",
            "  for x = -radius, radius do",
            "    for y = -radius, radius do",
            "      for z = -radius, radius do",
            "        if core.get_node({ x = center.x + x, y = center.y + y,",
            "            z = center.z + z }).name == node_name then",
            "          count = count + 1",
            "        end",
            "      end",
            "    end",
            "  end",
            "  return count",
            "end",
            "",
            "local function count_non_air(center, radius)",
            "  local count = 0",
            "  for x = -radius, radius do",
            "    for y = -radius, radius do",
            "      for z = -radius, radius do",
            "        if core.get_node({ x = center.x + x, y = center.y + y,",
            "            z = center.z + z }).name ~= \"air\" then",
            "          count = count + 1",
            "        end",
            "      end",
            "    end",
            "  end",
            "  return count",
            "end",
            "",
            "local map_block_size = 16",
            "",
            "local function block_floor(value)",
            "  return math.floor(value / map_block_size) * map_block_size",
            "end",
            "",
            "local function forceload_area(minp, maxp)",
            "  local held = {}",
            "  if not core.forceload_block then",
            "    return held",
            "  end",
            "  for x = block_floor(minp.x), block_floor(maxp.x), map_block_size do",
            "    for y = block_floor(minp.y), block_floor(maxp.y), map_block_size do",
            "      for z = block_floor(minp.z), block_floor(maxp.z), map_block_size do",
            "        local pos = { x = x, y = y, z = z }",
            "        local ok, loaded = pcall(core.forceload_block, pos, true, -1)",
            "        if ok and loaded == true then",
            "          held[#held + 1] = pos",
            "        end",
            "      end",
            "    end",
            "  end",
            "  return held",
            "end",
            "",
            "local function free_forceloaded_area(held)",
            "  if not core.forceload_free_block or type(held) ~= \"table\" then",
            "    return",
            "  end",
            "  for _, pos in ipairs(held) do",
            "    pcall(core.forceload_free_block, pos, true)",
            "  end",
            "end",
            "",
            "local function tool_trace_contains_in_order(tool_names, expected)",
            "  if type(tool_names) ~= \"table\" or type(expected) ~= \"table\" then",
            "    return false",
            "  end",
            "  local expected_index = 1",
            "  if #expected == 0 then",
            "    return true",
            "  end",
            "  for _, name in ipairs(tool_names) do",
            "    if name == expected[expected_index] then",
            "      expected_index = expected_index + 1",
            "      if expected_index > #expected then",
            "        return true",
            "      end",
            "    end",
            "  end",
            "  return false",
            "end",
            "",
            "local function emerge_for_case(spec, case_result, callback)",
            "  local minp, maxp = bounds(spec.pos, spec.count_radius + 2)",
            "  if core.load_area then",
            "    pcall(core.load_area, minp, maxp)",
            "  end",
            "  if not core.emerge_area then",
            "    callback()",
            "    return",
            "  end",
            "  local done = false",
            "  core.emerge_area(minp, maxp, function(_, _, calls_remaining)",
            "    if done then",
            "      return",
            "    end",
            "    if calls_remaining == 0 then",
            "      done = true",
            "      core.after(0.15, callback)",
            "    end",
            "  end)",
            "  core.after(25, function()",
            "    if not done and not finished then",
            "      fail(case_result, \"case \" .. spec.case_id ..",
            "        \" timed out waiting for area emergence\")",
            "    end",
            "  end)",
            "end",
            "",
            "local function mock_selected_option_id(prompt)",
            "  prompt = tostring(prompt or \"\"):lower()",
            "  if prompt:find(\"tnt\", 1, true) then",
            "    return \"tnt_wall\"",
            "  end",
            "  if prompt:find(\"6 wide\", 1, true)",
            "      and prompt:find(\"2 high\", 1, true)",
            "      and prompt:find(\"wall\", 1, true) then",
            "    return \"generated_dimensioned_wall\"",
            "  end",
            "  return \"fire\"",
            "end",
            "",
            "local function generated_dimensioned_wall_option()",
            "  return {",
            "    option_id = \"generated_dimensioned_wall\",",
            "    label = \"Generated 6x2 stone wall\",",
            "    reason = \"player requested exact wall dimensions\",",
            "    build_kind = \"wall\",",
            "    build_material_name = \"stone\",",
            "    build_width = 6,",
            "    build_height = 2,",
            "    planned_node_writes = 12,",
            "  }",
            "end",
            "",
            "local function install_mock_adapter()",
            "  if adapter_mode ~= \"mock_async_adapter\" then",
            "    return",
            "  end",
            "  core.ai_agent_plugin.set_model_adapter_async(function(request, done)",
            "    local prompt = request and request.context and request.context.player_request or \"\"",
            "    local selected = mock_selected_option_id(prompt)",
            "    local generated_option = nil",
            "    local required_tools = {",
            "      \"recall_build_prompt_memory\",",
            "      \"select_build_option\",",
            "      \"plan_build_actions\",",
            "    }",
            "    local tool_trace = {",
            "      { tool_name = \"recall_build_prompt_memory\" },",
            "      { tool_name = \"select_build_option\" },",
            "      { tool_name = \"plan_build_actions\" },",
            "    }",
            "    if selected == \"generated_dimensioned_wall\" then",
            "      generated_option = generated_dimensioned_wall_option()",
            "      required_tools = {",
            "        \"recall_build_prompt_memory\",",
            "        \"propose_build_option\",",
            "        \"select_build_option\",",
            "        \"plan_build_actions\",",
            "      }",
            "      tool_trace = {",
            "        { tool_name = \"recall_build_prompt_memory\" },",
            "        { tool_name = \"select_build_option\" },",
            "        { tool_name = \"propose_build_option\" },",
            "        { tool_name = \"select_build_option\" },",
            "        { tool_name = \"plan_build_actions\" },",
            "      }",
            "    end",
            "    core.after(0.1, function()",
            "      done({",
            "        ok = true,",
            "        message = \"Mock Nova auto-apply build planner response.\",",
            "        adapter_name = \"mock-nova-auto-apply-planner\",",
            "        elapsed_us = 1000,",
            "        response = {",
            "          agentic_execution = true,",
            "          selected_option_id = selected,",
            "          tool_decision_source = \"agents_sdk_function_tool\",",
            "          generated_build_option = generated_option,",
            "          required_tool_calls = required_tools,",
            "          missing_required_tool_calls = {},",
            "          required_tool_calls_satisfied = true,",
            "          tool_trace = tool_trace,",
            "          tool_decisions = {",
            "            build_option = {",
            "              selected_option_id = selected,",
            "              decision_source = selected == \"generated_dimensioned_wall\"",
            "                and \"agent_selected_generated_build_option\"",
            "                or \"agent_selected_build_option\",",
            "              generated_option_status = generated_option and \"ready\" or nil,",
            "              generated_option = generated_option,",
            "            },",
            "            build_action_plan = {",
            "              status = \"ready\",",
            "              selected_option_id = selected,",
            "              step_count = 4,",
            "              world_mutation_authority = \"luanti\",",
            "            },",
            "          },",
            "        },",
            "      })",
            "    end)",
            "    return true, \"queued\"",
            "  end)",
            "end",
            "",
            "local run_case",
            "local function run_next(index)",
            "  if index > #cases then",
            "    finish(\"pass\", \"nova auto-apply live probe passed\")",
            "    return",
            "  end",
            "  run_case(index, cases[index])",
            "end",
            "",
            "run_case = function(index, spec)",
            "  local case_result = {",
            "    case_id = spec.case_id,",
            "    prompt = spec.prompt,",
            "    expected_candidate = spec.expected_candidate,",
            "    expected_node = spec.expected_node,",
            "    expected_writes = spec.expected_writes,",
            "    expected_tool_trace_names = spec.expected_tool_trace_names",
            "      or default_tool_trace_names,",
            "    checks = {},",
            "  }",
            "  emerge_for_case(spec, case_result, function()",
            "    local area_minp, area_maxp = bounds(spec.pos, spec.count_radius + 2)",
            "    local held_area = forceload_area(area_minp, area_maxp)",
            "    case_result.forceloaded_block_count = #held_area",
            "    prepare_area(spec.pos, spec.count_radius)",
            "    case_result.prepared_center_node = core.get_node(spec.pos).name",
            "    if case_result.prepared_center_node == \"ignore\" then",
            "      free_forceloaded_area(held_area)",
            "      fail(case_result, \"case \" .. spec.case_id .. \" map area remained unloaded\")",
            "      return",
            "    end",
            "    local completed = false",
            "    local context = {",
            "      pos = clone_pos(spec.pos),",
            "      world_id = \"nova-auto-apply-live-probe\",",
            "      get_node = core.get_node,",
            "      set_node = core.set_node,",
            "      on_agentic_build_planner_complete = function(reply, trace)",
            "        completed = true",
            "        case_result.reply = summarize_reply(reply)",
            "        case_result.trace = summarize_trace(trace)",
            "        core.after(0.35, function()",
            "          if core.load_area then",
            "            pcall(core.load_area, area_minp, area_maxp)",
            "          end",
            "          for _ = 1, 10 do",
            "            core.step_ai_tasks()",
            "          end",
            "          local task = reply and reply.task_id and core.get_ai_task(reply.task_id) or nil",
            "          case_result.task = summarize_task(task)",
            "          local last = task and task.last_result or {}",
            "          case_result.node_count = count_node(spec.pos, spec.count_radius, spec.expected_node)",
            "          case_result.non_air_count = count_non_air(spec.pos, spec.count_radius)",
            "          case_result.center_node = core.get_node(spec.pos).name",
            "          case_result.checks.agentic_route = case_result.trace.route == \"agentic_build_planner\"",
            "          case_result.checks.reply_queued = reply and reply.ok == true",
            "            and reply.status == \"queued\"",
            "          case_result.checks.auto_applied = reply and reply.auto_applied_approval == true",
            "          case_result.checks.approved_build = reply and reply.approved_action == \"build\"",
            "          case_result.checks.selected_candidate = reply",
            "            and reply.selected_candidate_id == spec.expected_candidate",
            "          case_result.checks.kind = reply and reply.build_kind == spec.expected_kind",
            "          case_result.checks.material = reply",
            "            and reply.build_material_name == spec.expected_material",
            "          case_result.checks.node = reply and reply.build_material_node == spec.expected_node",
            "          case_result.checks.planned_writes = reply",
            "            and reply.planned_node_writes == spec.expected_writes",
            "          case_result.checks.width = spec.expected_width == nil",
            "            or (reply and reply.build_width == spec.expected_width)",
            "          case_result.checks.height = spec.expected_height == nil",
            "            or (reply and reply.build_height == spec.expected_height)",
            "          case_result.checks.required_tools = reply",
            "            and reply.adapter_required_tool_calls_satisfied == true",
            "          local tool_names = reply and reply.adapter_tool_trace_names or {}",
            "          case_result.checks.tool_trace_names =",
            "            tool_trace_contains_in_order(tool_names,",
            "              case_result.expected_tool_trace_names)",
            "          case_result.checks.action_plan_ready = reply",
            "            and reply.adapter_build_action_plan_status == \"ready\"",
            "          case_result.checks.world_mutation_authority = reply",
            "            and reply.adapter_build_action_plan_world_mutation_authority == \"luanti\"",
            "          case_result.checks.generated_option =",
            "            spec.requires_generated_option ~= true",
            "            or (reply and reply.generated_build_option_status == \"validated\"",
            "              and reply.generated_candidate_id == spec.expected_candidate)",
            "          case_result.checks.agentic_tool_success_required =",
            "            spec.requires_generated_option ~= true",
            "            or (reply and reply.agentic_tool_success_required == true)",
            "          case_result.checks.task_completed = task and task.status == \"completed\"",
            "          case_result.checks.rollback_record = last.rollback_record_id ~= nil",
            "          case_result.checks.node_count = case_result.node_count == spec.expected_writes",
            "          case_result.checks.no_extra_nodes = case_result.non_air_count == spec.expected_writes",
            "          for check, passed in pairs(case_result.checks) do",
            "            if passed ~= true then",
            "              free_forceloaded_area(held_area)",
            "              fail(case_result, \"case \" .. spec.case_id .. \" failed check \" .. check)",
            "              return",
            "            end",
            "          end",
            "          free_forceloaded_area(held_area)",
            "          case_result.status = \"pass\"",
            "          case_result.ok = true",
            "          results[#results + 1] = case_result",
            "          run_next(index + 1)",
            "        end)",
            "      end,",
            "    }",
            "    local initial = core.ai_agent_plugin.handle_command(spec.owner, spec.prompt, context)",
            "    case_result.initial_reply = summarize_reply(initial)",
            "    case_result.checks.initial_agentic_queued = initial and initial.ok == true",
            "      and initial.action == \"build_plan\" and initial.status == \"queued\"",
            "    if case_result.checks.initial_agentic_queued ~= true then",
            "      free_forceloaded_area(held_area)",
            "      fail(case_result, \"case \" .. spec.case_id ..",
            "        \" did not queue agentic build planner\")",
            "      return",
            "    end",
            "    core.after(135, function()",
            "      if not completed and not finished then",
            "        free_forceloaded_area(held_area)",
            "        fail(case_result, \"case \" .. spec.case_id ..",
            "          \" timed out waiting for live agent planner\")",
            "      end",
            "    end)",
            "  end)",
            "end",
            "",
            "core.register_on_mods_loaded(function()",
            "  if not core.ai_agent_plugin then",
            "    finish(\"fail\", \"ai_agent_plugin unavailable\")",
            "    return",
            "  end",
            "  if adapter_mode == \"agents_sdk_sidecar\" then",
            "    if not core.ai_agents_sdk_adapter_plugin then",
            "      finish(\"fail\", \"agents sdk adapter plugin unavailable\")",
            "      return",
            "    end",
            "    local config = core.ai_agents_sdk_adapter_plugin.get_config()",
            "    if config.enabled ~= true or config.has_http_api ~= true then",
            "      finish(\"fail\", \"agents sdk adapter not enabled with http api\")",
            "      return",
            "    end",
            "  else",
            "    install_mock_adapter()",
            "  end",
            "  core.ai_agent_plugin.configure({ auto_apply_build_approvals = true })",
            "  core.after(0.25, function()",
            "    run_next(1)",
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
        raise ValueError(f"nova auto-apply {field} is not {expected}")


def _case_by_id(payload: dict) -> dict[str, dict]:
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise ValueError("nova auto-apply cases are invalid")
    return {
        case.get("case_id"): case
        for case in cases
        if isinstance(case, dict) and isinstance(case.get("case_id"), str)
    }


def _tool_trace_contains_in_order(tool_names: object, expected: list[str]) -> bool:
    if not isinstance(tool_names, list):
        return False
    if not expected:
        return True
    expected_index = 0
    for name in tool_names:
        if name == expected[expected_index]:
            expected_index += 1
            if expected_index >= len(expected):
                return True
    return False


def _validate_case(
    case: dict,
    *,
    case_id: str,
    candidate: str,
    node: str,
    writes: int,
    expected_tool_trace_names: list[str] | None = None,
    width: int | None = None,
    height: int | None = None,
    generated: bool = False,
) -> None:
    if case.get("status") != "pass" or case.get("ok") is not True:
        raise ValueError(f"nova auto-apply {case_id} did not pass")
    if case.get("node_count") != writes or case.get("non_air_count") != writes:
        raise ValueError(f"nova auto-apply {case_id} wrote the wrong node count")
    if case.get("center_node") != node:
        raise ValueError(f"nova auto-apply {case_id} center node is invalid")
    checks = case.get("checks") if isinstance(case.get("checks"), dict) else {}
    for field in (
        "initial_agentic_queued",
        "agentic_route",
        "reply_queued",
        "auto_applied",
        "approved_build",
        "selected_candidate",
        "kind",
        "material",
        "node",
        "planned_writes",
        "required_tools",
        "tool_trace_names",
        "action_plan_ready",
        "world_mutation_authority",
        "task_completed",
        "rollback_record",
        "node_count",
        "no_extra_nodes",
    ):
        _require_bool(checks, field)
    initial = case.get("initial_reply") if isinstance(case.get("initial_reply"), dict) else {}
    if initial.get("action") != "build_plan" or initial.get("status") != "queued":
        raise ValueError(f"nova auto-apply {case_id} did not queue agentic planner")
    reply = case.get("reply") if isinstance(case.get("reply"), dict) else {}
    if reply.get("selected_candidate_id") != candidate:
        raise ValueError(f"nova auto-apply {case_id} selected the wrong candidate")
    if reply.get("build_material_node") != node:
        raise ValueError(f"nova auto-apply {case_id} material node is invalid")
    if reply.get("planned_node_writes") != writes:
        raise ValueError(f"nova auto-apply {case_id} planned writes are invalid")
    if width is not None and reply.get("build_width") != width:
        raise ValueError(f"nova auto-apply {case_id} width is invalid")
    if height is not None and reply.get("build_height") != height:
        raise ValueError(f"nova auto-apply {case_id} height is invalid")
    if reply.get("auto_applied_approval") is not True:
        raise ValueError(f"nova auto-apply {case_id} was not auto-applied")
    if reply.get("auto_apply_policy") != "ai_runtime.auto_apply_build_approvals":
        raise ValueError(f"nova auto-apply {case_id} policy is invalid")
    if reply.get("adapter_tool_decision_source") not in {
        "agents_sdk_function_tool",
        "agents_sdk_repair_function_tool",
    }:
        raise ValueError(f"nova auto-apply {case_id} did not use agent tool decision")
    if reply.get("adapter_required_tool_calls_satisfied") is not True:
        raise ValueError(f"nova auto-apply {case_id} required tools were not satisfied")
    expected_tools = expected_tool_trace_names or [
        "recall_build_prompt_memory",
        "select_build_option",
        "plan_build_actions",
    ]
    if not _tool_trace_contains_in_order(reply.get("adapter_tool_trace_names"), expected_tools):
        raise ValueError(f"nova auto-apply {case_id} tool trace names are invalid")
    if reply.get("adapter_build_action_plan_status") != "ready":
        raise ValueError(f"nova auto-apply {case_id} action plan was not ready")
    if reply.get("adapter_build_action_plan_world_mutation_authority") != "luanti":
        raise ValueError(f"nova auto-apply {case_id} mutation authority is invalid")
    if generated:
        _require_bool(checks, "generated_option")
        if reply.get("generated_build_option_status") != "validated":
            raise ValueError(f"nova auto-apply {case_id} generated option was not validated")
        if reply.get("generated_candidate_id") != candidate:
            raise ValueError(f"nova auto-apply {case_id} generated candidate is invalid")
    trace = case.get("trace") if isinstance(case.get("trace"), dict) else {}
    if trace.get("route") != "agentic_build_planner":
        raise ValueError(f"nova auto-apply {case_id} route is invalid")
    task = case.get("task") if isinstance(case.get("task"), dict) else {}
    last = task.get("last_result") if isinstance(task.get("last_result"), dict) else {}
    if task.get("status") != "completed":
        raise ValueError(f"nova auto-apply {case_id} task did not complete")
    if last.get("changed") != writes:
        raise ValueError(f"nova auto-apply {case_id} changed count is invalid")
    if last.get("status") != "success":
        raise ValueError(f"nova auto-apply {case_id} task result is invalid")
    if not isinstance(last.get("rollback_record_id"), str) or not last["rollback_record_id"]:
        raise ValueError(f"nova auto-apply {case_id} rollback record missing")


def validate_live_result(payload: dict, max_bytes: int = DEFAULT_MAX_BYTES) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("nova auto-apply result must be an object")
    if payload.get("live_result_kind") != "ai_native_nova_auto_apply_live_result":
        raise ValueError("nova auto-apply result kind is invalid")
    if _artifact_has_private_content(payload):
        raise ValueError("nova auto-apply result contains private content")
    runtime_context = payload.get("runtime_context")
    if not isinstance(runtime_context, dict):
        raise ValueError("nova auto-apply runtime_context missing or invalid")
    if runtime_context.get("mode") != "disposable_live_ai_runtime_nova_auto_apply_probe":
        raise ValueError("nova auto-apply runtime mode is invalid")
    if runtime_context.get("gameid") != "ai_runtime":
        raise ValueError("nova auto-apply gameid is invalid")
    if runtime_context.get("command") != "/nova":
        raise ValueError("nova auto-apply command is invalid")
    if runtime_context.get("adapter_mode") not in {"mock_async_adapter", "agents_sdk_sidecar"}:
        raise ValueError("nova auto-apply adapter mode is invalid")
    for field in ("requires_live_pi", "requires_private_world", "requires_private_assets"):
        if runtime_context.get(field) is not False:
            raise ValueError(f"nova auto-apply {field} must be false")
    if runtime_context.get("world_mutation_performed") is not True:
        raise ValueError("nova auto-apply must perform disposable world mutation")
    if runtime_context.get("world_mutation_scope") != "disposable_synthetic_ai_runtime_world":
        raise ValueError("nova auto-apply mutation scope is invalid")

    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    if summary.get("cases_total") != 5 or summary.get("cases_passed") != 5:
        raise ValueError("nova auto-apply summary case counts are invalid")
    if summary.get("cases_failed") != 0:
        raise ValueError("nova auto-apply summary has failed cases")
    for field in (
        "fire_only_strict_checked",
        "fire_simple_checked",
        "fire_me_simple_checked",
        "tnt_wall_checked",
        "generated_dimensioned_wall_checked",
        "agentic_build_planner_checked",
        "auto_apply_checked",
        "rollback_checked",
    ):
        _require_bool(summary, field)

    cases = _case_by_id(payload)
    _validate_case(
        cases.get("fire_only_strict", {}),
        case_id="fire_only_strict",
        candidate="fire",
        node="ai_runtime_base:fire",
        writes=1,
    )
    _validate_case(
        cases.get("fire_simple", {}),
        case_id="fire_simple",
        candidate="fire",
        node="ai_runtime_base:fire",
        writes=1,
    )
    _validate_case(
        cases.get("fire_me_simple", {}),
        case_id="fire_me_simple",
        candidate="fire",
        node="ai_runtime_base:fire",
        writes=1,
    )
    _validate_case(
        cases.get("tnt_wall", {}),
        case_id="tnt_wall",
        candidate="tnt_wall",
        node="ai_runtime_base:tnt",
        writes=12,
    )
    _validate_case(
        cases.get("generated_dimensioned_wall", {}),
        case_id="generated_dimensioned_wall",
        candidate="generated_dimensioned_wall",
        node="ai_runtime_base:stone",
        writes=12,
        width=6,
        height=2,
        generated=True,
        expected_tool_trace_names=[
            "recall_build_prompt_memory",
            "select_build_option",
            "propose_build_option",
            "select_build_option",
            "plan_build_actions",
        ],
    )

    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    for field in (
        "public_safe_output",
        "disposable_live_world_only",
        "world_mutation_performed",
        "no_raw_assets",
        "no_provider_prompts",
        "no_family_world_coordinates",
        "no_private_prompt_retained",
    ):
        _require_bool(safety, field)
    if safety.get("world_mutation_scope") != "disposable_synthetic_ai_runtime_world":
        raise ValueError("nova auto-apply safety mutation scope is invalid")
    if safety.get("world_mutation_authority") != "luanti":
        raise ValueError("nova auto-apply safety mutation authority is invalid")

    bounds = payload.get("bounds") if isinstance(payload.get("bounds"), dict) else {}
    output_bytes = bounds.get("output_bytes")
    declared_max = bounds.get("max_bytes", max_bytes)
    if not isinstance(output_bytes, int) or not isinstance(declared_max, int):
        raise ValueError("nova auto-apply bounds are invalid")
    if output_bytes > declared_max or output_bytes > max_bytes:
        raise ValueError("nova auto-apply output exceeds max bytes")

    return {
        "nova_auto_apply_status": "pass",
        "nova_auto_apply_output_bytes": output_bytes,
        "nova_auto_apply_cases": 5,
        "nova_auto_apply_passed": 5,
        "nova_auto_apply_fire_only_strict_checked": True,
        "nova_auto_apply_fire_only_strict_planned_node_writes": 1,
        "nova_auto_apply_fire_only_strict_changed_nodes": 1,
        "nova_auto_apply_fire_simple_checked": True,
        "nova_auto_apply_fire_simple_planned_node_writes": 1,
        "nova_auto_apply_fire_simple_changed_nodes": 1,
        "nova_auto_apply_fire_me_simple_checked": True,
        "nova_auto_apply_fire_me_simple_planned_node_writes": 1,
        "nova_auto_apply_fire_me_simple_changed_nodes": 1,
        "nova_auto_apply_tnt_wall_checked": True,
        "nova_auto_apply_tnt_wall_planned_node_writes": 12,
        "nova_auto_apply_tnt_wall_changed_nodes": 12,
        "nova_auto_apply_generated_dimensioned_wall_checked": True,
        "nova_auto_apply_generated_dimensioned_wall_planned_node_writes": 12,
        "nova_auto_apply_generated_dimensioned_wall_changed_nodes": 12,
        "nova_auto_apply_generated_dimensioned_wall_width": 6,
        "nova_auto_apply_generated_dimensioned_wall_height": 2,
        "nova_auto_apply_agentic_build_planner_checked": True,
        "nova_auto_apply_auto_apply_checked": True,
        "nova_auto_apply_rollback_checked": True,
        "nova_auto_apply_adapter_mode": runtime_context["adapter_mode"],
        "nova_auto_apply_requires_model_network":
            runtime_context.get("requires_model_network") is True,
        "nova_auto_apply_world_mutation": True,
    }


def run_probe(args) -> int:
    root = resolve_path(Path.cwd(), args.root).resolve()
    server_bin = resolve_path(root, args.server_bin)
    output = resolve_path(root, args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    world_dir = output.parent / "nova-auto-apply-live-world"
    write_probe_world(
        world_dir,
        args.generated_at,
        args.max_bytes,
        args.adapter_endpoint,
    )

    port = args.port or reserve_udp_port()
    log_path = world_dir / "debug.log"
    config_path = world_dir / "probe.conf"
    config_lines = [
        "server_name = Nova Auto Apply Live Probe",
        "name = nova_auto_apply_probe",
        "secure.enable_security = true",
        "creative_mode = true",
        "enable_damage = false",
        "server_announce = false",
        "ai_runtime.auto_apply_build_approvals = true",
    ]
    if args.adapter_endpoint:
        config_lines.extend([
            "ai_runtime.enable_agents_sdk_adapter = true",
            f"ai_runtime.agents_sdk_adapter_endpoint = {args.adapter_endpoint}",
            "ai_runtime.agents_sdk_adapter_auto_install = true",
            f"ai_runtime.agents_sdk_adapter_timeout = {int(args.adapter_timeout)}",
            "secure.http_mods = ai_runtime_agents_sdk_bridge",
        ])
    config_path.write_text("\n".join(config_lines) + "\n", encoding="utf-8")
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
        print("nova auto-apply live probe timed out", file=sys.stderr)
        return 1
    if completed.returncode != 0:
        print("nova auto-apply live server exited with non-zero status", file=sys.stderr)
        if completed.stderr.strip():
            print(completed.stderr.strip()[-1200:], file=sys.stderr)
        if log_path.is_file():
            print(log_path.read_text(encoding="utf-8", errors="replace")[-1200:], file=sys.stderr)
        return 1

    result = read_result(world_dir)
    if result.get("status") != "pass":
        reason = result.get("reason", "unknown")
        print(f"nova auto-apply live probe failed: {reason}", file=sys.stderr)
        return 1

    world_artifact = world_dir / LIVE_ARTIFACT_NAME
    if not world_artifact.is_file():
        print("nova auto-apply live artifact missing", file=sys.stderr)
        return 1
    try:
        payload = json.loads(world_artifact.read_text(encoding="utf-8"))
        validate_live_result(payload, max_bytes=args.max_bytes)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"nova auto-apply live artifact invalid: {exc}", file=sys.stderr)
        return 1
    output.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(output)
    return 0


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Run Nova auto-applied build regression coverage in a disposable ai_runtime world."
    )
    parser.add_argument("--root", default=".", help="Repository root. Default: current directory.")
    parser.add_argument(
        "--server-bin",
        default="bin/luantiserver",
        help="Luanti server binary relative to --root or absolute path.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to write the bounded live probe artifact.",
    )
    parser.add_argument(
        "--generated-at",
        required=True,
        help="UTC timestamp to embed in the live probe artifact.",
    )
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_BYTES,
        help="Maximum byte budget for retained artifact.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=160.0,
        help="Seconds to wait for the disposable server to finish.",
    )
    parser.add_argument("--port", type=int, help="Optional UDP port for the disposable server.")
    parser.add_argument(
        "--adapter-endpoint",
        help="Optional loopback Agents SDK model adapter endpoint for live OpenAI agent calls.",
    )
    parser.add_argument(
        "--adapter-timeout",
        type=float,
        default=90.0,
        help="Seconds for the Agents SDK adapter HTTP request when endpoint is set.",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    return run_probe(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
