"""Champion passive effects on the stat sheet, in rotations, and in defense (CH-03).

Pure functions and stateful rotation helper over declarative ``PassiveEffectSpec``
entries in ``lol-knowledge/champions/<Id>/kit.json``. No champion names are
hardcoded here: every rule is read from the kit.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from .damage import DamageType, format_number
from .errors import RotationError, StatsError
from .formula import ABILITY_OPS, FormulaError, evaluate_formula
from .kit import Kit, PassiveEffectSpec
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
from .survival import HealEvent, ShieldEvent

PASSIVES_RULES = "lol-knowledge/mechanics/passives.md"


@dataclass(frozen=True)
class PassiveSheetEffects:
    """Stat-sheet contributions and informational notes from a champion's passive."""

    flats: tuple[tuple[str, Contribution], ...] = ()
    amplifiers: tuple[StatAmplifier, ...] = ()
    notes: tuple[str, ...] = ()
    percents: tuple[tuple[str, Contribution], ...] = ()


@dataclass(frozen=True)
class PassiveStatBonus:
    stat_id: str
    amount: Fraction
    source: str
    label: Label
    note: str = ""
    percent: bool = False


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


@dataclass(frozen=True)
class PassiveResourceRestore:
    source: str
    resource: str
    amount: Fraction
    label: Label
    notes: tuple[str, ...] = ()


def _passive_specs(kit: Kit | None) -> tuple[PassiveEffectSpec, ...]:
    if kit is None or "P" not in kit.abilities:
        return ()
    return kit.abilities["P"].passive_effects


def passive_defense_specs(
    kit: Kit | None,
) -> tuple[list[PassiveEffectSpec], list[PassiveEffectSpec]]:
    """Return ``(damage_taken_modifiers, shield_effects)`` declared in ``kit.P``."""
    specs = _passive_specs(kit)
    dr = [e for e in specs if e.kind == "damage_taken_modifier"]
    shields = [e for e in specs if e.kind == "shield"]
    return dr, shields


def _formula_uses_input(node: Any, name: str) -> bool:
    if isinstance(node, Mapping):
        if node.get("op") == "input" and node.get("name") == name:
            return True
        return any(_formula_uses_input(v, name) for v in node.values())
    if isinstance(node, list):
        return any(_formula_uses_input(item, name) for item in node)
    return False


def _effect_cooldown(effect: PassiveEffectSpec, level: int) -> Fraction | None:
    if effect.cooldown_formula is not None:
        try:
            val = evaluate_formula(effect.cooldown_formula, {}, level=level, ops=ABILITY_OPS).exact
        except FormulaError as exc:
            raise RotationError(f"passive P.{effect.id}.cooldown_formula: {exc}") from exc
        assert val is not None
        return val
    return effect.cooldown_seconds


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
    percents: list[tuple[str, Contribution]] = []
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
            uses_self_input = effect.input_name is not None and _formula_uses_input(
                effect.formula, effect.input_name
            )
            total = per_unit if uses_self_input else per_unit * stacks
            if total == 0:
                continue
            if effect.mode == "percent":
                amplifiers.append(StatAmplifier(effect.stat, total, source, effect.label, note))
            elif effect.mode == "percent_ms":
                percents.append(
                    (
                        effect.stat,
                        Contribution(total, "bonus", source, effect.label, note),
                    )
                )
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
            if effect.only_at_max and given < effect.max_stacks:
                notes.append(
                    f"passive P {effect.name}: inactive below {effect.max_stacks} stacks "
                    f"({effect.input_name}={given})"
                )
                continue
            try:
                per_stack = evaluate_formula(
                    effect.formula, {}, level=level, inputs=scenario, ops=ABILITY_OPS
                ).exact
            except FormulaError as exc:
                raise StatsError(f"passive P.{effect.id}: {exc}") from exc
            assert per_stack is not None
            mult = effect.max_stacks_multiplier if given == effect.max_stacks else Fraction(1)
            total = per_stack * mult if effect.only_at_max else per_stack * given * mult
            note = f"scenario: {effect.input_name}={given}"
            if mult != 1:
                note += f" (max stacks x{format_number(mult)})"
            if effect.mode == "percent":
                amplifiers.append(StatAmplifier(effect.stat, total, source, effect.label, note))
            elif effect.mode == "percent_ms":
                percents.append(
                    (
                        effect.stat,
                        Contribution(total, "bonus", source, effect.label, note),
                    )
                )
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

        if effect.kind == "damage_taken_modifier":
            notes.append(f"passive P {effect.name}: defensive effect (applied in survive/target)")
        elif effect.kind == "shield":
            notes.append(f"passive P {effect.name}: shield effect (applied in rotation/survive)")
        elif effect.kind == "resource_restore":
            notes.append(f"passive P {effect.name}: resource restore (applied in rotation)")
        else:
            notes.append(f"passive P {effect.name}: combat effect (applied in rotation)")

    return PassiveSheetEffects(tuple(flats), tuple(amplifiers), tuple(notes), tuple(percents))


class PassiveCombat:
    """Combat passive state for one rotation (stacking stats, procs, heals, shields, resources)."""

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
        self._stacking_by_id: dict[str, PassiveEffectSpec] = {}
        self._heals: list[PassiveEffectSpec] = []
        self._procs: list[PassiveEffectSpec] = []
        self._shields: list[PassiveEffectSpec] = []
        self._resources: list[PassiveEffectSpec] = []
        self._stacks: dict[str, int] = {}
        self._stacked_at: dict[str, Fraction] = {}
        self._attack_counts: dict[str, int] = {}
        self._hit_counts: dict[str, int] = {}
        self._ability_hit_counts: dict[str, int] = {}
        self._ability_charges: dict[str, int] = {}
        self._ability_armed_at: dict[str, Fraction] = {}
        self._heal_stacks: dict[str, int] = {}
        self._ready: dict[str, Fraction] = {}
        self._fired: set[str] = set()
        self._noted_target_kind: set[str] = set()

        if not enabled:
            return
        for effect in _passive_specs(kit):
            if effect.kind == "stacking_stat":
                self._stacking.append(effect)
                self._stacking_by_id[effect.id] = effect
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
                self._attack_counts[effect.id] = 0
                self._hit_counts[effect.id] = 0
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
                self._hit_counts[effect.id] = 0
                self._ability_hit_counts[effect.id] = 0
                self._ability_charges[effect.id] = 0
            elif effect.kind == "shield":
                if effect.trigger in {"on_ability_cast", "on_champion_attack", "every_n_hits"}:
                    self._shields.append(effect)
                    self._hit_counts[effect.id] = 0
            elif effect.kind == "resource_restore":
                self._resources.append(effect)
                self._ability_hit_counts[effect.id] = 0

    def _expired(self, effect: PassiveEffectSpec, at: Fraction) -> bool:
        if not self.timeline or effect.duration_seconds is None:
            return False
        last = self._stacked_at.get(effect.id)
        return last is not None and at - last >= effect.duration_seconds

    def _matches_target_kind(self, effect: PassiveEffectSpec) -> bool:
        if effect.target_kind is None:
            return True
        if self.target.kind is None:
            if effect.id not in self._noted_target_kind:
                self._noted_target_kind.add(effect.id)
                self.notes.append(
                    f"passive P {effect.name}: requires --target-kind {effect.target_kind}"
                )
            return False
        if effect.target_kind == "champion":
            return self.target.kind == "champion"
        if effect.target_kind == "non_structure":
            return self.target.kind != "structure"
        return True

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
        self,
        at: Fraction,
        level: int,
        stats: Mapping[str, Fraction] | None = None,
    ) -> tuple[list[PassiveStatBonus], list[PassiveStatAmplifier]]:
        """Flat bonuses and total-stat amplifiers currently in force from passives."""
        if not self._stacking:
            return [], []
        flats: list[PassiveStatBonus] = []
        amplifiers: list[PassiveStatAmplifier] = []
        stat_env = stats or {}
        for effect in self._stacking:
            count = self._stacks.get(effect.id, 0)
            if count <= 0 or self._expired(effect, at):
                continue
            assert effect.stat is not None and effect.max_stacks is not None
            if effect.only_at_max and count < effect.max_stacks:
                continue
            try:
                per_stack = evaluate_formula(
                    effect.formula, stat_env, level=level, inputs=self.inputs, ops=ABILITY_OPS
                ).exact
            except FormulaError as exc:
                raise RotationError(f"passive P.{effect.id}: {exc}") from exc
            assert per_stack is not None
            mult = effect.max_stacks_multiplier if count == effect.max_stacks else Fraction(1)
            total = per_stack * mult if effect.only_at_max else per_stack * count * mult
            source = f"kit:{self.kit.champion} P {effect.id} ({count}/{effect.max_stacks} stacks)"
            if effect.mode == "percent":
                amplifiers.append(PassiveStatAmplifier(effect.stat, total, source, effect.label))
            elif effect.mode == "percent_ms":
                flats.append(
                    PassiveStatBonus(
                        effect.stat,
                        total,
                        source,
                        effect.label,
                        f"{count} stack{'' if count == 1 else 's'}",
                        percent=True,
                    )
                )
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

    def _can_fire(self, effect: PassiveEffectSpec, clock: Fraction, level: int) -> bool:
        cd = _effect_cooldown(effect, level)
        if cd is None:
            return True
        if not self.timeline:
            return effect.id not in self._fired
        return clock >= self._ready.get(effect.id, Fraction(0))

    def _mark_fired(self, effect: PassiveEffectSpec, clock: Fraction, level: int) -> None:
        self._fired.add(effect.id)
        cd = _effect_cooldown(effect, level)
        if self.timeline and cd is not None:
            self._ready[effect.id] = clock + cd

    def on_step(
        self,
        slot: str | None,
        dealt_damage: bool,
        clock: Fraction,
        sheet: StatSheet,
        *,
        target_health_before: Fraction | None = None,
        target_max_health: Fraction | None = None,
    ) -> list[PassiveProc]:
        """Fire damage procs for this step and advance stacking passive counters."""
        if not self._procs and not self._stacking:
            return []
        procs: list[PassiveProc] = []
        stats_pair: tuple[dict[str, Fraction], dict[str, tuple[str, Label]]] | None = None
        target_env: dict[str, Fraction] | None = None

        for effect in self._procs:
            triggered = False
            charge_mult = 1
            if (
                (effect.trigger in {"on_attack", "on_hit"} and slot is None)
                or (effect.trigger == "on_ability_hit" and slot is not None and dealt_damage)
                or (effect.trigger == "on_any_hit" and dealt_damage)
            ):
                triggered = self._matches_target_kind(effect)
            elif effect.trigger == "every_n_attacks" and slot is None:
                assert effect.every is not None
                if self._matches_target_kind(effect):
                    self._attack_counts[effect.id] += 1
                    if self._attack_counts[effect.id] >= effect.every:
                        self._attack_counts[effect.id] = 0
                        triggered = True
            elif effect.trigger == "every_n_hits" and dealt_damage:
                assert effect.every is not None
                if self._matches_target_kind(effect):
                    self._hit_counts[effect.id] += 1
                    if self._hit_counts[effect.id] >= effect.every:
                        self._hit_counts[effect.id] = 0
                        triggered = True
            elif effect.trigger == "every_n_ability_hits" and slot is not None and dealt_damage:
                assert effect.every is not None
                if self._matches_target_kind(effect):
                    self._ability_hit_counts[effect.id] += 1
                    if self._ability_hit_counts[effect.id] >= effect.every:
                        self._ability_hit_counts[effect.id] = 0
                        triggered = True
            elif effect.trigger == "after_ability":
                if slot is not None:
                    cap = effect.max_stacks or effect.charges_per_cast
                    self._ability_charges[effect.id] = min(
                        cap, self._ability_charges[effect.id] + effect.charges_per_cast
                    )
                    self._ability_armed_at[effect.id] = clock
                elif slot is None and self._ability_charges.get(effect.id, 0) > 0:
                    expired = (
                        self.timeline
                        and effect.duration_seconds is not None
                        and effect.id in self._ability_armed_at
                        and clock - self._ability_armed_at[effect.id] >= effect.duration_seconds
                    )
                    if expired:
                        self._ability_charges[effect.id] = 0
                    elif self._matches_target_kind(effect) and self._can_fire(
                        effect, clock, sheet.level
                    ):
                        if effect.consume_all_stacks:
                            charge_mult = self._ability_charges[effect.id]
                            self._ability_charges[effect.id] = 0
                        else:
                            self._ability_charges[effect.id] -= 1
                        triggered = True
            elif effect.trigger == "below_hp_percent" and slot is None:
                assert effect.threshold_hp_percent is not None
                if (
                    self._matches_target_kind(effect)
                    and target_health_before is not None
                    and target_max_health is not None
                    and target_max_health > 0
                    and target_health_before <= target_max_health * effect.threshold_hp_percent
                ):
                    triggered = True
            elif effect.trigger == "at_max_stacks" and slot is None:
                src_id = effect.stack_source_id
                src_spec = self._stacking_by_id.get(src_id or "")
                if (
                    src_spec is not None
                    and src_spec.max_stacks is not None
                    and self._stacks.get(src_spec.id, 0) >= src_spec.max_stacks
                    and not self._expired(src_spec, clock)
                    and self._matches_target_kind(effect)
                ):
                    triggered = True

            if not triggered or not self._can_fire(effect, clock, sheet.level):
                continue
            self._mark_fired(effect, clock, sheet.level)
            if stats_pair is None:
                stats_pair = sheet.cached_sheet_stats()
                target_env = {}
                if target_max_health is not None:
                    target_env["max_health"] = target_max_health
                if target_health_before is not None:
                    target_env["current_health"] = target_health_before
                if target_max_health and target_health_before is not None:
                    target_env["missing_fraction_health"] = (
                        max(Fraction(0), target_max_health - target_health_before)
                        / target_max_health
                    )
            stats, origin = stats_pair
            try:
                res = evaluate_formula(
                    effect.formula,
                    stats,
                    level=sheet.level,
                    target_stats=target_env or None,
                    inputs=self.inputs,
                    ops=ABILITY_OPS,
                )
            except FormulaError as exc:
                raise RotationError(f"passive P.{effect.id}: {exc}") from exc
            assert res.exact is not None and effect.damage_type is not None
            labels = [effect.label, *(origin[k][1] for k in res.dependencies if k in origin)]
            if any(k.startswith("target:") for k in res.dependencies):
                labels.append(self.target.label)
            raw_amount = res.exact * charge_mult
            proc_name = (
                f"{effect.name} x{charge_mult}"
                if effect.consume_all_stacks and charge_mult > 1
                else effect.name
            )
            procs.append(
                PassiveProc(
                    f"kit:{self.kit.champion} P {effect.id} ({proc_name})",
                    effect.damage_type,
                    raw_amount,
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

    def _target_max_health_env(self) -> dict[str, Fraction]:
        max_hp = self.target.stats.get("max_health")
        return {"max_health": max_hp} if max_hp is not None else {}

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
        heals: list[HealEvent] = []
        stats_pair: tuple[dict[str, Fraction], dict[str, tuple[str, Label]]] | None = None
        target_env: dict[str, Fraction] | None = None

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
            elif effect.trigger == "on_any_kill":
                if killed_target and self.target.kind != "structure":
                    triggered = True
                    notes.append("on unit kill")
            elif effect.trigger == "on_ability_cast":
                if slot is not None:
                    triggered = True
                    notes.append("on ability cast")
            elif effect.trigger == "on_champion_hit":
                if dealt_damage and self.target.kind == "champion":
                    triggered = True
                    notes.append("on champion hit")
            elif effect.trigger == "every_n_attacks" and slot is None:
                assert effect.every is not None
                self._attack_counts[effect.id] += 1
                if self._attack_counts[effect.id] >= effect.every:
                    self._attack_counts[effect.id] = 0
                    triggered = True
                    notes.append(f"every {effect.every} attacks")
            elif effect.trigger == "every_n_hits" and dealt_damage:
                assert effect.every is not None
                if self._matches_target_kind(effect):
                    self._hit_counts[effect.id] += 1
                    if self._hit_counts[effect.id] >= effect.every:
                        self._hit_counts[effect.id] = 0
                        triggered = True
                        notes.append(f"every {effect.every} hits")
            elif dealt_damage and (
                (effect.trigger == "on_hit" and slot is None)
                or (effect.trigger == "on_ability_hit" and slot is not None)
            ):
                triggered = True

            if not triggered or not self._can_fire(effect, clock, sheet.level):
                continue
            self._mark_fired(effect, clock, sheet.level)
            if stats_pair is None:
                stats_pair = sheet.cached_sheet_stats()
                target_env = self._target_max_health_env()
            stats, origin = stats_pair
            try:
                res = evaluate_formula(
                    effect.formula,
                    stats,
                    level=sheet.level,
                    target_stats=target_env or None,
                    inputs=self.inputs,
                    ops=ABILITY_OPS,
                )
            except FormulaError as exc:
                raise RotationError(f"passive P.{effect.id}: {exc}") from exc
            assert res.exact is not None
            labels = [effect.label, *(origin[k][1] for k in res.dependencies if k in origin)]
            if any(k.startswith("target:") for k in res.dependencies):
                labels.append(self.target.label)
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

    def on_step_shields(
        self,
        slot: str | None,
        dealt_damage: bool,
        clock: Fraction,
        sheet: StatSheet,
    ) -> list[ShieldEvent]:
        """Self-shield events triggered by the champion's passive on this step."""
        if not self._shields:
            return []
        shields: list[ShieldEvent] = []
        stats_pair: tuple[dict[str, Fraction], dict[str, tuple[str, Label]]] | None = None
        target_env: dict[str, Fraction] | None = None
        for effect in self._shields:
            triggered = False
            notes: list[str] = []
            if effect.trigger == "on_ability_cast" and slot is not None:
                triggered = True
                notes.append("on ability cast")
            elif (
                effect.trigger == "on_champion_attack"
                and slot is None
                and self.target.kind == "champion"
            ):
                triggered = True
                notes.append("on champion attack")
            elif effect.trigger == "every_n_hits" and dealt_damage:
                assert effect.every is not None
                if self._matches_target_kind(effect):
                    self._hit_counts[effect.id] += 1
                    if self._hit_counts[effect.id] >= effect.every:
                        self._hit_counts[effect.id] = 0
                        triggered = True
                        notes.append(f"every {effect.every} hits")
            if not triggered or not self._can_fire(effect, clock, sheet.level):
                continue
            self._mark_fired(effect, clock, sheet.level)
            if stats_pair is None:
                stats_pair = sheet.cached_sheet_stats()
                target_env = self._target_max_health_env()
            stats, origin = stats_pair
            try:
                res = evaluate_formula(
                    effect.formula,
                    stats,
                    level=sheet.level,
                    target_stats=target_env or None,
                    inputs=self.inputs,
                    ops=ABILITY_OPS,
                )
            except FormulaError as exc:
                raise RotationError(f"passive P.{effect.id}: {exc}") from exc
            assert res.exact is not None
            labels = [effect.label, *(origin[k][1] for k in res.dependencies if k in origin)]
            if any(k.startswith("target:") for k in res.dependencies):
                labels.append(self.target.label)
            shields.append(
                ShieldEvent(
                    f"kit:{self.kit.champion} P {effect.id} ({effect.name})",
                    res.exact,
                    res.exact,
                    effect.shield_type,
                    effect.duration_seconds,
                    weakest(labels),
                    tuple(notes),
                )
            )
        return shields

    def on_step_resources(
        self,
        slot: str | None,
        dealt_damage: bool,
        killed_target: bool,
        clock: Fraction,
        sheet: StatSheet,
    ) -> list[PassiveResourceRestore]:
        """Mana or energy restored by the champion's passive on this step."""
        if not self._resources:
            return []
        restores: list[PassiveResourceRestore] = []
        stats_pair: tuple[dict[str, Fraction], dict[str, tuple[str, Label]]] | None = None
        target_env: dict[str, Fraction] | None = None
        for effect in self._resources:
            assert effect.resource is not None
            triggered = False
            notes: list[str] = []
            if (
                effect.trigger == "on_any_kill"
                and killed_target
                and self.target.kind != "structure"
            ):
                triggered = True
                notes.append("on unit kill")
            elif effect.trigger == "on_hit" and slot is None and dealt_damage:
                if self._matches_target_kind(effect):
                    triggered = True
                    notes.append("on basic attack hit")
            elif effect.trigger == "on_ability_hit" and slot is not None and dealt_damage:
                if self._matches_target_kind(effect):
                    triggered = True
                    notes.append("on ability hit")
            elif (
                effect.trigger == "on_champion_hit"
                and dealt_damage
                and self.target.kind == "champion"
            ):
                triggered = True
                notes.append("on champion hit")
            elif effect.trigger == "every_n_ability_hits" and slot is not None and dealt_damage:
                assert effect.every is not None
                if self._matches_target_kind(effect):
                    self._ability_hit_counts[effect.id] += 1
                    if self._ability_hit_counts[effect.id] >= effect.every:
                        self._ability_hit_counts[effect.id] = 0
                        triggered = True
                        notes.append(f"every {effect.every} ability hits")
            if not triggered or not self._can_fire(effect, clock, sheet.level):
                continue
            self._mark_fired(effect, clock, sheet.level)
            if stats_pair is None:
                stats_pair = sheet.cached_sheet_stats()
                target_env = self._target_max_health_env()
            stats, origin = stats_pair
            try:
                res = evaluate_formula(
                    effect.formula,
                    stats,
                    level=sheet.level,
                    target_stats=target_env or None,
                    inputs=self.inputs,
                    ops=ABILITY_OPS,
                )
            except FormulaError as exc:
                raise RotationError(f"passive P.{effect.id}: {exc}") from exc
            assert res.exact is not None
            labels = [effect.label, *(origin[k][1] for k in res.dependencies if k in origin)]
            if any(k.startswith("target:") for k in res.dependencies):
                labels.append(self.target.label)
            restores.append(
                PassiveResourceRestore(
                    f"kit:{self.kit.champion} P {effect.id} ({effect.name})",
                    effect.resource,
                    res.exact,
                    weakest(labels),
                    tuple(notes),
                )
            )
        return restores
