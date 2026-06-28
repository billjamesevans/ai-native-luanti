local texture = "blank.png"

core.ai_agent_plugin.configure({
	light_node = "ai_runtime_base:cobble",
	marker_node = "ai_runtime_base:cobble",
	repair_nodes = {},
	max_lights = 8,
	max_entity_move_distance = 16,
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

core.register_alias("mapgen_stone", "ai_runtime_base:stone")
core.register_alias("mapgen_water_source", "air")
core.register_alias("mapgen_river_water_source", "air")
core.register_alias("mapgen_lava_source", "air")
core.register_alias("mapgen_dirt", "ai_runtime_base:dirt")
core.register_alias("mapgen_dirt_with_grass", "ai_runtime_base:dirt_with_grass")
core.register_alias("mapgen_sand", "ai_runtime_base:sand")
core.register_alias("mapgen_cobble", "ai_runtime_base:cobble")
