"""Generate the description stats of every Summoner's Rift item.

Data Dragon puts most item stats in ``stats``, but some (ability haste,
lethality, penetration, omnivamp, tenacity, base regeneration percentages…)
only appear in the ``<stats>`` block of the description. This module reads
that block for every purchasable Summoner's Rift item and writes
``lol-knowledge/objects/catalog-stats.json``. Every entry quotes the line it
comes from, so the catalog validator checks it like a curated stat.

The output is deterministic: ``validate`` regenerates it from the snapshot and
fails when the file on disk differs.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .catalog import ObjectModelError, Snapshot, derive_stats, description_text
from .schema import GENERATED_STATS_RELATIVE_PATH

GENERATED_KIND = "lol-object-description-stats"
GENERATED_SCHEMA_VERSION = 1
SUMMONERS_RIFT = "11"
# Mode variants (ARAM, Arena…) use ids of five or more digits.
MAX_ITEM_ID = 9999
SELECTION = (
    "maps['11'] is true, gold.purchasable is true and the id is a number up to 9999 "
    "(longer ids are mode variants)"
)
LOCALE = "es_ES"

_STATS_BLOCK = re.compile(r"<stats>(.*?)</stats>", re.DOTALL)
_LINE = re.compile(r"(?P<number>\d+(?:[.,]\d+)?)(?P<percent>%?) de (?P<phrase>.+)")
_EFFECT_TAGS = ("<passive>", "<active>")

# Phrase of the es_ES description -> (canonical stat, kind). ``None`` means the
# kind follows the "%" sign of the number.
STAT_PHRASES: dict[str, tuple[str, str | None]] = {
    "vida": ("health", "flat"),
    "maná": ("mana", "flat"),
    "armadura": ("armor", "flat"),
    "resistencia mágica": ("magic_resist", "flat"),
    "daño de ataque": ("attack_damage", "flat"),
    "poder de habilidad": ("ability_power", "flat"),
    "velocidad de habilidades": ("ability_haste", "flat"),
    "letalidad": ("lethality", "flat"),
    "velocidad de ataque": ("attack_speed", "percent"),
    "velocidad de movimiento": ("move_speed", None),
    "probabilidad de impacto crítico": ("crit_chance", "percent"),
    "daño de impacto crítico": ("crit_damage_bonus", "percent"),
    "robo de vida": ("life_steal", "percent"),
    "omnisucción": ("omnivamp", "percent"),
    "tenacidad": ("tenacity", "percent"),
    "regeneración de vida básica": ("health_regen", "percent"),
    "regeneración de maná básica": ("mana_regen", "percent"),
    "penetración de armadura": ("armor_penetration_percent", "percent"),
}
# Phrases whose stat depends on the "%" sign.
SIGNED_PHRASES: dict[str, tuple[str, str]] = {
    "penetración mágica": ("magic_penetration_flat", "magic_penetration_percent"),
}
# Data Dragon renders unpublished amounts as 0, so a 0 is never taken as a real zero.
ZERO_REASON = "the description shows 0, which Data Dragon also uses for unpublished amounts"
# Lines that are not a stat of the engine; they are kept, with the reason.
UNMODELLED_PHRASES: dict[str, str] = {
    "poder de curaciones y escudos": "heal and shield power is not a stat of the engine",
    "oro cada 10 segundos": "gold income is not a champion stat",
}


def summoners_rift_items(snapshot: Snapshot) -> list[str]:
    """Ids of the purchasable Summoner's Rift items, in numeric order."""
    selected = []
    for item_id, item in snapshot.items.items():
        if not isinstance(item, Mapping) or not str(item_id).isdigit():
            continue
        if int(item_id) > MAX_ITEM_ID:
            continue
        maps = item.get("maps") if isinstance(item.get("maps"), Mapping) else {}
        gold = item.get("gold") if isinstance(item.get("gold"), Mapping) else {}
        if maps.get(SUMMONERS_RIFT) is True and gold.get("purchasable") is True:
            selected.append(str(item_id))
    return sorted(selected, key=int)


def _number(text: str) -> int | float:
    value = float(text.replace(",", "."))
    return int(value) if value.is_integer() else value


def _classify(phrase: str, percent: bool) -> tuple[str, str] | None:
    if phrase in SIGNED_PHRASES:
        flat, percentage = SIGNED_PHRASES[phrase]
        return (percentage, "percent") if percent else (flat, "flat")
    mapped = STAT_PHRASES.get(phrase)
    if mapped is None:
        return None
    stat_id, kind = mapped
    return stat_id, kind or ("percent" if percent else "flat")


def _item_entry(item_id: str, item: Mapping[str, Any]) -> dict[str, Any]:
    description = item.get("description")
    if not isinstance(description, str):
        raise ObjectModelError(f"item {item_id} has no description")
    derived, _ = derive_stats(item)
    official = {(stat["id"], stat["kind"]): stat["value"] for stat in derived}
    stats: list[dict[str, Any]] = []
    unmodelled: list[dict[str, Any]] = []
    block = _STATS_BLOCK.search(description)
    for raw_line in block.group(1).split("<br>") if block else ():
        line = description_text(raw_line)
        if not line:
            continue
        match = _LINE.fullmatch(line)
        if match is None:
            raise ObjectModelError(f"item {item_id}: stat line {line!r} is not 'N de …'")
        phrase = match.group("phrase")
        value = _number(match.group("number"))
        if phrase in UNMODELLED_PHRASES:
            unmodelled.append({"quote": line, "reason": UNMODELLED_PHRASES[phrase]})
            continue
        classified = _classify(phrase, match.group("percent") == "%")
        if classified is None:
            raise ObjectModelError(f"item {item_id}: unknown stat phrase {phrase!r}")
        stat_id, kind = classified
        if (kind == "percent") != (match.group("percent") == "%"):
            raise ObjectModelError(f"item {item_id}: {line!r} does not match kind {kind!r}")
        if (stat_id, kind) in official:
            if official[(stat_id, kind)] != value:
                raise ObjectModelError(
                    f"item {item_id}: description says {line!r}, Data Dragon stats say "
                    f"{official[(stat_id, kind)]}"
                )
            continue
        if value == 0:
            stats.append(
                {
                    "id": stat_id,
                    "kind": kind,
                    "status": "unknown",
                    "reason": ZERO_REASON,
                    "quote": line,
                }
            )
            continue
        stats.append({"id": stat_id, "kind": kind, "value": value, "quote": line})
    has_effects = any(tag in description for tag in _EFFECT_TAGS)
    entry: dict[str, Any] = {
        "id": item_id,
        "name": item.get("name"),
        "stats": stats,
        "effects_in_description": has_effects,
    }
    if unmodelled:
        entry["unmodelled_stats"] = unmodelled
    return entry


def generate_description_stats(snapshot: Snapshot) -> dict[str, Any]:
    """The generated document for ``snapshot``; raises on any line it cannot read."""
    if snapshot.locale != LOCALE:
        raise ObjectModelError(f"stat phrases exist for {LOCALE} only, not {snapshot.locale}")
    return {
        "schema_version": GENERATED_SCHEMA_VERSION,
        "kind": GENERATED_KIND,
        "game_version": snapshot.patch,
        "items_sha256": snapshot.items_sha256,
        "generator": "src/lol_knowledge/objects/generate.py",
        "selection": SELECTION,
        "objects": [
            _item_entry(item_id, snapshot.items[item_id])
            for item_id in summoners_rift_items(snapshot)
        ],
    }


def dump_generated(document: Mapping[str, Any]) -> str:
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def load_generated(root: Path) -> Mapping[str, Any] | None:
    """The generated document on disk, or ``None`` when the project has none."""
    path = root / GENERATED_STATS_RELATIVE_PATH
    if not path.is_file():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ObjectModelError(
            f"cannot read {GENERATED_STATS_RELATIVE_PATH.as_posix()}: {exc}"
        ) from exc
    if not isinstance(document, Mapping):
        raise ObjectModelError("the generated stats must be a JSON object")
    return document
