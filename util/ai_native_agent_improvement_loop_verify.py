#!/usr/bin/env python3
"""Verify the public-safe agent improvement loop from logs to prompt memory."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any


sys.path.insert(0, str(Path(__file__).resolve().parent))
import ai_native_agent_memory_refresh as memory_refresh


ROOT = Path(__file__).resolve().parents[1]
RESULT_KIND = "ai_native_agent_improvement_loop_verification"
DEFAULT_MAX_BYTES = 32000

PRIVATE_PATTERNS = (
    re.compile(r"/Users/[^\s\"']+"),
    re.compile(r"\bminecraftpi(?:\.home)?\b", re.I),
    re.compile(r"\b192\.168(?:\.\d{1,3}){2}\b"),
    re.compile(r"\bspacebase|themepark|showcase100|disneyland100\b", re.I),
    re.compile(r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"\bOPENAI_API_KEY\b"),
    re.compile(r"\bprivate_prompt\b"),
    re.compile(r"\basset_payload\b"),
    re.compile(r"\bapi_key\b", re.I),
)


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return root / path


def write_jsonl(path: Path, entries: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(entry, sort_keys=True) + "\n" for entry in entries),
        encoding="utf-8",
    )


def build_sidecar_entry(
    *,
    prompt: str,
    selected_option_id: str,
    candidate_summary: str,
    created_at: str,
    tool_decision_source: str = "agents_sdk_function_tool",
    required_tool_calls_satisfied: bool = True,
    missing_required_tool_calls: list[str] | None = None,
) -> dict[str, Any]:
    required = [
        "recall_build_prompt_memory",
        "select_build_option",
        "plan_build_actions",
    ]
    missing = missing_required_tool_calls or []
    tool_trace = [
        {"tool_name": "recall_build_prompt_memory"},
        {"tool_name": "select_build_option"},
        {"tool_name": "plan_build_actions"},
    ]
    if missing:
        tool_trace = [entry for entry in tool_trace if entry["tool_name"] not in set(missing)]
    if selected_option_id.startswith("generated_"):
        required.append("propose_build_option")
    return {
        "schema_version": 1,
        "event_kind": "ai_native_agents_sdk_request_response",
        "created_at": created_at,
        "adapter_name": "openai-agents-sdk-model-adapter",
        "request": {
            "request_kind": "ai_native_model_adapter_request",
            "adapter_contract": "provider_neutral_v1",
            "agent_id": "nova_agent:ImprovementLoop:builder",
            "owner": "ImprovementLoop",
            "task_id": f"improvement-loop:{selected_option_id}",
            "public_prompt": "AI-native Luanti model adapter request.",
            "context": {
                "surface_id": "builder",
                "intent": "build_planning",
                "player_request": prompt,
                "candidate_summary": candidate_summary,
            },
            "safety": {"public_safe_request": True},
            "bounds": {"max_response_bytes": 4000},
        },
        "response": {
            "response_kind": "ai_native_model_adapter_response",
            "adapter_contract": "provider_neutral_v1",
            "ok": True,
            "message": "Bounded public-safe build decision.",
            "adapter_name": "openai-agents-sdk-model-adapter",
            "response": {
                "agentic_execution": True,
                "tools_enabled": [
                    "recall_build_prompt_memory",
                    "select_build_option",
                    "plan_build_actions",
                    "propose_build_option",
                    "WebSearchTool",
                ],
                "tool_decision_source": tool_decision_source,
                "selected_option_id": selected_option_id,
                "required_tool_calls": required,
                "missing_required_tool_calls": missing,
                "required_tool_calls_satisfied": required_tool_calls_satisfied,
                "tool_trace": tool_trace,
                "tool_decisions": {
                    "build_option": {
                        "selected_option_id": selected_option_id,
                        "decision_source": (
                            "agent_selected_generated_build_option"
                            if selected_option_id.startswith("generated_")
                            else "agent_selected_build_option"
                        ),
                        "memory_match": {
                            "memory_available": False,
                            "matched_case_id": None,
                        },
                    },
                    "build_action_plan": {
                        "status": "ready",
                        "selected_option_id": selected_option_id,
                        "step_count": 4,
                        "world_mutation_authority": "luanti",
                    },
                },
                "world_mutation_authority": "luanti",
            },
        },
    }


def build_nova_agent_entry() -> dict[str, Any]:
    return {
        "ts": "2026-06-30T13:05:00Z",
        "player": "ImprovementLoop",
        "prompt": "build a wall of tnt",
        "model": "gpt-4.1-mini",
        "source": "agents_sdk",
        "ok": True,
        "label": "tnt wall",
        "message": "Building a TNT wall.",
        "correction_source": "prompt_contract",
        "contract_satisfied": True,
        "prompt_contract": {
            "contract_kind": "tnt_wall",
            "contract_required": True,
        },
        "actions": [
            {
                "type": "fill_box",
                "material": "tnt",
                "size": {"x": 12, "y": 1, "z": 1},
            }
        ],
        "tool_trace": [
            {"tool_name": "analyze_build_intent"},
            {"tool_name": "validate_plan_contract"},
        ],
    }


def operator_feedback_line() -> str:
    payload = {
        "schema_version": 1,
        "event_kind": "ai_agent_operator_feedback",
        "feedback": {
            "feedback_id": "operator_feedback:improvement-loop:bridge",
            "owner": "ImprovementLoop",
            "agent_id": "nova_agent:ImprovementLoop:guide",
            "source_trace_id": "nova_trace:improvement-loop:bridge",
            "prompt": "build a bridge",
            "case_hint": "stone_bridge_platform",
            "expected": {
                "action": "build",
                "build_kind": "platform",
                "build_material_name": "stone",
                "planned_node_writes": 12,
                "route": "agentic_build_planner",
            },
            "review": {
                "operator_reviewed": True,
                "review_source": "ai_agent_feedback_chatcommand",
                "no_world_mutation": True,
            },
        },
        "safety": {
            "public_safe_output": True,
            "operator_reviewed": True,
            "no_world_mutation": True,
            "no_raw_assets": True,
            "no_provider_prompts": True,
            "no_family_world_coordinates": True,
        },
    }
    return "[ai_agent_plugin] operator_feedback=" + json.dumps(payload, sort_keys=True)


def build_sample_inputs(root: Path) -> tuple[Path, Path, Path]:
    agents_log = root / "agents-sdk-model-adapter.jsonl"
    nova_log = root / "nova-agent-requests.jsonl"
    action_log = root / "luanti-debug.log"
    write_jsonl(
        agents_log,
        [
            build_sidecar_entry(
                prompt="build me a fire and only a fire",
                selected_option_id="fire",
                candidate_summary="fire:fire:fire:1|platform:platform:stone:9",
                created_at="2026-06-30T13:00:00Z",
            ),
            build_sidecar_entry(
                prompt="build a bridge",
                selected_option_id="platform",
                candidate_summary="platform:platform:stone:4|wall:wall:stone:12",
                created_at="2026-06-30T13:01:00Z",
            ),
            build_sidecar_entry(
                prompt="build me a tower",
                selected_option_id="generated_tower_wall",
                candidate_summary="platform:platform:default:4|wall:wall:default:12",
                created_at="2026-06-30T13:02:00Z",
                tool_decision_source="adapter_fallback_after_agent_missing_required_tool",
                required_tool_calls_satisfied=False,
                missing_required_tool_calls=["propose_build_option"],
            ),
        ],
    )
    write_jsonl(nova_log, [build_nova_agent_entry()])
    action_log.write_text(operator_feedback_line() + "\n", encoding="utf-8")
    return agents_log, nova_log, action_log


def _artifact_has_private_content(payload: dict[str, Any]) -> bool:
    raw = json.dumps(payload, sort_keys=True)
    return any(pattern.search(raw) for pattern in PRIVATE_PATTERNS)


def _case_hints(case_pack: dict[str, Any]) -> set[str]:
    return {
        str(case.get("case_hint"))
        for case in case_pack.get("cases", [])
        if isinstance(case, dict) and case.get("case_hint")
    }


def _candidate_summary(candidate_queue: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for candidate in candidate_queue.get("candidates", []):
        if not isinstance(candidate, dict):
            continue
        result.append({
            "candidate_id": candidate.get("candidate_id"),
            "source_kind": candidate.get("source_kind"),
            "prompt": candidate.get("prompt"),
            "case_hint": candidate.get("case_hint"),
            "ready_for_prompt_eval": candidate.get("ready_for_prompt_eval") is True,
            "ready_for_adapter_contract_eval":
                candidate.get("ready_for_adapter_contract_eval") is True,
            "review_status": candidate.get("review_status"),
            "adapter_contract_review_status": candidate.get("adapter_contract_review_status"),
            "priority": candidate.get("priority"),
        })
    return result


def build_report(
    *,
    generated_at: str,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        agents_log, nova_log, action_log = build_sample_inputs(root)
        candidate_queue, case_pack = memory_refresh.build_memory_artifacts(
            agents_sdk_logs=[agents_log],
            nova_agent_logs=[nova_log],
            action_logs=[action_log],
            from_operator_feedback=True,
            generated_at=generated_at,
            candidate_queue_source_path="local/benchmarks/ai-agent-eval-candidate-queue.json",
        )

    source_summary = candidate_queue.get("source_summary", {})
    case_hints = _case_hints(case_pack)
    checks = {
        "agents_sdk_logs_read": source_summary.get("agents_sdk_log_entries_read") == 3,
        "nova_agent_logs_read": source_summary.get("nova_agent_log_entries_read") == 1,
        "operator_feedback_read": source_summary.get("operator_feedback_events_read") == 1,
        "operator_feedback_label_generated":
            source_summary.get("operator_feedback_labels_generated") == 1,
        "operator_feedback_label_applied": source_summary.get("operator_labels_applied") == 1,
        "prompt_eval_candidates_ready": source_summary.get("ready_for_prompt_eval") == 3,
        "adapter_contract_failure_ready":
            source_summary.get("ready_for_adapter_contract_eval") == 1
            and source_summary.get("adapter_contract_failures") == 1,
        "case_pack_ready": case_pack.get("status") == "ready",
        "case_pack_cases": case_pack.get("summary", {}).get("cases_total") == 3,
        "fire_memory_case": "fire_only_strict" in case_hints,
        "tnt_memory_case": "tnt_wall" in case_hints,
        "operator_bridge_memory_case": "stone_bridge_platform" in case_hints,
        "review_required_before_default_gate":
            case_pack.get("summary", {}).get("requires_maintainer_review_before_default_gate")
            is True,
        "public_safe": (
            candidate_queue.get("safety", {}).get("public_safe_output") is True
            and case_pack.get("safety", {}).get("public_safe_output") is True
        ),
        "no_world_mutation": (
            candidate_queue.get("safety", {}).get("no_world_mutation") is True
            and case_pack.get("safety", {}).get("no_world_mutation") is True
        ),
    }
    status = "pass" if all(checks.values()) else "fail"
    payload: dict[str, Any] = {
        "schema_version": 1,
        "artifact_kind": RESULT_KIND,
        "generated_at": generated_at,
        "status": status,
        "runtime_context": {
            "mode": "synthetic_public_safe_agent_improvement_loop",
            "requires_live_pi": False,
            "requires_private_world": False,
            "requires_private_assets": False,
            "requires_model_network": False,
            "world_mutation_performed": False,
        },
        "summary": {
            "agents_sdk_log_entries_read": source_summary.get("agents_sdk_log_entries_read"),
            "nova_agent_log_entries_read": source_summary.get("nova_agent_log_entries_read"),
            "operator_feedback_events_read": source_summary.get("operator_feedback_events_read"),
            "operator_feedback_labels_generated":
                source_summary.get("operator_feedback_labels_generated"),
            "operator_labels_applied": source_summary.get("operator_labels_applied"),
            "candidates_total": source_summary.get("candidates_total"),
            "ready_for_prompt_eval": source_summary.get("ready_for_prompt_eval"),
            "ready_for_adapter_contract_eval":
                source_summary.get("ready_for_adapter_contract_eval"),
            "adapter_contract_failures": source_summary.get("adapter_contract_failures"),
            "case_pack_status": case_pack.get("status"),
            "case_pack_cases": case_pack.get("summary", {}).get("cases_total"),
            "case_hints": sorted(case_hints),
        },
        "checks": checks,
        "candidate_queue": {
            "status": candidate_queue.get("status"),
            "source_summary": source_summary,
            "candidates": _candidate_summary(candidate_queue),
        },
        "case_pack": {
            "status": case_pack.get("status"),
            "summary": case_pack.get("summary"),
            "cases": case_pack.get("cases"),
        },
        "safety": {
            "public_safe_output": True,
            "synthetic_logs_only": True,
            "review_required_before_default_gate": True,
            "no_world_mutation": True,
            "no_raw_assets": True,
            "no_provider_prompts": True,
            "no_family_world_coordinates": True,
        },
        "bounds": {
            "max_bytes": max_bytes,
            "output_bytes": 0,
            "truncated": False,
        },
    }
    payload["bounds"]["output_bytes"] = len(json.dumps(payload, sort_keys=True).encode("utf-8"))
    if payload["bounds"]["output_bytes"] > max_bytes:
        payload["status"] = "fail"
        payload["bounds"]["truncated"] = True
    if _artifact_has_private_content(payload):
        payload["status"] = "fail"
        payload["safety"]["public_safe_output"] = False
    return payload


def validate_report(payload: dict[str, Any], max_bytes: int = DEFAULT_MAX_BYTES) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("agent improvement loop report must be an object")
    if payload.get("artifact_kind") != RESULT_KIND:
        raise ValueError("agent improvement loop result kind is invalid")
    if payload.get("status") != "pass":
        raise ValueError("agent improvement loop result did not pass")
    if _artifact_has_private_content(payload):
        raise ValueError("agent improvement loop result contains private content")
    runtime_context = payload.get("runtime_context")
    if not isinstance(runtime_context, dict):
        raise ValueError("agent improvement loop runtime_context missing")
    for field in (
        "requires_live_pi",
        "requires_private_world",
        "requires_private_assets",
        "requires_model_network",
        "world_mutation_performed",
    ):
        if runtime_context.get(field) is not False:
            raise ValueError(f"agent improvement loop {field} must be false")
    checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
    for field, passed in checks.items():
        if passed is not True:
            raise ValueError(f"agent improvement loop check failed: {field}")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    required_counts = {
        "agents_sdk_log_entries_read": 3,
        "nova_agent_log_entries_read": 1,
        "operator_feedback_events_read": 1,
        "operator_feedback_labels_generated": 1,
        "operator_labels_applied": 1,
        "ready_for_prompt_eval": 3,
        "ready_for_adapter_contract_eval": 1,
        "adapter_contract_failures": 1,
        "case_pack_cases": 3,
    }
    for field, expected in required_counts.items():
        if summary.get(field) != expected:
            raise ValueError(f"agent improvement loop {field} is invalid")
    case_hints = set(summary.get("case_hints") if isinstance(summary.get("case_hints"), list) else [])
    for required_hint in ("fire_only_strict", "tnt_wall", "stone_bridge_platform"):
        if required_hint not in case_hints:
            raise ValueError(f"agent improvement loop missing case hint {required_hint}")
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    for field in (
        "public_safe_output",
        "synthetic_logs_only",
        "review_required_before_default_gate",
        "no_world_mutation",
        "no_raw_assets",
        "no_provider_prompts",
        "no_family_world_coordinates",
    ):
        if safety.get(field) is not True:
            raise ValueError(f"agent improvement loop safety {field} is invalid")
    bounds = payload.get("bounds") if isinstance(payload.get("bounds"), dict) else {}
    output_bytes = bounds.get("output_bytes")
    declared_max = bounds.get("max_bytes", max_bytes)
    if not isinstance(output_bytes, int) or not isinstance(declared_max, int):
        raise ValueError("agent improvement loop bounds are invalid")
    if output_bytes > declared_max or output_bytes > max_bytes:
        raise ValueError("agent improvement loop output exceeds max bytes")
    return {
        "agent_improvement_loop_status": "pass",
        "agent_improvement_loop_output_bytes": output_bytes,
        "agent_improvement_loop_agents_sdk_logs": 3,
        "agent_improvement_loop_nova_agent_logs": 1,
        "agent_improvement_loop_operator_feedback": 1,
        "agent_improvement_loop_operator_labels_applied": 1,
        "agent_improvement_loop_prompt_eval_candidates": 3,
        "agent_improvement_loop_case_pack_cases": 3,
        "agent_improvement_loop_adapter_contract_failures": 1,
        "agent_improvement_loop_adapter_contract_eval_ready": 1,
        "agent_improvement_loop_case_hints": sorted(case_hints),
        "agent_improvement_loop_world_mutation": False,
        "agent_improvement_loop_requires_model_network": False,
    }


def run_verifier(args: argparse.Namespace) -> int:
    root = resolve_path(Path.cwd(), args.root).resolve()
    output = resolve_path(root, args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = build_report(generated_at=args.generated_at, max_bytes=args.max_bytes)
    try:
        validate_report(payload, max_bytes=args.max_bytes)
    except ValueError as exc:
        output.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
        print(f"agent improvement loop verification failed: {exc}", file=sys.stderr)
        return 1
    output.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(output)
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify the public-safe agent improvement loop from logs to prompt memory."
    )
    parser.add_argument("--root", default=".", help="Repository root. Default: current directory.")
    parser.add_argument("--output", required=True, help="Path to write the verification artifact.")
    parser.add_argument("--generated-at", required=True, help="UTC timestamp for the artifact.")
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_BYTES,
        help="Maximum byte budget for retained verification artifact.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    return run_verifier(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
