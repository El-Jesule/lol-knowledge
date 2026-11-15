"""Champion kits: per-ability damage cases and passive stats, evaluated on a stat sheet."""

from .evaluate import DamagePart, ability_damage, passive_contributions, sheet_stats
from .model import (
    SCHEMA,
    AbilitySpec,
    CaseSpec,
    DamagePartSpec,
    Kit,
    PassiveStatSpec,
    kit_path,
    load_kit,
    parse_kit,
)

__all__ = [
    "SCHEMA",
    "AbilitySpec",
    "CaseSpec",
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
