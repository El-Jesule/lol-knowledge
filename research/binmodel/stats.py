"""Champion stat extraction, growth and stat-reference resolution."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# mStat values observed in shipped champion bins. The names are corroborated by
# data-value names in several champions; see research/reports/agent-b-bin-structures.md.
STAT_NAMES: dict[int, tuple[str, str, str]] = {
    1: ("armor", "corroborated", "Malphite W / Rammus W / Poppy W armor ratios"),
    2: ("attack_damage", "corroborated", "Kha'Zix Q BonusADRatio, Garen Q tADRatio"),
    4: ("attack_speed", "inferred", "Jhin passive attack-speed conversion"),
    6: ("magic_resist", "corroborated", "Rammus W / Poppy W magic-resist ratios"),
    8: ("critical_strike_chance", "inferred", "Caitlyn passive / Jhin passive"),
    9: ("critical_strike_damage", "corroborated", "Nasus Q, Yasuo passive, Caitlyn, Senna"),
    12: ("health", "corroborated", "Sett W StoredHealth, Sion W, Poppy passive"),
}

STAT_FORMULAS: dict[int, tuple[str, str, str]] = {
    0: ("total", "corroborated", "Garen Q tADRatio and Darius Q use the default 0"),
    1: ("base", "inferred", "natural enum neighbour; no decisive champion sample yet"),
    2: ("bonus", "corroborated", "Kha'Zix Q BonusADRatio uses 2"),
}


def stat_ref(m_stat: Any, m_stat_formula: Any) -> dict[str, Any]:
    """Describe a ``mStat`` / ``mStatFormula`` pair without guessing."""
    try:
        stat_number = int(m_stat)
    except TypeError, ValueError:
        stat_number = None
    try:
        formula_number = int(m_stat_formula) if m_stat_formula is not None else 0
    except TypeError, ValueError:
        formula_number = None

    stat_entry = STAT_NAMES.get(stat_number) if stat_number is not None else None
    formula_entry = STAT_FORMULAS.get(formula_number) if formula_number is not None else None
    resolved = bool(stat_entry and formula_entry)
    if not resolved:
        confidence = "unverified"
    elif stat_entry[1] == "corroborated" and formula_entry[1] == "corroborated":
        confidence = "corroborated"
    else:
        confidence = "inferred"
    return {
        "mStat": stat_number,
        "mStatFormula": formula_number,
        "stat": stat_entry[0] if stat_entry else None,
        "formula": formula_entry[0] if formula_entry else None,
        "resolved": resolved,
        "confidence": confidence,
        "stat_confidence": stat_entry[1] if stat_entry else "unverified",
        "formula_confidence": formula_entry[1] if formula_entry else "unverified",
        "evidence": {
            "stat": stat_entry[2] if stat_entry else None,
            "formula": formula_entry[2] if formula_entry else None,
        },
    }


def champion_growth(base: float, per_level: float, level: int) -> float:
    """Return the standard champion stat at ``level``.

    The bin stores only ``base`` and ``per_level``. The growth curve is an
    external model: for levels 1..18 it is the well-known quadratic
    ``base + per_level*(n-1)*(0.7025 + 0.0175*(n-1))``. Past level 18 the
    standard rule is one full growth step per level. This function is marked
    ``inferred`` in the output; it is validated against the user's measurements.
    """
    if level < 1:
        raise ValueError("level must be >= 1")
    if level <= 18:
        steps = level - 1
        return base + per_level * steps * (0.7025 + 0.0175 * steps)
    return base + per_level * 17 + per_level * (level - 18)


def _base_value(root: Mapping[str, Any], field: str) -> float | None:
    entry = root.get(field)
    if not isinstance(entry, Mapping):
        return None
    value = entry.get("baseValue")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def extract_base_stats(root: Mapping[str, Any]) -> dict[str, Any]:
    """Extract the base stat block from ``CharacterRecords/Root``."""
    fields = {
        "attack_damage": "baseDamageModifiable",
        "attack_damage_per_level": "damagePerLevelModifiable",
        "health": "baseHPModifiable",
        "health_per_level": "hpPerLevelModifiable",
        "armor": "baseArmorModifiable",
        "armor_per_level": "armorPerLevelModifiable",
        "magic_resist": "baseMR",
        "magic_resist_per_level": "mrPerLevel",
        "move_speed": "baseMoveSpeedModifiable",
        "attack_range": "attackRangeModifiable",
        "attack_speed": "attackSpeedModifiable",
        "attack_speed_ratio": "attackSpeedRatioModifiable",
        "attack_speed_per_level": "attackSpeedPerLevelModifiable",
    }
    return {
        "values": {name: _base_value(root, field) for name, field in fields.items()},
        "source_fields": fields,
        "growth_model": {
            "formula": (
                "base + per_level*(level-1)*(0.7025 + 0.0175*(level-1)) for level<=18; "
                "base + per_level*17 + per_level*(level-18) after 18"
            ),
            "status": "inferred",
            "note": "The bin stores base and per-level only; the curve is an external model.",
        },
    }


def champion_stats(
    base: Mapping[str, Any],
    level: int,
    *,
    bonus_attack_damage: float = 0.0,
    bonus_health: float = 0.0,
    bonus_armor: float = 0.0,
    bonus_magic_resist: float = 0.0,
) -> dict[str, float]:
    """Compute the stat sheet used by the evaluator at ``level``."""
    values = base["values"]

    def required(name: str) -> float:
        value = values.get(name)
        if value is None:
            raise KeyError(f"missing base stat {name}")
        return float(value)

    base_ad = champion_growth(required("attack_damage"), required("attack_damage_per_level"), level)
    base_hp = champion_growth(required("health"), required("health_per_level"), level)
    base_armor = champion_growth(required("armor"), required("armor_per_level"), level)
    base_mr = champion_growth(required("magic_resist"), required("magic_resist_per_level"), level)
    base_as = required("attack_speed")
    as_per_level = required("attack_speed_per_level")
    attack_speed = base_as * (1.0 + (as_per_level / 100.0) * (level - 1))
    return {
        "level": float(level),
        "attack_damage": base_ad + bonus_attack_damage,
        "base_attack_damage": base_ad,
        "bonus_attack_damage": bonus_attack_damage,
        "health": base_hp + bonus_health,
        "base_health": base_hp,
        "bonus_health": bonus_health,
        "armor": base_armor + bonus_armor,
        "base_armor": base_armor,
        "bonus_armor": bonus_armor,
        "magic_resist": base_mr + bonus_magic_resist,
        "base_magic_resist": base_mr,
        "bonus_magic_resist": bonus_magic_resist,
        "move_speed": required("move_speed"),
        "attack_range": required("attack_range"),
        "attack_speed": attack_speed,
        "base_attack_speed": base_as,
    }


def stat_value(stats: Mapping[str, float], stat: str, formula: str) -> float:
    """Return the requested stat for ``total``, ``base`` or ``bonus``."""
    if stat in {"attack_damage", "health", "armor", "magic_resist"} and formula in {
        "total",
        "base",
        "bonus",
    }:
        key = stat if formula == "total" else f"{formula}_{stat}"
        if key in stats:
            return float(stats[key])
        raise KeyError(f"stat {stat!r} has no {formula!r} value")
    if stat in {"attack_speed", "critical_strike_chance", "critical_strike_damage"}:
        if formula == "total" and stat in stats:
            return float(stats[stat])
        if stat == "attack_speed" and formula in {"base", "bonus"}:
            base = float(stats["base_attack_speed"])
            total = float(stats["attack_speed"])
            return base if formula == "base" else total - base
    raise KeyError(f"unsupported stat {stat!r}/{formula!r}")
