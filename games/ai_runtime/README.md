# AI Runtime Game Profile

This is the production-like, player-ready alpha game profile for AI-native runtime checks and early agent playtesting.

It intentionally ships only tiny first-party mods for mapgen aliases and an
optional Agents SDK HTTP handle bridge. It includes no private content, copied
media, provider configuration, or world data. Synthetic smoke, benchmark, and
model-adapter probe helper modules are disabled by default and require
explicit dev/test settings before they load or register player-facing commands.

The base mod also declares `capability_profile = "clean"` for the first-party agent capability policy. It grants bounded world, entity, task, and model-adapter capabilities, and excludes privileged operator/import/player-combat grants. It registers a tiny code-only `ai_runtime_base:helper` entity for normal `/nova follow` and `/nova come` playtesting, keeping the separate demo benchmark helper disabled by default.

The first-party plugin splits `/nova` behavior into Builder, Repair, Guide,
Defender, and Importer role agents. In this clean profile, Builder, Repair,
and Guide can receive only their relevant clean grants; Defender does not get
`combat.defend`, and Importer does not get `import.assets` by default.
The profile also registers simple code-only fire and TNT nodes so `/nova build
a fire` and `/nova build a wall of tnt` exercise the real build planner,
approval, rollback, and trace paths without requiring private content or a
larger game package. The prompt-eval verifier treats these as exact behavior
contracts: fire must preview exactly one node write, and the default TNT wall
must preview exactly twelve node writes.
Ambiguous build prompts such as `/nova build a small shelter` route through the
agentic build planner, which presents bounded executable candidates, can ask the
Agents SDK sidecar for guidance, and still requires approval before mutation.

Default rollback storage is enabled for this profile so rollback-backed build and repair commands can persist local rollback metadata before mutating a disposable world.

The clean profile expects the core operator status and receipt-gated task-control commands to be present as product runtime surfaces. They are server-privileged, bounded, public-safe, and separate from synthetic smoke or benchmark commands.

The `ai_runtime_agents_sdk_bridge` mod only hands Luanti's HTTP API handle to
the builtin Agents SDK adapter when a server explicitly enables that adapter.
Server operators must still grant HTTP access with `secure.http_mods` and run a
loopback sidecar with server-local secrets outside the repository. The sidecar
returns bounded model-adapter responses; the engine remains the only world
mutation authority.

Runtime unit tests, synthetic smoke scenarios, and benchmark fixtures stay outside this profile. Use this profile for disposable local worlds and future low-power proving-ground checks after the one-command verification harness passes.
