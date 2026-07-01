from __future__ import annotations

from .identifiers import slugify
from .models import (
    CraftItemDef,
    NodeDef,
    OpenRealmPlan,
    OreDef,
    Placement,
    Recipe,
    Structure,
    ToolDef,
)
from .parser import Intent, parse_prompt


def plan_from_prompt(prompt: str) -> OpenRealmPlan:
    return plan_from_intent(parse_prompt(prompt), prompt)


def plan_from_intent(intent: Intent, prompt: str) -> OpenRealmPlan:
    if intent.kind == "ore_mod":
        return _ore_plan(intent, prompt)
    if intent.kind == "biome_recipe":
        return _biome_plan(intent, prompt)
    if intent.kind == "structure":
        return _structure_plan(intent, prompt)
    return _world_recipe_plan(intent, prompt)


def _ore_plan(intent: Intent, prompt: str) -> OpenRealmPlan:
    base = slugify(intent.name, "moonstone")
    mod_name = f"openrealm_{base}"
    ore_node = f"{mod_name}:{base}_ore"
    crystal = f"{mod_name}:{base}_crystal"
    sword = f"{mod_name}:{base}_glowing_sword"
    block = f"{mod_name}:{base}_block"
    y_max = int(intent.constraints.get("y_max", -200))
    glowing = bool(intent.constraints.get("glowing", False))
    light = 8 if glowing else 3
    nodes = [
        NodeDef(
            name=f"{base}_ore",
            description=f"{intent.display_name} Ore",
            texture_hint="deep violet stone with cyan crystal flecks",
            groups={"cracky": 2, "ore": 1},
            light_source=light,
        ),
        NodeDef(
            name=f"{base}_block",
            description=f"{intent.display_name} Block",
            texture_hint="polished luminous moon crystal block",
            groups={"cracky": 1, "level": 2},
            light_source=min(14, light + 2),
        ),
    ]
    items = [
        CraftItemDef(
            name=f"{base}_crystal",
            description=f"{intent.display_name} Crystal",
            inventory_image_hint="single glowing cyan violet crystal",
        )
    ]
    tools = [
        ToolDef(
            name=f"{base}_glowing_sword",
            description=f"{intent.display_name} Glowing Sword",
            inventory_image_hint="short glowing sword with violet blade",
            damage_groups={"fleshy": 8},
        )
    ]
    recipes = [
        Recipe(output=block, recipe=[[crystal, crystal, crystal], [crystal, crystal, crystal], [crystal, crystal, crystal]]),
        Recipe(output=sword, recipe=[[crystal], [crystal], ["default:stick"]]),
    ]
    ores = [OreDef(ore=ore_node, y_max=y_max, y_min=-31000)]
    structures = [
        Structure(
            name=f"{base}_shrine",
            description=f"Tiny safe showcase shrine for {intent.display_name}.",
            placements=[
                Placement(0, 0, 0, block),
                Placement(1, 0, 0, block),
                Placement(-1, 0, 0, block),
                Placement(0, 0, 1, block),
                Placement(0, 0, -1, block),
                Placement(0, 1, 0, ore_node),
            ],
        )
    ]
    return OpenRealmPlan.create(
        plan_kind="ore_mod",
        title=f"{intent.display_name} Ore Pack",
        source_prompt=prompt,
        mod_name=mod_name,
        summary=f"Adds {intent.display_name} ore, crystal, block, glowing sword, recipes, ore generation, and a tiny preview shrine.",
        tags=["ore", "tool", "recipe", "template-generated", "nova"],
        nodes=nodes,
        craft_items=items,
        tools=tools,
        recipes=recipes,
        ores=ores,
        structures=structures,
    )


def _structure_plan(intent: Intent, prompt: str) -> OpenRealmPlan:
    base = slugify(intent.name, "starter_build")
    mod_name = f"openrealm_{base}"
    wood = f"{mod_name}:realmwood"
    stone = f"{mod_name}:realmstone"
    lantern = f"{mod_name}:nova_lantern"
    glass = f"{mod_name}:soft_glass"
    nodes = [
        NodeDef("realmwood", "OpenRealm Warm Wood", "warm stylized wood planks", {"choppy": 2, "wood": 1}),
        NodeDef("realmstone", "OpenRealm Smooth Stone", "soft blue gray stone block", {"cracky": 2, "stone": 1}),
        NodeDef("nova_lantern", "Nova Lantern", "floating cyan violet lantern", {"cracky": 1, "light": 1}, light_source=12, drawtype="glasslike", paramtype="light", walkable=False),
        NodeDef("soft_glass", "Soft Blue Glass", "pale blue glass", {"cracky": 3, "glass": 1}, light_source=2, drawtype="glasslike", paramtype="light"),
    ]
    placements = _structure_placements(intent, wood=wood, stone=stone, lantern=lantern, glass=glass)
    structure = Structure(
        name=base,
        description=f"Template-generated {intent.display_name} with previewable bounded placements.",
        placements=placements,
        max_radius=48,
    )
    return OpenRealmPlan.create(
        plan_kind="structure",
        title=intent.display_name,
        source_prompt=prompt,
        mod_name=mod_name,
        summary=f"Creates a bounded starter {intent.display_name.lower()} with custom nodes, preview command, build command, and rollback metadata.",
        tags=["structure", "preview", "rollback", "template-generated", "nova"],
        nodes=nodes,
        structures=[structure],
        world_recipe={
            "style": intent.style,
            "size": intent.size,
            "features": intent.features,
            "recommended_demo_prompt": prompt,
        },
    )


def _structure_placements(intent: Intent, *, wood: str, stone: str, lantern: str, glass: str) -> list[Placement]:
    p: list[Placement] = []
    if "village" in intent.name:
        # Three tiny cottages, a path, dock, lanterns. Kept under budget on purpose.
        for ox, oz in [(-6, 0), (0, 4), (6, 0)]:
            p.extend(_cottage(ox, 0, oz, wood, stone, glass, lantern))
        for x in range(-8, 9):
            p.append(Placement(x, 0, 2, stone))
        for z in range(3, 9):
            p.append(Placement(8, 0, z, wood))
        for x in [-8, -4, 0, 4, 8]:
            p.append(Placement(x, 2, 2, lantern))
        p.append(Placement(8, 2, 8, lantern))
    elif "bridge" in intent.name:
        for x in range(-6, 7):
            p.append(Placement(x, 0, 0, wood))
            if x % 2 == 0:
                p.append(Placement(x, 1, -1, lantern))
                p.append(Placement(x, 1, 1, lantern))
        for x in [-6, 6]:
            for y in range(1, 4):
                p.append(Placement(x, y, -1, stone))
                p.append(Placement(x, y, 1, stone))
    elif "tower" in intent.name or "castle" in intent.name:
        for y in range(0, 7):
            for x, z in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
                p.append(Placement(x, y, z, stone))
        for x in range(-2, 3):
            for z in range(-2, 3):
                if abs(x) == 2 or abs(z) == 2:
                    p.append(Placement(x, 7, z, wood))
        p.append(Placement(0, 8, 0, lantern))
    elif "dock" in intent.name:
        for z in range(0, 9):
            for x in range(-1, 2):
                p.append(Placement(x, 0, z, wood))
        for z in [0, 3, 6, 8]:
            p.append(Placement(-2, 1, z, lantern))
            p.append(Placement(2, 1, z, lantern))
    elif "path" in intent.name:
        for x in range(0, 16):
            p.append(Placement(x, 0, 0, stone))
            if x % 4 == 0:
                p.append(Placement(x, 1, 1, lantern))
    else:
        p.extend(_cottage(0, 0, 0, wood, stone, glass, lantern))
    return p[:240]


def _cottage(ox: int, oy: int, oz: int, wood: str, stone: str, glass: str, lantern: str) -> list[Placement]:
    p: list[Placement] = []
    for x in range(-2, 3):
        for z in range(-2, 3):
            p.append(Placement(ox + x, oy, oz + z, stone))
    for y in range(1, 4):
        for x in range(-2, 3):
            p.append(Placement(ox + x, oy + y, oz - 2, wood))
            p.append(Placement(ox + x, oy + y, oz + 2, wood))
        for z in range(-1, 2):
            p.append(Placement(ox - 2, oy + y, oz + z, wood))
            p.append(Placement(ox + 2, oy + y, oz + z, wood))
    p.append(Placement(ox, oy + 2, oz - 2, glass))
    p.append(Placement(ox, oy + 2, oz + 2, glass))
    for x in range(-3, 4):
        p.append(Placement(ox + x, oy + 4, oz, wood))
    p.append(Placement(ox, oy + 5, oz, lantern))
    return p


def _biome_plan(intent: Intent, prompt: str) -> OpenRealmPlan:
    mod_name = "openrealm_glacier_biome"
    nodes = [
        NodeDef("alpine_stone", "Alpine Stone", "cool gray mountain stone", {"cracky": 2, "stone": 1}),
        NodeDef("glacier_ice", "Glacier Ice", "pale blue translucent glacier ice", {"cracky": 3, "ice": 1}, drawtype="glasslike", paramtype="light"),
        NodeDef("pine_needles", "Pine Needles", "deep green pine foliage", {"snappy": 3, "leaves": 1}, drawtype="allfaces_optional", paramtype="light", walkable=False),
        NodeDef("trail_marker", "Trail Marker", "small blue trail sign", {"choppy": 2}, light_source=5),
    ]
    world_recipe = {
        "recipe_kind": "biome_recipe",
        "biome_name": intent.display_name,
        "mood": "clean alpine, family-safe adventure, quiet lakes, bright peaks",
        "terrain": ["steep valleys", "cold lakes", "waterfalls", "pine forest pockets", "snowy ridges"],
        "ambient_sound_plan": ["wind through pines", "distant water", "soft birds"],
        "structure_suggestions": ["trailhead cabin", "lake dock", "lookout tower", "stone bridge"],
        "quest_hooks": ["find three vista markers", "repair the old bridge", "light the lakeside trail"],
        "safety_note": "This is a data recipe. Mapgen integration should remain template-based and approval-gated.",
    }
    return OpenRealmPlan.create(
        plan_kind="biome_recipe",
        title=intent.display_name,
        source_prompt=prompt,
        mod_name=mod_name,
        summary="Creates a data-first alpine biome recipe with nodes, mood, terrain guidance, quest hooks, and starter assets.",
        tags=["biome", "recipe", "glacier", "template-generated", "nova"],
        nodes=nodes,
        world_recipe=world_recipe,
    )


def _world_recipe_plan(intent: Intent, prompt: str) -> OpenRealmPlan:
    mod_name = "openrealm_world_recipe"
    world_recipe = {
        "recipe_kind": "world_recipe",
        "name": intent.display_name,
        "features": intent.features,
        "style": intent.style,
        "size": intent.size,
        "next_best_prompts": [
            "Build a small cabin near spawn",
            "Add a path with lanterns",
            "Create a starter quest for families",
        ],
    }
    return OpenRealmPlan.create(
        plan_kind="world_recipe",
        title=intent.display_name,
        source_prompt=prompt,
        mod_name=mod_name,
        summary="Creates a safe OpenRealm world recipe placeholder for iterative planning.",
        tags=["world-recipe", "nova", "planning"],
        world_recipe=world_recipe,
    )
