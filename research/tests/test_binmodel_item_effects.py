"""Item effect extraction tests on synthetic bins, RST tables and WAD archives."""

from __future__ import annotations

import json
import struct

import pytest
from binmodel.hashes import fnv1a32
from binmodel.item_effects import (
    TEXT_SUFFIXES,
    build_document,
    expand_templates,
    extract_item_effects,
    main,
    placeholder_names,
    texts_from_strings,
)
from binmodel.items import ItemError
from binmodel.propbin import BinType as T
from propbuild import encode_prop, encode_wad, lst, mapping, name, obj, prim
from tools.extract_rst import MASK

VERSION = "16.22.8348910+branch.releases-16-22.content.release"


def value(label, number=None):
    fields = {"mName": prim(T.STRING, label)}
    if number is not None:
        fields["mValue"] = prim(T.F32, number)
    return obj("ItemDataValue", fields)


def values(*pairs):
    return lst(T.EMBED, [value(*pair) for pair in pairs])


def yun_tal(**extra):
    fields = {
        "mDataValues": values(
            ("CritMax", 25.0),
            ("CritPerStackMelee", 0.4),
            ("StackRangedMultiplier", 0.5),
            ("Cooldown", 30.0),
            ("Cooldown", 30.0),
            ("Later",),
        ),
        "DataValuesModeOverride": mapping(
            T.HASH,
            T.EMBED,
            [
                (
                    prim(T.HASH, name("ARAM")),
                    obj("ItemDataValues", {"DataValues": values(("CritPerStackMelee", 1.0))}),
                )
            ],
        ),
        "mEffectAmount": lst(T.F32, [prim(T.F32, 0.5), prim(T.F32, 4.0)]),
        "mItemCalculations": mapping(
            T.HASH,
            T.EMBED,
            [
                (
                    prim(T.HASH, name("CritPerStackCalc")),
                    obj(
                        "{e9a3c91d}",
                        {
                            "mFormulaParts": lst(
                                T.EMBED,
                                [
                                    obj(
                                        "NamedDataValueCalculationPart",
                                        {"mDataValue": prim(T.HASH, name("CritPerStackMelee"))},
                                    )
                                ],
                            ),
                            "mPrecision": prim(T.I32, 1),
                            "mRangedMultiplier": obj(
                                "NamedDataValueCalculationPart",
                                {"mDataValue": prim(T.HASH, name("StackRangedMultiplier"))},
                            ),
                        },
                    ),
                ),
                (
                    prim(T.HASH, name("Hidden")),
                    obj(
                        "GameCalculation",
                        {
                            "mFormulaParts": lst(
                                T.EMBED,
                                [
                                    obj("NumberCalculationPart", {"mNumber": prim(T.F32, 0.1)}),
                                    obj(
                                        "NamedDataValueCalculationPart",
                                        {"mDataValue": prim(T.HASH, name("Elsewhere"))},
                                    ),
                                ],
                            )
                        },
                    ),
                ),
            ],
        ),
        "StringCalculations": mapping(
            T.HASH,
            T.EMBED,
            [
                (
                    prim(T.HASH, name("SplitCalc")),
                    obj(
                        "{4750ceb6}",
                        {
                            "MeleeResult": prim(T.STRING, "@CritMax@"),
                            "RangedResult": prim(T.STRING, "@Cooldown@"),
                            "DefaultResult": prim(T.STRING, "@CritMax@"),
                        },
                    ),
                )
            ],
        ),
    }
    fields.update(extra)
    return ("ItemData", fields)


TOOLTIP = (
    "@CritPerStackCalc@% hasta @CritMax@% (@Cooldown@ s) @Later@ @Effect2Amount*100@ "
    "@SplitCalc@ @f1@ @spell.SummonerSmite:PetDPS@ @Missing@"
)


def test_extracts_values_calculations_and_placeholder_kinds():
    data = encode_prop({"Items/3032": yun_tal()})
    items, failures, skipped = extract_item_effects(data, ["3032"], {"3032": {"tooltip": TOOLTIP}})
    assert failures == {} and skipped == ()
    item = items["3032"]
    assert item["data_values"] == {
        "CritMax": 25.0,
        "CritPerStackMelee": 0.4,
        "StackRangedMultiplier": 0.5,
        "Cooldown": 30.0,
    }
    assert item["data_values_without_amount"] == ["Later"]
    assert item["repeated_data_values"] == ["Cooldown"]
    assert item["mode_overrides"] == {"ARAM": {"CritPerStackMelee": 1.0}}
    assert item["effect_amounts"] == [0.5, 4.0]
    assert item["calculations"] == {
        "CritPerStackCalc": {
            "class": "{e9a3c91d}",
            "mFormulaParts": [
                {"class": "NamedDataValueCalculationPart", "mDataValue": "CritPerStackMelee"}
            ],
            "mPrecision": 1,
            "mRangedMultiplier": {
                "class": "NamedDataValueCalculationPart",
                "mDataValue": "StackRangedMultiplier",
            },
        },
        f"{{{fnv1a32('Hidden'):08x}}}": {
            "class": "GameCalculation",
            "mFormulaParts": [
                {"class": "NumberCalculationPart", "mNumber": 0.1},
                {
                    "class": "NamedDataValueCalculationPart",
                    "mDataValue": f"{{{fnv1a32('Elsewhere'):08x}}}",
                },
            ],
        },
    }
    assert item["string_calculations"] == {
        "SplitCalc": {"default": "@CritMax@", "melee": "@CritMax@", "ranged": "@Cooldown@"}
    }
    assert item["texts"] == {"tooltip": TOOLTIP}
    assert item["placeholders"] == {
        "Cooldown": "data_value",
        "CritMax": "data_value",
        "CritPerStackCalc": "calculation",
        "Effect2Amount": "effect_amount",
        "Later": "data_value_without_amount",
        "Missing": None,
        "SplitCalc": "string_calculation",
        "f1": "runtime",
        "spell.SummonerSmite:PetDPS": "other_record",
    }


def test_an_item_without_effect_data_keeps_empty_fields():
    data = encode_prop({"Items/1001": ("ItemData", {"price": prim(T.U32, 300)})})
    items, failures, _ = extract_item_effects(data, ["1001"], {})
    assert failures == {}
    assert items["1001"] == {
        "data_values": None,
        "mode_overrides": {},
        "effect_amounts": None,
        "calculations": {},
        "string_calculations": {},
        "texts": {},
        "placeholders": {},
    }


def test_effect_amounts_only_cover_their_length():
    data = encode_prop({"Items/1": ("ItemData", {"mEffectAmount": lst(T.F32, [prim(T.F32, 1.0)])})})
    items, _, _ = extract_item_effects(
        data, ["1"], {"1": {"active": "@Effect1Amount@ @Effect2Amount@"}}
    )
    assert items["1"]["placeholders"] == {"Effect1Amount": "effect_amount", "Effect2Amount": None}


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"mDataValues": values(("A", 1.0), ("A", 2.0))}, "repeated with another value"),
        ({"mDataValues": values(("A",), ("A",))}, "'A' is repeated"),
        ({"mDataValues": values(("A",), ("A", 1.0))}, "'A' is repeated"),
        ({"mDataValues": values(("A", 1.0), ("A",))}, "'A' is repeated"),
        ({"mDataValues": prim(T.U32, 1)}, "data values are not a list"),
        ({"mEffectAmount": lst(T.U32, [prim(T.U32, 1)])}, "mEffectAmount is not a list of floats"),
        ({"mItemCalculations": prim(T.U32, 1)}, "mItemCalculations is not a map"),
        (
            {
                "DataValuesModeOverride": mapping(
                    T.HASH,
                    T.EMBED,
                    [
                        (
                            prim(T.HASH, name("ARAM")),
                            obj("ItemDataValues", {"DataValues": values(("A",))}),
                        )
                    ],
                )
            },
            "override without mValue",
        ),
        (
            {
                "StringCalculations": mapping(
                    T.HASH,
                    T.EMBED,
                    [(prim(T.HASH, name("S")), obj("X", {"Other": prim(T.STRING, "@A@")}))],
                )
            },
            "StringCalculations.{",
        ),
    ],
)
def test_malformed_records_are_failures(fields, message):
    data = encode_prop({"Items/1": ("ItemData", fields)})
    items, failures, _ = extract_item_effects(data, ["1"], {})
    assert items == {}
    assert message in failures["1"]


def test_missing_and_foreign_records_are_failures():
    data = encode_prop({"Items/1": ("SpellObject", {})})
    items, failures, _ = extract_item_effects(data, ["1", "2"], {})
    assert items == {}
    assert failures["1"] == f"record class 0x{fnv1a32('SpellObject'):08x} is not ItemData"
    assert failures["2"] == "no record"


def test_placeholder_names_and_templates():
    assert placeholder_names(["@B*100@ y @A@", "@A@ @ C @"]) == ["A", "B", "C"]
    assert placeholder_names([]) == []
    strings = {"item_cooldown": "(@Cooldown@ s)"}
    assert expand_templates("{{ Item_Cooldown }} {{ Unknown }}", strings) == (
        "(@Cooldown@ s) {{ Unknown }}"
    )
    texts = texts_from_strings(
        {
            "item_1_tooltip": "x {{ Item_Cooldown }}",
            "item_1_name": "nombre",
            "item_2_active": "y",
            **strings,
        },
        ["1", "2", "3"],
    )
    assert texts == {"1": {"tooltip": "x (@Cooldown@ s)"}, "2": {"active": "y"}, "3": {}}
    assert TEXT_SUFFIXES == ("tooltip", "active")


def test_build_document_needs_a_content_version():
    with pytest.raises(ItemError, match="is not <major>"):
        build_document(
            {},
            {},
            (),
            bin_sha256="0",
            strings_sha256="0",
            locale="es_ES",
            content_version="16.22",
            retrieved_at="2026-11-16",
        )


def _rst(entries):
    blob = b""
    slots = b""
    for key, text in entries:
        slots += struct.pack("<Q", (len(blob) << 38) | (key & MASK))
        blob += text.encode("utf-8") + b"\0"
    return b"RST\x05" + struct.pack("<I", len(entries)) + slots + blob


def test_main_writes_the_document(tmp_path, capsys):
    wad = tmp_path / "Global.wad.client"
    wad.write_bytes(encode_wad({"items": (3, encode_prop({"Items/3032": yun_tal()}))}))
    strings = tmp_path / "Global.es_ES.wad.client"
    strings.write_bytes(
        encode_wad(
            {
                "data/menu/es_es/lol.stringtable": (
                    3,
                    _rst([(11, "@CritMax@ {{ Item_Cooldown }}"), (12, "(@Cooldown@ s)")]),
                )
            }
        )
    )
    hashes = tmp_path / "hashes.rst.xxh3.txt"
    hashes.write_text("000000000000000b item_3032_tooltip\n000000000000000c Item_Cooldown\n")
    output = tmp_path / "out.json"
    args = [
        "--wad", str(wad), "--strings", str(strings), "--rst-hashes", str(hashes),
        "--content-version", VERSION, "--retrieved-at", "2026-11-16", "--output", str(output),
    ]  # fmt: skip
    assert main([*args, "--ids", "3032"]) == 0
    assert "items: 1  failures: 0" in capsys.readouterr().out
    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["schema"] == "lol-derived-item-effects/1"
    assert document["label"] == "Derivado"
    assert document["game_version"] == "16.22"
    assert document["locale"] == "es_ES"
    assert len(document["bin_sha256"]) == 64 and len(document["strings_sha256"]) == 64
    assert document["items"]["3032"]["texts"] == {"tooltip": "@CritMax@ (@Cooldown@ s)"}
    assert document["failures"] == {}

    ids = tmp_path / "catalog-stats.json"
    ids.write_text(json.dumps({"objects": [{"id": "3032"}, {"id": "9"}]}), encoding="utf-8")
    assert main([*args, "--ids-from", str(ids)]) == 1
    assert json.loads(output.read_text(encoding="utf-8"))["failures"] == {"9": "no record"}
    ids.write_text("{}", encoding="utf-8")
    assert main([*args, "--ids-from", str(ids)]) == 2
    assert "no 'objects' list" in capsys.readouterr().err
