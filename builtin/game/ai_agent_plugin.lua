core.ai_agent_plugin = {}

local plugin = core.ai_agent_plugin
local player_states = {}
local player_task_ids = {}
local player_entity_ids = {}
local player_pending_approvals = {}
local task_sequence = 0
local approval_sequence = 0
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
	max_follow_steps = 6,
	max_follow_step_distance = 4,
	max_follow_total_distance = 24,
	max_follow_stop_distance = 1,
	max_follow_wall_time_ms = 250,
	max_navigation_nodes = 64,
	max_defend_distance = 8,
	capabilities = table.copy(default_capabilities),
}

local PRODUCT_SURFACE_ORDER = {
	"builder",
	"repair",
	"guide",
	"defender",
	"importer",
}

local PRODUCT_SURFACES = {
	builder = {
		surface_id = "builder",
		display_name = "Builder Agent",
		default_clean_profile_grant = "granted",
		required_capabilities = { "world.read", "world.place" },
		optional_capabilities = { "task.cancel" },
		commands = { "build plan", "build marker", "approve build", "light" },
		runtime_entrypoints = {
			"core.build_agent.plan",
			"core.build_agent.define_task",
		},
		mutation_policy = "preview_then_approval_rollback_backed",
	},
	repair = {
		surface_id = "repair",
		display_name = "Repair Agent",
		default_clean_profile_grant = "granted",
		required_capabilities = { "world.read", "world.place" },
		optional_capabilities = { "task.cancel" },
		commands = { "repair plan", "repair", "approve repair" },
		runtime_entrypoints = {
			"core.repair_agent.plan_area",
			"core.repair_agent.queue_apply_task",
		},
		mutation_policy = "preview_then_approval_rollback_backed",
	},
	guide = {
		surface_id = "guide",
		display_name = "Guide Agent",
		default_clean_profile_grant = "granted",
		required_capabilities = { "world.read" },
		optional_capabilities = { "task.cancel", "http.llm" },
		commands = { "guide", "tasks", "cancel", "audit", "rollback" },
		runtime_entrypoints = {
			"core.get_ai_task",
			"core.get_ai_runtime_audit",
			"core.cancel_ai_task",
		},
		mutation_policy = "read_only_review_or_owner_task_control",
	},
	defender = {
		surface_id = "defender",
		display_name = "Defender Agent",
		default_clean_profile_grant = "not_granted",
		required_capabilities = { "combat.defend" },
		optional_capabilities = { "task.cancel" },
		commands = { "defend" },
		runtime_entrypoints = {
			"core.ai_player_ops.defend",
		},
		mutation_policy = "operator_or_plugin_profile_only",
	},
	importer = {
		surface_id = "importer",
		display_name = "Importer Agent",
		default_clean_profile_grant = "not_granted",
		required_capabilities = { "import.assets" },
		optional_capabilities = { "task.cancel" },
		commands = { "import plan", "import preview", "import inventory" },
		runtime_entrypoints = {
			"core.ai_import_ops.plan",
		},
		mutation_policy = "dry_run_only_operator_or_plugin_profile",
	},
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

local function product_surface(surface_id)
	assert(PRODUCT_SURFACES[surface_id] ~= nil, "Unknown AI agent product surface")
	return PRODUCT_SURFACES[surface_id]
end

local function surface_agent_id_for(name, surface_id)
	return agent_id_for(name) .. ":" .. product_surface(surface_id).surface_id
end

local function capability_subset(surface)
	local capabilities = {}
	for _, capability in ipairs(surface.required_capabilities or {}) do
		if settings.capabilities[capability] then
			capabilities[capability] = true
		end
	end
	for _, capability in ipairs(surface.optional_capabilities or {}) do
		if settings.capabilities[capability] then
			capabilities[capability] = true
		end
	end
	return capabilities
end

local function capability_list_for(surface)
	local result = {}
	for _, capability in ipairs(surface.required_capabilities or {}) do
		result[#result + 1] = capability
	end
	for _, capability in ipairs(surface.optional_capabilities or {}) do
		result[#result + 1] = capability
	end
	return result
end

local function granted_capability_list_for(surface)
	local result = {}
	for _, capability in ipairs(capability_list_for(surface)) do
		if settings.capabilities[capability] then
			result[#result + 1] = capability
		end
	end
	return result
end

local function surface_required_capabilities_granted(surface)
	for _, capability in ipairs(surface.required_capabilities or {}) do
		if not settings.capabilities[capability] then
			return false
		end
	end
	return true
end

local function compact_product_surface(surface_id, name)
	local surface = product_surface(surface_id)
	return {
		surface_id = surface.surface_id,
		agent_id = name and surface_agent_id_for(name, surface_id) or nil,
		display_name = surface.display_name,
		capability_profile = settings.capability_profile,
		default_clean_profile_grant = surface.default_clean_profile_grant,
		required_capabilities = table.copy(surface.required_capabilities or {}),
		optional_capabilities = table.copy(surface.optional_capabilities or {}),
		granted_capabilities = granted_capability_list_for(surface),
		required_capabilities_granted = surface_required_capabilities_granted(surface),
		commands = table.copy(surface.commands or {}),
		runtime_entrypoints = table.copy(surface.runtime_entrypoints or {}),
		mutation_policy = surface.mutation_policy,
	}
end

function plugin.get_product_surfaces(name)
	local normalized_name = name and normalize_player_name(name) or nil
	local surfaces = {}
	for _, surface_id in ipairs(PRODUCT_SURFACE_ORDER) do
		surfaces[#surfaces + 1] = compact_product_surface(surface_id, normalized_name)
	end
	return surfaces
end

function plugin.get_product_surface(surface_id, name)
	local normalized_name = name and normalize_player_name(name) or nil
	return compact_product_surface(surface_id, normalized_name)
end

local function next_task_id(name, action)
	task_sequence = task_sequence + 1
	return "nova_agent:" .. name .. ":" .. action .. ":" .. task_sequence
end

local function next_approval_id(name, action)
	approval_sequence = approval_sequence + 1
	return "nova_agent:" .. name .. ":" .. action .. ":approval:" .. approval_sequence
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
		or status == "pending_approval"
	extra.status = status
	extra.action = action
	if extra.surface_id and not extra.agent_id then
		extra.agent_id = surface_agent_id_for(name, extra.surface_id)
	end
	extra.agent_id = extra.agent_id or agent_id_for(name)
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
	if options.max_follow_steps then
		settings.max_follow_steps = options.max_follow_steps
	end
	if options.max_follow_step_distance then
		settings.max_follow_step_distance = options.max_follow_step_distance
	end
	if options.max_follow_total_distance then
		settings.max_follow_total_distance = options.max_follow_total_distance
	end
	if options.max_follow_stop_distance then
		settings.max_follow_stop_distance = options.max_follow_stop_distance
	end
	if options.max_follow_wall_time_ms then
		settings.max_follow_wall_time_ms = options.max_follow_wall_time_ms
	end
	if options.max_navigation_nodes then
		settings.max_navigation_nodes = options.max_navigation_nodes
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
			max_follow_steps = settings.max_follow_steps,
			max_follow_step_distance = settings.max_follow_step_distance,
			max_follow_total_distance = settings.max_follow_total_distance,
			max_navigation_nodes = settings.max_navigation_nodes,
		},
	})
end

function plugin.ensure_surface_agent(name, surface_id)
	name = normalize_player_name(name)
	local surface = product_surface(surface_id)
	local agent_id = surface_agent_id_for(name, surface_id)
	local existing = core.get_ai_agent(agent_id)
	if existing then
		return existing
	end
	return core.register_ai_agent({
		agent_id = agent_id,
		display_name = surface.display_name .. " - " .. name,
		owner = name,
		plugin = "ai_agent_plugin:" .. surface.surface_id,
		capabilities = capability_subset(surface),
		limits = {
			capability_profile = settings.capability_profile,
			product_surface = surface.surface_id,
			default_clean_profile_grant = surface.default_clean_profile_grant,
			max_nodes_per_step = settings.max_lights,
			max_entities = surface.surface_id == "guide" and 0 or 1,
			max_entity_move_distance = settings.max_entity_move_distance,
			max_follow_steps = settings.max_follow_steps,
			max_follow_step_distance = settings.max_follow_step_distance,
			max_follow_total_distance = settings.max_follow_total_distance,
			max_navigation_nodes = settings.max_navigation_nodes,
		},
	})
end

function plugin.get_navigation_contract()
	return {
		schema_version = 1,
		contract_kind = "ai_native_navigation_perception_contract",
		surfaces = { "builder", "guide", "helper" },
		commands = { "follow", "come" },
		planner = "bounded_same_level_grid_or_injected_pathfinder",
		bounds = {
			max_nodes_searched = settings.max_navigation_nodes,
			max_step_distance = settings.max_follow_step_distance,
			max_total_distance = settings.max_follow_total_distance,
			max_wall_time_ms = settings.max_follow_wall_time_ms,
			max_entities = 1,
			node_writes = 0,
		},
		perception = {
			node_reader = "context.get_node_or_opt_in_core.get_node",
			obstacle_policy = "air_or_nonwalkable_nodes_are_passable",
			public_safe = true,
		},
		blocked_reasons = {
			"navigation_obstacle_blocked",
			"navigation_node_budget_exhausted",
			"navigation_wall_time_budget_exceeded",
			"follow_distance_limit_exceeded",
			"owner_mismatch",
			"entity_limit_exceeded",
			"task_cancelled",
			"lag_threshold_exceeded",
		},
	}
end

function plugin.ensure_product_agents(name)
	name = normalize_player_name(name)
	local agents = {}
	plugin.ensure_player_agent(name)
	for _, surface_id in ipairs(PRODUCT_SURFACE_ORDER) do
		agents[surface_id] = plugin.ensure_surface_agent(name, surface_id)
	end
	return agents
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

local function approval_context(context)
	context = context or {}
	return {
		pos = copy_pos(context.pos),
		player_name = context.player_name,
		world_id = context.world_id,
		get_node = context.get_node,
		set_node = context.set_node,
		persist_record = context.persist_record,
		persist_rollback_record = context.persist_rollback_record,
		rollback_policy = context.rollback_policy,
		sample_limit = context.sample_limit,
		max_node_writes_per_step = context.max_node_writes_per_step,
		max_wall_time_ms = context.max_wall_time_ms,
	}
end

local function compact_pending_approval(pending)
	if not pending then
		return nil
	end
	return {
		approval_id = pending.approval_id,
		surface_id = pending.surface_id,
		pending_action = pending.action,
		plan = pending.plan,
		candidate_count = pending.candidate_count,
		planned_node_writes = pending.planned_node_writes,
	}
end

local function remember_pending_approval(name, action, plan, context, extra)
	extra = extra or {}
	local pending = {
		approval_id = next_approval_id(name, action),
		surface_id = extra.surface_id,
		action = action,
		plan = plan,
		context = approval_context(context),
		candidate_count = extra.candidate_count,
		planned_node_writes = extra.planned_node_writes,
	}
	player_pending_approvals[name] = pending
	return pending
end

local function agent_entity_id_for(name)
	return agent_id_for(name) .. ":helper"
end

local function task_agent_id_for(name, context)
	context = context or {}
	if context.surface_id then
		plugin.ensure_surface_agent(name, context.surface_id)
		return surface_agent_id_for(name, context.surface_id)
	end
	return agent_id_for(name)
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
	local agent_id = task_agent_id_for(name, context)
	local task = core.queue_ai_task({
		task_id = task_id,
		agent_id = agent_id,
		owner = name,
		label = label,
		budget = {
			max_steps_per_step = 1,
			max_node_writes_per_step = context.max_node_writes_per_step or settings.max_lights,
			max_wall_time_ms = context.max_wall_time_ms or 0,
		},
		steps = steps,
	})
	remember_task(name, task_id)
	return public_reply(name, action, "queued", label .. " queued.", {
		task_id = task.task_id,
		surface_id = context.surface_id,
		agent_id = agent_id,
	})
end

local function queue_defined_task(name, action, label, definition, surface_id)
	if surface_id then
		plugin.ensure_surface_agent(name, surface_id)
	end
	local task = core.queue_ai_task(definition)
	remember_task(name, task.task_id)
	return public_reply(name, action, "queued", label .. " queued.", {
		task_id = task.task_id,
		surface_id = surface_id,
		agent_id = definition.agent_id,
	})
end

local function handle_light(name, prompt, context)
	context = context or {}
	configure_product_surfaces()
	local count = tonumber(prompt:match("(%d+)%s+lights?")) or 1
	count = math.max(1, math.min(count, settings.max_lights))
	local base = default_pos(context)
	local task_id = next_task_id(name, "light")
	local agent_id = surface_agent_id_for(name, "builder")
	plugin.ensure_surface_agent(name, "builder")
	return queue_defined_task(name, "light", "place " .. count .. " light node(s)",
		core.build_agent.define_task({
			kind = "lights",
			task_id = task_id,
			agent_id = agent_id,
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
		}), "builder")
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

local follow_options
local follow_next_step
local make_follow_result

local function handle_agent_move(name, action, label, target_pos, state, context)
	context = context or {}
	local target = copy_pos(target_pos)
	local move_context = table.copy(context)
	if move_context.max_follow_steps == nil then
		move_context.max_follow_steps = 1
	end
	if move_context.max_follow_stop_distance == nil then
		move_context.max_follow_stop_distance = 0
	end
	local options = follow_options("follow", move_context)
	local move_state = {
		steps_run = 0,
		distance_moved = 0,
		max_steps = options.max_steps,
		max_step_distance = options.max_step_distance,
		max_total_distance = options.max_total_distance,
		stop_distance = options.stop_distance,
		max_nodes_searched = options.max_nodes_searched,
	}
	local steps = {}
	for _ = 1, options.max_steps do
		steps[#steps + 1] = function()
			move_state.steps_run = move_state.steps_run + 1
			local entity_id, setup_result = ensure_agent_entity(name, target, context, state)
			if not entity_id then
				return setup_result
			end
			local current_pos = setup_result.entity and setup_result.entity.pos or target
			local next_pos, step_distance, distance_to_target, path_status, path_meta =
				follow_next_step(current_pos, target, options, context, move_state)
			if path_meta.blocked then
				return make_follow_result(name, context, move_state, "blocked",
					path_meta.blocked_reason or "navigation_obstacle_blocked",
					"Come navigation could not find a bounded path.", {
						operation = "ai_agent.navigation_step",
						entity = setup_result.entity,
						examined = path_meta.nodes_searched or 0,
						skipped = 1,
						step_distance = 0,
						distance_to_target = distance_to_target,
						path_status = path_status,
						path_planner = path_meta.planner,
						path_waypoint_count = path_meta.path_waypoint_count,
						pathfinder_used = path_meta.pathfinder_used,
						nodes_searched = path_meta.nodes_searched,
						max_nodes_searched = path_meta.max_nodes_searched,
						obstacles_seen = path_meta.obstacles_seen,
						navigation_elapsed_us = path_meta.elapsed_us,
						max_wall_time_ms = path_meta.max_wall_time_ms,
						skipped_reason = path_meta.blocked_reason,
						blocked_reason = path_meta.blocked_reason,
					})
			end
			if step_distance <= 0 then
				return make_follow_result(name, context, move_state, "success",
					"navigation_target_reached", "Helper is within navigation distance.", {
						operation = "ai_agent.navigation_step",
						entity = setup_result.entity,
						examined = 1,
						skipped = 1,
						step_distance = 0,
						distance_to_target = distance_to_target,
						path_status = path_status,
						path_planner = path_meta.planner,
						path_waypoint_count = path_meta.path_waypoint_count,
						pathfinder_used = path_meta.pathfinder_used,
						nodes_searched = path_meta.nodes_searched,
						max_nodes_searched = path_meta.max_nodes_searched,
						obstacles_seen = path_meta.obstacles_seen,
						navigation_elapsed_us = path_meta.elapsed_us,
						max_wall_time_ms = path_meta.max_wall_time_ms,
						skipped_reason = "within_stop_distance",
					})
			end
			if move_state.distance_moved + step_distance > options.max_total_distance then
				return make_follow_result(name, context, move_state, "blocked",
					"navigation_distance_limit_exceeded",
					"Navigation task exceeded its total movement distance limit.", {
						operation = "ai_agent.navigation_step",
						entity = setup_result.entity,
						examined = 1,
						skipped = 1,
						step_distance = step_distance,
						distance_to_target = distance_to_target,
						path_status = path_status,
						path_planner = path_meta.planner,
						path_waypoint_count = path_meta.path_waypoint_count,
						pathfinder_used = path_meta.pathfinder_used,
						nodes_searched = path_meta.nodes_searched,
						max_nodes_searched = path_meta.max_nodes_searched,
						obstacles_seen = path_meta.obstacles_seen,
						navigation_elapsed_us = path_meta.elapsed_us,
						max_wall_time_ms = path_meta.max_wall_time_ms,
						skipped_reason = "max_total_distance",
						blocked_reason = "navigation_distance_limit_exceeded",
					})
			end
			local move_context = table.copy(context)
			move_context.max_entity_move_distance = options.max_step_distance
			local moved = core.ai_entity_ops.move(entity_id, next_pos,
				entity_options(name, move_context))
			if moved.ok and moved.entity then
				local moved_distance = moved.metrics and moved.metrics.distance or step_distance
				move_state.distance_moved = move_state.distance_moved + moved_distance
				update_player_entity_state(name, state, moved.entity.entity_id)
			end
			return make_follow_result(name, context, move_state, moved.status,
				moved.reason, moved.message, {
					operation = "ai_agent.navigation_step",
					entity = moved.entity,
					movement_result = {
						operation = moved.operation,
						status = moved.status,
						reason = moved.reason,
						message = moved.message,
					},
					examined = moved.examined,
					skipped = moved.skipped,
					step_distance = step_distance,
					distance_to_target = distance_to_target,
					distance_moved = moved.metrics and moved.metrics.distance or 0,
					path_status = path_status,
					path_planner = path_meta.planner,
					path_waypoint_count = path_meta.path_waypoint_count,
					pathfinder_used = path_meta.pathfinder_used,
					nodes_searched = path_meta.nodes_searched,
					max_nodes_searched = path_meta.max_nodes_searched,
					obstacles_seen = path_meta.obstacles_seen,
					navigation_elapsed_us = path_meta.elapsed_us,
					max_wall_time_ms = path_meta.max_wall_time_ms,
					skipped_reason = moved.skipped > 0 and moved.reason or nil,
					blocked_reason = moved.skipped > 0 and moved.reason or nil,
				})
		end
	end
	context.max_node_writes_per_step = 0
	context.max_wall_time_ms = options.wall_time_ms
	return queue_plugin_task(name, action, label, steps, context)
end

local function numeric_limit(value, fallback, minimum, maximum)
	local result = tonumber(value)
	if result == nil then
		result = fallback
	end
	result = math.max(minimum, result)
	if maximum then
		result = math.min(maximum, result)
	end
	return result
end

local function distance_between(a, b)
	local dx = b.x - a.x
	local dy = b.y - a.y
	local dz = b.z - a.z
	return math.sqrt(dx * dx + dy * dy + dz * dz)
end

local function step_toward(current_pos, target_pos, max_step_distance, stop_distance)
	local distance = distance_between(current_pos, target_pos)
	if distance <= stop_distance then
		return copy_pos(current_pos), 0, distance, "within_stop_distance"
	end
	local travel = math.min(max_step_distance, math.max(0, distance - stop_distance))
	if travel <= 0 then
		return copy_pos(current_pos), 0, distance, "no_step_required"
	end
	local ratio = travel / distance
	return {
		x = current_pos.x + (target_pos.x - current_pos.x) * ratio,
		y = current_pos.y + (target_pos.y - current_pos.y) * ratio,
		z = current_pos.z + (target_pos.z - current_pos.z) * ratio,
	}, travel, distance, "direct_line_bounded"
end

local function is_pos(pos)
	return type(pos) == "table" and type(pos.x) == "number"
		and type(pos.y) == "number" and type(pos.z) == "number"
end

local function compact_waypoints(path)
	if type(path) ~= "table" then
		return nil
	end
	local waypoints = {}
	for _, waypoint in ipairs(path) do
		if is_pos(waypoint) then
			waypoints[#waypoints + 1] = copy_pos(waypoint)
		end
	end
	if #waypoints == 0 then
		return nil
	end
	return waypoints
end

local function rounded_coord(value)
	return math.floor(value + 0.5)
end

local function navigation_grid_pos(pos)
	return {
		x = rounded_coord(pos.x),
		y = rounded_coord(pos.y),
		z = rounded_coord(pos.z),
	}
end

local function navigation_key(pos)
	return pos.x .. ":" .. pos.y .. ":" .. pos.z
end

local function navigation_get_node(pos, context)
	local get_node = context.get_node
	if not get_node and context.use_core_perception then
		get_node = core.get_node
	end
	if not get_node then
		return nil
	end
	local ok, node = pcall(get_node, copy_pos(pos))
	if ok and type(node) == "table" then
		return node
	end
	return nil
end

local function has_navigation_perception(context)
	return type(context.is_path_blocked) == "function"
		or type(context.get_node) == "function"
		or (context.use_core_perception == true and type(core.get_node) == "function")
end

local function navigation_pos_passable(pos, context, metrics)
	if context.is_path_blocked then
		local ok, blocked = pcall(context.is_path_blocked, copy_pos(pos))
		if ok and blocked == true then
			metrics.obstacles_seen = metrics.obstacles_seen + 1
			return false, "navigation_obstacle_blocked"
		elseif ok then
			return true
		end
	end

	local node = navigation_get_node(pos, context)
	if not node then
		return true
	end
	if node.name == "air" then
		return true
	end
	local def = core.registered_nodes and core.registered_nodes[node.name] or nil
	if def and (def.walkable == false or def.buildable_to == true) then
		return true
	end
	metrics.obstacles_seen = metrics.obstacles_seen + 1
	return false, "navigation_obstacle_blocked"
end

local function navigation_elapsed_us(start_us)
	if not start_us or not core.get_us_time then
		return 0
	end
	return math.max(0, core.get_us_time() - start_us)
end

local function make_navigation_meta(options, status, reason, metrics)
	metrics = metrics or {}
	return {
		pathfinder_used = true,
		planner = "bounded_same_level_grid",
		path_status = status,
		blocked = status == "blocked",
		blocked_reason = reason,
		path_waypoint_count = metrics.path_waypoint_count or 0,
		nodes_searched = metrics.nodes_searched or 0,
		max_nodes_searched = options.max_nodes_searched,
		obstacles_seen = metrics.obstacles_seen or 0,
		elapsed_us = metrics.elapsed_us or 0,
		max_wall_time_ms = options.wall_time_ms,
	}
end

local function bounded_grid_path(current_pos, target_pos, options, context)
	local start_us = core.get_us_time and core.get_us_time() or nil
	local start = navigation_grid_pos(current_pos)
	local goal = navigation_grid_pos(target_pos)
	local max_nodes = math.max(1, math.floor(options.max_nodes_searched or 1))
	local max_distance_remaining = math.max(0, options.max_total_distance_remaining or 0)
	local metrics = {
		nodes_searched = 0,
		obstacles_seen = 0,
	}
	local function fail(reason)
		metrics.elapsed_us = navigation_elapsed_us(start_us)
		return nil, make_navigation_meta(options, "blocked", reason, metrics)
	end
	local function passable(pos)
		return navigation_pos_passable(pos, context, metrics)
	end

	local start_ok = passable(start)
	if not start_ok then
		return fail("navigation_start_blocked")
	end
	local goal_ok = passable(goal)
	if not goal_ok then
		return fail("navigation_goal_blocked")
	end

	local start_key = navigation_key(start)
	local queue = {
		{
			pos = start,
			path = { copy_pos(start) },
			distance = 0,
		},
	}
	local seen = {
		[start_key] = true,
	}
	local head = 1
	local directions = {
		{ x = 1, z = 0 },
		{ x = 0, z = 1 },
		{ x = 0, z = -1 },
		{ x = -1, z = 0 },
	}

	while head <= #queue do
		if metrics.nodes_searched >= max_nodes then
			return fail("navigation_node_budget_exhausted")
		end
		if options.wall_time_ms > 0
				and navigation_elapsed_us(start_us) > options.wall_time_ms * 1000 then
			return fail("navigation_wall_time_budget_exceeded")
		end

		local item = queue[head]
		head = head + 1
		metrics.nodes_searched = metrics.nodes_searched + 1
		if distance_between(item.pos, goal) <= options.stop_distance then
			metrics.path_waypoint_count = #item.path
			metrics.elapsed_us = navigation_elapsed_us(start_us)
			return item.path, make_navigation_meta(options,
				"bounded_grid_path", nil, metrics)
		end

		for _, direction in ipairs(directions) do
			local next_pos = {
				x = item.pos.x + direction.x,
				y = item.pos.y,
				z = item.pos.z + direction.z,
			}
			local key = navigation_key(next_pos)
			if not seen[key] then
				seen[key] = true
				local next_distance = item.distance + 1
				if next_distance <= max_distance_remaining then
					local open = passable(next_pos)
					if open then
						local next_path = table.copy(item.path)
						next_path[#next_path + 1] = copy_pos(next_pos)
						queue[#queue + 1] = {
							pos = next_pos,
							path = next_path,
							distance = next_distance,
						}
					end
				end
			end
		end
	end

	return fail("navigation_obstacle_blocked")
end

local function direct_path_blocked(current_pos, next_pos, context)
	if not has_navigation_perception(context) then
		return false
	end
	local distance = distance_between(current_pos, next_pos)
	local samples = math.max(1, math.ceil(distance))
	local checked = {}
	local metrics = {
		obstacles_seen = 0,
	}
	for i = 1, samples do
		local ratio = i / samples
		local sample = navigation_grid_pos({
			x = current_pos.x + (next_pos.x - current_pos.x) * ratio,
			y = current_pos.y + (next_pos.y - current_pos.y) * ratio,
			z = current_pos.z + (next_pos.z - current_pos.z) * ratio,
		})
		local key = navigation_key(sample)
		if not checked[key] then
			checked[key] = true
			local open = navigation_pos_passable(sample, context, metrics)
			if not open then
				return true
			end
		end
	end
	return false
end

local function call_follow_pathfinder(current_pos, target_pos, options, context)
	if context.find_path then
		local ok, path = pcall(context.find_path, copy_pos(current_pos),
			copy_pos(target_pos), {
				max_step_distance = options.max_step_distance,
				stop_distance = options.stop_distance,
				max_total_distance = options.max_total_distance,
				max_total_distance_remaining = options.max_total_distance_remaining,
				max_waypoints = options.max_waypoints,
				max_nodes_searched = options.max_nodes_searched,
				max_wall_time_ms = options.wall_time_ms,
			})
		if ok then
			local waypoints = compact_waypoints(path)
			if waypoints then
				return waypoints, {
					pathfinder_used = true,
					planner = "injected_pathfinder",
					path_status = "pathfinder_waypoint_bounded",
					path_waypoint_count = #waypoints,
					nodes_searched = 0,
					max_nodes_searched = options.max_nodes_searched,
					obstacles_seen = 0,
					elapsed_us = 0,
					max_wall_time_ms = options.wall_time_ms,
				}
			end
		end
	end
	if has_navigation_perception(context) then
		return bounded_grid_path(current_pos, target_pos, options, context)
	end
	if context.use_core_pathfinder and core.find_path then
		local search_distance = math.max(1, math.ceil(distance_between(current_pos,
			target_pos)) + 2)
		local ok, path = pcall(core.find_path, current_pos, target_pos,
			search_distance, 1, 4, "A*")
		if ok then
			local waypoints = compact_waypoints(path)
			if waypoints then
				return waypoints, {
					pathfinder_used = true,
					planner = "core.find_path",
					path_status = "pathfinder_waypoint_bounded",
					path_waypoint_count = #waypoints,
					nodes_searched = 0,
					max_nodes_searched = options.max_nodes_searched,
					obstacles_seen = 0,
					elapsed_us = 0,
					max_wall_time_ms = options.wall_time_ms,
				}
			end
		end
	end
	return nil, nil
end

function follow_next_step(current_pos, target_pos, options, context, follow_state)
	local next_pos, step_distance, distance_to_target, path_status =
		step_toward(current_pos, target_pos, options.max_step_distance,
			options.stop_distance)
	if step_distance <= 0 then
		return next_pos, step_distance, distance_to_target, path_status, {
			pathfinder_used = false,
			path_waypoint_count = 0,
		}
	end

	local path_options = {
		max_step_distance = options.max_step_distance,
		stop_distance = options.stop_distance,
		max_total_distance = options.max_total_distance,
		max_total_distance_remaining = math.max(0,
			options.max_total_distance - (follow_state.distance_moved or 0)),
		max_waypoints = math.max(1,
			options.max_steps - (follow_state.steps_run or 0) + 1),
		max_nodes_searched = options.max_nodes_searched,
		wall_time_ms = options.wall_time_ms,
	}
	local should_plan = context.force_navigation_search == true
		or context.find_path ~= nil
		or context.use_core_pathfinder == true
		or direct_path_blocked(current_pos, next_pos, context)
	local waypoints, path_meta
	if should_plan then
		waypoints, path_meta = call_follow_pathfinder(current_pos, target_pos,
			path_options, context)
	end
	if not waypoints then
		if path_meta and path_meta.blocked then
			return copy_pos(current_pos), 0, distance_to_target,
				path_meta.path_status, path_meta
		end
		return next_pos, step_distance, distance_to_target, path_status, {
			pathfinder_used = false,
			path_waypoint_count = 0,
			nodes_searched = 0,
			max_nodes_searched = options.max_nodes_searched,
			obstacles_seen = 0,
			elapsed_us = 0,
			max_wall_time_ms = options.wall_time_ms,
		}
	end

	local waypoint = nil
	for _, candidate in ipairs(waypoints) do
		if distance_between(current_pos, candidate) > 0.001 then
			waypoint = candidate
			break
		end
	end
	if not waypoint then
		return next_pos, step_distance, distance_to_target, path_status, {
			pathfinder_used = false,
			path_waypoint_count = #waypoints,
			nodes_searched = path_meta and path_meta.nodes_searched or 0,
			max_nodes_searched = options.max_nodes_searched,
			obstacles_seen = path_meta and path_meta.obstacles_seen or 0,
			elapsed_us = path_meta and path_meta.elapsed_us or 0,
			max_wall_time_ms = options.wall_time_ms,
		}
	end

	local waypoint_distance = distance_between(current_pos, waypoint)
	if waypoint_distance <= options.max_step_distance then
		next_pos = copy_pos(waypoint)
		step_distance = waypoint_distance
	else
		next_pos, step_distance = step_toward(current_pos, waypoint,
			options.max_step_distance, 0)
	end
	return next_pos, step_distance, distance_to_target,
		(path_meta and path_meta.path_status) or "pathfinder_waypoint_bounded", {
			pathfinder_used = true,
			path_waypoint_count = #waypoints,
			planner = path_meta and path_meta.planner or "unknown",
			nodes_searched = path_meta and path_meta.nodes_searched or 0,
			max_nodes_searched = options.max_nodes_searched,
			obstacles_seen = path_meta and path_meta.obstacles_seen or 0,
			elapsed_us = path_meta and path_meta.elapsed_us or 0,
			max_wall_time_ms = options.wall_time_ms,
		}
end

local function follow_target_pos(name, context)
	local get_player = context.get_player_by_name or core.get_player_by_name
	if get_player then
		local ok, player = pcall(get_player, name)
		if ok and player and player.get_pos then
			local pos_ok, pos = pcall(player.get_pos, player)
			if pos_ok and pos then
				return copy_pos(pos)
			end
			return nil, "invalid_player_position"
		elseif not ok then
			return nil, "player_lookup_failed"
		end
	end
	if context.pos then
		return copy_pos(context.pos)
	end
	return nil, "follow_target_not_found"
end

function follow_options(prompt, context)
	context = context or {}
	local requested_steps = context.max_follow_steps
		or tonumber(prompt:match("follow%s+(%d+)"))
		or settings.max_follow_steps
	local max_steps = numeric_limit(requested_steps, settings.max_follow_steps,
		1, settings.max_follow_steps)
	local max_entity_step = context.max_entity_move_distance or settings.max_entity_move_distance
	local max_step_distance = numeric_limit(context.max_follow_step_distance,
		settings.max_follow_step_distance, 0, max_entity_step)
	local max_total_distance = numeric_limit(context.max_follow_total_distance,
		settings.max_follow_total_distance, 0, settings.max_follow_total_distance)
	local stop_distance = numeric_limit(context.max_follow_stop_distance,
		settings.max_follow_stop_distance, 0, nil)
	return {
		max_steps = max_steps,
		max_step_distance = max_step_distance,
		max_total_distance = max_total_distance,
		stop_distance = stop_distance,
		wall_time_ms = numeric_limit(context.max_follow_wall_time_ms,
			settings.max_follow_wall_time_ms, 0, settings.max_follow_wall_time_ms),
		max_nodes_searched = numeric_limit(context.max_navigation_nodes,
			settings.max_navigation_nodes, 1, settings.max_navigation_nodes),
	}
end

function make_follow_result(name, context, state, status, reason, message, extra)
	extra = extra or {}
	local result = {
		ok = status == "success" or status == "partial",
		status = status,
		operation = extra.operation or "ai_agent.follow_step",
		agent_id = agent_id_for(name),
		task_id = context.task_id,
		changed = 0,
		examined = extra.examined or 0,
		skipped = extra.skipped or 0,
		reason = reason,
		message = message,
		entity = extra.entity,
		movement_result = extra.movement_result,
		metrics = {
			node_writes = 0,
			step_distance = extra.step_distance or 0,
			distance_to_target = extra.distance_to_target or 0,
			distance_moved = extra.distance_moved or 0,
			total_distance_moved = state.distance_moved or 0,
			steps_run = state.steps_run or 0,
			max_steps = state.max_steps,
			max_step_distance = state.max_step_distance,
			max_total_distance = state.max_total_distance,
			stop_distance = state.stop_distance,
			path_status = extra.path_status,
			path_planner = extra.path_planner,
			path_waypoint_count = extra.path_waypoint_count or 0,
			pathfinder_used = extra.pathfinder_used == true,
			nodes_searched = extra.nodes_searched or 0,
			max_nodes_searched = extra.max_nodes_searched or state.max_nodes_searched,
			obstacles_seen = extra.obstacles_seen or 0,
			navigation_elapsed_us = extra.navigation_elapsed_us or 0,
			max_wall_time_ms = extra.max_wall_time_ms,
			skipped_reason = extra.skipped_reason,
			blocked_reason = extra.blocked_reason,
		},
	}
	return result
end

local function handle_follow(name, prompt, context)
	context = context or {}
	local options = follow_options(prompt, context)
	local state = set_player_state(name, {
		mode = "follow",
		target_name = name,
		max_steps = options.max_steps,
		max_step_distance = options.max_step_distance,
		max_total_distance = options.max_total_distance,
		max_navigation_nodes = options.max_nodes_searched,
	})
	local follow_state = {
		steps_run = 0,
		distance_moved = 0,
		max_steps = options.max_steps,
		max_step_distance = options.max_step_distance,
		max_total_distance = options.max_total_distance,
		stop_distance = options.stop_distance,
		max_nodes_searched = options.max_nodes_searched,
	}
	local steps = {}
	for _ = 1, options.max_steps do
		steps[#steps + 1] = function()
			follow_state.steps_run = follow_state.steps_run + 1
			local target_pos, target_error = follow_target_pos(name, context)
			if not target_pos then
				return make_follow_result(name, context, follow_state, "blocked",
					target_error, "Follow target position was not available.", {
						skipped = 1,
						skipped_reason = target_error,
					})
			end

			local entity_id, setup_result = ensure_agent_entity(name, target_pos, context, state)
			if not entity_id then
				return setup_result
			end

			local current_pos = setup_result.entity and setup_result.entity.pos or target_pos
			local next_pos, step_distance, distance_to_target, path_status, path_meta =
				follow_next_step(current_pos, target_pos, options, context,
					follow_state)
			if path_meta.blocked then
				return make_follow_result(name, context, follow_state, "blocked",
					path_meta.blocked_reason or "navigation_obstacle_blocked",
					"Follow navigation could not find a bounded path.", {
						entity = setup_result.entity,
						examined = path_meta.nodes_searched or 0,
						skipped = 1,
						step_distance = 0,
						distance_to_target = distance_to_target,
						path_status = path_status,
						path_planner = path_meta.planner,
						path_waypoint_count = path_meta.path_waypoint_count,
						pathfinder_used = path_meta.pathfinder_used,
						nodes_searched = path_meta.nodes_searched,
						max_nodes_searched = path_meta.max_nodes_searched,
						obstacles_seen = path_meta.obstacles_seen,
						navigation_elapsed_us = path_meta.elapsed_us,
						max_wall_time_ms = path_meta.max_wall_time_ms,
						skipped_reason = path_meta.blocked_reason,
						blocked_reason = path_meta.blocked_reason,
					})
			end
			if step_distance <= 0 then
				return make_follow_result(name, context, follow_state, "success",
					"follow_target_reached", "Helper is within follow distance.", {
						entity = setup_result.entity,
						examined = 1,
						skipped = 1,
						step_distance = 0,
						distance_to_target = distance_to_target,
						path_status = path_status,
						path_planner = path_meta.planner,
						path_waypoint_count = path_meta.path_waypoint_count,
						pathfinder_used = path_meta.pathfinder_used,
						nodes_searched = path_meta.nodes_searched,
						max_nodes_searched = path_meta.max_nodes_searched,
						obstacles_seen = path_meta.obstacles_seen,
						navigation_elapsed_us = path_meta.elapsed_us,
						max_wall_time_ms = path_meta.max_wall_time_ms,
						skipped_reason = "within_stop_distance",
					})
			end
			if follow_state.distance_moved + step_distance > options.max_total_distance then
				return make_follow_result(name, context, follow_state, "blocked",
					"follow_distance_limit_exceeded",
					"Follow task exceeded its total movement distance limit.", {
						entity = setup_result.entity,
						examined = 1,
						skipped = 1,
						step_distance = step_distance,
						distance_to_target = distance_to_target,
						path_status = path_status,
						path_planner = path_meta.planner,
						path_waypoint_count = path_meta.path_waypoint_count,
						pathfinder_used = path_meta.pathfinder_used,
						nodes_searched = path_meta.nodes_searched,
						max_nodes_searched = path_meta.max_nodes_searched,
						obstacles_seen = path_meta.obstacles_seen,
						navigation_elapsed_us = path_meta.elapsed_us,
						max_wall_time_ms = path_meta.max_wall_time_ms,
						skipped_reason = "max_total_distance",
						blocked_reason = "follow_distance_limit_exceeded",
					})
			end

			local move_context = table.copy(context)
			move_context.max_entity_move_distance = options.max_step_distance
			local moved = core.ai_entity_ops.move(entity_id, next_pos,
				entity_options(name, move_context))
			if moved.ok and moved.entity then
				local moved_distance = moved.metrics and moved.metrics.distance or step_distance
				follow_state.distance_moved = follow_state.distance_moved + moved_distance
				update_player_entity_state(name, state, moved.entity.entity_id)
			end
			return make_follow_result(name, context, follow_state, moved.status,
				moved.reason, moved.message, {
					entity = moved.entity,
					movement_result = {
						operation = moved.operation,
						status = moved.status,
						reason = moved.reason,
						message = moved.message,
					},
					examined = moved.examined,
					skipped = moved.skipped,
					step_distance = step_distance,
					distance_to_target = distance_to_target,
					distance_moved = moved.metrics and moved.metrics.distance or 0,
					path_status = path_status,
					path_planner = path_meta.planner,
					path_waypoint_count = path_meta.path_waypoint_count,
					pathfinder_used = path_meta.pathfinder_used,
					nodes_searched = path_meta.nodes_searched,
					max_nodes_searched = path_meta.max_nodes_searched,
					obstacles_seen = path_meta.obstacles_seen,
					navigation_elapsed_us = path_meta.elapsed_us,
					max_wall_time_ms = path_meta.max_wall_time_ms,
					skipped_reason = moved.skipped > 0 and moved.reason or nil,
					blocked_reason = moved.skipped > 0 and moved.reason or nil,
				})
		end
	end
	context.max_node_writes_per_step = 0
	context.max_wall_time_ms = options.wall_time_ms
	return queue_plugin_task(name, "follow", "follow " .. name, steps, context)
end

local function queue_build_task(name, context)
	context = context or {}
	configure_product_surfaces()
	local pos = default_pos(context)
	local task_id = next_task_id(name, "build")
	local agent_id = surface_agent_id_for(name, "builder")
	plugin.ensure_surface_agent(name, "builder")
	return queue_defined_task(name, "build", "build marker",
		core.build_agent.define_task({
			kind = "marker",
			task_id = task_id,
			agent_id = agent_id,
			owner = name,
			world_id = context.world_id or "ai_agent_plugin",
			origin = pos,
			get_node = context.get_node,
			set_node = context.set_node,
			max_node_writes_per_step = 1,
			persist_record = context.persist_record or context.persist_rollback_record,
			rollback_policy = context.rollback_policy,
			operation_label = "ai_agent_plugin.build",
		}), "builder")
end

local function build_plan_for(name, context)
	context = context or {}
	configure_product_surfaces()
	local agent_id = surface_agent_id_for(name, "builder")
	plugin.ensure_surface_agent(name, "builder")
	local result = core.build_agent.plan({
		kind = "marker",
		task_id = context.task_id,
		agent_id = agent_id,
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
	return result, plan
end

local function handle_build_plan(name, context)
	local result, plan = build_plan_for(name, context)
	return public_reply(name, "build_plan", result.status, "Build plan returned without mutation.", {
		surface_id = "builder",
		plan = plan,
		planned_node_writes = plan.metrics.planned_node_writes or 0,
	})
end

local function handle_build(name, context)
	context = context or {}
	local result, plan = build_plan_for(name, context)
	local pending = remember_pending_approval(name, "build", plan, context, {
		surface_id = "builder",
		planned_node_writes = plan.metrics.planned_node_writes or 0,
	})
	return public_reply(name, "build", "pending_approval",
		"Build plan is pending approval before mutation.", {
			surface_id = "builder",
			approval_id = pending.approval_id,
			pending_action = "build",
			plan = plan,
			planned_node_writes = plan.metrics.planned_node_writes or 0,
			plan_status = result.status,
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
	local agent_id = surface_agent_id_for(name, "repair")
	plugin.ensure_surface_agent(name, "repair")
	local plan = core.repair_agent.plan_area(default_pos(context), {
		agent_id = agent_id,
		owner = name,
		task_id = context.task_id,
		radius = 0,
		repair_nodes = settings.repair_nodes,
		get_node = context.get_node,
		sample_limit = context.sample_limit or settings.max_lights,
	})
	local compact = compact_repair_plan(plan)
	return public_reply(name, "repair_plan", plan.status, "Repair plan returned without mutation.", {
		surface_id = "repair",
		plan = compact,
		candidate_count = compact.candidate_count,
	})
end

local function queue_repair_task(name, context, plan)
	context = context or {}
	configure_product_surfaces()
	local pos = default_pos(context)
	local task_id = next_task_id(name, "repair")
	local agent_id = surface_agent_id_for(name, "repair")
	plugin.ensure_surface_agent(name, "repair")
	plan = plan or core.repair_agent.plan_area(pos, {
		agent_id = agent_id,
		owner = name,
		task_id = task_id .. ":plan",
		radius = 0,
		repair_nodes = settings.repair_nodes,
		get_node = context.get_node,
		sample_limit = context.sample_limit or settings.max_lights,
	})
	local task = core.repair_agent.queue_apply_task({
		task_id = task_id,
		agent_id = agent_id,
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
		surface_id = "repair",
		agent_id = agent_id,
		task_id = task.task_id,
		plan_status = plan.status,
		candidate_count = #(plan.candidates or {}),
	})
end

local function handle_repair(name, context)
	context = context or {}
	configure_product_surfaces()
	local approval_id = next_approval_id(name, "repair")
	local agent_id = surface_agent_id_for(name, "repair")
	plugin.ensure_surface_agent(name, "repair")
	local plan = core.repair_agent.plan_area(default_pos(context), {
		agent_id = agent_id,
		owner = name,
		task_id = approval_id .. ":plan",
		radius = 0,
		repair_nodes = settings.repair_nodes,
		get_node = context.get_node,
		sample_limit = context.sample_limit or settings.max_lights,
	})
	local compact = compact_repair_plan(plan)
	local pending = {
		approval_id = approval_id,
		surface_id = "repair",
		action = "repair",
		plan = compact,
		raw_plan = plan,
		context = approval_context(context),
		candidate_count = compact.candidate_count,
	}
	player_pending_approvals[name] = pending
	return public_reply(name, "repair", "pending_approval",
		"Repair plan is pending approval before mutation.", {
			surface_id = "repair",
			approval_id = pending.approval_id,
			pending_action = "repair",
			plan = compact,
			candidate_count = compact.candidate_count,
			plan_status = plan.status,
		})
end

local function default_import_plan(context)
	context = context or {}
	if context.import_plan then
		return context.import_plan
	end
	return {
		source = {
			source_id = context.source_id or "agent-import-dry-run",
			source_class = context.source_class or "unknown",
			inventory = {},
			content_hashes = {},
		},
		dry_run = true,
		planned_actions = {},
	}
end

local function handle_import_plan(name, context)
	context = context or {}
	context.max_node_writes_per_step = 0
	context.surface_id = "importer"
	local agent_id = surface_agent_id_for(name, "importer")
	plugin.ensure_surface_agent(name, "importer")
	return queue_plugin_task(name, "import_plan", "import dry-run plan", {
		function()
			return core.ai_import_ops.plan(default_import_plan(context), {
				agent_id = agent_id,
				owner = name,
				task_id = context.task_id,
			})
		end,
	}, context)
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
	local agent_ids = {
		[agent_id_for(name)] = true,
	}
	for _, surface_id in ipairs(PRODUCT_SURFACE_ORDER) do
		agent_ids[surface_agent_id_for(name, surface_id)] = true
	end
	local events = {}
	for _, record in ipairs(core.get_ai_runtime_audit({ limit = limit or 25 })) do
		if agent_ids[record.agent_id] then
			events[#events + 1] = compact_audit_record(record)
		end
	end
	return events
end

local function handle_guide(name)
	local surface_agents = plugin.ensure_product_agents(name)
	return public_reply(name, "guide", "success", "First-party agent guide returned.", {
		surface_id = "guide",
		surfaces = {
			builder = true,
			repair = true,
			guide = true,
			defender = true,
			importer = true,
		},
		product_surfaces = plugin.get_product_surfaces(name),
		surface_agents = {
			builder = {
				agent_id = surface_agents.builder.agent_id,
				capability_profile = surface_agents.builder.limits.capability_profile,
			},
			repair = {
				agent_id = surface_agents.repair.agent_id,
				capability_profile = surface_agents.repair.limits.capability_profile,
			},
			guide = {
				agent_id = surface_agents.guide.agent_id,
				capability_profile = surface_agents.guide.limits.capability_profile,
			},
			defender = {
				agent_id = surface_agents.defender.agent_id,
				capability_profile = surface_agents.defender.limits.capability_profile,
			},
			importer = {
				agent_id = surface_agents.importer.agent_id,
				capability_profile = surface_agents.importer.limits.capability_profile,
			},
		},
		commands = {
			"status",
			"tasks",
			"cancel",
			"approve",
			"follow",
			"light",
			"build plan",
			"build marker",
			"repair plan",
			"repair",
			"defend",
			"import plan",
			"audit",
			"rollback",
		},
		navigation_contract = plugin.get_navigation_contract(),
		tasks = active_player_tasks(name),
		pending_approval = compact_pending_approval(player_pending_approvals[name]),
	})
end

local function handle_audit(name)
	plugin.ensure_surface_agent(name, "guide")
	return public_reply(name, "audit", "success", "Recent agent audit events returned.", {
		surface_id = "guide",
		audit_events = audit_events_for(name, 50),
	})
end

local function handle_rollback_review(name)
	plugin.ensure_surface_agent(name, "guide")
	local records = {}
	for _, record in ipairs(audit_events_for(name, 100)) do
		if record.event_type == "rollback.record" and record.rollback_record_id then
			records[#records + 1] = record
		end
	end
	return public_reply(name, "rollback", "success", "Recent rollback records returned.", {
		surface_id = "guide",
		rollback_records = records,
	})
end

local function handle_defend(name, context)
	context = context or {}
	context.surface_id = "defender"
	local agent_id = surface_agent_id_for(name, "defender")
	plugin.ensure_surface_agent(name, "defender")
	return queue_plugin_task(name, "defend", "defend player", {
		function()
			return core.ai_player_ops.defend(name, {
				agent_id = agent_id,
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
	plugin.ensure_surface_agent(name, "guide")
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
			surface_id = "guide",
			cancelled = cancelled,
		})
end

local function handle_tasks(name)
	plugin.ensure_surface_agent(name, "guide")
	return public_reply(name, "tasks", "success", "Task list returned.", {
		surface_id = "guide",
		tasks = active_player_tasks(name),
		pending_approval = compact_pending_approval(player_pending_approvals[name]),
	})
end

local function handle_approve(name, prompt)
	local pending = player_pending_approvals[name]
	if not pending then
		return public_reply(name, "approve", "blocked", "No pending approval to apply.", {
			reason = "no_pending_approval",
		})
	end
	local requested_action = prompt:match("^approve%s+([%w_%-]+)$")
	if requested_action and requested_action ~= pending.action then
		return public_reply(name, "approve", "blocked",
			"Pending approval action does not match request.", {
				reason = "approval_action_mismatch",
				approval_id = pending.approval_id,
				pending_action = pending.action,
				requested_action = requested_action,
			})
	end

	player_pending_approvals[name] = nil
	local queued
	if pending.action == "build" then
		queued = queue_build_task(name, pending.context)
	elseif pending.action == "repair" then
		queued = queue_repair_task(name, pending.context, pending.raw_plan)
	else
		return public_reply(name, "approve", "blocked", "Pending approval type is unsupported.", {
			reason = "unsupported_pending_approval",
			approval_id = pending.approval_id,
			pending_action = pending.action,
		})
	end

	queued.action = "approve"
	queued.approved_action = pending.action
	queued.approval_id = pending.approval_id
	return queued
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
			navigation_contract = plugin.get_navigation_contract(),
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
	if prompt == "approve" or prompt:match("^approve%s+[%w_%-]+$") then
		return handle_approve(name, prompt)
	end
	if prompt:find("follow me", 1, true) or prompt == "follow"
			or prompt:match("^follow%s+%d+$") then
		return handle_follow(name, prompt, context)
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
	if prompt:find("import", 1, true)
			and (prompt:find("plan", 1, true) or prompt:find("preview", 1, true)
				or prompt:find("inventory", 1, true)) then
		return handle_import_plan(name, context)
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
