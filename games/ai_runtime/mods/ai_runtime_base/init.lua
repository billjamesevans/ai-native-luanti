local helper_entity_name = "ai_runtime_base:helper"
local player_huds = {}
local guide_shown = {}

local textures = {
	stone = "ai_runtime_base_stone.png",
	dirt = "ai_runtime_base_dirt.png",
	grass_top = "ai_runtime_base_grass_top.png",
	grass_side = "ai_runtime_base_grass_side.png",
	leaves = "ai_runtime_base_leaves.png",
	sand = "ai_runtime_base_sand.png",
	cobble = "ai_runtime_base_cobble.png",
	fire = "ai_runtime_base_fire.png",
	tnt = "ai_runtime_base_tnt.png",
	wood_side = "ai_runtime_base_wood_side.png",
	wood_top = "ai_runtime_base_wood_top.png",
	gold = "ai_runtime_base_gold.png",
	quartz = "ai_runtime_base_quartz.png",
	glass = "ai_runtime_base_glass.png",
	diamond = "ai_runtime_base_diamond.png",
	glow = "ai_runtime_base_glow.png",
}

local formspec_theme = table.concat({
	"style_type[label;textcolor=#EAF2FF;font_size=*1.05]",
	"style_type[textarea,field;textcolor=#EAF2FF;border=false;font=normal]",
	"style_type[button,button_exit;border=false;bgcolor=#1C3E6E;bgcolor_hovered=#2E6BE6;bgcolor_pressed=#15345F;textcolor=#F7FBFF;font=bold]",
}, "")

local function show_guide(player)
	local name = player:get_player_name()
	local fs = table.concat({
		"formspec_version[6]",
		"size[9.2,6.4]",
		"real_coordinates[true]",
		"bgcolor[#07101E;true]",
		"container[0.45,0.45]",
		"style[title;textcolor=#F7FBFF;font=bold;font_size=*1.35]",
		"label[0,0;OpenRealm Alpha]",
		"style[sub;textcolor=#9FE8D1;font_size=*1.02]",
		"label[0,0.48;Nova builds through preview, approval, audit, and rollback.]",
		"style[body;textcolor=#C8D4EA]",
		"textarea[0,1.1;8.3,1.4;body;;Try /nova build only a fire\\nThen approve, inspect the result, and use rollback when needed.]",
		"style[cmd;textcolor=#FFD166;font=mono,bold;border=false]",
		"textarea[0,2.7;8.3,1.0;cmd;;/nova build only a fire\\n/nova options\\n/nova undo]",
		"button_exit[0,4.55;2.35,0.55;start;Start playing]",
		"button[2.55,4.55;2.35,0.55;hint;Send starter prompt]",
		"button_exit[5.1,4.55;2.35,0.55;close;Close]",
		"container_end[]",
	})
	core.show_formspec(name, "ai_runtime_base:guide", fs)
end

local function add_player_ui(player)
	player:set_formspec_prepend(formspec_theme)

	local name = player:get_player_name()
	if player_huds[name] then
		player:hud_remove(player_huds[name])
	end

	player_huds[name] = player:hud_add({
		type = "text",
		position = {x = 0.02, y = 0.08},
		offset = {x = 0, y = 0},
		alignment = {x = 1, y = 1},
		scale = {x = 100, y = 16},
		text = "OpenRealm Alpha  |  /nova build only a fire  |  /openrealm",
		number = 0xEAF2FF,
	})
end

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
	tiles = {textures.stone},
	groups = {cracky = 3},
})

core.register_node("ai_runtime_base:dirt", {
	description = "AI Runtime Dirt",
	tiles = {textures.dirt},
	groups = {crumbly = 3, soil = 1},
})

core.register_node("ai_runtime_base:dirt_with_grass", {
	description = "AI Runtime Grass Surface",
	tiles = {textures.grass_top, textures.dirt, textures.grass_side},
	groups = {crumbly = 3, soil = 1},
})

core.register_node("ai_runtime_base:leaves", {
	description = "AI Runtime Leaves",
	tiles = {textures.leaves},
	groups = {snappy = 3, leaves = 1},
})

core.register_node("ai_runtime_base:sand", {
	description = "AI Runtime Sand",
	tiles = {textures.sand},
	groups = {crumbly = 3},
})

core.register_node("ai_runtime_base:cobble", {
	description = "AI Runtime Cobble",
	tiles = {textures.cobble},
	groups = {cracky = 3},
})

core.register_node("ai_runtime_base:fire", {
	description = "AI Runtime Fire",
	tiles = {textures.fire},
	drawtype = "plantlike",
	use_texture_alpha = "clip",
	walkable = false,
	buildable_to = true,
	groups = {fire = 1},
})

core.register_node("ai_runtime_base:tnt", {
	description = "AI Runtime TNT",
	tiles = {textures.tnt},
	groups = {cracky = 3, tnt = 1},
})

core.register_node("ai_runtime_base:wood", {
	description = "AI Runtime Wood",
	tiles = {textures.wood_top, textures.wood_top, textures.wood_side},
	groups = {choppy = 3},
})

core.register_node("ai_runtime_base:gold", {
	description = "AI Runtime Gold",
	tiles = {textures.gold},
	groups = {cracky = 2},
})

core.register_node("ai_runtime_base:quartz", {
	description = "AI Runtime Quartz",
	tiles = {textures.quartz},
	groups = {cracky = 2},
})

core.register_node("ai_runtime_base:glass", {
	description = "AI Runtime Glass",
	tiles = {textures.glass},
	drawtype = "glasslike",
	use_texture_alpha = "blend",
	groups = {cracky = 3},
})

core.register_node("ai_runtime_base:diamond", {
	description = "AI Runtime Diamond",
	tiles = {textures.diamond},
	groups = {cracky = 1},
})

core.register_node("ai_runtime_base:glow", {
	description = "AI Runtime Glow",
	tiles = {textures.glow},
	light_source = 12,
	groups = {cracky = 2},
})

core.register_tool("ai_runtime_base:builder_pick", {
	description = "OpenRealm Builder Pick",
	inventory_image = "ai_runtime_base_builder_pick.png",
	wield_image = "ai_runtime_base_builder_pick.png",
	tool_capabilities = {
		full_punch_interval = 1.0,
		max_drop_level = 0,
		groupcaps = {
			cracky = {times = {[1] = 1.6, [2] = 1.0, [3] = 0.55}, uses = 0, maxlevel = 3},
			crumbly = {times = {[1] = 1.2, [2] = 0.8, [3] = 0.45}, uses = 0, maxlevel = 3},
			choppy = {times = {[1] = 1.5, [2] = 0.95, [3] = 0.55}, uses = 0, maxlevel = 3},
		},
	},
})

local legacy_node_aliases = {
	["basenodes:stone"] = "ai_runtime_base:stone",
	["basenodes:desert_stone"] = "ai_runtime_base:stone",
	["basenodes:dirt_with_grass"] = "ai_runtime_base:dirt_with_grass",
	["basenodes:dirt_with_snow"] = "ai_runtime_base:dirt_with_grass",
	["basenodes:dirt"] = "ai_runtime_base:dirt",
	["basenodes:sand"] = "ai_runtime_base:sand",
	["basenodes:desert_sand"] = "ai_runtime_base:sand",
	["basenodes:gravel"] = "ai_runtime_base:cobble",
	["basenodes:junglegrass"] = "ai_runtime_base:dirt_with_grass",
	["basenodes:tree"] = "ai_runtime_base:wood",
	["basenodes:jungletree"] = "ai_runtime_base:wood",
	["basenodes:pine_tree"] = "ai_runtime_base:wood",
	["basenodes:leaves"] = "ai_runtime_base:leaves",
	["basenodes:jungleleaves"] = "ai_runtime_base:leaves",
	["basenodes:pine_needles"] = "ai_runtime_base:leaves",
	["basenodes:water_source"] = "air",
	["basenodes:water_flowing"] = "air",
	["basenodes:river_water_source"] = "air",
	["basenodes:river_water_flowing"] = "air",
	["basenodes:lava_source"] = "air",
	["basenodes:lava_flowing"] = "air",
	["basenodes:cobble"] = "ai_runtime_base:cobble",
	["basenodes:mossycobble"] = "ai_runtime_base:cobble",
	["basenodes:apple"] = "ai_runtime_base:glow",
	["basenodes:ice"] = "ai_runtime_base:glass",
	["basenodes:snow"] = "ai_runtime_base:quartz",
	["basenodes:snowblock"] = "ai_runtime_base:quartz",
}

for old_name, new_name in pairs(legacy_node_aliases) do
	core.register_alias(old_name, new_name)
end

local legacy_tool_aliases = {
	"pick_mese",
	"pick_mese_no_delay",
	"pick_wood",
	"pick_stone",
	"pick_steel",
	"pick_steel_l1",
	"pick_steel_l2",
	"shovel_wood",
	"shovel_stone",
	"shovel_steel",
	"axe_wood",
	"axe_stone",
	"axe_steel",
	"shears_wood",
	"shears_stone",
	"shears_steel",
	"sword_wood",
	"sword_stone",
	"sword_steel",
	"sword_titanium",
	"sword_blood",
	"sword_mese",
	"sword_fire",
	"sword_ice",
	"sword_elemental",
	"dagger_heal",
	"sword_heal",
	"sword_heal_super",
	"dagger_wood",
	"dagger_steel",
	"random_wear_bar",
}

for _, old_tool in ipairs(legacy_tool_aliases) do
	core.register_alias("basetools:" .. old_tool, "ai_runtime_base:builder_pick")
end

core.register_chatcommand("openrealm", {
	description = "Open the OpenRealm alpha guide",
	func = function(name)
		local player = core.get_player_by_name(name)
		if player then
			show_guide(player)
		end
		return true
	end,
})

core.register_chatcommand("nova_ui", {
	description = "Open the OpenRealm alpha guide",
	func = function(name)
		local player = core.get_player_by_name(name)
		if player then
			show_guide(player)
		end
		return true
	end,
})

core.register_on_joinplayer(function(player)
	add_player_ui(player)

	local name = player:get_player_name()
	core.chat_send_player(name, core.colorize("#9FE8D1", "OpenRealm Alpha") ..
		" - use /nova to build, preview, approve, and rollback. Type /openrealm for the guide.")

	if not guide_shown[name] then
		guide_shown[name] = true
		core.after(0.8, function()
			local current_player = core.get_player_by_name(name)
			if current_player then
				show_guide(current_player)
			end
		end)
	end
end)

core.register_on_leaveplayer(function(player)
	local name = player:get_player_name()
	player_huds[name] = nil
	guide_shown[name] = nil
end)

core.register_on_player_receive_fields(function(player, formname, fields)
	if formname ~= "ai_runtime_base:guide" or not fields.hint then
		return false
	end

	core.chat_send_player(player:get_player_name(),
		core.colorize("#FFD166", "Try: ") .. "/nova build only a fire")
	return true
end)

core.register_alias("mapgen_stone", "ai_runtime_base:stone")
core.register_alias("mapgen_water_source", "air")
core.register_alias("mapgen_river_water_source", "air")
core.register_alias("mapgen_lava_source", "air")
core.register_alias("mapgen_dirt", "ai_runtime_base:dirt")
core.register_alias("mapgen_dirt_with_grass", "ai_runtime_base:dirt_with_grass")
core.register_alias("mapgen_sand", "ai_runtime_base:sand")
core.register_alias("mapgen_cobble", "ai_runtime_base:cobble")
