#!/usr/bin/env python3
"""Verify the first-party Agents SDK model adapter bridge contract."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
BRIDGE_DIR = ROOT / "tools" / "agents_sdk_model_adapter"
AGENT = BRIDGE_DIR / "agent.py"
MAIN = BRIDGE_DIR / "main.py"
PYPROJECT = BRIDGE_DIR / "pyproject.toml"
README = BRIDGE_DIR / "README.md"
DOC = ROOT / "doc" / "ai-native-runtime" / "agents-sdk-model-adapter.md"
READINESS = ROOT / "util" / "ai_native_agents_sdk_sidecar_readiness.py"
ADAPTER_CONTRACT_EVAL = ROOT / "util" / "ai_native_agent_adapter_contract_eval.py"
RUNTIME_README = ROOT / "doc" / "ai-native-runtime" / "README.md"
MODEL_CONTRACT = ROOT / "doc" / "ai-native-runtime" / "model-adapter-contract.md"
LUA_PLUGIN = ROOT / "builtin" / "game" / "ai_agents_sdk_adapter_plugin.lua"
BUILTIN_INIT = ROOT / "builtin" / "game" / "init.lua"

PRIVATE_PATTERNS = re.compile(
    r"minecraftpi|192\.168|spacebase|themepark|showcase100|disneyland100|"
    r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY=|/Users/",
    re.I,
)


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _require(condition: bool, kind: str, details: str, violations: list[dict]) -> None:
    if not condition:
        violations.append({"kind": kind, "details": details})


def _load_agent_module():
    spec = importlib.util.spec_from_file_location("ai_native_agents_sdk_agent", AGENT)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load agent.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_planning_sample_request(module) -> dict:
    request = module.sample_request()
    request["public_prompt"] = "\n".join([
        "Plan a Luanti build request using only the listed executable options.",
        "Player request: build a wall of tnt",
        "Candidate summary: platform:platform:default:4|tnt_wall:wall:tnt:12",
    ])
    request["context"] = {
        "surface_id": "builder",
        "intent": "build_planning",
        "capabilities": "world.read,http.llm",
        "player_request": "build a wall of tnt",
        "candidate_summary": "platform:platform:default:4|tnt_wall:wall:tnt:12",
    }
    return request


def validate_contract() -> dict:
    violations: list[dict] = []
    for path in (AGENT, MAIN, PYPROJECT, README, DOC, READINESS, ADAPTER_CONTRACT_EVAL, LUA_PLUGIN):
        _require(path.exists(), "missing_file", str(path), violations)
    if violations:
        return {"status": "fail", "violations": violations}

    agent_source = _read(AGENT)
    main_source = _read(MAIN)
    readiness_source = _read(READINESS)
    adapter_contract_eval_source = _read(ADAPTER_CONTRACT_EVAL)
    pyproject = _read(PYPROJECT)
    readme = _read(README)
    doc = _read(DOC)
    runtime_readme = _read(RUNTIME_README)
    model_contract = _read(MODEL_CONTRACT)
    lua_plugin = _read(LUA_PLUGIN)
    builtin_init = _read(BUILTIN_INIT)

    for phrase in (
        "from agents import Agent, Runner, WebSearchTool, function_tool",
        "@function_tool",
        "Agent(",
        "Runner.run",
        "WebSearchTool()",
        "TOOL_POWER_MANIFEST",
        "def tool_power_manifest",
        "recall_build_prompt_memory",
        "propose_build_option",
        "select_build_option",
        "plan_build_actions",
        "luanti_build_action_plan_v1",
        "BUILD_PLANNING_REQUIRED_TOOLS",
        "required_tool_calls_satisfied",
        "generated_option",
        "agent_selected_build_option",
        "generated_build_option_tool",
        "_build_option_uses_generated",
        "adapter_fallback_after_agent_missing_required_tool",
        "_TOOL_TRACE",
        '"tool_trace": tool_trace',
        '"tool_powers": tool_power_manifest()',
        '"tool_decisions": tool_decisions',
        '"build_action_plan": tool_decisions.get("build_action_plan")',
        '"tool_decision_source": decision_source',
        '"selected_option_id": _selected_option_id(tool_decisions)',
        '"direct_world_mutation": False',
        '"world_mutation_authority": "luanti"',
        "core.ai_model_ops.request",
        "ai_native_model_adapter_response",
        "FORBIDDEN_RESPONSE_KEYS",
    ):
        _require(phrase in agent_source, "agent_source_missing_phrase", phrase, violations)

    for phrase in (
        "GET",
        "/health",
        "POST",
        "/v1/model-adapter",
        "run_model_adapter_request",
    ):
        _require(phrase in main_source, "main_source_missing_phrase", phrase, violations)

    for phrase in (
        "ai_native_agents_sdk_sidecar_readiness",
        "managed-http",
        "existing-http",
        "offline-smoke",
        "/health",
        "/v1/model-adapter",
        "OPENAI_API_KEY",
        "endpoint_not_loopback",
        "no_provider_credentials_required",
        "require_live_agent",
        "live_agent_execution",
        "live_web_lookup_available",
        "no_forbidden_payload_keys",
        "tool_powers_declared",
        "no_direct_world_mutation_tools",
        "require_build_planning_tools",
        "required_tool_calls_satisfied",
    ):
        _require(phrase in readiness_source, "readiness_source_missing_phrase", phrase, violations)

    for phrase in (
        'REPORT_KIND = "ai_native_agent_adapter_contract_eval_result"',
        "loopback_endpoint",
        "ready_for_adapter_contract_eval",
        "adapter_replay_request",
        "agents_sdk_function_tool",
        "required_tool_calls_satisfied",
        "world_mutation_authority",
        "no_world_mutation",
        "no_raw_provider_payloads",
    ):
        _require(phrase in adapter_contract_eval_source, "adapter_contract_eval_missing_phrase", phrase, violations)

    for phrase in (
        'core.settings:get_bool("ai_runtime.enable_agents_sdk_adapter", false)',
        'core.register_chatcommand("ai_agents_sdk_adapter_probe"',
        "http://127.0.0.1:8766/v1/model-adapter",
        "endpoint_is_loopback",
        "core.ai_agent_plugin.set_model_adapter",
        "core.ai_agent_plugin.set_model_adapter_async",
        "core.ai_model_ops.request",
        "core.ai_model_ops.request_async",
        "ai_native_model_adapter_response",
        "sidecar_executes_world_mutation = false",
    ):
        _require(phrase in lua_plugin, "lua_plugin_missing_phrase", phrase, violations)

    _require(
        builtin_init.find('dofile(gamepath .. "ai_agent_plugin.lua")')
        < builtin_init.find('dofile(gamepath .. "ai_agents_sdk_adapter_plugin.lua")'),
        "lua_plugin_loaded_before_agent_plugin",
        "ai_agents_sdk_adapter_plugin must load after ai_agent_plugin",
        violations,
    )
    _require(
        'core.settings:get_bool("ai_runtime.enable_agents_sdk_adapter", false)' in builtin_init,
        "lua_plugin_init_gate_missing",
        str(BUILTIN_INIT),
        violations,
    )

    _require("openai-agents" in pyproject, "pyproject_missing_openai_agents", str(PYPROJECT), violations)
    _require("WebSearchTool" in readme, "readme_missing_web_search_tool", str(README), violations)
    _require("function_tool" in readme, "readme_missing_function_tool", str(README), violations)
    _require("ai_native_agent_adapter_contract_eval.py" in readme,
        "readme_missing_adapter_contract_eval", str(README), violations)
    _require("Agents SDK Model Adapter" in runtime_readme, "runtime_readme_missing_link", str(RUNTIME_README), violations)
    _require("ai_native_agent_adapter_contract_eval.py" in runtime_readme,
        "runtime_readme_missing_adapter_contract_eval", str(RUNTIME_README), violations)
    _require("tools/agents_sdk_model_adapter" in model_contract, "model_contract_missing_bridge", str(MODEL_CONTRACT), violations)

    for phrase in (
        "Agent",
        "Runner",
        "WebSearchTool",
        "function_tool",
        "http.llm",
        "The sidecar must not execute world mutations directly",
        "Luanti remains the only writer",
        "--require-live-agent",
        "agentic_execution",
        "live_web_lookup_available",
        "OPENAI_API_KEY",
        "ai_native_agent_adapter_contract_eval.py",
        "ready_for_adapter_contract_eval",
    ):
        _require(phrase in doc, "doc_missing_phrase", phrase, violations)

    combined_public_docs = "\n".join([readme, doc, model_contract])
    _require(not PRIVATE_PATTERNS.search(combined_public_docs), "private_pattern_found", "public docs", violations)

    try:
        module = _load_agent_module()
        response = module.run_model_adapter_request(module.sample_request(), force_offline=True)
    except Exception as exc:  # pragma: no cover - reported as verifier failure.
        violations.append({"kind": "offline_smoke_failed", "details": repr(exc)})
    else:
        _require(response.get("response_kind") == "ai_native_model_adapter_response",
            "offline_response_kind_invalid", str(response), violations)
        _require(response.get("adapter_name") == "openai-agents-sdk-model-adapter",
            "offline_adapter_name_invalid", str(response), violations)
        _require(response.get("ok") is True, "offline_response_not_ok", str(response), violations)
        nested = response.get("response") if isinstance(response.get("response"), dict) else {}
        _require(nested.get("agentic_execution") is False,
            "offline_response_should_not_claim_live_agent", str(response), violations)
        _require("WebSearchTool" in nested.get("tools_enabled", []),
            "offline_response_missing_web_search_tool", str(response), violations)
        _require("recall_build_prompt_memory" in nested.get("tools_enabled", []),
            "offline_response_missing_prompt_memory_tool", str(response), violations)
        _require("propose_build_option" in nested.get("tools_enabled", []),
            "offline_response_missing_generated_option_tool", str(response), violations)
        _require("select_build_option" in nested.get("tools_enabled", []),
            "offline_response_missing_select_option_tool", str(response), violations)
        _require("plan_build_actions" in nested.get("tools_enabled", []),
            "offline_response_missing_build_action_plan_tool", str(response), violations)
        _require(nested.get("tool_decision_source") == "offline_adapter_fallback",
            "offline_response_decision_source_invalid", str(response), violations)
        _require(nested.get("required_tool_calls_satisfied") is not False,
            "offline_response_required_tools_invalid", str(response), violations)
        tool_powers = nested.get("tool_powers") if isinstance(nested.get("tool_powers"), list) else []
        _require(any(power.get("name") == "WebSearchTool" for power in tool_powers if isinstance(power, dict)),
            "offline_response_missing_web_search_power", str(response), violations)
        _require(any(power.get("name") == "recall_build_prompt_memory"
            for power in tool_powers if isinstance(power, dict)),
            "offline_response_missing_prompt_memory_power", str(response), violations)
        _require(any(power.get("name") == "propose_build_option"
            for power in tool_powers if isinstance(power, dict)),
            "offline_response_missing_generated_option_power", str(response), violations)
        _require(any(power.get("name") == "select_build_option"
            for power in tool_powers if isinstance(power, dict)),
            "offline_response_missing_select_option_power", str(response), violations)
        _require(any(power.get("name") == "plan_build_actions"
            for power in tool_powers if isinstance(power, dict)),
            "offline_response_missing_build_action_plan_power", str(response), violations)
        _require(all(power.get("direct_world_mutation") is False for power in tool_powers if isinstance(power, dict)),
            "offline_response_tool_can_mutate_world", str(response), violations)
        _require(nested.get("world_mutation_authority") == "luanti",
            "offline_response_mutation_authority_invalid", str(response), violations)
        _require(not any(key in response for key in (
            "raw_provider_request",
            "raw_provider_response",
            "credentials",
            "private_payload",
            "asset_payload",
        )), "offline_response_has_forbidden_payload", str(response), violations)

        build_response = module.run_model_adapter_request(
            _build_planning_sample_request(module),
            force_offline=True,
        )
        build_nested = (
            build_response.get("response")
            if isinstance(build_response.get("response"), dict)
            else {}
        )
        build_plan = (
            build_nested.get("build_action_plan")
            if isinstance(build_nested.get("build_action_plan"), dict)
            else {}
        )
        _require(build_plan.get("status") == "ready",
            "offline_build_response_missing_build_action_plan", str(build_response), violations)
        _require(build_plan.get("selected_option_id") == "tnt_wall",
            "offline_build_response_plan_selected_option_invalid", str(build_response), violations)
        _require(build_plan.get("plan_kind") == "luanti_build_action_plan_v1",
            "offline_build_response_plan_kind_invalid", str(build_response), violations)
        _require(build_plan.get("step_count") == 4,
            "offline_build_response_plan_step_count_invalid", str(build_response), violations)
        _require("plan_build_actions" in build_nested.get("required_tool_calls", []),
            "offline_build_response_missing_required_plan_tool", str(build_response), violations)

    return {
        "status": "pass" if not violations else "fail",
        "bridge_dir": str(BRIDGE_DIR.relative_to(ROOT)),
        "checks": {
            "agents_sdk_imports": True,
            "web_search_tool": True,
            "function_tools": True,
            "http_adapter_endpoint": True,
            "lua_sidecar_adapter": True,
            "sidecar_readiness_probe": True,
            "adapter_contract_eval": True,
            "tool_power_manifest": True,
            "offline_smoke": True,
            "public_safe_docs": True,
        },
        "violations": violations,
    }


def main() -> int:
    result = validate_contract()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
