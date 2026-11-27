"""Single-shot rotation execution runner."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from fractions import Fraction

from ..damage import DamageType, format_number
from ..errors import RotationError
from ..item_combat import ALLY_HEAL_SHIELD_ACTIVES
from ..resources import ResourceEvent, StepResourceCost, resolve_ability_cost
from ..runes import linear_by_level, rune_value
from ..stats import Label, weakest
from ..survival import HealEvent, ShieldEvent
from .models import (
    HOLDER_RANGES,
    Part,
    RotationOutcome,
    Step,
    StepOutcome,
)


class _RunnerMixin:
    """Single-shot full-sequence rotation evaluator."""

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
            if (
                self.timeline is not None
                and step.slot is None
                and step.item_id is None
                and step.summoner_id is None
            ):
                clock = max(clock, next_attack)
            elif self.timeline is not None and step.slot is not None:
                self._cast(step, clock, ready, open_casts)
            parts: list[Part] = []
            heal_events: list[HealEvent] = []
            shield_events: list[ShieldEvent] = []
            resource_events: list[ResourceEvent] = []
            step_cost: StepResourceCost | None = None
            res_before = self.resources.current if self.resources.uses_casting_pool else None
            before = health
            shield_before = shield
            step_shield_shredded = Fraction(0)
            accrued_absorbed = Fraction(0)
            if self.timeline is not None:
                parts, health, shield, accrued_absorbed = self._accrue(clock, health, shield)
                if self._pending_accrued_heals:
                    heal_events.extend(self._pending_accrued_heals)
                    self._pending_accrued_heals.clear()
                resource_events.extend(self.resources.accrue_regen(clock))
            if not self._knights_vow_applied:
                self._knights_vow_applied = True
                kv_heals = self.item_combat.knights_vow_heal()
                if kv_heals:
                    heal_events.extend(self._convert_item_heals(kv_heals, clock))
            accrued_count = len(parts)
            self._set_moment(clock)
            target_stats = self._target_stats(health)
            extra: list[Label] = []
            if step.item_id is not None:
                name, active_parts, act_heals, act_shields, reset_attack = self._item_active(
                    step, target_stats, clock
                )
                parts += active_parts
                heal_events += act_heals
                shield_events += act_shields
                if step.item_id in ALLY_HEAL_SHIELD_ACTIVES:
                    ally_heals = self.item_combat.on_ally_heal_or_shield(clock)
                    heal_events.extend(self._convert_item_heals(ally_heals, clock))
                if reset_attack and self.timeline is not None:
                    next_attack = clock
            elif step.summoner_id is not None:
                name, s_parts, s_heals, s_shields = self._summoner_cast(step, target_stats, clock)
                parts += s_parts
                heal_events += s_heals
                shield_events += s_shields
            elif step.slot is None:
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
                active_empowers = [eff for effs in self.empowered_attacks.values() for eff in effs]
                if active_empowers:
                    self.empowered_attacks.clear()
                name = "critical basic attack" if step.crit else "basic attack"
                if empowered:
                    name += " with Spellblade"
                if active_empowers:
                    seen_names = list(dict.fromkeys(e.name or e.id for e in active_empowers))
                    name += f" ({', '.join(seen_names)})"
                attack_parts, attack_heals = self._attack(
                    step, target_stats, empowered, active_empowers, clock
                )
                parts += attack_parts
                heal_events += attack_heals
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
                    self._apply_cooldown_refunds(clock, ready, target_stats)
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
                ab_heals, ab_shields = self._apply_ability_active_effects(
                    step.slot, step.case, target_stats, clock, ability_parts=ability_parts
                )
                heal_events += ab_heals
                shield_events += ab_shields
                c_heals, c_shields = self._item_survival_events("cast", target_stats, clock)
                heal_events += c_heals
                shield_events += c_shields
                mana_spent = step_cost.amount if step_cost.resource == "mana" else Fraction(0)
                cast_ic_heals = self.item_combat.on_cast(step.slot, mana_spent, clock)
                heal_events.extend(self._convert_item_heals(cast_ic_heals, clock))
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
            if step.item_id is not None or step.summoner_id is not None:
                step_dealt = False
            else:
                step_dealt = (
                    bool(parts[accrued_count:]) if step.slot is None else bool(ability_parts)
                )
            if step_dealt:
                od_parts, od_shields = self._on_damage_procs(step, target_stats, clock, step.slot)
                parts += od_parts
                shield_events += od_shields
                pre_mit = sum((p.raw for p in parts[accrued_count:]), start=Fraction(0))
                post_phys = sum(
                    (
                        p.damage
                        for p in parts[accrued_count:]
                        if p.damage_type is DamageType.PHYSICAL
                    ),
                    start=Fraction(0),
                )
                cur_mana = self.resources.current if self.resources.pool.kind == "mana" else None
                ic_procs, ic_heals, ic_shields, shred_ratio = self.item_combat.on_damage_dealt(
                    pre_mitigation_total=pre_mit,
                    post_mitigation_physical=post_phys,
                    clock=clock,
                    current_mana=cur_mana,
                )
                if shred_ratio > 0 and shield > 0:
                    shredded_amt = shield * shred_ratio
                    step_shield_shredded += shredded_amt
                    shield -= shredded_amt
                for proc in ic_procs:
                    p_part, p_heals = self._emit_item_proc(proc, target_stats, clock)
                    parts.append(p_part)
                    heal_events.extend(p_heals)
                heal_events.extend(self._convert_item_heals(ic_heals, clock))
                for sh in ic_shields:
                    shield_events.append(
                        self._make_shield_event(
                            sh.source,
                            sh.raw,
                            sh.label,
                            duration=sh.duration,
                            notes=sh.notes,
                        )
                    )
                if self.timeline is not None:
                    dealt_types = frozenset(p.damage_type.value for p in parts[accrued_count:])
                    self._open(
                        "on_damage", clock, target_stats, step.slot, damage_types=dealt_types
                    )
            for ev in shield_events:
                self.rune_combat.on_attacker_shield(ev.amount, clock)
            if step.summoner_id is None:
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
                for p_proc in self.passive_combat.on_step(
                    step.slot,
                    step_dealt,
                    clock,
                    self.sheet,
                    target_health_before=before,
                    target_max_health=self.target.stats["max_health"],
                ):
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
            for p_sh in self.passive_combat.on_step_shields(
                step.slot, step_dealt, clock, self.sheet
            ):
                ev_sh = self._make_shield_event(
                    p_sh.source,
                    p_sh.raw,
                    p_sh.label,
                    shield_type=p_sh.shield_type,
                    duration=p_sh.duration,
                    notes=p_sh.notes,
                )
                shield_events.append(ev_sh)
                self.rune_combat.on_attacker_shield(ev_sh.amount, clock)
            # Defender Bone Plating (8473): reduce damage on up to 3 subsequent hits within 1.5 s
            if (
                self.def_bone_rune is not None
                and self.def_bone_charges > 0
                and (
                    self.timeline is None
                    or (self.def_bone_expires is not None and clock <= self.def_bone_expires)
                )
            ):
                def_lvl = self.target.level if self.target.level is not None else self.sheet.level
                block = linear_by_level(
                    rune_value(self.def_bone_rune, "BlockBase"),
                    rune_value(self.def_bone_rune, "BlockMax"),
                    def_lvl,
                )
                for p_idx in range(accrued_count, len(parts)):
                    part = parts[p_idx]
                    if part.primary_damage > 0 and part.kind != "execute":
                        applied = min(part.primary_damage, block)
                        self.def_bone_charges -= 1
                        parts[p_idx] = replace(
                            part,
                            flat_reduction=part.flat_reduction + applied,
                            label=weakest((part.label, self.def_rune_base)),
                            notes=(
                                *part.notes,
                                f"target rune:{self.def_bone_rune.id} {self.def_bone_rune.name} "
                                f"-{format_number(applied)} ({self.def_bone_charges} left)",
                            ),
                        )
                        break

            step_damage = sum((p.primary_damage for p in parts[accrued_count:]), start=Fraction(0))
            step_after, shield_after, step_absorbed = self._absorb_parts(
                parts[accrued_count:], health, shield
            )
            # Trigger Defender Bone Plating AFTER taking >0 real HP damage (not shield-only)
            if (
                self.def_bone_rune is not None
                and health - step_after > 0
                and step_after > 0
                and self.def_bone_charges == 0
            ):
                can_bp = (
                    (not self.def_bone_used_once)
                    if self.timeline is None
                    else (clock >= self.def_bone_ready)
                )
                if can_bp:
                    self.def_bone_used_once = True
                    self.def_bone_charges = int(rune_value(self.def_bone_rune, "BlockCount"))
                    dur = rune_value(self.def_bone_rune, "BlockDuration")
                    if self.timeline is not None:
                        self.def_bone_expires = clock + dur
                        self.def_bone_ready = (
                            clock + dur + rune_value(self.def_bone_rune, "Cooldown")
                        )
                    self.notes.append(
                        f"target rune:{self.def_bone_rune.id} {self.def_bone_rune.name} "
                        f"activated ({self.def_bone_charges} charges)"
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
            complete_parts.extend(self._check_threshold_procs(step_damage, clock, target_stats))
            if complete_parts:
                parts.extend(complete_parts)
                step_after, shield_after, extra_absorbed = self._absorb_parts(
                    complete_parts, step_after, shield_after
                )
                total_absorbed += extra_absorbed
            self._apply_shred_stacks(parts[accrued_count:], clock, target_stats, step.slot)
            parts += self._execute(parts, before, target_stats, total_absorbed)
            final_hp = max(
                Fraction(0),
                before - (sum((p.primary_damage for p in parts), Fraction(0)) - total_absorbed),
            )
            killed_now = before > 0 and final_hp == 0
            if killed_now:
                td_heals = self.item_combat.on_takedown(clock)
                heal_events.extend(self._convert_item_heals(td_heals, clock))
            # 3072 Bloodthirster: convert excess life steal above max HP into Ichor Shield
            if (
                "3072" in self.item_combat.item_ids
                and self.attacker_hp is not None
                and self.attacker_max_hp is not None
            ):
                ls_total = sum(
                    (
                        p.healing.amount
                        * p.healing.life_steal
                        / (p.healing.life_steal + p.healing.omnivamp)
                        for p in parts
                        if p.healing.life_steal > 0 and p.healing.amount > 0
                    ),
                    start=Fraction(0),
                )
                missing_hp = max(Fraction(0), self.attacker_max_hp - self.attacker_hp)
                if ls_total > missing_hp:
                    bt_sh = self.item_combat.on_bloodthirster_overheal(ls_total - missing_hp)
                    if bt_sh is not None:
                        shield_events.append(
                            self._make_shield_event(
                                bt_sh.source,
                                bt_sh.raw,
                                bt_sh.label,
                                duration=bt_sh.duration,
                                notes=bt_sh.notes,
                            )
                        )
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
            for p_res in self.passive_combat.on_step_resources(
                step.slot, step_dealt, killed_now, clock, self.sheet
            ):
                applied = self.resources.restore(
                    p_res.source,
                    p_res.resource,
                    p_res.amount,
                    p_res.label,
                    p_res.notes,
                )
                if applied is not None:
                    resource_events.append(applied)
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
            if self.item_combat.notes:
                self.notes.extend(self.item_combat.notes)
                self.item_combat.notes.clear()
            self.weakened |= self.item_combat.weakened
            self.speed_changed |= self.item_combat.speed_changed
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
                shield_shredded=step_shield_shredded,
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
            if (
                self.timeline is not None
                and step.slot is None
                and step.item_id is None
                and step.summoner_id is None
            ):
                # The next attack: 1 / the attack speed just after this one (timeline.md).
                self._set_moment(clock)
                next_attack = clock + 1 / self.sheet["attack_speed"].total()
        for item_id, active_effs in self.item_actives.items():
            if item_id not in self.cast_actives:
                self.notes.append(
                    f"attacker {active_effs[0].title}: active available "
                    f"(use step item:{item_id} to cast it)"
                )
        pending_end = self.rune_combat.last_pending_time()
        delayed_item_end = (
            max((t for t, _, _, _ in self.delayed_item_procs), default=None)
            if self.delayed_item_procs
            else None
        )
        periodic_end = (
            clock
            if self.timeline is not None and self.item_combat.has_periodic_due(clock)
            else None
        )
        summoner_burn_end = (
            max((b_end for b_end, _, _, _, _ in self._summoner_burns), default=None)
            if self._summoner_burns
            else None
        )
        if (
            self.burning
            or pending_end is not None
            or delayed_item_end is not None
            or periodic_end is not None
            or summoner_burn_end is not None
        ):
            ends = [*(burn.end for burn in self.burning.values())]
            if pending_end is not None:
                ends.append(pending_end)
            if delayed_item_end is not None:
                ends.append(delayed_item_end)
            if periodic_end is not None:
                ends.append(periodic_end)
            if summoner_burn_end is not None:
                ends.append(summoner_burn_end)
            end = max(ends)
            tail_name = (
                f"burns until {format_number(end)} s"
                if (self.burning or self._summoner_burns or self.rune_combat.has_active_burn())
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
