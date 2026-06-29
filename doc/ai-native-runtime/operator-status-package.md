# Operator Status Package

Status: operator-control contract for issue #162.

`util/ai_native_operator_status_package.py` emits bounded JSON for a future CLI/dashboard. It is a read-only summary surface: it does not mutate a world, does not execute rollback, does not apply imports, and does not load family-server content.

The package gives an operator one safe shape for:

- agent and capability inventory;
- task queue status;
- rollback record availability;
- compatibility/import review and promotion package summaries;
- benchmark or verifier gate summaries;
- product-profile hygiene from `util/ai_native_product_profile_verify.py`.

## Command

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

## Product Use

The first product use is an operator readout that can answer:

- Is this build product-profile clean?
- Which agents and capability profiles are active?
- Are tasks running, blocked, failed, or completed?
- Are rollback records available before an operator approves risky work?
- Are compatibility/import reviews and promotion packages approved, ready, or blocked?
- Are benchmark and verifier gates passing?

Future UI work should consume this package before adding a separate schema.
