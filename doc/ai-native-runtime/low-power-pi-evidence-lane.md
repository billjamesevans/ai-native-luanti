# Low-Power Pi Evidence Lane

Status: alpha-hardening lane for the side-by-side `ai_runtime` test service.

Latest post-deploy gate:

- Date: 2026-07-01
- Fork commit: `212900839`
- Backup artifact label: `raspberrypi_luanti_20260701-004002.tgz`
- Backup SHA-256:
  `6cd33caddbbfafe7db24f5521c4b3bb1f3cfe5706bc465472f6d85399e9d7599`
- Pi runtime test: `TestAIRuntime` passed.
- Service boundary: family active on UDP `30000`; fork active on UDP `30001`.
- Agents SDK sidecar: active on loopback TCP `8766`.
- Quality gate: `pass`; live prompt eval `pass`; compatibility import staging
  pilot `pass`; violations `0`; attention items `0`.
- Game discovery: `ai_runtime`, `devtest`, and `openrealm_demo`.
- Player-loop check: `Nova, options` returns pending build choices and the
  selected candidate from runtime state without world mutation.

This is post-deploy proof, not a retained soak manifest. Use the commands below
for quick, one-hour, or overnight low-power evidence manifests.

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
