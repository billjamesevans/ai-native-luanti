#!/usr/bin/env python3
"""Build a public-safe eval candidate queue from live Nova/Agents logs."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_KIND = "ai_native_agent_eval_candidate_queue"
DEFAULT_MAX_BYTES = 32000
DEFAULT_MAX_CANDIDATES = 50

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


FORBIDDEN_KEYS = {
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


def has_private_content(value: Any) -> bool:
    raw = json.dumps(value, sort_keys=True) if not isinstance(value, str) else value
    return any(pattern.search(raw) for pattern in PRIVATE_PATTERNS)


def has_forbidden_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(key, str) and key in FORBIDDEN_KEYS:
                return True
            if has_forbidden_key(child):
                return True
    if isinstance(value, list):
        return any(has_forbidden_key(child) for child in value)
    return False


def safe_scalar(value: Any, max_bytes: int = 1000) -> str | int | float | bool | None:
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return bounded_text(value, max_bytes)


def safe_string_list(value: Any, *, max_items: int = 8, max_bytes: int = 80) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        bounded_text(item, max_bytes)
        for item in value
        if isinstance(item, str)
    ][:max_items]


def stable_candidate_id(candidate: dict[str, Any]) -> str:
    seed = {
        "source_kind": candidate.get("source_kind"),
        "observed_at": candidate.get("observed_at"),
        "owner": candidate.get("owner"),
        "agent_id": candidate.get("agent_id"),
        "task_id": candidate.get("task_id"),
        "prompt": candidate.get("prompt"),
        "route": candidate.get("route"),
        "action": candidate.get("action"),
        "status": candidate.get("observed_status"),
        "reason": candidate.get("observed_reason"),
    }
    digest = hashlib.sha256(json.dumps(seed, sort_keys=True).encode("utf-8")).hexdigest()
    return f"agent-eval-candidate:{digest[:16]}"


def expected_outcome_for(prompt: str, candidate: dict[str, Any]) -> dict[str, Any]:
    lower = prompt.lower()
    observed = candidate.get("observed") if isinstance(candidate.get("observed"), dict) else {}
    route = candidate.get("route") or observed.get("route")

    if "fire" in lower and "only" in lower:
        return {
            "case_hint": "fire_only_strict",
            "ready_for_prompt_eval": True,
            "review_status": "candidate_ready",
            "expected": {
                "action": "build",
                "build_kind": "fire",
                "build_material_name": "fire",
                "planned_node_writes": 1,
                "route": "deterministic_build_parser",
                "forbidden_extra_structure": True,
            },
        }
    if "wall" in lower and "tnt" in lower:
        return {
            "case_hint": "tnt_wall",
            "ready_for_prompt_eval": True,
            "review_status": "candidate_ready",
            "expected": {
                "action": "build",
                "build_kind": "wall",
                "build_material_name": "tnt",
                "planned_node_writes": 12,
                "danger_refusal_allowed": False,
            },
        }
    if "fire" in lower:
        return {
            "case_hint": "build_fire",
            "ready_for_prompt_eval": True,
            "review_status": "candidate_ready",
            "expected": {
                "action": "build",
                "build_kind": "fire",
                "build_material_name": "fire",
                "planned_node_writes": 1,
            },
        }
    if route == "agentic_build_planner":
        return {
            "case_hint": "agentic_build_planner_review",
            "ready_for_prompt_eval": False,
            "review_status": "needs_operator_label",
            "expected": {
                "action": "build",
                "route": "agentic_build_planner",
                "operator_must_label_expected_build": True,
            },
        }
    if candidate.get("source_kind") == "agents_sdk_request_response":
        return {
            "case_hint": "model_adapter_review",
            "ready_for_prompt_eval": False,
            "review_status": "needs_operator_label",
            "expected": {
                "response_kind": "ai_native_model_adapter_response",
                "world_mutation_authority": "luanti",
                "operator_must_label_expected_answer": True,
            },
        }
    return {
        "case_hint": "manual_review",
        "ready_for_prompt_eval": False,
        "review_status": "needs_operator_label",
        "expected": {"operator_must_label_expected_behavior": True},
    }


def adapter_tool_contract_for(candidate: dict[str, Any]) -> dict[str, Any] | None:
    observed = candidate.get("observed") if isinstance(candidate.get("observed"), dict) else {}
    required = safe_string_list(
        observed.get("required_tool_calls") or observed.get("adapter_required_tool_calls")
    )
    missing = safe_string_list(
        observed.get("missing_required_tool_calls") or observed.get("adapter_missing_required_tool_calls")
    )
    satisfied = observed.get("required_tool_calls_satisfied")
    if satisfied is None:
        satisfied = observed.get("adapter_required_tool_calls_satisfied")
    decision_source = observed.get("tool_decision_source") or observed.get("adapter_tool_decision_source")
    if not required and not missing and satisfied is None and not decision_source:
        return None

    status = "unknown"
    if satisfied is True and not missing:
        status = "pass"
    if satisfied is False or missing or decision_source == "adapter_fallback_after_agent_missing_required_tool":
        status = "fail"

    return {
        "status": status,
        "required_tool_calls": required,
        "missing_required_tool_calls": missing,
        "required_tool_calls_satisfied": satisfied,
        "tool_decision_source": safe_scalar(decision_source),
        "ready_for_adapter_contract_eval": status == "fail",
        "expected": {
            "required_tool_calls": required,
            "missing_required_tool_calls": [],
            "required_tool_calls_satisfied": True,
            "tool_decision_source": "agents_sdk_function_tool",
        },
    }


def finalize_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    expected = expected_outcome_for(candidate["prompt"], candidate)
    candidate.update({
        "candidate_id": stable_candidate_id(candidate),
        "priority": candidate_priority(candidate, expected),
        **expected,
    })
    tool_contract = adapter_tool_contract_for(candidate)
    if tool_contract:
        candidate["adapter_tool_contract"] = tool_contract
        candidate["ready_for_adapter_contract_eval"] = tool_contract.get("ready_for_adapter_contract_eval") is True
        candidate["adapter_contract_review_status"] = (
            "adapter_contract_candidate_ready"
            if tool_contract.get("ready_for_adapter_contract_eval") is True
            else "adapter_contract_observed"
        )
        if tool_contract.get("status") == "fail":
            candidate["priority"] = "high"
    else:
        candidate["ready_for_adapter_contract_eval"] = False
    return candidate


def candidate_priority(candidate: dict[str, Any], expected: dict[str, Any]) -> str:
    status = str(candidate.get("observed_status") or "").lower()
    reason = str(candidate.get("observed_reason") or "").lower()
    if expected.get("ready_for_prompt_eval") is True:
        return "high"
    if status in {"blocked", "failed", "unsafe", "error"} or reason:
        return "high"
    if candidate.get("observed_ok") is False:
        return "high"
    return "normal"


def _base_candidate(source_kind: str, observed_at: str | None, prompt: str) -> dict[str, Any]:
    return {
        "source_kind": source_kind,
        "observed_at": observed_at,
        "prompt": bounded_text(prompt, 1000),
    }


def _agents_sdk_candidate_prompt(request: dict[str, Any]) -> tuple[str | None, str]:
    context = request.get("context") if isinstance(request.get("context"), dict) else {}
    player_request = context.get("player_request")
    if isinstance(player_request, str) and player_request.strip():
        return player_request, "context.player_request"
    public_prompt = request.get("public_prompt")
    if isinstance(public_prompt, str) and public_prompt.strip():
        for line in public_prompt.splitlines():
            if line.lower().startswith("player request:"):
                extracted = line.split(":", 1)[1].strip()
                if extracted:
                    return extracted, "request.public_prompt.player_request"
        return public_prompt, "request.public_prompt"
    return None, "missing"


def candidate_from_agents_sdk_entry(entry: dict[str, Any]) -> dict[str, Any] | None:
    request = entry.get("request") if isinstance(entry.get("request"), dict) else {}
    response = entry.get("response") if isinstance(entry.get("response"), dict) else {}
    prompt, prompt_source = _agents_sdk_candidate_prompt(request)
    if not isinstance(prompt, str) or not prompt.strip():
        return None
    nested = response.get("response") if isinstance(response.get("response"), dict) else {}
    tool_decisions = nested.get("tool_decisions") if isinstance(nested.get("tool_decisions"), dict) else {}
    build_option = tool_decisions.get("build_option") if isinstance(tool_decisions.get("build_option"), dict) else {}
    memory_match = build_option.get("memory_match") if isinstance(build_option.get("memory_match"), dict) else {}
    tool_trace = nested.get("tool_trace") if isinstance(nested.get("tool_trace"), list) else []
    candidate = _base_candidate(
        "agents_sdk_request_response",
        safe_scalar(entry.get("created_at")),
        prompt,
    )
    candidate.update({
        "owner": safe_scalar(request.get("owner")),
        "agent_id": safe_scalar(request.get("agent_id")),
        "task_id": safe_scalar(request.get("task_id")),
        "route": "model_adapter_async",
        "action": "model",
        "prompt_source": prompt_source,
        "observed_ok": response.get("ok") is True,
        "observed_status": "success" if response.get("ok") is True else "failed",
        "observed_reason": safe_scalar(response.get("reason")),
        "observed": {
            "response_kind": safe_scalar(response.get("response_kind")),
            "adapter_name": safe_scalar(response.get("adapter_name")),
            "agentic_execution": nested.get("agentic_execution"),
            "world_mutation_authority": safe_scalar(nested.get("world_mutation_authority")),
            "selected_option_id": safe_scalar(nested.get("selected_option_id")),
            "tool_decision_source": safe_scalar(nested.get("tool_decision_source")),
            "build_option_decision_source": safe_scalar(build_option.get("decision_source")),
            "build_option_selected_option_id": safe_scalar(build_option.get("selected_option_id")),
            "memory_available": memory_match.get("memory_available"),
            "memory_matched_case_id": safe_scalar(memory_match.get("matched_case_id")),
            "tools_enabled": [
                bounded_text(item, 80)
                for item in nested.get("tools_enabled", [])
                if isinstance(item, str)
            ][:8],
            "required_tool_calls": safe_string_list(nested.get("required_tool_calls")),
            "missing_required_tool_calls": safe_string_list(nested.get("missing_required_tool_calls")),
            "required_tool_calls_satisfied": nested.get("required_tool_calls_satisfied"),
            "tool_trace_names": [
                bounded_text(item.get("tool_name"), 80)
                for item in tool_trace
                if isinstance(item, dict) and isinstance(item.get("tool_name"), str)
            ][:8],
        },
    })
    return finalize_candidate(candidate)


def _extract_action_log_json(line: str) -> dict[str, Any] | None:
    marker = "request_trace="
    if marker not in line:
        return None
    raw = line.split(marker, 1)[1].strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if payload.get("event_kind") != "nova_request_trace":
        return None
    return payload


def candidate_from_nova_trace(payload: dict[str, Any]) -> dict[str, Any] | None:
    trace = payload.get("trace") if isinstance(payload.get("trace"), dict) else {}
    response = trace.get("response") if isinstance(trace.get("response"), dict) else {}
    prompt = trace.get("public_prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return None
    candidate = _base_candidate(
        "nova_request_trace",
        safe_scalar(trace.get("completed_us") or trace.get("created_us")),
        prompt,
    )
    candidate.update({
        "owner": safe_scalar(trace.get("owner")),
        "agent_id": safe_scalar(trace.get("agent_id")),
        "task_id": safe_scalar(response.get("task_id")),
        "route": safe_scalar(trace.get("route")),
        "action": safe_scalar(trace.get("action") or response.get("action")),
        "observed_ok": response.get("ok") is True,
        "observed_status": safe_scalar(response.get("status")),
        "observed_reason": safe_scalar(response.get("reason")),
        "trace_id": safe_scalar(trace.get("trace_id")),
        "observed": {
            "action": safe_scalar(response.get("action")),
            "status": safe_scalar(response.get("status")),
            "build_kind": safe_scalar(response.get("build_kind")),
            "build_material_name": safe_scalar(response.get("build_material_name")),
            "planned_node_writes": safe_scalar(response.get("planned_node_writes")),
            "planner_mode": safe_scalar(response.get("planner_mode")),
            "selected_candidate_id": safe_scalar(response.get("selected_candidate_id")),
            "candidate_count": safe_scalar(response.get("candidate_count")),
            "adapter_tool_decision_source": safe_scalar(response.get("adapter_tool_decision_source")),
            "adapter_required_tool_calls": safe_string_list(response.get("adapter_required_tool_calls")),
            "adapter_missing_required_tool_calls": safe_string_list(
                response.get("adapter_missing_required_tool_calls")
            ),
            "adapter_required_tool_calls_satisfied": response.get("adapter_required_tool_calls_satisfied"),
            "build_option_decision_source": safe_scalar(response.get("build_option_decision_source")),
            "adapter_memory_available": response.get("adapter_memory_available"),
            "adapter_memory_matched_case_id": safe_scalar(response.get("adapter_memory_matched_case_id")),
            "adapter_memory_case_hint": safe_scalar(response.get("adapter_memory_case_hint")),
            "adapter_tool_trace_names": [
                bounded_text(item, 80)
                for item in response.get("adapter_tool_trace_names", [])
                if isinstance(item, str)
            ][:8],
        },
    })
    return finalize_candidate(candidate)


def _first_action(entry: dict[str, Any]) -> dict[str, Any]:
    actions = entry.get("actions") if isinstance(entry.get("actions"), list) else []
    for action in actions:
        if isinstance(action, dict):
            return action
    return {}


def _planned_node_writes_from_actions(entry: dict[str, Any]) -> int:
    total = 0
    actions = entry.get("actions") if isinstance(entry.get("actions"), list) else []
    for action in actions:
        if not isinstance(action, dict):
            continue
        action_type = str(action.get("type") or "")
        if action_type == "place_node":
            try:
                total += max(1, int(action.get("count") or 1))
            except (TypeError, ValueError):
                total += 1
        elif action_type in {"fill_box", "hollow_box", "clear_box"}:
            size = action.get("size") if isinstance(action.get("size"), dict) else {}
            try:
                total += (
                    max(1, int(size.get("x") or 1))
                    * max(1, int(size.get("y") or 1))
                    * max(1, int(size.get("z") or 1))
                )
            except (TypeError, ValueError):
                total += 0
        elif action_type in {"sphere", "ring"}:
            try:
                radius = max(1, int(action.get("radius") or 1))
            except (TypeError, ValueError):
                radius = 1
            total += radius * radius * 4
        elif action_type == "line":
            total += 1
        elif action_type == "lights":
            try:
                total += max(1, int(action.get("count") or 1))
            except (TypeError, ValueError):
                total += 1
    return total


def _build_kind_from_sidecar_action(entry: dict[str, Any], action: dict[str, Any]) -> str | None:
    contract = entry.get("prompt_contract") if isinstance(entry.get("prompt_contract"), dict) else {}
    contract_kind = contract.get("contract_kind")
    if isinstance(contract_kind, str) and contract_kind:
        if contract_kind == "single_fire":
            return "fire"
        if contract_kind.endswith("_wall"):
            return "wall"
    material = str(action.get("material") or "")
    action_type = str(action.get("type") or "")
    if material == "fire" and action_type == "place_node":
        return "fire"
    if action_type == "fill_box":
        return "wall"
    return action_type or None


def candidate_from_nova_agent_log_entry(entry: dict[str, Any]) -> dict[str, Any] | None:
    prompt = entry.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return None
    first_action = _first_action(entry)
    prompt_contract = entry.get("prompt_contract") if isinstance(entry.get("prompt_contract"), dict) else {}
    tool_trace = entry.get("tool_trace") if isinstance(entry.get("tool_trace"), list) else []
    correction_source = safe_scalar(entry.get("correction_source"))
    contract_satisfied = entry.get("contract_satisfied")
    observed_status = "success" if entry.get("ok") is True else "failed"
    if correction_source:
        observed_status = "corrected"
    if contract_satisfied is False:
        observed_status = "contract_failed"
    candidate = _base_candidate(
        "nova_agent_sidecar_request_response",
        safe_scalar(entry.get("ts")),
        prompt,
    )
    candidate.update({
        "owner": safe_scalar(entry.get("player")),
        "agent_id": "nova_agent:sidecar",
        "task_id": None,
        "route": safe_scalar(entry.get("source") or "nova_agent_sidecar"),
        "action": "build" if first_action else "reply",
        "observed_ok": entry.get("ok") is True and contract_satisfied is not False,
        "observed_status": observed_status,
        "observed_reason": correction_source,
        "observed": {
            "source": safe_scalar(entry.get("source")),
            "label": safe_scalar(entry.get("label"), 200),
            "action": safe_scalar(first_action.get("type")),
            "build_kind": safe_scalar(_build_kind_from_sidecar_action(entry, first_action)),
            "build_material_name": safe_scalar(first_action.get("material")),
            "planned_node_writes": _planned_node_writes_from_actions(entry),
            "contract_kind": safe_scalar(prompt_contract.get("contract_kind")),
            "contract_satisfied": contract_satisfied,
            "correction_source": correction_source,
            "tool_trace_names": [
                bounded_text(item.get("tool_name"), 80)
                for item in tool_trace
                if isinstance(item, dict) and isinstance(item.get("tool_name"), str)
            ][:8],
            "action_count": len(entry.get("actions")) if isinstance(entry.get("actions"), list) else 0,
        },
    })
    return finalize_candidate(candidate)


def _read_jsonl_candidates(paths: list[Path], violations: list[dict[str, str]]) -> tuple[list[dict[str, Any]], int, int]:
    candidates: list[dict[str, Any]] = []
    read_entries = 0
    skipped_private = 0
    for path in paths:
        if not path.is_file():
            violations.append({"kind": "missing_agents_sdk_log", "details": str(path)})
            continue
        for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not raw.strip():
                continue
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                violations.append({
                    "kind": "invalid_agents_sdk_log_json",
                    "details": f"{path}:{line_number}",
                })
                continue
            if entry.get("event_kind") != "ai_native_agents_sdk_request_response":
                continue
            read_entries += 1
            if has_private_content(entry) or has_forbidden_key(entry):
                skipped_private += 1
                violations.append({
                    "kind": "skipped_private_agents_sdk_log_entry",
                    "details": f"{path}:{line_number}",
                })
                continue
            candidate = candidate_from_agents_sdk_entry(entry)
            if candidate:
                candidates.append(candidate)
    return candidates, read_entries, skipped_private


def _read_nova_agent_log_candidates(paths: list[Path], violations: list[dict[str, str]]) -> tuple[list[dict[str, Any]], int, int]:
    candidates: list[dict[str, Any]] = []
    read_entries = 0
    skipped_private = 0
    for path in paths:
        if not path.is_file():
            violations.append({"kind": "missing_nova_agent_log", "details": str(path)})
            continue
        for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not raw.strip():
                continue
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                violations.append({
                    "kind": "invalid_nova_agent_log_json",
                    "details": f"{path}:{line_number}",
                })
                continue
            if not isinstance(entry, dict) or "prompt" not in entry or "actions" not in entry:
                continue
            read_entries += 1
            if has_private_content(entry) or has_forbidden_key(entry):
                skipped_private += 1
                violations.append({
                    "kind": "skipped_private_nova_agent_log_entry",
                    "details": f"{path}:{line_number}",
                })
                continue
            candidate = candidate_from_nova_agent_log_entry(entry)
            if candidate:
                candidates.append(candidate)
    return candidates, read_entries, skipped_private


def _read_action_log_candidates(paths: list[Path], violations: list[dict[str, str]]) -> tuple[list[dict[str, Any]], int, int]:
    candidates: list[dict[str, Any]] = []
    read_entries = 0
    skipped_private = 0
    for path in paths:
        if not path.is_file():
            violations.append({"kind": "missing_action_log", "details": str(path)})
            continue
        for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            payload = _extract_action_log_json(raw)
            if payload is None:
                continue
            read_entries += 1
            if has_private_content(payload) or has_forbidden_key(payload):
                skipped_private += 1
                violations.append({
                    "kind": "skipped_private_nova_request_trace",
                    "details": f"{path}:{line_number}",
                })
                continue
            candidate = candidate_from_nova_trace(payload)
            if candidate:
                candidates.append(candidate)
    return candidates, read_entries, skipped_private


def _dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for candidate in candidates:
        candidate_id = str(candidate.get("candidate_id") or "")
        if candidate_id in seen:
            continue
        seen.add(candidate_id)
        result.append(candidate)
    return result


def _candidate_sort_key(candidate: dict[str, Any]) -> tuple[int, str, str]:
    priority_rank = 0 if candidate.get("priority") == "high" else 1
    ready_rank = "0" if candidate.get("ready_for_prompt_eval") is True else "1"
    return (priority_rank, ready_rank, str(candidate.get("candidate_id") or ""))


def build_eval_candidate_queue(
    *,
    agents_sdk_logs: list[Path] | None = None,
    nova_agent_logs: list[Path] | None = None,
    action_logs: list[Path] | None = None,
    generated_at: str | None = None,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict[str, Any]:
    violations: list[dict[str, str]] = []
    agents_sdk_logs = agents_sdk_logs or []
    nova_agent_logs = nova_agent_logs or []
    action_logs = action_logs or []
    generated_at = generated_at or utc_now()

    sdk_candidates, sdk_entries, sdk_private = _read_jsonl_candidates(agents_sdk_logs, violations)
    nova_agent_candidates, nova_agent_entries, nova_agent_private = _read_nova_agent_log_candidates(
        nova_agent_logs,
        violations,
    )
    trace_candidates, trace_entries, trace_private = _read_action_log_candidates(action_logs, violations)
    candidates = _dedupe_candidates(sdk_candidates + nova_agent_candidates + trace_candidates)
    candidates.sort(key=_candidate_sort_key)
    truncated = len(candidates) > max_candidates
    candidates = candidates[:max(0, max_candidates)]

    ready_count = sum(1 for item in candidates if item.get("ready_for_prompt_eval") is True)
    manual_count = sum(1 for item in candidates if item.get("ready_for_prompt_eval") is not True)
    adapter_contract_ready_count = sum(
        1 for item in candidates if item.get("ready_for_adapter_contract_eval") is True
    )
    adapter_contract_failure_count = sum(
        1
        for item in candidates
        if isinstance(item.get("adapter_tool_contract"), dict)
        and item["adapter_tool_contract"].get("status") == "fail"
    )
    status = "ready"
    if not candidates:
        status = "empty"
    if violations:
        status = "attention" if candidates else "empty"

    payload = {
        "schema_version": 1,
        "artifact_kind": REPORT_KIND,
        "generated_at": generated_at,
        "status": status,
        "source_summary": {
            "agents_sdk_log_entries_read": sdk_entries,
            "nova_agent_log_entries_read": nova_agent_entries,
            "nova_request_traces_read": trace_entries,
            "entries_skipped_private": sdk_private + nova_agent_private + trace_private,
            "candidates_total": len(candidates),
            "ready_for_prompt_eval": ready_count,
            "ready_for_adapter_contract_eval": adapter_contract_ready_count,
            "adapter_contract_failures": adapter_contract_failure_count,
            "manual_review_required": manual_count,
            "review_required": True,
        },
        "candidates": candidates,
        "violations": violations,
        "safety": {
            "public_safe_output": True,
            "review_required_before_promotion": True,
            "no_world_mutation": True,
            "no_raw_assets": True,
            "no_provider_prompts": True,
            "no_family_world_coordinates": True,
            "private_entries_skipped": sdk_private + nova_agent_private + trace_private,
        },
        "bounds": {
            "max_candidates": max_candidates,
            "max_bytes": max_bytes,
            "output_bytes": 0,
            "truncated": truncated,
        },
    }

    raw = json.dumps(payload, sort_keys=True)
    while len(raw.encode("utf-8")) > max_bytes and payload["candidates"]:
        payload["candidates"].pop()
        payload["bounds"]["truncated"] = True
        payload["source_summary"]["candidates_total"] = len(payload["candidates"])
        payload["source_summary"]["ready_for_prompt_eval"] = sum(
            1 for item in payload["candidates"] if item.get("ready_for_prompt_eval") is True
        )
        payload["source_summary"]["manual_review_required"] = sum(
            1 for item in payload["candidates"] if item.get("ready_for_prompt_eval") is not True
        )
        payload["source_summary"]["ready_for_adapter_contract_eval"] = sum(
            1 for item in payload["candidates"] if item.get("ready_for_adapter_contract_eval") is True
        )
        payload["source_summary"]["adapter_contract_failures"] = sum(
            1
            for item in payload["candidates"]
            if isinstance(item.get("adapter_tool_contract"), dict)
            and item["adapter_tool_contract"].get("status") == "fail"
        )
        raw = json.dumps(payload, sort_keys=True)

    payload["bounds"]["output_bytes"] = len(json.dumps(payload, sort_keys=True).encode("utf-8"))
    if payload["bounds"]["output_bytes"] > max_bytes:
        payload["status"] = "fail"
        payload["violations"].append({
            "kind": "output_exceeds_max_bytes",
            "details": str(payload["bounds"]["output_bytes"]),
        })
    if has_private_content(payload) or has_forbidden_key(payload):
        payload["status"] = "fail"
        payload["safety"]["public_safe_output"] = False
        payload["violations"].append({
            "kind": "private_pattern_in_output",
            "details": "candidate queue artifact",
        })
    return payload


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a public-safe eval candidate queue from Nova/Agents logs.",
    )
    parser.add_argument("--root", default=".", help="Repository root for relative paths.")
    parser.add_argument("--agents-sdk-log", action="append", default=[], help="Agents SDK adapter JSONL log path.")
    parser.add_argument("--nova-agent-log", action="append", default=[], help="Nova sidecar request JSONL log path.")
    parser.add_argument("--action-log", action="append", default=[], help="Luanti action/debug log path containing request_trace JSON.")
    parser.add_argument("--output", required=True, help="Output candidate queue JSON path.")
    parser.add_argument("--generated-at", default=None, help="ISO timestamp for deterministic artifacts.")
    parser.add_argument("--max-candidates", type=int, default=DEFAULT_MAX_CANDIDATES)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    root = resolve_path(Path.cwd(), args.root).resolve()
    agents_sdk_logs = [resolve_path(root, path) for path in args.agents_sdk_log]
    nova_agent_logs = [resolve_path(root, path) for path in args.nova_agent_log]
    action_logs = [resolve_path(root, path) for path in args.action_log]
    output = resolve_path(root, args.output)

    payload = build_eval_candidate_queue(
        agents_sdk_logs=agents_sdk_logs,
        nova_agent_logs=nova_agent_logs,
        action_logs=action_logs,
        generated_at=args.generated_at,
        max_candidates=max(0, args.max_candidates),
        max_bytes=max(1000, args.max_bytes),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(output.relative_to(root) if output.is_relative_to(root) else output)
    return 0 if payload.get("status") != "fail" else 1


if __name__ == "__main__":
    raise SystemExit(main())
