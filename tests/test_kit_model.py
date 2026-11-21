"""Kit document validation."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from lol_knowledge.errors import KitError
from lol_knowledge.kit import load_kit, parse_kit
from lol_knowledge.stats import STATS, Label, Stacking, StatDef, Unit

ROOT = Path(__file__).resolve().parents[1]
FORMULA = {
    "op": "add",
    "operands": [{"op": "by_rank", "values": [10, 20, 30]}, {"op": "constant", "value": 1}],
}
PART = {
    "damage_type": "physical",
    "formula": FORMULA,
    "label": "Derivado",
    "source": "s",
    "damage_type_source": "t",
}
KIT = {
    "schema": "lol-champion-kit/1",
    "champion": "Testchamp",
    "label": "Derivado",
    "game_version": "16.22",
    "content_version": "16.22.1+x",
    "abilities": {
        "R": {
            "name": "Ult",
            "max_rank": 3,
            "cases": [{"id": "hit", "name": "Hit", "parts": [PART]}],
            "passive_stats": [
                {
                    "stat": "armor_penetration_percent",
                    "formula": {"op": "by_rank", "values": [0.1, 0.2, 0.3]},
                    "label": "Derivado",
                    "source": "s",
                    "condition": "c",
                }
            ],
        }
    },
}


def kit_with(path, value):
    document = copy.deepcopy(KIT)
    node = document
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return document


def test_parses_a_valid_kit():
    kit = parse_kit(KIT)
    ability = kit.ability("r")
    assert kit.label is Label.DERIVED
    assert ability.max_rank == 3
    assert ability.case("hit").parts[0].damage_type.value == "physical"
    assert ability.passive_stats[0].stat == "armor_penetration_percent"


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (["schema"], "x", "schema"),
        (["label"], "Seguro", "label"),
        (["abilities"], {}, "non-empty"),
        (["abilities", "X"], {}, "unknown ability slots"),
        (["abilities", "R", "max_rank"], 0, "max_rank"),
        (["abilities", "R", "cases", 0, "id"], "Hit", "snake_case"),
        (["abilities", "R", "cases", 0, "parts"], [], "must not be empty"),
        (["abilities", "R", "cases", 0, "parts", 0, "damage_type"], "fire", "damage_type"),
        (["abilities", "R", "cases", 0, "parts", 0, "source"], "", "source"),
        (["abilities", "R", "cases", 0, "parts", 0, "formula"], {"op": "nope"}, "invalid formula"),
        (["abilities", "R", "passive_stats", 0, "stat"], "charisma", "resolvable"),
        (["abilities", "R", "not_modelled"], [""], "not_modelled"),
    ],
)
def test_rejects_malformed_kits(path, value, message):
    with pytest.raises(KitError, match=message):
        parse_kit(kit_with(path, value))


def test_rank_lists_must_match_max_rank():
    with pytest.raises(KitError, match="by_rank has 3 values, the ability has 5"):
        parse_kit(kit_with(["abilities", "R", "max_rank"], 5))


def test_duplicate_case_ids():
    case = KIT["abilities"]["R"]["cases"][0]
    with pytest.raises(KitError, match="duplicate case"):
        parse_kit(kit_with(["abilities", "R", "cases"], [case, case]))


def test_unknown_case():
    with pytest.raises(KitError, match="unknown case 'edge'"):
        parse_kit(KIT).ability("R").case("edge")


def test_project_kit_loads():
    kit = load_kit(ROOT, "Zaahen")
    assert kit is not None
    assert [case.id for case in kit.ability("E").cases] == ["center", "edge"]
    assert kit.ability("R").max_rank == 3
    assert load_kit(ROOT, "NonExistentChamp") is None
    assert load_kit(ROOT, "Lux") is not None
    assert load_kit(ROOT, "Ahri").ability("R").max_recasts == 2


def test_kit_must_match_its_directory(tmp_path):
    path = tmp_path / "lol-knowledge" / "champions" / "Other" / "kit.json"
    path.parent.mkdir(parents=True)
    import json

    path.write_text(json.dumps(KIT), encoding="utf-8")
    with pytest.raises(KitError, match="is for 'Testchamp'"):
        load_kit(tmp_path, "Other")


def test_passive_stats_must_be_resolvable(monkeypatch):
    # Every registered statistic has a rule now; a test-only pending one covers the check.
    pending = StatDef("test_pending", "Prueba", Stacking.ADDITIVE, Unit.AMOUNT, None, "sin regla")
    monkeypatch.setitem(STATS, "test_pending", pending)
    with pytest.raises(KitError, match="'test_pending' is not a resolvable stat"):
        parse_kit(kit_with(["abilities", "R", "passive_stats", 0, "stat"], "test_pending"))


def test_case_multi_target_and_area_attributes():
    from fractions import Fraction as F

    doc = copy.deepcopy(KIT)
    doc["abilities"]["R"]["cases"] = [
        {"id": "aoe_uncapped", "name": "AoE", "aoe": True, "parts": [PART]},
        {"id": "bolt_3", "name": "3 bolts", "aoe": True, "max_targets": 3, "parts": [PART]},
        {
            "id": "splash",
            "name": "Splash",
            "aoe": True,
            "secondary_damage_ratio": 0.5,
            "parts": [PART],
        },
        {"id": "single", "name": "Single", "aoe": False, "max_targets": 1, "parts": [PART]},
        {"id": "undeclared", "name": "Undeclared", "parts": [PART]},
    ]
    r = parse_kit(doc).ability("R")
    assert r.case("aoe_uncapped").resolve_targets(4) == (4, F(1), False)
    assert r.case("bolt_3").resolve_targets(5) == (3, F(1), False)
    assert r.case("bolt_3").resolve_targets(2) == (2, F(1), False)
    assert r.case("splash").resolve_targets(3) == (3, F("0.5"), False)
    assert r.case("single").resolve_targets(5) == (1, F(1), False)
    assert r.case("undeclared").resolve_targets(1) == (1, F(1), False)
    assert r.case("undeclared").resolve_targets(3) == (1, F(1), True)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("aoe", "yes", "aoe must be true or false"),
        ("aoe", 1, "aoe must be true or false"),
        ("max_targets", 0, "max_targets must be an integer >= 1"),
        ("max_targets", True, "max_targets must be an integer >= 1"),
        ("max_targets", 1.5, "max_targets must be an integer >= 1"),
        ("secondary_damage_ratio", 0, "secondary_damage_ratio must be a positive number"),
        ("secondary_damage_ratio", -0.5, "secondary_damage_ratio must be a positive number"),
        ("secondary_damage_ratio", 1.5, "secondary_damage_ratio must be <= 1"),
        ("secondary_damage_ratio", True, "secondary_damage_ratio must be a positive number"),
    ],
)
def test_rejects_invalid_case_multi_target_fields(field, value, message):
    with pytest.raises(KitError, match=message):
        parse_kit(kit_with(["abilities", "R", "cases", 0, field], value))


def test_secondary_damage_ratio_cannot_be_combined_with_max_targets_one():
    doc = copy.deepcopy(KIT)
    doc["abilities"]["R"]["cases"][0]["max_targets"] = 1
    doc["abilities"]["R"]["cases"][0]["secondary_damage_ratio"] = 0.5
    with pytest.raises(KitError, match="secondary_damage_ratio cannot be used with max_targets 1"):
        parse_kit(doc)
