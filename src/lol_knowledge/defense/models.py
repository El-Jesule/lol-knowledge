"""Core data models, constants, and incoming-hit parsers for reverse defense."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from fractions import Fraction

from ..damage import DamageType, format_number
from ..errors import RotationError
from ..rotation import RotationOutcome
from ..scenario import Target
from ..stats import Label
from ..summoners import SummonerSpellSpec
from ..survival import HealEvent, ShieldEvent

DEFENSE_RULES = (
    "lol-knowledge/mechanics/damage-mitigation.md",
    "lol-knowledge/mechanics/damage-modifiers.md",
    "lol-knowledge/mechanics/survival.md",
    "lol-knowledge/mechanics/runes.md",
)

_TOKEN_SPLIT = re.compile(r"[\s,]+")
_DAMAGE_KINDS = {
    "physical": DamageType.PHYSICAL,
    "magic": DamageType.MAGIC,
    "true": DamageType.TRUE,
    "attack": DamageType.PHYSICAL,
}


@dataclass(frozen=True)
class IncomingHit:
    """One incoming hit or wait interval in a reverse defense simulation."""

    # "attack", "crit", "physical", "magic", "true", "ability", "burn", "rune", "execute", "wait"
    kind: str
    damage_type: DamageType | None
    amount: Fraction
    source: str
    already_mitigated: bool = False
    resistances_already_live: bool = False
    time: Fraction | None = None
    wait: Fraction | None = None
    crit: bool = False
    label: Label = Label.OFFICIAL


def _positive_fraction(text: str, token: str) -> Fraction:
    try:
        value = Fraction(text)
    except (ValueError, ZeroDivisionError) as exc:
        raise RotationError(f"incoming token {token!r}: invalid number {text!r}") from exc
    if value <= 0:
        raise RotationError(f"incoming token {token!r}: amount must be positive")
    return value


def parse_incoming(text: str) -> list[IncomingHit]:
    """Parse manual incoming hits: ``attack:300, attack:crit:500, magic:250, true:100, wait:1``."""
    tokens = [tok for tok in _TOKEN_SPLIT.split(text.strip()) if tok]
    if not tokens:
        raise RotationError("incoming hit list is empty")
    hits: list[IncomingHit] = []
    for token in tokens:
        parts = token.lower().split(":")
        if parts[0] == "wait":
            if len(parts) != 2:
                raise RotationError(f"incoming token {token!r}: use wait:<seconds>")
            seconds = _positive_fraction(parts[1], token)
            hits.append(IncomingHit("wait", None, Fraction(0), token, wait=seconds))
            continue
        if parts[0] == "attack" and len(parts) == 3 and parts[1] == "crit":
            amount = _positive_fraction(parts[2], token)
            hits.append(
                IncomingHit(
                    "crit",
                    DamageType.PHYSICAL,
                    amount,
                    f"manual critical basic attack ({format_number(amount)} raw)",
                    crit=True,
                )
            )
            continue
        if parts[0] == "ability" and len(parts) == 3 and parts[1] in {"physical", "magic", "true"}:
            amount = _positive_fraction(parts[2], token)
            dtype = _DAMAGE_KINDS[parts[1]]
            hits.append(
                IncomingHit(
                    "ability",
                    dtype,
                    amount,
                    f"manual {parts[1]} ability ({format_number(amount)} raw)",
                )
            )
            continue
        if len(parts) == 2 and parts[0] in _DAMAGE_KINDS:
            kind = parts[0]
            dtype = _DAMAGE_KINDS[kind]
            amount = _positive_fraction(parts[1], token)
            label_kind = "basic attack" if kind == "attack" else f"{kind} hit"
            hits.append(
                IncomingHit(
                    kind,
                    dtype,
                    amount,
                    f"manual {label_kind} ({format_number(amount)} raw)",
                )
            )
            continue
        raise RotationError(
            f"unknown incoming token {token!r}: use attack:<n>, attack:crit:<n>, "
            "ability:<physical|magic|true>:<n>, physical:<n>, magic:<n>, true:<n> "
            "or wait:<seconds>"
        )
    return hits


def hits_from_rotation(outcome: RotationOutcome) -> list[IncomingHit]:
    """Convert an enemy champion's RotationOutcome into post-mitigation incoming hits."""
    hits: list[IncomingHit] = []
    for step in outcome.steps:
        if not step.parts and step.step.wait is not None:
            hits.append(
                IncomingHit(
                    "wait",
                    None,
                    Fraction(0),
                    step.step.text,
                    already_mitigated=True,
                    time=step.time,
                    wait=step.step.wait,
                )
            )
            continue
        for part in step.parts:
            kind = "crit" if (part.kind == "attack" and step.step.crit) else part.kind
            hits.append(
                IncomingHit(
                    kind,
                    part.damage_type,
                    part.primary_damage,
                    f"step {step.index} {step.step.text}: {part.source}",
                    already_mitigated=True,
                    time=step.time,
                    crit=step.step.crit and part.kind == "attack",
                    label=part.label,
                )
            )
    return hits


@dataclass(frozen=True)
class DefenseStep:
    index: int
    source: str
    kind: str
    damage_type: DamageType | None
    time: Fraction | None
    incoming: Fraction
    flat_reduced: Fraction
    damage_after_flat: Fraction
    shield_absorbed: Fraction
    health_damage: Fraction
    health_before: Fraction
    health_after: Fraction
    shield_before: Fraction
    shield_after: Fraction
    shields_granted: tuple[ShieldEvent, ...] = ()
    heals: tuple[HealEvent, ...] = ()
    reactive_damage: Fraction = Fraction(0)
    label: Label = Label.DERIVED
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class DefenseOutcome:
    defender_name: str
    defender_level: int
    patch: str
    enemy_description: str
    max_health: Fraction
    start_health: Fraction
    start_shield: Fraction
    shield_type: str
    steps: tuple[DefenseStep, ...]
    label: Label
    notes: tuple[str, ...]
    timeline: bool = False

    @property
    def total_incoming(self) -> Fraction:
        return sum((s.incoming for s in self.steps), start=Fraction(0))

    @property
    def total_flat_reduced(self) -> Fraction:
        return sum((s.flat_reduced for s in self.steps), start=Fraction(0))

    @property
    def total_damage_taken(self) -> Fraction:
        return sum((s.damage_after_flat for s in self.steps), start=Fraction(0))

    @property
    def total_shield_granted(self) -> Fraction:
        return sum((ev.amount for s in self.steps for ev in s.shields_granted), start=Fraction(0))

    @property
    def total_shield_absorbed(self) -> Fraction:
        return sum((s.shield_absorbed for s in self.steps), start=Fraction(0))

    @property
    def total_healing(self) -> Fraction:
        return sum((ev.amount for s in self.steps for ev in s.heals), start=Fraction(0))

    @property
    def total_reactive_damage(self) -> Fraction:
        return sum((s.reactive_damage for s in self.steps), start=Fraction(0))

    @property
    def remaining_health(self) -> Fraction:
        return self.steps[-1].health_after if self.steps else self.start_health

    @property
    def remaining_shield(self) -> Fraction:
        return self.steps[-1].shield_after if self.steps else self.start_shield

    @property
    def survived(self) -> bool:
        return self.remaining_health > 0

    @property
    def lethal_step(self) -> int | None:
        for step in self.steps:
            if step.health_after == 0:
                return step.index
        return None

    @property
    def time_to_die(self) -> Fraction | None:
        if not self.timeline:
            return None
        for step in self.steps:
            if step.health_after == 0:
                return step.time
        return None

    @property
    def duration(self) -> Fraction | None:
        if not self.timeline or not self.steps:
            return None
        times = [s.time for s in self.steps if s.time is not None]
        return times[-1] if times else None

    @property
    def damage_taken_per_second(self) -> Fraction | None:
        dur = self.duration
        if not dur:
            return None
        return self.total_damage_taken / dur


@dataclass
class _ActiveShield:
    source: str
    remaining: Fraction
    shield_type: str
    expires_at: Fraction | None


@dataclass
class _StaggerBleed:
    source: str
    end: Fraction
    rate: Fraction  # true damage per second
    label: Label


@dataclass
class _CCLock:
    kind: str
    end: Fraction
    source: str
    cleansable_by_cleanse: bool
    cleansable_by_qss: bool
    label: Label


TENACITY_MIN_DURATION = Fraction(3, 10)  # 0.3 s minimum floor (tenacity.md)


@dataclass(frozen=True)
class DefenseState:
    """Live snapshot of a defender's vital state during coupled duel simulation."""

    health: Fraction
    max_health: Fraction
    shield: Fraction
    clock: Fraction
    stasis_until: Fraction | None
    grievous_active: bool
    step_count: int
    attacks_locked_until: Fraction | None = None
    abilities_locked_until: Fraction | None = None
    suppressed_until: Fraction | None = None
    blinded_until: Fraction | None = None


@dataclass
class DefenseSession:
    """Incremental defensive simulation handle shared by ``survive`` and ``duel``."""

    snapshot_state: Callable[[], DefenseState]
    effective_resists: Callable[[Fraction], tuple[Fraction, Fraction, list[Label], list[str]]]
    target_snapshot: Callable[[Fraction], Target]
    accrue_to: Callable[
        [Fraction], tuple[list[HealEvent], Fraction, list[Label], list[str], Fraction | None]
    ]
    process_hit: Callable[..., DefenseStep]
    activate_ability_cast: Callable[
        [str, int, str | None, Fraction],
        tuple[list[ShieldEvent], list[HealEvent], list[Label], list[str]],
    ]
    activate_summoner: Callable[
        [SummonerSpellSpec, Fraction],
        tuple[list[ShieldEvent], list[HealEvent], list[Label], list[str]],
    ]
    apply_self_survival: Callable[
        [Sequence[HealEvent], Sequence[ShieldEvent], Fraction],
        tuple[Fraction, Fraction, list[HealEvent], list[ShieldEvent]],
    ]
    apply_health_cost: Callable[[Fraction], Fraction]
    set_grievous_until: Callable[[Fraction], None]
    set_shield_reaver: Callable[[Fraction, Fraction], None]
    apply_cc: Callable[..., tuple[Fraction, list[HealEvent], list[Label], list[str]]]
    cleanse_cc: Callable[..., list[str]]
    next_event_time: Callable[[Fraction, Fraction], Fraction | None]
    flush_tail: Callable[[], None]
    outcome: Callable[[str], DefenseOutcome]
