"""Game data needed by the stat sheet, and the loaders that read it from disk.

The data classes are plain values. Only the ``load_*`` functions touch the
filesystem; everything else in this package works on these values.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any

from ..damage import to_fraction
from ..ddragon import validate_champion_id
from ..errors import DamageInputError, PayloadError, StatsError
from ..objects import ObjectModelError, load_model
from .labels import Label

CURRENT = Path("data") / "current"
OFFICIAL_ITEM_SOURCES = frozenset({"ddragon_stat", "ddragon_description"})


@dataclass(frozen=True)
class SpellData:
    slot: str
    id: str
    name: str
    cooldowns: tuple[Fraction, ...]


@dataclass(frozen=True)
class ChampionData:
    id: str
    name: str
    patch: str
    locale: str
    resource: str
    stats: Mapping[str, Fraction]
    spells: tuple[SpellData, ...]


@dataclass(frozen=True)
class ItemStat:
    stat: str
    kind: str
    value: Fraction
    source: str
    # A Data Dragon value whose unit the model converted is derived, not official.
    label: Label = Label.OFFICIAL
    note: str = ""


@dataclass(frozen=True)
class ItemData:
    """A curated item: its stats and, untouched, the effects of the object model."""

    id: str
    name: str
    game_version: str
    stats: tuple[ItemStat, ...]
    effects: tuple[Mapping[str, Any], ...] = field(default=(), compare=False, hash=False)
    # "complete" when every effect of the description is in ``effects``.
    effect_review: str = "complete"


def _number(value: Any, context: str) -> Fraction:
    if isinstance(value, float) and not math.isfinite(value):
        raise StatsError(f"{context}: {value!r} is not finite")
    try:
        return to_fraction(value, context)
    except DamageInputError as exc:
        raise StatsError(str(exc)) from exc


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise StatsError(f"{path.as_posix()} not found") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StatsError(f"{path.as_posix()} is not valid UTF-8 JSON: {exc}") from exc


SPELL_SLOTS = ("Q", "W", "E", "R")


def champion_from_document(document: Mapping[str, Any], *, patch: str, locale: str) -> ChampionData:
    """Build ``ChampionData`` from one Data Dragon champion document."""
    if not isinstance(document, Mapping):
        raise StatsError("champion document must be a JSON object")
    try:
        champion_id = validate_champion_id(document.get("id"))
    except PayloadError as exc:
        raise StatsError(str(exc)) from exc
    stats = document.get("stats")
    if not isinstance(stats, Mapping) or not stats:
        raise StatsError(f"{champion_id}: 'stats' must be a non-empty object")
    numbers = {key: _number(value, f"{champion_id}.stats.{key}") for key, value in stats.items()}
    spells_raw = document.get("spells")
    if not isinstance(spells_raw, Sequence) or len(spells_raw) != len(SPELL_SLOTS):
        raise StatsError(f"{champion_id}: expected {len(SPELL_SLOTS)} spells")
    spells = []
    for slot, spell in zip(SPELL_SLOTS, spells_raw, strict=True):
        if not isinstance(spell, Mapping):
            raise StatsError(f"{champion_id}.{slot}: spell must be an object")
        cooldowns = spell.get("cooldown")
        maxrank = spell.get("maxrank")
        if (
            not isinstance(cooldowns, Sequence)
            or isinstance(cooldowns, (str, bytes))
            or not isinstance(maxrank, int)
            or len(cooldowns) != maxrank
            or maxrank < 1
        ):
            raise StatsError(f"{champion_id}.{slot}: cooldown must list one value per rank")
        values = tuple(_number(value, f"{champion_id}.{slot}.cooldown") for value in cooldowns)
        if any(value < 0 for value in values):
            raise StatsError(f"{champion_id}.{slot}: negative cooldown")
        spells.append(SpellData(slot, str(spell.get("id", "")), str(spell.get("name", "")), values))
    resource = document.get("partype")
    return ChampionData(
        id=champion_id,
        name=str(document.get("name", champion_id)),
        patch=patch,
        locale=locale,
        resource=resource if isinstance(resource, str) else "",
        stats=numbers,
        spells=tuple(spells),
    )


def _manifest(root: Path) -> tuple[str, str]:
    manifest = _read_json(root / CURRENT / "manifest.json")
    patch = manifest.get("patch") if isinstance(manifest, Mapping) else None
    locale = manifest.get("locale") if isinstance(manifest, Mapping) else None
    if not isinstance(patch, str) or not isinstance(locale, str):
        raise StatsError("data/current/manifest.json must declare 'patch' and 'locale'")
    return patch, locale


def resolve_champion_id(root: Path, name: str) -> str:
    """Find a champion id in the snapshot index (case-insensitive); never build paths from input."""
    index = _read_json(root / CURRENT / "champion-index.json")
    if not isinstance(index, Sequence):
        raise StatsError("data/current/champion-index.json must be a list")
    ids = [entry.get("id") for entry in index if isinstance(entry, Mapping)]
    wanted = name.strip().lower()
    for champion_id in ids:
        if isinstance(champion_id, str) and champion_id.lower() == wanted:
            try:
                return validate_champion_id(champion_id)
            except PayloadError as exc:
                raise StatsError(str(exc)) from exc
    raise StatsError(f"champion {name!r} is not in the snapshot")


def load_champion(root: Path, name: str) -> ChampionData:
    champion_id = resolve_champion_id(root, name)
    patch, locale = _manifest(root)
    document = _read_json(root / CURRENT / "champions" / f"{champion_id}.json")
    return champion_from_document(document, patch=patch, locale=locale)


def items_from_model(model: Mapping[str, Any], item_ids: Sequence[str]) -> tuple[ItemData, ...]:
    """Select curated items from the object model; uncurated ids are rejected."""
    game_version = model.get("game_version")
    objects = {str(obj.get("id")): obj for obj in model.get("objects") or []}
    selected = []
    for item_id in item_ids:
        obj = objects.get(str(item_id))
        if obj is None:
            raise StatsError(
                f"item {item_id!r} is not in the object catalog (purchasable Summoner's Rift "
                "items and curated objects); mode variants are not modelled"
            )
        stats = []
        for entry in obj.get("stats") or []:
            source = (entry.get("source") or {}).get("kind")
            if source not in OFFICIAL_ITEM_SOURCES:
                raise StatsError(f"item {item_id}: unsupported stat source {source!r}")
            if entry.get("value") is None:
                # Unknown in the source: a pending zero keeps the gap visible.
                stats.append(
                    ItemStat(
                        stat=str(entry.get("id")),
                        kind=str(entry.get("kind")),
                        value=Fraction(0),
                        source=source,
                        label=Label.PENDING,
                        note=f"value unknown: {entry.get('reason')}",
                    )
                )
                continue
            conversion = entry.get("unit_conversion")
            stats.append(
                ItemStat(
                    stat=str(entry.get("id")),
                    kind=str(entry.get("kind")),
                    value=_number(entry.get("value"), f"item {item_id}.{entry.get('id')}"),
                    source=source,
                    label=Label.DERIVED if conversion else Label.OFFICIAL,
                    note=f"unit converted: {conversion}" if conversion else "",
                )
            )
        selected.append(
            ItemData(
                str(obj["id"]),
                str(obj.get("name", "")),
                str(game_version),
                tuple(stats),
                tuple(obj.get("effects") or ()),
                str(obj.get("effect_review")),
            )
        )
    return tuple(selected)


def load_items(root: Path, item_ids: Sequence[str]) -> tuple[ItemData, ...]:
    if not item_ids:
        return ()
    try:
        model, _ = load_model(root)
    except ObjectModelError as exc:
        raise StatsError(f"object model: {exc}") from exc
    return items_from_model(model, item_ids)
