"""Consumable Elixirs and Ornn Masterwork item upgrades (OBJ-12, DEC-03).

Elixir stat values come from official Data Dragon descriptions
(``data/current/items.json``: ``2138``, ``2139``, ``2140``).
Ornn Masterwork stat efficiencies come directly from the installed client
``16.23`` ``Ornn.wad.client`` (``OrnnP.DataValues``: ``UpgradeTotalGoldValue=1000``,
``UpgradeADEff=35``, ``UpgradeAPEff=20``, ``UpgradeHPEff=2.66``,
``UpgradeAREff=20``, ``UpgradeMREff=18``, ``UpgradeAHEff=31.25``,
``UpgradeASEff=30``).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from .damage import format_number
from .errors import StatsError
from .objects.legality import ItemGroups
from .stats.data import ItemData
from .stats.labels import Label
from .stats.sheet import Contribution

ELIXIR_GOLD = 500
ELIXIR_MIN_LEVEL = 9
ORNN_MASTERWORK_LEVEL = 13
ORNN_TOTAL_GOLD_VALUE = Fraction(1000)

# Client 16.23 OrnnP.DataValues gold efficiency per 1 unit (attack_speed_bonus is fraction 0..1)
ORNN_STAT_GOLD_EFFICIENCY: dict[str, Fraction] = {
    "attack_damage": Fraction(35),
    "ability_power": Fraction(20),
    "health": Fraction("2.66"),
    "armor": Fraction(20),
    "magic_resist": Fraction(18),
    "ability_haste": Fraction("31.25"),
    "attack_speed_bonus": Fraction(3000),  # 30 g per 1% -> 3000 g per 1.00 fraction
}

_ITEM_STAT_TO_ORNN: dict[str, str] = {
    "attack_damage": "attack_damage",
    "ability_power": "ability_power",
    "health": "health",
    "armor": "armor",
    "magic_resist": "magic_resist",
    "ability_haste": "ability_haste",
    "attack_speed": "attack_speed_bonus",
    "attack_speed_bonus": "attack_speed_bonus",
}


@dataclass(frozen=True)
class ElixirSpec:
    id: str
    name: str
    gold: int
    flats: tuple[tuple[str, Fraction], ...]
    percents: tuple[tuple[str, Fraction], ...]
    notes: tuple[str, ...]
    label: Label = Label.OFFICIAL


ELIXIRS: dict[str, ElixirSpec] = {
    "2138": ElixirSpec(
        id="2138",
        name="Elixir de hierro",
        gold=ELIXIR_GOLD,
        flats=(("health", Fraction(300)), ("tenacity", Fraction(25, 100))),
        percents=(),
        notes=(
            "2138 Elixir de hierro (500 g, 3 min, 0 huecos): +300 vida, +25% tenacidad; "
            "tamaño y senda de +15% VM a aliados no modelados",
        ),
    ),
    "2139": ElixirSpec(
        id="2139",
        name="Elixir de brujería",
        gold=ELIXIR_GOLD,
        flats=(("ability_power", Fraction(50)),),
        percents=(("mana_regen", Fraction(15, 100)),),
        notes=(
            "2139 Elixir de brujería (500 g, 3 min, 0 huecos): +50 PH, +15% reg. maná base; "
            "proc de 25 daño verdadero (5 s CD) no aplicado automáticamente en stats",
        ),
    ),
    "2140": ElixirSpec(
        id="2140",
        name="Elixir de cólera",
        gold=ELIXIR_GOLD,
        flats=(("attack_damage", Fraction(30)),),
        percents=(),
        notes=(
            "2140 Elixir de cólera (500 g, 3 min, 0 huecos): +30 DA; "
            "12% succión física contra campeones declarada como Pendiente en rotaciones",
        ),
    ),
}

_ELIXIR_ALIASES: dict[str, str] = {
    "2138": "2138",
    "iron": "2138",
    "hierro": "2138",
    "elixir_of_iron": "2138",
    "elixirdehierro": "2138",
    "2139": "2139",
    "sorcery": "2139",
    "brujeria": "2139",
    "brujería": "2139",
    "elixir_of_sorcery": "2139",
    "elixirdebrujeria": "2139",
    "2140": "2140",
    "wrath": "2140",
    "colera": "2140",
    "cólera": "2140",
    "elixir_of_wrath": "2140",
    "elixirdecolera": "2140",
}


@dataclass(frozen=True)
class UpgradeEffect:
    """Stat contributions and metadata produced by an Elixir or Ornn Masterwork upgrade."""

    flats: tuple[tuple[str, Contribution], ...] = ()
    percents: tuple[tuple[str, Contribution], ...] = ()
    notes: tuple[str, ...] = ()
    extra_gold: int = 0
    elixir_id: str | None = None
    ornn_item_id: str | None = None


def resolve_elixir(token: str) -> ElixirSpec:
    """Resolve an elixir id or Spanish/English alias to its official ``ElixirSpec``."""
    norm = token.strip().lower().replace(" ", "").replace("-", "_")
    eid = _ELIXIR_ALIASES.get(norm)
    if eid is None:
        known = ", ".join(f"{e.id} ({e.name})" for e in ELIXIRS.values())
        raise StatsError(f"unknown elixir {token!r}; expected one of: {known}")
    return ELIXIRS[eid]


def elixir_contributions(
    token: str | None,
    *,
    level: int | None = None,
    uses_mana: bool = True,
) -> UpgradeEffect:
    """Return stat sheet contributions for one active SR elixir (max 1 active, 0 slots)."""
    if token is None or not token.strip():
        return UpgradeEffect()
    spec = resolve_elixir(token)
    source = f"elixir:{spec.id} {spec.name} (data/current/items.json)"
    flats = tuple(
        (stat_id, Contribution(val, "bonus", source, spec.label)) for stat_id, val in spec.flats
    )
    percents = tuple(
        (stat_id, Contribution(val, "bonus", source, spec.label))
        for stat_id, val in spec.percents
        if uses_mana or stat_id != "mana_regen"
    )
    notes = list(spec.notes)
    if level is not None and level < ELIXIR_MIN_LEVEL:
        notes.append(
            f"elixir:{spec.id}: en la Grieta del Invocador requiere nivel >= {ELIXIR_MIN_LEVEL} "
            f"(calculado igualmente a nivel {level})"
        )
    return UpgradeEffect(
        flats=flats,
        percents=percents,
        notes=tuple(notes),
        extra_gold=spec.gold,
        elixir_id=spec.id,
    )


def ornn_eligible_stats(item: ItemData) -> tuple[str, ...]:
    """Distinct Ornn-upgradeable stat IDs present on ``item`` (preserving deterministic order)."""
    found: list[str] = []
    for st in item.stats:
        mapped = _ITEM_STAT_TO_ORNN.get(st.stat)
        if mapped is not None and st.value > 0 and mapped not in found:
            found.append(mapped)
    return tuple(found)


def is_ornn_eligible_item(
    item: ItemData,
    *,
    item_groups: ItemGroups | None = None,
    gold: int | None = None,
) -> bool:
    """Whether ``item`` is a completed non-boots item eligible for Ornn's Masterwork upgrade."""
    if item_groups is not None and item_groups.has_boots([item.id]):
        return False
    if gold is not None and gold < 2000:
        return False
    return bool(ornn_eligible_stats(item))


def eligible_ornn_items(
    items: Sequence[ItemData],
    *,
    item_groups: ItemGroups | None = None,
    gold_by_id: dict[str, int] | None = None,
) -> list[ItemData]:
    """All items in ``items`` eligible to receive the single Ornn Masterwork upgrade (DEC-03)."""
    return [
        it
        for it in items
        if is_ornn_eligible_item(
            it,
            item_groups=item_groups,
            gold=None if gold_by_id is None else gold_by_id.get(it.id),
        )
    ]


def ornn_upgrade_contributions(
    ornn_item_id: str | None,
    items: Sequence[ItemData],
    *,
    level: int | None = None,
    item_groups: ItemGroups | None = None,
    gold: int | None = None,
) -> UpgradeEffect:
    """Return stat contributions for upgrading ONE equipped legendary item via Ornn (DEC-03)."""
    if ornn_item_id is None or not ornn_item_id.strip():
        return UpgradeEffect()
    target_id = ornn_item_id.strip()
    matched = [it for it in items if it.id == target_id]
    if not matched:
        raise StatsError(
            f"--ornn-item {target_id!r} must be one of the equipped items "
            f"({', '.join(it.id for it in items) or 'none'})"
        )
    item = matched[0]
    if not is_ornn_eligible_item(item, item_groups=item_groups, gold=gold):
        raise StatsError(
            f"--ornn-item {item.id} ({item.name}) is not eligible for Ornn Masterwork "
            "(must be a completed non-boots item with >= 1 upgradeable stat)"
        )
    stats = ornn_eligible_stats(item)
    gold_share = ORNN_TOTAL_GOLD_VALUE / len(stats)
    source = f"ornn_masterwork:{item.id} {item.name} (OrnnP.DataValues 16.23)"
    flats: list[tuple[str, Contribution]] = []
    parts_txt: list[str] = []
    for stat_id in stats:
        eff = ORNN_STAT_GOLD_EFFICIENCY[stat_id]
        bonus = gold_share / eff
        flats.append(
            (
                stat_id,
                Contribution(
                    bonus,
                    "bonus",
                    source,
                    Label.DERIVED,
                    f"1000g/{len(stats)} = {format_number(gold_share)}g / {format_number(eff)}g",
                ),
            )
        )
        if stat_id == "attack_speed_bonus":
            parts_txt.append(f"+{format_number(bonus * 100)}% AS")
        else:
            parts_txt.append(f"+{format_number(bonus)} {stat_id}")
    notes = [
        f"Ornn Masterwork en {item.id} {item.name} (máx. 1 objeto por build, 0 g extra): "
        + ", ".join(parts_txt)
        + " (OrnnP.DataValues 16.23; redondeo visual al entero del cliente no aplicado)"
    ]
    if level is not None and level < ORNN_MASTERWORK_LEVEL:
        notes.append(
            f"Ornn Masterwork: requiere nivel >= {ORNN_MASTERWORK_LEVEL} de Ornn "
            f"(calculado igualmente a nivel {level})"
        )
    return UpgradeEffect(
        flats=tuple(flats),
        notes=tuple(notes),
        extra_gold=0,
        ornn_item_id=item.id,
    )
