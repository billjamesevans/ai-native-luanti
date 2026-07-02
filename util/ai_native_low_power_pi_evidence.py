#!/usr/bin/env python3
"""Collect public-safe low-power evidence from a side-by-side Pi test lane."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = ROOT / "local" / "benchmarks"
EVIDENCE_NAME = "pi-low-power-evidence.json"
SOAK_TARGETS = {
    "quick": {
        "minimum_duration_seconds": 0,
        "recommended_iterations": 1,
        "recommended_interval_seconds": 0,
        "next_target": "one-hour",
    },
    "one-hour": {
        "minimum_duration_seconds": 3600,
        "recommended_iterations": 13,
        "recommended_interval_seconds": 300,
        "next_target": "overnight",
    },
    "overnight": {
        "minimum_duration_seconds": 8 * 60 * 60,
        "recommended_iterations": 17,
        "recommended_interval_seconds": 1800,
        "next_target": None,
    },
}

PRIVATE_REDACTIONS = (
    (re.compile(r"/Users/[^\s\"']+"), "<local-path>"),
    (re.compile(r"/opt/ai-native-luanti[^\s\"']*"), "<remote-fork-path>"),
    (re.compile(r"\bminecraftpi(?:\.home)?\b", re.I), "<private-host>"),
    (re.compile(r"\b192\.168(?:\.\d{1,3}){2}\b"), "<private-ip>"),
    (re.compile(r"\bspacebase|themepark|showcase100|disneyland100\b", re.I), "<private-demo>"),
    (re.compile(r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}"), "<secret>"),
    (re.compile(r"\bOPENAI_API_KEY\b"), "<secret-env>"),
    (re.compile(r"\bprivate_prompt\b"), "<private-prompt>"),
    (re.compile(r"\basset_payload\b"), "<asset-payload>"),
)

PRIVATE_PATTERN = re.compile(
    r"minecraftpi|192\.168|/opt/ai-native-luanti|/Users/|"
    r"spacebase|themepark|showcase100|disneyland100|"
    r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY|private_prompt|asset_payload",
    re.I,
)


class CommandRun:
    def __init__(
        self,
        returncode: int,
        stdout: str = "",
        stderr: str = "",
        duration_seconds: float = 0.0,
    ) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.duration_seconds = duration_seconds


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def path_part(value: str | None) -> str:
    value = str(value or "unknown").strip() or "unknown"
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value)[:80]


def sanitize_text(value: str) -> str:
    sanitized = str(value).replace(str(ROOT), "<repo>")
    sanitized = sanitized.replace(str(Path.home()), "<home>")
    for pattern, replacement in PRIVATE_REDACTIONS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


def sanitize_value(value):
    if isinstance(value, dict):
        return {sanitize_text(key): sanitize_value(child) for key, child in value.items()}
    if isinstance(value, list):
        return [sanitize_value(child) for child in value]
    if isinstance(value, str):
        return sanitize_text(value)
    return value


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def run_subprocess(command: list[str], *, timeout: int | None = None) -> CommandRun:
    started = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return CommandRun(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        duration_seconds=time.monotonic() - started,
    )


def ssh_command(args, remote_command: str) -> list[str]:
    return [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={args.ssh_connect_timeout}",
        args.ssh_target,
        remote_command,
    ]


def remote_verify_command(args) -> str:
    date_arg = shlex.quote(args.date)
    commit_expr = shlex.quote(args.luanti_commit) if args.luanti_commit else "$(git rev-parse --short HEAD)"
    client_bin = shlex.quote(args.remote_client_bin)
    client_config_prefix = shlex.quote(args.remote_client_config_prefix)
    return "\n".join(
        [
            "set -euo pipefail",
            f"cd {shlex.quote(args.remote_repo)}",
            "commit=" + commit_expr,
            f"headless_client_config=$(mktemp {client_config_prefix})",
            "cleanup_headless_client_config() { rm -f \"$headless_client_config\"; }",
            "trap cleanup_headless_client_config EXIT",
            "printf '%s\\n' "
            "'video_driver = null' "
            "'enable_minimap = false' "
            "'enable_post_processing = false' "
            "'enable_client_modding = false' "
            "'viewing_range = 10' "
            "'mute_sound = true' "
            "> \"$headless_client_config\"",
            (
                "headless_player_command=$(printf "
                "'%s --config %s --go --address {host} --port {port} --name {name}' "
                f"{client_bin} \"$headless_client_config\")"
            ),
            "python3 util/ai_native_runtime_verify.py "
            "--hardware-class low-power-server "
            "--game-profile ai_runtime "
            f"--server-bin {shlex.quote(args.remote_server_bin)} "
            "--headless-player-command \"$headless_player_command\" "
            f"--headless-player-count {int(args.headless_player_count)} "
            f"--headless-player-timeout {float(args.headless_player_timeout)} "
            "--require-headless-player-probe "
            "--confirm-low-power-backup "
            f"--date {date_arg} "
            "--luanti-commit \"$commit\"",
        ]
    )


def remote_service_command(args) -> str:
    family_port = int(args.family_port)
    fork_port = int(args.fork_port)
    return "\n".join(
        [
            "set -euo pipefail",
            f"family_status=$(systemctl is-active {shlex.quote(args.family_service)} 2>/dev/null || true)",
            f"fork_status=$(systemctl is-active {shlex.quote(args.fork_service)} 2>/dev/null || true)",
            (
                f"if sudo ss -lunp | grep -q ':{family_port}'; "
                "then family_udp=true; else family_udp=false; fi"
            ),
            (
                f"if sudo ss -lunp | grep -q ':{fork_port}'; "
                "then fork_udp=true; else fork_udp=false; fi"
            ),
            f"fork_version=$({shlex.quote(args.remote_server_bin)} --version | head -n 1 || true)",
            f"fork_commit=$(git -C {shlex.quote(args.remote_repo)} rev-parse --short HEAD 2>/dev/null || true)",
            f"fork_restart_count=$(systemctl show {shlex.quote(args.fork_service)} -p NRestarts --value 2>/dev/null || true)",
            f"fork_active_enter_timestamp=$(systemctl show {shlex.quote(args.fork_service)} -p ActiveEnterTimestamp --value 2>/dev/null || true)",
            f"studio_status_url={shlex.quote(args.studio_status_url)}",
            f"studio_status_timeout={shlex.quote(str(args.studio_status_timeout))}",
            'printf "family_service_active=%s\\n" "$family_status"',
            'printf "fork_service_active=%s\\n" "$fork_status"',
            'printf "family_udp_listening=%s\\n" "$family_udp"',
            'printf "fork_udp_listening=%s\\n" "$fork_udp"',
            'printf "fork_version=%s\\n" "$fork_version"',
            'printf "fork_commit=%s\\n" "$fork_commit"',
            'printf "fork_restart_count=%s\\n" "${fork_restart_count:-unknown}"',
            'printf "fork_active_enter_timestamp=%s\\n" "${fork_active_enter_timestamp:-unknown}"',
            "python3 - \"$studio_status_url\" \"$studio_status_timeout\" <<'PY'",
            "import json",
            "import sys",
            "import urllib.request",
            "",
            "url = sys.argv[1]",
            "timeout = float(sys.argv[2])",
            "",
            "def value_at(payload, *path):",
            "    current = payload",
            "    for key in path:",
            "        if not isinstance(current, dict):",
            "            return None",
            "        current = current.get(key)",
            "    return current",
            "",
            "def emit(key, value):",
            "    if isinstance(value, bool):",
            "        value = 'true' if value else 'false'",
            "    elif value is None:",
            "        value = ''",
            "    print(f'studio_{key}={value}')",
            "",
            "try:",
            "    with urllib.request.urlopen(url, timeout=timeout) as response:",
            "        status = json.load(response)",
            "except Exception:",
            "    emit('status_present', False)",
            "    emit('status_health', 'unavailable')",
            "else:",
            "    emit('status_present', isinstance(status, dict))",
            "    emit('status_health', 'available')",
            "    emit('schema_version', value_at(status, 'schema_version'))",
            "    emit('public_safe', value_at(status, 'public_safe'))",
            "    emit('live_bridge', value_at(status, 'live_bridge'))",
            "    emit('direct_world_mutation_by_ai', value_at(status, 'direct_world_mutation_by_ai'))",
            "    emit('services_all_active', value_at(status, 'services_all_active'))",
            "    emit('quality_gate_status', value_at(status, 'quality_gate', 'status'))",
            "    emit('quality_gate_attention_total', value_at(status, 'quality_gate', 'attention_total'))",
            "    emit('quality_gate_violations_total', value_at(status, 'quality_gate', 'violations_total'))",
            "    emit('quality_gate_live_prompt_eval_status', value_at(status, 'quality_gate', 'live_prompt_eval_status'))",
            "    emit('quality_gate_live_review_gate_health', value_at(status, 'quality_gate', 'live_review_gate_health'))",
            "    emit('live_review_gate_status', value_at(status, 'live_review_gate', 'status'))",
            "    emit('live_review_gate_health', value_at(status, 'live_review_gate', 'current_health'))",
            "    emit('live_review_gate_source_trace_id', value_at(status, 'live_review_gate', 'source_trace_id'))",
            "    emit('live_review_gate_selected_option_id', value_at(status, 'live_review_gate', 'selected_option_id'))",
            "    emit('live_review_gate_checks_passed', value_at(status, 'live_review_gate', 'checks_passed'))",
            "    emit('live_review_gate_checks_total', value_at(status, 'live_review_gate', 'checks_total'))",
            "    emit('live_review_gate_violations_total', value_at(status, 'live_review_gate', 'violations_total'))",
            "    emit('live_review_gate_public_safe_output', value_at(status, 'live_review_gate', 'public_safe_output'))",
            "    emit('live_review_gate_unsafe_payload_rejected', value_at(status, 'live_review_gate', 'unsafe_payload_rejected'))",
            "    emit('live_review_gate_no_world_mutation', value_at(status, 'live_review_gate', 'safety', 'no_world_mutation'))",
            "    emit('live_review_gate_no_raw_assets', value_at(status, 'live_review_gate', 'safety', 'no_raw_assets'))",
            "    emit('live_review_gate_no_provider_prompts', value_at(status, 'live_review_gate', 'safety', 'no_provider_prompts'))",
            "    emit('live_review_gate_no_family_world_coordinates', value_at(status, 'live_review_gate', 'safety', 'no_family_world_coordinates'))",
            "    emit('prompt_eval_health', value_at(status, 'prompt_eval', 'current_health'))",
            "    emit('prompt_eval_status', value_at(status, 'prompt_eval', 'status'))",
            "    emit('prompt_eval_cases_total', value_at(status, 'prompt_eval', 'cases_total'))",
            "    emit('prompt_eval_cases_passed', value_at(status, 'prompt_eval', 'cases_passed'))",
            "    emit('prompt_eval_cases_failed', value_at(status, 'prompt_eval', 'cases_failed'))",
            "    emit('prompt_eval_golden_prompts_total', value_at(status, 'prompt_eval', 'golden_prompts_total'))",
            "    emit('prompt_eval_golden_prompts_passed', value_at(status, 'prompt_eval', 'golden_prompts_passed'))",
            "    emit('prompt_eval_golden_prompts_failed', value_at(status, 'prompt_eval', 'golden_prompts_failed'))",
            "    emit('prompt_eval_agentic_tool_cases', value_at(status, 'prompt_eval', 'agentic_tool_cases'))",
            "    emit('prompt_eval_agentic_tool_cases_required', value_at(status, 'prompt_eval', 'agentic_tool_cases_required'))",
            "    emit('adapter_present', value_at(status, 'adapter_log', 'present'))",
            "    emit('adapter_release_health', value_at(status, 'adapter_log', 'release_health'))",
            "    emit('adapter_current_health', value_at(status, 'adapter_log', 'current_health'))",
            "    emit('adapter_recent_window_health', value_at(status, 'adapter_log', 'recent_window_health'))",
            "    emit('adapter_history_health', value_at(status, 'adapter_log', 'history_health'))",
            "    emit('adapter_latest_ok', value_at(status, 'adapter_log', 'latest_ok'))",
            "    emit('adapter_recent_window_entries', value_at(status, 'adapter_log', 'recent_window_entries'))",
            "    emit('adapter_recent_successes', value_at(status, 'adapter_log', 'recent_successes'))",
            "    emit('adapter_recent_failures', value_at(status, 'adapter_log', 'recent_failures'))",
            "    emit('adapter_recent_timeouts', value_at(status, 'adapter_log', 'recent_timeouts'))",
            "    emit('adapter_failures', value_at(status, 'adapter_log', 'failures'))",
            "    emit('adapter_timeouts', value_at(status, 'adapter_log', 'timeouts'))",
            "    emit('adapter_latest_source_trace_id', value_at(status, 'adapter_log', 'latest', 'source_trace_id'))",
            "    emit('adapter_latest_selected_option_id', value_at(status, 'adapter_log', 'latest', 'selected_option_id'))",
            "    emit('adapter_latest_tool_count', value_at(status, 'adapter_log', 'latest', 'tool_count'))",
            "    emit('adapter_latest_planned_node_writes', value_at(status, 'adapter_log', 'latest', 'planned_node_writes'))",
            "    emit('adapter_latest_web_search_available', value_at(status, 'adapter_log', 'latest', 'web_search_available'))",
            "    emit('adapter_latest_agentic_execution', value_at(status, 'adapter_log', 'latest', 'agentic_execution'))",
            "    emit('adapter_latest_required_tool_calls_satisfied', value_at(status, 'adapter_log', 'latest', 'required_tool_calls_satisfied'))",
            "    emit('adapter_latest_world_mutation_authority', value_at(status, 'adapter_log', 'latest', 'world_mutation_authority'))",
            "    emit('adapter_latest_direct_world_mutation', value_at(status, 'adapter_log', 'latest', 'direct_world_mutation'))",
            "    emit('runtime_proofs_health', value_at(status, 'runtime_proofs', 'current_health'))",
            "    emit('runtime_proofs_nova_status', value_at(status, 'runtime_proofs', 'nova_auto_apply', 'status'))",
            "    emit('runtime_proofs_nova_cases_total', value_at(status, 'runtime_proofs', 'nova_auto_apply', 'cases_total'))",
            "    emit('runtime_proofs_nova_cases_passed', value_at(status, 'runtime_proofs', 'nova_auto_apply', 'cases_passed'))",
            "    emit('runtime_proofs_nova_cases_failed', value_at(status, 'runtime_proofs', 'nova_auto_apply', 'cases_failed'))",
            "    emit('runtime_proofs_compat_status', value_at(status, 'runtime_proofs', 'compat_import', 'status'))",
            "    emit('runtime_proofs_compat_refusal_gates_passed', value_at(status, 'runtime_proofs', 'compat_import', 'refusal_gates_passed'))",
            "    emit('runtime_proofs_compat_refusal_gates_total', value_at(status, 'runtime_proofs', 'compat_import', 'refusal_gates_total'))",
            "PY",
        ]
    )


def parse_key_values(output: str) -> dict[str, str]:
    values = {}
    for line in output.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            values[key] = value.strip()
    return values


def number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def integer(value):
    parsed = number(value)
    if parsed is None:
        return None
    return int(parsed)


def boolean(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    return None


def field_text(values: dict[str, str], key: str, default: str = "unknown") -> str:
    value = values.get(key)
    if value in {None, ""}:
        return default
    return sanitize_text(value)


def bounded_text_list(value, *, max_items: int = 10, max_chars: int = 240) -> list[str]:
    if not isinstance(value, list):
        return []
    return [sanitize_text(str(item))[:max_chars] for item in value[:max_items]]


def soak_target_config(args) -> dict:
    config = dict(SOAK_TARGETS[args.soak_target])
    if args.soak_min_duration_seconds is not None:
        config["minimum_duration_seconds"] = max(
            float(config["minimum_duration_seconds"]),
            float(args.soak_min_duration_seconds),
        )
    return config


def parse_remote_manifest_path(output: str) -> str:
    for line in reversed(output.splitlines()):
        line = line.strip()
        if line:
            return line
    return ""


def logical_run_dir(date: str, commit: str) -> str:
    return "/".join(
        [
            "local",
            "benchmarks",
            "low-power-server",
            path_part(date),
            path_part(commit),
        ]
    )


def output_path(args, commit: str) -> Path:
    return Path(args.output_root) / "low-power-server" / path_part(args.date) / path_part(commit) / EVIDENCE_NAME


def backup_evidence(args) -> dict:
    label = Path(args.backup_artifact_label).name if args.backup_artifact_label else None
    return {
        "backup_first_confirmed": args.confirm_backup_first is True,
        "artifact_label": sanitize_text(label) if label else None,
        "sha256": args.backup_sha256 or None,
        "sha256_recorded": bool(args.backup_sha256),
    }


def runtime_evidence(remote_manifest: dict) -> dict:
    clean = remote_manifest.get("clean_profile_evidence") or {}
    product = remote_manifest.get("product_profile_evidence") or {}
    compat = remote_manifest.get("compat_import_staging_pilot_evidence") or {}
    server_step_workload = clean.get("server_step_workload") or {}
    avg_cpu = clean.get("avg_process_cpu_percent")
    max_cpu = clean.get("max_interval_cpu_percent")
    max_rss_kb = clean.get("max_rss_kb")
    max_rss_mb = None
    if isinstance(max_rss_kb, (int, float)):
        max_rss_mb = round(max_rss_kb / 1024, 3)
    return {
        "remote_manifest_status": sanitize_text(remote_manifest.get("overall_status", "unknown")),
        "logical_run_dir": sanitize_text(remote_manifest.get("logical_run_dir", "")),
        "artifact_paths": sanitize_value(remote_manifest.get("artifact_paths", {})),
        "product_profile_status": sanitize_text(product.get("status", "unknown")),
        "product_profile_no_private_content": product.get("no_private_content") is True,
        "clean_profile_status": sanitize_text(clean.get("overall_status", "unknown")),
        "player_load_probe_status": sanitize_text(clean.get("player_load_probe_status", "unknown")),
        "player_load_probe_kind": sanitize_text(clean.get("player_load_probe_kind", "unknown")),
        "headless_player_supported": clean.get("headless_player_supported") is True,
        "attempted_synthetic_player_count": clean.get("attempted_synthetic_player_count"),
        "connected_synthetic_player_count": clean.get("connected_synthetic_player_count"),
        "completed_synthetic_player_count": clean.get("completed_synthetic_player_count"),
        "latency_proxy_supported": clean.get("latency_proxy_supported") is True,
        "latency_probe_kind": sanitize_text(clean.get("latency_probe_kind", "unknown")),
        "join_latency_proxy_sample_count": clean.get("join_latency_proxy_sample_count"),
        "scale_gate_status": sanitize_text(clean.get("scale_gate_status", "unknown")),
        "scale_gate_required_synthetic_player_count": clean.get(
            "scale_gate_required_synthetic_player_count"
        ),
        "scale_gate_required_concurrent_task_count": clean.get(
            "scale_gate_required_concurrent_task_count"
        ),
        "server_step_workload_status": sanitize_text(
            clean.get("server_step_workload_status")
            or server_step_workload.get("status")
            or "unknown"
        ),
        "server_step_attempted_samples": clean.get("server_step_attempted_samples"),
        "server_step_completed_samples": clean.get("server_step_completed_samples"),
        "server_step_failed_samples": clean.get("server_step_failed_samples"),
        "actionable_warning_count": clean.get("actionable_warning_count"),
        "server_log_error_count": clean.get("server_log_error_count"),
        "cpu_status": sanitize_text(clean.get("cpu_status", "unknown")),
        "cpu_sample_count": clean.get("cpu_sample_count"),
        "avg_process_cpu_percent": avg_cpu,
        "max_interval_cpu_percent": max_cpu,
        "rss_sample_count": clean.get("rss_sample_count"),
        "max_rss_kb": max_rss_kb,
        "max_rss_mb": max_rss_mb,
        "compat_import_staging_pilot_status": sanitize_text(
            compat.get("compat_import_staging_pilot_status", "unknown")
        ),
        "compat_import_inventory_ready": compat.get("compat_import_inventory_ready") is True,
        "compat_import_node_writes": compat.get("compat_import_node_writes"),
        "compat_import_mapblock_churn": compat.get("compat_import_mapblock_churn"),
        "compat_import_refusal_gates": compat.get("compat_import_refusal_gates"),
        "failure_count": len(remote_manifest.get("failure_reasons") or []),
    }


def studio_status_evidence(service_values: dict[str, str]) -> dict:
    return {
        "present": boolean(service_values.get("studio_status_present")) is True,
        "health": field_text(service_values, "studio_status_health"),
        "schema_version": integer(service_values.get("studio_schema_version")),
        "public_safe": boolean(service_values.get("studio_public_safe")),
        "live_bridge": boolean(service_values.get("studio_live_bridge")),
        "direct_world_mutation_by_ai": boolean(
            service_values.get("studio_direct_world_mutation_by_ai")
        ),
        "services_all_active": boolean(service_values.get("studio_services_all_active")),
        "quality_gate": {
            "status": field_text(service_values, "studio_quality_gate_status"),
            "attention_total": integer(service_values.get("studio_quality_gate_attention_total")),
            "violations_total": integer(service_values.get("studio_quality_gate_violations_total")),
            "live_prompt_eval_status": field_text(
                service_values,
                "studio_quality_gate_live_prompt_eval_status",
            ),
            "live_review_gate_health": field_text(
                service_values,
                "studio_quality_gate_live_review_gate_health",
            ),
        },
        "live_review_gate": {
            "status": field_text(service_values, "studio_live_review_gate_status"),
            "current_health": field_text(service_values, "studio_live_review_gate_health"),
            "source_trace_id": field_text(
                service_values,
                "studio_live_review_gate_source_trace_id",
                default="",
            ),
            "selected_option_id": field_text(
                service_values,
                "studio_live_review_gate_selected_option_id",
                default="",
            ),
            "checks_passed": integer(service_values.get("studio_live_review_gate_checks_passed")),
            "checks_total": integer(service_values.get("studio_live_review_gate_checks_total")),
            "violations_total": integer(
                service_values.get("studio_live_review_gate_violations_total")
            ),
            "public_safe_output": boolean(
                service_values.get("studio_live_review_gate_public_safe_output")
            ),
            "unsafe_payload_rejected": boolean(
                service_values.get("studio_live_review_gate_unsafe_payload_rejected")
            ),
            "no_world_mutation": boolean(
                service_values.get("studio_live_review_gate_no_world_mutation")
            ),
            "no_raw_assets": boolean(service_values.get("studio_live_review_gate_no_raw_assets")),
            "no_provider_prompts": boolean(
                service_values.get("studio_live_review_gate_no_provider_prompts")
            ),
            "no_family_world_coordinates": boolean(
                service_values.get("studio_live_review_gate_no_family_world_coordinates")
            ),
        },
        "prompt_eval": {
            "current_health": field_text(service_values, "studio_prompt_eval_health"),
            "status": field_text(service_values, "studio_prompt_eval_status"),
            "cases_total": integer(service_values.get("studio_prompt_eval_cases_total")),
            "cases_passed": integer(service_values.get("studio_prompt_eval_cases_passed")),
            "cases_failed": integer(service_values.get("studio_prompt_eval_cases_failed")),
            "golden_prompts_total": integer(
                service_values.get("studio_prompt_eval_golden_prompts_total")
            ),
            "golden_prompts_passed": integer(
                service_values.get("studio_prompt_eval_golden_prompts_passed")
            ),
            "golden_prompts_failed": integer(
                service_values.get("studio_prompt_eval_golden_prompts_failed")
            ),
            "agentic_tool_cases": integer(
                service_values.get("studio_prompt_eval_agentic_tool_cases")
            ),
            "agentic_tool_cases_required": integer(
                service_values.get("studio_prompt_eval_agentic_tool_cases_required")
            ),
        },
        "adapter_log": {
            "present": boolean(service_values.get("studio_adapter_present")),
            "release_health": field_text(service_values, "studio_adapter_release_health"),
            "current_health": field_text(service_values, "studio_adapter_current_health"),
            "recent_window_health": field_text(
                service_values,
                "studio_adapter_recent_window_health",
            ),
            "history_health": field_text(service_values, "studio_adapter_history_health"),
            "latest_ok": boolean(service_values.get("studio_adapter_latest_ok")),
            "recent_window_entries": integer(
                service_values.get("studio_adapter_recent_window_entries")
            ),
            "recent_successes": integer(service_values.get("studio_adapter_recent_successes")),
            "recent_failures": integer(service_values.get("studio_adapter_recent_failures")),
            "recent_timeouts": integer(service_values.get("studio_adapter_recent_timeouts")),
            "failures": integer(service_values.get("studio_adapter_failures")),
            "timeouts": integer(service_values.get("studio_adapter_timeouts")),
            "latest": {
                "source_trace_id": field_text(
                    service_values,
                    "studio_adapter_latest_source_trace_id",
                    default="",
                ),
                "selected_option_id": field_text(
                    service_values,
                    "studio_adapter_latest_selected_option_id",
                    default="",
                ),
                "tool_count": integer(service_values.get("studio_adapter_latest_tool_count")),
                "planned_node_writes": integer(
                    service_values.get("studio_adapter_latest_planned_node_writes")
                ),
                "web_search_available": boolean(
                    service_values.get("studio_adapter_latest_web_search_available")
                ),
                "agentic_execution": boolean(
                    service_values.get("studio_adapter_latest_agentic_execution")
                ),
                "required_tool_calls_satisfied": boolean(
                    service_values.get("studio_adapter_latest_required_tool_calls_satisfied")
                ),
                "world_mutation_authority": field_text(
                    service_values,
                    "studio_adapter_latest_world_mutation_authority",
                ),
                "direct_world_mutation": boolean(
                    service_values.get("studio_adapter_latest_direct_world_mutation")
                ),
            },
        },
        "runtime_proofs": {
            "current_health": field_text(service_values, "studio_runtime_proofs_health"),
            "nova_status": field_text(service_values, "studio_runtime_proofs_nova_status"),
            "nova_cases_total": integer(
                service_values.get("studio_runtime_proofs_nova_cases_total")
            ),
            "nova_cases_passed": integer(
                service_values.get("studio_runtime_proofs_nova_cases_passed")
            ),
            "nova_cases_failed": integer(
                service_values.get("studio_runtime_proofs_nova_cases_failed")
            ),
            "compat_status": field_text(
                service_values,
                "studio_runtime_proofs_compat_status",
            ),
            "compat_refusal_gates_passed": integer(
                service_values.get("studio_runtime_proofs_compat_refusal_gates_passed")
            ),
            "compat_refusal_gates_total": integer(
                service_values.get("studio_runtime_proofs_compat_refusal_gates_total")
            ),
        },
    }


def build_soak_evidence(args, remote_manifests: list[dict], elapsed_seconds: float | None = None) -> dict:
    target = soak_target_config(args)
    target_minimum = float(target["minimum_duration_seconds"])
    elapsed = round(float(elapsed_seconds), 3) if elapsed_seconds is not None else None
    duration_met = elapsed is not None and elapsed >= target_minimum
    samples = []
    max_avg_cpu = None
    max_interval_cpu = None
    max_rss_mb = None
    max_actionable_warnings = 0
    max_errors = 0
    passed = 0
    for index, remote_manifest in enumerate(remote_manifests, start=1):
        evidence = runtime_evidence(remote_manifest)
        clean = remote_manifest.get("clean_profile_evidence") or {}
        artifact_paths = remote_manifest.get("artifact_paths") or {}
        sample = {
            "iteration": index,
            "remote_generated_at": sanitize_text(remote_manifest.get("generated_at", "")),
            "remote_manifest_status": evidence["remote_manifest_status"],
            "clean_profile_status": evidence["clean_profile_status"],
            "server_step_workload_status": evidence["server_step_workload_status"],
            "player_load_probe_status": evidence["player_load_probe_status"],
            "compat_import_staging_pilot_status": evidence["compat_import_staging_pilot_status"],
            "cpu_status": evidence["cpu_status"],
            "cpu_sample_count": evidence["cpu_sample_count"],
            "avg_process_cpu_percent": evidence["avg_process_cpu_percent"],
            "max_interval_cpu_percent": evidence["max_interval_cpu_percent"],
            "rss_sample_count": evidence["rss_sample_count"],
            "max_rss_mb": evidence["max_rss_mb"],
            "actionable_warning_count": evidence["actionable_warning_count"],
            "server_log_error_count": evidence["server_log_error_count"],
            "failure_count": evidence["failure_count"],
            "failure_reasons": bounded_text_list(remote_manifest.get("failure_reasons")),
            "clean_profile_failure_reasons": bounded_text_list(clean.get("failure_reasons")),
            "artifact_keys": sorted(str(key)[:80] for key in artifact_paths.keys())[:20]
            if isinstance(artifact_paths, dict)
            else [],
        }
        samples.append(sample)
        if remote_manifest.get("overall_status") == "pass":
            passed += 1
        for field, current in (
            ("avg_process_cpu_percent", "max_avg_cpu"),
            ("max_interval_cpu_percent", "max_interval_cpu"),
            ("max_rss_mb", "max_rss_mb"),
        ):
            value = number(sample.get(field))
            if value is None:
                continue
            if current == "max_avg_cpu":
                max_avg_cpu = value if max_avg_cpu is None else max(max_avg_cpu, value)
            elif current == "max_interval_cpu":
                max_interval_cpu = value if max_interval_cpu is None else max(max_interval_cpu, value)
            elif current == "max_rss_mb":
                max_rss_mb = value if max_rss_mb is None else max(max_rss_mb, value)
        max_actionable_warnings = max(
            max_actionable_warnings,
            integer(sample.get("actionable_warning_count")) or 0,
        )
        max_errors = max(max_errors, integer(sample.get("server_log_error_count")) or 0)

    return {
        "mode": "repeatable_side_by_side_low_power_soak",
        "iterations_requested": int(args.soak_iterations),
        "iterations_completed": len(samples),
        "iterations_passed": passed,
        "iterations_failed": max(0, len(samples) - passed),
        "sample_interval_seconds": float(args.soak_interval_seconds),
        "target": {
            "name": args.soak_target,
            "minimum_duration_seconds": target_minimum,
            "elapsed_seconds": elapsed,
            "duration_met": duration_met,
            "recommended_iterations": int(target["recommended_iterations"]),
            "recommended_interval_seconds": float(target["recommended_interval_seconds"]),
            "next_target": target["next_target"],
        },
        "resource_budgets": {
            "max_avg_cpu_percent": float(args.max_avg_cpu_percent),
            "max_interval_cpu_percent": float(args.max_interval_cpu_percent),
            "max_rss_mb": float(args.max_rss_mb),
            "max_actionable_warning_count": int(args.max_actionable_warning_count),
            "max_server_log_error_count": int(args.max_server_log_error_count),
            "max_fork_restarts": int(args.max_fork_restarts),
        },
        "resource_maxima": {
            "avg_process_cpu_percent": max_avg_cpu,
            "max_interval_cpu_percent": max_interval_cpu,
            "max_rss_mb": max_rss_mb,
            "actionable_warning_count": max_actionable_warnings,
            "server_log_error_count": max_errors,
        },
        "samples": samples,
    }


def ranked_follow_up_issues(failures: list[str]) -> list[dict]:
    issue_map = {
        "public_safety_violation": (
            "P0",
            "Private-data flag in Pi evidence output",
            "Sanitize the retained Pi evidence before promotion.",
        ),
        "fork_restart_budget_exceeded": (
            "P1",
            "Fork service restarted during Pi soak",
            "Inspect systemd journal and service limits before the next promotion.",
        ),
        "fork_restart_evidence_missing": (
            "P1",
            "Fork restart evidence missing from Pi soak",
            "Capture systemd restart counters so restarts cannot be hidden.",
        ),
        "memory_rss_budget_exceeded": (
            "P1",
            "Pi soak exceeded RSS memory budget",
            "Investigate OOM risk and memory growth before longer soaks.",
        ),
        "max_cpu_budget_exceeded": (
            "P2",
            "Pi soak had CPU spike above budget",
            "Review server-step samples and profile hot paths.",
        ),
        "avg_cpu_budget_exceeded": (
            "P2",
            "Pi soak exceeded average CPU budget",
            "Tune runtime workload or lower background agent pressure.",
        ),
        "actionable_warning_budget_exceeded": (
            "P2",
            "Pi soak produced actionable warnings",
            "Review verifier warnings and split defects into focused issues.",
        ),
        "server_log_error_budget_exceeded": (
            "P2",
            "Pi soak produced server log errors",
            "Review retained logs and open a bug for each reproducible error.",
        ),
        "soak_target_duration_not_met": (
            "P2",
            "Declared Pi soak target duration was not met",
            "Rerun with the recommended target iterations and interval.",
        ),
        "headless_player_probe_not_measured": (
            "P2",
            "Headless player join proxy was not measured",
            "Fix the null-video client probe before accepting low-power evidence.",
        ),
        "headless_player_latency_not_measured": (
            "P2",
            "Headless player join latency proxy was not measured",
            "Restore join-log latency evidence for multiplayer readiness.",
        ),
        "ai_runtime_scale_gate_not_pass": (
            "P2",
            "AI runtime scale gate did not pass on the Pi",
            "Refresh the low-power verifier with two synthetic players and concurrent first-party task evidence.",
        ),
        "compat_import_staging_pilot_not_pass": (
            "P2",
            "Compatibility staging pilot failed during Pi evidence run",
            "Keep compatibility apply expansion gated until the pilot passes.",
        ),
        "studio_status_unavailable": (
            "P1",
            "OpenRealm Studio status was unavailable during Pi evidence capture",
            "Restore the Studio UI service or its loopback /api/status endpoint before promotion.",
        ),
        "studio_status_not_public_safe": (
            "P0",
            "OpenRealm Studio status was not public-safe",
            "Block promotion until the Studio status payload excludes private paths, prompts, credentials, and copied assets.",
        ),
        "studio_services_not_all_active": (
            "P1",
            "OpenRealm Studio reported an inactive live service",
            "Check the family, fork, adapter, and Studio services before the next evidence run.",
        ),
        "studio_live_bridge_not_available": (
            "P1",
            "OpenRealm Studio live bridge was not available",
            "Restore the live telemetry bridge so the UI proves current runtime state.",
        ),
        "studio_direct_world_mutation_enabled": (
            "P0",
            "Studio status allowed direct AI world mutation",
            "Keep AI output behind preview, approval, task execution, audit, and rollback.",
        ),
        "studio_quality_gate_not_pass": (
            "P1",
            "OpenRealm quality gate did not pass",
            "Review the quality gate artifact and fix violations before promotion.",
        ),
        "studio_live_review_gate_not_pass": (
            "P1",
            "OpenRealm live review gate did not pass",
            "Rerun or repair the latest public-safe live review packet and approval gate.",
        ),
        "studio_prompt_eval_not_pass": (
            "P1",
            "OpenRealm prompt evaluation did not pass",
            "Fix the Nova golden prompt or live prompt-eval regression before promotion.",
        ),
        "studio_adapter_release_not_pass": (
            "P1",
            "Agents SDK adapter release health did not pass",
            "Repair the latest adapter trace so Nova uses tool-backed agentic execution without direct world mutation.",
        ),
        "studio_runtime_proofs_not_pass": (
            "P1",
            "Runtime proof bundle did not pass",
            "Refresh Nova apply/rollback and compatibility staging proofs before promotion.",
        ),
    }
    ranked = []
    for reason in failures:
        if reason not in issue_map:
            continue
        severity, title, action = issue_map[reason]
        ranked.append({
            "rank": len(ranked) + 1,
            "severity": severity,
            "source_failure": reason,
            "title": title,
            "recommended_action": action,
        })
    severity_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    ranked.sort(key=lambda item: (severity_order.get(item["severity"], 9), item["rank"]))
    for index, item in enumerate(ranked, start=1):
        item["rank"] = index
    return ranked


def build_manifest(
    args,
    remote_manifest: dict,
    service_values: dict,
    *,
    soak_manifests: list[dict] | None = None,
    soak_elapsed_seconds: float | None = None,
    now_fn=utc_now,
) -> dict:
    remote_manifest = sanitize_value(remote_manifest)
    soak_manifests = sanitize_value(soak_manifests or [remote_manifest])
    service_values = {key: sanitize_text(value) for key, value in service_values.items()}
    commit = (
        args.luanti_commit
        or remote_manifest.get("luanti_commit")
        or service_values.get("fork_commit")
        or "unknown"
    )
    fork_restart_count = integer(service_values.get("fork_restart_count"))
    soak_evidence = build_soak_evidence(args, soak_manifests, soak_elapsed_seconds)
    manifest = {
        "schema_version": 1,
        "evidence_kind": "ai_native_low_power_pi_evidence",
        "generated_at": now_fn(),
        "hardware_class": "low-power-server",
        "game_profile": "ai_runtime",
        "luanti_commit": sanitize_text(commit),
        "logical_run_dir": logical_run_dir(args.date, commit),
        "overall_status": "pass",
        "service_boundary": {
            "family_service": {
                "service_role": "family_server",
                "port": int(args.family_port),
                "active": service_values.get("family_service_active") == "active",
                "udp_listening": service_values.get("family_udp_listening") == "true",
            },
            "fork_test_service": {
                "service_role": "ai_native_fork_test",
                "port": int(args.fork_port),
                "active": service_values.get("fork_service_active") == "active",
                "udp_listening": service_values.get("fork_udp_listening") == "true",
                "version": service_values.get("fork_version") or "unknown",
                "commit": service_values.get("fork_commit") or "unknown",
                "restart_count": fork_restart_count,
                "active_enter_timestamp": service_values.get("fork_active_enter_timestamp") or "unknown",
            },
        },
        "runtime_verification_evidence": runtime_evidence(remote_manifest),
        "studio_status_evidence": studio_status_evidence(service_values),
        "soak_evidence": soak_evidence,
        "backup_evidence": backup_evidence(args),
        "run_context": {
            "mode": "low-power-pi-side-by-side-clean-profile-evidence",
            "requires_live_pi": True,
            "requires_private_world": False,
            "requires_private_assets": False,
            "records_private_target": False,
            "mutates_services": False,
        },
        "ranked_follow_up_issue_seeds": [],
        "safety": {
            "public_safe_output": True,
            "private_target_redacted": True,
            "remote_paths_redacted": True,
            "no_family_content": True,
            "no_provider_prompts": True,
            "no_copied_assets": True,
        },
        "failure_reasons": [],
    }

    failures = manifest["failure_reasons"]
    if not args.confirm_backup_first:
        failures.append("backup_first_confirmation_missing")
    if soak_evidence["iterations_completed"] != int(args.soak_iterations):
        failures.append("soak_iterations_incomplete")
    if soak_evidence["iterations_passed"] != int(args.soak_iterations):
        failures.append("soak_iteration_failed")
    if not soak_evidence["target"]["duration_met"]:
        failures.append("soak_target_duration_not_met")
    if remote_manifest.get("overall_status") != "pass":
        failures.append("remote_low_power_verifier_not_pass")
    if remote_manifest.get("hardware_class") != "low-power-server":
        failures.append("remote_manifest_not_low_power_server")
    if remote_manifest.get("game_profile") != "ai_runtime":
        failures.append("remote_manifest_not_ai_runtime")
    if manifest["runtime_verification_evidence"]["product_profile_status"] != "pass":
        failures.append("product_profile_hygiene_not_pass")
    if not manifest["runtime_verification_evidence"]["product_profile_no_private_content"]:
        failures.append("product_profile_private_content_detected")
    if manifest["runtime_verification_evidence"]["clean_profile_status"] != "pass":
        failures.append("clean_profile_evidence_not_pass")
    runtime = manifest["runtime_verification_evidence"]
    if runtime["compat_import_staging_pilot_status"] != "pass":
        failures.append("compat_import_staging_pilot_not_pass")
    attempted_players = runtime.get("attempted_synthetic_player_count")
    connected_players = runtime.get("connected_synthetic_player_count")
    if (
        runtime["player_load_probe_kind"] != "headless_client_load"
        or runtime["headless_player_supported"] is not True
        or not isinstance(attempted_players, (int, float))
        or attempted_players < 2
        or not isinstance(connected_players, (int, float))
        or connected_players < 2
        or connected_players != attempted_players
    ):
        failures.append("headless_player_probe_not_measured")
    if (
        runtime["latency_proxy_supported"] is not True
        or runtime["latency_probe_kind"] != "headless_join_log_observation"
        or not isinstance(runtime.get("join_latency_proxy_sample_count"), (int, float))
        or runtime["join_latency_proxy_sample_count"] <= 0
    ):
        failures.append("headless_player_latency_not_measured")
    if (
        runtime["scale_gate_status"] != "pass"
        or not isinstance(runtime.get("scale_gate_required_synthetic_player_count"), (int, float))
        or runtime["scale_gate_required_synthetic_player_count"] < 2
        or not isinstance(runtime.get("scale_gate_required_concurrent_task_count"), (int, float))
        or runtime["scale_gate_required_concurrent_task_count"] < 2
    ):
        failures.append("ai_runtime_scale_gate_not_pass")
    if not manifest["service_boundary"]["family_service"]["active"]:
        failures.append("family_service_not_active")
    if not manifest["service_boundary"]["family_service"]["udp_listening"]:
        failures.append("family_udp_port_not_listening")
    if not manifest["service_boundary"]["fork_test_service"]["active"]:
        failures.append("fork_test_service_not_active")
    if not manifest["service_boundary"]["fork_test_service"]["udp_listening"]:
        failures.append("fork_test_udp_port_not_listening")
    if fork_restart_count is None:
        failures.append("fork_restart_evidence_missing")
    elif fork_restart_count > int(args.max_fork_restarts):
        failures.append("fork_restart_budget_exceeded")
    fork_commit = manifest["service_boundary"]["fork_test_service"]["commit"]
    if fork_commit not in {"", "unknown"} and commit not in {"", "unknown"} and fork_commit != commit:
        failures.append("fork_commit_mismatch")

    studio = manifest["studio_status_evidence"]
    if studio["present"] is not True:
        failures.append("studio_status_unavailable")
    if studio["public_safe"] is not True:
        failures.append("studio_status_not_public_safe")
    if studio["services_all_active"] is not True:
        failures.append("studio_services_not_all_active")
    if studio["live_bridge"] is not True:
        failures.append("studio_live_bridge_not_available")
    if studio["direct_world_mutation_by_ai"] is not False:
        failures.append("studio_direct_world_mutation_enabled")
    if studio["quality_gate"]["status"] != "pass":
        failures.append("studio_quality_gate_not_pass")
    if studio["live_review_gate"]["current_health"] != "pass":
        failures.append("studio_live_review_gate_not_pass")
    if studio["prompt_eval"]["current_health"] != "pass":
        failures.append("studio_prompt_eval_not_pass")
    if studio["adapter_log"]["release_health"] != "pass":
        failures.append("studio_adapter_release_not_pass")
    if studio["runtime_proofs"]["current_health"] != "pass":
        failures.append("studio_runtime_proofs_not_pass")

    maxima = soak_evidence["resource_maxima"]
    if number(maxima.get("avg_process_cpu_percent")) is None:
        failures.append("avg_cpu_evidence_missing")
    elif maxima["avg_process_cpu_percent"] > float(args.max_avg_cpu_percent):
        failures.append("avg_cpu_budget_exceeded")
    if number(maxima.get("max_interval_cpu_percent")) is None:
        failures.append("max_cpu_evidence_missing")
    elif maxima["max_interval_cpu_percent"] > float(args.max_interval_cpu_percent):
        failures.append("max_cpu_budget_exceeded")
    if number(maxima.get("max_rss_mb")) is None:
        failures.append("memory_rss_evidence_missing")
    elif maxima["max_rss_mb"] > float(args.max_rss_mb):
        failures.append("memory_rss_budget_exceeded")
    if maxima["actionable_warning_count"] > int(args.max_actionable_warning_count):
        failures.append("actionable_warning_budget_exceeded")
    if maxima["server_log_error_count"] > int(args.max_server_log_error_count):
        failures.append("server_log_error_budget_exceeded")

    serialized = json.dumps(manifest, sort_keys=True)
    if PRIVATE_PATTERN.search(serialized):
        failures.append("public_safety_violation")
        manifest["safety"]["public_safe_output"] = False

    manifest["ranked_follow_up_issue_seeds"] = ranked_follow_up_issues(failures)
    manifest["overall_status"] = "fail" if failures else "pass"
    return manifest


def read_remote_manifest(args, remote_path: str, runner) -> tuple[CommandRun, dict | None]:
    if remote_path.startswith("/"):
        cat_command = f"cat {shlex.quote(remote_path)}"
    else:
        cat_command = f"cd {shlex.quote(args.remote_repo)} && cat {shlex.quote(remote_path)}"
    result = runner(ssh_command(args, cat_command), timeout=args.ssh_timeout)
    if result.returncode != 0:
        return result, None
    try:
        return result, json.loads(result.stdout)
    except json.JSONDecodeError:
        return result, None


def run(args, *, runner=run_subprocess, now_fn=utc_now, monotonic_fn=time.monotonic, sleep_fn=time.sleep):
    soak_started = monotonic_fn()
    remote_manifests = []
    verify_returncodes = []
    for iteration in range(int(args.soak_iterations)):
        verify_result = runner(
            ssh_command(args, remote_verify_command(args)),
            timeout=args.remote_verify_timeout,
        )
        verify_returncodes.append(verify_result.returncode)
        remote_manifest = None
        remote_path = parse_remote_manifest_path(verify_result.stdout)
        if remote_path:
            _, remote_manifest = read_remote_manifest(args, remote_path, runner)
        if remote_manifest is None:
            remote_manifest = {
                "schema_version": 1,
                "overall_status": "fail",
                "hardware_class": "low-power-server",
                "game_profile": "ai_runtime",
                "luanti_commit": args.luanti_commit or "unknown",
                "logical_run_dir": logical_run_dir(args.date, args.luanti_commit or "unknown"),
                "artifact_paths": {},
                "failure_reasons": ["remote_manifest_unavailable"],
            }
        remote_manifests.append(remote_manifest)
        if iteration + 1 < int(args.soak_iterations) and args.soak_interval_seconds > 0:
            sleep_fn(args.soak_interval_seconds)

    remote_manifest = remote_manifests[-1]

    service_result = runner(
        ssh_command(args, remote_service_command(args)),
        timeout=args.ssh_timeout,
    )
    service_values = parse_key_values(service_result.stdout)
    soak_elapsed_seconds = max(0.0, monotonic_fn() - soak_started)
    if service_result.returncode != 0:
        service_values.setdefault("family_service_active", "unknown")
        service_values.setdefault("fork_service_active", "unknown")
        service_values.setdefault("family_udp_listening", "false")
        service_values.setdefault("fork_udp_listening", "false")

    manifest = build_manifest(
        args,
        remote_manifest,
        service_values,
        soak_manifests=remote_manifests,
        soak_elapsed_seconds=soak_elapsed_seconds,
        now_fn=now_fn,
    )
    if any(returncode != 0 for returncode in verify_returncodes):
        manifest["failure_reasons"].append("remote_low_power_verifier_command_failed")
    if service_result.returncode != 0:
        manifest["failure_reasons"].append("remote_service_probe_failed")
    if manifest["failure_reasons"]:
        manifest["overall_status"] = "fail"

    path = output_path(args, manifest["luanti_commit"])
    write_json(path, manifest)
    return (0 if manifest["overall_status"] == "pass" else 2), path, manifest


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ssh-target", required=True, help="Operator-supplied SSH target; not written to the manifest.")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT), help="Local benchmark evidence root.")
    parser.add_argument("--date", default=datetime.now(timezone.utc).date().isoformat())
    parser.add_argument("--luanti-commit", help="Expected fork commit; defaults to the remote checkout commit.")
    parser.add_argument("--remote-repo", default="/opt/ai-native-luanti/src")
    parser.add_argument("--remote-server-bin", default="/opt/ai-native-luanti/src/bin/luantiserver")
    parser.add_argument("--remote-client-bin", default="bin/luanti")
    parser.add_argument("--remote-client-config-prefix", default="/tmp/ai-native-headless-client.XXXXXX")
    parser.add_argument("--studio-status-url", default="http://127.0.0.1:8788/api/status")
    parser.add_argument("--studio-status-timeout", type=float, default=4.0)
    parser.add_argument("--family-service", default="luanti-family.service")
    parser.add_argument("--fork-service", default="ai-native-luanti-test.service")
    parser.add_argument("--family-port", type=int, default=30000)
    parser.add_argument("--fork-port", type=int, default=30001)
    parser.add_argument("--headless-player-count", type=int, default=2)
    parser.add_argument("--headless-player-timeout", type=float, default=2.0)
    parser.add_argument("--soak-target", choices=tuple(SOAK_TARGETS), default="quick", help="Named soak gate target to record and enforce.")
    parser.add_argument("--soak-min-duration-seconds", type=float, help="Optional extra minimum duration; cannot lower the named target.")
    parser.add_argument(
        "--soak-iterations",
        type=int,
        help=(
            "Number of repeated low-power verifier samples to collect. Defaults "
            "to the recommended count for --soak-target."
        ),
    )
    parser.add_argument(
        "--soak-interval-seconds",
        type=float,
        help=(
            "Delay between soak iterations. Defaults to the recommended interval "
            "for --soak-target."
        ),
    )
    parser.add_argument("--max-avg-cpu-percent", type=float, default=85.0)
    parser.add_argument("--max-interval-cpu-percent", type=float, default=160.0)
    parser.add_argument("--max-rss-mb", type=float, default=1024.0)
    parser.add_argument("--max-actionable-warning-count", type=int, default=0)
    parser.add_argument("--max-server-log-error-count", type=int, default=0)
    parser.add_argument("--max-fork-restarts", type=int, default=0)
    parser.add_argument("--confirm-backup-first", action="store_true")
    parser.add_argument("--backup-artifact-label", help="Backup archive basename or label from the preceding deploy.")
    parser.add_argument("--backup-sha256", help="SHA256 of the preceding backup archive.")
    parser.add_argument("--ssh-connect-timeout", type=int, default=10)
    parser.add_argument("--ssh-timeout", type=int, default=60)
    parser.add_argument("--remote-verify-timeout", type=int, default=600)
    args = parser.parse_args(argv)
    target = SOAK_TARGETS[args.soak_target]
    if args.soak_iterations is None:
        args.soak_iterations = int(target["recommended_iterations"])
    if args.soak_interval_seconds is None:
        args.soak_interval_seconds = float(target["recommended_interval_seconds"])
    if args.soak_iterations < 1:
        parser.error("--soak-iterations must be at least 1")
    if args.soak_interval_seconds < 0:
        parser.error("--soak-interval-seconds must be non-negative")
    return args


def main(argv=None, *, runner=run_subprocess, now_fn=utc_now):
    args = parse_args(argv)
    exit_code, path, _ = run(args, runner=runner, now_fn=now_fn)
    print(path)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
