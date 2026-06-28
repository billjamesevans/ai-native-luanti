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
| Agent identity and capabilities | `already_proven` | `core.register_ai_agent`, capability checks, configurable first-party grants, and clean-profile policy tests exist. | Keep privileged grants out of default clean-profile policy unless an operator-specific profile explicitly opts in. |
| Queued inspect/place/remove | `already_proven` | Safe world ops and queue tests cover inspect, place, remove, batch place, and batch remove. | Keep expanding through runtime scenarios. |
| Structured action results | `already_proven` | Central action-result helpers and schema assertions exist. | Keep all new runtime APIs on this result shape. |
| Task cancellation | `already_proven` | Owner/admin cancellation paths are tested. | Keep cancellation wired into every long-running plugin task. |
| Protected and unsafe skips | `already_proven` | Protected, unbreakable, hazard, and sample reporting paths are tested. | Add player-proximity safety when player movement APIs land. |
| Runtime metrics | `already_proven` | Queue, node-write, model, entity, and task-duration counters are exposed in operator metrics. | Keep benchmark dashboards downstream of this runtime snapshot. |
| Deterministic first-party plugin actions | `already_proven` | The plugin queues light, build, repair, cancel, tasks, and model fallback paths through runtime APIs. | Preserve the no raw world-write boundary. |
| Follow/come product behavior | `already_proven` | Follow and come queue bounded helper-entity movement through `core.ai_entity_ops` and `core.queue_ai_task`. | Add continuous follow/pathfinding as a later gameplay slice. |
| Lag pausing and budgets | `already_proven` | Manual pause, automatic lag threshold pausing, node-write budget checks, and wall-clock budget checks are covered in `TestAIRuntime`. | Keep measuring behavior under benchmark load. |
| Player teleport and defensive combat | `already_proven` | `core.ai_player_ops` covers self teleport, admin-only other-player teleport, and bounded defend actions with focused runtime tests. | Keep broader combat AI and pathfinding as later gameplay slices. |
| Model/import capability gates | `already_proven` | `core.ai_model_ops.request` and `core.ai_import_ops.plan` gate queued runtime work through `http.llm` and `import.assets`. | Keep the compatibility apply phase deferred until runtime safety is stronger. |
| Compatibility/import | `compatibility_import_deferral` | MVP spec explicitly defers compatibility/import. | Resume after the runtime gaps above are closed. |

## Ranked Follow-On Issues

Completed:

- #95 `mvp-task-budget-lag-pausing`: implemented wall-clock budgets and automatic lag-based pausing.
- #96 `mvp-first-party-agent-plugin-runtime`: made follow and come queue bounded runtime entity movement.
- #97 `mvp-player-teleport-combat-runtime`: added safe player teleport and defensive-combat capability slices.
- #98 `mvp-model-import-capability-runtime`: aligned model and import capability gates with queued runtime execution.
- #99 `mvp-runtime-task-duration-metrics`: exposed task-duration aggregates in the operator runtime snapshot.
- #100 `mvp-agent-policy-profile`: added clean-profile policy tests for first-party agent capability grants.

Remaining:

None for the current AI-native runtime MVP acceptance matrix. Compatibility/import remains intentionally deferred.
