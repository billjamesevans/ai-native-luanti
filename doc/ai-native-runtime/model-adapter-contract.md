# Model Adapter Contract

Status: provider-neutral alpha contract for model-backed agent replies.

## Purpose

The fork does not ship a default network provider, API key flow, or hosted model
client. The runtime does define the safe boundary that optional provider plugins
must use. That boundary keeps model calls capability-gated, bounded,
public-safe by default, and observable through existing model audit and metrics.

Runtime entrypoints: `core.ai_model_ops.request` and
`core.ai_model_ops.request_async`

Agent plugin entrypoints: `core.ai_agent_plugin.set_model_adapter` and
`core.ai_agent_plugin.set_model_adapter_async`

Optional scaffold: [`model-adapter-plugin-scaffold.md`](model-adapter-plugin-scaffold.md)
documents the disabled-by-default mock probe used to verify this contract
without provider credentials or network calls.

First-party provider path:
[`agents-sdk-model-adapter.md`](agents-sdk-model-adapter.md) defines the
reference OpenAI Agents SDK sidecar under `tools/agents_sdk_model_adapter`.
That bridge uses `Agent`, `Runner`, `WebSearchTool`, and `function_tool` while
keeping this runtime contract provider-neutral.

Luanti-side opt-in:
`builtin/game/ai_agents_sdk_adapter_plugin.lua` is loaded only when
`ai_runtime.enable_agents_sdk_adapter = true`. It posts this request envelope to
the loopback sidecar endpoint and installs the resulting adapters through
`core.ai_agent_plugin.set_model_adapter` and, when available,
`core.ai_agent_plugin.set_model_adapter_async`.

## Request Envelope

Adapters receive a table matching
`schemas/model-adapter-request.schema.json`.

Required fields:

- `schema_version = 1`
- `request_kind = "ai_native_model_adapter_request"`
- `adapter_contract = "provider_neutral_v1"`
- `agent_id`
- `owner`
- `public_prompt`
- `context`
- `safety`
- `bounds`

The legacy raw `prompt` field is intentionally not included. Adapters use
`public_prompt`. The runtime may receive a private prompt for audit-policy
decisions, but private prompt payloads are not retained or forwarded through the
adapter request envelope.

The request safety block must state:

- `public_safe_request = true`
- `private_input_retained = false`
- `no_provider_credentials = true`
- `no_raw_media_payloads = true`

The default response bound is `bounds.max_response_bytes = 4000`. A caller may
lower or raise it within the runtime clamp, but adapters should treat it as a
hard public reply budget.

## Response Envelope

Adapters return a table matching
`schemas/model-adapter-response.schema.json`.

Required fields:

- `schema_version = 1`
- `response_kind = "ai_native_model_adapter_response"`
- `ok`
- `message`
- `adapter_name`

Optional fields:

- `reason`
- `elapsed_us`
- `timeout`
- `response`

The first-party Agents SDK sidecar places a public `tool_powers` manifest inside
`response`. This manifest describes agent powers such as `function_tool` and
`WebSearchTool`, but it is not a permission grant. Every listed power must state
`direct_world_mutation = false`; Luanti remains the only world writer through
capability, preview, approval, task, audit, and rollback APIs.

For build-planning responses, first-party adapters should also include a bounded
`tool_trace`, `tool_decision_source`, and `tool_decisions.build_option` object.
`tool_decision_source = agents_sdk_function_tool` means the executable selection
came from an SDK function-tool call. Fallback labels such as
`offline_adapter_fallback` or `adapter_fallback_after_agent_no_tool` are allowed
but should be treated as eval/improvement signals, not proof of healthy live
agent behavior. Luanti may honor `selected_option_id` only when it matches one
of the bounded executable candidates already supplied by the engine.

The runtime rejects unsafe/raw response fields with
`adapter_payload_rejected`. Optional provider plugins should keep raw provider
requests, provider responses, credentials, headers, and private payloads in
their own private logs if needed; those fields do not cross into the fork
runtime contract.

## Safety Rules

- Capability `http.llm` is required before an adapter is called.
- Missing adapters return `model_adapter_unavailable`.
- Adapter errors return `adapter_error`.
- Unsafe adapter result payloads return `adapter_payload_rejected`.
- The runtime records `model.request` before the adapter call.
- The runtime records `model.adapter` with success, failure, or timeout.
- Private payload retention remains disabled unless an explicit operator-only
  audit policy changes it.

`core.ai_model_ops.request_async(prompt, options, callback)` uses the same
envelope, safety checks, normalization, metrics, and audit records as the sync
entrypoint. The async adapter receives `(request, done)` and must call `done`
with a normal model-adapter response. The first-party `/nova` fallback records a
queued trace immediately and then updates that same trace when the callback
returns.

## Example

See:

- `examples/model-adapter-request.example.json`
- `examples/model-adapter-response.example.json`

Verify the package with:

```bash
python3 util/ai_native_model_adapter_contract.py
python3 util/ai_native_agents_sdk_bridge_contract.py
```
