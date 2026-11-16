"""Binary bin → export-shaped JSON (bin2json) on synthetic bins."""

from __future__ import annotations

import json

import pytest
from binmodel.bin2json import (
    MODE_NAMES,
    Names,
    candidates,
    load_names,
    main,
    placeholders,
    strings_of,
    to_json,
)
from binmodel.bindiff import diff_prop
from binmodel.hashes import fnv1a32
from binmodel.propbin import BinType as T
from binmodel.propbin import parse_prop
from binmodel.xxh64 import path_hash
from propbuild import encode_prop, encode_wad, lst, mapping, null, obj, opt, prim

PATH = "Characters/Test/Spells/Q"
OTHER = "Characters/Test/Spells/W"


def _fields():
    return {
        "Cooldown": obj("SpellDataValueVector", {"values": lst(T.F32, [prim(T.F32, 8.0)])}),
        "QCoeff": prim(T.F32, 0.15),
        "mLink": prim(T.LINK, fnv1a32(OTHER)),
        "mUnknownLink": prim(T.LINK, 0x12345678),
        "mDataValue": prim(T.HASH, fnv1a32("Q1BaseDamage")),
        "mCalc": prim(T.HASH, fnv1a32("InitialDamage")),
        "mName": prim(T.STRING, "Q1BaseDamage"),
        "ImgIconPath": prim(T.FILE, path_hash("assets/test/q.dds")),
        "mModes": mapping(T.HASH, T.F32, [(prim(T.HASH, fnv1a32("cherry")), prim(T.F32, 0.5))]),
        "mRanks": mapping(T.U8, T.STRING, [(prim(T.U8, 3), prim(T.STRING, "three"))]),
        "mEmpty": null(),
        "mMaybe": opt(T.U8),
        "mSome": opt(T.U8, prim(T.U8, 7)),
        "mOffset": prim(T.VEC3, (1.0, 2.0, 3.0)),
        "mMatrix": prim(T.MTX44, tuple(float(n) for n in range(16))),
        "mFlag": prim(T.FLAG, True),
    }


def _prop():
    return parse_prop(
        encode_prop(
            {PATH: ("SpellObject", {"mSpell": obj("SpellDataResource", _fields())})},
            linked=("data/shared.bin",),
        )
    )


def _names(extra=()):
    known = [
        "Cooldown", "values", "QCoeff", "mLink", "mUnknownLink", "mDataValue", "mCalc", "mName",
        "ImgIconPath", "mModes", "mRanks", "mEmpty", "mMaybe", "mSome", "mOffset", "mMatrix",
        "mFlag", "mSpell", "SpellObject", "SpellDataResource", "SpellDataValueVector",
    ]  # fmt: skip
    return Names(
        {fnv1a32(text): text for text in known},
        {fnv1a32(text): text for text in (PATH, OTHER)},
        candidates([*extra, *MODE_NAMES]),
    )


def test_an_entry_becomes_an_export_object():
    document = to_json(_prop(), _names(["Q1BaseDamage", "InitialDamage"]))
    assert document["__linked"] == ["data/shared.bin"]
    spell = document[PATH]["mSpell"]
    assert document[PATH]["__type"] == "SpellObject"
    assert list(spell)[-1] == "__type" and spell["__type"] == "SpellDataResource"
    assert spell["Cooldown"] == {"values": [8.0], "__type": "SpellDataValueVector"}
    assert spell["QCoeff"] == 0.15000000596046448  # the float32, as the exports write it
    assert spell["mLink"] == OTHER
    assert spell["mUnknownLink"] == "{12345678}"
    assert (spell["mDataValue"], spell["mCalc"]) == ("Q1BaseDamage", "InitialDamage")
    assert spell["ImgIconPath"] == f"{{{path_hash('assets/test/q.dds'):016x}}}"
    assert spell["mModes"] == {"cherry": 0.5}
    assert spell["mRanks"] == {"3": "three"}
    assert (spell["mEmpty"], spell["mMaybe"], spell["mSome"]) == (None, None, 7)
    assert spell["mOffset"] == [1.0, 2.0, 3.0]
    assert spell["mMatrix"] == [[0.0, 1.0, 2.0, 3.0], [4.0, 5.0, 6.0, 7.0],
                                [8.0, 9.0, 10.0, 11.0], [12.0, 13.0, 14.0, 15.0]]  # fmt: skip
    assert spell["mFlag"] is True


def test_unknown_names_stay_hashes_and_nothing_is_guessed():
    document = to_json(_prop(), Names({}, {}, {}))
    (key,) = [key for key in document if not key.startswith("__")]
    assert key == f"{{{fnv1a32(PATH):08x}}}"
    body = document[key]
    assert body["__type"] == f"{{{fnv1a32('SpellObject'):08x}}}"
    spell = body[f"{{{fnv1a32('mSpell'):08x}}}"]
    assert f"{{{fnv1a32('Q1BaseDamage'):08x}}}" in spell.values()


def test_a_hash_value_prefers_entries_then_candidates_then_fields():
    names = Names({1: "field"}, {1: "entry"}, {1: "candidate"})
    assert names.hashed(1) == "entry"
    assert Names({1: "field"}, {}, {1: "candidate"}).hashed(1) == "candidate"
    assert Names({1: "field"}, {}, {}).hashed(1) == "field"
    assert Names({}, {}, {1: "candidate"}).field(1) == "candidate"
    assert Names({}, {}, {1: "candidate"}).entry(1) == "candidate"


def test_the_export_matches_the_bin_for_bindiff():
    prop = _prop()
    document = to_json(prop, _names(["Q1BaseDamage", "InitialDamage"]))
    assert diff_prop(prop, document) == []


def test_candidate_names_come_from_strings_and_placeholders():
    assert strings_of(_prop()) == ["Q1BaseDamage", "three"]
    assert placeholders(["<magicDamage>@TotalDamage@</magicDamage> @Ratio*100@% y @A.B@"]) == [
        "TotalDamage",
        "Ratio",
        "A.B",
    ]
    table = candidates(["Name", "NAME", "other"])
    assert table[fnv1a32("name")] == "Name"  # the first spelling wins
    assert len(table) == 2


def test_hash_lists_are_read(tmp_path):
    (tmp_path / "hashes.binentries.txt").write_text(f"{fnv1a32(PATH):08x} {PATH}\n", "utf-8")
    (tmp_path / "hashes.binfields.txt").write_text(
        f"{fnv1a32('mSpell'):08x} mSpell\nbadline\n", "utf-8"
    )
    (tmp_path / "hashes.bintypes.txt").write_text(f"{fnv1a32('SpellObject'):08x} SpellObject\n")
    names = load_names(tmp_path, ["QCoeff"])
    assert names.entry(fnv1a32(PATH)) == PATH
    assert names.field(fnv1a32("mSpell")) == "mSpell"
    assert names.field(fnv1a32("SpellObject")) == "SpellObject"
    assert names.field(fnv1a32("QCoeff")) == "QCoeff"
    assert names.hashed(fnv1a32("ARAM")) == "ARAM"


def test_cli_converts_a_wad_entry(tmp_path, capsys):
    hashes = tmp_path / "hashes"
    hashes.mkdir()
    for name in ("hashes.binentries.txt", "hashes.binfields.txt", "hashes.bintypes.txt"):
        (hashes / name).write_text("", encoding="utf-8")
    data = encode_prop({PATH: ("SpellObject", {"mSpell": obj("SpellDataResource", _fields())})})
    wad = tmp_path / "test.wad.client"
    wad.write_bytes(encode_wad({"data/characters/test/test.bin": (3, data)}))
    tips = tmp_path / "tips.json"
    tips.write_text(json.dumps({"strings": {"q": "@InitialDamage@"}}), encoding="utf-8")
    output = tmp_path / "out.json"
    args = ["--wad", str(wad), "--entry", "data/characters/test/test.bin",
            "--hashes", str(hashes), "--names", str(tips), "--output", str(output)]  # fmt: skip
    assert main(args) == 0
    document = json.loads(output.read_text(encoding="utf-8"))
    spell = document[f"{{{fnv1a32(PATH):08x}}}"][f"{{{fnv1a32('mSpell'):08x}}}"]
    assert "InitialDamage" in spell.values() and "Q1BaseDamage" in spell.values()
    assert "unresolved names:" in capsys.readouterr().out
    assert main([*args[:4], "--hashes", str(tmp_path / "missing"), "--output", str(output)]) == 2


def test_cli_needs_an_entry_with_a_wad(tmp_path):
    with pytest.raises(SystemExit):
        main(["--wad", "x.wad", "--hashes", str(tmp_path), "--output", str(tmp_path / "o")])
