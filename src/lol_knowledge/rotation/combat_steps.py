"""Resolution of attacks, ability casts, item actives, and summoner spells."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from fractions import Fraction

from ..damage import DamageType, format_number, mitigate
from ..errors import KitError, RotationError, StatsError
from ..formula import ABILITY_OPS, FormulaError, evaluate_formula
from ..item_combat import ItemHeal, ItemProc
from ..kit import ActiveEffectSpec, ability_damage
from ..runes import scale_item_cooldown
from ..stats import Label, weakest
from ..summoners import (
    barrier_duration,
    barrier_shield,
    cleanse_tenacity,
    effective_cooldown,
    exhaust_values,
    ghost_ms,
    heal_amount,
    heal_ms,
    ignite_damage,
    ignite_duration,
    ignite_grievous,
    smite_damage,
    teleport_ms,
)
from ..survival import HealEvent, ShieldEvent
from .effects import _conditions_hold, _Effect, _key, _Window
from .models import (
    ATTACK_SPEED_STATS,
    CRIT_DAMAGE_REDUCTIONS,
    PATCH_CRIT_MULTIPLIER,
    TIMED_KINDS,
    CritBase,
    Part,
    Step,
)


class _CombatStepsMixin:
    """Step-level combat resolvers for attacks, abilities, actives, and summoners."""

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

    def _normal_crit_value(self) -> Fraction | None:
        """Normal crit multiplier (e.g. 2.0, or 2.3 with IE) for forced-crit items (6610, 2512)."""
        if not isinstance(self.crit_base, CritBase):
            return None
        bonus = self.sheet["crit_damage_bonus"]
        multiplier = self.crit_base.value + bonus.total()
        reduction = CRIT_DAMAGE_REDUCTIONS.get(self.sheet.champion.id)
        if reduction is not None:
            multiplier *= 1 - reduction
        return multiplier

    def _emit_item_proc(
        self,
        proc: ItemProc,
        target_stats: Mapping[str, Fraction],
        clock: Fraction,
    ) -> tuple[Part, list[HealEvent]]:
        ls_tag = {"value": True} if proc.life_steal else None
        part = self._part(
            proc.kind,
            proc.source,
            proc.damage_type,
            proc.raw,
            [proc.label],
            False,
            target_stats,
            proc.notes,
            life_steal_tag=ls_tag,
            apply_modifiers=proc.apply_modifiers,
            targets_hit=proc.targets_hit,
            aoe=proc.aoe,
        )
        heals: list[HealEvent] = []
        if proc.item_id == "2502" and part.damage > 0:
            raw_heal = part.damage * Fraction(5, 2)
            heals.append(
                self._make_heal_event(
                    "2502 anguish (drain heal)",
                    raw_heal,
                    Label.DERIVED,
                    clock,
                    uses_hsp=True,
                    notes=(f"250% of {format_number(part.damage)} post-mitigation damage",),
                )
            )
        return part, heals

    def _convert_item_heals(
        self, items_heals: Sequence[ItemHeal], clock: Fraction
    ) -> list[HealEvent]:
        return [
            self._make_heal_event(
                h.source, h.raw, h.label, clock, uses_hsp=h.uses_hsp, notes=h.notes
            )
            for h in items_heals
        ]

    def _attack(
        self,
        step: Step,
        target_stats: Mapping[str, Fraction],
        empowered: bool = False,
        active_empowers: Sequence[_Effect] = (),
        clock: Fraction = Fraction(0),
    ) -> tuple[list[Part], list[HealEvent]]:
        attack_damage = self.sheet["attack_damage"]
        raw = attack_damage.total()
        labels = [attack_damage.label]
        notes: list[str] = []
        source = "basic attack: total attack damage"
        ov = self.item_combat.on_attack(
            step_crit=step.crit,
            normal_crit_multiplier=self._normal_crit_value(),
            clock=clock,
            attacker_hp=self.attacker_hp,
            attacker_max_hp=self.attacker_max_hp,
        )
        eff_crit = step.crit or ov.crit_multiplier_override is not None
        crit_info = self._crit_multiplier(step)
        if crit_info is not None:
            multiplier, crit_labels, crit_notes, crit_suffix = crit_info
            raw *= multiplier
            labels += crit_labels
            notes += crit_notes
            source += crit_suffix
        elif ov.crit_multiplier_override is not None:
            raw *= ov.crit_multiplier_override
            labels.extend(ov.labels)
            notes.extend(ov.notes)
            source += f" x forced crit multiplier {format_number(ov.crit_multiplier_override)}"
        else:
            labels.extend(ov.labels)
            notes.extend(ov.notes)
        parts = [
            self._part(
                "attack", source, DamageType.PHYSICAL, raw, labels, eff_crit, target_stats, notes
            )
        ]
        if ov.bonus_true_damage_ratio > 0:
            parts.append(
                self._part(
                    "item",
                    "2512 opening-barrage (Andanada inicial: bonus true damage)",
                    DamageType.TRUE,
                    raw * ov.bonus_true_damage_ratio,
                    [Label.OFFICIAL],
                    False,
                    target_stats,
                    ("15% of critical attack damage as bonus true damage",),
                    apply_modifiers=False,
                )
            )
        attack_heals = self._convert_item_heals(ov.heals, clock)
        for proc in ov.extra_procs:
            p_part, p_heals = self._emit_item_proc(proc, target_stats, clock)
            parts.append(p_part)
            attack_heals.extend(p_heals)
        replaced = {eff.item for eff in active_empowers}
        active_on_hit = [e for e in self.on_hit if e.item not in replaced] + [
            e for e in active_empowers if not e.component.get("secondary_only")
        ]
        parts += self._on_hit(active_on_hit, step, target_stats)
        if empowered:
            parts += self._on_hit(self.spellblade, step, target_stats)
            for repeat in self.repeats:
                parts += self._on_hit(
                    active_on_hit, step, target_stats, f" - again by {repeat.title}", repeat.label
                )
        active_secondary = [e for e in self.secondary_attacks if e.item not in replaced] + [
            e for e in active_empowers if e.component.get("secondary_only") is True
        ]
        parts += self._secondary_attacks(step, target_stats, active_secondary)
        return parts, attack_heals

    def _secondary_attacks(
        self,
        step: Step,
        target_stats: Mapping[str, Fraction],
        effects: Sequence[_Effect] | None = None,
    ) -> list[Part]:
        """Secondary-only attack splash and bolts (Runaan's Hurricane, Tiamat/Hydras)."""
        candidates = self.secondary_attacks if effects is None else effects
        if self.target_count <= 1 or not candidates:
            return []
        parts: list[Part] = []
        for effect in candidates:
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
                # OBJ-05: Guinsoo (3124) Phantom Hit grants +1 Kraken Slayer (6672) stack.
                if effect.item == "3124":
                    for k_eff in self.counted:
                        if k_eff.item != "6672":
                            continue
                        counters[k_eff.title] += 1
                        if clock is not None:
                            self.last_counted[k_eff.title] = clock
                        if counters[k_eff.title] >= (k_eff.every or 3):
                            counters[k_eff.title] = 0
                            parts += self._on_hit(
                                [k_eff],
                                step,
                                target_stats,
                                f" - Phantom Hit stack from {effect.title}",
                                Label.DERIVED,
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

    def _item_active(
        self,
        step: Step,
        target_stats: Mapping[str, Fraction],
        clock: Fraction,
    ) -> tuple[str, list[Part], list[HealEvent], list[ShieldEvent], bool]:
        """Execute an ``item:<id>`` active step (damage, heal, shield, buff or attack empower)."""
        assert step.item_id is not None
        item_id = step.item_id
        equipped = {item.id for item in self.sheet.items}
        if item_id not in equipped:
            raise RotationError(f"step {step.text!r}: item {item_id} is not equipped")
        if self.item_combat.is_potion_active(item_id):
            p_name, p_heals = self.item_combat.cast_potion(item_id, clock)
            return p_name, [], self._convert_item_heals(p_heals, clock), [], False
        effects = self.item_actives.get(item_id)
        if not effects:
            raise RotationError(
                f"step {step.text!r}: item {item_id} has no modelled combat active effect"
            )
        if self.timeline is not None:
            ready_at = self.active_ready.get(item_id, Fraction(0))
            if clock < ready_at:
                raise RotationError(
                    f"step {step.text!r}: item {item_id} is on cooldown until "
                    f"{format_number(ready_at)} s"
                )
            cd = effects[0].cooldown
            if cd is not None:
                self.active_ready[item_id] = clock + scale_item_cooldown(
                    cd, self.rune_combat.item_haste
                )
        self.cast_actives.add(item_id)
        label_name = effects[0].name or effects[0].id
        step_name = f"item {item_id} ({label_name})"
        parts: list[Part] = []
        heals: list[HealEvent] = []
        shields: list[ShieldEvent] = []
        reset_attack = any(eff.resets_attack_timer for eff in effects)

        empower_effects = [eff for eff in effects if eff.empowers_next_attack]
        if empower_effects:
            self.empowered_attacks[item_id] = empower_effects
            return step_name, parts, heals, shields, reset_attack

        step_targets = step.targets if step.targets is not None else self.target_count
        for eff in effects:
            kind = eff.component.get("kind")
            if not _conditions_hold(eff, self.target, "trigger", False, target_stats):
                continue
            value, stat_labels = self._value(eff, target_stats)
            labels = [eff.label, *stat_labels]
            source = f"{eff.title} ({eff.name})"
            if kind == "damage":
                aoe = eff.component.get("aoe")
                hits = step_targets if aoe is True else 1
                damage_type = DamageType(str(eff.component.get("damage_type")))
                parts.append(
                    self._part(
                        "item",
                        source,
                        damage_type,
                        value,
                        labels,
                        False,
                        target_stats,
                        life_steal_tag=eff.component.get("applies_life_steal"),
                        targets_hit=hits,
                        aoe=aoe if isinstance(aoe, bool) else None,
                    )
                )
            elif kind == "healing" and eff.affects == "self":
                heals.append(self._make_heal_event(source, value, weakest(labels), clock))
            elif kind == "shield" and eff.affects == "self":
                sh_type = str(eff.component.get("shield_type", "normal"))
                shields.append(
                    self._make_shield_event(source, value, weakest(labels), shield_type=sh_type)
                )
            elif kind in TIMED_KINDS and eff.affects == "self":
                dur = eff.duration
                if eff.ranged_duration is not None:
                    if self.holder_range is None:
                        raise RotationError(
                            f"{eff.title}: ranged_duration_seconds needs --attacker-range "
                            "melee|ranged"
                        )
                    if self.holder_range == "ranged":
                        dur = eff.ranged_duration
                if self.timeline is None:
                    self.notes.append(
                        f"attacker {eff.title}: lasts {format_number(dur or Fraction(0))} s; "
                        "applied only with --timeline"
                    )
                    ms_only = (
                        kind == "stat_modifier" and str(eff.component.get("stat")) == "move_speed"
                    )
                    if not ms_only or self.ms_affects_damage:
                        self.weakened = True
                elif dur is not None:
                    self.windows[_key(eff)] = _Window(eff, clock + dur, value, tuple(labels))
                    if kind == "stat_modifier":
                        self.speed_changed |= str(eff.component.get("stat")) in ATTACK_SPEED_STATS
        return step_name, parts, heals, shields, reset_attack

    def _ability(self, step: Step, target_stats: Mapping[str, Fraction]) -> tuple[str, list[Part]]:
        assert step.slot is not None
        ability = self.kit.ability(step.slot)
        if step.slot not in self.ranks:
            raise RotationError(f"step {step.text}: learn {step.slot} first with --learned")
        rank = self.ranks[step.slot]
        if not ability.cases:
            if step.case is not None:
                raise RotationError(f"step {step.text}: {step.slot} has no damage cases")
            if not ability.active_effects and not ability.cc_effects:
                raise RotationError(
                    f"step {step.text}: {step.slot} has no modelled damage cases or active effects"
                )
            if not 1 <= rank <= ability.max_rank:
                raise RotationError(
                    f"step {step.text}: {step.slot} rank must be 1..{ability.max_rank}"
                )
            return f"{ability.slot} {ability.name} rank {rank}", []
        if step.case is None and len(ability.cases) > 1:
            names = ", ".join(f"{step.slot}.{case.id}" for case in ability.cases)
            raise RotationError(f"step {step.text}: pick one case ({names})")
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

    def _active_duration(self, effect: ActiveEffectSpec, rank: int) -> Fraction | None:
        if effect.duration_seconds is not None:
            return effect.duration_seconds
        if effect.duration_formula is not None:
            try:
                res = evaluate_formula(
                    effect.duration_formula,
                    self.stats,
                    rank=rank,
                    level=self.sheet.level,
                    inputs=self.inputs,
                    ops=ABILITY_OPS,
                )
            except FormulaError as exc:
                raise RotationError(f"{effect.id} duration: {exc}") from exc
            return res.exact
        return None

    def _apply_ability_active_effects(
        self,
        slot: str,
        case_id: str | None,
        target_stats: Mapping[str, Fraction],
        clock: Fraction,
        ability_parts: Sequence[Part] = (),
        *,
        defer_survival: bool = False,
    ) -> tuple[list[HealEvent], list[ShieldEvent]]:
        """Apply Q/W/E/R ``active_effects`` (shields, heals, stat steroids, DR notes) on cast."""
        ability = self.kit.ability(slot)
        if not ability.active_effects:
            return [], []
        rank = self.ranks[slot]
        resolved_case = case_id
        if resolved_case is None and len(ability.cases) == 1:
            resolved_case = ability.cases[0].id
        heals: list[HealEvent] = []
        shields: list[ShieldEvent] = []
        eval_stats = dict(self.stats)
        if (
            self.attacker_hp is not None
            and self.attacker_max_hp is not None
            and self.attacker_max_hp > 0
        ):
            max_hp = self.attacker_max_hp
            cur_hp = self.attacker_hp
            miss_frac = max(Fraction(0), min(Fraction(1), (max_hp - cur_hp) / max_hp))
        else:
            max_hp = eval_stats.get("health", Fraction(0))
            miss_in = self.inputs.get("champion_missing_health_fraction", 0)
            miss_frac = max(Fraction(0), min(Fraction(1), Fraction(str(miss_in))))
            cur_hp = max_hp * (1 - miss_frac)
        eval_stats["max_health"] = max_hp
        eval_stats["current_health"] = cur_hp
        eval_stats["missing_fraction_health"] = miss_frac
        for eff in ability.active_effects:
            if not eff.applies_to_case(resolved_case):
                continue
            if defer_survival and eff.kind in {
                "shield",
                "heal",
                "recent_damage_shield",
                "recent_damage_heal",
                "damage_taken_modifier",
                "dodge_attacks",
                "spell_shield",
                "block_first_hit",
                "invulnerable",
                "cleanse",
                "cc_immune",
            }:
                continue
            if (
                defer_survival
                and eff.kind == "stat_bonus"
                and eff.stat
                in {
                    "health",
                    "armor",
                    "magic_resist",
                }
            ):
                continue
            try:
                res = evaluate_formula(
                    eff.formula,
                    eval_stats,
                    rank=rank,
                    level=self.sheet.level,
                    target_stats=target_stats,
                    inputs=self.inputs,
                    ops=ABILITY_OPS,
                )
            except FormulaError as exc:
                raise RotationError(f"{slot}.{eff.id}: {exc}") from exc
            assert res.exact is not None
            if res.exact <= 0 and eff.kind in {"shield", "heal"}:
                continue
            dep_labels = [self.origin[k][1] for k in res.dependencies if k in self.origin]
            if any(k.startswith("target:") for k in res.dependencies):
                dep_labels.append(self.target.label)
            eff_label = weakest([eff.label, *dep_labels])
            dur = self._active_duration(eff, rank)
            src = f"kit:{self.kit.champion} {slot}.{eff.id} ({eff.name})"
            if eff.kind == "shield":
                s_notes = (
                    (f"{eff.name} ({format_number(dur)} s)",) if dur is not None else (eff.name,)
                )
                shields.append(
                    self._make_shield_event(
                        src,
                        res.exact,
                        eff_label,
                        shield_type=eff.shield_type,
                        duration=dur,
                        notes=s_notes,
                    )
                )
            elif eff.kind == "heal":
                h_notes = (
                    (f"{eff.name} (over {format_number(dur)} s)",)
                    if eff.over_duration and dur is not None
                    else (eff.name,)
                )
                heals.append(
                    self._make_heal_event(
                        src,
                        res.exact,
                        eff_label,
                        clock,
                        uses_hsp=eff.uses_hsp,
                        notes=h_notes,
                    )
                )
            elif eff.kind == "stat_bonus" and eff.stat is not None:
                end_t = clock + dur if (self.timeline is not None and dur is not None) else None
                key = f"{slot}.{eff.id}"
                self._ability_stat_buffs[key] = (
                    end_t,
                    eff.stat,
                    eff.mode,
                    res.exact,
                    src,
                    eff_label,
                )
                if self.timeline is not None and eff.stat in ATTACK_SPEED_STATS:
                    self.speed_changed = True
                dur_txt = f" for {format_number(dur)} s" if dur is not None else ""
                self.notes.append(f"{src}: {eff.stat} buff active{dur_txt}")
            elif eff.kind == "damage_dealt_heal":
                if eff.part_index is not None:
                    dealt = (
                        ability_parts[eff.part_index].damage
                        if 0 <= eff.part_index < len(ability_parts)
                        else Fraction(0)
                    )
                    part_labels = (
                        [ability_parts[eff.part_index].label]
                        if 0 <= eff.part_index < len(ability_parts)
                        else []
                    )
                else:
                    dealt = sum((p.damage for p in ability_parts), start=Fraction(0))
                    part_labels = [p.label for p in ability_parts]
                raw_heal = dealt * res.exact / 100
                if raw_heal > 0:
                    heals.append(
                        self._make_heal_event(
                            src,
                            raw_heal,
                            weakest([eff_label, *part_labels]),
                            clock,
                            uses_hsp=eff.uses_hsp,
                            notes=(
                                f"{eff.name} ({format_number(res.exact)}% of "
                                f"{format_number(dealt)} post-mitigation damage)",
                            ),
                        )
                    )
            elif eff.kind in {"recent_damage_shield", "recent_damage_heal"}:
                min_v: Fraction | None = None
                max_v: Fraction | None = None
                if eff.min_formula is not None:
                    min_res = evaluate_formula(
                        eff.min_formula,
                        eval_stats,
                        rank=rank,
                        level=self.sheet.level,
                        target_stats=target_stats,
                        inputs=self.inputs,
                        ops=ABILITY_OPS,
                    )
                    min_v = min_res.exact
                if eff.max_formula is not None:
                    max_res = evaluate_formula(
                        eff.max_formula,
                        eval_stats,
                        rank=rank,
                        level=self.sheet.level,
                        target_stats=target_stats,
                        inputs=self.inputs,
                        ops=ABILITY_OPS,
                    )
                    max_v = max_res.exact
                raw_val = Fraction(0)
                used_note = ""
                if eff.input_name is not None and eff.input_name in self.inputs:
                    stored = max(Fraction(0), Fraction(str(self.inputs[eff.input_name])))
                    raw_val = stored * res.exact / 100
                    used_note = (
                        f"{eff.name} (from --input {eff.input_name}={format_number(stored)})"
                    )
                elif min_v is not None and min_v > 0:
                    raw_val = min_v
                    used_note = f"{eff.name} (minimum baseline, 0 stored damage)"
                if min_v is not None and raw_val > 0:
                    raw_val = max(raw_val, min_v)
                if max_v is not None and raw_val > 0:
                    raw_val = min(raw_val, max_v)
                if raw_val > 0:
                    if eff.kind == "recent_damage_shield":
                        shields.append(
                            self._make_shield_event(
                                src,
                                raw_val,
                                eff_label,
                                shield_type=eff.shield_type,
                                duration=dur,
                                notes=(used_note,),
                            )
                        )
                    else:
                        heals.append(
                            self._make_heal_event(
                                src,
                                raw_val,
                                eff_label,
                                clock,
                                uses_hsp=eff.uses_hsp,
                                notes=(used_note,),
                            )
                        )
                else:
                    hint = f" or --input {eff.input_name}=<damage>" if eff.input_name else ""
                    self.notes.append(f"{src}: depends on recent damage taken (use survive{hint})")
            elif eff.kind == "damage_taken_modifier":
                dur_txt = f" for {format_number(dur)} s" if dur is not None else ""
                self.notes.append(f"{src}: defensive damage reduction{dur_txt} (use survive)")
            elif eff.kind in {
                "dodge_attacks",
                "spell_shield",
                "block_first_hit",
                "invulnerable",
                "cleanse",
                "cc_immune",
            }:
                dur_txt = f" for {format_number(dur)} s" if dur is not None else ""
                self.notes.append(f"{src}: defensive {eff.kind}{dur_txt} (use survive)")
        return heals, shields

    def _summoner_cast(
        self, step: Step, target_stats: Mapping[str, Fraction], clock: Fraction
    ) -> tuple[str, list[Part], list[HealEvent], list[ShieldEvent]]:
        """Execute a ``summoner:<name>`` step (Ignite, Smite, Barrier, Heal, Ghost, Exhaust…)."""
        assert step.summoner_id is not None
        if self.summoner_data is None:
            raise RotationError(
                f"step {step.text}: summoner spells require "
                "lol-knowledge/derived/summoner-spells.json"
            )
        try:
            sp = self.summoner_data.resolve(step.summoner_id)
        except StatsError as exc:
            raise RotationError(f"step {step.text}: {exc}") from exc
        if self.summoner_loadout and all(eq.id != sp.id for eq in self.summoner_loadout):
            equipped = ", ".join(f"{eq.alias} ({eq.id})" for eq in self.summoner_loadout)
            raise RotationError(
                f"step {step.text}: {sp.name} ({sp.id}) is not in equipped summoners ({equipped})"
            )
        if self.timeline is not None:
            ready_at = self._summoner_ready.get(sp.id, Fraction(0))
            if clock < ready_at:
                raise RotationError(
                    f"step {step.text}: {sp.name} is on cooldown until {format_number(ready_at)} s"
                )
            eff_cd = effective_cooldown(
                sp,
                level=self.sheet.level,
                summoner_haste=self._summoner_haste,
                unleashed=Fraction(str(self.inputs.get("unleashed_teleport", 0))) > 0,
            )
            self._summoner_ready[sp.id] = clock + eff_cd
        else:
            if sp.id in self._summoner_used:
                raise RotationError(
                    f"step {step.text}: {sp.name} can only be cast once without --timeline"
                )
            self._summoner_used.add(sp.id)

        s_lbl = self.summoner_label
        parts: list[Part] = []
        heals: list[HealEvent] = []
        shields: list[ShieldEvent] = []
        title = f"summoner:{sp.id} ({sp.name})"
        self._last_summoner_spec = sp
        self._last_summoner_grievous_until = None
        self._last_summoner_exhaust_until = None
        defer_surv = getattr(self, "_defer_summoner_survival", False)

        if sp.id == "SummonerDot":
            if self.target.kind is not None and self.target.kind != "champion":
                raise RotationError(f"step {step.text}: {sp.name} can only target champions")
            dmg = ignite_damage(sp, self.sheet.level)
            dur = ignite_duration(sp)
            gw = ignite_grievous(sp)
            gw_note = f"{format_number(gw * 100)}% Grievous Wounds for {format_number(dur)} s"
            self._last_summoner_grievous_until = clock + dur
            if self.timeline is not None:
                self._summoner_burns.append((clock + dur, dmg / dur, title, s_lbl, (gw_note,)))
                self.notes.append(
                    f"{title}: {format_number(dmg)} true damage over {dur} s + {gw_note}"
                )
            else:
                parts.append(
                    self._part(
                        "summoner",
                        title,
                        DamageType.TRUE,
                        dmg,
                        [s_lbl],
                        False,
                        target_stats,
                        (f"full {format_number(dur)} s burn without --timeline", gw_note),
                        apply_modifiers=False,
                    )
                )
            return f"summoner {sp.name}", parts, heals, shields

        if sp.id == "SummonerSmite":
            tier = int(Fraction(str(self.inputs.get("smite_tier", 0))))
            try:
                dmg, s_notes = smite_damage(sp, target_kind=self.target.kind, tier=tier)
            except StatsError as exc:
                raise RotationError(f"step {step.text}: {exc}") from exc
            parts.append(
                self._part(
                    "summoner",
                    title,
                    DamageType.TRUE,
                    dmg,
                    [s_lbl],
                    False,
                    target_stats,
                    tuple(s_notes),
                    apply_modifiers=False,
                )
            )
            return f"summoner {sp.name}", parts, heals, shields

        if sp.id == "SummonerBarrier":
            if not defer_surv:
                raw_sh = barrier_shield(sp, self.sheet.level)
                dur = barrier_duration(sp)
                shields.append(
                    self._make_shield_event(
                        title,
                        raw_sh,
                        s_lbl,
                        shield_type="normal",
                        duration=dur,
                        notes=(f"{sp.name} ({format_number(dur)} s)",),
                    )
                )
            return f"summoner {sp.name}", parts, heals, shields

        if sp.id == "SummonerHeal":
            debuffed = Fraction(str(self.inputs.get("heal_debuffed", 0))) > 0
            raw_h = heal_amount(sp, self.sheet.level, debuffed=debuffed)
            ms_pct, ms_dur = heal_ms(sp)
            if not defer_surv:
                h_notes = (
                    (f"+{format_number(ms_pct * 100)}% MS for {format_number(ms_dur)} s",)
                    if not debuffed
                    else (
                        "recent Heal debuff (-50%)",
                        f"+{format_number(ms_pct * 100)}% MS for {format_number(ms_dur)} s",
                    )
                )
                heals.append(self._make_heal_event(title, raw_h, s_lbl, clock, notes=h_notes))
            self._summoner_ms_buffs.append(
                (clock + ms_dur if self.timeline is not None else None, ms_pct, title, s_lbl)
            )
            return f"summoner {sp.name}", parts, heals, shields

        if sp.id == "SummonerHaste":
            ms_pct, dur = ghost_ms(sp, self.sheet.level)
            self._summoner_ms_buffs.append(
                (clock + dur if self.timeline is not None else None, ms_pct, title, s_lbl)
            )
            self.notes.append(
                f"{title}: +{format_number(ms_pct * 100)}% move speed and Ghosted for "
                f"{format_number(dur)} s"
            )
            return f"summoner {sp.name}", parts, heals, shields

        if sp.id == "SummonerExhaust":
            ex_dr, ex_slow, ex_dur = exhaust_values(sp)
            self._last_summoner_exhaust_until = clock + ex_dur
            self.notes.append(
                f"{title}: -{format_number(ex_dr * 100)}% target damage dealt and "
                f"-{format_number(ex_slow * 100)}% slow for {format_number(ex_dur)} s"
            )
            return f"summoner {sp.name}", parts, heals, shields

        if sp.id == "SummonerBoost":
            ten, dur = cleanse_tenacity(sp)
            self.notes.append(
                f"{title}: removes CC (except suppression/airborne) and summoner debuffs + "
                f"{format_number(ten * 100)}% tenacity for {format_number(dur)} s"
            )
            return f"summoner {sp.name}", parts, heals, shields

        if sp.id == "SummonerTeleport":
            if Fraction(str(self.inputs.get("unleashed_teleport", 0))) > 0:
                ms_pct, dur = teleport_ms(sp)
                self._summoner_ms_buffs.append(
                    (clock + dur if self.timeline is not None else None, ms_pct, title, s_lbl)
                )
                self.notes.append(
                    f"{title} (Teleportar desatado): +{format_number(ms_pct * 100)}% MS for "
                    f"{format_number(dur)} s"
                )
            else:
                self.notes.append(f"{title}: map mobility utility (3 s channel)")
            return f"summoner {sp.name}", parts, heals, shields

        dist = format_number(sp.dv("FlashDistance", Fraction(400)))
        self.notes.append(f"{title}: positional blink ({dist} units)")
        return f"summoner {sp.name}", parts, heals, shields
