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
from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Any

from .damage import DamageResult, DamageType, format_number, mitigate
from .errors import KitError, RotationError
from .formula import FormulaError, evaluate_formula
from .kit import Kit, ability_damage, sheet_stats
from .scenario import PENETRATION, Target, penetration_modifiers
from .stats import EVIDENCE_LABEL, ItemData, Label, StatSheet, sheet_effect_reason, weakest

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
# Base critical strike multiplier of the patch notes (26.1); records that differ are flagged.
PATCH_CRIT_MULTIPLIER = Fraction(2)
# Passives that reduce total critical strike damage: "Critical Strike Damage Reduction:
# -10% => -5%" for Yasuo and Yone in the 26.17 patch notes (critical-strike.md, C10).
CRIT_DAMAGE_REDUCTIONS = {"Yasuo": Fraction(5, 100), "Yone": Fraction(5, 100)}
# Limit conditions of the catalog, as the target kinds they apply to.
LIMIT_CONDITIONS = {"target is a minion or monster": frozenset({"minion", "monster"})}
# Effect components that change the damage of a rotation when not applied.
DAMAGE_KINDS = frozenset({"damage", "damage_modifier", "stat_modifier"})

# Kinds against which omnivamp drops to 33 % for pets, damage over time and area spells.
REDUCED_OMNIVAMP_KINDS = frozenset({"minion", "monster"})

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
    kind: str  # "attack", "on_hit" or "ability"
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
class RotationOutcome:
    steps: tuple[StepOutcome, ...]
    max_health: Fraction
    start_health: Fraction
    holder_range: str | None
    label: Label
    notes: tuple[str, ...]

    @property
    def total(self) -> Fraction:
        return sum((step.total for step in self.steps), start=Fraction(0))

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

    @property
    def title(self) -> str:
        return f"{self.item} {self.id}"


# Effect conditions on the target kind: a skipped effect whose condition rules
# out the rotation's target cannot change its damage.
TARGET_KIND_CONDITIONS = {"target_is_champion": "champion", "target_is_structure": "structure"}


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
                    )
                )
    return effects, notes, weakened


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


def _conditions_hold(effect: _Effect, target: Target, part_kind: str, crit: bool) -> bool:
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
    ) -> None:
        self.kit, self.sheet, self.ranks, self.target = kit, sheet, ranks, target
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

    def _percent(self, effect: _Effect, target_stats: Mapping[str, Fraction]) -> Fraction:
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
        return result.exact

    @staticmethod
    def _explain(exc: FormulaError) -> str:
        detail = str(exc)
        if exc.code == "missing_holder_range":
            detail += " (give --attacker-range melee|ranged)"
        elif "target:bonus_health" in detail:
            detail += " (give --target-bonus-health or --target-champion)"
        return detail

    def _modifiers(
        self, part_kind: str, crit: bool, target_stats: Mapping[str, Fraction]
    ) -> tuple[list[tuple[str, Fraction]], list[tuple[str, Fraction]], list[Label], list[str]]:
        dealt: list[tuple[str, Fraction]] = []
        taken: list[tuple[str, Fraction]] = []
        labels: list[Label] = []
        notes: list[str] = []
        for effect in self.dealt:
            if self._mode(effect) and _conditions_hold(effect, self.target, part_kind, crit):
                if effect.component.get("source") != "all":
                    raise RotationError(f"{effect.title}: source is not modelled")
                dealt.append((effect.title, self._percent(effect, target_stats)))
                labels.append(effect.label)
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
        mitigation = mitigate(
            raw,
            damage_type,
            self.target.resistance(damage_type),
            penetration_modifiers(self.sheet, damage_type),
        )
        if damage_type in PENETRATION:
            percent, flat = PENETRATION[damage_type]
            labels = [*labels, self.sheet[percent].label, self.sheet[flat].label]
        dealt, taken, modifier_labels, modifier_notes = self._modifiers(kind, crit, target_stats)
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
            else:
                labels.append(Label.PENDING)
                notes.append("the kit does not declare whether it applies life steal")
            if applied_life_steal:
                labels.append(self.life_steal.label)
        if omnivamp:
            labels.append(self.omnivamp.label)
            if part.kind == "ability":
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

    def _counted(
        self, step: Step, target_stats: Mapping[str, Fraction], counters: dict[str, int]
    ) -> list[Part]:
        """Effects on every Nth attack: count this attack and fire those that reach N."""
        parts: list[Part] = []
        for effect in [*self.counted, *self.counted_repeats]:
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
            value = self._limited(effect, self._percent(effect, target_stats))
            damage_type = DamageType(str(effect.component.get("damage_type")))
            parts.append(
                self._part(
                    "on_hit",
                    f"{effect.title} ({effect.name}){suffix}",
                    damage_type,
                    value,
                    [effect.label] if extra is None else [effect.label, extra],
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
        # Attack counters start at zero; Energized starts ready (attack-counters.md).
        counters = {effect.title: 0 for effect in [*self.counted, *self.counted_repeats]}
        energized = bool(self.energized)
        for index, step in enumerate(steps, start=1):
            target_stats = {**self.target.stats, "current_health": health}
            if step.slot is None:
                empowered = charged and step.spellblade and bool(self.spellblade)
                charged = False
                name = "critical basic attack" if step.crit else "basic attack"
                if empowered:
                    name += " with Spellblade"
                parts = self._attack(step, target_stats, empowered)
                parts += self._counted(step, target_stats, counters)
                if energized:
                    energized = False
                    name += " (Energized)"
                    parts += self._on_hit(self.energized, step, target_stats)
            else:
                name, parts = self._ability(step, target_stats)
                charged = True
                if energized and self.galvanize and parts and self.target.kind == "champion":
                    energized = False
                    name += " (Energized)"
                    parts += self._on_hit(self.energized, step, target_stats)
                    self.notes.append(
                        f"{self.galvanize[0].title}: the ability's damage to a champion "
                        "triggered Energized"
                    )
            outcome = StepOutcome(
                index, step, name, tuple(parts), health, weakest(part.label for part in parts)
            )
            outcomes.append(outcome)
            health = outcome.health_after
        if self.energized:
            self.notes.append(
                "Energized starts ready and fires once; recharging by moving and attacking "
                "is not modelled"
            )
        if counters:
            self.notes.append("attack counters ignore their time windows (stacks expiring)")
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
) -> RotationOutcome:
    """Damage of every step against ``target``, carrying its current health forward.

    ``holder_range`` is the attacker's melee/ranged classification; it is only
    required by effects that branch on it and is never guessed. ``crit_base``
    is only required by critical steps.
    """
    if not steps:
        raise RotationError("the rotation has no steps")
    rotation = _Rotation(kit, sheet, ranks, target, crit_base, holder_range, inputs or {})
    return rotation.run(steps)
