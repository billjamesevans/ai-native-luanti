#!/usr/bin/env python3
"""Serve OpenRealm Studio with a public-safe live runtime status API."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
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


def quality_gate_status() -> dict[str, Any]:
    quality = read_json(env_path("OPENREALM_QUALITY_GATE", "/opt/ai-native-luanti/memory/ai-agent-quality-gate.json")) or {}
    prompt_eval = read_json(env_path("OPENREALM_PROMPT_EVAL", "/opt/ai-native-luanti/memory/ai-agent-prompt-eval-live-latest.json")) or {}
    request_gate = read_json(env_path("OPENREALM_REQUEST_LOG_GATE", "/opt/ai-native-luanti/memory/ai-agent-request-response-log-gate.json")) or {}
    quality_summary = quality.get("summary") if isinstance(quality.get("summary"), dict) else {}
    prompt_summary = prompt_eval.get("summary") if isinstance(prompt_eval.get("summary"), dict) else {}
    request_summary = request_gate.get("summary") if isinstance(request_gate.get("summary"), dict) else {}
    return {
        "status": quality.get("status"),
        "generated_at": quality.get("generated_at"),
        "live_prompt_eval_status": quality_summary.get("live_prompt_eval_status") or prompt_eval.get("status"),
        "compat_import_staging_pilot_status": quality_summary.get("compat_import_staging_pilot_status"),
        "violations_total": quality_summary.get("violations_total"),
        "attention_total": quality_summary.get("attention_total"),
        "prompt_eval_passed": prompt_summary.get("passed_cases") or prompt_eval.get("passed_cases"),
        "prompt_eval_total": prompt_summary.get("total_cases") or prompt_eval.get("total_cases"),
        "request_log_gate_status": request_gate.get("status"),
        "request_log_checked_cases": request_summary.get("checked_cases"),
        "request_log_violations": request_summary.get("violations_total"),
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
    if not path.exists():
        return {
            "present": False,
            "total_entries": 0,
            "successes": 0,
            "failures": 0,
            "timeouts": 0,
            "latest": None,
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
                latest = summarize_adapter_record(record)
    except OSError:
        return {
            "present": False,
            "total_entries": total,
            "successes": successes,
            "failures": failures,
            "timeouts": timeouts,
            "latest": latest,
        }
    return {
        "present": True,
        "total_entries": total,
        "successes": successes,
        "failures": failures,
        "timeouts": timeouts,
        "latest": latest,
    }


def build_status_payload() -> dict[str, Any]:
    services = service_status()
    return {
        "schema_version": 1,
        "generated_at": utc_now(),
        "public_safe": True,
        "live_bridge": True,
        "direct_world_mutation_by_ai": False,
        "services": services,
        "services_all_active": all(service["active"] for service in services.values()),
        "fork": fork_status(),
        "quality_gate": quality_gate_status(),
        "adapter_log": adapter_log_status(),
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
