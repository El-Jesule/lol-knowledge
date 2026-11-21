"""Evaluate a champion kit against a stat sheet. Pure functions: no file access."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from ..damage import DamageType
from ..errors import KitError
from ..formula import ABILITY_OPS, FormulaError, evaluate_formula
from ..stats.labels import Label, weakest
from ..stats.registry import Stacking
from ..stats.sheet import Contribution, StatSheet
from .model import AbilitySpec, Kit


@dataclass(frozen=True)
class DamagePart:
    slot: str
    case: str
    index: int
    damage_type: DamageType
    raw: Fraction
    label: Label
    dependencies: tuple[str, ...]
    source: str


def _rank(ability: AbilitySpec, rank: object) -> int:
    if isinstance(rank, bool) or not isinstance(rank, int):
        raise KitError(f"{ability.slot}: rank must be an integer, got {rank!r}")
    if not 1 <= rank <= ability.max_rank:
        raise KitError(f"{ability.slot}: rank must be between 1 and {ability.max_rank}")
    return rank


def sheet_stats(sheet: StatSheet) -> tuple[dict[str, Fraction], dict[str, tuple[str, Label]]]:
    """Formula stat keys available from a sheet, and the stat id and label behind each key.

    Blocked and pending stats are absent, so a formula that needs one fails
    instead of reading a guess.
    """
    values: dict[str, Fraction] = {}
    origin: dict[str, tuple[str, Label]] = {}
    for stat_id, value in sheet.values.items():
        if value.status != "resolved":
            continue
        values[stat_id] = value.total()
        origin[stat_id] = (stat_id, value.label)
        if value.definition.stacking is Stacking.ADDITIVE:
            for scope in ("base", "bonus"):
                key = f"{scope}_{stat_id}"
                if scope == "bonus" and value.definition.soft_cap is not None:
                    # Effective bonus after soft caps (e.g. Janna Tailwind/Zephyr, Hecarim Warpath).
                    values[key] = max(Fraction(0), value.total() - value.scoped("base"))
                else:
                    values[key] = value.scoped(scope)
                origin[key] = (stat_id, value.label)
    return values, origin


def _why_missing(sheet: StatSheet, key: str) -> str:
    stat_id = key.split("_", 1)[1] if key.startswith(("base_", "bonus_")) else key
    value = sheet.values.get(stat_id)
    if value is None:
        return "not a sheet stat"
    return value.blocked or value.definition.pending or "not available"


def ability_damage(
    kit: Kit,
    slot: str,
    rank: int,
    sheet: StatSheet,
    *,
    case: str | None = None,
    target: Mapping[str, Any] | None = None,
    inputs: Mapping[str, Any] | None = None,
) -> tuple[DamagePart, ...]:
    """Raw damage of an ability's cases at ``rank``, ready for the mitigation engine.

    ``case`` selects one alternative (for example the edge of a sweep); without
    it every case is returned. ``target`` holds target stats such as
    ``max_health``; it is never filled in.
    """
    if kit.champion != sheet.champion.id:
        raise KitError(f"kit is for {kit.champion}, the sheet for {sheet.champion.id}")
    ability = kit.ability(slot)
    rank = _rank(ability, rank)
    cases = (ability.case(case),) if case is not None else ability.cases
    if not cases:
        raise KitError(f"{ability.slot}: the kit models no damage for this ability")
    stats, origin = sheet_stats(sheet)
    parts: list[DamagePart] = []
    for item in cases:
        for index, part in enumerate(item.parts):
            try:
                result = evaluate_formula(
                    part.formula,
                    stats,
                    rank=rank,
                    level=sheet.level,
                    inputs=inputs or {},
                    target_stats=target or {},
                    ops=ABILITY_OPS,
                )
            except FormulaError as exc:
                detail = str(exc)
                if exc.code == "missing_stat" and not detail.startswith("missing stat 'target:"):
                    key = detail.split("'")[1]
                    detail += f" ({_why_missing(sheet, key)})"
                raise KitError(f"{ability.slot}.{item.id}[{index}]: {detail}") from exc
            labels = [part.label]
            labels += [origin[key][1] for key in result.dependencies if key in origin]
            parts.append(
                DamagePart(
                    ability.slot,
                    item.id,
                    index,
                    part.damage_type,
                    result.exact,
                    weakest(labels),
                    result.dependencies,
                    part.source,
                )
            )
    return tuple(parts)


def passive_contributions(
    kit: Kit, ranks: Mapping[str, int]
) -> tuple[tuple[str, Contribution], ...]:
    """Stats granted passively by learned abilities, as sheet contributions."""
    contributions: list[tuple[str, Contribution]] = []
    for slot, raw_rank in ranks.items():
        ability = kit.ability(slot)
        rank = _rank(ability, raw_rank)
        for index, entry in enumerate(ability.passive_stats):
            try:
                value = evaluate_formula(entry.formula, {}, rank=rank, ops=ABILITY_OPS).exact
            except FormulaError as exc:
                raise KitError(f"{ability.slot}.passive_stats[{index}]: {exc}") from exc
            contributions.append(
                (
                    entry.stat,
                    Contribution(
                        value,
                        "bonus",
                        f"kit:{kit.champion} {ability.slot} rank {rank} ({entry.source})",
                        entry.label,
                        entry.condition,
                    ),
                )
            )
    return tuple(contributions)
