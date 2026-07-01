# OpenRealm Advantage Kit

A working prototype for an **AI-native voxel world creator** built around the OpenRealm/Nova product idea.

This package is designed to give OpenRealm a real technical advantage early:

- Prompt -> structured world recipe
- Recipe -> safe, auditable plan
- Plan -> preview page, manifest, and generated Luanti mod
- All mutation is approval-oriented, bounded, and rollback-aware
- The AI layer never writes arbitrary Lua directly

The core design principle is simple:

> Nova may propose. OpenRealm validates. Luanti mutates only through safe generated runtime code.

## Why this matters

Most "AI game creation" demos jump directly from text to untrusted code. This kit creates a safer product loop:

1. Parse intent from a user prompt.
2. Convert intent to a data-only OpenRealm Recipe.
3. Validate identifiers, node names, budgets, structures, and unsafe text.
4. Generate a Luanti mod from trusted templates.
5. Emit a preview and approval artifact before anything runs in-world.
6. Build with rollback metadata and an audit trail.

That creates a defensible OpenRealm identity: **AI-native creation with guardrails, previews, and ownership**.

## Quick start

```bash
cd openrealm_advantage_kit
python -m openrealm_creator_kernel.cli demo --out out/demo
python -m unittest discover tests
```

Generate a Luanti mod from a prompt:

```bash
python -m openrealm_creator_kernel.cli generate \
  "Add a new ore called moonstone that spawns below level -200 and crafts a glowing sword" \
  --out out/moonstone
```

Preview only:

```bash
python -m openrealm_creator_kernel.cli plan \
  "Build a cozy lakeside village with floating lanterns" \
  --out out/village
```

The generated output includes:

- `openrealm_plan.json` - canonical safe plan
- `preview.html` - human-readable approval preview
- `generated_luanti_mod/` - installable Luanti mod
- `openrealm_package.zip` - packaged mod bundle
- `audit_manifest.json` - provenance and safety metadata

## Install generated mod in Luanti

Copy the generated mod folder into a Luanti game or world mods directory, for example:

```bash
cp -R out/moonstone/generated_luanti_mod/openrealm_moonstone \
  ~/.minetest/mods/openrealm_moonstone
```

Then enable the mod for a disposable world using the OpenRealm `ai_runtime`
profile first. The generated `/or_build` command fails closed if the AI runtime
import task queue is not available.

Inside Luanti, the generated mod registers a safe preview command and queued
build command where applicable:

```text
/or_preview
/or_build <structure_name>
/or_rollback_last
```

## Project layout

```text
openrealm_creator_kernel/   Python package: parser, planner, validator, generator, CLI
lua_runtime/                Optional reusable runtime concept mod for Luanti
web_demo/                   Static concept UI for presenting the creator flow
docs/                       Product/architecture docs
examples/                   Golden prompts and generated sample output
tests/                      Stdlib unit tests
```

## The advantage

This is not trying to be a full launcher. It is the strategic core:

**A safe creator kernel that can later plug into a launcher, server host, ContentDB workflow, and Nova assistant.**

The generated code is intentionally boring in the right places: deterministic
templates, small APIs, explicit manifests, runtime task-queue handoff, and
validation gates. That is what lets the AI experience feel magical without
making the engine unsafe.

## Added local API and brand package

This package also includes:

- `python -m openrealm_creator_kernel.cli serve --port 8787` for a dependency-free local HTTP API.
- `studio/index.html` for a polished offline Creator Studio prototype.
- `assets/brand/` with OpenRealm brand boards, launcher mockups, roadmap, AI architecture, and creator-flow visuals.
- `README_FIRST.md` with the recommended first integration path.
- `VALIDATION_REPORT.md` with the validation commands used for this bundle.

The goal is to give OpenRealm a working advantage immediately: a safe creator kernel, a demoable studio UI, generated Luanti mod output, and strong product visuals in one package.
