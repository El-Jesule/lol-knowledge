"""Registry of known defects in official data (lol-knowledge/data-issues.json)."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..errors import StatsError

ISSUES_PATH = Path("lol-knowledge") / "data-issues.json"
SCHEMA = "lol-data-issues/1"
SOURCES = frozenset({"data_dragon"})
STATUSES = frozenset({"open", "resolved"})
_FIELDS = ("id", "source", "patch", "field", "champions", "status", "summary", "documentation")


@dataclass(frozen=True)
class DataIssue:
    id: str
    source: str
    patch: str
    field: str
    champions: tuple[str, ...] | None  # None means every champion
    status: str
    summary: str
    documentation: str

    def applies_to(self, champion_id: str, patch: str) -> bool:
        if self.status != "open" or self.patch != patch:
            return False
        return self.champions is None or champion_id in self.champions


def _text(record: Mapping[str, Any], key: str, context: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise StatsError(f"{context}: {key!r} must be a non-empty string")
    return value


def parse_issues(document: Any) -> tuple[DataIssue, ...]:
    """Validate the issues document and return its entries."""
    if not isinstance(document, Mapping):
        raise StatsError("data issues: the document must be a JSON object")
    if document.get("schema") != SCHEMA:
        raise StatsError(f"data issues: schema must be {SCHEMA!r}")
    entries = document.get("issues")
    if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes)):
        raise StatsError("data issues: 'issues' must be a list")
    issues: list[DataIssue] = []
    seen: set[str] = set()
    for index, record in enumerate(entries):
        context = f"data issues[{index}]"
        if not isinstance(record, Mapping):
            raise StatsError(f"{context}: must be an object")
        unknown = sorted(set(record) - set(_FIELDS))
        if unknown:
            raise StatsError(f"{context}: unknown keys {unknown}")
        values = {key: _text(record, key, context) for key in _FIELDS if key != "champions"}
        if values["id"] in seen:
            raise StatsError(f"{context}: duplicate id {values['id']!r}")
        seen.add(values["id"])
        if values["source"] not in SOURCES:
            raise StatsError(f"{context}: source must be one of {sorted(SOURCES)}")
        if values["status"] not in STATUSES:
            raise StatsError(f"{context}: status must be one of {sorted(STATUSES)}")
        champions_value = record.get("champions")
        if champions_value == "*":
            champions = None
        elif (
            isinstance(champions_value, Sequence)
            and not isinstance(champions_value, (str, bytes))
            and champions_value
            and all(isinstance(item, str) and item for item in champions_value)
        ):
            champions = tuple(champions_value)
        else:
            raise StatsError(f"{context}: champions must be '*' or a non-empty list of ids")
        issues.append(DataIssue(champions=champions, **values))
    return tuple(issues)


def load_issues(root: Path) -> tuple[DataIssue, ...]:
    path = root / ISSUES_PATH
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise StatsError(f"{ISSUES_PATH.as_posix()} not found") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StatsError(f"{ISSUES_PATH.as_posix()} is not valid UTF-8 JSON: {exc}") from exc
    return parse_issues(document)
