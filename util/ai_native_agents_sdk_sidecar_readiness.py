#!/usr/bin/env python3
"""Probe the Agents SDK sidecar without requiring provider credentials."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
BRIDGE_DIR = ROOT / "tools" / "agents_sdk_model_adapter"
AGENT = BRIDGE_DIR / "agent.py"
MAIN = BRIDGE_DIR / "main.py"

REPORT_KIND = "ai_native_agents_sdk_sidecar_readiness"
FORBIDDEN_RESPONSE_KEYS = {
    "raw_provider_request",
    "raw_provider_response",
    "provider_headers",
    "credentials",
    "provider_credentials",
    "private_payload",
    "private_prompt",
    "asset_payload",
}


def _loopback_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    return parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _load_agent_module():
    spec = importlib.util.spec_from_file_location("ai_native_agents_sdk_agent", AGENT)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load Agents SDK sidecar agent module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _http_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout_seconds: float,
) -> tuple[int, dict[str, Any]]:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            data = response.read().decode("utf-8")
            return response.status, json.loads(data)
    except urllib.error.HTTPError as exc:
        data = exc.read().decode("utf-8")
        return exc.code, json.loads(data)


def _public_response_summary(response: dict[str, Any]) -> dict[str, Any]:
    nested = response.get("response") if isinstance(response.get("response"), dict) else {}
    message = str(response.get("message") or "")
    return {
        "ok": response.get("ok") is True,
        "response_kind": response.get("response_kind"),
        "adapter_contract": response.get("adapter_contract"),
        "adapter_name": response.get("adapter_name"),
        "reason": response.get("reason"),
        "message_bytes": len(message.encode("utf-8")),
        "agentic_execution": nested.get("agentic_execution"),
        "web_search_available": nested.get("web_search_available"),
        "web_search_used": nested.get("web_search_used"),
        "tools_enabled": nested.get("tools_enabled") if isinstance(nested.get("tools_enabled"), list) else [],
        "tool_powers": nested.get("tool_powers") if isinstance(nested.get("tool_powers"), list) else [],
        "tool_decision_source": nested.get("tool_decision_source"),
        "selected_option_id": nested.get("selected_option_id"),
        "required_tool_calls": (
            nested.get("required_tool_calls")
            if isinstance(nested.get("required_tool_calls"), list)
            else []
        ),
        "missing_required_tool_calls": (
            nested.get("missing_required_tool_calls")
            if isinstance(nested.get("missing_required_tool_calls"), list)
            else []
        ),
        "required_tool_calls_satisfied": nested.get("required_tool_calls_satisfied"),
        "tool_trace_names": [
            item.get("tool_name")
            for item in nested.get("tool_trace", [])
            if isinstance(item, dict) and isinstance(item.get("tool_name"), str)
        ],
        "world_mutation_authority": nested.get("world_mutation_authority"),
    }


def _tool_powers_safe(tool_powers: Any) -> bool:
    if not isinstance(tool_powers, list) or not tool_powers:
        return False
    names = {
        power.get("name")
        for power in tool_powers
        if isinstance(power, dict)
    }
    required = {
        "WebSearchTool",
        "summarize_runtime_capabilities",
        "classify_world_action",
        "recall_build_prompt_memory",
        "recommend_build_option",
    }
    if not required.issubset(names):
        return False
    for power in tool_powers:
        if not isinstance(power, dict):
            return False
        if power.get("direct_world_mutation") is not False:
            return False
    return True


def _contains_forbidden_keys(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN_RESPONSE_KEYS:
                return True
            if _contains_forbidden_keys(child):
                return True
    elif isinstance(value, list):
        return any(_contains_forbidden_keys(child) for child in value)
    return False


def _base_report(
    mode: str,
    endpoint: str,
    *,
    require_live_agent: bool = False,
    require_build_planning_tools: bool = False,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "report_kind": REPORT_KIND,
        "mode": mode,
        "endpoint": endpoint,
        "loopback_endpoint": _loopback_url(endpoint),
        "live_agent_required": require_live_agent,
        "build_planning_tools_required": require_build_planning_tools,
        "status": "fail",
        "checks": {
            "files_present": AGENT.exists() and MAIN.exists(),
            "loopback_endpoint": _loopback_url(endpoint),
            "offline_smoke": False,
            "health_endpoint": False,
            "model_adapter_endpoint": False,
            "no_provider_credentials_required": False,
            "provider_credentials_present": False,
            "agents_sdk_available": False,
            "web_search_tool_available": False,
            "live_agent_execution": False,
            "live_web_lookup_available": False,
            "bounded_response": False,
            "no_forbidden_payload_keys": False,
            "tool_powers_declared": False,
            "no_direct_world_mutation_tools": False,
            "required_tool_calls_satisfied": False,
            "public_safe_response": False,
        },
        "health": {},
        "response": {},
        "violations": [],
    }


def _record_violation(report: dict[str, Any], kind: str, details: str) -> None:
    report["violations"].append({"kind": kind, "details": details})


def _offline_smoke(report: dict[str, Any]) -> dict[str, Any]:
    try:
        module = _load_agent_module()
        response = module.run_model_adapter_request(module.sample_request(), force_offline=True)
    except Exception as exc:
        _record_violation(report, "offline_smoke_failed", exc.__class__.__name__)
        return report

    report["response"] = _public_response_summary(response)
    report["checks"]["offline_smoke"] = response.get("ok") is True
    report["checks"]["model_adapter_endpoint"] = response.get("response_kind") == "ai_native_model_adapter_response"
    report["checks"]["no_provider_credentials_required"] = response.get("reason") == "forced_offline"
    report["checks"]["bounded_response"] = report["response"].get("message_bytes", 0) <= 4000
    report["checks"]["no_forbidden_payload_keys"] = not _contains_forbidden_keys(response)
    report["checks"]["tool_powers_declared"] = _tool_powers_safe(report["response"]["tool_powers"])
    report["checks"]["no_direct_world_mutation_tools"] = _tool_powers_safe(report["response"]["tool_powers"])
    if report.get("build_planning_tools_required"):
        report["checks"]["required_tool_calls_satisfied"] = (
            report["response"].get("required_tool_calls_satisfied") is True
            and not report["response"].get("missing_required_tool_calls")
        )
    else:
        report["checks"]["required_tool_calls_satisfied"] = (
            report["response"].get("required_tool_calls_satisfied") is not False
        )
    report["checks"]["public_safe_response"] = response.get("adapter_contract") == "provider_neutral_v1"
    return report


def _probe_http(
    report: dict[str, Any],
    endpoint: str,
    *,
    timeout_seconds: float,
    live_public_prompt: str | None = None,
    require_build_planning_tools: bool = False,
) -> dict[str, Any]:
    base = endpoint.rsplit("/v1/model-adapter", 1)[0]
    try:
        health_status, health = _http_json("GET", f"{base}/health", timeout_seconds=timeout_seconds)
    except Exception as exc:
        _record_violation(report, "health_probe_failed", exc.__class__.__name__)
        return report

    report["health"] = {
        "http_status": health_status,
        "service": health.get("service"),
        "status": health.get("status"),
        "agents_sdk_available": health.get("agents_sdk_available"),
        "openai_api_key_present": health.get("openai_api_key_present"),
        "web_search_tool_available": health.get("web_search_tool_available"),
        "tool_powers": health.get("tool_powers") if isinstance(health.get("tool_powers"), list) else [],
        "world_mutation_authority": health.get("world_mutation_authority"),
        "adapter_name": health.get("adapter_name"),
        "contract": health.get("contract"),
    }
    report["checks"]["health_endpoint"] = (
        health_status == 200
        and health.get("adapter_name") == "openai-agents-sdk-model-adapter"
        and health.get("contract") == "provider_neutral_v1"
    )
    report["checks"]["provider_credentials_present"] = health.get("openai_api_key_present") is True
    report["checks"]["agents_sdk_available"] = health.get("agents_sdk_available") is True
    report["checks"]["web_search_tool_available"] = health.get("web_search_tool_available") is True

    try:
        module = _load_agent_module()
        request = module.sample_request()
        if live_public_prompt:
            request = dict(request)
            request["public_prompt"] = live_public_prompt
        if require_build_planning_tools:
            request = dict(request)
            request["public_prompt"] = "\n".join([
                "Plan a Luanti build request using only the listed executable options.",
                "Player request: build a wall of tnt",
                "Candidate summary: platform:platform:default:4|tnt_wall:wall:tnt:12",
            ])
            request["context"] = {
                "surface_id": "builder",
                "intent": "build_planning",
                "capabilities": "world.read,http.llm",
                "player_request": "build a wall of tnt",
                "candidate_summary": "platform:platform:default:4|tnt_wall:wall:tnt:12",
            }
        adapter_status, response = _http_json(
            "POST",
            endpoint,
            request,
            timeout_seconds=timeout_seconds,
        )
    except Exception as exc:
        _record_violation(report, "adapter_probe_failed", exc.__class__.__name__)
        return report

    report["response"] = _public_response_summary(response)
    report["checks"]["model_adapter_endpoint"] = (
        adapter_status == 200
        and response.get("ok") is True
        and response.get("response_kind") == "ai_native_model_adapter_response"
        and response.get("adapter_contract") == "provider_neutral_v1"
    )
    report["checks"]["no_provider_credentials_required"] = (
        response.get("reason") in {"agents_sdk_not_ready", "forced_offline"}
        or health.get("openai_api_key_present") is True
    )
    report["checks"]["no_forbidden_payload_keys"] = not _contains_forbidden_keys(response)
    report["checks"]["live_agent_execution"] = report["response"].get("agentic_execution") is True
    report["checks"]["live_web_lookup_available"] = (
        report["checks"]["web_search_tool_available"]
        and report["response"].get("web_search_available") is True
    )
    report["checks"]["bounded_response"] = report["response"].get("message_bytes", 0) <= 4000
    report["checks"]["tool_powers_declared"] = (
        _tool_powers_safe(report["health"]["tool_powers"])
        and _tool_powers_safe(report["response"]["tool_powers"])
    )
    report["checks"]["no_direct_world_mutation_tools"] = report["checks"]["tool_powers_declared"]
    if report.get("build_planning_tools_required"):
        report["checks"]["required_tool_calls_satisfied"] = (
            report["response"].get("required_tool_calls_satisfied") is True
            and not report["response"].get("missing_required_tool_calls")
        )
    else:
        report["checks"]["required_tool_calls_satisfied"] = (
            report["response"].get("required_tool_calls_satisfied") is not False
        )
    report["checks"]["public_safe_response"] = response.get("adapter_contract") == "provider_neutral_v1"
    return report


def _start_sidecar(
    host: str,
    port: int,
    *,
    strip_provider_credentials: bool = True,
) -> subprocess.Popen:
    env = dict(os.environ)
    if strip_provider_credentials:
        env.pop("OPENAI_API_KEY", None)
    env.setdefault("AI_NATIVE_AGENT_HTTP_LOGS", "0")
    return subprocess.Popen(
        [sys.executable, str(MAIN), "--host", host, "--port", str(port)],
        cwd=BRIDGE_DIR,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _wait_for_health(endpoint: str, *, timeout_seconds: float) -> None:
    base = endpoint.rsplit("/v1/model-adapter", 1)[0]
    deadline = time.monotonic() + timeout_seconds
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        try:
            _http_json("GET", f"{base}/health", timeout_seconds=0.5)
            return
        except Exception as exc:
            last_exc = exc
            time.sleep(0.1)
    if last_exc:
        raise last_exc
    raise TimeoutError("sidecar health endpoint did not become ready")


def run_readiness(
    *,
    mode: str,
    host: str = "127.0.0.1",
    port: int = 8766,
    endpoint: str | None = None,
    timeout_seconds: float = 5.0,
    require_live_agent: bool = False,
    live_public_prompt: str | None = None,
    require_build_planning_tools: bool = False,
) -> dict[str, Any]:
    if mode == "managed-http" and port == 0:
        port = _free_port()
    endpoint = endpoint or f"http://{host}:{port}/v1/model-adapter"
    report = _base_report(
        mode,
        endpoint,
        require_live_agent=require_live_agent,
        require_build_planning_tools=require_build_planning_tools,
    )
    if not report["checks"]["files_present"]:
        _record_violation(report, "missing_sidecar_files", "agent.py or main.py")
        return report
    if not report["checks"]["loopback_endpoint"]:
        _record_violation(report, "endpoint_not_loopback", endpoint)
        return report
    if require_live_agent and mode == "offline-smoke":
        _record_violation(report, "live_agent_requires_http", "offline-smoke")
    if require_live_agent and mode == "managed-http" and not os.getenv("OPENAI_API_KEY"):
        _record_violation(report, "provider_credentials_missing", "OPENAI_API_KEY not present")

    if mode == "offline-smoke":
        report = _offline_smoke(report)
    elif mode == "existing-http":
        report = _probe_http(
            report,
            endpoint,
            timeout_seconds=timeout_seconds,
            live_public_prompt=live_public_prompt,
            require_build_planning_tools=require_build_planning_tools,
        )
    elif mode == "managed-http":
        process = _start_sidecar(
            host,
            port,
            strip_provider_credentials=not require_live_agent,
        )
        try:
            _wait_for_health(endpoint, timeout_seconds=timeout_seconds)
            report = _probe_http(
                report,
                endpoint,
                timeout_seconds=timeout_seconds,
                live_public_prompt=live_public_prompt,
                require_build_planning_tools=require_build_planning_tools,
            )
        except Exception as exc:
            _record_violation(report, "managed_sidecar_failed", exc.__class__.__name__)
        finally:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
    else:
        _record_violation(report, "unknown_mode", mode)

    required = [
        "files_present",
        "loopback_endpoint",
        "model_adapter_endpoint",
        "no_provider_credentials_required",
        "bounded_response",
        "no_forbidden_payload_keys",
        "tool_powers_declared",
        "no_direct_world_mutation_tools",
        "required_tool_calls_satisfied",
        "public_safe_response",
    ]
    if mode != "offline-smoke":
        required.append("health_endpoint")
    if require_live_agent:
        required.extend([
            "provider_credentials_present",
            "agents_sdk_available",
            "web_search_tool_available",
            "live_agent_execution",
            "live_web_lookup_available",
        ])
    if all(report["checks"].get(key) is True for key in required) and not report["violations"]:
        report["status"] = "pass"
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["offline-smoke", "managed-http", "existing-http"],
        default="managed-http",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--endpoint")
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    parser.add_argument(
        "--require-live-agent",
        action="store_true",
        help="Require provider-backed Agents SDK execution and hosted web lookup availability.",
    )
    parser.add_argument(
        "--live-public-prompt",
        default=(
            "Use current public information when useful, then explain one safe "
            "AI-native Luanti runtime action an operator could try next."
        ),
        help="Public-only prompt used when --require-live-agent is set.",
    )
    parser.add_argument(
        "--require-build-planning-tools",
        action="store_true",
        help="Post a build-planning request and require the sidecar to satisfy required tool calls.",
    )
    parser.add_argument("--output")
    args = parser.parse_args()

    report = run_readiness(
        mode=args.mode,
        host=args.host,
        port=args.port,
        endpoint=args.endpoint,
        timeout_seconds=args.timeout_seconds,
        require_live_agent=args.require_live_agent,
        live_public_prompt=args.live_public_prompt if args.require_live_agent else None,
        require_build_planning_tools=args.require_build_planning_tools,
    )
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        output = pathlib.Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
