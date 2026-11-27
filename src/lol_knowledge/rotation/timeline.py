"""Timeline clock, cooldowns, continuous burns, and deferred accrual."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from fractions import Fraction
from typing import Any

from ..damage import DamageType, format_number
from ..errors import RotationError
from ..runes import scale_item_cooldown
from ..stats import (
    Label,
    StatBlocked,
    ability_cooldowns,
    effect_amount,
    weakest,
    with_amplifier,
    with_bonus,
    with_percent_bonus,
)
from .effects import _Burn, _conditions_hold, _duration, _key, _Window
from .models import (
    ATTACK_SPEED_STATS,
    RESISTANCE_STATS,
    UNCERTAIN_START_TRIGGERS,
    Part,
    Step,
    StepOutcome,
    Timeline,
)


class _TimelineMixin:
    """Timeline state transitions, burns, cooldowns, and stat-window accrual."""

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
        self.now = at
        self.active_dealt, self.shred = [], {}
        ops: list[tuple[Any, ...]] = []
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
            ops.append(
                (
                    "b",
                    stat_id,
                    effect_amount(stat_id, per_stack * count),
                    f"{effect.title} ({effect.name})",
                    weakest(labels),
                    note,
                )
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
                    ops.append(
                        ("b", stat_id, effect_amount(stat_id, window.value), source, label, "")
                    )
                elif stat_id == "move_speed":
                    ops.append(("p", stat_id, window.value / 100, source, label, ""))
                else:
                    ops.append(("a", stat_id, window.value, source, label))
            else:
                damage_type = RESISTANCE_STATS[str(component.get("stat"))]
                self.shred.setdefault(damage_type, []).append(window)
        for bonus in self.rune_combat.active_stat_bonuses(at, self.base_sheet):
            kind = "p" if bonus.percent else "b"
            ops.append((kind, bonus.stat_id, bonus.amount, bonus.source, bonus.label, bonus.note))
        if self.passive_combat._stacking:
            p_flats, p_amps = self.passive_combat.active_stat_modifiers(
                at, self.base_sheet.level, stats=self.base_stats
            )
            for p_bonus in p_flats:
                kind = "p" if p_bonus.percent else "b"
                ops.append(
                    (
                        kind,
                        p_bonus.stat_id,
                        p_bonus.amount,
                        p_bonus.source,
                        p_bonus.label,
                        p_bonus.note,
                    )
                )
            for p_amp in p_amps:
                ops.append(("a", p_amp.stat_id, p_amp.percent, p_amp.source, p_amp.label))
        ic_as = self.item_combat.dynamic_bonus_as(at)
        if ic_as:
            ops.append(
                ("b", "attack_speed", ic_as, "item_combat dynamic attack speed", Label.DERIVED, "")
            )
        ic_ap = self.item_combat.dynamic_bonus_ap(at)
        if ic_ap:
            ops.append(("b", "ability_power", ic_ap, "6616 rapids (+40 AP)", Label.OFFICIAL, ""))
        ic_ah = self.item_combat.dynamic_bonus_ah(at)
        if ic_ah:
            ops.append(("b", "ability_haste", ic_ah, "6616 rapids (+15 AH)", Label.OFFICIAL, ""))
        ic_ms = self.item_combat.dynamic_bonus_flat_ms(at)
        if ic_ms:
            ops.append(("b", "move_speed", ic_ms, "2524 fanfare (+20 MS)", Label.DERIVED, ""))
        for end_t, ms_pct, ms_src, ms_lbl in self._summoner_ms_buffs:
            if end_t is None or at < end_t:
                ops.append(("p", "move_speed", ms_pct, ms_src, ms_lbl, ""))
        for end_t, stat_id, mode, amount, src, lbl in self._ability_stat_buffs.values():
            if end_t is not None and at >= end_t:
                continue
            if mode == "percent_ms":
                ops.append(("p", stat_id, amount, src, lbl, ""))
            elif mode == "percent":
                ops.append(("a", stat_id, amount, src, lbl))
            else:
                ops.append(("b", stat_id, effect_amount(stat_id, amount), src, lbl, ""))

        if not ops:
            self._last_moment_ops = None
            if self.sheet is not self.base_sheet:
                self.sheet = self.base_sheet
                self.stats, self.origin = self.base_stats, self.base_origin
            return
        ops_key = tuple(ops)
        if ops_key == self._last_moment_ops:
            return
        sheet = self.base_sheet
        for op in ops_key:
            kind = op[0]
            if kind == "b":
                sheet = with_bonus(sheet, op[1], op[2], op[3], op[4], op[5])
            elif kind == "p":
                sheet = with_percent_bonus(sheet, op[1], op[2], op[3], op[4], op[5])
            else:
                sheet = with_amplifier(sheet, op[1], op[2], op[3], op[4])
        self._last_moment_ops = ops_key
        self.sheet = sheet
        self.stats, self.origin = sheet.cached_sheet_stats()

    def _open(
        self,
        trigger: str,
        clock: Fraction,
        target_stats: Mapping[str, Fraction],
        slot: str | None = None,
        *,
        damage_types: frozenset[str] | None = None,
    ) -> bool:
        """(Re)start the timed effects of ``trigger``; True when one starts on a hit."""
        uncertain = False
        opened_cooldowns: dict[str, Fraction] = {}
        for effect in self.timed:
            if effect.trigger != trigger:
                continue
            if not _conditions_hold(effect, self.target, "trigger", False, target_stats, slot):
                continue
            allowed_types = effect.component.get("damage_types")
            if allowed_types is not None and (
                damage_types is None or not any(dt in allowed_types for dt in damage_types)
            ):
                continue
            if effect.cooldown is not None:
                if clock < self.timed_ready.get(effect.title, Fraction(0)):
                    continue
                opened_cooldowns[effect.title] = clock + effect.cooldown
            assert effect.duration is not None
            value, labels = self._value(effect, target_stats)
            self.windows[_key(effect)] = _Window(
                effect, clock + effect.duration, value, (effect.label, *labels)
            )
            if effect.component.get("kind") == "stat_modifier" and effect.affects == "self":
                self.speed_changed |= str(effect.component.get("stat")) in ATTACK_SPEED_STATS
            if trigger in UNCERTAIN_START_TRIGGERS:
                ms_only = (
                    effect.component.get("kind") == "stat_modifier"
                    and str(effect.component.get("stat")) == "move_speed"
                )
                if not ms_only or self.ms_affects_damage:
                    uncertain = True
                    self.notes.append(
                        f"{effect.title}: starts after the hit that triggers it; whether that hit "
                        "benefits is not verified"
                    )
        self.timed_ready.update(opened_cooldowns)
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

    def _apply_shred_stacks(
        self,
        step_parts: Sequence[Part],
        clock: Fraction,
        target_stats: Mapping[str, Fraction],
        slot: str | None,
    ) -> None:
        """Stack percent resistance shred (Black Cleaver, Bloodletter's Curse)."""
        if not self.shred_percent_effects or not step_parts:
            return
        for effect in self.shred_percent_effects:
            if not _conditions_hold(effect, self.target, "item", False, target_stats, slot):
                continue
            allowed = effect.component.get("damage_types")
            matched = False
            for part in step_parts:
                if not part.hits_primary or part.primary_damage <= 0:
                    continue
                if effect.trigger == "damaging_ability" and part.kind != "ability":
                    continue
                if allowed is not None and part.damage_type.value not in allowed:
                    continue
                matched = True
                break
            if not matched:
                continue
            last = self.shred_stacked_at.get(effect.title)
            if (
                self.timeline is not None
                and effect.window is not None
                and last is not None
                and clock - last >= effect.window
            ):
                self.shred_stacks[effect.title] = 0
            assert effect.max_stacks is not None
            self.shred_stacks[effect.title] = min(
                effect.max_stacks, self.shred_stacks.get(effect.title, 0) + 1
            )
            self.shred_stacked_at[effect.title] = clock

    def _check_threshold_procs(
        self,
        step_damage: Fraction,
        clock: Fraction,
        target_stats: Mapping[str, Fraction],
    ) -> list[Part]:
        """Damage-threshold procs (Stormsurge: 25% max HP in 2.5 s -> delayed strike)."""
        if not self.threshold_procs or step_damage <= 0:
            return []
        immediate: list[Part] = []
        max_hp = target_stats["max_health"]
        for effect in self.threshold_procs:
            if not _conditions_hold(effect, self.target, "item", False, target_stats):
                continue
            if effect.cooldown is not None:
                if self.timeline is not None:
                    if clock < self.proc_ready.get(effect.title, Fraction(0)):
                        continue
                elif effect.title in self.proc_fired:
                    continue
            threshold_pct = Fraction(str(effect.component["damage_threshold_percent"])) / 100
            win_val = effect.component.get("threshold_window_seconds")
            win = Fraction(str(win_val)) if win_val is not None else None
            log = self.threshold_damage_log.setdefault(effect.title, [])
            if self.timeline is not None and win is not None:
                log[:] = [(t, d) for t, d in log if clock - t <= win]
            log.append((clock, step_damage))
            if sum((d for _, d in log), start=Fraction(0)) < threshold_pct * max_hp:
                continue
            log.clear()
            if effect.cooldown is not None:
                if self.timeline is not None:
                    self.proc_ready[effect.title] = clock + effect.cooldown
                else:
                    self.proc_fired.add(effect.title)
                    self.notes.append(
                        f"attacker {effect.title}: cooldown ({format_number(effect.cooldown)} s) "
                        "fires once without --timeline"
                    )
            raw, stat_labels = self._value(effect, target_stats)
            delay_val = effect.component.get("delay_seconds")
            delay = Fraction(str(delay_val)) if delay_val is not None else Fraction(0)
            if self.timeline is not None and delay > 0:
                self.delayed_item_procs.append(
                    (clock + delay, effect, raw, (effect.label, *stat_labels))
                )
            else:
                notes_p: tuple[str, ...] = (
                    (
                        f"triggered after >= {format_number(threshold_pct * 100)}% target max HP; "
                        f"{format_number(delay)} s delay fires immediately without --timeline",
                    )
                    if delay > 0
                    else ()
                )
                immediate.append(
                    self._part(
                        "item",
                        f"{effect.title} ({effect.name})",
                        DamageType(str(effect.component.get("damage_type"))),
                        raw,
                        [effect.label, *stat_labels],
                        False,
                        target_stats,
                        notes_p,
                    )
                )
        return immediate

    def _apply_cooldown_refunds(
        self, clock: Fraction, ready: dict[str, Fraction], target_stats: Mapping[str, Fraction]
    ) -> None:
        """Basic-attack remaining cooldown refunds (Navori Flickerblade: -15% basic CD)."""
        if self.timeline is None or not self.cooldown_refunds:
            return
        for effect in self.cooldown_refunds:
            if not _conditions_hold(effect, self.target, "trigger", False, target_stats):
                continue
            pct, _ = self._value(effect, target_stats)
            factor = 1 - pct / 100
            scope = effect.component.get("scope", "basic")
            slots = (
                ("Q", "W", "E")
                if scope == "basic"
                else (("R",) if scope == "ultimate" else ("Q", "W", "E", "R"))
            )
            for slot in slots:
                until = ready.get(slot)
                if until is not None and until > clock:
                    ready[slot] = clock + (until - clock) * factor

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
            and not self._summoner_burns
            and not self.rune_combat.has_active_burn()
            and not self.rune_combat.has_due_procs(until)
            and not any(t <= until for t, _, _, _ in self.delayed_item_procs)
            and not self.item_combat.has_periodic_due(until)
        ):
            self.accrued = max(start, until)
            return [], health, shield, Fraction(0)
        ends = {
            end
            for end in [
                *(burn.end for burn in self.burning.values()),
                *(b_end for b_end, _, _, _, _ in self._summoner_burns),
                *(
                    b_end
                    for b_end, _, _, _, _, _ in self._ability_stat_buffs.values()
                    if b_end is not None
                ),
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
                *(t for t, _, _, _ in self.delayed_item_procs if t <= until),
                *self.passive_combat.stack_expiry_times(start, until),
                *self.item_combat.periodic_split_times(start, until),
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
            for b_end, b_rate, b_src, b_lbl, b_notes in self._summoner_burns:
                if b_end <= begin:
                    continue
                part = self._part(
                    "summoner",
                    f"{b_src} from {format_number(begin)} s to {format_number(finish)} s",
                    DamageType.TRUE,
                    b_rate * (finish - begin),
                    [b_lbl],
                    False,
                    target_stats,
                    b_notes,
                    apply_modifiers=False,
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
            due_items = [entry for entry in self.delayed_item_procs if entry[0] <= finish]
            if due_items:
                self.delayed_item_procs = [
                    entry for entry in self.delayed_item_procs if entry[0] > finish
                ]
                self._set_moment(finish)
                for due_at, effect, raw_val, eff_labels in due_items:
                    part = self._part(
                        "item",
                        f"{effect.title} ({effect.name}) at {format_number(due_at)} s",
                        DamageType(str(effect.component.get("damage_type"))),
                        raw_val,
                        list(eff_labels),
                        False,
                        self._target_stats(health),
                    )
                    parts.append(part)
                    health, shield, absorbed = self._absorb_parts([part], health, shield)
                    total_absorbed += absorbed
            ic_procs, ic_heals = self.item_combat.pop_periodic(finish)
            if ic_procs or ic_heals:
                self._set_moment(finish)
                for proc in ic_procs:
                    p_part, p_heals = self._emit_item_proc(proc, self._target_stats(health), finish)
                    parts.append(p_part)
                    health, shield, absorbed = self._absorb_parts([p_part], health, shield)
                    total_absorbed += absorbed
                    self._pending_accrued_heals.extend(p_heals)
                if ic_heals:
                    self._pending_accrued_heals.extend(self._convert_item_heals(ic_heals, finish))
        self.accrued = until
        self.burning = {key: burn for key, burn in self.burning.items() if burn.end > until}
        self._summoner_burns = [item for item in self._summoner_burns if item[0] > until]
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
                    return scale_item_cooldown(
                        Fraction(str(effect["cooldown_seconds"])), self.rune_combat.item_haste
                    )
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
        case = (
            ability.case(step.case)
            if step.case is not None
            else (ability.cases[0] if ability.cases else None)
        )
        if case is not None and case.recast:
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
        accrued_heals = list(self._pending_accrued_heals)
        self._pending_accrued_heals.clear()
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
            weakest([*(part.label for part in parts), *(h.label for h in accrued_heals)]),
            clock,
            shield_before=shield,
            shield_absorbed=absorbed,
            heal_events=tuple(accrued_heals),
            resource_before=res_before,
            resource_after=res_after,
            resource_events=tuple(regen_events),
        )
        self._record_attacker_healing(outcome.healing)
        return outcome
