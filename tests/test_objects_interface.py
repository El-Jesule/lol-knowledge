"""Tests for the damage-engine interface contract."""

from __future__ import annotations

from dataclasses import replace

import pytest

from lol_knowledge.objects import (
    ChampionState,
    DamageOutcome,
    DamageRequest,
    ImpactConditions,
    ItemSlot,
    RotationStep,
    RuneState,
    TargetProfile,
    formula_stat_requirements,
    required_stat_sheet,
    validate_request,
)


def _stats(**overrides: float) -> dict[str, float]:
    stats = {stat: 0.0 for stat in required_stat_sheet()}
    stats.update(
        {
            "attack_damage": 100.0,
            "health": 2000.0,
            "armor": 80.0,
            "magic_resist": 50.0,
            "attack_speed": 1.0,
            "crit_chance": 25.0,
            "crit_damage_bonus": 30.0,
            "ability_power": 0.0,
        }
    )
    stats.update(overrides)
    return stats


def _request() -> DamageRequest:
    return DamageRequest(
        game_version="16.20.1",
        champion=ChampionState(
            champion_id="Zaahen",
            level=18,
            ability_ranks={"q": 5, "w": 5, "e": 5, "r": 3},
            stats=_stats(),
        ),
        items=(ItemSlot("3153"), ItemSlot("3047")),
        runes=RuneState(rune_ids=(8005,), shards=("adaptive",)),
        target=TargetProfile(
            kind="champion",
            level=18,
            armor=100,
            magic_resist=60,
            health=2500,
            max_health=2500,
            bonus_health=500,
        ),
        conditions=ImpactConditions(on_hit=True, target_health_ratio=0.6),
        rotation=(RotationStep("q", rank=5, hits=1), RotationStep("r", rank=3, hits=1)),
    )


def test_complete_request_is_valid() -> None:
    assert validate_request(_request()) == ()


def test_missing_stat_key_is_not_zero() -> None:
    request = _request()
    stats = dict(request.champion.stats)
    del stats["attack_damage"]
    problems = validate_request(replace(request, champion=replace(request.champion, stats=stats)))
    assert any("missing 'attack_damage'" in problem for problem in problems)


def test_negative_or_incoherent_target_is_rejected() -> None:
    request = _request()
    target = replace(request.target, health=3000)
    assert any(
        "must not exceed" in problem
        for problem in validate_request(replace(request, target=target))
    )
    target = replace(request.target, armor=-1)
    assert any(
        "non-negative" in problem for problem in validate_request(replace(request, target=target))
    )
    target = replace(request.target, damage_reduction_percent=150)
    assert any(
        "between 0 and 100" in problem
        for problem in validate_request(replace(request, target=target))
    )


def test_unknown_target_kind_is_rejected() -> None:
    request = _request()
    target = replace(request.target, kind="tower")
    assert any(
        "target.kind" in problem for problem in validate_request(replace(request, target=target))
    )


def test_duplicate_item_is_rejected() -> None:
    request = _request()
    items = (ItemSlot("3153"), ItemSlot("3153"))
    assert any(
        "repeats item" in problem for problem in validate_request(replace(request, items=items))
    )


def test_empty_rotation_is_rejected() -> None:
    request = _request()
    assert any(
        "rotation must not be empty" in problem
        for problem in validate_request(replace(request, rotation=()))
    )


def test_invalid_condition_ratio_is_rejected() -> None:
    request = _request()
    conditions = ImpactConditions(target_health_ratio=1.5)
    assert any(
        "between 0 and 1" in problem
        for problem in validate_request(replace(request, conditions=conditions))
    )


def test_ability_rank_must_be_positive() -> None:
    request = _request()
    champion = replace(request.champion, ability_ranks={"q": 0})
    assert any(
        "positive integer" in problem
        for problem in validate_request(replace(request, champion=champion))
    )


def test_formula_requirements_separate_target_stats(object_model) -> None:
    requirements = formula_stat_requirements(object_model)
    assert requirements == {"champion": (), "target": ("current_health",)}


def test_outcome_states_are_the_four_documented_ones() -> None:
    for status in ("evaluable", "partially_evaluable", "excluded", "unreliable"):
        outcome = DamageOutcome.unevaluable(status, "reason")
        assert outcome.status == status
        assert outcome.total is None
        assert outcome.to_dict()["reasons"] == ["reason"]
    with pytest.raises(ValueError):
        DamageOutcome.unevaluable("guessed", "reason")


def test_required_stat_sheet_is_complete() -> None:
    sheet = required_stat_sheet()
    assert "attack_damage" in sheet
    assert "lethality" in sheet
    assert "magic_penetration_percent" in sheet
    assert len(sheet) == len(set(sheet))
