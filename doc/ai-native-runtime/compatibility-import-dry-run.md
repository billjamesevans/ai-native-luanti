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
- `schematic`: user-owned schematic preflight metadata, without raw schematic/NBT payloads.
- `structure`: user-owned structure exports.
- `world`: world metadata or conversion inventory.
- `luanti_mod`: Luanti mod metadata such as `mod.conf` and dependency declarations.
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
- A metadata-only public-safe structure or schematic preflight JSON file.
- A Luanti mod metadata folder with `mod.conf` and optional dependency files.

The report may include redacted source names and content hashes, but it should not copy source payloads into the fork.

## Report Contract

The machine-readable report schema lives at:

- [`schemas/compatibility-dry-run-report.schema.json`](schemas/compatibility-dry-run-report.schema.json)
- [`schemas/compatibility-inventory-discovery-report.schema.json`](schemas/compatibility-inventory-discovery-report.schema.json)

A synthetic Bedrock-style example lives at:

- [`examples/compatibility-dry-run-report.example.json`](examples/compatibility-dry-run-report.example.json)
- [`examples/compatibility-inventory-discovery-report.example.json`](examples/compatibility-inventory-discovery-report.example.json)

Additional public-safe examples cover the current structure and Luanti-mod lanes:

- [`examples/compatibility-public-schematic-report.example.json`](examples/compatibility-public-schematic-report.example.json)
- [`examples/compatibility-luanti-mod-report.example.json`](examples/compatibility-luanti-mod-report.example.json)

Every report has:

- `report_version`: integer schema version.
- `mode`: always `dry_run` for this phase.
- `generated_at`: ISO 8601 timestamp.
- `source`: classified source metadata and redacted path policy.
- `source.inventory`: redacted per-item inventory with classification, reason, size, and required runtime capabilities.
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

Inventory classification values:

- `mapped`: metadata or user-owned asset references can be mapped later without copying payloads in dry run.
- `skipped`: intentionally omitted from apply planning.
- `blocked`: detected and potentially useful, but requires operator review, approval, budgets, rollback policy, or manual mapping before apply.
- `unsupported`: detected but not supported by the current importer.
- `unknown`: listed but not classified strongly enough for apply planning.

Each inventory row must use a package-relative `source_path`, not an absolute local path, and must include `required_capabilities` so future apply planning remains aligned with runtime capability gates.

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
- `private_reference_not_imported`
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

Each action should include an estimated `mutation_cost` with counts such as node writes, mapblock churn, media files, entity definitions, or manual review items.

## Public-Safe Structure Adapters

The structure adapters are intentionally narrow and metadata-first. They read
reviewable JSON fixtures and emit dry-run reports before any apply task exists.

The synthetic test adapter reads a JSON fixture with:

- `fixture_kind: ai_native_synthetic_structure`
- `fixture_version: 1`
- `name`
- `recommended_chunk_size`
- `palette`: local fixture aliases mapped to Luanti node names such as `ai_runtime_test:stone`
- `placements`: relative `{x,y,z}` positions plus `node` or `node_name`, with optional `param1` and `param2`
- `unsupported_fields`: optional review-only rows for fields such as entities or block entities

The public-safe structure adapter reads a user-supplied, rights-confirmed JSON
fixture with `format_kind: ai_native_public_structure` and
`structure_format: ai_native_structure_v1`. The schematic preflight adapter reads
`format_kind: ai_native_public_schematic_preflight` with
`schematic_format: ai_native_schematic_preflight_v1` and `payload_policy:
metadata_only`. These formats contain reviewed palette, dimension, placement,
and unsupported-field metadata only; they reject raw schematics, NBT payloads,
private source paths, family-world coordinates, and copied protected content.

The adapter output remains a dry-run report. It adds an `import_structure`
planned action with a `structure_adapter` payload containing reviewed
placements, placement count, mapblock-churn estimate, and chunking guidance. It
does not queue tasks, copy assets, parse proprietary structure payloads, execute
behavior, or mutate a world.

Unsupported fixture fields become explicit `unsupported_features` rows, so the operator can review what was skipped before any apply request exists.

## Structure Cost Calibration

Structure sources are still dry-run only. The reporter must not parse proprietary structure payloads, copy structures into the fork, or place nodes in a world during calibration.

For public-safe synthetic adapter fixtures, structure cost is computed from reviewed synthetic placements. For opaque schematic or structure files, cost remains conservatively estimated from file inventory metadata:

- `node_writes`: conservative estimated placed-node count.
- `mapblock_churn`: estimated count of touched mapblocks.
- `manual_review_items`: placement and palette review items that an operator must approve before apply.

The `structures` section exposes `estimated_node_writes`, `estimated_mapblock_churn`, and `manual_review_items`. The `import_structure` planned action repeats the calibrated cost in its `mutation_cost`.

Use the dry-run reporter as the local structure benchmark:

```sh
python3 util/ai_native_compat_dry_run.py \
  util/tests/fixtures/compat/structure/example.mcstructure \
  --output local/benchmarks/compat-structure-cost-report.json \
  --summary
```

The output is ignored local evidence. It must remain public-safe: no proprietary structures, no family worlds, no asset payloads, and no world mutation.

## Batch Inventory Queue

Operators can scan a folder of user-owned sources into a single review queue:

```sh
python3 util/ai_native_compat_dry_run.py \
  --batch-inventory /path/to/user-owned-import-sources \
  --reports-dir local/compat-reports \
  --output local/compat-batch-queue.json \
  --summary
```

The batch scanner inspects immediate child files and folders, runs the normal
dry-run reporter for each source, writes per-source dry-run reports under
`--reports-dir`, and emits a bounded queue with relative `report_path` values.
Queue rows include source class, license status, risk level, inventory counts,
planned-action counts, required capabilities, content hash, estimated mutation
cost, and one of these review statuses:

- `mappable`: metadata or user-owned references can be mapped later.
- `skippable`: no useful import action was found.
- `blocked`: the source could not be classified safely.
- `manual_review`: the source has blocked entries, unsupported features,
  structure placement, or other review work before apply.

Batch inventory is still dry-run-only. It does not copy assets, execute apply,
queue runtime tasks, mutate worlds, or bypass approval, rollback, write-budget,
and staging-world gates.

## Import Inventory Discovery

The public-safe discovery report turns a batch scan into a parity-ready import
preview artifact:

```sh
python3 util/ai_native_compat_dry_run.py \
  --inventory-discovery /path/to/user-owned-import-sources \
  --reports-dir local/compat-reports \
  --output local/benchmarks/compatibility-import-inventory-discovery-report.json \
  --summary
```

The report classifies source-level and inventory-level content as `supported`,
`partial`, `unsupported`, `skipped`, or `blocked`. It accepts user-owned Java and
Bedrock pack metadata, Luanti mods, metadata-only structure/schematic preflights,
and world-export metadata. It records source class counts, content-hash
provenance, mapped/skipped/blocked/unsupported dry-run classifications,
required capabilities, and planned actions that can later become
`core.ai_import_ops` queued work. It also emits a `promotion_queue` that turns
each source into one explicit next step:

- `asset_reference_promotion_package`: Java or Bedrock resource-pack metadata
  can be packaged for no-world-mutation asset-reference review.
- `structure_import_promotion_package`: public-safe structure or schematic
  preflights need adapter smoke, review, approval, rollback metadata, and
  disposable-staging evidence before promotion.
- `luanti_mod_metadata_review`: mapped Luanti mod metadata is ready for manual
  review, but no runtime registration package is implied yet.
- `world_metadata_deferral`: world exports remain metadata-only and blocked from
  conversion apply until a separate safe conversion design exists.
- `blocked_source`: classification or privacy blockers must be resolved before
  promotion.

The promotion queue remains metadata-and-reference-only: private-looking source
names are redacted and blocked, asset bytes are never embedded, promotion
packages do not execute world mutation, and whole-world imports stay blocked
until a future conversion path is reviewed.

When the report is written at
`local/benchmarks/compatibility-import-inventory-discovery-report.json`, the
Minecraft-parity harness can use it to clear the compatibility-import inventory
action without claiming proprietary Minecraft benchmark evidence.

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
