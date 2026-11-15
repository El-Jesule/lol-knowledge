"""Inputs and outcomes for the future deterministic damage engine.

This module defines the contract only. It performs no damage simulation, no
build search and no temporal loop.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .schema import HOLDER_RANGES, OUTCOME_STATES, STAT_ORDER

TARGET_KINDS = frozenset({"champion", "monster", "minion", "structure"})
_ABILITY_SLOTS = frozenset({"passive", "q", "w", "e", "r"})


@dataclass(frozen=True)
class ChampionState:
    """The champion and its post-rune, post-item stat sheet.

    ``attack_range`` is the game's melee/ranged classification of the holder.
    Effects such as Blade of the Ruined King branch on it, so it is required:
    an absent value must never silently default to melee.
    """

    champion_id: str
    level: int
    ability_ranks: Mapping[str, int]
    stats: Mapping[str, float]
    attack_range: str


@dataclass(frozen=True)
class ItemSlot:
    """One equipped item, its copy count and any runtime stacks."""

    item_id: str
    count: int = 1
    stacks: Mapping[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class RuneState:
    """Selected runes and shards."""

    rune_ids: tuple[int, ...] = ()
    shards: tuple[str, ...] = ()


@dataclass(frozen=True)
class TargetProfile:
    """The target's defensive state.

    ``bonus_health`` is required: effects such as Lord Dominik's Regards read
    it, and an omitted value must not silently behave like a real zero.
    """

    kind: str
    level: int
    armor: float
    magic_resist: float
    health: float
    max_health: float
    bonus_health: float
    damage_reduction_percent: float = 0.0


@dataclass(frozen=True)
class ImpactConditions:
    """Game state that conditional effects read."""

    critical_strike: bool = False
    on_hit: bool = False
    ability_hit: bool = False
    distance: float | None = None
    target_health_ratio: float | None = None
    stacks: Mapping[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class RotationStep:
    """One ability or auto-attack window in the rotation."""

    ability: str
    rank: int
    hits: int = 1
    conditions: ImpactConditions = field(default_factory=ImpactConditions)
    cast_time_seconds: float | None = None


@dataclass(frozen=True)
class DamageRequest:
    """Everything one burst-damage evaluation needs; no field is optional."""

    game_version: str
    champion: ChampionState
    items: tuple[ItemSlot, ...]
    runes: RuneState
    target: TargetProfile
    conditions: ImpactConditions
    rotation: tuple[RotationStep, ...]


@dataclass(frozen=True)
class DamageOutcome:
    """A classified result; ``total`` is ``None`` unless it is reliable."""

    status: str
    total: float | None = None
    components: tuple[dict[str, Any], ...] = ()
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "total": self.total,
            "components": list(self.components),
            "reasons": list(self.reasons),
        }

    @classmethod
    def unevaluable(cls, status: str, reason: str) -> DamageOutcome:
        if status not in OUTCOME_STATES:
            raise ValueError(f"unknown outcome status {status!r}")
        return cls(status=status, total=None, reasons=(reason,))


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def required_stat_sheet() -> tuple[str, ...]:
    """Return the canonical champion stats a request must provide.

    Zero is a valid value, but the key must be present so an absent value is
    never confused with zero.
    """
    return tuple(STAT_ORDER)


def validate_request(request: DamageRequest) -> tuple[str, ...]:
    """Return every structural problem; an empty tuple means it is usable."""
    problems: list[str] = []
    if not isinstance(request.game_version, str) or not request.game_version:
        problems.append("game_version must be a non-empty string")

    champion = request.champion
    if not isinstance(champion.champion_id, str) or not champion.champion_id:
        problems.append("champion.champion_id must be a non-empty string")
    if not isinstance(champion.level, int) or isinstance(champion.level, bool):
        problems.append("champion.level must be an integer")
    elif not 1 <= champion.level <= 99:
        problems.append("champion.level must be between 1 and 99")
    if not champion.ability_ranks:
        problems.append("champion.ability_ranks must not be empty")
    for ability, rank in champion.ability_ranks.items():
        if ability not in _ABILITY_SLOTS:
            problems.append(f"champion.ability_ranks has unknown slot {ability!r}")
        if not isinstance(rank, int) or isinstance(rank, bool) or rank < 1:
            problems.append(f"champion.ability_ranks[{ability!r}] must be a positive integer")
    if champion.attack_range not in HOLDER_RANGES:
        problems.append(f"champion.attack_range must be one of {sorted(HOLDER_RANGES)}")
    for stat in required_stat_sheet():
        if stat not in champion.stats:
            problems.append(f"champion.stats is missing {stat!r}")
        elif not _is_number(champion.stats[stat]):
            problems.append(f"champion.stats[{stat!r}] must be a finite number")

    if not request.items:
        problems.append("items must not be empty")
    seen_items: set[str] = set()
    for index, item in enumerate(request.items):
        if not isinstance(item.item_id, str) or not item.item_id:
            problems.append(f"items[{index}].item_id must be a non-empty string")
        elif item.item_id in seen_items:
            problems.append(f"items[{index}] repeats item {item.item_id!r}")
        seen_items.add(item.item_id)
        if not isinstance(item.count, int) or isinstance(item.count, bool) or item.count < 1:
            problems.append(f"items[{index}].count must be a positive integer")
        for key, value in item.stacks.items():
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                problems.append(f"items[{index}].stacks[{key!r}] must be a non-negative integer")

    for index, rune_id in enumerate(request.runes.rune_ids):
        if not isinstance(rune_id, int) or isinstance(rune_id, bool) or rune_id < 0:
            problems.append(f"runes.rune_ids[{index}] must be a non-negative integer")
    for index, shard in enumerate(request.runes.shards):
        if not isinstance(shard, str) or not shard:
            problems.append(f"runes.shards[{index}] must be a non-empty string")

    target = request.target
    if target.kind not in TARGET_KINDS:
        problems.append(f"target.kind must be one of {sorted(TARGET_KINDS)}")
    if not isinstance(target.level, int) or isinstance(target.level, bool) or target.level < 1:
        problems.append("target.level must be a positive integer")
    for name in ("armor", "magic_resist", "health", "max_health", "bonus_health"):
        value = getattr(target, name)
        if not _is_number(value) or value < 0:
            problems.append(f"target.{name} must be a non-negative finite number")
    if _is_number(target.max_health) and target.max_health <= 0:
        problems.append("target.max_health must be positive")
    if (
        _is_number(target.health)
        and _is_number(target.max_health)
        and target.health > target.max_health
    ):
        problems.append("target.health must not exceed target.max_health")
    if (
        not _is_number(target.damage_reduction_percent)
        or not 0 <= target.damage_reduction_percent <= 100
    ):
        problems.append("target.damage_reduction_percent must be between 0 and 100")

    for label, conditions in (
        ("conditions", request.conditions),
        *(
            (f"rotation[{index}].conditions", step.conditions)
            for index, step in enumerate(request.rotation)
        ),
    ):
        if conditions.target_health_ratio is not None and (
            not _is_number(conditions.target_health_ratio)
            or not 0 <= conditions.target_health_ratio <= 1
        ):
            problems.append(f"{label}.target_health_ratio must be between 0 and 1")
        if conditions.distance is not None and (
            not _is_number(conditions.distance) or conditions.distance < 0
        ):
            problems.append(f"{label}.distance must be non-negative")
        for key, value in conditions.stacks.items():
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                problems.append(f"{label}.stacks[{key!r}] must be a non-negative integer")

    if not request.rotation:
        problems.append("rotation must not be empty")
    for index, step in enumerate(request.rotation):
        if not isinstance(step.ability, str) or not step.ability:
            problems.append(f"rotation[{index}].ability must be a non-empty string")
        if not isinstance(step.rank, int) or isinstance(step.rank, bool) or step.rank < 1:
            problems.append(f"rotation[{index}].rank must be a positive integer")
        if not isinstance(step.hits, int) or isinstance(step.hits, bool) or step.hits < 1:
            problems.append(f"rotation[{index}].hits must be a positive integer")
        if step.cast_time_seconds is not None and (
            not _is_number(step.cast_time_seconds) or step.cast_time_seconds < 0
        ):
            problems.append(f"rotation[{index}].cast_time_seconds must be non-negative")

    return tuple(problems)


def formula_stat_requirements(model: Mapping[str, Any]) -> dict[str, tuple[str, ...]]:
    """Collect the stat keys referenced by object formulas in a model.

    ``current``/``max`` scopes are target stats; the rest are champion stats.
    """
    champion: set[str] = set()
    target: set[str] = set()

    def walk(formula: Any) -> None:
        if not isinstance(formula, Mapping):
            return
        operation = formula.get("op")
        if operation in {"stat", "percent_of"}:
            stat = formula.get("stat")
            scope = formula.get("scope")
            if not isinstance(stat, str) or not isinstance(scope, str):
                return
            key = stat if scope == "total" else f"{scope}_{stat}"
            subject = formula.get("subject")
            is_target = subject == "target" or (subject is None and scope in {"current", "max"})
            if is_target:
                target.add(key)
            else:
                champion.add(key)
            return
        if operation == "by_holder_range":
            for branch in ("melee", "ranged"):
                walk(formula.get(branch))
            return
        operands = formula.get("operands")
        if isinstance(operands, Sequence) and not isinstance(operands, (str, bytes)):
            for operand in operands:
                walk(operand)

    for obj in model.get("objects") or []:
        for effect in obj.get("effects") or []:
            for component in effect.get("components") or []:
                walk(component.get("formula"))
                walk(component.get("magnitude"))
    return {"champion": tuple(sorted(champion)), "target": tuple(sorted(target))}
