# Benchmark Baseline Retention

Status: baseline workflow for issue #55

## Purpose

AI-native benchmark gates need stable evidence without committing machine-specific output or private server data. This policy connects mutation benchmark reports and generic demo entity benchmark reports to one local baseline workflow.

## Report Classes

committed synthetic examples live under:

- `doc/ai-native-runtime/examples/mutation-benchmark-report.example.json`
- `doc/ai-native-runtime/examples/generic-demo-entity-benchmark-report.example.json`

These files document report shape only. They are not accepted performance baselines and must not be treated as measured evidence.

local measured reports stay outside commits under:

- `local/benchmarks/local-mac/<YYYY-MM-DD>/<commit>/`
- `local/benchmarks/low-power-server/<YYYY-MM-DD>/<commit>/`
- `local/benchmarks/<hardware-class>/<date>/<commit>/`

Measured reports may include machine timing, branch labels, and local run metadata. They must not include private worlds, media, local paths, secrets, provider prompts, player-private data, private coordinates, or live server operational state.

Accepted local baselines should be retained with:

- the raw benchmark report
- the branch report being compared
- the comparison output from `util/ai_native_benchmark_compare.py`
- the Luanti commit or branch label
- the hardware class
- a short operator note when a regression exception is accepted

## Running Comparisons

Default local capture uses `util/ai_native_benchmark_capture.py`:

```sh
python3 util/ai_native_benchmark_capture.py \
  --hardware-class local-mac \
  --luanti-commit "$(git rev-parse --short HEAD)"
```

The default runner path requires no live server and writes ignored local files under `local/benchmarks/<hardware-class>/<date>/<commit>/`:

- `mutation-benchmark-report.json`
- `generic-demo-entity-benchmark-report.json`
- `benchmark-capture-manifest.json`

When a same-hardware baseline is available, pass it into the capture runner so it writes comparison files next to the branch reports:

```sh
python3 util/ai_native_benchmark_capture.py \
  --hardware-class local-mac \
  --mutation-baseline local/benchmarks/local-mac/accepted/mutation-benchmark-report.json \
  --demo-entity-baseline local/benchmarks/local-mac/accepted/generic-demo-entity-benchmark-report.json
```

## Promoting Accepted Baselines

After a reviewed clean capture is accepted, promote it into the local-only accepted lane with `util/ai_native_benchmark_promote.py`:

```sh
python3 util/ai_native_benchmark_promote.py \
  --capture-dir local/benchmarks/local-mac/2026-06-27/5cd0e627c \
  --output-root local/benchmarks \
  --source-label reviewed-clean
```

The promotion command writes local ignored files under `local/benchmarks/<hardware-class>/accepted/`:

- `mutation-benchmark-report.json`
- `generic-demo-entity-benchmark-report.json`
- `accepted-baseline-manifest.json`

The `accepted-baseline-manifest.json` stores only the commit label, hardware class, source capture label, generated timestamp, and report filenames. It must not contain absolute local paths, private worlds, media, secrets, provider prompts, player-private data, or live server state.

You must not promote a capture when either report has `warnings`, `errors`, `requires_private_world`, `requires_private_assets`, `requires_live_pi`, or a mismatched hardware class. Low-power-server captures remain backup-first and should not be promoted unless the same backup-first review has been completed for the source capture.

Mutation benchmark reports and generic demo entity benchmark reports both use `scenarios[*].metrics`, so they can use the same comparator:

```sh
python3 util/ai_native_benchmark_compare.py \
  --baseline local/benchmarks/local-mac/accepted/mutation-baseline.json \
  --branch local/benchmarks/local-mac/current/mutation-branch.json \
  --output local/benchmarks/local-mac/current/mutation-comparison.json
```

The comparator writes a JSON result that includes only report family, hardware class, commit labels, compared scenarios, threshold percentage, and gate results. It intentionally does not copy input file paths into the comparison output.

## Merge Gates

A branch must not merge when it regresses an accepted baseline for the same `hardware_class` without a written benchmark exception.

The default branch gate is 10 percent for timing and entity-load metrics:

- average step
- p95 step
- max lag
- entity counts

The branch must not merge when these safety metrics regress:

- warnings: new warnings must be reviewed before merge
- errors: branch runtime errors block merge
- node writes: branch node writes must not exceed the accepted baseline or scenario budget
- rollback records: mutating scenarios must preserve required rollback records

Comparison is only valid inside the same hardware class. Do not compare `local-mac` reports against `low-power-server` reports.

## Retention Rules

Keep public docs and committed examples synthetic. Keep measured reports local unless a future issue adds a scrubbed, deliberately committed baseline pack.

Delete or archive local measured reports when they are no longer needed for active branch review. Keep the accepted baseline for each hardware class until a newer clean baseline replaces it.

Low-power server runs are not part of the default workflow. They require a backup-first operator pass, an idle server window, and explicit confirmation that the run does not depend on live private world state.

## Privacy Boundary

Benchmark retention must avoid:

- private worlds
- copied media or asset bytes
- local paths
- secrets
- provider prompts or responses
- player-private data
- fixed family-server coordinates
- live Raspberry Pi operational state

Use synthetic worlds and code-only fixtures for default branch gates. Use live proving-ground runs only after local reports are clean and the target server is backed up.
