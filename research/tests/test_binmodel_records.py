"""Champion record extraction tests on synthetic bins and WAD archives."""

from __future__ import annotations

import json

import pytest
from binmodel.propbin import BinType as T
from binmodel.records import (
    RecordError,
    build_document,
    extract_all,
    extract_record,
    f32_decimal,
    main,
)
from propbuild import encode_prop, encode_wad, obj, prim

MODIFIABLE = "{ce9b917b}"


def modifiable(value: float):
    return obj(MODIFIABLE, {"baseValue": prim(T.F32, value)})


def record_bin(champion: str = "Testchamp", **fields) -> bytes:
    default = {
        "baseHPModifiable": modifiable(640.0),
        "hpPerLevelModifiable": modifiable(114.0),
        "baseDamageModifiable": modifiable(63.0),
        "damagePerLevelModifiable": modifiable(4.0),
        "mrPerLevel": modifiable(2.05),
        "attackSpeedRatioModifiable": prim(T.F32, 0.625),
    }
    default.update(fields)
    return encode_prop(
        {f"Characters/{champion}/CharacterRecords/Root": ("CharacterRecord", default)}
    )


def test_extracts_fields_with_data_dragon_names():
    fields, absent = extract_record(record_bin(), "Testchamp")
    assert fields == {
        "attackdamage": 63.0,
        "attackdamageperlevel": 4.0,
        "attackspeedratio": 0.625,
        "hp": 640.0,
        "hpperlevel": 114.0,
        "spellblockperlevel": 2.05,
    }
    assert "armor" in absent and "attackdamageperlevel" not in absent


def test_absent_fields_are_reported_not_filled():
    data = encode_prop(
        {
            "Characters/Testchamp/CharacterRecords/Root": (
                "CharacterRecord",
                {"baseHPModifiable": modifiable(1.0)},
            )
        }
    )
    fields, absent = extract_record(data, "Testchamp")
    assert fields == {"hp": 1.0}
    assert "attackdamageperlevel" in absent


@pytest.mark.parametrize(
    ("value", "expected"),
    [(4.3, 4.3), (2.049999952316284, 2.05), (0.1599999964237213, 0.16), (4.2999997, 4.2999997)],
)
def test_f32_decimal(value, expected):
    assert f32_decimal(value) == expected


def test_missing_root_is_an_error():
    with pytest.raises(RecordError, match="not found"):
        extract_record(record_bin("Other"), "Testchamp")


def test_unsupported_value_is_an_error():
    with pytest.raises(RecordError, match="unsupported"):
        extract_record(record_bin(baseHPModifiable=prim(T.U32, 5)), "Testchamp")


def test_broken_bin_is_an_error():
    with pytest.raises(RecordError, match="bin"):
        extract_record(b"NOPE", "Testchamp")


def _wad_dir(tmp_path):
    directory = tmp_path / "Champions"
    directory.mkdir()
    (directory / "Testchamp.wad.client").write_bytes(
        encode_wad({"data/characters/testchamp/testchamp.bin": (3, record_bin())})
    )
    (directory / "Testchamp.es_ES.wad.client").write_bytes(b"RW")
    (directory / "Broken.wad.client").write_bytes(
        encode_wad({"data/characters/broken/broken.bin": (0, b"junk")})
    )
    return directory


def test_extract_all_reports_failures(tmp_path):
    champions, failures = extract_all(_wad_dir(tmp_path), ["Testchamp", "Broken", "Missing"])
    assert champions["Testchamp"]["fields"]["attackdamageperlevel"] == 4.0
    assert champions["Testchamp"]["bin"] == "data/characters/testchamp/testchamp.bin"
    assert len(champions["Testchamp"]["bin_sha256"]) == 64
    assert "bin" in failures["Broken"]
    assert failures["Missing"] == "no WAD archive for this champion"


def test_document_versions():
    document = build_document({}, {}, content_version="16.22.1+x", retrieved_at="2026-11-15")
    assert document["game_version"] == "16.22"
    assert document["label"] == "Derivado"
    with pytest.raises(RecordError, match="content version"):
        build_document({}, {}, content_version="nope", retrieved_at="d")


def test_cli_writes_the_document(tmp_path, capsys):
    index = tmp_path / "index.json"
    index.write_text(json.dumps([{"id": "Testchamp"}]), encoding="utf-8")
    output = tmp_path / "out" / "records.json"
    code = main(
        [
            "--wad-dir", str(_wad_dir(tmp_path)),
            "--index", str(index),
            "--content-version", "16.22.1+x",
            "--retrieved-at", "2026-11-15",
            "--output", str(output),
        ]
    )  # fmt: skip
    assert code == 0
    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["champions"]["Testchamp"]["fields"]["hp"] == 640.0
    assert document["failures"] == {}
    assert "champions: 1" in capsys.readouterr().out


@pytest.mark.parametrize("content", ["{}", "[]", '[{"name": "x"}]', '["Testchamp"]'])
def test_cli_rejects_bad_index(tmp_path, capsys, content):
    index = tmp_path / "index.json"
    index.write_text(content, encoding="utf-8")
    code = main(
        ["--wad-dir", str(tmp_path), "--index", str(index), "--content-version", "16.22.1+x",
         "--retrieved-at", "d", "--output", str(tmp_path / "o.json")]
    )  # fmt: skip
    assert code == 2
    assert capsys.readouterr().err.startswith("error:")
