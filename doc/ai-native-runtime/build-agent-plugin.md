# Build Agent Plugin

Status: task-definition slice for issue #32

## Purpose

`core.build_agent` defines small reusable build tasks that can be queued through the AI task runtime and executed through `core.ai_world_ops`. The definition path does not queue work, write nodes, copy assets, or depend on private family-server builds.

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
- injected `get_node` and `set_node` hooks for tests

The returned definition includes:

- `task_id`, `agent_id`, `owner`, and `label`
- `required_capabilities.world.place = true`
- `mutation_class = "build"`
- `metadata.kind`
- `metadata.placement_count`
- `budget.max_steps_per_step = 1`
- `budget.max_node_writes_per_step`
- one task step that calls `core.ai_world_ops.batch_place`

## Safety Boundary

`define_task` is inert. It prepares a queueable definition but does not queue or execute it.

The queued step uses `core.ai_world_ops.batch_place` instead of raw node mutation APIs. Larger or destructive build work should remain out of this plugin until rollback metadata and benchmark coverage are mature enough for broader mutation scenarios.

## Private Content Boundary

This plugin must not include private showcase builds, fixed family world locations, protected names, copied assets, or one-off local commands. Game-specific packages can configure node names, but build shapes should remain small, generic, and benchmarkable.
