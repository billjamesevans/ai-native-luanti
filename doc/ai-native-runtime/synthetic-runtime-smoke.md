# Synthetic Runtime Smoke

Status: synthetic task-loop smoke scenario for issue #66

## Purpose

`core.ai_runtime_smoke.run_scenario` exercises the AI-native runtime task loop without a live server, private world, copied assets, provider prompts, or model network call. It is a local confidence check after `util/ai_native_benchmark_gate.py`: the benchmark gate catches performance regressions, and this smoke scenario proves the build/repair task path can still run end to end.

## Scenario

The scenario creates an in-memory synthetic world and queues:

- one bounded build-agent task through `core.build_agent.define_task` and `core.queue_ai_task`
- one repair-agent apply task through `core.repair_agent.queue_apply_task`

Both tasks use rollback metadata before mutation. The default successful path persists one rollback record for the build mutation and one rollback record for the repair mutation. The blocked path can intentionally omit repair rollback persistence so the summary records `rollback_metadata_unavailable` instead of silently passing.

## Summary Contract

The returned summary has:

- `run_context.mode = "synthetic-task-loop-smoke"`
- `task_statuses` for the build and repair tasks
- `results` with each task's operation, status, reason, changed count, skipped count, and rollback reference
- `rollback_records` and `rollback_record_summaries`
- `audit_event_count` and sanitized `audit_events`
- `blocked_or_unsafe_outcomes` when any task blocks, fails, or reports unsafe behavior
- `world_after` with the synthetic build and repair node names after the run

The summary must not include absolute local paths, private server hosts, private prompts, player-private data, copied media, or asset payload bytes.

## Operator Command

`/ai_runtime_smoke` is a `server`-privileged command for local operators. It runs the same synthetic scenario and returns a bounded JSON summary under 12k characters. The command always uses synthetic mode and does not accept player names, provider prompts, local paths, private assets, live-server targets, or model-network settings.

Default successful run:

```text
/ai_runtime_smoke
```

Intentional blocked rollback run:

```text
/ai_runtime_smoke mode=blocked
```

Optional coordinates keep repeated local checks separate without touching a real world:

```text
/ai_runtime_smoke mode=success origin=100
```

The command summary includes pass/fail status, build and repair `task_statuses`, compact `results`, `rollback_record_summaries`, `audit_event_count`, and `blocked_or_unsafe_outcomes`. It omits full audit payloads and task internals so the operator-facing output remains bounded and public-safe.

## Running It

The default project check is the AI runtime unit module:

```sh
bin/luantiserver --run-unittests --test-module TestAIRuntime
```

For branch work, run this after the benchmark gate:

```sh
python3 util/ai_native_benchmark_gate.py --hardware-class local-mac
bin/luantiserver --run-unittests --test-module TestAIRuntime
```

The smoke path requires no live server and does not touch the family proving-ground server. Any future low-power or family-server proving-ground run remains backup-first and must be explicitly requested.
