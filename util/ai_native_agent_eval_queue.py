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


def candidate_from_agents_sdk_entry(entry: dict[str, Any]) -> dict[str, Any] | None:
    request = entry.get("request") if isinstance(entry.get("request"), dict) else {}
    response = entry.get("response") if isinstance(entry.get("response"), dict) else {}
    prompt = request.get("public_prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return None
    nested = response.get("response") if isinstance(response.get("response"), dict) else {}
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
        "observed_ok": response.get("ok") is True,
        "observed_status": "success" if response.get("ok") is True else "failed",
        "observed_reason": safe_scalar(response.get("reason")),
        "observed": {
            "response_kind": safe_scalar(response.get("response_kind")),
            "adapter_name": safe_scalar(response.get("adapter_name")),
            "agentic_execution": nested.get("agentic_execution"),
            "world_mutation_authority": safe_scalar(nested.get("world_mutation_authority")),
            "tools_enabled": [
                bounded_text(item, 80)
                for item in nested.get("tools_enabled", [])
                if isinstance(item, str)
            ][:8],
        },
    })
    expected = expected_outcome_for(candidate["prompt"], candidate)
    candidate.update({
        "candidate_id": stable_candidate_id(candidate),
        "priority": candidate_priority(candidate, expected),
        **expected,
    })
    return candidate


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
        },
    })
    expected = expected_outcome_for(candidate["prompt"], candidate)
    candidate.update({
        "candidate_id": stable_candidate_id(candidate),
        "priority": candidate_priority(candidate, expected),
        **expected,
    })
    return candidate


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
    action_logs: list[Path] | None = None,
    generated_at: str | None = None,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict[str, Any]:
    violations: list[dict[str, str]] = []
    agents_sdk_logs = agents_sdk_logs or []
    action_logs = action_logs or []
    generated_at = generated_at or utc_now()

    sdk_candidates, sdk_entries, sdk_private = _read_jsonl_candidates(agents_sdk_logs, violations)
    trace_candidates, trace_entries, trace_private = _read_action_log_candidates(action_logs, violations)
    candidates = _dedupe_candidates(sdk_candidates + trace_candidates)
    candidates.sort(key=_candidate_sort_key)
    truncated = len(candidates) > max_candidates
    candidates = candidates[:max(0, max_candidates)]

    ready_count = sum(1 for item in candidates if item.get("ready_for_prompt_eval") is True)
    manual_count = sum(1 for item in candidates if item.get("ready_for_prompt_eval") is not True)
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
            "nova_request_traces_read": trace_entries,
            "entries_skipped_private": sdk_private + trace_private,
            "candidates_total": len(candidates),
            "ready_for_prompt_eval": ready_count,
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
            "private_entries_skipped": sdk_private + trace_private,
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
    action_logs = [resolve_path(root, path) for path in args.action_log]
    output = resolve_path(root, args.output)

    payload = build_eval_candidate_queue(
        agents_sdk_logs=agents_sdk_logs,
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
