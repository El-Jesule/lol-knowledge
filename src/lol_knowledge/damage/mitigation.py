"""Deterministic resistance and damage mitigation.

The engine is data-independent: it receives numbers and applies the rules
documented in ``lol-knowledge/mechanics/damage-mitigation.md``. It knows
nothing about champions, items or patches. Arithmetic is exact
(``fractions.Fraction``), so a result never depends on evaluation order or on
binary rounding.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from fractions import Fraction

from ..errors import DamageInputError

Number = int | float | Decimal | Fraction | str

ZERO = Fraction(0)
ONE = Fraction(1)
HUNDRED = Fraction(100)


class DamageType(StrEnum):
    PHYSICAL = "physical"
    MAGIC = "magic"
    TRUE = "true"


def to_fraction(value: Number, name: str) -> Fraction:
    """Convert an input to an exact fraction or raise ``DamageInputError``.

    A ``float`` is read through its shortest decimal representation, so ``0.3``
    means exactly 3/10 rather than its nearest binary value.
    """
    value_type = type(value)
    if value_type is Fraction:
        return value
    if value_type is int:
        return Fraction(value)
    if isinstance(value, bool):
        raise DamageInputError(f"{name}: expected a number, got a boolean")
    if isinstance(value, Fraction):
        return value
    if isinstance(value, int):
        return Fraction(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise DamageInputError(f"{name}: {value!r} is not a finite number")
        return Fraction(repr(value))
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise DamageInputError(f"{name}: {value!r} is not a finite number")
        return Fraction(value)
    if isinstance(value, str):
        try:
            return Fraction(value)
        except (ValueError, ZeroDivisionError) as exc:
            raise DamageInputError(f"{name}: {value!r} is not a number") from exc
    raise DamageInputError(f"{name}: expected a number, got {type(value).__name__}")


def _amounts(values: Iterable[Number], name: str) -> tuple[Fraction, ...]:
    if isinstance(values, (str, bytes)):
        raise DamageInputError(f"{name}: expected a sequence of numbers")
    result = tuple(to_fraction(value, name) for value in values)
    for value in result:
        if value < 0:
            raise DamageInputError(f"{name}: {value} is negative")
    return result


def _shares(values: Iterable[Number], name: str) -> tuple[Fraction, ...]:
    result = _amounts(values, name)
    for value in result:
        if value > 1:
            raise DamageInputError(
                f"{name}: {value} is not a fraction between 0 and 1 (0.3 means 30 %)"
            )
    return result


@dataclass(frozen=True)
class Modifiers:
    """Resistance modifiers; every element is one independent source.

    Percentages are fractions between 0 and 1. Flat penetration is lethality
    when the damage is physical.
    """

    flat_reduction: tuple[Fraction, ...] = ()
    percent_reduction: tuple[Fraction, ...] = ()
    percent_penetration: tuple[Fraction, ...] = ()
    flat_penetration: tuple[Fraction, ...] = ()

    def __post_init__(self) -> None:
        normalized = {
            "flat_reduction": _amounts(self.flat_reduction, "flat reduction"),
            "percent_reduction": _shares(self.percent_reduction, "percent reduction"),
            "percent_penetration": _shares(self.percent_penetration, "percent penetration"),
            "flat_penetration": _amounts(self.flat_penetration, "flat penetration"),
        }
        for field_name, value in normalized.items():
            object.__setattr__(self, field_name, value)

    @property
    def is_empty(self) -> bool:
        return not (
            self.flat_reduction
            or self.percent_reduction
            or self.percent_penetration
            or self.flat_penetration
        )


NO_MODIFIERS = Modifiers()


@dataclass(frozen=True)
class ResistanceTrace:
    """Resistance after each step, in application order."""

    initial: Fraction
    after_flat_reduction: Fraction
    after_percent_reduction: Fraction
    after_percent_penetration: Fraction
    effective: Fraction


@dataclass(frozen=True)
class DamageResult:
    damage_type: DamageType
    raw_damage: Fraction
    modifiers: Modifiers
    resistance: ResistanceTrace | None
    multiplier: Fraction
    damage: Fraction


def _remaining(shares: tuple[Fraction, ...]) -> Fraction:
    return math.prod((ONE - share for share in shares), start=ONE)


def effective_resistance(
    resistance: Number, modifiers: Modifiers = NO_MODIFIERS
) -> ResistanceTrace:
    """Apply reductions and penetrations to a resistance, in the game's order.

    1. Flat reduction: subtracted; it may push the resistance below zero.
    2. Percent reduction: multiplicative; skipped at zero or below.
    3. Percent penetration: multiplicative; skipped at zero or below.
    4. Flat penetration: subtracted, never below zero; skipped at zero or below.
    """
    initial = to_fraction(resistance, "resistance")
    if modifiers.is_empty:
        return ResistanceTrace(
            initial=initial,
            after_flat_reduction=initial,
            after_percent_reduction=initial,
            after_percent_penetration=initial,
            effective=initial,
        )
    after_flat_reduction = initial - sum(modifiers.flat_reduction, start=ZERO)

    after_percent_reduction = after_flat_reduction
    if after_flat_reduction > 0:  # pragma: no mutate
        after_percent_reduction *= _remaining(modifiers.percent_reduction)

    after_percent_penetration = after_percent_reduction
    if after_percent_reduction > 0:  # pragma: no mutate
        after_percent_penetration *= _remaining(modifiers.percent_penetration)

    effective = after_percent_penetration
    if after_percent_penetration > 0:  # pragma: no mutate
        effective = max(ZERO, effective - sum(modifiers.flat_penetration, start=ZERO))

    return ResistanceTrace(
        initial=initial,
        after_flat_reduction=after_flat_reduction,
        after_percent_reduction=after_percent_reduction,
        after_percent_penetration=after_percent_penetration,
        effective=effective,
    )


def damage_multiplier(resistance: Number) -> Fraction:
    """Return the factor applied to raw damage for an effective resistance."""
    value = to_fraction(resistance, "resistance")
    if value >= 0:  # pragma: no mutate
        return HUNDRED / (HUNDRED + value)
    return 2 - HUNDRED / (HUNDRED - value)


def _damage_type(value: DamageType | str) -> DamageType:
    try:
        return DamageType(value)
    except ValueError as exc:
        known = ", ".join(item.value for item in DamageType)
        raise DamageInputError(f"damage type: {value!r} is not one of {known}") from exc


def mitigate(
    raw_damage: Number,
    damage_type: DamageType | str,
    resistance: Number | None = None,
    modifiers: Modifiers = NO_MODIFIERS,
) -> DamageResult:
    """Return the post-mitigation damage of one damage instance.

    Physical and magic damage need the target's matching resistance (armor or
    magic resistance). True damage ignores resistances, so passing a resistance
    or modifiers with it is rejected as an inconsistent request.
    """
    kind = _damage_type(damage_type)
    raw = to_fraction(raw_damage, "raw damage")
    if raw < 0:
        raise DamageInputError(f"raw damage: {raw} is negative")

    if kind is DamageType.TRUE:
        if resistance is not None or not modifiers.is_empty:
            raise DamageInputError("true damage ignores resistance and its modifiers")
        return DamageResult(kind, raw, modifiers, None, ONE, raw)

    if resistance is None:
        raise DamageInputError(f"{kind.value} damage needs the target's resistance")
    trace = effective_resistance(resistance, modifiers)
    multiplier = damage_multiplier(trace.effective)
    return DamageResult(kind, raw, modifiers, trace, multiplier, raw * multiplier)
