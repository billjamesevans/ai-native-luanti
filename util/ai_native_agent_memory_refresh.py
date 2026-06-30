#!/usr/bin/env python3
"""Refresh the reviewed prompt-memory artifacts used by the Agents SDK sidecar."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


sys.path.insert(0, str(Path(__file__).resolve().parent))
import ai_native_agent_eval_promote as eval_promote
import ai_native_agent_eval_queue as eval_queue


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return root / path


def relative_label(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_memory_artifacts(
    *,
    agents_sdk_logs: list[Path] | None = None,
    nova_agent_logs: list[Path] | None = None,
    action_logs: list[Path] | None = None,
    generated_at: str | None = None,
    candidate_queue_source_path: str | None = None,
    max_candidates: int = eval_queue.DEFAULT_MAX_CANDIDATES,
    max_candidate_queue_bytes: int = eval_queue.DEFAULT_MAX_BYTES,
    max_cases: int = eval_promote.DEFAULT_MAX_CASES,
    max_case_pack_bytes: int = eval_promote.DEFAULT_MAX_BYTES,
) -> tuple[dict[str, Any], dict[str, Any]]:
    candidate_queue = eval_queue.build_eval_candidate_queue(
        agents_sdk_logs=agents_sdk_logs or [],
        nova_agent_logs=nova_agent_logs or [],
        action_logs=action_logs or [],
        generated_at=generated_at,
        max_candidates=max(0, max_candidates),
        max_bytes=max(1000, max_candidate_queue_bytes),
    )
    case_pack = eval_promote.build_case_pack(
        candidate_queue,
        generated_at=generated_at,
        source_path=candidate_queue_source_path,
        max_cases=max(0, max_cases),
        max_bytes=max(1000, max_case_pack_bytes),
    )
    return candidate_queue, case_pack


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh public-safe sidecar memory artifacts from Nova/Agents logs.",
    )
    parser.add_argument("--root", default=".", help="Repository root for relative paths.")
    parser.add_argument("--agents-sdk-log", action="append", default=[], help="Agents SDK adapter JSONL log path.")
    parser.add_argument("--nova-agent-log", action="append", default=[], help="Nova sidecar request JSONL log path.")
    parser.add_argument("--action-log", action="append", default=[], help="Luanti action/debug log path containing request_trace JSON.")
    parser.add_argument("--candidate-queue-output", required=True, help="Output candidate queue JSON path.")
    parser.add_argument("--case-pack-output", required=True, help="Output prompt-memory case pack JSON path.")
    parser.add_argument("--generated-at", default=None, help="ISO timestamp for deterministic artifacts.")
    parser.add_argument("--max-candidates", type=int, default=eval_queue.DEFAULT_MAX_CANDIDATES)
    parser.add_argument("--max-candidate-queue-bytes", type=int, default=eval_queue.DEFAULT_MAX_BYTES)
    parser.add_argument("--max-cases", type=int, default=eval_promote.DEFAULT_MAX_CASES)
    parser.add_argument("--max-case-pack-bytes", type=int, default=eval_promote.DEFAULT_MAX_BYTES)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    root = resolve_path(Path.cwd(), args.root).resolve()
    agents_sdk_logs = [resolve_path(root, path) for path in args.agents_sdk_log]
    nova_agent_logs = [resolve_path(root, path) for path in args.nova_agent_log]
    action_logs = [resolve_path(root, path) for path in args.action_log]
    candidate_queue_output = resolve_path(root, args.candidate_queue_output)
    case_pack_output = resolve_path(root, args.case_pack_output)

    candidate_queue, case_pack = build_memory_artifacts(
        agents_sdk_logs=agents_sdk_logs,
        nova_agent_logs=nova_agent_logs,
        action_logs=action_logs,
        generated_at=args.generated_at,
        candidate_queue_source_path=relative_label(root, candidate_queue_output),
        max_candidates=args.max_candidates,
        max_candidate_queue_bytes=args.max_candidate_queue_bytes,
        max_cases=args.max_cases,
        max_case_pack_bytes=args.max_case_pack_bytes,
    )
    write_json(candidate_queue_output, candidate_queue)
    write_json(case_pack_output, case_pack)

    summary = {
        "candidate_queue": relative_label(root, candidate_queue_output),
        "candidate_queue_status": candidate_queue.get("status"),
        "case_pack": relative_label(root, case_pack_output),
        "case_pack_status": case_pack.get("status"),
        "cases_total": case_pack.get("summary", {}).get("cases_total", 0),
    }
    print(json.dumps(summary, sort_keys=True))
    return 0 if "fail" not in {candidate_queue.get("status"), case_pack.get("status")} else 1


if __name__ == "__main__":
    raise SystemExit(main())
