# Compatibility Import Dry-Run Reports

Status: phase-two design slice for issue #8

## Purpose

Compatibility import starts as reporting, not mutation. A dry run inspects user-supplied Minecraft-like packs, schematics, or world metadata and produces a compatibility report before the fork copies assets, writes mapblocks, registers nodes, or changes a world.

The goal is to make imports explicit, reviewable, and legally safe. The fork should help a server operator understand what can be imported, what cannot, what needs manual mapping, and how expensive the resulting world changes may be.

## Non-Goals

- Do not commit proprietary assets, generated pack contents, or user-owned worlds to the engine fork.
- Do not ship Mojang server code, assets, trademarks, or behavior implementations.
- Do not mutate a Luanti world during the dry-run phase.
- Do not silently drop unsupported features.
- Do not treat compatibility as an all-or-nothing pass/fail result.

## Supported Source Classes

The dry-run reporter should classify source material into these initial classes:

- `java_resource_pack`: Java-style resource pack metadata such as `pack.mcmeta`, textures, sounds, models, and language files.
- `bedrock_resource_pack`: Bedrock-style resource pack metadata such as `manifest.json`, textures, sounds, models, and client entity descriptors.
- `bedrock_behavior_pack`: Bedrock-style behavior metadata such as entities, loot tables, recipes, and scripts.
- `structure`: user-owned schematic or structure exports.
- `world`: world metadata or conversion inventory.
- `unknown`: any source that can be listed but not classified safely.

The first implementation can parse metadata and file inventories without interpreting every asset format.

## Fixture Policy

Dry-run fixtures must live outside the engine core unless they are synthetic, minimal, and license-clear.

Public fork fixtures may include:

- Tiny hand-authored metadata files created only for tests.
- Empty placeholder files where only file presence matters.
- Redacted inventories containing file names, hashes, sizes, and feature tags.

Public fork fixtures must not include:

- Real Minecraft assets.
- User-owned pack contents.
- Private family-server worlds.
- Downloaded marketplace content.
- Generated art that is not explicitly licensed for the repo.

Operator-supplied fixtures should be referenced through a local path or environment variable such as:

```text
AI_NATIVE_IMPORT_FIXTURE_ROOT=/path/to/user-owned-fixtures
```

Current useful fixture types outside the engine core are:

- A Bedrock-style folder with `manifest.json`.
- A Java-style resource pack folder with `pack.mcmeta`.
- A compressed Bedrock `.mcpack`.

The report may include redacted source names and content hashes, but it should not copy source payloads into the fork.

## Report Contract

The machine-readable report schema lives at:

- [`schemas/compatibility-dry-run-report.schema.json`](schemas/compatibility-dry-run-report.schema.json)

A synthetic example lives at:

- [`examples/compatibility-dry-run-report.example.json`](examples/compatibility-dry-run-report.example.json)

Every report has:

- `report_version`: integer schema version.
- `mode`: always `dry_run` for this phase.
- `generated_at`: ISO 8601 timestamp.
- `source`: classified source metadata and redacted path policy.
- `summary`: totals, estimated mutation cost, risk level, and support counts.
- `sections`: per-domain compatibility sections for assets, behavior, structures, or world metadata.
- `unsupported_features`: explicit reasons for unsupported or partially supported items.
- `planned_actions`: import actions that would run in a later apply phase.
- `safety`: proof that the dry run did not copy assets or mutate a world.

## Compatibility Result Vocabulary

Result status values:

- `supported`: can be imported automatically within known limits.
- `partial`: can be imported with warnings, lossy mapping, or manual follow-up.
- `unsupported`: cannot be imported by the current fork.
- `skipped`: intentionally ignored because it is out of scope or blocked by policy.
- `unknown`: detected but not understood well enough to classify.

Risk levels:

- `low`: metadata-only or small asset mapping.
- `medium`: bounded world changes, known lossy mappings, or manual review required.
- `high`: large world mutation, script behavior, entity AI, redstone-like logic, or protected content risk.

## Unsupported Feature Reporting

Unsupported features must be first-class report rows, not buried in prose. Each row should include:

- `feature`: stable feature identifier.
- `source_path`: redacted relative path or package-local path.
- `status`: `partial`, `unsupported`, `skipped`, or `unknown`.
- `reason`: machine-readable reason.
- `severity`: `info`, `warning`, or `error`.
- `message`: short operator-facing explanation.
- `recommendation`: next action for the operator or importer.

Initial reasons:

- `protected_asset_policy`
- `missing_mapping`
- `unsupported_format`
- `behavior_script_not_supported`
- `entity_ai_not_supported`
- `world_format_not_supported`
- `requires_manual_review`
- `too_large_for_budget`

## Planned Actions

Dry-run reports should estimate the work an apply phase would queue later. Planned actions are not executed during dry run.

Initial action types:

- `copy_asset_reference`: reference a user-owned asset without committing it to the fork.
- `map_texture`: map a source texture to a Luanti texture target.
- `map_sound`: map a source sound to a Luanti sound target.
- `register_node_alias`: propose node or item aliases.
- `register_entity_stub`: create a placeholder entity definition for manual completion.
- `import_structure`: estimate structure placement or conversion.
- `skip_feature`: record an explicit skip.

Each action should include an estimated `mutation_cost` with counts such as node writes, media files, entity definitions, or manual review items.

## Safety Requirements

A valid dry-run report must state:

- `no_assets_copied: true`
- `no_world_mutation: true`
- `source_paths_redacted: true`
- `user_rights_required: true`

The importer should fail closed if it cannot prove those flags.

## Relationship To AI Runtime

Compatibility import becomes useful because the runtime can later assign bounded work to agents. The dry-run phase should therefore produce planned actions that can become `core.queue_ai_task` steps, require `import.assets` capability, and reuse safe world operations for any eventual apply phase.

This keeps compatibility aligned with the fork strategy: AI-native runtime first, import automation second.
