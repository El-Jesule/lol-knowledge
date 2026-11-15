"""Hash helpers used by the bin calculation model."""

from __future__ import annotations

import re

_HASH_RE = re.compile(r"^\{?0?x?([0-9a-fA-F]{1,8})\}?$")


def fnv1a32(name: str) -> int:
    """Return FNV-1a 32-bit of the lowercased UTF-8 name.

    This is the hash function used by the bin type and field tables. The
    implementation is intentionally small so the result can be reproduced
    without third-party dependencies.
    """
    value = 0x811C9DC5
    for byte in name.lower().encode("utf-8"):
        value ^= byte
        value = (value * 0x01000193) & 0xFFFFFFFF
    return value


def normalize_type(value: str | None) -> str | None:
    """Normalize ``{0a0eddc9}`` / ``0x0a0eddc9`` to ``0x0a0eddc9``.

    Names are returned unchanged. ``None`` is preserved.
    """
    if value is None:
        return None
    value = value.strip()
    if value.startswith("{") and value.endswith("}"):
        value = value[1:-1]
    if value.lower().startswith("0x"):
        value = value[2:]
    if re.fullmatch(r"[0-9a-fA-F]{1,8}", value) and not value.isalpha():
        return f"0x{int(value, 16):08x}"
    if re.fullmatch(r"[0-9a-fA-F]{8}", value):
        return f"0x{value.lower()}"
    return value


def normalize_field(value: str) -> str:
    """Normalize a field key to lowercase hexadecimal without a prefix."""
    value = value.strip().strip("{}")
    if value.lower().startswith("0x"):
        value = value[2:]
    return value.lower()


def is_hash_name(value: str | None) -> bool:
    """Return whether ``value`` looks like a raw 32-bit hash."""
    if value is None:
        return False
    normalized = normalize_type(value)
    return bool(normalized and normalized.startswith("0x") and len(normalized) == 10)
