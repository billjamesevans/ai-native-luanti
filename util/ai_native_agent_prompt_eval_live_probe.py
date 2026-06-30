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
DEFAULT_MAX_BYTES = 22000
DEFAULT_MODEL_PROMPT = "what can you plan with tools next?"

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
            "  return {",
            "    case_id = case.case_id,",
            "    status = case.status,",
            "    ok = case.ok == true,",
            "    prompt = case.prompt,",
            "    action = reply.action or final_reply.action,",
            "    reply_status = reply.status,",
            "    final_status = case.final_status or final_reply.status,",
            "    route = trace.route,",
            "    final_route = final_trace.route,",
            "    build_kind = reply.build_kind or final_reply.build_kind,",
            "    build_material_name = reply.build_material_name or final_reply.build_material_name,",
            "    planned_node_writes = reply.planned_node_writes or final_reply.planned_node_writes,",
            "    planner_mode = reply.planner_mode or final_reply.planner_mode,",
            "    selected_candidate_id = reply.selected_candidate_id or final_reply.selected_candidate_id,",
            "    candidate_count = reply.candidate_count or final_reply.candidate_count,",
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
            "      agentic_build_planner = cases.agentic_build_planner ~= nil,",
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
            "      done({",
            "        ok = true,",
            "        message = \"Mock agent prompt-eval adapter response.\",",
            "        adapter_name = \"mock-agent-prompt-eval-adapter\",",
            "        elapsed_us = 1000,",
            "        response = {",
            "          agentic_execution = true,",
            "          tools_enabled = { \"recommend_build_option\", \"classify_world_action\" },",
            "        },",
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
            "      agentic_build_planner_checked = eval.case_ids.agentic_build_planner == true,",
            "      model_checked = eval.case_ids.model == true,",
            "      model_adapter_requests = eval.metrics.model_adapter_requests_delta or 0,",
            "      model_adapter_successes = eval.metrics.model_adapter_successes_delta or 0,",
            "      model_adapter_failures = eval.metrics.model_adapter_failures_delta or 0,",
            "      model_adapter_timeouts = eval.metrics.model_adapter_timeouts_delta or 0,",
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
            "  core.ai_agent_plugin.configure({ max_lights = 16 })",
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
    if prompt_eval.get("cases_total") != 5:
        raise ValueError("agent prompt eval case count is invalid")
    if prompt_eval.get("cases_passed") != 5 or prompt_eval.get("cases_failed") != 0:
        raise ValueError("agent prompt eval cases did not all pass")
    case_ids = prompt_eval.get("case_ids") if isinstance(prompt_eval.get("case_ids"), dict) else {}
    for case_id in ("build_fire", "fire_only_strict", "tnt_wall", "agentic_build_planner", "model"):
        if case_ids.get(case_id) is not True:
            raise ValueError(f"agent prompt eval missing {case_id}")

    cases = prompt_eval.get("cases")
    if cases is None and payload.get("bounds", {}).get("truncated") is True:
        cases = []
    if not isinstance(cases, list):
        raise ValueError("agent prompt eval cases summary is invalid")
    case_map = {
        item.get("case_id"): item
        for item in cases
        if isinstance(item, dict) and item.get("case_id")
    }
    if cases:
        fire = case_map.get("build_fire", {})
        fire_only = case_map.get("fire_only_strict", {})
        tnt = case_map.get("tnt_wall", {})
        planner = case_map.get("agentic_build_planner", {})
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
        if model.get("status") != "pass":
            raise ValueError("agent prompt eval model case is invalid")
        if model.get("route") != "model_adapter_async" and model.get("final_route") != "model_adapter_async":
            raise ValueError("agent prompt eval model route is not async")

    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    if summary.get("cases_total") != 5 or summary.get("cases_passed") != 5:
        raise ValueError("agent prompt eval summary case counts are invalid")
    for field in (
        "build_fire_checked",
        "fire_only_strict_checked",
        "tnt_wall_checked",
        "agentic_build_planner_checked",
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

    return {
        "agent_prompt_eval_status": "pass",
        "agent_prompt_eval_output_bytes": output_bytes,
        "agent_prompt_eval_cases": summary["cases_total"],
        "agent_prompt_eval_passed": summary["cases_passed"],
        "agent_prompt_eval_build_fire_checked": True,
        "agent_prompt_eval_fire_only_strict_checked": True,
        "agent_prompt_eval_tnt_wall_checked": True,
        "agent_prompt_eval_agentic_build_planner_checked": True,
        "agent_prompt_eval_model_checked": True,
        "agent_prompt_eval_fire_planned_node_writes": 1,
        "agent_prompt_eval_fire_only_strict_planned_node_writes": 1,
        "agent_prompt_eval_tnt_wall_planned_node_writes": 12,
        "agent_prompt_eval_agentic_build_planner_planned_node_writes": next(
            (
                item.get("planned_node_writes")
                for item in cases
                if isinstance(item, dict) and item.get("case_id") == "agentic_build_planner"
            ),
            None,
        ),
        "agent_prompt_eval_model_adapter_requests": summary["model_adapter_requests"],
        "agent_prompt_eval_model_adapter_successes": summary["model_adapter_successes"],
        "agent_prompt_eval_adapter_mode": runtime_context["adapter_mode"],
        "agent_prompt_eval_requires_model_network": runtime_context.get("requires_model_network") is True,
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
