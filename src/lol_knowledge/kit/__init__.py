"""Champion kits: per-ability damage cases and passive stats, evaluated on a stat sheet."""

from .evaluate import DamagePart, ability_damage, passive_contributions, sheet_stats
from .model import (
    COST_RESOURCES,
    SCHEMA,
    AbilitySpec,
    CaseSpec,
    CostSpec,
    DamagePartSpec,
    Kit,
    PassiveStatSpec,
    kit_path,
    load_kit,
    parse_kit,
)

__all__ = [
    "COST_RESOURCES",
    "SCHEMA",
    "AbilitySpec",
    "CaseSpec",
    "CostSpec",
    "DamagePart",
    "DamagePartSpec",
    "Kit",
    "PassiveStatSpec",
    "ability_damage",
    "kit_path",
    "load_kit",
    "parse_kit",
    "passive_contributions",
    "sheet_stats",
]
