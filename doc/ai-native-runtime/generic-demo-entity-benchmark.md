# Generic Demo Entity Benchmark

Status: code-only fixture for issues #46 and #52

## Purpose

The first demo entity fixture proves benchmark shape before gameplay content. It exercises entity count, movement, collision, cleanup, and server-step impact through a deterministic helper entity named `ai_demo_benchmark:helper`.

This is not a gameplay creature. It is a small benchmark fixture for runtime validation.

## Provenance

The fixture is code-only. It includes no assets, no models, no sounds, no icons, no user world data, and no local server behavior.

The registered helper entity uses engine primitive properties only. Node mutation disabled is part of the fixture contract, and the benchmark reports `node_writes` as zero for every scenario.

## Runtime Entry Points

The Lua module lives at:

- `builtin/game/demo_entity_benchmark.lua`

Runtime helpers:

- `core.demo_entity_benchmark.get_fixture()`
- `core.demo_entity_benchmark.run_scenario(scenario_id, options)`
- `core.demo_entity_benchmark.run_suite(options)`
- `core.demo_entity_benchmark.run_report(options)`

Operator command:

```sh
/ai_demo_entity_benchmark count=16 steps=5 commit=local-build hardware=local-mac
```

The command returns a compact machine-readable JSON report. The report includes `hardware_class`, `luanti_commit`, `run_context`, `runtime_counters`, and the five scenario results.

Use `hardware=local-mac` for local workstation checks. Use `hardware=low-power-server` only after the benchmark is safe locally and the target server is backed up.

## Scenarios

### entity_count_small

Spawns a fixed small count of generic helper entities and records entity count metrics. The scenario immediately cleans up and leaves zero remaining entities.

### entity_scale_16

Spawns at least 16 generic helper entities, runs bounded patrol movement, records active peak and step impact, then cleans up every helper and leaves zero remaining entities.

### movement_patrol

Runs deterministic patrol movement for a bounded number of steps and records distance moved plus average step, p95 step, and max lag.

### collision_wall_contact

Moves helpers into a synthetic wall boundary and records collision checks and collision events without touching nodes.

### cleanup_despawn

Measures despawn cleanup behavior and confirms the runtime entity metric returns to zero.

## Non-Goals

- No gameplay behavior.
- No player-follow behavior.
- No vehicle controls.
- No media package.
- No node placement, digging, replacement, or repair.
- No private server commands or world coordinates.

## Example Report

Synthetic example report:

- [`examples/generic-demo-entity-benchmark-report.example.json`](examples/generic-demo-entity-benchmark-report.example.json)

The example is a report shape, not a performance baseline. Real benchmark runs should be compared on the same hardware class and commit range.
