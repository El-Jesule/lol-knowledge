"""Knowledge labels carried by every number, ordered from strongest to weakest."""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum


class Label(StrEnum):
    OFFICIAL = "Oficial"
    DERIVED = "Derivado"
    PENDING = "Pendiente de verificación"


# Label of a catalog effect by its evidence. Turning a description into a
# formula is an interpretation, so even ``official`` evidence is derived.
EVIDENCE_LABEL = {
    "official": Label.DERIVED,
    "corroborated": Label.DERIVED,
    "secondary": Label.PENDING,
    "unverified": Label.PENDING,
}

_STRENGTH = {Label.OFFICIAL: 2, Label.DERIVED: 1, Label.PENDING: 0}


def weakest(labels: Iterable[Label]) -> Label:
    """Return the weakest label; an empty input is ``Oficial`` (nothing weakens it)."""
    return min(labels, key=_STRENGTH.__getitem__, default=Label.OFFICIAL)
