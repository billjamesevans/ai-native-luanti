#!/usr/bin/env python3
"""Serve OpenRealm Studio with a public-safe live runtime status API."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
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
    "/opt/ai-native-luanti/src/local/review-packets/live-review-gate/live_trace11-gate-result.json"
)


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


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


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
            "latest": latest,
            "recent_traces": list(reversed(recent_traces)),
        }
    recent_successes = sum(1 for record in recent if record["ok"])
    recent_timeouts = sum(1 for record in recent if record["timeout"])
    recent_failures = len(recent) - recent_successes
    latest_ok = bool(latest and latest.get("ok") is True)
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

    def write_json(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(HTTPStatus.OK)
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
