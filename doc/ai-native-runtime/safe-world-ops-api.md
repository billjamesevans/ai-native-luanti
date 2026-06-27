# Safe World Operations API

Status: first implementation slice for issue #4

## Purpose

The safe world operations API gives AI agents and first-party plugins one structured path for world inspection and node edits. It is intentionally stricter than raw `core.set_node` and `core.remove_node`: every operation reports what it examined, changed, skipped, and why.

The first implementation is Lua-level and lives at `core.ai_world_ops`. It defaults to Luanti's existing node APIs, while tests and future tools can inject `get_node` and `set_node` hooks through the options table.

## Result Shape

Every operation returns an action result:

- `ok`: `true` for `success` or `partial`, otherwise `false`.
- `status`: `success`, `partial`, `blocked`, `unsafe`, `not_found`, or `error`.
- `operation`: stable operation name such as `ai_world.place_node`.
- `agent_id`: actor id when supplied.
- `task_id`: queued task id when supplied.
- `changed`: node count changed.
- `examined`: node or position count checked.
- `skipped`: node or position count skipped.
- `reason`: machine-readable result reason.
- `message`: short human-readable explanation.
- `samples`: bounded sample failures or matches.
- `metrics`: currently includes `elapsed_us` and `node_writes`.

## Operations

### `core.ai_world_ops.inspect_area(center, radius, filters, options)`

Inspects a cube around `center`. `radius = 0` inspects one node. `filters.node_names` may be a map or array of node names. Matching nodes are returned in bounded `samples`.

### `core.ai_world_ops.find_safe_position(anchor, constraints)`

Checks candidate offsets from `anchor` and returns the first safe buildable position as `result.pos`. Constraints may include `offsets`, `bounds`, `owner`, `agent_id`, `min_player_distance`, and injected world hooks.

### `core.ai_world_ops.place_node(pos, node_name, options)`

Places a registered node only when the target is loaded, in bounds, not protected, not near a player, not hazardous, and buildable. Existing occupied nodes are blocked unless `options.replace_existing` is set.

### `core.ai_world_ops.remove_node(pos, options)`

Removes a node by setting it to `air`. Air, unloaded, protected, unbreakable, hazardous, out-of-bounds, and player-proximity cases are reported instead of silently mutating.

### `core.ai_world_ops.replace_node(pos, expected, replacement, options)`

Replaces a node only when the existing node name matches `expected`. Expected-node mismatches return `not_found` with reason `expected_node_mismatch`.

### `core.ai_world_ops.batch_place(placements, options)`

Runs bounded placements. Each placement is `{ pos = <position>, node_name = <registered node> }`. `options.max_changes` limits writes. Skips are counted and sampled.

### `core.ai_world_ops.batch_remove(positions, options)`

Runs bounded removals over an array of positions. `options.max_changes` limits writes. Skips are counted and sampled.

## Safety Gates

The first slice checks:

- registered target nodes
- loaded positions
- optional bounds
- `core.is_protected(pos, owner)`
- optional `min_player_distance`
- unbreakable nodes through `diggable == false` or group `unbreakable`
- hazardous nodes through liquid type or groups `hazard`, `lava`, or `fire`
- occupied place targets unless `replace_existing` is explicit
- batch write budgets through `max_changes`

## Current Limits

- The implementation is Lua-level, not a C++ map-edit transaction system.
- Rollback metadata is not recorded automatically by raw safe-world operations. Mutating AI plugins should wrap safe-world calls with `core.run_ai_world_mutation_with_rollback` before they enable repair, build, or compatibility-import writes.
- Protection and player-proximity checks use current runtime hooks only.
- Hazard detection is conservative and group-based.
- Batch operations are sequential and stop only through their write budget.
- `summarize_area`, entity spawning, movement, and pathing remain future work.

## Direct Mutation Paths To Harden

Follow-up PRs should route or audit these paths where agent/plugin code may perform large edits:

- `core.set_node`, `core.add_node`, and `core.swap_node`
- `core.remove_node`
- `core.bulk_set_node` and `core.bulk_swap_node`
- `core.item_place_node` and item dig/place callbacks
- falling-node restore/removal paths in `builtin/game/falling.lua`
- any future first-party agent plugin that writes nodes directly

The immediate rule for agent-facing code is simple: use `core.ai_world_ops` rather than raw node mutation APIs.
