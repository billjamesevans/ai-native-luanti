local texture = "blank.png"
local helper_entity_name = "ai_runtime_base:helper"

if not core.registered_entities[helper_entity_name] then
	core.register_entity(":" .. helper_entity_name, {
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

		owner_ref = "owner:ai-runtime",

		on_activate = function(self, staticdata)
			if staticdata and staticdata ~= "" then
				self.owner_ref = staticdata
			end
		end,

		get_staticdata = function(self)
			return self.owner_ref or "owner:ai-runtime"
		end,
	})
end

core.ai_agent_plugin.configure({
	capability_profile = "clean",
	light_node = "ai_runtime_base:cobble",
	marker_node = "ai_runtime_base:cobble",
	platform_node = "ai_runtime_base:stone",
	path_node = "ai_runtime_base:cobble",
	fire_node = "ai_runtime_base:fire",
	wall_node = "ai_runtime_base:stone",
	house_node = "ai_runtime_base:wood",
	cabin_node = "ai_runtime_base:wood",
	landmark_node = "ai_runtime_base:quartz",
	tnt_node = "ai_runtime_base:tnt",
	build_material_nodes = {
		fire = "ai_runtime_base:fire",
		tnt = "ai_runtime_base:tnt",
		wood = "ai_runtime_base:wood",
		gold = "ai_runtime_base:gold",
		quartz = "ai_runtime_base:quartz",
		glass = "ai_runtime_base:glass",
		diamond = "ai_runtime_base:diamond",
		glow = "ai_runtime_base:glow",
	},
	agent_entity_name = helper_entity_name,
	repair_nodes = {},
	max_lights = 16,
	max_entity_move_distance = 16,
	max_follow_steps = 6,
	max_follow_step_distance = 4,
	max_follow_total_distance = 24,
	max_follow_stop_distance = 1,
	max_follow_wall_time_ms = 250,
	agentic_build_planner_first = true,
	auto_apply_build_approvals =
		core.settings:get_bool("ai_runtime.auto_apply_build_approvals", false),
	capabilities = {
		["world.read"] = true,
		["world.place"] = true,
		["world.remove"] = true,
		["entity.spawn"] = true,
		["entity.control"] = true,
		["task.cancel"] = true,
		["http.llm"] = true,
	},
})

core.ai_rollback_storage.configure({
	enabled = true,
})

core.register_node("ai_runtime_base:stone", {
	description = "AI Runtime Stone",
	tiles = {texture},
	groups = {cracky = 3},
})

core.register_node("ai_runtime_base:dirt", {
	description = "AI Runtime Dirt",
	tiles = {texture},
	groups = {crumbly = 3, soil = 1},
})

core.register_node("ai_runtime_base:dirt_with_grass", {
	description = "AI Runtime Grass Surface",
	tiles = {texture},
	groups = {crumbly = 3, soil = 1},
})

core.register_node("ai_runtime_base:sand", {
	description = "AI Runtime Sand",
	tiles = {texture},
	groups = {crumbly = 3},
})

core.register_node("ai_runtime_base:cobble", {
	description = "AI Runtime Cobble",
	tiles = {texture},
	groups = {cracky = 3},
})

core.register_node("ai_runtime_base:fire", {
	description = "AI Runtime Fire",
	tiles = {texture},
	drawtype = "plantlike",
	walkable = false,
	buildable_to = true,
	groups = {fire = 1},
})

core.register_node("ai_runtime_base:tnt", {
	description = "AI Runtime TNT",
	tiles = {texture},
	groups = {cracky = 3, tnt = 1},
})

core.register_node("ai_runtime_base:wood", {
	description = "AI Runtime Wood",
	tiles = {texture},
	groups = {choppy = 3},
})

core.register_node("ai_runtime_base:gold", {
	description = "AI Runtime Gold",
	tiles = {texture},
	groups = {cracky = 2},
})

core.register_node("ai_runtime_base:quartz", {
	description = "AI Runtime Quartz",
	tiles = {texture},
	groups = {cracky = 2},
})

core.register_node("ai_runtime_base:glass", {
	description = "AI Runtime Glass",
	tiles = {texture},
	drawtype = "glasslike",
	groups = {cracky = 3},
})

core.register_node("ai_runtime_base:diamond", {
	description = "AI Runtime Diamond",
	tiles = {texture},
	groups = {cracky = 1},
})

core.register_node("ai_runtime_base:glow", {
	description = "AI Runtime Glow",
	tiles = {texture},
	light_source = 12,
	groups = {cracky = 2},
})

core.register_alias("mapgen_stone", "ai_runtime_base:stone")
core.register_alias("mapgen_water_source", "air")
core.register_alias("mapgen_river_water_source", "air")
core.register_alias("mapgen_lava_source", "air")
core.register_alias("mapgen_dirt", "ai_runtime_base:dirt")
core.register_alias("mapgen_dirt_with_grass", "ai_runtime_base:dirt_with_grass")
core.register_alias("mapgen_sand", "ai_runtime_base:sand")
core.register_alias("mapgen_cobble", "ai_runtime_base:cobble")
