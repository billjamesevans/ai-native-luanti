#!/usr/bin/env python3
"""Probe receipt-gated task cancel/retry against a disposable live ai_runtime queue."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIVE_ARTIFACT_NAME = "ai-runtime-operator-task-control-live-result.json"
LIVE_RESULT_NAME = "ai-runtime-operator-taREDACTED_KEY_FIXTURE.json"
PROBE_MOD_NAME = "ai_operator_task_control_live_probe"
DEFAULT_MAX_BYTES = 22000

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


def lua_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def lua_long_string(value: str) -> str:
    return f"[=[{value}]=]"


def reserve_udp_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


def resolve_path(root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return root / path


def sample_live_receipt(generated_at: str) -> dict:
    def task_decision(
        decision_id: str,
        target_id: str,
        approval_kind: str,
        safe_next_action: str,
        *,
        decision_status: str = "approved",
        prerequisites_required: list[str] | None = None,
        prerequisites_acknowledged: list[str] | None = None,
    ) -> dict:
        required = prerequisites_required or [
            "inspect_task_status",
            "confirm_task_owner_and_capabilities",
        ]
        acknowledged = prerequisites_acknowledged if prerequisites_acknowledged is not None else required
        return {
            "decision_id": decision_id,
            "decision_status": decision_status,
            "target_kind": "task",
            "target_id": target_id,
            "target_status": "running" if approval_kind == "task_cancel_retry_review" else "blocked",
            "safe_next_action": safe_next_action,
            "approval_kind": approval_kind,
            "required_capabilities": ["task.inspect", f"{approval_kind}.capability"],
            "prerequisites_required": required,
            "prerequisites_acknowledged": acknowledged,
            "operator_note": "disposable live queue probe",
            "references": {"task_ids": [target_id], "rollback_records": [], "source_artifacts": []},
            "approval_required": True,
            "dry_run_only": True,
            "will_mutate": False,
            "mutation_performed": False,
            "receipt_only": True,
        }

    decisions = [
        task_decision(
            "decision:cancel-live-running",
            "task:live-cancel",
            "task_cancel_retry_review",
            "inspect_task_before_action",
        ),
        task_decision(
            "decision:retry-live-blocked",
            "task:live-retry",
            "task_retry_review",
            "review_blocked_task_before_retry",
            prerequisites_required=["inspect_blocked_result", "confirm_retry_budget"],
        ),
        task_decision(
            "decision:denied-live",
            "task:live-denied",
            "task_retry_review",
            "review_blocked_task_before_retry",
            decision_status="denied",
            prerequisites_required=["inspect_blocked_result", "confirm_retry_budget"],
        ),
        {
            "decision_id": "decision:rollback-live-rejected",
            "decision_status": "approved",
            "target_kind": "rollback",
            "target_id": "rollback:live-record",
            "target_status": "available",
            "safe_next_action": "review_rollback_record_before_execution",
            "approval_kind": "rollback_execution_review",
            "required_capabilities": ["rollback.review", "rollback.execute.review"],
            "prerequisites_required": ["inspect_rollback_record", "confirm_rollback_scope"],
            "prerequisites_acknowledged": ["inspect_rollback_record", "confirm_rollback_scope"],
            "operator_note": "must not execute in live task-control probe",
            "references": {"task_ids": [], "rollback_records": ["rollback:live-record"]},
            "approval_required": True,
            "dry_run_only": True,
            "will_mutate": False,
            "mutation_performed": False,
            "receipt_only": True,
        },
        {
            "decision_id": "decision:import-live-rejected",
            "decision_status": "approved",
            "target_kind": "import_promotion",
            "target_id": "promotion:live-ready",
            "target_status": "ready",
            "safe_next_action": "review_promotion_package_before_apply",
            "approval_kind": "import_apply_review",
            "required_capabilities": ["import.promotion.review", "import.apply.review"],
            "prerequisites_required": ["inspect_promotion_package", "confirm_operator_approval"],
            "prerequisites_acknowledged": ["inspect_promotion_package", "confirm_operator_approval"],
            "operator_note": "must not execute in live task-control probe",
            "references": {"task_ids": [], "source_artifacts": ["promotion:live-ready"]},
            "approval_required": True,
            "dry_run_only": True,
            "will_mutate": False,
            "mutation_performed": False,
            "receipt_only": True,
        },
    ]
    return {
        "schema_version": 1,
        "receipt_kind": "ai_native_operator_action_approval_receipt",
        "status": "attention",
        "generated_at": generated_at,
        "source_plan": {
            "plan_kind": "ai_native_operator_action_approval_plan",
            "status": "attention",
            "generated_at": generated_at,
        },
        "operator_decisions": {
            "mode": "receipt_only",
            "operator_id": "operator:task-control-live-probe",
            "mutation_performed": False,
            "decisions_total": len(decisions),
            "approved_total": 4,
            "denied_total": 1,
            "needs_review_total": 0,
            "truncated": False,
        },
        "summary": {
            "decisions_total": len(decisions),
            "source_actions_total": len(decisions),
            "by_decision_status": {"approved": 4, "denied": 1},
            "by_target_kind": {"task": 3, "rollback": 1, "import_promotion": 1},
            "by_approval_kind": {
                "task_cancel_retry_review": 1,
                "task_retry_review": 2,
                "rollback_execution_review": 1,
                "import_apply_review": 1,
            },
            "attention_required": True,
        },
        "decisions": decisions,
        "safety": {
            "public_safe_output": True,
            "dry_run_only": True,
            "approval_required": True,
            "receipt_only": True,
            "no_mutating_actions": True,
            "no_world_mutation": True,
            "no_rollback_execution": True,
            "no_import_promotion_execution": True,
            "no_raw_assets": True,
            "no_provider_prompts": True,
            "no_family_world_coordinates": True,
        },
        "bounds": {
            "max_bytes": DEFAULT_MAX_BYTES,
            "output_bytes": 4000,
            "truncated": False,
        },
    }


def write_probe_world(world_dir: Path, generated_at: str, max_bytes: int) -> None:
    if world_dir.exists():
        shutil.rmtree(world_dir)
    mod_dir = world_dir / "worldmods" / PROBE_MOD_NAME
    mod_dir.mkdir(parents=True, exist_ok=True)
    (world_dir / "world.mt").write_text(
        "\n".join([
            "gameid = ai_runtime",
            "backend = sqlite3",
            "player_backend = sqlite3",
            "auth_backend = sqlite3",
            "",
        ]),
        encoding="utf-8",
    )
    (mod_dir / "mod.conf").write_text(f"name = {PROBE_MOD_NAME}\n", encoding="utf-8")
    receipt_json = json.dumps(sample_live_receipt(generated_at), sort_keys=True)
    (mod_dir / "init.lua").write_text(
        "\n".join([
            "local output_path = core.get_worldpath() .. " + lua_string("/" + LIVE_ARTIFACT_NAME),
            "local result_path = core.get_worldpath() .. " + lua_string("/" + LIVE_RESULT_NAME),
            "local generated_at = " + lua_string(generated_at),
            f"local max_bytes = {int(max_bytes)}",
            "local receipt = core.parse_json(" + lua_long_string(receipt_json) + ")",
            "local executor_capabilities = {",
            "  [\"task.inspect\"] = true,",
            "  [\"task.cancel\"] = true,",
            "  [\"task.retry\"] = true,",
            "}",
            "",
            "local function write_result(status, reason)",
            "  core.safe_file_write(result_path, core.write_json({",
            "    status = status,",
            "    reason = reason,",
            "    execution_path = \"disposable_live_ai_runtime_queue_probe\",",
            "  }))",
            "end",
            "",
            "local function sorted_counts(values)",
            "  local counts = {}",
            "  for _, value in ipairs(values) do",
            "    counts[value] = (counts[value] or 0) + 1",
            "  end",
            "  return counts",
            "end",
            "",
            "local function register_probe_agent()",
            "  if core.registered_ai_agents[\"operator_task_control:probe\"] then",
            "    return",
            "  end",
            "  core.register_ai_agent({",
            "    agent_id = \"operator_task_control:probe\",",
            "    display_name = \"Operator Task Control Probe\",",
            "    owner = \"operator_task_control_probe\",",
            "    plugin = \"operator_task_control_live_probe\",",
            "    state = \"enabled\",",
            "    capabilities = { [\"world.read\"] = true, [\"task.cancel\"] = true },",
            "  })",
            "end",
            "",
            "local retry_attempts = 0",
            "local denied_attempts = 0",
            "local function seed_tasks()",
            "  register_probe_agent()",
            "  core.queue_ai_task({",
            "    task_id = \"task:live-retry\",",
            "    agent_id = \"operator_task_control:probe\",",
            "    owner = \"operator_task_control_probe\",",
            "    label = \"live retry probe\",",
            "    steps = {",
            "      function()",
            "        retry_attempts = retry_attempts + 1",
            "        if retry_attempts == 1 then",
            "          return { ok = false, status = \"blocked\", reason = \"probe_blocked\" }",
            "        end",
            "        return { ok = true, status = \"success\", changed = 0 }",
            "      end,",
            "    },",
            "  })",
            "  core.step_ai_tasks()",
            "  core.queue_ai_task({",
            "    task_id = \"task:live-denied\",",
            "    agent_id = \"operator_task_control:probe\",",
            "    owner = \"operator_task_control_probe\",",
            "    label = \"live denied probe\",",
            "    steps = {",
            "      function()",
            "        denied_attempts = denied_attempts + 1",
            "        return { ok = false, status = \"blocked\", reason = \"denied_probe_blocked\" }",
            "      end,",
            "    },",
            "  })",
            "  core.step_ai_tasks()",
            "  core.queue_ai_task({",
            "    task_id = \"task:live-cancel\",",
            "    agent_id = \"operator_task_control:probe\",",
            "    owner = \"operator_task_control_probe\",",
            "    label = \"live cancel probe\",",
            "    budget = { max_steps_per_step = 1 },",
            "    steps = {",
            "      function() return { ok = true, status = \"success\", changed = 0 } end,",
            "      function() return { ok = true, status = \"success\", changed = 0 } end,",
            "    },",
            "  })",
            "  core.step_ai_tasks()",
            "end",
            "",
            "local function task_status(task_id)",
            "  local task = core.get_ai_task(task_id)",
            "  return task and task.status or \"missing\"",
            "end",
            "",
            "local function task_retry_count(task_id)",
            "  local task = core.get_ai_task(task_id)",
            "  return task and (task.retry_count or 0) or 0",
            "end",
            "",
            "local function result_base(decision)",
            "  return {",
            "    decision_id = decision.decision_id,",
            "    decision_status = decision.decision_status,",
            "    target_kind = decision.target_kind,",
            "    target_id = decision.target_id,",
            "    approval_kind = decision.approval_kind,",
            "    safe_next_action = decision.safe_next_action,",
            "  }",
            "end",
            "",
            "local function reject(decision, reason)",
            "  local item = result_base(decision)",
            "  item.status = \"rejected\"",
            "  item.reason = reason",
            "  item.operation = \"none\"",
            "  item.mutation_performed = false",
            "  return item",
            "end",
            "",
            "local function missing_prerequisite(decision)",
            "  local acknowledged = {}",
            "  for _, value in ipairs(decision.prerequisites_acknowledged or {}) do",
            "    acknowledged[value] = true",
            "  end",
            "  for _, value in ipairs(decision.prerequisites_required or {}) do",
            "    if not acknowledged[value] then",
            "      return true",
            "    end",
            "  end",
            "  return false",
            "end",
            "",
            "local function execute_decision(decision)",
            "  if decision.decision_status ~= \"approved\" then",
            "    return reject(decision, \"decision_not_approved\")",
            "  end",
            "  if decision.target_kind ~= \"task\" then",
            "    return reject(decision, \"unsupported_approval_kind\")",
            "  end",
            "  if decision.approval_kind ~= \"task_cancel_retry_review\"",
            "      and decision.approval_kind ~= \"task_retry_review\" then",
            "    return reject(decision, \"unsupported_approval_kind\")",
            "  end",
            "  if missing_prerequisite(decision) then",
            "    return reject(decision, \"missing_acknowledged_prerequisite\")",
            "  end",
            "  local operation = decision.approval_kind == \"task_cancel_retry_review\"",
            "    and \"task.cancel\" or \"task.retry\"",
            "  if not executor_capabilities[operation] or not executor_capabilities[\"task.inspect\"] then",
            "    return reject(decision, \"missing_executor_capability\")",
            "  end",
            "  local before_status = task_status(decision.target_id)",
            "  local action_result",
            "  if operation == \"task.cancel\" then",
            "    action_result = core.cancel_ai_task(decision.target_id, \"operator_task_control_probe\")",
            "  else",
            "    action_result = core.retry_ai_task(decision.target_id, \"operator_task_control_probe\")",
            "  end",
            "  if not action_result or action_result.ok ~= true then",
            "    return reject(decision, action_result and action_result.reason or \"task_action_failed\")",
            "  end",
            "  local item = result_base(decision)",
            "  item.status = \"executed\"",
            "  item.reason = \"approved_receipt\"",
            "  item.operation = operation",
            "  item.before_status = before_status",
            "  item.after_status = task_status(decision.target_id)",
            "  item.mutation_performed = true",
            "  item.mutation_scope = \"disposable_live_task_queue\"",
            "  return item",
            "end",
            "",
            "local function task_summary(task_id)",
            "  return {",
            "    task_id = task_id,",
            "    status = task_status(task_id),",
            "    retry_count = task_retry_count(task_id),",
            "  }",
            "end",
            "",
            "local function build_payload(results)",
            "  local statuses = {}",
            "  local operations = {}",
            "  local rejection_reasons = {}",
            "  local executed_total = 0",
            "  local rejected_total = 0",
            "  for _, item in ipairs(results) do",
            "    statuses[#statuses + 1] = item.status",
            "    operations[#operations + 1] = item.operation or \"none\"",
            "    if item.status == \"executed\" then",
            "      executed_total = executed_total + 1",
            "    elseif item.status == \"rejected\" then",
            "      rejected_total = rejected_total + 1",
            "      rejection_reasons[#rejection_reasons + 1] = item.reason or \"unknown\"",
            "    end",
            "  end",
            "  local payload = {",
            "    schema_version = 1,",
            "    live_result_kind = \"ai_native_operator_task_control_live_result\",",
            "    generated_at = generated_at,",
            "    runtime_context = {",
            "      mode = \"disposable_live_ai_runtime_task_control_probe\",",
            "      gameid = \"ai_runtime\",",
            "      requires_live_pi = false,",
            "      requires_private_world = false,",
            "      world_mutation_performed = false,",
            "    },",
            "    source_receipt = {",
            "      receipt_kind = receipt.receipt_kind,",
            "      status = receipt.status,",
            "      generated_at = receipt.generated_at,",
            "    },",
            "    operator_actions = {",
            "      mode = \"receipt_gated_live_task_control\",",
            "      mutation_performed = executed_total > 0,",
            "      task_queue_mutation_performed = executed_total > 0,",
            "      world_mutation_performed = false,",
            "      allowed_approval_kinds = { \"task_cancel_retry_review\", \"task_retry_review\" },",
            "      executor_capabilities = { \"task.cancel\", \"task.inspect\", \"task.retry\" },",
            "    },",
            "    summary = {",
            "      decisions_total = #(receipt.decisions or {}),",
            "      executed_total = executed_total,",
            "      rejected_total = rejected_total,",
            "      skipped_total = 0,",
            "      by_result_status = sorted_counts(statuses),",
            "      by_operation = sorted_counts(operations),",
            "      by_rejection_reason = sorted_counts(rejection_reasons),",
            "      attention_required = rejected_total > 0,",
            "    },",
            "    results = results,",
            "    live_task_state_after = {",
            "      tasks = {",
            "        task_summary(\"task:live-cancel\"),",
            "        task_summary(\"task:live-retry\"),",
            "        task_summary(\"task:live-denied\"),",
            "      },",
            "    },",
            "    safety = {",
            "      public_safe_output = true,",
            "      receipt_required = true,",
            "      receipt_gated = true,",
            "      disposable_live_world_only = true,",
            "      live_queue_probe_only = true,",
            "      task_control_only = true,",
            "      task_queue_mutation_only = true,",
            "      world_mutation_performed = false,",
            "      no_world_mutation = true,",
            "      no_rollback_execution = true,",
            "      no_import_promotion_execution = true,",
            "      no_structure_apply = true,",
            "      no_raw_assets = true,",
            "      no_provider_prompts = true,",
            "      no_family_world_coordinates = true,",
            "    },",
            "    bounds = { max_bytes = max_bytes, output_bytes = 0, truncated = false },",
            "  }",
            "  payload.bounds.output_bytes = #core.write_json(payload)",
            "  return payload",
            "end",
            "",
            "core.register_on_mods_loaded(function()",
            "  if type(core.retry_ai_task) ~= \"function\" then",
            "    write_result(\"fail\", \"core.retry_ai_task missing\")",
            "    core.request_shutdown(\"task control live probe failed\", false, 0)",
            "    return",
            "  end",
            "  seed_tasks()",
            "  local results = {}",
            "  for _, decision in ipairs(receipt.decisions or {}) do",
            "    results[#results + 1] = execute_decision(decision)",
            "  end",
            "  local payload = build_payload(results)",
            "  if payload.bounds.output_bytes > max_bytes then",
            "    write_result(\"fail\", \"live result exceeds max bytes\")",
            "    core.request_shutdown(\"task control live probe failed\", false, 0)",
            "    return",
            "  end",
            "  if not core.safe_file_write(output_path, core.write_json(payload)) then",
            "    write_result(\"fail\", \"live result artifact write failed\")",
            "    core.request_shutdown(\"task control live probe failed\", false, 0)",
            "    return",
            "  end",
            "  write_result(\"pass\", \"receipt-gated live task control captured\")",
            "  core.request_shutdown(\"task control live probe complete\", false, 0)",
            "end)",
            "",
        ]),
        encoding="utf-8",
    )


def read_result(world_dir: Path) -> dict:
    result_path = world_dir / LIVE_RESULT_NAME
    if not result_path.is_file():
        return {"status": "fail", "reason": "probe result missing"}
    try:
        return json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "fail", "reason": f"probe result unreadable: {type(exc).__name__}"}


def _artifact_has_private_content(payload: dict) -> bool:
    raw = json.dumps(payload, sort_keys=True)
    return any(pattern.search(raw) for pattern in PRIVATE_PATTERNS)


def validate_live_result(payload: dict, max_bytes: int = DEFAULT_MAX_BYTES) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("live task-control result must be an object")
    if payload.get("live_result_kind") != "ai_native_operator_task_control_live_result":
        raise ValueError("live task-control result kind is invalid")
    if _artifact_has_private_content(payload):
        raise ValueError("live task-control result contains private content")
    runtime_context = payload.get("runtime_context")
    if not isinstance(runtime_context, dict):
        raise ValueError("live task-control runtime_context missing or invalid")
    if runtime_context.get("mode") != "disposable_live_ai_runtime_task_control_probe":
        raise ValueError("live task-control runtime mode is invalid")
    if runtime_context.get("requires_live_pi") is not False:
        raise ValueError("live task-control result requires live Pi")
    if runtime_context.get("requires_private_world") is not False:
        raise ValueError("live task-control result requires private world")
    if runtime_context.get("world_mutation_performed") is not False:
        raise ValueError("live task-control result performed world mutation")

    actions = payload.get("operator_actions")
    if not isinstance(actions, dict):
        raise ValueError("live task-control operator_actions missing or invalid")
    if actions.get("mode") != "receipt_gated_live_task_control":
        raise ValueError("live task-control mode is invalid")
    if actions.get("world_mutation_performed") is not False:
        raise ValueError("live task-control result performed world mutation")

    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    for field in (
        "public_safe_output",
        "receipt_required",
        "receipt_gated",
        "disposable_live_world_only",
        "live_queue_probe_only",
        "task_control_only",
        "task_queue_mutation_only",
        "no_world_mutation",
        "no_rollback_execution",
        "no_import_promotion_execution",
        "no_structure_apply",
        "no_raw_assets",
        "no_provider_prompts",
        "no_family_world_coordinates",
    ):
        if safety.get(field) is not True:
            raise ValueError(f"live task-control safety {field} is not true")
    if safety.get("world_mutation_performed") is not False:
        raise ValueError("live task-control result performed world mutation")

    bounds = payload.get("bounds") if isinstance(payload.get("bounds"), dict) else {}
    output_bytes = bounds.get("output_bytes")
    declared_max = bounds.get("max_bytes", max_bytes)
    if not isinstance(output_bytes, int) or not isinstance(declared_max, int):
        raise ValueError("live task-control bounds are invalid")
    if output_bytes > declared_max or output_bytes > max_bytes:
        raise ValueError("live task-control output exceeds max bytes")

    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    for field in ("decisions_total", "executed_total", "rejected_total"):
        if not isinstance(summary.get(field), int):
            raise ValueError(f"live task-control summary {field} is invalid")
    if summary["decisions_total"] != 5:
        raise ValueError("live task-control decision count is invalid")
    if summary["executed_total"] != 2:
        raise ValueError("live task-control cancel/retry execution count is invalid")
    if summary["rejected_total"] != 3:
        raise ValueError("live task-control rejection count is invalid")
    operations = set()
    rejection_reasons = set()
    for item in payload.get("results") or []:
        if not isinstance(item, dict):
            continue
        if item.get("status") == "executed" and isinstance(item.get("operation"), str):
            operations.add(item["operation"])
        if item.get("status") == "rejected" and isinstance(item.get("reason"), str):
            rejection_reasons.add(item["reason"])
    if not {"task.cancel", "task.retry"}.issubset(operations):
        raise ValueError("live task-control did not execute cancel and retry")
    if "unsupported_approval_kind" not in rejection_reasons:
        raise ValueError("live task-control did not reject unsupported approval kinds")
    return {
        "operator_task_control_live_status": "pass",
        "operator_task_control_live_output_bytes": output_bytes,
        "operator_task_control_live_items": summary["decisions_total"],
        "operator_task_control_live_executed": summary["executed_total"],
        "operator_task_control_live_rejected": summary["rejected_total"],
        "operator_task_control_live_world_mutation": False,
    }


def run_probe(args) -> int:
    root = resolve_path(Path.cwd(), args.root).resolve()
    server_bin = resolve_path(root, args.server_bin)
    output = resolve_path(root, args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    world_dir = output.parent / "operator-task-control-live-world"
    write_probe_world(world_dir, args.generated_at, args.max_bytes)

    port = args.port or reserve_udp_port()
    log_path = world_dir / "debug.log"
    config_path = world_dir / "probe.conf"
    config_path.write_text(
        "\n".join([
            "server_name = AI Native Operator Task Control Live Probe",
            "name = operator_task_control_probe",
            "secure.enable_security = true",
            "creative_mode = false",
            "enable_damage = false",
            "",
        ]),
        encoding="utf-8",
    )
    command = [
        str(server_bin),
        "--world",
        str(world_dir),
        "--gameid",
        "ai_runtime",
        "--port",
        str(port),
        "--config",
        str(config_path),
        "--logfile",
        str(log_path),
        "--color",
        "never",
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
            timeout=args.timeout,
        )
    except subprocess.TimeoutExpired:
        print("operator task-control live probe timed out", file=sys.stderr)
        return 1
    if completed.returncode != 0:
        print("operator task-control live server exited with non-zero status", file=sys.stderr)
        if completed.stderr.strip():
            print(completed.stderr.strip()[-1200:], file=sys.stderr)
        return 1

    result = read_result(world_dir)
    if result.get("status") != "pass":
        reason = result.get("reason", "unknown")
        print(f"operator task-control live probe failed: {reason}", file=sys.stderr)
        return 1

    world_artifact = world_dir / LIVE_ARTIFACT_NAME
    if not world_artifact.is_file():
        print("operator task-control live artifact missing", file=sys.stderr)
        return 1
    try:
        payload = json.loads(world_artifact.read_text(encoding="utf-8"))
        validate_live_result(payload, max_bytes=args.max_bytes)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"operator task-control live artifact invalid: {type(exc).__name__}", file=sys.stderr)
        return 1
    shutil.copyfile(world_artifact, output)
    print("operator task-control live probe captured")
    return 0


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Capture receipt-gated task cancel/retry from a disposable ai_runtime queue."
    )
    parser.add_argument("--root", default=".", help="Luanti source checkout root.")
    parser.add_argument("--server-bin", default="bin/luantiserver", help="Server binary to launch.")
    parser.add_argument("--output", required=True, help="Output JSON artifact path.")
    parser.add_argument("--generated-at", required=True, help="generated_at value for the probe.")
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES, help="Output byte budget.")
    parser.add_argument("--timeout", type=float, default=20.0, help="Seconds to wait for probe shutdown.")
    parser.add_argument("--port", type=int, help="Optional UDP port for the disposable server.")
    return parser.parse_args(argv)


def main(argv=None):
    return run_probe(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
