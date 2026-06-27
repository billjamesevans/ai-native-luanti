# AI-Native Runtime MVP Spec

Status: initial public-safe fork spec

## Objective

Build the first AI-native runtime milestone in the Luanti fork. The MVP lets AI agents safely inspect and modify a world through explicit APIs, run long tasks without freezing the server, return structured outcomes, and expose enough metrics to benchmark behavior.

## Non-Goals

- Do not implement Minecraft compatibility/import in this milestone.
- Do not ship private server content or showcase builds.
- Do not ship proprietary game assets or require closed server code.
- Do not turn a chat bot into the architecture.
- Do not rewrite the entire Luanti mod system before proving the narrower agent runtime.

## Core Model

An agent is an accountable world actor with identity, owner, capabilities, limits, task state, action results, and audit history.

## Runtime Components

### Agent Identity

Each registered agent has:

- `agent_id`: stable internal identifier.
- `display_name`: player-visible name.
- `owner`: player, server, or automation identity responsible for the agent.
- `plugin`: plugin or mod that registered the agent.
- `capabilities`: explicit permissions granted to the agent.
- `limits`: rate, area, distance, and budget limits.
- `state`: enabled, paused, disabled, or quarantined.

### Capabilities

The MVP capability set:

- `world.read`: inspect nodes, light, safe metadata summaries, and nearby entities.
- `world.place`: place or replace nodes within granted limits.
- `world.dig`: remove nodes within granted limits.
- `world.batch`: perform multi-node operations through a task queue.
- `entity.spawn`: spawn approved entities.
- `entity.control`: move or control an owned entity.
- `player.teleport.self`: move the agent itself.
- `player.teleport.other`: move players, admin-only by default.
- `combat.defend`: target hostile entities.
- `http.llm`: call configured model adapters.
- `import.assets`: prepare user-supplied compatibility imports.
- `admin.override`: bypass selected safety checks, admin-only and always audited.

### Task Queue

Long-running work must be queued, sliced, and cancellable.

A task has:

- `task_id`
- `agent_id`
- `owner`
- `label`
- `status`
- `created_at`
- `updated_at`
- `budget`
- `progress`
- `steps`
- `last_result`

Task statuses:

- `queued`
- `running`
- `paused`
- `completed`
- `cancelled`
- `failed`
- `blocked`
- `unsafe`

Tasks are constrained by server-step budget, node-write budget, and wall-clock budget. Tasks can pause when server lag exceeds configured thresholds.

### Safe World Operations

The MVP API should cover:

- `inspect_area(center, radius, filters)`
- `find_safe_position(anchor, constraints)`
- `place_node(pos, node_name, options)`
- `remove_node(pos, options)`
- `replace_node(pos, expected, replacement, options)`
- `batch_place(placements, options)`
- `batch_remove(positions, options)`
- `summarize_area(center, bounds, options)`
- `spawn_agent_entity(agent_id, pos, entity_type)`
- `move_agent(agent_id, target, options)`

Every operation returns a structured action result. Bulk operations return counts and bounded sample failures.

### Action Result

Every operation returns:

- `ok`: boolean.
- `status`: `success`, `partial`, `blocked`, `unsafe`, `not_found`, `rate_limited`, `permission_denied`, or `error`.
- `operation`: operation name.
- `agent_id`: actor.
- `task_id`: task if applicable.
- `changed`: changed node/entity count.
- `examined`: inspected node/entity count.
- `skipped`: skipped node/entity count.
- `reason`: short machine-readable reason.
- `message`: short human-readable message.
- `samples`: bounded examples of skipped or failed positions.
- `metrics`: elapsed time, server-step slice used, and write counts.

### Safety Gates

The MVP enforces:

- Protected-area checks.
- Unbreakable node checks.
- Liquids and hazards skipped by default.
- Player proximity safety.
- Area bounds.
- Node-write budget per step.
- Entity-spawn limits.
- Task cancellation.
- Audit logging for every admin override.

## First Plugin

The first first-party plugin should be a clean agent plugin that proves:

- One agent per player.
- Local deterministic actions before LLM fallback.
- Optional model adapter.
- Status, task listing, cancellation, follow, come, build, repair, and light commands.
- No direct bulk world writes outside the task queue.
- No private-server showcase commands.

## Testing

Required tests:

- Action result schema.
- Capability checks.
- Task state transitions.
- Queued node placement/removal.
- Protected and unsafe node skips.
- Cancellation.
- Lag-based pausing.
- Plugin command routing.
- Build, repair, inspect, and entity-load benchmarks.

## Acceptance Criteria

The MVP is complete when:

- The fork builds locally.
- Agent identity and capabilities are registered through a first-party runtime path.
- A queued task can inspect, place, and remove nodes through safe operations.
- Every operation returns structured action results.
- Tasks can be cancelled.
- Protected and unsafe operations are skipped and reported.
- Metrics expose queue length, task duration, and node-write counts.
- A first-party agent plugin can run deterministic local actions without direct ad hoc world writes.

