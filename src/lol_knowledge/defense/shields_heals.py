"""Shield stacks, Lifeline, stored-damage reactions, and defensive healing triggers."""

from __future__ import annotations

from fractions import Fraction
from typing import TYPE_CHECKING, Any

from ..damage import DamageType, format_number
from ..formula import ABILITY_OPS, evaluate_formula
from ..kit import ActiveEffectSpec
from ..passives import _effect_cooldown
from ..runes import linear_by_level, rune_value, scale_item_cooldown
from ..stats import Label, weakest
from ..summoners import barrier_duration, barrier_shield, heal_amount
from ..survival import HealEvent, ShieldEvent, scale_healing, scale_shield
from .models import IncomingHit, _ActiveShield

if TYPE_CHECKING:
    from .session import _DefenseRuntime


def apply_pre_damage_shields_and_heals(
    rt: _DefenseRuntime,
    hit: IncomingHit,
    dmg_after_flat: Fraction,
    sr_active_now: bool,
    granted: list[ShieldEvent],
    heals: list[HealEvent],
    step_labels: list[Label],
    step_notes: list[str],
    *,
    is_last: bool,
) -> None:
    """Evaluate Lifeline shields/vitality, Barrier, proactive heals, and Guardian."""
    preview_shields = [
        _ActiveShield(s.source, s.remaining, s.shield_type, s.expires_at) for s in rt.shields
    ]
    _, preview_hp_dmg = rt.sim._absorb_active(dmg_after_flat, hit.damage_type, preview_shields)
    projected_hp = max(Fraction(0), rt.health - preview_hp_dmg)

    # 1a. Lifeline shield items (Sterak, Shieldbow, Maw, Hexdrinker, Kaenic, boots)
    defender_range = rt.sim.defender_range
    for title, eff, comp, eff_label in rt.sim.lifeline_effects:
        shield_kind = str(comp.get("shield_type", "normal"))
        if shield_kind == "magic" and hit.damage_type is not DamageType.MAGIC:
            continue
        if shield_kind == "physical" and hit.damage_type is not DamageType.PHYSICAL:
            continue
        can_proc = (
            (title not in rt.lifeline_used)
            if not rt.sim.timeline
            else (rt.clock >= rt.lifeline_ready.get(title, Fraction(0)))
        )
        if not can_proc:
            continue
        threshold: Fraction | None = None
        for lim in eff.get("limits") or ():
            if lim.get("kind") == "threshold":
                threshold = Fraction(str(lim["value"])) / 100
        if threshold is None or projected_hp < threshold * rt.current_max_health:
            evaluated_sh = evaluate_formula(
                comp.get("formula"),
                rt.sim.stats_env,
                holder_range=defender_range,
                level=rt.sim.sheet.level,
            )
            raw_sh = evaluated_sh.exact
            assert raw_sh is not None
            rev_amp = rt.sim._revitalize_amp(rt.health)
            sh_amt = (
                scale_shield(raw_sh, hsp=rt.sim.hsp, revitalize_amp=rev_amp)
                * rt.sim.self_shield_amp
            )
            if sr_active_now and rt.sim.shield_reaver_rate > 0:
                sh_amt *= 1 - rt.sim.shield_reaver_rate
            dur = Fraction(str(eff["duration_seconds"])) if eff.get("duration_seconds") else None
            cd = scale_item_cooldown(
                Fraction(str(eff["cooldown_seconds"]))
                if eff.get("cooldown_seconds")
                else Fraction(90),
                rt.sim.item_haste,
            )
            rt.lifeline_used.add(title)
            if rt.sim.timeline:
                rt.lifeline_ready[title] = rt.clock + cd
            sh_notes = [
                f"triggered before dropping below {format_number(threshold * 100)}% HP"
                if threshold is not None
                else f"triggered on taking {shield_kind} damage"
            ]
            if rt.sim.hsp:
                sh_notes.append(f"heal & shield power +{format_number(rt.sim.hsp * 100)}%")
            if rev_amp:
                sh_notes.append(f"Revitalize <40% HP +{format_number(rev_amp * 100)}%")
            if rt.sim.self_shield_amp != 1:
                sh_notes.extend(n for n in rt.sim.self_amp_notes if "shielding" in n)
            if dur is not None:
                sh_notes.append(
                    f"lasts {format_number(dur)} s (decay curve not modelled)"
                    if title.startswith("3053 ")
                    else f"lasts {format_number(dur)} s"
                )
            dep_labels = [
                rt.sim.stat_origin[k][1]
                for k in evaluated_sh.dependencies
                if k in rt.sim.stat_origin
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
                        rt.sim.sheet["health"].label,
                        *dep_labels,
                        *rt.sim.self_amp_labels,
                    ]
                ),
                tuple(sh_notes),
            )
            granted.append(ev)
            rt.shields.append(
                _ActiveShield(
                    ev.source,
                    sh_amt,
                    shield_kind,
                    None if (not rt.sim.timeline or dur is None) else rt.clock + dur,
                )
            )
            step_labels.append(ev.label)
            preview_shields = [
                _ActiveShield(s.source, s.remaining, s.shield_type, s.expires_at)
                for s in rt.shields
            ]
            _, preview_hp_dmg = rt.sim._absorb_active(
                dmg_after_flat, hit.damage_type, preview_shields
            )
            projected_hp = max(Fraction(0), rt.health - preview_hp_dmg)

    # 1b. Lifeline vitality items (2525 Protoplasm Harness: temp max HP + HoT)
    for title, eff, eff_label in rt.sim.lifeline_vitality_effects:
        can_proc = (
            (title not in rt.lifeline_used)
            if not rt.sim.timeline
            else (rt.clock >= rt.lifeline_ready.get(title, Fraction(0)))
        )
        if not can_proc:
            continue
        threshold = Fraction(30, 100)
        for lim in eff.get("limits") or ():
            if lim.get("kind") == "threshold":
                threshold = Fraction(str(lim["value"])) / 100
        if projected_hp < threshold * rt.current_max_health:
            dur = Fraction(str(eff.get("duration_seconds", 5)))
            cd = Fraction(str(eff.get("cooldown_seconds", 90)))
            rt.lifeline_used.add(title)
            if rt.sim.timeline:
                rt.lifeline_ready[title] = rt.clock + cd
            for comp in eff.get("components") or ():
                ckind = comp.get("kind")
                ev_val = evaluate_formula(
                    comp.get("formula"),
                    rt.sim.stats_env,
                    holder_range=rt.sim.defender_range,
                    level=rt.sim.sheet.level,
                )
                val = ev_val.exact
                assert val is not None
                dep_lbls = [
                    rt.sim.stat_origin[k][1] for k in ev_val.dependencies if k in rt.sim.stat_origin
                ]
                c_label = weakest([eff_label, *dep_lbls, *rt.sim.self_amp_labels])
                if ckind == "stat_modifier" and comp.get("stat") == "health":
                    rt.current_max_health += val
                    rt.health += val
                    rt.proto_hp_gain = val
                    rt.proto_hp_end = rt.clock + dur if rt.sim.timeline else None
                    step_labels.append(c_label)
                    step_notes.append(
                        f"{title} granted +{format_number(val)} temporary max HP "
                        f"for {format_number(dur)} s"
                    )
                elif ckind == "healing":
                    if rt.sim.timeline:
                        rt.proto_heal_rate = val / dur
                        rt.proto_heal_end = rt.clock + dur
                        rt.proto_heal_source = f"{title} ({eff.get('name', 'Lifeline')})"
                        rt.proto_heal_label = c_label
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
                                grievous=rt.sim.grievous,
                                uses_hsp=False,
                            )
                            * rt.sim.self_heal_amp
                        )
                        gained = min(amt, max(Fraction(0), rt.current_max_health - rt.health))
                        rt.health += gained
                        heals.append(
                            HealEvent(
                                f"{title} ({eff.get('name', 'Lifeline')})",
                                val,
                                gained,
                                False,
                                rt.sim.grievous > 0,
                                c_label,
                                (f"full {format_number(dur)} s regen without --timeline",),
                            )
                        )
            projected_hp = max(Fraction(0), rt.health - preview_hp_dmg)

    # 1b. Champion passive defensive shields (Malphite, Blitzcrank, Yasuo, Rakan, etc.)
    for p_sh in rt.sim.passive_shield_specs:
        if p_sh.trigger not in {"on_taking_damage", "below_hp_percent"}:
            continue
        can_sh = (
            (p_sh.id not in rt.passive_shield_used)
            if not rt.sim.timeline
            else (rt.clock >= rt.passive_shield_ready.get(p_sh.id, Fraction(0)))
        )
        if not can_sh:
            continue
        fires = p_sh.trigger == "on_taking_damage"
        if p_sh.trigger == "below_hp_percent" and p_sh.threshold_hp_percent is not None:
            fires = projected_hp < rt.current_max_health * p_sh.threshold_hp_percent
        if not fires:
            continue
        rt.passive_shield_used.add(p_sh.id)
        cd = _effect_cooldown(p_sh, rt.sim.sheet.level)
        if rt.sim.timeline and cd is not None:
            rt.passive_shield_ready[p_sh.id] = rt.clock + cd
        sh_res = evaluate_formula(
            p_sh.formula, rt.sim.stats_env, level=rt.sim.sheet.level, ops=ABILITY_OPS
        )
        assert sh_res.exact is not None
        dep_lbls = [
            rt.sim.stat_origin[k][1] for k in sh_res.dependencies if k in rt.sim.stat_origin
        ]
        sh_label = weakest([p_sh.label, *dep_lbls, *rt.sim.self_amp_labels])
        rev_amp = rt.sim._revitalize_amp(rt.health)
        amt = (
            scale_shield(sh_res.exact, hsp=rt.sim.hsp, revitalize_amp=rev_amp)
            * rt.sim.self_shield_amp
        )
        sh_notes: list[str] = [f"passive P {p_sh.name}"]
        if rt.sim.shield_reaver_rate > 0:
            amt *= 1 - rt.sim.shield_reaver_rate
            sh_notes.append(f"Shield Reaver (-{format_number(rt.sim.shield_reaver_rate * 100)}%)")
        dur = p_sh.duration_seconds
        rt.shields.append(
            _ActiveShield(
                f"passive P {p_sh.name}",
                amt,
                p_sh.shield_type,
                rt.clock + dur if (rt.sim.timeline and dur is not None) else None,
            )
        )
        granted.append(
            ShieldEvent(
                f"kit:{rt.sim.sheet.champion.id} P {p_sh.id} ({p_sh.name})",
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
            _ActiveShield(s.source, s.remaining, s.shield_type, s.expires_at) for s in rt.shields
        ]
        _, preview_hp_dmg = rt.sim._absorb_active(dmg_after_flat, hit.damage_type, preview_shields)
        projected_hp = max(Fraction(0), rt.health - preview_hp_dmg)

    # 1c. SummonerBarrier (100..460 normal shield for 2.5 s)
    if rt.sim.summoner_barrier is not None and not rt.barrier_used:
        rt.barrier_used = True
        sp_bar = rt.sim.summoner_barrier
        raw_b = barrier_shield(sp_bar, rt.sim.sheet.level)
        rev_amp = rt.sim._revitalize_amp(rt.health)
        b_amt = scale_shield(raw_b, hsp=rt.sim.hsp, revitalize_amp=rev_amp) * rt.sim.self_shield_amp
        b_notes: list[str] = [f"{sp_bar.name} ({format_number(barrier_duration(sp_bar))} s)"]
        if rt.sim.hsp:
            b_notes.append(f"heal & shield power +{format_number(rt.sim.hsp * 100)}%")
        if rev_amp:
            b_notes.append(f"Revitalize <40% HP +{format_number(rev_amp * 100)}%")
        if sr_active_now and rt.sim.shield_reaver_rate > 0:
            b_amt *= 1 - rt.sim.shield_reaver_rate
            b_notes.append(f"Shield Reaver (-{format_number(rt.sim.shield_reaver_rate * 100)}%)")
        b_dur = barrier_duration(sp_bar)
        rt.shields.append(
            _ActiveShield(
                f"summoner:{sp_bar.id} ({sp_bar.name})",
                b_amt,
                "normal",
                rt.clock + b_dur if rt.sim.timeline else None,
            )
        )
        b_label = weakest([rt.sim.summoner_label, *rt.sim.self_amp_labels])
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
            _ActiveShield(s.source, s.remaining, s.shield_type, s.expires_at) for s in rt.shields
        ]
        _, preview_hp_dmg = rt.sim._absorb_active(dmg_after_flat, hit.damage_type, preview_shields)
        projected_hp = max(Fraction(0), rt.health - preview_hp_dmg)

    # 1d. SummonerHeal proactive before hit when already missing HP
    if rt.sim.summoner_heal is not None and not rt.heal_used and rt.health < rt.current_max_health:
        rt.heal_used = True
        sp_heal = rt.sim.summoner_heal
        raw_h = heal_amount(sp_heal, rt.sim.sheet.level, debuffed=rt.sim.summoner_heal_debuffed)
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
        h_notes = [f"{sp_heal.name} (proactive)"]
        if rt.sim.summoner_heal_debuffed:
            h_notes.append("recent Heal debuff (-50%)")
        if rt.sim.grievous > 0:
            h_notes.append("Grievous Wounds (-40%)")
        h_label = weakest([rt.sim.summoner_label, *rt.sim.self_amp_labels])
        heals.append(
            HealEvent(
                f"summoner:{sp_heal.id} ({sp_heal.name})",
                raw_h,
                gained,
                True,
                rt.sim.grievous > 0,
                h_label,
                tuple(h_notes),
            )
        )
        step_labels.append(h_label)
        projected_hp = max(Fraction(0), rt.health - preview_hp_dmg)

    # 1e. Defender active ability instant heals (proactive when already missing HP)
    if rt.active_instant_heals and rt.health < rt.current_max_health:
        remaining_instant: list[tuple[str, str, ActiveEffectSpec, int]] = []
        for h_slot, src, eff, rank in rt.active_instant_heals:
            if (
                eff.condition == "spell_blocked"
                and h_slot in rt.spell_shield_slots
                and h_slot not in rt.spell_shield_blocked_slots
            ):
                remaining_instant.append((h_slot, src, eff, rank))
                continue
            raw_h, h_lbl = rt.sim._eval_active(
                eff, rank, current_health=rt.health, current_max_health=rt.current_max_health
            )
            if raw_h <= 0:
                continue
            uses_hsp = eff.uses_hsp
            rev_amp = rt.sim._revitalize_amp(rt.health)
            h_amt = (
                scale_healing(
                    raw_h,
                    hsp=rt.sim.hsp if uses_hsp else Fraction(0),
                    revitalize_amp=rev_amp if uses_hsp else Fraction(0),
                    grievous=rt.sim.grievous,
                    uses_hsp=uses_hsp,
                )
                * rt.sim.self_heal_amp
            )
            gained = min(h_amt, max(Fraction(0), rt.current_max_health - rt.health))
            rt.health += gained
            h_notes = ["active ability heal (proactive)"]
            if rt.sim.grievous > 0:
                h_notes.append("Grievous Wounds (-40%)")
            ev_lbl = weakest([h_lbl, *rt.sim.self_amp_labels])
            heals.append(
                HealEvent(
                    src,
                    raw_h,
                    gained,
                    uses_hsp,
                    rt.sim.grievous > 0,
                    ev_lbl,
                    tuple(h_notes),
                )
            )
            step_labels.append(ev_lbl)
        rt.active_instant_heals = remaining_instant
        projected_hp = max(Fraction(0), rt.health - preview_hp_dmg)

    # 1f. Defender stored-damage shields with minimum floor before lethal/final hit
    if rt.pending_recent_shields:
        keep_pending_sh: list[tuple[str, ActiveEffectSpec, int, Fraction | None]] = []
        for src, eff, rank, dur in rt.pending_recent_shields:
            if eff.min_formula is not None and (projected_hp == 0 or is_last):
                ratio, eff_lbl = rt.sim._eval_active(
                    eff,
                    rank,
                    current_health=rt.health,
                    current_max_health=rt.current_max_health,
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
                mn, mn_lbl = rt.sim._eval_active_formula(
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
                rev_amp = rt.sim._revitalize_amp(rt.health)
                sh_amt = (
                    scale_shield(
                        raw_sh,
                        hsp=rt.sim.hsp if eff.uses_hsp else Fraction(0),
                        revitalize_amp=rev_amp if eff.uses_hsp else Fraction(0),
                    )
                    * rt.sim.self_shield_amp
                )
                sh_notes = [f"{eff.name} (stored={format_number(stored)}, min={format_number(mn)})"]
                if rt.sim.shield_reaver_rate > 0:
                    sh_amt *= 1 - rt.sim.shield_reaver_rate
                end_t = rt.clock + dur if (rt.sim.timeline and dur is not None) else None
                rt.shields.append(_ActiveShield(src, sh_amt, eff.shield_type, end_t))
                sh_lbl = weakest([eff_lbl, mn_lbl, *rt.sim.self_amp_labels])
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
        rt.pending_recent_shields = keep_pending_sh

    # 2. Guardian (8465): ally nearby + threshold (50..165 in 2.5 s) or lethal damage
    if rt.sim.guardian_rune is not None and rt.sim.guardian_ally:
        rune = rt.sim.guardian_rune
        can_guard = (
            (not rt.guardian_used_once) if not rt.sim.timeline else (rt.clock >= rt.guardian_ready)
        )
        if can_guard:
            g_win = rune_value(rune, "GuardDuration")
            if rt.sim.timeline:
                rt.guardian_window_hits = [
                    item for item in rt.guardian_window_hits if rt.clock - item[0] <= g_win
                ]
            rt.guardian_window_hits.append((rt.clock, dmg_after_flat))
            cum_dmg = sum((d for _, d in rt.guardian_window_hits), start=Fraction(0))
            g_thresh = linear_by_level(
                rune_value(rune, "ThresholdMin"),
                rune_value(rune, "ThresholdMax"),
                rt.sim.sheet.level,
            )
            if cum_dmg >= g_thresh or projected_hp == 0:
                rt.guardian_used_once = True
                rt.guardian_window_hits = []
                if rt.sim.timeline:
                    g_cd = linear_by_level(
                        rune_value(rune, "Cooldown"),
                        rune_value(rune, "CooldownMaxLevel"),
                        rt.sim.sheet.level,
                    )
                    rt.guardian_ready = rt.clock + g_cd
                ap_val = rt.sim.sheet["ability_power"].total()
                bonus_hp = rt.sim.sheet["health"].scoped("bonus")
                raw_g = (
                    linear_by_level(
                        rune_value(rune, "ShieldBase"),
                        rune_value(rune, "ShieldMax"),
                        rt.sim.sheet.level,
                    )
                    + ap_val * rune_value(rune, "APRatio")
                    + bonus_hp * rune_value(rune, "HPRatio")
                )
                rev_amp = rt.sim._revitalize_amp(rt.health)
                g_amt = scale_shield(raw_g, hsp=rt.sim.hsp, revitalize_amp=rev_amp)
                if sr_active_now and rt.sim.shield_reaver_rate > 0:
                    g_amt *= 1 - rt.sim.shield_reaver_rate
                g_dur = rune_value(rune, "ShieldDuration")
                g_notes = ["scenario: guardian_ally=1"]
                if rt.sim.hsp:
                    g_notes.append(f"heal & shield power +{format_number(rt.sim.hsp * 100)}%")
                if rev_amp:
                    g_notes.append(f"Revitalize <40% HP +{format_number(rev_amp * 100)}%")
                ev = ShieldEvent(
                    f"rune:{rune.id} {rune.key} ({rune.name})",
                    raw_g,
                    g_amt,
                    "normal",
                    g_dur,
                    weakest((rt.sim.rune_base, rt.sim.sheet["health"].label)),
                    tuple(g_notes),
                )
                granted.append(ev)
                rt.shields.append(
                    _ActiveShield(
                        ev.source,
                        g_amt,
                        "normal",
                        None if not rt.sim.timeline else rt.clock + g_dur,
                    )
                )
                step_labels.append(ev.label)


def apply_post_damage_reactions(
    rt: _DefenseRuntime,
    hit: IncomingHit,
    incoming: Fraction,
    dmg_after_flat: Fraction,
    h_before: Fraction,
    bypass: bool,
    granted: list[ShieldEvent],
    heals: list[HealEvent],
    step_labels: list[Label],
    step_notes: list[str],
) -> tuple[Fraction, Fraction]:
    """Absorb damage against active shields and trigger post-hit survival reactions."""
    # Absorb damage against active shields, then apply remainder to health
    absorbed, hp_dmg = rt.sim._absorb_active(
        dmg_after_flat, hit.damage_type, rt.shields, bypass=bypass
    )
    rt.health = max(Fraction(0), rt.health - hp_dmg)
    if rt.active_undying and h_before > 0:
        floors = [
            (flr, u_src, u_lbl)
            for end_t, flr, u_src, u_lbl in rt.active_undying
            if end_t is None or rt.clock <= end_t
        ]
        if floors:
            min_floor, u_src, u_lbl = max(floors, key=lambda item: item[0])
            if rt.health < min_floor:
                rt.health = min(h_before, min_floor)
                step_labels.append(u_lbl)
                step_notes.append(f"{u_src} undying (HP floor {format_number(min_floor)})")
    if hp_dmg > 0:
        rt.recent_damage_history.append((rt.clock, hp_dmg))
    rt.shields = rt.sim._expire_shields(rt.shields, rt.clock)

    # 3026 Guardian Angel (Rebirth): on lethal hit, 4 s stasis + revive with 50% base HP
    if rt.sim.has_guardian_angel and rt.health == 0 and h_before > 0:
        can_ga = (rt.clock >= rt.ga_ready) if rt.sim.timeline else (not rt.ga_used_once)
        if can_ga:
            rt.ga_used_once = True
            rt.stagger_bleeds.clear()
            revive_hp = rt.sim.base_health * Fraction(1, 2)
            rt.health = min(rt.current_max_health, revive_hp)
            if rt.sim.timeline:
                rt.ga_stasis_until = rt.clock + 4
                rt.ga_ready = rt.clock + 4 + scale_item_cooldown(Fraction(300), rt.sim.item_haste)
            step_labels.append(Label.OFFICIAL)
            step_notes.append(
                f"3026 rebirth: 4 s stasis, revived with {format_number(rt.health)} HP "
                "(50% base HP, 300 s CD)"
            )

    # Track last champion hit for 3083 Warmog's Heart (8 s OOC) & 6657/3803 Eternity
    if incoming > 0 or dmg_after_flat > 0:
        rt.last_champ_hit = rt.clock
        if rt.sim.has_eternity and hit.amount > 0:
            mana_gain = hit.amount * Fraction(10, 100)
            step_notes.append(
                f"eternity: restored {format_number(mana_gain)} mana (10% pre-mitigation damage)"
            )

    # 1054 Doran's Shield (Enduring Focus): 0..40 melee / 0..30 ranged over 8 s
    if rt.sim.has_dorans_shield and dmg_after_flat > 0 and rt.health > 0:
        max_reg = Fraction(30) if rt.sim.defender_range == "ranged" else Fraction(40)
        if rt.sim.aoe_dot_flag:
            max_reg *= Fraction(66, 100)
        missing_frac = (
            max(Fraction(0), rt.current_max_health - rt.health) / rt.current_max_health
            if rt.current_max_health > 0
            else Fraction(0)
        )
        total_reg = max_reg * missing_frac
        if rt.sim.timeline:
            rt.dshield_rate = total_reg / Fraction(8)
            rt.dshield_end = rt.clock + 8
        elif not rt.dshield_used_once and total_reg > 0:
            rt.dshield_used_once = True
            amt = (
                scale_healing(
                    total_reg,
                    hsp=Fraction(0),
                    revitalize_amp=Fraction(0),
                    grievous=rt.sim.grievous,
                    uses_hsp=False,
                )
                * rt.sim.self_heal_amp
            )
            missing = max(Fraction(0), rt.current_max_health - rt.health)
            gained = min(amt, missing)
            rt.health += gained
            heals.append(
                HealEvent(
                    "1054 enduring-focus (Escudo de Doran)",
                    total_reg,
                    gained,
                    False,
                    rt.sim.grievous > 0,
                    Label.DERIVED,
                    ("full 8 s regen without --timeline",),
                )
            )

    # SummonerHeal reactive after taking non-lethal damage from full HP
    if (
        rt.sim.summoner_heal is not None
        and not rt.heal_used
        and rt.health > 0
        and rt.health < rt.current_max_health
    ):
        rt.heal_used = True
        sp_heal = rt.sim.summoner_heal
        raw_h = heal_amount(sp_heal, rt.sim.sheet.level, debuffed=rt.sim.summoner_heal_debuffed)
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
        h_notes = [f"{sp_heal.name} (reactive)"]
        if rt.sim.summoner_heal_debuffed:
            h_notes.append("recent Heal debuff (-50%)")
        if rt.sim.grievous > 0:
            h_notes.append("Grievous Wounds (-40%)")
        h_label = weakest([rt.sim.summoner_label, *rt.sim.self_amp_labels])
        heals.append(
            HealEvent(
                f"summoner:{sp_heal.id} ({sp_heal.name})",
                raw_h,
                gained,
                True,
                rt.sim.grievous > 0,
                h_label,
                tuple(h_notes),
            )
        )
        step_labels.append(h_label)

    # Defender active ability instant heals (reactive after taking non-lethal damage)
    if rt.active_instant_heals and rt.health > 0 and rt.health < rt.current_max_health:
        remaining_reactive: list[tuple[str, str, ActiveEffectSpec, int]] = []
        for h_slot, src, eff, rank in rt.active_instant_heals:
            if (
                eff.condition == "spell_blocked"
                and h_slot in rt.spell_shield_slots
                and h_slot not in rt.spell_shield_blocked_slots
            ):
                remaining_reactive.append((h_slot, src, eff, rank))
                continue
            raw_h, h_lbl = rt.sim._eval_active(
                eff, rank, current_health=rt.health, current_max_health=rt.current_max_health
            )
            if raw_h <= 0:
                continue
            uses_hsp = eff.uses_hsp
            rev_amp = rt.sim._revitalize_amp(rt.health)
            h_amt = (
                scale_healing(
                    raw_h,
                    hsp=rt.sim.hsp if uses_hsp else Fraction(0),
                    revitalize_amp=rev_amp if uses_hsp else Fraction(0),
                    grievous=rt.sim.grievous,
                    uses_hsp=uses_hsp,
                )
                * rt.sim.self_heal_amp
            )
            gained = min(h_amt, max(Fraction(0), rt.current_max_health - rt.health))
            rt.health += gained
            h_notes = ["active ability heal (reactive)"]
            if rt.sim.grievous > 0:
                h_notes.append("Grievous Wounds (-40%)")
            ev_lbl = weakest([h_lbl, *rt.sim.self_amp_labels])
            heals.append(
                HealEvent(
                    src,
                    raw_h,
                    gained,
                    uses_hsp,
                    rt.sim.grievous > 0,
                    ev_lbl,
                    tuple(h_notes),
                )
            )
            step_labels.append(ev_lbl)
        rt.active_instant_heals = remaining_reactive

    # Defender stored-damage reactive shields (Sett W, TahmKench E, Mordekaiser W)
    if rt.pending_recent_shields and rt.health > 0 and rt.recent_damage_history:
        for src, eff, rank, dur in rt.pending_recent_shields:
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
            extra_lbls: list[Label] = [eff_lbl]
            if eff.min_formula is not None:
                mn, mn_lbl = rt.sim._eval_active_formula(
                    eff.min_formula,
                    rank,
                    eff.label,
                    current_health=rt.health,
                    current_max_health=rt.current_max_health,
                )
                raw_sh = max(raw_sh, mn)
                extra_lbls.append(mn_lbl)
            if eff.max_formula is not None:
                mx, mx_lbl = rt.sim._eval_active_formula(
                    eff.max_formula,
                    rank,
                    eff.label,
                    current_health=rt.health,
                    current_max_health=rt.current_max_health,
                )
                raw_sh = min(raw_sh, mx)
                extra_lbls.append(mx_lbl)
            if raw_sh <= 0:
                continue
            rev_amp = rt.sim._revitalize_amp(rt.health)
            sh_amt = (
                scale_shield(
                    raw_sh,
                    hsp=rt.sim.hsp if eff.uses_hsp else Fraction(0),
                    revitalize_amp=rev_amp if eff.uses_hsp else Fraction(0),
                )
                * rt.sim.self_shield_amp
            )
            sh_notes = [f"{eff.name} ({format_number(ratio)}% of {format_number(stored)} stored)"]
            if rt.sim.shield_reaver_rate > 0:
                sh_amt *= 1 - rt.sim.shield_reaver_rate
            end_t = rt.clock + dur if (rt.sim.timeline and dur is not None) else None
            rt.shields.append(_ActiveShield(src, sh_amt, eff.shield_type, end_t))
            sh_lbl = weakest([*extra_lbls, *rt.sim.self_amp_labels])
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
        rt.pending_recent_shields.clear()

    # Defender stored-damage reactive heals (Rengar W, DrMundo W)
    if (
        rt.pending_recent_heals
        and rt.health > 0
        and rt.health < rt.current_max_health
        and rt.recent_damage_history
    ):
        for src, eff, rank in rt.pending_recent_heals:
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
            if raw_h <= 0:
                continue
            uses_hsp = eff.uses_hsp
            rev_amp = rt.sim._revitalize_amp(rt.health)
            h_amt = (
                scale_healing(
                    raw_h,
                    hsp=rt.sim.hsp if uses_hsp else Fraction(0),
                    revitalize_amp=rev_amp if uses_hsp else Fraction(0),
                    grievous=rt.sim.grievous,
                    uses_hsp=uses_hsp,
                )
                * rt.sim.self_heal_amp
            )
            gained = min(h_amt, max(Fraction(0), rt.current_max_health - rt.health))
            rt.health += gained
            h_notes = [f"{eff.name} ({format_number(ratio)}% of {format_number(stored)} recent)"]
            if rt.sim.grievous > 0:
                h_notes.append("Grievous Wounds (-40%)")
            ev_lbl = weakest([h_lbl, *rt.sim.self_amp_labels])
            heals.append(
                HealEvent(
                    src,
                    raw_h,
                    gained,
                    uses_hsp,
                    rt.sim.grievous > 0,
                    ev_lbl,
                    tuple(h_notes),
                )
            )
            step_labels.append(ev_lbl)
        rt.pending_recent_heals.clear()

    # 8352 Time Warp Tonic immediate 40% potion restoration on first damage
    if (
        rt.sim.potion_active_flag
        and rt.potion_upfront > 0
        and not rt.potion_upfront_applied
        and rt.health > 0
        and rt.health < rt.current_max_health
    ):
        rt.potion_upfront_applied = True
        amt = (
            scale_healing(
                rt.potion_upfront,
                hsp=Fraction(0),
                revitalize_amp=Fraction(0),
                grievous=rt.sim.grievous,
                uses_hsp=False,
            )
            * rt.sim.self_heal_amp
        )
        missing = max(Fraction(0), rt.current_max_health - rt.health)
        gained = min(amt, missing)
        rt.health += gained
        heals.append(
            HealEvent(
                f"{rt.potion_source} (Time Warp Tonic instant)",
                rt.potion_upfront,
                gained,
                False,
                rt.sim.grievous > 0,
                rt.sim.rune_base,
                ("8352 Time Warp Tonic 40% upfront heal",),
            )
        )

    # 2003 / 2031 Potion without timeline (single full HoT heal on first damage)
    if (
        not rt.sim.timeline
        and rt.sim.potion_active_flag
        and not rt.potion_used_once
        and rt.potion_rate > 0
        and rt.health > 0
    ):
        rt.potion_used_once = True
        base_pot = Fraction(120) if "2003" in rt.sim.item_ids else Fraction(100)
        raw_pot = base_pot - rt.potion_upfront if rt.potion_upfront_applied else base_pot
        amt = (
            scale_healing(
                raw_pot,
                hsp=Fraction(0),
                revitalize_amp=Fraction(0),
                grievous=rt.sim.grievous,
                uses_hsp=False,
            )
            * rt.sim.self_heal_amp
        )
        missing = max(Fraction(0), rt.current_max_health - rt.health)
        gained = min(amt, missing)
        rt.health += gained
        heals.append(
            HealEvent(
                rt.potion_source,
                raw_pot,
                gained,
                False,
                rt.sim.grievous > 0,
                Label.OFFICIAL,
                ("full potion heal without --timeline",),
            )
        )

    # Start Jak'Sho combat ramp timer on first hit
    if rt.sim.combat_resist_ramps and (incoming > 0 or dmg_after_flat > 0):
        if rt.sim.timeline:
            if rt.jaksho_start is None:
                rt.jaksho_start = rt.clock
        elif not rt.jaksho_noted_no_timeline:
            rt.jaksho_noted_no_timeline = True
            rt.sim.notes.append(
                "6665 voidborn-resilience: activates after 5 s in combat (requires --timeline)"
            )
            rt.sim.weakened = True

    # Stack Force of Nature on magic damage hits
    if incoming > 0 and rt.health > 0 and hit.damage_type is not None:
        for title, eff, comp, _ in rt.sim.stacking_resist_effects:
            allowed = comp.get("damage_types")
            if allowed is not None and hit.damage_type.value not in allowed:
                continue
            req = int((eff.get("stacks") or {}).get("required", 8))
            dur = Fraction(str(eff.get("duration_seconds", 7)))
            prev = rt.fon_stacks.get(title, 0)
            new_count = min(req, prev + 1)
            rt.fon_stacks[title] = new_count
            rt.fon_last_hit[title] = rt.clock
            if new_count >= req:
                if rt.sim.timeline:
                    rt.fon_active_until[title] = rt.clock + dur
                if prev < req:
                    step_notes.append(f"{title} reached {req} stacks (activated)")

    # Trigger Bone Plating AFTER taking > 0 health damage (triggering hit not reduced!)
    if rt.sim.bone_rune is not None and hp_dmg > 0 and rt.health > 0:
        can_bone = (
            (not rt.bone_used_once)
            if not rt.sim.timeline
            else (rt.clock >= rt.bone_ready and rt.bone_charges == 0)
        )
        if can_bone:
            rt.bone_used_once = True
            rt.bone_charges = int(rune_value(rt.sim.bone_rune, "BlockCount"))
            dur = rune_value(rt.sim.bone_rune, "BlockDuration")
            rt.bone_expires = rt.clock + dur if rt.sim.timeline else None
            rt.bone_ready = rt.clock + dur + rune_value(rt.sim.bone_rune, "Cooldown")
            step_notes.append(
                f"rune:{rt.sim.bone_rune.id} {rt.sim.bone_rune.name} activated "
                f"({rt.bone_charges} charges)"
            )

    # Trigger / refresh Second Wind after taking damage (while alive)
    if rt.sim.second_wind_rune is not None and dmg_after_flat > 0 and rt.health > 0:
        rune = rt.sim.second_wind_rune
        pct = rune_value(rune, "RegenPercentMax")
        secs = rune_value(rune, "RegenSeconds")
        missing = max(Fraction(0), rt.current_max_health - rt.health)
        if rt.sim.timeline:
            rt.sw_rate = (missing * pct) / secs
            rt.sw_end = rt.clock + secs
        elif not rt.sw_used_once and missing > 0:
            rt.sw_used_once = True
            raw = missing * pct
            amt = scale_healing(
                raw,
                hsp=Fraction(0),
                revitalize_amp=Fraction(0),
                grievous=rt.sim.grievous,
                uses_hsp=False,
            )
            gained = min(amt, missing)
            rt.health += gained
            sw_notes = [f"full {format_number(secs)} s regen without --timeline"]
            if rt.sim.grievous:
                sw_notes.append("Grievous Wounds (-40%)")
            heals.append(
                HealEvent(
                    f"rune:{rune.id} {rune.key} ({rune.name})",
                    raw,
                    gained,
                    False,
                    rt.sim.grievous > 0,
                    rt.sim.rune_base,
                    tuple(sw_notes),
                )
            )

    return absorbed, hp_dmg


def accrue_continuous(
    rt: _DefenseRuntime,
    until: Fraction,
) -> tuple[list[HealEvent], Fraction, list[Label], list[str], Fraction | None]:
    """Accrue Second Wind, Protoplasm, Doran's, Warmog's, potions and bleeds."""
    if not rt.sim.timeline or until <= rt.last_accrued:
        rt.last_accrued = max(rt.last_accrued, until)
        return [], Fraction(0), [], [], None
    if rt.health <= 0:
        rt.last_accrued = until
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
        (rt.last_champ_hit + 8) if (rt.sim.has_warmogs and rt.last_champ_hit is not None) else None
    )

    t = rt.last_accrued
    while t < until and rt.health > 0:
        boundaries = [until]
        if rt.sw_end is not None and t < rt.sw_end < until:
            boundaries.append(rt.sw_end)
        if rt.proto_heal_end is not None and t < rt.proto_heal_end < until:
            boundaries.append(rt.proto_heal_end)
        if rt.proto_hp_end is not None and t < rt.proto_hp_end < until:
            boundaries.append(rt.proto_hp_end)
        if rt.dshield_end is not None and t < rt.dshield_end < until:
            boundaries.append(rt.dshield_end)
        if warmog_start is not None and t < warmog_start < until:
            boundaries.append(warmog_start)
        if rt.potion_end is not None and t < rt.potion_end < until:
            boundaries.append(rt.potion_end)
        for b in rt.stagger_bleeds:
            if t < b.end < until:
                boundaries.append(b.end)
        for h_end, _, _, _, _ in rt.active_hots:
            if t < h_end < until:
                boundaries.append(h_end)
        for hp_end, _ in rt.active_hp_buffs:
            if t < hp_end < until:
                boundaries.append(hp_end)
        t_next = min(boundaries)
        span = t_next - t

        active_bleeds = [b for b in rt.stagger_bleeds if b.end > t]
        bleed_rate = sum((b.rate for b in active_bleeds), start=Fraction(0))

        def _regen_eff(raw_rate: Fraction) -> Fraction:
            return (
                scale_healing(
                    raw_rate,
                    hsp=Fraction(0),
                    revitalize_amp=Fraction(0),
                    grievous=rt.sim.grievous,
                    uses_hsp=False,
                )
                * rt.sim.self_heal_amp
            )

        sw_active = rt.sim.second_wind_rune is not None and rt.sw_end is not None and rt.sw_end > t
        sw_eff_rate = _regen_eff(rt.sw_rate) if (sw_active and rt.sw_rate > 0) else Fraction(0)

        proto_active = (
            rt.proto_heal_end is not None and rt.proto_heal_end > t and rt.proto_heal_rate > 0
        )
        proto_eff_rate = _regen_eff(rt.proto_heal_rate) if proto_active else Fraction(0)

        ds_active = (
            rt.sim.has_dorans_shield
            and rt.dshield_end is not None
            and rt.dshield_end > t
            and rt.dshield_rate > 0
        )
        ds_eff_rate = _regen_eff(rt.dshield_rate) if ds_active else Fraction(0)

        wm_active = (
            warmog_start is not None and t >= warmog_start and rt.health < rt.current_max_health
        )
        wm_raw_rate = rt.current_max_health * Fraction(3, 100) if wm_active else Fraction(0)
        wm_eff_rate = _regen_eff(wm_raw_rate) if wm_active else Fraction(0)

        pot_active = rt.potion_end is not None and rt.potion_end > t and rt.potion_rate > 0
        pot_eff_rate = _regen_eff(rt.potion_rate) if pot_active else Fraction(0)

        rev_now = rt.sim._revitalize_amp(rt.health)
        cur_hots = [
            (
                h_raw,
                scale_healing(
                    h_raw,
                    hsp=rt.sim.hsp if h_hsp else Fraction(0),
                    revitalize_amp=rev_now if h_hsp else Fraction(0),
                    grievous=rt.sim.grievous,
                    uses_hsp=h_hsp,
                )
                * rt.sim.self_heal_amp,
                h_src,
                h_lbl,
                h_hsp,
            )
            for h_end, h_raw, h_src, h_lbl, h_hsp in rt.active_hots
            if h_end > t and h_raw > 0
        ]
        ahot_eff_rate = sum((x[1] for x in cur_hots), start=Fraction(0))

        total_eff_heal_rate = (
            sw_eff_rate + proto_eff_rate + ds_eff_rate + wm_eff_rate + pot_eff_rate + ahot_eff_rate
        )
        net_rate = total_eff_heal_rate - bleed_rate
        if net_rate < 0 and rt.health + net_rate * span <= 0:
            lethal_span = rt.health / (-net_rate)
            t_die = t + lethal_span
            if sw_active and rt.sw_rate > 0:
                sw_start_t = t if sw_start_t is None else sw_start_t
                sw_end_t = t_die
                sw_raw_total += rt.sw_rate * lethal_span
                sw_gained_total += sw_eff_rate * lethal_span
            if proto_active:
                proto_start_t = t if proto_start_t is None else proto_start_t
                proto_end_t = t_die
                proto_raw_total += rt.proto_heal_rate * lethal_span
                proto_gained_total += proto_eff_rate * lethal_span
            if ds_active:
                ds_start_t = t if ds_start_t is None else ds_start_t
                ds_end_t = t_die
                ds_raw_total += rt.dshield_rate * lethal_span
                ds_gained_total += ds_eff_rate * lethal_span
            if pot_active:
                pot_start_t = t if pot_start_t is None else pot_start_t
                pot_end_t = t_die
                pot_raw_total += rt.potion_rate * lethal_span
                pot_gained_total += pot_eff_rate * lethal_span
            if bleed_rate > 0:
                bleed_total += bleed_rate * lethal_span
                bleed_labels.extend(b.label for b in active_bleeds)
            rt.health = Fraction(0)
            died_at = t_die
            t = t_die
            break

        if bleed_rate > 0:
            bleed_total += bleed_rate * span
            bleed_labels.extend(b.label for b in active_bleeds)
        new_hp = rt.health + net_rate * span
        ratio = Fraction(1)
        if new_hp > rt.current_max_health:
            avail = max(Fraction(0), rt.current_max_health - (rt.health - bleed_rate * span))
            total_heal_eff = total_eff_heal_rate * span
            ratio = avail / total_heal_eff if total_heal_eff > 0 else Fraction(0)
            rt.health = rt.current_max_health
        else:
            rt.health = max(Fraction(0), new_hp)

        if sw_active and rt.sw_rate > 0:
            sw_start_t = t if sw_start_t is None else sw_start_t
            sw_end_t = t_next
            sw_raw_total += rt.sw_rate * span
            sw_gained_total += sw_eff_rate * span * ratio
        if proto_active:
            proto_start_t = t if proto_start_t is None else proto_start_t
            proto_end_t = t_next
            proto_raw_total += rt.proto_heal_rate * span
            proto_gained_total += proto_eff_rate * span * ratio
        if ds_active:
            ds_start_t = t if ds_start_t is None else ds_start_t
            ds_end_t = t_next
            ds_raw_total += rt.dshield_rate * span
            ds_gained_total += ds_eff_rate * span * ratio
        if wm_active:
            wm_start_t = t if wm_start_t is None else wm_start_t
            wm_end_t = t_next
            wm_raw_total += wm_raw_rate * span
            wm_gained_total += wm_eff_rate * span * ratio
        if pot_active:
            pot_start_t = t if pot_start_t is None else pot_start_t
            pot_end_t = t_next
            pot_raw_total += rt.potion_rate * span
            pot_gained_total += pot_eff_rate * span * ratio
        for h_raw, h_eff, h_src, h_lbl, h_hsp in cur_hots:
            bucket = ahot_totals.setdefault(
                h_src, [Fraction(0), Fraction(0), t, t_next, h_lbl, h_hsp]
            )
            bucket[0] += h_raw * span
            bucket[1] += h_eff * span * ratio
            bucket[3] = t_next

        t = t_next
        rt.stagger_bleeds = [b for b in rt.stagger_bleeds if b.end > t]
        rt.active_hots = [h for h in rt.active_hots if h[0] > t]
        kept_hp_buffs: list[tuple[Fraction, Fraction]] = []
        for hp_end, hp_gain in rt.active_hp_buffs:
            if hp_end <= t:
                rt.current_max_health -= hp_gain
                rt.health = min(rt.health, rt.current_max_health)
            else:
                kept_hp_buffs.append((hp_end, hp_gain))
        rt.active_hp_buffs = kept_hp_buffs
        if rt.sw_end is not None and rt.sw_end <= t:
            rt.sw_end = None
        if rt.proto_heal_end is not None and rt.proto_heal_end <= t:
            rt.proto_heal_end = None
        if rt.dshield_end is not None and rt.dshield_end <= t:
            rt.dshield_end = None
        if rt.potion_end is not None and rt.potion_end <= t:
            rt.potion_end = None
        if rt.proto_hp_end is not None and rt.proto_hp_end <= t:
            rt.current_max_health -= rt.proto_hp_gain
            rt.health = min(rt.health, rt.current_max_health)
            rt.proto_hp_gain = Fraction(0)
            rt.proto_hp_end = None

    rt.last_accrued = t
    if sw_raw_total > 0 and rt.sim.second_wind_rune is not None:
        rune = rt.sim.second_wind_rune
        assert sw_start_t is not None and sw_end_t is not None
        sw_notes = [f"regen {format_number(sw_start_t)}–{format_number(sw_end_t)} s"]
        if rt.sim.grievous:
            sw_notes.append("Grievous Wounds (-40%)")
        heals_out.append(
            HealEvent(
                f"rune:{rune.id} {rune.key} ({rune.name})",
                sw_raw_total,
                sw_gained_total,
                False,
                rt.sim.grievous > 0,
                rt.sim.rune_base,
                tuple(sw_notes),
            )
        )
    if proto_raw_total > 0:
        assert proto_start_t is not None and proto_end_t is not None
        p_notes = [f"regen {format_number(proto_start_t)}–{format_number(proto_end_t)} s"]
        if rt.sim.grievous:
            p_notes.append("Grievous Wounds (-40%)")
        heals_out.append(
            HealEvent(
                rt.proto_heal_source,
                proto_raw_total,
                proto_gained_total,
                False,
                rt.sim.grievous > 0,
                rt.proto_heal_label,
                tuple(p_notes),
            )
        )
    if ds_raw_total > 0:
        assert ds_start_t is not None and ds_end_t is not None
        ds_notes = [f"regen {format_number(ds_start_t)}–{format_number(ds_end_t)} s"]
        if rt.sim.grievous:
            ds_notes.append("Grievous Wounds (-40%)")
        heals_out.append(
            HealEvent(
                "1054 enduring-focus (Escudo de Doran)",
                ds_raw_total,
                ds_gained_total,
                False,
                rt.sim.grievous > 0,
                Label.DERIVED,
                tuple(ds_notes),
            )
        )
    if wm_raw_total > 0:
        assert wm_start_t is not None and wm_end_t is not None
        wm_notes = [f"OOC >=8 s regen {format_number(wm_start_t)}–{format_number(wm_end_t)} s"]
        if rt.sim.grievous:
            wm_notes.append("Grievous Wounds (-40%)")
        heals_out.append(
            HealEvent(
                "3083 warmogs-heart (Corazón de Warmog)",
                wm_raw_total,
                wm_gained_total,
                False,
                rt.sim.grievous > 0,
                Label.DERIVED,
                tuple(wm_notes),
            )
        )
    if pot_raw_total > 0:
        assert pot_start_t is not None and pot_end_t is not None
        pt_notes = [f"regen {format_number(pot_start_t)}–{format_number(pot_end_t)} s"]
        if rt.sim.grievous:
            pt_notes.append("Grievous Wounds (-40%)")
        heals_out.append(
            HealEvent(
                rt.potion_source,
                pot_raw_total,
                pot_gained_total,
                False,
                rt.sim.grievous > 0,
                Label.OFFICIAL,
                tuple(pt_notes),
            )
        )
    for h_src, (h_raw_tot, h_gained_tot, h_st, h_en, h_lbl, h_hsp) in ahot_totals.items():
        if h_raw_tot <= 0:
            continue
        ah_notes = [f"regen {format_number(h_st)}–{format_number(h_en)} s"]
        if rt.sim.grievous:
            ah_notes.append("Grievous Wounds (-40%)")
        heals_out.append(
            HealEvent(
                h_src,
                h_raw_tot,
                h_gained_tot,
                h_hsp,
                rt.sim.grievous > 0,
                h_lbl,
                tuple(ah_notes),
            )
        )
    if bleed_total > 0:
        bleed_notes.append(f"Death's Dance stagger bleed: {format_number(bleed_total)} true damage")
    return heals_out, bleed_total, bleed_labels, bleed_notes, died_at
