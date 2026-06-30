# AI-Native Runtime

Status: project direction for the `billjamesevans/ai-native-luanti` fork.

## Mission

Build an AI-native voxel server/runtime on top of Luanti. The first milestone is not Minecraft compatibility. The first milestone is a safer runtime where human players and AI agents can share a world, perform bounded work, report structured results, and remain observable and cancellable.

Compatibility and import tooling comes after the runtime can safely inspect, modify, repair, and explain world changes.

## Scope

The fork should add reusable runtime capabilities:

- Agent identity and ownership.
- Capability-based permissions for agents and plugins.
- Cancellable server-side task queues.
- Safe world operation APIs for inspect, place, remove, replace, batch, move, and summarize.
- Structured action results for every operation.
- Metrics and audit trails for long-running agent work.
- Benchmark gates for world edits, entity load, mapblock churn, and server-step impact.

The fork should not absorb private-server content, showcase builds, copied proprietary assets, or one-off world coordinates.

## Design Documents

- [MVP spec](mvp-spec.md)
- [MVP gap checklist](mvp-gap-checklist.md)
- [Post-MVP alpha roadmap](post-mvp-alpha-roadmap.md)
- [v0.3 AI-native proving ground roadmap](v0.3-proving-ground-roadmap.md)
- [Alpha release gate](alpha-release-gate.md)
- [Operator alpha release runbook](operator-alpha-release-runbook.md)
- [Clean ai_runtime install/run guide](clean-ai-runtime-install.md)
- [Project operating loop](project-operating-loop.md)
- [Low-power Pi evidence lane](low-power-pi-evidence-lane.md)
- [Public-safe sample data policy](public-safe-sample-data-policy.md)
- [Release notes template](release-notes-template.md)
- [Agent identity and capability API](agent-api.md)
- [Agent capability profiles](agent-capability-profiles.md)
- [Alpha server profile](alpha-server-profile.md)
- [Agent task queue API](task-queue-api.md)
- [Safe world operations API](safe-world-ops-api.md)
- [Safe entity operations API](safe-entity-ops-api.md)
- [Safe player operations API](safe-player-ops-api.md)
- [Model and import runtime gates](model-import-runtime-gates.md)
- [Model adapter contract](model-adapter-contract.md)
- [Agents SDK Model Adapter](agents-sdk-model-adapter.md)
- [Model adapter plugin scaffold](model-adapter-plugin-scaffold.md)
- [Runtime metrics and audit API](metrics-audit-api.md)
- [First-party agent plugin](first-party-agent-plugin.md)
- [Family prototype plugin boundaries](family-prototype-plugin-boundaries.md)
- [Family creatures boundary audit](family-creatures-boundary-audit.md)
- [Repair agent plugin](repair-agent-plugin.md)
- [Build agent plugin](build-agent-plugin.md)
- [Rollback metadata](rollback-metadata.md)
- [Demo entity and vehicle provenance](demo-entity-vehicle-provenance.md)
- [Generic demo entity benchmark](generic-demo-entity-benchmark.md)
- [Compatibility import dry-run reports](compatibility-import-dry-run.md)
- [Compatibility apply phase](compatibility-apply-phase.md)
- [Benchmark plan](benchmark-plan.md)
- [Mutation benchmark scenarios](mutation-benchmark-scenarios.md)
- [Benchmark baseline retention](benchmark-baseline-retention.md)
- [Minecraft-parity benchmark harness](minecraft-parity-benchmark-harness.md)
- [Synthetic runtime smoke](synthetic-runtime-smoke.md)
- [Operator status package](operator-status-package.md)
- Product-profile fixture gate: `python3 util/ai_native_product_profile_verify.py`
- Operator status package: `python3 util/ai_native_operator_status_package.py`
- Operator-control report adapter: `python3 util/ai_native_operator_control_report.py --input local/operator-status.json`
- Operator action approval plan: `python3 util/ai_native_operator_action_approval_plan.py --input local/operator-control-report.json`
- Operator action approval receipt: `python3 util/ai_native_operator_action_approval_receipt.py --input local/operator-action-approval-plan.json --decision local/operator-decision.json`
- Operator task-control executor: `python3 util/ai_native_operator_task_control_executor.py --input local/operator-action-approval-receipt.json`
- Operator task-control live probe: `python3 util/ai_native_operator_task_control_live_probe.py --output local/ai-runtime-operator-task-control-live-result.json --generated-at 2026-06-29T00:00:00Z`
- Operator task-control command probe: `python3 util/ai_native_operator_task_control_command_probe.py --output local/ai-runtime-operator-taREDACTED_KEY_FIXTURE.json --generated-at 2026-06-29T00:00:00Z`
- Command task-control boundary: receipt-gated task-control command probe, task cancel/retry only, no rollback execution, no import promotion execution, and no world mutation.
- Live task-control boundary: disposable live `ai_runtime` queue probe, task cancel/retry only, no rollback execution, no import promotion execution, and no world mutation.
- First-party agent product-loop live probe: `python3 util/ai_native_agent_product_loop_live_probe.py --root . --server-bin bin/luantiserver --output local/benchmarks/agent-product-loop-live.json --generated-at 2026-06-29T00:00:00Z`
- Nova prompt eval live probe: `python3 util/ai_native_agent_prompt_eval_live_probe.py --root . --server-bin bin/luantiserver --output local/benchmarks/ai-runtime-agent-prompt-eval-live-result.json --generated-at 2026-06-29T00:00:00Z`
- Agent Improvement Loop candidate queue: `python3 util/ai_native_agent_eval_queue.py --agents-sdk-log local/logs/agents-sdk-model-adapter.jsonl --nova-agent-log local/logs/nova-agent-requests.jsonl --action-log local/logs/luanti-debug.log --output local/benchmarks/ai-agent-eval-candidate-queue.json --generated-at 2026-06-30T00:00:00Z`
- Agent Improvement Loop case-pack promotion: `python3 util/ai_native_agent_eval_promote.py --candidate-queue local/benchmarks/ai-agent-eval-candidate-queue.json --output local/benchmarks/ai-agent-prompt-eval-case-pack.json --generated-at 2026-06-30T00:00:00Z`
- Agent memory refresh: `python3 util/ai_native_agent_memory_refresh.py --agents-sdk-log local/logs/agents-sdk-model-adapter.jsonl --nova-agent-log local/logs/nova-agent-requests.jsonl --action-log local/logs/luanti-debug.log --candidate-queue-output local/benchmarks/ai-agent-eval-candidate-queue.json --case-pack-output local/benchmarks/ai-agent-prompt-eval-case-pack.json --generated-at 2026-06-30T00:00:00Z`
- Agentic build selection contract: Agents SDK build-planning responses may change the pending preview only through `response.selected_option_id` or `response.tool_decisions.build_option.selected_option_id` matching a bounded candidate from Luanti; healthy live runs must expose `tool_decision_source = agents_sdk_function_tool` and `required_tool_calls_satisfied = true`, while fallback sources feed the eval/improvement loop.
- Compatibility import staging pilot: `python3 util/ai_native_compat_import_staging_pilot.py --root . --server-bin bin/luantiserver --output local/benchmarks/ai-runtime-compat-import-staging-pilot-result.json --generated-at 2026-06-29T00:00:00Z`
- Live operator status command: `/ai_runtime_operator_status`
- Focused operator status views: `/ai_runtime_operator_status view=tasks`, `view=task task_id=<task-id>`, `view=audit`, `view=rollback`, `view=imports`
- Live operator task-control command: `/ai_runtime_operator_task_control`
- Live Nova prompt eval command: `/ai_agent_eval`
- Alpha release package gate: `python3 util/ai_native_alpha_release_gate.py`
- Model adapter contract gate: `python3 util/ai_native_model_adapter_contract.py`
- Agents SDK bridge contract gate: `python3 util/ai_native_agents_sdk_bridge_contract.py`
- Optional model adapter scaffold: enable `ai_runtime.enable_model_adapter_probe_command` and run `/ai_model_adapter_probe`
- One-command local pre-PR verification with clean-profile workload evidence: `python3 util/ai_native_runtime_verify.py --hardware-class local-mac --game-profile ai_runtime`
- Low-power Pi evidence lane: `python3 util/ai_native_low_power_pi_evidence.py --ssh-target "<operator-supplied-target>" --confirm-backup-first --soak-target quick`
  - Promoted targets: add `--soak-target one-hour --soak-iterations 13 --soak-interval-seconds 300`; after that is clean, use `--soak-target overnight --soak-iterations 17 --soak-interval-seconds 1800`.
  - The Pi lane requires a strict `headless_client_load` probe with at least two attempted/connected synthetic players, join-log latency proxy evidence, and `ai_runtime_scale_gate=pass`.
- Synthetic-only utility fallback: add `--game-profile sample-synthetic`
- Strict headless-player verification: add `--require-headless-player-probe` with a disposable `--headless-player-command`
- One-command product-profile artifact: `ai-runtime-product-profile-hygiene.json`
- Clean-profile runtime gap scorecard: `python3 util/ai_native_runtime_gap_scorecard.py --output-root local/benchmarks`
- Minecraft-parity comparison report: `python3 util/ai_native_minecraft_parity_harness.py --output-root local/benchmarks`
- Alpha baseline review: `python3 util/ai_native_alpha_baseline_review.py --output-root local/benchmarks`
- MVP gap audit: `python3 util/ai_native_mvp_audit.py --scorecard local/benchmarks/runtime-gap-scorecard.json --output local/benchmarks/ai-native-mvp-audit.json`
- [AI runtime server profile](non-devtest-server-profile.md)
- [Baseline status](baseline-status.md)
