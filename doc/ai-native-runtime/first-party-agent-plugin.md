# First-Party Agent Plugin

Status: first implementation slice for issue #7

## Purpose

`core.ai_agent_plugin` is the first clean Nova-successor plugin surface in the fork. It proves that a player-owned AI agent can use the AI-native runtime APIs without importing private family-server content, one-off coordinates, showcase builders, or direct raw world writes.

The plugin is deliberately small. It is a runtime client, not a replacement for the runtime itself.

## Runtime Boundaries

The plugin uses:

- `core.register_ai_agent` for one agent per player.
- `core.queue_ai_task` for all world-changing work.
- `core.cancel_ai_task` for player-owned cancellation.
- `core.ai_world_ops` for node inspection, placement, removal, repair, and batch light placement.
- `core.ai_entity_ops` for spawning and moving the player's bounded helper entity.
- `core.record_ai_runtime_audit` for model-adapter requests without retaining private prompts.
- `core.get_ai_runtime_metrics` and `core.get_ai_task` for status and task views.

The plugin does not call raw `core.set_node`, `core.remove_node`, `core.bulk_set_node`, or hard-coded showcase builders.

## Public Commands

The plugin registers three aliases:

- `/bot <message>`
- `/nova <message>`
- `/aibot <message>`

Implemented deterministic commands:

- `status`: returns current state and runtime metrics.
- `tasks`, `task status`, `builder`: returns known plugin task records.
- `cancel`, `stop`: cancels queued/running/paused player-owned plugin tasks.
- `follow`, `follow me`: queues bounded movement for the player's helper entity to the current player position.
- `come`, `come here`: queues bounded movement for the player's helper entity to the requested target position.
- `light`, `place N lights`: queues a bounded safe-world batch placement.
- `build`, `build marker`, `marker`: queues a marker placement.
- `repair`, `fix`: queues a conservative repair step for configured repair nodes.

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
- Build is a single configurable marker node, not a showcase structure system.
- Repair only removes configured repair nodes at the target position.
- The model adapter is a boundary only; no default network client is bundled.

Those limits are intentional. The first milestone is proving clean runtime usage before expanding behavior.
