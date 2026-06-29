core.ai_operator_task_control = {}

local task_control = core.ai_operator_task_control
local DEFAULT_MAX_BYTES = 24000
local EXECUTION_LIMIT = 24
local FIELD_TEXT_LIMIT = 240

local private_redactions = {
	{ pattern = "/Users/[^%s\"']+", replacement = "<redacted-local-path>" },
	{ pattern = "minecraftpi%.home", replacement = "<redacted-private-host>" },
	{ pattern = "minecraftpi", replacement = "<redacted-private-host>" },
	{ pattern = "192%.168%.%d+%.%d+", replacement = "<redacted-private-ip>" },
	{ pattern = "spacebase", replacement = "<redacted-private-demo>" },
	{ pattern = "themepark", replacement = "<redacted-private-demo>" },
	{ pattern = "showcase100", replacement = "<redacted-private-demo>" },
	{ pattern = "disneyland100", replacement = "<redacted-private-demo>" },
	{ pattern = "OPENAI_API_KEY", replacement = "<redacted-secret-env>" },
	{ pattern = "private_prompt", replacement = "<redacted-private-prompt>" },
	{ pattern = "asset_payload", replacement = "<redacted-asset-payload>" },
}

local function redaction_context()
	return { count = 0, truncations = 0 }
end

local function redact_secret_tokens(text, context)
	local result = {}
	local index = 1
	while true do
		local start_pos, end_pos = text:find("sk%-[%w_-]+", index)
		if not start_pos then
			result[#result + 1] = text:sub(index)
			break
		end
		local previous = start_pos > 1 and text:sub(start_pos - 1, start_pos - 1) or ""
		if previous ~= "" and previous:match("[%w_-]") then
			result[#result + 1] = text:sub(index, end_pos)
		else
			result[#result + 1] = text:sub(index, start_pos - 1)
			result[#result + 1] = "<redacted-secret>"
			context.count = context.count + 1
		end
		index = end_pos + 1
	end
	return table.concat(result)
end

local function redact(value, context)
	if value == nil then
		return nil
	end
	local text = tostring(value)
	for _, redaction in ipairs(private_redactions) do
		local redacted, count = text:gsub(redaction.pattern, redaction.replacement)
		text = redacted
		context.count = context.count + count
	end
	text = redact_secret_tokens(text, context)
	if #text > FIELD_TEXT_LIMIT then
		text = text:sub(1, FIELD_TEXT_LIMIT) .. "<truncated>"
		context.truncations = context.truncations + 1
	end
	return text
end

local function contains_private_content(value)
	local text = core.write_json and core.write_json(value) or tostring(value)
	for _, redaction in ipairs(private_redactions) do
		if text:find(redaction.pattern) then
			return true
		end
	end
	local index = 1
	while true do
		local start_pos, end_pos = text:find("sk%-[%w_-]+", index)
		if not start_pos then
			return false
		end
		local previous = start_pos > 1 and text:sub(start_pos - 1, start_pos - 1) or ""
		if previous == "" or not previous:match("[%w_-]") then
			return true
		end
		index = end_pos + 1
	end
end

local function sorted_values(values)
	table.sort(values)
	return values
end

local function list_to_set(values)
	local result = {}
	for _, value in ipairs(values or {}) do
		result[tostring(value)] = true
	end
	return result
end

local function missing_values(required, acknowledged)
	local acknowledged_set = list_to_set(acknowledged)
	local missing = {}
	for _, value in ipairs(required or {}) do
		local key = tostring(value)
		if not acknowledged_set[key] then
			missing[#missing + 1] = key
		end
	end
	return sorted_values(missing)
end

local function count_by(results, field)
	local counts = {}
	for _, result in ipairs(results) do
		local key = result[field] or "none"
		counts[key] = (counts[key] or 0) + 1
	end
	return counts
end

local function receipt_decisions(receipt)
	if type(receipt.decisions) == "table" then
		return receipt.decisions
	end
	local operator_decisions = receipt.operator_decisions
	if type(operator_decisions) == "table" and type(operator_decisions.decisions) == "table" then
		return operator_decisions.decisions
	end
	return nil
end

local function operation_for_decision(decision)
	if decision.task_operation == "cancel" then
		return "cancel", "task.cancel"
	end
	if decision.task_operation == "retry" then
		return "retry", "task.retry"
	end
	if decision.approval_kind == "task_cancel_retry_review" then
		return "cancel", "task.cancel"
	end
	if decision.approval_kind == "task_retry_review" then
		return "retry", "task.retry"
	end
	return nil, nil
end

local function safe_result_base(decision, context)
	return {
		decision_id = redact(decision.decision_id or "unknown", context),
		decision_status = redact(decision.decision_status or "unknown", context),
		target_kind = redact(decision.target_kind or "unknown", context),
		target_id = redact(decision.target_id or "unknown", context),
		approval_kind = redact(decision.approval_kind or "unknown", context),
		safe_next_action = redact(decision.safe_next_action or "unknown", context),
	}
end

local function reject(decision, context, reason)
	local result = safe_result_base(decision, context)
	result.status = "rejected"
	result.reason = reason
	result.operation = "none"
	result.mutation_performed = false
	return result
end

local function invalid_receipt_result(reason, receipt, options, context)
	local decisions = type(receipt) == "table" and receipt_decisions(receipt) or {}
	if type(decisions) ~= "table" then
		decisions = {}
	end
	local result = {
		schema_version = 1,
		command_result_kind = "ai_native_operator_task_control_command_result",
		status = "rejected",
		generated_at = options.generated_at or tostring(core.get_us_time and core.get_us_time() or 0),
		runtime_context = {
			game_profile = "ai_runtime",
			command = "/ai_runtime_operator_task_control",
			source = "live_runtime_state",
			actor = redact(options.actor or "unknown", context),
			world_mutation_performed = false,
		},
		source_receipt = {
			receipt_kind = type(receipt) == "table" and redact(receipt.receipt_kind or "unknown", context) or "invalid",
			generated_at = type(receipt) == "table" and redact(receipt.generated_at or "unknown", context) or "unknown",
		},
		operator_actions = {
			mode = "receipt_gated_task_cancel_retry",
			mutation_scope = "live_task_queue",
			mutation_performed = false,
			task_queue_mutation_performed = false,
			world_mutation_performed = false,
			allowed_operations = { "cancel", "retry" },
			allowed_approval_kinds = { "task_cancel_retry_review", "task_retry_review" },
			truncated = false,
		},
		summary = {
			decisions_total = math.min(#decisions, EXECUTION_LIMIT),
			source_decisions_total = #decisions,
			executed_total = 0,
			rejected_total = math.max(1, math.min(#decisions, EXECUTION_LIMIT)),
			skipped_total = 0,
			results_retained = 1,
			by_result_status = { rejected = math.max(1, math.min(#decisions, EXECUTION_LIMIT)) },
			by_operation = { none = math.max(1, math.min(#decisions, EXECUTION_LIMIT)) },
			by_rejection_reason = { [reason] = math.max(1, math.min(#decisions, EXECUTION_LIMIT)) },
			attention_required = true,
		},
		results = {
			{
				status = "rejected",
				reason = reason,
				operation = "none",
				mutation_performed = false,
			},
		},
		safety = {
			public_safe_output = true,
			receipt_required = true,
			receipt_gated = true,
			task_control_only = true,
			task_queue_mutation_only = true,
			world_mutation_performed = false,
			no_world_mutation = true,
			no_rollback_execution = true,
			no_import_promotion_execution = true,
			no_structure_apply = true,
			no_raw_assets = true,
			no_provider_prompts = true,
			no_family_world_coordinates = true,
			redactions_applied = 0,
			truncations_applied = 0,
		},
	}
	return result
end

local function validate_receipt(receipt, options)
	if type(receipt) ~= "table" then
		return nil, "invalid_receipt"
	end
	if receipt.receipt_kind ~= "ai_native_operator_action_approval_receipt" then
		return nil, "invalid_receipt_kind"
	end
	local operator_decisions = receipt.operator_decisions
	if type(operator_decisions) ~= "table" then
		return nil, "invalid_operator_decisions"
	end
	if operator_decisions.mode ~= "receipt_only" then
		return nil, "invalid_receipt_mode"
	end
	if operator_decisions.mutation_performed ~= false then
		return nil, "receipt_already_mutated"
	end
	local decisions = receipt_decisions(receipt)
	if type(decisions) ~= "table" then
		return nil, "invalid_receipt_decisions"
	end
	if receipt.expired_at ~= nil and options.generated_at ~= nil
			and tostring(receipt.expired_at) < tostring(options.generated_at) then
		return nil, "receipt_stale"
	end
	local safety = type(receipt.safety) == "table" and receipt.safety or {}
	for _, field in ipairs({
		"public_safe_output",
		"receipt_only",
		"no_world_mutation",
		"no_rollback_execution",
		"no_import_promotion_execution",
		"no_raw_assets",
		"no_provider_prompts",
		"no_family_world_coordinates",
	}) do
		if safety[field] ~= true then
			return nil, "unsafe_receipt"
		end
	end
	local bounds = type(receipt.bounds) == "table" and receipt.bounds or {}
	local output_bytes = tonumber(bounds.output_bytes or 0) or 0
	local receipt_max_bytes = tonumber(bounds.max_bytes or options.max_bytes) or options.max_bytes
	if output_bytes > receipt_max_bytes or output_bytes > options.max_bytes then
		return nil, "receipt_oversized"
	end
	if contains_private_content(receipt) then
		return nil, "private_receipt_content"
	end
	return decisions, nil
end

local function validate_decision(decision, context)
	if type(decision) ~= "table" then
		return false, "invalid_decision"
	end
	for _, field in ipairs({
		"decision_id",
		"decision_status",
		"target_kind",
		"target_id",
		"safe_next_action",
		"approval_kind",
	}) do
		if type(decision[field]) ~= "string" or decision[field] == "" then
			return false, "invalid_decision"
		end
	end
	if decision.decision_status ~= "approved" then
		return false, "decision_not_approved"
	end
	if decision.target_kind ~= "task" then
		return false, "unsupported_target_kind"
	end
	local operation = operation_for_decision(decision)
	if operation == nil then
		return false, "unsupported_approval_kind"
	end
	if decision.approval_required ~= true then
		return false, "approval_required_missing"
	end
	if decision.dry_run_only ~= true then
		return false, "decision_not_dry_run_only"
	end
	if decision.will_mutate ~= false or decision.mutation_performed ~= false then
		return false, "decision_declares_mutation"
	end
	if decision.receipt_only ~= true then
		return false, "decision_not_receipt_only"
	end
	if type(decision.prerequisites_required) ~= "table"
			or type(decision.prerequisites_acknowledged) ~= "table" then
		return false, "invalid_prerequisites"
	end
	local missing_prerequisites = missing_values(
		decision.prerequisites_required,
		decision.prerequisites_acknowledged
	)
	if #missing_prerequisites > 0 then
		local result = reject(decision, context, "missing_acknowledged_prerequisite")
		result.missing_prerequisites = missing_prerequisites
		return false, result
	end
	if type(decision.required_capabilities) ~= "table" then
		return false, "invalid_required_capabilities"
	end
	return true, nil
end

local function capability_allowed(capabilities, capability)
	if capabilities[capability] then
		return true
	end
	if capability == "task.cancel" and capabilities["task.cancel.review"] then
		return true
	end
	if capability == "task.retry" and capabilities["task.retry.review"] then
		return true
	end
	return false
end

local function reject_missing_capability(decision, required_capability, capabilities, context)
	if capability_allowed(capabilities, required_capability) then
		return nil
	end
	local result = reject(decision, context, "missing_executor_capability")
	result.missing_executor_capabilities = { required_capability }
	return result
end

local function execute_decision(decision, options, context)
	local valid, invalid_reason = validate_decision(decision, context)
	if not valid then
		if type(invalid_reason) == "table" then
			return invalid_reason
		end
		return reject(decision, context, invalid_reason)
	end
	local operation, required_capability = operation_for_decision(decision)
	local capabilities = options.executor_capabilities or {}
	local missing = reject_missing_capability(decision, "task.inspect", capabilities, context)
	if missing then
		return missing
	end
	missing = reject_missing_capability(decision, required_capability, capabilities, context)
	if missing then
		return missing
	end
	local task_before = core.get_ai_task(decision.target_id)
	local before_status = task_before and task_before.status or "unknown"
	local action_result = nil
	if operation == "cancel" then
		action_result = core.cancel_ai_task(decision.target_id, options.actor)
	else
		action_result = core.retry_ai_task(decision.target_id, options.actor)
	end
	if not action_result or action_result.ok ~= true then
		local result = reject(decision, context,
			action_result and action_result.reason or "task_control_failed")
		result.before_status = redact(before_status, context)
		result.action_status = action_result and redact(action_result.status, context) or "failed"
		return result
	end
	local task_after = core.get_ai_task(decision.target_id)
	local result = safe_result_base(decision, context)
	result.status = "executed"
	result.reason = "approved_receipt"
	result.operation = operation
	result.before_status = redact(before_status, context)
	result.after_status = redact(task_after and task_after.status or action_result.status, context)
	result.mutation_performed = true
	result.mutation_scope = "live_task_queue"
	result.audit_event = operation == "cancel" and "task.cancelled" or "task.retried"
	return result
end

local function apply_bounds(result, max_bytes)
	local function refresh_size()
		result.bounds.output_bytes = #core.write_json(result)
		return result.bounds.output_bytes
	end
	local function trim_results(limit)
		local retained = {}
		for i = 1, math.min(#result.results, limit) do
			retained[#retained + 1] = result.results[i]
		end
		result.results = retained
		result.bounds.truncated = true
		result.operator_actions.truncated = true
		result.summary.results_retained = #result.results
	end

	result.bounds = {
		max_bytes = max_bytes,
		output_bytes = 0,
		truncated = result.operator_actions.truncated,
	}
	if refresh_size() > max_bytes then
		trim_results(8)
		refresh_size()
	end
	if result.bounds.output_bytes > max_bytes then
		trim_results(0)
		refresh_size()
	end
	return result
end

function task_control.apply_receipt(receipt, options)
	options = options or {}
	options.actor = options.actor or "admin"
	options.max_bytes = options.max_bytes or DEFAULT_MAX_BYTES
	options.executor_capabilities = options.executor_capabilities or {
		["task.inspect"] = true,
		["task.cancel"] = true,
		["task.retry"] = true,
	}
	local context = redaction_context()
	local decisions, invalid_reason = validate_receipt(receipt, options)
	if not decisions then
		local invalid = invalid_receipt_result(invalid_reason, receipt, options, context)
		invalid.safety.redactions_applied = context.count
		invalid.safety.truncations_applied = context.truncations
		return apply_bounds(invalid, options.max_bytes)
	end

	local selected_decisions = {}
	for i = 1, math.min(#decisions, EXECUTION_LIMIT) do
		selected_decisions[#selected_decisions + 1] = decisions[i]
	end
	local results = {}
	for _, decision in ipairs(selected_decisions) do
		results[#results + 1] = execute_decision(decision, options, context)
	end
	local status_counts = count_by(results, "status")
	local operation_counts = count_by(results, "operation")
	local rejection_counts = {}
	for _, result in ipairs(results) do
		if result.status ~= "executed" then
			local reason = result.reason or "none"
			rejection_counts[reason] = (rejection_counts[reason] or 0) + 1
		end
	end
	local executed_total = status_counts.executed or 0
	local rejected_total = status_counts.rejected or 0
	local result = {
		schema_version = 1,
		command_result_kind = "ai_native_operator_task_control_command_result",
		status = rejected_total > 0 and "attention" or "ready",
		generated_at = options.generated_at or tostring(core.get_us_time and core.get_us_time() or 0),
		runtime_context = {
			game_profile = "ai_runtime",
			command = "/ai_runtime_operator_task_control",
			source = "live_runtime_state",
			actor = redact(options.actor, context),
			world_mutation_performed = false,
		},
		source_receipt = {
			receipt_kind = redact(receipt.receipt_kind or "unknown", context),
			status = redact(receipt.status or "unknown", context),
			generated_at = redact(receipt.generated_at or "unknown", context),
		},
		operator_actions = {
			mode = "receipt_gated_task_cancel_retry",
			mutation_scope = "live_task_queue",
			mutation_performed = executed_total > 0,
			task_queue_mutation_performed = executed_total > 0,
			world_mutation_performed = false,
			allowed_operations = { "cancel", "retry" },
			allowed_approval_kinds = { "task_cancel_retry_review", "task_retry_review" },
			truncated = #decisions > EXECUTION_LIMIT,
		},
		summary = {
			decisions_total = #selected_decisions,
			source_decisions_total = #decisions,
			executed_total = executed_total,
			rejected_total = rejected_total,
			skipped_total = status_counts.skipped or 0,
			results_retained = #results,
			by_result_status = status_counts,
			by_operation = operation_counts,
			by_rejection_reason = rejection_counts,
			attention_required = rejected_total > 0 or #decisions > EXECUTION_LIMIT,
		},
		results = results,
		safety = {
			public_safe_output = true,
			receipt_required = true,
			receipt_gated = true,
			task_control_only = true,
			task_queue_mutation_only = true,
			world_mutation_performed = false,
			no_world_mutation = true,
			no_rollback_execution = true,
			no_import_promotion_execution = true,
			no_structure_apply = true,
			no_raw_assets = true,
			no_provider_prompts = true,
			no_family_world_coordinates = true,
			redactions_applied = context.count,
			truncations_applied = context.truncations,
		},
	}
	return apply_bounds(result, options.max_bytes)
end

core.apply_ai_operator_task_control_receipt = task_control.apply_receipt

local function parse_command_options(param)
	local options = {
		executor_capabilities = {
			["task.inspect"] = true,
			["task.cancel"] = true,
			["task.retry"] = true,
		},
	}
	local option_text = param or ""
	local receipt_start = option_text:find("receipt_json=", 1, true)
	if receipt_start then
		local receipt_json = option_text:sub(receipt_start + #"receipt_json=")
		option_text = option_text:sub(1, receipt_start - 1)
		local receipt = core.parse_json(receipt_json)
		if type(receipt) ~= "table" then
			return nil, "receipt_json must be valid JSON"
		end
		options.receipt = receipt
	end
	for token in string.gmatch(option_text, "%S+") do
		local key, value = token:match("^([%w_]+)=(.+)$")
		if not key then
			return nil, "unknown option '" .. token .. "'"
		end
		if key == "generated_at" then
			options.generated_at = value
		elseif key == "max_bytes" then
			local max_bytes = tonumber(value)
			if not max_bytes or max_bytes < 1000 then
				return nil, "max_bytes must be at least 1000"
			end
			options.max_bytes = max_bytes
		else
			return nil, "unknown option '" .. key .. "'"
		end
	end
	if not options.receipt then
		return nil, "receipt_json is required"
	end
	return options
end

core.register_chatcommand("ai_runtime_operator_task_control", {
	params = "[generated_at=ISO_OR_LABEL] [max_bytes=N] receipt_json=JSON",
	description = "Apply approved receipt-gated AI runtime task cancel/retry decisions and return bounded public-safe JSON.",
	privs = { server = true },
	func = function(name, param)
		local options, err = parse_command_options(param)
		if not options then
			return false, err
		end
		options.actor = name
		local result = task_control.apply_receipt(options.receipt, options)
		return true, core.write_json(result)
	end,
})
