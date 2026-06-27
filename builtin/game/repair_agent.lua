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

local function finish_result(result, ok, status, reason, message)
	result.ok = ok
	result.status = status
	result.reason = reason
	result.message = message
	result.metrics.candidate_count = #result.candidates
	return result
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
