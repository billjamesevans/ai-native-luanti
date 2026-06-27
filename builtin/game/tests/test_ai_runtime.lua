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
assert(metrics.tasks_queued == 5)
assert(metrics.task_steps_run == 5)
assert(metrics.tasks_completed == 2)
assert(metrics.tasks_cancelled == 2)
assert(metrics.tasks_unsafe == 1)
assert(metrics.queue_length == 0)
assert(metrics.active_tasks == 0)
assert(metrics.node_writes >= 4)
assert(metrics.skipped_operations >= 6)
assert(metrics.unsafe_operations >= 1)
assert(metrics.rollback_records_written >= 2)
assert(metrics.rollback_record_failures >= 1)
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
	.. "writes=total=7,world=5,reported=2 unsafe=3 audit=9 "
	.. "model=pending=4,requests=6,ok=3,fail=2,timeout=1")
assert(not formatted_metrics:find("nova:emma", 1, true))

local operator_metrics = core.get_ai_runtime_operator_metrics()
assert(type(operator_metrics.task_status_counts) == "table")
assert(operator_metrics.task_status_counts.completed >= 2)
assert(operator_metrics.task_status_counts.cancelled >= 2)
assert(operator_metrics.task_status_counts.unsafe >= 1)

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
assert(#demo_report.scenarios == 4)

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
assert(demo_scenarios.movement_patrol.metrics.movement_steps == 5)
assert(demo_scenarios.movement_patrol.metrics.distance_moved > 0)
assert(demo_scenarios.collision_wall_contact.metrics.collision_checks > 0)
assert(demo_scenarios.collision_wall_contact.metrics.collision_events > 0)
assert(demo_scenarios.cleanup_despawn.metrics.cleaned_up == 4)
local post_demo_metrics = core.get_ai_runtime_metrics()
assert(post_demo_metrics.entities_by_type["ai_demo_benchmark:helper"] == 0)

assert(core.registered_chatcommands.ai_runtime ~= nil)
local command_ok, command_message = core.registered_chatcommands.ai_runtime.func("admin", "")
assert(command_ok == true)
assert(command_message:find("AI runtime: queue=", 1, true))
assert(command_message:find("tasks=", 1, true))
assert(command_message:find("writes=", 1, true))
assert(command_message:find("audit=", 1, true))
assert(command_message:find("model=", 1, true))
assert(not command_message:find("do not retain this prompt", 1, true))
assert(#command_message < 240)

local audit = core.get_ai_runtime_audit({ limit = 100 })
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
assert(audit_has("task.unsafe", "task:write-budget"))
assert(audit_has("world.unsafe", nil))

local last_audit = audit[#audit]
assert(last_audit.event_type == "model.request")
assert(last_audit.private_payload == nil)
assert(last_audit.payload_retained == false)

core.ai_agent_plugin.configure({
	light_node = "ai_runtime_test:stone",
	marker_node = "ai_runtime_test:stone",
	repair_nodes = {
		["ai_runtime_test:hazard"] = true,
	},
	max_lights = 3,
})

local plugin_agent = core.ai_agent_plugin.ensure_player_agent("Wills")
assert(plugin_agent.agent_id == "nova_agent:Wills")
assert(plugin_agent.owner == "Wills")
assert(plugin_agent.plugin == "ai_agent_plugin")
assert(core.agent_has_capability(plugin_agent.agent_id, "world.read") == true)
assert(core.agent_has_capability(plugin_agent.agent_id, "world.place") == true)

local same_agent = core.ai_agent_plugin.ensure_player_agent("Wills")
assert(same_agent.agent_id == plugin_agent.agent_id)

assert(core.registered_chatcommands.bot ~= nil)
assert(core.registered_chatcommands.nova ~= nil)
assert(core.registered_chatcommands.aibot ~= nil)

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
assert(get_test_node(vector.add(plugin_base, { x = 0, y = 1, z = 0 })).name
	== "ai_runtime_test:stone")

local follow_reply = core.ai_agent_plugin.handle_command("Wills", "follow me", {
	pos = plugin_base,
})
assert(follow_reply.ok == true)
assert(follow_reply.action == "follow")
assert(core.ai_agent_plugin.get_player_state("Wills").mode == "follow")

local come_reply = core.ai_agent_plugin.handle_command("Wills", "come", {
	pos = vector.add(plugin_base, { x = 3, y = 0, z = 0 }),
})
assert(come_reply.ok == true)
assert(come_reply.action == "come")
assert(core.ai_agent_plugin.get_player_state("Wills").target_pos.x == plugin_base.x + 3)

local build_pos = test_pos(4210)
set_test_node(build_pos, { name = "air" })
local build_reply = core.ai_agent_plugin.handle_command("Wills", "build marker", {
	pos = build_pos,
	get_node = get_test_node,
	set_node = set_test_node,
})
assert(build_reply.ok == true)
assert(build_reply.action == "build")
assert(core.get_ai_task(build_reply.task_id).status == "queued")
assert(get_test_node(build_pos).name == "air")
core.step_ai_tasks()
assert(get_test_node(build_pos).name == "ai_runtime_test:stone")

local repair_pos = test_pos(4220)
set_test_node(repair_pos, { name = "ai_runtime_test:hazard" })
local repair_reply = core.ai_agent_plugin.handle_command("Wills", "repair", {
	pos = repair_pos,
	get_node = get_test_node,
	set_node = set_test_node,
})
assert(repair_reply.ok == true)
assert(repair_reply.action == "repair")
assert(get_test_node(repair_pos).name == "ai_runtime_test:hazard")
core.step_ai_tasks()
assert(get_test_node(repair_pos).name == "air")

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
