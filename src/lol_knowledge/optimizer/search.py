"""Deterministic pruned search over legal League of Legends builds (OPT-01..OPT-03)."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from fractions import Fraction
from pathlib import Path
from typing import Any

from ..damage import DamageType
from ..defense import IncomingHit, evaluate_defense
from ..errors import KitError, RotationError, StatsError
from ..kit import Kit
from ..objects import load_model
from ..objects.legality import INVENTORY_SLOTS, ItemGroups, check_build, load_item_groups
from ..passives import sheet_passive_effects
from ..rotation import ACTIVE_COMBAT_KINDS, DAMAGE_KINDS, CritBase, Step, evaluate_rotation
from ..runes import (
    RuneData,
    adaptive_stat,
    check_page,
    combat_rune_notes,
    minor_rune_effects,
    needs_adaptive_stat,
    shard_contributions,
)
from ..scenario import Target
from ..stats import (
    ChampionData,
    DerivedRecords,
    ItemData,
    Label,
    StatSheet,
    build_stat_sheet,
    effective_health,
    items_from_model,
    weakest,
)
from ..stats.issues import DataIssue
from ..stats.sheet import MANA_RESOURCE
from .models import (
    DEFENSE_OBJECTIVES,
    EHP_OBJECTIVES,
    OBJECTIVES,
    ROTATION_OBJECTIVES,
    TIERS,
    BuildResult,
    CandidateItem,
    OptimizeConstraints,
    OptimizeOutcome,
    SearchStats,
)

# Minimum gold for a non-boots item to count as "completed" when it has no upgrades in catalog.
COMPLETED_MIN_GOLD = 800
# Synergy items kept in the pruned pool even when their standalone 1-item delta is modest.
SYNERGY_ITEMS = frozenset({"3089", "3031", "3135", "3036", "3033", "3137", "3124", "3085"})


def _has_excluded_defensive_effect(item: ItemData) -> bool:
    """Whether ``item`` has an excluded defensive passive not yet modelled in ``defense.py``."""
    for effect in item.effects:
        if effect.get("model_status") == "evaluable":
            continue
        trigger = (effect.get("trigger") or {}).get("event")
        if trigger in {"taking_damage", "taking_attack"}:
            return True
    return False


# Component kinds on reactive defensive triggers not reflected in static t=0 EHP.
_COMBAT_ONLY_EHP_KINDS = frozenset({"stat_modifier", "damage_stagger", "healing"})


def _has_unmodelled_ehp_effect(item: ItemData) -> bool:
    """Whether ``item`` has defensive triggers that static EHP (HP * (1 + Res/100)) omits."""
    if _has_excluded_defensive_effect(item):
        return True
    for effect in item.effects:
        trigger = (effect.get("trigger") or {}).get("event")
        if trigger not in {"taking_damage", "taking_attack"}:
            continue
        for comp in effect.get("components") or ():
            kind = comp.get("kind")
            if kind in _COMBAT_ONLY_EHP_KINDS:
                return True
            if kind == "damage_modifier" and (
                comp.get("mode") == "flat" or effect.get("duration_seconds") is not None
            ):
                return True
    return False


def _is_verified_clean(item: ItemData) -> bool:
    """Whether ``item`` has complete effect review and no pending/excluded combat components."""
    if item.effect_review != "complete":
        return False
    if any(stat.label is Label.PENDING for stat in item.stats):
        return False
    for effect in item.effects:
        if effect.get("model_status") == "evaluable":
            continue
        components = effect.get("components") or ()
        if any(comp.get("kind") in DAMAGE_KINDS for comp in components):
            return False
    return True


def _steps_with_item_actives(
    base_steps: Sequence[Step], items: Sequence[ItemData], *, timeline: bool
) -> tuple[Step, ...]:
    """Weave equipped items' evaluable combat actives into ``base_steps`` once each."""
    already = {step.item_id for step in base_steps if step.item_id is not None}
    prefix: list[Step] = []
    suffix: list[Step] = []
    empowers: list[Step] = []
    for item in items:
        if item.id in already:
            continue
        active_effects = [
            eff
            for eff in item.effects
            if eff.get("kind") == "active" and eff.get("model_status") == "evaluable"
        ]
        if not active_effects:
            continue
        comp_kinds = {
            str(comp.get("kind"))
            for eff in active_effects
            for comp in (eff.get("components") or ())
        }
        if not (comp_kinds & ACTIVE_COMBAT_KINDS):
            continue
        step = Step(f"item:{item.id}", item_id=item.id)
        if any(eff.get("empowers_next_attack") for eff in active_effects):
            empowers.append(step)
        elif comp_kinds & {"damage", "healing", "shield"}:
            suffix.append(step)
        elif timeline:
            prefix.append(step)
    result = [*prefix, *base_steps]
    if empowers:
        attack_indices = [
            idx
            for idx, s in enumerate(result)
            if s.slot is None and s.item_id is None and s.wait is None
        ]
        if attack_indices:
            insert_at = attack_indices[-1]
            result[insert_at:insert_at] = empowers
    result.extend(suffix)
    return tuple(result)


def _has_spellblade(item: ItemData) -> bool:
    return any(
        (effect.get("trigger") or {}).get("event") == "spellblade" for effect in item.effects
    )


def load_candidate_pool(
    root: Path,
    item_groups: ItemGroups,
    *,
    champion_id: str,
) -> dict[str, CandidateItem]:
    """Load all 218 catalog items once and pre-index gold, tier, groups and legality."""
    model, _ = load_model(root)
    objects = model.get("objects") or []
    all_ids = [str(obj["id"]) for obj in objects]
    item_map = {item.id: item for item in items_from_model(model, all_ids)}
    catalog_ids = set(all_ids)
    pool: dict[str, CandidateItem] = {}
    for obj in objects:
        item_id = str(obj["id"])
        item = item_map[item_id]
        gold = int((obj.get("gold") or {}).get("total", 0))
        recipe = obj.get("recipe") or {}
        builds_into = [str(x) for x in (recipe.get("builds_into") or ()) if str(x) in catalog_ids]
        depth = recipe.get("depth")
        limits = item_groups.items.get(item_id)
        groups = limits.groups if limits is not None else ()
        req_champ = limits.required_champion if limits is not None else None
        slot_pinned = any(item_groups.groups[g].slot is not None for g in groups)
        is_boots = item_groups.has_boots([item_id])
        # Completed = no catalog upgrade (and >= 800g) OR tier-2 boots (depth == 2).
        is_completed = (not builds_into and gold >= COMPLETED_MIN_GOLD) or (is_boots and depth == 2)
        if req_champ is not None and req_champ.lower() != champion_id.lower():
            continue
        pool[item_id] = CandidateItem(
            item=item,
            gold=gold,
            is_boots=is_boots,
            is_completed=is_completed,
            verified_clean=_is_verified_clean(item),
            has_spellblade=_has_spellblade(item),
            groups=groups,
            required_champion=req_champ,
            slot_pinned=slot_pinned,
        )
    return pool


def _validate_constraints(
    constraints: OptimizeConstraints,
    pool: Mapping[str, CandidateItem],
    item_groups: ItemGroups,
    champion: ChampionData,
) -> tuple[str, ...]:
    if not 1 <= constraints.slots <= INVENTORY_SLOTS:
        raise StatsError(f"slots must be between 1 and {INVENTORY_SLOTS}, got {constraints.slots}")
    if constraints.budget is not None and constraints.budget < 0:
        raise StatsError(f"budget must be >= 0, got {constraints.budget}")
    if constraints.tier not in TIERS:
        raise StatsError(f"tier must be one of {sorted(TIERS)}, got {constraints.tier!r}")
    if constraints.top < 1:
        raise StatsError(f"top must be >= 1, got {constraints.top}")
    if constraints.beam_width < 1:
        raise StatsError(f"beam_width must be >= 1, got {constraints.beam_width}")
    if not 0 <= constraints.damage_mix_physical <= 1:
        raise StatsError("damage_mix_physical must be between 0 and 1")

    req = tuple(str(i) for i in constraints.required_items)
    forbid = {str(i) for i in constraints.forbidden_items}
    if len(set(req)) != len(req):
        raise StatsError("required_items cannot list the same item twice")
    overlap = sorted(set(req) & forbid)
    if overlap:
        raise StatsError(f"items cannot be both required and forbidden: {overlap}")
    missing = [i for i in req if i not in pool]
    if missing:
        raise StatsError(f"required items not available for {champion.id}: {missing}")
    if len(req) > constraints.slots:
        raise StatsError(f"required_items ({len(req)}) exceeds allowed slots ({constraints.slots})")
    if req:
        report = check_build(req, item_groups, patch=champion.patch, champion=champion.id)
        if not report.legal:
            problems = "; ".join(v.message for v in report.violations)
            raise StatsError(f"required_items are not a legal build: {problems}")
        if sum(1 for i in req if pool[i].has_spellblade) > 1:
            raise StatsError("required_items cannot include more than one Spellblade item")
    req_gold = sum(pool[i].gold for i in req)
    if constraints.budget is not None and req_gold > constraints.budget:
        raise StatsError(
            f"required_items cost {req_gold} gold, exceeding budget {constraints.budget}"
        )
    return tuple(sorted(req, key=lambda x: int(x)))


def _can_add(
    state: tuple[str, ...],
    candidate: CandidateItem,
    pool: Mapping[str, CandidateItem],
    item_groups: ItemGroups,
) -> bool:
    cid = candidate.item.id
    if cid in state:
        return False
    if candidate.has_spellblade and any(pool[existing].has_spellblade for existing in state):
        return False
    for group_key in candidate.groups:
        limit = item_groups.groups[group_key].max_ownable
        if limit is None:
            continue
        held = sum(1 for existing in state if group_key in pool[existing].groups)
        if held >= limit:
            return False
    return True


def _rank_key(build: BuildResult, objective: str) -> tuple[Any, ...]:
    """Deterministic ordering key: higher is better."""
    if objective in DEFENSE_OBJECTIVES:
        survived = 1 if build.metrics.get("survived") else 0
        return (
            survived,
            build.score,
            build.secondary_score,
            -build.total_gold,
            tuple(-int(i) for i in build.items),
        )
    return (
        build.score,
        build.secondary_score,
        -build.total_gold,
        tuple(-int(i) for i in build.items),
    )


class _BuildEvaluator:
    """Exact evaluator for any legal item combination under one objective."""

    def __init__(
        self,
        *,
        objective: str,
        champion: ChampionData,
        level: int,
        pool: Mapping[str, CandidateItem],
        item_groups: ItemGroups,
        issues: Sequence[DataIssue],
        derived: DerivedRecords | None,
        assumptions: Mapping[str, object] | None,
        inputs: Mapping[str, Any],
        kit: Kit | None,
        ranks: Mapping[str, int],
        target: Target | None,
        steps: Sequence[Step],
        crit_base: CritBase | None,
        holder_range: str | None,
        timeline: bool,
        target_count: int,
        incoming_hits: Sequence[IncomingHit],
        incoming_hits_for_sheet: Callable[[StatSheet], Sequence[IncomingHit]] | None,
        runes: Sequence[int],
        shards: Sequence[int],
        rune_data: RuneData | None,
        constraints: OptimizeConstraints,
    ) -> None:
        self.objective = objective
        self.champion = champion
        self.level = level
        self.pool = pool
        self.item_groups = item_groups
        self.issues = issues
        self.derived = derived
        self.assumptions = assumptions
        self.inputs = inputs
        self.kit = kit
        self.ranks = ranks
        self.target = target
        self.steps = steps
        self.crit_base = crit_base
        self.holder_range = holder_range
        self.timeline = timeline or objective == "dps"
        self.target_count = target_count
        self.incoming_hits = incoming_hits
        self.incoming_hits_for_sheet = incoming_hits_for_sheet
        self.runes = tuple(runes)
        self.shards = tuple(shards)
        self.rune_data = rune_data
        self.constraints = constraints
        self.has_ultimate = any(step.slot == "R" for step in steps)
        self.legality_label = (
            Label.DERIVED if item_groups.matches_patch(champion.patch) else Label.PENDING
        )

        # Precompute passive and validate rune page once (constant across item sets).
        self.combat_ctx = "rotation" if objective in ROTATION_OBJECTIVES else "stats"
        self.passive = sheet_passive_effects(
            kit, level, inputs, include_stacking=self.combat_ctx != "rotation"
        )
        self.needs_adaptive = False
        self.uses_mana = champion.resource == MANA_RESOURCE.get(champion.locale)
        self.ap_weight = (
            derived.value(champion.id, "adaptiveforceapweight") if derived is not None else None
        )
        if self.runes or self.shards:
            if rune_data is None:
                raise StatsError("runes/shards require lol-knowledge/derived/runes.json")
            report = check_page(self.runes, self.shards, rune_data, patch=champion.patch)
            if not report.legal:
                problems = "; ".join(report.violations)
                raise StatsError(f"rune page is not legal: {problems}")
            self.needs_adaptive = needs_adaptive_stat(self.runes, self.shards, rune_data)
        self.cache: dict[tuple[str, ...], BuildResult | None] = {}
        self.evaluations = 0

    def _make_sheet(self, items: tuple[ItemData, ...]) -> StatSheet:
        base_extras = tuple(self.passive.flats)
        if not self.runes and not self.shards:
            return build_stat_sheet(
                self.champion,
                self.level,
                items,
                self.issues,
                self.assumptions,
                self.derived,
                base_extras,
                extra_amplifiers=self.passive.amplifiers,
                extra_notes=self.passive.notes,
            )
        assert self.rune_data is not None
        adaptive, a_label, a_note = None, Label.DERIVED, ""
        if self.needs_adaptive:
            before = build_stat_sheet(
                self.champion,
                self.level,
                items,
                self.issues,
                self.assumptions,
                self.derived,
                base_extras,
            )
            bonus_ad = sum(
                (
                    p.value
                    for p in before["attack_damage"].contributions
                    if p.scope == "bonus" and not p.adaptive
                ),
                start=Fraction(0),
            )
            power = sum(
                (p.value for p in before["ability_power"].contributions if not p.adaptive),
                start=Fraction(0),
            )
            adaptive, a_label, a_note = adaptive_stat(bonus_ad, power, self.ap_weight)
        flats, percents = shard_contributions(
            self.shards,
            self.rune_data,
            level=self.level,
            patch=self.champion.patch,
            adaptive=adaptive,
            adaptive_label=a_label,
            adaptive_note=a_note,
        )
        has_boots = self.item_groups.has_boots([item.id for item in items]) if items else False
        rune_effects = minor_rune_effects(
            self.runes,
            self.rune_data,
            level=self.level,
            patch=self.champion.patch,
            items=items,
            uses_mana=self.uses_mana,
            has_boots=has_boots,
            inputs=self.inputs,
            adaptive=adaptive,
            adaptive_label=a_label,
            adaptive_note=a_note,
        )
        extra_notes = [*self.passive.notes, *rune_effects.notes]
        pending = list(rune_effects.pending)
        if self.combat_ctx != "rotation":
            extra_notes.extend(combat_rune_notes(self.runes, self.rune_data))
        return build_stat_sheet(
            self.champion,
            self.level,
            items,
            self.issues,
            self.assumptions,
            self.derived,
            (*base_extras, *flats, *rune_effects.flats),
            (*percents, *rune_effects.percents),
            tuple(pending),
            extra_amplifiers=(*self.passive.amplifiers, *rune_effects.amplifiers),
            extra_notes=tuple(extra_notes),
            move_speed_bonus_amp=rune_effects.move_speed_bonus_amp,
        )

    def evaluate(self, item_ids: tuple[str, ...]) -> BuildResult | None:
        key = tuple(sorted(item_ids, key=lambda x: int(x)))
        if key in self.cache:
            return self.cache[key]
        self.evaluations += 1
        candidates = [self.pool[i] for i in key]
        items = tuple(c.item for c in candidates)
        names = tuple(c.item.name for c in candidates)
        total_gold = sum(c.gold for c in candidates)
        sheet = self._make_sheet(items)
        result = self._score(key, names, total_gold, candidates, sheet)
        self.cache[key] = result
        return result

    def _score(
        self,
        item_ids: tuple[str, ...],
        names: tuple[str, ...],
        total_gold: int,
        candidates: Sequence[CandidateItem],
        sheet: StatSheet,
    ) -> BuildResult | None:
        obj = self.objective
        if obj in EHP_OBJECTIVES:
            ehp_p = effective_health(sheet, DamageType.PHYSICAL)
            ehp_m = effective_health(sheet, DamageType.MAGIC)
            if ehp_p.value is None or ehp_m.value is None:
                return None
            w_p = self.constraints.damage_mix_physical
            w_m = 1 - w_p
            if w_p == 1:
                ehp_mixed = ehp_p.value
            elif w_m == 1:
                ehp_mixed = ehp_m.value
            else:
                ehp_mixed = Fraction(1) / (w_p / ehp_p.value + w_m / ehp_m.value)
            if obj == "effective_health_physical":
                score = ehp_p.value
                base_labels = [ehp_p.label]
            elif obj == "effective_health_magic":
                score = ehp_m.value
                base_labels = [ehp_m.label]
            else:
                score = ehp_mixed
                base_labels = [ehp_p.label, ehp_m.label]
            notes: list[str] = []
            unmodelled_def = [
                c.item.id
                for c in candidates
                if c.item.effect_review != "complete" or _has_unmodelled_ehp_effect(c.item)
            ]
            if unmodelled_def:
                base_labels.append(Label.PENDING)
                notes.append(
                    f"items with unmodelled defensive effects ({', '.join(unmodelled_def)}): "
                    "defensive passives not modelled"
                )
            if sheet.pending_effects:
                base_labels.append(Label.PENDING)
                notes.extend(sheet.pending_effects)
            label = weakest([*base_labels, self.legality_label])
            return BuildResult(
                items=item_ids,
                item_names=names,
                total_gold=total_gold,
                score=score,
                secondary_score=-Fraction(total_gold),
                label=label,
                metrics={
                    "ehp_physical": float(ehp_p.value),
                    "ehp_magic": float(ehp_m.value),
                    "ehp_mixed": float(ehp_mixed),
                    "health": float(sheet["health"].total()),
                    "armor": float(sheet["armor"].total()),
                    "magic_resist": float(sheet["magic_resist"].total()),
                },
                notes=tuple(notes),
            )

        if obj in ROTATION_OBJECTIVES:
            assert self.kit is not None and self.target is not None
            eval_steps = (
                _steps_with_item_actives(self.steps, sheet.items, timeline=self.timeline)
                if self.constraints.use_item_actives
                else self.steps
            )
            try:
                outcome = evaluate_rotation(
                    self.kit,
                    sheet,
                    self.ranks,
                    self.target,
                    eval_steps,
                    self.crit_base,
                    holder_range=self.holder_range,
                    inputs=self.inputs,
                    timeline=self.timeline,
                    runes=self.runes,
                    rune_data=self.rune_data,
                    ap_weight=self.ap_weight,
                    target_count=self.target_count,
                )
            except RotationError, KitError, StatsError:
                return None
            if obj == "rotation_damage":
                score = outcome.total
                label = weakest([outcome.label, self.legality_label])
            elif obj == "dps":
                if outcome.damage_per_second is None:
                    raise StatsError(
                        "objective 'dps' requires a rotation with duration > 0 s "
                        "(include at least two basic attacks or a wait:<seconds> step)"
                    )
                score = outcome.damage_per_second
                label = weakest([outcome.label, self.legality_label])
            else:  # healing
                score = (
                    outcome.effective_healing
                    if outcome.effective_healing is not None
                    else outcome.healing
                )
                label = weakest([outcome.label, outcome.healing_label, self.legality_label])
            metrics: dict[str, Any] = {
                "total_damage": float(outcome.total),
                "primary_damage": float(outcome.primary_total),
                "secondary_damage": float(outcome.secondary_total),
                "healing": float(outcome.healing),
                "remaining_health": float(outcome.remaining_health),
                "lethal_step": outcome.lethal_step,
            }
            if outcome.duration is not None:
                metrics["duration"] = float(outcome.duration)
            if outcome.damage_per_second is not None:
                metrics["dps"] = float(outcome.damage_per_second)
            if outcome.total_shield_granted > 0:
                metrics["shield_granted"] = float(outcome.total_shield_granted)
            return BuildResult(
                items=item_ids,
                item_names=names,
                total_gold=total_gold,
                score=score,
                secondary_score=-Fraction(total_gold),
                label=label,
                metrics=metrics,
                notes=outcome.notes,
            )

        if obj in DEFENSE_OBJECTIVES:
            try:
                hits = (
                    self.incoming_hits_for_sheet(sheet)
                    if self.incoming_hits_for_sheet is not None
                    else self.incoming_hits
                )
                outcome = evaluate_defense(
                    sheet,
                    hits,
                    runes=self.runes,
                    rune_data=self.rune_data,
                    inputs=self.inputs,
                    timeline=self.timeline,
                )
            except StatsError, RotationError, KitError:
                return None
            if outcome.survived:
                score = outcome.remaining_health + outcome.remaining_shield
                secondary = score
            elif outcome.time_to_die is not None:
                score = outcome.time_to_die
                secondary = Fraction(outcome.lethal_step or 0)
            else:
                score = Fraction(outcome.lethal_step or 0)
                secondary = -outcome.total_damage_taken
            notes_def = list(outcome.notes)
            labels_def = [outcome.label, self.legality_label]
            unmodelled_def = [
                c.item.id
                for c in candidates
                if c.item.effect_review != "complete" or _has_excluded_defensive_effect(c.item)
            ]
            if unmodelled_def:
                labels_def.append(Label.PENDING)
                notes_def.append(
                    f"items with unmodelled defensive effects ({', '.join(unmodelled_def)}): "
                    "defensive passives not modelled"
                )
            return BuildResult(
                items=item_ids,
                item_names=names,
                total_gold=total_gold,
                score=score,
                secondary_score=secondary,
                label=weakest(labels_def),
                metrics={
                    "survived": outcome.survived,
                    "time_to_die": None
                    if outcome.time_to_die is None
                    else float(outcome.time_to_die),
                    "lethal_step": outcome.lethal_step,
                    "remaining_health": float(outcome.remaining_health),
                    "remaining_shield": float(outcome.remaining_shield),
                    "total_damage_taken": float(outcome.total_damage_taken),
                    "total_shield_granted": float(outcome.total_shield_granted),
                    "total_healing": float(outcome.total_healing),
                },
                notes=tuple(notes_def),
            )

        raise StatsError(f"unknown objective {obj!r}")


def _select_subpool(
    base_state: tuple[str, ...],
    candidates: Sequence[CandidateItem],
    evaluator: _BuildEvaluator,
    pool: Mapping[str, CandidateItem],
    item_groups: ItemGroups,
    constraints: OptimizeConstraints,
    objective: str,
) -> tuple[list[CandidateItem], int, int]:
    """Stage 1 pruning: rank individual candidates by marginal objective gain over base_state."""
    pruned_illegal = 0
    pruned_budget = 0
    base_gold = sum(pool[i].gold for i in base_state)
    baseline = evaluator.evaluate(base_state)
    base_key = _rank_key(baseline, objective) if baseline is not None else None

    scored_non_boots: list[tuple[tuple[Any, ...], CandidateItem]] = []
    boots_list: list[tuple[tuple[Any, ...], CandidateItem]] = []

    for cand in candidates:
        if not _can_add(base_state, cand, pool, item_groups):
            pruned_illegal += 1
            continue
        if constraints.budget is not None and base_gold + cand.gold > constraints.budget:
            pruned_budget += 1
            continue
        res = evaluator.evaluate((*base_state, cand.item.id))
        if res is None:
            continue
        rkey = _rank_key(res, objective)
        if cand.is_boots:
            boots_list.append((rkey, cand))
        else:
            scored_non_boots.append((rkey, cand))

    scored_non_boots.sort(key=lambda pair: pair[0], reverse=True)
    boots_list.sort(key=lambda pair: pair[0], reverse=True)

    # Keep top pool_limit non-boots + any synergy multiplier items that fit + top boots.
    selected: list[CandidateItem] = []
    selected_ids: set[str] = set()
    for rkey, cand in scored_non_boots[: constraints.pool_limit]:
        # Even if a candidate doesn't beat baseline alone (e.g. survive already survived),
        # keep it if it's in the top pool_limit.
        _ = (rkey, base_key)
        selected.append(cand)
        selected_ids.add(cand.item.id)
    for _, cand in scored_non_boots[constraints.pool_limit :]:
        if cand.item.id in SYNERGY_ITEMS and cand.item.id not in selected_ids:
            selected.append(cand)
            selected_ids.add(cand.item.id)
    boots_cap = len(boots_list) if constraints.require_boots else min(4, len(boots_list))
    for _, cand in boots_list[:boots_cap]:
        if cand.item.id not in selected_ids:
            selected.append(cand)
            selected_ids.add(cand.item.id)

    return selected, pruned_illegal, pruned_budget


def _beam_search(
    base_state: tuple[str, ...],
    subpool: Sequence[CandidateItem],
    evaluator: _BuildEvaluator,
    pool: Mapping[str, CandidateItem],
    item_groups: ItemGroups,
    constraints: OptimizeConstraints,
    objective: str,
) -> tuple[list[BuildResult], int, int, int]:
    """Stage 2: slot-by-slot deterministic beam search + 1-swap local refinement."""
    pruned_illegal = 0
    pruned_budget = 0
    pruned_beam = 0

    all_valid_results: dict[tuple[str, ...], BuildResult] = {}

    def record_if_complete(state: tuple[str, ...], res: BuildResult) -> None:
        if constraints.require_boots and not item_groups.has_boots(state):
            return
        all_valid_results[res.items] = res

    base_res = evaluator.evaluate(base_state)
    if base_res is not None:
        record_if_complete(base_state, base_res)

    beam: list[tuple[str, ...]] = [base_state]
    remaining_slots = constraints.slots - len(base_state)

    for depth in range(1, remaining_slots + 1):
        must_pick_boots_now = constraints.require_boots and depth == remaining_slots
        next_candidates: dict[tuple[str, ...], BuildResult] = {}
        for state in beam:
            state_gold = sum(pool[i].gold for i in state)
            has_boots = item_groups.has_boots(state)
            for cand in subpool:
                if must_pick_boots_now and not has_boots and not cand.is_boots:
                    pruned_illegal += 1
                    continue
                if constraints.budget is not None and state_gold + cand.gold > constraints.budget:
                    pruned_budget += 1
                    continue
                if not _can_add(state, cand, pool, item_groups):
                    pruned_illegal += 1
                    continue
                nxt = tuple(sorted((*state, cand.item.id), key=lambda x: int(x)))
                if nxt in next_candidates:
                    continue
                res = evaluator.evaluate(nxt)
                if res is None:
                    continue
                next_candidates[nxt] = res
                record_if_complete(nxt, res)
        if not next_candidates:
            break
        ranked = sorted(
            next_candidates.values(),
            key=lambda b: _rank_key(b, objective),
            reverse=True,
        )
        if len(ranked) > constraints.beam_width:
            pruned_beam += len(ranked) - constraints.beam_width
            ranked = ranked[: constraints.beam_width]
        beam = [b.items for b in ranked]

    # Stage 3: 1-swap polish on the top K complete builds to escape beam local optima.
    required_set = set(base_state)
    finalists = sorted(
        all_valid_results.values(),
        key=lambda b: _rank_key(b, objective),
        reverse=True,
    )[: constraints.top]
    for finalist in finalists:
        current = finalist
        improved = True
        while improved:
            improved = False
            best_local = current
            best_key = _rank_key(current, objective)
            for idx, item_id in enumerate(current.items):
                if item_id in required_set:
                    continue
                reduced = current.items[:idx] + current.items[idx + 1 :]
                reduced_gold = sum(pool[i].gold for i in reduced)
                for cand in subpool:
                    if cand.item.id == item_id:
                        continue
                    if (
                        constraints.budget is not None
                        and reduced_gold + cand.gold > constraints.budget
                    ):
                        pruned_budget += 1
                        continue
                    if not _can_add(reduced, cand, pool, item_groups):
                        pruned_illegal += 1
                        continue
                    swapped = tuple(sorted((*reduced, cand.item.id), key=lambda x: int(x)))
                    if constraints.require_boots and not item_groups.has_boots(swapped):
                        continue
                    res = evaluator.evaluate(swapped)
                    if res is None:
                        continue
                    record_if_complete(swapped, res)
                    rkey = _rank_key(res, objective)
                    if rkey > best_key:
                        best_local = res
                        best_key = rkey
                        improved = True
            current = best_local

    return list(all_valid_results.values()), pruned_illegal, pruned_budget, pruned_beam


def optimize_build(
    root: Path,
    champion: ChampionData,
    level: int,
    objective: str,
    *,
    constraints: OptimizeConstraints | None = None,
    issues: Sequence[DataIssue] = (),
    derived: DerivedRecords | None = None,
    assumptions: Mapping[str, object] | None = None,
    inputs: Mapping[str, Any] | None = None,
    kit: Kit | None = None,
    ranks: Mapping[str, int] | None = None,
    target: Target | None = None,
    steps: Sequence[Step] = (),
    crit_base: CritBase | None = None,
    holder_range: str | None = None,
    timeline: bool = False,
    target_count: int = 1,
    incoming_hits: Sequence[IncomingHit] = (),
    incoming_hits_for_sheet: Callable[[StatSheet], Sequence[IncomingHit]] | None = None,
    runes: Sequence[int] = (),
    shards: Sequence[int] = (),
    rune_data: RuneData | None = None,
) -> OptimizeOutcome:
    """Search legal builds for ``champion`` optimizing ``objective`` under ``constraints``."""
    t0 = time.perf_counter()
    if objective not in OBJECTIVES:
        raise StatsError(f"objective must be one of {sorted(OBJECTIVES)}, got {objective!r}")
    if objective in ROTATION_OBJECTIVES and (kit is None or target is None or not steps):
        raise StatsError(
            f"objective {objective!r} requires a champion kit, target and rotation steps"
        )
    if objective in DEFENSE_OBJECTIVES and not incoming_hits and incoming_hits_for_sheet is None:
        raise StatsError("objective 'time_to_die' requires incoming hits or an enemy rotation")

    item_groups = load_item_groups(root)
    if item_groups is None:
        raise StatsError("build optimization requires lol-knowledge/derived/item-groups.json")

    cfg = constraints or OptimizeConstraints()
    pool = load_candidate_pool(root, item_groups, champion_id=champion.id)
    base_state = _validate_constraints(cfg, pool, item_groups, champion)

    forbid = {str(i) for i in cfg.forbidden_items}
    eligible = [
        cand
        for cand in pool.values()
        if not cand.slot_pinned
        and cand.item.id not in forbid
        and (cfg.tier == "all" or cand.is_completed)
    ]
    eligible.sort(key=lambda c: int(c.item.id))
    verified_eligible = [
        c
        for c in eligible
        if c.verified_clean
        and (objective not in EHP_OBJECTIVES or not _has_unmodelled_ehp_effect(c.item))
        and (objective not in DEFENSE_OBJECTIVES or not _has_excluded_defensive_effect(c.item))
    ]

    evaluator = _BuildEvaluator(
        objective=objective,
        champion=champion,
        level=level,
        pool=pool,
        item_groups=item_groups,
        issues=issues,
        derived=derived,
        assumptions=assumptions,
        inputs=inputs or {},
        kit=kit,
        ranks=ranks or {},
        target=target,
        steps=steps,
        crit_base=crit_base,
        holder_range=holder_range,
        timeline=timeline,
        target_count=target_count,
        incoming_hits=incoming_hits,
        incoming_hits_for_sheet=incoming_hits_for_sheet,
        runes=runes,
        shards=shards,
        rune_data=rune_data,
        constraints=cfg,
    )

    total_pruned_illegal = 0
    total_pruned_budget = 0
    total_pruned_beam = 0
    collected: dict[tuple[str, ...], BuildResult] = {}

    # Pass A: Search verified-clean pool first so OPT-03 always finds optimal verified builds.
    if verified_eligible:
        v_subpool, pi, pb = _select_subpool(
            base_state, verified_eligible, evaluator, pool, item_groups, cfg, objective
        )
        total_pruned_illegal += pi
        total_pruned_budget += pb
        v_results, pi2, pb2, pbeam = _beam_search(
            base_state, v_subpool, evaluator, pool, item_groups, cfg, objective
        )
        total_pruned_illegal += pi2
        total_pruned_budget += pb2
        total_pruned_beam += pbeam
        for b in v_results:
            collected[b.items] = b

    # Pass B: Search full pool (unless --only-verified) to expose pending builds separately.
    if not cfg.only_verified and eligible:
        f_subpool, pi, pb = _select_subpool(
            base_state, eligible, evaluator, pool, item_groups, cfg, objective
        )
        total_pruned_illegal += pi
        total_pruned_budget += pb
        f_results, pi2, pb2, pbeam = _beam_search(
            base_state, f_subpool, evaluator, pool, item_groups, cfg, objective
        )
        total_pruned_illegal += pi2
        total_pruned_budget += pb2
        total_pruned_beam += pbeam
        for b in f_results:
            collected[b.items] = b

    # Final legality verification (OBJ-13) on returned top builds.
    ranked_all = sorted(
        collected.values(),
        key=lambda b: _rank_key(b, objective),
        reverse=True,
    )
    verified_builds = tuple(b for b in ranked_all if b.verified)[: cfg.top]
    pending_builds = tuple(b for b in ranked_all if not b.verified)[: cfg.top]
    all_builds = tuple(ranked_all[: cfg.top])

    for build in (*verified_builds, *pending_builds):
        rep = check_build(build.items, item_groups, patch=champion.patch, champion=champion.id)
        if not rep.legal:
            raise StatsError(
                f"internal optimizer legality error for {build.items}: "
                + "; ".join(v.message for v in rep.violations)
            )

    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    notes: list[str] = [
        f"search strategy: marginal relevance pre-filter (pool_limit={cfg.pool_limit}) + "
        f"beam search (width={cfg.beam_width}) + 1-swap polish; heuristic pruning does not "
        "guarantee a global optimum across all C(N,k) combinations",
    ]
    if cfg.only_verified:
        notes.append(
            "only_verified=True: items with pending effect review or excluded damage effects "
            "were excluded from the search space"
        )
    if not verified_builds:
        notes.append(
            "no verified (Oficial/Derivado) builds found under the given scenario and constraints; "
            "all returned builds depend on Pendiente de verificación inputs"
        )

    outcome_label = weakest(b.label for b in verified_builds) if verified_builds else Label.PENDING
    return OptimizeOutcome(
        objective=objective,
        champion=champion.id,
        level=level,
        patch=champion.patch,
        constraints=cfg,
        verified_builds=verified_builds,
        pending_builds=pending_builds,
        all_builds=all_builds,
        stats=SearchStats(
            candidate_pool_size=len(eligible),
            verified_pool_size=len(verified_eligible),
            states_evaluated=evaluator.evaluations,
            pruned_illegal=total_pruned_illegal,
            pruned_budget=total_pruned_budget,
            pruned_beam=total_pruned_beam,
            elapsed_ms=elapsed_ms,
            strategy=f"beam(w={cfg.beam_width},pool={cfg.pool_limit})+1swap",
        ),
        label=outcome_label,
        notes=tuple(notes),
    )
