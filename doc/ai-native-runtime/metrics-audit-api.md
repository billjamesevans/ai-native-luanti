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
- `task_duration_us`
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
- `model_adapter_requests`
- `model_adapter_successes`
- `model_adapter_failures`
- `model_adapter_timeouts`
- `model_adapter_latency_buckets`
- `rollback_records_written`
- `rollback_record_failures`
- `audit_records`
- `entities_by_type`

Task counters are updated by `core.queue_ai_task`, `core.step_ai_tasks`, and `core.cancel_ai_task`. `task_duration_us` records terminal task duration aggregates with `count`, `total`, `max`, `average`, and `by_status` buckets. World-operation counters are updated when `core.ai_world_ops` results are finalized.

## Pending Requests and Entity Counts

First-party plugins can report external work without depending on a metrics stack:

- `core.set_ai_runtime_pending_requests("model", count)`
- `core.set_ai_runtime_pending_requests("http", count)`
- `core.set_ai_runtime_entity_count(entity_type, count)`
- `core.record_ai_model_adapter_result(record)`

These values are exposed through `core.get_ai_runtime_metrics()`.

`core.record_ai_model_adapter_result(record)` accepts `success`, `failure`, and `timeout` outcomes. Records include adapter name, agent id, owner ref, optional task id, reason, and elapsed time. They do not include prompt text, response bodies, secrets, or private world content.

## Operator Command

`/ai_runtime` exposes a bounded server-privileged summary for local operators:

```text
AI runtime: queue=0 tasks=completed=2,cancelled=2,unsafe=1 duration=count=5,total_us=12000,max_us=5000,avg_us=2400 writes=total=4,world=4,reported=5 unsafe=1 audit=12 model=pending=0,requests=3,ok=1,fail=1,timeout=1
```

The command uses:

- `core.get_ai_runtime_operator_metrics()` for the snapshot.
- `core.format_ai_runtime_metrics(metrics)` for deterministic output.

The output includes queue length, task status counts, task-duration aggregates, node-write counters, unsafe operation count, audit record count, pending model requests, and model-adapter outcome counters. It intentionally omits agent ids, player names, prompts, payloads, source paths, and individual task labels.

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
- `adapter_name`
- `elapsed_us`
- `rollback_record_id`
- `rollback_storage_ref`
- `mutation_class`
- `chunk_index`
- `chunk_count`
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
- `model.adapter`
- `rollback.record`

Plugins may add their own event with `core.record_ai_runtime_audit(record)`.

`rollback.record` audit entries expose only rollback references and summary fields: record id, storage reference, task id, agent id, owner reference, mutation class, chunk index/count, status, reason, and changed count. They do not copy previous-node payloads into the audit log.

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

The lightweight `/ai_runtime` command is enough while the fork is validating local behavior on a small server or in tests.

A C++ `MetricsBackend` bridge becomes necessary when:

- Operators need time-series scraping instead of point-in-time chat output.
- CI or benchmark jobs need machine-collected AI-runtime counters.
- Multiple worlds or servers need comparable dashboards.
- Alerting needs to watch queue length, unsafe operations, or model backlog without a logged-in operator.
- The runtime needs metrics with lower overhead than Lua command polling.

Until those needs are real, the command remains the safer first operator surface.
