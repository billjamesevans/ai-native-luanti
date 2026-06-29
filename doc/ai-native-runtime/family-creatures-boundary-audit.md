# Family Creatures Boundary Audit

Status: public-safe concept audit for issue #241.

## Audit Source And Rule

This audit reviewed the private `family_creatures` prototype as a behavior
inventory only. No Lua implementation, assets, private coordinates, private
prompts, family-world data, provider credentials, local server paths, or
showcase builds are imported into the fork.

The family server remains a proving ground. The upstream engine fork receives
only reusable runtime primitives and clean first-party plugin surfaces.

## Concept Classification

| Prototype concept | Classification | Fork outcome |
| --- | --- | --- |
| Player-owned AI companion with one visible agent per player, local state, follow/come/stay/patrol modes, and command/chat entrypoints | First-party clean plugin behavior on existing engine primitives | Keep in `ai_agent_plugin` style plugins. Use `core.register_ai_agent`, owner-scoped capabilities, bounded navigation, safe entity/player ops, operator status, and task-control evidence. |
| Provider-specific model calls, model selection commands, async HTTP polling, request cooldowns, and response parsing | Optional model-adapter plugin, not engine runtime | Keep the engine provider-neutral. Route through the model-adapter contract, reject raw/private payload fields, and keep provider settings out of clean `games/ai_runtime`. |
| Agent plan interpreter for boxes, clears, spheres, rings, lines, lights, and material choices | First-party plugin behavior after schema tests | Keep as public-safe plan validation in a build/import plugin. Every generated action must become bounded task steps, use safe world ops, and record rollback before mutation. |
| Queued builder tasks for lights, platforms, markers, simple houses, towers, bridges, roads, gardens, fountains, mazes, race tracks, and imagined small builds | First-party `build_agent` plugin behavior | Use reusable public examples only. Tasks must run through `core.queue_ai_task`, write through `core.ai_world_ops`, expose progress, enforce write budgets, and retain benchmark evidence. |
| Large fixed landmark builders and showcase commands including `spacebase`, `themepark`, `showcase100`, and `disneyland100` | Private content that must stay out | Do not move into the main fork. At most, extract generic build-task needs such as chunking, approval, rollback, mapblock churn evidence, and operator cancellation. |
| Conservative terrain repair bot with natural-material scans, hazard cleanup, safe spawn checks, and explicit repair command | First-party `repair_agent` plugin behavior | Keep read-only planning and bounded repair apply as reusable plugin surfaces. Mutating repair requires safe world ops, rollback metadata, protection checks, player-proximity checks, and focused tests. |
| Creature and helper entities, spawn eggs/items, beacons, pods, particles, and custom creature behavior | Optional demo entity plugin after provenance review | Keep out of engine runtime. Public demos must use original or rights-cleared assets, non-destructive defaults, safe spawn limits, ownership, cleanup, and entity-load benchmarks. |
| Rideable vehicles with spawner items, attach/detach driver behavior, steering, hover/climb tuning, collision boxes, damage, and destruction | Optional demo vehicle plugin and benchmark pack | Do not make vehicles an engine requirement. If published, require asset provenance, safe entity-control APIs, ownership checks, attach/detach safety, entity-step metrics, and destructive behavior tests. |
| Combat-adjacent helper actions such as defend, attack hostile targets, durable helpers, and destructive tools | Optional plugin behavior behind strict capabilities | Keep player safety first. Use `core.ai_player_ops` for defensive actions, deny player attacks by default, and require explicit capabilities plus audit for any destructive world or entity action. |
| Admin convenience commands for time, modes, fly, invincibility, teleport overrides, and family-specific defaults | Optional local admin plugin or generic audited admin plugin | Keep family defaults local. A public version must be generic, permission-gated, audited, and separate from the clean `ai_runtime` profile. |
| Decorative map/sign/marker nodes and attraction labels | Optional content plugin or private package | Generic signs can be public only with clean assets and no private world assumptions. Attraction-specific labels and site maps stay local/private. |
| Public help text, command discovery, status text, and task summaries | Operator/user experience behavior | Reuse the pattern, not the content. Keep bounded command summaries in first-party plugins and expose runtime state through `/ai_runtime_operator_status`. |

## Smallest Reusable API Set

No new engine API should be added for this audit alone. Family-like plugins
should first prove they can use the current runtime surface:

- Agent identity and capability checks: `core.register_ai_agent`,
  `core.get_ai_agent`, and `core.check_agent_capability`.
- Task scheduling and cancellation: `core.queue_ai_task` and
  `/ai_runtime_operator_task_control`.
- Safe world reads/writes: `core.ai_world_ops`, write budgets, skipped counts,
  protection checks, and player-proximity checks.
- Rollback and audit: rollback metadata before mutation plus compact audit
  events for task, world, entity, player, model, and import actions.
- Safe entity/player operations: bounded spawn, inspect, move, cleanup,
  self-movement, defensive actions, and owner checks.
- Bounded navigation/perception: public navigation contract, searched-node
  limits, wall-clock limits, distance limits, and blocked reasons.
- Model boundary: `core.ai_agent_plugin.set_model_adapter` with public prompt,
  timeout, size limits, and raw/private payload rejection.
- Operator visibility: `/ai_runtime_operator_status` views for tasks, one task,
  audit, rollback, and imports.

Future engine work is allowed only when a plugin cannot express a reusable
behavior through these APIs without duplicating unsafe logic. That future work
needs a failing contract test first, usually in `TestAIRuntime` for engine Lua
behavior or `util/tests` for artifact and public-safety contracts.

## Plugin Boundary Decisions

| Package | Allowed in main fork | Required proof |
| --- | --- | --- |
| `ai_agent_plugin` | Yes, first-party runtime plugin | Owner-scoped agent, bounded movement, model adapter, task/status commands, no private content. |
| `build_agent` | Yes, first-party plugin | Small public build examples, queued steps, safe world ops, rollback, benchmark coverage, no fixed private sites. |
| `repair_agent` | Yes, first-party plugin | Read-only plans first, bounded apply second, rollback, protection checks, operator visibility. |
| `compat_import` | Yes, first-party tooling | Dry-run inventory, preview, explicit approval, bounded apply, rollback, public-safe evidence. |
| `demo_entities` | Optional | Rights-cleared assets, spawn/cleanup limits, entity-load benchmarks, no protected names or private content. |
| `demo_vehicles` | Optional | Rights-cleared assets, safe attachment/control, damage/destruction tests, entity-step benchmarks. |
| `server_admin_controls` | Optional/local | Generic permission gates and audit. Family defaults stay out. |
| Local showcase package | No | Remains outside the fork. |

## Public-Safe Extraction Checklist

Before a family prototype idea becomes fork work:

- It must be useful without private coordinates or family-world assumptions.
- It must not require `spacebase`, `themepark`, `showcase100`,
  `disneyland100`, local-only assets, or private family data.
- It must not copy `family_creatures/init.lua` or assets wholesale.
- It must route mutation through safe world/entity/player APIs.
- It must have explicit capabilities, budgets, rollback, audit, and operator
  visibility.
- It must have tests before engine APIs change.
- It must be benchmarkable with synthetic `ai_runtime` worlds.
- It must keep provider-specific model code in optional adapters.
