"""Combat minor runes evaluated during rotations (lol-knowledge/mechanics/runes.md).

Pure functions and stateful rotation helper over already-loaded rune data.
Covers the eight combat minor runes of phase 39: Coup de Grace, Cut Down,
Last Stand, Axiom Arcanist (NullifyingOrb), Scorch, Cheap Shot, Sudden Impact
and Demolish.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from fractions import Fraction

from .damage import DamageType, format_number
from .errors import RotationError, StatsError
from .rune_keystones import (
    DelayedRuneProc,
    KeystoneCombat,
    RuneModifier,
    RuneProc,
    RuneStatBonus,
    require_target_kind,
    rune_source,
)
from .runes import (
    COMBAT_MINOR_RUNE_KEYS,
    RULES,
    Rune,
    RuneData,
    fraction_input,
    int_input,
    linear_by_level,
    rune_value,
)
from .scenario import Target
from .stats import Label, StatBlocked, StatSheet, weakest

_require_target_kind = require_target_kind
_rune_source = rune_source


class RuneCombat:
    """Combat minor rune state for one rotation."""

    def __init__(
        self,
        rune_ids: Sequence[int],
        data: RuneData | None,
        sheet: StatSheet,
        target: Target,
        *,
        has_ultimate_step: bool,
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
        self.notes: list[str] = []
        self.weakened = False
        self._keystones = KeystoneCombat(
            rune_ids,
            data,
            sheet,
            target,
            holder_range=holder_range,
            inputs=inputs,
            timeline=timeline,
            ap_weight=ap_weight,
        )
        self.notes.extend(self._keystones.notes)
        self.weakened |= self._keystones.weakened
        self._reported_keystone_notes = len(self._keystones.notes)

        self._coup: tuple[Rune, Fraction, Fraction] | None = None
        self._cut_down: tuple[Rune, Fraction, Fraction] | None = None
        self._last_stand: RuneModifier | None = None
        self._axiom: RuneModifier | None = None
        self._scorch: Rune | None = None
        self._cheap_shot: Rune | None = None
        self._sudden_impact: Rune | None = None
        self._demolish: Rune | None = None

        self._fired: set[int] = set()
        self._ready: dict[int, Fraction] = {}
        self._demolish_hits = 0
        self._delayed: list[DelayedRuneProc] = []

        if not rune_ids or data is None:
            return
        self._base = Label.DERIVED if data.matches_patch(sheet.champion.patch) else Label.PENDING
        seen: set[int] = set()
        for rune_id in rune_ids:
            if rune_id in seen:
                continue
            seen.add(rune_id)
            rune = data.runes.get(rune_id)
            if rune is None or rune.key not in COMBAT_MINOR_RUNE_KEYS:
                continue
            try:
                self._configure(rune, inputs, has_ultimate_step)
            except StatsError as exc:
                raise RotationError(str(exc)) from exc

    def _configure(
        self, rune: Rune, inputs: Mapping[str, Fraction], has_ultimate_step: bool
    ) -> None:
        assert self.data is not None
        if rune.key == "CoupDeGrace":
            if _require_target_kind(rune, self.target) != "champion":
                return
            self._coup = (
                rune,
                rune_value(rune, "BonusPercentDamage") * 100,
                rune_value(rune, "EnemyHealthPercentageThreshold"),
            )
            return

        if rune.key == "CutDown":
            if _require_target_kind(rune, self.target) != "champion":
                return
            self._cut_down = (
                rune,
                rune_value(rune, "BonusPercentDamage") * 100,
                rune_value(rune, "EnemyHealthPercentageThreshold"),
            )
            return

        if rune.key == "LastStand":
            if self.target.kind not in (None, "champion"):
                return
            hp_pct = fraction_input(inputs, "attacker_health_percent")
            if hp_pct is None:
                self.notes.append(
                    f"rune {rune.id} {rune.name}: needs --input attacker_health_percent=<0..1> "
                    f"({RULES})"
                )
                self.weakened = True
                return
            start = rune_value(rune, "HealthThresholdStart")
            end = rune_value(rune, "HealthThresholdEnd")
            if hp_pct > start:
                pct_text = format_number(start * 100)
                self.notes.append(
                    f"rune {rune.id} {rune.name}: inactive above {pct_text}% attacker health"
                )
                return
            _require_target_kind(rune, self.target)
            low = rune_value(rune, "MinBonusDamagePercent") * 100
            high = rune_value(rune, "MaxBonusDamagePercent") * 100
            label = self._base
            note = f"scenario: attacker_health_percent={format_number(hp_pct)}"
            if hp_pct <= end:
                percent = high
            elif hp_pct == start:
                percent = low
                label = Label.PENDING
                note += "; at exact 60% threshold (< vs <= not measured)"
            else:
                percent = low + (high - low) * (start - hp_pct) / (start - end)
            self._last_stand = RuneModifier(f"rune:{rune.id} {rune.key}", percent, label, note)
            return

        if rune.key == "NullifyingOrb":
            self.notes.append(
                f"rune {rune.id} {rune.name}: ultimate heal/shield amp and takedown cooldown "
                "refund are not modelled"
            )
            if not has_ultimate_step:
                self.notes.append(f"rune {rune.id} {rune.name}: no R step in rotation")
                return
            aoe = int_input(inputs, "ultimate_aoe", minimum=0, maximum=1)
            if aoe is None:
                self.notes.append(
                    f"rune {rune.id} {rune.name}: needs --input ultimate_aoe=0|1 "
                    "(12% single-target, 8% AoE)"
                )
                self.weakened = True
                return
            key = "AOEAmp" if aoe == 1 else "DamageAmp"
            mode = "AoE" if aoe == 1 else "single-target"
            self._axiom = RuneModifier(
                f"rune:{rune.id} {rune.key}",
                rune_value(rune, key) * 100,
                self._base,
                f"scenario: ultimate_aoe={aoe} ({mode})",
            )
            return

        if rune.key == "Scorch":
            if _require_target_kind(rune, self.target) != "champion":
                return
            self._scorch = rune
            return

        if rune.key == "CheapShot":
            if self.target.kind not in (None, "champion"):
                return
            impaired = int_input(inputs, "target_impaired", minimum=0, maximum=1)
            if impaired is None:
                self.notes.append(
                    f"rune {rune.id} {rune.name}: needs --input target_impaired=0|1 ({RULES})"
                )
                self.weakened = True
                return
            if impaired == 0:
                self.notes.append(f"rune {rune.id} {rune.name}: inactive (target_impaired=0)")
                return
            _require_target_kind(rune, self.target)
            self._cheap_shot = rune
            return

        if rune.key == "SuddenImpact":
            if self.target.kind not in (None, "champion"):
                return
            armed = int_input(inputs, "sudden_impact", minimum=0, maximum=1)
            if armed is None:
                self.notes.append(
                    f"rune {rune.id} {rune.name}: needs --input sudden_impact=0|1 ({RULES})"
                )
                self.weakened = True
                return
            if armed == 0:
                self.notes.append(f"rune {rune.id} {rune.name}: inactive (sudden_impact=0)")
                return
            _require_target_kind(rune, self.target)
            self._sudden_impact = rune
            return

        if rune.key == "Demolish":
            if _require_target_kind(rune, self.target) != "structure":
                return
            if self.holder_range is None:
                raise RotationError(
                    f"rune {rune.id} {rune.name}: needs --attacker-range melee|ranged"
                )
            self._demolish = rune

    def dealt_modifiers(
        self, part_kind: str, slot: str | None, target_stats: Mapping[str, Fraction]
    ) -> list[RuneModifier]:
        """Damage-dealt percentage modifiers applicable to one part."""
        result: list[RuneModifier] = []
        current = target_stats["current_health"]
        maximum = target_stats["max_health"]
        if self._coup is not None:
            rune, percent, threshold = self._coup
            if current < threshold * maximum:
                result.append(RuneModifier(f"rune:{rune.id} {rune.key}", percent, self._base))
        if self._cut_down is not None:
            rune, percent, threshold = self._cut_down
            if current > threshold * maximum:
                result.append(RuneModifier(f"rune:{rune.id} {rune.key}", percent, self._base))
        if self._last_stand is not None:
            result.append(self._last_stand)
        if self._axiom is not None and part_kind == "ability" and slot == "R":
            result.append(self._axiom)
        result.extend(self._keystones.dealt_modifiers())
        return result

    @property
    def speed_changed(self) -> bool:
        return self._keystones.speed_changed

    def active_stat_bonuses(self, at: Fraction, base_sheet: StatSheet) -> list[RuneStatBonus]:
        return self._keystones.active_stat_bonuses(at, base_sheet)

    def healing_rate(self) -> tuple[Fraction, Label, str] | None:
        return self._keystones.healing_rate()

    def drain_runtime_updates(self) -> tuple[list[str], bool]:
        """New notes or weakening produced by keystones during rotation steps."""
        new_notes = self._keystones.notes[self._reported_keystone_notes :]
        self._reported_keystone_notes = len(self._keystones.notes)
        return new_notes, self._keystones.weakened

    def _can_fire(self, rune: Rune, clock: Fraction) -> bool:
        if not self.timeline:
            return rune.id not in self._fired
        return clock >= self._ready.get(rune.id, Fraction(0))

    def _mark_fired(self, rune: Rune, clock: Fraction, cooldown: Fraction) -> bool:
        """Record activation; return True when this is a repeat activation in timeline."""
        repeated = rune.id in self._fired
        self._fired.add(rune.id)
        if self.timeline:
            self._ready[rune.id] = clock + cooldown
        return repeated

    def on_step(
        self, slot: str | None, dealt_damage: bool, clock: Fraction, sheet: StatSheet
    ) -> list[RuneProc]:
        """Immediate rune procs for one attack or ability step (and schedule delayed procs)."""
        assert self.data is not None or not (
            self._cheap_shot or self._sudden_impact or self._scorch or self._demolish
        )
        procs: list[RuneProc] = []
        level = sheet.level

        if (
            self._cheap_shot is not None
            and dealt_damage
            and self._can_fire(self._cheap_shot, clock)
        ):
            rune = self._cheap_shot
            assert self.data is not None
            raw = linear_by_level(
                rune_value(rune, "DamageIncMin"), rune_value(rune, "DamageIncMax"), level
            )
            self._mark_fired(rune, clock, rune_value(rune, "Cooldown"))
            procs.append(
                RuneProc(
                    f"{_rune_source(rune, self.data)} ({rune.name})",
                    DamageType.TRUE,
                    raw,
                    self._base,
                    ("scenario: target_impaired=1",),
                )
            )

        if (
            self._sudden_impact is not None
            and dealt_damage
            and self._can_fire(self._sudden_impact, clock)
        ):
            rune = self._sudden_impact
            assert self.data is not None
            raw = linear_by_level(
                rune_value(rune, "MinDamageTooltip"), rune_value(rune, "MaxDamageTooltip"), level
            )
            repeated = self._mark_fired(rune, clock, rune_value(rune, "Cooldown"))
            notes = ["scenario: sudden_impact=1"]
            if repeated:
                notes.append("assumes armed again after cooldown")
            procs.append(
                RuneProc(
                    f"{_rune_source(rune, self.data)} ({rune.name})",
                    DamageType.TRUE,
                    raw,
                    self._base,
                    tuple(notes),
                )
            )

        if (
            self._scorch is not None
            and slot is not None
            and dealt_damage
            and self._can_fire(self._scorch, clock)
        ):
            rune = self._scorch
            assert self.data is not None
            raw = linear_by_level(rune_value(rune, "damage"), rune_value(rune, "damagemax"), level)
            delay = rune_value(rune, "dotduration")
            cooldown = rune_value(rune, "BurnlockoutDuration")
            self._mark_fired(rune, clock, cooldown)
            if self.timeline:
                at = clock + delay
                src = f"{_rune_source(rune, self.data)} ({rune.name}) at {format_number(at)} s"
                self._delayed.append(
                    DelayedRuneProc(at, RuneProc(src, DamageType.MAGIC, raw, self._base))
                )
            else:
                procs.append(
                    RuneProc(
                        f"{_rune_source(rune, self.data)} ({rune.name})",
                        DamageType.MAGIC,
                        raw,
                        self._base,
                        (
                            f"fires once without --timeline ({format_number(delay)} s delay and "
                            f"{format_number(cooldown)} s cooldown apply with --timeline)",
                        ),
                    )
                )

        if self._demolish is not None and slot is None:
            rune = self._demolish
            assert self.data is not None
            if not self.timeline or clock >= self._ready.get(rune.id, Fraction(0)):
                required = int(rune_value(rune, "{97664ba4}"))
                self._demolish_hits += 1
                if self._demolish_hits >= required:
                    self._demolish_hits = 0
                    self._mark_fired(rune, clock, rune_value(rune, "CooldownSeconds"))
                    health = sheet["health"]
                    try:
                        max_hp = health.total()
                    except StatBlocked as exc:
                        raise RotationError(f"rune {rune.id} {rune.name}: {exc}") from exc
                    if self.holder_range == "melee":
                        base_dmg = rune_value(rune, "BaseDamageMelee")
                        ratio = rune_value(rune, "HPRatioMelee")
                    else:
                        base_dmg = rune_value(rune, "BaseDamageRanged")
                        ratio = rune_value(rune, "HPRatioRanged")
                    demolish_notes: tuple[str, ...] = ()
                    if not self.timeline:
                        cd = format_number(rune_value(rune, "CooldownSeconds"))
                        demolish_notes = (f"without --timeline, ignores its {cd} s cooldown",)
                    procs.append(
                        RuneProc(
                            f"{_rune_source(rune, self.data)} ({rune.name})",
                            DamageType.PHYSICAL,
                            base_dmg + ratio * max_hp,
                            weakest((self._base, health.label)),
                            demolish_notes,
                        )
                    )

        procs.extend(self._keystones.on_step(slot, dealt_damage, clock, sheet))
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
        return self._keystones.on_step_complete(
            step_damage, clock, sheet, health_before, health_after, max_health
        )

    def has_active_burn(self) -> bool:
        return self._keystones.has_active_burn()

    def burn_split_times(self, start: Fraction, until: Fraction) -> list[Fraction]:
        return self._keystones.burn_split_times(start, until)

    def accrue_burn(self, begin: Fraction, finish: Fraction) -> RuneProc | None:
        return self._keystones.accrue_burn(begin, finish)

    def clear_expired_burns(self, until: Fraction) -> None:
        self._keystones.clear_expired_burns(until)

    def has_due_procs(self, until: Fraction) -> bool:
        return any(item.at <= until for item in self._delayed)

    def due_times(self, until: Fraction) -> list[Fraction]:
        return [item.at for item in self._delayed if item.at <= until]

    def pop_due(self, at: Fraction) -> list[RuneProc]:
        due = [item.proc for item in self._delayed if item.at <= at]
        if due:
            self._delayed = [item for item in self._delayed if item.at > at]
        return due

    def last_pending_time(self) -> Fraction | None:
        times = [item.at for item in self._delayed]
        burn_end = self._keystones.burn_end()
        if burn_end is not None:
            times.append(burn_end)
        return max(times) if times else None
