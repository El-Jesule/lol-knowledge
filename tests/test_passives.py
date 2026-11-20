"""Tests for linear_by_level formulas and champion passive effects (CH-03)."""

from __future__ import annotations

from fractions import Fraction as F

import pytest

from lol_knowledge.errors import KitError
from lol_knowledge.formula import ABILITY_OPS, FormulaError, evaluate_formula
from lol_knowledge.kit import parse_kit


def _kit_with_passive(*effects: dict) -> dict:
    return {
        "schema": "lol-champion-kit/1",
        "champion": "Testchamp",
        "label": "Derivado",
        "game_version": "16.23",
        "content_version": "16.23.test",
        "abilities": {
            "P": {
                "name": "Pasiva de prueba",
                "max_rank": 1,
                "cases": [],
                "passive_stats": [],
                "passive_effects": list(effects),
                "not_modelled": [],
            }
        },
    }


def test_linear_by_level_formula_exact_arithmetic_and_validation():
    formula = {"op": "linear_by_level", "min": 1.5, "max": 2.8}
    at_1 = evaluate_formula(formula, {}, level=1, ops=ABILITY_OPS)
    at_18 = evaluate_formula(formula, {}, level=18, ops=ABILITY_OPS)
    at_11 = evaluate_formula(formula, {}, level=11, ops=ABILITY_OPS)
    assert at_1.exact == F(3, 2)
    assert at_18.exact == F(14, 5)
    assert at_11.exact == F(3, 2) + (F(14, 5) - F(3, 2)) * F(10, 17)
    assert at_11.dependencies == ("level",)

    with pytest.raises(FormulaError, match="explicit level"):
        evaluate_formula(formula, {}, ops=ABILITY_OPS)
    with pytest.raises(FormulaError, match="outside 1..18"):
        evaluate_formula(formula, {}, level=19, ops=ABILITY_OPS)
    with pytest.raises(FormulaError, match="unsupported formula op"):
        evaluate_formula(formula, {}, level=1)  # OBJECT_OPS rejects linear_by_level


def test_passive_effect_spec_parsing_and_validation():
    kit = parse_kit(
        _kit_with_passive(
            {
                "id": "determination",
                "name": "Determinación",
                "kind": "stacking_stat",
                "stat": "attack_damage",
                "mode": "percent",
                "trigger": "champion_hit",
                "formula": {"op": "linear_by_level", "min": 1.5, "max": 2.8},
                "max_stacks": 12,
                "max_stacks_multiplier": 2,
                "duration_seconds": 5,
                "input_name": "determination_stacks",
                "label": "Derivado",
                "source": "client",
            },
            {
                "id": "takedown_heal",
                "name": "Robo de esencias",
                "kind": "heal",
                "trigger": "on_champion_takedown",
                "formula": {"op": "linear_by_level", "min": 75, "max": 165},
                "label": "Derivado",
                "source": "client",
            },
            {
                "id": "third_hit",
                "name": "Tercer golpe",
                "kind": "damage_proc",
                "trigger": "every_n_attacks",
                "every": 3,
                "damage_type": "magic",
                "formula": {"op": "constant", "value": 60},
                "label": "Derivado",
                "source": "client",
            },
        )
    )
    effects = kit.ability("P").passive_effects
    assert len(effects) == 3
    assert effects[0].max_stacks == 12 and effects[0].max_stacks_multiplier == F(2)
    assert effects[1].kind == "heal" and effects[1].trigger == "on_champion_takedown"
    assert effects[2].kind == "damage_proc" and effects[2].every == 3

    with pytest.raises(KitError, match="kind must be one of"):
        parse_kit(
            _kit_with_passive(
                {
                    "id": "bad",
                    "name": "x",
                    "kind": "aura",
                    "formula": {"op": "constant", "value": 1},
                    "label": "Derivado",
                    "source": "s",
                }
            )
        )
    with pytest.raises(KitError, match="stacking_stat requires max_stacks"):
        parse_kit(
            _kit_with_passive(
                {
                    "id": "bad",
                    "name": "x",
                    "kind": "stacking_stat",
                    "stat": "attack_damage",
                    "trigger": "champion_hit",
                    "formula": {"op": "constant", "value": 1},
                    "label": "Derivado",
                    "source": "s",
                }
            )
        )
    with pytest.raises(KitError, match="every_n_attacks requires every >= 2"):
        parse_kit(
            _kit_with_passive(
                {
                    "id": "bad",
                    "name": "x",
                    "kind": "damage_proc",
                    "trigger": "every_n_attacks",
                    "damage_type": "magic",
                    "formula": {"op": "constant", "value": 1},
                    "label": "Derivado",
                    "source": "s",
                }
            )
        )


# --- CH-03: Champion passives in stats, ability and rotation (Zaahen P, Ahri P, synthetic) ---

import json  # noqa: E402
from pathlib import Path  # noqa: E402

from lol_knowledge.cli import main  # noqa: E402
from lol_knowledge.kit import load_kit  # noqa: E402
from lol_knowledge.passives import sheet_passive_effects  # noqa: E402
from lol_knowledge.rotation import evaluate_rotation, parse_steps  # noqa: E402
from lol_knowledge.scenario import Target  # noqa: E402
from lol_knowledge.stats import (  # noqa: E402
    Label,
    build_stat_sheet,
    load_champion,
    load_issues,
    load_items,
    load_records,
)

ROOT = Path(__file__).resolve().parents[1]


def _target(
    *,
    armor: F = F(0),
    mr: F = F(0),
    max_health: F = F(5000),
    current_health: F | None = None,
    kind: str | None = "champion",
) -> Target:
    cur = max_health if current_health is None else current_health
    return Target(
        armor=armor,
        magic_resist=mr,
        stats={"max_health": max_health, "current_health": cur},
        label=Label.OFFICIAL,
        description="dummy",
        kind=kind,
    )


def _sheet(champ_id: str, level: int, items: tuple[str, ...] = ()):
    champ = load_champion(ROOT, champ_id)
    loaded = load_items(ROOT, list(items)) if items else ()
    return build_stat_sheet(
        champ,
        level,
        loaded,
        issues=load_issues(ROOT),
        derived=load_records(ROOT),
    )


def test_zaahen_determination_on_stat_sheet_and_ability_cli(capsys):
    kit = load_kit(ROOT, "Zaahen")
    assert kit is not None

    # Without input: informational note, no AD added
    no_in = sheet_passive_effects(kit, 18)
    assert no_in.amplifiers == ()
    assert any("determination_stacks" in note for note in no_in.notes)

    # At level 18: 2.8% AD per stack; at 12 stacks, doubled -> 24 * 2.8% = 67.2% AD!
    at_12 = sheet_passive_effects(kit, 18, {"determination_stacks": F(12)})
    assert len(at_12.amplifiers) == 1
    assert at_12.amplifiers[0].stat == "attack_damage"
    assert at_12.amplifiers[0].percent == F(28, 10) * 12 * 2  # 67.2%

    # CLI stats with --input determination_stacks=12 vs without
    base_args = ["stats", "--champion", "Zaahen", "--level", "18", "--root", str(ROOT), "--json"]
    assert main(base_args) == 0
    base_ad = json.loads(capsys.readouterr().out)["stats"]["attack_damage"]["total"]
    assert main([*base_args, "--input", "determination_stacks=12"]) == 0
    buffed_ad = json.loads(capsys.readouterr().out)["stats"]["attack_damage"]["total"]
    assert buffed_ad == pytest.approx(base_ad * 1.672)

    # CLI ability with --input determination_stacks=12 increases R bonus-AD scaling damage
    ab_args = [
        "ability",
        "--champion",
        "Zaahen",
        "--level",
        "18",
        "--ability",
        "R",
        "--rank",
        "3",
        "--target-armor",
        "0",
        "--target-mr",
        "0",
        "--root",
        str(ROOT),
        "--json",
    ]
    assert main(ab_args) == 0
    r_base = json.loads(capsys.readouterr().out)["cases"][0]["total"]
    assert main([*ab_args, "--input", "determination_stacks=12"]) == 0
    r_buffed = json.loads(capsys.readouterr().out)["cases"][0]["total"]
    assert r_buffed == pytest.approx(r_base + 2 * base_ad * 0.672)


def test_zaahen_determination_stacks_doubles_and_expires_in_rotation():
    kit = load_kit(ROOT, "Zaahen")
    assert kit is not None
    sheet = _sheet("Zaahen", 18)
    base_ad = sheet["attack_damage"].total()
    per_stack_pct = F(28, 10)  # 2.8% at level 18

    # 3 attacks against champion: step 1 = 0 stacks, step 2 = 1 stack, step 3 = 2 stacks
    out = evaluate_rotation(
        kit, sheet, {}, _target(kind="champion"), parse_steps("attack, attack, attack"), None
    )
    assert out.steps[0].total == base_ad
    assert out.steps[1].total == base_ad * (1 + per_stack_pct / 100)
    assert out.steps[2].total == base_ad * (1 + 2 * per_stack_pct / 100)

    # Starting at 11 stacks: step 1 has 11 stacks; step 2 hits 12 stacks and DOUBLES (x2)!
    at_11 = evaluate_rotation(
        kit,
        sheet,
        {},
        _target(kind="champion"),
        parse_steps("attack, attack"),
        None,
        inputs={"determination_stacks": F(11)},
    )
    assert at_11.steps[0].total == base_ad * (1 + 11 * per_stack_pct / 100)
    assert at_11.steps[1].total == base_ad * (1 + 24 * per_stack_pct / 100)

    # Timeline expiration: FallOffDuration = 5 s
    timed = evaluate_rotation(
        kit,
        sheet,
        {},
        _target(kind="champion"),
        parse_steps("attack, wait:4, attack, wait:5, attack"),
        None,
        timeline=True,
    )
    assert timed.steps[0].total == base_ad  # t=0: 0 stacks -> gains 1
    assert timed.steps[2].total == base_ad * (1 + per_stack_pct / 100)  # t=4 (<5s): 1 stack -> 2
    assert timed.steps[4].total == base_ad  # t=9 (5s since t=4): expired -> 0 stacks

    # Non-champion target does NOT stack Determination
    vs_monster = evaluate_rotation(
        kit, sheet, {}, _target(kind="monster"), parse_steps("attack, attack"), None
    )
    assert vs_monster.steps[0].total == base_ad
    assert vs_monster.steps[1].total == base_ad

    # Missing target.kind does not crash and emits a helpful note
    no_kind = evaluate_rotation(
        kit, sheet, {}, _target(kind=None), parse_steps("attack, attack"), None
    )
    assert no_kind.steps[1].total == base_ad
    assert any("only stacks against champions" in note for note in no_kind.notes)


def test_ahri_essence_theft_heals_on_champion_takedown_and_minion_9th_stack():
    kit = load_kit(ROOT, "Ahri")
    assert kit is not None
    # Ahri lvl 11 with Needlessly Large Rod (1058, +65 AP)
    sheet = _sheet("Ahri", 11, ("1058",))
    ap = sheet["ability_power"].total()
    expected_champ_heal = F(75) + (F(165) - F(75)) * F(10, 17) + F(3, 10) * ap

    # 1. Champion takedown heals ChampionHeal (and respects Grievous Wounds -40%)
    kill = evaluate_rotation(
        kit,
        sheet,
        {"Q": 5},
        _target(max_health=F(100), kind="champion"),
        parse_steps("Q.both"),
        None,
    )
    assert kill.lethal_step == 1
    assert len(kill.steps[0].heal_events) == 1
    assert kill.steps[0].heal_events[0].raw == expected_champ_heal
    assert kill.steps[0].heal_events[0].amount == expected_champ_heal

    kill_gw = evaluate_rotation(
        kit,
        sheet,
        {"Q": 5},
        _target(max_health=F(100), kind="champion"),
        parse_steps("Q.both"),
        None,
        inputs={"grievous_wounds": F(1)},
    )
    assert kill_gw.steps[0].heal_events[0].amount == expected_champ_heal * F(3, 5)

    # 2. Minion kill at 8/9 fragments triggers MinionHeal (35..95 + 20% AP)
    expected_minion_heal = F(35) + (F(95) - F(35)) * F(10, 17) + F(1, 5) * ap
    minion_9 = evaluate_rotation(
        kit,
        sheet,
        {"Q": 5},
        _target(max_health=F(100), kind="minion"),
        parse_steps("Q.both"),
        None,
        inputs={"essence_fragments": F(8)},
    )
    assert len(minion_9.steps[0].heal_events) == 1
    assert minion_9.steps[0].heal_events[0].raw == expected_minion_heal

    # At 7/9 fragments, 1 kill reaches 8 (< 9) -> no heal yet
    minion_8 = evaluate_rotation(
        kit,
        sheet,
        {"Q": 5},
        _target(max_health=F(100), kind="minion"),
        parse_steps("Q.both"),
        None,
        inputs={"essence_fragments": F(7)},
    )
    assert minion_8.steps[0].heal_events == ()


def test_synthetic_stat_bonus_and_damage_proc_passives():
    kit = parse_kit(
        _kit_with_passive(
            {
                "id": "bonus_armor",
                "name": "Piel férrea",
                "kind": "stat_bonus",
                "stat": "armor",
                "mode": "flat",
                "formula": {"op": "constant", "value": 15},
                "label": "Derivado",
                "source": "test",
            },
            {
                "id": "third_hit",
                "name": "Tercer golpe",
                "kind": "damage_proc",
                "trigger": "every_n_attacks",
                "every": 3,
                "damage_type": "magic",
                "formula": {"op": "constant", "value": 60},
                "label": "Derivado",
                "source": "test",
            },
        )
    )
    eff = sheet_passive_effects(kit, 1)
    assert eff.flats[0][0] == "armor" and eff.flats[0][1].value == F(15)

    ahri = load_champion(ROOT, "Ahri")
    sheet = build_stat_sheet(ahri, 1)
    kit_ahri = parse_kit(
        {
            **_kit_with_passive(
                {
                    "id": "third_hit",
                    "name": "Tercer golpe",
                    "kind": "damage_proc",
                    "trigger": "every_n_attacks",
                    "every": 3,
                    "damage_type": "magic",
                    "formula": {"op": "constant", "value": 60},
                    "label": "Derivado",
                    "source": "test",
                }
            ),
            "champion": "Ahri",
        }
    )
    out = evaluate_rotation(
        kit_ahri, sheet, {}, _target(), parse_steps("attack, attack, attack"), None
    )
    ad = sheet["attack_damage"].total()
    assert out.steps[0].total == ad
    assert out.steps[1].total == ad
    assert out.steps[2].total == ad + F(60)
