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
python3 util/ai_native_runtime_verify.py --hardware-class local-mac --game-profile ai_runtime
```

When benchmark evidence or target scoring changes, also run:

```bash
python3 util/ai_native_minecraft_parity_harness.py --output-root local/benchmarks
```

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

```bash
python3 util/ai_native_agent_eval_queue.py \
  --agents-sdk-log local/logs/agents-sdk-model-adapter.jsonl \
  --action-log local/logs/luanti-debug.log \
  --output local/benchmarks/ai-agent-eval-candidate-queue.json \
  --generated-at 2026-06-30T00:00:00Z
```

The queue is review-first. Ready candidates such as fire-only and TNT-wall
regressions can be promoted into `/ai_agent_eval`; unknown prompts require an
operator label before they become pass/fail tests. This keeps improvement tied
to observed failures while preserving the public/private boundary.

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
overnight evidence only after one-hour evidence is clean.

## Ranked Next-Issue Queue

Keep this ranked next-issue queue current after every milestone slice:

1. #253 Promoted Pi one-hour and overnight evidence for current alpha.
   Use when the Pi lane is clear. Gate: backup-first side-by-side deploy and
   clean low-power evidence.
2. #254 First-party AI agent productization lane.
   Use for parallel local work while Pi evidence is occupied. Gate: live
   product-loop probe and one-command local verifier.
3. #255 Compatibility import scale-up after staged apply pilot.
   Use after runtime and product-loop evidence remains clean. Gate: dry-run or
   approval-gated apply with rollback metadata.
4. #256 Minecraft parity benchmark expansion.
   Use after accepted local and low-power lanes are refreshed. Gate:
   public-safe parity harness with actionable scorecard.

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
