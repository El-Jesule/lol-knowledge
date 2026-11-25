"""Ability resource costs and rotation resource tracking (lol-knowledge/mechanics/resources.md).

Pure functions and stateful rotation helper over already-loaded champion, kit and
stat-sheet data. Supports mana, energy and health costs, passive regeneration in
timeline rotations, Manaflow Band missing-mana ticks, Essence Reaver refunds and
Presence of Mind restores.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from .damage import format_number
from .errors import RotationError, StatsError
from .formula import ABILITY_OPS, FormulaError, evaluate_formula
from .kit import CostSpec, Kit
from .runes import fraction_input
from .stats import Label, ResourcePool, StatSheet, champion_resource, weakest

RESOURCES_RULES = "lol-knowledge/mechanics/resources.md"
HEALTH_COST_KEYWORDS = ("vida", "health")


@dataclass(frozen=True)
class StepResourceCost:
    """Resolved resource cost of one ability step."""

    resource: str  # "mana", "energy", "health" or "none"
    amount: Fraction
    label: Label
    source: str
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResourceEvent:
    """One resource change during a step: cost, restore or passive regeneration."""

    source: str
    resource: str  # "mana", "energy" or "health"
    kind: str  # "cost", "restore" or "regen"
    raw: Fraction
    effective: Fraction
    label: Label
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResourceSummary:
    """End-of-rotation resource accounting."""

    kind: str  # "mana", "energy", "none" or "other"
    name: str
    maximum: Fraction
    start: Fraction
    spent: Fraction
    restored: Fraction
    effective_restored: Fraction
    regenerated: Fraction
    remaining: Fraction
    health_cost_spent: Fraction
    insufficient_steps: tuple[int, ...]
    uses_casting_pool: bool
    label: Label
    notes: tuple[str, ...] = ()


def _eval_cost_spec(
    spec: CostSpec,
    stats: Mapping[str, Fraction],
    origin: Mapping[str, tuple[str, Label]],
    *,
    rank: int,
    level: int,
    inputs: Mapping[str, Any],
    context: str,
) -> StepResourceCost:
    try:
        result = evaluate_formula(
            spec.formula,
            stats,
            rank=rank,
            level=level,
            inputs=inputs,
            ops=ABILITY_OPS,
        )
    except FormulaError as exc:
        raise RotationError(f"{context} cost: {exc}") from exc
    assert result.exact is not None
    if result.exact < 0:
        raise RotationError(f"{context} cost: evaluated to negative value {result.exact}")
    labels = [spec.label, *(origin[k][1] for k in result.dependencies if k in origin)]
    return StepResourceCost(spec.resource, result.exact, weakest(labels), spec.source)


def resolve_ability_cost(
    kit: Kit,
    sheet: StatSheet,
    slot: str,
    rank: int,
    case_id: str | None,
    stats: Mapping[str, Fraction],
    origin: Mapping[str, tuple[str, Label]],
    inputs: Mapping[str, Any],
    *,
    attacker_hp: Fraction | None = None,
    attacker_max_hp: Fraction | None = None,
) -> StepResourceCost:
    """Resolve the resource cost of an ability step.

    Precedence:
    1. Explicit ``case.cost`` declared in the champion kit.
    2. Recast cases (``case.recast is True``) cost 0 extra resource.
    3. Explicit ``ability.cost`` declared in the champion kit.
    4. Official Data Dragon ``spells[slot].cost[rank - 1]``.
    """
    ability = kit.ability(slot)
    case = (
        ability.case(case_id)
        if case_id is not None
        else (ability.cases[0] if ability.cases else None)
    )
    eval_stats = dict(stats)
    if attacker_max_hp is not None:
        eval_stats["max_health"] = attacker_max_hp
        eval_stats["current_health"] = attacker_max_hp if attacker_hp is None else attacker_hp
    elif "health" in eval_stats:
        eval_stats.setdefault("max_health", eval_stats["health"])
        eval_stats.setdefault("current_health", eval_stats["health"])

    if case is not None and case.cost is not None:
        return _eval_cost_spec(
            case.cost,
            eval_stats,
            origin,
            rank=rank,
            level=sheet.level,
            inputs=inputs,
            context=f"{slot}.{case.id}",
        )
    if case is not None and case.recast:
        return StepResourceCost(
            "none",
            Fraction(0),
            Label.DERIVED,
            f"kit:{kit.champion} {slot}.{case.id} recast (no extra resource cost)",
        )
    if ability.cost is not None:
        return _eval_cost_spec(
            ability.cost,
            eval_stats,
            origin,
            rank=rank,
            level=sheet.level,
            inputs=inputs,
            context=slot,
        )

    spell = next((item for item in sheet.champion.spells if item.slot == slot), None)
    source = (
        f"data:champion:{sheet.champion.id} spells.{slot}.cost[{rank}] ({sheet.champion.patch})"
    )
    if spell is None or len(spell.costs) < rank:
        return StepResourceCost("none", Fraction(0), Label.OFFICIAL, source)
    raw = spell.costs[rank - 1]
    if raw > 0:
        pool = champion_resource(sheet)
        kind = pool.kind if pool.kind in {"mana", "energy"} else "none"
        return StepResourceCost(kind, raw, Label.OFFICIAL, source)
    cost_type_lower = spell.cost_type.lower()
    if any(keyword in cost_type_lower for keyword in HEALTH_COST_KEYWORDS):
        return StepResourceCost(
            "none",
            Fraction(0),
            Label.PENDING,
            source,
            (
                f"{slot}: Data Dragon costType {spell.cost_type!r} indicates a health cost, "
                "but the kit declares no cost formula",
            ),
        )
    return StepResourceCost("none", Fraction(0), Label.OFFICIAL, source)


class ResourceTracker:
    """Mutable resource pool state across the steps of a single rotation."""

    def __init__(
        self,
        sheet: StatSheet,
        inputs: Mapping[str, Fraction],
        *,
        start_resource: Fraction | None = None,
        timeline: bool = False,
        allow_insufficient: bool = False,
        manaflow_regen: tuple[Fraction, Fraction, Label, str] | None = None,
    ) -> None:
        self.pool: ResourcePool = champion_resource(sheet)
        self.timeline = timeline
        self.allow_insufficient = allow_insufficient
        self.manaflow_regen = manaflow_regen if self.pool.kind == "mana" else None
        self.notes: list[str] = list(self.pool.notes)
        self.labels: list[Label] = [self.pool.label]
        self.weakened = False

        try:
            pct = fraction_input(inputs, "attacker_resource_percent")
        except StatsError as exc:
            raise RotationError(str(exc)) from exc
        if start_resource is not None and pct is not None:
            raise RotationError(
                "give either --attacker-resource or --input attacker_resource_percent, not both"
            )
        if not self.pool.uses_casting_pool:
            if start_resource is not None or pct is not None:
                raise RotationError(
                    f"{sheet.champion.id} uses {self.pool.name!r}, which has no casting "
                    "resource pool to set"
                )
            self.maximum = self.pool.maximum or Fraction(0)
            self.start = Fraction(0)
            self.current = Fraction(0)
            self.regen_per_second = Fraction(0)
        else:
            if self.pool.blocked is not None or self.pool.maximum is None:
                raise RotationError(f"resource pool is blocked: {self.pool.blocked}")
            self.maximum = self.pool.maximum
            self.regen_per_second = self.pool.regen_per_second or Fraction(0)
            if start_resource is not None:
                if start_resource < 0 or start_resource > self.maximum:
                    raise RotationError(
                        f"--attacker-resource must be between 0 and {format_number(self.maximum)} "
                        f"{self.pool.name}, got {format_number(start_resource)}"
                    )
                self.start = start_resource
            elif pct is not None:
                self.start = self.maximum * pct
            else:
                self.start = self.maximum
            self.current = self.start

        self.spent = Fraction(0)
        self.restored = Fraction(0)
        self.effective_restored = Fraction(0)
        self.regenerated = Fraction(0)
        self.health_cost_spent = Fraction(0)
        self.insufficient_steps: list[int] = []
        self._clock = Fraction(0)
        self._next_manaflow = (
            self.manaflow_regen[1] if (self.timeline and self.manaflow_regen is not None) else None
        )

    @property
    def uses_casting_pool(self) -> bool:
        return self.pool.uses_casting_pool

    def _add_passive_regen(self, dt: Fraction) -> Fraction:
        if dt <= 0 or self.regen_per_second <= 0 or not self.uses_casting_pool:
            return Fraction(0)
        missing = max(Fraction(0), self.maximum - self.current)
        if missing <= 0:
            return Fraction(0)
        gained = min(self.regen_per_second * dt, missing)
        self.current += gained
        self.regenerated += gained
        return gained

    def accrue_regen(self, until: Fraction) -> list[ResourceEvent]:
        """Accrue passive resource regen (and Manaflow Band 5 s ticks) up to ``until``."""
        if not self.timeline or not self.uses_casting_pool or until <= self._clock:
            return []
        events: list[ResourceEvent] = []
        cursor = self._clock
        passive_total = Fraction(0)
        while (
            self.manaflow_regen is not None
            and self._next_manaflow is not None
            and self._next_manaflow <= until
        ):
            tick = self._next_manaflow
            passive_total += self._add_passive_regen(tick - cursor)
            cursor = tick
            pct, interval, mf_label, mf_source = self.manaflow_regen
            missing = max(Fraction(0), self.maximum - self.current)
            if missing > 0:
                gain = min(missing * pct, missing)
                self.current += gain
                self.regenerated += gain
                self.labels.append(mf_label)
                events.append(
                    ResourceEvent(
                        f"{mf_source} at {format_number(tick)} s",
                        "mana",
                        "regen",
                        gain,
                        gain,
                        mf_label,
                        (f"{format_number(pct * 100)}% of missing mana every {interval} s",),
                    )
                )
            self._next_manaflow = tick + interval
        passive_total += self._add_passive_regen(until - cursor)
        if passive_total > 0:
            events.insert(
                0,
                ResourceEvent(
                    f"passive {self.pool.kind} regeneration ({format_number(self._clock)} s -> "
                    f"{format_number(until)} s)",
                    self.pool.kind,
                    "regen",
                    self.regen_per_second * (until - self._clock),
                    passive_total,
                    self.pool.label,
                ),
            )
        self._clock = until
        return events

    def spend_pool(
        self, step_index: int, step_text: str, cost: StepResourceCost
    ) -> tuple[ResourceEvent | None, bool]:
        """Deduct a mana or energy cost; return ``(event, was_insufficient)``."""
        if cost.notes:
            self.notes.extend(cost.notes)
        if cost.label is Label.PENDING:
            self.labels.append(Label.PENDING)
            self.weakened = True
        if cost.amount <= 0 or cost.resource not in {"mana", "energy"}:
            return None, False
        if not self.uses_casting_pool or cost.resource != self.pool.kind:
            raise RotationError(
                f"step {step_text}: ability costs {cost.resource}, but champion uses "
                f"{self.pool.name!r}"
            )
        self.labels.append(cost.label)
        if self.current < cost.amount:
            if not self.allow_insufficient:
                raise RotationError(
                    f"step {step_text}: needs {format_number(cost.amount)} {self.pool.name}, "
                    f"only {format_number(self.current)} available "
                    "(--allow-insufficient-resource calculates it anyway)"
                )
            self.insufficient_steps.append(step_index)
            self.labels.append(Label.PENDING)
            self.weakened = True
            available = self.current
            self.current = Fraction(0)
            self.spent += cost.amount
            note = (
                f"insufficient {self.pool.name}: needed {format_number(cost.amount)}, "
                f"only {format_number(available)} available (clamped to 0)"
            )
            self.notes.append(f"step {step_index} {step_text}: {note}")
            return (
                ResourceEvent(
                    cost.source,
                    cost.resource,
                    "cost",
                    cost.amount,
                    available,
                    Label.PENDING,
                    (*cost.notes, note),
                ),
                True,
            )
        self.current -= cost.amount
        self.spent += cost.amount
        return (
            ResourceEvent(
                cost.source,
                cost.resource,
                "cost",
                cost.amount,
                cost.amount,
                cost.label,
                cost.notes,
            ),
            False,
        )

    def spend_health(
        self, attacker_hp: Fraction, cost: StepResourceCost
    ) -> tuple[Fraction, ResourceEvent]:
        """Deduct a health cost; health costs never kill the caster (leaves >= 1 HP)."""
        self.labels.append(weakest((cost.label, Label.DERIVED)))
        if cost.notes:
            self.notes.extend(cost.notes)
        if cost.amount <= 0:
            return attacker_hp, ResourceEvent(
                cost.source, "health", "cost", Fraction(0), Fraction(0), cost.label, cost.notes
            )
        floor = Fraction(1) if attacker_hp > 1 else attacker_hp
        new_hp = max(floor, attacker_hp - cost.amount)
        actual = attacker_hp - new_hp
        self.health_cost_spent += actual
        notes = list(cost.notes)
        if actual < cost.amount:
            notes.append("health cost cannot kill the caster (clamped to 1 HP)")
        return new_hp, ResourceEvent(
            cost.source,
            "health",
            "cost",
            cost.amount,
            actual,
            weakest((cost.label, Label.DERIVED)),
            tuple(notes),
        )

    def restore(
        self,
        source: str,
        resource: str,
        raw: Fraction,
        label: Label,
        notes: tuple[str, ...] = (),
    ) -> ResourceEvent | None:
        """Apply a mana or energy restore capped at the pool maximum."""
        if raw <= 0 or not self.uses_casting_pool or resource != self.pool.kind:
            return None
        missing = max(Fraction(0), self.maximum - self.current)
        effective = min(raw, missing)
        self.current += effective
        self.restored += raw
        self.effective_restored += effective
        self.labels.append(label)
        return ResourceEvent(source, resource, "restore", raw, effective, label, notes)

    def summary(self) -> ResourceSummary:
        return ResourceSummary(
            kind=self.pool.kind,
            name=self.pool.name,
            maximum=self.maximum,
            start=self.start,
            spent=self.spent,
            restored=self.restored,
            effective_restored=self.effective_restored,
            regenerated=self.regenerated,
            remaining=self.current,
            health_cost_spent=self.health_cost_spent,
            insufficient_steps=tuple(self.insufficient_steps),
            uses_casting_pool=self.uses_casting_pool,
            label=weakest(self.labels),
            notes=tuple(dict.fromkeys(self.notes)),
        )
