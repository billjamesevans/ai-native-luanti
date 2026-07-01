# Suggested GitHub Issues

## Issue 1: Add OpenRealm Plan schema as product contract

Create a committed `doc/openrealm-plan-schema.md` and JSON schema for prompt-created plans.

Acceptance:

- schema includes nodes, craft items, tools, recipes, ores, structures, approval steps, AI disclosure, provenance, and budgets;
- validator rejects unsafe identifiers, over-budget structures, raw code payloads, and missing rollback policy.

## Issue 2: Add Nova Creator Mode preview

Create an in-game or launcher preview screen for OpenRealm plans.

Acceptance:

- shows planned node writes, node definitions, structures, and rollback policy;
- supports approve, request changes, and discard;
- stores approval id before mutation.

## Issue 3: Route generated structures through AI runtime task queue

Replace direct generated `/or_build` mutation with queued runtime tasks.

Status: initial generated-mod handoff is implemented. New CLI-generated
structures queue chunked `compat_import` tasks through `core.ai_import_ops` and
fail closed when the runtime queue is unavailable.

Acceptance:

- all placement operations use safe world operations;
- every task has audit and rollback metadata;
- cancellation works mid-task;
- remaining work: expose first-class in-game approval and task-control UI for generated OpenRealm tasks.

## Issue 4: Add golden prompt evaluation suite

Prompts:

- build a campfire;
- build a stone bridge;
- build a cozy lakeside village;
- add moonstone ore and glowing sword;
- make a Glacier National Park biome recipe.

Acceptance:

- each prompt produces a valid plan;
- each plan validates;
- generated mod passes template safety scan.
