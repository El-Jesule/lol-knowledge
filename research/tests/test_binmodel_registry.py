"""Registry resolution tests."""

from __future__ import annotations

from binmodel.registry import Registry


def test_known_classes_resolve():
    registry = Registry()
    game_calculation = registry.class_for("GameCalculation")
    assert game_calculation is not None
    assert game_calculation.resolved
    assert game_calculation.base == "IGameCalculation"


def test_hashed_classes_keep_a_provisional_name():
    registry = Registry()
    entry = registry.class_for("{ee18a47b}")
    assert entry is not None
    assert not entry.resolved
    assert entry.type_hash == "0xee18a47b"
    assert entry.provisional_name == "ByCharLevelNamedDataValuesInterpolationCalculationPart"
    assert registry.type_name("{ee18a47b}") == entry.provisional_name


def test_hashed_fields_resolve_to_provisional_names():
    registry = Registry()
    assert registry.field_name("0x4ce08984", "0x91d404a5") == "Level1DataValue"
    assert registry.field_name("{0x4ce08984}", "9823b29a") == "Breakpoints"
    assert registry.field_name("0x0a0eddc9", "0a3e0478") == "UnresolvedScalar0a3e0478"


def test_field_hash_dictionary_is_used_as_a_fallback():
    registry = Registry()
    assert registry.field_name(None, "3de6ce2d") == "CalculationKey"
    assert registry.field_name(None, "ffffffff").startswith("0x")
