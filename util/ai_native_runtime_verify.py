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
import ai_native_operator_control_report


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = ROOT / "local" / "benchmarks"
MANIFEST_NAME = "ai-runtime-verification-manifest.json"
OPERATOR_STATUS_NAME = "ai-runtime-operator-status.json"
OPERATOR_STATUS_LIVE_NAME = "ai-runtime-operator-status-live.json"
OPERATOR_CONTROL_REPORT_NAME = "ai-runtime-operator-control-report.json"
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
    (re.compile(r"sk-[A-Za-z0-9_-]{20,}"), "<secret>"),
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


def operator_control_report_artifact_path(args) -> Path:
    return physical_run_dir(args) / OPERATOR_CONTROL_REPORT_NAME


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
        evidence.update({
            "operator_control_report_status": "pass",
            "operator_control_report_output_bytes": report["bounds"]["output_bytes"],
            "operator_control_report_items": report["summary"]["items_total"],
        })
    except (OSError, ValueError) as exc:
        reasons.append(f"{step_id} operator control report failed: {type(exc).__name__}")

    evidence.update({
        "status": "fail" if reasons else "pass",
        "package_status": sanitize_text(str(payload.get("status", "unknown"))),
        "output_bytes": output_bytes,
        "max_bytes": max_bytes,
        "truncated": bounds.get("truncated") is True,
        "required_sections_present": not missing_sections,
        "private_scan_status": "fail" if artifact_has_private_content(raw_payload) else "pass",
        "failure_count": len(reasons),
    })
    evidence.update(control_evidence)
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

    operator_evidence = None
    if operator_status_step_ran:
        operator_evidence, operator_failures = operator_status_evidence(args)
        failure_reasons.extend(operator_failures)

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
        ]
        + (
            [
                "Opt-in clean-profile verification records a disposable ai_runtime server capture.",
            ]
            if args.game_profile == "ai_runtime"
            else []
        ),
    }
    if operator_evidence is not None:
        manifest["operator_status_evidence"] = operator_evidence
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
        default="sample-synthetic",
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
        default=1,
        help="Synthetic player command instances to launch when --headless-player-command is supplied.",
    )
    parser.add_argument(
        "--headless-player-timeout",
        type=float,
        default=2.0,
        help="Seconds to wait while cleaning up each synthetic player process.",
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
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    status, _, manifest = run_harness(args)
    print(manifest["artifact_paths"]["verification_manifest"])
    return status


if __name__ == "__main__":
    raise SystemExit(main())
