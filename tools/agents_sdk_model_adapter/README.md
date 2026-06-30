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
- bounded generated build-option proposals that Luanti validates before any
  preview or task;
- bounded build-action workflow plans that hand the selected option back to
  Luanti for preview, approval, rollback, task execution, and improvement
  evidence;
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
  --require-build-planning-tools \
  --output local/benchmarks/agents-sdk-sidecar-live-readiness.json
```

This stricter probe must show `agentic_execution = true`, hosted web lookup
availability, bounded public-safe response metadata,
`required_tool_calls_satisfied = true` for the build-planning probe, and
`world_mutation_authority = luanti`. It does not write secrets to the report.

For build-planning requests, live responses should include a healthy
tool-contract source (`agents_sdk_function_tool`,
`agents_sdk_repair_function_tool`, or `local_agent_tool_contract_fast_path`)
plus a bounded `tool_trace` containing `recall_build_prompt_memory`,
`select_build_option`, and `plan_build_actions`. The local fast path is only for
bounded build-planning requests after the live SDK path or repair path failed;
it keeps the game responsive while preserving explicit evidence that the model
path needed recovery. The action-plan tool is read-only; it records the intended
Luanti workflow and confirms that the engine, not the sidecar, owns preview,
approval, rollback, task execution, and improvement evidence.
For open-ended build requests, the `propose_build_option` function tool may
return a generated option such as a tower wall, bridge platform, path platform,
or shelter floor. That proposal is still read-only: Luanti validates the kind,
material, dimensions, and write budget before creating a pending preview.
Healthy live generated-option decisions must show `propose_build_option` in
`tool_trace`; otherwise the adapter marks the response as
`adapter_fallback_after_agent_missing_required_tool` so the run is treated as
improvement evidence rather than a healthy agent action.
If the model does not call the required tools, the adapter labels the executable
choice as `adapter_fallback_after_agent_missing_required_tool`, records
`missing_required_tool_calls`, and sets `required_tool_calls_satisfied = false`
so bad agent behavior is visible in logs and eval queues. If the model returns no
tool decision at all, the source is `adapter_fallback_after_agent_no_tool`.
Exact player constraints are also enforced by the tool contract: prompts such as
`build a fire`, `build me a fire and only a fire`, and `build a wall of tnt`
must select the matching executable candidate. If a live agent selects a generic
platform or other mismatch, the sidecar marks the run as
`adapter_fallback_after_agent_violated_player_request_constraints` and returns
the constrained executable option while retaining the bad tool trace for review.
The eval queue treats missing required tool calls as high-priority
adapter-contract regressions with `ready_for_adapter_contract_eval = true`; they
are not silently downgraded to generic manual review.

Reviewed prompt-eval cases can be mounted as runtime memory:

```bash
export AI_NATIVE_AGENT_CASE_PACK_PATH=local/benchmarks/ai-agent-prompt-eval-case-pack.json
```

That file must be an `ai_native_agent_prompt_eval_case_pack`. The sidecar only
uses it through the read-only `recall_build_prompt_memory` tool; it never mutates
world state or bypasses Luanti approval/rollback gates.

Case packs record whether each memory case is merely replayable or
`default_gate_eligible`. Default-gate eligibility requires repeated trusted
evidence with satisfied required-tool calls; single observations and operator
label overlays stay review-gated even though the sidecar can still use them as
read-only prompt memory.

Refresh candidate queues and mounted prompt memory from runtime logs with:

```bash
python3 util/ai_native_agent_memory_refresh.py \
  --agents-sdk-log local/logs/agents-sdk-model-adapter.jsonl \
  --action-log local/logs/luanti-debug.log \
  --from-operator-feedback \
  --operator-labels local/benchmarks/ai-agent-operator-labels.json \
  --candidate-queue-output local/benchmarks/ai-agent-eval-candidate-queue.json \
  --case-pack-output local/benchmarks/ai-agent-prompt-eval-case-pack.json \
  --review-output local/benchmarks/ai-agent-review-queue.json
```

For build-planning logs, `context.player_request` becomes the reviewed memory
prompt so future agent tool calls can match the exact player command.
Unknown prompts stay in manual review until a maintainer supplies a public-safe
`ai_native_agent_eval_operator_labels` file with a replayable build-output
expectation.
The optional review queue is the project-manager view of the same loop: it
summarizes manual-review candidates, active adapter-contract regressions,
resolved failures, verified live-probe coverage, and the next action to take.
It is bounded and public-safe, and it does not include provider prompts,
credentials, raw assets, or family-world coordinates.

Inspect an existing queue and case pack with:

```bash
python3 util/ai_native_agent_review_queue.py \
  --candidate-queue local/benchmarks/ai-agent-eval-candidate-queue.json \
  --case-pack local/benchmarks/ai-agent-prompt-eval-case-pack.json \
  --output local/benchmarks/ai-agent-review-queue.json
```

After the review queue is refreshed, build one pass/attention/fail quality gate
artifact for the agent loop:

```bash
python3 util/ai_native_agent_prompt_eval_live_probe.py \
  --server-bin bin/luantiserver \
  --output local/benchmarks/ai-agent-prompt-eval-live-latest.json \
  --adapter-endpoint http://127.0.0.1:8766/v1/model-adapter \
  --generated-at "$(date -u +%Y-%m-%dT%H:%M:%SZ)"

python3 util/ai_native_agent_adapter_contract_eval.py \
  --candidate-queue local/benchmarks/ai-agent-eval-candidate-queue.json \
  --output local/benchmarks/ai-agent-adapter-contract-eval.json \
  --endpoint http://127.0.0.1:8766/v1/model-adapter

python3 util/ai_native_compat_import_staging_pilot.py \
  --root . \
  --server-bin bin/luantiserver \
  --output local/benchmarks/ai-runtime-compat-import-staging-pilot-result.json

python3 util/ai_native_agent_quality_gate.py \
  --candidate-queue local/benchmarks/ai-agent-eval-candidate-queue.json \
  --case-pack local/benchmarks/ai-agent-prompt-eval-case-pack.json \
  --review-queue local/benchmarks/ai-agent-review-queue.json \
  --adapter-contract-eval local/benchmarks/ai-agent-adapter-contract-eval.json \
  --live-prompt-eval local/benchmarks/ai-agent-prompt-eval-live-latest.json \
  --compat-import-staging-pilot local/benchmarks/ai-runtime-compat-import-staging-pilot-result.json \
  --output local/benchmarks/ai-agent-quality-gate.json
```

The quality gate is intentionally artifact-only: it does not mutate the world,
does not include provider prompts or credentials, and keeps unresolved review
items in the `attention` list without making them deploy-blocking when the core
execution gates pass. Core artifact readiness, missing adapter-contract replay,
adapter-contract replay failures, a failed latest live prompt eval, or a failed
compatibility staging pilot remain deploy-blocking. When supplied, the
compatibility staging pilot proves dry-run import planning, bounded
disposable-world apply, rollback, and refusal gates without touching the family
server or private assets.
In `agents_sdk_sidecar` mode, the live prompt eval must also retain untruncated
case evidence showing that each build case used an accepted agent tool-contract
source, satisfied `recall_build_prompt_memory`, `select_build_option`, and
`plan_build_actions`, and left world mutation authority with Luanti.

For a reviewed correction where the expected build output is known, create the
candidate queue, label artifact, and prompt-memory case pack together:

```bash
python3 util/ai_native_agent_feedback_packet.py \
  --agents-sdk-log local/logs/agents-sdk-model-adapter.jsonl \
  --action-log local/logs/luanti-debug.log \
  --prompt "build a bridge" \
  --case-hint stone_bridge_platform \
  --build-kind platform \
  --build-material-name stone \
  --planned-node-writes 12 \
  --route agentic_build_planner \
  --candidate-queue-output local/benchmarks/ai-agent-eval-candidate-queue.json \
  --operator-label-output local/benchmarks/ai-agent-operator-labels.json \
  --case-pack-output local/benchmarks/ai-agent-prompt-eval-case-pack.json
```

If the correction was recorded in-game with `/ai_agent_feedback`, consume the
server-side `ai_agent_operator_feedback` event instead of repeating the prompt
and expected fields on the command line:

```bash
python3 util/ai_native_agent_feedback_packet.py \
  --agents-sdk-log local/logs/agents-sdk-model-adapter.jsonl \
  --action-log local/logs/luanti-debug.log \
  --from-operator-feedback \
  --candidate-queue-output local/benchmarks/ai-agent-eval-candidate-queue.json \
  --operator-label-output local/benchmarks/ai-agent-operator-labels.json \
  --case-pack-output local/benchmarks/ai-agent-prompt-eval-case-pack.json
```

Replay adapter-contract failures against the loopback sidecar with:

```bash
python3 util/ai_native_agent_adapter_contract_eval.py \
  --candidate-queue local/benchmarks/ai-agent-eval-candidate-queue.json \
  --output local/benchmarks/ai-agent-adapter-contract-eval.json \
  --endpoint http://127.0.0.1:8766/v1/model-adapter
```

The runner selects `ready_for_adapter_contract_eval` cases and fails runs that
drop required Agents SDK function tools or fall back to a non-agentic build
decision source.

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
