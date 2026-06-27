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
})
assert(formatted_metrics ==
	"AI runtime: queue=2 tasks=queued=1,running=1,completed=4,unsafe=1 "
	.. "writes=total=7,world=5,reported=2 unsafe=3 audit=9 model=4")
assert(not formatted_metrics:find("nova:emma", 1, true))

local operator_metrics = core.get_ai_runtime_operator_metrics()
assert(type(operator_metrics.task_status_counts) == "table")
assert(operator_metrics.task_status_counts.completed >= 2)
assert(operator_metrics.task_status_counts.cancelled >= 2)
assert(operator_metrics.task_status_counts.unsafe >= 1)

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
core.ai_agent_plugin.set_model_adapter(function(request)
	table.insert(adapter_calls, request)
	return {
		ok = true,
		message = "mock adapter response",
	}
end)

local model_reply = core.ai_agent_plugin.handle_command("Wills", "what should we explore next?", {
	private_prompt = "do not store this model prompt",
})
assert(model_reply.ok == true)
assert(model_reply.action == "model")
assert(model_reply.message == "mock adapter response")
assert(#adapter_calls == 1)
assert(adapter_calls[1].agent_id == plugin_agent.agent_id)

local plugin_audit = core.get_ai_runtime_audit({ limit = 10 })
local model_record = plugin_audit[#plugin_audit]
assert(model_record.event_type == "model.request")
assert(model_record.agent_id == plugin_agent.agent_id)
assert(model_record.private_payload == nil)
assert(model_record.payload_retained == false)

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
