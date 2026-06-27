# Repair Agent Plugin

Status: first read-only planning slice for issue #31

## Purpose

`core.repair_agent` is a reusable first-party plugin surface for conservative world repair. The first slice plans repair candidates only. It does not write nodes, copy assets, spawn entities, or depend on private family-server content.

Repair mutation remains blocked until rollback metadata and safe-world-op execution are covered by later issues.

## API

### `core.repair_agent.configure(options)`

Configures game-specific repair targets:

```lua
core.repair_agent.configure({
	repair_nodes = {
		["fire:basic_flame"] = {
			planned_action = "remove_node",
			replacement = "air",
			family = "hazard",
		},
	},
	radius = 1,
	sample_limit = 8,
})
```

`repair_nodes` accepts:

- `true`: plan `remove_node` with replacement `air`.
- string: plan `replace_node` with that replacement node.
- table: explicit `planned_action`, `replacement`, and `family` metadata.

### `core.repair_agent.plan_area(center, options)`

Builds a read-only plan around `center`.

Important options:

- `agent_id`
- `owner`
- `task_id`
- `radius`
- `repair_nodes`
- `get_node`
- `sample_limit`
- `bounds`

The planner uses `core.ai_world_ops.inspect_area` and returns a structured action result:

- `operation = "repair_agent.plan_area"`
- `changed = 0`
- `metrics.node_writes = 0`
- `candidates`: bounded candidate repairs with position, node name, planned action, replacement, family, and reason.
- `samples`: bounded inspection samples, including protected or skipped positions.

No `set_node` hook is called by the planning path.

### `core.repair_agent.queue_plan_task(def)`

Queues a one-step planning task through `core.queue_ai_task` so larger scans have visible task status:

```lua
core.repair_agent.queue_plan_task({
	task_id = "repair-plan:example",
	agent_id = "nova_agent:player",
	owner = "player",
	center = { x = 0, y = 0, z = 0 },
	radius = 1,
})
```

The queued task uses `max_node_writes_per_step = 0` and returns the same read-only plan result as `plan_area`.

## Safety Boundary

This slice is intentionally non-mutating:

- It does not call raw node mutation APIs.
- It does not call `core.ai_world_ops.remove_node`, `replace_node`, or batch mutation APIs.
- It reports protected and skipped positions instead of bypassing them.
- It records no private prompts, assets, or world payloads by default.

Follow-on mutation work must depend on rollback metadata and safe-world-op tests.
