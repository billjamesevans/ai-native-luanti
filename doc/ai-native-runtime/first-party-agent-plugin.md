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
- `core.ai_player_ops.defend` for bounded defensive actions when a profile grants `combat.defend`.
- `core.ai_world_ops` indirectly through build and repair task surfaces.
- `core.ai_entity_ops` for spawning and moving the player's bounded helper entity.
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
- `guide`, `help`: returns the available builder, repair, guide, and defender surfaces plus current task records.
- `tasks`, `task status`, `builder`: returns known plugin task records.
- `cancel`, `stop`: cancels queued/running/paused player-owned plugin tasks.
- `follow`, `follow me`: queues bounded movement for the player's helper entity to the current player position.
- `come`, `come here`: queues bounded movement for the player's helper entity to the requested target position.
- `light`, `place N lights`: queues a rollback-backed `build_agent` lights task.
- `build plan`, `preview build`: returns a read-only marker build plan before mutation.
- `build`, `build marker`, `marker`: queues a rollback-backed `build_agent` marker task.
- `repair plan`, `preview repair`: returns a read-only repair plan before mutation.
- `repair`, `fix`: queues a rollback-backed `repair_agent` apply task for configured repair nodes.
- `defend`: queues a bounded defensive player task through `core.ai_player_ops.defend`.
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

`capability_profile` is a short policy label such as `clean` or `operator`. It is copied into the registered agent limits for audit/debug visibility.

`capabilities` is the first-party grant policy for newly registered player agents. Clean profiles should declare it explicitly and should not include privileged capabilities such as `admin.override`, compatibility/import grants such as `import.assets`, or other-player controls unless that server profile is intentionally operator-only.

`combat.defend` is intentionally absent from the clean `ai_runtime` profile. A server profile or plugin must opt into it before the `defend` command can complete successfully.

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

- Follow and come use queued bounded entity movement. Full pathfinding and continuous follow ticks are later slices.
- Build remains small lights and marker tasks, not a showcase structure system.
- Repair only applies configured repair rules around the requested target position.
- Build and repair previews explain bounded plans, but approval workflow and richer plan editing remain later slices.
- Audit and rollback review return compact sanitized records, not full private payloads or rollback contents.
- Defender behavior needs a profile grant and a hostile discovery/attack path from the hosting game or plugin.
- The model adapter is a boundary only; no default network client is bundled.

Those limits are intentional. The first milestone is proving clean runtime usage before expanding behavior.
