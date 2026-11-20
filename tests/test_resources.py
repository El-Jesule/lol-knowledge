"""Tests for ability resource costs, non-mana stat resources and rotation resource tracking."""

from __future__ import annotations

import json
from fractions import Fraction as F
from pathlib import Path

import pytest

from lol_knowledge.cli import main
from lol_knowledge.errors import KitError, StatsError
from lol_knowledge.kit import parse_kit
from lol_knowledge.stats import (
    Label,
    ability_costs,
    build_stat_sheet,
    champion_from_document,
    champion_resource,
    format_text,
    load_champion,
    to_dict,
)
from stats_helpers import PATCH, champion_document, item

ROOT = Path(__file__).resolve().parents[1]


def _minimal_kit(ability_override: dict | None = None, case_override: dict | None = None) -> dict:
    case = {
        "id": "hit",
        "name": "Golpe",
        "parts": [
            {
                "damage_type": "magic",
                "formula": {"op": "by_rank", "values": [50, 80, 110, 140, 170]},
                "label": "Derivado",
                "source": "test",
                "damage_type_source": "test",
            }
        ],
    }
    if case_override:
        case.update(case_override)
    ability = {
        "name": "Hechizo Q",
        "max_rank": 5,
        "cases": [case],
        "passive_stats": [],
        "not_modelled": [],
    }
    if ability_override:
        ability.update(ability_override)
    return {
        "schema": "lol-champion-kit/1",
        "champion": "Testchamp",
        "label": "Derivado",
        "game_version": "16.23",
        "content_version": "16.23.test",
        "abilities": {"Q": ability},
    }


def test_real_champion_spells_carry_official_costs():
    ahri = load_champion(ROOT, "Ahri")
    by_slot = {spell.slot: spell for spell in ahri.spells}
    assert by_slot["Q"].costs == (F(55), F(65), F(75), F(85), F(95))
    assert by_slot["W"].costs == (F(30),) * 5
    assert by_slot["E"].costs == (F(60),) * 5
    assert by_slot["R"].costs == (F(100),) * 3

    zed = load_champion(ROOT, "Zed")
    zed_slots = {spell.slot: spell for spell in zed.spells}
    assert zed_slots["Q"].costs == (F(75), F(70), F(65), F(60), F(55))
    assert zed_slots["R"].costs == (F(0), F(0), F(0))


@pytest.mark.parametrize(
    ("bad_cost", "match"),
    [
        ([10, 20], "one value per rank"),
        ([-5, 0, 0, 0, 0], "negative cost"),
        ("50", "one value per rank"),
    ],
)
def test_invalid_spell_costs_are_rejected(bad_cost, match):
    doc = champion_document()
    doc["spells"][0]["cost"] = bad_cost
    with pytest.raises(StatsError, match=match):
        champion_from_document(doc, patch=PATCH, locale="es_ES")


def test_champion_resource_resolves_mana_energy_none_and_other():
    ahri = load_champion(ROOT, "Ahri")
    ahri_pool = champion_resource(build_stat_sheet(ahri, 1))
    assert ahri_pool.kind == "mana"
    assert ahri_pool.maximum == F(418)
    assert ahri_pool.regen_per_5s == F(8)
    assert ahri_pool.regen_per_second == F(8, 5)
    assert ahri_pool.uses_casting_pool is True
    assert ahri_pool.label is Label.OFFICIAL

    zed = load_champion(ROOT, "Zed")
    zed_sheet = build_stat_sheet(zed, 11, [item("1", ("mana", "flat", 300), version=zed.patch)])
    assert zed_sheet["mana"].status == "blocked"
    zed_pool = champion_resource(zed_sheet)
    assert zed_pool.kind == "energy"
    assert zed_pool.maximum == F(200)
    assert zed_pool.regen_per_5s == F(50)
    assert zed_pool.regen_per_second == F(10)
    assert zed_pool.uses_casting_pool is True
    assert zed_pool.label is Label.OFFICIAL
    assert any("do not affect energy" in note for note in zed_pool.notes)

    shen = load_champion(ROOT, "Shen")
    shen_pool = champion_resource(build_stat_sheet(shen, 18))
    assert shen_pool.kind == "energy" and shen_pool.maximum == F(400)

    garen = load_champion(ROOT, "Garen")
    garen_pool = champion_resource(build_stat_sheet(garen, 11))
    assert garen_pool.kind == "none" and garen_pool.uses_casting_pool is False

    renekton = load_champion(ROOT, "Renekton")
    renekton_pool = champion_resource(build_stat_sheet(renekton, 11))
    assert renekton_pool.kind == "other"
    assert renekton_pool.maximum == F(100)
    assert renekton_pool.uses_casting_pool is False


def test_stats_report_and_cli_expose_resource_pool_and_ability_costs(capsys):
    zed = load_champion(ROOT, "Zed")
    sheet = build_stat_sheet(zed, 11)
    text = format_text(sheet)
    assert "resource pool: Energía 200, regen 50 / 5 s (10 / s) [Oficial]" in text
    assert "ability costs (Energía): [Oficial]" in text
    assert "Q" in text and "75/70/65/60/55" in text

    data = to_dict(sheet)
    assert data["metrics"]["resource"]["kind"] == "energy"
    assert data["metrics"]["resource"]["maximum"] == 200.0
    assert data["metrics"]["resource"]["regen_per_second"] == 10.0
    assert data["metrics"]["ability_costs"]["spells"][0]["costs"] == [75.0, 70.0, 65.0, 60.0, 55.0]

    code = main(["stats", "--champion", "Zed", "--level", "11", "--root", str(ROOT), "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["metrics"]["resource"]["kind"] == "energy"
    assert payload["metrics"]["ability_costs"]["resource_kind"] == "energy"


def test_ability_costs_metric_for_synthetic_champion():
    doc = champion_document()
    doc["spells"][0]["cost"] = [40, 45, 50, 55, 60]
    sheet = build_stat_sheet(champion_from_document(doc, patch=PATCH, locale="es_ES"), 1)
    costs = ability_costs(sheet)
    assert costs.spells[0].costs == (F(40), F(45), F(50), F(55), F(60))
    assert costs.label is Label.OFFICIAL


def test_kit_cost_spec_parsing_and_validation():
    doc = _minimal_kit(
        ability_override={
            "cost": {
                "resource": "health",
                "formula": {
                    "op": "percent_of",
                    "percent": 20,
                    "stat": "health",
                    "scope": "current",
                },
                "label": "Derivado",
                "source": "client",
            }
        },
        case_override={
            "cost": {
                "resource": "none",
                "formula": {"op": "constant", "value": 0},
                "label": "Derivado",
                "source": "client",
            }
        },
    )
    kit = parse_kit(doc)
    assert kit.ability("Q").cost is not None
    assert kit.ability("Q").cost.resource == "health"
    assert kit.ability("Q").case("hit").cost is not None
    assert kit.ability("Q").case("hit").cost.resource == "none"

    bad_resource = _minimal_kit(
        ability_override={
            "cost": {
                "resource": "fury",
                "formula": {"op": "constant", "value": 50},
                "label": "Derivado",
                "source": "client",
            }
        }
    )
    with pytest.raises(KitError, match="resource must be one of"):
        parse_kit(bad_resource)

    bad_rank = _minimal_kit(
        ability_override={
            "cost": {
                "resource": "mana",
                "formula": {"op": "by_rank", "values": [10, 20]},
                "label": "Derivado",
                "source": "client",
            }
        }
    )
    with pytest.raises(KitError, match="by_rank has 2 values"):
        parse_kit(bad_rank)
