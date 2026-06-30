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
- reviewed prompt-memory lookup through an optional case pack;
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

For build-planning requests, live responses should include
`tool_decision_source = agents_sdk_function_tool` plus a bounded `tool_trace`.
If the model does not call the required tools, the adapter labels the executable
choice as `adapter_fallback_after_agent_no_tool` so bad agent behavior is visible
in logs and eval queues.

Reviewed prompt-eval cases can be mounted as runtime memory:

```bash
export AI_NATIVE_AGENT_CASE_PACK_PATH=local/benchmarks/ai-agent-prompt-eval-case-pack.json
```

That file must be an `ai_native_agent_prompt_eval_case_pack`. The sidecar only
uses it through the read-only `recall_build_prompt_memory` tool; it never mutates
world state or bypasses Luanti approval/rollback gates.

Adapter endpoint:

```text
POST /v1/model-adapter
```

The request and response shapes are the same provider-neutral envelopes
documented under `doc/ai-native-runtime/model-adapter-contract.md`.

Luanti bridge:

```text
ai_runtime.enable_agents_sdk_adapter = true
ai_runtime.agents_sdk_adapter_timeout = 60
secure.http_mods = ai_runtime_agents_sdk_bridge
/ai_agents_sdk_adapter_probe
```

The Luanti bridge accepts loopback endpoints only by default and keeps world
mutation in the engine task/approval/rollback path.
