# OpenRealm Brand Library

The OpenRealm brand library lives in
[`../../openrealm_advantage_kit/assets/`](../../openrealm_advantage_kit/assets/).
It is the current visual direction for transforming this fork into OpenRealm:
an open-source AI-native voxel world creator.

## Core Assets

| Asset | Purpose |
| --- | --- |
| [`openrealm_brand_style_guide.png`](../../openrealm_advantage_kit/assets/openrealm_brand_style_guide.png) | Primary identity board with OpenRealm, Nova, colors, type, launcher mockup, and website mockup. |
| [`openrealm_brand_assets_sheet.png`](../../openrealm_advantage_kit/assets/openrealm_brand_assets_sheet.png) | Icon, wordmark, lockup, Nova badge, app icon, and launcher tile concepts. |
| [`openrealm_creator_studio_mockup.png`](../../openrealm_advantage_kit/assets/openrealm_creator_studio_mockup.png) | Creator Studio product target: Play, Create, Worlds, Mods, Host, Community, Nova flow, and private multiplayer. |
| [`openrealm_future_key_art.png`](../../openrealm_advantage_kit/assets/openrealm_future_key_art.png) | Key art for the OpenRealm world promise and public-facing visual identity. |
| [`openrealm_creator_flow.png`](../../openrealm_advantage_kit/assets/openrealm_creator_flow.png) | Seven-step creator loop: Prompt, Plan, Preview, Approve, Build, Audit and Undo, Share. |
| [`how_nova_ai_works.png`](../../openrealm_advantage_kit/assets/how_nova_ai_works.png) | Nova architecture diagram showing UI, parser, planner, approval, task queue, mutation runtime, audit, and rollback. |
| [`openrealm_roadmap_ecosystem.png`](../../openrealm_advantage_kit/assets/openrealm_roadmap_ecosystem.png) | Five-phase product roadmap and ecosystem map for users, creators, modders, families, and servers. |

## Product Commitments

- OpenRealm is the platform and public project identity.
- Nova is the AI builder assistant.
- Luminara is the first polished creator playground.
- The signature loop is prompt -> plan -> preview -> approve -> build -> audit
  and undo -> share.
- AI does not mutate the world directly. Luanti remains the world authority.
- Public assets must not include private family-server worlds, proprietary
  assets, copied Minecraft assets, local credentials, or provider secrets.

## Technical Companion

The same library drop includes the OpenRealm Advantage Kit:

- [`openrealm_creator_kernel/`](../../openrealm_advantage_kit/openrealm_creator_kernel/)
  for deterministic prompt-to-plan tooling.
- [`schemas/openrealm_plan.schema.json`](../../openrealm_advantage_kit/schemas/openrealm_plan.schema.json)
  for the creator-plan contract.
- [`studio/index.html`](../../openrealm_advantage_kit/studio/index.html)
  for the local Creator Studio prototype.
- [`luanti_mod/openrealm_creator/`](../../openrealm_advantage_kit/luanti_mod/openrealm_creator/)
  for the prototype in-world preview/build/rollback commands.
- [`docs/`](../../openrealm_advantage_kit/docs/) for the product thesis,
  architecture, integration plan, and next issues.

## Validation

Current local validation for the kit:

```bash
python3 util/openrealm_advantage_kit_verify.py --run-tests --run-js-check
```

The repository-level public secret guard must also pass before publishing:

```bash
python3 util/scan_public_repo_secrets.py --tracked --untracked
```
