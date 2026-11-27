"""Targeted tests closing survivor gaps in high-threshold mutation targets."""

from __future__ import annotations

from fractions import Fraction

import pytest

from lol_knowledge.damage.mitigation import (
    DamageType,
    Modifiers,
    damage_multiplier,
    effective_resistance,
)
from lol_knowledge.errors import RotationError, StatsError
from lol_knowledge.rotation.models import RotationOutcome, StepOutcome, Timeline, parse_steps
from lol_knowledge.stats.data import ChampionData
from lol_knowledge.stats.labels import Label
from lol_knowledge.stats.metrics import champion_resource
from lol_knowledge.stats.registry import STATS
from lol_knowledge.stats.sheet import (
    ADAPTIVE_AD_PER_AP,
    CASSIOPEIA_MS_AMP_BASE,
    HECARIM_WARPATH_BY_LEVEL,
    AttackSpeedRatio,
    Contribution,
    PostMsEffect,
    StatSheet,
    StatValue,
    _apply_cassiopeia_move_speed_passive,
    _apply_ms_conversions,
    _scaled_attack_speed,
    adaptive_stat,
)
from lol_knowledge.survival import absorb_life_heal, absorb_shield, scale_healing, scale_shield


def _minimal_champion(champ_id: str = "Lux") -> ChampionData:
    return ChampionData(
        id=champ_id,
        name=champ_id,
        patch="16.23.1",
        locale="en_US",
        resource="Mana",
        stats={},
        spells=(),
    )


def test_mitigation_zero_boundaries_and_small_positive_resist() -> None:
    mods = Modifiers(
        flat_reduction=[0],
        percent_reduction=[0],
        percent_penetration=[0],
        flat_penetration=[0],
    )
    assert effective_resistance(Fraction(0), mods).effective == Fraction(0)
    assert effective_resistance(
        Fraction(1, 2), Modifiers(percent_reduction=[Fraction(1, 2)])
    ).effective == Fraction(1, 4)
    assert effective_resistance(
        Fraction(1, 2), Modifiers(percent_penetration=[Fraction(1, 2)])
    ).effective == Fraction(1, 4)
    assert effective_resistance(
        Fraction(1, 2), Modifiers(flat_penetration=[Fraction(1, 5)])
    ).effective == Fraction(3, 10)
    assert damage_multiplier(Fraction(1, 2)) == Fraction(100) / Fraction(201, 2)


def test_survival_fractional_absorption_scaling_defaults_and_absorb_life() -> None:
    assert absorb_shield(Fraction(1, 2), DamageType.PHYSICAL, Fraction(1, 2)) == (
        Fraction(1, 2),
        Fraction(0),
    )
    assert absorb_shield(Fraction(1, 2), DamageType.PHYSICAL, Fraction(1, 4)) == (
        Fraction(1, 4),
        Fraction(1, 4),
    )
    assert scale_healing(Fraction(100)) == Fraction(100)
    assert scale_shield(Fraction(100)) == Fraction(100)

    expected = {
        1: Fraction(1),
        2: Fraction(5, 4),
        5: Fraction(2),
        6: Fraction(3),
        10: Fraction(7),
        11: Fraction(9),
        18: Fraction(23),
    }
    for lvl, heal in expected.items():
        assert absorb_life_heal(lvl) == heal


def test_adaptive_stat_ties_and_strict_comparisons() -> None:
    stat_none, lbl_none, note_none = adaptive_stat(Fraction(10), Fraction(10), None)
    assert stat_none == "attack_damage"
    assert lbl_none is Label.PENDING
    assert "absent" in note_none

    stat_zero, lbl_zero, note_zero = adaptive_stat(Fraction(10), Fraction(10), Fraction(0))
    assert stat_zero == "attack_damage"
    assert lbl_zero is Label.PENDING
    assert "absent" in note_zero

    stat_one, lbl_one, note_one = adaptive_stat(Fraction(10), Fraction(10), Fraction(1))
    assert stat_one == "ability_power"
    assert lbl_one is Label.PENDING
    assert "(1)" in note_one

    stat_ad, _, _ = adaptive_stat(Fraction(10), Fraction(9), Fraction(1))
    assert stat_ad == "attack_damage"
    stat_ap, _, _ = adaptive_stat(Fraction(9), Fraction(10), None)
    assert stat_ap == "ability_power"


def test_stat_value_empty_single_bonus_and_unknown_scope() -> None:
    empty_hp = StatValue(STATS["health"], ())
    assert empty_hp.total() == Fraction(0)
    assert empty_hp.raw() == Fraction(0)
    assert empty_hp.scoped("base") == Fraction(0)
    assert empty_hp.scoped("bonus") == Fraction(0)
    assert empty_hp.scoped("other") == Fraction(0)
    assert empty_hp.label is Label.OFFICIAL

    empty_ms = StatValue(STATS["move_speed"], ())
    assert empty_ms.total() == Fraction(110)
    assert empty_ms.soft_capped is True
    assert empty_ms.label is Label.DERIVED

    single_bonus = StatValue(
        STATS["attack_damage"],
        (Contribution(Fraction(15), "bonus", "item:1", Label.OFFICIAL),),
    )
    assert single_bonus.scoped("base") == Fraction(0)
    assert single_bonus.scoped("bonus") == Fraction(15)
    assert single_bonus.scoped("other") == Fraction(0)


def test_sheet_attack_speed_ratio_cassiopeia_and_post_ms_conversions() -> None:
    champ = _minimal_champion()
    bonus = (Contribution(Fraction(1, 2), "bonus", "item:1", Label.OFFICIAL),)

    assert (
        _scaled_attack_speed(
            champ,
            bonus,
            AttackSpeedRatio(Fraction(0), Label.DERIVED, "derived:test"),
        )
        is None
    )
    scaled = _scaled_attack_speed(
        champ,
        bonus,
        AttackSpeedRatio(Fraction(1), Label.DERIVED, "derived:test"),
    )
    assert isinstance(scaled, Contribution)
    assert scaled.value == Fraction(1, 2)

    flats = [
        Contribution(Fraction(330), "base", "base", Label.OFFICIAL),
        Contribution(Fraction(1, 2), "bonus", "bonus_ms", Label.OFFICIAL),
    ]
    _apply_cassiopeia_move_speed_passive(1, flats, [])
    assert len(flats) == 3
    assert flats[2].value == Fraction(1, 2) * CASSIOPEIA_MS_AMP_BASE

    # Hecarim at 0 bonus MS does not append Warpath AD
    ms_zero = StatValue(
        STATS["move_speed"],
        (Contribution(Fraction(345), "base", "base", Label.OFFICIAL),),
    )
    contribs_zero: dict[str, list[Contribution]] = {"attack_damage": [], "ability_power": []}
    _apply_ms_conversions(
        "Hecarim", 1, ms_zero, (), contribs_zero, ap_weight=None, holder_range=None
    )
    assert contribs_zero["attack_damage"] == []

    # Hecarim level 2 and 3 with small positive bonus MS uses the level table
    ms_half = StatValue(
        STATS["move_speed"],
        (
            Contribution(Fraction(345), "base", "base", Label.OFFICIAL),
            Contribution(Fraction(1, 2), "bonus", "ms", Label.OFFICIAL),
        ),
    )
    contribs_lvl2: dict[str, list[Contribution]] = {"attack_damage": [], "ability_power": []}
    _apply_ms_conversions(
        "Hecarim", 2, ms_half, (), contribs_lvl2, ap_weight=None, holder_range=None
    )
    assert len(contribs_lvl2["attack_damage"]) == 1
    assert contribs_lvl2["attack_damage"][0].value == Fraction(1, 2) * HECARIM_WARPATH_BY_LEVEL[1]

    contribs_lvl3: dict[str, list[Contribution]] = {"attack_damage": [], "ability_power": []}
    _apply_ms_conversions(
        "Hecarim", 3, ms_half, (), contribs_lvl3, ap_weight=None, holder_range=None
    )
    assert contribs_lvl3["attack_damage"][0].value == Fraction(1, 2) * HECARIM_WARPATH_BY_LEVEL[2]

    # PostMsEffect adaptive force and fraction bounds on crit_chance
    ms_plain = StatValue(
        STATS["move_speed"],
        (Contribution(Fraction(350), "base", "base", Label.OFFICIAL),),
    )
    adaptive_eff = (
        PostMsEffect("adaptive_force", {"op": "constant", "value": 10}, "test:af", Label.DERIVED),
    )
    contribs_ad: dict[str, list[Contribution]] = {"attack_damage": [], "ability_power": []}
    _apply_ms_conversions(
        "Lux", 1, ms_plain, adaptive_eff, contribs_ad, ap_weight=None, holder_range=None
    )
    assert len(contribs_ad["attack_damage"]) == 1
    assert contribs_ad["attack_damage"][0].value == Fraction(10) * ADAPTIVE_AD_PER_AP

    contribs_ap: dict[str, list[Contribution]] = {"attack_damage": [], "ability_power": []}
    _apply_ms_conversions(
        "Lux", 1, ms_plain, adaptive_eff, contribs_ap, ap_weight=Fraction(1), holder_range=None
    )
    assert len(contribs_ap["ability_power"]) == 1
    assert contribs_ap["ability_power"][0].value == Fraction(10)

    crit_zero_and_full = (
        PostMsEffect("crit_chance", {"op": "constant", "value": 0}, "test:c0", Label.DERIVED),
        PostMsEffect("crit_chance", {"op": "constant", "value": 100}, "test:c100", Label.DERIVED),
    )
    contribs_crit: dict[str, list[Contribution]] = {
        "attack_damage": [],
        "ability_power": [],
        "crit_chance": [],
    }
    _apply_ms_conversions(
        "Lux", 1, ms_plain, crit_zero_and_full, contribs_crit, ap_weight=None, holder_range=None
    )
    assert [c.value for c in contribs_crit["crit_chance"]] == [Fraction(0), Fraction(1)]

    with pytest.raises(StatsError):
        _apply_ms_conversions(
            "Lux",
            1,
            ms_plain,
            (
                PostMsEffect(
                    "crit_chance", {"op": "constant", "value": 101}, "test:bad", Label.DERIVED
                ),
            ),
            {"crit_chance": []},
            ap_weight=None,
            holder_range=None,
        )

    with pytest.raises(StatsError):
        _apply_ms_conversions(
            "Lux",
            1,
            ms_plain,
            (
                PostMsEffect(
                    "crit_chance", {"op": "constant", "value": -1}, "test:neg", Label.DERIVED
                ),
            ),
            {"crit_chance": []},
            ap_weight=None,
            holder_range=None,
        )


def test_registry_metrics_and_rotation_models_survivors() -> None:
    assert STATS["crit_chance"].cap == Fraction(1)

    energy_champ = ChampionData(
        id="Zed",
        name="Zed",
        patch="16.23.1",
        locale="en_US",
        resource="Energy",
        stats={"mp": Fraction(200), "mpregen": Fraction(50)},
        spells=(),
    )
    pool = champion_resource(StatSheet(energy_champ, 1, (), {}, {}))
    assert pool.kind == "energy"
    assert pool.label is Label.OFFICIAL

    with pytest.raises(RotationError, match="target count must be at least 1"):
        parse_steps("item:3153@0")

    step = StepOutcome(
        1,
        parse_steps("attack")[0],
        "attack",
        (),
        Fraction(1000),
        Label.OFFICIAL,
        shield_before=Fraction(100),
        shield_shredded=Fraction(25),
        shield_absorbed=Fraction(50),
    )
    assert step.shield_after == Fraction(25)

    outcome = RotationOutcome(
        (),
        Fraction(1000),
        Fraction(1000),
        None,
        Label.OFFICIAL,
        (),
        timeline=Timeline(attack_interval=Fraction(1), label=Label.OFFICIAL),
    )
    with pytest.raises(RotationError):
        outcome.window(Fraction(0))
    assert outcome.window(Fraction(1, 2)).seconds == Fraction(1, 2)
