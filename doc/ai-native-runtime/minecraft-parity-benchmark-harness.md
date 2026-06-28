# Minecraft-Parity Benchmark Harness

Status: public-safe comparison harness for issue #124

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
- memory
- CPU
- latency

Current measured facts come from accepted clean-profile benchmark artifacts: startup listening time, player-load or liveness probes, server-step workload samples, map/chunk inspection, generic demo entity benchmarks, mutation/write benchmarks, and memory sampling.

CPU and true client/server network latency are tracked as qualitative Minecraft-parity gaps until public-safe probes exist.

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
- `measured_facts`: hardware-lane facts sourced from accepted benchmark reports.
- `qualitative_minecraft_parity_gaps`: missing or partial evidence that should drive the runtime backlog.
- `source_policy`: explicit separation between project targets and measured fork evidence.
- `retention`: the local benchmark retention lane where the report belongs.
- `privacy_scan`: a focused report-payload privacy scan.

The report must be read as fork evidence plus target gaps, not as a claim that Minecraft internals or proprietary benchmarks were used.
