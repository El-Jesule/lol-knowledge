"""Constants and enums for the versioned object model (``lol-object-model/1``)."""

from __future__ import annotations

from pathlib import Path

OBJECT_SCHEMA_VERSION = 1
MODEL_KIND = "lol-object-model"
CATALOG_KIND = "lol-object-model-catalog"
CATALOG_RELATIVE_PATH = Path("lol-knowledge") / "objects" / "catalog.json"
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
    "FlatHPRegenMod": ("health_regen", "flat", 1.0),
    "FlatCritChanceMod": ("crit_chance", "percent", 100.0),
    "PercentAttackSpeedMod": ("attack_speed", "percent", 100.0),
    "PercentLifeStealMod": ("life_steal", "percent", 100.0),
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
    "health_regen": frozenset({"flat"}),
    "mana_regen": frozenset({"percent"}),
    "crit_chance": frozenset({"percent"}),
    "crit_damage_bonus": frozenset({"percent"}),
    "attack_speed": frozenset({"percent"}),
    "life_steal": frozenset({"percent"}),
    "lethality": frozenset({"flat"}),
    "armor_penetration_percent": frozenset({"percent"}),
    "magic_penetration_percent": frozenset({"percent"}),
    "magic_penetration_flat": frozenset({"flat"}),
    "ability_haste": frozenset({"flat"}),
}

STAT_ORDER = tuple(CANONICAL_STAT_KINDS)

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

VERIFICATION_STATES = frozenset(
    {
        "official_field",
        "description_quote_verified",
        "secondary_source_verified",
        "unverified",
    }
)
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
    {"ddragon_description", "community_wiki", "community_dragon", "in_game_measurement"}
)
EVIDENCE_CONFIDENCE = frozenset({"official", "corroborated", "secondary", "unverified"})
HOLDER_RANGES = frozenset({"melee", "ranged"})
STAT_SUBJECTS = frozenset({"champion", "target"})
EFFECT_KINDS = frozenset({"passive", "active"})
TRIGGER_EVENTS = frozenset(
    {
        "always",
        "on_hit",
        "taking_attack",
        "damaging_ability",
        "on_heal_or_shield",
        "cast",
        "on_kill",
        "periodic",
        "unknown",
    }
)
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
    }
)
DAMAGE_TYPES = frozenset({"physical", "magic", "true"})
HEALING_MODES = frozenset({"absolute", "percent_of_trigger"})
STAT_SCOPES = frozenset({"base", "bonus", "total", "current", "max"})
FORMULA_OPS = frozenset(
    {
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
LIMIT_KINDS = frozenset({"maximum", "minimum", "threshold", "cap"})
CONDITION_KINDS = frozenset(
    {
        "target_is_champion",
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
MAX_FORMULA_DEPTH = 32

# The damage-engine interface reports exactly these outcomes.
OUTCOME_STATES = ("evaluable", "partially_evaluable", "excluded", "unreliable")
