# Safe Entity Operations API

Status: first implementation slice for issue #53

## Purpose

`core.ai_entity_ops` gives agents an explicit runtime path for owned helper entities. It keeps spawn, inspect, move, and cleanup work out of ad hoc entity callbacks while preserving the same action result style used by safe world operations.

The first fixture is the generic demo helper from `ai_demo_benchmark:helper`. Node mutation disabled remains part of the boundary: safe entity operations do not place, dig, replace, repair, or otherwise write nodes.

## Operations

### `core.ai_entity_ops.spawn(entity_name, pos, options)`

Spawns a registered entity type as an agent-owned helper.

Required options:

- `agent_id`
- `owner`

Optional options:

- `task_id`
- `entity_id`
- `max_entities`
- `spawn_entity`: injected spawn callback for tests or alternate hosts

The agent must have `entity.spawn`. The requested owner must match the agent owner. Any owner mismatch fails closed. The configured entity limit is enforced before spawn. The operation also fails closed with `owner_mismatch`, `unknown_entity_type`, `duplicate_entity_id`, `entity_limit_exceeded`, or `entity_spawn_failed` when the request cannot be safely completed.

### `core.ai_entity_ops.inspect(entity_id, options)`

Returns a public record for an owned helper entity. The agent must have `entity.control`, and the owner must match the stored entity owner.

### `core.ai_entity_ops.move(entity_id, pos, options)`

Moves an owned helper entity to a bounded target position. The agent must have `entity.control`. Movement can be limited with `options.max_distance` or the agent limit `max_entity_move_distance`. Requests beyond that bound fail closed with `movement_limit_exceeded`.

### `core.ai_entity_ops.cleanup(entity_id, options)`

Removes one owned helper entity. Cleanup is permission-gated through `entity.control` and owner matching.

### `core.ai_entity_ops.cleanup_owned(options)`

Removes all helpers owned by the supplied agent and owner, optionally filtered by `entity_name`. The call is idempotent: when no entities match, it succeeds with `no_owned_entities` and `changed = 0`.

## Action Result

Each operation returns an action result with:

- `ok`
- `status`
- `operation`
- `agent_id`
- `task_id`
- `changed`
- `examined`
- `skipped`
- `reason`
- `message`
- `entity` when one entity is returned
- `metrics`

Entity metrics include `entity_count` and, for movement, `distance`. Node-write metrics remain zero because entity operations do not mutate map nodes.

## Runtime Metrics And Audit

The runtime records:

- `entity_spawns`
- `entity_moves`
- `entity_cleanups`
- `entities_by_type`

Each operation also writes a bounded audit record using event names such as `entity.spawn`, `entity.move`, and `entity.cleanup`. Audit records keep task, agent, status, reason, changed, examined, and skipped counts. They do not retain private payloads.

## Non-Goals

- No autonomous pathfinding.
- No combat or damage behavior.
- No player-follow behavior.
- No vehicle controls.
- No media, model, texture, sound, or animation package.
- No node mutation.
- No private server commands or private world coordinates.
