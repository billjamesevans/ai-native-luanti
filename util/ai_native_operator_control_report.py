#!/usr/bin/env python3
"""Build a bounded operator-control report from an AI runtime status package."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from collections import Counter
from datetime import datetime, timezone


DEFAULT_MAX_BYTES = 16000
SUMMARY_LIMIT = 24
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


def _validate_source_package(package: dict) -> dict:
    if not isinstance(package, dict):
        raise ValueError("operator status package must be an object")
    if package.get("package_kind") != "ai_native_operator_status_package":
        raise ValueError("operator status package_kind is invalid")
    control = package.get("operator_control")
    if not isinstance(control, dict):
        raise ValueError("operator_control is missing or invalid")
    if control.get("surface_kind") != "read_only_task_rollback_control":
        raise ValueError("operator_control surface_kind is invalid")
    if control.get("action_mode") != "dry_run_only":
        raise ValueError("operator_control action_mode is not dry_run_only")
    if control.get("mutation_performed") is not False:
        raise ValueError("operator_control mutation_performed is not false")
    if not isinstance(control.get("recommendations_total"), int):
        raise ValueError("operator_control recommendations_total is not numeric")
    return control


def _normalized_recommendations(control: dict) -> list[dict]:
    summaries = control.get("summaries")
    if summaries is None and control.get("recommendations_total") == 0:
        return []
    if not isinstance(summaries, list):
        raise ValueError("operator_control summaries is not a list")
    return summaries


def _validate_recommendation(item: dict, index: int) -> None:
    if not isinstance(item, dict):
        raise ValueError(f"operator_control recommendation {index} is invalid")
    if item.get("dry_run_only") is not True:
        raise ValueError(f"operator_control recommendation {index} is mutating")
    if item.get("will_mutate") is not False:
        raise ValueError(f"operator_control recommendation {index} is mutating")
    for field in ("target_kind", "target_id", "status", "safe_next_action"):
        if not isinstance(item.get(field), str) or not item.get(field):
            raise ValueError(f"operator_control recommendation {index} missing {field}")
    safe_next_action = item["safe_next_action"]
    if safe_next_action.startswith(MUTATING_ACTION_PREFIXES):
        raise ValueError(f"operator_control recommendation {index} is mutating")


def _report_item(item: dict, redactor: Redactor) -> dict:
    return {
        "target_kind": redactor.text(item["target_kind"]),
        "target_id": redactor.text(item["target_id"]),
        "status": redactor.text(item["status"]),
        "safe_next_action": redactor.text(item["safe_next_action"]),
        "dry_run_only": True,
        "will_mutate": False,
    }


def _report_status(package_status: str, items: list[dict]) -> str:
    if package_status == "fail":
        return "fail"
    if package_status == "attention":
        return "attention"
    if any(item["status"] in ATTENTION_STATUSES for item in items):
        return "attention"
    return "ready"


def _with_bounds(report: dict, max_bytes: int) -> dict:
    def refresh_size() -> int:
        report["bounds"]["output_bytes"] = len(json.dumps(report, sort_keys=True).encode("utf-8"))
        return report["bounds"]["output_bytes"]

    def trim_items(limit: int) -> None:
        report["items"] = report["items"][:limit]
        report["operator_control"]["truncated"] = True
        report["bounds"]["truncated"] = True

    report["bounds"] = {
        "max_bytes": max_bytes,
        "output_bytes": 0,
        "truncated": report["operator_control"]["truncated"],
    }
    if refresh_size() > max_bytes:
        trim_items(8)
        refresh_size()
    if report["bounds"]["output_bytes"] > max_bytes:
        trim_items(0)
        refresh_size()
    return report


def build_report(
    package: dict,
    *,
    generated_at: str | None = None,
    source_path: str | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict:
    control = _validate_source_package(package)
    recommendations = _normalized_recommendations(control)
    for index, recommendation in enumerate(recommendations):
        _validate_recommendation(recommendation, index)

    redactor = Redactor()
    items = [_report_item(item, redactor) for item in recommendations[:SUMMARY_LIMIT]]
    by_target_kind = _sorted_counts(item["target_kind"] for item in items)
    by_status = _sorted_counts(item["status"] for item in items)
    by_safe_next_action = _sorted_counts(item["safe_next_action"] for item in items)
    report = {
        "schema_version": 1,
        "report_kind": "ai_native_operator_control_report",
        "generated_at": generated_at or utc_now(),
        "source_package": {
            "package_kind": package.get("package_kind"),
            "status": redactor.text(package.get("status", "unknown")),
            "generated_at": redactor.text(package.get("generated_at", "unknown")),
        },
        "operator_control": {
            "surface_kind": "read_only_task_rollback_control",
            "action_mode": "dry_run_only",
            "mutation_performed": False,
            "recommendations_total": control["recommendations_total"],
            "truncated": control.get("truncated") is True or len(recommendations) > SUMMARY_LIMIT,
        },
        "summary": {
            "items_total": len(items),
            "source_recommendations_total": control["recommendations_total"],
            "by_target_kind": by_target_kind,
            "by_status": by_status,
            "by_safe_next_action": by_safe_next_action,
            "attention_required": any(status in ATTENTION_STATUSES for status in by_status),
        },
        "items": items,
        "safety": {
            "public_safe_output": True,
            "redactions_applied": redactor.redactions_applied,
            "truncations_applied": redactor.truncations_applied,
            "dry_run_only": True,
            "no_mutating_actions": True,
            "no_world_mutation": True,
            "no_raw_assets": True,
            "no_provider_prompts": True,
            "no_family_world_coordinates": True,
        },
    }
    if source_path:
        report["source_package"]["path"] = redactor.text(source_path)
    report["status"] = _report_status(report["source_package"]["status"], items)
    return _with_bounds(report, max_bytes)


def format_text_report(report: dict) -> str:
    lines = [
        "ai_native_operator_control_report",
        f"status: {report['status']}",
        f"action_mode: {report['operator_control']['action_mode']}",
        f"dry_run_only: {str(report['safety']['dry_run_only']).lower()}",
        f"items_total: {report['summary']['items_total']}",
    ]
    for item in report["items"]:
        lines.append(
            "{target_kind} {target_id} status={status} safe_next_action={safe_next_action}".format(
                **item
            )
        )
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Operator status package JSON to adapt.")
    parser.add_argument("--output", help="Write the report to this path.")
    parser.add_argument("--generated-at", help="Override generated timestamp for reproducible tests.")
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--format", choices=("json", "text"), default="json")
    args = parser.parse_args(argv)

    try:
        package = _load_json(args.input)
        report = build_report(
            package,
            generated_at=args.generated_at,
            source_path=args.input,
            max_bytes=args.max_bytes,
        )
        if args.format == "text":
            payload = format_text_report(report)
        else:
            payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
        if args.output:
            pathlib.Path(args.output).write_text(payload, encoding="utf-8")
        else:
            sys.stdout.write(payload)
        return 0 if report["bounds"]["output_bytes"] <= args.max_bytes else 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
