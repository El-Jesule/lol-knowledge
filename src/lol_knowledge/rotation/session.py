"""Rotation engine assembly, incremental RotationSession, and public entrypoints."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from fractions import Fraction
from typing import Any

from ..damage import DamageType, format_number
from ..errors import RotationError, StatsError
from ..item_combat import ALLY_HEAL_SHIELD_ACTIVES, ItemCombat
from ..kit import Kit
from ..passives import PassiveCombat
from ..resources import ResourceEvent, ResourceTracker, StepResourceCost, resolve_ability_cost
from ..rune_combat import RuneCombat
from ..runes import Rune, RuneData, fraction_input, int_input
from ..scenario import Target
from ..stats import Label, StatBlocked, StatSheet, weakest
from ..summoners import SummonerSpellData, SummonerSpellSpec, resolve_loadout, summoner_spell_haste
from ..survival import GRIEVOUS_WOUNDS_REDUCTION, HealEvent, ShieldEvent
from .combat_steps import _CombatStepsMixin
from .effects import _Burn, _Effect, _effects, _EffectsMixin, _kit_uses_move_speed, _Window
from .models import (
    ACTIVE_COMBAT_KINDS,
    BURN_TRIGGERS,
    HOLDER_RANGES,
    RESISTANCE_STATS,
    TIMED_KINDS,
    TIMED_TRIGGERS,
    CritBase,
    DuelStepResult,
    Part,
    RotationOutcome,
    RotationSession,
    Step,
    StepOutcome,
)
from .runner import _RunnerMixin
from .timeline import _TimelineMixin


class _Rotation(_EffectsMixin, _TimelineMixin, _CombatStepsMixin, _RunnerMixin):
    """Stateful deterministic rotation evaluator."""

    def __init__(
        self,
        kit: Kit,
        sheet: StatSheet,
        ranks: Mapping[str, int],
        target: Target,
        crit_base: CritBase | None,
        holder_range: str | None,
        inputs: Mapping[str, Any],
        timeline: bool = False,
        runes: Sequence[int] = (),
        rune_data: RuneData | None = None,
        has_ultimate_step: bool = False,
        ap_weight: Fraction | None = None,
        start_resource: Fraction | None = None,
        allow_insufficient_resource: bool = False,
        apply_passives: bool = True,
        target_count: int = 1,
        summoners: Sequence[str] = (),
        summoner_data: SummonerSpellData | None = None,
    ) -> None:
        if isinstance(target_count, bool) or not isinstance(target_count, int) or target_count < 1:
            raise RotationError("target count must be an integer >= 1")
        self.kit, self.sheet, self.ranks, self.target = kit, sheet, ranks, target
        self.target_count = target_count
        self.base_sheet = sheet
        self.summoner_data = summoner_data
        self.summoner_loadout: tuple[SummonerSpellSpec, ...] = ()
        self.summoner_label = (
            summoner_data.label_for(sheet.champion.patch)
            if summoner_data is not None
            else Label.DERIVED
        )
        if summoners:
            if summoner_data is None:
                raise RotationError(
                    "summoner spells require lol-knowledge/derived/summoner-spells.json"
                )
            try:
                self.summoner_loadout, _ = resolve_loadout(summoners, summoner_data)
            except StatsError as exc:
                raise RotationError(str(exc)) from exc
        self._summoner_haste = summoner_spell_haste(sheet.items, runes, rune_data)
        self._summoner_used: set[str] = set()
        self._summoner_ready: dict[str, Fraction] = {}
        self._summoner_ms_buffs: list[tuple[Fraction | None, Fraction, str, Label]] = []
        self._summoner_burns: list[tuple[Fraction, Fraction, str, Label, tuple[str, ...]]] = []
        self._ability_stat_buffs: dict[
            str, tuple[Fraction | None, str, str, Fraction, str, Label]
        ] = {}
        self.attacker_exhausted = Fraction(str(inputs.get("exhausted", 0))) > 0
        self.timeline = self._timeline() if timeline else None
        self.crit_base, self.holder_range, self.inputs = crit_base, holder_range, inputs
        self.base_stats, self.base_origin = sheet.cached_sheet_stats()
        self.stats, self.origin = self.base_stats, self.base_origin
        self._last_moment_ops: tuple[tuple[Any, ...], ...] | None = None
        self.life_steal, self.omnivamp = sheet["life_steal"], sheet["omnivamp"]
        self.hsp = sheet["heal_and_shield_power"]
        try:
            gw_input = int_input(inputs, "grievous_wounds", minimum=0, maximum=1)
            atk_hp_pct = fraction_input(inputs, "attacker_health_percent")
        except StatsError as exc:
            raise RotationError(str(exc)) from exc
        self.grievous_permanent = GRIEVOUS_WOUNDS_REDUCTION if gw_input == 1 else Fraction(0)
        self.grievous_timed_rate = Fraction(0)
        self.grievous_timed_until: Fraction | None = None
        self.grievous_timed_source = ""
        self.grievous_timed_label = Label.DERIVED
        self.grievous_used = gw_input == 1
        self.attacker_max_hp: Fraction | None = None
        self.attacker_start_hp: Fraction | None = None
        self.attacker_hp: Fraction | None = None
        self.effective_healing_total: Fraction | None = None
        if atk_hp_pct is not None:
            try:
                max_hp = sheet["health"].total()
            except StatBlocked as exc:
                raise RotationError(
                    f"attacker_health_percent needs attacker health: {exc}"
                ) from exc
            self.attacker_max_hp = max_hp
            self.attacker_start_hp = max_hp * atk_hp_pct
            self.attacker_hp = self.attacker_start_hp
            self.effective_healing_total = Fraction(0)
        self.item_heals: list[_Effect] = []
        self.item_shields: list[_Effect] = []
        self.item_resource_restores: list[_Effect] = []
        self.defender_grievous: list[_Effect] = []
        attacker, notes, weakened = _effects(sheet.items, "attacker", target.kind)
        defender, target_notes, target_weakened = _effects(target.items, "target")
        self.rune_combat = RuneCombat(
            runes,
            rune_data,
            sheet,
            target,
            has_ultimate_step=has_ultimate_step,
            holder_range=holder_range,
            inputs=inputs,
            timeline=timeline,
            ap_weight=ap_weight,
        )
        self.resources = ResourceTracker(
            sheet,
            inputs,
            start_resource=start_resource,
            timeline=timeline,
            allow_insufficient=allow_insufficient_resource,
            manaflow_regen=self.rune_combat.manaflow_band_config(sheet),
        )
        self.passive_combat = PassiveCombat(
            kit,
            target,
            inputs,
            timeline=timeline,
            enabled=apply_passives,
        )
        self.notes = (
            notes
            + target_notes
            + list(sheet.pending_effects)
            + self.rune_combat.notes
            + list(self.resources.notes)
        )
        self.weakened = (
            weakened
            or target_weakened
            or bool(sheet.pending_effects)
            or self.rune_combat.weakened
            or self.resources.weakened
        )
        self.ms_affects_damage = (
            sheet.champion.id == "Hecarim"
            or bool(sheet.post_ms_effects)
            or _kit_uses_move_speed(kit)
        )
        self.on_hit: list[_Effect] = []
        self.secondary_attacks: list[_Effect] = []
        self.ability_procs: list[_Effect] = []
        self.on_damage_procs: list[_Effect] = []
        self.threshold_procs: list[_Effect] = []
        self.shred_percent_effects: list[_Effect] = []
        self.cooldown_refunds: list[_Effect] = []
        self.ability_stacked: list[_Effect] = []
        self.self_heal_amp = Fraction(1)
        self.self_shield_amp = Fraction(1)
        self.self_amp_labels: list[Label] = []
        self.self_amp_notes: list[str] = []
        self.dealt: list[_Effect] = []
        self.taken: list[_Effect] = []
        self.spellblade: list[_Effect] = []
        self.repeats: list[_Effect] = []
        self.counted: list[_Effect] = []
        self.counted_repeats: list[_Effect] = []
        self.energized: list[_Effect] = []
        self.galvanize: list[_Effect] = []
        self.executes: list[_Effect] = []
        self.burns: list[_Effect] = []
        self.timed: list[_Effect] = []
        # Timeline state: timed effects and burns in force, and how far burns are counted.
        self.windows: dict[str, _Window] = {}
        self.timed_ready: dict[str, Fraction] = {}  # cooldowns of timed effects
        self.proc_ready: dict[str, Fraction] = {}  # cooldowns of ability/on_damage procs
        self.proc_fired: set[str] = set()  # non-timeline one-shot cooldown procs
        self.combo_hits: dict[str, list[Fraction]] = {}  # timeline on_damage combo hits
        self.combo_counts: dict[str, int] = {}  # non-timeline on_damage combo hits
        self.ability_stacks: dict[str, int] = {}  # stacks gained per damaging ability (Shojin)
        self.ability_stacked_at: dict[str, Fraction] = {}
        self.shred_stacks: dict[
            str, int
        ] = {}  # percent resistance shred stacks (Cleaver, Bloodletter)
        self.shred_stacked_at: dict[str, Fraction] = {}
        self.threshold_damage_log: dict[str, list[tuple[Fraction, Fraction]]] = {}
        self.delayed_item_procs: list[tuple[Fraction, _Effect, Fraction, tuple[Label, ...]]] = []
        self.last_counted: dict[str, Fraction] = {}  # last attack of each counter
        self.speed_changed = False  # a timed effect changed the attack speed
        # Stacks gained per attack and seconds in combat, from 0 (combat-stacks.md).
        self.stacked: list[_Effect] = []
        self.combat: list[_Effect] = []
        self.stacks: dict[str, int] = {}
        self.stacked_at: dict[str, Fraction] = {}  # the last attack that added a stack
        self.turns: dict[str, int] = {}  # attacks taken by each alternation group
        self.now = Fraction(0)
        self.burning: dict[str, _Burn] = {}
        self.accrued = Fraction(0)
        self.active_dealt: list[_Window] = []
        self.shred: dict[DamageType, list[_Window]] = {}
        self.item_actives: dict[str, list[_Effect]] = {}
        self.active_ready: dict[str, Fraction] = {}
        self.empowered_attacks: dict[str, list[_Effect]] = {}
        self.cast_actives: set[str] = set()
        self.item_combat = ItemCombat(
            sheet,
            sheet.items,
            target.kind,
            holder_range,
            self.inputs,
            timeline=timeline,
            target_count=self.target_count,
            item_haste=self.rune_combat.item_haste,
            time_warp_ratio=self.rune_combat.time_warp_ratio(),
        )
        self._pending_accrued_heals: list[HealEvent] = []
        self._knights_vow_applied = False

        # Defender combat runes (8473 Bone Plating, 8444 Second Wind) when target.runes provided
        self.def_bone_rune: Rune | None = None
        self.def_bone_charges = 0
        self.def_bone_expires: Fraction | None = None
        self.def_bone_ready = Fraction(0)
        self.def_bone_used_once = False
        self.def_rune_base = (
            Label.DERIVED
            if (rune_data is not None and rune_data.matches_patch(sheet.champion.patch))
            else Label.PENDING
        )
        if target.runes and rune_data is not None:
            for rid in dict.fromkeys(target.runes):
                dr = rune_data.runes.get(rid)
                if dr is None:
                    continue
                if dr.key == "BonePlating":
                    self.def_bone_rune = dr
                elif dr.key == "SecondWind":
                    self.notes.append(
                        f"target rune:{dr.id} {dr.name}: 4% missing HP regen over 10 s "
                        "after taking damage (evaluate exact survival in survive)"
                    )
        owners = sorted(
            {
                item.id
                for item in sheet.items
                if any(
                    (effect.get("trigger") or {}).get("event") == "spellblade"
                    for effect in item.effects
                )
            }
        )
        if len(owners) > 1:
            raise RotationError(
                f"items {', '.join(owners)} all have Spellblade; a champion is limited to one "
                "Spellblade item (spellblade.md)"
            )
        for effect in attacker:
            kind = effect.component.get("kind")
            if effect.kind == "active":
                if kind in ACTIVE_COMBAT_KINDS:
                    self.item_actives.setdefault(effect.item, []).append(effect)
                else:
                    self._skip(effect, f"{effect.trigger} {kind}")
                continue
            if effect.every is not None and kind == "damage":
                self.counted.append(effect)
            elif effect.every is not None and kind == "repeat_on_hit":
                self.counted_repeats.append(effect)
            elif (
                effect.trigger in {"on_attack", "on_hit"}
                and kind == "damage"
                and effect.component.get("secondary_only") is True
            ):
                self.secondary_attacks.append(effect)
            elif effect.trigger == "on_hit" and kind == "damage":
                self.on_hit.append(effect)
            elif effect.trigger == "damaging_ability" and kind == "damage":
                self.ability_procs.append(effect)
            elif (
                effect.trigger == "damaging_ability"
                and kind == "damage_modifier"
                and effect.max_stacks is not None
            ):
                self._ability_stacking(effect)
            elif (
                effect.trigger in {"on_damage", "damaging_ability"}
                and kind == "stat_modifier"
                and effect.component.get("mode") == "percent"
                and str(effect.component.get("stat")) in RESISTANCE_STATS
                and effect.max_stacks is not None
            ):
                self.shred_percent_effects.append(effect)
            elif (
                effect.trigger == "on_damage"
                and kind == "damage"
                and "damage_threshold_percent" in effect.component
            ):
                self.threshold_procs.append(effect)
            elif effect.trigger == "on_damage" and kind in {"damage", "shield"}:
                self.on_damage_procs.append(effect)
            elif effect.trigger == "on_attack" and kind == "cooldown_refund":
                self.cooldown_refunds.append(effect)
            elif (
                effect.trigger == "always"
                and effect.affects == "self"
                and kind in {"healing", "shield"}
                and effect.component.get("mode") == "percent"
            ):
                pct, stat_labels = self._value(effect, self.target.stats)
                if kind == "healing":
                    self.self_heal_amp *= 1 + pct / 100
                    self.self_amp_labels.extend([effect.label, *stat_labels])
                    self.self_amp_notes.append(f"{effect.title} +{format_number(pct)}% healing")
                else:
                    self.self_shield_amp *= 1 + pct / 100
                    self.self_amp_labels.extend([effect.label, *stat_labels])
                    self.self_amp_notes.append(f"{effect.title} +{format_number(pct)}% shielding")
            elif effect.trigger == "energized" and kind == "damage":
                self.energized.append(effect)
            elif kind == "execute":
                self.executes.append(effect)
            elif effect.trigger in BURN_TRIGGERS and kind == "burn":
                self.burns.append(effect)
            elif effect.trigger == "damaging_ability" and kind == "trigger_energized":
                self.galvanize.append(effect)
            elif effect.trigger == "spellblade" and kind == "damage":
                self.spellblade.append(effect)
            elif effect.trigger == "spellblade" and kind == "repeat_on_hit":
                self.repeats.append(effect)
            elif effect.trigger == "on_attack" and effect.max_stacks is not None:
                self._stacking(effect)
            elif effect.trigger == "in_combat":
                self._in_combat(effect)
            elif effect.trigger == "always" and kind == "damage_modifier":
                if effect.component.get("direction") != "dealt":
                    self._skip(effect, "damage taken by the attacker")
                else:
                    self.dealt.append(effect)
                    if effect.scenario is not None:
                        self.notes.append(
                            f"attacker {effect.title}: applied at full stacks "
                            f"(scenario {effect.scenario})"
                        )
            elif (
                kind == "healing"
                and effect.component.get("mode") == "absolute"
                and effect.affects == "self"
                and effect.trigger in {"spellblade", "on_hit", "damaging_ability", "cast"}
            ):
                self.item_heals.append(effect)
            elif (
                kind == "shield"
                and effect.component.get("mode") == "absolute"
                and effect.affects == "self"
                and effect.trigger in {"spellblade", "on_hit", "damaging_ability", "cast"}
            ):
                self.item_shields.append(effect)
            elif (
                kind == "resource_restore"
                and ((effect.component.get("target") or {}).get("kind") or effect.affects) == "self"
                and effect.trigger in {"spellblade", "on_hit", "damaging_ability", "cast"}
            ):
                self.item_resource_restores.append(effect)
            elif (
                effect.duration is not None
                and kind in TIMED_KINDS
                and effect.trigger in TIMED_TRIGGERS
            ):
                self._timed(effect)
            else:
                self._skip(effect, f"{effect.trigger} {kind}")
        if len({effect.item for effect in self.energized}) > 1:
            self.notes.append(
                "several Energized items: whether their Energized effects stack is not verified"
            )
            self.weakened = True
        for effect in defender:
            kind = effect.component.get("kind")
            if (
                kind == "damage_modifier"
                and effect.component.get("direction") == "taken"
                and effect.component.get("mode") == "percent"
                and effect.duration is None
            ):
                self.taken.append(effect)
            elif (
                effect.trigger == "taking_attack"
                and kind == "status"
                and effect.component.get("effect") == "grievous_wounds"
            ):
                self.defender_grievous.append(effect)
            else:
                self._skip(effect, f"{effect.trigger} {kind}", owner="target")

    def open_session(self) -> RotationSession:
        """Open a step-by-step offensive session sharing all ``_Rotation`` mechanics."""
        if self.timeline is None:
            raise RotationError("RotationSession requires timeline=True")
        if self.holder_range is not None and self.holder_range not in HOLDER_RANGES:
            raise RotationError(f"attacker range must be melee or ranged, not {self.holder_range}")
        charged = False
        charged_at = Fraction(0)
        window = self._spellblade_window()
        counters = {effect.title: 0 for effect in [*self.counted, *self.counted_repeats]}
        energized = bool(self.energized)
        burned: set[str] = set()
        clock = Fraction(0)
        next_attack = Fraction(0)
        spellblade_ready = Fraction(0)
        ready: dict[str, Fraction] = {}
        open_casts: dict[str, tuple[Fraction, int, Fraction]] = {}
        step_counter = 0

        # Precompute Grievous Wounds item durations directly from catalog effects
        gw_items_all: list[tuple[frozenset[str], Fraction]] = []
        for item in self.sheet.items:
            for eff in item.effects:
                if eff.get("status") != "evaluable" and eff.get("kind") != "status":
                    pass
                for comp in eff.get("components") or ():
                    if comp.get("kind") == "status" and comp.get("status") == "grievous_wounds":
                        trig = (eff.get("trigger") or {}).get("event", "")
                        if trig in {"on_damage", "on_physical_damage", "on_magic_damage"}:
                            dur = Fraction(str(eff.get("duration_seconds") or 3))
                            if trig == "on_physical_damage":
                                gw_items_all.append((frozenset({"physical"}), dur))
                            elif trig == "on_magic_damage":
                                gw_items_all.append((frozenset({"magic"}), dur))
                            else:
                                gw_items_all.append((frozenset({"physical", "magic", "true"}), dur))

        def sync_context(
            target: Target,
            attacker_hp: Fraction,
            attacker_max_hp: Fraction,
            *,
            exhausted: bool = False,
        ) -> None:
            self.target = target
            self.attacker_hp = attacker_hp
            self.attacker_max_hp = attacker_max_hp
            self.attacker_exhausted = exhausted

        def notify_shield_granted(amount: Fraction, at: Fraction) -> None:
            if amount > 0:
                self.rune_combat.on_attacker_shield(amount, at)

        def next_attack_time() -> Fraction:
            return next_attack

        def ability_ready_time(slot: str) -> Fraction:
            return ready.get(slot.upper(), Fraction(0))

        def can_cast_slot(slot: str, case_id: str | None, at: Fraction) -> bool:
            s_up = slot.upper()
            if s_up not in self.ranks or s_up not in self.kit.abilities:
                return False
            if at < ready.get(s_up, Fraction(0)):
                return False
            if self.resources.uses_casting_pool:
                cost = resolve_ability_cost(
                    self.kit,
                    self.sheet,
                    s_up,
                    self.ranks[s_up],
                    case_id,
                    self.stats,
                    self.origin,
                    self.inputs,
                    attacker_hp=self.attacker_hp,
                    attacker_max_hp=self.attacker_max_hp,
                )
                if (
                    cost.resource == self.resources.pool.kind
                    and self.resources.current < cost.amount
                ):
                    return False
            return True

        def peek_step_time(
            step: Step, min_clock: Fraction, *, allow_wait_for_cd: bool = True
        ) -> Fraction:
            if step.wait is not None:
                return min_clock + step.wait
            if step.slot is None and step.item_id is None and step.summoner_id is None:
                return max(min_clock, next_attack)
            if step.slot is not None:
                ab = self.kit.ability(step.slot)
                case = (
                    ab.case(step.case)
                    if step.case is not None
                    else (ab.cases[0] if ab.cases else None)
                )
                if case is not None and case.recast:
                    if step.slot in open_casts:
                        _, _, last = open_casts[step.slot]
                        if ab.recast_interval is not None:
                            return max(min_clock, last + ab.recast_interval)
                    return min_clock
                cd_at = ready.get(step.slot, Fraction(0))
                return max(min_clock, cd_at) if allow_wait_for_cd else min_clock
            if step.item_id is not None:
                cd_at = self.active_ready.get(step.item_id, Fraction(0))
                return max(min_clock, cd_at) if allow_wait_for_cd else min_clock
            if step.summoner_id is not None and self.summoner_data is not None:
                try:
                    sp = self.summoner_data.resolve(step.summoner_id)
                except StatsError:
                    return min_clock
                cd_at = self._summoner_ready.get(sp.id, Fraction(0))
                return max(min_clock, cd_at) if allow_wait_for_cd else min_clock
            return min_clock

        def accrue_to(until: Fraction) -> tuple[list[Part], list[HealEvent], list[ResourceEvent]]:
            nonlocal clock
            if until < self.accrued:
                return [], [], []
            cur_t_hp = self.target.stats["current_health"]
            cur_t_sh = self.target.shield
            b_parts, _, _, _ = self._accrue(until, cur_t_hp, cur_t_sh)
            heals_out = list(self._pending_accrued_heals)
            self._pending_accrued_heals.clear()
            res_ev = list(self.resources.accrue_regen(until))
            clock = max(clock, until)
            return b_parts, heals_out, res_ev

        def next_pending_time(after: Fraction, limit: Fraction) -> Fraction | None:
            cands: list[Fraction] = []
            for burn in self.burning.values():
                if after < burn.end <= limit:
                    cands.append(burn.end)
            for b_end, *_ in self._summoner_burns:
                if after < b_end <= limit:
                    cands.append(b_end)
            for due_t, *_ in self.delayed_item_procs:
                if after < due_t <= limit:
                    cands.append(due_t)
            p_end = self.rune_combat.last_pending_time()
            if p_end is not None and after < p_end <= limit:
                cands.append(p_end)
            return min(cands) if cands else None

        def step_one(
            step: Step, at: Fraction, *, defer_ability_survival: bool = True
        ) -> DuelStepResult:
            nonlocal charged, charged_at, energized, clock, next_attack
            nonlocal spellblade_ready, step_counter
            step_counter += 1
            index = step_counter
            clock = max(clock, at)
            if step.slot is not None:
                self._cast(step, clock, ready, open_casts)
            parts: list[Part] = []
            heal_events: list[HealEvent] = []
            shield_events: list[ShieldEvent] = []
            resource_events: list[ResourceEvent] = []
            step_cost: StepResourceCost | None = None
            health_cost = Fraction(0)
            res_before = self.resources.current if self.resources.uses_casting_pool else None
            before = self.target.stats["current_health"]
            shield_before = self.target.shield
            health = before
            step_shield_shredded = Fraction(0)
            shred_ratio_out = Fraction(0)
            applied_gw: Fraction | None = None
            applied_ex: Fraction | None = None
            cast_summ: SummonerSpellSpec | None = None

            self._set_moment(clock)
            target_stats = self._target_stats(health)
            extra: list[Label] = []
            self._last_summoner_spec = None
            self._last_summoner_grievous_until = None
            self._last_summoner_exhaust_until = None
            self._defer_summoner_survival = defer_ability_survival

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
                if reset_attack:
                    next_attack = clock
            elif step.summoner_id is not None:
                name, s_parts, s_heals, s_shields = self._summoner_cast(step, target_stats, clock)
                parts += s_parts
                heal_events += s_heals
                shield_events += s_shields
                cast_summ = self._last_summoner_spec
                applied_gw = self._last_summoner_grievous_until
                applied_ex = self._last_summoner_exhaust_until
            elif step.slot is None:
                self._trigger_defender_grievous(clock)
                if charged and window is not None and clock - charged_at > window:
                    charged = False
                    extra.append(Label.PENDING)
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
                    spellblade_ready = clock + self._spellblade_cooldown()
                    if self._open("spellblade", clock, target_stats):
                        extra.append(Label.PENDING)
                self._stack(clock, target_stats)
                parts += self._counted(step, target_stats, counters, clock, extra)
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
                    health_cost = step_cost.amount
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
                    step.slot,
                    step.case,
                    target_stats,
                    clock,
                    ability_parts=ability_parts,
                    defer_survival=defer_ability_survival,
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
                if clock >= spellblade_ready:
                    charged, charged_at = True, clock
                parts += self._burns(step, ability_parts, target_stats, burned, clock)
                self._open("cast", clock, target_stats, step.slot)
                if ability_parts:
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
                    if self._open("energized", clock, target_stats):
                        extra.append(Label.PENDING)

            self._defer_summoner_survival = False
            step_dealt = (
                False if (step.item_id is not None or step.summoner_id is not None) else bool(parts)
            )
            if step_dealt:
                od_parts, od_shields = self._on_damage_procs(step, target_stats, clock, step.slot)
                parts += od_parts
                shield_events += od_shields
                pre_mit = sum((p.raw for p in parts), start=Fraction(0))
                post_phys = sum(
                    (p.damage for p in parts if p.damage_type is DamageType.PHYSICAL),
                    start=Fraction(0),
                )
                cur_mana = self.resources.current if self.resources.pool.kind == "mana" else None
                ic_procs, ic_heals, ic_shields, shred_ratio = self.item_combat.on_damage_dealt(
                    pre_mitigation_total=pre_mit,
                    post_mitigation_physical=post_phys,
                    clock=clock,
                    current_mana=cur_mana,
                )
                shred_ratio_out = shred_ratio
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
                dealt_types = frozenset(p.damage_type.value for p in parts)
                self._open("on_damage", clock, target_stats, step.slot, damage_types=dealt_types)
                for req_types, gw_dur in gw_items_all:
                    if dealt_types & req_types:
                        cand_gw = clock + gw_dur
                        if applied_gw is None or cand_gw > applied_gw:
                            applied_gw = cand_gw

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

            step_damage = sum((p.primary_damage for p in parts), start=Fraction(0))
            step_after = max(Fraction(0), before - step_damage)
            complete_parts: list[Part] = []
            for proc in self.rune_combat.on_step_complete(
                step_damage,
                clock,
                self.sheet,
                before,
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
            self._apply_shred_stacks(parts, clock, target_stats, step.slot)
            parts += self._execute(parts, before, target_stats, Fraction(0))

            for raw_heal in self.rune_combat.on_step_heals(
                step.slot,
                step_dealt,
                False,
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
                step.slot, step_dealt, False, clock, self.sheet
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
                step.slot, step_dealt, False, clock, self.sheet
            ):
                applied = self.resources.restore(
                    p_res.source, p_res.resource, p_res.amount, p_res.label, p_res.notes
                )
                if applied is not None:
                    resource_events.append(applied)
            for raw_restore in self.rune_combat.on_step_resource_restores(
                step_dealt,
                False,
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

            out = StepOutcome(
                index,
                step,
                name,
                tuple(parts),
                before,
                weakest(
                    [
                        *(part.label for part in parts),
                        *(ev.label for ev in shield_events),
                        *(ev.label for ev in heal_events),
                        *extra,
                    ]
                )
                if (parts or shield_events or heal_events or extra)
                else self.sheet["attack_damage"].label,
                clock,
                shield_before=shield_before,
                shield_absorbed=Fraction(0),
                shield_shredded=step_shield_shredded,
                heal_events=tuple(heal_events),
                shield_events=tuple(shield_events),
                resource_cost=step_cost,
                resource_before=res_before,
                resource_after=res_after,
                resource_events=tuple(resource_events),
            )
            if step.slot is None and step.item_id is None and step.summoner_id is None:
                self._set_moment(clock)
                next_attack = clock + 1 / self.sheet["attack_speed"].total()
            return DuelStepResult(
                outcome=out,
                new_parts=tuple(parts),
                heal_events=tuple(heal_events),
                shield_events=tuple(shield_events),
                health_cost=health_cost,
                applied_grievous_until=applied_gw,
                applied_exhaust_until=applied_ex,
                shield_reaver_ratio=shred_ratio_out,
                cast_summoner=cast_summ,
            )

        return RotationSession(
            sync_context=sync_context,
            notify_shield_granted=notify_shield_granted,
            next_attack_time=next_attack_time,
            ability_ready_time=ability_ready_time,
            can_cast_slot=can_cast_slot,
            peek_step_time=peek_step_time,
            accrue_to=accrue_to,
            step_one=step_one,
            next_pending_time=next_pending_time,
            get_notes=lambda: tuple(
                dict.fromkeys([*self.notes, *self.resources.notes, *self.passive_combat.notes])
            ),
            is_weakened=lambda: bool(self.weakened or self.resources.weakened),
            resource_summary=lambda: self.resources.summary(),
        )


def open_rotation_session(
    kit: Kit,
    sheet: StatSheet,
    ranks: Mapping[str, int],
    target: Target,
    crit_base: CritBase | None,
    *,
    holder_range: str | None = None,
    inputs: Mapping[str, Any] | None = None,
    runes: Sequence[int] = (),
    rune_data: RuneData | None = None,
    has_ultimate_step: bool = False,
    ap_weight: Fraction | None = None,
    start_resource: Fraction | None = None,
    allow_insufficient_resource: bool = False,
    apply_passives: bool = True,
    summoners: Sequence[str] = (),
    summoner_data: SummonerSpellData | None = None,
) -> RotationSession:
    """Create a live timeline-enabled offensive stepper coupled to an external duel clock."""
    rot = _Rotation(
        kit,
        sheet,
        ranks,
        target,
        crit_base,
        holder_range,
        inputs or {},
        timeline=True,
        runes=runes,
        rune_data=rune_data,
        has_ultimate_step=has_ultimate_step,
        ap_weight=ap_weight,
        start_resource=start_resource,
        allow_insufficient_resource=allow_insufficient_resource,
        apply_passives=apply_passives,
        target_count=1,
        summoners=summoners,
        summoner_data=summoner_data,
    )
    return rot.open_session()


def evaluate_rotation(
    kit: Kit,
    sheet: StatSheet,
    ranks: Mapping[str, int],
    target: Target,
    steps: Sequence[Step],
    crit_base: CritBase | None,
    *,
    holder_range: str | None = None,
    inputs: Mapping[str, Any] | None = None,
    timeline: bool = False,
    runes: Sequence[int] = (),
    rune_data: RuneData | None = None,
    ap_weight: Fraction | None = None,
    start_resource: Fraction | None = None,
    allow_insufficient_resource: bool = False,
    apply_passives: bool = True,
    target_count: int = 1,
    summoners: Sequence[str] = (),
    summoner_data: SummonerSpellData | None = None,
) -> RotationOutcome:
    """Damage of every step against ``target``, carrying its current health forward.

    ``holder_range`` is the attacker's melee/ranged classification; it is only
    required by effects that branch on it and is never guessed. ``crit_base``
    is only required by critical steps. With ``timeline`` every step gets a time:
    attacks are spaced by 1 / attack speed, cooldowns and recast windows are
    enforced and ``wait:<seconds>`` steps advance the clock (timeline.md).
    """
    if not steps:
        raise RotationError("the rotation has no steps")
    has_ultimate = any(step.slot == "R" for step in steps)
    rotation = _Rotation(
        kit,
        sheet,
        ranks,
        target,
        crit_base,
        holder_range,
        inputs or {},
        timeline,
        runes=runes,
        rune_data=rune_data,
        has_ultimate_step=has_ultimate,
        ap_weight=ap_weight,
        start_resource=start_resource,
        allow_insufficient_resource=allow_insufficient_resource,
        apply_passives=apply_passives,
        target_count=target_count,
        summoners=summoners,
        summoner_data=summoner_data,
    )
    return rotation.run(steps)
