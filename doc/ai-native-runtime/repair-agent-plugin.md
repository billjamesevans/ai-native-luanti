# Repair Agent Plugin

Status: rollback-backed mutation slice for issue #43

## Purpose

`core.repair_agent` is a reusable first-party plugin surface for conservative world repair. Planning remains read-only by default. Mutation is available only through an explicit apply path that writes via safe world operations after rollback metadata is persisted.

The plugin does not copy assets, spawn entities, or depend on private family-server content.

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

### `core.repair_agent.apply_plan(plan, options)`

Applies a previously generated repair plan through rollback-backed safe world operations.

Required options for mutation:

- `allow_mutation = true`
- `world_id`
- `agent_id`
- `owner`
- `task_id`
- `persist_record(record)` or `persist_rollback_record(record)`
- `get_node`
- `set_node`

Useful optional fields:

- `max_node_writes`, `max_changes`, or `max_node_writes_per_step`
- `rollback_record_id`
- `rollback_policy`
- `bounds`
- `allow_hazards`
- `sample_limit`

The apply path returns:

- `operation = "repair_agent.apply_plan"`
- `changed`, `skipped`, `samples`, and `metrics.node_writes`
- `metrics.candidate_count`
- `metrics.rollback_records` or `metrics.rollback_failures`
- `rollback_record_id` and `rollback_storage_ref` after successful rollback persistence

If `allow_mutation` is not true, the result is blocked with `reason = "repair_mutation_not_enabled"` and `changed = 0`. If rollback metadata cannot be persisted, the result is blocked with `reason = "rollback_metadata_unavailable"` before node writes run.

### `core.repair_agent.queue_apply_task(def)`

Queues a one-step repair apply task:

```lua
core.repair_agent.queue_apply_task({
	task_id = "repair-apply:example",
	agent_id = "nova_agent:player",
	owner = "player",
	world_id = "test-world",
	plan = repair_plan,
	allow_mutation = true,
	max_node_writes_per_step = 4,
	persist_record = function(record)
		return "rollback-store:" .. record.record_id
	end,
})
```

The task budget uses `max_steps_per_step = 1` and the configured node-write cap. The queued step stops as blocked if mutation is not explicitly enabled, the agent lacks write capability, rollback metadata cannot be persisted, or safe world operations skip every candidate.

## Safety Boundary

Planning remains intentionally non-mutating:

- It does not call raw node mutation APIs.
- It does not call `core.ai_world_ops.remove_node`, `replace_node`, or batch mutation APIs.
- It reports protected and skipped positions instead of bypassing them.
- It records no private prompts, assets, or world payloads by default.

Mutation is intentionally narrow:

- It requires `allow_mutation = true`.
- It requires the agent to have `world.place`.
- It persists rollback metadata before invoking a mutation callback.
- It writes only through `core.ai_world_ops.remove_node` or `core.ai_world_ops.replace_node`.
- It enforces the configured node-write cap.
- It preserves protected-area and safety skips from safe world operations.

Broader repair behavior, rollback restore operations, and benchmark scenarios remain follow-on work.
