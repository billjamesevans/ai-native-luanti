# Operator Alpha Release Runbook

Status: repeatable promote, verify, rollback, and evidence-retention path for
the side-by-side AI-native fork service.

## Purpose

This runbook turns a working dev deployment into a repeatable alpha release
lane. The lane promotes only the clean `games/ai_runtime` profile and its
first-party runtime/plugin surfaces. It does not promote private family worlds,
showcase builds, copied assets, provider prompts, credentials, or local-only
deployment details.

The Pi service split is fixed:

- `luanti-family.service` stays the family server on UDP `30000`.
- `ai-native-luanti-test.service` is the fork alpha lane on UDP `30001`.

The fork test service is a proving-ground deployment lane, not a replacement
for the family server.

## Release Candidate Contents

Classify every release-candidate change before promotion:

- Engine/runtime: agent identity, capabilities, task queues, safe world/entity
  and player operations, rollback, metrics, audit, operator status/control, and
  bounded navigation/perception.
- First-party plugins: clean `ai_agent_plugin`, build/repair/import helpers,
  and provider-neutral model-adapter boundaries.
- Optional family plugins: reusable ideas extracted into public-safe plugin
  interfaces only. Private content stays outside the main fork.
- Benchmark artifacts: local ignored reports under `local/benchmarks`, plus
  reviewed accepted lanes when promotion explicitly updates baselines.
- Compatibility/import artifacts: public-safe inventory, preview, staging
  apply, rollback, and refusal-gate evidence. No raw proprietary payloads.

Do not promote `spacebase`, `themepark`, `disneyland100`, family-world data,
private coordinates, private prompts, copied Minecraft assets, marketplace
content, server jars, or credentials.

## Preconditions

Set private deployment values in the operator shell. Do not write them into
committed files or retained public artifacts.

```sh
export AI_NATIVE_PI_SSH_TARGET="<operator-supplied-target>"
export AI_NATIVE_REMOTE_CHECKOUT="<operator-supplied-remote-checkout>"
export BACKUP_ARTIFACT_LABEL="<backup-archive-name>"
export BACKUP_SHA256="<backup-sha256>"
```

Confirm the branch and local release package:

```sh
git status --short --branch
git rev-parse --short HEAD
python3 util/ai_native_alpha_release_gate.py --root .
python3 util/ai_native_runtime_verify.py --hardware-class local-mac --game-profile ai_runtime
```

When release-candidate performance evidence changes, refresh reviewed captures
and promote only the reviewed capture directory:

```sh
python3 util/ai_native_benchmark_promote.py \
  --capture-dir "<reviewed-capture-dir>" \
  --output-root local/benchmarks \
  --source-label "<reviewed-source-label>"

python3 util/ai_native_minecraft_parity_harness.py --output-root local/benchmarks
```

The parity report must use accepted local and low-power lanes and must remain a
project target scorecard, not a proprietary Minecraft benchmark claim.

## Backup-First Deploy

Before replacing or restarting the fork test service, create and record a
server backup. The backup must happen before any deploy, service file write,
world change, or mod change.

The private operator wrapper may be used when available:

```sh
ops/deploy-ai-native-luanti-fork-to-pi.sh
```

That wrapper must keep this order:

1. Verify SSH access to the operator-supplied Pi target.
2. Back up the live server state and record `BACKUP_ARTIFACT_LABEL` plus
   `BACKUP_SHA256`.
3. Confirm `luanti-family.service` is active and UDP `30000` is listening.
4. Update/build the fork checkout separately from the family server.
5. Run `bin/luantiserver --run-unittests --test-module TestAIRuntime` on the
   fork checkout.
6. Write or update only `ai-native-luanti-test.service`.
7. Start or restart only `ai-native-luanti-test.service` on UDP `30001`.
8. Leave `luanti-family.service` active on UDP `30000`.

If a deploy step fails after backup, stop and retain the backup label, backup
SHA, failing commit, failing command, and service status. Do not continue into
evidence promotion.

## Independent Post-Deploy Checks

Do not rely only on deploy-script output. Verify the service split directly:

```sh
ssh -o BatchMode=yes "$AI_NATIVE_PI_SSH_TARGET" '
  systemctl is-active luanti-family.service
  systemctl is-active ai-native-luanti-test.service 2>/dev/null || true
  sudo ss -lunp | grep -E ":(30000|30001)" || true
'
```

Verify the fork binary and deployed commit without retaining private paths in
public artifacts:

```sh
ssh -o BatchMode=yes "$AI_NATIVE_PI_SSH_TARGET" "
  cd \"$AI_NATIVE_REMOTE_CHECKOUT\" &&
  bin/luantiserver --version | head -n 8 &&
  git rev-parse --short HEAD &&
  sudo journalctl -u ai-native-luanti-test.service -n 40 --no-pager
"
```

Expected smoke result:

- `luanti-family.service` is active.
- UDP `30000` is listening.
- `ai-native-luanti-test.service` is active.
- UDP `30001` is listening.
- The fork commit matches the release candidate.
- The fork service journal has no actionable warnings or server errors.

When the release candidate includes the Agents SDK model adapter bridge, prove
the sidecar wiring before any long soak:

```sh
python3 util/ai_native_agents_sdk_sidecar_readiness.py \
  --mode managed-http \
  --port 8766 \
  --output local/benchmarks/agents-sdk-sidecar-readiness.json
```

This readiness probe intentionally removes `OPENAI_API_KEY` from the managed
child process. A passing result proves loopback service wiring, `/health`,
`POST /v1/model-adapter`, provider-neutral envelopes, and no retained provider
credentials. Live provider execution is a separate operator action after
server-local secrets are configured.

When a release candidate changes player-facing agent behavior, prove the live
path with an in-engine prompt eval before promotion. This gate must use the
real loopback model adapter and then require that live artifact in the combined
quality gate:

```sh
python3 util/ai_native_agent_prompt_eval_live_probe.py \
  --root . \
  --server-bin bin/luantiserver \
  --output local/benchmarks/ai-agent-prompt-eval-live-latest.json \
  --generated-at "<utc-timestamp>" \
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
  --generated-at "<utc-timestamp>"
```

The promotion packet must show `live_prompt_eval_required = true`, a passing
live prompt eval, a passing request/response log gate for the known fire/TNT
regressions, and no missing required Agents SDK build-planning tool calls.

## Evidence Retention

Attach these evidence classes to a release candidate:

- Alpha package gate:
  `python3 util/ai_native_alpha_release_gate.py --root .`
- Local clean-profile verifier:
  `python3 util/ai_native_runtime_verify.py --hardware-class local-mac --game-profile ai_runtime`
- Agents SDK sidecar readiness:
  `python3 util/ai_native_agents_sdk_sidecar_readiness.py --mode managed-http --port 8766`
- Live in-engine prompt eval:
  `python3 util/ai_native_agent_prompt_eval_live_probe.py --root . --server-bin bin/luantiserver --output local/benchmarks/ai-agent-prompt-eval-live-latest.json --generated-at "<utc-timestamp>" --adapter-endpoint http://127.0.0.1:8766/v1/model-adapter`
- Required-live agent quality gate:
  `python3 util/ai_native_agent_quality_gate.py --candidate-queue local/benchmarks/ai-agent-eval-candidate-queue.json --case-pack local/benchmarks/ai-agent-prompt-eval-case-pack.json --review-queue local/benchmarks/ai-agent-review-queue.json --adapter-contract-eval local/benchmarks/ai-agent-adapter-contract-eval.json --live-prompt-eval local/benchmarks/ai-agent-prompt-eval-live-latest.json --require-live-prompt-eval --request-response-log-gate local/benchmarks/ai-agent-request-response-log-gate.json --compat-import-staging-pilot local/benchmarks/ai-runtime-compat-import-staging-pilot-result.json --output local/benchmarks/ai-agent-quality-gate.json --generated-at "<utc-timestamp>"`
- Low-power evidence:
  `python3 util/ai_native_low_power_pi_evidence.py --ssh-target "$AI_NATIVE_PI_SSH_TARGET" --confirm-backup-first --backup-artifact-label "$BACKUP_ARTIFACT_LABEL" --backup-sha256 "$BACKUP_SHA256" --soak-target quick`
- Promoted low-power evidence after quick proof:
  add `--soak-target one-hour`
- Overnight evidence after the one-hour target is clean:
  add `--soak-target overnight`
- Named soak targets default to their recommended cadence:
  `--soak-iterations 13 --soak-interval-seconds 300` for one-hour, and
  `--soak-iterations 17 --soak-interval-seconds 1800` for overnight.
- Minecraft-parity scorecard:
  `python3 util/ai_native_minecraft_parity_harness.py --output-root local/benchmarks`
- Privacy/public-safety scan status from the verifier and evidence manifests.

Retained public artifacts may include commit ids, public-safe logical artifact
paths, service roles, port numbers, pass/fail status, aggregate benchmark
counts, and sanitized follow-up issue seeds. They must not include private SSH
targets, private hostnames, private IPs, private remote checkout paths, raw
service paths, private family-world content, private prompts, provider keys,
credentials, copied assets, or raw proprietary payloads.

## Rollback

Default rollback stops only the fork alpha lane:

```sh
ssh -o BatchMode=yes "$AI_NATIVE_PI_SSH_TARGET" \
  'sudo systemctl disable --now ai-native-luanti-test.service'
```

Do not stop or replace `luanti-family.service` as part of fork rollback unless
an operator explicitly chooses a separate family-server recovery action.

Before restoring any backup, inspect the service status, deployed commit,
journal tail, failed command, backup label, and backup SHA. A backup restore is
a separate recovery decision, not the default fork rollback path.

## Release Decision

Promote an alpha candidate only when:

- The branch has no unrelated worktree changes.
- The alpha gate passes.
- The local clean-profile verifier passes.
- Player-facing agent changes have a passing live in-engine prompt eval and a
  passing agent quality gate with `--require-live-prompt-eval`.
- The Pi evidence lane proves the side-by-side split after a backup-first
  deploy.
- The parity harness has no new fail/warn actions for accepted evidence lanes,
  or any remaining actions have explicit follow-up issues.
- Release notes separate engine/runtime changes, first-party plugins, optional
  family plugins, benchmark evidence, and compatibility/import state.
- The public-safe boundary review finds no private family content, showcase
  builds, credentials, provider prompts, copied assets, or proprietary payloads.
