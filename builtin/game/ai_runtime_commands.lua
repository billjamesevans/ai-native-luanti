core.register_chatcommand("ai_runtime", {
	params = "",
	description = "Show AI runtime queue and safety metrics.",
	privs = { server = true },
	func = function()
		return true, core.format_ai_runtime_metrics()
	end,
})
