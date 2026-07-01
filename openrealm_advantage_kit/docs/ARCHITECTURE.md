# Architecture

## Design principle

Nova is a planner. OpenRealm is the safety boundary. Luanti is the world authority.

```text
Player prompt
  -> Nova intent/parser
  -> OpenRealm recipe model
  -> validator
  -> preview/approval artifacts
  -> deterministic Luanti templates
  -> task/audit/rollback runtime
```

## Why not direct code generation?

Direct code generation is powerful but unsafe. A model can accidentally produce file access, network calls, destructive world edits, or dependency confusion. This kernel uses a data-first design:

- AI proposes structured data.
- Identifiers are sanitized.
- Node/write budgets are enforced.
- External node prefixes are allowlisted.
- Generated Lua comes from deterministic templates.
- In-world mutation commands check protected areas and store rollback metadata.

## Components

### Parser

A simple deterministic parser for early golden prompts. Later, a model can fill the same `Intent` structure.

### Planner

Creates an `OpenRealmPlan` with nodes, craft items, tools, recipes, ores, structures, and world recipe metadata.

### Safety validator

Checks names, budgets, forbidden tokens, node prefixes, structure sizes, and mutation policy.

### Luanti generator

Emits:

- `mod.conf`
- `init.lua`
- placeholder PNG textures
- `openrealm_plan.json`
- `README.md`

### Preview generator

Creates a standalone `preview.html` for review and approval.

### Packager

Creates a distributable zip with audit metadata.

## Future integration

- Replace deterministic parser with an LLM adapter that emits the same `Intent` or `OpenRealmPlan` schema.
- Add a graphical preview in the launcher.
- Route generated plans into the existing AI runtime task queue.
- Add ContentDB metadata and AI disclosure fields.
- Add multiplayer approval roles for parents, teachers, and server owners.
