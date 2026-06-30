# First-Party Agent Plugin

Status: first implementation slice for issue #7

## Purpose

`core.ai_agent_plugin` is the first clean Nova-successor plugin surface in the fork. It proves that a player-owned AI agent can use the AI-native runtime APIs without importing private family-server content, one-off coordinates, showcase builders, or direct raw world writes.

The plugin is deliberately small. It is a runtime client, not a replacement for the runtime itself.

## Product Surfaces

The plugin keeps the `/nova` chat entrypoint stable, but product behavior is
split into five first-party role agents:

| Surface | Agent id shape | Clean profile boundary | Runtime path |
| --- | --- | --- | --- |
| Builder Agent | `nova_agent:<player>:builder` | Granted only `world.read`, `world.place`, and optional `task.cancel` when the clean profile declares them. Build and light mutations require preview, explicit approval for marker/platform/fire/wall builds, and rollback metadata before writes. | `core.build_agent.plan`, `core.build_agent.define_task` |
| Repair Agent | `nova_agent:<player>:repair` | Granted only `world.read`, `world.place`, and optional `task.cancel` when the clean profile declares them. Repair mutation requires preview, explicit approval, and rollback metadata before writes. | `core.repair_agent.plan_area`, `core.repair_agent.queue_apply_task` |
| Guide Agent | `nova_agent:<player>:guide` | Granted `world.read` plus optional `task.cancel` and `http.llm` when configured. It owns read-only guide, task, audit, rollback-review, and owner task-control views. | `core.get_ai_task`, `core.get_ai_runtime_audit`, `core.cancel_ai_task` |
| Defender Agent | `nova_agent:<player>:defender` | Not granted in the default clean profile. A server profile or optional plugin must explicitly grant `combat.defend`. | `core.ai_player_ops.defend` |
| Importer Agent | `nova_agent:<player>:importer` | Not granted in the default clean profile. A server profile or optional plugin must explicitly grant `import.assets`. The current surface is dry-run-only. | `core.ai_import_ops.plan` |

`core.ai_agent_plugin.ensure_product_agents(player_name)` registers those role
agents for a player, and `core.ai_agent_plugin.get_product_surfaces(player_name)`
returns a public-safe catalog with each surface's capability profile, required
capabilities, granted capabilities, default clean-profile grant boundary,
commands, runtime entrypoints, and mutation policy.

The legacy `nova_agent:<player>` identity remains for compatibility and for
generic status, follow/come helper movement, and model-adapter fallback. New
product work should prefer the role agents above so benchmark and operator
evidence can distinguish builder, repair, guide, defender, and importer
behavior.

## Runtime Boundaries

The plugin uses:

- `core.register_ai_agent` for one agent per player.
- `core.queue_ai_task` for all task-backed work.
- `core.cancel_ai_task` for player-owned cancellation.
- `core.build_agent.plan` and `core.build_agent.define_task` for read-only build previews and rollback-backed light, marker, fire, wall, and bounded platform build tasks.
- `core.repair_agent.queue_apply_task` for rollback-backed repair apply tasks.
- `core.ai_import_ops.plan` for dry-run-only Importer planning tasks that
  require `import.assets` and never copy assets or mutate worlds.
- `core.ai_player_ops.defend` for bounded defensive actions when a profile grants `combat.defend`.
- `core.ai_world_ops` indirectly through build and repair task surfaces.
- `core.ai_entity_ops` for spawning and moving the player's bounded helper entity during one-shot and continuous follow tasks.
- `core.ai_model_ops.request` and `core.ai_model_ops.request_async` for
  model-adapter requests without retaining private prompts.
- `core.record_ai_runtime_audit` for model-adapter request/result events.
- `core.get_ai_runtime_metrics`, `core.get_ai_task`, and `core.get_ai_runtime_audit` for status, task, audit, and rollback-review views.

The plugin does not call raw `core.set_node`, `core.remove_node`, `core.bulk_set_node`, or hard-coded showcase builders.

## Public Commands

The plugin registers three aliases:

- `/bot <message>`
- `/nova <message>`
- `/aibot <message>`

The plugin also registers `/ai_agent_eval` for operators with `server`
privilege. It runs a bounded public-safe prompt evaluation covering `build a
fire`, `build a wall of tnt`, and an unknown prompt routed through the
configured model adapter. The report is JSON, is logged with the prompt trace
ids and model-adapter metric deltas, requires approval for build plans instead
of mutating the world, and discards those approvals after recording the result.
Use `/ai_agent_eval case=fire`, `/ai_agent_eval case=tnt`, `/ai_agent_eval
case=model`, or `/ai_agent_eval model <prompt>` for narrower checks.

Implemented deterministic commands:

- `status`: returns current state, runtime metrics, product-surface readiness,
  known player task summaries, and any pending approval id.
- `guide`, `help`, `commands`: returns the available builder, repair, guide, defender, and `importer` surfaces plus current task records.
- `tasks`, `task status`, `builder`: returns known plugin task records.
- `task <task_id>`, `task status <task_id>`: returns one remembered
  player-owned plugin task by id without exposing unrelated runtime tasks.
- `traces`, `logs`, `model traces`, `request traces`: returns recent
  public-safe Nova request/response traces, including visible prompt, route,
  selected build intent/material, response status, and bounded response
  message. Private prompts and raw provider payloads are not retained.
- `pending`, `pending plan`, `plan`, `review plan`: returns the current
  player-owned pending build or repair approval without queuing mutation.
- `edit plan platform width N depth N`, `plan edit platform width N depth N`:
  updates the current pending build approval with a new bounded platform preview
  while keeping the same approval id and without mutating the world.
- `edit plan radius N`, `plan edit radius N`: updates the current pending
  repair approval with a new bounded repair-radius preview while keeping the
  same approval id and without mutating the world.
- `cancel`, `stop`: cancels queued/running/paused player-owned plugin tasks.
- `cancel <task_id>`, `stop <task_id>`: cancels one remembered player-owned
  plugin task and reports before/after status.
- `stay`, `wait`: stops the player's helper movement by cancelling only
  queued/running/paused follow or come tasks, preserving the helper entity id,
  and setting the player-visible helper mode to `stay`. This is guide-owned
  task control, not a broad task cancel, rollback command, import apply path,
  or direct world mutation.
- `discard`, `discard plan`, `cancel plan`, `cancel approval`, `reject`,
  `deny`, `no`, `discard <approval_id>`:
  clears the current pending approval before mutation. Targeted discard tokens
  must match the pending action or approval id.
- `approve`, `approve build`, `approve repair`, `approve <approval_id>`:
  queues the latest pending build or repair plan after the player has seen the
  preview. Approval ids are emitted by the preview/chat response so players can
  approve the exact pending plan they reviewed.
- `follow`, `follow me`, `follow N`: queues bounded continuous follow steps for the player's helper entity. Each task runs a finite number of server-step slices, recalculates the player's current position per slice, and moves through `core.ai_entity_ops.move` with per-step and total-distance budgets.
- `come`, `come here`: queues bounded movement for the player's helper entity to the requested target position.
- `light`, `place N lights`: queues a rollback-backed `build_agent` lights task.
- `build plan`, `preview build`: returns a read-only marker build plan before mutation.
- `build`, `build marker`, `marker`: creates a pending read-only marker build
  plan; `approve` queues the rollback-backed `build_agent` marker task.
- `build plan platform width N depth N`, `build platform width N depth N`:
  plans a bounded platform before approval. `width * depth` must fit within
  the configured build write budget, and the apply path remains rollback-backed.
- `build fire`, `build a fire`: plans a bounded fire placement using the
  configured or registered game fire node.
- `build wall width N height N`, `build a wall of tnt`: plans a bounded wall
  before approval. Requested game materials such as TNT are allowed when the
  node exists and the request fits the server's capability, protection,
  budget, approval, and rollback gates.
- `repair plan`, `preview repair`: returns a read-only repair plan before mutation.
- `repair plan radius N`, `repair radius N`: plans a bounded wider repair
  area before approval. `N` must be within the configured `max_repair_radius`
  and the plan remains rollback-backed and approval-gated.
- `repair`, `fix`: creates a pending read-only repair plan for configured
  repair nodes; `approve` queues the rollback-backed `repair_agent` apply task.
- `defend`: queues a bounded defensive player task through `core.ai_player_ops.defend`.
- `import plan`, `import preview`, `import inventory`: queues a dry-run-only
  Importer task through `core.ai_import_ops.plan`. The task records an
  operator-supplied compatibility plan behind the `import.assets` gate, copies
  no assets, performs no world mutation, and is intended as the agent-facing
  handoff to the compatibility inventory work.
- `audit`, `history`: returns recent sanitized audit events for the player-owned agent.
- `audit <task_id>`, `history <task_id>`: returns sanitized audit events for
  one remembered player-owned plugin task without exposing unrelated runtime
  tasks.
- `rollback`, `rollback review`: returns recent rollback audit summaries for the player-owned agent.
- `rollback <task_id>`, `rollback review <task_id>`, `rollback <rollback_id>`:
  returns rollback audit summaries for one remembered player-owned task or one
  player-owned rollback record id. The command is review-only and never executes
  rollback.

The chat response includes the action status plus the concrete public-safe
details a player needs to keep using the loop: product-surface readiness,
available commands, task ids, approval ids, pending actions, known task counts,
planned write or candidate counts, cancellation counts, audit counts, rollback
counts, and gated surface reasons. The structured Lua result remains available to tests and
operator tooling, but the registered chat command must not hide those details
behind a generic success string.

Targeted task, audit, rollback-review, and approval commands are deliberately
scoped to remembered player-owned plugin tasks, player-owned rollback audit
records, and the current player's pending approval. They do not provide a
general runtime task browser, do not expose unrelated operators or players, do
not execute rollback, do not bypass `core.cancel_ai_task` owner checks, and do
not approve mutation without the same rollback-backed build or repair task path.
Pending-plan review and discard are read-only/player-local: they expose only the
current pending approval summary and can only clear that player's unqueued build
or repair plan before mutation. Pending-plan edit is also read-only/player-local:
it re-runs the appropriate planner, replaces the pending preview under the same
approval id, and still requires explicit approval before any rollback-backed
build or repair task is queued.

Unknown prompts go to the configured model adapter. The adapter boundary is
explicit and testable through `core.ai_agent_plugin.set_model_adapter(fn)` for
sync/offline adapters and `core.ai_agent_plugin.set_model_adapter_async(fn)` for
live adapters that should not block the server step. The first-party provider
path should be the Agents SDK bridge documented in
[`agents-sdk-model-adapter.md`](agents-sdk-model-adapter.md), so unknown
prompts can become real agent runs with hosted web search and deterministic
tools while Luanti remains the task, capability, audit, rollback, and mutation
authority.
The Lua bridge is explicit opt-in through `ai_runtime.enable_agents_sdk_adapter`
and uses `/ai_agents_sdk_adapter_probe_async` for live public-safe verification.

Nova request traces are intentionally separate from provider payload retention.
`core.ai_agent_plugin.get_request_traces({ limit = N })` and the chat-facing
`traces` command keep bounded public prompt/response summaries for debugging bad
agent behavior. They are meant to answer "why did Nova do that?" after a player
command, without storing private prompts, raw API responses, credentials, or
unbounded media data. Async model requests first record a queued trace with a
trace id, then overwrite that same trace with the final bounded model response
when the adapter callback returns.

## Configuration

Games or server mods can configure game-specific nodes without changing the engine fork:

```lua
core.ai_agent_plugin.configure({
	capability_profile = "clean",
	light_node = "default:torch",
	marker_node = "default:mese_post_light",
	platform_node = "default:stone",
	path_node = "default:stone",
	fire_node = "fire:basic_flame",
	wall_node = "default:stone",
	tnt_node = "tnt:tnt",
	build_material_nodes = {
		fire = "fire:basic_flame",
		tnt = "tnt:tnt",
	},
	agent_entity_name = "ai_runtime_base:helper",
	repair_nodes = {
		["fire:basic_flame"] = true,
	},
	max_lights = 12,
	max_request_traces = 50,
	max_entity_move_distance = 16,
	max_follow_steps = 6,
	max_follow_step_distance = 4,
	max_follow_total_distance = 24,
	max_follow_stop_distance = 1,
	max_follow_wall_time_ms = 250,
	max_repair_radius = 2,
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

The default capability policy is empty. A game package or operator mod must declare a named `capability_profile` and explicit `capabilities` table before newly registered player agents receive grants. The role agents inherit only the subset of configured capabilities relevant to their surface; for example, a clean profile with `http.llm` does not automatically grant model access to the builder, and a clean profile without `import.assets` creates an Importer Agent with no import grant.

The default node/entity settings are intentionally generic and may not match every game. A game package should set nodes appropriate to its own content. The material resolver prefers explicitly configured `build_material_nodes`, then common Luanti/MineClone names such as `mcl_tnt:tnt`, `tnt:tnt`, `mcl_fire:fire`, and `fire:basic_flame` when those nodes are registered.

The build surface does not refuse a requested in-game material because it is explosive, fiery, or otherwise game-dangerous. That policy belongs to the server's capability profile and world-write controls: registered node availability, protected-area checks, write budgets, preview approval, and rollback metadata. If a player asks for a TNT wall and the node exists within those bounds, Nova should plan the TNT wall.

`agent_entity_name` is the registered entity type used for queued bounded entity movement. The clean `games/ai_runtime` profile registers and configures the code-only `ai_runtime_base:helper` entity for normal playtesting. The `ai_demo_benchmark:helper` entity remains a benchmark fixture behind its explicit dev setting and should not be required by the default product profile.

`max_follow_steps`, `max_follow_step_distance`, `max_follow_total_distance`, `max_follow_stop_distance`, and `max_follow_wall_time_ms` bound continuous follow. A follow task is still a normal player-owned AI task, so the player can cancel it with `cancel`/`stop`, and the task result exposes `ai_agent.follow_step` status, movement result, distance moved, skipped or blocked reasons, and path metrics.

Together, `follow`, `come`, and `stay` form the clean-profile helper-control set.
Players can use `stay` or `wait` when they only want to stop helper
movement. Unlike `cancel`/`stop`, `stay` targets movement tasks only; queued
build, repair, defend, import, audit, and rollback-review work remains under
the normal task controls.

Follow can use an operator-supplied `find_path(current_pos, target_pos, options)` callback or an explicit `use_core_pathfinder` context flag. The plugin accepts only positional waypoints from the callback and still moves at most one bounded step per queued task slice. If pathfinding is unavailable, invalid, or blocked, follow falls back to the existing direct-line bounded step. Result metrics expose `pathfinder_used`, `path_waypoint_count`, and `path_status` so playtests can distinguish direct movement from waypointed movement without retaining private map data.

`capability_profile` is a short policy label such as `clean` or `operator`. It is copied into the registered agent limits for audit/debug visibility.

`capabilities` is the first-party grant policy for newly registered player agents. Clean profiles should declare it explicitly and should not include privileged capabilities such as `admin.override`, compatibility/import grants such as `import.assets`, or other-player controls unless that server profile is intentionally operator-only.

`combat.defend` is intentionally absent from the clean `ai_runtime` profile. A server profile or plugin must opt into it before the `defend` command can complete successfully.
In the clean profile, direct `defend` requests fail fast with
`surface_capability_not_granted` and report the required `combat.defend`
capability before any task is queued.

`import.assets` is also absent from the clean `ai_runtime` profile. Operator
profiles can opt into it for dry-run-only Importer planning. Importer execution
is still plan-only in this first-party loop; structure apply, import promotion,
asset copying, and world mutation remain outside this command and belong to the
compatibility/import pipeline.
In the clean profile, direct `import plan`, `import preview`, or
`import inventory` requests fail fast with `surface_capability_not_granted` and
report the required `import.assets` capability before any task is queued.

## Model Adapter

The model adapter receives the provider-neutral request envelope documented in
[Model adapter contract](model-adapter-contract.md):

```lua
core.ai_agent_plugin.set_model_adapter(function(request)
	assert(request.request_kind == "ai_native_model_adapter_request")
	return {
		schema_version = 1,
		response_kind = "ai_native_model_adapter_response",
		ok = true,
		message = "response text",
		adapter_name = "example-adapter",
	}
end)
```

Request fields include `agent_id`, `owner`, `public_prompt`, `context`,
`safety`, and `bounds`. The plugin calls model adapters through
`core.ai_model_ops.request`, so the agent must have `http.llm`. The runtime
records a `model.request` audit event before calling the adapter, but private
prompt payloads are not forwarded through the adapter request envelope and are
not retained unless the runtime audit settings are explicitly changed. Adapter
responses that include raw provider payloads, credentials, headers, private
payloads, or raw asset payloads are blocked with `adapter_payload_rejected`.

## Current Limits

- Follow uses a small bounded waypoint slice: each queued task step recomputes the player target, optionally asks a pathfinder for waypoints, moves no more than the configured step distance, stops inside the configured follow distance, and blocks when the total movement budget would be exceeded. Richer obstacle-aware navigation remains opt-in so default clean-profile playtests stay deterministic.
- Come remains a one-shot bounded helper-entity move.
- Build remains small lights, marker tasks, and bounded platforms, not a
  showcase structure system.
- Repair only applies configured repair rules around the requested target position.
- Build and repair commands now create pending previews first; players can
  review, edit, or discard the current pending plan, and explicit approval
  queues the mutation. Platform width/depth and repair radius are player-editable
  within configured bounds; broader build-shape editing remains a later slice.
- Audit and rollback review return compact sanitized records, not full private
  payloads or rollback contents. Targeted rollback review is still read-only:
  rollback execution remains outside the first-party player command surface.
- Defender behavior needs a profile grant and a hostile discovery/attack path from the hosting game or plugin.
- Importer behavior is dry-run-only and depends on an operator-supplied plan;
  public-safe inventory discovery and richer compatibility reports remain the
  next compatibility slice.
- The model adapter is a boundary only; no default network client is bundled.

Those limits are intentional. The first milestone is proving clean runtime usage before expanding behavior.
