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
- [Runtime metrics and audit API](metrics-audit-api.md)
- [First-party agent plugin](first-party-agent-plugin.md)
- [Benchmark plan](benchmark-plan.md)
- [Baseline status](baseline-status.md)
