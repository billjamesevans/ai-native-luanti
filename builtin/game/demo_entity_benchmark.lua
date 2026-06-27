core.demo_entity_benchmark = {}

local benchmark = core.demo_entity_benchmark
local ENTITY_NAME = "ai_demo_benchmark:helper"
local FIXTURE_ID = "generic_demo_entity:benchmark:v1"
local DEFAULT_OWNER_REF = "owner:synthetic-operator"
local DEFAULT_ENTITY_COUNT = 4
local DEFAULT_MOVEMENT_STEPS = 5
local MAX_COMMAND_ENTITY_COUNT = 64
local MAX_COMMAND_MOVEMENT_STEPS = 200

if not core.registered_entities[ENTITY_NAME] then
	core.register_entity(":" .. ENTITY_NAME, {
		initial_properties = {
			hp_max = 1,
			physical = true,
			collide_with_objects = true,
			collisionbox = {-0.25, -0.25, -0.25, 0.25, 0.25, 0.25},
			selectionbox = {-0.25, -0.25, -0.25, 0.25, 0.25, 0.25},
			visual = "cube",
			visual_size = { x = 0.5, y = 0.5 },
			textures = { "", "", "", "", "", "" },
			is_visible = false,
			pointable = false,
			static_save = false,
		},

		owner_ref = DEFAULT_OWNER_REF,
		step_count = 0,

		on_activate = function(self, staticdata)
			if staticdata and staticdata ~= "" then
				self.owner_ref = staticdata
			end
		end,

		on_step = function(self)
			self.step_count = (self.step_count or 0) + 1
		end,

		get_staticdata = function(self)
			return self.owner_ref or DEFAULT_OWNER_REF
		end,
	})
end

local function copy_pos(pos)
	return {
		x = pos.x,
		y = pos.y,
		z = pos.z,
	}
end

local function positive_int(value, fallback, field)
	value = value or fallback
	assert(type(value) == "number" and value >= 1,
		(field or "value") .. " must be a positive number")
	return math.floor(value)
end

local function elapsed_us(started_at)
	if not core.get_us_time then
		return 0
	end
	return math.max(0, core.get_us_time() - started_at)
end

local function now_us()
	return core.get_us_time and core.get_us_time() or 0
end

local function fixture_provenance()
	return {
		source_category = "code-only",
		assets_included = false,
		media_review_required = false,
		license = "project-code",
		review_status = "no-media-required",
	}
end

local function fixture_mutation()
	return {
		node_mutation_enabled = false,
		node_writes_allowed = 0,
	}
end

function benchmark.get_fixture()
	return {
		schema_version = 1,
		fixture_id = FIXTURE_ID,
		entity_name = ENTITY_NAME,
		provenance = fixture_provenance(),
		mutation = fixture_mutation(),
		scenarios = {
			"entity_count_small",
			"movement_patrol",
			"collision_wall_contact",
			"cleanup_despawn",
		},
	}
end

local function make_entity(index, owner_ref, scenario_id)
	local x = index - 1
	local velocity_x = 1
	if scenario_id == "collision_wall_contact" then
		x = 2
	end
	return {
		entity_id = ENTITY_NAME .. ":" .. index,
		owner_ref = owner_ref,
		pos = { x = x, y = 0, z = 0 },
		start_pos = { x = x, y = 0, z = 0 },
		velocity = { x = velocity_x, y = 0, z = 0 },
	}
end

local function spawn_entities(count, owner_ref, scenario_id)
	local entities = {}
	for index = 1, count do
		entities[index] = make_entity(index, owner_ref, scenario_id)
	end
	core.set_ai_runtime_entity_count(ENTITY_NAME, #entities)
	return entities
end

local function cleanup_entities(entities)
	local cleaned_up = #entities
	for index = #entities, 1, -1 do
		entities[index] = nil
	end
	core.set_ai_runtime_entity_count(ENTITY_NAME, 0)
	return cleaned_up
end

local function step_impact(step_times_us)
	local total = 0
	local sorted = {}
	for index, value in ipairs(step_times_us) do
		total = total + value
		sorted[index] = value
	end
	table.sort(sorted)
	local count = math.max(1, #sorted)
	local p95_index = math.max(1, math.ceil(count * 0.95))
	local avg_ms = (total / count) / 1000
	local p95_ms = (sorted[p95_index] or 0) / 1000
	local max_ms = (sorted[#sorted] or 0) / 1000
	return avg_ms, p95_ms, max_ms
end

local function movement_for_scenario(scenario_id)
	if scenario_id == "entity_count_small" or scenario_id == "cleanup_despawn" then
		return "idle"
	end
	if scenario_id == "collision_wall_contact" then
		return "wall_contact"
	end
	return "patrol"
end

local function simulate_steps(entities, scenario_id, movement_steps)
	local step_times = {}
	local distance_moved = 0
	local collision_checks = 0
	local collision_events = 0
	local movement_mode = movement_for_scenario(scenario_id)

	for step = 1, movement_steps do
		local started_at = now_us()
		for _, entity in ipairs(entities) do
			if movement_mode == "patrol" or movement_mode == "wall_contact" then
				local next_x = entity.pos.x + entity.velocity.x
				if movement_mode == "wall_contact" then
					collision_checks = collision_checks + 1
					if next_x > 2 or next_x < 0 then
						collision_events = collision_events + 1
						entity.velocity.x = -entity.velocity.x
						next_x = entity.pos.x + entity.velocity.x
					end
				end
				distance_moved = distance_moved + math.abs(next_x - entity.pos.x)
				entity.pos.x = next_x
			end
		end
		step_times[#step_times + 1] = elapsed_us(started_at)
	end

	return {
		distance_moved = distance_moved,
		collision_checks = collision_checks,
		collision_events = collision_events,
		step_times = step_times,
	}
end

local scenario_defaults = {
	entity_count_small = {
		entity_count = DEFAULT_ENTITY_COUNT,
		movement_steps = 1,
	},
	movement_patrol = {
		entity_count = DEFAULT_ENTITY_COUNT,
		movement_steps = DEFAULT_MOVEMENT_STEPS,
	},
	collision_wall_contact = {
		entity_count = 2,
		movement_steps = DEFAULT_MOVEMENT_STEPS,
	},
	cleanup_despawn = {
		entity_count = DEFAULT_ENTITY_COUNT,
		movement_steps = 1,
	},
}

function benchmark.run_scenario(scenario_id, options)
	options = options or {}
	local defaults = scenario_defaults[scenario_id]
	assert(defaults ~= nil, "Unknown demo entity benchmark scenario")
	local owner_ref = options.owner_ref or DEFAULT_OWNER_REF
	local entity_count = positive_int(options.entity_count or defaults.entity_count,
		defaults.entity_count, "entity_count")
	local movement_steps = positive_int(options.movement_steps or defaults.movement_steps,
		defaults.movement_steps, "movement_steps")
	if scenario_id == "collision_wall_contact" then
		entity_count = math.max(2, entity_count)
	end

	local entities = spawn_entities(entity_count, owner_ref, scenario_id)
	local simulation = simulate_steps(entities, scenario_id, movement_steps)
	local cleaned_up = cleanup_entities(entities)
	local avg_step_ms, p95_step_ms, max_lag_ms = step_impact(simulation.step_times)

	return {
		ok = true,
		status = "success",
		operation = "demo_entity_benchmark.run_scenario",
		scenario_id = scenario_id,
		fixture_id = FIXTURE_ID,
		entity_name = ENTITY_NAME,
		owner_ref = owner_ref,
		changed = 0,
		examined = entity_count * movement_steps,
		skipped = 0,
		metrics = {
			entity_count = entity_count,
			spawned = entity_count,
			active_peak = entity_count,
			movement_steps = movement_steps,
			distance_moved = simulation.distance_moved,
			collision_checks = simulation.collision_checks,
			collision_events = simulation.collision_events,
			cleaned_up = cleaned_up,
			remaining_entities = 0,
			avg_step_ms = avg_step_ms,
			p95_step_ms = p95_step_ms,
			max_lag_ms = max_lag_ms,
			node_writes = 0,
			warnings = {},
			errors = {},
		},
	}
end

function benchmark.run_suite(options)
	options = options or {}
	local fixture = benchmark.get_fixture()
	local scenarios = {}
	for _, scenario_id in ipairs(fixture.scenarios) do
		scenarios[#scenarios + 1] = benchmark.run_scenario(scenario_id, options)
	end
	return {
		ok = true,
		status = "success",
		operation = "demo_entity_benchmark.run_suite",
		schema_version = fixture.schema_version,
		fixture_id = fixture.fixture_id,
		entity_name = fixture.entity_name,
		provenance = fixture.provenance,
		mutation = fixture.mutation,
		scenarios = scenarios,
	}
end

local function runtime_counters()
	local metrics = core.get_ai_runtime_metrics()
	return {
		active_tasks = metrics.active_tasks or 0,
		queue_length = metrics.queue_length or 0,
		audit_records = metrics.audit_records or 0,
		task_steps_run = metrics.task_steps_run or 0,
		entities_by_type = table.copy(metrics.entities_by_type or {}),
	}
end

local function normalize_hardware_class(value)
	value = value or "local-mac"
	assert(value == "local-mac" or value == "low-power-server",
		"hardware_class must be local-mac or low-power-server")
	return value
end

function benchmark.run_report(options)
	options = options or {}
	local report = benchmark.run_suite(options)
	report.generated_at = core.get_us_time and tostring(core.get_us_time()) or "0"
	report.luanti_commit = options.luanti_commit or "unknown"
	report.hardware_class = normalize_hardware_class(options.hardware_class)
	report.run_context = {
		mode = "measured",
		requires_private_world = false,
		requires_private_assets = false,
		requires_live_pi = false,
	}
	report.runtime_counters = runtime_counters()
	return report
end

local function is_array(value)
	local count = 0
	for key in pairs(value) do
		if type(key) ~= "number" or key < 1 or key % 1 ~= 0 then
			return false
		end
		count = math.max(count, key)
	end
	for index = 1, count do
		if value[index] == nil then
			return false
		end
	end
	return true, count
end

local function json_escape(value)
	value = value:gsub("\\", "\\\\")
	value = value:gsub("\"", "\\\"")
	value = value:gsub("\n", "\\n")
	value = value:gsub("\r", "\\r")
	value = value:gsub("\t", "\\t")
	return value
end

local encode_json

local function encode_json_object(value)
	local keys = {}
	for key in pairs(value) do
		keys[#keys + 1] = tostring(key)
	end
	table.sort(keys)
	local parts = {}
	for _, key in ipairs(keys) do
		parts[#parts + 1] = "\"" .. json_escape(key) .. "\":" .. encode_json(value[key])
	end
	return "{" .. table.concat(parts, ",") .. "}"
end

local function encode_json_array(value, count)
	local parts = {}
	for index = 1, count do
		parts[index] = encode_json(value[index])
	end
	return "[" .. table.concat(parts, ",") .. "]"
end

encode_json = function(value)
	local value_type = type(value)
	if value_type == "string" then
		return "\"" .. json_escape(value) .. "\""
	elseif value_type == "number" then
		return tostring(value)
	elseif value_type == "boolean" then
		return value and "true" or "false"
	elseif value_type == "nil" then
		return "null"
	elseif value_type == "table" then
		local array, count = is_array(value)
		if array then
			return encode_json_array(value, count)
		end
		return encode_json_object(value)
	end
	error("Cannot JSON encode value of type " .. value_type)
end

function benchmark.encode_report(report)
	return encode_json(report)
end

local function parse_positive_command_int(value, field, default, maximum)
	if value == nil then
		return default
	end
	local number = tonumber(value)
	if not number or number < 1 then
		return nil, field .. " must be a positive integer"
	end
	number = math.floor(number)
	if number > maximum then
		return nil, field .. " exceeds maximum " .. maximum
	end
	return number
end

local function parse_command_options(param)
	local raw = {}
	for token in string.gmatch(param or "", "%S+") do
		local key, value = token:match("^([^=]+)=(.+)$")
		if not key then
			return nil, "Use key=value parameters."
		end
		raw[key] = value
	end

	local entity_count, count_error = parse_positive_command_int(raw.count,
		"count", DEFAULT_ENTITY_COUNT, MAX_COMMAND_ENTITY_COUNT)
	if not entity_count then
		return nil, count_error
	end
	local movement_steps, steps_error = parse_positive_command_int(raw.steps,
		"steps", DEFAULT_MOVEMENT_STEPS, MAX_COMMAND_MOVEMENT_STEPS)
	if not movement_steps then
		return nil, steps_error
	end

	local hardware_class = raw.hardware or raw.hardware_class or "local-mac"
	if hardware_class ~= "local-mac" and hardware_class ~= "low-power-server" then
		return nil, "hardware must be local-mac or low-power-server"
	end

	return {
		entity_count = entity_count,
		movement_steps = movement_steps,
		luanti_commit = raw.commit or raw.luanti_commit or "unknown",
		hardware_class = hardware_class,
		owner_ref = raw.owner_ref or DEFAULT_OWNER_REF,
	}
end

core.register_chatcommand("ai_demo_entity_benchmark", {
	params = "[count=N] [steps=N] [commit=LABEL] [hardware=local-mac|low-power-server]",
	description = "Run the AI demo entity benchmark and return a JSON report.",
	privs = { server = true },
	func = function(_, param)
		local options, err = parse_command_options(param)
		if not options then
			return false, err
		end
		local report = benchmark.run_report(options)
		return true, benchmark.encode_report(report)
	end,
})
