from __future__ import annotations

from dataclasses import dataclass, field
import re

from .identifiers import slugify, titleize


@dataclass(frozen=True)
class Intent:
    kind: str
    name: str
    display_name: str
    features: list[str] = field(default_factory=list)
    materials: list[str] = field(default_factory=list)
    style: str = "openrealm"
    size: str = "medium"
    constraints: dict[str, object] = field(default_factory=dict)


_SIZE_WORDS = {
    "tiny": "small",
    "small": "small",
    "cozy": "small",
    "medium": "medium",
    "large": "large",
    "huge": "large",
    "massive": "large",
    "epic": "large",
}

_FEATURE_WORDS = [
    "lake", "lakeside", "village", "lantern", "floating", "bridge", "cabin",
    "castle", "portal", "waterfall", "forest", "mountain", "garden", "dock",
    "path", "tower", "ore", "sword", "biome", "quest", "npc", "animals",
]

_STYLE_WORDS = [
    "cozy", "fantasy", "glacier", "alpine", "crystal", "moon", "forest", "medieval",
    "cottage", "futuristic", "peaceful", "family", "adventure",
]


def parse_prompt(prompt: str) -> Intent:
    text = (prompt or "").strip()
    if not text:
        raise ValueError("Prompt cannot be empty.")
    low = text.lower()

    size = next((mapped for word, mapped in _SIZE_WORDS.items() if re.search(rf"\b{word}\b", low)), "medium")
    features = [word for word in _FEATURE_WORDS if re.search(rf"\b{re.escape(word)}s?\b", low)]
    style_words = [word for word in _STYLE_WORDS if re.search(rf"\b{re.escape(word)}\b", low)]
    style = " ".join(style_words[:3]) or "openrealm"

    ore_match = re.search(r"(?:ore called|new ore called|ore named|called)\s+([a-zA-Z][a-zA-Z0-9 _-]{1,32})", text, re.I)
    if "ore" in low or ore_match:
        raw_name = ore_match.group(1) if ore_match else "moonstone"
        raw_name = re.split(r"\s+(?:that|which|and|used|spawns|below|above)\b", raw_name, maxsplit=1, flags=re.I)[0]
        depth = -200
        depth_match = re.search(r"below\s+(?:level\s*)?(-?\d+)", low)
        if depth_match:
            depth = -abs(int(depth_match.group(1)))
        tool = "sword" if "sword" in low else "tool"
        return Intent(
            kind="ore_mod",
            name=slugify(raw_name, "moonstone"),
            display_name=titleize(raw_name),
            features=features or ["ore", tool],
            materials=[slugify(raw_name, "moonstone")],
            style=style,
            size=size,
            constraints={"y_max": depth, "tool": tool, "glowing": "glow" in low or "glowing" in low},
        )

    if "biome" in low or "glacier national park" in low or "glacier" in low:
        name = "glacier_alpine_biome" if "glacier" in low else "custom_biome"
        return Intent(
            kind="biome_recipe",
            name=name,
            display_name="Glacier Alpine Biome" if "glacier" in low else "Custom Biome",
            features=features or ["biome", "forest", "lake", "mountain"],
            materials=["pine", "stone", "water", "snow"],
            style=style,
            size=size,
            constraints={"climate": "alpine", "mood": "clean_cozy_adventure"},
        )

    if any(word in low for word in ["village", "cabin", "bridge", "path", "dock", "tower", "castle", "build", "make", "create"]):
        if "village" in low:
            name = "lakeside_village" if "lake" in low or "lakeside" in low else "village"
            display = "Cozy Lakeside Village" if "cozy" in low or "lakeside" in low else "OpenRealm Village"
        elif "bridge" in low:
            name, display = "stone_bridge", "Stone Bridge"
        elif "cabin" in low:
            name, display = "cozy_cabin", "Cozy Cabin"
        elif "dock" in low:
            name, display = "lakeside_dock", "Lakeside Dock"
        elif "tower" in low:
            name, display = "lookout_tower", "Lookout Tower"
        elif "castle" in low:
            name, display = "starter_castle", "Starter Castle"
        elif "path" in low:
            name, display = "trail_path", "Trail Path"
        else:
            name, display = "starter_build", "Starter Build"
        return Intent(
            kind="structure",
            name=slugify(name),
            display_name=display,
            features=features or ["structure"],
            materials=["wood", "stone", "lantern", "glass"],
            style=style,
            size=size,
            constraints={"theme": style, "needs_preview": True},
        )

    return Intent(
        kind="world_recipe",
        name="openrealm_world_recipe",
        display_name="OpenRealm World Recipe",
        features=features or ["world"],
        materials=["wood", "stone", "water", "light"],
        style=style,
        size=size,
        constraints={"fallback": True},
    )
