"""Shared registry of champion and item statistics.

Every statistic declares how independent sources combine and whether the
project has a documented rule to resolve it. A statistic without a rule is
still listed, with its contributions, but its total is not computed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ..errors import StatsError

MECHANICS = "lol-knowledge/mechanics"
GROWTH_RULES = f"{MECHANICS}/stat-growth.md"
HASTE_RULES = f"{MECHANICS}/ability-haste.md"
MITIGATION_RULES = f"{MECHANICS}/damage-mitigation.md"
CRIT_RULES = f"{MECHANICS}/critical-strike.md"


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

    @property
    def resolvable(self) -> bool:
        return self.pending is None

    @property
    def item_kind(self) -> str:
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
        _pending(
            "attack_speed",
            "Velocidad de ataque",
            "usa otra fórmula de crecimiento y un ratio que Data Dragon no publica",
        ),
        _pending("move_speed", "Velocidad de movimiento", "límites suaves " + NO_RULE),
        _pending("health_regen", "Regeneración de vida", "unidad por 5 s y aportes % " + NO_RULE),
        _pending("mana_regen", "Regeneración de maná", "unidad por 5 s y aportes % " + NO_RULE),
        _pending("crit_chance", "Probabilidad de crítico", "tope " + NO_RULE, Unit.FRACTION),
        StatDef(
            "crit_damage_bonus",
            "Daño crítico adicional",
            Stacking.ADDITIVE,
            Unit.FRACTION,
            CRIT_RULES,
        ),
        _pending("life_steal", "Robo de vida", "curación " + NO_RULE, Unit.FRACTION),
        _pending("omnivamp", "Omnivampirismo", "curación " + NO_RULE, Unit.FRACTION),
        _pending("tenacity", "Tenacidad", "apilamiento " + NO_RULE, Unit.FRACTION),
    )
}


def stat(stat_id: str) -> StatDef:
    try:
        return STATS[stat_id]
    except KeyError as exc:
        raise StatsError(f"unknown stat {stat_id!r}") from exc
