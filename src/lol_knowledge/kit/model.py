"""Champion kit documents (``lol-champion-kit/1``): parsing and validation.

A kit describes, per ability, the damage *cases* (alternatives such as a
centre hit or an edge hit) and their damage *parts*, each a formula with a
damage type, a label and a source. It also lists stats an ability grants
passively. Kits are curated data in ``lol-knowledge/champions/<Id>/kit.json``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from ..damage import DamageType
from ..errors import KitError
from ..formula import ABILITY_OPS, formula_issues
from ..stats.labels import Label
from ..stats.registry import STATS

SCHEMA = "lol-champion-kit/1"
KIT_FILENAME = "kit.json"
SLOTS = ("P", "Q", "W", "E", "R")
CASE_ID = re.compile(r"[a-z][a-z0-9_]*")
COST_RESOURCES = frozenset({"mana", "energy", "health", "none"})
PASSIVE_EFFECT_KINDS = frozenset(
    {
        "stat_bonus",
        "stacking_stat",
        "heal",
        "damage_proc",
        "shield",
        "damage_taken_modifier",
        "resource_restore",
    }
)
PASSIVE_STAT_MODES = frozenset({"flat", "percent", "percent_ms"})
PASSIVE_STACK_TRIGGERS = frozenset({"champion_hit", "attack", "ability_hit", "any_hit"})
PASSIVE_HEAL_TRIGGERS = frozenset(
    {
        "on_champion_takedown",
        "on_minion_monster_kill",
        "on_any_kill",
        "on_hit",
        "on_ability_hit",
        "on_ability_cast",
        "on_champion_hit",
        "every_n_attacks",
        "every_n_hits",
    }
)
PASSIVE_PROC_TRIGGERS = frozenset(
    {
        "on_attack",
        "on_hit",
        "on_any_hit",
        "every_n_attacks",
        "every_n_hits",
        "every_n_ability_hits",
        "after_ability",
        "on_ability_hit",
        "below_hp_percent",
        "at_max_stacks",
    }
)
PASSIVE_SHIELD_TRIGGERS = frozenset(
    {
        "on_taking_damage",
        "on_ability_cast",
        "on_champion_attack",
        "every_n_hits",
        "below_hp_percent",
    }
)
PASSIVE_RESOURCE_TRIGGERS = frozenset(
    {"on_any_kill", "on_hit", "on_ability_hit", "on_champion_hit", "every_n_ability_hits"}
)
PASSIVE_SHIELD_TYPES = frozenset({"normal", "physical", "magic"})
PASSIVE_DR_MODES = frozenset({"flat", "percent"})
PASSIVE_RESOURCES = frozenset({"mana", "energy"})
PASSIVE_TARGET_KINDS = frozenset({"champion", "non_structure"})
ACTIVE_EFFECT_KINDS = frozenset(
    {
        "shield",
        "heal",
        "damage_taken_modifier",
        "stat_bonus",
        "damage_dealt_heal",
        "recent_damage_heal",
        "recent_damage_shield",
        "dodge_attacks",
        "spell_shield",
        "block_first_hit",
        "invulnerable",
        "cleanse",
        "cc_immune",
    }
)
ACTIVE_INVULN_MODES = frozenset({"invulnerable", "undying"})
_FORMULA_OPTIONAL_ACTIVE_KINDS = frozenset(
    {"dodge_attacks", "spell_shield", "block_first_hit", "invulnerable", "cleanse", "cc_immune"}
)
CC_KINDS = frozenset(
    {
        "stun",
        "airborne",
        "suppression",
        "silence",
        "charm",
        "fear",
        "taunt",
        "blind",
        "polymorph",
        "sleep",
        "berserk",
        "root",
    }
)
CC_TENACITY_IMMUNE = frozenset({"airborne", "suppression"})
CC_CLEANSE_IMMUNE = frozenset({"airborne", "suppression"})
CC_QSS_IMMUNE = frozenset({"airborne"})
CC_BLOCKS_ATTACKS = frozenset(
    {"stun", "airborne", "suppression", "charm", "fear", "polymorph", "sleep"}
)
CC_BLOCKS_ABILITIES = frozenset(
    {
        "stun",
        "airborne",
        "suppression",
        "charm",
        "fear",
        "taunt",
        "polymorph",
        "sleep",
        "silence",
        "berserk",
    }
)
CC_BLINDS_ATTACKS = frozenset({"blind"})


@dataclass(frozen=True)
class CCEffectSpec:
    """Declarative crowd-control effect applied by casting Q/W/E/R."""

    id: str
    name: str
    kind: str
    duration_formula: Mapping[str, Any]
    label: Label
    source: str
    case_ids: tuple[str, ...] = ()
    tenacity_applies: bool = True
    cleansable_by_cleanse: bool = True
    cleansable_by_qss: bool = True
    condition: str = ""

    def applies_to_case(self, case_id: str | None) -> bool:
        if not self.case_ids:
            return True
        return case_id in self.case_ids


@dataclass(frozen=True)
class ActiveEffectSpec:
    """Declarative non-damage active effect triggered when casting Q/W/E/R."""

    id: str
    name: str
    kind: str
    formula: Mapping[str, Any]
    label: Label
    source: str
    case_ids: tuple[str, ...] = ()
    duration_seconds: Fraction | None = None
    duration_formula: Mapping[str, Any] | None = None
    stat: str | None = None
    mode: str = "flat"
    shield_type: str = "normal"
    damage_type: DamageType | None = None
    damage_reduction_cap: Fraction | None = None
    over_duration: bool = False
    uses_hsp: bool = True
    window_seconds: Fraction | None = None
    min_formula: Mapping[str, Any] | None = None
    max_formula: Mapping[str, Any] | None = None
    part_index: int | None = None
    input_name: str | None = None
    condition: str = ""

    def applies_to_case(self, case_id: str | None) -> bool:
        if not self.case_ids:
            return True
        return case_id in self.case_ids


@dataclass(frozen=True)
class PassiveEffectSpec:
    """Declarative champion passive effect applied on the stat sheet and/or in rotations."""

    id: str
    name: str
    kind: str
    formula: Mapping[str, Any]
    label: Label
    source: str
    # Stat target and mode for "stat_bonus" and "stacking_stat" (or "flat"/"percent" for DR).
    stat: str | None = None
    mode: str = "flat"
    # Trigger and stacking controls for combat passives.
    trigger: str | None = None
    max_stacks: int | None = None
    charges_per_cast: int = 1
    consume_all_stacks: bool = False
    max_stacks_multiplier: Fraction = Fraction(1)
    only_at_max: bool = False
    duration_seconds: Fraction | None = None
    cooldown_seconds: Fraction | None = None
    cooldown_formula: Mapping[str, Any] | None = None
    every: int | None = None
    stacks_required: int | None = None
    stack_source_id: str | None = None
    # Damage type for "damage_proc" or optional filter for "damage_taken_modifier".
    damage_type: DamageType | None = None
    # Shield / threshold / DR cap / resource controls.
    shield_type: str = "normal"
    threshold_hp_percent: Fraction | None = None
    damage_reduction_cap: Fraction | None = None
    resource: str | None = None
    target_kind: str | None = None
    # Optional scenario --input name (e.g. determination_stacks, essence_fragments).
    input_name: str | None = None
    condition: str = ""


@dataclass(frozen=True)
class CostSpec:
    """Explicit ability or case resource cost declared by a champion kit."""

    resource: str  # "mana", "energy", "health" or "none"
    formula: Mapping[str, Any]
    label: Label
    source: str


@dataclass(frozen=True)
class DamagePartSpec:
    damage_type: DamageType
    formula: Mapping[str, Any]
    label: Label
    source: str
    damage_type_source: str


@dataclass(frozen=True)
class CaseSpec:
    id: str
    name: str
    parts: tuple[DamagePartSpec, ...]
    # A recast of an ability already cast: it starts no cooldown (timeline.md).
    recast: bool = False
    cost: CostSpec | None = None
    # Area-of-effect classification (True = area spell, False = single-target, None = undeclared).
    aoe: bool | None = None
    # Maximum distinct targets hit in one cast (None = uncapped when aoe is True, else 1).
    max_targets: int | None = None
    # Damage multiplier (0 < ratio <= 1) applied to each secondary target beyond the primary one.
    secondary_damage_ratio: Fraction = Fraction(1)

    def resolve_targets(self, target_count: int) -> tuple[int, Fraction, bool]:
        """Return ``(targets_hit, secondary_damage_ratio, unverified)`` for ``target_count``."""
        if target_count <= 1:
            return 1, self.secondary_damage_ratio, False
        if self.max_targets is not None:
            return min(target_count, self.max_targets), self.secondary_damage_ratio, False
        if self.aoe is True:
            return target_count, self.secondary_damage_ratio, False
        if self.aoe is False:
            return 1, self.secondary_damage_ratio, False
        return 1, self.secondary_damage_ratio, True


@dataclass(frozen=True)
class PassiveStatSpec:
    stat: str
    formula: Mapping[str, Any]
    label: Label
    source: str
    condition: str


@dataclass(frozen=True)
class AbilitySpec:
    slot: str
    name: str
    max_rank: int
    cases: tuple[CaseSpec, ...]
    passive_stats: tuple[PassiveStatSpec, ...]
    not_modelled: tuple[str, ...]
    # Seconds after the first cast within which a recast case is allowed.
    recast_window: Fraction | None = None
    # Recasts allowed per cast (Ahri's R: 2), and the least time between two casts.
    max_recasts: int = 1
    recast_interval: Fraction | None = None
    cost: CostSpec | None = None
    passive_effects: tuple[PassiveEffectSpec, ...] = ()
    active_effects: tuple[ActiveEffectSpec, ...] = ()
    cc_effects: tuple[CCEffectSpec, ...] = ()

    def case(self, case_id: str) -> CaseSpec:
        for case in self.cases:
            if case.id == case_id:
                return case
        known = ", ".join(case.id for case in self.cases) or "none"
        raise KitError(f"{self.slot}: unknown case {case_id!r} (known: {known})")


@dataclass(frozen=True)
class Kit:
    champion: str
    label: Label
    game_version: str
    content_version: str
    abilities: Mapping[str, AbilitySpec]

    def ability(self, slot: str) -> AbilitySpec:
        try:
            return self.abilities[slot.upper()]
        except KeyError as exc:
            raise KitError(f"{self.champion} has no kit entry for {slot!r}") from exc


def _text(record: Mapping[str, Any], key: str, context: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise KitError(f"{context}: {key!r} must be a non-empty string")
    return value


def _label(record: Mapping[str, Any], context: str) -> Label:
    try:
        return Label(record.get("label"))
    except ValueError as exc:
        raise KitError(f"{context}: label must be one of {[item.value for item in Label]}") from exc


def _rank_lists(formula: Any) -> list[int]:
    """Lengths of every ``by_rank`` list in a formula."""
    if isinstance(formula, Mapping):
        found = [len(formula["values"])] if formula.get("op") == "by_rank" else []
        for value in formula.values():
            found.extend(_rank_lists(value))
        return found
    if isinstance(formula, Sequence) and not isinstance(formula, (str, bytes)):
        return [length for item in formula for length in _rank_lists(item)]
    return []


def _formula(record: Mapping[str, Any], max_rank: int, context: str) -> Mapping[str, Any]:
    formula = record.get("formula")
    issues = formula_issues(formula, ops=ABILITY_OPS)
    if issues:
        raise KitError(f"{context}: invalid formula: {'; '.join(issues)}")
    for length in _rank_lists(formula):
        if length != max_rank:
            raise KitError(f"{context}: by_rank has {length} values, the ability has {max_rank}")
    return formula


def _list(record: Mapping[str, Any], key: str, context: str) -> Sequence[Any]:
    value = record.get(key, [])
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise KitError(f"{context}: {key!r} must be a list")
    return value


def _cost(record: Mapping[str, Any], max_rank: int, context: str) -> CostSpec | None:
    raw = record.get("cost")
    if raw is None:
        return None
    cost_context = f"{context}.cost"
    if not isinstance(raw, Mapping):
        raise KitError(f"{cost_context}: must be an object")
    resource = _text(raw, "resource", cost_context)
    if resource not in COST_RESOURCES:
        raise KitError(f"{cost_context}: resource must be one of {sorted(COST_RESOURCES)}")
    return CostSpec(
        resource,
        _formula(raw, max_rank, cost_context),
        _label(raw, cost_context),
        _text(raw, "source", cost_context),
    )


def _optional_positive_fraction(
    record: Mapping[str, Any], key: str, context: str
) -> Fraction | None:
    value = record.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise KitError(f"{context}: {key} must be a positive number")
    return Fraction(str(value))


def _optional_positive_int(
    record: Mapping[str, Any], key: str, context: str, *, minimum: int = 1
) -> int | None:
    value = record.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise KitError(f"{context}: {key} must be an integer >= {minimum}")
    return value


def _passive_effects(
    record: Mapping[str, Any], max_rank: int, context: str
) -> tuple[PassiveEffectSpec, ...]:
    effects: list[PassiveEffectSpec] = []
    seen_ids: set[str] = set()
    for index, entry in enumerate(_list(record, "passive_effects", context)):
        entry_ctx = f"{context}.passive_effects[{index}]"
        if not isinstance(entry, Mapping):
            raise KitError(f"{entry_ctx}: must be an object")
        effect_id = _text(entry, "id", entry_ctx)
        if CASE_ID.fullmatch(effect_id) is None:
            raise KitError(f"{entry_ctx}: id must be lowercase snake_case")
        if effect_id in seen_ids:
            raise KitError(f"{entry_ctx}: duplicate passive effect id {effect_id!r}")
        seen_ids.add(effect_id)
        name = _text(entry, "name", entry_ctx)
        kind = _text(entry, "kind", entry_ctx)
        if kind not in PASSIVE_EFFECT_KINDS:
            raise KitError(f"{entry_ctx}: kind must be one of {sorted(PASSIVE_EFFECT_KINDS)}")
        formula = _formula(entry, max_rank, entry_ctx)
        label = _label(entry, entry_ctx)
        source = _text(entry, "source", entry_ctx)
        raw_input = entry.get("input_name")
        if raw_input is not None and (not isinstance(raw_input, str) or not raw_input.strip()):
            raise KitError(f"{entry_ctx}: input_name must be a non-empty string")
        condition = entry.get("condition", "")
        if not isinstance(condition, str):
            raise KitError(f"{entry_ctx}: condition must be a string")

        stat_id: str | None = None
        mode = "flat"
        trigger: str | None = None
        max_stacks: int | None = None
        charges_per_cast = 1
        consume_all_stacks = False
        max_mult = Fraction(1)
        only_at_max = bool(entry.get("only_at_max", False))
        duration: Fraction | None = None
        cooldown: Fraction | None = None
        cooldown_formula: Mapping[str, Any] | None = None
        every: int | None = None
        stacks_req: int | None = None
        stack_source_id: str | None = None
        damage_type: DamageType | None = None
        shield_type = "normal"
        threshold_hp: Fraction | None = None
        dr_cap: Fraction | None = None
        resource: str | None = None
        target_kind: str | None = None

        raw_cd_formula = entry.get("cooldown_formula")
        if raw_cd_formula is not None:
            cooldown_formula = _formula(
                {"formula": raw_cd_formula}, max_rank, f"{entry_ctx}.cooldown_formula"
            )
        raw_tk = entry.get("target_kind")
        if raw_tk is not None:
            if raw_tk not in PASSIVE_TARGET_KINDS:
                raise KitError(
                    f"{entry_ctx}: target_kind must be one of {sorted(PASSIVE_TARGET_KINDS)}"
                )
            target_kind = str(raw_tk)

        if kind in {"stat_bonus", "stacking_stat"}:
            stat_id = _text(entry, "stat", entry_ctx)
            definition = STATS.get(stat_id)
            if definition is None or not definition.resolvable:
                raise KitError(f"{entry_ctx}: {stat_id!r} is not a resolvable stat")
            mode = str(entry.get("mode", "flat"))
            if mode not in PASSIVE_STAT_MODES:
                raise KitError(f"{entry_ctx}: mode must be one of {sorted(PASSIVE_STAT_MODES)}")
            if kind == "stacking_stat":
                trigger = _text(entry, "trigger", entry_ctx)
                if trigger not in PASSIVE_STACK_TRIGGERS:
                    raise KitError(
                        f"{entry_ctx}: trigger must be one of {sorted(PASSIVE_STACK_TRIGGERS)}"
                    )
                max_stacks = _optional_positive_int(entry, "max_stacks", entry_ctx)
                if max_stacks is None:
                    raise KitError(f"{entry_ctx}: stacking_stat requires max_stacks")
                mult_val = _optional_positive_fraction(entry, "max_stacks_multiplier", entry_ctx)
                if mult_val is not None:
                    if mult_val < 1:
                        raise KitError(f"{entry_ctx}: max_stacks_multiplier must be >= 1")
                    max_mult = mult_val
                duration = _optional_positive_fraction(entry, "duration_seconds", entry_ctx)
            else:
                max_stacks = _optional_positive_int(entry, "max_stacks", entry_ctx)
        elif kind == "heal":
            trigger = _text(entry, "trigger", entry_ctx)
            if trigger not in PASSIVE_HEAL_TRIGGERS:
                raise KitError(
                    f"{entry_ctx}: trigger must be one of {sorted(PASSIVE_HEAL_TRIGGERS)}"
                )
            cooldown = _optional_positive_fraction(entry, "cooldown_seconds", entry_ctx)
            stacks_req = _optional_positive_int(entry, "stacks_required", entry_ctx)
            if trigger in {"every_n_attacks", "every_n_hits", "every_n_ability_hits"}:
                every = _optional_positive_int(entry, "every", entry_ctx, minimum=2)
                if every is None:
                    raise KitError(f"{entry_ctx}: {trigger} requires every >= 2")
            elif trigger == "after_ability":
                max_stacks = _optional_positive_int(entry, "max_stacks", entry_ctx)
                charges_per_cast = _optional_positive_int(entry, "charges_per_cast", entry_ctx) or 1
                raw_consume_all = entry.get("consume_all_stacks", False)
                if not isinstance(raw_consume_all, bool):
                    raise KitError(f"{entry_ctx}: consume_all_stacks must be a boolean")
                consume_all_stacks = raw_consume_all
                if max_stacks is not None and charges_per_cast > max_stacks:
                    raise KitError(
                        f"{entry_ctx}: charges_per_cast ({charges_per_cast}) exceeds "
                        f"max_stacks ({max_stacks})"
                    )
        elif kind == "damage_proc":
            trigger = _text(entry, "trigger", entry_ctx)
            if trigger not in PASSIVE_PROC_TRIGGERS:
                raise KitError(
                    f"{entry_ctx}: trigger must be one of {sorted(PASSIVE_PROC_TRIGGERS)}"
                )
            try:
                damage_type = DamageType(entry.get("damage_type"))
            except ValueError as exc:
                raise KitError(f"{entry_ctx}: unknown damage_type") from exc
            cooldown = _optional_positive_fraction(entry, "cooldown_seconds", entry_ctx)
            duration = _optional_positive_fraction(entry, "duration_seconds", entry_ctx)
            if trigger in {"every_n_attacks", "every_n_hits", "every_n_ability_hits"}:
                every = _optional_positive_int(entry, "every", entry_ctx, minimum=2)
                if every is None:
                    raise KitError(f"{entry_ctx}: {trigger} requires every >= 2")
            elif trigger == "after_ability":
                max_stacks = _optional_positive_int(entry, "max_stacks", entry_ctx)
                charges_per_cast = _optional_positive_int(entry, "charges_per_cast", entry_ctx) or 1
                raw_consume_all = entry.get("consume_all_stacks", False)
                if not isinstance(raw_consume_all, bool):
                    raise KitError(f"{entry_ctx}: consume_all_stacks must be a boolean")
                consume_all_stacks = raw_consume_all
                if max_stacks is not None and charges_per_cast > max_stacks:
                    raise KitError(
                        f"{entry_ctx}: charges_per_cast ({charges_per_cast}) exceeds "
                        f"max_stacks ({max_stacks})"
                    )
            elif trigger == "below_hp_percent":
                threshold_hp = _optional_positive_fraction(entry, "threshold_hp_percent", entry_ctx)
                if threshold_hp is None or threshold_hp > 1:
                    raise KitError(
                        f"{entry_ctx}: below_hp_percent requires threshold_hp_percent in (0, 1]"
                    )
            elif trigger == "at_max_stacks":
                stack_source_id = _text(entry, "stack_source_id", entry_ctx)
        elif kind == "shield":
            trigger = _text(entry, "trigger", entry_ctx)
            if trigger not in PASSIVE_SHIELD_TRIGGERS:
                raise KitError(
                    f"{entry_ctx}: trigger must be one of {sorted(PASSIVE_SHIELD_TRIGGERS)}"
                )
            shield_type = str(entry.get("shield_type", "normal"))
            if shield_type not in PASSIVE_SHIELD_TYPES:
                raise KitError(
                    f"{entry_ctx}: shield_type must be one of {sorted(PASSIVE_SHIELD_TYPES)}"
                )
            duration = _optional_positive_fraction(entry, "duration_seconds", entry_ctx)
            cooldown = _optional_positive_fraction(entry, "cooldown_seconds", entry_ctx)
            if trigger == "every_n_hits":
                every = _optional_positive_int(entry, "every", entry_ctx, minimum=2)
                if every is None:
                    raise KitError(f"{entry_ctx}: every_n_hits requires every >= 2")
            elif trigger == "below_hp_percent":
                threshold_hp = _optional_positive_fraction(entry, "threshold_hp_percent", entry_ctx)
                if threshold_hp is None or threshold_hp > 1:
                    raise KitError(
                        f"{entry_ctx}: below_hp_percent requires threshold_hp_percent in (0, 1]"
                    )
        elif kind == "damage_taken_modifier":
            mode = str(entry.get("mode", "percent"))
            if mode not in PASSIVE_DR_MODES:
                raise KitError(f"{entry_ctx}: mode must be one of {sorted(PASSIVE_DR_MODES)}")
            raw_dt = entry.get("damage_type")
            if raw_dt is not None:
                try:
                    damage_type = DamageType(raw_dt)
                except ValueError as exc:
                    raise KitError(f"{entry_ctx}: unknown damage_type") from exc
            dr_cap = _optional_positive_fraction(entry, "damage_reduction_cap", entry_ctx)
            if dr_cap is not None and dr_cap > 1:
                raise KitError(f"{entry_ctx}: damage_reduction_cap must be <= 1")
            cooldown = _optional_positive_fraction(entry, "cooldown_seconds", entry_ctx)
        elif kind == "resource_restore":
            trigger = _text(entry, "trigger", entry_ctx)
            if trigger not in PASSIVE_RESOURCE_TRIGGERS:
                raise KitError(
                    f"{entry_ctx}: trigger must be one of {sorted(PASSIVE_RESOURCE_TRIGGERS)}"
                )
            resource = _text(entry, "resource", entry_ctx)
            if resource not in PASSIVE_RESOURCES:
                raise KitError(f"{entry_ctx}: resource must be one of {sorted(PASSIVE_RESOURCES)}")
            cooldown = _optional_positive_fraction(entry, "cooldown_seconds", entry_ctx)
            if trigger == "every_n_ability_hits":
                every = _optional_positive_int(entry, "every", entry_ctx, minimum=2)
                if every is None:
                    raise KitError(f"{entry_ctx}: {trigger} requires every >= 2")

        effects.append(
            PassiveEffectSpec(
                id=effect_id,
                name=name,
                kind=kind,
                formula=formula,
                label=label,
                source=source,
                stat=stat_id,
                mode=mode,
                trigger=trigger,
                max_stacks=max_stacks,
                charges_per_cast=charges_per_cast,
                consume_all_stacks=consume_all_stacks,
                max_stacks_multiplier=max_mult,
                only_at_max=only_at_max,
                duration_seconds=duration,
                cooldown_seconds=cooldown,
                cooldown_formula=cooldown_formula,
                every=every,
                stacks_required=stacks_req,
                stack_source_id=stack_source_id,
                damage_type=damage_type,
                shield_type=shield_type,
                threshold_hp_percent=threshold_hp,
                damage_reduction_cap=dr_cap,
                resource=resource,
                target_kind=target_kind,
                input_name=raw_input,
                condition=condition,
            )
        )
    return tuple(effects)


def _active_effects(
    record: Mapping[str, Any], max_rank: int, valid_case_ids: set[str], context: str
) -> tuple[ActiveEffectSpec, ...]:
    effects: list[ActiveEffectSpec] = []
    seen_ids: set[str] = set()
    for index, entry in enumerate(_list(record, "active_effects", context)):
        entry_ctx = f"{context}.active_effects[{index}]"
        if not isinstance(entry, Mapping):
            raise KitError(f"{entry_ctx}: must be an object")
        effect_id = _text(entry, "id", entry_ctx)
        if CASE_ID.fullmatch(effect_id) is None:
            raise KitError(f"{entry_ctx}: id must be lowercase snake_case")
        if effect_id in seen_ids:
            raise KitError(f"{entry_ctx}: duplicate active effect id {effect_id!r}")
        seen_ids.add(effect_id)
        name = _text(entry, "name", entry_ctx)
        kind = _text(entry, "kind", entry_ctx)
        if kind not in ACTIVE_EFFECT_KINDS:
            raise KitError(f"{entry_ctx}: kind must be one of {sorted(ACTIVE_EFFECT_KINDS)}")
        if entry.get("formula") is None and kind in _FORMULA_OPTIONAL_ACTIVE_KINDS:
            formula: Mapping[str, Any] = {"op": "constant", "value": 1}
        else:
            formula = _formula(entry, max_rank, entry_ctx)
        label = _label(entry, entry_ctx)
        source = _text(entry, "source", entry_ctx)
        raw_cases = _list(entry, "case_ids", entry_ctx)
        case_ids: list[str] = []
        for cid in raw_cases:
            if not isinstance(cid, str) or cid not in valid_case_ids:
                raise KitError(f"{entry_ctx}: unknown case_id {cid!r}")
            case_ids.append(cid)
        duration = _optional_positive_fraction(entry, "duration_seconds", entry_ctx)
        duration_formula: Mapping[str, Any] | None = None
        if entry.get("duration_formula") is not None:
            duration_formula = _formula(
                {"formula": entry["duration_formula"]}, max_rank, f"{entry_ctx}.duration_formula"
            )
        window_seconds = _optional_positive_fraction(entry, "window_seconds", entry_ctx)
        min_formula: Mapping[str, Any] | None = None
        if entry.get("min_formula") is not None:
            min_formula = _formula(
                {"formula": entry["min_formula"]}, max_rank, f"{entry_ctx}.min_formula"
            )
        max_formula: Mapping[str, Any] | None = None
        if entry.get("max_formula") is not None:
            max_formula = _formula(
                {"formula": entry["max_formula"]}, max_rank, f"{entry_ctx}.max_formula"
            )
        part_index: int | None = None
        raw_part_idx = entry.get("part_index")
        if raw_part_idx is not None:
            if (
                isinstance(raw_part_idx, bool)
                or not isinstance(raw_part_idx, int)
                or raw_part_idx < 0
            ):
                raise KitError(f"{entry_ctx}: part_index must be a non-negative integer")
            part_index = raw_part_idx
        input_name: str | None = None
        raw_input_name = entry.get("input_name")
        if raw_input_name is not None:
            if not isinstance(raw_input_name, str) or not raw_input_name.strip():
                raise KitError(f"{entry_ctx}: input_name must be a non-empty string")
            input_name = raw_input_name
        condition = entry.get("condition", "")
        if not isinstance(condition, str):
            raise KitError(f"{entry_ctx}: condition must be a string")
        over_duration = entry.get("over_duration", False)
        if not isinstance(over_duration, bool):
            raise KitError(f"{entry_ctx}: over_duration must be a boolean")
        uses_hsp = entry.get("uses_hsp", True)
        if not isinstance(uses_hsp, bool):
            raise KitError(f"{entry_ctx}: uses_hsp must be a boolean")

        stat_id: str | None = None
        mode = "flat"
        shield_type = "normal"
        damage_type: DamageType | None = None
        dr_cap: Fraction | None = None

        if kind == "stat_bonus":
            stat_id = _text(entry, "stat", entry_ctx)
            definition = STATS.get(stat_id)
            if definition is None or not definition.resolvable:
                raise KitError(f"{entry_ctx}: {stat_id!r} is not a resolvable stat")
            mode = str(entry.get("mode", "flat"))
            if mode not in PASSIVE_STAT_MODES:
                raise KitError(f"{entry_ctx}: mode must be one of {sorted(PASSIVE_STAT_MODES)}")
        elif kind in {"shield", "recent_damage_shield"}:
            shield_type = str(entry.get("shield_type", "normal"))
            if shield_type not in PASSIVE_SHIELD_TYPES:
                raise KitError(
                    f"{entry_ctx}: shield_type must be one of {sorted(PASSIVE_SHIELD_TYPES)}"
                )
        elif kind == "damage_taken_modifier":
            mode = str(entry.get("mode", "percent"))
            if mode not in PASSIVE_DR_MODES:
                raise KitError(f"{entry_ctx}: mode must be one of {sorted(PASSIVE_DR_MODES)}")
            raw_dt = entry.get("damage_type")
            if raw_dt is not None:
                try:
                    damage_type = DamageType(raw_dt)
                except ValueError as exc:
                    raise KitError(f"{entry_ctx}: unknown damage_type") from exc
            dr_cap = _optional_positive_fraction(entry, "damage_reduction_cap", entry_ctx)
            if dr_cap is not None and dr_cap > 1:
                raise KitError(f"{entry_ctx}: damage_reduction_cap must be <= 1")
        elif kind == "invulnerable":
            mode = str(entry.get("mode", "invulnerable"))
            if mode not in ACTIVE_INVULN_MODES:
                raise KitError(f"{entry_ctx}: mode must be one of {sorted(ACTIVE_INVULN_MODES)}")

        effects.append(
            ActiveEffectSpec(
                id=effect_id,
                name=name,
                kind=kind,
                formula=formula,
                label=label,
                source=source,
                case_ids=tuple(case_ids),
                duration_seconds=duration,
                duration_formula=duration_formula,
                stat=stat_id,
                mode=mode,
                shield_type=shield_type,
                damage_type=damage_type,
                damage_reduction_cap=dr_cap,
                over_duration=over_duration,
                uses_hsp=uses_hsp,
                window_seconds=window_seconds,
                min_formula=min_formula,
                max_formula=max_formula,
                part_index=part_index,
                input_name=input_name,
                condition=condition,
            )
        )
    return tuple(effects)


def _cc_effects(
    record: Mapping[str, Any], max_rank: int, valid_cases: set[str], context: str
) -> tuple[CCEffectSpec, ...]:
    raw_list = record.get("cc_effects")
    if raw_list is None:
        return ()
    if not isinstance(raw_list, list):
        raise KitError(f"{context}: cc_effects must be a list")
    effects: list[CCEffectSpec] = []
    seen: set[str] = set()
    for index, entry in enumerate(raw_list):
        ectx = f"{context}.cc_effects[{index}]"
        if not isinstance(entry, Mapping):
            raise KitError(f"{ectx}: must be an object")
        eid = _text(entry, "id", ectx)
        if CASE_ID.fullmatch(eid) is None:
            raise KitError(f"{ectx}: id must be lowercase snake_case")
        if eid in seen:
            raise KitError(f"{ectx}: duplicate cc_effect id {eid!r}")
        seen.add(eid)
        kind = _text(entry, "kind", ectx)
        if kind not in CC_KINDS:
            raise KitError(f"{ectx}: unknown kind {kind!r} (known: {sorted(CC_KINDS)})")
        dur_formula = entry.get("duration_formula")
        issues = formula_issues(dur_formula, ops=ABILITY_OPS)
        if issues:
            raise KitError(f"{ectx}: invalid duration_formula: {'; '.join(issues)}")
        for length in _rank_lists(dur_formula):
            if length != max_rank:
                raise KitError(
                    f"{ectx}: duration_formula by_rank has {length} values, "
                    f"the ability has {max_rank}"
                )
        raw_cases = entry.get("case_ids")
        case_ids: tuple[str, ...] = ()
        if raw_cases is not None:
            if not isinstance(raw_cases, list) or not all(isinstance(c, str) for c in raw_cases):
                raise KitError(f"{ectx}: case_ids must be a list of case id strings")
            unknown_c = [c for c in raw_cases if c not in valid_cases]
            if unknown_c:
                raise KitError(f"{ectx}: unknown case_ids {unknown_c}")
            case_ids = tuple(raw_cases)
        tenacity_applies = entry.get("tenacity_applies", kind not in CC_TENACITY_IMMUNE)
        if not isinstance(tenacity_applies, bool):
            raise KitError(f"{ectx}: tenacity_applies must be true or false")
        cleansable_cleanse = entry.get("cleansable_by_cleanse", kind not in CC_CLEANSE_IMMUNE)
        if not isinstance(cleansable_cleanse, bool):
            raise KitError(f"{ectx}: cleansable_by_cleanse must be true or false")
        cleansable_qss = entry.get("cleansable_by_qss", kind not in CC_QSS_IMMUNE)
        if not isinstance(cleansable_qss, bool):
            raise KitError(f"{ectx}: cleansable_by_qss must be true or false")
        condition = str(entry.get("condition", ""))
        effects.append(
            CCEffectSpec(
                id=eid,
                name=_text(entry, "name", ectx),
                kind=kind,
                duration_formula=dur_formula,
                label=_label(entry, ectx),
                source=_text(entry, "source", ectx),
                case_ids=case_ids,
                tenacity_applies=tenacity_applies,
                cleansable_by_cleanse=cleansable_cleanse,
                cleansable_by_qss=cleansable_qss,
                condition=condition,
            )
        )
    return tuple(effects)


def _ability(slot: str, record: Any) -> AbilitySpec:
    context = f"kit.{slot}"
    if not isinstance(record, Mapping):
        raise KitError(f"{context}: must be an object")
    max_rank = record.get("max_rank")
    if isinstance(max_rank, bool) or not isinstance(max_rank, int) or max_rank < 1:
        raise KitError(f"{context}: max_rank must be a positive integer")
    cases: list[CaseSpec] = []
    for index, case in enumerate(_list(record, "cases", context)):
        case_context = f"{context}.cases[{index}]"
        if not isinstance(case, Mapping):
            raise KitError(f"{case_context}: must be an object")
        case_id = _text(case, "id", case_context)
        if CASE_ID.fullmatch(case_id) is None:
            raise KitError(f"{case_context}: id must be lowercase snake_case")
        if any(item.id == case_id for item in cases):
            raise KitError(f"{case_context}: duplicate case id {case_id!r}")
        parts = []
        raw_parts = _list(case, "parts", case_context)
        if not raw_parts:
            raise KitError(f"{case_context}: parts must not be empty")
        for part_index, part in enumerate(raw_parts):
            part_context = f"{case_context}.parts[{part_index}]"
            if not isinstance(part, Mapping):
                raise KitError(f"{part_context}: must be an object")
            try:
                damage_type = DamageType(part.get("damage_type"))
            except ValueError as exc:
                raise KitError(f"{part_context}: unknown damage_type") from exc
            parts.append(
                DamagePartSpec(
                    damage_type,
                    _formula(part, max_rank, part_context),
                    _label(part, part_context),
                    _text(part, "source", part_context),
                    _text(part, "damage_type_source", part_context),
                )
            )
        recast = case.get("recast", False)
        if not isinstance(recast, bool):
            raise KitError(f"{case_context}: recast must be true or false")
        aoe = case.get("aoe")
        if aoe is not None and not isinstance(aoe, bool):
            raise KitError(f"{case_context}: aoe must be true or false")
        max_targets = _optional_positive_int(case, "max_targets", case_context, minimum=1)
        sec_ratio = _optional_positive_fraction(case, "secondary_damage_ratio", case_context)
        if sec_ratio is None:
            sec_ratio = Fraction(1)
        elif sec_ratio > 1:
            raise KitError(f"{case_context}: secondary_damage_ratio must be <= 1")
        if "secondary_damage_ratio" in case and max_targets == 1:
            raise KitError(
                f"{case_context}: secondary_damage_ratio cannot be used with max_targets 1"
            )
        case_cost = _cost(case, max_rank, case_context)
        cases.append(
            CaseSpec(
                case_id,
                _text(case, "name", case_context),
                tuple(parts),
                recast,
                case_cost,
                aoe=aoe,
                max_targets=max_targets,
                secondary_damage_ratio=sec_ratio,
            )
        )
    passive_stats = []
    for index, entry in enumerate(_list(record, "passive_stats", context)):
        entry_context = f"{context}.passive_stats[{index}]"
        if not isinstance(entry, Mapping):
            raise KitError(f"{entry_context}: must be an object")
        stat_id = _text(entry, "stat", entry_context)
        definition = STATS.get(stat_id)
        if definition is None or not definition.resolvable:
            raise KitError(f"{entry_context}: {stat_id!r} is not a resolvable stat")
        passive_stats.append(
            PassiveStatSpec(
                stat_id,
                _formula(entry, max_rank, entry_context),
                _label(entry, entry_context),
                _text(entry, "source", entry_context),
                _text(entry, "condition", entry_context),
            )
        )
    not_modelled = _list(record, "not_modelled", context)
    if not all(isinstance(item, str) and item.strip() for item in not_modelled):
        raise KitError(f"{context}: not_modelled must list non-empty strings")
    window = record.get("recast_window_seconds")
    if window is not None and (
        isinstance(window, bool) or not isinstance(window, (int, float)) or window <= 0
    ):
        raise KitError(f"{context}: recast_window_seconds must be a positive number")
    if window is not None and not any(case.recast for case in cases):
        raise KitError(f"{context}: recast_window_seconds needs a recast case")
    max_recasts = record.get("max_recasts", 1)
    if isinstance(max_recasts, bool) or not isinstance(max_recasts, int) or max_recasts < 1:
        raise KitError(f"{context}: max_recasts must be a positive integer")
    interval = record.get("recast_interval_seconds")
    if interval is not None and (
        isinstance(interval, bool) or not isinstance(interval, (int, float)) or interval <= 0
    ):
        raise KitError(f"{context}: recast_interval_seconds must be a positive number")
    recasts = "max_recasts" in record or interval is not None
    if recasts and not any(case.recast for case in cases):
        raise KitError(f"{context}: max_recasts and recast_interval_seconds need a recast case")
    return AbilitySpec(
        slot,
        _text(record, "name", context),
        max_rank,
        tuple(cases),
        tuple(passive_stats),
        tuple(not_modelled),
        None if window is None else Fraction(str(window)),
        max_recasts,
        None if interval is None else Fraction(str(interval)),
        _cost(record, max_rank, context),
        _passive_effects(record, max_rank, context),
        _active_effects(record, max_rank, {case.id for case in cases}, context),
        _cc_effects(record, max_rank, {case.id for case in cases}, context),
    )


def parse_kit(document: Any) -> Kit:
    """Validate a kit document and return it as typed values."""
    if not isinstance(document, Mapping):
        raise KitError("kit: the document must be a JSON object")
    if document.get("schema") != SCHEMA:
        raise KitError(f"kit: schema must be {SCHEMA!r}")
    champion = _text(document, "champion", "kit")
    label = _label(document, "kit")
    abilities_raw = document.get("abilities")
    if not isinstance(abilities_raw, Mapping) or not abilities_raw:
        raise KitError("kit: 'abilities' must be a non-empty object")
    unknown = sorted(set(abilities_raw) - set(SLOTS))
    if unknown:
        raise KitError(f"kit: unknown ability slots {unknown}")
    abilities = {
        slot: _ability(slot, abilities_raw[slot]) for slot in SLOTS if slot in abilities_raw
    }
    return Kit(
        champion,
        label,
        _text(document, "game_version", "kit"),
        _text(document, "content_version", "kit"),
        abilities,
    )


def kit_path(root: Path, champion_id: str) -> Path:
    return root / "lol-knowledge" / "champions" / champion_id / KIT_FILENAME


def load_kit(root: Path, champion_id: str) -> Kit | None:
    """Load a champion's kit, or ``None`` when the champion has none.

    ``champion_id`` must already be a validated snapshot id.
    """
    path = kit_path(root, champion_id)
    if not path.is_file():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KitError(f"{path.as_posix()} is not valid UTF-8 JSON: {exc}") from exc
    kit = parse_kit(document)
    if kit.champion != champion_id:
        raise KitError(f"{path.as_posix()} is for {kit.champion!r}, not {champion_id!r}")
    return kit
