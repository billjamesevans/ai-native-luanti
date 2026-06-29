#!/usr/bin/env python3
"""Verify the AI-native alpha release contributor package is present."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import ai_native_product_profile_verify


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
            "operator-alpha-release-runbook.md",
            "deployment lane, not a replacement for the family server",
            "spacebase",
            "themepark",
            "disneyland100",
        ],
    },
    {
        "path": "doc/ai-native-runtime/operator-alpha-release-runbook.md",
        "kind": "operator_alpha_release_runbook",
        "phrases": [
            "ai-native-luanti-test.service",
            "luanti-family.service",
            "UDP `30000`",
            "UDP `30001`",
            "backup-first",
            "rollback stops only the fork alpha lane",
            "Release Candidate Contents",
            "Evidence Retention",
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
    {
        "path": "doc/ai-native-runtime/project-operating-loop.md",
        "kind": "project_operating_loop",
        "phrases": [
            "ranked next-issue queue",
            "release_candidate_checklist",
            "python3 util/ai_native_alpha_release_gate.py",
            "python3 util/ai_native_runtime_verify.py --hardware-class local-mac --game-profile ai_runtime",
            "python3 util/ai_native_minecraft_parity_harness.py --output-root local/benchmarks",
            "#253",
            "#254",
            "#255",
            "#256",
            "spacebase",
            "themepark",
            "disneyland100",
            "side-by-side",
        ],
    },
]

PROJECT_OPERATING_LOOP = {
    "cadence": [
        {
            "name": "pre_pr_local_gate",
            "commands": [
                ["python3", "util/ai_native_alpha_release_gate.py"],
                [
                    "python3",
                    "util/ai_native_runtime_verify.py",
                    "--hardware-class",
                    "local-mac",
                    "--game-profile",
                    "ai_runtime",
                ],
            ],
            "purpose": "prove the clean ai_runtime contributor package and local runtime evidence before opening a PR",
        },
        {
            "name": "benchmark_review",
            "commands": [
                [
                    "python3",
                    "util/ai_native_minecraft_parity_harness.py",
                    "--output-root",
                    "local/benchmarks",
                ]
            ],
            "purpose": "keep Minecraft-parity targets current without retaining proprietary benchmark payloads",
        },
        {
            "name": "pi_promotion",
            "commands": [
                [
                    "python3",
                    "util/ai_native_low_power_pi_evidence.py",
                    "--ssh-target",
                    "<operator-supplied-target>",
                    "--confirm-backup-first",
                    "--soak-target",
                    "quick",
                ]
            ],
            "purpose": "promote only after backup-first side-by-side deployment preserves the family server",
        },
    ],
    "ranked_next_issue_queue": [
        {
            "issue": "#253",
            "title": "Promoted Pi one-hour and overnight evidence for current alpha",
            "when": "after current evidence lane clears",
            "gate": "backup-first side-by-side Pi deploy and low-power evidence",
        },
        {
            "issue": "#254",
            "title": "First-party AI agent productization lane",
            "when": "parallel local work while Pi evidence is occupied",
            "gate": "live product-loop probe and one-command local verifier",
        },
        {
            "issue": "#255",
            "title": "Compatibility import scale-up after staged apply pilot",
            "when": "after runtime/product loop evidence stays clean",
            "gate": "dry-run or approval-gated apply with rollback metadata",
        },
        {
            "issue": "#256",
            "title": "Minecraft parity benchmark expansion",
            "when": "after accepted local and low-power lanes are refreshed",
            "gate": "public-safe parity harness with actionable scorecard",
        },
    ],
    "maintenance_invariants": [
        {
            "name": "operating_loop_maintenance",
            "status": "complete_but_enforced",
            "when": "after each milestone slice",
            "gate": "alpha gate docs/templates/report remain complete",
        },
    ],
    "public_boundary": {
        "family_server_role": "private proving ground only",
        "fork_lane": "side-by-side ai_runtime alpha lane",
        "excluded_content": ["spacebase", "themepark", "disneyland100"],
    },
}

RELEASE_CANDIDATE_CHECKLIST = {
    "candidate_id_source": {
        "command": ["git", "rev-parse", "--short", "HEAD"],
        "purpose": "record the public fork commit being promoted",
    },
    "phases": [
        {
            "name": "clean_checkout_package",
            "required_commands": [
                ["git", "status", "--short", "--branch"],
                ["python3", "util/ai_native_alpha_release_gate.py", "--root", "."],
            ],
            "done_when": [
                "worktree contains only intended release-candidate changes",
                "alpha release gate status is pass",
                "clean ai_runtime profile package is fixture-free",
            ],
        },
        {
            "name": "local_runtime_evidence",
            "required_commands": [
                ONE_COMMAND_LOCAL_VERIFIER,
                ["bin/luantiserver", "--run-unittests", "--test-module", "TestAIRuntime"],
            ],
            "retained_artifacts": [
                "local/benchmarks/local-mac/<date>/<commit>/ai-runtime-verification-manifest.json",
                "local/benchmarks/agent-product-loop-live.json",
            ],
            "done_when": [
                "local clean-profile verifier passes",
                "TestAIRuntime passes",
                "agent product-loop evidence is public-safe and bounded",
            ],
        },
        {
            "name": "compatibility_and_parity_review",
            "required_commands": [
                [
                    "python3",
                    "util/ai_native_minecraft_parity_harness.py",
                    "--output-root",
                    "local/benchmarks",
                ],
            ],
            "retained_artifacts": [
                "local/benchmarks/minecraft-parity-comparison-report.json",
                "local/benchmarks/compatibility-import-inventory-discovery-report.json",
            ],
            "done_when": [
                "Minecraft-parity report privacy_scan.status is passed",
                "ranked improvement targets are empty or have follow-up issues",
                "compatibility/import reports remain metadata-only or disposable-staging-only",
            ],
        },
        {
            "name": "pi_side_by_side_promotion",
            "required_commands": [
                [
                    "python3",
                    "util/ai_native_low_power_pi_evidence.py",
                    "--ssh-target",
                    "<operator-supplied-target>",
                    "--confirm-backup-first",
                    "--soak-target",
                    "quick",
                ],
            ],
            "deploy_boundary": {
                "family_service": "luanti-family.service",
                "family_port": "30000/udp",
                "fork_service": "ai-native-luanti-test.service",
                "fork_port": "30001/udp",
                "mode": "side_by_side_test_service_only",
            },
            "done_when": [
                "backup label and sha256 are recorded before deploy",
                "family service remains active on UDP 30000",
                "fork service is active on UDP 30001",
                "low-power evidence passes for the promoted commit",
            ],
        },
        {
            "name": "release_closeout",
            "required_artifacts": [
                "release notes using doc/ai-native-runtime/release-notes-template.md",
                "issue comment or PR comment with verification commands",
                "ranked next-issue queue from project_operating_loop",
            ],
            "done_when": [
                "release notes separate engine/runtime, first-party plugins, compatibility/import, benchmarks, and family-server exclusions",
                "next issue is selected from the ranked queue",
                "no private family content or proprietary payloads are committed",
            ],
        },
    ],
    "public_boundary": {
        "excluded_content": ["spacebase", "themepark", "disneyland100"],
        "private_artifacts_not_committed": [
            "family worlds",
            "player-private data",
            "provider prompts",
            "credentials",
            "copied proprietary assets",
            "server jars",
            "marketplace content",
        ],
    },
}

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
            "operator-alpha-release-runbook.md",
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
    clean_profile_package = ai_native_product_profile_verify.build_report(root)

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
        "clean_profile_package_verified": clean_profile_package.get("status") == "pass"
        and all(clean_profile_package.get("safety", {}).values()),
    }

    for key, value in safety.items():
        if value is not True:
            violations.append({"kind": "alpha_safety_gate_failed", "gate": key})
    if clean_profile_package.get("status") != "pass":
        violations.append({
            "kind": "clean_profile_package_failed",
            "status": clean_profile_package.get("status"),
            "violations": clean_profile_package.get("violations", []),
        })
    for key, value in clean_profile_package.get("safety", {}).items():
        if value is not True:
            violations.append({
                "kind": "clean_profile_package_safety_failed",
                "gate": key,
            })

    return {
        "schema_version": 1,
        "status": "pass" if not violations else "fail",
        "alpha_package": {
            "one_command_local_verifier": ONE_COMMAND_LOCAL_VERIFIER,
            "clean_profile": "games/ai_runtime",
            "pi_deployment_boundary": "side_by_side_test_service_only",
            "fresh_checkout_command_plan": [
                {
                    "step": "configure_server_release",
                    "command": [
                        "cmake",
                        "-S",
                        ".",
                        "-B",
                        "build/server-release",
                        "-DCMAKE_BUILD_TYPE=RelWithDebInfo",
                        "-DBUILD_CLIENT=FALSE",
                        "-DBUILD_SERVER=TRUE",
                        "-DBUILD_UNITTESTS=TRUE",
                        "-DRUN_IN_PLACE=TRUE",
                    ],
                },
                {
                    "step": "build_server_release",
                    "command": [
                        "cmake",
                        "--build",
                        "build/server-release",
                        "--parallel",
                    ],
                },
                {
                    "step": "smoke_test_runtime",
                    "command": [
                        "bin/luantiserver",
                        "--run-unittests",
                        "--test-module",
                        "TestAIRuntime",
                    ],
                },
                {
                    "step": "run_one_command_verifier",
                    "command": ONE_COMMAND_LOCAL_VERIFIER,
                },
            ],
        },
        "project_operating_loop": PROJECT_OPERATING_LOOP,
        "release_candidate_checklist": RELEASE_CANDIDATE_CHECKLIST,
        "clean_profile_package": clean_profile_package,
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
