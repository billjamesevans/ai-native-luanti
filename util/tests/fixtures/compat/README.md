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

The reporter may inventory these files, but tests must keep them small and free
of binary media payloads.
