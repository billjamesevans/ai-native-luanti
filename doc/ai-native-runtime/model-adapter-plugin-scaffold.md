# Model Adapter Plugin Scaffold

Status: optional dev/test scaffold for provider-neutral adapter wiring.

`builtin/game/ai_model_adapter_plugin.lua` proves that an optional plugin can
call `core.ai_model_ops.request` through the public provider-neutral envelope
without adding model credentials, provider SDKs, hostnames, or network defaults
to the engine fork.

The module is disabled by default. It is loaded only when:

```text
ai_runtime.enable_model_adapter_probe_command = true
```

When enabled, it registers:

```text
/ai_model_adapter_probe
```

The command requires `server` privilege and returns bounded JSON. The probe uses
a mock adapter, captures the request envelope seen by that adapter, and reports
the sanitized response shape plus model-adapter metric deltas.

## Runtime Contract

The scaffold intentionally reuses the runtime entrypoint:

```text
core.ai_model_ops.request
```

The mock adapter receives:

- `request_kind = "ai_native_model_adapter_request"`
- `adapter_contract = "provider_neutral_v1"`
- `public_prompt`
- bounded `context`
- safety flags requiring public-safe request handling, no retained private
  input, no provider credentials, and no raw media payloads

The mock adapter returns:

- `response_kind = "ai_native_model_adapter_response"`
- `adapter_contract = "provider_neutral_v1"`
- `adapter_name = "mock-provider-neutral"`
- a bounded public message and small structured response

The unsafe-payload probe deliberately returns a raw-provider field internally so
the runtime can prove that such payloads are rejected with
`adapter_payload_rejected`. The public report does not expose that payload.

## Provider Boundary

Real provider credentials belong in an operator-owned deployment layer outside
this public fork: for example, a private server plugin, local secret store, or
deployment-specific environment. A provider plugin should adapt its vendor call
into the same request and response shape documented in
[`model-adapter-contract.md`](model-adapter-contract.md).

The engine fork should continue to ship without:

- default model network calls
- provider-specific SDK code
- checked-in credentials
- retained private prompts
- raw provider request or response bodies
- copied media or proprietary asset payloads

This keeps the fork reusable and safe while still giving AI-native agents a
stable model-adapter seam.
