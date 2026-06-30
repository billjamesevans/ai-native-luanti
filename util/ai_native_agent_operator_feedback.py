#!/usr/bin/env python3
"""Convert public-safe in-game operator feedback events into label artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import ai_native_agent_eval_queue as eval_queue
import ai_native_agent_operator_label as operator_label


OPERATOR_FEEDBACK_MARKER = "operator_feedback="
OPERATOR_FEEDBACK_KIND = "ai_agent_operator_feedback"


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


def feedback_payload(event: dict[str, Any]) -> dict[str, Any]:
    feedback = event.get("feedback")
    return feedback if isinstance(feedback, dict) else {}


def operator_feedback_inputs(
    events: list[dict[str, Any]],
    *,
    feedback_id: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for event in events:
        feedback = feedback_payload(event)
        if feedback_id and feedback.get("feedback_id") != feedback_id:
            continue
        matches.append(event)
    if not matches:
        raise operator_label.OperatorLabelError("no matching operator feedback found")
    event = matches[-1]
    feedback = feedback_payload(event)
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


def _label_payload_from_feedback(
    event: dict[str, Any],
    *,
    candidate_queue_path: str,
    generated_at: str | None,
) -> dict[str, Any] | None:
    feedback = feedback_payload(event)
    expected = eval_queue.safe_expected_from_operator_label(feedback.get("expected"))
    if expected is None:
        return None
    prompt = feedback.get("prompt")
    candidate_id = feedback.get("candidate_id")
    if not isinstance(prompt, str) and not isinstance(candidate_id, str):
        return None
    case_hint = operator_label.slug(
        feedback.get("case_hint")
        or f"operator_labeled_{expected['build_material_name']}_{expected['build_kind']}"
    )
    label_id = feedback.get("label_id")
    if not isinstance(label_id, str) or not label_id:
        label_id = operator_label.stable_label_id(
            candidate_id=candidate_id if isinstance(candidate_id, str) else None,
            prompt=prompt if isinstance(prompt, str) else None,
            case_hint=case_hint,
            expected=expected,
        )
    label: dict[str, Any] = {
        "label_id": label_id,
        "case_hint": case_hint,
        "expected": expected,
    }
    if isinstance(candidate_id, str) and candidate_id:
        label["candidate_id"] = candidate_id
    if isinstance(prompt, str) and prompt:
        label["prompt"] = prompt
    source_kind = feedback.get("source_kind")
    if isinstance(source_kind, str) and source_kind:
        label["source_kind"] = source_kind
    artifact = {
        "schema_version": operator_label.OPERATOR_LABEL_SCHEMA_VERSION,
        "artifact_kind": eval_queue.OPERATOR_LABEL_KIND,
        "generated_at": generated_at or operator_label.utc_now(),
        "source": {
            "candidate_queue": candidate_queue_path,
            "matched_candidate_id": None,
            "matched": None,
            "operator_feedback_id": feedback.get("feedback_id"),
            "operator_feedback_source_trace_id": feedback.get("source_trace_id"),
        },
        "labels": [label],
        "safety": {
            "public_safe_output": True,
            "operator_reviewed": True,
            "no_world_mutation": True,
            "max_labels": operator_label.MAX_LABELS,
        },
    }
    if eval_queue.has_private_content(artifact) or eval_queue.has_forbidden_key(artifact):
        return None
    return artifact


def operator_feedback_label_payloads(
    events: list[dict[str, Any]],
    *,
    candidate_queue_path: str,
    generated_at: str | None = None,
    feedback_id: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    payloads: list[dict[str, Any]] = []
    summary = {
        "operator_feedback_labels_generated": 0,
        "operator_feedback_labels_skipped_invalid": 0,
    }
    for event in events:
        feedback = feedback_payload(event)
        if feedback_id and feedback.get("feedback_id") != feedback_id:
            continue
        payload = _label_payload_from_feedback(
            event,
            candidate_queue_path=candidate_queue_path,
            generated_at=generated_at,
        )
        if payload is None:
            summary["operator_feedback_labels_skipped_invalid"] += 1
            continue
        payloads.append(payload)
        summary["operator_feedback_labels_generated"] += 1
    return payloads, summary
