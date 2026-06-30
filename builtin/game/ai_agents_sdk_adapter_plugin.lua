core.ai_agents_sdk_adapter_plugin = {}

local plugin = core.ai_agents_sdk_adapter_plugin
local adapter_enabled = core.settings:get_bool("ai_runtime.enable_agents_sdk_adapter", false)
local auto_install = core.settings:get_bool("ai_runtime.agents_sdk_adapter_auto_install", true)

local DEFAULT_ENDPOINT = "http://127.0.0.1:8766/v1/model-adapter"
local DEFAULT_TIMEOUT = 10
local DEFAULT_MAX_POLL_ATTEMPTS = 5000
local DEFAULT_AGENT_ID = "ai_agents_sdk_adapter_probe:operator"
local DEFAULT_OWNER = "synthetic-operator"
local DEFAULT_TASK_ID = "agents-sdk-adapter-probe:operator"
local DEFAULT_PROMPT = "Use your tools to suggest one safe AI-native runtime action."
local MAX_COMMAND_OUTPUT_BYTES = 12000

local http_api
if adapter_enabled and core.request_http_api then
	http_api = core.request_http_api()
end

local function bounded_number(value, fallback, minimum, maximum)
	local result = tonumber(value)
	if not result then
		result = fallback
	end
	result = math.max(minimum, math.min(result, maximum))
	return result
end

local config = {
	endpoint = core.settings:get("ai_runtime.agents_sdk_adapter_endpoint") or DEFAULT_ENDPOINT,
	timeout = bounded_number(
		core.settings:get("ai_runtime.agents_sdk_adapter_timeout"),
		DEFAULT_TIMEOUT,
		1,
		120),
	max_poll_attempts = DEFAULT_MAX_POLL_ATTEMPTS,
	fetcher = nil,
	http_api = http_api,
}

local function clone(value)
	if type(value) ~= "table" then
		return value
	end
	local result = {}
	for key, child in pairs(value) do
		result[key] = clone(child)
	end
	return result
end

local function metric_delta(before, after, key)
	return (after[key] or 0) - (before[key] or 0)
end

local function model_metric_delta(before, after)
	return {
		model_adapter_requests_delta =
			metric_delta(before, after, "model_adapter_requests"),
		model_adapter_successes_delta =
			metric_delta(before, after, "model_adapter_successes"),
		model_adapter_failures_delta =
			metric_delta(before, after, "model_adapter_failures"),
		model_adapter_timeouts_delta =
			metric_delta(before, after, "model_adapter_timeouts"),
	}
end

local function compact_result(result)
	return {
		operation = result.operation,
		status = result.status,
		reason = result.reason,
		message = result.message,
		examined = result.examined,
		skipped = result.skipped,
		metrics = result.metrics,
		response = result.response,
	}
end

local function endpoint_is_loopback(endpoint)
	endpoint = tostring(endpoint or "")
	return endpoint:match("^http://127%.0%.0%.1[:/]")
		or endpoint:match("^http://localhost[:/]")
		or endpoint:match("^http://%[::1%][:/]")
end

local function adapter_response(ok, message, reason, extra)
	local response = {
		schema_version = 1,
		response_kind = "ai_native_model_adapter_response",
		adapter_contract = "provider_neutral_v1",
		ok = ok == true,
		message = message,
		adapter_name = "openai-agents-sdk-sidecar",
		reason = reason,
	}
	for key, value in pairs(extra or {}) do
		response[key] = value
	end
	return response
end

local function make_http_request(request)
	return {
		url = config.endpoint,
		method = "POST",
		timeout = config.timeout,
		data = core.write_json(request),
		extra_headers = {
			"Content-Type: application/json",
			"Accept: application/json",
		},
		user_agent = "ai-native-luanti-agents-sdk-adapter/0.1",
		quiet = true,
	}
end

local function default_fetcher(http_request)
	if not config.http_api then
		return nil, "http_api_unavailable"
	end
	if not config.http_api.fetch_async or not config.http_api.fetch_async_get then
		return nil, "http_api_incomplete"
	end
	local handle = config.http_api.fetch_async(http_request)
	for _ = 1, config.max_poll_attempts do
		local result = config.http_api.fetch_async_get(handle)
		if result and result.completed then
			return result
		end
	end
	return {
		completed = true,
		succeeded = false,
		timeout = true,
		code = 0,
		data = "",
	}, nil
end

local function response_from_http_result(http_result, fetch_error)
	if not http_result then
		return adapter_response(false, "Agents SDK sidecar HTTP API is unavailable.",
			fetch_error or "http_api_unavailable")
	end
	if http_result.timeout then
		return adapter_response(false, "Agents SDK sidecar request timed out.",
			"sidecar_timeout", { timeout = true })
	end
	if not http_result.succeeded or (http_result.code and http_result.code >= 400) then
		return adapter_response(false, "Agents SDK sidecar returned an HTTP error.",
			"sidecar_http_error", { response = { http_code = http_result.code or 0 } })
	end
	local decoded = core.parse_json(http_result.data or "")
	if type(decoded) ~= "table" then
		return adapter_response(false, "Agents SDK sidecar returned invalid JSON.",
			"sidecar_invalid_json")
	end
	if decoded.response_kind ~= "ai_native_model_adapter_response" then
		return adapter_response(false, "Agents SDK sidecar returned an invalid envelope.",
			"sidecar_invalid_response_kind")
	end
	return decoded
end

function plugin.configure(options)
	options = options or {}
	if options.endpoint ~= nil then
		config.endpoint = options.endpoint
	end
	if options.timeout ~= nil then
		config.timeout = options.timeout
	end
	if options.max_poll_attempts ~= nil then
		config.max_poll_attempts = options.max_poll_attempts
	end
	if options.fetcher ~= nil then
		assert(type(options.fetcher) == "function", "Field 'fetcher' must be a function")
		config.fetcher = options.fetcher
	end
	if options.http_api ~= nil then
		config.http_api = options.http_api
	end
	return plugin.get_config()
end

function plugin.get_config()
	return {
		endpoint = config.endpoint,
		timeout = config.timeout,
		max_poll_attempts = config.max_poll_attempts,
		has_fetcher = config.fetcher ~= nil,
		has_http_api = config.http_api ~= nil,
		loopback_endpoint = endpoint_is_loopback(config.endpoint) and true or false,
		enabled = adapter_enabled,
		auto_install = auto_install,
	}
end

function plugin.call_sidecar(request)
	if not endpoint_is_loopback(config.endpoint) then
		return adapter_response(false, "Agents SDK sidecar endpoint must be loopback.",
			"endpoint_not_loopback")
	end
	local http_request = make_http_request(request)
	local fetcher = config.fetcher or default_fetcher
	local ok, http_result, fetch_error = pcall(fetcher, http_request)
	if not ok then
		return adapter_response(false, "Agents SDK sidecar fetch failed.",
			"sidecar_fetch_error")
	end
	return response_from_http_result(http_result, fetch_error)
end

function plugin.call_sidecar_async(request, callback)
	assert(type(callback) == "function", "Field 'callback' must be a function")
	if not endpoint_is_loopback(config.endpoint) then
		callback(adapter_response(false, "Agents SDK sidecar endpoint must be loopback.",
			"endpoint_not_loopback"))
		return false, "endpoint_not_loopback"
	end
	local http_request = make_http_request(request)
	if config.http_api and config.http_api.fetch then
		local ok, err = pcall(config.http_api.fetch, http_request, function(http_result)
			callback(response_from_http_result(http_result))
		end)
		if not ok then
			callback(adapter_response(false, "Agents SDK sidecar fetch failed.",
				"sidecar_fetch_error"))
			return false, err
		end
		return true, "queued"
	end
	callback(plugin.call_sidecar(request))
	return true, "completed"
end

function plugin.install_model_adapter()
	if not core.ai_agent_plugin or not core.ai_agent_plugin.set_model_adapter then
		return false, "ai_agent_plugin_unavailable"
	end
	core.ai_agent_plugin.set_model_adapter(function(request)
		return plugin.call_sidecar(request)
	end)
	if core.ai_agent_plugin.set_model_adapter_async then
		core.ai_agent_plugin.set_model_adapter_async(function(request, callback)
			return plugin.call_sidecar_async(request, callback)
		end)
	end
	return true, "installed"
end

local function ensure_probe_agent(agent_id, owner)
	local agent = core.get_ai_agent(agent_id)
	if agent and agent.capabilities and agent.capabilities["http.llm"] == true then
		return agent
	end
	return core.register_ai_agent({
		agent_id = agent_id,
		display_name = "Agents SDK Adapter Probe",
		owner = owner,
		plugin = "ai_agents_sdk_adapter_plugin",
		capabilities = {
			["http.llm"] = true,
		},
		limits = {
			capability_profile = "agents_sdk_adapter_probe",
		},
	})
end

local function probe_options(options)
	options = options or {}
	return {
		agent_id = options.agent_id or DEFAULT_AGENT_ID,
		owner = options.owner or DEFAULT_OWNER,
		task_id = options.task_id or DEFAULT_TASK_ID,
		prompt = options.prompt or DEFAULT_PROMPT,
		context = clone(options.context or {
			surface_id = "guide",
			capabilities = "world.read,http.llm,task.cancel",
		}),
	}
end

local function public_response(response, result)
	response = response or {}
	return {
		schema_version = 1,
		response_kind = response.response_kind or "ai_native_model_adapter_response",
		adapter_contract = response.adapter_contract or "provider_neutral_v1",
		ok = result.status == "success",
		adapter_name = response.adapter_name or "openai-agents-sdk-sidecar",
		reason = result.reason,
		message = response.message,
	}
end

local function probe_safety(success)
	return {
		public_safe_output = true,
		loopback_endpoint_only = endpoint_is_loopback(config.endpoint) and true or false,
		no_provider_credentials = true,
		private_input_retained = false,
		no_raw_provider_payloads = true,
		adapter_result_accepted = success == true,
		sidecar_executes_world_mutation = false,
	}
end

function plugin.run_probe(options)
	local opts = probe_options(options)
	ensure_probe_agent(opts.agent_id, opts.owner)
	local before = core.get_ai_runtime_metrics()
	local adapter_request
	local adapter_response_value
	local result = core.ai_model_ops.request(opts.prompt, {
		agent_id = opts.agent_id,
		owner = opts.owner,
		task_id = opts.task_id,
		context = opts.context,
		adapter_name = "openai-agents-sdk-sidecar",
		adapter = function(request)
			adapter_request = clone(request)
			adapter_response_value = plugin.call_sidecar(request)
			return adapter_response_value
		end,
	})
	local after = core.get_ai_runtime_metrics()
	local success = result.status == "success"
	return {
		schema_version = 1,
		operation = "ai_agents_sdk_adapter_plugin.run_probe",
		ok = success,
		status = result.status,
		reason = result.reason,
		config = plugin.get_config(),
		request = adapter_request,
		response = public_response(adapter_response_value, result),
		result = compact_result(result),
		metrics = model_metric_delta(before, after),
		safety = probe_safety(success),
	}
end

function plugin.run_probe_async(options, callback)
	assert(type(callback) == "function", "Field 'callback' must be a function")
	if not core.ai_model_ops or not core.ai_model_ops.request_async then
		callback(plugin.run_probe(options))
		return true, "completed"
	end
	local opts = probe_options(options)
	ensure_probe_agent(opts.agent_id, opts.owner)
	local before = core.get_ai_runtime_metrics()
	local adapter_request
	local adapter_response_value
	return core.ai_model_ops.request_async(opts.prompt, {
		agent_id = opts.agent_id,
		owner = opts.owner,
		task_id = opts.task_id,
		context = opts.context,
		adapter_name = "openai-agents-sdk-sidecar",
		adapter_async = function(request, done)
			adapter_request = clone(request)
			return plugin.call_sidecar_async(request, function(response)
				adapter_response_value = response
				done(response)
			end)
		end,
	}, function(result)
		local after = core.get_ai_runtime_metrics()
		local success = result.status == "success"
		callback({
			schema_version = 1,
			operation = "ai_agents_sdk_adapter_plugin.run_probe_async",
			ok = success,
			status = result.status,
			reason = result.reason,
			config = plugin.get_config(),
			request = adapter_request,
			response = public_response(adapter_response_value, result),
			result = compact_result(result),
			metrics = model_metric_delta(before, after),
			safety = probe_safety(success),
		})
	end)
end

local function encode_report(report)
	local encoded = core.write_json(report)
	if #encoded <= MAX_COMMAND_OUTPUT_BYTES then
		return encoded
	end
	report = clone(report)
	if report.request then
		report.request.context = nil
	end
	if report.result then
		report.result.metrics = nil
	end
	report.command = {
		truncated = true,
		reason = "command_output_truncated",
	}
	return core.write_json(report)
end

local function parse_command_options(param)
	local options = {}
	for token in string.gmatch(param or "", "%S+") do
		local key, value = token:match("^([^=]+)=(.+)$")
		if not key then
			return nil, "Use key=value parameters."
		end
		if key == "task" or key == "task_id" then
			options.task_id = value
		elseif key == "agent" or key == "agent_id" then
			options.agent_id = value
		elseif key == "endpoint" then
			options.endpoint = value
		else
			return nil, "unknown option: " .. key
		end
	end
	return options
end

function plugin.run_command(param)
	local options, err = parse_command_options(param)
	if not options then
		return false, err
	end
	if options.endpoint then
		plugin.configure({ endpoint = options.endpoint })
	end
	return true, encode_report(plugin.run_probe(options))
end

if adapter_enabled then
	core.register_chatcommand("ai_agents_sdk_adapter_probe", {
		params = "[task=ID] [agent=ID] [endpoint=http://127.0.0.1:8766/v1/model-adapter]",
		description = "Run the Agents SDK model adapter sidecar probe and return bounded JSON.",
		privs = { server = true },
		func = function(_, param)
			return plugin.run_command(param)
		end,
	})
	core.register_chatcommand("ai_agents_sdk_adapter_probe_async", {
		params = "[task=ID] [agent=ID] [endpoint=http://127.0.0.1:8766/v1/model-adapter]",
		description = "Queue the Agents SDK model adapter sidecar probe and emit bounded JSON when complete.",
		privs = { server = true },
		func = function(name, param)
			local options, err = parse_command_options(param)
			if not options then
				return false, err
			end
			if options.endpoint then
				plugin.configure({ endpoint = options.endpoint })
			end
			local queued, reason = plugin.run_probe_async(options, function(report)
				local encoded = encode_report(report)
				core.log("action", "[ai_runtime] ai_agents_sdk_adapter_probe_async result="
					.. encoded)
				if name and name ~= "" and core.chat_send_player then
					core.chat_send_player(name, encoded)
				end
			end)
			if not queued then
				return false, reason
			end
			return true, "Agents SDK adapter probe queued."
		end,
	})
	if auto_install then
		plugin.install_model_adapter()
	end
end
