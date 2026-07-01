core.build_agent = {}

local build_agent = core.build_agent
local settings = {
	light_node = "default:torch",
	marker_node = "default:mese_post_light",
	platform_node = "default:stone",
	path_node = "default:stone",
	fire_node = "fire:basic_flame",
	wall_node = "default:stone",
	house_node = "default:stone",
	cabin_node = "default:wood",
	landmark_node = "default:stone",
	max_nodes_per_task = 32,
	sample_limit = 8,
}

local function copy_pos(pos)
	assert(type(pos) == "table", "Position must be a table")
	return {
		x = pos.x,
		y = pos.y,
		z = pos.z,
	}
end

local function offset_pos(origin, x, y, z)
	return {
		x = origin.x + x,
		y = origin.y + y,
		z = origin.z + z,
	}
end

local function positive_int(value, fallback)
	value = value or fallback
	assert(type(value) == "number" and value >= 1, "Build dimensions must be positive numbers")
	return math.floor(value)
end

local function clamp_count(value)
	return math.max(1, math.min(value, settings.max_nodes_per_task))
end

local function add_placement(placements, pos, node_name)
	placements[#placements + 1] = {
		pos = copy_pos(pos),
		node_name = node_name,
	}
end

local function placement_budget(options)
	local budget = settings.max_nodes_per_task
	if options and options.max_node_writes_per_step then
		budget = math.min(budget,
			positive_int(options.max_node_writes_per_step, budget))
	end
	return budget
end

local function add_placement_if_room(placements, pos, node_name, budget)
	if #placements >= budget then
		return false
	end
	add_placement(placements, pos, node_name)
	return true
end

local function material_node(options, fallback_field)
	local node_name = options.material_node or options.node_name or settings[fallback_field]
	assert(type(node_name) == "string" and node_name ~= "",
		"Build material node must be a non-empty string")
	return node_name
end

local function placement_positions(placements)
	local positions = {}
	for _, placement in ipairs(placements) do
		positions[#positions + 1] = copy_pos(placement.pos)
	end
	return positions
end

local function placement_samples(placements, limit)
	local samples = {}
	limit = math.min(limit or settings.sample_limit, #placements)
	for index = 1, limit do
		local placement = placements[index]
		samples[#samples + 1] = {
			pos = copy_pos(placement.pos),
			node = {
				name = placement.node_name,
			},
			planned_action = "place_node",
		}
	end
	return samples
end

local function light_placements(origin, options)
	local placements = {}
	local count = clamp_count(positive_int(options.count, 1))
	local node_name = material_node(options, "light_node")
	for index = 0, count - 1 do
		add_placement(placements, offset_pos(origin, index, 1, 0), node_name)
	end
	return placements
end

local function marker_placements(origin, options)
	local placements = {}
	add_placement(placements, origin, material_node(options, "marker_node"))
	return placements
end

local function platform_placements(origin, options)
	local placements = {}
	local width = positive_int(options.width, 2)
	local depth = positive_int(options.depth, 2)
	local node_name = material_node(options, "platform_node")
	while width * depth > settings.max_nodes_per_task do
		if depth >= width and depth > 1 then
			depth = depth - 1
		elseif width > 1 then
			width = width - 1
		else
			break
		end
	end
	for x = 0, width - 1 do
		for z = 0, depth - 1 do
			add_placement(placements, offset_pos(origin, x, 0, z), node_name)
		end
	end
	return placements
end

local function path_placements(origin, options)
	local placements = {}
	local length = clamp_count(positive_int(options.length, 3))
	local direction = options.direction or { x = 1, y = 0, z = 0 }
	local dx = direction.x or 0
	local dz = direction.z or 0
	if dx == 0 and dz == 0 then
		dx = 1
	end
	dx = dx == 0 and 0 or (dx > 0 and 1 or -1)
	dz = dz == 0 and 0 or (dz > 0 and 1 or -1)
	local node_name = material_node(options, "path_node")
	for index = 0, length - 1 do
		add_placement(placements, offset_pos(origin, dx * index, 0, dz * index), node_name)
	end
	return placements
end

local function fire_placements(origin, options)
	local placements = {}
	local count = clamp_count(positive_int(options.count, 1))
	local node_name = material_node(options, "fire_node")
	for index = 0, count - 1 do
		add_placement(placements, offset_pos(origin, index, 0, 0), node_name)
	end
	return placements
end

local function wall_placements(origin, options)
	local placements = {}
	local width = positive_int(options.width, 4)
	local height = positive_int(options.height, 3)
	local node_name = material_node(options, "wall_node")
	while width * height > settings.max_nodes_per_task do
		if width >= height and width > 1 then
			width = width - 1
		elseif height > 1 then
			height = height - 1
		else
			break
		end
	end
	for x = 0, width - 1 do
		for y = 0, height - 1 do
			add_placement(placements, offset_pos(origin, x, y, 0), node_name)
		end
	end
	return placements
end

local function corner_offsets(width, depth)
	local corners = {
		{ x = 0, z = 0 },
		{ x = width - 1, z = 0 },
		{ x = 0, z = depth - 1 },
		{ x = width - 1, z = depth - 1 },
	}
	local unique = {}
	local seen = {}
	for _, corner in ipairs(corners) do
		local key = corner.x .. ":" .. corner.z
		if not seen[key] then
			seen[key] = true
			unique[#unique + 1] = corner
		end
	end
	return unique
end

local function shell_placements(origin, options, fallback_field)
	local placements = {}
	local width = positive_int(options.width, 3)
	local depth = positive_int(options.depth, 2)
	local height = positive_int(options.height, 3)
	local node_name = material_node(options, fallback_field)
	local budget = placement_budget(options)
	while width * depth > budget do
		if width >= depth and width > 1 then
			width = width - 1
		elseif depth > 1 then
			depth = depth - 1
		else
			break
		end
	end
	for x = 0, width - 1 do
		for z = 0, depth - 1 do
			if not add_placement_if_room(placements,
					offset_pos(origin, x, 0, z), node_name, budget) then
				return placements
			end
		end
	end
	local corners = corner_offsets(width, depth)
	for y = 1, height - 1 do
		for _, corner in ipairs(corners) do
			if not add_placement_if_room(placements,
					offset_pos(origin, corner.x, y, corner.z), node_name, budget) then
				return placements
			end
		end
	end
	return placements
end

local function house_placements(origin, options)
	return shell_placements(origin, options, "house_node")
end

local function cabin_placements(origin, options)
	return shell_placements(origin, options, "cabin_node")
end

local function landmark_placements(origin, options)
	local placements = {}
	local width = positive_int(options.width, 3)
	local depth = positive_int(options.depth, 3)
	local height = positive_int(options.height, 3)
	local node_name = material_node(options, "landmark_node")
	local budget = placement_budget(options)
	while width * depth > budget do
		if width >= depth and width > 1 then
			width = width - 1
		elseif depth > 1 then
			depth = depth - 1
		else
			break
		end
	end
	for x = 0, width - 1 do
		for z = 0, depth - 1 do
			if not add_placement_if_room(placements,
					offset_pos(origin, x, 0, z), node_name, budget) then
				return placements
			end
		end
	end
	local center_x = math.floor(width / 2)
	local center_z = math.floor(depth / 2)
	for y = 1, height do
		if not add_placement_if_room(placements,
				offset_pos(origin, center_x, y, center_z), node_name, budget) then
			return placements
		end
	end
	return placements
end

local placement_builders = {
	lights = light_placements,
	marker = marker_placements,
	platform = platform_placements,
	path = path_placements,
	fire = fire_placements,
	wall = wall_placements,
	house = house_placements,
	cabin = cabin_placements,
	landmark = landmark_placements,
}

local function build_plan_data(options, require_task_id)
	assert(type(options) == "table", "Build task options must be a table")
	assert(type(options.kind) == "string" and placement_builders[options.kind],
		"Build task kind must be one of lights, marker, platform, path, fire, wall, house, cabin, or landmark")
	if require_task_id then
		assert(type(options.task_id) == "string" and options.task_id ~= "", "Build task id is required")
	end
	assert(type(options.agent_id) == "string" and options.agent_id ~= "", "Build agent id is required")
	assert(type(options.owner) == "string" and options.owner ~= "", "Build owner is required")
	local origin = copy_pos(options.origin)
	local placements = placement_builders[options.kind](origin, options)
	return origin, placements
end

function build_agent.configure(options)
	options = options or {}
	for _, field in ipairs({
		"light_node",
		"marker_node",
		"platform_node",
		"path_node",
		"fire_node",
		"wall_node",
		"house_node",
		"cabin_node",
		"landmark_node",
	}) do
		if options[field] then
			assert(type(options[field]) == "string" and options[field] ~= "",
				"Build node names must be non-empty strings")
			settings[field] = options[field]
		end
	end
	if options.max_nodes_per_task then
		settings.max_nodes_per_task = positive_int(options.max_nodes_per_task, settings.max_nodes_per_task)
	end
	if options.sample_limit then
		settings.sample_limit = positive_int(options.sample_limit, settings.sample_limit)
	end
end

function build_agent.plan(options)
	local origin, placements = build_plan_data(options, false)
	local placement_count = #placements
	local max_node_writes = options.max_node_writes_per_step or placement_count
	return {
		ok = true,
		status = "success",
		operation = "build_agent.plan",
		agent_id = options.agent_id,
		task_id = options.task_id,
		changed = 0,
		examined = placement_count,
		skipped = 0,
		reason = "build_plan_created",
		message = "Build plan created without mutation.",
		plan = {
			kind = options.kind,
			origin = origin,
			material_node = placements[1] and placements[1].node_name or options.material_node,
			placement_count = placement_count,
			mutation_class = "build",
			rollback_policy = options.rollback_policy or "snapshot",
			required_capabilities = {
				"world.place",
			},
			max_node_writes_per_step = max_node_writes,
			will_mutate = false,
		},
		samples = placement_samples(placements, options.sample_limit or settings.sample_limit),
		metrics = {
			node_writes = 0,
			planned_node_writes = placement_count,
			sample_count = math.min(placement_count, options.sample_limit or settings.sample_limit),
		},
	}
end

function build_agent.define_task(options)
	local _origin, placements = build_plan_data(options, true)
	local placement_count = #placements
	local max_node_writes = options.max_node_writes_per_step or placement_count

	return {
		task_id = options.task_id,
		agent_id = options.agent_id,
		owner = options.owner,
		label = "build " .. options.kind,
		required_capabilities = {
			["world.place"] = true,
		},
		mutation_class = "build",
		metadata = {
			kind = options.kind,
			material_node = placements[1] and placements[1].node_name or options.material_node,
			placement_count = placement_count,
		},
		budget = {
			max_steps_per_step = 1,
			max_node_writes_per_step = max_node_writes,
		},
		steps = {
			function(ctx)
				return core.run_ai_world_mutation_with_rollback({
					record_id = options.rollback_record_id,
					policy = options.rollback_policy or "snapshot",
					world_id = options.world_id,
					task_id = ctx.task_id,
					agent_id = ctx.agent_id,
					owner_ref = ctx.owner,
					operation_label = options.operation_label or "build_agent.execute",
					mutation_class = "build",
					bounds = options.bounds,
					positions = placement_positions(placements),
					get_node = options.get_node,
					persist_record = options.persist_record or options.persist_rollback_record,
				}, function()
					return core.ai_world_ops.batch_place(placements, {
						agent_id = ctx.agent_id,
						owner = ctx.owner,
						task_id = ctx.task_id,
						get_node = options.get_node,
						set_node = options.set_node,
						max_changes = placement_count,
						sample_limit = options.sample_limit or settings.sample_limit,
					})
				end)
			end,
		},
	}
end
