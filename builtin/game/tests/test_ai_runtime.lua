local function assert_result(result, ok, status, reason)
	assert(type(result) == "table")
	assert(result.ok == ok)
	assert(result.status == status)
	assert(result.reason == reason)
	assert(result.operation == "capability.check")
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
