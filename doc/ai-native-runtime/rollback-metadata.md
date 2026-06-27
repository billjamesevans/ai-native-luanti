# Rollback Metadata

Status: contract slice for issue #33

## Purpose

Repair, build, and compatibility-import tasks must not mutate a world until they can record enough rollback metadata to reverse or audit the change. This contract defines the minimum rollback record needed before later issues add mutating repair or build execution.

Issue #42 adds a rollback writer helper, but does not add new world-mutating plugin behavior by itself.

## Schema And Examples

The machine-readable rollback record schema lives at:

- [`schemas/ai-runtime-rollback-record.schema.json`](schemas/ai-runtime-rollback-record.schema.json)

Synthetic examples live at:

- [`examples/rollback-record.example.json`](examples/rollback-record.example.json)
- [`examples/rollback-record-chunked.example.json`](examples/rollback-record-chunked.example.json)

## Required Record Fields

Each rollback record includes:

- `schema_version`
- `record_id`
- `policy`: `manifest`, `snapshot`, or `chunked`
- `world_id`
- `task_id`
- `agent_id`
- `owner_ref`
- `operation_label`
- `mutation_class`: `repair`, `build`, or `compat_import`
- `bounds`
- `changed_positions`
- `previous_nodes`
- `chunk`
- `created_at`

`previous_nodes` stores the prior node name and param data for every changed position in the record chunk. Node metadata should be referenced by hash or storage reference unless exact metadata is required for a reviewed rollback implementation.

## Runtime Writer API

`core.write_ai_rollback_record(def)` prepares and persists one rollback record before a matching mutation step runs.

Required fields:

- `policy`: `manifest`, `snapshot`, or `chunked`
- `world_id`
- `task_id`
- `agent_id`
- `owner_ref`
- `operation_label`
- `mutation_class`: `repair`, `build`, or `compat_import`
- `positions`: changed positions planned for the next mutation batch
- `get_node`: optional injected node reader; defaults to Luanti node APIs
- `persist_record(record)`: callback that must persist the record and return a storage reference or `{ ok = true, storage_ref = "..." }`

Optional fields:

- `record_id`
- `bounds`; when omitted, bounds are derived from `positions`
- `chunk`
- `created_at`

The helper captures `previous_nodes` before persistence and returns an action result:

- success: `status = "success"`, `reason = "rollback_record_written"`, `rollback_record_id`, `rollback_storage_ref`, and `record`
- failure: `status = "blocked"`, `reason = "rollback_metadata_unavailable"`, and `changed = 0`

`core.run_ai_world_mutation_with_rollback(def, mutate)` wraps the same write path around a mutation callback. If rollback metadata cannot be prepared and persisted, the callback is not called. If the rollback record succeeds, the callback receives `rollback_record`, `rollback_record_id`, `rollback_storage_ref`, `task_id`, `agent_id`, and `owner_ref`; the returned action result is annotated with the rollback references.

## Chunking

Large tasks may split rollback data across multiple records. Each record carries:

- `chunk_index`
- `chunk_count`
- `first_position_index`
- `position_count`

Chunks must be durable before their matching world mutation step runs. A task that cannot write the next rollback chunk must stop before changing the next node batch.

## Failure Behavior

Mutating tasks must fail closed:

1. Validate the rollback policy before queueing mutation work.
2. Prepare the rollback record or chunk for the next planned mutation batch.
3. Persist the rollback metadata.
4. Only then run the matching safe-world-op mutation.

If rollback metadata cannot be written, the task must abort before mutation with:

- `status = "blocked"` or `status = "unsafe"`
- `reason = "rollback_metadata_unavailable"`
- `changed = 0` for the blocked step

The task may keep prior successful chunks and mutations, but it must not discard their rollback records.

## Audit Privacy

Rollback storage may contain positions and previous node names because that data is required to reverse world changes. Audit records should not expose the full rollback payload by default.

Default audit records should keep only:

- rollback record id or storage ref
- task id
- agent id
- owner ref
- mutation class
- chunk index and count
- changed/skipped counts
- status and reason

Audit records must not retain private prompts, player data, asset payload bytes, source asset paths, API keys, or provider request/response bodies by default.

## Dependencies For Mutation Work

Future repair and build mutation issues must depend on this contract and add tests proving:

- rollback metadata is created before mutation
- mutation stops when rollback metadata cannot be persisted
- rollback chunks match the positions actually changed
- audit events reference rollback records without copying private payloads

Until those tests exist, `repair_agent` remains read-only and `build_agent` work should stay at task-definition or no-mutation planning level.

Issue #42 supplies the shared writer and guarded-mutation helper. Issues #43 and #44 must still add plugin-specific tests before repair or build tasks rely on rollback-backed mutation.
