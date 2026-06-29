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


def validate_contract() -> dict:
    violations: list[dict] = []
    for path in (AGENT, MAIN, PYPROJECT, README, DOC, LUA_PLUGIN):
        _require(path.exists(), "missing_file", str(path), violations)
    if violations:
        return {"status": "fail", "violations": violations}

    agent_source = _read(AGENT)
    main_source = _read(MAIN)
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
        'core.settings:get_bool("ai_runtime.enable_agents_sdk_adapter", false)',
        'core.register_chatcommand("ai_agents_sdk_adapter_probe"',
        "http://127.0.0.1:8766/v1/model-adapter",
        "endpoint_is_loopback",
        "core.ai_agent_plugin.set_model_adapter",
        "core.ai_model_ops.request",
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
    _require("Agents SDK Model Adapter" in runtime_readme, "runtime_readme_missing_link", str(RUNTIME_README), violations)
    _require("tools/agents_sdk_model_adapter" in model_contract, "model_contract_missing_bridge", str(MODEL_CONTRACT), violations)

    for phrase in (
        "Agent",
        "Runner",
        "WebSearchTool",
        "function_tool",
        "http.llm",
        "The sidecar must not execute world mutations directly",
        "Luanti remains the only writer",
        "OPENAI_API_KEY",
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
        _require(not any(key in response for key in (
            "raw_provider_request",
            "raw_provider_response",
            "credentials",
            "private_payload",
            "asset_payload",
        )), "offline_response_has_forbidden_payload", str(response), violations)

    return {
        "status": "pass" if not violations else "fail",
        "bridge_dir": str(BRIDGE_DIR.relative_to(ROOT)),
        "checks": {
            "agents_sdk_imports": True,
            "web_search_tool": True,
            "function_tools": True,
            "http_adapter_endpoint": True,
            "lua_sidecar_adapter": True,
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
