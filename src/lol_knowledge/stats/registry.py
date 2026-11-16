"""Shared registry of champion and item statistics.

Every statistic declares how independent sources combine and whether the
project has a documented rule to resolve it. A statistic without a rule is
still listed, with its contributions, but its total is not computed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction

from ..errors import StatsError

MECHANICS = "lol-knowledge/mechanics"
GROWTH_RULES = f"{MECHANICS}/stat-growth.md"
HASTE_RULES = f"{MECHANICS}/ability-haste.md"
MITIGATION_RULES = f"{MECHANICS}/damage-mitigation.md"
CRIT_RULES = f"{MECHANICS}/critical-strike.md"
ATTACK_SPEED_RULES = f"{MECHANICS}/attack-speed.md"
VAMP_RULES = f"{MECHANICS}/life-steal-and-omnivamp.md"
# Attacks per second; "Baseline Attack Speed Cap: 2.5 => 3.0" in the 25.S1.3 patch notes.
ATTACK_SPEED_CAP = Fraction(3)
CRIT_CHANCE_CAP = Fraction(1)  # 100 %; the excess stays visible in the scopes


class Stacking(StrEnum):
    ADDITIVE = "additive"
    MULTIPLICATIVE = "multiplicative"


class Unit(StrEnum):
    AMOUNT = "amount"  # flat values; items declare them with kind "flat"
    FRACTION = "fraction"  # 0..1; items declare them with kind "percent" (percentage points)


@dataclass(frozen=True)
class StatDef:
    id: str
    name: str
    stacking: Stacking
    unit: Unit
    rules: str | None = None
    pending: str | None = None
    cap: Fraction | None = None  # the total never exceeds it; scopes are uncapped
    # Item and extra contributions declared with this id are added to that stat instead.
    routes_to: str | None = None

    @property
    def resolvable(self) -> bool:
        return self.pending is None

    @property
    def item_kind(self) -> str:
        if self.routes_to is not None:
            return STATS[self.routes_to].item_kind
        return "percent" if self.unit is Unit.FRACTION else "flat"


def _amount(stat_id: str, name: str, rules: str | None = None) -> StatDef:
    return StatDef(stat_id, name, Stacking.ADDITIVE, Unit.AMOUNT, rules)


def _pending(stat_id: str, name: str, reason: str, unit: Unit = Unit.AMOUNT) -> StatDef:
    return StatDef(stat_id, name, Stacking.ADDITIVE, unit, None, reason)


NO_RULE = "sin regla documentada en lol-knowledge/mechanics/"

STATS: dict[str, StatDef] = {
    stat.id: stat
    for stat in (
        _amount("health", "Vida", GROWTH_RULES),
        _amount("mana", "Maná", GROWTH_RULES),
        _amount("armor", "Armadura", GROWTH_RULES),
        _amount("magic_resist", "Resistencia mágica", GROWTH_RULES),
        _amount("attack_damage", "Daño de ataque", GROWTH_RULES),
        _amount("ability_power", "Poder de habilidad"),
        _amount("ability_haste", "Aceleración de habilidades", HASTE_RULES),
        _amount("lethality", "Letalidad", MITIGATION_RULES),
        _amount("magic_penetration_flat", "Penetración mágica plana", MITIGATION_RULES),
        StatDef(
            "armor_penetration_percent",
            "Penetración de armadura %",
            Stacking.MULTIPLICATIVE,
            Unit.FRACTION,
            MITIGATION_RULES,
        ),
        StatDef(
            "magic_penetration_percent",
            "Penetración mágica %",
            Stacking.MULTIPLICATIVE,
            Unit.FRACTION,
            MITIGATION_RULES,
        ),
        # Total attacks per second: base + ratio x attack_speed_bonus, capped. Items
        # declare "attack_speed" as a percentage, which is bonus attack speed.
        StatDef(
            "attack_speed",
            "Velocidad de ataque",
            Stacking.ADDITIVE,
            Unit.AMOUNT,
            ATTACK_SPEED_RULES,
            cap=ATTACK_SPEED_CAP,
            routes_to="attack_speed_bonus",
        ),
        StatDef(
            "attack_speed_bonus",
            "Velocidad de ataque adicional",
            Stacking.ADDITIVE,
            Unit.FRACTION,
            ATTACK_SPEED_RULES,
        ),
        _pending("move_speed", "Velocidad de movimiento", "límites suaves " + NO_RULE),
        _pending("health_regen", "Regeneración de vida", "unidad por 5 s y aportes % " + NO_RULE),
        _pending("mana_regen", "Regeneración de maná", "unidad por 5 s y aportes % " + NO_RULE),
        StatDef(
            "crit_chance",
            "Probabilidad de crítico",
            Stacking.ADDITIVE,
            Unit.FRACTION,
            CRIT_RULES,
            cap=CRIT_CHANCE_CAP,
        ),
        StatDef(
            "crit_damage_bonus",
            "Daño crítico adicional",
            Stacking.ADDITIVE,
            Unit.FRACTION,
            CRIT_RULES,
        ),
        StatDef("life_steal", "Robo de vida", Stacking.ADDITIVE, Unit.FRACTION, VAMP_RULES),
        StatDef("omnivamp", "Omnivampirismo", Stacking.ADDITIVE, Unit.FRACTION, VAMP_RULES),
        _pending("tenacity", "Tenacidad", "apilamiento " + NO_RULE, Unit.FRACTION),
    )
}


def stat(stat_id: str) -> StatDef:
    try:
        return STATS[stat_id]
    except KeyError as exc:
        raise StatsError(f"unknown stat {stat_id!r}") from exc
