"""Per-field provenance for values extracted from external game data."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any


class Status(StrEnum):
    """Verification state of a single extracted value.

    Precedence (higher wins when combining): conflict > unverified > verified >
    corroborated > inferred > derived > source_explicit.
    """

    SOURCE_EXPLICIT = "source_explicit"
    DERIVED = "derived"
    INFERRED = "inferred"
    CORROBORATED = "corroborated"
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    CONFLICT = "conflict"


_PRECEDENCE = {
    Status.SOURCE_EXPLICIT: 0,
    Status.DERIVED: 1,
    Status.INFERRED: 2,
    Status.CORROBORATED: 3,
    Status.VERIFIED: 4,
    Status.UNVERIFIED: 5,
    Status.CONFLICT: 6,
}


def combine_statuses(*statuses: Status) -> Status:
    """Return the most severe status."""
    if not statuses:
        return Status.UNVERIFIED
    return max(statuses, key=lambda status: _PRECEDENCE[status])


@dataclass(frozen=True)
class Provenance:
    """One value together with everything needed to audit it."""

    champion: str
    ability: str
    parameter: str
    ranks: tuple[float, ...]
    source: str
    url: str
    source_version: str
    source_path: str
    source_sha256: str
    extraction: str
    transformation: str
    status: Status
    cross_sources: tuple[str, ...] = ()
    notes: str = ""

    def with_status(self, status: Status, *, note: str | None = None) -> Provenance:
        notes = self.notes if note is None else f"{self.notes} {note}".strip()
        return replace(self, status=status, notes=notes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "champion": self.champion,
            "ability": self.ability,
            "parameter": self.parameter,
            "ranks": list(self.ranks),
            "source": self.source,
            "url": self.url,
            "source_version": self.source_version,
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "extraction": self.extraction,
            "transformation": self.transformation,
            "status": str(self.status),
            "cross_sources": list(self.cross_sources),
            "notes": self.notes,
        }
