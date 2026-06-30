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
local model_adapter = nil
local default_capabilities = {}
local settings = {
	capability_profile = nil,
	light_node = "default:torch",
	marker_node = "default:mese_post_light",
	platform_node = "default:stone",
	path_node = "default:stone",
	fire_node = "fire:basic_flame",
	wall_node = "default:stone",
	tnt_node = "tnt:tnt",
	build_material_nodes = {},
	agent_entity_name = "ai_demo_benchmark:helper",
	repair_nodes = {},
	max_lights = 12,
	max_request_traces = 50,
	max_entity_move_distance = 16,
	max_follow_steps = 6,
	max_follow_step_distance = 4,
	max_follow_total_distance = 24,
	max_follow_stop_distance = 1,
	max_follow_wall_time_ms = 250,
	max_navigation_nodes = 64,
	max_repair_radius = 2,
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
		commands = {
			"build plan",
			"build marker",
			"build plan platform width N depth N",
			"build platform width N depth N",
			"build fire",
			"build wall width N height N",
			"build wall of tnt",
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
			"tasks",
			"task <task_id>",
			"traces",
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
	}
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
	return remember_request_trace({
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
end

local function finish_request_trace(trace, result, extra)
	if not trace then
		return result
	end
	extra = extra or {}
	trace.completed_us = trace_timestamp_us()
	trace.response = {
		ok = result and result.ok or false,
		status = result and result.status,
		action = result and result.action,
		reason = result and result.reason,
		message = bounded_trace_text(result and result.message, 1000),
		approval_id = result and result.approval_id,
		task_id = result and result.task_id,
		build_kind = result and result.build_kind,
		build_width = result and result.build_width,
		build_depth = result and result.build_depth,
		build_height = result and result.build_height,
		build_material_name = result and result.build_material_name,
		build_material_node = result and result.build_material_node,
		planned_node_writes = result and result.planned_node_writes,
	}
	for key, value in pairs(extra) do
		trace[key] = value
	end
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

function plugin.get_model_traces(options)
	return plugin.get_request_traces(options)
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
	if result.agent_id then
		append(lines, "agent_id=" .. tostring(result.agent_id))
	end
	return table.concat(lines, "\n")
end

plugin.format_reply = format_command_reply

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
	return nil
end

local function parse_named_build_int(lower_prompt, name)
	return parse_build_positive_int(lower_prompt:match(name .. "%s+([%-%d]+)"))
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
	if lower:find("wall", 1, true) then
		parsed.build_kind = "wall"
		parsed.build_material_name = material_name
		parsed.build_material_node = resolve_build_material_node(
			material_name, settings.wall_node)
		if not parsed.build_material_node then
			return nil, "build_material_unavailable"
		end
		local x_width, x_height = lower:match("(%d+)%s*x%s*(%d+)")
		local width = parse_named_build_int(lower, "width")
			or parse_named_build_int(lower, "wide")
			or parse_named_build_int(lower, "length")
			or parse_build_positive_int(x_width or "4")
		local height = parse_named_build_int(lower, "height")
			or parse_named_build_int(lower, "high")
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
	else
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

local function handle_build(name, context)
	context = context or {}
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
	})
	return public_reply(name, "build", "pending_approval",
		"Build plan is pending approval before mutation.", {
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
			"tasks",
			"task <task_id>",
			"traces",
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
		traces = plugin.get_request_traces({ limit = 25 }),
	})
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
	return queued
end

local function handle_model(name, prompt, context)
	context = context or {}
	local trace = start_request_trace(name, "model", "model_adapter", prompt, context, {
		adapter_name = context.adapter_name or "ai_agent_plugin",
	})
	local result = core.ai_model_ops.request(prompt, {
		agent_id = agent_id_for(name),
		owner = name,
		task_id = context.task_id,
		private_prompt = context.private_prompt,
		adapter = model_adapter,
		adapter_name = context.adapter_name or "ai_agent_plugin",
		context = context,
	})
	return finish_request_trace(trace, public_reply(name, "model",
		result.ok and "success" or "blocked",
		result.message or "Model adapter did not return a response.", {
			reason = result.reason,
		}), {
			adapter_name = context.adapter_name or "ai_agent_plugin",
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
	if prompt == "traces" or prompt == "trace" or prompt == "logs"
			or prompt == "model traces" or prompt == "request traces" then
		return handle_request_traces(name)
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
		local trace = start_request_trace(name, "build_plan",
			"deterministic_build_parser", raw_prompt, context, {
				surface_id = "builder",
			})
		local build_context, reason = parse_build_options(raw_prompt, context)
		if not build_context then
			return finish_request_trace(trace, public_reply(name, "build_plan", "blocked",
				"Build plan parameters are outside the configured bounds.", {
					surface_id = "builder",
					reason = reason,
				}))
		end
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
	if prompt:find("build", 1, true) or prompt:find("marker", 1, true) then
		local trace = start_request_trace(name, "build",
			"deterministic_build_parser", raw_prompt, context, {
				surface_id = "builder",
			})
		local build_context, reason = parse_build_options(raw_prompt, context)
		if not build_context then
			return finish_request_trace(trace, public_reply(name, "build", "blocked",
				"Build parameters are outside the configured bounds.", {
					surface_id = "builder",
					reason = reason,
				}))
		end
		trace.context = compact_trace_context(build_context)
		return finish_request_trace(trace, handle_build(name, build_context), {
			selected_intent = build_context.build_kind,
			build_material_node = build_context.build_material_node,
		})
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
			return result.ok, plugin.format_reply(result)
		end,
	})
end

register_command("bot")
register_command("nova")
register_command("aibot")
