# Compatibility Apply Phase

Status: phase-two design slice for issue #19

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
- `budget`: node-write, media, entity, wall-clock, and manual-review limits.
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

This order keeps compatibility import aligned with the fork strategy: AI-native runtime first, compatibility automation second, world mutation last.
