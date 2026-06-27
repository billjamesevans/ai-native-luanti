# Benchmark Plan

Status: initial benchmark strategy for the AI-native runtime fork

## Objective

Benchmark whether AI-runtime changes preserve or improve server behavior. Benchmarks must catch regressions in server step time, queued tasks, map writes, entity load, HTTP/model adapter behavior, and player-visible lag.

## Baseline Targets

1. Current upstream fork build from `master`.
2. Stable Luanti release baseline.
3. AI-native runtime branch under test.
4. Low-power server hardware after local behavior is safe.

## Metrics

Collect:

- Server step time average, p95, and max.
- Maximum observed lag.
- Task queue length.
- Running task duration.
- Node writes per step.
- Node inspections per step.
- Mapblock load/write counts when available.
- Entity count by type.
- Active players or simulated clients.
- HTTP/model pending request count and latency when enabled.
- CPU, memory, disk IO, and host temperature for low-power hardware runs.
- Error and warning counts from logs.

## Scenarios

### Idle Server

Run the server with no connected players and no active agents. Observe baseline overhead and warnings.

### Player Exploration

Move through generated and newly generated areas. Measure mapblock load and write behavior.

### Small Agent Build

Queue a small build through safe operations. Repeat multiple times and verify node-write budgets, cancellation, and structured results.

### Medium Agent Build

Queue a larger bounded build. Verify throttling, lag-based pausing, and progress reporting.

### Repair Scan

Run a repair agent over controlled terrain damage. Separate read-only scan cost from mutation cost.

### Entity Load

Measure owned agents, helper entities, vehicles, and mob-like entities at controlled counts.

### HTTP/Model Adapter Pressure

Use a mock adapter first. Verify pending limits, timeouts, and non-blocking server behavior before real HTTP calls.

### Compatibility Import Dry Run

Parse user-supplied pack metadata and structures without mutating the world. Generate explicit compatibility reports.

## Regression Policy

A runtime branch cannot merge if it:

- Blocks server step on HTTP or model calls.
- Performs unbounded node writes in one step.
- Allows agent world writes without capability checks.
- Allows destructive operations without bounds and task identity.
- Removes cancellation for long tasks.
- Hides skipped or unsafe operations from action results.

