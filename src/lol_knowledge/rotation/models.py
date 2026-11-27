"""Core data models, constants, and step parser for rotations."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from fractions import Fraction

from ..damage import DamageResult, DamageType
from ..errors import RotationError
from ..resources import ResourceEvent, ResourceSummary, StepResourceCost
from ..stats import Label, weakest
from ..summoners import SummonerSpellSpec
from ..survival import HealEvent, ShieldEvent

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
TIMED_TRIGGERS = frozenset(
    {"spellblade", "energized", "damaging_ability", "on_attack", "on_damage", "cast"}
)
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
_ITEM_STEP = re.compile(r"item:(?P<id>\d+)(?:@(?P<targets>\d+))?", re.IGNORECASE)
_SUMMONER_STEP = re.compile(r"summoner:(?P<name>[a-z0-9_\u00c0-\u017f]+)", re.IGNORECASE)
# Active component kinds executable via ``item:<id>`` steps.
ACTIVE_COMBAT_KINDS = frozenset({"damage", "healing", "shield", "stat_modifier", "damage_modifier"})


@dataclass(frozen=True)
class Step:
    """One rotation step: attack, ability, ``wait:<s >``, ``item:<id>`` or ``summoner:<name>``."""

    text: str
    slot: str | None = None
    case: str | None = None
    crit: bool = False
    # False for ``attack:nospellblade``: the attack is not empowered (spellblade.md).
    spellblade: bool = True
    # Seconds to wait, for ``wait:<seconds>`` (timeline only, timeline.md).
    wait: Fraction | None = None
    # Explicit target count override for an ability or item active step (e.g. ``R.dash@3``).
    targets: int | None = None
    # Item id for an active item step (e.g. ``item:3074``, ``item:3748``).
    item_id: str | None = None
    # Summoner spell token for a summoner cast step (e.g. ``summoner:ignite``).
    summoner_id: str | None = None


def parse_steps(text: str) -> tuple[Step, ...]:
    """Read ``attack``, ``attack:crit``, ``Q``, ``E.edge``, ``item:3074``, ``summoner:ignite``…

    Steps are separated by commas or spaces; an attack takes any of the
    modifiers ``crit`` and ``nospellblade``, once each and in any order.
    """
    tokens = [token for token in re.split(r"[,\s]+", text.strip()) if token]
    if not tokens:
        raise RotationError("the rotation has no steps")
    steps = []
    for token in tokens:
        item_match = _ITEM_STEP.fullmatch(token)
        if item_match is not None:
            raw_targets = item_match.group("targets")
            step_targets: int | None = None
            if raw_targets is not None:
                step_targets = int(raw_targets)
                if step_targets < 1:
                    raise RotationError(f"step {token!r}: target count must be at least 1")
            steps.append(Step(token, item_id=item_match.group("id"), targets=step_targets))
            continue
        summ_match = _SUMMONER_STEP.fullmatch(token)
        if summ_match is not None:
            steps.append(Step(token, summoner_id=summ_match.group("name")))
            continue
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
                "Q, W, E, R, SLOT.case, item:<id> or summoner:<name>"
            )
        raw_targets = match.group("targets")
        step_targets = None
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
    flat_reduction: Fraction = Fraction(0)
    _dealt_factor: Fraction = field(init=False, repr=False, compare=False)
    _taken_factor: Fraction = field(init=False, repr=False, compare=False)
    _primary_damage: Fraction = field(init=False, repr=False, compare=False)
    _secondary_damage: Fraction = field(init=False, repr=False, compare=False)
    _damage: Fraction = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.dealt:
            dealt_factor = Fraction(1)
        else:
            dealt_factor = 1 + sum((percent for _, percent in self.dealt), start=Fraction(0)) / 100
        if not self.taken:
            taken_factor = Fraction(1)
        else:
            taken_factor = Fraction(1)
            for _, percent in self.taken:
                taken_factor *= 1 + percent / 100
        unit = self.mitigation.damage * dealt_factor * taken_factor
        primary_damage = (
            max(Fraction(0), unit - self.flat_reduction) if self.hits_primary else Fraction(0)
        )
        if self.targets_hit == 1 and self.hits_primary:
            secondary_damage = Fraction(0)
        elif not self.hits_primary:
            secondary_damage = unit * self.targets_hit * self.secondary_damage_ratio
        else:
            secondary_damage = unit * (self.targets_hit - 1) * self.secondary_damage_ratio
        damage = primary_damage + secondary_damage
        object.__setattr__(self, "_dealt_factor", dealt_factor)
        object.__setattr__(self, "_taken_factor", taken_factor)
        object.__setattr__(self, "_primary_damage", primary_damage)
        object.__setattr__(self, "_secondary_damage", secondary_damage)
        object.__setattr__(self, "_damage", damage)

    @property
    def dealt_factor(self) -> Fraction:
        """Damage-dealt modifiers add up (V26.09) before multiplying."""
        return self._dealt_factor

    @property
    def taken_factor(self) -> Fraction:
        """Damage-taken modifiers multiply with each other."""
        return self._taken_factor

    @property
    def primary_damage(self) -> Fraction:
        """Post-mitigation and post-modifier damage dealt to the primary target."""
        return self._primary_damage

    @property
    def secondary_damage(self) -> Fraction:
        """Total post-mitigation and post-modifier damage dealt to secondary targets."""
        return self._secondary_damage

    @property
    def damage(self) -> Fraction:
        """Total damage dealt by this part across all targets hit."""
        return self._damage


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
    shield_shredded: Fraction = Fraction(0)
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
        return max(Fraction(0), self.shield_before - self.shield_shredded - self.shield_absorbed)

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
class TimelineWindow:
    """Cumulative damage and DPS within ``[0, seconds]`` of a timeline rotation (MEC-21)."""

    seconds: Fraction
    steps_count: int
    total: Fraction
    primary_total: Fraction
    secondary_total: Fraction
    damage_per_second: Fraction
    healing: Fraction
    remaining_health: Fraction
    label: Label


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

    def window(self, seconds: Fraction) -> TimelineWindow:
        """Summarize cumulative damage, DPS and healing in ``[0, seconds]`` (MEC-21)."""
        if self.timeline is None:
            raise RotationError("window reports require --timeline")
        if seconds <= 0:
            raise RotationError("window duration must be positive")
        total = Fraction(0)
        primary = Fraction(0)
        secondary = Fraction(0)
        healing = Fraction(0)
        steps_count = 0
        rem_hp = self.start_health
        labels: list[Label] = []
        prev_t = Fraction(0)
        for step in self.steps:
            t = step.time if step.time is not None else Fraction(0)
            if t <= seconds:
                total += step.total
                primary += step.primary_total
                secondary += step.secondary_total
                healing += step.healing
                rem_hp = step.health_after
                labels.append(step.label)
                if step.step.text != "burns" and step.step.wait is None:
                    steps_count += 1
                prev_t = t
            elif step.step.text == "burns" and t > prev_t and seconds > prev_t:
                frac = (seconds - prev_t) / (t - prev_t)
                total += step.total * frac
                primary += step.primary_total * frac
                secondary += step.secondary_total * frac
                healing += step.healing * frac
                rem_hp = max(Fraction(0), rem_hp - step.health_damage * frac)
                labels.append(step.label)
                break
        return TimelineWindow(
            seconds=seconds,
            steps_count=steps_count,
            total=total,
            primary_total=primary,
            secondary_total=secondary,
            damage_per_second=total / seconds,
            healing=healing,
            remaining_health=rem_hp,
            label=weakest(labels) if labels else self.label,
        )


# Effect conditions on the target kind: a skipped effect whose condition rules
# out the rotation's target cannot change its damage.
TARGET_KIND_CONDITIONS = {
    "target_is_champion": "champion",
    "target_is_structure": "structure",
    "target_is_minion": "minion",
    "target_is_monster": "monster",
}


@dataclass(frozen=True)
class DuelStepResult:
    """Single-step emission produced by ``RotationSession.step_one`` for a 1v1 duel."""

    outcome: StepOutcome
    new_parts: tuple[Part, ...]
    heal_events: tuple[HealEvent, ...]
    shield_events: tuple[ShieldEvent, ...]
    health_cost: Fraction
    applied_grievous_until: Fraction | None
    applied_exhaust_until: Fraction | None
    shield_reaver_ratio: Fraction
    cast_summoner: SummonerSpellSpec | None


@dataclass
class RotationSession:
    """Incremental offensive stepper over ``_Rotation`` for coupled 1v1 duels."""

    sync_context: Callable[..., None]
    notify_shield_granted: Callable[[Fraction, Fraction], None]
    next_attack_time: Callable[[], Fraction]
    ability_ready_time: Callable[[str], Fraction]
    can_cast_slot: Callable[[str, str | None, Fraction], bool]
    peek_step_time: Callable[..., Fraction]
    accrue_to: Callable[[Fraction], tuple[list[Part], list[HealEvent], list[ResourceEvent]]]
    step_one: Callable[..., DuelStepResult]
    next_pending_time: Callable[[Fraction, Fraction], Fraction | None]
    get_notes: Callable[[], tuple[str, ...]]
    is_weakened: Callable[[], bool]
    resource_summary: Callable[[], ResourceSummary | None]
