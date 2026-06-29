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

`/ai_runtime_smoke` is a `server`-privileged command for local operators. Its module and command are disabled by default in the product profile and only load/register when `ai_runtime.enable_smoke_command = true` is set for an explicit dev/test lane. It runs the same synthetic scenario and returns a bounded JSON summary under 12k characters. The command always uses synthetic mode and does not accept player names, provider prompts, local paths, private assets, live-server targets, or model-network settings.

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

For branch work, run the focused smoke after the branch benchmark gate and `/ai_runtime_smoke`
operator command checks:

```sh
python3 util/ai_native_product_profile_verify.py
python3 util/ai_native_benchmark_gate.py --hardware-class local-mac
bin/luantiserver --run-unittests --test-module TestAIRuntime
```

For pre-PR work, prefer the one-command local harness:

```sh
python3 util/ai_native_runtime_verify.py --hardware-class local-mac
```

The harness runs the AI-native utility contracts, the branch benchmark gate, the live operator
status command probe, and the focused `TestAIRuntime` smoke in a repeatable order. It writes
`ai-runtime-verification-manifest.json` under
`local/benchmarks/<hardware-class>/<date>/<commit>/` with bounded command statuses, durations,
failure reasons, and local artifact paths. The default operator-status step launches a
disposable `ai_runtime` world with a temporary probe worldmod, executes the registered
`/ai_runtime_operator_status` command function, writes `ai-runtime-operator-status-live.json`, and
records source_kind = `live_command` with direct command execution evidence. The probe uses a
temporary local world only: no family server, no private world, no private assets, no provider
prompts, and no model-network calls.

The verifier also validates the live package's `operator_control` section: it must be read-only,
dry-run-only, contain safe next actions instead of mutating commands, and preserve public-safe
redaction boundaries.

If the live command path is unavailable in a narrow utility-only lane, use
`--operator-status-source surrogate` to write `ai-runtime-operator-status.json` with
`util/ai_native_operator_status_package.py`. The manifest records
source_kind = `command_surrogate` and `direct_command_execution = false` for that fallback. Both
paths fail the run if the retained artifact is missing required sections, exceeds
`--operator-status-max-bytes`, or contains private paths, hosts, family-showcase names, provider
keys, provider prompts, or raw asset payload fields.

Use the default synthetic-only verifier for fast feature branches that do not touch server-profile
startup, packaging, or benchmark capture behavior.

Use clean-profile verification when the branch changes runtime startup, server profile behavior,
benchmark capture, low-power evidence, or pre-compatibility performance gates:

```sh
python3 util/ai_native_runtime_verify.py \
  --hardware-class local-mac \
  --game-profile ai_runtime
```

The clean-profile verifier keeps the normal branch gate and focused AI runtime unit smoke, and also
routes `--game-profile ai_runtime` through benchmark capture. The run directory keeps
`benchmark-gate-manifest.json`, `ai-runtime-verification-manifest.json`, and
`clean-profile-benchmark-summary.json` together with `ai-runtime-operator-status-live.json`. It
still requires no family server, no private world, no private assets, no provider prompts, and no
model-network calls.

The smoke scenario itself remains synthetic: no live server, no private world, and no model
network. The verifier's live operator-status probe uses only a disposable local world and does not
touch the family proving-ground server. Any future low-power or family-server proving-ground run
remains backup-first and must be explicitly requested.
