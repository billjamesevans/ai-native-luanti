# Demo Entity and Vehicle Provenance

Status: public release gate for issue #34

## Purpose

Demo entities and vehicles can prove the AI-native runtime only if they are public-safe, generic, benchmarkable, and reversible. This contract defines what must be true before a first-party demo package can ship from family-prototype ideas.

The fork may use entities and vehicles to exercise movement, ownership, controls, collision, task queues, safe operations, and metrics. It must not import private family-server content or unchecked media from local prototypes.

## Release Gate

Every public demo entity or vehicle package must pass this checklist before it can be merged:

- Art is original, generated for this project, public-domain, or clearly licensed for redistribution.
- Models are original, generated for this project, public-domain, or clearly licensed for redistribution.
- Sounds are original, generated for this project, public-domain, or clearly licensed for redistribution.
- Names are generic and avoid private names, protected brands, trademarks, copied character names, or confusing references to other games.
- Licenses are recorded in a package-level provenance file with source, author when known, license id, modification notes, and redistribution allowance.
- Behavior defaults are non-destructive, permission-gated, and bounded.
- Generic examples replace family-specific creatures, vehicles, commands, paths, coordinates, and showcase assumptions.
- No private family-server content is used as source code, data, media, prompts, commands, or world state.
- No destructive behavior by default: spawning, movement, collision, item interaction, node interaction, and cleanup must avoid griefing unless an authorized admin opts into a bounded test.

## Hard Blocks

- Do not commit assets until their provenance file is reviewed.
- Do not commit models until their provenance file is reviewed.
- Do not commit sounds until their provenance file is reviewed.
- Do not commit private commands.
- Do not commit private world data.
- Do not commit local server paths, screenshots of private worlds, player data, secrets, provider prompts, copied Minecraft content, Disney content, or other protected third-party material.

## Provenance File

Each package that includes media must include a plain-text or JSON provenance file with one record per asset:

- Asset path inside the package.
- Asset type: texture, model, sound, icon, animation, metadata, or generated fixture.
- Source category: original, generated, public-domain, open-license, or user-supplied fixture.
- License name and URL when applicable.
- Author or generator description when applicable.
- Modification summary.
- Redistribution allowance.
- Review date.
- Reviewer.

Generated assets must record the generator class and prompt category without storing private prompts. User-supplied fixtures must be marked as fixtures and excluded from release packages unless their redistribution rights are documented.

## Entity Requirements

Demo entities should stay small, legible, and useful for runtime testing:

- Ownership and spawning must respect agent or player capabilities.
- Entity count limits must be configurable and visible through metrics.
- Movement must be deterministic enough for repeatable benchmark scenarios.
- Collision behavior must avoid pushing players into hazards or protected areas.
- Node interaction must be disabled by default unless routed through reviewed safe world operations.
- Cleanup must remove spawned entities without leaving private state, detached inventories, or unbounded timers.

## Vehicle Requirements

Demo vehicles should prove controls and performance, not ship private prototype behavior:

- Controls must be generic and documented through normal mod metadata.
- Passenger ownership and handoff must be permission-gated.
- Movement and collision must avoid destructive world changes by default.
- Any node placement, digging, projectile, or damage behavior must be disabled until rollback-backed mutation and benchmark coverage exist.
- Vehicle examples should prefer simple first-party fixtures unless an existing open mod is reviewed for license, maintenance, and API fit.

## Benchmark Requirements

Demo entity and vehicle packages must include benchmark scenarios before public release:

- Entity count: fixed-count scenarios at small, medium, and high counts.
- Movement: idle, patrol, follow, and direct-control movement where applicable.
- Collision: player collision, entity-to-entity collision, wall contact, and loaded-mapblock boundary cases.
- Control cost: per-step control handling for empty vehicles, occupied vehicles, and repeated input.
- Server-step impact: average, p95, and max lag while the scenario runs.
- Cleanup cost: despawn and task-cancel behavior after benchmark completion.

Benchmark reports should record hardware class, Luanti commit, game/mod list, entity count, active players or simulated clients, average step, p95 step, max lag, CPU, memory, warning count, and error count.

## Implementation Direction

Use new first-party demo examples for the first public package. Existing open mods can be studied, but should not become dependencies until their licenses, maintenance status, API boundaries, and benchmark behavior are reviewed.

Vehicles can also start as benchmark-only fixtures if controls or physics are not ready for a public gameplay package. That keeps the engine work honest without prematurely shipping gameplay promises.

## Follow-On Work

Implementation issues may be created only for cleared reusable demo work:

- A minimal generic helper entity with provenance metadata and entity-step benchmarks.
- A minimal generic rideable vehicle fixture with control and collision benchmarks.
- A benchmark pack that can run entity and vehicle load tests without private worlds.

Public issues should not include private family names, fixed world locations, private commands, copied media, or private server behavior.
