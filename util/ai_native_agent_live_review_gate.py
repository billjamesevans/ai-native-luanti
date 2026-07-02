#!/usr/bin/env python3
"""Gate the live Studio review loop and validate all generated artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ai_native_agent_eval_promote as eval_promote
import ai_native_agent_eval_queue as eval_queue
import ai_native_agent_live_review_loop as live_review_loop
import ai_native_agent_operator_label as operator_label
import ai_native_agent_studio_review_packet as studio_review_packet


class LiveReviewGateError(ValueError):
    """Raised when a live review gate check fails."""


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return root / path


def relative_label(root: Path, path: Path) -> str:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    return resolved_path.relative_to(resolved_root).as_posix() if resolved_path.is_relative_to(resolved_root) else path.name


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_json(path: Path, label: str, checks: dict[str, bool], violations: list[dict[str, str]]) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        checks[f"{label}_exists"] = False
        violations.append({"kind": f"{label}_missing", "details": str(path)})
        return {}
    except json.JSONDecodeError:
        checks[f"{label}_valid_json"] = False
        violations.append({"kind": f"{label}_invalid_json", "details": str(path)})
        return {}
    if not isinstance(payload, dict):
        checks[f"{label}_json_object"] = False
        violations.append({"kind": f"{label}_not_object", "details": str(path)})
        return {}
    checks[f"{label}_exists"] = True
    checks[f"{label}_valid_json"] = True
    checks[f"{label}_json_object"] = True
    return payload


def assert_public_safe(label: str, payload: dict[str, Any], checks: dict[str, bool], violations: list[dict[str, str]]) -> None:
    safe = not eval_queue.has_private_content(payload) and not eval_queue.has_forbidden_key(payload)
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    public_flag = safety.get("public_safe_output") is True
    checks[f"{label}_public_safe"] = safe and public_flag
    if not checks[f"{label}_public_safe"]:
        violations.append({"kind": f"{label}_not_public_safe", "details": label})


def artifact_path(root: Path, summary: dict[str, Any], key: str) -> Path:
    value = summary.get(key)
    if not isinstance(value, str) or not value:
        raise LiveReviewGateError(f"review loop summary missing {key}")
    return resolve_path(root, value)


def validate_review_artifacts(root: Path, summary: dict[str, Any]) -> dict[str, Any]:
    checks: dict[str, bool] = {
        "review_loop_status_ready": summary.get("status") == "ready",
        "operator_label_matched": summary.get("operator_label_matched") is True,
        "operator_labels_applied": int(summary.get("operator_labels_applied") or 0) >= 1,
        "case_pack_ready": summary.get("case_pack_status") == "ready",
        "candidate_queue_ready": summary.get("candidate_queue_status") == "ready",
    }
    violations: list[dict[str, str]] = []
    if not checks["review_loop_status_ready"]:
        violations.append({"kind": "review_loop_not_ready", "details": str(summary.get("status"))})
    for key in ("operator_label_matched", "operator_labels_applied", "case_pack_ready", "candidate_queue_ready"):
        if not checks[key]:
            violations.append({"kind": key, "details": "summary check failed"})

    review_packet_path = artifact_path(root, summary, "review_packet")
    candidate_queue_path = artifact_path(root, summary, "candidate_queue")
    operator_label_path = artifact_path(root, summary, "operator_label")
    case_pack_path = artifact_path(root, summary, "case_pack")

    review_packet = load_json(review_packet_path, "review_packet", checks, violations)
    operator_labels = load_json(operator_label_path, "operator_labels", checks, violations)
    candidate_queue = load_json(candidate_queue_path, "candidate_queue", checks, violations)
    case_pack = load_json(case_pack_path, "case_pack", checks, violations)

    for label, payload in (
        ("review_packet", review_packet),
        ("operator_labels", operator_labels),
        ("candidate_queue", candidate_queue),
        ("case_pack", case_pack),
    ):
        if payload:
            assert_public_safe(label, payload, checks, violations)

    checks["review_packet_kind"] = review_packet.get("artifact_kind") == studio_review_packet.STUDIO_REVIEW_PACKET_KIND
    checks["operator_labels_kind"] = operator_labels.get("artifact_kind") == eval_queue.OPERATOR_LABEL_KIND
    checks["candidate_queue_kind"] = candidate_queue.get("artifact_kind") == eval_queue.REPORT_KIND
    checks["case_pack_kind"] = case_pack.get("artifact_kind") == eval_promote.CASE_PACK_KIND

    if not checks["review_packet_kind"]:
        violations.append({"kind": "review_packet_kind", "details": str(review_packet.get("artifact_kind"))})
    if not checks["operator_labels_kind"]:
        violations.append({"kind": "operator_labels_kind", "details": str(operator_labels.get("artifact_kind"))})
    if not checks["candidate_queue_kind"]:
        violations.append({"kind": "candidate_queue_kind", "details": str(candidate_queue.get("artifact_kind"))})
    if not checks["case_pack_kind"]:
        violations.append({"kind": "case_pack_kind", "details": str(case_pack.get("artifact_kind"))})

    labels = operator_labels.get("labels") if isinstance(operator_labels.get("labels"), list) else []
    first_label = labels[0] if labels and isinstance(labels[0], dict) else {}
    safe_expected = eval_queue.safe_expected_from_operator_label(first_label.get("expected"))
    checks["operator_label_expected_valid"] = safe_expected is not None
    if safe_expected is None:
        violations.append({"kind": "operator_label_expected_invalid", "details": "expected"})

    label_source = operator_labels.get("source") if isinstance(operator_labels.get("source"), dict) else {}
    matched_candidate_id = label_source.get("matched_candidate_id")
    candidates = candidate_queue.get("candidates") if isinstance(candidate_queue.get("candidates"), list) else []
    checks["matched_candidate_in_queue"] = (
        isinstance(matched_candidate_id, str)
        and any(isinstance(candidate, dict) and candidate.get("candidate_id") == matched_candidate_id for candidate in candidates)
    )
    if not checks["matched_candidate_in_queue"]:
        violations.append({"kind": "matched_candidate_not_in_queue", "details": str(matched_candidate_id)})

    case_summary = case_pack.get("summary") if isinstance(case_pack.get("summary"), dict) else {}
    checks["case_pack_has_cases"] = int(case_summary.get("cases_total") or 0) >= 1
    if not checks["case_pack_has_cases"]:
        violations.append({"kind": "case_pack_empty", "details": str(case_summary.get("cases_total"))})

    status = "pass" if all(checks.values()) and not violations else "fail"
    return {
        "schema_version": 1,
        "artifact_kind": "openrealm_live_review_gate_result",
        "status": status,
        "source_trace_id": summary.get("source_trace_id"),
        "selected_option_id": summary.get("selected_option_id"),
        "case_hint": summary.get("case_hint"),
        "artifacts": {
            "review_packet": relative_label(root, review_packet_path),
            "candidate_queue": relative_label(root, candidate_queue_path),
            "operator_label": relative_label(root, operator_label_path),
            "case_pack": relative_label(root, case_pack_path),
        },
        "checks": checks,
        "violations": violations,
        "summary": summary,
        "safety": {
            "public_safe_output": status == "pass",
            "no_world_mutation": True,
            "no_raw_assets": True,
            "no_provider_prompts": True,
            "no_family_world_coordinates": True,
        },
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the live Studio review loop and gate the generated public-safe eval artifacts.",
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
    parser.add_argument("--gate-output", default=None, help="Optional gate result JSON path.")
    parser.add_argument("--generated-at", default=None, help="ISO timestamp for deterministic artifacts.")
    parser.add_argument("--max-candidates", type=int, default=eval_queue.DEFAULT_MAX_CANDIDATES)
    parser.add_argument("--max-candidate-queue-bytes", type=int, default=eval_queue.DEFAULT_MAX_BYTES)
    parser.add_argument("--max-cases", type=int, default=25)
    parser.add_argument("--max-case-pack-bytes", type=int, default=24000)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    root = resolve_path(Path.cwd(), args.root).resolve()
    try:
        summary = live_review_loop.build_live_review_loop(
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
        gate = validate_review_artifacts(root, summary)
        if args.gate_output:
            write_json(resolve_path(root, args.gate_output), gate)
    except (
        LiveReviewGateError,
        live_review_loop.LiveReviewLoopError,
        studio_review_packet.StudioReviewPacketError,
        operator_label.OperatorLabelError,
    ) as exc:
        print(json.dumps({"status": "fail", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(gate, sort_keys=True))
    return 0 if gate.get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
