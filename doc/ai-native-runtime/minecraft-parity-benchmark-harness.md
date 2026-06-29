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
- agent tool powers
- operator visibility
- recovery
- memory
- CPU
- latency

Each dimension carries pass/warn/fail criteria. A pass means measured evidence meets the current project target, a warn means evidence is partial or proxy-only but safe and useful, and a fail means evidence is missing, failing, private, unsafe, or not reproducible.

Dimensions also carry a gap area so engine/runtime gaps stay separate from game-content or plugin gaps and operator-experience gaps. This prevents a missing content feature from looking like an engine regression, and keeps plugin ergonomics work visible without polluting core runtime evidence.

## Target Bands

The harness publishes `target_bands` in every report and repeats the relevant
band on each dimension result. These bands are project targets for this fork,
not measured Minecraft internals:

| Dimension | Current target band |
| --- | --- |
| startup | server listens and `time_to_listen_ms <= 15000` |
| player join/liveness | public-safe headless client supported, at least 2 synthetic players attempted and connected, server remains listening |
| server-step stability | at least 10 completed samples, 0 failed samples, `p95_sample_interval_ms <= 250`, `max_sample_interval_ms <= 1000` |
| mapblock/chunk churn | SQLite/map inspection is `ok` and at least 1 mapblock row is present |
| entity load | at least 16 generic helper entities, 0 remaining entities, 0 warnings, 0 errors |
| world-edit throughput | at least 1 rollback-backed node write, at least 1 rollback record, max 16 writes per step, 0 warnings, 0 errors |
| persistence | map SQLite bytes are nonzero and at least 1 rollback record exists |
| mod/plugin ergonomics | first-party agent loop and `ai_runtime_scale_gate` pass with at least 2 queued/completed agent tasks, and compatibility inventory discovery is ready with at least 1 source and 1 planned action |
| agent tool powers | Agents SDK sidecar readiness passes, `tool_powers` declares `summarize_runtime_capabilities`, `classify_world_action`, and `WebSearchTool`, every listed power has `direct_world_mutation=false`, and `world_mutation_authority=luanti` |
| operator visibility | operator status, task control, and receipt-gated task control are present |
| recovery | at least 1 rollback record and task-control actions do not mutate the world |
| memory | at least 2 RSS samples and `max_rss_kb <= 262144` |
| CPU | at least 2 CPU samples, `avg_process_cpu_percent <= 150`, `max_interval_cpu_percent <= 250` |
| latency | headless join-log latency proxy present, at least 1 sample, `p95 <= 2000ms`, `max <= 5000ms` |

Changing a target band requires a normal reviewed PR that updates the harness,
this document, and tests. The PR body should explain whether the change raises
the alpha bar, relaxes an unrealistic threshold, or adds a new measurement path.
Target changes must not cite proprietary Minecraft code, server jars,
marketplace assets, private worlds, or private benchmark captures.

Current measured facts come from accepted clean-profile benchmark artifacts: startup listening time, player-load or liveness probes, headless join-log latency proxies when a synthetic client command is supplied, server-step workload samples, synthetic mapblock/chunk churn, generic demo entity benchmarks, mutation/write benchmarks, persistence and rollback metadata, operator status/task-control probes, memory sampling, bounded process CPU sampling, and the Agents SDK sidecar readiness report.

The scenarios are safe to run locally and on the Pi side-by-side service. They use disposable `ai_runtime` worlds, public-safe synthetic clients and fixtures, rollback-backed mutation reports, and operator command probes. They do not require a private world or proprietary Minecraft assets.

The first mapblock/chunk churn probe is `synthetic_sqlite_mapblock_churn`. It runs only in the disposable clean-profile benchmark world and records mapblock rows before/after, rows created, SQLite byte growth, workload duration, and warning/error counts.

The first latency probe is `headless_join_log_observation`. It runs only with public-safe headless synthetic players and records the elapsed time from launching each synthetic client process to the first observed server-log join line. It is classified as measured join-latency proxy evidence, while true network RTT remains future work.

CPU uses clean-profile process CPU samples for the disposable server process. The harness records sample count, average process CPU percent, max interval CPU percent, process CPU time delta, and sample method ids. Missing or failed CPU sampling remains a qualitative Minecraft-parity gap until refreshed accepted lanes contain measured CPU evidence.

First-party agent-loop proof comes from `comparison_summary.first_party_agent_product_loop` and `comparison_summary.ai_runtime_scale_gate` in accepted clean-profile summaries. The harness clears the first-party product-loop gap only when that evidence records passing build/repair approval, approved tasks, guide/tasks/cancel command coverage, audit review, rollback review, defender checks, importer preview checks, at least two queued/completed tasks, rollback records, task-duration fields, zero blocked or unsafe outcomes, and a passing multi-player/multi-agent scale gate. Compatibility import inventory discovery remains a separate plugin gap until it has its own public-safe report.

Compatibility import inventory proof comes from `local/benchmarks/compatibility-import-inventory-discovery-report.json`. The harness treats it as plugin evidence only when the report is `ready_for_import_preview`, remains dry-run-only, records no copied assets or world mutation, redacts source paths, rejects raw/private payloads, and avoids proprietary Minecraft code, server jars, and closed gameplay data.

Agent tool-power proof comes from `local/benchmarks/agents-sdk-sidecar-readiness.json`.
The harness treats it as first-party plugin evidence only when the sidecar reports
passing readiness, declares `tool_powers` for deterministic function tools and
hosted web lookup, and proves that no sidecar tool directly mutates the Luanti
world. Agents may reason, call tools, and look up current public information
through the Agents SDK sidecar, but world edits still have to return through the
engine task preview, approval, rollback, and audit path.

## Public-Safe Source Policy

Allowed inputs:

- synthetic `ai_runtime` worlds
- generic demo entity fixtures
- rollback-backed synthetic mutation workloads
- local accepted benchmark reports under `local/benchmarks`
- Agents SDK sidecar readiness reports
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
- `target_bands`: project target bands applied to measured fork evidence.
- `accepted_baseline_policy`: proof that same-hardware accepted lanes are required before comparison.
- `benchmark_scenarios`: local/Pi-safe scenario metadata for reproducible runs.
- `measured_facts`: hardware-lane facts sourced from accepted benchmark reports.
- `qualitative_minecraft_parity_gaps`: missing or partial evidence that should drive the runtime backlog.
- `actionable_scorecard`: ranked, deduplicated parity actions grouped across hardware lanes. A single dimension may produce multiple actions when the remaining work has separate owners, such as first-party agent scale-gate proof versus compatibility import inventory.
- `ranked_improvement_targets`: project-management targets derived from the actionable scorecard, with priority, owner lane, current evidence, target bands, next action, and done-when checks for each remaining Minecraft-parity improvement.
- `improvement_target_summary`: counts for ranked improvement targets by priority and owner lane.
- `issue_seeds`: public-safe follow-up issue seeds generated from the actionable scorecard, including labels, acceptance checks, evidence, and source-policy safety flags.
- `issue_seed_summary`: counts for the generated follow-up issue seeds by status, gap area, and hardware lane.
- `gap_summary_by_area`: counts for engine/runtime, game-content, plugin, and operator-experience gaps.
- `source_policy`: explicit separation between project targets and measured fork evidence.
- `retention`: the local benchmark retention lane where the report belongs.
- `privacy_scan`: a focused report-payload privacy scan.

The report must be read as fork evidence plus target gaps, not as a claim that Minecraft internals or proprietary benchmarks were used.
