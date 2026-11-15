"""Growth formula tests (lol-knowledge/mechanics/stat-growth.md)."""

from __future__ import annotations

from fractions import Fraction as F

import pytest

from lol_knowledge.errors import StatsError
from lol_knowledge.stats import growth_multiplier


def test_level_one_has_no_growth():
    assert growth_multiplier(1) == 0


def test_source_example_level_two():
    # S2: base 685, growth 120, level 2 -> 771.4
    assert 685 + 120 * growth_multiplier(2) == F("771.4")


@pytest.mark.parametrize(
    ("level", "gain"),
    [(2, F("0.72")), (10, F(1)), (18, F("1.28"))],
)
def test_gain_per_level_up_matches_the_sources(level, gain):
    # S2: 72 % of the growth from 1 to 2, 100 % from 9 to 10, 128 % from 17 to 18.
    assert growth_multiplier(level) - growth_multiplier(level - 1) == gain


def test_level_eighteen_totals_seventeen_growths():
    assert growth_multiplier(18) == 17


@pytest.mark.parametrize("level", [0, 31, -1, True, 1.5, "5"])
def test_rejects_invalid_levels(level):
    with pytest.raises(StatsError, match="level"):
        growth_multiplier(level)
