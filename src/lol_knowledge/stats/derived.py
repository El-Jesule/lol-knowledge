"""Derived champion records extracted from the game client (lol-knowledge/derived/).

They replace Data Dragon fields that have an open data issue. They are
``Derivado`` data, never official, and they carry the client version they came
from so a patch mismatch with the snapshot is visible.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from ..cache import DEFAULT_CACHE
from ..errors import StatsError

RECORDS_PATH = Path("lol-knowledge") / "derived" / "champion-records.json"
SCHEMA = "lol-derived-champion-records/1"
GAME_VERSION = re.compile(r"\d+\.\d+")
KNOWN_FIELDS = frozenset(
    {
        "hp",
        "hpperlevel",
        "attackdamage",
        "attackdamageperlevel",
        "armor",
        "armorperlevel",
        "spellblock",
        "spellblockperlevel",
        "movespeed",
        "attackrange",
        "attackspeed",
        "attackspeedratio",
        "attackspeedperlevel",
        "critdamagemultiplier",
        "adaptiveforceapweight",
    }
)


@dataclass(frozen=True)
class DerivedRecords:
    path: str
    content_version: str
    game_version: str
    champions: Mapping[str, Mapping[str, Fraction]]

    def value(self, champion_id: str, field: str) -> Fraction | None:
        return self.champions.get(champion_id, {}).get(field)

    def matches_patch(self, patch: str) -> bool:
        """Whether the client version is the snapshot's major.minor."""
        return ".".join(patch.split(".")[:2]) == self.game_version


def parse_records(document: Any, path: str = RECORDS_PATH.as_posix()) -> DerivedRecords:
    if not isinstance(document, Mapping):
        raise StatsError("derived records: the document must be a JSON object")
    if document.get("schema") != SCHEMA:
        raise StatsError(f"derived records: schema must be {SCHEMA!r}")
    if document.get("label") != "Derivado":
        raise StatsError("derived records: label must be 'Derivado'")
    content_version = document.get("content_version")
    game_version = document.get("game_version")
    if not isinstance(content_version, str) or not content_version:
        raise StatsError("derived records: content_version must be a non-empty string")
    if not isinstance(game_version, str) or GAME_VERSION.fullmatch(game_version) is None:
        raise StatsError("derived records: game_version must look like 16.22")
    if not content_version.startswith(f"{game_version}."):
        raise StatsError("derived records: content_version does not match game_version")
    champions_raw = document.get("champions")
    if not isinstance(champions_raw, Mapping):
        raise StatsError("derived records: 'champions' must be an object")
    champions: dict[str, dict[str, Fraction]] = {}
    for champion_id, record in champions_raw.items():
        fields = record.get("fields") if isinstance(record, Mapping) else None
        if not isinstance(fields, Mapping):
            raise StatsError(f"derived records: {champion_id}: 'fields' must be an object")
        parsed: dict[str, Fraction] = {}
        for field, value in fields.items():
            if field not in KNOWN_FIELDS:
                raise StatsError(f"derived records: {champion_id}: unknown field {field!r}")
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
                or value < 0
            ):
                raise StatsError(
                    f"derived records: {champion_id}.{field} must be a non-negative number"
                )
            parsed[field] = Fraction(repr(float(value)))
        champions[str(champion_id)] = parsed
    return DerivedRecords(path, content_version, game_version, champions)


def _load_records_uncached(root: Path) -> DerivedRecords | None:
    path = root / RECORDS_PATH
    if not path.is_file():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StatsError(f"{RECORDS_PATH.as_posix()} is not valid UTF-8 JSON: {exc}") from exc
    return parse_records(document)


def load_records(root: Path) -> DerivedRecords | None:
    """Load the derived records, or ``None`` when the project has none."""
    return DEFAULT_CACHE.records(root, lambda: _load_records_uncached(root))
