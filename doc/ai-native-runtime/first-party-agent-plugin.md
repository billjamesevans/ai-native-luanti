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
- `follow`, `follow me`: records follow state for the player.
- `come`, `come here`: records a target position.
- `light`, `place N lights`: queues a bounded safe-world batch placement.
- `build`, `build marker`, `marker`: queues a marker placement.
- `repair`, `fix`: queues a conservative repair step for configured repair nodes.

Unknown prompts go to the configured model adapter. The adapter boundary is explicit and testable through `core.ai_agent_plugin.set_model_adapter(fn)`.

## Configuration

Games or server mods can configure game-specific nodes without changing the engine fork:

```lua
core.ai_agent_plugin.configure({
	light_node = "default:torch",
	marker_node = "default:mese_post_light",
	repair_nodes = {
		["fire:basic_flame"] = true,
	},
	max_lights = 12,
})
```

The defaults are intentionally generic and may not match every game. A game package should set nodes appropriate to its own content.

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

Request fields include `agent_id`, `owner`, `prompt`, and `context`. The plugin records a `model.request` audit event before calling the adapter, but private prompt payloads are not retained unless the runtime audit settings are explicitly changed.

## Current Limits

- No visible entity is spawned yet.
- Follow and come commands update state only; movement/pathing is a later slice.
- Build is a single configurable marker node, not a showcase structure system.
- Repair only removes configured repair nodes at the target position.
- The model adapter is a boundary only; no default network client is bundled.

Those limits are intentional. The first milestone is proving clean runtime usage before expanding behavior.
