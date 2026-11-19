"""Ability scenarios: attacker sheet + kit + target → mitigated damage per part.

Pure functions over already-loaded values; the CLI does the loading.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from .damage import DamageResult, DamageType, Modifiers, mitigate
from .errors import StatsError
from .kit import DamagePart, Kit, ability_damage
from .stats import ItemData, Label, StatSheet, weakest

# Unit kinds that item conditions and limits distinguish.
TARGET_KINDS = frozenset({"champion", "monster", "minion", "structure"})

PENETRATION = {
    DamageType.PHYSICAL: ("armor_penetration_percent", "lethality"),
    DamageType.MAGIC: ("magic_penetration_percent", "magic_penetration_flat"),
}


@dataclass(frozen=True)
class Target:
    """The defender: resistances, health stats for formulas, and how they were obtained.

    ``kind`` is ``None`` when nobody said what the target is; effects that
    depend on it must then refuse to guess. ``items`` are the target's own
    items, whose damage-taken effects a rotation applies.
    """

    armor: Fraction
    magic_resist: Fraction
    stats: Mapping[str, Fraction]
    label: Label
    description: str
    kind: str | None = None
    items: tuple[ItemData, ...] = ()

    def resistance(self, damage_type: DamageType) -> Fraction | None:
        if damage_type is DamageType.PHYSICAL:
            return self.armor
        if damage_type is DamageType.MAGIC:
            return self.magic_resist
        return None


def _health(
    max_health: Fraction | None,
    current_health: Fraction | None,
    bonus_health: Fraction | None = None,
) -> dict[str, Fraction]:
    stats: dict[str, Fraction] = {}
    if bonus_health is not None:
        if bonus_health < 0:
            raise StatsError("target bonus health must not be negative")
        if max_health is not None and bonus_health > max_health:
            raise StatsError("target bonus health exceeds its max health")
        stats["bonus_health"] = bonus_health
    if max_health is not None:
        if max_health <= 0:
            raise StatsError("target max health must be positive")
        stats["max_health"] = max_health
    if current_health is not None:
        if current_health < 0:
            raise StatsError("target current health must not be negative")
        if max_health is not None and current_health > max_health:
            raise StatsError("target current health exceeds its max health")
        stats["current_health"] = current_health
    elif max_health is not None:
        stats["current_health"] = max_health
    return stats


def target_from_values(
    armor: Fraction,
    magic_resist: Fraction,
    *,
    max_health: Fraction | None = None,
    current_health: Fraction | None = None,
    bonus_health: Fraction | None = None,
    kind: str | None = None,
) -> Target:
    """A target given by hand.

    Its values are scenario inputs, not knowledge, so they weaken no label.
    """
    if kind is not None and kind not in TARGET_KINDS:
        raise StatsError(f"unknown target kind {kind!r} (use {', '.join(sorted(TARGET_KINDS))})")
    description = f"armor {armor}, magic resist {magic_resist}"
    if kind is not None:
        description = f"{kind}, {description}"
    return Target(
        armor,
        magic_resist,
        _health(max_health, current_health, bonus_health),
        Label.OFFICIAL,
        description,
        kind,
    )


def target_from_sheet(sheet: StatSheet, *, current_health: Fraction | None = None) -> Target:
    """A target champion resolved with the same stat sheet as the attacker."""
    armor, magic_resist, health = sheet["armor"], sheet["magic_resist"], sheet["health"]
    items = ", ".join(item.id for item in sheet.items) or "no items"
    return Target(
        armor.total(),
        magic_resist.total(),
        _health(health.total(), current_health, health.scoped("bonus")),
        weakest((armor.label, magic_resist.label, health.label)),
        f"{sheet.champion.id} level {sheet.level} ({items})",
        "champion",
        sheet.items,
    )


@dataclass(frozen=True)
class PartOutcome:
    part: DamagePart
    mitigation: DamageResult


@dataclass(frozen=True)
class CaseOutcome:
    id: str
    name: str
    parts: tuple[PartOutcome, ...]

    @property
    def total(self) -> Fraction:
        return sum((item.mitigation.damage for item in self.parts), start=Fraction(0))


@dataclass(frozen=True)
class AbilityOutcome:
    slot: str
    name: str
    rank: int
    cases: tuple[CaseOutcome, ...]
    label: Label
    not_modelled: tuple[str, ...]


def penetration_modifiers(sheet: StatSheet, damage_type: DamageType) -> Modifiers:
    """The attacker's penetration against ``damage_type``; true damage has none."""
    if damage_type not in PENETRATION:
        return Modifiers()
    percent, flat = PENETRATION[damage_type]
    return Modifiers(
        percent_penetration=sheet[percent].sources(), flat_penetration=sheet[flat].sources()
    )


def evaluate_ability(
    kit: Kit,
    sheet: StatSheet,
    slot: str,
    rank: int,
    target: Target,
    *,
    case: str | None = None,
    inputs: Mapping[str, Any] | None = None,
) -> AbilityOutcome:
    """Raw damage of each part from the kit, mitigated by the target's matching resistance."""
    ability = kit.ability(slot)
    parts = ability_damage(kit, slot, rank, sheet, case=case, target=target.stats, inputs=inputs)
    # Unmodelled sources on the sheet (tree runes) could change the damage.
    labels = [target.label, *([Label.PENDING] if sheet.pending_effects else [])]
    by_case: dict[str, list[PartOutcome]] = {}
    for part in parts:
        resistance = target.resistance(part.damage_type)
        mitigation = mitigate(
            part.raw, part.damage_type, resistance, penetration_modifiers(sheet, part.damage_type)
        )
        labels.append(part.label)
        if part.damage_type in PENETRATION:
            percent, flat = PENETRATION[part.damage_type]
            labels += [sheet[percent].label, sheet[flat].label]
        by_case.setdefault(part.case, []).append(PartOutcome(part, mitigation))
    names = {item.id: item.name for item in ability.cases}
    cases = tuple(
        CaseOutcome(case_id, names[case_id], tuple(items)) for case_id, items in by_case.items()
    )
    return AbilityOutcome(
        ability.slot, ability.name, rank, cases, weakest(labels), ability.not_modelled
    )
