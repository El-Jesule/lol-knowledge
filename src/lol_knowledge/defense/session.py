"""Defense session runtime, continuous accrual, hit processing, and entrypoints."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

from ..damage import DamageType, format_number, mitigate
from ..errors import RotationError, StatsError
from ..formula import ABILITY_OPS, FormulaError, evaluate_formula
from ..kit import (
    CC_BLINDS_ATTACKS,
    CC_BLOCKS_ABILITIES,
    CC_BLOCKS_ATTACKS,
    ActiveEffectSpec,
    Kit,
    sheet_stats,
)
from ..passives import passive_defense_specs
from ..runes import Rune, RuneData, int_input, rune_value
from ..scenario import Target
from ..stats import EVIDENCE_LABEL, Label, StatBlocked, StatSheet, weakest
from ..summoners import SummonerSpellData, SummonerSpellSpec, cleanse_tenacity, resolve_loadout
from ..survival import (
    GRIEVOUS_WOUNDS_REDUCTION,
    HealEvent,
    ShieldEvent,
    absorb_shield,
    scale_healing,
    scale_shield,
    validate_shield_type,
)
from .cc_negations import (
    activate_ability_cast,
    activate_summoner,
    apply_cc,
    apply_damage_reductions,
    check_hit_negations,
    cleanse_cc,
    effective_resists,
)
from .models import (
    DefenseOutcome,
    DefenseSession,
    DefenseState,
    DefenseStep,
    IncomingHit,
    _ActiveShield,
    _CCLock,
    _StaggerBleed,
)
from .shields_heals import (
    accrue_continuous,
    apply_post_damage_reactions,
    apply_pre_damage_shields_and_heals,
)


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
        shields: list[_ActiveShield] = []
        if self.start_shield > 0:
            shields.append(
                _ActiveShield("initial shield", self.start_shield, self.shield_type, None)
            )
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

        rt = _DefenseRuntime(
            sim=self,
            health=self.start_health,
            current_max_health=self.max_health,
            shields=shields,
            base_grievous=self.grievous,
            base_sr_rate=self.shield_reaver_rate,
            potion_end=potion_end,
            potion_rate=potion_rate,
            potion_source=potion_source,
            potion_upfront=potion_upfront,
            dream_dr_armed=self.dream_maker_active,
        )
        return DefenseSession(
            snapshot_state=lambda: snapshot_state(rt),
            effective_resists=lambda at: effective_resists(rt, at),
            target_snapshot=lambda at: target_snapshot(rt, at),
            accrue_to=lambda until: accrue_to(rt, until),
            process_hit=lambda hit, *, is_last=False: process_hit(rt, hit, is_last=is_last),
            activate_ability_cast=lambda slot, rank, case_id, at: activate_ability_cast(
                rt, slot, rank, case_id, at
            ),
            activate_summoner=lambda sp, at: activate_summoner(rt, sp, at),
            apply_self_survival=lambda in_heals, in_shields, at: apply_self_survival(
                rt, in_heals, in_shields, at
            ),
            apply_health_cost=lambda amount: apply_health_cost(rt, amount),
            set_grievous_until=lambda until: set_grievous_until(rt, until),
            set_shield_reaver=lambda rate, until: set_shield_reaver(rt, rate, until),
            apply_cc=lambda cc, base_duration, at, *, blocked_by_spell_shield=False: apply_cc(
                rt, cc, base_duration, at, blocked_by_spell_shield=blocked_by_spell_shield
            ),
            cleanse_cc=lambda *, qss=False, at: cleanse_cc(rt, qss=qss, at=at),
            next_event_time=lambda after, limit: next_event_time(rt, after, limit),
            flush_tail=lambda: flush_tail(rt),
            outcome=lambda enemy_description: outcome(rt, enemy_description),
        )

    def run(self, hits: Sequence[IncomingHit], enemy_description: str) -> DefenseOutcome:
        if not hits:
            raise RotationError("defense simulation needs at least one incoming hit")
        session = self.open_session()
        for idx, hit in enumerate(hits, start=1):
            session.process_hit(hit, is_last=(idx == len(hits)))
        session.flush_tail()
        return session.outcome(enemy_description)


@dataclass
class _DefenseRuntime:
    """Mutable state container for one ``DefenseSession``."""

    sim: _DefenseSimulator
    health: Fraction
    current_max_health: Fraction
    shields: list[_ActiveShield] = field(default_factory=list)
    clock: Fraction = Fraction(0)
    steps: list[DefenseStep] = field(default_factory=list)
    base_grievous: Fraction = Fraction(0)
    dynamic_grievous_until: Fraction | None = None
    base_sr_rate: Fraction = Fraction(0)
    dynamic_sr_rate: Fraction = Fraction(0)
    dynamic_sr_until: Fraction | None = None
    bone_charges: int = 0
    bone_expires: Fraction | None = None
    bone_ready: Fraction = Fraction(0)
    bone_used_once: bool = False
    exhaust_used: bool = False
    exhaust_end: Fraction | None = None
    barrier_used: bool = False
    heal_used: bool = False
    active_cast_triggered: bool = False
    active_resist_buffs: list[tuple[Fraction | None, str, str, Fraction, str, Label]] = field(
        default_factory=list
    )
    active_hp_buffs: list[tuple[Fraction, Fraction]] = field(default_factory=list)
    active_percent_dr: list[tuple[Fraction | None, DamageType | None, Fraction, str, Label]] = (
        field(default_factory=list)
    )
    active_flat_dr: list[
        tuple[Fraction | None, DamageType | None, Fraction, Fraction | None, str, Label]
    ] = field(default_factory=list)
    active_instant_heals: list[tuple[str, str, ActiveEffectSpec, int]] = field(default_factory=list)
    active_hots: list[tuple[Fraction, Fraction, str, Label, bool]] = field(default_factory=list)
    active_dodge_ends: list[tuple[Fraction | None, str, Label]] = field(default_factory=list)
    active_spell_shields: list[list[Any]] = field(default_factory=list)
    active_first_hit_blocks: list[list[Any]] = field(default_factory=list)
    active_invuln_ends: list[tuple[Fraction | None, str, Label]] = field(default_factory=list)
    active_undying: list[tuple[Fraction | None, Fraction, str, Label]] = field(default_factory=list)
    pending_recent_heals: list[tuple[str, ActiveEffectSpec, int]] = field(default_factory=list)
    pending_recent_shields: list[tuple[str, ActiveEffectSpec, int, Fraction | None]] = field(
        default_factory=list
    )
    recent_damage_history: list[tuple[Fraction, Fraction]] = field(default_factory=list)
    spell_shield_slots: set[str] = field(default_factory=set)
    spell_shield_blocked_slots: set[str] = field(default_factory=set)
    sw_end: Fraction | None = None
    sw_rate: Fraction = Fraction(0)
    sw_used_once: bool = False
    proto_heal_end: Fraction | None = None
    proto_heal_rate: Fraction = Fraction(0)
    proto_heal_source: str = ""
    proto_heal_label: Label = Label.DERIVED
    proto_hp_end: Fraction | None = None
    proto_hp_gain: Fraction = Fraction(0)
    stagger_bleeds: list[_StaggerBleed] = field(default_factory=list)
    last_accrued: Fraction = Fraction(0)
    guardian_ready: Fraction = Fraction(0)
    guardian_used_once: bool = False
    guardian_window_hits: list[tuple[Fraction, Fraction]] = field(default_factory=list)
    lifeline_ready: dict[str, Fraction] = field(default_factory=dict)
    lifeline_used: set[str] = field(default_factory=set)
    passive_shield_ready: dict[str, Fraction] = field(default_factory=dict)
    passive_shield_used: set[str] = field(default_factory=set)
    passive_dr_ready: dict[str, Fraction] = field(default_factory=dict)
    passive_dr_used: set[str] = field(default_factory=set)
    spell_shield_ready: dict[str, Fraction] = field(default_factory=dict)
    spell_shield_used: set[str] = field(default_factory=set)
    timed_dr_end: dict[str, Fraction] = field(default_factory=dict)
    timed_dr_ready: dict[str, Fraction] = field(default_factory=dict)
    timed_dr_used: set[str] = field(default_factory=set)
    jaksho_start: Fraction | None = None
    jaksho_noted_no_timeline: bool = False
    dshield_end: Fraction | None = None
    dshield_rate: Fraction = Fraction(0)
    dshield_used_once: bool = False
    last_champ_hit: Fraction | None = None
    ga_ready: Fraction = Fraction(0)
    ga_used_once: bool = False
    ga_stasis_until: Fraction | None = None
    shield_reaver_until: Fraction | None = None
    shield_reaver_applied: bool = False
    potion_end: Fraction | None = None
    potion_rate: Fraction = Fraction(0)
    potion_source: str = ""
    potion_upfront: Fraction = Fraction(0)
    potion_used_once: bool = False
    potion_upfront_applied: bool = False
    dream_dr_armed: bool = False
    knights_vow_applied: bool = False
    fon_stacks: dict[str, int] = field(default_factory=dict)
    fon_last_hit: dict[str, Fraction] = field(default_factory=dict)
    fon_active_until: dict[str, Fraction] = field(default_factory=dict)
    stagger_noted_no_timeline: bool = False
    cc_locks: list[_CCLock] = field(default_factory=list)
    cc_immune_windows: list[tuple[Fraction | None, bool, str, Label]] = field(default_factory=list)
    cleanse_tenacity_until: Fraction | None = None
    cleanse_tenacity_val: Fraction = Fraction(0)
    unflinching_cc_until: Fraction | None = None

    def sync_dynamic_debuffs(self, at: Fraction) -> None:
        if self.base_grievous > 0 or (
            self.dynamic_grievous_until is not None and at < self.dynamic_grievous_until
        ):
            self.sim.grievous = GRIEVOUS_WOUNDS_REDUCTION
        else:
            self.sim.grievous = Fraction(0)
        if self.dynamic_sr_until is not None and at < self.dynamic_sr_until:
            self.sim.shield_reaver_rate = max(self.base_sr_rate, self.dynamic_sr_rate)
        else:
            self.sim.shield_reaver_rate = self.base_sr_rate


def process_hit(rt: _DefenseRuntime, hit: IncomingHit, *, is_last: bool = False) -> DefenseStep:
    """Process one incoming hit or wait interval and append a ``DefenseStep``."""
    rt.sync_dynamic_debuffs(hit.time if (rt.sim.timeline and hit.time is not None) else rt.clock)
    if hit.wait is not None:
        if not rt.sim.timeline:
            raise RotationError(f"wait step {hit.source!r} requires --timeline")
        h_before = rt.health
        s_before = rt.sim._shield_total(rt.shields)
        target_clock = rt.clock + hit.wait
        sw_heals, bleed_dmg, bleed_labels, bleed_notes, died_at = accrue_continuous(
            rt, target_clock
        )
        rt.clock = died_at if died_at is not None else target_clock
        rt.shields = rt.sim._expire_shields(rt.shields, rt.clock)
        wait_labels: list[Label] = []
        if sw_heals:
            wait_labels.extend(h.label for h in sw_heals)
        if bleed_labels:
            wait_labels.extend(bleed_labels)
        rt.steps.append(
            DefenseStep(
                len(rt.steps) + 1,
                hit.source,
                "bleed" if died_at is not None else "wait",
                DamageType.TRUE if bleed_dmg > 0 else None,
                rt.clock,
                bleed_dmg,
                Fraction(0),
                bleed_dmg,
                Fraction(0),
                bleed_dmg,
                h_before,
                rt.health,
                s_before,
                rt.sim._shield_total(rt.shields),
                heals=tuple(sw_heals),
                label=weakest(wait_labels) if wait_labels else Label.OFFICIAL,
                notes=tuple(bleed_notes),
            )
        )
        return rt.steps[-1]

    if rt.sim.timeline and hit.time is not None:
        rt.clock = max(rt.clock, hit.time)
    rt.shields = rt.sim._expire_shields(rt.shields, rt.clock)
    pre_h = rt.health
    pre_s = rt.sim._shield_total(rt.shields)
    sw_heals, bleed_dmg, bleed_labels, bleed_notes, died_at = accrue_continuous(rt, rt.clock)
    if bleed_dmg > 0:
        bleed_t = died_at if died_at is not None else rt.clock
        rt.steps.append(
            DefenseStep(
                len(rt.steps) + 1,
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
                rt.health,
                pre_s,
                rt.sim._shield_total(rt.shields),
                heals=tuple(sw_heals),
                label=weakest([*bleed_labels, *(h.label for h in sw_heals)]),
                notes=tuple(bleed_notes),
            )
        )
        sw_heals = []

    h_before = rt.health
    s_before = rt.sim._shield_total(rt.shields)
    step_notes: list[str] = []
    step_labels: list[Label] = [rt.sim.sheet["health"].label]
    granted: list[ShieldEvent] = []
    heals: list[HealEvent] = list(sw_heals)

    # Expire Force of Nature stacks/buff if window elapsed in timeline
    if rt.sim.timeline:
        for title, eff, _, _ in rt.sim.stacking_resist_effects:
            if title in rt.fon_active_until and rt.clock >= rt.fon_active_until[title]:
                del rt.fon_active_until[title]
                rt.fon_stacks[title] = 0
            elif title in rt.fon_last_hit:
                win = Fraction(str((eff.get("stacks") or {}).get("window_seconds", 7)))
                if rt.clock - rt.fon_last_hit[title] >= win:
                    rt.fon_stacks[title] = 0

    # Stasis immunity from 3026 Guardian Angel Rebirth (4 s)
    if rt.sim.timeline and rt.ga_stasis_until is not None and rt.clock < rt.ga_stasis_until:
        rt.steps.append(
            DefenseStep(
                len(rt.steps) + 1,
                hit.source,
                hit.kind,
                hit.damage_type,
                rt.clock,
                Fraction(0),
                Fraction(0),
                Fraction(0),
                Fraction(0),
                Fraction(0),
                h_before,
                rt.health,
                s_before,
                rt.sim._shield_total(rt.shields),
                (),
                tuple(heals),
                Fraction(0),
                Label.OFFICIAL,
                ("3026 rebirth: invulnerable during 4 s stasis",),
            )
        )
        return rt.steps[-1]

    # 3109 Knight's Vow: redirect 14% of worthy ally's damage taken when >30% HP
    if (
        rt.sim.has_knights_vow
        and not rt.knights_vow_applied
        and rt.sim.worthy_ally_taken > 0
        and rt.health > rt.current_max_health * Fraction(3, 10)
    ):
        rt.knights_vow_applied = True
        redir = rt.sim.worthy_ally_taken * Fraction(14, 100)
        rt.health = max(Fraction(0), rt.health - redir)
        step_notes.append(
            f"3109 sacrifice: redirected {format_number(redir)} true damage (14% of "
            f"worthy ally {format_number(rt.sim.worthy_ally_taken)})"
        )
        step_labels.append(Label.OFFICIAL)

    # 8352 Time Warp Tonic: if potion is popped while already injured, heal 40% upfront
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

    spell_blocked = check_hit_negations(rt, hit, granted, step_labels, step_notes)
    cur_armor, cur_mr, res_labels, res_notes = effective_resists(rt, rt.clock)
    if spell_blocked:
        incoming = Fraction(0)
    elif hit.already_mitigated:
        incoming = hit.amount
        step_labels.append(hit.label)
        if (
            not hit.resistances_already_live
            and hit.damage_type is DamageType.PHYSICAL
            and cur_armor > rt.sim.armor
            and rt.sim.armor >= 0
        ):
            incoming = incoming * (100 + rt.sim.armor) / (100 + cur_armor)
            step_labels.extend([*res_labels, Label.PENDING])
            step_notes.extend(
                [
                    *res_notes,
                    "pre-mitigated enemy hit rescaled for dynamic armor without enemy penetration",
                ]
            )
        elif (
            not hit.resistances_already_live
            and hit.damage_type is DamageType.MAGIC
            and cur_mr > rt.sim.magic_resist
            and rt.sim.magic_resist >= 0
        ):
            incoming = incoming * (100 + rt.sim.magic_resist) / (100 + cur_mr)
            step_labels.extend([*res_labels, Label.PENDING])
            step_notes.extend(
                [
                    *res_notes,
                    "pre-mitigated enemy hit rescaled for dynamic MR without enemy penetration",
                ]
            )
    else:
        incoming, mit_labels, mit_notes = rt.sim._mitigate_manual(hit, cur_armor, cur_mr)
        step_labels.extend([*mit_labels, *res_labels])
        step_notes.extend([*mit_notes, *res_notes])
    incoming, flat_red, dmg_after_flat, sr_active_now = apply_damage_reductions(
        rt, hit, incoming, step_labels, step_notes
    )
    bypass = hit.kind == "execute"
    assert hit.damage_type is not None
    if rt.health > 0 and dmg_after_flat > 0 and not bypass:
        apply_pre_damage_shields_and_heals(
            rt,
            hit,
            dmg_after_flat,
            sr_active_now,
            granted,
            heals,
            step_labels,
            step_notes,
            is_last=is_last,
        )
    absorbed, hp_dmg = apply_post_damage_reactions(
        rt,
        hit,
        incoming,
        dmg_after_flat,
        h_before,
        bypass,
        granted,
        heals,
        step_labels,
        step_notes,
    )
    reactive, react_notes = rt.sim._reactive_reflect(hit)
    step_notes.extend(react_notes)

    rt.steps.append(
        DefenseStep(
            len(rt.steps) + 1,
            hit.source,
            hit.kind,
            hit.damage_type,
            None if not rt.sim.timeline else rt.clock,
            incoming,
            flat_red,
            dmg_after_flat,
            absorbed,
            hp_dmg,
            h_before,
            rt.health,
            s_before,
            rt.sim._shield_total(rt.shields),
            tuple(granted),
            tuple(heals),
            reactive,
            weakest(step_labels),
            tuple(step_notes),
        )
    )
    return rt.steps[-1]


def flush_tail(rt: _DefenseRuntime) -> None:
    # Final continuous tail (bleeds, Second Wind, Protoplasm, Doran's, Potions) in timeline
    if rt.sim.timeline and rt.health > 0:
        tail_ends = [b.end for b in rt.stagger_bleeds]
        if rt.sw_end is not None:
            tail_ends.append(rt.sw_end)
        if rt.proto_heal_end is not None:
            tail_ends.append(rt.proto_heal_end)
        if rt.proto_hp_end is not None:
            tail_ends.append(rt.proto_hp_end)
        if rt.dshield_end is not None:
            tail_ends.append(rt.dshield_end)
        if rt.potion_end is not None:
            tail_ends.append(rt.potion_end)
        tail_end = max(tail_ends, default=rt.clock)
        if tail_end > rt.clock:
            rt.sync_dynamic_debuffs(tail_end)
            h_before = rt.health
            s_before = rt.sim._shield_total(rt.shields)
            tail_heals, tail_bleed, tail_b_labels, tail_b_notes, died_at = accrue_continuous(
                rt, tail_end
            )
            rt.clock = died_at if died_at is not None else tail_end
            rt.shields = rt.sim._expire_shields(rt.shields, rt.clock)
            if tail_heals or tail_bleed > 0:
                t_labels = [*tail_b_labels, *(h.label for h in tail_heals)]
                t_kind = "bleed" if tail_bleed > 0 else "regen"
                t_src = (
                    f"Death's Dance bleed until {format_number(rt.clock)} s"
                    if tail_bleed > 0 and not tail_heals
                    else (
                        f"Second Wind regen until {format_number(rt.clock)} s"
                        if tail_bleed == 0 and rt.sim.second_wind_rune is not None
                        else f"bleed & regen until {format_number(rt.clock)} s"
                    )
                )
                rt.steps.append(
                    DefenseStep(
                        len(rt.steps) + 1,
                        t_src,
                        t_kind,
                        DamageType.TRUE if tail_bleed > 0 else None,
                        rt.clock,
                        tail_bleed,
                        Fraction(0),
                        tail_bleed,
                        Fraction(0),
                        tail_bleed,
                        h_before,
                        rt.health,
                        s_before,
                        rt.sim._shield_total(rt.shields),
                        heals=tuple(tail_heals),
                        label=weakest(t_labels) if t_labels else Label.DERIVED,
                        notes=tuple(tail_b_notes),
                    )
                )


def snapshot_state(rt: _DefenseRuntime) -> DefenseState:
    atk_locks = [c.end for c in rt.cc_locks if c.kind in CC_BLOCKS_ATTACKS and c.end > rt.clock]
    ab_locks = [c.end for c in rt.cc_locks if c.kind in CC_BLOCKS_ABILITIES and c.end > rt.clock]
    sup_locks = [c.end for c in rt.cc_locks if c.kind == "suppression" and c.end > rt.clock]
    bld_locks = [c.end for c in rt.cc_locks if c.kind in CC_BLINDS_ATTACKS and c.end > rt.clock]
    return DefenseState(
        health=rt.health,
        max_health=rt.current_max_health,
        shield=rt.sim._shield_total(rt.shields),
        clock=rt.clock,
        stasis_until=rt.ga_stasis_until,
        grievous_active=bool(
            rt.base_grievous > 0
            or (rt.dynamic_grievous_until is not None and rt.clock < rt.dynamic_grievous_until)
        ),
        step_count=len(rt.steps),
        attacks_locked_until=max(atk_locks) if atk_locks else None,
        abilities_locked_until=max(ab_locks) if ab_locks else None,
        suppressed_until=max(sup_locks) if sup_locks else None,
        blinded_until=max(bld_locks) if bld_locks else None,
    )


def target_snapshot(rt: _DefenseRuntime, at: Fraction) -> Target:
    cur_ar, cur_mr, r_lbls, _ = effective_resists(rt, at)
    bonus_hp = max(Fraction(0), rt.current_max_health - rt.sim.base_health)
    t_stats = {
        "max_health": rt.current_max_health,
        "current_health": rt.health,
        "bonus_health": bonus_hp,
    }
    t_lbl = weakest(
        [
            rt.sim.sheet["armor"].label,
            rt.sim.sheet["magic_resist"].label,
            rt.sim.sheet["health"].label,
            *r_lbls,
        ]
    )
    return Target(
        armor=cur_ar,
        magic_resist=cur_mr,
        stats=t_stats,
        label=t_lbl,
        description=f"{rt.sim.sheet.champion.name} (live duel state)",
        kind="champion",
        items=rt.sim.sheet.items,
        shield=rt.sim._shield_total(rt.shields),
        shield_type="normal",
        runes=(),
        level=rt.sim.sheet.level,
    )


def accrue_to(
    rt: _DefenseRuntime,
    until: Fraction,
) -> tuple[list[HealEvent], Fraction, list[Label], list[str], Fraction | None]:
    rt.sync_dynamic_debuffs(until)
    heals_out, bleed_dmg, b_lbls, b_notes, died_at = accrue_continuous(rt, until)
    rt.clock = died_at if died_at is not None else max(rt.clock, until)
    rt.shields = rt.sim._expire_shields(rt.shields, rt.clock)
    return heals_out, bleed_dmg, b_lbls, b_notes, died_at


def apply_self_survival(
    rt: _DefenseRuntime,
    in_heals: Sequence[HealEvent],
    in_shields: Sequence[ShieldEvent],
    at: Fraction,
) -> tuple[Fraction, Fraction, list[HealEvent], list[ShieldEvent]]:
    if rt.health <= 0:
        return Fraction(0), Fraction(0), [], []
    rt.clock = max(rt.clock, at)
    rt.sync_dynamic_debuffs(rt.clock)
    rt.shields = rt.sim._expire_shields(rt.shields, rt.clock)
    healed_total = Fraction(0)
    shielded_total = Fraction(0)
    out_heals: list[HealEvent] = []
    out_shields: list[ShieldEvent] = []
    for h_ev in in_heals:
        if h_ev.raw <= 0:
            continue
        rev_amp = rt.sim._revitalize_amp(rt.health)
        h_amt = (
            scale_healing(
                h_ev.raw,
                hsp=rt.sim.hsp if h_ev.uses_hsp else Fraction(0),
                revitalize_amp=rev_amp if h_ev.uses_hsp else Fraction(0),
                grievous=rt.sim.grievous,
                uses_hsp=h_ev.uses_hsp,
            )
            * rt.sim.self_heal_amp
        )
        gained = min(h_amt, max(Fraction(0), rt.current_max_health - rt.health))
        rt.health += gained
        healed_total += gained
        h_notes = list(h_ev.notes)
        if rt.sim.grievous > 0 and not any("Grievous" in n for n in h_notes):
            h_notes.append("Grievous Wounds (-40%)")
        out_heals.append(
            HealEvent(
                h_ev.source,
                h_ev.raw,
                gained,
                h_ev.uses_hsp,
                rt.sim.grievous > 0,
                weakest([h_ev.label, *rt.sim.self_amp_labels]),
                tuple(h_notes),
            )
        )
    for s_ev in in_shields:
        if s_ev.raw <= 0:
            continue
        rev_amp = rt.sim._revitalize_amp(rt.health)
        sh_amt = (
            scale_shield(s_ev.raw, hsp=rt.sim.hsp, revitalize_amp=rev_amp) * rt.sim.self_shield_amp
        )
        s_notes = list(s_ev.notes)
        if rt.sim.shield_reaver_rate > 0:
            sh_amt *= 1 - rt.sim.shield_reaver_rate
            s_notes.append(f"Shield Reaver (-{format_number(rt.sim.shield_reaver_rate * 100)}%)")
        end_t = (
            rt.clock + s_ev.duration if (rt.sim.timeline and s_ev.duration is not None) else None
        )
        rt.shields.append(_ActiveShield(s_ev.source, sh_amt, s_ev.shield_type, end_t))
        shielded_total += sh_amt
        out_shields.append(
            ShieldEvent(
                s_ev.source,
                s_ev.raw,
                sh_amt,
                s_ev.shield_type,
                s_ev.duration,
                weakest([s_ev.label, *rt.sim.self_amp_labels]),
                tuple(s_notes),
            )
        )
    return healed_total, shielded_total, out_heals, out_shields


def apply_health_cost(rt: _DefenseRuntime, amount: Fraction) -> Fraction:
    if amount <= 0 or rt.health <= 1:
        return Fraction(0)
    paid = min(amount, rt.health - 1)
    rt.health -= paid
    return paid


def set_grievous_until(rt: _DefenseRuntime, until: Fraction) -> None:
    if rt.dynamic_grievous_until is None or until > rt.dynamic_grievous_until:
        rt.dynamic_grievous_until = until


def set_shield_reaver(rt: _DefenseRuntime, rate: Fraction, until: Fraction) -> None:
    if rate > 0:
        for sh in rt.shields:
            if sh.remaining > 0:
                sh.remaining *= 1 - rate
        rt.dynamic_sr_rate = max(rt.dynamic_sr_rate, rate)
        if rt.dynamic_sr_until is None or until > rt.dynamic_sr_until:
            rt.dynamic_sr_until = until


def next_event_time(rt: _DefenseRuntime, after: Fraction, limit: Fraction) -> Fraction | None:
    candidates: list[Fraction] = []
    if rt.ga_stasis_until is not None and after < rt.ga_stasis_until <= limit:
        candidates.append(rt.ga_stasis_until)
    for lock in rt.cc_locks:
        if after < lock.end <= limit:
            candidates.append(lock.end)
    for end_t, _ in rt.active_hp_buffs:
        if after < end_t <= limit:
            candidates.append(end_t)
    for end_t, *_ in rt.active_hots:
        if after < end_t <= limit:
            candidates.append(end_t)
    for b in rt.stagger_bleeds:
        if after < b.end <= limit:
            candidates.append(b.end)
    for sh in rt.shields:
        if sh.expires_at is not None and after < sh.expires_at <= limit:
            candidates.append(sh.expires_at)
    for end_t, *_ in rt.active_undying:
        if end_t is not None and after < end_t <= limit:
            candidates.append(end_t)
    for end_t, *_ in rt.active_invuln_ends:
        if end_t is not None and after < end_t <= limit:
            candidates.append(end_t)
    for end_t, *_ in rt.active_dodge_ends:
        if end_t is not None and after < end_t <= limit:
            candidates.append(end_t)
    return min(candidates) if candidates else None


def outcome(rt: _DefenseRuntime, enemy_description: str) -> DefenseOutcome:
    all_labels = [s.label for s in rt.steps]
    if rt.sim.weakened:
        all_labels.append(Label.PENDING)
    return DefenseOutcome(
        rt.sim.sheet.champion.name,
        rt.sim.sheet.level,
        rt.sim.sheet.champion.patch,
        enemy_description,
        rt.sim.max_health,
        rt.sim.start_health,
        rt.sim.start_shield,
        rt.sim.shield_type,
        tuple(rt.steps),
        weakest(all_labels) if all_labels else rt.sim.sheet["health"].label,
        tuple(dict.fromkeys(rt.sim.notes)),
        rt.sim.timeline,
    )


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
