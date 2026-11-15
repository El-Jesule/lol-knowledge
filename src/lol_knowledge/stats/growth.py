"""Per-level growth of champion statistics (lol-knowledge/mechanics/stat-growth.md)."""

from __future__ import annotations

from fractions import Fraction

from ..errors import StatsError

MIN_LEVEL = 1
MAX_LEVEL = 30
LINEAR = Fraction(281, 400)  # 0.7025
QUADRATIC = Fraction(7, 400)  # 0.0175


def check_level(level: object) -> int:
    if not isinstance(level, int) or isinstance(level, bool):
        raise StatsError(f"level must be an integer, got {level!r}")
    if not MIN_LEVEL <= level <= MAX_LEVEL:
        raise StatsError(f"level must be between {MIN_LEVEL} and {MAX_LEVEL}, got {level}")
    return level


def growth_multiplier(level: int) -> Fraction:
    """Return the factor that multiplies a growth statistic at ``level``."""
    ups = check_level(level) - 1
    return ups * (LINEAR + QUADRATIC * ups)
