"""Small JSON-ready model types used by the extractor."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Diagnostic:
    """One extraction or validation problem."""

    severity: str
    code: str
    path: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "path": self.path,
            "message": self.message,
            "data": self.data,
        }


@dataclass
class DataValue:
    """One named spell data value with its raw and ranked forms."""

    name: str
    source_path: str
    raw_values: list[float] | None
    ranks: list[float] | None
    level_count: int | None
    mode: str = "base"
    status: str = "source_explicit"
    notes: str = ""
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "source_path": self.source_path,
            "raw_values": self.raw_values,
            "ranks": self.ranks,
            "level_count": self.level_count,
            "mode": self.mode,
            "status": self.status,
            "notes": self.notes,
            "provenance": self.provenance,
        }


@dataclass
class Calculation:
    """One named calculation tree."""

    name: str
    tree: dict[str, Any]
    source_path: str
    status: str = "source_explicit"
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "tree": self.tree,
            "source_path": self.source_path,
            "status": self.status,
            "notes": self.notes,
        }


@dataclass
class Ability:
    """One champion spell (passive, Q, W, E or R)."""

    ability_id: str
    slot: str
    path: str
    name: str
    root_spell: str
    level_count: int | None
    source_level_count: str
    data_values: list[DataValue] = field(default_factory=list)
    calculations: list[Calculation] = field(default_factory=list)
    cooldown: dict[str, Any] | None = None
    mana: dict[str, Any] | None = None
    cast_range: dict[str, Any] | None = None
    tooltip: dict[str, Any] = field(default_factory=dict)
    children: list[str] = field(default_factory=list)
    child_spells: list[dict[str, Any]] = field(default_factory=list)
    bot_data: dict[str, Any] | None = None
    diagnostics: list[Diagnostic] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.ability_id,
            "slot": self.slot,
            "path": self.path,
            "name": self.name,
            "root_spell": self.root_spell,
            "level_count": self.level_count,
            "level_count_source": self.source_level_count,
            "data_values": [item.to_dict() for item in self.data_values],
            "calculations": [item.to_dict() for item in self.calculations],
            "cooldown": self.cooldown,
            "mana": self.mana,
            "cast_range": self.cast_range,
            "tooltip": self.tooltip,
            "children": self.children,
            "child_spells": self.child_spells,
            "bot_data": self.bot_data,
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }


@dataclass
class ChampionExtract:
    """Full extraction result for one champion document."""

    schema_version: int
    game_version: str
    content_version: str
    source: dict[str, Any]
    champion: dict[str, Any]
    abilities: list[Ability]
    unresolved: list[dict[str, Any]]
    diagnostics: list[Diagnostic]
    registry: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": "lol-bin-champion-extract",
            "game_version": self.game_version,
            "content_version": self.content_version,
            "source": self.source,
            "champion": self.champion,
            "abilities": [item.to_dict() for item in self.abilities],
            "unresolved": self.unresolved,
            "diagnostics": [item.to_dict() for item in self.diagnostics],
            "registry": self.registry,
        }
