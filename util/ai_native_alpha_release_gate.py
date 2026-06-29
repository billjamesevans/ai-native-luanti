#!/usr/bin/env python3
"""Verify the AI-native alpha release contributor package is present."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys


ONE_COMMAND_LOCAL_VERIFIER = [
    "python3",
    "util/ai_native_runtime_verify.py",
    "--hardware-class",
    "local-mac",
    "--game-profile",
    "ai_runtime",
]

REQUIRED_DOCS = [
    {
        "path": "doc/ai-native-runtime/alpha-release-gate.md",
        "kind": "alpha_gate",
        "phrases": [
            "one-command local verifier",
            "python3 util/ai_native_runtime_verify.py --hardware-class local-mac --game-profile ai_runtime",
            "deployment lane, not a replacement for the family server",
            "spacebase",
            "themepark",
            "disneyland100",
        ],
    },
    {
        "path": "doc/ai-native-runtime/clean-ai-runtime-install.md",
        "kind": "clean_install",
        "phrases": [
            "games/ai_runtime",
            "cmake -S . -B build/server-release",
            "--gameid ai_runtime",
            "TestAIRuntime",
        ],
    },
    {
        "path": "doc/ai-native-runtime/public-safe-sample-data-policy.md",
        "kind": "sample_data_policy",
        "phrases": [
            "metadata-only",
            "no raw asset payloads",
            "no private worlds",
            "no provider prompts",
            "spacebase",
            "themepark",
            "disneyland100",
        ],
    },
    {
        "path": "doc/ai-native-runtime/release-notes-template.md",
        "kind": "release_notes_template",
        "phrases": [
            "Engine/runtime changes",
            "Optional plugin changes",
            "Family-server content excluded",
            "Public-safe sample data",
        ],
    },
]

REQUIRED_ISSUE_TEMPLATES = [
    {
        "path": ".github/ISSUE_TEMPLATE/ai_runtime.yml",
        "kind": "runtime",
        "phrases": ["AI runtime", "clean ai_runtime profile", "Public/private boundary"],
    },
    {
        "path": ".github/ISSUE_TEMPLATE/agent_plugin.yml",
        "kind": "agent",
        "phrases": ["Agent plugin", "capability profile", "Public/private boundary"],
    },
    {
        "path": ".github/ISSUE_TEMPLATE/benchmark.yml",
        "kind": "benchmark",
        "phrases": ["Benchmark", "hardware class", "Public/private boundary"],
    },
    {
        "path": ".github/ISSUE_TEMPLATE/compat_import.yml",
        "kind": "compat_import",
        "phrases": ["Compatibility import", "dry-run", "Public/private boundary"],
    },
]

REQUIRED_REPO_FILES = [
    {
        "path": ".github/PULL_REQUEST_TEMPLATE.md",
        "kind": "pull_request_template",
        "phrases": [
            "python3 util/ai_native_alpha_release_gate.py",
            "python3 util/ai_native_runtime_verify.py --hardware-class local-mac --game-profile ai_runtime",
            "spacebase",
            "themepark",
            "disneyland100",
            "family-server content",
        ],
    },
    {
        "path": "doc/ai-native-runtime/README.md",
        "kind": "runtime_readme",
        "phrases": [
            "alpha-release-gate.md",
            "clean-ai-runtime-install.md",
            "public-safe-sample-data-policy.md",
            "release-notes-template.md",
            "python3 util/ai_native_alpha_release_gate.py",
        ],
    },
]


def read_text(root: pathlib.Path, relpath: str) -> str:
    return (root / relpath).read_text(encoding="utf-8")


def check_required_file(root: pathlib.Path, spec: dict) -> tuple[dict, list[dict]]:
    path = root / spec["path"]
    result = {
        "kind": spec["kind"],
        "path": spec["path"],
        "status": "present",
        "missing_phrases": [],
    }
    violations = []
    if not path.is_file():
        result["status"] = "missing"
        violations.append({"kind": "missing_file", "path": spec["path"]})
        return result, violations

    body = read_text(root, spec["path"])
    missing_phrases = [phrase for phrase in spec["phrases"] if phrase not in body]
    result["missing_phrases"] = missing_phrases
    if missing_phrases:
        result["status"] = "incomplete"
        violations.append({
            "kind": "missing_required_phrases",
            "path": spec["path"],
            "phrases": missing_phrases,
        })
    return result, violations


def build_report(root: pathlib.Path | str) -> dict:
    root = pathlib.Path(root)
    violations = []

    docs = []
    for spec in REQUIRED_DOCS:
        result, file_violations = check_required_file(root, spec)
        docs.append(result)
        violations.extend(file_violations)

    issue_templates = []
    for spec in REQUIRED_ISSUE_TEMPLATES:
        result, file_violations = check_required_file(root, spec)
        issue_templates.append(result)
        violations.extend(file_violations)

    repo_files = []
    for spec in REQUIRED_REPO_FILES:
        result, file_violations = check_required_file(root, spec)
        repo_files.append(result)
        violations.extend(file_violations)

    doc_status = {entry["kind"]: entry["status"] for entry in docs}
    file_status = {entry["kind"]: entry["status"] for entry in repo_files}

    safety = {
        "public_sample_data_only": doc_status.get("sample_data_policy") == "present",
        "family_content_excluded": doc_status.get("alpha_gate") == "present"
        and file_status.get("pull_request_template") == "present",
        "pi_side_by_side_only": doc_status.get("alpha_gate") == "present",
        "release_notes_separate_engine_plugins_family_content": (
            doc_status.get("release_notes_template") == "present"
        ),
    }

    for key, value in safety.items():
        if value is not True:
            violations.append({"kind": "alpha_safety_gate_failed", "gate": key})

    return {
        "schema_version": 1,
        "status": "pass" if not violations else "fail",
        "alpha_package": {
            "one_command_local_verifier": ONE_COMMAND_LOCAL_VERIFIER,
            "clean_profile": "games/ai_runtime",
            "pi_deployment_boundary": "side_by_side_test_service_only",
        },
        "docs": docs,
        "issue_templates": issue_templates,
        "repo_files": repo_files,
        "safety": safety,
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
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
