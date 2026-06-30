#!/usr/bin/env python3
"""OpenAI Agents SDK bridge for Luanti's core.ai_model_ops.request contract."""

from __future__ import annotations

import asyncio
from contextvars import ContextVar
from datetime import datetime, timezone
import inspect
import json
import os
from pathlib import Path
import re
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
MAX_TOOL_TRACE_ENTRIES = 12
MAX_MEMORY_CASES = 12
BUILD_PLANNING_REQUIRED_TOOLS = (
    "recall_build_prompt_memory",
    "select_build_option",
)
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

_TOOL_TRACE: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "ai_native_luanti_agent_tool_trace",
    default=None,
)


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
        "name": "propose_build_option",
        "kind": "function_tool",
        "runtime_power": "bounded_generated_build_option",
        "read_only": True,
        "available_without_provider_credentials": True,
        "direct_world_mutation": False,
        "engine_authority": "luanti_generated_option_validator",
    },
    {
        "name": "select_build_option",
        "kind": "function_tool",
        "runtime_power": "agent_selected_build_option_validation",
        "read_only": True,
        "available_without_provider_credentials": True,
        "direct_world_mutation": False,
        "engine_authority": "luanti_task_preview_approval_rollback",
    },
    {
        "name": "recall_build_prompt_memory",
        "kind": "function_tool",
        "runtime_power": "reviewed_prompt_memory_lookup",
        "read_only": True,
        "available_without_provider_credentials": True,
        "direct_world_mutation": False,
        "engine_authority": "reviewed_eval_case_pack",
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


def _record_tool_call(name: str, args: dict[str, Any], result: dict[str, Any]) -> None:
    trace = _TOOL_TRACE.get()
    if trace is None or len(trace) >= MAX_TOOL_TRACE_ENTRIES:
        return
    trace.append({
        "tool_name": name,
        "args": _safe_log_value(args),
        "result": _safe_log_value(result),
    })


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
    result = {
        "action": action or "reply",
        "planned_node_writes": writes,
        "requires_preview": writes > 0,
        "requires_approval": writes > 0,
        "requires_rollback": writes > 0,
        "max_recommended_writes": 1000,
    }
    _record_tool_call(
        "classify_world_action",
        {"action": action, "planned_node_writes": planned_node_writes},
        result,
    )
    return result


def _candidate_entries(candidate_summary: str) -> list[dict[str, Any]]:
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
    return candidates


def _generated_build_budget(candidates: list[dict[str, Any]]) -> int:
    candidate_budget = max(
        [int(item.get("planned_node_writes") or 0) for item in candidates] + [12]
    )
    return max(1, min(32, candidate_budget))


def _bounded_generated_dims(width: int, depth_or_height: int, budget: int) -> tuple[int, int]:
    width = max(1, int(width))
    depth_or_height = max(1, int(depth_or_height))
    while width * depth_or_height > budget:
        if width >= depth_or_height and width > 1:
            width -= 1
        elif depth_or_height > 1:
            depth_or_height -= 1
        else:
            break
    return width, depth_or_height


def _first_prompt_int(pattern: str, request: str) -> int | None:
    match = re.search(pattern, request)
    if not match:
        return None
    try:
        value = int(match.group(1))
    except (TypeError, ValueError):
        return None
    return value if value >= 1 else None


def propose_build_option_payload(candidate_summary: str, player_request: str) -> dict[str, Any]:
    """Propose one generated build option for Luanti to validate, without mutating the world."""

    request = str(player_request or "").lower()
    candidates = _candidate_entries(candidate_summary)
    budget = _generated_build_budget(candidates)

    if "only a fire" in request or "fire" in request or "flame" in request:
        return {
            "status": "not_needed",
            "reason": "fixed_fire_candidate_preferred",
            "generated_option": None,
            "direct_world_mutation": False,
            "policy": "luanti_validates_generated_options_before_preview",
        }
    if "tnt" in request:
        return {
            "status": "not_needed",
            "reason": "fixed_tnt_candidate_preferred",
            "generated_option": None,
            "direct_world_mutation": False,
            "policy": "luanti_validates_generated_options_before_preview",
        }

    option: dict[str, Any] | None = None
    if "tower" in request or "tall" in request:
        width = _first_prompt_int(r"(?:width|wide)\s+(\d+)", request) or 3
        height = (
            _first_prompt_int(r"(?:height|high|tall)\s+(\d+)", request)
            or min(6, max(3, budget // max(1, width)))
        )
        width, height = _bounded_generated_dims(width, height, budget)
        option = {
            "option_id": "generated_tower_wall",
            "label": "Generated tower wall",
            "reason": "player asked for a taller build than the fixed candidates",
            "build_kind": "wall",
            "build_width": width,
            "build_height": height,
            "build_material_name": "stone",
            "planned_node_writes": width * height,
        }
    elif "bridge" in request:
        width, depth = _bounded_generated_dims(8, 2, budget)
        option = {
            "option_id": "generated_bridge_platform",
            "label": "Generated bridge platform",
            "reason": "player asked for a bridge-like surface",
            "build_kind": "platform",
            "build_width": width,
            "build_depth": depth,
            "build_material_name": "stone",
            "planned_node_writes": width * depth,
        }
    elif "road" in request or "path" in request or "walkway" in request:
        width, depth = _bounded_generated_dims(min(8, budget), 1, budget)
        option = {
            "option_id": "generated_path_platform",
            "label": "Generated path platform",
            "reason": "player asked for a path-like build",
            "build_kind": "platform",
            "build_width": width,
            "build_depth": depth,
            "build_material_name": "stone",
            "planned_node_writes": width * depth,
        }
    elif any(word in request for word in ("shelter", "house", "base", "floor", "room")):
        width, depth = _bounded_generated_dims(4, 3, budget)
        option = {
            "option_id": "generated_shelter_floor",
            "label": "Generated shelter floor",
            "reason": "player asked for a small usable footprint",
            "build_kind": "platform",
            "build_width": width,
            "build_depth": depth,
            "build_material_name": "stone",
            "planned_node_writes": width * depth,
        }

    if option is None:
        return {
            "status": "not_needed",
            "reason": "no_safe_generated_shape_matched",
            "generated_option": None,
            "direct_world_mutation": False,
            "policy": "luanti_validates_generated_options_before_preview",
        }
    return {
        "status": "ready",
        "reason": "generated_candidate_requires_luanti_validation",
        "generated_option": option,
        "candidate_count": len(candidates),
        "build_budget": budget,
        "requires_preview": True,
        "requires_approval": True,
        "requires_rollback": True,
        "direct_world_mutation": False,
        "policy": "luanti_validates_generated_options_before_preview",
    }


def _load_reviewed_case_pack() -> dict[str, Any] | None:
    path_value = os.getenv("AI_NATIVE_AGENT_CASE_PACK_PATH")
    if not path_value:
        return None
    try:
        path = Path(path_value)
        if not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("artifact_kind") != "ai_native_agent_prompt_eval_case_pack":
        return None
    return payload


def _expected_option_from_case(
    expected: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> str | None:
    expected_kind = str(expected.get("build_kind") or "")
    expected_material = str(expected.get("build_material_name") or "")
    expected_writes = expected.get("planned_node_writes")
    for candidate in candidates:
        if expected_kind and candidate.get("build_kind") != expected_kind:
            continue
        if expected_material and candidate.get("material") != expected_material:
            continue
        if expected_writes is not None and candidate.get("planned_node_writes") != expected_writes:
            continue
        return str(candidate.get("option_id") or "") or None
    return None


def select_build_option_payload(
    candidate_summary: str,
    selected_option_id: str,
    player_request: str,
    selection_reason: str = "",
) -> dict[str, Any]:
    """Validate the option id selected by the agent without mutating the world."""

    candidates = _candidate_entries(candidate_summary)
    selected_id = str(selected_option_id or "").strip()
    memory = recall_build_prompt_memory_payload(player_request, candidate_summary)
    generated = propose_build_option_payload(candidate_summary, player_request)
    generated_option = generated.get("generated_option") if isinstance(generated, dict) else None
    selected = next((item for item in candidates if item["option_id"] == selected_id), None)
    decision_source = "agent_selected_build_option"

    if selected is None and isinstance(generated_option, dict) and selected_id == generated_option.get("option_id"):
        selected = {
            "option_id": selected_id,
            "build_kind": generated_option.get("build_kind"),
            "material": generated_option.get("build_material_name") or "default",
            "planned_node_writes": generated_option.get("planned_node_writes") or 0,
        }
        decision_source = "agent_selected_generated_build_option"

    alternatives = [item["option_id"] for item in candidates[:6]]
    if isinstance(generated_option, dict):
        alternatives.append(str(generated_option.get("option_id") or "generated_agent_option"))

    if selected is None:
        return {
            "selected_option_id": None,
            "selection_status": "rejected",
            "selection_reason": _bounded_text(selection_reason, 400),
            "rejection_reason": "selected_option_not_executable",
            "candidate_count": len(candidates),
            "alternatives": alternatives,
            "decision_source": "agent_selection_rejected",
            "memory_match": memory,
            "generated_option_status": generated.get("status") if isinstance(generated, dict) else None,
            "generated_option_reason": generated.get("reason") if isinstance(generated, dict) else None,
            "generated_option": generated_option if isinstance(generated_option, dict) else None,
            "requires_preview": True,
            "requires_approval": True,
            "requires_rollback": True,
            "direct_world_mutation": False,
            "policy": "luanti_executes_only_after_player_approval",
        }

    return {
        "selected_option_id": selected["option_id"],
        "selection_status": "accepted",
        "selection_reason": _bounded_text(selection_reason, 400),
        "candidate_count": len(candidates),
        "alternatives": alternatives,
        "decision_source": decision_source,
        "memory_match": memory,
        "selected_build_kind": selected.get("build_kind"),
        "selected_material": selected.get("material"),
        "selected_planned_node_writes": selected.get("planned_node_writes"),
        "generated_option_status": generated.get("status") if isinstance(generated, dict) else None,
        "generated_option_reason": generated.get("reason") if isinstance(generated, dict) else None,
        "generated_option": generated_option
            if isinstance(generated_option, dict)
            and selected["option_id"] == generated_option.get("option_id")
            else None,
        "requires_preview": True,
        "requires_approval": True,
        "requires_rollback": True,
        "direct_world_mutation": False,
        "policy": "luanti_executes_only_after_player_approval",
    }


def recall_build_prompt_memory_payload(
    player_request: str,
    candidate_summary: str,
) -> dict[str, Any]:
    """Look up reviewed prompt-eval memory without mutating the world."""

    request = str(player_request or "").strip()
    candidates = _candidate_entries(candidate_summary)
    payload = _load_reviewed_case_pack()
    if not payload:
        return {
            "memory_available": False,
            "selected_option_id": None,
            "matched_case_id": None,
            "reviewed_case_count": 0,
            "direct_world_mutation": False,
            "policy": "reviewed_case_pack_only",
        }

    cases = payload.get("cases") if isinstance(payload.get("cases"), list) else []
    reviewed_case_count = min(len(cases), MAX_MEMORY_CASES)
    if reviewed_case_count == 0:
        return {
            "memory_available": False,
            "selected_option_id": None,
            "matched_case_id": None,
            "reviewed_case_count": 0,
            "direct_world_mutation": False,
            "policy": "reviewed_case_pack_only",
        }
    request_lower = request.lower()
    for case in cases[:MAX_MEMORY_CASES]:
        if not isinstance(case, dict):
            continue
        prompt = case.get("prompt")
        expected = case.get("expected")
        if not isinstance(prompt, str) or not isinstance(expected, dict):
            continue
        if prompt.strip().lower() != request_lower:
            continue
        selected = _expected_option_from_case(expected, candidates)
        if selected:
            return {
                "memory_available": True,
                "selected_option_id": selected,
                "matched_case_id": case.get("case_id"),
                "case_hint": case.get("case_hint"),
                "reviewed_case_count": reviewed_case_count,
                "direct_world_mutation": False,
                "policy": "reviewed_case_pack_only",
            }

    return {
        "memory_available": True,
        "selected_option_id": None,
        "matched_case_id": None,
        "reviewed_case_count": reviewed_case_count,
        "direct_world_mutation": False,
        "policy": "reviewed_case_pack_only",
    }


def recommend_build_option_payload(candidate_summary: str, player_request: str) -> dict[str, Any]:
    """Compatibility fallback that chooses one bounded build candidate for Luanti validation."""

    request = str(player_request or "").lower()
    candidates = _candidate_entries(candidate_summary)

    preferred = "platform"
    memory = recall_build_prompt_memory_payload(player_request, candidate_summary)
    memory_selected = memory.get("selected_option_id")
    generated = propose_build_option_payload(candidate_summary, player_request)
    generated_option = generated.get("generated_option") if isinstance(generated, dict) else None
    if isinstance(memory_selected, str) and memory_selected:
        preferred = memory_selected
    elif isinstance(generated_option, dict) and generated.get("status") == "ready":
        preferred = str(generated_option.get("option_id") or "generated_agent_option")
    elif "only a fire" in request:
        preferred = "fire"
    elif "tnt" in request:
        preferred = "tnt_wall"
    elif "fire" in request or "flame" in request:
        preferred = "fire"
    elif "wall" in request:
        preferred = "wall"
    elif "marker" in request or "beacon" in request:
        preferred = "marker"

    selected = next((item for item in candidates if item["option_id"] == preferred), None)
    decision_source = "agent_build_option_tool"
    if memory.get("selected_option_id"):
        decision_source = "reviewed_prompt_memory"
    elif isinstance(generated_option, dict) and selected and selected["option_id"] == generated_option.get("option_id"):
        decision_source = "generated_build_option_tool"
    elif isinstance(generated_option, dict) and preferred == generated_option.get("option_id"):
        decision_source = "generated_build_option_tool"

    if selected is None and candidates and not isinstance(generated_option, dict):
        preferred = str(candidates[0].get("option_id") or "")
    selected_result = select_build_option_payload(
        candidate_summary,
        preferred,
        player_request,
        "compatibility fallback selected an executable build option",
    )
    selected_result["decision_source"] = decision_source
    selected_result["memory_match"] = memory
    selected_result["generated_option_status"] = generated.get("status") if isinstance(generated, dict) else None
    selected_result["generated_option_reason"] = generated.get("reason") if isinstance(generated, dict) else None
    selected_result["generated_option"] = generated_option if isinstance(generated_option, dict) else None
    return {
        **selected_result,
        "memory_match": memory,
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
        decisions["build_option"]["decision_source"] = "offline_adapter_fallback"
    return decisions


def _build_option_uses_generated(tool_decisions: dict[str, Any] | None) -> bool:
    if not isinstance(tool_decisions, dict):
        return False
    build_option = tool_decisions.get("build_option")
    if not isinstance(build_option, dict):
        return False
    selected = build_option.get("selected_option_id")
    return (
        isinstance(build_option.get("generated_option"), dict)
        or build_option.get("decision_source") == "generated_build_option_tool"
        or build_option.get("decision_source") == "agent_selected_generated_build_option"
        or (isinstance(selected, str) and selected.startswith("generated_"))
    )


def _required_tool_names_for_request(
    request: dict[str, Any],
    tool_decisions: dict[str, Any] | None = None,
) -> list[str]:
    context = _safe_context(request.get("context"))
    required: list[str] = []
    if context.get("intent") == "build_planning" and context.get("candidate_summary"):
        required.extend(BUILD_PLANNING_REQUIRED_TOOLS)
        if _build_option_uses_generated(tool_decisions):
            required.append("propose_build_option")
    return required


def _tool_trace_names(tool_trace: Any) -> list[str]:
    if not isinstance(tool_trace, list):
        return []
    names: list[str] = []
    for entry in tool_trace:
        if not isinstance(entry, dict):
            continue
        name = entry.get("tool_name")
        if isinstance(name, str) and name:
            names.append(name)
    return names


def _missing_required_tool_names(
    request: dict[str, Any],
    tool_trace: Any,
    tool_decisions: dict[str, Any] | None = None,
) -> list[str]:
    required = _required_tool_names_for_request(request, tool_decisions)
    if not required:
        return []
    called = set(_tool_trace_names(tool_trace))
    return [name for name in required if name not in called]


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

    result = recommend_build_option_payload(candidate_summary, player_request)
    _record_tool_call(
        "recommend_build_option",
        {"candidate_summary": candidate_summary, "player_request": player_request},
        result,
    )
    return result


@function_tool
def propose_build_option(candidate_summary: str, player_request: str) -> dict[str, Any]:
    """Propose a generated build option that Luanti must validate before preview."""

    result = propose_build_option_payload(candidate_summary, player_request)
    _record_tool_call(
        "propose_build_option",
        {"candidate_summary": candidate_summary, "player_request": player_request},
        result,
    )
    return result


@function_tool
def select_build_option(
    candidate_summary: str,
    selected_option_id: str,
    player_request: str,
    selection_reason: str = "",
) -> dict[str, Any]:
    """Validate the build option selected by the agent without mutating the world."""

    result = select_build_option_payload(
        candidate_summary,
        selected_option_id,
        player_request,
        selection_reason,
    )
    _record_tool_call(
        "select_build_option",
        {
            "candidate_summary": candidate_summary,
            "selected_option_id": selected_option_id,
            "player_request": player_request,
            "selection_reason": selection_reason,
        },
        result,
    )
    return result


@function_tool
def recall_build_prompt_memory(player_request: str, candidate_summary: str) -> dict[str, Any]:
    """Return reviewed prompt-memory guidance for a build request, if available."""

    result = recall_build_prompt_memory_payload(player_request, candidate_summary)
    _record_tool_call(
        "recall_build_prompt_memory",
        {"player_request": player_request, "candidate_summary": candidate_summary},
        result,
    )
    return result


def build_agent(model: str | None = None) -> Any:
    if not _sdk_available():
        raise RuntimeError("openai-agents is not installed")

    tools: list[Any] = [
        summarize_runtime_capabilities,
        classify_world_action,
        recall_build_prompt_memory,
        propose_build_option,
        select_build_option,
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
            "reviewed prompt memory, generated build-option proposals, and "
            "agent-selected build-option validation. "
            "For build planning, call recall_build_prompt_memory and "
            "then choose among the listed options yourself; call "
            "propose_build_option when the listed fixed candidates are too "
            "generic for the player request, and call select_build_option "
            "with the option id you chose before producing final output. "
            "Return public-safe, bounded guidance. Do not return provider raw "
            "payloads, credentials, private prompts, private world coordinates, "
            "or asset payloads."
        ),
        tools=tools,
    )


def adapter_health() -> dict[str, Any]:
    case_pack = _load_reviewed_case_pack()
    cases = case_pack.get("cases") if isinstance(case_pack, dict) and isinstance(case_pack.get("cases"), list) else []
    return {
        "service": "ai-native-luanti-agents-sdk-model-adapter",
        "status": "ready" if _sdk_ready() else "degraded",
        "agents_sdk_available": _sdk_available(),
        "openai_api_key_present": bool(os.getenv("OPENAI_API_KEY")),
        "web_search_tool_available": WebSearchTool is not None,
        "reviewed_prompt_memory": {
            "case_pack_configured": bool(os.getenv("AI_NATIVE_AGENT_CASE_PACK_PATH")),
            "case_pack_available": case_pack is not None,
            "case_count": min(len(cases), MAX_MEMORY_CASES),
            "status": case_pack.get("status") if isinstance(case_pack, dict) else None,
        },
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
            f"planner_reason: {context.get('planner_reason', '')}",
            f"player_request: {context.get('player_request', '')}",
            f"candidate_summary: {context.get('candidate_summary', '')}",
            f"selected_candidate_id: {context.get('selected_candidate_id', '')}",
            "Return concise public-safe guidance for the player or operator. "
            "For build planning, first call recall_build_prompt_memory, then "
            "decide which executable option best matches the player request. "
            "Call propose_build_option when the fixed candidates are too "
            "generic, then call select_build_option using the exact "
            "candidate_summary, player_request, chosen option id, and a short "
            "selection reason. Generated options must be returned only through "
            "function-tool output so Luanti can validate them before preview.",
        ]
    )


def _tool_decisions_from_trace(tool_trace: list[dict[str, Any]]) -> dict[str, Any]:
    decisions: dict[str, Any] = {}
    fallback: dict[str, Any] | None = None
    for entry in tool_trace:
        result = entry.get("result")
        if entry.get("tool_name") == "select_build_option" and isinstance(result, dict):
            decisions["build_option"] = result
        elif entry.get("tool_name") == "recommend_build_option" and isinstance(result, dict):
            fallback = result
    if "build_option" not in decisions and fallback is not None:
        decisions["build_option"] = fallback
    return decisions


async def _run_sdk_agent(request: dict[str, Any], model: str | None = None) -> dict[str, Any]:
    agent = build_agent(model)
    tool_trace: list[dict[str, Any]] = []
    token = _TOOL_TRACE.set(tool_trace)
    try:
        result = Runner.run(agent, _agent_input_from_request(request))
        if inspect.isawaitable(result):
            result = await result
        return {
            "final_output": _bounded_text(getattr(result, "final_output", result), MAX_RESPONSE_BYTES),
            "tool_trace": _safe_log_value(tool_trace),
            "tool_decisions": _tool_decisions_from_trace(tool_trace),
        }
    finally:
        _TOOL_TRACE.reset(token)


def _offline_fallback(request: dict[str, Any], reason: str) -> dict[str, Any]:
    prompt = _bounded_text(request.get("public_prompt"), 400)
    tool_decisions = _tool_decisions_for_request(request)
    required_tools = _required_tool_names_for_request(request, tool_decisions)
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
            "tool_trace": [],
            "tool_decisions": tool_decisions,
            "tool_decision_source": "offline_adapter_fallback",
            "selected_option_id": _selected_option_id(tool_decisions),
            "required_tool_calls": required_tools,
            "missing_required_tool_calls": required_tools,
            "required_tool_calls_satisfied": not required_tools,
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
        agent_result = asyncio.run(_run_sdk_agent(request, model=model))
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

    tool_trace = agent_result.get("tool_trace") if isinstance(agent_result, dict) else []
    tool_decisions = agent_result.get("tool_decisions") if isinstance(agent_result, dict) else {}
    decision_source = "agents_sdk_function_tool"
    required_tools = _required_tool_names_for_request(request, tool_decisions)
    missing_required_tools = _missing_required_tool_names(request, tool_trace, tool_decisions)
    if missing_required_tools:
        fallback_decisions = _tool_decisions_for_request(request)
        if fallback_decisions:
            tool_decisions = fallback_decisions
        required_tools = _required_tool_names_for_request(request, tool_decisions)
        missing_required_tools = _missing_required_tool_names(request, tool_trace, tool_decisions)
        decision_source = "adapter_fallback_after_agent_missing_required_tool"
    elif not tool_decisions:
        tool_decisions = _tool_decisions_for_request(request)
        required_tools = _required_tool_names_for_request(request, tool_decisions)
        missing_required_tools = _missing_required_tool_names(request, tool_trace, tool_decisions)
        decision_source = "adapter_fallback_after_agent_no_tool"

    response = _sanitize_response({
        "schema_version": 1,
        "response_kind": "ai_native_model_adapter_response",
        "adapter_contract": "provider_neutral_v1",
        "ok": True,
        "message": agent_result.get("final_output") if isinstance(agent_result, dict) else "",
        "adapter_name": ADAPTER_NAME,
        "elapsed_us": int((time.perf_counter() - start) * 1_000_000),
        "response": {
            "agentic_execution": True,
            "web_search_available": WebSearchTool is not None,
            "tools_enabled": tool_power_names(),
            "tool_powers": tool_power_manifest(),
            "tool_trace": tool_trace,
            "tool_decisions": tool_decisions,
            "tool_decision_source": decision_source,
            "selected_option_id": _selected_option_id(tool_decisions),
            "required_tool_calls": required_tools,
            "missing_required_tool_calls": missing_required_tools,
            "required_tool_calls_satisfied": not missing_required_tools,
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
