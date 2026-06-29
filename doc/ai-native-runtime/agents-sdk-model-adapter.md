# Agents SDK Model Adapter

Status: first reference sidecar for issue #254.

## Decision

The first-party AI provider path for this fork should use the OpenAI Agents SDK,
not a plain chat-completion wrapper. The runtime still exposes a
provider-neutral model adapter contract, but the maintained reference adapter is
an Agents SDK sidecar with real agent orchestration, hosted web search, and
deterministic tools.

The sidecar lives outside the engine process:

```text
Luanti Lua runtime -> core.ai_model_ops.request -> local model adapter sidecar
                   -> OpenAI Agents SDK Agent/Runner/WebSearchTool/function_tool
                   -> ai_native_model_adapter_response
```

This keeps the engine fork open, buildable, and provider-neutral while allowing
servers that opt in to run real agents with web/tool powers.

## Boundary

The engine owns:

- `http.llm` capability checks before any model call.
- Player ownership, task ids, and bounded request envelopes.
- Audit and metrics for model requests and adapter outcomes.
- Rejection of private payloads, credentials, raw provider requests/responses,
  raw media payloads, and asset payloads.
- World mutation, rollback, import promotion, and task-control execution.

The Agents SDK sidecar owns:

- `Agent` instructions and orchestration.
- `Runner` execution.
- `WebSearchTool` for current public web lookup when needed.
- `function_tool` deterministic tools for runtime-capability summaries and
  world-action classification.
- Optional future handoffs or sandbox agents, only after the engine has a
  matching capability and approval contract.

The sidecar must not execute world mutations directly. It returns a bounded
`ai_native_model_adapter_response`; Luanti remains the only writer.

## Reference Implementation

Reference path:

```text
tools/agents_sdk_model_adapter/
```

Luanti-side bridge:

```text
builtin/game/ai_agents_sdk_adapter_plugin.lua
```

Important files:

- `agent.py`: Agents SDK adapter, tools, offline smoke path, and response
  envelope conversion.
- `main.py`: HTTP service with `GET /health` and `POST /v1/model-adapter`.
- `pyproject.toml`: declares `openai-agents`.

Offline smoke:

```bash
python3 tools/agents_sdk_model_adapter/main.py --smoke
python3 util/ai_native_agents_sdk_sidecar_readiness.py --mode offline-smoke
```

Live sidecar:

```bash
cd tools/agents_sdk_model_adapter
uv run python main.py --host 127.0.0.1 --port 8766
```

Live mode requires `OPENAI_API_KEY`. The key belongs in server-local secret
configuration, never in the repository, runtime manifests, or public evidence.

Managed readiness probe, without provider credentials:

```bash
python3 util/ai_native_agents_sdk_sidecar_readiness.py \
  --mode managed-http \
  --port 8766 \
  --output local/benchmarks/agents-sdk-sidecar-readiness.json
```

The readiness probe starts the sidecar on loopback, removes `OPENAI_API_KEY`
from the child process, checks `GET /health`, posts a sample
`ai_native_model_adapter_request` to `POST /v1/model-adapter`, and emits a
bounded JSON report. It is intended for local and Pi release evidence before
enabling live provider credentials.

## Luanti Adapter

The Lua adapter is disabled by default and is loaded only when:

```text
ai_runtime.enable_agents_sdk_adapter = true
```

Default endpoint:

```text
http://127.0.0.1:8766/v1/model-adapter
```

Probe command:

```text
/ai_agents_sdk_adapter_probe
```

The adapter installs itself into `core.ai_agent_plugin.set_model_adapter` when
enabled, so unknown `/nova` prompts can flow through the Agents SDK sidecar.
The Lua side only accepts loopback endpoints by default. The sidecar can perform
hosted web search and function-tool reasoning, but it still returns a bounded
`ai_native_model_adapter_response`; the engine decides whether any proposed
world action becomes a preview, approval, rollback-backed task, or refusal.

## Tool Policy

Initial tools are deliberately read-only:

- `summarize_runtime_capabilities`: tells the agent which runtime gates have
  already been granted.
- `classify_world_action`: labels planned node writes as requiring preview,
  approval, and rollback before the engine may execute them.
- `WebSearchTool`: lets the agent look up current public information when the
  prompt genuinely needs it.

Future powers must follow the same pattern:

- define a capability name first;
- add a public-safe envelope and verifier;
- require explicit player or operator approval for mutation;
- prove the behavior in disposable worlds before Pi deployment.

## Verification

Run:

```bash
python3 util/ai_native_agents_sdk_bridge_contract.py
python3 util/ai_native_agents_sdk_sidecar_readiness.py --mode managed-http --port 8766
python3 tools/agents_sdk_model_adapter/main.py --smoke
bin/luantiserver --run-unittests --test-module TestAIRuntime
```

The contract verifier checks that the reference sidecar imports and wires the
Agents SDK primitives, exposes the model-adapter HTTP endpoint, keeps the
runtime as the mutation authority, gates the Lua bridge behind
`ai_runtime.enable_agents_sdk_adapter`, and produces a safe offline response
envelope without credentials or network access.
