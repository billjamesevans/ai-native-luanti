# OpenRealm Product Roadmap

## Phase 0: Public Identity Reset

Goal: make the repo instantly understandable.

Ship:

- root README that presents OpenRealm, Nova, Luminara, and the AI-native
  creator loop;
- product docs under `doc/product/`;
- architecture diagram or screenshot placeholder;
- "what works today" and "try this in five minutes" sections;
- explicit "built on Luanti" and license notes.

Exit gate:

- a new visitor can explain the project in one sentence without reading runtime
  internals.

## Phase 1: Creator Loop MVP

Goal: make the AI magic obvious and reliable.

Ship:

- prompt -> plan -> preview -> approve -> apply -> audit -> rollback loop;
- visible plan details: build kind, material, bounds, writes, location, hazards,
  rollback availability;
- approve/edit/cancel controls;
- task progress and result summaries;
- request/response logs tied to player-facing outcomes;
- quality gate that fails when golden prompts regress.

Exit gate:

- all golden prompts pass locally and on the Raspberry Pi fork test server.

Current Pi gate evidence:

- 2026-07-01 side-by-side fork deploy advanced the Pi test lane to
  `d375eeee7`.
- `TestAIRuntime` passed on the Pi before service restart.
- family service stayed active on UDP `30000`.
- fork test service restarted active on UDP `30001`.
- Agents SDK sidecar stayed active on loopback TCP `8766`.
- quality gate passed with live prompt eval `pass`, compatibility import staging
  pilot `pass`, `0` violations, and `0` attention items.
- `openrealm_demo` is discoverable in the Pi build alongside `ai_runtime` and
  `devtest`.
- `Nova, options` is now a player-loop review path for pending build choices
  and selected candidate reasoning without provider calls or world mutation.
  Its executable candidates carry `openrealm.plan.v1` safety contracts.

## Phase 2: Luminara Creator Playground

Goal: give normal users a complete first experience without building a full
survival game first.

Ship:

- separate player-facing `games/openrealm_demo` or `games/luminara` profile;
- starter world with good lighting, simple materials, signs/tutorial flow, and
  no private/proprietary assets;
- Nova onboarding;
- rollback practice area;
- ten guided prompt moments;
- screenshots and a demo capture path.

Exit gate:

- a new player can launch the world, use Nova successfully, and undo a build
  without reading developer docs.

## Phase 3: AI Mod And World Generator

Goal: turn creation into the flagship feature.

Ship:

- template-based generated mods for nodes, ores, tools, recipes, simple mobs,
  biomes, structures, and quests;
- generated `mod.conf`, manifest, tests, AI disclosure metadata, and uninstall
  path;
- disposable-world validation before install;
- blocked execution for raw arbitrary Lua that has not passed validation.

Exit gate:

- a prompt like "add moonstone ore below -200 and a glowing sword recipe"
  produces a reviewed, testable, removable local package.

## Phase 4: Shareable World Packages

Goal: let players publish creations.

Ship:

- world recipe JSON;
- generated mod files;
- dependency manifest;
- screenshots;
- engine/version compatibility notes;
- AI disclosure and provenance;
- rollback/uninstall metadata.

Exit gate:

- a created world package can be exported, imported into a clean checkout, and
  replayed without private paths or credentials.

## Phase 5: One-Click Private Multiplayer

Goal: make creation social for families, schools, youth groups, and friends.

Ship:

- invite-only world flow;
- roles and moderation defaults;
- snapshots and restore points;
- no-port-forwarding host path;
- parent/teacher controls;
- backup-first server operations.

Exit gate:

- a non-developer can host a private creator world and recover from a bad build.

## Phase 6: Consumer Launcher

Goal: make OpenRealm approachable.

Ship:

- home screen with Play, Create, Host, Browse, Continue, and Share;
- OpenRealm/Luminara visual identity;
- one-click ContentDB package flow;
- known-good modpack profiles;
- dependency and compatibility reports.

Exit gate:

- the launcher exposes the creator loop without requiring command-line setup.

## Phase 7: Public Alpha Ecosystem

Goal: turn the fork into a contributor-friendly platform.

Ship:

- templates and plugin API docs;
- ContentDB integration;
- pre-PR verifier;
- sample packs;
- issue templates and contributor path;
- benchmark evidence for local Mac and low-power Pi lanes.

Exit gate:

- outside contributors can build creator features without touching private
  family-server content.
