"""Kit compiler tests: tooltip damage types, translation and reproducibility."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from binmodel.cli import main as extract_main
from binmodel.kitgen import KitGenError, compile_kit, main, tooltip_damage_type

RESEARCH = Path(__file__).resolve().parents[1]
ROOT = RESEARCH.parent
SPEC = RESEARCH / "kits" / "Zaahen.spec.json"
TOOLTIPS = RESEARCH / "fixtures" / "zaahen_tooltips_es_es.json"


@pytest.fixture(scope="module")
def extract(tmp_path_factory):
    output = tmp_path_factory.mktemp("kit") / "extract.json"
    code = extract_main(
        ["--input", str(RESEARCH / "fixtures" / "zaahen_extract_min.json"), "--output", str(output)]
    )
    assert code == 0
    return json.loads(output.read_text(encoding="utf-8"))


def tooltips():
    return json.loads(TOOLTIPS.read_text(encoding="utf-8"))["strings"]


@pytest.mark.parametrize(
    ("tooltip", "reference", "expected"),
    [
        ("<physicalDamage>@A@ de daño</physicalDamage>", "A", "physical"),
        ("<magicDamage>+@B*100@% de vida</magicDamage>", "B", "magic"),
        ("<trueDamage>@C@</trueDamage>", "C", "true"),
    ],
)
def test_tooltip_damage_type(tooltip, reference, expected):
    assert tooltip_damage_type(tooltip, reference) == expected


@pytest.mark.parametrize(
    "tooltip",
    ["@A@ sin etiqueta", "<physicalDamage>@A@</physicalDamage> <magicDamage>@A@</magicDamage>"],
)
def test_tooltip_damage_type_must_be_unambiguous(tooltip):
    with pytest.raises(KitGenError):
        tooltip_damage_type(tooltip, "A")


def test_reference_names_do_not_match_prefixes():
    with pytest.raises(KitGenError):
        tooltip_damage_type("<physicalDamage>@InitialDamageX@</physicalDamage>", "InitialDamage")


def test_committed_kit_is_reproducible_from_the_fixture(extract):
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    committed = json.loads(
        (ROOT / "lol-knowledge" / "champions" / "Zaahen" / "kit.json").read_text(encoding="utf-8")
    )
    assert compile_kit(extract, tooltips(), spec) == committed


def _spec(**changes):
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    spec["abilities"]["R"].update(changes)
    return spec


def test_declared_damage_type_must_match_the_tooltip(extract):
    spec = _spec(
        cases=[
            {
                "id": "slam",
                "name": "x",
                "parts": [{"calculation": "DamageEndCalc", "damage_type": "magic"}],
            }
        ]
    )
    with pytest.raises(KitGenError, match="declared 'magic', tooltip says 'physical'"):
        compile_kit(extract, tooltips(), spec)


def test_unknown_calculation_stops_compilation(extract):
    spec = _spec(cases=[{"id": "slam", "name": "x", "parts": [{"calculation": "Nope"}]}])
    with pytest.raises(KitGenError, match="no calculation named 'Nope'"):
        compile_kit(extract, tooltips(), spec)


def test_missing_data_value_stops_compilation(extract):
    spec = _spec(
        passive_stats=[
            {"stat": "armor_penetration_percent", "data_value": "Nope", "condition": "c"}
        ]
    )
    with pytest.raises(KitGenError, match="data value 'Nope'"):
        compile_kit(extract, tooltips(), spec)


def test_uncorroborated_stats_are_not_translated(extract):
    extract = copy.deepcopy(extract)  # the fixture is shared by the module
    for ability in extract["abilities"]:
        for calculation in ability["calculations"]:
            for part in calculation["tree"].get("parts", []):
                if part.get("kind") == "stat_scaled":
                    part["stat"]["formula_confidence"] = "inferred"
    with pytest.raises(KitGenError, match="not corroborated"):
        compile_kit(extract, tooltips(), json.loads(SPEC.read_text(encoding="utf-8")))


def test_cli_writes_the_kit(extract, tmp_path, capsys):
    extract_path = tmp_path / "extract.json"
    extract_path.write_text(json.dumps(extract), encoding="utf-8")
    output = tmp_path / "kit.json"
    args = [
        "--extract",
        str(extract_path),
        "--tooltips",
        str(TOOLTIPS),
        "--spec",
        str(SPEC),
        "--output",
        str(output),
    ]
    assert main(args) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["champion"] == "Zaahen"
    assert main([*args[:4], "--spec", str(tmp_path / "missing.json"), "--output", str(output)]) == 2
    assert capsys.readouterr().err.startswith("error:")


# Ahri (phase 33): a value under two damage tags, recast settings from the bin


AHRI_SPEC = RESEARCH / "kits" / "Ahri.spec.json"
AHRI_TOOLTIPS = RESEARCH / "fixtures" / "ahri_tooltips_es_es.json"
AHRI_VERSION = "16.22.8348910+branch.releases-16-22.content.release"


@pytest.fixture(scope="module")
def ahri_extract(tmp_path_factory):
    output = tmp_path_factory.mktemp("ahri") / "extract.json"
    fixture = RESEARCH / "fixtures" / "ahri_extract_min.json"
    args = ["--input", str(fixture), "--output", str(output), "--game-version", "16.22",
            "--content-version", AHRI_VERSION]  # fmt: skip
    assert extract_main(args) == 0
    return json.loads(output.read_text(encoding="utf-8"))


def ahri_tooltips():
    return json.loads(AHRI_TOOLTIPS.read_text(encoding="utf-8"))["strings"]


def test_a_value_under_two_tags_needs_a_declared_type_shown_by_the_tooltip():
    tooltip = "<magicDamage>@D@ ida</magicDamage> y <trueDamage>@D@ vuelta</trueDamage>"
    assert tooltip_damage_type(tooltip, "D", "true") == "true"
    assert tooltip_damage_type(tooltip, "D", "magic") == "magic"
    with pytest.raises(KitGenError, match="need exactly one"):
        tooltip_damage_type(tooltip, "D")
    with pytest.raises(KitGenError, match=r"declared 'physical', tooltip wraps @D@"):
        tooltip_damage_type(tooltip, "D", "physical")


def test_the_ahri_kit_is_reproducible_from_the_fixture(ahri_extract):
    spec = json.loads(AHRI_SPEC.read_text(encoding="utf-8"))
    committed = json.loads(
        (ROOT / "lol-knowledge" / "champions" / "Ahri" / "kit.json").read_text(encoding="utf-8")
    )
    assert compile_kit(ahri_extract, ahri_tooltips(), spec) == committed
    rush = committed["abilities"]["R"]
    assert (
        rush["recast_window_seconds"],
        rush["max_recasts"],
        rush["recast_interval_seconds"],
    ) == (
        15,
        2,
        1,
    )


def test_ability_power_comes_from_parts_without_mstat(ahri_extract):
    (orb,) = [item for item in ahri_extract["abilities"] if item["slot"] == "Q"]
    (calculation,) = orb["calculations"]
    stat = calculation["tree"]["parts"][1]["stat"]
    assert (stat["mStat"], stat["stat"], stat["stat_confidence"]) == (
        0,
        "ability_power",
        "corroborated",
    )


def _ahri_spec(**changes):
    spec = json.loads(AHRI_SPEC.read_text(encoding="utf-8"))
    spec["abilities"]["R"].update(changes)
    return spec


def test_recast_settings_read_from_the_bin_must_be_constant(ahri_extract):
    spec = _ahri_spec(recast_window_seconds={"data_value": "RBaseDamage"})
    with pytest.raises(KitGenError, match="RBaseDamage changes with the rank"):
        compile_kit(ahri_extract, ahri_tooltips(), spec)
    spec = _ahri_spec(recast_window_seconds=7)
    assert (
        compile_kit(ahri_extract, ahri_tooltips(), spec)["abilities"]["R"]["recast_window_seconds"]
        == 7
    )
    spec = json.loads(AHRI_SPEC.read_text(encoding="utf-8"))
    spec["abilities"]["P"]["recast_window_seconds"] = {"data_value": "X"}
    spec["abilities"]["P"]["max_rank"] = 1
    extract = copy.deepcopy(ahri_extract)
    extract["abilities"] = [item for item in extract["abilities"] if item["slot"] != "P"]
    with pytest.raises(KitGenError, match="no bin data for this ability"):
        compile_kit(extract, ahri_tooltips(), spec)


def test_explicit_max_rank_in_spec_overrides_bin_level_count(ahri_extract):
    spec = json.loads(AHRI_SPEC.read_text(encoding="utf-8"))
    spec["abilities"]["W"]["cases"] = []
    spec["abilities"]["W"]["max_rank"] = 6
    compiled = compile_kit(ahri_extract, ahri_tooltips(), spec)
    assert compiled["abilities"]["W"]["max_rank"] == 6
