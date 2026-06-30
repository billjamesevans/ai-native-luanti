#!/usr/bin/env python3
"""Verify the public AI model-adapter contract package."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys


REQUEST_EXAMPLE = pathlib.Path(
    "doc/ai-native-runtime/examples/model-adapter-request.example.json"
)
RESPONSE_EXAMPLE = pathlib.Path(
    "doc/ai-native-runtime/examples/model-adapter-response.example.json"
)
REQUEST_SCHEMA = pathlib.Path(
    "doc/ai-native-runtime/schemas/model-adapter-request.schema.json"
)
RESPONSE_SCHEMA = pathlib.Path(
    "doc/ai-native-runtime/schemas/model-adapter-response.schema.json"
)
DOC = pathlib.Path("doc/ai-native-runtime/model-adapter-contract.md")
README = pathlib.Path("doc/ai-native-runtime/README.md")

PRIVATE_PATTERNS = re.compile(
    r"minecraftpi|192\.168|spacebase|themepark|showcase100|disneyland100|"
    r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY|private_prompt|"
    r"asset_payload|raw_provider_response|/Users/",
    re.I,
)
FORBIDDEN_RESPONSE_FIELDS = {
    "private_payload",
    "private_prompt",
    "raw_provider_response",
    "raw_provider_request",
    "raw_asset_payload",
    "asset_payload",
    "provider_credentials",
    "api_key",
    "headers",
    "request_body",
}


def read_json(root: pathlib.Path, relpath: pathlib.Path) -> dict:
    return json.loads((root / relpath).read_text(encoding="utf-8"))


def has_forbidden_field(value) -> bool:
    if not isinstance(value, dict):
        return False
    for key, child in value.items():
        if key in FORBIDDEN_RESPONSE_FIELDS:
            return True
        if isinstance(child, dict) and has_forbidden_field(child):
            return True
        if isinstance(child, list):
            for item in child:
                if isinstance(item, dict) and has_forbidden_field(item):
                    return True
    return False


def require_file(root: pathlib.Path, relpath: pathlib.Path, violations: list[dict]) -> bool:
    if not (root / relpath).is_file():
        violations.append({"kind": "missing_file", "path": relpath.as_posix()})
        return False
    return True


def check_request(payload: dict, violations: list[dict]) -> dict:
    checks = {
        "schema_version": payload.get("schema_version") == 1,
        "request_kind": payload.get("request_kind") == "ai_native_model_adapter_request",
        "adapter_contract": payload.get("adapter_contract") == "provider_neutral_v1",
        "agent_id": isinstance(payload.get("agent_id"), str) and payload.get("agent_id"),
        "owner": isinstance(payload.get("owner"), str) and payload.get("owner"),
        "public_prompt": isinstance(payload.get("public_prompt"), str)
        and bool(payload.get("public_prompt")),
        "no_legacy_prompt": "prompt" not in payload,
        "no_private_prompt": "private_prompt" not in payload,
        "safety": isinstance(payload.get("safety"), dict)
        and payload["safety"].get("public_safe_request") is True
        and payload["safety"].get("private_input_retained") is False
        and payload["safety"].get("no_provider_credentials") is True,
        "bounds": isinstance(payload.get("bounds"), dict)
        and isinstance(payload["bounds"].get("max_response_bytes"), int)
        and payload["bounds"]["max_response_bytes"] > 0
        and isinstance(payload["bounds"].get("max_context_keys"), int)
        and payload["bounds"]["max_context_keys"] >= 0,
    }
    for check, passed in checks.items():
        if not passed:
            violations.append({"kind": "request_contract_failed", "check": check})
    return checks


def check_response(payload: dict, violations: list[dict]) -> dict:
    checks = {
        "schema_version": payload.get("schema_version") == 1,
        "response_kind": payload.get("response_kind") == "ai_native_model_adapter_response",
        "ok": payload.get("ok") in {True, False},
        "message": isinstance(payload.get("message"), str) and bool(payload.get("message")),
        "adapter_name": isinstance(payload.get("adapter_name"), str)
        and bool(payload.get("adapter_name")),
        "no_forbidden_fields": not has_forbidden_field(payload),
    }
    for check, passed in checks.items():
        if not passed:
            violations.append({"kind": "response_contract_failed", "check": check})
    return checks


def build_report(root: pathlib.Path | str) -> dict:
    root = pathlib.Path(root)
    violations = []
    for path in [REQUEST_EXAMPLE, RESPONSE_EXAMPLE, REQUEST_SCHEMA, RESPONSE_SCHEMA, DOC, README]:
        require_file(root, path, violations)

    request = {}
    response = {}
    request_checks = {}
    response_checks = {}
    if not violations:
        request = read_json(root, REQUEST_EXAMPLE)
        response = read_json(root, RESPONSE_EXAMPLE)
        request_checks = check_request(request, violations)
        response_checks = check_response(response, violations)

        combined = json.dumps({"request": request, "response": response}, sort_keys=True)
        if PRIVATE_PATTERNS.search(combined):
            violations.append({"kind": "private_or_raw_payload_marker_in_examples"})

        readme = (root / README).read_text(encoding="utf-8")
        doc = (root / DOC).read_text(encoding="utf-8")
        if "model-adapter-contract.md" not in readme:
            violations.append({"kind": "readme_missing_model_adapter_contract"})
        if "python3 util/ai_native_model_adapter_contract.py" not in readme:
            violations.append({"kind": "readme_missing_model_adapter_verifier"})
        for phrase in [
            "provider-neutral",
            "core.ai_model_ops.request",
            "core.ai_model_ops.request_async",
            "core.ai_agent_plugin.set_model_adapter",
            "core.ai_agent_plugin.set_model_adapter_async",
            "public_prompt",
            "adapter_payload_rejected",
        ]:
            if phrase not in doc:
                violations.append({"kind": "doc_missing_required_phrase", "phrase": phrase})

    return {
        "schema_version": 1,
        "status": "pass" if not violations else "fail",
        "contract": {
            "runtime_entrypoint": "core.ai_model_ops.request",
            "runtime_entrypoints": [
                "core.ai_model_ops.request",
                "core.ai_model_ops.request_async",
            ],
            "agent_plugin_entrypoint": "core.ai_agent_plugin.set_model_adapter",
            "agent_plugin_entrypoints": [
                "core.ai_agent_plugin.set_model_adapter",
                "core.ai_agent_plugin.set_model_adapter_async",
            ],
            "request_example": REQUEST_EXAMPLE.as_posix(),
            "response_example": RESPONSE_EXAMPLE.as_posix(),
            "request_schema": REQUEST_SCHEMA.as_posix(),
            "response_schema": RESPONSE_SCHEMA.as_posix(),
        },
        "request_checks": request_checks,
        "response_checks": response_checks,
        "safety": {
            "provider_neutral": request.get("adapter_contract") == "provider_neutral_v1",
            "public_safe_examples": not PRIVATE_PATTERNS.search(
                json.dumps({"request": request, "response": response}, sort_keys=True)
            ) if request or response else False,
            "no_raw_provider_payloads": not has_forbidden_field(response),
        },
        "violations": violations,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root to verify.")
    parser.add_argument("--output", help="Write JSON report to this path.")
    args = parser.parse_args(argv)

    try:
        report = build_report(args.root)
        payload = json.dumps(report, indent=2, sort_keys=False) + "\n"
        if args.output:
            output_path = pathlib.Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(payload, encoding="utf-8")
        else:
            sys.stdout.write(payload)
        return 0 if report["status"] == "pass" else 2
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
