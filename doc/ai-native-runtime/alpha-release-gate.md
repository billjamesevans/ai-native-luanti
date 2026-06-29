# Alpha Release Gate

Status: required public-alpha gate for the AI-native Luanti fork.

## Purpose

The dev build can contain tests, synthetic fixtures, and benchmark probes. The
alpha release must be different: a new contributor should be able to clone the
fork, build the server, run `games/ai_runtime`, and run the one-command local
verifier without private data or family-server content.

The one-command local verifier is:

```bash
python3 util/ai_native_runtime_verify.py --hardware-class local-mac --game-profile ai_runtime
```

The release-package gate is:

```bash
python3 util/ai_native_alpha_release_gate.py
```

## Required Gates

1. Build the server from a clean checkout.
2. Run the clean `games/ai_runtime` profile from a disposable world.
3. Run the one-command local verifier.
4. Run the product-profile hygiene gate.
5. Run the Minecraft-parity harness against accepted local and low-power
   baselines when benchmark evidence changes.
6. Keep compatibility import work in dry-run or preview mode unless a separate
   apply-phase review explicitly enables mutation.
7. Publish release notes using the template that separates engine/runtime
   changes, optional plugin changes, and family-server content.

## Public Boundary

The main fork must not include private worlds, private prompts, secrets,
provider configuration, copied marketplace content, or proprietary assets.
The following family/server content stays out of the public fork and belongs in
private deployment or optional local plugin lanes only:

- `spacebase`
- `themepark`
- `disneyland100`
- family worlds, player data, coordinates, screenshots, and private prompts

## Pi Lane

The Raspberry Pi remains a proving ground. The fork may be deployed to the
side-by-side `ai-native-luanti-test.service` on UDP `30001` as a deployment
lane, not a replacement for the family server on UDP `30000`.

In short: the Pi test service is a deployment lane, not a replacement for the family server.

Any Pi deploy must be backup-first and must preserve the existing family
service unless an operator explicitly chooses otherwise outside the public
alpha gate.

After a backup-first deploy, collect low-power evidence with:

```bash
python3 util/ai_native_low_power_pi_evidence.py \
  --ssh-target "<operator-supplied-target>" \
  --confirm-backup-first \
  --backup-artifact-label "<backup-archive-name>" \
  --backup-sha256 "<backup-sha256>" \
  --soak-target quick
```

The generated manifest must stay public-safe: it records the low-power verifier
summary, strict headless-client player-load evidence, attempted/connected
synthetic player counts with at least two players, join-log latency proxy evidence,
`ai_runtime_scale_gate=pass`, bounded CPU and memory
samples, actionable warning/error counts, compatibility import staging-pilot
evidence, fork-service restart evidence, ranked follow-up issue seeds, repeated
soak iteration results, named soak target duration evidence, and the UDP
`30000`/`30001` service split. It must not write the private SSH target, private
host/IP, remote checkout path, family-world content, prompts, copied assets, or
raw service paths.

The promoted v0.3 target is a one-hour soak after the quick post-deploy proof:

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

The overnight path uses the same gate after the one-hour target is clean:

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

Default low-power budgets are explicit and can be tightened per run:

```text
max_avg_cpu_percent=85
max_interval_cpu_percent=160
max_rss_mb=1024
max_actionable_warning_count=0
max_server_log_error_count=0
max_fork_restarts=0
```
