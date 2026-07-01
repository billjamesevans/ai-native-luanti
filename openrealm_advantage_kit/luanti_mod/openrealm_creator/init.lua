local S = minetest.get_translator and minetest.get_translator("openrealm_creator") or function(s) return s end

local pending_by_player = {}
local rollback_by_player = {}
local audit_log = {}

local function now()
	return os.date("!%Y-%m-%dT%H:%M:%SZ")
end

local function hash_text(text)
	local h = 2166136261
	for i = 1, #text do
		h = bit32.bxor(h, string.byte(text, i))
		h = (h * 16777619) % 4294967296
	end
	return h
end

local function make_rng(seed)
	local state = seed % 2147483647
	if state <= 0 then state = state + 2147483646 end
	return function(min, max)
		state = (state * 16807) % 2147483647
		local value = (state - 1) / 2147483646
		return math.floor(min + value * (max - min + 1))
	end
end

local function node_exists(name)
	return minetest.registered_nodes[name] ~= nil
end

local function node_or(name, fallback)
	if node_exists(name) then return name end
	if node_exists(fallback) then return fallback end
	return "air"
end

local nodes = {
	stone = node_or("default:stone", "mapgen_stone"),
	wood = node_or("default:wood", "mapgen_tree"),
	glass = node_or("default:glass", "air"),
	light = node_or("default:torch", "air"),
	water = node_or("default:water_source", "mapgen_water_source"),
	leaves = node_or("default:leaves", "mapgen_leaves"),
	tree = node_or("default:tree", "mapgen_tree"),
	path = node_or("default:cobble", "mapgen_stone"),
	portal = node_or("default:mese", "default:stone"),
	flower = node_or("flowers:dandelion_yellow", "default:leaves"),
}

local function pkey(pos)
	return pos.x .. "," .. pos.y .. "," .. pos.z
end

local function add(actions, pos, node_name, reason)
	actions[#actions + 1] = {
		action = "place_node",
		pos = vector.round(pos),
		node = node_name,
		reason = reason,
	}
end

local function dedupe(actions)
	local map = {}
	for _, action in ipairs(actions) do
		map[pkey(action.pos)] = action
	end
	local keys = {}
	for key in pairs(map) do keys[#keys + 1] = key end
	table.sort(keys)
	local result = {}
	for _, key in ipairs(keys) do result[#result + 1] = map[key] end
	return result
end

local function cabin(actions, origin, w, d)
	for x = 0, w - 1 do
		for z = 0, d - 1 do
			add(actions, vector.add(origin, {x=x, y=0, z=z}), nodes.stone, "cabin foundation")
		end
	end
	for y = 1, 3 do
		for x = 0, w - 1 do
			for z = 0, d - 1 do
				local wall = x == 0 or x == w - 1 or z == 0 or z == d - 1
				if wall then
					local node = nodes.wood
					if y == 2 and (x == math.floor(w / 2) or z == math.floor(d / 2)) then
						node = nodes.glass
					end
					add(actions, vector.add(origin, {x=x, y=y, z=z}), node, "cabin wall")
				end
			end
		end
	end
	for x = -1, w do
		for z = -1, d do
			if x == -1 or x == w or z == -1 or z == d or ((x + z) % 2 == 0) then
				add(actions, vector.add(origin, {x=x, y=4, z=z}), nodes.wood, "cabin roof")
			end
		end
	end
	add(actions, vector.add(origin, {x=math.floor(w / 2), y=1, z=0}), "air", "cabin doorway")
	add(actions, vector.add(origin, {x=math.floor(w / 2), y=2, z=0}), "air", "cabin doorway")
end

local function trail(actions, origin, length, axis)
	for i = 0, length - 1 do
		add(actions, vector.add(origin, {x=axis == "x" and i or 0, y=0, z=axis == "z" and i or 0}), nodes.path, "trail path")
	end
end

local function bridge(actions, origin, length, axis)
	for i = 0, length - 1 do
		local pos = vector.add(origin, {x=axis == "x" and i or 0, y=0, z=axis == "z" and i or 0})
		add(actions, pos, nodes.path, "bridge deck")
		if i % 3 == 0 then
			add(actions, vector.add(pos, {x=0, y=1, z=1}), nodes.light, "bridge lantern")
			add(actions, vector.add(pos, {x=0, y=1, z=-1}), nodes.light, "bridge lantern")
		end
	end
end

local function lanterns(actions, origin, count, axis)
	for i = 0, count - 1 do
		add(actions, vector.add(origin, {x=axis == "x" and i * 3 or 0, y=2, z=axis == "z" and i * 3 or 0}), nodes.light, "floating lantern")
	end
end

local function lake(actions, origin, w, d)
	local cx = w / 2
	local cz = d / 2
	for x = 0, w - 1 do
		for z = 0, d - 1 do
			if ((x - cx) ^ 2) / (cx ^ 2) + ((z - cz) ^ 2) / (cz ^ 2) <= 1 then
				add(actions, vector.add(origin, {x=x, y=-1, z=z}), nodes.water, "alpine water")
			end
		end
	end
end

local function pine(actions, origin)
	for y = 0, 3 do
		add(actions, vector.add(origin, {x=0, y=y, z=0}), nodes.tree, "pine trunk")
	end
	for _, layer in ipairs({{3, 2}, {4, 1}, {5, 1}}) do
		local y = layer[1]
		local r = layer[2]
		for x = -r, r do
			for z = -r, r do
				if math.abs(x) + math.abs(z) <= r + 1 then
					add(actions, vector.add(origin, {x=x, y=y, z=z}), nodes.leaves, "pine canopy")
				end
			end
		end
	end
end

local function portal(actions, origin)
	for y = 0, 4 do
		add(actions, vector.add(origin, {x=0, y=y, z=0}), nodes.portal, "portal arch")
		add(actions, vector.add(origin, {x=4, y=y, z=0}), nodes.portal, "portal arch")
	end
	for x = 0, 4 do
		add(actions, vector.add(origin, {x=x, y=5, z=0}), nodes.portal, "portal arch")
	end
	for x = 1, 3 do
		for y = 1, 4 do
			if (x + y) % 2 == 0 then
				add(actions, vector.add(origin, {x=x, y=y, z=0}), nodes.light, "portal shimmer")
			end
		end
	end
end

local function garden(actions, origin, w, d)
	for x = 0, w - 1 do
		for z = 0, d - 1 do
			local edge = x == 0 or x == w - 1 or z == 0 or z == d - 1
			add(actions, vector.add(origin, {x=x, y=0, z=z}), edge and nodes.path or nodes.flower, "garden layout")
		end
	end
end

local function tower(actions, origin, height)
	for y = 0, height - 1 do
		for _, p in ipairs({{0,0},{2,0},{0,2},{2,2}}) do
			add(actions, vector.add(origin, {x=p[1], y=y, z=p[2]}), nodes.stone, "tower support")
		end
	end
	for x = -1, 3 do
		for z = -1, 3 do
			add(actions, vector.add(origin, {x=x, y=height, z=z}), nodes.stone, "lookout deck")
		end
	end
	add(actions, vector.add(origin, {x=1, y=height + 1, z=1}), nodes.light, "lookout beacon")
end

local function plan_from_prompt(name, prompt)
	local player = minetest.get_player_by_name(name)
	if not player then return nil, "Player not found." end
	local text = string.lower(prompt or "")
	local seed = hash_text(prompt)
	local rand = make_rng(seed)
	local origin = vector.round(vector.add(player:get_pos(), {x=2, y=0, z=2}))
	local actions = {}
	add(actions, origin, nodes.path, "realm anchor")

	if text:find("glacier") or text:find("mountain") or text:find("alpine") then
		lake(actions, vector.add(origin, {x=-8, y=0, z=-8}), 9, 5)
		trail(actions, vector.add(origin, {x=-10, y=0, z=0}), 20, "x")
		for _ = 1, 10 do pine(actions, vector.add(origin, {x=rand(-12, 12), y=0, z=rand(-12, 12)})) end
		cabin(actions, vector.add(origin, {x=5, y=0, z=5}), 5, 4)
		tower(actions, vector.add(origin, {x=-8, y=0, z=7}), 5)
	end
	if text:find("village") then
		for _, p in ipairs({{-8,-4}, {2,5}, {9,-3}}) do cabin(actions, vector.add(origin, {x=p[1], y=0, z=p[2]}), 5, 4) end
		trail(actions, vector.add(origin, {x=-10, y=0, z=0}), 22, "x")
		trail(actions, vector.add(origin, {x=0, y=0, z=-8}), 18, "z")
		lanterns(actions, vector.add(origin, {x=-8, y=0, z=0}), 6, "x")
	end
	if text:find("cabin") or text:find("house") or text:find("shelter") then cabin(actions, vector.add(origin, {x=2, y=0, z=2}), 6, 5) end
	if text:find("bridge") then bridge(actions, vector.add(origin, {x=-8, y=0, z=0}), 17, "x") end
	if text:find("portal") then portal(actions, vector.add(origin, {x=0, y=0, z=-7})) end
	if text:find("garden") then garden(actions, vector.add(origin, {x=-5, y=0, z=5}), 8, 6) end
	if text:find("lake") or text:find("river") or text:find("water") then lake(actions, vector.add(origin, {x=-6, y=0, z=-6}), 8, 5) end
	if text:find("tower") or text:find("lookout") then tower(actions, vector.add(origin, {x=6, y=0, z=-6}), 8) end
	if text:find("lantern") or text:find("light") then lanterns(actions, vector.add(origin, {x=-5, y=0, z=-4}), 8, "x") end
	if #actions == 1 then cabin(actions, vector.add(origin, {x=1, y=0, z=1}), 4, 4) end

	actions = dedupe(actions)
	if #actions > 512 then
		return nil, "Plan blocked: too many node writes (" .. #actions .. ")."
	end
	return {
		plan_id = "plan:" .. seed,
		prompt = prompt,
		origin = origin,
		actions = actions,
		created_at = now(),
	}, nil
end

local function summarize_plan(plan)
	local reasons = {}
	for _, action in ipairs(plan.actions) do
		reasons[action.reason] = (reasons[action.reason] or 0) + 1
	end
	local parts = {}
	for reason, count in pairs(reasons) do
		parts[#parts + 1] = reason .. "=" .. count
	end
	table.sort(parts)
	return "OpenRealm plan " .. plan.plan_id .. ": " .. #plan.actions .. " writes. " .. table.concat(parts, "; ")
end

local function audit(event_type, actor, plan_id, message)
	audit_log[#audit_log + 1] = {
		at = now(),
		event_type = event_type,
		actor = actor,
		plan_id = plan_id,
		message = message,
	}
	while #audit_log > 50 do table.remove(audit_log, 1) end
	minetest.log("action", "[openrealm_creator] " .. event_type .. " actor=" .. actor .. " plan=" .. tostring(plan_id) .. " " .. message)
end

minetest.register_chatcommand("realm_plan", {
	params = "<prompt>",
	description = "Create a safe previewable OpenRealm build plan.",
	privs = {interact = true},
	func = function(name, param)
		if not param or param == "" then return false, "Usage: /realm_plan <prompt>" end
		local plan, err = plan_from_prompt(name, param)
		if not plan then return false, err end
		pending_by_player[name] = plan
		audit("plan.created", name, plan.plan_id, #plan.actions .. " planned writes")
		return true, summarize_plan(plan) .. " Use /realm_approve to apply or /realm_status to inspect."
	end,
})

minetest.register_chatcommand("realm_approve", {
	description = "Approve and apply your pending OpenRealm plan.",
	privs = {interact = true},
	func = function(name)
		local plan = pending_by_player[name]
		if not plan then return false, "No pending OpenRealm plan. Use /realm_plan first." end
		local before = {}
		for _, action in ipairs(plan.actions) do
			before[pkey(action.pos)] = minetest.get_node(action.pos).name
		end
		for _, action in ipairs(plan.actions) do
			minetest.set_node(action.pos, {name = action.node})
		end
		local rollback_id = "rollback:" .. plan.plan_id .. ":" .. os.time()
		rollback_by_player[name] = {rollback_id = rollback_id, before = before}
		pending_by_player[name] = nil
		audit("plan.applied", name, plan.plan_id, #plan.actions .. " applied writes; rollback=" .. rollback_id)
		return true, "Applied " .. #plan.actions .. " changes. Undo with /realm_undo."
	end,
})

minetest.register_chatcommand("realm_undo", {
	description = "Undo your last OpenRealm approved build.",
	privs = {interact = true},
	func = function(name)
		local record = rollback_by_player[name]
		if not record then return false, "No rollback record for this player." end
		local changed = 0
		for key, node_name in pairs(record.before) do
			local x, y, z = key:match("([^,]+),([^,]+),([^,]+)")
			minetest.set_node({x=tonumber(x), y=tonumber(y), z=tonumber(z)}, {name=node_name})
			changed = changed + 1
		end
		rollback_by_player[name] = nil
		audit("rollback.applied", name, record.rollback_id, changed .. " positions restored")
		return true, "Rollback applied. Restored " .. changed .. " node positions."
	end,
})

minetest.register_chatcommand("realm_status", {
	description = "Show OpenRealm pending plan and audit status.",
	privs = {interact = true},
	func = function(name)
		local plan = pending_by_player[name]
		local pending = plan and summarize_plan(plan) or "No pending plan."
		local rollback = rollback_by_player[name] and rollback_by_player[name].rollback_id or "No rollback record."
		return true, pending .. "\n" .. rollback .. "\nAudit events retained: " .. #audit_log
	end,
})
