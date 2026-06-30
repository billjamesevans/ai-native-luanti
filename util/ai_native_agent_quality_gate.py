#!/usr/bin/env python3
"""Build one public-safe quality gate artifact for the Nova agent loop."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any


sys.path.insert(0, str(Path(__file__).resolve().parent))
import ai_native_agent_adapter_contract_eval as adapter_contract_eval
import ai_native_agent_eval_promote as eval_promote
import ai_native_agent_eval_queue as eval_queue
import ai_native_agent_prompt_eval_live_probe as prompt_eval_live_probe
import ai_native_agent_review_queue as review_queue
import ai_native_compat_import_staging_pilot as compat_import_staging_pilot


REPORT_KIND = "ai_native_agent_quality_gate"
DEFAULT_MAX_BYTES = 24000
PASSING_ADAPTER_EVAL_STATUSES = {"pass", "empty"}
BLOCKING_ATTENTION_KINDS = {
    "candidate_queue_not_ready",
    "case_pack_not_ready",
    "adapter_contract_replay_missing",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return root / path


def relative_label(root: Path, path: Path | None) -> str | None:
    if path is None:
        return None
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)


def bounded_text(value: Any, max_bytes: int = 1000) -> str | None:
    if value is None:
        return None
    text = str(value)
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def load_json(path: Path) -> tuple[dict[str, Any], str | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, "missing"
    except json.JSONDecodeError:
        return {}, "invalid_json"
    except OSError as exc:
        return {}, exc.__class__.__name__
    if not isinstance(payload, dict):
        return {}, "not_object"
    return payload, None


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _int(value: Any, default: int = 0) -> int:
    return value if isinstance(value, int) else default


def _list_len(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def _source_summary(candidate_queue: dict[str, Any]) -> dict[str, Any]:
    summary = candidate_queue.get("source_summary")
    return summary if isinstance(summary, dict) else {}


def _case_pack_summary(case_pack: dict[str, Any]) -> dict[str, Any]:
    summary = case_pack.get("summary")
    return summary if isinstance(summary, dict) else {}


def _review_summary(review: dict[str, Any]) -> dict[str, Any]:
    summary = review.get("summary")
    return summary if isinstance(summary, dict) else {}


def _adapter_summary(adapter_eval: dict[str, Any]) -> dict[str, Any]:
    summary = adapter_eval.get("summary")
    return summary if isinstance(summary, dict) else {}


def _prompt_eval_summary(live_prompt_eval: dict[str, Any]) -> dict[str, Any]:
    summary = live_prompt_eval.get("summary")
    return summary if isinstance(summary, dict) else {}


def _violations(payload: dict[str, Any]) -> list[Any]:
    violations = payload.get("violations")
    return violations if isinstance(violations, list) else []


def _action_items(payload: dict[str, Any]) -> list[Any]:
    action_items = payload.get("action_items")
    return action_items if isinstance(action_items, list) else []


def _artifact_private(payload: dict[str, Any]) -> bool:
    return eval_queue.has_private_content(payload) or eval_queue.has_forbidden_key(payload)


def build_quality_gate(
    *,
    candidate_queue: dict[str, Any],
    case_pack: dict[str, Any],
    review: dict[str, Any],
    adapter_eval: dict[str, Any] | None = None,
    live_prompt_eval: dict[str, Any] | None = None,
    compat_import_pilot: dict[str, Any] | None = None,
    generated_at: str | None = None,
    candidate_queue_path: str | None = None,
    case_pack_path: str | None = None,
    review_queue_path: str | None = None,
    adapter_contract_eval_path: str | None = None,
    live_prompt_eval_path: str | None = None,
    compat_import_pilot_path: str | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict[str, Any]:
    generated_at = generated_at or utc_now()
    adapter_eval = adapter_eval or {}
    live_prompt_eval = live_prompt_eval or {}
    compat_import_pilot = compat_import_pilot or {}
    violations: list[dict[str, str]] = []
    attention: list[dict[str, Any]] = []

    if candidate_queue.get("artifact_kind") != eval_queue.REPORT_KIND:
        violations.append({"kind": "invalid_candidate_queue_kind", "details": str(candidate_queue.get("artifact_kind"))})
    if case_pack.get("artifact_kind") != eval_promote.CASE_PACK_KIND:
        violations.append({"kind": "invalid_case_pack_kind", "details": str(case_pack.get("artifact_kind"))})
    if review.get("artifact_kind") != review_queue.REVIEW_KIND:
        violations.append({"kind": "invalid_review_queue_kind", "details": str(review.get("artifact_kind"))})
    if adapter_eval and adapter_eval.get("artifact_kind") != adapter_contract_eval.REPORT_KIND:
        violations.append({
            "kind": "invalid_adapter_contract_eval_kind",
            "details": str(adapter_eval.get("artifact_kind")),
        })

    for name, payload in (
        ("candidate_queue", candidate_queue),
        ("case_pack", case_pack),
        ("review_queue", review),
        ("adapter_contract_eval", adapter_eval),
        ("live_prompt_eval", live_prompt_eval),
        ("compat_import_staging_pilot", compat_import_pilot),
    ):
        if payload and _artifact_private(payload):
            violations.append({"kind": f"{name}_not_public_safe", "details": "private or forbidden content"})

    candidate_summary = _source_summary(candidate_queue)
    case_summary = _case_pack_summary(case_pack)
    review_summary = _review_summary(review)
    adapter_summary = _adapter_summary(adapter_eval)
    live_prompt_summary = _prompt_eval_summary(live_prompt_eval)

    active_contract_failures = _int(
        candidate_summary.get("adapter_contract_failures_active"),
        _int(candidate_summary.get("adapter_contract_failures")),
    )
    ready_for_adapter_contract_eval = _int(candidate_summary.get("ready_for_adapter_contract_eval"))
    manual_review_required = _int(candidate_summary.get("manual_review_required"))
    case_count = _int(case_summary.get("cases_total"))
    review_items_total = _int(review_summary.get("review_items_total"), _list_len(review.get("review_items")))
    review_action_items_total = _int(review_summary.get("action_items_total"), _list_len(_action_items(review)))

    if candidate_queue.get("status") != "ready":
        attention.append({"kind": "candidate_queue_not_ready", "status": bounded_text(candidate_queue.get("status"), 80)})
    if case_pack.get("status") != "ready" or case_count <= 0:
        attention.append({
            "kind": "case_pack_not_ready",
            "status": bounded_text(case_pack.get("status"), 80),
            "cases_total": case_count,
        })
    if review.get("status") != "ready":
        attention.append({"kind": "review_queue_not_ready", "status": bounded_text(review.get("status"), 80)})
    if _violations(candidate_queue) or _violations(case_pack) or _violations(review):
        violations.append({"kind": "source_artifact_violations", "details": "candidate/case/review violations present"})
    if manual_review_required or review_items_total:
        attention.append({
            "kind": "manual_review_required",
            "candidate_count": max(manual_review_required, review_items_total),
        })
    if review_action_items_total or _action_items(review):
        attention.append({
            "kind": "review_action_items_pending",
            "action_items_total": max(review_action_items_total, _list_len(_action_items(review))),
        })

    adapter_eval_status = adapter_eval.get("status") if adapter_eval else None
    if active_contract_failures:
        violations.append({
            "kind": "active_adapter_contract_failures",
            "details": str(active_contract_failures),
        })
    if ready_for_adapter_contract_eval and not adapter_eval:
        attention.append({
            "kind": "adapter_contract_replay_missing",
            "candidate_count": ready_for_adapter_contract_eval,
        })
    if adapter_eval:
        if adapter_eval_status not in PASSING_ADAPTER_EVAL_STATUSES:
            violations.append({
                "kind": "adapter_contract_eval_not_passing",
                "details": str(adapter_eval_status),
            })
        if _violations(adapter_eval):
            violations.append({"kind": "adapter_contract_eval_violations", "details": str(len(_violations(adapter_eval)))})
    live_prompt_eval_status = None
    live_prompt_evidence: dict[str, Any] = {}
    if live_prompt_eval:
        try:
            live_prompt_evidence = prompt_eval_live_probe.validate_live_result(live_prompt_eval)
        except ValueError as exc:
            live_prompt_eval_status = "fail"
            violations.append({
                "kind": "live_prompt_eval_not_passing",
                "details": bounded_text(exc, 240) or "invalid live prompt eval",
            })
        else:
            live_prompt_eval_status = "pass"

    compat_import_status = None
    compat_import_evidence: dict[str, Any] = {}
    if compat_import_pilot:
        try:
            compat_import_evidence = compat_import_staging_pilot.validate_live_result(compat_import_pilot)
        except ValueError as exc:
            compat_import_status = "fail"
            violations.append({
                "kind": "compat_import_staging_pilot_not_passing",
                "details": bounded_text(exc, 240) or "invalid compat import staging pilot",
            })
        else:
            compat_import_status = "pass"

    blocking_attention = [
        item
        for item in attention
        if isinstance(item, dict) and item.get("kind") in BLOCKING_ATTENTION_KINDS
    ]

    status = "pass"
    if blocking_attention:
        status = "attention"
    if violations:
        status = "fail"

    payload = {
        "schema_version": 1,
        "artifact_kind": REPORT_KIND,
        "generated_at": generated_at,
        "status": status,
        "source": {
            "candidate_queue_path": candidate_queue_path,
            "case_pack_path": case_pack_path,
            "review_queue_path": review_queue_path,
            "adapter_contract_eval_path": adapter_contract_eval_path,
            "live_prompt_eval_path": live_prompt_eval_path,
            "compat_import_staging_pilot_path": compat_import_pilot_path,
        },
        "summary": {
            "candidate_queue_status": bounded_text(candidate_queue.get("status"), 80),
            "case_pack_status": bounded_text(case_pack.get("status"), 80),
            "review_queue_status": bounded_text(review.get("status"), 80),
            "adapter_contract_eval_status": bounded_text(adapter_eval_status, 80),
            "live_prompt_eval_status": bounded_text(live_prompt_eval_status, 80),
            "compat_import_staging_pilot_status": bounded_text(compat_import_status, 80),
            "live_prompt_eval_cases_total": _int(live_prompt_summary.get("cases_total")),
            "live_prompt_eval_cases_passed": _int(live_prompt_summary.get("cases_passed")),
            "live_prompt_eval_cases_failed": _int(live_prompt_summary.get("cases_failed")),
            "live_prompt_eval_model_adapter_requests": _int(live_prompt_summary.get("model_adapter_requests")),
            "live_prompt_eval_agentic_tool_cases": _int(
                live_prompt_evidence.get("agent_prompt_eval_agentic_tool_cases")
            ),
            "live_prompt_eval_agentic_tool_cases_required": _int(
                live_prompt_evidence.get("agent_prompt_eval_agentic_tool_cases_required")
            ),
            "candidates_total": _int(candidate_summary.get("candidates_total"), _list_len(candidate_queue.get("candidates"))),
            "ready_for_prompt_eval": _int(candidate_summary.get("ready_for_prompt_eval")),
            "unique_ready_for_prompt_eval": _int(review_summary.get("unique_ready_for_prompt_eval")),
            "case_pack_cases_total": case_count,
            "case_pack_default_gate_eligible_cases": _int(
                case_summary.get("default_gate_eligible_cases")
            ),
            "case_pack_review_required_cases": _int(case_summary.get("review_required_cases")),
            "case_pack_requires_maintainer_review_before_default_gate":
                case_summary.get("requires_maintainer_review_before_default_gate") is True,
            "manual_review_required": manual_review_required,
            "review_items_total": review_items_total,
            "review_action_items_total": review_action_items_total,
            "attention_total": len(attention),
            "blocking_attention_total": len(blocking_attention),
            "adapter_contract_failures_active": active_contract_failures,
            "adapter_contract_failures_resolved": _int(candidate_summary.get("adapter_contract_failures_resolved")),
            "ready_for_adapter_contract_eval": ready_for_adapter_contract_eval,
            "adapter_contract_replayed_total": _int(adapter_summary.get("replayed_total")),
            "adapter_contract_passed": _int(adapter_summary.get("passed")),
            "adapter_contract_failed": _int(adapter_summary.get("failed")),
            "verified_live_probe_cases_read": _int(candidate_summary.get("verified_live_probe_cases_read")),
            "operator_feedback_events_read": _int(candidate_summary.get("operator_feedback_events_read")),
            "operator_labels_applied": _int(candidate_summary.get("operator_labels_applied")),
            "compat_import_node_writes": _int(compat_import_evidence.get("compat_import_node_writes")),
            "compat_import_mapblock_churn": _int(compat_import_evidence.get("compat_import_mapblock_churn")),
            "compat_import_apply_chunks": _int(compat_import_evidence.get("compat_import_apply_chunks")),
            "compat_import_refusal_gates": _int(compat_import_evidence.get("compat_import_refusal_gates")),
            "compat_import_rollback_records": _int(compat_import_evidence.get("compat_import_rollback_records")),
            "compat_import_world_mutation": compat_import_evidence.get("compat_import_world_mutation"),
            "compat_import_mutation_scope": bounded_text(
                compat_import_evidence.get("compat_import_mutation_scope"),
                120,
            ),
        },
        "attention": attention,
        "violations": violations,
        "safety": {
            "public_safe_output": True,
            "no_world_mutation": True,
            "no_raw_assets": True,
            "no_provider_prompts": True,
            "no_provider_credentials": True,
            "no_family_world_coordinates": True,
            "artifact_gate_only": True,
        },
        "bounds": {
            "max_bytes": max_bytes,
            "output_bytes": 0,
            "truncated": False,
        },
    }

    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    payload["bounds"]["output_bytes"] = len(encoded)
    if len(encoded) > max_bytes:
        payload["attention"] = []
        payload["bounds"]["truncated"] = True
        payload["bounds"]["output_bytes"] = len(json.dumps(payload, sort_keys=True).encode("utf-8"))
        if payload["bounds"]["output_bytes"] > max_bytes:
            payload["status"] = "fail"
            payload["violations"].append({
                "kind": "quality_gate_output_exceeds_max_bytes",
                "details": str(payload["bounds"]["output_bytes"]),
            })
    if _artifact_private(payload):
        payload["status"] = "fail"
        payload["safety"]["public_safe_output"] = False
        payload["violations"].append({
            "kind": "quality_gate_not_public_safe",
            "details": "private or forbidden content",
        })
    return payload


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build one public-safe pass/attention/fail quality gate for the Nova agent loop.",
    )
    parser.add_argument("--root", default=".", help="Repository root for relative paths.")
    parser.add_argument("--candidate-queue", required=True, help="Candidate queue JSON path.")
    parser.add_argument("--case-pack", required=True, help="Prompt-eval case pack JSON path.")
    parser.add_argument("--review-queue", required=True, help="Agent review queue JSON path.")
    parser.add_argument("--adapter-contract-eval", default=None, help="Optional adapter-contract replay result JSON path.")
    parser.add_argument("--live-prompt-eval", default=None, help="Optional latest live prompt-eval probe result JSON path.")
    parser.add_argument(
        "--compat-import-staging-pilot",
        default=None,
        help="Optional compatibility import staging pilot JSON path.",
    )
    parser.add_argument("--output", required=True, help="Output quality-gate JSON path.")
    parser.add_argument("--generated-at", default=None, help="ISO timestamp for deterministic artifacts.")
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    root = resolve_path(Path.cwd(), args.root).resolve()
    candidate_queue_path = resolve_path(root, args.candidate_queue)
    case_pack_path = resolve_path(root, args.case_pack)
    review_queue_path = resolve_path(root, args.review_queue)
    adapter_contract_eval_path = (
        resolve_path(root, args.adapter_contract_eval)
        if args.adapter_contract_eval else None
    )
    live_prompt_eval_path = (
        resolve_path(root, args.live_prompt_eval)
        if args.live_prompt_eval else None
    )
    compat_import_pilot_path = (
        resolve_path(root, args.compat_import_staging_pilot)
        if args.compat_import_staging_pilot else None
    )
    output = resolve_path(root, args.output)

    payloads: dict[str, dict[str, Any]] = {}
    load_errors: list[dict[str, str]] = []
    for name, path in (
        ("candidate_queue", candidate_queue_path),
        ("case_pack", case_pack_path),
        ("review_queue", review_queue_path),
        ("adapter_contract_eval", adapter_contract_eval_path),
        ("live_prompt_eval", live_prompt_eval_path),
        ("compat_import_staging_pilot", compat_import_pilot_path),
    ):
        if path is None:
            payloads[name] = {}
            continue
        payload, error = load_json(path)
        payloads[name] = payload
        if error:
            load_errors.append({"kind": f"{name}_unreadable", "details": error})

    report = build_quality_gate(
        candidate_queue=payloads["candidate_queue"],
        case_pack=payloads["case_pack"],
        review=payloads["review_queue"],
        adapter_eval=payloads["adapter_contract_eval"],
        live_prompt_eval=payloads["live_prompt_eval"],
        compat_import_pilot=payloads["compat_import_staging_pilot"],
        generated_at=args.generated_at,
        candidate_queue_path=relative_label(root, candidate_queue_path),
        case_pack_path=relative_label(root, case_pack_path),
        review_queue_path=relative_label(root, review_queue_path),
        adapter_contract_eval_path=relative_label(root, adapter_contract_eval_path),
        live_prompt_eval_path=relative_label(root, live_prompt_eval_path),
        compat_import_pilot_path=relative_label(root, compat_import_pilot_path),
        max_bytes=max(1000, args.max_bytes),
    )
    if load_errors:
        report["status"] = "fail"
        report["violations"].extend(load_errors)
        report["summary"]["load_errors_total"] = len(load_errors)
    write_json(output, report)
    print(json.dumps({
        "quality_gate": relative_label(root, output),
        "quality_gate_status": report.get("status"),
        "attention_total": len(report.get("attention", [])) if isinstance(report.get("attention"), list) else 0,
        "violations_total": len(report.get("violations", [])) if isinstance(report.get("violations"), list) else 0,
        "review_queue_status": report.get("summary", {}).get("review_queue_status"),
        "adapter_contract_eval_status": report.get("summary", {}).get("adapter_contract_eval_status"),
        "live_prompt_eval_status": report.get("summary", {}).get("live_prompt_eval_status"),
        "compat_import_staging_pilot_status": report.get("summary", {}).get("compat_import_staging_pilot_status"),
    }, sort_keys=True))
    return 1 if report.get("status") == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
