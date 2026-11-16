"""Health and mana regeneration per 5 s: base, growth, flat and % of base (regeneration.md)."""

from __future__ import annotations

from fractions import Fraction as F
from pathlib import Path

import pytest

from lol_knowledge.cli import main
from lol_knowledge.errors import StatsError
from lol_knowledge.objects import Snapshot, build_model
from lol_knowledge.objects.schema import DDRAGON_UNIT_CONVERSIONS
from lol_knowledge.stats import (
    STATS,
    ItemData,
    ItemStat,
    Label,
    Stacking,
    Unit,
    build_stat_sheet,
    growth_multiplier,
    items_from_model,
    load_champion,
)
from stats_helpers import PATCH, champion, item

ROOT = Path(__file__).resolve().parents[1]
RULES = "lol-knowledge/mechanics/regeneration.md"
CONVERSION = DDRAGON_UNIT_CONVERSIONS["FlatHPRegenMod"]


@pytest.mark.parametrize("stat_id", ["health_regen", "mana_regen"])
def test_registry_declares_additive_amounts_with_percent_of_base(stat_id):
    definition = STATS[stat_id]
    assert definition.resolvable
    assert definition.stacking is Stacking.ADDITIVE
    assert definition.unit is Unit.AMOUNT
    assert definition.rules == RULES
    assert definition.percent_of_base
    assert definition.item_kind == "flat"


def test_level_one_is_the_official_data_dragon_base():
    sheet = build_stat_sheet(champion(), 1)
    assert sheet["health_regen"].total() == F("7.5")
    assert sheet["mana_regen"].total() == F("8.15")
    assert sheet["health_regen"].label is Label.OFFICIAL


def test_growth_uses_the_general_formula():
    sheet = build_stat_sheet(champion(), 10)
    regen = sheet["health_regen"]
    assert regen.total() == F("7.5") + F("0.8") * growth_multiplier(10)
    assert regen.label is Label.DERIVED


def test_a_percentage_item_multiplies_the_base_including_growth():
    sheet = build_stat_sheet(champion(), 10, [item("1", ("mana_regen", "percent", 125))])
    regen = sheet["mana_regen"]
    base = F("8.15") + F("0.75") * growth_multiplier(10)
    assert regen.scoped("base") == base
    assert regen.scoped("bonus") == F("1.25") * base
    added = regen.contributions[-1]
    assert added.note == "125% of base 13.955"
    assert added.label is Label.DERIVED  # the base carries the derived growth


def test_at_level_one_a_percentage_of_an_official_base_stays_official():
    sheet = build_stat_sheet(champion(), 1, [item("1", ("health_regen", "percent", 100))])
    assert sheet["health_regen"].total() == 15
    assert sheet["health_regen"].contributions[-1].label is Label.OFFICIAL


def test_percentages_add_up_and_flat_amounts_are_added_after():
    items = [
        item("1", ("health_regen", "percent", 100)),
        item("2", ("health_regen", "percent", 50), ("health_regen", "flat", 10)),
    ]
    regen = build_stat_sheet(champion(), 1, items)["health_regen"]
    # 7.5 x (1 + 1 + 0.5) + 10
    assert regen.total() == F("7.5") * F("2.5") + 10


def test_mana_regeneration_needs_a_mana_champion():
    data = champion(partype="Energía")
    sheet = build_stat_sheet(data, 1, [item("1", ("mana_regen", "percent", 100))])
    assert sheet["mana_regen"].status == "blocked"
    assert sheet["health_regen"].status == "resolved"


def test_unknown_kinds_are_still_rejected():
    with pytest.raises(StatsError, match="unknown kind"):
        build_stat_sheet(champion(), 1, [item("1", ("health_regen", "ratio", 1))])


def test_percent_of_base_is_only_for_regeneration():
    with pytest.raises(StatsError, match="kind 'percent' is not supported for armor"):
        build_stat_sheet(champion(), 1, [item("1", ("armor", "percent", 10))])


def test_a_converted_data_dragon_value_is_derived_and_says_why():
    converted = ItemStat(
        "health_regen", "flat", F(4), "ddragon_stat", Label.DERIVED, f"unit converted: {CONVERSION}"
    )
    data = ItemData("1054", "Escudo de Doran", PATCH, (converted,))
    regen = build_stat_sheet(champion(), 1, [data])["health_regen"]
    added = regen.contributions[-1]
    assert added.value == 4 and added.label is Label.DERIVED
    assert added.note == f"unit converted: {CONVERSION}"
    assert regen.label is Label.DERIVED


def test_the_object_model_converts_flat_health_regen_to_per_five_seconds():
    snapshot = Snapshot(
        patch=PATCH,
        locale="es_ES",
        items={
            "1054": {
                "name": "Escudo de Doran",
                "description": "<stats>110 de vida</stats> Restaura 4 de vida cada 5 s.",
                "gold": {"base": 450, "total": 450, "sell": 180, "purchasable": True},
                "maps": {"11": True},
                "stats": {"FlatHPPoolMod": 110, "FlatHPRegenMod": 0.8},
                "tags": [],
            }
        },
        items_sha256="0" * 64,
    )
    catalog = {"catalog_version": 1, "objects": [{"id": "1054", "stats": [], "effects": []}]}
    model = build_model(catalog, snapshot)
    (regen,) = [s for s in model["objects"][0]["stats"] if s["id"] == "health_regen"]
    assert regen["value"] == 4.0 and regen["raw_value"] == 0.8
    assert regen["unit_conversion"] == CONVERSION
    (health,) = [s for s in model["objects"][0]["stats"] if s["id"] == "health"]
    assert "unit_conversion" not in health
    (data,) = items_from_model(model, ["1054"])
    stats = {entry.stat: entry for entry in data.stats}
    assert stats["health_regen"].value == 4 and stats["health_regen"].label is Label.DERIVED
    assert stats["health_regen"].note == f"unit converted: {CONVERSION}"
    assert stats["health"].label is Label.OFFICIAL and stats["health"].note == ""


def test_briar_has_no_base_health_regeneration():
    sheet = build_stat_sheet(load_champion(ROOT, "Briar"), 18)
    assert sheet["health_regen"].total() == 0


def test_stats_command_with_moonstone(capsys):
    code = main(
        ["stats", "--root", str(ROOT), "--champion", "Zaahen", "--level", "10", "--item", "6617"]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "  mana_regen: 31.39875 (base 13.955 + bonus 17.44375) [Derivado]" in out
    assert "  health_regen: 13.692 [Derivado]" in out
