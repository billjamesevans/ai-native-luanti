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
            'printf "family_service_active=%s\\n" "$family_status"',
            'printf "fork_service_active=%s\\n" "$fork_status"',
            'printf "family_udp_listening=%s\\n" "$family_udp"',
            'printf "fork_udp_listening=%s\\n" "$fork_udp"',
            'printf "fork_version=%s\\n" "$fork_version"',
            'printf "fork_commit=%s\\n" "$fork_commit"',
            'printf "fork_restart_count=%s\\n" "${fork_restart_count:-unknown}"',
            'printf "fork_active_enter_timestamp=%s\\n" "${fork_active_enter_timestamp:-unknown}"',
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
        "failure_count": len(remote_manifest.get("failure_reasons") or []),
    }


def build_soak_evidence(args, remote_manifests: list[dict]) -> dict:
    samples = []
    max_avg_cpu = None
    max_interval_cpu = None
    max_rss_mb = None
    max_actionable_warnings = 0
    max_errors = 0
    passed = 0
    for index, remote_manifest in enumerate(remote_manifests, start=1):
        evidence = runtime_evidence(remote_manifest)
        sample = {
            "iteration": index,
            "remote_manifest_status": evidence["remote_manifest_status"],
            "clean_profile_status": evidence["clean_profile_status"],
            "server_step_workload_status": evidence["server_step_workload_status"],
            "player_load_probe_status": evidence["player_load_probe_status"],
            "cpu_status": evidence["cpu_status"],
            "cpu_sample_count": evidence["cpu_sample_count"],
            "avg_process_cpu_percent": evidence["avg_process_cpu_percent"],
            "max_interval_cpu_percent": evidence["max_interval_cpu_percent"],
            "rss_sample_count": evidence["rss_sample_count"],
            "max_rss_mb": evidence["max_rss_mb"],
            "actionable_warning_count": evidence["actionable_warning_count"],
            "server_log_error_count": evidence["server_log_error_count"],
            "failure_count": evidence["failure_count"],
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


def build_manifest(
    args,
    remote_manifest: dict,
    service_values: dict,
    *,
    soak_manifests: list[dict] | None = None,
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
    soak_evidence = build_soak_evidence(args, soak_manifests)
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
    attempted_players = runtime.get("attempted_synthetic_player_count")
    connected_players = runtime.get("connected_synthetic_player_count")
    if (
        runtime["player_load_probe_kind"] != "headless_client_load"
        or runtime["headless_player_supported"] is not True
        or not isinstance(attempted_players, (int, float))
        or attempted_players <= 0
        or not isinstance(connected_players, (int, float))
        or connected_players <= 0
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


def run(args, *, runner=run_subprocess, now_fn=utc_now):
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
            time.sleep(args.soak_interval_seconds)

    remote_manifest = remote_manifests[-1]

    service_result = runner(
        ssh_command(args, remote_service_command(args)),
        timeout=args.ssh_timeout,
    )
    service_values = parse_key_values(service_result.stdout)
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
    parser.add_argument("--family-service", default="luanti-family.service")
    parser.add_argument("--fork-service", default="ai-native-luanti-test.service")
    parser.add_argument("--family-port", type=int, default=30000)
    parser.add_argument("--fork-port", type=int, default=30001)
    parser.add_argument("--headless-player-count", type=int, default=1)
    parser.add_argument("--headless-player-timeout", type=float, default=2.0)
    parser.add_argument("--soak-iterations", type=int, default=1, help="Number of repeated low-power verifier samples to collect.")
    parser.add_argument("--soak-interval-seconds", type=float, default=0.0, help="Delay between soak iterations.")
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
