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


# --- Rotation resource tracking, Essence Reaver, Presence of Mind, Manaflow, Energy & Health ---

from lol_knowledge.errors import RotationError  # noqa: E402
from lol_knowledge.kit import load_kit  # noqa: E402
from lol_knowledge.rotation import evaluate_rotation, parse_steps  # noqa: E402
from lol_knowledge.rotation_report import format_text as format_rotation_text  # noqa: E402
from lol_knowledge.rotation_report import to_dict as rotation_to_dict  # noqa: E402
from lol_knowledge.runes import load_runes  # noqa: E402
from lol_knowledge.scenario import Target  # noqa: E402
from lol_knowledge.stats import load_issues, load_items, load_records  # noqa: E402


def _target(
    *,
    armor: F = F(0),
    mr: F = F(0),
    max_health: F = F(2000),
    current_health: F | None = None,
    kind: str = "champion",
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


def _real_sheet(champ_id: str, level: int, items: tuple[str, ...] = ()):
    champ = load_champion(ROOT, champ_id)
    loaded_items = load_items(ROOT, list(items)) if items else ()
    return build_stat_sheet(
        champ,
        level,
        loaded_items,
        issues=load_issues(ROOT),
        derived=load_records(ROOT),
    )


def test_ahri_rotation_tracks_mana_costs_and_free_recast():
    kit = load_kit(ROOT, "Ahri")
    assert kit is not None
    sheet = _real_sheet("Ahri", 11)
    max_mana = sheet["mana"].total()
    ranks = {"Q": 5, "W": 5, "E": 5, "R": 2}
    # Q(95) + W(30) + E(60) + R.dash(100) + R.recast(0) = 285
    out = evaluate_rotation(
        kit,
        sheet,
        ranks,
        _target(),
        parse_steps("Q.out, W.all, E, R.dash, R.recast"),
        None,
        holder_range="ranged",
    )
    assert out.resource is not None
    assert out.resource.kind == "mana"
    assert out.resource.start == max_mana
    assert out.resource.spent == F(285)
    assert out.resource.remaining == max_mana - F(285)
    assert out.steps[0].resource_cost is not None
    assert out.steps[0].resource_cost.amount == F(95)
    assert out.steps[0].resource_cost.label is Label.OFFICIAL
    assert out.steps[4].resource_cost is not None
    assert out.steps[4].resource_cost.amount == F(0)
    assert out.steps[4].resource_before == out.steps[4].resource_after


def test_insufficient_mana_refused_unless_allowed():
    kit = load_kit(ROOT, "Ahri")
    assert kit is not None
    sheet = _real_sheet("Ahri", 11)
    ranks = {"Q": 5, "R": 2}
    with pytest.raises(RotationError, match="needs 100 Maná, only 80 available"):
        evaluate_rotation(
            kit,
            sheet,
            ranks,
            _target(),
            parse_steps("R.dash"),
            None,
            start_resource=F(80),
        )
    allowed = evaluate_rotation(
        kit,
        sheet,
        ranks,
        _target(),
        parse_steps("R.dash"),
        None,
        start_resource=F(80),
        allow_insufficient_resource=True,
    )
    assert allowed.resource is not None
    assert allowed.resource.remaining == F(0)
    assert allowed.resource.insufficient_steps == (1,)
    assert allowed.steps[0].label is Label.PENDING
    assert allowed.label is Label.PENDING


def test_start_resource_validation_and_percent_input():
    kit = load_kit(ROOT, "Ahri")
    assert kit is not None
    sheet = _real_sheet("Ahri", 11)
    max_mana = sheet["mana"].total()
    out = evaluate_rotation(
        kit,
        sheet,
        {"Q": 1},
        _target(),
        parse_steps("Q.out"),
        None,
        inputs={"attacker_resource_percent": F(1, 2)},
    )
    assert out.resource is not None
    assert out.resource.start == max_mana / 2
    assert out.resource.remaining == max_mana / 2 - F(55)

    with pytest.raises(RotationError, match="not both"):
        evaluate_rotation(
            kit,
            sheet,
            {"Q": 1},
            _target(),
            parse_steps("Q.out"),
            None,
            start_resource=F(100),
            inputs={"attacker_resource_percent": F(1, 2)},
        )
    with pytest.raises(RotationError, match="must be between 0"):
        evaluate_rotation(
            kit,
            sheet,
            {"Q": 1},
            _target(),
            parse_steps("Q.out"),
            None,
            start_resource=max_mana + 1,
        )


def test_timeline_accrues_passive_mana_regen_and_manaflow_band():
    kit = load_kit(ROOT, "Ahri")
    assert kit is not None
    sheet = _real_sheet("Ahri", 11)
    max_mana = sheet["mana"].total()
    regen_per_s = sheet["mana_regen"].total() / 5

    # Spend 95 mana at t=0, wait 5 s -> gains 5 * regen_per_s = mana_regen
    plain = evaluate_rotation(
        kit,
        sheet,
        {"Q": 5},
        _target(),
        parse_steps("Q.out, wait:5"),
        None,
        timeline=True,
    )
    assert plain.resource is not None
    expected_regen = min(F(95), regen_per_s * 5)
    assert plain.resource.regenerated == expected_regen
    assert plain.resource.remaining == max_mana - F(95) + expected_regen

    # With 8226 Manaflow Band: at t=5 s, passive regen applies first, then 1% of missing mana!
    rune_data = load_runes(ROOT)
    assert rune_data is not None
    with_mf = evaluate_rotation(
        kit,
        sheet,
        {"Q": 5},
        _target(),
        parse_steps("Q.out, wait:5"),
        None,
        timeline=True,
        runes=(8226,),
        rune_data=rune_data,
    )
    assert with_mf.resource is not None
    missing_at_5 = F(95) - expected_regen
    mf_gain = missing_at_5 * F(1, 100)
    assert with_mf.resource.regenerated == expected_regen + mf_gain
    assert with_mf.resource.remaining == max_mana - F(95) + expected_regen + mf_gain


def test_essence_reaver_spellblade_restores_premitigation_mana():
    kit = load_kit(ROOT, "Zaahen")
    assert kit is not None
    # 3508 Essence Reaver gives 25% crit chance; Spellblade = 125% base AD + 50 * 0.25.
    # Mana refund = 0.5 * SpellbladeDamage (pre-mitigation, client 16.23 + wiki rev 4095269).
    sheet = _real_sheet("Zaahen", 11, ("3508",))
    base_ad = sheet["attack_damage"].scoped("base")
    crit = sheet["crit_chance"].total()
    expected_refund = F(1, 2) * (base_ad * F(125, 100) + crit * F(50))
    # Target has 200 armor to verify refund is pre-mitigation, not post-mitigation!
    out = evaluate_rotation(
        kit,
        sheet,
        {"R": 2},
        _target(armor=F(200)),
        parse_steps("R, attack"),
        None,
        holder_range="melee",
    )
    assert out.resource is not None
    assert out.resource.spent == F(100)
    assert out.resource.restored == expected_refund
    # Refund is capped by missing mana (100)
    expected_effective = min(expected_refund, F(100))
    assert out.resource.effective_restored == expected_effective
    assert out.resource.remaining == sheet["mana"].total() - F(100) + expected_effective
    assert any(ev.kind == "restore" and "3508" in ev.source for ev in out.steps[1].resource_events)


def test_presence_of_mind_melee_ranged_cooldown_and_takedown():
    rune_data = load_runes(ROOT)
    assert rune_data is not None

    # 1. Melee level 11 (Zaahen): table[11] = 20 mana on damaging champion, 8 s CD.
    z_kit = load_kit(ROOT, "Zaahen")
    assert z_kit is not None
    z_sheet = _real_sheet("Zaahen", 11)
    # R (100 mana) at t=0 -> PoM +20; wait 4 s, Q (25) -> on CD; wait 4 s (t=8), E (40) -> +20
    out_melee = evaluate_rotation(
        z_kit,
        z_sheet,
        {"Q": 5, "E": 5, "R": 2},
        _target(max_health=F(5000)),
        parse_steps("R, wait:4, Q.first_hit, wait:4, E.center"),
        None,
        holder_range="melee",
        timeline=True,
        runes=(8009,),
        rune_data=rune_data,
    )
    assert out_melee.resource is not None
    assert out_melee.resource.restored == F(40)  # 20 at t=0 + 20 at t=8
    assert len([ev for ev in out_melee.steps[0].resource_events if ev.kind == "restore"]) == 1
    assert len([ev for ev in out_melee.steps[2].resource_events if ev.kind == "restore"]) == 0
    assert len([ev for ev in out_melee.steps[4].resource_events if ev.kind == "restore"]) == 1

    # 2. Ranged level 11 (Ahri): 0.8 * 20 = 16 mana on damaging champion + 15% max mana on kill!
    a_kit = load_kit(ROOT, "Ahri")
    assert a_kit is not None
    a_sheet = _real_sheet("Ahri", 11)
    max_mana = a_sheet["mana"].total()
    out_kill = evaluate_rotation(
        a_kit,
        a_sheet,
        {"Q": 5},
        _target(max_health=F(100), current_health=F(100)),
        parse_steps("Q.both"),
        None,
        holder_range="ranged",
        start_resource=F(200),
        runes=(8009,),
        rune_data=rune_data,
    )
    assert out_kill.lethal_step == 1
    assert out_kill.resource is not None
    expected_raw = F(16) + max_mana * F(15, 100)
    assert out_kill.resource.restored == expected_raw
    assert out_kill.resource.remaining == F(200) - F(95) + expected_raw


def test_energy_champion_costs_regen_and_presence_of_mind():
    sheet = _real_sheet("Zed", 11)
    kit = parse_kit(
        {
            **_minimal_kit(),
            "champion": "Zed",
        }
    )
    rune_data = load_runes(ROOT)
    assert rune_data is not None

    # Zed Q rank 5 costs 55 energy (from Data Dragon). Start 200.
    # Q (55 -> 145), PoM restores +6 energy (-> 151); wait:4 -> passive regen +40 (10/s) -> 191;
    # wait:4 -> regen +9 (capped at 200).
    out = evaluate_rotation(
        kit,
        sheet,
        {"Q": 5},
        _target(max_health=F(5000)),
        parse_steps("Q, wait:4, wait:4"),
        None,
        timeline=True,
        runes=(8009,),
        rune_data=rune_data,
    )
    assert out.resource is not None
    assert out.resource.kind == "energy"
    assert out.resource.spent == F(55)
    assert out.resource.restored == F(6)
    assert out.resource.regenerated == F(49)
    assert out.resource.remaining == F(200)

    # Insufficient energy refused when starting with 50 energy and casting rank-5 Q (55 energy)
    with pytest.raises(RotationError, match="needs 55 Energía, only 50 available"):
        evaluate_rotation(
            kit, sheet, {"Q": 5}, _target(), parse_steps("Q"), None, start_resource=F(50)
        )

    # Takedown restores 15% of 200 = 30 energy
    kill = evaluate_rotation(
        kit,
        sheet,
        {"Q": 5},
        _target(max_health=F(100)),
        parse_steps("Q"),
        None,
        runes=(8009,),
        rune_data=rune_data,
    )
    assert kill.resource is not None
    assert kill.resource.restored == F(6) + F(30)
    assert kill.resource.remaining == F(200) - F(55) + F(36)


def test_presence_of_mind_notes_replacement_on_resourceless_champion():
    garen_sheet = _real_sheet("Garen", 11)
    kit = parse_kit({**_minimal_kit(), "champion": "Garen"})
    rune_data = load_runes(ROOT)
    assert rune_data is not None
    out = evaluate_rotation(
        kit,
        garen_sheet,
        {"Q": 5},
        _target(),
        parse_steps("Q"),
        None,
        runes=(8009,),
        rune_data=rune_data,
    )
    assert out.resource is not None and out.resource.uses_casting_pool is False
    assert any("replaced by Triumph" in note for note in out.notes)


def test_health_cost_ability_deducts_attacker_hp_and_cannot_kill_caster():
    mundo = load_champion(ROOT, "DrMundo")
    sheet = build_stat_sheet(mundo, 1)
    max_hp = sheet["health"].total()

    # 1. Explicit health cost (flat 50 HP): auto-tracks attacker HP from max_hp
    kit_flat = parse_kit(
        {
            **_minimal_kit(
                ability_override={
                    "cost": {
                        "resource": "health",
                        "formula": {"op": "constant", "value": 50},
                        "label": "Derivado",
                        "source": "client",
                    }
                }
            ),
            "champion": "DrMundo",
        }
    )
    out = evaluate_rotation(kit_flat, sheet, {"Q": 1}, _target(), parse_steps("Q"), None)
    assert out.attacker_start_health == max_hp
    assert out.attacker_remaining_health == max_hp - F(50)
    assert out.resource is not None
    assert out.resource.health_cost_spent == F(50)

    # 2. Percent current health cost: two casts of 20% current HP compound cleanly
    kit_pct = parse_kit(
        {
            **_minimal_kit(
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
                }
            ),
            "champion": "DrMundo",
        }
    )
    out_pct = evaluate_rotation(kit_pct, sheet, {"Q": 1}, _target(), parse_steps("Q, Q"), None)
    after_first = max_hp * F(4, 5)
    after_second = after_first * F(4, 5)
    assert out_pct.attacker_remaining_health == after_second
    assert out_pct.resource is not None
    assert out_pct.resource.health_cost_spent == max_hp - after_second

    # 3. Health cost cannot kill caster: starting at 30 HP and spending 50 leaves 1 HP (actual 29)
    low_pct = F(30) / max_hp
    out_low = evaluate_rotation(
        kit_flat,
        sheet,
        {"Q": 1},
        _target(),
        parse_steps("Q"),
        None,
        inputs={"attacker_health_percent": low_pct},
    )
    assert out_low.attacker_remaining_health == F(1)
    assert out_low.resource is not None
    assert out_low.resource.health_cost_spent == F(29)

    # 4. Missing health-cost declaration on DrMundo flags Pendiente de verificación
    kit_no_cost = parse_kit({**_minimal_kit(), "champion": "DrMundo"})
    warned = evaluate_rotation(kit_no_cost, sheet, {"Q": 1}, _target(), parse_steps("Q"), None)
    assert warned.steps[0].label is Label.PENDING
    assert warned.label is Label.PENDING
    assert any("health cost" in note for note in warned.notes)


def test_rotation_cli_and_reports_surface_resources(capsys):
    args = [
        "rotation",
        "--champion",
        "Ahri",
        "--level",
        "11",
        "--learned",
        "Q=5",
        "--learned",
        "R=2",
        "--steps",
        "Q.out, R.dash, R.recast",
        "--attacker-range",
        "ranged",
        "--attacker-resource",
        "300",
        "--target-armor",
        "0",
        "--target-mr",
        "0",
        "--target-max-health",
        "2000",
        "--target-kind",
        "champion",
        "--root",
        str(ROOT),
    ]
    assert main(args) == 0
    text = capsys.readouterr().out
    assert "attacker resource: Maná 300 /" in text
    assert "resource (Maná): spent 195, restored 0, remaining 105 /" in text

    assert main([*args, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["resource"]["spent"] == 195.0
    assert payload["resource"]["remaining"] == 105.0
    assert payload["steps"][0]["resource_cost"]["amount"] == 95.0
    assert payload["steps"][2]["resource_cost"]["amount"] == 0.0

    # Refusal via CLI returns exit code 2; --allow-insufficient-resource succeeds
    oom_args = [*args[: args.index("300")], "100", *args[args.index("300") + 1 :]]
    assert main(oom_args) == 2
    assert "needs 100 Maná, only 5 available" in capsys.readouterr().err
    assert main([*oom_args, "--allow-insufficient-resource", "--json"]) == 0
    oom_payload = json.loads(capsys.readouterr().out)
    assert oom_payload["resource"]["insufficient_steps"] == [2]
    assert oom_payload["weakest_input_label"] == "Pendiente de verificación"

    # Also exercise format_rotation_text & rotation_to_dict directly on Essence Reaver
    kit = load_kit(ROOT, "Zaahen")
    assert kit is not None
    sheet = _real_sheet("Zaahen", 11, ("3508",))
    t = _target()
    out = evaluate_rotation(kit, sheet, {"R": 2}, t, parse_steps("R, attack"), None)
    assert "resource restore:" in format_rotation_text(out, sheet, t, None)
    assert rotation_to_dict(out, sheet, t, None)["resource"]["restored"] > 0
