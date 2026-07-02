#!/usr/bin/env python3
"""Generate deterministic OpenRealm alpha base textures."""

from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw


SIZE = 32
LOGICAL_SIZE = 16
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "mods" / "ai_runtime_base" / "textures"


def clamp(value: int) -> int:
    return max(0, min(255, value))


def rgb(hex_color: str) -> tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[index:index + 2], 16) for index in range(0, 6, 2))


def rgba(hex_color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    return rgb(hex_color) + (alpha,)


def adjust(color: tuple[int, int, int], amount: int) -> tuple[int, int, int]:
    return tuple(clamp(channel + amount) for channel in color)


def save(image: Image.Image, name: str, *, opaque: bool = True) -> None:
    if opaque:
        image = image.copy()
        image.putalpha(255)
    image.save(OUT / f"ai_runtime_base_{name}.png")


def tile(base: str) -> Image.Image:
    return Image.new("RGBA", (SIZE, SIZE), rgba(base))


def voxel_map(rows: tuple[str, ...], palette: dict[str, str]) -> Image.Image:
    return upscale_voxel(lowres_voxel_map(rows, palette))


def lowres_voxel_map(rows: tuple[str, ...], palette: dict[str, str]) -> Image.Image:
    if len(rows) != LOGICAL_SIZE or any(len(row) != LOGICAL_SIZE for row in rows):
        raise ValueError("voxel texture maps must be 16x16 before export")

    image = Image.new("RGBA", (LOGICAL_SIZE, LOGICAL_SIZE))
    pixels = image.load()
    for y, row in enumerate(rows):
        for x, key in enumerate(row):
            pixels[x, y] = rgba(palette[key])

    return image


def upscale_voxel(image: Image.Image) -> Image.Image:
    resample = Image.Resampling.NEAREST if hasattr(Image, "Resampling") else Image.NEAREST
    return image.resize((SIZE, SIZE), resample=resample)


def weighted_voxel_grid(
    seed: int,
    palette: dict[str, str],
    weights: tuple[tuple[str, int], ...],
    *,
    clump_bias: float = 0.62,
) -> Image.Image:
    rng = random.Random(seed)
    pool = [key for key, weight in weights for _ in range(weight)]
    image = Image.new("RGBA", (LOGICAL_SIZE, LOGICAL_SIZE), rgba(palette[weights[0][0]]))
    pixels = image.load()

    for y in range(LOGICAL_SIZE):
        for x in range(LOGICAL_SIZE):
            clump_rng = random.Random(seed + (x // 2) * 37 + (y // 2) * 101)
            clump_key = clump_rng.choice(pool)
            key = clump_key if rng.random() < clump_bias else rng.choice(pool)
            pixels[x, y] = rgba(palette[key])

    return image


def dirt_lowres() -> Image.Image:
    palette = {
        "a": "#6B4A34",
        "b": "#78563B",
        "c": "#8C6846",
        "d": "#50372A",
        "e": "#3F2D25",
    }
    image = weighted_voxel_grid(
        2202,
        palette,
        (("a", 52), ("b", 18), ("c", 8), ("d", 17), ("e", 5)),
    )
    draw = ImageDraw.Draw(image)
    for box, key in (
        ((2, 2, 4, 3), "c"),
        ((10, 1, 12, 2), "d"),
        ((5, 6, 7, 7), "b"),
        ((13, 7, 14, 9), "e"),
        ((1, 11, 3, 12), "d"),
        ((8, 12, 10, 13), "c"),
    ):
        draw.rectangle(box, fill=rgba(palette[key]))
    return image


def grass_top_lowres() -> Image.Image:
    palette = {
        "a": "#5E9A3A",
        "b": "#70AD44",
        "c": "#83BE51",
        "d": "#477D31",
        "e": "#356B29",
    }
    image = weighted_voxel_grid(
        3303,
        palette,
        (("a", 54), ("b", 19), ("c", 6), ("d", 16), ("e", 5)),
    )
    draw = ImageDraw.Draw(image)
    for box, key in (
        ((1, 1, 3, 2), "b"),
        ((9, 1, 11, 2), "d"),
        ((12, 4, 14, 5), "b"),
        ((3, 6, 5, 7), "d"),
        ((7, 8, 10, 9), "b"),
        ((1, 11, 2, 13), "e"),
        ((12, 11, 14, 13), "d"),
        ((5, 13, 7, 14), "c"),
    ):
        draw.rectangle(box, fill=rgba(palette[key]))
    return image


def stone_lowres() -> Image.Image:
    return lowres_voxel_map(
        (
            "aaaabbbaaaaaadaa",
            "aaabbbbaaaadadaa",
            "aabbbaaaaaddaaaa",
            "aaaaaaaccaaaaaaa",
            "ddaaaaaccaaabbaa",
            "ddaaaaaaaabbbbaa",
            "aaaacccaaaaabbaa",
            "aaacccaaaddaaaaa",
            "aaaaaaaadddaaccc",
            "bbbaaaaaadaaccca",
            "bbbbaaaaaaaacaaa",
            "aaaaaddaaaabbbbb",
            "aaaadddaaaabbbbb",
            "aaaaadaaaaabaaaa",
            "aaccaaaaaddaaaaa",
            "aaacaaaaadddaaaa",
        ),
        {
            "a": "#6F767D",
            "b": "#7A8188",
            "c": "#858C93",
            "d": "#626970",
        },
    )


def cobble_lowres() -> Image.Image:
    palette = {
        "m": "#4A5158",
        "a": "#666D74",
        "b": "#737A81",
        "c": "#7B8289",
        "d": "#5C636B",
        "e": "#555C64",
    }
    image = Image.new("RGBA", (LOGICAL_SIZE, LOGICAL_SIZE), rgba(palette["m"]))
    draw = ImageDraw.Draw(image)
    stones = (
        (((-1, -1), (6, -1), (5, 4), (1, 5), (-1, 3)), "a"),
        (((6, -1), (16, -1), (16, 5), (12, 6), (5, 4)), "b"),
        (((-1, 4), (1, 5), (5, 4), (7, 8), (3, 11), (-1, 10)), "d"),
        (((6, 5), (12, 6), (14, 9), (10, 12), (4, 11), (7, 8)), "b"),
        (((13, 6), (16, 5), (16, 13), (12, 12), (14, 9)), "e"),
        (((-1, 11), (3, 12), (4, 16), (-1, 16)), "c"),
        (((4, 12), (10, 13), (12, 16), (4, 16)), "a"),
        (((11, 13), (16, 13), (16, 16), (12, 16)), "d"),
    )
    for points, key in stones:
        draw.polygon(points, fill=rgba(palette[key]))

    for line in (
        ((5, 0), (5, 4), (7, 8), (4, 11), (4, 15)),
        ((5, 4), (12, 6), (14, 9), (12, 12)),
        ((1, 5), (5, 4)),
        ((3, 12), (10, 13), (12, 15)),
        ((12, 6), (16, 5)),
    ):
        draw.line(line, fill=rgba("#424950"))

    for line in (
        ((1, 1), (4, 1)),
        ((8, 1), (12, 1)),
        ((7, 6), (10, 6)),
        ((1, 12), (3, 13)),
        ((6, 13), (9, 14)),
    ):
        draw.line(line, fill=rgba("#858C93"))
    return image


def add_bevel(draw: ImageDraw.ImageDraw, base: str, alpha: int = 255) -> None:
    base_rgb = rgb(base)
    draw.line((0, 0, SIZE - 1, 0), fill=adjust(base_rgb, 28) + (alpha,))
    draw.line((0, 0, 0, SIZE - 1), fill=adjust(base_rgb, 18) + (alpha,))
    draw.line((0, SIZE - 1, SIZE - 1, SIZE - 1), fill=adjust(base_rgb, -30) + (alpha,))
    draw.line((SIZE - 1, 0, SIZE - 1, SIZE - 1), fill=adjust(base_rgb, -24) + (alpha,))


def deterministic_noise(image: Image.Image, seed: int, strength: int, mask_alpha: int = 255) -> None:
    rng = random.Random(seed)
    pixels = image.load()
    for y in range(SIZE):
        for x in range(SIZE):
            r, g, b, a = pixels[x, y]
            if a == 0:
                continue
            jitter = rng.randint(-strength, strength)
            light = 3 if x + y < SIZE else 0
            shade = -4 if x + y > SIZE * 1.35 else 0
            pixels[x, y] = (
                clamp(r + jitter + light + shade),
                clamp(g + jitter + light + shade),
                clamp(b + jitter + light + shade),
                min(a, mask_alpha),
            )


def stone() -> None:
    image = upscale_voxel(stone_lowres())
    save(image, "stone")


def dirt() -> None:
    image = upscale_voxel(dirt_lowres())
    save(image, "dirt")


def grass_top() -> None:
    image = upscale_voxel(grass_top_lowres())
    save(image, "grass_top")


def grass_side() -> None:
    lowres = Image.new("RGBA", (LOGICAL_SIZE, LOGICAL_SIZE), rgba("#6B4A34"))
    lowres.alpha_composite(dirt_lowres().crop((0, 4, LOGICAL_SIZE, LOGICAL_SIZE)), (0, 4))
    pixels = lowres.load()
    grass_rows = (
        "aabbaaaabbaaaabb",
        "abbcaabaabbcaaba",
        "eabbaaeeaabbaaee",
        "emmmabmmemmmabmm",
    )
    palette = {
        "a": "#5E9A3A",
        "b": "#70AD44",
        "c": "#83BE51",
        "e": "#356B29",
        "m": "#6B4A34",
    }
    for y, row in enumerate(grass_rows):
        for x, key in enumerate(row):
            pixels[x, y] = rgba(palette[key])
    image = upscale_voxel(lowres)
    save(image, "grass_side")


def leaves() -> None:
    image = tile("#245E3A")
    deterministic_noise(image, 454, 5)
    draw = ImageDraw.Draw(image)
    clusters = [
        ((0, 1, 11, 10), "#2F7A47"),
        ((13, 0, 28, 9), "#1C4D32"),
        ((4, 12, 17, 23), "#2F8A4D"),
        ((19, 13, 31, 25), "#173F2A"),
        ((2, 24, 14, 31), "#2B7043"),
    ]
    for box, color in clusters:
        draw.rounded_rectangle(box, radius=2, fill=rgba(color, 210))
    for x, y in ((6, 4), (17, 7), (9, 17), (25, 16), (13, 27), (28, 27)):
        draw.line((x, y, x + 2, y - 2), fill=rgba("#7BDE78", 175), width=1)
    for x, y in ((3, 12), (16, 19), (24, 6), (30, 21)):
        draw.point((x, y), fill=rgba("#75F4D5", 120))
    add_bevel(draw, "#245E3A")
    save(image, "leaves")


def sand() -> None:
    image = tile("#D8C27B")
    deterministic_noise(image, 505, 5)
    draw = ImageDraw.Draw(image)
    for y, offset in ((8, 0), (17, 7), (25, 3)):
        points = [(x, y + int(math.sin((x + offset) / 5) * 2)) for x in range(0, 32, 2)]
        draw.line(points, fill=rgba("#A99250", 120), width=1)
    for x, y in ((6, 12), (14, 5), (21, 20), (27, 14), (11, 26)):
        draw.point((x, y), fill=rgba("#F4DEA0", 210))
        draw.point((x + 1, y), fill=rgba("#947D45", 140))
    add_bevel(draw, "#D8C27B")
    save(image, "sand")


def cobble() -> None:
    image = upscale_voxel(cobble_lowres())
    save(image, "cobble")


def fire() -> None:
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.polygon([(2, 31), (6, 23), (8, 13), (12, 23), (15, 3), (19, 22), (24, 12), (30, 31)], fill=rgba("#D9483D", 220))
    draw.polygon([(6, 31), (10, 20), (13, 26), (17, 9), (21, 25), (24, 18), (27, 31)], fill=rgba("#FF8A3D", 245))
    draw.polygon([(11, 31), (14, 23), (16, 15), (19, 25), (22, 31)], fill=rgba("#FFD166", 255))
    draw.polygon([(15, 31), (17, 25), (19, 31)], fill=rgba("#FFF2A8", 255))
    draw.line((7, 30, 25, 30), fill=rgba("#741E2A", 160), width=1)
    save(image, "fire", opaque=False)


def tnt() -> None:
    image = tile("#B83245")
    deterministic_noise(image, 707, 3)
    draw = ImageDraw.Draw(image)
    for y in (0, 7, 24, 31):
        draw.line((0, y, 31, y), fill=rgba("#7A2631", 155), width=1)
    for x in (5, 16, 27):
        draw.line((x, 0, x, 31), fill=rgba("#8E2C39", 135), width=1)
    draw.rectangle((0, 11, 31, 20), fill=rgba("#F3E8D3"))
    draw.line((0, 10, 31, 10), fill=rgba("#7A2631", 230))
    draw.line((0, 21, 31, 21), fill=rgba("#7A2631", 230))
    letter = rgba("#4B2630")
    for x in (5, 13, 21):
        draw.rectangle((x, 13, x + 5, 14), fill=letter)
    draw.rectangle((7, 13, 8, 18), fill=letter)
    draw.rectangle((13, 13, 14, 18), fill=letter)
    draw.rectangle((17, 13, 18, 18), fill=letter)
    draw.rectangle((21, 13, 22, 18), fill=letter)
    draw.rectangle((23, 13, 26, 14), fill=letter)
    draw.rectangle((23, 16, 26, 17), fill=letter)
    add_bevel(draw, "#B83245")
    save(image, "tnt")


def wood_side() -> None:
    image = tile("#8C5A38")
    deterministic_noise(image, 808, 5)
    draw = ImageDraw.Draw(image)
    for x, color in ((4, "#5D3824"), (10, "#B97845"), (17, "#5A341F"), (24, "#B17443")):
        draw.line((x, 0, x, 31), fill=rgba(color, 180), width=1)
    draw.ellipse((7, 10, 15, 18), outline=rgba("#5A341F", 210), width=1)
    draw.ellipse((20, 21, 27, 28), outline=rgba("#5A341F", 190), width=1)
    for y in (6, 15, 25):
        draw.line((0, y, 31, y), fill=rgba("#C88A55", 85), width=1)
    add_bevel(draw, "#8C5A38")
    save(image, "wood_side")


def wood_top() -> None:
    image = tile("#A66F3F")
    deterministic_noise(image, 809, 4)
    draw = ImageDraw.Draw(image)
    rings = [
        (2, 2, 29, 29, "#70452A"),
        (6, 6, 25, 25, "#D79B60"),
        (10, 9, 22, 22, "#70452A"),
        (14, 13, 18, 18, "#DDA36A"),
    ]
    for x1, y1, x2, y2, color in rings:
        draw.ellipse((x1, y1, x2, y2), outline=rgba(color, 190), width=1)
    draw.line((3, 20, 13, 15), fill=rgba("#6C432A", 150), width=1)
    draw.line((19, 9, 27, 5), fill=rgba("#6C432A", 130), width=1)
    add_bevel(draw, "#A66F3F")
    save(image, "wood_top")


def gold() -> None:
    image = tile("#DCA93A")
    draw = ImageDraw.Draw(image)
    panels = [
        (1, 1, 14, 14, "#FFD166"),
        (15, 1, 30, 14, "#E8B946"),
        (1, 15, 14, 30, "#C89224"),
        (15, 15, 30, 30, "#F2C454"),
    ]
    for panel in panels:
        draw.rectangle(panel[:4], fill=rgba(panel[4]))
        draw.line((panel[0], panel[1], panel[2], panel[1]), fill=rgba("#FFF2A8", 135))
    draw.line((14, 1, 14, 30), fill=rgba("#9B6B1E", 170))
    draw.line((1, 14, 30, 14), fill=rgba("#9B6B1E", 170))
    draw.line((3, 3, 13, 3), fill=rgba("#FFF0AA", 180), width=1)
    deterministic_noise(image, 909, 2)
    add_bevel(draw, "#DCA93A")
    save(image, "gold")


def quartz() -> None:
    image = tile("#E9EEF7")
    deterministic_noise(image, 1001, 3)
    draw = ImageDraw.Draw(image)
    veins = [
        [(1, 22), (8, 17), (12, 12), (20, 7), (30, 4)],
        [(7, 31), (12, 25), (17, 24), (25, 18), (31, 16)],
        [(0, 5), (6, 8), (12, 8)],
    ]
    for vein in veins:
        draw.line(vein, fill=rgba("#B8C3D2", 120), width=1)
    draw.line((0, 0, 31, 0), fill=rgba("#FFFFFF", 210))
    draw.line((0, 31, 31, 31), fill=rgba("#C7D0DF", 170))
    add_bevel(draw, "#E9EEF7")
    save(image, "quartz")


def glass() -> None:
    image = Image.new("RGBA", (SIZE, SIZE), rgba("#87E7FF", 82))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 31, 31), outline=rgba("#DDFBFF", 230), width=2)
    draw.rectangle((3, 3, 28, 28), outline=rgba("#3EA7BD", 80), width=1)
    draw.line((6, 3, 28, 25), fill=rgba("#FFFFFF", 100), width=2)
    draw.line((16, 3, 29, 16), fill=rgba("#FFFFFF", 82), width=1)
    draw.rectangle((2, 2, 9, 9), fill=rgba("#CFF7FF", 55))
    save(image, "glass", opaque=False)


def diamond() -> None:
    image = tile("#2CC7D0")
    draw = ImageDraw.Draw(image)
    facets = [
        [(0, 0), (15, 0), (7, 15)],
        [(16, 0), (31, 0), (24, 15)],
        [(7, 15), (15, 0), (24, 15), (15, 31)],
        [(0, 31), (7, 15), (15, 31)],
        [(31, 31), (24, 15), (15, 31)],
    ]
    colors = ["#8FFBFF", "#43D4E8", "#26B5C9", "#5EF4D6", "#138AA3"]
    for points, color in zip(facets, colors, strict=True):
        draw.polygon(points, fill=rgba(color))
    for line in (((15, 0), (7, 15), (15, 31), (24, 15), (15, 0)), ((0, 0), (7, 15), (0, 31)), ((31, 0), (24, 15), (31, 31))):
        draw.line(line, fill=rgba("#D7FFF8", 115), width=1)
    deterministic_noise(image, 1101, 2)
    add_bevel(draw, "#2CC7D0")
    save(image, "diamond")


def glow() -> None:
    image = tile("#3B2B86")
    draw = ImageDraw.Draw(image)
    draw.rectangle((2, 2, 29, 29), fill=rgba("#241C5E"))
    draw.polygon([(16, 3), (29, 16), (16, 29), (3, 16)], fill=rgba("#704BFF"))
    draw.polygon([(16, 7), (25, 16), (16, 25), (7, 16)], fill=rgba("#9C6DFF"))
    draw.polygon([(16, 11), (21, 16), (16, 21), (11, 16)], fill=rgba("#E2C8FF"))
    draw.line((16, 3, 16, 29), fill=rgba("#62E8FF", 120), width=1)
    draw.line((3, 16, 29, 16), fill=rgba("#62E8FF", 120), width=1)
    for x, y in ((5, 5), (26, 6), (5, 27), (27, 26), (10, 21), (22, 10)):
        draw.point((x, y), fill=rgba("#B9F7FF", 230))
    add_bevel(draw, "#3B2B86")
    save(image, "glow")


def builder_pick() -> None:
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.line((8, 24, 23, 9), fill=rgba("#233A5F"), width=5)
    draw.line((8, 24, 23, 9), fill=rgba("#9FE8D1"), width=2)
    draw.polygon([(6, 6), (23, 5), (28, 9), (25, 13), (16, 10), (8, 13)], fill=rgba("#5EF4D6"))
    draw.line((8, 7, 25, 9), fill=rgba("#D7FFF8", 230), width=1)
    draw.line((7, 13, 25, 13), fill=rgba("#1BAE9C", 220), width=1)
    save(image, "builder_pick", opaque=False)


TEXTURE_BUILDERS = [
    ("builder_pick", builder_pick),
    ("stone", stone),
    ("dirt", dirt),
    ("grass_top", grass_top),
    ("grass_side", grass_side),
    ("leaves", leaves),
    ("sand", sand),
    ("cobble", cobble),
    ("fire", fire),
    ("tnt", tnt),
    ("wood_side", wood_side),
    ("wood_top", wood_top),
    ("gold", gold),
    ("quartz", quartz),
    ("glass", glass),
    ("diamond", diamond),
    ("glow", glow),
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for _name, build_texture in TEXTURE_BUILDERS:
        build_texture()


if __name__ == "__main__":
    main()
