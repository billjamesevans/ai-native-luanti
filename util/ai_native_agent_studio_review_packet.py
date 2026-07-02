#!/usr/bin/env python3
"""Create a public-safe OpenRealm Studio review packet from status telemetry."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ai_native_agent_eval_queue as eval_queue
import ai_native_agent_operator_label as operator_label


STUDIO_REVIEW_PACKET_KIND = "openrealm_studio_agent_review_packet"
TRACE_RE = re.compile(r"nova_trace:[A-Za-z0-9_.-]+")


class StudioReviewPacketError(ValueError):
    """Raised when Studio status cannot safely become a review packet."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def text_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def safe_slug(value: Any, fallback: str = "operator_labeled") -> str:
    return operator_label.slug(str(value or fallback), fallback=fallback)


def trace_id_from_task_id(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    match = TRACE_RE.search(value)
    return match.group(0) if match else None


def selected_trace_id(trace: dict[str, Any]) -> str | None:
    return text_or_none(trace.get("source_trace_id")) or trace_id_from_task_id(trace.get("task_id"))


def load_status_json(path: Path | None, url: str | None) -> dict[str, Any]:
    if bool(path) == bool(url):
        raise StudioReviewPacketError("provide exactly one of --status-json or --status-url")
    try:
        if path is not None:
            payload = json.loads(path.read_text(encoding="utf-8"))
        else:
            with urlopen(url, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
    except FileNotFoundError as exc:
        raise StudioReviewPacketError("status JSON file not found") from exc
    except json.JSONDecodeError as exc:
        raise StudioReviewPacketError("status JSON is not valid JSON") from exc
    except OSError as exc:
        raise StudioReviewPacketError("status URL could not be read") from exc
    if not isinstance(payload, dict):
        raise StudioReviewPacketError("status payload must be a JSON object")
    if eval_queue.has_private_content(payload) or eval_queue.has_forbidden_key(payload):
        raise StudioReviewPacketError("status payload is not public-safe")
    return payload


def status_traces(status: dict[str, Any]) -> list[dict[str, Any]]:
    adapter_log = status.get("adapter_log") if isinstance(status.get("adapter_log"), dict) else {}
    traces = adapter_log.get("recent_traces")
    result: list[dict[str, Any]] = []
    if isinstance(traces, list):
        result.extend(item for item in traces if isinstance(item, dict))
    latest = adapter_log.get("latest")
    if isinstance(latest, dict) and latest not in result:
        result.insert(0, latest)
    return result


def is_reviewable_trace(trace: dict[str, Any]) -> bool:
    if text_or_none(trace.get("selected_option_id")) is None:
        return False
    if text_or_none(trace.get("task_id")) is None and selected_trace_id(trace) is None:
        return False
    if trace.get("ok") is not True:
        return False
    if trace.get("agentic_execution") is not True:
        return False
    if trace.get("world_mutation_authority") not in {None, "luanti"}:
        return False
    if trace.get("direct_world_mutation") is True:
        return False
    return True


def select_trace(
    status: dict[str, Any],
    *,
    trace_id: str | None,
    task_id: str | None,
    selected_option_id: str | None,
    trace_index: int | None,
) -> dict[str, Any]:
    traces = [trace for trace in status_traces(status) if is_reviewable_trace(trace)]
    if not traces:
        raise StudioReviewPacketError("status payload has no reviewable agent trace")
    for index, trace in enumerate(traces):
        if trace_id and selected_trace_id(trace) != trace_id:
            continue
        if task_id and text_or_none(trace.get("task_id")) != task_id:
            continue
        if selected_option_id and text_or_none(trace.get("selected_option_id")) != selected_option_id:
            continue
        if trace_index is not None and index != trace_index:
            continue
        return trace
    if trace_id or task_id or selected_option_id or trace_index is not None:
        raise StudioReviewPacketError("no reviewable trace matched the requested selector")
    return traces[0]


def infer_review_defaults(trace: dict[str, Any]) -> dict[str, Any]:
    selected = text_or_none(trace.get("selected_option_id")) or "operator_labeled_build"
    normalized = selected.lower()
    build_kind = "build"
    material = "stone"
    case_hint = safe_slug(selected)
    if "fire" in normalized:
        build_kind = "fire"
        material = "fire"
        case_hint = "fire_only_strict"
    elif "tnt" in normalized:
        build_kind = "wall"
        material = "tnt"
        case_hint = "tnt_wall"
    elif "path" in normalized:
        build_kind = "path"
        material = "stone"
        case_hint = "path_to_hill"
    elif "bridge" in normalized or "platform" in normalized:
        build_kind = "platform"
        material = "stone"
    elif any(value in normalized for value in ("cabin", "house", "shelter")):
        build_kind = "cabin"
        material = "wood"
    elif "village" in normalized:
        build_kind = "village"
        material = "wood"
    planned = trace.get("planned_node_writes")
    planned_writes = planned if isinstance(planned, int) and planned >= 0 else 0
    return {
        "case_hint": case_hint,
        "build_kind": build_kind,
        "material": material,
        "planned_writes": planned_writes,
    }


def build_expected(
    trace: dict[str, Any],
    *,
    case_hint: str | None,
    build_kind: str | None,
    build_material_name: str | None,
    planned_node_writes: int | None,
) -> tuple[dict[str, Any], str]:
    defaults = infer_review_defaults(trace)
    selected = text_or_none(trace.get("selected_option_id")) or defaults["case_hint"]
    resolved_case_hint = safe_slug(case_hint or defaults["case_hint"])
    resolved_writes = planned_node_writes if planned_node_writes is not None else defaults["planned_writes"]
    expected = {
        "action": "build",
        "build_kind": safe_slug(build_kind or defaults["build_kind"], defaults["build_kind"]),
        "build_material_name": safe_slug(build_material_name or defaults["material"], defaults["material"]),
        "planned_node_writes": max(0, int(resolved_writes)),
        "route": "agentic_build_planner",
        "selected_candidate_id": selected,
        "danger_refusal_allowed": False,
        "forbidden_extra_structure": True,
    }
    safe_expected = eval_queue.safe_expected_from_operator_label(expected)
    if safe_expected is None:
        raise StudioReviewPacketError("review packet expected build behavior is invalid")
    return safe_expected, resolved_case_hint


def build_review_command(trace: dict[str, Any], expected: dict[str, Any], case_hint: str) -> str:
    trace_id = selected_trace_id(trace)
    target = f"trace={trace_id}" if trace_id else "last"
    pieces = [
        target,
        f"case={safe_slug(case_hint)}",
        f"build_kind={expected['build_kind']}",
        f"material={expected['build_material_name']}",
        f"planned_writes={expected['planned_node_writes']}",
        f"route={expected['route']}",
        f"selected_candidate={safe_slug(expected['selected_candidate_id'], 'selected_candidate')}",
        "danger_refusal_allowed=false",
        "forbidden_extra_structure=true",
    ]
    return f"/ai_agent_feedback {'; '.join(pieces)}"


def build_review_packet(
    status: dict[str, Any],
    *,
    trace_id: str | None = None,
    task_id: str | None = None,
    selected_option_id: str | None = None,
    trace_index: int | None = None,
    case_hint: str | None = None,
    build_kind: str | None = None,
    build_material_name: str | None = None,
    planned_node_writes: int | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    trace = select_trace(
        status,
        trace_id=trace_id,
        task_id=task_id,
        selected_option_id=selected_option_id,
        trace_index=trace_index,
    )
    expected, resolved_case_hint = build_expected(
        trace,
        case_hint=case_hint,
        build_kind=build_kind,
        build_material_name=build_material_name,
        planned_node_writes=planned_node_writes,
    )
    packet = {
        "schema_version": 1,
        "artifact_kind": STUDIO_REVIEW_PACKET_KIND,
        "generated_at": generated_at or utc_now(),
        "source": {
            "source": "openrealm_studio_status",
            "source_trace_id": selected_trace_id(trace),
            "task_id": text_or_none(trace.get("task_id")),
            "agent_id": text_or_none(trace.get("agent_id")),
            "selected_option_id": text_or_none(trace.get("selected_option_id")),
            "tool_decision_source": text_or_none(trace.get("tool_decision_source")),
            "web_search_available": trace.get("web_search_available") is True,
            "world_mutation_authority": text_or_none(trace.get("world_mutation_authority")),
            "public_safe_trace_summary": True,
        },
        "operator_feedback_command": build_review_command(trace, expected, resolved_case_hint),
        "expected": expected,
        "safety": {
            "public_safe_output": True,
            "no_world_mutation": True,
            "no_raw_assets": True,
            "no_provider_prompts": True,
            "no_family_world_coordinates": True,
        },
    }
    if eval_queue.has_private_content(packet) or eval_queue.has_forbidden_key(packet):
        raise StudioReviewPacketError("review packet is not public-safe")
    return packet


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a public-safe OpenRealm Studio review packet from /api/status telemetry.",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--status-json", default=None, help="Path to a saved Studio /api/status JSON file.")
    source.add_argument("--status-url", default=None, help="URL for a Studio /api/status endpoint.")
    parser.add_argument("--trace-id", default=None, help="Specific source_trace_id to export, such as nova_trace:11.")
    parser.add_argument("--task-id", default=None, help="Specific task_id to export.")
    parser.add_argument("--selected-option-id", default=None, help="Specific selected_option_id to export.")
    parser.add_argument("--trace-index", type=int, default=None, help="Zero-based index among reviewable traces.")
    parser.add_argument("--case-hint", default=None, help="Override prompt-memory case hint.")
    parser.add_argument("--build-kind", default=None, help="Override expected build kind.")
    parser.add_argument("--build-material-name", default=None, help="Override expected material.")
    parser.add_argument("--planned-node-writes", type=int, default=None, help="Override expected planned write count.")
    parser.add_argument("--generated-at", default=None, help="ISO timestamp for deterministic artifacts.")
    parser.add_argument("--output", default=None, help="Optional output JSON path. Defaults to stdout packet JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        status = load_status_json(
            Path(args.status_json) if args.status_json else None,
            args.status_url,
        )
        packet = build_review_packet(
            status,
            trace_id=args.trace_id,
            task_id=args.task_id,
            selected_option_id=args.selected_option_id,
            trace_index=args.trace_index,
            case_hint=args.case_hint,
            build_kind=args.build_kind,
            build_material_name=args.build_material_name,
            planned_node_writes=args.planned_node_writes,
            generated_at=args.generated_at,
        )
        if args.output:
            output_path = Path(args.output)
            write_json(output_path, packet)
            print(json.dumps({
                "status": "ready",
                "output": str(output_path),
                "source_trace_id": packet["source"].get("source_trace_id"),
                "selected_option_id": packet["source"].get("selected_option_id"),
                "case_hint": case_hint_from_packet(packet),
            }, sort_keys=True))
        else:
            print(json.dumps(packet, indent=2, sort_keys=True))
    except StudioReviewPacketError as exc:
        print(json.dumps({"status": "fail", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 1
    return 0


def case_hint_from_packet(packet: dict[str, Any]) -> str | None:
    command = packet.get("operator_feedback_command")
    if not isinstance(command, str):
        return None
    for piece in command.replace(";", " ").split():
        if piece.startswith("case="):
            return piece.split("=", 1)[1]
    return None


if __name__ == "__main__":
    raise SystemExit(main())
