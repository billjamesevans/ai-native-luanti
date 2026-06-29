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
