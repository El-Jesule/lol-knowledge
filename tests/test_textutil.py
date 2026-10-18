"""Tests for tooltip placeholder substitution."""

from lol_knowledge.textutil import substitute_placeholders


def test_replaces_known_placeholder() -> None:
    assert substitute_placeholders("Daño: {{ e1 }}", {"e1": "120"}) == "Daño: 120"


def test_accepts_spaces_inside_braces() -> None:
    assert substitute_placeholders("{{ e2 }}", {"e2": "7"}) == "7"


def test_replaces_every_occurrence() -> None:
    assert substitute_placeholders("{{ e1 }} / {{ e1 }}", {"e1": "5"}) == "5 / 5"


def test_keeps_unknown_placeholder_visible() -> None:
    assert substitute_placeholders("{{ e1 }} y {{ totaldamage }}", {"e1": "9"}) == (
        "9 y {{ totaldamage }}"
    )


def test_returns_text_without_placeholders_unchanged() -> None:
    assert substitute_placeholders("Sin marcadores", {}) == "Sin marcadores"
