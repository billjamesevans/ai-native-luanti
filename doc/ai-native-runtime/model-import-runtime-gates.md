# Model And Import Runtime Gates

Status: first implementation slice for issue #98

## Purpose

The runtime exposes first-class gates for the MVP capabilities that touch external model adapters and compatibility import planning:

- `http.llm`
- `import.assets`

These gates are intentionally narrow. They prove capability enforcement, queued-task behavior, structured action results, and audit records without bundling a network provider, copying assets, or applying compatibility imports.

## Model Requests

`core.ai_model_ops.request(prompt, options)` calls an injected model adapter only after the agent passes the `http.llm` capability check.

Required options:

- `agent_id`
- `owner`
- `adapter`

Optional options:

- `task_id`
- `context`
- `private_prompt`
- `adapter_name`

The operation records a `model.request` audit event before the adapter call and records adapter outcome through the existing `model.adapter` metric/audit path. Private prompt payloads are not retained unless runtime audit options explicitly enable private payload retention.

When the agent lacks `http.llm`, the operation returns a structured blocked result with `reason = "missing_capability"`. When no adapter is configured, it returns `model_adapter_unavailable`.

## Import Planning

`core.ai_import_ops.plan(plan, options)` records an operator-supplied dry-run compatibility plan only after the agent passes the `import.assets` capability check.

Required options:

- `agent_id`
- `owner`

Required plan fields:

- `dry_run = true`
- `planned_actions`

Each planned action must include `import.assets` in `required_capabilities`. The runtime rejects asset payloads, private payloads, copied-asset flags, and non-dry-run plans. This keeps the compatibility/import milestone deferred while still giving future import tooling a safe runtime handoff point.

## Task Queue Behavior

Both operations are designed for queued runtime steps:

- Missing `http.llm` or `import.assets` returns `status = "blocked"`.
- `core.step_ai_tasks()` promotes that blocked action result to a blocked task.
- Successful model requests and import plans complete normally.

## Non-Goals

- No default model provider.
- No provider API keys or provider prompts.
- No copied assets.
- No private worlds or private player data.
- No compatibility apply phase.
- No proprietary Minecraft behavior.
