#!/usr/bin/env python3
"""Create a reviewed Nova feedback packet from runtime logs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ai_native_agent_eval_queue as eval_queue
import ai_native_agent_memory_refresh as memory_refresh
import ai_native_agent_operator_label as operator_label


OPERATOR_FEEDBACK_MARKER = "operator_feedback="
OPERATOR_FEEDBACK_KIND = "ai_agent_operator_feedback"


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return root / path


def relative_label(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else path.name


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def extract_operator_feedback_json(line: str) -> dict[str, Any] | None:
    raw = line.strip()
    if OPERATOR_FEEDBACK_MARKER in raw:
        raw = raw.split(OPERATOR_FEEDBACK_MARKER, 1)[1].strip()
    if not raw.startswith("{"):
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or payload.get("event_kind") != OPERATOR_FEEDBACK_KIND:
        return None
    return payload


def read_operator_feedback_events(paths: list[Path]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    events: list[dict[str, Any]] = []
    summary = {
        "operator_feedback_events_read": 0,
        "operator_feedback_events_skipped_private": 0,
        "operator_feedback_missing_logs": 0,
    }
    for path in paths:
        if not path.is_file():
            summary["operator_feedback_missing_logs"] += 1
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            payload = extract_operator_feedback_json(raw)
            if payload is None:
                continue
            summary["operator_feedback_events_read"] += 1
            if eval_queue.has_private_content(payload) or eval_queue.has_forbidden_key(payload):
                summary["operator_feedback_events_skipped_private"] += 1
                continue
            events.append(payload)
    return events, summary


def operator_feedback_inputs(
    events: list[dict[str, Any]],
    *,
    feedback_id: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for event in events:
        feedback = event.get("feedback") if isinstance(event.get("feedback"), dict) else {}
        if feedback_id and feedback.get("feedback_id") != feedback_id:
            continue
        matches.append(event)
    if not matches:
        raise operator_label.OperatorLabelError("no matching operator feedback found")
    event = matches[-1]
    feedback = event.get("feedback") if isinstance(event.get("feedback"), dict) else {}
    expected = eval_queue.safe_expected_from_operator_label(feedback.get("expected"))
    if expected is None:
        raise operator_label.OperatorLabelError("operator feedback expected build behavior is invalid")
    prompt = feedback.get("prompt")
    candidate_id = feedback.get("candidate_id")
    if not isinstance(prompt, str) and not isinstance(candidate_id, str):
        raise operator_label.OperatorLabelError("operator feedback needs prompt or candidate_id")
    inputs = {
        "candidate_id": candidate_id if isinstance(candidate_id, str) and candidate_id else None,
        "prompt": prompt if isinstance(prompt, str) and prompt else None,
        "source_kind": feedback.get("source_kind") if isinstance(feedback.get("source_kind"), str) else None,
        "case_hint": feedback.get("case_hint") if isinstance(feedback.get("case_hint"), str) else None,
        "label_id": feedback.get("label_id") if isinstance(feedback.get("label_id"), str) else None,
        "expected": expected,
    }
    summary = {
        "operator_feedback_id": feedback.get("feedback_id"),
        "operator_feedback_source_trace_id": feedback.get("source_trace_id"),
        "operator_feedback_case_hint": inputs["case_hint"],
    }
    return inputs, summary


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build one public-safe reviewed Nova feedback packet: candidate queue, "
            "operator label, and prompt-memory case pack."
        ),
    )
    parser.add_argument("--root", default=".", help="Repository root for relative paths.")
    parser.add_argument("--agents-sdk-log", action="append", default=[], help="Agents SDK adapter JSONL log path.")
    parser.add_argument("--nova-agent-log", action="append", default=[], help="Nova sidecar request JSONL log path.")
    parser.add_argument("--action-log", action="append", default=[], help="Luanti action/debug log with request_trace JSON.")
    parser.add_argument("--candidate-id", default=None, help="Candidate id to label.")
    parser.add_argument("--prompt", default=None, help="Public prompt to label when candidate id is not supplied.")
    parser.add_argument("--source-kind", default=None, help="Optional source_kind match guard.")
    parser.add_argument("--case-hint", default=None, help="Prompt-memory case hint.")
    parser.add_argument("--label-id", default=None, help="Stable reviewed label id.")
    parser.add_argument(
        "--from-operator-feedback",
        action="store_true",
        help="Use the latest public-safe ai_agent_operator_feedback event from action logs.",
    )
    parser.add_argument("--feedback-id", default=None, help="Specific ai_agent_operator_feedback feedback_id to use.")
    parser.add_argument("--build-kind", default=None, help="Expected build kind, such as fire, wall, or platform.")
    parser.add_argument("--build-material-name", default=None, help="Expected material name, such as fire or tnt.")
    parser.add_argument("--build-material-node", default=None, help="Optional expected Luanti node name.")
    parser.add_argument("--planned-node-writes", type=int, default=None, help="Expected planned write count.")
    parser.add_argument("--route", default=None, help="Optional expected route.")
    parser.add_argument("--danger-refusal-allowed", type=operator_label.parse_optional_bool, default=None)
    parser.add_argument("--forbidden-extra-structure", type=operator_label.parse_optional_bool, default=None)
    parser.add_argument("--allow-unmatched", action="store_true", help="Create the label even if no candidate matches.")
    parser.add_argument(
        "--candidate-queue-output",
        default="local/benchmarks/ai-agent-eval-candidate-queue.json",
        help="Output candidate queue JSON path.",
    )
    parser.add_argument(
        "--operator-label-output",
        default="local/benchmarks/ai-agent-operator-labels.json",
        help="Output operator-label JSON path.",
    )
    parser.add_argument(
        "--case-pack-output",
        default="local/benchmarks/ai-agent-prompt-eval-case-pack.json",
        help="Output prompt-memory case pack JSON path.",
    )
    parser.add_argument("--generated-at", default=None, help="ISO timestamp for deterministic artifacts.")
    parser.add_argument("--max-candidates", type=int, default=eval_queue.DEFAULT_MAX_CANDIDATES)
    parser.add_argument("--max-candidate-queue-bytes", type=int, default=eval_queue.DEFAULT_MAX_BYTES)
    parser.add_argument("--max-cases", type=int, default=25)
    parser.add_argument("--max-case-pack-bytes", type=int, default=24000)
    return parser.parse_args(argv)


def build_feedback_packet(
    *,
    root: Path,
    agents_sdk_logs: list[Path],
    nova_agent_logs: list[Path],
    action_logs: list[Path],
    candidate_queue_output: Path,
    operator_label_output: Path,
    case_pack_output: Path,
    candidate_id: str | None,
    prompt: str | None,
    source_kind: str | None,
    case_hint: str | None,
    label_id: str | None,
    expected: dict[str, Any],
    allow_unmatched: bool,
    generated_at: str | None,
    max_candidates: int,
    max_candidate_queue_bytes: int,
    max_cases: int,
    max_case_pack_bytes: int,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    initial_queue = eval_queue.build_eval_candidate_queue(
        agents_sdk_logs=agents_sdk_logs,
        nova_agent_logs=nova_agent_logs,
        action_logs=action_logs,
        generated_at=generated_at,
        max_candidates=max(0, max_candidates),
        max_bytes=max(1000, max_candidate_queue_bytes),
    )
    label_artifact = operator_label.build_operator_label_artifact(
        candidate_queue=initial_queue,
        candidate_queue_path=relative_label(root, candidate_queue_output),
        candidate_id=candidate_id,
        prompt=prompt,
        source_kind=source_kind,
        case_hint=case_hint,
        label_id=label_id,
        expected=expected,
        allow_unmatched=allow_unmatched,
        generated_at=generated_at,
    )
    write_json(operator_label_output, label_artifact)
    candidate_queue, case_pack = memory_refresh.build_memory_artifacts(
        agents_sdk_logs=agents_sdk_logs,
        nova_agent_logs=nova_agent_logs,
        action_logs=action_logs,
        operator_label_files=[operator_label_output],
        generated_at=generated_at,
        candidate_queue_source_path=relative_label(root, candidate_queue_output),
        max_candidates=max_candidates,
        max_candidate_queue_bytes=max_candidate_queue_bytes,
        max_cases=max_cases,
        max_case_pack_bytes=max_case_pack_bytes,
    )
    write_json(candidate_queue_output, candidate_queue)
    write_json(case_pack_output, case_pack)
    label = label_artifact["labels"][0]
    summary = {
        "status": "ready" if "fail" not in {candidate_queue.get("status"), case_pack.get("status")} else "fail",
        "candidate_queue": relative_label(root, candidate_queue_output),
        "candidate_queue_status": candidate_queue.get("status"),
        "operator_label": relative_label(root, operator_label_output),
        "operator_label_id": label.get("label_id"),
        "operator_label_matched": label_artifact.get("source", {}).get("matched"),
        "operator_labels_applied": candidate_queue.get("source_summary", {}).get("operator_labels_applied", 0),
        "case_pack": relative_label(root, case_pack_output),
        "case_pack_status": case_pack.get("status"),
        "cases_total": case_pack.get("summary", {}).get("cases_total", 0),
        "manual_review_required": candidate_queue.get("source_summary", {}).get("manual_review_required", 0),
        "ready_for_prompt_eval": candidate_queue.get("source_summary", {}).get("ready_for_prompt_eval", 0),
    }
    return candidate_queue, label_artifact, case_pack, summary


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    root = resolve_path(Path.cwd(), args.root).resolve()
    agents_sdk_logs = [resolve_path(root, path) for path in args.agents_sdk_log]
    nova_agent_logs = [resolve_path(root, path) for path in args.nova_agent_log]
    action_logs = [resolve_path(root, path) for path in args.action_log]
    candidate_queue_output = resolve_path(root, args.candidate_queue_output)
    operator_label_output = resolve_path(root, args.operator_label_output)
    case_pack_output = resolve_path(root, args.case_pack_output)
    try:
        operator_feedback_summary: dict[str, Any] = {}
        if args.from_operator_feedback:
            feedback_events, read_summary = read_operator_feedback_events(action_logs)
            feedback_inputs, operator_feedback_summary = operator_feedback_inputs(
                feedback_events,
                feedback_id=args.feedback_id,
            )
            operator_feedback_summary.update(read_summary)
            expected = feedback_inputs["expected"]
            candidate_id = args.candidate_id or feedback_inputs["candidate_id"]
            prompt = args.prompt or feedback_inputs["prompt"]
            source_kind = args.source_kind or feedback_inputs["source_kind"]
            case_hint = args.case_hint or feedback_inputs["case_hint"]
            label_id = args.label_id or feedback_inputs["label_id"]
        else:
            if not args.build_kind or not args.build_material_name:
                raise operator_label.OperatorLabelError(
                    "--build-kind and --build-material-name are required unless --from-operator-feedback is used"
                )
            expected = operator_label.expected_build_behavior(
                build_kind=args.build_kind,
                build_material_name=args.build_material_name,
                build_material_node=args.build_material_node,
                planned_node_writes=args.planned_node_writes,
                route=args.route,
                danger_refusal_allowed=args.danger_refusal_allowed,
                forbidden_extra_structure=args.forbidden_extra_structure,
            )
            candidate_id = args.candidate_id
            prompt = args.prompt
            source_kind = args.source_kind
            case_hint = args.case_hint
            label_id = args.label_id
        _, _, _, summary = build_feedback_packet(
            root=root,
            agents_sdk_logs=agents_sdk_logs,
            nova_agent_logs=nova_agent_logs,
            action_logs=action_logs,
            candidate_queue_output=candidate_queue_output,
            operator_label_output=operator_label_output,
            case_pack_output=case_pack_output,
            candidate_id=candidate_id,
            prompt=prompt,
            source_kind=source_kind,
            case_hint=case_hint,
            label_id=label_id,
            expected=expected,
            allow_unmatched=args.allow_unmatched,
            generated_at=args.generated_at,
            max_candidates=args.max_candidates,
            max_candidate_queue_bytes=args.max_candidate_queue_bytes,
            max_cases=args.max_cases,
            max_case_pack_bytes=args.max_case_pack_bytes,
        )
        summary.update(operator_feedback_summary)
    except operator_label.OperatorLabelError as exc:
        print(json.dumps({"status": "fail", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(summary, sort_keys=True))
    return 0 if summary.get("status") != "fail" else 1


if __name__ == "__main__":
    raise SystemExit(main())
