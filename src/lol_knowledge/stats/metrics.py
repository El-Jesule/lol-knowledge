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


def ability_cooldowns(sheet: StatSheet) -> Cooldowns:
    """Cooldown of every rank of Q, W, E and R after ability haste."""
    haste_value = sheet["ability_haste"]
    try:
        haste = haste_value.total()
    except StatBlocked as exc:
        return Cooldowns(None, None, Label.PENDING, (), str(exc))
    factor = Fraction(100) / (100 + haste)
    spells = tuple(
        SpellCooldown(
            spell.slot,
            spell.id,
            spell.name,
            spell.cooldowns,
            tuple(value * factor for value in spell.cooldowns),
        )
        for spell in sheet.champion.spells
    )
    label = Label.OFFICIAL if haste == 0 else weakest((haste_value.label, Label.DERIVED))
    return Cooldowns(haste, factor, label, spells)
