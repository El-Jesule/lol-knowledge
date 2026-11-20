"""Champion kit documents (``lol-champion-kit/1``): parsing and validation.

A kit describes, per ability, the damage *cases* (alternatives such as a
centre hit or an edge hit) and their damage *parts*, each a formula with a
damage type, a label and a source. It also lists stats an ability grants
passively. Kits are curated data in ``lol-knowledge/champions/<Id>/kit.json``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from ..damage import DamageType
from ..errors import KitError
from ..formula import ABILITY_OPS, formula_issues
from ..stats.labels import Label
from ..stats.registry import STATS

SCHEMA = "lol-champion-kit/1"
KIT_FILENAME = "kit.json"
SLOTS = ("P", "Q", "W", "E", "R")
CASE_ID = re.compile(r"[a-z][a-z0-9_]*")
COST_RESOURCES = frozenset({"mana", "energy", "health", "none"})


@dataclass(frozen=True)
class CostSpec:
    """Explicit ability or case resource cost declared by a champion kit."""

    resource: str  # "mana", "energy", "health" or "none"
    formula: Mapping[str, Any]
    label: Label
    source: str


@dataclass(frozen=True)
class DamagePartSpec:
    damage_type: DamageType
    formula: Mapping[str, Any]
    label: Label
    source: str
    damage_type_source: str


@dataclass(frozen=True)
class CaseSpec:
    id: str
    name: str
    parts: tuple[DamagePartSpec, ...]
    # A recast of an ability already cast: it starts no cooldown (timeline.md).
    recast: bool = False
    cost: CostSpec | None = None


@dataclass(frozen=True)
class PassiveStatSpec:
    stat: str
    formula: Mapping[str, Any]
    label: Label
    source: str
    condition: str


@dataclass(frozen=True)
class AbilitySpec:
    slot: str
    name: str
    max_rank: int
    cases: tuple[CaseSpec, ...]
    passive_stats: tuple[PassiveStatSpec, ...]
    not_modelled: tuple[str, ...]
    # Seconds after the first cast within which a recast case is allowed.
    recast_window: Fraction | None = None
    # Recasts allowed per cast (Ahri's R: 2), and the least time between two casts.
    max_recasts: int = 1
    recast_interval: Fraction | None = None
    cost: CostSpec | None = None

    def case(self, case_id: str) -> CaseSpec:
        for case in self.cases:
            if case.id == case_id:
                return case
        known = ", ".join(case.id for case in self.cases) or "none"
        raise KitError(f"{self.slot}: unknown case {case_id!r} (known: {known})")


@dataclass(frozen=True)
class Kit:
    champion: str
    label: Label
    game_version: str
    content_version: str
    abilities: Mapping[str, AbilitySpec]

    def ability(self, slot: str) -> AbilitySpec:
        try:
            return self.abilities[slot.upper()]
        except KeyError as exc:
            raise KitError(f"{self.champion} has no kit entry for {slot!r}") from exc


def _text(record: Mapping[str, Any], key: str, context: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise KitError(f"{context}: {key!r} must be a non-empty string")
    return value


def _label(record: Mapping[str, Any], context: str) -> Label:
    try:
        return Label(record.get("label"))
    except ValueError as exc:
        raise KitError(f"{context}: label must be one of {[item.value for item in Label]}") from exc


def _rank_lists(formula: Any) -> list[int]:
    """Lengths of every ``by_rank`` list in a formula."""
    if isinstance(formula, Mapping):
        found = [len(formula["values"])] if formula.get("op") == "by_rank" else []
        for value in formula.values():
            found.extend(_rank_lists(value))
        return found
    if isinstance(formula, Sequence) and not isinstance(formula, (str, bytes)):
        return [length for item in formula for length in _rank_lists(item)]
    return []


def _formula(record: Mapping[str, Any], max_rank: int, context: str) -> Mapping[str, Any]:
    formula = record.get("formula")
    issues = formula_issues(formula, ops=ABILITY_OPS)
    if issues:
        raise KitError(f"{context}: invalid formula: {'; '.join(issues)}")
    for length in _rank_lists(formula):
        if length != max_rank:
            raise KitError(f"{context}: by_rank has {length} values, the ability has {max_rank}")
    return formula


def _list(record: Mapping[str, Any], key: str, context: str) -> Sequence[Any]:
    value = record.get(key, [])
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise KitError(f"{context}: {key!r} must be a list")
    return value


def _cost(record: Mapping[str, Any], max_rank: int, context: str) -> CostSpec | None:
    raw = record.get("cost")
    if raw is None:
        return None
    cost_context = f"{context}.cost"
    if not isinstance(raw, Mapping):
        raise KitError(f"{cost_context}: must be an object")
    resource = _text(raw, "resource", cost_context)
    if resource not in COST_RESOURCES:
        raise KitError(f"{cost_context}: resource must be one of {sorted(COST_RESOURCES)}")
    return CostSpec(
        resource,
        _formula(raw, max_rank, cost_context),
        _label(raw, cost_context),
        _text(raw, "source", cost_context),
    )


def _ability(slot: str, record: Any) -> AbilitySpec:
    context = f"kit.{slot}"
    if not isinstance(record, Mapping):
        raise KitError(f"{context}: must be an object")
    max_rank = record.get("max_rank")
    if isinstance(max_rank, bool) or not isinstance(max_rank, int) or max_rank < 1:
        raise KitError(f"{context}: max_rank must be a positive integer")
    cases: list[CaseSpec] = []
    for index, case in enumerate(_list(record, "cases", context)):
        case_context = f"{context}.cases[{index}]"
        if not isinstance(case, Mapping):
            raise KitError(f"{case_context}: must be an object")
        case_id = _text(case, "id", case_context)
        if CASE_ID.fullmatch(case_id) is None:
            raise KitError(f"{case_context}: id must be lowercase snake_case")
        if any(item.id == case_id for item in cases):
            raise KitError(f"{case_context}: duplicate case id {case_id!r}")
        parts = []
        raw_parts = _list(case, "parts", case_context)
        if not raw_parts:
            raise KitError(f"{case_context}: parts must not be empty")
        for part_index, part in enumerate(raw_parts):
            part_context = f"{case_context}.parts[{part_index}]"
            if not isinstance(part, Mapping):
                raise KitError(f"{part_context}: must be an object")
            try:
                damage_type = DamageType(part.get("damage_type"))
            except ValueError as exc:
                raise KitError(f"{part_context}: unknown damage_type") from exc
            parts.append(
                DamagePartSpec(
                    damage_type,
                    _formula(part, max_rank, part_context),
                    _label(part, part_context),
                    _text(part, "source", part_context),
                    _text(part, "damage_type_source", part_context),
                )
            )
        recast = case.get("recast", False)
        if not isinstance(recast, bool):
            raise KitError(f"{case_context}: recast must be true or false")
        case_cost = _cost(case, max_rank, case_context)
        cases.append(
            CaseSpec(case_id, _text(case, "name", case_context), tuple(parts), recast, case_cost)
        )
    passive_stats = []
    for index, entry in enumerate(_list(record, "passive_stats", context)):
        entry_context = f"{context}.passive_stats[{index}]"
        if not isinstance(entry, Mapping):
            raise KitError(f"{entry_context}: must be an object")
        stat_id = _text(entry, "stat", entry_context)
        definition = STATS.get(stat_id)
        if definition is None or not definition.resolvable:
            raise KitError(f"{entry_context}: {stat_id!r} is not a resolvable stat")
        passive_stats.append(
            PassiveStatSpec(
                stat_id,
                _formula(entry, max_rank, entry_context),
                _label(entry, entry_context),
                _text(entry, "source", entry_context),
                _text(entry, "condition", entry_context),
            )
        )
    not_modelled = _list(record, "not_modelled", context)
    if not all(isinstance(item, str) and item.strip() for item in not_modelled):
        raise KitError(f"{context}: not_modelled must list non-empty strings")
    window = record.get("recast_window_seconds")
    if window is not None and (
        isinstance(window, bool) or not isinstance(window, (int, float)) or window <= 0
    ):
        raise KitError(f"{context}: recast_window_seconds must be a positive number")
    if window is not None and not any(case.recast for case in cases):
        raise KitError(f"{context}: recast_window_seconds needs a recast case")
    max_recasts = record.get("max_recasts", 1)
    if isinstance(max_recasts, bool) or not isinstance(max_recasts, int) or max_recasts < 1:
        raise KitError(f"{context}: max_recasts must be a positive integer")
    interval = record.get("recast_interval_seconds")
    if interval is not None and (
        isinstance(interval, bool) or not isinstance(interval, (int, float)) or interval <= 0
    ):
        raise KitError(f"{context}: recast_interval_seconds must be a positive number")
    recasts = "max_recasts" in record or interval is not None
    if recasts and not any(case.recast for case in cases):
        raise KitError(f"{context}: max_recasts and recast_interval_seconds need a recast case")
    return AbilitySpec(
        slot,
        _text(record, "name", context),
        max_rank,
        tuple(cases),
        tuple(passive_stats),
        tuple(not_modelled),
        None if window is None else Fraction(str(window)),
        max_recasts,
        None if interval is None else Fraction(str(interval)),
        _cost(record, max_rank, context),
    )


def parse_kit(document: Any) -> Kit:
    """Validate a kit document and return it as typed values."""
    if not isinstance(document, Mapping):
        raise KitError("kit: the document must be a JSON object")
    if document.get("schema") != SCHEMA:
        raise KitError(f"kit: schema must be {SCHEMA!r}")
    champion = _text(document, "champion", "kit")
    label = _label(document, "kit")
    abilities_raw = document.get("abilities")
    if not isinstance(abilities_raw, Mapping) or not abilities_raw:
        raise KitError("kit: 'abilities' must be a non-empty object")
    unknown = sorted(set(abilities_raw) - set(SLOTS))
    if unknown:
        raise KitError(f"kit: unknown ability slots {unknown}")
    abilities = {
        slot: _ability(slot, abilities_raw[slot]) for slot in SLOTS if slot in abilities_raw
    }
    return Kit(
        champion,
        label,
        _text(document, "game_version", "kit"),
        _text(document, "content_version", "kit"),
        abilities,
    )


def kit_path(root: Path, champion_id: str) -> Path:
    return root / "lol-knowledge" / "champions" / champion_id / KIT_FILENAME


def load_kit(root: Path, champion_id: str) -> Kit | None:
    """Load a champion's kit, or ``None`` when the champion has none.

    ``champion_id`` must already be a validated snapshot id.
    """
    path = kit_path(root, champion_id)
    if not path.is_file():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KitError(f"{path.as_posix()} is not valid UTF-8 JSON: {exc}") from exc
    kit = parse_kit(document)
    if kit.champion != champion_id:
        raise KitError(f"{path.as_posix()} is for {kit.champion!r}, not {champion_id!r}")
    return kit
