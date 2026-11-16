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
from .data import ChampionData, ItemData
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
# Champions whose kit removes or changes the attack speed cap (attack-speed.md, V3).
ATTACK_SPEED_CAP_KITS = frozenset({"Belveth", "Graves", "Jhin", "Sion", "Zeri"})
# Data Dragon crit chance base and growth; 0 for every champion (critical-strike.md, C8).
CRIT_FIELDS = ("crit", "critperlevel")
# Cassiopeia's passive increases the effectiveness of movement speed bonuses (move-speed.md, M5).
MOVE_SPEED_KITS = frozenset({"Cassiopeia"})
# Yasuo's and Yone's passives (critical-strike.md, C9): their crit chance from every
# other source is doubled, and each 1 % above 100 % becomes 0.5 bonus attack damage.
CRIT_CHANCE_KITS = frozenset({"Yasuo", "Yone"})
CRIT_CHANCE_KIT_MULTIPLIER = 2
EXCESS_CRIT_AD = 50  # bonus AD per 1.0 (100 %) of excess crit chance: 0.5 per 1 %
MANA_STATS = frozenset({"mana", "mana_regen"})
MANA_RESOURCE = {"es_ES": "Maná", "en_US": "Mana"}


@dataclass(frozen=True)
class Contribution:
    value: Fraction
    scope: str  # "base" (champion and growth) or "bonus" (items, assumptions)
    source: str
    label: Label
    note: str = ""


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
class StatSheet:
    champion: ChampionData
    level: int
    items: tuple[ItemData, ...]
    assumptions: Mapping[str, Fraction]
    values: Mapping[str, StatValue]
    notes: tuple[str, ...] = field(default=())

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
    if effect.get("scenario") is not None:
        return f"scenario {effect['scenario']}"
    components = effect.get("components") or ()
    if (
        (effect.get("trigger") or {}).get("event") == "always"
        and not effect.get("conditions")
        and components
        and all(component.get("kind") == "stat_modifier" for component in components)
    ):
        return "always"
    return None


@dataclass(frozen=True)
class _Amplifier:
    """``percent`` % of a stat's total, added once every other amount is known."""

    stat: str
    percent: Fraction
    source: str
    label: Label


def _sheet_effects(item: ItemData) -> tuple[list[tuple[str, Contribution]], list[_Amplifier]]:
    """Stats from the effects of ``item`` that the sheet applies (``sheet_effect_reason``).

    A ``flat`` component adds its amount in the catalog unit: percentage points
    for fraction stats (25 -> 0.25), the stat's own unit otherwise. A
    ``percent`` component with scope ``total`` amplifies the total of an amount
    stat (Rabadon's Deathcap: +30 % ability power).
    """
    flat: list[tuple[str, Contribution]] = []
    amplifiers: list[_Amplifier] = []
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
            definition = _receiver(str(component.get("stat")))
            if mode == "percent" and (
                scenario is not None
                or component.get("scope") != "total"
                or definition.unit is not Unit.AMOUNT
            ):
                raise StatsError(f"{title}: only always effects amplify a total amount")
            if status != "evaluable":
                why = f"effect {status}, not applied"
                why = f"{note}; {why}" if note else why
                flat.append(
                    (definition.id, Contribution(Fraction(0), "bonus", source, Label.PENDING, why))
                )
                continue
            try:
                amount = evaluate_formula(component.get("formula"), {}).exact
            except FormulaError as exc:
                raise StatsError(f"{title}: {exc}") from exc
            if mode == "percent":
                amplifiers.append(_Amplifier(definition.id, amount, source, label))
                continue
            value = amount / 100 if definition.unit is Unit.FRACTION else amount
            if definition.unit is Unit.FRACTION and not 0 <= value <= 1:
                raise StatsError(f"{title}: {value} is not a fraction 0..1")
            flat.append((definition.id, Contribution(value, "bonus", source, label, note)))
    return flat, amplifiers


def _amplified(amplifier: _Amplifier, current: Sequence[Contribution]) -> Contribution:
    """The amplifier's share of the total of ``current`` (amplifiers do not compound)."""
    total = sum((item.value for item in current), start=Fraction(0))
    return Contribution(
        total * amplifier.percent / 100,
        "bonus",
        amplifier.source,
        weakest([amplifier.label, *(item.label for item in current)]),
        f"{format_number(amplifier.percent)}% of the total",
    )


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


def _scaled_attack_speed(
    champion: ChampionData, bonus: Sequence[Contribution], derived: DerivedRecords | None
) -> Contribution | str | None:
    """Bonus attack speed times the champion's ratio, or why it cannot be computed.

    ``None`` means there is no bonus attack speed, so the total is the base.
    """
    total_bonus = sum((item.value for item in bonus), start=Fraction(0))
    if not total_bonus:
        return None
    ratio = derived.value(champion.id, ATTACK_SPEED_RATIO) if derived else None
    if derived is None or ratio is None:
        return (
            f"bonus attack speed {format_number(total_bonus)} needs the attack speed ratio, "
            f"which Data Dragon does not publish, and the derived records have no "
            f"{champion.id}.{ATTACK_SPEED_RATIO} (see {ATTACK_SPEED_RULES})"
        )
    note = f"ratio {format_number(ratio)} x bonus {format_percent(total_bonus)}"
    label = Label.DERIVED
    if not derived.matches_patch(champion.patch):
        label = Label.PENDING
        note += f"; client {derived.game_version} record used with snapshot {champion.patch}"
    return Contribution(
        ratio * total_bonus,
        "bonus",
        f"{derived.path} {champion.id}.{ATTACK_SPEED_RATIO} ({derived.content_version})"
        " x attack_speed_bonus",
        weakest([label, *(item.label for item in bonus)]),
        note,
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


def build_stat_sheet(
    champion: ChampionData,
    level: int,
    items: Sequence[ItemData] = (),
    issues: Sequence[DataIssue] = (),
    assumptions: Mapping[str, object] | None = None,
    derived: DerivedRecords | None = None,
    extras: Sequence[tuple[str, Contribution]] = (),
) -> StatSheet:
    """Resolve the champion's statistics at ``level`` with ``items``.

    A field with an open data issue is replaced, in this order, by an explicit
    assumption (``Pendiente de verificación``) or by a derived client record
    (``Derivado`` when the client patch matches the snapshot, otherwise
    ``Pendiente de verificación``). With neither, the statistic is blocked.

    ``extras`` adds further contributions, such as stats an ability grants
    passively (see ``lol_knowledge.kit.passive_contributions``).

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
    amplifiers: list[_Amplifier] = []
    blocked: dict[str, str] = {}
    notes: list[str] = []
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
        effect_stats, item_amplifiers = _sheet_effects(item)
        for stat_id, contribution in effect_stats:
            contributions[stat_id].append(contribution)
        amplifiers += item_amplifiers

    for stat_id, extra in extras:
        definition = _receiver(stat_id)
        if definition.unit is Unit.FRACTION and not 0 <= extra.value <= 1:
            raise StatsError(f"extra {stat_id}: {extra.value} is not a fraction 0..1")
        if definition.id == "tenacity":
            extra = _ungrouped_tenacity(extra)
        contributions[definition.id].append(extra)

    # Percentages last, once every flat amount is known (regeneration.md, move-speed.md).
    for stat_id, pending in percents.items():
        reference = list(contributions[stat_id])
        contributions[stat_id] += [
            _percent_amount(STATS[stat_id], percent, reference) for percent in pending
        ]
    # Amplifiers of a total last, all on the same total (only Rabadon's Deathcap today).
    reference = {amplifier.stat: list(contributions[amplifier.stat]) for amplifier in amplifiers}
    for amplifier in amplifiers:
        contributions[amplifier.stat].append(_amplified(amplifier, reference[amplifier.stat]))
    if champion.id in MOVE_SPEED_KITS:
        reason = f"{champion.id}'s passive changes the effectiveness of movement speed bonuses"
        contributions["move_speed"].append(
            Contribution(Fraction(0), "bonus", MOVE_SPEED_RULES, Label.PENDING, reason)
        )
        notes.append(reason)

    scaled = _scaled_attack_speed(champion, contributions["attack_speed_bonus"], derived)
    if isinstance(scaled, str):
        blocked["attack_speed"] = scaled
    elif scaled is not None:
        contributions["attack_speed"].append(scaled)
    if champion.id in ATTACK_SPEED_CAP_KITS:
        reason = f"{champion.id}'s kit changes the attack speed cap; not modelled"
        contributions["attack_speed"].append(
            Contribution(Fraction(0), "bonus", ATTACK_SPEED_RULES, Label.PENDING, reason)
        )
        notes.append(reason)
    if champion.id in CRIT_CHANCE_KITS:
        if "crit_chance" in blocked:
            blocked["attack_damage"] = (
                f"{champion.id}'s passive converts excess crit chance into attack damage, "
                "and crit chance is blocked"
            )
        else:
            _crit_chance_passive(champion, contributions)

    for issue in applicable:
        if level == 1:
            notes.append(f"{issue.id} does not affect level 1 (no growth applies)")

    values = {
        stat_id: StatValue(STATS[stat_id], tuple(contributions[stat_id]), blocked.get(stat_id))
        for stat_id in STATS
    }
    return StatSheet(champion, level, tuple(items), assumed, values, tuple(notes))
