#!/usr/bin/env python3
"""OpenAI Agents SDK bridge for Luanti's core.ai_model_ops.request contract."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import inspect
import json
import os
from pathlib import Path
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
MAX_LOG_STRING_BYTES = 1200
FORBIDDEN_RESPONSE_KEYS = {
    "raw_provider_request",
    "raw_provider_response",
    "provider_headers",
    "credentials",
    "private_payload",
    "private_prompt",
    "asset_payload",
    "raw_asset_payload",
    "provider_credentials",
    "api_key",
    "requires_openai_api_key",
    "headers",
    "request_body",
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
        "name": "recommend_build_option",
        "kind": "function_tool",
        "runtime_power": "build_option_recommendation",
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


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_log_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 6:
        return "<truncated>"
    if isinstance(value, str):
        return _bounded_text(value, MAX_LOG_STRING_BYTES).replace(
            "OPENAI_API_KEY", "<redacted-secret-env>"
        )
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_safe_log_value(item, depth=depth + 1) for item in value[:16]]
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, child in value.items():
            if len(safe) >= 32:
                break
            if not isinstance(key, str) or key in FORBIDDEN_RESPONSE_KEYS:
                continue
            safe[key] = _safe_log_value(child, depth=depth + 1)
        return safe
    return _bounded_text(value, MAX_LOG_STRING_BYTES)


def _public_log_request(request: dict[str, Any]) -> dict[str, Any]:
    context = _safe_context(request.get("context"))
    return {
        "request_kind": request.get("request_kind"),
        "adapter_contract": request.get("adapter_contract"),
        "agent_id": request.get("agent_id"),
        "owner": request.get("owner"),
        "task_id": request.get("task_id"),
        "public_prompt": _bounded_text(request.get("public_prompt"), MAX_LOG_STRING_BYTES),
        "context": _safe_log_value(context),
        "safety": _safe_log_value(request.get("safety")),
        "bounds": _safe_log_value(request.get("bounds")),
    }


def _public_log_response(response: dict[str, Any]) -> dict[str, Any]:
    return _safe_log_value({
        "response_kind": response.get("response_kind"),
        "adapter_contract": response.get("adapter_contract"),
        "ok": response.get("ok"),
        "message": response.get("message"),
        "adapter_name": response.get("adapter_name"),
        "reason": response.get("reason"),
        "elapsed_us": response.get("elapsed_us"),
        "response": response.get("response"),
    })


def _write_request_response_log(request: dict[str, Any], response: dict[str, Any]) -> None:
    log_path = os.getenv("AI_NATIVE_AGENT_LOG_PATH")
    if not log_path:
        return
    entry = {
        "schema_version": 1,
        "event_kind": "ai_native_agents_sdk_request_response",
        "created_at": _utc_now(),
        "adapter_name": ADAPTER_NAME,
        "request": _public_log_request(request),
        "response": _public_log_response(response),
    }
    try:
        path = Path(log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
    except OSError:
        return


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


def recommend_build_option_payload(candidate_summary: str, player_request: str) -> dict[str, Any]:
    """Choose one bounded build candidate from Luanti's public-safe summary."""

    request = str(player_request or "").lower()
    candidates: list[dict[str, Any]] = []
    for raw_entry in str(candidate_summary or "").split("|"):
        parts = raw_entry.split(":")
        if len(parts) != 4:
            continue
        option_id, build_kind, material, writes = parts
        try:
            planned_node_writes = max(0, int(writes))
        except ValueError:
            planned_node_writes = 0
        candidates.append(
            {
                "option_id": option_id,
                "build_kind": build_kind,
                "material": material,
                "planned_node_writes": planned_node_writes,
            }
        )

    preferred = "platform"
    if "tnt" in request:
        preferred = "tnt_wall"
    elif "fire" in request or "flame" in request:
        preferred = "fire"
    elif "wall" in request:
        preferred = "wall"
    elif "marker" in request or "beacon" in request:
        preferred = "marker"

    selected = next((item for item in candidates if item["option_id"] == preferred), None)
    if selected is None and candidates:
        selected = candidates[0]
    return {
        "selected_option_id": selected["option_id"] if selected else None,
        "candidate_count": len(candidates),
        "alternatives": [item["option_id"] for item in candidates[:6]],
        "requires_preview": True,
        "requires_approval": True,
        "requires_rollback": True,
        "direct_world_mutation": False,
        "policy": "luanti_executes_only_after_player_approval",
    }


def _extract_player_request(public_prompt: str) -> str:
    for line in str(public_prompt or "").splitlines():
        if line.lower().startswith("player request:"):
            return line.split(":", 1)[1].strip()
    return str(public_prompt or "")


def _tool_decisions_for_request(request: dict[str, Any]) -> dict[str, Any]:
    context = _safe_context(request.get("context"))
    decisions: dict[str, Any] = {}
    if context.get("intent") == "build_planning" and context.get("candidate_summary"):
        player_request = str(context.get("player_request") or "").strip()
        if not player_request:
            player_request = _extract_player_request(str(request.get("public_prompt") or ""))
        decisions["build_option"] = recommend_build_option_payload(
            str(context.get("candidate_summary") or ""),
            player_request,
        )
    return decisions


def _selected_option_id(decisions: dict[str, Any]) -> str | None:
    build_option = decisions.get("build_option")
    if isinstance(build_option, dict):
        selected = build_option.get("selected_option_id")
        if isinstance(selected, str) and selected:
            return selected
    return None


@function_tool
def recommend_build_option(candidate_summary: str, player_request: str) -> dict[str, Any]:
    """Recommend one of Luanti's bounded build candidates without mutating the world."""

    return recommend_build_option_payload(candidate_summary, player_request)


def build_agent(model: str | None = None) -> Any:
    if not _sdk_available():
        raise RuntimeError("openai-agents is not installed")

    tools: list[Any] = [
        summarize_runtime_capabilities,
        classify_world_action,
        recommend_build_option,
    ]
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
            "function tools to classify capabilities, world-action policy, "
            "and bounded build-option recommendations. "
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
    tool_decisions = _tool_decisions_for_request(request)
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
            f"planner_reason: {context.get('planner_reason', '')}",
            f"player_request: {context.get('player_request', '')}",
            f"candidate_summary: {context.get('candidate_summary', '')}",
            f"selected_candidate_id: {context.get('selected_candidate_id', '')}",
            f"tool_decision_recommendation: {json.dumps(tool_decisions, sort_keys=True)}",
            "Return concise public-safe guidance for the player or operator. "
            "For build planning, use the recommend_build_option decision and "
            "do not invent options that are not in candidate_summary.",
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
    tool_decisions = _tool_decisions_for_request(request)
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
            "tool_decisions": tool_decisions,
            "selected_option_id": _selected_option_id(tool_decisions),
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
        response = {
            "schema_version": 1,
            "response_kind": "ai_native_model_adapter_response",
            "adapter_contract": "provider_neutral_v1",
            "ok": False,
            "message": "Invalid model adapter request.",
            "adapter_name": ADAPTER_NAME,
            "reason": "invalid_request_kind",
        }
        _write_request_response_log(request, response)
        return response

    if force_offline or not _sdk_ready():
        reason = "forced_offline" if force_offline else "agents_sdk_not_ready"
        response = _offline_fallback(request, reason)
        response["elapsed_us"] = int((time.perf_counter() - start) * 1_000_000)
        _write_request_response_log(request, response)
        return response

    try:
        tool_decisions = _tool_decisions_for_request(request)
        final_output = asyncio.run(_run_sdk_agent(request, model=model))
    except Exception as exc:  # pragma: no cover - live SDK path depends on credentials.
        response = {
            "schema_version": 1,
            "response_kind": "ai_native_model_adapter_response",
            "adapter_contract": "provider_neutral_v1",
            "ok": False,
            "message": "Agents SDK bridge failed.",
            "adapter_name": ADAPTER_NAME,
            "reason": exc.__class__.__name__,
            "elapsed_us": int((time.perf_counter() - start) * 1_000_000),
        }
        _write_request_response_log(request, response)
        return response

    response = _sanitize_response({
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
            "tool_decisions": tool_decisions,
            "selected_option_id": _selected_option_id(tool_decisions),
            "world_mutation_authority": "luanti",
        },
    })
    _write_request_response_log(request, response)
    return response


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
