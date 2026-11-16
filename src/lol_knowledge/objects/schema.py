"""Constants and enums for the versioned object model (``lol-object-model/1``)."""

from __future__ import annotations

from pathlib import Path

from ..formula.schema import (  # noqa: F401 - re-exported for the object model
    MAX_FORMULA_DEPTH,
    STAT_SCOPES,
    STAT_SCOPES_BY_STAT,
    STAT_SUBJECTS,
)
from ..formula.schema import OBJECT_OPS as FORMULA_OPS  # noqa: F401

OBJECT_SCHEMA_VERSION = 1
MODEL_KIND = "lol-object-model"
CATALOG_KIND = "lol-object-model-catalog"
CATALOG_RELATIVE_PATH = Path("lol-knowledge") / "objects" / "catalog.json"
GENERATED_STATS_RELATIVE_PATH = Path("lol-knowledge") / "objects" / "catalog-stats.json"
OBJECTS_DIRNAME = "objects"
SNAPSHOT_RELATIVE_PATH = Path("data") / "current"
ITEMS_FILENAME = "items.json"
MANIFEST_FILENAME = "manifest.json"

# Data Dragon stores percentages as fractions. The canonical model uses
# percentage points (0.25 -> 25.0) and keeps the raw value for traceability.
DDRAGON_STAT_MAP: dict[str, tuple[str, str, float]] = {
    "FlatPhysicalDamageMod": ("attack_damage", "flat", 1.0),
    "FlatMagicDamageMod": ("ability_power", "flat", 1.0),
    "FlatHPPoolMod": ("health", "flat", 1.0),
    "FlatMPPoolMod": ("mana", "flat", 1.0),
    "FlatArmorMod": ("armor", "flat", 1.0),
    "FlatSpellBlockMod": ("magic_resist", "flat", 1.0),
    "FlatMovementSpeedMod": ("move_speed", "flat", 1.0),
    "PercentMovementSpeedMod": ("move_speed", "percent", 100.0),
    # Per second in Data Dragon; the model uses per 5 s (see DDRAGON_UNIT_CONVERSIONS).
    "FlatHPRegenMod": ("health_regen", "flat", 5.0),
    "FlatCritChanceMod": ("crit_chance", "percent", 100.0),
    "PercentAttackSpeedMod": ("attack_speed", "percent", 100.0),
    "PercentLifeStealMod": ("life_steal", "percent", 100.0),
}

# Factors that change the unit, not only the notation. The converted value is
# derived, so the model records why (lol-knowledge/mechanics/regeneration.md).
DDRAGON_UNIT_CONVERSIONS: dict[str, str] = {
    "FlatHPRegenMod": (
        "Data Dragon gives it per second; item descriptions show 5x per 5 s "
        "(lol-knowledge/mechanics/regeneration.md)"
    ),
}

# Stats that Data Dragon does not encode in ``stats`` and the catalog may
# declare from the item description. ``kind`` is ``flat`` or ``percent``;
# percentage values are percentage points.
CANONICAL_STAT_KINDS: dict[str, frozenset[str]] = {
    "attack_damage": frozenset({"flat"}),
    "ability_power": frozenset({"flat"}),
    "health": frozenset({"flat"}),
    "mana": frozenset({"flat"}),
    "armor": frozenset({"flat"}),
    "magic_resist": frozenset({"flat"}),
    "move_speed": frozenset({"flat", "percent"}),
    # Regeneration: flat per 5 s, or a percentage of the base regeneration.
    "health_regen": frozenset({"flat", "percent"}),
    "mana_regen": frozenset({"flat", "percent"}),
    "crit_chance": frozenset({"percent"}),
    "crit_damage_bonus": frozenset({"percent"}),
    "attack_speed": frozenset({"percent"}),
    "life_steal": frozenset({"percent"}),
    # Data Dragon only shows omnivamp in descriptions ("omnisucción").
    "omnivamp": frozenset({"percent"}),
    # Like omnivamp, tenacity only appears in descriptions.
    "tenacity": frozenset({"percent"}),
    "lethality": frozenset({"flat"}),
    "armor_penetration_percent": frozenset({"percent"}),
    "magic_penetration_percent": frozenset({"percent"}),
    "magic_penetration_flat": frozenset({"flat"}),
    "ability_haste": frozenset({"flat"}),
}

STAT_ORDER = tuple(CANONICAL_STAT_KINDS)


VERIFICATION_STATES = frozenset(
    {
        "official_field",
        "description_quote_verified",
        "secondary_source_verified",
        "unverified",
    }
)
# complete: every effect of the description is modelled; partial: some are;
# pending: none reviewed yet (items that only have generated stats).
EFFECT_REVIEWS = frozenset({"complete", "partial", "pending"})
MODEL_STATUSES = frozenset({"evaluable", "partially_evaluable", "excluded"})
MODEL_STATUS_RANK = {"excluded": 0, "partially_evaluable": 1, "evaluable": 2}
BASIS_STATES = frozenset(
    {
        "description_explicit",
        "description_partial",
        "description_silent",
        "external_evidence_explicit",
    }
)
# Evidence that is not the Data Dragon description. ``secondary`` is a
# community source; it is never presented as an official Riot value.
EVIDENCE_KINDS = frozenset(
    {
        "ddragon_description",
        "community_wiki",
        "community_dragon",
        "in_game_measurement",
        "client_data",
        "patch_notes",
    }
)
# ``derived``: read from the client's data (``client_data``) and nowhere else.
EVIDENCE_CONFIDENCE = frozenset({"official", "corroborated", "derived", "secondary", "unverified"})
HOLDER_RANGES = frozenset({"melee", "ranged"})
EFFECT_KINDS = frozenset({"passive", "active"})
TRIGGER_EVENTS = frozenset(
    {
        "always",
        "on_attack",
        "on_hit",
        "spellblade",
        "energized",
        "taking_attack",
        "damaging_ability",
        "on_heal_or_shield",
        "cast",
        "on_kill",
        "periodic",
        "unknown",
    }
)
# Declared assumptions under which an engine may apply an effect permanently.
# ``max_stacks``: the components give the value with every stack gained, and
# the stat sheet applies them as stats (lol-knowledge/objects/README.md).
SCENARIOS = frozenset({"max_stacks"})
TARGET_KINDS = frozenset(
    {"self", "enemy_champion", "enemy_unit", "attacker", "ally_champion", "area", "unknown"}
)
COMPONENT_KINDS = frozenset(
    {
        "damage",
        "healing",
        "shield",
        "stat_modifier",
        "damage_modifier",
        "crowd_control",
        "status",
        "stasis",
        "repeat_on_hit",
        "trigger_energized",
        "execute",
    }
)
DAMAGE_TYPES = frozenset({"physical", "magic", "true"})
HEALING_MODES = frozenset({"absolute", "percent_of_trigger"})
LIMIT_KINDS = frozenset({"maximum", "minimum", "threshold", "cap"})
CONDITION_KINDS = frozenset(
    {
        "target_is_champion",
        "target_is_structure",
        "target_is_monster",
        "target_is_minion",
        "target_health_below",
        "target_health_above",
        "damage_source_is_attack",
        "damage_source_is_ability",
        "distance",
        "critical_strike",
        "on_hit",
        "ability_hit",
        "stacks_at_least",
    }
)

# The damage-engine interface reports exactly these outcomes.
OUTCOME_STATES = ("evaluable", "partially_evaluable", "excluded", "unreliable")
