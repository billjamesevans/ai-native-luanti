#!/usr/bin/env python3
"""Capture /ai_runtime_operator_status from a disposable live ai_runtime server."""

from __future__ import annotations

import argparse
import json
import shutil
import socket
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIVE_ARTIFACT_NAME = "ai-runtime-operator-status-live.json"
LIVE_RESULT_NAME = "ai-runtime-operator-status-live-result.json"
PROBE_MOD_NAME = "ai_operator_status_probe"


def lua_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def reserve_udp_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


def resolve_path(root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return root / path


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
    (mod_dir / "mod.conf").write_text(
        f"name = {PROBE_MOD_NAME}\n",
        encoding="utf-8",
    )
    command_params = f"generated_at={generated_at} max_bytes={max_bytes}"
    (mod_dir / "init.lua").write_text(
        "\n".join([
            "local output_path = core.get_worldpath() .. " + lua_string("/" + LIVE_ARTIFACT_NAME),
            "local result_path = core.get_worldpath() .. " + lua_string("/" + LIVE_RESULT_NAME),
            "",
            "local function write_result(status, reason)",
            "  core.safe_file_write(result_path, core.write_json({",
            "    status = status,",
            "    reason = reason,",
            "    command = \"/ai_runtime_operator_status\",",
            "    execution_path = \"disposable_worldmod_registered_chatcommand\",",
            "  }))",
            "end",
            "",
            "core.register_on_mods_loaded(function()",
            "  local command = core.registered_chatcommands",
            "    and core.registered_chatcommands.ai_runtime_operator_status",
            "  if type(command) ~= \"table\" or type(command.func) ~= \"function\" then",
            "    write_result(\"fail\", \"operator status command missing\")",
            "    core.request_shutdown(\"operator status probe failed\", false, 0)",
            "    return",
            "  end",
            "  local ran, command_ok, message = pcall(command.func, \"operator_status_probe\", "
            + lua_string(command_params)
            + ")",
            "  if not ran then",
            "    write_result(\"fail\", \"operator status command raised error\")",
            "    core.request_shutdown(\"operator status probe failed\", false, 0)",
            "    return",
            "  end",
            "  if command_ok ~= true or type(message) ~= \"string\" then",
            "    write_result(\"fail\", \"operator status command returned failure\")",
            "    core.request_shutdown(\"operator status probe failed\", false, 0)",
            "    return",
            "  end",
            "  if not core.safe_file_write(output_path, message) then",
            "    write_result(\"fail\", \"operator status artifact write failed\")",
            "    core.request_shutdown(\"operator status probe failed\", false, 0)",
            "    return",
            "  end",
            "  write_result(\"pass\", \"operator status command captured\")",
            "  core.request_shutdown(\"operator status probe complete\", false, 0)",
            "end)",
            "",
        ]),
        encoding="utf-8",
    )


def read_result(world_dir: Path) -> dict:
    result_path = world_dir / LIVE_RESULT_NAME
    if not result_path.is_file():
        return {"status": "fail", "reason": "probe result missing"}
    try:
        return json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "fail", "reason": f"probe result unreadable: {type(exc).__name__}"}


def run_probe(args) -> int:
    root = resolve_path(Path.cwd(), args.root).resolve()
    server_bin = resolve_path(root, args.server_bin)
    output = resolve_path(root, args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    world_dir = output.parent / "operator-status-live-world"
    write_probe_world(world_dir, args.generated_at, args.max_bytes)

    port = args.port or reserve_udp_port()
    log_path = world_dir / "debug.log"
    config_path = world_dir / "probe.conf"
    config_path.write_text(
        "\n".join([
            "server_name = AI Native Operator Status Probe",
            "name = operator_status_probe",
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
        print("operator status live command timed out", file=sys.stderr)
        return 1
    if completed.returncode != 0:
        print("operator status live server exited with non-zero status", file=sys.stderr)
        if completed.stderr.strip():
            print(completed.stderr.strip()[-1200:], file=sys.stderr)
        return 1

    result = read_result(world_dir)
    if result.get("status") != "pass":
        reason = result.get("reason", "unknown")
        print(f"operator status live command failed: {reason}", file=sys.stderr)
        return 1

    world_artifact = world_dir / LIVE_ARTIFACT_NAME
    if not world_artifact.is_file():
        print("operator status live artifact missing", file=sys.stderr)
        return 1
    shutil.copyfile(world_artifact, output)
    print("operator status live command captured")
    return 0


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Capture /ai_runtime_operator_status from a disposable ai_runtime server."
    )
    parser.add_argument("--root", default=".", help="Luanti source checkout root.")
    parser.add_argument("--server-bin", default="bin/luantiserver", help="Server binary to launch.")
    parser.add_argument("--output", required=True, help="Output JSON artifact path.")
    parser.add_argument("--generated-at", required=True, help="generated_at value for the command.")
    parser.add_argument("--max-bytes", type=int, default=24000, help="Command output byte budget.")
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="Seconds to wait for probe shutdown.",
    )
    parser.add_argument("--port", type=int, help="Optional UDP port for the disposable server.")
    return parser.parse_args(argv)


def main(argv=None):
    return run_probe(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
