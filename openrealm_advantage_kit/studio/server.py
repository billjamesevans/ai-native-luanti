#!/usr/bin/env python3
"""Serve OpenRealm Studio with a public-safe live runtime status API."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


SERVICE_SPECS = {
    "family": {"unit": "luanti-family.service", "port": 30000},
    "fork": {"unit": "ai-native-luanti-test.service", "port": 30001},
    "adapter": {"unit": "ai-native-luanti-agents-sdk-adapter.service", "port": 8766},
    "studio": {"unit": "openrealm-studio-ui.service", "port": 8788},
}

RECENT_ADAPTER_WINDOW = 50
RECENT_TRACE_LIMIT = 6
MAX_STUDIO_POST_BYTES = 48_000
MAX_STUDIO_PROMPT_BYTES = 1_000
MAX_STUDIO_FIELD_BYTES = 400
STUDIO_ADAPTER_ENDPOINT_DEFAULT = "http://127.0.0.1:8766/v1/model-adapter"
TRACE_ID_RE = re.compile(r"nova_trace:[A-Za-z0-9_.-]+")
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
PROMPT_EVAL_CASES = (
    ("build_fire", "Fire"),
    ("fire_only_strict", "Fire only"),
    ("tnt_wall", "TNT wall"),
    ("stone_bridge", "Stone bridge"),
    ("small_cabin", "Cabin"),
    ("path_to_hill", "Path"),
    ("agentic_build_planner", "Agentic planner"),
    ("openrealm_village", "OpenRealm village"),
    ("player_agent_loop", "Player loop"),
    ("natural_chat_followup", "Follow-up"),
    ("natural_pending_edit", "Pending edit"),
    ("model", "Model adapter"),
)
LIVE_REVIEW_GATE_KIND = "openrealm_live_review_gate_result"
LIVE_REVIEW_GATE_DEFAULT = (
    "/opt/ai-native-luanti/src/local/review-packets/live-review-gate/latest-gate-result.json"
)


class ApiError(Exception):
    def __init__(self, status: HTTPStatus, reason: str) -> None:
        super().__init__(reason)
        self.status = status
        self.reason = reason


def count_passed_refusal_gates(refusal_gates: dict[str, Any]) -> tuple[int, int]:
    if not isinstance(refusal_gates, dict):
        return 0, 0
    total = 0
    passed = 0
    for gate in refusal_gates.values():
        if not isinstance(gate, dict):
            continue
        total += 1
        if gate.get("passed") is True:
            passed += 1
    return passed, total


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def env_path(name: str, default: str) -> Path:
    return Path(os.environ.get(name, default))


def run_text(args: list[str], timeout: float = 2.0) -> str | None:
    try:
        result = subprocess.run(args, check=False, capture_output=True, text=True, timeout=timeout)
    except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def bounded_text(value: Any, max_bytes: int = MAX_STUDIO_FIELD_BYTES) -> str:
    text = str(value or "").strip()
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def has_private_content(value: Any) -> bool:
    raw = json.dumps(value, sort_keys=True) if not isinstance(value, str) else value
    return any(pattern.search(raw) for pattern in PRIVATE_PATTERNS)


def reject_private_payload(value: Any, reason: str = "unsafe_public_payload") -> None:
    if has_private_content(value) or has_forbidden_key(value):
        raise ApiError(HTTPStatus.BAD_REQUEST, reason)


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


def int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


def first_int(*values: Any) -> int | None:
    for value in values:
        candidate = int_or_none(value)
        if candidate is not None:
            return candidate
    return None


def first_text(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value:
            return value[:120]
    return None


def first_bool(*values: Any) -> bool | None:
    for value in values:
        if isinstance(value, bool):
            return value
    return None


def trace_id_from_task_id(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    match = TRACE_ID_RE.search(value)
    return match.group(0) if match else None


def service_status() -> dict[str, Any]:
    services: dict[str, Any] = {}
    for key, spec in SERVICE_SPECS.items():
        unit = spec["unit"]
        status = run_text(["systemctl", "is-active", unit])
        services[key] = {
            "unit": unit,
            "status": status or "unknown",
            "active": status == "active",
            "expected_port": spec["port"],
        }
    return services


def fork_status() -> dict[str, Any]:
    repo = env_path("OPENREALM_REPO_ROOT", "/opt/ai-native-luanti/src")
    server_bin = env_path("OPENREALM_SERVER_BIN", "/opt/ai-native-luanti/src/bin/luantiserver")
    commit = run_text(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"])
    version = None
    if server_bin.exists():
        version_text = run_text([str(server_bin), "--version"])
        if version_text:
            version = version_text.splitlines()[0]
    return {
        "commit": commit,
        "version": version,
        "commit_available": bool(commit),
        "version_available": bool(version),
    }


def live_review_gate_status() -> dict[str, Any]:
    path = env_path("OPENREALM_LIVE_REVIEW_GATE", LIVE_REVIEW_GATE_DEFAULT)
    if not path.exists():
        return {
            "present": False,
            "status": None,
            "current_health": "unknown",
            "checks_passed": 0,
            "checks_total": 0,
            "violations_total": 0,
            "public_safe_output": None,
            "unsafe_payload_rejected": False,
        }

    payload = read_json(path)
    if not payload:
        return {
            "present": True,
            "status": "invalid",
            "current_health": "fail",
            "checks_passed": 0,
            "checks_total": 0,
            "violations_total": 1,
            "public_safe_output": False,
            "unsafe_payload_rejected": True,
        }

    unsafe_payload = has_private_content(payload) or has_forbidden_key(payload)
    checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
    violations = payload.get("violations") if isinstance(payload.get("violations"), list) else []
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), dict) else {}
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    checks_total = len(checks)
    checks_passed = sum(1 for value in checks.values() if value is True)
    violations_total = len(violations)
    artifact_kind_ok = payload.get("artifact_kind") == LIVE_REVIEW_GATE_KIND
    public_safe_output = first_bool(safety.get("public_safe_output"))
    status = first_text(payload.get("status"))
    current_health = (
        "pass"
        if artifact_kind_ok
        and status == "pass"
        and checks_total > 0
        and checks_passed == checks_total
        and violations_total == 0
        and public_safe_output is True
        and not unsafe_payload
        else "fail"
    )

    return {
        "present": True,
        "status": status or "unknown",
        "current_health": current_health,
        "source_trace_id": first_text(payload.get("source_trace_id"), summary.get("source_trace_id")),
        "selected_option_id": first_text(payload.get("selected_option_id"), summary.get("selected_option_id")),
        "case_hint": first_text(payload.get("case_hint"), summary.get("case_hint")),
        "checks_passed": checks_passed,
        "checks_total": checks_total,
        "violations_total": violations_total,
        "artifact_count": len(artifacts),
        "artifact_keys": sorted(str(key)[:80] for key in artifacts.keys())[:8],
        "operator_label_matched": first_bool(summary.get("operator_label_matched")),
        "operator_labels_applied": first_int(summary.get("operator_labels_applied")),
        "candidate_queue_status": first_text(summary.get("candidate_queue_status")),
        "case_pack_status": first_text(summary.get("case_pack_status")),
        "cases_total": first_int(summary.get("cases_total")),
        "public_safe_output": public_safe_output is True and not unsafe_payload,
        "unsafe_payload_rejected": unsafe_payload,
        "safety": {
            "no_world_mutation": first_bool(safety.get("no_world_mutation")),
            "no_raw_assets": first_bool(safety.get("no_raw_assets")),
            "no_provider_prompts": first_bool(safety.get("no_provider_prompts")),
            "no_family_world_coordinates": first_bool(safety.get("no_family_world_coordinates")),
        },
    }


def quality_gate_status(live_review_gate: dict[str, Any] | None = None) -> dict[str, Any]:
    quality = read_json(env_path("OPENREALM_QUALITY_GATE", "/opt/ai-native-luanti/memory/ai-agent-quality-gate.json")) or {}
    prompt_eval = read_json(env_path("OPENREALM_PROMPT_EVAL", "/opt/ai-native-luanti/logs/live-probes/ai-agent-prompt-eval-live-latest.json")) or {}
    request_gate = read_json(env_path("OPENREALM_REQUEST_LOG_GATE", "/opt/ai-native-luanti/memory/ai-agent-request-response-log-gate.json")) or {}
    quality_summary = quality.get("summary") if isinstance(quality.get("summary"), dict) else {}
    prompt_summary = prompt_eval.get("summary") if isinstance(prompt_eval.get("summary"), dict) else {}
    request_summary = request_gate.get("summary") if isinstance(request_gate.get("summary"), dict) else {}
    live_review_gate = live_review_gate or live_review_gate_status()
    live_review_present = live_review_gate.get("present") is True
    live_review_health = live_review_gate.get("current_health")
    status = first_text(quality.get("status"))
    if live_review_present and live_review_health != "pass":
        status = "fail"
    elif not status and live_review_present:
        status = first_text(live_review_gate.get("status"))
    attention_total = first_int(quality_summary.get("attention_total"))
    violations_total = first_int(quality_summary.get("violations_total"))
    if live_review_present and live_review_health != "pass":
        attention_total = (attention_total or 0) + 1
    if live_review_present:
        violations_total = (violations_total or 0) + (first_int(live_review_gate.get("violations_total")) or 0)
    return {
        "status": status,
        "generated_at": quality.get("generated_at"),
        "live_prompt_eval_status": quality_summary.get("live_prompt_eval_status") or prompt_eval.get("status"),
        "compat_import_staging_pilot_status": quality_summary.get("compat_import_staging_pilot_status"),
        "violations_total": violations_total,
        "attention_total": attention_total,
        "prompt_eval_passed": prompt_summary.get("passed_cases") or prompt_eval.get("passed_cases"),
        "prompt_eval_total": prompt_summary.get("total_cases") or prompt_eval.get("total_cases"),
        "request_log_gate_status": request_gate.get("status"),
        "request_log_checked_cases": request_summary.get("checked_cases"),
        "request_log_violations": request_summary.get("violations_total"),
        "live_review_gate_status": live_review_gate.get("status"),
        "live_review_gate_health": live_review_health,
        "live_review_gate_checks_passed": live_review_gate.get("checks_passed"),
        "live_review_gate_checks_total": live_review_gate.get("checks_total"),
        "live_review_gate_violations": live_review_gate.get("violations_total"),
    }


def prompt_eval_status() -> dict[str, Any]:
    quality = read_json(env_path("OPENREALM_QUALITY_GATE", "/opt/ai-native-luanti/memory/ai-agent-quality-gate.json")) or {}
    prompt_eval = read_json(env_path("OPENREALM_PROMPT_EVAL", "/opt/ai-native-luanti/logs/live-probes/ai-agent-prompt-eval-live-latest.json")) or {}
    quality_summary = quality.get("summary") if isinstance(quality.get("summary"), dict) else {}
    summary = prompt_eval.get("summary") if isinstance(prompt_eval.get("summary"), dict) else {}
    eval_payload = prompt_eval.get("prompt_eval") if isinstance(prompt_eval.get("prompt_eval"), dict) else {}
    eval_case_ids = eval_payload.get("case_ids") if isinstance(eval_payload.get("case_ids"), dict) else {}
    golden_case_ids = summary.get("golden_prompt_case_ids") if isinstance(summary.get("golden_prompt_case_ids"), dict) else {}
    safety = prompt_eval.get("safety") if isinstance(prompt_eval.get("safety"), dict) else {}

    cases_total = first_int(summary.get("cases_total"), eval_payload.get("cases_total"), quality_summary.get("live_prompt_eval_cases_total"))
    cases_passed = first_int(summary.get("cases_passed"), eval_payload.get("cases_passed"), quality_summary.get("live_prompt_eval_cases_passed"))
    cases_failed = first_int(summary.get("cases_failed"), eval_payload.get("cases_failed"), quality_summary.get("live_prompt_eval_cases_failed"))
    golden_total = first_int(summary.get("golden_prompts_total"), quality_summary.get("live_prompt_eval_golden_prompts_total"))
    golden_passed = first_int(summary.get("golden_prompts_passed"), quality_summary.get("live_prompt_eval_golden_prompts_passed"))
    golden_failed = first_int(summary.get("golden_prompts_failed"), quality_summary.get("live_prompt_eval_golden_prompts_failed"))
    status = first_text(eval_payload.get("status"), quality_summary.get("live_prompt_eval_status"))
    no_world_mutation = first_bool(safety.get("no_world_mutation"), quality.get("safety", {}).get("no_world_mutation") if isinstance(quality.get("safety"), dict) else None)
    public_safe = first_bool(safety.get("public_safe_output"), quality.get("safety", {}).get("public_safe_output") if isinstance(quality.get("safety"), dict) else None)
    no_provider_prompts = first_bool(safety.get("no_provider_prompts"), quality.get("safety", {}).get("no_provider_prompts") if isinstance(quality.get("safety"), dict) else None)
    current_health = (
        "pass"
        if status == "pass"
        and cases_failed == 0
        and golden_failed == 0
        and no_world_mutation is True
        and public_safe is True
        and no_provider_prompts is True
        else "attention"
    )

    return {
        "present": bool(prompt_eval),
        "status": status,
        "current_health": current_health,
        "generated_at": prompt_eval.get("generated_at"),
        "cases_total": cases_total,
        "cases_passed": cases_passed,
        "cases_failed": cases_failed,
        "golden_prompt_suite": first_text(summary.get("golden_prompt_suite"), quality_summary.get("live_prompt_eval_golden_prompt_suite")),
        "golden_prompt_backlog_total": first_int(summary.get("golden_prompt_backlog_total"), quality_summary.get("live_prompt_eval_golden_prompt_backlog_total")),
        "golden_prompts_total": golden_total,
        "golden_prompts_passed": golden_passed,
        "golden_prompts_failed": golden_failed,
        "model_adapter_requests": first_int(summary.get("model_adapter_requests"), quality_summary.get("live_prompt_eval_model_adapter_requests")),
        "model_adapter_successes": first_int(summary.get("model_adapter_successes")),
        "model_adapter_failures": first_int(summary.get("model_adapter_failures")),
        "model_adapter_timeouts": first_int(summary.get("model_adapter_timeouts")),
        "agentic_tool_cases": first_int(quality_summary.get("live_prompt_eval_agentic_tool_cases")),
        "agentic_tool_cases_required": first_int(quality_summary.get("live_prompt_eval_agentic_tool_cases_required")),
        "coverage": [
            {
                "case_id": case_id,
                "label": label,
                "passed": bool(eval_case_ids.get(case_id) is True or golden_case_ids.get(case_id) is True),
                "golden": case_id in golden_case_ids,
            }
            for case_id, label in PROMPT_EVAL_CASES
        ],
        "safety": {
            "public_safe_output": public_safe,
            "no_world_mutation": no_world_mutation,
            "no_provider_prompts": no_provider_prompts,
            "no_family_world_coordinates": first_bool(safety.get("no_family_world_coordinates")),
            "no_raw_assets": first_bool(safety.get("no_raw_assets")),
            "read_only_prompt_eval": first_bool(safety.get("read_only_prompt_eval")),
        },
    }


def summarize_adapter_record(record: dict[str, Any]) -> dict[str, Any]:
    request = record.get("request") if isinstance(record.get("request"), dict) else {}
    response = record.get("response") if isinstance(record.get("response"), dict) else {}
    payload = response.get("response") if isinstance(response.get("response"), dict) else {}
    plan = payload.get("build_action_plan") if isinstance(payload.get("build_action_plan"), dict) else {}
    tool_decisions = payload.get("tool_decisions") if isinstance(payload.get("tool_decisions"), dict) else {}
    build_option = tool_decisions.get("build_option") if isinstance(tool_decisions.get("build_option"), dict) else {}
    selected_option_id = (
        payload.get("selected_option_id")
        or plan.get("selected_option_id")
        or build_option.get("selected_option_id")
    )
    planned_node_writes = (
        plan.get("planned_node_writes")
        or build_option.get("selected_planned_node_writes")
        or build_option.get("planned_node_writes")
    )
    tools_enabled = payload.get("tools_enabled") if isinstance(payload.get("tools_enabled"), list) else []
    return {
        "created_at": record.get("created_at"),
        "agent_id": request.get("agent_id"),
        "task_id": request.get("task_id"),
        "source_trace_id": first_text(
            payload.get("source_trace_id"),
            payload.get("trace_id"),
            request.get("source_trace_id"),
            request.get("trace_id"),
            trace_id_from_task_id(request.get("task_id")),
        ),
        "ok": response.get("ok"),
        "elapsed_ms": round((response.get("elapsed_us") or 0) / 1000, 1) if isinstance(response.get("elapsed_us"), int) else None,
        "agent_model_timeout": bool(payload.get("agent_model_timeout")),
        "agentic_execution": payload.get("agentic_execution"),
        "tool_decision_source": payload.get("tool_decision_source"),
        "selected_option_id": selected_option_id,
        "planned_node_writes": planned_node_writes,
        "required_tool_calls_satisfied": payload.get("required_tool_calls_satisfied"),
        "web_search_available": payload.get("web_search_available"),
        "world_mutation_authority": payload.get("world_mutation_authority"),
        "direct_world_mutation": bool(plan.get("direct_world_mutation")) if plan else False,
        "tool_count": len(tools_enabled),
        "tools_enabled": [str(tool) for tool in tools_enabled[:12]],
    }


def adapter_release_health(latest: dict[str, Any] | None) -> str:
    if not latest:
        return "unknown"
    if latest.get("ok") is not True:
        return "attention"
    if latest.get("agent_model_timeout") is True:
        return "attention"
    if latest.get("direct_world_mutation") is True:
        return "attention"
    if latest.get("agentic_execution") is True:
        if latest.get("required_tool_calls_satisfied") is not True:
            return "attention"
        if latest.get("world_mutation_authority") not in {None, "luanti"}:
            return "attention"
    return "pass"


def adapter_log_status() -> dict[str, Any]:
    path = env_path("OPENREALM_ADAPTER_LOG", "/opt/ai-native-luanti/logs/agents-sdk-model-adapter.jsonl")
    total = 0
    successes = 0
    failures = 0
    timeouts = 0
    latest: dict[str, Any] | None = None
    recent: deque[dict[str, Any]] = deque(maxlen=RECENT_ADAPTER_WINDOW)
    recent_traces: deque[dict[str, Any]] = deque(maxlen=RECENT_TRACE_LIMIT)
    if not path.exists():
        return {
            "present": False,
            "total_entries": 0,
            "successes": 0,
            "failures": 0,
            "timeouts": 0,
            "recent_window_entries": 0,
            "recent_successes": 0,
            "recent_failures": 0,
            "recent_timeouts": 0,
            "latest_ok": False,
            "current_health": "unknown",
            "release_health": "unknown",
            "recent_window_health": "unknown",
            "history_health": "unknown",
            "latest": None,
            "recent_traces": [],
        }
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(record, dict):
                    continue
                total += 1
                response = record.get("response") if isinstance(record.get("response"), dict) else {}
                payload = response.get("response") if isinstance(response.get("response"), dict) else {}
                if response.get("ok") is True:
                    successes += 1
                else:
                    failures += 1
                if payload.get("agent_model_timeout"):
                    timeouts += 1
                recent.append({
                    "ok": response.get("ok") is True,
                    "timeout": bool(payload.get("agent_model_timeout")),
                })
                latest = summarize_adapter_record(record)
                recent_traces.append(latest)
    except OSError:
        recent_successes = sum(1 for record in recent if record["ok"])
        recent_timeouts = sum(1 for record in recent if record["timeout"])
        recent_failures = len(recent) - recent_successes
        return {
            "present": False,
            "total_entries": total,
            "successes": successes,
            "failures": failures,
            "timeouts": timeouts,
            "recent_window_entries": len(recent),
            "recent_successes": recent_successes,
            "recent_failures": recent_failures,
            "recent_timeouts": recent_timeouts,
            "latest_ok": bool(latest and latest.get("ok") is True),
            "current_health": "unknown",
            "release_health": adapter_release_health(latest),
            "recent_window_health": "unknown",
            "history_health": "unknown",
            "latest": latest,
            "recent_traces": list(reversed(recent_traces)),
        }
    recent_successes = sum(1 for record in recent if record["ok"])
    recent_timeouts = sum(1 for record in recent if record["timeout"])
    recent_failures = len(recent) - recent_successes
    latest_ok = bool(latest and latest.get("ok") is True)
    release_health = adapter_release_health(latest)
    recent_window_health = "pass" if len(recent) > 0 and recent_failures == 0 and recent_timeouts == 0 else "attention"
    history_health = "pass" if total > 0 and failures == 0 and timeouts == 0 else "attention"
    return {
        "present": True,
        "total_entries": total,
        "successes": successes,
        "failures": failures,
        "timeouts": timeouts,
        "recent_window_entries": len(recent),
        "recent_successes": recent_successes,
        "recent_failures": recent_failures,
        "recent_timeouts": recent_timeouts,
        "latest_ok": latest_ok,
        "release_health": release_health,
        "recent_window_health": recent_window_health,
        "history_health": history_health,
        "current_health": "pass" if latest_ok and recent_failures == 0 and recent_timeouts == 0 else "attention",
        "latest": latest,
        "recent_traces": list(reversed(recent_traces)),
    }


def runtime_proofs_status() -> dict[str, Any]:
    nova = read_json(env_path(
        "OPENREALM_NOVA_AUTO_APPLY_PROBE",
        "/opt/ai-native-luanti/logs/live-probes/nova-auto-apply-live-world/ai-runtime-nova-auto-apply-live-result.json",
    )) or {}
    compat = read_json(env_path(
        "OPENREALM_COMPAT_IMPORT_PILOT",
        "/opt/ai-native-luanti/memory/ai-runtime-compat-import-staging-pilot-result.json",
    )) or {}

    nova_summary = nova.get("summary") if isinstance(nova.get("summary"), dict) else {}
    nova_safety = nova.get("safety") if isinstance(nova.get("safety"), dict) else {}
    compat_workflow = compat.get("workflow") if isinstance(compat.get("workflow"), dict) else {}
    compat_apply = compat_workflow.get("apply") if isinstance(compat_workflow.get("apply"), dict) else {}
    compat_rollback = compat_workflow.get("rollback") if isinstance(compat_workflow.get("rollback"), dict) else {}
    compat_benchmark = compat.get("benchmark_coverage") if isinstance(compat.get("benchmark_coverage"), dict) else {}
    compat_safety = compat.get("safety") if isinstance(compat.get("safety"), dict) else {}
    refusal_passed, refusal_total = count_passed_refusal_gates(compat.get("refusal_gates"))

    nova_status = first_text(nova.get("status"))
    nova_cases_total = first_int(nova_summary.get("cases_total"))
    nova_cases_passed = first_int(nova_summary.get("cases_passed"))
    nova_cases_failed = first_int(nova_summary.get("cases_failed"))
    compat_status = first_text(compat_benchmark.get("status"))
    compat_node_writes = first_int(compat_benchmark.get("actual_node_writes"), compat_apply.get("node_writes_actual"))
    compat_apply_chunks = first_int(compat_benchmark.get("actual_apply_chunks"), compat_apply.get("step_count"))
    compat_rollback_records = first_int(compat_apply.get("rollback_record_count"), compat_rollback.get("plan_record_count"))
    compat_rollback_execution_records = first_int(compat_rollback.get("rollback_execution_records"))
    current_health = (
        "pass"
        if nova_status == "pass"
        and nova_cases_failed == 0
        and nova_summary.get("rollback_checked") is True
        and nova_safety.get("world_mutation_authority") == "luanti"
        and compat_status == "pass"
        and refusal_total > 0
        and refusal_passed == refusal_total
        and compat_safety.get("no_live_family_world_mutation") is True
        and compat_safety.get("no_provider_prompts") is True
        and compat_safety.get("no_raw_assets") is True
        else "attention"
    )

    return {
        "current_health": current_health,
        "nova_auto_apply": {
            "present": bool(nova),
            "status": nova_status,
            "generated_at": nova.get("generated_at"),
            "cases_total": nova_cases_total,
            "cases_passed": nova_cases_passed,
            "cases_failed": nova_cases_failed,
            "auto_apply_checked": first_bool(nova_summary.get("auto_apply_checked")),
            "rollback_checked": first_bool(nova_summary.get("rollback_checked")),
            "agentic_build_planner_checked": first_bool(nova_summary.get("agentic_build_planner_checked")),
            "world_mutation_authority": first_text(nova_safety.get("world_mutation_authority")),
            "world_mutation_scope": first_text(nova_safety.get("world_mutation_scope")),
            "disposable_live_world_only": first_bool(nova_safety.get("disposable_live_world_only")),
            "no_provider_prompts": first_bool(nova_safety.get("no_provider_prompts")),
            "no_family_world_coordinates": first_bool(nova_safety.get("no_family_world_coordinates")),
        },
        "compat_import": {
            "present": bool(compat),
            "generated_at": compat.get("generated_at"),
            "status": compat_status,
            "actual_node_writes": compat_node_writes,
            "actual_apply_chunks": compat_apply_chunks,
            "actual_mapblock_churn": first_int(compat_benchmark.get("actual_mapblock_churn")),
            "rollback_record_count": compat_rollback_records,
            "rollback_execution_records": compat_rollback_execution_records,
            "refusal_gates_passed": refusal_passed,
            "refusal_gates_total": refusal_total,
            "all_refusal_gates_passed": first_bool(compat_safety.get("all_refusal_gates_passed")),
            "no_live_family_world_mutation": first_bool(compat_safety.get("no_live_family_world_mutation")),
            "no_provider_prompts": first_bool(compat_safety.get("no_provider_prompts")),
            "no_raw_assets": first_bool(compat_safety.get("no_raw_assets")),
            "staging_target_only": first_bool(compat_safety.get("staging_target_only")),
        },
    }


def build_status_payload() -> dict[str, Any]:
    services = service_status()
    live_review_gate = live_review_gate_status()
    return {
        "schema_version": 1,
        "generated_at": utc_now(),
        "public_safe": True,
        "live_bridge": True,
        "direct_world_mutation_by_ai": False,
        "services": services,
        "services_all_active": all(service["active"] for service in services.values()),
        "fork": fork_status(),
        "quality_gate": quality_gate_status(live_review_gate),
        "prompt_eval": prompt_eval_status(),
        "adapter_log": adapter_log_status(),
        "runtime_proofs": runtime_proofs_status(),
        "live_review_gate": live_review_gate,
        "studio_handoff": studio_handoff_status(),
        "studio_handoff_approval": studio_handoff_approval_status(),
    }


def clamp_int(value: Any, default: int = 0, minimum: int = 0, maximum: int = 10_000) -> int:
    if isinstance(value, bool):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def studio_submission_log_path() -> Path:
    configured = os.environ.get("OPENREALM_STUDIO_SUBMISSION_LOG")
    if configured:
        return Path(configured)
    repo = env_path("OPENREALM_REPO_ROOT", "/opt/ai-native-luanti/src")
    base = repo.parent if repo.name == "src" else repo
    return base / "logs" / "openrealm-studio-operator-submissions.jsonl"


def studio_runtime_handoff_log_path() -> Path:
    configured = os.environ.get("OPENREALM_STUDIO_RUNTIME_HANDOFF_LOG")
    if configured:
        return Path(configured)
    repo = env_path("OPENREALM_REPO_ROOT", "/opt/ai-native-luanti/src")
    base = repo.parent if repo.name == "src" else repo
    return base / "logs" / "openrealm-studio-runtime-handoffs.jsonl"


def studio_runtime_handoff_latest_path() -> Path:
    configured = os.environ.get("OPENREALM_STUDIO_RUNTIME_HANDOFF_LATEST")
    if configured:
        return Path(configured)
    repo = env_path("OPENREALM_REPO_ROOT", "/opt/ai-native-luanti/src")
    base = repo.parent if repo.name == "src" else repo
    return base / "logs" / "openrealm-studio-runtime-handoff-latest.json"


def studio_runtime_handoff_approval_log_path() -> Path:
    configured = os.environ.get("OPENREALM_STUDIO_RUNTIME_HANDOFF_APPROVAL_LOG")
    if configured:
        return Path(configured)
    repo = env_path("OPENREALM_REPO_ROOT", "/opt/ai-native-luanti/src")
    base = repo.parent if repo.name == "src" else repo
    return base / "logs" / "openrealm-studio-runtime-handoff-approvals.jsonl"


def studio_runtime_handoff_approval_latest_path() -> Path:
    configured = os.environ.get("OPENREALM_STUDIO_RUNTIME_HANDOFF_APPROVAL_LATEST")
    if configured:
        return Path(configured)
    repo = env_path("OPENREALM_REPO_ROOT", "/opt/ai-native-luanti/src")
    base = repo.parent if repo.name == "src" else repo
    return base / "logs" / "openrealm-studio-runtime-handoff-approval-latest.json"


def studio_adapter_endpoint() -> str:
    endpoint = os.environ.get("OPENREALM_MODEL_ADAPTER_ENDPOINT", STUDIO_ADAPTER_ENDPOINT_DEFAULT)
    parsed = urlparse(endpoint)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ApiError(HTTPStatus.BAD_REQUEST, "adapter_endpoint_must_be_loopback")
    return endpoint


def plan_action_count(plan: dict[str, Any]) -> int:
    for key in ("action_count", "node_writes", "planned_node_writes"):
        value = plan.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return clamp_int(value, maximum=10_000)
    actions = plan.get("actions")
    if isinstance(actions, list):
        return clamp_int(len(actions), maximum=10_000)
    return 0


def selected_candidate_for_prompt(public_prompt: str) -> str:
    prompt = public_prompt.lower()
    if (
        "only a fire" in prompt
        or (
            ("build a fire" in prompt or "build me a fire" in prompt)
            and "tnt" not in prompt
            and "wall" not in prompt
        )
    ):
        return "fire"
    if "tnt" in prompt and "wall" in prompt:
        return "tnt_wall"
    return "studio_preview"


def studio_candidate_summary(public_prompt: str, plan: dict[str, Any]) -> str:
    writes = max(1, plan_action_count(plan))
    entries = [
        ("fire", "fire", "fire", 1),
        ("tnt_wall", "wall", "tnt", 36),
        ("studio_preview", "openrealm_structure", "openrealm_template", writes),
    ]
    return "|".join(f"{option}:{kind}:{material}:{count}" for option, kind, material, count in entries)


def compact_public_plan(plan: Any) -> dict[str, Any]:
    if not isinstance(plan, dict):
        return {}
    safety = plan.get("safety") if isinstance(plan.get("safety"), dict) else {}
    return {
        "plan_id": bounded_text(plan.get("plan_id"), 120),
        "summary": bounded_text(plan.get("summary"), 240),
        "features": [bounded_text(item, 80) for item in plan.get("features", [])[:12]]
            if isinstance(plan.get("features"), list) else [],
        "materials": [bounded_text(item, 80) for item in plan.get("materials", [])[:16]]
            if isinstance(plan.get("materials"), list) else [],
        "node_writes": plan_action_count(plan),
        "safety": {
            "status": bounded_text(safety.get("status"), 80),
            "risk": bounded_text(safety.get("risk"), 80),
            "requires_approval": safety.get("requires_approval") is True,
            "rollback_policy": bounded_text(safety.get("rollback_policy"), 80),
        },
    }


def build_studio_model_adapter_request(payload: dict[str, Any], generated_at: str | None = None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ApiError(HTTPStatus.BAD_REQUEST, "invalid_json_payload")
    reject_private_payload(payload)
    public_prompt = bounded_text(payload.get("public_prompt") or payload.get("prompt"), MAX_STUDIO_PROMPT_BYTES)
    if not public_prompt:
        raise ApiError(HTTPStatus.BAD_REQUEST, "public_prompt_required")
    plan = compact_public_plan(payload.get("plan"))
    reject_private_payload({"public_prompt": public_prompt, "plan": plan})
    selected_candidate = selected_candidate_for_prompt(public_prompt)
    candidate_summary = studio_candidate_summary(public_prompt, plan)
    generated_at = generated_at or utc_now()
    task_seed = re.sub(r"[^A-Za-z0-9_.:-]+", "-", plan.get("plan_id") or "adhoc").strip("-")[:80]
    return {
        "schema_version": 1,
        "request_kind": "ai_native_model_adapter_request",
        "adapter_contract": "provider_neutral_v1",
        "agent_id": "nova_agent:OpenRealmStudio",
        "owner": "openrealm_studio_operator",
        "task_id": f"openrealm-studio:nova-plan:{generated_at}:{task_seed}",
        "public_prompt": public_prompt,
        "context": {
            "intent": "build_planning",
            "surface_id": "openrealm_studio",
            "capabilities": "http.llm,import.assets,world.place,world.remove,world.batch",
            "planner_reason": "studio_operator_submit",
            "player_request": public_prompt,
            "candidate_summary": candidate_summary,
            "selected_candidate_id": selected_candidate,
            "studio_plan_id": plan.get("plan_id") or "",
            "studio_plan_summary": plan.get("summary") or "",
            "studio_plan_node_writes": plan.get("node_writes") or 0,
            "studio_plan_risk": plan.get("safety", {}).get("risk") or "",
            "world_context": json.dumps({
                "surface_id": "openrealm_studio",
                "preview_source": "browser_openrealm_studio",
                "node_writes": plan.get("node_writes"),
                "safety_status": plan.get("safety", {}).get("status"),
                "risk": plan.get("safety", {}).get("risk"),
            }, sort_keys=True),
            "player_agent_loop": json.dumps({
                "status": "operator_submitted",
                "phase": "preview_to_agent_plan",
                "active_surface": "openrealm_studio",
                "active_goal": "turn public prompt into Luanti-authoritative preview/approval/task plan",
                "next_action": "return build_action_plan without direct world mutation",
            }, sort_keys=True),
        },
        "safety": {
            "public_safe_request": True,
            "private_input_retained": False,
            "no_provider_credentials": True,
            "no_raw_media_payloads": True,
        },
        "bounds": {
            "max_response_bytes": 4000,
            "max_context_keys": 16,
        },
    }


def http_post_json(url: str, payload: dict[str, Any], timeout_seconds: float = 60.0) -> tuple[int, dict[str, Any]]:
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read(256_000)
            data = json.loads(raw.decode("utf-8"))
            return int(response.status), data if isinstance(data, dict) else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read(64_000)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            data = {"ok": False, "reason": "adapter_http_error"}
        return int(exc.code), data if isinstance(data, dict) else {"ok": False, "reason": "adapter_http_error"}
    except (OSError, TimeoutError, json.JSONDecodeError) as exc:
        raise ApiError(HTTPStatus.BAD_GATEWAY, f"adapter_unavailable:{type(exc).__name__}") from exc


def summarize_studio_adapter_response(response: dict[str, Any]) -> dict[str, Any]:
    payload = response.get("response") if isinstance(response.get("response"), dict) else {}
    plan = payload.get("build_action_plan") if isinstance(payload.get("build_action_plan"), dict) else {}
    tool_trace = payload.get("tool_trace") if isinstance(payload.get("tool_trace"), list) else []
    summary = {
        "ok": response.get("ok") is True,
        "message": bounded_text(response.get("message"), 240),
        "reason": bounded_text(response.get("reason"), 160),
        "agentic_execution": payload.get("agentic_execution") is True,
        "tool_decision_source": bounded_text(payload.get("tool_decision_source"), 160),
        "selected_option_id": bounded_text(
            payload.get("selected_option_id")
            or plan.get("selected_option_id"),
            160,
        ),
        "planned_node_writes": first_int(plan.get("planned_node_writes")),
        "build_kind": bounded_text(plan.get("build_kind"), 120),
        "build_material_name": bounded_text(plan.get("build_material_name"), 120),
        "required_tool_calls_satisfied": payload.get("required_tool_calls_satisfied") is True,
        "missing_required_tool_calls": [
            bounded_text(item, 80)
            for item in payload.get("missing_required_tool_calls", [])[:12]
        ] if isinstance(payload.get("missing_required_tool_calls"), list) else [],
        "web_search_available": payload.get("web_search_available") is True,
        "world_mutation_authority": bounded_text(payload.get("world_mutation_authority"), 120),
        "direct_world_mutation": plan.get("direct_world_mutation") is True,
        "plan_status": bounded_text(plan.get("status"), 80),
        "plan_kind": bounded_text(plan.get("plan_kind"), 120),
        "plan_step_count": first_int(plan.get("step_count")),
        "tool_trace_names": [
            bounded_text(entry.get("tool_name"), 80)
            for entry in tool_trace[:12]
            if isinstance(entry, dict)
        ],
    }
    reject_private_payload(summary, "unsafe_adapter_summary")
    return summary


def write_studio_submission_log(entry: dict[str, Any]) -> bool:
    reject_private_payload(entry, "unsafe_submission_log")
    path = studio_submission_log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
        return True
    except OSError:
        return False


def runtime_handoff_id(submission: dict[str, Any], generated_at: str) -> str:
    adapter = submission.get("adapter") if isinstance(submission.get("adapter"), dict) else {}
    request = submission.get("request") if isinstance(submission.get("request"), dict) else {}
    context = request.get("context") if isinstance(request.get("context"), dict) else {}
    seed = "-".join([
        str(context.get("studio_plan_id") or "adhoc"),
        str(adapter.get("selected_option_id") or "no-option"),
        generated_at,
    ])
    cleaned = re.sub(r"[^A-Za-z0-9_.:-]+", "-", seed).strip("-")[:120] or "adhoc"
    return f"openrealm-studio-runtime-handoff:{cleaned}"


def build_studio_runtime_handoff(submission: dict[str, Any], generated_at: str) -> dict[str, Any]:
    request = submission.get("request") if isinstance(submission.get("request"), dict) else {}
    context = request.get("context") if isinstance(request.get("context"), dict) else {}
    adapter = submission.get("adapter") if isinstance(submission.get("adapter"), dict) else {}
    runtime_handoff = (
        submission.get("runtime_handoff")
        if isinstance(submission.get("runtime_handoff"), dict)
        else {}
    )
    selected_option_id = bounded_text(adapter.get("selected_option_id") or context.get("selected_candidate_id"), 120)
    planned_node_writes = first_int(adapter.get("planned_node_writes")) or 0
    handoff_id = runtime_handoff_id(submission, generated_at)
    luanti_task_id = re.sub(r"[^A-Za-z0-9_.:-]+", "-", handoff_id).strip("-")
    artifact = {
        "schema_version": 1,
        "artifact_kind": "openrealm_studio_runtime_handoff_v1",
        "created_at": generated_at,
        "handoff_id": handoff_id,
        "artifact_ref": f"openrealm-studio-runtime-handoff:{handoff_id}",
        "status": runtime_handoff.get("status") or "needs_operator_review",
        "source": {
            "surface_id": "openrealm_studio",
            "model_adapter_endpoint": "loopback",
            "agent_id": request.get("agent_id"),
            "owner": request.get("owner"),
            "source_task_id": request.get("task_id"),
            "public_prompt": request.get("public_prompt"),
            "selected_candidate_id": context.get("selected_candidate_id"),
            "candidate_summary": context.get("candidate_summary"),
            "studio_plan_id": context.get("studio_plan_id"),
            "studio_plan_node_writes": context.get("studio_plan_node_writes"),
        },
        "adapter_summary": adapter,
        "luanti_task_handoff": {
            "queue_contract": "core.queue_ai_task",
            "handoff_queued": False,
            "task_id": f"openrealm-studio:runtime-task:{luanti_task_id}",
            "label": f"OpenRealm Studio preview: {selected_option_id or 'review'}",
            "operation_label": "openrealm.studio.preview_approval",
            "selected_option_id": selected_option_id,
            "build_kind": adapter.get("build_kind"),
            "build_material_name": adapter.get("build_material_name"),
            "planned_node_writes": planned_node_writes,
            "plan_kind": adapter.get("plan_kind"),
            "plan_step_count": adapter.get("plan_step_count"),
            "required_capabilities": ["world.read", "world.place", "world.batch"],
            "preview_required": True,
            "approval_required": True,
            "rollback_required": True,
            "audit_required": True,
            "execute_after_approval_only": True,
            "world_mutation_authority": "luanti",
            "direct_world_mutation": False,
            "next_runtime_action": "create_luanti_preview_then_queue_after_operator_approval",
        },
        "safety": {
            "public_safe_output": True,
            "private_input_retained": False,
            "no_provider_credentials": True,
            "no_provider_prompts": True,
            "no_raw_assets": True,
            "no_family_world_coordinates": True,
            "direct_world_mutation": False,
            "world_mutation_authority": "luanti",
        },
    }
    reject_private_payload(artifact, "unsafe_runtime_handoff")
    return artifact


def write_studio_runtime_handoff(handoff: dict[str, Any]) -> bool:
    reject_private_payload(handoff, "unsafe_runtime_handoff")
    log_path = studio_runtime_handoff_log_path()
    latest_path = studio_runtime_handoff_latest_path()
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        latest_path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(handoff, sort_keys=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(encoded + "\n")
        latest_path.write_text(encoded + "\n", encoding="utf-8")
        return True
    except OSError:
        return False


def summarize_studio_runtime_handoff(handoff: dict[str, Any]) -> dict[str, Any]:
    reject_private_payload(handoff, "unsafe_runtime_handoff")
    task_handoff = handoff.get("luanti_task_handoff") if isinstance(handoff.get("luanti_task_handoff"), dict) else {}
    safety = handoff.get("safety") if isinstance(handoff.get("safety"), dict) else {}
    return {
        "present": True,
        "created_at": handoff.get("created_at"),
        "handoff_id": bounded_text(handoff.get("handoff_id"), 160),
        "artifact_ref": bounded_text(handoff.get("artifact_ref"), 180),
        "status": bounded_text(handoff.get("status"), 120),
        "queue_contract": bounded_text(task_handoff.get("queue_contract"), 80),
        "task_id": bounded_text(task_handoff.get("task_id"), 180),
        "handoff_queued": task_handoff.get("handoff_queued") is True,
        "selected_option_id": bounded_text(task_handoff.get("selected_option_id"), 120),
        "build_kind": bounded_text(task_handoff.get("build_kind"), 80),
        "build_material_name": bounded_text(task_handoff.get("build_material_name"), 80),
        "planned_node_writes": first_int(task_handoff.get("planned_node_writes")),
        "preview_required": task_handoff.get("preview_required") is True,
        "approval_required": task_handoff.get("approval_required") is True,
        "rollback_required": task_handoff.get("rollback_required") is True,
        "audit_required": task_handoff.get("audit_required") is True,
        "execute_after_approval_only": task_handoff.get("execute_after_approval_only") is True,
        "world_mutation_authority": bounded_text(task_handoff.get("world_mutation_authority"), 80),
        "direct_world_mutation": task_handoff.get("direct_world_mutation") is True,
        "public_safe_output": safety.get("public_safe_output") is True,
        "no_provider_prompts": safety.get("no_provider_prompts") is True,
        "no_family_world_coordinates": safety.get("no_family_world_coordinates") is True,
    }


def studio_handoff_status() -> dict[str, Any]:
    path = studio_runtime_handoff_latest_path()
    if not path.exists():
        return {
            "present": False,
            "status": "none",
            "current_health": "unknown",
            "latest": None,
        }
    payload = read_json(path)
    if not isinstance(payload, dict):
        return {
            "present": True,
            "status": "invalid",
            "current_health": "fail",
            "latest": None,
        }
    try:
        latest = summarize_studio_runtime_handoff(payload)
    except ApiError:
        return {
            "present": True,
            "status": "unsafe",
            "current_health": "fail",
            "latest": None,
        }
    current_health = (
        "pass"
        if latest["status"] == "ready_for_luanti_preview_approval_task"
        and latest["queue_contract"] == "core.queue_ai_task"
        and latest["preview_required"]
        and latest["approval_required"]
        and latest["rollback_required"]
        and latest["audit_required"]
        and latest["execute_after_approval_only"]
        and latest["world_mutation_authority"] == "luanti"
        and latest["direct_world_mutation"] is False
        and latest["public_safe_output"]
        and latest["no_provider_prompts"]
        and latest["no_family_world_coordinates"]
        else "attention"
    )
    return {
        "present": True,
        "status": latest["status"],
        "current_health": current_health,
        "latest": latest,
    }


def build_studio_handoff_approval_receipt(
    handoff: dict[str, Any],
    payload: dict[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    reject_private_payload(payload, "unsafe_handoff_approval")
    latest = summarize_studio_runtime_handoff(handoff)
    if latest["status"] != "ready_for_luanti_preview_approval_task":
        raise ApiError(HTTPStatus.CONFLICT, "handoff_not_ready_for_approval")
    if latest["queue_contract"] != "core.queue_ai_task":
        raise ApiError(HTTPStatus.CONFLICT, "handoff_queue_contract_invalid")
    if latest["handoff_queued"]:
        raise ApiError(HTTPStatus.CONFLICT, "handoff_already_queued")
    if latest["world_mutation_authority"] != "luanti" or latest["direct_world_mutation"]:
        raise ApiError(HTTPStatus.CONFLICT, "handoff_mutation_authority_invalid")
    for field in (
        "preview_required",
        "approval_required",
        "rollback_required",
        "audit_required",
        "execute_after_approval_only",
        "public_safe_output",
        "no_provider_prompts",
        "no_family_world_coordinates",
    ):
        if latest.get(field) is not True:
            raise ApiError(HTTPStatus.CONFLICT, f"handoff_{field}_missing")

    decision_status = bounded_text(payload.get("decision_status") or "approved", 40)
    if decision_status != "approved":
        raise ApiError(HTTPStatus.BAD_REQUEST, "decision_status_must_be_approved")
    generated_at = generated_at or utc_now()
    receipt = {
        "schema_version": 1,
        "receipt_kind": "openrealm_studio_runtime_handoff_approval_receipt",
        "event_kind": "openrealm_studio_runtime_handoff_approval",
        "created_at": generated_at,
        "operator": {
            "operator_id": bounded_text(payload.get("operator_id") or "operator:openrealm_studio", 120),
            "approval_source": "openrealm_studio_ui",
            "private_input_retained": False,
        },
        "handoff_id": latest["handoff_id"],
        "artifact_ref": latest["artifact_ref"],
        "task_id": latest["task_id"],
        "decision_status": decision_status,
        "queue_contract": latest["queue_contract"],
        "runtime_queue_status": "approved_waiting_for_luanti_consumer",
        "runtime_entrypoint": "core.ai_agent_plugin.consume_studio_runtime_handoff",
        "next_runtime_action": "consume_studio_runtime_handoff",
        "selected_option_id": latest["selected_option_id"],
        "build_kind": latest["build_kind"],
        "build_material_name": latest["build_material_name"],
        "planned_node_writes": latest["planned_node_writes"],
        "handoff_queued": False,
        "preview_required": latest["preview_required"],
        "approval_required": latest["approval_required"],
        "rollback_required": latest["rollback_required"],
        "audit_required": latest["audit_required"],
        "execute_after_approval_only": latest["execute_after_approval_only"],
        "world_mutation_authority": "luanti",
        "direct_world_mutation": False,
        "safety": {
            "public_safe_output": True,
            "approval_receipt_only": True,
            "no_direct_world_mutation": True,
            "no_provider_prompts": True,
            "no_raw_assets": True,
            "no_family_world_coordinates": True,
            "world_mutation_authority": "luanti",
        },
    }
    reject_private_payload(receipt, "unsafe_handoff_approval")
    return receipt


def write_studio_handoff_approval_receipt(receipt: dict[str, Any]) -> bool:
    reject_private_payload(receipt, "unsafe_handoff_approval")
    log_path = studio_runtime_handoff_approval_log_path()
    latest_path = studio_runtime_handoff_approval_latest_path()
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        latest_path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(receipt, sort_keys=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(encoded + "\n")
        latest_path.write_text(encoded + "\n", encoding="utf-8")
        return True
    except OSError:
        return False


def summarize_studio_handoff_approval_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    reject_private_payload(receipt, "unsafe_handoff_approval")
    safety = receipt.get("safety") if isinstance(receipt.get("safety"), dict) else {}
    return {
        "present": True,
        "created_at": receipt.get("created_at"),
        "receipt_kind": bounded_text(receipt.get("receipt_kind"), 120),
        "handoff_id": bounded_text(receipt.get("handoff_id"), 160),
        "artifact_ref": bounded_text(receipt.get("artifact_ref"), 180),
        "task_id": bounded_text(receipt.get("task_id"), 180),
        "decision_status": bounded_text(receipt.get("decision_status"), 80),
        "queue_contract": bounded_text(receipt.get("queue_contract"), 80),
        "runtime_queue_status": bounded_text(receipt.get("runtime_queue_status"), 120),
        "runtime_entrypoint": bounded_text(receipt.get("runtime_entrypoint"), 120),
        "next_runtime_action": bounded_text(receipt.get("next_runtime_action"), 120),
        "selected_option_id": bounded_text(receipt.get("selected_option_id"), 120),
        "build_kind": bounded_text(receipt.get("build_kind"), 80),
        "build_material_name": bounded_text(receipt.get("build_material_name"), 80),
        "planned_node_writes": first_int(receipt.get("planned_node_writes")),
        "handoff_queued": receipt.get("handoff_queued") is True,
        "direct_world_mutation": receipt.get("direct_world_mutation") is True,
        "world_mutation_authority": bounded_text(receipt.get("world_mutation_authority"), 80),
        "public_safe_output": safety.get("public_safe_output") is True,
        "approval_receipt_only": safety.get("approval_receipt_only") is True,
        "no_direct_world_mutation": safety.get("no_direct_world_mutation") is True,
        "no_provider_prompts": safety.get("no_provider_prompts") is True,
        "no_family_world_coordinates": safety.get("no_family_world_coordinates") is True,
    }


def studio_handoff_approval_status() -> dict[str, Any]:
    path = studio_runtime_handoff_approval_latest_path()
    if not path.exists():
        return {
            "present": False,
            "status": "none",
            "current_health": "unknown",
            "latest": None,
        }
    payload = read_json(path)
    if not isinstance(payload, dict):
        return {
            "present": True,
            "status": "invalid",
            "current_health": "fail",
            "latest": None,
        }
    try:
        latest = summarize_studio_handoff_approval_receipt(payload)
    except ApiError:
        return {
            "present": True,
            "status": "unsafe",
            "current_health": "fail",
            "latest": None,
        }
    current_health = (
        "pass"
        if latest["receipt_kind"] == "openrealm_studio_runtime_handoff_approval_receipt"
        and latest["decision_status"] == "approved"
        and latest["queue_contract"] == "core.queue_ai_task"
        and latest["runtime_queue_status"] == "approved_waiting_for_luanti_consumer"
        and latest["runtime_entrypoint"] == "core.ai_agent_plugin.consume_studio_runtime_handoff"
        and latest["handoff_queued"] is False
        and latest["direct_world_mutation"] is False
        and latest["world_mutation_authority"] == "luanti"
        and latest["public_safe_output"]
        and latest["approval_receipt_only"]
        and latest["no_direct_world_mutation"]
        and latest["no_provider_prompts"]
        and latest["no_family_world_coordinates"]
        else "attention"
    )
    return {
        "present": True,
        "status": latest["runtime_queue_status"],
        "current_health": current_health,
        "latest": latest,
    }


def approve_latest_studio_runtime_handoff(
    payload: dict[str, Any] | None = None,
    generated_at: str | None = None,
) -> tuple[HTTPStatus, dict[str, Any]]:
    payload = payload if isinstance(payload, dict) else {}
    reject_private_payload(payload, "unsafe_handoff_approval")
    handoff = read_json(studio_runtime_handoff_latest_path())
    if not isinstance(handoff, dict):
        raise ApiError(HTTPStatus.NOT_FOUND, "studio_runtime_handoff_missing")
    requested_handoff_id = payload.get("handoff_id")
    if requested_handoff_id and requested_handoff_id != handoff.get("handoff_id"):
        raise ApiError(HTTPStatus.CONFLICT, "studio_runtime_handoff_mismatch")
    receipt = build_studio_handoff_approval_receipt(
        handoff, payload=payload, generated_at=generated_at)
    written = write_studio_handoff_approval_receipt(receipt)
    summary = summarize_studio_handoff_approval_receipt(receipt)
    return HTTPStatus.OK, {
        "schema_version": 1,
        "event_kind": "openrealm_studio_runtime_handoff_approval_result",
        "generated_at": receipt["created_at"],
        "ok": written,
        "public_safe": True,
        "live_bridge": True,
        "approval_written": written,
        "runtime_queue_status": receipt["runtime_queue_status"],
        "world_mutation_authority": "luanti",
        "direct_world_mutation": False,
        "approval_receipt": receipt,
        "approval_summary": summary,
    }


def submit_studio_nova_plan(payload: dict[str, Any]) -> tuple[HTTPStatus, dict[str, Any]]:
    generated_at = utc_now()
    request_payload = build_studio_model_adapter_request(payload, generated_at=generated_at)
    endpoint = studio_adapter_endpoint()
    status, adapter_response = http_post_json(endpoint, request_payload)
    adapter_summary = summarize_studio_adapter_response(adapter_response)
    submission = {
        "schema_version": 1,
        "event_kind": "openrealm_studio_nova_plan_submission",
        "created_at": generated_at,
        "public_safe": True,
        "live_bridge": True,
        "direct_world_mutation": False,
        "model_adapter_endpoint": "loopback",
        "request": {
            "agent_id": request_payload["agent_id"],
            "owner": request_payload["owner"],
            "task_id": request_payload["task_id"],
            "public_prompt": request_payload["public_prompt"],
            "context": {
                "intent": request_payload["context"]["intent"],
                "surface_id": request_payload["context"]["surface_id"],
                "candidate_summary": request_payload["context"]["candidate_summary"],
                "selected_candidate_id": request_payload["context"]["selected_candidate_id"],
                "studio_plan_id": request_payload["context"].get("studio_plan_id"),
                "studio_plan_node_writes": request_payload["context"].get("studio_plan_node_writes"),
            },
            "safety": request_payload["safety"],
            "bounds": request_payload["bounds"],
        },
        "adapter_http_status": status,
        "adapter": adapter_summary,
        "runtime_handoff": {
            "status": "ready_for_luanti_preview_approval_task"
                if adapter_summary["ok"] and adapter_summary["plan_status"] == "ready"
                else "needs_operator_review",
            "world_mutation_authority": "luanti",
            "requires_preview": True,
            "requires_approval": True,
            "requires_rollback": True,
        },
    }
    runtime_handoff_artifact = build_studio_runtime_handoff(submission, generated_at)
    handoff_written = write_studio_runtime_handoff(runtime_handoff_artifact)
    submission["runtime_handoff"]["handoff_id"] = runtime_handoff_artifact["handoff_id"]
    submission["runtime_handoff"]["artifact_ref"] = runtime_handoff_artifact["artifact_ref"]
    submission["runtime_handoff"]["handoff_written"] = handoff_written
    logged = write_studio_submission_log(submission)
    response_status = HTTPStatus.OK if status < 400 and adapter_summary["ok"] else HTTPStatus.BAD_GATEWAY
    result_ok = response_status == HTTPStatus.OK
    return response_status, {
        "schema_version": 1,
        "event_kind": "openrealm_studio_nova_plan_submission_result",
        "generated_at": generated_at,
        "ok": result_ok,
        "public_safe": True,
        "live_bridge": True,
        "direct_world_mutation": False,
        "logged": logged,
        "adapter_http_status": status,
        "summary": adapter_summary,
        "runtime_handoff": submission["runtime_handoff"],
        "runtime_handoff_status": submission["runtime_handoff"]["status"],
        "runtime_handoff_artifact": summarize_studio_runtime_handoff(runtime_handoff_artifact),
        "runtime_handoff_written": handoff_written,
        "world_mutation_authority": submission["runtime_handoff"]["world_mutation_authority"],
        "submission": submission,
    }


class OpenRealmStudioHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, directory: str | None = None, **kwargs: Any) -> None:
        super().__init__(*args, directory=directory, **kwargs)

    def end_headers(self) -> None:
        if self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/status":
            self.write_json(build_status_payload())
            return
        if parsed.path == "/api/health":
            self.write_json({"ok": True, "generated_at": utc_now()})
            return
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path not in {"/api/nova/plan", "/api/studio/handoff/approve"}:
            self.write_json({"ok": False, "reason": "not_found"}, status=HTTPStatus.NOT_FOUND)
            return
        try:
            payload = self.read_json_body()
            if parsed.path == "/api/nova/plan":
                status, response = submit_studio_nova_plan(payload)
            else:
                status, response = approve_latest_studio_runtime_handoff(payload)
            self.write_json(response, status=status)
        except ApiError as exc:
            self.write_json({"ok": False, "reason": exc.reason}, status=exc.status)

    def read_json_body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, "invalid_content_length") from exc
        if length <= 0:
            raise ApiError(HTTPStatus.BAD_REQUEST, "empty_request_body")
        if length > MAX_STUDIO_POST_BYTES:
            raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "request_too_large")
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, "invalid_json") from exc
        if not isinstance(payload, dict):
            raise ApiError(HTTPStatus.BAD_REQUEST, "invalid_json_payload")
        return payload

    def write_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.environ.get("OPENREALM_STUDIO_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("OPENREALM_STUDIO_PORT", "8788")))
    parser.add_argument(
        "--root",
        default=os.environ.get(
            "OPENREALM_STUDIO_ROOT",
            str(Path(__file__).resolve().parents[1]),
        ),
        help="Directory containing studio/ and assets/.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    handler = lambda *handler_args, **handler_kwargs: OpenRealmStudioHandler(  # noqa: E731
        *handler_args,
        directory=str(root),
        **handler_kwargs,
    )
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"OpenRealm Studio serving {root} on http://{args.host}:{args.port}/studio/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
