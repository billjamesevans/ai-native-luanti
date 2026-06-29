#!/usr/bin/env python3
"""Build receipt-only operator approval artifacts from approval plans."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from collections import Counter
from datetime import datetime, timezone


DEFAULT_MAX_BYTES = 20000
RECEIPT_LIMIT = 24
FIELD_TEXT_LIMIT = 240
DECISION_STATUSES = {"approved", "denied", "needs_review"}
MUTATING_ACTION_PREFIXES = ("cancel_", "execute_", "apply_", "approve_", "mutate_", "rollback_")
ATTENTION_DECISIONS = {"denied", "needs_review"}

PRIVATE_PATTERNS = (
    re.compile(r"/Users/[^\s\"']+"),
    re.compile(r"\bminecraftpi(?:\.home)?\b", re.I),
    re.compile(r"\b192\.168(?:\.\d{1,3}){2}\b"),
    re.compile(r"\bspacebase|themepark|showcase100|disneyland100\b", re.I),
    re.compile(r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"\bOPENAI_API_KEY\b"),
    re.compile(r"\bprivate_prompt\b"),
    re.compile(r"\basset_payload\b"),
)

PRIVATE_REDACTIONS = (
    (PRIVATE_PATTERNS[0], "<redacted-local-path>"),
    (PRIVATE_PATTERNS[1], "<redacted-private-host>"),
    (PRIVATE_PATTERNS[2], "<redacted-private-ip>"),
    (PRIVATE_PATTERNS[3], "<redacted-private-demo>"),
    (PRIVATE_PATTERNS[4], "<redacted-secret>"),
    (PRIVATE_PATTERNS[5], "<redacted-secret-env>"),
    (PRIVATE_PATTERNS[6], "<redacted-private-prompt>"),
    (PRIVATE_PATTERNS[7], "<redacted-asset-payload>"),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class Redactor:
    def __init__(self) -> None:
        self.redactions_applied = 0
        self.truncations_applied = 0

    def text(self, value) -> str:
        text = str(value)
        for pattern, replacement in PRIVATE_REDACTIONS:
            text, count = pattern.subn(replacement, text)
            self.redactions_applied += count
        encoded = text.encode("utf-8")
        if len(encoded) <= FIELD_TEXT_LIMIT:
            return text
        self.truncations_applied += 1
        return encoded[:FIELD_TEXT_LIMIT].decode("utf-8", "ignore") + "<truncated>"


def _load_json(path: str | pathlib.Path) -> dict:
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def _contains_private_patterns(payload: dict) -> bool:
    raw = json.dumps(payload, sort_keys=True)
    return any(pattern.search(raw) for pattern in PRIVATE_PATTERNS)


def _sorted_counts(values) -> dict:
    return dict(sorted(Counter(values).items()))


def _parse_utc(value: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("timestamp is invalid")
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _validate_source_plan(plan: dict) -> None:
    if not isinstance(plan, dict):
        raise ValueError("approval plan must be an object")
    if plan.get("plan_kind") != "ai_native_operator_action_approval_plan":
        raise ValueError("approval plan_kind is invalid")
    operator_actions = plan.get("operator_actions")
    if not isinstance(operator_actions, dict):
        raise ValueError("operator_actions is missing or invalid")
    if operator_actions.get("mode") != "approval_required":
        raise ValueError("approval plan mode is invalid")
    if operator_actions.get("mutation_performed") is not False:
        raise ValueError("approval plan mutation_performed is not false")
    safety = plan.get("safety") if isinstance(plan.get("safety"), dict) else {}
    for field in (
        "public_safe_output",
        "dry_run_only",
        "approval_required",
        "no_mutating_actions",
        "no_world_mutation",
        "no_task_mutation",
        "no_rollback_execution",
        "no_import_promotion_execution",
        "no_raw_assets",
        "no_provider_prompts",
        "no_family_world_coordinates",
    ):
        if safety.get(field) is not True:
            raise ValueError(f"approval plan safety {field} is not true")
    bounds = plan.get("bounds") if isinstance(plan.get("bounds"), dict) else {}
    output_bytes = bounds.get("output_bytes")
    max_bytes = bounds.get("max_bytes")
    if not isinstance(output_bytes, int) or not isinstance(max_bytes, int):
        raise ValueError("approval plan bounds are invalid")
    if output_bytes > max_bytes:
        raise ValueError("source plan exceeds declared max_bytes")
    if not isinstance(plan.get("approval_groups"), list):
        raise ValueError("approval plan approval_groups are invalid")


def _validate_plan_group(group: dict, index: int) -> None:
    if not isinstance(group, dict):
        raise ValueError(f"approval plan group {index} is invalid")
    if group.get("supported") is not True:
        raise ValueError(f"approval plan group {index} is unsupported")
    if group.get("dry_run_only") is not True:
        raise ValueError(f"approval plan group {index} is mutating")
    if group.get("will_mutate") is not False:
        raise ValueError(f"approval plan group {index} is mutating")
    if group.get("approval_required") is not True:
        raise ValueError(f"approval plan group {index} does not require approval")
    for field in ("target_kind", "target_id", "status", "safe_next_action", "approval_kind"):
        if not isinstance(group.get(field), str) or not group.get(field):
            raise ValueError(f"approval plan group {index} missing {field}")
    if group["safe_next_action"].startswith(MUTATING_ACTION_PREFIXES):
        raise ValueError(f"approval plan group {index} safe_next_action is mutating")
    if not isinstance(group.get("required_capabilities"), list):
        raise ValueError(f"approval plan group {index} missing required_capabilities")
    if not isinstance(group.get("prerequisites"), list):
        raise ValueError(f"approval plan group {index} missing prerequisites")
    if not isinstance(group.get("references"), dict):
        raise ValueError(f"approval plan group {index} missing references")


def _validate_decision_document(plan: dict, decision_doc: dict, generated_at: str | None) -> None:
    if not isinstance(decision_doc, dict):
        raise ValueError("decision document must be an object")
    if _contains_private_patterns(decision_doc):
        raise ValueError("decision document contains private content")
    if decision_doc.get("decision_kind") != "ai_native_operator_action_decision":
        raise ValueError("decision document kind is invalid")
    decisions = decision_doc.get("decisions")
    if not isinstance(decisions, list):
        raise ValueError("decision document decisions are invalid")
    source_plan_generated_at = decision_doc.get("source_plan_generated_at")
    if source_plan_generated_at != plan.get("generated_at"):
        raise ValueError("decision document source_plan_generated_at does not match plan")
    max_age = decision_doc.get("max_plan_age_seconds")
    if max_age is not None:
        if not isinstance(max_age, int) or max_age < 0:
            raise ValueError("decision document max_plan_age_seconds is invalid")
        current_time = _parse_utc(generated_at or decision_doc.get("generated_at") or utc_now())
        plan_time = _parse_utc(plan["generated_at"])
        if (current_time - plan_time).total_seconds() > max_age:
            raise ValueError("approval plan is stale")


def _decision_key(item: dict) -> tuple[str, str, str]:
    return (
        str(item.get("target_kind", "")),
        str(item.get("target_id", "")),
        str(item.get("safe_next_action", "")),
    )


def _validate_decision(decision: dict, index: int) -> None:
    if not isinstance(decision, dict):
        raise ValueError(f"decision {index} is invalid")
    for field in ("target_kind", "target_id", "safe_next_action", "decision_status"):
        if not isinstance(decision.get(field), str) or not decision.get(field):
            raise ValueError(f"decision {index} missing {field}")
    if decision["safe_next_action"].startswith(MUTATING_ACTION_PREFIXES):
        raise ValueError(f"decision {index} safe_next_action is mutating")
    if decision["decision_status"] not in DECISION_STATUSES:
        raise ValueError(f"decision {index} status is invalid")
    if not isinstance(decision.get("prerequisites_acknowledged"), list):
        raise ValueError(f"decision {index} missing prerequisites_acknowledged")


def _receipt_decision(group: dict, decision: dict, redactor: Redactor, index: int) -> dict:
    decision_status = redactor.text(decision["decision_status"])
    required_prerequisites = [redactor.text(value) for value in group["prerequisites"]]
    acknowledged = [redactor.text(value) for value in decision.get("prerequisites_acknowledged", [])]
    if decision_status == "approved":
        missing = sorted(set(required_prerequisites) - set(acknowledged))
        if missing:
            raise ValueError("approved decision is missing prerequisites")
    return {
        "decision_id": redactor.text(decision.get("decision_id", f"decision:{index + 1:03d}")),
        "decision_status": decision_status,
        "target_kind": redactor.text(group["target_kind"]),
        "target_id": redactor.text(group["target_id"]),
        "target_status": redactor.text(group["status"]),
        "safe_next_action": redactor.text(group["safe_next_action"]),
        "approval_kind": redactor.text(group["approval_kind"]),
        "required_capabilities": [redactor.text(value) for value in group["required_capabilities"]],
        "prerequisites_required": required_prerequisites,
        "prerequisites_acknowledged": acknowledged,
        "operator_note": redactor.text(decision.get("operator_note", "")),
        "references": {
            key: [redactor.text(value) for value in values]
            for key, values in group["references"].items()
            if isinstance(values, list)
        },
        "approval_required": True,
        "dry_run_only": True,
        "will_mutate": False,
        "mutation_performed": False,
        "receipt_only": True,
    }


def _receipt_status(plan_status: str, decisions: list[dict]) -> str:
    if plan_status == "fail":
        return "fail"
    if any(decision["decision_status"] in ATTENTION_DECISIONS for decision in decisions):
        return "attention"
    if plan_status == "attention":
        return "attention"
    return "ready"


def _with_bounds(receipt: dict, max_bytes: int) -> dict:
    def refresh_size() -> int:
        receipt["bounds"]["output_bytes"] = len(json.dumps(receipt, sort_keys=True).encode("utf-8"))
        return receipt["bounds"]["output_bytes"]

    def trim_items(limit: int) -> None:
        receipt["decisions"] = receipt["decisions"][:limit]
        receipt["operator_decisions"]["truncated"] = True
        receipt["bounds"]["truncated"] = True
        receipt["summary"]["decisions_total"] = len(receipt["decisions"])

    receipt["bounds"] = {
        "max_bytes": max_bytes,
        "output_bytes": 0,
        "truncated": receipt["operator_decisions"]["truncated"],
    }
    if refresh_size() > max_bytes:
        trim_items(8)
        refresh_size()
    if receipt["bounds"]["output_bytes"] > max_bytes:
        trim_items(0)
        refresh_size()
    return receipt


def sample_decision_document(plan: dict, *, generated_at: str | None = None) -> dict:
    _validate_source_plan(plan)
    decisions = []
    for group in plan.get("approval_groups", []):
        decisions.append({
            "target_kind": group.get("target_kind", "unknown"),
            "target_id": group.get("target_id", "unknown"),
            "safe_next_action": group.get("safe_next_action", "unknown"),
            "decision_status": "needs_review",
            "prerequisites_acknowledged": [],
            "operator_note": "sample verifier receipt only",
        })
    return {
        "schema_version": 1,
        "decision_kind": "ai_native_operator_action_decision",
        "generated_at": generated_at or utc_now(),
        "operator_id": "operator:verifier-sample",
        "source_plan_generated_at": plan.get("generated_at"),
        "max_plan_age_seconds": 86400,
        "decisions": decisions,
    }


def build_receipt(
    plan: dict,
    decision_doc: dict,
    *,
    generated_at: str | None = None,
    source_path: str | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict:
    _validate_source_plan(plan)
    groups = plan["approval_groups"][:RECEIPT_LIMIT]
    for index, group in enumerate(groups):
        _validate_plan_group(group, index)
    _validate_decision_document(plan, decision_doc, generated_at)
    group_by_key = {_decision_key(group): group for group in groups}

    redactor = Redactor()
    receipt_decisions = []
    for index, decision in enumerate(decision_doc["decisions"][:RECEIPT_LIMIT]):
        _validate_decision(decision, index)
        group = group_by_key.get(_decision_key(decision))
        if group is None:
            raise ValueError(f"decision {index} missing plan entry")
        receipt_decisions.append(_receipt_decision(group, decision, redactor, index))

    status_counts = _sorted_counts(item["decision_status"] for item in receipt_decisions)
    by_target_kind = _sorted_counts(item["target_kind"] for item in receipt_decisions)
    by_approval_kind = _sorted_counts(item["approval_kind"] for item in receipt_decisions)
    plan_status = redactor.text(plan.get("status", "unknown"))
    receipt = {
        "schema_version": 1,
        "receipt_kind": "ai_native_operator_action_approval_receipt",
        "generated_at": generated_at or utc_now(),
        "source_plan": {
            "plan_kind": plan.get("plan_kind"),
            "status": plan_status,
            "generated_at": redactor.text(plan.get("generated_at", "unknown")),
        },
        "operator_decisions": {
            "mode": "receipt_only",
            "operator_id": redactor.text(decision_doc.get("operator_id", "unknown")),
            "mutation_performed": False,
            "decisions_total": len(receipt_decisions),
            "approved_total": status_counts.get("approved", 0),
            "denied_total": status_counts.get("denied", 0),
            "needs_review_total": status_counts.get("needs_review", 0),
            "truncated": len(decision_doc["decisions"]) > RECEIPT_LIMIT,
        },
        "summary": {
            "decisions_total": len(receipt_decisions),
            "source_actions_total": len(groups),
            "by_decision_status": status_counts,
            "by_target_kind": by_target_kind,
            "by_approval_kind": by_approval_kind,
            "attention_required": bool(status_counts.get("denied") or status_counts.get("needs_review")),
        },
        "decisions": receipt_decisions,
        "safety": {
            "public_safe_output": True,
            "redactions_applied": redactor.redactions_applied,
            "truncations_applied": redactor.truncations_applied,
            "dry_run_only": True,
            "approval_required": True,
            "receipt_only": True,
            "no_mutating_actions": True,
            "no_world_mutation": True,
            "no_task_mutation": True,
            "no_rollback_execution": True,
            "no_import_promotion_execution": True,
            "no_raw_assets": True,
            "no_provider_prompts": True,
            "no_family_world_coordinates": True,
        },
    }
    source_report = plan.get("source_report") if isinstance(plan.get("source_report"), dict) else {}
    if source_report.get("path"):
        receipt["source_plan"]["source_report_path"] = redactor.text(source_report["path"])
    if source_path:
        receipt["source_plan"]["path"] = redactor.text(source_path)
    receipt["safety"]["redactions_applied"] = redactor.redactions_applied
    receipt["safety"]["truncations_applied"] = redactor.truncations_applied
    receipt["status"] = _receipt_status(plan_status, receipt_decisions)
    if receipt["operator_decisions"]["truncated"]:
        receipt["summary"]["attention_required"] = True
    return _with_bounds(receipt, max_bytes)


def format_text_receipt(receipt: dict) -> str:
    lines = [
        "ai_native_operator_action_approval_receipt",
        f"status: {receipt['status']}",
        f"mode: {receipt['operator_decisions']['mode']}",
        f"dry_run_only: {str(receipt['safety']['dry_run_only']).lower()}",
        f"decisions_total: {receipt['summary']['decisions_total']}",
    ]
    for item in receipt["decisions"]:
        lines.append(
            "{target_kind} {target_id} decision={decision_status} "
            "approval_kind={approval_kind} safe_next_action={safe_next_action}".format(**item)
        )
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Operator action approval plan JSON.")
    parser.add_argument(
        "--decision",
        help="Explicit operator decision JSON. If omitted, writes a needs_review sample receipt.",
    )
    parser.add_argument("--output", help="Write the receipt to this path.")
    parser.add_argument("--generated-at", help="Override generated timestamp for reproducible tests.")
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--format", choices=("json", "text"), default="json")
    args = parser.parse_args(argv)

    try:
        plan = _load_json(args.input)
        if args.decision:
            decision = _load_json(args.decision)
        else:
            decision = sample_decision_document(plan, generated_at=args.generated_at)
        receipt = build_receipt(
            plan,
            decision,
            generated_at=args.generated_at,
            source_path=args.input,
            max_bytes=args.max_bytes,
        )
        if args.format == "text":
            payload = format_text_receipt(receipt)
        else:
            payload = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
        if args.output:
            pathlib.Path(args.output).write_text(payload, encoding="utf-8")
        else:
            sys.stdout.write(payload)
        return 0 if receipt["bounds"]["output_bytes"] <= args.max_bytes else 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
