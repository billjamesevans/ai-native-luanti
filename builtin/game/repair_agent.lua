core.repair_agent = {}

local repair_agent = core.repair_agent
local settings = {
	repair_nodes = {},
	radius = 1,
	sample_limit = 8,
}

local function copy_pos(pos)
	return {
		x = pos.x,
		y = pos.y,
		z = pos.z,
	}
end

local function normalize_repair_rule(rule)
	if rule == true then
		return {
			planned_action = "remove_node",
			replacement = "air",
			family = "generic",
		}
	end
	if type(rule) == "string" then
		return {
			planned_action = "replace_node",
			replacement = rule,
			family = "generic",
		}
	end
	assert(type(rule) == "table", "Repair node rule must be true, a replacement string, or a table")
	return {
		planned_action = rule.planned_action or "remove_node",
		replacement = rule.replacement or "air",
		family = rule.family or "generic",
	}
end

local function normalize_repair_nodes(repair_nodes)
	local normalized = {}
	for node_name, rule in pairs(repair_nodes or {}) do
		assert(type(node_name) == "string" and node_name ~= "",
			"Repair node names must be non-empty strings")
		normalized[node_name] = normalize_repair_rule(rule)
	end
	return normalized
end

local function repair_node_filter(repair_nodes)
	local node_names = {}
	for node_name in pairs(repair_nodes) do
		node_names[node_name] = true
	end
	return {
		node_names = node_names,
	}
end

local function copy_samples(samples)
	local copied = {}
	for _, sample in ipairs(samples or {}) do
		local item = table.copy(sample)
		if sample.pos then
			item.pos = copy_pos(sample.pos)
		end
		if sample.node then
			item.node = table.copy(sample.node)
		end
		copied[#copied + 1] = item
	end
	return copied
end

local function make_result(options)
	return {
		ok = false,
		status = "error",
		operation = "repair_agent.plan_area",
		agent_id = options.agent_id,
		task_id = options.task_id,
		changed = 0,
		examined = 0,
		skipped = 0,
		reason = "not_planned",
		message = "Repair planning did not run.",
		candidates = {},
		samples = {},
		metrics = {
			node_writes = 0,
			candidate_count = 0,
		},
	}
end

local function make_apply_result(options)
	return {
		ok = false,
		status = "error",
		operation = "repair_agent.apply_plan",
		agent_id = options.agent_id,
		task_id = options.task_id,
		changed = 0,
		examined = 0,
		skipped = 0,
		reason = "not_applied",
		message = "Repair mutation did not run.",
		samples = {},
		metrics = {
			node_writes = 0,
			candidate_count = 0,
			rollback_records = 0,
			rollback_failures = 0,
		},
	}
end

local function finish_result(result, ok, status, reason, message)
	result.ok = ok
	result.status = status
	result.reason = reason
	result.message = message
	result.metrics.candidate_count = #result.candidates
	return result
end

local function finish_apply_result(result, status, reason, message)
	result.ok = status == "success" or status == "partial"
	result.status = status
	result.reason = reason
	result.message = message
	return result
end

local function apply_sample_limit(options)
	if options.sample_limit ~= nil then
		assert(type(options.sample_limit) == "number" and options.sample_limit >= 0,
			"Repair sample limit must be a non-negative number")
		return math.floor(options.sample_limit)
	end
	return settings.sample_limit
end

local function add_apply_sample(result, options, sample)
	if #result.samples >= apply_sample_limit(options) then
		return
	end
	local copied = table.copy(sample)
	if sample.pos then
		copied.pos = copy_pos(sample.pos)
	end
	if sample.node then
		copied.node = table.copy(sample.node)
	end
	result.samples[#result.samples + 1] = copied
end

local function repair_write_budget(options, candidate_count)
	local max_writes = options.max_node_writes or options.max_changes
		or options.max_node_writes_per_step or candidate_count
	assert(type(max_writes) == "number" and max_writes >= 0,
		"Repair max node writes must be a non-negative number")
	return math.floor(max_writes)
end

local function select_repair_candidates(candidates, max_writes)
	local selected = {}
	local skipped = {}
	for _, candidate in ipairs(candidates) do
		if #selected < max_writes then
			selected[#selected + 1] = candidate
		else
			skipped[#skipped + 1] = {
				reason = "max_changes_reached",
				message = "Repair write budget was reached.",
				pos = copy_pos(candidate.pos),
				node = {
					name = candidate.node_name,
				},
			}
		end
	end
	return selected, skipped
end

local function apply_candidate(candidate, options)
	local op_options = {
		agent_id = options.agent_id,
		task_id = options.task_id,
		owner = options.owner,
		get_node = options.get_node,
		set_node = options.set_node,
		bounds = options.bounds,
		allow_hazards = options.allow_hazards == true,
		min_player_distance = options.min_player_distance,
		sample_limit = options.sample_limit or settings.sample_limit,
	}
	if candidate.planned_action == "replace_node" then
		return core.ai_world_ops.replace_node(candidate.pos, candidate.node_name,
			candidate.replacement or "air", op_options)
	end
	return core.ai_world_ops.remove_node(candidate.pos, op_options)
end

local function aggregate_candidate_result(result, options, candidate_result)
	result.changed = result.changed + (candidate_result.changed or 0)
	result.skipped = result.skipped + (candidate_result.skipped or 0)
	result.metrics.node_writes = result.metrics.node_writes
		+ (candidate_result.metrics and candidate_result.metrics.node_writes or 0)
	for _, sample in ipairs(candidate_result.samples or {}) do
		add_apply_sample(result, options, sample)
	end
end

function repair_agent.configure(options)
	options = options or {}
	if options.repair_nodes then
		settings.repair_nodes = normalize_repair_nodes(options.repair_nodes)
	end
	if options.radius then
		assert(type(options.radius) == "number" and options.radius >= 0,
			"Repair radius must be a non-negative number")
		settings.radius = math.floor(options.radius)
	end
	if options.sample_limit then
		assert(type(options.sample_limit) == "number" and options.sample_limit >= 0,
			"Repair sample limit must be a non-negative number")
		settings.sample_limit = math.floor(options.sample_limit)
	end
end

function repair_agent.plan_area(center, options)
	options = options or {}
	local repair_nodes = normalize_repair_nodes(options.repair_nodes or settings.repair_nodes)
	local radius = options.radius or settings.radius
	local result = make_result(options)
	local inspect_options = table.copy(options)
	inspect_options.sample_limit = options.sample_limit or settings.sample_limit
	inspect_options.set_node = nil

	local inspected = core.ai_world_ops.inspect_area(center, radius,
		repair_node_filter(repair_nodes), inspect_options)
	result.examined = inspected.examined
	result.skipped = inspected.skipped
	result.samples = copy_samples(inspected.samples)
	result.metrics.elapsed_us = inspected.metrics and inspected.metrics.elapsed_us or 0

	for _, sample in ipairs(inspected.samples or {}) do
		if sample.reason == "matched" and sample.node and repair_nodes[sample.node.name] then
			local rule = repair_nodes[sample.node.name]
			result.candidates[#result.candidates + 1] = {
				pos = copy_pos(sample.pos),
				node_name = sample.node.name,
				planned_action = rule.planned_action,
				replacement = rule.replacement,
				family = rule.family,
				reason = "configured_repair_node",
			}
		end
	end

	if inspected.status == "blocked" then
		return finish_result(result, false, "blocked", inspected.reason,
			"No repair plan could be created because all positions were skipped.")
	end
	if #result.candidates == 0 then
		return finish_result(result, true, "success", "no_repair_candidates",
			"No configured repair candidates were found.")
	end
	if result.skipped > 0 then
		return finish_result(result, true, "partial", "repair_candidates_with_skips",
			"Repair candidates were found, with skipped positions.")
	end
	return finish_result(result, true, "success", "repair_candidates_found",
		"Repair candidates were found.")
end

function repair_agent.queue_plan_task(def)
	assert(type(def) == "table", "Repair plan task definition must be a table")
	assert(type(def.center) == "table", "Repair plan task center is required")
	local task_def = table.copy(def)
	return core.queue_ai_task({
		task_id = def.task_id,
		agent_id = def.agent_id,
		owner = def.owner,
		label = def.label or "repair plan",
		budget = {
			max_steps_per_step = 1,
			max_node_writes_per_step = 0,
		},
		steps = {
			function(ctx)
				task_def.agent_id = ctx.agent_id
				task_def.owner = ctx.owner
				task_def.task_id = ctx.task_id
				return repair_agent.plan_area(def.center, task_def)
			end,
		},
	})
end

function repair_agent.apply_plan(plan, options)
	assert(type(plan) == "table", "Repair apply plan must be a table")
	options = options or {}
	local candidates = plan.candidates or {}
	assert(type(candidates) == "table", "Repair apply plan candidates must be a table")
	local result = make_apply_result(options)
	result.examined = #candidates
	result.metrics.candidate_count = #candidates

	if #candidates == 0 then
		return finish_apply_result(result, "success", "no_repair_candidates",
			"No repair candidates were supplied.")
	end
	if options.allow_mutation ~= true then
		return finish_apply_result(result, "blocked", "repair_mutation_not_enabled",
			"Repair mutation requires explicit allow_mutation.")
	end
	if options.agent_id and not core.agent_has_capability(options.agent_id, "world.place") then
		return finish_apply_result(result, "blocked", "missing_capability",
			"Repair mutation requires world.place capability.")
	end

	local max_writes = repair_write_budget(options, #candidates)
	local selected, budget_skips = select_repair_candidates(candidates, max_writes)
	for _, sample in ipairs(budget_skips) do
		result.skipped = result.skipped + 1
		add_apply_sample(result, options, sample)
	end
	if #selected == 0 then
		return finish_apply_result(result, "blocked", "max_changes_reached",
			"Repair write budget was reached before mutation.")
	end

	local positions = {}
	for _, candidate in ipairs(selected) do
		positions[#positions + 1] = copy_pos(candidate.pos)
	end

	local rollback_result = core.run_ai_world_mutation_with_rollback({
		record_id = options.rollback_record_id,
		policy = options.rollback_policy or "snapshot",
		world_id = options.world_id,
		task_id = options.task_id or plan.task_id,
		agent_id = options.agent_id or plan.agent_id,
		owner_ref = options.owner or plan.owner,
		operation_label = options.operation_label or "repair_agent.apply_plan",
		mutation_class = "repair",
		bounds = options.bounds,
		positions = positions,
		get_node = options.get_node,
		persist_record = options.persist_record or options.persist_rollback_record,
	}, function()
		for _, candidate in ipairs(selected) do
			aggregate_candidate_result(result, options, apply_candidate(candidate, options))
		end
		if result.changed > 0 and result.skipped > 0 then
			return finish_apply_result(result, "partial", "repair_operations_skipped",
				"Some repair operations were skipped.")
		end
		if result.changed > 0 then
			return finish_apply_result(result, "success", "repair_applied",
				"Repair operations were applied.")
		end
		return finish_apply_result(result, "blocked", "all_repair_operations_skipped",
			"All repair operations were skipped.")
	end)

	if not rollback_result.ok and rollback_result.reason == "rollback_metadata_unavailable" then
		result.metrics.rollback_failures = 1
		result.skipped = #candidates
		return finish_apply_result(result, "blocked", "rollback_metadata_unavailable",
			rollback_result.message or "Rollback metadata is unavailable.")
	end
	if rollback_result.rollback_record_id then
		rollback_result.metrics = rollback_result.metrics or result.metrics
		rollback_result.metrics.rollback_records = 1
	end
	return rollback_result
end

function repair_agent.queue_apply_task(def)
	assert(type(def) == "table", "Repair apply task definition must be a table")
	assert(type(def.plan) == "table", "Repair apply task plan is required")
	local max_writes = def.max_node_writes_per_step or def.max_node_writes
		or #(def.plan.candidates or {})
	local task_def = table.copy(def)
	return core.queue_ai_task({
		task_id = def.task_id,
		agent_id = def.agent_id,
		owner = def.owner,
		label = def.label or "repair apply",
		budget = {
			max_steps_per_step = 1,
			max_node_writes_per_step = max_writes,
		},
		steps = {
			function(ctx)
				task_def.agent_id = ctx.agent_id
				task_def.owner = ctx.owner
				task_def.task_id = ctx.task_id
				task_def.max_node_writes = max_writes
				return repair_agent.apply_plan(def.plan, task_def)
			end,
		},
	})
end
