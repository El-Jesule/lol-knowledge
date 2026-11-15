"""Knowledge labels carried by every number, ordered from strongest to weakest."""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum


class Label(StrEnum):
    OFFICIAL = "Oficial"
    DERIVED = "Derivado"
    PENDING = "Pendiente de verificación"


_STRENGTH = {Label.OFFICIAL: 2, Label.DERIVED: 1, Label.PENDING: 0}


def weakest(labels: Iterable[Label]) -> Label:
    """Return the weakest label; an empty input is ``Oficial`` (nothing weakens it)."""
    return min(labels, key=_STRENGTH.__getitem__, default=Label.OFFICIAL)
