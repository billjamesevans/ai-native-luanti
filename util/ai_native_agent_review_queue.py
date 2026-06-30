#!/usr/bin/env python3
"""Build a public-safe review queue for Nova agent improvement work."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any


sys.path.insert(0, str(Path(__file__).resolve().parent))
import ai_native_agent_eval_promote as eval_promote
import ai_native_agent_eval_queue as eval_queue


REVIEW_KIND = "ai_native_agent_review_queue"
DEFAULT_MAX_BYTES = 24000
DEFAULT_MAX_ITEMS = 20


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return root / path


def relative_label(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)


def bounded_text(value: Any, max_bytes: int = 1000) -> str | None:
    if value is None:
        return None
    text = str(value)
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _safe_expected_summary(expected: Any) -> dict[str, Any]:
    if not isinstance(expected, dict):
        return {}
    return {
        "action": bounded_text(expected.get("action"), 80),
        "build_kind": bounded_text(expected.get("build_kind"), 80),
        "build_material_name": bounded_text(expected.get("build_material_name"), 80),
        "planned_node_writes": expected.get("planned_node_writes")
        if isinstance(expected.get("planned_node_writes"), int) else None,
        "forbidden_extra_structure": expected.get("forbidden_extra_structure") is True,
    }


def _safe_observed_summary(observed: Any) -> dict[str, Any]:
    if not isinstance(observed, dict):
        return {}
    missing_tools = observed.get("missing_required_tool_calls")
    if not isinstance(missing_tools, list):
        missing_tools = observed.get("adapter_missing_required_tool_calls")
    return {
        "selected_option_id": bounded_text(
            observed.get("selected_option_id")
            or observed.get("build_option_selected_option_id")
            or observed.get("live_probe_selected_candidate_id"),
            120,
        ),
        "tool_decision_source": bounded_text(
            observed.get("tool_decision_source")
            or observed.get("adapter_tool_decision_source"),
            120,
        ),
        "required_tool_calls_satisfied": observed.get("required_tool_calls_satisfied") is True
        or observed.get("adapter_required_tool_calls_satisfied") is True,
        "missing_required_tool_calls": [
            bounded_text(item, 80)
            for item in missing_tools
            if isinstance(item, str)
        ][:8] if isinstance(missing_tools, list) else [],
        "live_probe_case_id": bounded_text(observed.get("live_probe_case_id"), 120),
    }


def _candidate_review_reason(candidate: dict[str, Any]) -> str | None:
    if candidate.get("ready_for_adapter_contract_eval") is True:
        return "adapter_contract_eval_required"
    if candidate.get("adapter_contract_review_status") == "adapter_contract_regression":
        return "adapter_contract_regression"
    if candidate.get("review_status") == "manual_review_required":
        return "manual_review_required"
    if candidate.get("ready_for_prompt_eval") is not True:
        return "prompt_eval_expectation_missing"
    return None


def _candidate_review_rank(candidate: dict[str, Any], reason: str) -> tuple[int, str]:
    priority = str(candidate.get("priority") or "")
    if reason.startswith("adapter_contract"):
        return (0, str(candidate.get("observed_at") or ""))
    if priority == "high":
        return (1, str(candidate.get("observed_at") or ""))
    if reason == "manual_review_required":
        return (2, str(candidate.get("observed_at") or ""))
    return (3, str(candidate.get("observed_at") or ""))


def _candidate_item(candidate: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "candidate_id": bounded_text(candidate.get("candidate_id"), 160),
        "prompt": bounded_text(candidate.get("prompt"), 1000),
        "case_hint": bounded_text(candidate.get("case_hint"), 120),
        "source_kind": bounded_text(candidate.get("source_kind"), 120),
        "priority": bounded_text(candidate.get("priority"), 40),
        "review_status": bounded_text(candidate.get("review_status"), 80),
        "review_reason": reason,
        "ready_for_prompt_eval": candidate.get("ready_for_prompt_eval") is True,
        "ready_for_adapter_contract_eval": candidate.get("ready_for_adapter_contract_eval") is True,
        "adapter_contract_review_status": bounded_text(
            candidate.get("adapter_contract_review_status"), 120
        ),
        "expected": _safe_expected_summary(candidate.get("expected")),
        "observed": _safe_observed_summary(candidate.get("observed")),
    }


def _case_pack_summary(case_pack: dict[str, Any]) -> dict[str, Any]:
    summary = case_pack.get("summary") if isinstance(case_pack.get("summary"), dict) else {}
    cases = case_pack.get("cases") if isinstance(case_pack.get("cases"), list) else []
    case_hints = sorted({
        str(case.get("case_hint"))
        for case in cases
        if isinstance(case, dict) and isinstance(case.get("case_hint"), str)
    })
    return {
        "status": bounded_text(case_pack.get("status"), 80),
        "cases_total": summary.get("cases_total") if isinstance(summary.get("cases_total"), int) else len(cases),
        "ready_for_runtime_prompt_eval": summary.get("ready_for_runtime_prompt_eval"),
        "default_gate_eligible_cases": summary.get("default_gate_eligible_cases")
        if isinstance(summary.get("default_gate_eligible_cases"), int) else 0,
        "review_required_cases": summary.get("review_required_cases")
        if isinstance(summary.get("review_required_cases"), int) else len(cases),
        "auto_default_gate_min_sources": summary.get("auto_default_gate_min_sources")
        if isinstance(summary.get("auto_default_gate_min_sources"), int) else None,
        "requires_maintainer_review_before_default_gate":
            summary.get("requires_maintainer_review_before_default_gate") is True,
        "case_hints": case_hints[:50],
    }


def _promotable_case_keys(candidates: list[Any]) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        case = eval_promote.case_from_candidate(candidate)
        if case is None:
            continue
        keys.add((str(case.get("case_hint") or ""), str(case.get("prompt") or "")))
    return keys


def _case_pack_case_keys(case_pack: dict[str, Any]) -> set[tuple[str, str]]:
    cases = case_pack.get("cases") if isinstance(case_pack.get("cases"), list) else []
    keys: set[tuple[str, str]] = set()
    for case in cases:
        if not isinstance(case, dict):
            continue
        case_hint = case.get("case_hint")
        prompt = case.get("prompt")
        if isinstance(case_hint, str) and isinstance(prompt, str):
            keys.add((case_hint, prompt))
    return keys


def build_review_queue(
    candidate_queue: dict[str, Any],
    case_pack: dict[str, Any] | None = None,
    *,
    generated_at: str | None = None,
    candidate_queue_path: str | None = None,
    case_pack_path: str | None = None,
    max_items: int = DEFAULT_MAX_ITEMS,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict[str, Any]:
    generated_at = generated_at or utc_now()
    case_pack = case_pack or {}
    violations: list[dict[str, str]] = []
    if candidate_queue.get("artifact_kind") != eval_queue.REPORT_KIND:
        violations.append({
            "kind": "invalid_candidate_queue_kind",
            "details": str(candidate_queue.get("artifact_kind")),
        })
    if case_pack and case_pack.get("artifact_kind") != eval_promote.CASE_PACK_KIND:
        violations.append({
            "kind": "invalid_case_pack_kind",
            "details": str(case_pack.get("artifact_kind")),
        })
    if eval_queue.has_private_content(candidate_queue) or eval_queue.has_forbidden_key(candidate_queue):
        violations.append({"kind": "candidate_queue_not_public_safe", "details": "private content"})
    if case_pack and (eval_queue.has_private_content(case_pack) or eval_queue.has_forbidden_key(case_pack)):
        violations.append({"kind": "case_pack_not_public_safe", "details": "private content"})

    source_summary = candidate_queue.get("source_summary")
    source_summary = source_summary if isinstance(source_summary, dict) else {}
    raw_candidates = candidate_queue.get("candidates")
    raw_candidates = raw_candidates if isinstance(raw_candidates, list) else []

    review_items: list[tuple[tuple[int, str], dict[str, Any]]] = []
    for candidate in raw_candidates:
        if not isinstance(candidate, dict):
            continue
        reason = _candidate_review_reason(candidate)
        if not reason:
            continue
        review_items.append((_candidate_review_rank(candidate, reason), _candidate_item(candidate, reason)))
    review_items.sort(key=lambda item: item[0])
    truncated = len(review_items) > max_items
    items = [item for _, item in review_items[:max(0, max_items)]]

    action_items: list[dict[str, Any]] = []
    active_contract_failures = int(source_summary.get("adapter_contract_failures_active") or 0)
    ready_for_adapter_contract_eval = int(source_summary.get("ready_for_adapter_contract_eval") or 0)
    manual_review_required = int(source_summary.get("manual_review_required") or 0)
    ready_for_prompt_eval = int(source_summary.get("ready_for_prompt_eval") or 0)
    case_summary = _case_pack_summary(case_pack)
    cases_total = int(case_summary.get("cases_total") or 0)
    promotable_case_keys = _promotable_case_keys(raw_candidates)
    promoted_case_keys = _case_pack_case_keys(case_pack)
    unpromoted_case_keys = promotable_case_keys - promoted_case_keys

    if active_contract_failures or ready_for_adapter_contract_eval:
        action_items.append({
            "action": "run_adapter_contract_eval",
            "reason": "active_agent_tool_contract_regressions",
            "candidate_count": max(active_contract_failures, ready_for_adapter_contract_eval),
        })
    if manual_review_required or any(item["review_reason"] == "manual_review_required" for item in items):
        action_items.append({
            "action": "review_and_label_manual_candidates",
            "reason": "prompt_output_expectation_missing",
            "candidate_count": max(manual_review_required, sum(
                1 for item in items if item["review_reason"] == "manual_review_required"
            )),
        })
    if unpromoted_case_keys:
        action_items.append({
            "action": "refresh_prompt_eval_case_pack",
            "reason": "unique_ready_cases_missing_from_case_pack",
            "candidate_count": len(unpromoted_case_keys),
        })
    if cases_total == 0 and raw_candidates:
        action_items.append({
            "action": "promote_reviewed_cases",
            "reason": "case_pack_empty",
            "candidate_count": len(raw_candidates),
        })

    status = "attention" if action_items or items else "ready"
    if violations:
        status = "fail"
    payload = {
        "schema_version": 1,
        "artifact_kind": REVIEW_KIND,
        "generated_at": generated_at,
        "status": status,
        "source": {
            "candidate_queue_path": candidate_queue_path,
            "candidate_queue_status": bounded_text(candidate_queue.get("status"), 80),
            "candidate_queue_generated_at": bounded_text(candidate_queue.get("generated_at"), 80),
            "case_pack_path": case_pack_path,
            "case_pack_status": bounded_text(case_pack.get("status"), 80),
            "case_pack_generated_at": bounded_text(case_pack.get("generated_at"), 80),
        },
        "summary": {
            "candidates_total": len(raw_candidates),
            "review_items_total": len(review_items),
            "review_items_retained": len(items),
            "manual_review_required": manual_review_required,
            "ready_for_prompt_eval": ready_for_prompt_eval,
            "unique_ready_for_prompt_eval": len(promotable_case_keys),
            "ready_for_adapter_contract_eval": ready_for_adapter_contract_eval,
            "adapter_contract_failures_active": active_contract_failures,
            "adapter_contract_failures_resolved": source_summary.get(
                "adapter_contract_failures_resolved", 0
            ),
            "verified_live_probe_cases_read": source_summary.get(
                "verified_live_probe_cases_read", 0
            ),
            "operator_feedback_events_read": source_summary.get(
                "operator_feedback_events_read", 0
            ),
            "operator_labels_applied": source_summary.get("operator_labels_applied", 0),
            "case_pack_cases_total": cases_total,
            "case_pack_unique_cases_total": len(promoted_case_keys),
            "case_pack_default_gate_eligible_cases": case_summary.get(
                "default_gate_eligible_cases", 0
            ),
            "case_pack_review_required_cases": case_summary.get(
                "review_required_cases", cases_total
            ),
            "action_items_total": len(action_items),
        },
        "action_items": action_items,
        "review_items": items,
        "case_pack": case_summary,
        "violations": violations,
        "safety": {
            "public_safe_output": True,
            "no_world_mutation": True,
            "no_raw_assets": True,
            "no_provider_prompts": True,
            "no_family_world_coordinates": True,
            "review_artifact_only": True,
        },
        "bounds": {
            "max_items": max_items,
            "max_bytes": max_bytes,
            "output_bytes": 0,
            "truncated": truncated,
        },
    }
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    payload["bounds"]["output_bytes"] = len(encoded)
    if len(encoded) > max_bytes:
        payload["review_items"] = []
        payload["bounds"]["truncated"] = True
        payload["violations"].append({
            "kind": "review_queue_output_truncated",
            "details": "review_items removed to fit byte budget",
        })
        payload["bounds"]["output_bytes"] = len(json.dumps(payload, sort_keys=True).encode("utf-8"))
        if payload["bounds"]["output_bytes"] > max_bytes:
            payload["status"] = "fail"
    if eval_queue.has_private_content(payload) or eval_queue.has_forbidden_key(payload):
        payload["status"] = "fail"
        payload["violations"].append({
            "kind": "review_queue_not_public_safe",
            "details": "private content",
        })
    return payload


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a public-safe Nova agent review queue from eval memory artifacts.",
    )
    parser.add_argument("--root", default=".", help="Repository root for relative paths.")
    parser.add_argument("--candidate-queue", required=True, help="Candidate queue JSON path.")
    parser.add_argument("--case-pack", default=None, help="Prompt-eval case pack JSON path.")
    parser.add_argument("--output", required=True, help="Output review queue JSON path.")
    parser.add_argument("--generated-at", default=None, help="ISO timestamp for deterministic artifacts.")
    parser.add_argument("--max-items", type=int, default=DEFAULT_MAX_ITEMS)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    root = resolve_path(Path.cwd(), args.root).resolve()
    candidate_queue_path = resolve_path(root, args.candidate_queue)
    case_pack_path = resolve_path(root, args.case_pack) if args.case_pack else None
    output = resolve_path(root, args.output)
    candidate_queue = load_json(candidate_queue_path)
    case_pack = load_json(case_pack_path) if case_pack_path else {}
    report = build_review_queue(
        candidate_queue,
        case_pack,
        generated_at=args.generated_at,
        candidate_queue_path=relative_label(root, candidate_queue_path),
        case_pack_path=relative_label(root, case_pack_path) if case_pack_path else None,
        max_items=max(0, args.max_items),
        max_bytes=max(1000, args.max_bytes),
    )
    write_json(output, report)
    print(json.dumps({
        "review_queue": relative_label(root, output),
        "review_queue_status": report.get("status"),
        "review_items_total": report.get("summary", {}).get("review_items_total", 0),
        "action_items_total": report.get("summary", {}).get("action_items_total", 0),
        "manual_review_required": report.get("summary", {}).get("manual_review_required", 0),
        "ready_for_adapter_contract_eval": report.get("summary", {}).get(
            "ready_for_adapter_contract_eval", 0
        ),
    }, sort_keys=True))
    return 0 if report.get("status") != "fail" else 1


if __name__ == "__main__":
    raise SystemExit(main())
