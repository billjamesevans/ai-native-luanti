#!/usr/bin/env python3
"""Replay agent adapter-contract candidates against a loopback sidecar."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Callable
import urllib.error
import urllib.parse
import urllib.request


sys.path.insert(0, str(Path(__file__).resolve().parent))
import ai_native_agent_eval_queue as eval_queue


REPORT_KIND = "ai_native_agent_adapter_contract_eval_result"
DEFAULT_MAX_BYTES = 32000
DEFAULT_MAX_CASES = 25
DEFAULT_ENDPOINT = "http://127.0.0.1:8766/v1/model-adapter"
HEALTHY_TOOL_DECISION_SOURCE = eval_queue.PRIMARY_AGENT_TOOL_DECISION_SOURCE
HEALTHY_TOOL_DECISION_SOURCES = set(eval_queue.ACCEPTED_AGENT_TOOL_DECISION_SOURCES)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return root / path


def relative_label(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)


def loopback_endpoint(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    return parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}


def http_post_json(endpoint: str, payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, sort_keys=True).encode("utf-8"),
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return json.loads(exc.read().decode("utf-8"))


def string_list(value: Any, *, max_items: int = 12) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        eval_queue.bounded_text(item, 80)
        for item in value
        if isinstance(item, str)
    ][:max_items]


def response_summary(response: dict[str, Any]) -> dict[str, Any]:
    nested = response.get("response") if isinstance(response.get("response"), dict) else {}
    build_option = {}
    tool_decisions = nested.get("tool_decisions")
    if isinstance(tool_decisions, dict) and isinstance(tool_decisions.get("build_option"), dict):
        build_option = tool_decisions["build_option"]
    return {
        "ok": response.get("ok") is True,
        "response_kind": eval_queue.safe_scalar(response.get("response_kind")),
        "adapter_contract": eval_queue.safe_scalar(response.get("adapter_contract")),
        "adapter_name": eval_queue.safe_scalar(response.get("adapter_name")),
        "reason": eval_queue.safe_scalar(response.get("reason")),
        "agentic_execution": nested.get("agentic_execution"),
        "world_mutation_authority": eval_queue.safe_scalar(nested.get("world_mutation_authority")),
        "selected_option_id": eval_queue.safe_scalar(nested.get("selected_option_id")),
        "tool_decision_source": eval_queue.safe_scalar(nested.get("tool_decision_source")),
        "build_option_decision_source": eval_queue.safe_scalar(build_option.get("decision_source")),
        "required_tool_calls": string_list(nested.get("required_tool_calls")),
        "missing_required_tool_calls": string_list(nested.get("missing_required_tool_calls")),
        "required_tool_calls_satisfied": nested.get("required_tool_calls_satisfied"),
        "tool_trace_names": [
            eval_queue.bounded_text(item.get("tool_name"), 80)
            for item in nested.get("tool_trace", [])
            if isinstance(item, dict) and isinstance(item.get("tool_name"), str)
        ][:12],
    }


def expected_tool_decision_sources(expected: dict[str, Any]) -> list[str]:
    sources = string_list(expected.get("tool_decision_sources"))
    if sources:
        return sources
    source = expected.get("tool_decision_source") or HEALTHY_TOOL_DECISION_SOURCE
    if isinstance(source, str) and source == HEALTHY_TOOL_DECISION_SOURCE:
        return sorted(HEALTHY_TOOL_DECISION_SOURCES)
    return string_list([source])


def failures_from_checks(checks: dict[str, bool]) -> list[str]:
    return sorted(key for key, ok in checks.items() if ok is not True)


def selected_candidates(
    candidate_queue: dict[str, Any],
    selected_candidate_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    raw_candidates = candidate_queue.get("candidates") if isinstance(candidate_queue, dict) else []
    if not isinstance(raw_candidates, list):
        return []
    candidates = []
    for candidate in raw_candidates:
        if not isinstance(candidate, dict):
            continue
        if selected_candidate_ids is not None and str(candidate.get("candidate_id") or "") not in selected_candidate_ids:
            continue
        if candidate.get("ready_for_adapter_contract_eval") is True:
            candidates.append(candidate)
    return candidates


def replay_candidate(
    candidate: dict[str, Any],
    *,
    endpoint: str,
    timeout_seconds: float,
    request_runner: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    replay_request = candidate.get("adapter_replay_request")
    tool_contract = candidate.get("adapter_tool_contract") if isinstance(candidate.get("adapter_tool_contract"), dict) else {}
    expected = tool_contract.get("expected") if isinstance(tool_contract.get("expected"), dict) else {}
    observed = candidate.get("observed") if isinstance(candidate.get("observed"), dict) else {}
    case = {
        "candidate_id": eval_queue.safe_scalar(candidate.get("candidate_id"), 160),
        "source_kind": eval_queue.safe_scalar(candidate.get("source_kind"), 120),
        "prompt": eval_queue.safe_scalar(candidate.get("prompt"), 1000),
        "expected": {
            "required_tool_calls": string_list(expected.get("required_tool_calls")),
            "missing_required_tool_calls": string_list(expected.get("missing_required_tool_calls")),
            "required_tool_calls_satisfied": expected.get("required_tool_calls_satisfied"),
            "tool_decision_source": eval_queue.safe_scalar(
                expected.get("tool_decision_source") or HEALTHY_TOOL_DECISION_SOURCE
            ),
            "tool_decision_sources": expected_tool_decision_sources(expected),
            "selected_option_id": eval_queue.safe_scalar(
                observed.get("selected_option_id") or observed.get("build_option_selected_option_id")
            ),
        },
        "checks": {
            "replay_request_available": isinstance(replay_request, dict),
        },
    }
    if not isinstance(replay_request, dict):
        case.update({
            "status": "skipped",
            "ok": False,
            "reason": "adapter_replay_request_missing",
            "response": {},
            "failures": failures_from_checks(case["checks"]),
        })
        return case

    try:
        response = request_runner(replay_request) if request_runner else http_post_json(
            endpoint,
            replay_request,
            timeout_seconds,
        )
    except Exception as exc:
        case.update({
            "status": "fail",
            "ok": False,
            "reason": exc.__class__.__name__,
            "response": {},
            "failures": failures_from_checks(case["checks"]) + ["request_completed"],
        })
        return case

    summary = response_summary(response if isinstance(response, dict) else {})
    expected_required = set(case["expected"]["required_tool_calls"])
    actual_required = set(summary["required_tool_calls"])
    expected_selected = case["expected"]["selected_option_id"]
    checks = {
        **case["checks"],
        "request_completed": isinstance(response, dict),
        "response_ok": summary["ok"] is True,
        "response_kind": summary["response_kind"] == "ai_native_model_adapter_response",
        "adapter_contract": summary["adapter_contract"] == "provider_neutral_v1",
        "world_mutation_authority": summary["world_mutation_authority"] == "luanti",
        "required_tool_calls_present": expected_required.issubset(actual_required),
        "missing_required_tool_calls_empty": summary["missing_required_tool_calls"] == [],
        "required_tool_calls_satisfied": summary["required_tool_calls_satisfied"] is True,
        "tool_decision_source": summary["tool_decision_source"] in case["expected"]["tool_decision_sources"],
        "selected_option_id": expected_selected in {None, ""} or summary["selected_option_id"] == expected_selected,
        "no_forbidden_payload_keys": not eval_queue.has_forbidden_key(response),
    }
    failures = failures_from_checks(checks)
    case.update({
        "checks": checks,
        "response": summary,
        "status": "pass" if not failures else "fail",
        "ok": not failures,
        "failures": failures,
    })
    return case


def build_adapter_contract_eval(
    candidate_queue: dict[str, Any],
    *,
    endpoint: str = DEFAULT_ENDPOINT,
    generated_at: str | None = None,
    source_path: str | None = None,
    selected_candidate_ids: set[str] | None = None,
    timeout_seconds: float = 60.0,
    max_cases: int = DEFAULT_MAX_CASES,
    max_bytes: int = DEFAULT_MAX_BYTES,
    request_runner: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
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
    if eval_queue.has_private_content(candidate_queue) or eval_queue.has_forbidden_key(candidate_queue):
        violations.append({
            "kind": "candidate_queue_not_public_safe",
            "details": "private or forbidden content found",
        })
    if not loopback_endpoint(endpoint):
        violations.append({"kind": "endpoint_not_loopback", "details": endpoint})

    candidates = selected_candidates(candidate_queue, selected_candidate_ids)
    truncated = len(candidates) > max_cases
    candidates = candidates[:max(0, max_cases)]
    cases: list[dict[str, Any]] = []
    if not any(item["kind"] == "endpoint_not_loopback" for item in violations):
        for candidate in candidates:
            cases.append(
                replay_candidate(
                    candidate,
                    endpoint=endpoint,
                    timeout_seconds=timeout_seconds,
                    request_runner=request_runner,
                )
            )

    passed = sum(1 for case in cases if case.get("status") == "pass")
    failed = sum(1 for case in cases if case.get("status") == "fail")
    skipped = sum(1 for case in cases if case.get("status") == "skipped")
    status = "pass" if cases and failed == 0 and skipped == 0 and not violations else "fail"
    if not cases and not violations:
        status = "empty"
    payload = {
        "schema_version": 1,
        "artifact_kind": REPORT_KIND,
        "generated_at": generated_at,
        "status": status,
        "endpoint": endpoint,
        "source": {
            "candidate_queue_path": source_path,
            "candidate_queue_generated_at": candidate_queue.get("generated_at"),
            "candidate_queue_status": candidate_queue.get("status"),
        },
        "summary": {
            "source_candidates_total": len(candidate_queue.get("candidates", []))
            if isinstance(candidate_queue.get("candidates"), list)
            else 0,
            "selected_candidates_total": len(candidates),
            "replayed_total": len(cases),
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "truncated": truncated,
        },
        "cases": cases,
        "violations": violations,
        "safety": {
            "public_safe_output": True,
            "loopback_endpoint_only": True,
            "no_world_mutation": True,
            "no_raw_provider_payloads": True,
            "no_provider_credentials": True,
            "no_family_world_coordinates": True,
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
        payload["summary"]["replayed_total"] = len(payload["cases"])
        payload["summary"]["passed"] = sum(1 for case in payload["cases"] if case.get("status") == "pass")
        payload["summary"]["failed"] = sum(1 for case in payload["cases"] if case.get("status") == "fail")
        payload["summary"]["skipped"] = sum(1 for case in payload["cases"] if case.get("status") == "skipped")
        raw = json.dumps(payload, sort_keys=True)
    payload["bounds"]["output_bytes"] = len(json.dumps(payload, sort_keys=True).encode("utf-8"))
    if payload["bounds"]["output_bytes"] > max_bytes:
        payload["status"] = "fail"
        payload["violations"].append({
            "kind": "output_exceeds_max_bytes",
            "details": str(payload["bounds"]["output_bytes"]),
        })
    if eval_queue.has_private_content(payload) or eval_queue.has_forbidden_key(payload):
        payload["status"] = "fail"
        payload["safety"]["public_safe_output"] = False
        payload["violations"].append({
            "kind": "private_pattern_in_output",
            "details": "adapter contract eval result",
        })
    return payload


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay adapter-contract eval candidates against the loopback Agents SDK sidecar.",
    )
    parser.add_argument("--root", default=".", help="Repository root for relative paths.")
    parser.add_argument("--candidate-queue", required=True, help="Input candidate queue JSON path.")
    parser.add_argument("--output", required=True, help="Output adapter-contract eval JSON path.")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="Loopback model adapter endpoint.")
    parser.add_argument("--generated-at", default=None, help="ISO timestamp for deterministic artifacts.")
    parser.add_argument("--candidate-id", action="append", default=[], help="Only replay this candidate id; repeatable.")
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    parser.add_argument("--max-cases", type=int, default=DEFAULT_MAX_CASES)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
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
            "artifact_kind": REPORT_KIND,
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
        payload = build_adapter_contract_eval(
            candidate_queue,
            endpoint=args.endpoint,
            generated_at=args.generated_at,
            source_path=relative_label(root, candidate_queue_path),
            selected_candidate_ids=selected,
            timeout_seconds=args.timeout_seconds,
            max_cases=max(0, args.max_cases),
            max_bytes=max(1000, args.max_bytes),
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(output.relative_to(root) if output.is_relative_to(root) else output)
    return 0 if payload.get("status") not in {"fail"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
