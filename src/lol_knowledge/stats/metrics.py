"""Metrics computed from a stat sheet. Pure functions: no file access."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from ..damage import DamageType, damage_multiplier
from .labels import Label, weakest
from .registry import HASTE_RULES
from .sheet import ENERGY_RESOURCE, MANA_RESOURCE, NO_RESOURCE, StatBlocked, StatSheet

EHP_RULES = "lol-knowledge/mechanics/effective-health.md"
RESOURCES_RULES = "lol-knowledge/mechanics/resources.md"
RESISTANCE_FOR = {DamageType.PHYSICAL: "armor", DamageType.MAGIC: "magic_resist"}


@dataclass(frozen=True)
class EffectiveHealth:
    damage_type: DamageType
    value: Fraction | None
    label: Label
    blocked: str | None = None
    rules: str = EHP_RULES


def effective_health(sheet: StatSheet, damage_type: DamageType | str) -> EffectiveHealth:
    """Raw damage of ``damage_type`` needed to deplete the champion's health."""
    kind = DamageType(damage_type)
    health = sheet["health"]
    try:
        total = health.total()
        if kind is DamageType.TRUE:
            return EffectiveHealth(kind, total, health.label)
        resistance = sheet[RESISTANCE_FOR[kind]]
        value = total / damage_multiplier(resistance.total())
    except StatBlocked as exc:
        return EffectiveHealth(kind, None, Label.PENDING, str(exc))
    return EffectiveHealth(kind, value, weakest((health.label, resistance.label, Label.DERIVED)))


@dataclass(frozen=True)
class SpellCooldown:
    slot: str
    spell_id: str
    name: str
    base: tuple[Fraction, ...]
    effective: tuple[Fraction, ...]


@dataclass(frozen=True)
class Cooldowns:
    haste: Fraction | None
    factor: Fraction | None
    label: Label
    spells: tuple[SpellCooldown, ...]
    blocked: str | None = None
    rules: str = HASTE_RULES
    basic_haste: Fraction = Fraction(0)
    ultimate_haste: Fraction = Fraction(0)


def _haste_factor(haste: Fraction) -> Fraction:
    return Fraction(100) / (100 + haste)


def ability_cooldowns(sheet: StatSheet) -> Cooldowns:
    """Cooldown of every rank of Q, W, E and R after ability, basic and ultimate haste."""
    haste_value = sheet["ability_haste"]
    basic_value = sheet["basic_ability_haste"]
    ultimate_value = sheet["ultimate_haste"]
    try:
        haste = haste_value.total()
        basic_haste = basic_value.total()
        ultimate_haste = ultimate_value.total()
    except StatBlocked as exc:
        return Cooldowns(None, None, Label.PENDING, (), str(exc))
    factor = _haste_factor(haste)
    basic_factor = _haste_factor(haste + basic_haste)
    ultimate_factor = _haste_factor(haste + ultimate_haste)
    spells = tuple(
        SpellCooldown(
            spell.slot,
            spell.id,
            spell.name,
            spell.cooldowns,
            tuple(
                value * (ultimate_factor if spell.slot == "R" else basic_factor)
                for value in spell.cooldowns
            ),
        )
        for spell in sheet.champion.spells
    )
    active_labels = [
        stat_val.label
        for stat_val, amount in (
            (haste_value, haste),
            (basic_value, basic_haste),
            (ultimate_value, ultimate_haste),
        )
        if amount != 0
    ]
    label = Label.OFFICIAL if not active_labels else weakest((*active_labels, Label.DERIVED))
    return Cooldowns(
        haste,
        factor,
        label,
        spells,
        basic_haste=basic_haste,
        ultimate_haste=ultimate_haste,
    )


@dataclass(frozen=True)
class ResourcePool:
    """Champion resource pool and passive regeneration resolved from the stat sheet.

    Covers mana (from ``sheet["mana"]`` and ``sheet["mana_regen"]``), energy (fixed
    Data Dragon pool and 50/5 s regen, unaffected by mana items or level growth),
    resourceless champions, and other champion-specific secondary bars (fury, flow,
    heat, courage, shield, ferocity, crimson rush).
    """

    kind: str  # "mana", "energy", "none" or "other"
    name: str
    maximum: Fraction | None
    regen_per_5s: Fraction | None
    label: Label
    uses_casting_pool: bool
    blocked: str | None = None
    notes: tuple[str, ...] = ()
    rules: str = RESOURCES_RULES

    @property
    def regen_per_second(self) -> Fraction | None:
        return None if self.regen_per_5s is None else self.regen_per_5s / 5


def champion_resource(sheet: StatSheet) -> ResourcePool:
    """Resolve the champion's casting or secondary resource pool (resources.md)."""
    champion = sheet.champion
    locale = champion.locale
    mana_name = MANA_RESOURCE.get(locale)
    energy_name = ENERGY_RESOURCE.get(locale)
    none_names = NO_RESOURCE.get(locale, frozenset({"", "Nada", "None"}))
    partype = champion.resource

    if mana_name is not None and partype == mana_name:
        mana_val = sheet["mana"]
        regen_val = sheet["mana_regen"]
        try:
            maximum = mana_val.total()
            regen = regen_val.total()
        except StatBlocked as exc:
            return ResourcePool("mana", partype, None, None, Label.PENDING, True, str(exc))
        return ResourcePool(
            "mana",
            partype,
            maximum,
            regen,
            weakest((mana_val.label, regen_val.label)),
            uses_casting_pool=True,
        )

    if energy_name is not None and partype == energy_name:
        maximum = champion.stats.get("mp", Fraction(0))
        regen = champion.stats.get("mpregen", Fraction(0))
        mp_growth = champion.stats.get("mpperlevel", Fraction(0))
        regen_growth = champion.stats.get("mpregenperlevel", Fraction(0))
        notes: list[str] = []
        label = Label.OFFICIAL
        if mp_growth or regen_growth:
            label = Label.PENDING
            notes.append("unexpected non-zero energy growth in Data Dragon")
        if any(
            entry.stat in {"mana", "mana_regen"} for item in sheet.items for entry in item.stats
        ):
            notes.append("mana and mana regeneration items do not affect energy")
        return ResourcePool(
            "energy",
            partype,
            maximum,
            regen,
            label,
            uses_casting_pool=True,
            notes=tuple(notes),
        )

    maximum = champion.stats.get("mp", Fraction(0))
    regen = champion.stats.get("mpregen", Fraction(0))
    if partype in none_names or (maximum == 0 and regen == 0):
        return ResourcePool(
            "none",
            partype or "none",
            Fraction(0),
            Fraction(0),
            Label.OFFICIAL,
            uses_casting_pool=False,
            notes=("champion has no mana or energy casting pool",),
        )
    return ResourcePool(
        "other",
        partype,
        maximum,
        regen,
        Label.OFFICIAL,
        uses_casting_pool=False,
        notes=(
            f"{partype} is a champion-specific secondary resource; generation and decay are "
            "not modelled as a standard casting pool",
        ),
    )


@dataclass(frozen=True)
class SpellCost:
    slot: str
    spell_id: str
    name: str
    costs: tuple[Fraction, ...]
    cost_type: str


@dataclass(frozen=True)
class AbilityCosts:
    resource_kind: str
    resource_name: str
    label: Label
    spells: tuple[SpellCost, ...]
    rules: str = RESOURCES_RULES


def ability_costs(sheet: StatSheet) -> AbilityCosts:
    """Official Data Dragon resource costs per rank for Q, W, E and R."""
    pool = champion_resource(sheet)
    spells = tuple(
        SpellCost(
            spell.slot,
            spell.id,
            spell.name,
            spell.costs or (Fraction(0),) * len(spell.cooldowns),
            spell.cost_type,
        )
        for spell in sheet.champion.spells
    )
    return AbilityCosts(pool.kind, pool.name, Label.OFFICIAL, spells)
