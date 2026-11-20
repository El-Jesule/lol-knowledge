"""Comprehensive validation and spot-check tests for all published champion kits (CH-01)."""

from __future__ import annotations

from fractions import Fraction as F
from pathlib import Path

import pytest

from lol_knowledge.kit import ability_damage, load_kit, passive_contributions
from lol_knowledge.objects import load_catalog
from lol_knowledge.passives import sheet_passive_effects
from lol_knowledge.rotation import evaluate_rotation, parse_steps
from lol_knowledge.scenario import Target
from lol_knowledge.stats import (
    Label,
    build_stat_sheet,
    load_champion,
    load_issues,
    load_items,
    load_records,
)

ROOT = Path(__file__).resolve().parents[1]
CHAMPIONS_DIR = ROOT / "lol-knowledge" / "champions"
ISSUES = load_issues(ROOT)
RECORDS = load_records(ROOT)
CATALOG = load_catalog(ROOT)


def _published_kit_ids() -> list[str]:
    return sorted(path.parent.name for path in CHAMPIONS_DIR.glob("*/kit.json"))


def _sheet(
    champion_id: str,
    level: int,
    item_ids: tuple[str, ...] = (),
    *,
    learned: dict[str, int] | None = None,
    inputs: dict[str, F] | None = None,
    include_stacking: bool = True,
):
    champ = load_champion(ROOT, champion_id)
    loaded = load_items(ROOT, list(item_ids)) if item_ids else ()
    kit = load_kit(ROOT, champion_id)
    extras = list(passive_contributions(kit, learned or {})) if kit is not None else []
    passive_fx = sheet_passive_effects(kit, level, inputs, include_stacking=include_stacking)
    extras.extend(passive_fx.flats)
    return build_stat_sheet(
        champ,
        level,
        loaded,
        issues=ISSUES,
        derived=RECORDS,
        extras=extras,
        extra_amplifiers=passive_fx.amplifiers,
    )


def _target(
    *,
    armor: F = F(0),
    mr: F = F(0),
    max_health: F = F(2000),
    current_health: F = F(1000),
    kind: str = "champion",
) -> Target:
    return Target(
        armor=armor,
        magic_resist=mr,
        stats={"max_health": max_health, "current_health": current_health},
        label=Label.OFFICIAL,
        description="dummy",
        kind=kind,
    )


def test_published_kits_count_reaches_wave_1_target():
    ids = _published_kit_ids()
    assert len(ids) >= 40
    for expected in (
        "Ahri",
        "Zaahen",
        "Jax",
        "Darius",
        "Malphite",
        "Pantheon",
        "Annie",
        "Lux",
        "Veigar",
        "Syndra",
        "Ezreal",
        "Garen",
        "Brand",
        "Vayne",
        "Leona",
        "Nautilus",
    ):
        assert expected in ids


@pytest.mark.parametrize("champion_id", _published_kit_ids())
def test_every_published_kit_evaluates_all_cases_and_timeline_rotation(champion_id: str):
    kit = load_kit(ROOT, champion_id)
    assert kit is not None
    learned = {
        slot: ability.max_rank
        for slot, ability in kit.abilities.items()
        if slot in ("Q", "W", "E", "R")
    }
    # Give non-zero AD, AP, bonus HP and bonus Armor so every stat scaling evaluates cleanly.
    items = ("1058", "1037", "1028", "1031")
    target_stats = {
        "max_health": F(2000),
        "current_health": F(1000),
        "missing_fraction_health": F(1, 2),
    }

    for level in (11, 18):
        sheet = _sheet(champion_id, level, items, learned=learned)
        for slot, ability in kit.abilities.items():
            if not ability.cases:
                continue
            parts = ability_damage(
                kit,
                slot,
                ability.max_rank,
                sheet,
                target=target_stats,
            )
            assert parts, f"{champion_id} {slot} returned no parts"
            for part in parts:
                assert part.raw > 0, (
                    f"{champion_id} {slot}.{part.case}[{part.index}] raw={part.raw} <= 0"
                )

    # Also verify a real --timeline rotation using the first non-recast case of each active slot.
    sheet18 = _sheet(champion_id, 18, items, learned=learned, include_stacking=False)
    step_tokens: list[str] = ["attack"]
    for slot in ("Q", "W", "E", "R"):
        ability = kit.abilities.get(slot)
        if ability is None:
            continue
        non_recast = [case for case in ability.cases if not case.recast]
        if non_recast:
            step_tokens.append(f"{slot}.{non_recast[0].id}")
    assert len(step_tokens) >= 3
    out = evaluate_rotation(
        kit,
        sheet18,
        learned,
        _target(armor=F(80), mr=F(60), max_health=F(2000), current_health=F(1000)),
        parse_steps(", ".join(step_tokens)),
        CATALOG,
        timeline=True,
        allow_insufficient_resource=True,
    )
    assert out.total > 0
    assert len(out.steps) == len(step_tokens)


def test_jax_ap_burst_rotation_with_rabadon_and_lich_bane():
    kit = load_kit(ROOT, "Jax")
    assert kit is not None
    # Roadmap showcase: AP-burst Jax at level 18 with Rabadon (3089) + Lich Bane (3100)
    learned = {"Q": 5, "W": 5, "E": 5, "R": 3}
    sheet = _sheet("Jax", 18, ("3089", "3100"), learned=learned)
    ap = sheet["ability_power"].total()
    # 130 (Rabadon) + 100 (Lich Bane) = 230, x 1.30 (Rabadon amp) = 299 AP
    assert ap == F(299)

    e_min = ability_damage(kit, "E", 5, sheet, case="min", target={"max_health": F(2000)})
    # 160 + 0.7 * 299 = 369.3 magic + 4% * 2000 = 80 magic
    assert sum(part.raw for part in e_min) == F(160) + F(7, 10) * ap + F(80)

    r_active = ability_damage(kit, "R", 3, sheet, case="active")
    # 250 + 1.0 * 299 = 549 magic
    assert r_active[0].raw == F(250) + ap

    rot = evaluate_rotation(
        kit,
        sheet,
        learned,
        _target(armor=F(0), mr=F(0), max_health=F(2000), current_health=F(2000)),
        parse_steps("Q.leap, W.empower, attack, E.min, R.active"),
        CATALOG,
    )
    assert rot.total > F(1800)


def test_passive_stats_on_annie_darius_pantheon_and_nocturne():
    annie_sheet = _sheet("Annie", 16, learned={"R": 3})
    assert annie_sheet["magic_penetration_percent"].total() == F(1, 5)

    darius_sheet = _sheet("Darius", 18, learned={"E": 5})
    assert darius_sheet["armor_penetration_percent"].total() == F(2, 5)

    pantheon_sheet = _sheet("Pantheon", 16, learned={"R": 3})
    assert pantheon_sheet["armor_penetration_percent"].total() == F(3, 10)

    nocturne_base = _sheet("Nocturne", 18)
    nocturne_w5 = _sheet("Nocturne", 18, learned={"W": 5})
    assert nocturne_w5["attack_speed_bonus"].total() - nocturne_base[
        "attack_speed_bonus"
    ].total() == F(1, 2)


def test_veigar_phenomenal_evil_stacks_apply_in_stats_and_ability():
    kit = load_kit(ROOT, "Veigar")
    assert kit is not None
    sheet0 = _sheet("Veigar", 18, inputs={"phenomenal_evil_stacks": F(0)})
    sheet200 = _sheet("Veigar", 18, inputs={"phenomenal_evil_stacks": F(200)})
    assert sheet0["ability_power"].total() == F(0)
    assert sheet200["ability_power"].total() == F(200)

    r_max_0 = ability_damage(kit, "R", 3, sheet0, case="max")[0].raw
    r_max_200 = ability_damage(kit, "R", 3, sheet200, case="max")[0].raw
    assert r_max_200 > r_max_0


def test_true_damage_and_percent_hp_spot_checks_darius_garen_vayne_syndra():
    # Darius R: rank 3 base = 375 + 0.75 * bonus_ad; max_stacks = 2x base
    darius_kit = load_kit(ROOT, "Darius")
    assert darius_kit is not None
    darius_sheet = _sheet("Darius", 18, ("1038",))  # B.F. Sword = +40 bonus AD
    r_base = ability_damage(darius_kit, "R", 3, darius_sheet, case="base")[0].raw
    r_max = ability_damage(darius_kit, "R", 3, darius_sheet, case="max_stacks")[0].raw
    assert r_base == F(375) + F(3, 4) * F(40)
    assert r_max == r_base * 2

    # Garen R: rank 3 = 275 + 35% of missing health (50% of 2000 = 1000 -> 625 true)
    garen_kit = load_kit(ROOT, "Garen")
    assert garen_kit is not None
    garen_sheet = _sheet("Garen", 18)
    garen_r = ability_damage(
        garen_kit,
        "R",
        3,
        garen_sheet,
        case="execute",
        target={"max_health": F(2000), "missing_fraction_health": F(1, 2)},
    )[0]
    assert garen_r.damage_type == "true"
    assert garen_r.raw == F(625)

    # Vayne W: rank 5 = 10% of 2000 max HP = 200 true damage
    vayne_kit = load_kit(ROOT, "Vayne")
    assert vayne_kit is not None
    vayne_w = ability_damage(
        vayne_kit, "W", 5, _sheet("Vayne", 18), case="proc", target={"max_health": F(2000)}
    )[0]
    assert vayne_w.damage_type == "true"
    assert vayne_w.raw == F(200)

    # Syndra W evolved has both magic and true damage parts
    syndra_kit = load_kit(ROOT, "Syndra")
    assert syndra_kit is not None
    syndra_w = ability_damage(syndra_kit, "W", 5, _sheet("Syndra", 18, ("1058",)), case="evolved")
    assert [part.damage_type for part in syndra_w] == ["magic", "true"]
    assert all(part.raw > 0 for part in syndra_w)
