# AI Runtime Game Profile

This is a production-like, public-safe game profile for AI-native runtime operator checks.

It intentionally ships only a tiny base mod for mapgen aliases. It includes no private content, copied media, provider configuration, or world data. The AI runtime command surfaces are loaded by builtin server code, so this profile can host local checks such as `/ai_runtime_smoke` without pulling in test-only gameplay material.

The base mod also declares `capability_profile = "clean"` for the first-party agent capability policy. It grants bounded world, entity, task, and model-adapter capabilities, and excludes privileged operator/import/player-combat grants.

Default rollback storage is enabled for this profile so rollback-backed build and repair commands can persist local rollback metadata before mutating a disposable world.

Use this profile for disposable local worlds and future low-power proving-ground checks after the one-command verification harness passes.
