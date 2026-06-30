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
OPERATOR_LABEL_KIND = "ai_native_agent_eval_operator_labels"
REQUEST_RESPONSE_LOG_GATE_KIND = "ai_native_agent_request_response_log_gate"
REQUEST_RESPONSE_LOG_GATE_SOURCE_KIND = "agents_sdk_request_response_log_gate"
VERIFIED_LIVE_PROBE_KIND = "disposable_live_ai_runtime_nova_auto_apply_probe"
VERIFIED_LIVE_RESULT_KIND = "ai_native_nova_auto_apply_live_result"
PROMPT_EVAL_LIVE_RESULT_KIND = "ai_native_agent_prompt_eval_live_result"
DEFAULT_MAX_BYTES = 32000
DEFAULT_MAX_CANDIDATES = 50
PRIMARY_AGENT_TOOL_DECISION_SOURCE = "agents_sdk_function_tool"
REPAIR_AGENT_TOOL_DECISION_SOURCE = "agents_sdk_repair_function_tool"
LOCAL_AGENT_TOOL_CONTRACT_FAST_PATH = "local_agent_tool_contract_fast_path"
NOVA_AGENT_PLAN_TOOL_DECISION_SOURCE = "agents_sdk_submit_nova_plan_tool"
ACCEPTED_AGENT_TOOL_DECISION_SOURCES = {
    PRIMARY_AGENT_TOOL_DECISION_SOURCE,
    REPAIR_AGENT_TOOL_DECISION_SOURCE,
    LOCAL_AGENT_TOOL_CONTRACT_FAST_PATH,
}

ALLOWED_LABEL_EXPECTED_KEYS = {
    "action",
    "build_kind",
    "build_count",
    "build_depth",
    "build_height",
    "build_material_name",
    "build_material_node",
    "build_width",
    "planned_node_writes",
    "route",
    "selected_candidate_id",
    "danger_refusal_allowed",
    "forbidden_extra_structure",
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


def accepted_agent_tool_decision_sources() -> list[str]:
    return sorted(ACCEPTED_AGENT_TOOL_DECISION_SOURCES)


def is_accepted_agent_tool_decision_source(value: Any) -> bool:
    return isinstance(value, str) and value in ACCEPTED_AGENT_TOOL_DECISION_SOURCES


def safe_int(value: Any, *, minimum: int = 0, maximum: int = 10000) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    if result < minimum or result > maximum:
        return None
    return result


def safe_string_list(value: Any, *, max_items: int = 8, max_bytes: int = 80) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        bounded_text(item, max_bytes)
        for item in value
        if isinstance(item, str)
    ][:max_items]


def safe_build_option_summaries(value: Any, *, max_items: int = 5) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    summaries: list[dict[str, Any]] = []
    for option in value:
        if not isinstance(option, dict):
            continue
        actions = option.get("actions") if isinstance(option.get("actions"), list) else []
        action_count = safe_int(option.get("action_count"), minimum=0, maximum=10000)
        if action_count is None and actions:
            action_count = len(actions)
        summary = {
            "option_id": safe_scalar(option.get("option_id"), 120),
            "source": safe_scalar(option.get("source"), 120),
            "label": safe_scalar(option.get("label"), 160),
            "build_kind": safe_scalar(option.get("build_kind"), 120),
            "build_material_name": safe_scalar(option.get("build_material_name"), 120),
            "planned_node_writes": safe_int(option.get("planned_node_writes"), minimum=0),
            "contract_satisfied": option.get("contract_satisfied"),
            "action_count": action_count,
        }
        summaries.append({
            key: item
            for key, item in summary.items()
            if item is not None
        })
        if len(summaries) >= max_items:
            break
    return summaries


def safe_reviewed_prompt_memory(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    allowed = {
        "case_hint": 120,
        "matched_case_id": 180,
        "match_quality": 80,
        "memory_available": 80,
        "source": 120,
    }
    result: dict[str, Any] = {}
    for key, max_bytes in allowed.items():
        if key in value:
            result[key] = safe_scalar(value.get(key), max_bytes)
    return {
        key: item
        for key, item in result.items()
        if item is not None
    }


def normalized_prompt(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def safe_expected_from_operator_label(expected: Any) -> dict[str, Any] | None:
    if not isinstance(expected, dict):
        return None
    result: dict[str, Any] = {}
    for key in sorted(ALLOWED_LABEL_EXPECTED_KEYS):
        if key not in expected:
            continue
        value = expected[key]
        if isinstance(value, (str, int, float, bool)) or value is None:
            result[key] = safe_scalar(value, 200)
    action = result.get("action") or "build"
    if action != "build":
        return None
    result["action"] = "build"
    if not isinstance(result.get("build_kind"), str) or not result["build_kind"].strip():
        return None
    if not isinstance(result.get("build_material_name"), str) or not result["build_material_name"].strip():
        return None
    selected_candidate_id = result.get("selected_candidate_id")
    if selected_candidate_id is not None:
        if not isinstance(selected_candidate_id, str) or not selected_candidate_id.strip():
            return None
        result["selected_candidate_id"] = selected_candidate_id.strip()
    if "planned_node_writes" in result:
        writes = safe_int(result["planned_node_writes"], minimum=0)
        if writes is None:
            return None
        result["planned_node_writes"] = writes
    for dimension_key in ("build_width", "build_depth", "build_height", "build_count"):
        if dimension_key not in result:
            continue
        dimension = safe_int(result[dimension_key], minimum=1)
        if dimension is None:
            return None
        result[dimension_key] = dimension
    return result


def read_operator_label_payloads(paths: list[Path], violations: list[dict[str, str]]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for path in paths:
        if not path.is_file():
            violations.append({"kind": "missing_operator_labels", "details": str(path)})
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            violations.append({"kind": "invalid_operator_labels_json", "details": str(path)})
            continue
        if not isinstance(payload, dict):
            violations.append({"kind": "invalid_operator_labels_payload", "details": str(path)})
            continue
        payloads.append(payload)
    return payloads


def iter_operator_labels(
    payloads: list[dict[str, Any]],
    violations: list[dict[str, str]],
) -> list[dict[str, Any]]:
    labels: list[dict[str, Any]] = []
    for payload_index, payload in enumerate(payloads, start=1):
        if payload.get("artifact_kind") != OPERATOR_LABEL_KIND:
            violations.append({
                "kind": "invalid_operator_labels_kind",
                "details": str(payload.get("artifact_kind")),
            })
            continue
        if has_private_content(payload) or has_forbidden_key(payload):
            violations.append({
                "kind": "operator_labels_not_public_safe",
                "details": f"operator_labels:{payload_index}",
            })
            continue
        raw_labels = payload.get("labels")
        if not isinstance(raw_labels, list):
            violations.append({
                "kind": "missing_operator_label_entries",
                "details": f"operator_labels:{payload_index}",
            })
            continue
        for label_index, raw_label in enumerate(raw_labels, start=1):
            if not isinstance(raw_label, dict):
                violations.append({
                    "kind": "invalid_operator_label_entry",
                    "details": f"operator_labels:{payload_index}:{label_index}",
                })
                continue
            expected = safe_expected_from_operator_label(raw_label.get("expected"))
            if expected is None:
                violations.append({
                    "kind": "invalid_operator_label_expected",
                    "details": f"operator_labels:{payload_index}:{label_index}",
                })
                continue
            candidate_id = raw_label.get("candidate_id")
            prompt = raw_label.get("prompt")
            if not isinstance(candidate_id, str) and not isinstance(prompt, str):
                violations.append({
                    "kind": "operator_label_missing_match",
                    "details": f"operator_labels:{payload_index}:{label_index}",
                })
                continue
            labels.append({
                "label_id": safe_scalar(raw_label.get("label_id"), 160)
                or f"operator_label:{payload_index}:{label_index}",
                "candidate_id": safe_scalar(candidate_id, 180),
                "prompt": safe_scalar(prompt, 1000),
                "prompt_normalized": normalized_prompt(prompt),
                "source_kind": safe_scalar(raw_label.get("source_kind"), 120),
                "case_hint": safe_scalar(raw_label.get("case_hint"), 120) or "operator_labeled",
                "expected": expected,
            })
    return labels


def operator_label_matches(candidate: dict[str, Any], label: dict[str, Any]) -> bool:
    label_candidate_id = label.get("candidate_id")
    if isinstance(label_candidate_id, str) and label_candidate_id:
        if candidate.get("candidate_id") != label_candidate_id:
            return False
    elif label.get("prompt_normalized") != normalized_prompt(candidate.get("prompt")):
        return False
    elif (
        candidate.get("source_kind") == VERIFIED_LIVE_PROBE_KIND
        and isinstance(label.get("case_hint"), str)
        and isinstance(candidate.get("case_hint"), str)
        and label["case_hint"] != candidate["case_hint"]
    ):
        return False
    label_source_kind = label.get("source_kind")
    if isinstance(label_source_kind, str) and label_source_kind:
        return candidate.get("source_kind") == label_source_kind
    return True


def generated_option_from_sources(*sources: Any) -> dict[str, Any]:
    for source in sources:
        if not isinstance(source, dict):
            continue
        option = source.get("generated_option")
        if isinstance(option, dict):
            return option
    return {}


def generated_option_from_tool_trace(tool_trace: Any) -> dict[str, Any]:
    if not isinstance(tool_trace, list):
        return {}
    for item in tool_trace:
        if not isinstance(item, dict):
            continue
        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        option = generated_option_from_sources(result)
        if option:
            return option
    return {}


def generated_expected_outcome(candidate: dict[str, Any], observed: dict[str, Any]) -> dict[str, Any] | None:
    if candidate.get("source_kind") not in {
        "agents_sdk_request_response",
        REQUEST_RESPONSE_LOG_GATE_SOURCE_KIND,
        VERIFIED_LIVE_PROBE_KIND,
    }:
        return None
    selected_id = observed.get("selected_option_id") or observed.get("build_option_selected_option_id")
    if not isinstance(selected_id, str) or not selected_id.startswith("generated_"):
        return None
    tool_trace_names = {
        item for item in observed.get("tool_trace_names", [])
        if isinstance(item, str)
    }
    required_trace = {
        "recall_build_prompt_memory",
        "propose_build_option",
        "select_build_option",
        "plan_build_actions",
    }
    if not required_trace.issubset(tool_trace_names):
        return None
    if not is_accepted_agent_tool_decision_source(observed.get("tool_decision_source")):
        return None
    if observed.get("required_tool_calls_satisfied") is not True:
        return None
    if observed.get("missing_required_tool_calls"):
        return None
    if observed.get("build_action_plan_status") != "ready":
        return None
    if observed.get("build_action_plan_world_mutation_authority") != "luanti":
        return None
    if observed.get("generated_option_status") != "ready":
        return None
    generated_id = observed.get("generated_option_id")
    if not isinstance(generated_id, str) or generated_id != selected_id:
        return None
    build_kind = observed.get("generated_option_build_kind")
    material = observed.get("generated_option_build_material_name")
    writes = safe_int(observed.get("generated_option_planned_node_writes"), minimum=1)
    if not isinstance(build_kind, str) or not build_kind.strip():
        return None
    if not isinstance(material, str) or not material.strip():
        return None
    if writes is None:
        return None
    expected: dict[str, Any] = {
        "action": "build",
        "route": "agentic_build_planner",
        "selected_candidate_id": selected_id,
        "build_kind": build_kind.strip(),
        "build_material_name": material.strip(),
        "planned_node_writes": writes,
        "forbidden_extra_structure": True,
    }
    for source_key, expected_key in (
        ("generated_option_build_width", "build_width"),
        ("generated_option_build_depth", "build_depth"),
        ("generated_option_build_height", "build_height"),
        ("generated_option_build_count", "build_count"),
    ):
        dimension = safe_int(observed.get(source_key), minimum=1)
        if dimension is not None:
            expected[expected_key] = dimension
    return {
        "case_hint": selected_id,
        "ready_for_prompt_eval": True,
        "review_status": "candidate_ready",
        "expected": expected,
    }


def apply_operator_labels(
    candidates: list[dict[str, Any]],
    operator_label_payloads: list[dict[str, Any]],
    violations: list[dict[str, str]],
) -> dict[str, int]:
    labels = iter_operator_labels(operator_label_payloads, violations)
    applied = 0
    for candidate in candidates:
        for label in labels:
            if not operator_label_matches(candidate, label):
                continue
            candidate["case_hint"] = label["case_hint"]
            candidate["expected"] = dict(label["expected"])
            candidate["ready_for_prompt_eval"] = True
            candidate["review_status"] = "operator_labeled_candidate_ready"
            candidate["priority"] = "high"
            candidate["operator_label"] = {
                "label_id": label["label_id"],
                "mode": "operator_label_overlay",
                "matched_by": "candidate_id" if label.get("candidate_id") else "prompt",
                "review_required_before_default_gate": True,
            }
            applied += 1
            break
    return {"operator_labels_read": len(labels), "operator_labels_applied": applied}


def safe_context_subset(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    allowed = {
        "capabilities",
        "candidate_summary",
        "intent",
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
            result[key] = safe_scalar(item, 1600 if key == "candidate_summary" else 400)
    return result


def adapter_replay_request_from_agents_sdk_request(
    request: dict[str, Any],
    prompt: str,
) -> dict[str, Any]:
    context = safe_context_subset(request.get("context"))
    if "player_request" not in context:
        context["player_request"] = bounded_text(prompt, 400)
    public_prompt = request.get("public_prompt")
    if not isinstance(public_prompt, str) or not public_prompt.strip():
        public_prompt = f"Player request: {prompt}"
    return {
        "request_kind": "ai_native_model_adapter_request",
        "adapter_contract": safe_scalar(request.get("adapter_contract")) or "provider_neutral_v1",
        "agent_id": safe_scalar(request.get("agent_id")) or "nova_agent:adapter_contract_eval",
        "owner": safe_scalar(request.get("owner")) or "AdapterContractEval",
        "task_id": safe_scalar(request.get("task_id")) or "adapter-contract-eval",
        "public_prompt": bounded_text(public_prompt, 2000),
        "context": context,
        "safety": {"public_safe_request": True},
        "bounds": {"max_response_bytes": 4000},
    }


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
    verified_live_probe = candidate.get("source_kind") in {
        REQUEST_RESPONSE_LOG_GATE_SOURCE_KIND,
        VERIFIED_LIVE_PROBE_KIND,
    }
    agentic_nova_sidecar = (
        candidate.get("source_kind") == "nova_agent_sidecar_request_response"
        and isinstance(route, str)
        and route.startswith("agents_sdk")
    )

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
                "route": (
                    "agentic_build_planner"
                    if verified_live_probe or agentic_nova_sidecar
                    else "deterministic_build_parser"
                ),
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
                "forbidden_extra_structure": True,
            },
        }
    generated = generated_expected_outcome(candidate, observed)
    if generated is not None:
        return generated
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
    if candidate.get("source_kind") == "nova_agent_sidecar_request_response":
        expected_decision_sources = {
            NOVA_AGENT_PLAN_TOOL_DECISION_SOURCE,
            *ACCEPTED_AGENT_TOOL_DECISION_SOURCES,
        }
    else:
        expected_decision_sources = set(ACCEPTED_AGENT_TOOL_DECISION_SOURCES)
    source_accepted = isinstance(decision_source, str) and decision_source in expected_decision_sources

    if satisfied is True and not missing and source_accepted:
        status = "pass"
    if satisfied is False or missing or (decision_source and not source_accepted):
        status = "fail"
    replayable = isinstance(candidate.get("adapter_replay_request"), dict)
    non_replayable_sidecar_observation = (
        status == "fail"
        and candidate.get("source_kind") == "nova_agent_sidecar_request_response"
        and not replayable
    )
    if non_replayable_sidecar_observation:
        status = "review"
    expected_decision_source = (
        NOVA_AGENT_PLAN_TOOL_DECISION_SOURCE
        if candidate.get("source_kind") == "nova_agent_sidecar_request_response"
        else PRIMARY_AGENT_TOOL_DECISION_SOURCE
    )

    result = {
        "status": status,
        "required_tool_calls": required,
        "missing_required_tool_calls": missing,
        "required_tool_calls_satisfied": satisfied,
        "tool_decision_source": safe_scalar(decision_source),
        "ready_for_adapter_contract_eval": status == "fail" and replayable,
        "expected": {
            "required_tool_calls": required,
            "missing_required_tool_calls": [],
            "required_tool_calls_satisfied": True,
            "tool_decision_source": expected_decision_source,
            "tool_decision_sources": sorted(expected_decision_sources),
        },
    }
    if non_replayable_sidecar_observation:
        result["review_reason"] = "non_replayable_family_sidecar_contract_observation"
    return result


def _candidate_selected_option_id(candidate: dict[str, Any]) -> str | None:
    observed = candidate.get("observed") if isinstance(candidate.get("observed"), dict) else {}
    expected = candidate.get("expected") if isinstance(candidate.get("expected"), dict) else {}
    for value in (
        observed.get("selected_option_id"),
        observed.get("selected_candidate_id"),
        observed.get("build_option_selected_option_id"),
        expected.get("selected_candidate_id"),
    ):
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _adapter_contract_required_tools(candidate: dict[str, Any]) -> set[str]:
    contract = candidate.get("adapter_tool_contract")
    if not isinstance(contract, dict):
        return set()
    return {
        item
        for item in safe_string_list(contract.get("required_tool_calls"), max_items=12)
        if isinstance(item, str) and item
    }


def _adapter_contract_is_active_failure(candidate: dict[str, Any]) -> bool:
    contract = candidate.get("adapter_tool_contract")
    return (
        isinstance(contract, dict)
        and contract.get("status") == "fail"
        and not isinstance(candidate.get("adapter_contract_resolution"), dict)
    )


def _contract_pass_resolves_failure(
    failure: dict[str, Any],
    passing: dict[str, Any],
) -> bool:
    failure_prompt = normalized_prompt(failure.get("prompt"))
    passing_prompt = normalized_prompt(passing.get("prompt"))
    if not failure_prompt or failure_prompt != passing_prompt:
        return False
    failure_observed_at = str(failure.get("observed_at") or "")
    passing_observed_at = str(passing.get("observed_at") or "")
    if failure_observed_at and passing_observed_at and passing_observed_at <= failure_observed_at:
        return False
    failure_selected = _candidate_selected_option_id(failure)
    passing_selected = _candidate_selected_option_id(passing)
    if failure_selected and passing_selected and failure_selected != passing_selected:
        return False
    required = _adapter_contract_required_tools(failure)
    passing_required = _adapter_contract_required_tools(passing)
    return not required or required.issubset(passing_required)


def apply_adapter_contract_resolutions(candidates: list[dict[str, Any]]) -> dict[str, int]:
    passing_candidates = [
        candidate
        for candidate in candidates
        if isinstance(candidate.get("adapter_tool_contract"), dict)
        and candidate["adapter_tool_contract"].get("status") == "pass"
    ]
    resolved = 0
    for candidate in candidates:
        contract = candidate.get("adapter_tool_contract")
        if not isinstance(contract, dict) or contract.get("status") != "fail":
            continue
        resolver = next(
            (
                passing
                for passing in sorted(
                    passing_candidates,
                    key=lambda item: str(item.get("observed_at") or ""),
                    reverse=True,
                )
                if _contract_pass_resolves_failure(candidate, passing)
            ),
            None,
        )
        if resolver is None:
            continue
        candidate["adapter_contract_resolution"] = {
            "status": "resolved_by_later_pass",
            "resolved_by_candidate_id": safe_scalar(resolver.get("candidate_id"), 180),
            "resolved_at": safe_scalar(resolver.get("observed_at"), 120),
            "resolved_by_source_kind": safe_scalar(resolver.get("source_kind"), 120),
            "required_tool_calls_satisfied": True,
        }
        contract["resolution_status"] = "resolved_by_later_pass"
        contract["resolved_by_candidate_id"] = safe_scalar(resolver.get("candidate_id"), 180)
        candidate["ready_for_adapter_contract_eval"] = False
        candidate["adapter_contract_review_status"] = "adapter_contract_resolved"
        candidate["priority"] = "high"
        resolved += 1
    total_failures = sum(
        1
        for candidate in candidates
        if isinstance(candidate.get("adapter_tool_contract"), dict)
        and candidate["adapter_tool_contract"].get("status") == "fail"
    )
    active_failures = sum(1 for candidate in candidates if _adapter_contract_is_active_failure(candidate))
    return {
        "adapter_contract_failures_total": total_failures,
        "adapter_contract_failures_resolved": resolved,
        "adapter_contract_failures_active": active_failures,
    }


def adapter_contract_summary(candidates: list[dict[str, Any]]) -> dict[str, int]:
    total_failures = sum(
        1
        for item in candidates
        if isinstance(item.get("adapter_tool_contract"), dict)
        and item["adapter_tool_contract"].get("status") == "fail"
    )
    resolved_failures = sum(
        1
        for item in candidates
        if isinstance(item.get("adapter_tool_contract"), dict)
        and item["adapter_tool_contract"].get("status") == "fail"
        and isinstance(item.get("adapter_contract_resolution"), dict)
    )
    active_failures = sum(1 for item in candidates if _adapter_contract_is_active_failure(item))
    ready_for_replay = sum(1 for item in candidates if item.get("ready_for_adapter_contract_eval") is True)
    return {
        "ready_for_adapter_contract_eval": ready_for_replay,
        "adapter_contract_failures": active_failures,
        "adapter_contract_failures_active": active_failures,
        "adapter_contract_failures_total": total_failures,
        "adapter_contract_failures_resolved": resolved_failures,
    }


def _candidate_requires_manual_review(candidate: dict[str, Any]) -> bool:
    if candidate.get("ready_for_prompt_eval") is True:
        return False
    if candidate.get("ready_for_adapter_contract_eval") is True:
        return False
    if (
        candidate.get("adapter_contract_review_status") == "adapter_contract_resolved"
        and isinstance(candidate.get("adapter_contract_resolution"), dict)
    ):
        return False
    return candidate.get("review_status") in {"needs_operator_label", "manual_review_required"}


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
    build_action_plan = nested.get("build_action_plan")
    if not isinstance(build_action_plan, dict):
        build_action_plan = (
            tool_decisions.get("build_action_plan")
            if isinstance(tool_decisions.get("build_action_plan"), dict)
            else {}
        )
    tool_trace = nested.get("tool_trace") if isinstance(nested.get("tool_trace"), list) else []
    generated_option = generated_option_from_sources(
        build_option,
        build_action_plan,
        nested,
        generated_option_from_tool_trace(tool_trace),
    )
    memory_match = build_option.get("memory_match") if isinstance(build_option.get("memory_match"), dict) else {}
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
            "model_selected_option_id": safe_scalar(nested.get("model_selected_option_id")),
            "rejected_model_selected_option_id": safe_scalar(
                nested.get("rejected_model_selected_option_id")
            ),
            "initial_model_selected_option_id": safe_scalar(
                nested.get("initial_model_selected_option_id")
            ),
            "agent_repair_attempted": nested.get("agent_repair_attempted"),
            "agent_repair_succeeded": nested.get("agent_repair_succeeded"),
            "agent_repair_reason": safe_scalar(nested.get("agent_repair_reason")),
            "initial_missing_required_tool_calls": safe_string_list(
                nested.get("initial_missing_required_tool_calls")
            ),
            "intent_constraint_option_id": safe_scalar(nested.get("intent_constraint_option_id")),
            "intent_constraint_reason": safe_scalar(nested.get("intent_constraint_reason")),
            "tool_decision_source": safe_scalar(nested.get("tool_decision_source")),
            "build_option_decision_source": safe_scalar(build_option.get("decision_source")),
            "build_option_selected_option_id": safe_scalar(build_option.get("selected_option_id")),
            "build_option_generated_option_status": safe_scalar(
                build_option.get("generated_option_status")
            ),
            "build_action_plan_status": safe_scalar(build_action_plan.get("status")),
            "build_action_plan_selected_option_id": safe_scalar(
                build_action_plan.get("selected_option_id")
            ),
            "build_action_plan_step_count": safe_scalar(build_action_plan.get("step_count")),
            "build_action_plan_world_mutation_authority": safe_scalar(
                build_action_plan.get("world_mutation_authority")
            ),
            "build_action_plan_build_kind": safe_scalar(build_action_plan.get("build_kind")),
            "build_action_plan_build_material_name": safe_scalar(
                build_action_plan.get("build_material_name")
            ),
            "build_action_plan_planned_node_writes": safe_scalar(
                build_action_plan.get("planned_node_writes")
            ),
            "generated_option_id": safe_scalar(generated_option.get("option_id")),
            "generated_option_status": safe_scalar(
                build_option.get("generated_option_status")
                or nested.get("generated_option_status")
            ),
            "generated_option_reason": safe_scalar(
                generated_option.get("reason")
                or build_option.get("generated_option_reason")
                or nested.get("generated_option_reason")
            ),
            "generated_option_build_kind": safe_scalar(generated_option.get("build_kind")),
            "generated_option_build_material_name": safe_scalar(
                generated_option.get("build_material_name")
            ),
            "generated_option_build_width": safe_int(generated_option.get("build_width"), minimum=1),
            "generated_option_build_depth": safe_int(generated_option.get("build_depth"), minimum=1),
            "generated_option_build_height": safe_int(generated_option.get("build_height"), minimum=1),
            "generated_option_build_count": safe_int(generated_option.get("build_count"), minimum=1),
            "generated_option_planned_node_writes": safe_int(
                generated_option.get("planned_node_writes"),
                minimum=0,
            ),
            "memory_available": memory_match.get("memory_available"),
            "memory_matched_case_id": safe_scalar(memory_match.get("matched_case_id")),
            "tools_enabled": safe_string_list(nested.get("tools_enabled")),
            "required_tool_calls": safe_string_list(nested.get("required_tool_calls")),
            "missing_required_tool_calls": safe_string_list(nested.get("missing_required_tool_calls")),
            "required_tool_calls_satisfied": nested.get("required_tool_calls_satisfied"),
            "tool_trace_names": [
                bounded_text(item.get("tool_name"), 80)
                for item in tool_trace
                if isinstance(item, dict) and isinstance(item.get("tool_name"), str)
            ][:8],
        },
        "adapter_replay_request": adapter_replay_request_from_agents_sdk_request(request, prompt),
    })
    return finalize_candidate(candidate)


def _candidate_summary_selected_option(candidate_summary: Any, selected_id: Any) -> dict[str, Any]:
    if not isinstance(candidate_summary, str) or not isinstance(selected_id, str):
        return {}
    selected_id = selected_id.strip()
    if not selected_id:
        return {}
    for raw_item in candidate_summary.split("|"):
        parts = raw_item.split(":")
        if len(parts) < 4:
            continue
        option_id = parts[0].strip()
        if option_id != selected_id:
            continue
        return {
            "option_id": option_id,
            "build_kind": parts[1].strip(),
            "build_material_name": parts[2].strip(),
            "planned_node_writes": safe_int(parts[3].strip(), minimum=0),
        }
    return {}


def candidate_from_request_response_log_gate_case(
    payload: dict[str, Any],
    case: dict[str, Any],
) -> dict[str, Any] | None:
    if payload.get("artifact_kind") != REQUEST_RESPONSE_LOG_GATE_KIND:
        return None
    if case.get("status") != "pass":
        return None
    prompt = case.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return None
    observed = case.get("observed") if isinstance(case.get("observed"), dict) else {}
    request = observed.get("request") if isinstance(observed.get("request"), dict) else {}
    response = observed.get("response") if isinstance(observed.get("response"), dict) else {}
    context = request.get("context") if isinstance(request.get("context"), dict) else {}
    selected_id = safe_scalar(response.get("selected_option_id"), 120)
    summary_option = _candidate_summary_selected_option(
        context.get("candidate_summary"),
        selected_id,
    )
    build_kind = (
        safe_scalar(response.get("build_action_plan_build_kind"), 120)
        or safe_scalar(response.get("generated_option_build_kind"), 120)
        or safe_scalar(summary_option.get("build_kind"), 120)
    )
    material = (
        safe_scalar(response.get("build_action_plan_build_material_name"), 120)
        or safe_scalar(response.get("generated_option_build_material_name"), 120)
        or safe_scalar(summary_option.get("build_material_name"), 120)
    )
    planned_writes = safe_int(response.get("build_action_plan_planned_node_writes"), minimum=0)
    if planned_writes is None:
        planned_writes = safe_int(response.get("generated_option_planned_node_writes"), minimum=0)
    if planned_writes is None:
        planned_writes = safe_int(summary_option.get("planned_node_writes"), minimum=0)

    candidate = _base_candidate(
        REQUEST_RESPONSE_LOG_GATE_SOURCE_KIND,
        safe_scalar(observed.get("created_at") or payload.get("generated_at")),
        prompt,
    )
    candidate.update({
        "owner": safe_scalar(request.get("owner")) or "RequestResponseLogGate",
        "agent_id": safe_scalar(request.get("agent_id")) or "nova_agent:request_response_log_gate",
        "task_id": safe_scalar(request.get("task_id")) or safe_scalar(case.get("case_id")),
        "route": "request_response_log_gate",
        "action": "build",
        "prompt_source": "request_response_log_gate.case.prompt",
        "observed_ok": True,
        "observed_status": "pass",
        "observed_reason": None,
        "observed": {
            "action": "build",
            "status": "pass",
            "gate_case_id": safe_scalar(case.get("case_id"), 120),
            "gate_generated_at": safe_scalar(payload.get("generated_at"), 120),
            "gate_status": "pass",
            "selected_option_id": selected_id,
            "selected_candidate_id": selected_id,
            "tool_decision_source": safe_scalar(response.get("tool_decision_source"), 120),
            "required_tool_calls": safe_string_list(
                response.get("required_tool_calls"),
                max_items=12,
            ),
            "missing_required_tool_calls": safe_string_list(
                response.get("missing_required_tool_calls"),
                max_items=12,
            ),
            "required_tool_calls_satisfied": response.get("required_tool_calls_satisfied"),
            "tool_trace_names": safe_string_list(response.get("tool_trace_names"), max_items=12),
            "build_action_plan_status": safe_scalar(
                response.get("build_action_plan_status"),
                120,
            ),
            "build_action_plan_selected_option_id": selected_id,
            "build_action_plan_step_count": safe_int(
                response.get("build_action_plan_step_count"),
                minimum=0,
            ),
            "build_action_plan_world_mutation_authority": safe_scalar(
                response.get("world_mutation_authority"),
                120,
            ),
            "build_action_plan_build_kind": build_kind,
            "build_action_plan_build_material_name": material,
            "build_action_plan_planned_node_writes": planned_writes,
            "generated_option_id": safe_scalar(response.get("generated_option_id"), 120),
            "generated_option_status": safe_scalar(
                response.get("generated_option_status"),
                120,
            ),
            "generated_option_build_kind": safe_scalar(
                response.get("generated_option_build_kind"),
                120,
            ),
            "generated_option_build_material_name": safe_scalar(
                response.get("generated_option_build_material_name"),
                120,
            ),
            "generated_option_build_width": safe_int(
                response.get("generated_option_build_width"),
                minimum=1,
            ),
            "generated_option_build_depth": safe_int(
                response.get("generated_option_build_depth"),
                minimum=1,
            ),
            "generated_option_build_height": safe_int(
                response.get("generated_option_build_height"),
                minimum=1,
            ),
            "generated_option_build_count": safe_int(
                response.get("generated_option_build_count"),
                minimum=1,
            ),
            "generated_option_planned_node_writes": safe_int(
                response.get("generated_option_planned_node_writes"),
                minimum=0,
            ),
        },
        "adapter_replay_request": adapter_replay_request_from_agents_sdk_request(request, prompt),
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
            "build_width": safe_int(response.get("build_width"), minimum=1),
            "build_depth": safe_int(response.get("build_depth"), minimum=1),
            "build_height": safe_int(response.get("build_height"), minimum=1),
            "build_count": safe_int(response.get("build_count"), minimum=1),
            "planned_node_writes": safe_scalar(response.get("planned_node_writes")),
            "planner_mode": safe_scalar(response.get("planner_mode")),
            "selected_candidate_id": safe_scalar(response.get("selected_candidate_id")),
            "adapter_selected_candidate_id": safe_scalar(
                response.get("adapter_selected_candidate_id")
            ),
            "model_selected_candidate_id": safe_scalar(response.get("model_selected_candidate_id")),
            "selection_source": safe_scalar(response.get("selection_source")),
            "intent_constraint_option_id": safe_scalar(response.get("intent_constraint_option_id")),
            "intent_constraint_reason": safe_scalar(response.get("intent_constraint_reason")),
            "candidate_count": safe_scalar(response.get("candidate_count")),
            "adapter_tool_decision_source": safe_scalar(response.get("adapter_tool_decision_source")),
            "adapter_model_selected_candidate_id": safe_scalar(
                response.get("adapter_model_selected_candidate_id")
            ),
            "adapter_initial_model_selected_candidate_id": safe_scalar(
                response.get("adapter_initial_model_selected_candidate_id")
            ),
            "adapter_rejected_model_selected_candidate_id": safe_scalar(
                response.get("adapter_rejected_model_selected_candidate_id")
            ),
            "adapter_agent_repair_attempted": response.get("adapter_agent_repair_attempted"),
            "adapter_agent_repair_succeeded": response.get("adapter_agent_repair_succeeded"),
            "adapter_agent_repair_reason": safe_scalar(response.get("adapter_agent_repair_reason")),
            "adapter_initial_missing_required_tool_calls": safe_string_list(
                response.get("adapter_initial_missing_required_tool_calls")
            ),
            "adapter_required_tool_calls": safe_string_list(response.get("adapter_required_tool_calls")),
            "adapter_missing_required_tool_calls": safe_string_list(
                response.get("adapter_missing_required_tool_calls")
            ),
            "adapter_required_tool_calls_satisfied": response.get("adapter_required_tool_calls_satisfied"),
            "build_option_decision_source": safe_scalar(response.get("build_option_decision_source")),
            "generated_build_option_status": safe_scalar(
                response.get("generated_build_option_status")
            ),
            "generated_candidate_id": safe_scalar(response.get("generated_candidate_id")),
            "adapter_memory_available": response.get("adapter_memory_available"),
            "adapter_memory_matched_case_id": safe_scalar(response.get("adapter_memory_matched_case_id")),
            "adapter_memory_case_hint": safe_scalar(response.get("adapter_memory_case_hint")),
            "adapter_tool_trace_names": safe_string_list(
                response.get("adapter_tool_trace_names")
            ),
            "adapter_build_action_plan_status": safe_scalar(
                response.get("adapter_build_action_plan_status")
            ),
            "adapter_build_action_plan_selected_candidate_id": safe_scalar(
                response.get("adapter_build_action_plan_selected_candidate_id")
            ),
            "adapter_build_action_plan_step_count": safe_scalar(
                response.get("adapter_build_action_plan_step_count")
            ),
            "adapter_build_action_plan_world_mutation_authority": safe_scalar(
                response.get("adapter_build_action_plan_world_mutation_authority")
            ),
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
    build_options = safe_build_option_summaries(entry.get("build_options"))
    reviewed_prompt_memory = safe_reviewed_prompt_memory(entry.get("reviewed_prompt_memory"))
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
            "tool_decision_source": safe_scalar(entry.get("tool_decision_source")),
            "label": safe_scalar(entry.get("label"), 200),
            "action": safe_scalar(first_action.get("type")),
            "build_kind": safe_scalar(_build_kind_from_sidecar_action(entry, first_action)),
            "build_material_name": safe_scalar(first_action.get("material")),
            "planned_node_writes": _planned_node_writes_from_actions(entry),
            "selected_option_id": safe_scalar(entry.get("selected_option_id"), 120),
            "selected_candidate_id": safe_scalar(entry.get("selected_option_id"), 120),
            "decision_reason": safe_scalar(entry.get("decision_reason"), 300),
            "required_tool_calls": safe_string_list(entry.get("required_tool_calls"), max_items=12),
            "missing_required_tool_calls": safe_string_list(entry.get("missing_required_tool_calls"), max_items=12),
            "required_tool_calls_satisfied": entry.get("required_tool_calls_satisfied"),
            "contract_kind": safe_scalar(prompt_contract.get("contract_kind")),
            "contract_satisfied": contract_satisfied,
            "correction_source": correction_source,
            "tool_trace_names": [
                bounded_text(item.get("tool_name"), 80)
                for item in tool_trace
                if isinstance(item, dict) and isinstance(item.get("tool_name"), str)
            ][:12],
            "action_count": len(entry.get("actions")) if isinstance(entry.get("actions"), list) else 0,
            "build_options": build_options,
            "build_option_count": len(build_options),
            "reviewed_prompt_memory": reviewed_prompt_memory,
            "reviewed_prompt_memory_matched_case_id": safe_scalar(
                reviewed_prompt_memory.get("matched_case_id"),
                180,
            ),
            "reviewed_prompt_memory_case_hint": safe_scalar(
                reviewed_prompt_memory.get("case_hint"),
                120,
            ),
        },
    })
    return finalize_candidate(candidate)


def _path_list_from_live_probe_inputs(paths: list[Path]) -> list[Path]:
    result: list[Path] = []
    for path in paths:
        if path.is_dir():
            result.extend(sorted(child for child in path.glob("*.json") if child.is_file()))
        else:
            result.append(path)
    return result


def _live_probe_checks_pass(case: dict[str, Any]) -> bool:
    checks = case.get("checks")
    if not isinstance(checks, dict) or not checks:
        return False
    return all(value is True for value in checks.values())


def _tool_trace_contains(tool_trace_names: list[str], required: list[str]) -> bool:
    cursor = 0
    for name in tool_trace_names:
        if cursor < len(required) and name == required[cursor]:
            cursor += 1
    return cursor == len(required)


def candidate_from_verified_live_probe_case(
    payload: dict[str, Any],
    case: dict[str, Any],
) -> dict[str, Any] | None:
    if payload.get("live_result_kind") != VERIFIED_LIVE_RESULT_KIND:
        return None
    if payload.get("ok") is not True or payload.get("status") != "pass":
        return None
    if case.get("ok") is not True or case.get("status") != "pass":
        return None
    if not _live_probe_checks_pass(case):
        return None

    prompt = case.get("prompt")
    reply = case.get("reply") if isinstance(case.get("reply"), dict) else {}
    trace = case.get("trace") if isinstance(case.get("trace"), dict) else {}
    if not isinstance(prompt, str) or not prompt.strip():
        return None
    if reply.get("ok") is not True:
        return None
    if reply.get("action") != "build" or reply.get("status") != "queued":
        return None
    if reply.get("planner_mode") != "agentic_model_adapter":
        return None
    if reply.get("approved_action") != "build" or reply.get("auto_applied_approval") is not True:
        return None
    if reply.get("selected_candidate_id") != case.get("expected_candidate"):
        return None
    adapter_tool_decision_source = reply.get("adapter_tool_decision_source")
    if not is_accepted_agent_tool_decision_source(adapter_tool_decision_source):
        return None
    if reply.get("adapter_required_tool_calls_satisfied") is not True:
        return None
    missing_required = safe_string_list(reply.get("adapter_missing_required_tool_calls"))
    if missing_required:
        return None
    if reply.get("adapter_build_action_plan_status") != "ready":
        return None
    if reply.get("adapter_build_action_plan_world_mutation_authority") != "luanti":
        return None

    expected_writes = safe_int(case.get("expected_writes"), minimum=0)
    planned_writes = safe_int(reply.get("planned_node_writes"), minimum=0)
    if expected_writes is not None and planned_writes != expected_writes:
        return None
    if not isinstance(reply.get("build_kind"), str) or not reply.get("build_kind"):
        return None
    if not isinstance(reply.get("build_material_name"), str) or not reply.get("build_material_name"):
        return None

    tool_trace_names = safe_string_list(reply.get("adapter_tool_trace_names"), max_items=12)
    selected_id = safe_scalar(reply.get("selected_candidate_id"))
    required_tools = ["recall_build_prompt_memory", "select_build_option", "plan_build_actions"]
    generated_status = None
    if isinstance(selected_id, str) and selected_id.startswith("generated_"):
        required_tools = [
            "recall_build_prompt_memory",
            "propose_build_option",
            "select_build_option",
            "plan_build_actions",
        ]
        if reply.get("agentic_tool_success_required") is False:
            return None
        if reply.get("generated_candidate_id") != selected_id:
            return None
        if reply.get("generated_build_option_status") not in {"ready", "validated"}:
            return None
        generated_status = "ready"
    if not _tool_trace_contains(tool_trace_names, required_tools):
        return None

    candidate = _base_candidate(
        VERIFIED_LIVE_PROBE_KIND,
        safe_scalar(payload.get("generated_at")),
        prompt,
    )
    candidate.update({
        "owner": "LiveProbe",
        "agent_id": "nova_agent:live_probe",
        "task_id": safe_scalar(case.get("case_id")),
        "route": safe_scalar(trace.get("route") or "agentic_build_planner"),
        "action": "build",
        "prompt_source": "verified_live_probe.case.prompt",
        "observed_ok": True,
        "observed_status": "queued",
        "observed_reason": None,
        "observed": {
            "action": "build",
            "status": "queued",
            "route": safe_scalar(trace.get("route") or "agentic_build_planner"),
            "build_kind": safe_scalar(reply.get("build_kind")),
            "build_material_name": safe_scalar(reply.get("build_material_name")),
            "build_material_node": safe_scalar(reply.get("build_material_node")),
            "build_width": safe_int(reply.get("build_width"), minimum=1),
            "build_depth": safe_int(reply.get("build_depth"), minimum=1),
            "build_height": safe_int(reply.get("build_height"), minimum=1),
            "build_count": safe_int(reply.get("build_count"), minimum=1),
            "planned_node_writes": planned_writes,
            "planner_mode": "agentic_model_adapter",
            "selected_option_id": selected_id,
            "selected_candidate_id": selected_id,
            "tool_decision_source": safe_scalar(adapter_tool_decision_source),
            "required_tool_calls": required_tools,
            "missing_required_tool_calls": [],
            "required_tool_calls_satisfied": True,
            "tool_trace_names": tool_trace_names,
            "build_action_plan_status": "ready",
            "build_action_plan_selected_option_id": selected_id,
            "build_action_plan_step_count": safe_int(
                reply.get("adapter_build_action_plan_step_count"),
                minimum=0,
            ),
            "build_action_plan_world_mutation_authority": "luanti",
            "generated_option_id": safe_scalar(reply.get("generated_candidate_id")),
            "generated_option_status": generated_status,
            "generated_option_build_kind": safe_scalar(reply.get("build_kind")),
            "generated_option_build_material_name": safe_scalar(reply.get("build_material_name")),
            "generated_option_build_width": safe_int(reply.get("build_width"), minimum=1),
            "generated_option_build_depth": safe_int(reply.get("build_depth"), minimum=1),
            "generated_option_build_height": safe_int(reply.get("build_height"), minimum=1),
            "generated_option_build_count": safe_int(reply.get("build_count"), minimum=1),
            "generated_option_planned_node_writes": planned_writes,
            "live_probe_case_id": safe_scalar(case.get("case_id")),
            "live_probe_node_count": safe_int(case.get("node_count"), minimum=0),
            "live_probe_non_air_count": safe_int(case.get("non_air_count"), minimum=0),
        },
    })
    return finalize_candidate(candidate)


def _read_verified_live_probe_candidates(
    paths: list[Path],
    violations: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], int, int, int]:
    candidates: list[dict[str, Any]] = []
    files_read = 0
    cases_read = 0
    skipped_private = 0
    for path in _path_list_from_live_probe_inputs(paths):
        if not path.is_file():
            violations.append({"kind": "missing_verified_live_probe", "details": str(path)})
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            violations.append({"kind": "invalid_verified_live_probe_json", "details": str(path)})
            continue
        if not isinstance(payload, dict):
            violations.append({"kind": "invalid_verified_live_probe_payload", "details": str(path)})
            continue
        live_result_kind = payload.get("live_result_kind")
        if live_result_kind == PROMPT_EVAL_LIVE_RESULT_KIND:
            continue
        if live_result_kind != VERIFIED_LIVE_RESULT_KIND:
            violations.append({
                "kind": "invalid_verified_live_probe_kind",
                "details": str(live_result_kind),
            })
            continue
        files_read += 1
        if has_private_content(payload) or has_forbidden_key(payload):
            skipped_private += 1
            violations.append({
                "kind": "skipped_private_verified_live_probe",
                "details": str(path),
            })
            continue
        if payload.get("ok") is not True or payload.get("status") != "pass":
            violations.append({
                "kind": "verified_live_probe_not_passed",
                "details": str(path),
            })
            continue
        raw_cases = payload.get("cases")
        if not isinstance(raw_cases, list):
            violations.append({
                "kind": "verified_live_probe_missing_cases",
                "details": str(path),
            })
            continue
        for index, case in enumerate(raw_cases, start=1):
            if not isinstance(case, dict):
                violations.append({
                    "kind": "invalid_verified_live_probe_case",
                    "details": f"{path}:{index}",
                })
                continue
            cases_read += 1
            candidate = candidate_from_verified_live_probe_case(payload, case)
            if candidate:
                candidates.append(candidate)
            else:
                violations.append({
                    "kind": "verified_live_probe_case_not_promotable",
                    "details": bounded_text(case.get("case_id") or index, 120),
                })
    return candidates, files_read, cases_read, skipped_private


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


def _read_request_response_log_gate_candidates(
    paths: list[Path],
    violations: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], int, int, int]:
    candidates: list[dict[str, Any]] = []
    files_read = 0
    cases_read = 0
    skipped_private = 0
    for path in paths:
        if not path.is_file():
            violations.append({"kind": "missing_request_response_log_gate", "details": str(path)})
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            violations.append({"kind": "invalid_request_response_log_gate_json", "details": str(path)})
            continue
        if not isinstance(payload, dict):
            violations.append({"kind": "invalid_request_response_log_gate_payload", "details": str(path)})
            continue
        if payload.get("artifact_kind") != REQUEST_RESPONSE_LOG_GATE_KIND:
            violations.append({
                "kind": "invalid_request_response_log_gate_kind",
                "details": str(payload.get("artifact_kind")),
            })
            continue
        files_read += 1
        if has_private_content(payload) or has_forbidden_key(payload):
            skipped_private += 1
            violations.append({
                "kind": "skipped_private_request_response_log_gate",
                "details": str(path),
            })
            continue
        if payload.get("status") != "pass":
            violations.append({
                "kind": "request_response_log_gate_not_passed",
                "details": str(path),
            })
        raw_cases = payload.get("cases")
        if not isinstance(raw_cases, list):
            violations.append({
                "kind": "request_response_log_gate_missing_cases",
                "details": str(path),
            })
            continue
        for index, case in enumerate(raw_cases, start=1):
            if not isinstance(case, dict):
                violations.append({
                    "kind": "invalid_request_response_log_gate_case",
                    "details": f"{path}:{index}",
                })
                continue
            cases_read += 1
            candidate = candidate_from_request_response_log_gate_case(payload, case)
            if candidate:
                candidates.append(candidate)
            elif case.get("status") != "pass":
                violations.append({
                    "kind": "request_response_log_gate_case_not_passed",
                    "details": bounded_text(case.get("case_id") or index, 120),
                })
    return candidates, files_read, cases_read, skipped_private


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
            try:
                candidate = candidate_from_nova_trace(payload)
            except (AttributeError, TypeError, ValueError) as exc:
                violations.append({
                    "kind": "skipped_invalid_nova_request_trace",
                    "details": f"{path}:{line_number}:{type(exc).__name__}",
                })
                continue
            if candidate:
                candidates.append(candidate)
    return candidates, read_entries, skipped_private


def _dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[tuple[str, str, str], dict[str, Any]] = {}
    order: list[tuple[str, str, str]] = []
    for candidate in candidates:
        if candidate.get("observed_ok") is True and candidate.get("ready_for_prompt_eval") is True:
            key = (
                str(candidate.get("source_kind") or ""),
                str(candidate.get("case_hint") or ""),
                normalized_prompt(candidate.get("prompt")),
            )
        else:
            key = ("candidate_id", str(candidate.get("candidate_id") or ""), "")
        if key not in seen:
            seen[key] = candidate
            order.append(key)
            continue
        previous = seen[key]
        if str(candidate.get("observed_at") or "") > str(previous.get("observed_at") or ""):
            seen[key] = candidate
    return [seen[key] for key in order]


def _candidate_learning_rank(candidate: dict[str, Any]) -> int:
    if candidate.get("ready_for_adapter_contract_eval") is True:
        return 0
    if candidate.get("source_kind") == REQUEST_RESPONSE_LOG_GATE_SOURCE_KIND:
        return 1
    if isinstance(candidate.get("adapter_contract_resolution"), dict):
        return 2
    if candidate.get("source_kind") == "nova_agent_sidecar_request_response":
        return 3
    expected = candidate.get("expected") if isinstance(candidate.get("expected"), dict) else {}
    selected = expected.get("selected_candidate_id")
    if (
        str(candidate.get("case_hint") or "").startswith("generated_")
        or (isinstance(selected, str) and selected.startswith("generated_"))
    ):
        return 4
    if candidate.get("source_kind") == VERIFIED_LIVE_PROBE_KIND:
        return 5
    if isinstance(candidate.get("operator_label"), dict):
        return 6
    if candidate.get("ready_for_prompt_eval") is True:
        return 7
    return 8


def _candidate_sort_key(candidate: dict[str, Any]) -> tuple[int, int, str, str]:
    priority_rank = 0 if candidate.get("priority") == "high" else 1
    learning_rank = _candidate_learning_rank(candidate)
    ready_rank = "0" if candidate.get("ready_for_prompt_eval") is True else "1"
    return (priority_rank, learning_rank, ready_rank, str(candidate.get("candidate_id") or ""))


def build_eval_candidate_queue(
    *,
    agents_sdk_logs: list[Path] | None = None,
    request_response_log_gate_paths: list[Path] | None = None,
    nova_agent_logs: list[Path] | None = None,
    action_logs: list[Path] | None = None,
    verified_live_probe_paths: list[Path] | None = None,
    operator_label_files: list[Path] | None = None,
    operator_label_payloads: list[dict[str, Any]] | None = None,
    generated_at: str | None = None,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict[str, Any]:
    violations: list[dict[str, str]] = []
    agents_sdk_logs = agents_sdk_logs or []
    request_response_log_gate_paths = request_response_log_gate_paths or []
    nova_agent_logs = nova_agent_logs or []
    action_logs = action_logs or []
    verified_live_probe_paths = verified_live_probe_paths or []
    operator_label_files = operator_label_files or []
    operator_label_payloads = operator_label_payloads or []
    generated_at = generated_at or utc_now()

    sdk_candidates, sdk_entries, sdk_private = _read_jsonl_candidates(agents_sdk_logs, violations)
    gate_candidates, gate_files, gate_cases, gate_private = _read_request_response_log_gate_candidates(
        request_response_log_gate_paths,
        violations,
    )
    nova_agent_candidates, nova_agent_entries, nova_agent_private = _read_nova_agent_log_candidates(
        nova_agent_logs,
        violations,
    )
    trace_candidates, trace_entries, trace_private = _read_action_log_candidates(action_logs, violations)
    live_probe_candidates, live_probe_files, live_probe_cases, live_probe_private = (
        _read_verified_live_probe_candidates(verified_live_probe_paths, violations)
    )
    file_label_payloads = read_operator_label_payloads(operator_label_files, violations)
    candidates = _dedupe_candidates(
        sdk_candidates
        + gate_candidates
        + nova_agent_candidates
        + trace_candidates
        + live_probe_candidates
    )
    label_summary = apply_operator_labels(candidates, file_label_payloads + operator_label_payloads, violations)
    resolution_summary = apply_adapter_contract_resolutions(candidates)
    candidates.sort(key=_candidate_sort_key)
    truncated = len(candidates) > max_candidates
    candidates = candidates[:max(0, max_candidates)]

    ready_count = sum(1 for item in candidates if item.get("ready_for_prompt_eval") is True)
    manual_count = sum(1 for item in candidates if _candidate_requires_manual_review(item))
    contract_summary = adapter_contract_summary(candidates)
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
            "request_response_log_gate_files_read": gate_files,
            "request_response_log_gate_cases_read": gate_cases,
            "request_response_log_gate_candidates_added": len(gate_candidates),
            "nova_agent_log_entries_read": nova_agent_entries,
            "nova_request_traces_read": trace_entries,
            "verified_live_probe_files_read": live_probe_files,
            "verified_live_probe_cases_read": live_probe_cases,
            "verified_live_probe_candidates_added": len(live_probe_candidates),
            "entries_skipped_private": (
                sdk_private + gate_private + nova_agent_private + trace_private + live_probe_private
            ),
            "candidates_total": len(candidates),
            "ready_for_prompt_eval": ready_count,
            **contract_summary,
            "operator_labels_read": label_summary["operator_labels_read"],
            "operator_labels_applied": label_summary["operator_labels_applied"],
            "manual_review_required": manual_count,
            "review_required": True,
            "adapter_contract_failures_resolved_in_source": resolution_summary[
                "adapter_contract_failures_resolved"
            ],
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
            "private_entries_skipped": (
                sdk_private + gate_private + nova_agent_private + trace_private + live_probe_private
            ),
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
            1 for item in payload["candidates"] if _candidate_requires_manual_review(item)
        )
        payload["source_summary"].update(adapter_contract_summary(payload["candidates"]))
        payload["source_summary"]["operator_labels_applied"] = sum(
            1 for item in payload["candidates"] if isinstance(item.get("operator_label"), dict)
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
    parser.add_argument(
        "--request-response-log-gate",
        action="append",
        default=[],
        help="Request/response log gate JSON path.",
    )
    parser.add_argument("--nova-agent-log", action="append", default=[], help="Nova sidecar request JSONL log path.")
    parser.add_argument("--action-log", action="append", default=[], help="Luanti action/debug log path containing request_trace JSON.")
    parser.add_argument("--verified-live-probe", action="append", default=[], help="Verified Nova auto-apply live probe JSON file or directory.")
    parser.add_argument("--operator-labels", action="append", default=[], help="Reviewed operator label JSON path.")
    parser.add_argument("--output", required=True, help="Output candidate queue JSON path.")
    parser.add_argument("--generated-at", default=None, help="ISO timestamp for deterministic artifacts.")
    parser.add_argument("--max-candidates", type=int, default=DEFAULT_MAX_CANDIDATES)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    root = resolve_path(Path.cwd(), args.root).resolve()
    agents_sdk_logs = [resolve_path(root, path) for path in args.agents_sdk_log]
    request_response_log_gate_paths = [
        resolve_path(root, path)
        for path in args.request_response_log_gate
    ]
    nova_agent_logs = [resolve_path(root, path) for path in args.nova_agent_log]
    action_logs = [resolve_path(root, path) for path in args.action_log]
    verified_live_probe_paths = [resolve_path(root, path) for path in args.verified_live_probe]
    operator_label_files = [resolve_path(root, path) for path in args.operator_labels]
    output = resolve_path(root, args.output)

    payload = build_eval_candidate_queue(
        agents_sdk_logs=agents_sdk_logs,
        request_response_log_gate_paths=request_response_log_gate_paths,
        nova_agent_logs=nova_agent_logs,
        action_logs=action_logs,
        verified_live_probe_paths=verified_live_probe_paths,
        operator_label_files=operator_label_files,
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
