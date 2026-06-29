core.registered_ai_agents = {}
core.registered_ai_tasks = {}
core.ai_world_ops = {}
core.ai_entity_ops = {}
core.ai_player_ops = {}
core.ai_model_ops = {}
core.ai_import_ops = {}
core.ai_rollback_storage = {}

local ai_task_queue = {}
local ai_task_queue_paused = false
local ai_task_queue_pause_reason = nil
local ai_task_queue_auto_paused = false
local ai_task_queue_lag_monitor = nil

local function check_string(value, field)
	assert(type(value) == "string" and value ~= "",
		"Field '" .. field .. "' must be a non-empty string")
end

local function normalize_bool_map(value, field)
	if value == nil then
		return {}
	end
	assert(type(value) == "table", "Field '" .. field .. "' must be a table")
	local result = {}
	for name, enabled in pairs(value) do
		check_string(name, field .. " key")
		if enabled then
			result[name] = true
		end
	end
	return result
end

local function normalize_limits(value)
	if value == nil then
		return {}
	end
	assert(type(value) == "table", "Field 'limits' must be a table")
	return table.copy(value)
end

local function normalize_agent(def)
	assert(type(def) == "table", "Agent definition must be a table")
	check_string(def.agent_id, "agent_id")
	check_string(def.display_name, "display_name")
	check_string(def.owner, "owner")
	check_string(def.plugin, "plugin")

	return {
		agent_id = def.agent_id,
		display_name = def.display_name,
		owner = def.owner,
		plugin = def.plugin,
		capabilities = normalize_bool_map(def.capabilities, "capabilities"),
		limits = normalize_limits(def.limits),
		state = def.state or "enabled",
	}
end

local function make_capability_result(agent_id, capability, ok, status, reason, message)
	return {
		ok = ok,
		status = status,
		operation = "capability.check",
		agent_id = agent_id,
		capability = capability,
		reason = reason,
		message = message,
		audit_required = ok and capability == "admin.override" or false,
	}
end

local function make_task_result(task_id, ok, status, reason, message)
	return {
		ok = ok,
		status = status,
		operation = "task",
		task_id = task_id,
		reason = reason,
		message = message,
	}
end

local function public_task(task)
	if not task then
		return nil
	end
	return {
		task_id = task.task_id,
		agent_id = task.agent_id,
		owner = task.owner,
		label = task.label,
		status = task.status,
		created_at = task.created_at,
		updated_at = task.updated_at,
		budget = table.copy(task.budget),
		progress = table.copy(task.progress),
		last_result = table.copy(task.last_result),
		duration_us = task.duration_us,
	}
end

local function normalize_budget(value)
	local budget = normalize_limits(value)
	if budget.max_steps_per_step == nil then
		budget.max_steps_per_step = 1
	end
	if budget.max_node_writes_per_step == nil then
		budget.max_node_writes_per_step = 0
	end
	if budget.max_wall_time_ms == nil then
		budget.max_wall_time_ms = 0
	end
	assert(type(budget.max_steps_per_step) == "number" and budget.max_steps_per_step >= 1,
		"Field 'budget.max_steps_per_step' must be a positive number")
	assert(type(budget.max_node_writes_per_step) == "number" and budget.max_node_writes_per_step >= 0,
		"Field 'budget.max_node_writes_per_step' must be a non-negative number")
	assert(type(budget.max_wall_time_ms) == "number" and budget.max_wall_time_ms >= 0,
		"Field 'budget.max_wall_time_ms' must be a non-negative number")
	return budget
end

local function normalize_steps(value)
	assert(type(value) == "table" and #value > 0, "Field 'steps' must be a non-empty table")
	local steps = {}
	for i, step in ipairs(value) do
		assert(type(step) == "function", "Task step " .. i .. " must be a function")
		steps[i] = step
	end
	return steps
end

local function task_is_active(task)
	return task.status == "queued" or task.status == "running" or task.status == "paused"
end

local function count_active_tasks()
	local count = 0
	for _, task_id in ipairs(ai_task_queue) do
		local task = core.registered_ai_tasks[task_id]
		if task and task_is_active(task) then
			count = count + 1
		end
	end
	return count
end

local ai_runtime_audit = {}
local ai_runtime_audit_options = {
	enabled = true,
	max_records = 200,
	retain_private_payloads = false,
}
local ai_runtime_metrics = {
	tasks_queued = 0,
	tasks_completed = 0,
	tasks_cancelled = 0,
	tasks_failed = 0,
	tasks_blocked = 0,
	tasks_unsafe = 0,
	task_steps_run = 0,
	node_writes = 0,
	task_reported_node_writes = 0,
	world_node_writes = 0,
	skipped_operations = 0,
	unsafe_operations = 0,
	blocked_operations = 0,
	pending_model_requests = 0,
	pending_http_requests = 0,
	model_runtime_requests = 0,
	model_adapter_requests = 0,
	model_adapter_successes = 0,
	model_adapter_failures = 0,
	model_adapter_timeouts = 0,
	model_adapter_latency_buckets = {
		under_100ms = 0,
		under_1000ms = 0,
		over_1000ms = 0,
	},
	rollback_records_written = 0,
	rollback_record_failures = 0,
	task_lag_pauses = 0,
	task_wall_clock_budget_exceeded = 0,
	task_duration_us = {
		count = 0,
		total = 0,
		max = 0,
		average = 0,
		by_status = {},
	},
	entity_spawns = 0,
	entity_moves = 0,
	entity_cleanups = 0,
	player_teleports = 0,
	combat_defends = 0,
	import_plans = 0,
	entities_by_type = {},
}
local ai_task_status_order = {
	"queued",
	"running",
	"paused",
	"completed",
	"cancelled",
	"failed",
	"blocked",
	"unsafe",
}

local function increment_metric(name, amount)
	ai_runtime_metrics[name] = (ai_runtime_metrics[name] or 0) + (amount or 1)
end

local function audit_timestamp()
	return core.get_us_time and core.get_us_time() or 0
end

local function copy_audit_record(record)
	local copy = table.copy(record)
	if record.private_payload and ai_runtime_audit_options.retain_private_payloads then
		copy.private_payload = table.copy(record.private_payload)
	end
	return copy
end

function core.set_ai_runtime_audit_options(options)
	assert(type(options) == "table", "Audit options must be a table")
	if options.enabled ~= nil then
		ai_runtime_audit_options.enabled = options.enabled == true
	end
	if options.max_records ~= nil then
		assert(type(options.max_records) == "number" and options.max_records >= 0,
			"Field 'max_records' must be a non-negative number")
		ai_runtime_audit_options.max_records = options.max_records
	end
	if options.retain_private_payloads ~= nil then
		ai_runtime_audit_options.retain_private_payloads =
			options.retain_private_payloads == true
	end
end

function core.record_ai_runtime_audit(record)
	assert(type(record) == "table", "Audit record must be a table")
	check_string(record.event_type, "event_type")
	if not ai_runtime_audit_options.enabled then
		return nil
	end

	local sanitized = {
		at = audit_timestamp(),
		event_type = record.event_type,
		agent_id = record.agent_id,
		task_id = record.task_id,
		actor = record.actor,
		operation = record.operation,
		status = record.status,
		reason = record.reason,
		message = record.message,
		adapter_name = record.adapter_name,
		elapsed_us = record.elapsed_us,
		rollback_record_id = record.rollback_record_id,
		rollback_storage_ref = record.rollback_storage_ref,
		mutation_class = record.mutation_class,
		chunk_index = record.chunk_index,
		chunk_count = record.chunk_count,
		changed = record.changed,
		examined = record.examined,
		skipped = record.skipped,
		payload_retained = false,
	}
	if record.private_payload and ai_runtime_audit_options.retain_private_payloads then
		sanitized.private_payload = table.copy(record.private_payload)
		sanitized.payload_retained = true
	end

	ai_runtime_audit[#ai_runtime_audit + 1] = sanitized
	while #ai_runtime_audit > ai_runtime_audit_options.max_records do
		table.remove(ai_runtime_audit, 1)
	end

	if core.log then
		core.log("action", "[ai_runtime] audit event=" .. sanitized.event_type
			.. (sanitized.agent_id and (" agent=" .. sanitized.agent_id) or "")
			.. (sanitized.task_id and (" task=" .. sanitized.task_id) or "")
			.. (sanitized.status and (" status=" .. sanitized.status) or "")
			.. (sanitized.reason and (" reason=" .. sanitized.reason) or ""))
	end
	return copy_audit_record(sanitized)
end

function core.get_ai_runtime_audit(options)
	options = options or {}
	local limit = options.limit or #ai_runtime_audit
	assert(type(limit) == "number" and limit >= 0,
		"Field 'limit' must be a non-negative number")
	local start = math.max(1, #ai_runtime_audit - math.floor(limit) + 1)
	local result = {}
	for i = start, #ai_runtime_audit do
		result[#result + 1] = copy_audit_record(ai_runtime_audit[i])
	end
	return result
end

function core.set_ai_runtime_pending_requests(kind, count)
	assert(kind == "model" or kind == "http", "Pending request kind must be 'model' or 'http'")
	assert(type(count) == "number" and count >= 0, "Pending request count must be non-negative")
	if kind == "model" then
		ai_runtime_metrics.pending_model_requests = count
	else
		ai_runtime_metrics.pending_http_requests = count
	end
end

local function increment_model_latency_bucket(elapsed_us)
	if elapsed_us < 100000 then
		ai_runtime_metrics.model_adapter_latency_buckets.under_100ms =
			ai_runtime_metrics.model_adapter_latency_buckets.under_100ms + 1
	elseif elapsed_us < 1000000 then
		ai_runtime_metrics.model_adapter_latency_buckets.under_1000ms =
			ai_runtime_metrics.model_adapter_latency_buckets.under_1000ms + 1
	else
		ai_runtime_metrics.model_adapter_latency_buckets.over_1000ms =
			ai_runtime_metrics.model_adapter_latency_buckets.over_1000ms + 1
	end
end

function core.record_ai_model_adapter_result(record)
	assert(type(record) == "table", "Model adapter metric record must be a table")
	local status = record.status
	assert(status == "success" or status == "failure" or status == "timeout",
		"Model adapter status must be success, failure, or timeout")
	local elapsed_us = record.elapsed_us or 0
	assert(type(elapsed_us) == "number" and elapsed_us >= 0,
		"Model adapter elapsed_us must be a non-negative number")
	local adapter_name = record.adapter_name or "model_adapter"
	check_string(adapter_name, "adapter_name")

	increment_metric("model_adapter_requests")
	if status == "success" then
		increment_metric("model_adapter_successes")
	elseif status == "timeout" then
		increment_metric("model_adapter_timeouts")
	else
		increment_metric("model_adapter_failures")
	end
	increment_model_latency_bucket(elapsed_us)

	return core.record_ai_runtime_audit({
		event_type = "model.adapter",
		agent_id = record.agent_id,
		task_id = record.task_id,
		actor = record.owner_ref,
		operation = "model.adapter",
		status = status,
		reason = record.reason,
		message = "Model adapter " .. status .. ".",
		adapter_name = adapter_name,
		elapsed_us = elapsed_us,
	})
end

function core.set_ai_runtime_entity_count(entity_type, count)
	check_string(entity_type, "entity_type")
	assert(type(count) == "number" and count >= 0, "Entity count must be non-negative")
	ai_runtime_metrics.entities_by_type[entity_type] = count
end

function core.get_ai_runtime_metrics()
	local metrics = table.copy(ai_runtime_metrics)
	metrics.active_tasks = count_active_tasks()
	metrics.queue_length = metrics.active_tasks
	metrics.audit_records = #ai_runtime_audit
	metrics.entities_by_type = table.copy(ai_runtime_metrics.entities_by_type)
	metrics.model_adapter_latency_buckets =
		table.copy(ai_runtime_metrics.model_adapter_latency_buckets)
	metrics.task_duration_us = {
		count = ai_runtime_metrics.task_duration_us.count,
		total = ai_runtime_metrics.task_duration_us.total,
		max = ai_runtime_metrics.task_duration_us.max,
		average = ai_runtime_metrics.task_duration_us.average,
		by_status = {},
	}
	for status, duration in pairs(ai_runtime_metrics.task_duration_us.by_status) do
		metrics.task_duration_us.by_status[status] = table.copy(duration)
	end
	return metrics
end

local function count_task_statuses()
	local counts = {}
	for _, status in ipairs(ai_task_status_order) do
		counts[status] = 0
	end
	for _, task in pairs(core.registered_ai_tasks) do
		counts[task.status] = (counts[task.status] or 0) + 1
	end
	return counts
end

function core.get_ai_runtime_operator_metrics()
	local metrics = core.get_ai_runtime_metrics()
	metrics.task_status_counts = count_task_statuses()
	return metrics
end

local function format_task_status_counts(counts)
	local parts = {}
	for _, status in ipairs(ai_task_status_order) do
		local count = counts and counts[status] or 0
		if count and count > 0 then
			parts[#parts + 1] = status .. "=" .. count
		end
	end
	if #parts == 0 then
		return "none"
	end
	return table.concat(parts, ",")
end

local function metric_number(metrics, name)
	local value = metrics and metrics[name] or 0
	if type(value) ~= "number" then
		return 0
	end
	return value
end

local function duration_metric_number(metrics, name)
	local duration = metrics and metrics.task_duration_us or nil
	local value = duration and duration[name] or 0
	if type(value) ~= "number" then
		return 0
	end
	return value
end

function core.format_ai_runtime_metrics(metrics)
	metrics = metrics or core.get_ai_runtime_operator_metrics()
	return "AI runtime: queue=" .. metric_number(metrics, "queue_length")
		.. " tasks=" .. format_task_status_counts(metrics.task_status_counts)
		.. " duration=count=" .. duration_metric_number(metrics, "count")
		.. ",total_us=" .. duration_metric_number(metrics, "total")
		.. ",max_us=" .. duration_metric_number(metrics, "max")
		.. ",avg_us=" .. duration_metric_number(metrics, "average")
		.. " writes=total=" .. metric_number(metrics, "node_writes")
		.. ",world=" .. metric_number(metrics, "world_node_writes")
		.. ",reported=" .. metric_number(metrics, "task_reported_node_writes")
		.. " unsafe=" .. metric_number(metrics, "unsafe_operations")
		.. " audit=" .. metric_number(metrics, "audit_records")
		.. " model=pending=" .. metric_number(metrics, "pending_model_requests")
		.. ",requests=" .. metric_number(metrics, "model_adapter_requests")
		.. ",ok=" .. metric_number(metrics, "model_adapter_successes")
		.. ",fail=" .. metric_number(metrics, "model_adapter_failures")
		.. ",timeout=" .. metric_number(metrics, "model_adapter_timeouts")
end

local function record_task_audit(event_type, task, extra)
	extra = extra or {}
	core.record_ai_runtime_audit({
		event_type = event_type,
		agent_id = task.agent_id,
		task_id = task.task_id,
		status = extra.status or task.status,
		reason = extra.reason,
		message = extra.message,
		changed = extra.changed,
		skipped = extra.skipped,
	})
end

local function record_task_duration(task, status)
	if task.duration_recorded then
		return
	end
	local finished_at = core.get_us_time and core.get_us_time() or task.updated_at or 0
	local started_at = task.started_at or task.created_at or finished_at
	local elapsed_us = math.max(0, finished_at - started_at)
	task.duration_us = elapsed_us
	task.duration_recorded = true

	local duration = ai_runtime_metrics.task_duration_us
	duration.count = duration.count + 1
	duration.total = duration.total + elapsed_us
	duration.max = math.max(duration.max, elapsed_us)
	duration.average = duration.count > 0 and duration.total / duration.count or 0

	local by_status = duration.by_status[status] or {
		count = 0,
		total = 0,
		max = 0,
		average = 0,
	}
	by_status.count = by_status.count + 1
	by_status.total = by_status.total + elapsed_us
	by_status.max = math.max(by_status.max, elapsed_us)
	by_status.average = by_status.count > 0 and by_status.total / by_status.count or 0
	duration.by_status[status] = by_status
end

local function copy_pos(pos)
	return {
		x = pos.x,
		y = pos.y,
		z = pos.z,
	}
end

local function check_pos(pos, field)
	assert(type(pos) == "table", "Field '" .. field .. "' must be a position table")
	assert(type(pos.x) == "number", "Field '" .. field .. ".x' must be a number")
	assert(type(pos.y) == "number", "Field '" .. field .. ".y' must be a number")
	assert(type(pos.z) == "number", "Field '" .. field .. ".z' must be a number")
	return copy_pos(pos)
end

local function make_action_result(operation, options)
	local started_at = core.get_us_time and core.get_us_time() or 0
	return {
		ok = false,
		status = "error",
		operation = operation,
		agent_id = options and options.agent_id or nil,
		task_id = options and options.task_id or nil,
		changed = 0,
		examined = 0,
		skipped = 0,
		reason = nil,
		message = nil,
		samples = {},
		metrics = {
			started_at = started_at,
			elapsed_us = 0,
			node_writes = 0,
		},
	}
end

local function finish_action_result(result, status, reason, message)
	result.status = status
	result.ok = status == "success" or status == "partial"
	result.reason = reason
	result.message = message
	local started_at = result.metrics.started_at
	if core.get_us_time and started_at > 0 then
		result.metrics.elapsed_us = core.get_us_time() - started_at
	end
	result.metrics.started_at = nil
	if result.operation and result.operation:sub(1, 9) == "ai_world." then
		local writes = result.metrics.node_writes or 0
		increment_metric("node_writes", writes)
		increment_metric("world_node_writes", writes)
		increment_metric("skipped_operations", result.skipped)
		if status == "unsafe" then
			increment_metric("unsafe_operations")
			core.record_ai_runtime_audit({
				event_type = "world.unsafe",
				agent_id = result.agent_id,
				task_id = result.task_id,
				operation = result.operation,
				status = result.status,
				reason = result.reason,
				message = result.message,
				changed = result.changed,
				examined = result.examined,
				skipped = result.skipped,
			})
		elseif status == "blocked" then
			increment_metric("blocked_operations")
		end
	end
	return result
end

local function runtime_gate_options(options, operation)
	assert(type(options) == "table", "Runtime gate options must be a table")
	check_string(options.agent_id, "agent_id")
	local agent = core.get_ai_agent(options.agent_id)
	local owner = options.owner or options.owner_ref or agent and agent.owner
	if owner then
		check_string(owner, "owner")
	end
	return agent, owner, make_action_result(operation, options)
end

local function finish_runtime_gate_result(result, status, reason, message)
	return finish_action_result(result, status, reason, message)
end

local function runtime_gate_denied(options, operation, capability, event_type)
	local result = make_action_result(operation, options)
	local capability_result = core.check_agent_capability(options.agent_id, capability)
	if capability_result.ok then
		return nil
	end
	result.skipped = 1
	core.record_ai_runtime_audit({
		event_type = event_type,
		agent_id = result.agent_id,
		task_id = result.task_id,
		operation = operation,
		status = "blocked",
		reason = capability_result.reason,
		message = capability_result.message,
		skipped = result.skipped,
	})
	return finish_runtime_gate_result(result, "blocked",
		capability_result.reason, capability_result.message)
end

function core.ai_model_ops.request(prompt, options)
	check_string(prompt, "prompt")
	options = options or {}
	local _, owner, result = runtime_gate_options(options, "ai_model.request")
	local denied = runtime_gate_denied(options, "ai_model.request", "http.llm", "model.request")
	if denied then
		return denied
	end
	local adapter = options.adapter
	if adapter == nil then
		result.skipped = 1
		core.record_ai_runtime_audit({
			event_type = "model.request",
			agent_id = result.agent_id,
			task_id = result.task_id,
			operation = result.operation,
			status = "blocked",
			reason = "model_adapter_unavailable",
			message = "No model adapter is configured.",
			skipped = result.skipped,
		})
		return finish_runtime_gate_result(result, "blocked", "model_adapter_unavailable",
			"No model adapter is configured.")
	end
	assert(type(adapter) == "function", "Field 'adapter' must be a function")

	increment_metric("model_runtime_requests")
	core.record_ai_runtime_audit({
		event_type = "model.request",
		agent_id = result.agent_id,
		task_id = result.task_id,
		actor = owner,
		operation = result.operation,
		status = "running",
		reason = "model_adapter_requested",
		message = "Model adapter requested.",
		private_payload = {
			prompt = options.private_prompt or prompt,
		},
	})

	local started_at = core.get_us_time and core.get_us_time() or 0
	local ok, adapter_result = pcall(adapter, {
		agent_id = options.agent_id,
		owner = owner,
		prompt = prompt,
		context = options.context or {},
		task_id = options.task_id,
	})
	if not ok then
		adapter_result = {
			ok = false,
			message = "Model adapter failed.",
			reason = "adapter_error",
		}
	end
	local elapsed_us = adapter_result and adapter_result.elapsed_us
	if not elapsed_us then
		elapsed_us = started_at > 0 and core.get_us_time and (core.get_us_time() - started_at) or 0
	end
	local adapter_status = "failure"
	if adapter_result and adapter_result.timeout then
		adapter_status = "timeout"
	elseif adapter_result and adapter_result.ok then
		adapter_status = "success"
	end
	core.record_ai_model_adapter_result({
		agent_id = options.agent_id,
		owner_ref = owner,
		task_id = options.task_id,
		adapter_name = adapter_result and adapter_result.adapter_name
			or options.adapter_name or "model_adapter",
		status = adapter_status,
		reason = adapter_result and adapter_result.reason,
		elapsed_us = elapsed_us,
	})

	result.examined = 1
	result.metrics.elapsed_us = elapsed_us
	if adapter_result and adapter_result.response ~= nil then
		result.response = adapter_result.response
	end
	local message = adapter_result and adapter_result.message
		or "Model adapter did not return a response."
	if adapter_result and adapter_result.ok then
		return finish_runtime_gate_result(result, "success", "model_response", message)
	end
	result.skipped = 1
	return finish_runtime_gate_result(result, "blocked",
		adapter_result and adapter_result.reason or "model_adapter_failed", message)
end

local function import_action_requires_capability(action)
	local capabilities = action.required_capabilities or {}
	for _, capability in ipairs(capabilities) do
		if capability == "import.assets" then
			return true
		end
	end
	return false
end

local function import_handoff_has_payload(value, depth)
	if type(value) ~= "table" then
		return false
	end
	depth = depth or 0
	if depth > 8 then
		return false
	end
	if value.asset_payload ~= nil or value.private_payload ~= nil or value.payload ~= nil then
		return true
	end
	for _, child in pairs(value) do
		if import_handoff_has_payload(child, depth + 1) then
			return true
		end
	end
	return false
end

local function import_inventory_requires_capability(entry)
	local capabilities = entry.required_capabilities or {}
	for _, capability in ipairs(capabilities) do
		if capability == "import.assets" then
			return true
		end
	end
	return false
end

local function import_source_inventory(plan)
	local source = plan.source or {}
	local inventory = plan.source_inventory or source.inventory or {}
	assert(type(inventory) == "table", "Import source inventory must be a table")
	return inventory
end

function core.ai_import_ops.plan(plan, options)
	assert(type(plan) == "table", "Import plan must be a table")
	options = options or {}
	local _, owner, result = runtime_gate_options(options, "ai_import.plan")
	local denied = runtime_gate_denied(options, "ai_import.plan", "import.assets", "import.plan")
	if denied then
		return denied
	end
	if import_handoff_has_payload(plan) then
		result.skipped = 1
		core.record_ai_runtime_audit({
			event_type = "import.plan",
			agent_id = result.agent_id,
			task_id = result.task_id,
			actor = owner,
			operation = result.operation,
			status = "blocked",
			reason = "payload_rejected",
			message = "Import planning cannot retain asset payloads.",
			skipped = result.skipped,
		})
		return finish_runtime_gate_result(result, "blocked", "payload_rejected",
			"Import planning cannot retain asset payloads.")
	end
	if plan.dry_run ~= true or plan.assets_copied == true then
		result.skipped = 1
		core.record_ai_runtime_audit({
			event_type = "import.plan",
			agent_id = result.agent_id,
			task_id = result.task_id,
			actor = owner,
			operation = result.operation,
			status = "blocked",
			reason = "dry_run_required",
			message = "Import planning is dry-run only in this runtime milestone.",
			skipped = result.skipped,
		})
		return finish_runtime_gate_result(result, "blocked", "dry_run_required",
			"Import planning is dry-run only in this runtime milestone.")
	end

	local actions = plan.planned_actions or {}
	assert(type(actions) == "table", "Field 'planned_actions' must be a table")
	for _, action in ipairs(actions) do
		assert(type(action) == "table", "Import planned actions must be tables")
		if not import_action_requires_capability(action) then
			result.skipped = 1
			core.record_ai_runtime_audit({
				event_type = "import.plan",
				agent_id = result.agent_id,
				task_id = result.task_id,
				actor = owner,
				operation = result.operation,
				status = "blocked",
				reason = "import_capability_marker_required",
				message = "Every import action must require import.assets.",
				skipped = result.skipped,
			})
			return finish_runtime_gate_result(result, "blocked",
				"import_capability_marker_required",
				"Every import action must require import.assets.")
		end
	end
	local inventory = import_source_inventory(plan)
	for _, entry in ipairs(inventory) do
		assert(type(entry) == "table", "Import inventory entries must be tables")
		if not import_inventory_requires_capability(entry) then
			result.skipped = 1
			core.record_ai_runtime_audit({
				event_type = "import.plan",
				agent_id = result.agent_id,
				task_id = result.task_id,
				actor = owner,
				operation = result.operation,
				status = "blocked",
				reason = "import_inventory_capability_marker_required",
				message = "Every import inventory entry must require import.assets.",
				skipped = result.skipped,
			})
			return finish_runtime_gate_result(result, "blocked",
				"import_inventory_capability_marker_required",
				"Every import inventory entry must require import.assets.")
		end
	end

	result.examined = #actions
	local source = plan.source or {}
	result.import_plan = {
		dry_run = true,
		source_id = plan.source_id or source.source_id,
		source_class = plan.source_class or source.source_class,
		source_inventory = table.copy(inventory),
		source_content_hashes = table.copy(source.content_hashes or plan.source_content_hashes or {}),
		planned_actions = table.copy(actions),
		assets_copied = false,
		inventory_count = #inventory,
	}
	increment_metric("import_plans")
	core.record_ai_runtime_audit({
		event_type = "import.plan",
		agent_id = result.agent_id,
		task_id = result.task_id,
		actor = owner,
		operation = result.operation,
		status = "success",
		reason = "import_plan_recorded",
		message = "Import dry-run plan recorded.",
		examined = result.examined,
	})
	return finish_runtime_gate_result(result, "success", "import_plan_recorded",
		"Import dry-run plan recorded.")
end

local function sample_limit(options)
	if not options or options.sample_limit == nil then
		return 8
	end
	assert(type(options.sample_limit) == "number" and options.sample_limit >= 0,
		"Field 'sample_limit' must be a non-negative number")
	return options.sample_limit
end

local function add_action_sample(result, options, pos, node, reason, message)
	if #result.samples >= sample_limit(options) then
		return
	end
	local sample = {
		reason = reason,
		message = message,
	}
	if pos then
		sample.pos = copy_pos(pos)
	end
	if node then
		sample.node = table.copy(node)
	end
	result.samples[#result.samples + 1] = sample
end

local function actor_name(options)
	return options and (options.owner or options.player_name or options.agent_id) or ""
end

local import_structure_required_capabilities = {
	"import.assets",
	"world.place",
	"world.batch",
}

local ai_import_structure_runs = {}
local ai_import_rollback_runs = {}

local function import_structure_result(options)
	local result = make_action_result("ai_import.structure_apply", options)
	result.metrics.planned_node_writes = 0
	result.metrics.mapblock_churn = 0
	result.metrics.rollback_records = 0
	result.metrics.rollback_failures = 0
	return result
end

local function normalize_structure_chunk(options, position_count)
	options = options or {}
	local chunk = options.chunk or {}
	local result = {
		chunk_index = options.chunk_index or chunk.chunk_index or 0,
		chunk_count = options.chunk_count or chunk.chunk_count or 1,
		first_position_index = options.first_position_index
			or chunk.first_position_index or 0,
		position_count = chunk.position_count or position_count,
	}
	for key, value in pairs(result) do
		assert(type(value) == "number" and value >= 0,
			"Field 'chunk." .. key .. "' must be a non-negative number")
		result[key] = math.floor(value)
	end
	assert(result.chunk_count >= 1, "Field 'chunk.chunk_count' must be at least 1")
	assert(result.position_count >= 1, "Field 'chunk.position_count' must be at least 1")
	return result
end

local function annotate_structure_result(result, chunk)
	result.metrics.chunk_index = chunk.chunk_index
	result.metrics.chunk_count = chunk.chunk_count
	result.metrics.first_position_index = chunk.first_position_index
	result.metrics.position_count = chunk.position_count
	result.chunk = table.copy(chunk)
	return result
end

local function record_structure_chunk_result(result)
	if not result or not result.task_id then
		return
	end
	local chunk = result.chunk or {
		chunk_index = result.metrics and result.metrics.chunk_index or 0,
		chunk_count = result.metrics and result.metrics.chunk_count or 1,
		first_position_index = result.metrics and result.metrics.first_position_index or 0,
		position_count = result.metrics and result.metrics.position_count
			or result.examined or 0,
	}
	local run = ai_import_structure_runs[result.task_id]
	if not run then
		run = {
			task_id = result.task_id,
			chunk_count = chunk.chunk_count or 1,
			chunks = {},
			started_at = result.metrics and result.metrics.started_at or nil,
		}
		ai_import_structure_runs[result.task_id] = run
	end
	run.chunk_count = math.max(run.chunk_count or 1, chunk.chunk_count or 1)
	local index = (chunk.chunk_index or 0) + 1
	run.chunks[index] = {
		status = result.status,
		reason = result.reason,
		changed = result.changed or 0,
		examined = result.examined or 0,
		skipped = result.skipped or 0,
		rollback_record_id = result.rollback_record_id,
		rollback_storage_ref = result.rollback_storage_ref,
		chunk = table.copy(chunk),
		metrics = {
			node_writes = result.metrics and result.metrics.node_writes or 0,
			mapblock_churn = result.metrics and result.metrics.mapblock_churn or 0,
			planned_node_writes = result.metrics and result.metrics.planned_node_writes or 0,
			elapsed_us = result.metrics and result.metrics.elapsed_us or 0,
			rollback_records = result.metrics and result.metrics.rollback_records or 0,
			rollback_failures = result.metrics and result.metrics.rollback_failures or 0,
		},
	}
end

local function record_rollback_chunk_result(result)
	if not result or not result.task_id then
		return
	end
	local chunk = result.chunk or {
		chunk_index = result.metrics and result.metrics.chunk_index or 0,
		chunk_count = result.metrics and result.metrics.chunk_count or 1,
		first_position_index = result.metrics and result.metrics.first_position_index or 0,
		position_count = result.metrics and result.metrics.position_count
			or result.examined or 0,
	}
	local run = ai_import_rollback_runs[result.task_id]
	if not run then
		run = {
			task_id = result.task_id,
			chunk_count = chunk.chunk_count or 1,
			chunks = {},
			started_at = result.metrics and result.metrics.started_at or nil,
		}
		ai_import_rollback_runs[result.task_id] = run
	end
	run.chunk_count = math.max(run.chunk_count or 1, chunk.chunk_count or 1)
	local index = (chunk.chunk_index or 0) + 1
	run.chunks[index] = {
		status = result.status,
		reason = result.reason,
		changed = result.changed or 0,
		examined = result.examined or 0,
		skipped = result.skipped or 0,
		rollback_record_id = result.rollback_record_id,
		rollback_storage_ref = result.rollback_storage_ref,
		source_rollback_record_id = result.source_rollback_record_id,
		chunk = table.copy(chunk),
		metrics = {
			node_writes = result.metrics and result.metrics.node_writes or 0,
			mapblock_churn = result.metrics and result.metrics.mapblock_churn or 0,
			planned_node_writes = result.metrics and result.metrics.planned_node_writes or 0,
			elapsed_us = result.metrics and result.metrics.elapsed_us or 0,
			rollback_records = result.metrics and result.metrics.rollback_records or 0,
			rollback_failures = result.metrics and result.metrics.rollback_failures or 0,
		},
	}
end

local function finish_import_structure_result(result, status, reason, message)
	record_structure_chunk_result(result)
	core.record_ai_runtime_audit({
		event_type = "import.structure_apply",
		agent_id = result.agent_id,
		task_id = result.task_id,
		operation = result.operation,
		status = status,
		reason = reason,
		message = message,
		changed = result.changed,
		examined = result.examined,
		skipped = result.skipped,
		rollback_record_id = result.rollback_record_id,
		rollback_storage_ref = result.rollback_storage_ref,
		mutation_class = "compat_import",
	})
	return finish_runtime_gate_result(result, status, reason, message)
end

local function blocked_import_structure_result(result, reason, message)
	if result.examined > 0 and result.skipped == 0 then
		result.skipped = result.examined
	end
	return finish_import_structure_result(result, "blocked", reason, message)
end

local function normalize_structure_rollback_policy(policy)
	policy = policy or "snapshot"
	if policy == "manifest_only" then
		return "manifest"
	end
	if policy == "snapshot" or policy == "manifest" or policy == "chunked" then
		return policy
	end
	return nil
end

local function normalize_structure_placements(placements)
	assert(type(placements) == "table" and #placements > 0,
		"Field 'placements' must be a non-empty table")
	local normalized = {}
	for index, placement in ipairs(placements) do
		assert(type(placement) == "table", "Structure placements must be tables")
		local node_name = placement.node_name or placement.name
		check_string(node_name, "placements[" .. index .. "].node_name")
		normalized[#normalized + 1] = {
			pos = check_pos(placement.pos, "placements[" .. index .. "].pos"),
			node_name = node_name,
		}
	end
	return normalized
end

local function structure_positions(placements)
	local positions = {}
	for _, placement in ipairs(placements) do
		positions[#positions + 1] = copy_pos(placement.pos)
	end
	return positions
end

local function mapblock_key(pos)
	return math.floor(pos.x / 16) .. ":"
		.. math.floor(pos.y / 16) .. ":"
		.. math.floor(pos.z / 16)
end

local function structure_mapblock_churn(placements)
	local seen = {}
	local count = 0
	for _, placement in ipairs(placements or {}) do
		local pos = placement.pos or placement
		local key = mapblock_key(pos)
		if not seen[key] then
			seen[key] = true
			count = count + 1
		end
	end
	return count
end

local function structure_budget_value(options, field, fallback)
	local value = options[field]
	if value == nil then
		value = fallback
	end
	assert(type(value) == "number" and value >= 0,
		"Field '" .. field .. "' must be a non-negative number")
	return math.floor(value)
end

local function copy_source_reference(source_reference)
	if type(source_reference) ~= "table" then
		return nil
	end
	return {
		reference_type = source_reference.reference_type,
		redacted_id = source_reference.redacted_id,
		inventory_hash = source_reference.inventory_hash,
	}
end

local function import_structure_capability_block(options, result)
	for _, capability in ipairs(import_structure_required_capabilities) do
		local capability_result = core.check_agent_capability(options.agent_id, capability)
		if not capability_result.ok then
			result.skipped = result.examined > 0 and result.examined or 1
			return blocked_import_structure_result(result, capability_result.reason,
				capability_result.message)
		end
	end
	return nil
end

function core.ai_import_ops.apply_structure(placements, options)
	options = options or {}
	runtime_gate_options(options, "ai_import.structure_apply")
	local normalized = normalize_structure_placements(placements)
	local result = import_structure_result(options)
	result.examined = #normalized
	result.metrics.planned_node_writes = #normalized
	result.metrics.mapblock_churn = structure_mapblock_churn(normalized)
	local chunk = normalize_structure_chunk(options, #normalized)
	annotate_structure_result(result, chunk)

	local capability_block = import_structure_capability_block(options, result)
	if capability_block then
		return capability_block
	end
	if import_handoff_has_payload({
			placements = placements,
			source_reference = options.source_reference,
			provenance = options.provenance,
			private_payload = options.private_payload,
			asset_payload = options.asset_payload,
			has_rejected_payload = options.has_rejected_payload and {
				payload = true,
			} or nil,
		}) then
		return blocked_import_structure_result(result, "payload_rejected",
			"Structure apply cannot retain private payloads or asset bytes.")
	end
	if options.explicit_approval ~= true then
		return blocked_import_structure_result(result, "approval_required",
			"Structure apply requires explicit operator approval.")
	end
	local target_world = options.target_world or {}
	if options.staging ~= true and target_world.staging ~= true then
		return blocked_import_structure_result(result, "staging_target_required",
			"Structure apply requires a staging target world.")
	end
	if options.allow_mutation ~= true then
		return blocked_import_structure_result(result, "structure_mutation_not_enabled",
			"Structure apply requires explicit allow_mutation.")
	end
	local rollback_policy = normalize_structure_rollback_policy(options.rollback_policy)
	if not rollback_policy then
		return blocked_import_structure_result(result, "rollback_policy_not_mutating",
			"Structure apply requires manifest_only, manifest, chunked, or snapshot rollback.")
	end
	local max_writes = structure_budget_value(options, "max_node_writes_per_step", #normalized)
	if #normalized > max_writes then
		return blocked_import_structure_result(result, "node_write_budget_exceeded",
			"Structure apply exceeds the per-step node-write budget.")
	end
	local max_mapblock_churn = structure_budget_value(options,
		"max_mapblock_churn_total", result.metrics.mapblock_churn)
	if result.metrics.mapblock_churn > max_mapblock_churn then
		return blocked_import_structure_result(result, "mapblock_churn_budget_exceeded",
			"Structure apply exceeds the mapblock-churn budget.")
	end
	if not options.world_id or options.world_id == "" then
		return blocked_import_structure_result(result, "rollback_metadata_unavailable",
			"Structure apply requires a target world id before mutation.")
	end

	local rollback_result = core.run_ai_world_mutation_with_rollback({
		record_id = options.rollback_record_id,
		policy = rollback_policy,
		world_id = options.world_id,
		task_id = options.task_id,
		agent_id = options.agent_id,
		owner_ref = options.owner or options.owner_ref,
		operation_label = options.operation_label or "compat.structure.apply",
		mutation_class = "compat_import",
		bounds = options.bounds,
		positions = structure_positions(normalized),
		chunk = chunk,
		get_node = options.get_node,
		persist_record = options.persist_record or options.persist_rollback_record,
	}, function(ctx)
		return core.ai_world_ops.batch_place(normalized, {
			agent_id = ctx.agent_id,
			task_id = ctx.task_id,
			owner = options.owner or options.owner_ref,
			get_node = options.get_node,
			set_node = options.set_node,
			bounds = options.bounds,
			replace_existing = options.replace_existing == true,
			allow_hazards = options.allow_hazards == true,
			min_player_distance = options.min_player_distance,
			max_changes = #normalized,
			sample_limit = options.sample_limit,
		})
	end)

	if not rollback_result.ok and rollback_result.reason == "rollback_metadata_unavailable" then
		result.metrics.rollback_failures = 1
		return blocked_import_structure_result(result, "rollback_metadata_unavailable",
			rollback_result.message or "Rollback metadata is unavailable.")
	end
	annotate_structure_result(rollback_result, chunk)
	if rollback_result.rollback_record_id then
		rollback_result.metrics = rollback_result.metrics or {}
		rollback_result.metrics.rollback_records = 1
		rollback_result.metrics.mapblock_churn = result.metrics.mapblock_churn
		rollback_result.metrics.planned_node_writes = result.metrics.planned_node_writes
		rollback_result.source_reference = copy_source_reference(options.source_reference)
	end
	record_structure_chunk_result(rollback_result)
	return rollback_result
end

function core.ai_import_ops.define_structure_apply_task(def)
	assert(type(def) == "table", "Structure apply task definition must be a table")
	check_string(def.task_id, "task_id")
	check_string(def.agent_id, "agent_id")
	check_string(def.owner, "owner")
	local placements = normalize_structure_placements(def.placements)
	local max_writes = structure_budget_value(def,
		"max_node_writes_per_step", #placements)
	local has_rejected_payload = import_handoff_has_payload(def)
	local task_def = table.copy(def)
	task_def.source_reference = copy_source_reference(def.source_reference)
	task_def.placements = nil
	task_def.provenance = nil
	task_def.private_payload = nil
	task_def.asset_payload = nil
	task_def.payload = nil
	task_def.has_rejected_payload = has_rejected_payload
	return {
		task_id = def.task_id,
		agent_id = def.agent_id,
		owner = def.owner,
		label = def.label or "compat.structure.place",
		required_capabilities = {
			["import.assets"] = true,
			["world.place"] = true,
			["world.batch"] = true,
		},
		mutation_class = "compat_import",
		metadata = {
			report_id = def.report_id,
			action_index = def.action_index,
			placement_count = #placements,
			staging = def.staging == true
				or (def.target_world and def.target_world.staging == true) or false,
			source_reference = task_def.source_reference,
		},
		budget = {
			max_steps_per_step = 1,
			max_node_writes_per_step = max_writes,
			max_wall_time_ms = def.max_wall_time_ms or 0,
		},
		steps = {
			function(ctx)
				task_def.agent_id = ctx.agent_id
				task_def.owner = ctx.owner
				task_def.task_id = ctx.task_id
				task_def.max_node_writes_per_step = max_writes
				return core.ai_import_ops.apply_structure(placements, task_def)
			end,
		},
	}
end

function core.ai_import_ops.queue_structure_apply_task(def)
	return core.queue_ai_task(core.ai_import_ops.define_structure_apply_task(def))
end

local function chunk_structure_placements(placements, chunk_size)
	assert(type(chunk_size) == "number" and chunk_size >= 1,
		"Field 'chunk_size' must be a positive number")
	chunk_size = math.floor(chunk_size)
	local chunks = {}
	local index = 1
	while index <= #placements do
		local chunk = {
			first_position_index = index - 1,
			placements = {},
		}
		for _ = 1, chunk_size do
			if index > #placements then
				break
			end
			chunk.placements[#chunk.placements + 1] = placements[index]
			index = index + 1
		end
		chunks[#chunks + 1] = chunk
	end
	for chunk_index, chunk in ipairs(chunks) do
		chunk.chunk = {
			chunk_index = chunk_index - 1,
			chunk_count = #chunks,
			first_position_index = chunk.first_position_index,
			position_count = #chunk.placements,
		}
	end
	return chunks
end

local function blocked_structure_task_step(ctx, task_def, placements, reason, message)
	local result = import_structure_result({
		agent_id = ctx.agent_id,
		task_id = ctx.task_id,
	})
	result.examined = #placements
	result.metrics.planned_node_writes = #placements
	result.metrics.mapblock_churn = structure_mapblock_churn(placements)
	annotate_structure_result(result, normalize_structure_chunk(task_def, #placements))
	return blocked_import_structure_result(result, reason, message)
end

local function chunk_rollback_record_id(base_record_id, task_id, chunk)
	local base = base_record_id or ("rollback:" .. task_id .. ":compat.structure.apply")
	return base .. ":chunk:" .. tostring(chunk.chunk_index)
end

function core.ai_import_ops.define_chunked_structure_apply_task(def)
	assert(type(def) == "table", "Chunked structure apply task definition must be a table")
	check_string(def.task_id, "task_id")
	check_string(def.agent_id, "agent_id")
	check_string(def.owner, "owner")
	local placements = normalize_structure_placements(def.placements)
	local max_writes = structure_budget_value(def,
		"max_node_writes_per_step", #placements)
	local total_writes = structure_budget_value(def,
		"max_node_writes_total", #placements)
	local total_mapblock_churn = structure_mapblock_churn(placements)
	local max_mapblock_churn_total = structure_budget_value(def,
		"max_mapblock_churn_total", total_mapblock_churn)
	local chunk_size = structure_budget_value(def, "chunk_size", max_writes)
	if chunk_size < 1 then
		chunk_size = 1
	end
	local chunks = chunk_structure_placements(placements, chunk_size)
	local has_rejected_payload = import_handoff_has_payload(def)
	local task_def = table.copy(def)
	task_def.source_reference = copy_source_reference(def.source_reference)
	task_def.placements = nil
	task_def.provenance = nil
	task_def.private_payload = nil
	task_def.asset_payload = nil
	task_def.payload = nil
	task_def.has_rejected_payload = has_rejected_payload
	task_def.rollback_policy = def.rollback_policy or "chunked"
	local steps = {}

	if #placements > total_writes then
		steps[1] = function(ctx)
			task_def.agent_id = ctx.agent_id
			task_def.owner = ctx.owner
			task_def.task_id = ctx.task_id
			task_def.chunk = {
				chunk_index = 0,
				chunk_count = #chunks,
				first_position_index = 0,
				position_count = math.min(#placements, chunk_size),
			}
			return blocked_structure_task_step(ctx, task_def, placements,
				"node_write_total_budget_exceeded",
				"Structure apply exceeds the total node-write budget.")
		end
	elseif total_mapblock_churn > max_mapblock_churn_total then
		steps[1] = function(ctx)
			task_def.agent_id = ctx.agent_id
			task_def.owner = ctx.owner
			task_def.task_id = ctx.task_id
			task_def.chunk = {
				chunk_index = 0,
				chunk_count = #chunks,
				first_position_index = 0,
				position_count = math.min(#placements, chunk_size),
			}
			return blocked_structure_task_step(ctx, task_def, placements,
				"mapblock_churn_budget_exceeded",
				"Structure apply exceeds the total mapblock-churn budget.")
		end
	else
		for index, chunk in ipairs(chunks) do
			steps[index] = function(ctx)
				task_def.agent_id = ctx.agent_id
				task_def.owner = ctx.owner
				task_def.task_id = ctx.task_id
				task_def.max_node_writes_per_step = max_writes
				task_def.chunk = chunk.chunk
				task_def.chunk_index = chunk.chunk.chunk_index
				task_def.chunk_count = chunk.chunk.chunk_count
				task_def.first_position_index = chunk.chunk.first_position_index
				task_def.max_mapblock_churn_total = max_mapblock_churn_total
				task_def.rollback_record_id = chunk_rollback_record_id(
					def.rollback_record_id, ctx.task_id, chunk.chunk)
				task_def.operation_label = def.operation_label
					or "compat.structure.apply.chunk"
				return core.ai_import_ops.apply_structure(chunk.placements, task_def)
			end
		end
	end

	return {
		task_id = def.task_id,
		agent_id = def.agent_id,
		owner = def.owner,
		label = def.label or "compat.structure.place",
		required_capabilities = {
			["import.assets"] = true,
			["world.place"] = true,
			["world.batch"] = true,
		},
		mutation_class = "compat_import",
		metadata = {
			report_id = def.report_id,
			action_index = def.action_index,
			placement_count = #placements,
			chunk_count = #chunks,
			chunk_size = chunk_size,
			staging = def.staging == true
				or (def.target_world and def.target_world.staging == true) or false,
			source_reference = task_def.source_reference,
		},
		budget = {
			max_steps_per_step = 1,
			max_node_writes_per_step = max_writes,
			max_wall_time_ms = def.max_wall_time_ms or 0,
		},
		steps = steps,
	}
end

function core.ai_import_ops.queue_chunked_structure_apply_task(def)
	return core.queue_ai_task(core.ai_import_ops.define_chunked_structure_apply_task(def))
end

local function task_summary_ref(task)
	return {
		task_id = task.task_id,
		label = task.label,
		status = task.status,
	}
end

local function structure_run_totals(run)
	local totals = {
		node_writes = 0,
		mapblock_churn = 0,
		rollback_records = 0,
		rollback_failures = 0,
		elapsed_us = 0,
		records = {},
	}
	if not run then
		return totals
	end
	for _, chunk in pairs(run.chunks or {}) do
		local metrics = chunk.metrics or {}
		totals.node_writes = totals.node_writes + (chunk.changed or 0)
		totals.mapblock_churn = totals.mapblock_churn
			+ (metrics.mapblock_churn or 0)
		totals.rollback_records = totals.rollback_records
			+ (metrics.rollback_records or 0)
		totals.rollback_failures = totals.rollback_failures
			+ (metrics.rollback_failures or 0)
		totals.elapsed_us = totals.elapsed_us + (metrics.elapsed_us or 0)
		if chunk.rollback_record_id then
			totals.records[#totals.records + 1] = {
				record_id = chunk.rollback_record_id,
				storage_ref = chunk.rollback_storage_ref,
				policy = "chunked",
				world_mutating = true,
				chunk = table.copy(chunk.chunk),
			}
		end
	end
	return totals
end

function core.ai_import_ops.build_apply_summary(options)
	options = options or {}
	local summary = {
		summary_version = 1,
		apply_id = options.apply_id or ("apply-runtime:" .. (options.report_id or "unknown")),
		report_id = options.report_id,
		status = "queued",
		approved_actions = table.copy(options.approved_actions or {}),
		queued_tasks = {},
		running_tasks = {},
		completed_tasks = {},
		blocked_tasks = {},
		mutation_cost_actual = {
			node_writes = 0,
			mapblock_churn = 0,
			media_files = 0,
			entity_definitions = 0,
			manual_review_items = 0,
			elapsed_us = 0,
		},
		rollback_records = {},
		audit_record_count = #core.get_ai_runtime_audit({}),
		operator_next_actions = {},
		safety = {
			assets_remain_operator_supplied = true,
			dry_run_report_unchanged = true,
			world_mutation_executed = false,
		},
	}
	local saw_active = false
	local saw_blocked = false
	local saw_completed = false
	for _, task_id in ipairs(options.task_ids or {}) do
		local task = core.get_ai_task(task_id)
		if task then
			local ref = task_summary_ref(task)
			local run = ai_import_structure_runs[task_id]
			local totals = structure_run_totals(run)
			if task.status == "queued" or task.status == "paused" then
				summary.queued_tasks[#summary.queued_tasks + 1] = ref
				saw_active = true
			elseif task.status == "running" then
				summary.running_tasks[#summary.running_tasks + 1] = ref
				saw_active = true
			elseif task.status == "completed" then
				summary.completed_tasks[#summary.completed_tasks + 1] = ref
				saw_completed = true
			elseif task.status == "blocked" or task.status == "unsafe"
					or task.status == "failed" then
				summary.blocked_tasks[#summary.blocked_tasks + 1] = ref
				saw_blocked = true
			end
			local result = task.last_result or {}
			local changed = totals.node_writes > 0 and totals.node_writes
				or tonumber(result.changed) or 0
			summary.mutation_cost_actual.node_writes =
				summary.mutation_cost_actual.node_writes + changed
			if changed > 0 then
				summary.safety.world_mutation_executed = true
			end
			if totals.mapblock_churn > 0 then
				summary.mutation_cost_actual.mapblock_churn =
					summary.mutation_cost_actual.mapblock_churn + totals.mapblock_churn
			elseif result.metrics and result.metrics.mapblock_churn then
				summary.mutation_cost_actual.mapblock_churn = math.max(
					summary.mutation_cost_actual.mapblock_churn,
					result.metrics.mapblock_churn)
			end
			for _, record in ipairs(totals.records) do
				summary.rollback_records[#summary.rollback_records + 1] = record
			end
			if #totals.records == 0 and result.rollback_record_id then
				summary.rollback_records[#summary.rollback_records + 1] = {
					record_id = result.rollback_record_id,
					policy = options.rollback_policy or "snapshot",
					world_mutating = true,
				}
			end
			if totals.elapsed_us > 0 then
				summary.mutation_cost_actual.elapsed_us =
					summary.mutation_cost_actual.elapsed_us + totals.elapsed_us
			end
		end
	end
	if saw_blocked then
		summary.status = "blocked"
	elseif saw_active then
		summary.status = #summary.running_tasks > 0 and "running" or "queued"
	elseif saw_completed then
		summary.status = "completed"
	else
		summary.status = "planned"
	end
	return summary
end

local function rollback_plan_record_ref(record, storage_ref)
	local positions = record.changed_positions or {}
	return {
		record_id = record.record_id,
		storage_ref = storage_ref or record.storage_ref,
		policy = record.policy,
		world_mutating = true,
		chunk = table.copy(record.chunk or {}),
		position_count = #positions,
		record = table.copy(record),
	}
end

function core.ai_import_ops.plan_structure_rollback(options)
	options = options or {}
	local result = make_action_result("ai_import.rollback_plan", options)
	result.rollback_records = {}
	result.rollback_plan = {
		will_mutate = false,
		chunks = {},
		missing_records = {},
	}
	result.metrics.planned_node_writes = 0
	result.metrics.mapblock_churn = 0
	result.metrics.rollback_records = 0
	local refs = table.copy(options.rollback_refs or {})
	if #refs == 0 and options.task_id and ai_import_structure_runs[options.task_id] then
		for _, chunk in pairs(ai_import_structure_runs[options.task_id].chunks or {}) do
			if chunk.rollback_storage_ref then
				refs[#refs + 1] = chunk.rollback_storage_ref
			end
		end
	end
	local supplied_records = options.rollback_records or {}
	for _, record in ipairs(supplied_records) do
		refs[#refs + 1] = {
			record = record,
			storage_ref = record.storage_ref,
		}
	end
	result.examined = #refs
	if #refs == 0 then
		result.skipped = 1
		return finish_runtime_gate_result(result, "blocked",
			"rollback_records_required",
			"Rollback planning requires rollback record references.")
	end
	for _, ref in ipairs(refs) do
		local storage_ref = ref
		local record = nil
		if type(ref) == "table" then
			record = ref.record
			storage_ref = ref.storage_ref or ref.ref or ref.record_id
		end
		if not record and storage_ref then
			record = core.ai_rollback_storage.inspect(tostring(storage_ref))
		end
		if type(record) ~= "table" then
			result.skipped = result.skipped + 1
			result.rollback_plan.missing_records[#result.rollback_plan.missing_records + 1] =
				tostring(storage_ref or "unknown")
		else
			local record_ref = rollback_plan_record_ref(record, storage_ref)
			result.rollback_records[#result.rollback_records + 1] = record_ref
			result.rollback_plan.chunks[#result.rollback_plan.chunks + 1] = record_ref
			result.metrics.planned_node_writes = result.metrics.planned_node_writes
				+ record_ref.position_count
			result.metrics.mapblock_churn = result.metrics.mapblock_churn
				+ structure_mapblock_churn(record.changed_positions or {})
		end
	end
	result.metrics.rollback_records = #result.rollback_records
	result.changed = 0
	if #result.rollback_records == 0 then
		return finish_runtime_gate_result(result, "blocked",
			"rollback_records_unavailable",
			"Rollback records could not be inspected.")
	end
	if result.skipped > 0 then
		return finish_runtime_gate_result(result, "partial",
			"rollback_plan_with_missing_records",
			"Rollback plan was created with missing record references.")
	end
	return finish_runtime_gate_result(result, "success", "rollback_plan_created",
		"Rollback plan was created without mutation.")
end

local import_rollback_required_capabilities = {
	"rollback.execute",
	"world.place",
	"world.batch",
}

local function import_rollback_result(options)
	local result = make_action_result("ai_import.rollback_execute", options)
	result.metrics.planned_node_writes = 0
	result.metrics.mapblock_churn = 0
	result.metrics.rollback_records = 0
	result.metrics.rollback_failures = 0
	return result
end

local function finish_import_rollback_result(result, status, reason, message)
	record_rollback_chunk_result(result)
	core.record_ai_runtime_audit({
		event_type = "import.rollback_execute",
		agent_id = result.agent_id,
		task_id = result.task_id,
		operation = result.operation,
		status = status,
		reason = reason,
		message = message,
		changed = result.changed,
		examined = result.examined,
		skipped = result.skipped,
		rollback_record_id = result.rollback_record_id,
		rollback_storage_ref = result.rollback_storage_ref,
		source_rollback_record_id = result.source_rollback_record_id,
		mutation_class = "compat_import",
	})
	return finish_runtime_gate_result(result, status, reason, message)
end

local function finalize_import_rollback_mutation_result(result, status, reason, message)
	result.operation = "ai_import.rollback_execute"
	record_rollback_chunk_result(result)
	core.record_ai_runtime_audit({
		event_type = "import.rollback_execute",
		agent_id = result.agent_id,
		task_id = result.task_id,
		operation = result.operation,
		status = status or result.status,
		reason = reason or result.reason,
		message = message or result.message,
		changed = result.changed,
		examined = result.examined,
		skipped = result.skipped,
		rollback_record_id = result.rollback_record_id,
		rollback_storage_ref = result.rollback_storage_ref,
		source_rollback_record_id = result.source_rollback_record_id,
		mutation_class = "compat_import",
	})
	return result
end

local function blocked_import_rollback_result(result, reason, message)
	if result.examined > 0 and result.skipped == 0 then
		result.skipped = result.examined
	end
	return finish_import_rollback_result(result, "blocked", reason, message)
end

local function import_rollback_capability_block(options, result)
	for _, capability in ipairs(import_rollback_required_capabilities) do
		local capability_result = core.check_agent_capability(options.agent_id, capability)
		if not capability_result.ok then
			result.skipped = result.examined > 0 and result.examined or 1
			return blocked_import_rollback_result(result, capability_result.reason,
				capability_result.message)
		end
	end
	local admin_result = core.check_agent_capability(options.agent_id, "admin.override")
	if not admin_result.ok then
		result.skipped = result.examined > 0 and result.examined or 1
		return blocked_import_rollback_result(result, "admin_override_required",
			"Compatibility rollback execution requires admin override.")
	end
	return nil
end

local function rollback_execution_record_id(base_record_id, task_id, chunk)
	local base = base_record_id or ("rollback:" .. task_id .. ":compat.structure.rollback")
	return base .. ":chunk:" .. tostring(chunk.chunk_index)
end

local function rollback_record_positions(record)
	local positions = {}
	for _, previous in ipairs(record.previous_nodes or {}) do
		positions[#positions + 1] = check_pos(previous.pos, "previous_nodes.pos")
	end
	return positions
end

local function rollback_record_placements(record)
	assert(type(record) == "table", "Rollback execution record must be a table")
	local previous_nodes = record.previous_nodes or {}
	assert(type(previous_nodes) == "table" and #previous_nodes > 0,
		"Rollback execution requires previous node records")
	local placements = {}
	for index, previous in ipairs(previous_nodes) do
		assert(type(previous) == "table",
			"Rollback previous node " .. index .. " must be a table")
		local node = previous.node or {}
		check_string(node.name, "previous_nodes[" .. index .. "].node.name")
		placements[#placements + 1] = {
			pos = check_pos(previous.pos, "previous_nodes[" .. index .. "].pos"),
			node_name = node.name,
			param1 = node.param1 or 0,
			param2 = node.param2 or 0,
		}
	end
	return placements
end

local function rollback_record_chunk(record, fallback_count)
	return normalize_structure_chunk({
		chunk = record.chunk or {},
	}, fallback_count)
end

local function rollback_plan_records(plan)
	local records = {}
	for _, record_ref in ipairs(plan.rollback_records or {}) do
		local record = record_ref.record
		if type(record) == "table" then
			records[#records + 1] = table.copy(record)
		end
	end
	return records
end

local function ordered_rollback_records(records, reverse_order)
	local ordered = table.copy(records)
	table.sort(ordered, function(a, b)
		local a_chunk = a.chunk or {}
		local b_chunk = b.chunk or {}
		local a_index = tonumber(a_chunk.chunk_index) or 0
		local b_index = tonumber(b_chunk.chunk_index) or 0
		if a_index == b_index then
			return tostring(a.record_id or "") < tostring(b.record_id or "")
		end
		if reverse_order == false then
			return a_index < b_index
		end
		return a_index > b_index
	end)
	return ordered
end

local function resolve_rollback_execution_records(def)
	if type(def.rollback_records) == "table" and #def.rollback_records > 0 then
		local records = {}
		for _, record in ipairs(def.rollback_records) do
			if type(record.record) == "table" then
				records[#records + 1] = table.copy(record.record)
			else
				records[#records + 1] = table.copy(record)
			end
		end
		return {
			ok = true,
			status = "success",
			records = records,
			missing_records = {},
		}
	end

	local plan = def.rollback_plan
	if type(plan) ~= "table" then
		local plan_options = table.copy(def)
		if def.source_task_id then
			plan_options.task_id = def.source_task_id
		elseif def.apply_task_id then
			plan_options.task_id = def.apply_task_id
		end
		plan = core.ai_import_ops.plan_structure_rollback(plan_options)
	end
	local records = rollback_plan_records(plan)
	local rollback_plan = plan.rollback_plan or {}
	return {
		ok = plan.ok == true and #records > 0 and #(rollback_plan.missing_records or {}) == 0,
		status = plan.status,
		reason = plan.reason,
		message = plan.message,
		records = records,
		missing_records = table.copy(rollback_plan.missing_records or {}),
	}
end

local function rollback_execution_totals(records)
	local totals = {
		node_writes = 0,
		mapblock_churn = 0,
	}
	for _, record in ipairs(records or {}) do
		local placements = rollback_record_placements(record)
		totals.node_writes = totals.node_writes + #placements
		totals.mapblock_churn = totals.mapblock_churn
			+ structure_mapblock_churn(placements)
	end
	return totals
end

function core.ai_import_ops.execute_structure_rollback(record, options)
	options = options or {}
	runtime_gate_options(options, "ai_import.rollback_execute")
	local placements = rollback_record_placements(record)
	local result = import_rollback_result(options)
	result.examined = #placements
	result.metrics.planned_node_writes = #placements
	result.metrics.mapblock_churn = structure_mapblock_churn(placements)
	result.source_rollback_record_id = record.record_id
	local chunk = rollback_record_chunk(record, #placements)
	annotate_structure_result(result, chunk)

	local capability_block = import_rollback_capability_block(options, result)
	if capability_block then
		return capability_block
	end
	if options.explicit_approval ~= true then
		return blocked_import_rollback_result(result, "approval_required",
			"Compatibility rollback execution requires explicit operator approval.")
	end
	local target_world = options.target_world or {}
	if options.staging ~= true and target_world.staging ~= true then
		return blocked_import_rollback_result(result, "staging_target_required",
			"Compatibility rollback execution requires a staging target world.")
	end
	if options.allow_mutation ~= true then
		return blocked_import_rollback_result(result, "rollback_mutation_not_enabled",
			"Compatibility rollback execution requires explicit allow_mutation.")
	end
	if not options.world_id or options.world_id == "" then
		return blocked_import_rollback_result(result, "rollback_metadata_unavailable",
			"Compatibility rollback execution requires a target world id before mutation.")
	end
	local rollback_policy = normalize_structure_rollback_policy(options.rollback_policy)
	if not rollback_policy then
		return blocked_import_rollback_result(result, "rollback_policy_not_mutating",
			"Compatibility rollback execution requires manifest, chunked, or snapshot rollback.")
	end
	local max_writes = structure_budget_value(options, "max_node_writes_per_step", #placements)
	if #placements > max_writes then
		return blocked_import_rollback_result(result, "node_write_budget_exceeded",
			"Compatibility rollback execution exceeds the per-step node-write budget.")
	end
	local max_mapblock_churn = structure_budget_value(options,
		"max_mapblock_churn_total", result.metrics.mapblock_churn)
	if result.metrics.mapblock_churn > max_mapblock_churn then
		return blocked_import_rollback_result(result, "mapblock_churn_budget_exceeded",
			"Compatibility rollback execution exceeds the mapblock-churn budget.")
	end

	local rollback_result = core.run_ai_world_mutation_with_rollback({
		record_id = options.rollback_record_id,
		policy = rollback_policy,
		world_id = options.world_id,
		task_id = options.task_id,
		agent_id = options.agent_id,
		owner_ref = options.owner or options.owner_ref,
		operation_label = options.operation_label or "compat.structure.rollback",
		mutation_class = "compat_import",
		bounds = options.bounds,
		positions = rollback_record_positions(record),
		chunk = chunk,
		get_node = options.get_node,
		persist_record = options.persist_record or options.persist_rollback_record,
	}, function(ctx)
		return core.ai_world_ops.batch_place(placements, {
			agent_id = ctx.agent_id,
			task_id = ctx.task_id,
			owner = options.owner or options.owner_ref,
			get_node = options.get_node,
			set_node = options.set_node,
			bounds = options.bounds,
			replace_existing = true,
			allow_hazards = options.allow_hazards == true,
			min_player_distance = options.min_player_distance,
			max_changes = #placements,
			sample_limit = options.sample_limit,
		})
	end)

	if not rollback_result.ok and rollback_result.reason == "rollback_metadata_unavailable" then
		result.metrics.rollback_failures = 1
		return blocked_import_rollback_result(result, "rollback_metadata_unavailable",
			rollback_result.message or "Rollback metadata is unavailable.")
	end
	annotate_structure_result(rollback_result, chunk)
	rollback_result.operation = "ai_import.rollback_execute"
	rollback_result.source_rollback_record_id = record.record_id
	if rollback_result.rollback_record_id then
		rollback_result.metrics = rollback_result.metrics or {}
		rollback_result.metrics.rollback_records = 1
		rollback_result.metrics.mapblock_churn = result.metrics.mapblock_churn
		rollback_result.metrics.planned_node_writes = result.metrics.planned_node_writes
	end
	return finalize_import_rollback_mutation_result(rollback_result,
		rollback_result.status, rollback_result.reason, rollback_result.message)
end

local function blocked_rollback_task_step(ctx, task_def, records, reason, message)
	local result = import_rollback_result({
		agent_id = ctx.agent_id,
		task_id = ctx.task_id,
	})
	local totals = rollback_execution_totals(records or {})
	result.examined = totals.node_writes
	result.metrics.planned_node_writes = totals.node_writes
	result.metrics.mapblock_churn = totals.mapblock_churn
	annotate_structure_result(result, normalize_structure_chunk(task_def,
		math.max(totals.node_writes, 1)))
	return blocked_import_rollback_result(result, reason, message)
end

function core.ai_import_ops.define_chunked_structure_rollback_task(def)
	assert(type(def) == "table", "Chunked structure rollback task definition must be a table")
	check_string(def.task_id, "task_id")
	check_string(def.agent_id, "agent_id")
	check_string(def.owner, "owner")
	local resolved = resolve_rollback_execution_records(def)
	local records = ordered_rollback_records(resolved.records or {},
		def.reverse_order ~= false)
	local totals = rollback_execution_totals(records)
	local total_writes = structure_budget_value(def,
		"max_node_writes_total", totals.node_writes)
	local max_mapblock_churn_total = structure_budget_value(def,
		"max_mapblock_churn_total", totals.mapblock_churn)
	local max_writes = structure_budget_value(def,
		"max_node_writes_per_step", totals.node_writes)
	local task_def = table.copy(def)
	task_def.rollback_policy = def.rollback_policy or "chunked"
	task_def.rollback_plan = nil
	task_def.rollback_records = nil
	task_def.rollback_refs = nil
	task_def.private_payload = nil
	task_def.asset_payload = nil
	task_def.payload = nil
	local steps = {}

	if not resolved.ok then
		steps[1] = function(ctx)
			task_def.agent_id = ctx.agent_id
			task_def.owner = ctx.owner
			task_def.task_id = ctx.task_id
			task_def.chunk = {
				chunk_index = 0,
				chunk_count = math.max(#records, 1),
				first_position_index = 0,
				position_count = math.max(totals.node_writes, 1),
			}
			return blocked_rollback_task_step(ctx, task_def, records,
				"rollback_records_unavailable",
				"Rollback execution requires complete inspected rollback records.")
		end
	elseif totals.node_writes > total_writes then
		steps[1] = function(ctx)
			task_def.agent_id = ctx.agent_id
			task_def.owner = ctx.owner
			task_def.task_id = ctx.task_id
			task_def.chunk = {
				chunk_index = 0,
				chunk_count = math.max(#records, 1),
				first_position_index = 0,
				position_count = math.max(totals.node_writes, 1),
			}
			return blocked_rollback_task_step(ctx, task_def, records,
				"node_write_total_budget_exceeded",
				"Compatibility rollback execution exceeds the total node-write budget.")
		end
	elseif totals.mapblock_churn > max_mapblock_churn_total then
		steps[1] = function(ctx)
			task_def.agent_id = ctx.agent_id
			task_def.owner = ctx.owner
			task_def.task_id = ctx.task_id
			task_def.chunk = {
				chunk_index = 0,
				chunk_count = math.max(#records, 1),
				first_position_index = 0,
				position_count = math.max(totals.node_writes, 1),
			}
			return blocked_rollback_task_step(ctx, task_def, records,
				"mapblock_churn_budget_exceeded",
				"Compatibility rollback execution exceeds the total mapblock-churn budget.")
		end
	else
		for index, record in ipairs(records) do
			steps[index] = function(ctx)
				local chunk = rollback_record_chunk(record,
					#(record.previous_nodes or {}))
				task_def.agent_id = ctx.agent_id
				task_def.owner = ctx.owner
				task_def.task_id = ctx.task_id
				task_def.max_node_writes_per_step = max_writes
				task_def.max_mapblock_churn_total = max_mapblock_churn_total
				task_def.chunk = chunk
				task_def.chunk_index = chunk.chunk_index
				task_def.chunk_count = chunk.chunk_count
				task_def.first_position_index = chunk.first_position_index
				task_def.rollback_record_id = rollback_execution_record_id(
					def.rollback_record_id, ctx.task_id, chunk)
				task_def.operation_label = def.operation_label
					or "compat.structure.rollback.chunk"
				return core.ai_import_ops.execute_structure_rollback(record, task_def)
			end
		end
	end

	return {
		task_id = def.task_id,
		agent_id = def.agent_id,
		owner = def.owner,
		label = def.label or "compat.structure.rollback",
		required_capabilities = {
			["rollback.execute"] = true,
			["admin.override"] = true,
			["world.place"] = true,
			["world.batch"] = true,
		},
		mutation_class = "compat_import",
		metadata = {
			source_task_id = def.source_task_id or def.apply_task_id,
			source_rollback_record_count = #records,
			placement_count = totals.node_writes,
			mapblock_churn = totals.mapblock_churn,
			reverse_order = def.reverse_order ~= false,
			staging = def.staging == true
				or (def.target_world and def.target_world.staging == true) or false,
		},
		budget = {
			max_steps_per_step = 1,
			max_node_writes_per_step = max_writes,
			max_wall_time_ms = def.max_wall_time_ms or 0,
		},
		steps = steps,
	}
end

function core.ai_import_ops.queue_chunked_structure_rollback_task(def)
	return core.queue_ai_task(core.ai_import_ops.define_chunked_structure_rollback_task(def))
end

function core.ai_import_ops.build_rollback_summary(options)
	options = options or {}
	local summary = {
		summary_version = 1,
		rollback_id = options.rollback_id or ("rollback-runtime:" .. (options.apply_id or "unknown")),
		status = "queued",
		queued_tasks = {},
		running_tasks = {},
		completed_tasks = {},
		blocked_tasks = {},
		mutation_cost_actual = {
			node_writes = 0,
			mapblock_churn = 0,
			elapsed_us = 0,
		},
		rollback_records = {},
		source_rollback_records = {},
		audit_record_count = #core.get_ai_runtime_audit({}),
		safety = {
			rollback_of_rollback_required = true,
			world_mutation_executed = false,
		},
	}
	local saw_active = false
	local saw_blocked = false
	local saw_completed = false
	for _, task_id in ipairs(options.task_ids or {}) do
		local task = core.get_ai_task(task_id)
		if task then
			local ref = task_summary_ref(task)
			local totals = structure_run_totals(ai_import_rollback_runs[task_id])
			if task.status == "queued" or task.status == "paused" then
				summary.queued_tasks[#summary.queued_tasks + 1] = ref
				saw_active = true
			elseif task.status == "running" then
				summary.running_tasks[#summary.running_tasks + 1] = ref
				saw_active = true
			elseif task.status == "completed" then
				summary.completed_tasks[#summary.completed_tasks + 1] = ref
				saw_completed = true
			elseif task.status == "blocked" or task.status == "unsafe"
					or task.status == "failed" then
				summary.blocked_tasks[#summary.blocked_tasks + 1] = ref
				saw_blocked = true
			end
			local result = task.last_result or {}
			local changed = totals.node_writes > 0 and totals.node_writes
				or tonumber(result.changed) or 0
			summary.mutation_cost_actual.node_writes =
				summary.mutation_cost_actual.node_writes + changed
			if changed > 0 then
				summary.safety.world_mutation_executed = true
			end
			if totals.mapblock_churn > 0 then
				summary.mutation_cost_actual.mapblock_churn =
					summary.mutation_cost_actual.mapblock_churn + totals.mapblock_churn
			elseif result.metrics and result.metrics.mapblock_churn then
				summary.mutation_cost_actual.mapblock_churn = math.max(
					summary.mutation_cost_actual.mapblock_churn,
					result.metrics.mapblock_churn)
			end
			for _, record in ipairs(totals.records) do
				summary.rollback_records[#summary.rollback_records + 1] = record
			end
			for _, chunk in pairs((ai_import_rollback_runs[task_id] or {}).chunks or {}) do
				if chunk.source_rollback_record_id then
					summary.source_rollback_records[#summary.source_rollback_records + 1] = {
						record_id = chunk.source_rollback_record_id,
						chunk = table.copy(chunk.chunk),
					}
				end
			end
			if totals.elapsed_us > 0 then
				summary.mutation_cost_actual.elapsed_us =
					summary.mutation_cost_actual.elapsed_us + totals.elapsed_us
			end
		end
	end
	if saw_blocked then
		summary.status = "blocked"
	elseif saw_active then
		summary.status = #summary.running_tasks > 0 and "running" or "queued"
	elseif saw_completed then
		summary.status = "completed"
	else
		summary.status = "planned"
	end
	return summary
end

local function world_get_node(pos, options)
	if options and options.get_node then
		return options.get_node(pos)
	end
	if core.get_node_or_nil then
		return core.get_node_or_nil(pos)
	end
	return core.get_node(pos)
end

local function world_set_node(pos, node, options)
	if options and options.set_node then
		return options.set_node(pos, node)
	end
	return core.set_node(pos, node)
end

local ai_owned_entities = {}
local ai_entity_counter = 0

local function entity_id_part(value)
	return tostring(value):gsub("[^%w._:-]", "_")
end

local function next_entity_id(agent_id, entity_name)
	ai_entity_counter = ai_entity_counter + 1
	return "entity:" .. entity_id_part(agent_id) .. ":"
		.. entity_id_part(entity_name) .. ":" .. ai_entity_counter
end

local function entity_distance(a, b)
	local dx = (a.x or 0) - (b.x or 0)
	local dy = (a.y or 0) - (b.y or 0)
	local dz = (a.z or 0) - (b.z or 0)
	return math.sqrt(dx * dx + dy * dy + dz * dz)
end

local function entity_ref_pos(ref, fallback)
	if ref and ref.get_pos then
		local ok, pos = pcall(ref.get_pos, ref)
		if ok and pos then
			return check_pos(pos, "entity.pos")
		end
	end
	return copy_pos(fallback)
end

local function count_owned_entities(entity_name, agent_id, owner)
	local count = 0
	for _, record in pairs(ai_owned_entities) do
		if (not entity_name or record.entity_name == entity_name)
				and (not agent_id or record.agent_id == agent_id)
				and (not owner or record.owner == owner) then
			count = count + 1
		end
	end
	return count
end

local function refresh_entity_count(entity_name)
	core.set_ai_runtime_entity_count(entity_name, count_owned_entities(entity_name))
end

local function public_entity(record)
	if not record then
		return nil
	end
	return {
		entity_id = record.entity_id,
		entity_name = record.entity_name,
		agent_id = record.agent_id,
		owner = record.owner,
		pos = entity_ref_pos(record.ref, record.pos),
	}
end

local function make_entity_result(operation, options)
	local result = make_action_result(operation, options)
	result.metrics.entity_count = 0
	result.metrics.distance = 0
	return result
end

local function entity_event_type(operation)
	if operation == "ai_entity.cleanup_owned" then
		return "entity.cleanup"
	end
	return operation:gsub("^ai_entity%.", "entity.")
end

local function finish_entity_result(result, status, reason, message)
	core.record_ai_runtime_audit({
		event_type = entity_event_type(result.operation),
		agent_id = result.agent_id,
		task_id = result.task_id,
		operation = result.operation,
		status = status,
		reason = reason,
		message = message,
		changed = result.changed,
		examined = result.examined,
		skipped = result.skipped,
	})
	return finish_action_result(result, status, reason, message)
end

local function entity_options(options, operation)
	assert(type(options) == "table", "Entity operation options must be a table")
	check_string(options.agent_id, "agent_id")
	local agent = core.get_ai_agent(options.agent_id)
	local owner = options.owner or options.owner_ref or agent and agent.owner
	if owner then
		check_string(owner, "owner")
	end
	return agent, owner, make_entity_result(operation, options)
end

local function entity_capability(options, operation, capability)
	local result = make_entity_result(operation, options)
	local capability_result = core.check_agent_capability(options.agent_id, capability)
	if capability_result.ok then
		return nil
	end
	result.skipped = 1
	return finish_entity_result(result, capability_result.status,
		capability_result.reason, capability_result.message)
end

local function entity_owner_check(record, owner, result)
	if not record then
		result.skipped = 1
		return finish_entity_result(result, "not_found", "unknown_entity",
			"Owned entity was not found.")
	end
	if record.owner ~= owner then
		result.skipped = 1
		return finish_entity_result(result, "blocked", "owner_mismatch",
			"Owned entity belongs to another owner.")
	end
	return nil
end

local function entity_limit(agent, options)
	local limit = options.max_entities or agent and agent.limits and agent.limits.max_entities
	if limit == nil then
		return nil
	end
	assert(type(limit) == "number" and limit >= 0, "Entity limit must be non-negative")
	return math.floor(limit)
end

local function entity_move_limit(agent, options)
	local limit = options.max_distance or agent and agent.limits
		and agent.limits.max_entity_move_distance
	if limit == nil then
		return nil
	end
	assert(type(limit) == "number" and limit >= 0,
		"Entity movement limit must be non-negative")
	return limit
end

function core.ai_entity_ops.spawn(entity_name, pos, options)
	check_string(entity_name, "entity_name")
	local spawn_pos = check_pos(pos, "pos")
	options = options or {}
	local agent, owner, result = entity_options(options, "ai_entity.spawn")
	local denied = entity_capability(options, "ai_entity.spawn", "entity.spawn")
	if denied then
		return denied
	end
	if not core.registered_entities[entity_name] then
		result.skipped = 1
		return finish_entity_result(result, "not_found", "unknown_entity_type",
			"Entity type is not registered.")
	end
	if not owner or not agent or agent.owner ~= owner then
		result.skipped = 1
		return finish_entity_result(result, "blocked", "owner_mismatch",
			"Agent owner does not match requested entity owner.")
	end

	local limit = entity_limit(agent, options)
	if limit and count_owned_entities(nil, options.agent_id, owner) >= limit then
		result.skipped = 1
		result.metrics.entity_count = count_owned_entities(entity_name)
		return finish_entity_result(result, "blocked", "entity_limit_exceeded",
			"Agent-owned entity limit was reached.")
	end

	local entity_id = options.entity_id or next_entity_id(options.agent_id, entity_name)
	check_string(entity_id, "entity_id")
	if ai_owned_entities[entity_id] then
		result.skipped = 1
		return finish_entity_result(result, "blocked", "duplicate_entity_id",
			"Owned entity id already exists.")
	end

	local spawn = options.spawn_entity or function(spawn_pos_arg, entity_name_arg, staticdata)
		if core.add_entity then
			return core.add_entity(spawn_pos_arg, entity_name_arg, staticdata)
		end
		return nil
	end
	local ok, ref = pcall(spawn, spawn_pos, entity_name, owner)
	if not ok or not ref then
		result.skipped = 1
		return finish_entity_result(result, "blocked", "entity_spawn_failed",
			"Entity could not be spawned.")
	end

	local record = {
		entity_id = entity_id,
		entity_name = entity_name,
		agent_id = options.agent_id,
		owner = owner,
		pos = spawn_pos,
		ref = ref,
	}
	ai_owned_entities[entity_id] = record
	refresh_entity_count(entity_name)
	increment_metric("entity_spawns")

	result.changed = 1
	result.examined = 1
	result.entity = public_entity(record)
	result.metrics.entity_count = count_owned_entities(entity_name)
	return finish_entity_result(result, "success", "entity_spawned",
		"Owned entity was spawned.")
end

function core.ai_entity_ops.inspect(entity_id, options)
	check_string(entity_id, "entity_id")
	options = options or {}
	local _, owner, result = entity_options(options, "ai_entity.inspect")
	local denied = entity_capability(options, "ai_entity.inspect", "entity.control")
	if denied then
		return denied
	end
	local record = ai_owned_entities[entity_id]
	local owner_error = entity_owner_check(record, owner, result)
	if owner_error then
		return owner_error
	end
	record.pos = entity_ref_pos(record.ref, record.pos)
	result.examined = 1
	result.entity = public_entity(record)
	result.metrics.entity_count = count_owned_entities(record.entity_name)
	return finish_entity_result(result, "success", "entity_inspected",
		"Owned entity was inspected.")
end

function core.ai_entity_ops.move(entity_id, pos, options)
	check_string(entity_id, "entity_id")
	local target_pos = check_pos(pos, "pos")
	options = options or {}
	local agent, owner, result = entity_options(options, "ai_entity.move")
	local denied = entity_capability(options, "ai_entity.move", "entity.control")
	if denied then
		return denied
	end
	local record = ai_owned_entities[entity_id]
	local owner_error = entity_owner_check(record, owner, result)
	if owner_error then
		return owner_error
	end

	local current_pos = entity_ref_pos(record.ref, record.pos)
	local distance = entity_distance(current_pos, target_pos)
	local limit = entity_move_limit(agent, options)
	if limit and distance > limit then
		result.skipped = 1
		result.metrics.distance = distance
		result.metrics.entity_count = count_owned_entities(record.entity_name)
		return finish_entity_result(result, "blocked", "movement_limit_exceeded",
			"Entity movement distance exceeded the configured limit.")
	end

	local ok, moved = true, true
	if record.ref and record.ref.set_pos then
		ok, moved = pcall(record.ref.set_pos, record.ref, target_pos)
	end
	if not ok or moved == false then
		result.skipped = 1
		return finish_entity_result(result, "blocked", "entity_move_failed",
			"Owned entity could not be moved.")
	end

	record.pos = target_pos
	result.changed = 1
	result.examined = 1
	result.entity = public_entity(record)
	result.metrics.distance = distance
	result.metrics.entity_count = count_owned_entities(record.entity_name)
	increment_metric("entity_moves")
	return finish_entity_result(result, "success", "entity_moved",
		"Owned entity was moved.")
end

local function remove_entity_record(record)
	if record.ref and record.ref.remove then
		pcall(record.ref.remove, record.ref)
	end
	ai_owned_entities[record.entity_id] = nil
	refresh_entity_count(record.entity_name)
end

function core.ai_entity_ops.cleanup(entity_id, options)
	check_string(entity_id, "entity_id")
	options = options or {}
	local _, owner, result = entity_options(options, "ai_entity.cleanup")
	local denied = entity_capability(options, "ai_entity.cleanup", "entity.control")
	if denied then
		return denied
	end
	local record = ai_owned_entities[entity_id]
	local owner_error = entity_owner_check(record, owner, result)
	if owner_error then
		return owner_error
	end
	remove_entity_record(record)
	result.changed = 1
	result.examined = 1
	result.metrics.entity_count = count_owned_entities(record.entity_name)
	increment_metric("entity_cleanups")
	return finish_entity_result(result, "success", "entity_cleaned_up",
		"Owned entity was cleaned up.")
end

function core.ai_entity_ops.cleanup_owned(options)
	options = options or {}
	local _, owner, result = entity_options(options, "ai_entity.cleanup_owned")
	local denied = entity_capability(options, "ai_entity.cleanup_owned", "entity.control")
	if denied then
		return denied
	end
	local removed_by_type = {}
	local to_remove = {}
	for entity_id, record in pairs(ai_owned_entities) do
		if record.agent_id == options.agent_id and record.owner == owner
				and (not options.entity_name or record.entity_name == options.entity_name) then
			to_remove[#to_remove + 1] = entity_id
		end
	end
	for _, entity_id in ipairs(to_remove) do
		local record = ai_owned_entities[entity_id]
		if record then
			removed_by_type[record.entity_name] = true
			remove_entity_record(record)
			result.changed = result.changed + 1
			result.examined = result.examined + 1
		end
	end
	for entity_name in pairs(removed_by_type) do
		refresh_entity_count(entity_name)
	end
	result.metrics.entity_count = options.entity_name and count_owned_entities(options.entity_name)
		or count_owned_entities()
	if result.changed == 0 then
		return finish_entity_result(result, "success", "no_owned_entities",
			"No owned entities matched cleanup.")
	end
	increment_metric("entity_cleanups", result.changed)
	return finish_entity_result(result, "success", "owned_entities_cleaned_up",
		"Owned entities were cleaned up.")
end

local function make_player_result(operation, options)
	local result = make_action_result(operation, options)
	result.metrics.distance = 0
	return result
end

local function player_event_type(operation)
	return operation:gsub("^ai_player%.", "player.")
end

local function finish_player_result(result, status, reason, message)
	core.record_ai_runtime_audit({
		event_type = player_event_type(result.operation),
		agent_id = result.agent_id,
		task_id = result.task_id,
		operation = result.operation,
		status = status,
		reason = reason,
		message = message,
		changed = result.changed,
		examined = result.examined,
		skipped = result.skipped,
	})
	return finish_action_result(result, status, reason, message)
end

local function player_options(options, operation)
	assert(type(options) == "table", "Player operation options must be a table")
	check_string(options.agent_id, "agent_id")
	local agent = core.get_ai_agent(options.agent_id)
	local owner = options.owner or options.owner_ref or agent and agent.owner
	if owner then
		check_string(owner, "owner")
	end
	return agent, owner, make_player_result(operation, options)
end

local function player_capability(options, operation, capability)
	local result = make_player_result(operation, options)
	local capability_result = core.check_agent_capability(options.agent_id, capability)
	if capability_result.ok then
		return nil
	end
	result.skipped = 1
	return finish_player_result(result, capability_result.status,
		capability_result.reason, capability_result.message)
end

local function public_player(player, name)
	return {
		name = name,
		pos = player:get_pos(),
	}
end

local function get_player_ref(player_name, options, result)
	local get_player = options.get_player_by_name or core.get_player_by_name
	local player = get_player and get_player(player_name) or nil
	if not player then
		result.skipped = 1
		return nil, finish_player_result(result, "not_found", "unknown_player",
			"Player was not found.")
	end
	if not player.get_pos or not player.set_pos then
		result.skipped = 1
		return nil, finish_player_result(result, "blocked", "invalid_player_ref",
			"Player reference cannot be moved.")
	end
	if player.get_attach and player:get_attach() then
		result.skipped = 1
		return nil, finish_player_result(result, "blocked", "player_attached",
			"Attached players cannot be teleported.")
	end
	return player, nil
end

local function player_move_limit(agent, options)
	local limit = options.max_distance or agent and agent.limits
		and agent.limits.max_player_teleport_distance
	if limit == nil then
		return nil
	end
	assert(type(limit) == "number" and limit >= 0,
		"Player teleport distance limit must be non-negative")
	return limit
end

local function teleport_player_ref(player_name, target_pos, options, operation, capability)
	local agent, _, result = player_options(options, operation)
	local denied = player_capability(options, operation, capability)
	if denied then
		return denied
	end
	local player, player_error = get_player_ref(player_name, options, result)
	if player_error then
		return player_error
	end
	local current_pos = check_pos(player:get_pos(), "player.pos")
	local distance = entity_distance(current_pos, target_pos)
	local limit = player_move_limit(agent, options)
	if limit and distance > limit then
		result.skipped = 1
		result.metrics.distance = distance
		return finish_player_result(result, "blocked", "movement_limit_exceeded",
			"Player teleport distance exceeded the configured limit.")
	end

	local ok, moved = pcall(player.set_pos, player, target_pos)
	if not ok or moved == false then
		result.skipped = 1
		return finish_player_result(result, "blocked", "player_move_failed",
			"Player could not be teleported.")
	end

	result.changed = 1
	result.examined = 1
	result.player = public_player(player, player_name)
	result.metrics.distance = distance
	increment_metric("player_teleports")
	return finish_player_result(result, "success", "player_teleported",
		"Player was teleported.")
end

function core.ai_player_ops.teleport_self(pos, options)
	local target_pos = check_pos(pos, "pos")
	options = options or {}
	local agent, owner, result = player_options(options, "ai_player.teleport_self")
	local player_name = options.player_name or owner
	if not player_name then
		result.skipped = 1
		return finish_player_result(result, "blocked", "missing_player_name",
			"Player name is required.")
	end
	check_string(player_name, "player_name")
	if not agent or agent.owner ~= player_name or owner ~= player_name then
		result.skipped = 1
		return finish_player_result(result, "blocked", "owner_mismatch",
			"Self teleport requires the agent owner to match the player.")
	end
	return teleport_player_ref(player_name, target_pos, options,
		"ai_player.teleport_self", "player.teleport.self")
end

function core.ai_player_ops.teleport_player(player_name, pos, options)
	check_string(player_name, "player_name")
	local target_pos = check_pos(pos, "pos")
	options = options or {}
	local _, _, result = player_options(options, "ai_player.teleport_player")
	local admin_check = core.check_agent_capability(options.agent_id, "admin.override")
	if not admin_check.ok then
		result.skipped = 1
		return finish_player_result(result, "permission_denied", "admin_override_required",
			"Teleporting other players requires admin override.")
	end
	return teleport_player_ref(player_name, target_pos, options,
		"ai_player.teleport_player", "player.teleport.other")
end

local function defend_limit(agent, options)
	local limit = options.max_distance or agent and agent.limits
		and agent.limits.max_defend_distance
	if limit == nil then
		return nil
	end
	assert(type(limit) == "number" and limit >= 0,
		"Defend distance limit must be non-negative")
	return limit
end

local function hostile_pos(hostile)
	if hostile.pos then
		return check_pos(hostile.pos, "hostile.pos")
	end
	if hostile.ref and hostile.ref.get_pos then
		local ok, pos = pcall(hostile.ref.get_pos, hostile.ref)
		if ok and pos then
			return check_pos(pos, "hostile.pos")
		end
	end
	return nil
end

local function public_hostile(hostile, pos)
	return {
		entity_id = hostile.entity_id,
		entity_name = hostile.entity_name,
		pos = pos and copy_pos(pos) or nil,
	}
end

function core.ai_player_ops.defend(player_name, options)
	check_string(player_name, "player_name")
	options = options or {}
	local agent, owner, result = player_options(options, "ai_player.defend")
	local denied = player_capability(options, "ai_player.defend", "combat.defend")
	if denied then
		return denied
	end
	if not agent or agent.owner ~= player_name or owner ~= player_name then
		result.skipped = 1
		return finish_player_result(result, "blocked", "owner_mismatch",
			"Defend requires the agent owner to match the player.")
	end
	local player, player_error = get_player_ref(player_name, options, result)
	if player_error then
		return player_error
	end
	local player_pos = check_pos(player:get_pos(), "player.pos")
	local hostiles = options.hostiles
	if not hostiles and options.find_hostiles then
		hostiles = options.find_hostiles(player, options)
	end
	hostiles = hostiles or {}
	assert(type(hostiles) == "table", "Field 'hostiles' must be a table")

	local limit = defend_limit(agent, options)
	local nearest = nil
	local nearest_pos = nil
	local nearest_distance = nil
	for _, hostile in ipairs(hostiles) do
		if hostile.hostile ~= false then
			result.examined = result.examined + 1
			local pos = hostile_pos(hostile)
			if pos then
				local distance = entity_distance(player_pos, pos)
				if (not limit or distance <= limit)
						and (not nearest_distance or distance < nearest_distance) then
					nearest = hostile
					nearest_pos = pos
					nearest_distance = distance
				end
			end
		end
	end
	if not nearest then
		result.skipped = result.examined
		return finish_player_result(result, "blocked", "no_hostile_target",
			"No hostile target was found within the defend limit.")
	end

	local attack = options.attack_entity or function(hostile)
		if hostile.ref and hostile.ref.punch then
			return hostile.ref:punch(player)
		end
		return false
	end
	local ok, attacked = pcall(attack, nearest, player, options)
	if not ok or attacked == false then
		result.skipped = 1
		result.metrics.distance = nearest_distance
		result.target = public_hostile(nearest, nearest_pos)
		return finish_player_result(result, "blocked", "attack_failed",
			"Defensive action could not be applied to the target.")
	end

	result.changed = 1
	result.target = public_hostile(nearest, nearest_pos)
	result.metrics.distance = nearest_distance
	increment_metric("combat_defends")
	return finish_player_result(result, "success", "hostile_target_defended",
		"Hostile target was defended against.")
end

local ai_rollback_record_counter = 0
local rollback_policies = {
	manifest = true,
	snapshot = true,
	chunked = true,
}
local rollback_mutation_classes = {
	repair = true,
	build = true,
	compat_import = true,
}

local function rollback_pos(pos, field)
	local copied = check_pos(pos, field)
	return {
		x = math.floor(copied.x),
		y = math.floor(copied.y),
		z = math.floor(copied.z),
	}
end

local function normalize_rollback_positions(value)
	assert(type(value) == "table" and #value > 0,
		"Field 'positions' must be a non-empty table")
	local positions = {}
	for i, pos in ipairs(value) do
		positions[i] = rollback_pos(pos, "positions[" .. i .. "]")
	end
	return positions
end

local function rollback_bounds_from_positions(positions)
	local minp = table.copy(positions[1])
	local maxp = table.copy(positions[1])
	for _, pos in ipairs(positions) do
		minp.x = math.min(minp.x, pos.x)
		minp.y = math.min(minp.y, pos.y)
		minp.z = math.min(minp.z, pos.z)
		maxp.x = math.max(maxp.x, pos.x)
		maxp.y = math.max(maxp.y, pos.y)
		maxp.z = math.max(maxp.z, pos.z)
	end
	return {
		min = minp,
		max = maxp,
	}
end

local function normalize_rollback_bounds(bounds, positions)
	bounds = bounds or rollback_bounds_from_positions(positions)
	assert(type(bounds) == "table", "Field 'bounds' must be a table")
	return {
		min = rollback_pos(bounds.min, "bounds.min"),
		max = rollback_pos(bounds.max, "bounds.max"),
	}
end

local function normalize_rollback_chunk(chunk, position_count)
	chunk = chunk or {}
	local result = {
		chunk_index = chunk.chunk_index or 0,
		chunk_count = chunk.chunk_count or 1,
		first_position_index = chunk.first_position_index or 0,
		position_count = chunk.position_count or position_count,
	}
	for key, value in pairs(result) do
		assert(type(value) == "number" and value >= 0,
			"Field 'chunk." .. key .. "' must be a non-negative number")
		result[key] = math.floor(value)
	end
	assert(result.chunk_count >= 1, "Field 'chunk.chunk_count' must be at least 1")
	assert(result.position_count >= 1, "Field 'chunk.position_count' must be at least 1")
	return result
end

local function rollback_node(node)
	node = node or {
		name = "air",
		param1 = 0,
		param2 = 0,
	}
	local result = {
		name = node.name or "air",
		param1 = node.param1 or 0,
		param2 = node.param2 or 0,
	}
	if node.metadata_hash then
		result.metadata_hash = node.metadata_hash
	end
	return result
end

local function rollback_timestamp()
	if os and os.date then
		return os.date("!%Y-%m-%dT%H:%M:%SZ")
	end
	return tostring(audit_timestamp())
end

local function rollback_id_part(value)
	return tostring(value):gsub("[^%w._:-]", "_")
end

local function rollback_filename_part(value)
	return tostring(value):gsub("[^%w._-]", "_")
end

local function next_rollback_record_id(task_id, operation_label)
	ai_rollback_record_counter = ai_rollback_record_counter + 1
	return "rollback:" .. rollback_id_part(task_id) .. ":"
		.. rollback_id_part(operation_label) .. ":" .. ai_rollback_record_counter
end

local ai_rollback_storage_options = {
	enabled = false,
}

function core.ai_rollback_storage.configure(options)
	if options == nil then
		ai_rollback_storage_options = {
			enabled = false,
		}
		return {
			ok = true,
			status = "success",
			reason = "rollback_storage_disabled",
		}
	end
	assert(type(options) == "table", "Rollback storage options must be a table")
	if options.persist_record ~= nil then
		assert(type(options.persist_record) == "function",
			"Rollback storage persist_record must be a function")
	end
	if options.inspect_record ~= nil then
		assert(type(options.inspect_record) == "function",
			"Rollback storage inspect_record must be a function")
	end
	if options.prune_records ~= nil then
		assert(type(options.prune_records) == "function",
			"Rollback storage prune_records must be a function")
	end
	ai_rollback_storage_options = {
		enabled = options.enabled ~= false,
		persist_record = options.persist_record,
		inspect_record = options.inspect_record,
		prune_records = options.prune_records,
	}
	return {
		ok = true,
		status = "success",
		reason = ai_rollback_storage_options.enabled
			and "rollback_storage_enabled" or "rollback_storage_disabled",
	}
end

local function default_rollback_storage_ref(record)
	return "rollback://world/" .. record.record_id
end

local function default_rollback_storage_path(record)
	if not core.get_worldpath then
		return nil
	end
	local worldpath = core.get_worldpath()
	if not worldpath or worldpath == "" then
		return nil
	end
	return worldpath .. DIR_DELIM .. "ai_rollback_"
		.. rollback_filename_part(record.record_id) .. ".json"
end

local function default_persist_rollback_record(record)
	if not core.safe_file_write or not core.write_json then
		return nil
	end
	local path = default_rollback_storage_path(record)
	if not path then
		return nil
	end
	local payload = core.write_json(record, true)
	if not payload then
		return nil
	end
	local ok = core.safe_file_write(path, payload)
	if ok == false then
		return nil
	end
	return {
		ok = true,
		storage_ref = default_rollback_storage_ref(record),
	}
end

local function configured_rollback_persist(record)
	if ai_rollback_storage_options.persist_record then
		return ai_rollback_storage_options.persist_record(record)
	end
	return default_persist_rollback_record(record)
end

local function active_configured_rollback_persist()
	if not ai_rollback_storage_options.enabled then
		return nil
	end
	return configured_rollback_persist
end

function core.ai_rollback_storage.inspect(storage_ref)
	if not ai_rollback_storage_options.enabled
			or not ai_rollback_storage_options.inspect_record then
		return nil
	end
	return ai_rollback_storage_options.inspect_record(storage_ref)
end

function core.ai_rollback_storage.prune(options)
	if not ai_rollback_storage_options.enabled
			or not ai_rollback_storage_options.prune_records then
		return {
			removed = 0,
			reason = "rollback_storage_prune_unavailable",
		}
	end
	local result = ai_rollback_storage_options.prune_records(options or {})
	if type(result) == "table" then
		return result
	end
	return {
		removed = result or 0,
	}
end

local function make_rollback_result(def, position_count)
	local result = make_action_result("ai_rollback.write_record", {
		agent_id = def and def.agent_id or nil,
		task_id = def and def.task_id or nil,
	})
	result.examined = position_count or 0
	return result
end

local function record_rollback_audit(def, status, reason, message, record, storage_ref)
	local chunk = record and record.chunk or def and def.chunk or {}
	core.record_ai_runtime_audit({
		event_type = "rollback.record",
		agent_id = def and def.agent_id or nil,
		task_id = def and def.task_id or nil,
		actor = def and (def.owner_ref or def.owner) or nil,
		operation = def and def.operation_label or nil,
		status = status,
		reason = reason,
		message = message,
		rollback_record_id = record and record.record_id or def and def.record_id or nil,
		rollback_storage_ref = storage_ref,
		mutation_class = def and def.mutation_class or nil,
		chunk_index = chunk.chunk_index,
		chunk_count = chunk.chunk_count,
		changed = record and #(record.changed_positions or {}) or 0,
	})
end

local function rollback_unavailable(def, position_count, message)
	increment_metric("rollback_record_failures")
	record_rollback_audit(def, "blocked", "rollback_metadata_unavailable",
		message or "Rollback metadata is unavailable.", nil, nil)
	return finish_action_result(make_rollback_result(def, position_count),
		"blocked", "rollback_metadata_unavailable",
		message or "Rollback metadata is unavailable.")
end

function core.write_ai_rollback_record(def)
	assert(type(def) == "table", "Rollback record definition must be a table")
	local raw_positions = def.positions or def.changed_positions
	local positions = normalize_rollback_positions(raw_positions)
	local persist_record = def.persist_record or def.persist_rollback_record
		or active_configured_rollback_persist()
	if type(persist_record) ~= "function" then
		return rollback_unavailable(def, #positions,
			"Rollback persistence callback is required before mutation.")
	end

	local policy = def.policy or "snapshot"
	assert(rollback_policies[policy], "Rollback policy must be manifest, snapshot, or chunked")
	check_string(def.world_id, "world_id")
	check_string(def.task_id, "task_id")
	check_string(def.agent_id, "agent_id")
	local owner_ref = def.owner_ref or def.owner
	check_string(owner_ref, "owner_ref")
	check_string(def.operation_label, "operation_label")
	assert(rollback_mutation_classes[def.mutation_class],
		"Rollback mutation_class must be repair, build, or compat_import")

	local previous_nodes = {}
	for i, pos in ipairs(positions) do
		local ok, node = pcall(world_get_node, pos, def)
		if not ok or not node then
			return rollback_unavailable(def, #positions,
				"Previous node state could not be captured.")
		end
		previous_nodes[i] = {
			pos = table.copy(pos),
			node = rollback_node(node),
		}
	end

	local record = {
		schema_version = 1,
		record_id = def.record_id or next_rollback_record_id(def.task_id, def.operation_label),
		policy = policy,
		world_id = def.world_id,
		task_id = def.task_id,
		agent_id = def.agent_id,
		owner_ref = owner_ref,
		operation_label = def.operation_label,
		mutation_class = def.mutation_class,
		bounds = normalize_rollback_bounds(def.bounds, positions),
		changed_positions = positions,
		previous_nodes = previous_nodes,
		chunk = normalize_rollback_chunk(def.chunk, #positions),
		created_at = def.created_at or rollback_timestamp(),
	}
	check_string(record.record_id, "record_id")

	local ok, persisted = pcall(persist_record, record)
	if not ok or persisted == nil or persisted == false
			or (type(persisted) == "table" and persisted.ok == false) then
		return rollback_unavailable(def, #positions,
			"Rollback metadata could not be persisted.")
	end

	local storage_ref
	if type(persisted) == "table" then
		storage_ref = persisted.storage_ref or persisted.ref or persisted.record_id
	else
		storage_ref = persisted
	end
	if storage_ref ~= nil then
		storage_ref = tostring(storage_ref)
		record.storage_ref = storage_ref
	end

	increment_metric("rollback_records_written")
	record_rollback_audit(def, "success", "rollback_record_written",
		"Rollback record was written.", record, storage_ref)

	local result = make_rollback_result(def, #positions)
	result.rollback_record_id = record.record_id
	result.rollback_storage_ref = storage_ref
	result.record = record
	return finish_action_result(result, "success", "rollback_record_written",
		"Rollback record was written.")
end

function core.run_ai_world_mutation_with_rollback(def, mutate)
	assert(type(mutate) == "function", "Mutation callback must be a function")
	local rollback = core.write_ai_rollback_record(def)
	if not rollback.ok then
		return rollback
	end
	local ok, result = pcall(mutate, {
		task_id = def.task_id,
		agent_id = def.agent_id,
		owner_ref = def.owner_ref or def.owner,
		rollback_record = rollback.record,
		rollback_record_id = rollback.rollback_record_id,
		rollback_storage_ref = rollback.rollback_storage_ref,
	})
	if not ok then
		local failed = make_action_result("ai_rollback.mutation", def)
		failed.rollback_record_id = rollback.rollback_record_id
		failed.rollback_storage_ref = rollback.rollback_storage_ref
		return finish_action_result(failed, "failed", "mutation_error", tostring(result))
	end
	if type(result) ~= "table" then
		result = {
			ok = true,
			status = "success",
		}
	end
	result.rollback_record_id = rollback.rollback_record_id
	result.rollback_storage_ref = rollback.rollback_storage_ref
	return result
end

local function registered_node(node_name)
	return core.registered_nodes and core.registered_nodes[node_name] or nil
end

local function node_group_value(node_name, group)
	local def = registered_node(node_name)
	local groups = def and def.groups or nil
	return groups and (groups[group] or 0) or 0
end

local function is_buildable_target(node)
	if not node or node.name == "air" then
		return true
	end
	local def = registered_node(node.name)
	return def and def.buildable_to == true
end

local function is_unbreakable_node(node)
	if not node or node.name == "air" then
		return false
	end
	local def = registered_node(node.name)
	return def and (def.diggable == false
		or node_group_value(node.name, "unbreakable") > 0)
end

local function is_hazard_node(node)
	if not node then
		return false
	end
	local def = registered_node(node.name)
	if not def then
		return false
	end
	return (def.liquidtype and def.liquidtype ~= "none")
		or node_group_value(node.name, "hazard") > 0
		or node_group_value(node.name, "lava") > 0
		or node_group_value(node.name, "fire") > 0
end

local function inside_bounds(pos, bounds)
	if not bounds then
		return true
	end
	local minp = bounds.min and check_pos(bounds.min, "bounds.min") or nil
	local maxp = bounds.max and check_pos(bounds.max, "bounds.max") or nil
	if minp and (pos.x < minp.x or pos.y < minp.y or pos.z < minp.z) then
		return false
	end
	if maxp and (pos.x > maxp.x or pos.y > maxp.y or pos.z > maxp.z) then
		return false
	end
	return true
end

local function is_position_protected(pos, options)
	if not core.is_protected then
		return false
	end
	local ok, protected = pcall(core.is_protected, pos, actor_name(options))
	return ok and protected == true
end

local function is_player_near(pos, options)
	if not options or not options.min_player_distance
			or options.min_player_distance <= 0 or not core.get_connected_players then
		return false
	end
	for _, player in ipairs(core.get_connected_players()) do
		if player and player.get_pos then
			local player_pos = player:get_pos()
			if player_pos and vector.distance(pos, player_pos) < options.min_player_distance then
				return true
			end
		end
	end
	return false
end

local function validate_common_write(pos, options)
	if not inside_bounds(pos, options and options.bounds or nil) then
		return false, "blocked", "out_of_bounds", "Position is outside allowed bounds."
	end
	if is_position_protected(pos, options) then
		return false, "blocked", "protected_area", "Position is protected."
	end
	if is_player_near(pos, options) then
		return false, "unsafe", "player_proximity", "A player is too close."
	end
	return true
end

local function validate_place_target(pos, node_name, options)
	if type(node_name) ~= "string" or node_name == "" or not registered_node(node_name) then
		return false, "not_found", "unknown_node", "Target node is not registered."
	end
	local ok, status, reason, message = validate_common_write(pos, options)
	if not ok then
		return false, status, reason, message
	end
	local current = world_get_node(pos, options)
	if not current then
		return false, "not_found", "node_unloaded", "Position is not loaded."
	end
	if is_unbreakable_node(current) then
		return false, "blocked", "unbreakable_node", "Existing node is unbreakable.", current
	end
	if not (options and options.allow_hazards) and is_hazard_node(current) then
		return false, "unsafe", "hazard_node", "Existing node is hazardous.", current
	end
	if not (options and options.replace_existing) and not is_buildable_target(current) then
		return false, "blocked", "target_not_empty", "Target position is occupied.", current
	end
	return true, nil, nil, nil, current
end

local function validate_remove_target(pos, options)
	local ok, status, reason, message = validate_common_write(pos, options)
	if not ok then
		return false, status, reason, message
	end
	local current = world_get_node(pos, options)
	if not current then
		return false, "not_found", "node_unloaded", "Position is not loaded."
	end
	if current.name == "air" then
		return false, "not_found", "node_not_found", "Position is already air.", current
	end
	if is_unbreakable_node(current) then
		return false, "blocked", "unbreakable_node", "Existing node is unbreakable.", current
	end
	if not (options and options.allow_hazards) and is_hazard_node(current) then
		return false, "unsafe", "hazard_node", "Existing node is hazardous.", current
	end
	return true, nil, nil, nil, current
end

local function blocked_action(result, options, status, reason, message, pos, node)
	result.skipped = result.skipped + 1
	add_action_sample(result, options, pos, node, reason, message)
	return finish_action_result(result, status, reason, message)
end

local function set_node_success(result, pos, node_name, options)
	world_set_node(pos, { name = node_name, param1 = 0, param2 = 0 }, options)
	result.changed = result.changed + 1
	result.metrics.node_writes = result.metrics.node_writes + 1
	return finish_action_result(result, "success", "changed", "Node was changed.")
end

function core.ai_world_ops.place_node(pos, node_name, options)
	options = options or {}
	pos = check_pos(pos, "pos")
	local result = make_action_result("ai_world.place_node", options)
	result.examined = 1

	local ok, status, reason, message, current = validate_place_target(pos, node_name, options)
	if not ok then
		return blocked_action(result, options, status, reason, message, pos, current)
	end
	return set_node_success(result, pos, node_name, options)
end

function core.ai_world_ops.remove_node(pos, options)
	options = options or {}
	pos = check_pos(pos, "pos")
	local result = make_action_result("ai_world.remove_node", options)
	result.examined = 1

	local ok, status, reason, message, current = validate_remove_target(pos, options)
	if not ok then
		return blocked_action(result, options, status, reason, message, pos, current)
	end
	return set_node_success(result, pos, "air", options)
end

function core.ai_world_ops.replace_node(pos, expected, replacement, options)
	options = options or {}
	pos = check_pos(pos, "pos")
	local result = make_action_result("ai_world.replace_node", options)
	result.examined = 1

	if type(replacement) ~= "string" or replacement == "" or not registered_node(replacement) then
		return blocked_action(result, options, "not_found", "unknown_node",
			"Replacement node is not registered.", pos)
	end
	local ok, status, reason, message = validate_common_write(pos, options)
	if not ok then
		return blocked_action(result, options, status, reason, message, pos)
	end
	local current = world_get_node(pos, options)
	if not current then
		return blocked_action(result, options, "not_found", "node_unloaded",
			"Position is not loaded.", pos)
	end
	if current.name ~= expected then
		return blocked_action(result, options, "not_found", "expected_node_mismatch",
			"Existing node does not match the expected node.", pos, current)
	end
	if is_unbreakable_node(current) then
		return blocked_action(result, options, "blocked", "unbreakable_node",
			"Existing node is unbreakable.", pos, current)
	end
	if not options.allow_hazards and is_hazard_node(current) then
		return blocked_action(result, options, "unsafe", "hazard_node",
			"Existing node is hazardous.", pos, current)
	end
	return set_node_success(result, pos, replacement, options)
end

local function filters_match(node, filters)
	if not filters or not filters.node_names then
		return true
	end
	if filters.node_names[node.name] ~= nil then
		return filters.node_names[node.name] == true
	end
	for _, node_name in ipairs(filters.node_names) do
		if node.name == node_name then
			return true
		end
	end
	return false
end

function core.ai_world_ops.inspect_area(center, radius, filters, options)
	options = options or {}
	center = check_pos(center, "center")
	radius = radius or 0
	assert(type(radius) == "number" and radius >= 0, "Field 'radius' must be non-negative")
	radius = math.floor(radius)
	local result = make_action_result("ai_world.inspect_area", options)

	for x = center.x - radius, center.x + radius do
		for y = center.y - radius, center.y + radius do
			for z = center.z - radius, center.z + radius do
				local pos = { x = x, y = y, z = z }
				result.examined = result.examined + 1
				if not inside_bounds(pos, options.bounds) then
					result.skipped = result.skipped + 1
					add_action_sample(result, options, pos, nil, "out_of_bounds",
						"Position is outside allowed bounds.")
				elseif is_position_protected(pos, options) then
					result.skipped = result.skipped + 1
					add_action_sample(result, options, pos, nil, "protected_area",
						"Position is protected.")
				else
					local node = world_get_node(pos, options)
					if node and filters_match(node, filters) then
						add_action_sample(result, options, pos, node, "matched",
							"Node matched inspect filters.")
					elseif not node then
						result.skipped = result.skipped + 1
						add_action_sample(result, options, pos, nil, "node_unloaded",
							"Position is not loaded.")
					end
				end
			end
		end
	end

	if result.skipped > 0 and result.examined == result.skipped then
		return finish_action_result(result, "blocked", "all_positions_skipped",
			"All inspected positions were skipped.")
	end
	if result.skipped > 0 then
		return finish_action_result(result, "partial", "some_positions_skipped",
			"Some inspected positions were skipped.")
	end
	return finish_action_result(result, "success", "inspected", "Area was inspected.")
end

function core.ai_world_ops.find_safe_position(anchor, constraints)
	constraints = constraints or {}
	anchor = check_pos(anchor, "anchor")
	local result = make_action_result("ai_world.find_safe_position", constraints)
	local offsets = constraints.offsets or {
		{ x = 0, y = 0, z = 0 },
	}

	for _, offset in ipairs(offsets) do
		local pos = {
			x = anchor.x + (offset.x or 0),
			y = anchor.y + (offset.y or 0),
			z = anchor.z + (offset.z or 0),
		}
		result.examined = result.examined + 1
		local ok, status, reason, message, current =
			validate_place_target(pos, "air", constraints)
		if ok and is_buildable_target(current) then
			result.pos = copy_pos(pos)
			return finish_action_result(result, "success", "safe_position_found",
				"Safe position was found.")
		end
		result.skipped = result.skipped + 1
		add_action_sample(result, constraints, pos, current, reason or status, message)
	end

	return finish_action_result(result, "blocked", "no_safe_position",
		"No safe position matched the constraints.")
end

function core.ai_world_ops.batch_place(placements, options)
	options = options or {}
	assert(type(placements) == "table", "Field 'placements' must be a table")
	local result = make_action_result("ai_world.batch_place", options)
	local max_changes = options.max_changes or #placements

	for _, placement in ipairs(placements) do
		local pos = check_pos(placement.pos, "placement.pos")
		local node = placement.node or {}
		local node_name = placement.node_name or placement.name or node.name
		result.examined = result.examined + 1
		local ok, status, reason, message, current =
			validate_place_target(pos, node_name, options)
		if not ok then
			result.skipped = result.skipped + 1
			add_action_sample(result, options, pos, current, reason, message)
		elseif result.changed >= max_changes then
			result.skipped = result.skipped + 1
			add_action_sample(result, options, pos, current, "max_changes_reached",
				"Batch change budget was reached.")
		else
			world_set_node(pos, {
				name = node_name,
				param1 = placement.param1 or node.param1 or 0,
				param2 = placement.param2 or node.param2 or 0,
			}, options)
			result.changed = result.changed + 1
			result.metrics.node_writes = result.metrics.node_writes + 1
		end
	end

	if result.changed > 0 and result.skipped > 0 then
		return finish_action_result(result, "partial", "some_operations_skipped",
			"Some batch placements were skipped.")
	end
	if result.changed > 0 then
		return finish_action_result(result, "success", "changed", "Batch placement changed nodes.")
	end
	return finish_action_result(result, "blocked", "all_operations_skipped",
		"All batch placements were skipped.")
end

function core.ai_world_ops.batch_remove(positions, options)
	options = options or {}
	assert(type(positions) == "table", "Field 'positions' must be a table")
	local result = make_action_result("ai_world.batch_remove", options)
	local max_changes = options.max_changes or #positions

	for _, raw_pos in ipairs(positions) do
		local pos = check_pos(raw_pos, "pos")
		result.examined = result.examined + 1
		local ok, status, reason, message, current = validate_remove_target(pos, options)
		if not ok then
			result.skipped = result.skipped + 1
			add_action_sample(result, options, pos, current, reason, message)
		elseif result.changed >= max_changes then
			result.skipped = result.skipped + 1
			add_action_sample(result, options, pos, current, "max_changes_reached",
				"Batch change budget was reached.")
		else
			world_set_node(pos, { name = "air", param1 = 0, param2 = 0 }, options)
			result.changed = result.changed + 1
			result.metrics.node_writes = result.metrics.node_writes + 1
		end
	end

	if result.changed > 0 and result.skipped > 0 then
		return finish_action_result(result, "partial", "some_operations_skipped",
			"Some batch removals were skipped.")
	end
	if result.changed > 0 then
		return finish_action_result(result, "success", "changed", "Batch removal changed nodes.")
	end
	return finish_action_result(result, "blocked", "all_operations_skipped",
		"All batch removals were skipped.")
end

function core.register_ai_agent(def)
	local agent = normalize_agent(def)
	core.registered_ai_agents[agent.agent_id] = agent
	return table.copy(agent)
end

function core.get_ai_agent(agent_id)
	local agent = core.registered_ai_agents[agent_id]
	if not agent then
		return nil
	end
	return table.copy(agent)
end

function core.agent_has_capability(agent_id, capability)
	local agent = core.registered_ai_agents[agent_id]
	return agent ~= nil and agent.capabilities[capability] == true
end

function core.check_agent_capability(agent_id, capability)
	local agent = core.registered_ai_agents[agent_id]
	if not agent then
		return make_capability_result(agent_id, capability, false, "not_found",
			"unknown_agent", "Agent is not registered.")
	end
	if agent.state ~= "enabled" then
		return make_capability_result(agent_id, capability, false, "blocked",
			"agent_" .. agent.state, "Agent state is '" .. agent.state .. "'.")
	end
	if not agent.capabilities[capability] then
		return make_capability_result(agent_id, capability, false, "permission_denied",
			"missing_capability", "Agent does not have capability '" .. capability .. "'.")
	end
	if capability == "admin.override" then
		core.record_ai_runtime_audit({
			event_type = "capability.admin_override",
			agent_id = agent_id,
			operation = "capability.check",
			status = "success",
			reason = "admin_override_granted",
			message = "Agent has admin override; audit is required.",
		})
		return make_capability_result(agent_id, capability, true, "success",
			"admin_override_granted", "Agent has admin override; audit is required.")
	end
	return make_capability_result(agent_id, capability, true, "success",
		"capability_granted", "Agent capability is granted.")
end

function core.queue_ai_task(def)
	assert(type(def) == "table", "Task definition must be a table")
	check_string(def.task_id, "task_id")
	check_string(def.agent_id, "agent_id")
	check_string(def.owner, "owner")
	check_string(def.label, "label")
	assert(core.registered_ai_agents[def.agent_id], "Task agent must be registered")
	assert(core.registered_ai_tasks[def.task_id] == nil,
		"Task '" .. def.task_id .. "' already exists")

	local steps = normalize_steps(def.steps)
	local now = core.get_us_time and core.get_us_time() or 0
	local task = {
		task_id = def.task_id,
		agent_id = def.agent_id,
		owner = def.owner,
		label = def.label,
		status = "queued",
		created_at = now,
		updated_at = now,
		budget = normalize_budget(def.budget),
		progress = {
			current = 0,
			total = #steps,
		},
		steps = steps,
		last_result = {},
	}

	core.registered_ai_tasks[task.task_id] = task
	ai_task_queue[#ai_task_queue + 1] = task.task_id
	increment_metric("tasks_queued")
	return public_task(task)
end

function core.get_ai_task(task_id)
	return public_task(core.registered_ai_tasks[task_id])
end

function core.cancel_ai_task(task_id, actor)
	local task = core.registered_ai_tasks[task_id]
	if not task then
		return make_task_result(task_id, false, "not_found", "unknown_task",
			"Task is not registered.")
	end
	if task.status == "completed" then
		return make_task_result(task_id, false, "completed", "task_completed",
			"Task is already completed.")
	end
	if task.status == "cancelled" then
		return make_task_result(task_id, true, "cancelled", "task_cancelled",
			"Task is already cancelled.")
	end
	if actor ~= task.owner and actor ~= "admin"
			and not core.agent_has_capability(actor, "admin.override") then
		return make_task_result(task_id, false, "permission_denied",
			"cancel_denied", "Only the task owner or an admin can cancel this task.")
	end

	task.status = "cancelled"
	task.updated_at = core.get_us_time and core.get_us_time() or task.updated_at
	task.last_result = make_task_result(task_id, true, "cancelled",
		"task_cancelled", "Task was cancelled.")
	increment_metric("tasks_cancelled")
	record_task_duration(task, "cancelled")
	record_task_audit("task.cancelled", task, {
		status = "cancelled",
		reason = "task_cancelled",
		message = "Task was cancelled.",
	})
	return table.copy(task.last_result)
end

local function resume_paused_ai_tasks()
	for _, task in pairs(core.registered_ai_tasks) do
		if task.status == "paused" then
			task.status = task.progress.current > 0 and "running" or "queued"
		end
	end
end

function core.set_ai_task_queue_paused(paused, reason)
	ai_task_queue_paused = paused == true
	ai_task_queue_pause_reason = ai_task_queue_paused and (reason or "paused") or nil
	if not ai_task_queue_paused then
		resume_paused_ai_tasks()
	end
end

function core.set_ai_task_queue_lag_monitor(options)
	if options == nil then
		ai_task_queue_lag_monitor = nil
		ai_task_queue_auto_paused = false
		if not ai_task_queue_paused then
			resume_paused_ai_tasks()
		end
		return
	end
	assert(type(options) == "table", "Lag monitor options must be a table")
	assert(type(options.max_lag_ms) == "number" and options.max_lag_ms >= 0,
		"Field 'max_lag_ms' must be a non-negative number")
	if options.get_lag_ms ~= nil then
		assert(type(options.get_lag_ms) == "function",
			"Field 'get_lag_ms' must be a function")
	end
	ai_task_queue_lag_monitor = {
		max_lag_ms = options.max_lag_ms,
		get_lag_ms = options.get_lag_ms,
	}
end

local function default_lag_sample_ms()
	if core.get_server_max_lag then
		local lag_seconds = core.get_server_max_lag()
		if type(lag_seconds) == "number" then
			return lag_seconds * 1000
		end
	end
	return 0
end

local function sample_ai_task_queue_lag()
	if not ai_task_queue_lag_monitor then
		return nil
	end
	local sampler = ai_task_queue_lag_monitor.get_lag_ms
	local value = sampler and sampler() or default_lag_sample_ms()
	assert(type(value) == "number" and value >= 0,
		"Lag monitor sample must be a non-negative number")
	return value
end

local function pause_active_ai_tasks()
	for _, task_id in ipairs(ai_task_queue) do
		local task = core.registered_ai_tasks[task_id]
		if task and (task.status == "queued" or task.status == "running") then
			task.status = "paused"
		end
	end
end

function core.step_ai_tasks()
	if ai_task_queue_paused then
		pause_active_ai_tasks()
		return {
			ran = 0,
			remaining = count_active_tasks(),
			paused = true,
			reason = ai_task_queue_pause_reason,
		}
	end

	local current_lag_ms = sample_ai_task_queue_lag()
	if current_lag_ms and current_lag_ms > ai_task_queue_lag_monitor.max_lag_ms then
		pause_active_ai_tasks()
		ai_task_queue_auto_paused = true
		increment_metric("task_lag_pauses")
		return {
			ran = 0,
			remaining = count_active_tasks(),
			paused = true,
			reason = "lag_threshold_exceeded",
			current_lag_ms = current_lag_ms,
			max_lag_ms = ai_task_queue_lag_monitor.max_lag_ms,
		}
	elseif ai_task_queue_auto_paused then
		ai_task_queue_auto_paused = false
		resume_paused_ai_tasks()
	end

	local ran = 0
	for _, task_id in ipairs(ai_task_queue) do
		local task = core.registered_ai_tasks[task_id]
		if task and (task.status == "queued" or task.status == "running") then
			local was_queued = task.status == "queued"
			task.status = "running"
			if was_queued and not task.started_at then
				task.started_at = core.get_us_time and core.get_us_time() or 0
				record_task_audit("task.started", task, {
					status = "running",
					reason = "task_started",
					message = "Task started running.",
				})
			end
			local budget = task.budget.max_steps_per_step
			while budget > 0 and task.progress.current < task.progress.total do
				local step = task.steps[task.progress.current + 1]
				local ok, result = pcall(step, {
					task_id = task.task_id,
					agent_id = task.agent_id,
					owner = task.owner,
					budget = table.copy(task.budget),
					progress = table.copy(task.progress),
				})
				ran = ran + 1
				increment_metric("task_steps_run")
				budget = budget - 1
				task.updated_at = core.get_us_time and core.get_us_time() or task.updated_at
				if not ok then
					task.status = "failed"
					task.last_result = make_task_result(task.task_id, false, "failed",
						"step_error", tostring(result))
					increment_metric("tasks_failed")
					record_task_duration(task, "failed")
					record_task_audit("task.failed", task, {
						status = "failed",
						reason = "step_error",
						message = tostring(result),
					})
					break
				end
				task.progress.current = task.progress.current + 1
				task.last_result = type(result) == "table" and table.copy(result) or {
					ok = true,
					status = "success",
				}
				local reported_changed = tonumber(task.last_result.changed) or 0
				increment_metric("node_writes", reported_changed)
				increment_metric("task_reported_node_writes", reported_changed)
				if task.budget.max_node_writes_per_step > 0
						and (task.last_result.changed or 0) > task.budget.max_node_writes_per_step then
					task.status = "unsafe"
					task.last_result = make_task_result(task.task_id, false, "unsafe",
						"node_write_budget_exceeded",
						"Task step exceeded its node-write budget.")
					increment_metric("tasks_unsafe")
					record_task_duration(task, "unsafe")
					record_task_audit("task.unsafe", task, {
						status = "unsafe",
						reason = "node_write_budget_exceeded",
						message = "Task step exceeded its node-write budget.",
						changed = reported_changed,
					})
					break
				end
				if task.budget.max_wall_time_ms > 0 and task.started_at then
					local now = core.get_us_time and core.get_us_time() or task.updated_at
					local elapsed_us = now - task.started_at
					if elapsed_us > task.budget.max_wall_time_ms * 1000 then
						task.status = "unsafe"
						task.last_result = make_task_result(task.task_id, false, "unsafe",
							"wall_clock_budget_exceeded",
							"Task exceeded its wall-clock budget.")
						task.last_result.metrics = {
							elapsed_us = elapsed_us,
							max_wall_time_ms = task.budget.max_wall_time_ms,
						}
						increment_metric("tasks_unsafe")
						increment_metric("task_wall_clock_budget_exceeded")
						record_task_duration(task, "unsafe")
						record_task_audit("task.unsafe", task, {
							status = "unsafe",
							reason = "wall_clock_budget_exceeded",
							message = "Task exceeded its wall-clock budget.",
							changed = reported_changed,
						})
						break
					end
				end
				if task.last_result.status == "blocked" or task.last_result.status == "unsafe"
						or task.last_result.status == "failed" then
					task.status = task.last_result.status
					if task.status == "blocked" then
						increment_metric("tasks_blocked")
					elseif task.status == "unsafe" then
						increment_metric("tasks_unsafe")
					elseif task.status == "failed" then
						increment_metric("tasks_failed")
					end
					record_task_duration(task, task.status)
					record_task_audit("task." .. task.status, task, {
						status = task.status,
						reason = task.last_result.reason,
						message = task.last_result.message,
						changed = reported_changed,
						skipped = task.last_result.skipped,
						})
						break
					end
				end
				if task.status == "running" and task.progress.current >= task.progress.total then
				task.status = "completed"
				increment_metric("tasks_completed")
				record_task_duration(task, "completed")
				record_task_audit("task.completed", task, {
					status = "completed",
					reason = "task_completed",
					message = "Task completed.",
				})
			end
			break
		end
	end

	return {
		ran = ran,
		remaining = count_active_tasks(),
		paused = false,
	}
end
