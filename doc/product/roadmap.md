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
  `907b393b5`.
- Backup: `raspberrypi_luanti_20260701-182811.tgz`
  (`9a0f27c2a7652dc668a7582775c61082614f7d36993b742dbaa3294359f7a39d`).
- `TestAIRuntime` passed on the Pi before service restart.
- family service stayed active on UDP `30000`.
- fork test service restarted active on UDP `30001`.
- Agents SDK sidecar service `ai-native-luanti-agents-sdk-adapter.service`
  stayed active on loopback TCP `8766`.
- memory refresh quality gate passed with live prompt eval `pass`,
  compatibility import staging pilot `pass`, `10/10` required agentic tool cases,
  `0` attention items, and `0` violations. The retained quality gate artifact
  was generated at `2026-07-01T23:34:03Z`.
- request/response log gate passed with `1978` request log entries and `74`
  Nova agent log entries read, `7/7` checked cases passed, and `0`
  violations. The retained request/response artifact was generated at
  `2026-07-01T23:33:36Z`.
- live prompt eval passed `12/12` cases; the OpenRealm golden subset passed
  `9/9`, with `11` model-adapter requests, `11` successes, `0` failures, and
  `0` timeouts. The current live-probe prompt-eval artifact was generated at
  `2026-07-01T23:32:41Z`.
- promoted one-hour low-power Pi evidence passed for `907b393b5` at
  `local/benchmarks/low-power-server/2026-07-01/907b393b5/pi-low-power-evidence.json`;
  target `one-hour`, elapsed `4254.735` seconds, duration met, `13/13`
  iterations passed, service split intact, 2/2 headless synthetic players
  connected/completed, compatibility import staging pilot `pass`, average CPU
  max `84.261%`, max interval CPU `113.667%`, max RSS `77.781 MB`,
  actionable warnings `0`, server log errors `0`, and failure count `0`.
- the live Pi prompt gate now includes `Build a stone bridge`: Nova generated
  and selected `generated_bridge_platform`, preserved `stone` material,
  produced a bounded `6 x 2` platform preview with `12` planned node writes,
  and exposed `inspect_build_site_context`, `recall_build_prompt_memory`,
  `propose_build_option`, `select_build_option`, and `plan_build_actions` in
  the Agents SDK tool trace.
- the live Pi prompt gate now includes `Build a small cabin`: Nova generated
  and selected `generated_prompt_shaped_cabin`, preserved `wood` material,
  produced a bounded `3 x 2 x 2` cabin preview with `10` planned node writes,
  and exposed `recall_build_prompt_memory`, `propose_build_option`,
  `select_build_option`, and `plan_build_actions` in the Agents SDK tool
  trace.
- the live Pi prompt gate now includes `Build a path to that hill`: the model
  proposed `generated_path_platform`, the runtime intent constraint locked the
  final selected candidate to `parsed_request`, preserved `path` intent, and
  produced an `8` node write path preview without letting generated content
  override the player's explicit request.
- the live Pi prompt gate now checks `player_agent_loop`, starting from natural
  chat (`Nova, Build a cozy lakeside village with floating lanterns`), then
  verifying `Nova, options`, `Nova, pending plan`, `Nova, no`, and the
  after-discard `no_pending_approval` block without world mutation.
- the retained live Pi prompt-eval artifact now requires
  `player_agent_loop_review_traces_checked = true`, proving public-safe
  `natural_chat_review` traces for options, pending-plan review, discard, and
  after-discard blocked review turns.
- the retained live Pi quality-gate artifact now also summarizes
  `live_prompt_eval_player_agent_loop_review_traces_checked = true`, so the
  top-level release gate proves normal player conversation review traces.
- the retained live Pi prompt-eval artifact now also requires
  `natural_chat_followup_checked = true`: `Nova, build a fire` followed by
  `Nova, only the fire, nothing else` must carry the previous builder goal and
  new player constraint into the agentic build-planner context, preserve the
  `fire` candidate, require approval, and perform no direct world mutation.
- live sidecar trace summaries now preserve unique required tool names, so
  repeated generated-option retries cannot hide required evidence such as
  `plan_build_actions` from the release gate.
- Agents SDK adapter health reports OpenAI key present, hosted web search
  available, and `world_mutation_authority = luanti`.
- `Nova, options` remains the player-loop review path for pending build choices
  and selected candidate reasoning without provider calls or world mutation.
- Natural chat can now revise an existing pending build preview without starting
  over: `Nova, make it wider` updates dimensions and `Nova, use tnt instead`
  updates material through `edit_plan`, preserving the approval id, returning
  `no_world_mutation = true`, and retaining a public-safe `natural_chat_review`
  trace. The retained live Pi prompt-eval and quality-gate artifacts now require
  `natural_pending_edit_checked = true` /
  `live_prompt_eval_natural_pending_edit_checked = true`.
- Generated Agents SDK build options can now carry an `openrealm.plan.v1`
  structure placement plan. Luanti converts that into a non-mutating preview
  first, then queues a rollback-backed `openrealm.structure.apply` task only
  after approval.
- New local adapter contract evidence: the checked-in OpenRealm creator kernel
  now backs the "cozy lakeside village with floating lanterns" prompt, producing
  `generated_openrealm_lakeside_village` with `96` runtime-safe placements
  mapped to `ai_runtime_base:stone`, `ai_runtime_base:wood`,
  `ai_runtime_base:glass`, and `ai_runtime_base:glow`.
- New live Pi sidecar evidence: the same OpenRealm village prompt returned
  `generated_openrealm_lakeside_village` through
  `agents_sdk_generated_tool_completion`, produced an `openrealm_structure` /
  `openrealm_template` preview with `96` planned node writes, and included
  `inspect_build_site_context`, `recall_build_prompt_memory`,
  `propose_build_option`, `select_build_option`, and `plan_build_actions` in
  the Agents SDK tool trace.

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
