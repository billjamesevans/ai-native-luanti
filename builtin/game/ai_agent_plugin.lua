core.ai_agent_plugin = {}

local plugin = core.ai_agent_plugin
local player_states = {}
local player_task_ids = {}
local player_entity_ids = {}
local task_sequence = 0
local model_adapter = nil
local settings = {
	light_node = "default:torch",
	marker_node = "default:mese_post_light",
	agent_entity_name = "ai_demo_benchmark:helper",
	repair_nodes = {},
	max_lights = 12,
	max_entity_move_distance = 16,
}

local function copy_pos(pos)
	if not pos then
		return nil
	end
	return {
		x = pos.x,
		y = pos.y,
		z = pos.z,
	}
end

local function normalize_player_name(name)
	assert(type(name) == "string" and name ~= "", "Player name must be a non-empty string")
	return name
end

local function agent_id_for(name)
	return "nova_agent:" .. normalize_player_name(name)
end

local function next_task_id(name, action)
	task_sequence = task_sequence + 1
	return "nova_agent:" .. name .. ":" .. action .. ":" .. task_sequence
end

local function default_pos(context)
	context = context or {}
	if context.pos then
		return copy_pos(context.pos)
	end
	if context.player_name and core.get_player_by_name then
		local player = core.get_player_by_name(context.player_name)
		if player and player.get_pos then
			return player:get_pos()
		end
	end
	return { x = 0, y = 0, z = 0 }
end

local function world_options(name, context)
	context = context or {}
	return {
		agent_id = agent_id_for(name),
		owner = name,
		task_id = context.task_id,
		get_node = context.get_node,
		set_node = context.set_node,
		sample_limit = context.sample_limit or 4,
		max_changes = context.max_changes,
		allow_hazards = context.allow_hazards,
	}
end

local function public_reply(name, action, status, message, extra)
	extra = extra or {}
	extra.ok = status == "success" or status == "queued" or status == "partial"
	extra.status = status
	extra.action = action
	extra.agent_id = agent_id_for(name)
	extra.message = message
	return extra
end

function plugin.configure(options)
	options = options or {}
	if options.light_node then
		settings.light_node = options.light_node
	end
	if options.marker_node then
		settings.marker_node = options.marker_node
	end
	if options.agent_entity_name then
		settings.agent_entity_name = options.agent_entity_name
	end
	if options.repair_nodes then
		settings.repair_nodes = table.copy(options.repair_nodes)
	end
	if options.max_lights then
		settings.max_lights = options.max_lights
	end
	if options.max_entity_move_distance then
		settings.max_entity_move_distance = options.max_entity_move_distance
	end
end

function plugin.ensure_player_agent(name)
	name = normalize_player_name(name)
	local agent_id = agent_id_for(name)
	local existing = core.get_ai_agent(agent_id)
	if existing then
		return existing
	end
	return core.register_ai_agent({
		agent_id = agent_id,
		display_name = "Nova Agent - " .. name,
		owner = name,
		plugin = "ai_agent_plugin",
		capabilities = {
			["world.read"] = true,
			["world.place"] = true,
			["world.remove"] = true,
			["entity.spawn"] = true,
			["entity.control"] = true,
			["task.cancel"] = true,
			["model.request"] = true,
		},
		limits = {
			max_nodes_per_step = settings.max_lights,
			max_entities = 1,
			max_entity_move_distance = settings.max_entity_move_distance,
		},
	})
end

function plugin.get_player_state(name)
	name = normalize_player_name(name)
	if not player_states[name] then
		player_states[name] = {
			mode = "idle",
		}
	end
	return table.copy(player_states[name])
end

local function set_player_state(name, state)
	player_states[name] = table.copy(state)
	return plugin.get_player_state(name)
end

function plugin.set_model_adapter(adapter)
	assert(adapter == nil or type(adapter) == "function", "Model adapter must be a function")
	model_adapter = adapter
end

local function remember_task(name, task_id)
	player_task_ids[name] = player_task_ids[name] or {}
	player_task_ids[name][#player_task_ids[name] + 1] = task_id
end

local function active_player_tasks(name)
	local result = {}
	for _, task_id in ipairs(player_task_ids[name] or {}) do
		local task = core.get_ai_task(task_id)
		if task then
			result[#result + 1] = task
		end
	end
	return result
end

local function agent_entity_id_for(name)
	return agent_id_for(name) .. ":helper"
end

local function entity_options(name, context)
	context = context or {}
	return {
		agent_id = agent_id_for(name),
		owner = name,
		task_id = context.task_id,
		spawn_entity = context.spawn_entity,
		max_entities = 1,
		max_distance = context.max_entity_move_distance or settings.max_entity_move_distance,
	}
end

local function queue_plugin_task(name, action, label, steps, context)
	context = context or {}
	local task_id = next_task_id(name, action)
	context.task_id = task_id
	local task = core.queue_ai_task({
		task_id = task_id,
		agent_id = agent_id_for(name),
		owner = name,
		label = label,
		budget = {
			max_steps_per_step = 1,
			max_node_writes_per_step = context.max_node_writes_per_step or settings.max_lights,
		},
		steps = steps,
	})
	remember_task(name, task_id)
	return public_reply(name, action, "queued", label .. " queued.", {
		task_id = task.task_id,
	})
end

local function light_positions(base, count)
	local positions = {}
	for i = 1, count do
		positions[i] = {
			x = base.x + (i - 1),
			y = base.y + 1,
			z = base.z,
		}
	end
	return positions
end

local function handle_light(name, prompt, context)
	context = context or {}
	local count = tonumber(prompt:match("(%d+)%s+lights?")) or 1
	count = math.max(1, math.min(count, settings.max_lights))
	local base = default_pos(context)
	return queue_plugin_task(name, "light", "place " .. count .. " light node(s)", {
		function()
			local placements = {}
			for _, pos in ipairs(light_positions(base, count)) do
				placements[#placements + 1] = {
					pos = pos,
					node_name = settings.light_node,
				}
			end
			local options = world_options(name, context)
			options.task_id = context.task_id
			options.max_changes = count
			return core.ai_world_ops.batch_place(placements, options)
		end,
	}, context)
end

local function update_player_entity_state(name, state, entity_id)
	state = table.copy(state or plugin.get_player_state(name))
	state.entity_id = entity_id
	set_player_state(name, state)
end

local function ensure_agent_entity(name, pos, context, state)
	local entity_id = player_entity_ids[name] or agent_entity_id_for(name)
	local options = entity_options(name, context)
	local inspected = core.ai_entity_ops.inspect(entity_id, options)
	if inspected.ok then
		player_entity_ids[name] = entity_id
		update_player_entity_state(name, state, entity_id)
		return entity_id, inspected
	end

	options.entity_id = entity_id
	local spawned = core.ai_entity_ops.spawn(settings.agent_entity_name, pos, options)
	if not spawned.ok then
		return nil, spawned
	end
	entity_id = spawned.entity.entity_id
	player_entity_ids[name] = entity_id
	update_player_entity_state(name, state, entity_id)
	return entity_id, spawned
end

local function handle_agent_move(name, action, label, target_pos, state, context)
	context = context or {}
	local target = copy_pos(target_pos)
	return queue_plugin_task(name, action, label, {
		function()
			local entity_id, setup_result = ensure_agent_entity(name, target, context, state)
			if not entity_id then
				return setup_result
			end
			local options = entity_options(name, context)
			local moved = core.ai_entity_ops.move(entity_id, target, options)
			if moved.ok and moved.entity then
				update_player_entity_state(name, state, moved.entity.entity_id)
			end
			return moved
		end,
	}, context)
end

local function handle_build(name, context)
	context = context or {}
	local pos = default_pos(context)
	return queue_plugin_task(name, "build", "build marker", {
		function()
			local options = world_options(name, context)
			options.task_id = context.task_id
			return core.ai_world_ops.place_node(pos, settings.marker_node, options)
		end,
	}, context)
end

local function handle_repair(name, context)
	context = context or {}
	local pos = default_pos(context)
	return queue_plugin_task(name, "repair", "repair nearby hazard", {
		function()
			local options = world_options(name, context)
			options.task_id = context.task_id
			local node = options.get_node and options.get_node(pos) or core.get_node_or_nil(pos)
			if node and settings.repair_nodes[node.name] then
				options.allow_hazards = true
				return core.ai_world_ops.remove_node(pos, options)
			end
			return {
				ok = true,
				status = "success",
				changed = 0,
				examined = 1,
				skipped = 0,
				reason = "no_repair_needed",
				message = "No configured repair target was found.",
			}
		end,
	}, context)
end

local function handle_cancel(name)
	local cancelled = 0
	for _, task in ipairs(active_player_tasks(name)) do
		if task.status == "queued" or task.status == "running" or task.status == "paused" then
			local result = core.cancel_ai_task(task.task_id, name)
			if result.ok then
				cancelled = cancelled + 1
			end
		end
	end
	return public_reply(name, "cancel", cancelled > 0 and "success" or "blocked",
		cancelled > 0 and ("Cancelled " .. cancelled .. " task(s).") or "No active tasks to cancel.", {
			cancelled = cancelled,
		})
end

local function handle_tasks(name)
	return public_reply(name, "tasks", "success", "Task list returned.", {
		tasks = active_player_tasks(name),
	})
end

local function handle_model(name, prompt, context)
	context = context or {}
	core.record_ai_runtime_audit({
		event_type = "model.request",
		agent_id = agent_id_for(name),
		message = "Model adapter requested.",
		private_payload = {
			prompt = context.private_prompt or prompt,
		},
	})
	if not model_adapter then
		return public_reply(name, "model", "blocked", "No model adapter is configured.")
	end
	local started_at = core.get_us_time and core.get_us_time() or 0
	local ok, result = pcall(model_adapter, {
		agent_id = agent_id_for(name),
		owner = name,
		prompt = prompt,
		context = context,
	})
	if not ok then
		result = {
			ok = false,
			message = "Model adapter failed.",
			reason = "adapter_error",
		}
	end
	local elapsed_us = result and result.elapsed_us
	if not elapsed_us then
		elapsed_us = started_at > 0 and core.get_us_time and (core.get_us_time() - started_at) or 0
	end
	local adapter_status = "failure"
	if result and result.timeout then
		adapter_status = "timeout"
	elseif result and result.ok then
		adapter_status = "success"
	end
	core.record_ai_model_adapter_result({
		agent_id = agent_id_for(name),
		owner_ref = name,
		task_id = context.task_id,
		adapter_name = result and result.adapter_name or context.adapter_name or "ai_agent_plugin",
		status = adapter_status,
		reason = result and result.reason,
		elapsed_us = elapsed_us,
	})
	return public_reply(name, "model", result and result.ok and "success" or "blocked",
		result and result.message or "Model adapter did not return a response.")
end

function plugin.handle_command(name, param, context)
	name = normalize_player_name(name)
	plugin.ensure_player_agent(name)
	context = context or {}
	context.player_name = name
	local prompt = tostring(param or ""):lower():trim()

	if prompt == "" or prompt == "status" then
		return public_reply(name, "status", "success", "Nova agent is ready.", {
			state = plugin.get_player_state(name),
			metrics = core.get_ai_runtime_metrics(),
		})
	end
	if prompt == "tasks" or prompt == "task status" or prompt == "builder" then
		return handle_tasks(name)
	end
	if prompt == "cancel" or prompt == "stop" then
		return handle_cancel(name)
	end
	if prompt:find("follow me", 1, true) or prompt == "follow" then
		local state = set_player_state(name, {
			mode = "follow",
			target_name = name,
		})
		return handle_agent_move(name, "follow", "follow " .. name,
			default_pos(context), state, context)
	end
	if prompt == "come" or prompt:find("come here", 1, true) then
		local target = default_pos(context)
		local state = set_player_state(name, {
			mode = "come",
			target_pos = target,
		})
		return handle_agent_move(name, "come", "come to player", target, state, context)
	end
	if prompt:find("light", 1, true) then
		return handle_light(name, prompt, context)
	end
	if prompt:find("repair", 1, true) or prompt:find("fix", 1, true) then
		return handle_repair(name, context)
	end
	if prompt:find("build", 1, true) or prompt:find("marker", 1, true) then
		return handle_build(name, context)
	end
	return handle_model(name, prompt, context)
end

local function register_command(name)
	core.register_chatcommand(name, {
		params = "<message>",
		description = "Control your first-party AI agent.",
		privs = { interact = true },
		func = function(player_name, param)
			local result = plugin.handle_command(player_name, param or "")
			return result.ok, result.message
		end,
	})
end

register_command("bot")
register_command("nova")
register_command("aibot")
