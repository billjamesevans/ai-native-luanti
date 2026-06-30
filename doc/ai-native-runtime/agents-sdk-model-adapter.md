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
- `Runner` execution. When `Runner.run_streamed` is available, the sidecar
  streams the run and returns as soon as the required build-planning tools have
  produced a ready Luanti action plan; it cancels the remaining stream instead
  of waiting for final prose.
- `WebSearchTool` for current public web lookup when needed.
- `function_tool` deterministic tools for runtime-capability summaries,
  world-action classification, reviewed prompt-memory lookup, and build-option
  recommendations.
- Optional future handoffs or sandbox agents, only after the engine has a
  matching capability and approval contract.

The sidecar must not execute world mutations directly. It returns a bounded
`ai_native_model_adapter_response`; Luanti remains the only writer.

The default player-facing build policy is preview then approval. Test worlds can
opt in to `ai_runtime.auto_apply_build_approvals = true`; this only skips the
second player approval prompt after Luanti has validated the selected build
plan. The mutation still runs as a normal rollback-backed engine task owned by
Luanti, and the reply records `auto_applied_approval = true`.

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
  envelope conversion. When `AI_NATIVE_AGENT_LOG_PATH` is set, it appends
  bounded public-safe JSONL request/response entries for post-incident review.
  When `AI_NATIVE_AGENT_CASE_PACK_PATH` points at a reviewed
  `ai_native_agent_prompt_eval_case_pack`, the sidecar exposes those cases to the
  agent through a read-only prompt-memory tool. For open-ended build requests,
  the sidecar can also return a read-only generated build option through
  `propose_build_option`; Luanti must validate its kind, material, dimensions,
  and planned writes before it can become a pending preview.
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
Set `AI_NATIVE_AGENT_LOG_PATH=/path/to/agents-sdk-model-adapter.jsonl` to retain
public-safe sidecar request/response logs. The log records the public prompt,
safe context, status, reason, elapsed time, and tool metadata; it drops private
prompt fields, provider raw payloads, credentials, headers, and asset payloads.

## Agent Improvement Loop

The sidecar log is an input to the eval backlog, not just a debug file. After a
bad or surprising Nova interaction, pair the sidecar JSONL with the Luanti
action/debug log, and optionally include product-side Nova sidecar request logs
that already contain public-safe prompt contracts, corrections, actions, and
tool traces:

```bash
python3 util/ai_native_agent_eval_queue.py \
  --agents-sdk-log local/logs/agents-sdk-model-adapter.jsonl \
  --nova-agent-log local/logs/nova-agent-requests.jsonl \
  --action-log local/logs/luanti-debug.log \
  --verified-live-probe local/logs/live-probes \
  --output local/benchmarks/ai-agent-eval-candidate-queue.json \
  --generated-at 2026-06-30T00:00:00Z
```

The queue is public-safe and review-first. It skips entries containing private
fields, credentials, raw provider payloads, private prompts, asset payloads, or
private world references. Known regressions such as `build me a fire and only a
fire` and `build a wall of tnt` are labeled with ready prompt-eval assertions;
unknown prompts stay in `needs_operator_label` until a maintainer records the
expected behavior. Maintainers record that behavior with a public-safe
`ai_native_agent_eval_operator_labels` file passed as `--operator-labels`; a
label can match by exact candidate id or public prompt and can only promote
build-output expectations that the runtime prompt-eval runner can replay.
Adapter traces that miss required SDK tools are also marked
`ready_for_adapter_contract_eval = true` and counted under
`adapter_contract_failures` while active, even when the expected build-output
behavior still needs an operator label. Later passing evidence for the same
public prompt keeps the failed candidate in the queue but marks it resolved;
operators can distinguish `adapter_contract_failures_active`,
`adapter_contract_failures_total`, and `adapter_contract_failures_resolved` in
the refresh summary.

Passing Nova auto-apply live probe artifacts can also feed the queue through
`--verified-live-probe`. Those cases are treated as reviewed evidence only when
the disposable-world probe proves the SDK tool trace, selected candidate, ready
Luanti action plan, auto-apply path, rollback record, and no-extra-node checks.

Use the artifact builder for reviewed corrections instead of hand-writing label
JSON:

```text
/ai_agent_feedback last; case=stone_bridge_platform; build_kind=platform; material=stone; planned_writes=12; route=agentic_build_planner
```

When the correction starts from the server-side feedback command, consume the
logged `ai_agent_operator_feedback` event directly:

```bash
python3 util/ai_native_agent_feedback_packet.py \
  --agents-sdk-log local/logs/agents-sdk-model-adapter.jsonl \
  --action-log local/logs/luanti-debug.log \
  --from-operator-feedback \
  --candidate-queue-output local/benchmarks/ai-agent-eval-candidate-queue.json \
  --operator-label-output local/benchmarks/ai-agent-operator-labels.json \
  --case-pack-output local/benchmarks/ai-agent-prompt-eval-case-pack.json \
  --generated-at 2026-06-30T00:00:00Z
```

```bash
python3 util/ai_native_agent_operator_label.py \
  --candidate-queue local/benchmarks/ai-agent-eval-candidate-queue.json \
  --prompt "build a bridge" \
  --case-hint stone_bridge_platform \
  --build-kind platform \
  --build-material-name stone \
  --planned-node-writes 12 \
  --route agentic_build_planner \
  --output local/benchmarks/ai-agent-operator-labels.json \
  --generated-at 2026-06-30T00:00:00Z
```

Ready candidates can then become an `ai_native_agent_prompt_eval_case_pack`:

```bash
python3 util/ai_native_agent_eval_promote.py \
  --candidate-queue local/benchmarks/ai-agent-eval-candidate-queue.json \
  --output local/benchmarks/ai-agent-prompt-eval-case-pack.json \
  --generated-at 2026-06-30T00:00:00Z
```

The routine refresh command writes both artifacts together and is the preferred
operator path for sidecar memory. Include `--from-operator-feedback` so
server-side `/ai_agent_feedback` reviews in the action log are harvested during
the normal refresh:

```bash
python3 util/ai_native_agent_memory_refresh.py \
  --agents-sdk-log local/logs/agents-sdk-model-adapter.jsonl \
  --nova-agent-log local/logs/nova-agent-requests.jsonl \
  --action-log local/logs/luanti-debug.log \
  --verified-live-probe local/logs/live-probes \
  --from-operator-feedback \
  --operator-labels local/benchmarks/ai-agent-operator-labels.json \
  --candidate-queue-output local/benchmarks/ai-agent-eval-candidate-queue.json \
  --case-pack-output local/benchmarks/ai-agent-prompt-eval-case-pack.json \
  --generated-at 2026-06-30T00:00:00Z
```

The promotion artifact separates replayable memory from default-gate memory.
Ready cases are safe to replay and mount as read-only `recall_build_prompt_memory`
input, but they remain review-gated unless repeated trusted evidence proves the
same behavior. By default, `ai_native_agent_eval_promote.py` and
`ai_native_agent_memory_refresh.py` require two independent trusted source kinds
with passing required-tool contracts before a case is marked
`default_gate_eligible`; the threshold is explicit as
`--auto-default-gate-min-sources`.

Adapter-contract regressions can be replayed against the live loopback sidecar:

```bash
python3 util/ai_native_agent_adapter_contract_eval.py \
  --candidate-queue local/benchmarks/ai-agent-eval-candidate-queue.json \
  --output local/benchmarks/ai-agent-adapter-contract-eval.json \
  --endpoint http://127.0.0.1:8766/v1/model-adapter \
  --generated-at 2026-06-30T00:00:00Z
```

The replay runner consumes only `ready_for_adapter_contract_eval` candidates and
grades the real adapter response for required tool calls, empty
`missing_required_tool_calls`, `required_tool_calls_satisfied = true`,
an accepted tool-contract source (`agents_sdk_function_tool`,
`agents_sdk_repair_function_tool`, or `local_agent_tool_contract_fast_path`),
and Luanti-only world mutation authority.

When a sidecar log includes `context.player_request`, that exact player request
is promoted as the case prompt. This keeps reviewed memory aligned to the command
the player actually typed instead of the adapter's larger wrapper prompt.

The case pack is consumed by `custom_cases` in
`core.ai_agent_plugin.run_prompt_eval`, and can also be mounted into the sidecar
with:

```bash
AI_NATIVE_AGENT_CASE_PACK_PATH=local/benchmarks/ai-agent-prompt-eval-case-pack.json
```

Mounted cases become read-only prompt memory through the
`recall_build_prompt_memory` function tool. They do not directly mutate the
world and do not bypass Luanti preview, approval, rollback, or task gates. This
is the first improvement loop: bad live requests create logs, logs become
candidate queues, reviewed candidates become eval cases, and those reviewed
cases can influence future agent planning while staying public-safe.

For build-planning requests, the sidecar response also includes a structured
read-only tool decision:

```json
{
  "response": {
    "selected_option_id": "fire",
    "tool_decision_source": "agents_sdk_function_tool",
    "required_tool_calls": [
      "recall_build_prompt_memory",
      "select_build_option",
      "plan_build_actions",
      "propose_build_option"
    ],
    "missing_required_tool_calls": [],
    "required_tool_calls_satisfied": true,
    "tool_trace": [
      {
        "tool_name": "recall_build_prompt_memory"
      },
      {
        "tool_name": "propose_build_option"
      },
      {
        "tool_name": "select_build_option"
      },
      {
        "tool_name": "plan_build_actions"
      }
    ],
    "build_action_plan": {
      "status": "ready",
      "selected_option_id": "generated_tower_wall",
      "plan_kind": "luanti_build_action_plan_v1",
      "step_count": 4,
      "direct_world_mutation": false,
      "world_mutation_authority": "luanti"
    },
    "tool_decisions": {
      "build_option": {
        "selected_option_id": "generated_tower_wall",
        "decision_source": "agent_selected_generated_build_option",
        "generated_option_status": "ready",
        "generated_option": {
          "option_id": "generated_tower_wall",
          "build_kind": "wall",
          "build_width": 3,
          "build_height": 4,
          "build_material_name": "stone",
          "planned_node_writes": 12
        },
        "direct_world_mutation": false
      },
      "build_action_plan": {
        "status": "ready",
        "selected_option_id": "generated_tower_wall",
        "plan_kind": "luanti_build_action_plan_v1",
        "step_count": 4,
        "direct_world_mutation": false,
        "world_mutation_authority": "luanti"
      }
    }
  }
}
```

The Lua planner honors a selected fixed option only when it matches one of the
bounded executable candidates supplied in the request. It honors a generated
option only after the Luanti-side generated-option validator accepts the
proposed kind, material, dimensions, and write budget and can produce a normal
rollback-backed preview plan from it. The model's prose is kept as player
guidance; the structured `tool_decisions` field is the execution contract that
can change the pending preview plan.
For healthy live agent evidence, generated-option decisions require an explicit
`propose_build_option` entry in `tool_trace`. Fixed options such as strict fire
or TNT wall still require `recall_build_prompt_memory` and
`select_build_option`, and every healthy build-planning response requires
`plan_build_actions` so the sidecar records the Luanti preview, approval,
rollback, task, and improvement-evidence workflow. Generated options add
`propose_build_option` to `required_tool_calls`. If a live run selects a
generated option without that tool call, the adapter labels the response as
`adapter_fallback_after_agent_missing_required_tool` and records
`missing_required_tool_calls = ["propose_build_option"]`.
In live mode the adapter prefers streamed Agents SDK execution. Once
`recall_build_prompt_memory`, `select_build_option`, and `plan_build_actions`
have yielded a valid build decision and ready action plan, the sidecar cancels
the remaining stream and returns that tool output as the execution contract.
The model can still reason and use web/tool powers, but late prose is not
allowed to override the structured plan.
If a live agent does not call the required function tools, the adapter still
returns a bounded fallback decision but labels it with
`tool_decision_source = adapter_fallback_after_agent_missing_required_tool`,
sets `required_tool_calls_satisfied = false`, and records
`missing_required_tool_calls` so the run can be promoted into evals instead of
being mistaken for healthy agent behavior. If no tool decision is returned at
all, the source is `adapter_fallback_after_agent_no_tool`.
The same review loop now treats exact build requests as constraints. `build a
fire`, `build me a fire and only a fire`, and `build a wall of tnt` must resolve
to their matching executable candidates when those candidates are available. A
live agent can still reason and call tools, but a mismatched choice is labeled
`adapter_fallback_after_agent_violated_player_request_constraints`; the adapter
returns the constrained option while preserving the rejected tool trace in the
request/response log.

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
bounded JSON report. The report verifies `tool_powers` and confirms every
declared tool has `direct_world_mutation = false`. It is intended for local and
Pi release evidence before enabling live provider credentials.

Live-agent readiness is a separate, stricter gate for deployments that have the
Agents SDK dependency and a server-local `OPENAI_API_KEY` configured outside the
repository:

```bash
uv run --project tools/agents_sdk_model_adapter \
  python util/ai_native_agents_sdk_sidecar_readiness.py \
  --mode managed-http \
  --port 8766 \
  --require-live-agent \
  --require-build-planning-tools \
  --output local/benchmarks/agents-sdk-sidecar-live-readiness.json
```

That mode keeps the endpoint loopback-only, does not print or retain the key,
and requires provider-backed `agentic_execution = true`,
`web_search_tool_available = true`, `live_web_lookup_available = true`,
bounded public-safe response metadata, `required_tool_calls_satisfied = true`
for the build-planning probe, and `world_mutation_authority = luanti`.
It is the evidence path for proving the sidecar is actually running Agents SDK
agents with hosted web lookup instead of only publishing the offline contract.
The Pi fork deploy script sets the live sidecar log to:

```text
/opt/ai-native-luanti/logs/agents-sdk-model-adapter.jsonl
```

Live side-by-side Pi proof from 2026-06-30:

- Family server remained active on UDP `30000`.
- Fork test server remained active on UDP `30001`.
- Agents SDK adapter remained active on loopback TCP `8766`.
- The live adapter health check reported `agents_sdk_available = true`,
  `openai_api_key_present = true`, `web_search_tool_available = true`, and a
  mounted reviewed prompt-memory case pack.
- Provider-backed build-planning probes for `build a fire`,
  `build me a fire and only a fire`, and `build a wall of tnt` each returned
  `tool_decision_source = agents_sdk_function_tool`,
  `required_tool_calls_satisfied = true`, no missing required tools, no repair
  pass, and no rejected tool calls after candidate-token alias normalization.
- The selected executable options were `fire`, `fire`, and `tnt_wall`
  respectively, each with a ready `luanti_build_action_plan_v1`.
- Observed adapter latency for those three live probes was about 5.2-7.5
  seconds on the Pi lane.

## Luanti Adapter

The Lua adapter is disabled by default and is loaded only when:

```text
ai_runtime.enable_agents_sdk_adapter = true
ai_runtime.agents_sdk_adapter_timeout = 60
```

For real server use, grant HTTP access to the profile bridge mod, not to
builtin code or unrelated gameplay mods:

```text
secure.http_mods = ai_runtime_agents_sdk_bridge
```

`games/ai_runtime/mods/ai_runtime_agents_sdk_bridge` supplies only the Luanti
HTTP API handle to the already-enabled builtin bridge. It does not contain
provider credentials, endpoints, or world mutation logic.

Default endpoint:

```text
http://127.0.0.1:8766/v1/model-adapter
```

Probe commands:

```text
/ai_agents_sdk_adapter_probe
/ai_agents_sdk_adapter_probe_async
```

The adapter installs itself into `core.ai_agent_plugin.set_model_adapter` and,
when available, `core.ai_agent_plugin.set_model_adapter_async` when enabled, so
unknown `/nova` prompts can flow through the Agents SDK sidecar without
spin-waiting on a live provider call. The synchronous probe is for
contract/offline checks. Live sidecar checks should use the async probe path,
which calls Luanti's callback HTTP API and lets the server continue stepping
while the Agents SDK call is in flight. The Lua side only accepts loopback
endpoints by default. The sidecar can perform hosted web search and
function-tool reasoning, but it still returns a bounded
`ai_native_model_adapter_response`; the engine decides whether any proposed
world action becomes a preview, approval, rollback-backed task, or refusal.

## Tool Policy

Initial tools are deliberately read-only:

- `summarize_runtime_capabilities`: tells the agent which runtime gates have
  already been granted.
- `classify_world_action`: labels planned node writes as requiring preview,
  approval, and rollback before the engine may execute them.
- `recall_build_prompt_memory`: checks an optional reviewed prompt-eval case pack
  for exact public prompt regressions, then returns only a bounded option id and
  case id.
- `plan_build_actions`: converts the selected build option into a read-only
  `luanti_build_action_plan_v1` workflow. It does not mutate the world; it
  states that Luanti owns preview, player approval, rollback-backed task
  execution, and improvement evidence.
- `propose_build_option`: creates a bounded generated build option for
  open-ended player requests such as towers, bridges, paths, or shelter floors;
  it is read-only and Luanti may reject it before preview.
- `select_build_option`: validates the option id the live agent selected from
  Luanti-supplied bounded candidates or a validated generated proposal. This is
  the required live build-planning tool because the model chooses and the tool
  binds that choice to an auditable execution contract.
- `recommend_build_option`: compatibility fallback that can choose from
  Luanti-supplied bounded build candidates when the live agent path is missing
  or fails required tool-call evidence. It is not the primary live intelligence
  path.
- `WebSearchTool`: lets the agent look up current public information when the
  prompt genuinely needs it.

The sidecar publishes these as a structured `tool_powers` manifest from
`GET /health` and in adapter responses:

```json
{
  "name": "WebSearchTool",
  "kind": "hosted_tool",
  "runtime_power": "public_web_lookup",
  "read_only": true,
  "direct_world_mutation": false,
  "engine_authority": "luanti_model_adapter_response_only"
}
```

`tool_powers` is an evidence surface, not a permission grant. The engine still
checks capabilities, records audit, and converts any proposed world action into
preview, approval, rollback, or refusal.

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
uv run --project tools/agents_sdk_model_adapter python util/ai_native_agents_sdk_sidecar_readiness.py --mode managed-http --port 8766 --require-live-agent
python3 tools/agents_sdk_model_adapter/main.py --smoke
bin/luantiserver --run-unittests --test-module TestAIRuntime
```

The contract verifier checks that the reference sidecar imports and wires the
Agents SDK primitives, exposes the model-adapter HTTP endpoint, keeps the
runtime as the mutation authority, gates the Lua bridge behind
`ai_runtime.enable_agents_sdk_adapter`, publishes a safe `tool_powers` manifest,
and produces a safe offline response envelope without credentials or network
access.
