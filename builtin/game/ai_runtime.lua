core.registered_ai_agents = {}
core.registered_ai_tasks = {}
core.ai_world_ops = {}

local ai_task_queue = {}
local ai_task_queue_paused = false
local ai_task_queue_pause_reason = nil

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
	assert(type(budget.max_steps_per_step) == "number" and budget.max_steps_per_step >= 1,
		"Field 'budget.max_steps_per_step' must be a positive number")
	assert(type(budget.max_node_writes_per_step) == "number" and budget.max_node_writes_per_step >= 0,
		"Field 'budget.max_node_writes_per_step' must be a non-negative number")
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

function core.format_ai_runtime_metrics(metrics)
	metrics = metrics or core.get_ai_runtime_operator_metrics()
	return "AI runtime: queue=" .. metric_number(metrics, "queue_length")
		.. " tasks=" .. format_task_status_counts(metrics.task_status_counts)
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

local function next_rollback_record_id(task_id, operation_label)
	ai_rollback_record_counter = ai_rollback_record_counter + 1
	return "rollback:" .. rollback_id_part(task_id) .. ":"
		.. rollback_id_part(operation_label) .. ":" .. ai_rollback_record_counter
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
	if type(def.persist_record) ~= "function" then
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

	local ok, persisted = pcall(def.persist_record, record)
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
		local node_name = placement.node_name or placement.name
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
			world_set_node(pos, { name = node_name, param1 = 0, param2 = 0 }, options)
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
	record_task_audit("task.cancelled", task, {
		status = "cancelled",
		reason = "task_cancelled",
		message = "Task was cancelled.",
	})
	return table.copy(task.last_result)
end

function core.set_ai_task_queue_paused(paused, reason)
	ai_task_queue_paused = paused == true
	ai_task_queue_pause_reason = ai_task_queue_paused and (reason or "paused") or nil
	if not ai_task_queue_paused then
		for _, task in pairs(core.registered_ai_tasks) do
			if task.status == "paused" then
				task.status = task.progress.current > 0 and "running" or "queued"
			end
		end
	end
end

function core.step_ai_tasks()
	if ai_task_queue_paused then
		for _, task_id in ipairs(ai_task_queue) do
			local task = core.registered_ai_tasks[task_id]
			if task and (task.status == "queued" or task.status == "running") then
				task.status = "paused"
			end
		end
		return {
			ran = 0,
			remaining = count_active_tasks(),
			paused = true,
			reason = ai_task_queue_pause_reason,
		}
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
					record_task_audit("task.unsafe", task, {
						status = "unsafe",
						reason = "node_write_budget_exceeded",
						message = "Task step exceeded its node-write budget.",
						changed = reported_changed,
					})
					break
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
