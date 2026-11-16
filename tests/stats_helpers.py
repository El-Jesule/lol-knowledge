"""Synthetic champions, items and issues for stat sheet tests."""

from __future__ import annotations

from fractions import Fraction

from lol_knowledge.stats import (
    ChampionData,
    DataIssue,
    ItemData,
    ItemStat,
    SpellData,
    champion_from_document,
)

PATCH = "16.20.1"

BASE_STATS = {
    "hp": 640,
    "hpperlevel": 114,
    "mp": 350,
    "mpperlevel": 55,
    "armor": 36,
    "armorperlevel": 5,
    "spellblock": 32,
    "spellblockperlevel": 2.05,
    "attackdamage": 63,
    "attackdamageperlevel": 0,
    "hpregen": 7.5,
    "hpregenperlevel": 0.8,
    "mpregen": 8.15,
    "mpregenperlevel": 0.75,
    "movespeed": 345,
    "attackspeed": 0.625,
    "attackspeedperlevel": 2.5,
    "crit": 0,
    "critperlevel": 0,
}


def champion_document(champion_id: str = "Testchamp", **overrides) -> dict:
    stats = dict(BASE_STATS)
    stats.update(overrides.pop("stats", {}))
    document = {
        "id": champion_id,
        "name": champion_id,
        "partype": "Maná",
        "stats": stats,
        "spells": [
            {"id": f"{champion_id}{slot}", "name": slot, "cooldown": cds, "maxrank": len(cds)}
            for slot, cds in (
                ("Q", [10, 9, 8, 7, 6]),
                ("W", [14, 13.5, 13, 12.5, 12]),
                ("E", [10, 9.5, 9, 8.5, 8]),
                ("R", [110, 95, 80]),
            )
        ],
    }
    document.update(overrides)
    return document


def champion(champion_id: str = "Testchamp", **overrides) -> ChampionData:
    return champion_from_document(
        champion_document(champion_id, **overrides), patch=PATCH, locale="es_ES"
    )


def item(item_id: str, *stats: tuple[str, str, float], version: str = PATCH) -> ItemData:
    return ItemData(
        item_id,
        f"Item {item_id}",
        version,
        tuple(
            ItemStat(stat, kind, Fraction(str(value)), "ddragon_stat")
            for stat, kind, value in stats
        ),
    )


def ad_growth_issue(champions: tuple[str, ...] | None = None, patch: str = PATCH) -> DataIssue:
    return DataIssue(
        id="ddragon-attack-damage-growth",
        source="data_dragon",
        patches=(patch,),
        field="attackdamageperlevel",
        champions=champions,
        status="open",
        summary="AD growth is zero.",
        documentation="lol-knowledge/mechanics/known-data-issues.md",
    )


__all__ = ["PATCH", "SpellData", "ad_growth_issue", "champion", "champion_document", "item"]
