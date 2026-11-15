"""RST v5 parser tests with a synthetic chunk (no WAD, no network)."""

from __future__ import annotations

import struct

from tools.extract_rst import MASK, parse_rst, select


def _make_rst(entries: list[tuple[int, str]]) -> bytes:
    blob = b""
    slots = b""
    for key, value in entries:
        packed = ((len(blob)) << 38) | (key & MASK)
        slots += struct.pack("<Q", packed)
        blob += value.encode("utf-8") + b"\0"
    return b"RST\x05" + struct.pack("<I", len(entries)) + slots + blob


def test_parse_rst_resolves_packed_slots():
    data = _make_rst([(0x123, "Hola"), (0x456, "Mundo")])
    parsed = parse_rst(data)
    assert parsed == {0x123: "Hola", 0x456: "Mundo"}


def test_parse_rst_uses_38_bit_keys():
    data = _make_rst([(0x3FFFFFFFF, "Max")])
    parsed = parse_rst(data)
    assert list(parsed) == [0x3FFFFFFFF]


def test_select_filters_by_resolved_name():
    values = {1: "uno", 2: "dos", 3: "tres"}
    names = {1: "spell_zaahenq_tooltip", 2: "item_1001_name", 3: "spell_zaahenr_tooltip"}
    selected = select(values, names, ("spell_zaahen",))
    assert selected == {
        "spell_zaahenq_tooltip": "uno",
        "spell_zaahenr_tooltip": "tres",
    }
