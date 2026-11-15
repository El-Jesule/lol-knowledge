"""Strict PROP reader tests on synthetic bins."""

from __future__ import annotations

import struct

import pytest
from binmodel.hashes import fnv1a32
from binmodel.propbin import (
    BinType as T,
)
from binmodel.propbin import (
    ListValue,
    MapValue,
    ObjectValue,
    OptionValue,
    PropError,
    Value,
    parse_prop,
)
from propbuild import encode_prop, lst, mapping, null, obj, opt, prim


def _sample() -> bytes:
    return encode_prop(
        {
            "Characters/Test/Spells/Q": (
                "SpellObject",
                {
                    "mScriptName": prim(T.STRING, "TestQ"),
                    "mSpell": obj(
                        "SpellDataResource",
                        {
                            "Cooldown": obj(
                                "{0a0eddc9}", {"values": lst(T.F32, [prim(T.F32, 8.0)])}
                            ),
                            "mCastRange": lst(T.F32, [prim(T.F32, 175.0), prim(T.F32, 175.0)]),
                            "mLink": prim(T.LINK, fnv1a32("Characters/Test/Spells/W")),
                            "mFlag": prim(T.FLAG, True),
                            "mEmpty": null(),
                            "mMaybe": opt(T.U8, prim(T.U8, 7)),
                            "mNone": opt(T.U8),
                            "mModes": mapping(
                                T.HASH,
                                T.F32,
                                [(prim(T.HASH, fnv1a32("cherry")), prim(T.F32, 0.5))],
                            ),
                            "mColor": prim(T.RGBA, (1, 2, 3, 4)),
                            "mOffset": prim(T.VEC3, (1.0, 2.0, 3.0)),
                        },
                    ),
                },
            )
        },
        linked=("data/shared.bin",),
    )


def test_parses_entries_and_every_container():
    prop = parse_prop(_sample())
    assert prop.version == 3
    assert prop.linked == ("data/shared.bin",)
    entry = prop.entries[fnv1a32("Characters/Test/Spells/Q")]
    assert entry.class_hash == fnv1a32("SpellObject")
    assert entry.fields[fnv1a32("mScriptName")] == Value(T.STRING, "TestQ")
    spell = entry.fields[fnv1a32("mSpell")]
    assert isinstance(spell, ObjectValue)
    fields = spell.fields
    assert isinstance(fields[fnv1a32("mCastRange")], ListValue)
    assert fields[fnv1a32("mCastRange")].items == (Value(T.F32, 175.0), Value(T.F32, 175.0))
    assert fields[fnv1a32("mEmpty")] == ObjectValue(T.POINTER, 0)
    assert fields[fnv1a32("mMaybe")] == OptionValue(T.U8, Value(T.U8, 7))
    assert fields[fnv1a32("mNone")] == OptionValue(T.U8, None)
    modes = fields[fnv1a32("mModes")]
    assert isinstance(modes, MapValue)
    assert modes.items == ((Value(T.HASH, fnv1a32("cherry")), Value(T.F32, 0.5)),)
    assert fields[fnv1a32("mColor")] == Value(T.RGBA, (1, 2, 3, 4))
    assert fields[fnv1a32("mFlag")] == Value(T.FLAG, True)


def test_version_one_has_no_linked_list():
    data = encode_prop({"A": ("C", {"x": prim(T.U32, 5)})}, version=1)
    prop = parse_prop(data)
    assert prop.linked == ()
    assert prop.entries[fnv1a32("A")].fields[fnv1a32("x")] == Value(T.U32, 5)


def test_ptch_header_is_skipped():
    data = b"PTCH" + struct.pack("<Q", 1) + encode_prop({"A": ("C", {})}, version=2)
    assert parse_prop(data).is_patch


def test_rejects_missing_magic():
    with pytest.raises(PropError, match="magic"):
        parse_prop(b"NOPE" + bytes(16))


def test_rejects_unsupported_version():
    with pytest.raises(PropError, match="version"):
        parse_prop(b"PROP" + struct.pack("<I", 9))


@pytest.mark.parametrize("cut", [1, 5, 20])
def test_rejects_truncated_buffers(cut):
    data = _sample()
    with pytest.raises(PropError):
        parse_prop(data[:-cut])


def test_rejects_trailing_bytes():
    with pytest.raises(PropError, match="trailing"):
        parse_prop(_sample() + b"\x00")


def test_rejects_unknown_type():
    data = bytearray(encode_prop({"A": ("C", {"x": prim(T.U8, 1)})}))
    data[-2] = 0xB5  # field type byte
    with pytest.raises(PropError, match="unknown bin type 0xb5"):
        parse_prop(bytes(data))


def test_rejects_entry_size_mismatch():
    data = bytearray(encode_prop({"A": ("C", {"x": prim(T.U8, 1)})}))
    size_offset = len(data) - (4 + 2 + 4 + 1 + 1) - 4
    (size,) = struct.unpack_from("<I", data, size_offset)
    struct.pack_into("<I", data, size_offset, size + 1)
    with pytest.raises(PropError):
        parse_prop(bytes(data))


def test_rejects_duplicate_fields():
    body = struct.pack("<IH", fnv1a32("A"), 2) + (struct.pack("<IBB", fnv1a32("x"), T.U8, 1) * 2)
    data = b"PROP" + struct.pack("<III", 3, 0, 1) + struct.pack("<I", fnv1a32("C"))
    data += struct.pack("<I", len(body)) + body
    with pytest.raises(PropError, match="duplicate field"):
        parse_prop(data)
