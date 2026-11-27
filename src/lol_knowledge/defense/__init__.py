"""Reverse survival simulation: incoming damage, flat reduction and defensive triggers."""

from __future__ import annotations

from .models import (
    DEFENSE_RULES,
    TENACITY_MIN_DURATION,
    DefenseOutcome,
    DefenseSession,
    DefenseState,
    DefenseStep,
    IncomingHit,
    hits_from_rotation,
    parse_incoming,
)
from .session import evaluate_defense, open_defense_session

__all__ = [
    "DEFENSE_RULES",
    "DefenseOutcome",
    "DefenseSession",
    "DefenseState",
    "DefenseStep",
    "IncomingHit",
    "TENACITY_MIN_DURATION",
    "evaluate_defense",
    "hits_from_rotation",
    "open_defense_session",
    "parse_incoming",
]
