from __future__ import annotations

import struct
import zlib
from pathlib import Path


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def write_solid_png(path: Path, rgb: tuple[int, int, int], size: int = 16, checker: bool = True) -> None:
    """Write a tiny valid PNG using only the Python standard library.

    The generated texture is intentionally simple, but valid enough for Luanti
    placeholders. Real art can replace it later without changing the manifest.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    width = height = size
    rows = []
    r, g, b = rgb
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            shade = 1.0
            if checker and ((x // 4) + (y // 4)) % 2:
                shade = 0.72
            rr = max(0, min(255, int(r * shade)))
            gg = max(0, min(255, int(g * shade)))
            bb = max(0, min(255, int(b * shade)))
            row.extend([rr, gg, bb, 255])
        rows.append(bytes(row))
    raw = b"".join(rows)
    png = b"\x89PNG\r\n\x1a\n"
    png += _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
    png += _chunk(b"IDAT", zlib.compress(raw, level=9))
    png += _chunk(b"IEND", b"")
    path.write_bytes(png)
