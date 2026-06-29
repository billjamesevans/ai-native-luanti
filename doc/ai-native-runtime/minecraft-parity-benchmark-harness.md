# Minecraft-Parity Benchmark Harness

Status: public-safe comparison harness for issue #186

## Purpose

`util/ai_native_minecraft_parity_harness.py` builds a local JSON report that compares AI-native Luanti progress against Minecraft-like server expectations without running proprietary Minecraft code, copying server jars, importing closed gameplay data, or bundling proprietary assets.

The report is a planning and measurement surface. It separates measured facts from qualitative Minecraft-parity gaps so the fork can improve toward Mojang-level quality without pretending that project targets are measured Minecraft data.

## Command

```sh
python3 util/ai_native_minecraft_parity_harness.py \
  --output-root local/benchmarks
```

Default output:

```text
local/benchmarks/minecraft-parity-comparison-report.json
```

Use `--hardware-class local-mac` or `--hardware-class low-power-server` to build a single-lane report. Without `--hardware-class`, the harness expects both accepted local benchmark lanes:

- `local/benchmarks/local-mac/accepted/`
- `local/benchmarks/low-power-server/accepted/`

Those accepted lanes are created by the existing benchmark capture and promotion flow. The parity report is a local retained artifact and should not be committed unless a future issue defines a scrubbed public baseline pack.

## Dimensions

The harness defines these comparison dimensions:

- startup
- player join/liveness
- server-step stability
- mapblock/chunk churn
- entity load
- world-edit throughput
- persistence
- mod/plugin ergonomics
- operator visibility
- recovery
- memory
- CPU
- latency

Each dimension carries pass/warn/fail criteria. A pass means measured evidence meets the current project target, a warn means evidence is partial or proxy-only but safe and useful, and a fail means evidence is missing, failing, private, unsafe, or not reproducible.

Dimensions also carry a gap area so engine/runtime gaps stay separate from game-content or plugin gaps and operator-experience gaps. This prevents a missing content feature from looking like an engine regression, and keeps plugin ergonomics work visible without polluting core runtime evidence.

Current measured facts come from accepted clean-profile benchmark artifacts: startup listening time, player-load or liveness probes, headless join-log latency proxies when a synthetic client command is supplied, server-step workload samples, synthetic mapblock/chunk churn, generic demo entity benchmarks, mutation/write benchmarks, persistence and rollback metadata, operator status/task-control probes, memory sampling, and bounded process CPU sampling.

The scenarios are safe to run locally and on the Pi side-by-side service. They use disposable `ai_runtime` worlds, public-safe synthetic clients and fixtures, rollback-backed mutation reports, and operator command probes. They do not require a private world or proprietary Minecraft assets.

The first mapblock/chunk churn probe is `synthetic_sqlite_mapblock_churn`. It runs only in the disposable clean-profile benchmark world and records mapblock rows before/after, rows created, SQLite byte growth, workload duration, and warning/error counts.

The first latency probe is `headless_join_log_observation`. It runs only with public-safe headless synthetic players and records the elapsed time from launching each synthetic client process to the first observed server-log join line. It is classified as measured join-latency proxy evidence, while true network RTT remains future work.

CPU uses clean-profile process CPU samples for the disposable server process. The harness records sample count, average process CPU percent, max interval CPU percent, process CPU time delta, and sample method ids. Missing or failed CPU sampling remains a qualitative Minecraft-parity gap until refreshed accepted lanes contain measured CPU evidence.

First-party agent-loop proof comes from `comparison_summary.first_party_agent_product_loop` in accepted clean-profile summaries. The harness clears the first-party product-loop gap only when that evidence records passing build/repair approval, approved tasks, guide/tasks/cancel command coverage, audit review, rollback review, defender checks, importer preview checks, and zero blocked or unsafe outcomes. Compatibility import inventory discovery remains a separate plugin gap until it has its own public-safe report.

Compatibility import inventory proof comes from `local/benchmarks/compatibility-import-inventory-discovery-report.json`. The harness treats it as plugin evidence only when the report is `ready_for_import_preview`, remains dry-run-only, records no copied assets or world mutation, redacts source paths, rejects raw/private payloads, and avoids proprietary Minecraft code, server jars, and closed gameplay data.

## Public-Safe Source Policy

Allowed inputs:

- synthetic `ai_runtime` worlds
- generic demo entity fixtures
- rollback-backed synthetic mutation workloads
- local accepted benchmark reports under `local/benchmarks`
- operator-supplied external references when they are recorded as references only

Not allowed:

- proprietary Minecraft code or assets
- copied server jars
- closed gameplay data
- private family worlds or showcase content
- private hosts, network addresses, paths, prompts, player-private data, or secrets

## Report Shape

The JSON report contains:

- `comparison_dimensions`: the dimensions and metric paths the harness understands.
- `scorecard_status_criteria`: the pass/warn/fail meaning used by every dimension.
- `benchmark_scenarios`: local/Pi-safe scenario metadata for reproducible runs.
- `measured_facts`: hardware-lane facts sourced from accepted benchmark reports.
- `qualitative_minecraft_parity_gaps`: missing or partial evidence that should drive the runtime backlog.
- `actionable_scorecard`: ranked, deduplicated parity actions grouped across hardware lanes. A single dimension may produce multiple actions when the remaining work has separate owners, such as first-party agent-loop proof versus compatibility import inventory.
- `gap_summary_by_area`: counts for engine/runtime, game-content, plugin, and operator-experience gaps.
- `source_policy`: explicit separation between project targets and measured fork evidence.
- `retention`: the local benchmark retention lane where the report belongs.
- `privacy_scan`: a focused report-payload privacy scan.

The report must be read as fork evidence plus target gaps, not as a claim that Minecraft internals or proprietary benchmarks were used.
