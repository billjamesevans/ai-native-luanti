#!/usr/bin/env python3
"""Build a bounded operator status package for the AI-native runtime."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import ai_native_product_profile_verify


DEFAULT_MAX_BYTES = 24000
SUMMARY_LIMIT = 12
FIELD_TEXT_LIMIT = 240

PRIVATE_REDACTIONS = (
    (re.compile(r"/Users/[^\s\"']+"), "<redacted-local-path>"),
    (re.compile(r"\bminecraftpi(?:\.home)?\b", re.I), "<redacted-private-host>"),
    (re.compile(r"\b192\.168(?:\.\d{1,3}){2}\b"), "<redacted-private-ip>"),
    (re.compile(r"\bspacebase|themepark|showcase100|disneyland100\b", re.I), "<redacted-private-demo>"),
    (re.compile(r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}"), "<redacted-secret>"),
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

    def _bounded_text(self, value: str) -> str:
        encoded = value.encode("utf-8")
        if len(encoded) <= FIELD_TEXT_LIMIT:
            return value
        self.truncations_applied += 1
        return encoded[:FIELD_TEXT_LIMIT].decode("utf-8", "ignore") + "<truncated>"

    def text(self, value) -> str:
        sanitized = str(value)
        for pattern, replacement in PRIVATE_REDACTIONS:
            sanitized, count = pattern.subn(replacement, sanitized)
            self.redactions_applied += count
        return self._bounded_text(sanitized)

    def optional_text(self, value):
        if value is None:
            return None
        return self.text(value)


def _load_json(path):
    if not path:
        return {}
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def _status_counts(items) -> dict:
    counts = Counter(item.get("status", "unknown") for item in items)
    return dict(sorted(counts.items()))


def _task_counts(tasks) -> dict:
    counts = {"total": len(tasks)}
    counts.update(_status_counts(tasks))
    return counts


def _summarize_agents(agents, redactor: Redactor) -> dict:
    summaries = []
    profiles = set()
    for agent in agents[:SUMMARY_LIMIT]:
        profile = agent.get("capability_profile") or "unspecified"
        profiles.add(profile)
        summaries.append({
            "agent_id": redactor.text(agent.get("agent_id", "unknown")),
            "owner": redactor.text(agent.get("owner", "unknown")),
            "capability_profile": redactor.text(profile),
            "capabilities": sorted(redactor.text(capability) for capability in agent.get("capabilities", [])),
        })
    for agent in agents[SUMMARY_LIMIT:]:
        profiles.add(agent.get("capability_profile") or "unspecified")
    return {
        "total": len(agents),
        "capability_profiles": sorted(redactor.text(profile) for profile in profiles),
        "summaries": summaries,
        "truncated": len(agents) > SUMMARY_LIMIT,
    }


def _summarize_tasks(tasks, redactor: Redactor) -> dict:
    summaries = []
    for task in tasks[:SUMMARY_LIMIT]:
        summary = {
            "task_id": redactor.text(task.get("task_id", "unknown")),
            "agent_id": redactor.text(task.get("agent_id", "unknown")),
            "status": redactor.text(task.get("status", "unknown")),
        }
        for field in ("label", "reason"):
            value = redactor.optional_text(task.get(field))
            if value is not None:
                summary[field] = value
        summaries.append(summary)
    return {
        "counts": _task_counts(tasks),
        "summaries": summaries,
        "truncated": len(tasks) > SUMMARY_LIMIT,
    }


def _summarize_rollback(records, redactor: Redactor) -> dict:
    available = [
        record for record in records
        if record.get("status", "available") in {"available", "success", "recorded"}
    ]
    summaries = []
    for record in records[:SUMMARY_LIMIT]:
        summary = {
            "record_id": redactor.text(record.get("record_id", "unknown")),
            "task_id": redactor.text(record.get("task_id", "unknown")),
            "status": redactor.text(record.get("status", "available")),
        }
        storage_ref = redactor.optional_text(record.get("storage_ref"))
        if storage_ref is not None:
            summary["storage_ref"] = storage_ref
        summaries.append(summary)
    return {
        "records_total": len(records),
        "records_available": len(available),
        "status_counts": _status_counts(records),
        "summaries": summaries,
        "truncated": len(records) > SUMMARY_LIMIT,
    }


def _summarize_imports(reviews, promotions, redactor: Redactor) -> dict:
    summaries = []
    for review in reviews[:SUMMARY_LIMIT]:
        summary = {
            "review_id": redactor.text(review.get("review_id", "unknown")),
            "status": redactor.text(review.get("status", "unknown")),
            "rights_confirmed": review.get("rights_confirmed") is True,
        }
        source = redactor.optional_text(review.get("source"))
        if source is not None:
            summary["source"] = source
        summaries.append(summary)
    promotion_summaries = []
    for package in promotions[:SUMMARY_LIMIT]:
        summary = {
            "package_id": redactor.text(package.get("package_id", "unknown")),
            "status": redactor.text(package.get("status", "unknown")),
            "approval_confirmed": package.get("approval_confirmed") is True,
        }
        source = redactor.optional_text(package.get("source"))
        if source is not None:
            summary["source"] = source
        promotion_summaries.append(summary)
    return {
        "reviews_total": len(reviews),
        "promotions_total": len(promotions),
        "status_counts": _status_counts(reviews),
        "promotion_status_counts": _status_counts(promotions),
        "summaries": summaries,
        "promotion_summaries": promotion_summaries,
        "truncated": len(reviews) > SUMMARY_LIMIT or len(promotions) > SUMMARY_LIMIT,
    }


def _summarize_benchmarks(gates, redactor: Redactor) -> dict:
    summaries = []
    for gate in gates[:SUMMARY_LIMIT]:
        summary = {
            "gate_id": redactor.text(gate.get("gate_id", "unknown")),
            "status": redactor.text(gate.get("status", "unknown")),
        }
        source = redactor.optional_text(gate.get("source"))
        if source is not None:
            summary["source"] = source
        summaries.append(summary)
    return {
        "gates": summaries,
        "status_counts": _status_counts(gates),
        "truncated": len(gates) > SUMMARY_LIMIT,
    }


def _task_safe_next_action(status: str) -> str:
    if status in {"blocked", "unsafe", "failed"}:
        return "review_blocked_task_before_retry"
    if status in {"completed", "cancelled"}:
        return "inspect_completed_task_summary"
    return "inspect_task_before_action"


def _task_is_actionable(status: str) -> bool:
    return status not in {"completed", "cancelled"}


def _rollback_safe_next_action(status: str) -> str:
    if status in {"available", "success", "recorded"}:
        return "review_rollback_record_before_execution"
    return "inspect_rollback_record_status"


def _import_review_safe_next_action(status: str) -> str:
    if status == "blocked":
        return "review_import_blocker"
    if status in {"approved", "ready", "success"}:
        return "review_import_review_before_promotion"
    return "inspect_import_review_status"


def _promotion_safe_next_action(status: str) -> str:
    if status == "ready":
        return "review_promotion_package_before_apply"
    if status in {"blocked", "fail"}:
        return "review_promotion_blocker"
    return "inspect_promotion_status"


def _benchmark_safe_next_action(status: str) -> str:
    if status == "fail":
        return "review_benchmark_failure"
    return "inspect_benchmark_gate_summary"


def _operator_recommendation(
    redactor: Redactor,
    *,
    target_kind: str,
    target_id,
    status,
    safe_next_action: str,
) -> dict:
    return {
        "target_kind": redactor.text(target_kind),
        "target_id": redactor.text(target_id or "unknown"),
        "status": redactor.text(status or "unknown"),
        "safe_next_action": redactor.text(safe_next_action),
        "dry_run_only": True,
        "will_mutate": False,
    }


def _summarize_operator_control(
    tasks,
    rollback_records,
    import_reviews,
    promotions,
    gates,
    redactor: Redactor,
) -> dict:
    recommendations = []
    control_tasks = [
        task for task in tasks
        if _task_is_actionable(task.get("status", "unknown"))
    ]
    if not control_tasks:
        control_tasks = tasks
    for task in control_tasks:
        status = task.get("status", "unknown")
        recommendations.append(_operator_recommendation(
            redactor,
            target_kind="task",
            target_id=task.get("task_id", "unknown"),
            status=status,
            safe_next_action=_task_safe_next_action(status),
        ))
    for record in rollback_records:
        status = record.get("status", "available")
        recommendations.append(_operator_recommendation(
            redactor,
            target_kind="rollback",
            target_id=record.get("record_id") or record.get("task_id") or "unknown",
            status=status,
            safe_next_action=_rollback_safe_next_action(status),
        ))
    for review in import_reviews:
        status = review.get("status", "unknown")
        recommendations.append(_operator_recommendation(
            redactor,
            target_kind="import_review",
            target_id=review.get("review_id", "unknown"),
            status=status,
            safe_next_action=_import_review_safe_next_action(status),
        ))
    for package in promotions:
        status = package.get("status", "unknown")
        recommendations.append(_operator_recommendation(
            redactor,
            target_kind="import_promotion",
            target_id=package.get("package_id", "unknown"),
            status=status,
            safe_next_action=_promotion_safe_next_action(status),
        ))
    for gate in gates:
        status = gate.get("status", "unknown")
        if status == "fail":
            recommendations.append(_operator_recommendation(
                redactor,
                target_kind="benchmark_gate",
                target_id=gate.get("gate_id", "unknown"),
                status=status,
                safe_next_action=_benchmark_safe_next_action(status),
            ))
    return {
        "surface_kind": "read_only_task_rollback_control",
        "action_mode": "dry_run_only",
        "mutation_performed": False,
        "recommendations_total": len(recommendations),
        "summaries": recommendations[:SUMMARY_LIMIT],
        "truncated": len(recommendations) > SUMMARY_LIMIT,
    }


def _server_profile_hygiene(root: pathlib.Path) -> dict:
    report = ai_native_product_profile_verify.build_report(root)
    return {
        "status": report["status"],
        "gameid": report["profile"]["gameid"],
        "product_mods": report["profile"]["product_mods"],
        "dev_surfaces_disabled_by_default": report["safety"]["dev_surfaces_disabled_by_default"],
        "test_fixtures_explicit_only": report["safety"]["test_fixtures_explicit_only"],
        "no_private_content": report["safety"]["no_private_content"],
        "violations": report["violations"],
    }


def _package_status(package) -> str:
    if package["server_profile_hygiene"]["status"] != "pass":
        return "attention"
    if package["tasks"]["counts"].get("blocked", 0) or package["tasks"]["counts"].get("failed", 0):
        return "attention"
    if package["imports"]["status_counts"].get("blocked", 0):
        return "attention"
    if package["benchmarks"]["status_counts"].get("fail", 0):
        return "attention"
    return "ready"


def _with_bounds(package, max_bytes: int) -> dict:
    def refresh_size() -> int:
        package["bounds"]["output_bytes"] = len(json.dumps(package, sort_keys=True).encode("utf-8"))
        return package["bounds"]["output_bytes"]

    def trim_lists(limit: int) -> None:
        for section in ("agents", "tasks", "rollback", "imports", "benchmarks", "operator_control"):
            if "summaries" in package[section]:
                package[section]["summaries"] = package[section]["summaries"][:limit]
                package[section]["truncated"] = True
        if "promotion_summaries" in package["imports"]:
            package["imports"]["promotion_summaries"] = package["imports"]["promotion_summaries"][:limit]
            package["imports"]["truncated"] = True
        if "gates" in package["benchmarks"]:
            package["benchmarks"]["gates"] = package["benchmarks"]["gates"][:limit]
            package["benchmarks"]["truncated"] = True
        package["bounds"]["truncated"] = True

    def drop_verbose_fields() -> None:
        for task in package["tasks"].get("summaries", []):
            task.pop("label", None)
            task.pop("reason", None)
        for record in package["rollback"].get("summaries", []):
            record.pop("storage_ref", None)
        for review in package["imports"].get("summaries", []):
            review.pop("source", None)
        for promotion in package["imports"].get("promotion_summaries", []):
            promotion.pop("source", None)
        for gate in package["benchmarks"].get("gates", []):
            gate.pop("source", None)
        package["bounds"]["truncated"] = True

    package["bounds"] = {
        "max_bytes": max_bytes,
        "output_bytes": 0,
        "truncated": any(
            package[section].get("truncated")
            for section in ("agents", "tasks", "rollback", "imports", "benchmarks", "operator_control")
        ),
    }
    if refresh_size() > max_bytes:
        trim_lists(3)
        refresh_size()
    if package["bounds"]["output_bytes"] > max_bytes:
        drop_verbose_fields()
        refresh_size()
    if package["bounds"]["output_bytes"] > max_bytes:
        trim_lists(0)
        refresh_size()
    return package


def build_package(
    root,
    *,
    generated_at: str | None = None,
    source_state: dict | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict:
    root = pathlib.Path(root)
    state = source_state or {}
    redactor = Redactor()
    tasks = state.get("tasks", [])
    rollback_records = state.get("rollback_records", [])
    import_reviews = state.get("import_reviews", [])
    promotion_packages = state.get("promotion_packages", [])
    benchmark_gates = state.get("benchmark_gates", [])

    package = {
        "schema_version": 1,
        "package_kind": "ai_native_operator_status_package",
        "generated_at": generated_at or utc_now(),
        "runtime_context": {
            "game_profile": "ai_runtime",
            "source": "synthetic_or_default_state",
            "mutation_performed": False,
        },
        "server_profile_hygiene": _server_profile_hygiene(root),
        "agents": _summarize_agents(state.get("agents", []), redactor),
        "tasks": _summarize_tasks(tasks, redactor),
        "rollback": _summarize_rollback(rollback_records, redactor),
        "imports": _summarize_imports(
            import_reviews,
            promotion_packages,
            redactor,
        ),
        "benchmarks": _summarize_benchmarks(benchmark_gates, redactor),
        "operator_control": _summarize_operator_control(
            tasks,
            rollback_records,
            import_reviews,
            promotion_packages,
            benchmark_gates,
            redactor,
        ),
    }
    package["safety"] = {
        "public_safe_output": True,
        "redactions_applied": redactor.redactions_applied,
        "truncations_applied": redactor.truncations_applied,
        "no_raw_assets": True,
        "no_provider_prompts": True,
        "no_family_world_coordinates": True,
    }
    package["status"] = _package_status(package)
    return _with_bounds(package, max_bytes)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root to inspect.")
    parser.add_argument("--input", help="Optional synthetic/default operator state JSON.")
    parser.add_argument("--output", help="Write the package JSON to this path.")
    parser.add_argument("--generated-at", help="Override generated timestamp for reproducible tests.")
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    args = parser.parse_args(argv)

    try:
        package = build_package(
            pathlib.Path(args.root),
            generated_at=args.generated_at,
            source_state=_load_json(args.input),
            max_bytes=args.max_bytes,
        )
        payload = json.dumps(package, indent=2, sort_keys=True) + "\n"
        if args.output:
            pathlib.Path(args.output).write_text(payload, encoding="utf-8")
        else:
            sys.stdout.write(payload)
        return 0 if package["bounds"]["output_bytes"] <= args.max_bytes else 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
