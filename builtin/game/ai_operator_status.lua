core.ai_operator_status = {}

local operator_status = core.ai_operator_status
local DEFAULT_MAX_BYTES = 24000
local SUMMARY_LIMIT = 12
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
	{ pattern = "sk%-[%w_-]+", replacement = "<redacted-secret>" },
	{ pattern = "OPENAI_API_KEY", replacement = "<redacted-secret-env>" },
	{ pattern = "private_prompt", replacement = "<redacted-private-prompt>" },
	{ pattern = "asset_payload", replacement = "<redacted-asset-payload>" },
}

local function redaction_context()
	return { count = 0, truncations = 0 }
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
	if #text > FIELD_TEXT_LIMIT then
		text = text:sub(1, FIELD_TEXT_LIMIT) .. "<truncated>"
		context.truncations = context.truncations + 1
	end
	return text
end

local function sorted_keys(map)
	local keys = {}
	for key, enabled in pairs(map or {}) do
		if enabled then
			keys[#keys + 1] = key
		end
	end
	table.sort(keys)
	return keys
end

local function sorted_values(values)
	table.sort(values)
	return values
end

local function count_status(items)
	local counts = {}
	for _, item in ipairs(items or {}) do
		local status = item.status or "unknown"
		counts[status] = (counts[status] or 0) + 1
	end
	return counts
end

local function truncate_to(list, limit)
	local result = {}
	for i = 1, math.min(#list, limit or SUMMARY_LIMIT) do
		result[#result + 1] = list[i]
	end
	return result, #list > (limit or SUMMARY_LIMIT)
end

local function truncate(list)
	return truncate_to(list, SUMMARY_LIMIT)
end

local function sorted_agents()
	local agents = {}
	for _, agent in pairs(core.registered_ai_agents or {}) do
		agents[#agents + 1] = agent
	end
	table.sort(agents, function(a, b)
		return tostring(a.agent_id) < tostring(b.agent_id)
	end)
	return agents
end

local function summarize_agents(context)
	local summaries = {}
	local profiles = {}
	for _, agent in ipairs(sorted_agents()) do
		local profile = agent.limits and agent.limits.capability_profile or "unspecified"
		profiles[profile] = true
		summaries[#summaries + 1] = {
			agent_id = redact(agent.agent_id, context),
			owner = redact(agent.owner, context),
			capability_profile = redact(profile, context),
			capabilities = sorted_values((function()
				local capabilities = {}
				for _, capability in ipairs(sorted_keys(agent.capabilities)) do
					capabilities[#capabilities + 1] = redact(capability, context)
				end
				return capabilities
			end)()),
		}
	end
	local limited, truncated = truncate(summaries)
	local profile_names = {}
	for profile in pairs(profiles) do
		profile_names[#profile_names + 1] = redact(profile, context)
	end
	return {
		total = #summaries,
		capability_profiles = sorted_values(profile_names),
		summaries = limited,
		truncated = truncated,
	}
end

local function sorted_tasks()
	local tasks = {}
	for _, task in pairs(core.registered_ai_tasks or {}) do
		tasks[#tasks + 1] = task
	end
	table.sort(tasks, function(a, b)
		return tostring(a.task_id) < tostring(b.task_id)
	end)
	return tasks
end

local function task_counts(tasks)
	local counts = { total = #tasks }
	for _, task in ipairs(tasks) do
		local status = task.status or "unknown"
		counts[status] = (counts[status] or 0) + 1
	end
	return counts
end

local function compact_navigation_metrics(metrics, context)
	if type(metrics) ~= "table" then
		return nil
	end
	if metrics.path_status == nil and metrics.blocked_reason == nil
			and metrics.nodes_searched == nil then
		return nil
	end
	return {
		path_status = redact(metrics.path_status, context),
		path_planner = redact(metrics.path_planner, context),
		blocked_reason = redact(metrics.blocked_reason, context),
		skipped_reason = redact(metrics.skipped_reason, context),
		step_distance = metrics.step_distance,
		distance_to_target = metrics.distance_to_target,
		distance_moved = metrics.distance_moved,
		total_distance_moved = metrics.total_distance_moved,
		steps_run = metrics.steps_run,
		max_steps = metrics.max_steps,
		max_step_distance = metrics.max_step_distance,
		max_total_distance = metrics.max_total_distance,
		path_waypoint_count = metrics.path_waypoint_count,
		pathfinder_used = metrics.pathfinder_used == true,
		nodes_searched = metrics.nodes_searched,
		max_nodes_searched = metrics.max_nodes_searched,
		obstacles_seen = metrics.obstacles_seen,
		navigation_elapsed_us = metrics.navigation_elapsed_us,
		max_wall_time_ms = metrics.max_wall_time_ms,
	}
end

local function summarize_tasks(context, limit)
	local tasks = sorted_tasks()
	local summaries = {}
	for _, task in ipairs(tasks) do
		local summary = {
			task_id = redact(task.task_id, context),
			agent_id = redact(task.agent_id, context),
			status = redact(task.status or "unknown", context),
			duration_us = task.duration_us,
		}
		if task.label then
			summary.label = redact(task.label, context)
		end
		local reason = task.last_result and task.last_result.reason
		if reason then
			summary.reason = redact(reason, context)
		end
		local navigation = compact_navigation_metrics(
			task.last_result and task.last_result.metrics,
			context
		)
		if navigation then
			summary.navigation = navigation
		end
		summaries[#summaries + 1] = summary
	end
	local limited, truncated = truncate_to(summaries, limit or SUMMARY_LIMIT)
	return {
		counts = task_counts(tasks),
		summaries = limited,
		truncated = truncated,
	}
end

local function compact_task_detail(task, context)
	if not task then
		return nil
	end
	local last_result = task.last_result or {}
	local detail = {
		task_id = redact(task.task_id, context),
		agent_id = redact(task.agent_id, context),
		owner = redact(task.owner, context),
		label = redact(task.label, context),
		status = redact(task.status or "unknown", context),
		created_at = task.created_at,
		updated_at = task.updated_at,
		duration_us = task.duration_us,
		retry_count = task.retry_count or 0,
		budget = {
			max_steps_per_step = task.budget and task.budget.max_steps_per_step or nil,
			max_node_writes_per_step = task.budget and task.budget.max_node_writes_per_step or nil,
			max_wall_time_ms = task.budget and task.budget.max_wall_time_ms or nil,
		},
		progress = {
			current = task.progress and task.progress.current or 0,
			total = task.progress and task.progress.total or 0,
		},
		last_result = {
			status = redact(last_result.status, context),
			reason = redact(last_result.reason, context),
			message = redact(last_result.message, context),
			operation = redact(last_result.operation, context),
			changed = last_result.changed,
			examined = last_result.examined,
			skipped = last_result.skipped,
			rollback_record_id = redact(last_result.rollback_record_id, context),
			rollback_storage_ref = redact(last_result.rollback_storage_ref, context),
			navigation = compact_navigation_metrics(last_result.metrics, context),
		},
	}
	return detail
end

local function summarize_audit(context, audit_records)
	local summaries = {}
	for _, record in ipairs(audit_records or {}) do
		summaries[#summaries + 1] = {
			event_type = redact(record.event_type or "unknown", context),
			agent_id = redact(record.agent_id, context),
			task_id = redact(record.task_id, context),
			status = redact(record.status or "unknown", context),
			reason = redact(record.reason, context),
			message = redact(record.message, context),
			operation = redact(record.operation, context),
			rollback_record_id = redact(record.rollback_record_id, context),
			rollback_storage_ref = redact(record.rollback_storage_ref, context),
			changed = record.changed,
			skipped = record.skipped,
		}
	end
	local limited, truncated = truncate(summaries)
	return {
		records_total = #summaries,
		status_counts = count_status(summaries),
		event_counts = (function()
			local counts = {}
			for _, summary in ipairs(summaries) do
				local event_type = summary.event_type or "unknown"
				counts[event_type] = (counts[event_type] or 0) + 1
			end
			return counts
		end)(),
		summaries = limited,
		truncated = truncated,
	}
end

local function summarize_rollback(context, audit_records)
	local records = {}
	for _, record in ipairs(audit_records) do
		if record.event_type == "rollback.record" then
			records[#records + 1] = {
				record_id = redact(record.rollback_record_id or "unknown", context),
				task_id = redact(record.task_id or "unknown", context),
				status = redact(record.status or "available", context),
				storage_ref = redact(record.rollback_storage_ref, context),
			}
		end
	end
	local available = 0
	for _, record in ipairs(records) do
		if record.status == "success" or record.status == "available"
				or record.status == "recorded" then
			available = available + 1
		end
	end
	local limited, truncated = truncate(records)
	return {
		records_total = #records,
		records_available = available,
		status_counts = count_status(records),
		summaries = limited,
		truncated = truncated,
	}
end

local function summarize_imports(context, audit_records, promotion_packages)
	local reviews = {}
	for _, record in ipairs(audit_records) do
		if type(record.event_type) == "string" and record.event_type:sub(1, 7) == "import." then
			reviews[#reviews + 1] = {
				review_id = redact(record.task_id or record.event_type, context),
				status = redact(record.status or "unknown", context),
				rights_confirmed = record.status == "success",
				source = redact(record.reason or record.message or record.event_type, context),
			}
		end
	end
	local promotion_summaries = {}
	for _, package in ipairs(promotion_packages or {}) do
		promotion_summaries[#promotion_summaries + 1] = {
			package_id = redact(package.package_id or "unknown", context),
			status = redact(package.status or "unknown", context),
			approval_confirmed = package.approval_confirmed == true,
			source = redact(package.source, context),
		}
	end
	local limited_reviews, reviews_truncated = truncate(reviews)
	local limited_promotions, promotions_truncated = truncate(promotion_summaries)
	return {
		reviews_total = #reviews,
		promotions_total = #promotion_summaries,
		status_counts = count_status(reviews),
		promotion_status_counts = count_status(promotion_summaries),
		summaries = limited_reviews,
		promotion_summaries = limited_promotions,
		truncated = reviews_truncated or promotions_truncated,
	}
end

local function summarize_benchmarks(context, gates)
	local summaries = {}
	for _, gate in ipairs(gates or {}) do
		summaries[#summaries + 1] = {
			gate_id = redact(gate.gate_id or "unknown", context),
			status = redact(gate.status or "unknown", context),
			source = redact(gate.source, context),
		}
	end
	local limited, truncated = truncate(summaries)
	return {
		gates = limited,
		status_counts = count_status(summaries),
		truncated = truncated,
	}
end

local function task_safe_next_action(status)
	if status == "blocked" or status == "unsafe" or status == "failed" then
		return "review_blocked_task_before_retry"
	end
	if status == "completed" or status == "cancelled" then
		return "inspect_completed_task_summary"
	end
	return "inspect_task_before_action"
end

local function task_is_actionable(status)
	return status ~= "completed" and status ~= "cancelled"
end

local function rollback_safe_next_action(status)
	if status == "success" or status == "available" or status == "recorded" then
		return "review_rollback_record_before_execution"
	end
	return "inspect_rollback_record_status"
end

local function import_review_safe_next_action(status)
	if status == "blocked" then
		return "review_import_blocker"
	end
	if status == "success" or status == "approved" or status == "ready" then
		return "review_import_review_before_promotion"
	end
	return "inspect_import_review_status"
end

local function promotion_safe_next_action(status)
	if status == "ready" then
		return "review_promotion_package_before_apply"
	end
	if status == "blocked" or status == "fail" then
		return "review_promotion_blocker"
	end
	return "inspect_promotion_status"
end

local function benchmark_safe_next_action(status)
	if status == "fail" then
		return "review_benchmark_failure"
	end
	return "inspect_benchmark_gate_summary"
end

local function add_operator_recommendation(recommendations, context, target_kind,
		target_id, status, safe_next_action)
	recommendations[#recommendations + 1] = {
		target_kind = redact(target_kind, context),
		target_id = redact(target_id or "unknown", context),
		status = redact(status or "unknown", context),
		safe_next_action = redact(safe_next_action, context),
		dry_run_only = true,
		will_mutate = false,
	}
end

local function summarize_operator_control(context, audit_records, promotion_packages, gates)
	local recommendations = {}
	local tasks = sorted_tasks()
	local control_tasks = {}
	for _, task in ipairs(tasks) do
		if task_is_actionable(task.status or "unknown") then
			control_tasks[#control_tasks + 1] = task
		end
	end
	if #control_tasks == 0 then
		control_tasks = tasks
	end
	for _, task in ipairs(control_tasks) do
		local status = task.status or "unknown"
		add_operator_recommendation(
			recommendations,
			context,
			"task",
			task.task_id,
			status,
			task_safe_next_action(status)
		)
	end
	for _, record in ipairs(audit_records) do
		if record.event_type == "rollback.record" then
			local status = record.status or "available"
			add_operator_recommendation(
				recommendations,
				context,
				"rollback",
				record.rollback_record_id or record.task_id or "unknown",
				status,
				rollback_safe_next_action(status)
			)
		elseif type(record.event_type) == "string" and record.event_type:sub(1, 7) == "import." then
			local status = record.status or "unknown"
			add_operator_recommendation(
				recommendations,
				context,
				"import_review",
				record.task_id or record.event_type,
				status,
				import_review_safe_next_action(status)
			)
		end
	end
	for _, package in ipairs(promotion_packages or {}) do
		local status = package.status or "unknown"
		add_operator_recommendation(
			recommendations,
			context,
			"import_promotion",
			package.package_id or "unknown",
			status,
			promotion_safe_next_action(status)
		)
	end
	for _, gate in ipairs(gates or {}) do
		local status = gate.status or "unknown"
		if status == "fail" then
			add_operator_recommendation(
				recommendations,
				context,
				"benchmark_gate",
				gate.gate_id or "unknown",
				status,
				benchmark_safe_next_action(status)
			)
		end
	end
	local limited, truncated = truncate(recommendations)
	return {
		surface_kind = "read_only_task_rollback_control",
		action_mode = "dry_run_only",
		mutation_performed = false,
		recommendations_total = #recommendations,
		summaries = limited,
		truncated = truncated,
	}
end

local function profile_hygiene()
	local smoke_enabled = core.settings:get_bool("ai_runtime.enable_smoke_command", false)
	local benchmark_enabled = core.settings:get_bool("ai_runtime.enable_demo_benchmark_command", false)
	local model_adapter_probe_enabled =
		core.settings:get_bool("ai_runtime.enable_model_adapter_probe_command", false)
	local current_dev_surfaces = {}
	if smoke_enabled then
		current_dev_surfaces[#current_dev_surfaces + 1] = "ai_runtime_smoke"
	end
	if benchmark_enabled then
		current_dev_surfaces[#current_dev_surfaces + 1] = "ai_demo_entity_benchmark"
	end
	if model_adapter_probe_enabled then
		current_dev_surfaces[#current_dev_surfaces + 1] = "ai_model_adapter_probe"
	end
	local gameid = "ai_runtime"
	if core.get_game_info then
		local ok, info = pcall(core.get_game_info)
		if ok and type(info) == "table" and type(info.id) == "string" and info.id ~= "" then
			gameid = info.id
		end
	end
	return {
		status = "pass",
		gameid = gameid,
		product_mods = { "ai_runtime_base" },
		dev_surfaces_disabled_by_default = true,
		test_fixtures_explicit_only = true,
		current_dev_surfaces_enabled = current_dev_surfaces,
		no_private_content = true,
		violations = {},
	}
end

local function package_status(package)
	if package.server_profile_hygiene.status ~= "pass" then
		return "attention"
	end
	if (package.tasks.counts.blocked or 0) > 0 or (package.tasks.counts.failed or 0) > 0 then
		return "attention"
	end
	if (package.imports.status_counts.blocked or 0) > 0 then
		return "attention"
	end
	if (package.benchmarks.status_counts.fail or 0) > 0 then
		return "attention"
	end
	return "ready"
end

local function apply_bounds(package, max_bytes)
	local function refresh_size()
		package.bounds.output_bytes = #core.write_json(package)
		return package.bounds.output_bytes
	end

	local function trim_list(list, limit)
		local truncated = {}
		for i = 1, math.min(#list, limit) do
			truncated[#truncated + 1] = list[i]
		end
		return truncated
	end

	local function trim_sections(limit)
		for _, section_name in ipairs({
				"agents",
				"tasks",
				"rollback",
				"imports",
				"benchmarks",
				"operator_control",
			}) do
			local section = package[section_name]
			if section.summaries then
				section.summaries = trim_list(section.summaries, limit)
				section.truncated = true
			end
		end
		if package.imports.promotion_summaries then
			package.imports.promotion_summaries =
				trim_list(package.imports.promotion_summaries, limit)
			package.imports.truncated = true
		end
		if package.benchmarks.gates then
			package.benchmarks.gates = trim_list(package.benchmarks.gates, limit)
			package.benchmarks.truncated = true
		end
		package.bounds.truncated = true
	end

	local function drop_verbose_fields()
		for _, task in ipairs(package.tasks.summaries or {}) do
			task.label = nil
			task.reason = nil
		end
		for _, record in ipairs(package.rollback.summaries or {}) do
			record.storage_ref = nil
		end
		for _, review in ipairs(package.imports.summaries or {}) do
			review.source = nil
		end
		for _, promotion in ipairs(package.imports.promotion_summaries or {}) do
			promotion.source = nil
		end
		for _, gate in ipairs(package.benchmarks.gates or {}) do
			gate.source = nil
		end
		package.bounds.truncated = true
	end

	package.bounds = {
		max_bytes = max_bytes,
		output_bytes = 0,
		truncated = package.agents.truncated or package.tasks.truncated
			or package.rollback.truncated or package.imports.truncated
			or package.benchmarks.truncated or package.operator_control.truncated,
	}
	if refresh_size() > max_bytes then
		trim_sections(3)
		refresh_size()
	end
	if package.bounds.output_bytes > max_bytes then
		drop_verbose_fields()
		refresh_size()
	end
	if package.bounds.output_bytes > max_bytes then
		trim_sections(0)
		refresh_size()
	end
	return package
end

function operator_status.build_package(options)
	options = options or {}
	local max_bytes = options.max_bytes or DEFAULT_MAX_BYTES
	local context = redaction_context()
	local audit_records = core.get_ai_runtime_audit({ limit = options.audit_limit or 200 })
	local package = {
		schema_version = 1,
		package_kind = "ai_native_operator_status_package",
		generated_at = options.generated_at or tostring(core.get_us_time and core.get_us_time() or 0),
		runtime_context = {
			game_profile = "ai_runtime",
			source = "live_runtime_state",
			mutation_performed = false,
		},
		server_profile_hygiene = profile_hygiene(),
		agents = summarize_agents(context),
		tasks = summarize_tasks(context),
		rollback = summarize_rollback(context, audit_records),
		imports = summarize_imports(context, audit_records, options.promotion_packages),
		benchmarks = summarize_benchmarks(context, options.benchmark_gates),
		operator_control = summarize_operator_control(
			context,
			audit_records,
			options.promotion_packages,
			options.benchmark_gates
		),
	}
	package.safety = {
		public_safe_output = true,
		redactions_applied = context.count,
		truncations_applied = context.truncations,
		no_raw_assets = true,
		no_provider_prompts = true,
		no_family_world_coordinates = true,
	}
	package.status = package_status(package)
	return apply_bounds(package, max_bytes)
end

core.build_ai_operator_status_package = operator_status.build_package

local COMMAND_VIEWS = {
	tasks = true,
	task = true,
	audit = true,
	rollback = true,
	imports = true,
}

local function view_base(options, context, view_name)
	return {
		schema_version = 1,
		package_kind = "ai_native_operator_status_view",
		view = view_name,
		generated_at = options.generated_at or tostring(core.get_us_time and core.get_us_time() or 0),
		runtime_context = {
			game_profile = "ai_runtime",
			source = "live_runtime_state",
			command = "/ai_runtime_operator_status",
			view = view_name,
			mutation_performed = false,
			world_mutation_performed = false,
		},
		safety = {
			public_safe_output = true,
			redactions_applied = context.count,
			truncations_applied = context.truncations,
			read_only = true,
			no_task_queue_mutation = true,
			no_world_mutation = true,
			no_rollback_execution = true,
			no_import_promotion_execution = true,
			no_structure_apply = true,
			no_raw_assets = true,
			no_provider_prompts = true,
			no_family_world_coordinates = true,
		},
		bounds = {
			max_bytes = options.max_bytes or DEFAULT_MAX_BYTES,
			output_bytes = 0,
			truncated = false,
		},
	}
end

local function apply_view_bounds(view, max_bytes)
	local function refresh_size()
		view.bounds.output_bytes = #core.write_json(view)
		return view.bounds.output_bytes
	end
	local function mark_truncated(section)
		if section then
			section.truncated = true
		end
		view.bounds.truncated = true
	end
	local function trim_list_field(section, key, limit)
		if section and section[key] then
			section[key] = truncate_to(section[key], limit)
			mark_truncated(section)
		end
	end
	local function drop_verbose_fields()
		for _, task in ipairs((view.tasks and view.tasks.summaries) or {}) do
			task.label = nil
			task.reason = nil
		end
		if view.task then
			view.task.label = nil
			if view.task.last_result then
				view.task.last_result.message = nil
				view.task.last_result.rollback_storage_ref = nil
			end
		end
		for _, audit in ipairs((view.audit and view.audit.summaries) or {}) do
			audit.message = nil
			audit.rollback_storage_ref = nil
		end
		for _, record in ipairs((view.rollback and view.rollback.summaries) or {}) do
			record.storage_ref = nil
		end
		for _, review in ipairs((view.imports and view.imports.summaries) or {}) do
			review.source = nil
		end
		for _, promotion in ipairs((view.imports and view.imports.promotion_summaries) or {}) do
			promotion.source = nil
		end
		view.bounds.truncated = true
	end

	view.bounds.max_bytes = max_bytes
	if refresh_size() > max_bytes then
		trim_list_field(view.tasks, "summaries", 3)
		trim_list_field(view.audit, "summaries", 3)
		trim_list_field(view.rollback, "summaries", 3)
		trim_list_field(view.imports, "summaries", 3)
		trim_list_field(view.imports, "promotion_summaries", 3)
		refresh_size()
	end
	if view.bounds.output_bytes > max_bytes then
		drop_verbose_fields()
		refresh_size()
	end
	if view.bounds.output_bytes > max_bytes then
		trim_list_field(view.tasks, "summaries", 0)
		trim_list_field(view.audit, "summaries", 0)
		trim_list_field(view.rollback, "summaries", 0)
		trim_list_field(view.imports, "summaries", 0)
		trim_list_field(view.imports, "promotion_summaries", 0)
		refresh_size()
	end
	return view
end

function operator_status.build_view(options)
	options = options or {}
	local view_name = options.view
	assert(COMMAND_VIEWS[view_name], "Unsupported operator status view")
	local max_bytes = options.max_bytes or DEFAULT_MAX_BYTES
	local limit = options.limit or SUMMARY_LIMIT
	local context = redaction_context()
	local audit_records = core.get_ai_runtime_audit({ limit = options.audit_limit or limit })
	local view = view_base(options, context, view_name)
	if view_name == "tasks" then
		view.tasks = summarize_tasks(context, limit)
		view.summary = {
			tasks_total = view.tasks.counts.total,
			status_counts = table.copy(view.tasks.counts),
			results_retained = #(view.tasks.summaries or {}),
			read_only = true,
		}
		view.status = "ready"
	elseif view_name == "task" then
		local task = core.get_ai_task(options.task_id)
		view.task = compact_task_detail(task, context) or {
			task_id = redact(options.task_id, context),
			status = "not_found",
		}
		view.summary = {
			task_found = task ~= nil,
			task_id = redact(options.task_id, context),
			read_only = true,
		}
		view.status = task and "ready" or "attention"
	elseif view_name == "audit" then
		view.audit = summarize_audit(context, audit_records)
		view.summary = {
			audit_records_total = view.audit.records_total,
			results_retained = #(view.audit.summaries or {}),
			read_only = true,
		}
		view.status = "ready"
	elseif view_name == "rollback" then
		view.rollback = summarize_rollback(context, audit_records)
		view.summary = {
			rollback_records_total = view.rollback.records_total,
			rollback_records_available = view.rollback.records_available,
			results_retained = #(view.rollback.summaries or {}),
			read_only = true,
		}
		view.status = "ready"
	elseif view_name == "imports" then
		view.imports = summarize_imports(context, audit_records, options.promotion_packages)
		view.summary = {
			import_reviews_total = view.imports.reviews_total,
			import_promotions_total = view.imports.promotions_total,
			results_retained = #(view.imports.summaries or {}),
			read_only = true,
		}
		view.status = "ready"
	end
	view.safety.redactions_applied = context.count
	view.safety.truncations_applied = context.truncations
	return apply_view_bounds(view, max_bytes)
end

core.build_ai_operator_status_view = operator_status.build_view

local function parse_command_options(param)
	local options = {}
	for token in string.gmatch(param or "", "%S+") do
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
		elseif key == "view" then
			if not COMMAND_VIEWS[value] then
				return nil, "view must be one of tasks, task, audit, rollback, imports"
			end
			options.view = value
		elseif key == "task_id" then
			if value == "" then
				return nil, "task_id must be non-empty"
			end
			options.task_id = value
		elseif key == "limit" then
			local limit = tonumber(value)
			if not limit or limit < 1 or limit > 200 then
				return nil, "limit must be between 1 and 200"
			end
			options.limit = math.floor(limit)
		else
			return nil, "unknown option '" .. key .. "'"
		end
	end
	if options.view == "task" and not options.task_id then
		return nil, "task_id is required for view=task"
	end
	return options
end

core.register_chatcommand("ai_runtime_operator_status", {
	params = "[generated_at=ISO_OR_LABEL] [max_bytes=N] [view=tasks|task|audit|rollback|imports] [task_id=ID] [limit=N]",
	description = "Return bounded public-safe AI runtime operator status or focused read-only views as JSON.",
	privs = { server = true },
	func = function(_, param)
		local options, err = parse_command_options(param)
		if not options then
			return false, err
		end
		if options.view then
			return true, core.write_json(operator_status.build_view(options))
		end
		return true, core.write_json(operator_status.build_package(options))
	end,
})
