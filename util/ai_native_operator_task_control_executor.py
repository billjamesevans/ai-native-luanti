#!/usr/bin/env python3
"""Execute approved task cancel/retry receipts against synthetic task state."""

from __future__ import annotations

import argparse
import copy
import json
import pathlib
import re
import sys
from collections import Counter
from datetime import datetime, timezone


DEFAULT_MAX_BYTES = 20000
EXECUTION_LIMIT = 24
FIELD_TEXT_LIMIT = 240
MUTATING_ACTION_PREFIXES = ("cancel_", "execute_", "apply_", "approve_", "mutate_", "rollback_")
ALLOWED_APPROVAL_KINDS = {
    "task_cancel_retry_review": {
        "operation": "task.cancel",
        "required_executor_capabilities": {"task.inspect", "task.cancel"},
        "actionable_statuses": {"queued", "running", "blocked"},
    },
    "task_retry_review": {
        "operation": "task.retry",
        "required_executor_capabilities": {"task.inspect", "task.retry"},
        "actionable_statuses": {"blocked", "failed", "unsafe"},
    },
}

PRIVATE_PATTERNS = (
    re.compile(r"/Users/[^\s\"']+"),
    re.compile(r"\bminecraftpi(?:\.home)?\b", re.I),
    re.compile(r"\b192\.168(?:\.\d{1,3}){2}\b"),
    re.compile(r"\bspacebase|themepark|showcase100|disneyland100\b", re.I),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
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


def _sorted_counts(values) -> dict:
    return dict(sorted(Counter(values).items()))


def _parse_utc(value: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("timestamp is invalid")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _contains_private_patterns(payload) -> bool:
    raw = json.dumps(payload, sort_keys=True)
    return any(pattern.search(raw) for pattern in PRIVATE_PATTERNS)


def _task_status_for_decision(decision: dict) -> str:
    approval_kind = decision.get("approval_kind")
    status = decision.get("target_status")
    if approval_kind == "task_retry_review":
        return status if status in {"blocked", "failed", "unsafe"} else "blocked"
    return status if status in {"queued", "running", "blocked"} else "running"


def sample_task_state_for_receipt(receipt: dict) -> dict:
    """Build disposable task state for receipt verification without a live world."""
    tasks = []
    seen = set()
    for decision in receipt.get("decisions", []):
        if not isinstance(decision, dict) or decision.get("target_kind") != "task":
            continue
        target_id = str(decision.get("target_id", ""))
        if not target_id or target_id in seen:
            continue
        seen.add(target_id)
        task = {
            "task_id": target_id,
            "status": _task_status_for_decision(decision),
            "owner": "operator-status-verifier",
            "retry_count": 0,
        }
        if task["status"] in {"blocked", "failed", "unsafe"}:
            task["blocked_reason"] = "synthetic_receipt_sample"
        tasks.append(task)
    return {
        "schema_version": 1,
        "state_kind": "ai_native_synthetic_task_control_state",
        "generated_at": receipt.get("generated_at", utc_now()),
        "runtime_context": {
            "mode": "synthetic_task_control",
            "requires_live_pi": False,
            "requires_private_world": False,
            "world_mutation_performed": False,
        },
        "tasks": tasks,
        "safety": {
            "synthetic_only": True,
            "public_safe_output": True,
            "no_world_mutation": True,
        },
    }


def _validate_receipt(
    receipt: dict,
    *,
    generated_at: str | None,
    max_receipt_age_seconds: int,
    max_bytes: int,
) -> None:
    if not isinstance(receipt, dict):
        raise ValueError("approval receipt must be an object")
    if receipt.get("receipt_kind") != "ai_native_operator_action_approval_receipt":
        raise ValueError("approval receipt kind is invalid")
    if not isinstance(receipt.get("decisions"), list):
        raise ValueError("approval receipt decisions are invalid")
    operator_decisions = receipt.get("operator_decisions")
    if not isinstance(operator_decisions, dict):
        raise ValueError("approval receipt operator_decisions missing or invalid")
    if operator_decisions.get("mode") != "receipt_only":
        raise ValueError("approval receipt mode is invalid")
    if operator_decisions.get("mutation_performed") is not False:
        raise ValueError("approval receipt already mutated state")

    safety = receipt.get("safety") if isinstance(receipt.get("safety"), dict) else {}
    for field in (
        "public_safe_output",
        "receipt_only",
        "no_world_mutation",
        "no_rollback_execution",
        "no_import_promotion_execution",
        "no_raw_assets",
        "no_provider_prompts",
        "no_family_world_coordinates",
    ):
        if safety.get(field) is not True:
            raise ValueError(f"approval receipt safety {field} is not true")

    bounds = receipt.get("bounds") if isinstance(receipt.get("bounds"), dict) else {}
    output_bytes = bounds.get("output_bytes")
    receipt_max_bytes = bounds.get("max_bytes", max_bytes)
    if not isinstance(output_bytes, int) or not isinstance(receipt_max_bytes, int):
        raise ValueError("approval receipt bounds are invalid")
    if output_bytes > receipt_max_bytes or output_bytes > max_bytes:
        raise ValueError("source receipt exceeds max_bytes")

    current_time = _parse_utc(generated_at or utc_now())
    receipt_time = _parse_utc(str(receipt.get("generated_at", "")))
    if max_receipt_age_seconds >= 0 and (
        current_time - receipt_time
    ).total_seconds() > max_receipt_age_seconds:
        raise ValueError("approval receipt is stale")

    for index, decision in enumerate(receipt["decisions"][:EXECUTION_LIMIT]):
        _validate_decision(decision, index)


def _validate_decision(decision: dict, index: int) -> None:
    if not isinstance(decision, dict):
        raise ValueError(f"decision {index} is invalid")
    for field in (
        "decision_id",
        "decision_status",
        "target_kind",
        "target_id",
        "safe_next_action",
        "approval_kind",
    ):
        if not isinstance(decision.get(field), str) or not decision.get(field):
            raise ValueError(f"decision {index} missing {field}")
    if decision["safe_next_action"].startswith(MUTATING_ACTION_PREFIXES):
        raise ValueError(f"decision {index} safe_next_action is mutating")
    if decision.get("approval_required") is not True:
        raise ValueError(f"decision {index} does not require approval")
    if decision.get("dry_run_only") is not True:
        raise ValueError(f"decision {index} is not dry-run-only")
    if decision.get("will_mutate") is not False:
        raise ValueError(f"decision {index} declares mutation")
    if decision.get("mutation_performed") is not False:
        raise ValueError(f"decision {index} already mutated")
    if decision.get("receipt_only") is not True:
        raise ValueError(f"decision {index} is not receipt-only")
    if not isinstance(decision.get("required_capabilities"), list):
        raise ValueError(f"decision {index} missing required_capabilities")
    if not isinstance(decision.get("prerequisites_required"), list):
        raise ValueError(f"decision {index} missing prerequisites_required")
    if not isinstance(decision.get("prerequisites_acknowledged"), list):
        raise ValueError(f"decision {index} missing prerequisites_acknowledged")
    if _contains_private_patterns({
        "decision_id": decision.get("decision_id"),
        "target_kind": decision.get("target_kind"),
        "target_id": decision.get("target_id"),
        "safe_next_action": decision.get("safe_next_action"),
        "approval_kind": decision.get("approval_kind"),
        "operator_note": decision.get("operator_note", ""),
        "references": decision.get("references", {}),
    }):
        raise ValueError(f"decision {index} contains private content")


def _validate_task_state(task_state: dict) -> None:
    if not isinstance(task_state, dict):
        raise ValueError("task state must be an object")
    if task_state.get("state_kind") != "ai_native_synthetic_task_control_state":
        raise ValueError("task state_kind is invalid")
    runtime_context = task_state.get("runtime_context")
    if not isinstance(runtime_context, dict):
        raise ValueError("task state runtime_context missing or invalid")
    if runtime_context.get("mode") != "synthetic_task_control":
        raise ValueError("task state mode is invalid")
    if runtime_context.get("requires_live_pi") is not False:
        raise ValueError("task state requires live Pi")
    if runtime_context.get("requires_private_world") is not False:
        raise ValueError("task state requires private world")
    if runtime_context.get("world_mutation_performed") is not False:
        raise ValueError("task state already mutated world")
    if not isinstance(task_state.get("tasks"), list):
        raise ValueError("task state tasks are invalid")
    if _contains_private_patterns(task_state):
        raise ValueError("task state contains private content")


def _task_by_id(task_state: dict) -> dict[str, dict]:
    tasks = {}
    for task in task_state.get("tasks", []):
        if not isinstance(task, dict):
            continue
        task_id = task.get("task_id")
        if isinstance(task_id, str) and task_id:
            tasks[task_id] = task
    return tasks


def _result_base(decision: dict, redactor: Redactor) -> dict:
    return {
        "decision_id": redactor.text(decision.get("decision_id", "unknown")),
        "decision_status": redactor.text(decision.get("decision_status", "unknown")),
        "target_kind": redactor.text(decision.get("target_kind", "unknown")),
        "target_id": redactor.text(decision.get("target_id", "unknown")),
        "approval_kind": redactor.text(decision.get("approval_kind", "unknown")),
        "safe_next_action": redactor.text(decision.get("safe_next_action", "unknown")),
    }


def _reject(decision: dict, redactor: Redactor, reason: str) -> dict:
    item = _result_base(decision, redactor)
    item.update({
        "status": "rejected",
        "reason": reason,
        "operation": "none",
        "mutation_performed": False,
    })
    return item


def _execute_decision(
    decision: dict,
    tasks: dict[str, dict],
    executor_capabilities: set[str],
    redactor: Redactor,
) -> dict:
    if decision["decision_status"] != "approved":
        return _reject(decision, redactor, "decision_not_approved")

    spec = ALLOWED_APPROVAL_KINDS.get(decision["approval_kind"])
    if spec is None or decision["target_kind"] != "task":
        return _reject(decision, redactor, "unsupported_approval_kind")

    missing_prerequisites = sorted(
        set(str(value) for value in decision["prerequisites_required"])
        - set(str(value) for value in decision["prerequisites_acknowledged"])
    )
    if missing_prerequisites:
        result = _reject(decision, redactor, "missing_acknowledged_prerequisite")
        result["missing_prerequisites"] = [redactor.text(value) for value in missing_prerequisites]
        return result

    missing_capabilities = sorted(spec["required_executor_capabilities"] - executor_capabilities)
    if missing_capabilities:
        result = _reject(decision, redactor, "missing_executor_capability")
        result["missing_executor_capabilities"] = [
            redactor.text(value) for value in missing_capabilities
        ]
        return result

    task = tasks.get(decision["target_id"])
    if task is None:
        return _reject(decision, redactor, "task_not_found")

    before_status = str(task.get("status", "unknown"))
    if before_status not in spec["actionable_statuses"]:
        return _reject(
            decision,
            redactor,
            "task_not_retryable" if spec["operation"] == "task.retry" else "task_not_actionable",
        )

    if spec["operation"] == "task.cancel":
        task["status"] = "cancelled"
    else:
        task["status"] = "queued"
        task["retry_count"] = int(task.get("retry_count", 0)) + 1
        task.pop("blocked_reason", None)

    item = _result_base(decision, redactor)
    item.update({
        "status": "executed",
        "reason": "approved_receipt",
        "operation": spec["operation"],
        "before_status": redactor.text(before_status),
        "after_status": redactor.text(task["status"]),
        "mutation_performed": True,
        "mutation_scope": "synthetic_task_state",
    })
    return item


def _sanitize_task_state(task_state: dict, redactor: Redactor) -> dict:
    tasks = []
    for task in task_state.get("tasks", []):
        if not isinstance(task, dict):
            continue
        sanitized = {}
        for key in ("task_id", "status", "owner", "blocked_reason"):
            if key in task:
                sanitized[key] = redactor.text(task[key])
        if "retry_count" in task:
            try:
                sanitized["retry_count"] = int(task["retry_count"])
            except (TypeError, ValueError):
                sanitized["retry_count"] = 0
        tasks.append(sanitized)
    return {
        "state_kind": redactor.text(task_state.get("state_kind", "unknown")),
        "runtime_context": {
            "mode": "synthetic_task_control",
            "requires_live_pi": False,
            "requires_private_world": False,
            "world_mutation_performed": False,
        },
        "tasks": tasks,
    }


def _with_bounds(result: dict, max_bytes: int) -> dict:
    def refresh_size() -> int:
        result["bounds"]["output_bytes"] = len(json.dumps(result, sort_keys=True).encode("utf-8"))
        return result["bounds"]["output_bytes"]

    def trim_results(limit: int) -> None:
        result["results"] = result["results"][:limit]
        result["bounds"]["truncated"] = True
        result["operator_actions"]["truncated"] = True
        result["summary"]["results_retained"] = len(result["results"])

    result["bounds"] = {
        "max_bytes": max_bytes,
        "output_bytes": 0,
        "truncated": result["operator_actions"]["truncated"],
    }
    if refresh_size() > max_bytes:
        trim_results(8)
        refresh_size()
    if result["bounds"]["output_bytes"] > max_bytes:
        trim_results(0)
        refresh_size()
    return result


def build_execution_result(
    receipt: dict,
    task_state: dict,
    *,
    generated_at: str | None = None,
    source_path: str | None = None,
    executor_capabilities: list[str] | tuple[str, ...] | set[str] | None = None,
    max_receipt_age_seconds: int = 86400,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict:
    _validate_receipt(
        receipt,
        generated_at=generated_at,
        max_receipt_age_seconds=max_receipt_age_seconds,
        max_bytes=max_bytes,
    )
    _validate_task_state(task_state)

    redactor = Redactor()
    before_state = copy.deepcopy(task_state)
    after_state = copy.deepcopy(task_state)
    tasks = _task_by_id(after_state)
    capability_set = set(executor_capabilities or ())
    decisions = receipt.get("decisions", [])[:EXECUTION_LIMIT]
    results = [
        _execute_decision(decision, tasks, capability_set, redactor)
        for decision in decisions
    ]

    status_counts = _sorted_counts(item["status"] for item in results)
    by_operation = _sorted_counts(item.get("operation", "none") for item in results)
    by_reason = _sorted_counts(
        item.get("reason", "none") for item in results if item["status"] != "executed"
    )
    executed_total = status_counts.get("executed", 0)
    rejected_total = status_counts.get("rejected", 0)
    skipped_total = status_counts.get("skipped", 0)
    result = {
        "schema_version": 1,
        "execution_kind": "ai_native_operator_action_execution_result",
        "generated_at": generated_at or utc_now(),
        "source_receipt": {
            "receipt_kind": receipt.get("receipt_kind"),
            "status": redactor.text(receipt.get("status", "unknown")),
            "generated_at": redactor.text(receipt.get("generated_at", "unknown")),
        },
        "operator_actions": {
            "mode": "receipt_gated_task_control",
            "mutation_performed": executed_total > 0,
            "task_state_mutation_performed": executed_total > 0,
            "world_mutation_performed": False,
            "allowed_approval_kinds": sorted(ALLOWED_APPROVAL_KINDS),
            "executor_capabilities": sorted(redactor.text(value) for value in capability_set),
            "truncated": len(receipt.get("decisions", [])) > EXECUTION_LIMIT,
        },
        "summary": {
            "decisions_total": len(decisions),
            "source_decisions_total": len(receipt.get("decisions", [])),
            "executed_total": executed_total,
            "rejected_total": rejected_total,
            "skipped_total": skipped_total,
            "results_retained": len(results),
            "by_result_status": status_counts,
            "by_operation": by_operation,
            "by_rejection_reason": by_reason,
            "attention_required": rejected_total > 0 or len(receipt.get("decisions", [])) > EXECUTION_LIMIT,
        },
        "results": results,
        "task_state_before": _sanitize_task_state(before_state, redactor),
        "task_state_after": _sanitize_task_state(after_state, redactor),
        "safety": {
            "public_safe_output": True,
            "receipt_required": True,
            "receipt_gated": True,
            "task_control_only": True,
            "task_state_mutation_only": True,
            "world_mutation_performed": False,
            "no_world_mutation": True,
            "no_rollback_execution": True,
            "no_import_promotion_execution": True,
            "no_structure_apply": True,
            "no_raw_assets": True,
            "no_provider_prompts": True,
            "no_family_world_coordinates": True,
            "redactions_applied": redactor.redactions_applied,
            "truncations_applied": redactor.truncations_applied,
        },
    }
    source_plan = receipt.get("source_plan") if isinstance(receipt.get("source_plan"), dict) else {}
    if source_plan.get("path"):
        result["source_receipt"]["source_plan_path"] = redactor.text(source_plan["path"])
    if source_plan.get("source_report_path"):
        result["source_receipt"]["source_report_path"] = redactor.text(source_plan["source_report_path"])
    if source_path:
        result["source_receipt"]["path"] = redactor.text(source_path)
    result["safety"]["redactions_applied"] = redactor.redactions_applied
    result["safety"]["truncations_applied"] = redactor.truncations_applied
    result["status"] = "attention" if result["summary"]["attention_required"] else "ready"
    return _with_bounds(result, max_bytes)


def format_text_result(result: dict) -> str:
    lines = [
        "ai_native_operator_action_execution_result",
        f"status: {result['status']}",
        f"mode: {result['operator_actions']['mode']}",
        f"task_state_mutation_performed: {str(result['operator_actions']['task_state_mutation_performed']).lower()}",
        f"world_mutation_performed: {str(result['operator_actions']['world_mutation_performed']).lower()}",
        f"decisions_total: {result['summary']['decisions_total']}",
    ]
    for item in result["results"]:
        lines.append(
            "{decision_id} target={target_kind}:{target_id} status={status} "
            "operation={operation} reason={reason}".format(
                decision_id=item["decision_id"],
                target_kind=item["target_kind"],
                target_id=item["target_id"],
                status=item["status"],
                operation=item["operation"],
                reason=item.get("reason", "none"),
            )
        )
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Operator action approval receipt JSON.")
    parser.add_argument(
        "--state",
        help="Synthetic task state JSON. If omitted, builds disposable state from the receipt.",
    )
    parser.add_argument("--output", help="Write the execution result to this path.")
    parser.add_argument("--generated-at", help="Override generated timestamp for reproducible tests.")
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--max-receipt-age-seconds", type=int, default=86400)
    parser.add_argument(
        "--capability",
        action="append",
        default=[],
        help="Executor capability to enable; repeat for task.inspect, task.cancel, task.retry.",
    )
    parser.add_argument("--format", choices=("json", "text"), default="json")
    args = parser.parse_args(argv)

    try:
        receipt = _load_json(args.input)
        task_state = _load_json(args.state) if args.state else sample_task_state_for_receipt(receipt)
        result = build_execution_result(
            receipt,
            task_state,
            generated_at=args.generated_at,
            source_path=args.input,
            executor_capabilities=args.capability,
            max_receipt_age_seconds=args.max_receipt_age_seconds,
            max_bytes=args.max_bytes,
        )
        if args.format == "text":
            payload = format_text_result(result)
        else:
            payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
        if args.output:
            pathlib.Path(args.output).write_text(payload, encoding="utf-8")
        else:
            sys.stdout.write(payload)
        return 0 if result["bounds"]["output_bytes"] <= args.max_bytes else 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
