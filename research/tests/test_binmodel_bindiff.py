"""Binary-vs-export diff tests on synthetic bins."""

from __future__ import annotations

import json

import pytest
from binmodel.bindiff import ADDED, CHANGED, REMOVED, SHAPE, diff_prop, main
from binmodel.hashes import fnv1a32
from binmodel.propbin import BinType as T
from binmodel.propbin import parse_prop
from binmodel.xxh64 import path_hash
from propbuild import encode_prop, encode_wad, lst, mapping, null, obj, opt, prim

PATH = "Characters/Test/Spells/Q"


def _bin(**overrides):
    fields = {
        "Cooldown": obj("{0a0eddc9}", {"values": lst(T.F32, [prim(T.F32, 8.0), prim(T.F32, 7.5)])}),
        "PBonusADMax": prim(T.F32, 0.028),
        "mLink": prim(T.LINK, fnv1a32("Characters/Test/Spells/W")),
        "ImgIconPath": prim(T.FILE, path_hash("assets/test/q.dds")),
        "mModes": mapping(T.HASH, T.F32, [(prim(T.HASH, fnv1a32("cherry")), prim(T.F32, 0.01))]),
        "mEmpty": null(),
        "mMaybe": opt(T.U8),
        "mOffset": prim(T.VEC3, (1.0, 2.0, 3.0)),
        "mFlag": prim(T.FLAG, False),
    }
    fields.update(overrides)
    return parse_prop(
        encode_prop({PATH: ("SpellObject", {"mSpell": obj("SpellDataResource", fields)})})
    )


def _export(**overrides):
    spell = {
        "Cooldown": {"values": [8.0, 7.5], "__type": "{0a0eddc9}"},
        # float32 noise as CommunityDragon writes it
        "PBonusADMax": 0.02800000086426735,
        "mLink": "Characters/Test/Spells/W",
        "ImgIconPath": "assets/test/q.dds",
        "mModes": {"cherry": 0.009999999776482582},
        "mEmpty": None,
        "mMaybe": None,
        "mOffset": [1.0, 2.0, 3.0],
        "mFlag": False,
        "__type": "SpellDataResource",
    }
    spell.update(overrides)
    return {"__linked": [], PATH: {"mSpell": spell, "__type": "SpellObject"}}


def test_identical_trees_have_no_differences():
    assert diff_prop(_bin(), _export()) == []


def test_reports_changed_floats_but_not_float32_noise():
    differences = diff_prop(
        _bin(), _export(Cooldown={"values": [10.0, 7.5], "__type": "{0a0eddc9}"})
    )
    assert [(d.path, d.kind, d.old, d.new) for d in differences] == [
        (f"{PATH}.mSpell.Cooldown.values[0]", CHANGED, 10.0, 8.0)
    ]


def test_reports_added_and_removed_fields():
    binary = _bin(mNew=prim(T.U32, 1))
    export = _export(mGone=3)
    kinds = {(d.kind, d.path) for d in diff_prop(binary, export)}
    assert (ADDED, f"{PATH}.mSpell.{{{fnv1a32('mNew'):08x}}}") in kinds
    assert (REMOVED, f"{PATH}.mSpell.mGone") in kinds


def test_reports_list_length_changes_as_shape():
    differences = diff_prop(_bin(), _export(Cooldown={"values": [8.0], "__type": "{0a0eddc9}"}))
    assert [d.kind for d in differences] == [SHAPE]


def test_hash_link_and_file_strings_are_hashed_before_comparing():
    assert diff_prop(_bin(), _export(mLink=f"{{{fnv1a32('Characters/Test/Spells/W'):08x}}}")) == []
    changed = diff_prop(_bin(), _export(ImgIconPath="assets/test/other.dds"))
    assert [d.path for d in changed] == [f"{PATH}.mSpell.ImgIconPath"]


def test_map_keys_are_normalized_by_key_type():
    changed = diff_prop(_bin(), _export(mModes={"cherry": 0.02}))
    assert [(d.path, d.old, d.new) for d in changed] == [
        (f"{PATH}.mSpell.mModes{{cherry}}", 0.02, 0.01)
    ]
    removed = diff_prop(_bin(), _export(mModes={"cherry": 0.01, "aram": 1.0}))
    assert [(d.kind, d.path) for d in removed] == [(REMOVED, f"{PATH}.mSpell.mModes{{aram}}")]


def test_bool_does_not_equal_integer():
    assert [d.kind for d in diff_prop(_bin(), _export(mFlag=0))] == [CHANGED]


def test_class_change_stops_at_the_object():
    differences = diff_prop(_bin(), _export(__type="OtherClass"))
    assert [(d.path, d.kind) for d in differences] == [(f"{PATH}.mSpell.__type", CHANGED)]


def test_entries_added_and_removed():
    export = _export()
    export["Characters/Test/Gone"] = {"__type": "SpellObject"}
    binary = parse_prop(
        encode_prop(
            {
                PATH: ("SpellObject", {"mSpell": obj("SpellDataResource", {})}),
                "Characters/Test/New": ("SpellObject", {}),
            }
        )
    )
    kinds = {(d.kind, d.path) for d in diff_prop(binary, export)}
    assert (REMOVED, "Characters/Test/Gone") in kinds
    assert (ADDED, f"{{{fnv1a32('Characters/Test/New'):08x}}}") in kinds


def _files(tmp_path, binary: bytes, export: dict):
    bin_path = tmp_path / "test.bin"
    bin_path.write_bytes(binary)
    json_path = tmp_path / "test.bin.json"
    json_path.write_text(json.dumps(export), encoding="utf-8")
    return bin_path, json_path


def test_cli_reports_and_check_exit_code(tmp_path, capsysbinary):
    raw = encode_prop(
        {PATH: ("SpellObject", {"mSpell": obj("SpellDataResource", {"x": prim(T.F32, 2.0)})})}
    )
    bin_path, json_path = _files(
        tmp_path, raw, {PATH: {"mSpell": {"x": 1.0}, "__type": "SpellObject"}}
    )
    assert main(["--bin", str(bin_path), "--against", str(json_path)]) == 0
    assert main(["--bin", str(bin_path), "--against", str(json_path), "--check"]) == 1
    out = capsysbinary.readouterr().out.decode("utf-8")
    assert "differences: 1" in out
    assert f"changed: {PATH}.mSpell.x: 1.0 -> 2.0" in out


def test_cli_json_report_reads_from_a_wad(tmp_path, capsysbinary):
    raw = encode_prop({PATH: ("SpellObject", {})})
    wad = tmp_path / "Test.wad.client"
    wad.write_bytes(encode_wad({"data/characters/test/test.bin": (3, raw)}))
    json_path = tmp_path / "ref.json"
    json_path.write_text(json.dumps({PATH: {"__type": "SpellObject"}}), encoding="utf-8")
    code = main(
        [
            "--wad",
            str(wad),
            "--entry",
            "data/characters/test/test.bin",
            "--against",
            str(json_path),
            "--json",
            "--check",
        ]
    )
    report = json.loads(capsysbinary.readouterr().out.decode("utf-8"))
    assert code == 0
    assert report["entries"] == 1
    assert report["differences"] == []
    assert report["source"]["entry"] == "data/characters/test/test.bin"


@pytest.mark.parametrize(
    ("binary", "reference"),
    [(b"NOTPROP", "{}"), (encode_prop({}), "[]"), (encode_prop({}), "{not json")],
)
def test_cli_invalid_inputs_exit_2(tmp_path, capsys, binary, reference):
    bin_path = tmp_path / "x.bin"
    bin_path.write_bytes(binary)
    json_path = tmp_path / "x.json"
    json_path.write_text(reference, encoding="utf-8")
    assert main(["--bin", str(bin_path), "--against", str(json_path)]) == 2
    assert capsys.readouterr().err.startswith("error:")


def test_cli_wad_requires_entry(tmp_path):
    with pytest.raises(SystemExit) as exc:
        main(["--wad", str(tmp_path / "x"), "--against", str(tmp_path / "y")])
    assert exc.value.code == 2
