"""Item/rune/passive effect extraction, conditions, modifiers, and healing."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from fractions import Fraction
from typing import Any

from ..damage import DamageType, format_number, mitigate
from ..errors import RotationError
from ..formula import OBJECT_OPS, CompiledFormula, FormulaError, compile_formula, evaluate_formula
from ..item_combat import SPECIALIZED_ITEM_EFFECTS
from ..kit import Kit
from ..resources import ResourceEvent
from ..scenario import PENETRATION, Target, penetration_modifiers
from ..stats import EVIDENCE_LABEL, ItemData, Label, StatBlocked, sheet_effect_reason, weakest
from ..summoners import exhaust_values
from ..survival import HealEvent, ShieldEvent, absorb_shield, scale_healing, scale_shield
from .models import (
    ATTACK_SPEED_STATS,
    COUNTED_TRIGGERS,
    DAMAGE_KINDS,
    LIMIT_CONDITIONS,
    NO_HEALING,
    REDUCED_OMNIVAMP_KINDS,
    RESISTANCE_STATS,
    TARGET_KIND_CONDITIONS,
    Healing,
    Part,
)


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
    # ``"passive"`` or ``"active"`` (active effects are cast via ``item:<id>`` steps).
    kind: str = "passive"
    # Optional ranged duration override (e.g. Youmuu's Wraith Step: 6 s melee / 4 s ranged).
    ranged_duration: Fraction | None = None
    # Active empowers the next basic attack (Titanic Hydra) and optionally resets attack timer.
    empowers_next_attack: bool = False
    resets_attack_timer: bool = False
    _compiled_formula: CompiledFormula | None = field(
        default=None, init=False, repr=False, compare=False
    )

    @property
    def title(self) -> str:
        return f"{self.item} {self.id}"


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


_ROTATION_EFFECTS_CACHE: dict[
    tuple[int, str, str | None], tuple[ItemData, tuple[_Effect, ...], tuple[str, ...], bool]
] = {}
_ROTATION_EFFECTS_CACHE_MAX = 2048


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
        cache_key = (id(item), owner, target_kind)
        cached = _ROTATION_EFFECTS_CACHE.get(cache_key)
        if cached is not None and cached[0] is item:
            _, effs_t, notes_t, w_flag = cached
        else:
            item_effs: list[_Effect] = []
            item_notes: list[str] = []
            item_weakened = False
            if item.effect_review != "complete":
                item_notes.append(
                    f"{owner} {item.id}: effect review {item.effect_review}; "
                    "effects missing from the catalog are not applied"
                )
                item_weakened = True
            for effect in item.effects:
                reason = sheet_effect_reason(effect)
                if reason is not None:
                    item_notes.append(
                        f"{owner} {item.id} {effect.get('id')}: "
                        f"applied by the stat sheet ({reason})"
                    )
                    continue
                status = effect.get("model_status")
                if (item.id, str(effect.get("id"))) in SPECIALIZED_ITEM_EFFECTS and (
                    status == "evaluable"
                ):
                    continue
                components = effect.get("components") or ()
                if status != "evaluable":
                    item_notes.append(
                        f"{owner} {item.id} {effect.get('id')}: {status}, not applied"
                    )
                    item_weakened |= _could_apply(effect, target_kind) and any(
                        c.get("kind") in DAMAGE_KINDS for c in components
                    )
                    continue
                label = EVIDENCE_LABEL.get(str(effect.get("evidence_confidence")), Label.DERIVED)
                for component in components:
                    item_effs.append(
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
                            _seconds_of(component.get("duration_seconds")) or _duration(effect),
                            (component.get("target") or effect.get("target") or {}).get("kind"),
                            _seconds_of(effect.get("cooldown_seconds")),
                            _refund(effect),
                            _window(effect),
                            _max_stacks(effect),
                            _alternation(effect),
                            _combo_required(effect),
                            str(effect.get("kind", "passive")),
                            _seconds_of(effect.get("ranged_duration_seconds")),
                            bool(effect.get("empowers_next_attack", False)),
                            bool(effect.get("resets_attack_timer", False)),
                        )
                    )
            effs_t = tuple(item_effs)
            notes_t = tuple(item_notes)
            w_flag = item_weakened
            if len(_ROTATION_EFFECTS_CACHE) >= _ROTATION_EFFECTS_CACHE_MAX:
                _ROTATION_EFFECTS_CACHE.pop(next(iter(_ROTATION_EFFECTS_CACHE)))
            _ROTATION_EFFECTS_CACHE[cache_key] = (item, effs_t, notes_t, w_flag)
        effects.extend(effs_t)
        notes.extend(notes_t)
        weakened |= w_flag
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


def _formula_references_stat(formula: Any, stat_name: str) -> bool:
    if not isinstance(formula, Mapping):
        return False
    if formula.get("stat") == stat_name:
        return True
    for value in formula.values():
        if isinstance(value, Mapping) and _formula_references_stat(value, stat_name):
            return True
        if (
            isinstance(value, Sequence)
            and not isinstance(value, (str, bytes))
            and any(_formula_references_stat(item, stat_name) for item in value)
        ):
            return True
    return False


def _kit_uses_move_speed(kit: Kit | None) -> bool:
    if kit is None:
        return False
    cached = kit._uses_move_speed
    if cached is not None:
        return cached
    uses = False
    for ability in kit.abilities.values():
        for case in ability.cases:
            if any(_formula_references_stat(part.formula, "move_speed") for part in case.parts):
                uses = True
                break
        if uses:
            break
        if any(
            _formula_references_stat(pe.formula, "move_speed") for pe in ability.passive_effects
        ):
            uses = True
            break
    object.__setattr__(kit, "_uses_move_speed", uses)
    return uses


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


class _EffectsMixin:
    """Effect filtering, modifier stacking, part mitigation, and healing methods."""

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
        amount = (
            scale_healing(
                raw, hsp=hsp_val, revitalize_amp=rev_amp, grievous=gw_rate, uses_hsp=uses_hsp
            )
            * self.self_heal_amp
        )
        labels = [label]
        out_notes = list(notes)
        if uses_hsp and hsp_val:
            labels.append(self.hsp.label)
            out_notes.append(f"heal & shield power +{format_number(hsp_val * 100)}%")
        if rev_amp:
            labels.append(Label.DERIVED)
            out_notes.append(f"Revitalize <40% HP +{format_number(rev_amp * 100)}%")
        if self.self_heal_amp != 1:
            labels.extend(self.self_amp_labels)
            out_notes.extend(n for n in self.self_amp_notes if "healing" in n)
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
        amount = scale_shield(raw, hsp=hsp_val, revitalize_amp=rev_amp) * self.self_shield_amp
        labels = [label]
        out_notes = list(notes)
        if hsp_val:
            labels.append(self.hsp.label)
            out_notes.append(f"heal & shield power +{format_number(hsp_val * 100)}%")
        if rev_amp:
            labels.append(Label.DERIVED)
            out_notes.append(f"Revitalize <40% HP +{format_number(rev_amp * 100)}%")
        if self.self_shield_amp != 1:
            labels.extend(self.self_amp_labels)
            out_notes.extend(n for n in self.self_amp_notes if "shielding" in n)
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
        if (
            effect.component.get("kind") in DAMAGE_KINDS
            and owner == "attacker"
            and effect.trigger not in {"taking_damage", "taking_attack"}
        ):
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
        component = effect.component
        kind = component.get("kind")
        if self.timeline is None:
            self.notes.append(
                f"attacker {effect.title}: lasts {format_number(effect.duration)} s; "
                "applied only with --timeline"
            )
            ms_only = kind == "stat_modifier" and str(component.get("stat")) == "move_speed"
            if not ms_only or self.ms_affects_damage:
                self.weakened |= not _excluded(effect, self.target.kind)
            return
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
            compiled = effect._compiled_formula
            if compiled is None:
                compiled = compile_formula(effect.component.get("formula"), ops=OBJECT_OPS)
                object.__setattr__(effect, "_compiled_formula", compiled)
            result = evaluate_formula(
                compiled,
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
            source = window.effect.component.get("source")
            if source == "ability" and part_kind != "ability":
                continue
            if _conditions_hold(window.effect, self.target, part_kind, crit, target_stats):
                dealt.append((window.effect.title, window.value))
                labels += window.labels
        ic_dealt, ic_labels, ic_notes = self.item_combat.dealt_modifier(
            part_kind, self.now, slot=slot
        )
        if ic_dealt:
            dealt.append(("item_combat", ic_dealt * 100))
            labels.extend(ic_labels)
            notes.extend(ic_notes)
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
        if self.attacker_exhausted and damage_type is not DamageType.TRUE:
            ex_pct = Fraction(35)
            if self.summoner_data is not None and "SummonerExhaust" in self.summoner_data.spells:
                ex_dr, _, _ = exhaust_values(self.summoner_data.spells["SummonerExhaust"])
                ex_pct = ex_dr * 100
            taken.append(("summoner:SummonerExhaust", -ex_pct))
            labels.append(self.summoner_label)
            notes.append(f"summoner:SummonerExhaust (-{format_number(ex_pct)}% non-true damage)")
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
        pct_shreds: list[Fraction] = []
        for eff in self.shred_percent_effects:
            if RESISTANCE_STATS.get(str(eff.component.get("stat"))) is not damage_type:
                continue
            count = self.shred_stacks.get(eff.title, 0)
            if not count:
                continue
            last = self.shred_stacked_at.get(eff.title)
            if (
                self.timeline is not None
                and eff.window is not None
                and last is not None
                and self.now - last >= eff.window
            ):
                continue
            per_stack, stat_labels = self._value(eff, target_stats)
            pct = abs(per_stack) * count / 100
            pct_shreds.append(pct)
            labels = [*labels, eff.label, *stat_labels]
            notes = (
                *notes,
                f"{eff.title} ({eff.name}): -{format_number(pct * 100)}% "
                f"{eff.component.get('stat')} ({count}x)",
            )
        if pct_shreds:
            modifiers = replace(
                modifiers,
                percent_reduction=(*modifiers.percent_reduction, *pct_shreds),
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
        healing = self._healing(part, life_steal_tag)
        if healing is not NO_HEALING:
            object.__setattr__(part, "healing", healing)
        return part

    def _healing(self, part: Part, tag: Mapping[str, Any] | None) -> Healing:
        """Life steal and omnivamp healing of ``part`` (life-steal-and-omnivamp.md)."""
        if part.kind == "summoner":
            return NO_HEALING
        life_steal = self.life_steal.total()
        omnivamp = self.omnivamp.total() + self.item_combat.dynamic_bonus_omnivamp(self.now)
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
        amount = (
            scale_healing(
                raw_heal,
                hsp=Fraction(0),
                revitalize_amp=rev_amp,
                grievous=gw_rate,
                uses_hsp=False,
            )
            * self.self_heal_amp
        )
        if raw_heal > 0:
            if rev_amp:
                labels.append(Label.DERIVED)
                notes.append(f"Revitalize <40% HP +{format_number(rev_amp * 100)}%")
            if self.self_heal_amp != 1:
                labels.extend(self.self_amp_labels)
                notes.extend(n for n in self.self_amp_notes if "healing" in n)
            if gw_rate:
                labels.append(gw_label)
                notes.append(gw_source)
                self.grievous_used = True
        return Healing(applied_life_steal, omnivamp, amount, weakest(labels), tuple(notes))

    def _limited(self, effect: _Effect, value: Fraction) -> Fraction:
        for limit in effect.limits:
            condition = str(limit.get("condition"))
            kinds = LIMIT_CONDITIONS.get(condition)
            if kinds is None or limit.get("kind") != "maximum" or limit.get("unit") != "flat":
                raise RotationError(f"{effect.title}: limit {condition!r} is not modelled")
            if _target_kind(self.target, f"{effect.title} limit") in kinds:
                value = min(value, Fraction(str(limit["value"])))
        return value
