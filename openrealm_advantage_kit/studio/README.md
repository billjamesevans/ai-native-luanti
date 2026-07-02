# OpenRealm Creator Studio Prototype

Open `index.html` in a browser, or serve the parent `openrealm_advantage_kit`
directory and visit `/studio/`.

For live Pi telemetry, serve the Studio through the bundled bridge:

```bash
python3 studio/server.py --root . --host 127.0.0.1 --port 8788
```

Then open `http://127.0.0.1:8788/studio/`. The bridge exposes `/api/status`
with public-safe service, fork, quality-gate, and Agents SDK adapter summaries.
It does not expose raw prompts, provider messages, credentials, private paths,
or world payloads. Adapter summaries separate current gate health from
historical lifetime counts so old failed probes do not obscure a passing live
release gate. `adapter_log.release_health` reports the newest public-safe trace,
while `recent_window_health` and `history_health` keep rolling and lifetime
failures visible for follow-up. Prompt-eval summaries expose only case IDs, pass
counts, golden prompt coverage, and safety flags.

Runtime-proof summaries expose only status and counts for rollback-backed Nova
auto-apply probes and compatibility import staging rehearsals. They prove that
world mutation goes through Luanti runtime tasks, rollback records exist, and
compatibility import stays in disposable/staging worlds without exposing raw
prompts, private coordinates, provider messages, or copied assets.

Live-review gate summaries expose the newest Nova review-loop result when
`OPENREALM_LIVE_REVIEW_GATE` points at a gate JSON file. The bridge only emits
status, trace ID, selected option, case hint, check counts, artifact key names,
and safety flags. It rejects unsafe gate payloads and never exposes raw prompts,
provider messages, credentials, private paths, violation details, or generated
artifact paths. On the Pi, the default gate path is
`/opt/ai-native-luanti/src/local/review-packets/live-review-gate/latest-gate-result.json`.

The Agent trace panel displays the newest public-safe adapter summaries: selected
option, tool-decision source, planned write count, required-tool status,
web-search availability, mutation authority, and a bounded tool-name list. It
does not display raw player prompts, model messages, provider prompts, secrets,
private paths, coordinates, or world payloads.

The Review packet panel turns a selected trace summary into a public-safe
operator-feedback handoff. It generates the matching `/ai_agent_feedback
trace=...` command plus an exportable JSON packet with expected build kind,
material, planned writes, selected candidate, and safety flags. The packet is
designed to feed the existing `util/ai_native_agent_feedback_packet.py` /
prompt-memory refresh loop without exposing raw prompts or provider messages.

To turn a live or saved Studio trace into reviewed eval artifacts, run:

```bash
python3 util/ai_native_agent_live_review_gate.py \
  --status-json local/status/openrealm-studio-status.json \
  --agents-sdk-log local/benchmarks/agents-sdk-model-adapter.jsonl \
  --output-dir local/review-packets/live-review \
  --artifact-prefix latest \
  --gate-output local/review-packets/live-review/latest-gate-result.json
```

The gate writes the review packet, candidate queue, operator label, and
prompt-memory case pack, then verifies artifact kinds, public-safety flags,
label matching, candidate membership, and case-pack readiness. For manual
handoff or debugging, pass a specific `--trace-id nova_trace:...`, or run the
same flow in smaller steps:

```bash
python3 util/ai_native_agent_live_review_loop.py \
  --status-json local/status/openrealm-studio-status.json \
  --agents-sdk-log local/benchmarks/agents-sdk-model-adapter.jsonl \
  --trace-id nova_trace:11 \
  --output-dir local/review-packets/live-review

python3 util/ai_native_agent_studio_review_packet.py \
  --status-json local/status/openrealm-studio-status.json \
  --trace-id nova_trace:11 \
  --output local/review-packets/openrealm_agent_review_packet.json

python3 util/ai_native_agent_feedback_packet.py \
  --agents-sdk-log local/benchmarks/agents-sdk-model-adapter.jsonl \
  --studio-review-packet local/review-packets/openrealm_agent_review_packet.json
```

These tools reject packets that include private paths, provider payloads,
credentials, raw assets, or family-world details.

This prototype is dependency-free and can still run entirely offline. It demonstrates the product loop:

1. Prompt Nova.
2. Generate a deterministic safe plan.
3. Preview planned world changes.
4. Approve and apply.
5. Audit the changes.
6. Undo with rollback.
7. Export JSON or Lua.

Current planner checks cover strict simple requests:

- `Build only a fire` creates exactly one `fire:basic_flame` action.
- `Build a wall of tnt` creates a ready medium-risk TNT wall plan instead of
  refusing or falling back to a generic structure.

The code is intentionally framework-free so it can be moved into React, Tauri, Qt, Electron, or the Luanti UI layer later.
