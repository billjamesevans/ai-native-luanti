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
DEFAULT_MODEL_TIMEOUT_SECONDS = 18.0
ADAPTER_NAME = "openai-agents-sdk-model-adapter"
MAX_PROMPT_BYTES = 6000
MAX_RESPONSE_BYTES = 4000
MAX_LOG_STRING_BYTES = 1200
MAX_TOOL_TRACE_ENTRIES = 12
MAX_MEMORY_CASES = 12
BUILD_PLANNING_REQUIRED_TOOLS = (
    "recall_build_prompt_memory",
    "select_build_option",
    "plan_build_actions",
)
FALLBACK_AFTER_AGENT_MISSING_REQUIRED_TOOL = "adapter_fallback_after_agent_missing_required_tool"
LOCAL_AGENT_TOOL_CONTRACT_FAST_PATH = "local_agent_tool_contract_fast_path"
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
_BUILD_TOOL_STATE: ContextVar[dict[str, Any] | None] = ContextVar(
    "ai_native_luanti_agent_build_tool_state",
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
        "name": "plan_build_actions",
        "kind": "function_tool",
        "runtime_power": "build_action_workflow_planning",
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


def _current_generated_options() -> list[dict[str, Any]]:
    state = _BUILD_TOOL_STATE.get()
    if not isinstance(state, dict):
        return []
    generated_options = state.get("generated_options")
    if not isinstance(generated_options, list):
        return []
    return [option for option in generated_options if isinstance(option, dict)]


def _remember_generated_option(option: dict[str, Any] | None) -> None:
    if not isinstance(option, dict):
        return
    option_id = option.get("option_id")
    if not isinstance(option_id, str) or not option_id:
        return
    state = _BUILD_TOOL_STATE.get()
    if not isinstance(state, dict):
        state = {"generated_options": []}
        _BUILD_TOOL_STATE.set(state)
    generated_options = state.setdefault("generated_options", [])
    if not isinstance(generated_options, list):
        generated_options = []
        state["generated_options"] = generated_options
    for index, existing in enumerate(generated_options):
        if isinstance(existing, dict) and existing.get("option_id") == option_id:
            generated_options[index] = option
            return
    generated_options.append(option)


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


def model_timeout_seconds() -> float:
    try:
        timeout = float(os.getenv("AI_NATIVE_AGENT_MODEL_TIMEOUT_SECONDS", DEFAULT_MODEL_TIMEOUT_SECONDS))
    except ValueError:
        timeout = DEFAULT_MODEL_TIMEOUT_SECONDS
    return max(0.05, min(60.0, timeout))


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


def _candidate_summary_token(candidate: dict[str, Any]) -> str:
    return ":".join(
        [
            str(candidate.get("option_id") or ""),
            str(candidate.get("build_kind") or ""),
            str(candidate.get("material") or ""),
            str(candidate.get("planned_node_writes") or 0),
        ]
    )


def _resolve_candidate_option_id(candidates: list[dict[str, Any]], selected_id: str) -> str:
    cleaned = str(selected_id or "").strip()
    if not cleaned:
        return ""
    if any(candidate.get("option_id") == cleaned for candidate in candidates):
        return cleaned
    for candidate in candidates:
        if cleaned == _candidate_summary_token(candidate):
            return str(candidate.get("option_id") or "")
    return cleaned


def _has_candidate(candidates: list[dict[str, Any]], option_id: str) -> bool:
    return any(candidate.get("option_id") == option_id for candidate in candidates)


def _locked_build_option_for_request(
    player_request: str,
    candidates: list[dict[str, Any]],
) -> dict[str, Any] | None:
    request = str(player_request or "").lower()
    if not candidates:
        return None
    if (
        "only a fire" in request
        or (
            ("build a fire" in request or "build me a fire" in request)
            and "tnt" not in request
            and "wall" not in request
            and "platform" not in request
        )
    ) and _has_candidate(candidates, "fire"):
        return {
            "option_id": "fire",
            "reason": "player_request_requires_fire_only",
        }
    if "tnt" in request and "wall" in request and _has_candidate(candidates, "tnt_wall"):
        return {
            "option_id": "tnt_wall",
            "reason": "player_request_requires_tnt_wall",
        }
    return None


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


def _requested_wall_dimensions(request: str) -> tuple[int, int] | None:
    if "wall" not in request:
        return None
    width = (
        _first_prompt_int(r"(\d+)\s+(?:wide|width)", request)
        or _first_prompt_int(r"(?:width|wide)\s+(\d+)", request)
    )
    height = (
        _first_prompt_int(r"(\d+)\s+(?:high|height|tall)", request)
        or _first_prompt_int(r"(?:height|high|tall)\s+(\d+)", request)
    )
    if width is None or height is None:
        return None
    return width, height


def _positive_tool_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        value = int(value)
        return value if value >= 1 else None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            parsed = int(value)
        except ValueError:
            return None
        return parsed if parsed >= 1 else None
    return None


def _custom_generated_option_requested(*values: Any) -> bool:
    for value in values:
        if isinstance(value, str) and value.strip():
            return True
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value:
            return True
    return False


def _generated_option_response(
    *,
    status: str,
    reason: str,
    generated_option: dict[str, Any] | None,
    candidate_count: int,
    build_budget: int,
) -> dict[str, Any]:
    response = {
        "status": status,
        "reason": reason,
        "generated_option": generated_option,
        "candidate_count": candidate_count,
        "build_budget": build_budget,
        "direct_world_mutation": False,
        "policy": "luanti_validates_generated_options_before_preview",
    }
    if status == "ready":
        response.update({
            "requires_preview": True,
            "requires_approval": True,
            "requires_rollback": True,
        })
    return response


def _agent_authored_generated_option(
    candidates: list[dict[str, Any]],
    *,
    option_id: str,
    build_kind: str,
    build_material_name: str,
    build_width: Any,
    build_depth: Any,
    build_height: Any,
    build_count: Any,
    reason: str,
    label: str,
) -> dict[str, Any]:
    budget = _generated_build_budget(candidates)
    option_id = _bounded_text(option_id, 64).strip()
    if not re.match(r"^generated[\w-]*$", option_id):
        return _generated_option_response(
            status="rejected",
            reason="generated_option_id_invalid",
            generated_option=None,
            candidate_count=len(candidates),
            build_budget=budget,
        )

    kind = str(build_kind or "").strip().lower()
    if kind not in {"marker", "platform", "wall", "fire"}:
        return _generated_option_response(
            status="rejected",
            reason="generated_build_kind_unsupported",
            generated_option=None,
            candidate_count=len(candidates),
            build_budget=budget,
        )

    material = str(build_material_name or "default").strip().lower() or "default"
    if kind == "fire":
        material = "fire"
    if material not in {"default", "stone", "tnt", "fire"}:
        return _generated_option_response(
            status="rejected",
            reason="generated_build_material_unsupported",
            generated_option=None,
            candidate_count=len(candidates),
            build_budget=budget,
        )
    if material == "fire" and kind != "fire":
        return _generated_option_response(
            status="rejected",
            reason="generated_build_material_kind_mismatch",
            generated_option=None,
            candidate_count=len(candidates),
            build_budget=budget,
        )

    option: dict[str, Any] = {
        "option_id": option_id,
        "label": _bounded_text(label or "Agent-authored build option", 120),
        "reason": _bounded_text(reason or "agent-authored bounded option", 240),
        "build_kind": kind,
        "build_material_name": material,
    }
    if kind == "marker":
        planned_writes = 1
    elif kind == "platform":
        width = _positive_tool_int(build_width)
        depth = _positive_tool_int(build_depth)
        if width is None or depth is None:
            return _generated_option_response(
                status="rejected",
                reason="generated_build_dimensions_missing",
                generated_option=None,
                candidate_count=len(candidates),
                build_budget=budget,
            )
        option["build_width"] = width
        option["build_depth"] = depth
        planned_writes = width * depth
    elif kind == "wall":
        width = _positive_tool_int(build_width)
        height = _positive_tool_int(build_height)
        if width is None or height is None:
            return _generated_option_response(
                status="rejected",
                reason="generated_build_dimensions_missing",
                generated_option=None,
                candidate_count=len(candidates),
                build_budget=budget,
            )
        option["build_width"] = width
        option["build_height"] = height
        planned_writes = width * height
    else:
        count = _positive_tool_int(build_count) or 1
        option["build_count"] = count
        planned_writes = count

    if planned_writes < 1 or planned_writes > budget:
        return _generated_option_response(
            status="rejected",
            reason="generated_build_shape_out_of_bounds",
            generated_option=None,
            candidate_count=len(candidates),
            build_budget=budget,
        )
    option["planned_node_writes"] = planned_writes
    return _generated_option_response(
        status="ready",
        reason="agent_authored_generated_option_requires_luanti_validation",
        generated_option=option,
        candidate_count=len(candidates),
        build_budget=budget,
    )


def propose_build_option_payload(
    candidate_summary: str,
    player_request: str,
    option_id: str = "",
    build_kind: str = "",
    build_material_name: str = "",
    build_width: Any = 0,
    build_depth: Any = 0,
    build_height: Any = 0,
    build_count: Any = 0,
    reason: str = "",
    label: str = "",
) -> dict[str, Any]:
    """Propose one generated build option for Luanti to validate, without mutating the world."""

    request = str(player_request or "").lower()
    candidates = _candidate_entries(candidate_summary)
    budget = _generated_build_budget(candidates)
    if _custom_generated_option_requested(
        option_id,
        build_kind,
        build_material_name,
        build_width,
        build_depth,
        build_height,
        build_count,
        reason,
        label,
    ):
        return _agent_authored_generated_option(
            candidates,
            option_id=option_id,
            build_kind=build_kind,
            build_material_name=build_material_name,
            build_width=build_width,
            build_depth=build_depth,
            build_height=build_height,
            build_count=build_count,
            reason=reason,
            label=label,
        )

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
    requested_wall_dimensions = _requested_wall_dimensions(request)
    if requested_wall_dimensions is not None:
        width, height = _bounded_generated_dims(
            requested_wall_dimensions[0],
            requested_wall_dimensions[1],
            budget,
        )
        option = {
            "option_id": "generated_dimensioned_wall",
            "label": "Generated dimensioned wall",
            "reason": "player specified wall dimensions that need a generated bounded candidate",
            "build_kind": "wall",
            "build_width": width,
            "build_height": height,
            "build_material_name": "stone",
            "planned_node_writes": width * height,
        }
    elif "tower" in request or "tall" in request:
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


def _combined_generated_options(
    generated: dict[str, Any] | None,
    generated_options: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    seen: set[str] = set()
    if isinstance(generated, dict):
        option = generated.get("generated_option")
        if isinstance(option, dict):
            option_id = str(option.get("option_id") or "")
            if option_id:
                options.append(option)
                seen.add(option_id)
    for option in generated_options or []:
        if not isinstance(option, dict):
            continue
        option_id = str(option.get("option_id") or "")
        if not option_id or option_id in seen:
            continue
        options.append(option)
        seen.add(option_id)
    return options


def _generated_options_from_result(generated: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(generated, dict):
        return []
    option = generated.get("generated_option")
    return [option] if isinstance(option, dict) else []


def _find_generated_option(
    generated_options: list[dict[str, Any]],
    selected_id: str,
) -> dict[str, Any] | None:
    for option in generated_options:
        if option.get("option_id") == selected_id:
            return option
    return None


def _required_generated_option_for_request(
    player_request: str,
    generated_options: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not generated_options:
        return None
    request = str(player_request or "").lower()
    if _requested_wall_dimensions(request) is not None:
        return generated_options[0]
    if any(word in request for word in (
        "tower",
        "tall",
        "bridge",
        "road",
        "path",
        "walkway",
        "shelter",
        "house",
        "base",
        "floor",
        "room",
    )):
        return generated_options[0]
    return None


def select_build_option_payload(
    candidate_summary: str,
    selected_option_id: str,
    player_request: str,
    selection_reason: str = "",
    generated_options: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Validate the option id selected by the agent without mutating the world."""

    candidates = _candidate_entries(candidate_summary)
    selected_id = _resolve_candidate_option_id(
        candidates,
        str(selected_option_id or "").strip(),
    )
    memory = recall_build_prompt_memory_payload(player_request, candidate_summary)
    generated_requirement = propose_build_option_payload(candidate_summary, player_request)
    generated_option_list = _combined_generated_options(None, generated_options)
    generated_requirement_options = _combined_generated_options(
        generated_requirement,
        generated_options,
    )
    generated_option = _find_generated_option(generated_option_list, selected_id)
    required_generated_option = _required_generated_option_for_request(
        player_request,
        generated_requirement_options,
    )
    selected = next((item for item in candidates if item["option_id"] == selected_id), None)
    decision_source = "agent_selected_build_option"
    locked_option = _locked_build_option_for_request(player_request, candidates)

    if selected is None and isinstance(generated_option, dict):
        selected = {
            "option_id": selected_id,
            "build_kind": generated_option.get("build_kind"),
            "material": generated_option.get("build_material_name") or "default",
            "planned_node_writes": generated_option.get("planned_node_writes") or 0,
        }
        decision_source = "agent_selected_generated_build_option"

    alternatives = [item["option_id"] for item in candidates[:6]]
    for option in generated_option_list:
        alternatives.append(str(option.get("option_id") or "generated_agent_option"))
    generated_status = "ready" if isinstance(generated_option, dict) else (
        "tool_call_required"
        if isinstance(required_generated_option, dict)
        else generated_requirement.get("status") if isinstance(generated_requirement, dict) else None
    )
    generated_reason = (
        generated_option.get("reason")
        if isinstance(generated_option, dict) and generated_option.get("reason")
        else required_generated_option.get("reason")
        if isinstance(required_generated_option, dict) and required_generated_option.get("reason")
        else generated_requirement.get("reason") if isinstance(generated_requirement, dict) else None
    )

    if locked_option and selected_id != locked_option["option_id"]:
        return {
            "selected_option_id": None,
            "selection_status": "rejected",
            "selection_reason": _bounded_text(selection_reason, 400),
            "rejection_reason": "selection_violates_player_request_constraints",
            "required_option_id": locked_option["option_id"],
            "required_option_reason": locked_option["reason"],
            "candidate_count": len(candidates),
            "alternatives": alternatives,
            "decision_source": "agent_selection_rejected",
            "memory_match": memory,
            "generated_option_status": generated_status,
            "generated_option_reason": generated_reason,
            "generated_option": generated_option if isinstance(generated_option, dict) else None,
            "requires_preview": True,
            "requires_approval": True,
            "requires_rollback": True,
            "direct_world_mutation": False,
            "policy": "luanti_executes_only_after_player_approval",
        }

    if (
        isinstance(required_generated_option, dict)
        and selected_id != required_generated_option.get("option_id")
    ):
        return {
            "selected_option_id": None,
            "selection_status": "rejected",
            "selection_reason": _bounded_text(selection_reason, 400),
            "rejection_reason": "selection_violates_player_request_constraints",
            "required_option_id": required_generated_option.get("option_id"),
            "required_option_reason": "player_request_requires_generated_option",
            "candidate_count": len(candidates),
            "alternatives": alternatives,
            "decision_source": "agent_selection_rejected",
            "memory_match": memory,
            "generated_option_status": "ready",
            "generated_option_reason": required_generated_option.get("reason"),
            "generated_option": required_generated_option,
            "requires_preview": True,
            "requires_approval": True,
            "requires_rollback": True,
            "direct_world_mutation": False,
            "policy": "luanti_executes_only_after_player_approval",
        }

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
            "generated_option_status": generated_status,
            "generated_option_reason": generated_reason,
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
        "generated_option_status": generated_status,
        "generated_option_reason": generated_reason,
        "generated_option": generated_option
            if isinstance(generated_option, dict)
            else None,
        "requires_preview": True,
        "requires_approval": True,
        "requires_rollback": True,
        "direct_world_mutation": False,
        "policy": "luanti_executes_only_after_player_approval",
    }


def _selected_build_plan_entry(
    candidate_summary: str,
    player_request: str,
    selected_option_id: str,
    generated_options: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    candidates = _candidate_entries(candidate_summary)
    selected_id = _resolve_candidate_option_id(
        candidates,
        str(selected_option_id or "").strip(),
    )
    selected = next((item for item in candidates if item["option_id"] == selected_id), None)
    if selected is not None:
        return {
            "option_id": selected["option_id"],
            "build_kind": selected.get("build_kind"),
            "build_material_name": selected.get("material") or "default",
            "planned_node_writes": selected.get("planned_node_writes") or 0,
        }
    generated_option = _find_generated_option(
        _combined_generated_options(None, generated_options),
        selected_id,
    )
    if isinstance(generated_option, dict):
        return {
            "option_id": selected_id,
            "build_kind": generated_option.get("build_kind"),
            "build_material_name": generated_option.get("build_material_name") or "default",
            "planned_node_writes": generated_option.get("planned_node_writes") or 0,
        }
    return None


def plan_build_actions_payload(
    candidate_summary: str,
    player_request: str,
    selected_option_id: str,
    generated_options: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Plan the Luanti-controlled workflow for a selected build option."""

    selected = _selected_build_plan_entry(
        candidate_summary,
        player_request,
        selected_option_id,
        generated_options,
    )
    selected_id = str(selected_option_id or "").strip()
    if selected is None:
        return {
            "status": "rejected",
            "reason": "selected_option_not_executable",
            "selected_option_id": selected_id or None,
            "plan_kind": "luanti_build_action_plan_v1",
            "step_count": 0,
            "steps": [],
            "direct_world_mutation": False,
            "world_mutation_authority": "luanti",
            "policy": "luanti_executes_only_after_player_approval",
        }

    planned_writes = max(0, int(selected.get("planned_node_writes") or 0))
    build_kind = str(selected.get("build_kind") or "build")
    material = str(selected.get("build_material_name") or "default")
    steps = [
        {
            "step_id": "preview_candidate",
            "authority": "luanti",
            "description": "Create a public pending preview from the selected bounded candidate.",
            "direct_world_mutation": False,
        },
        {
            "step_id": "await_player_approval",
            "authority": "player",
            "description": "Wait for the owning player to approve or discard the pending plan.",
            "direct_world_mutation": False,
        },
        {
            "step_id": "queue_rollback_backed_build_task",
            "authority": "luanti",
            "description": "Queue the approved build through Luanti task, budget, audit, and rollback gates.",
            "planned_node_writes": planned_writes,
            "direct_world_mutation": False,
        },
        {
            "step_id": "record_improvement_evidence",
            "authority": "luanti",
            "description": "Retain public-safe trace evidence for eval and operator feedback review.",
            "direct_world_mutation": False,
        },
    ]
    return {
        "status": "ready",
        "selected_option_id": selected["option_id"],
        "build_kind": build_kind,
        "build_material_name": material,
        "planned_node_writes": planned_writes,
        "plan_kind": "luanti_build_action_plan_v1",
        "step_count": len(steps),
        "steps": steps,
        "requires_preview": planned_writes > 0,
        "requires_approval": planned_writes > 0,
        "requires_rollback": planned_writes > 0,
        "direct_world_mutation": False,
        "world_mutation_authority": "luanti",
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
        _generated_options_from_result(generated),
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
        selected = decisions["build_option"].get("selected_option_id")
        if isinstance(selected, str) and selected:
            generated_option = decisions["build_option"].get("generated_option")
            generated_options = [generated_option] if isinstance(generated_option, dict) else []
            decisions["build_action_plan"] = plan_build_actions_payload(
                str(context.get("candidate_summary") or ""),
                player_request,
                selected,
                generated_options,
            )
    return decisions


def _local_build_tool_contract_result(
    request: dict[str, Any],
    reason: str,
) -> dict[str, Any] | None:
    context = _safe_context(request.get("context"))
    if context.get("intent") != "build_planning" or not context.get("candidate_summary"):
        return None
    candidate_summary = str(context.get("candidate_summary") or "")
    player_request = str(context.get("player_request") or "").strip()
    if not player_request:
        player_request = _extract_player_request(str(request.get("public_prompt") or ""))
    if not player_request.strip() or not candidate_summary.strip():
        return None

    tool_trace: list[dict[str, Any]] = []
    memory = recall_build_prompt_memory_payload(player_request, candidate_summary)
    tool_trace.append({
        "tool_name": "recall_build_prompt_memory",
        "args": {
            "player_request": player_request,
            "candidate_summary": candidate_summary,
        },
        "result": _safe_log_value(memory),
    })

    generated = propose_build_option_payload(candidate_summary, player_request)
    generated_option = generated.get("generated_option") if isinstance(generated, dict) else None
    generated_options = [generated_option] if isinstance(generated_option, dict) else []
    selected_option_id = memory.get("selected_option_id")
    build_option_decision_source = "reviewed_prompt_memory" if selected_option_id else LOCAL_AGENT_TOOL_CONTRACT_FAST_PATH
    if not isinstance(selected_option_id, str) or not selected_option_id:
        if isinstance(generated_option, dict) and generated.get("status") == "ready":
            selected_option_id = str(generated_option.get("option_id") or "")
            build_option_decision_source = "generated_build_option_tool"
    if not selected_option_id:
        locked = _locked_build_option_for_request(player_request, _candidate_entries(candidate_summary))
        if isinstance(locked, dict):
            selected_option_id = str(locked.get("option_id") or "")
            build_option_decision_source = "player_request_constraint"
    if not selected_option_id:
        recommended = recommend_build_option_payload(candidate_summary, player_request)
        selected_option_id = str(recommended.get("selected_option_id") or "")
        build_option_decision_source = str(
            recommended.get("decision_source") or LOCAL_AGENT_TOOL_CONTRACT_FAST_PATH
        )
        recommended_generated = recommended.get("generated_option")
        if isinstance(recommended_generated, dict):
            generated_options = [recommended_generated]
            generated_option = recommended_generated
            generated = {
                "status": recommended.get("generated_option_status") or "ready",
                "reason": recommended.get("generated_option_reason"),
                "generated_option": recommended_generated,
            }
    if not selected_option_id:
        return None

    if isinstance(generated_option, dict) and (
        selected_option_id == generated_option.get("option_id")
        or str(selected_option_id).startswith("generated_")
    ):
        tool_trace.append({
            "tool_name": "propose_build_option",
            "args": {
                "candidate_summary": candidate_summary,
                "player_request": player_request,
                "option_id": generated_option.get("option_id"),
                "build_kind": generated_option.get("build_kind"),
                "build_material_name": generated_option.get("build_material_name"),
                "build_width": generated_option.get("build_width", 0),
                "build_depth": generated_option.get("build_depth", 0),
                "build_height": generated_option.get("build_height", 0),
                "build_count": generated_option.get("build_count", 0),
                "reason": generated_option.get("reason", ""),
            },
            "result": _safe_log_value(generated),
        })

    selection = select_build_option_payload(
        candidate_summary,
        selected_option_id,
        player_request,
        f"local tool contract fallback after {reason}",
        generated_options,
    )
    selection["decision_source"] = build_option_decision_source
    selection["memory_match"] = memory
    selection["generated_option_status"] = generated.get("status") if isinstance(generated, dict) else None
    selection["generated_option_reason"] = generated.get("reason") if isinstance(generated, dict) else None
    selection["generated_option"] = generated_option if isinstance(generated_option, dict) else None
    tool_trace.append({
        "tool_name": "select_build_option",
        "args": {
            "candidate_summary": candidate_summary,
            "selected_option_id": selected_option_id,
            "player_request": player_request,
            "selection_reason": f"local tool contract fallback after {reason}",
        },
        "result": _safe_log_value(selection),
    })
    if selection.get("selection_status") != "accepted":
        return None

    plan = plan_build_actions_payload(
        candidate_summary,
        player_request,
        selected_option_id,
        generated_options,
    )
    tool_trace.append({
        "tool_name": "plan_build_actions",
        "args": {
            "candidate_summary": candidate_summary,
            "player_request": player_request,
            "selected_option_id": selected_option_id,
        },
        "result": _safe_log_value(plan),
    })
    if plan.get("status") != "ready":
        return None

    return {
        "final_output": "Local tool-contract fallback selected a bounded Luanti build plan.",
        "tool_trace": _safe_log_value(tool_trace),
        "tool_decisions": {
            "build_option": selection,
            "build_action_plan": plan,
        },
        "tool_decision_source": LOCAL_AGENT_TOOL_CONTRACT_FAST_PATH,
        "local_tool_contract_reason": reason,
        "agent_model_timeout": reason == "agents_sdk_model_timeout",
    }


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


def _build_contract_failure_reason(
    request: dict[str, Any],
    tool_trace: Any,
    tool_decisions: dict[str, Any] | None,
) -> str | None:
    missing_required_tools = _missing_required_tool_names(request, tool_trace, tool_decisions)
    if missing_required_tools:
        return "agent_missing_required_tool"
    context = _safe_context(request.get("context"))
    if (
        context.get("intent") == "build_planning"
        and context.get("candidate_summary")
        and not tool_decisions
    ):
        return "agent_no_build_option"
    return _build_decision_fallback_reason(request, tool_decisions or {})


def _repair_request_for_contract_failure(
    request: dict[str, Any],
    *,
    reason: str,
    required_tools: list[str],
    missing_tools: list[str],
    model_selected_option_id: str | None,
) -> dict[str, Any]:
    context = dict(request.get("context")) if isinstance(request.get("context"), dict) else {}
    context["planner_reason"] = f"agent_repair_required:{reason}"
    prompt = _bounded_text(request.get("public_prompt"), MAX_PROMPT_BYTES)
    required = ", ".join(required_tools) if required_tools else "none"
    missing = ", ".join(missing_tools) if missing_tools else "none"
    selected = model_selected_option_id or "none"
    repair = dict(request)
    repair["context"] = context
    repair["public_prompt"] = "\n".join(
        [
            prompt,
            "",
            "Agent repair pass:",
            f"Previous pass failed build-planning contract: {reason}.",
            f"Required function tools: {required}.",
            f"Missing function tools: {missing}.",
            f"Previous selected option id: {selected}.",
            "Call the required tools in this pass before final output. "
            "For fire-only requests select fire. For TNT wall requests select "
            "tnt_wall. For generated shapes call propose_build_option before "
            "select_build_option, then call plan_build_actions.",
        ]
    )
    return repair


def _adapter_fallback_decision_source(reason: str) -> str:
    if reason == "agent_missing_required_tool":
        return FALLBACK_AFTER_AGENT_MISSING_REQUIRED_TOOL
    return f"adapter_fallback_after_{reason}"


def _selected_option_id(decisions: dict[str, Any]) -> str | None:
    build_option = decisions.get("build_option")
    if isinstance(build_option, dict):
        selected = build_option.get("selected_option_id")
        if isinstance(selected, str) and selected:
            return selected
    return None


def _model_selected_option_id(
    decisions: dict[str, Any] | None,
    tool_trace: Any,
) -> str | None:
    if isinstance(decisions, dict):
        selected = _selected_option_id(decisions)
        if selected:
            return selected
    if not isinstance(tool_trace, list):
        return None
    for entry in tool_trace:
        if not isinstance(entry, dict) or entry.get("tool_name") != "select_build_option":
            continue
        args = entry.get("args")
        if isinstance(args, dict):
            selected = args.get("selected_option_id")
            if isinstance(selected, str) and selected:
                return selected
        result = entry.get("result")
        if isinstance(result, dict):
            selected = result.get("selected_option_id")
            if isinstance(selected, str) and selected:
                return selected
    return None


def _intent_constraint_for_request(request: dict[str, Any]) -> dict[str, Any] | None:
    context = _safe_context(request.get("context"))
    if context.get("intent") != "build_planning" or not context.get("candidate_summary"):
        return None
    candidates = _candidate_entries(str(context.get("candidate_summary") or ""))
    return _locked_build_option_for_request(
        str(context.get("player_request") or ""),
        candidates,
    )


def _build_decision_fallback_reason(
    request: dict[str, Any],
    decisions: dict[str, Any] | None,
) -> str | None:
    context = _safe_context(request.get("context"))
    if context.get("intent") != "build_planning" or not context.get("candidate_summary"):
        return None
    if not isinstance(decisions, dict):
        return "agent_no_build_option"
    build_option = decisions.get("build_option")
    if not isinstance(build_option, dict):
        return "agent_no_build_option"

    candidates = _candidate_entries(str(context.get("candidate_summary") or ""))
    locked = _locked_build_option_for_request(
        str(context.get("player_request") or ""),
        candidates,
    )
    selected = build_option.get("selected_option_id")
    if build_option.get("selection_status") == "rejected" or not selected:
        return "agent_invalid_build_selection"
    if locked and selected != locked["option_id"]:
        return "agent_violated_player_request_constraints"
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
def propose_build_option(
    candidate_summary: str,
    player_request: str,
    option_id: str = "",
    build_kind: str = "",
    build_material_name: str = "",
    build_width: int = 0,
    build_depth: int = 0,
    build_height: int = 0,
    build_count: int = 0,
    reason: str = "",
    label: str = "",
) -> dict[str, Any]:
    """Propose or validate a generated build option that Luanti must validate before preview."""

    result = propose_build_option_payload(
        candidate_summary,
        player_request,
        option_id,
        build_kind,
        build_material_name,
        build_width,
        build_depth,
        build_height,
        build_count,
        reason,
        label,
    )
    if result.get("status") == "ready":
        _remember_generated_option(result.get("generated_option"))
    _record_tool_call(
        "propose_build_option",
        {
            "candidate_summary": candidate_summary,
            "player_request": player_request,
            "option_id": option_id,
            "build_kind": build_kind,
            "build_material_name": build_material_name,
            "build_width": build_width,
            "build_depth": build_depth,
            "build_height": build_height,
            "build_count": build_count,
            "reason": reason,
            "label": label,
        },
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
        _current_generated_options(),
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
def plan_build_actions(
    candidate_summary: str,
    player_request: str,
    selected_option_id: str,
) -> dict[str, Any]:
    """Plan Luanti-controlled build workflow steps for the selected option."""

    result = plan_build_actions_payload(
        candidate_summary,
        player_request,
        selected_option_id,
        _current_generated_options(),
    )
    _record_tool_call(
        "plan_build_actions",
        {
            "candidate_summary": candidate_summary,
            "player_request": player_request,
            "selected_option_id": selected_option_id,
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
        plan_build_actions,
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
            "generic for the player request. When you propose a custom "
            "bounded option, pass a generated option_id plus build_kind, "
            "material, dimensions, and reason through propose_build_option; "
            "if reviewed prompt memory suggests a generated_ option, call "
            "propose_build_option in this run to materialize the generated "
            "option before selecting it; "
            "then call select_build_option with the option id you chose. "
            "Then call plan_build_actions for that selected option before "
            "producing final output. "
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
            "generic; for custom generated options pass a generated option_id, "
            "build_kind, material, bounded dimensions, and reason. If reviewed "
            "prompt memory points at a generated_ option, call "
            "propose_build_option first to materialize that option in this "
            "tool run. Then call "
            "select_build_option using the exact candidate_summary, "
            "player_request, chosen option id, and a short selection reason. "
            "Then call plan_build_actions with the same "
            "candidate_summary, player_request, and selected option id so "
            "Luanti receives a read-only approval/task/rollback workflow plan. "
            "Generated options must be returned only through function-tool "
            "output so Luanti can validate them before preview.",
        ]
    )


def _tool_decisions_from_trace(tool_trace: list[dict[str, Any]]) -> dict[str, Any]:
    decisions: dict[str, Any] = {}
    fallback: dict[str, Any] | None = None
    for entry in tool_trace:
        result = entry.get("result")
        if entry.get("tool_name") == "select_build_option" and isinstance(result, dict):
            decisions["build_option"] = result
        elif entry.get("tool_name") == "plan_build_actions" and isinstance(result, dict):
            decisions["build_action_plan"] = result
        elif entry.get("tool_name") == "recommend_build_option" and isinstance(result, dict):
            fallback = result
    if "build_option" not in decisions and fallback is not None:
        decisions["build_option"] = fallback
    return decisions


def _build_action_plan_failure_reason(
    request: dict[str, Any],
    tool_decisions: dict[str, Any] | None,
) -> str | None:
    context = _safe_context(request.get("context"))
    if context.get("intent") != "build_planning" or not context.get("candidate_summary"):
        return None
    if not isinstance(tool_decisions, dict):
        return "agent_no_build_action_plan"
    plan = tool_decisions.get("build_action_plan")
    if not isinstance(plan, dict):
        return "agent_no_build_action_plan"
    if plan.get("status") != "ready":
        return "agent_invalid_build_action_plan"
    selected = _selected_option_id(tool_decisions)
    plan_selected = plan.get("selected_option_id")
    if isinstance(selected, str) and selected and plan_selected != selected:
        return "agent_build_action_plan_mismatched_selection"
    return None


def _agent_tool_contract_result_from_trace(
    request: dict[str, Any],
    tool_trace: list[dict[str, Any]],
    *,
    final_output: Any = "",
    agent_model_status: str = "",
) -> dict[str, Any] | None:
    context = _safe_context(request.get("context"))
    if context.get("intent") != "build_planning" or not context.get("candidate_summary"):
        return None
    tool_decisions = _tool_decisions_from_trace(tool_trace)
    if not tool_decisions:
        return None
    if _build_contract_failure_reason(request, tool_trace, tool_decisions):
        return None
    if _build_action_plan_failure_reason(request, tool_decisions):
        return None
    message = _bounded_text(final_output, MAX_RESPONSE_BYTES)
    if not message:
        selected = _selected_option_id(tool_decisions) or "selected"
        message = f"Agents SDK tool plan selected {selected} for Luanti approval."
    result = {
        "final_output": message,
        "tool_trace": _safe_log_value(tool_trace),
        "tool_decisions": tool_decisions,
        "tool_decision_source": "agents_sdk_function_tool",
    }
    if agent_model_status:
        result["agent_model_status"] = agent_model_status
    return result


async def _consume_stream_until_tool_contract_ready(
    request: dict[str, Any],
    stream_result: Any,
    tool_trace: list[dict[str, Any]],
) -> dict[str, Any] | None:
    stream_events = getattr(stream_result, "stream_events", None)
    if not callable(stream_events):
        return None
    async for _event in stream_events():
        ready = _agent_tool_contract_result_from_trace(
            request,
            tool_trace,
            agent_model_status="success_early_tool_plan",
        )
        if ready is None:
            continue
        cancel = getattr(stream_result, "cancel", None)
        if callable(cancel):
            cancel()
        return ready
    final_output = getattr(stream_result, "final_output", "")
    return _agent_tool_contract_result_from_trace(
        request,
        tool_trace,
        final_output=final_output,
        agent_model_status="success_stream_complete",
    )


async def _run_sdk_agent(request: dict[str, Any], model: str | None = None) -> dict[str, Any]:
    agent = build_agent(model)
    tool_trace: list[dict[str, Any]] = []
    token = _TOOL_TRACE.set(tool_trace)
    build_token = _BUILD_TOOL_STATE.set({"generated_options": []})
    try:
        agent_input = _agent_input_from_request(request)
        if hasattr(Runner, "run_streamed"):
            stream_result = Runner.run_streamed(agent, agent_input)
            if inspect.isawaitable(stream_result):
                stream_result = await asyncio.wait_for(
                    stream_result,
                    timeout=model_timeout_seconds(),
                )
            ready = await asyncio.wait_for(
                _consume_stream_until_tool_contract_ready(request, stream_result, tool_trace),
                timeout=model_timeout_seconds(),
            )
            if ready is not None:
                return ready
            result = stream_result
        else:
            result = Runner.run(agent, agent_input)
            if inspect.isawaitable(result):
                result = await asyncio.wait_for(result, timeout=model_timeout_seconds())
        ready = _agent_tool_contract_result_from_trace(
            request,
            tool_trace,
            final_output=getattr(result, "final_output", result),
            agent_model_status="success",
        )
        if ready is not None:
            return ready
        return {
            "final_output": _bounded_text(getattr(result, "final_output", result), MAX_RESPONSE_BYTES),
            "tool_trace": _safe_log_value(tool_trace),
            "tool_decisions": _tool_decisions_from_trace(tool_trace),
        }
    finally:
        _TOOL_TRACE.reset(token)
        _BUILD_TOOL_STATE.reset(build_token)


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
            "build_action_plan": tool_decisions.get("build_action_plan")
                if isinstance(tool_decisions, dict) else None,
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
    except asyncio.TimeoutError:
        agent_result = _local_build_tool_contract_result(request, "agents_sdk_model_timeout")
        if agent_result is None:
            response = _offline_fallback(request, "agents_sdk_model_timeout")
            response["elapsed_us"] = int((time.perf_counter() - start) * 1_000_000)
            response["response"]["tool_decision_source"] = "offline_adapter_fallback_after_agent_timeout"
            response["response"]["agent_model_timeout"] = True
            _write_request_response_log(request, response)
            return response
    except Exception as exc:  # pragma: no cover - live SDK path depends on credentials.
        agent_result = _local_build_tool_contract_result(request, exc.__class__.__name__)
        if agent_result is None:
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
    model_tool_decisions = tool_decisions if isinstance(tool_decisions, dict) else {}
    model_selected_option_id = _model_selected_option_id(model_tool_decisions, tool_trace)
    initial_model_selected_option_id = model_selected_option_id
    initial_missing_required_tools: list[str] = []
    repair_attempted = False
    repair_succeeded = False
    repair_reason: str | None = None
    decision_source = (
        agent_result.get("tool_decision_source")
        if isinstance(agent_result, dict) and isinstance(agent_result.get("tool_decision_source"), str)
        else "agents_sdk_function_tool"
    )
    required_tools = _required_tool_names_for_request(request, tool_decisions)
    missing_required_tools = _missing_required_tool_names(request, tool_trace, tool_decisions)
    repair_reason = _build_contract_failure_reason(request, tool_trace, tool_decisions)
    if repair_reason:
        initial_missing_required_tools = list(missing_required_tools)
        repair_request = _repair_request_for_contract_failure(
            request,
            reason=repair_reason,
            required_tools=required_tools,
            missing_tools=missing_required_tools,
            model_selected_option_id=model_selected_option_id,
        )
        repair_attempted = True
        try:
            repair_result = asyncio.run(_run_sdk_agent(repair_request, model=model))
        except Exception:
            repair_result = {}
        repair_trace = repair_result.get("tool_trace") if isinstance(repair_result, dict) else []
        repair_decisions = repair_result.get("tool_decisions") if isinstance(repair_result, dict) else {}
        repair_failure_reason = _build_contract_failure_reason(
            request,
            repair_trace,
            repair_decisions,
        )
        if repair_failure_reason is None:
            agent_result = repair_result
            tool_trace = repair_trace
            tool_decisions = repair_decisions
            model_tool_decisions = repair_decisions if isinstance(repair_decisions, dict) else {}
            model_selected_option_id = (
                _model_selected_option_id(model_tool_decisions, tool_trace)
                or initial_model_selected_option_id
            )
            required_tools = _required_tool_names_for_request(request, tool_decisions)
            missing_required_tools = _missing_required_tool_names(request, tool_trace, tool_decisions)
            decision_source = "agents_sdk_repair_function_tool"
            repair_succeeded = True
        else:
            repair_reason = repair_failure_reason
            tool_trace = repair_trace if repair_trace else tool_trace
            if isinstance(repair_decisions, dict) and repair_decisions:
                model_tool_decisions = repair_decisions
                model_selected_option_id = (
                    _model_selected_option_id(model_tool_decisions, tool_trace)
                    or model_selected_option_id
                )
            local_result = _local_build_tool_contract_result(
                request,
                f"agent_repair_failed:{repair_reason}",
            )
            if local_result is not None:
                agent_result = local_result
                tool_trace = local_result.get("tool_trace") if isinstance(local_result, dict) else []
                tool_decisions = local_result.get("tool_decisions") if isinstance(local_result, dict) else {}
                model_tool_decisions = tool_decisions if isinstance(tool_decisions, dict) else {}
                model_selected_option_id = (
                    model_selected_option_id
                    or _model_selected_option_id(model_tool_decisions, tool_trace)
                )
                required_tools = _required_tool_names_for_request(request, tool_decisions)
                missing_required_tools = _missing_required_tool_names(request, tool_trace, tool_decisions)
                decision_source = LOCAL_AGENT_TOOL_CONTRACT_FAST_PATH
            else:
                fallback_decisions = _tool_decisions_for_request(request)
                if fallback_decisions:
                    tool_decisions = fallback_decisions
                required_tools = _required_tool_names_for_request(request, tool_decisions)
                missing_required_tools = _missing_required_tool_names(request, tool_trace, tool_decisions)
                decision_source = _adapter_fallback_decision_source(repair_reason)

    final_selected_option_id = _selected_option_id(tool_decisions)
    intent_constraint = _intent_constraint_for_request(request)
    rejected_model_selected_option_id = None
    if (
        model_selected_option_id
        and final_selected_option_id
        and model_selected_option_id != final_selected_option_id
        and (
            decision_source.startswith("adapter_fallback_after_agent_")
            or decision_source == LOCAL_AGENT_TOOL_CONTRACT_FAST_PATH
        )
    ):
        rejected_model_selected_option_id = model_selected_option_id

    response = _sanitize_response({
        "schema_version": 1,
        "response_kind": "ai_native_model_adapter_response",
        "adapter_contract": "provider_neutral_v1",
        "ok": True,
        "message": agent_result.get("final_output") if isinstance(agent_result, dict) else "",
        "adapter_name": ADAPTER_NAME,
        "reason": agent_result.get("local_tool_contract_reason")
            if isinstance(agent_result, dict) else None,
        "elapsed_us": int((time.perf_counter() - start) * 1_000_000),
        "response": {
            "agentic_execution": True,
            "web_search_available": WebSearchTool is not None,
            "tools_enabled": tool_power_names(),
            "tool_powers": tool_power_manifest(),
            "tool_trace": tool_trace,
            "tool_decisions": tool_decisions,
            "tool_decision_source": decision_source,
            "selected_option_id": final_selected_option_id,
            "model_selected_option_id": model_selected_option_id,
            "rejected_model_selected_option_id": rejected_model_selected_option_id,
            "initial_model_selected_option_id": initial_model_selected_option_id,
            "agent_repair_attempted": repair_attempted,
            "agent_repair_succeeded": repair_succeeded,
            "agent_repair_reason": repair_reason,
            "local_tool_contract_reason": agent_result.get("local_tool_contract_reason")
                if isinstance(agent_result, dict) else None,
            "agent_model_timeout": agent_result.get("agent_model_timeout") is True
                if isinstance(agent_result, dict) else False,
            "initial_missing_required_tool_calls": initial_missing_required_tools,
            "build_action_plan": tool_decisions.get("build_action_plan")
                if isinstance(tool_decisions, dict) else None,
            "intent_constraint_option_id": intent_constraint.get("option_id")
                if isinstance(intent_constraint, dict) else None,
            "intent_constraint_reason": intent_constraint.get("reason")
                if isinstance(intent_constraint, dict) else None,
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
