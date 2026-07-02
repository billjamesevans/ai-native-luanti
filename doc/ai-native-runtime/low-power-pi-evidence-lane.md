# Low-Power Pi Evidence Lane

Status: alpha-hardening lane for the side-by-side `ai_runtime` test service.

Latest post-deploy gate:

- Date: 2026-07-01
- Fork commit: `907b393b5`
- Backup artifact label: `raspberrypi_luanti_20260701-182811.tgz`
- Backup SHA-256:
  `9a0f27c2a7652dc668a7582775c61082614f7d36993b742dbaa3294359f7a39d`
- Pi runtime test: `TestAIRuntime` passed.
- Service boundary: family active on UDP `30000`; fork active on UDP `30001`.
- Agents SDK sidecar: `ai-native-luanti-agents-sdk-adapter.service` active on
  loopback TCP `8766`.
- Quality gate: `pass`; live prompt eval `pass`; compatibility import staging
  pilot `pass`; agentic tool cases `10/10`; attention items `0`; violations
  `0`; retained artifact generated at `2026-07-01T23:34:03Z`.
- Request/response log gate: `pass`; `1978` request log entries and `74` Nova
  agent log entries read; `7/7` checked cases passed; violations `0`.
- Live prompt eval: `12/12` cases passed; the OpenRealm golden subset passed
  `9/9`; model adapter requests `11`, successes `11`, failures `0`, timeouts
  `0`; retained artifact generated at `2026-07-01T23:32:41Z`.
- Stone bridge generation proof: the live Pi sidecar call for
  "Build a stone bridge" returned `generated_bridge_platform` through
  `agents_sdk_generated_tool_completion`, produced a `stone` `platform`
  preview with dimensions `6 x 2` and `12` planned node writes, and included
  `inspect_build_site_context`, `recall_build_prompt_memory`,
  `propose_build_option`, `select_build_option`, and `plan_build_actions` in
  the Agents SDK tool trace.
- Small cabin generation proof: the live Pi sidecar call for
  "Build a small cabin" returned `generated_prompt_shaped_cabin` through
  `agents_sdk_generated_tool_completion`, produced a `wood` `cabin` preview
  with dimensions `3 x 2 x 2` and `10` planned node writes, and included
  `recall_build_prompt_memory`, `propose_build_option`, `select_build_option`,
  and `plan_build_actions` in the Agents SDK tool trace.
- Explicit path intent proof: the live Pi sidecar call for
  "Build a path to that hill" allowed the model to propose
  `generated_path_platform`, then the runtime intent constraint selected
  `parsed_request`, preserved `path` build intent, and produced an `8` node
  write path preview. The runtime, not the generated proposal, retained final
  mutation authority.
- Player-loop check: `Nova, options` returns pending build choices and the
  selected candidate from runtime state without world mutation. Each executable
  option carries an `openrealm.plan.v1` safety/preview contract.
- Natural-chat review trace proof:
  `player_agent_loop_review_traces_checked = true`, with public-safe
  `natural_chat_review` traces retained for `Nova, options`,
  `Nova, pending plan`, `Nova, no`, and the after-discard
  `no_pending_approval` review turn. The top-level quality gate also exposes
  `live_prompt_eval_player_agent_loop_review_traces_checked = true`.
- Natural pending-edit proof: the live Pi gate requires
  `natural_pending_edit_checked = true` and the top-level quality gate exposes
  `live_prompt_eval_natural_pending_edit_checked = true`; `Nova, make it wider`
  and `Nova, use tnt instead` revise the same pending build preview through
  `edit_plan` without world mutation.
- OpenRealm structure apply path: generated Agents SDK build options with an
  `openrealm.plan.v1` placement plan now become non-mutating previews first and
  rollback-backed `openrealm.structure.apply` tasks only after approval.
- OpenRealm template generation proof: a live Pi sidecar call for "Build a cozy
  lakeside village with floating lanterns" returned
  `generated_openrealm_lakeside_village` through
  `agents_sdk_generated_tool_completion`, produced an `openrealm_structure` /
  `openrealm_template` preview with `96` planned node writes, and included
  `inspect_build_site_context`, `recall_build_prompt_memory`,
  `propose_build_option`, `select_build_option`, and `plan_build_actions` in
  the Agents SDK tool trace.

Latest retained one-hour soak manifest:

- Date: 2026-07-01
- Fork commit: `907b393b5`
- Path:
  `local/benchmarks/low-power-server/2026-07-01/907b393b5/pi-low-power-evidence.json`
- Target: `one-hour`; elapsed `4254.735` seconds; duration met.
- Iterations: `13/13` passed, `0` failed.
- Service boundary: family active on UDP `30000`; fork active on UDP `30001`.
- Runtime verification: product profile `pass`, clean profile `pass`, headless
  client load `pass` with 2 attempted/connected/completed synthetic players,
  scale gate `pass`, server-step workload `pass` with 29 completed samples, and
  compatibility import staging pilot `pass`.
- Resource maxima: average CPU `84.261%`, interval CPU `113.667%`, RSS
  `77.781 MB`, actionable warnings `0`, server log errors `0`, failure count
  `0`.
- Backup artifact:
  `raspberrypi_luanti_20260701-182811.tgz`
  (`9a0f27c2a7652dc668a7582775c61082614f7d36993b742dbaa3294359f7a39d`).

The post-deploy gate above is not itself a soak manifest; the retained
one-hour manifest is recorded separately. Use the commands below for quick,
one-hour, or overnight low-power evidence manifests.

After the local verifier passes and the fork has been deployed through the
backup-first Pi workflow, collect low-power evidence with:

```bash
python3 util/ai_native_low_power_pi_evidence.py \
  --ssh-target "<operator-supplied-target>" \
  --confirm-backup-first \
  --backup-artifact-label "<backup-archive-name>" \
  --backup-sha256 "<backup-sha256>" \
  --soak-target quick
```

The command creates a temporary null-video client config on the remote checkout,
runs the remote low-power verifier with a `bin/luanti` headless-client command
and `--require-headless-player-probe`, reads its machine-readable manifest,
verifies the side-by-side service boundary, and writes:

```text
local/benchmarks/low-power-server/<date>/<commit>/pi-low-power-evidence.json
```

The generated manifest is local evidence and stays ignored by Git. It records
the hardware class, clean profile, fork commit, product-profile status,
clean-profile workload status, `headless_client_load` player-load probe status,
at least two attempted/connected synthetic players, join-log latency proxy evidence,
`ai_runtime_scale_gate` status,
compatibility import staging-pilot status, ranked follow-up issue seeds, soak
target duration evidence, and the expected port split: family server on UDP
`30000`, fork test service on UDP `30001`.

## Soak Targets

Use named targets so a retained manifest can prove whether a quick check, the
first promoted one-hour gate, or the overnight path was actually met.

Quick side-by-side check:

```bash
python3 util/ai_native_low_power_pi_evidence.py \
  --ssh-target "<operator-supplied-target>" \
  --confirm-backup-first \
  --backup-artifact-label "<backup-archive-name>" \
  --backup-sha256 "<backup-sha256>" \
  --soak-target quick
```

First promoted gate:

```bash
python3 util/ai_native_low_power_pi_evidence.py \
  --ssh-target "<operator-supplied-target>" \
  --confirm-backup-first \
  --backup-artifact-label "<backup-archive-name>" \
  --backup-sha256 "<backup-sha256>" \
  --soak-target one-hour \
  --soak-iterations 13 \
  --soak-interval-seconds 300
```

Overnight path:

```bash
python3 util/ai_native_low_power_pi_evidence.py \
  --ssh-target "<operator-supplied-target>" \
  --confirm-backup-first \
  --backup-artifact-label "<backup-archive-name>" \
  --backup-sha256 "<backup-sha256>" \
  --soak-target overnight \
  --soak-iterations 17 \
  --soak-interval-seconds 1800
```

The manifest fails with `soak_target_duration_not_met` if the declared target
does not run long enough. The quick target is for post-deploy proof only; v0.3
promotion requires the one-hour target before the overnight lane is meaningful.

## Safety Boundary

The evidence manifest must not retain the SSH target, remote checkout path,
private hostnames, private IPs, provider prompts, copied assets, family-world
content, or showcase names. It records only public-safe service roles, ports,
status booleans, logical artifact paths, and sanitized verifier summaries.

This command does not deploy, restart, or mutate services. It starts only a
disposable verifier server and disposable synthetic client processes on the Pi
checkout. Deployments remain owned by the backup-first Pi deploy workflow. The
evidence lane only proves the current deployed fork state.
