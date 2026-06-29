# Operator Status Package

Status: operator-control contract for issue #162.

`util/ai_native_operator_status_package.py` emits bounded JSON for a future CLI/dashboard. The running server also exposes `/ai_runtime_operator_status` for the same operator-control shape from live runtime state. Both paths are read-only summary surfaces. Each does not mutate a world, does not execute rollback, does not apply imports, and does not load family-server content.

The package gives an operator one safe shape for:

- agent and capability inventory;
- task queue status;
- rollback record availability;
- dry-run-only operator-control recommendations with safe next actions;
- compatibility/import review and promotion package summaries;
- benchmark or verifier gate summaries;
- product-profile hygiene from `util/ai_native_product_profile_verify.py`.

## Command

Python package generator:

```sh
python3 util/ai_native_operator_status_package.py --root . --output local/operator-status.json
```

For tests or future adapters, pass synthetic/default state:

```sh
python3 util/ai_native_operator_status_package.py \
  --root . \
  --input local/operator-state.json \
  --output local/operator-status.json
```

The input is optional. When omitted, the package still reports product-profile hygiene and empty runtime sections.

Live server command:

```text
/ai_runtime_operator_status
```

The live command requires `server` privilege and returns compact JSON with `package_kind = "ai_native_operator_status_package"`. It summarizes registered agents, task counts, recent rollback/import audit availability, optional benchmark gates, `operator_control`, and product-profile hygiene. It rejects unknown parameters and accepts `generated_at=...` and `max_bytes=N` for reproducible checks.

## Boundary

The package is intentionally not a web dashboard. It is the stable report contract that a future CLI/dashboard can consume after the runtime surfaces mature.

The output must stay public-safe:

- no private server hosts or local paths;
- no player secrets;
- no provider prompts;
- no raw assets or asset payloads;
- no family-world coordinates;
- no `spacebase`, `themepark`, `showcase100`, or `disneyland100` content.

Runtime sections are summaries, not raw records. Rollback and import entries show ids, statuses, and review state; they do not embed rollback node snapshots, source asset bytes, or live-world payloads.

The `operator_control` section is read-only and dry-run-only. It exposes stable target IDs, target kinds, current statuses, and safe next actions such as `inspect_task_before_action`, `review_rollback_record_before_execution`, and `review_import_blocker`. These are action affordances for a future CLI/dashboard; this package does not cancel tasks, execute rollback, approve imports, apply structures, or mutate worlds.

## Operator-Control Report Adapter

`util/ai_native_operator_control_report.py` turns a live or recorded operator-status package into a smaller operator-control report adapter artifact. It accepts `ai-runtime-operator-status-live.json` or `ai-runtime-operator-status.json` and writes bounded JSON by default:

```sh
python3 util/ai_native_operator_control_report.py \
  --input local/benchmarks/local-mac/2026-06-29/run/ai-runtime-operator-status-live.json \
  --output local/benchmarks/local-mac/2026-06-29/run/ai-runtime-operator-control-report.json
```

Use `--format text` for a concise human-readable report. Both formats preserve the dry-run-only boundary, list stable target IDs, target kinds, current statuses, and safe next actions, and reject recommendations that advertise mutating actions. The adapter remains public-safe: it redacts private paths, private hosts or IPs, provider prompts, raw asset payload fields, and family-showcase names.

`util/ai_native_runtime_verify.py` writes `ai-runtime-operator-control-report.json` as a sibling artifact whenever it captures or generates an operator-status package. The verification manifest records the report path and pass/fail status so local and low-power lanes prove the adapter works against live operator-status evidence.

## Operator Action Approval Plan

The operator action approval plan is the next review layer after the operator-control report.
`util/ai_native_operator_action_approval_plan.py` turns the operator-control report into non-mutating approval-plan artifacts. It accepts `ai-runtime-operator-control-report.json` and writes `ai-runtime-operator-action-approval-plan.json`:

```sh
python3 util/ai_native_operator_action_approval_plan.py \
  --input local/benchmarks/local-mac/2026-06-29/run/ai-runtime-operator-control-report.json \
  --output local/benchmarks/local-mac/2026-06-29/run/ai-runtime-operator-action-approval-plan.json
```

The plan groups candidate operator actions by target kind, status, and safe next action. Each approval group records prerequisites, required review capabilities, rollback references, source artifact references, blocked reasons, and unsupported reasons. Current plans cover task cancel/retry review, rollback execution review, import blocker review, import promotion/apply review, and benchmark failure follow-up.

Approval-plan artifacts are review contracts, not execution controls. They preserve the dry-run-only boundary from the source report: no task mutation, no rollback execution, no import promotion execution, no world mutation, no raw assets, no provider prompts, and no family-world coordinates. Unknown safe-next-action values are held for manual operator review instead of becoming executable.

`util/ai_native_runtime_verify.py` writes `ai-runtime-operator-action-approval-plan.json` next to the raw status package and operator-control report. The manifest records `operator_action_approval_plan_status`, path, output bytes, and item count so local and low-power lanes prove the approval-plan adapter against live operator evidence.

## Operator Action Approval Receipt

The operator action approval receipt is the audit bridge between an approval plan and future execution controls. `util/ai_native_operator_action_approval_receipt.py` accepts an `ai_native_operator_action_approval_plan` plus an explicit operator decision document and writes receipt artifacts as `ai-runtime-operator-action-approval-receipt.json`:

```sh
python3 util/ai_native_operator_action_approval_receipt.py \
  --input local/benchmarks/local-mac/2026-06-29/run/ai-runtime-operator-action-approval-plan.json \
  --decision local/operator-action-decision.json \
  --output local/benchmarks/local-mac/2026-06-29/run/ai-runtime-operator-action-approval-receipt.json
```

Receipt artifacts record approval/denial state only. Each decision binds `approved`, `denied`, or `needs_review` to a plan entry by target kind, target id, and safe next action. The receipt repeats the approval kind, required capabilities, required prerequisites, acknowledged prerequisites, and source references so later execution code can require a durable operator decision instead of trusting a transient prompt or dashboard click.

Receipts are receipt-only and non-mutating. They do not cancel tasks, retry tasks, execute rollback, approve import promotion execution, apply structures, mutate worlds, copy assets, call model providers, or touch family-server state. Unsupported plan entries, stale plans, missing plan entries, mutating safe-next-action names, private decision content, provider prompts, raw asset payload fields, and family-showcase content are rejected instead of being redacted into approval.

`util/ai_native_runtime_verify.py` writes a bounded sample receipt next to the approval plan without approving execution. The manifest records `operator_action_approval_receipt_status`, path, output bytes, and item count so local and low-power lanes prove the receipt shape without adding execution controls.

## Receipt-Gated Task Control Executor

The receipt-gated task control executor is the first execution layer after receipts. `util/ai_native_operator_task_control_executor.py` accepts `ai-runtime-operator-action-approval-receipt.json` plus disposable synthetic task state and writes `ai-runtime-operator-action-execution-result.json`:

```sh
python3 util/ai_native_operator_task_control_executor.py \
  --input local/benchmarks/local-mac/2026-06-29/run/ai-runtime-operator-action-approval-receipt.json \
  --output local/benchmarks/local-mac/2026-06-29/run/ai-runtime-operator-action-execution-result.json \
  --capability task.inspect \
  --capability task.cancel \
  --capability task.retry
```

Execution is task cancel/retry only. Approved task cancel and retry receipt entries may mutate synthetic task state when prerequisites and executor capabilities match. Denied, needs-review, unsupported, stale, oversized, private, or mutating receipt entries are rejected. The executor records per-decision results, before/after task status, rejected reasons, and bounded summary counts.

The executor preserves the same public-safe boundary as the earlier artifacts: no rollback execution, no import promotion execution, no world mutation, no structure apply, no raw assets, no provider prompts, and no family-world coordinates. It is not a rollback executor, import applier, world editor, or live family-server control path.

`util/ai_native_runtime_verify.py` writes `ai-runtime-operator-action-execution-result.json` as the final operator-control artifact in the local and low-power verifier chain. The manifest records `operator_action_execution_status`, path, output bytes, and item count so side-by-side fork runs prove receipt-gated task control without touching private worlds or family-server state.

## Product Use

The first product use is an operator readout that can answer:

- Is this build product-profile clean?
- Which agents and capability profiles are active?
- Are tasks running, blocked, failed, or completed?
- Are rollback records available before an operator approves risky work?
- Are compatibility/import reviews and promotion packages approved, ready, or blocked?
- Are benchmark and verifier gates passing?
- What safe next actions should an operator review before cancelling, retrying, approving, or rolling back AI work?

Future UI work should consume this package before adding a separate schema.
