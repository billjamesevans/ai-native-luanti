# Family Prototype Plugin Boundaries

Status: public-safe inventory for issue #25

## Purpose

The private family-server prototype proves several useful runtime needs: player-owned agents, queued builders, conservative repair, operator controls, custom entities, vehicles, and compatibility experiments. This document maps those ideas into public engine and plugin boundaries without importing private implementation content.

The family server is a proving ground, not product source. The fork should mine behavior categories and safety requirements from it, then build clean public APIs and plugins from scratch.

## Non-Goals

- Do not copy private family-server Lua code, assets, coordinates, player data, server paths, secrets, or operational state.
- Do not include local showcase builders, fixed landmark sites, or one-off family world commands in the engine fork.
- Do not ship protected third-party assets, names, trademarks, or copied Minecraft content.
- Do not keep provider-specific LLM code inside generic agent runtime code.
- Do not allow chat commands or entity callbacks to perform large raw world writes directly.

## Boundary Principles

- Engine code owns reusable primitives: agent identity, capabilities, task queues, safe world operations, action results, metrics, audit, and rollback hooks.
- First-party plugins prove those primitives through small reusable behavior, not private world content.
- Optional demo plugins may ship only after asset provenance, licensing, and destructive behavior are reviewed.
- Local-only server packages may continue to exist outside the fork for family-specific builds and controls.
- Compatibility tooling imports user-supplied content through reviewed reports and bounded tasks.

## Candidate Packages

| Boundary | Public role | Prototype behavior category | Public-safe outcome |
| --- | --- | --- | --- |
| Engine runtime | Core fork capability | Agent ownership, queueing, safe node edits, metrics, audit | Keep in `core` APIs such as `core.register_ai_agent`, `core.queue_ai_task`, and `core.ai_world_ops`. |
| `ai_agent_plugin` | First-party agent plugin | Nova-style chat commands, task status, model adapter boundary | Continue as the clean Nova successor without private coordinates, showcase commands, or direct raw node writes. |
| `build_agent` | First-party plugin or plugin module | Small builds, light placement, marker/platform/road/bridge/house style tasks | Queue bounded build tasks through safe world operations with benchmarkable scenarios. |
| `repair_agent` | First-party plugin and benchmark scenario | Conservative terrain repair, hazard cleanup, safe spawn/scan helpers | Start with read-only scan plans, then add bounded repair mutation after rollback coverage. |
| `compat_import` | First-party compatibility tooling | User-owned pack metadata and generated compatibility reports | Keep dry-run/apply-plan non-mutating until staging and safe-world-op execution are tested. |
| `demo_entities` | Optional demo plugin | Friendly custom creatures, helper mobs, spawn items | Publish only generic examples with reviewed asset provenance and non-destructive defaults. |
| `demo_vehicles` | Optional demo plugin and benchmark pack | Rideable vehicles, smooth controls, entity-step load | Use as an entity-performance and controls benchmark after licensing review. |
| `server_admin_controls` | Optional local or generic admin plugin | Mode switching, fly helpers, invincibility helpers, teleport helpers | Keep family defaults local; public version must be generic, audited, and permission-gated. |
| Local showcase package | Private server package | Large fixed-site builders and theme-specific builds | Keep outside the main fork and outside first-party runtime MVP. |

## Engine API Pressure

The prototype points to these reusable runtime needs:

- Safe node placement, removal, repair, and batch operations with protected-area, hazardous-node, and player-proximity checks.
- Structured action results for success, partial success, blocked, unsafe, failed, and cancelled work.
- Bounded server-step scheduling for long actions.
- Task cancellation, pause, and visible status.
- Per-agent capabilities and owner-scoped permissions.
- Metrics for queue length, task latency, node writes, skipped positions, entity step cost, and model-adapter requests.
- Audit records that preserve what happened without storing private prompts or asset payloads by default.
- Rollback metadata before any world-mutating compatibility or build task.
- Future entity/pathing APIs so agents can move, follow, patrol, defend, and interact without ad hoc entity code.

## Extraction Order

1. Keep the current `ai_agent_plugin` as the reference for public runtime usage.
2. Add a read-only `repair_agent` planning slice that reports candidate repairs without mutation.
3. Add bounded `build_agent` task definitions for small public examples such as lights, markers, platforms, and short paths.
4. Add rollback-backed repair mutation only after safe-world-op rollback metadata exists.
5. Add public demo entity or vehicle packs only after provenance and benchmark requirements are clear.
6. Expand compatibility staging for media/entity metadata before any structure placement work.
7. Leave local showcase builders and family-specific admin defaults outside the fork.

## Public Review Checklist

Before a prototype idea becomes fork or first-party plugin work:

- Is it reusable without private world locations or family-specific assumptions?
- Does every mutating action go through `core.ai_world_ops` or a reviewed equivalent?
- Does long-running work run through `core.queue_ai_task`?
- Does it return structured action results and bounded samples?
- Can the owner or an authorized admin cancel it?
- Does it have metrics and audit coverage?
- Are assets and names cleared for public distribution?
- Does it avoid storing secrets, prompts, player data, or asset payload bytes by default?
- Can it be benchmarked without private worlds?

## Follow-On Issue Candidates

Reusable work is tracked as small implementation issues:

- `#31`: Add a read-only `repair_agent` planning plugin slice.
- `#32`: Add bounded `build_agent` task definitions for lights, markers, platforms, and short paths.
- `#33`: Define rollback metadata for repair and build mutations.
- `#34`: Define public demo entity/vehicle provenance and benchmark requirements.
- `#35`: Add model-adapter request metrics without retaining private prompts.

Local showcase builders, fixed family landmarks, private admin defaults, and unaudited assets should not receive main-fork implementation issues.
