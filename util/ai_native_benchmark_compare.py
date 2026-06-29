#!/usr/bin/env python3
"""Compare AI-native benchmark reports against an accepted baseline."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


TIME_METRICS = ("avg_step_ms", "p95_step_ms", "max_lag_ms")
WRITE_METRICS = ("node_writes_per_step", "node_writes")
ENTITY_METRICS = ("entity_count", "active_peak")
PRIVATE_CONTEXT_FLAGS = (
    "requires_private_world",
    "requires_private_assets",
    "requires_live_pi",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def number(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def count_items(value) -> int:
    if value is None:
        return 0
    if isinstance(value, list):
        return len(value)
    return 1


def report_family(report: dict) -> str:
    if report.get("fixture_id") == "generic_demo_entity:benchmark:v1":
        return "demo_entity"
    return "mutation"


def scenario_index(report: dict) -> dict:
    return {
        scenario.get("scenario_id"): scenario
        for scenario in report.get("scenarios", [])
        if scenario.get("scenario_id")
    }


def report_ref(report: dict) -> dict:
    return {
        "luanti_commit": report.get("luanti_commit"),
        "hardware_class": report.get("hardware_class"),
        "run_mode": (report.get("run_context") or {}).get("mode"),
    }


def make_gate(scenario_id, metric, baseline, branch, status, merge_rule, detail):
    return {
        "scenario_id": scenario_id,
        "metric": metric,
        "baseline": baseline,
        "branch": branch,
        "status": status,
        "merge_rule": merge_rule,
        "detail": detail,
    }


def compare_ratio(scenario_id, metric, baseline, branch, max_regression):
    base = number(baseline)
    candidate = number(branch)
    if base is None or candidate is None:
        return None
    allowed = base if base == 0 else base * (1 + max_regression)
    status = "pass" if candidate <= allowed else "fail"
    return make_gate(
        scenario_id,
        metric,
        base,
        candidate,
        status,
        "must not merge without an explicit benchmark exception",
        f"branch value must stay within {max_regression:.0%} of baseline",
    )


def compare_not_greater(scenario_id, metric, baseline, branch, merge_rule):
    base = number(baseline)
    candidate = number(branch)
    if base is None or candidate is None:
        return None
    status = "pass" if candidate <= base else "fail"
    return make_gate(
        scenario_id,
        metric,
        base,
        candidate,
        status,
        merge_rule,
        "branch value must not exceed baseline",
    )


def compare_reports(baseline: dict, branch: dict, max_regression: float) -> dict:
    gates = []
    baseline_family = report_family(baseline)
    branch_family = report_family(branch)
    family = branch_family if baseline_family == branch_family else "mixed"

    if baseline_family != branch_family:
        gates.append(make_gate(
            "report",
            "report_family",
            baseline_family,
            branch_family,
            "fail",
            "must not merge benchmark comparisons across report families",
            "baseline and branch report families differ",
        ))

    if baseline.get("hardware_class") != branch.get("hardware_class"):
        gates.append(make_gate(
            "report",
            "hardware_class",
            baseline.get("hardware_class"),
            branch.get("hardware_class"),
            "fail",
            "must not merge benchmark comparisons across hardware classes",
            "baseline and branch hardware classes differ",
        ))

    for label, report in (("baseline", baseline), ("branch", branch)):
        run_context = report.get("run_context") or {}
        for flag in PRIVATE_CONTEXT_FLAGS:
            if run_context.get(flag) is True:
                gates.append(make_gate(
                    "report",
                    flag,
                    False,
                    True,
                    "fail",
                    "must not merge reports that require private or live server state",
                    f"{label} report has {flag}=true",
                ))

    baseline_scenarios = scenario_index(baseline)
    branch_scenarios = scenario_index(branch)
    scenario_ids = sorted(set(baseline_scenarios) | set(branch_scenarios))
    compared_scenarios = []
    baseline_only_scenarios = []
    branch_only_scenarios = []

    for scenario_id in scenario_ids:
        base_scenario = baseline_scenarios.get(scenario_id)
        branch_scenario = branch_scenarios.get(scenario_id)
        if not base_scenario and branch_scenario:
            branch_only_scenarios.append(scenario_id)
            gates.append(make_gate(
                scenario_id,
                "scenario_presence",
                False,
                True,
                "pass",
                "new benchmark coverage should be reviewed before the next baseline promotion",
                "branch includes an additive scenario that is not yet in the accepted baseline",
            ))
            continue
        if base_scenario and not branch_scenario:
            baseline_only_scenarios.append(scenario_id)
            gates.append(make_gate(
                scenario_id,
                "scenario_presence",
                bool(base_scenario),
                bool(branch_scenario),
                "fail",
                "must not merge with missing benchmark scenarios",
                "branch is missing a scenario from the accepted baseline",
            ))
            continue

        compared_scenarios.append(scenario_id)
        base_metrics = base_scenario.get("metrics") or {}
        branch_metrics = branch_scenario.get("metrics") or {}

        for metric in TIME_METRICS:
            gate = compare_ratio(
                scenario_id,
                metric,
                base_metrics.get(metric),
                branch_metrics.get(metric),
                max_regression,
            )
            if gate:
                gates.append(gate)

        for metric in WRITE_METRICS:
            gate = compare_not_greater(
                scenario_id,
                metric,
                base_metrics.get(metric),
                branch_metrics.get(metric),
                "must not merge if node writes exceed the accepted baseline",
            )
            if gate:
                gates.append(gate)

        for metric in ENTITY_METRICS:
            gate = compare_ratio(
                scenario_id,
                metric,
                base_metrics.get(metric),
                branch_metrics.get(metric),
                max_regression,
            )
            if gate:
                gates.append(gate)

        remaining_gate = compare_not_greater(
            scenario_id,
            "remaining_entities",
            base_metrics.get("remaining_entities"),
            branch_metrics.get("remaining_entities"),
            "must not merge if benchmark cleanup leaves extra entities",
        )
        if remaining_gate:
            gates.append(remaining_gate)

        baseline_warnings = count_items(base_metrics.get("warnings"))
        branch_warnings = count_items(branch_metrics.get("warnings"))
        gates.append(make_gate(
            scenario_id,
            "warnings",
            baseline_warnings,
            branch_warnings,
            "pass" if branch_warnings <= baseline_warnings else "fail",
            "must not merge until new warnings are reviewed",
            "branch warning count must not exceed baseline warning count",
        ))

        branch_errors = count_items(branch_metrics.get("errors"))
        gates.append(make_gate(
            scenario_id,
            "errors",
            count_items(base_metrics.get("errors")),
            branch_errors,
            "pass" if branch_errors == 0 else "fail",
            "must not merge with runtime errors",
            "branch errors must be empty",
        ))

        if "rollback_records" in base_metrics or "rollback_records" in branch_metrics:
            baseline_records = number(base_metrics.get("rollback_records"))
            branch_records = number(branch_metrics.get("rollback_records"))
            if baseline_records is not None and branch_records is not None:
                gates.append(make_gate(
                    scenario_id,
                    "rollback_records",
                    baseline_records,
                    branch_records,
                    "pass" if baseline_records <= 0 or branch_records >= baseline_records else "fail",
                    "must not merge if rollback records are missing from mutating scenarios",
                    "branch rollback record count must preserve the accepted baseline",
                ))

    failed = any(gate["status"] == "fail" for gate in gates)
    return {
        "schema_version": 1,
        "generated_at": utc_now(),
        "report_family": family,
        "baseline_ref": report_ref(baseline),
        "branch_ref": report_ref(branch),
        "threshold_percent": max_regression * 100,
        "overall_status": "fail" if failed else "pass",
        "compared_scenarios": compared_scenarios,
        "baseline_only_scenarios": baseline_only_scenarios,
        "branch_only_scenarios": branch_only_scenarios,
        "gates": gates,
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Compare an AI-native benchmark report against an accepted baseline."
    )
    parser.add_argument("--baseline", required=True, help="Accepted baseline JSON report.")
    parser.add_argument("--branch", required=True, help="Branch JSON report to compare.")
    parser.add_argument("--output", required=True, help="Where to write comparison JSON.")
    parser.add_argument(
        "--max-regression",
        type=float,
        default=0.10,
        help="Allowed fractional regression for timing/entity metrics. Default: 0.10.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    comparison = compare_reports(
        load_json(Path(args.baseline)),
        load_json(Path(args.branch)),
        args.max_regression,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(comparison, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(comparison["overall_status"])
    return 1 if comparison["overall_status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
