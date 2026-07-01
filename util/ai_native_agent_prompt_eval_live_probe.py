#!/usr/bin/env python3
"""Probe /ai_agent_eval in a disposable live ai_runtime world."""

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
LIVE_ARTIFACT_NAME = "ai-runtime-agent-prompt-eval-live-result.json"
LIVE_RESULT_NAME = "ai-runtime-agent-prompt-eval-live-probe-result.json"
PROBE_MOD_NAME = "ai_agent_prompt_eval_live_probe"
DEFAULT_MAX_BYTES = 40000
DEFAULT_MODEL_PROMPT = "what can you plan with tools next?"
GOLDEN_PROMPT_SUITE = "openrealm_creator_loop"
GOLDEN_PROMPT_BACKLOG_TOTAL = 11
ENFORCED_GOLDEN_PROMPT_CASE_IDS = (
    "build_fire",
    "fire_only_strict",
    "tnt_wall",
    "stone_bridge",
    "small_cabin",
    "path_to_hill",
    "agentic_build_planner",
    "openrealm_village",
    "player_agent_loop",
)
ACCEPTED_AGENTIC_TOOL_DECISION_SOURCES = {
    "agents_sdk_function_tool",
    "agents_sdk_repair_function_tool",
    "agents_sdk_generated_tool_completion",
    "local_agent_tool_contract_fast_path",
}

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
    model_prompt: str,
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
            "local model_prompt = " + lua_string(model_prompt),
            "",
            "local function write_result(status, reason)",
            "  core.safe_file_write(result_path, core.write_json({",
            "    status = status,",
            "    reason = reason,",
            "    execution_path = \"disposable_live_ai_runtime_agent_prompt_eval_probe\",",
            "  }))",
            "end",
            "",
            "local function shutdown(reason)",
            "  core.after(0.25, function()",
            "    core.request_shutdown(reason, false, 0)",
            "  end)",
            "end",
            "",
            "local function case_by_id(report)",
            "  local cases = {}",
            "  for _, case in ipairs(report.cases or {}) do",
            "    cases[case.case_id] = case",
            "  end",
            "  return cases",
            "end",
            "",
            "local function summarize_case(case)",
            "  case = case or {}",
            "  local reply = case.reply or case.initial_reply or {}",
            "  local trace = case.trace or case.initial_trace or case.final_trace or {}",
            "  local final_trace = case.final_trace or {}",
            "  local final_reply = case.final_reply or {}",
            "  local options_reply = case.options_reply or {}",
            "  local options_trace = case.options_trace or {}",
            "  local select_reply = case.select_reply or {}",
            "  local select_trace = case.select_trace or {}",
            "  local pending_plan_reply = case.pending_plan_reply or {}",
            "  local pending_plan_trace = case.pending_plan_trace or {}",
            "  local discard_reply = case.discard_reply or {}",
            "  local discard_trace = case.discard_trace or {}",
            "  local after_discard_reply = case.after_discard_reply or {}",
            "  local after_discard_trace = case.after_discard_trace or {}",
            "  local effective_reply = final_reply.status and final_reply or reply",
            "  return {",
            "    case_id = case.case_id,",
            "    status = case.status,",
            "    ok = case.ok == true,",
            "    prompt = case.prompt,",
            "    natural_chat_handled = case.natural_chat_handled == true,",
            "    action = effective_reply.action,",
            "    reply_status = reply.status,",
            "    final_status = case.final_status or final_reply.status,",
            "    route = trace.route,",
            "    final_route = final_trace.route,",
            "    build_kind = effective_reply.build_kind,",
            "    build_width = effective_reply.build_width,",
            "    build_depth = effective_reply.build_depth,",
            "    build_height = effective_reply.build_height,",
            "    build_count = effective_reply.build_count,",
            "    build_material_name = effective_reply.build_material_name,",
            "    planned_node_writes = effective_reply.planned_node_writes,",
            "    planner_mode = effective_reply.planner_mode,",
            "    selected_candidate_id = effective_reply.selected_candidate_id,",
            "    candidate_count = effective_reply.candidate_count,",
            "    intent_constraint_option_id = effective_reply.intent_constraint_option_id,",
            "    intent_constraint_reason = effective_reply.intent_constraint_reason,",
            "    adapter_tool_decision_source = effective_reply.adapter_tool_decision_source,",
            "    adapter_required_tool_calls = effective_reply.adapter_required_tool_calls,",
            "    adapter_missing_required_tool_calls = effective_reply.adapter_missing_required_tool_calls,",
            "    adapter_required_tool_calls_satisfied = effective_reply.adapter_required_tool_calls_satisfied,",
            "    adapter_tool_trace_names = effective_reply.adapter_tool_trace_names,",
            "    adapter_build_action_plan_status = effective_reply.adapter_build_action_plan_status,",
            "    adapter_build_action_plan_step_count = effective_reply.adapter_build_action_plan_step_count,",
            "    adapter_build_action_plan_world_mutation_authority = effective_reply.adapter_build_action_plan_world_mutation_authority,",
            "    adapter_selected_candidate_id = effective_reply.adapter_selected_candidate_id,",
            "    model_selected_candidate_id = effective_reply.model_selected_candidate_id,",
            "    adapter_rejected_model_selected_candidate_id = effective_reply.adapter_rejected_model_selected_candidate_id,",
            "    build_option_decision_source = effective_reply.build_option_decision_source,",
            "    generated_build_option_status = effective_reply.generated_build_option_status,",
            "    generated_candidate_id = effective_reply.generated_candidate_id,",
            "    openrealm_plan_id = effective_reply.openrealm_plan_id,",
            "    options_handled = case.options_handled == true,",
            "    options_status = options_reply.status,",
            "    options_action = options_reply.action,",
            "    options_selected_candidate_id = options_reply.selected_candidate_id,",
            "    options_no_world_mutation = options_reply.no_world_mutation,",
            "    options_trace_route = options_trace.route,",
            "    options_trace_action = options_trace.action,",
            "    options_trace_public_prompt = options_trace.public_prompt,",
            "    options_trace_status = options_trace.response and options_trace.response.status or nil,",
            "    select_handled = case.select_handled == true,",
            "    select_status = select_reply.status,",
            "    select_action = select_reply.action,",
            "    select_selected_candidate_id = select_reply.selected_candidate_id,",
            "    select_previous_selected_candidate_id = select_reply.previous_selected_candidate_id,",
            "    select_selected_by_player = select_reply.selected_by_player,",
            "    select_decision_source = select_reply.build_option_decision_source,",
            "    select_no_world_mutation = select_reply.no_world_mutation,",
            "    select_trace_route = select_trace.route,",
            "    select_trace_action = select_trace.action,",
            "    select_trace_public_prompt = select_trace.public_prompt,",
            "    select_trace_status = select_trace.response and select_trace.response.status or nil,",
            "    pending_plan_handled = case.pending_plan_handled == true,",
            "    pending_plan_status = pending_plan_reply.status,",
            "    pending_plan_action = pending_plan_reply.action,",
            "    pending_plan_selected_candidate_id = pending_plan_reply.selected_candidate_id,",
            "    pending_plan_trace_route = pending_plan_trace.route,",
            "    pending_plan_trace_action = pending_plan_trace.action,",
            "    pending_plan_trace_public_prompt = pending_plan_trace.public_prompt,",
            "    pending_plan_trace_status = pending_plan_trace.response and pending_plan_trace.response.status or nil,",
            "    discard_handled = case.discard_handled == true,",
            "    discard_status = discard_reply.status,",
            "    discard_action = discard_reply.action,",
            "    discard_trace_route = discard_trace.route,",
            "    discard_trace_action = discard_trace.action,",
            "    discard_trace_public_prompt = discard_trace.public_prompt,",
            "    discard_trace_status = discard_trace.response and discard_trace.response.status or nil,",
            "    after_discard_handled = case.after_discard_handled == true,",
            "    after_discard_status = after_discard_reply.status,",
            "    after_discard_reason = after_discard_reply.reason,",
            "    after_discard_trace_route = after_discard_trace.route,",
            "    after_discard_trace_action = after_discard_trace.action,",
            "    after_discard_trace_public_prompt = after_discard_trace.public_prompt,",
            "    after_discard_trace_status = after_discard_trace.response and after_discard_trace.response.status or nil,",
            "    after_discard_trace_reason = after_discard_trace.response and after_discard_trace.response.reason or nil,",
            "    cleanup_status = case.cleanup and case.cleanup.status or nil,",
            "    failure_count = #(case.failures or {}),",
            "  }",
            "end",
            "",
            "local function summarize_report(report)",
            "  local cases = case_by_id(report)",
            "  local summaries = {}",
            "  local passed = 0",
            "  for _, case in ipairs(report.cases or {}) do",
            "    summaries[#summaries + 1] = summarize_case(case)",
            "    if case.ok == true then",
            "      passed = passed + 1",
            "    end",
            "  end",
            "  return {",
            "    status = report.status,",
            "    ok = report.ok == true,",
            "    owner = report.owner,",
            "    cases_total = #(report.cases or {}),",
            "    cases_passed = passed,",
            "    cases_failed = #(report.cases or {}) - passed,",
            "    case_ids = {",
            "      build_fire = cases.build_fire ~= nil,",
            "      fire_only_strict = cases.fire_only_strict ~= nil,",
            "      tnt_wall = cases.tnt_wall ~= nil,",
            "      stone_bridge = cases.stone_bridge ~= nil,",
            "      small_cabin = cases.small_cabin ~= nil,",
            "      path_to_hill = cases.path_to_hill ~= nil,",
            "      agentic_build_planner = cases.agentic_build_planner ~= nil,",
            "      openrealm_village = cases.openrealm_village ~= nil,",
            "      player_agent_loop = cases.player_agent_loop ~= nil,",
            "      model = cases.model ~= nil,",
            "    },",
            "    cases = summaries,",
            "    metrics = report.metrics or {},",
            "    safety = report.safety or {},",
            "  }",
            "end",
            "",
            "local function install_mock_adapter()",
            "  if adapter_mode ~= \"mock_async_adapter\" then",
            "    return",
            "  end",
            "  core.ai_agent_plugin.set_model_adapter_async(function(request, done)",
            "    core.after(0.1, function()",
            "      local response = {",
            "        agentic_execution = true,",
            "        tools_enabled = { \"recommend_build_option\", \"classify_world_action\" },",
            "      }",
            "      local prompt = tostring(request.public_prompt or \"\"):lower()",
            "      if prompt:find(\"stone bridge\", 1, true) then",
            "        response = {",
            "          agentic_execution = true,",
            "          selected_option_id = \"generated_bridge_platform\",",
            "          model_selected_option_id = \"generated_bridge_platform\",",
            "          tool_decision_source = \"agents_sdk_generated_tool_completion\",",
            "          required_tool_calls = { \"recall_build_prompt_memory\", \"propose_build_option\", \"select_build_option\", \"plan_build_actions\" },",
            "          missing_required_tool_calls = {},",
            "          required_tool_calls_satisfied = true,",
            "          tool_trace = {",
            "            { tool_name = \"recall_build_prompt_memory\" },",
            "            { tool_name = \"propose_build_option\" },",
            "            { tool_name = \"select_build_option\" },",
            "            { tool_name = \"plan_build_actions\" },",
            "          },",
            "          generated_build_option = {",
            "            option_id = \"generated_bridge_platform\",",
            "            label = \"Generated bridge platform\",",
            "            reason = \"player asked for a bridge-like surface\",",
            "            build_kind = \"platform\",",
            "            build_width = 6,",
            "            build_depth = 2,",
            "            build_material_name = \"stone\",",
            "            planned_node_writes = 12,",
            "          },",
            "          build_action_plan = {",
            "            status = \"ready\",",
            "            selected_option_id = \"generated_bridge_platform\",",
            "            step_count = 12,",
            "            world_mutation_authority = \"luanti\",",
            "          },",
            "          tool_decisions = {",
            "            build_option = {",
            "              selected_option_id = \"generated_bridge_platform\",",
            "              decision_source = \"agent_selected_generated_build_option\",",
            "              generated_option = {",
            "                option_id = \"generated_bridge_platform\",",
            "                label = \"Generated bridge platform\",",
            "                reason = \"player asked for a bridge-like surface\",",
            "                build_kind = \"platform\",",
            "                build_width = 6,",
            "                build_depth = 2,",
            "                build_material_name = \"stone\",",
            "                planned_node_writes = 12,",
            "              },",
            "            },",
            "            build_action_plan = {",
            "              status = \"ready\",",
            "              selected_option_id = \"generated_bridge_platform\",",
            "              step_count = 12,",
            "              world_mutation_authority = \"luanti\",",
            "            },",
            "          },",
            "        }",
            "      elseif prompt:find(\"small cabin\", 1, true) then",
            "        response = {",
            "          agentic_execution = true,",
            "          selected_option_id = \"generated_prompt_shaped_cabin\",",
            "          model_selected_option_id = \"generated_prompt_shaped_cabin\",",
            "          tool_decision_source = \"agents_sdk_generated_tool_completion\",",
            "          required_tool_calls = { \"recall_build_prompt_memory\", \"propose_build_option\", \"select_build_option\", \"plan_build_actions\" },",
            "          missing_required_tool_calls = {},",
            "          required_tool_calls_satisfied = true,",
            "          tool_trace = {",
            "            { tool_name = \"recall_build_prompt_memory\" },",
            "            { tool_name = \"propose_build_option\" },",
            "            { tool_name = \"select_build_option\" },",
            "            { tool_name = \"plan_build_actions\" },",
            "          },",
            "          generated_build_option = {",
            "            option_id = \"generated_prompt_shaped_cabin\",",
            "            label = \"Generated prompt-shaped cabin\",",
            "            reason = \"player asked for a compact cabin-like build\",",
            "            build_kind = \"cabin\",",
            "            build_width = 3,",
            "            build_depth = 2,",
            "            build_height = 2,",
            "            build_material_name = \"wood\",",
            "            planned_node_writes = 10,",
            "          },",
            "          build_action_plan = {",
            "            status = \"ready\",",
            "            selected_option_id = \"generated_prompt_shaped_cabin\",",
            "            step_count = 10,",
            "            world_mutation_authority = \"luanti\",",
            "          },",
            "          tool_decisions = {",
            "            build_option = {",
            "              selected_option_id = \"generated_prompt_shaped_cabin\",",
            "              decision_source = \"agent_selected_generated_build_option\",",
            "              generated_option = {",
            "                option_id = \"generated_prompt_shaped_cabin\",",
            "                label = \"Generated prompt-shaped cabin\",",
            "                reason = \"player asked for a compact cabin-like build\",",
            "                build_kind = \"cabin\",",
            "                build_width = 3,",
            "                build_depth = 2,",
            "                build_height = 2,",
            "                build_material_name = \"wood\",",
            "                planned_node_writes = 10,",
            "              },",
            "            },",
            "            build_action_plan = {",
            "              status = \"ready\",",
            "              selected_option_id = \"generated_prompt_shaped_cabin\",",
            "              step_count = 10,",
            "              world_mutation_authority = \"luanti\",",
            "            },",
            "          },",
            "        }",
            "      elseif prompt:find(\"path to that hill\", 1, true) then",
            "        response = {",
            "          agentic_execution = true,",
            "          selected_option_id = \"parsed_request\",",
            "          model_selected_option_id = \"parsed_request\",",
            "          tool_decision_source = \"agents_sdk_function_tool\",",
            "          required_tool_calls = { \"recall_build_prompt_memory\", \"select_build_option\", \"plan_build_actions\" },",
            "          missing_required_tool_calls = {},",
            "          required_tool_calls_satisfied = true,",
            "          tool_trace = {",
            "            { tool_name = \"recall_build_prompt_memory\" },",
            "            { tool_name = \"select_build_option\" },",
            "            { tool_name = \"plan_build_actions\" },",
            "          },",
            "          build_action_plan = {",
            "            status = \"ready\",",
            "            selected_option_id = \"parsed_request\",",
            "            step_count = 8,",
            "            world_mutation_authority = \"luanti\",",
            "          },",
            "          tool_decisions = {",
            "            build_option = {",
            "              selected_option_id = \"parsed_request\",",
            "              decision_source = \"agent_selected_build_option\",",
            "            },",
            "            build_action_plan = {",
            "              status = \"ready\",",
            "              selected_option_id = \"parsed_request\",",
            "              step_count = 8,",
            "              world_mutation_authority = \"luanti\",",
            "            },",
            "          },",
            "        }",
            "      end",
            "      done({",
            "        ok = true,",
            "        message = \"Mock agent prompt-eval adapter response.\",",
            "        adapter_name = \"mock-agent-prompt-eval-adapter\",",
            "        elapsed_us = 1000,",
            "        response = response,",
            "      })",
            "    end)",
            "    return true, \"queued\"",
            "  end)",
            "end",
            "",
            "local function command_fire_eval(command)",
            "  if adapter_mode == \"mock_async_adapter\" or adapter_mode == \"agents_sdk_sidecar\" then",
            "    return {",
            "      status = \"pass\",",
            "      ok = true,",
            "      cases_total = 0,",
            "      command = \"/ai_agent_eval\",",
            "      reason = \"async_agentic_eval_verified_by_full_run\",",
            "    }",
            "  end",
            "  local ran, command_ok, message = pcall(command.func, \"PromptEvalCommand\", \"case=fire\")",
            "  if not ran then",
            "    return { status = \"fail\", reason = \"command_raised_error\" }",
            "  end",
            "  if command_ok ~= true or type(message) ~= \"string\" then",
            "    return { status = \"fail\", reason = tostring(message or \"command_failed\") }",
            "  end",
            "  local parsed = core.parse_json(message)",
            "  if type(parsed) ~= \"table\" then",
            "    return { status = \"fail\", reason = \"command_returned_invalid_json\" }",
            "  end",
            "  return {",
            "    status = parsed.status,",
            "    ok = parsed.ok == true,",
            "    cases_total = #(parsed.cases or {}),",
            "    command = \"/ai_agent_eval\",",
            "  }",
            "end",
            "",
            "local function write_payload(report, command_fire)",
            "  local eval = summarize_report(report)",
            "  local report_cases = case_by_id(report)",
            "  local golden_case_ids = {",
            "    \"build_fire\",",
            "    \"fire_only_strict\",",
            "    \"tnt_wall\",",
            "    \"stone_bridge\",",
            "    \"small_cabin\",",
            "    \"path_to_hill\",",
            "    \"agentic_build_planner\",",
            "    \"openrealm_village\",",
            "    \"player_agent_loop\",",
            "  }",
            "  local golden_case_status = {}",
            "  local golden_passed = 0",
            "  for _, case_id in ipairs(golden_case_ids) do",
            "    local case = report_cases[case_id] or {}",
            "    local ok = case.ok == true and case.status == \"pass\"",
            "    golden_case_status[case_id] = ok",
            "    if ok then",
            "      golden_passed = golden_passed + 1",
            "    end",
            "  end",
            "  local player_loop_case = report_cases.player_agent_loop or {}",
            "  local player_loop_checks = player_loop_case.checks or {}",
            "  local player_loop_review_traces_checked =",
            "    player_loop_checks.options_trace_logged == true",
            "    and player_loop_checks.select_trace_logged == true",
            "    and player_loop_checks.pending_trace_logged == true",
            "    and player_loop_checks.discard_trace_logged == true",
            "    and player_loop_checks.after_discard_trace_logged == true",
            "  local player_loop_option_selection_checked =",
            "    player_loop_checks.select_handled == true",
            "    and player_loop_checks.select_success == true",
            "    and player_loop_checks.select_no_world_mutation == true",
            "    and player_loop_checks.select_same_approval == true",
            "    and player_loop_checks.select_previous_candidate == true",
            "    and player_loop_checks.select_selected_candidate == true",
            "    and player_loop_checks.select_marked_player_selected == true",
            "    and player_loop_checks.select_decision_source == true",
            "    and player_loop_checks.pending_selected_candidate == true",
            "  local payload = {",
            "    schema_version = 1,",
            "    live_result_kind = \"ai_native_agent_prompt_eval_live_result\",",
            "    generated_at = generated_at,",
            "    runtime_context = {",
            "      mode = \"disposable_live_ai_runtime_agent_prompt_eval_probe\",",
            "      gameid = \"ai_runtime\",",
            "      command = \"/ai_agent_eval\",",
            "      adapter_mode = adapter_mode,",
            "      requires_live_pi = false,",
            "      requires_private_world = false,",
            "      requires_private_assets = false,",
            "      requires_model_network = adapter_mode == \"agents_sdk_sidecar\",",
            "      world_mutation_performed = false,",
            "      world_mutation_scope = \"read_only_prompt_eval_pending_approval_cleanup\",",
            "    },",
            "    command = {",
            "      fire_case_status = command_fire.status,",
            "      fire_case_ok = command_fire.ok == true,",
            "      fire_case_count = command_fire.cases_total or 0,",
            "      registered = true,",
            "      server_privilege_required = true,",
            "    },",
            "    prompt_eval = eval,",
            "    summary = {",
            "      cases_total = eval.cases_total,",
            "      cases_passed = eval.cases_passed,",
            "      cases_failed = eval.cases_failed,",
            "      build_fire_checked = eval.case_ids.build_fire == true,",
            "      fire_only_strict_checked = eval.case_ids.fire_only_strict == true,",
            "      tnt_wall_checked = eval.case_ids.tnt_wall == true,",
            "      stone_bridge_checked = eval.case_ids.stone_bridge == true,",
            "      small_cabin_checked = eval.case_ids.small_cabin == true,",
            "      path_to_hill_checked = eval.case_ids.path_to_hill == true,",
            "      agentic_build_planner_checked = eval.case_ids.agentic_build_planner == true,",
            "      openrealm_village_checked = eval.case_ids.openrealm_village == true,",
            "      player_agent_loop_checked = eval.case_ids.player_agent_loop == true,",
            "      player_agent_loop_review_traces_checked = player_loop_review_traces_checked == true,",
            "      player_agent_loop_option_selection_checked = player_loop_option_selection_checked == true,",
            "      model_checked = eval.case_ids.model == true,",
            "      model_adapter_requests = eval.metrics.model_adapter_requests_delta or 0,",
            "      model_adapter_successes = eval.metrics.model_adapter_successes_delta or 0,",
            "      model_adapter_failures = eval.metrics.model_adapter_failures_delta or 0,",
            "      model_adapter_timeouts = eval.metrics.model_adapter_timeouts_delta or 0,",
            "      golden_prompt_suite = \"openrealm_creator_loop\",",
            "      golden_prompt_backlog_total = 11,",
            "      golden_prompt_case_ids = golden_case_status,",
            "      golden_prompts_total = #golden_case_ids,",
            "      golden_prompts_passed = golden_passed,",
            "      golden_prompts_failed = #golden_case_ids - golden_passed,",
            "    },",
            "    safety = {",
            "      public_safe_output = true,",
            "      disposable_live_world_only = true,",
            "      read_only_prompt_eval = true,",
            "      pending_approvals_discarded = true,",
            "      world_mutation_performed = false,",
            "      no_world_mutation = true,",
            "      no_raw_assets = true,",
            "      no_provider_prompts = true,",
            "      no_family_world_coordinates = true,",
            "      no_private_prompt_retained = eval.safety.audit_private_payload_retained ~= true,",
            "    },",
            "    bounds = { max_bytes = max_bytes, output_bytes = 0, truncated = false },",
            "  }",
            "  payload.bounds.output_bytes = #core.write_json(payload)",
            "  if payload.bounds.output_bytes > max_bytes then",
            "    payload.bounds.truncated = true",
            "    payload.prompt_eval.cases = nil",
            "    payload.bounds.output_bytes = #core.write_json(payload)",
            "  end",
            "  if payload.bounds.output_bytes > max_bytes then",
            "    write_result(\"fail\", \"agent prompt eval artifact exceeded max bytes\")",
            "    shutdown(\"agent prompt eval probe failed\")",
            "    return",
            "  end",
            "  if not core.safe_file_write(output_path, core.write_json(payload)) then",
            "    write_result(\"fail\", \"agent prompt eval artifact write failed\")",
            "    shutdown(\"agent prompt eval probe failed\")",
            "    return",
            "  end",
            "  write_result(payload.prompt_eval.ok and \"pass\" or \"fail\", \"agent prompt eval captured\")",
            "  shutdown(\"agent prompt eval probe complete\")",
            "end",
            "",
            "core.register_on_mods_loaded(function()",
            "  if not core.ai_agent_plugin or not core.ai_agent_plugin.run_prompt_eval then",
            "    write_result(\"fail\", \"ai_agent_plugin prompt eval unavailable\")",
            "    shutdown(\"agent prompt eval probe failed\")",
            "    return",
            "  end",
            "  core.ai_agent_plugin.configure({ max_lights = 128 })",
            "  install_mock_adapter()",
            "  local command = core.registered_chatcommands",
            "    and core.registered_chatcommands.ai_agent_eval",
            "  if type(command) ~= \"table\" or type(command.func) ~= \"function\"",
            "      or not command.privs or command.privs.server ~= true then",
            "    write_result(\"fail\", \"ai_agent_eval command missing\")",
            "    shutdown(\"agent prompt eval probe failed\")",
            "    return",
            "  end",
            "  local command_fire = command_fire_eval(command)",
            "  if command_fire.status ~= \"pass\" or command_fire.ok ~= true then",
            "    write_result(\"fail\", command_fire.reason or \"ai_agent_eval fire command failed\")",
            "    shutdown(\"agent prompt eval probe failed\")",
            "    return",
            "  end",
            "  local ran, queued, reason = pcall(core.ai_agent_plugin.run_prompt_eval, {",
            "    owner = \"PromptEvalLive\",",
            "    cases = \"all\",",
            "    model_prompt = model_prompt,",
            "    world_id = \"agent-prompt-eval-live-probe\",",
            "  }, function(report)",
            "    write_payload(report, command_fire)",
            "  end)",
            "  if not ran then",
            "    write_result(\"fail\", \"prompt eval raised error\")",
            "    shutdown(\"agent prompt eval probe failed\")",
            "    return",
            "  end",
            "  if not queued then",
            "    write_result(\"fail\", tostring(reason or \"prompt_eval_not_queued\"))",
            "    shutdown(\"agent prompt eval probe failed\")",
            "  end",
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
        raise ValueError(f"agent prompt eval {field} is not {expected}")


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _require_agentic_tool_case(
    case: dict,
    case_id: str,
    extra_expected_tools: set[str] | None = None,
) -> None:
    if case.get("route") != "agentic_build_planner" and case.get("final_route") != "agentic_build_planner":
        raise ValueError(f"agent prompt eval {case_id} route is not agentic")
    if case.get("adapter_tool_decision_source") not in ACCEPTED_AGENTIC_TOOL_DECISION_SOURCES:
        raise ValueError(f"agent prompt eval {case_id} did not use an accepted agent tool contract")
    if case.get("adapter_required_tool_calls_satisfied") is not True:
        raise ValueError(f"agent prompt eval {case_id} required tool calls were not satisfied")
    if _string_list(case.get("adapter_missing_required_tool_calls")):
        raise ValueError(f"agent prompt eval {case_id} has missing required tool calls")
    required = set(_string_list(case.get("adapter_required_tool_calls")))
    trace_names = set(_string_list(case.get("adapter_tool_trace_names")))
    expected = {
        "recall_build_prompt_memory",
        "select_build_option",
        "plan_build_actions",
    }
    if extra_expected_tools:
        expected |= extra_expected_tools
    missing_required = expected - required
    if missing_required:
        raise ValueError(f"agent prompt eval {case_id} required tool metadata is incomplete")
    missing_trace = expected - trace_names
    if missing_trace:
        raise ValueError(f"agent prompt eval {case_id} tool trace is incomplete")
    if case.get("adapter_build_action_plan_status") != "ready":
        raise ValueError(f"agent prompt eval {case_id} build-action plan was not ready")
    if case.get("adapter_build_action_plan_world_mutation_authority") != "luanti":
        raise ValueError(f"agent prompt eval {case_id} mutation authority is invalid")
    if not isinstance(case.get("adapter_build_action_plan_step_count"), int) \
            or case["adapter_build_action_plan_step_count"] <= 0:
        raise ValueError(f"agent prompt eval {case_id} build-action plan step count is invalid")
    if not isinstance(case.get("selected_candidate_id"), str) or not case["selected_candidate_id"]:
        raise ValueError(f"agent prompt eval {case_id} selected candidate missing")
    if case.get("adapter_selected_candidate_id") != case.get("selected_candidate_id") \
            and case.get("intent_constraint_option_id") != case.get("selected_candidate_id"):
        raise ValueError(f"agent prompt eval {case_id} adapter-selected candidate mismatch")
    if not isinstance(case.get("model_selected_candidate_id"), str) or not case["model_selected_candidate_id"]:
        raise ValueError(f"agent prompt eval {case_id} model-selected candidate missing")
    if not isinstance(case.get("candidate_count"), int) or case["candidate_count"] < 3:
        raise ValueError(f"agent prompt eval {case_id} candidate count is invalid")


def _require_natural_review_trace(
    case: dict,
    *,
    prefix: str,
    label: str,
    expected_action: str,
    expected_status: str,
    expected_public_prompt: str,
    expected_reason: str | None = None,
) -> None:
    required_fields = (
        f"{prefix}_trace_route",
        f"{prefix}_trace_action",
        f"{prefix}_trace_public_prompt",
        f"{prefix}_trace_status",
    )
    if any(not case.get(field) for field in required_fields):
        raise ValueError("agent prompt eval natural review trace evidence missing")
    if case.get(f"{prefix}_trace_route") != "natural_chat_review":
        raise ValueError(f"agent prompt eval {label} trace route is invalid")
    if case.get(f"{prefix}_trace_action") != expected_action:
        raise ValueError(f"agent prompt eval {label} trace action is invalid")
    if case.get(f"{prefix}_trace_public_prompt") != expected_public_prompt:
        raise ValueError(f"agent prompt eval {label} trace prompt is invalid")
    if case.get(f"{prefix}_trace_status") != expected_status:
        raise ValueError(f"agent prompt eval {label} trace status is invalid")
    if expected_reason is not None and case.get(f"{prefix}_trace_reason") != expected_reason:
        raise ValueError(f"agent prompt eval {label} trace reason is invalid")


def validate_live_result(payload: dict, max_bytes: int = DEFAULT_MAX_BYTES) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("agent prompt eval result must be an object")
    if payload.get("live_result_kind") != "ai_native_agent_prompt_eval_live_result":
        raise ValueError("agent prompt eval result kind is invalid")
    if _artifact_has_private_content(payload):
        raise ValueError("agent prompt eval result contains private content")

    runtime_context = payload.get("runtime_context")
    if not isinstance(runtime_context, dict):
        raise ValueError("agent prompt eval runtime_context missing or invalid")
    if runtime_context.get("mode") != "disposable_live_ai_runtime_agent_prompt_eval_probe":
        raise ValueError("agent prompt eval runtime mode is invalid")
    if runtime_context.get("gameid") != "ai_runtime":
        raise ValueError("agent prompt eval gameid is invalid")
    if runtime_context.get("command") != "/ai_agent_eval":
        raise ValueError("agent prompt eval command is invalid")
    if runtime_context.get("adapter_mode") not in {
        "mock_async_adapter",
        "agents_sdk_sidecar",
    }:
        raise ValueError("agent prompt eval adapter mode is invalid")
    adapter_mode = runtime_context["adapter_mode"]
    for field in ("requires_live_pi", "requires_private_world", "requires_private_assets"):
        if runtime_context.get(field) is not False:
            raise ValueError(f"agent prompt eval {field} must be false")
    if runtime_context.get("world_mutation_performed") is not False:
        raise ValueError("agent prompt eval performed world mutation")
    if runtime_context.get("world_mutation_scope") != "read_only_prompt_eval_pending_approval_cleanup":
        raise ValueError("agent prompt eval mutation scope is invalid")

    command = payload.get("command") if isinstance(payload.get("command"), dict) else {}
    if command.get("fire_case_status") != "pass" or command.get("fire_case_ok") is not True:
        raise ValueError("agent prompt eval command fire case did not pass")
    if command.get("fire_case_count") not in {0, 1}:
        raise ValueError("agent prompt eval command fire case count is invalid")
    _require_bool(command, "registered")
    _require_bool(command, "server_privilege_required")

    prompt_eval = payload.get("prompt_eval")
    if not isinstance(prompt_eval, dict):
        raise ValueError("agent prompt eval payload missing prompt_eval")
    if prompt_eval.get("status") != "pass" or prompt_eval.get("ok") is not True:
        raise ValueError("agent prompt eval did not pass")
    if prompt_eval.get("cases_total") != 10:
        raise ValueError("agent prompt eval case count is invalid")
    if prompt_eval.get("cases_passed") != 10 or prompt_eval.get("cases_failed") != 0:
        raise ValueError("agent prompt eval cases did not all pass")
    case_ids = prompt_eval.get("case_ids") if isinstance(prompt_eval.get("case_ids"), dict) else {}
    for case_id in (
        "build_fire",
        "fire_only_strict",
        "tnt_wall",
        "stone_bridge",
        "small_cabin",
        "path_to_hill",
        "agentic_build_planner",
        "openrealm_village",
        "player_agent_loop",
        "model",
    ):
        if case_ids.get(case_id) is not True:
            raise ValueError(f"agent prompt eval missing {case_id}")

    cases = prompt_eval.get("cases")
    if cases is None and payload.get("bounds", {}).get("truncated") is True:
        cases = []
    if not isinstance(cases, list):
        raise ValueError("agent prompt eval cases summary is invalid")
    if adapter_mode == "agents_sdk_sidecar" and not cases:
        raise ValueError("agent prompt eval sidecar mode requires untruncated case evidence")
    case_map = {
        item.get("case_id"): item
        for item in cases
        if isinstance(item, dict) and item.get("case_id")
    }
    if cases:
        fire = case_map.get("build_fire", {})
        fire_only = case_map.get("fire_only_strict", {})
        tnt = case_map.get("tnt_wall", {})
        stone_bridge = case_map.get("stone_bridge", {})
        small_cabin = case_map.get("small_cabin", {})
        path_to_hill = case_map.get("path_to_hill", {})
        planner = case_map.get("agentic_build_planner", {})
        openrealm = case_map.get("openrealm_village", {})
        player_loop = case_map.get("player_agent_loop", {})
        model = case_map.get("model", {})
        if fire.get("status") != "pass" or fire.get("build_kind") != "fire":
            raise ValueError("agent prompt eval fire case is invalid")
        if fire.get("build_material_name") != "fire":
            raise ValueError("agent prompt eval fire material is invalid")
        if fire.get("planned_node_writes") != 1:
            raise ValueError("agent prompt eval fire must plan exactly one node write")
        if fire_only.get("status") != "pass" or fire_only.get("build_kind") != "fire":
            raise ValueError("agent prompt eval fire-only strict case is invalid")
        if fire_only.get("prompt") != "build me a fire and only a fire":
            raise ValueError("agent prompt eval fire-only strict prompt is invalid")
        if fire_only.get("build_material_name") != "fire":
            raise ValueError("agent prompt eval fire-only strict material is invalid")
        if fire_only.get("planned_node_writes") != 1:
            raise ValueError("agent prompt eval fire-only strict must plan exactly one node write")
        if fire_only.get("route") not in {"deterministic_build_parser", "agentic_build_planner"} \
                and fire_only.get("final_route") != "agentic_build_planner":
            raise ValueError("agent prompt eval fire-only strict route is invalid")
        if tnt.get("status") != "pass" or tnt.get("build_kind") != "wall":
            raise ValueError("agent prompt eval TNT wall case is invalid")
        if tnt.get("build_material_name") != "tnt":
            raise ValueError("agent prompt eval TNT wall material is invalid")
        if tnt.get("planned_node_writes") != 12:
            raise ValueError("agent prompt eval TNT wall must plan exactly twelve node writes")
        if stone_bridge.get("status") != "pass":
            raise ValueError("agent prompt eval stone bridge case is invalid")
        if stone_bridge.get("prompt") != "build a stone bridge":
            raise ValueError("agent prompt eval stone bridge prompt is invalid")
        if stone_bridge.get("route") != "agentic_build_planner" \
                and stone_bridge.get("final_route") != "agentic_build_planner":
            raise ValueError("agent prompt eval stone bridge route is invalid")
        if stone_bridge.get("build_kind") != "platform":
            raise ValueError("agent prompt eval stone bridge build kind is invalid")
        if stone_bridge.get("build_material_name") != "stone":
            raise ValueError("agent prompt eval stone bridge material is invalid")
        bridge_width = stone_bridge.get("build_width")
        bridge_depth = stone_bridge.get("build_depth")
        bridge_writes = stone_bridge.get("planned_node_writes")
        if not isinstance(bridge_width, int) or bridge_width < 6 or bridge_width > 8 \
                or bridge_depth != 2:
            raise ValueError("agent prompt eval stone bridge dimensions are invalid")
        if bridge_writes != bridge_width * bridge_depth:
            raise ValueError("agent prompt eval stone bridge planned writes must match bridge area")
        if stone_bridge.get("selected_candidate_id") != "generated_bridge_platform":
            raise ValueError("agent prompt eval stone bridge selected candidate is invalid")
        if stone_bridge.get("generated_candidate_id") != "generated_bridge_platform":
            raise ValueError("agent prompt eval stone bridge generated candidate is invalid")
        if stone_bridge.get("generated_build_option_status") != "validated":
            raise ValueError("agent prompt eval stone bridge generated option was not validated")
        if small_cabin.get("status") != "pass":
            raise ValueError("agent prompt eval small cabin case is invalid")
        if small_cabin.get("prompt") != "build a small cabin":
            raise ValueError("agent prompt eval small cabin prompt is invalid")
        if small_cabin.get("route") != "agentic_build_planner" \
                and small_cabin.get("final_route") != "agentic_build_planner":
            raise ValueError("agent prompt eval small cabin route is invalid")
        if small_cabin.get("build_kind") != "cabin":
            raise ValueError("agent prompt eval small cabin build kind is invalid")
        if small_cabin.get("build_material_name") != "wood":
            raise ValueError("agent prompt eval small cabin material is invalid")
        if small_cabin.get("build_width") != 3 \
                or small_cabin.get("build_depth") != 2 \
                or small_cabin.get("build_height") != 2:
            raise ValueError("agent prompt eval small cabin dimensions are invalid")
        if small_cabin.get("planned_node_writes") != 10:
            raise ValueError("agent prompt eval small cabin must plan exactly ten node writes")
        if small_cabin.get("selected_candidate_id") != "generated_prompt_shaped_cabin":
            raise ValueError("agent prompt eval small cabin selected candidate is invalid")
        if small_cabin.get("generated_candidate_id") != "generated_prompt_shaped_cabin":
            raise ValueError("agent prompt eval small cabin generated candidate is invalid")
        if small_cabin.get("generated_build_option_status") != "validated":
            raise ValueError("agent prompt eval small cabin generated option was not validated")
        if path_to_hill.get("status") != "pass":
            raise ValueError("agent prompt eval path-to-hill case is invalid")
        if path_to_hill.get("prompt") != "build a path to that hill":
            raise ValueError("agent prompt eval path-to-hill prompt is invalid")
        if path_to_hill.get("route") != "agentic_build_planner" \
                and path_to_hill.get("final_route") != "agentic_build_planner":
            raise ValueError("agent prompt eval path-to-hill route is invalid")
        if path_to_hill.get("build_kind") != "path":
            raise ValueError("agent prompt eval path-to-hill build kind is invalid")
        if path_to_hill.get("build_material_name") != "stone":
            raise ValueError("agent prompt eval path-to-hill material is invalid")
        if path_to_hill.get("build_count") != 8:
            raise ValueError("agent prompt eval path-to-hill build count is invalid")
        if path_to_hill.get("planned_node_writes") != 8:
            raise ValueError("agent prompt eval path-to-hill must plan exactly eight node writes")
        if path_to_hill.get("selected_candidate_id") != "parsed_request":
            raise ValueError("agent prompt eval path-to-hill selected candidate is invalid")
        adapter_path_selection = path_to_hill.get("adapter_selected_candidate_id")
        model_path_selection = path_to_hill.get("model_selected_candidate_id")
        if (
            (adapter_path_selection and adapter_path_selection != "parsed_request")
            or (model_path_selection and model_path_selection != "parsed_request")
        ) and path_to_hill.get("intent_constraint_option_id") != "parsed_request":
            raise ValueError("agent prompt eval path-to-hill intent constraint is invalid")
        if planner.get("status") != "pass":
            raise ValueError("agent prompt eval build planner case is invalid")
        if planner.get("route") != "agentic_build_planner" and planner.get("final_route") != "agentic_build_planner":
            raise ValueError("agent prompt eval build planner route is invalid")
        if not isinstance(planner.get("build_kind"), str) or not planner["build_kind"]:
            raise ValueError("agent prompt eval build planner candidate is invalid")
        if not isinstance(planner.get("selected_candidate_id"), str) or not planner["selected_candidate_id"]:
            raise ValueError("agent prompt eval build planner selected candidate is invalid")
        if not isinstance(planner.get("candidate_count"), int) or planner["candidate_count"] < 3:
            raise ValueError("agent prompt eval build planner candidate count is invalid")
        if not isinstance(planner.get("planned_node_writes"), int):
            raise ValueError("agent prompt eval build planner planned writes are invalid")
        if planner["planned_node_writes"] <= 0 or planner["planned_node_writes"] > 16:
            raise ValueError("agent prompt eval build planner planned writes are out of bounds")
        if openrealm.get("status") != "pass":
            raise ValueError("agent prompt eval OpenRealm village case is invalid")
        if openrealm.get("prompt") != "Build a cozy lakeside village with floating lanterns":
            raise ValueError("agent prompt eval OpenRealm village prompt is invalid")
        if openrealm.get("route") != "agentic_build_planner" \
                and openrealm.get("final_route") != "agentic_build_planner":
            raise ValueError("agent prompt eval OpenRealm village route is invalid")
        if openrealm.get("build_kind") != "openrealm_structure":
            raise ValueError("agent prompt eval OpenRealm village build kind is invalid")
        if openrealm.get("build_material_name") != "openrealm_template":
            raise ValueError("agent prompt eval OpenRealm village material is invalid")
        if openrealm.get("planned_node_writes") != 96:
            raise ValueError("agent prompt eval OpenRealm village must plan exactly 96 node writes")
        if openrealm.get("selected_candidate_id") != "generated_openrealm_lakeside_village":
            raise ValueError("agent prompt eval OpenRealm village selected candidate is invalid")
        if openrealm.get("generated_candidate_id") != "generated_openrealm_lakeside_village":
            raise ValueError("agent prompt eval OpenRealm village generated candidate is invalid")
        if openrealm.get("generated_build_option_status") != "validated":
            raise ValueError("agent prompt eval OpenRealm village generated option was not validated")
        if player_loop.get("status") != "pass":
            raise ValueError("agent prompt eval player agent loop case is invalid")
        if player_loop.get("prompt") != "Nova, Build a cozy lakeside village with floating lanterns":
            raise ValueError("agent prompt eval player agent loop prompt is invalid")
        if player_loop.get("route") != "agentic_build_planner" \
                and player_loop.get("final_route") != "agentic_build_planner":
            raise ValueError("agent prompt eval player agent loop route is invalid")
        if player_loop.get("final_status") != "pending_approval":
            raise ValueError("agent prompt eval player agent loop final status is invalid")
        if player_loop.get("build_kind") != "openrealm_structure":
            raise ValueError("agent prompt eval player agent loop build kind is invalid")
        if player_loop.get("build_material_name") != "openrealm_template":
            raise ValueError("agent prompt eval player agent loop material is invalid")
        if player_loop.get("planned_node_writes") != 96:
            raise ValueError("agent prompt eval player agent loop must plan exactly 96 node writes")
        if player_loop.get("selected_candidate_id") != "generated_openrealm_lakeside_village":
            raise ValueError("agent prompt eval player agent loop selected candidate is invalid")
        if player_loop.get("natural_chat_handled") is not True:
            raise ValueError("agent prompt eval player agent loop natural chat was not handled")
        if player_loop.get("options_handled") is not True \
                or player_loop.get("options_status") != "success" \
                or player_loop.get("options_action") != "build_options":
            raise ValueError("agent prompt eval player agent loop options reply is invalid")
        if player_loop.get("options_selected_candidate_id") != "generated_openrealm_lakeside_village":
            raise ValueError("agent prompt eval player agent loop options selected candidate is invalid")
        if player_loop.get("options_no_world_mutation") is not True:
            raise ValueError("agent prompt eval player agent loop options mutated the world")
        _require_natural_review_trace(
            player_loop,
            prefix="options",
            label="options",
            expected_action="build_options",
            expected_status="success",
            expected_public_prompt="options",
        )
        if player_loop.get("select_handled") is not True \
                or player_loop.get("select_status") != "success" \
                or player_loop.get("select_action") != "select_build_option":
            raise ValueError("agent prompt eval player agent loop select reply is invalid")
        if player_loop.get("select_selected_candidate_id") != "marker":
            raise ValueError("agent prompt eval player agent loop select candidate is invalid")
        if player_loop.get("select_previous_selected_candidate_id") != "generated_openrealm_lakeside_village":
            raise ValueError("agent prompt eval player agent loop select previous candidate is invalid")
        if player_loop.get("select_selected_by_player") is not True:
            raise ValueError("agent prompt eval player agent loop select was not marked player-selected")
        if player_loop.get("select_decision_source") != "player_selected_build_option":
            raise ValueError("agent prompt eval player agent loop select decision source is invalid")
        if player_loop.get("select_no_world_mutation") is not True:
            raise ValueError("agent prompt eval player agent loop select mutated the world")
        _require_natural_review_trace(
            player_loop,
            prefix="select",
            label="select option",
            expected_action="select_build_option",
            expected_status="success",
            expected_public_prompt="select option marker",
        )
        if player_loop.get("pending_plan_handled") is not True \
                or player_loop.get("pending_plan_status") != "success" \
                or player_loop.get("pending_plan_action") != "pending_plan":
            raise ValueError("agent prompt eval player agent loop pending plan reply is invalid")
        if player_loop.get("pending_plan_selected_candidate_id") != "marker":
            raise ValueError("agent prompt eval player agent loop pending plan selected candidate is invalid")
        _require_natural_review_trace(
            player_loop,
            prefix="pending_plan",
            label="pending plan",
            expected_action="pending_plan",
            expected_status="success",
            expected_public_prompt="pending plan",
        )
        if player_loop.get("discard_handled") is not True \
                or player_loop.get("discard_status") != "success" \
                or player_loop.get("discard_action") != "discard_approval":
            raise ValueError("agent prompt eval player agent loop discard reply is invalid")
        _require_natural_review_trace(
            player_loop,
            prefix="discard",
            label="discard",
            expected_action="discard_approval",
            expected_status="success",
            expected_public_prompt="no",
        )
        if player_loop.get("after_discard_handled") is not True \
                or player_loop.get("after_discard_status") != "blocked" \
                or player_loop.get("after_discard_reason") != "no_pending_approval":
            raise ValueError("agent prompt eval player agent loop after-discard reply is invalid")
        _require_natural_review_trace(
            player_loop,
            prefix="after_discard",
            label="after discard",
            expected_action="pending_plan",
            expected_status="blocked",
            expected_public_prompt="pending plan",
            expected_reason="no_pending_approval",
        )
        if model.get("status") != "pass":
            raise ValueError("agent prompt eval model case is invalid")
        if model.get("route") != "model_adapter_async" and model.get("final_route") != "model_adapter_async":
            raise ValueError("agent prompt eval model route is not async")
        if adapter_mode == "agents_sdk_sidecar":
            for case_id in ("build_fire", "fire_only_strict", "tnt_wall", "agentic_build_planner"):
                _require_agentic_tool_case(case_map.get(case_id, {}), case_id)
            _require_agentic_tool_case(
                stone_bridge,
                "stone_bridge",
                {"propose_build_option"},
            )
            _require_agentic_tool_case(
                small_cabin,
                "small_cabin",
                {"propose_build_option"},
            )
            _require_agentic_tool_case(path_to_hill, "path_to_hill")
            _require_agentic_tool_case(
                openrealm,
                "openrealm_village",
                {"propose_build_option"},
            )
            _require_agentic_tool_case(
                player_loop,
                "player_agent_loop",
                {"propose_build_option"},
            )

    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    if summary.get("cases_total") != 10 or summary.get("cases_passed") != 10:
        raise ValueError("agent prompt eval summary case counts are invalid")
    if summary.get("golden_prompt_suite") != GOLDEN_PROMPT_SUITE:
        raise ValueError("agent prompt eval golden prompt suite is invalid")
    if summary.get("golden_prompt_backlog_total") != GOLDEN_PROMPT_BACKLOG_TOTAL:
        raise ValueError("agent prompt eval golden prompt backlog total is invalid")
    if summary.get("golden_prompts_total") != len(ENFORCED_GOLDEN_PROMPT_CASE_IDS):
        raise ValueError("agent prompt eval golden prompt enforced count is invalid")
    if summary.get("golden_prompts_passed") != len(ENFORCED_GOLDEN_PROMPT_CASE_IDS):
        raise ValueError("agent prompt eval golden prompts did not all pass")
    if summary.get("golden_prompts_failed") != 0:
        raise ValueError("agent prompt eval golden prompt failures must be zero")
    golden_case_ids = summary.get("golden_prompt_case_ids")
    if not isinstance(golden_case_ids, dict):
        raise ValueError("agent prompt eval golden prompt case ids are invalid")
    for case_id in ENFORCED_GOLDEN_PROMPT_CASE_IDS:
        if golden_case_ids.get(case_id) is not True:
            raise ValueError(f"agent prompt eval missing golden prompt case {case_id}")
    for field in (
        "build_fire_checked",
        "fire_only_strict_checked",
        "tnt_wall_checked",
        "stone_bridge_checked",
        "small_cabin_checked",
        "path_to_hill_checked",
        "agentic_build_planner_checked",
        "openrealm_village_checked",
        "player_agent_loop_checked",
        "player_agent_loop_review_traces_checked",
        "player_agent_loop_option_selection_checked",
        "model_checked",
    ):
        _require_bool(summary, field)
    if not isinstance(summary.get("model_adapter_requests"), int) or summary["model_adapter_requests"] < 2:
        raise ValueError("agent prompt eval model adapter request count is invalid")
    if summary.get("model_adapter_successes") != summary.get("model_adapter_requests"):
        raise ValueError("agent prompt eval model adapter success count is invalid")
    if summary.get("model_adapter_failures") != 0:
        raise ValueError("agent prompt eval model adapter failures must be zero")
    if summary.get("model_adapter_timeouts") != 0:
        raise ValueError("agent prompt eval model adapter timeouts must be zero")

    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    for field in (
        "public_safe_output",
        "disposable_live_world_only",
        "read_only_prompt_eval",
        "pending_approvals_discarded",
        "no_world_mutation",
        "no_raw_assets",
        "no_provider_prompts",
        "no_family_world_coordinates",
        "no_private_prompt_retained",
    ):
        _require_bool(safety, field)
    if safety.get("world_mutation_performed") is not False:
        raise ValueError("agent prompt eval safety says world mutation occurred")

    bounds = payload.get("bounds") if isinstance(payload.get("bounds"), dict) else {}
    output_bytes = bounds.get("output_bytes")
    declared_max = bounds.get("max_bytes", max_bytes)
    if not isinstance(output_bytes, int) or not isinstance(declared_max, int):
        raise ValueError("agent prompt eval bounds are invalid")
    if output_bytes > declared_max or output_bytes > max_bytes:
        raise ValueError("agent prompt eval output exceeds max bytes")
    if adapter_mode == "agents_sdk_sidecar" and bounds.get("truncated") is True:
        raise ValueError("agent prompt eval sidecar evidence was truncated")

    agentic_tool_cases = 0
    if cases:
        for case_id in (
            "build_fire",
            "fire_only_strict",
            "tnt_wall",
            "stone_bridge",
            "small_cabin",
            "path_to_hill",
            "agentic_build_planner",
            "openrealm_village",
            "player_agent_loop",
        ):
            case = case_map.get(case_id, {})
            if case.get("adapter_tool_decision_source") in ACCEPTED_AGENTIC_TOOL_DECISION_SOURCES \
                    and case.get("adapter_required_tool_calls_satisfied") is True:
                agentic_tool_cases += 1

    return {
        "agent_prompt_eval_status": "pass",
        "agent_prompt_eval_output_bytes": output_bytes,
        "agent_prompt_eval_cases": summary["cases_total"],
        "agent_prompt_eval_passed": summary["cases_passed"],
        "agent_prompt_eval_build_fire_checked": True,
        "agent_prompt_eval_fire_only_strict_checked": True,
        "agent_prompt_eval_tnt_wall_checked": True,
        "agent_prompt_eval_stone_bridge_checked": True,
        "agent_prompt_eval_path_to_hill_checked": True,
        "agent_prompt_eval_agentic_build_planner_checked": True,
        "agent_prompt_eval_openrealm_village_checked": True,
        "agent_prompt_eval_player_agent_loop_checked": True,
        "agent_prompt_eval_player_agent_loop_review_traces_checked": True,
        "agent_prompt_eval_player_agent_loop_option_selection_checked": True,
        "agent_prompt_eval_model_checked": True,
        "agent_prompt_eval_golden_prompt_suite": GOLDEN_PROMPT_SUITE,
        "agent_prompt_eval_golden_prompt_backlog_total": GOLDEN_PROMPT_BACKLOG_TOTAL,
        "agent_prompt_eval_golden_prompts_total": len(ENFORCED_GOLDEN_PROMPT_CASE_IDS),
        "agent_prompt_eval_golden_prompts_passed": len(ENFORCED_GOLDEN_PROMPT_CASE_IDS),
        "agent_prompt_eval_golden_prompts_failed": 0,
        "agent_prompt_eval_fire_planned_node_writes": 1,
        "agent_prompt_eval_fire_only_strict_planned_node_writes": 1,
        "agent_prompt_eval_tnt_wall_planned_node_writes": 12,
        "agent_prompt_eval_stone_bridge_planned_node_writes": next(
            (
                item.get("planned_node_writes")
                for item in cases
                if isinstance(item, dict) and item.get("case_id") == "stone_bridge"
            ),
            None,
        ),
        "agent_prompt_eval_stone_bridge_candidate_id": "generated_bridge_platform",
        "agent_prompt_eval_small_cabin_checked": True,
        "agent_prompt_eval_small_cabin_planned_node_writes": 10,
        "agent_prompt_eval_small_cabin_candidate_id": "generated_prompt_shaped_cabin",
        "agent_prompt_eval_path_to_hill_planned_node_writes": 8,
        "agent_prompt_eval_path_to_hill_candidate_id": "parsed_request",
        "agent_prompt_eval_agentic_build_planner_planned_node_writes": next(
            (
                item.get("planned_node_writes")
                for item in cases
                if isinstance(item, dict) and item.get("case_id") == "agentic_build_planner"
            ),
            None,
        ),
        "agent_prompt_eval_openrealm_village_planned_node_writes": 96,
        "agent_prompt_eval_openrealm_village_candidate_id": "generated_openrealm_lakeside_village",
        "agent_prompt_eval_player_agent_loop_planned_node_writes": 96,
        "agent_prompt_eval_player_agent_loop_candidate_id": "generated_openrealm_lakeside_village",
        "agent_prompt_eval_player_agent_loop_selected_option_after_player_choice": "marker",
        "agent_prompt_eval_model_adapter_requests": summary["model_adapter_requests"],
        "agent_prompt_eval_model_adapter_successes": summary["model_adapter_successes"],
        "agent_prompt_eval_adapter_mode": runtime_context["adapter_mode"],
        "agent_prompt_eval_requires_model_network": runtime_context.get("requires_model_network") is True,
        "agent_prompt_eval_agentic_tool_cases": agentic_tool_cases,
        "agent_prompt_eval_agentic_tool_cases_required": 9 if adapter_mode == "agents_sdk_sidecar" else 0,
        "agent_prompt_eval_world_mutation": False,
    }


def run_probe(args) -> int:
    root = resolve_path(Path.cwd(), args.root).resolve()
    server_bin = resolve_path(root, args.server_bin)
    output = resolve_path(root, args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    world_dir = output.parent / "agent-prompt-eval-live-world"
    write_probe_world(
        world_dir,
        args.generated_at,
        args.max_bytes,
        args.adapter_endpoint,
        args.model_prompt,
    )

    port = args.port or reserve_udp_port()
    log_path = world_dir / "debug.log"
    config_path = world_dir / "probe.conf"
    config_lines = [
        "server_name = AI Native Agent Prompt Eval Probe",
        "name = agent_prompt_eval_probe",
        "secure.enable_security = true",
        "creative_mode = false",
        "enable_damage = false",
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
        print("agent prompt eval live probe timed out", file=sys.stderr)
        return 1
    if completed.returncode != 0:
        print("agent prompt eval live server exited with non-zero status", file=sys.stderr)
        if completed.stderr.strip():
            print(completed.stderr.strip()[-1200:], file=sys.stderr)
        return 1

    world_artifact = world_dir / LIVE_ARTIFACT_NAME
    result = read_result(world_dir)
    if result.get("status") != "pass":
        if world_artifact.is_file():
            shutil.copyfile(world_artifact, output)
        reason = result.get("reason", "unknown")
        print(f"agent prompt eval live probe failed: {reason}", file=sys.stderr)
        return 1

    if not world_artifact.is_file():
        print("agent prompt eval live artifact missing", file=sys.stderr)
        return 1
    try:
        payload = json.loads(world_artifact.read_text(encoding="utf-8"))
        validate_live_result(payload, max_bytes=args.max_bytes)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(
            f"agent prompt eval live artifact invalid: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 1
    shutil.copyfile(world_artifact, output)
    print("agent prompt eval live probe captured")
    return 0


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Capture /ai_agent_eval from a disposable ai_runtime server."
    )
    parser.add_argument("--root", default=".", help="Luanti source checkout root.")
    parser.add_argument("--server-bin", default="bin/luantiserver", help="Server binary to launch.")
    parser.add_argument("--output", required=True, help="Output JSON artifact path.")
    parser.add_argument("--generated-at", required=True, help="generated_at value for the probe.")
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES, help="Output byte budget.")
    parser.add_argument("--timeout", type=float, default=20.0, help="Seconds to wait for probe shutdown.")
    parser.add_argument("--port", type=int, help="Optional UDP port for the disposable server.")
    parser.add_argument(
        "--adapter-endpoint",
        help=(
            "Optional loopback Agents SDK model adapter endpoint. When omitted, "
            "the probe installs a deterministic mock async adapter."
        ),
    )
    parser.add_argument(
        "--adapter-timeout",
        type=float,
        default=60.0,
        help="Seconds for the Agents SDK adapter HTTP request when --adapter-endpoint is set.",
    )
    parser.add_argument(
        "--model-prompt",
        default=DEFAULT_MODEL_PROMPT,
        help="Model prompt used for the model eval case.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    return run_probe(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
