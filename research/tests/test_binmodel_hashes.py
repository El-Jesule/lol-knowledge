"""Hash and normalization tests for the bin model."""

from __future__ import annotations

from binmodel.hashes import fnv1a32, normalize_field, normalize_type


def test_fnv1a32_matches_published_type_hashes():
    assert f"{fnv1a32('ByCharLevelBreakpointsCalculationPart'):08x}" == "5cf69ece"
    assert f"{fnv1a32('NamedDataValueCalculationPart'):08x}" != ""
    assert f"{fnv1a32('SpellObject'):08x}" == "5e7e5a06"
    assert f"{fnv1a32('SpellDataValue'):08x}" == "005008a6"


def test_fnv1a32_matches_the_provisional_interpolation_name():
    assert f"{fnv1a32('ByCharLevelNamedDataValuesInterpolationCalculationPart'):08x}" == "ee18a47b"


def test_normalize_type_accepts_braces_prefix_and_case():
    assert normalize_type("{ee18a47b}") == "0xee18a47b"
    assert normalize_type("0xEE18A47B") == "0xee18a47b"
    assert normalize_type("ee18a47b") == "0xee18a47b"
    assert normalize_type("GameCalculation") == "GameCalculation"
    assert normalize_type(None) is None


def test_normalize_field_strips_prefix_and_braces():
    assert normalize_field("0x91D404A5") == "91d404a5"
    assert normalize_field("{0a3e0478}") == "0a3e0478"
    assert normalize_field("mStat") == "mstat"
