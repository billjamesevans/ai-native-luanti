core.registered_ai_agents = {}

local function check_string(value, field)
	assert(type(value) == "string" and value ~= "",
		"Field '" .. field .. "' must be a non-empty string")
end

local function normalize_bool_map(value, field)
	if value == nil then
		return {}
	end
	assert(type(value) == "table", "Field '" .. field .. "' must be a table")
	local result = {}
	for name, enabled in pairs(value) do
		check_string(name, field .. " key")
		if enabled then
			result[name] = true
		end
	end
	return result
end

local function normalize_limits(value)
	if value == nil then
		return {}
	end
	assert(type(value) == "table", "Field 'limits' must be a table")
	return table.copy(value)
end

local function normalize_agent(def)
	assert(type(def) == "table", "Agent definition must be a table")
	check_string(def.agent_id, "agent_id")
	check_string(def.display_name, "display_name")
	check_string(def.owner, "owner")
	check_string(def.plugin, "plugin")

	return {
		agent_id = def.agent_id,
		display_name = def.display_name,
		owner = def.owner,
		plugin = def.plugin,
		capabilities = normalize_bool_map(def.capabilities, "capabilities"),
		limits = normalize_limits(def.limits),
		state = def.state or "enabled",
	}
end

local function make_capability_result(agent_id, capability, ok, status, reason, message)
	return {
		ok = ok,
		status = status,
		operation = "capability.check",
		agent_id = agent_id,
		capability = capability,
		reason = reason,
		message = message,
		audit_required = ok and capability == "admin.override" or false,
	}
end

function core.register_ai_agent(def)
	local agent = normalize_agent(def)
	core.registered_ai_agents[agent.agent_id] = agent
	return table.copy(agent)
end

function core.get_ai_agent(agent_id)
	local agent = core.registered_ai_agents[agent_id]
	if not agent then
		return nil
	end
	return table.copy(agent)
end

function core.agent_has_capability(agent_id, capability)
	local agent = core.registered_ai_agents[agent_id]
	return agent ~= nil and agent.capabilities[capability] == true
end

function core.check_agent_capability(agent_id, capability)
	local agent = core.registered_ai_agents[agent_id]
	if not agent then
		return make_capability_result(agent_id, capability, false, "not_found",
			"unknown_agent", "Agent is not registered.")
	end
	if agent.state ~= "enabled" then
		return make_capability_result(agent_id, capability, false, "blocked",
			"agent_" .. agent.state, "Agent state is '" .. agent.state .. "'.")
	end
	if not agent.capabilities[capability] then
		return make_capability_result(agent_id, capability, false, "permission_denied",
			"missing_capability", "Agent does not have capability '" .. capability .. "'.")
	end
	if capability == "admin.override" then
		return make_capability_result(agent_id, capability, true, "success",
			"admin_override_granted", "Agent has admin override; audit is required.")
	end
	return make_capability_result(agent_id, capability, true, "success",
		"capability_granted", "Agent capability is granted.")
end
