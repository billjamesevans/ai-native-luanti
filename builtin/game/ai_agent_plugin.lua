core.ai_agent_plugin = {}

local plugin = core.ai_agent_plugin
local player_states = {}
local player_task_ids = {}
local player_entity_ids = {}
local player_pending_approvals = {}
local task_sequence = 0
local approval_sequence = 0
local request_trace_sequence = 0
local request_traces = {}
local operator_feedback_sequence = 0
local operator_feedback_events = {}
local model_adapter = nil
local model_adapter_async = nil
local default_capabilities = {}
local settings = {
	capability_profile = nil,
	light_node = "default:torch",
	marker_node = "default:mese_post_light",
	platform_node = "default:stone",
	path_node = "default:stone",
	fire_node = "fire:basic_flame",
	wall_node = "default:stone",
	house_node = "default:stone",
	cabin_node = "default:wood",
	landmark_node = "default:stone",
	tnt_node = "tnt:tnt",
	build_material_nodes = {},
	agent_entity_name = "ai_demo_benchmark:helper",
	repair_nodes = {},
	max_lights = 12,
	max_request_traces = 50,
	max_operator_feedback_events = 50,
	max_entity_move_distance = 16,
	max_follow_steps = 6,
	max_follow_step_distance = 4,
	max_follow_total_distance = 24,
	max_follow_stop_distance = 1,
	max_follow_wall_time_ms = 250,
	max_navigation_nodes = 64,
	max_repair_radius = 2,
	max_defend_distance = 8,
	agentic_build_planner_first = false,
	auto_apply_build_approvals = false,
	max_player_loop_turns = 16,
	player_loop_auto_review_enabled = true,
	player_loop_review_interval = 1.0,
	natural_chat_enabled = true,
	natural_chat_aliases = { "nova", "bot", "aibot" },
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
		commands = {
			"build plan",
			"build marker",
			"build plan platform width N depth N",
			"build platform width N depth N",
			"build fire",
			"build wall width N height N",
			"build wall of tnt",
			"build <freeform request>",
			"approve build",
			"light",
		},
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
		commands = { "repair plan", "repair plan radius N", "repair radius N", "repair", "approve repair" },
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
		commands = {
			"status",
			"guide",
			"help",
			"commands",
			"last",
			"last command",
			"diagnostics",
			"tasks",
			"task <task_id>",
			"traces",
			"feedback last",
			"feedback fire",
			"feedback tnt wall",
			"wrong <expected build>",
			"teach <expected build>",
			"pending plan",
			"edit plan",
			"discard plan",
			"cancel plan",
			"cancel approval",
			"no",
			"cancel",
			"cancel <task_id>",
			"follow",
			"follow N",
			"come",
			"stay",
			"wait",
			"audit",
			"audit <task_id>",
			"rollback",
			"rollback <task_id|rollback_id>",
		},
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

local function bounded_trace_text(value, max_bytes)
	if value == nil then
		return nil
	end
	local text = tostring(value)
	max_bytes = max_bytes or 1000
	if #text <= max_bytes then
		return text
	end
	return text:sub(1, max_bytes) .. "...<truncated>"
end

local function trace_timestamp_us()
	return core.get_us_time and core.get_us_time() or 0
end

local function compact_trace_context(context)
	context = context or {}
	return {
		surface_id = context.surface_id,
		task_id = context.task_id,
		build_kind = context.build_kind,
		build_width = context.build_width,
		build_depth = context.build_depth,
		build_height = context.build_height,
		build_count = context.build_count,
		build_material_name = context.build_material_name,
		build_material_node = context.build_material_node,
		adapter_name = context.adapter_name,
		planner_mode = context.planner_mode,
		input_surface = context.input_surface,
		natural_chat_alias = context.natural_chat_alias,
		player_turn_source = context.player_turn_source,
		player_agent_loop = context.player_agent_loop,
		selected_candidate_id = context.selected_candidate_id,
		candidate_count = context.candidate_count,
	}
end

plugin._player_loop = {}
plugin._player_loop.task_reviews = {}

function plugin._player_loop.copy_observation(observation)
	if type(observation) ~= "table" then
		return nil
	end
	local copied = table.copy(observation)
	if observation.anchor_pos then
		copied.anchor_pos = copy_pos(observation.anchor_pos)
	end
	return copied
end

function plugin._player_loop.copy_task_review(review)
	if type(review) ~= "table" then
		return nil
	end
	return table.copy(review)
end

function plugin._player_loop.copy_turns(turns)
	if type(turns) ~= "table" then
		return {}
	end
	local copied = {}
	for index, turn in ipairs(turns) do
		if type(turn) == "table" then
			copied[index] = table.copy(turn)
		end
	end
	return copied
end

function plugin._player_loop.public_observation(observation)
	if type(observation) ~= "table" then
		return nil
	end
	return {
		action = observation.action,
		route = observation.route,
		surface_id = observation.surface_id,
		prompt = observation.prompt,
		world_id = observation.world_id,
		task_id = observation.task_id,
		agent_id = observation.agent_id,
		anchor_pos_available = observation.anchor_pos_available == true,
		anchor_node_name = observation.anchor_node_name,
	}
end

function plugin._player_loop.public_turns(turns)
	local copied = {}
	if type(turns) ~= "table" then
		return copied
	end
	local max_turns = settings.max_player_loop_turns or 8
	local start_index = math.max(1, #turns - max_turns + 1)
	for index = start_index, #turns do
		local turn = turns[index]
		if type(turn) == "table" then
			copied[#copied + 1] = {
				role = turn.role,
				text = bounded_trace_text(turn.text, 120),
				surface_id = turn.surface_id,
				source = turn.source,
			}
		end
	end
	return copied
end

function plugin._player_loop.public_snapshot(name)
	local state = plugin.get_player_state(name)
	local loop = type(state.loop) == "table" and state.loop or {}
	return {
		status = loop.status,
		phase = loop.phase,
		iteration = loop.iteration,
		active_goal = loop.active_goal,
		active_surface = loop.active_surface,
		next_action = loop.next_action,
		last_trace_id = loop.last_trace_id,
		last_task_id = loop.last_task_id,
		last_result_status = loop.last_result_status,
		last_task_review =
			plugin._player_loop.copy_task_review(loop.last_task_review),
		last_observation =
			plugin._player_loop.public_observation(loop.last_observation),
		recent_turns = plugin._player_loop.public_turns(loop.recent_turns),
		recent_turn_count = type(loop.recent_turns) == "table"
			and #loop.recent_turns or 0,
		privacy = {
			public_safe = true,
			family_world_coordinates = false,
			raw_player_payload = false,
		},
	}
end

function plugin._player_loop.public_context_json(name)
	if not core.write_json then
		return nil
	end
	local ok, encoded = pcall(core.write_json,
		plugin._player_loop.public_snapshot(name))
	if not ok or type(encoded) ~= "string" then
		return nil
	end
	return bounded_trace_text(encoded, 3200)
end

function plugin._player_loop.default_state()
	return {
		status = "idle",
		phase = "idle",
		iteration = 0,
		active_goal = nil,
		active_surface = nil,
		next_action = "wait_for_player_intent",
		last_observation = nil,
		last_task_review = nil,
		recent_turns = {},
		last_trace_id = nil,
		last_task_id = nil,
		last_result_status = nil,
		last_updated_us = nil,
	}
end

function plugin._player_loop.ensure_state(state)
	state.loop = type(state.loop) == "table" and state.loop
		or plugin._player_loop.default_state()
	local defaults = plugin._player_loop.default_state()
	for key, value in pairs(defaults) do
		if state.loop[key] == nil then
			state.loop[key] = value
		end
	end
	return state.loop
end

function plugin._player_loop.copy_state(state)
	local copied = table.copy(state or {})
	if type(state) == "table" and type(state.loop) == "table" then
		copied.loop = table.copy(state.loop)
		copied.loop.last_observation =
			plugin._player_loop.copy_observation(state.loop.last_observation)
		copied.loop.last_task_review =
			plugin._player_loop.copy_task_review(state.loop.last_task_review)
		copied.loop.recent_turns =
			plugin._player_loop.copy_turns(state.loop.recent_turns)
	end
	plugin._player_loop.ensure_state(copied)
	return copied
end

function plugin._player_loop.context_node_name(context)
	context = context or {}
	if not context.pos then
		return nil
	end
	local get_node = context.get_node
	if not get_node and context.use_core_perception then
		get_node = core.get_node
	end
	if type(get_node) ~= "function" then
		return nil
	end
	local ok, node = pcall(get_node, copy_pos(context.pos))
	if ok and type(node) == "table" then
		return node.name
	end
	return nil
end

function plugin._player_loop.compact_observation(context, extra)
	context = context or {}
	extra = extra or {}
	local observation = {
		observed_us = trace_timestamp_us(),
		action = extra.action,
		route = extra.route,
		surface_id = extra.surface_id or context.surface_id,
		prompt = bounded_trace_text(extra.prompt, 240),
		world_id = context.world_id,
		task_id = context.task_id,
		agent_id = extra.agent_id,
		anchor_pos_available = context.pos ~= nil,
		anchor_node_name = plugin._player_loop.context_node_name(context),
	}
	if context.pos then
		observation.anchor_pos = copy_pos(context.pos)
	end
	return observation
end

function plugin._player_loop.result_phase(result)
	local status = result and result.status
	if status == "pending_approval" then
		return "awaiting_player_approval", "wait_for_player_approval"
	end
	if status == "queued" then
		return "acting", "step_ai_task_queue"
	end
	if status == "blocked" then
		return "blocked", "ask_player_or_replan"
	end
	if status == "success" or status == "partial" then
		return "reviewing_result", "wait_for_player_intent"
	end
	return "idle", "wait_for_player_intent"
end

function plugin._player_loop.record(name, update)
	update = update or {}
	name = normalize_player_name(name)
	local current = plugin._player_loop.copy_state(player_states[name] or { mode = "idle" })
	local loop = plugin._player_loop.ensure_state(current)
	if update.increment_iteration then
		loop.iteration = (loop.iteration or 0) + 1
	end
	if update.status ~= nil then
		loop.status = update.status
	end
	if update.phase ~= nil then
		loop.phase = update.phase
	end
	if update.active_goal ~= nil then
		loop.active_goal = bounded_trace_text(update.active_goal, 240)
	end
	if update.active_surface ~= nil then
		loop.active_surface = update.active_surface
	end
	if update.next_action ~= nil then
		loop.next_action = update.next_action
	end
	if update.last_trace_id ~= nil then
		loop.last_trace_id = update.last_trace_id
	end
	if update.last_task_id ~= nil then
		loop.last_task_id = update.last_task_id
	end
	if update.last_result_status ~= nil then
		loop.last_result_status = update.last_result_status
	end
	if update.last_observation ~= nil then
		loop.last_observation = plugin._player_loop.copy_observation(update.last_observation)
	end
	if update.last_task_review ~= nil then
		loop.last_task_review =
			plugin._player_loop.copy_task_review(update.last_task_review)
	end
	loop.last_updated_us = trace_timestamp_us()
	player_states[name] = plugin._player_loop.copy_state(current)
	return plugin.get_player_state(name)
end

function plugin._player_loop.append_turn(name, role, text, surface_id, source)
	text = bounded_trace_text(text, 240)
	if text == nil or text == "" then
		return plugin.get_player_state(name)
	end
	name = normalize_player_name(name)
	local current = plugin._player_loop.copy_state(player_states[name] or { mode = "idle" })
	local loop = plugin._player_loop.ensure_state(current)
	loop.recent_turns = plugin._player_loop.copy_turns(loop.recent_turns)
	loop.recent_turns[#loop.recent_turns + 1] = {
		role = role or "user",
		text = text,
		surface_id = surface_id,
		source = source,
		turn_us = trace_timestamp_us(),
	}
	while #loop.recent_turns > (settings.max_player_loop_turns or 8) do
		table.remove(loop.recent_turns, 1)
	end
	loop.last_updated_us = trace_timestamp_us()
	player_states[name] = plugin._player_loop.copy_state(current)
	return plugin.get_player_state(name)
end

function plugin.record_player_loop(name, update)
	return plugin._player_loop.record(name, update)
end

local function compact_trace_entry(entry)
	local result = table.copy(entry or {})
	if entry and entry.request then
		result.request = table.copy(entry.request)
	end
	if entry and entry.response then
		result.response = table.copy(entry.response)
	end
	if entry and entry.context then
		result.context = table.copy(entry.context)
	end
	return result
end

local function log_request_trace(trace, event)
	if not trace or not core.write_json or not core.log then
		return
	end
	local ok, encoded = pcall(core.write_json, {
		schema_version = 1,
		event_kind = "nova_request_trace",
		event = event or "completed",
		trace = compact_trace_entry(trace),
	})
	if ok and encoded then
		core.log("action", "[ai_agent_plugin] request_trace="
			.. bounded_trace_text(encoded, 4000))
	end
end

local function log_operator_feedback_event(event)
	if not event or not core.write_json or not core.log then
		return
	end
	local ok, encoded = pcall(core.write_json, event)
	if ok and encoded then
		core.log("action", "[ai_agent_plugin] operator_feedback="
			.. bounded_trace_text(encoded, 4000))
	end
end

local function remember_request_trace(entry)
	entry = entry or {}
	request_trace_sequence = request_trace_sequence + 1
	entry.trace_id = entry.trace_id or ("nova_trace:" .. request_trace_sequence)
	entry.trace_kind = entry.trace_kind or "agent_request"
	entry.created_us = entry.created_us or trace_timestamp_us()
	request_traces[#request_traces + 1] = entry
	local max_traces = math.max(1, settings.max_request_traces or 50)
	while #request_traces > max_traces do
		table.remove(request_traces, 1)
	end
	return entry
end

local function start_request_trace(name, action, route, prompt, context, extra)
	extra = extra or {}
	local surface_id = extra.surface_id or (context and context.surface_id)
	if extra.record_player_turn ~= false then
		local player_turn_text = extra.player_turn_text
		if player_turn_text == nil and context then
			player_turn_text = context.player_turn_text
		end
		local player_turn_source = extra.player_turn_source
		if player_turn_source == nil and context then
			player_turn_source = context.player_turn_source
		end
		plugin._player_loop.append_turn(name, "user",
			player_turn_text or prompt, surface_id,
			player_turn_source or route)
	end
	local trace = remember_request_trace({
		owner = name,
		agent_id = extra.agent_id or agent_id_for(name),
		action = action,
		route = route,
		public_prompt = bounded_trace_text(prompt, 1000),
		context = compact_trace_context(context),
		request = {
			action = action,
			route = route,
			surface_id = extra.surface_id or (context and context.surface_id),
			adapter_name = extra.adapter_name,
		},
	})
	plugin._player_loop.record(name, {
		status = "running",
		phase = "observing",
		active_goal = prompt,
		active_surface = surface_id,
		next_action = "reason_with_tools",
		last_trace_id = trace.trace_id,
		increment_iteration = true,
		last_observation = plugin._player_loop.compact_observation(
			extra.observation_context or context, {
			action = action,
			route = route,
			surface_id = surface_id,
			prompt = prompt,
			agent_id = trace.agent_id,
		}),
	})
	return trace
end

local function finish_request_trace(trace, result, extra)
	if not trace then
		return result
	end
	extra = extra or {}
	if result and result.trace_id == nil then
		result.trace_id = trace.trace_id
	end
	trace.completed_us = trace_timestamp_us()
	trace.response = {
		ok = result and result.ok or false,
		status = result and result.status,
		action = result and result.action,
		reason = result and result.reason,
		message = bounded_trace_text(result and result.message, 1000),
		approval_id = result and result.approval_id,
		task_id = result and result.task_id,
		approved_action = result and result.approved_action,
		auto_applied_approval = result and result.auto_applied_approval,
		auto_apply_policy = result and result.auto_apply_policy,
		build_kind = result and result.build_kind,
		build_width = result and result.build_width,
		build_depth = result and result.build_depth,
		build_height = result and result.build_height,
		build_material_name = result and result.build_material_name,
		build_material_node = result and result.build_material_node,
		planned_node_writes = result and result.planned_node_writes,
		planner_mode = result and result.planner_mode,
		selected_candidate_id = result and result.selected_candidate_id,
		adapter_selected_candidate_id =
			result and result.adapter_selected_candidate_id,
		model_selected_candidate_id =
			result and result.model_selected_candidate_id,
		selection_source = result and result.selection_source,
		intent_constraint_option_id =
			result and result.intent_constraint_option_id,
		intent_constraint_reason =
			result and result.intent_constraint_reason,
		candidate_count = result and result.candidate_count,
		adapter_tool_decision_source = result and result.adapter_tool_decision_source,
		adapter_model_selected_candidate_id =
			result and result.adapter_model_selected_candidate_id,
		adapter_initial_model_selected_candidate_id =
			result and result.adapter_initial_model_selected_candidate_id,
		adapter_rejected_model_selected_candidate_id =
			result and result.adapter_rejected_model_selected_candidate_id,
		adapter_agent_repair_attempted =
			result and result.adapter_agent_repair_attempted,
		adapter_agent_repair_succeeded =
			result and result.adapter_agent_repair_succeeded,
		adapter_agent_repair_reason =
			result and result.adapter_agent_repair_reason,
		adapter_initial_missing_required_tool_calls =
			result and result.adapter_initial_missing_required_tool_calls,
		adapter_required_tool_calls = result and result.adapter_required_tool_calls,
		adapter_missing_required_tool_calls =
			result and result.adapter_missing_required_tool_calls,
		adapter_required_tool_calls_satisfied =
			result and result.adapter_required_tool_calls_satisfied,
		build_option_decision_source = result and result.build_option_decision_source,
		adapter_memory_available = result and result.adapter_memory_available,
		adapter_memory_matched_case_id =
			result and result.adapter_memory_matched_case_id,
		adapter_memory_case_hint = result and result.adapter_memory_case_hint,
		adapter_tool_trace_names = result and result.adapter_tool_trace_names,
		adapter_build_action_plan_status =
			result and result.adapter_build_action_plan_status,
		adapter_build_action_plan_selected_candidate_id =
			result and result.adapter_build_action_plan_selected_candidate_id,
		adapter_build_action_plan_step_count =
			result and result.adapter_build_action_plan_step_count,
		adapter_build_action_plan_world_mutation_authority =
			result and result.adapter_build_action_plan_world_mutation_authority,
		generated_build_option_status = result and result.generated_build_option_status,
		generated_build_option_reason = result and result.generated_build_option_reason,
		generated_candidate_id = result and result.generated_candidate_id,
		planner_model_status = result and result.planner_model_status,
		planner_model_reason = result and result.planner_model_reason,
		agentic_tool_success_required =
			result and result.agentic_tool_success_required,
		agentic_planner_fallback_blocked =
			result and result.agentic_planner_fallback_blocked,
		fallback_blocked_reason = result and result.fallback_blocked_reason,
		}
	for key, value in pairs(extra) do
		trace[key] = value
	end
	local phase, next_action = plugin._player_loop.result_phase(result)
	plugin._player_loop.record(trace.owner, {
		status = result and result.status or "unknown",
		phase = phase,
		active_goal = trace.public_prompt,
		active_surface = (result and result.surface_id)
			or (trace.request and trace.request.surface_id),
		next_action = next_action,
		last_trace_id = trace.trace_id,
		last_task_id = result and result.task_id,
		last_result_status = result and result.status,
	})
	log_request_trace(trace, "completed")
	return result
end

function plugin.get_request_traces(options)
	options = options or {}
	local limit = options.limit or #request_traces
	limit = math.max(0, math.min(limit, #request_traces))
	local result = {}
	local start_index = #request_traces - limit + 1
	for index = start_index, #request_traces do
		result[#result + 1] = compact_trace_entry(request_traces[index])
	end
	return result
end

function plugin.player_request_traces(name, options)
	name = normalize_player_name(name)
	options = options or {}
	local limit = options.limit or (settings.max_request_traces or 50)
	limit = math.max(0, limit)
	local traces = plugin.get_request_traces({
		limit = settings.max_request_traces or 50,
	})
	local result = {}
	for index = #traces, 1, -1 do
		local trace = traces[index]
		if trace.owner == name then
			table.insert(result, 1, trace)
			if #result >= limit then
				break
			end
		end
	end
	return result
end

function plugin.get_model_traces(options)
	return plugin.get_request_traces(options)
end

function plugin.get_operator_feedback(options)
	options = options or {}
	local limit = options.limit or #operator_feedback_events
	limit = math.max(0, math.min(limit, #operator_feedback_events))
	local result = {}
	local start_index = #operator_feedback_events - limit + 1
	for index = start_index, #operator_feedback_events do
		result[#result + 1] = table.copy(operator_feedback_events[index])
	end
	return result
end

local function configure_product_surfaces()
	if core.build_agent then
		core.build_agent.configure({
			light_node = settings.light_node,
			marker_node = settings.marker_node,
			platform_node = settings.platform_node,
			path_node = settings.path_node,
			fire_node = settings.fire_node,
			wall_node = settings.wall_node,
			house_node = settings.house_node,
			cabin_node = settings.cabin_node,
			landmark_node = settings.landmark_node,
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

local function surface_gated_reply(name, surface_id, action)
	local surface = product_surface(surface_id)
	plugin.ensure_surface_agent(name, surface_id)
	return public_reply(name, action, "blocked",
		surface.display_name .. " is not enabled for this capability profile.", {
			surface_id = surface_id,
			reason = "surface_capability_not_granted",
			required_capabilities = table.copy(surface.required_capabilities or {}),
			granted_capabilities = granted_capability_list_for(surface),
			required_capabilities_granted = false,
			default_clean_profile_grant = surface.default_clean_profile_grant,
		})
end

local function append(list, value)
	list[#list + 1] = value
end

local function task_summary(task)
	if type(task) ~= "table" then
		return nil
	end
	local summary = tostring(task.task_id or "unknown") .. "="
		.. tostring(task.status or "unknown")
	if task.label then
		summary = summary .. " (" .. tostring(task.label) .. ")"
	end
	return summary
end

local function surface_summary(surface)
	if type(surface) ~= "table" then
		return nil
	end
	local grant = surface.required_capabilities_granted and "ready" or "gated"
	return tostring(surface.surface_id or "unknown") .. "=" .. grant
end

local function pending_approval_summary(pending)
	if type(pending) ~= "table" then
		return nil
	end
	local parts = {
		"pending=" .. tostring(pending.pending_action or "unknown"),
		"approval_id=" .. tostring(pending.approval_id or "unknown"),
	}
	if pending.candidate_count then
		append(parts, "candidates=" .. tostring(pending.candidate_count))
	end
	if pending.planned_node_writes then
		append(parts, "planned_writes=" .. tostring(pending.planned_node_writes))
	end
	if pending.build_kind then
		append(parts, "build_kind=" .. tostring(pending.build_kind))
	end
	if pending.build_material_node then
		append(parts, "material=" .. tostring(pending.build_material_node))
	end
	if pending.selected_candidate_id then
		append(parts, "selected_candidate=" .. tostring(pending.selected_candidate_id))
	end
	if pending.adapter_tool_decision_source then
		append(parts, "tool_decision_source=" .. tostring(pending.adapter_tool_decision_source))
	end
	if pending.adapter_required_tool_calls_satisfied ~= nil then
		append(parts, "required_tools_satisfied="
			.. tostring(pending.adapter_required_tool_calls_satisfied))
	end
	if pending.adapter_memory_matched_case_id then
		append(parts, "memory_match=" .. tostring(pending.adapter_memory_matched_case_id))
	end
	return table.concat(parts, " ")
end

function plugin._build_option_summary(option)
	if type(option) ~= "table" then
		return nil
	end
	local parts = {
		"option=" .. tostring(option.option_id or "unknown"),
	}
	if option.build_kind then
		append(parts, "kind=" .. tostring(option.build_kind))
	end
	if option.build_material_name then
		append(parts, "material=" .. tostring(option.build_material_name))
	elseif option.build_material_node then
		append(parts, "material=" .. tostring(option.build_material_node))
	end
	if option.planned_node_writes then
		append(parts, "writes=" .. tostring(option.planned_node_writes))
	end
	if option.reason then
		append(parts, "reason=" .. bounded_trace_text(option.reason, 80))
	end
	return table.concat(parts, " ")
end

local function append_build_material_details(lines, result)
	if result.build_height then
		append(lines, "height=" .. tostring(result.build_height))
	end
	if result.build_material_name then
		append(lines, "material_name=" .. tostring(result.build_material_name))
	end
	if result.build_material_node then
		append(lines, "material=" .. tostring(result.build_material_node))
	end
end

local function join_limited(values, limit)
	local parts = {}
	limit = limit or #values
	for index, value in ipairs(values or {}) do
		if index > limit then
			append(parts, "...")
			break
		end
		append(parts, tostring(value))
	end
	return table.concat(parts, ", ")
end

local function append_task_details(lines, result)
	if result.task_id then
		append(lines, "task_id=" .. tostring(result.task_id))
	end
	if result.task_status then
		append(lines, "task_status=" .. tostring(result.task_status))
	end
	if result.before_status then
		append(lines, "before_status=" .. tostring(result.before_status))
	end
	if result.after_status then
		append(lines, "after_status=" .. tostring(result.after_status))
	end
	if result.surface_id then
		append(lines, "surface=" .. tostring(result.surface_id))
	end
	if result.approval_id then
		append(lines, "approval_id=" .. tostring(result.approval_id))
	end
	if result.approved_action then
		append(lines, "approved_action=" .. tostring(result.approved_action))
	end
	if result.reason then
		append(lines, "reason=" .. tostring(result.reason))
	end
	if result.planner_mode then
		append(lines, "planner_mode=" .. tostring(result.planner_mode))
	end
	if result.selected_candidate_id then
		append(lines, "selected_candidate=" .. tostring(result.selected_candidate_id))
	end
	if result.adapter_tool_decision_source then
		append(lines, "tool_decision_source=" .. tostring(result.adapter_tool_decision_source))
	end
	if result.adapter_required_tool_calls_satisfied ~= nil then
		append(lines, "required_tools_satisfied="
			.. tostring(result.adapter_required_tool_calls_satisfied))
	end
	if result.adapter_memory_matched_case_id then
		append(lines, "memory_match=" .. tostring(result.adapter_memory_matched_case_id))
	end
	if type(result.required_capabilities) == "table" then
		append(lines, "required_capabilities="
			.. join_limited(result.required_capabilities, 8))
	end
	if result.required_capabilities_granted ~= nil then
		append(lines, "required_capabilities_granted="
			.. tostring(result.required_capabilities_granted))
	end
	if result.default_clean_profile_grant then
		append(lines, "default_clean_profile_grant="
			.. tostring(result.default_clean_profile_grant))
	end
end

local function format_command_reply(result)
	result = result or {}
	local lines = {
		tostring(result.message or "AI agent command completed."),
		"status=" .. tostring(result.status or "unknown")
			.. " action=" .. tostring(result.action or "unknown"),
	}
	if result.action == "guide" then
		local surfaces = {}
		for _, surface in ipairs(result.product_surfaces or {}) do
			local summary = surface_summary(surface)
			if summary then
				append(surfaces, summary)
			end
		end
		if #surfaces > 0 then
			append(lines, "surfaces=" .. join_limited(surfaces, 8))
		end
		if type(result.commands) == "table" then
			append(lines, "commands=" .. join_limited(result.commands, 64))
		end
		local pending = pending_approval_summary(result.pending_approval)
		if pending then
			append(lines, pending)
		end
	elseif result.action == "tasks" then
		local tasks = {}
		for _, task in ipairs(result.tasks or {}) do
			local summary = task_summary(task)
			if summary then
				append(tasks, summary)
			end
		end
		append(lines, "tasks=" .. (#tasks > 0 and join_limited(tasks, 8) or "none"))
		local pending = pending_approval_summary(result.pending_approval)
		if pending then
			append(lines, pending)
		end
	elseif result.action == "last_command" then
		append_task_details(lines, result)
		if result.prompt then
			append(lines, "prompt=" .. tostring(result.prompt))
		end
		if result.route then
			append(lines, "route=" .. tostring(result.route))
		end
		if result.planner_mode then
			append(lines, "planner_mode=" .. tostring(result.planner_mode))
		end
		if result.selected_candidate_id then
			append(lines, "selected_candidate=" .. tostring(result.selected_candidate_id))
		end
		if result.model_selected_candidate_id then
			append(lines, "model_selected_candidate="
				.. tostring(result.model_selected_candidate_id))
		end
		if result.adapter_selected_candidate_id then
			append(lines, "adapter_selected_candidate="
				.. tostring(result.adapter_selected_candidate_id))
		end
		if result.selection_source then
			append(lines, "selection_source=" .. tostring(result.selection_source))
		end
		if result.intent_constraint_option_id then
			append(lines, "intent_constraint="
				.. tostring(result.intent_constraint_option_id))
		end
		if result.intent_constraint_reason then
			append(lines, "intent_constraint_reason="
				.. tostring(result.intent_constraint_reason))
		end
		if result.build_kind then
			append(lines, "build_kind=" .. tostring(result.build_kind))
		end
		if result.build_width then
			append(lines, "width=" .. tostring(result.build_width))
		end
		if result.build_depth then
			append(lines, "depth=" .. tostring(result.build_depth))
		end
		append_build_material_details(lines, result)
		if result.planned_node_writes then
			append(lines, "planned_writes=" .. tostring(result.planned_node_writes))
		end
		if result.actual_node_writes ~= nil then
			append(lines, "actual_writes=" .. tostring(result.actual_node_writes))
		end
		if result.task_result_status then
			append(lines, "task_result_status=" .. tostring(result.task_result_status))
		end
		if result.task_result_reason then
			append(lines, "task_result_reason=" .. tostring(result.task_result_reason))
		end
		if result.rollback_record_id then
			append(lines, "rollback_record=" .. tostring(result.rollback_record_id))
		end
		if type(result.adapter_tool_trace_names) == "table"
				and #result.adapter_tool_trace_names > 0 then
			append(lines, "tools=" .. join_limited(result.adapter_tool_trace_names, 8))
		end
		if result.adapter_tool_decision_source then
			append(lines, "tool_decision_source="
				.. tostring(result.adapter_tool_decision_source))
		end
		if result.adapter_required_tool_calls_satisfied ~= nil then
			append(lines, "required_tools_satisfied="
				.. tostring(result.adapter_required_tool_calls_satisfied))
		end
		local review = result.eval_review or {}
		if review.request_trace_logged ~= nil then
			append(lines, "review=source=" .. tostring(review.source_kind or "unknown")
				.. " prompt_eval="
				.. tostring(review.ready_for_prompt_eval and "ready" or "not_ready")
				.. " adapter_contract="
				.. tostring(review.ready_for_adapter_contract_eval and "ready" or "not_needed")
				.. " memory_refresh="
				.. tostring(review.memory_refresh_required and "required" or "not_required"))
		end
	elseif result.action == "task_status" then
		append_task_details(lines, result)
		if result.task_label then
			append(lines, "task_label=" .. tostring(result.task_label))
		end
		if result.build_kind then
			append(lines, "build_kind=" .. tostring(result.build_kind))
		end
		if result.build_width then
			append(lines, "width=" .. tostring(result.build_width))
		end
		if result.build_depth then
			append(lines, "depth=" .. tostring(result.build_depth))
		end
		append_build_material_details(lines, result)
		if result.last_result_status then
			append(lines, "last_result_status=" .. tostring(result.last_result_status))
		end
		if result.last_result_reason then
			append(lines, "last_result_reason=" .. tostring(result.last_result_reason))
		end
	elseif result.action == "pending_plan" then
		append_task_details(lines, result)
		local pending = pending_approval_summary(result.pending_approval)
		append(lines, pending or "pending=none")
		if result.plan_status then
			append(lines, "plan_status=" .. tostring(result.plan_status))
		end
	elseif result.action == "build_options" then
		append_task_details(lines, result)
		local pending = pending_approval_summary(result.pending_approval)
		append(lines, pending or "pending=none")
		if result.selected_candidate_id then
			append(lines, "selected_candidate=" .. tostring(result.selected_candidate_id))
		end
		for _, option in ipairs(result.candidate_options or {}) do
			local summary = plugin._build_option_summary(option)
			if summary then
				append(lines, summary)
			end
		end
	elseif result.action == "edit_plan" then
		append_task_details(lines, result)
		local pending = pending_approval_summary(result.pending_approval)
		append(lines, pending or "pending=none")
		if result.build_kind then
			append(lines, "build_kind=" .. tostring(result.build_kind))
		end
		if result.build_width then
			append(lines, "width=" .. tostring(result.build_width))
		end
		if result.build_depth then
			append(lines, "depth=" .. tostring(result.build_depth))
		end
		append_build_material_details(lines, result)
		if result.repair_radius then
			append(lines, "radius=" .. tostring(result.repair_radius))
		end
		if result.sample_limit then
			append(lines, "sample_limit=" .. tostring(result.sample_limit))
		end
		if result.planned_node_writes then
			append(lines, "planned_writes=" .. tostring(result.planned_node_writes))
		end
		if result.candidate_count then
			append(lines, "candidates=" .. tostring(result.candidate_count))
		end
		if result.plan_status then
			append(lines, "plan_status=" .. tostring(result.plan_status))
		end
	elseif result.action == "discard_approval" then
		append_task_details(lines, result)
		if result.discarded_action then
			append(lines, "discarded_action=" .. tostring(result.discarded_action))
		end
		if result.planned_node_writes then
			append(lines, "planned_writes=" .. tostring(result.planned_node_writes))
		end
		if result.candidate_count then
			append(lines, "candidates=" .. tostring(result.candidate_count))
		end
	elseif result.action == "status" then
		local state = result.state or {}
		append(lines, "mode=" .. tostring(state.mode or "unknown"))
		local loop = state.loop or {}
		append(lines, "loop=" .. tostring(loop.status or "unknown")
			.. ":" .. tostring(loop.phase or "unknown"))
		if loop.active_goal then
			append(lines, "goal=" .. bounded_trace_text(loop.active_goal, 80))
		end
		if loop.active_surface then
			append(lines, "surface=" .. tostring(loop.active_surface))
		end
		if loop.next_action then
			append(lines, "next_action=" .. tostring(loop.next_action))
		end
		if loop.last_trace_id then
			append(lines, "last_trace_id=" .. tostring(loop.last_trace_id))
		end
		if loop.last_task_id then
			append(lines, "last_task_id=" .. tostring(loop.last_task_id))
		end
		if loop.last_observation and loop.last_observation.anchor_node_name then
			append(lines, "observed_node="
				.. tostring(loop.last_observation.anchor_node_name))
		end
		local metrics = result.metrics or {}
		append(lines, "queue=" .. tostring(metrics.active_tasks or 0)
			.. " queued=" .. tostring(metrics.tasks_queued or 0)
			.. " completed=" .. tostring(metrics.tasks_completed or 0)
			.. " cancelled=" .. tostring(metrics.tasks_cancelled or 0))
		local surfaces = {}
		for _, surface in ipairs(result.product_surfaces or {}) do
			local summary = surface_summary(surface)
			if summary then
				append(surfaces, summary)
			end
		end
		if #surfaces > 0 then
			append(lines, "surfaces=" .. join_limited(surfaces, 8))
		end
		local tasks = {}
		for _, task in ipairs(result.tasks or {}) do
			local summary = task_summary(task)
			if summary then
				append(tasks, summary)
			end
		end
		append(lines, "known_tasks=" .. tostring(result.known_task_count or #tasks))
		append(lines, "tasks=" .. (#tasks > 0 and join_limited(tasks, 8) or "none"))
		local pending = pending_approval_summary(result.pending_approval)
		if pending then
			append(lines, pending)
		end
	elseif result.action == "build_plan" or result.action == "repair_plan" then
		append_task_details(lines, result)
		append(lines, "surface=" .. tostring(result.surface_id or "unknown"))
		if result.build_kind then
			append(lines, "build_kind=" .. tostring(result.build_kind))
		end
		if result.build_width then
			append(lines, "width=" .. tostring(result.build_width))
		end
		if result.build_depth then
			append(lines, "depth=" .. tostring(result.build_depth))
		end
		append_build_material_details(lines, result)
		if result.repair_radius then
			append(lines, "radius=" .. tostring(result.repair_radius))
		end
		if result.sample_limit then
			append(lines, "sample_limit=" .. tostring(result.sample_limit))
		end
		if result.planned_node_writes then
			append(lines, "planned_writes=" .. tostring(result.planned_node_writes))
		end
		if result.candidate_count then
			append(lines, "candidates=" .. tostring(result.candidate_count))
		end
	elseif result.status == "pending_approval" then
		append_task_details(lines, result)
		if result.pending_action then
			append(lines, "pending_action=" .. tostring(result.pending_action))
		end
		if result.build_kind then
			append(lines, "build_kind=" .. tostring(result.build_kind))
		end
		if result.build_width then
			append(lines, "width=" .. tostring(result.build_width))
		end
		if result.build_depth then
			append(lines, "depth=" .. tostring(result.build_depth))
		end
		append_build_material_details(lines, result)
		if result.repair_radius then
			append(lines, "radius=" .. tostring(result.repair_radius))
		end
		if result.sample_limit then
			append(lines, "sample_limit=" .. tostring(result.sample_limit))
		end
		if result.planned_node_writes then
			append(lines, "planned_writes=" .. tostring(result.planned_node_writes))
		end
		if result.candidate_count then
			append(lines, "candidates=" .. tostring(result.candidate_count))
		end
	elseif result.action == "audit" then
		if result.target_kind then
			append(lines, "target_kind=" .. tostring(result.target_kind))
		end
		if result.target_id then
			append(lines, "target_id=" .. tostring(result.target_id))
		end
		append(lines, "audit_events=" .. tostring(#(result.audit_events or {})))
		local summaries = {}
		for _, record in ipairs(result.audit_events or {}) do
			append(summaries, tostring(record.event_type or "event") .. ":"
				.. tostring(record.status or "unknown"))
		end
		if #summaries > 0 then
			append(lines, "recent=" .. join_limited(summaries, 5))
		end
	elseif result.action == "request_traces" then
		append(lines, "traces=" .. tostring(#(result.traces or {})))
		if result.trace_scope then
			append(lines, "scope=" .. tostring(result.trace_scope))
		end
		local summaries = {}
		for _, trace in ipairs(result.traces or {}) do
			local response = trace.response or {}
			append(summaries, tostring(trace.action or "request") .. ":"
				.. tostring(trace.route or "unknown") .. ":"
				.. tostring(response.status or "unknown"))
		end
		if #summaries > 0 then
			append(lines, "recent=" .. join_limited(summaries, 5))
		end
		local latest = result.latest_diagnostic
		if type(latest) == "table" then
			if latest.prompt then
				append(lines, "latest_prompt=" .. tostring(latest.prompt))
			end
			if latest.route then
				append(lines, "latest_route=" .. tostring(latest.route))
			end
			if latest.response_status then
				append(lines, "latest_status=" .. tostring(latest.response_status))
			end
			if latest.selected_candidate_id then
				append(lines, "latest_selected_candidate="
					.. tostring(latest.selected_candidate_id))
			end
			if latest.model_selected_candidate_id then
				append(lines, "latest_model_selected_candidate="
					.. tostring(latest.model_selected_candidate_id))
			end
			if latest.selection_source then
				append(lines, "latest_selection_source="
					.. tostring(latest.selection_source))
			end
			if latest.build_kind then
				append(lines, "latest_build_kind=" .. tostring(latest.build_kind))
			end
			if latest.build_material_node then
				append(lines, "latest_material="
					.. tostring(latest.build_material_node))
			end
			if latest.planned_node_writes then
				append(lines, "latest_planned_writes="
					.. tostring(latest.planned_node_writes))
			end
			if latest.actual_node_writes ~= nil then
				append(lines, "latest_actual_writes="
					.. tostring(latest.actual_node_writes))
			end
			if type(latest.adapter_tool_trace_names) == "table"
					and #latest.adapter_tool_trace_names > 0 then
				append(lines, "latest_tools="
					.. join_limited(latest.adapter_tool_trace_names, 8))
			end
			local review = latest.eval_review or {}
			if review.request_trace_logged ~= nil then
				append(lines, "latest_review=prompt_eval="
					.. tostring(review.ready_for_prompt_eval and "ready" or "not_ready")
					.. " adapter_contract="
					.. tostring(review.ready_for_adapter_contract_eval
						and "ready" or "not_needed")
					.. " memory_refresh="
					.. tostring(review.memory_refresh_required
						and "required" or "not_required"))
			end
		end
	elseif result.action == "rollback" then
		if result.target_kind then
			append(lines, "target_kind=" .. tostring(result.target_kind))
		end
		if result.target_id then
			append(lines, "target_id=" .. tostring(result.target_id))
		end
		append(lines, "rollback_records=" .. tostring(#(result.rollback_records or {})))
		if result.no_rollback_execution then
			append(lines, "no_rollback_execution=true")
		end
		local summaries = {}
		for _, record in ipairs(result.rollback_records or {}) do
			append(summaries, tostring(record.rollback_record_id or "rollback"))
		end
		if #summaries > 0 then
			append(lines, "recent=" .. join_limited(summaries, 5))
		end
	elseif result.action == "cancel" then
		append_task_details(lines, result)
		append(lines, "cancelled=" .. tostring(result.cancelled or 0))
	elseif result.action == "stay" then
		append_task_details(lines, result)
		local state = result.state or {}
		append(lines, "mode=" .. tostring(state.mode or "unknown"))
		if state.entity_id then
			append(lines, "entity_id=" .. tostring(state.entity_id))
		end
		append(lines, "cancelled=" .. tostring(result.cancelled or 0))
	else
		append_task_details(lines, result)
		if result.candidate_count then
			append(lines, "candidates=" .. tostring(result.candidate_count))
		end
	end
	if result.trace_id then
		append(lines, "trace_id=" .. tostring(result.trace_id))
	end
	if result.adapter_name then
		append(lines, "adapter=" .. tostring(result.adapter_name))
	end
	if result.agent_id then
		append(lines, "agent_id=" .. tostring(result.agent_id))
	end
	return table.concat(lines, "\n")
end

plugin.format_reply = format_command_reply

function plugin.format_player_reply(result)
	result = result or {}
	local trace_suffix = result.trace_id and (" trace=" .. tostring(result.trace_id)) or ""
	if result.action == "status" then
		local state = result.state or {}
		local loop = state.loop or {}
		return "I am " .. tostring(loop.status or state.mode or "idle")
			.. " and my next step is "
			.. tostring(loop.next_action or "wait_for_player_intent") .. "."
	end
	if result.action == "request_traces" then
		local latest = result.latest_diagnostic
		if type(latest) == "table" then
			local parts = {
				"I found " .. tostring(#(result.traces or {}))
					.. " of your recent Nova traces.",
				"Latest: " .. tostring(latest.prompt or "unknown request"),
			}
			if latest.selected_candidate_id then
				append(parts, "selected="
					.. tostring(latest.selected_candidate_id))
			end
			if latest.model_selected_candidate_id
					and latest.model_selected_candidate_id ~= latest.selected_candidate_id then
				append(parts, "model_selected="
					.. tostring(latest.model_selected_candidate_id))
			end
			if latest.actual_node_writes ~= nil then
				append(parts, "writes=" .. tostring(latest.actual_node_writes))
			elseif latest.planned_node_writes ~= nil then
				append(parts, "planned_writes="
					.. tostring(latest.planned_node_writes))
			end
			return table.concat(parts, " ")
		end
		return "I found " .. tostring(#(result.traces or {}))
			.. " of your recent Nova traces."
	end
	if result.action == "last_command" then
		local parts = {
			"Last thing I did: "
				.. tostring(result.prompt or result.action or "unknown request") .. ".",
		}
		if result.selected_candidate_id then
			append(parts, "selected=" .. tostring(result.selected_candidate_id))
		end
		if result.model_selected_candidate_id
				and result.model_selected_candidate_id ~= result.selected_candidate_id then
			append(parts, "model_selected="
				.. tostring(result.model_selected_candidate_id))
		end
		if result.actual_node_writes ~= nil then
			append(parts, "writes=" .. tostring(result.actual_node_writes))
		elseif result.planned_node_writes ~= nil then
			append(parts, "planned_writes="
				.. tostring(result.planned_node_writes))
		end
		if result.task_result_status then
			append(parts, "task=" .. tostring(result.task_result_status))
		end
		return table.concat(parts, " ")
	end
	if result.action == "build_options" then
		local count = result.candidate_count or #(result.candidate_options or {})
		local parts = {
			"I have " .. tostring(count) .. " build options",
		}
		if result.selected_candidate_id then
			append(parts, "selected " .. tostring(result.selected_candidate_id) .. ".")
		else
			append(parts, "for the pending plan.")
		end
		local option_text = {}
		for _, option in ipairs(result.candidate_options or {}) do
			local summary = plugin._build_option_summary(option)
			if summary then
				append(option_text, summary)
			end
			if #option_text >= 3 then
				break
			end
		end
		if #option_text > 0 then
			append(parts, table.concat(option_text, " | "))
		end
		return table.concat(parts, " ")
	end
	if result.status == "pending_approval" then
		local build_kind = result.build_kind and tostring(result.build_kind) or "that"
		local writes = result.planned_node_writes
			and (" with " .. tostring(result.planned_node_writes) .. " node writes")
			or ""
		return "I planned " .. build_kind .. writes
			.. ". Say `Nova, approve` to run it or `Nova, no` to discard it."
			.. trace_suffix
	end
	if result.status == "queued" then
		if result.action == "build_plan" then
			return "I am planning that with the agent tools." .. trace_suffix
		end
		if result.action == "approve" then
			return "I queued the approved "
				.. tostring(result.approved_action or "task") .. "."
				.. (result.task_id and (" task=" .. tostring(result.task_id)) or "")
		end
		return "I queued " .. tostring(result.action or "that") .. "."
			.. (result.task_id and (" task=" .. tostring(result.task_id)) or trace_suffix)
	end
	if result.status == "blocked" then
		local reason = result.reason and (" Reason: " .. tostring(result.reason) .. ".")
			or ""
		return "I could not complete that." .. reason
			.. (result.message and (" " .. tostring(result.message)) or "")
			.. trace_suffix
	end
	if result.status == "success" or result.status == "partial" then
		return tostring(result.message or "Done.") .. trace_suffix
	end
	return tostring(result.message or "I handled that.") .. trace_suffix
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
		if not options.platform_node then
			settings.platform_node = options.marker_node
		end
		if not options.path_node then
			settings.path_node = options.marker_node
		end
		if not options.wall_node then
			settings.wall_node = options.marker_node
		end
		if not options.house_node then
			settings.house_node = options.marker_node
		end
		if not options.cabin_node then
			settings.cabin_node = options.marker_node
		end
		if not options.landmark_node then
			settings.landmark_node = options.marker_node
		end
	end
	if options.platform_node then
		settings.platform_node = options.platform_node
	end
	if options.path_node then
		settings.path_node = options.path_node
	end
	if options.fire_node then
		settings.fire_node = options.fire_node
	end
	if options.wall_node then
		settings.wall_node = options.wall_node
	end
	if options.house_node then
		settings.house_node = options.house_node
	end
	if options.cabin_node then
		settings.cabin_node = options.cabin_node
	end
	if options.landmark_node then
		settings.landmark_node = options.landmark_node
	end
	if options.tnt_node then
		settings.tnt_node = options.tnt_node
	end
	if options.build_material_nodes then
		assert(type(options.build_material_nodes) == "table",
			"Build material nodes must be a table")
		settings.build_material_nodes = table.copy(options.build_material_nodes)
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
	if options.max_request_traces then
		settings.max_request_traces = options.max_request_traces
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
	if options.max_repair_radius then
		settings.max_repair_radius = options.max_repair_radius
	end
	if options.max_defend_distance then
		settings.max_defend_distance = options.max_defend_distance
	end
	if options.agentic_build_planner_first ~= nil then
		settings.agentic_build_planner_first =
			options.agentic_build_planner_first == true
	end
	if options.auto_apply_build_approvals ~= nil then
		settings.auto_apply_build_approvals =
			options.auto_apply_build_approvals == true
	end
	if options.max_player_loop_turns ~= nil then
		assert(type(options.max_player_loop_turns) == "number"
			and options.max_player_loop_turns >= 1,
			"Max player loop turns must be a positive number")
		settings.max_player_loop_turns = math.floor(options.max_player_loop_turns)
	end
	if options.player_loop_auto_review_enabled ~= nil then
		settings.player_loop_auto_review_enabled =
			options.player_loop_auto_review_enabled == true
	end
	if options.player_loop_review_interval ~= nil then
		assert(type(options.player_loop_review_interval) == "number"
			and options.player_loop_review_interval >= 0,
			"Player loop review interval must be a non-negative number")
		settings.player_loop_review_interval = options.player_loop_review_interval
	end
	if options.natural_chat_enabled ~= nil then
		settings.natural_chat_enabled = options.natural_chat_enabled == true
	end
	if options.natural_chat_aliases then
		assert(type(options.natural_chat_aliases) == "table",
			"Natural chat aliases must be a table")
		settings.natural_chat_aliases = table.copy(options.natural_chat_aliases)
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
		control_commands = { "stay", "wait" },
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
		player_states[name] = plugin._player_loop.copy_state({
			mode = "idle",
		})
	end
	player_states[name] = plugin._player_loop.copy_state(player_states[name])
	return plugin._player_loop.copy_state(player_states[name])
end

local function set_player_state(name, state)
	state = table.copy(state or {})
	if state.loop == nil and player_states[name] and player_states[name].loop then
		state.loop = table.copy(player_states[name].loop)
		state.loop.last_observation =
			plugin._player_loop.copy_observation(player_states[name].loop.last_observation)
	end
	player_states[name] = plugin._player_loop.copy_state(state)
	return plugin.get_player_state(name)
end

function plugin.set_model_adapter(adapter)
	assert(adapter == nil or type(adapter) == "function", "Model adapter must be a function")
	model_adapter = adapter
	if adapter ~= nil then
		model_adapter_async = nil
	end
end

function plugin.set_model_adapter_async(adapter)
	assert(adapter == nil or type(adapter) == "function",
		"Async model adapter must be a function")
	model_adapter_async = adapter
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

function plugin._player_loop.task_is_terminal(task)
	if type(task) ~= "table" then
		return false
	end
	return task.status == "completed"
		or task.status == "blocked"
		or task.status == "failed"
		or task.status == "unsafe"
		or task.status == "cancelled"
end

function plugin._player_loop.task_review_signature(task)
	local result = type(task.last_result) == "table" and task.last_result or {}
	return table.concat({
		tostring(task.status or "unknown"),
		tostring(result.status or ""),
		tostring(result.reason or ""),
		tostring(result.changed or ""),
		tostring(result.skipped or ""),
	}, "|")
end

function plugin._player_loop.compact_task_review(task)
	local result = type(task.last_result) == "table" and task.last_result or {}
	local metrics = type(result.metrics) == "table" and result.metrics or {}
	return {
		task_id = task.task_id,
		task_label = task.label,
		task_status = task.status,
		result_status = result.status,
		result_reason = result.reason,
		operation = result.operation,
		changed = result.changed,
		examined = result.examined,
		skipped = result.skipped,
		actual_node_writes = metrics.node_writes or result.changed,
		rollback_record_id = result.rollback_record_id,
		reviewed_us = trace_timestamp_us(),
	}
end

function plugin._player_loop.task_review_text(review)
	if type(review) ~= "table" then
		return nil
	end
	local text = "Task " .. tostring(review.task_label or review.task_id or "unknown")
		.. " " .. tostring(review.task_status or "unknown")
	if review.result_status then
		text = text .. " with result " .. tostring(review.result_status)
	end
	if review.actual_node_writes ~= nil then
		text = text .. " after " .. tostring(review.actual_node_writes)
			.. " node writes"
	end
	if review.result_reason then
		text = text .. " reason=" .. tostring(review.result_reason)
	end
	return bounded_trace_text(text, 240)
end

function plugin.review_player_agent_tasks(name, options)
	name = normalize_player_name(name)
	options = options or {}
	plugin._player_loop.task_reviews[name] =
		plugin._player_loop.task_reviews[name] or {}
	local reviews = {}
	for _, task_id in ipairs(player_task_ids[name] or {}) do
		local task = core.get_ai_task(task_id)
		if task and plugin._player_loop.task_is_terminal(task) then
			local signature = plugin._player_loop.task_review_signature(task)
			if options.force == true
					or plugin._player_loop.task_reviews[name][task.task_id]
						~= signature then
				plugin._player_loop.task_reviews[name][task.task_id] = signature
				reviews[#reviews + 1] =
					plugin._player_loop.compact_task_review(task)
			end
		end
	end
	local latest = reviews[#reviews]
	if latest then
		local blocked = latest.task_status == "blocked"
			or latest.task_status == "failed"
			or latest.task_status == "unsafe"
			or latest.task_status == "cancelled"
		plugin._player_loop.record(name, {
			status = latest.task_status,
			phase = blocked and "blocked" or "reviewing_result",
			next_action = blocked and "ask_player_or_replan" or "wait_for_player_intent",
			last_task_id = latest.task_id,
			last_result_status = latest.result_status or latest.task_status,
			last_task_review = latest,
		})
		if options.append_turn ~= false then
			plugin._player_loop.append_turn(name, "assistant",
				plugin._player_loop.task_review_text(latest),
				"task_review", "task_review")
		end
		if options.notify_player == true and core.chat_send_player then
			local message = plugin._player_loop.task_review_text(latest)
			if message then
				core.chat_send_player(name, message)
			end
		end
	end
	return public_reply(name, "player_loop_review", "success",
		latest and "Player-agent task review updated." or "No new task reviews.", {
			surface_id = "guide",
			review_count = #reviews,
			reviews = reviews,
			latest_review = latest,
		})
end

function plugin.step_player_agent_loops(options)
	options = options or {}
	local reviewed_players = 0
	local review_count = 0
	for name in pairs(player_task_ids) do
		local reply = plugin.review_player_agent_tasks(name, options)
		if reply.review_count and reply.review_count > 0 then
			reviewed_players = reviewed_players + 1
			review_count = review_count + reply.review_count
		end
	end
	return {
		ok = true,
		status = "success",
		action = "player_loop_step",
		reviewed_players = reviewed_players,
		review_count = review_count,
	}
end

local function player_task_by_id(name, requested_task_id)
	if type(requested_task_id) ~= "string" or requested_task_id == "" then
		return nil, nil
	end
	local requested = requested_task_id:trim()
	local requested_lower = requested:lower()
	for _, task_id in ipairs(player_task_ids[name] or {}) do
		if task_id == requested or task_id:lower() == requested_lower then
			return core.get_ai_task(task_id), task_id
		end
	end
	return nil, requested
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
		build_kind = context.build_kind,
		build_width = context.build_width,
		build_depth = context.build_depth,
		build_height = context.build_height,
		build_count = context.build_count,
		build_material_name = context.build_material_name,
		build_material_node = context.build_material_node,
		repair_radius = context.repair_radius,
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
		build_kind = pending.build_kind,
		build_width = pending.build_width,
		build_depth = pending.build_depth,
		build_height = pending.build_height,
		build_material_name = pending.build_material_name,
		build_material_node = pending.build_material_node,
		planner_mode = pending.planner_mode,
		selected_candidate_id = pending.selected_candidate_id,
		adapter_selected_candidate_id = pending.adapter_selected_candidate_id,
		model_selected_candidate_id = pending.model_selected_candidate_id,
		selection_source = pending.selection_source,
		intent_constraint_option_id = pending.intent_constraint_option_id,
		intent_constraint_reason = pending.intent_constraint_reason,
		candidate_options = pending.candidate_options,
		adapter_tool_decision_source = pending.adapter_tool_decision_source,
		adapter_model_selected_candidate_id =
			pending.adapter_model_selected_candidate_id,
		adapter_initial_model_selected_candidate_id =
			pending.adapter_initial_model_selected_candidate_id,
		adapter_rejected_model_selected_candidate_id =
			pending.adapter_rejected_model_selected_candidate_id,
		adapter_agent_repair_attempted =
			pending.adapter_agent_repair_attempted,
		adapter_agent_repair_succeeded =
			pending.adapter_agent_repair_succeeded,
		adapter_agent_repair_reason =
			pending.adapter_agent_repair_reason,
		adapter_initial_missing_required_tool_calls =
			pending.adapter_initial_missing_required_tool_calls,
		adapter_required_tool_calls = pending.adapter_required_tool_calls,
		adapter_missing_required_tool_calls = pending.adapter_missing_required_tool_calls,
		adapter_required_tool_calls_satisfied =
			pending.adapter_required_tool_calls_satisfied,
		build_option_decision_source = pending.build_option_decision_source,
		adapter_memory_available = pending.adapter_memory_available,
		adapter_memory_matched_case_id = pending.adapter_memory_matched_case_id,
		adapter_memory_case_hint = pending.adapter_memory_case_hint,
		adapter_tool_trace_names = pending.adapter_tool_trace_names,
		adapter_build_action_plan_status =
			pending.adapter_build_action_plan_status,
		adapter_build_action_plan_selected_candidate_id =
			pending.adapter_build_action_plan_selected_candidate_id,
		adapter_build_action_plan_step_count =
			pending.adapter_build_action_plan_step_count,
		adapter_build_action_plan_world_mutation_authority =
			pending.adapter_build_action_plan_world_mutation_authority,
		generated_build_option_status = pending.generated_build_option_status,
		generated_build_option_reason = pending.generated_build_option_reason,
		generated_candidate_id = pending.generated_candidate_id,
		agentic_tool_success_required =
			pending.agentic_tool_success_required,
		repair_radius = pending.repair_radius,
		sample_limit = pending.sample_limit,
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
		build_kind = extra.build_kind,
		build_width = extra.build_width,
		build_depth = extra.build_depth,
		build_height = extra.build_height,
		build_material_name = extra.build_material_name,
		build_material_node = extra.build_material_node,
		planner_mode = extra.planner_mode,
		selected_candidate_id = extra.selected_candidate_id,
		adapter_selected_candidate_id = extra.adapter_selected_candidate_id,
		model_selected_candidate_id = extra.model_selected_candidate_id,
		selection_source = extra.selection_source,
		intent_constraint_option_id = extra.intent_constraint_option_id,
		intent_constraint_reason = extra.intent_constraint_reason,
		candidate_options = extra.candidate_options,
		adapter_tool_decision_source = extra.adapter_tool_decision_source,
		adapter_model_selected_candidate_id =
			extra.adapter_model_selected_candidate_id,
		adapter_initial_model_selected_candidate_id =
			extra.adapter_initial_model_selected_candidate_id,
		adapter_rejected_model_selected_candidate_id =
			extra.adapter_rejected_model_selected_candidate_id,
		adapter_agent_repair_attempted =
			extra.adapter_agent_repair_attempted,
		adapter_agent_repair_succeeded =
			extra.adapter_agent_repair_succeeded,
		adapter_agent_repair_reason =
			extra.adapter_agent_repair_reason,
		adapter_initial_missing_required_tool_calls =
			extra.adapter_initial_missing_required_tool_calls,
		adapter_required_tool_calls = extra.adapter_required_tool_calls,
		adapter_missing_required_tool_calls =
			extra.adapter_missing_required_tool_calls,
		adapter_required_tool_calls_satisfied =
			extra.adapter_required_tool_calls_satisfied,
		build_option_decision_source = extra.build_option_decision_source,
		adapter_memory_available = extra.adapter_memory_available,
		adapter_memory_matched_case_id = extra.adapter_memory_matched_case_id,
		adapter_memory_case_hint = extra.adapter_memory_case_hint,
		adapter_tool_trace_names = extra.adapter_tool_trace_names,
		adapter_build_action_plan_status =
			extra.adapter_build_action_plan_status,
		adapter_build_action_plan_selected_candidate_id =
			extra.adapter_build_action_plan_selected_candidate_id,
		adapter_build_action_plan_step_count =
			extra.adapter_build_action_plan_step_count,
		adapter_build_action_plan_world_mutation_authority =
			extra.adapter_build_action_plan_world_mutation_authority,
		generated_build_option_status = extra.generated_build_option_status,
		generated_build_option_reason = extra.generated_build_option_reason,
		generated_candidate_id = extra.generated_candidate_id,
		agentic_tool_success_required =
			extra.agentic_tool_success_required,
		repair_radius = extra.repair_radius,
		sample_limit = extra.sample_limit,
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

local function parse_build_positive_int(raw_value)
	if type(raw_value) ~= "string" or raw_value == "" then
		return nil
	end
	local number = tonumber(raw_value)
	if not number then
		return nil
	end
	number = math.floor(number)
	if number < 1 then
		return nil
	end
	return number
end

local function build_kind_for(context)
	context = context or {}
	return context.build_kind or "marker"
end

local function build_width_for(context)
	context = context or {}
	return context.build_width or 2
end

local function build_depth_for(context)
	context = context or {}
	return context.build_depth or 2
end

local function build_height_for(context)
	context = context or {}
	return context.build_height or 3
end

local function build_count_for(context)
	context = context or {}
	return context.build_count or 1
end

function plugin._bounded_shell_writes(width, depth, height, limit)
	width = math.max(1, math.floor(width or 1))
	depth = math.max(1, math.floor(depth or 1))
	height = math.max(1, math.floor(height or 1))
	limit = math.max(1, math.floor(limit or settings.max_lights))
	local floor_writes = width * depth
	if floor_writes >= limit then
		return floor_writes
	end
	local corners = 1
	if width > 1 and depth > 1 then
		corners = 4
	elseif width > 1 or depth > 1 then
		corners = 2
	end
	return floor_writes + math.min(corners * math.max(0, height - 1),
		limit - floor_writes)
end

function plugin._bounded_landmark_writes(width, depth, height, limit)
	width = math.max(1, math.floor(width or 1))
	depth = math.max(1, math.floor(depth or 1))
	height = math.max(1, math.floor(height or 1))
	limit = math.max(1, math.floor(limit or settings.max_lights))
	local base_writes = width * depth
	if base_writes >= limit then
		return base_writes
	end
	return base_writes + math.min(height, limit - base_writes)
end

local function node_is_registered(node_name)
	return type(node_name) == "string"
		and node_name ~= ""
		and (not core.registered_nodes or core.registered_nodes[node_name] ~= nil)
end

local function append_candidate_node(candidates, node_name)
	if type(node_name) ~= "string" or node_name == "" then
		return
	end
	for _, existing in ipairs(candidates) do
		if existing == node_name then
			return
		end
	end
	candidates[#candidates + 1] = node_name
end

local function material_node_candidates(material_name)
	local candidates = {}
	if settings.build_material_nodes then
		append_candidate_node(candidates, settings.build_material_nodes[material_name])
	end
	if material_name == "tnt" then
		append_candidate_node(candidates, settings.tnt_node)
		append_candidate_node(candidates, "mcl_tnt:tnt")
		append_candidate_node(candidates, "tnt:tnt")
		append_candidate_node(candidates, "experimental:tnt")
	elseif material_name == "fire" then
		append_candidate_node(candidates, settings.fire_node)
		append_candidate_node(candidates, "mcl_fire:fire")
		append_candidate_node(candidates, "fire:basic_flame")
		append_candidate_node(candidates, "fire:permanent_flame")
	elseif material_name == "stone" then
		append_candidate_node(candidates, settings.platform_node)
		append_candidate_node(candidates, settings.marker_node)
	end
	return candidates
end

local function resolve_build_material_node(material_name, fallback_node)
	if not material_name then
		return fallback_node
	end
	for _, node_name in ipairs(material_node_candidates(material_name)) do
		if node_is_registered(node_name) then
			return node_name
		end
	end
	return nil
end

local function parse_build_material_name(lower_prompt)
	if lower_prompt:find("tnt", 1, true) then
		return "tnt"
	end
	if lower_prompt:find("fire", 1, true) or lower_prompt:find("flame", 1, true) then
		return "fire"
	end
	if lower_prompt:find("gold", 1, true) then
		return "gold"
	end
	if lower_prompt:find("quartz", 1, true) then
		return "quartz"
	end
	if lower_prompt:find("wood", 1, true) or lower_prompt:find("wooden", 1, true) then
		return "wood"
	end
	if lower_prompt:find("glass", 1, true) then
		return "glass"
	end
	if lower_prompt:find("diamond", 1, true) then
		return "diamond"
	end
	if lower_prompt:find("glow", 1, true) or lower_prompt:find("light", 1, true) then
		return "glow"
	end
	if lower_prompt:find("stone", 1, true) then
		return "stone"
	end
	return nil
end

local function parse_named_build_int(lower_prompt, name)
	return parse_build_positive_int(lower_prompt:match(name .. "%s+([%-%d]+)"))
		or parse_build_positive_int(lower_prompt:match("([%-%d]+)%s+" .. name))
end

local function prompt_is_explicit_marker_build(lower_prompt)
	return lower_prompt == "build"
		or lower_prompt == "build plan"
		or lower_prompt == "preview build"
		or lower_prompt == "build marker"
		or lower_prompt == "marker"
		or lower_prompt == "build a marker"
		or lower_prompt == "place marker"
		or lower_prompt:find("marker", 1, true) ~= nil
end

local function build_options_for(name, context, task_id)
	context = context or {}
	local kind = build_kind_for(context)
	local options = {
		kind = kind,
		task_id = task_id,
		agent_id = surface_agent_id_for(name, "builder"),
		owner = name,
		world_id = context.world_id or "ai_agent_plugin",
		origin = default_pos(context),
		get_node = context.get_node,
		set_node = context.set_node,
		max_node_writes_per_step = context.max_node_writes_per_step,
		persist_record = context.persist_record or context.persist_rollback_record,
		rollback_policy = context.rollback_policy,
		operation_label = "ai_agent_plugin.build",
		sample_limit = context.sample_limit or settings.max_lights,
	}
	if context.build_material_node then
		options.material_node = context.build_material_node
	end
	if kind == "platform" then
		options.width = build_width_for(context)
		options.depth = build_depth_for(context)
		options.material_node = options.material_node or settings.platform_node
		options.max_node_writes_per_step = options.max_node_writes_per_step
			or math.min(options.width * options.depth, settings.max_lights)
	elseif kind == "wall" then
		options.width = build_width_for(context)
		options.height = build_height_for(context)
		options.material_node = options.material_node or settings.wall_node
		options.max_node_writes_per_step = options.max_node_writes_per_step
			or math.min(options.width * options.height, settings.max_lights)
	elseif kind == "fire" then
		options.count = build_count_for(context)
		options.material_node = options.material_node or settings.fire_node
		options.max_node_writes_per_step = options.max_node_writes_per_step
			or math.min(options.count, settings.max_lights)
	elseif kind == "house" or kind == "cabin" then
		options.width = build_width_for(context)
		options.depth = build_depth_for(context)
		options.height = build_height_for(context)
		if kind == "house" then
			options.material_node = options.material_node or settings.house_node
		else
			options.material_node = options.material_node or settings.cabin_node
		end
		options.max_node_writes_per_step = options.max_node_writes_per_step
			or math.min(
				plugin._bounded_shell_writes(options.width, options.depth, options.height,
					settings.max_lights),
				settings.max_lights)
	elseif kind == "landmark" then
		options.width = build_width_for(context)
		options.depth = build_depth_for(context)
		options.height = build_height_for(context)
		options.material_node = options.material_node or settings.landmark_node
		options.max_node_writes_per_step = options.max_node_writes_per_step
			or math.min(
				plugin._bounded_landmark_writes(options.width, options.depth, options.height,
					settings.max_lights),
				settings.max_lights)
	else
		options.kind = "marker"
		options.material_node = options.material_node or settings.marker_node
		options.max_node_writes_per_step = options.max_node_writes_per_step or 1
	end
	return options
end

local function parse_build_options(raw_prompt, context)
	local parsed = table.copy(context or {})
	local lower = raw_prompt:lower()
	local material_name = parse_build_material_name(lower)
	if lower:find("house", 1, true) or lower:find("home", 1, true)
			or lower:find("cabin", 1, true) or lower:find("hut", 1, true)
			or lower:find("landmark", 1, true) or lower:find("monument", 1, true)
			or lower:find("statue", 1, true) then
		local kind = "house"
		local fallback_node = settings.house_node
		if lower:find("cabin", 1, true) or lower:find("hut", 1, true) then
			kind = "cabin"
			fallback_node = settings.cabin_node
		elseif lower:find("landmark", 1, true)
				or lower:find("monument", 1, true)
				or lower:find("statue", 1, true) then
			kind = "landmark"
			fallback_node = settings.landmark_node
		end
		parsed.build_kind = kind
		parsed.build_material_name = material_name
		parsed.build_material_node = resolve_build_material_node(
			material_name, fallback_node)
		if material_name and not parsed.build_material_node then
			return nil, "build_material_unavailable"
		end
		local width = parse_named_build_int(lower, "width")
			or parse_build_positive_int(lower:match("([%-%d]+)%s+wide"))
			or parse_named_build_int(lower, "wide")
			or parse_build_positive_int(lower:match("(%d+)%s*x%s*%d+"))
			or 3
		local depth = parse_named_build_int(lower, "depth")
			or parse_named_build_int(lower, "deep")
			or parse_build_positive_int(lower:match("%d+%s*x%s*(%d+)"))
			or (kind == "landmark" and 3 or 2)
		local height = parse_named_build_int(lower, "height")
			or parse_build_positive_int(lower:match("([%-%d]+)%s+high"))
			or parse_named_build_int(lower, "high")
			or parse_build_positive_int(lower:match("([%-%d]+)%s+tall"))
			or parse_named_build_int(lower, "tall")
			or 3
		if not width or not depth or not height then
			return nil, "invalid_build_dimensions"
		end
		local planned_writes = kind == "landmark"
			and plugin._bounded_landmark_writes(width, depth, height, settings.max_lights)
			or plugin._bounded_shell_writes(width, depth, height, settings.max_lights)
		if planned_writes > settings.max_lights then
			return nil, "build_shape_out_of_bounds"
		end
		parsed.build_width = width
		parsed.build_depth = depth
		parsed.build_height = height
	elseif lower:find("wall", 1, true) then
		parsed.build_kind = "wall"
		parsed.build_material_name = material_name
		parsed.build_material_node = resolve_build_material_node(
			material_name, settings.wall_node)
		if not parsed.build_material_node then
			return nil, "build_material_unavailable"
		end
		local x_width, x_height = lower:match("(%d+)%s*x%s*(%d+)")
		local width = parse_named_build_int(lower, "width")
			or parse_build_positive_int(lower:match("([%-%d]+)%s+wide"))
			or parse_named_build_int(lower, "wide")
			or parse_build_positive_int(lower:match("([%-%d]+)%s+length"))
			or parse_named_build_int(lower, "length")
			or parse_build_positive_int(x_width or "4")
		local height = parse_named_build_int(lower, "height")
			or parse_build_positive_int(lower:match("([%-%d]+)%s+high"))
			or parse_named_build_int(lower, "high")
			or parse_build_positive_int(lower:match("([%-%d]+)%s+tall"))
			or parse_named_build_int(lower, "tall")
			or parse_build_positive_int(x_height or "3")
		if not width or not height then
			return nil, "invalid_build_dimensions"
		end
		if width * height > settings.max_lights then
			return nil, "build_shape_out_of_bounds"
		end
		parsed.build_width = width
		parsed.build_depth = nil
		parsed.build_height = height
	elseif material_name == "fire" then
		parsed.build_kind = "fire"
		parsed.build_material_name = "fire"
		parsed.build_material_node = resolve_build_material_node("fire", settings.fire_node)
		if not parsed.build_material_node then
			return nil, "build_material_unavailable"
		end
		local count = parse_build_positive_int(lower:match("(%d+)%s+fires?") or "1")
		if not count then
			return nil, "invalid_build_dimensions"
		end
		if count > settings.max_lights then
			return nil, "build_shape_out_of_bounds"
		end
		parsed.build_count = count
		parsed.build_width = nil
		parsed.build_depth = nil
		parsed.build_height = nil
	elseif lower:find("platform", 1, true) then
		parsed.build_kind = "platform"
		parsed.build_material_name = material_name
		parsed.build_material_node = resolve_build_material_node(
			material_name, settings.platform_node)
		if material_name and not parsed.build_material_node then
			return nil, "build_material_unavailable"
		end
		local width_text = lower:match("width%s+([%-%d]+)")
		local depth_text = lower:match("depth%s+([%-%d]+)")
		if not width_text or not depth_text then
			local x_width, x_depth = lower:match("(%d+)%s*x%s*(%d+)")
			width_text = width_text or x_width
			depth_text = depth_text or x_depth
		end
		local width = parse_build_positive_int(width_text or "2")
		local depth = parse_build_positive_int(depth_text or "2")
		if not width or not depth then
			return nil, "invalid_build_dimensions"
		end
		if width * depth > settings.max_lights then
			return nil, "build_shape_out_of_bounds"
		end
		parsed.build_width = width
		parsed.build_depth = depth
		parsed.build_height = nil
	elseif prompt_is_explicit_marker_build(lower) then
		parsed.build_kind = "marker"
		parsed.build_material_name = material_name
		parsed.build_material_node = resolve_build_material_node(
			material_name, settings.marker_node)
		if material_name and not parsed.build_material_node then
			return nil, "build_material_unavailable"
		end
		parsed.build_width = nil
		parsed.build_depth = nil
		parsed.build_height = nil
	else
		return nil, "ambiguous_build_intent"
	end
	return parsed, nil
end

local function parse_build_edit_options(raw_prompt, context)
	local lower = raw_prompt:lower()
	local has_shape = raw_prompt:match("[Ww][Ii][Dd][Tt][Hh]%s+([%-%d]+)")
		or raw_prompt:match("[Dd][Ee][Pp][Tt][Hh]%s+([%-%d]+)")
		or raw_prompt:match("[Hh][Ee][Ii][Gg][Hh][Tt]%s+([%-%d]+)")
		or raw_prompt:match("%d+%s*[Xx]%s*%d+")
	if not lower:find("marker", 1, true)
			and not lower:find("platform", 1, true)
			and not lower:find("wall", 1, true)
			and not lower:find("fire", 1, true)
			and not lower:find("tnt", 1, true)
			and not has_shape then
		return nil, "no_plan_edit_parameters"
	end
	local prompt = raw_prompt
	if has_shape and not lower:find("platform", 1, true)
			and not lower:find("wall", 1, true)
			and not lower:find("marker", 1, true) then
		prompt = raw_prompt .. " platform"
	end
	return parse_build_options(prompt, context)
end

local function parse_feedback_bool(raw_value)
	if raw_value == nil then
		return nil
	end
	local value = tostring(raw_value):lower():trim()
	if value == "1" or value == "true" or value == "yes"
			or value == "y" or value == "on" then
		return true
	end
	if value == "0" or value == "false" or value == "no"
			or value == "n" or value == "off" then
		return false
	end
	return nil
end

local function split_feedback_segments(raw)
	local text = tostring(raw or ""):trim()
	local segments = {}
	if text == "" then
		return segments
	end
	if text:find(";", 1, true) then
		for segment in text:gmatch("[^;]+") do
			segment = segment:trim()
			if segment ~= "" then
				segments[#segments + 1] = segment
			end
		end
	else
		for segment in text:gmatch("%S+") do
			segments[#segments + 1] = segment
		end
	end
	return segments
end

local function parse_operator_feedback_params(raw)
	local params = {
		use_latest = false,
	}
	for _, segment in ipairs(split_feedback_segments(raw)) do
		if segment:lower() == "last" then
			params.use_latest = true
		else
			local key, value = segment:match("^([%w_%-]+)%s*=%s*(.+)$")
			if not key or not value then
				return nil, "invalid_feedback_parameter"
			end
			key = key:lower():gsub("%-", "_")
			value = value:trim()
			if value == "" then
				return nil, "invalid_feedback_parameter"
			end
			if key == "prompt" or key == "public_prompt" then
				params.prompt = bounded_trace_text(value, 1000)
			elseif key == "case" or key == "case_hint" then
				params.case_hint = bounded_trace_text(value, 120)
			elseif key == "label" or key == "label_id" then
				params.label_id = bounded_trace_text(value, 160)
			elseif key == "candidate" or key == "candidate_id" then
				params.candidate_id = bounded_trace_text(value, 180)
			elseif key == "trace" or key == "trace_id" then
				params.trace_id = bounded_trace_text(value, 120)
			elseif key == "source" or key == "source_kind" then
				params.source_kind = bounded_trace_text(value, 120)
			elseif key == "build_kind" or key == "kind" then
				params.build_kind = bounded_trace_text(value:lower(), 80)
			elseif key == "material" or key == "build_material"
					or key == "build_material_name" then
				params.build_material_name = bounded_trace_text(value:lower(), 80)
			elseif key == "node" or key == "build_material_node" then
				params.build_material_node = bounded_trace_text(value, 160)
			elseif key == "planned_writes" or key == "planned_node_writes"
					or key == "writes" or key == "count" then
				params.planned_node_writes = parse_build_positive_int(value)
				if not params.planned_node_writes then
					return nil, "invalid_feedback_planned_writes"
				end
			elseif key == "selected_candidate" or key == "selected_candidate_id" then
				params.selected_candidate_id = bounded_trace_text(value, 120)
			elseif key == "width" or key == "build_width" then
				params.build_width = parse_build_positive_int(value)
				if not params.build_width then
					return nil, "invalid_feedback_width"
				end
			elseif key == "depth" or key == "build_depth" then
				params.build_depth = parse_build_positive_int(value)
				if not params.build_depth then
					return nil, "invalid_feedback_depth"
				end
			elseif key == "height" or key == "build_height" then
				params.build_height = parse_build_positive_int(value)
				if not params.build_height then
					return nil, "invalid_feedback_height"
				end
			elseif key == "build_count" then
				params.build_count = parse_build_positive_int(value)
				if not params.build_count then
					return nil, "invalid_feedback_count"
				end
			elseif key == "route" then
				params.route = bounded_trace_text(value, 120)
			elseif key == "danger_refusal_allowed" then
				local parsed = parse_feedback_bool(value)
				if parsed == nil then
					return nil, "invalid_feedback_bool"
				end
				params.danger_refusal_allowed = parsed
			elseif key == "forbidden_extra_structure"
					or key == "no_extra_structure"
					or key == "extra_structure_forbidden" then
				local parsed = parse_feedback_bool(value)
				if parsed == nil then
					return nil, "invalid_feedback_bool"
				end
				params.forbidden_extra_structure = parsed
			else
				return nil, "unknown_feedback_parameter"
			end
		end
	end
	if not params.prompt and not params.trace_id then
		params.use_latest = true
	end
	return params
end

local function latest_feedback_trace_for(name, trace_id)
	local traces = plugin.get_request_traces({ limit = settings.max_request_traces or 50 })
	for index = #traces, 1, -1 do
		local trace = traces[index]
		if type(trace) == "table"
				and type(trace.public_prompt) == "string"
				and trace.public_prompt ~= ""
				and (not trace_id or trace.trace_id == trace_id)
				and (trace_id or trace.owner == name) then
			return trace
		end
	end
	return nil
end

local function expected_from_feedback_params(params)
	if not params.build_kind or params.build_kind == "" then
		return nil, "feedback_build_kind_required"
	end
	if not params.build_material_name or params.build_material_name == "" then
		return nil, "feedback_material_required"
	end
	local expected = {
		action = "build",
		build_kind = params.build_kind,
		build_material_name = params.build_material_name,
	}
	if params.build_material_node then
		expected.build_material_node = params.build_material_node
	end
	if params.planned_node_writes then
		expected.planned_node_writes = params.planned_node_writes
	end
	if params.route then
		expected.route = params.route
	end
	if params.selected_candidate_id then
		expected.selected_candidate_id = params.selected_candidate_id
	end
	if params.build_width then
		expected.build_width = params.build_width
	end
	if params.build_depth then
		expected.build_depth = params.build_depth
	end
	if params.build_height then
		expected.build_height = params.build_height
	end
	if params.build_count then
		expected.build_count = params.build_count
	end
	if params.danger_refusal_allowed ~= nil then
		expected.danger_refusal_allowed = params.danger_refusal_allowed
	end
	if params.forbidden_extra_structure ~= nil then
		expected.forbidden_extra_structure = params.forbidden_extra_structure
	end
	return expected
end

function plugin._planned_feedback_writes_for(context)
	local kind = build_kind_for(context)
	if kind == "wall" then
		return build_width_for(context) * build_height_for(context)
	end
	if kind == "platform" then
		return build_width_for(context) * build_depth_for(context)
	end
	if kind == "fire" then
		return build_count_for(context)
	end
	if kind == "house" or kind == "cabin" then
		return plugin._bounded_shell_writes(build_width_for(context), build_depth_for(context),
			build_height_for(context), settings.max_lights)
	end
	if kind == "landmark" then
		return plugin._bounded_landmark_writes(build_width_for(context), build_depth_for(context),
			build_height_for(context), settings.max_lights)
	end
	return 1
end

function plugin._feedback_material_name_for(context)
	if context.build_material_name and context.build_material_name ~= "" then
		return context.build_material_name
	end
	if build_kind_for(context) == "fire" then
		return "fire"
	end
	return "stone"
end

function plugin._feedback_case_hint_for(context, material_name)
	local kind = build_kind_for(context)
	if kind == "fire" and material_name == "fire" and build_count_for(context) == 1 then
		return "fire_only_strict"
	end
	if kind == "wall" and material_name == "tnt" then
		return "tnt_wall"
	end
	return tostring(material_name or "default"):gsub("[^%w_%-]+", "_")
		.. "_" .. tostring(kind or "build")
end

function plugin._structured_feedback_param(raw)
	local text = tostring(raw or ""):trim()
	if text == "" then
		return nil
	end
	local lower = text:lower()
	if not text:find("=", 1, true) and not text:find(";", 1, true)
			and lower ~= "last" then
		return nil
	end
	if lower ~= "last"
			and not lower:match("^last[%s;]")
			and not lower:find("trace=", 1, true)
			and not lower:find("trace_id=", 1, true)
			and not lower:find("prompt=", 1, true)
			and not lower:find("public_prompt=", 1, true) then
		return "last; " .. text
	end
	return text
end

function plugin._natural_feedback_param(raw)
	local text = tostring(raw or ""):trim()
	if text == "" then
		return nil, "feedback_expected_behavior_required"
	end
	local lower = text:lower()
	if lower:match("^last%s+") then
		text = text:sub(6):trim()
		lower = text:lower()
	end
	if text == "" then
		return nil, "feedback_expected_behavior_required"
	end
	local parsed, reason = parse_build_options(text, {})
	if not parsed and reason == "ambiguous_build_intent" then
		parsed, reason = parse_build_options("build " .. text, {})
	end
	if not parsed then
		return nil, reason
	end

	local material_name = plugin._feedback_material_name_for(parsed)
	local planned_writes = plugin._planned_feedback_writes_for(parsed)
	local pieces = {
		"last",
		"case=" .. plugin._feedback_case_hint_for(parsed, material_name),
		"build_kind=" .. build_kind_for(parsed),
		"material=" .. material_name,
		"planned_writes=" .. tostring(planned_writes),
		"route=agentic_build_planner",
		"danger_refusal_allowed=false",
		"forbidden_extra_structure=true",
	}
	if parsed.build_material_node then
		pieces[#pieces + 1] = "node=" .. tostring(parsed.build_material_node)
	end
	if parsed.build_width then
		pieces[#pieces + 1] = "width=" .. tostring(parsed.build_width)
	end
	if parsed.build_depth then
		pieces[#pieces + 1] = "depth=" .. tostring(parsed.build_depth)
	end
	if parsed.build_height then
		pieces[#pieces + 1] = "height=" .. tostring(parsed.build_height)
	end
	if parsed.build_count then
		pieces[#pieces + 1] = "build_count=" .. tostring(parsed.build_count)
	end
	return table.concat(pieces, "; "), nil
end

function plugin._nova_feedback_payload(raw_prompt)
	local text = tostring(raw_prompt or ""):trim()
	local command, rest = text:match("^(%S+)%s*(.*)$")
	if not command then
		return nil
	end
	command = command:lower()
	if command == "feedback" or command == "wrong"
			or command == "bad" or command == "teach" then
		return tostring(rest or ""):trim()
	end
	return nil
end

function plugin._handle_nova_feedback(name, raw_payload, context)
	local param = plugin._structured_feedback_param(raw_payload)
	local reason
	if not param then
		param, reason = plugin._natural_feedback_param(raw_payload)
	end
	if not param then
		return public_reply(name, "agent_feedback", "blocked",
			"Feedback expected behavior was incomplete.", {
				surface_id = "guide",
				reason = reason,
				no_world_mutation = true,
			})
	end
	local feedback_context = table.copy(context or {})
	feedback_context.review_source = "nova_feedback_chatcommand"
	return plugin.record_operator_feedback(name, param, feedback_context)
end

function plugin.record_operator_feedback(name, param, context)
	name = normalize_player_name(name)
	context = context or {}
	local params, reason = parse_operator_feedback_params(param)
	if not params then
		return public_reply(name, "agent_feedback", "blocked",
			"Feedback parameters were invalid.", {
				surface_id = "guide",
				reason = reason,
			})
	end
	local trace
	if params.trace_id or params.use_latest then
		trace = latest_feedback_trace_for(name, params.trace_id)
		if not trace then
			return public_reply(name, "agent_feedback", "blocked",
				"No matching request trace was found for feedback.", {
					surface_id = "guide",
					reason = "feedback_trace_not_found",
					trace_id = params.trace_id,
				})
		end
		params.prompt = params.prompt or trace.public_prompt
		params.source_trace_id = trace.trace_id
	end
	if not params.prompt or params.prompt == "" then
		return public_reply(name, "agent_feedback", "blocked",
			"Feedback requires a prompt or a matching recent trace.", {
				surface_id = "guide",
				reason = "feedback_prompt_required",
			})
	end
	local expected, expected_reason = expected_from_feedback_params(params)
	if not expected then
		return public_reply(name, "agent_feedback", "blocked",
			"Feedback expected behavior was incomplete.", {
				surface_id = "guide",
				reason = expected_reason,
			})
	end
	operator_feedback_sequence = operator_feedback_sequence + 1
	local feedback_id = "operator_feedback:" .. tostring(operator_feedback_sequence)
	local feedback = {
		feedback_id = feedback_id,
		owner = name,
		agent_id = surface_agent_id_for(name, "guide"),
		created_us = trace_timestamp_us(),
		prompt = bounded_trace_text(params.prompt, 1000),
		source_trace_id = params.source_trace_id,
		candidate_id = params.candidate_id,
		source_kind = params.source_kind,
		case_hint = params.case_hint
			or ("operator_labeled_" .. expected.build_material_name
				.. "_" .. expected.build_kind),
		label_id = params.label_id,
		expected = expected,
		review = {
			operator_reviewed = true,
			review_source = bounded_trace_text(
				context.review_source or "ai_agent_feedback_chatcommand", 120),
			no_world_mutation = true,
		},
	}
	local event = {
		schema_version = 1,
		event_kind = "ai_agent_operator_feedback",
		feedback = feedback,
		safety = {
			public_safe_output = true,
			operator_reviewed = true,
			no_world_mutation = true,
			no_raw_assets = true,
			no_provider_prompts = true,
			no_family_world_coordinates = true,
		},
	}
	operator_feedback_events[#operator_feedback_events + 1] = event
	local max_events = math.max(1, settings.max_operator_feedback_events or 50)
	while #operator_feedback_events > max_events do
		table.remove(operator_feedback_events, 1)
	end
	log_operator_feedback_event(event)
	return public_reply(name, "agent_feedback", "success",
		"Operator feedback recorded for prompt-eval promotion.", {
			surface_id = "guide",
			feedback_id = feedback_id,
			prompt = feedback.prompt,
			source_trace_id = feedback.source_trace_id,
			candidate_id = feedback.candidate_id,
			source_kind = feedback.source_kind,
			case_hint = feedback.case_hint,
			expected = table.copy(expected),
			no_world_mutation = true,
		})
end

local function prompt_has_build_surface(prompt)
	return prompt:find("build", 1, true)
		or prompt:find("marker", 1, true)
		or prompt:find("platform", 1, true)
		or prompt:find("wall", 1, true)
		or prompt:find("fire", 1, true)
		or prompt:find("tnt", 1, true)
end

local function queue_build_task(name, context)
	context = context or {}
	configure_product_surfaces()
	local task_id = next_task_id(name, "build")
	plugin.ensure_surface_agent(name, "builder")
	local build_options = build_options_for(name, context, task_id)
	return queue_defined_task(name, "build", "build " .. build_options.kind,
		core.build_agent.define_task(build_options), "builder")
end

local function build_plan_for(name, context)
	context = context or {}
	configure_product_surfaces()
	local agent_id = surface_agent_id_for(name, "builder")
	plugin.ensure_surface_agent(name, "builder")
	local build_options = build_options_for(name, context, context.task_id)
	build_options.agent_id = agent_id
	local result = core.build_agent.plan(build_options)
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
	plan.build_kind = build_options.kind
	plan.build_width = build_options.width
	plan.build_depth = build_options.depth
	plan.build_height = build_options.height
	plan.build_count = build_options.count
	plan.build_material_name = context.build_material_name
	plan.build_material_node = build_options.material_node
	return result, plan
end

local function handle_build_plan(name, context)
	local result, plan = build_plan_for(name, context)
	return public_reply(name, "build_plan", result.status, "Build plan returned without mutation.", {
		surface_id = "builder",
		plan = plan,
		planned_node_writes = plan.metrics.planned_node_writes or 0,
		build_kind = plan.build_kind,
		build_width = plan.build_width,
		build_depth = plan.build_depth,
		build_height = plan.build_height,
		build_material_name = plan.build_material_name,
		build_material_node = plan.build_material_node,
	})
end

function plugin.auto_apply_build_pending_reply(name, pending, result, plan)
	player_pending_approvals[name] = nil
	local queued = queue_build_task(name, pending.context)
	queued.message = "Build plan auto-applied and queued."
	queued.auto_applied_approval = true
	queued.auto_apply_policy = "ai_runtime.auto_apply_build_approvals"
	queued.approved_action = "build"
	queued.approval_id = pending.approval_id
	queued.pending_action = nil
	queued.plan = plan
	queued.plan_status = result.status
	queued.planned_node_writes = pending.planned_node_writes
	queued.build_kind = pending.build_kind
	queued.build_width = pending.build_width
	queued.build_depth = pending.build_depth
	queued.build_height = pending.build_height
	queued.build_material_name = pending.build_material_name
	queued.build_material_node = pending.build_material_node
	queued.planner_mode = pending.planner_mode
	queued.selected_candidate_id = pending.selected_candidate_id
	queued.adapter_selected_candidate_id = pending.adapter_selected_candidate_id
	queued.model_selected_candidate_id = pending.model_selected_candidate_id
	queued.selection_source = pending.selection_source
	queued.intent_constraint_option_id = pending.intent_constraint_option_id
	queued.intent_constraint_reason = pending.intent_constraint_reason
	queued.adapter_tool_decision_source = pending.adapter_tool_decision_source
	queued.adapter_model_selected_candidate_id =
		pending.adapter_model_selected_candidate_id
	queued.adapter_initial_model_selected_candidate_id =
		pending.adapter_initial_model_selected_candidate_id
	queued.adapter_rejected_model_selected_candidate_id =
		pending.adapter_rejected_model_selected_candidate_id
	queued.adapter_agent_repair_attempted =
		pending.adapter_agent_repair_attempted
	queued.adapter_agent_repair_succeeded =
		pending.adapter_agent_repair_succeeded
	queued.adapter_agent_repair_reason =
		pending.adapter_agent_repair_reason
	queued.adapter_initial_missing_required_tool_calls =
		pending.adapter_initial_missing_required_tool_calls
	queued.adapter_required_tool_calls = pending.adapter_required_tool_calls
	queued.adapter_missing_required_tool_calls = pending.adapter_missing_required_tool_calls
	queued.adapter_required_tool_calls_satisfied =
		pending.adapter_required_tool_calls_satisfied
	queued.build_option_decision_source = pending.build_option_decision_source
	queued.adapter_memory_available = pending.adapter_memory_available
	queued.adapter_memory_matched_case_id = pending.adapter_memory_matched_case_id
	queued.adapter_memory_case_hint = pending.adapter_memory_case_hint
	queued.adapter_tool_trace_names = pending.adapter_tool_trace_names
	queued.adapter_build_action_plan_status =
		pending.adapter_build_action_plan_status
	queued.adapter_build_action_plan_selected_candidate_id =
		pending.adapter_build_action_plan_selected_candidate_id
	queued.adapter_build_action_plan_step_count =
		pending.adapter_build_action_plan_step_count
	queued.adapter_build_action_plan_world_mutation_authority =
		pending.adapter_build_action_plan_world_mutation_authority
	queued.generated_build_option_status = pending.generated_build_option_status
	queued.generated_build_option_reason = pending.generated_build_option_reason
	queued.generated_candidate_id = pending.generated_candidate_id
	queued.agentic_tool_success_required =
		pending.agentic_tool_success_required
	return queued
end

local function create_build_pending_reply(name, context, message, extra)
	context = context or {}
	extra = extra or {}
	local result, plan = build_plan_for(name, context)
	local pending = remember_pending_approval(name, "build", plan, context, {
		surface_id = "builder",
		planned_node_writes = plan.metrics.planned_node_writes or 0,
		build_kind = plan.build_kind,
		build_width = plan.build_width,
		build_depth = plan.build_depth,
		build_height = plan.build_height,
		build_material_name = plan.build_material_name,
		build_material_node = plan.build_material_node,
		planner_mode = extra.planner_mode,
		selected_candidate_id = extra.selected_candidate_id,
		adapter_selected_candidate_id = extra.adapter_selected_candidate_id,
		model_selected_candidate_id = extra.model_selected_candidate_id,
		selection_source = extra.selection_source,
		intent_constraint_option_id = extra.intent_constraint_option_id,
		intent_constraint_reason = extra.intent_constraint_reason,
		candidate_options = extra.candidate_options,
		candidate_count = extra.candidate_count,
		adapter_tool_decision_source = extra.adapter_tool_decision_source,
		adapter_model_selected_candidate_id =
			extra.adapter_model_selected_candidate_id,
		adapter_initial_model_selected_candidate_id =
			extra.adapter_initial_model_selected_candidate_id,
		adapter_rejected_model_selected_candidate_id =
			extra.adapter_rejected_model_selected_candidate_id,
		adapter_agent_repair_attempted =
			extra.adapter_agent_repair_attempted,
		adapter_agent_repair_succeeded =
			extra.adapter_agent_repair_succeeded,
		adapter_agent_repair_reason =
			extra.adapter_agent_repair_reason,
		adapter_initial_missing_required_tool_calls =
			extra.adapter_initial_missing_required_tool_calls,
		adapter_required_tool_calls = extra.adapter_required_tool_calls,
		adapter_missing_required_tool_calls = extra.adapter_missing_required_tool_calls,
		adapter_required_tool_calls_satisfied =
			extra.adapter_required_tool_calls_satisfied,
		build_option_decision_source = extra.build_option_decision_source,
		adapter_memory_available = extra.adapter_memory_available,
		adapter_memory_matched_case_id = extra.adapter_memory_matched_case_id,
		adapter_memory_case_hint = extra.adapter_memory_case_hint,
		adapter_tool_trace_names = extra.adapter_tool_trace_names,
		adapter_build_action_plan_status =
			extra.adapter_build_action_plan_status,
		adapter_build_action_plan_selected_candidate_id =
			extra.adapter_build_action_plan_selected_candidate_id,
		adapter_build_action_plan_step_count =
			extra.adapter_build_action_plan_step_count,
		adapter_build_action_plan_world_mutation_authority =
			extra.adapter_build_action_plan_world_mutation_authority,
		generated_build_option_status = extra.generated_build_option_status,
		generated_build_option_reason = extra.generated_build_option_reason,
		generated_candidate_id = extra.generated_candidate_id,
		agentic_tool_success_required =
			extra.agentic_tool_success_required,
		})
	local reply = public_reply(name, "build", "pending_approval",
		message or "Build plan is pending approval before mutation.", {
			surface_id = "builder",
			approval_id = pending.approval_id,
			pending_action = "build",
			plan = plan,
			planned_node_writes = plan.metrics.planned_node_writes or 0,
			build_kind = plan.build_kind,
			build_width = plan.build_width,
			build_depth = plan.build_depth,
			build_height = plan.build_height,
			build_material_name = plan.build_material_name,
			build_material_node = plan.build_material_node,
			plan_status = result.status,
			planner_mode = extra.planner_mode,
			selected_candidate_id = extra.selected_candidate_id,
			adapter_selected_candidate_id = extra.adapter_selected_candidate_id,
			model_selected_candidate_id = extra.model_selected_candidate_id,
			selection_source = extra.selection_source,
			intent_constraint_option_id = extra.intent_constraint_option_id,
			intent_constraint_reason = extra.intent_constraint_reason,
			candidate_options = extra.candidate_options,
			candidate_count = extra.candidate_count,
			adapter_tool_decision_source = extra.adapter_tool_decision_source,
			adapter_model_selected_candidate_id =
				extra.adapter_model_selected_candidate_id,
			adapter_initial_model_selected_candidate_id =
				extra.adapter_initial_model_selected_candidate_id,
			adapter_rejected_model_selected_candidate_id =
				extra.adapter_rejected_model_selected_candidate_id,
			adapter_agent_repair_attempted =
				extra.adapter_agent_repair_attempted,
			adapter_agent_repair_succeeded =
				extra.adapter_agent_repair_succeeded,
			adapter_agent_repair_reason =
				extra.adapter_agent_repair_reason,
			adapter_initial_missing_required_tool_calls =
				extra.adapter_initial_missing_required_tool_calls,
			adapter_required_tool_calls = extra.adapter_required_tool_calls,
			adapter_missing_required_tool_calls =
				extra.adapter_missing_required_tool_calls,
			adapter_required_tool_calls_satisfied =
				extra.adapter_required_tool_calls_satisfied,
			build_option_decision_source = extra.build_option_decision_source,
			adapter_memory_available = extra.adapter_memory_available,
			adapter_memory_matched_case_id = extra.adapter_memory_matched_case_id,
			adapter_memory_case_hint = extra.adapter_memory_case_hint,
			adapter_tool_trace_names = extra.adapter_tool_trace_names,
			adapter_build_action_plan_status =
				extra.adapter_build_action_plan_status,
			adapter_build_action_plan_selected_candidate_id =
				extra.adapter_build_action_plan_selected_candidate_id,
			adapter_build_action_plan_step_count =
				extra.adapter_build_action_plan_step_count,
			adapter_build_action_plan_world_mutation_authority =
				extra.adapter_build_action_plan_world_mutation_authority,
			generated_build_option_status = extra.generated_build_option_status,
			generated_build_option_reason = extra.generated_build_option_reason,
			generated_candidate_id = extra.generated_candidate_id,
			agentic_tool_success_required =
				extra.agentic_tool_success_required,
			planner_model_status = extra.planner_model_status,
			planner_model_reason = extra.planner_model_reason,
			planner_guidance = extra.planner_guidance,
			trace_id = extra.trace_id,
			adapter_name = extra.adapter_name,
		})
	if settings.auto_apply_build_approvals == true
			and result
			and result.ok == true
			and result.status == "success"
			and plan
			and plan.will_mutate == false then
		return plugin.auto_apply_build_pending_reply(name, pending, result, plan),
			result, plan, pending
	end
	return reply, result, plan, pending
end

local function handle_build(name, context)
	local reply = create_build_pending_reply(name, context,
		"Build plan is pending approval before mutation.")
	return reply
end

local function capability_csv()
	local capabilities = {}
	for capability, enabled in pairs(settings.capabilities or {}) do
		if enabled then
			capabilities[#capabilities + 1] = capability
		end
	end
	table.sort(capabilities)
	return table.concat(capabilities, ",")
end

local function agentic_build_context(base_context, fields)
	local context = table.copy(base_context or {})
	for key, value in pairs(fields or {}) do
		context[key] = value
	end
	return context
end

local function public_candidate_option(candidate)
	return {
		option_id = candidate.option_id,
		label = candidate.label,
		reason = candidate.reason,
		build_kind = candidate.context.build_kind,
		build_width = candidate.context.build_width,
		build_depth = candidate.context.build_depth,
		build_height = candidate.context.build_height,
		build_count = candidate.context.build_count,
		build_material_name = candidate.context.build_material_name,
		build_material_node = candidate.context.build_material_node,
		planned_node_writes = candidate.planned_node_writes,
		requires_preview = true,
		requires_approval = true,
		requires_rollback = true,
		executable = true,
	}
end

local function public_candidate_options(candidates)
	local public_candidates = {}
	for _, candidate in ipairs(candidates or {}) do
		public_candidates[#public_candidates + 1] = public_candidate_option(candidate)
	end
	return public_candidates
end

local function candidate_summary(candidates)
	local parts = {}
	for _, candidate in ipairs(candidates or {}) do
		parts[#parts + 1] = string.format("%s:%s:%s:%s",
			tostring(candidate.option_id),
			tostring(candidate.build_kind),
			tostring(candidate.build_material_name or "default"),
			tostring(candidate.planned_node_writes or 0))
	end
	return table.concat(parts, "|")
end

local function append_agentic_build_candidate(candidates, name, base_context,
		option_id, label, reason, fields)
	local context = agentic_build_context(base_context, fields)
	local ok, _result, plan = pcall(build_plan_for, name, context)
	if not ok or not plan then
		return
	end
	local candidate = {
		option_id = option_id,
		label = label,
		reason = reason,
		context = context,
		planned_node_writes = plan.metrics and plan.metrics.planned_node_writes or 0,
	}
	candidates[#candidates + 1] = candidate
	return candidate
end

local function select_agentic_build_candidate(candidates, lower_prompt, parsed_candidate)
	if parsed_candidate
			and (lower_prompt:find("width", 1, true)
				or lower_prompt:find("wide", 1, true)
				or lower_prompt:find("height", 1, true)
				or lower_prompt:find("high", 1, true)
				or lower_prompt:find("tall", 1, true)
				or lower_prompt:match("%d+%s*[xX]%s*%d+")
				or lower_prompt:match("%d+%s+fires?")
				or lower_prompt:find("house", 1, true)
				or lower_prompt:find("home", 1, true)
				or lower_prompt:find("cabin", 1, true)
				or lower_prompt:find("hut", 1, true)
				or lower_prompt:find("landmark", 1, true)
				or lower_prompt:find("monument", 1, true)
				or lower_prompt:find("statue", 1, true)) then
		return parsed_candidate
	end
	local preferred = "platform"
	if lower_prompt:find("tnt", 1, true) then
		preferred = "tnt_wall"
	elseif lower_prompt:find("fire", 1, true) or lower_prompt:find("flame", 1, true) then
		preferred = "fire"
	elseif lower_prompt:find("wall", 1, true) then
		preferred = "wall"
	elseif lower_prompt:find("marker", 1, true) or lower_prompt:find("beacon", 1, true) then
		preferred = "marker"
	elseif lower_prompt:find("floor", 1, true)
			or lower_prompt:find("base", 1, true)
			or lower_prompt:find("shelter", 1, true)
			or lower_prompt:find("house", 1, true)
			or lower_prompt:find("platform", 1, true) then
		preferred = "platform"
	end
	for _, candidate in ipairs(candidates or {}) do
		if candidate.option_id == preferred then
			return candidate
		end
	end
	return candidates and candidates[1] or nil
end

local function build_context_matches_candidate(candidate, context)
	if type(candidate) ~= "table" or type(candidate.context) ~= "table"
			or type(context) ~= "table" then
		return false
	end
	local candidate_context = candidate.context
	return candidate_context.build_kind == context.build_kind
		and candidate_context.build_width == context.build_width
		and candidate_context.build_depth == context.build_depth
		and candidate_context.build_height == context.build_height
		and candidate_context.build_count == context.build_count
		and candidate_context.build_material_name == context.build_material_name
		and candidate_context.build_material_node == context.build_material_node
end

local function find_matching_agentic_build_candidate(candidates, context)
	for _, candidate in ipairs(candidates or {}) do
		if build_context_matches_candidate(candidate, context) then
			return candidate
		end
	end
	return nil
end

local function find_agentic_build_candidate(candidates, option_id)
	if type(option_id) ~= "string" or option_id == "" then
		return nil
	end
	for _, candidate in ipairs(candidates or {}) do
		if candidate.option_id == option_id then
			return candidate
		end
	end
	return nil
end

local function locked_agentic_build_candidate_id(raw_prompt, candidates)
	local lower_prompt = tostring(raw_prompt or ""):lower()
	if (lower_prompt:find("only a fire", 1, true)
			or ((lower_prompt:find("build a fire", 1, true)
					or lower_prompt:find("build me a fire", 1, true))
				and not lower_prompt:find("tnt", 1, true)
				and not lower_prompt:find("wall", 1, true)
				and not lower_prompt:find("platform", 1, true)))
			and find_agentic_build_candidate(candidates, "fire") then
		return "fire", "player_request_requires_fire_only"
	end
	if lower_prompt:find("tnt", 1, true)
			and lower_prompt:find("wall", 1, true)
			and find_agentic_build_candidate(candidates, "tnt_wall") then
		return "tnt_wall", "player_request_requires_tnt_wall"
	end
	return nil, nil
end

local GENERATED_BUILD_KINDS = {
	marker = true,
	platform = true,
	wall = true,
	fire = true,
	house = true,
	cabin = true,
	landmark = true,
}

local GENERATED_BUILD_MATERIALS = {
	["default"] = true,
	stone = true,
	tnt = true,
	fire = true,
	wood = true,
	gold = true,
	quartz = true,
	glass = true,
	diamond = true,
	glow = true,
}

local function generated_positive_int(value)
	if type(value) == "number" then
		value = math.floor(value)
		if value >= 1 then
			return value
		end
		return nil
	end
	if type(value) == "string" then
		return parse_build_positive_int(value)
	end
	return nil
end

local function generated_build_material(kind, material_name)
	if type(material_name) == "string" then
		material_name = material_name:lower()
	else
		material_name = nil
	end
	if material_name == "" then
		material_name = nil
	end
	if material_name == "default" then
		material_name = nil
	end
	if kind == "fire" then
		material_name = "fire"
	end
	if material_name and not GENERATED_BUILD_MATERIALS[material_name] then
		return nil, nil, "generated_build_material_unsupported"
	end
	if material_name == "fire" and kind ~= "fire" then
		return nil, nil, "generated_build_material_kind_mismatch"
	end
	local fallback_node = settings.marker_node
	if kind == "platform" then
		fallback_node = settings.platform_node
	elseif kind == "wall" then
		fallback_node = settings.wall_node
	elseif kind == "fire" then
		fallback_node = settings.fire_node
	elseif kind == "house" then
		fallback_node = settings.house_node
	elseif kind == "cabin" then
		fallback_node = settings.cabin_node
	elseif kind == "landmark" then
		fallback_node = settings.landmark_node
	end
	local node_name = resolve_build_material_node(material_name, fallback_node)
	if material_name and not node_name then
		return nil, nil, "generated_build_material_unavailable"
	end
	return material_name, node_name or fallback_node, nil
end

local function safe_generated_option_id(option_id)
	if type(option_id) ~= "string" then
		return "generated_agent_option"
	end
	option_id = bounded_trace_text(option_id, 64)
	if option_id:match("^generated[%w_%-]*$") then
		return option_id
	end
	return "generated_agent_option"
end

local function append_generated_agentic_build_candidate(candidates, name,
		base_context, option)
	if type(option) ~= "table" then
		return nil, "generated_build_option_missing"
	end
	local kind = option.build_kind or option.kind
	if type(kind) ~= "string" then
		return nil, "generated_build_kind_missing"
	end
	kind = kind:lower()
	if not GENERATED_BUILD_KINDS[kind] then
		return nil, "generated_build_kind_unsupported"
	end
	local material_name, material_node, material_reason =
		generated_build_material(kind,
			option.build_material_name or option.material_name or option.material)
	if material_reason then
		return nil, material_reason
	end
	local fields = {
		build_kind = kind,
		build_material_name = material_name,
		build_material_node = material_node,
	}
	if kind == "platform" then
		local width = generated_positive_int(option.build_width or option.width)
		local depth = generated_positive_int(option.build_depth or option.depth)
		if not width or not depth then
			return nil, "generated_build_dimensions_missing"
		end
		if width * depth > settings.max_lights then
			return nil, "generated_build_shape_out_of_bounds"
		end
		fields.build_width = width
		fields.build_depth = depth
	elseif kind == "wall" then
		local width = generated_positive_int(option.build_width or option.width)
		local height = generated_positive_int(option.build_height or option.height)
		if not width or not height then
			return nil, "generated_build_dimensions_missing"
		end
		if width * height > settings.max_lights then
			return nil, "generated_build_shape_out_of_bounds"
		end
		fields.build_width = width
		fields.build_height = height
	elseif kind == "fire" then
		local count = generated_positive_int(option.build_count or option.count or 1)
		if not count then
			return nil, "generated_build_dimensions_missing"
		end
		if count > settings.max_lights then
			return nil, "generated_build_shape_out_of_bounds"
		end
		fields.build_count = count
	elseif kind == "house" or kind == "cabin" then
		local width = generated_positive_int(option.build_width or option.width)
		local depth = generated_positive_int(option.build_depth or option.depth)
		local height = generated_positive_int(option.build_height or option.height)
		if not width or not depth or not height then
			return nil, "generated_build_dimensions_missing"
		end
		if plugin._bounded_shell_writes(width, depth, height, settings.max_lights)
				> settings.max_lights then
			return nil, "generated_build_shape_out_of_bounds"
		end
		fields.build_width = width
		fields.build_depth = depth
		fields.build_height = height
	elseif kind == "landmark" then
		local width = generated_positive_int(option.build_width or option.width)
		local depth = generated_positive_int(option.build_depth or option.depth)
		local height = generated_positive_int(option.build_height or option.height)
		if not width or not depth or not height then
			return nil, "generated_build_dimensions_missing"
		end
		if plugin._bounded_landmark_writes(width, depth, height, settings.max_lights)
				> settings.max_lights then
			return nil, "generated_build_shape_out_of_bounds"
		end
		fields.build_width = width
		fields.build_depth = depth
		fields.build_height = height
	end
	local candidate = append_agentic_build_candidate(candidates, name, base_context,
		safe_generated_option_id(option.option_id),
		bounded_trace_text(option.label or "Generated build option", 120),
		bounded_trace_text(option.reason or "agent-proposed bounded option", 240),
		fields)
	if not candidate then
		return nil, "generated_build_plan_rejected"
	end
	return candidate, "validated"
end

local function adapter_selected_agentic_candidate_id_from_model_result(model_result)
	if type(model_result) ~= "table" or model_result.status ~= "success" then
		return nil
	end
	local response = model_result.response
	if type(response) ~= "table" then
		return nil
	end
	if type(response.selected_option_id) == "string" then
		return response.selected_option_id
	end
	local tool_decisions = response.tool_decisions
	if type(tool_decisions) ~= "table" then
		return nil
	end
	local build_option = tool_decisions.build_option
	if type(build_option) == "table" and type(build_option.selected_option_id) == "string" then
		return build_option.selected_option_id
	end
	return nil
end

local function model_selected_agentic_candidate_id_from_model_result(model_result)
	if type(model_result) ~= "table" or model_result.status ~= "success" then
		return nil
	end
	local response = model_result.response
	if type(response) ~= "table" then
		return nil
	end
	if type(response.model_selected_option_id) == "string" then
		return response.model_selected_option_id
	end
	if type(response.rejected_model_selected_option_id) == "string" then
		return response.rejected_model_selected_option_id
	end
	return adapter_selected_agentic_candidate_id_from_model_result(model_result)
end

local function agentic_model_response(model_result)
	if type(model_result) ~= "table" or type(model_result.response) ~= "table" then
		return nil
	end
	return model_result.response
end

local function agentic_build_option_decision(response)
	if type(response) ~= "table" or type(response.tool_decisions) ~= "table" then
		return nil
	end
	local build_option = response.tool_decisions.build_option
	if type(build_option) ~= "table" then
		return nil
	end
	return build_option
end

local function generated_build_option(response)
	if type(response) ~= "table" then
		return nil
	end
	if type(response.generated_build_option) == "table" then
		return response.generated_build_option
	end
	local build_option = agentic_build_option_decision(response)
	if type(build_option) == "table" and type(build_option.generated_option) == "table" then
		return build_option.generated_option
	end
	return nil
end

local function agentic_tool_trace_names(response)
	local names = {}
	if type(response) ~= "table" or type(response.tool_trace) ~= "table" then
		return names
	end
	for _, entry in ipairs(response.tool_trace) do
		if type(entry) == "table" and type(entry.tool_name) == "string" then
			names[#names + 1] = bounded_trace_text(entry.tool_name, 80)
			if #names >= 8 then
				break
			end
		end
	end
	return names
end

local function agentic_build_planner_adapter_metadata(model_result)
	local response = agentic_model_response(model_result)
	if not response then
		return {}
	end
	local build_option = agentic_build_option_decision(response) or {}
	local build_action_plan = {}
	if type(response.build_action_plan) == "table" then
		build_action_plan = response.build_action_plan
	elseif type(response.tool_decisions) == "table"
			and type(response.tool_decisions.build_action_plan) == "table" then
		build_action_plan = response.tool_decisions.build_action_plan
	end
	local memory_match = type(build_option.memory_match) == "table"
		and build_option.memory_match or {}
	local missing_required = type(response.missing_required_tool_calls) == "table"
		and table.copy(response.missing_required_tool_calls) or nil
	local required = type(response.required_tool_calls) == "table"
		and table.copy(response.required_tool_calls) or nil
	return {
		adapter_tool_decision_source = response.tool_decision_source,
		adapter_selected_candidate_id = response.selected_option_id,
		adapter_model_selected_candidate_id = response.model_selected_option_id,
		adapter_initial_model_selected_candidate_id =
			response.initial_model_selected_option_id,
		adapter_rejected_model_selected_candidate_id =
			response.rejected_model_selected_option_id,
		adapter_intent_constraint_option_id =
			response.intent_constraint_option_id,
		adapter_intent_constraint_reason =
			response.intent_constraint_reason,
		adapter_agent_repair_attempted = response.agent_repair_attempted,
		adapter_agent_repair_succeeded = response.agent_repair_succeeded,
		adapter_agent_repair_reason = response.agent_repair_reason,
		adapter_initial_missing_required_tool_calls =
			type(response.initial_missing_required_tool_calls) == "table"
				and table.copy(response.initial_missing_required_tool_calls)
				or nil,
		adapter_required_tool_calls = required,
		adapter_missing_required_tool_calls = missing_required,
		adapter_required_tool_calls_satisfied =
			response.required_tool_calls_satisfied,
		build_option_decision_source = build_option.decision_source,
		adapter_memory_available = memory_match.memory_available,
		adapter_memory_matched_case_id = memory_match.matched_case_id,
		adapter_memory_case_hint = memory_match.case_hint,
		adapter_tool_trace_names = agentic_tool_trace_names(response),
		adapter_build_action_plan_status = build_action_plan.status,
		adapter_build_action_plan_selected_candidate_id =
			build_action_plan.selected_option_id,
		adapter_build_action_plan_step_count = build_action_plan.step_count,
		adapter_build_action_plan_world_mutation_authority =
			build_action_plan.world_mutation_authority,
	}
end

local function build_agentic_candidate_options(name, raw_prompt, context)
	local lower = raw_prompt:lower()
	local candidates = {}
	local parsed_context = parse_build_options(raw_prompt, context)
	append_agentic_build_candidate(candidates, name, context, "platform",
		"Small platform", "safe default buildable surface", {
			build_kind = "platform",
			build_width = 2,
			build_depth = 2,
			build_material_name = nil,
			build_material_node = settings.platform_node,
		})
	append_agentic_build_candidate(candidates, name, context, "marker",
		"Marker block", "single-block visible marker", {
			build_kind = "marker",
			build_material_name = nil,
			build_material_node = settings.marker_node,
		})
	append_agentic_build_candidate(candidates, name, context, "wall",
		"Small wall", "bounded wall preview", {
			build_kind = "wall",
			build_width = 4,
			build_height = 3,
			build_material_name = nil,
			build_material_node = settings.wall_node,
		})
	local fire_node = resolve_build_material_node("fire", settings.fire_node)
	if fire_node then
		append_agentic_build_candidate(candidates, name, context, "fire",
			"Single fire", "requested as approval-gated game build", {
				build_kind = "fire",
				build_count = 1,
				build_material_name = "fire",
				build_material_node = fire_node,
			})
	end
	local tnt_node = resolve_build_material_node("tnt", settings.tnt_node)
	if tnt_node and lower:find("tnt", 1, true) then
		append_agentic_build_candidate(candidates, name, context, "tnt_wall",
			"Small TNT wall", "requested game material behind approval and rollback", {
				build_kind = "wall",
				build_width = 4,
				build_height = 3,
				build_material_name = "tnt",
				build_material_node = tnt_node,
			})
	end
	local parsed_candidate = find_matching_agentic_build_candidate(candidates, parsed_context)
	if parsed_context and not parsed_candidate then
		parsed_candidate = append_agentic_build_candidate(candidates, name, context,
			"parsed_request", "Parsed player request",
			"exact bounded command parsed from the player request",
			parsed_context)
	end
	local public_candidates = public_candidate_options(candidates)
	return candidates, public_candidates,
		select_agentic_build_candidate(candidates, lower, parsed_candidate)
end

local function agentic_build_planner_prompt(raw_prompt, public_candidates)
	local lines = {
		"Plan a Luanti build request using listed executable options or one bounded generated option.",
		"Luanti will enforce capabilities, approval, rollback, and world mutation.",
		"Player request: " .. bounded_trace_text(raw_prompt, 500),
		"Options:",
	}
	for _, candidate in ipairs(public_candidates or {}) do
		lines[#lines + 1] = string.format(
			"- %s: %s kind=%s material=%s planned_writes=%s",
			tostring(candidate.option_id),
			tostring(candidate.label),
			tostring(candidate.build_kind),
			tostring(candidate.build_material_name or candidate.build_material_node or "default"),
			tostring(candidate.planned_node_writes or 0))
	end
	lines[#lines + 1] =
		"Return concise public guidance and name the option id to preview; generated options must be returned through the build-option tool contract for Luanti validation."
	return table.concat(lines, "\n")
end

local function handle_agentic_build_planner(name, raw_prompt, context, reason)
	context = context or {}
	local candidates, public_candidates, selected =
		build_agentic_candidate_options(name, raw_prompt, context)
	if not selected then
		return public_reply(name, "build_plan", "blocked",
			"No executable build options are available for this request.", {
				surface_id = "builder",
				reason = "no_build_candidates",
			})
	end
	local adapter_name = "ai_agent_plugin.build_planner"
	local planner_context = {
		surface_id = "builder",
		intent = "build_planning",
		planner_reason = reason or "ambiguous_build_intent",
		input_surface = context.input_surface,
		natural_chat_alias = context.natural_chat_alias,
		player_turn_source = context.player_turn_source,
		capabilities = capability_csv(),
		candidate_count = #public_candidates,
		selected_candidate_id = selected.option_id,
		player_request = raw_prompt,
		candidate_summary = candidate_summary(public_candidates),
	}
	local trace = start_request_trace(name, "build",
		model_adapter_async and "agentic_build_planner"
			or "deterministic_build_candidate_fallback",
		raw_prompt, planner_context, {
			surface_id = "builder",
			agent_id = agent_id_for(name),
			adapter_name = adapter_name,
			observation_context = context,
			player_turn_text = context.player_turn_text or raw_prompt,
			player_turn_source = context.player_turn_source,
		})
	planner_context.player_agent_loop =
		plugin._player_loop.public_context_json(name)
	trace.context = compact_trace_context(planner_context)
	local function finish_with_pending(model_result, planner_mode)
		model_result = model_result or {}
		local adapter_metadata = agentic_build_planner_adapter_metadata(model_result)
		local response = agentic_model_response(model_result)
		local generated_option_status
		local generated_option_reason
		local generated_candidate_id
		local proposed_generated = generated_build_option(response)
		if proposed_generated then
			local generated_candidate, generated_reason =
				append_generated_agentic_build_candidate(candidates, name,
					context, proposed_generated)
			if generated_candidate then
				generated_option_status = "validated"
				generated_option_reason = "validated_by_luanti_build_planner"
				generated_candidate_id = generated_candidate.option_id
				public_candidates = public_candidate_options(candidates)
			else
				generated_option_status = "rejected"
				generated_option_reason = generated_reason
			end
		end
		local adapter_selected_id =
			adapter_selected_agentic_candidate_id_from_model_result(model_result)
		local model_selected_id =
			model_selected_agentic_candidate_id_from_model_result(model_result)
		local locked_candidate_id, locked_candidate_reason =
			locked_agentic_build_candidate_id(raw_prompt, candidates)
		local final_selected = find_agentic_build_candidate(candidates, adapter_selected_id)
			or find_agentic_build_candidate(candidates, model_selected_id)
			or selected
		local selection_source = "deterministic_preselection"
		if final_selected.option_id == adapter_selected_id
				and adapter_selected_id == model_selected_id then
			selection_source = "model_tool_decision"
		elseif final_selected.option_id == adapter_selected_id then
			selection_source =
				adapter_metadata.adapter_tool_decision_source
				or "adapter_selected_candidate"
		elseif generated_option_status == "rejected" then
			selection_source = "generated_option_rejected_fallback"
		elseif model_selected_id then
			selection_source = "model_tool_decision_rejected_fallback"
		end
		if locked_candidate_id and model_selected_id ~= locked_candidate_id then
			local locked_candidate =
				find_agentic_build_candidate(candidates, locked_candidate_id)
			if locked_candidate then
				final_selected = locked_candidate
				selection_source = model_selected_id
					and "model_tool_decision_rejected_intent_constraint"
					or "intent_constraint_preselection"
			end
		end
		local agentic_tool_success_required =
			final_selected.option_id == "parsed_request"
				or generated_option_status == "validated"
		if planner_mode == "agentic_model_adapter_fallback"
				and agentic_tool_success_required then
			local fallback_blocked_reason = "agentic_build_planner_failed"
			if model_result.timeout == true
					or model_result.status == "timeout"
					or model_result.reason == "sidecar_timeout"
					or model_result.reason == "timeout" then
				fallback_blocked_reason = "agentic_build_planner_timeout"
			end
			local blocked_reply = public_reply(name, "build_plan", "blocked",
				"Agentic build planner did not complete; custom builds require a successful tool-validated agent plan before mutation.", {
					surface_id = "builder",
					reason = fallback_blocked_reason,
					planner_mode = planner_mode,
					selected_candidate_id = final_selected.option_id,
					adapter_selected_candidate_id = adapter_selected_id,
					model_selected_candidate_id = model_selected_id,
					selection_source = selection_source,
					intent_constraint_option_id = locked_candidate_id,
					intent_constraint_reason = locked_candidate_reason,
					candidate_options = public_candidates,
					candidate_count = #public_candidates,
					planner_model_status = model_result.status,
					planner_model_reason = model_result.reason,
					planner_guidance = bounded_trace_text(model_result.message, 1000),
					agentic_tool_success_required = true,
					agentic_planner_fallback_blocked = true,
					fallback_blocked_reason = fallback_blocked_reason,
					adapter_name = model_result.adapter_name or adapter_name,
					trace_id = trace.trace_id,
				})
			return finish_request_trace(trace, blocked_reply, {
				planner_mode = planner_mode,
				selected_candidate_id = final_selected.option_id,
				adapter_selected_candidate_id = adapter_selected_id,
				model_selected_candidate_id = model_selected_id,
				selection_source = selection_source,
				intent_constraint_option_id = locked_candidate_id,
				intent_constraint_reason = locked_candidate_reason,
				candidate_count = #public_candidates,
				adapter_name = model_result.adapter_name or adapter_name,
				planner_model_status = model_result.status,
				planner_model_reason = model_result.reason,
				agentic_tool_success_required = true,
				agentic_planner_fallback_blocked = true,
				fallback_blocked_reason = fallback_blocked_reason,
			})
		end
		local pending_reply = create_build_pending_reply(name, final_selected.context,
			"Agentic build planner selected an approval-gated build option.", {
				planner_mode = planner_mode,
				selected_candidate_id = final_selected.option_id,
				adapter_selected_candidate_id = adapter_selected_id,
				model_selected_candidate_id = model_selected_id,
				selection_source = selection_source,
				intent_constraint_option_id = locked_candidate_id,
				intent_constraint_reason = locked_candidate_reason,
				candidate_options = public_candidates,
				candidate_count = #public_candidates,
				planner_model_status = model_result.status,
				planner_model_reason = model_result.reason,
				planner_guidance = bounded_trace_text(model_result.message, 1000),
				adapter_tool_decision_source =
					adapter_metadata.adapter_tool_decision_source,
				adapter_model_selected_candidate_id =
					adapter_metadata.adapter_model_selected_candidate_id,
				adapter_initial_model_selected_candidate_id =
					adapter_metadata.adapter_initial_model_selected_candidate_id,
				adapter_rejected_model_selected_candidate_id =
					adapter_metadata.adapter_rejected_model_selected_candidate_id,
				adapter_agent_repair_attempted =
					adapter_metadata.adapter_agent_repair_attempted,
				adapter_agent_repair_succeeded =
					adapter_metadata.adapter_agent_repair_succeeded,
				adapter_agent_repair_reason =
					adapter_metadata.adapter_agent_repair_reason,
				adapter_initial_missing_required_tool_calls =
					adapter_metadata.adapter_initial_missing_required_tool_calls,
				adapter_required_tool_calls =
					adapter_metadata.adapter_required_tool_calls,
				adapter_missing_required_tool_calls =
					adapter_metadata.adapter_missing_required_tool_calls,
				adapter_required_tool_calls_satisfied =
					adapter_metadata.adapter_required_tool_calls_satisfied,
					build_option_decision_source =
						adapter_metadata.build_option_decision_source,
					adapter_memory_available =
						adapter_metadata.adapter_memory_available,
					adapter_memory_matched_case_id =
						adapter_metadata.adapter_memory_matched_case_id,
					adapter_memory_case_hint =
						adapter_metadata.adapter_memory_case_hint,
					adapter_tool_trace_names =
						adapter_metadata.adapter_tool_trace_names,
					adapter_build_action_plan_status =
						adapter_metadata.adapter_build_action_plan_status,
					adapter_build_action_plan_selected_candidate_id =
						adapter_metadata.adapter_build_action_plan_selected_candidate_id,
					adapter_build_action_plan_step_count =
						adapter_metadata.adapter_build_action_plan_step_count,
					adapter_build_action_plan_world_mutation_authority =
						adapter_metadata.adapter_build_action_plan_world_mutation_authority,
					generated_build_option_status = generated_option_status,
					generated_build_option_reason = generated_option_reason,
					generated_candidate_id = generated_candidate_id,
					agentic_tool_success_required = agentic_tool_success_required,
					trace_id = trace.trace_id,
				adapter_name = model_result.adapter_name or adapter_name,
		})
		return finish_request_trace(trace, pending_reply, {
			planner_mode = planner_mode,
			selected_candidate_id = final_selected.option_id,
			adapter_selected_candidate_id = adapter_selected_id,
			model_selected_candidate_id = model_selected_id,
			selection_source = selection_source,
			intent_constraint_option_id = locked_candidate_id,
			intent_constraint_reason = locked_candidate_reason,
			candidate_count = #public_candidates,
			adapter_name = model_result.adapter_name or adapter_name,
			adapter_tool_decision_source =
				adapter_metadata.adapter_tool_decision_source,
			adapter_model_selected_candidate_id =
				adapter_metadata.adapter_model_selected_candidate_id,
			adapter_initial_model_selected_candidate_id =
				adapter_metadata.adapter_initial_model_selected_candidate_id,
			adapter_rejected_model_selected_candidate_id =
				adapter_metadata.adapter_rejected_model_selected_candidate_id,
			adapter_agent_repair_attempted =
				adapter_metadata.adapter_agent_repair_attempted,
			adapter_agent_repair_succeeded =
				adapter_metadata.adapter_agent_repair_succeeded,
			adapter_agent_repair_reason =
				adapter_metadata.adapter_agent_repair_reason,
			adapter_initial_missing_required_tool_calls =
				adapter_metadata.adapter_initial_missing_required_tool_calls,
			adapter_required_tool_calls =
				adapter_metadata.adapter_required_tool_calls,
			adapter_missing_required_tool_calls =
				adapter_metadata.adapter_missing_required_tool_calls,
			adapter_required_tool_calls_satisfied =
				adapter_metadata.adapter_required_tool_calls_satisfied,
				build_option_decision_source =
					adapter_metadata.build_option_decision_source,
				adapter_memory_available =
					adapter_metadata.adapter_memory_available,
				adapter_memory_matched_case_id =
					adapter_metadata.adapter_memory_matched_case_id,
				adapter_memory_case_hint =
					adapter_metadata.adapter_memory_case_hint,
				adapter_tool_trace_names =
					adapter_metadata.adapter_tool_trace_names,
				adapter_build_action_plan_status =
					adapter_metadata.adapter_build_action_plan_status,
				adapter_build_action_plan_selected_candidate_id =
					adapter_metadata.adapter_build_action_plan_selected_candidate_id,
				adapter_build_action_plan_step_count =
					adapter_metadata.adapter_build_action_plan_step_count,
				adapter_build_action_plan_world_mutation_authority =
					adapter_metadata.adapter_build_action_plan_world_mutation_authority,
				generated_build_option_status = generated_option_status,
				generated_build_option_reason = generated_option_reason,
				generated_candidate_id = generated_candidate_id,
			})
	end
	if not model_adapter_async or not core.ai_model_ops or not core.ai_model_ops.request_async then
		return finish_with_pending({
			status = "skipped",
			reason = "model_adapter_async_unavailable",
			message = "No async model adapter configured; using bounded build candidates.",
			adapter_name = adapter_name,
		}, "deterministic_candidate_fallback")
	end
	local completed = false
	local returned_to_player = false
	local completed_reply
	local function complete_agentic_planner(result)
		local planner_mode = result and result.status == "success"
			and "agentic_model_adapter" or "agentic_model_adapter_fallback"
		completed = true
		completed_reply = finish_with_pending(result, planner_mode)
		if type(context.on_agentic_build_planner_complete) == "function" then
			local callback_ok, callback_err = pcall(context.on_agentic_build_planner_complete,
				completed_reply, trace)
			if not callback_ok then
				core.log("error", "[ai_agent_plugin] build planner completion callback failed: "
					.. tostring(callback_err))
			end
		end
		if returned_to_player and core.chat_send_player then
			local completed_text = context.natural_chat
				and plugin.format_player_reply(completed_reply)
				or plugin.format_reply(completed_reply)
			if context.natural_chat then
				plugin._player_loop.append_turn(name, "assistant",
					completed_text, completed_reply.surface_id, "natural_chat")
			end
			core.chat_send_player(name, completed_text)
		end
	end
	local queued, queue_reason = core.ai_model_ops.request_async(
		agentic_build_planner_prompt(raw_prompt, public_candidates), {
			agent_id = agent_id_for(name),
			owner = name,
			task_id = "ai-agent-build-planner:" .. tostring(trace.trace_id),
			adapter_async = model_adapter_async,
			adapter_name = adapter_name,
			context = planner_context,
			max_context_keys = 24,
		}, complete_agentic_planner)
	if not queued then
		return finish_with_pending({
			status = "blocked",
			reason = queue_reason or "model_adapter_queue_failed",
			message = "Model-backed build planning was unavailable; using bounded build candidates.",
			adapter_name = adapter_name,
		}, "agentic_model_adapter_fallback")
	end
	if completed then
		return completed_reply
	end
	local queued_reply = public_reply(name, "build_plan", "queued",
		"Agentic build planner request queued.", {
			surface_id = "builder",
			reason = "agentic_build_planner_queued",
			trace_id = trace.trace_id,
			adapter_name = adapter_name,
			planner_mode = "agentic_model_adapter",
			selected_candidate_id = selected.option_id,
			candidate_options = public_candidates,
			candidate_count = #public_candidates,
		})
	trace.response = {
		ok = true,
		status = "queued",
		action = "build_plan",
		reason = "agentic_build_planner_queued",
		message = "Agentic build planner request queued.",
		trace_id = trace.trace_id,
		planner_mode = "agentic_model_adapter",
		selected_candidate_id = selected.option_id,
		candidate_count = #public_candidates,
	}
	log_request_trace(trace, "queued")
	returned_to_player = true
	return queued_reply
end

local function agentic_build_planner_available()
	return settings.agentic_build_planner_first == true
		and model_adapter_async ~= nil
		and core.ai_model_ops ~= nil
		and core.ai_model_ops.request_async ~= nil
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

local function parse_bounded_int(raw_value)
	if type(raw_value) ~= "string" or raw_value == "" then
		return nil
	end
	local number = tonumber(raw_value)
	if not number then
		return nil
	end
	number = math.floor(number)
	if number < 0 then
		return nil
	end
	return number
end

local function repair_radius_for(context)
	context = context or {}
	if context.repair_radius ~= nil then
		return math.floor(context.repair_radius)
	end
	return 0
end

local function repair_sample_limit_for(context)
	context = context or {}
	if context.sample_limit ~= nil then
		return math.floor(context.sample_limit)
	end
	return settings.max_lights
end

local function parse_repair_options(raw_prompt, context)
	local parsed = table.copy(context or {})
	local radius_text = raw_prompt:match("[Rr][Aa][Dd][Ii][Uu][Ss]%s+([%-%d]+)")
		or raw_prompt:match("[Rr][Aa][Nn][Gg][Ee]%s+([%-%d]+)")
	if radius_text then
		local radius = parse_bounded_int(radius_text)
		if not radius then
			return nil, "invalid_repair_radius"
		end
		if radius > settings.max_repair_radius then
			return nil, "repair_radius_out_of_bounds"
		end
		parsed.repair_radius = radius
	end
	local sample_text = raw_prompt:match("[Ss][Aa][Mm][Pp][Ll][Ee][Ss]?%s+([%-%d]+)")
		or raw_prompt:match("[Ll][Ii][Mm][Ii][Tt]%s+([%-%d]+)")
	if sample_text then
		local sample_limit = parse_bounded_int(sample_text)
		if not sample_limit then
			return nil, "invalid_repair_sample_limit"
		end
		if sample_limit > settings.max_lights then
			return nil, "repair_sample_limit_out_of_bounds"
		end
		parsed.sample_limit = sample_limit
	end
	return parsed, nil
end

local function parse_repair_edit_options(raw_prompt, context)
	local has_repair_edit = raw_prompt:match("[Rr][Aa][Dd][Ii][Uu][Ss]%s+([%-%d]+)")
		or raw_prompt:match("[Rr][Aa][Nn][Gg][Ee]%s+([%-%d]+)")
		or raw_prompt:match("[Ss][Aa][Mm][Pp][Ll][Ee][Ss]?%s+([%-%d]+)")
		or raw_prompt:match("[Ll][Ii][Mm][Ii][Tt]%s+([%-%d]+)")
	if not has_repair_edit then
		return nil, "no_plan_edit_parameters"
	end
	return parse_repair_options(raw_prompt, context)
end

local function handle_repair_plan(name, context)
	context = context or {}
	configure_product_surfaces()
	local agent_id = surface_agent_id_for(name, "repair")
	plugin.ensure_surface_agent(name, "repair")
	local repair_radius = repair_radius_for(context)
	local sample_limit = repair_sample_limit_for(context)
	local plan = core.repair_agent.plan_area(default_pos(context), {
		agent_id = agent_id,
		owner = name,
		task_id = context.task_id,
		radius = repair_radius,
		repair_nodes = settings.repair_nodes,
		get_node = context.get_node,
		sample_limit = sample_limit,
	})
	local compact = compact_repair_plan(plan)
	compact.repair_radius = repair_radius
	compact.sample_limit = sample_limit
	return public_reply(name, "repair_plan", plan.status, "Repair plan returned without mutation.", {
		surface_id = "repair",
		plan = compact,
		candidate_count = compact.candidate_count,
		repair_radius = repair_radius,
		sample_limit = sample_limit,
	})
end

local function queue_repair_task(name, context, plan)
	context = context or {}
	configure_product_surfaces()
	local pos = default_pos(context)
	local task_id = next_task_id(name, "repair")
	local agent_id = surface_agent_id_for(name, "repair")
	plugin.ensure_surface_agent(name, "repair")
	local repair_radius = repair_radius_for(context)
	local sample_limit = repair_sample_limit_for(context)
	plan = plan or core.repair_agent.plan_area(pos, {
		agent_id = agent_id,
		owner = name,
		task_id = task_id .. ":plan",
		radius = repair_radius,
		repair_nodes = settings.repair_nodes,
		get_node = context.get_node,
		sample_limit = sample_limit,
	})
	local max_repair_writes = context.max_node_writes_per_step
		or math.min(#(plan.candidates or {}), settings.max_lights)
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
		max_node_writes_per_step = max_repair_writes,
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
		repair_radius = repair_radius,
		sample_limit = sample_limit,
	})
end

local function handle_repair(name, context)
	context = context or {}
	configure_product_surfaces()
	local approval_id = next_approval_id(name, "repair")
	local agent_id = surface_agent_id_for(name, "repair")
	plugin.ensure_surface_agent(name, "repair")
	local repair_radius = repair_radius_for(context)
	local sample_limit = repair_sample_limit_for(context)
	local plan = core.repair_agent.plan_area(default_pos(context), {
		agent_id = agent_id,
		owner = name,
		task_id = approval_id .. ":plan",
		radius = repair_radius,
		repair_nodes = settings.repair_nodes,
		get_node = context.get_node,
		sample_limit = sample_limit,
	})
	local compact = compact_repair_plan(plan)
	compact.repair_radius = repair_radius
	compact.sample_limit = sample_limit
	local pending = {
		approval_id = approval_id,
		surface_id = "repair",
		action = "repair",
		plan = compact,
		raw_plan = plan,
		context = approval_context(context),
		candidate_count = compact.candidate_count,
		repair_radius = repair_radius,
		sample_limit = sample_limit,
	}
	player_pending_approvals[name] = pending
	return public_reply(name, "repair", "pending_approval",
		"Repair plan is pending approval before mutation.", {
			surface_id = "repair",
			approval_id = pending.approval_id,
			pending_action = "repair",
			plan = compact,
			candidate_count = compact.candidate_count,
			repair_radius = repair_radius,
			sample_limit = sample_limit,
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
	if not surface_required_capabilities_granted(product_surface("importer")) then
		return surface_gated_reply(name, "importer", "import_plan")
	end
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

local function audit_record_matches_filter(record, filter)
	if type(filter) ~= "table" then
		return true
	end
	if filter.task_id and record.task_id ~= filter.task_id then
		return false
	end
	if filter.rollback_record_id
			and record.rollback_record_id ~= filter.rollback_record_id then
		return false
	end
	return true
end

local function audit_events_for(name, limit, filter)
	local agent_ids = {
		[agent_id_for(name)] = true,
	}
	for _, surface_id in ipairs(PRODUCT_SURFACE_ORDER) do
		agent_ids[surface_agent_id_for(name, surface_id)] = true
	end
	local events = {}
	for _, record in ipairs(core.get_ai_runtime_audit({ limit = limit or 25 })) do
		if agent_ids[record.agent_id] and audit_record_matches_filter(record, filter) then
			events[#events + 1] = compact_audit_record(record)
		end
	end
	return events
end

local function rollback_records_for(name, limit, filter)
	local records = {}
	for _, record in ipairs(audit_events_for(name, limit, filter)) do
		if record.event_type == "rollback.record" and record.rollback_record_id then
			records[#records + 1] = record
		end
	end
	return records
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
			"help",
			"commands",
			"last",
			"last command",
			"diagnostics",
			"tasks",
			"task <task_id>",
			"traces",
			"feedback last",
			"feedback fire",
			"feedback tnt wall",
			"wrong <expected build>",
			"teach <expected build>",
			"pending plan",
			"edit plan",
			"edit plan platform width N depth N",
			"edit plan radius N",
			"discard plan",
			"cancel plan",
			"cancel approval",
			"no",
			"cancel",
			"cancel <task_id>",
			"stay",
			"wait",
			"approve",
			"approve <approval_id>",
			"follow",
			"follow N",
			"come",
			"light",
			"build plan",
			"build marker",
			"build platform width N depth N",
			"build fire",
			"build wall width N height N",
			"build wall of tnt",
			"repair plan",
			"repair radius N",
			"repair",
			"defend",
			"import plan",
			"audit",
			"audit <task_id>",
			"rollback",
			"rollback <task_id|rollback_id>",
		},
		navigation_contract = plugin.get_navigation_contract(),
		tasks = active_player_tasks(name),
		pending_approval = compact_pending_approval(player_pending_approvals[name]),
	})
end

local function handle_status(name)
	local tasks = active_player_tasks(name)
	return public_reply(name, "status", "success", "Nova agent status returned.", {
		state = plugin.get_player_state(name),
		metrics = core.get_ai_runtime_metrics(),
		product_surfaces = plugin.get_product_surfaces(name),
		tasks = tasks,
		known_task_count = #tasks,
		pending_approval = compact_pending_approval(player_pending_approvals[name]),
		navigation_contract = plugin.get_navigation_contract(),
	})
end

local function handle_audit(name, requested_task_id)
	plugin.ensure_surface_agent(name, "guide")
	local filter
	local target_kind
	local target_id
	if requested_task_id then
		local task, canonical_task_id = player_task_by_id(name, requested_task_id)
		if not task then
			return public_reply(name, "audit", "blocked",
				"Requested task was not found for this player.", {
					surface_id = "guide",
					reason = "task_not_found_or_not_owned",
					task_id = canonical_task_id,
					target_kind = "task",
					target_id = canonical_task_id,
					audit_events = {},
				})
		end
		filter = { task_id = task.task_id }
		target_kind = "task"
		target_id = task.task_id
	end
	return public_reply(name, "audit", "success", "Recent agent audit events returned.", {
		surface_id = "guide",
		task_id = target_kind == "task" and target_id or nil,
		target_kind = target_kind,
		target_id = target_id,
		audit_events = audit_events_for(name, 50, filter),
	})
end

local function handle_request_traces(name)
	plugin.ensure_surface_agent(name, "guide")
	return public_reply(name, "request_traces", "success", "Recent Nova request traces returned.", {
		surface_id = "guide",
		trace_scope = "player",
		traces = plugin.player_request_traces(name, { limit = 25 }),
		latest_diagnostic = plugin.get_last_command_diagnostic(name),
	})
end

function plugin.latest_player_request_trace(name)
	local traces = plugin.player_request_traces(name, { limit = 1 })
	return traces[1]
end

function plugin.compact_task_outcome(task)
	if type(task) ~= "table" then
		return nil
	end
	local result = type(task.last_result) == "table" and task.last_result or {}
	local metrics = type(result.metrics) == "table" and result.metrics or {}
	return {
		task_id = task.task_id,
		task_status = task.status,
		task_result_status = result.status,
		task_result_reason = result.reason,
		operation = result.operation,
		changed = result.changed,
		examined = result.examined,
		skipped = result.skipped,
		actual_node_writes = metrics.node_writes or result.changed,
		rollback_record_id = result.rollback_record_id,
		rollback_storage_ref = result.rollback_storage_ref,
		mapblock_churn = metrics.mapblock_churn,
	}
end

function plugin.command_eval_review(trace, response)
	local missing_tools = response.adapter_missing_required_tool_calls
		or trace.adapter_missing_required_tool_calls
	local ready_for_adapter_contract_eval =
		type(missing_tools) == "table" and #missing_tools > 0
	local ready_for_prompt_eval = type(trace.public_prompt) == "string"
		and trace.public_prompt ~= ""
		and response.action == "build"
		and type(response.build_kind) == "string"
		and type(response.planned_node_writes) == "number"
	return {
		source_kind = "nova_request_trace",
		request_trace_logged = true,
		agents_sdk_sidecar_log_expected =
			response.planner_mode == "agentic_model_adapter",
		ready_for_prompt_eval = ready_for_prompt_eval,
		ready_for_adapter_contract_eval = ready_for_adapter_contract_eval,
		memory_refresh_required = ready_for_prompt_eval
			or ready_for_adapter_contract_eval,
		candidate_review_status =
			ready_for_prompt_eval and "candidate_ready" or "needs_operator_label",
	}
end

function plugin.get_last_command_diagnostic(name)
	name = normalize_player_name(name)
	local trace = plugin.latest_player_request_trace(name)
	if not trace then
		return nil
	end
	local response = type(trace.response) == "table" and trace.response or {}
	local task = response.task_id and core.get_ai_task(response.task_id) or nil
	local task_outcome = plugin.compact_task_outcome(task) or {}
	local required_tools_satisfied = response.adapter_required_tool_calls_satisfied
	if required_tools_satisfied == nil then
		required_tools_satisfied = trace.adapter_required_tool_calls_satisfied
	end
	local memory_available = response.adapter_memory_available
	if memory_available == nil then
		memory_available = trace.adapter_memory_available
	end
	local repair_attempted = response.adapter_agent_repair_attempted
	if repair_attempted == nil then
		repair_attempted = trace.adapter_agent_repair_attempted
	end
	local repair_succeeded = response.adapter_agent_repair_succeeded
	if repair_succeeded == nil then
		repair_succeeded = trace.adapter_agent_repair_succeeded
	end
	local diagnostic = {
		schema_version = 1,
		diagnostic_kind = "nova_last_command",
		trace_id = trace.trace_id,
		prompt = bounded_trace_text(trace.public_prompt, 1000),
		route = trace.route,
		action = response.action or trace.action,
		response_status = response.status,
		response_reason = response.reason,
		message = bounded_trace_text(response.message, 1000),
		task_id = response.task_id,
		task_status = task_outcome.task_status,
		task_result_status = task_outcome.task_result_status,
		task_result_reason = task_outcome.task_result_reason,
		task_operation = task_outcome.operation,
		actual_node_writes = task_outcome.actual_node_writes,
		changed = task_outcome.changed,
		examined = task_outcome.examined,
		skipped = task_outcome.skipped,
		rollback_record_id = task_outcome.rollback_record_id,
		rollback_storage_ref = task_outcome.rollback_storage_ref,
		mapblock_churn = task_outcome.mapblock_churn,
		build_kind = response.build_kind,
		build_width = response.build_width,
		build_depth = response.build_depth,
		build_height = response.build_height,
		build_material_name = response.build_material_name,
		build_material_node = response.build_material_node,
		planned_node_writes = response.planned_node_writes,
		planner_mode = response.planner_mode,
		selected_candidate_id = response.selected_candidate_id,
		adapter_selected_candidate_id =
			response.adapter_selected_candidate_id or trace.adapter_selected_candidate_id,
		model_selected_candidate_id =
			response.model_selected_candidate_id or trace.model_selected_candidate_id,
		selection_source = response.selection_source,
		intent_constraint_option_id =
			response.intent_constraint_option_id or trace.intent_constraint_option_id,
		intent_constraint_reason =
			response.intent_constraint_reason or trace.intent_constraint_reason,
		candidate_count = response.candidate_count,
		adapter_name = trace.adapter_name,
		adapter_tool_decision_source =
			response.adapter_tool_decision_source or trace.adapter_tool_decision_source,
		adapter_initial_model_selected_candidate_id =
			response.adapter_initial_model_selected_candidate_id
			or trace.adapter_initial_model_selected_candidate_id,
		adapter_agent_repair_attempted =
			repair_attempted,
		adapter_agent_repair_succeeded =
			repair_succeeded,
		adapter_agent_repair_reason =
			response.adapter_agent_repair_reason or trace.adapter_agent_repair_reason,
		adapter_initial_missing_required_tool_calls =
			table.copy(response.adapter_initial_missing_required_tool_calls
				or trace.adapter_initial_missing_required_tool_calls or {}),
		adapter_required_tool_calls =
			table.copy(response.adapter_required_tool_calls
				or trace.adapter_required_tool_calls or {}),
		adapter_missing_required_tool_calls =
			table.copy(response.adapter_missing_required_tool_calls
				or trace.adapter_missing_required_tool_calls or {}),
		adapter_required_tool_calls_satisfied = required_tools_satisfied,
		adapter_tool_trace_names =
			table.copy(response.adapter_tool_trace_names
				or trace.adapter_tool_trace_names or {}),
		adapter_memory_available = memory_available,
		adapter_memory_matched_case_id =
			response.adapter_memory_matched_case_id or trace.adapter_memory_matched_case_id,
		adapter_memory_case_hint =
			response.adapter_memory_case_hint or trace.adapter_memory_case_hint,
		eval_review = plugin.command_eval_review(trace, response),
	}
	return diagnostic
end

function plugin.handle_last_command(name)
	plugin.ensure_surface_agent(name, "guide")
	local diagnostic = plugin.get_last_command_diagnostic(name)
	if not diagnostic then
		return public_reply(name, "last_command", "blocked",
			"No Nova request trace is available for this player yet.", {
				surface_id = "guide",
				reason = "no_request_trace",
			})
	end
	diagnostic.surface_id = "guide"
	return public_reply(name, "last_command", "success",
		"Last Nova command diagnostic returned.", diagnostic)
end

local function handle_rollback_review(name, requested_token)
	plugin.ensure_surface_agent(name, "guide")
	local filter
	local target_kind
	local target_id
	local reason_if_empty = "rollback_record_not_found_or_not_owned"
	if requested_token then
		local task = player_task_by_id(name, requested_token)
		if task then
			filter = { task_id = task.task_id }
			target_kind = "task"
			target_id = task.task_id
			reason_if_empty = "task_has_no_rollback_records"
		else
			filter = { rollback_record_id = requested_token }
			target_kind = "rollback"
			target_id = requested_token
		end
	end
	local records = rollback_records_for(name, 100, filter)
	if requested_token and #records == 0 then
		return public_reply(name, "rollback", "blocked",
			"Requested rollback record was not found for this player.", {
				surface_id = "guide",
				reason = reason_if_empty,
				target_kind = target_kind,
				target_id = target_id,
				rollback_records = {},
				no_rollback_execution = true,
			})
	end
	return public_reply(name, "rollback", "success", "Recent rollback records returned.", {
		surface_id = "guide",
		target_kind = target_kind,
		target_id = target_id,
		rollback_records = records,
		no_rollback_execution = true,
	})
end

local function handle_defend(name, context)
	context = context or {}
	context.surface_id = "defender"
	if not surface_required_capabilities_granted(product_surface("defender")) then
		return surface_gated_reply(name, "defender", "defend")
	end
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

local function handle_cancel(name, requested_task_id)
	plugin.ensure_surface_agent(name, "guide")
	if requested_task_id then
		local task, canonical_task_id = player_task_by_id(name, requested_task_id)
		if not task then
			return public_reply(name, "cancel", "blocked",
				"Requested task was not found for this player.", {
					surface_id = "guide",
					reason = "task_not_found_or_not_owned",
					task_id = canonical_task_id,
					cancelled = 0,
				})
		end
		local before_status = task.status
		local result = core.cancel_ai_task(task.task_id, name)
		local after = core.get_ai_task(task.task_id) or task
		return public_reply(name, "cancel", result.ok and "success" or "blocked",
			result.message or "Task cancellation checked.", {
				surface_id = "guide",
				reason = result.reason,
				task_id = task.task_id,
				task_status = after.status,
				before_status = before_status,
				after_status = after.status,
				cancelled = result.ok and 1 or 0,
			})
	end
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

local function is_movement_task(task)
	if type(task) ~= "table" then
		return false
	end
	local task_id = tostring(task.task_id or "")
	local label = tostring(task.label or "")
	return task_id:find(":follow:", 1, true) ~= nil
		or task_id:find(":come:", 1, true) ~= nil
		or label:find("follow", 1, true) ~= nil
		or label:find("come", 1, true) ~= nil
end

local function handle_stay(name)
	plugin.ensure_surface_agent(name, "guide")
	local cancelled = 0
	for _, task in ipairs(active_player_tasks(name)) do
		if is_movement_task(task)
				and (task.status == "queued" or task.status == "running"
					or task.status == "paused") then
			local result = core.cancel_ai_task(task.task_id, name)
			if result.ok then
				cancelled = cancelled + 1
			end
		end
	end
	local state = plugin.get_player_state(name)
	state.mode = "stay"
	state.target_name = nil
	state.target_pos = nil
	state = set_player_state(name, state)
	return public_reply(name, "stay", "success", "Helper movement stopped.", {
		surface_id = "guide",
		cancelled = cancelled,
		state = state,
	})
end

local function handle_tasks(name, requested_task_id)
	plugin.ensure_surface_agent(name, "guide")
	if requested_task_id then
		local task, canonical_task_id = player_task_by_id(name, requested_task_id)
		if not task then
			return public_reply(name, "task_status", "blocked",
				"Requested task was not found for this player.", {
					surface_id = "guide",
					reason = "task_not_found_or_not_owned",
					task_id = canonical_task_id,
				})
		end
		local last_result = task.last_result or {}
		return public_reply(name, "task_status", "success", "Task status returned.", {
			surface_id = "guide",
			task = task,
			task_id = task.task_id,
			task_status = task.status,
			task_label = task.label,
			last_result_status = last_result.status,
			last_result_reason = last_result.reason,
		})
	end
	return public_reply(name, "tasks", "success", "Task list returned.", {
		surface_id = "guide",
		tasks = active_player_tasks(name),
		pending_approval = compact_pending_approval(player_pending_approvals[name]),
	})
end

local function pending_approval_matches(pending, requested_action)
	if not requested_action or requested_action == "" then
		return true
	end
	local requested_lower = requested_action:lower()
	local approval_lower = pending.approval_id and pending.approval_id:lower() or nil
	return requested_lower == pending.action
		or requested_lower == approval_lower
		or requested_lower == "plan"
		or requested_lower == "approval"
end

local function handle_pending_plan(name)
	plugin.ensure_surface_agent(name, "guide")
	local pending = player_pending_approvals[name]
	if not pending then
		return public_reply(name, "pending_plan", "blocked", "No pending plan to review.", {
			surface_id = "guide",
			reason = "no_pending_approval",
		})
	end
	local plan = pending.plan or {}
	return public_reply(name, "pending_plan", "success", "Pending plan returned without mutation.", {
		surface_id = pending.surface_id or "guide",
		pending_approval = compact_pending_approval(pending),
		approval_id = pending.approval_id,
		pending_action = pending.action,
		plan = plan,
		plan_status = plan.status,
		candidate_count = pending.candidate_count,
		planned_node_writes = pending.planned_node_writes,
		build_kind = pending.build_kind,
		build_width = pending.build_width,
		build_depth = pending.build_depth,
		build_height = pending.build_height,
		build_material_name = pending.build_material_name,
		build_material_node = pending.build_material_node,
		planner_mode = pending.planner_mode,
		selected_candidate_id = pending.selected_candidate_id,
		adapter_selected_candidate_id = pending.adapter_selected_candidate_id,
		model_selected_candidate_id = pending.model_selected_candidate_id,
		selection_source = pending.selection_source,
		intent_constraint_option_id = pending.intent_constraint_option_id,
		intent_constraint_reason = pending.intent_constraint_reason,
		candidate_options = pending.candidate_options,
		adapter_tool_decision_source = pending.adapter_tool_decision_source,
		adapter_model_selected_candidate_id =
			pending.adapter_model_selected_candidate_id,
		adapter_initial_model_selected_candidate_id =
			pending.adapter_initial_model_selected_candidate_id,
		adapter_rejected_model_selected_candidate_id =
			pending.adapter_rejected_model_selected_candidate_id,
		adapter_agent_repair_attempted =
			pending.adapter_agent_repair_attempted,
		adapter_agent_repair_succeeded =
			pending.adapter_agent_repair_succeeded,
		adapter_agent_repair_reason =
			pending.adapter_agent_repair_reason,
		adapter_initial_missing_required_tool_calls =
			pending.adapter_initial_missing_required_tool_calls,
		adapter_required_tool_calls = pending.adapter_required_tool_calls,
		adapter_missing_required_tool_calls = pending.adapter_missing_required_tool_calls,
		adapter_required_tool_calls_satisfied =
			pending.adapter_required_tool_calls_satisfied,
		build_option_decision_source = pending.build_option_decision_source,
		adapter_memory_available = pending.adapter_memory_available,
		adapter_memory_matched_case_id = pending.adapter_memory_matched_case_id,
		adapter_memory_case_hint = pending.adapter_memory_case_hint,
		adapter_tool_trace_names = pending.adapter_tool_trace_names,
		adapter_build_action_plan_status =
			pending.adapter_build_action_plan_status,
		adapter_build_action_plan_selected_candidate_id =
			pending.adapter_build_action_plan_selected_candidate_id,
		adapter_build_action_plan_step_count =
			pending.adapter_build_action_plan_step_count,
		adapter_build_action_plan_world_mutation_authority =
			pending.adapter_build_action_plan_world_mutation_authority,
		generated_build_option_status = pending.generated_build_option_status,
		generated_build_option_reason = pending.generated_build_option_reason,
		generated_candidate_id = pending.generated_candidate_id,
		agentic_tool_success_required =
			pending.agentic_tool_success_required,
	})
end

function plugin.handle_build_options(name)
	plugin.ensure_surface_agent(name, "guide")
	local pending = player_pending_approvals[name]
	if not pending then
		return public_reply(name, "build_options", "blocked",
			"No pending build options are available.", {
				surface_id = "guide",
				reason = "no_pending_approval",
			})
	end
	if pending.action ~= "build" then
		return public_reply(name, "build_options", "blocked",
			"Pending approval is not a build plan.", {
				surface_id = pending.surface_id or "guide",
				reason = "pending_approval_not_build",
				pending_action = pending.action,
				pending_approval = compact_pending_approval(pending),
			})
	end
	local options = table.copy(pending.candidate_options or {})
	return public_reply(name, "build_options", "success",
		"Pending build options returned without mutation.", {
			surface_id = pending.surface_id or "builder",
			no_world_mutation = true,
			pending_approval = compact_pending_approval(pending),
			approval_id = pending.approval_id,
			pending_action = pending.action,
			selected_candidate_id = pending.selected_candidate_id,
			adapter_selected_candidate_id = pending.adapter_selected_candidate_id,
			model_selected_candidate_id = pending.model_selected_candidate_id,
			selection_source = pending.selection_source,
			candidate_count = pending.candidate_count or #options,
			candidate_options = options,
			planner_mode = pending.planner_mode,
			planned_node_writes = pending.planned_node_writes,
			build_kind = pending.build_kind,
			build_width = pending.build_width,
			build_depth = pending.build_depth,
			build_height = pending.build_height,
			build_material_name = pending.build_material_name,
			build_material_node = pending.build_material_node,
		})
end

local function update_build_pending_plan(name, pending, raw_prompt)
	local edited_context, reason = parse_build_edit_options(raw_prompt, pending.context)
	if not edited_context then
		return public_reply(name, "edit_plan", "blocked",
			"Pending build plan edit parameters are outside the configured bounds.", {
				surface_id = pending.surface_id or "builder",
				reason = reason,
				approval_id = pending.approval_id,
				pending_action = pending.action,
				pending_approval = compact_pending_approval(pending),
			})
	end
	local result, plan = build_plan_for(name, edited_context)
	pending.context = approval_context(edited_context)
	pending.plan = plan
	pending.candidate_count = nil
	pending.planned_node_writes = plan.metrics.planned_node_writes or 0
	pending.build_kind = plan.build_kind
	pending.build_width = plan.build_width
	pending.build_depth = plan.build_depth
	pending.build_height = plan.build_height
	pending.build_material_name = plan.build_material_name
	pending.build_material_node = plan.build_material_node
	pending.repair_radius = nil
	pending.sample_limit = nil
	player_pending_approvals[name] = pending
	return public_reply(name, "edit_plan", "success",
		"Pending build plan updated without mutation.", {
			surface_id = "builder",
			approval_id = pending.approval_id,
			pending_action = pending.action,
			pending_approval = compact_pending_approval(pending),
			plan = plan,
			plan_status = result.status,
			planned_node_writes = pending.planned_node_writes,
			build_kind = pending.build_kind,
			build_width = pending.build_width,
			build_depth = pending.build_depth,
			build_height = pending.build_height,
			build_material_name = pending.build_material_name,
			build_material_node = pending.build_material_node,
		})
end

local function update_repair_pending_plan(name, pending, raw_prompt)
	local edited_context, reason = parse_repair_edit_options(raw_prompt, pending.context)
	if not edited_context then
		return public_reply(name, "edit_plan", "blocked",
			"Pending repair plan edit parameters are outside the configured bounds.", {
				surface_id = pending.surface_id or "repair",
				reason = reason,
				approval_id = pending.approval_id,
				pending_action = pending.action,
				pending_approval = compact_pending_approval(pending),
			})
	end
	configure_product_surfaces()
	local agent_id = surface_agent_id_for(name, "repair")
	plugin.ensure_surface_agent(name, "repair")
	local repair_radius = repair_radius_for(edited_context)
	local sample_limit = repair_sample_limit_for(edited_context)
	local plan = core.repair_agent.plan_area(default_pos(edited_context), {
		agent_id = agent_id,
		owner = name,
		task_id = pending.approval_id .. ":plan",
		radius = repair_radius,
		repair_nodes = settings.repair_nodes,
		get_node = edited_context.get_node,
		sample_limit = sample_limit,
	})
	local compact = compact_repair_plan(plan)
	compact.repair_radius = repair_radius
	compact.sample_limit = sample_limit
	pending.context = approval_context(edited_context)
	pending.plan = compact
	pending.raw_plan = plan
	pending.candidate_count = compact.candidate_count
	pending.planned_node_writes = nil
	pending.build_kind = nil
	pending.build_width = nil
	pending.build_depth = nil
	pending.repair_radius = repair_radius
	pending.sample_limit = sample_limit
	player_pending_approvals[name] = pending
	return public_reply(name, "edit_plan", "success",
		"Pending repair plan updated without mutation.", {
			surface_id = "repair",
			approval_id = pending.approval_id,
			pending_action = pending.action,
			pending_approval = compact_pending_approval(pending),
			plan = compact,
			plan_status = plan.status,
			candidate_count = compact.candidate_count,
			repair_radius = repair_radius,
			sample_limit = sample_limit,
		})
end

local function handle_edit_pending_plan(name, raw_prompt)
	plugin.ensure_surface_agent(name, "guide")
	local pending = player_pending_approvals[name]
	if not pending then
		return public_reply(name, "edit_plan", "blocked", "No pending plan to edit.", {
			surface_id = "guide",
			reason = "no_pending_approval",
		})
	end
	if pending.action == "build" then
		return update_build_pending_plan(name, pending, raw_prompt)
	elseif pending.action == "repair" then
		return update_repair_pending_plan(name, pending, raw_prompt)
	end
	return public_reply(name, "edit_plan", "blocked",
		"Pending approval type is unsupported.", {
			surface_id = pending.surface_id or "guide",
			reason = "unsupported_pending_approval",
			approval_id = pending.approval_id,
			pending_action = pending.action,
		})
end

local function handle_discard_approval(name, raw_prompt)
	plugin.ensure_surface_agent(name, "guide")
	local pending = player_pending_approvals[name]
	if not pending then
		return public_reply(name, "discard_approval", "blocked", "No pending approval to discard.", {
			surface_id = "guide",
			reason = "no_pending_approval",
		})
	end
	local requested_action = raw_prompt:match("^[Dd][Ii][Ss][Cc][Aa][Rr][Dd]%s+(.+)$")
		or raw_prompt:match("^[Rr][Ee][Jj][Ee][Cc][Tt]%s+(.+)$")
		or raw_prompt:match("^[Dd][Ee][Nn][Yy]%s+(.+)$")
		or raw_prompt:match("^[Cc][Aa][Nn][Cc][Ee][Ll]%s+(.+)$")
		or raw_prompt:match("^[Nn][Oo]%s+(.+)$")
	if requested_action then
		requested_action = requested_action:trim()
		if requested_action:lower():match("^plan%s+.+$") then
			requested_action = requested_action:match("^[Pp][Ll][Aa][Nn]%s+(.+)$"):trim()
		elseif requested_action:lower():match("^approval%s+.+$") then
			requested_action = requested_action:match("^[Aa][Pp][Pp][Rr][Oo][Vv][Aa][Ll]%s+(.+)$"):trim()
		end
	end
	if not pending_approval_matches(pending, requested_action) then
		return public_reply(name, "discard_approval", "blocked",
			"Pending approval action does not match request.", {
				surface_id = "guide",
				reason = "approval_action_mismatch",
				approval_id = pending.approval_id,
				pending_action = pending.action,
				requested_action = requested_action,
			})
	end
	player_pending_approvals[name] = nil
	return public_reply(name, "discard_approval", "success",
		"Pending approval discarded before mutation.", {
			surface_id = pending.surface_id or "guide",
			approval_id = pending.approval_id,
			discarded_action = pending.action,
			candidate_count = pending.candidate_count,
			planned_node_writes = pending.planned_node_writes,
		})
end

local function handle_approve(name, raw_prompt)
	local pending = player_pending_approvals[name]
	if not pending then
		return public_reply(name, "approve", "blocked", "No pending approval to apply.", {
			reason = "no_pending_approval",
		})
	end
	local requested_action = raw_prompt:match("^[Aa][Pp][Pp][Rr][Oo][Vv][Ee]%s+(.+)$")
	if requested_action then
		requested_action = requested_action:trim()
	end
	if not pending_approval_matches(pending, requested_action) then
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
	plugin._player_loop.record(name, {
		status = queued.status,
		phase = "acting",
		active_surface = queued.surface_id or pending.surface_id,
		next_action = "step_ai_task_queue",
		last_task_id = queued.task_id,
		last_result_status = queued.status,
	})
	return queued
end

function plugin._player_loop.prompt_looks_like_builder_refinement(prompt)
	if prompt == "" then
		return false
	end
	return prompt:find("only", 1, true)
		or prompt:find("just", 1, true)
		or prompt:find("instead", 1, true)
		or prompt:find("nothing else", 1, true)
		or prompt:find("no platform", 1, true)
		or prompt:find("not a platform", 1, true)
		or prompt:find("do not", 1, true)
		or prompt:find("don't", 1, true)
		or prompt:find("change it", 1, true)
		or prompt:find("make it", 1, true)
		or prompt:find("use ", 1, true)
		or prompt:find("tnt", 1, true)
		or prompt:find("fire", 1, true)
end

function plugin._player_loop.builder_followup_prompt(name, raw_prompt, prompt)
	local state = plugin.get_player_state(name)
	local loop = state.loop or {}
	if loop.active_surface ~= "builder" or not loop.active_goal then
		return nil
	end
	if prompt == "build"
			or prompt:match("^build%s+")
			or prompt == "marker"
			or prompt:match("^marker%s+")
			or prompt:match("^plan%s+")
			or prompt:match("^preview%s+") then
		return nil
	end
	if not plugin._player_loop.prompt_looks_like_builder_refinement(prompt) then
		return nil
	end
	return "Previous builder goal: "
		.. bounded_trace_text(loop.active_goal, 240)
		.. "\nPlayer follow-up: "
		.. bounded_trace_text(raw_prompt, 240)
end

plugin._natural_chat = {}

function plugin._natural_chat.normalized_aliases()
	local aliases = {}
	for _, alias in ipairs(settings.natural_chat_aliases or {}) do
		if type(alias) == "string" then
			local normalized = alias:trim():lower()
			if normalized ~= "" then
				aliases[#aliases + 1] = normalized
			end
		end
	end
	if #aliases == 0 then
		return { "nova", "bot", "aibot" }
	end
	return aliases
end

function plugin._natural_chat.prompt_after_addressed_alias(message, alias, leading_phrase)
	leading_phrase = leading_phrase or ""
	local lower = message:lower()
	if leading_phrase ~= "" and lower:sub(1, #leading_phrase) ~= leading_phrase then
		return nil
	end
	local alias_start = #leading_phrase + 1
	local alias_end = alias_start + #alias - 1
	if lower:sub(alias_start, alias_end) ~= alias then
		return nil
	end
	local next_char = lower:sub(alias_end + 1, alias_end + 1)
	if next_char ~= "" and not next_char:match("[%s,:%-]") then
		return nil
	end
	local prompt = message:sub(alias_end + 1):gsub("^[%s,:%-]+", ""):trim()
	return prompt ~= "" and prompt or "status"
end

function plugin._natural_chat.extract_prompt(message)
	local trimmed = tostring(message or ""):trim()
	if trimmed == "" or trimmed:sub(1, 1) == "/" then
		return nil
	end
	local leading_phrases = { "", "hey ", "ok ", "okay " }
	for _, alias in ipairs(plugin._natural_chat.normalized_aliases()) do
		for _, leading_phrase in ipairs(leading_phrases) do
			local prompt = plugin._natural_chat.prompt_after_addressed_alias(
				trimmed, alias, leading_phrase)
			if prompt then
				return prompt, alias
			end
		end
	end
	return nil
end

local function handle_model(name, prompt, context)
	context = context or {}
	local adapter_name = context.adapter_name or "ai_agent_plugin"
	local has_async_adapter = model_adapter_async ~= nil
		and core.ai_model_ops and core.ai_model_ops.request_async
	local trace = start_request_trace(name, "model",
		has_async_adapter and "model_adapter_async" or "model_adapter",
		prompt, context, {
			adapter_name = adapter_name,
		})
	if has_async_adapter then
		local completed = false
		local returned_to_player = false
		local completed_reply
		local function complete_async_model(result)
			completed = true
			completed_reply = public_reply(name, "model",
				result.ok and "success" or "blocked",
				result.message or "Model adapter did not return a response.", {
					reason = result.reason,
					trace_id = trace.trace_id,
					adapter_name = adapter_name,
					async_model_request = true,
				})
			finish_request_trace(trace, completed_reply, {
				adapter_name = adapter_name,
				async_model_request = true,
			})
			if type(context.on_model_complete) == "function" then
				local callback_ok, callback_err = pcall(context.on_model_complete,
					completed_reply, trace)
				if not callback_ok then
					core.log("error", "[ai_agent_plugin] model completion callback failed: "
						.. tostring(callback_err))
				end
			end
			if returned_to_player and core.chat_send_player then
				local completed_text = context.natural_chat
					and plugin.format_player_reply(completed_reply)
					or plugin.format_reply(completed_reply)
				if context.natural_chat then
					plugin._player_loop.append_turn(name, "assistant",
						completed_text, completed_reply.surface_id, "natural_chat")
				end
				core.chat_send_player(name, completed_text)
			end
		end
		local queued, reason = core.ai_model_ops.request_async(prompt, {
			agent_id = agent_id_for(name),
			owner = name,
			task_id = context.task_id,
			private_prompt = context.private_prompt,
			adapter_async = model_adapter_async,
			adapter_name = adapter_name,
			context = context,
		}, complete_async_model)
		if not queued then
			return finish_request_trace(trace, public_reply(name, "model", "blocked",
				"Model adapter request could not be queued.", {
					reason = reason,
					trace_id = trace.trace_id,
					adapter_name = adapter_name,
					async_model_request = true,
				}), {
					adapter_name = adapter_name,
					async_model_request = true,
				})
		end
		if completed then
			return completed_reply
		end
		local queued_reply = public_reply(name, "model", "queued",
			"Model adapter request queued.", {
				reason = "model_adapter_queued",
				trace_id = trace.trace_id,
				adapter_name = adapter_name,
				async_model_request = true,
			})
			trace.response = {
				ok = true,
				status = "queued",
				action = "model",
				reason = "model_adapter_queued",
				message = "Model adapter request queued.",
				trace_id = trace.trace_id,
			}
			log_request_trace(trace, "queued")
			returned_to_player = true
			return queued_reply
		end
	local result = core.ai_model_ops.request(prompt, {
		agent_id = agent_id_for(name),
		owner = name,
		task_id = context.task_id,
		private_prompt = context.private_prompt,
		adapter = model_adapter,
		adapter_name = adapter_name,
		context = context,
	})
	return finish_request_trace(trace, public_reply(name, "model",
		result.ok and "success" or "blocked",
		result.message or "Model adapter did not return a response.", {
			reason = result.reason,
			adapter_name = adapter_name,
		}), {
			adapter_name = adapter_name,
		})
end

function plugin.handle_command(name, param, context)
	name = normalize_player_name(name)
	plugin.ensure_player_agent(name)
	context = context or {}
	context.player_name = name
	local raw_prompt = tostring(param or ""):trim()
	local prompt = raw_prompt:lower()

	if prompt == "" or prompt == "status" then
		return handle_status(name)
	end
	if prompt == "guide" or prompt == "help" or prompt == "commands" then
		return handle_guide(name)
	end
	if prompt == "last" or prompt == "last command" or prompt == "last nova"
			or prompt == "diagnostic" or prompt == "diagnostics"
			or prompt == "debug last" or prompt == "why"
			or prompt == "what happened" or prompt == "what did you do" then
		return plugin.handle_last_command(name)
	end
	if prompt == "traces" or prompt == "trace" or prompt == "logs"
			or prompt == "model traces" or prompt == "request traces" then
		return handle_request_traces(name)
	end
	local feedback_payload = plugin._nova_feedback_payload(raw_prompt)
	if feedback_payload ~= nil then
		return plugin._handle_nova_feedback(name, feedback_payload, context)
	end
	local requested_audit_task_id = raw_prompt:match("^[Aa][Uu][Dd][Ii][Tt]%s+(.+)$")
		or raw_prompt:match("^[Hh][Ii][Ss][Tt][Oo][Rr][Yy]%s+(.+)$")
	if requested_audit_task_id then
		return handle_audit(name, requested_audit_task_id:trim())
	end
	if prompt == "audit" or prompt == "history" then
		return handle_audit(name)
	end
	local requested_rollback_token =
		raw_prompt:match("^[Rr][Oo][Ll][Ll][Bb][Aa][Cc][Kk]%s+[Rr][Ee][Vv][Ii][Ee][Ww]%s+(.+)$")
		or raw_prompt:match("^[Rr][Oo][Ll][Ll][Bb][Aa][Cc][Kk]%s+(.+)$")
	if requested_rollback_token then
		return handle_rollback_review(name, requested_rollback_token:trim())
	end
	if prompt == "rollback" or prompt == "rollback review" then
		return handle_rollback_review(name)
	end
	if prompt == "tasks" or prompt == "task status" or prompt == "builder" then
		return handle_tasks(name)
	end
	if prompt == "pending" or prompt == "pending plan"
			or prompt == "plan" or prompt == "review plan" then
		return handle_pending_plan(name)
	end
	if prompt == "options" or prompt == "choices"
			or prompt == "build options" or prompt == "show options"
			or prompt == "show choices" or prompt == "what are my options"
			or prompt == "what options" then
		return plugin.handle_build_options(name)
	end
	if prompt == "edit plan" or prompt:match("^edit%s+plan%s+.+$")
			or prompt:match("^plan%s+edit%s+.+$")
			or prompt:match("^update%s+plan%s+.+$")
			or prompt:match("^change%s+plan%s+.+$")
			or prompt:match("^pending%s+plan%s+.+$")
			or prompt:match("^edit%s+build%s+plan%s+.+$")
			or prompt:match("^edit%s+repair%s+plan%s+.+$") then
		return handle_edit_pending_plan(name, raw_prompt)
	end
	local requested_task_id = raw_prompt:match("^[Tt][Aa][Ss][Kk]%s+[Ss][Tt][Aa][Tt][Uu][Ss]%s+(.+)$")
		or raw_prompt:match("^[Tt][Aa][Ss][Kk]%s+(.+)$")
	if requested_task_id then
		return handle_tasks(name, requested_task_id:trim())
	end
	if prompt == "cancel" or prompt == "stop" then
		return handle_cancel(name)
	end
	if prompt == "stay" or prompt == "wait" then
		return handle_stay(name)
	end
	if prompt == "cancel plan" or prompt == "cancel approval"
			or prompt == "no" or prompt == "no plan"
			or prompt:match("^cancel%s+plan%s+.+$")
			or prompt:match("^cancel%s+approval%s+.+$")
			or prompt:match("^no%s+.+$") then
		return handle_discard_approval(name, raw_prompt)
	end
	local requested_cancel_task_id = raw_prompt:match("^[Cc][Aa][Nn][Cc][Ee][Ll]%s+(.+)$")
		or raw_prompt:match("^[Ss][Tt][Oo][Pp]%s+(.+)$")
	if requested_cancel_task_id then
		return handle_cancel(name, requested_cancel_task_id:trim())
	end
	if prompt == "discard" or prompt == "discard plan"
			or prompt == "reject" or prompt == "reject plan"
			or prompt == "deny" or prompt == "deny plan"
			or prompt:match("^discard%s+.+$")
			or prompt:match("^reject%s+.+$")
			or prompt:match("^deny%s+.+$") then
		return handle_discard_approval(name, raw_prompt)
	end
	if prompt == "approve" or prompt:match("^approve%s+.+$") then
		return handle_approve(name, raw_prompt)
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
			and prompt_has_build_surface(prompt) then
		if agentic_build_planner_available() then
			return handle_agentic_build_planner(name, raw_prompt, context,
				"agentic_build_planner_first")
		end
		local build_context, reason = parse_build_options(raw_prompt, context)
		if not build_context then
			if reason == "ambiguous_build_intent" then
				return handle_agentic_build_planner(name, raw_prompt, context, reason)
			end
			local trace = start_request_trace(name, "build_plan",
				"deterministic_build_parser", raw_prompt, context, {
					surface_id = "builder",
				})
			return finish_request_trace(trace, public_reply(name, "build_plan", "blocked",
				"Build plan parameters are outside the configured bounds.", {
					surface_id = "builder",
					reason = reason,
				}))
		end
		local trace = start_request_trace(name, "build_plan",
			"deterministic_build_parser", raw_prompt, context, {
				surface_id = "builder",
			})
		trace.context = compact_trace_context(build_context)
		return finish_request_trace(trace, handle_build_plan(name, build_context), {
			selected_intent = build_context.build_kind,
			build_material_node = build_context.build_material_node,
		})
	end
	if (prompt:find("plan", 1, true) or prompt:find("preview", 1, true))
			and (prompt:find("repair", 1, true) or prompt:find("fix", 1, true)) then
		local repair_context, reason = parse_repair_options(raw_prompt, context)
		if not repair_context then
			return public_reply(name, "repair_plan", "blocked",
				"Repair plan parameters are outside the configured bounds.", {
					surface_id = "repair",
					reason = reason,
				})
		end
		return handle_repair_plan(name, repair_context)
	end
	if prompt:find("repair", 1, true) or prompt:find("fix", 1, true) then
		local repair_context, reason = parse_repair_options(raw_prompt, context)
		if not repair_context then
			return public_reply(name, "repair", "blocked",
				"Repair parameters are outside the configured bounds.", {
					surface_id = "repair",
					reason = reason,
				})
		end
		return handle_repair(name, repair_context)
	end
	if prompt:find("defend", 1, true) then
		return handle_defend(name, context)
	end
	if prompt:find("import", 1, true)
			and (prompt:find("plan", 1, true) or prompt:find("preview", 1, true)
				or prompt:find("inventory", 1, true)) then
		return handle_import_plan(name, context)
	end
	local followup_prompt =
		plugin._player_loop.builder_followup_prompt(name, raw_prompt, prompt)
	if followup_prompt then
		local followup_context = table.copy(context)
		followup_context.player_turn_text = raw_prompt
		followup_context.player_turn_source =
			context.player_turn_source or "nova_builder_followup"
		return handle_agentic_build_planner(name, followup_prompt,
			followup_context, "player_agent_followup_refinement")
	end
	if prompt:find("build", 1, true) or prompt:find("marker", 1, true) then
		if agentic_build_planner_available() then
			return handle_agentic_build_planner(name, raw_prompt, context,
				"agentic_build_planner_first")
		end
		local build_context, reason = parse_build_options(raw_prompt, context)
		if not build_context then
			if reason == "ambiguous_build_intent" then
				return handle_agentic_build_planner(name, raw_prompt, context, reason)
			end
			local trace = start_request_trace(name, "build",
				"deterministic_build_parser", raw_prompt, context, {
					surface_id = "builder",
				})
			return finish_request_trace(trace, public_reply(name, "build", "blocked",
				"Build parameters are outside the configured bounds.", {
					surface_id = "builder",
					reason = reason,
				}))
		end
		local trace = start_request_trace(name, "build",
			"deterministic_build_parser", raw_prompt, context, {
				surface_id = "builder",
			})
		trace.context = compact_trace_context(build_context)
		return finish_request_trace(trace, handle_build(name, build_context), {
			selected_intent = build_context.build_kind,
			build_material_node = build_context.build_material_node,
		})
	end
	return handle_model(name, prompt, context)
end

function plugin.handle_natural_chat_message(name, message, context)
	if settings.natural_chat_enabled ~= true then
		return false
	end
	local prompt, alias = plugin._natural_chat.extract_prompt(message)
	if not prompt then
		return false
	end
	local chat_context = table.copy(context or {})
	chat_context.input_surface = "natural_chat"
	chat_context.natural_chat = true
	chat_context.natural_chat_alias = alias
	chat_context.player_turn_text = prompt
	chat_context.player_turn_source = "natural_chat"
	local result = plugin.handle_command(name, prompt, chat_context)
	local player_reply = plugin.format_player_reply(result)
	result.player_reply = player_reply
	plugin._player_loop.append_turn(name, "assistant", player_reply,
		result.surface_id or chat_context.surface_id, "natural_chat")
	if core.chat_send_player and chat_context.suppress_chat_send ~= true then
		core.chat_send_player(name, player_reply)
	end
	return true, result
end

local EVAL_DEFAULT_MODEL_PROMPT = "what can you plan with tools next?"
local EVAL_DEFAULT_CASES = { "build_fire", "fire_only_strict", "tnt_wall", "agentic_build_planner", "model" }
local EVAL_MAX_OUTPUT_BYTES = 12000

local function eval_metric_delta(before, after, key)
	return (after[key] or 0) - (before[key] or 0)
end

local function latest_request_trace()
	local traces = plugin.get_request_traces({ limit = 1 })
	return traces[1]
end

local function trace_by_id(trace_id)
	if not trace_id then
		return nil
	end
	for _, trace in ipairs(plugin.get_request_traces({ limit = settings.max_request_traces or 50 })) do
		if trace.trace_id == trace_id then
			return trace
		end
	end
	return nil
end

local function compact_eval_reply(reply)
	reply = reply or {}
	return {
		ok = reply.ok,
		action = reply.action,
		status = reply.status,
		reason = reply.reason,
		message = bounded_trace_text(reply.message, 400),
		approval_id = reply.approval_id,
		pending_action = reply.pending_action,
		trace_id = reply.trace_id,
		build_kind = reply.build_kind,
		build_width = reply.build_width,
		build_depth = reply.build_depth,
		build_height = reply.build_height,
		build_count = reply.build_count,
		build_material_name = reply.build_material_name,
		build_material_node = reply.build_material_node,
		planned_node_writes = reply.planned_node_writes,
		planner_mode = reply.planner_mode,
		selected_candidate_id = reply.selected_candidate_id,
		adapter_selected_candidate_id = reply.adapter_selected_candidate_id,
		model_selected_candidate_id = reply.model_selected_candidate_id,
		selection_source = reply.selection_source,
		intent_constraint_option_id = reply.intent_constraint_option_id,
		intent_constraint_reason = reply.intent_constraint_reason,
		candidate_count = reply.candidate_count,
		adapter_tool_decision_source = reply.adapter_tool_decision_source,
		adapter_model_selected_candidate_id =
			reply.adapter_model_selected_candidate_id,
		adapter_initial_model_selected_candidate_id =
			reply.adapter_initial_model_selected_candidate_id,
		adapter_rejected_model_selected_candidate_id =
			reply.adapter_rejected_model_selected_candidate_id,
		adapter_agent_repair_attempted = reply.adapter_agent_repair_attempted,
		adapter_agent_repair_succeeded = reply.adapter_agent_repair_succeeded,
		adapter_agent_repair_reason = reply.adapter_agent_repair_reason,
		adapter_initial_missing_required_tool_calls =
			reply.adapter_initial_missing_required_tool_calls,
		adapter_required_tool_calls = reply.adapter_required_tool_calls,
		adapter_missing_required_tool_calls =
			reply.adapter_missing_required_tool_calls,
		adapter_required_tool_calls_satisfied =
			reply.adapter_required_tool_calls_satisfied,
		build_option_decision_source = reply.build_option_decision_source,
		adapter_memory_available = reply.adapter_memory_available,
		adapter_memory_matched_case_id = reply.adapter_memory_matched_case_id,
		adapter_memory_case_hint = reply.adapter_memory_case_hint,
		adapter_tool_trace_names = reply.adapter_tool_trace_names,
		adapter_build_action_plan_status =
			reply.adapter_build_action_plan_status,
		adapter_build_action_plan_selected_candidate_id =
			reply.adapter_build_action_plan_selected_candidate_id,
		adapter_build_action_plan_step_count =
			reply.adapter_build_action_plan_step_count,
		adapter_build_action_plan_world_mutation_authority =
			reply.adapter_build_action_plan_world_mutation_authority,
		generated_build_option_status = reply.generated_build_option_status,
		generated_build_option_reason = reply.generated_build_option_reason,
		generated_candidate_id = reply.generated_candidate_id,
		planner_model_status = reply.planner_model_status,
		planner_model_reason = reply.planner_model_reason,
		agentic_tool_success_required =
			reply.agentic_tool_success_required,
		agentic_planner_fallback_blocked =
			reply.agentic_planner_fallback_blocked,
		fallback_blocked_reason = reply.fallback_blocked_reason,
		adapter_name = reply.adapter_name,
		async_model_request = reply.async_model_request,
	}
end

local function compact_eval_trace(trace)
	if not trace then
		return nil
	end
	local response = trace.response or {}
	local context = trace.context or {}
	return {
		trace_id = trace.trace_id,
		action = trace.action,
		route = trace.route,
		public_prompt = trace.public_prompt,
		adapter_name = trace.adapter_name,
		async_model_request = trace.async_model_request,
		response = {
			ok = response.ok,
			status = response.status,
			reason = response.reason,
			message = bounded_trace_text(response.message, 400),
			build_kind = response.build_kind,
			build_width = response.build_width,
			build_depth = response.build_depth,
			build_height = response.build_height,
			build_count = response.build_count,
			build_material_name = response.build_material_name,
			build_material_node = response.build_material_node,
			planned_node_writes = response.planned_node_writes,
			planner_mode = response.planner_mode,
			selected_candidate_id = response.selected_candidate_id,
			adapter_selected_candidate_id =
				response.adapter_selected_candidate_id,
			model_selected_candidate_id =
				response.model_selected_candidate_id,
			selection_source = response.selection_source,
			intent_constraint_option_id = response.intent_constraint_option_id,
			intent_constraint_reason = response.intent_constraint_reason,
			candidate_count = response.candidate_count,
			adapter_tool_decision_source =
				response.adapter_tool_decision_source,
			adapter_model_selected_candidate_id =
				response.adapter_model_selected_candidate_id,
			adapter_initial_model_selected_candidate_id =
				response.adapter_initial_model_selected_candidate_id,
			adapter_rejected_model_selected_candidate_id =
				response.adapter_rejected_model_selected_candidate_id,
			adapter_agent_repair_attempted =
				response.adapter_agent_repair_attempted,
			adapter_agent_repair_succeeded =
				response.adapter_agent_repair_succeeded,
			adapter_agent_repair_reason =
				response.adapter_agent_repair_reason,
			adapter_initial_missing_required_tool_calls =
				response.adapter_initial_missing_required_tool_calls,
			adapter_required_tool_calls =
				response.adapter_required_tool_calls,
			adapter_missing_required_tool_calls =
				response.adapter_missing_required_tool_calls,
			adapter_required_tool_calls_satisfied =
				response.adapter_required_tool_calls_satisfied,
			build_option_decision_source =
				response.build_option_decision_source,
			adapter_memory_available =
				response.adapter_memory_available,
			adapter_memory_matched_case_id =
				response.adapter_memory_matched_case_id,
			adapter_memory_case_hint =
				response.adapter_memory_case_hint,
			adapter_tool_trace_names =
				response.adapter_tool_trace_names,
			adapter_build_action_plan_status =
				response.adapter_build_action_plan_status,
			adapter_build_action_plan_selected_candidate_id =
				response.adapter_build_action_plan_selected_candidate_id,
			adapter_build_action_plan_step_count =
				response.adapter_build_action_plan_step_count,
			adapter_build_action_plan_world_mutation_authority =
				response.adapter_build_action_plan_world_mutation_authority,
			generated_build_option_status =
				response.generated_build_option_status,
			generated_build_option_reason =
				response.generated_build_option_reason,
			generated_candidate_id = response.generated_candidate_id,
			planner_model_status = response.planner_model_status,
			planner_model_reason = response.planner_model_reason,
			agentic_tool_success_required =
				response.agentic_tool_success_required,
			agentic_planner_fallback_blocked =
				response.agentic_planner_fallback_blocked,
			fallback_blocked_reason = response.fallback_blocked_reason,
		},
		context = {
			build_kind = context.build_kind,
			build_width = context.build_width,
			build_depth = context.build_depth,
			build_height = context.build_height,
			build_count = context.build_count,
			build_material_name = context.build_material_name,
			build_material_node = context.build_material_node,
		},
	}
end

local function eval_checks_status(checks)
	local failures = {}
	for name, passed in pairs(checks or {}) do
		if passed ~= true then
			failures[#failures + 1] = name
		end
	end
	table.sort(failures)
	return #failures == 0, failures
end

local trace_private_context_retained

local function eval_context(options)
	local context = table.copy(options.context or {})
	context.pos = context.pos or options.pos or { x = 0, y = 20, z = 0 }
	context.world_id = context.world_id or options.world_id or "ai_agent_eval"
	return context
end

local function append_eval_case(report, case_report)
	local ok, failures = eval_checks_status(case_report.checks)
	case_report.ok = ok
	case_report.status = ok and "pass" or "fail"
	case_report.failures = failures
	report.cases[#report.cases + 1] = case_report
	return case_report
end

local function run_build_eval_case(report, owner, case_id, prompt, context, expected, metadata)
	metadata = metadata or {}
	local reply = plugin.handle_command(owner, prompt, context)
	local trace = latest_request_trace()
	local cleanup
	if reply and reply.status == "pending_approval" then
		cleanup = plugin.handle_command(owner, "discard plan", {})
	end
	return append_eval_case(report, {
		case_id = case_id,
		case_hint = metadata.case_hint,
		source_candidate_id = metadata.source_candidate_id,
		prompt = prompt,
		reply = compact_eval_reply(reply),
		trace = compact_eval_trace(trace),
		cleanup = cleanup and {
			action = cleanup.action,
			status = cleanup.status,
			reason = cleanup.reason,
		} or nil,
		checks = {
			reply_ok = reply and reply.ok == true,
			action = reply and reply.action == "build",
			status = reply and reply.status == "pending_approval",
			approval_required = reply and reply.approval_id ~= nil,
			not_refused_as_dangerous = reply
				and reply.reason ~= "dangerous"
				and reply.reason ~= "unsafe",
			trace_route = trace and trace.route
				== (expected.route or "deterministic_build_parser"),
			trace_prompt = trace and trace.public_prompt == prompt,
			trace_status = trace and trace.response
				and trace.response.status == "pending_approval",
			build_kind = reply and reply.build_kind == expected.build_kind,
			material_name = expected.build_material_name == nil
				or (reply and reply.build_material_name == expected.build_material_name),
			material_node = expected.build_material_node == nil
				or (reply and reply.build_material_node == expected.build_material_node),
			build_width = expected.build_width == nil
				or (reply and reply.build_width == expected.build_width),
			build_depth = expected.build_depth == nil
				or (reply and reply.build_depth == expected.build_depth),
			build_height = expected.build_height == nil
				or (reply and reply.build_height == expected.build_height),
			build_count = expected.build_count == nil
				or (reply and reply.build_count == expected.build_count),
			planned_writes = expected.planned_node_writes == nil
				or (reply and reply.planned_node_writes == expected.planned_node_writes),
			cleanup_discarded = cleanup == nil
				or (cleanup.action == "discard_approval"
					and cleanup.status == "success"),
		},
	})
end

local function finish_agentic_build_eval_case(case_report, final_reply, final_trace, expected)
	expected = expected or {}
	final_trace = final_trace or trace_by_id(case_report.trace_id) or latest_request_trace()
	local cleanup
	if final_reply and final_reply.status == "pending_approval" then
		cleanup = plugin.handle_command(case_report.owner, "discard plan", {})
	end
	case_report.final_reply = compact_eval_reply(final_reply)
	case_report.final_trace = compact_eval_trace(final_trace)
	case_report.cleanup = cleanup and {
		action = cleanup.action,
		status = cleanup.status,
		reason = cleanup.reason,
	} or nil
	case_report.final_status = final_reply and final_reply.status
	case_report.final_reason = final_reply and final_reply.reason
	case_report.checks.final_reply_ok = final_reply and final_reply.ok == true
	case_report.checks.final_action = final_reply and final_reply.action == "build"
	case_report.checks.final_status = final_reply and final_reply.status == "pending_approval"
	case_report.checks.approval_required = final_reply and final_reply.approval_id ~= nil
	case_report.checks.planner_mode = final_reply
		and (expected.agentic_model_required == false
			or final_reply.planner_mode == "agentic_model_adapter")
	case_report.checks.selected_candidate = final_reply
		and type(final_reply.selected_candidate_id) == "string"
		and final_reply.selected_candidate_id ~= ""
	if expected.selected_candidate_id ~= nil then
		case_report.checks.selected_candidate =
			case_report.checks.selected_candidate
			and final_reply.selected_candidate_id == expected.selected_candidate_id
	end
	case_report.checks.multiple_options = final_reply
		and (final_reply.candidate_count or 0) >= 3
	case_report.checks.build_kind = final_reply
		and type(final_reply.build_kind) == "string"
		and final_reply.build_kind ~= ""
	if expected.build_kind ~= nil then
		case_report.checks.build_kind =
			case_report.checks.build_kind
			and final_reply.build_kind == expected.build_kind
	end
	case_report.checks.material_name = expected.build_material_name == nil
		or (final_reply and final_reply.build_material_name == expected.build_material_name)
	case_report.checks.material_node = expected.build_material_node == nil
		or (final_reply and final_reply.build_material_node == expected.build_material_node)
	case_report.checks.build_width = expected.build_width == nil
		or (final_reply and final_reply.build_width == expected.build_width)
	case_report.checks.build_depth = expected.build_depth == nil
		or (final_reply and final_reply.build_depth == expected.build_depth)
	case_report.checks.build_height = expected.build_height == nil
		or (final_reply and final_reply.build_height == expected.build_height)
	case_report.checks.build_count = expected.build_count == nil
		or (final_reply and final_reply.build_count == expected.build_count)
	local planned_writes = final_reply and final_reply.planned_node_writes or nil
	case_report.checks.planned_writes = type(planned_writes) == "number"
		and planned_writes > 0
		and planned_writes <= settings.max_lights
	if expected.planned_node_writes ~= nil then
		case_report.checks.planned_writes =
			case_report.checks.planned_writes
			and planned_writes == expected.planned_node_writes
	end
	case_report.checks.trace_route = final_trace
		and final_trace.route == (expected.route or "agentic_build_planner")
	case_report.checks.trace_status = final_trace and final_trace.response
		and final_trace.response.status == "pending_approval"
	case_report.checks.trace_prompt = final_trace
		and final_trace.public_prompt == case_report.prompt
	case_report.checks.no_trace_private_context =
		not trace_private_context_retained(final_trace)
	case_report.checks.cleanup_discarded = cleanup
		and cleanup.action == "discard_approval"
		and cleanup.status == "success"
	local ok, failures = eval_checks_status(case_report.checks)
	case_report.ok = ok
	case_report.status = ok and "pass" or "fail"
	case_report.failures = failures
	case_report.owner = nil
end

local function run_agentic_build_eval_case(report, owner, prompt, context, async_done,
		case_id, expected, metadata)
	expected = expected or {
		route = "agentic_build_planner",
	}
	metadata = metadata or {}
	local case_report = {
		case_id = case_id or "agentic_build_planner",
		case_hint = metadata.case_hint,
		source_candidate_id = metadata.source_candidate_id,
		owner = owner,
		prompt = prompt,
		expected = table.copy(expected),
		checks = {},
	}
	report.cases[#report.cases + 1] = case_report
	local planner_context = table.copy(context or {})
	planner_context.on_agentic_build_planner_complete = function(final_reply, final_trace)
		case_report.completed_by_hook = true
		finish_agentic_build_eval_case(case_report, final_reply, final_trace, expected)
		if case_report.initial_recorded then
			async_done()
		end
	end
	local initial_reply = plugin.handle_command(owner, prompt, planner_context)
	local initial_trace = initial_reply and initial_reply.trace_id
		and trace_by_id(initial_reply.trace_id) or latest_request_trace()
	case_report.trace_id = initial_reply and initial_reply.trace_id
		or (initial_trace and initial_trace.trace_id)
	case_report.initial_reply = compact_eval_reply(initial_reply)
	case_report.initial_trace = compact_eval_trace(initial_trace)
	case_report.queued_status = initial_reply and initial_reply.status
	case_report.queued_reason = initial_reply and initial_reply.reason
	case_report.checks.initial_action = initial_reply
		and initial_reply.action == "build_plan"
	case_report.checks.initial_trace_id = case_report.trace_id ~= nil
	case_report.checks.initial_queued = initial_reply
		and (initial_reply.status == "queued"
			or initial_reply.status == "pending_approval")
	case_report.checks.initial_planner_mode = initial_reply
		and (initial_reply.planner_mode == "agentic_model_adapter"
			or initial_reply.planner_mode == "deterministic_candidate_fallback")
	case_report.checks.initial_multiple_options = initial_reply
		and (initial_reply.candidate_count or 0) >= 3
	local expected_initial_candidate = expected.initial_selected_candidate_id
	if expected_initial_candidate == nil and expected.selected_candidate_id == nil then
		expected_initial_candidate = "platform"
	end
	case_report.checks.initial_selected_candidate = initial_reply
		and type(initial_reply.selected_candidate_id) == "string"
		and initial_reply.selected_candidate_id ~= ""
	if expected_initial_candidate ~= nil then
		case_report.checks.initial_selected_candidate =
			case_report.checks.initial_selected_candidate
			and initial_reply.selected_candidate_id == expected_initial_candidate
	end
	case_report.checks.initial_trace_route = initial_trace
		and (initial_trace.route == "agentic_build_planner"
			or initial_trace.route == "deterministic_build_candidate_fallback")
	case_report.checks.no_initial_trace_private_context =
		not trace_private_context_retained(initial_trace)
	case_report.initial_recorded = true
	if initial_reply and initial_reply.status == "queued"
			and not case_report.completed_by_hook then
		case_report.status = "queued"
		return true
	end
	if case_report.completed_by_hook then
		return false
	end
	finish_agentic_build_eval_case(case_report, initial_reply, initial_trace, expected)
	return false
end

local function audit_payload_retained(records)
	for _, record in ipairs(records or {}) do
		if record.private_payload ~= nil or record.payload_retained == true then
			return true
		end
	end
	return false
end

function trace_private_context_retained(trace)
	return trace and trace.context and trace.context.private_prompt ~= nil
end

local function finish_model_eval_case(case_report, final_reply, final_trace)
	final_trace = final_trace or trace_by_id(case_report.trace_id) or latest_request_trace()
	case_report.final_reply = compact_eval_reply(final_reply)
	case_report.final_trace = compact_eval_trace(final_trace)
	case_report.final_status = final_reply and final_reply.status
	case_report.final_reason = final_reply and final_reply.reason
	case_report.checks.final_reply_ok = final_reply and final_reply.ok == true
	case_report.checks.final_action = final_reply and final_reply.action == "model"
	case_report.checks.final_status = final_reply and final_reply.status == "success"
	case_report.checks.trace_route = final_trace
		and (final_trace.route == "model_adapter_async"
			or final_trace.route == "model_adapter")
	case_report.checks.trace_status = final_trace and final_trace.response
		and final_trace.response.status == "success"
	case_report.checks.trace_prompt = final_trace
		and final_trace.public_prompt == case_report.prompt
	case_report.checks.no_trace_private_context =
		not trace_private_context_retained(final_trace)
	local ok, failures = eval_checks_status(case_report.checks)
	case_report.ok = ok
	case_report.status = ok and "pass" or "fail"
	case_report.failures = failures
end

local function run_model_eval_case(report, owner, prompt, context, async_done)
	local case_report = {
		case_id = "model",
		prompt = prompt,
		checks = {},
	}
	report.cases[#report.cases + 1] = case_report
	local model_context = table.copy(context or {})
	model_context.private_prompt = "synthetic eval private prompt must not be retained"
	model_context.task_id = model_context.task_id or "ai-agent-eval:model"
	model_context.on_model_complete = function(final_reply, final_trace)
		case_report.completed_by_hook = true
		finish_model_eval_case(case_report, final_reply, final_trace)
		if case_report.initial_recorded then
			async_done()
		end
	end
	local initial_reply = plugin.handle_command(owner, prompt, model_context)
	local initial_trace = initial_reply and initial_reply.trace_id
		and trace_by_id(initial_reply.trace_id) or latest_request_trace()
	case_report.trace_id = initial_reply and initial_reply.trace_id
		or (initial_trace and initial_trace.trace_id)
	case_report.initial_reply = compact_eval_reply(initial_reply)
	case_report.initial_trace = compact_eval_trace(initial_trace)
	case_report.queued_status = initial_reply and initial_reply.status
	case_report.queued_reason = initial_reply and initial_reply.reason
	case_report.checks.initial_action = initial_reply and initial_reply.action == "model"
	case_report.checks.initial_trace_id = case_report.trace_id ~= nil
	case_report.checks.initial_not_blocked = initial_reply
		and (initial_reply.status == "queued" or initial_reply.status == "success")
	case_report.checks.initial_trace_route = initial_trace
		and (initial_trace.route == "model_adapter_async"
			or initial_trace.route == "model_adapter")
	case_report.checks.no_initial_trace_private_context =
		not trace_private_context_retained(initial_trace)
	case_report.initial_recorded = true
	if initial_reply and initial_reply.status == "queued"
			and not case_report.completed_by_hook then
		case_report.status = "queued"
		return true
	end
	if not case_report.completed_by_hook then
		finish_model_eval_case(case_report, initial_reply, initial_trace)
	end
	return false
end

local function normalize_eval_case(value)
	value = tostring(value or ""):lower():gsub("[%-_]", "")
	if value == "all" then
		return "all"
	elseif value == "fire" or value == "buildfire" then
		return "build_fire"
	elseif value == "fireonly" or value == "onlyfire"
			or value == "fireonlystrict" or value == "buildfireonly" then
		return "fire_only_strict"
	elseif value == "tnt" or value == "walltnt" or value == "tntwall" then
		return "tnt_wall"
	elseif value == "agentic" or value == "planner" or value == "buildplanner"
			or value == "agenticbuildplanner" or value == "shelter" then
		return "agentic_build_planner"
	elseif value == "model" or value == "unknown" or value == "adapter" then
		return "model"
	end
	return nil
end

local function parse_eval_cases(value)
	if not value or value == "" then
		return table.copy(EVAL_DEFAULT_CASES)
	end
	local cases = {}
	local seen = {}
	for raw_case in tostring(value):gmatch("[^,%s]+") do
		local case_id = normalize_eval_case(raw_case)
		if case_id == "all" then
			return table.copy(EVAL_DEFAULT_CASES)
		end
		if case_id and not seen[case_id] then
			seen[case_id] = true
			cases[#cases + 1] = case_id
		end
	end
	if #cases == 0 then
		return table.copy(EVAL_DEFAULT_CASES)
	end
	local ordered = {}
	for _, case_id in ipairs(cases) do
		if case_id ~= "model" then
			ordered[#ordered + 1] = case_id
		end
	end
	if seen.model then
		ordered[#ordered + 1] = "model"
	end
	return ordered
end

local function normalize_custom_eval_cases(value)
	local custom_cases = {}
	if type(value) ~= "table" then
		return custom_cases
	end
	for _, raw_case in ipairs(value) do
		if type(raw_case) == "table"
				and type(raw_case.case_id) == "string"
				and type(raw_case.prompt) == "string"
				and type(raw_case.expected) == "table" then
			local expected = table.copy(raw_case.expected)
			local action = expected.action or raw_case.action or "build"
			if action == "build"
					and type(expected.build_kind) == "string"
					and type(expected.build_material_name) == "string" then
				custom_cases[#custom_cases + 1] = {
					case_id = bounded_trace_text(raw_case.case_id, 120),
					case_hint = bounded_trace_text(raw_case.case_hint, 120),
					source_candidate_id =
						bounded_trace_text(raw_case.source_candidate_id, 160),
					prompt = bounded_trace_text(raw_case.prompt, 1000),
					expected = expected,
				}
			end
		end
	end
	return custom_cases
end

local function eval_report_ok(report)
	for _, case_report in ipairs(report.cases or {}) do
		if case_report.ok ~= true then
			return false
		end
	end
	return true
end

function plugin.run_prompt_eval(options, callback)
	assert(type(callback) == "function", "Field 'callback' must be a function")
	options = options or {}
	local owner = normalize_player_name(options.owner or options.name or "NovaEval")
	local custom_cases = normalize_custom_eval_cases(options.custom_cases)
	local normalized_case_param = tostring(options.cases or ""):lower():gsub("[%-_]", "")
	local custom_only = normalized_case_param == "custom"
		or normalized_case_param == "promoted"
	local cases = custom_only and {} or parse_eval_cases(options.cases)
	local before = core.get_ai_runtime_metrics()
	local finished = false
	local report = {
		schema_version = 1,
		operation = "ai_agent_plugin.run_prompt_eval",
		owner = owner,
		custom_case_count = #custom_cases,
		cases = {},
	}
	local function finish_report()
		if finished then
			return
		end
		finished = true
		local after = core.get_ai_runtime_metrics()
		report.metrics = {
			model_adapter_requests_delta =
				eval_metric_delta(before, after, "model_adapter_requests"),
			model_adapter_successes_delta =
				eval_metric_delta(before, after, "model_adapter_successes"),
			model_adapter_failures_delta =
				eval_metric_delta(before, after, "model_adapter_failures"),
			model_adapter_timeouts_delta =
				eval_metric_delta(before, after, "model_adapter_timeouts"),
		}
		report.safety = {
			audit_private_payload_retained =
				audit_payload_retained(core.get_ai_runtime_audit({ limit = 20 })),
		}
		report.ok = eval_report_ok(report)
			and report.safety.audit_private_payload_retained ~= true
		report.status = report.ok and "pass" or "fail"
		for _, case_report in ipairs(report.cases or {}) do
			case_report.completed_by_hook = nil
			case_report.initial_recorded = nil
		end
		callback(report)
	end
	local pending_async_count = 0
	local function async_case_done()
		if pending_async_count > 0 then
			pending_async_count = pending_async_count - 1
		end
		if pending_async_count == 0 then
			finish_report()
		end
	end
	local context = eval_context(options)
	if custom_only and #custom_cases == 0 then
		append_eval_case(report, {
			case_id = "custom_cases_missing",
			prompt = "",
			checks = {
				custom_cases_present = false,
			},
		})
	end
	for _, case_id in ipairs(cases) do
		if case_id == "build_fire" then
			local expected = {
				build_kind = "fire",
				build_material_name = "fire",
				build_material_node = settings.fire_node,
				planned_node_writes = 1,
				selected_candidate_id = "fire",
			}
			if agentic_build_planner_available() then
				expected.route = "agentic_build_planner"
				if run_agentic_build_eval_case(report, owner, "build a fire",
						context, async_case_done, case_id, expected) then
					pending_async_count = pending_async_count + 1
				end
			else
				run_build_eval_case(report, owner, case_id, "build a fire",
					context, expected)
			end
		elseif case_id == "fire_only_strict" then
			local expected = {
				build_kind = "fire",
				build_material_name = "fire",
				build_material_node = settings.fire_node,
				planned_node_writes = 1,
				selected_candidate_id = "fire",
			}
			if agentic_build_planner_available() then
				expected.route = "agentic_build_planner"
				if run_agentic_build_eval_case(report, owner,
						"build me a fire and only a fire", context,
						async_case_done, case_id, expected) then
					pending_async_count = pending_async_count + 1
				end
			else
				run_build_eval_case(report, owner, case_id,
					"build me a fire and only a fire", context, expected)
			end
		elseif case_id == "tnt_wall" then
			local expected = {
				build_kind = "wall",
				build_material_name = "tnt",
				build_material_node = settings.tnt_node,
				planned_node_writes = 12,
				selected_candidate_id = "tnt_wall",
			}
			if agentic_build_planner_available() then
				expected.route = "agentic_build_planner"
				if run_agentic_build_eval_case(report, owner, "build a wall of tnt",
						context, async_case_done, case_id, expected) then
					pending_async_count = pending_async_count + 1
				end
			else
				run_build_eval_case(report, owner, case_id, "build a wall of tnt",
					context, expected)
			end
		elseif case_id == "agentic_build_planner" then
			if run_agentic_build_eval_case(report, owner, "build a small shelter",
					context, async_case_done) then
				pending_async_count = pending_async_count + 1
			end
		elseif case_id == "model" then
			if run_model_eval_case(report, owner,
				options.model_prompt or EVAL_DEFAULT_MODEL_PROMPT,
				context, async_case_done) then
				pending_async_count = pending_async_count + 1
			end
		end
	end
	for _, custom_case in ipairs(custom_cases) do
		if custom_case.expected.route == "agentic_build_planner" then
			if run_agentic_build_eval_case(report, owner, custom_case.prompt,
					context, async_case_done, custom_case.case_id,
					custom_case.expected, {
						case_hint = custom_case.case_hint,
						source_candidate_id = custom_case.source_candidate_id,
					}) then
				pending_async_count = pending_async_count + 1
			end
		else
			run_build_eval_case(report, owner, custom_case.case_id,
				custom_case.prompt, context, custom_case.expected, {
					case_hint = custom_case.case_hint,
					source_candidate_id = custom_case.source_candidate_id,
				})
		end
	end
	if pending_async_count > 0 and not finished then
		return true, "queued"
	end
	finish_report()
	return true, "completed"
end

local function encode_prompt_eval_report(report)
	local encoded = core.write_json(report)
	if #encoded <= EVAL_MAX_OUTPUT_BYTES then
		return encoded
	end
	return core.write_json({
		schema_version = report.schema_version,
		operation = report.operation,
		owner = report.owner,
		ok = report.ok,
		status = report.status,
		reason = "prompt_eval_report_truncated",
		case_count = #(report.cases or {}),
		metrics = report.metrics,
		safety = report.safety,
	})
end

local function parse_prompt_eval_command(param)
	local raw = tostring(param or ""):trim()
	local model_prompt = raw:match("^[Mm][Oo][Dd][Ee][Ll]%s+(.+)$")
		or raw:match("^[Pp][Rr][Oo][Mm][Pp][Tt]%s+(.+)$")
	if model_prompt then
		return {
			cases = "model",
			model_prompt = model_prompt:trim(),
		}
	end
	local options = {}
	for token in raw:gmatch("%S+") do
		local key, value = token:match("^([%w_]+)=(.+)$")
		if key and value then
			key = key:lower()
			if key == "case" or key == "cases" then
				options.cases = value
			elseif key == "agent" or key == "owner" or key == "name" then
				options.owner = value
			elseif key == "prompt" then
				options.model_prompt = value
				options.cases = options.cases or "model"
			end
		else
			local case_id = normalize_eval_case(token)
			if case_id then
				options.cases = token
			end
		end
	end
	return options
end

core.register_chatcommand("ai_agent_eval", {
	params = "[case=all|fire|fire_only|tnt|agentic|model] [agent=NAME] OR model <prompt>",
	description = "Run a bounded first-party AI agent prompt evaluation and emit public-safe JSON.",
	privs = { server = true },
	func = function(name, param)
		local options = parse_prompt_eval_command(param)
		options.owner = options.owner or name or "NovaEval"
		local immediate_report
		local returned_to_player = false
		local queued, reason = plugin.run_prompt_eval(options, function(report)
			local encoded = encode_prompt_eval_report(report)
			core.log("action", "[ai_agent_plugin] prompt_eval result=" .. encoded)
			if returned_to_player and name and name ~= "" and core.chat_send_player then
				core.chat_send_player(name, encoded)
			end
			immediate_report = encoded
		end)
		if not queued then
			return false, reason
		end
		if immediate_report then
			return true, immediate_report
		end
		returned_to_player = true
		return true, "AI agent prompt evaluation queued."
	end,
})

core.register_chatcommand("ai_agent_feedback", {
	params = "last; case=CASE; build_kind=KIND; material=MATERIAL; planned_writes=N",
	description = "Record public-safe reviewed AI agent feedback for prompt-eval promotion.",
	privs = { server = true },
	func = function(name, param)
		local result = plugin.record_operator_feedback(name or "Operator", param or "")
		return result.ok, core.write_json(result)
	end,
})

local function register_command(name)
	core.register_chatcommand(name, {
		params = "<message>",
		description = "Control your first-party AI agent.",
		privs = { interact = true },
		func = function(player_name, param)
			local result = plugin.handle_command(player_name, param or "")
			return result.ok, plugin.format_reply(result)
		end,
	})
end

register_command("bot")
register_command("nova")
register_command("aibot")

if core.register_on_chat_message then
	core.register_on_chat_message(function(name, message)
		return plugin.handle_natural_chat_message(name, message)
	end)
end

plugin._player_loop.globalstep_elapsed = 0
if core.register_globalstep then
	core.register_globalstep(function(dtime)
		if settings.player_loop_auto_review_enabled ~= true then
			return
		end
		plugin._player_loop.globalstep_elapsed =
			(plugin._player_loop.globalstep_elapsed or 0) + (dtime or 0)
		local interval = settings.player_loop_review_interval or 1.0
		if plugin._player_loop.globalstep_elapsed < interval then
			return
		end
		plugin._player_loop.globalstep_elapsed = 0
		plugin.step_player_agent_loops()
	end)
end
