core.ai_agent_plugin = {}

local plugin = core.ai_agent_plugin
local player_states = {}
local player_task_ids = {}
local player_entity_ids = {}
local task_sequence = 0
local model_adapter = nil
local default_capabilities = {}
local settings = {
	capability_profile = nil,
	light_node = "default:torch",
	marker_node = "default:mese_post_light",
	agent_entity_name = "ai_demo_benchmark:helper",
	repair_nodes = {},
	max_lights = 12,
	max_entity_move_distance = 16,
	max_defend_distance = 8,
	capabilities = table.copy(default_capabilities),
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

local function configure_product_surfaces()
	if core.build_agent then
		core.build_agent.configure({
			light_node = settings.light_node,
			marker_node = settings.marker_node,
			platform_node = settings.marker_node,
			path_node = settings.marker_node,
			max_nodes_per_task = settings.max_lights,
			sample_limit = settings.max_lights,
		})
	end
	if core.repair_agent then
		core.repair_agent.configure({
			repair_nodes = settings.repair_nodes,
			radius = 0,
			sample_limit = settings.max_lights,
		})
	end
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
	if options.capability_profile then
		assert(type(options.capability_profile) == "string"
			and options.capability_profile ~= "", "Capability profile must be a non-empty string")
		settings.capability_profile = options.capability_profile
	end
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
	if options.max_defend_distance then
		settings.max_defend_distance = options.max_defend_distance
	end
	if options.capabilities then
		assert(type(options.capabilities) == "table", "Capabilities must be a table")
		settings.capabilities = table.copy(options.capabilities)
	end
	configure_product_surfaces()
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
		capabilities = table.copy(settings.capabilities),
		limits = {
			capability_profile = settings.capability_profile,
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

local function queue_defined_task(name, action, label, definition)
	local task = core.queue_ai_task(definition)
	remember_task(name, task.task_id)
	return public_reply(name, action, "queued", label .. " queued.", {
		task_id = task.task_id,
	})
end

local function handle_light(name, prompt, context)
	context = context or {}
	configure_product_surfaces()
	local count = tonumber(prompt:match("(%d+)%s+lights?")) or 1
	count = math.max(1, math.min(count, settings.max_lights))
	local base = default_pos(context)
	local task_id = next_task_id(name, "light")
	return queue_defined_task(name, "light", "place " .. count .. " light node(s)",
		core.build_agent.define_task({
			kind = "lights",
			task_id = task_id,
			agent_id = agent_id_for(name),
			owner = name,
			world_id = context.world_id or "ai_agent_plugin",
			origin = base,
			count = count,
			get_node = context.get_node,
			set_node = context.set_node,
			max_node_writes_per_step = count,
			persist_record = context.persist_record or context.persist_rollback_record,
			rollback_policy = context.rollback_policy,
			operation_label = "ai_agent_plugin.light",
		}))
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
	configure_product_surfaces()
	local pos = default_pos(context)
	local task_id = next_task_id(name, "build")
	return queue_defined_task(name, "build", "build marker",
		core.build_agent.define_task({
			kind = "marker",
			task_id = task_id,
			agent_id = agent_id_for(name),
			owner = name,
			world_id = context.world_id or "ai_agent_plugin",
			origin = pos,
			get_node = context.get_node,
			set_node = context.set_node,
			max_node_writes_per_step = 1,
			persist_record = context.persist_record or context.persist_rollback_record,
			rollback_policy = context.rollback_policy,
			operation_label = "ai_agent_plugin.build",
		}))
end

local function handle_build_plan(name, context)
	context = context or {}
	configure_product_surfaces()
	local result = core.build_agent.plan({
		kind = "marker",
		task_id = context.task_id,
		agent_id = agent_id_for(name),
		owner = name,
		world_id = context.world_id or "ai_agent_plugin",
		origin = default_pos(context),
		rollback_policy = context.rollback_policy,
		sample_limit = context.sample_limit or settings.max_lights,
	})
	local plan = table.copy(result.plan or {})
	plan.operation = result.operation
	plan.status = result.status
	plan.reason = result.reason
	plan.message = result.message
	plan.changed = result.changed
	plan.examined = result.examined
	plan.skipped = result.skipped
	plan.samples = result.samples or {}
	plan.metrics = result.metrics or {}
	return public_reply(name, "build_plan", result.status, "Build plan returned without mutation.", {
		plan = plan,
		planned_node_writes = plan.metrics.planned_node_writes or 0,
	})
end

local function compact_repair_plan(plan)
	return {
		ok = plan.ok,
		status = plan.status,
		operation = plan.operation,
		agent_id = plan.agent_id,
		task_id = plan.task_id,
		changed = plan.changed,
		examined = plan.examined,
		skipped = plan.skipped,
		reason = plan.reason,
		message = plan.message,
		candidate_count = #(plan.candidates or {}),
		candidates = plan.candidates or {},
		samples = plan.samples or {},
		metrics = plan.metrics or {},
		will_mutate = false,
	}
end

local function handle_repair_plan(name, context)
	context = context or {}
	configure_product_surfaces()
	local plan = core.repair_agent.plan_area(default_pos(context), {
		agent_id = agent_id_for(name),
		owner = name,
		task_id = context.task_id,
		radius = 0,
		repair_nodes = settings.repair_nodes,
		get_node = context.get_node,
		sample_limit = context.sample_limit or settings.max_lights,
	})
	local compact = compact_repair_plan(plan)
	return public_reply(name, "repair_plan", plan.status, "Repair plan returned without mutation.", {
		plan = compact,
		candidate_count = compact.candidate_count,
	})
end

local function handle_repair(name, context)
	context = context or {}
	configure_product_surfaces()
	local pos = default_pos(context)
	local task_id = next_task_id(name, "repair")
	local plan = core.repair_agent.plan_area(pos, {
		agent_id = agent_id_for(name),
		owner = name,
		task_id = task_id .. ":plan",
		radius = 0,
		repair_nodes = settings.repair_nodes,
		get_node = context.get_node,
		sample_limit = context.sample_limit or settings.max_lights,
	})
	local task = core.repair_agent.queue_apply_task({
		task_id = task_id,
		agent_id = agent_id_for(name),
		owner = name,
		world_id = context.world_id or "ai_agent_plugin",
		plan = plan,
		allow_mutation = true,
		allow_hazards = true,
		get_node = context.get_node,
		set_node = context.set_node,
		max_node_writes_per_step = 1,
		persist_record = context.persist_record or context.persist_rollback_record,
		rollback_policy = context.rollback_policy,
		operation_label = "ai_agent_plugin.repair",
	})
	remember_task(name, task.task_id)
	return public_reply(name, "repair", "queued", "repair nearby hazard queued.", {
		task_id = task.task_id,
		plan_status = plan.status,
		candidate_count = #(plan.candidates or {}),
	})
end

local function compact_audit_record(record)
	return {
		event_type = record.event_type,
		agent_id = record.agent_id,
		task_id = record.task_id,
		operation = record.operation,
		status = record.status,
		reason = record.reason,
		rollback_record_id = record.rollback_record_id,
		rollback_storage_ref = record.rollback_storage_ref,
		mutation_class = record.mutation_class,
		changed = record.changed,
		skipped = record.skipped,
		payload_retained = record.payload_retained == true,
	}
end

local function audit_events_for(name, limit)
	local agent_id = agent_id_for(name)
	local events = {}
	for _, record in ipairs(core.get_ai_runtime_audit({ limit = limit or 25 })) do
		if record.agent_id == agent_id then
			events[#events + 1] = compact_audit_record(record)
		end
	end
	return events
end

local function handle_guide(name)
	return public_reply(name, "guide", "success", "First-party agent guide returned.", {
		surfaces = {
			builder = true,
			repair = true,
			guide = true,
			defender = true,
		},
		commands = {
			"status",
			"tasks",
			"cancel",
			"light",
			"build plan",
			"build marker",
			"repair plan",
			"repair",
			"defend",
			"audit",
			"rollback",
		},
		tasks = active_player_tasks(name),
	})
end

local function handle_audit(name)
	return public_reply(name, "audit", "success", "Recent agent audit events returned.", {
		audit_events = audit_events_for(name, 50),
	})
end

local function handle_rollback_review(name)
	local records = {}
	for _, record in ipairs(audit_events_for(name, 100)) do
		if record.event_type == "rollback.record" and record.rollback_record_id then
			records[#records + 1] = record
		end
	end
	return public_reply(name, "rollback", "success", "Recent rollback records returned.", {
		rollback_records = records,
	})
end

local function handle_defend(name, context)
	context = context or {}
	return queue_plugin_task(name, "defend", "defend player", {
		function()
			return core.ai_player_ops.defend(name, {
				agent_id = agent_id_for(name),
				owner = name,
				task_id = context.task_id,
				get_player_by_name = context.get_player_by_name,
				hostiles = context.hostiles,
				find_hostiles = context.find_hostiles,
				attack_entity = context.attack_entity,
				max_distance = context.max_defend_distance or context.max_distance
					or settings.max_defend_distance,
			})
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
	local result = core.ai_model_ops.request(prompt, {
		agent_id = agent_id_for(name),
		owner = name,
		task_id = context.task_id,
		private_prompt = context.private_prompt,
		adapter = model_adapter,
		adapter_name = context.adapter_name or "ai_agent_plugin",
		context = context,
	})
	return public_reply(name, "model", result.ok and "success" or "blocked",
		result.message or "Model adapter did not return a response.", {
			reason = result.reason,
		})
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
	if prompt == "guide" or prompt == "help" then
		return handle_guide(name)
	end
	if prompt == "audit" or prompt == "history" then
		return handle_audit(name)
	end
	if prompt == "rollback" or prompt == "rollback review" then
		return handle_rollback_review(name)
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
	if (prompt:find("plan", 1, true) or prompt:find("preview", 1, true))
			and (prompt:find("build", 1, true) or prompt:find("marker", 1, true)) then
		return handle_build_plan(name, context)
	end
	if (prompt:find("plan", 1, true) or prompt:find("preview", 1, true))
			and (prompt:find("repair", 1, true) or prompt:find("fix", 1, true)) then
		return handle_repair_plan(name, context)
	end
	if prompt:find("repair", 1, true) or prompt:find("fix", 1, true) then
		return handle_repair(name, context)
	end
	if prompt:find("defend", 1, true) then
		return handle_defend(name, context)
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
