# Mutation Benchmark Scenarios

Status: runnable report contract for issue #45

## Purpose

AI-native mutation work needs a repeatable benchmark shape before more repair and build workloads are added. This slice defines public synthetic scenarios, a JSON report schema, and a small repo-local generator that can produce either a planned report or a deterministic sample report.

The report contract covers average step, p95 step, max lag, total node writes (`node_writes`), node writes per step, mapblock churn (`mapblock_churn`), skipped positions, rollback record count, AI runtime counters, warnings, and errors.

## Entry Point

Generate a planned report:

```sh
python3 util/ai_native_mutation_benchmarks.py \
  --output /tmp/ai-runtime-mutation-benchmark.json \
  --hardware-class local-mac \
  --luanti-commit "$(git rev-parse --short HEAD)"
```

Generate a deterministic synthetic sample:

```sh
python3 util/ai_native_mutation_benchmarks.py \
  --output /tmp/ai-runtime-mutation-benchmark.sample.json \
  --hardware-class local-mac \
  --luanti-commit example-commit \
  --sample-synthetic
```

Use `hardware-class local-mac` for local workstation runs. Use `hardware-class low-power-server` only after the same scenarios are safe on local hardware and the server is backed up.

## Scenario Set

### small_build_rollback

Entry point: `core.build_agent.define_task -> core.queue_ai_task`

Runs a small synthetic build task through the rollback-backed safe-world-operation path. It must report total node writes, node writes per step, skipped positions, rollback records, average step, p95 step, and max lag.

### repair_scan_readonly

Entry point: `core.repair_agent.plan_area`

Inspects bounded synthetic terrain damage without changing nodes. It must report scan cost separately from mutation cost, with `node_writes`, `node_writes_per_step`, and `rollback_records` at zero.

### repair_mutation_rollback

Entry point: `core.repair_agent.queue_apply_task`

Applies a bounded synthetic repair plan only after rollback metadata has been persisted. It must report total node writes, skipped positions, rollback records, average step, p95 step, max lag, warnings, and errors.

### rollback_record_write

Entry point: `core.write_ai_rollback_record`

Measures rollback record creation overhead without applying a world mutation. It isolates metadata capture and persistence overhead from node writes and reports `node_writes` as zero.

### first_party_agent_product_loop_approval

Entry point: `core.ai_agent_plugin.handle_command -> approve`

Exercises the first-party agent product loop for build and repair requests. The scenario records two approval plans, two approved tasks, guide/tasks/cancel command coverage, audit review, rollback review, defender checks, and importer preview coverage while keeping all fixtures synthetic. It must report total node writes, rollback records, `blocked_or_unsafe_outcomes`, average step, p95 step, max lag, warnings, and errors.

### compat_structure_chunked_apply

Entry point: `core.ai_import_ops.queue_chunked_structure_apply_task`

Applies a reviewed synthetic structure fixture through chunked compatibility import tasks. It must report actual node writes, per-step node writes, mapblock churn, rollback record count, average step, p95 step, max lag, warnings, and errors. The fixture is synthetic and runs in a disposable staging world reference; it must not copy Minecraft assets or family showcase content into the fork.

### compat_structure_rollback_execute

Entry point: `core.ai_import_ops.queue_chunked_structure_rollback_task`

Executes reviewed rollback chunks for a synthetic staged structure import. It must report rollback execution node writes, per-step node writes, mapblock churn, rollback-of-rollback record count, average step, p95 step, max lag, warnings, and errors. The fixture remains synthetic and disposable; rollback execution requires explicit approval, staging, `rollback.execute`, `admin.override`, and bounded write/churn budgets before mutation.

## Report Files

Schema:

- [`schemas/ai-runtime-mutation-benchmark-report.schema.json`](schemas/ai-runtime-mutation-benchmark-report.schema.json)

Synthetic example:

- [`examples/mutation-benchmark-report.example.json`](examples/mutation-benchmark-report.example.json)

The generator intentionally does not require private worlds, private assets, or live server state. Real measurements should write the same fields with `run_context.mode` set to `measured`.

## Regression Gates

A mutation branch must not merge when any scenario records runtime errors.

A mutation branch must not merge when it introduces new safety warnings unless the warning is reviewed and accepted.

A mutation branch must not merge when `max_lag_ms` is more than 10 percent above the accepted baseline for the same `hardware_class` without an explicit benchmark exception.

A mutation branch must not merge when `node_writes_per_step` exceeds the scenario write budget.

A mutation branch must not merge when structure or map/chunk mutation scenarios do not report `mapblock_churn`.

A mutation branch must not merge when mutating scenarios do not record total node writes.

A mutation branch must not merge when a mutating scenario changes nodes without matching rollback records.
