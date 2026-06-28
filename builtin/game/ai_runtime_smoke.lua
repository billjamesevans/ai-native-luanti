core.ai_runtime_smoke = {}

local smoke = core.ai_runtime_smoke

local function copy_pos(pos)
	return {
		x = pos.x,
		y = pos.y,
		z = pos.z,
	}
end

local function offset_pos(pos, x, y, z)
	return {
		x = pos.x + x,
		y = pos.y + y,
		z = pos.z + z,
	}
end

local function task_id_part(value)
	return tostring(value):gsub("[^%w._-]", "_")
end

local function task_prefix_for(agent_id)
	local base = "ai-runtime-smoke:" .. task_id_part(agent_id)
	local prefix = base
	local suffix = 1
	while core.get_ai_task(prefix .. ":build") or core.get_ai_task(prefix .. ":repair") do
		suffix = suffix + 1
		prefix = base .. ":" .. suffix
	end
	return prefix
end

local function world_key(pos)
	return pos.x .. ":" .. pos.y .. ":" .. pos.z
end

local function make_world()
	local world = {}
	return world,
		function(pos)
			return table.copy(world[world_key(pos)] or {
				name = "air",
				param1 = 0,
				param2 = 0,
			})
		end,
		function(pos, node)
			world[world_key(pos)] = {
				name = node.name,
				param1 = node.param1 or 0,
				param2 = node.param2 or 0,
			}
			return true
		end
end

local function ensure_agent(agent_id, owner)
	local existing = core.get_ai_agent(agent_id)
	if existing then
		return existing
	end
	return core.register_ai_agent({
		agent_id = agent_id,
		display_name = "Synthetic Smoke Agent",
		owner = owner,
		plugin = "ai_runtime_smoke",
		capabilities = {
			["world.read"] = true,
			["world.place"] = true,
			["world.remove"] = true,
		},
		limits = {
			max_nodes_per_step = 4,
		},
	})
end

local function summarize_result(result)
	result = result or {}
	local metrics = result.metrics or {}
	return {
		operation = result.operation,
		ok = result.ok,
		status = result.status,
		reason = result.reason,
		changed = result.changed or 0,
		examined = result.examined or 0,
		skipped = result.skipped or 0,
		rollback_record_id = result.rollback_record_id,
		rollback_storage_ref = result.rollback_storage_ref,
		metrics = {
			node_writes = metrics.node_writes or 0,
			candidate_count = metrics.candidate_count or 0,
			rollback_records = metrics.rollback_records or 0,
			rollback_failures = metrics.rollback_failures or 0,
		},
	}
end

local function summarize_task(task)
	return {
		task_id = task.task_id,
		status = task.status,
		label = task.label,
		progress = table.copy(task.progress or {}),
		result = summarize_result(task.last_result),
	}
end

local function add_outcome(outcomes, task)
	local result = task.last_result or {}
	if task.status == "completed" and result.ok ~= false
			and result.status ~= "blocked" and result.status ~= "unsafe"
			and result.status ~= "failed" then
		return
	end
	outcomes[#outcomes + 1] = {
		task_id = task.task_id,
		task_status = task.status,
		result_status = result.status,
		reason = result.reason,
		operation = result.operation,
	}
end

local function smoke_status(outcomes)
	if #outcomes == 0 then
		return true, "success"
	end
	for _, outcome in ipairs(outcomes) do
		if outcome.result_status == "unsafe" or outcome.task_status == "unsafe" then
			return false, "unsafe"
		end
	end
	for _, outcome in ipairs(outcomes) do
		if outcome.result_status == "blocked" or outcome.task_status == "blocked" then
			return false, "blocked"
		end
	end
	return false, "failed"
end

local function audit_events_for(task_ids)
	local events = {}
	for _, record in ipairs(core.get_ai_runtime_audit({ limit = 200 })) do
		if task_ids[record.task_id] then
			events[#events + 1] = {
				event_type = record.event_type,
				task_id = record.task_id,
				status = record.status,
				reason = record.reason,
				operation = record.operation,
				rollback_record_id = record.rollback_record_id,
				mutation_class = record.mutation_class,
				changed = record.changed,
				skipped = record.skipped,
			}
		end
	end
	return events
end

function smoke.run_scenario(options)
	options = options or {}
	local agent_id = options.agent_id or "ai_runtime_smoke:agent"
	local owner = options.owner or "synthetic-operator"
	local world_id = options.world_id or "synthetic-smoke-world"
	local origin = copy_pos(options.origin or { x = 0, y = 32, z = 0 })
	local build_node = options.build_node or "default:stone"
	local repair_node = options.repair_node or build_node
	local replacement_node = options.replacement_node or "air"
	local prefix = task_prefix_for(agent_id)
	local build_task_id = prefix .. ":build"
	local repair_task_id = prefix .. ":repair"
	local build_pos = copy_pos(origin)
	local repair_pos = offset_pos(origin, 2, 0, 0)
	local _, get_node, set_node = make_world()
	local rollback_records = {}

	ensure_agent(agent_id, owner)
	set_node(build_pos, { name = "air" })
	set_node(repair_pos, { name = repair_node })

	local function persist_record(record)
		rollback_records[#rollback_records + 1] = {
			record_id = record.record_id,
			mutation_class = record.mutation_class,
			operation_label = record.operation_label,
			changed_count = #(record.changed_positions or {}),
		}
		return {
			ok = true,
			storage_ref = "rollback://smoke/" .. record.record_id,
		}
	end

	core.build_agent.configure({
		marker_node = build_node,
		max_nodes_per_task = 4,
		sample_limit = 4,
	})
	core.repair_agent.configure({
		repair_nodes = {
			[repair_node] = replacement_node == "air" and {
				planned_action = "remove_node",
				replacement = "air",
				family = "synthetic-smoke",
			} or {
				planned_action = "replace_node",
				replacement = replacement_node,
				family = "synthetic-smoke",
			},
		},
		radius = 0,
		sample_limit = 4,
	})

	core.queue_ai_task(core.build_agent.define_task({
		kind = "marker",
		task_id = build_task_id,
		agent_id = agent_id,
		owner = owner,
		world_id = world_id,
		origin = build_pos,
		get_node = get_node,
		set_node = set_node,
		max_node_writes_per_step = 1,
		persist_record = persist_record,
	}))
	core.step_ai_tasks()

	local repair_plan = core.repair_agent.plan_area(repair_pos, {
		agent_id = agent_id,
		owner = owner,
		task_id = prefix .. ":repair-plan",
		radius = 0,
		get_node = get_node,
		set_node = set_node,
		sample_limit = 4,
	})
	local repair_task = {
		task_id = repair_task_id,
		agent_id = agent_id,
		owner = owner,
		world_id = world_id,
		plan = repair_plan,
		get_node = get_node,
		set_node = set_node,
		allow_mutation = true,
		allow_hazards = true,
		max_node_writes_per_step = 1,
	}
	if not options.block_repair_rollback then
		repair_task.persist_record = persist_record
	end
	core.repair_agent.queue_apply_task(repair_task)
	core.step_ai_tasks()

	local build_task = core.get_ai_task(build_task_id)
	local completed_repair_task = core.get_ai_task(repair_task_id)
	local outcomes = {}
	add_outcome(outcomes, build_task)
	add_outcome(outcomes, completed_repair_task)
	local ok, status = smoke_status(outcomes)
	local task_ids = {
		[build_task_id] = true,
		[repair_task_id] = true,
	}
	local audit_events = audit_events_for(task_ids)

	return {
		schema_version = 1,
		operation = "ai_runtime_smoke.run_scenario",
		ok = ok,
		status = status,
		agent_id = agent_id,
		owner_ref = owner,
		world_id = world_id,
		run_context = {
			mode = "synthetic-task-loop-smoke",
			requires_private_world = false,
			requires_private_assets = false,
			requires_live_pi = false,
			requires_model_network = false,
		},
		tasks = {
			build = summarize_task(build_task),
			repair = summarize_task(completed_repair_task),
		},
		task_statuses = {
			build = build_task.status,
			repair = completed_repair_task.status,
		},
		results = {
			build = summarize_result(build_task.last_result),
			repair = summarize_result(completed_repair_task.last_result),
		},
		rollback_records = #rollback_records,
		rollback_record_summaries = rollback_records,
		audit_event_count = #audit_events,
		audit_events = audit_events,
		blocked_or_unsafe_outcomes = outcomes,
		world_after = {
			build_node = get_node(build_pos).name,
			repair_node = get_node(repair_pos).name,
		},
		notes = {
			"Scenario uses an in-memory synthetic world and no live server.",
			"Summary intentionally omits prompts, asset payloads, local paths, and player-private data.",
		},
	}
end
