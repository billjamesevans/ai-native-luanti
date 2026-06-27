# Runtime Metrics and Audit API

Status: first implementation slice for issue #5

## Purpose

The runtime metrics and audit API makes AI-agent work observable before a full dashboard or Prometheus bridge exists. It gives server operators a local snapshot of queue, task, write, skip, unsafe, pending-request, and entity counters, plus bounded audit records for important runtime events.

The first implementation is Lua-level and intentionally avoids retaining private prompts or model payloads by default.

## Metrics Snapshot

`core.get_ai_runtime_metrics()` returns a table with counters and gauges:

- `tasks_queued`
- `tasks_completed`
- `tasks_cancelled`
- `tasks_failed`
- `tasks_blocked`
- `tasks_unsafe`
- `task_steps_run`
- `queue_length`
- `active_tasks`
- `node_writes`
- `task_reported_node_writes`
- `world_node_writes`
- `skipped_operations`
- `unsafe_operations`
- `blocked_operations`
- `pending_model_requests`
- `pending_http_requests`
- `audit_records`
- `entities_by_type`

Task counters are updated by `core.queue_ai_task`, `core.step_ai_tasks`, and `core.cancel_ai_task`. World-operation counters are updated when `core.ai_world_ops` results are finalized.

## Pending Requests and Entity Counts

First-party plugins can report external work without depending on a metrics stack:

- `core.set_ai_runtime_pending_requests("model", count)`
- `core.set_ai_runtime_pending_requests("http", count)`
- `core.set_ai_runtime_entity_count(entity_type, count)`

These values are exposed through `core.get_ai_runtime_metrics()`.

## Audit Records

`core.get_ai_runtime_audit({ limit = n })` returns the newest `n` records in chronological order. Records are bounded in memory and include concise fields:

- `at`
- `event_type`
- `agent_id`
- `task_id`
- `actor`
- `operation`
- `status`
- `reason`
- `message`
- `changed`
- `examined`
- `skipped`
- `payload_retained`

Built-in audit events currently include:

- `capability.admin_override`
- `task.started`
- `task.completed`
- `task.cancelled`
- `task.failed`
- `task.blocked`
- `task.unsafe`
- `world.unsafe`

Plugins may add their own event with `core.record_ai_runtime_audit(record)`.

## Privacy Defaults

Private payloads are not retained by default. If a plugin calls:

```lua
core.record_ai_runtime_audit({
	event_type = "model.request",
	agent_id = "nova:emma",
	private_payload = {
		prompt = "sensitive text",
	},
})
```

the stored record omits `private_payload` and sets `payload_retained = false`.

Retention can be explicitly changed for controlled local debugging:

```lua
core.set_ai_runtime_audit_options({
	enabled = true,
	max_records = 200,
	retain_private_payloads = false,
})
```

The default should remain `retain_private_payloads = false` for public fork behavior and family-server proving-ground use.

## Local Logs

Every audit record is also written to Luanti's action log as a compact line prefixed with `[ai_runtime]`. The log line includes event type, agent, task, status, and reason where available. It does not include private payloads.

## Prometheus Path

Luanti already has optional C++ Prometheus support behind `ENABLE_PROMETHEUS`.

Local status for this fork:

- The current server-debug build keeps Prometheus disabled.
- `src/CMakeLists.txt` requires `prometheus/counter.h`, `prometheus-cpp-pull`, and `prometheus-cpp-core`.
- When compiled with `ENABLE_PROMETHEUS=ON` and the dependencies are found, Luanti serves metrics at the configured `prometheus_listener_address`; the default is `127.0.0.1:30000`.

This PR does not bridge Lua AI-runtime counters into the C++ metrics backend yet. The next metrics hardening step is to expose these counters either through a Lua polling endpoint, a server command, or a C++ bridge to `MetricsBackend`.
