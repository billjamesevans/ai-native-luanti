# Post-MVP Alpha Roadmap

Status: roadmap after the AI-native runtime MVP audit reports `mvp-ready`.

## Direction

The fork now has enough runtime surface to move from MVP closure to alpha hardening. The next milestone is not a content pack and not a Minecraft clone. The next milestone is a reliable AI-native server profile where player-owned agents can work under explicit policy, bounded budgets, audit logs, rollback metadata, and benchmark gates.

Compatibility and import work remains second. It should start only through public-safe dry-run inventory and runtime-gated apply paths.

## Alpha Readiness Gate

Alpha is ready when all of these are true:

- `util/ai_native_mvp_audit.py` reports `mvp-ready`.
- The clean `ai_runtime` profile starts in local and low-power-server lanes.
- Clean-profile benchmark reports include server-step/player-load evidence, not only idle liveness.
- Operator metrics expose queue length, task outcomes, task duration, write counts, model outcomes, and unsafe-operation counts.
- First-party agent grants are profile-owned and tested.
- Rollback metadata is required before any world-changing apply path.
- Private family content, showcase worlds, proprietary game content, live hostnames, provider prompts, and copied assets stay outside the core fork.

## Phase 1: Runtime Alpha Hardening

Goal: make the clean server profile measurable and reliable enough to run repeatedly.

Deliverables:

- Low-power-server benchmark capture for the clean `ai_runtime` profile.
- Headless-player or server-step workload in clean-profile benchmark capture.
- Benchmark gate that fails on missing clean-profile reports, player-load probe failures, private-data flags, or unclassified warnings.
- Operator runtime snapshot that remains bounded and public-safe under load.
- Restart/rollback notes that let an operator recover from a bad alpha deployment.

## Phase 2: Agent Product Loop

Goal: make the first-party agents feel like usable tools instead of API demos.

Deliverables:

- Builder, repair, guide, defender, and importer agents as separate first-party plugin surfaces.
- Capability profiles for clean, operator, and family-plugin contexts.
- Chat/operator commands for task status, cancellation, audit review, and rollback review.
- Pathfinding/follow improvements that remain bounded by entity and wall-clock budgets.
- Repair/build plans that explain what will change before they mutate the world.

## Phase 3: Compatibility And Import

Goal: import community-created work where licensing and source metadata permit it, without copying proprietary assets or bypassing runtime safety.

Deliverables:

- Public-safe source inventory format for schematics, map exports, and mod metadata.
- Dry-run import report that classifies what can be mapped, skipped, or blocked.
- Apply request path that requires `import.assets`, explicit approval, rollback policy, and write budgets.
- Per-action provenance and rollback records.
- Compatibility benchmark scenarios for imported structures and mapblock churn.

## Phase 4: Public Alpha Package

Goal: make the fork understandable and repeatable for contributors.

Deliverables:

- One-command local verifier as the required pre-PR gate.
- Clean profile install/run instructions.
- Contributor-safe issue templates for runtime, agent, benchmark, and import work.
- Public-safe sample data only.
- Release notes that separate engine/runtime changes from optional plugins.
