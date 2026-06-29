#!/usr/bin/env python3
"""Run the local AI-native runtime pre-PR verification sequence."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ai_native_benchmark_capture
import ai_native_agent_product_loop_live_probe
import ai_native_compat_import_staging_pilot
import ai_native_operator_action_approval_plan
import ai_native_operator_action_approval_receipt
import ai_native_operator_task_control_executor
import ai_native_operator_task_control_command_probe
import ai_native_operator_task_control_live_probe
import ai_native_operator_control_report


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = ROOT / "local" / "benchmarks"
MANIFEST_NAME = "ai-runtime-verification-manifest.json"
OPERATOR_STATUS_NAME = "ai-runtime-operator-status.json"
OPERATOR_STATUS_LIVE_NAME = "ai-runtime-operator-status-live.json"
OPERATOR_CONTROL_REPORT_NAME = "ai-runtime-operator-control-report.json"
OPERATOR_ACTION_APPROVAL_PLAN_NAME = "ai-runtime-operator-action-approval-plan.json"
OPERATOR_ACTION_APPROVAL_RECEIPT_NAME = "ai-runtime-operator-action-approval-receipt.json"
OPERATOR_ACTION_EXECUTION_RESULT_NAME = "ai-runtime-operator-action-execution-result.json"
AGENT_PRODUCT_LOOP_LIVE_RESULT_NAME = "ai-runtime-agent-product-loop-live-result.json"
COMPAT_IMPORT_STAGING_PILOT_RESULT_NAME = "ai-runtime-compat-import-staging-pilot-result.json"
OPERATOR_TASK_CONTROL_LIVE_RESULT_NAME = "ai-runtime-operator-task-control-live-result.json"
OPERATOR_TASK_CONTROL_COMMAND_RESULT_NAME = "ai-runtime-operator-taREDACTED_KEY_FIXTURE.json"
PRODUCT_PROFILE_HYGIENE_NAME = "ai-runtime-product-profile-hygiene.json"
CLEAN_PROFILE_SUMMARY_NAME = "clean-profile-benchmark-summary.json"
OPERATOR_STATUS_REQUIRED_SECTIONS = {
    "schema_version",
    "package_kind",
    "status",
    "runtime_context",
    "server_profile_hygiene",
    "agents",
    "tasks",
    "rollback",
    "imports",
    "benchmarks",
    "operator_control",
    "safety",
    "bounds",
}


class CommandStep:
    def __init__(
        self,
        step_id: str,
        label: str,
        actual_command: list[str],
        manifest_command: list[str],
    ) -> None:
        self.id = step_id
        self.label = label
        self.actual_command = actual_command
        self.manifest_command = manifest_command


class CommandRun:
    def __init__(
        self,
        returncode: int,
        duration_seconds: float,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        self.returncode = returncode
        self.duration_seconds = duration_seconds
        self.stdout = stdout
        self.stderr = stderr


PRIVATE_REDACTIONS = (
    (re.compile(r"/Users/[^\s\"']+"), "<local-path>"),
    (re.compile(r"\bminecraftpi(?:\.home)?\b", re.I), "<private-host>"),
    (re.compile(r"\b192\.168(?:\.\d{1,3}){2}\b"), "<private-ip>"),
    (re.compile(r"\bspacebase|themepark|showcase100|disneyland100\b", re.I), "<private-demo>"),
    (re.compile(r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}"), "<secret>"),
    (re.compile(r"\bOPENAI_API_KEY\b"), "<secret-env>"),
    (re.compile(r"\bprivate_prompt\b"), "<private-prompt>"),
    (re.compile(r"\basset_payload\b"), "<asset-payload>"),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sanitize_text(value: str) -> str:
    sanitized = value.replace(str(ROOT), "<repo>")
    sanitized = sanitized.replace(str(Path.home()), "<home>")
    for pattern, replacement in PRIVATE_REDACTIONS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


def bounded_summary(stdout: str, stderr: str, max_chars: int) -> str:
    text = stderr.strip() or stdout.strip()
    text = sanitize_text(text)
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def logical_run_dir(args) -> str:
    return "/".join(
        [
            "local",
            "benchmarks",
            args.hardware_class,
            ai_native_benchmark_capture.path_part(args.date),
            ai_native_benchmark_capture.path_part(args.luanti_commit),
        ]
    )


def physical_run_dir(args) -> Path:
    return (
        Path(args.output_root)
        / args.hardware_class
        / ai_native_benchmark_capture.path_part(args.date)
        / ai_native_benchmark_capture.path_part(args.luanti_commit)
    )


def logical_path(args, filename: str) -> str:
    return f"{logical_run_dir(args)}/{filename}"


def operator_status_artifact_path(args) -> Path:
    return physical_run_dir(args) / operator_status_artifact_name(args)


def product_profile_hygiene_artifact_path(args) -> Path:
    return physical_run_dir(args) / PRODUCT_PROFILE_HYGIENE_NAME


def clean_profile_summary_artifact_path(args) -> Path:
    return physical_run_dir(args) / CLEAN_PROFILE_SUMMARY_NAME


def operator_control_report_artifact_path(args) -> Path:
    return physical_run_dir(args) / OPERATOR_CONTROL_REPORT_NAME


def operator_action_approval_plan_artifact_path(args) -> Path:
    return physical_run_dir(args) / OPERATOR_ACTION_APPROVAL_PLAN_NAME


def operator_action_approval_receipt_artifact_path(args) -> Path:
    return physical_run_dir(args) / OPERATOR_ACTION_APPROVAL_RECEIPT_NAME


def operator_action_execution_result_artifact_path(args) -> Path:
    return physical_run_dir(args) / OPERATOR_ACTION_EXECUTION_RESULT_NAME


def agent_product_loop_live_result_artifact_path(args) -> Path:
    return physical_run_dir(args) / AGENT_PRODUCT_LOOP_LIVE_RESULT_NAME


def compat_import_staging_pilot_result_artifact_path(args) -> Path:
    return physical_run_dir(args) / COMPAT_IMPORT_STAGING_PILOT_RESULT_NAME


def operator_task_control_live_result_artifact_path(args) -> Path:
    return physical_run_dir(args) / OPERATOR_TASK_CONTROL_LIVE_RESULT_NAME


def operator_task_control_command_result_artifact_path(args) -> Path:
    return physical_run_dir(args) / OPERATOR_TASK_CONTROL_COMMAND_RESULT_NAME


def operator_status_artifact_name(args) -> str:
    if args.operator_status_source == "live":
        return OPERATOR_STATUS_LIVE_NAME
    return OPERATOR_STATUS_NAME


def operator_status_step_id(args) -> str:
    if args.operator_status_source == "live":
        return "operator_status_live_command"
    return "operator_status_package"


def operator_status_source_kind(args) -> str:
    if args.operator_status_source == "live":
        return "live_command"
    return "command_surrogate"


def operator_status_execution_path(args) -> str:
    if args.operator_status_source == "live":
        return "disposable_worldmod_registered_chatcommand"
    return "python_package_surrogate"


def operator_status_generated_at(args) -> str:
    return f"{ai_native_benchmark_capture.path_part(args.date)}T00:00:00Z"


def python_manifest_command(*parts: str) -> list[str]:
    return ["python3", *parts]


def resolve_server_bin(server_bin: str) -> str:
    path = Path(server_bin)
    if path.is_absolute():
        return str(path)
    return str(ROOT / path)


def server_manifest_bin(server_bin: str) -> str:
    path = Path(server_bin)
    if path.is_absolute():
        try:
            return path.relative_to(ROOT).as_posix()
        except ValueError:
            return "<server-bin>"
    return path.as_posix()


def build_steps(args) -> list[CommandStep]:
    actual_profile_args = []
    manifest_profile_args = []
    if args.game_profile == "ai_runtime":
        actual_profile_args = [
            "--game-profile",
            "ai_runtime",
            "--server-bin",
            args.server_bin,
            "--profile-sample-seconds",
            str(args.profile_sample_seconds),
            "--profile-startup-timeout",
            str(args.profile_startup_timeout),
        ]
        manifest_profile_args = [
            "--game-profile",
            "ai_runtime",
            "--server-bin",
            server_manifest_bin(args.server_bin),
            "--profile-sample-seconds",
            str(args.profile_sample_seconds),
            "--profile-startup-timeout",
            str(args.profile_startup_timeout),
        ]
        if args.profile_port:
            actual_profile_args += ["--profile-port", str(args.profile_port)]
            manifest_profile_args += ["--profile-port", str(args.profile_port)]
        if args.headless_player_command:
            actual_profile_args += [
                "--headless-player-command",
                args.headless_player_command,
                "--headless-player-count",
                str(args.headless_player_count),
                "--headless-player-timeout",
                str(args.headless_player_timeout),
            ]
            manifest_profile_args += [
                "--headless-player-command",
                "<headless-player-command>",
                "--headless-player-count",
                str(args.headless_player_count),
                "--headless-player-timeout",
                str(args.headless_player_timeout),
            ]

    steps = [
        CommandStep(
            "utility_contract_tests",
            "AI-native Python utility contract tests",
            [args.python, "-m", "unittest", "discover", "util/tests"],
            python_manifest_command("-m", "unittest", "discover", "util/tests"),
        ),
        build_product_profile_hygiene_step(args),
        CommandStep(
            "branch_benchmark_gate",
            "Branch benchmark gate against accepted local baseline",
            [
                args.python,
                "util/ai_native_benchmark_gate.py",
                "--output-root",
                str(args.output_root),
                "--hardware-class",
                args.hardware_class,
                "--date",
                args.date,
                "--luanti-commit",
                args.luanti_commit,
            ]
            + actual_profile_args
            + (["--confirm-low-power-backup"] if args.confirm_low_power_backup else []),
            python_manifest_command(
                "util/ai_native_benchmark_gate.py",
                "--output-root",
                "local/benchmarks",
                "--hardware-class",
                args.hardware_class,
                "--date",
                args.date,
                "--luanti-commit",
                args.luanti_commit,
            )
            + manifest_profile_args
            + (["--confirm-low-power-backup"] if args.confirm_low_power_backup else []),
        ),
        build_operator_status_step(args),
        build_agent_product_loop_live_step(args),
        build_compat_import_staging_pilot_step(args),
        build_operator_task_control_live_step(args),
        build_operator_task_control_command_step(args),
        CommandStep(
            "ai_runtime_focused_tests",
            "Focused AI runtime unit smoke",
            [
                resolve_server_bin(args.server_bin),
                "--run-unittests",
                "--test-module",
                "TestAIRuntime",
            ],
            [
                server_manifest_bin(args.server_bin),
                "--run-unittests",
                "--test-module",
                "TestAIRuntime",
            ],
        ),
    ]

    if args.include_full_unittests:
        steps.append(
            CommandStep(
                "full_engine_unittests",
                "Full engine unit test suite",
                [resolve_server_bin(args.server_bin), "--run-unittests"],
                [server_manifest_bin(args.server_bin), "--run-unittests"],
            )
        )

    return steps


def build_product_profile_hygiene_step(args) -> CommandStep:
    return CommandStep(
        "product_profile_hygiene",
        "Clean ai_runtime product-profile fixture and privacy gate",
        [
            args.python,
            "util/ai_native_product_profile_verify.py",
            "--root",
            ".",
            "--output",
            str(product_profile_hygiene_artifact_path(args)),
        ],
        python_manifest_command(
            "util/ai_native_product_profile_verify.py",
            "--root",
            ".",
            "--output",
            logical_path(args, PRODUCT_PROFILE_HYGIENE_NAME),
        ),
    )


def build_operator_status_step(args) -> CommandStep:
    if args.operator_status_source == "live":
        return CommandStep(
            "operator_status_live_command",
            "Live operator status command probe in disposable ai_runtime world",
            [
                args.python,
                "util/ai_native_operator_status_live_command.py",
                "--root",
                ".",
                "--server-bin",
                args.server_bin,
                "--output",
                str(operator_status_artifact_path(args)),
                "--generated-at",
                operator_status_generated_at(args),
                "--max-bytes",
                str(args.operator_status_max_bytes),
                "--timeout",
                str(args.operator_status_live_timeout),
            ],
            python_manifest_command(
                "util/ai_native_operator_status_live_command.py",
                "--root",
                ".",
                "--server-bin",
                server_manifest_bin(args.server_bin),
                "--output",
                logical_path(args, OPERATOR_STATUS_LIVE_NAME),
                "--generated-at",
                operator_status_generated_at(args),
                "--max-bytes",
                str(args.operator_status_max_bytes),
                "--timeout",
                str(args.operator_status_live_timeout),
            ),
        )
    return CommandStep(
        "operator_status_package",
        "Operator status package command surrogate",
        [
            args.python,
            "util/ai_native_operator_status_package.py",
            "--root",
            ".",
            "--output",
            str(operator_status_artifact_path(args)),
            "--generated-at",
            operator_status_generated_at(args),
            "--max-bytes",
            str(args.operator_status_max_bytes),
        ],
        python_manifest_command(
            "util/ai_native_operator_status_package.py",
            "--root",
            ".",
            "--output",
            logical_path(args, OPERATOR_STATUS_NAME),
            "--generated-at",
            operator_status_generated_at(args),
            "--max-bytes",
            str(args.operator_status_max_bytes),
        ),
    )


def build_agent_product_loop_live_step(args) -> CommandStep:
    return CommandStep(
        "agent_product_loop_live_probe",
        "First-party agent product-loop probe in disposable ai_runtime world",
        [
            args.python,
            "util/ai_native_agent_product_loop_live_probe.py",
            "--root",
            ".",
            "--server-bin",
            args.server_bin,
            "--output",
            str(agent_product_loop_live_result_artifact_path(args)),
            "--generated-at",
            operator_status_generated_at(args),
            "--max-bytes",
            str(args.agent_product_loop_live_result_max_bytes),
            "--timeout",
            str(args.agent_product_loop_live_timeout),
        ],
        python_manifest_command(
            "util/ai_native_agent_product_loop_live_probe.py",
            "--root",
            ".",
            "--server-bin",
            server_manifest_bin(args.server_bin),
            "--output",
            logical_path(args, AGENT_PRODUCT_LOOP_LIVE_RESULT_NAME),
            "--generated-at",
            operator_status_generated_at(args),
            "--max-bytes",
            str(args.agent_product_loop_live_result_max_bytes),
            "--timeout",
            str(args.agent_product_loop_live_timeout),
        ),
    )


def build_compat_import_staging_pilot_step(args) -> CommandStep:
    return CommandStep(
        "compat_import_staging_pilot",
        "Public-safe compatibility import pilot in disposable ai_runtime staging world",
        [
            args.python,
            "util/ai_native_compat_import_staging_pilot.py",
            "--root",
            ".",
            "--server-bin",
            args.server_bin,
            "--output",
            str(compat_import_staging_pilot_result_artifact_path(args)),
            "--generated-at",
            operator_status_generated_at(args),
            "--max-bytes",
            str(args.compat_import_staging_pilot_result_max_bytes),
            "--timeout",
            str(args.compat_import_staging_pilot_timeout),
        ],
        python_manifest_command(
            "util/ai_native_compat_import_staging_pilot.py",
            "--root",
            ".",
            "--server-bin",
            server_manifest_bin(args.server_bin),
            "--output",
            logical_path(args, COMPAT_IMPORT_STAGING_PILOT_RESULT_NAME),
            "--generated-at",
            operator_status_generated_at(args),
            "--max-bytes",
            str(args.compat_import_staging_pilot_result_max_bytes),
            "--timeout",
            str(args.compat_import_staging_pilot_timeout),
        ),
    )


def build_operator_task_control_live_step(args) -> CommandStep:
    return CommandStep(
        "operator_task_control_live_probe",
        "Receipt-gated task control probe in disposable ai_runtime queue",
        [
            args.python,
            "util/ai_native_operator_task_control_live_probe.py",
            "--root",
            ".",
            "--server-bin",
            args.server_bin,
            "--output",
            str(operator_task_control_live_result_artifact_path(args)),
            "--generated-at",
            operator_status_generated_at(args),
            "--max-bytes",
            str(args.operator_task_control_live_result_max_bytes),
            "--timeout",
            str(args.operator_task_control_live_timeout),
        ],
        python_manifest_command(
            "util/ai_native_operator_task_control_live_probe.py",
            "--root",
            ".",
            "--server-bin",
            server_manifest_bin(args.server_bin),
            "--output",
            logical_path(args, OPERATOR_TASK_CONTROL_LIVE_RESULT_NAME),
            "--generated-at",
            operator_status_generated_at(args),
            "--max-bytes",
            str(args.operator_task_control_live_result_max_bytes),
            "--timeout",
            str(args.operator_task_control_live_timeout),
        ),
    )


def build_operator_task_control_command_step(args) -> CommandStep:
    return CommandStep(
        "operator_task_control_command_probe",
        "Receipt-gated task control command probe in disposable ai_runtime world",
        [
            args.python,
            "util/ai_native_operator_task_control_command_probe.py",
            "--root",
            ".",
            "--server-bin",
            args.server_bin,
            "--output",
            str(operator_task_control_command_result_artifact_path(args)),
            "--generated-at",
            operator_status_generated_at(args),
            "--max-bytes",
            str(args.operator_task_control_command_result_max_bytes),
            "--timeout",
            str(args.operator_task_control_command_timeout),
        ],
        python_manifest_command(
            "util/ai_native_operator_task_control_command_probe.py",
            "--root",
            ".",
            "--server-bin",
            server_manifest_bin(args.server_bin),
            "--output",
            logical_path(args, OPERATOR_TASK_CONTROL_COMMAND_RESULT_NAME),
            "--generated-at",
            operator_status_generated_at(args),
            "--max-bytes",
            str(args.operator_task_control_command_result_max_bytes),
            "--timeout",
            str(args.operator_task_control_command_timeout),
        ),
    )


def run_subprocess(step: CommandStep) -> CommandRun:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            step.actual_command,
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        return CommandRun(
            completed.returncode,
            time.monotonic() - started,
            completed.stdout,
            completed.stderr,
        )
    except OSError as exc:
        return CommandRun(127, time.monotonic() - started, "", str(exc))


def benchmark_gate_artifact(args, result: CommandRun) -> str:
    for line in result.stdout.splitlines():
        candidate = line.strip()
        if candidate.startswith("local/benchmarks/") and candidate.endswith(
            "benchmark-gate-manifest.json"
        ):
            return sanitize_text(candidate)
    return logical_path(args, "benchmark-gate-manifest.json")


def artifact_has_private_content(raw_payload: str) -> bool:
    return any(pattern.search(raw_payload) for pattern, _ in PRIVATE_REDACTIONS)


def operator_control_findings(payload: dict, step_id: str) -> tuple[dict, list[str]]:
    evidence = {
        "operator_control_status": "fail",
        "operator_control_action_mode": "missing",
        "operator_control_recommendations": None,
    }
    reasons = []
    control = payload.get("operator_control")
    if not isinstance(control, dict):
        reasons.append(f"{step_id} operator_control missing or invalid")
        return evidence, reasons

    action_mode = control.get("action_mode")
    recommendations_total = control.get("recommendations_total")
    summaries = control.get("summaries")
    evidence["operator_control_action_mode"] = sanitize_text(str(action_mode))
    evidence["operator_control_recommendations"] = recommendations_total

    if control.get("surface_kind") != "read_only_task_rollback_control":
        reasons.append(f"{step_id} operator_control surface_kind is invalid")
    if action_mode != "dry_run_only":
        reasons.append(f"{step_id} operator_control action_mode is not dry_run_only")
    if control.get("mutation_performed") is not False:
        reasons.append(f"{step_id} operator_control mutation_performed is not false")
    if not isinstance(recommendations_total, int):
        reasons.append(f"{step_id} operator_control recommendations_total is not numeric")
    if summaries is None and recommendations_total == 0:
        summaries = []
    if not isinstance(summaries, list):
        reasons.append(f"{step_id} operator_control summaries is not a list")
        evidence["operator_control_status"] = "fail"
        return evidence, reasons

    for index, summary in enumerate(summaries):
        if not isinstance(summary, dict):
            reasons.append(f"{step_id} operator_control summary {index} is invalid")
            continue
        if summary.get("dry_run_only") is not True:
            reasons.append(f"{step_id} operator_control summary {index} is not dry_run_only")
        if summary.get("will_mutate") is not False:
            reasons.append(f"{step_id} operator_control summary {index} can mutate")
        if not isinstance(summary.get("target_id"), str) or not summary.get("target_id"):
            reasons.append(f"{step_id} operator_control summary {index} missing target_id")
        if not isinstance(summary.get("target_kind"), str) or not summary.get("target_kind"):
            reasons.append(f"{step_id} operator_control summary {index} missing target_kind")
        safe_next_action = summary.get("safe_next_action")
        if not isinstance(safe_next_action, str) or not safe_next_action:
            reasons.append(f"{step_id} operator_control summary {index} missing safe_next_action")
        elif safe_next_action.startswith(("cancel_", "execute_", "apply_", "approve_", "mutate_")):
            reasons.append(f"{step_id} operator_control summary {index} safe_next_action mutates")

    evidence["operator_control_status"] = "fail" if reasons else "pass"
    return evidence, reasons


def operator_status_evidence(args) -> tuple[dict, list[str]]:
    path = operator_status_artifact_path(args)
    source_path = logical_path(args, operator_status_artifact_name(args))
    report_path = operator_control_report_artifact_path(args)
    report_source_path = logical_path(args, OPERATOR_CONTROL_REPORT_NAME)
    approval_plan_path = operator_action_approval_plan_artifact_path(args)
    approval_plan_source_path = logical_path(args, OPERATOR_ACTION_APPROVAL_PLAN_NAME)
    approval_receipt_path = operator_action_approval_receipt_artifact_path(args)
    approval_receipt_source_path = logical_path(args, OPERATOR_ACTION_APPROVAL_RECEIPT_NAME)
    execution_result_path = operator_action_execution_result_artifact_path(args)
    execution_result_source_path = logical_path(args, OPERATOR_ACTION_EXECUTION_RESULT_NAME)
    step_id = operator_status_step_id(args)
    evidence = {
        "status": "fail",
        "source_kind": operator_status_source_kind(args),
        "source_path": source_path,
        "live_command": "/ai_runtime_operator_status",
        "direct_command_execution": args.operator_status_source == "live",
        "execution_path": operator_status_execution_path(args),
        "operator_control_report_status": "fail",
        "operator_control_report_path": report_source_path,
        "operator_action_approval_plan_status": "fail",
        "operator_action_approval_plan_path": approval_plan_source_path,
        "operator_action_approval_receipt_status": "fail",
        "operator_action_approval_receipt_path": approval_receipt_source_path,
        "operator_action_execution_status": "fail",
        "operator_action_execution_path": execution_result_source_path,
    }
    reasons = []
    if not path.is_file():
        reasons.append(f"{step_id} artifact missing")
        evidence["failure_count"] = len(reasons)
        return evidence, reasons

    try:
        raw_payload = path.read_text(encoding="utf-8")
        payload = json.loads(raw_payload)
    except (OSError, json.JSONDecodeError) as exc:
        reasons.append(f"{step_id} artifact unreadable: {type(exc).__name__}")
        evidence["failure_count"] = len(reasons)
        return evidence, reasons

    missing_sections = sorted(OPERATOR_STATUS_REQUIRED_SECTIONS - set(payload))
    if missing_sections:
        reasons.append(
            f"{step_id} missing required sections: "
            + ",".join(missing_sections)
        )
    if payload.get("package_kind") != "ai_native_operator_status_package":
        reasons.append(f"{step_id} has unexpected package_kind")
    if artifact_has_private_content(raw_payload):
        reasons.append(f"{step_id} contains private patterns")

    bounds = payload.get("bounds") if isinstance(payload.get("bounds"), dict) else {}
    output_bytes = bounds.get("output_bytes")
    max_bytes = bounds.get("max_bytes", args.operator_status_max_bytes)
    if not isinstance(output_bytes, int):
        reasons.append(f"{step_id} missing numeric output_bytes")
    if not isinstance(max_bytes, int):
        reasons.append(f"{step_id} missing numeric max_bytes")
    if isinstance(output_bytes, int) and isinstance(max_bytes, int):
        if output_bytes > max_bytes:
            reasons.append(f"{step_id} output_bytes exceeds max_bytes")
        if output_bytes > args.operator_status_max_bytes:
            reasons.append(f"{step_id} output_bytes exceeds harness byte budget")

    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    if safety.get("public_safe_output") is not True:
        reasons.append(f"{step_id} public_safe_output is not true")

    ux_probe = (
        payload.get("operator_ux_command_probe")
        if isinstance(payload.get("operator_ux_command_probe"), dict)
        else {}
    )
    ux_fields = [
        "task_list_checked",
        "task_detail_checked",
        "audit_review_checked",
        "rollback_review_checked",
        "import_review_checked",
        "refusal_checked",
    ]
    if args.operator_status_source == "live":
        if ux_probe.get("status") != "pass":
            reasons.append(f"{step_id} focused operator status view probe did not pass")
        if ux_probe.get("read_only_views") is not True:
            reasons.append(f"{step_id} focused operator status views are not read-only")
        for field in ux_fields:
            if ux_probe.get(field) is not True:
                reasons.append(f"{step_id} focused operator status view missing {field}")
        views_checked_total = ux_probe.get("views_checked_total")
        if not isinstance(views_checked_total, int) or views_checked_total < 5:
            reasons.append(f"{step_id} focused operator status views_checked_total is too low")
        max_view_output_bytes = ux_probe.get("max_view_output_bytes")
        if not isinstance(max_view_output_bytes, int) or max_view_output_bytes > 5000:
            reasons.append(f"{step_id} focused operator status view output budget invalid")

    control_evidence, control_reasons = operator_control_findings(payload, step_id)
    reasons.extend(control_reasons)
    try:
        report = ai_native_operator_control_report.build_report(
            payload,
            generated_at=operator_status_generated_at(args),
            source_path=source_path,
            max_bytes=args.operator_control_report_max_bytes,
        )
        write_json(report_path, report)
        approval_plan = ai_native_operator_action_approval_plan.build_plan(
            report,
            generated_at=operator_status_generated_at(args),
            source_path=report_source_path,
            max_bytes=args.operator_action_approval_plan_max_bytes,
        )
        write_json(approval_plan_path, approval_plan)
        approval_decision = ai_native_operator_action_approval_receipt.sample_decision_document(
            approval_plan,
            generated_at=operator_status_generated_at(args),
        )
        approval_receipt = ai_native_operator_action_approval_receipt.build_receipt(
            approval_plan,
            approval_decision,
            generated_at=operator_status_generated_at(args),
            source_path=approval_plan_source_path,
            max_bytes=args.operator_action_approval_receipt_max_bytes,
        )
        write_json(approval_receipt_path, approval_receipt)
        task_state = ai_native_operator_task_control_executor.sample_task_state_for_receipt(
            approval_receipt
        )
        execution_result = ai_native_operator_task_control_executor.build_execution_result(
            approval_receipt,
            task_state,
            generated_at=operator_status_generated_at(args),
            source_path=approval_receipt_source_path,
            executor_capabilities=["task.inspect", "task.cancel", "task.retry"],
            max_bytes=args.operator_action_execution_result_max_bytes,
        )
        write_json(execution_result_path, execution_result)
        evidence.update({
            "operator_control_report_status": "pass",
            "operator_control_report_output_bytes": report["bounds"]["output_bytes"],
            "operator_control_report_items": report["summary"]["items_total"],
            "operator_action_approval_plan_status": "pass",
            "operator_action_approval_plan_output_bytes": approval_plan["bounds"]["output_bytes"],
            "operator_action_approval_plan_items": approval_plan["summary"]["actions_total"],
            "operator_action_approval_receipt_status": "pass",
            "operator_action_approval_receipt_output_bytes": approval_receipt["bounds"]["output_bytes"],
            "operator_action_approval_receipt_items": approval_receipt["summary"]["decisions_total"],
            "operator_action_execution_status": "pass",
            "operator_action_execution_output_bytes": execution_result["bounds"]["output_bytes"],
            "operator_action_execution_items": execution_result["summary"]["decisions_total"],
        })
    except (OSError, ValueError) as exc:
        reasons.append(
            f"{step_id} operator control report, approval plan, approval receipt, "
            "or action execution result failed: "
            f"{type(exc).__name__}"
        )

    evidence.update({
        "status": "fail" if reasons else "pass",
        "package_status": sanitize_text(str(payload.get("status", "unknown"))),
        "output_bytes": output_bytes,
        "max_bytes": max_bytes,
        "truncated": bounds.get("truncated") is True,
        "required_sections_present": not missing_sections,
        "private_scan_status": "fail" if artifact_has_private_content(raw_payload) else "pass",
        "failure_count": len(reasons),
        "operator_ux_command_probe_status": sanitize_text(str(ux_probe.get("status", "not_run"))),
        "operator_ux_task_list_checked": ux_probe.get("task_list_checked") is True,
        "operator_ux_task_detail_checked": ux_probe.get("task_detail_checked") is True,
        "operator_ux_audit_review_checked": ux_probe.get("audit_review_checked") is True,
        "operator_ux_rollback_review_checked": ux_probe.get("rollback_review_checked") is True,
        "operator_ux_import_review_checked": ux_probe.get("import_review_checked") is True,
        "operator_ux_refusal_checked": ux_probe.get("refusal_checked") is True,
        "operator_ux_views_checked_total": ux_probe.get("views_checked_total", 0),
        "operator_ux_max_view_output_bytes": ux_probe.get("max_view_output_bytes", 0),
    })
    evidence.update(control_evidence)
    return evidence, reasons


def product_profile_evidence(args) -> tuple[dict, list[str]]:
    path = product_profile_hygiene_artifact_path(args)
    source_path = logical_path(args, PRODUCT_PROFILE_HYGIENE_NAME)
    evidence = {
        "status": "fail",
        "source_path": source_path,
        "game_profile": None,
        "manifest_path": None,
        "product_mods": [],
        "violation_count": None,
        "no_private_content": False,
        "dev_surfaces_disabled_by_default": False,
        "test_fixtures_explicit_only": False,
        "runtime_surfaces_available": False,
        "runtime_surface_count": 0,
        "runtime_surface_commands": [],
    }
    reasons = []
    if not path.is_file():
        reasons.append("product_profile_hygiene artifact missing")
        evidence["failure_count"] = len(reasons)
        return evidence, reasons

    try:
        raw_payload = path.read_text(encoding="utf-8")
        payload = json.loads(raw_payload)
    except (OSError, json.JSONDecodeError) as exc:
        reasons.append(f"product_profile_hygiene artifact unreadable: {type(exc).__name__}")
        evidence["failure_count"] = len(reasons)
        return evidence, reasons

    if artifact_has_private_content(raw_payload):
        reasons.append("product_profile_hygiene contains private patterns")

    profile = payload.get("profile") if isinstance(payload.get("profile"), dict) else {}
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    violations = payload.get("violations") if isinstance(payload.get("violations"), list) else []
    product_mods = profile.get("product_mods") if isinstance(profile.get("product_mods"), list) else []
    runtime_surfaces = (
        payload.get("required_runtime_surfaces")
        if isinstance(payload.get("required_runtime_surfaces"), list)
        else []
    )
    runtime_surface_commands = [
        sanitize_text(str(surface.get("command", "")))
        for surface in runtime_surfaces
        if isinstance(surface, dict)
    ]
    evidence.update({
        "status": "fail",
        "game_profile": sanitize_text(str(profile.get("gameid", ""))),
        "manifest_path": sanitize_text(str(profile.get("manifest_path", ""))),
        "product_mods": [sanitize_text(str(mod)) for mod in product_mods],
        "violation_count": len(violations),
        "no_private_content": safety.get("no_private_content") is True,
        "dev_surfaces_disabled_by_default": safety.get("dev_surfaces_disabled_by_default") is True,
        "test_fixtures_explicit_only": safety.get("test_fixtures_explicit_only") is True,
        "runtime_surfaces_available": safety.get("runtime_surfaces_available") is True,
        "runtime_surface_count": len(runtime_surfaces),
        "runtime_surface_commands": runtime_surface_commands,
    })

    if payload.get("status") != "pass":
        reasons.append("product_profile_hygiene status is not pass")
    if profile.get("gameid") != "ai_runtime":
        reasons.append("product_profile_hygiene gameid is not ai_runtime")
    if product_mods != ["ai_runtime_base"]:
        reasons.append("product_profile_hygiene product_mods changed from clean profile")
    if safety.get("no_private_content") is not True:
        reasons.append("product_profile_hygiene private content scan failed")
    if safety.get("dev_surfaces_disabled_by_default") is not True:
        reasons.append("product_profile_hygiene dev surfaces are not disabled by default")
    if safety.get("test_fixtures_explicit_only") is not True:
        reasons.append("product_profile_hygiene test fixtures are not explicit-only")
    if safety.get("runtime_surfaces_available") is not True:
        reasons.append("product_profile_hygiene runtime surfaces are not available")
    for surface in runtime_surfaces:
        if not isinstance(surface, dict):
            reasons.append("product_profile_hygiene runtime surface entry is invalid")
            continue
        if surface.get("status") != "present":
            reasons.append("product_profile_hygiene runtime surface is not present")
        if surface.get("loaded_by_default_product_profile") is not True:
            reasons.append("product_profile_hygiene runtime surface is not loaded by default")
        if surface.get("command_registered") is not True:
            reasons.append("product_profile_hygiene runtime surface command is not registered")
        if surface.get("server_privilege_required") is not True:
            reasons.append("product_profile_hygiene runtime surface server privilege is missing")
        if surface.get("public_safe_output_required") is not True:
            reasons.append("product_profile_hygiene runtime surface public-safe output is not required")

    evidence["status"] = "fail" if reasons else "pass"
    evidence["failure_count"] = len(reasons)
    return evidence, reasons


def positive_number(value) -> bool:
    return type(value) in (int, float) and value > 0


def nonnegative_number(value) -> bool:
    return type(value) in (int, float) and value >= 0


def warning_count(section: dict, field: str) -> int:
    value = section.get(field)
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(0, value)
    return 0


def actionable_warning_count(section: dict) -> int:
    if "actionable_server_log_warning_count" in section:
        return warning_count(section, "actionable_server_log_warning_count")
    total = warning_count(section, "server_log_warning_count")
    expected = warning_count(section, "expected_server_log_warning_count")
    return max(0, total - expected)


def clean_profile_workload_evidence(args) -> tuple[dict, list[str]]:
    path = clean_profile_summary_artifact_path(args)
    source_path = logical_path(args, CLEAN_PROFILE_SUMMARY_NAME)
    evidence = {
        "status": "fail",
        "source_path": source_path,
        "overall_status": None,
        "game_profile": None,
        "failure_note_count": None,
        "private_scan_status": "fail",
        "server_step_workload_status": "missing",
        "server_step_workload_kind": None,
        "server_step_attempted_samples": None,
        "server_step_completed_samples": None,
        "server_step_failed_samples": None,
        "server_step_stayed_listening": False,
        "player_load_probe_status": "missing",
        "player_load_probe_kind": None,
        "headless_player_supported": False,
        "headless_player_required": args.require_headless_player_probe,
        "attempted_synthetic_player_count": None,
        "connected_synthetic_player_count": None,
        "latency_proxy_supported": False,
        "scale_gate_status": "missing",
        "scale_gate_required_synthetic_player_count": None,
        "scale_gate_required_concurrent_task_count": None,
        "map_chunk_workload_status": "missing",
        "map_chunk_workload_kind": None,
        "mapblock_rows_created": None,
        "cpu_status": "missing",
        "cpu_sample_count": None,
        "avg_process_cpu_percent": None,
        "max_interval_cpu_percent": None,
        "rss_sample_count": None,
        "max_rss_kb": None,
        "server_log_error_count": None,
        "actionable_warning_count": None,
        "unsafe_operation_count": None,
    }
    reasons = []
    if not path.is_file():
        reasons.append("clean_profile_summary artifact missing")
        evidence["failure_count"] = len(reasons)
        return evidence, reasons

    try:
        raw_payload = path.read_text(encoding="utf-8")
        payload = json.loads(raw_payload)
    except (OSError, json.JSONDecodeError) as exc:
        reasons.append(f"clean_profile_summary artifact unreadable: {type(exc).__name__}")
        evidence["failure_count"] = len(reasons)
        return evidence, reasons

    private_scan_failed = artifact_has_private_content(raw_payload)
    if private_scan_failed:
        reasons.append("clean_profile_summary contains private patterns")

    game_profile = payload.get("game_profile") if isinstance(payload.get("game_profile"), dict) else {}
    failure_notes = payload.get("failure_notes")
    if not isinstance(failure_notes, list):
        failure_notes = []
        reasons.append("clean_profile_summary failure_notes is not a list")
    evidence.update({
        "overall_status": sanitize_text(str(payload.get("overall_status", ""))),
        "game_profile": sanitize_text(str(game_profile.get("gameid", ""))),
        "failure_note_count": len(failure_notes),
        "private_scan_status": "fail" if private_scan_failed else "pass",
    })

    if payload.get("overall_status") != "pass":
        reasons.append("clean_profile_summary overall_status is not pass")
    if game_profile.get("gameid") != "ai_runtime":
        reasons.append("clean_profile_summary game_profile.gameid is not ai_runtime")
    if failure_notes:
        reasons.append("clean_profile_summary failure_notes present")

    run_context = payload.get("run_context") if isinstance(payload.get("run_context"), dict) else {}
    for flag in (
        "requires_private_world",
        "requires_private_assets",
        "requires_live_pi",
        "requires_model_network",
    ):
        if run_context.get(flag) is True:
            reasons.append(f"clean_profile_summary {flag} is true")

    comparison_summary = (
        payload.get("comparison_summary")
        if isinstance(payload.get("comparison_summary"), dict)
        else {}
    )
    actionable_warnings = 0
    for section_name in (
        "steady_tick_behavior",
        "server_step_workload",
        "player_load_tick_probe",
    ):
        section = comparison_summary.get(section_name)
        if isinstance(section, dict):
            actionable_warnings += actionable_warning_count(section)
    evidence["actionable_warning_count"] = actionable_warnings
    if actionable_warnings > 0:
        reasons.append("clean_profile_summary actionable server log warnings present")

    server_step = comparison_summary.get("server_step_workload")
    server_log_error_total = 0
    if not isinstance(server_step, dict):
        reasons.append("clean_profile_summary server_step_workload missing")
    else:
        attempted = server_step.get("attempted_sample_count")
        completed = server_step.get("completed_sample_count")
        failed = server_step.get("failed_sample_count")
        server_log_error_total += int(server_step.get("server_log_error_count") or 0)
        evidence.update({
            "server_step_workload_status": sanitize_text(str(server_step.get("workload_status", ""))),
            "server_step_workload_kind": sanitize_text(str(server_step.get("workload_kind", ""))),
            "server_step_attempted_samples": attempted,
            "server_step_completed_samples": completed,
            "server_step_failed_samples": failed,
            "server_step_stayed_listening": server_step.get("server_stayed_listening") is True,
        })
        if server_step.get("workload_status") != "pass":
            reasons.append("clean_profile_summary server_step_workload status is not pass")
        if server_step.get("workload_kind") != "server_step_liveness":
            reasons.append("clean_profile_summary server_step_workload kind is invalid")
        if not positive_number(attempted):
            reasons.append("clean_profile_summary server_step_workload attempted_sample_count must be positive")
        if not positive_number(completed):
            reasons.append("clean_profile_summary server_step_workload completed_sample_count must be positive")
        if failed != 0:
            reasons.append("clean_profile_summary server_step_workload failed_sample_count must be 0")
        if server_step.get("server_stayed_listening") is not True:
            reasons.append("clean_profile_summary server_step_workload server_stayed_listening is not true")
        if (server_step.get("server_log_error_count") or 0) != 0:
            reasons.append("clean_profile_summary server_step_workload server_log_error_count must be 0")

    player_probe = comparison_summary.get("player_load_tick_probe")
    if not isinstance(player_probe, dict):
        reasons.append("clean_profile_summary player_load_tick_probe missing")
    else:
        attempted_players = player_probe.get("attempted_synthetic_player_count")
        connected_players = player_probe.get("connected_synthetic_player_count")
        completed_players = player_probe.get("completed_synthetic_player_count")
        join_latency = (
            player_probe.get("join_latency_proxy_ms")
            if isinstance(player_probe.get("join_latency_proxy_ms"), dict)
            else {}
        )
        server_log_error_total += int(player_probe.get("server_log_error_count") or 0)
        evidence.update({
            "player_load_probe_status": sanitize_text(str(player_probe.get("probe_status", ""))),
            "player_load_probe_kind": sanitize_text(str(player_probe.get("probe_kind", ""))),
            "headless_player_supported": player_probe.get("headless_player_supported") is True,
            "attempted_synthetic_player_count": attempted_players,
            "connected_synthetic_player_count": connected_players,
            "completed_synthetic_player_count": completed_players,
            "latency_proxy_supported": player_probe.get("latency_proxy_supported") is True,
            "latency_probe_kind": sanitize_text(str(player_probe.get("latency_probe_kind", ""))),
            "join_latency_proxy_sample_count": join_latency.get("sample_count"),
        })
        if player_probe.get("probe_status") != "pass":
            reasons.append("clean_profile_summary player_load_tick_probe status is not pass")
        if player_probe.get("probe_kind") not in {"server_process_liveness", "headless_client_load"}:
            reasons.append("clean_profile_summary player_load_tick_probe kind is invalid")
        if player_probe.get("server_stayed_listening") is not True:
            reasons.append("clean_profile_summary player_load_tick_probe server_stayed_listening is not true")
        if (player_probe.get("server_log_error_count") or 0) != 0:
            reasons.append("clean_profile_summary player_load_tick_probe server_log_error_count must be 0")
        if not positive_number(player_probe.get("sample_count")):
            reasons.append("clean_profile_summary player_load_tick_probe sample_count must be positive")
        if args.require_headless_player_probe:
            if (
                player_probe.get("probe_kind") != "headless_client_load"
                or player_probe.get("headless_player_supported") is not True
            ):
                reasons.append(
                    "clean_profile_summary headless player probe required but not measured"
                )
            if not positive_number(attempted_players):
                reasons.append("clean_profile_summary attempted_synthetic_player_count must be at least 2")
            if not positive_number(connected_players):
                reasons.append("clean_profile_summary connected_synthetic_player_count must be at least 2")
            if (
                positive_number(attempted_players)
                and attempted_players < 2
            ):
                reasons.append("clean_profile_summary attempted_synthetic_player_count must be at least 2")
            if (
                positive_number(connected_players)
                and connected_players < 2
            ):
                reasons.append("clean_profile_summary connected_synthetic_player_count must be at least 2")
            if (
                nonnegative_number(attempted_players)
                and nonnegative_number(connected_players)
                and connected_players != attempted_players
            ):
                reasons.append("clean_profile_summary connected synthetic players must equal attempted synthetic players")
            if player_probe.get("latency_proxy_supported") is not True:
                reasons.append("clean_profile_summary latency_proxy_supported must be true")
            if player_probe.get("latency_probe_kind") != "headless_join_log_observation":
                reasons.append("clean_profile_summary latency_probe_kind must be headless_join_log_observation")
            if not positive_number(join_latency.get("sample_count")):
                reasons.append("clean_profile_summary join_latency_proxy_ms.sample_count must be positive")

    scale_gate = comparison_summary.get("ai_runtime_scale_gate")
    if isinstance(scale_gate, dict):
        evidence.update({
            "scale_gate_status": sanitize_text(str(scale_gate.get("scale_gate_status", ""))),
            "scale_gate_required_synthetic_player_count": scale_gate.get(
                "required_synthetic_player_count"
            ),
            "scale_gate_required_concurrent_task_count": scale_gate.get(
                "required_concurrent_task_count"
            ),
        })
        if args.require_headless_player_probe:
            if scale_gate.get("scale_gate_status") != "pass":
                reasons.append("clean_profile_summary ai_runtime_scale_gate status is not pass")
            if scale_gate.get("synthetic_disposable_only") is not True:
                reasons.append("clean_profile_summary ai_runtime_scale_gate synthetic_disposable_only is not true")
            if (scale_gate.get("required_synthetic_player_count") or 0) < 2:
                reasons.append("clean_profile_summary ai_runtime_scale_gate required_synthetic_player_count must be at least 2")
            if (scale_gate.get("required_concurrent_task_count") or 0) < 2:
                reasons.append("clean_profile_summary ai_runtime_scale_gate required_concurrent_task_count must be at least 2")
    elif args.require_headless_player_probe:
        reasons.append("clean_profile_summary ai_runtime_scale_gate missing")

    map_workload = comparison_summary.get("map_chunk_workload")
    if not isinstance(map_workload, dict):
        reasons.append("clean_profile_summary map_chunk_workload missing")
    else:
        evidence.update({
            "map_chunk_workload_status": sanitize_text(str(map_workload.get("workload_status", ""))),
            "map_chunk_workload_kind": sanitize_text(str(map_workload.get("workload_kind", ""))),
            "mapblock_rows_created": map_workload.get("mapblock_rows_created"),
        })
        if map_workload.get("workload_status") != "pass":
            reasons.append("clean_profile_summary map_chunk_workload status is not pass")
        if map_workload.get("workload_kind") != "synthetic_sqlite_mapblock_churn":
            reasons.append("clean_profile_summary map_chunk_workload kind is invalid")
        if not positive_number(map_workload.get("mapblock_rows_created")):
            reasons.append("clean_profile_summary mapblock_rows_created must be positive")
        if (map_workload.get("warning_count") or 0) != 0:
            reasons.append("clean_profile_summary map_chunk_workload warning_count must be 0")
        server_log_error_total += int(map_workload.get("error_count") or 0)
        if (map_workload.get("error_count") or 0) != 0:
            reasons.append("clean_profile_summary map_chunk_workload error_count must be 0")

    entity_runtime = comparison_summary.get("entity_runtime_operations")
    if isinstance(entity_runtime, dict):
        if (entity_runtime.get("warnings") or 0) != 0:
            reasons.append("clean_profile_summary entity_runtime_operations warnings must be 0")
        server_log_error_total += int(entity_runtime.get("errors") or 0)
        if (entity_runtime.get("errors") or 0) != 0:
            reasons.append("clean_profile_summary entity_runtime_operations errors must be 0")
    else:
        reasons.append("clean_profile_summary entity_runtime_operations missing")

    mutation_writes = comparison_summary.get("mutation_write_throughput")
    if isinstance(mutation_writes, dict):
        unsafe_operations = mutation_writes.get("unsafe_operations")
        evidence["unsafe_operation_count"] = unsafe_operations
        if (mutation_writes.get("warnings") or 0) != 0:
            reasons.append("clean_profile_summary mutation_write_throughput warnings must be 0")
        server_log_error_total += int(mutation_writes.get("errors") or 0)
        if (mutation_writes.get("errors") or 0) != 0:
            reasons.append("clean_profile_summary mutation_write_throughput errors must be 0")
        if unsafe_operations != 0:
            reasons.append("clean_profile_summary unsafe operation leakage present")
    else:
        reasons.append("clean_profile_summary mutation_write_throughput missing")

    cpu = comparison_summary.get("cpu")
    if not isinstance(cpu, dict):
        reasons.append("clean_profile_summary cpu missing")
    else:
        evidence.update({
            "cpu_status": sanitize_text(str(cpu.get("sample_status", ""))),
            "cpu_sample_count": cpu.get("cpu_sample_count"),
            "avg_process_cpu_percent": cpu.get("avg_process_cpu_percent"),
            "max_interval_cpu_percent": cpu.get("max_interval_cpu_percent"),
        })
        if cpu.get("sample_status") != "measured":
            reasons.append("clean_profile_summary cpu sample_status is not measured")
        if not positive_number(cpu.get("cpu_sample_count")) or cpu.get("cpu_sample_count") < 2:
            reasons.append("clean_profile_summary cpu_sample_count must be at least 2")
        if cpu.get("avg_process_cpu_percent") is None:
            reasons.append("clean_profile_summary avg_process_cpu_percent is required")
        if cpu.get("max_interval_cpu_percent") is None:
            reasons.append("clean_profile_summary max_interval_cpu_percent is required")

    memory = comparison_summary.get("memory")
    if not isinstance(memory, dict):
        reasons.append("clean_profile_summary memory missing")
    else:
        evidence.update({
            "rss_sample_count": memory.get("rss_sample_count"),
            "max_rss_kb": memory.get("max_rss_kb"),
        })
        if not positive_number(memory.get("rss_sample_count")):
            reasons.append("clean_profile_summary rss_sample_count must be positive")
        if not positive_number(memory.get("max_rss_kb")):
            reasons.append("clean_profile_summary max_rss_kb must be positive")

    evidence["server_log_error_count"] = server_log_error_total
    evidence["status"] = "fail" if reasons else "pass"
    evidence["failure_count"] = len(reasons)
    return evidence, reasons


def operator_task_control_live_evidence(args) -> tuple[dict, list[str]]:
    path = operator_task_control_live_result_artifact_path(args)
    source_path = logical_path(args, OPERATOR_TASK_CONTROL_LIVE_RESULT_NAME)
    evidence = {
        "operator_task_control_live_status": "fail",
        "operator_task_control_live_path": source_path,
        "source_kind": "disposable_live_ai_runtime_queue_probe",
        "direct_command_execution": True,
    }
    reasons = []
    if not path.is_file():
        reasons.append("operator_task_control_live_probe artifact missing")
        evidence["failure_count"] = len(reasons)
        return evidence, reasons
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        evidence.update(
            ai_native_operator_task_control_live_probe.validate_live_result(
                payload,
                max_bytes=args.operator_task_control_live_result_max_bytes,
            )
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        reasons.append(f"operator_task_control_live_probe artifact invalid: {type(exc).__name__}")
    evidence["operator_task_control_live_status"] = "fail" if reasons else "pass"
    evidence["failure_count"] = len(reasons)
    return evidence, reasons


def agent_product_loop_live_evidence(args) -> tuple[dict, list[str]]:
    path = agent_product_loop_live_result_artifact_path(args)
    source_path = logical_path(args, AGENT_PRODUCT_LOOP_LIVE_RESULT_NAME)
    evidence = {
        "agent_product_loop_live_status": "fail",
        "agent_product_loop_live_path": source_path,
        "source_kind": "disposable_live_ai_runtime_agent_product_loop_probe",
        "direct_command_execution": True,
    }
    reasons = []
    if not path.is_file():
        reasons.append("agent_product_loop_live_probe artifact missing")
        evidence["failure_count"] = len(reasons)
        return evidence, reasons
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        evidence.update(
            ai_native_agent_product_loop_live_probe.validate_live_result(
                payload,
                max_bytes=args.agent_product_loop_live_result_max_bytes,
            )
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        reasons.append(f"agent_product_loop_live_probe artifact invalid: {type(exc).__name__}")
    evidence["agent_product_loop_live_status"] = "fail" if reasons else "pass"
    evidence["failure_count"] = len(reasons)
    return evidence, reasons


def compat_import_staging_pilot_evidence(args) -> tuple[dict, list[str]]:
    path = compat_import_staging_pilot_result_artifact_path(args)
    source_path = logical_path(args, COMPAT_IMPORT_STAGING_PILOT_RESULT_NAME)
    evidence = {
        "compat_import_staging_pilot_status": "fail",
        "compat_import_staging_pilot_path": source_path,
        "source_kind": "disposable_live_ai_runtime_compat_import_staging_pilot",
        "direct_command_execution": True,
    }
    reasons = []
    if not path.is_file():
        reasons.append("compat_import_staging_pilot artifact missing")
        evidence["failure_count"] = len(reasons)
        return evidence, reasons
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        evidence.update(
            ai_native_compat_import_staging_pilot.validate_live_result(
                payload,
                max_bytes=args.compat_import_staging_pilot_result_max_bytes,
            )
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        reasons.append(f"compat_import_staging_pilot artifact invalid: {type(exc).__name__}")
    evidence["compat_import_staging_pilot_status"] = "fail" if reasons else "pass"
    evidence["failure_count"] = len(reasons)
    return evidence, reasons


def operator_task_control_command_evidence(args) -> tuple[dict, list[str]]:
    path = operator_task_control_command_result_artifact_path(args)
    source_path = logical_path(args, OPERATOR_TASK_CONTROL_COMMAND_RESULT_NAME)
    evidence = {
        "operator_task_control_command_status": "fail",
        "operator_task_control_command_path": source_path,
        "source_kind": "disposable_live_ai_runtime_command_probe",
        "live_command": "/ai_runtime_operator_task_control",
        "direct_command_execution": True,
    }
    reasons = []
    if not path.is_file():
        reasons.append("operator_task_control_command_probe artifact missing")
        evidence["failure_count"] = len(reasons)
        return evidence, reasons
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        evidence.update(
            ai_native_operator_task_control_command_probe.validate_command_result(
                payload,
                max_bytes=args.operator_task_control_command_result_max_bytes,
            )
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        reasons.append(f"operator_task_control_command_probe artifact invalid: {type(exc).__name__}")
    evidence["operator_task_control_command_status"] = "fail" if reasons else "pass"
    evidence["failure_count"] = len(reasons)
    return evidence, reasons


def build_step_manifest(step: CommandStep, result: CommandRun, max_output_chars: int) -> dict:
    status = "pass" if result.returncode == 0 else "fail"
    payload = {
        "id": step.id,
        "label": step.label,
        "status": status,
        "returncode": result.returncode,
        "duration_seconds": round(result.duration_seconds, 3),
        "command": " ".join(step.manifest_command),
    }
    summary = bounded_summary(result.stdout, result.stderr, max_output_chars)
    if summary:
        payload["output_summary"] = summary
    return payload


def build_manifest(args, command_results: list[tuple[CommandStep, CommandRun]], now_fn=utc_now) -> dict:
    steps = [
        build_step_manifest(step, result, args.max_output_chars)
        for step, result in command_results
    ]
    failure_reasons = []
    for step, result in command_results:
        if result.returncode != 0:
            failure_reasons.append(f"{step.id} exited with status {result.returncode}")

    artifact_paths = {
        "verification_manifest": logical_path(args, MANIFEST_NAME),
    }
    operator_status_step_ran = False
    for step, result in command_results:
        if step.id == "product_profile_hygiene":
            artifact_paths["product_profile_hygiene"] = logical_path(
                args,
                PRODUCT_PROFILE_HYGIENE_NAME,
            )
        if step.id == "branch_benchmark_gate":
            artifact_paths["benchmark_gate_manifest"] = benchmark_gate_artifact(args, result)
            if args.game_profile == "ai_runtime":
                artifact_paths["clean_profile_summary"] = logical_path(
                    args,
                    "clean-profile-benchmark-summary.json",
                )
        if step.id in {"operator_status_live_command", "operator_status_package"}:
            operator_status_step_ran = True
            artifact_paths[step.id] = logical_path(args, operator_status_artifact_name(args))
            artifact_paths["operator_control_report"] = logical_path(args, OPERATOR_CONTROL_REPORT_NAME)
            artifact_paths["operator_action_approval_plan"] = logical_path(
                args,
                OPERATOR_ACTION_APPROVAL_PLAN_NAME,
            )
            artifact_paths["operator_action_approval_receipt"] = logical_path(
                args,
                OPERATOR_ACTION_APPROVAL_RECEIPT_NAME,
            )
            artifact_paths["operator_action_execution_result"] = logical_path(
                args,
                OPERATOR_ACTION_EXECUTION_RESULT_NAME,
            )
        if step.id == "agent_product_loop_live_probe":
            artifact_paths["agent_product_loop_live_result"] = logical_path(
                args,
                AGENT_PRODUCT_LOOP_LIVE_RESULT_NAME,
            )
        if step.id == "compat_import_staging_pilot":
            artifact_paths["compat_import_staging_pilot_result"] = logical_path(
                args,
                COMPAT_IMPORT_STAGING_PILOT_RESULT_NAME,
            )
        if step.id == "operator_task_control_live_probe":
            artifact_paths["operator_task_control_live_result"] = logical_path(
                args,
                OPERATOR_TASK_CONTROL_LIVE_RESULT_NAME,
            )
        if step.id == "operator_task_control_command_probe":
            artifact_paths["operator_task_control_command_result"] = logical_path(
                args,
                OPERATOR_TASK_CONTROL_COMMAND_RESULT_NAME,
            )

    product_profile = None
    if any(step.id == "product_profile_hygiene" for step, _ in command_results):
        product_profile, product_profile_failures = product_profile_evidence(args)
        failure_reasons.extend(product_profile_failures)

    clean_profile = None
    if args.game_profile == "ai_runtime" and any(
        step.id == "branch_benchmark_gate" for step, _ in command_results
    ):
        clean_profile, clean_profile_failures = clean_profile_workload_evidence(args)
        failure_reasons.extend(clean_profile_failures)

    operator_evidence = None
    if operator_status_step_ran:
        operator_evidence, operator_failures = operator_status_evidence(args)
        failure_reasons.extend(operator_failures)

    agent_product_loop_live = None
    if any(step.id == "agent_product_loop_live_probe" for step, _ in command_results):
        agent_product_loop_live, agent_product_loop_failures = agent_product_loop_live_evidence(args)
        failure_reasons.extend(agent_product_loop_failures)

    compat_import_staging_pilot = None
    if any(step.id == "compat_import_staging_pilot" for step, _ in command_results):
        compat_import_staging_pilot, compat_import_failures = compat_import_staging_pilot_evidence(args)
        failure_reasons.extend(compat_import_failures)

    operator_task_control_live = None
    if any(step.id == "operator_task_control_live_probe" for step, _ in command_results):
        operator_task_control_live, live_failures = operator_task_control_live_evidence(args)
        failure_reasons.extend(live_failures)

    operator_task_control_command = None
    if any(step.id == "operator_task_control_command_probe" for step, _ in command_results):
        operator_task_control_command, command_failures = operator_task_control_command_evidence(args)
        failure_reasons.extend(command_failures)

    manifest = {
        "schema_version": 1,
        "generated_at": now_fn(),
        "hardware_class": args.hardware_class,
        "luanti_commit": args.luanti_commit,
        "game_profile": args.game_profile,
        "logical_run_dir": logical_run_dir(args),
        "overall_status": "fail" if failure_reasons else "pass",
        "steps": steps,
        "artifact_paths": artifact_paths,
        "failure_reasons": failure_reasons,
        "run_context": {
            "mode": "ai-runtime-pre-pr-verification+clean-profile"
            if args.game_profile == "ai_runtime"
            else "ai-runtime-pre-pr-verification",
            "requires_private_world": False,
            "requires_private_assets": False,
            "requires_live_pi": False,
            "requires_model_network": False,
        },
        "notes": [
            "Runs local utility contracts, the branch benchmark gate, and focused AI runtime unit smoke.",
            "Generated artifacts remain local-only and ignored by Git under local/benchmarks.",
            "Use the low-power lane only after backup-first readiness is confirmed.",
            "Operator status uses a disposable ai_runtime live command probe by default.",
            "First-party agent product-loop proof uses a disposable ai_runtime world and synthetic public nodes.",
            "Compatibility import pilot runs public-safe inventory, dry-run, reviewed staging apply, rollback, and refusal gates in a disposable ai_runtime world.",
        ]
        + (
            [
                "Default clean-profile verification records a disposable ai_runtime server capture.",
            ]
            if args.game_profile == "ai_runtime"
            else []
        ),
    }
    if product_profile is not None:
        manifest["product_profile_evidence"] = product_profile
    if clean_profile is not None:
        manifest["clean_profile_evidence"] = clean_profile
    if operator_evidence is not None:
        manifest["operator_status_evidence"] = operator_evidence
    if agent_product_loop_live is not None:
        manifest["agent_product_loop_live_evidence"] = agent_product_loop_live
    if compat_import_staging_pilot is not None:
        manifest["compat_import_staging_pilot_evidence"] = compat_import_staging_pilot
    if operator_task_control_live is not None:
        manifest["operator_task_control_live_evidence"] = operator_task_control_live
    if operator_task_control_command is not None:
        manifest["operator_task_control_command_evidence"] = operator_task_control_command
    return manifest


def run_harness(args, runner=run_subprocess, now_fn=utc_now) -> tuple[int, Path, dict]:
    command_results = []
    for step in build_steps(args):
        result = runner(step)
        command_results.append((step, result))
        if args.fail_fast and result.returncode != 0:
            break

    manifest = build_manifest(args, command_results, now_fn=now_fn)
    manifest_path = physical_run_dir(args) / MANIFEST_NAME
    write_json(manifest_path, manifest)
    return (0 if manifest["overall_status"] == "pass" else 1), manifest_path, manifest


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Run local AI-native runtime pre-PR verification and write a bounded manifest."
    )
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_OUTPUT_ROOT),
        help="Local benchmark evidence root. Default: local/benchmarks.",
    )
    parser.add_argument(
        "--hardware-class",
        choices=("local-mac", "low-power-server"),
        default="local-mac",
        help="Hardware lane for verification evidence.",
    )
    parser.add_argument(
        "--date",
        default=ai_native_benchmark_capture.utc_date(),
        help="Run date segment for local evidence.",
    )
    parser.add_argument(
        "--luanti-commit",
        default=ai_native_benchmark_capture.default_commit(),
        help="Commit or label for the branch under verification.",
    )
    parser.add_argument(
        "--server-bin",
        default="bin/luantiserver",
        help="Server binary to use for AI runtime unit checks.",
    )
    parser.add_argument(
        "--game-profile",
        choices=("sample-synthetic", "ai_runtime"),
        default="ai_runtime",
        help="Optional clean server profile to launch through the benchmark gate.",
    )
    parser.add_argument(
        "--profile-sample-seconds",
        type=float,
        default=3.0,
        help="Seconds to keep the disposable ai_runtime server alive after startup.",
    )
    parser.add_argument(
        "--profile-startup-timeout",
        type=float,
        default=15.0,
        help="Seconds to wait for the ai_runtime server listening log line.",
    )
    parser.add_argument(
        "--profile-port",
        type=int,
        help="Optional UDP port for the disposable ai_runtime profile launch.",
    )
    parser.add_argument(
        "--headless-player-command",
        help=(
            "Optional command template for disposable synthetic players during "
            "clean-profile capture. Supported placeholders: {host}, {port}, "
            "{name}, {server_log}, {duration_seconds}."
        ),
    )
    parser.add_argument(
        "--headless-player-count",
        type=int,
        default=2,
        help="Synthetic player command instances to launch when --headless-player-command is supplied.",
    )
    parser.add_argument(
        "--headless-player-timeout",
        type=float,
        default=2.0,
        help="Seconds to wait while cleaning up each synthetic player process.",
    )
    parser.add_argument(
        "--require-headless-player-probe",
        action="store_true",
        help=(
            "Fail clean-profile verification unless the benchmark summary contains "
            "a measured headless-client load probe with join-latency evidence."
        ),
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python executable for utility checks.",
    )
    parser.add_argument(
        "--include-full-unittests",
        action="store_true",
        help="Also run the full Luanti unit test suite after focused AI runtime checks.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop after the first failed command while still writing a manifest.",
    )
    parser.add_argument(
        "--max-output-chars",
        type=int,
        default=1200,
        help="Maximum sanitized output summary characters to keep per step.",
    )
    parser.add_argument(
        "--confirm-low-power-backup",
        action="store_true",
        help="Pass backup-first confirmation through to low-power-server benchmark gates.",
    )
    parser.add_argument(
        "--operator-status-max-bytes",
        type=int,
        default=24000,
        help="Maximum byte budget for the retained operator status artifact.",
    )
    parser.add_argument(
        "--operator-status-source",
        choices=("live", "surrogate"),
        default="live",
        help=(
            "Capture operator status from a disposable live ai_runtime server by default. "
            "Use surrogate to call the Python package generator explicitly."
        ),
    )
    parser.add_argument(
        "--operator-status-live-timeout",
        type=float,
        default=20.0,
        help="Seconds to wait for the disposable live operator-status probe.",
    )
    parser.add_argument(
        "--operator-control-report-max-bytes",
        type=int,
        default=16000,
        help="Maximum byte budget for the derived operator-control report artifact.",
    )
    parser.add_argument(
        "--operator-action-approval-plan-max-bytes",
        type=int,
        default=20000,
        help="Maximum byte budget for the derived operator action approval-plan artifact.",
    )
    parser.add_argument(
        "--operator-action-approval-receipt-max-bytes",
        type=int,
        default=20000,
        help="Maximum byte budget for the derived operator action approval receipt artifact.",
    )
    parser.add_argument(
        "--operator-action-execution-result-max-bytes",
        type=int,
        default=20000,
        help="Maximum byte budget for the derived operator action execution result artifact.",
    )
    parser.add_argument(
        "--agent-product-loop-live-result-max-bytes",
        type=int,
        default=26000,
        help="Maximum byte budget for the first-party agent product-loop live probe artifact.",
    )
    parser.add_argument(
        "--agent-product-loop-live-timeout",
        type=float,
        default=20.0,
        help="Seconds to wait for the disposable first-party agent product-loop live probe.",
    )
    parser.add_argument(
        "--compat-import-staging-pilot-result-max-bytes",
        type=int,
        default=30000,
        help="Maximum byte budget for the compatibility import staging pilot artifact.",
    )
    parser.add_argument(
        "--compat-import-staging-pilot-timeout",
        type=float,
        default=20.0,
        help="Seconds to wait for the disposable compatibility import staging pilot.",
    )
    parser.add_argument(
        "--operator-taREDACTED_KEY_FIXTURE",
        type=int,
        default=22000,
        help="Maximum byte budget for the operator task-control live probe artifact.",
    )
    parser.add_argument(
        "--operator-taREDACTED_KEY_FIXTURE",
        type=float,
        default=20.0,
        help="Seconds to wait for the disposable operator task-control live probe.",
    )
    parser.add_argument(
        "--operator-taREDACTED_KEY_FIXTURE",
        type=int,
        default=22000,
        help="Maximum byte budget for the operator task-control command result artifact.",
    )
    parser.add_argument(
        "--operator-taREDACTED_KEY_FIXTURE",
        type=float,
        default=20.0,
        help="Seconds to wait for the disposable operator task-control command probe.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    status, _, manifest = run_harness(args)
    print(manifest["artifact_paths"]["verification_manifest"])
    return status


if __name__ == "__main__":
    raise SystemExit(main())
