# Compatibility Apply Phase

Status: phase-two design, no-mutation planning, staged structure apply, reviewed rollback, adapter smoke implementation, operator smoke review, and promotion evidence packaging

## Purpose

The compatibility apply phase turns an approved dry-run report into bounded AI task queue work. It is the first point where compatibility import may reference user-owned assets, register generated definitions, or mutate a Luanti world.

Dry run and apply are separate modes. Dry run inventories and reports. Apply consumes a reviewed report plus explicit operator approval.

## Non-Goals

- Do not apply anything from an unreviewed dry-run report.
- Do not copy protected assets into the engine fork.
- Do not mutate a world from `dry_run` mode.
- Do not execute source behavior scripts.
- Do not bypass `import.assets` capability checks.
- Do not perform large node writes outside the AI task queue.

## Inputs

An apply request requires:

- `report_id`: stable identifier for the dry-run report.
- `report_version`: dry-run schema version accepted by the apply code.
- `source_reference`: external path, mount, or operator-supplied content address.
- `approved_actions`: explicit list of planned action ids or action indexes to run.
- `target_world`: Luanti world identifier or staging world.
- `operator`: player, server admin, or automation identity approving the work.
- `agent_id`: import agent that will own queued tasks.
- `budget`: node-write, mapblock-churn, media, entity, wall-clock, and manual-review limits.
- `rollback_policy`: snapshot, manifest-only, or no-world-mutation mode.

The apply phase must reject requests that omit approval, source references, budgets, or rollback policy.

The machine-readable request and summary contracts live at:

- [`schemas/compatibility-apply-request.schema.json`](schemas/compatibility-apply-request.schema.json)
- [`schemas/compatibility-apply-summary.schema.json`](schemas/compatibility-apply-summary.schema.json)

Synthetic examples live at:

- [`examples/compatibility-apply-request.example.json`](examples/compatibility-apply-request.example.json)
- [`examples/compatibility-apply-summary.example.json`](examples/compatibility-apply-summary.example.json)

## Required Capability

The import agent must be registered through the AI runtime and hold:

- `import.assets`

World-changing apply steps also require the relevant world capability:

- `world.place` for structure placement or node alias materialization.
- `world.remove` only when an approved action explicitly replaces existing content.
- `world.batch` for multi-node operations.

`admin.override` may bypass selected safety gates only when the action is audited and the operator is an admin.

## Dry-Run To Apply Transition

1. Operator runs dry run against a user-owned source.
2. Operator reviews `unsupported_features`, `planned_actions`, `mutation_cost`, and `safety`.
3. Operator selects approved planned actions.
4. Apply validates the report and source reference.
5. Apply expands each approved planned action into queued task steps.
6. The AI task queue executes bounded steps.
7. Each step records audit events and rollback metadata.
8. Apply emits an apply summary that links back to the dry-run report.

The dry-run report remains immutable. Apply creates a separate apply record.

## Planned Action Mapping

| Dry-run action | Apply task label | Queue behavior | World mutation |
| --- | --- | --- | --- |
| `copy_asset_reference` | `compat.asset.reference` | Verify external source path/hash and write an operator-local manifest entry. | No mapblock writes. |
| `map_texture` | `compat.media.texture` | Register or stage a texture mapping from an operator-owned source. | No mapblock writes. |
| `map_sound` | `compat.media.sound` | Register or stage a sound mapping from an operator-owned source. | No mapblock writes. |
| `register_node_alias` | `compat.node.alias` | Register a node or item alias mapping for later use. | No mapblock writes unless paired with approved placement. |
| `register_entity_stub` | `compat.entity.stub` | Create a placeholder entity definition without imported behavior AI. | No mapblock writes. |
| `import_structure` | `compat.structure.place` | Slice structure placement into safe world operation batches. | Yes, through `core.ai_world_ops` only. |
| `skip_feature` | `compat.feature.skip` | Record explicit skip reason in apply summary. | No mutation. |

No planned action maps to direct raw world writes.

## Task Shape

Each apply task should use `core.queue_ai_task` with:

- `task_id`: `compat:<report_id>:<action_index>`.
- `agent_id`: approved import agent.
- `owner`: approving operator.
- `label`: task label from the mapping table.
- `budget.max_steps_per_step`: conservative default of `1`.
- `budget.max_node_writes_per_step`: operator-approved node-write slice.
- `steps`: generated bounded functions for validate, stage, apply, audit, and summarize.

Every step returns a structured action result. A `blocked`, `unsafe`, or `failed` result stops the task and preserves rollback metadata.

## Budgets

Apply must enforce explicit budgets before queueing and during execution:

- `max_media_files`: number of external media references to stage.
- `max_entity_definitions`: number of generated entity or node definitions.
- `max_node_writes_total`: total approved world writes.
- `max_node_writes_per_step`: per-queue-step world writes.
- `max_mapblock_churn_total`: total approved mapblock churn from structure placement.
- `max_manual_review_items`: count of items allowed to remain manual.
- `max_wall_time_ms`: operator-facing runtime limit.

If the dry-run report estimates a larger cost than the approval budget, apply fails closed with `too_large_for_budget`.

## Rollback Requirements

Before any mapblock mutation, apply must create rollback metadata:

- Target world id.
- Report id and planned action id.
- Task id.
- Operator and agent id.
- Bounds or positions to be changed.
- Previous node names and param data for touched positions.
- Timestamp and fork version.

For large structure imports, rollback data may be chunked by task step. A failed step must not discard prior rollback chunks.

Media and definition staging should be reversible by manifest entry, not by deleting unknown files from the operator's source path.

## Rollback Execution

Reviewed structure rollbacks use `core.ai_import_ops.queue_chunked_structure_rollback_task`. The task consumes inspected records from `core.ai_import_ops.plan_structure_rollback`, direct rollback records, or explicit rollback refs, then executes chunks in reverse chunk order by default.

Rollback execution is not a default player action. It requires:

- `rollback.execute`
- `admin.override`
- `world.place`
- `world.batch`
- explicit operator approval
- a staging target and `world_id`
- `allow_mutation = true`
- manifest, snapshot, or chunked rollback policy
- total and per-step node-write budgets
- mapblock-churn and wall-clock budgets

Each rollback execution chunk writes rollback-of-rollback metadata before it mutates the world. If that safety metadata cannot be persisted, the task blocks before node writes. Protected areas and safe-world failures remain visible as structured action results, including changed and skipped counts.

## Reviewed Adapter Apply Smoke

The structure adapter path can now produce a reviewed apply-and-rollback smoke manifest for disposable staging worlds. This mode consumes the `structure_adapter` handoff emitted by the dry-run report and turns it into a machine-readable runtime sequence:

- `core.ai_import_ops.define_chunked_structure_apply_task` for approved structure placement.
- `core.ai_import_ops.plan_structure_rollback` for readback of generated rollback records.
- `core.ai_import_ops.queue_chunked_structure_rollback_task` for reviewed rollback execution.

The smoke manifest is not a live-world importer. It requires:

- an approved `import_structure` action from a supported structure adapter
- `target_world.staging = true`
- `target_world.disposable = true`
- `rollback_policy.policy = chunked`
- node-write and mapblock-churn budgets large enough for the adapter payload
- operator-supplied runtime hooks for node reads/writes and rollback persistence

The CLI shape is:

```bash
python3 util/ai_native_compat_dry_run.py \
	--adapter-apply-smoke /path/to/dry-run-report.json \
	--approval /path/to/apply-request.json \
	--output /path/to/adapter-smoke.json \
	--summary
```

The generated manifest reports expected node writes, mapblock churn, apply chunk count, rollback chunk count, target world, required capabilities, and the runtime entrypoints. Creating the manifest does not mutate a world; the server-side smoke is verified by `TestAIRuntime`, which applies the reviewed handoff in a disposable in-memory staging world, reads rollback records back, executes rollback in reverse chunk order, and covers approval denial, non-staging denial, and protected partial behavior.

Before running the apply task, operators can gate the manifest with:

```bash
python3 util/ai_native_compat_dry_run.py \
	--review-adapter-smoke /path/to/adapter-smoke.json \
	--output /path/to/adapter-smoke-review.json \
	--summary
```

The review output is machine-readable and never mutates a world. It reports `ready` only when the manifest still targets a disposable staging world, uses the expected apply/rollback entrypoints, carries explicit approval, includes rollback tasks, keeps runtime hooks available for node read/write and rollback persistence/readback, and stays within the reviewed mutation budgets. Missing approval, missing rollback, missing hooks, forbidden family/prod world ids, non-staging targets, non-disposable targets, and inflated write/churn budgets produce `blocked` findings before any runtime apply task is considered promotable.

## Public-Safe Structure Format

The first real structure-format slice is `ai_native_structure_v1`, carried by a JSON file with `format_kind = ai_native_public_structure`. It is deliberately small and public-safe:

- `license.status = user_supplied` and `license.rights_confirmed = true` are required.
- `dimensions` bounds every placement.
- `palette` maps local aliases to Luanti node names or `air`.
- `placements` hold position, node alias/name, and optional `param1`/`param2`.
- `unsupported_fields` and redacted `private_references` are reported as unsupported/manual-review items, not imported silently.

The adapter emits `public_safe_structure_v1` metadata into the dry-run report, then reuses the same approval, adapter-smoke, operator-review, chunked apply, rollback planning, and rollback execution gates. It does not parse proprietary Minecraft server behavior, ship Mojang assets, ship family-world assets, or mutate the live family world.

## Public-Safe Staging Pilot

The current end-to-end pilot is:

```bash
python3 util/ai_native_compat_import_staging_pilot.py \
	--root . \
	--server-bin bin/luantiserver \
	--output local/benchmarks/ai-runtime-compat-import-staging-pilot-result.json \
	--generated-at 2026-06-29T00:00:00Z
```

The pilot runs the public-safe structure fixture through inventory discovery, dry-run reporting, apply-plan validation, adapter smoke, operator review, and promotion evidence construction before launching a disposable `ai_runtime` staging world. Inside that disposable world it queues the reviewed chunked apply task through `core.ai_import_ops`, verifies five node writes across three chunks, records mapblock churn, reads rollback records back, executes rollback, and verifies the nodes reverted.

The same live artifact records refusal gates for missing approval, missing rollback policy, unsafe/private payloads, non-staging targets, and over-budget writes. The one-command verifier runs this pilot by default and retains the bounded artifact as `ai-runtime-compat-import-staging-pilot-result.json`.

## Public-Safe Schematic Preflight

The next compatibility-format slice is `ai_native_schematic_preflight_v1`, carried by a JSON file with `format_kind = ai_native_public_schematic_preflight`. It is not a raw schematic parser. It is a public-safe preflight contract for operator-supplied metadata:

- `license.status = user_supplied` and `license.rights_confirmed = true` are required.
- `preflight.payload_policy = metadata_only` and `preflight.source_format = schematic` are required.
- `dimensions`, `palette`, and `placements` or `estimated_placements` map safe placement metadata into the existing `public_safe_structure_v1` handoff shape.
- `unsupported_fields` records schematic features such as block entities or biomes for manual review.
- Raw schematic/NBT payloads, copied protected content, private source paths, and family-world coordinates are rejected before a dry-run report is produced.

The preflight adapter emits `source_adapter_kind = public_safe_schematic_preflight_v1` and `structure_format = ai_native_schematic_preflight_v1` while preserving the same approval, adapter-smoke, operator-review, rollback, and promotion-package gates as `ai_native_structure_v1`.

## Reviewed Structure Promotion Package

Before adding broader schematic, world, or resource-pack compatibility formats, reviewed public-safe structure imports produce a durable promotion package. This package is an operator evidence artifact, not an importer. It binds together:

- the immutable dry-run report id and redacted source inventory
- license status and operator-confirmed rights status
- explicit operator approval state, target world, rollback policy, and budgets
- adapter apply smoke summary
- operator review gate status and machine-promotable flag
- apply task ids, entrypoints, placement count, chunk count, and required capabilities
- rollback task ids, rollback policy, metadata-readback requirement, and required capabilities
- unsupported-feature summary
- public-safety flags that keep private paths, raw payloads, private prompts, secrets, family-world coordinates, and live-world mutation out of the artifact

The CLI shape is:

```bash
python3 util/ai_native_compat_dry_run.py \
	--promotion-package /path/to/dry-run-report.json \
	--approval /path/to/apply-request.json \
	--adapter-smoke /path/to/adapter-smoke.json \
	--adapter-review /path/to/adapter-smoke-review.json \
	--output /path/to/structure-promotion-package.json \
	--summary
```

The command fails closed when approval is missing, the dry-run hash does not match the approval request, the smoke/review report ids differ from the approval report id, the target is not disposable staging, the target names a family or production world, rollback metadata readback is missing, the supplied review gate is blocked, or recomputing the review from the smoke artifact is blocked.

Promotion packages are available only for public-safe adapter handoffs. Synthetic fixtures remain useful for tests and runtime smoke coverage, but they are not eligible for operator promotion packages.

## Reviewed Asset-Reference Promotion Package

Resource-pack compatibility uses a separate no-mutation promotion package. It is an operator evidence artifact for Java or Bedrock resource-pack dry-run reports, not an asset copier. It can package reviewed texture, sound, and model-reference intent while leaving all source asset bytes operator-supplied outside the fork.

The package binds together:

- the immutable dry-run report id and redacted source inventory
- license status and operator-confirmed rights status
- explicit operator approval, operator id, agent id, rollback policy, and zero-mutation budgets
- approved asset-reference actions such as `copy_asset_reference`, `map_texture`, and `map_sound`
- planned no-world-mutation task definitions and apply-plan summary
- budget gates for media, manual review, wall-clock, node writes, and mapblock churn
- required capabilities, currently `import.assets`
- unsupported-feature summary for rows such as behavior scripts that remain unexecuted
- public-safety flags that keep private paths, raw payloads, copied protected content, embedded asset bytes, behavior-script execution, and live-family-world mutation out of the artifact

The CLI shape is:

```bash
python3 util/ai_native_compat_dry_run.py \
	--asset-promotion-package /path/to/resource-pack-dry-run-report.json \
	--approval /path/to/apply-request.json \
	--output /path/to/asset-reference-promotion-package.json \
	--summary
```

The command fails closed when approval is missing, rights are not `user_supplied`, the dry-run hash does not match the approval request, a source path is private, raw payload or asset byte fields are present, copied protected content is declared, behavior-script execution is approved, the approval includes world-mutating actions, the rollback policy is not `no_world_mutation`, mutation budgets are nonzero, or the target names a family or production world.

This path intentionally does not require adapter smoke or rollback execution evidence because it never queues world mutation. Structure, schematic, and world conversion promotion must continue through the reviewed adapter smoke chain.

## Audit Requirements

Apply must audit:

- Approval accepted.
- Capability checks.
- Source hash or inventory hash verified.
- Task queued.
- Each world-changing step result.
- Budget exceeded.
- Unsafe/protected node skips.
- Rollback metadata created.
- Apply completed, cancelled, failed, or rolled back.

Audit records should include `report_id`, `task_id`, `agent_id`, `owner`, planned action, and bounded status details. They must not include private asset payload bytes.

## Operator Approval

The operator approval UI or CLI must show:

- Source class and redacted source id.
- Dry-run risk level.
- Unsupported features.
- Planned actions selected for apply.
- Estimated mutation cost.
- Requested budgets.
- Rollback policy.
- Confirmation that assets remain operator-supplied.

Apply should require an explicit confirmation token or command flag. Interactive defaults should prefer no mutation.

## Safety Gates

Apply must stop before mutation when:

- The report is invalid.
- The report mode is not `dry_run`.
- Required safety flags are not true.
- `import.assets` is missing.
- The source reference cannot be verified.
- Approved actions are missing from the report.
- Budgets are exceeded.
- Rollback metadata cannot be written.
- Protected areas or hazardous nodes block a safe world operation.

## Apply Summary

Every apply run emits a summary with:

- `apply_id`
- `report_id`
- `status`
- `approved_actions`
- `queued_tasks`
- `running_tasks`
- `completed_tasks`
- `blocked_tasks`
- `mutation_cost_actual`
- `rollback_records`
- `audit_record_count`
- `operator_next_actions`

This summary is separate from the dry-run report so the dry-run artifact remains a reproducible pre-approval record.

## Implementation Order

1. Add apply request and summary schemas.
2. Add a local `--apply-plan` command that validates approvals but does not mutate.
3. Map approved planned actions into task definitions.
4. Add media/entity staging tasks with no mapblock writes.
5. Add structure placement only after rollback metadata and safe world operations are covered by tests.
6. Add reviewed adapter apply smoke for disposable staging worlds before broadening supported structure formats.
7. Add operator review for adapter smoke manifests before broadening supported structure formats.
8. Add the first public-safe structure format adapter behind operator review before broader schematic or world conversion support.
9. Add a reviewed public-safe structure promotion package before broader schematic or world conversion support.
10. Add a public-safe schematic preflight adapter behind the same promotion chain before broader schematic or world conversion support.
11. Add a reviewed no-mutation asset-reference promotion package for user-owned resource-pack dry runs before asset staging or media-copy support.

This order keeps compatibility import aligned with the fork strategy: AI-native runtime first, compatibility automation second, world mutation last.

## Current Apply-Plan Command

The first implementation is a no-mutation planning command in `util/ai_native_compat_dry_run.py`:

```bash
python3 util/ai_native_compat_dry_run.py \
	--apply-plan /path/to/dry-run-report.json \
	--approval /path/to/apply-request.json \
	--output /path/to/apply-summary.json
```

This command:

- Validates the dry-run report.
- Requires explicit approval request JSON.
- Rejects missing approval actions, budgets, rollback policy, and unknown planned action references.
- Verifies the approved action list against the dry-run report.
- Validates approved `import_structure` actions against node-write, mapblock-churn, manual-review, wall-clock, and rollback budgets.
- Requires staging plus `manifest_only` or `snapshot` rollback policy before a structure handoff can be defined.
- Allows `chunked` rollback policy for reviewed structure actions that need bounded multi-step apply and rollback execution.
- Emits inert task definitions that preserve calibrated structure cost, redacted source provenance, required `import.assets`/world capabilities, and `mutation_enabled = false`.
- Marks approved `import_structure` definitions with staged runtime entrypoints such as `core.ai_import_ops.define_structure_apply_task` and `core.ai_import_ops.define_chunked_structure_apply_task`.
- Emits an apply summary with `status = planned`.

The command does not queue runnable world-write steps or mutate a world.
- Leaves the dry-run report unchanged.
- Copies no assets and performs no world mutation.

The command is intentionally not an apply executor.

## Current Task Definition Mapper

`build_apply_task_definitions(report, request)` maps approved dry-run planned actions to reviewable task definition records. The records are inert: they are not queued through `core.queue_ai_task`, they contain no executable steps, and they do not copy assets or write to a world.

Each generated task definition includes:

- `task_id`, `agent_id`, `owner`, and mapped task `label`.
- `required_capabilities`, including `import.assets`.
- Operator-supplied task budget values plus `max_steps_per_step = 1`.
- `mutation_class` and `requires_safe_world_ops`.
- Rollback policy and metadata requirements.
- Source planned-action metadata for review.
- For synthetic structure-adapter actions, a `staged_apply` block with reviewed placements, chunk size/count, staging target, `core.ai_import_ops.define_chunked_structure_apply_task` when chunking is required, `core.ai_import_ops.plan_structure_rollback`, and `core.ai_import_ops.queue_chunked_structure_rollback_task`.

`import_structure` maps to `compat.structure.place`, has `mutation_class = world_mutating`, and sets `requires_safe_world_ops = true`. Apply-plan output remains definition-only, but the runtime now exposes `core.ai_import_ops.define_structure_apply_task` and `core.ai_import_ops.define_chunked_structure_apply_task` for staged execution in disposable worlds.

## Current Structure Runtime Executor

`core.ai_import_ops.define_structure_apply_task(def)` creates a queueable staged structure apply task for synthetic or operator-reviewed structure placements. `core.ai_import_ops.define_chunked_structure_apply_task(def)` slices the same placement list into bounded task steps. This is the first mutating compatibility path and is intentionally narrow.

Required runtime gates:

- The import agent must have `import.assets`, `world.place`, and `world.batch`.
- `explicit_approval = true`.
- The target world must be staging-only.
- `allow_mutation = true`.
- Rollback policy must be `manifest_only`, `manifest`, `chunked`, or `snapshot`.
- Rollback metadata must persist before any node write.
- `max_node_writes_total`, `max_node_writes_per_step`, `max_mapblock_churn_total`, and the task queue wall-clock budget must be explicit and enforced.

Execution calls `core.run_ai_world_mutation_with_rollback`, then places nodes through `core.ai_world_ops.batch_place`. Failed rollback persistence blocks before mutation. Budget failures block before rollback and before mutation. Protected-area or safe-world-op failures can persist rollback metadata first, then block with `changed = 0`.

Chunked execution writes one rollback record per chunk before that chunk's node writes. Each chunk record carries `chunk_index`, `chunk_count`, `first_position_index`, and `position_count`. If a later chunk blocks, prior successful chunks and rollback records remain available for operator review.

`core.ai_import_ops.plan_structure_rollback(options)` reads persisted rollback chunk references through `core.ai_rollback_storage.inspect` and returns a no-mutation rollback plan. It reports inspected records, missing records, chunk metadata, planned node-write count, and mapblock churn.

`core.ai_import_ops.queue_chunked_structure_rollback_task(def)` turns reviewed rollback records into bounded rollback execution. It requires `rollback.execute`, `admin.override`, explicit approval, staging, `allow_mutation = true`, rollback policy, write/churn budgets, and rollback-of-rollback metadata before it mutates the world.

`core.ai_import_ops.build_apply_summary(options)` inspects queued runtime task ids and separates `queued_tasks`, `running_tasks`, `completed_tasks`, and `blocked_tasks`. It reports actual node writes, mapblock churn, elapsed runtime, rollback records, audit count, and keeps `assets_remain_operator_supplied = true` plus `dry_run_report_unchanged = true`.

This executor is for disposable staging worlds and reviewed synthetic or public-safe adapter payloads only. Showcase worlds, private family-server content, copied Minecraft assets, secrets, and local paths remain outside the fork.
