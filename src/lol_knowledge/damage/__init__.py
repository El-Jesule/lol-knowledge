"""Data-independent deterministic damage engine."""

from .mitigation import (
    NO_MODIFIERS,
    DamageResult,
    DamageType,
    Modifiers,
    ResistanceTrace,
    damage_multiplier,
    effective_resistance,
    mitigate,
    to_fraction,
)
from .report import format_number, format_text, to_dict

__all__ = [
    "NO_MODIFIERS",
    "DamageResult",
    "DamageType",
    "Modifiers",
    "ResistanceTrace",
    "damage_multiplier",
    "effective_resistance",
    "format_number",
    "format_text",
    "mitigate",
    "to_dict",
    "to_fraction",
]
