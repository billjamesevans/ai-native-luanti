# Low-Power Pi Evidence Lane

Status: alpha-hardening lane for the side-by-side `ai_runtime` test service.

After the local verifier passes and the fork has been deployed through the
backup-first Pi workflow, collect low-power evidence with:

```bash
python3 util/ai_native_low_power_pi_evidence.py \
  --ssh-target "<operator-supplied-target>" \
  --confirm-backup-first \
  --backup-artifact-label "<backup-archive-name>" \
  --backup-sha256 "<backup-sha256>"
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
attempted/connected synthetic player counts, join-log latency proxy evidence,
and the expected port split: family server on UDP `30000`, fork test service on
UDP `30001`.

## Safety Boundary

The evidence manifest must not retain the SSH target, remote checkout path,
private hostnames, private IPs, provider prompts, copied assets, family-world
content, or showcase names. It records only public-safe service roles, ports,
status booleans, logical artifact paths, and sanitized verifier summaries.

This command does not deploy, restart, or mutate services. It starts only a
disposable verifier server and disposable synthetic client processes on the Pi
checkout. Deployments remain owned by the backup-first Pi deploy workflow. The
evidence lane only proves the current deployed fork state.
