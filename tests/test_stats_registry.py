"""Registry and label tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from lol_knowledge.errors import StatsError
from lol_knowledge.objects.schema import CANONICAL_STAT_KINDS
from lol_knowledge.stats import STATS, Label, Stacking, stat, weakest

ROOT = Path(__file__).resolve().parents[1]


def test_registry_covers_every_object_model_stat():
    assert set(CANONICAL_STAT_KINDS) <= set(STATS)


def test_resolvable_stats_accept_the_kind_items_declare():
    for stat_id, kinds in CANONICAL_STAT_KINDS.items():
        definition = STATS[stat_id]
        if definition.resolvable:
            assert definition.item_kind in kinds, stat_id


def test_rule_documents_exist():
    for definition in STATS.values():
        if definition.rules:
            assert (ROOT / definition.rules).is_file(), definition.id


def test_pending_stats_explain_why():
    for definition in STATS.values():
        assert definition.resolvable or definition.pending.strip()


def test_penetration_percent_stacks_multiplicatively():
    assert stat("armor_penetration_percent").stacking is Stacking.MULTIPLICATIVE
    assert stat("magic_penetration_percent").stacking is Stacking.MULTIPLICATIVE
    assert stat("health").stacking is Stacking.ADDITIVE


def test_user_requested_stats_are_registered():
    for stat_id in ("omnivamp", "life_steal", "tenacity", "health_regen", "mana_regen"):
        assert stat_id in STATS


def test_unknown_stat():
    with pytest.raises(StatsError, match="unknown stat"):
        stat("charisma")


def test_weakest_label():
    assert weakest([]) is Label.OFFICIAL
    assert weakest([Label.OFFICIAL, Label.DERIVED]) is Label.DERIVED
    assert weakest([Label.DERIVED, Label.PENDING, Label.OFFICIAL]) is Label.PENDING
