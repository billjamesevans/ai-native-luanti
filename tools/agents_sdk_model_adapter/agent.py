#!/usr/bin/env python3
"""OpenAI Agents SDK bridge for Luanti's core.ai_model_ops.request contract."""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import time
from typing import Any

try:
    from agents import Agent, Runner, WebSearchTool, function_tool
except Exception:  # pragma: no cover - offline contract tests use the fallback.
    Agent = None
    Runner = None
    WebSearchTool = None

    def function_tool(func=None, **_kwargs):
        def decorator(fn):
            return fn

        if func is None:
            return decorator
        return decorator(func)


DEFAULT_MODEL = os.getenv("AI_NATIVE_AGENT_MODEL", "gpt-4.1-mini")
ADAPTER_NAME = "openai-agents-sdk-model-adapter"
MAX_PROMPT_BYTES = 6000
MAX_RESPONSE_BYTES = 4000
FORBIDDEN_RESPONSE_KEYS = {
    "raw_provider_request",
    "raw_provider_response",
    "provider_headers",
    "credentials",
    "private_payload",
    "asset_payload",
}


TOOL_POWER_MANIFEST = (
    {
        "name": "summarize_runtime_capabilities",
        "kind": "function_tool",
        "runtime_power": "capability_summary",
        "read_only": True,
        "available_without_provider_credentials": True,
        "direct_world_mutation": False,
        "engine_authority": "luanti_capability_checks",
    },
    {
        "name": "classify_world_action",
        "kind": "function_tool",
        "runtime_power": "world_action_policy_classification",
        "read_only": True,
        "available_without_provider_credentials": True,
        "direct_world_mutation": False,
        "engine_authority": "luanti_task_preview_approval_rollback",
    },
    {
        "name": "WebSearchTool",
        "kind": "hosted_tool",
        "runtime_power": "public_web_lookup",
        "read_only": True,
        "available_without_provider_credentials": False,
        "direct_world_mutation": False,
        "engine_authority": "luanti_model_adapter_response_only",
    },
)


def _bounded_text(value: Any, max_bytes: int) -> str:
    text = str(value or "")
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def _safe_context(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    safe: dict[str, Any] = {}
    for key, child in value.items():
        if len(safe) >= 16:
            break
        if not isinstance(key, str) or key in FORBIDDEN_RESPONSE_KEYS:
            continue
        if isinstance(child, (str, int, float, bool)) or child is None:
            safe[key] = child
    return safe


def _sdk_available() -> bool:
    return Agent is not None and Runner is not None


def _sdk_ready() -> bool:
    return _sdk_available() and bool(os.getenv("OPENAI_API_KEY"))


def tool_power_manifest() -> list[dict[str, Any]]:
    powers: list[dict[str, Any]] = []
    for entry in TOOL_POWER_MANIFEST:
        power = dict(entry)
        if power["name"] == "WebSearchTool":
            power["available"] = WebSearchTool is not None
            power["requires_openai_api_key"] = True
        else:
            power["available"] = True
            power["requires_openai_api_key"] = False
        powers.append(power)
    return powers


def tool_power_names() -> list[str]:
    return [power["name"] for power in tool_power_manifest()]


@function_tool
def summarize_runtime_capabilities(surface_id: str, capability_csv: str) -> dict[str, Any]:
    """Summarize the runtime capability grants the engine already checked."""

    capabilities = {
        capability.strip()
        for capability in str(capability_csv or "").split(",")
        if capability.strip()
    }
    return {
        "surface_id": surface_id or "unknown",
        "can_use_model_adapter": "http.llm" in capabilities,
        "can_plan_imports": "import.assets" in capabilities,
        "can_mutate_world": bool({"world.place", "world.remove"} & capabilities),
        "policy": "engine_runtime_gates_remain_authoritative",
    }


@function_tool
def classify_world_action(action: str, planned_node_writes: int) -> dict[str, Any]:
    """Classify a requested world action before it is returned to Luanti."""

    writes = max(0, int(planned_node_writes or 0))
    return {
        "action": action or "reply",
        "planned_node_writes": writes,
        "requires_preview": writes > 0,
        "requires_approval": writes > 0,
        "requires_rollback": writes > 0,
        "max_recommended_writes": 1000,
    }


def build_agent(model: str | None = None) -> Any:
    if not _sdk_available():
        raise RuntimeError("openai-agents is not installed")

    tools: list[Any] = [summarize_runtime_capabilities, classify_world_action]
    if WebSearchTool is not None:
        tools.append(WebSearchTool())

    return Agent(
        name="AI-Native Luanti Runtime Agent",
        model=model or DEFAULT_MODEL,
        instructions=(
            "You are the model-backed agent sidecar for an AI-native Luanti "
            "runtime. The Luanti engine is authoritative for capabilities, "
            "world mutation, rollback, audit, and task execution. Use hosted "
            "web search only when current public information is needed. Use "
            "function tools to classify capabilities and world-action policy. "
            "Return public-safe, bounded guidance. Do not return provider raw "
            "payloads, credentials, private prompts, private world coordinates, "
            "or asset payloads."
        ),
        tools=tools,
    )


def adapter_health() -> dict[str, Any]:
    return {
        "service": "ai-native-luanti-agents-sdk-model-adapter",
        "status": "ready" if _sdk_ready() else "degraded",
        "agents_sdk_available": _sdk_available(),
        "openai_api_key_present": bool(os.getenv("OPENAI_API_KEY")),
        "web_search_tool_available": WebSearchTool is not None,
        "tool_powers": tool_power_manifest(),
        "world_mutation_authority": "luanti",
        "adapter_name": ADAPTER_NAME,
        "contract": "provider_neutral_v1",
    }


def _agent_input_from_request(request: dict[str, Any]) -> str:
    context = _safe_context(request.get("context"))
    prompt = _bounded_text(request.get("public_prompt"), MAX_PROMPT_BYTES)
    capability_csv = ""
    capabilities = context.get("capabilities")
    if isinstance(capabilities, str):
        capability_csv = capabilities
    surface_id = str(context.get("surface_id") or "guide")
    return "\n".join(
        [
            "AI-native Luanti model adapter request.",
            f"agent_id: {request.get('agent_id')}",
            f"owner: {request.get('owner')}",
            f"surface_id: {surface_id}",
            f"capabilities: {capability_csv}",
            f"public_prompt: {prompt}",
            "Return concise public-safe guidance for the player or operator.",
        ]
    )


async def _run_sdk_agent(request: dict[str, Any], model: str | None = None) -> str:
    agent = build_agent(model)
    result = Runner.run(agent, _agent_input_from_request(request))
    if inspect.isawaitable(result):
        result = await result
    return _bounded_text(getattr(result, "final_output", result), MAX_RESPONSE_BYTES)


def _offline_fallback(request: dict[str, Any], reason: str) -> dict[str, Any]:
    prompt = _bounded_text(request.get("public_prompt"), 400)
    return {
        "schema_version": 1,
        "response_kind": "ai_native_model_adapter_response",
        "adapter_contract": "provider_neutral_v1",
        "ok": True,
        "message": "Agents SDK bridge offline fallback returned bounded guidance.",
        "adapter_name": ADAPTER_NAME,
        "reason": reason,
        "response": {
            "agentic_execution": False,
            "web_search_used": False,
            "tools_enabled": tool_power_names(),
            "tool_powers": tool_power_manifest(),
            "world_mutation_authority": "luanti",
            "guidance": (
                "The sidecar is configured for Agents SDK execution. Set "
                "OPENAI_API_KEY and install openai-agents to enable live agent "
                "reasoning, hosted web search, and function tools."
            ),
            "public_prompt_echo": prompt,
        },
    }


def _sanitize_response(response: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in response.items()
        if key not in FORBIDDEN_RESPONSE_KEYS
    }


def run_model_adapter_request(
    request: dict[str, Any],
    *,
    force_offline: bool = False,
    model: str | None = None,
) -> dict[str, Any]:
    start = time.perf_counter()
    if request.get("request_kind") != "ai_native_model_adapter_request":
        return {
            "schema_version": 1,
            "response_kind": "ai_native_model_adapter_response",
            "adapter_contract": "provider_neutral_v1",
            "ok": False,
            "message": "Invalid model adapter request.",
            "adapter_name": ADAPTER_NAME,
            "reason": "invalid_request_kind",
        }

    if force_offline or not _sdk_ready():
        reason = "forced_offline" if force_offline else "agents_sdk_not_ready"
        response = _offline_fallback(request, reason)
        response["elapsed_us"] = int((time.perf_counter() - start) * 1_000_000)
        return response

    try:
        final_output = asyncio.run(_run_sdk_agent(request, model=model))
    except Exception as exc:  # pragma: no cover - live SDK path depends on credentials.
        return {
            "schema_version": 1,
            "response_kind": "ai_native_model_adapter_response",
            "adapter_contract": "provider_neutral_v1",
            "ok": False,
            "message": "Agents SDK bridge failed.",
            "adapter_name": ADAPTER_NAME,
            "reason": exc.__class__.__name__,
            "elapsed_us": int((time.perf_counter() - start) * 1_000_000),
        }

    return _sanitize_response({
        "schema_version": 1,
        "response_kind": "ai_native_model_adapter_response",
        "adapter_contract": "provider_neutral_v1",
        "ok": True,
        "message": final_output,
        "adapter_name": ADAPTER_NAME,
        "elapsed_us": int((time.perf_counter() - start) * 1_000_000),
        "response": {
            "agentic_execution": True,
            "web_search_available": WebSearchTool is not None,
            "tools_enabled": tool_power_names(),
            "tool_powers": tool_power_manifest(),
            "world_mutation_authority": "luanti",
        },
    })


def sample_request() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "request_kind": "ai_native_model_adapter_request",
        "adapter_contract": "provider_neutral_v1",
        "agent_id": "nova_agent:Example:guide",
        "owner": "Example",
        "public_prompt": "What safe AI-native runtime action should I try next?",
        "context": {
            "surface_id": "guide",
            "capabilities": "world.read,http.llm,task.cancel",
        },
        "safety": {
            "public_safe_request": True,
            "private_input_retained": False,
            "no_provider_credentials": True,
            "no_raw_media_payloads": True,
        },
        "bounds": {
            "max_response_bytes": 4000,
        },
    }


def main() -> int:
    response = run_model_adapter_request(sample_request(), force_offline=True)
    print(json.dumps(response, indent=2, sort_keys=True))
    return 0 if response.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
