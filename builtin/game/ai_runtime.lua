core.registered_ai_agents = {}
core.registered_ai_tasks = {}

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
			task.status = "running"
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
				budget = budget - 1
				task.updated_at = core.get_us_time and core.get_us_time() or task.updated_at
				if not ok then
					task.status = "failed"
					task.last_result = make_task_result(task.task_id, false, "failed",
						"step_error", tostring(result))
					break
				end
				task.progress.current = task.progress.current + 1
				task.last_result = type(result) == "table" and table.copy(result) or {
					ok = true,
					status = "success",
				}
				if task.budget.max_node_writes_per_step > 0
						and (task.last_result.changed or 0) > task.budget.max_node_writes_per_step then
					task.status = "unsafe"
					task.last_result = make_task_result(task.task_id, false, "unsafe",
						"node_write_budget_exceeded",
						"Task step exceeded its node-write budget.")
					break
				end
				if task.last_result.status == "blocked" or task.last_result.status == "unsafe"
						or task.last_result.status == "failed" then
					task.status = task.last_result.status
					break
				end
			end
			if task.status == "running" and task.progress.current >= task.progress.total then
				task.status = "completed"
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
