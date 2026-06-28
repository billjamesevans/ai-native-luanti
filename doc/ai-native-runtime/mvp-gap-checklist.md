# AI-Native Runtime MVP Gap Checklist

Status: Issue #94 audit artifact

This checklist tracks MVP readiness against `doc/ai-native-runtime/mvp-spec.md`. The clean scorecard is a prerequisite gate, not proof that the MVP behavior is complete.

Run the verifier:

```bash
python3 util/ai_native_mvp_audit.py --scorecard local/benchmarks/runtime-gap-scorecard.json --output local/benchmarks/ai-native-mvp-audit.json
```

The generated JSON is local evidence under `local/benchmarks/`. This committed checklist is the public-safe project record and must not include private worlds, live hostnames, player-private data, provider prompts, copied assets, or proprietary game content.

## Category Definitions

- `already_proven`: implemented and backed by focused tests, docs, and accepted benchmark or verifier evidence.
- `implemented_but_weakly_verified`: code exists, but the current verification is too narrow for MVP completion.
- `missing_runtime_behavior`: required runtime behavior is absent or only a placeholder.
- `missing_first_party_plugin_behavior`: first-party plugin behavior is not yet real enough to prove the player-facing agent loop.
- `compatibility_import_deferral`: intentionally deferred until the AI-native runtime is safer and more observable.

## Requirement Matrix

| MVP item | Category | Current evidence | Next action |
| --- | --- | --- | --- |
| Fork builds locally | `already_proven` | `util/ai_native_runtime_verify.py` runs utility contracts, benchmark gate, and `TestAIRuntime`. | Keep as the pre-PR gate. |
| Agent identity and capabilities | `implemented_but_weakly_verified` | `core.register_ai_agent`, capability checks, and unit tests exist. | Add clean-profile policy coverage for real server defaults. |
| Queued inspect/place/remove | `already_proven` | Safe world ops and queue tests cover inspect, place, remove, batch place, and batch remove. | Keep expanding through runtime scenarios. |
| Structured action results | `already_proven` | Central action-result helpers and schema assertions exist. | Keep all new runtime APIs on this result shape. |
| Task cancellation | `already_proven` | Owner/admin cancellation paths are tested. | Keep cancellation wired into every long-running plugin task. |
| Protected and unsafe skips | `already_proven` | Protected, unbreakable, hazard, and sample reporting paths are tested. | Add player-proximity safety when player movement APIs land. |
| Runtime metrics | `implemented_but_weakly_verified` | Queue and node-write counters exist; per-result elapsed time exists. | Add task-duration aggregates to operator metrics. |
| Deterministic first-party plugin actions | `already_proven` | The plugin queues light, build, repair, cancel, tasks, and model fallback paths through runtime APIs. | Preserve the no raw world-write boundary. |
| Follow/come product behavior | `missing_first_party_plugin_behavior` | Current follow and come commands store state only. | Implement bounded movement/pathing through runtime APIs. |
| Lag pausing and budgets | `already_proven` | Manual pause, automatic lag threshold pausing, node-write budget checks, and wall-clock budget checks are covered in `TestAIRuntime`. | Keep measuring behavior under benchmark load. |
| Player teleport and defensive combat | `missing_runtime_behavior` | Capabilities are in the MVP spec, but runtime APIs are not present. | Add default-deny safe APIs and tests. |
| Model/import capability gates | `missing_runtime_behavior` | Model metrics and import dry-run planning exist. | Align `http.llm` and `import.assets` with runtime task gates. |
| Compatibility/import | `compatibility_import_deferral` | MVP spec explicitly defers compatibility/import. | Resume after the runtime gaps above are closed. |

## Ranked Follow-On Issues

Completed:

- #95 `mvp-task-budget-lag-pausing`: implemented wall-clock budgets and automatic lag-based pausing.

Remaining:

1. #96 `mvp-first-party-agent-plugin-runtime`: make follow and come real bounded runtime behavior.
2. #97 `mvp-player-teleport-combat-runtime`: add safe player teleport and defensive-combat capability slices.
3. #98 `mvp-model-import-capability-runtime`: align model and import capability gates with runtime task execution.
4. #99 `mvp-runtime-task-duration-metrics`: expose task-duration aggregates in operator metrics.
5. #100 `mvp-agent-policy-profile`: add clean-profile policy tests for first-party agent capability grants.
