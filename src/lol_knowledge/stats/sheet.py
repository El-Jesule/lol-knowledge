"""Stat sheet: every statistic as a list of sourced contributions."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from fractions import Fraction
from typing import Any

from ..damage import format_number, format_percent, to_fraction
from ..errors import DamageInputError, StatsError
from ..formula import FormulaError, evaluate_formula
from ..objects.transforms import TEAR_BASE_TO_TRANSFORM, TEAR_STACK_MAX
from .data import ChampionData, ItemData, transformed_tear_item
from .derived import DerivedRecords
from .growth import check_level, growth_multiplier
from .issues import DataIssue
from .labels import EVIDENCE_LABEL, Label, weakest
from .registry import (
    ATTACK_SPEED_RULES,
    CRIT_RULES,
    MOVE_SPEED_RULES,
    STATS,
    TENACITY_RULES,
    Stacking,
    StatDef,
    Unit,
    stat,
)

# Data Dragon field names: (stat, base field, growth field or None)
CHAMPION_FIELDS: tuple[tuple[str, str, str | None], ...] = (
    ("health", "hp", "hpperlevel"),
    ("mana", "mp", "mpperlevel"),
    ("armor", "armor", "armorperlevel"),
    ("magic_resist", "spellblock", "spellblockperlevel"),
    ("attack_damage", "attackdamage", "attackdamageperlevel"),
    ("health_regen", "hpregen", "hpregenperlevel"),
    ("mana_regen", "mpregen", "mpregenperlevel"),
    ("move_speed", "movespeed", None),
    # Attack speed growth is bonus attack speed (see _attack_speed_growth).
    ("attack_speed", "attackspeed", None),
)
ATTACK_SPEED_GROWTH = "attackspeedperlevel"  # percentage points per level
ATTACK_SPEED_RATIO = "attackspeedratio"  # derived from the client; not in Data Dragon
# Champion-specific attack speed rules (attack-speed.md):
# - Bel'Veth: passive removes the 3.0 attack speed cap (cap = None).
# - Zeri: Q caps attack speed at 1.5 and converts 60% of excess bonus AS into bonus AD.
# - Jhin: Whisper fixes attack speed (+3% per level growth curve, 0 ratio) and amplifies
#   total AD by (4..44% by level + 35% of crit chance + 30% of bonus attack speed).
ZERI_ATTACK_SPEED_CAP = Fraction(3, 2)
ZERI_EXCESS_AS_AD = Fraction(60)  # 0.6 AD per 1% (0.01) of excess bonus attack speed
JHIN_FIXED_AS_GROWTH = Fraction(3, 100)  # +3% per level with standard growth_multiplier
JHIN_AD_PERCENT_BY_LEVEL: tuple[int, ...] = (
    4,
    5,
    6,
    7,
    8,
    9,
    10,
    11,
    12,
    14,
    16,
    20,
    24,
    28,
    32,
    36,
    40,
    44,
)
JHIN_CRIT_TO_AD_PERCENT = Fraction(35)  # +35% total AD per 100% crit chance
JHIN_AS_TO_AD_PERCENT = Fraction(30)  # +30% total AD per 100% bonus attack speed
# Data Dragon crit chance base and growth; 0 for every champion (critical-strike.md, C8).
CRIT_FIELDS = ("crit", "critperlevel")
# Cassiopeia's passive increases the effectiveness of movement speed bonuses by
# 5% + 1.8% * (level - 1) = 5%..35.6% (move-speed.md, M5; CassiopeiaPassive.PercentHasteMod).
CASSIOPEIA_MS_AMP_BASE = Fraction(5, 100)
CASSIOPEIA_MS_AMP_PER_LEVEL = Fraction(18, 1000)
# Hecarim's passive (Warpath, HecarimPassive in client 16.23): converts 12..24% of
# effective (post-soft-cap) bonus movement speed into bonus AD, +2% at levels 3/6/9/12/15/18.
HECARIM_WARPATH_BY_LEVEL: tuple[Fraction, ...] = (
    Fraction(12, 100),
    Fraction(12, 100),
    Fraction(14, 100),
    Fraction(14, 100),
    Fraction(14, 100),
    Fraction(16, 100),
    Fraction(16, 100),
    Fraction(16, 100),
    Fraction(18, 100),
    Fraction(18, 100),
    Fraction(18, 100),
    Fraction(20, 100),
    Fraction(20, 100),
    Fraction(20, 100),
    Fraction(22, 100),
    Fraction(22, 100),
    Fraction(22, 100),
    Fraction(24, 100),
)
# Adaptive force conversion: 1 adaptive force = 0.6 bonus AD or 1.0 AP (runes.md).
ADAPTIVE_AD_PER_AP = Fraction(3, 5)
RUNES_RULES = "lol-knowledge/mechanics/runes.md"
# Yasuo's and Yone's passives (critical-strike.md, C9): their crit chance from every
# other source is doubled, and each 1 % above 100 % becomes 0.5 bonus attack damage.
CRIT_CHANCE_KITS = frozenset({"Yasuo", "Yone"})
CRIT_CHANCE_KIT_MULTIPLIER = 2
EXCESS_CRIT_AD = 50  # bonus AD per 1.0 (100 %) of excess crit chance: 0.5 per 1 %
# Global passive stat conversions (passives.md, client 16.23 base DataValues):
PASSIVES_RULES = "lol-knowledge/mechanics/passives.md"
VLADIMIR_HP_PER_AP = Fraction(30)  # VladimirBloodGorged.HPforAP = 30
VLADIMIR_HP_PER_AP_GAIN = Fraction(8, 5)  # VladimirBloodGorged.APRatioBonusHP = 1.6
PYKE_HP_PER_AD = Fraction(14)  # PykePassive.HPPerBAD = 14
RYZE_MANA_PCT_PER_100_AP = Fraction(10, 100)  # RyzePassive.PercentManaIncrease = 10 / 100 AP
ORNN_BASE_STAT_AMP = Fraction(10, 100)  # OrnnP.BaseStatAmp = 0.10
ORNN_MASTERWORK_STAT_AMP = Fraction(4, 100)  # OrnnP.AdditionalMythicStatAmp = 0.04
ORNN_MAX_MASTERWORKS = 5
RAMMUS_ARMOR_TO_AD = Fraction(15, 100)  # RammusP.ArmorRatio = 0.15
RAMMUS_MR_TO_AD = Fraction(15, 100)  # RammusP.MagicResistRatio = 0.15
MANA_STATS = frozenset({"mana", "mana_regen"})
MANA_RESOURCE = {"es_ES": "Maná", "en_US": "Mana"}
ENERGY_RESOURCE = {"es_ES": "Energía", "en_US": "Energy"}
NO_RESOURCE = {"es_ES": frozenset({"", "Nada"}), "en_US": frozenset({"", "None"})}


def adaptive_stat(
    bonus_attack_damage: Fraction, ability_power: Fraction, ap_weight: Fraction | None
) -> tuple[str, Label, str]:
    """Which stat adaptive force gives: the higher bonus; on a tie, the champion's.

    On a tie the client's ``mAdaptiveForceToAbilityPowerWeight`` decides: 1 gives
    ability power; absent gives attack damage. That reading is not confirmed.
    """
    if bonus_attack_damage > ability_power:
        return "attack_damage", Label.DERIVED, "adaptive: bonus AD is higher than AP"
    if ability_power > bonus_attack_damage:
        return "ability_power", Label.DERIVED, "adaptive: AP is higher than bonus AD"
    chosen = "ability_power" if ap_weight == 1 else "attack_damage"
    note = (
        f"adaptive: bonus AD and AP are equal; the champion's adaptiveforceapweight "
        f"({'1' if ap_weight == 1 else 'absent'}) is read as {chosen} ({RUNES_RULES})"
    )
    return chosen, Label.PENDING, note


@dataclass(frozen=True)
class Contribution:
    value: Fraction
    scope: str  # "base" (champion and growth) or "bonus" (items, assumptions)
    source: str
    label: Label
    note: str = ""
    # True for a share of a total (Rabadon's Deathcap); other amplifiers use the
    # total without it, since amplifiers do not compound.
    amplifier: bool = False
    # True for the attack speed share of bonus attack speed (ratio x bonus).
    scaled: bool = False
    # Tenacity stacking group when a non-item source declares it (tenacity.md).
    tenacity_group: str | None = None
    # True when granted as adaptive force (excluded when resolving adaptive tie-breakers).
    adaptive: bool = False
    # True for move_speed entries derived from percent MS, Cassiopeia passive, or Celerity.
    ms_derived: bool = False
    # True for stat conversions fed by resolved move_speed (Hecarim Warpath, Swiftmarch).
    derived_from_ms: bool = False


class StatBlocked(StatsError):
    """A statistic cannot be totalled; the message says why."""


@dataclass(frozen=True)
class StatValue:
    definition: StatDef
    contributions: tuple[Contribution, ...] = ()
    blocked: str | None = None

    @property
    def status(self) -> str:
        if self.blocked:
            return "blocked"
        return "resolved" if self.definition.resolvable else "pending"

    @property
    def label(self) -> Label:
        labels = [item.label for item in self.contributions]
        if self.soft_capped:
            labels.append(Label.DERIVED)  # the soft cap rule comes from secondary sources
        return weakest(labels)

    def _check(self) -> None:
        if self.blocked:
            raise StatBlocked(f"{self.definition.id}: {self.blocked}")
        if not self.definition.resolvable:
            raise StatBlocked(f"{self.definition.id}: {self.definition.pending}")

    def _uncapped(self) -> Fraction:
        self._check()
        values = [item.value for item in self.contributions]
        if self.definition.stacking is Stacking.MULTIPLICATIVE:
            return 1 - math.prod((1 - value for value in values), start=Fraction(1))
        return sum(values, start=Fraction(0))

    def total(self) -> Fraction:
        total = self._uncapped()
        cap = self.definition.cap
        if cap is not None:
            total = min(total, cap)
        soft_cap = self.definition.soft_cap
        return total if soft_cap is None else soft_cap(total)

    def raw(self) -> Fraction:
        """The total before any cap or soft cap."""
        return self._uncapped()

    @property
    def soft_capped(self) -> bool:
        """Whether a soft cap changed the total."""
        soft_cap = self.definition.soft_cap
        if soft_cap is None or self.status != "resolved":
            return False
        total = self._uncapped()
        return soft_cap(total) != total

    @property
    def capped(self) -> bool:
        """Whether the contributions add up to more than the statistic's cap."""
        cap = self.definition.cap
        return cap is not None and self.status == "resolved" and self._uncapped() > cap

    def scoped(self, scope: str) -> Fraction:
        """Total of one scope (``base`` or ``bonus``) for additive statistics."""
        self._check()
        if self.definition.stacking is not Stacking.ADDITIVE:
            raise StatsError(f"{self.definition.id}: scopes only apply to additive stats")
        return sum(
            (item.value for item in self.contributions if item.scope == scope), start=Fraction(0)
        )

    def sources(self) -> tuple[Fraction, ...]:
        """Each contribution separately, for engines that stack sources themselves."""
        self._check()
        return tuple(item.value for item in self.contributions if item.value)


@dataclass(frozen=True)
class AttackSpeedRatio:
    """The client ratio that turns bonus attack speed into attack speed."""

    value: Fraction
    label: Label
    source: str
    note: str = ""


@dataclass(frozen=True)
class PostMsEffect:
    """An always-on item stat modifier evaluated after move_speed soft caps (e.g. Swiftmarch)."""

    stat: str  # target stat id or "adaptive_force"
    formula: Mapping[str, Any]
    source: str
    label: Label
    note: str = ""


@dataclass(frozen=True)
class StatSheet:
    champion: ChampionData
    level: int
    items: tuple[ItemData, ...]
    assumptions: Mapping[str, Fraction]
    values: Mapping[str, StatValue]
    notes: tuple[str, ...] = field(default=())
    # The champion's attack speed ratio, to rescale a temporary bonus (rotations).
    attack_speed_ratio: AttackSpeedRatio | None = None
    # Sources given to the sheet whose effects are not modelled (tree runes): they
    # weaken any damage computed from the sheet.
    pending_effects: tuple[str, ...] = ()
    # Move-speed context for dynamic rotation buffs (flat/% MS -> Warpath / Swiftmarch).
    move_speed_percents: tuple[Contribution, ...] = ()
    move_speed_bonus_amp: Contribution | None = None
    post_ms_effects: tuple[PostMsEffect, ...] = ()
    ap_weight: Fraction | None = None
    holder_range: str | None = None
    amplifiers: tuple[StatAmplifier, ...] = ()

    def __getitem__(self, stat_id: str) -> StatValue:
        try:
            return self.values[stat_id]
        except KeyError as exc:
            raise StatsError(f"unknown stat {stat_id!r}") from exc


def _ungrouped_tenacity(extra: Contribution) -> Contribution:
    """Non-item tenacity: its stacking group is unknown, so it is stacked as group A."""
    note = f"stacking group not declared; multiplied with items as group A (see {TENACITY_RULES})"
    return replace(extra, label=Label.PENDING, note=f"{extra.note}; {note}" if extra.note else note)


def _percent_amount(
    definition: StatDef, percent: Contribution, current: Sequence[Contribution]
) -> Contribution:
    """An item's percentage as an amount: of the base, or of every flat contribution."""
    if definition.percent_of == "base":
        reference = [item for item in current if item.scope == "base"]
    else:
        reference = list(current)
    total = sum((item.value for item in reference), start=Fraction(0))
    note = f"{format_percent(percent.value)} of {definition.percent_of} {format_number(total)}"
    if percent.note:
        note += f"; {percent.note}"
    return replace(
        percent,
        value=percent.value * total,
        label=weakest([percent.label, *(item.label for item in reference)]),
        note=note,
    )


# Assumptions under which a catalog effect becomes a stat (objects/README.md).
SCENARIO_NOTES = {"max_stacks": "scenario: maximum stacks"}


def sheet_effect_reason(effect: Mapping[str, Any]) -> str | None:
    """Why the stat sheet applies ``effect`` as stats, or ``None`` if it does not.

    The sheet takes effects declared under a scenario and unconditional
    (``always``) effects made only of stat modifiers. Rotations leave both to it.
    """
    components = effect.get("components") or ()
    stats_only = bool(components) and all(
        component.get("kind") == "stat_modifier" for component in components
    )
    if effect.get("scenario") is not None and stats_only:
        return f"scenario {effect['scenario']}"
    if (
        (effect.get("trigger") or {}).get("event") == "always"
        and not effect.get("conditions")
        and stats_only
    ):
        return "always"
    return None


@dataclass(frozen=True)
class StatAmplifier:
    """``percent`` % of a stat's total, added once every other amount is known."""

    stat: str
    percent: Fraction
    source: str
    label: Label
    note: str = ""


def _formula_uses_stat(formula: Any, stat_name: str) -> bool:
    """Whether ``formula`` references ``stat_name`` anywhere in its tree."""
    if not isinstance(formula, Mapping):
        return False
    if formula.get("stat") == stat_name:
        return True
    for value in formula.values():
        if isinstance(value, Mapping) and _formula_uses_stat(value, stat_name):
            return True
        if (
            isinstance(value, Sequence)
            and not isinstance(value, (str, bytes))
            and any(_formula_uses_stat(item, stat_name) for item in value)
        ):
            return True
    return False


def _sheet_effects(
    item: ItemData,
    level: int,
    base_stats: Mapping[str, Fraction] = (),
    base_labels: Mapping[str, Label] = (),
    blocked_stats: Mapping[str, str] = (),
    holder_range: str | None = None,
) -> tuple[list[tuple[str, Contribution]], list[StatAmplifier], list[PostMsEffect]]:
    """Stats from the effects of ``item`` that the sheet applies (``sheet_effect_reason``).

    A ``flat`` component adds its amount in the catalog unit: percentage points
    for fraction stats (25 -> 0.25), the stat's own unit otherwise. A
    ``percent`` component with scope ``total`` amplifies the total of an amount
    stat (Rabadon's Deathcap: +30 % ability power). Formulas may read resolved
    champion ``base_*`` stats (e.g. Sterak's Gage: 50 % base AD). Effects that
    read ``move_speed`` or grant ``adaptive_force`` are returned in
    ``post_ms_effects`` so they run after movement speed percentages and soft caps.
    """
    stat_env = dict(base_stats)
    label_env = dict(base_labels)
    flat: list[tuple[str, Contribution]] = []
    amplifiers: list[StatAmplifier] = []
    post_ms: list[PostMsEffect] = []
    for effect in item.effects:
        reason = sheet_effect_reason(effect)
        if reason is None:
            continue
        title = f"item {item.id} {effect.get('id')}"
        scenario = effect.get("scenario")
        note = "" if scenario is None else SCENARIO_NOTES.get(str(scenario))
        if note is None:
            raise StatsError(f"{title}: scenario {scenario!r} is not modelled")
        source = f"data:item:{item.id} effect {effect.get('id')} ({item.game_version})"
        status = effect.get("model_status")
        label = EVIDENCE_LABEL.get(str(effect.get("evidence_confidence")), Label.DERIVED)
        for component in effect.get("components") or ():
            mode = component.get("mode")
            if component.get("kind") != "stat_modifier" or mode not in {"flat", "percent"}:
                raise StatsError(f"{title}: only stat modifiers can be sheet stats")
            raw_stat = str(component.get("stat"))
            formula = component.get("formula")
            is_adaptive = raw_stat == "adaptive_force"
            if status != "evaluable":
                why = f"effect {status}, not applied"
                why = f"{note}; {why}" if note else why
                target_id = "attack_damage" if is_adaptive else _receiver(raw_stat).id
                flat.append(
                    (target_id, Contribution(Fraction(0), "bonus", source, Label.PENDING, why))
                )
                continue
            if is_adaptive or (mode == "flat" and _formula_uses_stat(formula, "move_speed")):
                if mode != "flat":
                    raise StatsError(f"{title}: post-move-speed effects must be flat")
                if not is_adaptive:
                    raw_stat = _receiver(raw_stat).id
                post_ms.append(PostMsEffect(raw_stat, formula, source, label, note))
                continue
            definition = _receiver(raw_stat)
            if mode == "percent" and (
                scenario is not None
                or component.get("scope") != "total"
                or definition.unit is not Unit.AMOUNT
            ):
                raise StatsError(f"{title}: only always effects amplify a total amount")
            try:
                evaluated = evaluate_formula(
                    formula, stat_env, holder_range=holder_range, level=level
                )
            except FormulaError as exc:
                if definition.id in blocked_stats:
                    continue
                raise StatsError(f"{title}: {exc}") from exc
            amount = evaluated.exact
            part_label = weakest(
                [label, *(label_env[k] for k in evaluated.dependencies if k in label_env)]
            )
            if mode == "percent":
                amplifiers.append(StatAmplifier(definition.id, amount, source, part_label))
                continue
            value = effect_amount(definition.id, amount)
            if definition.unit is Unit.FRACTION and not 0 <= value <= 1:
                raise StatsError(f"{title}: {value} is not a fraction 0..1")
            flat.append((definition.id, Contribution(value, "bonus", source, part_label, note)))
    return flat, amplifiers, post_ms


def _amplified(
    amplifier: StatAmplifier, current: Sequence[Contribution], *, compounded: bool = False
) -> Contribution:
    """The amplifier's share of the total of ``current`` (amplifiers do not compound)."""
    total = sum((item.value for item in current), start=Fraction(0))
    note = f"{format_number(amplifier.percent)}% of the total"
    if amplifier.note:
        note = f"{amplifier.note}; {note}"
    label = weakest([amplifier.label, *(item.label for item in current)])
    if compounded:
        label = Label.PENDING
        note += "; added to another amplifier of the same total, which is not verified"
    return Contribution(
        total * amplifier.percent / 100,
        "bonus",
        amplifier.source,
        label,
        note,
        amplifier=True,
    )


# Statistics that feed others when the sheet is built; a bonus added afterwards
# would not reach them (bonus attack speed is rescaled by ``with_bonus``).
_FEEDING_STATS = frozenset({"attack_speed", "crit_chance"})


def effect_amount(stat_id: str, value: Fraction) -> Fraction:
    """A catalog amount in the stat's unit: percentage points for fraction stats."""
    return value / 100 if _receiver(stat_id).unit is Unit.FRACTION else value


def _recompute_move_speed(
    sheet: StatSheet,
    *,
    extra_flat: Contribution | None = None,
    extra_percent: Contribution | None = None,
) -> StatSheet:
    """Recompute move_speed (with % MS, Cassiopeia, Celerity, soft caps) and MS->damage stats."""
    raw_flats = [item for item in sheet["move_speed"].contributions if not item.ms_derived]
    if extra_flat is not None:
        raw_flats.append(extra_flat)
    raw_percents = list(sheet.move_speed_percents)
    if extra_percent is not None:
        raw_percents.append(extra_percent)
    resolved_ms = _resolve_move_speed(
        sheet.champion.id,
        sheet.level,
        raw_flats,
        raw_percents,
        sheet.move_speed_bonus_amp,
    )
    values = dict(sheet.values)
    ms_value = replace(sheet["move_speed"], contributions=tuple(resolved_ms))
    values["move_speed"] = ms_value

    if sheet.champion.id == "Hecarim" or sheet.post_ms_effects:
        target_ids = {"attack_damage", "ability_power"}
        for eff in sheet.post_ms_effects:
            if eff.stat != "adaptive_force":
                target_ids.add(eff.stat)
        static_amps_by_stat: dict[str, list[StatAmplifier]] = {}
        static_amp_sources: dict[str, set[str]] = {}
        for amp in sheet.amplifiers:
            if amp.stat in target_ids:
                static_amps_by_stat.setdefault(amp.stat, []).append(amp)
                static_amp_sources.setdefault(amp.stat, set()).add(amp.source)
        contrib_map: dict[str, list[Contribution]] = {}
        for stat_id in target_ids:
            amp_sources = static_amp_sources.get(stat_id, set())
            contrib_map[stat_id] = [
                c
                for c in values[stat_id].contributions
                if not c.derived_from_ms and not (c.amplifier and c.source in amp_sources)
            ]
        _apply_ms_conversions(
            sheet.champion.id,
            sheet.level,
            ms_value,
            sheet.post_ms_effects,
            contrib_map,
            ap_weight=sheet.ap_weight,
            holder_range=sheet.holder_range,
        )
        for stat_id, amps in static_amps_by_stat.items():
            ref = [c for c in contrib_map[stat_id] if not c.amplifier]
            for amp in amps:
                contrib_map[stat_id].append(_amplified(amp, ref))
        for stat_id, items_list in contrib_map.items():
            values[stat_id] = replace(values[stat_id], contributions=tuple(items_list))
    return replace(sheet, values=values, move_speed_percents=tuple(raw_percents))


def _added(sheet: StatSheet, stat_id: str, contribution: Contribution) -> StatSheet:
    definition = _receiver(stat_id)
    if definition.id == "move_speed":
        return _recompute_move_speed(sheet, extra_flat=contribution)
    speed = definition.id == "attack_speed_bonus"
    if definition.id in _FEEDING_STATS:
        raise StatsError(f"{definition.id}: feeds other stats; it takes no temporary bonus")
    if definition.unit is Unit.FRACTION and not 0 <= contribution.value <= 1:
        raise StatsError(f"{definition.id}: {contribution.value} is not a fraction 0..1")
    value = sheet[definition.id]
    values = dict(sheet.values)
    values[definition.id] = replace(value, contributions=(*value.contributions, contribution))
    if speed:
        values["attack_speed"] = _rescaled(sheet, values[definition.id].contributions)
    return replace(sheet, values=values)


def _rescaled(sheet: StatSheet, bonus: Sequence[Contribution]) -> StatValue:
    """Attack speed again from a changed bonus attack speed."""
    current = sheet["attack_speed"]
    if current.blocked:
        raise StatsError(f"attack_speed: {current.blocked}")
    scaled = _scaled_attack_speed(sheet.champion, bonus, sheet.attack_speed_ratio)
    if isinstance(scaled, str):
        raise StatsError(f"attack_speed: {scaled}")
    kept = tuple(item for item in current.contributions if not item.scaled)
    return replace(current, contributions=kept if scaled is None else (*kept, scaled))


def with_bonus(
    sheet: StatSheet, stat_id: str, amount: Fraction, source: str, label: Label, note: str = ""
) -> StatSheet:
    """``sheet`` with a temporary flat bonus to an additive amount (rotations)."""
    return _added(sheet, stat_id, Contribution(amount, "bonus", source, label, note))


def with_percent_bonus(
    sheet: StatSheet, stat_id: str, percent: Fraction, source: str, label: Label, note: str = ""
) -> StatSheet:
    """``sheet`` with a temporary additive percentage bonus (e.g. +20% move speed, fraction 0.2)."""
    definition = _receiver(stat_id)
    if definition.id != "move_speed":
        raise StatsError(
            f"{definition.id}: temporary additive percent bonuses are only for move_speed"
        )
    return _recompute_move_speed(
        sheet,
        extra_percent=Contribution(percent, "bonus", source, label, note),
    )


def with_amplifier(
    sheet: StatSheet, stat_id: str, percent: Fraction, source: str, label: Label
) -> StatSheet:
    """``sheet`` with a temporary ``percent`` % of a stat's total (rotations).

    The share is of the total without other amplifiers, as the sheet does for
    its own; with another amplifier on the stat that is not verified.
    """
    current = sheet[_receiver(stat_id).id].contributions
    contribution = _amplified(
        StatAmplifier(stat_id, percent, source, label),
        [item for item in current if not item.amplifier],
        compounded=any(item.amplifier for item in current),
    )
    return _added(sheet, stat_id, contribution)


def _receiver(stat_id: str) -> StatDef:
    """The statistic that receives item and extra contributions declared as ``stat_id``."""
    definition = stat(stat_id)
    return stat(definition.routes_to) if definition.routes_to else definition


def _parse_assumptions(
    assumptions: Mapping[str, object], issues: Sequence[DataIssue]
) -> dict[str, Fraction]:
    allowed = {issue.field for issue in issues}
    parsed: dict[str, Fraction] = {}
    for key, raw in assumptions.items():
        if key not in allowed:
            hint = ", ".join(sorted(allowed)) or "none"
            raise StatsError(
                f"cannot assume {key!r}: only fields with an open data issue can be assumed "
                f"(available: {hint})"
            )
        try:
            value = to_fraction(raw, f"assumption {key}")
        except DamageInputError as exc:
            raise StatsError(str(exc)) from exc
        if value < 0:
            raise StatsError(f"assumption {key}: {value} is negative")
        parsed[key] = value
    return parsed


def _source(champion: ChampionData, field_name: str) -> str:
    return f"data:champion:{champion.id} stats.{field_name} ({champion.patch})"


def _attack_speed_growth(champion: ChampionData, level: int, multiplier: Fraction) -> Contribution:
    if ATTACK_SPEED_GROWTH not in champion.stats:
        raise StatsError(f"{champion.id}: stats.{ATTACK_SPEED_GROWTH} is missing")
    growth = champion.stats[ATTACK_SPEED_GROWTH]
    return Contribution(
        growth / 100 * multiplier,
        "base",
        _source(champion, ATTACK_SPEED_GROWTH),
        Label.DERIVED if growth else Label.OFFICIAL,
        f"growth to level {level}",
    )


def _attack_speed_ratio(
    champion: ChampionData, derived: DerivedRecords | None
) -> AttackSpeedRatio | None:
    ratio = derived.value(champion.id, ATTACK_SPEED_RATIO) if derived else None
    if derived is None or ratio is None:
        return None
    label, note = Label.DERIVED, ""
    if not derived.matches_patch(champion.patch):
        label = Label.PENDING
        note = f"; client {derived.game_version} record used with snapshot {champion.patch}"
    source = f"{derived.path} {champion.id}.{ATTACK_SPEED_RATIO} ({derived.content_version})"
    return AttackSpeedRatio(ratio, label, source, note)


def _scaled_attack_speed(
    champion: ChampionData, bonus: Sequence[Contribution], ratio: AttackSpeedRatio | None
) -> Contribution | str | None:
    """Bonus attack speed times the champion's ratio, or why it cannot be computed.

    ``None`` means there is no bonus attack speed, so the total is the base.
    """
    if champion.id == "Jhin":
        return None
    total_bonus = sum((item.value for item in bonus), start=Fraction(0))
    if not total_bonus:
        return None
    if ratio is None:
        return (
            f"bonus attack speed {format_number(total_bonus)} needs the attack speed ratio, "
            f"which Data Dragon does not publish, and the derived records have no "
            f"{champion.id}.{ATTACK_SPEED_RATIO} (see {ATTACK_SPEED_RULES})"
        )
    if ratio.value == 0:
        return None
    return Contribution(
        ratio.value * total_bonus,
        "bonus",
        f"{ratio.source} x attack_speed_bonus",
        weakest([ratio.label, *(item.label for item in bonus)]),
        f"ratio {format_number(ratio.value)} x bonus {format_percent(total_bonus)}{ratio.note}",
        scaled=True,
    )


def _crit_chance_base(champion: ChampionData) -> Contribution | str:
    """The champion's own crit chance, or why it cannot be used.

    Data Dragon publishes ``crit`` and ``critperlevel`` as 0 for every champion,
    so their unit is unknown: a non-zero value blocks the statistic instead of
    being guessed as a fraction or a percentage.
    """
    for field_name in CRIT_FIELDS:
        if field_name not in champion.stats:
            raise StatsError(f"{champion.id}: stats.{field_name} is missing")
    nonzero = [name for name in CRIT_FIELDS if champion.stats[name]]
    if nonzero:
        return (
            f"{champion.id} has non-zero stats.{nonzero[0]} in Data Dragon; its unit is not "
            f"documented (see {CRIT_RULES})"
        )
    return Contribution(Fraction(0), "base", _source(champion, "crit"), Label.OFFICIAL)


def _crit_chance_passive(
    champion: ChampionData, contributions: dict[str, list[Contribution]]
) -> None:
    """Yasuo and Yone: double their crit chance and turn the excess into attack damage."""
    sources = contributions["crit_chance"]
    total = sum((item.value for item in sources), start=Fraction(0))
    labels = [Label.DERIVED, *(item.label for item in sources)]
    passive = f"{CRIT_RULES} ({champion.id} passive)"
    doubled = total * CRIT_CHANCE_KIT_MULTIPLIER
    contributions["crit_chance"].append(
        Contribution(
            doubled - total,
            "bonus",
            passive,
            weakest(labels),
            f"passive doubles critical strike chance ({format_percent(total)} x "
            f"{CRIT_CHANCE_KIT_MULTIPLIER})",
        )
    )
    excess = doubled - STATS["crit_chance"].cap
    if excess > 0:
        contributions["attack_damage"].append(
            Contribution(
                excess * EXCESS_CRIT_AD,
                "bonus",
                passive,
                weakest(labels),
                f"excess critical strike chance {format_percent(excess)} x 0.5 per 1%",
            )
        )


def _apply_cassiopeia_move_speed_passive(
    level: int,
    flats: list[Contribution],
    percents: list[Contribution],
) -> None:
    """Cassiopeia: increase effectiveness of all flat and % move speed bonuses by 5%..35.6%."""
    amp = CASSIOPEIA_MS_AMP_BASE + CASSIOPEIA_MS_AMP_PER_LEVEL * (min(level, 18) - 1)
    source = f"{MOVE_SPEED_RULES} (Cassiopeia passive)"
    bonus_flat = [item for item in flats if item.scope == "bonus"]
    flat_total = sum((item.value for item in bonus_flat), start=Fraction(0))
    if flat_total > 0:
        flats.append(
            Contribution(
                flat_total * amp,
                "bonus",
                source,
                weakest([Label.DERIVED, *(item.label for item in bonus_flat)]),
                f"passive increases bonus flat move speed {format_number(flat_total)} by "
                f"{format_percent(amp)}",
                ms_derived=True,
            )
        )
    pct_total = sum((item.value for item in percents), start=Fraction(0))
    if pct_total > 0:
        percents.append(
            Contribution(
                pct_total * amp,
                "bonus",
                source,
                weakest([Label.DERIVED, *(item.label for item in percents)]),
                f"passive increases % move speed bonuses {format_percent(pct_total)} by "
                f"{format_percent(amp)}",
                ms_derived=True,
            )
        )


def _apply_move_speed_bonus_amp(
    amp: Contribution,
    flats: list[Contribution],
    percents: list[Contribution],
) -> None:
    """Increase effectiveness of other bonus flat and percent movement speed (e.g. Celerity)."""
    bonus_flat = [item for item in flats if item.scope == "bonus"]
    other_pct = [item for item in percents if item.source != amp.source]
    flat_total = sum((item.value for item in bonus_flat), start=Fraction(0))
    if flat_total > 0:
        flats.append(
            Contribution(
                flat_total * amp.value,
                "bonus",
                amp.source,
                Label.PENDING,
                f"{format_percent(amp.value)} of bonus flat move speed "
                f"{format_number(flat_total)}; {amp.note}",
                ms_derived=True,
            )
        )
    pct_total = sum((item.value for item in other_pct), start=Fraction(0))
    if pct_total > 0:
        percents.append(
            Contribution(
                pct_total * amp.value,
                "bonus",
                amp.source,
                Label.PENDING,
                f"{format_percent(amp.value)} of other % move speed bonuses "
                f"{format_percent(pct_total)}; {amp.note}",
                ms_derived=True,
            )
        )


def _resolve_move_speed(
    champion_id: str,
    level: int,
    raw_flats: Sequence[Contribution],
    raw_percents: Sequence[Contribution],
    move_speed_bonus_amp: Contribution | None = None,
) -> list[Contribution]:
    """Resolve move_speed flats + Cassiopeia/Celerity amps + additive percentages."""
    flats = list(raw_flats)
    percents = list(raw_percents)
    if champion_id == "Cassiopeia":
        _apply_cassiopeia_move_speed_passive(level, flats, percents)
    if move_speed_bonus_amp is not None:
        _apply_move_speed_bonus_amp(move_speed_bonus_amp, flats, percents)
    reference = list(flats)
    ms_def = STATS["move_speed"]
    for percent in percents:
        flats.append(replace(_percent_amount(ms_def, percent, reference), ms_derived=True))
    return flats


def _effective_bonus_move_speed(ms_value: StatValue) -> Fraction:
    """Effective bonus move speed after percentages and soft caps (total - base, >= 0)."""
    return max(Fraction(0), ms_value.total() - ms_value.scoped("base"))


def _apply_ms_conversions(
    champion_id: str,
    level: int,
    ms_value: StatValue,
    post_ms_effects: Sequence[PostMsEffect],
    contributions: Mapping[str, list[Contribution]],
    *,
    ap_weight: Fraction | None,
    holder_range: str | None,
) -> None:
    """Apply champion/item conversions that read resolved post-soft-cap move_speed."""
    if ms_value.status != "resolved":
        return
    total_ms = ms_value.total()
    base_ms = ms_value.scoped("base")
    bonus_ms = _effective_bonus_move_speed(ms_value)
    ms_label = ms_value.label

    if champion_id == "Hecarim" and bonus_ms > 0:
        ratio = HECARIM_WARPATH_BY_LEVEL[min(level, 18) - 1]
        contributions["attack_damage"].append(
            Contribution(
                bonus_ms * ratio,
                "bonus",
                f"{MOVE_SPEED_RULES} (Hecarim passive)",
                weakest([Label.DERIVED, ms_label]),
                f"Warpath: {format_percent(ratio)} of effective bonus move speed "
                f"{format_number(bonus_ms)}",
                derived_from_ms=True,
            )
        )

    if not post_ms_effects:
        return
    ms_env: dict[str, Fraction] = {
        "move_speed": total_ms,
        "base_move_speed": base_ms,
        "bonus_move_speed": bonus_ms,
    }
    for eff in post_ms_effects:
        try:
            evaluated = evaluate_formula(
                eff.formula, ms_env, holder_range=holder_range, level=level
            )
        except FormulaError as exc:
            raise StatsError(f"{eff.source}: {exc}") from exc
        if eff.stat == "adaptive_force":
            bonus_ad = sum(
                (
                    c.value
                    for c in contributions["attack_damage"]
                    if c.scope == "bonus" and not c.adaptive
                ),
                start=Fraction(0),
            )
            ap = sum(
                (c.value for c in contributions["ability_power"] if not c.adaptive),
                start=Fraction(0),
            )
            target_stat, ad_label, ad_note = adaptive_stat(bonus_ad, ap, ap_weight)
            if target_stat == "attack_damage":
                amount = evaluated.exact * ADAPTIVE_AD_PER_AP
                kind_label = "bonus AD"
            else:
                amount = evaluated.exact
                kind_label = "AP"
            note = (
                f"{format_number(evaluated.exact)} adaptive force -> "
                f"{format_number(amount)} {kind_label}; {ad_note}"
            )
            if eff.note:
                note = f"{eff.note}; {note}"
            contributions[target_stat].append(
                Contribution(
                    amount,
                    "bonus",
                    eff.source,
                    weakest([eff.label, ms_label, ad_label]),
                    note,
                    adaptive=True,
                    derived_from_ms=True,
                )
            )
        else:
            definition = _receiver(eff.stat)
            val = effect_amount(definition.id, evaluated.exact)
            if definition.unit is Unit.FRACTION and not 0 <= val <= 1:
                raise StatsError(f"{eff.source}: {val} is not a fraction 0..1")
            contributions[definition.id].append(
                Contribution(
                    val,
                    "bonus",
                    eff.source,
                    weakest([eff.label, ms_label]),
                    eff.note,
                    derived_from_ms=True,
                )
            )


def _parse_stack_input(
    inputs: Mapping[str, Fraction] | None,
    key: str,
    *,
    minimum: int = 0,
    maximum: int | None = None,
    integer: bool = True,
) -> Fraction | None:
    """Validate an optional numeric scenario input for an item passive."""
    if not inputs or key not in inputs:
        return None
    val = inputs[key]
    if val < minimum or (maximum is not None and val > maximum):
        bound = f"{minimum}..{maximum}" if maximum is not None else f">= {minimum}"
        raise StatsError(f"input {key} must be {bound}, got {format_number(val)}")
    if integer and val.denominator != 1:
        raise StatsError(f"input {key} must be an integer, got {format_number(val)}")
    return val


def _resolve_tear_transforms(
    items: Sequence[ItemData],
    inputs: Mapping[str, Fraction],
    notes: list[str],
) -> tuple[ItemData, ...]:
    """Upgrade Tear items (3003/3004/3119/2526) into their 360-stack forms when requested."""
    stacks = _parse_stack_input(inputs, "manaflow_stacks", minimum=0, maximum=TEAR_STACK_MAX)
    if stacks is None or stacks < TEAR_STACK_MAX:
        return tuple(items)
    resolved: list[ItemData] = []
    for item in items:
        target_id = TEAR_BASE_TO_TRANSFORM.get(item.id)
        if target_id is None:
            resolved.append(item)
            continue
        upgraded = transformed_tear_item(target_id, item.game_version)
        if upgraded is not None:
            resolved.append(upgraded)
            notes.append(
                f"item {item.id} transformed into data:item:{upgraded.id} ({upgraded.name}) "
                f"at {TEAR_STACK_MAX} Manaflow stacks"
            )
        else:
            resolved.append(item)
    return tuple(resolved)


def _apply_item_input_and_consumable_stats(
    items: Sequence[ItemData],
    level: int,
    inputs: Mapping[str, Fraction],
    uses_mana: bool,
    champ_range: str | None,
    contributions: dict[str, list[Contribution]],
    percents: dict[str, list[Contribution]],
    amplifiers: list[StatAmplifier],
    notes: list[str],
    pending: list[str],
) -> None:
    """Apply stackable/conditional item passives and active elixirs (client 16.23)."""
    manaflow = _parse_stack_input(inputs, "manaflow_stacks", minimum=0, maximum=TEAR_STACK_MAX)
    for item in items:
        iid = item.id
        src_base = f"data:item:{iid} ({item.game_version})"
        if iid in {"3070", "3003", "3004", "3119", "2526"}:
            if manaflow is not None and manaflow > 0 and uses_mana:
                contributions["mana"].append(
                    Contribution(
                        manaflow,
                        "bonus",
                        f"{src_base} effect manaflow",
                        Label.OFFICIAL,
                        f"manaflow_stacks={int(manaflow)}",
                    )
                )
        elif iid == "1082":
            glory = _parse_stack_input(inputs, "glory_stacks", minimum=0, maximum=10)
            if glory is None:
                notes.append("1082 Glory: 0 stacks (pass --input glory_stacks=0..10)")
            elif glory > 0:
                contributions["ability_power"].append(
                    Contribution(
                        glory * 4,
                        "bonus",
                        f"{src_base} effect glory",
                        Label.OFFICIAL,
                        f"glory_stacks={int(glory)} x 4 AP",
                    )
                )
        elif iid == "3041":
            glory = _parse_stack_input(inputs, "glory_stacks", minimum=0, maximum=25)
            if glory is None:
                notes.append("3041 Glory: 0 stacks (pass --input glory_stacks=0..25)")
            else:
                if glory > 0:
                    contributions["ability_power"].append(
                        Contribution(
                            glory * 5,
                            "bonus",
                            f"{src_base} effect glory",
                            Label.OFFICIAL,
                            f"glory_stacks={int(glory)} x 5 AP",
                        )
                    )
                if glory >= 10:
                    percents.setdefault("move_speed", []).append(
                        Contribution(
                            Fraction(10, 100),
                            "bonus",
                            f"{src_base} effect glory",
                            Label.OFFICIAL,
                            f"glory_stacks={int(glory)} >= 10 (+10% MS)",
                        )
                    )
        elif iid == "6697":
            statues = _parse_stack_input(inputs, "hubris_stacks", minimum=0)
            if statues is None:
                notes.append("6697 Eminence: inactive (pass --input hubris_stacks=<n>)")
            else:
                ranged_mult = Fraction(667, 1000) if champ_range == "ranged" else Fraction(1)
                ad_gain = (Fraction(15) + Fraction(3) * statues) * ranged_mult
                contributions["attack_damage"].append(
                    Contribution(
                        ad_gain,
                        "bonus",
                        f"{src_base} effect eminence",
                        Label.DERIVED,
                        f"hubris_stacks={int(statues)} (15 + 3x{int(statues)})"
                        + (" x 0.667 ranged" if champ_range == "ranged" else ""),
                    )
                )
        elif iid == "6657":
            roa = _parse_stack_input(inputs, "roa_stacks", minimum=0, maximum=10)
            if roa is None:
                notes.append("6657 Timeless: 0 stacks (pass --input roa_stacks=0..10)")
            elif roa > 0:
                contributions["health"].append(
                    Contribution(
                        roa * 10,
                        "bonus",
                        f"{src_base} effect timeless",
                        Label.OFFICIAL,
                        f"roa_stacks={int(roa)} x 10 HP",
                    )
                )
                if uses_mana:
                    contributions["mana"].append(
                        Contribution(
                            roa * 30,
                            "bonus",
                            f"{src_base} effect timeless",
                            Label.OFFICIAL,
                            f"roa_stacks={int(roa)} x 30 mana",
                        )
                    )
                contributions["ability_power"].append(
                    Contribution(
                        roa * 3,
                        "bonus",
                        f"{src_base} effect timeless",
                        Label.OFFICIAL,
                        f"roa_stacks={int(roa)} x 3 AP",
                    )
                )
        elif iid in {"3008", "3168"}:
            murder = _parse_stack_input(inputs, "murder_stacks", minimum=0, maximum=10)
            stacks = Fraction(10) if murder is None else murder
            if stacks > 0:
                contributions["omnivamp"].append(
                    Contribution(
                        stacks * Fraction(6, 1000),
                        "bonus",
                        f"{src_base} effect murder",
                        Label.OFFICIAL,
                        (
                            f"murder_stacks={int(stacks)}"
                            if murder is not None
                            else "scenario: maximum stacks (10)"
                        ),
                    )
                )
            if iid == "3168":
                hp_pct = _parse_stack_input(
                    inputs, "attacker_health_percent", minimum=0, maximum=1, integer=False
                )
                if hp_pct is not None and hp_pct < Fraction(1, 2):
                    contributions["heal_and_shield_power"].append(
                        Contribution(
                            Fraction(12, 100),
                            "bonus",
                            f"{src_base} effect now-and-forever",
                            Label.OFFICIAL,
                            f"attacker_health_percent={format_number(hp_pct)} < 0.5 (+12% HSP)",
                        )
                    )
                    percents.setdefault("health_regen", []).append(
                        Contribution(
                            Fraction(12, 100),
                            "bonus",
                            f"{src_base} effect now-and-forever",
                            Label.OFFICIAL,
                            "<50% HP (+12% health regen)",
                        )
                    )
        elif iid == "2501":
            hp_pct = _parse_stack_input(
                inputs, "attacker_health_percent", minimum=0, maximum=1, integer=False
            )
            if hp_pct is not None and hp_pct < 1:
                missing_frac = min(Fraction(1) - hp_pct, Fraction(7, 10)) / Fraction(7, 10)
                amp_pct = missing_frac * Fraction(10)
                if amp_pct > 0:
                    amplifiers.append(
                        StatAmplifier(
                            "attack_damage",
                            amp_pct,
                            f"{src_base} effect retribution",
                            Label.DERIVED,
                            f"Retribution: +{format_number(amp_pct)}% AD at "
                            f"{format_percent(hp_pct)} HP",
                        )
                    )
        elif iid == "3742":
            mom = _parse_stack_input(inputs, "momentum_stacks", minimum=0, maximum=100)
            if mom is not None and mom > 0:
                contributions["move_speed"].append(
                    Contribution(
                        mom * Fraction(1, 5),
                        "bonus",
                        f"{src_base} effect shipwrecker",
                        Label.DERIVED,
                        f"momentum_stacks={int(mom)} (+{format_number(mom * Fraction(1, 5))} MS)",
                    )
                )
        elif iid == "2138":
            if level < 9:
                notes.append(f"2138 Elixir of Iron requires level 9 (champion is level {level})")
            else:
                contributions["health"].append(
                    Contribution(
                        Fraction(300), "bonus", f"{src_base} effect elixir-of-iron", Label.OFFICIAL
                    )
                )
                contributions["tenacity"].append(
                    Contribution(
                        Fraction(25, 100),
                        "bonus",
                        f"{src_base} effect elixir-of-iron",
                        Label.OFFICIAL,
                        tenacity_group="A",
                    )
                )
        elif iid == "2139":
            if level < 9:
                notes.append(f"2139 Elixir of Sorcery requires level 9 (champion is level {level})")
            else:
                contributions["ability_power"].append(
                    Contribution(
                        Fraction(50),
                        "bonus",
                        f"{src_base} effect elixir-of-sorcery",
                        Label.OFFICIAL,
                    )
                )
                if uses_mana:
                    contributions["mana_regen"].append(
                        Contribution(
                            Fraction(15),
                            "bonus",
                            f"{src_base} effect elixir-of-sorcery",
                            Label.DERIVED,
                            "flat +15 mana regen per 5 s",
                        )
                    )
        elif iid == "2140":
            if level < 9:
                notes.append(f"2140 Elixir of Wrath requires level 9 (champion is level {level})")
            else:
                contributions["attack_damage"].append(
                    Contribution(
                        Fraction(30), "bonus", f"{src_base} effect elixir-of-wrath", Label.OFFICIAL
                    )
                )


def build_stat_sheet(
    champion: ChampionData,
    level: int,
    items: Sequence[ItemData] = (),
    issues: Sequence[DataIssue] = (),
    assumptions: Mapping[str, object] | None = None,
    derived: DerivedRecords | None = None,
    extras: Sequence[tuple[str, Contribution]] = (),
    percent_extras: Sequence[tuple[str, Contribution]] = (),
    pending_effects: Sequence[str] = (),
    *,
    extra_amplifiers: Sequence[StatAmplifier] = (),
    extra_notes: Sequence[str] = (),
    move_speed_bonus_amp: Contribution | None = None,
    inputs: Mapping[str, Fraction] = (),
) -> StatSheet:
    """Resolve the champion's statistics at ``level`` with ``items``.

    A field with an open data issue is replaced, in this order, by an explicit
    assumption (``Pendiente de verificación``) or by a derived client record
    (``Derivado`` when the client patch matches the snapshot, otherwise
    ``Pendiente de verificación``). With neither, the statistic is blocked.

    ``extras`` adds further contributions, such as stats an ability grants
    passively (see ``lol_knowledge.kit.passive_contributions``) or stat shards;
    ``percent_extras`` adds percentages (a fraction, like an item's ``percent``)
    of a stat that accepts them. ``pending_effects`` lists given sources whose
    effects are not modelled; they become notes and weaken damage built on the sheet.

    Attack speed is ``base + ratio x attack_speed_bonus``, capped. The bonus
    holds the level growth and every item or extra declared as attack speed;
    the ratio comes from the derived records (see attack-speed.md).
    """
    check_level(level)
    applicable = [issue for issue in issues if issue.applies_to(champion.id, champion.patch)]
    assumed = _parse_assumptions(assumptions or {}, applicable)
    issue_by_field = {issue.field: issue for issue in applicable}
    for item in items:
        if item.game_version != champion.patch:
            raise StatsError(
                f"item {item.id} is from {item.game_version}, the champion from {champion.patch}"
            )

    contributions: dict[str, list[Contribution]] = {stat_id: [] for stat_id in STATS}
    percents: dict[str, list[Contribution]] = {}
    amplifiers: list[StatAmplifier] = []
    blocked: dict[str, str] = {}
    notes: list[str] = []
    extra_pending: list[str] = list(pending_effects)
    items = _resolve_tear_transforms(items, inputs, notes)
    mana_resource = MANA_RESOURCE.get(champion.locale)
    if mana_resource is None:
        raise StatsError(f"snapshot locale {champion.locale!r} has no known name for mana")
    uses_mana = champion.resource == mana_resource

    multiplier = growth_multiplier(level)
    for stat_id, base_field, growth_field in CHAMPION_FIELDS:
        if stat_id in MANA_STATS and not uses_mana:
            blocked[stat_id] = (
                f"the champion's resource is {champion.resource!r}; only mana is modelled"
            )
            continue
        if base_field not in champion.stats:
            raise StatsError(f"{champion.id}: stats.{base_field} is missing")
        contributions[stat_id].append(
            Contribution(
                champion.stats[base_field], "base", _source(champion, base_field), Label.OFFICIAL
            )
        )
        if growth_field is None or level == 1:
            continue
        if growth_field not in champion.stats:
            raise StatsError(f"{champion.id}: stats.{growth_field} is missing")
        issue = issue_by_field.get(growth_field)
        derived_value = derived.value(champion.id, growth_field) if derived else None
        note = f"growth to level {level}"
        if issue is not None and growth_field in assumed:
            growth = assumed[growth_field]
            source = f"assumption {growth_field}={growth} ({issue.id})"
            label = Label.PENDING
        elif issue is not None and derived is not None and derived_value is not None:
            growth = derived_value
            source = f"{derived.path} {champion.id}.{growth_field} ({derived.content_version})"
            if derived.matches_patch(champion.patch):
                label = Label.DERIVED
            else:
                label = Label.PENDING
                note += (
                    f"; client {derived.game_version} record used with snapshot {champion.patch}"
                )
        elif issue is not None:
            blocked[stat_id] = (
                f"{issue.id}: {issue.summary} No derived record for {champion.id}; "
                f"use --assume {growth_field}=<value> (see {issue.documentation})"
            )
            continue
        else:
            growth = champion.stats[growth_field]
            source = _source(champion, growth_field)
            label = Label.DERIVED if growth else Label.OFFICIAL
        contributions[stat_id].append(
            Contribution(growth * multiplier, "base", source, label, note)
        )
    if level > 1:
        if champion.id == "Jhin":
            if ATTACK_SPEED_GROWTH not in champion.stats:
                raise StatsError(f"{champion.id}: stats.{ATTACK_SPEED_GROWTH} is missing")
            contributions["attack_speed"].append(
                Contribution(
                    champion.stats["attackspeed"] * JHIN_FIXED_AS_GROWTH * multiplier,
                    "base",
                    f"{ATTACK_SPEED_RULES} (Jhin passive)",
                    Label.DERIVED,
                    f"Whisper fixed attack speed growth to level {level}",
                )
            )
        else:
            contributions["attack_speed_bonus"].append(
                _attack_speed_growth(champion, level, multiplier)
            )
    crit_base = _crit_chance_base(champion)
    if isinstance(crit_base, str):
        blocked["crit_chance"] = crit_base
    else:
        contributions["crit_chance"].append(crit_base)

    for item in items:
        for entry in item.stats:
            definition = _receiver(entry.stat)
            if entry.kind not in {"flat", "percent"}:
                raise StatsError(f"item {item.id}.{entry.stat}: unknown kind {entry.kind!r}")
            deferred = definition.percent_of is not None and entry.kind == "percent"
            if definition.resolvable and entry.kind != definition.item_kind and not deferred:
                raise StatsError(
                    f"item {item.id}.{entry.stat}: kind {entry.kind!r} is not supported "
                    f"for {definition.id}"
                )
            value = entry.value / 100 if entry.kind == "percent" else entry.value
            if definition.unit is Unit.FRACTION and not 0 <= value <= 1:
                raise StatsError(f"item {item.id}.{entry.stat}: {value} is not a fraction 0..1")
            note = "percent" if entry.kind == "percent" and definition.unit is Unit.AMOUNT else ""
            if definition.id != entry.stat:
                note = f"declared as {entry.stat}"
            if deferred:
                note = ""
            if entry.note:
                note = f"{note}; {entry.note}" if note else entry.note
            contribution = Contribution(
                value,
                "bonus",
                f"data:item:{item.id} {entry.source} ({item.game_version})",
                entry.label,
                note,
            )
            target = percents if deferred else contributions
            target.setdefault(definition.id, []).append(contribution)

    for stat_id, extra in extras:
        definition = _receiver(stat_id)
        if definition.unit is Unit.FRACTION and not 0 <= extra.value <= 1:
            raise StatsError(f"extra {stat_id}: {extra.value} is not a fraction 0..1")
        if definition.id == "tenacity" and extra.tenacity_group is None:
            extra = _ungrouped_tenacity(extra)
        contributions[definition.id].append(extra)
    for stat_id, extra in percent_extras:
        definition = _receiver(stat_id)
        if definition.percent_of is None:
            raise StatsError(f"extra {stat_id}: the stat takes no percentage")
        percents.setdefault(definition.id, []).append(extra)
    for extra_amp in extra_amplifiers:
        definition = _receiver(extra_amp.stat)
        if definition.unit is not Unit.AMOUNT:
            raise StatsError(
                f"extra amplifier {extra_amp.stat}: only amount stats can be amplified"
            )
        amplifiers.append(replace(extra_amp, stat=definition.id))

    atk_range = champion.stats.get("attackrange")
    champ_range = None if atk_range is None else ("melee" if atk_range < 300 else "ranged")

    _apply_item_input_and_consumable_stats(
        items,
        level,
        inputs,
        uses_mana,
        champ_range,
        contributions,
        percents,
        amplifiers,
        notes,
        extra_pending,
    )

    # Build the resolved stat environment after flat item stats and extras so
    # stat-from-stat conversion passives (Sterak, Overlord's, Riftmaker, Tear items, Dawncore)
    # can read base_*, bonus_* and total stats before amplifiers (Rabadon) run.
    stat_env: dict[str, Fraction] = {}
    label_env: dict[str, Label] = {}
    for stat_id, items_list in contributions.items():
        if stat_id in blocked:
            if stat_id == "mana" and champion.resource != MANA_RESOURCE.get(champion.locale):
                stat_env["mana"] = Fraction(0)
                stat_env["base_mana"] = Fraction(0)
                stat_env["bonus_mana"] = Fraction(0)
                label_env["mana"] = Label.OFFICIAL
                label_env["base_mana"] = Label.OFFICIAL
                label_env["bonus_mana"] = Label.OFFICIAL
            continue
        base_items = [c for c in items_list if c.scope == "base"]
        bonus_items = [c for c in items_list if c.scope == "bonus"]
        stat_env[stat_id] = sum((c.value for c in items_list), start=Fraction(0))
        label_env[stat_id] = weakest(c.label for c in items_list)
        if base_items:
            stat_env[f"base_{stat_id}"] = sum((c.value for c in base_items), start=Fraction(0))
            label_env[f"base_{stat_id}"] = weakest(c.label for c in base_items)
        else:
            stat_env[f"base_{stat_id}"] = Fraction(0)
            label_env[f"base_{stat_id}"] = Label.OFFICIAL
        stat_env[f"bonus_{stat_id}"] = sum((c.value for c in bonus_items), start=Fraction(0))
        label_env[f"bonus_{stat_id}"] = weakest(c.label for c in bonus_items)

    mr_percents = percents.get("mana_regen", ())
    stat_env["bonus_mana_regen_percent"] = (
        sum((c.value for c in mr_percents), start=Fraction(0)) * 100
    )
    label_env["bonus_mana_regen_percent"] = (
        weakest(c.label for c in mr_percents) if mr_percents else Label.OFFICIAL
    )

    post_ms_effects: list[PostMsEffect] = []
    for item in items:
        effect_stats, item_amplifiers, item_post_ms = _sheet_effects(
            item, level, stat_env, label_env, blocked, holder_range=champ_range
        )
        for stat_id, contribution in effect_stats:
            contributions[stat_id].append(contribution)
        amplifiers += item_amplifiers
        post_ms_effects += item_post_ms

    # Move speed: apply Cassiopeia/Celerity amps and additive % before soft-cap conversions.
    raw_ms_percents = tuple(percents.pop("move_speed", ()))
    contributions["move_speed"] = _resolve_move_speed(
        champion.id,
        level,
        contributions["move_speed"],
        raw_ms_percents,
        move_speed_bonus_amp,
    )

    # Remaining percentages (regeneration.md) once every flat amount is known.
    for stat_id, pending in percents.items():
        reference = list(contributions[stat_id])
        contributions[stat_id] += [
            _percent_amount(STATS[stat_id], percent, reference) for percent in pending
        ]

    ratio = _attack_speed_ratio(champion, derived)
    scaled = _scaled_attack_speed(champion, contributions["attack_speed_bonus"], ratio)
    if isinstance(scaled, str):
        blocked["attack_speed"] = scaled
    elif scaled is not None:
        contributions["attack_speed"].append(scaled)

    if champion.id == "Zeri" and ratio is not None and ratio.value > 0:
        base_as = sum(
            (c.value for c in contributions["attack_speed"] if c.scope == "base"),
            start=Fraction(0),
        )
        bonus_as_list = contributions["attack_speed_bonus"]
        total_bonus_as = sum((c.value for c in bonus_as_list), start=Fraction(0))
        max_bonus_as = (ZERI_ATTACK_SPEED_CAP - base_as) / ratio.value
        if total_bonus_as > max_bonus_as:
            excess_as = total_bonus_as - max_bonus_as
            contributions["attack_damage"].append(
                Contribution(
                    excess_as * ZERI_EXCESS_AS_AD,
                    "bonus",
                    f"{ATTACK_SPEED_RULES} (Zeri Q passive)",
                    weakest([Label.DERIVED, ratio.label, *(c.label for c in bonus_as_list)]),
                    f"excess bonus attack speed {format_percent(excess_as)} x 0.6 per 1%",
                )
            )

    if champion.id in CRIT_CHANCE_KITS:
        if "crit_chance" in blocked:
            blocked["attack_damage"] = (
                f"{champion.id}'s passive converts excess crit chance into attack damage, "
                "and crit chance is blocked"
            )
        else:
            _crit_chance_passive(champion, contributions)

    ap_weight = derived.value(champion.id, "adaptiveforceapweight") if derived else None
    ms_value = StatValue(
        STATS["move_speed"], tuple(contributions["move_speed"]), blocked.get("move_speed")
    )
    _apply_ms_conversions(
        champion.id,
        level,
        ms_value,
        post_ms_effects,
        contributions,
        ap_weight=ap_weight,
        holder_range=champ_range,
    )

    if champion.id == "Jhin":
        if "crit_chance" in blocked:
            blocked["attack_damage"] = (
                "Jhin's passive scales attack damage with crit chance, and crit chance is blocked"
            )
        else:
            crit_sources = contributions["crit_chance"]
            crit_total = min(
                sum((c.value for c in crit_sources), start=Fraction(0)),
                STATS["crit_chance"].cap,
            )
            as_sources = contributions["attack_speed_bonus"]
            bonus_as_total = sum((c.value for c in as_sources), start=Fraction(0))
            level_pct = Fraction(JHIN_AD_PERCENT_BY_LEVEL[min(level, 18) - 1])
            whisper_pct = (
                level_pct
                + crit_total * JHIN_CRIT_TO_AD_PERCENT
                + bonus_as_total * JHIN_AS_TO_AD_PERCENT
            )
            whisper_labels = [
                Label.DERIVED,
                *(c.label for c in crit_sources if c.value),
                *(c.label for c in as_sources if c.value),
            ]
            whisper_note = (
                f"Whisper: {format_number(level_pct)}% level + "
                f"{format_number(crit_total * JHIN_CRIT_TO_AD_PERCENT)}% from crit + "
                f"{format_number(bonus_as_total * JHIN_AS_TO_AD_PERCENT)}% from bonus AS"
            )
            amplifiers.append(
                StatAmplifier(
                    "attack_damage",
                    whisper_pct,
                    f"{ATTACK_SPEED_RULES} (Jhin passive)",
                    weakest(whisper_labels),
                    whisper_note,
                )
            )

    if champion.id == "Graves":
        notes.append("Graves fires 2 shells before reloading; attack_speed is his inter-shot rate")

    # Pre-amplifier passive conversions (Vladimir HP->AP, Pyke bonus HP->AD, Ornn bonus amp)
    vladimir_ap_from_hp = Fraction(0)
    if champion.id == "Vladimir" and "health" not in blocked:
        non_passive_bonus_hp = sum(
            (c.value for c in contributions["health"] if c.scope == "bonus"),
            start=Fraction(0),
        )
        if non_passive_bonus_hp > 0:
            vladimir_ap_from_hp = non_passive_bonus_hp / VLADIMIR_HP_PER_AP
            hp_labels = [c.label for c in contributions["health"] if c.scope == "bonus" and c.value]
            contributions["ability_power"].append(
                Contribution(
                    vladimir_ap_from_hp,
                    "bonus",
                    f"{PASSIVES_RULES} (Vladimir Crimson Pact)",
                    weakest([Label.DERIVED, *hp_labels]),
                    f"1 AP per 30 bonus HP ({format_number(non_passive_bonus_hp)} bonus HP)",
                )
            )

    if champion.id == "Pyke" and "health" not in blocked:
        pyke_bonus_hp = sum(
            (c.value for c in contributions["health"] if c.scope == "bonus"),
            start=Fraction(0),
        )
        if pyke_bonus_hp > 0:
            hp_labels = [c.label for c in contributions["health"] if c.scope == "bonus" and c.value]
            p_label = weakest([Label.DERIVED, *hp_labels])
            contributions["health"].append(
                Contribution(
                    -pyke_bonus_hp,
                    "bonus",
                    f"{PASSIVES_RULES} (Pyke Gift of the Drowned Ones)",
                    p_label,
                    "cannot gain bonus HP; converted to bonus AD",
                )
            )
            contributions["attack_damage"].append(
                Contribution(
                    pyke_bonus_hp / PYKE_HP_PER_AD,
                    "bonus",
                    f"{PASSIVES_RULES} (Pyke Gift of the Drowned Ones)",
                    p_label,
                    f"1 bonus AD per 14 bonus HP ({format_number(pyke_bonus_hp)} bonus HP)",
                )
            )

    if champion.id == "Ornn":
        mw_raw = _parse_stack_input(
            inputs, "ornn_masterworks", minimum=0, maximum=ORNN_MAX_MASTERWORKS
        )
        mw_count = int(mw_raw) if mw_raw is not None else 0
        ornn_amp = ORNN_BASE_STAT_AMP + ORNN_MASTERWORK_STAT_AMP * mw_count
        ornn_note = (
            f"Living Forge: +{format_number(ornn_amp * 100)}% bonus HP/Armor/MR "
            f"(ornn_masterworks={mw_count})"
        )
        for stat_id in ("health", "armor", "magic_resist"):
            if stat_id in blocked:
                continue
            bonus_parts = [c for c in contributions[stat_id] if c.scope == "bonus"]
            bonus_val = sum((c.value for c in bonus_parts), start=Fraction(0))
            if bonus_val > 0:
                contributions[stat_id].append(
                    Contribution(
                        bonus_val * ornn_amp,
                        "bonus",
                        f"{PASSIVES_RULES} (Ornn Living Forge)",
                        weakest([Label.DERIVED, *(c.label for c in bonus_parts if c.value)]),
                        ornn_note,
                    )
                )

    # Amplifiers of a total last, all on the same total (Rabadon, Conditioning, Overgrowth, Jhin).
    reference = {amplifier.stat: list(contributions[amplifier.stat]) for amplifier in amplifiers}
    for amplifier in amplifiers:
        contributions[amplifier.stat].append(_amplified(amplifier, reference[amplifier.stat]))

    # Post-amplifier champion passive conversions (Vladimir AP->HP, Pyke overflow, Ryze AP->Mana,
    # Rammus Armor+MR->AD) so Rabadon/Conditioning feed into them without recursion.
    if champion.id == "Vladimir" and "health" not in blocked:
        non_self_ap = (
            sum((c.value for c in contributions["ability_power"]), start=Fraction(0))
            - vladimir_ap_from_hp
        )
        if non_self_ap > 0:
            ap_labels = [c.label for c in contributions["ability_power"] if c.value]
            contributions["health"].append(
                Contribution(
                    non_self_ap * VLADIMIR_HP_PER_AP_GAIN,
                    "bonus",
                    f"{PASSIVES_RULES} (Vladimir Crimson Pact)",
                    weakest([Label.DERIVED, *ap_labels]),
                    f"1.6 bonus HP per 1 AP ({format_number(non_self_ap)} AP, no recursion)",
                )
            )

    if champion.id == "Pyke" and "health" not in blocked:
        extra_bonus_hp = sum(
            (c.value for c in contributions["health"] if c.scope == "bonus"),
            start=Fraction(0),
        )
        if extra_bonus_hp > 0:
            hp_labels = [c.label for c in contributions["health"] if c.scope == "bonus" and c.value]
            p_label = weakest([Label.DERIVED, *hp_labels])
            contributions["health"].append(
                Contribution(
                    -extra_bonus_hp,
                    "bonus",
                    f"{PASSIVES_RULES} (Pyke Gift of the Drowned Ones)",
                    p_label,
                    "post-amplifier bonus HP converted to bonus AD",
                )
            )
            contributions["attack_damage"].append(
                Contribution(
                    extra_bonus_hp / PYKE_HP_PER_AD,
                    "bonus",
                    f"{PASSIVES_RULES} (Pyke Gift of the Drowned Ones)",
                    p_label,
                    f"1 bonus AD per 14 bonus HP ({format_number(extra_bonus_hp)} bonus HP)",
                )
            )

    if champion.id == "Ryze" and "mana" not in blocked:
        ryze_ap = sum((c.value for c in contributions["ability_power"]), start=Fraction(0))
        if ryze_ap > 0:
            mana_parts = list(contributions["mana"])
            base_plus_bonus_mana = sum((c.value for c in mana_parts), start=Fraction(0))
            mana_amp = (ryze_ap / 100) * RYZE_MANA_PCT_PER_100_AP
            ryze_labels = [
                Label.DERIVED,
                *(c.label for c in contributions["ability_power"] if c.value),
                *(c.label for c in mana_parts if c.value),
            ]
            contributions["mana"].append(
                Contribution(
                    base_plus_bonus_mana * mana_amp,
                    "bonus",
                    f"{PASSIVES_RULES} (Ryze Arcane Mastery)",
                    weakest(ryze_labels),
                    f"+{format_number(mana_amp * 100)}% max mana from {format_number(ryze_ap)} AP",
                )
            )

    if champion.id == "Rammus" and "armor" not in blocked and "magic_resist" not in blocked:
        r_armor = sum((c.value for c in contributions["armor"]), start=Fraction(0))
        r_mr = sum((c.value for c in contributions["magic_resist"]), start=Fraction(0))
        spiked_ad = r_armor * RAMMUS_ARMOR_TO_AD + r_mr * RAMMUS_MR_TO_AD
        if spiked_ad > 0:
            r_labels = [
                Label.DERIVED,
                *(c.label for c in contributions["armor"] if c.value),
                *(c.label for c in contributions["magic_resist"] if c.value),
            ]
            contributions["attack_damage"].append(
                Contribution(
                    spiked_ad,
                    "bonus",
                    f"{PASSIVES_RULES} (Rammus Spiked Shell)",
                    weakest(r_labels),
                    f"15% Armor ({format_number(r_armor)}) + 15% MR ({format_number(r_mr)}) as AD",
                )
            )

    for issue in applicable:
        if level == 1:
            notes.append(f"{issue.id} does not affect level 1 (no growth applies)")
    notes += list(extra_notes)
    notes += list(extra_pending)

    def _stat_def(stat_id: str) -> StatDef:
        definition = STATS[stat_id]
        if stat_id == "attack_speed":
            if champion.id == "Belveth":
                return replace(definition, cap=None)
            if champion.id == "Zeri":
                return replace(definition, cap=ZERI_ATTACK_SPEED_CAP)
        return definition

    values = {
        stat_id: StatValue(_stat_def(stat_id), tuple(contributions[stat_id]), blocked.get(stat_id))
        for stat_id in STATS
    }
    return StatSheet(
        champion,
        level,
        tuple(items),
        assumed,
        values,
        tuple(notes),
        ratio,
        tuple(extra_pending),
        move_speed_percents=raw_ms_percents,
        move_speed_bonus_amp=move_speed_bonus_amp,
        post_ms_effects=tuple(post_ms_effects),
        ap_weight=ap_weight,
        holder_range=champ_range,
        amplifiers=tuple(amplifiers),
    )
