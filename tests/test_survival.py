"""Survival mechanics: heal & shield power, shields, Grievous Wounds and effect healing."""

from __future__ import annotations

from fractions import Fraction as F
from pathlib import Path

from lol_knowledge.runes import load_runes, minor_rune_effects
from lol_knowledge.stats import (
    Label,
    build_stat_sheet,
    load_champion,
    load_issues,
    load_items,
    load_records,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = load_runes(ROOT)
DERIVED = load_records(ROOT)
ISSUES = load_issues(ROOT)


def test_heal_and_shield_power_stacks_additively_from_items_and_revitalize():
    # 3107 Redemption (+10% HSP) + 3504 Ardent Censer (+10% HSP) + 8453 Revitalize (+5% HSP).
    champ = load_champion(ROOT, "Ahri")
    items = load_items(ROOT, ("3107", "3504"))
    assert DATA is not None
    eff = minor_rune_effects([8453], DATA, level=11, patch=champ.patch, items=items)
    sheet = build_stat_sheet(champ, 11, items, ISSUES, {}, DERIVED, extras=eff.flats)
    hsp = sheet["heal_and_shield_power"]
    assert hsp.total() == F(25, 100)
    assert hsp.label is Label.DERIVED


def test_jack_of_all_trades_counts_heal_and_shield_power_from_real_item():
    # 3107 Redemption has health, ability_haste, mana_regen, heal_and_shield_power -> 4 distinct.
    champ = load_champion(ROOT, "Ahri")
    items = load_items(ROOT, ("3107",))
    assert DATA is not None
    eff = minor_rune_effects([8316], DATA, level=11, patch=champ.patch, items=items)
    haste = [c for stat_id, c in eff.flats if stat_id == "ability_haste"]
    assert len(haste) == 1 and haste[0].value == 4
