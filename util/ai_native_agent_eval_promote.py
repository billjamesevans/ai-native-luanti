#!/usr/bin/env python3
"""Promote reviewed agent eval candidates into replayable prompt-eval cases."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ai_native_agent_eval_queue as eval_queue


ROOT = Path(__file__).resolve().parents[1]
CASE_PACK_KIND = "ai_native_agent_prompt_eval_case_pack"
DEFAULT_MAX_BYTES = 24000
DEFAULT_MAX_CASES = 25
DEFAULT_AUTO_DEFAULT_GATE_MIN_SOURCES = 2
READY_REVIEW_STATUSES = {"candidate_ready", "operator_labeled_candidate_ready"}
AUTO_DEFAULT_GATE_REVIEW_STATUSES = {"candidate_ready"}
AUTO_DEFAULT_GATE_SOURCE_KINDS = {
    "agents_sdk_request_response",
    "nova_agent_sidecar_request_response",
    eval_queue.VERIFIED_LIVE_PROBE_KIND,
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


ALLOWED_EXPECTED_KEYS = {
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


def prompt_case_id(case_hint: str, candidate_id: str, prompt: str) -> str:
    digest = hashlib.sha256(
        json.dumps(
            {
                "case_hint": case_hint,
                "candidate_id": candidate_id,
                "prompt": prompt,
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return f"promoted_{case_hint}_{digest[:10]}"


def sanitize_expected(expected: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key in ALLOWED_EXPECTED_KEYS:
        if key not in expected:
            continue
        value = expected[key]
        if isinstance(value, (str, int, float, bool)) or value is None:
            sanitized[key] = value
    return sanitized


def _candidate_selected(candidate: dict[str, Any], selected_ids: set[str] | None) -> bool:
    if selected_ids is None:
        return True
    return str(candidate.get("candidate_id") or "") in selected_ids


def _case_evidence_key(case: dict[str, Any]) -> tuple[str, str, str]:
    expected = case.get("expected") if isinstance(case.get("expected"), dict) else {}
    return (
        str(case.get("case_hint") or ""),
        str(case.get("prompt") or ""),
        json.dumps(expected, sort_keys=True),
    )


def _candidate_tool_contract_passes(candidate: dict[str, Any]) -> bool:
    contract = candidate.get("adapter_tool_contract")
    if not isinstance(contract, dict):
        return False
    if contract.get("status") != "pass":
        return False
    if contract.get("required_tool_calls_satisfied") is not True:
        return False
    missing = contract.get("missing_required_tool_calls")
    return not missing


def _default_gate_evidence_entry(candidate: dict[str, Any]) -> dict[str, str]:
    return {
        "candidate_id": bounded_text(candidate.get("candidate_id"), 180),
        "source_kind": bounded_text(candidate.get("source_kind"), 120),
        "observed_at": bounded_text(candidate.get("observed_at"), 120),
    }


def _build_default_gate_evidence(
    candidates: list[Any],
    *,
    selected_candidate_ids: set[str] | None,
    min_sources: int,
) -> dict[tuple[str, str, str], dict[str, Any]]:
    raw_evidence: dict[tuple[str, str, str], list[dict[str, str]]] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        if not _candidate_selected(candidate, selected_candidate_ids):
            continue
        if candidate.get("review_status") not in AUTO_DEFAULT_GATE_REVIEW_STATUSES:
            continue
        if candidate.get("source_kind") not in AUTO_DEFAULT_GATE_SOURCE_KINDS:
            continue
        if not _candidate_tool_contract_passes(candidate):
            continue
        case = case_from_candidate(candidate)
        if case is None:
            continue
        raw_evidence.setdefault(_case_evidence_key(case), []).append(
            _default_gate_evidence_entry(candidate)
        )

    result: dict[tuple[str, str, str], dict[str, Any]] = {}
    for key, entries in raw_evidence.items():
        sources = sorted({
            str(entry.get("source_kind") or "")
            for entry in entries
            if entry.get("source_kind")
        })
        source_count = len(sources)
        result[key] = {
            "default_gate_eligible": source_count >= max(1, min_sources),
            "reason": (
                "verified_repeat_agent_tool_contract"
                if source_count >= max(1, min_sources)
                else "insufficient_independent_agent_tool_evidence"
            ),
            "evidence_count": len(entries),
            "independent_source_count": source_count,
            "required_independent_source_count": max(1, min_sources),
            "source_kinds": sources,
            "candidate_ids": [
                entry["candidate_id"]
                for entry in entries
                if entry.get("candidate_id")
            ][:8],
        }
    return result


def case_from_candidate(
    candidate: dict[str, Any],
    *,
    default_gate_evidence: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if candidate.get("ready_for_prompt_eval") is not True:
        return None
    review_status = candidate.get("review_status")
    if review_status not in READY_REVIEW_STATUSES:
        return None
    prompt = candidate.get("prompt")
    expected = candidate.get("expected")
    case_hint = candidate.get("case_hint")
    candidate_id = candidate.get("candidate_id")
    if not isinstance(prompt, str) or not prompt.strip():
        return None
    if not isinstance(expected, dict) or not isinstance(case_hint, str):
        return None
    if not isinstance(candidate_id, str):
        return None
    action = expected.get("action") or candidate.get("action") or "build"
    if action != "build":
        return None
    sanitized_expected = sanitize_expected(expected)
    if sanitized_expected.get("build_kind") is None:
        return None
    if sanitized_expected.get("build_material_name") is None:
        return None
    sanitized_expected["action"] = "build"
    promotion_mode = (
        "operator_label_overlay"
        if review_status == "operator_labeled_candidate_ready"
        else "candidate_ready_only"
    )
    default_gate_evidence = default_gate_evidence or {}
    default_gate_eligible = default_gate_evidence.get("default_gate_eligible") is True
    promotion = {
        "mode": promotion_mode,
        "review_status": review_status,
        "requires_maintainer_review_before_default_gate": not default_gate_eligible,
        "default_gate_eligible": default_gate_eligible,
    }
    if default_gate_evidence:
        promotion["default_gate_evidence"] = {
            "reason": default_gate_evidence.get("reason"),
            "evidence_count": default_gate_evidence.get("evidence_count", 0),
            "independent_source_count": default_gate_evidence.get("independent_source_count", 0),
            "required_independent_source_count": default_gate_evidence.get(
                "required_independent_source_count",
                DEFAULT_AUTO_DEFAULT_GATE_MIN_SOURCES,
            ),
            "source_kinds": default_gate_evidence.get("source_kinds", []),
            "candidate_ids": default_gate_evidence.get("candidate_ids", []),
        }
    return {
        "case_id": prompt_case_id(case_hint, candidate_id, prompt),
        "case_hint": bounded_text(case_hint, 120),
        "source_candidate_id": bounded_text(candidate_id, 160),
        "source_kind": bounded_text(candidate.get("source_kind"), 120),
        "prompt": bounded_text(prompt, 1000),
        "action": "build",
        "expected": sanitized_expected,
        "promotion": promotion,
    }


def _dedupe_cases(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, Any]] = []
    for case in cases:
        key = (str(case.get("case_hint") or ""), str(case.get("prompt") or ""))
        if key in seen:
            continue
        seen.add(key)
        result.append(case)
    return result


def _default_gate_eligible_case_count(cases: list[dict[str, Any]]) -> int:
    return sum(
        1
        for case in cases
        if isinstance(case.get("promotion"), dict)
        and case["promotion"].get("default_gate_eligible") is True
    )


def build_case_pack(
    candidate_queue: dict[str, Any],
    *,
    generated_at: str | None = None,
    source_path: str | None = None,
    selected_candidate_ids: set[str] | None = None,
    max_cases: int = DEFAULT_MAX_CASES,
    max_bytes: int = DEFAULT_MAX_BYTES,
    auto_default_gate_min_sources: int = DEFAULT_AUTO_DEFAULT_GATE_MIN_SOURCES,
) -> dict[str, Any]:
    generated_at = generated_at or utc_now()
    violations: list[dict[str, str]] = []
    if not isinstance(candidate_queue, dict):
        candidate_queue = {}
    if candidate_queue.get("artifact_kind") != eval_queue.REPORT_KIND:
        violations.append({
            "kind": "invalid_candidate_queue_kind",
            "details": str(candidate_queue.get("artifact_kind")),
        })
    if has_private_content(candidate_queue) or eval_queue.has_forbidden_key(candidate_queue):
        violations.append({
            "kind": "candidate_queue_not_public_safe",
            "details": "private or forbidden content found",
        })

    raw_candidates = candidate_queue.get("candidates")
    if not isinstance(raw_candidates, list):
        raw_candidates = []
        violations.append({"kind": "missing_candidates", "details": "candidates"})

    default_gate_evidence = _build_default_gate_evidence(
        raw_candidates,
        selected_candidate_ids=selected_candidate_ids,
        min_sources=auto_default_gate_min_sources,
    )
    cases: list[dict[str, Any]] = []
    ignored_not_ready = 0
    ignored_unselected = 0
    for candidate in raw_candidates:
        if not isinstance(candidate, dict):
            ignored_not_ready += 1
            continue
        if not _candidate_selected(candidate, selected_candidate_ids):
            ignored_unselected += 1
            continue
        base_case = case_from_candidate(candidate)
        evidence = default_gate_evidence.get(_case_evidence_key(base_case)) if base_case else None
        case = case_from_candidate(candidate, default_gate_evidence=evidence)
        if case is None:
            ignored_not_ready += 1
            continue
        cases.append(case)

    cases = _dedupe_cases(cases)
    truncated = len(cases) > max_cases
    cases = cases[:max(0, max_cases)]
    default_gate_eligible_cases = _default_gate_eligible_case_count(cases)
    review_required_cases = len(cases) - default_gate_eligible_cases
    status = "ready" if cases and not violations else "empty"
    if violations and cases:
        status = "attention"
    payload = {
        "schema_version": 1,
        "artifact_kind": CASE_PACK_KIND,
        "generated_at": generated_at,
        "status": status,
        "source": {
            "candidate_queue_path": source_path,
            "candidate_queue_generated_at": candidate_queue.get("generated_at"),
            "candidate_queue_status": candidate_queue.get("status"),
        },
        "summary": {
            "source_candidates_total": len(raw_candidates),
            "cases_total": len(cases),
            "ignored_not_ready": ignored_not_ready,
            "ignored_unselected": ignored_unselected,
            "ready_for_runtime_prompt_eval": len(cases),
            "default_gate_eligible_cases": default_gate_eligible_cases,
            "review_required_cases": review_required_cases,
            "requires_maintainer_review_before_default_gate": review_required_cases > 0,
            "auto_default_gate_min_sources": max(1, auto_default_gate_min_sources),
        },
        "cases": cases,
        "violations": violations,
        "safety": {
            "public_safe_output": True,
            "review_required_before_default_gate": True,
            "auto_default_gate_requires_verified_repeat": True,
            "auto_default_gate_requires_agent_tool_contract": True,
            "no_world_mutation": True,
            "no_raw_assets": True,
            "no_provider_prompts": True,
            "no_family_world_coordinates": True,
        },
        "runtime": {
            "runner": "core.ai_agent_plugin.run_prompt_eval",
            "cases_option": "custom",
            "custom_cases_field": "cases",
            "chat_command_import": False,
        },
        "bounds": {
            "max_cases": max_cases,
            "max_bytes": max_bytes,
            "output_bytes": 0,
            "truncated": truncated,
        },
    }

    raw = json.dumps(payload, sort_keys=True)
    while len(raw.encode("utf-8")) > max_bytes and payload["cases"]:
        payload["cases"].pop()
        payload["bounds"]["truncated"] = True
        payload["summary"]["cases_total"] = len(payload["cases"])
        payload["summary"]["ready_for_runtime_prompt_eval"] = len(payload["cases"])
        default_gate_eligible_cases = _default_gate_eligible_case_count(payload["cases"])
        payload["summary"]["default_gate_eligible_cases"] = default_gate_eligible_cases
        payload["summary"]["review_required_cases"] = (
            len(payload["cases"]) - default_gate_eligible_cases
        )
        payload["summary"]["requires_maintainer_review_before_default_gate"] = (
            payload["summary"]["review_required_cases"] > 0
        )
        raw = json.dumps(payload, sort_keys=True)
    payload["bounds"]["output_bytes"] = len(json.dumps(payload, sort_keys=True).encode("utf-8"))
    if payload["bounds"]["output_bytes"] > max_bytes:
        payload["status"] = "fail"
        payload["violations"].append({
            "kind": "output_exceeds_max_bytes",
            "details": str(payload["bounds"]["output_bytes"]),
        })
    if has_private_content(payload) or eval_queue.has_forbidden_key(payload):
        payload["status"] = "fail"
        payload["safety"]["public_safe_output"] = False
        payload["violations"].append({
            "kind": "private_pattern_in_output",
            "details": "case pack artifact",
        })
    return payload


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Promote agent eval candidates into replayable prompt-eval cases.",
    )
    parser.add_argument("--root", default=".", help="Repository root for relative paths.")
    parser.add_argument("--candidate-queue", required=True, help="Input candidate queue JSON path.")
    parser.add_argument("--output", required=True, help="Output prompt-eval case pack JSON path.")
    parser.add_argument("--generated-at", default=None, help="ISO timestamp for deterministic artifacts.")
    parser.add_argument("--candidate-id", action="append", default=[], help="Only promote this candidate id; repeatable.")
    parser.add_argument("--max-cases", type=int, default=DEFAULT_MAX_CASES)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument(
        "--auto-default-gate-min-sources",
        type=int,
        default=DEFAULT_AUTO_DEFAULT_GATE_MIN_SOURCES,
        help="Independent trusted source kinds required before a case is default-gate eligible.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    root = resolve_path(Path.cwd(), args.root).resolve()
    candidate_queue_path = resolve_path(root, args.candidate_queue)
    output = resolve_path(root, args.output)
    try:
        candidate_queue = json.loads(candidate_queue_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        payload = {
            "schema_version": 1,
            "artifact_kind": CASE_PACK_KIND,
            "generated_at": args.generated_at or utc_now(),
            "status": "fail",
            "cases": [],
            "violations": [{
                "kind": "candidate_queue_unreadable",
                "details": exc.__class__.__name__,
            }],
        }
    else:
        selected = set(args.candidate_id) if args.candidate_id else None
        payload = build_case_pack(
            candidate_queue,
            generated_at=args.generated_at,
            source_path=(
                candidate_queue_path.relative_to(root).as_posix()
                if candidate_queue_path.is_relative_to(root)
                else str(candidate_queue_path)
            ),
            selected_candidate_ids=selected,
            max_cases=max(0, args.max_cases),
            max_bytes=max(1000, args.max_bytes),
            auto_default_gate_min_sources=max(1, args.auto_default_gate_min_sources),
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(output.relative_to(root) if output.is_relative_to(root) else output)
    return 0 if payload.get("status") != "fail" else 1


if __name__ == "__main__":
    raise SystemExit(main())
