#!/usr/bin/env python3
"""Create reviewed operator-label artifacts for Nova prompt-memory refreshes."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ai_native_agent_eval_queue as eval_queue


OPERATOR_LABEL_SCHEMA_VERSION = 1
MAX_LABELS = 1
SLUG_RE = re.compile(r"[^a-z0-9_]+")


class OperatorLabelError(ValueError):
    """Raised when an operator-label artifact cannot be safely created."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return root / path


def relative_label(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else path.name


def slug(value: str, *, fallback: str = "operator_labeled") -> str:
    text = SLUG_RE.sub("_", value.strip().lower()).strip("_")
    return text or fallback


def stable_label_id(
    *,
    candidate_id: str | None,
    prompt: str | None,
    case_hint: str,
    expected: dict[str, Any],
) -> str:
    seed = {
        "candidate_id": candidate_id,
        "prompt": eval_queue.normalized_prompt(prompt),
        "case_hint": case_hint,
        "expected": expected,
    }
    digest = hashlib.sha256(json.dumps(seed, sort_keys=True).encode("utf-8")).hexdigest()
    return f"reviewed_{slug(case_hint)}_{digest[:10]}"


def parse_optional_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"expected boolean, got {value!r}")


def load_candidate_queue(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise OperatorLabelError("candidate queue not found") from exc
    except json.JSONDecodeError as exc:
        raise OperatorLabelError("candidate queue is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise OperatorLabelError("candidate queue must be a JSON object")
    if payload.get("artifact_kind") != eval_queue.REPORT_KIND:
        raise OperatorLabelError("candidate queue artifact_kind is invalid")
    if eval_queue.has_private_content(payload) or eval_queue.has_forbidden_key(payload):
        raise OperatorLabelError("candidate queue is not public-safe")
    return payload


def candidate_matches(
    candidate: dict[str, Any],
    *,
    candidate_id: str | None,
    prompt: str | None,
    source_kind: str | None,
) -> bool:
    if source_kind and candidate.get("source_kind") != source_kind:
        return False
    if candidate_id:
        return candidate.get("candidate_id") == candidate_id
    return eval_queue.normalized_prompt(candidate.get("prompt")) == eval_queue.normalized_prompt(prompt)


def find_candidate(
    candidate_queue: dict[str, Any],
    *,
    candidate_id: str | None = None,
    prompt: str | None = None,
    source_kind: str | None = None,
) -> dict[str, Any] | None:
    candidates = candidate_queue.get("candidates")
    if not isinstance(candidates, list):
        return None
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        if candidate_matches(candidate, candidate_id=candidate_id, prompt=prompt, source_kind=source_kind):
            return candidate
    return None


def expected_build_behavior(
    *,
    build_kind: str,
    build_material_name: str,
    build_material_node: str | None = None,
    planned_node_writes: int | None = None,
    route: str | None = None,
    selected_candidate_id: str | None = None,
    build_width: int | None = None,
    build_depth: int | None = None,
    build_height: int | None = None,
    build_count: int | None = None,
    danger_refusal_allowed: bool | None = None,
    forbidden_extra_structure: bool | None = None,
) -> dict[str, Any]:
    expected: dict[str, Any] = {
        "action": "build",
        "build_kind": build_kind,
        "build_material_name": build_material_name,
    }
    if build_material_node:
        expected["build_material_node"] = build_material_node
    if planned_node_writes is not None:
        expected["planned_node_writes"] = planned_node_writes
    if route:
        expected["route"] = route
    if selected_candidate_id:
        expected["selected_candidate_id"] = selected_candidate_id
    if build_width is not None:
        expected["build_width"] = build_width
    if build_depth is not None:
        expected["build_depth"] = build_depth
    if build_height is not None:
        expected["build_height"] = build_height
    if build_count is not None:
        expected["build_count"] = build_count
    if danger_refusal_allowed is not None:
        expected["danger_refusal_allowed"] = danger_refusal_allowed
    if forbidden_extra_structure is not None:
        expected["forbidden_extra_structure"] = forbidden_extra_structure
    safe_expected = eval_queue.safe_expected_from_operator_label(expected)
    if safe_expected is None:
        raise OperatorLabelError("expected build behavior is invalid")
    return safe_expected


def build_operator_label_artifact(
    *,
    candidate_queue: dict[str, Any],
    candidate_queue_path: str,
    candidate_id: str | None = None,
    prompt: str | None = None,
    source_kind: str | None = None,
    case_hint: str | None = None,
    label_id: str | None = None,
    expected: dict[str, Any],
    allow_unmatched: bool = False,
    generated_at: str | None = None,
) -> dict[str, Any]:
    if not candidate_id and not prompt:
        raise OperatorLabelError("candidate_id or prompt is required")
    if eval_queue.has_private_content(candidate_queue) or eval_queue.has_forbidden_key(candidate_queue):
        raise OperatorLabelError("candidate queue is not public-safe")
    matched = find_candidate(
        candidate_queue,
        candidate_id=candidate_id,
        prompt=prompt,
        source_kind=source_kind,
    )
    if matched is None and not allow_unmatched:
        raise OperatorLabelError("no matching candidate found")
    if matched is not None:
        candidate_id = str(matched.get("candidate_id") or candidate_id or "")
        prompt = str(matched.get("prompt") or prompt or "")
        source_kind = str(matched.get("source_kind") or source_kind or "")
    safe_expected = eval_queue.safe_expected_from_operator_label(expected)
    if safe_expected is None:
        raise OperatorLabelError("expected build behavior is invalid")
    case_hint = slug(case_hint or f"operator_labeled_{safe_expected['build_material_name']}_{safe_expected['build_kind']}")
    label_id = label_id or stable_label_id(
        candidate_id=candidate_id,
        prompt=prompt,
        case_hint=case_hint,
        expected=safe_expected,
    )
    label: dict[str, Any] = {
        "label_id": label_id,
        "case_hint": case_hint,
        "expected": safe_expected,
    }
    if candidate_id:
        label["candidate_id"] = candidate_id
    if prompt:
        label["prompt"] = prompt
    if source_kind:
        label["source_kind"] = source_kind
    artifact = {
        "schema_version": OPERATOR_LABEL_SCHEMA_VERSION,
        "artifact_kind": eval_queue.OPERATOR_LABEL_KIND,
        "generated_at": generated_at or utc_now(),
        "source": {
            "candidate_queue": candidate_queue_path,
            "matched_candidate_id": matched.get("candidate_id") if matched else None,
            "matched": matched is not None,
        },
        "labels": [label],
        "safety": {
            "public_safe_output": True,
            "operator_reviewed": True,
            "no_world_mutation": True,
            "max_labels": MAX_LABELS,
        },
    }
    if eval_queue.has_private_content(artifact) or eval_queue.has_forbidden_key(artifact):
        raise OperatorLabelError("operator-label artifact is not public-safe")
    return artifact


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create one reviewed public-safe Nova operator-label artifact.",
    )
    parser.add_argument("--root", default=".", help="Repository root for relative paths.")
    parser.add_argument("--candidate-queue", required=True, help="Input candidate queue JSON path.")
    parser.add_argument("--output", required=True, help="Output operator-label JSON path.")
    parser.add_argument("--candidate-id", default=None, help="Candidate id to label.")
    parser.add_argument("--prompt", default=None, help="Candidate prompt to label when candidate id is not supplied.")
    parser.add_argument("--source-kind", default=None, help="Optional source_kind match guard.")
    parser.add_argument("--case-hint", default=None, help="Prompt-memory case hint.")
    parser.add_argument("--label-id", default=None, help="Stable reviewed label id.")
    parser.add_argument("--build-kind", required=True, help="Expected build kind, such as fire, wall, or platform.")
    parser.add_argument("--build-material-name", required=True, help="Expected material name, such as fire or tnt.")
    parser.add_argument("--build-material-node", default=None, help="Optional expected Luanti node name.")
    parser.add_argument("--planned-node-writes", type=int, default=None, help="Expected planned write count.")
    parser.add_argument("--route", default=None, help="Optional expected route.")
    parser.add_argument("--selected-candidate-id", default=None, help="Optional expected selected candidate id.")
    parser.add_argument("--build-width", type=int, default=None, help="Optional expected build width.")
    parser.add_argument("--build-depth", type=int, default=None, help="Optional expected build depth.")
    parser.add_argument("--build-height", type=int, default=None, help="Optional expected build height.")
    parser.add_argument("--build-count", type=int, default=None, help="Optional expected build count.")
    parser.add_argument("--danger-refusal-allowed", type=parse_optional_bool, default=None)
    parser.add_argument("--forbidden-extra-structure", type=parse_optional_bool, default=None)
    parser.add_argument("--allow-unmatched", action="store_true", help="Create the label even if the candidate is absent.")
    parser.add_argument("--generated-at", default=None, help="ISO timestamp for deterministic artifacts.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    root = resolve_path(Path.cwd(), args.root).resolve()
    candidate_queue_path = resolve_path(root, args.candidate_queue)
    output = resolve_path(root, args.output)
    try:
        candidate_queue = load_candidate_queue(candidate_queue_path)
        expected = expected_build_behavior(
            build_kind=args.build_kind,
            build_material_name=args.build_material_name,
            build_material_node=args.build_material_node,
            planned_node_writes=args.planned_node_writes,
            route=args.route,
            selected_candidate_id=args.selected_candidate_id,
            build_width=args.build_width,
            build_depth=args.build_depth,
            build_height=args.build_height,
            build_count=args.build_count,
            danger_refusal_allowed=args.danger_refusal_allowed,
            forbidden_extra_structure=args.forbidden_extra_structure,
        )
        artifact = build_operator_label_artifact(
            candidate_queue=candidate_queue,
            candidate_queue_path=relative_label(root, candidate_queue_path),
            candidate_id=args.candidate_id,
            prompt=args.prompt,
            source_kind=args.source_kind,
            case_hint=args.case_hint,
            label_id=args.label_id,
            expected=expected,
            allow_unmatched=args.allow_unmatched,
            generated_at=args.generated_at,
        )
        write_json(output, artifact)
    except OperatorLabelError as exc:
        print(json.dumps({"status": "fail", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 1

    label = artifact["labels"][0]
    summary = {
        "status": "ready",
        "output": relative_label(root, output),
        "labels_total": len(artifact["labels"]),
        "label_id": label.get("label_id"),
        "candidate_id": label.get("candidate_id"),
        "prompt": label.get("prompt"),
        "case_hint": label.get("case_hint"),
        "matched": artifact.get("source", {}).get("matched"),
    }
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
