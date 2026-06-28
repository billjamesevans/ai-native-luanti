# Safe Player Operations API

Status: first implementation slice for issue #97

## Purpose

`core.ai_player_ops` gives AI agents a small, explicit runtime path for player movement and defensive combat. It keeps teleport and combat-adjacent behavior permission-gated, bounded, structured, and audited instead of relying on ad hoc chat commands.

This API is intentionally conservative. It proves the MVP capability names and default-deny behavior without adding autonomous pathfinding, broad combat AI, private server commands, or game-specific content.

## Operations

### `core.ai_player_ops.teleport_self(pos, options)`

Moves the player owned by the agent to a bounded target position.

Required options:

- `agent_id`
- `owner`

Optional options:

- `player_name`; defaults to `owner`
- `task_id`
- `max_distance`
- `get_player_by_name`; injected lookup for tests or alternate hosts

The agent must have `player.teleport.self`. The requested player must match the agent owner and supplied owner. Requests fail closed with `owner_mismatch`, `unknown_player`, `player_attached`, `movement_limit_exceeded`, or `player_move_failed` when the runtime cannot safely move the player.

### `core.ai_player_ops.teleport_player(player_name, pos, options)`

Moves another player to a bounded target position.

Required options:

- `agent_id`
- `owner`

Optional options:

- `task_id`
- `max_distance`
- `get_player_by_name`

The agent must have both `admin.override` and `player.teleport.other`. The admin override requirement is deliberate: other-player teleport is admin-only by default. Requests without admin override fail closed with `admin_override_required`.

### `core.ai_player_ops.defend(player_name, options)`

Applies one bounded defensive action against the nearest hostile target within the agent's defend distance.

Required options:

- `agent_id`
- `owner`

Optional options:

- `task_id`
- `max_distance`
- `get_player_by_name`
- `hostiles`; deterministic hostile candidate list
- `find_hostiles`; callback used when `hostiles` is not supplied
- `attack_entity`; callback that applies the defensive action

The agent must have `combat.defend`, and the requested player must match the agent owner and supplied owner. The API selects the nearest hostile candidate within the configured limit. If no target is available, it returns `no_hostile_target`. If no safe attack callback or punch path succeeds, it returns `attack_failed`.

## Action Result

Each operation returns a structured action result with:

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
- `player` for teleport operations
- `target` for defend operations
- `metrics.distance`

Node-write metrics remain zero. These operations move players or apply a bounded defensive action; they do not place, dig, replace, or import map content.

## Runtime Metrics And Audit

The runtime records:

- `player_teleports`
- `combat_defends`

Each operation writes a bounded audit record using event names such as `player.teleport_self`, `player.teleport_player`, and `player.defend`. Audit records keep task, agent, operation, status, reason, and changed/examined/skipped counts. They do not retain private prompts, private world coordinates beyond the action result, or payload bodies.

## Non-Goals

- No broad combat AI.
- No autonomous pathfinding.
- No continuous protection loop.
- No private server commands or private player policy.
- No proprietary game behavior.
- No compatibility/import behavior.
