"""Reverse survival simulation: incoming damage, flat reduction and defensive triggers.

Evaluates how well an analyzed defender survives an enemy champion's rotation or a
manual sequence of incoming hits (MEC-08 and MEC-09, lol-knowledge/mechanics/survival.md):
- Flat post-mitigation damage reduction (Bone Plating 8473, --input flat_damage_reduction).
- Pre-damage defensive shields (Sterak's Gage Lifeline 3053, Guardian 8465), scaled by
  heal & shield power and Revitalize (<40% HP) and immune to Grievous Wounds.
- Defensive regeneration (Second Wind 8444), reduced by Grievous Wounds and unaffected by
  heal & shield power or Revitalize.
- Reactive basic-attack reflect (Thornmail 3075).
- Time to die and damage taken per second with --timeline.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from .damage import DamageType, format_number, mitigate
from .errors import RotationError, StatsError
from .formula import FormulaError, evaluate_formula
from .kit import sheet_stats
from .rotation import RotationOutcome
from .runes import Rune, RuneData, int_input, linear_by_level, rune_value
from .stats import EVIDENCE_LABEL, Label, StatBlocked, StatSheet, weakest
from .survival import (
    GRIEVOUS_WOUNDS_REDUCTION,
    HealEvent,
    ShieldEvent,
    absorb_shield,
    scale_healing,
    scale_shield,
    validate_shield_type,
)

DEFENSE_RULES = (
    "lol-knowledge/mechanics/damage-mitigation.md",
    "lol-knowledge/mechanics/damage-modifiers.md",
    "lol-knowledge/mechanics/survival.md",
    "lol-knowledge/mechanics/runes.md",
)

_TOKEN_SPLIT = re.compile(r"[\s,]+")
_DAMAGE_KINDS = {
    "physical": DamageType.PHYSICAL,
    "magic": DamageType.MAGIC,
    "true": DamageType.TRUE,
    "attack": DamageType.PHYSICAL,
}


@dataclass(frozen=True)
class IncomingHit:
    """One incoming hit or wait interval in a reverse defense simulation."""

    # "attack", "crit", "physical", "magic", "true", "ability", "burn", "rune", "execute", "wait"
    kind: str
    damage_type: DamageType | None
    amount: Fraction
    source: str
    already_mitigated: bool = False
    time: Fraction | None = None
    wait: Fraction | None = None
    crit: bool = False
    label: Label = Label.OFFICIAL


def _positive_fraction(text: str, token: str) -> Fraction:
    try:
        value = Fraction(text)
    except (ValueError, ZeroDivisionError) as exc:
        raise RotationError(f"incoming token {token!r}: invalid number {text!r}") from exc
    if value <= 0:
        raise RotationError(f"incoming token {token!r}: amount must be positive")
    return value


def parse_incoming(text: str) -> list[IncomingHit]:
    """Parse manual incoming hits: ``attack:300, attack:crit:500, magic:250, true:100, wait:1``."""
    tokens = [tok for tok in _TOKEN_SPLIT.split(text.strip()) if tok]
    if not tokens:
        raise RotationError("incoming hit list is empty")
    hits: list[IncomingHit] = []
    for token in tokens:
        parts = token.lower().split(":")
        if parts[0] == "wait":
            if len(parts) != 2:
                raise RotationError(f"incoming token {token!r}: use wait:<seconds>")
            seconds = _positive_fraction(parts[1], token)
            hits.append(IncomingHit("wait", None, Fraction(0), token, wait=seconds))
            continue
        if parts[0] == "attack" and len(parts) == 3 and parts[1] == "crit":
            amount = _positive_fraction(parts[2], token)
            hits.append(
                IncomingHit(
                    "crit",
                    DamageType.PHYSICAL,
                    amount,
                    f"manual critical basic attack ({format_number(amount)} raw)",
                    crit=True,
                )
            )
            continue
        if len(parts) == 2 and parts[0] in _DAMAGE_KINDS:
            kind = parts[0]
            dtype = _DAMAGE_KINDS[kind]
            amount = _positive_fraction(parts[1], token)
            label_kind = "basic attack" if kind == "attack" else f"{kind} hit"
            hits.append(
                IncomingHit(
                    kind,
                    dtype,
                    amount,
                    f"manual {label_kind} ({format_number(amount)} raw)",
                )
            )
            continue
        raise RotationError(
            f"unknown incoming token {token!r}: use attack:<n>, attack:crit:<n>, "
            "physical:<n>, magic:<n>, true:<n> or wait:<seconds>"
        )
    return hits


def hits_from_rotation(outcome: RotationOutcome) -> list[IncomingHit]:
    """Convert an enemy champion's RotationOutcome into post-mitigation incoming hits."""
    hits: list[IncomingHit] = []
    for step in outcome.steps:
        if not step.parts and step.step.wait is not None:
            hits.append(
                IncomingHit(
                    "wait",
                    None,
                    Fraction(0),
                    step.step.text,
                    already_mitigated=True,
                    time=step.time,
                    wait=step.step.wait,
                )
            )
            continue
        for part in step.parts:
            kind = "crit" if (part.kind == "attack" and step.step.crit) else part.kind
            hits.append(
                IncomingHit(
                    kind,
                    part.damage_type,
                    part.primary_damage,
                    f"step {step.index} {step.step.text}: {part.source}",
                    already_mitigated=True,
                    time=step.time,
                    crit=step.step.crit and part.kind == "attack",
                    label=part.label,
                )
            )
    return hits


@dataclass(frozen=True)
class DefenseStep:
    index: int
    source: str
    kind: str
    damage_type: DamageType | None
    time: Fraction | None
    incoming: Fraction
    flat_reduced: Fraction
    damage_after_flat: Fraction
    shield_absorbed: Fraction
    health_damage: Fraction
    health_before: Fraction
    health_after: Fraction
    shield_before: Fraction
    shield_after: Fraction
    shields_granted: tuple[ShieldEvent, ...] = ()
    heals: tuple[HealEvent, ...] = ()
    reactive_damage: Fraction = Fraction(0)
    label: Label = Label.DERIVED
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class DefenseOutcome:
    defender_name: str
    defender_level: int
    patch: str
    enemy_description: str
    max_health: Fraction
    start_health: Fraction
    start_shield: Fraction
    shield_type: str
    steps: tuple[DefenseStep, ...]
    label: Label
    notes: tuple[str, ...]
    timeline: bool = False

    @property
    def total_incoming(self) -> Fraction:
        return sum((s.incoming for s in self.steps), start=Fraction(0))

    @property
    def total_flat_reduced(self) -> Fraction:
        return sum((s.flat_reduced for s in self.steps), start=Fraction(0))

    @property
    def total_damage_taken(self) -> Fraction:
        return sum((s.damage_after_flat for s in self.steps), start=Fraction(0))

    @property
    def total_shield_granted(self) -> Fraction:
        return sum((ev.amount for s in self.steps for ev in s.shields_granted), start=Fraction(0))

    @property
    def total_shield_absorbed(self) -> Fraction:
        return sum((s.shield_absorbed for s in self.steps), start=Fraction(0))

    @property
    def total_healing(self) -> Fraction:
        return sum((ev.amount for s in self.steps for ev in s.heals), start=Fraction(0))

    @property
    def total_reactive_damage(self) -> Fraction:
        return sum((s.reactive_damage for s in self.steps), start=Fraction(0))

    @property
    def remaining_health(self) -> Fraction:
        return self.steps[-1].health_after if self.steps else self.start_health

    @property
    def remaining_shield(self) -> Fraction:
        return self.steps[-1].shield_after if self.steps else self.start_shield

    @property
    def survived(self) -> bool:
        return self.remaining_health > 0

    @property
    def lethal_step(self) -> int | None:
        for step in self.steps:
            if step.health_after == 0:
                return step.index
        return None

    @property
    def time_to_die(self) -> Fraction | None:
        if not self.timeline:
            return None
        for step in self.steps:
            if step.health_after == 0:
                return step.time
        return None

    @property
    def duration(self) -> Fraction | None:
        if not self.timeline or not self.steps:
            return None
        times = [s.time for s in self.steps if s.time is not None]
        return times[-1] if times else None

    @property
    def damage_taken_per_second(self) -> Fraction | None:
        dur = self.duration
        if not dur:
            return None
        return self.total_damage_taken / dur


@dataclass
class _ActiveShield:
    source: str
    remaining: Fraction
    shield_type: str
    expires_at: Fraction | None


class _DefenseSimulator:
    def __init__(
        self,
        sheet: StatSheet,
        *,
        start_health: Fraction | None,
        start_shield: Fraction,
        shield_type: str,
        runes: Sequence[int],
        rune_data: RuneData | None,
        inputs: Mapping[str, Fraction],
        timeline: bool,
    ) -> None:
        self.sheet = sheet
        self.timeline = timeline
        self.shield_type = validate_shield_type(shield_type)
        if start_shield < 0:
            raise StatsError("defender shield must not be negative")
        try:
            self.max_health = sheet["health"].total()
            self.armor = sheet["armor"].total()
            self.magic_resist = sheet["magic_resist"].total()
            self.hsp = sheet["heal_and_shield_power"].total()
        except StatBlocked as exc:
            raise RotationError(f"defense simulation needs defender stats: {exc}") from exc
        if start_health is None:
            self.start_health = self.max_health
        else:
            if start_health <= 0 or start_health > self.max_health:
                raise RotationError(
                    f"defender health must be between 0 and {format_number(self.max_health)}"
                )
            self.start_health = start_health
        self.start_shield = start_shield
        self.stats_env, self.stat_origin = sheet_stats(sheet)
        self.notes: list[str] = list(sheet.pending_effects)
        self.weakened = bool(sheet.pending_effects)

        try:
            gw_flag = int_input(inputs, "grievous_wounds", minimum=0, maximum=1)
        except StatsError as exc:
            raise RotationError(str(exc)) from exc
        self.grievous = GRIEVOUS_WOUNDS_REDUCTION if gw_flag == 1 else Fraction(0)

        self.flat_input = Fraction(0)
        if "flat_damage_reduction" in inputs:
            val = inputs["flat_damage_reduction"]
            if val < 0:
                raise RotationError(
                    f"input flat_damage_reduction: must not be negative, got {format_number(val)}"
                )
            self.flat_input = val

        # Parse defensive runes
        self.rune_data = rune_data
        self.rune_base = (
            Label.DERIVED
            if (rune_data is not None and rune_data.matches_patch(sheet.champion.patch))
            else Label.PENDING
        )
        self.bone_rune: Rune | None = None
        self.second_wind_rune: Rune | None = None
        self.guardian_rune: Rune | None = None
        self.revitalize_rune: Rune | None = None
        self.guardian_ally = False
        if runes and rune_data is not None:
            for rid in dict.fromkeys(runes):
                rune = rune_data.runes.get(rid)
                if rune is None:
                    continue
                if rune.key == "BonePlating":
                    self.bone_rune = rune
                elif rune.key == "SecondWind":
                    self.second_wind_rune = rune
                elif rune.key == "Revitalize":
                    self.revitalize_rune = rune
                elif rune.key == "Guardian":
                    try:
                        ally = int_input(inputs, "guardian_ally", minimum=0, maximum=1)
                    except StatsError as exc:
                        raise RotationError(str(exc)) from exc
                    if ally is None:
                        self.notes.append(
                            f"rune {rune.id} {rune.name}: needs --input guardian_ally=0|1"
                        )
                        self.weakened = True
                    elif ally == 0:
                        self.notes.append(f"rune {rune.id} {rune.name}: inactive (guardian_ally=0)")
                    else:
                        self.guardian_rune = rune
                        self.guardian_ally = True

        # Parse defender item effects: taken percent modifiers, reactive shields, reflect, self-amps
        self.taken_modifiers: list[tuple[str, Mapping[str, Any], Label]] = []
        self.lifeline_effects: list[tuple[str, Mapping[str, Any], Mapping[str, Any], Label]] = []
        self.reflect_effects: list[tuple[str, Mapping[str, Any], Label]] = []
        self.self_heal_amp = Fraction(1)
        self.self_shield_amp = Fraction(1)
        self.self_amp_labels: list[Label] = []
        self.self_amp_notes: list[str] = []
        for item in sheet.items:
            for effect in item.effects:
                if effect.get("model_status") != "evaluable":
                    continue
                trigger = (effect.get("trigger") or {}).get("event")
                label = EVIDENCE_LABEL.get(str(effect.get("evidence_confidence")), Label.DERIVED)
                title = f"{item.id} {effect.get('id')}"
                for comp in effect.get("components") or ():
                    kind = comp.get("kind")
                    if kind == "damage_modifier" and comp.get("direction") == "taken":
                        self.taken_modifiers.append((title, comp, label))
                    elif trigger == "taking_damage" and kind == "shield":
                        self.lifeline_effects.append((title, effect, comp, label))
                    elif trigger == "taking_attack" and kind == "damage":
                        self.reflect_effects.append((title, comp, label))
                    elif trigger == "always" and comp.get("mode") == "percent":
                        pct = evaluate_formula(
                            comp.get("formula"), self.stats_env, level=self.sheet.level
                        ).exact
                        assert pct is not None
                        if kind == "healing":
                            self.self_heal_amp *= 1 + pct / 100
                            self.self_amp_labels.append(label)
                            self.self_amp_notes.append(f"{title} +{format_number(pct)}% healing")
                        elif kind == "shield":
                            self.self_shield_amp *= 1 + pct / 100
                            self.self_amp_labels.append(label)
                            self.self_amp_notes.append(f"{title} +{format_number(pct)}% shielding")

    def _revitalize_amp(self, health: Fraction) -> Fraction:
        if self.revitalize_rune is None or self.max_health <= 0:
            return Fraction(0)
        cutoff = rune_value(self.revitalize_rune, "HealthCutoff") / 100
        if health / self.max_health < cutoff:
            return rune_value(self.revitalize_rune, "ExtraAmp") / 100
        return Fraction(0)

    def _mitigate_manual(self, hit: IncomingHit) -> tuple[Fraction, list[Label], list[str]]:
        assert hit.damage_type is not None
        res = (
            self.armor
            if hit.damage_type is DamageType.PHYSICAL
            else (self.magic_resist if hit.damage_type is DamageType.MAGIC else None)
        )
        mit = mitigate(hit.amount, hit.damage_type, res)
        dmg = mit.damage
        labels = [hit.label]
        notes: list[str] = []
        if hit.damage_type is DamageType.PHYSICAL:
            labels.append(self.sheet["armor"].label)
        elif hit.damage_type is DamageType.MAGIC:
            labels.append(self.sheet["magic_resist"].label)
        for title, comp, eff_label in self.taken_modifiers:
            src = comp.get("source")
            if src == "attack" and hit.kind not in {"attack", "crit"}:
                continue
            conds = [c.get("kind") for c in (comp.get("conditions") or ())]
            if "critical_strike" in conds and not hit.crit:
                continue
            pct = evaluate_formula(
                comp.get("formula"), self.stats_env, level=self.sheet.level
            ).exact
            assert pct is not None
            dmg *= 1 + pct / 100
            labels.append(eff_label)
            notes.append(f"{title} {format_number(pct)}%")
        return dmg, labels, notes

    def _shield_total(self, shields: list[_ActiveShield]) -> Fraction:
        return sum((s.remaining for s in shields), start=Fraction(0))

    def _expire_shields(self, shields: list[_ActiveShield], clock: Fraction) -> list[_ActiveShield]:
        if not self.timeline:
            return [s for s in shields if s.remaining > 0]
        return [
            s for s in shields if s.remaining > 0 and (s.expires_at is None or clock < s.expires_at)
        ]

    def _absorb_active(
        self,
        damage: Fraction,
        damage_type: DamageType,
        shields: list[_ActiveShield],
        *,
        bypass: bool = False,
    ) -> tuple[Fraction, Fraction]:
        if bypass or damage <= 0 or not shields:
            return Fraction(0), damage
        # Soonest-expiring shields absorb first (Shield rev 4093144).
        ordered = sorted(
            shields,
            key=lambda s: (s.expires_at is None, s.expires_at if s.expires_at is not None else 0),
        )
        rem = damage
        total_abs = Fraction(0)
        for sh in ordered:
            if rem <= 0:
                break
            abs_amt, rem = absorb_shield(rem, damage_type, sh.remaining, sh.shield_type)
            sh.remaining -= abs_amt
            total_abs += abs_amt
        return total_abs, rem

    def _reactive_reflect(self, hit: IncomingHit) -> tuple[Fraction, list[str]]:
        if hit.kind not in {"attack", "crit"} or not self.reflect_effects:
            return Fraction(0), []
        total = Fraction(0)
        notes: list[str] = []
        for title, comp, _ in self.reflect_effects:
            try:
                val = evaluate_formula(
                    comp.get("formula"), self.stats_env, level=self.sheet.level
                ).exact
            except FormulaError:
                continue
            if val and val > 0:
                total += val
                notes.append(f"reactive {title}: {format_number(val)} raw magic damage")
        return total, notes

    def run(self, hits: Sequence[IncomingHit], enemy_description: str) -> DefenseOutcome:
        if not hits:
            raise RotationError("defense simulation needs at least one incoming hit")
        health = self.start_health
        shields: list[_ActiveShield] = []
        if self.start_shield > 0:
            shields.append(
                _ActiveShield("initial shield", self.start_shield, self.shield_type, None)
            )
        clock = Fraction(0)
        steps: list[DefenseStep] = []

        # Defensive rune / item state
        bone_charges = 0
        bone_expires: Fraction | None = None
        bone_ready = Fraction(0)
        bone_used_once = False

        sw_end: Fraction | None = None
        sw_rate = Fraction(0)
        sw_last_accrued = Fraction(0)
        sw_used_once = False

        guardian_ready = Fraction(0)
        guardian_used_once = False
        guardian_window_hits: list[tuple[Fraction, Fraction]] = []

        lifeline_ready: dict[str, Fraction] = {}
        lifeline_used: set[str] = set()

        def accrue_second_wind(until: Fraction) -> tuple[list[HealEvent], Fraction]:
            nonlocal health, sw_end, sw_last_accrued
            if (
                not self.timeline
                or self.second_wind_rune is None
                or sw_end is None
                or health <= 0
                or until <= sw_last_accrued
            ):
                sw_last_accrued = max(sw_last_accrued, until)
                return [], Fraction(0)
            stop = min(until, sw_end)
            heals: list[HealEvent] = []
            gained = Fraction(0)
            if stop > sw_last_accrued and sw_rate > 0:
                span = stop - sw_last_accrued
                raw = sw_rate * span
                # Second Wind is health regeneration: reduced by Grievous Wounds,
                # unaffected by HSP or Revitalize (Template:Healing_modifiers rev 4021803).
                amt = (
                    scale_healing(
                        raw,
                        hsp=Fraction(0),
                        revitalize_amp=Fraction(0),
                        grievous=self.grievous,
                        uses_hsp=False,
                    )
                    * self.self_heal_amp
                )
                missing = max(Fraction(0), self.max_health - health)
                gained = min(amt, missing)
                health += gained
                rune = self.second_wind_rune
                assert self.rune_data is not None
                sw_notes = [f"regen {format_number(sw_last_accrued)}–{format_number(stop)} s"]
                if self.grievous:
                    sw_notes.append("Grievous Wounds (-40%)")
                heals.append(
                    HealEvent(
                        f"rune:{rune.id} {rune.key} ({rune.name})",
                        raw,
                        gained,
                        False,
                        self.grievous > 0,
                        self.rune_base,
                        tuple(sw_notes),
                    )
                )
            sw_last_accrued = until
            if sw_end <= until:
                sw_end = None
            return heals, gained

        for idx, hit in enumerate(hits, start=1):
            if hit.wait is not None:
                if not self.timeline:
                    raise RotationError(f"wait step {hit.source!r} requires --timeline")
                h_before = health
                s_before = self._shield_total(shields)
                clock += hit.wait
                shields = self._expire_shields(shields, clock)
                sw_heals, _ = accrue_second_wind(clock)
                steps.append(
                    DefenseStep(
                        idx,
                        hit.source,
                        "wait",
                        None,
                        clock,
                        Fraction(0),
                        Fraction(0),
                        Fraction(0),
                        Fraction(0),
                        Fraction(0),
                        h_before,
                        health,
                        s_before,
                        self._shield_total(shields),
                        heals=tuple(sw_heals),
                        label=self.rune_base if sw_heals else Label.OFFICIAL,
                    )
                )
                continue

            if self.timeline and hit.time is not None:
                clock = max(clock, hit.time)
            shields = self._expire_shields(shields, clock)
            sw_heals, _ = accrue_second_wind(clock)

            h_before = health
            s_before = self._shield_total(shields)
            step_notes: list[str] = []
            step_labels: list[Label] = [self.sheet["health"].label]
            granted: list[ShieldEvent] = []
            heals: list[HealEvent] = list(sw_heals)

            if hit.already_mitigated:
                incoming = hit.amount
                step_labels.append(hit.label)
            else:
                incoming, mit_labels, mit_notes = self._mitigate_manual(hit)
                step_labels.extend(mit_labels)
                step_notes.extend(mit_notes)

            # Flat damage reduction (MEC-08): Bone Plating + explicit flat_damage_reduction
            flat_red = Fraction(0)
            if self.flat_input > 0 and incoming > 0:
                applied = min(incoming, self.flat_input)
                flat_red += applied
                step_notes.append(f"flat reduction -{format_number(applied)} (scenario)")

            bone_active = (
                self.bone_rune is not None
                and bone_charges > 0
                and (not self.timeline or (bone_expires is not None and clock <= bone_expires))
            )
            if bone_active and incoming - flat_red > 0:
                assert self.bone_rune is not None
                block = linear_by_level(
                    rune_value(self.bone_rune, "BlockBase"),
                    rune_value(self.bone_rune, "BlockMax"),
                    self.sheet.level,
                )
                applied = min(incoming - flat_red, block)
                flat_red += applied
                bone_charges -= 1
                step_labels.append(self.rune_base)
                step_notes.append(
                    f"rune:{self.bone_rune.id} {self.bone_rune.name} -{format_number(applied)} "
                    f"({bone_charges} charges left)"
                )

            dmg_after_flat = max(Fraction(0), incoming - flat_red)
            bypass = hit.kind == "execute"
            assert hit.damage_type is not None

            # Pre-damage shield triggers (Sterak's Lifeline & Guardian)
            if health > 0 and dmg_after_flat > 0 and not bypass:
                # Estimate unshielded HP damage with current shields to check thresholds
                preview_shields = [
                    _ActiveShield(s.source, s.remaining, s.shield_type, s.expires_at)
                    for s in shields
                ]
                _, preview_hp_dmg = self._absorb_active(
                    dmg_after_flat, hit.damage_type, preview_shields
                )
                projected_hp = max(Fraction(0), health - preview_hp_dmg)

                # 1. Lifeline items (3053 Sterak's, 6673 Shieldbow, 3156 Maw, 3155 Hexdrinker)
                attack_range = self.sheet.champion.stats.get("attackrange")
                defender_range = (
                    None if attack_range is None else ("melee" if attack_range < 300 else "ranged")
                )
                for title, eff, comp, eff_label in self.lifeline_effects:
                    shield_kind = str(comp.get("shield_type", "normal"))
                    if shield_kind == "magic" and hit.damage_type is not DamageType.MAGIC:
                        continue
                    if shield_kind == "physical" and hit.damage_type is not DamageType.PHYSICAL:
                        continue
                    can_proc = (
                        (title not in lifeline_used)
                        if not self.timeline
                        else (clock >= lifeline_ready.get(title, Fraction(0)))
                    )
                    if not can_proc:
                        continue
                    threshold: Fraction | None = None
                    for lim in eff.get("limits") or ():
                        if lim.get("kind") == "threshold":
                            threshold = Fraction(str(lim["value"])) / 100
                    if threshold is None or projected_hp < threshold * self.max_health:
                        evaluated_sh = evaluate_formula(
                            comp.get("formula"),
                            self.stats_env,
                            holder_range=defender_range,
                            level=self.sheet.level,
                        )
                        raw_sh = evaluated_sh.exact
                        assert raw_sh is not None
                        rev_amp = self._revitalize_amp(health)
                        sh_amt = (
                            scale_shield(raw_sh, hsp=self.hsp, revitalize_amp=rev_amp)
                            * self.self_shield_amp
                        )
                        dur = (
                            Fraction(str(eff["duration_seconds"]))
                            if eff.get("duration_seconds")
                            else None
                        )
                        cd = (
                            Fraction(str(eff["cooldown_seconds"]))
                            if eff.get("cooldown_seconds")
                            else Fraction(90)
                        )
                        lifeline_used.add(title)
                        if self.timeline:
                            lifeline_ready[title] = clock + cd
                        sh_notes = [
                            f"triggered before dropping below {format_number(threshold * 100)}% HP"
                            if threshold is not None
                            else f"triggered on taking {shield_kind} damage"
                        ]
                        if self.hsp:
                            sh_notes.append(
                                f"heal & shield power +{format_number(self.hsp * 100)}%"
                            )
                        if rev_amp:
                            sh_notes.append(f"Revitalize <40% HP +{format_number(rev_amp * 100)}%")
                        if self.self_shield_amp != 1:
                            sh_notes.extend(n for n in self.self_amp_notes if "shielding" in n)
                        if dur is not None:
                            sh_notes.append(
                                f"lasts {format_number(dur)} s (decay curve not modelled)"
                                if title.startswith("3053 ")
                                else f"lasts {format_number(dur)} s"
                            )
                        dep_labels = [
                            self.stat_origin[k][1]
                            for k in evaluated_sh.dependencies
                            if k in self.stat_origin
                        ]
                        ev = ShieldEvent(
                            f"{title} ({eff.get('name', 'Lifeline')})",
                            raw_sh,
                            sh_amt,
                            shield_kind,
                            dur,
                            weakest(
                                [
                                    eff_label,
                                    self.sheet["health"].label,
                                    *dep_labels,
                                    *self.self_amp_labels,
                                ]
                            ),
                            tuple(sh_notes),
                        )
                        granted.append(ev)
                        shields.append(
                            _ActiveShield(
                                ev.source,
                                sh_amt,
                                shield_kind,
                                None if (not self.timeline or dur is None) else clock + dur,
                            )
                        )
                        step_labels.append(ev.label)
                        # Recompute projected HP after Lifeline shield
                        preview_shields = [
                            _ActiveShield(s.source, s.remaining, s.shield_type, s.expires_at)
                            for s in shields
                        ]
                        _, preview_hp_dmg = self._absorb_active(
                            dmg_after_flat, hit.damage_type, preview_shields
                        )
                        projected_hp = max(Fraction(0), health - preview_hp_dmg)

                # 2. Guardian (8465): ally nearby + threshold (50..165 in 2.5 s) or lethal damage
                if self.guardian_rune is not None and self.guardian_ally:
                    rune = self.guardian_rune
                    can_guard = (
                        (not guardian_used_once) if not self.timeline else (clock >= guardian_ready)
                    )
                    if can_guard:
                        g_win = rune_value(rune, "GuardDuration")
                        if self.timeline:
                            guardian_window_hits = [
                                item for item in guardian_window_hits if clock - item[0] <= g_win
                            ]
                        guardian_window_hits.append((clock, dmg_after_flat))
                        cum_dmg = sum((d for _, d in guardian_window_hits), start=Fraction(0))
                        g_thresh = linear_by_level(
                            rune_value(rune, "ThresholdMin"),
                            rune_value(rune, "ThresholdMax"),
                            self.sheet.level,
                        )
                        if cum_dmg >= g_thresh or projected_hp == 0:
                            guardian_used_once = True
                            guardian_window_hits = []
                            if self.timeline:
                                g_cd = linear_by_level(
                                    rune_value(rune, "Cooldown"),
                                    rune_value(rune, "CooldownMaxLevel"),
                                    self.sheet.level,
                                )
                                guardian_ready = clock + g_cd
                            ap_val = self.sheet["ability_power"].total()
                            bonus_hp = self.sheet["health"].scoped("bonus")
                            raw_g = (
                                linear_by_level(
                                    rune_value(rune, "ShieldBase"),
                                    rune_value(rune, "ShieldMax"),
                                    self.sheet.level,
                                )
                                + ap_val * rune_value(rune, "APRatio")
                                + bonus_hp * rune_value(rune, "HPRatio")
                            )
                            rev_amp = self._revitalize_amp(health)
                            g_amt = scale_shield(raw_g, hsp=self.hsp, revitalize_amp=rev_amp)
                            g_dur = rune_value(rune, "ShieldDuration")
                            g_notes = ["scenario: guardian_ally=1"]
                            if self.hsp:
                                g_notes.append(
                                    f"heal & shield power +{format_number(self.hsp * 100)}%"
                                )
                            if rev_amp:
                                g_notes.append(
                                    f"Revitalize <40% HP +{format_number(rev_amp * 100)}%"
                                )
                            ev = ShieldEvent(
                                f"rune:{rune.id} {rune.key} ({rune.name})",
                                raw_g,
                                g_amt,
                                "normal",
                                g_dur,
                                weakest((self.rune_base, self.sheet["health"].label)),
                                tuple(g_notes),
                            )
                            granted.append(ev)
                            shields.append(
                                _ActiveShield(
                                    ev.source,
                                    g_amt,
                                    "normal",
                                    None if not self.timeline else clock + g_dur,
                                )
                            )
                            step_labels.append(ev.label)

            # Absorb damage against active shields, then apply remainder to health
            absorbed, hp_dmg = self._absorb_active(
                dmg_after_flat, hit.damage_type, shields, bypass=bypass
            )
            health = max(Fraction(0), health - hp_dmg)
            shields = self._expire_shields(shields, clock)

            # Trigger Bone Plating AFTER taking > 0 health damage (triggering hit not reduced!)
            if self.bone_rune is not None and hp_dmg > 0 and health > 0:
                can_bone = (
                    (not bone_used_once)
                    if not self.timeline
                    else (clock >= bone_ready and bone_charges == 0)
                )
                if can_bone:
                    bone_used_once = True
                    bone_charges = int(rune_value(self.bone_rune, "BlockCount"))
                    dur = rune_value(self.bone_rune, "BlockDuration")
                    bone_expires = clock + dur if self.timeline else None
                    bone_ready = clock + dur + rune_value(self.bone_rune, "Cooldown")
                    step_notes.append(
                        f"rune:{self.bone_rune.id} {self.bone_rune.name} activated "
                        f"({bone_charges} charges)"
                    )

            # Trigger / refresh Second Wind after taking damage (while alive)
            if self.second_wind_rune is not None and dmg_after_flat > 0 and health > 0:
                rune = self.second_wind_rune
                pct = rune_value(rune, "RegenPercentMax")
                secs = rune_value(rune, "RegenSeconds")
                missing = max(Fraction(0), self.max_health - health)
                if self.timeline:
                    sw_rate = (missing * pct) / secs
                    sw_end = clock + secs
                    sw_last_accrued = clock
                elif not sw_used_once and missing > 0:
                    sw_used_once = True
                    raw = missing * pct
                    amt = scale_healing(
                        raw,
                        hsp=Fraction(0),
                        revitalize_amp=Fraction(0),
                        grievous=self.grievous,
                        uses_hsp=False,
                    )
                    gained = min(amt, missing)
                    health += gained
                    sw_notes = [f"full {format_number(secs)} s regen without --timeline"]
                    if self.grievous:
                        sw_notes.append("Grievous Wounds (-40%)")
                    heals.append(
                        HealEvent(
                            f"rune:{rune.id} {rune.key} ({rune.name})",
                            raw,
                            gained,
                            False,
                            self.grievous > 0,
                            self.rune_base,
                            tuple(sw_notes),
                        )
                    )

            reactive, react_notes = self._reactive_reflect(hit)
            step_notes.extend(react_notes)

            steps.append(
                DefenseStep(
                    idx,
                    hit.source,
                    hit.kind,
                    hit.damage_type,
                    None if not self.timeline else clock,
                    incoming,
                    flat_red,
                    dmg_after_flat,
                    absorbed,
                    hp_dmg,
                    h_before,
                    health,
                    s_before,
                    self._shield_total(shields),
                    tuple(granted),
                    tuple(heals),
                    reactive,
                    weakest(step_labels),
                    tuple(step_notes),
                )
            )

        # Final Second Wind regen tail in timeline mode if defender survived
        if self.timeline and sw_end is not None and health > 0 and sw_end > clock:
            h_before = health
            s_before = self._shield_total(shields)
            clock = sw_end
            shields = self._expire_shields(shields, clock)
            sw_heals, _ = accrue_second_wind(clock)
            if sw_heals:
                steps.append(
                    DefenseStep(
                        len(steps) + 1,
                        f"Second Wind regen until {format_number(clock)} s",
                        "regen",
                        None,
                        clock,
                        Fraction(0),
                        Fraction(0),
                        Fraction(0),
                        Fraction(0),
                        Fraction(0),
                        h_before,
                        health,
                        s_before,
                        self._shield_total(shields),
                        heals=tuple(sw_heals),
                        label=self.rune_base,
                    )
                )

        all_labels = [s.label for s in steps]
        if self.weakened:
            all_labels.append(Label.PENDING)
        return DefenseOutcome(
            self.sheet.champion.name,
            self.sheet.level,
            self.sheet.champion.patch,
            enemy_description,
            self.max_health,
            self.start_health,
            self.start_shield,
            self.shield_type,
            tuple(steps),
            weakest(all_labels),
            tuple(dict.fromkeys(self.notes)),
            self.timeline,
        )


def evaluate_defense(
    defender_sheet: StatSheet,
    hits: Sequence[IncomingHit],
    *,
    enemy_description: str = "manual incoming damage",
    start_health: Fraction | None = None,
    start_shield: Fraction = Fraction(0),
    shield_type: str = "normal",
    runes: Sequence[int] = (),
    rune_data: RuneData | None = None,
    inputs: Mapping[str, Fraction] | None = None,
    timeline: bool = False,
) -> DefenseOutcome:
    """Evaluate how ``defender_sheet`` survives ``hits`` (MEC-08 and MEC-09)."""
    sim = _DefenseSimulator(
        defender_sheet,
        start_health=start_health,
        start_shield=start_shield,
        shield_type=shield_type,
        runes=runes,
        rune_data=rune_data,
        inputs=inputs or {},
        timeline=timeline,
    )
    return sim.run(hits, enemy_description)
