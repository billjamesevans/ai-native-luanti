from __future__ import annotations

import re

IDENT_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
MOD_RE = re.compile(r"^[a-z][a-z0-9_]{1,62}$")
NODE_RE = re.compile(r"^[a-z][a-z0-9_]{1,62}:[a-z][a-z0-9_]{0,62}$")

_RESERVED = {
    "and", "break", "do", "else", "elseif", "end", "false", "for", "function",
    "if", "in", "local", "nil", "not", "or", "repeat", "return", "then", "true",
    "until", "while",
}


def slugify(value: str, fallback: str = "realm") -> str:
    """Return a Luanti/Lua-safe lowercase identifier fragment."""
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = value.strip("_")
    if not value:
        value = fallback
    if value[0].isdigit():
        value = f"or_{value}"
    if value in _RESERVED:
        value = f"or_{value}"
    value = value[:63].strip("_") or fallback
    if not IDENT_RE.match(value):
        value = fallback
    return value


def titleize(value: str) -> str:
    value = re.sub(r"[_\-]+", " ", value or "").strip()
    return " ".join(part.capitalize() for part in value.split()) or "OpenRealm Creation"


def is_identifier(value: str) -> bool:
    return bool(IDENT_RE.match(value or "")) and value not in _RESERVED


def is_mod_name(value: str) -> bool:
    return bool(MOD_RE.match(value or "")) and value not in _RESERVED


def is_node_name(value: str) -> bool:
    return bool(NODE_RE.match(value or ""))


def lua_quote(value: object) -> str:
    """Quote a value as a safe Lua string literal."""
    text = str(value if value is not None else "")
    text = text.replace("\\", "\\\\").replace('"', '\\"')
    text = text.replace("\n", "\\n").replace("\r", "")
    return f'"{text}"'


def lua_identifier(value: str, fallback: str = "item") -> str:
    slug = slugify(value, fallback=fallback)
    if not is_identifier(slug):
        raise ValueError(f"Unsafe Lua identifier: {value!r}")
    return slug
