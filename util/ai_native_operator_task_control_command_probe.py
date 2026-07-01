#!/usr/bin/env python3
"""Probe /ai_runtime_operator_task_control in a disposable live ai_runtime world."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ai_native_operator_task_control_live_probe import (  # noqa: E402
    DEFAULT_MAX_BYTES,
    PRIVATE_PATTERNS,
    lua_long_string,
    lua_string,
    reserve_udp_port,
    resolve_path,
    sample_live_receipt,
)


ROOT = Path(__file__).resolve().parents[1]
COMMAND_ARTIFACT_NAME = "ai-runtime-operator-task-control-command-result.json"
COMMAND_PROBE_STATUS_NAME = "ai-runtime-operator-task-control-command-probe-result.json"
PROBE_MOD_NAME = "ai_operator_task_control_command_probe"


def write_probe_world(world_dir: Path, generated_at: str, max_bytes: int) -> None:
    if world_dir.exists():
        shutil.rmtree(world_dir)
    mod_dir = world_dir / "worldmods" / PROBE_MOD_NAME
    mod_dir.mkdir(parents=True, exist_ok=True)
    (world_dir / "world.mt").write_text(
        "\n".join([
            "gameid = ai_runtime",
            "backend = sqlite3",
            "player_backend = sqlite3",
            "auth_backend = sqlite3",
            "",
        ]),
        encoding="utf-8",
    )
    (mod_dir / "mod.conf").write_text(f"name = {PROBE_MOD_NAME}\n", encoding="utf-8")
    receipt_json = json.dumps(sample_live_receipt(generated_at), sort_keys=True)
    (mod_dir / "init.lua").write_text(
        "\n".join([
            "local output_path = core.get_worldpath() .. " + lua_string("/" + COMMAND_ARTIFACT_NAME),
            "local result_path = core.get_worldpath() .. " + lua_string("/" + COMMAND_PROBE_STATUS_NAME),
            "local generated_at = " + lua_string(generated_at),
            f"local max_bytes = {int(max_bytes)}",
            "local receipt = core.parse_json(" + lua_long_string(receipt_json) + ")",
            "",
            "local function write_result(status, reason)",
            "  core.safe_file_write(result_path, core.write_json({",
            "    status = status,",
            "    reason = reason,",
            "    command = \"/ai_runtime_operator_task_control\",",
            "    execution_path = \"disposable_worldmod_registered_chatcommand\",",
            "  }))",
            "end",
            "",
            "local function seed_task(task_id, status, retry_count)",
            "  core.registered_ai_tasks[task_id] = {",
            "    task_id = task_id,",
            "    agent_id = \"operator_task_control:command_probe\",",
            "    owner = \"admin\",",
            "    label = \"operator task-control command probe\",",
            "    status = status,",
            "    created_at = 0,",
            "    updated_at = 0,",
            "    budget = {},",
            "    progress = { current = status == \"running\" and 1 or 0, total = 2 },",
            "    retry_count = retry_count or 0,",
            "    last_result = { ok = status ~= \"blocked\", status = status, reason = \"probe_seeded\" },",
            "    steps = {",
            "      function() return { ok = false, status = \"blocked\", reason = \"probe_blocked\" } end,",
            "      function() return { ok = true, status = \"success\", changed = 0 } end,",
            "    },",
            "  }",
            "end",
            "",
            "local function seed_tasks()",
            "  seed_task(\"task:live-cancel\", \"running\", 0)",
            "  seed_task(\"task:live-retry\", \"blocked\", 0)",
            "  seed_task(\"task:live-denied\", \"blocked\", 0)",
            "end",
            "",
            "core.register_on_mods_loaded(function()",
            "  local command = core.registered_chatcommands.ai_runtime_operator_task_control",
            "  if type(command) ~= \"table\" or type(command.func) ~= \"function\" then",
            "    write_result(\"fail\", \"operator task-control command missing\")",
            "    core.request_shutdown(\"task-control command probe failed\", false, 0)",
            "    return",
            "  end",
            "  seed_tasks()",
            "  local params = \"generated_at=\" .. generated_at",
            "    .. \" max_bytes=\" .. tostring(max_bytes)",
            "    .. \" receipt_json=\" .. core.write_json(receipt)",
            "  local ran, command_ok, message = pcall(command.func, \"admin\", params)",
            "  if not ran then",
            "    write_result(\"fail\", \"operator task-control command raised error\")",
            "    core.request_shutdown(\"task-control command probe failed\", false, 0)",
            "    return",
            "  end",
            "  if command_ok ~= true or type(message) ~= \"string\" then",
            "    write_result(\"fail\", \"operator task-control command returned failure\")",
            "    core.request_shutdown(\"task-control command probe failed\", false, 0)",
            "    return",
            "  end",
            "  local payload = core.parse_json(message)",
            "  if type(payload) ~= \"table\"",
            "      or payload.command_result_kind ~= \"ai_native_operator_task_control_command_result\" then",
            "    write_result(\"fail\", \"operator task-control command result invalid\")",
            "    core.request_shutdown(\"task-control command probe failed\", false, 0)",
            "    return",
            "  end",
            "  if payload.runtime_context and payload.runtime_context.world_mutation_performed ~= false then",
            "    write_result(\"fail\", \"operator task-control command mutated world\")",
            "    core.request_shutdown(\"task-control command probe failed\", false, 0)",
            "    return",
            "  end",
            "  if not core.safe_file_write(output_path, message) then",
            "    write_result(\"fail\", \"operator task-control command artifact write failed\")",
            "    core.request_shutdown(\"task-control command probe failed\", false, 0)",
            "    return",
            "  end",
            "  write_result(\"pass\", \"receipt-gated task-control command captured\")",
            "  core.request_shutdown(\"task-control command probe complete\", false, 0)",
            "end)",
            "",
        ]),
        encoding="utf-8",
    )


def read_result(world_dir: Path) -> dict:
    result_path = world_dir / COMMAND_PROBE_STATUS_NAME
    if not result_path.is_file():
        return {"status": "fail", "reason": "probe result missing"}
    try:
        return json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "fail", "reason": f"probe result unreadable: {type(exc).__name__}"}


def _artifact_has_private_content(payload: dict) -> bool:
    raw = json.dumps(payload, sort_keys=True)
    return any(pattern.search(raw) for pattern in PRIVATE_PATTERNS)


def validate_command_result(payload: dict, max_bytes: int = DEFAULT_MAX_BYTES) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("operator task-control command result must be an object")
    if payload.get("command_result_kind") != "ai_native_operator_task_control_command_result":
        raise ValueError("operator task-control command result kind is invalid")
    if _artifact_has_private_content(payload):
        raise ValueError("operator task-control command result contains private content")

    runtime_context = payload.get("runtime_context")
    if not isinstance(runtime_context, dict):
        raise ValueError("operator task-control command runtime_context missing or invalid")
    if runtime_context.get("game_profile") != "ai_runtime":
        raise ValueError("operator task-control command game_profile is invalid")
    if runtime_context.get("command") != "/ai_runtime_operator_task_control":
        raise ValueError("operator task-control command name is invalid")
    if runtime_context.get("world_mutation_performed") is not False:
        raise ValueError("operator task-control command result performed world mutation")

    actions = payload.get("operator_actions")
    if not isinstance(actions, dict):
        raise ValueError("operator task-control command operator_actions missing or invalid")
    if actions.get("mode") != "receipt_gated_task_cancel_retry":
        raise ValueError("operator task-control command mode is invalid")
    if actions.get("mutation_scope") != "live_task_queue":
        raise ValueError("operator task-control command mutation_scope is invalid")
    if actions.get("world_mutation_performed") is not False:
        raise ValueError("operator task-control command result performed world mutation")

    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    for field in (
        "public_safe_output",
        "receipt_required",
        "receipt_gated",
        "task_control_only",
        "task_queue_mutation_only",
        "no_world_mutation",
        "no_rollback_execution",
        "no_import_promotion_execution",
        "no_structure_apply",
        "no_raw_assets",
        "no_provider_prompts",
        "no_family_world_coordinates",
    ):
        if safety.get(field) is not True:
            raise ValueError(f"operator task-control command safety {field} is not true")
    if safety.get("world_mutation_performed") is not False:
        raise ValueError("operator task-control command result performed world mutation")

    bounds = payload.get("bounds") if isinstance(payload.get("bounds"), dict) else {}
    output_bytes = bounds.get("output_bytes")
    declared_max = bounds.get("max_bytes", max_bytes)
    if not isinstance(output_bytes, int) or not isinstance(declared_max, int):
        raise ValueError("operator task-control command bounds are invalid")
    if output_bytes > declared_max or output_bytes > max_bytes:
        raise ValueError("operator task-control command output exceeds max bytes")

    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    for field in ("decisions_total", "executed_total", "rejected_total"):
        if not isinstance(summary.get(field), int):
            raise ValueError(f"operator task-control command summary {field} is invalid")
    if summary["decisions_total"] != 5:
        raise ValueError("operator task-control command decision count is invalid")
    if summary["executed_total"] != 2:
        raise ValueError("operator task-control command cancel/retry execution count is invalid")
    if summary["rejected_total"] != 3:
        raise ValueError("operator task-control command rejection count is invalid")

    operations = set()
    rejection_reasons = set()
    for item in payload.get("results") or []:
        if not isinstance(item, dict):
            continue
        if item.get("status") == "executed" and isinstance(item.get("operation"), str):
            operations.add(item["operation"])
        if item.get("status") == "rejected" and isinstance(item.get("reason"), str):
            rejection_reasons.add(item["reason"])
    if not {"cancel", "retry"}.issubset(operations):
        raise ValueError("operator task-control command did not execute cancel and retry")
    if "unsupported_target_kind" not in rejection_reasons:
        raise ValueError("operator task-control command did not reject unsupported targets")

    return {
        "operator_task_control_command_status": "pass",
        "operator_task_control_command_output_bytes": output_bytes,
        "operator_task_control_command_items": summary["decisions_total"],
        "operator_task_control_command_executed": summary["executed_total"],
        "operator_task_control_command_rejected": summary["rejected_total"],
        "operator_task_control_command_world_mutation": False,
        "live_command": "/ai_runtime_operator_task_control",
        "source_kind": "disposable_live_ai_runtime_command_probe",
        "direct_command_execution": True,
    }


def run_probe(args) -> int:
    root = resolve_path(Path.cwd(), args.root).resolve()
    server_bin = resolve_path(root, args.server_bin)
    output = resolve_path(root, args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    world_dir = output.parent / "operator-task-control-command-world"
    write_probe_world(world_dir, args.generated_at, args.max_bytes)

    port = args.port or reserve_udp_port()
    log_path = world_dir / "debug.log"
    config_path = world_dir / "probe.conf"
    config_path.write_text(
        "\n".join([
            "server_name = AI Native Operator Task Control Command Probe",
            "name = operator_task_control_command_probe",
            "secure.enable_security = true",
            "creative_mode = false",
            "enable_damage = false",
            "",
        ]),
        encoding="utf-8",
    )
    command = [
        str(server_bin),
        "--world",
        str(world_dir),
        "--gameid",
        "ai_runtime",
        "--port",
        str(port),
        "--config",
        str(config_path),
        "--logfile",
        str(log_path),
        "--color",
        "never",
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
            timeout=args.timeout,
        )
    except subprocess.TimeoutExpired:
        print("operator task-control command probe timed out", file=sys.stderr)
        return 1
    if completed.returncode != 0:
        print("operator task-control command server exited with non-zero status", file=sys.stderr)
        if completed.stderr.strip():
            print(completed.stderr.strip()[-1200:], file=sys.stderr)
        return 1

    result = read_result(world_dir)
    if result.get("status") != "pass":
        reason = result.get("reason", "unknown")
        print(f"operator task-control command probe failed: {reason}", file=sys.stderr)
        return 1

    world_artifact = world_dir / COMMAND_ARTIFACT_NAME
    if not world_artifact.is_file():
        print("operator task-control command artifact missing", file=sys.stderr)
        return 1
    try:
        payload = json.loads(world_artifact.read_text(encoding="utf-8"))
        validate_command_result(payload, max_bytes=args.max_bytes)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"operator task-control command artifact invalid: {type(exc).__name__}", file=sys.stderr)
        return 1
    shutil.copyfile(world_artifact, output)
    print("operator task-control command probe captured")
    return 0


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Capture /ai_runtime_operator_task_control from a disposable ai_runtime server."
    )
    parser.add_argument("--root", default=".", help="Luanti source checkout root.")
    parser.add_argument("--server-bin", default="bin/luantiserver", help="Server binary to launch.")
    parser.add_argument("--output", required=True, help="Output JSON artifact path.")
    parser.add_argument("--generated-at", required=True, help="generated_at value for the command.")
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES, help="Output byte budget.")
    parser.add_argument("--timeout", type=float, default=20.0, help="Seconds to wait for probe shutdown.")
    parser.add_argument("--port", type=int, help="Optional UDP port for the disposable server.")
    return parser.parse_args(argv)


def main(argv=None):
    return run_probe(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
