"""Coupled deterministic 1v1 duel simulator (exact Fraction discrete-event clock).

Both champions maintain coupled live ``RotationSession`` (offense) and
``DefenseSession`` (defense) state over a shared exact ``Fraction`` timeline.
No damage, mitigation, healing, shielding, or proc logic is re-implemented here:
``rotation.py`` owns offensive calculations and ``defense.py`` owns live HP,
shields, damage reduction, negations, and survival reactions.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

from .damage import DamageType, format_number
from .defense import DefenseSession, DefenseState, IncomingHit, open_defense_session
from .errors import RotationError
from .formula import ABILITY_OPS, FormulaError, evaluate_formula
from .kit import Kit, sheet_stats
from .resources import ResourceSummary
from .rotation import (
    CritBase,
    DuelStepResult,
    Part,
    RotationSession,
    Step,
    open_rotation_session,
)
from .runes import RuneData
from .stats import Label, StatSheet, weakest
from .summoners import SummonerSpellData, SummonerSpellSpec, exhaust_values
from .survival import HealEvent, ShieldEvent

DUEL_MODES = frozenset({"scripted_then_attack", "strict_scripted", "priority_loop"})
DUEL_TIE_BREAKS = frozenset({"simultaneous", "a_first", "b_first"})
DEFAULT_DUEL_MODE = "scripted_then_attack"
DEFAULT_DUEL_TIE_BREAK = "simultaneous"
DEFAULT_DUEL_MAX_DURATION = Fraction(30)
DEFAULT_PRIORITY_SLOTS: tuple[str, ...] = ("R", "Q", "W", "E")
_QSS_ITEM_IDS = frozenset({"3139", "3140", "6035"})
_MAX_DUEL_TICKS = 2000


@dataclass(frozen=True)
class DuelFighterSpec:
    """Complete immutable specification of one side of a 1v1 duel."""

    sheet: StatSheet
    kit: Kit
    ranks: Mapping[str, int]
    crit_base: CritBase | None = None
    steps: Sequence[Step] = ()
    priority_slots: Sequence[str] = DEFAULT_PRIORITY_SLOTS
    holder_range: str | None = None
    start_health: Fraction | None = None
    start_shield: Fraction = Fraction(0)
    shield_type: str = "normal"
    runes: Sequence[int] = ()
    rune_data: RuneData | None = None
    summoners: Sequence[str] = ()
    summoner_data: SummonerSpellData | None = None
    inputs: Mapping[str, Any] = field(default_factory=dict)
    start_resource: Fraction | None = None
    allow_insufficient_resource: bool = False
    apply_passives: bool = True
    ap_weight: Fraction | None = None


@dataclass(frozen=True)
class DuelEvent:
    """One chronological event emitted by the coupled duel simulation."""

    index: int
    time: Fraction
    actor: str  # "A" | "B" | "system"
    action: str
    damage_dealt: Fraction
    shield_absorbed: Fraction
    health_damage: Fraction
    healing_done: Fraction
    shield_granted: Fraction
    reactive_damage: Fraction
    a_health_after: Fraction
    a_shield_after: Fraction
    b_health_after: Fraction
    b_shield_after: Fraction
    label: Label
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class FighterDuelSummary:
    """End-of-duel totals and surviving state for one combatant."""

    side: str  # "A" | "B"
    champion_id: str
    champion_name: str
    level: int
    start_health: Fraction
    max_health: Fraction
    remaining_health: Fraction
    remaining_shield: Fraction
    damage_dealt: Fraction
    damage_taken: Fraction
    healing_done: Fraction
    shield_granted: Fraction
    shield_absorbed: Fraction
    actions_taken: int
    survived: bool
    resource: ResourceSummary | None = None


@dataclass(frozen=True)
class DuelOutcome:
    """Complete deterministic result of a 1v1 duel simulation."""

    patch: str
    mode: str
    tie_break: str
    max_duration: Fraction
    winner: str  # "A" | "B" | "draw_mutual_kill" | "draw_timeout"
    duration: Fraction
    fighter_a: FighterDuelSummary
    fighter_b: FighterDuelSummary
    events: tuple[DuelEvent, ...]
    label: Label
    notes: tuple[str, ...]


@dataclass
class _FighterRuntime:
    side: str
    spec: DuelFighterSpec
    defense: DefenseSession
    offense: RotationSession
    start_health: Fraction
    step_idx: int = 0
    pending_wait_target: Fraction | None = None
    exhausted_until: Fraction | None = None
    damage_dealt: Fraction = Fraction(0)
    damage_taken: Fraction = Fraction(0)
    healing_done: Fraction = Fraction(0)
    shield_granted: Fraction = Fraction(0)
    shield_absorbed: Fraction = Fraction(0)
    actions_taken: int = 0
    labels: list[Label] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    priority_parsed: tuple[tuple[str, str | None], ...] = ()


@dataclass
class _ActionPayload:
    actor: _FighterRuntime
    defender: _FighterRuntime
    step: Step
    is_scripted: bool
    pre_shields: list[ShieldEvent] = field(default_factory=list)
    pre_heals: list[HealEvent] = field(default_factory=list)
    pre_labels: list[Label] = field(default_factory=list)
    pre_notes: list[str] = field(default_factory=list)
    step_result: DuelStepResult | None = None


def _parse_priority_slots(
    spec: DuelFighterSpec,
) -> tuple[tuple[str, str | None], ...]:
    spell_by_slot = {sp.slot.upper(): sp for sp in spec.sheet.champion.spells}
    parsed: list[tuple[str, str | None]] = []
    seen: set[str] = set()
    for raw in spec.priority_slots:
        token = raw.strip()
        if not token:
            continue
        if "." in token:
            slot_raw, case_id = token.split(".", 1)
            slot = slot_raw.upper()
            case: str | None = case_id
        else:
            slot = token.upper()
            case = None
        if slot in seen or slot not in spec.ranks or slot not in spec.kit.abilities:
            continue
        ability = spec.kit.abilities[slot]
        if not ability.cases and not ability.active_effects:
            continue
        rank = spec.ranks[slot]
        if not 1 <= rank <= ability.max_rank:
            continue
        spell = spell_by_slot.get(slot)
        if spell is None or rank > len(spell.cooldowns) or spell.cooldowns[rank - 1] <= 0:
            continue
        if case is None and len(ability.cases) > 1:
            non_recast = [c for c in ability.cases if not c.recast]
            if not non_recast:
                continue
            case = non_recast[0].id
        seen.add(slot)
        parsed.append((slot, case))
    return tuple(parsed)


def _defense_inputs(raw_inputs: Mapping[str, Any]) -> dict[str, Fraction]:
    out: dict[str, Fraction] = {}
    for key, val in raw_inputs.items():
        try:
            out[key] = val if isinstance(val, Fraction) else Fraction(str(val))
        except ValueError, TypeError:
            continue
    return out


def _is_exhausted(fighter: _FighterRuntime, at: Fraction) -> bool:
    return fighter.exhausted_until is not None and at < fighter.exhausted_until


def _is_cleanse_ability(fighter: _FighterRuntime, slot: str, case_id: str | None) -> bool:
    ab = fighter.spec.kit.abilities.get(slot)
    if ab is None:
        return False
    return any(eff.kind == "cleanse" and eff.applies_to_case(case_id) for eff in ab.active_effects)


def _step_min_clock(
    fighter: _FighterRuntime, step: Step, st: DefenseState, clock: Fraction
) -> Fraction:
    """Earliest clock >= ``clock`` at which ``fighter`` is allowed to execute ``step``."""
    base = max(clock, st.stasis_until) if (st.stasis_until and st.stasis_until > clock) else clock
    if step.wait is not None:
        return base
    if step.item_id is not None:
        if step.item_id in _QSS_ITEM_IDS:
            return base
        if st.abilities_locked_until and st.abilities_locked_until > base:
            return st.abilities_locked_until
        return base
    if step.summoner_id is not None:
        # Summoners (including Cleanse, Barrier, Heal, Ignite, Exhaust) are blocked by suppression
        if st.suppressed_until and st.suppressed_until > base:
            return st.suppressed_until
        return base
    if step.slot is not None:
        if _is_cleanse_ability(fighter, step.slot, step.case):
            # Milio R cannot cleanse suppression; QSS-tier cleanses (Alistar R, GP W, Olaf R) can
            if (
                fighter.spec.sheet.champion.id == "Milio"
                and st.suppressed_until
                and st.suppressed_until > base
            ):
                return st.suppressed_until
            return base
        if st.abilities_locked_until and st.abilities_locked_until > base:
            return st.abilities_locked_until
        return base
    # Basic attack
    if st.attacks_locked_until and st.attacks_locked_until > base:
        return st.attacks_locked_until
    return base


def _next_action(
    fighter: _FighterRuntime,
    clock: Fraction,
    mode: str,
) -> tuple[Fraction, Step, bool] | None:
    """Return ``(scheduled_time, step, is_scripted)`` for ``fighter``, or ``None``."""
    st = fighter.defense.snapshot_state()
    if st.health <= 0:
        return None
    min_clock = (
        max(clock, st.stasis_until) if (st.stasis_until and st.stasis_until > clock) else clock
    )

    if fighter.step_idx < len(fighter.spec.steps):
        step = fighter.spec.steps[fighter.step_idx]
        if step.wait is not None:
            if fighter.pending_wait_target is None:
                fighter.pending_wait_target = min_clock + step.wait
            return max(min_clock, fighter.pending_wait_target), step, True
        allowed_at = _step_min_clock(fighter, step, st, clock)
        t_step = fighter.offense.peek_step_time(step, allowed_at, allow_wait_for_cd=True)
        return max(allowed_at, t_step), step, True

    if mode == "strict_scripted":
        return None

    atk_step = Step("attack")
    atk_min = _step_min_clock(fighter, atk_step, st, clock)
    t_atk = max(atk_min, fighter.offense.next_attack_time())
    if mode == "scripted_then_attack":
        return t_atk, atk_step, False

    # priority_loop: prefer ready & affordable priority abilities over attacks
    best_time = t_atk
    best_step = atk_step
    best_prio = len(fighter.priority_parsed) + 1
    for prio_idx, (slot, case_id) in enumerate(fighter.priority_parsed):
        text = f"{slot}.{case_id}" if case_id is not None else slot
        cand_step = Step(text, slot=slot, case=case_id)
        ab_min = _step_min_clock(fighter, cand_step, st, clock)
        t_ready = max(ab_min, fighter.offense.ability_ready_time(slot))
        if t_ready > best_time:
            continue
        if not fighter.offense.can_cast_slot(slot, case_id, t_ready):
            continue
        if t_ready < best_time or (t_ready == best_time and prio_idx < best_prio):
            best_time = t_ready
            best_prio = prio_idx
            best_step = cand_step
    return best_time, best_step, False


def _resolve_summoner_spec(fighter: _FighterRuntime, summoner_id: str) -> SummonerSpellSpec | None:
    if fighter.spec.summoner_data is None:
        return None
    try:
        return fighter.spec.summoner_data.resolve(summoner_id)
    except Exception:
        return None


def _deliver_parts(
    actor: _FighterRuntime,
    defender: _FighterRuntime,
    parts: Sequence[Part],
    step_label: str,
    step_crit: bool,
    at: Fraction,
    *,
    actor_blinded: bool = False,
) -> tuple[Fraction, Fraction, Fraction, list[HealEvent], Fraction, list[Label], list[str]]:
    """Deliver post-resistance ``parts`` into ``defender.defense`` and build scaled vamp heals."""
    total_dealt = Fraction(0)
    total_shield_abs = Fraction(0)
    total_hp_dmg = Fraction(0)
    total_reactive = Fraction(0)
    vamp_heals: list[HealEvent] = []
    labels: list[Label] = []
    notes: list[str] = []

    for part in parts:
        if part.primary_damage <= 0:
            continue
        if actor_blinded and part.kind in {"attack", "on_hit"}:
            notes.append(f"{actor.side} {step_label}: missed (blinded)")
            labels.append(part.label)
            continue
        hit_kind = "crit" if (part.kind == "attack" and step_crit) else part.kind
        hit = IncomingHit(
            hit_kind,
            part.damage_type,
            part.primary_damage,
            f"{actor.side} {step_label}: {part.source}",
            already_mitigated=True,
            resistances_already_live=True,
            time=at,
            crit=step_crit and part.kind == "attack",
            label=part.label,
        )
        d_step = defender.defense.process_hit(hit)
        actual_dmg = d_step.damage_after_flat
        total_dealt += actual_dmg
        total_shield_abs += d_step.shield_absorbed
        total_hp_dmg += d_step.health_damage
        total_reactive += d_step.reactive_damage
        defender.damage_taken += actual_dmg
        defender.shield_absorbed += d_step.shield_absorbed
        for sh_ev in d_step.shields_granted:
            defender.shield_granted += sh_ev.amount
            defender.offense.notify_shield_granted(sh_ev.amount, at)
        for h_ev in d_step.heals:
            defender.healing_done += h_ev.amount
        labels.append(d_step.label)
        notes.extend(d_step.notes)

        # Scale life steal & omnivamp by actual post-DR/post-negation damage landed
        vamp_rate = part.healing.life_steal + part.healing.omnivamp
        if vamp_rate > 0 and actual_dmg > 0:
            raw_vamp = actual_dmg * vamp_rate
            vamp_heals.append(
                HealEvent(
                    f"vamp ({part.source})",
                    raw_vamp,
                    raw_vamp,
                    False,
                    False,
                    part.healing.label,
                    part.healing.notes,
                )
            )

    actor.damage_dealt += total_dealt
    return (
        total_dealt,
        total_shield_abs,
        total_hp_dmg,
        vamp_heals,
        total_reactive,
        labels,
        notes,
    )


def _apply_reactive_reflect(
    actor: _FighterRuntime,
    defender: _FighterRuntime,
    reactive_damage: Fraction,
    at: Fraction,
) -> tuple[Fraction, list[Label], list[str]]:
    """Apply Thornmail reactive magic damage + 3 s GW back onto ``actor``."""
    if reactive_damage <= 0:
        return Fraction(0), [], []
    actor.defense.set_grievous_until(at + 3)
    hit = IncomingHit(
        "ability",
        DamageType.MAGIC,
        reactive_damage,
        f"{defender.side} Thornmail reflect",
        already_mitigated=False,
        time=at,
        label=Label.OFFICIAL,
    )
    r_step = actor.defense.process_hit(hit)
    actor.damage_taken += r_step.damage_after_flat
    actor.shield_absorbed += r_step.shield_absorbed
    defender.damage_dealt += r_step.damage_after_flat
    for sh_ev in r_step.shields_granted:
        actor.shield_granted += sh_ev.amount
        actor.offense.notify_shield_granted(sh_ev.amount, at)
    for h_ev in r_step.heals:
        actor.healing_done += h_ev.amount
    return r_step.damage_after_flat, [r_step.label], list(r_step.notes)


def _scale_damage_dealt_heals(
    heal_events: Sequence[HealEvent],
    parts: Sequence[Part],
    actual_total_dealt: Fraction,
) -> list[HealEvent]:
    """Scale ``damage_dealt_heal`` events when defender DR/negations reduced landed damage."""
    expected_total = sum((p.primary_damage for p in parts if p.primary_damage > 0), Fraction(0))
    ratio = (actual_total_dealt / expected_total) if expected_total > 0 else Fraction(1)
    out: list[HealEvent] = []
    for h_ev in heal_events:
        is_dd_heal = any(("post-mitigation damage" in n or "damage dealt" in n) for n in h_ev.notes)
        if is_dd_heal and ratio != 1:
            scaled_raw = h_ev.raw * ratio
            if scaled_raw <= 0:
                continue
            out.append(
                HealEvent(
                    h_ev.source,
                    scaled_raw,
                    scaled_raw,
                    h_ev.uses_hsp,
                    h_ev.grievous_applied,
                    h_ev.label,
                    h_ev.notes,
                )
            )
        else:
            out.append(h_ev)
    return out


def _phase1_activate_defensives(payload: _ActionPayload, at: Fraction) -> None:
    """Activate defensive active effects, defensive summoners, and Exhaust before strikes."""
    actor = payload.actor
    defender = payload.defender
    step = payload.step

    if step.item_id in _QSS_ITEM_IDS:
        cleared = actor.defense.cleanse_cc(qss=True, at=at)
        cleared_txt = f" ({', '.join(cleared)})" if cleared else ""
        payload.pre_notes.append(
            f"item:{step.item_id} Quicksilver: cleansed active CC{cleared_txt}"
        )
        payload.pre_labels.append(Label.OFFICIAL)
        return

    if step.slot is not None and step.slot in actor.spec.ranks:
        shs, hls, lbls, nts = actor.defense.activate_ability_cast(
            step.slot, actor.spec.ranks[step.slot], step.case, at
        )
        payload.pre_shields.extend(shs)
        payload.pre_heals.extend(hls)
        payload.pre_labels.extend(lbls)
        payload.pre_notes.extend(nts)
        for sh_ev in shs:
            actor.shield_granted += sh_ev.amount
            actor.offense.notify_shield_granted(sh_ev.amount, at)
        for h_ev in hls:
            actor.healing_done += h_ev.amount
    elif step.summoner_id is not None:
        sp = _resolve_summoner_spec(actor, step.summoner_id)
        if sp is not None:
            if sp.id in {"SummonerBarrier", "SummonerHeal", "SummonerBoost"}:
                shs, hls, lbls, nts = actor.defense.activate_summoner(sp, at)
                payload.pre_shields.extend(shs)
                payload.pre_heals.extend(hls)
                payload.pre_labels.extend(lbls)
                payload.pre_notes.extend(nts)
                for sh_ev in shs:
                    actor.shield_granted += sh_ev.amount
                    actor.offense.notify_shield_granted(sh_ev.amount, at)
                for h_ev in hls:
                    actor.healing_done += h_ev.amount
                if sp.id == "SummonerBoost":
                    actor.exhausted_until = None
            elif sp.id == "SummonerExhaust":
                _dmg_red, _slow, dur = exhaust_values(sp)
                until = at + dur
                if defender.exhausted_until is None or until > defender.exhausted_until:
                    defender.exhausted_until = until
                payload.pre_notes.append(
                    f"SummonerExhaust: reduced {defender.side} non-true damage by "
                    f"{format_number(_dmg_red * 100)}% for {format_number(dur)} s"
                )


def _phase2_compute_offense(payload: _ActionPayload, at: Fraction) -> None:
    """Sync live pre-strike context and evaluate ``RotationSession.step_one``."""
    actor = payload.actor
    defender = payload.defender
    a_state = actor.defense.snapshot_state()
    d_target = defender.defense.target_snapshot(at)
    actor.offense.sync_context(
        d_target,
        a_state.health,
        a_state.max_health,
        exhausted=_is_exhausted(actor, at),
    )
    payload.step_result = actor.offense.step_one(payload.step, at, defer_ability_survival=True)
    actor.actions_taken += 1
    if payload.is_scripted:
        actor.step_idx += 1


def _phase3_deliver_and_survive(
    payloads: Sequence[_ActionPayload],
    at: Fraction,
    events: list[DuelEvent],
    fighter_a: _FighterRuntime,
    fighter_b: _FighterRuntime,
) -> None:
    """Deliver all hits for the tick, apply reflects and debuffs, then apply self-survival."""
    delivery_results: list[
        tuple[
            _ActionPayload,
            Fraction,
            Fraction,
            Fraction,
            list[HealEvent],
            Fraction,
            list[Label],
            list[str],
        ]
    ] = []

    # 3a. Spend health costs & apply pre-hit shield shred (Serpent's Fang)
    for p in payloads:
        res = p.step_result
        assert res is not None
        if res.health_cost > 0:
            p.actor.defense.apply_health_cost(res.health_cost)
        if res.shield_reaver_ratio > 0:
            p.defender.defense.set_shield_reaver(res.shield_reaver_ratio, at + 3)

    # 3b. Deliver all offensive damage parts into each defender's DefenseSession
    for p in payloads:
        res = p.step_result
        assert res is not None
        a_st = p.actor.defense.snapshot_state()
        is_blinded = a_st.blinded_until is not None and at < a_st.blinded_until
        dealt, sh_abs, hp_dmg, vamp_heals, reactive, d_lbls, d_nts = _deliver_parts(
            p.actor,
            p.defender,
            res.new_parts,
            p.step.text,
            p.step.crit,
            at,
            actor_blinded=is_blinded,
        )
        # Apply crowd-control effects declared on the cast ability
        if p.step.slot is not None and p.step.slot in p.actor.spec.ranks:
            ab = p.actor.spec.kit.abilities.get(p.step.slot)
            if ab is not None and ab.cc_effects:
                spell_blocked = any("spell shield" in n.lower() for n in d_nts)
                actor_stats, _ = sheet_stats(p.actor.spec.sheet)
                rank = p.actor.spec.ranks[p.step.slot]
                for cc in ab.cc_effects:
                    if not cc.applies_to_case(p.step.case):
                        continue
                    try:
                        eval_dur = evaluate_formula(
                            cc.duration_formula,
                            actor_stats,
                            rank=rank,
                            level=p.actor.spec.sheet.level,
                            ops=ABILITY_OPS,
                        )
                    except FormulaError:
                        continue
                    if eval_dur.exact is None or eval_dur.exact <= 0:
                        continue
                    _eff_dur, ss_heals, cc_lbls, cc_nts = p.defender.defense.apply_cc(
                        cc,
                        eval_dur.exact,
                        at,
                        blocked_by_spell_shield=spell_blocked,
                    )
                    for h_ev in ss_heals:
                        p.defender.healing_done += h_ev.amount
                    d_lbls.extend(cc_lbls)
                    d_nts.extend(cc_nts)
        delivery_results.append((p, dealt, sh_abs, hp_dmg, vamp_heals, reactive, d_lbls, d_nts))

    # 3c. Apply post-hit debuffs (Ignite / Grievous Wounds / Exhaust) & Thornmail reflect
    reflect_taken: list[tuple[Fraction, list[Label], list[str]]] = []
    for p, _dealt, _sh_abs, _hp_dmg, _vamp, reactive, _d_lbls, _d_nts in delivery_results:
        res = p.step_result
        assert res is not None
        if res.applied_grievous_until is not None:
            p.defender.defense.set_grievous_until(res.applied_grievous_until)
        if res.applied_exhaust_until is not None and (
            p.defender.exhausted_until is None
            or res.applied_exhaust_until > p.defender.exhausted_until
        ):
            p.defender.exhausted_until = res.applied_exhaust_until
        r_dmg, r_lbls, r_nts = _apply_reactive_reflect(p.actor, p.defender, reactive, at)
        reflect_taken.append((r_dmg, r_lbls, r_nts))

    # 3d. Apply scaled vamp, step heal events, and step shield events onto alive actors
    final_heals: list[Fraction] = []
    final_shields: list[Fraction] = []
    final_labels: list[list[Label]] = []
    for (p, dealt, _sh_abs, _hp_dmg, vamp_heals, _reactive, d_lbls, _d_nts), (
        _r_dmg,
        r_lbls,
        _r_nts,
    ) in zip(delivery_results, reflect_taken, strict=True):
        res = p.step_result
        assert res is not None
        scaled_heals = _scale_damage_dealt_heals(res.heal_events, res.new_parts, dealt)
        all_in_heals = [*vamp_heals, *scaled_heals]
        healed_amt, shielded_amt, out_heals, out_shields = p.actor.defense.apply_self_survival(
            all_in_heals, res.shield_events, at
        )
        p.actor.healing_done += healed_amt
        p.actor.shield_granted += shielded_amt
        for sh_ev in out_shields:
            p.actor.offense.notify_shield_granted(sh_ev.amount, at)
        pre_heal_total = sum((h.amount for h in p.pre_heals), Fraction(0))
        pre_shield_total = sum((s.amount for s in p.pre_shields), Fraction(0))
        final_heals.append(pre_heal_total + healed_amt)
        final_shields.append(pre_shield_total + shielded_amt)
        ev_lbls = [
            res.outcome.label,
            *p.pre_labels,
            *d_lbls,
            *r_lbls,
            *(h.label for h in out_heals),
            *(s.label for s in out_shields),
        ]
        final_labels.append(ev_lbls)
        p.actor.labels.extend(ev_lbls)

    # 3e. Emit chronological DuelEvents with end-of-tick HP/shield snapshots
    a_after = fighter_a.defense.snapshot_state()
    b_after = fighter_b.defense.snapshot_state()
    for (
        (p, dealt, sh_abs, hp_dmg, _vamp, _reactive, _d_lbls, d_nts),
        (r_dmg, _r_lbls, r_nts),
        h_tot,
        s_tot,
        ev_lbls,
    ) in zip(
        delivery_results, reflect_taken, final_heals, final_shields, final_labels, strict=True
    ):
        ev_notes = tuple(dict.fromkeys([*p.pre_notes, *d_nts, *r_nts]))
        events.append(
            DuelEvent(
                index=len(events) + 1,
                time=at,
                actor=p.actor.side,
                action=p.step.text,
                damage_dealt=dealt,
                shield_absorbed=sh_abs,
                health_damage=hp_dmg,
                healing_done=h_tot,
                shield_granted=s_tot,
                reactive_damage=r_dmg,
                a_health_after=a_after.health,
                a_shield_after=a_after.shield,
                b_health_after=b_after.health,
                b_shield_after=b_after.shield,
                label=weakest(ev_lbls) if ev_lbls else Label.OFFICIAL,
                notes=ev_notes,
            )
        )


def _accrue_both(
    fighter_a: _FighterRuntime,
    fighter_b: _FighterRuntime,
    until: Fraction,
    tie_break: str,
    events: list[DuelEvent],
) -> tuple[bool, bool]:
    """Advance continuous HoTs/bleeds/burns/regen for both sides to ``until``."""
    # 1. Defense continuous accruals (HoTs, Warmog, Doran's Shield, Second Wind, DD bleeds)
    a_d_heals, a_bleed, a_b_lbls, a_b_nts, _ = fighter_a.defense.accrue_to(until)
    b_d_heals, b_bleed, b_b_lbls, b_b_nts, _ = fighter_b.defense.accrue_to(until)
    a_h_gain = sum((h.amount for h in a_d_heals), Fraction(0))
    b_h_gain = sum((h.amount for h in b_d_heals), Fraction(0))
    fighter_a.healing_done += a_h_gain
    fighter_b.healing_done += b_h_gain
    fighter_a.damage_taken += a_bleed
    fighter_b.damage_taken += b_bleed

    # Sync offense targets before accruing burns/delayed procs
    a_st = fighter_a.defense.snapshot_state()
    b_st = fighter_b.defense.snapshot_state()
    fighter_a.offense.sync_context(
        fighter_b.defense.target_snapshot(until),
        a_st.health,
        a_st.max_health,
        exhausted=_is_exhausted(fighter_a, until),
    )
    fighter_b.offense.sync_context(
        fighter_a.defense.target_snapshot(until),
        b_st.health,
        b_st.max_health,
        exhausted=_is_exhausted(fighter_b, until),
    )

    a_b_parts, a_o_heals, _ = fighter_a.offense.accrue_to(until)
    b_b_parts, b_o_heals, _ = fighter_b.offense.accrue_to(until)

    if a_o_heals:
        ah, _, _, _ = fighter_a.defense.apply_self_survival(a_o_heals, (), until)
        fighter_a.healing_done += ah
        a_h_gain += ah
    if b_o_heals:
        bh, _, _, _ = fighter_b.defense.apply_self_survival(b_o_heals, (), until)
        fighter_b.healing_done += bh
        b_h_gain += bh

    # Deliver burns / delayed procs (respecting tie_break order when lethal)
    burn_pairs: list[tuple[_FighterRuntime, _FighterRuntime, list[Part]]] = []
    if tie_break == "b_first":
        if b_b_parts:
            burn_pairs.append((fighter_b, fighter_a, b_b_parts))
        if a_b_parts:
            burn_pairs.append((fighter_a, fighter_b, a_b_parts))
    else:
        if a_b_parts:
            burn_pairs.append((fighter_a, fighter_b, a_b_parts))
        if b_b_parts:
            burn_pairs.append((fighter_b, fighter_a, b_b_parts))

    burn_records: list[
        tuple[_FighterRuntime, Fraction, Fraction, Fraction, Fraction, list[Label], list[str]]
    ] = []
    for actor, defender, b_parts in burn_pairs:
        if tie_break != "simultaneous" and actor.defense.snapshot_state().health <= 0:
            continue
        dealt, sh_abs, hp_dmg, vamp_heals, reactive, d_lbls, d_nts = _deliver_parts(
            actor, defender, b_parts, "burns", False, until
        )
        r_dmg, r_lbls, r_nts = _apply_reactive_reflect(actor, defender, reactive, until)
        v_gain = Fraction(0)
        if vamp_heals:
            v_gain, _, _, _ = actor.defense.apply_self_survival(vamp_heals, (), until)
            actor.healing_done += v_gain
        if dealt > 0 or v_gain > 0 or r_dmg > 0:
            burn_records.append(
                (actor, dealt, sh_abs, hp_dmg, v_gain, [*d_lbls, *r_lbls], [*d_nts, *r_nts])
            )
            actor.labels.extend([*d_lbls, *r_lbls])

    a_after = fighter_a.defense.snapshot_state()
    b_after = fighter_b.defense.snapshot_state()
    for actor, dealt, sh_abs, hp_dmg, v_gain, lbls, nts in burn_records:
        events.append(
            DuelEvent(
                index=len(events) + 1,
                time=until,
                actor=actor.side,
                action="burns",
                damage_dealt=dealt,
                shield_absorbed=sh_abs,
                health_damage=hp_dmg,
                healing_done=v_gain,
                shield_granted=Fraction(0),
                reactive_damage=Fraction(0),
                a_health_after=a_after.health,
                a_shield_after=a_after.shield,
                b_health_after=b_after.health,
                b_shield_after=b_after.shield,
                label=weakest(lbls) if lbls else Label.OFFICIAL,
                notes=tuple(dict.fromkeys(nts)),
            )
        )

    if a_bleed > 0 or b_bleed > 0:
        sys_lbls = [*a_b_lbls, *b_b_lbls]
        sys_nts = tuple(dict.fromkeys([*a_b_nts, *b_b_nts]))
        events.append(
            DuelEvent(
                index=len(events) + 1,
                time=until,
                actor="system",
                action="bleed",
                damage_dealt=a_bleed + b_bleed,
                shield_absorbed=Fraction(0),
                health_damage=a_bleed + b_bleed,
                healing_done=a_h_gain + b_h_gain,
                shield_granted=Fraction(0),
                reactive_damage=Fraction(0),
                a_health_after=a_after.health,
                a_shield_after=a_after.shield,
                b_health_after=b_after.health,
                b_shield_after=b_after.shield,
                label=weakest(sys_lbls) if sys_lbls else Label.OFFICIAL,
                notes=sys_nts,
            )
        )

    return a_after.health <= 0, b_after.health <= 0


def _summary(fighter: _FighterRuntime) -> FighterDuelSummary:
    st: DefenseState = fighter.defense.snapshot_state()
    return FighterDuelSummary(
        side=fighter.side,
        champion_id=fighter.spec.sheet.champion.id,
        champion_name=fighter.spec.sheet.champion.name,
        level=fighter.spec.sheet.level,
        start_health=fighter.start_health,
        max_health=st.max_health,
        remaining_health=st.health,
        remaining_shield=st.shield,
        damage_dealt=fighter.damage_dealt,
        damage_taken=fighter.damage_taken,
        healing_done=fighter.healing_done,
        shield_granted=fighter.shield_granted,
        shield_absorbed=fighter.shield_absorbed,
        actions_taken=fighter.actions_taken,
        survived=st.health > 0,
        resource=fighter.offense.resource_summary(),
    )


def evaluate_duel(
    fighter_a: DuelFighterSpec,
    fighter_b: DuelFighterSpec,
    *,
    mode: str = DEFAULT_DUEL_MODE,
    tie_break: str = DEFAULT_DUEL_TIE_BREAK,
    max_duration: Fraction = DEFAULT_DUEL_MAX_DURATION,
) -> DuelOutcome:
    """Run a deterministic coupled 1v1 duel between ``fighter_a`` and ``fighter_b``."""
    if mode not in DUEL_MODES:
        raise RotationError(f"unknown duel mode {mode!r}; expected one of {sorted(DUEL_MODES)}")
    if tie_break not in DUEL_TIE_BREAKS:
        raise RotationError(
            f"unknown duel tie_break {tie_break!r}; expected one of {sorted(DUEL_TIE_BREAKS)}"
        )
    if max_duration <= 0:
        raise RotationError("max_duration must be positive")

    # Initialize both defense sessions first so each offense session sees the live opponent
    def_a = open_defense_session(
        fighter_a.sheet,
        start_health=fighter_a.start_health,
        start_shield=fighter_a.start_shield,
        shield_type=fighter_a.shield_type,
        runes=fighter_a.runes,
        rune_data=fighter_a.rune_data,
        inputs=_defense_inputs(fighter_a.inputs),
        timeline=True,
        kit=fighter_a.kit,
        summoners=fighter_a.summoners,
        summoner_data=fighter_a.summoner_data,
        defender_ranks=fighter_a.ranks,
    )
    def_b = open_defense_session(
        fighter_b.sheet,
        start_health=fighter_b.start_health,
        start_shield=fighter_b.start_shield,
        shield_type=fighter_b.shield_type,
        runes=fighter_b.runes,
        rune_data=fighter_b.rune_data,
        inputs=_defense_inputs(fighter_b.inputs),
        timeline=True,
        kit=fighter_b.kit,
        summoners=fighter_b.summoners,
        summoner_data=fighter_b.summoner_data,
        defender_ranks=fighter_b.ranks,
    )

    init_a = def_a.snapshot_state()
    init_b = def_b.snapshot_state()
    off_a = open_rotation_session(
        fighter_a.kit,
        fighter_a.sheet,
        fighter_a.ranks,
        def_b.target_snapshot(Fraction(0)),
        fighter_a.crit_base,
        holder_range=fighter_a.holder_range,
        inputs=fighter_a.inputs,
        runes=fighter_a.runes,
        rune_data=fighter_a.rune_data,
        ap_weight=fighter_a.ap_weight,
        start_resource=fighter_a.start_resource,
        allow_insufficient_resource=fighter_a.allow_insufficient_resource,
        apply_passives=fighter_a.apply_passives,
        summoners=fighter_a.summoners,
        summoner_data=fighter_a.summoner_data,
    )
    off_b = open_rotation_session(
        fighter_b.kit,
        fighter_b.sheet,
        fighter_b.ranks,
        def_a.target_snapshot(Fraction(0)),
        fighter_b.crit_base,
        holder_range=fighter_b.holder_range,
        inputs=fighter_b.inputs,
        runes=fighter_b.runes,
        rune_data=fighter_b.rune_data,
        ap_weight=fighter_b.ap_weight,
        start_resource=fighter_b.start_resource,
        allow_insufficient_resource=fighter_b.allow_insufficient_resource,
        apply_passives=fighter_b.apply_passives,
        summoners=fighter_b.summoners,
        summoner_data=fighter_b.summoner_data,
    )
    off_a.sync_context(def_b.target_snapshot(Fraction(0)), init_a.health, init_a.max_health)
    off_b.sync_context(def_a.target_snapshot(Fraction(0)), init_b.health, init_b.max_health)

    rt_a = _FighterRuntime(
        side="A",
        spec=fighter_a,
        defense=def_a,
        offense=off_a,
        start_health=init_a.health,
        priority_parsed=_parse_priority_slots(fighter_a),
    )
    rt_b = _FighterRuntime(
        side="B",
        spec=fighter_b,
        defense=def_b,
        offense=off_b,
        start_health=init_b.health,
        priority_parsed=_parse_priority_slots(fighter_b),
    )

    clock = Fraction(0)
    events: list[DuelEvent] = []
    winner: str | None = None
    ticks = 0

    while ticks < _MAX_DUEL_TICKS:
        ticks += 1
        act_a = _next_action(rt_a, clock, mode)
        act_b = _next_action(rt_b, clock, mode)

        # Collect all candidate timestamps <= max_duration
        candidates: list[Fraction] = []
        if act_a is not None and act_a[0] <= max_duration:
            candidates.append(act_a[0])
        if act_b is not None and act_b[0] <= max_duration:
            candidates.append(act_b[0])
        for pending_t in (
            rt_a.defense.next_event_time(clock, max_duration),
            rt_b.defense.next_event_time(clock, max_duration),
            rt_a.offense.next_pending_time(clock, max_duration),
            rt_b.offense.next_pending_time(clock, max_duration),
        ):
            if pending_t is not None and pending_t <= max_duration:
                candidates.append(pending_t)

        if not candidates:
            # No further actions or pending events within max_duration
            if mode != "strict_scripted" and clock < max_duration:
                a_dead, b_dead = _accrue_both(rt_a, rt_b, max_duration, tie_break, events)
                clock = max_duration
                if a_dead and b_dead:
                    winner = "draw_mutual_kill"
                elif b_dead:
                    winner = "A"
                elif a_dead:
                    winner = "B"
            break

        t_next = min(candidates)
        if t_next > clock:
            a_dead, b_dead = _accrue_both(rt_a, rt_b, t_next, tie_break, events)
            clock = t_next
            if a_dead and b_dead:
                winner = "draw_mutual_kill"
                break
            if b_dead:
                winner = "A"
                break
            if a_dead:
                winner = "B"
                break

        a_acts = act_a is not None and act_a[0] == clock
        b_acts = act_b is not None and act_b[0] == clock

        # Consume completed wait steps cleanly
        if a_acts and act_a is not None and act_a[1].wait is not None:
            rt_a.pending_wait_target = None
            rt_a.step_idx += 1
            a_acts = False
        if b_acts and act_b is not None and act_b[1].wait is not None:
            rt_b.pending_wait_target = None
            rt_b.step_idx += 1
            b_acts = False

        if not a_acts and not b_acts:
            # Pure internal event tick (shield/HoT/burn/stasis expiry); continue loop
            continue

        if a_acts and b_acts and act_a is not None and act_b is not None:
            if tie_break == "simultaneous":
                pa = _ActionPayload(rt_a, rt_b, act_a[1], act_a[2])
                pb = _ActionPayload(rt_b, rt_a, act_b[1], act_b[2])
                _phase1_activate_defensives(pa, clock)
                _phase1_activate_defensives(pb, clock)
                _phase2_compute_offense(pa, clock)
                _phase2_compute_offense(pb, clock)
                _phase3_deliver_and_survive((pa, pb), clock, events, rt_a, rt_b)
            else:
                order = (
                    ((rt_a, rt_b, act_a), (rt_b, rt_a, act_b))
                    if tie_break == "a_first"
                    else ((rt_b, rt_a, act_b), (rt_a, rt_b, act_a))
                )
                for actor, defender, act_info in order:
                    st_actor = actor.defense.snapshot_state()
                    if st_actor.health <= 0 or (
                        st_actor.stasis_until is not None and clock < st_actor.stasis_until
                    ):
                        continue
                    if defender.defense.snapshot_state().health <= 0:
                        break
                    p = _ActionPayload(actor, defender, act_info[1], act_info[2])
                    _phase1_activate_defensives(p, clock)
                    _phase2_compute_offense(p, clock)
                    _phase3_deliver_and_survive((p,), clock, events, rt_a, rt_b)
                    if (
                        rt_a.defense.snapshot_state().health <= 0
                        or rt_b.defense.snapshot_state().health <= 0
                    ):
                        break
        elif a_acts and act_a is not None:
            pa = _ActionPayload(rt_a, rt_b, act_a[1], act_a[2])
            _phase1_activate_defensives(pa, clock)
            _phase2_compute_offense(pa, clock)
            _phase3_deliver_and_survive((pa,), clock, events, rt_a, rt_b)
        elif b_acts and act_b is not None:
            pb = _ActionPayload(rt_b, rt_a, act_b[1], act_b[2])
            _phase1_activate_defensives(pb, clock)
            _phase2_compute_offense(pb, clock)
            _phase3_deliver_and_survive((pb,), clock, events, rt_a, rt_b)

        a_dead = rt_a.defense.snapshot_state().health <= 0
        b_dead = rt_b.defense.snapshot_state().health <= 0
        if a_dead and b_dead:
            winner = "draw_mutual_kill"
            break
        if b_dead:
            winner = "A"
            break
        if a_dead:
            winner = "B"
            break

    if winner is None:
        winner = "draw_timeout"

    def_out_a = rt_a.defense.outcome(f"duel vs {fighter_b.sheet.champion.name}")
    def_out_b = rt_b.defense.outcome(f"duel vs {fighter_a.sheet.champion.name}")

    all_labels: list[Label] = [
        def_out_a.label,
        def_out_b.label,
        *rt_a.labels,
        *rt_b.labels,
        *(ev.label for ev in events),
    ]
    if rt_a.offense.is_weakened() or rt_b.offense.is_weakened():
        all_labels.append(Label.PENDING)

    notes: list[str] = [
        f"duel: mode={mode}, tie_break={tie_break}, max_duration={format_number(max_duration)} s; "
        "positioning, skillshot misses, channel interruptions, and cast animation times "
        "are not modelled",
        *(f"A: {n}" for n in rt_a.offense.get_notes()),
        *(f"A defense: {n}" for n in def_out_a.notes),
        *(f"B: {n}" for n in rt_b.offense.get_notes()),
        *(f"B defense: {n}" for n in def_out_b.notes),
    ]
    if ticks >= _MAX_DUEL_TICKS:
        notes.append(f"duel stopped at safety tick cap ({_MAX_DUEL_TICKS})")
        all_labels.append(Label.PENDING)

    return DuelOutcome(
        patch=fighter_a.sheet.champion.patch,
        mode=mode,
        tie_break=tie_break,
        max_duration=max_duration,
        winner=winner,
        duration=clock,
        fighter_a=_summary(rt_a),
        fighter_b=_summary(rt_b),
        events=tuple(events),
        label=weakest(all_labels) if all_labels else Label.DERIVED,
        notes=tuple(dict.fromkeys(notes)),
    )
