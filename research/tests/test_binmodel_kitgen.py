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
