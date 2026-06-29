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
- conversion back to the provider-neutral
  `ai_native_model_adapter_response` envelope.

## Local Smoke

Offline contract smoke, without network or credentials:

```bash
python3 tools/agents_sdk_model_adapter/main.py --smoke
```

Live agent mode requires `openai-agents` and `OPENAI_API_KEY`:

```bash
cd tools/agents_sdk_model_adapter
uv run python main.py --host 127.0.0.1 --port 8766
curl -fsS http://127.0.0.1:8766/health
```

Adapter endpoint:

```text
POST /v1/model-adapter
```

The request and response shapes are the same provider-neutral envelopes
documented under `doc/ai-native-runtime/model-adapter-contract.md`.
