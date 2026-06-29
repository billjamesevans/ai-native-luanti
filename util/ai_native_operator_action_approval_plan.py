#!/usr/bin/env python3
"""Build non-mutating approval plans from an operator-control report."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from collections import Counter
from datetime import datetime, timezone


DEFAULT_MAX_BYTES = 20000
PLAN_LIMIT = 24
FIELD_TEXT_LIMIT = 240
MUTATING_ACTION_PREFIXES = ("cancel_", "execute_", "apply_", "approve_", "mutate_", "rollback_")
ATTENTION_STATUSES = {"blocked", "failed", "fail", "unsafe", "error"}

PRIVATE_REDACTIONS = (
    (re.compile(r"/Users/[^\s\"']+"), "<redacted-local-path>"),
    (re.compile(r"\bminecraftpi(?:\.home)?\b", re.I), "<redacted-private-host>"),
    (re.compile(r"\b192\.168(?:\.\d{1,3}){2}\b"), "<redacted-private-ip>"),
    (re.compile(r"\bspacebase|themepark|showcase100|disneyland100\b", re.I), "<redacted-private-demo>"),
    (re.compile(r"sk-[A-Za-z0-9_-]{20,}"), "<redacted-secret>"),
    (re.compile(r"\bOPENAI_API_KEY\b"), "<redacted-secret-env>"),
    (re.compile(r"\bprivate_prompt\b"), "<redacted-private-prompt>"),
    (re.compile(r"\basset_payload\b"), "<redacted-asset-payload>"),
)

ACTION_TEMPLATES = {
    "inspect_task_before_action": {
        "approval_kind": "task_cancel_retry_review",
        "required_capabilities": ["task.inspect", "task.cancel.review"],
        "prerequisites": [
            "inspect_task_status",
            "confirm_task_owner_and_capabilities",
            "confirm_task_still_active",
        ],
        "reference_bucket": "task_ids",
    },
    "review_blocked_task_before_retry": {
        "approval_kind": "task_retry_review",
        "required_capabilities": ["task.inspect", "task.retry.review"],
        "prerequisites": [
            "inspect_blocked_result",
            "confirm_retry_budget",
            "confirm_rollback_metadata_if_mutating",
        ],
        "reference_bucket": "task_ids",
    },
    "inspect_completed_task_summary": {
        "approval_kind": "task_summary_review",
        "required_capabilities": ["task.inspect"],
        "prerequisites": ["inspect_completed_result"],
        "reference_bucket": "task_ids",
    },
    "review_rollback_record_before_execution": {
        "approval_kind": "rollback_execution_review",
        "required_capabilities": ["rollback.review", "rollback.execute.review"],
        "prerequisites": [
            "inspect_rollback_record",
            "confirm_rollback_scope",
            "confirm_operator_approval",
            "confirm_rollback_of_rollback_plan",
        ],
        "reference_bucket": "rollback_records",
    },
    "inspect_rollback_record_status": {
        "approval_kind": "rollback_status_review",
        "required_capabilities": ["rollback.review"],
        "prerequisites": ["inspect_rollback_record_status"],
        "reference_bucket": "rollback_records",
    },
    "review_import_blocker": {
        "approval_kind": "import_blocker_review",
        "required_capabilities": ["import.review"],
        "prerequisites": [
            "inspect_import_blocker",
            "confirm_user_supplied_rights",
            "confirm_no_raw_assets",
        ],
        "reference_bucket": "source_artifacts",
    },
    "review_import_review_before_promotion": {
        "approval_kind": "import_promotion_review",
        "required_capabilities": ["import.review", "import.promotion.review"],
        "prerequisites": [
            "inspect_import_review",
            "confirm_user_supplied_rights",
            "confirm_public_safe_adapter_output",
        ],
        "reference_bucket": "source_artifacts",
    },
    "inspect_import_review_status": {
        "approval_kind": "import_review_status",
        "required_capabilities": ["import.review"],
        "prerequisites": ["inspect_import_review_status"],
        "reference_bucket": "source_artifacts",
    },
    "review_promotion_package_before_apply": {
        "approval_kind": "import_apply_review",
        "required_capabilities": ["import.promotion.review", "import.apply.review"],
        "prerequisites": [
            "inspect_promotion_package",
            "confirm_operator_approval",
            "confirm_disposable_staging_target",
            "confirm_rollback_metadata_available",
        ],
        "reference_bucket": "source_artifacts",
    },
    "review_promotion_blocker": {
        "approval_kind": "promotion_blocker_review",
        "required_capabilities": ["import.promotion.review"],
        "prerequisites": ["inspect_promotion_blocker"],
        "reference_bucket": "source_artifacts",
    },
    "inspect_promotion_status": {
        "approval_kind": "promotion_status_review",
        "required_capabilities": ["import.promotion.review"],
        "prerequisites": ["inspect_promotion_status"],
        "reference_bucket": "source_artifacts",
    },
    "review_benchmark_failure": {
        "approval_kind": "benchmark_failure_review",
        "required_capabilities": ["benchmark.review"],
        "prerequisites": [
            "inspect_benchmark_gate_manifest",
            "compare_accepted_baseline",
            "confirm_no_private_artifacts",
        ],
        "reference_bucket": "source_artifacts",
    },
    "inspect_benchmark_gate_summary": {
        "approval_kind": "benchmark_status_review",
        "required_capabilities": ["benchmark.review"],
        "prerequisites": ["inspect_benchmark_gate_summary"],
        "reference_bucket": "source_artifacts",
    },
}


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


def _validate_source_report(report: dict) -> None:
    if not isinstance(report, dict):
        raise ValueError("operator-control report must be an object")
    if report.get("report_kind") != "ai_native_operator_control_report":
        raise ValueError("operator-control report_kind is invalid")
    control = report.get("operator_control")
    if not isinstance(control, dict):
        raise ValueError("operator_control is missing or invalid")
    if control.get("action_mode") != "dry_run_only":
        raise ValueError("operator_control action_mode is not dry_run_only")
    if control.get("mutation_performed") is not False:
        raise ValueError("operator_control mutation_performed is not false")
    safety = report.get("safety") if isinstance(report.get("safety"), dict) else {}
    if safety.get("dry_run_only") is not True:
        raise ValueError("operator-control report safety is not dry_run_only")
    if safety.get("no_mutating_actions") is not True:
        raise ValueError("operator-control report allows mutating actions")
    if safety.get("no_world_mutation") is not True:
        raise ValueError("operator-control report allows world mutation")
    bounds = report.get("bounds") if isinstance(report.get("bounds"), dict) else {}
    output_bytes = bounds.get("output_bytes")
    max_bytes = bounds.get("max_bytes")
    if not isinstance(output_bytes, int) or not isinstance(max_bytes, int):
        raise ValueError("operator-control report bounds are invalid")
    if output_bytes > max_bytes:
        raise ValueError("source report exceeds declared max_bytes")
    if not isinstance(report.get("items"), list):
        raise ValueError("operator-control report items are invalid")


def _validate_report_item(item: dict, index: int) -> None:
    if not isinstance(item, dict):
        raise ValueError(f"operator-control report item {index} is invalid")
    if item.get("dry_run_only") is not True:
        raise ValueError(f"operator-control report item {index} is mutating")
    if item.get("will_mutate") is not False:
        raise ValueError(f"operator-control report item {index} is mutating")
    for field in ("target_kind", "target_id", "status", "safe_next_action"):
        if not isinstance(item.get(field), str) or not item.get(field):
            raise ValueError(f"operator-control report item {index} missing {field}")
    if item["safe_next_action"].startswith(MUTATING_ACTION_PREFIXES):
        raise ValueError(f"operator-control report item {index} is mutating")


def _empty_references() -> dict:
    return {
        "task_ids": [],
        "rollback_records": [],
        "source_artifacts": [],
    }


def _blocked_reasons(target_kind: str, status: str) -> list[str]:
    if target_kind == "benchmark_gate" and status == "fail":
        return ["benchmark_gate_failed"]
    if status == "blocked":
        return [f"{target_kind}_blocked"]
    if status in {"fail", "failed", "error"}:
        return [f"{target_kind}_failed"]
    if status == "unsafe":
        return [f"{target_kind}_unsafe"]
    return []


def _approval_group(item: dict, redactor: Redactor) -> dict:
    target_kind = redactor.text(item["target_kind"])
    target_id = redactor.text(item["target_id"])
    status = redactor.text(item["status"])
    safe_next_action = redactor.text(item["safe_next_action"])
    template = ACTION_TEMPLATES.get(item["safe_next_action"])
    supported = template is not None
    if template is None:
        template = {
            "approval_kind": "manual_operator_review",
            "required_capabilities": ["operator.review"],
            "prerequisites": ["manual_operator_review"],
            "reference_bucket": "source_artifacts",
        }
    references = _empty_references()
    references[template["reference_bucket"]] = [target_id]
    return {
        "target_kind": target_kind,
        "target_id": target_id,
        "status": status,
        "safe_next_action": safe_next_action,
        "approval_kind": redactor.text(template["approval_kind"]),
        "approval_required": True,
        "dry_run_only": True,
        "will_mutate": False,
        "supported": supported,
        "unsupported_reasons": [] if supported else ["unsupported_safe_next_action"],
        "blocked_reasons": _blocked_reasons(target_kind, status),
        "required_capabilities": [redactor.text(value) for value in template["required_capabilities"]],
        "prerequisites": [redactor.text(value) for value in template["prerequisites"]],
        "references": references,
    }


def _plan_status(source_status: str, approval_groups: list[dict]) -> str:
    if source_status == "fail":
        return "fail"
    if any(not group["supported"] for group in approval_groups):
        return "attention"
    if source_status == "attention":
        return "attention"
    if any(group["status"] in ATTENTION_STATUSES for group in approval_groups):
        return "attention"
    return "ready"


def _with_bounds(plan: dict, max_bytes: int) -> dict:
    def refresh_size() -> int:
        plan["bounds"]["output_bytes"] = len(json.dumps(plan, sort_keys=True).encode("utf-8"))
        return plan["bounds"]["output_bytes"]

    def trim_items(limit: int) -> None:
        plan["approval_groups"] = plan["approval_groups"][:limit]
        plan["operator_actions"]["truncated"] = True
        plan["bounds"]["truncated"] = True
        plan["summary"]["actions_total"] = len(plan["approval_groups"])

    plan["bounds"] = {
        "max_bytes": max_bytes,
        "output_bytes": 0,
        "truncated": plan["operator_actions"]["truncated"],
    }
    if refresh_size() > max_bytes:
        trim_items(8)
        refresh_size()
    if plan["bounds"]["output_bytes"] > max_bytes:
        trim_items(0)
        refresh_size()
    return plan


def build_plan(
    report: dict,
    *,
    generated_at: str | None = None,
    source_path: str | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict:
    _validate_source_report(report)
    for index, item in enumerate(report["items"]):
        _validate_report_item(item, index)

    redactor = Redactor()
    approval_groups = [
        _approval_group(item, redactor)
        for item in report["items"][:PLAN_LIMIT]
    ]
    by_target_kind = _sorted_counts(item["target_kind"] for item in approval_groups)
    by_status = _sorted_counts(item["status"] for item in approval_groups)
    by_safe_next_action = _sorted_counts(item["safe_next_action"] for item in approval_groups)
    source_status = redactor.text(report.get("status", "unknown"))
    plan = {
        "schema_version": 1,
        "plan_kind": "ai_native_operator_action_approval_plan",
        "generated_at": generated_at or utc_now(),
        "source_report": {
            "report_kind": report.get("report_kind"),
            "status": source_status,
            "generated_at": redactor.text(report.get("generated_at", "unknown")),
        },
        "operator_actions": {
            "mode": "approval_required",
            "mutation_performed": False,
            "candidate_actions_total": len(report["items"]),
            "truncated": len(report["items"]) > PLAN_LIMIT,
        },
        "summary": {
            "actions_total": len(approval_groups),
            "source_items_total": len(report["items"]),
            "by_target_kind": by_target_kind,
            "by_status": by_status,
            "by_safe_next_action": by_safe_next_action,
            "attention_required": any(status in ATTENTION_STATUSES for status in by_status),
            "unsupported_actions": sum(1 for item in approval_groups if not item["supported"]),
        },
        "approval_groups": approval_groups,
        "safety": {
            "public_safe_output": True,
            "redactions_applied": redactor.redactions_applied,
            "truncations_applied": redactor.truncations_applied,
            "dry_run_only": True,
            "approval_required": True,
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
    if source_path:
        plan["source_report"]["path"] = redactor.text(source_path)
    plan["status"] = _plan_status(source_status, approval_groups)
    if plan["summary"]["unsupported_actions"]:
        plan["summary"]["attention_required"] = True
    return _with_bounds(plan, max_bytes)


def format_text_plan(plan: dict) -> str:
    lines = [
        "ai_native_operator_action_approval_plan",
        f"status: {plan['status']}",
        f"mode: {plan['operator_actions']['mode']}",
        f"dry_run_only: {str(plan['safety']['dry_run_only']).lower()}",
        f"actions_total: {plan['summary']['actions_total']}",
    ]
    for item in plan["approval_groups"]:
        lines.append(
            "{target_kind} {target_id} status={status} safe_next_action={safe_next_action} "
            "approval_kind={approval_kind} capabilities={capabilities}".format(
                capabilities=",".join(item["required_capabilities"]),
                **item,
            )
        )
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Operator-control report JSON to adapt.")
    parser.add_argument("--output", help="Write the approval plan to this path.")
    parser.add_argument("--generated-at", help="Override generated timestamp for reproducible tests.")
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--format", choices=("json", "text"), default="json")
    args = parser.parse_args(argv)

    try:
        report = _load_json(args.input)
        plan = build_plan(
            report,
            generated_at=args.generated_at,
            source_path=args.input,
            max_bytes=args.max_bytes,
        )
        if args.format == "text":
            payload = format_text_plan(plan)
        else:
            payload = json.dumps(plan, indent=2, sort_keys=True) + "\n"
        if args.output:
            pathlib.Path(args.output).write_text(payload, encoding="utf-8")
        else:
            sys.stdout.write(payload)
        return 0 if plan["bounds"]["output_bytes"] <= args.max_bytes else 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
