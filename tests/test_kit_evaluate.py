"""Ability damage from a kit and a stat sheet, end to end with the mitigation engine."""

from __future__ import annotations

from fractions import Fraction as F
from pathlib import Path

import pytest

from lol_knowledge.damage import Modifiers, mitigate
from lol_knowledge.errors import KitError
from lol_knowledge.kit import ability_damage, load_kit, parse_kit, passive_contributions
from lol_knowledge.stats import (
    Label,
    build_stat_sheet,
    load_champion,
    load_issues,
    load_items,
    load_records,
)
from stats_helpers import ad_growth_issue, champion, item
from test_kit_model import KIT

ROOT = Path(__file__).resolve().parents[1]


def test_ranked_damage_and_labels():
    kit = parse_kit(KIT)
    sheet = build_stat_sheet(champion(), 1)
    (part,) = ability_damage(kit, "R", 2, sheet)
    assert part.raw == 21
    assert part.label is Label.DERIVED
    assert part.case == "hit"


def test_rank_must_be_valid():
    kit = parse_kit(KIT)
    sheet = build_stat_sheet(champion(), 1)
    for rank in (0, 4, True):
        with pytest.raises(KitError, match="rank"):
            ability_damage(kit, "R", rank, sheet)


def test_kit_and_sheet_must_be_the_same_champion():
    with pytest.raises(KitError, match="kit is for"):
        ability_damage(parse_kit(KIT), "R", 1, build_stat_sheet(champion("Other"), 1))


def test_passive_stats_become_sheet_contributions():
    kit = parse_kit(KIT)
    extras = passive_contributions(kit, {"R": 3})
    sheet = build_stat_sheet(
        champion(), 1, [item("1", ("armor_penetration_percent", "percent", 35))], extras=extras
    )
    pen = sheet["armor_penetration_percent"]
    assert pen.sources() == (F(35, 100), F(3, 10))
    assert pen.contributions[1].note == "c"


ZAAHEN = load_kit(ROOT, "Zaahen")


def zaahen_sheet(level=16, items=("3036",), ranks=None):
    data = load_champion(ROOT, "Zaahen")
    extras = passive_contributions(ZAAHEN, ranks or {"R": 3})
    return build_stat_sheet(
        data,
        level,
        load_items(ROOT, list(items)),
        load_issues(ROOT),
        {},
        load_records(ROOT),
        extras,
    )


def test_zaahen_r_end_to_end():
    sheet = zaahen_sheet()
    bonus_ad = sheet["attack_damage"].scoped("bonus")
    (part,) = ability_damage(ZAAHEN, "R", 3, sheet)
    assert part.raw == 550 + 2 * bonus_ad == 620
    assert part.dependencies == ("rank", "bonus_attack_damage")
    pen = sheet["armor_penetration_percent"]
    result = mitigate(part.raw, part.damage_type, 150, Modifiers(percent_penetration=pen.sources()))
    assert result.resistance.effective == F("68.25")  # 150 x 0.65 x 0.70
    assert result.damage == 620 * F(100, F("168.25"))


def test_zaahen_e_edge_needs_and_uses_target_health():
    sheet = zaahen_sheet()
    with pytest.raises(KitError, match="target:max_health"):
        ability_damage(ZAAHEN, "E", 5, sheet, case="edge")
    physical, magic = ability_damage(
        ZAAHEN, "E", 5, sheet, case="edge", target={"max_health": 2500}
    )
    assert physical.raw == (120 + F(1, 2) * 35) * F(3, 2)
    assert magic.damage_type.value == "magic"
    assert magic.raw == F("0.06") * 2500


def test_zaahen_q_cases_are_alternatives():
    parts = ability_damage(ZAAHEN, "Q", 5, zaahen_sheet())
    assert [part.case for part in parts] == ["first_hit", "recast"]


def test_passive_without_cases_says_so():
    with pytest.raises(KitError, match="models no damage"):
        ability_damage(ZAAHEN, "P", 1, zaahen_sheet())


def test_blocked_stat_explains_itself():
    issue = ad_growth_issue()
    data = champion("Zaahen")
    sheet = build_stat_sheet(data, 11, issues=[issue])
    with pytest.raises(KitError, match="bonus_attack_damage.*ddragon-attack-damage-growth"):
        ability_damage(ZAAHEN, "R", 1, sheet)


def test_rank_one_r_damage_matches_the_documented_example():
    # research handoff D.4: rank 1 with 100 bonus AD -> 250 + 2 x 100 = 450
    sheet = zaahen_sheet(level=6, items=(), ranks={"R": 1})
    stats_bonus = sheet["attack_damage"].scoped("bonus")
    (part,) = ability_damage(ZAAHEN, "R", 1, sheet)
    assert part.raw == 250 + 2 * stats_bonus


def test_pending_stats_weaken_the_damage_label():
    issue = ad_growth_issue()
    sheet = build_stat_sheet(
        champion(), 11, issues=[issue], assumptions={"attackdamageperlevel": "3"}
    )
    kit = parse_kit(
        {
            **KIT,
            "abilities": {
                "R": {
                    "name": "Ult",
                    "max_rank": 3,
                    "cases": [
                        {
                            "id": "hit",
                            "name": "Hit",
                            "parts": [
                                {
                                    "damage_type": "physical",
                                    "formula": {
                                        "op": "stat",
                                        "stat": "attack_damage",
                                        "scope": "total",
                                    },
                                    "label": "Derivado",
                                    "source": "s",
                                    "damage_type_source": "t",
                                }
                            ],
                        }
                    ],
                }
            },
        }
    )
    (part,) = ability_damage(kit, "R", 1, sheet)
    assert sheet["attack_damage"].label is Label.PENDING
    assert part.label is Label.PENDING


def test_rank_is_checked_even_without_ranked_values():
    constant = {
        "damage_type": "true",
        "formula": {"op": "constant", "value": 5},
        "label": "Derivado",
        "source": "s",
        "damage_type_source": "t",
    }
    kit = parse_kit(
        {
            **KIT,
            "abilities": {
                "R": {
                    "name": "Ult",
                    "max_rank": 3,
                    "cases": [{"id": "hit", "name": "H", "parts": [constant]}],
                }
            },
        }
    )
    sheet = build_stat_sheet(champion(), 1)
    assert ability_damage(kit, "R", 3, sheet)[0].raw == 5
    with pytest.raises(KitError, match="rank must be between 1 and 3"):
        ability_damage(kit, "R", 9, sheet)
    with pytest.raises(KitError, match="rank must be between 1 and 3"):
        passive_contributions(kit, {"R": 0})
