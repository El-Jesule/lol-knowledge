"""Item data value extraction tests on synthetic bins and WAD archives."""

from __future__ import annotations

import json
import struct

import pytest
from binmodel.hashes import fnv1a32
from binmodel.items import ItemError, build_document, extract_items, main
from binmodel.propbin import BinType as T
from binmodel.propbin import PropError, parse_prop
from propbuild import encode_prop, encode_wad, lst, mapping, name, obj, prim


def value(label: str, number: float):
    return obj("ItemDataValue", {"mName": prim(T.STRING, label), "mValue": prim(T.F32, number)})


def item(values, overrides=None):
    fields = {"mDataValues": lst(T.EMBED, [value(*pair) for pair in values])}
    if overrides is not None:
        fields["DataValuesModeOverride"] = mapping(
            T.HASH,
            T.EMBED,
            [
                (
                    prim(T.HASH, name(mode)),
                    obj("ItemDataValues", {"DataValues": lst(T.EMBED, [value(*p) for p in pairs])}),
                )
                for mode, pairs in overrides.items()
            ],
        )
    return ("ItemData", fields)


def items_bin(**extra) -> bytes:
    entries = {
        "Items/3153": item(
            [("MeleeValue", 0.09), ("RangedValue", 0.06), ("MonsterDamageCap", 100.0)],
            {"ARAM": [("MeleeValue", 0.12)], "{1c14db4d}": [("MeleeValue", 0.06)]},
        ),
        "Items/3036": item([("MaxBonusDamagePercent", 0.15), ("MaxBonusHealth", 1500.0)]),
    }
    entries.update(extra)
    return encode_prop(entries)


def test_extracts_data_values_and_mode_overrides():
    items, failures, skipped = extract_items(items_bin(), ["3153", "3036"])
    assert failures == {} and skipped == ()
    assert items["3153"]["data_values"] == {
        "MeleeValue": 0.09,
        "RangedValue": 0.06,
        "MonsterDamageCap": 100.0,
    }
    assert items["3153"]["mode_overrides"] == {
        "ARAM": {"MeleeValue": 0.12},
        "{1c14db4d}": {"MeleeValue": 0.06},
    }
    assert items["3036"]["mode_overrides"] == {}


def test_missing_and_malformed_records_are_failures():
    data = items_bin(
        **{
            "Items/1": ("SpellObject", {"mDataValues": lst(T.EMBED, [])}),
            "Items/2": ("ItemData", {"price": prim(T.U32, 5)}),
            "Items/3": (
                "ItemData",
                {"mDataValues": lst(T.EMBED, [value("A", 1.0), value("A", 2.0)])},
            ),
            "Items/4": (
                "ItemData",
                {"mDataValues": lst(T.EMBED, [obj("ItemDataValue", {"mValue": prim(T.F32, 1)})])},
            ),
        }
    )
    items, failures, _ = extract_items(data, ["1", "2", "3", "4", "9999"])
    assert items["2"] == {"data_values": None, "mode_overrides": {}}
    assert failures["1"].endswith("is not ItemData")
    assert "2" not in failures
    assert "repeated" in failures["3"]
    assert "without a name" in failures["4"]
    assert failures["9999"] == "no record"


def _break_first_field(data: bytes, path: str) -> bytes:
    """Overwrite the type byte of the first field of ``path`` with an unknown type."""
    needle = struct.pack("<I", fnv1a32(path))
    at = data.index(needle) + 4 + 2 + 4
    return data[:at] + bytes([0x4D]) + data[at + 1 :]


def test_unreadable_entries_are_skipped_only_when_asked():
    data = _break_first_field(items_bin(), "Items/3036")
    with pytest.raises(PropError, match="unknown bin type 0x4d"):
        parse_prop(data)
    prop = parse_prop(data, skip_unreadable=True)
    assert prop.skipped == (fnv1a32("Items/3036"),)
    assert fnv1a32("Items/3153") in prop.entries
    items, failures, skipped = extract_items(data, ["3153", "3036"])
    assert "3153" in items
    assert failures == {"3036": "unreadable record"}
    assert skipped == (fnv1a32("Items/3036"),)


def test_skipping_never_hides_a_bad_entry_size():
    data = items_bin()
    needle = struct.pack("<I", fnv1a32("Items/3036"))
    at = data.index(needle) - 4
    broken = data[:at] + struct.pack("<I", 10**6) + data[at + 4 :]
    with pytest.raises(PropError, match="exceeds the buffer"):
        parse_prop(broken, skip_unreadable=True)


def test_document_versions():
    document = build_document(
        {}, {}, (0xFF9D3409,), bin_sha256="x", content_version="16.22.1+b", retrieved_at="d"
    )
    assert document["game_version"] == "16.22"
    assert document["skipped_entries"] == ["0xff9d3409"]
    with pytest.raises(ItemError):
        build_document({}, {}, (), bin_sha256="x", content_version="16.22", retrieved_at="d")


def test_cli_reads_the_wad(tmp_path, capsys):
    wad = tmp_path / "Global.wad.client"
    wad.write_bytes(encode_wad({"items": (0, items_bin())}))
    output = tmp_path / "items.json"
    argv = ["--wad", str(wad), "--content-version", "16.22.1+b", "--retrieved-at", "d"]
    code = main([*argv, "--ids", "3153", "3036", "--output", str(output)])
    assert code == 0
    document = json.loads(output.read_text(encoding="utf-8"))
    assert list(document["items"]) == ["3036", "3153"]
    assert "items: 2" in capsys.readouterr().out
    assert main([*argv, "--ids", "3153", "1", "--output", str(output)]) == 1
    assert main([*argv[:1], str(tmp_path / "none"), *argv[2:], "--ids", "1", "--output", "x"]) == 2
