# Agent Task Queue API

Status: first implementation slice for issue #3

## Purpose

The task queue lets plugins run long AI-agent work in bounded server-step slices. It is the runtime path for future build, repair, import, and patrol jobs. Direct world mutation APIs should use this queue when work may span many nodes, entities, or server ticks.

## API

### `core.queue_ai_task(def)`

Queues a task and returns a defensive public copy.

Required fields:

- `task_id`: stable non-empty string.
- `agent_id`: registered AI agent id.
- `owner`: player, server, or automation identity that owns the task.
- `label`: player/admin-visible task label.
- `steps`: non-empty array of step functions.

Optional fields:

- `budget.max_steps_per_step`: maximum task step functions to run in one `core.step_ai_tasks()` call. Defaults to `1`.
- `budget.max_node_writes_per_step`: maximum node writes a step may report through `last_result.changed`. Defaults to `0`, which means not enforced yet.

The queued task starts with status `queued`, progress `{ current = 0, total = #steps }`, and an empty `last_result`.

### `core.get_ai_task(task_id)`

Returns a defensive public copy of a task, or `nil` when the task is unknown. The returned table does not expose executable step functions.

### `core.step_ai_tasks()`

Runs bounded task work and returns a summary:

- `ran`: number of step functions executed.
- `remaining`: active queued/running/paused task count.
- `paused`: whether the queue is paused.
- `reason`: pause reason when paused.

Current behavior runs the first queued/running task in queue order. Each call respects that task's `max_steps_per_step` budget.

Step functions receive a context table:

- `task_id`
- `agent_id`
- `owner`
- `budget`
- `progress`

Step functions should return an action-result-like table. The task stores it as `last_result`. If the result status is `blocked`, `unsafe`, or `failed`, the task stops with that status. If the reported `changed` count exceeds `budget.max_node_writes_per_step`, the task stops as `unsafe` with reason `node_write_budget_exceeded`.

### `core.cancel_ai_task(task_id, actor)`

Cancels a queued or running task. Cancellation is allowed when:

- `actor` is the task owner.
- `actor` is the literal server-admin fallback `"admin"`.
- `actor` is a registered AI agent with `admin.override`.

The function returns a structured task result with status `cancelled`, `permission_denied`, `not_found`, or `completed`.

### `core.set_ai_task_queue_paused(paused, reason)`

Sets a global queue pause hook. This is the first placeholder for lag-based pausing. When paused, active tasks are marked `paused` and `core.step_ai_tasks()` runs no task steps. Clearing the pause returns paused tasks to `queued` or `running` based on progress.

## Task Statuses

Implemented statuses:

- `queued`
- `running`
- `paused`
- `completed`
- `cancelled`
- `failed`
- `blocked`
- `unsafe`

## Current Limits

This first slice is intentionally small:

- Queue state is in-memory only.
- It does not yet persist tasks across server restart.
- It does not yet wire into automatic globalstep scheduling.
- It does not yet perform actual protected-node checks or world writes.
- It enforces node-write budgets only when step results report `changed`.

Those limits are deliberate. Safe world operations and metrics are tracked by later MVP issues.

