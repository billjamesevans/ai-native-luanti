# AI-Native Luanti Agents SDK Model Adapter

This is the first-party reference sidecar for connecting the Luanti
`core.ai_model_ops.request` envelope to the OpenAI Agents SDK.

The Luanti engine remains authoritative for:

- agent identity and ownership;
- `http.llm` capability checks;
- task queues, audit, metrics, and rollback requirements;
- world mutation and import promotion gates.

The sidecar owns:

- Agents SDK orchestration through `Agent` and `Runner`;
- hosted web search through `WebSearchTool`;
- deterministic function tools through `function_tool`;
- a structured `tool_powers` manifest for readiness and release evidence;
- conversion back to the provider-neutral
  `ai_native_model_adapter_response` envelope.

## Local Smoke

Offline contract smoke, without network or credentials:

```bash
python3 tools/agents_sdk_model_adapter/main.py --smoke
python3 util/ai_native_agents_sdk_sidecar_readiness.py --mode offline-smoke
```

Live agent mode requires `openai-agents` and `OPENAI_API_KEY`:

```bash
cd tools/agents_sdk_model_adapter
uv run python main.py --host 127.0.0.1 --port 8766
curl -fsS http://127.0.0.1:8766/health
```

Managed HTTP readiness, still without provider credentials:

```bash
python3 util/ai_native_agents_sdk_sidecar_readiness.py \
  --mode managed-http \
  --port 8766 \
  --output local/benchmarks/agents-sdk-sidecar-readiness.json
```

The readiness report verifies that `tool_powers` includes function tools and
`WebSearchTool`, and that every declared power has
`direct_world_mutation = false`.

Live agent readiness, with `openai-agents` installed and `OPENAI_API_KEY`
provided by the local secret environment:

```bash
uv run --project tools/agents_sdk_model_adapter \
  python util/ai_native_agents_sdk_sidecar_readiness.py \
  --mode managed-http \
  --port 8766 \
  --require-live-agent \
  --output local/benchmarks/agents-sdk-sidecar-live-readiness.json
```

This stricter probe must show `agentic_execution = true`, hosted web lookup
availability, bounded public-safe response metadata, and
`world_mutation_authority = luanti`. It does not write secrets to the report.

Adapter endpoint:

```text
POST /v1/model-adapter
```

The request and response shapes are the same provider-neutral envelopes
documented under `doc/ai-native-runtime/model-adapter-contract.md`.

Luanti bridge:

```text
ai_runtime.enable_agents_sdk_adapter = true
/ai_agents_sdk_adapter_probe
```

The Luanti bridge accepts loopback endpoints only by default and keeps world
mutation in the engine task/approval/rollback path.
