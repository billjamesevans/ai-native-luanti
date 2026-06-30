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
    "local_agent_tool_contract_fast_path",
}
BASE_REQUIRED_TOOLS = {
    "recall_build_prompt_memory",
    "select_build_option",
    "plan_build_actions",
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
            "build_action_plan_status": bounded_text(plan.get("status"), 80),
            "build_action_plan_step_count": plan.get("step_count"),
            "world_mutation_authority": bounded_text(
                plan.get("world_mutation_authority") or body.get("world_mutation_authority"),
                80,
            ),
            "generated_option_status": bounded_text(option.get("generated_option_status"), 80),
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


def matching_entries(entries: list[dict[str, Any]], prompt: str) -> list[dict[str, Any]]:
    needle = normalized_prompt(prompt)
    return [
        entry
        for entry in entries
        if normalized_prompt(entry_prompt(entry)) == needle
    ]


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


def build_report(
    *,
    log_paths: list[Path],
    generated_at: str | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict[str, Any]:
    generated_at = generated_at or utc_now()
    entries, violations, source_summary = read_entries(log_paths)
    cases = [validate_case(case_def, entries) for case_def in CASE_DEFS]
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
    parser.add_argument("--agents-sdk-log", action="append", required=True, help="Agents SDK adapter JSONL log path.")
    parser.add_argument("--output", required=True, help="Output JSON report path.")
    parser.add_argument("--generated-at", default=None)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    root = resolve_path(Path.cwd(), args.root).resolve()
    log_paths = [resolve_path(root, value) for value in args.agents_sdk_log]
    output = resolve_path(root, args.output)
    report = build_report(
        log_paths=log_paths,
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
    }, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
