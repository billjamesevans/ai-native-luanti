# AI Runtime Game Profile

This is the production-like, player-ready alpha game profile for AI-native runtime checks and early agent playtesting.

It intentionally ships only a tiny base mod for mapgen aliases. It includes no private content, copied media, provider configuration, or world data. Synthetic smoke and benchmark helper modules are disabled by default and require explicit dev/test settings before they load or register player-facing commands.

The base mod also declares `capability_profile = "clean"` for the first-party agent capability policy. It grants bounded world, entity, task, and model-adapter capabilities, and excludes privileged operator/import/player-combat grants.

Default rollback storage is enabled for this profile so rollback-backed build and repair commands can persist local rollback metadata before mutating a disposable world.

Runtime unit tests, synthetic smoke scenarios, and benchmark fixtures stay outside this profile. Use this profile for disposable local worlds and future low-power proving-ground checks after the one-command verification harness passes.
