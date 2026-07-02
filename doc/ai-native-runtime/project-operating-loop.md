# Project Operating Loop

Status: contributor and maintainer cadence for the AI-native Luanti fork.

## Purpose

This loop keeps the fork moving like a real open-source project instead of a
private experiment. It ties every release-candidate change to clean-profile
verification, public-safe evidence, a ranked next-issue queue, and the
side-by-side Raspberry Pi proving lane.

The project direction remains:

- AI-native runtime first.
- Compatibility/import second and behind runtime gates.
- Family-server content stays private or optional.
- The Pi is a proving ground, not the public source tree.

## Pre-PR Local Loop

Run these before opening a PR that changes engine/runtime, first-party plugins,
release packaging, benchmarks, or compatibility/import behavior:

```bash
python3 util/ai_native_alpha_release_gate.py
python3 util/openrealm_advantage_kit_verify.py --run-tests --run-js-check
python3 util/ai_native_agents_sdk_sidecar_readiness.py --mode offline-smoke
python3 util/ai_native_runtime_verify.py --hardware-class local-mac --game-profile ai_runtime
```

When benchmark evidence or target scoring changes, also run:

```bash
python3 util/ai_native_minecraft_parity_harness.py --output-root local/benchmarks
```

When a PR changes player-facing agent behavior, the pre-PR packet must also
prove the Agents SDK sidecar contract in offline mode and live in-engine
behavior through the Agents SDK model adapter. Run sidecar readiness first, run
the live prompt eval, then make the combined quality gate require that artifact:

```bash
python3 util/ai_native_agents_sdk_sidecar_readiness.py --mode offline-smoke
```

```bash
python3 util/ai_native_agent_prompt_eval_live_probe.py \
  --root . \
  --server-bin bin/luantiserver \
  --output local/benchmarks/ai-agent-prompt-eval-live-latest.json \
  --generated-at 2026-06-30T00:00:00Z \
  --adapter-endpoint http://127.0.0.1:8766/v1/model-adapter

python3 util/ai_native_agent_quality_gate.py \
  --candidate-queue local/benchmarks/ai-agent-eval-candidate-queue.json \
  --case-pack local/benchmarks/ai-agent-prompt-eval-case-pack.json \
  --review-queue local/benchmarks/ai-agent-review-queue.json \
  --adapter-contract-eval local/benchmarks/ai-agent-adapter-contract-eval.json \
  --live-prompt-eval local/benchmarks/ai-agent-prompt-eval-live-latest.json \
  --require-live-prompt-eval \
  --request-response-log-gate local/benchmarks/ai-agent-request-response-log-gate.json \
  --compat-import-staging-pilot local/benchmarks/ai-runtime-compat-import-staging-pilot-result.json \
  --output local/benchmarks/ai-agent-quality-gate.json \
  --generated-at 2026-06-30T00:00:00Z
```

The agent quality gate is promotion-blocking when the live prompt eval is
missing, when the fire-only or TNT-wall request/response cases fail, or when
the Agents SDK response lacks the required build-planning tool evidence.

The alpha gate emits a machine-readable `project_operating_loop` section with
the expected cadence, ranked next-issue queue, and public boundary. Local
artifacts belong under `local/benchmarks` unless a maintainer explicitly
promotes reviewed public-safe evidence.

The same report also emits `release_candidate_checklist`. Treat that section as
the repeatable alpha-candidate packet: it records the candidate commit command,
clean-checkout gates, local runtime evidence, compatibility/parity review,
backup-first Pi side-by-side promotion requirements, release closeout evidence,
and the public/private content boundary.

## Agent Improvement Loop

Live agent behavior must feed the eval backlog. After a bad Nova response or a
surprising Agents SDK sidecar result, collect the public-safe sidecar JSONL and
Luanti action/debug log, then produce an eval candidate queue:

Before touching live logs, run the synthetic verifier to prove the log-to-memory
mechanics still work end to end:

```bash
python3 util/ai_native_agent_improvement_loop_verify.py \
  --root . \
  --output local/benchmarks/ai-runtime-agent-improvement-loop-result.json \
  --generated-at 2026-06-30T00:00:00Z
```

```bash
python3 util/ai_native_agent_request_response_log_gate.py \
  --agents-sdk-log local/logs/agents-sdk-model-adapter.jsonl \
  --output local/benchmarks/ai-agent-request-response-log-gate.json \
  --generated-at 2026-06-30T00:00:00Z

python3 util/ai_native_agent_eval_queue.py \
  --agents-sdk-log local/logs/agents-sdk-model-adapter.jsonl \
  --request-response-log-gate local/benchmarks/ai-agent-request-response-log-gate.json \
  --nova-agent-log local/logs/nova-agent-requests.jsonl \
  --action-log local/logs/luanti-debug.log \
  --verified-live-probe local/logs/live-probes \
  --output local/benchmarks/ai-agent-eval-candidate-queue.json \
  --generated-at 2026-06-30T00:00:00Z
```

The log gate is the immediate regression check for the player-facing failures:
`build me a fire and only a fire` must select the fire option, `build a wall of
tnt` must select the TNT wall instead of refusing game-world danger, and an
open-ended generated build must retain `propose_build_option` tool evidence. Its
passing cases can seed the eval queue through `--request-response-log-gate`, so
the latest gated behavior is not lost in raw-log noise. The queue remains
review-first. Ready candidates such as fire-only and TNT-wall
regressions can be promoted into `/ai_agent_eval`; unknown prompts require an
operator label before they become pass/fail tests. The same queue marks missing
Agents SDK required-tool calls as high-priority adapter-contract regressions with
`ready_for_adapter_contract_eval = true`, so a bad agent trace is not buried as
generic manual review. This keeps improvement tied to observed failures while
preserving the public/private boundary.

Verified Nova auto-apply live probe artifacts can be passed with
`--verified-live-probe`. Only passing disposable-world cases with satisfied
Agents SDK tool calls, a ready Luanti action plan, and successful rollback/no
extra-node checks are promoted; failed or incomplete probe cases stay out of
prompt memory.

When a maintainer knows the expected build output for an unknown prompt, create a
public-safe `ai_native_agent_eval_operator_labels` artifact and pass it with
`--operator-labels`. Labels may match by exact `candidate_id` or exact public
`prompt`, and can only promote build-output expectations that the runtime prompt
eval can replay. Use the builder so reviewed corrections come from the candidate
queue instead of hand-written JSON:

```text
/ai_agent_feedback last; case=stone_bridge_platform; build_kind=platform; material=stone; planned_writes=12; route=agentic_build_planner
```

The `/ai_agent_feedback` chat command is server-privileged and records a
public-safe reviewed event for the latest request trace without mutating the
world. The feedback packet can then consume that event directly from the Luanti
action log:

```bash
python3 util/ai_native_agent_feedback_packet.py \
  --agents-sdk-log local/logs/agents-sdk-model-adapter.jsonl \
  --action-log local/logs/luanti-debug.log \
  --from-operator-feedback \
  --candidate-queue-output local/benchmarks/ai-agent-eval-candidate-queue.json \
  --operator-label-output local/benchmarks/ai-agent-operator-labels.json \
  --case-pack-output local/benchmarks/ai-agent-prompt-eval-case-pack.json \
  --generated-at 2026-06-30T00:00:00Z
```

```bash
python3 util/ai_native_agent_feedback_packet.py \
  --agents-sdk-log local/logs/agents-sdk-model-adapter.jsonl \
  --action-log local/logs/luanti-debug.log \
  --prompt "build a bridge" \
  --case-hint stone_bridge_platform \
  --build-kind platform \
  --build-material-name stone \
  --planned-node-writes 12 \
  --route agentic_build_planner \
  --candidate-queue-output local/benchmarks/ai-agent-eval-candidate-queue.json \
  --operator-label-output local/benchmarks/ai-agent-operator-labels.json \
  --case-pack-output local/benchmarks/ai-agent-prompt-eval-case-pack.json \
  --generated-at 2026-06-30T00:00:00Z
```

When the queue already exists and only the reviewed label artifact is needed,
use the lower-level label builder:

```bash
python3 util/ai_native_agent_operator_label.py \
  --candidate-queue local/benchmarks/ai-agent-eval-candidate-queue.json \
  --prompt "build a bridge" \
  --case-hint stone_bridge_platform \
  --build-kind platform \
  --build-material-name stone \
  --planned-node-writes 12 \
  --route agentic_build_planner \
  --output local/benchmarks/ai-agent-operator-labels.json \
  --generated-at 2026-06-30T00:00:00Z
```

```bash
python3 util/ai_native_agent_eval_queue.py \
  --agents-sdk-log local/logs/agents-sdk-model-adapter.jsonl \
  --request-response-log-gate local/benchmarks/ai-agent-request-response-log-gate.json \
  --action-log local/logs/luanti-debug.log \
  --operator-labels local/benchmarks/ai-agent-operator-labels.json \
  --output local/benchmarks/ai-agent-eval-candidate-queue.json \
  --generated-at 2026-06-30T00:00:00Z
```

Promote reviewed ready candidates into a replayable
`ai_native_agent_prompt_eval_case_pack`:

```bash
python3 util/ai_native_agent_eval_promote.py \
  --candidate-queue local/benchmarks/ai-agent-eval-candidate-queue.json \
  --output local/benchmarks/ai-agent-prompt-eval-case-pack.json \
  --generated-at 2026-06-30T00:00:00Z
```

For routine sidecar operations, refresh both artifacts in one audited command:
Add `--from-operator-feedback` when the action log may contain
`/ai_agent_feedback` reviews; those reviews are converted into in-memory
operator labels before prompt-memory promotion.

```bash
python3 util/ai_native_agent_memory_refresh.py \
  --agents-sdk-log local/logs/agents-sdk-model-adapter.jsonl \
  --request-response-log-gate local/benchmarks/ai-agent-request-response-log-gate.json \
  --nova-agent-log local/logs/nova-agent-requests.jsonl \
  --action-log local/logs/luanti-debug.log \
  --verified-live-probe local/logs/live-probes \
  --from-operator-feedback \
  --operator-labels local/benchmarks/ai-agent-operator-labels.json \
  --candidate-queue-output local/benchmarks/ai-agent-eval-candidate-queue.json \
  --case-pack-output local/benchmarks/ai-agent-prompt-eval-case-pack.json \
  --generated-at 2026-06-30T00:00:00Z
```

Replay sidecar adapter-contract failures against the loopback model adapter
before treating a live agent run as healthy:

```bash
python3 util/ai_native_agent_adapter_contract_eval.py \
  --candidate-queue local/benchmarks/ai-agent-eval-candidate-queue.json \
  --output local/benchmarks/ai-agent-adapter-contract-eval.json \
  --endpoint http://127.0.0.1:8766/v1/model-adapter \
  --generated-at 2026-06-30T00:00:00Z
```

The replay runner selects only candidates marked
`ready_for_adapter_contract_eval = true`, refuses non-loopback endpoints, avoids
world mutation, and fails runs where required function tools are missing,
`required_tool_calls_satisfied` is not true, or the decision source is not one
of the accepted agent tool-contract sources: `agents_sdk_function_tool`,
`agents_sdk_repair_function_tool`, or `local_agent_tool_contract_fast_path`.

Case packs are for harnesses and disposable-world probes. They run through
`core.ai_agent_plugin.run_prompt_eval({ cases = "custom", custom_cases = ... })`
so promoted cases exercise the same preview, approval, cleanup, trace, and
metric checks as built-in `/ai_agent_eval` cases. The chat command remains
limited to built-in eval cases until a reviewed operator import surface exists.
The Pi fork sidecar mounts the refreshed case pack as read-only prompt memory
through `AI_NATIVE_AGENT_CASE_PACK_PATH`; it still cannot bypass Luanti preview,
approval, rollback, or task gates.

Prompt memory has two promotion levels. A single reviewed candidate can be
replayed by custom prompt-eval harnesses and mounted as read-only sidecar
memory, but it remains marked `requires_maintainer_review_before_default_gate`.
When the same public-safe behavior is observed from at least two trusted source
kinds, and each observation has a passing required-tool contract, the case pack
marks that case `default_gate_eligible`. This is the normal self-improvement
path for repeated verified behavior: the agent can learn from live evidence
without letting a single model answer, private artifact, or direct world mutation
change the default gate.

Ambiguous build behavior must be improved through the same loop. The Agents SDK
sidecar can reason and call read-only tools, but Luanti only changes an
executable pending build when the sidecar returns a structured
`selected_option_id` or `tool_decisions.build_option.selected_option_id` that
matches a candidate Luanti already offered. When the sidecar selects the wrong
candidate, capture the request/response logs, promote the public-safe failure
into a custom prompt-eval case if the expected build behavior is known, and fix
the agent/tool contract or candidate ranking until the eval passes. When the
problem is missing tool evidence rather than a known wrong build output, keep it
in the adapter-contract lane until the expected build behavior is reviewed.

## Pi Promotion Loop

Pi promotion is an operator lane, not a contributor default. Promote only after
the local gates pass and a backup-first side-by-side deploy preserves the
family service.

The service split is fixed:

- `luanti-family.service` stays on UDP `30000`.
- `ai-native-luanti-test.service` is the fork proving lane on UDP `30001`.

Use the low-power evidence tool after a backup-first deploy:

```bash
python3 util/ai_native_low_power_pi_evidence.py \
  --ssh-target "<operator-supplied-target>" \
  --confirm-backup-first \
  --backup-artifact-label "<backup-archive-name>" \
  --backup-sha256 "<backup-sha256>" \
  --soak-target quick
```

Promote to one-hour evidence only after quick proof is clean. Promote to
overnight evidence only after one-hour evidence is clean. Named soak targets
default to their recommended cadence; use explicit `--soak-iterations` and
`--soak-interval-seconds` only when deliberately overriding the target cadence.

## Ranked Next-Issue Queue

Keep this ranked next-issue queue current after every milestone slice:

1. #253 Promoted Pi one-hour and overnight evidence for current alpha.
   Current overnight proof is clean for `907b393b5`: 17/17 samples, elapsed
   29649.598 seconds, zero fork restarts, zero actionable warnings, and zero
   server log errors. Keep this lane for future runtime candidates; do not use
   it as the blocker for the current productization slice.
2. #254 First-party AI agent productization lane.
   Use for parallel local work while Pi evidence is occupied. Gate: live
   product-loop probe, streamed Agents SDK build-planning tool evidence,
   request/response log gate, required live prompt eval, the agent quality
   gate, and one-command local verifier.
3. #255 Compatibility import scale-up after staged apply pilot.
   Use after runtime, quick Pi evidence, and product-loop evidence remain
   clean. Gate: dry-run or approval-gated apply with rollback metadata.
4. #256 Minecraft parity benchmark expansion.
   Use after accepted local and low-power lanes are refreshed for the current
   candidate. Gate: public-safe parity harness with actionable scorecard.

The contributor release automation and project operating loop lane is complete
but still enforced. Keep the alpha gate docs, issue/PR templates,
machine-readable report, and `release_candidate_checklist` complete after each
milestone slice.

## Public Boundary

The main fork must not absorb private family worlds, player-private data,
provider prompts, credentials, copied proprietary assets, marketplace content,
or local showcase builds.

Keep these out of the public fork:

- `spacebase`
- `themepark`
- `disneyland100`

Reusable ideas from private family plugins can move into the fork only as
generic engine/runtime or first-party plugin behavior with tests, docs, public
sample data, rollback/audit evidence, and benchmark coverage.

## Release Closeout

Every merged milestone slice should leave:

- a clean `master` branch;
- a PR comment or issue comment listing verification commands;
- local evidence under `local/benchmarks`;
- no private artifacts committed;
- a clear next action from the ranked next-issue queue.
