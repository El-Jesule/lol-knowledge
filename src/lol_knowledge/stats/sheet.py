"""Stat sheet: every statistic as a list of sourced contributions."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from fractions import Fraction

from ..damage import to_fraction
from ..errors import DamageInputError, StatsError
from .data import ChampionData, ItemData
from .growth import check_level, growth_multiplier
from .issues import DataIssue
from .labels import Label, weakest
from .registry import STATS, Stacking, StatDef, Unit, stat

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
    # Attack speed growth follows another formula; only the base is listed.
    ("attack_speed", "attackspeed", None),
)
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
        return weakest(item.label for item in self.contributions)

    def _check(self) -> None:
        if self.blocked:
            raise StatBlocked(f"{self.definition.id}: {self.blocked}")
        if not self.definition.resolvable:
            raise StatBlocked(f"{self.definition.id}: {self.definition.pending}")

    def total(self) -> Fraction:
        self._check()
        values = [item.value for item in self.contributions]
        if self.definition.stacking is Stacking.MULTIPLICATIVE:
            return 1 - math.prod((1 - value for value in values), start=Fraction(1))
        return sum(values, start=Fraction(0))

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


def build_stat_sheet(
    champion: ChampionData,
    level: int,
    items: Sequence[ItemData] = (),
    issues: Sequence[DataIssue] = (),
    assumptions: Mapping[str, object] | None = None,
) -> StatSheet:
    """Resolve the champion's statistics at ``level`` with ``items``.

    Open data issues for this champion and patch block the statistics they
    affect, unless ``assumptions`` gives a value for the affected field; an
    assumed value is labelled ``Pendiente de verificación``.
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
        if issue is not None and growth_field not in assumed:
            blocked[stat_id] = (
                f"{issue.id}: {issue.summary} Use --assume {growth_field}=<value> "
                f"(see {issue.documentation})"
            )
            continue
        if issue is not None:
            growth = assumed[growth_field]
            source = f"assumption {growth_field}={growth} ({issue.id})"
            label = Label.PENDING
        else:
            growth = champion.stats[growth_field]
            source = _source(champion, growth_field)
            label = Label.DERIVED if growth else Label.OFFICIAL
        contributions[stat_id].append(
            Contribution(growth * multiplier, "base", source, label, f"growth to level {level}")
        )

    for item in items:
        for entry in item.stats:
            definition = stat(entry.stat)
            if entry.kind not in {"flat", "percent"}:
                raise StatsError(f"item {item.id}.{entry.stat}: unknown kind {entry.kind!r}")
            if definition.resolvable and entry.kind != definition.item_kind:
                raise StatsError(
                    f"item {item.id}.{entry.stat}: kind {entry.kind!r} is not supported "
                    f"for {definition.id}"
                )
            value = entry.value / 100 if entry.kind == "percent" else entry.value
            if definition.unit is Unit.FRACTION and not 0 <= value <= 1:
                raise StatsError(f"item {item.id}.{entry.stat}: {value} is not a fraction 0..1")
            note = "percent" if entry.kind == "percent" and definition.unit is Unit.AMOUNT else ""
            contributions[entry.stat].append(
                Contribution(
                    value,
                    "bonus",
                    f"data:item:{item.id} {entry.source} ({item.game_version})",
                    Label.OFFICIAL,
                    note,
                )
            )

    for issue in applicable:
        if level == 1:
            notes.append(f"{issue.id} does not affect level 1 (no growth applies)")

    values = {
        stat_id: StatValue(STATS[stat_id], tuple(contributions[stat_id]), blocked.get(stat_id))
        for stat_id in STATS
    }
    return StatSheet(champion, level, tuple(items), assumed, values, tuple(notes))
