"""Offensive keystones evaluated during rotations (lol-knowledge/mechanics/runes.md).

Covers the 11 combat keystones of phase 40: Electrocute, Dark Harvest, Press the
Attack, Conqueror, Lethal Tempo, Hail of Blades, Summon Aery, Arcane Comet,
Deathfire Touch, First Strike and Grasp of the Undying.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction

from .damage import DamageType, format_number
from .errors import RotationError, StatsError
from .runes import (
    ADAPTIVE_AD_PER_AP,
    COMBAT_KEYSTONE_KEYS,
    LEVELS,
    RULES,
    Rune,
    RuneData,
    adaptive_stat,
    int_input,
    linear_by_level,
    rune_value,
)
from .scenario import Target
from .stats import Label, StatBlocked, StatSheet, weakest


@dataclass(frozen=True)
class RuneModifier:
    """One damage-dealt percentage modifier from a rune."""

    source: str
    percent: Fraction
    label: Label
    note: str = ""


@dataclass(frozen=True)
class RuneProc:
    """One bonus damage instance dealt by a rune."""

    source: str
    damage_type: DamageType
    raw: Fraction
    label: Label
    notes: tuple[str, ...] = ()
    # False for post-mitigation bonus procs (First Strike) to avoid double-applying modifiers.
    apply_modifiers: bool = True


@dataclass(frozen=True)
class DelayedRuneProc:
    """A rune proc scheduled to land at ``at`` seconds in the timeline."""

    at: Fraction
    proc: RuneProc


@dataclass(frozen=True)
class RuneStatBonus:
    """A temporary stat bonus granted by a keystone (Conqueror, Lethal Tempo, Hail of Blades)."""

    stat_id: str
    amount: Fraction
    source: str
    label: Label
    note: str = ""


def require_target_kind(rune: Rune, target: Target) -> str:
    if target.kind is None:
        raise RotationError(
            f"rune {rune.id} {rune.name} depends on the target kind; give --target-kind"
        )
    return target.kind


def rune_source(rune: Rune, data: RuneData) -> str:
    return f"rune:{rune.id} {rune.key} ({data.content_version})"


def _sheet_adaptive(
    sheet: StatSheet, ap_weight: Fraction | None
) -> tuple[str, DamageType, Label, str]:
    try:
        bonus_ad = sheet["attack_damage"].scoped("bonus")
        ap = sheet["ability_power"].total()
    except StatBlocked as exc:
        raise RotationError(f"adaptive rune needs attack damage and ability power: {exc}") from exc
    stat_name, label, note = adaptive_stat(bonus_ad, ap, ap_weight)
    damage_type = DamageType.MAGIC if stat_name == "ability_power" else DamageType.PHYSICAL
    return stat_name, damage_type, label, note


def _bonus_ad_and_ap(sheet: StatSheet) -> tuple[Fraction, Fraction, list[Label]]:
    try:
        ad_val, ap_val = sheet["attack_damage"], sheet["ability_power"]
        return ad_val.scoped("bonus"), ap_val.total(), [ad_val.label, ap_val.label]
    except StatBlocked as exc:
        raise RotationError(
            f"keystone scaling needs attack damage and ability power: {exc}"
        ) from exc


def _range_required(rune: Rune, holder_range: str | None) -> str:
    if holder_range is None:
        raise RotationError(f"rune {rune.id} {rune.name}: needs --attacker-range melee|ranged")
    return holder_range


def _nonneg_fraction(inputs: Mapping[str, Fraction], name: str) -> Fraction | None:
    if name not in inputs:
        return None
    value = inputs[name]
    if value < 0:
        raise RotationError(f"input {name}: must not be negative, got {format_number(value)}")
    return value


class KeystoneCombat:
    """Offensive keystone state for one rotation."""

    def __init__(
        self,
        rune_ids: Sequence[int],
        data: RuneData | None,
        sheet: StatSheet,
        target: Target,
        *,
        holder_range: str | None,
        inputs: Mapping[str, Fraction],
        timeline: bool,
        ap_weight: Fraction | None = None,
    ) -> None:
        self.data = data
        self.sheet = sheet
        self.target = target
        self.holder_range = holder_range
        self.timeline = timeline
        self.ap_weight = ap_weight
        self.notes: list[str] = []
        self.weakened = False
        self.speed_changed = False

        self._keystone: Rune | None = None
        self._base = Label.DERIVED

        # Per-keystone state
        self._elec_hits: list[tuple[Fraction, str]] = []
        self._elec_ready = Fraction(0)
        self._elec_fired = False

        self._dh_souls: int | None = None
        self._dh_ready = Fraction(0)
        self._dh_fired = False

        self._pta_hits = 0
        self._pta_exposed = False
        self._pta_last_hit: Fraction | None = None

        self._conq_stacks = 0
        self._conq_last: Fraction | None = None

        self._lt_stacks = 0
        self._lt_last: Fraction | None = None

        self._hob_remaining = 0
        self._hob_last: Fraction | None = None
        self._hob_ready = Fraction(0)
        self._hob_used_once = False

        self._aery_fired = False
        self._aery_warned = False

        self._comet_dist: Fraction | None = None
        self._comet_ready = Fraction(0)
        self._comet_fired = False

        self._dft_duration: Fraction | None = None
        self._dft_started: Fraction | None = None
        self._dft_end: Fraction | None = None
        self._dft_dps = Fraction(0)
        self._dft_labels: tuple[Label, ...] = ()
        self._dft_fired = False

        self._fs_enabled = False
        self._fs_window_end: Fraction | None = None
        self._fs_ready = Fraction(0)
        self._fs_steps = 0

        self._grasp_ready = False
        self._grasp_next_at = Fraction(0)
        self._grasp_fired = False

        if not rune_ids or data is None:
            return
        self._base = Label.DERIVED if data.matches_patch(sheet.champion.patch) else Label.PENDING
        for rune_id in rune_ids:
            rune = data.runes.get(rune_id)
            if rune is None or rune.key not in COMBAT_KEYSTONE_KEYS:
                continue
            try:
                self._configure(rune, inputs)
            except StatsError as exc:
                raise RotationError(str(exc)) from exc
            break  # a legal page has at most one keystone

    def _configure(self, rune: Rune, inputs: Mapping[str, Fraction]) -> None:
        if self.target.kind not in (None, "champion"):
            return  # all 11 offensive keystones trigger only against champions

        if rune.key in ("Electrocute", "PressTheAttack", "SummonAery"):
            require_target_kind(rune, self.target)
            self._keystone = rune
            return

        if rune.key in ("Conqueror", "LethalTempo", "HailOfBlades"):
            require_target_kind(rune, self.target)
            _range_required(rune, self.holder_range)
            self._keystone = rune
            return

        if rune.key == "DarkHarvest":
            souls = int_input(inputs, "dark_harvest_souls", minimum=0)
            if souls is None:
                self.notes.append(
                    f"rune {rune.id} {rune.name}: needs --input dark_harvest_souls=<count> (no cap)"
                )
                self.weakened = True
                return
            require_target_kind(rune, self.target)
            self._dh_souls = souls
            self._keystone = rune
            return

        if rune.key == "ArcaneComet":
            dist = _nonneg_fraction(inputs, "comet_distance")
            if dist is None:
                self.notes.append(
                    f"rune {rune.id} {rune.name}: needs --input comet_distance=<0..750> "
                    f"(distance amplifies damage up to +100%; {RULES})"
                )
                self.weakened = True
                return
            require_target_kind(rune, self.target)
            self._comet_dist = dist
            self._keystone = rune
            return

        if rune.key == "DeathfireTouch":
            dur = int_input(inputs, "deathfire_duration", minimum=1, maximum=4)
            if dur is None:
                self.notes.append(
                    f"rune {rune.id} {rune.name}: needs --input deathfire_duration=1|2|4 "
                    "(DoT 1 s, AoE 2 s, single-target 4 s)"
                )
                self.weakened = True
                return
            if dur not in (1, 2, 4):
                raise RotationError(
                    f"input deathfire_duration: must be 1 (DoT), 2 (AoE) or 4 (single-target), "
                    f"got {dur}"
                )
            require_target_kind(rune, self.target)
            self._dft_duration = Fraction(dur)
            self._keystone = rune
            return

        if rune.key == "FirstStrike":
            enabled = int_input(inputs, "first_strike", minimum=0, maximum=1)
            if enabled is None:
                self.notes.append(
                    f"rune {rune.id} {rune.name}: needs --input first_strike=0|1 ({RULES})"
                )
                self.weakened = True
                return
            if enabled == 0:
                self.notes.append(f"rune {rune.id} {rune.name}: inactive (first_strike=0)")
                return
            require_target_kind(rune, self.target)
            self._fs_enabled = True
            self._keystone = rune
            self.notes.append(f"rune {rune.id} {rune.name}: bonus gold is not modelled")
            return

        if rune.key == "GraspOfTheUndying":
            ready = int_input(inputs, "grasp_ready", minimum=0, maximum=1)
            if ready is None:
                self.notes.append(
                    f"rune {rune.id} {rune.name}: needs --input grasp_ready=0|1 "
                    "(whether 4 s in combat elapsed before the rotation)"
                )
                self.weakened = True
                return
            require_target_kind(rune, self.target)
            _range_required(rune, self.holder_range)
            self._grasp_ready = ready == 1
            if not self._grasp_ready:
                self._grasp_next_at = rune_value(rune, "TriggerTime")
            self._keystone = rune
            self.notes.append(
                f"rune {rune.id} {rune.name}: healing and permanent max health gain are not "
                "modelled (MEC-05)"
            )

    def _refresh_expirations(self, at: Fraction) -> None:
        if self._keystone is None or not self.timeline:
            return
        key = self._keystone.key
        if key == "Conqueror" and self._conq_last is not None:
            if at - self._conq_last >= rune_value(self._keystone, "BuffDuration"):
                self._conq_stacks = 0
                self._conq_last = None
        elif key == "LethalTempo" and self._lt_last is not None:
            if at - self._lt_last >= rune_value(self._keystone, "Duration"):
                self._lt_stacks = 0
                self._lt_last = None
        elif key == "HailOfBlades" and self._hob_remaining > 0 and self._hob_last is not None:
            if at - self._hob_last > rune_value(self._keystone, "Duration"):
                self._hob_remaining = 0
                self._hob_ready = self._hob_last + rune_value(self._keystone, "Cooldown")
        elif (
            key == "PressTheAttack"
            and self._pta_exposed
            and self._pta_last_hit is not None
            and at - self._pta_last_hit >= rune_value(self._keystone, "Cooldown")
        ):
            self._pta_exposed = False
            self._pta_hits = 0

    def active_stat_bonuses(self, at: Fraction, base_sheet: StatSheet) -> list[RuneStatBonus]:
        """Temporary stat bonuses active at ``at`` (Conqueror, Lethal Tempo, Hail of Blades)."""
        if self._keystone is None or self.data is None:
            return []
        self._refresh_expirations(at)
        rune = self._keystone
        src = f"{rune_source(rune, self.data)} ({rune.name})"

        if rune.key == "Conqueror" and self._conq_stacks > 0:
            stat_name, _, ad_label, ad_note = _sheet_adaptive(base_sheet, self.ap_weight)
            per_stack = linear_by_level(
                rune_value(rune, "MinAdaptivePerStack"),
                rune_value(rune, "MaxAdaptivePerStack"),
                base_sheet.level,
            )
            ap_amount = per_stack * self._conq_stacks
            amount = ap_amount if stat_name == "ability_power" else ap_amount * ADAPTIVE_AD_PER_AP
            curve_label = self._base if base_sheet.level in (1, LEVELS) else Label.PENDING
            note = f"{self._conq_stacks} stacks"
            if base_sheet.level not in (1, LEVELS):
                note += "; per-level curve taken as linear (not in bin)"
            if ad_note:
                note += f"; {ad_note}"
            return [RuneStatBonus(stat_name, amount, src, weakest((curve_label, ad_label)), note)]

        if rune.key == "LethalTempo" and self._lt_stacks > 0:
            if self.holder_range == "melee":
                per_stack = rune_value(rune, "TTASPerStackMelee")
                label = self._base
                note = f"{self._lt_stacks} stacks (melee)"
            else:
                per_stack = rune_value(rune, "TTASPerStackRanged")
                label = Label.PENDING
                note = f"{self._lt_stacks} stacks (ranged: tooltip 4% vs calc 4.8% in client 16.23)"
            return [
                RuneStatBonus("attack_speed_bonus", per_stack * self._lt_stacks, src, label, note)
            ]

        if rune.key == "HailOfBlades" and self._hob_remaining > 0:
            key = "ASBoost" if self.holder_range == "melee" else "ASBoostRanged"
            boost = rune_value(rune, key)
            note = f"{self._hob_remaining} empowered attacks remaining"
            return [RuneStatBonus("attack_speed_bonus", boost, src, self._base, note)]

        return []

    def dealt_modifiers(self) -> list[RuneModifier]:
        """Damage-dealt modifiers active from the keystone (Press the Attack +8%)."""
        if (
            self._keystone is None
            or self._keystone.key != "PressTheAttack"
            or not self._pta_exposed
        ):
            return []
        rune = self._keystone
        return [
            RuneModifier(
                f"rune:{rune.id} {rune.key}",
                rune_value(rune, "BonusPercentDamage") * 100,
                self._base,
                "exposed after 3 consecutive basic attacks",
            )
        ]

    def healing_rate(self) -> tuple[Fraction, Label, str] | None:
        """Extra post-mitigation healing rate against champions (Conqueror at max stacks)."""
        if self._keystone is None or self._keystone.key != "Conqueror":
            return None
        rune = self._keystone
        if self._conq_stacks < int(rune_value(rune, "MaxStacks")):
            return None
        key = "HealingPercent" if self.holder_range == "melee" else "RangedHealingPercent"
        return (
            rune_value(rune, key),
            self._base,
            f"Conqueror max stacks healing ({self.holder_range})",
        )

    def on_step(
        self,
        slot: str | None,
        dealt_damage: bool,
        clock: Fraction,
        sheet: StatSheet,
    ) -> list[RuneProc]:
        """Procs and state transitions fired by one attack or ability step."""
        if self._keystone is None or self.data is None or not dealt_damage:
            return []
        self._refresh_expirations(clock)
        rune = self._keystone
        src = f"{rune_source(rune, self.data)} ({rune.name})"
        procs: list[RuneProc] = []

        if rune.key == "Electrocute":
            if not self.timeline:
                if not self._elec_fired:
                    self._elec_hits.append((clock, slot or "attack"))
                    if len(self._elec_hits) >= 3:
                        self._elec_fired = True
                        procs.append(self._electrocute_proc(rune, src, sheet, timeline=False))
            elif clock >= self._elec_ready:
                window = rune_value(rune, "WindowDuration")
                self._elec_hits = [item for item in self._elec_hits if clock - item[0] <= window]
                self._elec_hits.append((clock, slot or "attack"))
                if len(self._elec_hits) >= 3:
                    self._elec_hits = []
                    self._elec_ready = clock + rune_value(rune, "Cooldown")
                    procs.append(self._electrocute_proc(rune, src, sheet, timeline=True))
            return procs

        if rune.key == "PressTheAttack":
            self._pta_last_hit = clock
            if slot is None and not self._pta_exposed:
                self._pta_hits += 1
                if self._pta_hits >= int(rune_value(rune, "HitsRequired")):
                    self._pta_hits = 0
                    self._pta_exposed = True
                    _, dtype, ad_label, ad_note = _sheet_adaptive(sheet, self.ap_weight)
                    raw = linear_by_level(
                        rune_value(rune, "MinDamage"), rune_value(rune, "MaxDamage"), sheet.level
                    )
                    curve_label = self._base if sheet.level in (1, LEVELS) else Label.PENDING
                    notes = []
                    if sheet.level not in (1, LEVELS):
                        notes.append("per-level curve taken as linear (not in bin)")
                    if ad_note:
                        notes.append(ad_note)
                    procs.append(
                        RuneProc(src, dtype, raw, weakest((curve_label, ad_label)), tuple(notes))
                    )
            return procs

        if rune.key == "Conqueror":
            gain = 1 if (slot is None and self.holder_range == "ranged") else 2
            max_stacks = int(rune_value(rune, "MaxStacks"))
            self._conq_stacks = min(max_stacks, self._conq_stacks + gain)
            self._conq_last = clock
            return procs

        if rune.key == "LethalTempo" and slot is None:
            max_stacks = int(rune_value(rune, "MaxStacks"))
            was_full = self._lt_stacks >= max_stacks
            if was_full:
                procs.append(self._lethal_tempo_proc(rune, src, sheet))
            self._lt_stacks = min(max_stacks, self._lt_stacks + 1)
            self._lt_last = clock
            if self.timeline:
                self.speed_changed = True
            return procs

        if rune.key == "HailOfBlades" and slot is None:
            can_start = (
                (not self._hob_used_once)
                if not self.timeline
                else (self._hob_remaining == 0 and clock >= self._hob_ready)
            )
            if can_start:
                self._hob_remaining = int(rune_value(rune, "NumHits"))
                self._hob_used_once = True
            if self._hob_remaining > 0:
                procs.append(self._hob_proc(rune, src, sheet))
                self._hob_remaining -= 1
                self._hob_last = clock
                if self.timeline:
                    self.speed_changed = True
                    if self._hob_remaining == 0:
                        self._hob_ready = clock + rune_value(rune, "Cooldown")
            return procs

        if rune.key == "SummonAery":
            if not self._aery_fired:
                self._aery_fired = True
                _, dtype, ad_label, ad_note = _sheet_adaptive(sheet, self.ap_weight)
                bonus_ad, ap, stat_labels = _bonus_ad_and_ap(sheet)
                raw = (
                    linear_by_level(
                        rune_value(rune, "DamageBase"),
                        rune_value(rune, "DamageMax"),
                        sheet.level,
                    )
                    + bonus_ad * rune_value(rune, "DamageADRatio")
                    + ap * rune_value(rune, "DamageAPRatio")
                )
                notes = (ad_note,) if ad_note else ()
                procs.append(
                    RuneProc(src, dtype, raw, weakest([self._base, ad_label, *stat_labels]), notes)
                )
            elif not self._aery_warned:
                self._aery_warned = True
                self.weakened = True
                self.notes.append(
                    f"rune {rune.id} {rune.name}: return travel time depends on distance "
                    "(fires once; subsequent procs not modelled)"
                )
            return procs

        if rune.key == "ArcaneComet" and slot is not None:
            if not self.timeline:
                if not self._comet_fired:
                    self._comet_fired = True
                    procs.append(self._comet_proc(rune, src, sheet, timeline=False))
            elif clock >= self._comet_ready:
                cd = linear_by_level(
                    rune_value(rune, "RechargeTime"),
                    rune_value(rune, "RechargeTimeMin"),
                    sheet.level,
                )
                self._comet_ready = clock + cd
                procs.append(self._comet_proc(rune, src, sheet, timeline=True))
            else:
                remaining = self._comet_ready - clock
                refund = remaining * rune_value(rune, "PercentRefund")
                self._comet_ready = max(clock, self._comet_ready - refund)
            return procs

        if rune.key == "DeathfireTouch" and slot is not None:
            assert self._dft_duration is not None
            bonus_ad, ap, stat_labels = _bonus_ad_and_ap(sheet)
            dps = (
                linear_by_level(
                    rune_value(rune, "Level1DamageTOOLTIP"),
                    rune_value(rune, "Level18DamageTOOLTIP"),
                    sheet.level,
                )
                + ap * rune_value(rune, "APRatio")
                + bonus_ad * rune_value(rune, "ADRatio")
            )
            labels = (self._base, *stat_labels)
            if not self.timeline:
                if not self._dft_fired:
                    self._dft_fired = True
                    amp_after = rune_value(rune, "TimeToAmp")
                    mult = rune_value(rune, "DamageMultiplier")
                    if self._dft_duration <= amp_after:
                        total = dps * self._dft_duration
                    else:
                        total = dps * amp_after + dps * (1 + mult) * (
                            self._dft_duration - amp_after
                        )
                    dur_text = format_number(self._dft_duration)
                    procs.append(
                        RuneProc(
                            f"{src} over {dur_text} s",
                            DamageType.MAGIC,
                            total,
                            weakest(labels),
                            (
                                f"scenario: deathfire_duration={dur_text}; "
                                "fires once without --timeline",
                            ),
                        )
                    )
            else:
                if self._dft_end is None or clock >= self._dft_end:
                    self._dft_started = clock
                self._dft_end = clock + self._dft_duration
                self._dft_dps = dps
                self._dft_labels = labels
            return procs

        if rune.key == "GraspOfTheUndying" and slot is None:
            can_fire = (
                (self._grasp_ready and not self._grasp_fired)
                if not self.timeline
                else (self._grasp_ready or clock >= self._grasp_next_at)
            )
            if can_fire:
                self._grasp_fired = True
                self._grasp_ready = False
                self._grasp_next_at = clock + rune_value(rune, "TriggerTime")
                health = sheet["health"]
                try:
                    max_hp = health.total()
                except StatBlocked as exc:
                    raise RotationError(f"rune {rune.id} {rune.name}: {exc}") from exc
                pct = rune_value(rune, "PercentHealthDamage")
                if self.holder_range == "ranged":
                    pct *= rune_value(rune, "RangedPenaltyMod")
                procs.append(
                    RuneProc(
                        src,
                        DamageType.MAGIC,
                        max_hp * pct,
                        weakest((self._base, health.label)),
                        (f"grasp ({self.holder_range})",),
                    )
                )
            return procs

        return procs

    def on_step_complete(
        self,
        step_damage: Fraction,
        clock: Fraction,
        sheet: StatSheet,
        health_before: Fraction,
        health_after: Fraction,
        max_health: Fraction,
    ) -> list[RuneProc]:
        """Post-step procs (Dark Harvest < 50% HP, First Strike +7% bonus true damage)."""
        if self._keystone is None or self.data is None or step_damage <= 0:
            return []
        rune = self._keystone
        src = f"{rune_source(rune, self.data)} ({rune.name})"
        procs: list[RuneProc] = []

        if rune.key == "DarkHarvest" and self._dh_souls is not None:
            threshold = rune_value(rune, "HarvestThreshold") * max_health
            below = health_before < threshold or health_after < threshold
            can_fire = (not self._dh_fired) if not self.timeline else (clock >= self._dh_ready)
            if below and can_fire:
                self._dh_fired = True
                if self.timeline:
                    self._dh_ready = clock + rune_value(rune, "Cooldown")
                _, dtype, ad_label, ad_note = _sheet_adaptive(sheet, self.ap_weight)
                bonus_ad, ap, stat_labels = _bonus_ad_and_ap(sheet)
                raw = (
                    rune_value(rune, "BaseDamage")
                    + self._dh_souls * rune_value(rune, "DamagePerSoulEssence")
                    + bonus_ad * rune_value(rune, "ADRatio")
                    + ap * rune_value(rune, "APRatio")
                )
                notes = [f"scenario: dark_harvest_souls={self._dh_souls}"]
                if ad_note:
                    notes.append(ad_note)
                self._dh_souls += 1
                procs.append(
                    RuneProc(
                        src,
                        dtype,
                        raw,
                        weakest([self._base, ad_label, *stat_labels]),
                        tuple(notes),
                    )
                )
            return procs

        if rune.key == "FirstStrike" and self._fs_enabled:
            amp = rune_value(rune, "DamageAmp")
            if not self.timeline:
                self._fs_steps += 1
                label = self._base if self._fs_steps == 1 else Label.PENDING
                notes = ["scenario: first_strike=1"]
                if self._fs_steps > 1:
                    notes.append("3 s window not enforced without --timeline")
                procs.append(
                    RuneProc(
                        src,
                        DamageType.TRUE,
                        step_damage * amp,
                        label,
                        tuple(notes),
                        apply_modifiers=False,
                    )
                )
            else:
                if (
                    self._fs_window_end is None or clock > self._fs_window_end
                ) and clock >= self._fs_ready:
                    self._fs_window_end = clock + rune_value(rune, "Duration")
                    cd = linear_by_level(
                        rune_value(rune, "TooltipOnlyCooldownStartAmount"),
                        rune_value(rune, "TooltipOnlyCooldownEndAmount"),
                        sheet.level,
                    )
                    self._fs_ready = clock + cd
                if self._fs_window_end is not None and clock <= self._fs_window_end:
                    procs.append(
                        RuneProc(
                            src,
                            DamageType.TRUE,
                            step_damage * amp,
                            self._base,
                            ("scenario: first_strike=1",),
                            apply_modifiers=False,
                        )
                    )
            return procs

        return procs

    def _electrocute_proc(
        self, rune: Rune, src: str, sheet: StatSheet, *, timeline: bool
    ) -> RuneProc:
        _, dtype, ad_label, ad_note = _sheet_adaptive(sheet, self.ap_weight)
        bonus_ad, ap, stat_labels = _bonus_ad_and_ap(sheet)
        raw = (
            linear_by_level(
                rune_value(rune, "DamageBase"), rune_value(rune, "DamageMax"), sheet.level
            )
            + bonus_ad * rune_value(rune, "BonusADRatio")
            + ap * rune_value(rune, "APRatio")
        )
        notes = []
        if not timeline:
            notes.append("3 s window and 20 s cooldown apply with --timeline")
        if ad_note:
            notes.append(ad_note)
        return RuneProc(
            src, dtype, raw, weakest([self._base, ad_label, *stat_labels]), tuple(notes)
        )

    def _lethal_tempo_proc(self, rune: Rune, src: str, sheet: StatSheet) -> RuneProc:
        _, dtype, ad_label, ad_note = _sheet_adaptive(sheet, self.ap_weight)
        as_bonus_val = sheet["attack_speed_bonus"]
        try:
            as_bonus = as_bonus_val.total()
        except StatBlocked as exc:
            raise RotationError(f"rune {rune.id} {rune.name}: {exc}") from exc
        if self.holder_range == "melee":
            base_dmg = linear_by_level(
                rune_value(rune, "TTMinNoteDamageMelee"),
                rune_value(rune, "TTMaxNoteDamageMelee"),
                sheet.level,
            )
            label = weakest((self._base, ad_label, as_bonus_val.label))
            notes = []
        else:
            base_dmg = linear_by_level(
                rune_value(rune, "TTMinNoteDamageRanged"),
                rune_value(rune, "TTMaxNoteDamageRanged"),
                sheet.level,
            )
            label = Label.PENDING
            notes = ["ranged max damage: tooltip 24 vs calc 20 in client 16.23"]
        if ad_note:
            notes.append(ad_note)
        return RuneProc(src, dtype, base_dmg * (1 + as_bonus), label, tuple(notes))

    def _hob_proc(self, rune: Rune, src: str, sheet: StatSheet) -> RuneProc:
        bonus_ad, ap, stat_labels = _bonus_ad_and_ap(sheet)
        raw = (
            linear_by_level(
                rune_value(rune, "BonusDamageMin"), rune_value(rune, "BonusDamageMax"), sheet.level
            )
            + bonus_ad * rune_value(rune, "BonusADRatio")
            + ap * rune_value(rune, "APRatio")
        )
        curve_label = self._base if sheet.level in (1, LEVELS) else Label.PENDING
        notes = []
        if sheet.level not in (1, LEVELS):
            notes.append("per-level curve {ee18a47b} taken as linear (not decoded)")
        return RuneProc(
            src, DamageType.TRUE, raw, weakest([curve_label, *stat_labels]), tuple(notes)
        )

    def _comet_proc(self, rune: Rune, src: str, sheet: StatSheet, *, timeline: bool) -> RuneProc:
        assert self._comet_dist is not None
        _, dtype, ad_label, ad_note = _sheet_adaptive(sheet, self.ap_weight)
        bonus_ad, ap, stat_labels = _bonus_ad_and_ap(sheet)
        max_range = rune_value(rune, "MaxRange")
        clamped = min(self._comet_dist, max_range)
        amp = 1 + rune_value(rune, "MaxDamageAmp") * clamped / max_range
        raw = (
            linear_by_level(
                rune_value(rune, "DamageBase"), rune_value(rune, "DamageMax"), sheet.level
            )
            + bonus_ad * rune_value(rune, "ADRatio")
            + ap * rune_value(rune, "APRatio")
        ) * amp
        dist_label = self._base if clamped in (0, max_range) else Label.PENDING
        notes = [f"scenario: comet_distance={format_number(self._comet_dist)}"]
        if clamped not in (0, max_range):
            notes.append("distance amplification taken as linear")
        if not timeline:
            notes.append("cooldown and 20% refund apply with --timeline")
        if ad_note:
            notes.append(ad_note)
        return RuneProc(
            src, dtype, raw, weakest([dist_label, ad_label, *stat_labels]), tuple(notes)
        )

    def has_active_burn(self) -> bool:
        return self._dft_end is not None

    def burn_end(self) -> Fraction | None:
        return self._dft_end

    def burn_split_times(self, start: Fraction, until: Fraction) -> list[Fraction]:
        if self._dft_end is None or self._dft_started is None or self._keystone is None:
            return []
        amp_at = self._dft_started + rune_value(self._keystone, "TimeToAmp")
        return [t for t in (self._dft_end, amp_at) if start < t < until]

    def accrue_burn(self, begin: Fraction, finish: Fraction) -> RuneProc | None:
        if (
            self._dft_end is None
            or self._dft_started is None
            or self._keystone is None
            or self.data is None
            or self._dft_end <= begin
        ):
            return None
        rune = self._keystone
        amp_at = self._dft_started + rune_value(rune, "TimeToAmp")
        mult = 1 + rune_value(rune, "DamageMultiplier") if begin >= amp_at else Fraction(1)
        src = (
            f"{rune_source(rune, self.data)} ({rune.name}) from {format_number(begin)} s "
            f"to {format_number(finish)} s"
        )
        notes = ("amplified +75% (burning >= 3 s)",) if mult > 1 else ()
        return RuneProc(
            src,
            DamageType.MAGIC,
            self._dft_dps * mult * (finish - begin),
            weakest(self._dft_labels),
            notes,
        )

    def clear_expired_burns(self, until: Fraction) -> None:
        if self._dft_end is not None and self._dft_end <= until:
            self._dft_started = None
            self._dft_end = None
