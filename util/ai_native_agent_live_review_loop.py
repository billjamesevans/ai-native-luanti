#!/usr/bin/env python3
"""Convert a live Studio trace into reviewed eval artifacts in one command."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ai_native_agent_feedback_packet as feedback_packet
import ai_native_agent_eval_queue as eval_queue
import ai_native_agent_operator_label as operator_label
import ai_native_agent_studio_review_packet as studio_review_packet


class LiveReviewLoopError(ValueError):
    """Raised when the live review loop cannot safely produce artifacts."""


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


def artifact_prefix_from_packet(packet: dict[str, Any], override: str | None) -> str:
    if override:
        return operator_label.slug(override, fallback="openrealm_live_review")
    source = packet.get("source") if isinstance(packet.get("source"), dict) else {}
    source_trace_id = source.get("source_trace_id")
    selected_option_id = source.get("selected_option_id")
    return operator_label.slug(
        str(source_trace_id or selected_option_id or "openrealm_live_review"),
        fallback="openrealm_live_review",
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a Studio review packet from public-safe status telemetry and "
            "immediately build reviewed eval artifacts from runtime logs."
        ),
    )
    parser.add_argument("--root", default=".", help="Repository root for relative paths.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--status-json", default=None, help="Path to a saved Studio /api/status JSON file.")
    source.add_argument("--status-url", default=None, help="URL for a Studio /api/status endpoint.")
    parser.add_argument("--agents-sdk-log", action="append", default=[], help="Agents SDK adapter JSONL log path.")
    parser.add_argument("--nova-agent-log", action="append", default=[], help="Nova sidecar request JSONL log path.")
    parser.add_argument("--action-log", action="append", default=[], help="Luanti action/debug log with request_trace JSON.")
    parser.add_argument("--trace-id", default=None, help="Specific source_trace_id to export, such as nova_trace:11.")
    parser.add_argument("--task-id", default=None, help="Specific task_id to export.")
    parser.add_argument("--selected-option-id", default=None, help="Specific selected_option_id to export.")
    parser.add_argument("--trace-index", type=int, default=None, help="Zero-based index among reviewable traces.")
    parser.add_argument("--case-hint", default=None, help="Override prompt-memory case hint.")
    parser.add_argument("--build-kind", default=None, help="Override expected build kind.")
    parser.add_argument("--build-material-name", default=None, help="Override expected material.")
    parser.add_argument("--planned-node-writes", type=int, default=None, help="Override expected planned write count.")
    parser.add_argument("--allow-unmatched", action="store_true", help="Create the label even if no candidate matches.")
    parser.add_argument("--output-dir", default="local/review-packets/live-review", help="Directory for output artifacts.")
    parser.add_argument("--artifact-prefix", default=None, help="Stable output filename prefix.")
    parser.add_argument("--generated-at", default=None, help="ISO timestamp for deterministic artifacts.")
    parser.add_argument("--max-candidates", type=int, default=eval_queue.DEFAULT_MAX_CANDIDATES)
    parser.add_argument("--max-candidate-queue-bytes", type=int, default=eval_queue.DEFAULT_MAX_BYTES)
    parser.add_argument("--max-cases", type=int, default=25)
    parser.add_argument("--max-case-pack-bytes", type=int, default=24000)
    return parser.parse_args(argv)


def build_live_review_loop(
    *,
    root: Path,
    status_json: Path | None,
    status_url: str | None,
    agents_sdk_logs: list[Path],
    nova_agent_logs: list[Path],
    action_logs: list[Path],
    output_dir: Path,
    artifact_prefix: str | None,
    trace_id: str | None,
    task_id: str | None,
    selected_option_id: str | None,
    trace_index: int | None,
    case_hint: str | None,
    build_kind: str | None,
    build_material_name: str | None,
    planned_node_writes: int | None,
    allow_unmatched: bool,
    generated_at: str | None,
    max_candidates: int,
    max_candidate_queue_bytes: int,
    max_cases: int,
    max_case_pack_bytes: int,
) -> dict[str, Any]:
    if not (agents_sdk_logs or nova_agent_logs or action_logs):
        raise LiveReviewLoopError("at least one runtime log path is required")
    status = studio_review_packet.load_status_json(status_json, status_url)
    packet = studio_review_packet.build_review_packet(
        status,
        trace_id=trace_id,
        task_id=task_id,
        selected_option_id=selected_option_id,
        trace_index=trace_index,
        case_hint=case_hint,
        build_kind=build_kind,
        build_material_name=build_material_name,
        planned_node_writes=planned_node_writes,
        generated_at=generated_at,
    )
    expected = feedback_packet.expected_from_studio_review_packet(packet)
    resolved_case_hint = feedback_packet.case_hint_from_studio_review_packet(packet, expected)
    prefix = artifact_prefix_from_packet(packet, artifact_prefix)
    review_packet_output = output_dir / f"{prefix}-studio-review-packet.json"
    candidate_queue_output = output_dir / f"{prefix}-candidate-queue.json"
    operator_label_output = output_dir / f"{prefix}-operator-labels.json"
    case_pack_output = output_dir / f"{prefix}-case-pack.json"
    write_json(review_packet_output, packet)
    _, _, _, feedback_summary = feedback_packet.build_feedback_packet(
        root=root,
        agents_sdk_logs=agents_sdk_logs,
        nova_agent_logs=nova_agent_logs,
        action_logs=action_logs,
        candidate_queue_output=candidate_queue_output,
        operator_label_output=operator_label_output,
        case_pack_output=case_pack_output,
        candidate_id=None,
        prompt=None,
        source_kind=None,
        case_hint=resolved_case_hint,
        label_id=None,
        expected=expected,
        allow_unmatched=allow_unmatched,
        generated_at=generated_at,
        max_candidates=max_candidates,
        max_candidate_queue_bytes=max_candidate_queue_bytes,
        max_cases=max_cases,
        max_case_pack_bytes=max_case_pack_bytes,
        studio_review_packet=packet,
    )
    summary = {
        "status": feedback_summary.get("status"),
        "review_packet": relative_label(root, review_packet_output),
        "source_trace_id": packet.get("source", {}).get("source_trace_id"),
        "selected_option_id": packet.get("source", {}).get("selected_option_id"),
        "case_hint": resolved_case_hint,
        "operator_feedback_command": packet.get("operator_feedback_command"),
    }
    summary.update(feedback_summary)
    if summary.get("status") != "ready":
        raise LiveReviewLoopError("review loop produced non-ready artifacts")
    return summary


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    root = resolve_path(Path.cwd(), args.root).resolve()
    try:
        summary = build_live_review_loop(
            root=root,
            status_json=resolve_path(root, args.status_json) if args.status_json else None,
            status_url=args.status_url,
            agents_sdk_logs=[resolve_path(root, path) for path in args.agents_sdk_log],
            nova_agent_logs=[resolve_path(root, path) for path in args.nova_agent_log],
            action_logs=[resolve_path(root, path) for path in args.action_log],
            output_dir=resolve_path(root, args.output_dir),
            artifact_prefix=args.artifact_prefix,
            trace_id=args.trace_id,
            task_id=args.task_id,
            selected_option_id=args.selected_option_id,
            trace_index=args.trace_index,
            case_hint=args.case_hint,
            build_kind=args.build_kind,
            build_material_name=args.build_material_name,
            planned_node_writes=args.planned_node_writes,
            allow_unmatched=args.allow_unmatched,
            generated_at=args.generated_at,
            max_candidates=args.max_candidates,
            max_candidate_queue_bytes=args.max_candidate_queue_bytes,
            max_cases=args.max_cases,
            max_case_pack_bytes=args.max_case_pack_bytes,
        )
    except (LiveReviewLoopError, studio_review_packet.StudioReviewPacketError, operator_label.OperatorLabelError) as exc:
        print(json.dumps({"status": "fail", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
