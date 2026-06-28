# AI-Native Runtime

Status: project direction for the `billjamesevans/ai-native-luanti` fork.

## Mission

Build an AI-native voxel server/runtime on top of Luanti. The first milestone is not Minecraft compatibility. The first milestone is a safer runtime where human players and AI agents can share a world, perform bounded work, report structured results, and remain observable and cancellable.

Compatibility and import tooling comes after the runtime can safely inspect, modify, repair, and explain world changes.

## Scope

The fork should add reusable runtime capabilities:

- Agent identity and ownership.
- Capability-based permissions for agents and plugins.
- Cancellable server-side task queues.
- Safe world operation APIs for inspect, place, remove, replace, batch, move, and summarize.
- Structured action results for every operation.
- Metrics and audit trails for long-running agent work.
- Benchmark gates for world edits, entity load, mapblock churn, and server-step impact.

The fork should not absorb private-server content, showcase builds, copied proprietary assets, or one-off world coordinates.

## Design Documents

- [MVP spec](mvp-spec.md)
- [Agent identity and capability API](agent-api.md)
- [Agent task queue API](task-queue-api.md)
- [Safe world operations API](safe-world-ops-api.md)
- [Safe entity operations API](safe-entity-ops-api.md)
- [Runtime metrics and audit API](metrics-audit-api.md)
- [First-party agent plugin](first-party-agent-plugin.md)
- [Family prototype plugin boundaries](family-prototype-plugin-boundaries.md)
- [Repair agent plugin](repair-agent-plugin.md)
- [Build agent plugin](build-agent-plugin.md)
- [Rollback metadata](rollback-metadata.md)
- [Demo entity and vehicle provenance](demo-entity-vehicle-provenance.md)
- [Generic demo entity benchmark](generic-demo-entity-benchmark.md)
- [Compatibility import dry-run reports](compatibility-import-dry-run.md)
- [Compatibility apply phase](compatibility-apply-phase.md)
- [Benchmark plan](benchmark-plan.md)
- [Mutation benchmark scenarios](mutation-benchmark-scenarios.md)
- [Benchmark baseline retention](benchmark-baseline-retention.md)
- [Synthetic runtime smoke](synthetic-runtime-smoke.md)
- One-command local pre-PR verification: `python3 util/ai_native_runtime_verify.py --hardware-class local-mac`
- Clean-profile runtime gap scorecard: `python3 util/ai_native_runtime_gap_scorecard.py --output-root local/benchmarks`
- [AI runtime server profile](non-devtest-server-profile.md)
- [Baseline status](baseline-status.md)
