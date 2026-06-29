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

For clean-profile baselines, run the capture after the one-command verification harness has passed and add `--game-profile ai_runtime`:

```sh
python3 util/ai_native_runtime_verify.py \
  --hardware-class local-mac \
  --luanti-commit "$(git rev-parse --short HEAD)"

python3 util/ai_native_benchmark_capture.py \
  --hardware-class local-mac \
  --luanti-commit "$(git rev-parse --short HEAD)" \
  --game-profile ai_runtime
```

The clean-profile capture starts a disposable local `ai_runtime` world and writes:

- `clean-profile-benchmark-summary.json`

That summary records the runner version, Luanti commit, hardware class, and game profile. Its public-safe comparison summary covers startup, idle steady tick behavior, `server_step_workload`, `player_load_tick_probe`, map/chunk workload, entity/runtime operations, mutation/write throughput, memory, CPU, and failure notes. `server_step_workload` is the required bounded workload section: it records attempted, completed, and failed sample counts, sample duration, p95/max sample interval, warning/error counts, and whether the server stayed listening. `map_chunk_workload` is a synthetic disposable-world workload named `synthetic_sqlite_mapblock_churn`; it records mapblock rows before/after, rows created, SQLite byte growth, workload duration, and warning/error counts. `cpu` records bounded process CPU evidence for the disposable server process: sample status, sample count, process CPU time delta, observed wall time, average process CPU percent, max interval CPU percent, and sample method ids. Without a client command, the first player-load/server-step probe remains a bounded server-process liveness probe and records the current headless-player limitation. It must not include temporary paths, private worlds, provider prompts, player data, copied assets, live hostnames, or live service state.

When a disposable client path is available, add `--headless-player-command` to the same clean-profile capture. The command is an operator-supplied template; the runner expands `{host}`, `{port}`, `{name}`, `{server_log}`, and `{duration_seconds}` for each synthetic player. The report stores only bounded evidence, not the command path: `probe_kind=headless_client_load`, attempted and connected synthetic players, completed synthetic players, client exit statuses, cleanup status, warning/error counts, sample intervals, whether the server stayed listening, and a named `headless_join_log_observation` latency proxy. That proxy measures elapsed time from launching each synthetic client process to the first observed server-log join line. It is public-safe join latency evidence, not a claimed network RTT or proprietary Minecraft benchmark.

Clean-profile warning counts are split into raw and classified fields. `server_log_warning_count` remains the total number of warning lines, `expected_server_log_warning_count` records known expected startup warnings, `actionable_server_log_warning_count` records warnings that still need review, and `expected_warning_kinds` stores bounded classification ids such as `run_in_place_builtin_sha_missing`. The scorecard uses actionable warnings for `server_log_warning_cleanup`; old summaries without these fields are treated conservatively as actionable.

For client-capable lanes, build a local client binary with sound disabled so the probe can run with a null video driver:

```sh
cmake -S . -B build/client-probe \
  -DBUILD_CLIENT=TRUE \
  -DBUILD_SERVER=TRUE \
  -DBUILD_UNITTESTS=TRUE \
  -DRUN_IN_PLACE=TRUE \
  -DENABLE_SOUND=FALSE

cmake --build build/client-probe --target luanti --parallel "$(sysctl -n hw.logicalcpu 2>/dev/null || nproc)"
```

On low-power Linux, install client build dependencies before the same configure step:

```sh
sudo apt-get install -y \
  libjpeg-dev libpng-dev libsdl2-dev libfreetype-dev \
  libgl1-mesa-dev libx11-dev libxxf86vm-dev libxi-dev
```

Use a temporary null-video client config for the command:

```sh
tmpconf="$(mktemp /tmp/ai-native-headless-client.XXXXXX)"
printf '%s\n' \
  'video_driver = null' \
  'enable_minimap = false' \
  'enable_post_processing = false' \
  'enable_client_modding = false' \
  'viewing_range = 10' \
  'mute_sound = true' \
  > "$tmpconf"
```

Example local command shape:

```sh
python3 util/ai_native_benchmark_capture.py \
  --hardware-class local-mac \
  --luanti-commit "$(git rev-parse --short HEAD)" \
  --game-profile ai_runtime \
  --headless-player-command "bin/luanti --config $tmpconf --go --address {host} --port {port} --name {name}" \
  --headless-player-count 1
```

Use the one-command verifier when refreshing branch evidence:

```sh
python3 util/ai_native_runtime_verify.py \
  --hardware-class local-mac \
  --luanti-commit "$(git rev-parse --short HEAD)" \
  --game-profile ai_runtime \
  --headless-player-command "bin/luanti --config $tmpconf --go --address {host} --port {port} --name {name}" \
  --headless-player-count 1
```

After the branch passes and the capture is reviewed, promote the refreshed local lane:

```sh
python3 util/ai_native_benchmark_promote.py \
  --capture-dir local/benchmarks/local-mac/<date>/<commit> \
  --output-root local/benchmarks \
  --source-label reviewed-local-headless-client
```

Repeat the same flow for `low-power-server` only after backup-first readiness, keeping the family server side by side and passing `--confirm-low-power-backup` during capture. Use a low-power source label such as `reviewed-low-power-headless-client`.

Do not promote either lane unless the clean-profile summary has `overall_status=pass`, `server_step_workload.workload_status=pass`, `server_step_workload.failed_sample_count=0`, `player_load_tick_probe.probe_status=pass`, `probe_kind=headless_client_load`, `headless_player_supported=true`, `synthetic_player_count>0`, connected synthetic players equal attempted synthetic players, `latency_probe_kind=headless_join_log_observation`, `latency_proxy_supported=true`, and nonzero `join_latency_proxy_ms.sample_count`.

For entity-scale refreshes, review the generated `generic-demo-entity-benchmark-report.json` before promotion. The report must include `entity_scale_16`, and the clean-profile summary must show `entity_runtime_operations.max_entity_count >= 16`, `max_active_peak >= 16`, and `max_remaining_entities = 0`. Promote the local and `low-power-server` captures with labels that identify the scale refresh, then regenerate the scorecard and confirm `entity_scale_runtime_probe` is no longer ranked:

```sh
python3 util/ai_native_benchmark_promote.py \
  --capture-dir local/benchmarks/local-mac/<date>/<commit>-scale16-local \
  --output-root local/benchmarks \
  --source-label reviewed-local-headless-scale16

python3 util/ai_native_benchmark_promote.py \
  --capture-dir local/benchmarks/low-power-server/<date>/<commit>-scale16-low-power \
  --output-root local/benchmarks \
  --source-label reviewed-low-power-headless-scale16

python3 util/ai_native_runtime_gap_scorecard.py \
  --output-root local/benchmarks
```

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
- `clean-profile-benchmark-summary.json` when the reviewed capture used `--game-profile ai_runtime`
- `accepted-baseline-manifest.json`

The `accepted-baseline-manifest.json` stores only the commit label, hardware class, source capture label, generated timestamp, and report filenames. It must not contain absolute local paths, private worlds, media, secrets, provider prompts, player-private data, or live server state.

You must not promote a capture when either scenario report has `warnings`, `errors`, `requires_private_world`, `requires_private_assets`, `requires_live_pi`, or a mismatched hardware class. A clean-profile capture must also have `overall_status=pass`, `game_profile.gameid=ai_runtime`, empty failure notes, `server_step_workload.workload_status=pass`, positive attempted/completed workload sample counts, zero failed workload samples, `map_chunk_workload.workload_status=pass`, nonzero `mapblock_rows_created`, passing `first_party_agent_product_loop` evidence for the build/repair approval loop, and no private or model-network requirements. Low-power-server captures remain backup-first and should not be promoted unless the same backup-first review has been completed for the source capture.

## Running The Branch Gate

After promotion, use `util/ai_native_benchmark_gate.py` for the normal promotion -> branch gate loop:

```sh
python3 util/ai_native_benchmark_gate.py \
  --hardware-class local-mac \
  --luanti-commit "$(git rev-parse --short HEAD)"
```

The gate finds the accepted reports under `local/benchmarks/<hardware-class>/accepted/`, runs a fresh local capture for the branch, compares both benchmark report families, and writes `benchmark-gate-manifest.json` next to the branch reports. It exits `0` when all comparisons pass and will exit nonzero when a required comparison fails or the accepted baseline is missing.

The default gate path requires no live server. It must not depend on private worlds, copied assets, provider prompts, player-private data, local absolute paths, or live Raspberry Pi state. Low-power-server gates stay backup-first and require explicit operator confirmation before they are used.

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

Use the same logical lane for low-power proving-ground captures, but keep the evidence local and generic:

```sh
python3 util/ai_native_benchmark_capture.py \
  --hardware-class low-power-server \
  --luanti-commit "$(git rev-parse --short HEAD)" \
  --game-profile ai_runtime \
  --confirm-low-power-backup
```

Do not write server names, private network addresses, world paths, player names, coordinates, provider configuration, API keys, copied media, or family-showcase content into committed docs or benchmark artifacts. Low-power summaries are for comparing runtime shape against the same clean profile, not for publishing proving-ground operational details.

Clean-profile baselines guide Minecraft-parity work by showing which server-runtime gaps are real before compatibility/import code expands: startup cost, idle stability, map/chunk work, entity/runtime overhead, mutation/write throughput, memory, and failure modes. Compatibility changes should be judged against these measurements without importing proprietary Minecraft code or assets.

## Runtime Gap Scorecard

After both accepted clean-profile lanes exist, build the clean-profile runtime gap scorecard with:

```sh
python3 util/ai_native_runtime_gap_scorecard.py \
  --output-root local/benchmarks
```

The default scorecard reads:

- `local/benchmarks/local-mac/accepted/`
- `local/benchmarks/low-power-server/accepted/`

and writes the ignored local artifact:

- `runtime-gap-scorecard.json`

The report separates measured fork evidence from Minecraft-parity target bands. The measured section covers startup, clean-profile server health, bounded server-step workload evidence, player-load/headless-player probe evidence, mutation throughput, demo entity/runtime cost, map/chunk workload, memory, and failure notes. The target bands are project targets only; they do not use proprietary Minecraft code or assets, server jars, copied benchmarks, copied media, or closed gameplay data.

Use the ranked gaps as the runtime hardening queue before compatibility/import expansion. The first expected gaps are missing or failing `server_step_workload`, missing player-load tick probes, true headless-player load after the server-step workload exists, non-empty map/chunk workload, larger entity-runtime probes, total mutation-write measurements, and clean-profile warning classification. If the scorecard refuses to run, refresh the missing accepted clean-profile baseline with `util/ai_native_benchmark_capture.py`, review it, and promote it with `util/ai_native_benchmark_promote.py`.

The headless-player gap is cleared only when every accepted lane has complete public-safe evidence from `--headless-player-command`: the probe passes, `headless_player_supported=true`, `synthetic_player_count>0`, attempted and connected synthetic players match, cleanup is complete or bounded, and `join_latency_proxy_ms` has at least one sample. Partial evidence remains a ranked gap even if one synthetic player joined.

The scorecard performs a focused privacy scan of the JSON payload before writing the artifact. Do not publish or commit scorecards that include private hosts, private network addresses, local absolute paths, secrets, provider prompts, private showcase names, copied media, or family-server operational details.

## Minecraft-Parity Harness

After accepted clean-profile lanes exist, build the public-safe Minecraft-parity comparison report with:

```sh
python3 util/ai_native_minecraft_parity_harness.py \
  --output-root local/benchmarks
```

Default output:

```text
local/benchmarks/minecraft-parity-comparison-report.json
```

The harness reads the same accepted lanes as the clean-profile runtime gap scorecard and defines explicit dimensions for startup, player join/liveness, server-step stability, mapblock/chunk churn, entity load, world-edit throughput, memory, CPU, latency, mod/plugin ergonomics, operator visibility, and recovery. It separates measured facts from qualitative Minecraft-parity gaps and uses only synthetic workloads, accepted local benchmark reports, or operator-supplied external references. CPU is measured only when the accepted lane has clean-profile process CPU samples; older accepted lanes remain a CPU evidence gap until refreshed. Latency is measured only when the accepted lane has the headless join-log observation proxy; failing or missing headless evidence remains a qualitative gap. The first-party agent-loop gap clears only when every accepted lane includes passing `comparison_summary.first_party_agent_product_loop` evidence with build/repair approval, approved tasks, guide/tasks/cancel command coverage, audit review, rollback review, defender checks, importer preview checks, and zero blocked or unsafe outcomes. Compatibility import inventory discovery remains a separate gap. The harness does not use proprietary Minecraft code or assets, copied server jars, copied media, or closed gameplay data.

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
