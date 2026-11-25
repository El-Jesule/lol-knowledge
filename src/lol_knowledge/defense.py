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
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from .damage import DamageType, format_number, mitigate
from .errors import RotationError, StatsError
from .formula import ABILITY_OPS, FormulaError, evaluate_formula
from .kit import (
    CC_BLINDS_ATTACKS,
    CC_BLOCKS_ABILITIES,
    CC_BLOCKS_ATTACKS,
    ActiveEffectSpec,
    CCEffectSpec,
    Kit,
    sheet_stats,
)
from .passives import _effect_cooldown, passive_defense_specs
from .rotation import RotationOutcome
from .runes import Rune, RuneData, int_input, linear_by_level, rune_value, scale_item_cooldown
from .scenario import Target
from .stats import EVIDENCE_LABEL, Label, StatBlocked, StatSheet, weakest
from .summoners import (
    SummonerSpellData,
    SummonerSpellSpec,
    barrier_duration,
    barrier_shield,
    cleanse_tenacity,
    exhaust_values,
    heal_amount,
    resolve_loadout,
)
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
    resistances_already_live: bool = False
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
        if parts[0] == "ability" and len(parts) == 3 and parts[1] in {"physical", "magic", "true"}:
            amount = _positive_fraction(parts[2], token)
            dtype = _DAMAGE_KINDS[parts[1]]
            hits.append(
                IncomingHit(
                    "ability",
                    dtype,
                    amount,
                    f"manual {parts[1]} ability ({format_number(amount)} raw)",
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
            "ability:<physical|magic|true>:<n>, physical:<n>, magic:<n>, true:<n> "
            "or wait:<seconds>"
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


@dataclass
class _StaggerBleed:
    source: str
    end: Fraction
    rate: Fraction  # true damage per second
    label: Label


@dataclass
class _CCLock:
    kind: str
    end: Fraction
    source: str
    cleansable_by_cleanse: bool
    cleansable_by_qss: bool
    label: Label


TENACITY_MIN_DURATION = Fraction(3, 10)  # 0.3 s minimum floor (tenacity.md)


@dataclass(frozen=True)
class DefenseState:
    """Live snapshot of a defender's vital state during coupled duel simulation."""

    health: Fraction
    max_health: Fraction
    shield: Fraction
    clock: Fraction
    stasis_until: Fraction | None
    grievous_active: bool
    step_count: int
    attacks_locked_until: Fraction | None = None
    abilities_locked_until: Fraction | None = None
    suppressed_until: Fraction | None = None
    blinded_until: Fraction | None = None


@dataclass
class DefenseSession:
    """Incremental defensive simulation handle shared by ``survive`` and ``duel``."""

    snapshot_state: Callable[[], DefenseState]
    effective_resists: Callable[[Fraction], tuple[Fraction, Fraction, list[Label], list[str]]]
    target_snapshot: Callable[[Fraction], Target]
    accrue_to: Callable[
        [Fraction], tuple[list[HealEvent], Fraction, list[Label], list[str], Fraction | None]
    ]
    process_hit: Callable[..., DefenseStep]
    activate_ability_cast: Callable[
        [str, int, str | None, Fraction],
        tuple[list[ShieldEvent], list[HealEvent], list[Label], list[str]],
    ]
    activate_summoner: Callable[
        [SummonerSpellSpec, Fraction],
        tuple[list[ShieldEvent], list[HealEvent], list[Label], list[str]],
    ]
    apply_self_survival: Callable[
        [Sequence[HealEvent], Sequence[ShieldEvent], Fraction],
        tuple[Fraction, Fraction, list[HealEvent], list[ShieldEvent]],
    ]
    apply_health_cost: Callable[[Fraction], Fraction]
    set_grievous_until: Callable[[Fraction], None]
    set_shield_reaver: Callable[[Fraction, Fraction], None]
    apply_cc: Callable[..., tuple[Fraction, list[HealEvent], list[Label], list[str]]]
    cleanse_cc: Callable[..., list[str]]
    next_event_time: Callable[[Fraction, Fraction], Fraction | None]
    flush_tail: Callable[[], None]
    outcome: Callable[[str], DefenseOutcome]


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
        kit: Kit | None = None,
        summoners: Sequence[str] = (),
        summoner_data: SummonerSpellData | None = None,
        defender_casts: Sequence[str] = (),
        defender_ranks: Mapping[str, int] | None = None,
    ) -> None:
        self.sheet = sheet
        self.timeline = timeline
        self.kit = kit
        self.inputs = dict(inputs)
        self.passive_dr_specs, self.passive_shield_specs = passive_defense_specs(kit)
        self.defender_active_effects: list[tuple[str, int, ActiveEffectSpec]] = []
        if defender_casts:
            if kit is None:
                raise StatsError(f"defender_casts requires a kit for {sheet.champion.id}")
            ranks_upper = {k.upper(): int(v) for k, v in (defender_ranks or {}).items()}
            for raw_tok in defender_casts:
                tok = raw_tok.strip()
                if not tok:
                    continue
                slot_part, sep, rank_part = tok.partition("=")
                slot_head, _, case_part = slot_part.partition(".")
                slot = slot_head.strip().upper()
                case_id = case_part.strip() or None
                if slot not in {"Q", "W", "E", "R"}:
                    raise StatsError(
                        f"defender cast {tok!r}: expected Q, W, E or R (optionally SLOT=RANK)"
                    )
                ab = kit.ability(slot)
                if sep:
                    try:
                        rank = int(rank_part.strip())
                    except ValueError as exc:
                        raise StatsError(f"defender cast {tok!r}: rank must be an integer") from exc
                elif slot in ranks_upper:
                    rank = ranks_upper[slot]
                else:
                    raise StatsError(
                        f"defender cast {tok!r}: specify rank with --learned {slot}=<rank> "
                        f"or {slot}=<rank>"
                    )
                if not 1 <= rank <= ab.max_rank:
                    raise StatsError(f"defender cast {tok!r}: {slot} rank must be 1..{ab.max_rank}")
                matched = [e for e in ab.active_effects if e.applies_to_case(case_id)]
                if not matched:
                    raise StatsError(
                        f"defender cast {tok!r}: {sheet.champion.id} {slot} has no modelled "
                        "active_effects"
                    )
                for eff in matched:
                    self.defender_active_effects.append((slot, rank, eff))
        self.summoner_exhaust: SummonerSpellSpec | None = None
        self.summoner_barrier: SummonerSpellSpec | None = None
        self.summoner_heal: SummonerSpellSpec | None = None
        self.summoner_cleanse: SummonerSpellSpec | None = None
        self.summoner_label = Label.DERIVED
        self.summoner_heal_debuffed = inputs.get("heal_debuffed", Fraction(0)) > 0
        self.summoner_init_notes: list[str] = []
        if summoners:
            if summoner_data is None:
                raise StatsError(
                    "summoner spells require lol-knowledge/derived/summoner-spells.json"
                )
            resolved_summs, _ = resolve_loadout(summoners, summoner_data)
            self.summoner_label = summoner_data.label_for(sheet.champion.patch)
            for sp in resolved_summs:
                if sp.id == "SummonerExhaust":
                    self.summoner_exhaust = sp
                elif sp.id == "SummonerBarrier":
                    self.summoner_barrier = sp
                elif sp.id == "SummonerHeal":
                    self.summoner_heal = sp
                elif sp.id == "SummonerBoost":
                    self.summoner_cleanse = sp
                    ten, dur = cleanse_tenacity(sp)
                    self.summoner_init_notes.append(
                        f"summoner:{sp.id} ({sp.name}): removes CC (except suppression/airborne) "
                        f"and enemy summoner debuffs + {format_number(ten * 100)}% tenacity "
                        f"for {format_number(dur)} s"
                    )
        self.shield_type = validate_shield_type(shield_type)
        if start_shield < 0:
            raise StatsError("defender shield must not be negative")
        try:
            self.max_health = sheet["health"].total()
            self.base_health = sheet["health"].scoped("base")
            self.bonus_health = sheet["health"].scoped("bonus")
            self.armor = sheet["armor"].total()
            self.magic_resist = sheet["magic_resist"].total()
            self.bonus_armor = sheet["armor"].scoped("bonus")
            self.bonus_mr = sheet["magic_resist"].scoped("bonus")
            self.hsp = sheet["heal_and_shield_power"].total()
        except StatBlocked as exc:
            raise RotationError(f"defense simulation needs defender stats: {exc}") from exc
        attack_range = sheet.champion.stats.get("attackrange")
        self.defender_range: str | None = (
            None if attack_range is None else ("melee" if attack_range < 300 else "ranged")
        )
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
        self.notes: list[str] = [*sheet.pending_effects, *self.summoner_init_notes]
        self.weakened = bool(sheet.pending_effects)

        try:
            gw_flag = int_input(inputs, "grievous_wounds", minimum=0, maximum=1)
            self.aoe_dot_flag = int_input(inputs, "aoe_dot", minimum=0, maximum=1) == 1
            self.potion_active_flag = int_input(inputs, "potion_active", minimum=0, maximum=1) == 1
            self.dream_maker_active = (
                int_input(inputs, "dream_maker_active", minimum=0, maximum=1) == 1
            )
        except StatsError as exc:
            raise RotationError(str(exc)) from exc
        self.grievous = GRIEVOUS_WOUNDS_REDUCTION if gw_flag == 1 else Fraction(0)

        self.shield_reaver_rate = Fraction(0)
        if "shield_reaver" in inputs:
            sr_val = inputs["shield_reaver"]
            if sr_val == 1:
                self.shield_reaver_rate = Fraction(1, 2)
            elif Fraction(0) <= sr_val <= Fraction(1):
                self.shield_reaver_rate = sr_val
            else:
                raise RotationError(
                    "input shield_reaver: must be 0..1 (e.g. 0.5 or 0.35), "
                    f"got {format_number(sr_val)}"
                )

        self.worthy_ally_taken = Fraction(0)
        if "worthy_ally_damage_taken" in inputs:
            wa_val = inputs["worthy_ally_damage_taken"]
            if wa_val < 0:
                raise RotationError("input worthy_ally_damage_taken must not be negative")
            self.worthy_ally_taken = wa_val

        self.item_ids: frozenset[str] = frozenset(item.id for item in sheet.items)
        self.has_dorans_shield = "1054" in self.item_ids
        self.has_warmogs = "3083" in self.item_ids and self.bonus_health >= 2000
        self.has_guardian_angel = "3026" in self.item_ids
        self.has_eternity = bool({"6657", "3803"} & self.item_ids)
        self.has_knights_vow = "3109" in self.item_ids

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
        self.aftershock_rune: Rune | None = None
        self.unflinching_rune: Rune | None = None
        self.item_haste = Fraction(0)
        self.time_warp_ratio = Fraction(0)
        self.guardian_ally = False
        try:
            self.aftershock_active = (
                int_input(inputs, "aftershock_active", minimum=0, maximum=1) == 1
                or int_input(inputs, "target_impaired", minimum=0, maximum=1) == 1
            )
            self.defender_impaired = (
                int_input(inputs, "defender_impaired", minimum=0, maximum=1) == 1
                or int_input(inputs, "cc_taken", minimum=0, maximum=1) == 1
            )
            self.glacial_ally = int_input(inputs, "glacial_ally", minimum=0, maximum=1) == 1
        except StatsError as exc:
            raise RotationError(str(exc)) from exc
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
                elif rune.key == "Aftershock":
                    self.aftershock_rune = rune
                elif rune.key == "Unflinching":
                    # Avoid double-counting if minor_rune_effects already added Unflinching to sheet
                    already_in_sheet = any(
                        "Unflinching" in c.source for c in sheet["armor"].contributions
                    )
                    if not already_in_sheet:
                        self.unflinching_rune = rune
                elif rune.key == "CosmicInsight":
                    self.item_haste += rune_value(rune, "ItemHaste")
                elif rune.key == "TimeWarpTonic":
                    self.time_warp_ratio = rune_value(rune, "RestorationPercentage")
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

        # Parse defender item effects: taken modifiers, reactive shields, reflect, self-amps,
        # spell shields, resist ramps/stacks, Lifeline vitality, and damage stagger.
        self.taken_modifiers: list[tuple[str, Mapping[str, Any], Label]] = []
        self.flat_taken_modifiers: list[
            tuple[str, Mapping[str, Any], Mapping[str, Any], Label]
        ] = []
        self.timed_taken_modifiers: list[
            tuple[str, Mapping[str, Any], Mapping[str, Any], Label]
        ] = []
        self.spell_shields: list[tuple[str, Mapping[str, Any], Label]] = []
        self.combat_resist_ramps: list[tuple[str, Mapping[str, Any], Mapping[str, Any], Label]] = []
        self.stacking_resist_effects: list[
            tuple[str, Mapping[str, Any], Mapping[str, Any], Label]
        ] = []
        self.stagger_effects: list[tuple[str, Mapping[str, Any], Mapping[str, Any], Label]] = []
        self.lifeline_effects: list[tuple[str, Mapping[str, Any], Mapping[str, Any], Label]] = []
        self.lifeline_vitality_effects: list[tuple[str, Mapping[str, Any], Label]] = []
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
                comps = effect.get("components") or ()
                # Lifeline vitality (e.g. 2525 Protoplasm Harness: temp max HP + HoT below 30% HP)
                if (
                    trigger == "taking_damage"
                    and any(lim.get("kind") == "threshold" for lim in (effect.get("limits") or ()))
                    and any(
                        c.get("kind") == "stat_modifier" and c.get("stat") == "health"
                        for c in comps
                    )
                ):
                    self.lifeline_vitality_effects.append((title, effect, label))
                    continue
                for comp in comps:
                    kind = comp.get("kind")
                    if kind == "damage_modifier" and comp.get("direction") == "taken":
                        if comp.get("mode") == "flat":
                            self.flat_taken_modifiers.append((title, effect, comp, label))
                        elif effect.get("duration_seconds") is not None:
                            self.timed_taken_modifiers.append((title, effect, comp, label))
                        else:
                            self.taken_modifiers.append((title, comp, label))
                    elif trigger == "taking_damage" and kind == "shield":
                        self.lifeline_effects.append((title, effect, comp, label))
                    elif (
                        trigger == "taking_damage"
                        and kind == "status"
                        and comp.get("effect") == "spell_shield"
                    ):
                        self.spell_shields.append((title, effect, label))
                    elif trigger == "taking_damage" and kind == "damage_stagger":
                        self.stagger_effects.append((title, effect, comp, label))
                    elif trigger == "taking_damage" and kind == "stat_modifier":
                        if comp.get("delay_seconds") is not None:
                            self.combat_resist_ramps.append((title, effect, comp, label))
                        elif isinstance(effect.get("stacks"), Mapping):
                            self.stacking_resist_effects.append((title, effect, comp, label))
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

    def _mitigate_manual(
        self,
        hit: IncomingHit,
        armor: Fraction | None = None,
        magic_resist: Fraction | None = None,
    ) -> tuple[Fraction, list[Label], list[str]]:
        assert hit.damage_type is not None
        eff_armor = self.armor if armor is None else armor
        eff_mr = self.magic_resist if magic_resist is None else magic_resist
        res = (
            eff_armor
            if hit.damage_type is DamageType.PHYSICAL
            else (eff_mr if hit.damage_type is DamageType.MAGIC else None)
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

    def _active_duration(self, eff: ActiveEffectSpec, rank: int) -> Fraction | None:
        if eff.duration_seconds is not None:
            return eff.duration_seconds
        if eff.duration_formula is not None:
            res = evaluate_formula(
                eff.duration_formula,
                self.stats_env,
                rank=rank,
                level=self.sheet.level,
                inputs=self.inputs,
                ops=ABILITY_OPS,
            )
            return res.exact
        return None

    def _eval_active_formula(
        self,
        formula: Mapping[str, Any],
        rank: int,
        base_label: Label,
        *,
        current_health: Fraction | None = None,
        current_max_health: Fraction | None = None,
    ) -> tuple[Fraction, Label]:
        env = dict(self.stats_env)
        max_hp = current_max_health if current_max_health is not None else self.max_health
        cur_hp = current_health if current_health is not None else self.start_health
        env["max_health"] = max_hp
        env["current_health"] = cur_hp
        env["missing_fraction_health"] = (
            max(Fraction(0), max_hp - cur_hp) / max_hp if max_hp > 0 else Fraction(0)
        )
        res = evaluate_formula(
            formula,
            env,
            rank=rank,
            level=self.sheet.level,
            inputs=self.inputs,
            ops=ABILITY_OPS,
        )
        assert res.exact is not None
        dep_lbls = [self.stat_origin[k][1] for k in res.dependencies if k in self.stat_origin]
        return res.exact, weakest([base_label, *dep_lbls])

    def _eval_active(
        self,
        eff: ActiveEffectSpec,
        rank: int,
        *,
        current_health: Fraction | None = None,
        current_max_health: Fraction | None = None,
    ) -> tuple[Fraction, Label]:
        return self._eval_active_formula(
            eff.formula,
            rank,
            eff.label,
            current_health=current_health,
            current_max_health=current_max_health,
        )

    def open_session(self) -> DefenseSession:
        health = self.start_health
        current_max_health = self.max_health
        shields: list[_ActiveShield] = []
        if self.start_shield > 0:
            shields.append(
                _ActiveShield("initial shield", self.start_shield, self.shield_type, None)
            )
        clock = Fraction(0)
        steps: list[DefenseStep] = []
        base_grievous = self.grievous
        dynamic_grievous_until: Fraction | None = None
        base_sr_rate = self.shield_reaver_rate
        dynamic_sr_rate = Fraction(0)
        dynamic_sr_until: Fraction | None = None

        def _sync_dynamic_debuffs(at: Fraction) -> None:
            if base_grievous > 0 or (
                dynamic_grievous_until is not None and at < dynamic_grievous_until
            ):
                self.grievous = GRIEVOUS_WOUNDS_REDUCTION
            else:
                self.grievous = Fraction(0)
            if dynamic_sr_until is not None and at < dynamic_sr_until:
                self.shield_reaver_rate = max(base_sr_rate, dynamic_sr_rate)
            else:
                self.shield_reaver_rate = base_sr_rate

        # Defensive rune / item / summoner state
        bone_charges = 0
        bone_expires: Fraction | None = None
        bone_ready = Fraction(0)
        bone_used_once = False

        exhaust_used = False
        exhaust_end: Fraction | None = None
        barrier_used = False
        heal_used = False

        active_cast_triggered = False
        active_resist_buffs: list[tuple[Fraction | None, str, str, Fraction, str, Label]] = []
        active_hp_buffs: list[tuple[Fraction, Fraction]] = []
        active_percent_dr: list[
            tuple[Fraction | None, DamageType | None, Fraction, str, Label]
        ] = []
        active_flat_dr: list[
            tuple[Fraction | None, DamageType | None, Fraction, Fraction | None, str, Label]
        ] = []
        active_instant_heals: list[tuple[str, str, ActiveEffectSpec, int]] = []
        active_hots: list[tuple[Fraction, Fraction, str, Label, bool]] = []
        active_dodge_ends: list[tuple[Fraction | None, str, Label]] = []
        active_spell_shields: list[list[Any]] = []
        active_first_hit_blocks: list[list[Any]] = []
        active_invuln_ends: list[tuple[Fraction | None, str, Label]] = []
        active_undying: list[tuple[Fraction | None, Fraction, str, Label]] = []
        pending_recent_heals: list[tuple[str, ActiveEffectSpec, int]] = []
        pending_recent_shields: list[tuple[str, ActiveEffectSpec, int, Fraction | None]] = []
        recent_damage_history: list[tuple[Fraction, Fraction]] = []
        spell_shield_slots: set[str] = set()
        spell_shield_blocked_slots: set[str] = set()

        sw_end: Fraction | None = None
        sw_rate = Fraction(0)
        sw_used_once = False

        proto_heal_end: Fraction | None = None
        proto_heal_rate = Fraction(0)
        proto_heal_source = ""
        proto_heal_label = Label.DERIVED
        proto_hp_end: Fraction | None = None
        proto_hp_gain = Fraction(0)

        stagger_bleeds: list[_StaggerBleed] = []
        last_accrued = Fraction(0)

        guardian_ready = Fraction(0)
        guardian_used_once = False
        guardian_window_hits: list[tuple[Fraction, Fraction]] = []

        lifeline_ready: dict[str, Fraction] = {}
        lifeline_used: set[str] = set()
        passive_shield_ready: dict[str, Fraction] = {}
        passive_shield_used: set[str] = set()
        passive_dr_ready: dict[str, Fraction] = {}
        passive_dr_used: set[str] = set()

        spell_shield_ready: dict[str, Fraction] = {}
        spell_shield_used: set[str] = set()

        timed_dr_end: dict[str, Fraction] = {}
        timed_dr_ready: dict[str, Fraction] = {}
        timed_dr_used: set[str] = set()

        jaksho_start: Fraction | None = None
        jaksho_noted_no_timeline = False

        # Additional Block 1 defensive item states (1054, 3083, 3026, 6695, 2003/2031, 3870, 3109)
        dshield_end: Fraction | None = None
        dshield_rate = Fraction(0)
        dshield_used_once = False

        last_champ_hit: Fraction | None = None

        ga_ready = Fraction(0)
        ga_used_once = False
        ga_stasis_until: Fraction | None = None

        shield_reaver_until: Fraction | None = None
        shield_reaver_applied = False

        potion_end: Fraction | None = None
        potion_rate = Fraction(0)
        potion_source = ""
        potion_upfront = Fraction(0)
        if self.potion_active_flag and ("2003" in self.item_ids or "2031" in self.item_ids):
            total_pot = Fraction(120) if "2003" in self.item_ids else Fraction(100)
            dur_pot = Fraction(15) if "2003" in self.item_ids else Fraction(12)
            potion_source = (
                "2003 consume (Poción de vida)"
                if "2003" in self.item_ids
                else "2031 consume (Poción reutilizable)"
            )
            if self.time_warp_ratio > 0:
                potion_upfront = total_pot * self.time_warp_ratio
                total_pot -= potion_upfront
            potion_rate = total_pot / dur_pot
            potion_end = dur_pot if self.timeline else None
        potion_used_once = False
        potion_upfront_applied = False

        dream_dr_armed = self.dream_maker_active
        knights_vow_applied = False

        fon_stacks: dict[str, int] = {}
        fon_last_hit: dict[str, Fraction] = {}
        fon_active_until: dict[str, Fraction] = {}

        stagger_noted_no_timeline = False
        cc_locks: list[_CCLock] = []
        cc_immune_windows: list[tuple[Fraction | None, bool, str, Label]] = []
        cleanse_tenacity_until: Fraction | None = None
        cleanse_tenacity_val = Fraction(0)
        unflinching_cc_until: Fraction | None = None

        def effective_resists(at: Fraction) -> tuple[Fraction, Fraction, list[Label], list[str]]:
            cur_armor = self.armor
            cur_mr = self.magic_resist
            extra_bonus_armor = Fraction(0)
            extra_bonus_mr = Fraction(0)
            res_labels: list[Label] = []
            res_notes: list[str] = []

            # 8242 Unflinching (+10 Armor/MR while CC'd / 2 s after)
            live_impaired = self.defender_impaired or (
                unflinching_cc_until is not None and at < unflinching_cc_until
            )
            if self.unflinching_rune is not None and live_impaired:
                u_val = rune_value(self.unflinching_rune, "ResistMax")
                cur_armor += u_val
                cur_mr += u_val
                extra_bonus_armor += u_val
                extra_bonus_mr += u_val
                res_labels.append(self.rune_base)
                res_notes.append(
                    f"rune:{self.unflinching_rune.id} Unflinching "
                    f"(+{format_number(u_val)} Armor/MR)"
                )

            # 8439 Aftershock (+45 + 75% bonus resist, capped 80..150 for 2.5 s)
            if self.aftershock_rune is not None and self.aftershock_active:
                as_dur = rune_value(self.aftershock_rune, "DelayBeforeBurst")
                if not self.timeline or at < as_dur:
                    flat_r = rune_value(self.aftershock_rune, "FlatResists")
                    pct_r = rune_value(self.aftershock_rune, "PercentBonusResist")
                    cap_r = linear_by_level(
                        rune_value(self.aftershock_rune, "BonusResistMin"),
                        rune_value(self.aftershock_rune, "BonusResistMax"),
                        self.sheet.level,
                    )
                    a_gain = min(cap_r, flat_r + self.bonus_armor * pct_r)
                    m_gain = min(cap_r, flat_r + self.bonus_mr * pct_r)
                    cur_armor += a_gain
                    cur_mr += m_gain
                    extra_bonus_armor += a_gain
                    extra_bonus_mr += m_gain
                    res_labels.append(self.rune_base)
                    res_notes.append(
                        f"rune:{self.aftershock_rune.id} Aftershock "
                        f"(+{format_number(a_gain)} Armor, +{format_number(m_gain)} MR)"
                    )

            for title, eff, comp, eff_label in self.stacking_resist_effects:
                active = (
                    (title in fon_active_until and at < fon_active_until[title])
                    if self.timeline
                    else (
                        fon_stacks.get(title, 0)
                        >= int((eff.get("stacks") or {}).get("required", 8))
                    )
                )
                if not active:
                    continue
                val = evaluate_formula(
                    comp.get("formula"),
                    self.stats_env,
                    holder_range=self.defender_range,
                    level=self.sheet.level,
                ).exact
                assert val is not None
                if comp.get("stat") == "magic_resist":
                    cur_mr += val
                    extra_bonus_mr += val
                elif comp.get("stat") == "armor":
                    cur_armor += val
                    extra_bonus_armor += val
                res_labels.append(eff_label)
                res_notes.append(f"{title} (+{format_number(val)} {comp.get('stat')})")

            if self.timeline and jaksho_start is not None:
                for title, _, comp, eff_label in self.combat_resist_ramps:
                    delay = Fraction(str(comp["delay_seconds"]))
                    if at - jaksho_start < delay:
                        continue
                    pct = evaluate_formula(
                        comp.get("formula"),
                        self.stats_env,
                        holder_range=self.defender_range,
                        level=self.sheet.level,
                    ).exact
                    assert pct is not None
                    if comp.get("stat") == "armor":
                        gain = (self.bonus_armor + extra_bonus_armor) * pct / 100
                        cur_armor += gain
                    elif comp.get("stat") == "magic_resist":
                        gain = (self.bonus_mr + extra_bonus_mr) * pct / 100
                        cur_mr += gain
                    else:
                        gain = Fraction(0)
                    if gain > 0:
                        res_labels.append(eff_label)
                        res_notes.append(f"{title} (+{format_number(gain)} {comp.get('stat')})")

            for end_t, st_id, mode, val, src, lbl in active_resist_buffs:
                if end_t is not None and at >= end_t:
                    continue
                if st_id == "armor":
                    gain = cur_armor * val / 100 if mode == "percent" else val
                    cur_armor += gain
                    extra_bonus_armor += gain
                elif st_id == "magic_resist":
                    gain = cur_mr * val / 100 if mode == "percent" else val
                    cur_mr += gain
                    extra_bonus_mr += gain
                else:
                    continue
                if gain > 0:
                    res_labels.append(lbl)
                    res_notes.append(f"{src} (+{format_number(gain)} {st_id})")
            return cur_armor, cur_mr, res_labels, res_notes

        def accrue_continuous(
            until: Fraction,
        ) -> tuple[list[HealEvent], Fraction, list[Label], list[str], Fraction | None]:
            """Accrue Second Wind, Protoplasm, Doran's, Warmog's, potions and bleeds."""
            nonlocal health, current_max_health, sw_end, last_accrued
            nonlocal proto_heal_end, proto_heal_rate, proto_hp_end, proto_hp_gain
            nonlocal dshield_end, dshield_rate, potion_end, potion_rate
            nonlocal stagger_bleeds, active_hots, active_hp_buffs
            if not self.timeline or until <= last_accrued:
                last_accrued = max(last_accrued, until)
                return [], Fraction(0), [], [], None
            if health <= 0:
                last_accrued = until
                return [], Fraction(0), [], [], None

            heals_out: list[HealEvent] = []
            sw_raw_total = Fraction(0)
            sw_gained_total = Fraction(0)
            sw_start_t: Fraction | None = None
            sw_end_t: Fraction | None = None

            proto_raw_total = Fraction(0)
            proto_gained_total = Fraction(0)
            proto_start_t: Fraction | None = None
            proto_end_t: Fraction | None = None

            ds_raw_total = Fraction(0)
            ds_gained_total = Fraction(0)
            ds_start_t: Fraction | None = None
            ds_end_t: Fraction | None = None

            wm_raw_total = Fraction(0)
            wm_gained_total = Fraction(0)
            wm_start_t: Fraction | None = None
            wm_end_t: Fraction | None = None

            pot_raw_total = Fraction(0)
            pot_gained_total = Fraction(0)
            pot_start_t: Fraction | None = None
            pot_end_t: Fraction | None = None

            ahot_totals: dict[str, list[Any]] = {}

            bleed_total = Fraction(0)
            bleed_labels: list[Label] = []
            bleed_notes: list[str] = []
            died_at: Fraction | None = None

            warmog_start = (
                (last_champ_hit + 8) if (self.has_warmogs and last_champ_hit is not None) else None
            )

            t = last_accrued
            while t < until and health > 0:
                boundaries = [until]
                if sw_end is not None and t < sw_end < until:
                    boundaries.append(sw_end)
                if proto_heal_end is not None and t < proto_heal_end < until:
                    boundaries.append(proto_heal_end)
                if proto_hp_end is not None and t < proto_hp_end < until:
                    boundaries.append(proto_hp_end)
                if dshield_end is not None and t < dshield_end < until:
                    boundaries.append(dshield_end)
                if warmog_start is not None and t < warmog_start < until:
                    boundaries.append(warmog_start)
                if potion_end is not None and t < potion_end < until:
                    boundaries.append(potion_end)
                for b in stagger_bleeds:
                    if t < b.end < until:
                        boundaries.append(b.end)
                for h_end, _, _, _, _ in active_hots:
                    if t < h_end < until:
                        boundaries.append(h_end)
                for hp_end, _ in active_hp_buffs:
                    if t < hp_end < until:
                        boundaries.append(hp_end)
                t_next = min(boundaries)
                span = t_next - t

                active_bleeds = [b for b in stagger_bleeds if b.end > t]
                bleed_rate = sum((b.rate for b in active_bleeds), start=Fraction(0))

                def _regen_eff(raw_rate: Fraction) -> Fraction:
                    return (
                        scale_healing(
                            raw_rate,
                            hsp=Fraction(0),
                            revitalize_amp=Fraction(0),
                            grievous=self.grievous,
                            uses_hsp=False,
                        )
                        * self.self_heal_amp
                    )

                sw_active = self.second_wind_rune is not None and sw_end is not None and sw_end > t
                sw_eff_rate = _regen_eff(sw_rate) if (sw_active and sw_rate > 0) else Fraction(0)

                proto_active = (
                    proto_heal_end is not None and proto_heal_end > t and proto_heal_rate > 0
                )
                proto_eff_rate = _regen_eff(proto_heal_rate) if proto_active else Fraction(0)

                ds_active = (
                    self.has_dorans_shield
                    and dshield_end is not None
                    and dshield_end > t
                    and dshield_rate > 0
                )
                ds_eff_rate = _regen_eff(dshield_rate) if ds_active else Fraction(0)

                wm_active = (
                    warmog_start is not None and t >= warmog_start and health < current_max_health
                )
                wm_raw_rate = current_max_health * Fraction(3, 100) if wm_active else Fraction(0)
                wm_eff_rate = _regen_eff(wm_raw_rate) if wm_active else Fraction(0)

                pot_active = potion_end is not None and potion_end > t and potion_rate > 0
                pot_eff_rate = _regen_eff(potion_rate) if pot_active else Fraction(0)

                rev_now = self._revitalize_amp(health)
                cur_hots = [
                    (
                        h_raw,
                        scale_healing(
                            h_raw,
                            hsp=self.hsp if h_hsp else Fraction(0),
                            revitalize_amp=rev_now if h_hsp else Fraction(0),
                            grievous=self.grievous,
                            uses_hsp=h_hsp,
                        )
                        * self.self_heal_amp,
                        h_src,
                        h_lbl,
                        h_hsp,
                    )
                    for h_end, h_raw, h_src, h_lbl, h_hsp in active_hots
                    if h_end > t and h_raw > 0
                ]
                ahot_eff_rate = sum((x[1] for x in cur_hots), start=Fraction(0))

                total_eff_heal_rate = (
                    sw_eff_rate
                    + proto_eff_rate
                    + ds_eff_rate
                    + wm_eff_rate
                    + pot_eff_rate
                    + ahot_eff_rate
                )
                net_rate = total_eff_heal_rate - bleed_rate
                if net_rate < 0 and health + net_rate * span <= 0:
                    lethal_span = health / (-net_rate)
                    t_die = t + lethal_span
                    if sw_active and sw_rate > 0:
                        sw_start_t = t if sw_start_t is None else sw_start_t
                        sw_end_t = t_die
                        sw_raw_total += sw_rate * lethal_span
                        sw_gained_total += sw_eff_rate * lethal_span
                    if proto_active:
                        proto_start_t = t if proto_start_t is None else proto_start_t
                        proto_end_t = t_die
                        proto_raw_total += proto_heal_rate * lethal_span
                        proto_gained_total += proto_eff_rate * lethal_span
                    if ds_active:
                        ds_start_t = t if ds_start_t is None else ds_start_t
                        ds_end_t = t_die
                        ds_raw_total += dshield_rate * lethal_span
                        ds_gained_total += ds_eff_rate * lethal_span
                    if pot_active:
                        pot_start_t = t if pot_start_t is None else pot_start_t
                        pot_end_t = t_die
                        pot_raw_total += potion_rate * lethal_span
                        pot_gained_total += pot_eff_rate * lethal_span
                    if bleed_rate > 0:
                        bleed_total += bleed_rate * lethal_span
                        bleed_labels.extend(b.label for b in active_bleeds)
                    health = Fraction(0)
                    died_at = t_die
                    t = t_die
                    break

                if bleed_rate > 0:
                    bleed_total += bleed_rate * span
                    bleed_labels.extend(b.label for b in active_bleeds)
                new_hp = health + net_rate * span
                ratio = Fraction(1)
                if new_hp > current_max_health:
                    avail = max(Fraction(0), current_max_health - (health - bleed_rate * span))
                    total_heal_eff = total_eff_heal_rate * span
                    ratio = avail / total_heal_eff if total_heal_eff > 0 else Fraction(0)
                    health = current_max_health
                else:
                    health = max(Fraction(0), new_hp)

                if sw_active and sw_rate > 0:
                    sw_start_t = t if sw_start_t is None else sw_start_t
                    sw_end_t = t_next
                    sw_raw_total += sw_rate * span
                    sw_gained_total += sw_eff_rate * span * ratio
                if proto_active:
                    proto_start_t = t if proto_start_t is None else proto_start_t
                    proto_end_t = t_next
                    proto_raw_total += proto_heal_rate * span
                    proto_gained_total += proto_eff_rate * span * ratio
                if ds_active:
                    ds_start_t = t if ds_start_t is None else ds_start_t
                    ds_end_t = t_next
                    ds_raw_total += dshield_rate * span
                    ds_gained_total += ds_eff_rate * span * ratio
                if wm_active:
                    wm_start_t = t if wm_start_t is None else wm_start_t
                    wm_end_t = t_next
                    wm_raw_total += wm_raw_rate * span
                    wm_gained_total += wm_eff_rate * span * ratio
                if pot_active:
                    pot_start_t = t if pot_start_t is None else pot_start_t
                    pot_end_t = t_next
                    pot_raw_total += potion_rate * span
                    pot_gained_total += pot_eff_rate * span * ratio
                for h_raw, h_eff, h_src, h_lbl, h_hsp in cur_hots:
                    bucket = ahot_totals.setdefault(
                        h_src, [Fraction(0), Fraction(0), t, t_next, h_lbl, h_hsp]
                    )
                    bucket[0] += h_raw * span
                    bucket[1] += h_eff * span * ratio
                    bucket[3] = t_next

                t = t_next
                stagger_bleeds = [b for b in stagger_bleeds if b.end > t]
                active_hots = [h for h in active_hots if h[0] > t]
                kept_hp_buffs: list[tuple[Fraction, Fraction]] = []
                for hp_end, hp_gain in active_hp_buffs:
                    if hp_end <= t:
                        current_max_health -= hp_gain
                        health = min(health, current_max_health)
                    else:
                        kept_hp_buffs.append((hp_end, hp_gain))
                active_hp_buffs = kept_hp_buffs
                if sw_end is not None and sw_end <= t:
                    sw_end = None
                if proto_heal_end is not None and proto_heal_end <= t:
                    proto_heal_end = None
                if dshield_end is not None and dshield_end <= t:
                    dshield_end = None
                if potion_end is not None and potion_end <= t:
                    potion_end = None
                if proto_hp_end is not None and proto_hp_end <= t:
                    current_max_health -= proto_hp_gain
                    health = min(health, current_max_health)
                    proto_hp_gain = Fraction(0)
                    proto_hp_end = None

            last_accrued = t
            if sw_raw_total > 0 and self.second_wind_rune is not None:
                rune = self.second_wind_rune
                assert sw_start_t is not None and sw_end_t is not None
                sw_notes = [f"regen {format_number(sw_start_t)}–{format_number(sw_end_t)} s"]
                if self.grievous:
                    sw_notes.append("Grievous Wounds (-40%)")
                heals_out.append(
                    HealEvent(
                        f"rune:{rune.id} {rune.key} ({rune.name})",
                        sw_raw_total,
                        sw_gained_total,
                        False,
                        self.grievous > 0,
                        self.rune_base,
                        tuple(sw_notes),
                    )
                )
            if proto_raw_total > 0:
                assert proto_start_t is not None and proto_end_t is not None
                p_notes = [f"regen {format_number(proto_start_t)}–{format_number(proto_end_t)} s"]
                if self.grievous:
                    p_notes.append("Grievous Wounds (-40%)")
                heals_out.append(
                    HealEvent(
                        proto_heal_source,
                        proto_raw_total,
                        proto_gained_total,
                        False,
                        self.grievous > 0,
                        proto_heal_label,
                        tuple(p_notes),
                    )
                )
            if ds_raw_total > 0:
                assert ds_start_t is not None and ds_end_t is not None
                ds_notes = [f"regen {format_number(ds_start_t)}–{format_number(ds_end_t)} s"]
                if self.grievous:
                    ds_notes.append("Grievous Wounds (-40%)")
                heals_out.append(
                    HealEvent(
                        "1054 enduring-focus (Escudo de Doran)",
                        ds_raw_total,
                        ds_gained_total,
                        False,
                        self.grievous > 0,
                        Label.DERIVED,
                        tuple(ds_notes),
                    )
                )
            if wm_raw_total > 0:
                assert wm_start_t is not None and wm_end_t is not None
                wm_notes = [
                    f"OOC >=8 s regen {format_number(wm_start_t)}–{format_number(wm_end_t)} s"
                ]
                if self.grievous:
                    wm_notes.append("Grievous Wounds (-40%)")
                heals_out.append(
                    HealEvent(
                        "3083 warmogs-heart (Corazón de Warmog)",
                        wm_raw_total,
                        wm_gained_total,
                        False,
                        self.grievous > 0,
                        Label.DERIVED,
                        tuple(wm_notes),
                    )
                )
            if pot_raw_total > 0:
                assert pot_start_t is not None and pot_end_t is not None
                pt_notes = [f"regen {format_number(pot_start_t)}–{format_number(pot_end_t)} s"]
                if self.grievous:
                    pt_notes.append("Grievous Wounds (-40%)")
                heals_out.append(
                    HealEvent(
                        potion_source,
                        pot_raw_total,
                        pot_gained_total,
                        False,
                        self.grievous > 0,
                        Label.OFFICIAL,
                        tuple(pt_notes),
                    )
                )
            for h_src, (h_raw_tot, h_gained_tot, h_st, h_en, h_lbl, h_hsp) in ahot_totals.items():
                if h_raw_tot <= 0:
                    continue
                ah_notes = [f"regen {format_number(h_st)}–{format_number(h_en)} s"]
                if self.grievous:
                    ah_notes.append("Grievous Wounds (-40%)")
                heals_out.append(
                    HealEvent(
                        h_src,
                        h_raw_tot,
                        h_gained_tot,
                        h_hsp,
                        self.grievous > 0,
                        h_lbl,
                        tuple(ah_notes),
                    )
                )
            if bleed_total > 0:
                bleed_notes.append(
                    f"Death's Dance stagger bleed: {format_number(bleed_total)} true damage"
                )
            return heals_out, bleed_total, bleed_labels, bleed_notes, died_at

        def _apply_one_active_effect(
            slot: str,
            rank: int,
            eff: ActiveEffectSpec,
            at: Fraction,
            granted_out: list[ShieldEvent],
            labels_out: list[Label],
            notes_out: list[str],
        ) -> None:
            nonlocal health, current_max_health
            dur = self._active_duration(eff, rank)
            end_t = at + dur if (self.timeline and dur is not None) else None
            src = f"kit:{self.sheet.champion.id} {slot}.{eff.id} ({eff.name})"
            if eff.kind == "damage_dealt_heal":
                return
            if eff.kind == "heal" and not (
                eff.over_duration and self.timeline and dur is not None and dur > 0
            ):
                active_instant_heals.append((slot, src, eff, rank))
                return
            if eff.kind == "recent_damage_heal":
                pending_recent_heals.append((src, eff, rank))
                return
            if eff.kind == "recent_damage_shield":
                if eff.input_name is not None and eff.input_name in self.inputs:
                    ratio, eff_lbl = self._eval_active(
                        eff, rank, current_health=health, current_max_health=current_max_health
                    )
                    stored = max(Fraction(0), Fraction(str(self.inputs[eff.input_name])))
                    raw_sh = stored * ratio / 100
                    if eff.min_formula is not None:
                        mn, _ = self._eval_active_formula(
                            eff.min_formula,
                            rank,
                            eff.label,
                            current_health=health,
                            current_max_health=current_max_health,
                        )
                        raw_sh = max(raw_sh, mn)
                    if eff.max_formula is not None:
                        mx, _ = self._eval_active_formula(
                            eff.max_formula,
                            rank,
                            eff.label,
                            current_health=health,
                            current_max_health=current_max_health,
                        )
                        raw_sh = min(raw_sh, mx)
                    if raw_sh > 0:
                        rev_amp = self._revitalize_amp(health)
                        sh_amt = (
                            scale_shield(
                                raw_sh,
                                hsp=self.hsp if eff.uses_hsp else Fraction(0),
                                revitalize_amp=rev_amp if eff.uses_hsp else Fraction(0),
                            )
                            * self.self_shield_amp
                        )
                        sh_notes = [
                            f"{eff.name} (--input {eff.input_name}={format_number(stored)})"
                        ]
                        if self.shield_reaver_rate > 0:
                            sh_amt *= 1 - self.shield_reaver_rate
                        shields.append(_ActiveShield(src, sh_amt, eff.shield_type, end_t))
                        sh_lbl = weakest([eff_lbl, *self.self_amp_labels])
                        granted_out.append(
                            ShieldEvent(
                                src,
                                raw_sh,
                                sh_amt,
                                eff.shield_type,
                                dur,
                                sh_lbl,
                                tuple(sh_notes),
                            )
                        )
                        labels_out.append(sh_lbl)
                else:
                    pending_recent_shields.append((src, eff, rank, dur))
                return
            if eff.kind == "dodge_attacks":
                active_dodge_ends.append((end_t, src, eff.label))
                return
            if eff.kind == "spell_shield":
                spell_shield_slots.add(slot)
                active_spell_shields.append([end_t, False, src, eff.label, slot])
                return
            if eff.kind == "block_first_hit":
                active_first_hit_blocks.append([end_t, False, src, eff.label])
                return
            if eff.kind == "cleanse":
                qss_level = self.sheet.champion.id != "Milio"
                cleared = cleanse_cc(qss=qss_level, at=at)
                labels_out.append(eff.label)
                if cleared:
                    notes_out.append(f"{src}: cleansed {', '.join(cleared)}")
                else:
                    notes_out.append(f"{src}: cleansed active CC")
                return
            if eff.kind == "cc_immune":
                requires_magic_sh = self.sheet.champion.id == "Morgana" and slot == "E"
                cc_immune_windows.append((end_t, requires_magic_sh, src, eff.label))
                labels_out.append(eff.label)
                notes_out.append(
                    f"{src}: CC immune"
                    + (f" for {format_number(dur)} s" if dur is not None else "")
                )
                return
            val, eff_lbl = self._eval_active(
                eff, rank, current_health=health, current_max_health=current_max_health
            )
            if eff.kind == "invulnerable":
                if eff.mode == "undying":
                    active_undying.append((end_t, val, src, eff_lbl))
                else:
                    active_invuln_ends.append((end_t, src, eff_lbl))
                return
            if eff.kind == "stat_bonus" and eff.stat is not None:
                if eff.stat == "health":
                    gain = current_max_health * val / 100 if eff.mode == "percent" else val
                    current_max_health += gain
                    health += gain
                    if end_t is not None:
                        active_hp_buffs.append((end_t, gain))
                    labels_out.append(eff_lbl)
                    notes_out.append(
                        f"{src} (+{format_number(gain)} max HP"
                        + (f" for {format_number(dur)} s)" if dur is not None else ")")
                    )
                elif eff.stat in {"armor", "magic_resist"}:
                    active_resist_buffs.append((end_t, eff.stat, eff.mode, val, src, eff_lbl))
            elif eff.kind == "damage_taken_modifier":
                if eff.mode == "percent":
                    frac = val / 100 if val > 1 else val
                    active_percent_dr.append((end_t, eff.damage_type, frac, src, eff_lbl))
                else:
                    active_flat_dr.append(
                        (end_t, eff.damage_type, val, eff.damage_reduction_cap, src, eff_lbl)
                    )
            elif eff.kind == "shield":
                rev_amp = self._revitalize_amp(health)
                sh_amt = (
                    scale_shield(
                        val,
                        hsp=self.hsp if eff.uses_hsp else Fraction(0),
                        revitalize_amp=rev_amp if eff.uses_hsp else Fraction(0),
                    )
                    * self.self_shield_amp
                )
                sh_notes = [f"{eff.name} ({format_number(dur)} s)" if dur is not None else eff.name]
                if self.shield_reaver_rate > 0:
                    sh_amt *= 1 - self.shield_reaver_rate
                    sh_notes.append(
                        f"Shield Reaver (-{format_number(self.shield_reaver_rate * 100)}%)"
                    )
                shields.append(_ActiveShield(src, sh_amt, eff.shield_type, end_t))
                sh_label = weakest([eff_lbl, *self.self_amp_labels])
                granted_out.append(
                    ShieldEvent(src, val, sh_amt, eff.shield_type, dur, sh_label, tuple(sh_notes))
                )
                labels_out.append(sh_label)
            elif eff.kind == "heal":
                assert dur is not None and dur > 0
                active_hots.append((at + dur, val / dur, src, eff_lbl, eff.uses_hsp))
                labels_out.append(eff_lbl)
                notes_out.append(
                    f"{src} started {format_number(val)} heal over {format_number(dur)} s"
                )

        def process_hit(hit: IncomingHit, *, is_last: bool = False) -> DefenseStep:
            nonlocal health, current_max_health, shields, clock
            nonlocal bone_charges, bone_expires, bone_ready, bone_used_once
            nonlocal exhaust_used, exhaust_end, barrier_used, heal_used
            nonlocal active_cast_triggered, active_instant_heals
            nonlocal sw_end, sw_rate, sw_used_once
            nonlocal proto_heal_end, proto_heal_rate, proto_heal_source, proto_heal_label
            nonlocal proto_hp_end, proto_hp_gain, last_accrued
            nonlocal guardian_ready, guardian_used_once, guardian_window_hits
            nonlocal jaksho_start, jaksho_noted_no_timeline
            nonlocal dshield_end, dshield_rate, dshield_used_once, last_champ_hit
            nonlocal ga_ready, ga_used_once, ga_stasis_until
            nonlocal shield_reaver_until, shield_reaver_applied
            nonlocal potion_end, potion_rate, potion_used_once, potion_upfront_applied
            nonlocal dream_dr_armed, knights_vow_applied, stagger_noted_no_timeline
            nonlocal pending_recent_shields
            _sync_dynamic_debuffs(hit.time if (self.timeline and hit.time is not None) else clock)
            if hit.wait is not None:
                if not self.timeline:
                    raise RotationError(f"wait step {hit.source!r} requires --timeline")
                h_before = health
                s_before = self._shield_total(shields)
                target_clock = clock + hit.wait
                sw_heals, bleed_dmg, bleed_labels, bleed_notes, died_at = accrue_continuous(
                    target_clock
                )
                clock = died_at if died_at is not None else target_clock
                shields = self._expire_shields(shields, clock)
                wait_labels: list[Label] = []
                if sw_heals:
                    wait_labels.extend(h.label for h in sw_heals)
                if bleed_labels:
                    wait_labels.extend(bleed_labels)
                steps.append(
                    DefenseStep(
                        len(steps) + 1,
                        hit.source,
                        "bleed" if died_at is not None else "wait",
                        DamageType.TRUE if bleed_dmg > 0 else None,
                        clock,
                        bleed_dmg,
                        Fraction(0),
                        bleed_dmg,
                        Fraction(0),
                        bleed_dmg,
                        h_before,
                        health,
                        s_before,
                        self._shield_total(shields),
                        heals=tuple(sw_heals),
                        label=weakest(wait_labels) if wait_labels else Label.OFFICIAL,
                        notes=tuple(bleed_notes),
                    )
                )
                return steps[-1]

            if self.timeline and hit.time is not None:
                clock = max(clock, hit.time)
            shields = self._expire_shields(shields, clock)
            pre_h = health
            pre_s = self._shield_total(shields)
            sw_heals, bleed_dmg, bleed_labels, bleed_notes, died_at = accrue_continuous(clock)
            if bleed_dmg > 0:
                bleed_t = died_at if died_at is not None else clock
                steps.append(
                    DefenseStep(
                        len(steps) + 1,
                        f"Death's Dance bleed until {format_number(bleed_t)} s",
                        "bleed",
                        DamageType.TRUE,
                        bleed_t,
                        bleed_dmg,
                        Fraction(0),
                        bleed_dmg,
                        Fraction(0),
                        bleed_dmg,
                        pre_h,
                        health,
                        pre_s,
                        self._shield_total(shields),
                        heals=tuple(sw_heals),
                        label=weakest([*bleed_labels, *(h.label for h in sw_heals)]),
                        notes=tuple(bleed_notes),
                    )
                )
                sw_heals = []

            h_before = health
            s_before = self._shield_total(shields)
            step_notes: list[str] = []
            step_labels: list[Label] = [self.sheet["health"].label]
            granted: list[ShieldEvent] = []
            heals: list[HealEvent] = list(sw_heals)

            # Expire Force of Nature stacks/buff if window elapsed in timeline
            if self.timeline:
                for title, eff, _, _ in self.stacking_resist_effects:
                    if title in fon_active_until and clock >= fon_active_until[title]:
                        del fon_active_until[title]
                        fon_stacks[title] = 0
                    elif title in fon_last_hit:
                        win = Fraction(str((eff.get("stacks") or {}).get("window_seconds", 7)))
                        if clock - fon_last_hit[title] >= win:
                            fon_stacks[title] = 0

            # Stasis immunity from 3026 Guardian Angel Rebirth (4 s)
            if self.timeline and ga_stasis_until is not None and clock < ga_stasis_until:
                steps.append(
                    DefenseStep(
                        len(steps) + 1,
                        hit.source,
                        hit.kind,
                        hit.damage_type,
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
                        (),
                        tuple(heals),
                        Fraction(0),
                        Label.OFFICIAL,
                        ("3026 rebirth: invulnerable during 4 s stasis",),
                    )
                )
                return steps[-1]

            # 3109 Knight's Vow: redirect 14% of worthy ally's damage taken when >30% HP
            if (
                self.has_knights_vow
                and not knights_vow_applied
                and self.worthy_ally_taken > 0
                and health > current_max_health * Fraction(3, 10)
            ):
                knights_vow_applied = True
                redir = self.worthy_ally_taken * Fraction(14, 100)
                health = max(Fraction(0), health - redir)
                step_notes.append(
                    f"3109 sacrifice: redirected {format_number(redir)} true damage (14% of "
                    f"worthy ally {format_number(self.worthy_ally_taken)})"
                )
                step_labels.append(Label.OFFICIAL)

            # 8352 Time Warp Tonic: if potion is popped while already injured, heal 40% upfront
            if (
                self.potion_active_flag
                and potion_upfront > 0
                and not potion_upfront_applied
                and health > 0
                and health < current_max_health
            ):
                potion_upfront_applied = True
                amt = (
                    scale_healing(
                        potion_upfront,
                        hsp=Fraction(0),
                        revitalize_amp=Fraction(0),
                        grievous=self.grievous,
                        uses_hsp=False,
                    )
                    * self.self_heal_amp
                )
                missing = max(Fraction(0), current_max_health - health)
                gained = min(amt, missing)
                health += gained
                heals.append(
                    HealEvent(
                        f"{potion_source} (Time Warp Tonic instant)",
                        potion_upfront,
                        gained,
                        False,
                        self.grievous > 0,
                        self.rune_base,
                        ("8352 Time Warp Tonic 40% upfront heal",),
                    )
                )

            # 0. Spell Shield (3102 Banshee's, 3814 Edge of Night, 4632 Verdant Barrier)
            spell_blocked = False
            if hit.kind == "ability" and hit.amount > 0 and health > 0:
                for title, eff, eff_label in self.spell_shields:
                    can_block = (
                        (title not in spell_shield_used)
                        if not self.timeline
                        else (clock >= spell_shield_ready.get(title, Fraction(0)))
                    )
                    if can_block:
                        spell_shield_used.add(title)
                        if self.timeline and eff.get("cooldown_seconds"):
                            spell_shield_ready[title] = clock + scale_item_cooldown(
                                Fraction(str(eff["cooldown_seconds"])), self.item_haste
                            )
                        spell_blocked = True
                        step_labels.append(eff_label)
                        step_notes.append(f"{title} blocked incoming ability")
                        break

            # 0b. Defender active ability casts (Q/W/E/R shields, heals, DR, resist/HP steroids)
            if self.defender_active_effects and not active_cast_triggered and health > 0:
                active_cast_triggered = True
                for slot, rank, eff in self.defender_active_effects:
                    _apply_one_active_effect(
                        slot, rank, eff, clock, granted, step_labels, step_notes
                    )

            # 0c. Active defender hit negations (invulnerable, dodge, spell shield, block first hit)
            if not spell_blocked and hit.amount > 0 and health > 0:
                for end_t, src, eff_lbl in active_invuln_ends:
                    if end_t is None or clock <= end_t:
                        spell_blocked = True
                        step_labels.append(eff_lbl)
                        step_notes.append(f"{src} invulnerable (0 damage)")
                        break
            if (
                not spell_blocked
                and hit.kind in {"attack", "crit"}
                and hit.amount > 0
                and health > 0
            ):
                for end_t, src, eff_lbl in active_dodge_ends:
                    if end_t is None or clock <= end_t:
                        spell_blocked = True
                        step_labels.append(eff_lbl)
                        step_notes.append(f"{src} dodged basic attack")
                        break
            if not spell_blocked and hit.kind == "ability" and hit.amount > 0 and health > 0:
                for entry in active_spell_shields:
                    end_t, consumed, src, eff_lbl, sh_slot = entry
                    if not consumed and (end_t is None or clock <= end_t):
                        entry[1] = True
                        spell_blocked = True
                        spell_shield_blocked_slots.add(sh_slot)
                        step_labels.append(eff_lbl)
                        step_notes.append(f"{src} blocked incoming ability")
                        break
            if not spell_blocked and hit.amount > 0 and health > 0:
                for entry in active_first_hit_blocks:
                    end_t, consumed, src, eff_lbl = entry
                    if not consumed and (end_t is None or clock <= end_t):
                        entry[1] = True
                        spell_blocked = True
                        step_labels.append(eff_lbl)
                        step_notes.append(f"{src} blocked first hit")
                        break

            cur_armor, cur_mr, res_labels, res_notes = effective_resists(clock)
            if spell_blocked:
                incoming = Fraction(0)
            elif hit.already_mitigated:
                incoming = hit.amount
                step_labels.append(hit.label)
                if (
                    not hit.resistances_already_live
                    and hit.damage_type is DamageType.PHYSICAL
                    and cur_armor > self.armor
                    and self.armor >= 0
                ):
                    incoming = incoming * (100 + self.armor) / (100 + cur_armor)
                    step_labels.extend([*res_labels, Label.PENDING])
                    step_notes.extend(
                        [
                            *res_notes,
                            "pre-mitigated enemy hit rescaled for dynamic armor "
                            "without enemy penetration",
                        ]
                    )
                elif (
                    not hit.resistances_already_live
                    and hit.damage_type is DamageType.MAGIC
                    and cur_mr > self.magic_resist
                    and self.magic_resist >= 0
                ):
                    incoming = incoming * (100 + self.magic_resist) / (100 + cur_mr)
                    step_labels.extend([*res_labels, Label.PENDING])
                    step_notes.extend(
                        [
                            *res_notes,
                            "pre-mitigated enemy hit rescaled for dynamic MR "
                            "without enemy penetration",
                        ]
                    )
            else:
                incoming, mit_labels, mit_notes = self._mitigate_manual(hit, cur_armor, cur_mr)
                step_labels.extend([*mit_labels, *res_labels])
                step_notes.extend([*mit_notes, *res_notes])

            # 8351 Glacial Augment ally freeze zone (-15% incoming physical & magic damage for 3 s)
            if (
                self.glacial_ally
                and incoming > 0
                and health > 0
                and hit.damage_type in {DamageType.PHYSICAL, DamageType.MAGIC}
                and (not self.timeline or clock < 3)
            ):
                incoming *= Fraction(85, 100)
                step_labels.append(self.rune_base)
                step_notes.append("rune:8351 GlacialAugment (-15% enemy damage vs allies)")

            # SummonerExhaust (-35% incoming physical & magic damage for 3 s; never reduces true)
            if (
                self.summoner_exhaust is not None
                and incoming > 0
                and health > 0
                and hit.damage_type in {DamageType.PHYSICAL, DamageType.MAGIC}
            ):
                ex_dr, ex_slow, ex_dur = exhaust_values(self.summoner_exhaust)
                if not exhaust_used:
                    exhaust_used = True
                    if self.timeline:
                        exhaust_end = clock + ex_dur
                if not self.timeline or (exhaust_end is not None and clock < exhaust_end):
                    incoming *= 1 - ex_dr
                    step_labels.append(self.summoner_label)
                    step_notes.append(
                        f"summoner:{self.summoner_exhaust.id} ({self.summoner_exhaust.name} "
                        f"-{format_number(ex_dr * 100)}% {hit.damage_type.value}, "
                        f"-{format_number(ex_slow * 100)}% slow for {format_number(ex_dur)} s)"
                    )

            # Defender active ability percent damage reduction (e.g. Alistar R, Garen W, Yi W)
            if active_percent_dr and incoming > 0 and health > 0 and hit.damage_type is not None:
                for end_t, dt_filter, frac, src, lbl in active_percent_dr:
                    if end_t is not None and clock >= end_t:
                        continue
                    if dt_filter is not None and hit.damage_type is not dt_filter:
                        continue
                    if hit.damage_type is DamageType.TRUE and dt_filter is None:
                        continue
                    incoming *= 1 - frac
                    step_labels.append(lbl)
                    step_notes.append(
                        f"{src} (-{format_number(frac * 100)}% {hit.damage_type.value})"
                    )

            # Champion passive percent damage-taken modifiers (e.g. Kassadin -10%, Malzahar -90%)
            if incoming > 0 and health > 0 and hit.damage_type is not None:
                for p_dr in self.passive_dr_specs:
                    if p_dr.mode != "percent":
                        continue
                    if p_dr.damage_type is not None and hit.damage_type is not p_dr.damage_type:
                        continue
                    if hit.damage_type is DamageType.TRUE and p_dr.damage_type is None:
                        continue
                    p_cd = _effect_cooldown(p_dr, self.sheet.level)
                    if p_cd is not None:
                        can_dr = (
                            (p_dr.id not in passive_dr_used)
                            if not self.timeline
                            else (clock >= passive_dr_ready.get(p_dr.id, Fraction(0)))
                        )
                        if not can_dr:
                            continue
                        passive_dr_used.add(p_dr.id)
                        if self.timeline:
                            passive_dr_ready[p_dr.id] = clock + p_cd
                    pct_res = evaluate_formula(
                        p_dr.formula, self.stats_env, level=self.sheet.level, ops=ABILITY_OPS
                    )
                    assert pct_res.exact is not None
                    frac = pct_res.exact / 100 if pct_res.exact > 1 else pct_res.exact
                    incoming *= 1 - frac
                    step_labels.append(p_dr.label)
                    step_notes.append(
                        f"passive P {p_dr.name} (-{format_number(frac * 100)}% "
                        f"{hit.damage_type.value})"
                    )

            # Timed percent damage reduction (e.g. 3869 Celestial Opposition -35%/-25% for 2 s)
            if incoming > 0 and health > 0 and hit.damage_type is not None:
                for title, eff, comp, eff_label in self.timed_taken_modifiers:
                    allowed = comp.get("damage_types")
                    if allowed is not None and hit.damage_type.value not in allowed:
                        continue
                    is_active = (
                        (title in timed_dr_end and clock < timed_dr_end[title])
                        if self.timeline
                        else (title in timed_dr_used)
                    )
                    if not is_active:
                        can_open = (
                            (title not in timed_dr_used)
                            if not self.timeline
                            else (clock >= timed_dr_ready.get(title, Fraction(0)))
                        )
                        if can_open:
                            timed_dr_used.add(title)
                            is_active = True
                            if self.timeline:
                                dur = Fraction(str(eff["duration_seconds"]))
                                timed_dr_end[title] = clock + dur
                                if eff.get("cooldown_seconds"):
                                    timed_dr_ready[title] = clock + scale_item_cooldown(
                                        Fraction(str(eff["cooldown_seconds"])), self.item_haste
                                    )
                    if is_active:
                        pct = evaluate_formula(
                            comp.get("formula"),
                            self.stats_env,
                            holder_range=self.defender_range,
                            level=self.sheet.level,
                        ).exact
                        assert pct is not None
                        incoming *= 1 + pct / 100
                        step_labels.append(eff_label)
                        step_notes.append(f"{title} {format_number(pct)}%")

            # Flat damage reduction (MEC-08): scenario flat, champion passives (Fizz), Bone Plating
            flat_red = Fraction(0)
            if self.flat_input > 0 and incoming > 0:
                applied = min(incoming, self.flat_input)
                flat_red += applied
                step_notes.append(f"flat reduction -{format_number(applied)} (scenario)")

            if incoming - flat_red > 0 and hit.damage_type is not DamageType.TRUE:
                for p_dr in self.passive_dr_specs:
                    if p_dr.mode != "flat":
                        continue
                    if p_dr.damage_type is not None and hit.damage_type is not p_dr.damage_type:
                        continue
                    raw_res = evaluate_formula(
                        p_dr.formula, self.stats_env, level=self.sheet.level, ops=ABILITY_OPS
                    )
                    assert raw_res.exact is not None
                    raw_val = abs(raw_res.exact)
                    if p_dr.damage_reduction_cap is not None:
                        raw_val = min(raw_val, (incoming - flat_red) * p_dr.damage_reduction_cap)
                    applied = min(incoming - flat_red, raw_val)
                    if applied > 0:
                        flat_red += applied
                        step_labels.append(p_dr.label)
                        step_notes.append(f"passive P {p_dr.name} (-{format_number(applied)})")

            if incoming - flat_red > 0:
                for title, eff, comp, eff_label in self.flat_taken_modifiers:
                    src = comp.get("source")
                    if src == "attack" and hit.kind not in {"attack", "crit"}:
                        continue
                    raw_val = abs(
                        evaluate_formula(
                            comp.get("formula"),
                            self.stats_env,
                            holder_range=self.defender_range,
                            level=self.sheet.level,
                        ).exact
                    )
                    cap_amt = incoming
                    for lim in eff.get("limits") or ():
                        if lim.get("kind") == "cap" and lim.get("unit") == "percent":
                            cap_amt = min(cap_amt, incoming * Fraction(str(lim["value"])) / 100)
                    applied = min(incoming - flat_red, raw_val, cap_amt)
                    if applied > 0:
                        flat_red += applied
                        step_labels.append(eff_label)
                        step_notes.append(f"{title} -{format_number(applied)}")

            # 3870 Dream Maker blue bubble: flat attack damage reduction (50 L1-6, +12/lvl L7+)
            if dream_dr_armed and hit.kind in {"attack", "crit"} and incoming - flat_red > 0:
                dream_dr_armed = False
                lvl = self.sheet.level
                dm_block = Fraction(50) if lvl < 7 else Fraction(50 + 12 * (lvl - 6))
                applied = min(incoming - flat_red, dm_block)
                flat_red += applied
                step_labels.append(Label.DERIVED)
                step_notes.append(f"3870 dream-maker (blue bubble) -{format_number(applied)}")

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

            # Defender active ability flat damage reduction (e.g. Leona W Eclipse)
            if active_flat_dr and incoming - flat_red > 0 and hit.damage_type is not None:
                for end_t, dt_filter, flat_val, dr_cap, src, lbl in active_flat_dr:
                    if end_t is not None and clock >= end_t:
                        continue
                    if dt_filter is not None and hit.damage_type is not dt_filter:
                        continue
                    if hit.damage_type is DamageType.TRUE and dt_filter is None:
                        continue
                    cap_amt = incoming * dr_cap if dr_cap is not None else incoming
                    applied = min(incoming - flat_red, flat_val, cap_amt)
                    if applied > 0:
                        flat_red += applied
                        step_labels.append(lbl)
                        step_notes.append(f"{src} (-{format_number(applied)} flat)")

            dmg_after_flat = max(Fraction(0), incoming - flat_red)
            bypass = hit.kind == "execute"
            assert hit.damage_type is not None

            # Damage stagger (6333 Death's Dance Ignore Pain): defer 30%/10% as 3 s true bleed
            if self.stagger_effects and dmg_after_flat > 0 and health > 0 and not bypass:
                for title, _, comp, eff_label in self.stagger_effects:
                    allowed = comp.get("damage_types")
                    if allowed is not None and hit.damage_type.value not in allowed:
                        continue
                    if not self.timeline:
                        if not stagger_noted_no_timeline:
                            stagger_noted_no_timeline = True
                            self.notes.append(
                                f"{title}: defers damage over "
                                f"{format_number(Fraction(str(comp['duration_seconds'])))} s; "
                                "requires --timeline"
                            )
                            self.weakened = True
                        continue
                    defer_pct = evaluate_formula(
                        comp.get("formula"),
                        self.stats_env,
                        holder_range=self.defender_range,
                        level=self.sheet.level,
                    ).exact
                    assert defer_pct is not None
                    dur = Fraction(str(comp["duration_seconds"]))
                    deferred = dmg_after_flat * defer_pct / 100
                    dmg_after_flat -= deferred
                    stagger_bleeds.append(
                        _StaggerBleed(title, clock + dur, deferred / dur, eff_label)
                    )
                    step_labels.append(eff_label)
                    step_notes.append(
                        f"{title} deferred {format_number(deferred)} ({format_number(defer_pct)}%) "
                        f"over {format_number(dur)} s"
                    )

            # 6695 Serpent's Fang (Shield Reaver): shred existing & new shields for 3 s
            sr_active_now = False
            if self.shield_reaver_rate > 0 and dmg_after_flat > 0 and health > 0:
                sr_active_now = (
                    (shield_reaver_until is not None and clock < shield_reaver_until)
                    if self.timeline
                    else shield_reaver_applied
                )
                if not sr_active_now:
                    for active_s in shields:
                        active_s.remaining *= 1 - self.shield_reaver_rate
                    shield_reaver_applied = True
                    sr_active_now = True
                    if self.timeline:
                        shield_reaver_until = clock + 3
                    step_notes.append(
                        f"6695 shield-reaver: -{format_number(self.shield_reaver_rate * 100)}% "
                        "defender shields (3 s)"
                    )

            # Pre-damage shield & vitality Lifeline triggers
            if health > 0 and dmg_after_flat > 0 and not bypass:
                preview_shields = [
                    _ActiveShield(s.source, s.remaining, s.shield_type, s.expires_at)
                    for s in shields
                ]
                _, preview_hp_dmg = self._absorb_active(
                    dmg_after_flat, hit.damage_type, preview_shields
                )
                projected_hp = max(Fraction(0), health - preview_hp_dmg)

                # 1a. Lifeline shield items (Sterak, Shieldbow, Maw, Hexdrinker, Kaenic, boots)
                defender_range = self.defender_range
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
                    if threshold is None or projected_hp < threshold * current_max_health:
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
                        if sr_active_now and self.shield_reaver_rate > 0:
                            sh_amt *= 1 - self.shield_reaver_rate
                        dur = (
                            Fraction(str(eff["duration_seconds"]))
                            if eff.get("duration_seconds")
                            else None
                        )
                        cd = scale_item_cooldown(
                            Fraction(str(eff["cooldown_seconds"]))
                            if eff.get("cooldown_seconds")
                            else Fraction(90),
                            self.item_haste,
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
                        preview_shields = [
                            _ActiveShield(s.source, s.remaining, s.shield_type, s.expires_at)
                            for s in shields
                        ]
                        _, preview_hp_dmg = self._absorb_active(
                            dmg_after_flat, hit.damage_type, preview_shields
                        )
                        projected_hp = max(Fraction(0), health - preview_hp_dmg)

                # 1b. Lifeline vitality items (2525 Protoplasm Harness: temp max HP + HoT)
                for title, eff, eff_label in self.lifeline_vitality_effects:
                    can_proc = (
                        (title not in lifeline_used)
                        if not self.timeline
                        else (clock >= lifeline_ready.get(title, Fraction(0)))
                    )
                    if not can_proc:
                        continue
                    threshold = Fraction(30, 100)
                    for lim in eff.get("limits") or ():
                        if lim.get("kind") == "threshold":
                            threshold = Fraction(str(lim["value"])) / 100
                    if projected_hp < threshold * current_max_health:
                        dur = Fraction(str(eff.get("duration_seconds", 5)))
                        cd = Fraction(str(eff.get("cooldown_seconds", 90)))
                        lifeline_used.add(title)
                        if self.timeline:
                            lifeline_ready[title] = clock + cd
                        for comp in eff.get("components") or ():
                            ckind = comp.get("kind")
                            ev_val = evaluate_formula(
                                comp.get("formula"),
                                self.stats_env,
                                holder_range=self.defender_range,
                                level=self.sheet.level,
                            )
                            val = ev_val.exact
                            assert val is not None
                            dep_lbls = [
                                self.stat_origin[k][1]
                                for k in ev_val.dependencies
                                if k in self.stat_origin
                            ]
                            c_label = weakest([eff_label, *dep_lbls, *self.self_amp_labels])
                            if ckind == "stat_modifier" and comp.get("stat") == "health":
                                current_max_health += val
                                health += val
                                proto_hp_gain = val
                                proto_hp_end = clock + dur if self.timeline else None
                                step_labels.append(c_label)
                                step_notes.append(
                                    f"{title} granted +{format_number(val)} temporary max HP "
                                    f"for {format_number(dur)} s"
                                )
                            elif ckind == "healing":
                                if self.timeline:
                                    proto_heal_rate = val / dur
                                    proto_heal_end = clock + dur
                                    proto_heal_source = f"{title} ({eff.get('name', 'Lifeline')})"
                                    proto_heal_label = c_label
                                    step_notes.append(
                                        f"{title} started {format_number(val)} regen over "
                                        f"{format_number(dur)} s"
                                    )
                                else:
                                    amt = (
                                        scale_healing(
                                            val,
                                            hsp=Fraction(0),
                                            revitalize_amp=Fraction(0),
                                            grievous=self.grievous,
                                            uses_hsp=False,
                                        )
                                        * self.self_heal_amp
                                    )
                                    gained = min(amt, max(Fraction(0), current_max_health - health))
                                    health += gained
                                    heals.append(
                                        HealEvent(
                                            f"{title} ({eff.get('name', 'Lifeline')})",
                                            val,
                                            gained,
                                            False,
                                            self.grievous > 0,
                                            c_label,
                                            (
                                                f"full {format_number(dur)} s regen without "
                                                "--timeline",
                                            ),
                                        )
                                    )
                        projected_hp = max(Fraction(0), health - preview_hp_dmg)

                # 1b. Champion passive defensive shields (Malphite, Blitzcrank, Yasuo, Rakan, etc.)
                for p_sh in self.passive_shield_specs:
                    if p_sh.trigger not in {"on_taking_damage", "below_hp_percent"}:
                        continue
                    can_sh = (
                        (p_sh.id not in passive_shield_used)
                        if not self.timeline
                        else (clock >= passive_shield_ready.get(p_sh.id, Fraction(0)))
                    )
                    if not can_sh:
                        continue
                    fires = p_sh.trigger == "on_taking_damage"
                    if p_sh.trigger == "below_hp_percent" and p_sh.threshold_hp_percent is not None:
                        fires = projected_hp < current_max_health * p_sh.threshold_hp_percent
                    if not fires:
                        continue
                    passive_shield_used.add(p_sh.id)
                    cd = _effect_cooldown(p_sh, self.sheet.level)
                    if self.timeline and cd is not None:
                        passive_shield_ready[p_sh.id] = clock + cd
                    sh_res = evaluate_formula(
                        p_sh.formula, self.stats_env, level=self.sheet.level, ops=ABILITY_OPS
                    )
                    assert sh_res.exact is not None
                    dep_lbls = [
                        self.stat_origin[k][1] for k in sh_res.dependencies if k in self.stat_origin
                    ]
                    sh_label = weakest([p_sh.label, *dep_lbls, *self.self_amp_labels])
                    rev_amp = self._revitalize_amp(health)
                    amt = (
                        scale_shield(sh_res.exact, hsp=self.hsp, revitalize_amp=rev_amp)
                        * self.self_shield_amp
                    )
                    sh_notes: list[str] = [f"passive P {p_sh.name}"]
                    if self.shield_reaver_rate > 0:
                        amt *= 1 - self.shield_reaver_rate
                        sh_notes.append(
                            f"Shield Reaver (-{format_number(self.shield_reaver_rate * 100)}%)"
                        )
                    dur = p_sh.duration_seconds
                    shields.append(
                        _ActiveShield(
                            f"passive P {p_sh.name}",
                            amt,
                            p_sh.shield_type,
                            clock + dur if (self.timeline and dur is not None) else None,
                        )
                    )
                    granted.append(
                        ShieldEvent(
                            f"kit:{self.sheet.champion.id} P {p_sh.id} ({p_sh.name})",
                            sh_res.exact,
                            amt,
                            p_sh.shield_type,
                            dur,
                            sh_label,
                            tuple(sh_notes),
                        )
                    )
                    step_labels.append(sh_label)
                    preview_shields = [
                        _ActiveShield(s.source, s.remaining, s.shield_type, s.expires_at)
                        for s in shields
                    ]
                    _, preview_hp_dmg = self._absorb_active(
                        dmg_after_flat, hit.damage_type, preview_shields
                    )
                    projected_hp = max(Fraction(0), health - preview_hp_dmg)

                # 1c. SummonerBarrier (100..460 normal shield for 2.5 s)
                if self.summoner_barrier is not None and not barrier_used:
                    barrier_used = True
                    sp_bar = self.summoner_barrier
                    raw_b = barrier_shield(sp_bar, self.sheet.level)
                    rev_amp = self._revitalize_amp(health)
                    b_amt = (
                        scale_shield(raw_b, hsp=self.hsp, revitalize_amp=rev_amp)
                        * self.self_shield_amp
                    )
                    b_notes: list[str] = [
                        f"{sp_bar.name} ({format_number(barrier_duration(sp_bar))} s)"
                    ]
                    if self.hsp:
                        b_notes.append(f"heal & shield power +{format_number(self.hsp * 100)}%")
                    if rev_amp:
                        b_notes.append(f"Revitalize <40% HP +{format_number(rev_amp * 100)}%")
                    if sr_active_now and self.shield_reaver_rate > 0:
                        b_amt *= 1 - self.shield_reaver_rate
                        b_notes.append(
                            f"Shield Reaver (-{format_number(self.shield_reaver_rate * 100)}%)"
                        )
                    b_dur = barrier_duration(sp_bar)
                    shields.append(
                        _ActiveShield(
                            f"summoner:{sp_bar.id} ({sp_bar.name})",
                            b_amt,
                            "normal",
                            clock + b_dur if self.timeline else None,
                        )
                    )
                    b_label = weakest([self.summoner_label, *self.self_amp_labels])
                    granted.append(
                        ShieldEvent(
                            f"summoner:{sp_bar.id} ({sp_bar.name})",
                            raw_b,
                            b_amt,
                            "normal",
                            b_dur,
                            b_label,
                            tuple(b_notes),
                        )
                    )
                    step_labels.append(b_label)
                    preview_shields = [
                        _ActiveShield(s.source, s.remaining, s.shield_type, s.expires_at)
                        for s in shields
                    ]
                    _, preview_hp_dmg = self._absorb_active(
                        dmg_after_flat, hit.damage_type, preview_shields
                    )
                    projected_hp = max(Fraction(0), health - preview_hp_dmg)

                # 1d. SummonerHeal proactive before hit when already missing HP
                if self.summoner_heal is not None and not heal_used and health < current_max_health:
                    heal_used = True
                    sp_heal = self.summoner_heal
                    raw_h = heal_amount(
                        sp_heal, self.sheet.level, debuffed=self.summoner_heal_debuffed
                    )
                    rev_amp = self._revitalize_amp(health)
                    h_amt = (
                        scale_healing(
                            raw_h,
                            hsp=self.hsp,
                            revitalize_amp=rev_amp,
                            grievous=self.grievous,
                            uses_hsp=True,
                        )
                        * self.self_heal_amp
                    )
                    gained = min(h_amt, max(Fraction(0), current_max_health - health))
                    health += gained
                    h_notes = [f"{sp_heal.name} (proactive)"]
                    if self.summoner_heal_debuffed:
                        h_notes.append("recent Heal debuff (-50%)")
                    if self.grievous > 0:
                        h_notes.append("Grievous Wounds (-40%)")
                    h_label = weakest([self.summoner_label, *self.self_amp_labels])
                    heals.append(
                        HealEvent(
                            f"summoner:{sp_heal.id} ({sp_heal.name})",
                            raw_h,
                            gained,
                            True,
                            self.grievous > 0,
                            h_label,
                            tuple(h_notes),
                        )
                    )
                    step_labels.append(h_label)
                    projected_hp = max(Fraction(0), health - preview_hp_dmg)

                # 1e. Defender active ability instant heals (proactive when already missing HP)
                if active_instant_heals and health < current_max_health:
                    remaining_instant: list[tuple[str, str, ActiveEffectSpec, int]] = []
                    for h_slot, src, eff, rank in active_instant_heals:
                        if (
                            eff.condition == "spell_blocked"
                            and h_slot in spell_shield_slots
                            and h_slot not in spell_shield_blocked_slots
                        ):
                            remaining_instant.append((h_slot, src, eff, rank))
                            continue
                        raw_h, h_lbl = self._eval_active(
                            eff, rank, current_health=health, current_max_health=current_max_health
                        )
                        if raw_h <= 0:
                            continue
                        uses_hsp = eff.uses_hsp
                        rev_amp = self._revitalize_amp(health)
                        h_amt = (
                            scale_healing(
                                raw_h,
                                hsp=self.hsp if uses_hsp else Fraction(0),
                                revitalize_amp=rev_amp if uses_hsp else Fraction(0),
                                grievous=self.grievous,
                                uses_hsp=uses_hsp,
                            )
                            * self.self_heal_amp
                        )
                        gained = min(h_amt, max(Fraction(0), current_max_health - health))
                        health += gained
                        h_notes = ["active ability heal (proactive)"]
                        if self.grievous > 0:
                            h_notes.append("Grievous Wounds (-40%)")
                        ev_lbl = weakest([h_lbl, *self.self_amp_labels])
                        heals.append(
                            HealEvent(
                                src,
                                raw_h,
                                gained,
                                uses_hsp,
                                self.grievous > 0,
                                ev_lbl,
                                tuple(h_notes),
                            )
                        )
                        step_labels.append(ev_lbl)
                    active_instant_heals = remaining_instant
                    projected_hp = max(Fraction(0), health - preview_hp_dmg)

                # 1f. Defender stored-damage shields with minimum floor before lethal/final hit
                if pending_recent_shields:
                    keep_pending_sh: list[tuple[str, ActiveEffectSpec, int, Fraction | None]] = []
                    for src, eff, rank, dur in pending_recent_shields:
                        if eff.min_formula is not None and (projected_hp == 0 or is_last):
                            ratio, eff_lbl = self._eval_active(
                                eff,
                                rank,
                                current_health=health,
                                current_max_health=current_max_health,
                            )
                            win = eff.window_seconds
                            stored = sum(
                                (
                                    d
                                    for t_h, d in recent_damage_history
                                    if (not self.timeline or win is None or clock - t_h <= win)
                                ),
                                start=Fraction(0),
                            )
                            raw_sh = stored * ratio / 100
                            mn, mn_lbl = self._eval_active_formula(
                                eff.min_formula,
                                rank,
                                eff.label,
                                current_health=health,
                                current_max_health=current_max_health,
                            )
                            raw_sh = max(raw_sh, mn)
                            if eff.max_formula is not None:
                                mx, _ = self._eval_active_formula(
                                    eff.max_formula,
                                    rank,
                                    eff.label,
                                    current_health=health,
                                    current_max_health=current_max_health,
                                )
                                raw_sh = min(raw_sh, mx)
                            rev_amp = self._revitalize_amp(health)
                            sh_amt = (
                                scale_shield(
                                    raw_sh,
                                    hsp=self.hsp if eff.uses_hsp else Fraction(0),
                                    revitalize_amp=rev_amp if eff.uses_hsp else Fraction(0),
                                )
                                * self.self_shield_amp
                            )
                            sh_notes = [
                                f"{eff.name} (stored={format_number(stored)}, "
                                f"min={format_number(mn)})"
                            ]
                            if self.shield_reaver_rate > 0:
                                sh_amt *= 1 - self.shield_reaver_rate
                            end_t = clock + dur if (self.timeline and dur is not None) else None
                            shields.append(_ActiveShield(src, sh_amt, eff.shield_type, end_t))
                            sh_lbl = weakest([eff_lbl, mn_lbl, *self.self_amp_labels])
                            granted.append(
                                ShieldEvent(
                                    src,
                                    raw_sh,
                                    sh_amt,
                                    eff.shield_type,
                                    dur,
                                    sh_lbl,
                                    tuple(sh_notes),
                                )
                            )
                            step_labels.append(sh_lbl)
                        else:
                            keep_pending_sh.append((src, eff, rank, dur))
                    pending_recent_shields = keep_pending_sh

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
                            if sr_active_now and self.shield_reaver_rate > 0:
                                g_amt *= 1 - self.shield_reaver_rate
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
            if active_undying and h_before > 0:
                floors = [
                    (flr, u_src, u_lbl)
                    for end_t, flr, u_src, u_lbl in active_undying
                    if end_t is None or clock <= end_t
                ]
                if floors:
                    min_floor, u_src, u_lbl = max(floors, key=lambda item: item[0])
                    if health < min_floor:
                        health = min(h_before, min_floor)
                        step_labels.append(u_lbl)
                        step_notes.append(f"{u_src} undying (HP floor {format_number(min_floor)})")
            if hp_dmg > 0:
                recent_damage_history.append((clock, hp_dmg))
            shields = self._expire_shields(shields, clock)

            # 3026 Guardian Angel (Rebirth): on lethal hit, 4 s stasis + revive with 50% base HP
            if self.has_guardian_angel and health == 0 and h_before > 0:
                can_ga = (clock >= ga_ready) if self.timeline else (not ga_used_once)
                if can_ga:
                    ga_used_once = True
                    stagger_bleeds.clear()
                    revive_hp = self.base_health * Fraction(1, 2)
                    health = min(current_max_health, revive_hp)
                    if self.timeline:
                        ga_stasis_until = clock + 4
                        ga_ready = clock + 4 + scale_item_cooldown(Fraction(300), self.item_haste)
                    step_labels.append(Label.OFFICIAL)
                    step_notes.append(
                        f"3026 rebirth: 4 s stasis, revived with {format_number(health)} HP "
                        "(50% base HP, 300 s CD)"
                    )

            # Track last champion hit for 3083 Warmog's Heart (8 s OOC) & 6657/3803 Eternity
            if incoming > 0 or dmg_after_flat > 0:
                last_champ_hit = clock
                if self.has_eternity and hit.amount > 0:
                    mana_gain = hit.amount * Fraction(10, 100)
                    step_notes.append(
                        f"eternity: restored {format_number(mana_gain)} mana "
                        "(10% pre-mitigation damage)"
                    )

            # 1054 Doran's Shield (Enduring Focus): 0..40 melee / 0..30 ranged over 8 s
            if self.has_dorans_shield and dmg_after_flat > 0 and health > 0:
                max_reg = Fraction(30) if self.defender_range == "ranged" else Fraction(40)
                if self.aoe_dot_flag:
                    max_reg *= Fraction(66, 100)
                missing_frac = (
                    max(Fraction(0), current_max_health - health) / current_max_health
                    if current_max_health > 0
                    else Fraction(0)
                )
                total_reg = max_reg * missing_frac
                if self.timeline:
                    dshield_rate = total_reg / Fraction(8)
                    dshield_end = clock + 8
                elif not dshield_used_once and total_reg > 0:
                    dshield_used_once = True
                    amt = (
                        scale_healing(
                            total_reg,
                            hsp=Fraction(0),
                            revitalize_amp=Fraction(0),
                            grievous=self.grievous,
                            uses_hsp=False,
                        )
                        * self.self_heal_amp
                    )
                    missing = max(Fraction(0), current_max_health - health)
                    gained = min(amt, missing)
                    health += gained
                    heals.append(
                        HealEvent(
                            "1054 enduring-focus (Escudo de Doran)",
                            total_reg,
                            gained,
                            False,
                            self.grievous > 0,
                            Label.DERIVED,
                            ("full 8 s regen without --timeline",),
                        )
                    )

            # SummonerHeal reactive after taking non-lethal damage from full HP
            if (
                self.summoner_heal is not None
                and not heal_used
                and health > 0
                and health < current_max_health
            ):
                heal_used = True
                sp_heal = self.summoner_heal
                raw_h = heal_amount(sp_heal, self.sheet.level, debuffed=self.summoner_heal_debuffed)
                rev_amp = self._revitalize_amp(health)
                h_amt = (
                    scale_healing(
                        raw_h,
                        hsp=self.hsp,
                        revitalize_amp=rev_amp,
                        grievous=self.grievous,
                        uses_hsp=True,
                    )
                    * self.self_heal_amp
                )
                gained = min(h_amt, max(Fraction(0), current_max_health - health))
                health += gained
                h_notes = [f"{sp_heal.name} (reactive)"]
                if self.summoner_heal_debuffed:
                    h_notes.append("recent Heal debuff (-50%)")
                if self.grievous > 0:
                    h_notes.append("Grievous Wounds (-40%)")
                h_label = weakest([self.summoner_label, *self.self_amp_labels])
                heals.append(
                    HealEvent(
                        f"summoner:{sp_heal.id} ({sp_heal.name})",
                        raw_h,
                        gained,
                        True,
                        self.grievous > 0,
                        h_label,
                        tuple(h_notes),
                    )
                )
                step_labels.append(h_label)

            # Defender active ability instant heals (reactive after taking non-lethal damage)
            if active_instant_heals and health > 0 and health < current_max_health:
                remaining_reactive: list[tuple[str, str, ActiveEffectSpec, int]] = []
                for h_slot, src, eff, rank in active_instant_heals:
                    if (
                        eff.condition == "spell_blocked"
                        and h_slot in spell_shield_slots
                        and h_slot not in spell_shield_blocked_slots
                    ):
                        remaining_reactive.append((h_slot, src, eff, rank))
                        continue
                    raw_h, h_lbl = self._eval_active(
                        eff, rank, current_health=health, current_max_health=current_max_health
                    )
                    if raw_h <= 0:
                        continue
                    uses_hsp = eff.uses_hsp
                    rev_amp = self._revitalize_amp(health)
                    h_amt = (
                        scale_healing(
                            raw_h,
                            hsp=self.hsp if uses_hsp else Fraction(0),
                            revitalize_amp=rev_amp if uses_hsp else Fraction(0),
                            grievous=self.grievous,
                            uses_hsp=uses_hsp,
                        )
                        * self.self_heal_amp
                    )
                    gained = min(h_amt, max(Fraction(0), current_max_health - health))
                    health += gained
                    h_notes = ["active ability heal (reactive)"]
                    if self.grievous > 0:
                        h_notes.append("Grievous Wounds (-40%)")
                    ev_lbl = weakest([h_lbl, *self.self_amp_labels])
                    heals.append(
                        HealEvent(
                            src,
                            raw_h,
                            gained,
                            uses_hsp,
                            self.grievous > 0,
                            ev_lbl,
                            tuple(h_notes),
                        )
                    )
                    step_labels.append(ev_lbl)
                active_instant_heals = remaining_reactive

            # Defender stored-damage reactive shields (Sett W, TahmKench E, Mordekaiser W)
            if pending_recent_shields and health > 0 and recent_damage_history:
                for src, eff, rank, dur in pending_recent_shields:
                    ratio, eff_lbl = self._eval_active(
                        eff, rank, current_health=health, current_max_health=current_max_health
                    )
                    win = eff.window_seconds
                    stored = sum(
                        (
                            d
                            for t_h, d in recent_damage_history
                            if (not self.timeline or win is None or clock - t_h <= win)
                        ),
                        start=Fraction(0),
                    )
                    raw_sh = stored * ratio / 100
                    extra_lbls: list[Label] = [eff_lbl]
                    if eff.min_formula is not None:
                        mn, mn_lbl = self._eval_active_formula(
                            eff.min_formula,
                            rank,
                            eff.label,
                            current_health=health,
                            current_max_health=current_max_health,
                        )
                        raw_sh = max(raw_sh, mn)
                        extra_lbls.append(mn_lbl)
                    if eff.max_formula is not None:
                        mx, mx_lbl = self._eval_active_formula(
                            eff.max_formula,
                            rank,
                            eff.label,
                            current_health=health,
                            current_max_health=current_max_health,
                        )
                        raw_sh = min(raw_sh, mx)
                        extra_lbls.append(mx_lbl)
                    if raw_sh <= 0:
                        continue
                    rev_amp = self._revitalize_amp(health)
                    sh_amt = (
                        scale_shield(
                            raw_sh,
                            hsp=self.hsp if eff.uses_hsp else Fraction(0),
                            revitalize_amp=rev_amp if eff.uses_hsp else Fraction(0),
                        )
                        * self.self_shield_amp
                    )
                    sh_notes = [
                        f"{eff.name} ({format_number(ratio)}% of {format_number(stored)} stored)"
                    ]
                    if self.shield_reaver_rate > 0:
                        sh_amt *= 1 - self.shield_reaver_rate
                    end_t = clock + dur if (self.timeline and dur is not None) else None
                    shields.append(_ActiveShield(src, sh_amt, eff.shield_type, end_t))
                    sh_lbl = weakest([*extra_lbls, *self.self_amp_labels])
                    granted.append(
                        ShieldEvent(
                            src,
                            raw_sh,
                            sh_amt,
                            eff.shield_type,
                            dur,
                            sh_lbl,
                            tuple(sh_notes),
                        )
                    )
                    step_labels.append(sh_lbl)
                pending_recent_shields.clear()

            # Defender stored-damage reactive heals (Rengar W, DrMundo W)
            if (
                pending_recent_heals
                and health > 0
                and health < current_max_health
                and recent_damage_history
            ):
                for src, eff, rank in pending_recent_heals:
                    ratio, h_lbl = self._eval_active(
                        eff, rank, current_health=health, current_max_health=current_max_health
                    )
                    win = eff.window_seconds
                    stored = sum(
                        (
                            d
                            for t_h, d in recent_damage_history
                            if (not self.timeline or win is None or clock - t_h <= win)
                        ),
                        start=Fraction(0),
                    )
                    raw_h = stored * ratio / 100
                    if eff.min_formula is not None:
                        mn, _ = self._eval_active_formula(
                            eff.min_formula,
                            rank,
                            eff.label,
                            current_health=health,
                            current_max_health=current_max_health,
                        )
                        raw_h = max(raw_h, mn)
                    if eff.max_formula is not None:
                        mx, _ = self._eval_active_formula(
                            eff.max_formula,
                            rank,
                            eff.label,
                            current_health=health,
                            current_max_health=current_max_health,
                        )
                        raw_h = min(raw_h, mx)
                    if raw_h <= 0:
                        continue
                    uses_hsp = eff.uses_hsp
                    rev_amp = self._revitalize_amp(health)
                    h_amt = (
                        scale_healing(
                            raw_h,
                            hsp=self.hsp if uses_hsp else Fraction(0),
                            revitalize_amp=rev_amp if uses_hsp else Fraction(0),
                            grievous=self.grievous,
                            uses_hsp=uses_hsp,
                        )
                        * self.self_heal_amp
                    )
                    gained = min(h_amt, max(Fraction(0), current_max_health - health))
                    health += gained
                    h_notes = [
                        f"{eff.name} ({format_number(ratio)}% of {format_number(stored)} recent)"
                    ]
                    if self.grievous > 0:
                        h_notes.append("Grievous Wounds (-40%)")
                    ev_lbl = weakest([h_lbl, *self.self_amp_labels])
                    heals.append(
                        HealEvent(
                            src,
                            raw_h,
                            gained,
                            uses_hsp,
                            self.grievous > 0,
                            ev_lbl,
                            tuple(h_notes),
                        )
                    )
                    step_labels.append(ev_lbl)
                pending_recent_heals.clear()

            # 8352 Time Warp Tonic immediate 40% potion restoration on first damage
            if (
                self.potion_active_flag
                and potion_upfront > 0
                and not potion_upfront_applied
                and health > 0
                and health < current_max_health
            ):
                potion_upfront_applied = True
                amt = (
                    scale_healing(
                        potion_upfront,
                        hsp=Fraction(0),
                        revitalize_amp=Fraction(0),
                        grievous=self.grievous,
                        uses_hsp=False,
                    )
                    * self.self_heal_amp
                )
                missing = max(Fraction(0), current_max_health - health)
                gained = min(amt, missing)
                health += gained
                heals.append(
                    HealEvent(
                        f"{potion_source} (Time Warp Tonic instant)",
                        potion_upfront,
                        gained,
                        False,
                        self.grievous > 0,
                        self.rune_base,
                        ("8352 Time Warp Tonic 40% upfront heal",),
                    )
                )

            # 2003 / 2031 Potion without timeline (single full HoT heal on first damage)
            if (
                not self.timeline
                and self.potion_active_flag
                and not potion_used_once
                and potion_rate > 0
                and health > 0
            ):
                potion_used_once = True
                base_pot = Fraction(120) if "2003" in self.item_ids else Fraction(100)
                raw_pot = base_pot - potion_upfront if potion_upfront_applied else base_pot
                amt = (
                    scale_healing(
                        raw_pot,
                        hsp=Fraction(0),
                        revitalize_amp=Fraction(0),
                        grievous=self.grievous,
                        uses_hsp=False,
                    )
                    * self.self_heal_amp
                )
                missing = max(Fraction(0), current_max_health - health)
                gained = min(amt, missing)
                health += gained
                heals.append(
                    HealEvent(
                        potion_source,
                        raw_pot,
                        gained,
                        False,
                        self.grievous > 0,
                        Label.OFFICIAL,
                        ("full potion heal without --timeline",),
                    )
                )

            # Start Jak'Sho combat ramp timer on first hit
            if self.combat_resist_ramps and (incoming > 0 or dmg_after_flat > 0):
                if self.timeline:
                    if jaksho_start is None:
                        jaksho_start = clock
                elif not jaksho_noted_no_timeline:
                    jaksho_noted_no_timeline = True
                    self.notes.append(
                        "6665 voidborn-resilience: activates after 5 s in combat "
                        "(requires --timeline)"
                    )
                    self.weakened = True

            # Stack Force of Nature on magic damage hits
            if incoming > 0 and health > 0 and hit.damage_type is not None:
                for title, eff, comp, _ in self.stacking_resist_effects:
                    allowed = comp.get("damage_types")
                    if allowed is not None and hit.damage_type.value not in allowed:
                        continue
                    req = int((eff.get("stacks") or {}).get("required", 8))
                    dur = Fraction(str(eff.get("duration_seconds", 7)))
                    prev = fon_stacks.get(title, 0)
                    new_count = min(req, prev + 1)
                    fon_stacks[title] = new_count
                    fon_last_hit[title] = clock
                    if new_count >= req:
                        if self.timeline:
                            fon_active_until[title] = clock + dur
                        if prev < req:
                            step_notes.append(f"{title} reached {req} stacks (activated)")

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
                missing = max(Fraction(0), current_max_health - health)
                if self.timeline:
                    sw_rate = (missing * pct) / secs
                    sw_end = clock + secs
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
                    len(steps) + 1,
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
            return steps[-1]

        def flush_tail() -> None:
            nonlocal health, current_max_health, shields, clock
            # Final continuous tail (bleeds, Second Wind, Protoplasm, Doran's, Potions) in timeline
            if self.timeline and health > 0:
                tail_ends = [b.end for b in stagger_bleeds]
                if sw_end is not None:
                    tail_ends.append(sw_end)
                if proto_heal_end is not None:
                    tail_ends.append(proto_heal_end)
                if proto_hp_end is not None:
                    tail_ends.append(proto_hp_end)
                if dshield_end is not None:
                    tail_ends.append(dshield_end)
                if potion_end is not None:
                    tail_ends.append(potion_end)
                tail_end = max(tail_ends, default=clock)
                if tail_end > clock:
                    _sync_dynamic_debuffs(tail_end)
                    h_before = health
                    s_before = self._shield_total(shields)
                    tail_heals, tail_bleed, tail_b_labels, tail_b_notes, died_at = (
                        accrue_continuous(tail_end)
                    )
                    clock = died_at if died_at is not None else tail_end
                    shields = self._expire_shields(shields, clock)
                    if tail_heals or tail_bleed > 0:
                        t_labels = [*tail_b_labels, *(h.label for h in tail_heals)]
                        t_kind = "bleed" if tail_bleed > 0 else "regen"
                        t_src = (
                            f"Death's Dance bleed until {format_number(clock)} s"
                            if tail_bleed > 0 and not tail_heals
                            else (
                                f"Second Wind regen until {format_number(clock)} s"
                                if tail_bleed == 0 and self.second_wind_rune is not None
                                else f"bleed & regen until {format_number(clock)} s"
                            )
                        )
                        steps.append(
                            DefenseStep(
                                len(steps) + 1,
                                t_src,
                                t_kind,
                                DamageType.TRUE if tail_bleed > 0 else None,
                                clock,
                                tail_bleed,
                                Fraction(0),
                                tail_bleed,
                                Fraction(0),
                                tail_bleed,
                                h_before,
                                health,
                                s_before,
                                self._shield_total(shields),
                                heals=tuple(tail_heals),
                                label=weakest(t_labels) if t_labels else Label.DERIVED,
                                notes=tuple(tail_b_notes),
                            )
                        )

        def snapshot_state() -> DefenseState:
            atk_locks = [c.end for c in cc_locks if c.kind in CC_BLOCKS_ATTACKS and c.end > clock]
            ab_locks = [c.end for c in cc_locks if c.kind in CC_BLOCKS_ABILITIES and c.end > clock]
            sup_locks = [c.end for c in cc_locks if c.kind == "suppression" and c.end > clock]
            bld_locks = [c.end for c in cc_locks if c.kind in CC_BLINDS_ATTACKS and c.end > clock]
            return DefenseState(
                health=health,
                max_health=current_max_health,
                shield=self._shield_total(shields),
                clock=clock,
                stasis_until=ga_stasis_until,
                grievous_active=bool(
                    base_grievous > 0
                    or (dynamic_grievous_until is not None and clock < dynamic_grievous_until)
                ),
                step_count=len(steps),
                attacks_locked_until=max(atk_locks) if atk_locks else None,
                abilities_locked_until=max(ab_locks) if ab_locks else None,
                suppressed_until=max(sup_locks) if sup_locks else None,
                blinded_until=max(bld_locks) if bld_locks else None,
            )

        def target_snapshot(at: Fraction) -> Target:
            cur_ar, cur_mr, r_lbls, _ = effective_resists(at)
            bonus_hp = max(Fraction(0), current_max_health - self.base_health)
            t_stats = {
                "max_health": current_max_health,
                "current_health": health,
                "bonus_health": bonus_hp,
            }
            t_lbl = weakest(
                [
                    self.sheet["armor"].label,
                    self.sheet["magic_resist"].label,
                    self.sheet["health"].label,
                    *r_lbls,
                ]
            )
            return Target(
                armor=cur_ar,
                magic_resist=cur_mr,
                stats=t_stats,
                label=t_lbl,
                description=f"{self.sheet.champion.name} (live duel state)",
                kind="champion",
                items=self.sheet.items,
                shield=self._shield_total(shields),
                shield_type="normal",
                runes=(),
                level=self.sheet.level,
            )

        def accrue_to(
            until: Fraction,
        ) -> tuple[list[HealEvent], Fraction, list[Label], list[str], Fraction | None]:
            nonlocal clock, shields
            _sync_dynamic_debuffs(until)
            heals_out, bleed_dmg, b_lbls, b_notes, died_at = accrue_continuous(until)
            clock = died_at if died_at is not None else max(clock, until)
            shields = self._expire_shields(shields, clock)
            return heals_out, bleed_dmg, b_lbls, b_notes, died_at

        def activate_ability_cast(
            slot: str, rank: int, case_id: str | None, at: Fraction
        ) -> tuple[list[ShieldEvent], list[HealEvent], list[Label], list[str]]:
            nonlocal health, shields, clock, active_instant_heals, pending_recent_shields
            if self.kit is None or health <= 0:
                return [], [], [], []
            clock = max(clock, at)
            _sync_dynamic_debuffs(clock)
            shields = self._expire_shields(shields, clock)
            ab = self.kit.ability(slot)
            matched = [e for e in ab.active_effects if e.applies_to_case(case_id)]
            granted_out: list[ShieldEvent] = []
            heals_out: list[HealEvent] = []
            labels_out: list[Label] = []
            notes_out: list[str] = []
            for eff in matched:
                if eff.kind == "recent_damage_shield" and recent_damage_history:
                    ratio, eff_lbl = self._eval_active(
                        eff, rank, current_health=health, current_max_health=current_max_health
                    )
                    win = eff.window_seconds
                    stored = sum(
                        (
                            d
                            for t_h, d in recent_damage_history
                            if (not self.timeline or win is None or clock - t_h <= win)
                        ),
                        start=Fraction(0),
                    )
                    raw_sh = stored * ratio / 100
                    if eff.min_formula is not None:
                        mn, _ = self._eval_active_formula(
                            eff.min_formula,
                            rank,
                            eff.label,
                            current_health=health,
                            current_max_health=current_max_health,
                        )
                        raw_sh = max(raw_sh, mn)
                    if eff.max_formula is not None:
                        mx, _ = self._eval_active_formula(
                            eff.max_formula,
                            rank,
                            eff.label,
                            current_health=health,
                            current_max_health=current_max_health,
                        )
                        raw_sh = min(raw_sh, mx)
                    if raw_sh > 0:
                        dur = self._active_duration(eff, rank)
                        end_t = clock + dur if (self.timeline and dur is not None) else None
                        rev_amp = self._revitalize_amp(health)
                        sh_amt = (
                            scale_shield(
                                raw_sh,
                                hsp=self.hsp if eff.uses_hsp else Fraction(0),
                                revitalize_amp=rev_amp if eff.uses_hsp else Fraction(0),
                            )
                            * self.self_shield_amp
                        )
                        if self.shield_reaver_rate > 0:
                            sh_amt *= 1 - self.shield_reaver_rate
                        src = f"kit:{self.sheet.champion.id} {slot}.{eff.id} ({eff.name})"
                        shields.append(_ActiveShield(src, sh_amt, eff.shield_type, end_t))
                        sh_lbl = weakest([eff_lbl, *self.self_amp_labels])
                        granted_out.append(
                            ShieldEvent(
                                src,
                                raw_sh,
                                sh_amt,
                                eff.shield_type,
                                dur,
                                sh_lbl,
                                (
                                    f"{eff.name} ({format_number(ratio)}% of "
                                    f"{format_number(stored)} stored)",
                                ),
                            )
                        )
                        labels_out.append(sh_lbl)
                    continue
                if eff.kind == "recent_damage_shield" and eff.min_formula is not None:
                    mn, mn_lbl = self._eval_active_formula(
                        eff.min_formula,
                        rank,
                        eff.label,
                        current_health=health,
                        current_max_health=current_max_health,
                    )
                    if mn > 0:
                        dur = self._active_duration(eff, rank)
                        end_t = clock + dur if (self.timeline and dur is not None) else None
                        rev_amp = self._revitalize_amp(health)
                        sh_amt = (
                            scale_shield(
                                mn,
                                hsp=self.hsp if eff.uses_hsp else Fraction(0),
                                revitalize_amp=rev_amp if eff.uses_hsp else Fraction(0),
                            )
                            * self.self_shield_amp
                        )
                        if self.shield_reaver_rate > 0:
                            sh_amt *= 1 - self.shield_reaver_rate
                        src = f"kit:{self.sheet.champion.id} {slot}.{eff.id} ({eff.name})"
                        shields.append(_ActiveShield(src, sh_amt, eff.shield_type, end_t))
                        sh_lbl = weakest([mn_lbl, *self.self_amp_labels])
                        granted_out.append(
                            ShieldEvent(
                                src,
                                mn,
                                sh_amt,
                                eff.shield_type,
                                dur,
                                sh_lbl,
                                (f"{eff.name} (minimum baseline)",),
                            )
                        )
                        labels_out.append(sh_lbl)
                    continue
                if eff.kind == "recent_damage_shield":
                    if eff.input_name is not None and eff.input_name in self.inputs:
                        _apply_one_active_effect(
                            slot, rank, eff, clock, granted_out, labels_out, notes_out
                        )
                    continue
                if eff.kind == "recent_damage_heal":
                    if recent_damage_history:
                        ratio, h_lbl = self._eval_active(
                            eff, rank, current_health=health, current_max_health=current_max_health
                        )
                        win = eff.window_seconds
                        stored = sum(
                            (
                                d
                                for t_h, d in recent_damage_history
                                if (not self.timeline or win is None or clock - t_h <= win)
                            ),
                            start=Fraction(0),
                        )
                        raw_h = stored * ratio / 100
                        if eff.min_formula is not None:
                            mn, _ = self._eval_active_formula(
                                eff.min_formula,
                                rank,
                                eff.label,
                                current_health=health,
                                current_max_health=current_max_health,
                            )
                            raw_h = max(raw_h, mn)
                        if eff.max_formula is not None:
                            mx, _ = self._eval_active_formula(
                                eff.max_formula,
                                rank,
                                eff.label,
                                current_health=health,
                                current_max_health=current_max_health,
                            )
                            raw_h = min(raw_h, mx)
                        if raw_h > 0 and health < current_max_health:
                            rev_amp = self._revitalize_amp(health)
                            h_amt = (
                                scale_healing(
                                    raw_h,
                                    hsp=self.hsp if eff.uses_hsp else Fraction(0),
                                    revitalize_amp=rev_amp if eff.uses_hsp else Fraction(0),
                                    grievous=self.grievous,
                                    uses_hsp=eff.uses_hsp,
                                )
                                * self.self_heal_amp
                            )
                            gained = min(h_amt, max(Fraction(0), current_max_health - health))
                            health += gained
                            src = f"kit:{self.sheet.champion.id} {slot}.{eff.id} ({eff.name})"
                            ev_lbl = weakest([h_lbl, *self.self_amp_labels])
                            heals_out.append(
                                HealEvent(
                                    src,
                                    raw_h,
                                    gained,
                                    eff.uses_hsp,
                                    self.grievous > 0,
                                    ev_lbl,
                                    (
                                        f"{eff.name} ({format_number(ratio)}% of "
                                        f"{format_number(stored)} recent)",
                                    ),
                                )
                            )
                            labels_out.append(ev_lbl)
                    continue
                _apply_one_active_effect(slot, rank, eff, clock, granted_out, labels_out, notes_out)
            # Fire immediate non-conditional instant heals; keep only spell_blocked heals waiting
            if active_instant_heals:
                still_waiting: list[tuple[str, str, ActiveEffectSpec, int]] = []
                for h_slot, src, eff, h_rank in active_instant_heals:
                    if (
                        eff.condition == "spell_blocked"
                        and h_slot in spell_shield_slots
                        and h_slot not in spell_shield_blocked_slots
                    ):
                        still_waiting.append((h_slot, src, eff, h_rank))
                        continue
                    if health >= current_max_health:
                        continue
                    raw_h, h_lbl = self._eval_active(
                        eff, h_rank, current_health=health, current_max_health=current_max_health
                    )
                    if raw_h <= 0:
                        continue
                    rev_amp = self._revitalize_amp(health)
                    h_amt = (
                        scale_healing(
                            raw_h,
                            hsp=self.hsp if eff.uses_hsp else Fraction(0),
                            revitalize_amp=rev_amp if eff.uses_hsp else Fraction(0),
                            grievous=self.grievous,
                            uses_hsp=eff.uses_hsp,
                        )
                        * self.self_heal_amp
                    )
                    gained = min(h_amt, max(Fraction(0), current_max_health - health))
                    health += gained
                    ev_lbl = weakest([h_lbl, *self.self_amp_labels])
                    heals_out.append(
                        HealEvent(
                            src,
                            raw_h,
                            gained,
                            eff.uses_hsp,
                            self.grievous > 0,
                            ev_lbl,
                            ("active ability heal",),
                        )
                    )
                    labels_out.append(ev_lbl)
                active_instant_heals = still_waiting
            return granted_out, heals_out, labels_out, notes_out

        def activate_summoner(
            sp: SummonerSpellSpec, at: Fraction
        ) -> tuple[list[ShieldEvent], list[HealEvent], list[Label], list[str]]:
            nonlocal health, shields, clock, dynamic_grievous_until
            if health <= 0:
                return [], [], [], []
            clock = max(clock, at)
            _sync_dynamic_debuffs(clock)
            granted_out: list[ShieldEvent] = []
            heals_out: list[HealEvent] = []
            labels_out: list[Label] = []
            notes_out: list[str] = []
            title = f"summoner:{sp.id} ({sp.name})"
            if sp.id == "SummonerBarrier":
                raw_b = barrier_shield(sp, self.sheet.level)
                dur_b = barrier_duration(sp)
                rev_amp = self._revitalize_amp(health)
                b_amt = (
                    scale_shield(raw_b, hsp=self.hsp, revitalize_amp=rev_amp) * self.self_shield_amp
                )
                if self.shield_reaver_rate > 0:
                    b_amt *= 1 - self.shield_reaver_rate
                end_t = clock + dur_b if self.timeline else None
                shields.append(_ActiveShield(title, b_amt, "normal", end_t))
                b_lbl = weakest([self.summoner_label, *self.self_amp_labels])
                granted_out.append(
                    ShieldEvent(title, raw_b, b_amt, "normal", dur_b, b_lbl, (sp.name,))
                )
                labels_out.append(b_lbl)
            elif sp.id == "SummonerHeal":
                raw_h = heal_amount(sp, self.sheet.level, debuffed=self.summoner_heal_debuffed)
                rev_amp = self._revitalize_amp(health)
                h_amt = (
                    scale_healing(
                        raw_h,
                        hsp=self.hsp,
                        revitalize_amp=rev_amp,
                        grievous=self.grievous,
                        uses_hsp=True,
                    )
                    * self.self_heal_amp
                )
                gained = min(h_amt, max(Fraction(0), current_max_health - health))
                health += gained
                h_lbl = weakest([self.summoner_label, *self.self_amp_labels])
                heals_out.append(
                    HealEvent(title, raw_h, gained, True, self.grievous > 0, h_lbl, (sp.name,))
                )
                labels_out.append(h_lbl)
            elif sp.id == "SummonerBoost":
                nonlocal cleanse_tenacity_until, cleanse_tenacity_val
                ten, dur_c = cleanse_tenacity(sp)
                cleared = cleanse_cc(qss=False, at=clock)
                cleanse_tenacity_val = max(cleanse_tenacity_val, ten)
                new_ten_end = clock + dur_c
                if cleanse_tenacity_until is None or new_ten_end > cleanse_tenacity_until:
                    cleanse_tenacity_until = new_ten_end
                cleared_txt = f" ({', '.join(cleared)})" if cleared else ""
                notes_out.append(
                    f"{title}: cleansed debuffs{cleared_txt} + {format_number(ten * 100)}% "
                    f"tenacity for {format_number(dur_c)} s"
                )
                labels_out.append(self.summoner_label)
            return granted_out, heals_out, labels_out, notes_out

        def apply_self_survival(
            in_heals: Sequence[HealEvent],
            in_shields: Sequence[ShieldEvent],
            at: Fraction,
        ) -> tuple[Fraction, Fraction, list[HealEvent], list[ShieldEvent]]:
            nonlocal health, shields, clock
            if health <= 0:
                return Fraction(0), Fraction(0), [], []
            clock = max(clock, at)
            _sync_dynamic_debuffs(clock)
            shields = self._expire_shields(shields, clock)
            healed_total = Fraction(0)
            shielded_total = Fraction(0)
            out_heals: list[HealEvent] = []
            out_shields: list[ShieldEvent] = []
            for h_ev in in_heals:
                if h_ev.raw <= 0:
                    continue
                rev_amp = self._revitalize_amp(health)
                h_amt = (
                    scale_healing(
                        h_ev.raw,
                        hsp=self.hsp if h_ev.uses_hsp else Fraction(0),
                        revitalize_amp=rev_amp if h_ev.uses_hsp else Fraction(0),
                        grievous=self.grievous,
                        uses_hsp=h_ev.uses_hsp,
                    )
                    * self.self_heal_amp
                )
                gained = min(h_amt, max(Fraction(0), current_max_health - health))
                health += gained
                healed_total += gained
                h_notes = list(h_ev.notes)
                if self.grievous > 0 and not any("Grievous" in n for n in h_notes):
                    h_notes.append("Grievous Wounds (-40%)")
                out_heals.append(
                    HealEvent(
                        h_ev.source,
                        h_ev.raw,
                        gained,
                        h_ev.uses_hsp,
                        self.grievous > 0,
                        weakest([h_ev.label, *self.self_amp_labels]),
                        tuple(h_notes),
                    )
                )
            for s_ev in in_shields:
                if s_ev.raw <= 0:
                    continue
                rev_amp = self._revitalize_amp(health)
                sh_amt = (
                    scale_shield(s_ev.raw, hsp=self.hsp, revitalize_amp=rev_amp)
                    * self.self_shield_amp
                )
                s_notes = list(s_ev.notes)
                if self.shield_reaver_rate > 0:
                    sh_amt *= 1 - self.shield_reaver_rate
                    s_notes.append(
                        f"Shield Reaver (-{format_number(self.shield_reaver_rate * 100)}%)"
                    )
                end_t = (
                    clock + s_ev.duration if (self.timeline and s_ev.duration is not None) else None
                )
                shields.append(_ActiveShield(s_ev.source, sh_amt, s_ev.shield_type, end_t))
                shielded_total += sh_amt
                out_shields.append(
                    ShieldEvent(
                        s_ev.source,
                        s_ev.raw,
                        sh_amt,
                        s_ev.shield_type,
                        s_ev.duration,
                        weakest([s_ev.label, *self.self_amp_labels]),
                        tuple(s_notes),
                    )
                )
            return healed_total, shielded_total, out_heals, out_shields

        def apply_health_cost(amount: Fraction) -> Fraction:
            nonlocal health
            if amount <= 0 or health <= 1:
                return Fraction(0)
            paid = min(amount, health - 1)
            health -= paid
            return paid

        def set_grievous_until(until: Fraction) -> None:
            nonlocal dynamic_grievous_until
            if dynamic_grievous_until is None or until > dynamic_grievous_until:
                dynamic_grievous_until = until

        def set_shield_reaver(rate: Fraction, until: Fraction) -> None:
            nonlocal dynamic_sr_rate, dynamic_sr_until
            if rate > 0:
                for sh in shields:
                    if sh.remaining > 0:
                        sh.remaining *= 1 - rate
                dynamic_sr_rate = max(dynamic_sr_rate, rate)
                if dynamic_sr_until is None or until > dynamic_sr_until:
                    dynamic_sr_until = until

        def cleanse_cc(*, qss: bool = False, at: Fraction) -> list[str]:
            nonlocal cc_locks
            cleared: list[str] = []
            kept: list[_CCLock] = []
            for lock in cc_locks:
                if lock.end <= at:
                    continue
                can_clear = lock.cleansable_by_qss if qss else lock.cleansable_by_cleanse
                if can_clear:
                    cleared.append(lock.kind)
                else:
                    kept.append(lock)
            cc_locks = kept
            return cleared

        def apply_cc(
            cc: CCEffectSpec,
            base_duration: Fraction,
            at: Fraction,
            *,
            blocked_by_spell_shield: bool = False,
        ) -> tuple[Fraction, list[HealEvent], list[Label], list[str]]:
            nonlocal health, clock, unflinching_cc_until, active_instant_heals
            if health <= 0 or base_duration <= 0:
                return Fraction(0), [], [], []
            clock = max(clock, at)
            if self.timeline and ga_stasis_until is not None and clock < ga_stasis_until:
                return Fraction(0), [], [Label.OFFICIAL], ["CC ignored during 4 s GA stasis"]
            if blocked_by_spell_shield:
                return Fraction(0), [], [cc.label], [f"{cc.name}: blocked by spell shield"]
            # Intercept zero-damage pure-CC spells with an unconsumed spell shield
            for ss_entry in active_spell_shields:
                ss_end, ss_used, ss_src, ss_lbl, ss_slot = ss_entry
                if not ss_used and (ss_end is None or clock <= ss_end):
                    ss_entry[1] = True
                    spell_shield_blocked_slots.add(ss_slot)
                    ss_heals: list[HealEvent] = []
                    ss_labels: list[Label] = [ss_lbl]
                    # Fire spell_blocked instant heal (e.g. Sivir E) immediately
                    if active_instant_heals:
                        remaining_heals: list[tuple[str, str, ActiveEffectSpec, int]] = []
                        for h_slot, h_src, h_eff, h_rank in active_instant_heals:
                            if h_slot == ss_slot and h_eff.condition == "spell_blocked":
                                raw_h, h_lbl = self._eval_active(
                                    h_eff,
                                    h_rank,
                                    current_health=health,
                                    current_max_health=current_max_health,
                                )
                                if raw_h > 0 and health < current_max_health:
                                    rev_amp = self._revitalize_amp(health)
                                    h_amt = (
                                        scale_healing(
                                            raw_h,
                                            hsp=self.hsp if h_eff.uses_hsp else Fraction(0),
                                            revitalize_amp=rev_amp
                                            if h_eff.uses_hsp
                                            else Fraction(0),
                                            grievous=self.grievous,
                                            uses_hsp=h_eff.uses_hsp,
                                        )
                                        * self.self_heal_amp
                                    )
                                    gained = min(
                                        h_amt, max(Fraction(0), current_max_health - health)
                                    )
                                    health += gained
                                    ev_lbl = weakest([h_lbl, *self.self_amp_labels])
                                    ss_heals.append(
                                        HealEvent(
                                            h_src,
                                            raw_h,
                                            gained,
                                            h_eff.uses_hsp,
                                            self.grievous > 0,
                                            ev_lbl,
                                            ("spell shield heal",),
                                        )
                                    )
                                    ss_labels.append(ev_lbl)
                            else:
                                remaining_heals.append((h_slot, h_src, h_eff, h_rank))
                        active_instant_heals = remaining_heals
                    return (
                        Fraction(0),
                        ss_heals,
                        ss_labels,
                        [f"{ss_src} blocked {cc.name} ({cc.kind})"],
                    )
            # Check active CC immunity (Olaf R, Fiora W Parry, Morgana E Black Shield)
            for imm_end, req_magic_sh, imm_src, imm_lbl in cc_immune_windows:
                if imm_end is not None and clock >= imm_end:
                    continue
                if req_magic_sh and not any(
                    sh.shield_type == "magic" and sh.remaining > 0 for sh in shields
                ):
                    continue
                return Fraction(0), [], [imm_lbl], [f"{imm_src} blocked {cc.name} ({cc.kind})"]

            eff_dur = base_duration
            out_labels: list[Label] = [cc.label]
            out_notes: list[str] = []
            if cc.tenacity_applies:
                base_ten = min(Fraction(1), max(Fraction(0), self.sheet["tenacity"].total()))
                if cleanse_tenacity_until is not None and clock < cleanse_tenacity_until:
                    eff_ten = 1 - (1 - base_ten) * (1 - cleanse_tenacity_val)
                    out_labels.append(self.summoner_label)
                else:
                    eff_ten = base_ten
                if eff_ten > 0:
                    reduced = base_duration * (1 - eff_ten)
                    eff_dur = min(base_duration, max(TENACITY_MIN_DURATION, reduced))
                    if base_ten > 0:
                        out_labels.append(self.sheet["tenacity"].label)
                    out_notes.append(
                        f"{cc.name} ({cc.kind}): {format_number(eff_dur)} s "
                        f"(base {format_number(base_duration)} s reduced by "
                        f"{format_number(eff_ten * 100)}% tenacity)"
                    )
                else:
                    out_notes.append(f"{cc.name} ({cc.kind}): {format_number(eff_dur)} s")
            else:
                out_notes.append(
                    f"{cc.name} ({cc.kind}): {format_number(eff_dur)} s (tenacity immune)"
                )

            end_at = clock + eff_dur
            cc_locks.append(
                _CCLock(
                    cc.kind,
                    end_at,
                    cc.name,
                    cc.cleansable_by_cleanse,
                    cc.cleansable_by_qss,
                    weakest(out_labels),
                )
            )
            new_unf = end_at + 2
            if unflinching_cc_until is None or new_unf > unflinching_cc_until:
                unflinching_cc_until = new_unf
            return eff_dur, [], out_labels, out_notes

        def next_event_time(after: Fraction, limit: Fraction) -> Fraction | None:
            candidates: list[Fraction] = []
            if ga_stasis_until is not None and after < ga_stasis_until <= limit:
                candidates.append(ga_stasis_until)
            for lock in cc_locks:
                if after < lock.end <= limit:
                    candidates.append(lock.end)
            for end_t, _ in active_hp_buffs:
                if after < end_t <= limit:
                    candidates.append(end_t)
            for end_t, *_ in active_hots:
                if after < end_t <= limit:
                    candidates.append(end_t)
            for b in stagger_bleeds:
                if after < b.end <= limit:
                    candidates.append(b.end)
            for sh in shields:
                if sh.expires_at is not None and after < sh.expires_at <= limit:
                    candidates.append(sh.expires_at)
            for end_t, *_ in active_undying:
                if end_t is not None and after < end_t <= limit:
                    candidates.append(end_t)
            for end_t, *_ in active_invuln_ends:
                if end_t is not None and after < end_t <= limit:
                    candidates.append(end_t)
            for end_t, *_ in active_dodge_ends:
                if end_t is not None and after < end_t <= limit:
                    candidates.append(end_t)
            return min(candidates) if candidates else None

        def outcome(enemy_description: str) -> DefenseOutcome:
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
                weakest(all_labels) if all_labels else self.sheet["health"].label,
                tuple(dict.fromkeys(self.notes)),
                self.timeline,
            )

        return DefenseSession(
            snapshot_state=snapshot_state,
            effective_resists=effective_resists,
            target_snapshot=target_snapshot,
            accrue_to=accrue_to,
            process_hit=process_hit,
            activate_ability_cast=activate_ability_cast,
            activate_summoner=activate_summoner,
            apply_self_survival=apply_self_survival,
            apply_health_cost=apply_health_cost,
            set_grievous_until=set_grievous_until,
            set_shield_reaver=set_shield_reaver,
            apply_cc=apply_cc,
            cleanse_cc=cleanse_cc,
            next_event_time=next_event_time,
            flush_tail=flush_tail,
            outcome=outcome,
        )

    def run(self, hits: Sequence[IncomingHit], enemy_description: str) -> DefenseOutcome:
        if not hits:
            raise RotationError("defense simulation needs at least one incoming hit")
        session = self.open_session()
        for idx, hit in enumerate(hits, start=1):
            session.process_hit(hit, is_last=(idx == len(hits)))
        session.flush_tail()
        return session.outcome(enemy_description)


def open_defense_session(
    defender_sheet: StatSheet,
    *,
    start_health: Fraction | None = None,
    start_shield: Fraction = Fraction(0),
    shield_type: str = "normal",
    runes: Sequence[int] = (),
    rune_data: RuneData | None = None,
    inputs: Mapping[str, Fraction] | None = None,
    timeline: bool = True,
    kit: Kit | None = None,
    summoners: Sequence[str] = (),
    summoner_data: SummonerSpellData | None = None,
    defender_casts: Sequence[str] = (),
    defender_ranks: Mapping[str, int] | None = None,
) -> DefenseSession:
    """Open an incremental defensive simulation session for coupled duel evaluation."""
    sim = _DefenseSimulator(
        defender_sheet,
        start_health=start_health,
        start_shield=start_shield,
        shield_type=shield_type,
        runes=runes,
        rune_data=rune_data,
        inputs=inputs or {},
        timeline=timeline,
        kit=kit,
        summoners=summoners,
        summoner_data=summoner_data,
        defender_casts=defender_casts,
        defender_ranks=defender_ranks,
    )
    return sim.open_session()


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
    kit: Kit | None = None,
    summoners: Sequence[str] = (),
    summoner_data: SummonerSpellData | None = None,
    defender_casts: Sequence[str] = (),
    defender_ranks: Mapping[str, int] | None = None,
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
        kit=kit,
        summoners=summoners,
        summoner_data=summoner_data,
        defender_casts=defender_casts,
        defender_ranks=defender_ranks,
    )
    return sim.run(hits, enemy_description)
