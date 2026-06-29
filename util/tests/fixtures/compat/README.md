# Synthetic Compatibility Fixtures

These fixtures are original, minimal metadata-only inputs for the AI-native
compatibility dry-run reporter tests.

Rules:

- Synthetic files only.
- No real Minecraft assets.
- No user-owned family-server assets.
- No marketplace or downloaded pack payloads.
- Placeholder behavior files are tiny text fixtures used only to exercise
  unsupported-feature reporting.
- Bedrock asset-pack fixtures are metadata-only JSON fixtures used to exercise
  model/reference promotion without texture, sound, or binary media payloads.
- Placeholder structure, world, and mod metadata files are tiny synthetic
  fixtures used only to exercise classifier paths.
- Public structure fixtures are tiny original `ai_native_structure_v1` JSON
  files used to exercise the reviewed structure adapter path. They do not
  contain copied Minecraft, marketplace, family-world, or showcase payloads.
- Public schematic preflight fixtures are tiny original
  `ai_native_schematic_preflight_v1` JSON files. They contain metadata-only
  estimated placements and explicit unsupported/manual-review rows, never raw
  schematic/NBT payloads, copied protected content, private source paths, or
  family-world coordinates.

The reporter may inventory these files, but tests must keep them small and free
  of binary media payloads.
