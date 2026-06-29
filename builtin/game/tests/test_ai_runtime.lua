local function assert_result(result, ok, status, reason)
	assert(type(result) == "table")
	assert(result.ok == ok)
	assert(result.status == status)
	assert(result.reason == reason)
	assert(result.operation == "capability.check")
end

local function assert_action_result(result, ok, status, operation)
	assert(type(result) == "table")
	assert(result.ok == ok)
	assert(result.status == status)
	assert(result.operation == operation)
	assert(result.agent_id == "nova:emma")
	assert(result.changed ~= nil)
	assert(result.examined ~= nil)
	assert(result.skipped ~= nil)
	assert(type(result.samples) == "table")
	assert(type(result.metrics) == "table")
end

local agent = core.register_ai_agent({
	agent_id = "nova:emma",
	display_name = "Nova - Emma",
	owner = "emma",
	plugin = "nova_agent",
	capabilities = {
		["world.read"] = true,
		["world.place"] = true,
	},
	limits = {
		max_nodes_per_step = 32,
	},
})

assert(agent.agent_id == "nova:emma")
assert(agent.display_name == "Nova - Emma")
assert(agent.owner == "emma")
assert(agent.plugin == "nova_agent")
assert(agent.state == "enabled")
assert(agent.capabilities["world.read"] == true)
assert(agent.limits.max_nodes_per_step == 32)

local stored = core.get_ai_agent("nova:emma")
assert(stored.agent_id == "nova:emma")
assert(stored.capabilities["world.place"] == true)

stored.capabilities["world.dig"] = true
assert(core.agent_has_capability("nova:emma", "world.dig") == false)
assert(core.agent_has_capability("nova:emma", "world.read") == true)

local allowed = core.check_agent_capability("nova:emma", "world.read")
assert_result(allowed, true, "success", "capability_granted")
assert(allowed.agent_id == "nova:emma")
assert(allowed.audit_required == false)

local denied = core.check_agent_capability("nova:emma", "world.dig")
assert_result(denied, false, "permission_denied", "missing_capability")
assert(denied.agent_id == "nova:emma")
assert(denied.capability == "world.dig")

core.register_ai_agent({
	agent_id = "server:ops",
	display_name = "Ops Agent",
	owner = "server",
	plugin = "agent_core",
	capabilities = {
		["admin.override"] = true,
	},
})

local override = core.check_agent_capability("server:ops", "admin.override")
assert_result(override, true, "success", "admin_override_granted")
assert(override.audit_required == true)

local missing = core.check_agent_capability("missing", "world.read")
assert_result(missing, false, "not_found", "unknown_agent")
assert(missing.agent_id == "missing")

core.register_ai_agent({
	agent_id = "nova:disabled",
	display_name = "Disabled Nova",
	owner = "wills",
	plugin = "nova_agent",
	state = "disabled",
	capabilities = {
		["world.read"] = true,
	},
})

local disabled = core.check_agent_capability("nova:disabled", "world.read")
assert_result(disabled, false, "blocked", "agent_disabled")

local task_events = {}
local task = core.queue_ai_task({
	task_id = "task:lights",
	agent_id = "nova:emma",
	owner = "emma",
	label = "place lights",
	budget = {
		max_steps_per_step = 1,
		max_node_writes_per_step = 4,
	},
	steps = {
		function(ctx)
			table.insert(task_events, "step1:" .. ctx.task_id .. ":" .. ctx.agent_id)
			return { ok = true, status = "success", changed = 1 }
		end,
		function(ctx)
			table.insert(task_events, "step2")
			return { ok = true, status = "success", changed = 2 }
		end,
	},
})

assert(task.task_id == "task:lights")
assert(task.agent_id == "nova:emma")
assert(task.owner == "emma")
assert(task.label == "place lights")
assert(task.status == "queued")
assert(task.progress.current == 0)
assert(task.progress.total == 2)

local first_run = core.step_ai_tasks()
assert(first_run.ran == 1)
assert(first_run.remaining == 1)
assert(task_events[1] == "step1:task:lights:nova:emma")

local running = core.get_ai_task("task:lights")
assert(running.status == "running")
assert(running.progress.current == 1)
assert(running.last_result.changed == 1)

local second_run = core.step_ai_tasks()
assert(second_run.ran == 1)
assert(second_run.remaining == 0)
assert(task_events[2] == "step2")

local completed = core.get_ai_task("task:lights")
assert(completed.status == "completed")
assert(completed.progress.current == 2)
assert(completed.last_result.changed == 2)

core.queue_ai_task({
	task_id = "task:queued-cancel",
	agent_id = "nova:emma",
	owner = "emma",
	label = "queued cancel",
	steps = {
		function()
			error("cancelled queued task must not run")
		end,
	},
})

local queued_cancel = core.cancel_ai_task("task:queued-cancel", "emma")
assert(queued_cancel.ok == true)
assert(queued_cancel.status == "cancelled")
assert(core.step_ai_tasks().ran == 0)
assert(core.get_ai_task("task:queued-cancel").status == "cancelled")

local cancelled_events = {}
core.queue_ai_task({
	task_id = "task:running-cancel",
	agent_id = "nova:emma",
	owner = "emma",
	label = "running cancel",
	budget = {
		max_steps_per_step = 1,
	},
	steps = {
		function()
			table.insert(cancelled_events, "first")
			return { ok = true, status = "success" }
		end,
		function()
			table.insert(cancelled_events, "second")
			return { ok = true, status = "success" }
		end,
	},
})

core.step_ai_tasks()
local running_cancel = core.cancel_ai_task("task:running-cancel", "server:ops")
assert(running_cancel.ok == true)
assert(running_cancel.status == "cancelled")
assert(core.step_ai_tasks().ran == 0)
assert(#cancelled_events == 1)

do
	local retry_attempts = 0
	core.queue_ai_task({
		task_id = "task:retry-live",
		agent_id = "nova:emma",
		owner = "emma",
		label = "retry live task",
		steps = {
			function()
				retry_attempts = retry_attempts + 1
				if retry_attempts == 1 then
					return {
						ok = false,
						status = "blocked",
						reason = "temporary_block",
						message = "Temporary block for retry contract.",
					}
				end
				return { ok = true, status = "success", changed = 0 }
			end,
		},
	})
	core.step_ai_tasks()
	assert(core.get_ai_task("task:retry-live").status == "blocked")
	local retry_denied = core.retry_ai_task("task:retry-live", "nova:disabled")
	assert(retry_denied.ok == false)
	assert(retry_denied.status == "permission_denied")
	local retry_result = core.retry_ai_task("task:retry-live", "emma")
	assert(retry_result.ok == true)
	assert(retry_result.status == "queued")
	assert(retry_result.reason == "task_retried")
	local retry_queued = core.get_ai_task("task:retry-live")
	assert(retry_queued.status == "queued")
	assert(retry_queued.progress.current == 0)
	assert(retry_queued.retry_count == 1)
	core.step_ai_tasks()
	local retry_completed = core.get_ai_task("task:retry-live")
	assert(retry_completed.status == "completed")
	assert(retry_attempts == 2)
	local retry_completed_again = core.retry_ai_task("task:retry-live", "emma")
	assert(retry_completed_again.ok == false)
	assert(retry_completed_again.status == "completed")
end

local lag_events = {}
core.queue_ai_task({
	task_id = "task:lag-paused",
	agent_id = "nova:emma",
	owner = "emma",
	label = "lag paused",
	steps = {
		function()
			table.insert(lag_events, "ran")
			return { ok = true, status = "success" }
		end,
	},
})
core.set_ai_task_queue_paused(true, "lag_high")
local paused = core.step_ai_tasks()
assert(paused.ran == 0)
assert(paused.paused == true)
assert(paused.reason == "lag_high")
assert(core.get_ai_task("task:lag-paused").status == "paused")
assert(#lag_events == 0)
core.set_ai_task_queue_paused(false)
assert(core.step_ai_tasks().ran == 1)
assert(#lag_events == 1)
assert(core.get_ai_task("task:lag-paused").status == "completed")

local automatic_lag_events = {}
local lag_samples = { 75, 10 }
core.set_ai_task_queue_lag_monitor({
	max_lag_ms = 50,
	get_lag_ms = function()
		local sample = lag_samples[1] or 0
		table.remove(lag_samples, 1)
		return sample
	end,
})
core.queue_ai_task({
	task_id = "task:auto-lag-paused",
	agent_id = "nova:emma",
	owner = "emma",
	label = "automatic lag paused",
	steps = {
		function()
			table.insert(automatic_lag_events, "ran")
			return { ok = true, status = "success" }
		end,
	},
})
local auto_paused = core.step_ai_tasks()
assert(auto_paused.ran == 0)
assert(auto_paused.paused == true)
assert(auto_paused.reason == "lag_threshold_exceeded")
assert(auto_paused.current_lag_ms == 75)
assert(auto_paused.max_lag_ms == 50)
assert(core.get_ai_task("task:auto-lag-paused").status == "paused")
assert(#automatic_lag_events == 0)
local auto_resumed = core.step_ai_tasks()
assert(auto_resumed.ran == 1)
assert(auto_resumed.paused == false)
assert(#automatic_lag_events == 1)
assert(core.get_ai_task("task:auto-lag-paused").status == "completed")
core.set_ai_task_queue_lag_monitor(nil)

core.queue_ai_task({
	task_id = "task:write-budget",
	agent_id = "nova:emma",
	owner = "emma",
	label = "write budget",
	budget = {
		max_node_writes_per_step = 1,
	},
	steps = {
		function()
			return { ok = true, status = "success", changed = 2 }
		end,
		function()
			error("unsafe task must not continue")
		end,
	},
})

local write_budget = core.step_ai_tasks()
assert(write_budget.ran == 1)
local unsafe_task = core.get_ai_task("task:write-budget")
assert(unsafe_task.status == "unsafe")
assert(unsafe_task.last_result.ok == false)
assert(unsafe_task.last_result.reason == "node_write_budget_exceeded")

local old_get_us_time = core.get_us_time
local fake_us_time = 1000000
core.get_us_time = function()
	return fake_us_time
end
core.queue_ai_task({
	task_id = "task:wall-clock-budget",
	agent_id = "nova:emma",
	owner = "emma",
	label = "wall clock budget",
	budget = {
		max_steps_per_step = 2,
		max_wall_time_ms = 2,
	},
	steps = {
		function()
			fake_us_time = fake_us_time + 3000
			return { ok = true, status = "success", changed = 0 }
		end,
		function()
			error("wall-clock budgeted task must not continue")
		end,
	},
})
local wall_clock_budget = core.step_ai_tasks()
assert(wall_clock_budget.ran == 1)
local wall_clock_task = core.get_ai_task("task:wall-clock-budget")
assert(wall_clock_task.status == "unsafe")
assert(wall_clock_task.last_result.ok == false)
assert(wall_clock_task.last_result.reason == "wall_clock_budget_exceeded")
assert(wall_clock_task.last_result.metrics.elapsed_us == 3000)
local duration_snapshot = core.get_ai_runtime_operator_metrics().task_duration_us
assert(type(duration_snapshot) == "table")
assert(duration_snapshot.count >= 1)
assert(duration_snapshot.total >= 3000)
assert(duration_snapshot.max >= 3000)
assert(duration_snapshot.average >= 1)
assert(type(duration_snapshot.by_status) == "table")
assert(duration_snapshot.by_status.unsafe.count >= 1)
assert(duration_snapshot.by_status.unsafe.max >= 3000)
core.get_us_time = old_get_us_time

core.register_node(":ai_runtime_test:stone", {
	description = "AI Runtime Test Stone",
	groups = { cracky = 1 },
})

core.register_node(":ai_runtime_test:unbreakable", {
	description = "AI Runtime Test Unbreakable",
	groups = { unbreakable = 1 },
})

core.register_node(":ai_runtime_test:hazard", {
	description = "AI Runtime Test Hazard",
	groups = { hazard = 1 },
})

local function test_pos(x)
	return { x = x, y = 32, z = 4100 }
end

local test_world = {}

local function test_world_key(pos)
	return pos.x .. ":" .. pos.y .. ":" .. pos.z
end

local function set_test_node(pos, node)
	test_world[test_world_key(pos)] = {
		name = node.name,
		param1 = node.param1 or 0,
		param2 = node.param2 or 0,
	}
	return true
end

local function get_test_node(pos)
	return table.copy(test_world[test_world_key(pos)] or {
		name = "air",
		param1 = 0,
		param2 = 0,
	})
end

local rollback_capture_pos = test_pos(4090)
set_test_node(rollback_capture_pos, {
	name = "ai_runtime_test:stone",
	param1 = 12,
	param2 = 34,
})
local persisted_rollback_records = {}
local rollback_record_result = core.write_ai_rollback_record({
	record_id = "rollback:test:capture",
	policy = "snapshot",
	world_id = "test-world",
	task_id = "task:rollback-capture",
	agent_id = "nova:emma",
	owner_ref = "emma",
	operation_label = "repair.remove_hazard",
	mutation_class = "repair",
	bounds = {
		min = test_pos(4080),
		max = test_pos(4100),
	},
	positions = {
		rollback_capture_pos,
	},
	get_node = get_test_node,
	persist_record = function(record)
		persisted_rollback_records[#persisted_rollback_records + 1] = record
		return {
			ok = true,
			storage_ref = "rollback-store:" .. record.record_id,
		}
	end,
	private_payload = {
		prompt = "must not be retained",
		asset_payload = "must not be retained",
	},
})
assert(rollback_record_result.ok == true)
assert(rollback_record_result.status == "success")
assert(rollback_record_result.operation == "ai_rollback.write_record")
assert(rollback_record_result.rollback_record_id == "rollback:test:capture")
assert(rollback_record_result.rollback_storage_ref == "rollback-store:rollback:test:capture")
assert(#persisted_rollback_records == 1)
local rollback_record = persisted_rollback_records[1]
assert(rollback_record.schema_version == 1)
assert(rollback_record.record_id == "rollback:test:capture")
assert(rollback_record.policy == "snapshot")
assert(rollback_record.world_id == "test-world")
assert(rollback_record.task_id == "task:rollback-capture")
assert(rollback_record.agent_id == "nova:emma")
assert(rollback_record.owner_ref == "emma")
assert(rollback_record.operation_label == "repair.remove_hazard")
assert(rollback_record.mutation_class == "repair")
assert(rollback_record.changed_positions[1].x == rollback_capture_pos.x)
assert(rollback_record.previous_nodes[1].pos.x == rollback_capture_pos.x)
assert(rollback_record.previous_nodes[1].node.name == "ai_runtime_test:stone")
assert(rollback_record.previous_nodes[1].node.param1 == 12)
assert(rollback_record.previous_nodes[1].node.param2 == 34)
assert(rollback_record.chunk.chunk_index == 0)
assert(rollback_record.chunk.chunk_count == 1)
assert(rollback_record.chunk.first_position_index == 0)
assert(rollback_record.chunk.position_count == 1)
assert(type(rollback_record.created_at) == "string")
assert(rollback_record.private_payload == nil)
assert(rollback_record.asset_payload == nil)

local rollback_blocked_pos = test_pos(4091)
set_test_node(rollback_blocked_pos, { name = "air" })
local rollback_mutation_writes = 0
local rollback_blocked = core.run_ai_world_mutation_with_rollback({
	record_id = "rollback:test:blocked",
	policy = "snapshot",
	world_id = "test-world",
	task_id = "task:rollback-blocked",
	agent_id = "nova:emma",
	owner_ref = "emma",
	operation_label = "build.marker",
	mutation_class = "build",
	bounds = {
		min = test_pos(4080),
		max = test_pos(4100),
	},
	positions = {
		rollback_blocked_pos,
	},
	get_node = get_test_node,
}, function()
	rollback_mutation_writes = rollback_mutation_writes + 1
	set_test_node(rollback_blocked_pos, { name = "ai_runtime_test:stone" })
	return {
		ok = true,
		status = "success",
		changed = 1,
	}
end)
assert(rollback_blocked.ok == false)
assert(rollback_blocked.status == "blocked")
assert(rollback_blocked.operation == "ai_rollback.write_record")
assert(rollback_blocked.reason == "rollback_metadata_unavailable")
assert(rollback_blocked.changed == 0)
assert(rollback_mutation_writes == 0)
assert(get_test_node(rollback_blocked_pos).name == "air")

assert(core.ai_rollback_storage ~= nil)
local durable_records = {}
core.ai_rollback_storage.configure({
	enabled = true,
	persist_record = function(record)
		durable_records[record.record_id] = record
		return {
			ok = true,
			storage_ref = "rollback://test/" .. record.record_id,
		}
	end,
	inspect_record = function(storage_ref)
		local record_id = storage_ref:match("^rollback://test/(.+)$")
		return durable_records[record_id]
	end,
	prune_records = function()
		local removed = 0
		for record_id in pairs(durable_records) do
			durable_records[record_id] = nil
			removed = removed + 1
		end
		return removed
	end,
})

local durable_pos = test_pos(4093)
set_test_node(durable_pos, {
	name = "ai_runtime_test:stone",
	param1 = 4,
	param2 = 5,
})
local durable_write = core.write_ai_rollback_record({
	record_id = "rollback:test:durable",
	policy = "chunked",
	world_id = "test-world",
	task_id = "task:rollback-durable",
	agent_id = "nova:emma",
	owner_ref = "emma",
	operation_label = "repair.default_storage",
	mutation_class = "repair",
	positions = {
		durable_pos,
	},
	get_node = get_test_node,
	chunk = {
		chunk_index = 1,
		chunk_count = 3,
		first_position_index = 16,
		position_count = 1,
	},
})
assert(durable_write.ok == true)
assert(durable_write.status == "success")
assert(durable_write.rollback_storage_ref == "rollback://test/rollback:test:durable")
assert(durable_records["rollback:test:durable"].chunk.chunk_index == 1)
assert(durable_records["rollback:test:durable"].chunk.chunk_count == 3)
assert(durable_records["rollback:test:durable"].chunk.first_position_index == 16)
assert(durable_records["rollback:test:durable"].chunk.position_count == 1)
local inspected_durable_record =
	core.ai_rollback_storage.inspect(durable_write.rollback_storage_ref)
assert(inspected_durable_record.record_id == "rollback:test:durable")
assert(inspected_durable_record.private_payload == nil)
assert(core.ai_rollback_storage.prune({ world_id = "test-world" }).removed == 1)
assert(core.ai_rollback_storage.inspect(durable_write.rollback_storage_ref) == nil)
core.ai_rollback_storage.configure(nil)

local old_get_worldpath = core.get_worldpath
local old_safe_file_write = core.safe_file_write
local old_write_json = core.write_json
local default_storage_write = nil
core.get_worldpath = function()
	return "/tmp/ai-runtime-test-world"
end
core.safe_file_write = function(path, payload)
	default_storage_write = {
		path = path,
		payload = payload,
	}
	return true
end
core.write_json = function(record)
	assert(record.record_id == "rollback:test:world-default")
	return "{\"record_id\":\"" .. record.record_id .. "\"}"
end
core.ai_rollback_storage.configure({
	enabled = true,
})
local default_file_pos = test_pos(4095)
set_test_node(default_file_pos, { name = "ai_runtime_test:stone" })
local default_file_write = core.write_ai_rollback_record({
	record_id = "rollback:test:world-default",
	policy = "snapshot",
	world_id = "test-world",
	task_id = "task:rollback-world-default",
	agent_id = "nova:emma",
	owner_ref = "emma",
	operation_label = "build.default_world_storage",
	mutation_class = "build",
	positions = {
		default_file_pos,
	},
	get_node = get_test_node,
})
assert(default_file_write.ok == true)
assert(default_file_write.rollback_storage_ref
	== "rollback://world/rollback:test:world-default")
assert(default_storage_write.path
	== "/tmp/ai-runtime-test-world/ai_rollback_rollback_test_world-default.json")
assert(default_storage_write.payload:find("rollback:test:world-default", 1, true))
core.ai_rollback_storage.configure(nil)
core.get_worldpath = old_get_worldpath
core.safe_file_write = old_safe_file_write
core.write_json = old_write_json

core.ai_rollback_storage.configure({
	enabled = true,
	persist_record = function()
		return false
	end,
})
local storage_failure_pos = test_pos(4094)
set_test_node(storage_failure_pos, { name = "air" })
local storage_failure_writes = 0
local storage_failure = core.run_ai_world_mutation_with_rollback({
	record_id = "rollback:test:storage-failure",
	policy = "snapshot",
	world_id = "test-world",
	task_id = "task:rollback-storage-failure",
	agent_id = "nova:emma",
	owner_ref = "emma",
	operation_label = "build.default_storage_failure",
	mutation_class = "build",
	positions = {
		storage_failure_pos,
	},
	get_node = get_test_node,
}, function()
	storage_failure_writes = storage_failure_writes + 1
	return core.ai_world_ops.place_node(storage_failure_pos,
		"ai_runtime_test:stone", {
			agent_id = "nova:emma",
			task_id = "task:rollback-storage-failure",
			owner = "emma",
			get_node = get_test_node,
			set_node = set_test_node,
		})
end)
assert(storage_failure.ok == false)
assert(storage_failure.status == "blocked")
assert(storage_failure.reason == "rollback_metadata_unavailable")
assert(storage_failure.changed == 0)
assert(storage_failure_writes == 0)
assert(get_test_node(storage_failure_pos).name == "air")
core.ai_rollback_storage.configure(nil)

local rollback_guarded_pos = test_pos(4092)
set_test_node(rollback_guarded_pos, { name = "air" })
local rollback_guarded_writes = 0
local rollback_guarded = core.run_ai_world_mutation_with_rollback({
	record_id = "rollback:test:guarded",
	policy = "snapshot",
	world_id = "test-world",
	task_id = "task:rollback-guarded",
	agent_id = "nova:emma",
	owner_ref = "emma",
	operation_label = "build.marker",
	mutation_class = "build",
	bounds = {
		min = test_pos(4080),
		max = test_pos(4100),
	},
	positions = {
		rollback_guarded_pos,
	},
	get_node = get_test_node,
	persist_record = function(record)
		return "rollback-store:" .. record.record_id
	end,
}, function(ctx)
	assert(ctx.rollback_record.record_id == "rollback:test:guarded")
	assert(ctx.rollback_storage_ref == "rollback-store:rollback:test:guarded")
	rollback_guarded_writes = rollback_guarded_writes + 1
	return core.ai_world_ops.place_node(rollback_guarded_pos,
		"ai_runtime_test:stone", {
			agent_id = ctx.agent_id,
			task_id = ctx.task_id,
			owner = "emma",
			get_node = get_test_node,
			set_node = set_test_node,
		})
end)
assert(rollback_guarded.ok == true)
assert(rollback_guarded.status == "success")
assert(rollback_guarded.rollback_record_id == "rollback:test:guarded")
assert(rollback_guarded.rollback_storage_ref == "rollback-store:rollback:test:guarded")
assert(rollback_guarded.changed == 1)
assert(rollback_guarded_writes == 1)
assert(get_test_node(rollback_guarded_pos).name == "ai_runtime_test:stone")

local rollback_audit = core.get_ai_runtime_audit({ limit = 10 })
local rollback_audit_record = nil
for _, record in ipairs(rollback_audit) do
	if record.event_type == "rollback.record"
			and record.rollback_record_id == "rollback:test:guarded" then
		rollback_audit_record = record
	end
end
assert(rollback_audit_record ~= nil)
assert(rollback_audit_record.event_type == "rollback.record")
assert(rollback_audit_record.rollback_record_id == "rollback:test:guarded")
assert(rollback_audit_record.rollback_storage_ref == "rollback-store:rollback:test:guarded")
assert(rollback_audit_record.mutation_class == "build")
assert(rollback_audit_record.private_payload == nil)
assert(rollback_audit_record.payload_retained == false)

local safe_options = {
	agent_id = "nova:emma",
	task_id = "task:safe-world",
	owner = "emma",
	sample_limit = 2,
	get_node = get_test_node,
	set_node = set_test_node,
}

local place_pos = test_pos(4100)
set_test_node(place_pos, { name = "air" })
local placed = core.ai_world_ops.place_node(place_pos, "ai_runtime_test:stone", safe_options)
assert_action_result(placed, true, "success", "ai_world.place_node")
assert(placed.task_id == "task:safe-world")
assert(placed.changed == 1)
assert(placed.examined == 1)
assert(placed.skipped == 0)
assert(placed.metrics.node_writes == 1)
assert(get_test_node(place_pos).name == "ai_runtime_test:stone")

local inspected = core.ai_world_ops.inspect_area(place_pos, 0, {
	node_names = {
		["ai_runtime_test:stone"] = true,
	},
}, safe_options)
assert_action_result(inspected, true, "success", "ai_world.inspect_area")
assert(inspected.examined == 1)
assert(inspected.changed == 0)
assert(#inspected.samples == 1)
assert(inspected.samples[1].node.name == "ai_runtime_test:stone")

local safe_search_base = test_pos(4110)
set_test_node(safe_search_base, { name = "ai_runtime_test:stone" })
local safe_search_target = test_pos(4111)
set_test_node(safe_search_target, { name = "air" })
local found = core.ai_world_ops.find_safe_position(safe_search_base, {
	agent_id = "nova:emma",
	owner = "emma",
	get_node = get_test_node,
	offsets = {
		{ x = 0, y = 0, z = 0 },
		{ x = 1, y = 0, z = 0 },
	},
})
assert_action_result(found, true, "success", "ai_world.find_safe_position")
assert(found.pos.x == safe_search_target.x)
assert(found.pos.y == safe_search_target.y)
assert(found.pos.z == safe_search_target.z)

local protected_pos = test_pos(4120)
set_test_node(protected_pos, { name = "air" })
local old_is_protected = core.is_protected
core.is_protected = function(pos, name)
	return name == "emma" and pos.x == protected_pos.x
end
local protected = core.ai_world_ops.place_node(protected_pos, "ai_runtime_test:stone", safe_options)
assert_action_result(protected, false, "blocked", "ai_world.place_node")
assert(protected.reason == "protected_area")
assert(protected.changed == 0)
assert(protected.skipped == 1)
assert(#protected.samples == 1)
assert(protected.samples[1].reason == "protected_area")
assert(get_test_node(protected_pos).name == "air")
core.is_protected = old_is_protected

local unbreakable_pos = test_pos(4130)
set_test_node(unbreakable_pos, { name = "ai_runtime_test:unbreakable" })
local unbreakable = core.ai_world_ops.remove_node(unbreakable_pos, safe_options)
assert_action_result(unbreakable, false, "blocked", "ai_world.remove_node")
assert(unbreakable.reason == "unbreakable_node")
assert(unbreakable.changed == 0)
assert(unbreakable.skipped == 1)
assert(get_test_node(unbreakable_pos).name == "ai_runtime_test:unbreakable")

local replace_pos = test_pos(4140)
set_test_node(replace_pos, { name = "ai_runtime_test:stone" })
local replaced = core.ai_world_ops.replace_node(replace_pos, "ai_runtime_test:stone",
		"air", safe_options)
assert_action_result(replaced, true, "success", "ai_world.replace_node")
assert(replaced.changed == 1)
assert(get_test_node(replace_pos).name == "air")

local mismatch = core.ai_world_ops.replace_node(replace_pos, "ai_runtime_test:stone",
		"air", safe_options)
assert_action_result(mismatch, false, "not_found", "ai_world.replace_node")
assert(mismatch.reason == "expected_node_mismatch")

local batch_one = test_pos(4150)
local batch_two = test_pos(4151)
local batch_three = test_pos(4152)
set_test_node(batch_one, { name = "air" })
set_test_node(batch_two, { name = "air" })
set_test_node(batch_three, { name = "air" })
old_is_protected = core.is_protected
core.is_protected = function(pos, name)
	return name == "emma" and pos.x == batch_two.x
end
local batch_place = core.ai_world_ops.batch_place({
	{ pos = batch_one, node_name = "ai_runtime_test:stone" },
	{ pos = batch_two, node_name = "ai_runtime_test:stone" },
	{ pos = batch_three, node_name = "ai_runtime_test:stone" },
}, {
	agent_id = "nova:emma",
	owner = "emma",
	max_changes = 1,
	sample_limit = 2,
	get_node = get_test_node,
	set_node = set_test_node,
})
assert_action_result(batch_place, true, "partial", "ai_world.batch_place")
assert(batch_place.changed == 1)
assert(batch_place.examined == 3)
assert(batch_place.skipped == 2)
assert(#batch_place.samples == 2)
assert(batch_place.samples[1].reason == "protected_area")
assert(batch_place.samples[2].reason == "max_changes_reached")
assert(get_test_node(batch_one).name == "ai_runtime_test:stone")
assert(get_test_node(batch_two).name == "air")
assert(get_test_node(batch_three).name == "air")
core.is_protected = old_is_protected

local batch_param_pos = test_pos(4153)
set_test_node(batch_param_pos, { name = "air" })
local batch_param_place = core.ai_world_ops.batch_place({
	{
		pos = batch_param_pos,
		node = {
			name = "ai_runtime_test:stone",
			param1 = 7,
			param2 = 9,
		},
	},
}, safe_options)
assert_action_result(batch_param_place, true, "success", "ai_world.batch_place")
assert(get_test_node(batch_param_pos).name == "ai_runtime_test:stone")
assert(get_test_node(batch_param_pos).param1 == 7)
assert(get_test_node(batch_param_pos).param2 == 9)

local batch_remove = core.ai_world_ops.batch_remove({ batch_one, unbreakable_pos }, safe_options)
assert_action_result(batch_remove, true, "partial", "ai_world.batch_remove")
assert(batch_remove.changed == 1)
assert(batch_remove.examined == 2)
assert(batch_remove.skipped == 1)
assert(batch_remove.samples[1].reason == "unbreakable_node")
assert(get_test_node(batch_one).name == "air")

local hazard_pos = test_pos(4160)
set_test_node(hazard_pos, { name = "ai_runtime_test:hazard" })
local hazard = core.ai_world_ops.remove_node(hazard_pos, safe_options)
assert_action_result(hazard, false, "unsafe", "ai_world.remove_node")
assert(hazard.reason == "hazard_node")
assert(get_test_node(hazard_pos).name == "ai_runtime_test:hazard")

core.record_ai_runtime_audit({
	event_type = "model.request",
	agent_id = "nova:emma",
	task_id = "task:safe-world",
	message = "model request queued",
	private_payload = {
		prompt = "do not retain this prompt",
	},
})

local metrics = core.get_ai_runtime_metrics()
assert(type(metrics) == "table")
assert(metrics.tasks_queued == 8)
assert(metrics.task_steps_run == 9)
assert(metrics.tasks_completed == 4)
assert(metrics.tasks_cancelled == 2)
assert(metrics.tasks_unsafe == 2)
assert(metrics.queue_length == 0)
assert(metrics.active_tasks == 0)
assert(metrics.node_writes >= 4)
assert(metrics.skipped_operations >= 6)
assert(metrics.unsafe_operations >= 1)
assert(metrics.rollback_records_written >= 2)
assert(metrics.rollback_record_failures >= 1)
assert(metrics.task_lag_pauses >= 1)
assert(metrics.task_wall_clock_budget_exceeded >= 1)
assert(metrics.audit_records >= 1)
assert(type(metrics.entities_by_type) == "table")

local formatted_metrics = core.format_ai_runtime_metrics({
	queue_length = 2,
	task_status_counts = {
		queued = 1,
		running = 1,
		completed = 4,
		unsafe = 1,
	},
	task_duration_us = {
		count = 5,
		total = 12000,
		max = 5000,
		average = 2400,
	},
	node_writes = 7,
	world_node_writes = 5,
	task_reported_node_writes = 2,
	unsafe_operations = 3,
	audit_records = 9,
	pending_model_requests = 4,
	model_adapter_requests = 6,
	model_adapter_successes = 3,
	model_adapter_failures = 2,
	model_adapter_timeouts = 1,
})
assert(formatted_metrics ==
	"AI runtime: queue=2 tasks=queued=1,running=1,completed=4,unsafe=1 "
	.. "duration=count=5,total_us=12000,max_us=5000,avg_us=2400 "
	.. "writes=total=7,world=5,reported=2 unsafe=3 audit=9 "
	.. "model=pending=4,requests=6,ok=3,fail=2,timeout=1")
assert(not formatted_metrics:find("nova:emma", 1, true))

local operator_metrics = core.get_ai_runtime_operator_metrics()
assert(type(operator_metrics.task_status_counts) == "table")
assert(operator_metrics.task_status_counts.completed >= 2)
assert(operator_metrics.task_status_counts.cancelled >= 2)
assert(operator_metrics.task_status_counts.unsafe >= 1)

function test_ai_runtime_operator_status_package_command()
core.register_ai_agent({
	agent_id = "operator_status:private",
	display_name = "Private Status Agent",
	owner = "/Users/billevans/private/spacebase",
	plugin = "operator_status_test",
	capabilities = {
		["world.read"] = true,
		["rollback.execute"] = true,
	},
	limits = {
		capability_profile = "operator",
	},
})
core.registered_ai_tasks["operator-status:queued"] = {
	task_id = "operator-status:queued",
	agent_id = "operator_status:private",
	owner = "operator",
	label = "Inspect minecraftpi.home / 192.168.230.60 themepark private_prompt asset_payload "
		.. string.rep("x", 20000),
	status = "queued",
	created_at = 0,
	updated_at = 0,
	budget = {},
	progress = {
		current = 0,
		total = 1,
	},
	last_result = {},
}
core.record_ai_runtime_audit({
	event_type = "rollback.record",
	agent_id = "operator_status:private",
	task_id = "operator-status:queued",
	status = "success",
	reason = "rollback_record_written",
	rollback_record_id = "rollback:operator-status",
	rollback_storage_ref = "rollback://minecraftpi.home/192.168.230.60/spacebase",
	message = "private_prompt asset_payload /Users/billevans/private " .. string.rep("y", 20000),
})
core.record_ai_runtime_audit({
	event_type = "import.plan",
	agent_id = "operator_status:private",
	task_id = "operator-status:queued",
	status = "blocked",
	reason = "payload_rejected",
	message = "themepark import blocked before mutation",
})

assert(type(core.build_ai_operator_status_package) == "function")
local status_before_metrics = core.get_ai_runtime_operator_metrics()
local operator_status_package = core.build_ai_operator_status_package({
	generated_at = "2026-06-29T00:00:00Z",
	max_bytes = 24000,
	benchmark_gates = {
		{
			gate_id = "runtime-command-test",
			status = "pass",
			source = "/Users/billevans/benchmarks/sk-123456789012345678901234",
		},
	},
})
local status_after_metrics = core.get_ai_runtime_operator_metrics()
assert(status_after_metrics.node_writes == status_before_metrics.node_writes)
assert(status_after_metrics.tasks_cancelled == status_before_metrics.tasks_cancelled)
assert(status_after_metrics.rollback_records_written == status_before_metrics.rollback_records_written)
assert(operator_status_package.schema_version == 1)
assert(operator_status_package.package_kind == "ai_native_operator_status_package")
assert(operator_status_package.generated_at == "2026-06-29T00:00:00Z")
assert(operator_status_package.runtime_context.game_profile == "ai_runtime")
assert(operator_status_package.runtime_context.mutation_performed == false)
assert(operator_status_package.server_profile_hygiene.status == "pass")
assert(operator_status_package.server_profile_hygiene.dev_surfaces_disabled_by_default == true)
assert(operator_status_package.agents.total >= 1)
assert(operator_status_package.tasks.counts.total >= 1)
assert(operator_status_package.tasks.counts.queued >= 1)
assert(operator_status_package.rollback.records_available >= 1)
assert(operator_status_package.imports.reviews_total >= 1)
assert(operator_status_package.benchmarks.status_counts.pass == 1)
assert(operator_status_package.operator_control.surface_kind == "read_only_task_rollback_control")
assert(operator_status_package.operator_control.action_mode == "dry_run_only")
assert(operator_status_package.operator_control.mutation_performed == false)
assert(operator_status_package.operator_control.recommendations_total >= 3)
assert(operator_status_package.operator_control.truncated == false)
local task_control_found = false
local rollback_control_found = false
local import_control_found = false
for _, recommendation in ipairs(operator_status_package.operator_control.summaries) do
	assert(recommendation.dry_run_only == true)
	assert(recommendation.will_mutate == false)
	assert(type(recommendation.target_id) == "string")
	assert(type(recommendation.safe_next_action) == "string")
	if recommendation.target_kind == "task"
			and recommendation.target_id == "operator-status:queued" then
		task_control_found = true
		assert(recommendation.status == "queued")
		assert(recommendation.safe_next_action == "inspect_task_before_action")
	elseif recommendation.target_kind == "rollback"
			and recommendation.target_id == "rollback:operator-status" then
		rollback_control_found = true
		assert(recommendation.status == "success")
		assert(recommendation.safe_next_action == "review_rollback_record_before_execution")
	elseif recommendation.target_kind == "import_review"
			and recommendation.target_id == "operator-status:queued" then
		import_control_found = true
		assert(recommendation.status == "blocked")
		assert(recommendation.safe_next_action == "review_import_blocker")
	end
end
assert(task_control_found)
assert(rollback_control_found)
assert(import_control_found)
assert(operator_status_package.safety.redactions_applied > 0)
assert(operator_status_package.safety.truncations_applied > 0)
assert(operator_status_package.bounds.output_bytes <= operator_status_package.bounds.max_bytes)
local operator_status_json = core.write_json(operator_status_package)
assert(operator_status_json:find("\"package_kind\":\"ai_native_operator_status_package\"", 1, true))
assert(not operator_status_json:find("/Users/", 1, true))
assert(not operator_status_json:find("minecraftpi", 1, true))
assert(not operator_status_json:find("192.168", 1, true))
assert(not operator_status_json:find("spacebase", 1, true))
assert(not operator_status_json:find("themepark", 1, true))
assert(not operator_status_json:find("private_prompt", 1, true))
assert(not operator_status_json:find("asset_payload", 1, true))

assert(core.registered_chatcommands.ai_runtime_operator_status ~= nil)
assert(core.registered_chatcommands.ai_runtime_operator_status.privs.server == true)
local command_before_metrics = core.get_ai_runtime_operator_metrics()
local operator_command_ok, operator_command_message =
	core.registered_chatcommands.ai_runtime_operator_status.func(
		"admin",
		"generated_at=2026-06-29T00:00:00Z")
local command_after_metrics = core.get_ai_runtime_operator_metrics()
assert(operator_command_ok == true)
assert(command_after_metrics.node_writes == command_before_metrics.node_writes)
assert(command_after_metrics.tasks_cancelled == command_before_metrics.tasks_cancelled)
assert(command_after_metrics.rollback_records_written == command_before_metrics.rollback_records_written)
assert(operator_command_message:find("\"package_kind\":\"ai_native_operator_status_package\"", 1, true))
assert(operator_command_message:find("\"runtime_context\"", 1, true))
assert(operator_command_message:find("\"server_profile_hygiene\"", 1, true))
assert(operator_command_message:find("\"agents\"", 1, true))
assert(operator_command_message:find("\"tasks\"", 1, true))
assert(operator_command_message:find("\"rollback\"", 1, true))
assert(operator_command_message:find("\"imports\"", 1, true))
assert(operator_command_message:find("\"benchmarks\"", 1, true))
assert(operator_command_message:find("\"operator_control\"", 1, true))
assert(operator_command_message:find("\"dry_run_only\"", 1, true))
assert(#operator_command_message <= 24000)
assert(not operator_command_message:find("/Users/", 1, true))
assert(not operator_command_message:find("minecraftpi", 1, true))
assert(not operator_command_message:find("192.168", 1, true))
assert(not operator_command_message:find("spacebase", 1, true))
assert(not operator_command_message:find("themepark", 1, true))
assert(not operator_command_message:find("private_prompt", 1, true))
assert(not operator_command_message:find("asset_payload", 1, true))
local compact_command_ok, compact_command_message =
	core.registered_chatcommands.ai_runtime_operator_status.func(
		"admin",
		"generated_at=2026-06-29T00:00:00Z max_bytes=2000")
assert(compact_command_ok == true)
assert(#compact_command_message <= 2000)
assert(compact_command_message:find("\"truncated\":true", 1, true))
end
test_ai_runtime_operator_status_package_command()
test_ai_runtime_operator_status_package_command = nil

do
	local function assert_task_control_result_shape(result, decisions_total, executed_total, rejected_total)
		assert(type(result) == "table")
		assert(result.schema_version == 1)
		assert(result.command_result_kind == "ai_native_operator_task_control_command_result")
		assert(result.runtime_context.game_profile == "ai_runtime")
		assert(result.runtime_context.command == "/ai_runtime_operator_task_control")
		assert(result.runtime_context.world_mutation_performed == false)
		assert(result.operator_actions.mode == "receipt_gated_task_cancel_retry")
		assert(result.operator_actions.mutation_scope == "live_task_queue")
		assert(result.summary.decisions_total == decisions_total)
		assert(result.summary.executed_total == executed_total)
		assert(result.summary.rejected_total == rejected_total)
		assert(result.safety.public_safe_output == true)
		assert(result.safety.no_world_mutation == true)
		assert(result.safety.no_rollback_execution == true)
		assert(result.safety.no_import_promotion_execution == true)
		assert(result.safety.no_raw_assets == true)
		assert(result.safety.no_provider_prompts == true)
		assert(result.safety.no_family_world_coordinates == true)
		assert(result.bounds.output_bytes <= result.bounds.max_bytes)
	end

	local function queue_running_task(task_id)
		core.registered_ai_tasks[task_id] = {
			task_id = task_id,
			agent_id = "nova:emma",
			owner = "emma",
			label = "operator task control cancel target",
			status = "running",
			created_at = 0,
			updated_at = 0,
			budget = {},
			progress = {
				current = 1,
				total = 2,
			},
			retry_count = 0,
			last_result = {
				ok = true,
				status = "success",
			},
			steps = {
				function()
					return { ok = true, status = "success", changed = 0 }
				end,
				function()
					return { ok = true, status = "success", changed = 0 }
				end,
			},
		}
		assert(core.get_ai_task(task_id).status == "running")
	end

	local function queue_blocked_task(task_id)
		core.registered_ai_tasks[task_id] = {
			task_id = task_id,
			agent_id = "nova:emma",
			owner = "emma",
			label = "operator task control retry target",
			status = "blocked",
			created_at = 0,
			updated_at = 0,
			budget = {},
			progress = {
				current = 1,
				total = 1,
			},
			retry_count = 0,
			last_result = {
				ok = false,
				status = "blocked",
				reason = "operator_review_required",
				message = "Blocked for receipt-gated retry review.",
			},
			steps = {
				function()
					return {
						ok = false,
						status = "blocked",
						reason = "operator_review_required",
						message = "Blocked for receipt-gated retry review.",
					}
				end,
			},
		}
		assert(core.get_ai_task(task_id).status == "blocked")
	end

	local function decision(target_id, operation, overrides)
		local item = {
			decision_id = "decision:" .. target_id,
			decision_status = "approved",
			approval_kind = "task_cancel_retry_review",
			target_kind = "task",
			target_id = target_id,
			task_operation = operation,
			safe_next_action = "execute_task_" .. operation,
			approval_required = true,
			dry_run_only = true,
			will_mutate = false,
			mutation_performed = false,
			receipt_only = true,
			prerequisites_required = {
				"inspect_task_before_action",
			},
			prerequisites_acknowledged = {
				"inspect_task_before_action",
			},
			required_capabilities = {
				"task.inspect",
				operation == "cancel" and "task.cancel" or "task.retry",
			},
		}
		for key, value in pairs(overrides or {}) do
			item[key] = value
		end
		return item
	end

	local function receipt(decisions, overrides)
		local item = {
			receipt_kind = "ai_native_operator_action_approval_receipt",
			schema_version = 1,
			generated_at = "2026-06-29T00:00:00Z",
			operator_decisions = {
				mode = "receipt_only",
				mutation_performed = false,
				decisions = decisions,
			},
			safety = {
				public_safe_output = true,
				receipt_only = true,
				no_world_mutation = true,
				no_rollback_execution = true,
				no_import_promotion_execution = true,
				no_raw_assets = true,
				no_provider_prompts = true,
				no_family_world_coordinates = true,
			},
			bounds = {
				output_bytes = 1200,
				max_bytes = 24000,
			},
		}
		for key, value in pairs(overrides or {}) do
			item[key] = value
		end
		return item
	end

	local function capability_set(values)
		local result = {}
		for _, value in ipairs(values) do
			result[value] = true
		end
		return result
	end

	assert(type(core.apply_ai_operator_task_control_receipt) == "function")

	queue_running_task("operator-task-control:cancel-api")
	queue_blocked_task("operator-task-control:retry-api")

	local api_result = core.apply_ai_operator_task_control_receipt(receipt({
		decision("operator-task-control:cancel-api", "cancel"),
		decision("operator-task-control:retry-api", "retry"),
		decision("operator-task-control:denied-api", "cancel", {
			decision_status = "denied",
		}),
		decision("rollback:operator-task-control", "cancel", {
			target_kind = "rollback",
			safe_next_action = "execute_rollback",
		}),
		decision("import:operator-task-control", "retry", {
			target_kind = "import_promotion",
			safe_next_action = "promote_import",
		}),
	}), {
		actor = "emma",
		generated_at = "2026-06-29T00:00:00Z",
		max_bytes = 24000,
		executor_capabilities = capability_set({
			"task.inspect",
			"task.cancel",
			"task.retry",
		}),
	})
	assert_task_control_result_shape(api_result, 5, 2, 3)
	assert(api_result.operator_actions.mutation_performed == true)
	assert(core.get_ai_task("operator-task-control:cancel-api").status == "cancelled")
	assert(core.get_ai_task("operator-task-control:retry-api").status == "queued")
	assert(api_result.results[1].status == "executed")
	assert(api_result.results[1].operation == "cancel")
	assert(api_result.results[1].before_status == "running")
	assert(api_result.results[1].after_status == "cancelled")
	assert(api_result.results[2].status == "executed")
	assert(api_result.results[2].operation == "retry")
	assert(api_result.results[2].before_status == "blocked")
	assert(api_result.results[2].after_status == "queued")
	assert(api_result.results[3].status == "rejected")
	assert(api_result.results[3].reason == "decision_not_approved")
	assert(api_result.results[4].reason == "unsupported_target_kind")
	assert(api_result.results[5].reason == "unsupported_target_kind")

	queue_blocked_task("operator-task-control:missing-capability")
	local missing_capability = core.apply_ai_operator_task_control_receipt(receipt({
		decision("operator-task-control:missing-capability", "retry"),
	}), {
		actor = "emma",
		executor_capabilities = capability_set({
			"task.inspect",
		}),
	})
	assert_task_control_result_shape(missing_capability, 1, 0, 1)
	assert(missing_capability.results[1].reason == "missing_executor_capability")
	assert(core.get_ai_task("operator-task-control:missing-capability").status == "blocked")

	queue_blocked_task("operator-task-control:missing-prereq")
	local missing_prereq = core.apply_ai_operator_task_control_receipt(receipt({
		decision("operator-task-control:missing-prereq", "retry", {
			prerequisites_acknowledged = {},
		}),
	}), {
		actor = "emma",
		executor_capabilities = capability_set({
			"task.inspect",
			"task.retry",
		}),
	})
	assert(missing_prereq.results[1].reason == "missing_acknowledged_prerequisite")
	assert(core.get_ai_task("operator-task-control:missing-prereq").status == "blocked")

	queue_blocked_task("operator-task-control:unauthorized")
	local unauthorized = core.apply_ai_operator_task_control_receipt(receipt({
		decision("operator-task-control:unauthorized", "retry"),
	}), {
		actor = "nova:disabled",
		executor_capabilities = capability_set({
			"task.inspect",
			"task.retry",
		}),
	})
	assert(unauthorized.results[1].reason == "retry_denied")
	assert(core.get_ai_task("operator-task-control:unauthorized").status == "blocked")

	local invalid_receipt_result = core.apply_ai_operator_task_control_receipt(receipt({
		decision("operator-task-control:stale", "cancel"),
	}, {
		expired_at = "2026-06-28T00:00:00Z",
		safety = {
			public_safe_output = true,
			receipt_only = true,
			no_world_mutation = false,
			no_rollback_execution = true,
			no_import_promotion_execution = true,
			no_raw_assets = true,
			no_provider_prompts = true,
			no_family_world_coordinates = true,
		},
	}), {
		actor = "emma",
		generated_at = "2026-06-29T00:00:00Z",
		executor_capabilities = capability_set({
			"task.inspect",
			"task.cancel",
		}),
	})
	assert(invalid_receipt_result.summary.executed_total == 0)
	assert(invalid_receipt_result.results[1].reason == "receipt_stale")

	local private_receipt_result = core.apply_ai_operator_task_control_receipt(receipt({
		decision("operator-task-control:private", "cancel", {
			private_prompt = "minecraftpi.home /Users/billevans/private/spacebase sk-12345678901234567890",
		}),
	}), {
		actor = "emma",
		executor_capabilities = capability_set({
			"task.inspect",
			"task.cancel",
		}),
	})
	assert(private_receipt_result.results[1].reason == "private_receipt_content")
	local private_result_json = core.write_json(private_receipt_result)
	assert(not private_result_json:find("minecraftpi", 1, true))
	assert(not private_result_json:find("/Users/", 1, true))
	assert(not private_result_json:find("spacebase", 1, true))
	assert(not private_result_json:find("sk%-", 1, false))

	assert(core.registered_chatcommands.ai_runtime_operator_task_control ~= nil)
	assert(core.registered_chatcommands.ai_runtime_operator_task_control.privs.server == true)
	queue_running_task("operator-task-control:cancel-command")
	queue_blocked_task("operator-task-control:retry-command")
	local command_receipt = receipt({
		decision("operator-task-control:cancel-command", "cancel"),
		decision("operator-task-control:retry-command", "retry"),
		decision("operator-task-control:needs-review-command", "retry", {
			decision_status = "needs_review",
		}),
	})
	local command_ok, command_message =
		core.registered_chatcommands.ai_runtime_operator_task_control.func(
			"admin",
			"generated_at=2026-06-29T00:00:00Z max_bytes=24000 receipt_json="
				.. core.write_json(command_receipt))
	assert(command_ok == true)
	local command_result = core.parse_json(command_message)
	assert_task_control_result_shape(command_result, 3, 2, 1)
	assert(command_result.runtime_context.actor == "admin")
	assert(command_result.results[3].reason == "decision_not_approved")
	assert(core.get_ai_task("operator-task-control:cancel-command").status == "cancelled")
	assert(core.get_ai_task("operator-task-control:retry-command").status == "queued")
	assert(#command_message <= 24000)
	assert(not command_message:find("private_prompt", 1, true))
	assert(not command_message:find("asset_payload", 1, true))

	queue_blocked_task("operator-task-control:retry-command-spaced-json")
	local spaced_command_receipt = receipt({
		decision("operator-task-control:retry-command-spaced-json", "retry", {
			operator_note = "operator approved retry after reading the task status",
		}),
	})
	local spaced_command_ok, spaced_command_message =
		core.registered_chatcommands.ai_runtime_operator_task_control.func(
			"admin",
			"generated_at=2026-06-29T00:00:00Z max_bytes=24000 receipt_json="
				.. core.write_json(spaced_command_receipt))
	assert(spaced_command_ok == true)
	local spaced_command_result = core.parse_json(spaced_command_message)
	assert_task_control_result_shape(spaced_command_result, 1, 1, 0)
	assert(core.get_ai_task("operator-task-control:retry-command-spaced-json").status == "queued")

	local missing_command_ok, missing_command_message =
		core.registered_chatcommands.ai_runtime_operator_task_control.func("admin", "")
	assert(missing_command_ok == false)
	assert(missing_command_message:find("receipt_json", 1, true))
end

assert(core.demo_entity_benchmark ~= nil)
local demo_fixture = core.demo_entity_benchmark.get_fixture()
assert(demo_fixture.fixture_id == "generic_demo_entity:benchmark:v1")
assert(demo_fixture.entity_name == "ai_demo_benchmark:helper")
assert(demo_fixture.provenance.source_category == "code-only")
assert(demo_fixture.provenance.assets_included == false)
assert(demo_fixture.mutation.node_mutation_enabled == false)

local demo_report = core.demo_entity_benchmark.run_suite({
	owner_ref = "owner:synthetic-operator",
	entity_count = 4,
	movement_steps = 5,
})
assert(demo_report.operation == "demo_entity_benchmark.run_suite")
assert(demo_report.fixture_id == demo_fixture.fixture_id)
assert(demo_report.entity_name == demo_fixture.entity_name)
assert(demo_report.provenance.assets_included == false)
assert(demo_report.mutation.node_mutation_enabled == false)
assert(#demo_report.scenarios == 5)

local demo_scenarios = {}
for _, scenario in ipairs(demo_report.scenarios) do
	demo_scenarios[scenario.scenario_id] = scenario
	assert(scenario.status == "success")
	assert(scenario.changed == 0)
	assert(scenario.metrics.node_writes == 0)
	assert(scenario.metrics.remaining_entities == 0)
	assert(scenario.metrics.cleaned_up == scenario.metrics.spawned)
	assert(scenario.metrics.avg_step_ms >= 0)
	assert(scenario.metrics.p95_step_ms >= scenario.metrics.avg_step_ms)
	assert(scenario.metrics.max_lag_ms >= scenario.metrics.p95_step_ms)
	assert(#scenario.metrics.warnings == 0)
	assert(#scenario.metrics.errors == 0)
end

assert(demo_scenarios.entity_count_small.metrics.entity_count == 4)
assert(demo_scenarios.entity_scale_16.metrics.entity_count >= 16)
assert(demo_scenarios.entity_scale_16.metrics.active_peak >= 16)
assert(demo_scenarios.entity_scale_16.metrics.remaining_entities == 0)
assert(demo_scenarios.movement_patrol.metrics.movement_steps == 5)
assert(demo_scenarios.movement_patrol.metrics.distance_moved > 0)
assert(demo_scenarios.collision_wall_contact.metrics.collision_checks > 0)
assert(demo_scenarios.collision_wall_contact.metrics.collision_events > 0)
assert(demo_scenarios.cleanup_despawn.metrics.cleaned_up == 4)
local post_demo_metrics = core.get_ai_runtime_metrics()
assert(post_demo_metrics.entities_by_type["ai_demo_benchmark:helper"] == 0)

local demo_command_report = core.demo_entity_benchmark.run_report({
	owner_ref = "owner:synthetic-operator",
	entity_count = 3,
	movement_steps = 2,
	hardware_class = "local-mac",
	luanti_commit = "test-commit",
})
assert(demo_command_report.schema_version == 1)
assert(demo_command_report.fixture_id == demo_fixture.fixture_id)
assert(demo_command_report.hardware_class == "local-mac")
assert(demo_command_report.luanti_commit == "test-commit")
assert(demo_command_report.run_context.requires_private_world == false)
assert(demo_command_report.run_context.requires_private_assets == false)
assert(demo_command_report.run_context.requires_live_pi == false)
assert(demo_command_report.runtime_counters.entities_by_type["ai_demo_benchmark:helper"] == 0)
assert(#demo_command_report.scenarios == 5)

assert(core.registered_chatcommands.ai_demo_entity_benchmark ~= nil)
local demo_command_ok, demo_command_message =
	core.registered_chatcommands.ai_demo_entity_benchmark.func(
		"admin",
		"count=3 steps=2 commit=test-commit hardware=local-mac")
assert(demo_command_ok == true)
assert(demo_command_message:find("\"fixture_id\":\"generic_demo_entity:benchmark:v1\"", 1, true))
assert(demo_command_message:find("\"hardware_class\":\"local-mac\"", 1, true))
assert(demo_command_message:find("\"luanti_commit\":\"test-commit\"", 1, true))
assert(demo_command_message:find("\"runtime_counters\"", 1, true))
assert(#demo_command_message < 12000)
local post_demo_command_metrics = core.get_ai_runtime_metrics()
assert(post_demo_command_metrics.entities_by_type["ai_demo_benchmark:helper"] == 0)

assert(core.ai_entity_ops ~= nil)
core.register_ai_agent({
	agent_id = "entity_agent:helper",
	display_name = "Entity Helper Agent",
	owner = "entity-owner",
	plugin = "entity_ops_test",
	capabilities = {
		["entity.spawn"] = true,
		["entity.control"] = true,
	},
	limits = {
		max_entities = 2,
		max_entity_move_distance = 5,
	},
})
core.register_ai_agent({
	agent_id = "entity_agent:spawn_only",
	display_name = "Spawn Only Agent",
	owner = "entity-owner",
	plugin = "entity_ops_test",
	capabilities = {
		["entity.spawn"] = true,
	},
})

local spawned_refs = {}
local function spawn_test_entity(pos, entity_name, staticdata)
	local ref = {
		entity_name = entity_name,
		staticdata = staticdata,
		pos = table.copy(pos),
		removed = false,
	}
	function ref:get_pos()
		return table.copy(self.pos)
	end
	function ref:set_pos(pos)
		self.pos = table.copy(pos)
		return true
	end
	function ref:remove()
		self.removed = true
	end
	spawned_refs[#spawned_refs + 1] = ref
	return ref
end

local entity_spawn_one = core.ai_entity_ops.spawn("ai_demo_benchmark:helper",
	{ x = 0, y = 0, z = 0 }, {
		entity_id = "entity:test:one",
		agent_id = "entity_agent:helper",
		owner = "entity-owner",
		task_id = "entity-task:spawn-one",
		spawn_entity = spawn_test_entity,
	})
assert(entity_spawn_one.ok == true)
assert(entity_spawn_one.status == "success")
assert(entity_spawn_one.operation == "ai_entity.spawn")
assert(entity_spawn_one.changed == 1)
assert(entity_spawn_one.metrics.entity_count == 1)
assert(entity_spawn_one.entity.entity_id == "entity:test:one")
assert(core.get_ai_runtime_metrics().entities_by_type["ai_demo_benchmark:helper"] == 1)

local entity_inspect = core.ai_entity_ops.inspect("entity:test:one", {
	agent_id = "entity_agent:helper",
	owner = "entity-owner",
	task_id = "entity-task:inspect",
})
assert(entity_inspect.ok == true)
assert(entity_inspect.status == "success")
assert(entity_inspect.operation == "ai_entity.inspect")
assert(entity_inspect.examined == 1)
assert(entity_inspect.entity.pos.x == 0)

local entity_move = core.ai_entity_ops.move("entity:test:one",
	{ x = 2, y = 0, z = 0 }, {
		agent_id = "entity_agent:helper",
		owner = "entity-owner",
		task_id = "entity-task:move",
	})
assert(entity_move.ok == true)
assert(entity_move.status == "success")
assert(entity_move.operation == "ai_entity.move")
assert(entity_move.changed == 1)
assert(entity_move.entity.pos.x == 2)
assert(entity_move.metrics.distance == 2)

local denied_entity_move = core.ai_entity_ops.move("entity:test:one",
	{ x = 3, y = 0, z = 0 }, {
		agent_id = "entity_agent:spawn_only",
		owner = "entity-owner",
		task_id = "entity-task:denied-move",
	})
assert(denied_entity_move.ok == false)
assert(denied_entity_move.status == "permission_denied")
assert(denied_entity_move.reason == "missing_capability")
assert(denied_entity_move.changed == 0)
assert(core.ai_entity_ops.inspect("entity:test:one", {
	agent_id = "entity_agent:helper",
	owner = "entity-owner",
}).entity.pos.x == 2)

local too_far_entity_move = core.ai_entity_ops.move("entity:test:one",
	{ x = 20, y = 0, z = 0 }, {
		agent_id = "entity_agent:helper",
		owner = "entity-owner",
		task_id = "entity-task:too-far",
	})
assert(too_far_entity_move.ok == false)
assert(too_far_entity_move.status == "blocked")
assert(too_far_entity_move.reason == "movement_limit_exceeded")
assert(too_far_entity_move.changed == 0)

local owner_mismatch_cleanup = core.ai_entity_ops.cleanup("entity:test:one", {
	agent_id = "entity_agent:helper",
	owner = "other-owner",
	task_id = "entity-task:owner-mismatch",
})
assert(owner_mismatch_cleanup.ok == false)
assert(owner_mismatch_cleanup.status == "blocked")
assert(owner_mismatch_cleanup.reason == "owner_mismatch")
assert(owner_mismatch_cleanup.changed == 0)

local entity_spawn_two = core.ai_entity_ops.spawn("ai_demo_benchmark:helper",
	{ x = 1, y = 0, z = 0 }, {
		entity_id = "entity:test:two",
		agent_id = "entity_agent:helper",
		owner = "entity-owner",
		task_id = "entity-task:spawn-two",
		spawn_entity = spawn_test_entity,
	})
assert(entity_spawn_two.ok == true)
assert(entity_spawn_two.changed == 1)
assert(core.get_ai_runtime_metrics().entities_by_type["ai_demo_benchmark:helper"] == 2)

local entity_spawn_limit = core.ai_entity_ops.spawn("ai_demo_benchmark:helper",
	{ x = 2, y = 0, z = 0 }, {
		entity_id = "entity:test:three",
		agent_id = "entity_agent:helper",
		owner = "entity-owner",
		task_id = "entity-task:spawn-limit",
		spawn_entity = spawn_test_entity,
	})
assert(entity_spawn_limit.ok == false)
assert(entity_spawn_limit.status == "blocked")
assert(entity_spawn_limit.reason == "entity_limit_exceeded")
assert(entity_spawn_limit.changed == 0)
assert(entity_spawn_limit.skipped == 1)
assert(core.get_ai_runtime_metrics().entities_by_type["ai_demo_benchmark:helper"] == 2)

local cleanup_entities = core.ai_entity_ops.cleanup_owned({
	agent_id = "entity_agent:helper",
	owner = "entity-owner",
	task_id = "entity-task:cleanup-owned",
	entity_name = "ai_demo_benchmark:helper",
})
assert(cleanup_entities.ok == true)
assert(cleanup_entities.status == "success")
assert(cleanup_entities.operation == "ai_entity.cleanup_owned")
assert(cleanup_entities.changed == 2)
assert(cleanup_entities.metrics.entity_count == 0)
assert(spawned_refs[1].removed == true)
assert(spawned_refs[2].removed == true)
assert(core.get_ai_runtime_metrics().entities_by_type["ai_demo_benchmark:helper"] == 0)

local cleanup_again = core.ai_entity_ops.cleanup_owned({
	agent_id = "entity_agent:helper",
	owner = "entity-owner",
	task_id = "entity-task:cleanup-again",
	entity_name = "ai_demo_benchmark:helper",
})
assert(cleanup_again.ok == true)
assert(cleanup_again.status == "success")
assert(cleanup_again.reason == "no_owned_entities")
assert(cleanup_again.changed == 0)
assert(cleanup_again.metrics.entity_count == 0)

local post_entity_ops_metrics = core.get_ai_runtime_metrics()
assert(post_entity_ops_metrics.entity_spawns >= 2)
assert(post_entity_ops_metrics.entity_moves >= 1)
assert(post_entity_ops_metrics.entity_cleanups >= 2)

local entity_audit = core.get_ai_runtime_audit({ limit = 50 })
local function entity_audit_has(event_type, task_id)
	for _, record in ipairs(entity_audit) do
		if record.event_type == event_type and record.task_id == task_id then
			return true
		end
	end
	return false
end
assert(entity_audit_has("entity.spawn", "entity-task:spawn-one"))
assert(entity_audit_has("entity.move", "entity-task:move"))
assert(entity_audit_has("entity.cleanup", "entity-task:cleanup-owned"))

local function run_player_ops_tests()
	assert(core.ai_player_ops ~= nil)
	core.register_ai_agent({
	agent_id = "player_agent:self",
	display_name = "Player Self Agent",
	owner = "PlayerOne",
	plugin = "player_ops_test",
	capabilities = {
		["player.teleport.self"] = true,
		["combat.defend"] = true,
	},
	limits = {
		max_player_teleport_distance = 8,
		max_defend_distance = 6,
	},
})
core.register_ai_agent({
	agent_id = "player_agent:other-no-admin",
	display_name = "Other Teleport No Admin",
	owner = "server",
	plugin = "player_ops_test",
	capabilities = {
		["player.teleport.other"] = true,
	},
})
core.register_ai_agent({
	agent_id = "player_agent:admin",
	display_name = "Admin Player Agent",
	owner = "server",
	plugin = "player_ops_test",
	capabilities = {
		["player.teleport.other"] = true,
		["admin.override"] = true,
	},
	limits = {
		max_player_teleport_distance = 32,
	},
})

local test_players = {}
local function make_test_player(name, pos)
	local player = {
		name = name,
		pos = table.copy(pos),
		attached = false,
	}
	function player:get_player_name()
		return self.name
	end
	function player:get_pos()
		return table.copy(self.pos)
	end
	function player:set_pos(pos)
		self.pos = table.copy(pos)
		return true
	end
	function player:get_attach()
		return self.attached
	end
	test_players[name] = player
	return player
end
make_test_player("PlayerOne", { x = 0, y = 0, z = 0 })
make_test_player("TargetPlayer", { x = 4, y = 0, z = 0 })
local function get_test_player(name)
	return test_players[name]
end

local self_teleport = core.ai_player_ops.teleport_self({ x = 3, y = 0, z = 0 }, {
	agent_id = "player_agent:self",
	owner = "PlayerOne",
	player_name = "PlayerOne",
	task_id = "player-task:self-teleport",
	get_player_by_name = get_test_player,
})
assert(self_teleport.ok == true)
assert(self_teleport.status == "success")
assert(self_teleport.operation == "ai_player.teleport_self")
assert(self_teleport.player.name == "PlayerOne")
assert(self_teleport.player.pos.x == 3)
assert(self_teleport.metrics.distance == 3)
assert(test_players.PlayerOne.pos.x == 3)

local too_far_self_teleport = core.ai_player_ops.teleport_self({ x = 20, y = 0, z = 0 }, {
	agent_id = "player_agent:self",
	owner = "PlayerOne",
	player_name = "PlayerOne",
	task_id = "player-task:self-too-far",
	get_player_by_name = get_test_player,
})
assert(too_far_self_teleport.ok == false)
assert(too_far_self_teleport.status == "blocked")
assert(too_far_self_teleport.reason == "movement_limit_exceeded")
assert(test_players.PlayerOne.pos.x == 3)

	local non_admin_other_teleport = core.ai_player_ops.teleport_player("TargetPlayer",
		{ x = 7, y = 0, z = 0 }, {
			agent_id = "player_agent:other-no-admin",
			owner = "server",
			task_id = "player-task:other-no-admin",
			get_player_by_name = get_test_player,
		})
	assert(non_admin_other_teleport.ok == false)
	assert(non_admin_other_teleport.status == "permission_denied")
	assert(non_admin_other_teleport.reason == "admin_override_required")
	assert(test_players.TargetPlayer.pos.x == 4)

	local missing_agent_ok, missing_agent_error = pcall(core.ai_player_ops.teleport_player,
		"TargetPlayer", { x = 7, y = 0, z = 0 }, {
			owner = "server",
			task_id = "player-task:other-missing-agent",
			get_player_by_name = get_test_player,
		})
	assert(missing_agent_ok == false)
	assert(missing_agent_error:find("agent_id", 1, true))

	local admin_other_teleport = core.ai_player_ops.teleport_player("TargetPlayer",
		{ x = 7, y = 0, z = 0 }, {
		agent_id = "player_agent:admin",
		owner = "server",
		task_id = "player-task:other-admin",
		get_player_by_name = get_test_player,
	})
assert(admin_other_teleport.ok == true)
assert(admin_other_teleport.status == "success")
assert(admin_other_teleport.operation == "ai_player.teleport_player")
assert(admin_other_teleport.player.name == "TargetPlayer")
assert(admin_other_teleport.player.pos.x == 7)

local attacked_hostile = nil
local defend_result = core.ai_player_ops.defend("PlayerOne", {
	agent_id = "player_agent:self",
	owner = "PlayerOne",
	task_id = "player-task:defend",
	get_player_by_name = get_test_player,
	hostiles = {
		{
			entity_id = "hostile:far",
			entity_name = "synthetic:hostile",
			pos = { x = 20, y = 0, z = 0 },
			hostile = true,
		},
		{
			entity_id = "hostile:near",
			entity_name = "synthetic:hostile",
			pos = { x = 5, y = 0, z = 0 },
			hostile = true,
		},
	},
	attack_entity = function(hostile)
		attacked_hostile = hostile.entity_id
		return true
	end,
})
assert(defend_result.ok == true)
assert(defend_result.status == "success")
assert(defend_result.operation == "ai_player.defend")
assert(defend_result.target.entity_id == "hostile:near")
assert(defend_result.changed == 1)
assert(defend_result.examined == 2)
assert(defend_result.metrics.distance == 2)
assert(attacked_hostile == "hostile:near")

local no_hostile_result = core.ai_player_ops.defend("PlayerOne", {
	agent_id = "player_agent:self",
	owner = "PlayerOne",
	task_id = "player-task:defend-empty",
	get_player_by_name = get_test_player,
	hostiles = {},
})
	assert(no_hostile_result.ok == false)
	assert(no_hostile_result.status == "blocked")
	assert(no_hostile_result.reason == "no_hostile_target")
end

run_player_ops_tests()

local function run_model_import_gate_tests()
	assert(core.ai_model_ops ~= nil)
	assert(core.ai_import_ops ~= nil)
	core.register_ai_agent({
		agent_id = "runtime_gate:none",
		display_name = "Runtime Gate Missing Capability",
		owner = "runtime-owner",
		plugin = "runtime_gate_test",
		capabilities = {
			["world.read"] = true,
		},
	})
	core.register_ai_agent({
		agent_id = "runtime_gate:http",
		display_name = "Runtime Gate HTTP Agent",
		owner = "runtime-owner",
		plugin = "runtime_gate_test",
		capabilities = {
			["http.llm"] = true,
		},
	})
	core.register_ai_agent({
		agent_id = "runtime_gate:import",
		display_name = "Runtime Gate Import Agent",
		owner = "runtime-owner",
		plugin = "runtime_gate_test",
		capabilities = {
			["import.assets"] = true,
		},
	})

	core.queue_ai_task({
		task_id = "runtime-gate:model-denied",
		agent_id = "runtime_gate:none",
		owner = "runtime-owner",
		label = "denied model runtime gate",
		steps = {
			function(ctx)
				return core.ai_model_ops.request("synthetic model prompt", {
					agent_id = ctx.agent_id,
					owner = ctx.owner,
					task_id = ctx.task_id,
					adapter = function()
						error("adapter should not be called without http.llm")
					end,
				})
			end,
		},
	})
	core.step_ai_tasks()
	local denied_model_task = core.get_ai_task("runtime-gate:model-denied")
	assert(denied_model_task.status == "blocked")
	assert(denied_model_task.last_result.operation == "ai_model.request")
	assert(denied_model_task.last_result.reason == "missing_capability")

	local model_requests = {}
	local before_gate_model_metrics = core.get_ai_runtime_metrics()
	core.queue_ai_task({
		task_id = "runtime-gate:model-success",
		agent_id = "runtime_gate:http",
		owner = "runtime-owner",
		label = "allowed model runtime gate",
		steps = {
			function(ctx)
				return core.ai_model_ops.request("runtime model request", {
					agent_id = ctx.agent_id,
					owner = ctx.owner,
					task_id = ctx.task_id,
					private_prompt = "synthetic private model prompt",
					adapter = function(request)
						table.insert(model_requests, request)
						return {
							ok = true,
							message = "runtime model response",
							adapter_name = "runtime-gate-model",
							elapsed_us = 25000,
						}
					end,
				})
			end,
		},
	})
	core.step_ai_tasks()
	local allowed_model_task = core.get_ai_task("runtime-gate:model-success")
	assert(allowed_model_task.status == "completed")
	assert(allowed_model_task.last_result.operation == "ai_model.request")
	assert(allowed_model_task.last_result.status == "success")
	assert(allowed_model_task.last_result.message == "runtime model response")
	assert(#model_requests == 1)
	assert(model_requests[1].agent_id == "runtime_gate:http")
	local after_gate_model_metrics = core.get_ai_runtime_metrics()
	assert(after_gate_model_metrics.model_adapter_requests
		== before_gate_model_metrics.model_adapter_requests + 1)

	core.queue_ai_task({
		task_id = "runtime-gate:import-denied",
		agent_id = "runtime_gate:none",
		owner = "runtime-owner",
		label = "denied import runtime gate",
		steps = {
			function(ctx)
				return core.ai_import_ops.plan({
					source_class = "resource_pack",
					dry_run = true,
					planned_actions = {},
				}, {
					agent_id = ctx.agent_id,
					owner = ctx.owner,
					task_id = ctx.task_id,
				})
			end,
		},
	})
	core.step_ai_tasks()
	local denied_import_task = core.get_ai_task("runtime-gate:import-denied")
	assert(denied_import_task.status == "blocked")
	assert(denied_import_task.last_result.operation == "ai_import.plan")
	assert(denied_import_task.last_result.reason == "missing_capability")

	core.queue_ai_task({
		task_id = "runtime-gate:import-payload-blocked",
		agent_id = "runtime_gate:import",
		owner = "runtime-owner",
		label = "blocked import payload runtime gate",
		steps = {
			function(ctx)
				return core.ai_import_ops.plan({
					source = {
						source_id = "synthetic-pack",
						source_class = "bedrock_resource_pack",
						inventory = {
							{
								entry_id = "entry:1",
								source_path = "textures/example.png",
								classification = "mapped",
								required_capabilities = { "import.assets" },
								asset_payload = "must not be retained",
							},
						},
					},
					dry_run = true,
					planned_actions = {
						{
							action = "map_texture",
							status = "partial",
							required_capabilities = { "import.assets" },
						},
					},
				}, {
					agent_id = ctx.agent_id,
					owner = ctx.owner,
					task_id = ctx.task_id,
				})
			end,
		},
	})
	core.step_ai_tasks()
	local blocked_payload_import_task = core.get_ai_task("runtime-gate:import-payload-blocked")
	assert(blocked_payload_import_task.status == "blocked")
	assert(blocked_payload_import_task.last_result.operation == "ai_import.plan")
	assert(blocked_payload_import_task.last_result.reason == "payload_rejected")

	core.queue_ai_task({
		task_id = "runtime-gate:import-plan",
		agent_id = "runtime_gate:import",
		owner = "runtime-owner",
		label = "allowed import runtime gate",
		steps = {
			function(ctx)
				return core.ai_import_ops.plan({
					source = {
						source_id = "synthetic-pack",
						source_class = "bedrock_resource_pack",
						inventory = {
							{
								entry_id = "entry:1",
								source_path = "textures/example.png",
								source_kind = "texture",
								classification = "mapped",
								reason = "metadata_or_asset_reference",
								required_capabilities = { "import.assets" },
							},
						},
						content_hashes = {
							{
								algorithm = "sha256",
								value = string.rep("0", 64),
								purpose = "synthetic inventory hash",
							},
						},
					},
					dry_run = true,
					planned_actions = {
						{
							action = "map_texture",
							status = "partial",
							required_capabilities = { "import.assets" },
							provenance = {
								source_id = "synthetic-pack",
								inventory_refs = { "entry:1" },
								classification = "mapped",
							},
							mutation_cost = {
								node_writes = 0,
								media_files = 1,
								manual_review_items = 0,
							},
						},
					},
				}, {
					agent_id = ctx.agent_id,
					owner = ctx.owner,
					task_id = ctx.task_id,
				})
			end,
		},
	})
	core.step_ai_tasks()
	local import_plan_task = core.get_ai_task("runtime-gate:import-plan")
	assert(import_plan_task.status == "completed")
	assert(import_plan_task.last_result.operation == "ai_import.plan")
	assert(import_plan_task.last_result.status == "success")
	assert(import_plan_task.last_result.import_plan.dry_run == true)
	assert(import_plan_task.last_result.import_plan.assets_copied == false)
	assert(import_plan_task.last_result.import_plan.source_id == "synthetic-pack")
	assert(import_plan_task.last_result.import_plan.source_class == "bedrock_resource_pack")
	assert(import_plan_task.last_result.import_plan.inventory_count == 1)
	assert(import_plan_task.last_result.import_plan.source_inventory[1].classification == "mapped")
	assert(import_plan_task.last_result.import_plan.source_inventory[1].asset_payload == nil)
	assert(import_plan_task.last_result.import_plan.planned_actions[1].provenance.inventory_refs[1] == "entry:1")
	assert(import_plan_task.last_result.import_plan.source_content_hashes[1].algorithm == "sha256")
	assert(import_plan_task.last_result.examined == 1)

	local gate_audit = core.get_ai_runtime_audit({ limit = 30 })
	local has_model_request = false
	local has_import_plan = false
	for _, record in ipairs(gate_audit) do
		if record.event_type == "model.request"
				and record.task_id == "runtime-gate:model-success" then
			has_model_request = true
			assert(record.private_payload == nil)
			assert(record.payload_retained == false)
		end
		if record.event_type == "import.plan"
				and record.task_id == "runtime-gate:import-plan" then
			has_import_plan = true
			assert(record.private_payload == nil)
			assert(record.payload_retained == false)
		end
	end
	assert(has_model_request == true)
	assert(has_import_plan == true)
end

run_model_import_gate_tests()

local function run_compat_structure_apply_tests()
	core.ai_rollback_storage.configure(nil)
	core.register_ai_agent({
		agent_id = "compat_import:runtime",
		display_name = "Compatibility Runtime Import Agent",
		owner = "compat-operator",
		plugin = "compat_import_test",
		capabilities = {
			["import.assets"] = true,
			["world.place"] = true,
			["world.batch"] = true,
		},
	})
	core.register_ai_agent({
		agent_id = "compat_import:no_batch",
		display_name = "Compatibility Missing Batch Agent",
		owner = "compat-operator",
		plugin = "compat_import_test",
		capabilities = {
			["import.assets"] = true,
			["world.place"] = true,
		},
	})
	core.register_ai_agent({
		agent_id = "compat_rollback:runtime",
		display_name = "Compatibility Runtime Rollback Agent",
		owner = "compat-operator",
		plugin = "compat_import_test",
		capabilities = {
			["rollback.execute"] = true,
			["admin.override"] = true,
			["world.place"] = true,
			["world.batch"] = true,
		},
	})
	core.register_ai_agent({
		agent_id = "compat_rollback:no_admin",
		display_name = "Compatibility Rollback Missing Admin Agent",
		owner = "compat-operator",
		plugin = "compat_import_test",
		capabilities = {
			["rollback.execute"] = true,
			["world.place"] = true,
			["world.batch"] = true,
		},
	})

	local apply_base = test_pos(4500)
	local function structure_placements(origin)
		return {
			{
				pos = vector.add(origin, { x = 0, y = 0, z = 0 }),
				node_name = "ai_runtime_test:stone",
			},
			{
				pos = vector.add(origin, { x = 1, y = 0, z = 0 }),
				node_name = "ai_runtime_test:stone",
			},
		}
	end

	local structure_writes = 0
	local function counting_structure_set_node(pos, node)
		structure_writes = structure_writes + 1
		return set_test_node(pos, node)
	end

	local rollback_records = {}
	local apply_success_origin = vector.add(apply_base, { x = 0, y = 0, z = 0 })
	for _, placement in ipairs(structure_placements(apply_success_origin)) do
		set_test_node(placement.pos, { name = "air" })
	end
	local apply_task = core.ai_import_ops.define_structure_apply_task({
		task_id = "compat-structure:success",
		agent_id = "compat_import:runtime",
		owner = "compat-operator",
		report_id = "synthetic-structure-report",
		action_index = 0,
		world_id = "staging-world",
		staging = true,
		explicit_approval = true,
		allow_mutation = true,
		rollback_policy = "manifest_only",
		placements = structure_placements(apply_success_origin),
		get_node = get_test_node,
		set_node = counting_structure_set_node,
		max_node_writes_per_step = 2,
		max_mapblock_churn_total = 1,
		max_wall_time_ms = 5000,
		source_reference = {
			reference_type = "mounted_fixture",
			redacted_id = "synthetic-structure-fixture",
			inventory_hash = string.rep("1", 64),
		},
		persist_record = function(record)
			assert(structure_writes == 0)
			rollback_records[#rollback_records + 1] = record
			return {
				ok = true,
				storage_ref = "rollback://compat/" .. record.record_id,
			}
		end,
	})
	assert(apply_task.required_capabilities["import.assets"] == true)
	assert(apply_task.required_capabilities["world.place"] == true)
	assert(apply_task.required_capabilities["world.batch"] == true)
	assert(apply_task.mutation_class == "compat_import")
	assert(apply_task.metadata.placement_count == 2)
	assert(apply_task.metadata.source_reference.redacted_id == "synthetic-structure-fixture")
	assert(apply_task.metadata.source_reference.payload == nil)
	core.queue_ai_task(apply_task)
	local queued_summary = core.ai_import_ops.build_apply_summary({
		apply_id = "apply-runtime:queued",
		report_id = "synthetic-structure-report",
		task_ids = {
			"compat-structure:success",
		},
		approved_actions = {
			{ action_index = 0, action = "import_structure" },
		},
		rollback_policy = "manifest_only",
	})
	assert(queued_summary.status == "queued")
	assert(#queued_summary.queued_tasks == 1)
	assert(#queued_summary.running_tasks == 0)
	core.step_ai_tasks()
	local completed_apply = core.get_ai_task("compat-structure:success")
	assert(completed_apply.status == "completed")
	assert(completed_apply.last_result.operation == "ai_world.batch_place")
	assert(completed_apply.last_result.changed == 2)
	assert(completed_apply.last_result.rollback_record_id ~= nil)
	assert(completed_apply.last_result.rollback_storage_ref ~= nil)
	assert(completed_apply.last_result.metrics.rollback_records == 1)
	assert(completed_apply.last_result.metrics.mapblock_churn == 1)
	assert(#rollback_records == 1)
	assert(rollback_records[1].mutation_class == "compat_import")
	assert(rollback_records[1].operation_label == "compat.structure.apply")
	assert(rollback_records[1].policy == "manifest")
	assert(#rollback_records[1].changed_positions == 2)
	assert(get_test_node(vector.add(apply_success_origin, { x = 0, y = 0, z = 0 })).name
		== "ai_runtime_test:stone")
	assert(get_test_node(vector.add(apply_success_origin, { x = 1, y = 0, z = 0 })).name
		== "ai_runtime_test:stone")

	local over_budget_origin = vector.add(apply_base, { x = 16, y = 0, z = 0 })
	for _, placement in ipairs(structure_placements(over_budget_origin)) do
		set_test_node(placement.pos, { name = "air" })
	end
	local writes_before_budget = structure_writes
	core.ai_import_ops.queue_structure_apply_task({
		task_id = "compat-structure:over-budget",
		agent_id = "compat_import:runtime",
		owner = "compat-operator",
		world_id = "staging-world",
		staging = true,
		explicit_approval = true,
		allow_mutation = true,
		rollback_policy = "snapshot",
		placements = structure_placements(over_budget_origin),
		get_node = get_test_node,
		set_node = counting_structure_set_node,
		max_node_writes_per_step = 1,
		max_mapblock_churn_total = 1,
		persist_record = function()
			error("rollback must not be written for over-budget apply")
		end,
	})
	core.step_ai_tasks()
	local over_budget_task = core.get_ai_task("compat-structure:over-budget")
	assert(over_budget_task.status == "blocked")
	assert(over_budget_task.last_result.operation == "ai_import.structure_apply")
	assert(over_budget_task.last_result.reason == "node_write_budget_exceeded")
	assert(over_budget_task.last_result.changed == 0)
	assert(structure_writes == writes_before_budget)
	assert(get_test_node(vector.add(over_budget_origin, { x = 0, y = 0, z = 0 })).name == "air")

	local no_rollback_origin = vector.add(apply_base, { x = 32, y = 0, z = 0 })
	for _, placement in ipairs(structure_placements(no_rollback_origin)) do
		set_test_node(placement.pos, { name = "air" })
	end
	local writes_before_missing_rollback = structure_writes
	core.ai_import_ops.queue_structure_apply_task({
		task_id = "compat-structure:missing-rollback",
		agent_id = "compat_import:runtime",
		owner = "compat-operator",
		world_id = "staging-world",
		staging = true,
		explicit_approval = true,
		allow_mutation = true,
		rollback_policy = "snapshot",
		placements = structure_placements(no_rollback_origin),
		get_node = get_test_node,
		set_node = counting_structure_set_node,
		max_node_writes_per_step = 2,
		max_mapblock_churn_total = 1,
	})
	core.step_ai_tasks()
	local missing_rollback_task = core.get_ai_task("compat-structure:missing-rollback")
	assert(missing_rollback_task.status == "blocked")
	assert(missing_rollback_task.last_result.operation == "ai_import.structure_apply")
	assert(missing_rollback_task.last_result.reason == "rollback_metadata_unavailable")
	assert(missing_rollback_task.last_result.metrics.rollback_failures == 1)
	assert(structure_writes == writes_before_missing_rollback)

	local missing_cap_origin = vector.add(apply_base, { x = 48, y = 0, z = 0 })
	for _, placement in ipairs(structure_placements(missing_cap_origin)) do
		set_test_node(placement.pos, { name = "air" })
	end
	local writes_before_missing_cap = structure_writes
	core.ai_import_ops.queue_structure_apply_task({
		task_id = "compat-structure:missing-capability",
		agent_id = "compat_import:no_batch",
		owner = "compat-operator",
		world_id = "staging-world",
		staging = true,
		explicit_approval = true,
		allow_mutation = true,
		rollback_policy = "snapshot",
		placements = structure_placements(missing_cap_origin),
		get_node = get_test_node,
		set_node = counting_structure_set_node,
		max_node_writes_per_step = 2,
		max_mapblock_churn_total = 1,
		persist_record = function()
			error("rollback must not be written when capability is missing")
		end,
	})
	core.step_ai_tasks()
	local missing_cap_task = core.get_ai_task("compat-structure:missing-capability")
	assert(missing_cap_task.status == "blocked")
	assert(missing_cap_task.last_result.reason == "missing_capability")
	assert(structure_writes == writes_before_missing_cap)

	local no_mutation_origin = vector.add(apply_base, { x = 64, y = 0, z = 0 })
	for _, placement in ipairs(structure_placements(no_mutation_origin)) do
		set_test_node(placement.pos, { name = "air" })
	end
	local writes_before_no_mutation = structure_writes
	core.ai_import_ops.queue_structure_apply_task({
		task_id = "compat-structure:no-mutation",
		agent_id = "compat_import:runtime",
		owner = "compat-operator",
		world_id = "staging-world",
		staging = true,
		explicit_approval = true,
		allow_mutation = false,
		rollback_policy = "snapshot",
		placements = structure_placements(no_mutation_origin),
		get_node = get_test_node,
		set_node = counting_structure_set_node,
		max_node_writes_per_step = 2,
		max_mapblock_churn_total = 1,
		persist_record = function()
			error("rollback must not be written when mutation is disabled")
		end,
	})
	core.step_ai_tasks()
	local no_mutation_task = core.get_ai_task("compat-structure:no-mutation")
	assert(no_mutation_task.status == "blocked")
	assert(no_mutation_task.last_result.reason == "structure_mutation_not_enabled")
	assert(structure_writes == writes_before_no_mutation)

	local protected_origin = vector.add(apply_base, { x = 80, y = 0, z = 0 })
	for _, placement in ipairs(structure_placements(protected_origin)) do
		set_test_node(placement.pos, { name = "air" })
	end
	local protected_records = {}
	local old_protected = core.is_protected
	core.is_protected = function(pos, name)
		return name == "compat-operator" and pos.x == protected_origin.x
	end
	local writes_before_protected = structure_writes
	core.ai_import_ops.queue_structure_apply_task({
		task_id = "compat-structure:protected",
		agent_id = "compat_import:runtime",
		owner = "compat-operator",
		world_id = "staging-world",
		staging = true,
		explicit_approval = true,
		allow_mutation = true,
		rollback_policy = "snapshot",
		placements = {
			{
				pos = protected_origin,
				node_name = "ai_runtime_test:stone",
			},
		},
		get_node = get_test_node,
		set_node = counting_structure_set_node,
		max_node_writes_per_step = 1,
		max_mapblock_churn_total = 1,
		persist_record = function(record)
			protected_records[#protected_records + 1] = record
			return "rollback://compat/" .. record.record_id
		end,
	})
	core.step_ai_tasks()
	core.is_protected = old_protected
	local protected_task = core.get_ai_task("compat-structure:protected")
	assert(protected_task.status == "blocked")
	assert(protected_task.last_result.operation == "ai_world.batch_place")
	assert(protected_task.last_result.reason == "all_operations_skipped")
	assert(protected_task.last_result.samples[1].reason == "protected_area")
	assert(protected_task.last_result.changed == 0)
	assert(#protected_records == 1)
	assert(structure_writes == writes_before_protected)

	local private_origin = vector.add(apply_base, { x = 96, y = 0, z = 0 })
	for _, placement in ipairs(structure_placements(private_origin)) do
		set_test_node(placement.pos, { name = "air" })
	end
	local private_definition = core.ai_import_ops.define_structure_apply_task({
		task_id = "compat-structure:privacy",
		agent_id = "compat_import:runtime",
		owner = "compat-operator",
		world_id = "staging-world",
		staging = true,
		explicit_approval = true,
		allow_mutation = true,
		rollback_policy = "snapshot",
		placements = structure_placements(private_origin),
		get_node = get_test_node,
		set_node = counting_structure_set_node,
		max_node_writes_per_step = 2,
		max_mapblock_churn_total = 1,
		source_reference = {
			reference_type = "mounted_fixture",
			redacted_id = "synthetic-private-fixture",
			inventory_hash = string.rep("2", 64),
			payload = "must not be retained",
		},
		private_payload = {
			secret = "must not be retained",
		},
		persist_record = function()
			error("rollback must not be written when payload is rejected")
		end,
	})
	assert(private_definition.metadata.source_reference.redacted_id == "synthetic-private-fixture")
	assert(private_definition.metadata.source_reference.payload == nil)
	core.queue_ai_task(private_definition)
	core.step_ai_tasks()
	local private_task = core.get_ai_task("compat-structure:privacy")
	assert(private_task.status == "blocked")
	assert(private_task.last_result.reason == "payload_rejected")
	assert(private_task.last_result.changed == 0)

	core.queue_ai_task({
		task_id = "compat-structure:running",
		agent_id = "compat_import:runtime",
		owner = "compat-operator",
		label = "compat.structure.place",
		budget = {
			max_steps_per_step = 1,
		},
		steps = {
			function()
				return {
					ok = true,
					status = "success",
					changed = 0,
				}
			end,
			function()
				return {
					ok = true,
					status = "success",
					changed = 0,
				}
			end,
		},
	})
	core.step_ai_tasks()
	local apply_summary = core.ai_import_ops.build_apply_summary({
		apply_id = "apply-runtime:final",
		report_id = "synthetic-structure-report",
		task_ids = {
			"compat-structure:success",
			"compat-structure:over-budget",
			"compat-structure:running",
		},
		approved_actions = {
			{ action_index = 0, action = "import_structure" },
		},
		rollback_policy = "manifest_only",
	})
	assert(apply_summary.status == "blocked")
	assert(#apply_summary.completed_tasks == 1)
	assert(#apply_summary.blocked_tasks == 1)
	assert(#apply_summary.running_tasks == 1)
	assert(apply_summary.completed_tasks[1].status == "completed")
	assert(apply_summary.blocked_tasks[1].status == "blocked")
	assert(apply_summary.running_tasks[1].status == "running")
	assert(apply_summary.mutation_cost_actual.node_writes >= 2)
	assert(apply_summary.mutation_cost_actual.mapblock_churn >= 1)
	assert(#apply_summary.rollback_records >= 1)
	assert(apply_summary.safety.assets_remain_operator_supplied == true)
	assert(apply_summary.safety.dry_run_report_unchanged == true)
	assert(apply_summary.safety.world_mutation_executed == true)
	core.step_ai_tasks()
	assert(core.get_ai_task("compat-structure:running").status == "completed")

	local function many_structure_placements(origin, count)
		local placements = {}
		for index = 0, count - 1 do
			placements[#placements + 1] = {
				pos = vector.add(origin, { x = index * 17, y = 0, z = 0 }),
				node_name = "ai_runtime_test:stone",
			}
		end
		return placements
	end

	local chunk_origin = vector.add(apply_base, { x = 128, y = 0, z = 0 })
	local chunk_placements = many_structure_placements(chunk_origin, 5)
	for _, placement in ipairs(chunk_placements) do
		set_test_node(placement.pos, { name = "air" })
	end
	local chunk_records = {}
	local chunk_storage = {}
	local writes_before_chunk_success = structure_writes
	core.ai_import_ops.queue_chunked_structure_apply_task({
		task_id = "compat-structure:chunked-success",
		agent_id = "compat_import:runtime",
		owner = "compat-operator",
		report_id = "synthetic-structure-report",
		action_index = 1,
		world_id = "staging-world",
		staging = true,
		explicit_approval = true,
		allow_mutation = true,
		rollback_policy = "chunked",
		placements = chunk_placements,
		get_node = get_test_node,
		set_node = counting_structure_set_node,
		chunk_size = 2,
		max_node_writes_total = 5,
		max_node_writes_per_step = 2,
		max_mapblock_churn_total = 5,
		max_wall_time_ms = 5000,
		persist_record = function(record)
			assert(structure_writes == writes_before_chunk_success
				+ record.chunk.first_position_index)
			chunk_records[#chunk_records + 1] = record
			local storage_ref = "rollback://compat-chunk/" .. record.record_id
			chunk_storage[storage_ref] = record
			return {
				ok = true,
				storage_ref = storage_ref,
			}
		end,
	})
	core.step_ai_tasks()
	assert(core.get_ai_task("compat-structure:chunked-success").status == "running")
	core.step_ai_tasks()
	assert(core.get_ai_task("compat-structure:chunked-success").status == "running")
	core.step_ai_tasks()
	local chunked_success = core.get_ai_task("compat-structure:chunked-success")
	assert(chunked_success.status == "completed")
	assert(chunked_success.progress.current == 3)
	assert(chunked_success.progress.total == 3)
	assert(#chunk_records == 3)
	assert(chunk_records[1].chunk.chunk_index == 0)
	assert(chunk_records[1].chunk.chunk_count == 3)
	assert(chunk_records[1].chunk.first_position_index == 0)
	assert(chunk_records[1].chunk.position_count == 2)
	assert(chunk_records[2].chunk.chunk_index == 1)
	assert(chunk_records[2].chunk.first_position_index == 2)
	assert(chunk_records[3].chunk.chunk_index == 2)
	assert(chunk_records[3].chunk.first_position_index == 4)
	assert(chunk_records[3].chunk.position_count == 1)
	assert(structure_writes == writes_before_chunk_success + 5)

	core.ai_rollback_storage.configure({
		enabled = true,
		inspect_record = function(storage_ref)
			return chunk_storage[storage_ref]
		end,
	})
	local rollback_plan = core.ai_import_ops.plan_structure_rollback({
		agent_id = "compat_import:runtime",
		task_id = "compat-structure:chunked-success",
		owner = "compat-operator",
	})
	assert(rollback_plan.ok == true)
	assert(rollback_plan.status == "success")
	assert(rollback_plan.operation == "ai_import.rollback_plan")
	assert(rollback_plan.changed == 0)
	assert(rollback_plan.rollback_plan.will_mutate == false)
	assert(#rollback_plan.rollback_records == 3)
	assert(#rollback_plan.rollback_plan.chunks == 3)
	assert(rollback_plan.metrics.rollback_records == 3)
	assert(rollback_plan.metrics.planned_node_writes == 5)
	assert(rollback_plan.metrics.mapblock_churn >= 3)
	assert(rollback_plan.rollback_records[1].storage_ref:find(
		"rollback://compat-chunk/", 1, true))
	assert(rollback_plan.rollback_records[1].record.record_id ~= nil)

	local missing_readback = core.ai_import_ops.plan_structure_rollback({
		agent_id = "compat_import:runtime",
		owner = "compat-operator",
		rollback_refs = {
			"rollback://compat-chunk/missing",
			chunk_records[1].storage_ref,
		},
		rollback_records = {
			chunk_records[2],
		},
	})
	assert(missing_readback.ok == true)
	assert(missing_readback.status == "partial")
	assert(missing_readback.reason == "rollback_plan_with_missing_records")
	assert(missing_readback.changed == 0)
	assert(#missing_readback.rollback_records == 2)
	assert(#missing_readback.rollback_plan.missing_records == 1)

	local rollback_execute_records = {}
	local writes_before_rollback_success = structure_writes
	core.ai_rollback_storage.configure({
		enabled = true,
		inspect_record = function(storage_ref)
			return chunk_storage[storage_ref]
		end,
		persist_record = function(record)
			local expected_writes_before = { 0, 1, 3 }
			local ordinal = #rollback_execute_records + 1
			assert(structure_writes == writes_before_rollback_success
				+ expected_writes_before[ordinal])
			rollback_execute_records[#rollback_execute_records + 1] = record
			return {
				ok = true,
				storage_ref = "rollback://compat-rollback/" .. record.record_id,
			}
		end,
	})
	local rollback_definition =
		core.ai_import_ops.define_chunked_structure_rollback_task({
			task_id = "compat-rollback:success",
			agent_id = "compat_rollback:runtime",
			owner = "compat-operator",
			source_task_id = "compat-structure:chunked-success",
			world_id = "staging-world",
			staging = true,
			explicit_approval = true,
			allow_mutation = true,
			rollback_policy = "chunked",
			get_node = get_test_node,
			set_node = counting_structure_set_node,
			max_node_writes_total = 5,
			max_node_writes_per_step = 2,
			max_mapblock_churn_total = 5,
			max_wall_time_ms = 5000,
		})
	assert(rollback_definition.required_capabilities["rollback.execute"] == true)
	assert(rollback_definition.required_capabilities["admin.override"] == true)
	assert(rollback_definition.required_capabilities["world.place"] == true)
	assert(rollback_definition.required_capabilities["world.batch"] == true)
	assert(rollback_definition.metadata.reverse_order == true)
	core.queue_ai_task(rollback_definition)
	core.step_ai_tasks()
	assert(core.get_ai_task("compat-rollback:success").status == "running")
	core.step_ai_tasks()
	assert(core.get_ai_task("compat-rollback:success").status == "running")
	core.step_ai_tasks()
	local rollback_success = core.get_ai_task("compat-rollback:success")
	assert(rollback_success.status == "completed")
	assert(rollback_success.progress.current == 3)
	assert(rollback_success.progress.total == 3)
	assert(rollback_success.last_result.operation == "ai_import.rollback_execute")
	assert(rollback_success.last_result.changed == 2)
	assert(rollback_success.last_result.metrics.rollback_records == 1)
	assert(rollback_success.last_result.source_rollback_record_id
		== chunk_records[1].record_id)
	assert(#rollback_execute_records == 3)
	assert(rollback_execute_records[1].chunk.chunk_index == 2)
	assert(rollback_execute_records[2].chunk.chunk_index == 1)
	assert(rollback_execute_records[3].chunk.chunk_index == 0)
	assert(structure_writes == writes_before_rollback_success + 5)
	for _, placement in ipairs(chunk_placements) do
		assert(get_test_node(placement.pos).name == "air")
	end

	local writes_before_missing_rollback_execute = structure_writes
	local unexpected_rollback_persist = 0
	core.ai_rollback_storage.configure({
		enabled = true,
		inspect_record = function()
			return nil
		end,
		persist_record = function()
			unexpected_rollback_persist = unexpected_rollback_persist + 1
			error("rollback must not be written when source rollback records are missing")
		end,
	})
	core.ai_import_ops.queue_chunked_structure_rollback_task({
		task_id = "compat-rollback:missing-record",
		agent_id = "compat_rollback:runtime",
		owner = "compat-operator",
		rollback_refs = {
			"rollback://compat-chunk/missing",
		},
		world_id = "staging-world",
		staging = true,
		explicit_approval = true,
		allow_mutation = true,
		rollback_policy = "chunked",
		get_node = get_test_node,
		set_node = counting_structure_set_node,
		max_node_writes_total = 5,
		max_node_writes_per_step = 2,
		max_mapblock_churn_total = 5,
	})
	core.step_ai_tasks()
	local missing_record_rollback = core.get_ai_task(
		"compat-rollback:missing-record")
	assert(missing_record_rollback.status == "blocked")
	assert(missing_record_rollback.last_result.reason
		== "rollback_records_unavailable")
	assert(structure_writes == writes_before_missing_rollback_execute)
	assert(unexpected_rollback_persist == 0)

	local writes_before_no_approval_rollback = structure_writes
	core.ai_rollback_storage.configure({
		enabled = true,
		persist_record = function()
			error("rollback must not be written without explicit approval")
		end,
	})
	core.ai_import_ops.queue_chunked_structure_rollback_task({
		task_id = "compat-rollback:no-approval",
		agent_id = "compat_rollback:runtime",
		owner = "compat-operator",
		rollback_records = {
			chunk_records[1],
		},
		world_id = "staging-world",
		staging = true,
		explicit_approval = false,
		allow_mutation = true,
		rollback_policy = "chunked",
		get_node = get_test_node,
		set_node = counting_structure_set_node,
		max_node_writes_total = 2,
		max_node_writes_per_step = 2,
		max_mapblock_churn_total = 2,
	})
	core.step_ai_tasks()
	local no_approval_rollback = core.get_ai_task("compat-rollback:no-approval")
	assert(no_approval_rollback.status == "blocked")
	assert(no_approval_rollback.last_result.reason == "approval_required")
	assert(no_approval_rollback.last_result.changed == 0)
	assert(structure_writes == writes_before_no_approval_rollback)

	local writes_before_no_admin_rollback = structure_writes
	core.ai_rollback_storage.configure({
		enabled = true,
		persist_record = function()
			error("rollback must not be written without admin override")
		end,
	})
	core.ai_import_ops.queue_chunked_structure_rollback_task({
		task_id = "compat-rollback:no-admin",
		agent_id = "compat_rollback:no_admin",
		owner = "compat-operator",
		rollback_records = {
			chunk_records[1],
		},
		world_id = "staging-world",
		staging = true,
		explicit_approval = true,
		allow_mutation = true,
		rollback_policy = "chunked",
		get_node = get_test_node,
		set_node = counting_structure_set_node,
		max_node_writes_total = 2,
		max_node_writes_per_step = 2,
		max_mapblock_churn_total = 2,
	})
	core.step_ai_tasks()
	local no_admin_rollback = core.get_ai_task("compat-rollback:no-admin")
	assert(no_admin_rollback.status == "blocked")
	assert(no_admin_rollback.last_result.reason == "admin_override_required")
	assert(no_admin_rollback.last_result.changed == 0)
	assert(structure_writes == writes_before_no_admin_rollback)

	local writes_before_rollback_budget = structure_writes
	core.ai_rollback_storage.configure({
		enabled = true,
		persist_record = function()
			error("rollback must not be written for over-budget rollback")
		end,
	})
	core.ai_import_ops.queue_chunked_structure_rollback_task({
		task_id = "compat-rollback:total-over-budget",
		agent_id = "compat_rollback:runtime",
		owner = "compat-operator",
		rollback_records = chunk_records,
		world_id = "staging-world",
		staging = true,
		explicit_approval = true,
		allow_mutation = true,
		rollback_policy = "chunked",
		get_node = get_test_node,
		set_node = counting_structure_set_node,
		max_node_writes_total = 2,
		max_node_writes_per_step = 2,
		max_mapblock_churn_total = 5,
	})
	core.step_ai_tasks()
	local rollback_total_budget = core.get_ai_task(
		"compat-rollback:total-over-budget")
	assert(rollback_total_budget.status == "blocked")
	assert(rollback_total_budget.last_result.reason
		== "node_write_total_budget_exceeded")
	assert(rollback_total_budget.last_result.changed == 0)
	assert(structure_writes == writes_before_rollback_budget)

	local protected_rollback_records = {}
	local protected_rollback_pos = chunk_records[1].previous_nodes[2].pos
	local old_rollback_protected = core.is_protected
	core.is_protected = function(pos, name)
		return name == "compat-operator" and pos.x == protected_rollback_pos.x
	end
	local writes_before_protected_rollback = structure_writes
	core.ai_rollback_storage.configure({
		enabled = true,
		persist_record = function(record)
			protected_rollback_records[#protected_rollback_records + 1] = record
			return {
				ok = true,
				storage_ref = "rollback://compat-rollback-protected/" .. record.record_id,
			}
		end,
	})
	core.ai_import_ops.queue_chunked_structure_rollback_task({
		task_id = "compat-rollback:protected",
		agent_id = "compat_rollback:runtime",
		owner = "compat-operator",
		rollback_records = {
			chunk_records[1],
		},
		world_id = "staging-world",
		staging = true,
		explicit_approval = true,
		allow_mutation = true,
		rollback_policy = "chunked",
		get_node = get_test_node,
		set_node = counting_structure_set_node,
		max_node_writes_total = 2,
		max_node_writes_per_step = 2,
		max_mapblock_churn_total = 2,
	})
	core.step_ai_tasks()
	core.is_protected = old_rollback_protected
	local protected_rollback = core.get_ai_task("compat-rollback:protected")
	assert(protected_rollback.status == "completed")
	assert(protected_rollback.last_result.operation == "ai_import.rollback_execute")
	assert(protected_rollback.last_result.status == "partial")
	assert(protected_rollback.last_result.changed == 1)
	assert(protected_rollback.last_result.skipped == 1)
	assert(protected_rollback.last_result.samples[1].reason == "protected_area")
	assert(#protected_rollback_records == 1)
	assert(structure_writes == writes_before_protected_rollback + 1)

	local summary_rollback_records = {}
	core.ai_rollback_storage.configure({
		enabled = true,
		persist_record = function(record)
			summary_rollback_records[#summary_rollback_records + 1] = record
			return {
				ok = true,
				storage_ref = "rollback://compat-rollback-summary/" .. record.record_id,
			}
		end,
	})
	core.ai_import_ops.queue_chunked_structure_rollback_task({
		task_id = "compat-rollback:running",
		agent_id = "compat_rollback:runtime",
		owner = "compat-operator",
		rollback_records = {
			chunk_records[2],
			chunk_records[3],
		},
		world_id = "staging-world",
		staging = true,
		explicit_approval = true,
		allow_mutation = true,
		rollback_policy = "chunked",
		get_node = get_test_node,
		set_node = counting_structure_set_node,
		max_node_writes_total = 3,
		max_node_writes_per_step = 2,
		max_mapblock_churn_total = 3,
	})
	core.ai_import_ops.queue_chunked_structure_rollback_task({
		task_id = "compat-rollback:queued",
		agent_id = "compat_rollback:runtime",
		owner = "compat-operator",
		rollback_records = {
			chunk_records[1],
		},
		world_id = "staging-world",
		staging = true,
		explicit_approval = true,
		allow_mutation = true,
		rollback_policy = "chunked",
		get_node = get_test_node,
		set_node = counting_structure_set_node,
		max_node_writes_total = 2,
		max_node_writes_per_step = 2,
		max_mapblock_churn_total = 2,
	})
	core.step_ai_tasks()
	assert(core.get_ai_task("compat-rollback:running").status == "running")
	assert(core.get_ai_task("compat-rollback:queued").status == "queued")
	local rollback_summary = core.ai_import_ops.build_rollback_summary({
		rollback_id = "rollback-runtime:final",
		task_ids = {
			"compat-rollback:success",
			"compat-rollback:no-approval",
			"compat-rollback:protected",
			"compat-rollback:running",
			"compat-rollback:queued",
		},
	})
	assert(rollback_summary.status == "blocked")
	assert(#rollback_summary.completed_tasks == 2)
	assert(#rollback_summary.blocked_tasks == 1)
	assert(#rollback_summary.running_tasks == 1)
	assert(#rollback_summary.queued_tasks == 1)
	assert(rollback_summary.mutation_cost_actual.node_writes >= 7)
	assert(rollback_summary.mutation_cost_actual.mapblock_churn >= 7)
	assert(#rollback_summary.rollback_records >= 5)
	assert(#rollback_summary.source_rollback_records >= 5)
	assert(rollback_summary.safety.rollback_of_rollback_required == true)
	assert(rollback_summary.safety.world_mutation_executed == true)
	core.step_ai_tasks()
	assert(core.get_ai_task("compat-rollback:running").status == "completed")
	core.step_ai_tasks()
	assert(core.get_ai_task("compat-rollback:queued").status == "completed")
	core.ai_rollback_storage.configure(nil)

	local chunk_over_budget_origin = vector.add(apply_base, { x = 256, y = 0, z = 0 })
	local over_budget_chunk_placements = many_structure_placements(chunk_over_budget_origin, 3)
	for _, placement in ipairs(over_budget_chunk_placements) do
		set_test_node(placement.pos, { name = "air" })
	end
	local writes_before_chunk_budget = structure_writes
	core.ai_import_ops.queue_chunked_structure_apply_task({
		task_id = "compat-structure:chunk-over-budget",
		agent_id = "compat_import:runtime",
		owner = "compat-operator",
		world_id = "staging-world",
		staging = true,
		explicit_approval = true,
		allow_mutation = true,
		rollback_policy = "chunked",
		placements = over_budget_chunk_placements,
		get_node = get_test_node,
		set_node = counting_structure_set_node,
		chunk_size = 3,
		max_node_writes_total = 3,
		max_node_writes_per_step = 2,
		max_mapblock_churn_total = 3,
		persist_record = function()
			error("rollback must not be written for over-budget chunk")
		end,
	})
	core.step_ai_tasks()
	local chunk_over_budget = core.get_ai_task("compat-structure:chunk-over-budget")
	assert(chunk_over_budget.status == "blocked")
	assert(chunk_over_budget.last_result.reason == "node_write_budget_exceeded")
	assert(chunk_over_budget.last_result.changed == 0)
	assert(structure_writes == writes_before_chunk_budget)

	local total_over_budget_origin = vector.add(apply_base, { x = 320, y = 0, z = 0 })
	local total_over_budget_placements = many_structure_placements(total_over_budget_origin, 3)
	for _, placement in ipairs(total_over_budget_placements) do
		set_test_node(placement.pos, { name = "air" })
	end
	core.ai_import_ops.queue_chunked_structure_apply_task({
		task_id = "compat-structure:total-over-budget",
		agent_id = "compat_import:runtime",
		owner = "compat-operator",
		world_id = "staging-world",
		staging = true,
		explicit_approval = true,
		allow_mutation = true,
		rollback_policy = "chunked",
		placements = total_over_budget_placements,
		get_node = get_test_node,
		set_node = counting_structure_set_node,
		chunk_size = 1,
		max_node_writes_total = 2,
		max_node_writes_per_step = 1,
		max_mapblock_churn_total = 1,
		persist_record = function()
			error("rollback must not be written for total over-budget apply")
		end,
	})
	core.step_ai_tasks()
	local total_over_budget = core.get_ai_task("compat-structure:total-over-budget")
	assert(total_over_budget.status == "blocked")
	assert(total_over_budget.last_result.reason == "node_write_total_budget_exceeded")

	local mapblock_over_budget_origin = vector.add(apply_base, { x = 352, y = 0, z = 0 })
	local mapblock_over_budget_placements = many_structure_placements(
		mapblock_over_budget_origin, 3)
	for _, placement in ipairs(mapblock_over_budget_placements) do
		set_test_node(placement.pos, { name = "air" })
	end
	local writes_before_mapblock_budget = structure_writes
	core.ai_import_ops.queue_chunked_structure_apply_task({
		task_id = "compat-structure:mapblock-over-budget",
		agent_id = "compat_import:runtime",
		owner = "compat-operator",
		world_id = "staging-world",
		staging = true,
		explicit_approval = true,
		allow_mutation = true,
		rollback_policy = "chunked",
		placements = mapblock_over_budget_placements,
		get_node = get_test_node,
		set_node = counting_structure_set_node,
		chunk_size = 1,
		max_node_writes_total = 3,
		max_node_writes_per_step = 1,
		max_mapblock_churn_total = 2,
		persist_record = function()
			error("rollback must not be written for mapblock over-budget apply")
		end,
	})
	core.step_ai_tasks()
	local mapblock_over_budget = core.get_ai_task(
		"compat-structure:mapblock-over-budget")
	assert(mapblock_over_budget.status == "blocked")
	assert(mapblock_over_budget.last_result.reason == "mapblock_churn_budget_exceeded")
	assert(structure_writes == writes_before_mapblock_budget)

	local missing_chunk_rollback_origin = vector.add(apply_base, { x = 384, y = 0, z = 0 })
	local missing_chunk_rollback_placements = many_structure_placements(
		missing_chunk_rollback_origin, 3)
	for _, placement in ipairs(missing_chunk_rollback_placements) do
		set_test_node(placement.pos, { name = "air" })
	end
	local writes_before_chunk_missing_rollback = structure_writes
	core.ai_import_ops.queue_chunked_structure_apply_task({
		task_id = "compat-structure:chunk-missing-rollback",
		agent_id = "compat_import:runtime",
		owner = "compat-operator",
		world_id = "staging-world",
		staging = true,
		explicit_approval = true,
		allow_mutation = true,
		rollback_policy = "chunked",
		placements = missing_chunk_rollback_placements,
		get_node = get_test_node,
		set_node = counting_structure_set_node,
		chunk_size = 2,
		max_node_writes_total = 3,
		max_node_writes_per_step = 2,
		max_mapblock_churn_total = 3,
	})
	core.step_ai_tasks()
	local missing_chunk_rollback = core.get_ai_task(
		"compat-structure:chunk-missing-rollback")
	assert(missing_chunk_rollback.status == "blocked")
	assert(missing_chunk_rollback.last_result.reason == "rollback_metadata_unavailable")
	assert(structure_writes == writes_before_chunk_missing_rollback)

	local protected_chunk_origin = vector.add(apply_base, { x = 448, y = 0, z = 0 })
	local protected_chunk_placements = many_structure_placements(protected_chunk_origin, 3)
	for _, placement in ipairs(protected_chunk_placements) do
		set_test_node(placement.pos, { name = "air" })
	end
	local protected_chunk_records = {}
	local old_chunk_protected = core.is_protected
	core.is_protected = function(pos, name)
		return name == "compat-operator"
			and pos.x == protected_chunk_placements[3].pos.x
	end
	local writes_before_protected_chunk = structure_writes
	core.ai_import_ops.queue_chunked_structure_apply_task({
		task_id = "compat-structure:chunk-protected",
		agent_id = "compat_import:runtime",
		owner = "compat-operator",
		world_id = "staging-world",
		staging = true,
		explicit_approval = true,
		allow_mutation = true,
		rollback_policy = "chunked",
		placements = protected_chunk_placements,
		get_node = get_test_node,
		set_node = counting_structure_set_node,
		chunk_size = 2,
		max_node_writes_total = 3,
		max_node_writes_per_step = 2,
		max_mapblock_churn_total = 3,
		persist_record = function(record)
			protected_chunk_records[#protected_chunk_records + 1] = record
			return "rollback://compat-protected/" .. record.record_id
		end,
	})
	core.step_ai_tasks()
	assert(core.get_ai_task("compat-structure:chunk-protected").status == "running")
	assert(structure_writes == writes_before_protected_chunk + 2)
	core.step_ai_tasks()
	core.is_protected = old_chunk_protected
	local protected_chunk_task = core.get_ai_task("compat-structure:chunk-protected")
	assert(protected_chunk_task.status == "blocked")
	assert(protected_chunk_task.last_result.operation == "ai_world.batch_place")
	assert(protected_chunk_task.last_result.reason == "all_operations_skipped")
	assert(protected_chunk_task.last_result.changed == 0)
	assert(#protected_chunk_records == 2)
	assert(protected_chunk_records[2].chunk.chunk_index == 1)
	assert(structure_writes == writes_before_protected_chunk + 2)

	local queued_chunk_origin = vector.add(apply_base, { x = 544, y = 0, z = 0 })
	local queued_chunk_placements = many_structure_placements(queued_chunk_origin, 2)
	for _, placement in ipairs(queued_chunk_placements) do
		set_test_node(placement.pos, { name = "air" })
	end
	core.ai_import_ops.queue_chunked_structure_apply_task({
		task_id = "compat-structure:chunk-queued",
		agent_id = "compat_import:runtime",
		owner = "compat-operator",
		world_id = "staging-world",
		staging = true,
		explicit_approval = true,
		allow_mutation = true,
		rollback_policy = "chunked",
		placements = queued_chunk_placements,
		get_node = get_test_node,
		set_node = counting_structure_set_node,
		chunk_size = 1,
		max_node_writes_total = 2,
		max_node_writes_per_step = 1,
		max_mapblock_churn_total = 2,
		persist_record = function(record)
			return "rollback://compat-queued/" .. record.record_id
		end,
	})

	local running_chunk_origin = vector.add(apply_base, { x = 608, y = 0, z = 0 })
	local running_chunk_placements = many_structure_placements(running_chunk_origin, 2)
	for _, placement in ipairs(running_chunk_placements) do
		set_test_node(placement.pos, { name = "air" })
	end
	core.ai_import_ops.queue_chunked_structure_apply_task({
		task_id = "compat-structure:chunk-running",
		agent_id = "compat_import:runtime",
		owner = "compat-operator",
		world_id = "staging-world",
		staging = true,
		explicit_approval = true,
		allow_mutation = true,
		rollback_policy = "chunked",
		placements = running_chunk_placements,
		get_node = get_test_node,
		set_node = counting_structure_set_node,
		chunk_size = 1,
		max_node_writes_total = 2,
		max_node_writes_per_step = 1,
		max_mapblock_churn_total = 2,
		persist_record = function(record)
			return "rollback://compat-running/" .. record.record_id
		end,
	})
	core.step_ai_tasks()
	assert(core.get_ai_task("compat-structure:chunk-queued").status == "running")
	core.step_ai_tasks()
	assert(core.get_ai_task("compat-structure:chunk-queued").status == "completed")
	core.step_ai_tasks()
	assert(core.get_ai_task("compat-structure:chunk-running").status == "running")

	local chunk_summary = core.ai_import_ops.build_apply_summary({
		apply_id = "apply-runtime:chunked-final",
		report_id = "synthetic-structure-report",
		task_ids = {
			"compat-structure:chunk-queued",
			"compat-structure:chunk-running",
			"compat-structure:chunk-protected",
			"compat-structure:chunked-success",
		},
		approved_actions = {
			{ action_index = 1, action = "import_structure" },
		},
		rollback_policy = "chunked",
	})
	assert(chunk_summary.status == "blocked")
	assert(#chunk_summary.completed_tasks == 2)
	assert(#chunk_summary.running_tasks == 1)
	assert(#chunk_summary.blocked_tasks == 1)
	assert(chunk_summary.mutation_cost_actual.node_writes >= 10)
	assert(chunk_summary.mutation_cost_actual.mapblock_churn >= 10)
	assert(chunk_summary.mutation_cost_actual.elapsed_us >= 0)
	assert(#chunk_summary.rollback_records >= 8)
	core.step_ai_tasks()
	assert(core.get_ai_task("compat-structure:chunk-running").status == "completed")
end

run_compat_structure_apply_tests()

local function run_structure_adapter_handoff_smoke_tests()
	local smoke_base = test_pos(6200)
	local function adapter_placements(origin)
		return {
			{
				pos = vector.add(origin, { x = 0, y = 0, z = 0 }),
				node_name = "ai_runtime_test:stone",
			},
			{
				pos = vector.add(origin, { x = 1, y = 0, z = 0 }),
				node_name = "ai_runtime_test:stone",
				param1 = 3,
				param2 = 7,
			},
			{
				pos = vector.add(origin, { x = 17, y = 0, z = 0 }),
				node_name = "ai_runtime_test:stone",
			},
			{
				pos = vector.add(origin, { x = 34, y = 0, z = 0 }),
				node_name = "ai_runtime_test:stone",
			},
			{
				pos = vector.add(origin, { x = 35, y = 0, z = 0 }),
				node_name = "ai_runtime_test:stone",
			},
		}
	end

	local staged_apply = {
		status = "review_required",
		task_constructor = "core.ai_import_ops.define_chunked_structure_apply_task",
		rollback_plan_entrypoint = "core.ai_import_ops.plan_structure_rollback",
		rollback_execute_entrypoint = "core.ai_import_ops.queue_chunked_structure_rollback_task",
		placements = adapter_placements(smoke_base),
		placement_count = 5,
		chunk_size = 2,
		chunk_count = 3,
		target_world = {
			world_id = "disposable-staging-world",
			staging = true,
			disposable = true,
		},
		rollback_policy = "chunked",
		requires_explicit_approval = true,
		allow_mutation = false,
	}
	assert(staged_apply.status == "review_required")
	assert(staged_apply.allow_mutation == false)
	assert(staged_apply.target_world.disposable == true)

	local smoke_writes = 0
	local function smoke_set_node(pos, node)
		smoke_writes = smoke_writes + 1
		return set_test_node(pos, node)
	end

	for _, placement in ipairs(staged_apply.placements) do
		set_test_node(placement.pos, { name = "air" })
	end

	local apply_records = {}
	local smoke_storage = {}
	core.ai_rollback_storage.configure({
		enabled = true,
		inspect_record = function(storage_ref)
			return smoke_storage[storage_ref]
		end,
		persist_record = function(record)
			apply_records[#apply_records + 1] = record
			local storage_ref = "rollback://adapter-smoke/" .. record.record_id
			smoke_storage[storage_ref] = record
			return {
				ok = true,
				storage_ref = storage_ref,
			}
		end,
	})

	local apply_task_id = "compat-adapter-smoke:apply"
	core.ai_import_ops.queue_chunked_structure_apply_task({
		task_id = apply_task_id,
		agent_id = "compat_import:runtime",
		owner = "compat-operator",
		report_id = "synthetic-structure-report",
		action_index = 0,
		world_id = staged_apply.target_world.world_id,
		target_world = staged_apply.target_world,
		staging = staged_apply.target_world.staging,
		explicit_approval = staged_apply.requires_explicit_approval,
		allow_mutation = true,
		rollback_policy = staged_apply.rollback_policy,
		placements = staged_apply.placements,
		get_node = get_test_node,
		set_node = smoke_set_node,
		chunk_size = staged_apply.chunk_size,
		max_node_writes_total = staged_apply.placement_count,
		max_node_writes_per_step = staged_apply.chunk_size,
		max_mapblock_churn_total = staged_apply.chunk_count,
		max_wall_time_ms = 5000,
		source_reference = {
			reference_type = "mounted_fixture",
			redacted_id = "synthetic-structure-fixture",
			inventory_hash = string.rep("3", 64),
		},
	})
	core.step_ai_tasks()
	assert(core.get_ai_task(apply_task_id).status == "running")
	core.step_ai_tasks()
	assert(core.get_ai_task(apply_task_id).status == "running")
	core.step_ai_tasks()
	local apply_task = core.get_ai_task(apply_task_id)
	assert(apply_task.status == "completed")
	assert(apply_task.progress.current == staged_apply.chunk_count)
	assert(apply_task.last_result.operation == "ai_world.batch_place")
	assert(#apply_records == staged_apply.chunk_count)
	assert(smoke_writes == staged_apply.placement_count)
	for _, placement in ipairs(staged_apply.placements) do
		assert(get_test_node(placement.pos).name == "ai_runtime_test:stone")
	end
	assert(get_test_node(staged_apply.placements[2].pos).param1 == 3)
	assert(get_test_node(staged_apply.placements[2].pos).param2 == 7)

	local rollback_plan = core.ai_import_ops.plan_structure_rollback({
		agent_id = "compat_import:runtime",
		task_id = apply_task_id,
		owner = "compat-operator",
	})
	assert(rollback_plan.ok == true)
	assert(rollback_plan.status == "success")
	assert(rollback_plan.changed == 0)
	assert(rollback_plan.rollback_plan.will_mutate == false)
	assert(#rollback_plan.rollback_records == staged_apply.chunk_count)
	assert(rollback_plan.metrics.planned_node_writes == staged_apply.placement_count)

	local rollback_records = {}
	core.ai_rollback_storage.configure({
		enabled = true,
		inspect_record = function(storage_ref)
			return smoke_storage[storage_ref]
		end,
		persist_record = function(record)
			rollback_records[#rollback_records + 1] = record
			local storage_ref = "rollback://adapter-smoke-rollback/" .. record.record_id
			smoke_storage[storage_ref] = record
			return {
				ok = true,
				storage_ref = storage_ref,
			}
		end,
	})
	local rollback_task_id = "compat-adapter-smoke:rollback"
	core.ai_import_ops.queue_chunked_structure_rollback_task({
		task_id = rollback_task_id,
		agent_id = "compat_rollback:runtime",
		owner = "compat-operator",
		source_task_id = apply_task_id,
		world_id = staged_apply.target_world.world_id,
		target_world = staged_apply.target_world,
		staging = staged_apply.target_world.staging,
		explicit_approval = true,
		allow_mutation = true,
		rollback_policy = staged_apply.rollback_policy,
		get_node = get_test_node,
		set_node = smoke_set_node,
		max_node_writes_total = staged_apply.placement_count,
		max_node_writes_per_step = staged_apply.chunk_size,
		max_mapblock_churn_total = staged_apply.placement_count,
		max_wall_time_ms = 5000,
	})
	core.step_ai_tasks()
	assert(core.get_ai_task(rollback_task_id).status == "running")
	core.step_ai_tasks()
	assert(core.get_ai_task(rollback_task_id).status == "running")
	core.step_ai_tasks()
	local rollback_task = core.get_ai_task(rollback_task_id)
	assert(rollback_task.status == "completed")
	assert(rollback_task.last_result.operation == "ai_import.rollback_execute")
	assert(#rollback_records == staged_apply.chunk_count)
	assert(rollback_records[1].chunk.chunk_index == 2)
	assert(rollback_records[2].chunk.chunk_index == 1)
	assert(rollback_records[3].chunk.chunk_index == 0)
	assert(smoke_writes == staged_apply.placement_count * 2)
	for _, placement in ipairs(staged_apply.placements) do
		assert(get_test_node(placement.pos).name == "air")
	end

	local denied_origin = vector.add(smoke_base, { x = 128, y = 0, z = 0 })
	local denied_placements = adapter_placements(denied_origin)
	for _, placement in ipairs(denied_placements) do
		set_test_node(placement.pos, { name = "air" })
	end
	local writes_before_denied = smoke_writes
	core.ai_import_ops.queue_chunked_structure_apply_task({
		task_id = "compat-adapter-smoke:no-approval",
		agent_id = "compat_import:runtime",
		owner = "compat-operator",
		world_id = staged_apply.target_world.world_id,
		staging = true,
		explicit_approval = false,
		allow_mutation = true,
		rollback_policy = "chunked",
		placements = denied_placements,
		get_node = get_test_node,
		set_node = smoke_set_node,
		chunk_size = 2,
		max_node_writes_total = 5,
		max_node_writes_per_step = 2,
		max_mapblock_churn_total = 3,
		persist_record = function()
			error("rollback must not be written without approval")
		end,
	})
	core.step_ai_tasks()
	local no_approval = core.get_ai_task("compat-adapter-smoke:no-approval")
	assert(no_approval.status == "blocked")
	assert(no_approval.last_result.reason == "approval_required")
	assert(smoke_writes == writes_before_denied)

	local non_staging_origin = vector.add(smoke_base, { x = 256, y = 0, z = 0 })
	local non_staging_placements = adapter_placements(non_staging_origin)
	for _, placement in ipairs(non_staging_placements) do
		set_test_node(placement.pos, { name = "air" })
	end
	core.ai_import_ops.queue_chunked_structure_apply_task({
		task_id = "compat-adapter-smoke:non-staging",
		agent_id = "compat_import:runtime",
		owner = "compat-operator",
		world_id = "family_voxelibre",
		staging = false,
		explicit_approval = true,
		allow_mutation = true,
		rollback_policy = "chunked",
		placements = non_staging_placements,
		get_node = get_test_node,
		set_node = smoke_set_node,
		chunk_size = 2,
		max_node_writes_total = 5,
		max_node_writes_per_step = 2,
		max_mapblock_churn_total = 3,
		persist_record = function()
			error("rollback must not be written for a non-staging target")
		end,
	})
	core.step_ai_tasks()
	local non_staging = core.get_ai_task("compat-adapter-smoke:non-staging")
	assert(non_staging.status == "blocked")
	assert(non_staging.last_result.reason == "staging_target_required")

	local partial_origin = vector.add(smoke_base, { x = 384, y = 0, z = 0 })
	local partial_placements = {
		{
			pos = vector.add(partial_origin, { x = 0, y = 0, z = 0 }),
			node_name = "ai_runtime_test:stone",
		},
		{
			pos = vector.add(partial_origin, { x = 1, y = 0, z = 0 }),
			node_name = "ai_runtime_test:stone",
		},
	}
	for _, placement in ipairs(partial_placements) do
		set_test_node(placement.pos, { name = "air" })
	end
	local old_partial_protected = core.is_protected
	core.is_protected = function(pos, name)
		return name == "compat-operator" and pos.x == partial_placements[1].pos.x
	end
	local partial_records = {}
	core.ai_rollback_storage.configure({
		enabled = true,
		persist_record = function(record)
			partial_records[#partial_records + 1] = record
			return {
				ok = true,
				storage_ref = "rollback://adapter-smoke-partial/" .. record.record_id,
			}
		end,
	})
	core.ai_import_ops.queue_chunked_structure_apply_task({
		task_id = "compat-adapter-smoke:protected-partial",
		agent_id = "compat_import:runtime",
		owner = "compat-operator",
		world_id = staged_apply.target_world.world_id,
		staging = true,
		explicit_approval = true,
		allow_mutation = true,
		rollback_policy = "chunked",
		placements = partial_placements,
		get_node = get_test_node,
		set_node = smoke_set_node,
		chunk_size = 2,
		max_node_writes_total = 2,
		max_node_writes_per_step = 2,
		max_mapblock_churn_total = 1,
	})
	core.step_ai_tasks()
	core.is_protected = old_partial_protected
	local partial_task = core.get_ai_task("compat-adapter-smoke:protected-partial")
	assert(partial_task.status == "completed")
	assert(partial_task.last_result.status == "partial")
	assert(partial_task.last_result.reason == "some_operations_skipped")
	assert(partial_task.last_result.changed == 1)
	assert(partial_task.last_result.skipped == 1)
	assert(partial_task.last_result.samples[1].reason == "protected_area")
	assert(#partial_records == 1)
	assert(get_test_node(partial_placements[1].pos).name == "air")
	assert(get_test_node(partial_placements[2].pos).name == "ai_runtime_test:stone")
	core.ai_rollback_storage.configure(nil)
end

run_structure_adapter_handoff_smoke_tests()

assert(core.registered_chatcommands.ai_runtime ~= nil)
local command_ok, command_message = core.registered_chatcommands.ai_runtime.func("admin", "")
assert(command_ok == true)
assert(command_message:find("AI runtime: queue=", 1, true))
assert(command_message:find("tasks=", 1, true))
assert(command_message:find("writes=", 1, true))
assert(command_message:find("audit=", 1, true))
assert(command_message:find("model=", 1, true))
assert(not command_message:find("do not retain this prompt", 1, true))
assert(#command_message < 320)

local audit = core.get_ai_runtime_audit({ limit = 300 })
assert(type(audit) == "table")

local function audit_has(event_type, task_id)
	for _, record in ipairs(audit) do
		if record.event_type == event_type and (not task_id or record.task_id == task_id) then
			return true
		end
	end
	return false
end

assert(audit_has("capability.admin_override", nil))
assert(audit_has("task.started", "task:lights"))
assert(audit_has("task.completed", "task:lights"))
assert(audit_has("task.cancelled", "task:queued-cancel"))
assert(audit_has("task.retried", "task:retry-live"))
assert(audit_has("task.unsafe", "task:write-budget"))
assert(audit_has("world.unsafe", nil))

local model_request_audit = nil
for _, record in ipairs(audit) do
	if record.event_type == "model.request" and record.task_id == "task:safe-world" then
		model_request_audit = record
	end
end
assert(model_request_audit ~= nil)
assert(model_request_audit.private_payload == nil)
assert(model_request_audit.payload_retained == false)

function test_ai_agent_plugin_defaults_are_profile_empty()
	local default_policy_agent = core.ai_agent_plugin.ensure_player_agent("DefaultPolicy")
	assert(default_policy_agent.agent_id == "nova_agent:DefaultPolicy")
	assert(core.agent_has_capability(default_policy_agent.agent_id, "world.read") == false)
	assert(core.agent_has_capability(default_policy_agent.agent_id, "world.place") == false)
	assert(core.agent_has_capability(default_policy_agent.agent_id, "entity.spawn") == false)
	assert(core.agent_has_capability(default_policy_agent.agent_id, "task.cancel") == false)
	assert(core.agent_has_capability(default_policy_agent.agent_id, "http.llm") == false)
	assert(core.agent_has_capability(default_policy_agent.agent_id, "admin.override") == false)
	assert(core.agent_has_capability(default_policy_agent.agent_id, "import.assets") == false)
end

test_ai_agent_plugin_defaults_are_profile_empty()
test_ai_agent_plugin_defaults_are_profile_empty = nil

core.ai_agent_plugin.configure({
	capability_profile = "operator",
	capabilities = {
		["admin.override"] = true,
	},
})

function test_ai_agent_plugin_operator_profile_requires_explicit_audited_override()
	local operator_policy_agent = core.ai_agent_plugin.ensure_player_agent("OperatorPolicy")
	assert(operator_policy_agent.agent_id == "nova_agent:OperatorPolicy")
	assert(operator_policy_agent.limits.capability_profile == "operator")
	assert(core.agent_has_capability(operator_policy_agent.agent_id, "admin.override") == true)

	local override_check = core.check_agent_capability(operator_policy_agent.agent_id, "admin.override")
	assert_result(override_check, true, "success", "admin_override_granted")
	assert(override_check.audit_required == true)

	local latest_audit = core.get_ai_runtime_audit({ limit = 10 })
	local saw_override_audit = false
	for _, record in ipairs(latest_audit) do
		if record.event_type == "capability.admin_override"
				and record.agent_id == operator_policy_agent.agent_id
				and record.operation == "capability.check"
				and record.status == "success" then
			saw_override_audit = true
		end
	end
	assert(saw_override_audit == true)
end

test_ai_agent_plugin_operator_profile_requires_explicit_audited_override()
test_ai_agent_plugin_operator_profile_requires_explicit_audited_override = nil

core.ai_agent_plugin.configure({
	capability_profile = "clean",
	light_node = "ai_runtime_test:stone",
	marker_node = "ai_runtime_test:stone",
	repair_nodes = {
		["ai_runtime_test:hazard"] = true,
	},
	max_lights = 3,
	capabilities = {
		["world.read"] = true,
		["entity.spawn"] = true,
		["task.cancel"] = true,
	},
})

function test_ai_runtime_profile_policy_capabilities()
	local policy_agent = core.ai_agent_plugin.ensure_player_agent("ProfilePolicy")
	assert(policy_agent.agent_id == "nova_agent:ProfilePolicy")
	assert(policy_agent.limits.capability_profile == "clean")
	assert(core.agent_has_capability(policy_agent.agent_id, "world.read") == true)
	assert(core.agent_has_capability(policy_agent.agent_id, "entity.spawn") == true)
	assert(core.agent_has_capability(policy_agent.agent_id, "task.cancel") == true)
	assert(core.agent_has_capability(policy_agent.agent_id, "world.place") == false)
	assert(core.agent_has_capability(policy_agent.agent_id, "world.remove") == false)
	assert(core.agent_has_capability(policy_agent.agent_id, "http.llm") == false)
	assert(core.agent_has_capability(policy_agent.agent_id, "admin.override") == false)
	assert(core.agent_has_capability(policy_agent.agent_id, "import.assets") == false)
end

test_ai_runtime_profile_policy_capabilities()
test_ai_runtime_profile_policy_capabilities = nil

core.ai_agent_plugin.configure({
	capability_profile = "clean",
	light_node = "ai_runtime_test:stone",
	marker_node = "ai_runtime_test:stone",
	repair_nodes = {
		["ai_runtime_test:hazard"] = true,
	},
	max_lights = 3,
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

local plugin_agent = core.ai_agent_plugin.ensure_player_agent("Wills")
assert(plugin_agent.agent_id == "nova_agent:Wills")
assert(plugin_agent.owner == "Wills")
assert(plugin_agent.plugin == "ai_agent_plugin")
assert(core.agent_has_capability(plugin_agent.agent_id, "world.read") == true)
assert(core.agent_has_capability(plugin_agent.agent_id, "world.place") == true)
assert(core.agent_has_capability(plugin_agent.agent_id, "entity.spawn") == true)
assert(core.agent_has_capability(plugin_agent.agent_id, "entity.control") == true)
assert(core.agent_has_capability(plugin_agent.agent_id, "http.llm") == true)

local same_agent = core.ai_agent_plugin.ensure_player_agent("Wills")
assert(same_agent.agent_id == plugin_agent.agent_id)

assert(core.registered_chatcommands.bot ~= nil)
assert(core.registered_chatcommands.nova ~= nil)
assert(core.registered_chatcommands.aibot ~= nil)

product_loop_records = {}
core.ai_rollback_storage.configure({
	enabled = true,
	persist_record = function(record)
		product_loop_records[#product_loop_records + 1] = record
		return {
			ok = true,
			storage_ref = "rollback://product-loop/" .. record.record_id,
		}
	end,
})

local plugin_base = test_pos(4200)
set_test_node(vector.add(plugin_base, { x = 0, y = 1, z = 0 }), { name = "air" })
local light_reply = core.ai_agent_plugin.handle_command("Wills", "place 2 lights", {
	pos = plugin_base,
	get_node = get_test_node,
	set_node = set_test_node,
})
assert(light_reply.ok == true)
assert(light_reply.status == "queued")
assert(light_reply.action == "light")
assert(light_reply.agent_id == plugin_agent.agent_id)
assert(light_reply.task_id ~= nil)
assert(get_test_node(vector.add(plugin_base, { x = 0, y = 1, z = 0 })).name == "air")

local task_view = core.get_ai_task(light_reply.task_id)
assert(task_view.status == "queued")
assert(task_view.owner == "Wills")

core.step_ai_tasks()
assert(core.get_ai_task(light_reply.task_id).status == "completed")
assert(core.get_ai_task(light_reply.task_id).last_result.rollback_record_id ~= nil)
assert(get_test_node(vector.add(plugin_base, { x = 0, y = 1, z = 0 })).name
	== "ai_runtime_test:stone")

function test_ai_agent_plugin_continuous_follow(plugin_base, plugin_agent)
local follow_player_pos = table.copy(plugin_base)
local follow_player = {
	get_pos = function()
		return table.copy(follow_player_pos)
	end,
}
local follow_reply = core.ai_agent_plugin.handle_command("Wills", "follow me", {
	get_player_by_name = function(name)
		if name == "Wills" then
			return follow_player
		end
		return nil
	end,
	spawn_entity = spawn_test_entity,
	max_follow_steps = 3,
	max_follow_step_distance = 2,
	max_follow_total_distance = 8,
	max_follow_stop_distance = 0,
})
assert(follow_reply.ok == true)
assert(follow_reply.status == "queued")
assert(follow_reply.action == "follow")
assert(follow_reply.task_id ~= nil)
assert(core.ai_agent_plugin.get_player_state("Wills").mode == "follow")
core.step_ai_tasks()
assert(core.get_ai_task(follow_reply.task_id).status == "running")
assert(core.get_ai_task(follow_reply.task_id).last_result.operation == "ai_agent.follow_step")
assert(core.get_ai_task(follow_reply.task_id).last_result.reason == "follow_target_reached")
follow_player_pos = vector.add(plugin_base, { x = 2, y = 0, z = 0 })
core.step_ai_tasks()
assert(core.get_ai_task(follow_reply.task_id).status == "running")
follow_player_pos = vector.add(plugin_base, { x = 4, y = 0, z = 0 })
core.step_ai_tasks()
local completed_follow = core.get_ai_task(follow_reply.task_id)
assert(completed_follow.status == "completed")
assert(completed_follow.last_result.operation == "ai_agent.follow_step")
assert(completed_follow.last_result.movement_result.operation == "ai_entity.move")
assert(completed_follow.last_result.entity.entity_name == "ai_demo_benchmark:helper")
assert(completed_follow.last_result.entity.pos.x == plugin_base.x + 4)
assert(completed_follow.last_result.entity.pos.y == plugin_base.y)
assert(completed_follow.last_result.entity.pos.z == plugin_base.z)
assert(completed_follow.last_result.metrics.total_distance_moved == 4)
assert(completed_follow.last_result.metrics.max_steps == 3)
assert(completed_follow.last_result.metrics.path_status == "direct_line_bounded")
assert(completed_follow.last_result.metrics.node_writes == 0)
local follow_entity_id = completed_follow.last_result.entity.entity_id
assert(follow_entity_id ~= nil)
assert(core.ai_agent_plugin.get_player_state("Wills").entity_id == follow_entity_id)

follow_player_pos = vector.add(plugin_base, { x = 4, y = 0, z = 0 })
local cancel_follow_reply = core.ai_agent_plugin.handle_command("Wills", "follow 3", {
	get_player_by_name = function(name)
		if name == "Wills" then
			return follow_player
		end
		return nil
	end,
	spawn_entity = spawn_test_entity,
	max_follow_step_distance = 1,
	max_follow_total_distance = 8,
	max_follow_stop_distance = 0,
})
assert(cancel_follow_reply.ok == true)
core.step_ai_tasks()
follow_player_pos = vector.add(plugin_base, { x = 5, y = 0, z = 0 })
core.step_ai_tasks()
local cancel_follow_task = core.get_ai_task(cancel_follow_reply.task_id)
assert(cancel_follow_task.status == "running")
assert(cancel_follow_task.last_result.metrics.total_distance_moved == 1)
local cancelled_follow = core.ai_agent_plugin.handle_command("Wills", "cancel", {})
assert(cancelled_follow.ok == true)
assert(core.get_ai_task(cancel_follow_reply.task_id).status == "cancelled")
follow_player_pos = vector.add(plugin_base, { x = 6, y = 0, z = 0 })
core.step_ai_tasks()
local inspected_after_cancel = core.ai_entity_ops.inspect(follow_entity_id, {
	agent_id = plugin_agent.agent_id,
	owner = "Wills",
})
assert(inspected_after_cancel.entity.pos.x == plugin_base.x + 5)

local limit_player_pos = test_pos(4245)
local limit_player = {
	get_pos = function()
		return table.copy(limit_player_pos)
	end,
}
local limited_follow = core.ai_agent_plugin.handle_command("Limit", "follow me", {
	get_player_by_name = function(name)
		if name == "Limit" then
			return limit_player
		end
		return nil
	end,
	spawn_entity = spawn_test_entity,
	max_follow_steps = 2,
	max_follow_step_distance = 2,
	max_follow_total_distance = 1,
	max_follow_stop_distance = 0,
})
assert(limited_follow.ok == true)
core.step_ai_tasks()
limit_player_pos = vector.add(limit_player_pos, { x = 3, y = 0, z = 0 })
core.step_ai_tasks()
local blocked_follow = core.get_ai_task(limited_follow.task_id)
assert(blocked_follow.status == "blocked")
assert(blocked_follow.last_result.reason == "follow_distance_limit_exceeded")
assert(blocked_follow.last_result.skipped == 1)
assert(blocked_follow.last_result.metrics.step_distance == 2)
assert(blocked_follow.last_result.metrics.skipped_reason == "max_total_distance")
return follow_entity_id
end

local follow_entity_id = test_ai_agent_plugin_continuous_follow(plugin_base, plugin_agent)
test_ai_agent_plugin_continuous_follow = nil

local come_reply = core.ai_agent_plugin.handle_command("Wills", "come", {
	pos = vector.add(plugin_base, { x = 3, y = 0, z = 0 }),
	spawn_entity = spawn_test_entity,
})
assert(come_reply.ok == true)
assert(come_reply.status == "queued")
assert(come_reply.action == "come")
assert(core.ai_agent_plugin.get_player_state("Wills").target_pos.x == plugin_base.x + 3)
core.step_ai_tasks()
local completed_come = core.get_ai_task(come_reply.task_id)
assert(completed_come.status == "completed")
assert(completed_come.last_result.operation == "ai_entity.move")
assert(completed_come.last_result.entity.entity_id == follow_entity_id)
assert(completed_come.last_result.entity.pos.x == plugin_base.x + 3)
assert(completed_come.last_result.metrics.distance == 2)

function test_ai_agent_plugin_product_loop_commands()
local build_plan_pos = test_pos(4208)
set_test_node(build_plan_pos, { name = "air" })
local build_plan_reply = core.ai_agent_plugin.handle_command("Wills", "build plan", {
	pos = build_plan_pos,
	get_node = get_test_node,
	set_node = function()
		error("build plan must not mutate")
	end,
})
assert(build_plan_reply.ok == true)
assert(build_plan_reply.action == "build_plan")
assert(build_plan_reply.task_id == nil)
assert(build_plan_reply.plan.operation == "build_agent.plan")
assert(build_plan_reply.plan.will_mutate == false)
assert(build_plan_reply.planned_node_writes == 1)
assert(build_plan_reply.plan.metrics.node_writes == 0)
assert(get_test_node(build_plan_pos).name == "air")

local repair_plan_pos = test_pos(4209)
set_test_node(repair_plan_pos, { name = "ai_runtime_test:hazard" })
local repair_plan_reply = core.ai_agent_plugin.handle_command("Wills", "repair plan", {
	pos = repair_plan_pos,
	get_node = get_test_node,
	set_node = function()
		error("repair plan must not mutate")
	end,
})
assert(repair_plan_reply.ok == true)
assert(repair_plan_reply.action == "repair_plan")
assert(repair_plan_reply.task_id == nil)
assert(repair_plan_reply.plan.operation == "repair_agent.plan_area")
assert(repair_plan_reply.plan.will_mutate == false)
assert(repair_plan_reply.plan.changed == 0)
assert(repair_plan_reply.plan.metrics.node_writes == 0)
assert(repair_plan_reply.candidate_count == 1)
assert(get_test_node(repair_plan_pos).name == "ai_runtime_test:hazard")

local build_pos = test_pos(4210)
set_test_node(build_pos, { name = "air" })
local build_reply = core.ai_agent_plugin.handle_command("Wills", "build marker", {
	pos = build_pos,
	world_id = "product-loop-world",
	get_node = get_test_node,
	set_node = set_test_node,
})
assert(build_reply.ok == true)
assert(build_reply.action == "build")
assert(core.get_ai_task(build_reply.task_id).status == "queued")
assert(get_test_node(build_pos).name == "air")
core.step_ai_tasks()
assert(get_test_node(build_pos).name == "ai_runtime_test:stone")
local completed_plugin_build = core.get_ai_task(build_reply.task_id)
assert(completed_plugin_build.status == "completed")
assert(completed_plugin_build.last_result.rollback_record_id ~= nil)
assert(completed_plugin_build.last_result.rollback_storage_ref:find(
	"rollback://product-loop/", 1, true))

local repair_pos = test_pos(4220)
set_test_node(repair_pos, { name = "ai_runtime_test:hazard" })
local repair_reply = core.ai_agent_plugin.handle_command("Wills", "repair", {
	pos = repair_pos,
	world_id = "product-loop-world",
	get_node = get_test_node,
	set_node = set_test_node,
})
assert(repair_reply.ok == true)
assert(repair_reply.action == "repair")
assert(get_test_node(repair_pos).name == "ai_runtime_test:hazard")
core.step_ai_tasks()
assert(get_test_node(repair_pos).name == "air")
local completed_repair = core.get_ai_task(repair_reply.task_id)
assert(completed_repair.status == "completed")
assert(completed_repair.last_result.operation == "repair_agent.apply_plan")
assert(completed_repair.last_result.changed == 1)
assert(completed_repair.last_result.rollback_record_id ~= nil)

local guide_reply = core.ai_agent_plugin.handle_command("Wills", "guide", {})
assert(guide_reply.ok == true)
assert(guide_reply.action == "guide")
assert(guide_reply.surfaces.builder == true)
assert(guide_reply.surfaces.repair == true)
assert(guide_reply.surfaces.guide == true)
assert(guide_reply.surfaces.defender == true)
assert(guide_reply.surfaces.importer == true)
assert(type(guide_reply.commands) == "table")

local audit_reply = core.ai_agent_plugin.handle_command("Wills", "audit", {})
assert(audit_reply.ok == true)
assert(audit_reply.action == "audit")
assert(#audit_reply.audit_events > 0)
for _, record in ipairs(audit_reply.audit_events) do
	assert(record.private_payload == nil)
end

local rollback_reply = core.ai_agent_plugin.handle_command("Wills", "rollback", {})
assert(rollback_reply.ok == true)
assert(rollback_reply.action == "rollback")
assert(#rollback_reply.rollback_records >= 2)
for _, record in ipairs(rollback_reply.rollback_records) do
	assert(record.rollback_record_id ~= nil)
	assert(record.rollback_storage_ref ~= nil)
end
assert(#product_loop_records >= 2)
core.ai_rollback_storage.configure(nil)

core.ai_agent_plugin.configure({
	capability_profile = "operator",
	capabilities = {
		["combat.defend"] = true,
		["task.cancel"] = true,
	},
})

local defender_pos = test_pos(4230)
local defender_player = {
	get_pos = function()
		return defender_pos
	end,
	set_pos = function()
		return true
	end,
	get_attach = function()
		return nil
	end,
}
local defended = false
local defend_reply = core.ai_agent_plugin.handle_command("Defender", "defend", {
	get_player_by_name = function(name)
		if name == "Defender" then
			return defender_player
		end
		return nil
	end,
	hostiles = {
		{
			entity_id = "hostile:test",
			entity_name = "ai_runtime_test:hostile",
			pos = vector.add(defender_pos, { x = 1, y = 0, z = 0 }),
		},
	},
	attack_entity = function()
		defended = true
		return true
	end,
	max_defend_distance = 8,
})
assert(defend_reply.ok == true)
assert(defend_reply.action == "defend")
assert(defend_reply.status == "queued")
assert(defend_reply.task_id ~= nil)
core.step_ai_tasks()
local completed_defend = core.get_ai_task(defend_reply.task_id)
assert(completed_defend.status == "completed")
assert(completed_defend.last_result.operation == "ai_player.defend")
assert(completed_defend.last_result.reason == "hostile_target_defended")
assert(completed_defend.last_result.changed == 1)
assert(defended == true)

core.ai_agent_plugin.configure({
	capability_profile = "operator",
	capabilities = {
		["import.assets"] = true,
		["task.cancel"] = true,
	},
})

local importer_plan_reply = core.ai_agent_plugin.handle_command("Importer", "import plan", {
	import_plan = {
		source = {
			source_id = "agent-import-synthetic-pack",
			source_class = "bedrock_resource_pack",
			inventory = {
				{
					entry_id = "entry:agent-import:1",
					source_path = "textures/agent_import.png",
					source_kind = "texture",
					classification = "mapped",
					reason = "metadata_or_asset_reference",
					required_capabilities = { "import.assets" },
				},
			},
			content_hashes = {
				{
					algorithm = "sha256",
					value = string.rep("1", 64),
					purpose = "synthetic agent import inventory hash",
				},
			},
		},
		dry_run = true,
		planned_actions = {
			{
				action = "map_texture",
				status = "partial",
				required_capabilities = { "import.assets" },
				provenance = {
					source_id = "agent-import-synthetic-pack",
					inventory_refs = { "entry:agent-import:1" },
					classification = "mapped",
				},
				mutation_cost = {
					node_writes = 0,
					media_files = 1,
					manual_review_items = 1,
				},
			},
		},
	},
})
assert(importer_plan_reply.ok == true)
assert(importer_plan_reply.action == "import_plan")
assert(importer_plan_reply.status == "queued")
assert(importer_plan_reply.task_id ~= nil)
core.step_ai_tasks()
local completed_importer_plan = core.get_ai_task(importer_plan_reply.task_id)
assert(completed_importer_plan.status == "completed")
assert(completed_importer_plan.last_result.operation == "ai_import.plan")
assert(completed_importer_plan.last_result.import_plan.dry_run == true)
assert(completed_importer_plan.last_result.import_plan.assets_copied == false)
assert(completed_importer_plan.last_result.import_plan.source_id == "agent-import-synthetic-pack")
assert(completed_importer_plan.last_result.import_plan.inventory_count == 1)
assert(completed_importer_plan.last_result.import_plan.planned_actions[1].action == "map_texture")
assert(completed_importer_plan.last_result.changed == 0)
assert(completed_importer_plan.last_result.skipped == 0)

core.ai_agent_plugin.configure({
	capability_profile = "clean",
	light_node = "ai_runtime_test:stone",
	marker_node = "ai_runtime_test:stone",
	repair_nodes = {
		["ai_runtime_test:hazard"] = true,
	},
	max_lights = 3,
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
end

test_ai_agent_plugin_product_loop_commands()
test_ai_agent_plugin_product_loop_commands = nil
product_loop_records = nil

local cancel_reply = core.ai_agent_plugin.handle_command("Wills", "light", {
	pos = test_pos(4230),
	get_node = get_test_node,
	set_node = set_test_node,
})
assert(cancel_reply.status == "queued")
local cancel_done = core.ai_agent_plugin.handle_command("Wills", "cancel", {})
assert(cancel_done.ok == true)
assert(cancel_done.action == "cancel")
assert(core.get_ai_task(cancel_reply.task_id).status == "cancelled")

local tasks_reply = core.ai_agent_plugin.handle_command("Wills", "tasks", {})
assert(tasks_reply.ok == true)
assert(tasks_reply.action == "tasks")
assert(#tasks_reply.tasks >= 1)

local adapter_calls = {}
local before_model_metrics = core.get_ai_runtime_metrics()
core.ai_agent_plugin.set_model_adapter(function(request)
	table.insert(adapter_calls, request)
	return {
		ok = true,
		message = "mock adapter response",
		adapter_name = "mock-success",
		elapsed_us = 50000,
	}
end)

local model_reply = core.ai_agent_plugin.handle_command("Wills", "what should we explore next?", {
	private_prompt = "synthetic model prompt",
})
assert(model_reply.ok == true)
assert(model_reply.action == "model")
assert(model_reply.message == "mock adapter response")
assert(#adapter_calls == 1)
assert(adapter_calls[1].agent_id == plugin_agent.agent_id)

local plugin_audit = core.get_ai_runtime_audit({ limit = 10 })
local model_record = plugin_audit[#plugin_audit - 1]
assert(model_record.event_type == "model.request")
assert(model_record.agent_id == plugin_agent.agent_id)
assert(model_record.private_payload == nil)
assert(model_record.payload_retained == false)
local model_result_record = plugin_audit[#plugin_audit]
assert(model_result_record.event_type == "model.adapter")
assert(model_result_record.agent_id == plugin_agent.agent_id)
assert(model_result_record.adapter_name == "mock-success")
assert(model_result_record.status == "success")
assert(model_result_record.private_payload == nil)
assert(model_result_record.payload_retained == false)

local after_success_metrics = core.get_ai_runtime_metrics()
assert(after_success_metrics.model_adapter_requests == before_model_metrics.model_adapter_requests + 1)
assert(after_success_metrics.model_adapter_successes == before_model_metrics.model_adapter_successes + 1)
assert(after_success_metrics.model_adapter_failures == before_model_metrics.model_adapter_failures)
assert(after_success_metrics.model_adapter_timeouts == before_model_metrics.model_adapter_timeouts)
assert(after_success_metrics.model_adapter_latency_buckets.under_100ms
	== before_model_metrics.model_adapter_latency_buckets.under_100ms + 1)

local before_failure_metrics = core.get_ai_runtime_metrics()
core.ai_agent_plugin.set_model_adapter(function()
	return {
		ok = false,
		message = "mock adapter failure",
		reason = "mock_failure",
		adapter_name = "mock-failure",
		elapsed_us = 250000,
	}
end)
local failure_reply = core.ai_agent_plugin.handle_command("Wills", "adapter failure test", {
	private_prompt = "synthetic failure prompt",
})
assert(failure_reply.ok == false)
assert(failure_reply.action == "model")
local after_failure_metrics = core.get_ai_runtime_metrics()
assert(after_failure_metrics.model_adapter_requests == before_failure_metrics.model_adapter_requests + 1)
assert(after_failure_metrics.model_adapter_failures == before_failure_metrics.model_adapter_failures + 1)
assert(after_failure_metrics.model_adapter_successes == before_failure_metrics.model_adapter_successes)
assert(after_failure_metrics.model_adapter_latency_buckets.under_1000ms
	== before_failure_metrics.model_adapter_latency_buckets.under_1000ms + 1)

local before_timeout_metrics = core.get_ai_runtime_metrics()
core.ai_agent_plugin.set_model_adapter(function()
	return {
		ok = false,
		timeout = true,
		message = "mock adapter timeout",
		reason = "timeout",
		adapter_name = "mock-timeout",
		elapsed_us = 1500000,
	}
end)
local timeout_reply = core.ai_agent_plugin.handle_command("Wills", "adapter timeout test", {
	private_prompt = "synthetic timeout prompt",
})
assert(timeout_reply.ok == false)
assert(timeout_reply.action == "model")
local after_timeout_metrics = core.get_ai_runtime_metrics()
assert(after_timeout_metrics.model_adapter_requests == before_timeout_metrics.model_adapter_requests + 1)
assert(after_timeout_metrics.model_adapter_timeouts == before_timeout_metrics.model_adapter_timeouts + 1)
assert(after_timeout_metrics.model_adapter_failures == before_timeout_metrics.model_adapter_failures)
assert(after_timeout_metrics.model_adapter_latency_buckets.over_1000ms
	== before_timeout_metrics.model_adapter_latency_buckets.over_1000ms + 1)

local adapter_audit = core.get_ai_runtime_audit({ limit = 12 })
local timeout_record = adapter_audit[#adapter_audit]
assert(timeout_record.event_type == "model.adapter")
assert(timeout_record.adapter_name == "mock-timeout")
assert(timeout_record.status == "timeout")
assert(timeout_record.private_payload == nil)
assert(timeout_record.payload_retained == false)

assert(core.repair_agent ~= nil)
core.repair_agent.configure({
	repair_nodes = {
		["ai_runtime_test:hazard"] = {
			planned_action = "remove_node",
			replacement = "air",
			family = "hazard",
		},
	},
	sample_limit = 8,
})

local repair_plan_center = test_pos(4240)
local protected_repair_pos = vector.add(repair_plan_center, { x = 1, y = 0, z = 0 })
set_test_node(repair_plan_center, { name = "ai_runtime_test:hazard" })
set_test_node(protected_repair_pos, { name = "ai_runtime_test:hazard" })
local repair_plan_writes = 0
local function forbidden_repair_set_node(pos, node)
	repair_plan_writes = repair_plan_writes + 1
	return set_test_node(pos, node)
end

old_is_protected = core.is_protected
core.is_protected = function(pos, name)
	return name == "Wills" and pos.x == protected_repair_pos.x
end

local repair_plan = core.repair_agent.plan_area(repair_plan_center, {
	agent_id = plugin_agent.agent_id,
	owner = "Wills",
	task_id = "repair-plan:direct",
	radius = 1,
	get_node = get_test_node,
	set_node = forbidden_repair_set_node,
	sample_limit = 8,
})
assert(repair_plan.ok == true)
assert(repair_plan.status == "partial")
assert(repair_plan.operation == "repair_agent.plan_area")
assert(repair_plan.agent_id == plugin_agent.agent_id)
assert(repair_plan.task_id == "repair-plan:direct")
assert(repair_plan.changed == 0)
assert(repair_plan.examined == 27)
assert(repair_plan.skipped >= 1)
assert(repair_plan.metrics.node_writes == 0)
assert(repair_plan.metrics.candidate_count == 1)
assert(#repair_plan.candidates == 1)
assert(repair_plan.candidates[1].node_name == "ai_runtime_test:hazard")
assert(repair_plan.candidates[1].planned_action == "remove_node")
assert(repair_plan.candidates[1].replacement == "air")
assert(repair_plan.candidates[1].pos.x == repair_plan_center.x)
assert(repair_plan_writes == 0)
assert(get_test_node(repair_plan_center).name == "ai_runtime_test:hazard")
assert(get_test_node(protected_repair_pos).name == "ai_runtime_test:hazard")

local saw_protected_skip = false
for _, sample in ipairs(repair_plan.samples) do
	if sample.reason == "protected_area" then
		saw_protected_skip = true
	end
end
assert(saw_protected_skip == true)

core.is_protected = old_is_protected

local empty_repair_plan = core.repair_agent.plan_area(test_pos(4260), {
	agent_id = plugin_agent.agent_id,
	owner = "Wills",
	radius = 0,
	get_node = get_test_node,
	set_node = forbidden_repair_set_node,
})
assert(empty_repair_plan.ok == true)
assert(empty_repair_plan.status == "success")
assert(empty_repair_plan.reason == "no_repair_candidates")
assert(empty_repair_plan.changed == 0)
assert(#empty_repair_plan.candidates == 0)
assert(repair_plan_writes == 0)

local queued_repair_plan = core.repair_agent.queue_plan_task({
	task_id = "repair-plan:queued",
	agent_id = plugin_agent.agent_id,
	owner = "Wills",
	center = repair_plan_center,
	radius = 0,
	get_node = get_test_node,
	set_node = forbidden_repair_set_node,
})
assert(queued_repair_plan.status == "queued")
assert(queued_repair_plan.task_id == "repair-plan:queued")
assert(core.get_ai_task("repair-plan:queued").status == "queued")
core.step_ai_tasks()
local completed_repair_plan = core.get_ai_task("repair-plan:queued")
assert(completed_repair_plan.status == "completed")
assert(completed_repair_plan.last_result.operation == "repair_agent.plan_area")
assert(completed_repair_plan.last_result.changed == 0)
assert(repair_plan_writes == 0)

local repair_apply_center = test_pos(4265)
local repair_apply_left = vector.add(repair_apply_center, { x = -1, y = 0, z = 0 })
set_test_node(repair_apply_left, { name = "ai_runtime_test:hazard" })
set_test_node(repair_apply_center, { name = "ai_runtime_test:hazard" })
local repair_apply_writes = 0
local function counting_repair_set_node(pos, node)
	repair_apply_writes = repair_apply_writes + 1
	return set_test_node(pos, node)
end

local repair_apply_plan = core.repair_agent.plan_area(repair_apply_center, {
	agent_id = plugin_agent.agent_id,
	owner = plugin_agent.owner,
	task_id = "repair-apply:plan",
	radius = 1,
	get_node = get_test_node,
	set_node = counting_repair_set_node,
	sample_limit = 16,
})
assert(repair_apply_plan.ok == true)
assert(#repair_apply_plan.candidates == 2)
assert(repair_apply_writes == 0)

local repair_apply_disabled = core.repair_agent.apply_plan(repair_apply_plan, {
	agent_id = plugin_agent.agent_id,
	owner = plugin_agent.owner,
	task_id = "repair-apply:disabled",
	world_id = "test-world",
	get_node = get_test_node,
	set_node = counting_repair_set_node,
	allow_hazards = true,
})
assert(repair_apply_disabled.ok == false)
assert(repair_apply_disabled.status == "blocked")
assert(repair_apply_disabled.reason == "repair_mutation_not_enabled")
assert(repair_apply_disabled.changed == 0)
assert(repair_apply_writes == 0)

local repair_apply_no_rollback = core.repair_agent.apply_plan(repair_apply_plan, {
	agent_id = plugin_agent.agent_id,
	owner = plugin_agent.owner,
	task_id = "repair-apply:no-rollback",
	world_id = "test-world",
	get_node = get_test_node,
	set_node = counting_repair_set_node,
	allow_mutation = true,
	allow_hazards = true,
	max_node_writes = 1,
})
assert(repair_apply_no_rollback.ok == false)
assert(repair_apply_no_rollback.status == "blocked")
assert(repair_apply_no_rollback.reason == "rollback_metadata_unavailable")
assert(repair_apply_no_rollback.changed == 0)
assert(repair_apply_writes == 0)

local persisted_repair_records = {}
local repair_apply_result = core.repair_agent.apply_plan(repair_apply_plan, {
	agent_id = plugin_agent.agent_id,
	owner = plugin_agent.owner,
	task_id = "repair-apply:success",
	world_id = "test-world",
	get_node = get_test_node,
	set_node = counting_repair_set_node,
	allow_mutation = true,
	allow_hazards = true,
	max_node_writes = 1,
	persist_record = function(record)
		persisted_repair_records[#persisted_repair_records + 1] = record
		return "repair-store:" .. record.record_id
	end,
})
assert(repair_apply_result.ok == true)
assert(repair_apply_result.status == "partial")
assert(repair_apply_result.operation == "repair_agent.apply_plan")
assert(repair_apply_result.changed == 1)
assert(repair_apply_result.skipped == 1)
assert(repair_apply_result.reason == "repair_operations_skipped")
assert(repair_apply_result.rollback_record_id ~= nil)
assert(repair_apply_result.rollback_storage_ref ~= nil)
assert(repair_apply_result.metrics.node_writes == 1)
assert(repair_apply_result.metrics.candidate_count == 2)
assert(repair_apply_result.metrics.rollback_records == 1)
assert(#persisted_repair_records == 1)
assert(#persisted_repair_records[1].changed_positions == 1)
assert(repair_apply_writes == 1)

local repaired_count = 0
for _, pos in ipairs({ repair_apply_left, repair_apply_center }) do
	if get_test_node(pos).name == "air" then
		repaired_count = repaired_count + 1
	end
end
assert(repaired_count == 1)

local repair_protected_pos = test_pos(4268)
set_test_node(repair_protected_pos, { name = "ai_runtime_test:hazard" })
old_is_protected = core.is_protected
core.is_protected = function(pos, name)
	return name == plugin_agent.owner and pos.x == repair_protected_pos.x
end
local protected_repair_apply = core.repair_agent.apply_plan({
	agent_id = plugin_agent.agent_id,
	task_id = "repair-apply:protected-plan",
	candidates = {
		{
			pos = repair_protected_pos,
			node_name = "ai_runtime_test:hazard",
			planned_action = "remove_node",
			replacement = "air",
			family = "hazard",
		},
	},
}, {
	agent_id = plugin_agent.agent_id,
	owner = plugin_agent.owner,
	task_id = "repair-apply:protected",
	world_id = "test-world",
	get_node = get_test_node,
	set_node = counting_repair_set_node,
	allow_mutation = true,
	allow_hazards = true,
	persist_record = function(record)
		return "repair-store:" .. record.record_id
	end,
})
assert(protected_repair_apply.ok == false)
assert(protected_repair_apply.status == "blocked")
assert(protected_repair_apply.changed == 0)
assert(protected_repair_apply.skipped == 1)
assert(protected_repair_apply.reason == "all_repair_operations_skipped")
assert(get_test_node(repair_protected_pos).name == "ai_runtime_test:hazard")
core.is_protected = old_is_protected

local queued_apply_pos = test_pos(4269)
set_test_node(queued_apply_pos, { name = "ai_runtime_test:hazard" })
local queued_repair_apply = core.repair_agent.queue_apply_task({
	task_id = "repair-apply:queued",
	agent_id = plugin_agent.agent_id,
	owner = plugin_agent.owner,
	world_id = "test-world",
	plan = {
		candidates = {
			{
				pos = queued_apply_pos,
				node_name = "ai_runtime_test:hazard",
				planned_action = "remove_node",
				replacement = "air",
				family = "hazard",
			},
		},
	},
	get_node = get_test_node,
	set_node = counting_repair_set_node,
	allow_mutation = true,
	allow_hazards = true,
	max_node_writes_per_step = 1,
	persist_record = function(record)
		return "repair-store:" .. record.record_id
	end,
})
assert(queued_repair_apply.status == "queued")
core.step_ai_tasks()
local completed_repair_apply = core.get_ai_task("repair-apply:queued")
assert(completed_repair_apply.status == "completed")
assert(completed_repair_apply.last_result.operation == "repair_agent.apply_plan")
assert(completed_repair_apply.last_result.changed == 1)
assert(completed_repair_apply.last_result.rollback_record_id ~= nil)
assert(get_test_node(queued_apply_pos).name == "air")

local default_storage_repair_pos = test_pos(4270)
set_test_node(default_storage_repair_pos, { name = "ai_runtime_test:hazard" })
local default_storage_repair_plan = core.repair_agent.plan_area(default_storage_repair_pos, {
	agent_id = plugin_agent.agent_id,
	owner = plugin_agent.owner,
	task_id = "repair-default-storage:plan",
	radius = 0,
	get_node = get_test_node,
	set_node = counting_repair_set_node,
	sample_limit = 8,
})
local default_storage_records = {}
core.ai_rollback_storage.configure({
	enabled = true,
	persist_record = function(record)
		default_storage_records[#default_storage_records + 1] = record
		return {
			ok = true,
			storage_ref = "rollback://default/" .. record.record_id,
		}
	end,
})
local default_storage_repair = core.repair_agent.apply_plan(default_storage_repair_plan, {
	agent_id = plugin_agent.agent_id,
	owner = plugin_agent.owner,
	task_id = "repair-default-storage:apply",
	world_id = "test-world",
	get_node = get_test_node,
	set_node = counting_repair_set_node,
	allow_mutation = true,
	allow_hazards = true,
	max_node_writes = 1,
})
assert(default_storage_repair.ok == true)
assert(default_storage_repair.changed == 1)
assert(default_storage_repair.rollback_storage_ref ~= nil)
assert(default_storage_repair.rollback_storage_ref:find("rollback://default/", 1, true))
assert(#default_storage_records == 1)
assert(default_storage_records[1].mutation_class == "repair")
assert(get_test_node(default_storage_repair_pos).name == "air")
core.ai_rollback_storage.configure(nil)

assert(core.build_agent ~= nil)
core.build_agent.configure({
	light_node = "ai_runtime_test:stone",
	marker_node = "ai_runtime_test:stone",
	platform_node = "ai_runtime_test:stone",
	path_node = "ai_runtime_test:stone",
	max_nodes_per_task = 16,
})

local build_origin = test_pos(4280)
local build_writes = 0
local function counting_build_set_node(pos, node)
	build_writes = build_writes + 1
	return set_test_node(pos, node)
end

local build_definitions = {
	{
		kind = "lights",
		expected_label = "build lights",
		expected_count = 2,
		options = {
			count = 2,
		},
	},
	{
		kind = "marker",
		expected_label = "build marker",
		expected_count = 1,
		options = {},
	},
	{
		kind = "platform",
		expected_label = "build platform",
		expected_count = 4,
		options = {
			width = 2,
			depth = 2,
		},
	},
	{
		kind = "path",
		expected_label = "build path",
		expected_count = 3,
		options = {
			length = 3,
			direction = { x = 1, y = 0, z = 0 },
		},
	},
}

local platform_definition = nil
for index, entry in ipairs(build_definitions) do
	local definition_options = table.copy(entry.options)
	definition_options.kind = entry.kind
	definition_options.task_id = "build-agent:test:" .. entry.kind
	definition_options.agent_id = plugin_agent.agent_id
	definition_options.owner = "builder"
	definition_options.origin = vector.add(build_origin, { x = index * 8, y = 0, z = 0 })
	definition_options.get_node = get_test_node
	definition_options.set_node = counting_build_set_node
	definition_options.max_node_writes_per_step = 8
	local definition = core.build_agent.define_task(definition_options)
	assert(definition.task_id == definition_options.task_id)
	assert(definition.agent_id == plugin_agent.agent_id)
	assert(definition.owner == "builder")
	assert(definition.label == entry.expected_label)
	assert(definition.mutation_class == "build")
	assert(definition.required_capabilities["world.place"] == true)
	assert(definition.budget.max_steps_per_step == 1)
	assert(definition.budget.max_node_writes_per_step == 8)
	assert(definition.metadata.kind == entry.kind)
	assert(definition.metadata.placement_count == entry.expected_count)
	assert(type(definition.steps[1]) == "function")
	assert(build_writes == 0)
	if entry.kind == "platform" then
		platform_definition = definition
	end
end

assert(platform_definition ~= nil)
local queued_build_definition = core.queue_ai_task(platform_definition)
assert(queued_build_definition.status == "queued")
assert(build_writes == 0)
core.step_ai_tasks()
local completed_build_definition = core.get_ai_task(platform_definition.task_id)
assert(completed_build_definition.status == "blocked")
assert(completed_build_definition.last_result.operation == "ai_rollback.write_record")
assert(completed_build_definition.last_result.reason == "rollback_metadata_unavailable")
assert(completed_build_definition.last_result.changed == 0)
assert(build_writes == 0)

local default_storage_build_records = {}
core.ai_rollback_storage.configure({
	enabled = true,
	persist_record = function(record)
		default_storage_build_records[#default_storage_build_records + 1] = record
		return {
			ok = true,
			storage_ref = "rollback://default/" .. record.record_id,
		}
	end,
})
local default_storage_build_pos = test_pos(4310)
set_test_node(default_storage_build_pos, { name = "air" })
local default_storage_build_definition = core.build_agent.define_task({
	kind = "marker",
	task_id = "build-agent:default-storage",
	agent_id = plugin_agent.agent_id,
	owner = "builder",
	world_id = "test-world",
	origin = default_storage_build_pos,
	get_node = get_test_node,
	set_node = counting_build_set_node,
	max_node_writes_per_step = 1,
})
core.queue_ai_task(default_storage_build_definition)
core.step_ai_tasks()
local completed_default_storage_build =
	core.get_ai_task("build-agent:default-storage")
assert(completed_default_storage_build.status == "completed")
assert(completed_default_storage_build.last_result.changed == 1)
assert(completed_default_storage_build.last_result.rollback_storage_ref ~= nil)
assert(completed_default_storage_build.last_result.rollback_storage_ref:find(
	"rollback://default/", 1, true))
assert(#default_storage_build_records == 1)
assert(default_storage_build_records[1].mutation_class == "build")
assert(get_test_node(default_storage_build_pos).name == "ai_runtime_test:stone")
core.ai_rollback_storage.configure(nil)

local persisted_build_records = {}
local build_success_writes_before = build_writes
local build_success_origin = test_pos(4320)
for index, entry in ipairs(build_definitions) do
	local definition_options = table.copy(entry.options)
	definition_options.kind = entry.kind
	definition_options.task_id = "build-agent:rollback:" .. entry.kind
	definition_options.agent_id = plugin_agent.agent_id
	definition_options.owner = "builder"
	definition_options.world_id = "test-world"
	definition_options.origin = vector.add(build_success_origin, { x = index * 8, y = 0, z = 0 })
	definition_options.get_node = get_test_node
	definition_options.set_node = counting_build_set_node
	definition_options.max_node_writes_per_step = 8
	definition_options.persist_record = function(record)
		persisted_build_records[#persisted_build_records + 1] = record
		return "build-store:" .. record.record_id
	end
	local writes_before_definition = build_writes
	local definition = core.build_agent.define_task(definition_options)
	assert(build_writes == writes_before_definition)
	core.queue_ai_task(definition)
	core.step_ai_tasks()
	local completed_build = core.get_ai_task(definition.task_id)
	assert(completed_build.status == "completed")
	assert(completed_build.last_result.operation == "ai_world.batch_place")
	assert(completed_build.last_result.changed == entry.expected_count)
	assert(completed_build.last_result.rollback_record_id ~= nil)
	assert(completed_build.last_result.rollback_storage_ref ~= nil)
	assert(completed_build.last_result.metrics.node_writes == entry.expected_count)
end

local expected_build_writes = 0
for _, entry in ipairs(build_definitions) do
	expected_build_writes = expected_build_writes + entry.expected_count
end
assert(build_writes == build_success_writes_before + expected_build_writes)
assert(#persisted_build_records == #build_definitions)
for _, record in ipairs(persisted_build_records) do
	assert(record.mutation_class == "build")
	assert(record.operation_label == "build_agent.execute")
	assert(#record.changed_positions == #record.previous_nodes)
	assert(record.private_payload == nil)
	assert(record.asset_payload == nil)
end

assert(core.ai_runtime_smoke ~= nil)

local smoke_success = core.ai_runtime_smoke.run_scenario({
	agent_id = "smoke_agent:success",
	owner = "synthetic-operator",
	world_id = "synthetic-smoke-world",
	origin = test_pos(4400),
	build_node = "ai_runtime_test:stone",
	repair_node = "ai_runtime_test:hazard",
	replacement_node = "air",
})
assert(smoke_success.schema_version == 1)
assert(smoke_success.operation == "ai_runtime_smoke.run_scenario")
assert(smoke_success.ok == true)
assert(smoke_success.status == "success")
assert(smoke_success.run_context.mode == "synthetic-task-loop-smoke")
assert(smoke_success.run_context.requires_private_world == false)
assert(smoke_success.run_context.requires_private_assets == false)
assert(smoke_success.run_context.requires_live_pi == false)
assert(smoke_success.task_statuses.build == "completed")
assert(smoke_success.task_statuses.repair == "completed")
assert(smoke_success.results.build.status == "success")
assert(smoke_success.results.repair.status == "success")
assert(smoke_success.results.build.changed == 1)
assert(smoke_success.results.repair.changed == 1)
assert(smoke_success.rollback_records == 2)
assert(smoke_success.audit_event_count >= 4)
assert(#smoke_success.blocked_or_unsafe_outcomes == 0)
assert(smoke_success.world_after.build_node == "ai_runtime_test:stone")
assert(smoke_success.world_after.repair_node == "air")
assert(smoke_success.private_prompt == nil)
assert(smoke_success.asset_payload == nil)

local smoke_repeat = core.ai_runtime_smoke.run_scenario({
	agent_id = "smoke_agent:success",
	owner = "synthetic-operator",
	world_id = "synthetic-smoke-world",
	origin = test_pos(4430),
	build_node = "ai_runtime_test:stone",
	repair_node = "ai_runtime_test:hazard",
	replacement_node = "air",
})
assert(smoke_repeat.ok == true)
assert(smoke_repeat.status == "success")
assert(smoke_repeat.tasks.build.task_id ~= smoke_success.tasks.build.task_id)
assert(smoke_repeat.tasks.repair.task_id ~= smoke_success.tasks.repair.task_id)

local smoke_blocked = core.ai_runtime_smoke.run_scenario({
	agent_id = "smoke_agent:blocked",
	owner = "synthetic-operator",
	world_id = "synthetic-smoke-world",
	origin = test_pos(4450),
	build_node = "ai_runtime_test:stone",
	repair_node = "ai_runtime_test:hazard",
	replacement_node = "air",
	block_repair_rollback = true,
})
assert(smoke_blocked.ok == false)
assert(smoke_blocked.status == "blocked")
assert(smoke_blocked.task_statuses.build == "completed")
assert(smoke_blocked.task_statuses.repair == "blocked")
assert(smoke_blocked.results.repair.status == "blocked")
assert(smoke_blocked.results.repair.reason == "rollback_metadata_unavailable")
assert(#smoke_blocked.blocked_or_unsafe_outcomes >= 1)
assert(smoke_blocked.blocked_or_unsafe_outcomes[1].task_id
	== "ai-runtime-smoke:smoke_agent_blocked:repair")
assert(smoke_blocked.rollback_records == 1)
assert(smoke_blocked.world_after.build_node == "ai_runtime_test:stone")
assert(smoke_blocked.world_after.repair_node == "ai_runtime_test:hazard")
assert(smoke_blocked.private_prompt == nil)
assert(smoke_blocked.asset_payload == nil)

assert(core.registered_chatcommands.ai_runtime_smoke ~= nil)
assert(core.registered_chatcommands.ai_runtime_smoke.privs.server == true)
local smoke_command_ok, smoke_command_message =
	core.registered_chatcommands.ai_runtime_smoke.func(
		"admin",
		"origin=4480")
assert(smoke_command_ok == true)
assert(smoke_command_message:find("\"operation\":\"ai_runtime_smoke.run_scenario\"", 1, true))
assert(smoke_command_message:find("\"status\":\"success\"", 1, true))
assert(smoke_command_message:find("\"task_statuses\"", 1, true))
assert(smoke_command_message:find("\"rollback_records\":2", 1, true))
assert(smoke_command_message:find("\"audit_event_count\"", 1, true))
assert(smoke_command_message:find("\"blocked_or_unsafe_outcomes\":[]", 1, true))
assert(not smoke_command_message:find("/Users/", 1, true))
assert(not smoke_command_message:find("minecraftpi", 1, true))
assert(not smoke_command_message:find("private_prompt", 1, true))
assert(not smoke_command_message:find("asset_payload", 1, true))
assert(#smoke_command_message < 12000)

local smoke_blocked_command_ok, smoke_blocked_command_message =
	core.registered_chatcommands.ai_runtime_smoke.func(
		"admin",
		"mode=blocked origin=4490")
assert(smoke_blocked_command_ok == true)
assert(smoke_blocked_command_message:find("\"status\":\"blocked\"", 1, true))
assert(smoke_blocked_command_message:find("\"reason\":\"rollback_metadata_unavailable\"", 1, true))
assert(smoke_blocked_command_message:find("\"rollback_records\":1", 1, true))
assert(smoke_blocked_command_message:find("\"blocked_or_unsafe_outcomes\":[", 1, true))
assert(#smoke_blocked_command_message < 12000)

local private_option_ok, private_option_message =
	core.registered_chatcommands.ai_runtime_smoke.func("admin", "agent=bill")
assert(private_option_ok == false)
assert(private_option_message:find("unknown option", 1, true))
