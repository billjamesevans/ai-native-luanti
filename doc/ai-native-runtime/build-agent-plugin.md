# Build Agent Plugin

Status: rollback-backed execution slice for issue #44

## Purpose

`core.build_agent` defines small reusable build tasks that can be queued through the AI task runtime and executed through `core.ai_world_ops`. The definition path does not queue work, write nodes, copy assets, or depend on private family-server builds.

Queued execution now requires rollback metadata before any node writes occur. If rollback metadata cannot be prepared and persisted, the queued step blocks before mutation.

The first task kinds are deliberately modest and benchmarkable:

- `lights`
- `marker`
- `platform`
- `path`

## API

### `core.build_agent.configure(options)`

Configures game-specific nodes and limits:

```lua
core.build_agent.configure({
	light_node = "default:torch",
	marker_node = "default:mese_post_light",
	platform_node = "default:stone",
	path_node = "default:stone",
	max_nodes_per_task = 32,
	sample_limit = 8,
})
```

### `core.build_agent.define_task(options)`

Returns a task definition compatible with `core.queue_ai_task`.

Required options:

- `kind`: `lights`, `marker`, `platform`, or `path`
- `task_id`
- `agent_id`
- `owner`
- `origin`

Useful optional fields:

- `count` for lights
- `width` and `depth` for platforms
- `length` and `direction` for paths
- `max_node_writes_per_step`
- `world_id`
- `persist_record(record)` or `persist_rollback_record(record)`
- `rollback_policy`
- injected `get_node` and `set_node` hooks for tests

The returned definition includes:

- `task_id`, `agent_id`, `owner`, and `label`
- `required_capabilities.world.place = true`
- `mutation_class = "build"`
- `metadata.kind`
- `metadata.placement_count`
- `budget.max_steps_per_step = 1`
- `budget.max_node_writes_per_step`
- one task step that calls `core.run_ai_world_mutation_with_rollback`, then `core.ai_world_ops.batch_place`

### `core.build_agent.plan(options)`

Returns a read-only build preview for the same task kinds accepted by
`define_task`. Planning does not queue a task, persist rollback records, or
write nodes.

The result includes:

- `operation = "build_agent.plan"`
- `changed = 0`
- `metrics.node_writes = 0`
- `metrics.planned_node_writes`
- `plan.kind`
- `plan.placement_count`
- `plan.rollback_policy`
- `plan.required_capabilities`
- `plan.will_mutate = false`
- bounded placement `samples`

## Safety Boundary

`plan` and `define_task` are inert. `plan` returns a preview, while `define_task`
prepares a queueable definition. Neither queues work or executes mutation by
itself.

The queued step uses `core.run_ai_world_mutation_with_rollback` and `core.ai_world_ops.batch_place` instead of raw node mutation APIs. It returns `blocked` with `reason = "rollback_metadata_unavailable"` if the caller does not provide rollback persistence or previous-node capture fails.

Successful execution returns the safe-world action result with `rollback_record_id` and `rollback_storage_ref` attached. Rollback records use `mutation_class = "build"` and `operation_label = "build_agent.execute"` by default.

Larger or destructive build work should remain out of this plugin until benchmark coverage is mature enough for broader mutation scenarios.

## Private Content Boundary

This plugin must not include private showcase builds, fixed family world locations, protected names, copied assets, or one-off local commands. Game-specific packages can configure node names, but build shapes should remain small, generic, and benchmarkable.
