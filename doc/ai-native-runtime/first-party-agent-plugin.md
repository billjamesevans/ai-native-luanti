# First-Party Agent Plugin

Status: first implementation slice for issue #7

## Purpose

`core.ai_agent_plugin` is the first clean Nova-successor plugin surface in the fork. It proves that a player-owned AI agent can use the AI-native runtime APIs without importing private family-server content, one-off coordinates, showcase builders, or direct raw world writes.

The plugin is deliberately small. It is a runtime client, not a replacement for the runtime itself.

## Runtime Boundaries

The plugin uses:

- `core.register_ai_agent` for one agent per player.
- `core.queue_ai_task` for all task-backed work.
- `core.cancel_ai_task` for player-owned cancellation.
- `core.build_agent.plan` and `core.build_agent.define_task` for read-only build previews and rollback-backed light/marker build tasks.
- `core.repair_agent.queue_apply_task` for rollback-backed repair apply tasks.
- `core.ai_import_ops.plan` for dry-run-only Importer planning tasks that
  require `import.assets` and never copy assets or mutate worlds.
- `core.ai_player_ops.defend` for bounded defensive actions when a profile grants `combat.defend`.
- `core.ai_world_ops` indirectly through build and repair task surfaces.
- `core.ai_entity_ops` for spawning and moving the player's bounded helper entity during one-shot and continuous follow tasks.
- `core.record_ai_runtime_audit` for model-adapter requests without retaining private prompts.
- `core.get_ai_runtime_metrics`, `core.get_ai_task`, and `core.get_ai_runtime_audit` for status, task, audit, and rollback-review views.

The plugin does not call raw `core.set_node`, `core.remove_node`, `core.bulk_set_node`, or hard-coded showcase builders.

## Public Commands

The plugin registers three aliases:

- `/bot <message>`
- `/nova <message>`
- `/aibot <message>`

Implemented deterministic commands:

- `status`: returns current state and runtime metrics.
- `guide`, `help`: returns the available builder, repair, guide, defender, and `importer` surfaces plus current task records.
- `tasks`, `task status`, `builder`: returns known plugin task records.
- `cancel`, `stop`: cancels queued/running/paused player-owned plugin tasks.
- `approve`, `approve build`, `approve repair`: queues the latest pending
  build or repair plan after the player has seen the preview.
- `follow`, `follow me`, `follow N`: queues bounded continuous follow steps for the player's helper entity. Each task runs a finite number of server-step slices, recalculates the player's current position per slice, and moves through `core.ai_entity_ops.move` with per-step and total-distance budgets.
- `come`, `come here`: queues bounded movement for the player's helper entity to the requested target position.
- `light`, `place N lights`: queues a rollback-backed `build_agent` lights task.
- `build plan`, `preview build`: returns a read-only marker build plan before mutation.
- `build`, `build marker`, `marker`: creates a pending read-only marker build
  plan; `approve` queues the rollback-backed `build_agent` marker task.
- `repair plan`, `preview repair`: returns a read-only repair plan before mutation.
- `repair`, `fix`: creates a pending read-only repair plan for configured
  repair nodes; `approve` queues the rollback-backed `repair_agent` apply task.
- `defend`: queues a bounded defensive player task through `core.ai_player_ops.defend`.
- `import plan`, `import preview`, `import inventory`: queues a dry-run-only
  Importer task through `core.ai_import_ops.plan`. The task records an
  operator-supplied compatibility plan behind the `import.assets` gate, copies
  no assets, performs no world mutation, and is intended as the agent-facing
  handoff to the compatibility inventory work.
- `audit`, `history`: returns recent sanitized audit events for the player-owned agent.
- `rollback`, `rollback review`: returns recent rollback audit summaries for the player-owned agent.

Unknown prompts go to the configured model adapter. The adapter boundary is explicit and testable through `core.ai_agent_plugin.set_model_adapter(fn)`.

## Configuration

Games or server mods can configure game-specific nodes without changing the engine fork:

```lua
core.ai_agent_plugin.configure({
	capability_profile = "clean",
	light_node = "default:torch",
	marker_node = "default:mese_post_light",
	agent_entity_name = "ai_demo_benchmark:helper",
	repair_nodes = {
		["fire:basic_flame"] = true,
	},
	max_lights = 12,
	max_entity_move_distance = 16,
	max_follow_steps = 6,
	max_follow_step_distance = 4,
	max_follow_total_distance = 24,
	max_follow_stop_distance = 1,
	max_follow_wall_time_ms = 250,
	max_defend_distance = 8,
	capabilities = {
		["world.read"] = true,
		["world.place"] = true,
		["world.remove"] = true,
		["entity.spawn"] = true,
		["entity.control"] = true,
		["task.cancel"] = true,
		["http.llm"] = true,
	},
})
```

The default capability policy is empty. A game package or operator mod must declare a named `capability_profile` and explicit `capabilities` table before newly registered player agents receive grants.

The default node/entity settings are intentionally generic and may not match every game. A game package should set nodes appropriate to its own content.

`agent_entity_name` is the registered entity type used for queued bounded entity movement. The default uses the public demo helper fixture; a game package can configure a different registered entity without changing the engine fork.

`max_follow_steps`, `max_follow_step_distance`, `max_follow_total_distance`, `max_follow_stop_distance`, and `max_follow_wall_time_ms` bound continuous follow. A follow task is still a normal player-owned AI task, so the player can cancel it with `cancel`/`stop`, and the task result exposes `ai_agent.follow_step` status, movement result, distance moved, skipped or blocked reasons, and path metrics.

Follow can use an operator-supplied `find_path(current_pos, target_pos, options)` callback or an explicit `use_core_pathfinder` context flag. The plugin accepts only positional waypoints from the callback and still moves at most one bounded step per queued task slice. If pathfinding is unavailable, invalid, or blocked, follow falls back to the existing direct-line bounded step. Result metrics expose `pathfinder_used`, `path_waypoint_count`, and `path_status` so playtests can distinguish direct movement from waypointed movement without retaining private map data.

`capability_profile` is a short policy label such as `clean` or `operator`. It is copied into the registered agent limits for audit/debug visibility.

`capabilities` is the first-party grant policy for newly registered player agents. Clean profiles should declare it explicitly and should not include privileged capabilities such as `admin.override`, compatibility/import grants such as `import.assets`, or other-player controls unless that server profile is intentionally operator-only.

`combat.defend` is intentionally absent from the clean `ai_runtime` profile. A server profile or plugin must opt into it before the `defend` command can complete successfully.

`import.assets` is also absent from the clean `ai_runtime` profile. Operator
profiles can opt into it for dry-run-only Importer planning. Importer execution
is still plan-only in this first-party loop; structure apply, import promotion,
asset copying, and world mutation remain outside this command and belong to the
compatibility/import pipeline.

## Model Adapter

The model adapter receives a small request table:

```lua
core.ai_agent_plugin.set_model_adapter(function(request)
	return {
		ok = true,
		message = "response text",
	}
end)
```

Request fields include `agent_id`, `owner`, `prompt`, and `context`. The plugin calls model adapters through `core.ai_model_ops.request`, so the agent must have `http.llm`. The runtime records a `model.request` audit event before calling the adapter, but private prompt payloads are not retained unless the runtime audit settings are explicitly changed.

## Current Limits

- Follow uses a small bounded waypoint slice: each queued task step recomputes the player target, optionally asks a pathfinder for waypoints, moves no more than the configured step distance, stops inside the configured follow distance, and blocks when the total movement budget would be exceeded. Richer obstacle-aware navigation remains opt-in so default clean-profile playtests stay deterministic.
- Come remains a one-shot bounded helper-entity move.
- Build remains small lights and marker tasks, not a showcase structure system.
- Repair only applies configured repair rules around the requested target position.
- Build and repair commands now create pending previews first; explicit
  approval queues the mutation. Richer plan editing remains a later slice.
- Audit and rollback review return compact sanitized records, not full private payloads or rollback contents.
- Defender behavior needs a profile grant and a hostile discovery/attack path from the hosting game or plugin.
- Importer behavior is dry-run-only and depends on an operator-supplied plan;
  public-safe inventory discovery and richer compatibility reports remain the
  next compatibility slice.
- The model adapter is a boundary only; no default network client is bundled.

Those limits are intentional. The first milestone is proving clean runtime usage before expanding behavior.
