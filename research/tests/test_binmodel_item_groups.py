"""Item group extraction tests on synthetic bins and WAD archives."""

from __future__ import annotations

import json

import pytest
from binmodel.hashes import fnv1a32
from binmodel.item_groups import (
    ItemError,
    build_document,
    extract_item_groups,
    main,
    read_group_names,
)
from binmodel.propbin import BinType as T
from propbuild import encode_prop, encode_wad, lst, prim


def link(path: str):
    return prim(T.LINK, fnv1a32(path))


def group(group_id: str, **fields):
    body = {"mItemGroupID": prim(T.HASH, fnv1a32(group_id))}
    for key, value in fields.items():
        body[key] = prim(T.I32, value)
    return ("ItemGroup", body)


def item(*groups, **fields):
    body = {"mItemGroups": lst(T.LINK, [link(path) for path in groups])}
    if "max_stack" in fields:
        body["maxStack"] = prim(T.U8, fields["max_stack"])
    if "champion" in fields:
        body["mRequiredChampion"] = prim(T.STRING, fields["champion"])
    return ("ItemData", body)


BOOTS = "Items/ItemGroups/Boots"
TRINKET = "Items/ItemGroups/Trinket"
UNIQUE = "Items/ItemGroups/Unique3031"  # a path the entry list does not name


def items_bin(**extra) -> bytes:
    entries = {
        BOOTS: group("Boots", mMaxGroupOwnable=1),
        TRINKET: group("Trinket", mInventorySlotMin=6, mInventorySlotMax=6),
        UNIQUE: group("3031", mMaxGroupOwnable=1),
        "Items/1001": item(BOOTS, max_stack=1),
        "Items/3031": item(UNIQUE, max_stack=1),
        "Items/3330": item(TRINKET, max_stack=1, champion="FiddleSticks"),
        "Items/3133": item(),
    }
    entries.update(extra)
    return encode_prop(entries)


NAMES = {fnv1a32(BOOTS): BOOTS, fnv1a32(TRINKET): TRINKET}


def test_extracts_groups_limits_slots_and_champions():
    items, groups, failures, skipped = extract_item_groups(
        items_bin(), ["1001", "3031", "3330", "3133"], NAMES
    )
    assert failures == {} and skipped == ()
    boots = f"{fnv1a32(BOOTS):08x}"
    assert items["1001"] == {"groups": [boots], "max_stack": 1, "required_champion": None}
    assert groups[boots] == {
        "entry": BOOTS,
        "group_id": "Boots",
        "max_ownable": 1,
        "inventory_slot_min": None,
        "inventory_slot_max": None,
    }
    # An unnamed group keeps entry null; its id is the item id.
    unique = groups[f"{fnv1a32(UNIQUE):08x}"]
    assert unique["entry"] is None and unique["group_id"] == "3031"
    trinket = groups[f"{fnv1a32(TRINKET):08x}"]
    assert (trinket["inventory_slot_min"], trinket["inventory_slot_max"]) == (6, 6)
    assert items["3330"]["required_champion"] == "FiddleSticks"
    # A field the record leaves out is not given a default.
    assert items["3133"] == {"groups": [], "max_stack": None, "required_champion": None}


def test_missing_records_and_broken_links_are_failures():
    data = items_bin(
        **{
            "Items/1": ("SpellObject", {}),
            "Items/2": item("Items/ItemGroups/Nowhere"),
            "Items/3": ("ItemData", {"mItemGroups": prim(T.U32, 5)}),
        }
    )
    items, groups, failures, _ = extract_item_groups(data, ["1", "2", "3", "9"])
    assert items == {} and groups == {}
    assert failures["1"].endswith("is not ItemData")
    assert "is not a readable group" in failures["2"]
    assert "is not a list of links" in failures["3"]
    assert failures["9"] == "no record"


def test_read_group_names_keeps_only_item_groups():
    lines = [f"{fnv1a32(BOOTS):08x} {BOOTS}", "deadbeef Characters/Ahri", ""]
    assert read_group_names(lines) == {fnv1a32(BOOTS): BOOTS}


def test_document_header_and_version():
    document = build_document(
        {}, {}, {}, (), bin_sha256="0" * 64, content_version="16.23.1+b", retrieved_at="d"
    )
    assert document["schema"] == "lol-derived-item-groups/1"
    assert document["game_version"] == "16.23" and document["label"] == "Derivado"
    with pytest.raises(ItemError):
        build_document({}, {}, {}, (), bin_sha256="x", content_version="16", retrieved_at="d")


def test_cli_reads_the_wad(tmp_path, capsys):
    wad = tmp_path / "Global.wad.client"
    wad.write_bytes(encode_wad({"items": (0, items_bin())}))
    names = tmp_path / "hashes.binentries.txt"
    names.write_text(f"{fnv1a32(BOOTS):08x} {BOOTS}\n", encoding="utf-8")
    output = tmp_path / "item-groups.json"
    argv = ["--wad", str(wad), "--content-version", "16.23.1+b", "--retrieved-at", "d"]
    code = main(
        [*argv, "--ids", "3031", "1001", "--entry-names", str(names), "--output", str(output)]
    )
    assert code == 0
    document = json.loads(output.read_text(encoding="utf-8"))
    assert list(document["items"]) == ["1001", "3031"]
    assert document["groups"][f"{fnv1a32(BOOTS):08x}"]["entry"] == BOOTS
    assert "items: 2  groups: 2  failures: 0" in capsys.readouterr().out
    assert main([*argv, "--ids", "1001", "9", "--output", str(output)]) == 1
