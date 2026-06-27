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
