"""CC locks, tenacity, cleanses, immunities, active casts, and hit negations."""

from __future__ import annotations

from fractions import Fraction
from typing import TYPE_CHECKING

from ..damage import DamageType, format_number
from ..formula import ABILITY_OPS, evaluate_formula
from ..kit import ActiveEffectSpec, CCEffectSpec
from ..passives import _effect_cooldown
from ..runes import linear_by_level, rune_value, scale_item_cooldown
from ..stats import Label, weakest
from ..summoners import (
    SummonerSpellSpec,
    barrier_duration,
    barrier_shield,
    cleanse_tenacity,
    exhaust_values,
    heal_amount,
)
from ..survival import HealEvent, ShieldEvent, scale_healing, scale_shield
from .models import TENACITY_MIN_DURATION, IncomingHit, _ActiveShield, _CCLock, _StaggerBleed

if TYPE_CHECKING:
    from .session import _DefenseRuntime


def effective_resists(
    rt: _DefenseRuntime, at: Fraction
) -> tuple[Fraction, Fraction, list[Label], list[str]]:
    cur_armor = rt.sim.armor
    cur_mr = rt.sim.magic_resist
    extra_bonus_armor = Fraction(0)
    extra_bonus_mr = Fraction(0)
    res_labels: list[Label] = []
    res_notes: list[str] = []

    # 8242 Unflinching (+10 Armor/MR while CC'd / 2 s after)
    live_impaired = rt.sim.defender_impaired or (
        rt.unflinching_cc_until is not None and at < rt.unflinching_cc_until
    )
    if rt.sim.unflinching_rune is not None and live_impaired:
        u_val = rune_value(rt.sim.unflinching_rune, "ResistMax")
        cur_armor += u_val
        cur_mr += u_val
        extra_bonus_armor += u_val
        extra_bonus_mr += u_val
        res_labels.append(rt.sim.rune_base)
        res_notes.append(
            f"rune:{rt.sim.unflinching_rune.id} Unflinching (+{format_number(u_val)} Armor/MR)"
        )

    # 8439 Aftershock (+45 + 75% bonus resist, capped 80..150 for 2.5 s)
    if rt.sim.aftershock_rune is not None and rt.sim.aftershock_active:
        as_dur = rune_value(rt.sim.aftershock_rune, "DelayBeforeBurst")
        if not rt.sim.timeline or at < as_dur:
            flat_r = rune_value(rt.sim.aftershock_rune, "FlatResists")
            pct_r = rune_value(rt.sim.aftershock_rune, "PercentBonusResist")
            cap_r = linear_by_level(
                rune_value(rt.sim.aftershock_rune, "BonusResistMin"),
                rune_value(rt.sim.aftershock_rune, "BonusResistMax"),
                rt.sim.sheet.level,
            )
            a_gain = min(cap_r, flat_r + rt.sim.bonus_armor * pct_r)
            m_gain = min(cap_r, flat_r + rt.sim.bonus_mr * pct_r)
            cur_armor += a_gain
            cur_mr += m_gain
            extra_bonus_armor += a_gain
            extra_bonus_mr += m_gain
            res_labels.append(rt.sim.rune_base)
            res_notes.append(
                f"rune:{rt.sim.aftershock_rune.id} Aftershock "
                f"(+{format_number(a_gain)} Armor, +{format_number(m_gain)} MR)"
            )

    for title, eff, comp, eff_label in rt.sim.stacking_resist_effects:
        active = (
            (title in rt.fon_active_until and at < rt.fon_active_until[title])
            if rt.sim.timeline
            else (rt.fon_stacks.get(title, 0) >= int((eff.get("stacks") or {}).get("required", 8)))
        )
        if not active:
            continue
        val = evaluate_formula(
            comp.get("formula"),
            rt.sim.stats_env,
            holder_range=rt.sim.defender_range,
            level=rt.sim.sheet.level,
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

    if rt.sim.timeline and rt.jaksho_start is not None:
        for title, _, comp, eff_label in rt.sim.combat_resist_ramps:
            delay = Fraction(str(comp["delay_seconds"]))
            if at - rt.jaksho_start < delay:
                continue
            pct = evaluate_formula(
                comp.get("formula"),
                rt.sim.stats_env,
                holder_range=rt.sim.defender_range,
                level=rt.sim.sheet.level,
            ).exact
            assert pct is not None
            if comp.get("stat") == "armor":
                gain = (rt.sim.bonus_armor + extra_bonus_armor) * pct / 100
                cur_armor += gain
            elif comp.get("stat") == "magic_resist":
                gain = (rt.sim.bonus_mr + extra_bonus_mr) * pct / 100
                cur_mr += gain
            else:
                gain = Fraction(0)
            if gain > 0:
                res_labels.append(eff_label)
                res_notes.append(f"{title} (+{format_number(gain)} {comp.get('stat')})")

    for end_t, st_id, mode, val, src, lbl in rt.active_resist_buffs:
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


def apply_one_active_effect(
    rt: _DefenseRuntime,
    slot: str,
    rank: int,
    eff: ActiveEffectSpec,
    at: Fraction,
    granted_out: list[ShieldEvent],
    labels_out: list[Label],
    notes_out: list[str],
) -> None:
    dur = rt.sim._active_duration(eff, rank)
    end_t = at + dur if (rt.sim.timeline and dur is not None) else None
    src = f"kit:{rt.sim.sheet.champion.id} {slot}.{eff.id} ({eff.name})"
    if eff.kind == "damage_dealt_heal":
        return
    if eff.kind == "heal" and not (
        eff.over_duration and rt.sim.timeline and dur is not None and dur > 0
    ):
        rt.active_instant_heals.append((slot, src, eff, rank))
        return
    if eff.kind == "recent_damage_heal":
        rt.pending_recent_heals.append((src, eff, rank))
        return
    if eff.kind == "recent_damage_shield":
        if eff.input_name is not None and eff.input_name in rt.sim.inputs:
            ratio, eff_lbl = rt.sim._eval_active(
                eff, rank, current_health=rt.health, current_max_health=rt.current_max_health
            )
            stored = max(Fraction(0), Fraction(str(rt.sim.inputs[eff.input_name])))
            raw_sh = stored * ratio / 100
            if eff.min_formula is not None:
                mn, _ = rt.sim._eval_active_formula(
                    eff.min_formula,
                    rank,
                    eff.label,
                    current_health=rt.health,
                    current_max_health=rt.current_max_health,
                )
                raw_sh = max(raw_sh, mn)
            if eff.max_formula is not None:
                mx, _ = rt.sim._eval_active_formula(
                    eff.max_formula,
                    rank,
                    eff.label,
                    current_health=rt.health,
                    current_max_health=rt.current_max_health,
                )
                raw_sh = min(raw_sh, mx)
            if raw_sh > 0:
                rev_amp = rt.sim._revitalize_amp(rt.health)
                sh_amt = (
                    scale_shield(
                        raw_sh,
                        hsp=rt.sim.hsp if eff.uses_hsp else Fraction(0),
                        revitalize_amp=rev_amp if eff.uses_hsp else Fraction(0),
                    )
                    * rt.sim.self_shield_amp
                )
                sh_notes = [f"{eff.name} (--input {eff.input_name}={format_number(stored)})"]
                if rt.sim.shield_reaver_rate > 0:
                    sh_amt *= 1 - rt.sim.shield_reaver_rate
                rt.shields.append(_ActiveShield(src, sh_amt, eff.shield_type, end_t))
                sh_lbl = weakest([eff_lbl, *rt.sim.self_amp_labels])
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
            rt.pending_recent_shields.append((src, eff, rank, dur))
        return
    if eff.kind == "dodge_attacks":
        rt.active_dodge_ends.append((end_t, src, eff.label))
        return
    if eff.kind == "spell_shield":
        rt.spell_shield_slots.add(slot)
        rt.active_spell_shields.append([end_t, False, src, eff.label, slot])
        return
    if eff.kind == "block_first_hit":
        rt.active_first_hit_blocks.append([end_t, False, src, eff.label])
        return
    if eff.kind == "cleanse":
        qss_level = rt.sim.sheet.champion.id != "Milio"
        cleared = cleanse_cc(rt, qss=qss_level, at=at)
        labels_out.append(eff.label)
        if cleared:
            notes_out.append(f"{src}: cleansed {', '.join(cleared)}")
        else:
            notes_out.append(f"{src}: cleansed active CC")
        return
    if eff.kind == "cc_immune":
        requires_magic_sh = rt.sim.sheet.champion.id == "Morgana" and slot == "E"
        rt.cc_immune_windows.append((end_t, requires_magic_sh, src, eff.label))
        labels_out.append(eff.label)
        notes_out.append(
            f"{src}: CC immune" + (f" for {format_number(dur)} s" if dur is not None else "")
        )
        return
    val, eff_lbl = rt.sim._eval_active(
        eff, rank, current_health=rt.health, current_max_health=rt.current_max_health
    )
    if eff.kind == "invulnerable":
        if eff.mode == "undying":
            rt.active_undying.append((end_t, val, src, eff_lbl))
        else:
            rt.active_invuln_ends.append((end_t, src, eff_lbl))
        return
    if eff.kind == "stat_bonus" and eff.stat is not None:
        if eff.stat == "health":
            gain = rt.current_max_health * val / 100 if eff.mode == "percent" else val
            rt.current_max_health += gain
            rt.health += gain
            if end_t is not None:
                rt.active_hp_buffs.append((end_t, gain))
            labels_out.append(eff_lbl)
            notes_out.append(
                f"{src} (+{format_number(gain)} max HP"
                + (f" for {format_number(dur)} s)" if dur is not None else ")")
            )
        elif eff.stat in {"armor", "magic_resist"}:
            rt.active_resist_buffs.append((end_t, eff.stat, eff.mode, val, src, eff_lbl))
    elif eff.kind == "damage_taken_modifier":
        if eff.mode == "percent":
            frac = val / 100 if val > 1 else val
            rt.active_percent_dr.append((end_t, eff.damage_type, frac, src, eff_lbl))
        else:
            rt.active_flat_dr.append(
                (end_t, eff.damage_type, val, eff.damage_reduction_cap, src, eff_lbl)
            )
    elif eff.kind == "shield":
        rev_amp = rt.sim._revitalize_amp(rt.health)
        sh_amt = (
            scale_shield(
                val,
                hsp=rt.sim.hsp if eff.uses_hsp else Fraction(0),
                revitalize_amp=rev_amp if eff.uses_hsp else Fraction(0),
            )
            * rt.sim.self_shield_amp
        )
        sh_notes = [f"{eff.name} ({format_number(dur)} s)" if dur is not None else eff.name]
        if rt.sim.shield_reaver_rate > 0:
            sh_amt *= 1 - rt.sim.shield_reaver_rate
            sh_notes.append(f"Shield Reaver (-{format_number(rt.sim.shield_reaver_rate * 100)}%)")
        rt.shields.append(_ActiveShield(src, sh_amt, eff.shield_type, end_t))
        sh_label = weakest([eff_lbl, *rt.sim.self_amp_labels])
        granted_out.append(
            ShieldEvent(src, val, sh_amt, eff.shield_type, dur, sh_label, tuple(sh_notes))
        )
        labels_out.append(sh_label)
    elif eff.kind == "heal":
        assert dur is not None and dur > 0
        rt.active_hots.append((at + dur, val / dur, src, eff_lbl, eff.uses_hsp))
        labels_out.append(eff_lbl)
        notes_out.append(f"{src} started {format_number(val)} heal over {format_number(dur)} s")


def activate_ability_cast(
    rt: _DefenseRuntime, slot: str, rank: int, case_id: str | None, at: Fraction
) -> tuple[list[ShieldEvent], list[HealEvent], list[Label], list[str]]:
    if rt.sim.kit is None or rt.health <= 0:
        return [], [], [], []
    rt.clock = max(rt.clock, at)
    rt.sync_dynamic_debuffs(rt.clock)
    rt.shields = rt.sim._expire_shields(rt.shields, rt.clock)
    ab = rt.sim.kit.ability(slot)
    matched = [e for e in ab.active_effects if e.applies_to_case(case_id)]
    granted_out: list[ShieldEvent] = []
    heals_out: list[HealEvent] = []
    labels_out: list[Label] = []
    notes_out: list[str] = []
    for eff in matched:
        if eff.kind == "recent_damage_shield" and rt.recent_damage_history:
            ratio, eff_lbl = rt.sim._eval_active(
                eff, rank, current_health=rt.health, current_max_health=rt.current_max_health
            )
            win = eff.window_seconds
            stored = sum(
                (
                    d
                    for t_h, d in rt.recent_damage_history
                    if (not rt.sim.timeline or win is None or rt.clock - t_h <= win)
                ),
                start=Fraction(0),
            )
            raw_sh = stored * ratio / 100
            if eff.min_formula is not None:
                mn, _ = rt.sim._eval_active_formula(
                    eff.min_formula,
                    rank,
                    eff.label,
                    current_health=rt.health,
                    current_max_health=rt.current_max_health,
                )
                raw_sh = max(raw_sh, mn)
            if eff.max_formula is not None:
                mx, _ = rt.sim._eval_active_formula(
                    eff.max_formula,
                    rank,
                    eff.label,
                    current_health=rt.health,
                    current_max_health=rt.current_max_health,
                )
                raw_sh = min(raw_sh, mx)
            if raw_sh > 0:
                dur = rt.sim._active_duration(eff, rank)
                end_t = rt.clock + dur if (rt.sim.timeline and dur is not None) else None
                rev_amp = rt.sim._revitalize_amp(rt.health)
                sh_amt = (
                    scale_shield(
                        raw_sh,
                        hsp=rt.sim.hsp if eff.uses_hsp else Fraction(0),
                        revitalize_amp=rev_amp if eff.uses_hsp else Fraction(0),
                    )
                    * rt.sim.self_shield_amp
                )
                if rt.sim.shield_reaver_rate > 0:
                    sh_amt *= 1 - rt.sim.shield_reaver_rate
                src = f"kit:{rt.sim.sheet.champion.id} {slot}.{eff.id} ({eff.name})"
                rt.shields.append(_ActiveShield(src, sh_amt, eff.shield_type, end_t))
                sh_lbl = weakest([eff_lbl, *rt.sim.self_amp_labels])
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
            mn, mn_lbl = rt.sim._eval_active_formula(
                eff.min_formula,
                rank,
                eff.label,
                current_health=rt.health,
                current_max_health=rt.current_max_health,
            )
            if mn > 0:
                dur = rt.sim._active_duration(eff, rank)
                end_t = rt.clock + dur if (rt.sim.timeline and dur is not None) else None
                rev_amp = rt.sim._revitalize_amp(rt.health)
                sh_amt = (
                    scale_shield(
                        mn,
                        hsp=rt.sim.hsp if eff.uses_hsp else Fraction(0),
                        revitalize_amp=rev_amp if eff.uses_hsp else Fraction(0),
                    )
                    * rt.sim.self_shield_amp
                )
                if rt.sim.shield_reaver_rate > 0:
                    sh_amt *= 1 - rt.sim.shield_reaver_rate
                src = f"kit:{rt.sim.sheet.champion.id} {slot}.{eff.id} ({eff.name})"
                rt.shields.append(_ActiveShield(src, sh_amt, eff.shield_type, end_t))
                sh_lbl = weakest([mn_lbl, *rt.sim.self_amp_labels])
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
            if eff.input_name is not None and eff.input_name in rt.sim.inputs:
                apply_one_active_effect(
                    rt, slot, rank, eff, rt.clock, granted_out, labels_out, notes_out
                )
            continue
        if eff.kind == "recent_damage_heal":
            if rt.recent_damage_history:
                ratio, h_lbl = rt.sim._eval_active(
                    eff, rank, current_health=rt.health, current_max_health=rt.current_max_health
                )
                win = eff.window_seconds
                stored = sum(
                    (
                        d
                        for t_h, d in rt.recent_damage_history
                        if (not rt.sim.timeline or win is None or rt.clock - t_h <= win)
                    ),
                    start=Fraction(0),
                )
                raw_h = stored * ratio / 100
                if eff.min_formula is not None:
                    mn, _ = rt.sim._eval_active_formula(
                        eff.min_formula,
                        rank,
                        eff.label,
                        current_health=rt.health,
                        current_max_health=rt.current_max_health,
                    )
                    raw_h = max(raw_h, mn)
                if eff.max_formula is not None:
                    mx, _ = rt.sim._eval_active_formula(
                        eff.max_formula,
                        rank,
                        eff.label,
                        current_health=rt.health,
                        current_max_health=rt.current_max_health,
                    )
                    raw_h = min(raw_h, mx)
                if raw_h > 0 and rt.health < rt.current_max_health:
                    rev_amp = rt.sim._revitalize_amp(rt.health)
                    h_amt = (
                        scale_healing(
                            raw_h,
                            hsp=rt.sim.hsp if eff.uses_hsp else Fraction(0),
                            revitalize_amp=rev_amp if eff.uses_hsp else Fraction(0),
                            grievous=rt.sim.grievous,
                            uses_hsp=eff.uses_hsp,
                        )
                        * rt.sim.self_heal_amp
                    )
                    gained = min(h_amt, max(Fraction(0), rt.current_max_health - rt.health))
                    rt.health += gained
                    src = f"kit:{rt.sim.sheet.champion.id} {slot}.{eff.id} ({eff.name})"
                    ev_lbl = weakest([h_lbl, *rt.sim.self_amp_labels])
                    heals_out.append(
                        HealEvent(
                            src,
                            raw_h,
                            gained,
                            eff.uses_hsp,
                            rt.sim.grievous > 0,
                            ev_lbl,
                            (
                                f"{eff.name} ({format_number(ratio)}% of "
                                f"{format_number(stored)} recent)",
                            ),
                        )
                    )
                    labels_out.append(ev_lbl)
            continue
        apply_one_active_effect(rt, slot, rank, eff, rt.clock, granted_out, labels_out, notes_out)
    # Fire immediate non-conditional instant heals; keep only spell_blocked heals waiting
    if rt.active_instant_heals:
        still_waiting: list[tuple[str, str, ActiveEffectSpec, int]] = []
        for h_slot, src, eff, h_rank in rt.active_instant_heals:
            if (
                eff.condition == "spell_blocked"
                and h_slot in rt.spell_shield_slots
                and h_slot not in rt.spell_shield_blocked_slots
            ):
                still_waiting.append((h_slot, src, eff, h_rank))
                continue
            if rt.health >= rt.current_max_health:
                continue
            raw_h, h_lbl = rt.sim._eval_active(
                eff, h_rank, current_health=rt.health, current_max_health=rt.current_max_health
            )
            if raw_h <= 0:
                continue
            rev_amp = rt.sim._revitalize_amp(rt.health)
            h_amt = (
                scale_healing(
                    raw_h,
                    hsp=rt.sim.hsp if eff.uses_hsp else Fraction(0),
                    revitalize_amp=rev_amp if eff.uses_hsp else Fraction(0),
                    grievous=rt.sim.grievous,
                    uses_hsp=eff.uses_hsp,
                )
                * rt.sim.self_heal_amp
            )
            gained = min(h_amt, max(Fraction(0), rt.current_max_health - rt.health))
            rt.health += gained
            ev_lbl = weakest([h_lbl, *rt.sim.self_amp_labels])
            heals_out.append(
                HealEvent(
                    src,
                    raw_h,
                    gained,
                    eff.uses_hsp,
                    rt.sim.grievous > 0,
                    ev_lbl,
                    ("active ability heal",),
                )
            )
            labels_out.append(ev_lbl)
        rt.active_instant_heals = still_waiting
    return granted_out, heals_out, labels_out, notes_out


def activate_summoner(
    rt: _DefenseRuntime, sp: SummonerSpellSpec, at: Fraction
) -> tuple[list[ShieldEvent], list[HealEvent], list[Label], list[str]]:
    if rt.health <= 0:
        return [], [], [], []
    rt.clock = max(rt.clock, at)
    rt.sync_dynamic_debuffs(rt.clock)
    granted_out: list[ShieldEvent] = []
    heals_out: list[HealEvent] = []
    labels_out: list[Label] = []
    notes_out: list[str] = []
    title = f"summoner:{sp.id} ({sp.name})"
    if sp.id == "SummonerBarrier":
        raw_b = barrier_shield(sp, rt.sim.sheet.level)
        dur_b = barrier_duration(sp)
        rev_amp = rt.sim._revitalize_amp(rt.health)
        b_amt = scale_shield(raw_b, hsp=rt.sim.hsp, revitalize_amp=rev_amp) * rt.sim.self_shield_amp
        if rt.sim.shield_reaver_rate > 0:
            b_amt *= 1 - rt.sim.shield_reaver_rate
        end_t = rt.clock + dur_b if rt.sim.timeline else None
        rt.shields.append(_ActiveShield(title, b_amt, "normal", end_t))
        b_lbl = weakest([rt.sim.summoner_label, *rt.sim.self_amp_labels])
        granted_out.append(ShieldEvent(title, raw_b, b_amt, "normal", dur_b, b_lbl, (sp.name,)))
        labels_out.append(b_lbl)
    elif sp.id == "SummonerHeal":
        raw_h = heal_amount(sp, rt.sim.sheet.level, debuffed=rt.sim.summoner_heal_debuffed)
        rev_amp = rt.sim._revitalize_amp(rt.health)
        h_amt = (
            scale_healing(
                raw_h,
                hsp=rt.sim.hsp,
                revitalize_amp=rev_amp,
                grievous=rt.sim.grievous,
                uses_hsp=True,
            )
            * rt.sim.self_heal_amp
        )
        gained = min(h_amt, max(Fraction(0), rt.current_max_health - rt.health))
        rt.health += gained
        h_lbl = weakest([rt.sim.summoner_label, *rt.sim.self_amp_labels])
        heals_out.append(
            HealEvent(title, raw_h, gained, True, rt.sim.grievous > 0, h_lbl, (sp.name,))
        )
        labels_out.append(h_lbl)
    elif sp.id == "SummonerBoost":
        ten, dur_c = cleanse_tenacity(sp)
        cleared = cleanse_cc(rt, qss=False, at=rt.clock)
        rt.cleanse_tenacity_val = max(rt.cleanse_tenacity_val, ten)
        new_ten_end = rt.clock + dur_c
        if rt.cleanse_tenacity_until is None or new_ten_end > rt.cleanse_tenacity_until:
            rt.cleanse_tenacity_until = new_ten_end
        cleared_txt = f" ({', '.join(cleared)})" if cleared else ""
        notes_out.append(
            f"{title}: cleansed debuffs{cleared_txt} + {format_number(ten * 100)}% "
            f"tenacity for {format_number(dur_c)} s"
        )
        labels_out.append(rt.sim.summoner_label)
    return granted_out, heals_out, labels_out, notes_out


def cleanse_cc(rt: _DefenseRuntime, *, qss: bool = False, at: Fraction) -> list[str]:
    cleared: list[str] = []
    kept: list[_CCLock] = []
    for lock in rt.cc_locks:
        if lock.end <= at:
            continue
        can_clear = lock.cleansable_by_qss if qss else lock.cleansable_by_cleanse
        if can_clear:
            cleared.append(lock.kind)
        else:
            kept.append(lock)
    rt.cc_locks = kept
    return cleared


def apply_cc(
    rt: _DefenseRuntime,
    cc: CCEffectSpec,
    base_duration: Fraction,
    at: Fraction,
    *,
    blocked_by_spell_shield: bool = False,
) -> tuple[Fraction, list[HealEvent], list[Label], list[str]]:
    if rt.health <= 0 or base_duration <= 0:
        return Fraction(0), [], [], []
    rt.clock = max(rt.clock, at)
    if rt.sim.timeline and rt.ga_stasis_until is not None and rt.clock < rt.ga_stasis_until:
        return Fraction(0), [], [Label.OFFICIAL], ["CC ignored during 4 s GA stasis"]
    if blocked_by_spell_shield:
        return Fraction(0), [], [cc.label], [f"{cc.name}: blocked by spell shield"]
    # Intercept zero-damage pure-CC spells with an unconsumed spell shield
    for ss_entry in rt.active_spell_shields:
        ss_end, ss_used, ss_src, ss_lbl, ss_slot = ss_entry
        if not ss_used and (ss_end is None or rt.clock <= ss_end):
            ss_entry[1] = True
            rt.spell_shield_blocked_slots.add(ss_slot)
            ss_heals: list[HealEvent] = []
            ss_labels: list[Label] = [ss_lbl]
            # Fire spell_blocked instant heal (e.g. Sivir E) immediately
            if rt.active_instant_heals:
                remaining_heals: list[tuple[str, str, ActiveEffectSpec, int]] = []
                for h_slot, h_src, h_eff, h_rank in rt.active_instant_heals:
                    if h_slot == ss_slot and h_eff.condition == "spell_blocked":
                        raw_h, h_lbl = rt.sim._eval_active(
                            h_eff,
                            h_rank,
                            current_health=rt.health,
                            current_max_health=rt.current_max_health,
                        )
                        if raw_h > 0 and rt.health < rt.current_max_health:
                            rev_amp = rt.sim._revitalize_amp(rt.health)
                            h_amt = (
                                scale_healing(
                                    raw_h,
                                    hsp=rt.sim.hsp if h_eff.uses_hsp else Fraction(0),
                                    revitalize_amp=rev_amp if h_eff.uses_hsp else Fraction(0),
                                    grievous=rt.sim.grievous,
                                    uses_hsp=h_eff.uses_hsp,
                                )
                                * rt.sim.self_heal_amp
                            )
                            gained = min(h_amt, max(Fraction(0), rt.current_max_health - rt.health))
                            rt.health += gained
                            ev_lbl = weakest([h_lbl, *rt.sim.self_amp_labels])
                            ss_heals.append(
                                HealEvent(
                                    h_src,
                                    raw_h,
                                    gained,
                                    h_eff.uses_hsp,
                                    rt.sim.grievous > 0,
                                    ev_lbl,
                                    ("spell shield heal",),
                                )
                            )
                            ss_labels.append(ev_lbl)
                    else:
                        remaining_heals.append((h_slot, h_src, h_eff, h_rank))
                rt.active_instant_heals = remaining_heals
            return (
                Fraction(0),
                ss_heals,
                ss_labels,
                [f"{ss_src} blocked {cc.name} ({cc.kind})"],
            )
    # Check active CC immunity (Olaf R, Fiora W Parry, Morgana E Black Shield)
    for imm_end, req_magic_sh, imm_src, imm_lbl in rt.cc_immune_windows:
        if imm_end is not None and rt.clock >= imm_end:
            continue
        if req_magic_sh and not any(
            sh.shield_type == "magic" and sh.remaining > 0 for sh in rt.shields
        ):
            continue
        return Fraction(0), [], [imm_lbl], [f"{imm_src} blocked {cc.name} ({cc.kind})"]

    eff_dur = base_duration
    out_labels: list[Label] = [cc.label]
    out_notes: list[str] = []
    if cc.tenacity_applies:
        base_ten = min(Fraction(1), max(Fraction(0), rt.sim.sheet["tenacity"].total()))
        if rt.cleanse_tenacity_until is not None and rt.clock < rt.cleanse_tenacity_until:
            eff_ten = 1 - (1 - base_ten) * (1 - rt.cleanse_tenacity_val)
            out_labels.append(rt.sim.summoner_label)
        else:
            eff_ten = base_ten
        if eff_ten > 0:
            reduced = base_duration * (1 - eff_ten)
            eff_dur = min(base_duration, max(TENACITY_MIN_DURATION, reduced))
            if base_ten > 0:
                out_labels.append(rt.sim.sheet["tenacity"].label)
            out_notes.append(
                f"{cc.name} ({cc.kind}): {format_number(eff_dur)} s "
                f"(base {format_number(base_duration)} s reduced by "
                f"{format_number(eff_ten * 100)}% tenacity)"
            )
        else:
            out_notes.append(f"{cc.name} ({cc.kind}): {format_number(eff_dur)} s")
    else:
        out_notes.append(f"{cc.name} ({cc.kind}): {format_number(eff_dur)} s (tenacity immune)")

    end_at = rt.clock + eff_dur
    rt.cc_locks.append(
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
    if rt.unflinching_cc_until is None or new_unf > rt.unflinching_cc_until:
        rt.unflinching_cc_until = new_unf
    return eff_dur, [], out_labels, out_notes


def check_hit_negations(
    rt: _DefenseRuntime,
    hit: IncomingHit,
    granted: list[ShieldEvent],
    step_labels: list[Label],
    step_notes: list[str],
) -> bool:
    """Evaluate spell shields, active defender casts, invulnerability, dodge, and blocks."""
    spell_blocked = False
    if hit.kind == "ability" and hit.amount > 0 and rt.health > 0:
        for title, eff, eff_label in rt.sim.spell_shields:
            can_block = (
                (title not in rt.spell_shield_used)
                if not rt.sim.timeline
                else (rt.clock >= rt.spell_shield_ready.get(title, Fraction(0)))
            )
            if can_block:
                rt.spell_shield_used.add(title)
                if rt.sim.timeline and eff.get("cooldown_seconds"):
                    rt.spell_shield_ready[title] = rt.clock + scale_item_cooldown(
                        Fraction(str(eff["cooldown_seconds"])), rt.sim.item_haste
                    )
                spell_blocked = True
                step_labels.append(eff_label)
                step_notes.append(f"{title} blocked incoming ability")
                break

    # 0b. Defender active ability casts (Q/W/E/R shields, heals, DR, resist/HP steroids)
    if rt.sim.defender_active_effects and not rt.active_cast_triggered and rt.health > 0:
        rt.active_cast_triggered = True
        for slot, rank, eff in rt.sim.defender_active_effects:
            apply_one_active_effect(rt, slot, rank, eff, rt.clock, granted, step_labels, step_notes)

    # 0c. Active defender hit negations (invulnerable, dodge, spell shield, block first hit)
    if not spell_blocked and hit.amount > 0 and rt.health > 0:
        for end_t, src, eff_lbl in rt.active_invuln_ends:
            if end_t is None or rt.clock <= end_t:
                spell_blocked = True
                step_labels.append(eff_lbl)
                step_notes.append(f"{src} invulnerable (0 damage)")
                break
    if not spell_blocked and hit.kind in {"attack", "crit"} and hit.amount > 0 and rt.health > 0:
        for end_t, src, eff_lbl in rt.active_dodge_ends:
            if end_t is None or rt.clock <= end_t:
                spell_blocked = True
                step_labels.append(eff_lbl)
                step_notes.append(f"{src} dodged basic attack")
                break
    if not spell_blocked and hit.kind == "ability" and hit.amount > 0 and rt.health > 0:
        for entry in rt.active_spell_shields:
            end_t, consumed, src, eff_lbl, sh_slot = entry
            if not consumed and (end_t is None or rt.clock <= end_t):
                entry[1] = True
                spell_blocked = True
                rt.spell_shield_blocked_slots.add(sh_slot)
                step_labels.append(eff_lbl)
                step_notes.append(f"{src} blocked incoming ability")
                break
    if not spell_blocked and hit.amount > 0 and rt.health > 0:
        for entry in rt.active_first_hit_blocks:
            end_t, consumed, src, eff_lbl = entry
            if not consumed and (end_t is None or rt.clock <= end_t):
                entry[1] = True
                spell_blocked = True
                step_labels.append(eff_lbl)
                step_notes.append(f"{src} blocked first hit")
                break

    return spell_blocked


def apply_damage_reductions(
    rt: _DefenseRuntime,
    hit: IncomingHit,
    incoming: Fraction,
    step_labels: list[Label],
    step_notes: list[str],
) -> tuple[Fraction, Fraction, Fraction, bool]:
    """Apply percent/flat DR, Death's Dance stagger, and Serpent's Fang shred."""
    # 8351 Glacial Augment ally freeze zone (-15% incoming physical & magic damage for 3 s)
    if (
        rt.sim.glacial_ally
        and incoming > 0
        and rt.health > 0
        and hit.damage_type in {DamageType.PHYSICAL, DamageType.MAGIC}
        and (not rt.sim.timeline or rt.clock < 3)
    ):
        incoming *= Fraction(85, 100)
        step_labels.append(rt.sim.rune_base)
        step_notes.append("rune:8351 GlacialAugment (-15% enemy damage vs allies)")

    # SummonerExhaust (-35% incoming physical & magic damage for 3 s; never reduces true)
    if (
        rt.sim.summoner_exhaust is not None
        and incoming > 0
        and rt.health > 0
        and hit.damage_type in {DamageType.PHYSICAL, DamageType.MAGIC}
    ):
        ex_dr, ex_slow, ex_dur = exhaust_values(rt.sim.summoner_exhaust)
        if not rt.exhaust_used:
            rt.exhaust_used = True
            if rt.sim.timeline:
                rt.exhaust_end = rt.clock + ex_dur
        if not rt.sim.timeline or (rt.exhaust_end is not None and rt.clock < rt.exhaust_end):
            incoming *= 1 - ex_dr
            step_labels.append(rt.sim.summoner_label)
            step_notes.append(
                f"summoner:{rt.sim.summoner_exhaust.id} ({rt.sim.summoner_exhaust.name} "
                f"-{format_number(ex_dr * 100)}% {hit.damage_type.value}, "
                f"-{format_number(ex_slow * 100)}% slow for {format_number(ex_dur)} s)"
            )

    # Defender active ability percent damage reduction (e.g. Alistar R, Garen W, Yi W)
    if rt.active_percent_dr and incoming > 0 and rt.health > 0 and hit.damage_type is not None:
        for end_t, dt_filter, frac, src, lbl in rt.active_percent_dr:
            if end_t is not None and rt.clock >= end_t:
                continue
            if dt_filter is not None and hit.damage_type is not dt_filter:
                continue
            if hit.damage_type is DamageType.TRUE and dt_filter is None:
                continue
            incoming *= 1 - frac
            step_labels.append(lbl)
            step_notes.append(f"{src} (-{format_number(frac * 100)}% {hit.damage_type.value})")

    # Champion passive percent damage-taken modifiers (e.g. Kassadin -10%, Malzahar -90%)
    if incoming > 0 and rt.health > 0 and hit.damage_type is not None:
        for p_dr in rt.sim.passive_dr_specs:
            if p_dr.mode != "percent":
                continue
            if p_dr.damage_type is not None and hit.damage_type is not p_dr.damage_type:
                continue
            if hit.damage_type is DamageType.TRUE and p_dr.damage_type is None:
                continue
            p_cd = _effect_cooldown(p_dr, rt.sim.sheet.level)
            if p_cd is not None:
                can_dr = (
                    (p_dr.id not in rt.passive_dr_used)
                    if not rt.sim.timeline
                    else (rt.clock >= rt.passive_dr_ready.get(p_dr.id, Fraction(0)))
                )
                if not can_dr:
                    continue
                rt.passive_dr_used.add(p_dr.id)
                if rt.sim.timeline:
                    rt.passive_dr_ready[p_dr.id] = rt.clock + p_cd
            pct_res = evaluate_formula(
                p_dr.formula, rt.sim.stats_env, level=rt.sim.sheet.level, ops=ABILITY_OPS
            )
            assert pct_res.exact is not None
            frac = pct_res.exact / 100 if pct_res.exact > 1 else pct_res.exact
            incoming *= 1 - frac
            step_labels.append(p_dr.label)
            step_notes.append(
                f"passive P {p_dr.name} (-{format_number(frac * 100)}% {hit.damage_type.value})"
            )

    # Timed percent damage reduction (e.g. 3869 Celestial Opposition -35%/-25% for 2 s)
    if incoming > 0 and rt.health > 0 and hit.damage_type is not None:
        for title, eff, comp, eff_label in rt.sim.timed_taken_modifiers:
            allowed = comp.get("damage_types")
            if allowed is not None and hit.damage_type.value not in allowed:
                continue
            is_active = (
                (title in rt.timed_dr_end and rt.clock < rt.timed_dr_end[title])
                if rt.sim.timeline
                else (title in rt.timed_dr_used)
            )
            if not is_active:
                can_open = (
                    (title not in rt.timed_dr_used)
                    if not rt.sim.timeline
                    else (rt.clock >= rt.timed_dr_ready.get(title, Fraction(0)))
                )
                if can_open:
                    rt.timed_dr_used.add(title)
                    is_active = True
                    if rt.sim.timeline:
                        dur = Fraction(str(eff["duration_seconds"]))
                        rt.timed_dr_end[title] = rt.clock + dur
                        if eff.get("cooldown_seconds"):
                            rt.timed_dr_ready[title] = rt.clock + scale_item_cooldown(
                                Fraction(str(eff["cooldown_seconds"])), rt.sim.item_haste
                            )
            if is_active:
                pct = evaluate_formula(
                    comp.get("formula"),
                    rt.sim.stats_env,
                    holder_range=rt.sim.defender_range,
                    level=rt.sim.sheet.level,
                ).exact
                assert pct is not None
                incoming *= 1 + pct / 100
                step_labels.append(eff_label)
                step_notes.append(f"{title} {format_number(pct)}%")

    # Flat damage reduction (MEC-08): scenario flat, champion passives (Fizz), Bone Plating
    flat_red = Fraction(0)
    if rt.sim.flat_input > 0 and incoming > 0:
        applied = min(incoming, rt.sim.flat_input)
        flat_red += applied
        step_notes.append(f"flat reduction -{format_number(applied)} (scenario)")

    if incoming - flat_red > 0 and hit.damage_type is not DamageType.TRUE:
        for p_dr in rt.sim.passive_dr_specs:
            if p_dr.mode != "flat":
                continue
            if p_dr.damage_type is not None and hit.damage_type is not p_dr.damage_type:
                continue
            raw_res = evaluate_formula(
                p_dr.formula, rt.sim.stats_env, level=rt.sim.sheet.level, ops=ABILITY_OPS
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
        for title, eff, comp, eff_label in rt.sim.flat_taken_modifiers:
            src = comp.get("source")
            if src == "attack" and hit.kind not in {"attack", "crit"}:
                continue
            raw_val = abs(
                evaluate_formula(
                    comp.get("formula"),
                    rt.sim.stats_env,
                    holder_range=rt.sim.defender_range,
                    level=rt.sim.sheet.level,
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
    if rt.dream_dr_armed and hit.kind in {"attack", "crit"} and incoming - flat_red > 0:
        rt.dream_dr_armed = False
        lvl = rt.sim.sheet.level
        dm_block = Fraction(50) if lvl < 7 else Fraction(50 + 12 * (lvl - 6))
        applied = min(incoming - flat_red, dm_block)
        flat_red += applied
        step_labels.append(Label.DERIVED)
        step_notes.append(f"3870 dream-maker (blue bubble) -{format_number(applied)}")

    bone_active = (
        rt.sim.bone_rune is not None
        and rt.bone_charges > 0
        and (not rt.sim.timeline or (rt.bone_expires is not None and rt.clock <= rt.bone_expires))
    )
    if bone_active and incoming - flat_red > 0:
        assert rt.sim.bone_rune is not None
        block = linear_by_level(
            rune_value(rt.sim.bone_rune, "BlockBase"),
            rune_value(rt.sim.bone_rune, "BlockMax"),
            rt.sim.sheet.level,
        )
        applied = min(incoming - flat_red, block)
        flat_red += applied
        rt.bone_charges -= 1
        step_labels.append(rt.sim.rune_base)
        step_notes.append(
            f"rune:{rt.sim.bone_rune.id} {rt.sim.bone_rune.name} -{format_number(applied)} "
            f"({rt.bone_charges} charges left)"
        )

    # Defender active ability flat damage reduction (e.g. Leona W Eclipse)
    if rt.active_flat_dr and incoming - flat_red > 0 and hit.damage_type is not None:
        for end_t, dt_filter, flat_val, dr_cap, src, lbl in rt.active_flat_dr:
            if end_t is not None and rt.clock >= end_t:
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
    if rt.sim.stagger_effects and dmg_after_flat > 0 and rt.health > 0 and not bypass:
        for title, _, comp, eff_label in rt.sim.stagger_effects:
            allowed = comp.get("damage_types")
            if allowed is not None and hit.damage_type.value not in allowed:
                continue
            if not rt.sim.timeline:
                if not rt.stagger_noted_no_timeline:
                    rt.stagger_noted_no_timeline = True
                    rt.sim.notes.append(
                        f"{title}: defers damage over "
                        f"{format_number(Fraction(str(comp['duration_seconds'])))} s; "
                        "requires --timeline"
                    )
                    rt.sim.weakened = True
                continue
            defer_pct = evaluate_formula(
                comp.get("formula"),
                rt.sim.stats_env,
                holder_range=rt.sim.defender_range,
                level=rt.sim.sheet.level,
            ).exact
            assert defer_pct is not None
            dur = Fraction(str(comp["duration_seconds"]))
            deferred = dmg_after_flat * defer_pct / 100
            dmg_after_flat -= deferred
            rt.stagger_bleeds.append(
                _StaggerBleed(title, rt.clock + dur, deferred / dur, eff_label)
            )
            step_labels.append(eff_label)
            step_notes.append(
                f"{title} deferred {format_number(deferred)} ({format_number(defer_pct)}%) "
                f"over {format_number(dur)} s"
            )

    # 6695 Serpent's Fang (Shield Reaver): shred existing & new shields for 3 s
    sr_active_now = False
    if rt.sim.shield_reaver_rate > 0 and dmg_after_flat > 0 and rt.health > 0:
        sr_active_now = (
            (rt.shield_reaver_until is not None and rt.clock < rt.shield_reaver_until)
            if rt.sim.timeline
            else rt.shield_reaver_applied
        )
        if not sr_active_now:
            for active_s in rt.shields:
                active_s.remaining *= 1 - rt.sim.shield_reaver_rate
            rt.shield_reaver_applied = True
            sr_active_now = True
            if rt.sim.timeline:
                rt.shield_reaver_until = rt.clock + 3
            step_notes.append(
                f"6695 shield-reaver: -{format_number(rt.sim.shield_reaver_rate * 100)}% "
                "defender shields (3 s)"
            )

    return incoming, flat_red, dmg_after_flat, sr_active_now
