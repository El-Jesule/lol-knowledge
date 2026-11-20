"""Metrics computed from a stat sheet. Pure functions: no file access."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from ..damage import DamageType, damage_multiplier
from .labels import Label, weakest
from .registry import HASTE_RULES
from .sheet import StatBlocked, StatSheet

EHP_RULES = "lol-knowledge/mechanics/effective-health.md"
RESISTANCE_FOR = {DamageType.PHYSICAL: "armor", DamageType.MAGIC: "magic_resist"}


@dataclass(frozen=True)
class EffectiveHealth:
    damage_type: DamageType
    value: Fraction | None
    label: Label
    blocked: str | None = None
    rules: str = EHP_RULES


def effective_health(sheet: StatSheet, damage_type: DamageType | str) -> EffectiveHealth:
    """Raw damage of ``damage_type`` needed to deplete the champion's health."""
    kind = DamageType(damage_type)
    health = sheet["health"]
    try:
        total = health.total()
        if kind is DamageType.TRUE:
            return EffectiveHealth(kind, total, health.label)
        resistance = sheet[RESISTANCE_FOR[kind]]
        value = total / damage_multiplier(resistance.total())
    except StatBlocked as exc:
        return EffectiveHealth(kind, None, Label.PENDING, str(exc))
    return EffectiveHealth(kind, value, weakest((health.label, resistance.label, Label.DERIVED)))


@dataclass(frozen=True)
class SpellCooldown:
    slot: str
    spell_id: str
    name: str
    base: tuple[Fraction, ...]
    effective: tuple[Fraction, ...]


@dataclass(frozen=True)
class Cooldowns:
    haste: Fraction | None
    factor: Fraction | None
    label: Label
    spells: tuple[SpellCooldown, ...]
    blocked: str | None = None
    rules: str = HASTE_RULES
    basic_haste: Fraction = Fraction(0)
    ultimate_haste: Fraction = Fraction(0)


def _haste_factor(haste: Fraction) -> Fraction:
    return Fraction(100) / (100 + haste)


def ability_cooldowns(sheet: StatSheet) -> Cooldowns:
    """Cooldown of every rank of Q, W, E and R after ability, basic and ultimate haste."""
    haste_value = sheet["ability_haste"]
    basic_value = sheet["basic_ability_haste"]
    ultimate_value = sheet["ultimate_haste"]
    try:
        haste = haste_value.total()
        basic_haste = basic_value.total()
        ultimate_haste = ultimate_value.total()
    except StatBlocked as exc:
        return Cooldowns(None, None, Label.PENDING, (), str(exc))
    factor = _haste_factor(haste)
    basic_factor = _haste_factor(haste + basic_haste)
    ultimate_factor = _haste_factor(haste + ultimate_haste)
    spells = tuple(
        SpellCooldown(
            spell.slot,
            spell.id,
            spell.name,
            spell.cooldowns,
            tuple(
                value * (ultimate_factor if spell.slot == "R" else basic_factor)
                for value in spell.cooldowns
            ),
        )
        for spell in sheet.champion.spells
    )
    active_labels = [
        stat_val.label
        for stat_val, amount in (
            (haste_value, haste),
            (basic_value, basic_haste),
            (ultimate_value, ultimate_haste),
        )
        if amount != 0
    ]
    label = Label.OFFICIAL if not active_labels else weakest((*active_labels, Label.DERIVED))
    return Cooldowns(
        haste,
        factor,
        label,
        spells,
        basic_haste=basic_haste,
        ultimate_haste=ultimate_haste,
    )
