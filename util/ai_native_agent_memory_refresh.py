#!/usr/bin/env python3
"""Refresh the reviewed prompt-memory artifacts used by the Agents SDK sidecar."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


sys.path.insert(0, str(Path(__file__).resolve().parent))
import ai_native_agent_eval_promote as eval_promote
import ai_native_agent_eval_queue as eval_queue
import ai_native_agent_operator_feedback as operator_feedback
import ai_native_agent_review_queue as review_queue


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return root / path


def relative_label(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_memory_artifacts(
    *,
    agents_sdk_logs: list[Path] | None = None,
    nova_agent_logs: list[Path] | None = None,
    action_logs: list[Path] | None = None,
    verified_live_probe_paths: list[Path] | None = None,
    operator_label_files: list[Path] | None = None,
    from_operator_feedback: bool = False,
    feedback_id: str | None = None,
    generated_at: str | None = None,
    candidate_queue_source_path: str | None = None,
    max_candidates: int = eval_queue.DEFAULT_MAX_CANDIDATES,
    max_candidate_queue_bytes: int = eval_queue.DEFAULT_MAX_BYTES,
    max_cases: int = eval_promote.DEFAULT_MAX_CASES,
    max_case_pack_bytes: int = eval_promote.DEFAULT_MAX_BYTES,
    auto_default_gate_min_sources: int = eval_promote.DEFAULT_AUTO_DEFAULT_GATE_MIN_SOURCES,
) -> tuple[dict[str, Any], dict[str, Any]]:
    candidate_queue_path = candidate_queue_source_path or "ai-agent-eval-candidate-queue.json"
    operator_label_payloads: list[dict[str, Any]] = []
    operator_feedback_summary: dict[str, int] = {}
    if from_operator_feedback:
        feedback_events, read_summary = operator_feedback.read_operator_feedback_events(action_logs or [])
        feedback_payloads, payload_summary = operator_feedback.operator_feedback_label_payloads(
            feedback_events,
            candidate_queue_path=candidate_queue_path,
            generated_at=generated_at,
            feedback_id=feedback_id,
        )
        operator_label_payloads = feedback_payloads
        operator_feedback_summary.update(read_summary)
        operator_feedback_summary.update(payload_summary)
    candidate_queue = eval_queue.build_eval_candidate_queue(
        agents_sdk_logs=agents_sdk_logs or [],
        nova_agent_logs=nova_agent_logs or [],
        action_logs=action_logs or [],
        verified_live_probe_paths=verified_live_probe_paths or [],
        operator_label_files=operator_label_files or [],
        operator_label_payloads=operator_label_payloads,
        generated_at=generated_at,
        max_candidates=max(0, max_candidates),
        max_bytes=max(1000, max_candidate_queue_bytes),
    )
    if operator_feedback_summary:
        candidate_queue.setdefault("source_summary", {}).update(operator_feedback_summary)
    case_pack = eval_promote.build_case_pack(
        candidate_queue,
        generated_at=generated_at,
        source_path=candidate_queue_source_path,
        max_cases=max(0, max_cases),
        max_bytes=max(1000, max_case_pack_bytes),
        auto_default_gate_min_sources=max(1, auto_default_gate_min_sources),
    )
    return candidate_queue, case_pack


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh public-safe sidecar memory artifacts from Nova/Agents logs.",
    )
    parser.add_argument("--root", default=".", help="Repository root for relative paths.")
    parser.add_argument("--agents-sdk-log", action="append", default=[], help="Agents SDK adapter JSONL log path.")
    parser.add_argument("--nova-agent-log", action="append", default=[], help="Nova sidecar request JSONL log path.")
    parser.add_argument("--action-log", action="append", default=[], help="Luanti action/debug log path containing request_trace JSON.")
    parser.add_argument("--verified-live-probe", action="append", default=[], help="Verified Nova auto-apply live probe JSON file or directory.")
    parser.add_argument("--operator-labels", action="append", default=[], help="Reviewed operator label JSON path.")
    parser.add_argument(
        "--from-operator-feedback",
        action="store_true",
        help="Harvest public-safe ai_agent_operator_feedback events from action logs as reviewed labels.",
    )
    parser.add_argument("--feedback-id", default=None, help="Specific ai_agent_operator_feedback feedback_id to harvest.")
    parser.add_argument("--candidate-queue-output", required=True, help="Output candidate queue JSON path.")
    parser.add_argument("--case-pack-output", required=True, help="Output prompt-memory case pack JSON path.")
    parser.add_argument("--review-output", default=None, help="Optional output Nova agent review queue JSON path.")
    parser.add_argument("--generated-at", default=None, help="ISO timestamp for deterministic artifacts.")
    parser.add_argument("--max-candidates", type=int, default=eval_queue.DEFAULT_MAX_CANDIDATES)
    parser.add_argument("--max-candidate-queue-bytes", type=int, default=eval_queue.DEFAULT_MAX_BYTES)
    parser.add_argument("--max-cases", type=int, default=eval_promote.DEFAULT_MAX_CASES)
    parser.add_argument("--max-case-pack-bytes", type=int, default=eval_promote.DEFAULT_MAX_BYTES)
    parser.add_argument(
        "--auto-default-gate-min-sources",
        type=int,
        default=eval_promote.DEFAULT_AUTO_DEFAULT_GATE_MIN_SOURCES,
        help="Independent trusted source kinds required before prompt memory is default-gate eligible.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    root = resolve_path(Path.cwd(), args.root).resolve()
    agents_sdk_logs = [resolve_path(root, path) for path in args.agents_sdk_log]
    nova_agent_logs = [resolve_path(root, path) for path in args.nova_agent_log]
    action_logs = [resolve_path(root, path) for path in args.action_log]
    verified_live_probe_paths = [resolve_path(root, path) for path in args.verified_live_probe]
    operator_label_files = [resolve_path(root, path) for path in args.operator_labels]
    candidate_queue_output = resolve_path(root, args.candidate_queue_output)
    case_pack_output = resolve_path(root, args.case_pack_output)
    review_output = resolve_path(root, args.review_output) if args.review_output else None

    candidate_queue, case_pack = build_memory_artifacts(
        agents_sdk_logs=agents_sdk_logs,
        nova_agent_logs=nova_agent_logs,
        action_logs=action_logs,
        verified_live_probe_paths=verified_live_probe_paths,
        operator_label_files=operator_label_files,
        from_operator_feedback=args.from_operator_feedback,
        feedback_id=args.feedback_id,
        generated_at=args.generated_at,
        candidate_queue_source_path=relative_label(root, candidate_queue_output),
        max_candidates=args.max_candidates,
        max_candidate_queue_bytes=args.max_candidate_queue_bytes,
        max_cases=args.max_cases,
        max_case_pack_bytes=args.max_case_pack_bytes,
        auto_default_gate_min_sources=args.auto_default_gate_min_sources,
    )
    write_json(candidate_queue_output, candidate_queue)
    write_json(case_pack_output, case_pack)
    review_report: dict[str, Any] | None = None
    if review_output is not None:
        review_report = review_queue.build_review_queue(
            candidate_queue,
            case_pack,
            generated_at=args.generated_at,
            candidate_queue_path=relative_label(root, candidate_queue_output),
            case_pack_path=relative_label(root, case_pack_output),
        )
        write_json(review_output, review_report)

    summary = {
        "candidate_queue": relative_label(root, candidate_queue_output),
        "candidate_queue_status": candidate_queue.get("status"),
        "adapter_contract_failures": candidate_queue.get("source_summary", {}).get(
            "adapter_contract_failures", 0
        ),
        "adapter_contract_failures_active": candidate_queue.get("source_summary", {}).get(
            "adapter_contract_failures_active", 0
        ),
        "adapter_contract_failures_total": candidate_queue.get("source_summary", {}).get(
            "adapter_contract_failures_total", 0
        ),
        "adapter_contract_failures_resolved": candidate_queue.get("source_summary", {}).get(
            "adapter_contract_failures_resolved", 0
        ),
        "ready_for_adapter_contract_eval": candidate_queue.get("source_summary", {}).get(
            "ready_for_adapter_contract_eval", 0
        ),
        "operator_labels_read": candidate_queue.get("source_summary", {}).get(
            "operator_labels_read", 0
        ),
        "operator_labels_applied": candidate_queue.get("source_summary", {}).get(
            "operator_labels_applied", 0
        ),
        "operator_feedback_events_read": candidate_queue.get("source_summary", {}).get(
            "operator_feedback_events_read", 0
        ),
        "operator_feedback_labels_generated": candidate_queue.get("source_summary", {}).get(
            "operator_feedback_labels_generated", 0
        ),
        "verified_live_probe_files_read": candidate_queue.get("source_summary", {}).get(
            "verified_live_probe_files_read", 0
        ),
        "verified_live_probe_cases_read": candidate_queue.get("source_summary", {}).get(
            "verified_live_probe_cases_read", 0
        ),
        "verified_live_probe_candidates_added": candidate_queue.get("source_summary", {}).get(
            "verified_live_probe_candidates_added", 0
        ),
        "case_pack": relative_label(root, case_pack_output),
        "case_pack_status": case_pack.get("status"),
        "cases_total": case_pack.get("summary", {}).get("cases_total", 0),
        "default_gate_eligible_cases": case_pack.get("summary", {}).get(
            "default_gate_eligible_cases",
            0,
        ),
        "review_required_cases": case_pack.get("summary", {}).get(
            "review_required_cases",
            0,
        ),
    }
    if review_report is not None and review_output is not None:
        summary.update({
            "review_queue": relative_label(root, review_output),
            "review_queue_status": review_report.get("status"),
            "review_items_total": review_report.get("summary", {}).get(
                "review_items_total", 0
            ),
            "review_action_items_total": review_report.get("summary", {}).get(
                "action_items_total", 0
            ),
            "manual_review_required": review_report.get("summary", {}).get(
                "manual_review_required", 0
            ),
        })
    print(json.dumps(summary, sort_keys=True))
    statuses = {candidate_queue.get("status"), case_pack.get("status")}
    if review_report is not None:
        statuses.add(review_report.get("status"))
    return 0 if "fail" not in statuses else 1


if __name__ == "__main__":
    raise SystemExit(main())
