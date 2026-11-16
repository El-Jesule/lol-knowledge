"""Rotations: an ordered list of basic attacks and ability casts against one target.

Each step is turned into damage parts (the attack itself, item on-hit damage,
ability cases), every part is mitigated by the target's resistance, then
multiplied by the attacker's damage-dealt modifiers and the target's
damage-taken modifiers. The target's current health is carried from step to
step, so current-health effects read the health left by earlier steps.

Every part also carries the healing the attacker gets from it through life
steal and omnivamp, computed from the part's final damage.

Rules: ``lol-knowledge/mechanics/critical-strike.md``,
``lol-knowledge/mechanics/damage-modifiers.md``,
``lol-knowledge/mechanics/basic-attacks-and-on-hit.md`` and
``lol-knowledge/mechanics/life-steal-and-omnivamp.md``. Pure functions over
already-loaded values; the CLI does the loading.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from fractions import Fraction
from typing import Any

from .damage import DamageResult, DamageType, format_number, mitigate
from .errors import KitError, RotationError
from .formula import FormulaError, evaluate_formula
from .kit import Kit, ability_damage, sheet_stats
from .scenario import PENETRATION, Target, penetration_modifiers
from .stats import (
    EVIDENCE_LABEL,
    ItemData,
    Label,
    StatBlocked,
    StatSheet,
    ability_cooldowns,
    effect_amount,
    sheet_effect_reason,
    weakest,
    with_amplifier,
    with_bonus,
)

RULES = (
    "lol-knowledge/mechanics/basic-attacks-and-on-hit.md",
    "lol-knowledge/mechanics/critical-strike.md",
    "lol-knowledge/mechanics/damage-modifiers.md",
    "lol-knowledge/mechanics/damage-mitigation.md",
    "lol-knowledge/mechanics/stat-growth.md",
    "lol-knowledge/mechanics/life-steal-and-omnivamp.md",
)
HOLDER_RANGES = frozenset({"melee", "ranged"})
ATTACK_MODIFIERS = frozenset({"crit", "nospellblade"})
# Triggers whose ``stacks.required`` counts basic attacks (attack-counters.md).
COUNTED_TRIGGERS = frozenset({"on_hit", "on_attack"})
# A burn starts when an ability deals damage, or when one is cast (burns.md).
BURN_TRIGGERS = frozenset({"damaging_ability", "cast"})
# Base critical strike multiplier of the patch notes (26.1); records that differ are flagged.
PATCH_CRIT_MULTIPLIER = Fraction(2)
# Passives that reduce total critical strike damage: "Critical Strike Damage Reduction:
# -10% => -5%" for Yasuo and Yone in the 26.17 patch notes (critical-strike.md, C10).
CRIT_DAMAGE_REDUCTIONS = {"Yasuo": Fraction(5, 100), "Yone": Fraction(5, 100)}
# Limit conditions of the catalog, as the target kinds they apply to.
LIMIT_CONDITIONS = {"target is a minion or monster": frozenset({"minion", "monster"})}
# Effect components that change the damage of a rotation when not applied.
DAMAGE_KINDS = frozenset(
    {"damage", "damage_modifier", "stat_modifier", "burn", "execute", "repeat_on_hit"}
)

# Effects that last a while once triggered; only the timeline applies them (timeline.md).
TIMED_KINDS = frozenset({"damage_modifier", "stat_modifier"})
TIMED_TRIGGERS = frozenset({"spellblade", "energized", "damaging_ability", "on_attack"})
# Triggers on a hit: whether that hit benefits from its own effect is not verified.
UNCERTAIN_START_TRIGGERS = frozenset({"spellblade", "energized"})
# Target resistances a timed effect can reduce, by the damage type they mitigate.
RESISTANCE_STATS = {"armor": DamageType.PHYSICAL, "magic_resist": DamageType.MAGIC}
# Stats whose timed change moves the attack timer.
ATTACK_SPEED_STATS = frozenset({"attack_speed", "attack_speed_bonus"})

# Kinds against which omnivamp drops to 33 % for pets, damage over time and area spells.
REDUCED_OMNIVAMP_KINDS = frozenset({"minion", "monster"})

WAIT_SECONDS = re.compile(r"\d+(?:\.\d+)?")
_ABILITY_STEP = re.compile(r"(?P<slot>[QWER])(?:\.(?P<case>[a-z0-9_]+))?")


@dataclass(frozen=True)
class Step:
    """One rotation step: a basic attack (``slot`` is ``None``) or an ability case."""

    text: str
    slot: str | None = None
    case: str | None = None
    crit: bool = False
    # False for ``attack:nospellblade``: the attack is not empowered (spellblade.md).
    spellblade: bool = True
    # Seconds to wait, for ``wait:<seconds>`` (timeline only, timeline.md).
    wait: Fraction | None = None


def parse_steps(text: str) -> tuple[Step, ...]:
    """Read ``attack``, ``attack:crit``, ``attack:nospellblade``, ``Q``, ``E.edge``…

    Steps are separated by commas or spaces; an attack takes any of the
    modifiers ``crit`` and ``nospellblade``, once each and in any order.
    """
    tokens = [token for token in re.split(r"[,\s]+", text.strip()) if token]
    if not tokens:
        raise RotationError("the rotation has no steps")
    steps = []
    for token in tokens:
        head, *modifiers = token.lower().split(":")
        if head == "wait":
            steps.append(Step(token, wait=_seconds(token, modifiers)))
            continue
        if head == "attack":
            if not set(modifiers) <= ATTACK_MODIFIERS or len(set(modifiers)) != len(modifiers):
                raise RotationError(
                    f"unknown step {token!r}: an attack takes crit and nospellblade, once each"
                )
            steps.append(
                Step(token, crit="crit" in modifiers, spellblade="nospellblade" not in modifiers)
            )
            continue
        match = _ABILITY_STEP.fullmatch(token[:1].upper() + token[1:])
        if match is None:
            raise RotationError(
                f"unknown step {token!r}: use attack, attack:crit, attack:nospellblade, "
                "Q, W, E, R or SLOT.case"
            )
        steps.append(Step(token, match.group("slot"), match.group("case")))
    return tuple(steps)


def _seconds(token: str, modifiers: Sequence[str]) -> Fraction:
    if len(modifiers) != 1 or WAIT_SECONDS.fullmatch(modifiers[0]) is None:
        raise RotationError(f"unknown step {token!r}: use wait:<seconds>, e.g. wait:0.5")
    seconds = Fraction(modifiers[0])
    if seconds <= 0:
        raise RotationError(f"step {token!r}: the wait must be longer than 0 s")
    return seconds


@dataclass(frozen=True)
class CritBase:
    """The champion's base critical strike multiplier and where it comes from."""

    value: Fraction
    label: Label
    source: str


@dataclass(frozen=True)
class Healing:
    """Healing from one part: its final damage x (life steal + omnivamp) that apply."""

    life_steal: Fraction  # rate applied to this part; 0 when it does not apply
    omnivamp: Fraction
    amount: Fraction
    label: Label
    notes: tuple[str, ...] = ()


NO_HEALING = Healing(Fraction(0), Fraction(0), Fraction(0), Label.OFFICIAL)


@dataclass(frozen=True)
class Part:
    kind: str  # "attack", "on_hit", "ability", "burn" or "execute"
    source: str
    damage_type: DamageType
    raw: Fraction
    mitigation: DamageResult
    dealt: tuple[tuple[str, Fraction], ...]  # (effect, percent) applied
    taken: tuple[tuple[str, Fraction], ...]
    label: Label
    notes: tuple[str, ...] = ()
    healing: Healing = NO_HEALING

    @property
    def dealt_factor(self) -> Fraction:
        """Damage-dealt modifiers add up (V26.09) before multiplying."""
        return 1 + sum((percent for _, percent in self.dealt), start=Fraction(0)) / 100

    @property
    def taken_factor(self) -> Fraction:
        """Damage-taken modifiers multiply with each other."""
        factor = Fraction(1)
        for _, percent in self.taken:
            factor *= 1 + percent / 100
        return factor

    @property
    def damage(self) -> Fraction:
        return self.mitigation.damage * self.dealt_factor * self.taken_factor


@dataclass(frozen=True)
class StepOutcome:
    index: int
    step: Step
    name: str
    parts: tuple[Part, ...]
    health_before: Fraction
    label: Label
    # Seconds from the start of the rotation, with the timeline (timeline.md).
    time: Fraction | None = None

    @property
    def total(self) -> Fraction:
        return sum((part.damage for part in self.parts), start=Fraction(0))

    @property
    def health_after(self) -> Fraction:
        return max(Fraction(0), self.health_before - self.total)

    @property
    def overkill(self) -> bool:
        """Whether the step deals more damage than the health the target had left."""
        return self.total > self.health_before

    @property
    def healing(self) -> Fraction:
        return sum((part.healing.amount for part in self.parts), start=Fraction(0))

    @property
    def healing_label(self) -> Label:
        labels = [part.healing.label for part in self.parts]
        if self.overkill and self.healing:
            labels.append(Label.PENDING)
        return weakest(labels)

    @property
    def healing_notes(self) -> tuple[str, ...]:
        if self.overkill and self.healing:
            return (
                "the step deals more damage than the target's remaining health; healing uses "
                "the full damage, which is not verified",
            )
        return ()


@dataclass(frozen=True)
class Timeline:
    """What the timeline read from the sheet: attack interval and cooldowns."""

    attack_interval: Fraction
    label: Label
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class RotationOutcome:
    steps: tuple[StepOutcome, ...]
    max_health: Fraction
    start_health: Fraction
    holder_range: str | None
    label: Label
    notes: tuple[str, ...]
    timeline: Timeline | None = None

    @property
    def total(self) -> Fraction:
        return sum((step.total for step in self.steps), start=Fraction(0))

    @property
    def duration(self) -> Fraction | None:
        """Seconds from the first step to the last one, with the timeline."""
        if self.timeline is None:
            return None
        return self.steps[-1].time

    @property
    def damage_per_second(self) -> Fraction | None:
        duration = self.duration
        if not duration:
            return None
        return self.total / duration

    @property
    def remaining_health(self) -> Fraction:
        return max(Fraction(0), self.start_health - self.total)

    @property
    def healing(self) -> Fraction:
        return sum((step.healing for step in self.steps), start=Fraction(0))

    @property
    def healing_label(self) -> Label:
        return weakest(step.healing_label for step in self.steps)

    @property
    def lethal_step(self) -> int | None:
        """Index (from 1) of the step that takes the target to 0 health, if any."""
        for step in self.steps:
            if step.health_after == 0:
                return step.index
        return None


@dataclass(frozen=True)
class _Effect:
    item: str
    id: str
    name: str
    label: Label
    trigger: str
    conditions: tuple[str, ...]
    component: Mapping[str, Any]
    limits: tuple[Mapping[str, Any], ...]
    # Fires on every Nth basic attack (``stacks.required``), counted from zero.
    every: int | None = None
    # Values of conditions that take one (``target_health_below``: a percentage).
    condition_values: Mapping[str, Any] = field(default_factory=dict)
    scenario: str | None = None
    # Seconds the effect lasts once triggered (``duration_seconds``), and whom it affects.
    duration: Fraction | None = None
    affects: str | None = None
    # Cooldown once triggered, and seconds each attack hit (critical) takes off it.
    cooldown: Fraction | None = None
    refund: tuple[Fraction, Fraction] | None = None
    # Seconds a counter's stacks last after the last attack (``stacks.window_seconds``).
    window: Fraction | None = None

    @property
    def title(self) -> str:
        return f"{self.item} {self.id}"


# Effect conditions on the target kind: a skipped effect whose condition rules
# out the rotation's target cannot change its damage.
TARGET_KIND_CONDITIONS = {
    "target_is_champion": "champion",
    "target_is_structure": "structure",
    "target_is_minion": "minion",
    "target_is_monster": "monster",
}


@dataclass(frozen=True)
class _Window:
    """A timed effect in force until ``end``, with its value when it was triggered."""

    effect: _Effect
    end: Fraction
    value: Fraction
    labels: tuple[Label, ...]


@dataclass(frozen=True)
class _Burn:
    """A burn in progress: damage per second (as applied) until ``end``."""

    effect: _Effect
    end: Fraction
    per_second: Fraction
    labels: tuple[Label, ...]


def _could_apply(effect: Mapping[str, Any], target_kind: str | None) -> bool:
    if target_kind is None:
        return True
    return all(
        TARGET_KIND_CONDITIONS[kind] == target_kind
        for kind in (str(entry.get("kind")) for entry in effect.get("conditions") or ())
        if kind in TARGET_KIND_CONDITIONS
    )


def _effects(
    items: Sequence[ItemData], owner: str, target_kind: str | None = None
) -> tuple[list[_Effect], list[str], bool]:
    """Split item effects into evaluable components and notes on the rest.

    Returns the components, the notes and whether a skipped effect could have
    changed the damage (which weakens the result). A skipped effect whose
    conditions exclude ``target_kind`` does not weaken it.
    """
    seen: set[str] = set()
    effects: list[_Effect] = []
    notes: list[str] = []
    weakened = False
    for item in items:
        if item.id in seen:
            raise RotationError(
                f"{owner} item {item.id} is listed twice; unique effects of copies are not modelled"
            )
        seen.add(item.id)
        if item.effect_review != "complete":
            notes.append(
                f"{owner} {item.id}: effect review {item.effect_review}; "
                "effects missing from the catalog are not applied"
            )
            weakened = True
        for effect in item.effects:
            reason = sheet_effect_reason(effect)
            if reason is not None:
                notes.append(
                    f"{owner} {item.id} {effect.get('id')}: applied by the stat sheet ({reason})"
                )
                continue
            status = effect.get("model_status")
            components = effect.get("components") or ()
            if status != "evaluable":
                notes.append(f"{owner} {item.id} {effect.get('id')}: {status}, not applied")
                weakened |= _could_apply(effect, target_kind) and any(
                    c.get("kind") in DAMAGE_KINDS for c in components
                )
                continue
            label = EVIDENCE_LABEL.get(str(effect.get("evidence_confidence")), Label.DERIVED)
            for component in components:
                effects.append(
                    _Effect(
                        item.id,
                        str(effect.get("id")),
                        str(effect.get("name", "")),
                        label,
                        str((effect.get("trigger") or {}).get("event")),
                        tuple(
                            str(entry.get("kind"))
                            for entry in [
                                *(effect.get("conditions") or ()),
                                *(component.get("conditions") or ()),
                            ]
                        ),
                        component,
                        tuple(effect.get("limits") or ()),
                        _every(effect),
                        {
                            str(entry.get("kind")): entry["value"]
                            for entry in [
                                *(effect.get("conditions") or ()),
                                *(component.get("conditions") or ()),
                            ]
                            if "value" in entry
                        },
                        effect.get("scenario"),
                        _duration(effect),
                        (effect.get("target") or {}).get("kind"),
                        _seconds_of(effect.get("cooldown_seconds")),
                        _refund(effect),
                        _window(effect),
                    )
                )
    return effects, notes, weakened


def _seconds_of(value: Any) -> Fraction | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
        return Fraction(str(value))
    return None


def _duration(effect: Mapping[str, Any]) -> Fraction | None:
    return _seconds_of(effect.get("duration_seconds"))


def _refund(effect: Mapping[str, Any]) -> tuple[Fraction, Fraction] | None:
    refund = effect.get("cooldown_reduced_by_attacks")
    if not isinstance(refund, Mapping):
        return None
    return Fraction(str(refund["seconds"])), Fraction(str(refund["critical_seconds"]))


def _window(effect: Mapping[str, Any]) -> Fraction | None:
    stacks = effect.get("stacks")
    if _every(effect) is None or not isinstance(stacks, Mapping):
        return None
    return _seconds_of(stacks.get("window_seconds"))


def _excluded(effect: _Effect, target_kind: str | None) -> bool:
    """Whether a condition of ``effect`` on the target kind rules out ``target_kind``."""
    return target_kind is not None and any(
        TARGET_KIND_CONDITIONS[condition] != target_kind
        for condition in effect.conditions
        if condition in TARGET_KIND_CONDITIONS
    )


def _every(effect: Mapping[str, Any]) -> int | None:
    """``N`` for an effect on every Nth attack, from ``stacks.required`` (N >= 2)."""
    stacks = effect.get("stacks")
    required = stacks.get("required") if isinstance(stacks, Mapping) else None
    if (effect.get("trigger") or {}).get("event") not in COUNTED_TRIGGERS:
        return None
    if isinstance(required, int) and not isinstance(required, bool) and required >= 2:
        return required
    return None


def _target_kind(target: Target, why: str) -> str:
    if target.kind is None:
        raise RotationError(f"{why} depends on the target kind; give --target-kind")
    return target.kind


def _conditions_hold(
    effect: _Effect,
    target: Target,
    part_kind: str,
    crit: bool,
    target_stats: Mapping[str, Fraction] | None = None,
    slot: str | None = None,
) -> bool:
    for condition in effect.conditions:
        if condition in TARGET_KIND_CONDITIONS:
            if _target_kind(target, effect.title) != TARGET_KIND_CONDITIONS[condition]:
                return False
        elif condition == "on_hit":
            if part_kind != "on_hit":
                return False
        elif condition == "critical_strike":
            if not (crit and part_kind == "attack"):
                return False
        elif condition == "damage_source_is_attack":
            if part_kind != "attack":
                return False
        elif condition == "ultimate_ability":
            if slot != "R":
                return False
        elif condition == "target_health_below":
            if target_stats is None:
                raise RotationError(f"{effect.title}: needs the target's health")
            threshold = Fraction(str(effect.condition_values[condition])) / 100
            if target_stats["current_health"] >= threshold * target_stats["max_health"]:
                return False
        else:
            raise RotationError(f"{effect.title}: condition {condition!r} is not modelled")
    return True


class _Rotation:
    def __init__(
        self,
        kit: Kit,
        sheet: StatSheet,
        ranks: Mapping[str, int],
        target: Target,
        crit_base: CritBase | None,
        holder_range: str | None,
        inputs: Mapping[str, Any],
        timeline: bool = False,
    ) -> None:
        self.kit, self.sheet, self.ranks, self.target = kit, sheet, ranks, target
        self.base_sheet = sheet
        self.timeline = self._timeline() if timeline else None
        self.crit_base, self.holder_range, self.inputs = crit_base, holder_range, inputs
        self.stats, self.origin = sheet_stats(sheet)
        self.life_steal, self.omnivamp = sheet["life_steal"], sheet["omnivamp"]
        attacker, notes, weakened = _effects(sheet.items, "attacker", target.kind)
        defender, target_notes, target_weakened = _effects(target.items, "target")
        self.notes = notes + target_notes
        self.weakened = weakened or target_weakened
        self.on_hit: list[_Effect] = []
        self.dealt: list[_Effect] = []
        self.taken: list[_Effect] = []
        self.spellblade: list[_Effect] = []
        self.repeats: list[_Effect] = []
        self.counted: list[_Effect] = []
        self.counted_repeats: list[_Effect] = []
        self.energized: list[_Effect] = []
        self.galvanize: list[_Effect] = []
        self.executes: list[_Effect] = []
        self.burns: list[_Effect] = []
        self.timed: list[_Effect] = []
        # Timeline state: timed effects and burns in force, and how far burns are counted.
        self.windows: dict[str, _Window] = {}
        self.timed_ready: dict[str, Fraction] = {}  # cooldowns of timed effects
        self.last_counted: dict[str, Fraction] = {}  # last attack of each counter
        self.speed_changed = False  # a timed effect changed the attack speed
        self.burning: dict[str, _Burn] = {}
        self.accrued = Fraction(0)
        self.active_dealt: list[_Window] = []
        self.shred: dict[DamageType, list[_Window]] = {}
        owners = sorted(
            {
                item.id
                for item in sheet.items
                if any(
                    (effect.get("trigger") or {}).get("event") == "spellblade"
                    for effect in item.effects
                )
            }
        )
        if len(owners) > 1:
            raise RotationError(
                f"items {', '.join(owners)} all have Spellblade; a champion is limited to one "
                "Spellblade item (spellblade.md)"
            )
        for effect in attacker:
            kind = effect.component.get("kind")
            if effect.every is not None and kind == "damage":
                self.counted.append(effect)
            elif effect.every is not None and kind == "repeat_on_hit":
                self.counted_repeats.append(effect)
            elif effect.trigger == "on_hit" and kind == "damage":
                self.on_hit.append(effect)
            elif effect.trigger == "energized" and kind == "damage":
                self.energized.append(effect)
            elif kind == "execute":
                self.executes.append(effect)
            elif effect.trigger in BURN_TRIGGERS and kind == "burn":
                self.burns.append(effect)
            elif effect.trigger == "damaging_ability" and kind == "trigger_energized":
                self.galvanize.append(effect)
            elif effect.trigger == "spellblade" and kind == "damage":
                self.spellblade.append(effect)
            elif effect.trigger == "spellblade" and kind == "repeat_on_hit":
                self.repeats.append(effect)
            elif effect.trigger == "always" and kind == "damage_modifier":
                if effect.component.get("direction") != "dealt":
                    self._skip(effect, "damage taken by the attacker")
                else:
                    self.dealt.append(effect)
                    if effect.scenario is not None:
                        self.notes.append(
                            f"attacker {effect.title}: applied at full stacks "
                            f"(scenario {effect.scenario})"
                        )
            elif (
                effect.duration is not None
                and kind in TIMED_KINDS
                and effect.trigger in TIMED_TRIGGERS
            ):
                self._timed(effect)
            else:
                self._skip(effect, f"{effect.trigger} {kind}")
        if len({effect.item for effect in self.energized}) > 1:
            self.notes.append(
                "several Energized items: whether their Energized effects stack is not verified"
            )
            self.weakened = True
        for effect in defender:
            kind = effect.component.get("kind")
            if kind == "damage_modifier" and effect.component.get("direction") == "taken":
                self.taken.append(effect)
            else:
                self._skip(effect, f"{effect.trigger} {kind}", owner="target")

    def _skip(self, effect: _Effect, why: str, owner: str = "attacker") -> None:
        self.notes.append(f"{owner} {effect.title}: {why} is not part of rotations, not applied")
        if effect.component.get("kind") in DAMAGE_KINDS and owner == "attacker":
            self.weakened = True

    def _timed(self, effect: _Effect) -> None:
        """Keep a timed effect for the timeline, or note that it needs one."""
        assert effect.duration is not None
        if self.timeline is None:
            self.notes.append(
                f"attacker {effect.title}: lasts {format_number(effect.duration)} s; "
                "applied only with --timeline"
            )
            self.weakened |= not _excluded(effect, self.target.kind)
            return
        component = effect.component
        kind = component.get("kind")
        if kind == "damage_modifier":
            if component.get("direction") != "dealt" or component.get("source") != "all":
                raise RotationError(f"{effect.title}: only dealt modifiers of all damage are timed")
            self._mode(effect)
        elif effect.affects == "self":
            mode = component.get("mode")
            if mode not in {"flat", "percent"} or (
                mode == "percent" and component.get("scope") != "total"
            ):
                raise RotationError(f"{effect.title}: only flat or total-percent stats are timed")
        elif str(component.get("stat")) not in RESISTANCE_STATS or component.get("mode") != "flat":
            raise RotationError(f"{effect.title}: only flat target resistance changes are timed")
        self.timed.append(effect)

    def _percent(self, effect: _Effect, target_stats: Mapping[str, Fraction]) -> Fraction:
        return self._value(effect, target_stats)[0]

    def _value(
        self, effect: _Effect, target_stats: Mapping[str, Fraction]
    ) -> tuple[Fraction, list[Label]]:
        """The effect's formula and the labels of the attacker stats it reads."""
        try:
            result = evaluate_formula(
                effect.component.get("formula"),
                self.stats,
                holder_range=self.holder_range,
                level=self.sheet.level,
                target_stats=target_stats,
            )
        except FormulaError as exc:
            raise RotationError(f"{effect.title}: {self._explain(exc)}") from exc
        labels = [self.origin[key][1] for key in result.dependencies if key in self.origin]
        assert result.exact is not None
        return result.exact, labels

    @staticmethod
    def _explain(exc: FormulaError) -> str:
        detail = str(exc)
        if exc.code == "missing_holder_range":
            detail += " (give --attacker-range melee|ranged)"
        elif "target:bonus_health" in detail:
            detail += " (give --target-bonus-health or --target-champion)"
        return detail

    def _modifiers(
        self,
        part_kind: str,
        crit: bool,
        target_stats: Mapping[str, Fraction],
        damage_type: DamageType,
    ) -> tuple[list[tuple[str, Fraction]], list[tuple[str, Fraction]], list[Label], list[str]]:
        dealt: list[tuple[str, Fraction]] = []
        taken: list[tuple[str, Fraction]] = []
        labels: list[Label] = []
        notes: list[str] = []
        for effect in self.dealt:
            types = effect.component.get("damage_types")
            if types is not None and damage_type.value not in types:
                continue
            if self._mode(effect) and _conditions_hold(
                effect, self.target, part_kind, crit, target_stats
            ):
                if effect.component.get("source") != "all":
                    raise RotationError(f"{effect.title}: source is not modelled")
                value, stat_labels = self._value(effect, target_stats)
                dealt.append((effect.title, value))
                labels += [effect.label, *stat_labels]
        for window in self.active_dealt:
            types = window.effect.component.get("damage_types")
            if types is not None and damage_type.value not in types:
                continue
            if _conditions_hold(window.effect, self.target, part_kind, crit, target_stats):
                dealt.append((window.effect.title, window.value))
                labels += window.labels
        for effect in self.taken:
            if not (self._mode(effect) and _conditions_hold(effect, self.target, part_kind, crit)):
                continue
            source = effect.component.get("source")
            if source == "attack" and part_kind == "on_hit":
                notes.append(f"{effect.title}: unknown whether it reduces on-hit item damage")
                labels.append(Label.PENDING)
                continue
            if source == "attack" and part_kind != "attack":
                continue
            if source not in {"all", "attack"}:
                raise RotationError(f"{effect.title}: source {source!r} is not modelled")
            taken.append((effect.title, self._percent(effect, target_stats)))
            labels.append(effect.label)
        return dealt, taken, labels, notes

    @staticmethod
    def _mode(effect: _Effect) -> bool:
        if effect.component.get("mode") != "percent":
            raise RotationError(f"{effect.title}: only percent damage modifiers are modelled")
        return True

    def _part(
        self,
        kind: str,
        source: str,
        damage_type: DamageType,
        raw: Fraction,
        labels: list[Label],
        crit: bool,
        target_stats: Mapping[str, Fraction],
        notes: Sequence[str] = (),
        life_steal_tag: Mapping[str, Any] | None = None,
    ) -> Part:
        modifiers = penetration_modifiers(self.sheet, damage_type)
        shred = self.shred.get(damage_type, [])
        if shred:
            modifiers = replace(
                modifiers,
                flat_reduction=(*modifiers.flat_reduction, *(-window.value for window in shred)),
            )
            labels = [*labels, *(label for window in shred for label in window.labels)]
            notes = (
                *notes,
                *(
                    f"{window.effect.title} ({window.effect.name}): target "
                    f"{window.effect.component.get('stat')} {format_number(window.value)}"
                    for window in shred
                ),
            )
        mitigation = mitigate(raw, damage_type, self.target.resistance(damage_type), modifiers)
        if damage_type in PENETRATION:
            percent, flat = PENETRATION[damage_type]
            labels = [*labels, self.sheet[percent].label, self.sheet[flat].label]
        dealt, taken, modifier_labels, modifier_notes = self._modifiers(
            kind, crit, target_stats, damage_type
        )
        part = Part(
            kind,
            source,
            damage_type,
            raw,
            mitigation,
            tuple(dealt),
            tuple(taken),
            weakest([*labels, *modifier_labels]),
            (*notes, *modifier_notes),
        )
        return replace(part, healing=self._healing(part, life_steal_tag))

    def _healing(self, part: Part, tag: Mapping[str, Any] | None) -> Healing:
        """Life steal and omnivamp healing of ``part`` (life-steal-and-omnivamp.md)."""
        life_steal, omnivamp = self.life_steal.total(), self.omnivamp.total()
        if not life_steal and not omnivamp:
            return NO_HEALING
        if self.target.kind == "structure":
            return Healing(
                Fraction(0),
                Fraction(0),
                Fraction(0),
                Label.PENDING,
                ("no life steal or omnivamp healing against structures",),
            )
        labels = [Label.DERIVED, part.label]
        notes: list[str] = []
        applied_life_steal = Fraction(0)
        if life_steal:
            if part.kind == "attack":
                applied_life_steal = life_steal
            elif part.kind == "on_hit" and tag is not None:
                if tag.get("value") is True:
                    applied_life_steal = life_steal
                    confidence = str((tag.get("source") or {}).get("confidence"))
                    labels.append(EVIDENCE_LABEL.get(confidence, Label.PENDING))
            elif part.kind == "on_hit":
                labels.append(Label.PENDING)
                notes.append("the catalog does not declare whether it applies life steal")
            elif part.kind == "burn":
                pass  # life steal comes from attacks; an item burn is not one (burns.md)
            else:
                labels.append(Label.PENDING)
                notes.append("the kit does not declare whether it applies life steal")
            if applied_life_steal:
                labels.append(self.life_steal.label)
        if omnivamp:
            labels.append(self.omnivamp.label)
            if part.kind == "burn" and self.target.kind in REDUCED_OMNIVAMP_KINDS:
                omnivamp /= 3
                notes.append(f"omnivamp from damage over time against a {self.target.kind}: 33%")
            elif part.kind == "ability":
                kind = _target_kind(self.target, "omnivamp healing from an ability")
                if kind in REDUCED_OMNIVAMP_KINDS:
                    labels.append(Label.PENDING)
                    notes.append(
                        f"omnivamp against a {kind} is 33% for pets, damage over time and "
                        "area spells; the kit does not say which, healed at 100%"
                    )
        if applied_life_steal and omnivamp:
            labels.append(Label.PENDING)
            notes.append("life steal and omnivamp on the same damage: their sum is not verified")
        rate = applied_life_steal + omnivamp
        return Healing(
            applied_life_steal, omnivamp, part.damage * rate, weakest(labels), tuple(notes)
        )

    def _attack(
        self, step: Step, target_stats: Mapping[str, Fraction], empowered: bool = False
    ) -> list[Part]:
        attack_damage = self.sheet["attack_damage"]
        raw = attack_damage.total()
        labels = [attack_damage.label]
        notes: list[str] = []
        source = "basic attack: total attack damage"
        if step.crit:
            if self.crit_base is None:
                raise RotationError(
                    f"step {step.text}: no critical multiplier for {self.sheet.champion.id} "
                    "(lol-knowledge/derived/champion-records.json has no critdamagemultiplier)"
                )
            bonus = self.sheet["crit_damage_bonus"]
            multiplier = self.crit_base.value + bonus.total()
            labels += [self.crit_base.label, bonus.label]
            reduction = CRIT_DAMAGE_REDUCTIONS.get(self.sheet.champion.id)
            if reduction is not None:
                multiplier *= 1 - reduction
                labels.append(Label.DERIVED)
                notes.append(
                    f"{self.sheet.champion.id}'s passive reduces total critical strike damage "
                    f"by {format_number(reduction * 100)}%"
                )
            raw *= multiplier
            source += f" x critical multiplier {format_number(multiplier)}"
            if len(bonus.sources()) > 1:
                labels.append(Label.PENDING)
                notes.append("several crit damage sources: their stacking is not verified")
            if self.crit_base.value != PATCH_CRIT_MULTIPLIER:
                labels.append(Label.PENDING)
                notes.append(
                    f"{self.sheet.champion.id}'s record has a {self.crit_base.value} critical "
                    f"multiplier, not the patch's {PATCH_CRIT_MULTIPLIER}; its kit may change "
                    "crits"
                )
        parts = [
            self._part(
                "attack", source, DamageType.PHYSICAL, raw, labels, step.crit, target_stats, notes
            )
        ]
        parts += self._on_hit(self.on_hit, step, target_stats)
        if not empowered:
            return parts
        parts += self._on_hit(self.spellblade, step, target_stats)
        for repeat in self.repeats:
            parts += self._on_hit(
                self.on_hit, step, target_stats, f" - again by {repeat.title}", repeat.label
            )
        return parts

    def _burns(
        self,
        step: Step,
        parts: Sequence[Part],
        target_stats: Mapping[str, Fraction],
        burned: set[str],
        clock: Fraction = Fraction(0),
    ) -> list[Part]:
        """Each burn's full duration, once, on the first ability step that starts it.

        With the timeline, the step (re)starts the burn instead; its damage is
        counted as time passes (``_accrue``).
        """
        result: list[Part] = []
        for effect in self.burns:
            if effect.trigger == "damaging_ability" and not parts:
                continue
            if self.timeline is None and effect.title in burned:
                continue
            if not _conditions_hold(effect, self.target, "burn", False, target_stats, step.slot):
                continue
            burned.add(effect.title)
            duration = Fraction(str(effect.component.get("duration_seconds")))
            per_second, stat_labels = self._value(effect, target_stats)
            if self.timeline is not None:
                self.burning[effect.title] = _Burn(
                    effect, clock + duration, per_second, (effect.label, *stat_labels)
                )
                continue
            result.append(
                self._part(
                    "burn",
                    f"{effect.title} ({effect.name}) over {format_number(duration)} s",
                    DamageType(str(effect.component.get("damage_type"))),
                    per_second * duration,
                    [effect.label, *stat_labels],
                    False,
                    target_stats,
                )
            )
        return result

    def _target_stats(self, health: Fraction) -> dict[str, Fraction]:
        return {
            **self.target.stats,
            "current_health": health,
            "missing_fraction_health": 1 - health / self.target.stats["max_health"],
        }

    def _set_moment(self, at: Fraction) -> None:
        """Apply the timed effects in force at ``at``: stats, dealt damage, resistances."""
        sheet = self.base_sheet
        self.active_dealt, self.shred = [], {}
        for window in self.windows.values():
            if window.end <= at:
                continue
            effect = window.effect
            component = effect.component
            if component.get("kind") == "damage_modifier":
                self.active_dealt.append(window)
            elif effect.affects == "self":
                source = f"{effect.title} ({effect.name}) until {format_number(window.end)} s"
                label = weakest(window.labels)
                stat_id = str(component.get("stat"))
                if component.get("mode") == "flat":
                    amount = effect_amount(stat_id, window.value)
                    sheet = with_bonus(sheet, stat_id, amount, source, label)
                else:
                    sheet = with_amplifier(sheet, stat_id, window.value, source, label)
            else:
                damage_type = RESISTANCE_STATS[str(component.get("stat"))]
                self.shred.setdefault(damage_type, []).append(window)
        if sheet is not self.sheet:
            self.sheet = sheet
            self.stats, self.origin = sheet_stats(sheet)

    def _open(
        self,
        trigger: str,
        clock: Fraction,
        target_stats: Mapping[str, Fraction],
        slot: str | None = None,
    ) -> bool:
        """(Re)start the timed effects of ``trigger``; True when one starts on a hit."""
        uncertain = False
        for effect in self.timed:
            if effect.trigger != trigger:
                continue
            if not _conditions_hold(effect, self.target, "trigger", False, target_stats, slot):
                continue
            if effect.cooldown is not None:
                if clock < self.timed_ready.get(effect.title, Fraction(0)):
                    continue
                self.timed_ready[effect.title] = clock + effect.cooldown
            assert effect.duration is not None
            value, labels = self._value(effect, target_stats)
            self.windows[effect.title] = _Window(
                effect, clock + effect.duration, value, (effect.label, *labels)
            )
            if effect.component.get("kind") == "stat_modifier" and effect.affects == "self":
                self.speed_changed |= str(effect.component.get("stat")) in ATTACK_SPEED_STATS
            if trigger in UNCERTAIN_START_TRIGGERS:
                uncertain = True
                self.notes.append(
                    f"{effect.title}: starts after the hit that triggers it; whether that hit "
                    "benefits is not verified"
                )
        return uncertain

    def _refund(self, clock: Fraction, crit: bool) -> None:
        """An attack hit shortens the cooldowns that attacks reduce (Yun Tal's Flurry)."""
        for effect in self.timed:
            ready = self.timed_ready.get(effect.title)
            if effect.refund is None or ready is None or ready <= clock:
                continue
            seconds = effect.refund[1] if crit else effect.refund[0]
            self.timed_ready[effect.title] = max(clock, ready - seconds)

    def _accrue(self, until: Fraction, health: Fraction) -> tuple[list[Part], Fraction]:
        """Burn damage from the last count to ``until``, split where an effect ends.

        Burns deal their damage per second continuously (burns.md); each piece
        uses the timed effects in force during it.
        """
        start = self.accrued
        if until <= start or not self.burning:
            self.accrued = max(start, until)
            return [], health
        ends = {
            end
            for end in [
                *(burn.end for burn in self.burning.values()),
                *(window.end for window in self.windows.values()),
            ]
            if start < end < until
        }
        points = sorted({start, until, *ends})
        parts: list[Part] = []
        for begin, finish in zip(points, points[1:], strict=False):
            self._set_moment(begin)
            target_stats = self._target_stats(health)
            for burn in self.burning.values():
                if burn.end <= begin:
                    continue
                effect = burn.effect
                labels = list(burn.labels)
                notes: tuple[str, ...] = ()
                if self._percent(effect, target_stats) != burn.per_second:
                    labels.append(Label.PENDING)
                    notes = (
                        "its damage per second is the one when it was applied; the stats have "
                        "changed since, and whether the game updates it is not verified",
                    )
                part = self._part(
                    "burn",
                    f"{effect.title} ({effect.name}) from {format_number(begin)} s to "
                    f"{format_number(finish)} s",
                    DamageType(str(effect.component.get("damage_type"))),
                    burn.per_second * (finish - begin),
                    labels,
                    False,
                    target_stats,
                    notes,
                )
                parts.append(part)
                health = max(Fraction(0), health - part.damage)
        self.accrued = until
        self.burning = {key: burn for key, burn in self.burning.items() if burn.end > until}
        return parts, health

    def _timeline(self) -> Timeline:
        """Attack interval (1 / attack speed) and the checks the timeline needs."""
        try:
            attack_speed = self.sheet["attack_speed"].total()
        except StatBlocked as exc:
            raise RotationError(f"the timeline needs the attack speed: {exc}") from exc
        cooldowns = ability_cooldowns(self.sheet)
        if cooldowns.blocked is not None:
            raise RotationError(f"the timeline needs the cooldowns: {cooldowns.blocked}")
        self.cooldowns = {spell.slot: spell.effective for spell in cooldowns.spells}
        return Timeline(
            1 / attack_speed,
            weakest([self.sheet["attack_speed"].label, cooldowns.label]),
            (
                "timeline: abilities are instant and attacks land when they start; cast "
                "times, attack windups and projectile travel are not modelled (no data)",
            ),
        )

    def _spellblade_cooldown(self) -> Fraction:
        """The Spellblade item's cooldown from the catalog (1.5 s for every item today)."""
        for item in self.sheet.items:
            for effect in item.effects:
                if (effect.get("trigger") or {}).get("event") == "spellblade" and isinstance(
                    effect.get("cooldown_seconds"), (int, float)
                ):
                    return Fraction(str(effect["cooldown_seconds"]))
        raise RotationError("the Spellblade item declares no cooldown")

    def _spellblade_window(self) -> Fraction | None:
        """How long a Spellblade charge lasts (``duration_seconds``, 10 s from the wiki)."""
        for item in self.sheet.items:
            for effect in item.effects:
                if (effect.get("trigger") or {}).get("event") == "spellblade":
                    window = _duration(effect)
                    if window is not None:
                        return window
        return None

    def _cast(
        self,
        step: Step,
        clock: Fraction,
        ready: dict[str, Fraction],
        open_casts: dict[str, Fraction],
    ) -> None:
        """Check a cast against the cooldown and recast rules of the timeline."""
        assert step.slot is not None
        ability = self.kit.ability(step.slot)
        case = ability.case(step.case) if step.case is not None else ability.cases[0]
        if case.recast:
            opened = open_casts.pop(step.slot, None)
            if opened is None:
                raise RotationError(f"step {step.text}: {step.slot} has not been cast to recast it")
            window = ability.recast_window
            if window is not None and clock - opened > window:
                raise RotationError(
                    f"step {step.text}: the recast window ({format_number(window)} s) closed at "
                    f"{format_number(opened + window)} s"
                )
            return
        until = ready.get(step.slot, Fraction(0))
        if clock < until:
            raise RotationError(
                f"step {step.text}: {step.slot} is on cooldown until {format_number(until)} s "
                f"(now {format_number(clock)} s)"
            )
        ready[step.slot] = clock + self.cooldowns[step.slot][self.ranks[step.slot] - 1]
        open_casts[step.slot] = clock

    def _execute(
        self, parts: Sequence[Part], health: Fraction, target_stats: Mapping[str, Fraction]
    ) -> list[Part]:
        """An execute: the target's remaining health as true damage (execute.md)."""
        left = health - sum((part.damage for part in parts), start=Fraction(0))
        for effect in self.executes:
            if left <= 0 or not parts:
                return []
            if not _conditions_hold(effect, self.target, "execute", False, target_stats):
                continue
            threshold = self._percent(effect, target_stats) / 100
            if left < threshold * target_stats["max_health"]:
                return [
                    Part(
                        "execute",
                        f"{effect.title} ({effect.name})",
                        DamageType.TRUE,
                        left,
                        mitigate(left, DamageType.TRUE),
                        (),
                        (),
                        effect.label,
                    )
                ]
        return []

    def _counted(
        self,
        step: Step,
        target_stats: Mapping[str, Fraction],
        counters: dict[str, int],
        clock: Fraction | None = None,
        extra: list[Label] | None = None,
    ) -> list[Part]:
        """Effects on every Nth attack: count this attack and fire those that reach N.

        With the timeline (``clock``), a counter with a stack window loses its
        stacks when this attack comes the window or later after the last one.
        """
        parts: list[Part] = []
        for effect in [*self.counted, *self.counted_repeats]:
            if clock is not None and effect.window is not None:
                last = self.last_counted.get(effect.title)
                if counters[effect.title] and last is not None and clock - last >= effect.window:
                    count = counters[effect.title]
                    self.notes.append(
                        f"{effect.title}: {count} stack{'' if count == 1 else 's'} expired "
                        f"({format_number(effect.window)} s after the attack at "
                        f"{format_number(last)} s)"
                    )
                    counters[effect.title] = 0
                    if extra is not None:
                        extra.append(Label.PENDING)
                self.last_counted[effect.title] = clock
            counters[effect.title] += 1
            if counters[effect.title] < (effect.every or 0):
                continue
            counters[effect.title] = 0
            if effect.component.get("kind") == "repeat_on_hit":
                parts += self._on_hit(
                    self.on_hit, step, target_stats, f" - again by {effect.title}", effect.label
                )
            else:
                parts += self._on_hit([effect], step, target_stats)
        return parts

    def _on_hit(
        self,
        effects: Sequence[_Effect],
        step: Step,
        target_stats: Mapping[str, Fraction],
        suffix: str = "",
        extra: Label | None = None,
    ) -> list[Part]:
        parts = []
        for effect in effects:
            if not _conditions_hold(effect, self.target, "on_hit", step.crit):
                continue
            value, stat_labels = self._value(effect, target_stats)
            value = self._limited(effect, value)
            damage_type = DamageType(str(effect.component.get("damage_type")))
            labels = [effect.label, *stat_labels]
            if extra is not None:
                labels.append(extra)
            parts.append(
                self._part(
                    "on_hit",
                    f"{effect.title} ({effect.name}){suffix}",
                    damage_type,
                    value,
                    labels,
                    step.crit,
                    target_stats,
                    life_steal_tag=effect.component.get("applies_life_steal"),
                )
            )
        return parts

    def _limited(self, effect: _Effect, value: Fraction) -> Fraction:
        for limit in effect.limits:
            condition = str(limit.get("condition"))
            kinds = LIMIT_CONDITIONS.get(condition)
            if kinds is None or limit.get("kind") != "maximum" or limit.get("unit") != "flat":
                raise RotationError(f"{effect.title}: limit {condition!r} is not modelled")
            if _target_kind(self.target, f"{effect.title} limit") in kinds:
                value = min(value, Fraction(str(limit["value"])))
        return value

    def _ability(self, step: Step, target_stats: Mapping[str, Fraction]) -> tuple[str, list[Part]]:
        assert step.slot is not None
        ability = self.kit.ability(step.slot)
        if step.slot not in self.ranks:
            raise RotationError(f"step {step.text}: learn {step.slot} first with --learned")
        if step.case is None and len(ability.cases) > 1:
            names = ", ".join(f"{step.slot}.{case.id}" for case in ability.cases)
            raise RotationError(f"step {step.text}: pick one case ({names})")
        rank = self.ranks[step.slot]
        try:
            raw_parts = ability_damage(
                self.kit,
                step.slot,
                rank,
                self.sheet,
                case=step.case,
                target=target_stats,
                inputs=self.inputs,
            )
        except KitError as exc:
            raise RotationError(f"step {step.text}: {exc}") from exc
        notes = tuple(f"{ability.slot}: {note}" for note in ability.not_modelled)
        parts = [
            self._part(
                "ability",
                f"{ability.slot}.{part.case}[{part.index}] {part.source}",
                part.damage_type,
                part.raw,
                [part.label],
                False,
                target_stats,
                notes,
            )
            for part in raw_parts
        ]
        return f"{ability.slot} {ability.name} rank {rank}", parts

    def _burn_outcome(
        self, index: int, step: Step, name: str, clock: Fraction, health: Fraction
    ) -> StepOutcome:
        """A step with no damage of its own: the burn damage up to ``clock``."""
        parts, left = self._accrue(clock, health)
        if parts:
            parts += self._execute(parts, health, self._target_stats(left))
        return StepOutcome(
            index,
            step,
            name,
            tuple(parts),
            health,
            weakest(part.label for part in parts),
            clock,
        )

    def run(self, steps: Sequence[Step]) -> RotationOutcome:
        if "max_health" not in self.target.stats:
            raise RotationError(
                "a rotation tracks the target's health; give --target-max-health "
                "or --target-champion"
            )
        if self.holder_range is not None and self.holder_range not in HOLDER_RANGES:
            raise RotationError(f"attacker range must be melee or ranged, not {self.holder_range}")
        start = self.target.stats["current_health"]
        health = start
        outcomes = []
        # Spellblade: an ability charges the next attack; that attack uses the charge
        # (or drops it with attack:nospellblade). Its cooldown is taken as ready.
        charged = False
        charged_at = Fraction(0)  # when the charge was made, for its window (timeline)
        window = self._spellblade_window() if self.timeline is not None else None
        # Attack counters start at zero; Energized starts ready (attack-counters.md).
        counters = {effect.title: 0 for effect in [*self.counted, *self.counted_repeats]}
        energized = bool(self.energized)
        burned: set[str] = set()  # one full burn per effect and rotation (burns.md)
        clock, next_attack = Fraction(0), Fraction(0)
        spellblade_ready = Fraction(0)  # its cooldown, with the timeline
        ready: dict[str, Fraction] = {}
        open_casts: dict[str, Fraction] = {}
        for index, step in enumerate(steps, start=1):
            if step.wait is not None:
                if self.timeline is None:
                    raise RotationError(f"step {step.text}: waits need the timeline (--timeline)")
                outcomes.append(self._burn_outcome(index, step, "wait", clock, health))
                health = outcomes[-1].health_after
                clock += step.wait
                continue
            if self.timeline is not None and step.slot is None:
                clock = max(clock, next_attack)
            elif self.timeline is not None:
                self._cast(step, clock, ready, open_casts)
            parts: list[Part] = []
            before = health
            if self.timeline is not None:
                parts, health = self._accrue(clock, health)
                self._set_moment(clock)
            target_stats = self._target_stats(health)
            extra: list[Label] = []
            if step.slot is None:
                if charged and window is not None and clock - charged_at > window:
                    charged = False
                    extra.append(Label.PENDING)
                    self.notes.append(
                        f"Spellblade: the charge from {format_number(charged_at)} s expired "
                        f"after {format_number(window)} s (LoL Wiki, secondary)"
                    )
                empowered = charged and step.spellblade and bool(self.spellblade)
                charged = False
                name = "critical basic attack" if step.crit else "basic attack"
                if empowered:
                    name += " with Spellblade"
                parts += self._attack(step, target_stats, empowered)
                if empowered and self.timeline is not None:
                    spellblade_ready = clock + self._spellblade_cooldown()
                    if self._open("spellblade", clock, target_stats):
                        extra.append(Label.PENDING)
                timed = self.timeline is not None
                parts += self._counted(
                    step, target_stats, counters, clock if timed else None, extra
                )
                if timed:
                    self._open("on_attack", clock, target_stats)
                    self._refund(clock, step.crit)
                if energized:
                    energized = False
                    name += " (Energized)"
                    parts += self._on_hit(self.energized, step, target_stats)
                    if self._open("energized", clock, target_stats):
                        extra.append(Label.PENDING)
            else:
                name, ability_parts = self._ability(step, target_stats)
                parts += ability_parts
                # An ability cast while Spellblade is on cooldown does not charge it.
                if self.timeline is None or clock >= spellblade_ready:
                    charged, charged_at = True, clock
                parts += self._burns(step, ability_parts, target_stats, burned, clock)
                if ability_parts and self.timeline is not None:
                    self._open("damaging_ability", clock, target_stats, step.slot)
                if (
                    energized
                    and self.galvanize
                    and ability_parts
                    and self.target.kind == "champion"
                ):
                    energized = False
                    name += " (Energized)"
                    parts += self._on_hit(self.energized, step, target_stats)
                    self.notes.append(
                        f"{self.galvanize[0].title}: the ability's damage to a champion "
                        "triggered Energized"
                    )
                    if self.timeline is not None and self._open("energized", clock, target_stats):
                        extra.append(Label.PENDING)
            parts += self._execute(parts, before, target_stats)
            outcome = StepOutcome(
                index,
                step,
                name,
                tuple(parts),
                before,
                weakest([*(part.label for part in parts), *extra]),
                None if self.timeline is None else clock,
            )
            outcomes.append(outcome)
            health = outcome.health_after
            if self.timeline is not None and step.slot is None:
                # The next attack: 1 / the attack speed just after this one (timeline.md).
                self._set_moment(clock)
                next_attack = clock + 1 / self.sheet["attack_speed"].total()
        if self.burning:
            end = max(burn.end for burn in self.burning.values())
            outcomes.append(
                self._burn_outcome(
                    len(steps) + 1,
                    Step("burns"),
                    f"burns until {format_number(end)} s",
                    end,
                    health,
                )
            )
        if self.energized:
            self.notes.append(
                "Energized starts ready and fires once; recharging by moving and attacking "
                "is not modelled"
            )
        if counters and self.timeline is None:
            self.notes.append("attack counters ignore their time windows (stacks expiring)")
        elif counters:
            self.notes += [
                f"{effect.title}: no stack window declared; its count does not expire"
                for effect in [*self.counted, *self.counted_repeats]
                if effect.window is None
            ]
            if any(effect.window is not None for effect in [*self.counted, *self.counted_repeats]):
                self.notes.append(
                    "timeline: a counter's stacks expire when an attack comes its window or later "
                    "after the previous one; every attack renews them (timeline.md)"
                )
        if self.speed_changed:
            self.notes.append(
                "timeline: the time to the next attack uses the attack speed just after each "
                "attack; whether the game recomputes it when the attack speed changes before "
                "the next attack is not verified"
            )
            self.weakened = True
        if self.timeline is not None:
            self.notes += self.timeline.notes
            if self.burns:
                self.notes.append(
                    "timeline: a burn deals its damage per second continuously from the step "
                    "that applies it until it ends; applying it again restarts its duration, and "
                    "damage after the last step is counted (burns.md)"
                )
            if self.timed:
                self.notes.append(
                    "timeline: a timed effect starts after the damage of the step that triggers "
                    "it and lasts its duration; triggering it again restarts it (timeline.md)"
                )
        notes = list(dict.fromkeys(self.notes))
        passive = self.kit.abilities.get("P")
        if passive is not None and passive.not_modelled:
            notes += [f"P: {note}" for note in passive.not_modelled]
        labels = [self.target.label, *(step.label for step in outcomes)]
        if self.weakened:
            labels.append(Label.PENDING)
        return RotationOutcome(
            tuple(outcomes),
            self.target.stats["max_health"],
            start,
            self.holder_range,
            weakest(labels),
            tuple(notes),
            self.timeline,
        )


def evaluate_rotation(
    kit: Kit,
    sheet: StatSheet,
    ranks: Mapping[str, int],
    target: Target,
    steps: Sequence[Step],
    crit_base: CritBase | None,
    *,
    holder_range: str | None = None,
    inputs: Mapping[str, Any] | None = None,
    timeline: bool = False,
) -> RotationOutcome:
    """Damage of every step against ``target``, carrying its current health forward.

    ``holder_range`` is the attacker's melee/ranged classification; it is only
    required by effects that branch on it and is never guessed. ``crit_base``
    is only required by critical steps. With ``timeline`` every step gets a time:
    attacks are spaced by 1 / attack speed, cooldowns and recast windows are
    enforced and ``wait:<seconds>`` steps advance the clock (timeline.md).
    """
    if not steps:
        raise RotationError("the rotation has no steps")
    rotation = _Rotation(kit, sheet, ranks, target, crit_base, holder_range, inputs or {}, timeline)
    return rotation.run(steps)
