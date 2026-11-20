"""Champion passive effects on the stat sheet and in combat rotations (CH-03).

Pure functions and stateful rotation helper over declarative ``PassiveEffectSpec``
entries in ``lol-knowledge/champions/<Id>/kit.json``. No champion names are
hardcoded here: every rule is read from the kit.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction

from .damage import DamageType, format_number
from .errors import RotationError, StatsError
from .formula import ABILITY_OPS, FormulaError, evaluate_formula
from .kit import Kit, PassiveEffectSpec, sheet_stats
from .runes import int_input
from .scenario import Target
from .stats import (
    Contribution,
    Label,
    StatAmplifier,
    StatSheet,
    effect_amount,
    weakest,
)
from .survival import HealEvent

PASSIVES_RULES = "lol-knowledge/mechanics/passives.md"


@dataclass(frozen=True)
class PassiveSheetEffects:
    """Stat-sheet contributions and informational notes from a champion's passive."""

    flats: tuple[tuple[str, Contribution], ...] = ()
    amplifiers: tuple[StatAmplifier, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class PassiveStatBonus:
    stat_id: str
    amount: Fraction
    source: str
    label: Label
    note: str = ""


@dataclass(frozen=True)
class PassiveStatAmplifier:
    stat_id: str
    percent: Fraction
    source: str
    label: Label


@dataclass(frozen=True)
class PassiveProc:
    source: str
    damage_type: DamageType
    raw: Fraction
    label: Label
    notes: tuple[str, ...] = ()


def _passive_specs(kit: Kit | None) -> tuple[PassiveEffectSpec, ...]:
    if kit is None or "P" not in kit.abilities:
        return ()
    return kit.abilities["P"].passive_effects


def sheet_passive_effects(
    kit: Kit | None,
    level: int,
    inputs: Mapping[str, Fraction] | None = None,
    *,
    include_stacking: bool = True,
) -> PassiveSheetEffects:
    """Evaluate champion passive effects applicable to the stat sheet.

    In ``stats`` and ``ability`` (``include_stacking=True``), a ``stacking_stat``
    passive with ``input_name`` can be inspected at an explicit stack count via
    ``--input <input_name>=<0..max_stacks>``. In ``rotation``
    (``include_stacking=False``), ``PassiveCombat`` manages those stacks step by step.
    """
    specs = _passive_specs(kit)
    if not specs:
        return PassiveSheetEffects()
    assert kit is not None
    scenario = inputs or {}
    flats: list[tuple[str, Contribution]] = []
    amplifiers: list[StatAmplifier] = []
    notes: list[str] = []

    for effect in specs:
        source = f"kit:{kit.champion} P {effect.id} ({effect.source})"
        if effect.kind == "stat_bonus":
            assert effect.stat is not None
            stacks = 1
            note = effect.condition
            if effect.input_name is not None:
                given = int_input(scenario, effect.input_name, minimum=0, maximum=effect.max_stacks)
                if given is None:
                    bound = f"0..{effect.max_stacks}" if effect.max_stacks is not None else ">=0"
                    notes.append(
                        f"passive P {effect.name}: pass --input {effect.input_name}=<{bound}> "
                        "to include in stats"
                    )
                    continue
                stacks = given
                note = f"scenario: {effect.input_name}={stacks}"
            if stacks == 0:
                notes.append(f"passive P {effect.name}: 0 stacks ({effect.input_name}=0)")
                continue
            try:
                per_unit = evaluate_formula(
                    effect.formula, {}, level=level, inputs=scenario, ops=ABILITY_OPS
                ).exact
            except FormulaError as exc:
                raise StatsError(f"passive P.{effect.id}: {exc}") from exc
            assert per_unit is not None
            total = per_unit * stacks
            if effect.mode == "percent":
                amplifiers.append(StatAmplifier(effect.stat, total, source, effect.label, note))
            else:
                flats.append(
                    (
                        effect.stat,
                        Contribution(
                            effect_amount(effect.stat, total), "bonus", source, effect.label, note
                        ),
                    )
                )
            continue

        if effect.kind == "stacking_stat":
            if not include_stacking:
                continue
            assert effect.stat is not None and effect.max_stacks is not None
            if effect.input_name is None:
                notes.append(f"passive P {effect.name}: combat stacking (applied in rotation)")
                continue
            given = int_input(scenario, effect.input_name, minimum=0, maximum=effect.max_stacks)
            if given is None:
                notes.append(
                    f"passive P {effect.name}: combat stacking (pass --input "
                    f"{effect.input_name}=0..{effect.max_stacks} to include in stats)"
                )
                continue
            if given == 0:
                notes.append(f"passive P {effect.name}: 0 stacks ({effect.input_name}=0)")
                continue
            try:
                per_stack = evaluate_formula(
                    effect.formula, {}, level=level, inputs=scenario, ops=ABILITY_OPS
                ).exact
            except FormulaError as exc:
                raise StatsError(f"passive P.{effect.id}: {exc}") from exc
            assert per_stack is not None
            mult = effect.max_stacks_multiplier if given == effect.max_stacks else Fraction(1)
            total = per_stack * given * mult
            note = f"scenario: {effect.input_name}={given}"
            if mult != 1:
                note += f" (max stacks x{format_number(mult)})"
            if effect.mode == "percent":
                amplifiers.append(StatAmplifier(effect.stat, total, source, effect.label, note))
            else:
                flats.append(
                    (
                        effect.stat,
                        Contribution(
                            effect_amount(effect.stat, total), "bonus", source, effect.label, note
                        ),
                    )
                )
            continue

        notes.append(f"passive P {effect.name}: combat effect (applied in rotation)")

    return PassiveSheetEffects(tuple(flats), tuple(amplifiers), tuple(notes))


class PassiveCombat:
    """Combat passive state for one rotation (stacking stats, procs and heals)."""

    def __init__(
        self,
        kit: Kit,
        target: Target,
        inputs: Mapping[str, Fraction],
        *,
        timeline: bool,
        enabled: bool = True,
    ) -> None:
        self.kit = kit
        self.target = target
        self.inputs = inputs
        self.timeline = timeline
        self.enabled = enabled
        self.notes: list[str] = []
        self._stacking: list[PassiveEffectSpec] = []
        self._heals: list[PassiveEffectSpec] = []
        self._procs: list[PassiveEffectSpec] = []
        self._stacks: dict[str, int] = {}
        self._stacked_at: dict[str, Fraction] = {}
        self._attack_counts: dict[str, int] = {}
        self._heal_stacks: dict[str, int] = {}
        self._ready: dict[str, Fraction] = {}
        self._fired: set[str] = set()
        self._noted_target_kind: set[str] = set()

        if not enabled:
            return
        for effect in _passive_specs(kit):
            if effect.kind == "stacking_stat":
                self._stacking.append(effect)
                initial = 0
                if effect.input_name is not None:
                    try:
                        given = int_input(
                            inputs, effect.input_name, minimum=0, maximum=effect.max_stacks
                        )
                    except StatsError as exc:
                        raise RotationError(str(exc)) from exc
                    if given is not None:
                        initial = given
                self._stacks[effect.id] = initial
                if initial > 0:
                    self._stacked_at[effect.id] = Fraction(0)
            elif effect.kind == "heal":
                self._heals.append(effect)
                if effect.stacks_required is not None:
                    initial = 0
                    if effect.input_name is not None:
                        try:
                            given = int_input(
                                inputs,
                                effect.input_name,
                                minimum=0,
                                maximum=effect.stacks_required - 1,
                            )
                        except StatsError as exc:
                            raise RotationError(str(exc)) from exc
                        if given is not None:
                            initial = given
                    self._heal_stacks[effect.id] = initial
            elif effect.kind == "damage_proc":
                self._procs.append(effect)
                self._attack_counts[effect.id] = 0

    def _expired(self, effect: PassiveEffectSpec, at: Fraction) -> bool:
        if not self.timeline or effect.duration_seconds is None:
            return False
        last = self._stacked_at.get(effect.id)
        return last is not None and at - last >= effect.duration_seconds

    def stack_expiry_times(self, start: Fraction, until: Fraction) -> list[Fraction]:
        if not self.timeline:
            return []
        times: list[Fraction] = []
        for effect in self._stacking:
            if effect.duration_seconds is None or effect.id not in self._stacked_at:
                continue
            end = self._stacked_at[effect.id] + effect.duration_seconds
            if start < end < until:
                times.append(end)
        return times

    def active_stat_modifiers(
        self, at: Fraction, level: int
    ) -> tuple[list[PassiveStatBonus], list[PassiveStatAmplifier]]:
        """Flat bonuses and total-stat amplifiers currently in force from passives."""
        flats: list[PassiveStatBonus] = []
        amplifiers: list[PassiveStatAmplifier] = []
        for effect in self._stacking:
            count = self._stacks.get(effect.id, 0)
            if count <= 0 or self._expired(effect, at):
                continue
            assert effect.stat is not None and effect.max_stacks is not None
            try:
                per_stack = evaluate_formula(
                    effect.formula, {}, level=level, inputs=self.inputs, ops=ABILITY_OPS
                ).exact
            except FormulaError as exc:
                raise RotationError(f"passive P.{effect.id}: {exc}") from exc
            assert per_stack is not None
            mult = effect.max_stacks_multiplier if count == effect.max_stacks else Fraction(1)
            total = per_stack * count * mult
            source = f"kit:{self.kit.champion} P {effect.id} ({count}/{effect.max_stacks} stacks)"
            if effect.mode == "percent":
                amplifiers.append(PassiveStatAmplifier(effect.stat, total, source, effect.label))
            else:
                note = f"{count} stack{'' if count == 1 else 's'}"
                if mult != 1:
                    note += f" (max stacks x{format_number(mult)})"
                flats.append(
                    PassiveStatBonus(
                        effect.stat,
                        effect_amount(effect.stat, total),
                        source,
                        effect.label,
                        note,
                    )
                )
        return flats, amplifiers

    def _can_fire(self, effect: PassiveEffectSpec, clock: Fraction) -> bool:
        if effect.cooldown_seconds is None:
            return True
        if not self.timeline:
            return effect.id not in self._fired
        return clock >= self._ready.get(effect.id, Fraction(0))

    def _mark_fired(self, effect: PassiveEffectSpec, clock: Fraction) -> None:
        self._fired.add(effect.id)
        if self.timeline and effect.cooldown_seconds is not None:
            self._ready[effect.id] = clock + effect.cooldown_seconds

    def on_step(
        self, slot: str | None, dealt_damage: bool, clock: Fraction, sheet: StatSheet
    ) -> list[PassiveProc]:
        """Fire damage procs for this step and advance stacking passive counters."""
        procs: list[PassiveProc] = []
        stats, origin = sheet_stats(sheet)

        for effect in self._procs:
            triggered = False
            if effect.trigger in {"on_attack", "on_hit"} and slot is None:
                triggered = True
            elif effect.trigger == "every_n_attacks" and slot is None:
                assert effect.every is not None
                self._attack_counts[effect.id] += 1
                if self._attack_counts[effect.id] >= effect.every:
                    self._attack_counts[effect.id] = 0
                    triggered = True
            if not triggered or not self._can_fire(effect, clock):
                continue
            self._mark_fired(effect, clock)
            try:
                res = evaluate_formula(
                    effect.formula,
                    stats,
                    level=sheet.level,
                    inputs=self.inputs,
                    ops=ABILITY_OPS,
                )
            except FormulaError as exc:
                raise RotationError(f"passive P.{effect.id}: {exc}") from exc
            assert res.exact is not None and effect.damage_type is not None
            labels = [effect.label, *(origin[k][1] for k in res.dependencies if k in origin)]
            procs.append(
                PassiveProc(
                    f"kit:{self.kit.champion} P {effect.id} ({effect.name})",
                    effect.damage_type,
                    res.exact,
                    weakest(labels),
                )
            )

        for effect in self._stacking:
            assert effect.max_stacks is not None
            if effect.trigger == "champion_hit":
                if not dealt_damage:
                    continue
                if self.target.kind is None:
                    if effect.id not in self._noted_target_kind:
                        self._noted_target_kind.add(effect.id)
                        self.notes.append(
                            f"passive P {effect.name}: only stacks against champions "
                            "(give --target-kind champion to stack it)"
                        )
                    continue
                if self.target.kind != "champion":
                    continue
            elif effect.trigger == "attack":
                if slot is not None:
                    continue
            elif effect.trigger == "ability_hit":
                if slot is None or not dealt_damage:
                    continue
            elif effect.trigger == "any_hit":
                if not dealt_damage:
                    continue
            if self._expired(effect, clock):
                self._stacks[effect.id] = 0
            self._stacks[effect.id] = min(effect.max_stacks, self._stacks[effect.id] + 1)
            self._stacked_at[effect.id] = clock

        return procs

    def on_step_heals(
        self,
        slot: str | None,
        dealt_damage: bool,
        killed_target: bool,
        clock: Fraction,
        sheet: StatSheet,
    ) -> list[HealEvent]:
        """Direct heal events triggered by the champion's passive on this step."""
        if not self._heals:
            return []
        stats, origin = sheet_stats(sheet)
        heals: list[HealEvent] = []

        for effect in self._heals:
            triggered = False
            notes: list[str] = []
            if effect.trigger == "on_champion_takedown":
                if killed_target and self.target.kind == "champion":
                    triggered = True
                    notes.append("on champion takedown")
            elif effect.trigger == "on_minion_monster_kill":
                if killed_target and self.target.kind in {"minion", "monster"}:
                    if effect.stacks_required is None:
                        triggered = True
                    else:
                        self._heal_stacks[effect.id] += 1
                        if self._heal_stacks[effect.id] >= effect.stacks_required:
                            self._heal_stacks[effect.id] = 0
                            triggered = True
                            notes.append(f"consumed {effect.stacks_required} stacks on kill")
            elif dealt_damage and (
                (effect.trigger == "on_hit" and slot is None)
                or (effect.trigger == "on_ability_hit" and slot is not None)
            ):
                triggered = True

            if not triggered or not self._can_fire(effect, clock):
                continue
            self._mark_fired(effect, clock)
            try:
                res = evaluate_formula(
                    effect.formula,
                    stats,
                    level=sheet.level,
                    inputs=self.inputs,
                    ops=ABILITY_OPS,
                )
            except FormulaError as exc:
                raise RotationError(f"passive P.{effect.id}: {exc}") from exc
            assert res.exact is not None
            labels = [effect.label, *(origin[k][1] for k in res.dependencies if k in origin)]
            heals.append(
                HealEvent(
                    f"kit:{self.kit.champion} P {effect.id} ({effect.name})",
                    res.exact,
                    res.exact,
                    True,
                    False,
                    weakest(labels),
                    tuple(notes),
                )
            )
        return heals
