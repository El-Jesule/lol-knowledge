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

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from fractions import Fraction
from typing import Any

from .damage import DamageResult, DamageType, format_number, mitigate
from .errors import KitError, RotationError, StatsError
from .formula import FormulaError, evaluate_formula
from .kit import Kit, ability_damage, sheet_stats
from .passives import PassiveCombat
from .resources import (
    ResourceEvent,
    ResourceSummary,
    ResourceTracker,
    StepResourceCost,
    resolve_ability_cost,
)
from .rune_combat import RuneCombat
from .runes import RuneData, fraction_input, int_input
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
from .survival import (
    GRIEVOUS_WOUNDS_REDUCTION,
    HealEvent,
    ShieldEvent,
    absorb_shield,
    scale_healing,
    scale_shield,
)

RULES = (
    "lol-knowledge/mechanics/basic-attacks-and-on-hit.md",
    "lol-knowledge/mechanics/critical-strike.md",
    "lol-knowledge/mechanics/damage-modifiers.md",
    "lol-knowledge/mechanics/damage-mitigation.md",
    "lol-knowledge/mechanics/stat-growth.md",
    "lol-knowledge/mechanics/life-steal-and-omnivamp.md",
    "lol-knowledge/mechanics/survival.md",
    "lol-knowledge/mechanics/resources.md",
    "lol-knowledge/mechanics/passives.md",
)
HOLDER_RANGES = frozenset({"melee", "ranged"})
ATTACK_MODIFIERS = frozenset({"crit", "nospellblade"})
# Triggers whose ``stacks.required`` counts basic attacks (attack-counters.md).
COUNTED_TRIGGERS = frozenset({"on_hit", "on_attack"})
# A burn starts when an ability deals damage, is cast, or on any damaging hit (burns.md).
BURN_TRIGGERS = frozenset({"damaging_ability", "cast", "on_damage"})
# Base critical strike multiplier of the patch notes (26.1); records that differ are flagged.
PATCH_CRIT_MULTIPLIER = Fraction(2)
# Passives that reduce total critical strike damage: "Critical Strike Damage Reduction:
# -10% => -5%" for Yasuo and Yone in 26.17 (critical-strike.md, C10) and -25% for Jhin
# (JhinPassive.DataValues.CritReductionPercent = 0.25).
CRIT_DAMAGE_REDUCTIONS = {
    "Yasuo": Fraction(5, 100),
    "Yone": Fraction(5, 100),
    "Jhin": Fraction(25, 100),
}
# Limit conditions of the catalog, as the target kinds they apply to.
LIMIT_CONDITIONS = {
    "target is a minion or monster": frozenset({"minion", "monster"}),
    "target is a monster": frozenset({"monster"}),
}
# Effect components that change the damage of a rotation when not applied.
DAMAGE_KINDS = frozenset(
    {"damage", "damage_modifier", "stat_modifier", "burn", "execute", "repeat_on_hit"}
)

# Effects that last a while once triggered; only the timeline applies them (timeline.md).
TIMED_KINDS = frozenset({"damage_modifier", "stat_modifier"})
TIMED_TRIGGERS = frozenset({"spellblade", "energized", "damaging_ability", "on_attack", "cast"})
# Triggers on a hit: whether that hit benefits from its own effect is not verified.
UNCERTAIN_START_TRIGGERS = frozenset({"spellblade", "energized"})
# Target resistances a timed effect can reduce, by the damage type they mitigate.
RESISTANCE_STATS = {"armor": DamageType.PHYSICAL, "magic_resist": DamageType.MAGIC}
# Stats whose timed change moves the attack timer.
ATTACK_SPEED_STATS = frozenset({"attack_speed", "attack_speed_bonus"})

# Kinds against which omnivamp drops to 33 % for pets, damage over time and area spells.
REDUCED_OMNIVAMP_KINDS = frozenset({"minion", "monster"})

WAIT_SECONDS = re.compile(r"\d+(?:\.\d+)?")
_ABILITY_STEP = re.compile(r"(?P<slot>[QWER])(?:\.(?P<case>[a-z0-9_]+))?(?:@(?P<targets>\d+))?")


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
    # Explicit target count override for an ability step (e.g. ``R.dash@3``).
    targets: int | None = None


def parse_steps(text: str) -> tuple[Step, ...]:
    """Read ``attack``, ``attack:crit``, ``attack:nospellblade``, ``Q``, ``E.edge``, ``R.dash@3``…

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
        raw_targets = match.group("targets")
        step_targets: int | None = None
        if raw_targets is not None:
            step_targets = int(raw_targets)
            if step_targets < 1:
                raise RotationError(f"step {token!r}: target count must be at least 1")
        steps.append(Step(token, match.group("slot"), match.group("case"), targets=step_targets))
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
    kind: str  # "attack", "on_hit", "ability", "burn", "rune", "item" or "execute"
    source: str
    damage_type: DamageType
    raw: Fraction
    mitigation: DamageResult
    dealt: tuple[tuple[str, Fraction], ...]  # (effect, percent) applied
    taken: tuple[tuple[str, Fraction], ...]
    label: Label
    notes: tuple[str, ...] = ()
    healing: Healing = NO_HEALING
    targets_hit: int = 1
    secondary_damage_ratio: Fraction = Fraction(1)
    aoe: bool | None = None
    hits_primary: bool = True

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
    def primary_damage(self) -> Fraction:
        """Post-mitigation and post-modifier damage dealt to the primary target."""
        if not self.hits_primary:
            return Fraction(0)
        return self.mitigation.damage * self.dealt_factor * self.taken_factor

    @property
    def secondary_damage(self) -> Fraction:
        """Total post-mitigation and post-modifier damage dealt to secondary targets."""
        unit = self.mitigation.damage * self.dealt_factor * self.taken_factor
        if not self.hits_primary:
            return unit * self.targets_hit * self.secondary_damage_ratio
        return unit * (self.targets_hit - 1) * self.secondary_damage_ratio

    @property
    def damage(self) -> Fraction:
        """Total damage dealt by this part across all targets hit."""
        return self.primary_damage + self.secondary_damage


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
    shield_before: Fraction = Fraction(0)
    shield_absorbed: Fraction = Fraction(0)
    heal_events: tuple[HealEvent, ...] = ()
    shield_events: tuple[ShieldEvent, ...] = ()
    resource_cost: StepResourceCost | None = None
    resource_before: Fraction | None = None
    resource_after: Fraction | None = None
    resource_events: tuple[ResourceEvent, ...] = ()

    @property
    def primary_total(self) -> Fraction:
        return sum((part.primary_damage for part in self.parts), start=Fraction(0))

    @property
    def secondary_total(self) -> Fraction:
        return sum((part.secondary_damage for part in self.parts), start=Fraction(0))

    @property
    def targets_hit(self) -> int:
        return max((part.targets_hit for part in self.parts), default=1)

    @property
    def total(self) -> Fraction:
        return sum((part.damage for part in self.parts), start=Fraction(0))

    @property
    def shield_after(self) -> Fraction:
        return self.shield_before - self.shield_absorbed

    @property
    def health_damage(self) -> Fraction:
        return self.primary_total - self.shield_absorbed

    @property
    def health_after(self) -> Fraction:
        return max(Fraction(0), self.health_before - self.health_damage)

    @property
    def overkill(self) -> bool:
        """Whether the step deals more damage to health than the target had left."""
        return self.health_damage > self.health_before

    @property
    def healing(self) -> Fraction:
        vamp = sum((part.healing.amount for part in self.parts), start=Fraction(0))
        direct = sum((event.amount for event in self.heal_events), start=Fraction(0))
        return vamp + direct

    @property
    def healing_label(self) -> Label:
        labels = [part.healing.label for part in self.parts] + [
            event.label for event in self.heal_events
        ]
        if self.overkill and any(part.healing.amount for part in self.parts):
            labels.append(Label.PENDING)
        return weakest(labels)

    @property
    def healing_notes(self) -> tuple[str, ...]:
        if self.overkill and any(part.healing.amount for part in self.parts):
            return (
                "the step deals more damage than the target's remaining health; healing uses "
                "the full damage, which is not verified",
            )
        return ()

    @property
    def shield_granted(self) -> Fraction:
        return sum((event.amount for event in self.shield_events), start=Fraction(0))


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
    start_shield: Fraction = Fraction(0)
    shield_type: str = "normal"
    attacker_start_health: Fraction | None = None
    attacker_max_health: Fraction | None = None
    attacker_remaining_health: Fraction | None = None
    effective_healing: Fraction | None = None
    grievous_wounds_applied: bool = False
    resource: ResourceSummary | None = None
    target_count: int = 1

    @property
    def primary_total(self) -> Fraction:
        return sum((step.primary_total for step in self.steps), start=Fraction(0))

    @property
    def secondary_total(self) -> Fraction:
        return sum((step.secondary_total for step in self.steps), start=Fraction(0))

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
    def total_shield_absorbed(self) -> Fraction:
        return sum((step.shield_absorbed for step in self.steps), start=Fraction(0))

    @property
    def remaining_shield(self) -> Fraction:
        return self.start_shield - self.total_shield_absorbed

    @property
    def remaining_health(self) -> Fraction:
        return self.steps[-1].health_after if self.steps else self.start_health

    @property
    def healing(self) -> Fraction:
        return sum((step.healing for step in self.steps), start=Fraction(0))

    @property
    def healing_label(self) -> Label:
        return weakest(step.healing_label for step in self.steps)

    @property
    def total_shield_granted(self) -> Fraction:
        return sum((step.shield_granted for step in self.steps), start=Fraction(0))

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
    # Seconds stacks last after the last attack (``stacks.window_seconds``).
    window: Fraction | None = None
    # Stacks gained one per attack (``stacks.required`` 1): their maximum, and the
    # turn they take with other effects of a group (``alternation``).
    max_stacks: int | None = None
    alternation: tuple[str, int, int] | None = None
    # Combo hits required for ``on_damage`` triggers (e.g. Eclipse: 2 hits in 2 s).
    combo_required: int | None = None

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
                        _max_stacks(effect),
                        _alternation(effect),
                        _combo_required(effect),
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
    if not isinstance(stacks, Mapping):
        return None
    return _seconds_of(stacks.get("window_seconds"))


def _max_stacks(effect: Mapping[str, Any]) -> int | None:
    """The maximum of stacks gained one per attack (combat-stacks.md)."""
    stacks = effect.get("stacks")
    if not isinstance(stacks, Mapping) or stacks.get("required") != 1:
        return None
    value = stacks.get("max_stacks")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _alternation(effect: Mapping[str, Any]) -> tuple[str, int, int] | None:
    entry = effect.get("alternation")
    if not isinstance(entry, Mapping):
        return None
    return str(entry["group"]), int(entry["position"]), int(entry["of"])


def _key(effect: _Effect) -> str:
    """One stack count per effect component (an effect may change several stats)."""
    return f"{effect.title}:{effect.component.get('stat')}"


def _excluded(effect: _Effect, target_kind: str | None) -> bool:
    """Whether a condition of ``effect`` on the target kind rules out ``target_kind``."""
    return target_kind is not None and any(
        TARGET_KIND_CONDITIONS[condition] != target_kind
        for condition in effect.conditions
        if condition in TARGET_KIND_CONDITIONS
    )


def _combo_required(effect: Mapping[str, Any]) -> int | None:
    """``N`` for an ``on_damage`` combo proc (e.g. Eclipse: 2 hits in 2 s)."""
    if (effect.get("trigger") or {}).get("event") != "on_damage":
        return None
    stacks = effect.get("stacks")
    required = stacks.get("required") if isinstance(stacks, Mapping) else None
    if isinstance(required, int) and not isinstance(required, bool) and required >= 2:
        return required
    return None


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
        runes: Sequence[int] = (),
        rune_data: RuneData | None = None,
        has_ultimate_step: bool = False,
        ap_weight: Fraction | None = None,
        start_resource: Fraction | None = None,
        allow_insufficient_resource: bool = False,
        apply_passives: bool = True,
        target_count: int = 1,
    ) -> None:
        if isinstance(target_count, bool) or not isinstance(target_count, int) or target_count < 1:
            raise RotationError("target count must be an integer >= 1")
        self.kit, self.sheet, self.ranks, self.target = kit, sheet, ranks, target
        self.target_count = target_count
        self.base_sheet = sheet
        self.timeline = self._timeline() if timeline else None
        self.crit_base, self.holder_range, self.inputs = crit_base, holder_range, inputs
        self.stats, self.origin = sheet_stats(sheet)
        self.life_steal, self.omnivamp = sheet["life_steal"], sheet["omnivamp"]
        self.hsp = sheet["heal_and_shield_power"]
        try:
            gw_input = int_input(inputs, "grievous_wounds", minimum=0, maximum=1)
            atk_hp_pct = fraction_input(inputs, "attacker_health_percent")
        except StatsError as exc:
            raise RotationError(str(exc)) from exc
        self.grievous_permanent = GRIEVOUS_WOUNDS_REDUCTION if gw_input == 1 else Fraction(0)
        self.grievous_timed_rate = Fraction(0)
        self.grievous_timed_until: Fraction | None = None
        self.grievous_timed_source = ""
        self.grievous_timed_label = Label.DERIVED
        self.grievous_used = gw_input == 1
        self.attacker_max_hp: Fraction | None = None
        self.attacker_start_hp: Fraction | None = None
        self.attacker_hp: Fraction | None = None
        self.effective_healing_total: Fraction | None = None
        if atk_hp_pct is not None:
            try:
                max_hp = sheet["health"].total()
            except StatBlocked as exc:
                raise RotationError(
                    f"attacker_health_percent needs attacker health: {exc}"
                ) from exc
            self.attacker_max_hp = max_hp
            self.attacker_start_hp = max_hp * atk_hp_pct
            self.attacker_hp = self.attacker_start_hp
            self.effective_healing_total = Fraction(0)
        self.item_heals: list[_Effect] = []
        self.item_shields: list[_Effect] = []
        self.item_resource_restores: list[_Effect] = []
        self.defender_grievous: list[_Effect] = []
        attacker, notes, weakened = _effects(sheet.items, "attacker", target.kind)
        defender, target_notes, target_weakened = _effects(target.items, "target")
        self.rune_combat = RuneCombat(
            runes,
            rune_data,
            sheet,
            target,
            has_ultimate_step=has_ultimate_step,
            holder_range=holder_range,
            inputs=inputs,
            timeline=timeline,
            ap_weight=ap_weight,
        )
        self.resources = ResourceTracker(
            sheet,
            inputs,
            start_resource=start_resource,
            timeline=timeline,
            allow_insufficient=allow_insufficient_resource,
            manaflow_regen=self.rune_combat.manaflow_band_config(sheet),
        )
        self.passive_combat = PassiveCombat(
            kit,
            target,
            inputs,
            timeline=timeline,
            enabled=apply_passives,
        )
        self.notes = (
            notes
            + target_notes
            + list(sheet.pending_effects)
            + self.rune_combat.notes
            + list(self.resources.notes)
        )
        self.weakened = (
            weakened
            or target_weakened
            or bool(sheet.pending_effects)
            or self.rune_combat.weakened
            or self.resources.weakened
        )
        self.on_hit: list[_Effect] = []
        self.secondary_attacks: list[_Effect] = []
        self.ability_procs: list[_Effect] = []
        self.on_damage_procs: list[_Effect] = []
        self.ability_stacked: list[_Effect] = []
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
        self.proc_ready: dict[str, Fraction] = {}  # cooldowns of ability/on_damage procs
        self.proc_fired: set[str] = set()  # non-timeline one-shot cooldown procs
        self.combo_hits: dict[str, list[Fraction]] = {}  # timeline on_damage combo hits
        self.combo_counts: dict[str, int] = {}  # non-timeline on_damage combo hits
        self.ability_stacks: dict[str, int] = {}  # stacks gained per damaging ability (Shojin)
        self.ability_stacked_at: dict[str, Fraction] = {}
        self.last_counted: dict[str, Fraction] = {}  # last attack of each counter
        self.speed_changed = False  # a timed effect changed the attack speed
        # Stacks gained per attack and seconds in combat, from 0 (combat-stacks.md).
        self.stacked: list[_Effect] = []
        self.combat: list[_Effect] = []
        self.stacks: dict[str, int] = {}
        self.stacked_at: dict[str, Fraction] = {}  # the last attack that added a stack
        self.turns: dict[str, int] = {}  # attacks taken by each alternation group
        self.now = Fraction(0)
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
            elif (
                effect.trigger in {"on_attack", "on_hit"}
                and kind == "damage"
                and effect.component.get("secondary_only") is True
            ):
                self.secondary_attacks.append(effect)
            elif effect.trigger == "on_hit" and kind == "damage":
                self.on_hit.append(effect)
            elif effect.trigger == "damaging_ability" and kind == "damage":
                self.ability_procs.append(effect)
            elif (
                effect.trigger == "damaging_ability"
                and kind == "damage_modifier"
                and effect.max_stacks is not None
            ):
                self._ability_stacking(effect)
            elif effect.trigger == "on_damage" and kind in {"damage", "shield"}:
                self.on_damage_procs.append(effect)
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
            elif effect.trigger == "on_attack" and effect.max_stacks is not None:
                self._stacking(effect)
            elif effect.trigger == "in_combat":
                self._in_combat(effect)
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
                kind == "healing"
                and effect.component.get("mode") == "absolute"
                and effect.affects == "self"
                and effect.trigger in {"spellblade", "on_hit", "damaging_ability", "cast"}
            ):
                self.item_heals.append(effect)
            elif (
                kind == "shield"
                and effect.component.get("mode") == "absolute"
                and effect.affects == "self"
                and effect.trigger in {"spellblade", "on_hit", "damaging_ability", "cast"}
            ):
                self.item_shields.append(effect)
            elif (
                kind == "resource_restore"
                and ((effect.component.get("target") or {}).get("kind") or effect.affects) == "self"
                and effect.trigger in {"spellblade", "on_hit", "damaging_ability", "cast"}
            ):
                self.item_resource_restores.append(effect)
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
            elif (
                effect.trigger == "taking_attack"
                and kind == "status"
                and effect.component.get("effect") == "grievous_wounds"
            ):
                self.defender_grievous.append(effect)
            else:
                self._skip(effect, f"{effect.trigger} {kind}", owner="target")

    def _current_grievous(self, clock: Fraction) -> tuple[Fraction, Label, str]:
        """Active Grievous Wounds reduction (0 or 0.4, non-stacking) at ``clock``."""
        rate = self.grievous_permanent
        label = Label.DERIVED
        source = "Grievous Wounds (-40%, scenario)" if rate else ""
        timed_active = self.grievous_timed_rate > 0 and (
            self.timeline is None
            or self.grievous_timed_until is None
            or clock < self.grievous_timed_until
        )
        if timed_active and self.grievous_timed_rate >= rate:
            rate = self.grievous_timed_rate
            label = self.grievous_timed_label
            source = self.grievous_timed_source
        return rate, label, source

    def _trigger_defender_grievous(self, clock: Fraction) -> None:
        """Apply Grievous Wounds from defender's taking_attack items (Thornmail, rev 4025130)."""
        for effect in self.defender_grievous:
            mag = effect.component.get("magnitude")
            pct = (
                Fraction(str(mag["value"]))
                if isinstance(mag, Mapping) and mag.get("op") == "constant"
                else Fraction(40)
            )
            rate = pct / 100
            dur = _seconds_of(effect.component.get("duration_seconds"))
            if rate >= self.grievous_timed_rate:
                self.grievous_timed_rate = rate
                self.grievous_timed_label = effect.label
                self.grievous_timed_source = (
                    f"Grievous Wounds (-{format_number(pct)}% from target {effect.title})"
                )
            if self.timeline is not None and dur is not None:
                until = clock + dur
                self.grievous_timed_until = (
                    until
                    if self.grievous_timed_until is None
                    else max(self.grievous_timed_until, until)
                )
            self.grievous_used = True

    def _revitalize_amp(self) -> Fraction:
        """Revitalize's extra +10% healing/shielding below 40% attacker HP."""
        if self.attacker_hp is None or self.attacker_max_hp is None or self.attacker_max_hp <= 0:
            return Fraction(0)
        return self.rune_combat.revitalize_low_hp_amp(self.attacker_hp / self.attacker_max_hp)

    def _make_heal_event(
        self,
        source: str,
        raw: Fraction,
        label: Label,
        clock: Fraction,
        *,
        uses_hsp: bool = True,
        notes: tuple[str, ...] = (),
    ) -> HealEvent:
        hsp_val = self.hsp.total() if uses_hsp else Fraction(0)
        rev_amp = self._revitalize_amp()
        gw_rate, gw_label, gw_source = self._current_grievous(clock)
        amount = scale_healing(
            raw, hsp=hsp_val, revitalize_amp=rev_amp, grievous=gw_rate, uses_hsp=uses_hsp
        )
        labels = [label]
        out_notes = list(notes)
        if uses_hsp and hsp_val:
            labels.append(self.hsp.label)
            out_notes.append(f"heal & shield power +{format_number(hsp_val * 100)}%")
        if rev_amp:
            labels.append(Label.DERIVED)
            out_notes.append(f"Revitalize <40% HP +{format_number(rev_amp * 100)}%")
        if gw_rate:
            labels.append(gw_label)
            out_notes.append(gw_source)
            self.grievous_used = True
        return HealEvent(
            source,
            raw,
            amount,
            uses_hsp,
            gw_rate > 0,
            weakest(labels),
            tuple(out_notes),
        )

    def _make_shield_event(
        self,
        source: str,
        raw: Fraction,
        label: Label,
        *,
        shield_type: str = "normal",
        duration: Fraction | None = None,
        notes: tuple[str, ...] = (),
    ) -> ShieldEvent:
        hsp_val = self.hsp.total()
        rev_amp = self._revitalize_amp()
        amount = scale_shield(raw, hsp=hsp_val, revitalize_amp=rev_amp)
        labels = [label]
        out_notes = list(notes)
        if hsp_val:
            labels.append(self.hsp.label)
            out_notes.append(f"heal & shield power +{format_number(hsp_val * 100)}%")
        if rev_amp:
            labels.append(Label.DERIVED)
            out_notes.append(f"Revitalize <40% HP +{format_number(rev_amp * 100)}%")
        return ShieldEvent(
            source,
            raw,
            amount,
            shield_type,
            duration,
            weakest(labels),
            tuple(out_notes),
        )

    def _item_survival_events(
        self, trigger: str, target_stats: Mapping[str, Fraction], clock: Fraction
    ) -> tuple[list[HealEvent], list[ShieldEvent]]:
        heals: list[HealEvent] = []
        shields: list[ShieldEvent] = []
        for effect in self.item_heals:
            if effect.trigger != trigger:
                continue
            if not _conditions_hold(effect, self.target, "healing", False, target_stats):
                continue
            raw, stat_labels = self._value(effect, target_stats)
            heals.append(
                self._make_heal_event(
                    f"{effect.title} ({effect.name})",
                    raw,
                    weakest([effect.label, *stat_labels]),
                    clock,
                )
            )
        for effect in self.item_shields:
            if effect.trigger != trigger:
                continue
            if not _conditions_hold(effect, self.target, "shield", False, target_stats):
                continue
            raw, stat_labels = self._value(effect, target_stats)
            shields.append(
                self._make_shield_event(
                    f"{effect.title} ({effect.name})",
                    raw,
                    weakest([effect.label, *stat_labels]),
                    duration=effect.duration,
                )
            )
        return heals, shields

    def _item_resource_restores(
        self, trigger: str, target_stats: Mapping[str, Fraction]
    ) -> list[ResourceEvent]:
        events: list[ResourceEvent] = []
        part_kind = "on_hit" if trigger in {"spellblade", "on_hit"} else "trigger"
        for effect in self.item_resource_restores:
            if effect.trigger != trigger:
                continue
            if not _conditions_hold(effect, self.target, part_kind, False, target_stats):
                continue
            raw, stat_labels = self._value(effect, target_stats)
            resource = str(effect.component.get("resource", "mana"))
            ev = self.resources.restore(
                f"{effect.title} ({effect.name})",
                resource,
                raw,
                weakest([effect.label, *stat_labels]),
            )
            if ev is not None:
                events.append(ev)
        return events

    def _ensure_attacker_hp(self) -> Fraction:
        if self.attacker_hp is None:
            try:
                max_hp = self.sheet["health"].total()
            except StatBlocked as exc:
                raise RotationError(f"health cost needs attacker health: {exc}") from exc
            self.attacker_max_hp = max_hp
            self.attacker_start_hp = max_hp
            self.attacker_hp = max_hp
            self.effective_healing_total = Fraction(0)
        return self.attacker_hp

    def _absorb_parts(
        self, parts: Sequence[Part], health: Fraction, shield: Fraction
    ) -> tuple[Fraction, Fraction, Fraction]:
        """Apply ``parts`` against ``shield`` then ``health`` (Shield rev 4093144)."""
        absorbed_total = Fraction(0)
        for part in parts:
            absorbed, hp_dmg = absorb_shield(
                part.primary_damage,
                part.damage_type,
                shield,
                self.target.shield_type,
                bypass_shield=part.kind == "execute",
            )
            shield -= absorbed
            absorbed_total += absorbed
            health = max(Fraction(0), health - hp_dmg)
        return health, shield, absorbed_total

    def _record_attacker_healing(self, amount: Fraction) -> None:
        if self.attacker_hp is None or self.attacker_max_hp is None or amount <= 0:
            return
        missing = max(Fraction(0), self.attacker_max_hp - self.attacker_hp)
        gained = min(amount, missing)
        self.attacker_hp += gained
        assert self.effective_healing_total is not None
        self.effective_healing_total += gained

    def _skip(self, effect: _Effect, why: str, owner: str = "attacker") -> None:
        self.notes.append(f"{owner} {effect.title}: {why} is not part of rotations, not applied")
        if effect.component.get("kind") in DAMAGE_KINDS and owner == "attacker":
            self.weakened = True

    def _stacking(self, effect: _Effect) -> None:
        component = effect.component
        if (
            component.get("kind") != "stat_modifier"
            or effect.affects != "self"
            or component.get("mode") != "flat"
        ):
            raise RotationError(f"{effect.title}: only flat stats of the attacker stack per attack")
        self.stacked.append(effect)

    def _ability_stacking(self, effect: _Effect) -> None:
        component = effect.component
        if component.get("direction") != "dealt" or component.get("source") not in {
            "ability",
            "all",
        }:
            raise RotationError(
                f"{effect.title}: only dealt damage modifiers stack on damaging abilities"
            )
        self._mode(effect)
        self.ability_stacked.append(effect)

    def _ability_stack_expired(self, effect: _Effect, at: Fraction) -> bool:
        last = self.ability_stacked_at.get(effect.title)
        return (
            self.timeline is not None
            and effect.window is not None
            and last is not None
            and at - last >= effect.window
        )

    def _stack_ability(
        self, clock: Fraction, target_stats: Mapping[str, Fraction], slot: str | None
    ) -> None:
        """Each damaging ability adds one stack up to ``max_stacks`` (Spear of Shojin)."""
        for effect in self.ability_stacked:
            if not _conditions_hold(effect, self.target, "ability", False, target_stats, slot):
                continue
            if self._ability_stack_expired(effect, clock):
                self.ability_stacks[effect.title] = 0
            assert effect.max_stacks is not None
            self.ability_stacks[effect.title] = min(
                effect.max_stacks, self.ability_stacks.get(effect.title, 0) + 1
            )
            self.ability_stacked_at[effect.title] = clock

    def _in_combat(self, effect: _Effect) -> None:
        component = effect.component
        if (
            component.get("kind") != "damage_modifier"
            or component.get("direction") != "dealt"
            or component.get("source") != "all"
        ):
            raise RotationError(f"{effect.title}: only dealt modifiers grow in combat")
        self._mode(effect)
        self._cap(effect)
        if self.timeline is None:
            self.notes.append(
                f"attacker {effect.title}: grows each second in combat; without --timeline "
                "it stays at 0"
            )
            self.weakened |= not _excluded(effect, self.target.kind)
        self.combat.append(effect)

    @staticmethod
    def _cap(effect: _Effect) -> Fraction:
        for limit in effect.limits:
            if limit.get("kind") == "maximum":
                return Fraction(str(limit["value"]))
        raise RotationError(f"{effect.title}: an in-combat effect needs a maximum")

    def _combat_value(self, effect: _Effect, target_stats: Mapping[str, Fraction]) -> Fraction:
        """Per second x whole seconds in combat (from the start), up to the maximum.

        Without the timeline the clock stays at 0, so the increase does too.
        """
        return min(self._cap(effect), self._percent(effect, target_stats) * math.floor(self.now))

    def _stack(self, clock: Fraction, target_stats: Mapping[str, Fraction]) -> None:
        """An attack adds a stack to each effect whose turn it is, up to its maximum."""
        taken: set[str] = set()
        for effect in self.stacked:
            if not _conditions_hold(effect, self.target, "trigger", False, target_stats):
                continue
            if effect.alternation is not None:
                group, position, size = effect.alternation
                taken.add(group)
                if self.turns.get(group, 0) % size + 1 != position:
                    continue
            key = _key(effect)
            if self._expired(effect, clock):
                self.stacks[key] = 0
            assert effect.max_stacks is not None
            self.stacks[key] = min(effect.max_stacks, self.stacks.get(key, 0) + 1)
            self.stacked_at[key] = clock
            if self.timeline is not None:
                self.speed_changed |= str(effect.component.get("stat")) in ATTACK_SPEED_STATS
        for group in taken:
            self.turns[group] = self.turns.get(group, 0) + 1

    def _expired(self, effect: _Effect, at: Fraction) -> bool:
        """Whether the stacks of ``effect`` ran out by ``at`` (timeline only)."""
        last = self.stacked_at.get(_key(effect))
        return (
            self.timeline is not None
            and effect.window is not None
            and last is not None
            and at - last >= effect.window
        )

    def _full(self, item: str, effect_id: str) -> bool:
        """Whether every component of an item's stacking effect is at its maximum."""
        title = f"{item} {effect_id}"
        effects = [effect for effect in self.stacked if effect.title == title]
        if not effects:
            raise RotationError(f"{title}: stacks_full refers to no stacking effect")
        # ``_stack`` has already dropped expired stacks for this attack.
        return all(self.stacks.get(_key(effect), 0) == effect.max_stacks for effect in effects)

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
        slot: str | None = None,
    ) -> tuple[list[tuple[str, Fraction]], list[tuple[str, Fraction]], list[Label], list[str]]:
        dealt: list[tuple[str, Fraction]] = []
        taken: list[tuple[str, Fraction]] = []
        labels: list[Label] = []
        notes: list[str] = []
        for rune_mod in self.rune_combat.dealt_modifiers(part_kind, slot, target_stats):
            dealt.append((rune_mod.source, rune_mod.percent))
            labels.append(rune_mod.label)
            if rune_mod.note:
                notes.append(f"{rune_mod.source}: {rune_mod.note}")
        for effect in self.dealt:
            types = effect.component.get("damage_types")
            if types is not None and damage_type.value not in types:
                continue
            if self._mode(effect) and _conditions_hold(
                effect, self.target, part_kind, crit, target_stats, slot
            ):
                source = effect.component.get("source")
                if source == "ability":
                    if part_kind != "ability":
                        continue
                elif source != "all":
                    raise RotationError(f"{effect.title}: source is not modelled")
                value, stat_labels = self._value(effect, target_stats)
                dealt.append((effect.title, value))
                labels += [effect.label, *stat_labels]
        for effect in self.ability_stacked:
            source = effect.component.get("source")
            if source == "ability" and part_kind != "ability":
                continue
            types = effect.component.get("damage_types")
            if types is not None and damage_type.value not in types:
                continue
            count = self.ability_stacks.get(effect.title, 0)
            if not count or self._ability_stack_expired(effect, self.now):
                continue
            if _conditions_hold(effect, self.target, part_kind, crit, target_stats, slot):
                per_stack, stat_labels = self._value(effect, target_stats)
                dealt.append((f"{effect.title} ({count}x)", per_stack * count))
                labels += [effect.label, *stat_labels]
        for effect in self.combat:
            if _conditions_hold(effect, self.target, part_kind, crit, target_stats):
                value = self._combat_value(effect, target_stats)
                if value:
                    dealt.append((effect.title, value))
                    labels.append(effect.label)
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
        slot: str | None = None,
        apply_modifiers: bool = True,
        targets_hit: int = 1,
        secondary_damage_ratio: Fraction = Fraction(1),
        aoe: bool | None = None,
        hits_primary: bool = True,
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
        if apply_modifiers:
            dealt, taken, modifier_labels, modifier_notes = self._modifiers(
                kind, crit, target_stats, damage_type, slot
            )
        else:
            dealt, taken, modifier_labels, modifier_notes = [], [], [], []
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
            targets_hit=targets_hit,
            secondary_damage_ratio=secondary_damage_ratio,
            aoe=aoe,
            hits_primary=hits_primary,
        )
        return replace(part, healing=self._healing(part, life_steal_tag))

    def _healing(self, part: Part, tag: Mapping[str, Any] | None) -> Healing:
        """Life steal and omnivamp healing of ``part`` (life-steal-and-omnivamp.md)."""
        life_steal, omnivamp = self.life_steal.total(), self.omnivamp.total()
        rune_heal = self.rune_combat.healing_rate()
        if not life_steal and not omnivamp and rune_heal is None:
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
            elif part.kind == "item":
                if tag is not None and tag.get("value") is True:
                    applied_life_steal = life_steal
                    confidence = str((tag.get("source") or {}).get("confidence"))
                    labels.append(EVIDENCE_LABEL.get(confidence, Label.PENDING))
            elif part.kind in ("burn", "rune"):
                pass  # life steal comes from attacks; burns and rune procs are not attacks
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
            elif (
                part.kind == "item"
                and part.aoe is True
                and self.target.kind in REDUCED_OMNIVAMP_KINDS
            ):
                omnivamp /= 3
                notes.append(f"omnivamp from an area item effect against a {self.target.kind}: 33%")
            elif part.kind == "ability":
                kind = _target_kind(self.target, "omnivamp healing from an ability")
                if kind in REDUCED_OMNIVAMP_KINDS:
                    if part.aoe is True:
                        omnivamp /= 3
                        notes.append(f"omnivamp from an area ability against a {kind}: 33%")
                    elif part.aoe is None:
                        labels.append(Label.PENDING)
                        notes.append(
                            f"omnivamp against a {kind} is 33% for pets, damage over time and "
                            "area spells; the kit does not say which, healed at 100%"
                        )
        if rune_heal is not None and self.target.kind == "champion":
            omnivamp += rune_heal[0]
            labels.append(rune_heal[1])
            notes.append(rune_heal[2])
        if applied_life_steal and omnivamp:
            labels.append(Label.PENDING)
            notes.append("life steal and omnivamp on the same damage: their sum is not verified")
        rate = applied_life_steal + omnivamp
        raw_heal = part.damage * rate
        rev_amp = self._revitalize_amp()
        gw_rate, gw_label, gw_source = self._current_grievous(self.now)
        amount = scale_healing(
            raw_heal,
            hsp=Fraction(0),
            revitalize_amp=rev_amp,
            grievous=gw_rate,
            uses_hsp=False,
        )
        if raw_heal > 0:
            if rev_amp:
                labels.append(Label.DERIVED)
                notes.append(f"Revitalize <40% HP +{format_number(rev_amp * 100)}%")
            if gw_rate:
                labels.append(gw_label)
                notes.append(gw_source)
                self.grievous_used = True
        return Healing(applied_life_steal, omnivamp, amount, weakest(labels), tuple(notes))

    def _crit_multiplier(self, step: Step) -> tuple[Fraction, list[Label], list[str], str] | None:
        """Champion critical multiplier (including Ashe Frost Shot and passive reductions)."""
        labels: list[Label] = []
        notes: list[str] = []
        if self.sheet.champion.id == "Ashe":
            crit_chance = self.sheet["crit_chance"]
            bonus = self.sheet["crit_damage_bonus"]
            if crit_chance.total() > 0 or step.crit:
                if step.crit and self.crit_base is None:
                    raise RotationError(
                        f"step {step.text}: no critical multiplier for {self.sheet.champion.id} "
                        "(lol-knowledge/derived/champion-records.json has no critdamagemultiplier)"
                    )
                multiplier = 1 + crit_chance.total() * (1 + bonus.total())
                labels += [Label.DERIVED, crit_chance.label, bonus.label]
                if step.crit and self.crit_base is not None:
                    labels.append(self.crit_base.label)
                    notes.append(
                        "Ashe's critical strikes deal Frost Shot damage without extra crit "
                        "damage (they double the slow)"
                    )
                if len(bonus.sources()) > 1:
                    labels.append(Label.PENDING)
                    notes.append("several crit damage sources: their stacking is not verified")
                return (
                    multiplier,
                    labels,
                    notes,
                    f" x Frost Shot multiplier {format_number(multiplier)}",
                )
            return None
        if not step.crit:
            return None
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
        return multiplier, labels, notes, f" x critical multiplier {format_number(multiplier)}"

    def _attack(
        self, step: Step, target_stats: Mapping[str, Fraction], empowered: bool = False
    ) -> list[Part]:
        attack_damage = self.sheet["attack_damage"]
        raw = attack_damage.total()
        labels = [attack_damage.label]
        notes: list[str] = []
        source = "basic attack: total attack damage"
        crit_info = self._crit_multiplier(step)
        if crit_info is not None:
            multiplier, crit_labels, crit_notes, crit_suffix = crit_info
            raw *= multiplier
            labels += crit_labels
            notes += crit_notes
            source += crit_suffix
        parts = [
            self._part(
                "attack", source, DamageType.PHYSICAL, raw, labels, step.crit, target_stats, notes
            )
        ]
        parts += self._on_hit(self.on_hit, step, target_stats)
        if empowered:
            parts += self._on_hit(self.spellblade, step, target_stats)
            for repeat in self.repeats:
                parts += self._on_hit(
                    self.on_hit, step, target_stats, f" - again by {repeat.title}", repeat.label
                )
        parts += self._secondary_attacks(step, target_stats)
        return parts

    def _secondary_attacks(self, step: Step, target_stats: Mapping[str, Fraction]) -> list[Part]:
        """Secondary-only attack splash and bolts (Runaan's Hurricane, Tiamat/Hydras)."""
        if self.target_count <= 1 or not self.secondary_attacks:
            return []
        parts: list[Part] = []
        for effect in self.secondary_attacks:
            part_kind = "on_hit" if effect.trigger == "on_hit" else "item"
            if not _conditions_hold(effect, self.target, part_kind, step.crit, target_stats):
                continue
            secondary_count = self.target_count - 1
            max_targets = effect.component.get("max_targets")
            if isinstance(max_targets, int) and not isinstance(max_targets, bool):
                secondary_count = min(secondary_count, max_targets)
            if secondary_count <= 0:
                continue
            raw, stat_labels = self._value(effect, target_stats)
            raw = self._limited(effect, raw)
            labels = [effect.label, *stat_labels]
            notes = [
                f"hits {secondary_count} secondary target{'' if secondary_count == 1 else 's'}"
            ]
            source = f"{effect.title} ({effect.name})"
            can_crit = effect.component.get("can_crit") is True
            if can_crit:
                crit_info = self._crit_multiplier(step)
                if crit_info is not None:
                    multiplier, crit_labels, crit_notes, crit_suffix = crit_info
                    raw *= multiplier
                    labels += crit_labels
                    notes += crit_notes
                    source += crit_suffix
            damage_type = DamageType(str(effect.component.get("damage_type")))
            repeats_oh = effect.component.get("repeats_on_hit") is True
            parts.append(
                self._part(
                    part_kind,
                    source,
                    damage_type,
                    raw,
                    labels,
                    step.crit and can_crit,
                    target_stats,
                    notes,
                    life_steal_tag=effect.component.get("applies_life_steal"),
                    targets_hit=secondary_count,
                    aoe=not repeats_oh,
                    hits_primary=False,
                )
            )
            if repeats_oh and self.on_hit:
                parts += self._on_hit(
                    self.on_hit,
                    step,
                    target_stats,
                    f" - bolt by {effect.title}",
                    effect.label,
                    targets_hit=secondary_count,
                    hits_primary=False,
                )
        return parts

    def _ability_procs(
        self,
        step: Step,
        ability_parts: Sequence[Part],
        target_stats: Mapping[str, Fraction],
        clock: Fraction,
    ) -> list[Part]:
        """Item damage procs triggered by a damaging ability (e.g. Luden's Companion)."""
        if not ability_parts or not self.ability_procs:
            return []
        parts: list[Part] = []
        step_targets = step.targets if step.targets is not None else self.target_count
        for effect in self.ability_procs:
            if not _conditions_hold(effect, self.target, "item", False, target_stats, step.slot):
                continue
            if effect.cooldown is not None:
                if self.timeline is not None:
                    if clock < self.proc_ready.get(effect.title, Fraction(0)):
                        continue
                    self.proc_ready[effect.title] = clock + effect.cooldown
                else:
                    if effect.title in self.proc_fired:
                        continue
                    self.proc_fired.add(effect.title)
                    self.notes.append(
                        f"attacker {effect.title}: cooldown ({format_number(effect.cooldown)} s) "
                        "fires once without --timeline"
                    )
            base_raw, stat_labels = self._value(effect, target_stats)
            base_raw = self._limited(effect, base_raw)
            damage_type = DamageType(str(effect.component.get("damage_type")))
            labels = [effect.label, *stat_labels]
            echo = effect.component.get("echo")
            if isinstance(echo, Mapping):
                charges = int(echo["charges"])
                repeat_ratio = Fraction(str(echo["repeat_ratio"]))
                targets_hit = min(step_targets, charges)
                extra_hits = charges - targets_hit
                primary_raw = base_raw * (1 + extra_hits * repeat_ratio)
                primary_notes: tuple[str, ...] = (
                    (
                        f"1 full shot + {extra_hits} repeat shots at "
                        f"{format_number(repeat_ratio * 100)}%",
                    )
                    if extra_hits > 0
                    else (f"1 full shot (all {charges} charges split across targets)",)
                )
                parts.append(
                    self._part(
                        "item",
                        f"{effect.title} ({effect.name})",
                        damage_type,
                        primary_raw,
                        labels,
                        False,
                        target_stats,
                        primary_notes,
                        life_steal_tag=effect.component.get("applies_life_steal"),
                    )
                )
                if targets_hit > 1:
                    sec_count = targets_hit - 1
                    parts.append(
                        self._part(
                            "item",
                            f"{effect.title} ({effect.name}) secondary shots",
                            damage_type,
                            base_raw,
                            labels,
                            False,
                            target_stats,
                            (f"{sec_count} secondary shot{'' if sec_count == 1 else 's'} at 100%",),
                            life_steal_tag=effect.component.get("applies_life_steal"),
                            targets_hit=sec_count,
                            hits_primary=False,
                        )
                    )
            else:
                parts.append(
                    self._part(
                        "item",
                        f"{effect.title} ({effect.name})",
                        damage_type,
                        base_raw,
                        labels,
                        False,
                        target_stats,
                        life_steal_tag=effect.component.get("applies_life_steal"),
                    )
                )
        return parts

    def _on_damage_procs(
        self,
        step: Step,
        target_stats: Mapping[str, Fraction],
        clock: Fraction,
        slot: str | None,
    ) -> tuple[list[Part], list[ShieldEvent]]:
        """Item damage/shield procs triggered on dealing damage (Eclipse, Alternator, Slingshot)."""
        if not self.on_damage_procs:
            return [], []
        grouped: dict[str, list[_Effect]] = {}
        for effect in self.on_damage_procs:
            grouped.setdefault(effect.title, []).append(effect)
        parts: list[Part] = []
        shields: list[ShieldEvent] = []
        for title, group in grouped.items():
            lead = group[0]
            if not any(
                _conditions_hold(e, self.target, "item", False, target_stats, slot) for e in group
            ):
                continue
            if lead.cooldown is not None:
                if self.timeline is not None:
                    if clock < self.proc_ready.get(title, Fraction(0)):
                        continue
                elif title in self.proc_fired:
                    continue
            if lead.combo_required is not None:
                if self.timeline is not None:
                    hits = self.combo_hits.setdefault(title, [])
                    if lead.window is not None:
                        hits[:] = [t for t in hits if clock - t < lead.window]
                    hits.append(clock)
                    if len(hits) < lead.combo_required:
                        continue
                    hits.clear()
                else:
                    count = self.combo_counts.get(title, 0) + 1
                    if count < lead.combo_required:
                        self.combo_counts[title] = count
                        continue
                    self.combo_counts[title] = 0
                    if lead.window is not None:
                        self.notes.append(
                            f"attacker {title}: combo window ({format_number(lead.window)} s) "
                            "ignored without --timeline"
                        )
            if lead.cooldown is not None:
                if self.timeline is not None:
                    self.proc_ready[title] = clock + lead.cooldown
                else:
                    self.proc_fired.add(title)
                    self.notes.append(
                        f"attacker {title}: cooldown ({format_number(lead.cooldown)} s) "
                        "fires once without --timeline"
                    )
            for effect in group:
                if not _conditions_hold(effect, self.target, "item", False, target_stats, slot):
                    continue
                raw, stat_labels = self._value(effect, target_stats)
                raw = self._limited(effect, raw)
                kind = effect.component.get("kind")
                if kind == "damage":
                    parts.append(
                        self._part(
                            "item",
                            f"{effect.title} ({effect.name})",
                            DamageType(str(effect.component.get("damage_type"))),
                            raw,
                            [effect.label, *stat_labels],
                            False,
                            target_stats,
                            life_steal_tag=effect.component.get("applies_life_steal"),
                        )
                    )
                elif kind == "shield":
                    shields.append(
                        self._make_shield_event(
                            f"{effect.title} ({effect.name})",
                            raw,
                            weakest([effect.label, *stat_labels]),
                            shield_type=str(effect.component.get("shield_type", "normal")),
                            duration=effect.duration,
                        )
                    )
        return parts, shields

    def _burns(
        self,
        step: Step,
        parts: Sequence[Part],
        target_stats: Mapping[str, Fraction],
        burned: set[str],
        clock: Fraction = Fraction(0),
    ) -> list[Part]:
        """Each burn's full duration, once, on the first qualifying step that starts it.

        With the timeline, the step (re)starts the burn instead; its damage is
        counted as time passes (``_accrue``).
        """
        result: list[Part] = []
        for effect in self.burns:
            if effect.trigger == "damaging_ability" and (step.slot is None or not parts):
                continue
            if effect.trigger == "cast" and step.slot is None:
                continue
            if effect.trigger == "on_damage" and not parts:
                continue
            if self.timeline is None and effect.title in burned:
                continue
            if not _conditions_hold(effect, self.target, "burn", False, target_stats, step.slot):
                continue
            burned.add(effect.title)
            duration = Fraction(str(effect.component.get("duration_seconds")))
            per_second, stat_labels = self._value(effect, target_stats)
            per_second = self._limited(effect, per_second)
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
        """Apply the timed effects in force at ``at``: stats, dealt damage, resistances.

        Also the stacks gained per attack (combat-stacks.md), with or without the timeline.
        """
        sheet = self.base_sheet
        self.now = at
        self.active_dealt, self.shred = [], {}
        for effect in self.stacked:
            count = self.stacks.get(_key(effect), 0)
            if not count or self._expired(effect, at):
                continue
            stat_id = str(effect.component.get("stat"))
            per_stack, stat_labels = self._value(effect, self.target.stats)
            labels = [effect.label, *stat_labels]
            note = f"{count} stack{'' if count == 1 else 's'}"
            if effect.alternation is not None:
                labels.append(Label.PENDING)
                note += "; light and dark hits alternate from a light one (not verified)"
            sheet = with_bonus(
                sheet,
                stat_id,
                effect_amount(stat_id, per_stack * count),
                f"{effect.title} ({effect.name})",
                weakest(labels),
                note,
            )
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
        for bonus in self.rune_combat.active_stat_bonuses(at, self.base_sheet):
            sheet = with_bonus(
                sheet, bonus.stat_id, bonus.amount, bonus.source, bonus.label, bonus.note
            )
        p_flats, p_amps = self.passive_combat.active_stat_modifiers(at, self.base_sheet.level)
        for p_bonus in p_flats:
            sheet = with_bonus(
                sheet, p_bonus.stat_id, p_bonus.amount, p_bonus.source, p_bonus.label, p_bonus.note
            )
        for p_amp in p_amps:
            sheet = with_amplifier(sheet, p_amp.stat_id, p_amp.percent, p_amp.source, p_amp.label)
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
        """An attack hit shortens the cooldowns that attacks reduce (Yun Tal, Scout's Slingshot)."""
        for effect in self.timed:
            ready = self.timed_ready.get(effect.title)
            if effect.refund is None or ready is None or ready <= clock:
                continue
            seconds = effect.refund[1] if crit else effect.refund[0]
            self.timed_ready[effect.title] = max(clock, ready - seconds)
        seen: set[str] = set()
        for effect in self.on_damage_procs:
            if effect.title in seen or effect.refund is None:
                continue
            seen.add(effect.title)
            ready = self.proc_ready.get(effect.title)
            if ready is None or ready <= clock:
                continue
            seconds = effect.refund[1] if crit else effect.refund[0]
            self.proc_ready[effect.title] = max(clock, ready - seconds)

    def _accrue(
        self, until: Fraction, health: Fraction, shield: Fraction = Fraction(0)
    ) -> tuple[list[Part], Fraction, Fraction, Fraction]:
        """Burn damage from the last count to ``until``, split where an effect ends.

        Burns deal their damage per second continuously (burns.md); each piece
        uses the timed effects in force during it.
        """
        start = self.accrued
        if until <= start or (
            not self.burning
            and not self.rune_combat.has_active_burn()
            and not self.rune_combat.has_due_procs(until)
        ):
            self.accrued = max(start, until)
            return [], health, shield, Fraction(0)
        ends = {
            end
            for end in [
                *(burn.end for burn in self.burning.values()),
                *(window.end for window in self.windows.values()),
                *(
                    self.stacked_at[_key(effect)] + effect.window
                    for effect in self.stacked
                    if effect.window is not None and _key(effect) in self.stacked_at
                ),
                # Seconds in combat change the in-combat increases on whole seconds.
                *(Fraction(second) for second in range(math.ceil(until)) if self.combat),
                *self.rune_combat.burn_split_times(start, until),
                *self.rune_combat.due_times(until),
                *self.passive_combat.stack_expiry_times(start, until),
            ]
            if start < end < until
        }
        points = sorted({start, until, *ends})
        parts: list[Part] = []
        total_absorbed = Fraction(0)
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
                health, shield, absorbed = self._absorb_parts([part], health, shield)
                total_absorbed += absorbed
            rune_burn = self.rune_combat.accrue_burn(begin, finish)
            if rune_burn is not None:
                part = self._part(
                    "burn",
                    rune_burn.source,
                    rune_burn.damage_type,
                    rune_burn.raw,
                    [rune_burn.label],
                    False,
                    target_stats,
                    rune_burn.notes,
                )
                parts.append(part)
                health, shield, absorbed = self._absorb_parts([part], health, shield)
                total_absorbed += absorbed
            due_procs = self.rune_combat.pop_due(finish)
            if due_procs:
                self._set_moment(finish)
                for proc in due_procs:
                    part = self._part(
                        "rune",
                        proc.source,
                        proc.damage_type,
                        proc.raw,
                        [proc.label],
                        False,
                        self._target_stats(health),
                        proc.notes,
                        apply_modifiers=proc.apply_modifiers,
                    )
                    parts.append(part)
                    health, shield, absorbed = self._absorb_parts([part], health, shield)
                    total_absorbed += absorbed
        self.accrued = until
        self.burning = {key: burn for key, burn in self.burning.items() if burn.end > until}
        self.rune_combat.clear_expired_burns(until)
        return parts, health, shield, total_absorbed

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
        open_casts: dict[str, tuple[Fraction, int, Fraction]],
    ) -> None:
        """Check a cast against the cooldown and recast rules of the timeline.

        ``open_casts`` holds, per slot, when it was cast, the recasts used since
        and the time of the last of them.
        """
        assert step.slot is not None
        ability = self.kit.ability(step.slot)
        case = ability.case(step.case) if step.case is not None else ability.cases[0]
        if case.recast:
            if step.slot not in open_casts:
                raise RotationError(f"step {step.text}: {step.slot} has not been cast to recast it")
            opened, used, last = open_casts[step.slot]
            window = ability.recast_window
            if window is not None and clock - opened > window:
                raise RotationError(
                    f"step {step.text}: the recast window ({format_number(window)} s) closed at "
                    f"{format_number(opened + window)} s"
                )
            if used >= ability.max_recasts:
                raise RotationError(
                    f"step {step.text}: {step.slot} has no recast left "
                    f"({ability.max_recasts} per cast)"
                )
            interval = ability.recast_interval
            if interval is not None and clock - last < interval:
                raise RotationError(
                    f"step {step.text}: the next {step.slot} is available at "
                    f"{format_number(last + interval)} s (now {format_number(clock)} s)"
                )
            open_casts[step.slot] = (opened, used + 1, clock)
            return
        until = ready.get(step.slot, Fraction(0))
        if clock < until:
            raise RotationError(
                f"step {step.text}: {step.slot} is on cooldown until {format_number(until)} s "
                f"(now {format_number(clock)} s)"
            )
        ready[step.slot] = clock + self.cooldowns[step.slot][self.ranks[step.slot] - 1]
        open_casts[step.slot] = (clock, 0, clock)

    def _execute(
        self,
        parts: Sequence[Part],
        health: Fraction,
        target_stats: Mapping[str, Fraction],
        shield_absorbed: Fraction = Fraction(0),
    ) -> list[Part]:
        """An execute: the target's remaining health as true damage (execute.md)."""
        left = health - (
            sum((part.primary_damage for part in parts), start=Fraction(0)) - shield_absorbed
        )
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
            needed = effect.condition_values.get("stacks_full")
            if needed is not None and not self._full(effect.item, str(needed)):
                continue  # phantom hits count only at full stacks (combat-stacks.md)
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
                label = effect.label
                if needed is not None:
                    label = Label.PENDING
                    self.notes.append(
                        f"{effect.title}: the attack that completes the stacks counts (user "
                        "decision; an old Leaguepedia note), not verified"
                    )
                parts += self._on_hit(
                    self.on_hit, step, target_stats, f" - again by {effect.title}", label
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
        *,
        targets_hit: int = 1,
        hits_primary: bool = True,
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
                    targets_hit=targets_hit,
                    hits_primary=hits_primary,
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
        case_spec = ability.case(step.case) if step.case is not None else ability.cases[0]
        step_targets = step.targets if step.targets is not None else self.target_count
        targets_hit, sec_ratio, unverified = case_spec.resolve_targets(step_targets)
        notes = list(f"{ability.slot}: {note}" for note in ability.not_modelled)
        extra_labels: list[Label] = []
        if unverified:
            extra_labels.append(Label.PENDING)
            self.weakened = True
            self.notes.append(
                f"step {step.text} ({ability.slot}.{case_spec.id}): kit does not declare aoe or "
                f"max_targets; evaluated against 1 of {step_targets} targets"
            )
        if targets_hit > 1:
            if sec_ratio == 1:
                notes.append(f"hits {targets_hit} targets (primary + {targets_hit - 1} secondary)")
            else:
                notes.append(
                    f"hits {targets_hit} targets (primary at 100% + {targets_hit - 1} secondary "
                    f"at {format_number(sec_ratio * 100)}%)"
                )
        parts = [
            self._part(
                "ability",
                f"{ability.slot}.{part.case}[{part.index}] {part.source}",
                part.damage_type,
                part.raw,
                [part.label, *extra_labels],
                False,
                target_stats,
                tuple(notes),
                slot=ability.slot,
                targets_hit=targets_hit,
                secondary_damage_ratio=sec_ratio,
                aoe=case_spec.aoe,
            )
            for part in raw_parts
        ]
        return f"{ability.slot} {ability.name} rank {rank}", parts

    def _burn_outcome(
        self,
        index: int,
        step: Step,
        name: str,
        clock: Fraction,
        health: Fraction,
        shield: Fraction = Fraction(0),
        *,
        regen_until: Fraction | None = None,
    ) -> StepOutcome:
        """A step with no damage of its own: the burn damage up to ``clock``."""
        res_before = self.resources.current if self.resources.uses_casting_pool else None
        parts, left, _, absorbed = self._accrue(clock, health, shield)
        if parts:
            parts += self._execute(parts, health, self._target_stats(left), absorbed)
        regen_events = self.resources.accrue_regen(clock if regen_until is None else regen_until)
        res_after = self.resources.current if self.resources.uses_casting_pool else None
        outcome = StepOutcome(
            index,
            step,
            name,
            tuple(parts),
            health,
            weakest(part.label for part in parts),
            clock,
            shield_before=shield,
            shield_absorbed=absorbed,
            resource_before=res_before,
            resource_after=res_after,
            resource_events=tuple(regen_events),
        )
        self._record_attacker_healing(outcome.healing)
        return outcome

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
        shield = self.target.shield
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
        open_casts: dict[str, tuple[Fraction, int, Fraction]] = {}
        for index, step in enumerate(steps, start=1):
            if step.wait is not None:
                if self.timeline is None:
                    raise RotationError(f"step {step.text}: waits need the timeline (--timeline)")
                outcome = self._burn_outcome(
                    index,
                    step,
                    "wait",
                    clock,
                    health,
                    shield,
                    regen_until=clock + step.wait,
                )
                outcomes.append(outcome)
                health = outcome.health_after
                shield = outcome.shield_after
                clock += step.wait
                continue
            if self.timeline is not None and step.slot is None:
                clock = max(clock, next_attack)
            elif self.timeline is not None:
                self._cast(step, clock, ready, open_casts)
            parts: list[Part] = []
            heal_events: list[HealEvent] = []
            shield_events: list[ShieldEvent] = []
            resource_events: list[ResourceEvent] = []
            step_cost: StepResourceCost | None = None
            res_before = self.resources.current if self.resources.uses_casting_pool else None
            before = health
            shield_before = shield
            accrued_absorbed = Fraction(0)
            if self.timeline is not None:
                parts, health, shield, accrued_absorbed = self._accrue(clock, health, shield)
                resource_events.extend(self.resources.accrue_regen(clock))
            accrued_count = len(parts)
            self._set_moment(clock)
            target_stats = self._target_stats(health)
            extra: list[Label] = []
            if step.slot is None:
                # Thornmail's Grievous Wounds applies before the triggering attack's own heal.
                self._trigger_defender_grievous(clock)
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
                attack_parts = self._attack(step, target_stats, empowered)
                parts += attack_parts
                parts += self._burns(step, attack_parts, target_stats, burned, clock)
                oh_heals, oh_shields = self._item_survival_events("on_hit", target_stats, clock)
                heal_events += oh_heals
                shield_events += oh_shields
                resource_events.extend(self._item_resource_restores("on_hit", target_stats))
                if empowered:
                    sb_heals, sb_shields = self._item_survival_events(
                        "spellblade", target_stats, clock
                    )
                    heal_events += sb_heals
                    shield_events += sb_shields
                    resource_events.extend(self._item_resource_restores("spellblade", target_stats))
                if empowered and self.timeline is not None:
                    spellblade_ready = clock + self._spellblade_cooldown()
                    if self._open("spellblade", clock, target_stats):
                        extra.append(Label.PENDING)
                timed = self.timeline is not None
                self._stack(clock, target_stats)
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
                step_cost = resolve_ability_cost(
                    self.kit,
                    self.sheet,
                    step.slot,
                    self.ranks[step.slot],
                    step.case,
                    self.stats,
                    self.origin,
                    self.inputs,
                    attacker_hp=self.attacker_hp,
                    attacker_max_hp=self.attacker_max_hp,
                )
                if step_cost.resource == "health":
                    current_hp = self._ensure_attacker_hp()
                    self.attacker_hp, hp_ev = self.resources.spend_health(current_hp, step_cost)
                    resource_events.append(hp_ev)
                else:
                    cost_ev, was_insufficient = self.resources.spend_pool(
                        index, step.text, step_cost
                    )
                    if cost_ev is not None:
                        resource_events.append(cost_ev)
                    if was_insufficient:
                        extra.append(Label.PENDING)
                if step_cost.label is Label.PENDING:
                    extra.append(Label.PENDING)
                parts += ability_parts
                c_heals, c_shields = self._item_survival_events("cast", target_stats, clock)
                heal_events += c_heals
                shield_events += c_shields
                resource_events.extend(self._item_resource_restores("cast", target_stats))
                if ability_parts:
                    da_heals, da_shields = self._item_survival_events(
                        "damaging_ability", target_stats, clock
                    )
                    heal_events += da_heals
                    shield_events += da_shields
                    resource_events.extend(
                        self._item_resource_restores("damaging_ability", target_stats)
                    )
                    parts += self._ability_procs(step, ability_parts, target_stats, clock)
                    self._stack_ability(clock, target_stats, step.slot)
                # An ability cast while Spellblade is on cooldown does not charge it.
                if self.timeline is None or clock >= spellblade_ready:
                    charged, charged_at = True, clock
                parts += self._burns(step, ability_parts, target_stats, burned, clock)
                if self.timeline is not None:
                    self._open("cast", clock, target_stats, step.slot)
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
            step_dealt = bool(parts[accrued_count:]) if step.slot is None else bool(ability_parts)
            if step_dealt:
                od_parts, od_shields = self._on_damage_procs(step, target_stats, clock, step.slot)
                parts += od_parts
                shield_events += od_shields
            for ev in shield_events:
                self.rune_combat.on_attacker_shield(ev.amount, clock)
            for proc in self.rune_combat.on_step(step.slot, step_dealt, clock, self.sheet):
                parts.append(
                    self._part(
                        "rune",
                        proc.source,
                        proc.damage_type,
                        proc.raw,
                        [proc.label],
                        False,
                        target_stats,
                        proc.notes,
                        apply_modifiers=proc.apply_modifiers,
                    )
                )
            for p_proc in self.passive_combat.on_step(step.slot, step_dealt, clock, self.sheet):
                parts.append(
                    self._part(
                        "ability",
                        p_proc.source,
                        p_proc.damage_type,
                        p_proc.raw,
                        [p_proc.label],
                        False,
                        target_stats,
                        p_proc.notes,
                        slot="P",
                    )
                )
            step_damage = sum((p.primary_damage for p in parts[accrued_count:]), start=Fraction(0))
            step_after, shield_after, step_absorbed = self._absorb_parts(
                parts[accrued_count:], health, shield
            )
            total_absorbed = accrued_absorbed + step_absorbed
            complete_parts: list[Part] = []
            for proc in self.rune_combat.on_step_complete(
                step_damage,
                clock,
                self.sheet,
                health,
                step_after,
                self.target.stats["max_health"],
            ):
                complete_parts.append(
                    self._part(
                        "rune",
                        proc.source,
                        proc.damage_type,
                        proc.raw,
                        [proc.label],
                        False,
                        target_stats,
                        proc.notes,
                        apply_modifiers=proc.apply_modifiers,
                    )
                )
            if complete_parts:
                parts.extend(complete_parts)
                step_after, shield_after, extra_absorbed = self._absorb_parts(
                    complete_parts, step_after, shield_after
                )
                total_absorbed += extra_absorbed
            parts += self._execute(parts, before, target_stats, total_absorbed)
            final_hp = max(
                Fraction(0),
                before - (sum((p.primary_damage for p in parts), Fraction(0)) - total_absorbed),
            )
            killed_now = before > 0 and final_hp == 0
            for raw_heal in self.rune_combat.on_step_heals(
                step.slot,
                step_dealt,
                killed_now,
                clock,
                self.sheet,
                self.attacker_hp,
                self.attacker_max_hp,
            ):
                heal_events.append(
                    self._make_heal_event(
                        raw_heal.source,
                        raw_heal.raw,
                        raw_heal.label,
                        clock,
                        uses_hsp=raw_heal.uses_hsp,
                        notes=raw_heal.notes,
                    )
                )
            for p_heal in self.passive_combat.on_step_heals(
                step.slot, step_dealt, killed_now, clock, self.sheet
            ):
                heal_events.append(
                    self._make_heal_event(
                        p_heal.source,
                        p_heal.raw,
                        p_heal.label,
                        clock,
                        uses_hsp=p_heal.uses_hsp,
                        notes=p_heal.notes,
                    )
                )
            for raw_restore in self.rune_combat.on_step_resource_restores(
                step_dealt,
                killed_now,
                clock,
                self.sheet,
                self.resources.pool.kind,
                self.resources.maximum,
            ):
                applied = self.resources.restore(
                    raw_restore.source,
                    raw_restore.resource,
                    raw_restore.raw,
                    raw_restore.label,
                    raw_restore.notes,
                )
                if applied is not None:
                    resource_events.append(applied)
            new_notes, kw_weak = self.rune_combat.drain_runtime_updates()
            self.notes.extend(new_notes)
            self.weakened |= kw_weak
            self.speed_changed |= self.rune_combat.speed_changed
            res_after = self.resources.current if self.resources.uses_casting_pool else None
            outcome = StepOutcome(
                index,
                step,
                name,
                tuple(parts),
                before,
                weakest(
                    [
                        *(part.label for part in parts),
                        *(ev.label for ev in shield_events),
                        *extra,
                    ]
                ),
                None if self.timeline is None else clock,
                shield_before=shield_before,
                shield_absorbed=total_absorbed,
                heal_events=tuple(heal_events),
                shield_events=tuple(shield_events),
                resource_cost=step_cost,
                resource_before=res_before,
                resource_after=res_after,
                resource_events=tuple(resource_events),
            )
            outcomes.append(outcome)
            self._record_attacker_healing(outcome.healing)
            health = outcome.health_after
            shield = outcome.shield_after
            if self.timeline is not None and step.slot is None:
                # The next attack: 1 / the attack speed just after this one (timeline.md).
                self._set_moment(clock)
                next_attack = clock + 1 / self.sheet["attack_speed"].total()
        pending_end = self.rune_combat.last_pending_time()
        if self.burning or pending_end is not None:
            ends = [*(burn.end for burn in self.burning.values())]
            if pending_end is not None:
                ends.append(pending_end)
            end = max(ends)
            tail_name = (
                f"burns until {format_number(end)} s"
                if (self.burning or self.rune_combat.has_active_burn())
                else f"delayed effects until {format_number(end)} s"
            )
            outcomes.append(
                self._burn_outcome(
                    len(steps) + 1,
                    Step("burns"),
                    tail_name,
                    end,
                    health,
                    shield,
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
        resource_summary = self.resources.summary()
        self.notes.extend(self.resources.notes)
        self.notes.extend(self.passive_combat.notes)
        self.weakened |= self.resources.weakened
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
            start_shield=self.target.shield,
            shield_type=self.target.shield_type,
            attacker_start_health=self.attacker_start_hp,
            attacker_max_health=self.attacker_max_hp,
            attacker_remaining_health=self.attacker_hp,
            effective_healing=self.effective_healing_total,
            grievous_wounds_applied=self.grievous_used,
            resource=resource_summary,
            target_count=self.target_count,
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
    runes: Sequence[int] = (),
    rune_data: RuneData | None = None,
    ap_weight: Fraction | None = None,
    start_resource: Fraction | None = None,
    allow_insufficient_resource: bool = False,
    apply_passives: bool = True,
    target_count: int = 1,
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
    has_ultimate = any(step.slot == "R" for step in steps)
    rotation = _Rotation(
        kit,
        sheet,
        ranks,
        target,
        crit_base,
        holder_range,
        inputs or {},
        timeline,
        runes=runes,
        rune_data=rune_data,
        has_ultimate_step=has_ultimate,
        ap_weight=ap_weight,
        start_resource=start_resource,
        allow_insufficient_resource=allow_insufficient_resource,
        apply_passives=apply_passives,
        target_count=target_count,
    )
    return rotation.run(steps)
