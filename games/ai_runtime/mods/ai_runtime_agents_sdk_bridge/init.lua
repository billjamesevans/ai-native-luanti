local bridge = core.ai_agents_sdk_adapter_plugin

if bridge and bridge.configure and core.request_http_api then
	bridge.configure({
		http_api = core.request_http_api(),
	})
end
