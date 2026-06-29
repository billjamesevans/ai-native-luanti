# Public-Safe Sample Data Policy

Status: required policy for fixtures, examples, benchmark reports, and import
inventory samples committed to the public fork.

## Allowed

Public samples may contain metadata-only fixtures, synthetic node names,
synthetic agent names, public-safe paths, aggregate benchmark counts, schema
examples, and content hashes that cannot reconstruct private assets.

## Not Allowed

Public samples must contain:

- no raw asset payloads
- no private worlds
- no provider prompts
- no API keys or model credentials
- no local home-directory paths
- no private IP addresses or hostnames
- no copied proprietary Minecraft, marketplace, or pack assets
- no family coordinates, player data, screenshots, or private server logs

The names `spacebase`, `themepark`, and `disneyland100` are reserved examples
of private family/server content that must not appear as import payloads,
world content, release assets, or committed sample data.

## Compatibility Fixtures

Compatibility fixtures should describe source class, manifest metadata,
content hashes, planned actions, unsupported capabilities, and safety status.
They should not include texture payloads, model payloads, sound payloads, copied
world regions, or raw NBT/media data.

## Review Rule

Every committed example report or fixture should answer:

- Can a contributor understand the format without private context?
- Can the sample be redistributed with the repository?
- Could the sample reconstruct or identify a private world, prompt, person, or
  asset?

If the third answer is yes, the sample does not belong in the public fork.
