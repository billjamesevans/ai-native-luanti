# Agent Identity and Capability API

Status: first implementation slice for issue #2

## Purpose

The agent API gives plugins a small, explicit contract for registering AI-controlled world actors and checking whether they can perform a requested action. It is intentionally smaller than the full task/runtime system. Task queues, safe world writes, metrics, and audit storage build on top of this API.

## API

### `core.register_ai_agent(def)`

Registers or replaces an AI agent and returns a defensive copy of the normalized agent record.

Required fields:

- `agent_id`: stable non-empty string.
- `display_name`: player-visible non-empty string.
- `owner`: responsible player, server, or automation identity.
- `plugin`: plugin or mod that owns the agent.

Optional fields:

- `capabilities`: table keyed by capability name with truthy values for grants.
- `limits`: table of runtime limits. The first slice stores this as metadata; later task/world APIs enforce specific limits.
- `state`: `enabled` by default. Non-enabled states block capability checks.

### `core.get_ai_agent(agent_id)`

Returns a defensive copy of a registered agent, or `nil` when the agent is unknown.

### `core.agent_has_capability(agent_id, capability)`

Returns `true` only when the agent is registered and the named capability is granted.

### `core.check_agent_capability(agent_id, capability)`

Returns a structured action result for capability checks.

Result fields:

- `ok`: boolean.
- `status`: `success`, `permission_denied`, `not_found`, or `blocked`.
- `operation`: always `capability.check`.
- `agent_id`: checked agent id.
- `capability`: checked capability.
- `reason`: machine-readable reason.
- `message`: short human-readable explanation.
- `audit_required`: true when `admin.override` is granted.

## Current Reasons

- `capability_granted`: the agent is enabled and has the capability.
- `admin_override_granted`: the agent is enabled, has `admin.override`, and the action must be audited.
- `missing_capability`: the agent is enabled but lacks the capability.
- `unknown_agent`: no agent exists for the supplied id.
- `agent_disabled`, `agent_paused`, or another `agent_<state>` reason: the agent exists but is not enabled.

## Initial Capability Names

The runtime accepts arbitrary capability strings so first-party plugins can evolve without a hard-coded registry. The MVP vocabulary is:

- `world.read`
- `world.place`
- `world.dig`
- `world.batch`
- `entity.spawn`
- `entity.control`
- `player.teleport.self`
- `player.teleport.other`
- `combat.defend`
- `http.llm`
- `import.assets`
- `admin.override`

