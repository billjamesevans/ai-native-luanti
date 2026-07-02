# OpenRealm Alpha Sprite Bible

## Scope

This profile uses small, public-safe voxel textures for AI-built preview structures. The art should read clearly at distance and stay compatible with older Luanti clients.

## Format

- Pixel art PNG textures, 32x32.
- One texture tile per material, no atlases.
- Each block material needs its own silhouette language: stone cracks, dirt roots,
  grass blades, sand ripples, cobble mortar, wood grain, metal panels, crystal
  facets, glass glints, or glow cores.
- Low-frequency noise only; avoid dense checkerboards or accidental text-like marks.
- Terrain blocks should benchmark against classic Minecraft readability: simple
  clustered pixels, restrained contrast, no bevel/border treatment, and no
  high-frequency static that turns into shimmer when tiled.
- Rock/cobble should use larger irregular chunks with muted mortar. Avoid brick
  rows, sharp tile-wide stripes, and dense crack networks.
- Transparent PNGs are allowed only for plantlike effects and glass.

## Palette

- Stone: `#566070`, with cool blue highlights and muted charcoal cracks.
- Dirt and wood: warm browns, limited saturation.
- Grass: clean green top color with a darker side strip.
- Leaves: deep saturated greens with cool moonlit highlights.
- Fire and gold: warm village/crafting accents.
- Diamond and glass: cool cyan-blue highlights.
- Glow: portal-like violet core with cyan sparkle accents.
- UI accent: `#9FE8D1` for Nova/OpenRealm guidance and `#FFD166` for prompts.

## Lighting

Use a subtle upper-left highlight and lower-right shade. Keep material contrast moderate so world geometry reads as professional and calm rather than noisy.

## Compatibility

The game profile should ship actual PNG textures instead of relying on generated texture modifiers for node tiles. This avoids unknown-texture fallback on older or stricter clients.

## Texture Export Contract

Every material is authored and exported as an individual 32x32 PNG. Do not pack these into an atlas or generate one generic tinted tile for multiple materials.

- `ai_runtime_base_stone.png`
- `ai_runtime_base_dirt.png`
- `ai_runtime_base_grass_top.png`
- `ai_runtime_base_grass_side.png`
- `ai_runtime_base_leaves.png`
- `ai_runtime_base_sand.png`
- `ai_runtime_base_cobble.png`
- `ai_runtime_base_fire.png`
- `ai_runtime_base_tnt.png`
- `ai_runtime_base_wood_side.png`
- `ai_runtime_base_wood_top.png`
- `ai_runtime_base_gold.png`
- `ai_runtime_base_quartz.png`
- `ai_runtime_base_glass.png`
- `ai_runtime_base_diamond.png`
- `ai_runtime_base_glow.png`
- `ai_runtime_base_builder_pick.png`
