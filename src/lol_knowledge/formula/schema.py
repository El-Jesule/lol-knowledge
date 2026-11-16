"""Vocabulary shared by every formula: stats, scopes, subjects and operations."""

from __future__ import annotations

STAT_SUBJECTS = frozenset({"champion", "target"})
STAT_SCOPES = frozenset({"base", "bonus", "total", "current", "max"})
MAX_FORMULA_DEPTH = 32

# Which scopes make sense for each stat. The engine resolves ``total`` to the
# bare key, ``base``/``bonus`` to ``<scope>_<stat>`` and ``current``/``max`` to
# ``<scope>_<stat>`` (for example ``current_health``).
STAT_SCOPES_BY_STAT: dict[str, frozenset[str]] = {
    "attack_damage": frozenset({"base", "bonus", "total"}),
    "ability_power": frozenset({"total"}),
    "health": frozenset({"base", "bonus", "total", "current", "max"}),
    "mana": frozenset({"base", "bonus", "total"}),
    "armor": frozenset({"base", "bonus", "total"}),
    "magic_resist": frozenset({"base", "bonus", "total"}),
    "move_speed": frozenset({"total"}),
    "health_regen": frozenset({"total"}),
    "mana_regen": frozenset({"total"}),
    "crit_chance": frozenset({"total"}),
    "crit_damage_bonus": frozenset({"total"}),
    "attack_speed": frozenset({"total"}),
    "life_steal": frozenset({"total"}),
    "lethality": frozenset({"total"}),
    "armor_penetration_percent": frozenset({"total"}),
    "magic_penetration_percent": frozenset({"total"}),
    "magic_penetration_flat": frozenset({"total"}),
    "ability_haste": frozenset({"total"}),
}
# Operations allowed in the item catalog. ``by_level`` (one value per champion
# level) was added in catalog version 12 for client level breakpoints.
OBJECT_OPS = frozenset(
    {
        "by_level",
        "constant",
        "stat",
        "percent_of",
        "add",
        "mul",
        "min",
        "by_holder_range",
        "unknown",
        "unsupported",
    }
)
# Champion kits also need per-rank and per-level values and scenario inputs.
ABILITY_OPS = OBJECT_OPS | {"by_rank", "input"}
ALL_OPS = ABILITY_OPS
