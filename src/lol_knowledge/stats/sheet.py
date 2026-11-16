"""Stat sheet: every statistic as a list of sourced contributions."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from fractions import Fraction

from ..damage import format_number, to_fraction
from ..errors import DamageInputError, StatsError
from .data import ChampionData, ItemData
from .derived import DerivedRecords
from .growth import check_level, growth_multiplier
from .issues import DataIssue
from .labels import Label, weakest
from .registry import ATTACK_SPEED_RULES, CRIT_RULES, STATS, Stacking, StatDef, Unit, stat

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
        return weakest(item.label for item in self.contributions)

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
        return total if cap is None else min(total, cap)

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
    note = f"ratio {format_number(ratio)} x bonus {format_number(total_bonus)}"
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
            f"passive doubles critical strike chance ({format_number(total)} x "
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
                f"excess critical strike chance {format_number(excess)} x 0.5 per 1%",
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
            if definition.resolvable and entry.kind != definition.item_kind:
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
            contributions[definition.id].append(
                Contribution(
                    value,
                    "bonus",
                    f"data:item:{item.id} {entry.source} ({item.game_version})",
                    Label.OFFICIAL,
                    note,
                )
            )

    for stat_id, extra in extras:
        definition = _receiver(stat_id)
        if definition.unit is Unit.FRACTION and not 0 <= extra.value <= 1:
            raise StatsError(f"extra {stat_id}: {extra.value} is not a fraction 0..1")
        contributions[definition.id].append(extra)

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
