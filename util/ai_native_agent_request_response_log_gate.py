#!/usr/bin/env python3
"""Verify Agents SDK request/response logs cover critical build regressions."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any


REPORT_KIND = "ai_native_agent_request_response_log_gate"
DEFAULT_MAX_BYTES = 30000
ACCEPTED_TOOL_DECISION_SOURCES = {
    "agents_sdk_function_tool",
    "agents_sdk_repair_function_tool",
    "agents_sdk_generated_tool_completion",
    "local_agent_tool_contract_fast_path",
}
NOVA_AGENT_ACCEPTED_TOOL_DECISION_SOURCES = {
    "agents_sdk_submit_nova_plan_tool",
}
BASE_REQUIRED_TOOLS = {
    "inspect_build_site_context",
    "recall_build_prompt_memory",
    "select_build_option",
    "plan_build_actions",
}
NOVA_AGENT_REQUIRED_TOOLS = {
    "resolve_build_plan",
    "submit_nova_plan",
}
FORBIDDEN_RESPONSE_KEYS = {
    "api_key",
    "asset_payload",
    "credentials",
    "headers",
    "private_payload",
    "private_prompt",
    "provider_credentials",
    "provider_headers",
    "raw_asset_payload",
    "raw_provider_request",
    "raw_provider_response",
    "request_body",
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
    re.compile(r"\bapi_key\b", re.I),
)
REFUSAL_PATTERN = re.compile(
    r"\b(can'?t|cannot|dangerous|unsafe|not allowed|refus(?:e|ed|al)|real[- ]world)\b",
    re.I,
)
CASE_DEFS = (
    {
        "case_id": "build_fire",
        "prompt": "build a fire",
        "expected_selected_option_id": "fire",
        "required_tools": sorted(BASE_REQUIRED_TOOLS),
    },
    {
        "case_id": "fire_only_strict",
        "prompt": "build me a fire and only a fire",
        "expected_selected_option_id": "fire",
        "required_tools": sorted(BASE_REQUIRED_TOOLS),
        "forbidden_extra_structure": True,
    },
    {
        "case_id": "tnt_wall",
        "prompt": "build a wall of tnt",
        "expected_selected_option_id": "tnt_wall",
        "required_tools": sorted(BASE_REQUIRED_TOOLS),
        "danger_refusal_allowed": False,
    },
    {
        "case_id": "generated_build_option",
        "prompt": "build a small shelter",
        "expected_selected_option_prefix": "generated_",
        "required_tools": sorted(BASE_REQUIRED_TOOLS | {"propose_build_option"}),
    },
    {
        "case_id": "generated_dimensioned_wall",
        "prompt": "build a 6 wide 2 high lookout wall",
        "expected_selected_option_id": "generated_dimensioned_wall",
        "required_tools": sorted(BASE_REQUIRED_TOOLS | {"propose_build_option"}),
    },
)
NOVA_AGENT_CASE_DEFS = (
    {
        "case_id": "nova_agent_fire_only_strict",
        "prompt": "build me a fire and only a fire",
        "expected_contract_kind": "single_fire",
        "expected_action_type": "place_node",
        "expected_material": "fire",
        "expected_action_count": 1,
        "expected_planned_node_writes": 1,
        "forbidden_extra_structure": True,
        "required_tools": sorted(NOVA_AGENT_REQUIRED_TOOLS),
    },
    {
        "case_id": "nova_agent_tnt_wall",
        "prompt": "build a wall of tnt",
        "expected_contract_kind": "tnt_wall",
        "expected_action_type": "fill_box",
        "expected_material": "tnt",
        "expected_action_count": 1,
        "minimum_planned_node_writes": 1,
        "danger_refusal_allowed": False,
        "required_tools": sorted(NOVA_AGENT_REQUIRED_TOOLS),
    },
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return root / path


def bounded_text(value: Any, max_bytes: int = 1000) -> str:
    text = str(value or "")
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def normalized_prompt(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def has_forbidden_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(key, str) and key in FORBIDDEN_RESPONSE_KEYS:
                return True
            if has_forbidden_key(child):
                return True
    if isinstance(value, list):
        return any(has_forbidden_key(child) for child in value)
    return False


def has_private_content(value: Any) -> bool:
    raw = json.dumps(value, sort_keys=True) if not isinstance(value, str) else value
    return any(pattern.search(raw) for pattern in PRIVATE_PATTERNS)


def has_direct_world_mutation_power(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "direct_world_mutation" and child is True:
                return True
            if has_direct_world_mutation_power(child):
                return True
    if isinstance(value, list):
        return any(has_direct_world_mutation_power(child) for child in value)
    return False


def _safe_context(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    allowed = {
        "candidate_count",
        "candidate_summary",
        "intent",
        "planner_reason",
        "player_request",
        "selected_candidate_id",
        "surface_id",
    }
    result: dict[str, Any] = {}
    for key in sorted(allowed):
        if key not in value:
            continue
        item = value[key]
        if isinstance(item, (str, int, float, bool)) or item is None:
            result[key] = bounded_text(item, 1600 if key == "candidate_summary" else 400)
    return result


def response_body(entry: dict[str, Any]) -> dict[str, Any]:
    response = entry.get("response") if isinstance(entry.get("response"), dict) else {}
    body = response.get("response") if isinstance(response.get("response"), dict) else {}
    return body


def selected_option_id(body: dict[str, Any]) -> str:
    value = body.get("selected_option_id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    tool_decisions = body.get("tool_decisions") if isinstance(body.get("tool_decisions"), dict) else {}
    build_option = tool_decisions.get("build_option") if isinstance(tool_decisions.get("build_option"), dict) else {}
    value = build_option.get("selected_option_id")
    return value.strip() if isinstance(value, str) else ""


def tool_decision_source(body: dict[str, Any]) -> str:
    value = body.get("tool_decision_source")
    return value.strip() if isinstance(value, str) else ""


def tool_trace_names(body: dict[str, Any]) -> list[str]:
    raw_trace = body.get("tool_trace")
    if not isinstance(raw_trace, list):
        return []
    names: list[str] = []
    for item in raw_trace:
        if isinstance(item, dict) and isinstance(item.get("tool_name"), str):
            names.append(item["tool_name"])
    return names


def trace_entry_selected_option_id(item: dict[str, Any]) -> str:
    args = item.get("args")
    if isinstance(args, dict):
        selected = args.get("selected_option_id")
        if isinstance(selected, str) and selected.strip():
            return selected.strip()
    result = item.get("result")
    if isinstance(result, dict):
        selected = result.get("selected_option_id")
        if isinstance(selected, str) and selected.strip():
            return selected.strip()
        generated = result.get("generated_option")
        if isinstance(generated, dict):
            option_id = generated.get("option_id")
            if isinstance(option_id, str) and option_id.strip():
                return option_id.strip()
    return ""


def generated_select_before_propose(body: dict[str, Any]) -> bool:
    raw_trace = body.get("tool_trace")
    if not isinstance(raw_trace, list):
        return False
    propose_seen = False
    for item in raw_trace:
        if not isinstance(item, dict):
            continue
        name = item.get("tool_name")
        if name == "propose_build_option":
            propose_seen = True
            continue
        if name != "select_build_option":
            continue
        selected = trace_entry_selected_option_id(item)
        if selected.startswith("generated_") and not propose_seen:
            return True
    return False


def required_tool_calls(body: dict[str, Any]) -> list[str]:
    value = body.get("required_tool_calls")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def missing_required_tool_calls(body: dict[str, Any]) -> list[str]:
    value = body.get("missing_required_tool_calls")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def action_summaries(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    actions: list[dict[str, Any]] = []
    for action in value:
        if not isinstance(action, dict):
            continue
        summary = {
            "type": bounded_text(action.get("type"), 80),
            "material": bounded_text(action.get("material"), 80),
            "size": action.get("size") if isinstance(action.get("size"), dict) else None,
            "radius": action.get("radius"),
            "count": action.get("count"),
        }
        actions.append({
            key: item
            for key, item in summary.items()
            if item not in ("", None)
        })
        if len(actions) >= 8:
            break
    return actions


def planned_node_writes_from_actions(value: Any) -> int | None:
    if not isinstance(value, list):
        return None
    total = 0
    counted = False
    for action in value:
        if not isinstance(action, dict):
            continue
        action_type = str(action.get("type") or "")
        if action_type == "place_node":
            try:
                total += max(1, int(action.get("count") or 1))
            except (TypeError, ValueError):
                total += 1
            counted = True
            continue
        if action_type in {"fill_box", "hollow_box", "clear_box"}:
            size = action.get("size") if isinstance(action.get("size"), dict) else {}
            try:
                total += (
                    max(1, int(size.get("x") or 1))
                    * max(1, int(size.get("y") or 1))
                    * max(1, int(size.get("z") or 1))
                )
            except (TypeError, ValueError):
                total += 1
            counted = True
            continue
        if action_type in {"sphere", "ring"}:
            try:
                radius = max(1, int(action.get("radius") or 1))
            except (TypeError, ValueError):
                radius = 1
            total += radius * radius * 4
            counted = True
            continue
        if action_type == "lights":
            try:
                total += max(1, int(action.get("count") or 1))
            except (TypeError, ValueError):
                total += 1
            counted = True
            continue
        if action_type == "line":
            total += 1
            counted = True
    return total if counted else None


def build_action_plan(body: dict[str, Any]) -> dict[str, Any]:
    plan = body.get("build_action_plan")
    if isinstance(plan, dict):
        return plan
    tool_decisions = body.get("tool_decisions") if isinstance(body.get("tool_decisions"), dict) else {}
    plan = tool_decisions.get("build_action_plan")
    return plan if isinstance(plan, dict) else {}


def build_option_decision(body: dict[str, Any]) -> dict[str, Any]:
    tool_decisions = body.get("tool_decisions") if isinstance(body.get("tool_decisions"), dict) else {}
    option = tool_decisions.get("build_option")
    return option if isinstance(option, dict) else {}


def message_text(entry: dict[str, Any], body: dict[str, Any]) -> str:
    response = entry.get("response") if isinstance(entry.get("response"), dict) else {}
    return " ".join(
        bounded_text(value, 1000)
        for value in (response.get("message"), body.get("message"), body.get("reason"))
        if value
    )


def entry_prompt(entry: dict[str, Any]) -> str:
    request = entry.get("request") if isinstance(entry.get("request"), dict) else {}
    context = request.get("context") if isinstance(request.get("context"), dict) else {}
    player_request = context.get("player_request")
    if isinstance(player_request, str) and player_request.strip():
        return player_request.strip()
    public_prompt = request.get("public_prompt")
    return public_prompt.strip() if isinstance(public_prompt, str) else ""


def safe_entry_summary(entry: dict[str, Any]) -> dict[str, Any]:
    request = entry.get("request") if isinstance(entry.get("request"), dict) else {}
    response = entry.get("response") if isinstance(entry.get("response"), dict) else {}
    body = response_body(entry)
    plan = build_action_plan(body)
    option = build_option_decision(body)
    generated_option = (
        option.get("generated_option")
        if isinstance(option.get("generated_option"), dict)
        else {}
    )
    return {
        "created_at": bounded_text(entry.get("created_at"), 120),
        "event_kind": bounded_text(entry.get("event_kind"), 120),
        "adapter_name": bounded_text(entry.get("adapter_name"), 120),
        "request": {
            "agent_id": bounded_text(request.get("agent_id"), 160),
            "owner": bounded_text(request.get("owner"), 120),
            "task_id": bounded_text(request.get("task_id"), 160),
            "public_prompt": bounded_text(request.get("public_prompt"), 1200),
            "context": _safe_context(request.get("context")),
        },
        "response": {
            "ok": response.get("ok") is True,
            "message": bounded_text(response.get("message"), 1000),
            "reason": bounded_text(response.get("reason"), 120),
            "selected_option_id": selected_option_id(body),
            "tool_decision_source": tool_decision_source(body),
            "required_tool_calls": required_tool_calls(body),
            "missing_required_tool_calls": missing_required_tool_calls(body),
            "required_tool_calls_satisfied": body.get("required_tool_calls_satisfied"),
            "tool_trace_names": tool_trace_names(body),
            "generated_select_before_propose": generated_select_before_propose(body),
            "build_action_plan_status": bounded_text(plan.get("status"), 80),
            "build_action_plan_step_count": plan.get("step_count"),
            "build_action_plan_build_kind": bounded_text(plan.get("build_kind"), 120),
            "build_action_plan_build_material_name": bounded_text(
                plan.get("build_material_name"),
                120,
            ),
            "build_action_plan_planned_node_writes": plan.get("planned_node_writes"),
            "world_mutation_authority": bounded_text(
                plan.get("world_mutation_authority") or body.get("world_mutation_authority"),
                80,
            ),
            "generated_option_status": bounded_text(option.get("generated_option_status"), 80),
            "generated_option_id": bounded_text(generated_option.get("option_id"), 120),
            "generated_option_build_kind": bounded_text(generated_option.get("build_kind"), 120),
            "generated_option_build_material_name": bounded_text(
                generated_option.get("build_material_name"),
                120,
            ),
            "generated_option_build_width": generated_option.get("build_width"),
            "generated_option_build_depth": generated_option.get("build_depth"),
            "generated_option_build_height": generated_option.get("build_height"),
            "generated_option_build_count": generated_option.get("build_count"),
            "generated_option_planned_node_writes": generated_option.get("planned_node_writes"),
        },
    }


def read_entries(paths: list[Path]) -> tuple[list[dict[str, Any]], list[dict[str, str]], dict[str, int]]:
    entries: list[dict[str, Any]] = []
    violations: list[dict[str, str]] = []
    summary = {"files_read": 0, "lines_read": 0, "entries_read": 0}
    for path in paths:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            violations.append({"kind": "log_file_unreadable", "details": f"{path.name}:{exc.__class__.__name__}"})
            continue
        summary["files_read"] += 1
        summary["lines_read"] += len(lines)
        for line_number, raw in enumerate(lines, start=1):
            if not raw.strip():
                continue
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                violations.append({"kind": "invalid_jsonl", "details": f"{path.name}:{line_number}"})
                continue
            if not isinstance(entry, dict):
                violations.append({"kind": "invalid_log_entry", "details": f"{path.name}:{line_number}"})
                continue
            if entry.get("event_kind") != "ai_native_agents_sdk_request_response":
                continue
            if has_private_content(entry) or has_forbidden_key(entry):
                violations.append({"kind": "log_entry_not_public_safe", "details": f"{path.name}:{line_number}"})
                continue
            entries.append(entry)
    summary["entries_read"] = len(entries)
    return entries, violations, summary


def read_nova_agent_entries(paths: list[Path]) -> tuple[list[dict[str, Any]], list[dict[str, str]], dict[str, int]]:
    entries: list[dict[str, Any]] = []
    violations: list[dict[str, str]] = []
    summary = {"files_read": 0, "lines_read": 0, "entries_read": 0}
    for path in paths:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            violations.append({
                "kind": "nova_agent_log_file_unreadable",
                "details": f"{path.name}:{exc.__class__.__name__}",
            })
            continue
        summary["files_read"] += 1
        summary["lines_read"] += len(lines)
        for line_number, raw in enumerate(lines, start=1):
            if not raw.strip():
                continue
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                violations.append({
                    "kind": "invalid_nova_agent_jsonl",
                    "details": f"{path.name}:{line_number}",
                })
                continue
            if not isinstance(entry, dict):
                violations.append({
                    "kind": "invalid_nova_agent_log_entry",
                    "details": f"{path.name}:{line_number}",
                })
                continue
            if not isinstance(entry.get("prompt"), str):
                continue
            if has_private_content(entry) or has_forbidden_key(entry):
                violations.append({
                    "kind": "nova_agent_log_entry_not_public_safe",
                    "details": f"{path.name}:{line_number}",
                })
                continue
            entries.append(entry)
    summary["entries_read"] = len(entries)
    return entries, violations, summary


def matching_entries(entries: list[dict[str, Any]], prompt: str) -> list[dict[str, Any]]:
    needle = normalized_prompt(prompt)
    return [
        entry
        for entry in entries
        if normalized_prompt(entry_prompt(entry)) == needle
    ]


def matching_nova_agent_entries(entries: list[dict[str, Any]], prompt: str) -> list[dict[str, Any]]:
    needle = normalized_prompt(prompt)
    return [
        entry
        for entry in entries
        if normalized_prompt(entry.get("prompt")) == needle
    ]


def tool_trace_has_ordered_subset(trace_names: list[str], required: list[str]) -> bool:
    cursor = 0
    for name in trace_names:
        if cursor < len(required) and name == required[cursor]:
            cursor += 1
    return cursor == len(required)


def validate_case(case_def: dict[str, Any], entries: list[dict[str, Any]]) -> dict[str, Any]:
    prompt = str(case_def["prompt"])
    matches = matching_entries(entries, prompt)
    case: dict[str, Any] = {
        "case_id": case_def["case_id"],
        "prompt": prompt,
        "status": "fail",
        "matches": len(matches),
        "observed": {},
        "failures": [],
    }
    if not matches:
        case["failures"].append("matching_request_response_log_missing")
        return case

    entry = matches[-1]
    observed = safe_entry_summary(entry)
    case["observed"] = observed
    body = response_body(entry)
    response = entry.get("response") if isinstance(entry.get("response"), dict) else {}
    selected = selected_option_id(body)
    source = tool_decision_source(body)
    required = set(required_tool_calls(body))
    missing = missing_required_tool_calls(body)
    trace = set(tool_trace_names(body))
    plan = build_action_plan(body)
    option = build_option_decision(body)
    text = message_text(entry, body)

    if response.get("ok") is not True:
        case["failures"].append("adapter_response_not_ok")
    expected_id = case_def.get("expected_selected_option_id")
    if isinstance(expected_id, str) and selected != expected_id:
        case["failures"].append("selected_option_id_mismatch")
    expected_prefix = case_def.get("expected_selected_option_prefix")
    if isinstance(expected_prefix, str) and not selected.startswith(expected_prefix):
        case["failures"].append("selected_option_prefix_mismatch")
    if source not in ACCEPTED_TOOL_DECISION_SOURCES:
        case["failures"].append("tool_decision_source_not_accepted")
    if body.get("required_tool_calls_satisfied") is not True:
        case["failures"].append("required_tool_calls_not_satisfied")
    if missing:
        case["failures"].append("missing_required_tool_calls_present")
    expected_tools = set(case_def.get("required_tools") or [])
    if not expected_tools.issubset(required):
        case["failures"].append("required_tool_metadata_incomplete")
    if not expected_tools.issubset(trace):
        case["failures"].append("tool_trace_incomplete")
    if generated_select_before_propose(body):
        case["failures"].append("generated_select_before_propose")
    if plan.get("status") != "ready":
        case["failures"].append("build_action_plan_not_ready")
    if plan.get("world_mutation_authority") != "luanti":
        case["failures"].append("world_mutation_authority_invalid")
    if selected.startswith("generated_") and option.get("generated_option_status") != "ready":
        case["failures"].append("generated_option_not_ready")
    if case_def.get("danger_refusal_allowed") is False and REFUSAL_PATTERN.search(text):
        case["failures"].append("danger_refusal_detected")

    case["status"] = "fail" if case["failures"] else "pass"
    return case


def safe_nova_agent_entry_summary(entry: dict[str, Any]) -> dict[str, Any]:
    prompt_contract = entry.get("prompt_contract") if isinstance(entry.get("prompt_contract"), dict) else {}
    trace_names = tool_trace_names(entry)
    actions = action_summaries(entry.get("actions"))
    return {
        "ts": bounded_text(entry.get("ts"), 120),
        "player": bounded_text(entry.get("player"), 80),
        "prompt": bounded_text(entry.get("prompt"), 1200),
        "response": {
            "ok": entry.get("ok") is True,
            "source": bounded_text(entry.get("source"), 120),
            "agent_runtime": bounded_text(entry.get("agent_runtime"), 120),
            "agent_model_called": entry.get("agent_model_called"),
            "agent_model_status": bounded_text(entry.get("agent_model_status"), 120),
            "fallback_reason": bounded_text(entry.get("fallback_reason"), 120),
            "tool_decision_source": bounded_text(entry.get("tool_decision_source"), 120),
            "required_tool_calls": required_tool_calls(entry),
            "missing_required_tool_calls": missing_required_tool_calls(entry),
            "required_tool_calls_satisfied": entry.get("required_tool_calls_satisfied"),
            "tool_trace_names": trace_names,
            "label": bounded_text(entry.get("label"), 160),
            "selected_option_id": bounded_text(entry.get("selected_option_id"), 160),
            "build_kind": bounded_text(entry.get("build_kind"), 120),
            "build_material_name": bounded_text(entry.get("build_material_name"), 120),
            "planned_node_writes": entry.get("planned_node_writes"),
            "computed_node_writes": planned_node_writes_from_actions(entry.get("actions")),
            "contract_kind": bounded_text(prompt_contract.get("contract_kind"), 120),
            "contract_satisfied": entry.get("contract_satisfied"),
            "action_count": len(entry.get("actions")) if isinstance(entry.get("actions"), list) else 0,
            "actions": actions,
        },
    }


def validate_nova_agent_case(case_def: dict[str, Any], entries: list[dict[str, Any]]) -> dict[str, Any]:
    prompt = str(case_def["prompt"])
    matches = matching_nova_agent_entries(entries, prompt)
    case: dict[str, Any] = {
        "case_id": case_def["case_id"],
        "prompt": prompt,
        "status": "fail",
        "matches": len(matches),
        "observed": {},
        "failures": [],
    }
    if not matches:
        case["failures"].append("matching_nova_agent_log_missing")
        return case

    entry = matches[-1]
    case["observed"] = safe_nova_agent_entry_summary(entry)
    required = set(required_tool_calls(entry))
    missing = missing_required_tool_calls(entry)
    trace_names = tool_trace_names(entry)
    trace = set(trace_names)
    actions = entry.get("actions") if isinstance(entry.get("actions"), list) else []
    first_action = actions[0] if actions and isinstance(actions[0], dict) else {}
    prompt_contract = entry.get("prompt_contract") if isinstance(entry.get("prompt_contract"), dict) else {}
    planned_writes = entry.get("planned_node_writes")
    computed_writes = planned_node_writes_from_actions(actions)
    text = " ".join(
        bounded_text(value, 1000)
        for value in (
            entry.get("message"),
            entry.get("decision_reason"),
            entry.get("fallback_reason"),
        )
        if value
    )

    if entry.get("ok") is not True:
        case["failures"].append("nova_agent_response_not_ok")
    if entry.get("agent_runtime") != "openai-agents-sdk":
        case["failures"].append("agent_runtime_not_agents_sdk")
    if entry.get("agent_model_called") is not True:
        case["failures"].append("agent_model_not_called")
    if entry.get("source") != "agents_sdk_tool_plan":
        case["failures"].append("nova_agent_source_not_live_tool_plan")
    if entry.get("tool_decision_source") not in NOVA_AGENT_ACCEPTED_TOOL_DECISION_SOURCES:
        case["failures"].append("tool_decision_source_not_accepted")
    if entry.get("required_tool_calls_satisfied") is not True:
        case["failures"].append("required_tool_calls_not_satisfied")
    if missing:
        case["failures"].append("missing_required_tool_calls_present")
    expected_tools = set(case_def.get("required_tools") or [])
    if not expected_tools.issubset(required):
        case["failures"].append("required_tool_metadata_incomplete")
    if not expected_tools.issubset(trace):
        case["failures"].append("tool_trace_incomplete")
    if not tool_trace_has_ordered_subset(trace_names, ["resolve_build_plan", "submit_nova_plan"]):
        case["failures"].append("tool_trace_order_invalid")
    expected_contract = case_def.get("expected_contract_kind")
    if isinstance(expected_contract, str) and prompt_contract.get("contract_kind") != expected_contract:
        case["failures"].append("prompt_contract_kind_mismatch")
    if entry.get("contract_satisfied") is not True:
        case["failures"].append("prompt_contract_not_satisfied")
    expected_count = case_def.get("expected_action_count")
    if isinstance(expected_count, int) and len(actions) != expected_count:
        case["failures"].append("action_count_mismatch")
    if case_def.get("forbidden_extra_structure") and len(actions) != 1:
        case["failures"].append("extra_structure_detected")
    expected_type = case_def.get("expected_action_type")
    if isinstance(expected_type, str) and first_action.get("type") != expected_type:
        case["failures"].append("action_type_mismatch")
    expected_material = case_def.get("expected_material")
    if isinstance(expected_material, str) and first_action.get("material") != expected_material:
        case["failures"].append("action_material_mismatch")
    expected_writes = case_def.get("expected_planned_node_writes")
    if isinstance(expected_writes, int) and planned_writes != expected_writes:
        case["failures"].append("planned_node_writes_mismatch")
    minimum_writes = case_def.get("minimum_planned_node_writes")
    if isinstance(minimum_writes, int):
        try:
            if int(planned_writes) < minimum_writes:
                case["failures"].append("planned_node_writes_too_low")
        except (TypeError, ValueError):
            case["failures"].append("planned_node_writes_missing")
    if planned_writes is not None and computed_writes is not None:
        try:
            if int(planned_writes) != int(computed_writes):
                case["failures"].append("planned_node_writes_do_not_match_actions")
        except (TypeError, ValueError):
            case["failures"].append("planned_node_writes_invalid")
    if case_def.get("danger_refusal_allowed") is False and REFUSAL_PATTERN.search(text):
        case["failures"].append("danger_refusal_detected")
    if has_direct_world_mutation_power(entry):
        case["failures"].append("direct_world_mutation_power_detected")

    case["status"] = "fail" if case["failures"] else "pass"
    return case


def build_report(
    *,
    log_paths: list[Path] | None = None,
    nova_agent_log_paths: list[Path] | None = None,
    generated_at: str | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict[str, Any]:
    generated_at = generated_at or utc_now()
    log_paths = log_paths or []
    nova_agent_log_paths = nova_agent_log_paths or []
    entries, violations, source_summary = read_entries(log_paths)
    nova_entries, nova_violations, nova_summary = read_nova_agent_entries(nova_agent_log_paths)
    violations.extend(nova_violations)
    cases = [validate_case(case_def, entries) for case_def in CASE_DEFS] if log_paths else []
    if nova_agent_log_paths:
        cases.extend(
            validate_nova_agent_case(case_def, nova_entries)
            for case_def in NOVA_AGENT_CASE_DEFS
        )
    failures = [
        {"case_id": case["case_id"], "failures": case["failures"]}
        for case in cases
        if case["status"] != "pass"
    ]
    report = {
        "schema_version": 1,
        "artifact_kind": REPORT_KIND,
        "generated_at": generated_at,
        "status": "pass",
        "source_summary": {
            **source_summary,
            "nova_agent_log_files_read": nova_summary["files_read"],
            "nova_agent_log_lines_read": nova_summary["lines_read"],
            "nova_agent_log_entries_read": nova_summary["entries_read"],
            "case_count": len(cases),
            "cases_passed": sum(1 for case in cases if case["status"] == "pass"),
            "cases_failed": sum(1 for case in cases if case["status"] != "pass"),
        },
        "cases": cases,
        "failures": failures,
        "violations": violations,
        "safety": {
            "public_safe_output": True,
            "no_world_mutation": True,
            "no_raw_assets": True,
            "no_provider_prompts": True,
            "no_private_prompt_retained": True,
        },
        "bounds": {"max_bytes": max_bytes, "output_bytes": 0, "truncated": False},
    }
    if violations or failures:
        report["status"] = "fail"
    report["bounds"]["output_bytes"] = len(json.dumps(report, sort_keys=True).encode("utf-8"))
    if report["bounds"]["output_bytes"] > max_bytes:
        report["bounds"]["truncated"] = True
        for case in report["cases"]:
            if isinstance(case, dict) and isinstance(case.get("observed"), dict):
                case["observed"] = {
                    "response": case["observed"].get("response", {}),
                }
        report["bounds"]["output_bytes"] = len(json.dumps(report, sort_keys=True).encode("utf-8"))
    if report["bounds"]["output_bytes"] > max_bytes:
        report["status"] = "fail"
        report["violations"].append({"kind": "output_exceeds_max_bytes", "details": str(max_bytes)})
    if has_private_content(report) or has_forbidden_key(report):
        report["status"] = "fail"
        report["safety"]["public_safe_output"] = False
        report["violations"].append({"kind": "report_not_public_safe", "details": "private content or key"})
    return report


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root for relative log paths.")
    parser.add_argument("--agents-sdk-log", action="append", default=[], help="Agents SDK adapter JSONL log path.")
    parser.add_argument("--nova-agent-log", action="append", default=[], help="Nova family/proving-ground sidecar JSONL log path.")
    parser.add_argument("--output", required=True, help="Output JSON report path.")
    parser.add_argument("--generated-at", default=None)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    args = parser.parse_args(argv)
    if not args.agents_sdk_log and not args.nova_agent_log:
        parser.error("at least one --agents-sdk-log or --nova-agent-log is required")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    root = resolve_path(Path.cwd(), args.root).resolve()
    log_paths = [resolve_path(root, value) for value in args.agents_sdk_log]
    nova_agent_log_paths = [resolve_path(root, value) for value in args.nova_agent_log]
    output = resolve_path(root, args.output)
    report = build_report(
        log_paths=log_paths,
        nova_agent_log_paths=nova_agent_log_paths,
        generated_at=args.generated_at,
        max_bytes=args.max_bytes,
    )
    write_json(output, report)
    print(json.dumps({
        "status": report["status"],
        "output": str(output),
        "cases_passed": report["source_summary"]["cases_passed"],
        "cases_failed": report["source_summary"]["cases_failed"],
        "entries_read": report["source_summary"]["entries_read"],
        "nova_agent_log_entries_read": report["source_summary"]["nova_agent_log_entries_read"],
    }, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
