# Agent Capability Profiles

Status: alpha policy contract for issue #111

## Purpose

Capability profiles keep first-party agent grants owned by server profiles and plugins instead of hard-coding privileged behavior into the engine fork. The runtime still enforces individual capabilities, budgets, audit records, and rollback requirements; profiles decide which grants an agent receives in a specific context.

The default `core.ai_agent_plugin` policy is empty. A game, operator mod, or optional plugin must call `core.ai_agent_plugin.configure` with a named `capability_profile` and an explicit `capabilities` table before newly registered player agents receive grants.

## Clean Profile

The clean profile is the public-safe default for `games/ai_runtime`. It is for disposable local worlds, low-power benchmark runs, and first-party agent behavior that should be safe to exercise before compatibility/import work expands.

Configuration anchor:

```lua
core.ai_agent_plugin.configure({
	capability_profile = "clean",
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

Allowed by default:

- `world.read`
- `world.place`
- `world.remove`
- `entity.spawn`
- `entity.control`
- `task.cancel`
- `http.llm`

Excluded by default:

- `admin.override`
- `import.assets`
- `player.teleport.other`
- `combat.defend`
- family-plugin grants

Clean profile agents may call a configured model adapter through `http.llm`, but runtime audit records must not retain private prompts or response payloads unless an operator-only profile explicitly changes audit policy. The first-party provider adapter is the Agents SDK sidecar; its web search and function tools are sidecar-owned powers that still return through the same provider-neutral response envelope. They do not grant direct world mutation, import promotion, rollback execution, shell access, or file access inside the Luanti process.

## Operator Profile

The operator profile is for trusted local administration and compatibility-apply work. It is never selected by default and requires explicit opt-in through a server-owned profile or operator mod.

Configuration anchor:

```lua
core.ai_agent_plugin.configure({
	capability_profile = "operator",
	capabilities = {
		["admin.override"] = true,
	},
})
```

Operator-only capabilities include:

- `admin.override`
- `player.teleport.other`
- `import.assets`
- `rollback.execute`

Rules:

- `admin.override` must require explicit opt-in.
- `admin.override` checks must return `audit_required = true`.
- The runtime must record a `capability.admin_override` audit event for successful override checks.
- Operator imports and rollback execution still need public-safe inventory, explicit approval, rollback policy, and write budgets.
- Operator profiles must not become the default clean profile.

## Family-Plugin Profile

The family-plugin profile is for optional local or private plugins that consume the runtime without becoming part of the core engine fork. It can adapt private server behavior into reusable plugin surfaces, but the core fork should only receive generic runtime primitives.

Allowed location:

- Optional plugin or modpack outside the core engine fork.
- Local deployment configuration.
- Public-safe extraction docs that describe boundaries without copying private world content.

Not allowed in the core fork:

- Fixed private-world coordinates.
- Showcase builders or local landmarks.
- Provider prompts, secrets, or private assets.
- Unreviewed grants that bypass clean/operator profile policy.

Family-plugin grants must be explicit, documented by the plugin that owns them, and audited when they perform privileged actions. Generic capabilities that prove broadly useful should be proposed as runtime API work only after they have tests, benchmark coverage, and a public-safe example.

## Review Checklist

- New first-party agent grants are added to a named profile, not to engine defaults.
- Clean profile tests prove privileged grants are absent.
- Operator-only grants require explicit profile opt-in and audit coverage.
- Optional family/plugin grants stay outside the core engine fork.
- Benchmark and smoke runs use `capability_profile = "clean"` unless the test is specifically about operator behavior.
