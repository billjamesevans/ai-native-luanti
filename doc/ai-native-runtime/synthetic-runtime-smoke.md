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

The harness runs the AI-native utility contracts, the product-profile hygiene gate, the branch
benchmark gate, the live operator status command probe, the Nova prompt eval probe, the
compatibility import staging pilot, the receipt-gated task-control command probe, and the focused
`TestAIRuntime` smoke in a repeatable order. It writes
`ai-runtime-verification-manifest.json` under
`local/benchmarks/<hardware-class>/<date>/<commit>/` with bounded command statuses, durations,
failure reasons, and local artifact paths. The product-profile step writes
`ai-runtime-product-profile-hygiene.json` with the standalone
`util/ai_native_product_profile_verify.py` report and fails the run if the clean `ai_runtime`
profile loads fixture mods by default, enables dev surfaces without explicit settings, loses its
`ai_runtime_base` product-mod boundary, or contains private/showcase content. The default
operator-status step launches a
disposable `ai_runtime` world with a temporary probe worldmod, executes the registered
`/ai_runtime_operator_status` command function, writes `ai-runtime-operator-status-live.json`, and
records source_kind = `live_command` with direct command execution evidence. The same disposable
probe seeds synthetic operator state after capturing the default package, calls focused read-only
`view=tasks`, `view=task`, `view=audit`, `view=rollback`, and `view=imports` command modes, checks
invalid-view refusals, and records compact `operator_ux_command_probe` evidence without changing
the default package status. It also derives
`ai-runtime-operator-control-report.json` with `util/ai_native_operator_control_report.py` so the
run keeps both the raw package and the operator-facing report adapter. It then derives
`ai-runtime-operator-action-approval-plan.json` with
`util/ai_native_operator_action_approval_plan.py` so approval-plan artifacts are available before
any future execution controls exist. It also derives
`ai-runtime-operator-action-approval-receipt.json` with
`util/ai_native_operator_action_approval_receipt.py` as a bounded receipt artifact that marks plan
entries as needs-review by default. Finally, it runs the receipt-gated task control executor in
`util/ai_native_operator_task_control_executor.py` and writes
`ai-runtime-operator-action-execution-result.json` so the verifier proves the task cancel/retry only
execution contract against synthetic task state. It then runs
`util/ai_native_agent_product_loop_live_probe.py` against a disposable live `ai_runtime` world and
writes `ai-runtime-agent-product-loop-live-result.json`. That probe uses synthetic public nodes to
queue build and repair previews, require explicit approval, execute rollback-backed build and repair
tasks, review and edit pending plans before approval, cancel a queued task, retry a
rollback-blocked task, and check guide/tasks/audit/rollback, targeted audit, targeted rollback
review, normal follow movement through the clean `ai_runtime_base:helper` entity, defender, and
importer-preview surfaces without private content. It also captures a compact
same-world operator-status snapshot proving the live status surface sees the product-loop tasks,
rollback records, and import review without retaining private payloads. Rollback review remains
read-only in this probe, including targeted rollback-record lookup. It then runs
`util/ai_native_agent_prompt_eval_live_probe.py` against a disposable live `ai_runtime` world and
writes `ai-runtime-agent-prompt-eval-live-result.json`. That probe executes the registered
`/ai_agent_eval` command for the fire case, runs `core.ai_agent_plugin.run_prompt_eval` for
`build a fire`, strict `build me a fire and only a fire`, `build a wall of tnt`, ambiguous `build a
small shelter` agentic planning, and the async model-adapter case, checks request/response trace
routes, verifies the TNT wall is not refused as dangerous, enforces exact preview sizes for one-node
fire prompts, twelve TNT wall nodes, and the four-node agentic shelter platform, discards pending
build approvals before mutation, and records model-adapter request/success/failure/timeout deltas.
By default it
uses a deterministic mock async adapter and requires no model-network calls; pass
`--agent-prompt-eval-adapter-endpoint http://127.0.0.1:8766/v1/model-adapter` to run the same
regression gate through the loopback Agents SDK adapter. It then runs
`util/ai_native_compat_import_staging_pilot.py` against a disposable live `ai_runtime` staging world
and writes `ai-runtime-compat-import-staging-pilot-result.json`. That pilot runs public-safe
inventory discovery, dry-run report generation, reviewed adapter smoke, operator review, chunked
staging apply, rollback planning, rollback execution, and refusal gates for missing approval,
missing rollback policy, unsafe private payloads, non-staging targets, and over-budget writes. It
records node-write, apply-chunk, rollback-record, and mapblock-churn evidence without copying raw
assets or mutating the family server. It then runs
`util/ai_native_operator_task_control_live_probe.py` as a receipt-gated live task-control probe
against a disposable live `ai_runtime` queue probe and writes
`ai-runtime-operator-task-control-live-result.json`. The probe uses a temporary local world only: no
family server, no private world, no private assets, no provider prompts, and no model-network calls.
The verifier then runs `util/ai_native_operator_task_control_command_probe.py` as a receipt-gated
task-control command probe against the registered `/ai_runtime_operator_task_control` command and
writes `ai-runtime-operator-taREDACTED_KEY_FIXTURE.json`. That command probe uses the same
temporary local-world boundary and exists to prove the operator command adapter separately from the
disposable live queue probe.

The verifier also validates the live package's `operator_control` section and the derived
operator-control report adapter: both must be read-only, dry-run-only, contain safe next actions
instead of mutating commands, and preserve public-safe redaction boundaries. The derived approval
plan must remain non-mutating, approval-required, and bounded by
`--operator-action-approval-plan-max-bytes`. The derived receipt artifacts must stay receipt-only,
non-mutating, and bounded by `--operator-action-approval-receipt-max-bytes`. The derived execution
result must stay receipt-gated, synthetic-task-state-only, task cancel/retry only, and bounded by
`--operator-action-execution-result-max-bytes`. The first-party product-loop live result must stay
disposable-world-only, public-safe, rollback-backed for build and repair, explicit-approval-gated for
build and repair mutation, operator-status-visible, no rollback execution, no import promotion execution, and bounded by
`--agent-product-loop-live-result-max-bytes`. The Nova prompt eval live result must stay
read-only, public-safe, pending-approval cleanup only, no world mutation, five-case complete, and
bounded by `--agent-prompt-eval-live-result-max-bytes` and
`--agent-prompt-eval-live-timeout`; optional real adapter checks use
`--agent-prompt-eval-adapter-endpoint` and `--agent-prompt-eval-adapter-timeout`. The compatibility import staging pilot result must
stay public-safe, disposable-staging-only, approval-gated, rollback-backed, family-world-free,
asset-copy-free, and bounded by `--compat-import-staging-pilot-result-max-bytes` and
`--compat-import-staging-pilot-timeout`. The live task-control result must stay receipt-gated,
disposable-live-queue-only, task cancel/retry only, no rollback execution, no import promotion execution,
no world mutation, and bounded by `--operator-taREDACTED_KEY_FIXTURE`.
The task-control command result must stay receipt-gated, command-surface-only, task cancel/retry only,
no rollback execution, no import promotion execution, no world mutation, and bounded by
`--operator-taREDACTED_KEY_FIXTURE`.

If the live command path is unavailable in a narrow utility-only lane, use
`--operator-status-source surrogate` to write `ai-runtime-operator-status.json` with
`util/ai_native_operator_status_package.py`. The manifest records
source_kind = `command_surrogate` and `direct_command_execution = false` for that fallback. Both
paths fail the run if the retained artifact is missing required sections, exceeds
`--operator-status-max-bytes`, or contains private paths, hosts, family-showcase names, provider
keys, provider prompts, or raw asset payload fields.

The default verifier uses the clean `ai_runtime` profile so every normal pre-PR run includes
workload evidence. Use the synthetic-only verifier only for narrow utility branches that cannot
launch a disposable server profile:

```sh
python3 util/ai_native_runtime_verify.py \
  --hardware-class local-mac \
  --game-profile sample-synthetic
```

The default clean-profile verification command is:

```sh
python3 util/ai_native_runtime_verify.py \
  --hardware-class local-mac
```

The clean-profile verifier keeps the normal product-profile gate, branch gate, and focused AI
runtime unit smoke, and routes the default `ai_runtime` profile through benchmark capture. The run
directory keeps `benchmark-gate-manifest.json`, `ai-runtime-verification-manifest.json`,
`ai-runtime-product-profile-hygiene.json`, and
`clean-profile-benchmark-summary.json` together with `ai-runtime-operator-status-live.json` and
`ai-runtime-operator-control-report.json` and
`ai-runtime-operator-action-approval-plan.json` and
`ai-runtime-operator-action-approval-receipt.json` and
`ai-runtime-operator-action-execution-result.json` and
`ai-runtime-agent-product-loop-live-result.json` and
`ai-runtime-agent-prompt-eval-live-result.json` and
`ai-runtime-compat-import-staging-pilot-result.json` and
`ai-runtime-operator-task-control-live-result.json` and
`ai-runtime-operator-taREDACTED_KEY_FIXTURE.json`. It still requires no family server, no private
world, no private assets, no provider prompts, and no model-network calls.

The verifier validates `clean-profile-benchmark-summary.json` before the overall manifest can pass.
The derived `clean_profile_evidence` section requires `overall_status = pass`,
`game_profile.gameid = ai_runtime`, no `failure_notes`, no private/live context flags, passing
`server_step_workload`, passing `player_load_tick_probe`, passing `map_chunk_workload`, and measured
CPU samples with `cpu_sample_count >= 2`. It also records `actionable_warning_count` and
`unsafe_operation_count`; both must be zero, so unclassified clean-profile warnings or unsafe
operation leakage fail the verifier even if the benchmark command exits successfully. By default the
player-load evidence may be either a bounded `server_process_liveness` fallback or a measured
`headless_client_load` probe. Promotion and release-candidate lanes should use the strict
headless-player gate:

```sh
python3 util/ai_native_runtime_verify.py \
  --hardware-class local-mac \
  --game-profile ai_runtime \
  --headless-player-command "bin/luanti --config $tmpconf --go --address {host} --port {port} --name {name}" \
  --headless-player-count 2 \
  --require-headless-player-probe
```

The smoke scenario itself remains synthetic: no live server, no private world, and no model
network. The verifier's live operator-status probe uses only a disposable local world and does not
touch the family proving-ground server. Any future low-power or family-server proving-ground run
remains backup-first and must be explicitly requested.
