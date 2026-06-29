core.ai_model_adapter_plugin = {}

local plugin = core.ai_model_adapter_plugin
local dev_command_enabled = core.settings:get_bool("ai_runtime.enable_model_adapter_probe_command", false)

local DEFAULT_AGENT_ID = "ai_model_adapter_probe:operator"
local DEFAULT_OWNER = "synthetic-operator"
local DEFAULT_TASK_ID = "model-adapter-probe:operator"
local DEFAULT_PROMPT = "Suggest one safe AI-native runtime verification action."
local DEFAULT_WORLD_REF = "world:synthetic-model-adapter-probe"
local MAX_COMMAND_OUTPUT_BYTES = 12000

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
	}
end

local function ensure_probe_agent(agent_id, owner)
	local agent = core.get_ai_agent(agent_id)
	if agent and agent.capabilities and agent.capabilities["http.llm"] == true then
		return agent
	end
	return core.register_ai_agent({
		agent_id = agent_id,
		display_name = "Model Adapter Probe",
		owner = owner,
		plugin = "ai_model_adapter_plugin",
		capabilities = {
			["http.llm"] = true,
		},
		limits = {
			capability_profile = "model_adapter_probe",
		},
	})
end

local function probe_options(options)
	options = options or {}
	local context = clone(options.context or {})
	if context.world_ref == nil then
		context.world_ref = DEFAULT_WORLD_REF
	end
	if context.intent == nil then
		context.intent = "runtime_probe"
	end
	return {
		agent_id = options.agent_id or DEFAULT_AGENT_ID,
		owner = options.owner or DEFAULT_OWNER,
		task_id = options.task_id or DEFAULT_TASK_ID,
		prompt = options.prompt or DEFAULT_PROMPT,
		context = context,
	}
end

local function safe_probe_response(request)
	return {
		schema_version = 1,
		response_kind = "ai_native_model_adapter_response",
		adapter_contract = request.adapter_contract,
		ok = true,
		message = "Mock provider-neutral adapter response.",
		adapter_name = "mock-provider-neutral",
		elapsed_us = 1000,
		response = {
			action = "review_agent_task_status",
			confidence = "synthetic",
		},
	}
end

local function unsafe_probe_response(request)
	return {
		schema_version = 1,
		response_kind = "ai_native_model_adapter_response",
		adapter_contract = request.adapter_contract,
		ok = true,
		message = "Unsafe mock adapter response.",
		adapter_name = "mock-provider-neutral-unsafe",
		elapsed_us = 1000,
		raw_provider_response = {
			blocked = true,
		},
	}
end

local function public_response(response, result)
	response = response or {}
	return {
		schema_version = 1,
		response_kind = "ai_native_model_adapter_response",
		adapter_contract = response.adapter_contract or "provider_neutral_v1",
		ok = result.status == "success",
		adapter_name = response.adapter_name or "mock-provider-neutral",
		reason = result.reason,
	}
end

local function probe_safety(success)
	return {
		public_safe_output = true,
		no_provider_credentials = true,
		no_network_adapter = true,
		private_input_retained = false,
		no_raw_provider_payloads = true,
		adapter_result_accepted = success == true,
	}
end

local function build_probe_report(kind, opts, adapter_factory)
	ensure_probe_agent(opts.agent_id, opts.owner)
	local before = core.get_ai_runtime_metrics()
	local adapter_request
	local adapter_response
	local result = core.ai_model_ops.request(opts.prompt, {
		agent_id = opts.agent_id,
		owner = opts.owner,
		task_id = opts.task_id,
		context = opts.context,
		adapter = function(request)
			adapter_request = clone(request)
			adapter_response = adapter_factory(request)
			return adapter_response
		end,
	})
	local after = core.get_ai_runtime_metrics()
	local success = result.status == "success"
	return {
		schema_version = 1,
		operation = kind,
		ok = success,
		status = result.status,
		reason = result.reason,
		request = adapter_request,
		response = public_response(adapter_response, result),
		result = compact_result(result),
		metrics = model_metric_delta(before, after),
		safety = probe_safety(success),
	}
end

function plugin.run_probe(options)
	return build_probe_report("ai_model_adapter_plugin.run_probe",
		probe_options(options), safe_probe_response)
end

function plugin.run_unsafe_payload_probe(options)
	return build_probe_report("ai_model_adapter_plugin.run_unsafe_payload_probe",
		probe_options(options), unsafe_probe_response)
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
	return true, encode_report(plugin.run_probe(options))
end

if dev_command_enabled then
	core.register_chatcommand("ai_model_adapter_probe", {
		params = "[task=ID] [agent=ID]",
		description = "Run the provider-neutral AI model adapter probe and return bounded JSON.",
		privs = { server = true },
		func = function(_, param)
			return plugin.run_command(param)
		end,
	})
end
