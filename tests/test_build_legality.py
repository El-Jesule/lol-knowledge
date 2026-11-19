"""Build legality from the client's item groups (lol-knowledge/mechanics/build-legality.md)."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from lol_knowledge.cli import main
from lol_knowledge.errors import StatsError
from lol_knowledge.objects.legality import (
    INVENTORY_SLOTS,
    check_build,
    item_groups_problems,
    load_item_groups,
    parse_item_groups,
)
from lol_knowledge.stats import Label

ROOT = Path(__file__).resolve().parents[1]


def group(entry=None, group_id="G", max_ownable=None, slot=None):
    return {
        "entry": entry,
        "group_id": group_id,
        "max_ownable": max_ownable,
        "inventory_slot_min": slot,
        "inventory_slot_max": slot,
    }


def item(*groups, max_stack=1, champion=None):
    return {"groups": list(groups), "max_stack": max_stack, "required_champion": champion}


def document(**changes):
    base = {
        "schema": "lol-derived-item-groups/1",
        "label": "Derivado",
        "content_version": "16.23.1+x",
        "game_version": "16.23",
        "retrieved_at": "2026-11-19",
        "source": "test",
        "method": "test",
        "bin_sha256": "0" * 64,
        "groups": {
            "00000001": group("Items/ItemGroups/Boots", "Boots", 1),
            "00000002": group(None, "3031", 1),
            "00000003": group("Items/ItemGroups/Potion", "Potion", 1),
            "00000004": group("Items/ItemGroups/Trinket", "Trinket", slot=6),
            "00000005": group("Items/ItemGroups/Default", "Default"),
        },
        "items": {
            "1001": item("00000001", "00000005"),
            "3006": item("00000001", "00000005"),
            "3031": item("00000002", "00000005"),
            "2003": item("00000003", max_stack=5),
            "2031": item("00000003"),
            "1036": item("00000005"),
            "3133": item("00000005", max_stack=None),
            "3340": item("00000004"),
            "3364": item("00000004"),
            "3599": item("00000005", champion="Kalista"),
        },
        "failures": {},
    }
    base.update(changes)
    return base


DATA = parse_item_groups(document())


def check(*items, champion="Ahri", patch="16.23.1"):
    return check_build(list(items), DATA, patch=patch, champion=champion)


def rules(report):
    return [violation.rule for violation in report.violations]


def test_a_full_legal_build_has_no_violations_and_is_derived():
    report = check("1001", "3031", "1036", "1036", "1036", "1036", "3340")
    assert report.legal and report.violations == () and report.notes == ()
    assert report.label is Label.DERIVED
    assert "build-legality.md" in report.source


def test_a_group_caps_how_many_of_its_items_are_held():
    report = check("1001", "3006")
    assert rules(report) == ["group_limit"]
    assert "Items/ItemGroups/Boots allows 1 at once; the build holds 2" in (
        report.violations[0].message
    )
    assert rules(check("3031", "3031")) == ["group_limit"]


def test_stackable_items_count_one_stack_per_group_and_per_slot():
    assert check("2003", "2003", "2003", "2003", "2003").legal
    assert rules(check(*["2003"] * 6)) == ["group_limit"]
    assert rules(check("2003", "2031")) == ["group_limit"]


def test_the_inventory_has_six_ordinary_slots():
    assert INVENTORY_SLOTS == 6
    assert check(*["1036"] * 6).legal
    report = check(*["1036"] * 7)
    assert rules(report) == ["slots"]
    assert "need 7 slots; the inventory has 6" in report.violations[0].message


def test_trinkets_share_their_own_slot_and_do_not_use_an_ordinary_one():
    assert check(*["1036"] * 6, "3340").legal
    report = check("3340", "3364")
    assert rules(report) == ["slots"]
    assert "slot 6 holds one item" in report.violations[0].message


def test_an_unknown_max_stack_counts_each_copy_and_says_so():
    report = check("3133", "3133")
    assert report.legal
    assert report.notes == (
        "3133: the client gives no maxStack; each copy is counted in its own slot",
    )
    assert rules(check(*["3133"] * 7)) == ["slots"]


def test_champion_items_are_only_for_their_champion():
    assert rules(check("3599", champion="Ahri")) == ["champion"]
    assert check("3599", champion="kalista").legal
    report = check("3599", champion=None)
    assert report.legal and report.notes == ("3599 is only for Kalista; the holder is not known",)


def test_items_without_group_data_are_a_violation():
    report = check("9999", "1001")
    assert rules(report) == ["no_group_data"]
    assert report.violations[0].items == ("9999",)


def test_data_of_another_patch_weakens_the_label():
    report = check("1001", patch="16.24.1")
    assert report.legal and report.label is Label.PENDING
    assert report.notes == ("item groups are from client 16.23, the snapshot is 16.24.1",)


def test_the_document_is_validated():
    assert item_groups_problems(document(), patch="16.23.1", item_ids=set(DATA.items)) == []
    broken = document()
    broken["items"]["1001"]["groups"] = ["0000000f"]
    assert "items.1001.groups links to unknown groups ['0000000f']" in item_groups_problems(broken)
    stale = item_groups_problems(document(), patch="16.24.1")
    assert stale == ["client 16.23 data for snapshot 16.24.1; regenerate it with "
                     "python -m binmodel.item_groups (research/README.md)"]  # fmt: skip
    coverage = item_groups_problems(document(), item_ids={"1001", "4444"})
    assert any("without group data: ['4444']" in problem for problem in coverage)
    assert any("not in the catalog" in problem for problem in coverage)
    odd = copy.deepcopy(document())
    odd["groups"]["00000001"]["max_ownable"] = -1
    odd["items"]["2003"]["max_stack"] = 0
    odd["schema"] = "other"
    problems = item_groups_problems(odd)
    assert "schema must be 'lol-derived-item-groups/1'" in problems
    assert "groups.00000001.max_ownable must be a non-negative integer or null" in problems
    assert "items.2003.max_stack must be a positive integer or null" in problems
    with pytest.raises(StatsError, match="schema must be"):
        parse_item_groups(odd)


def test_unused_groups_are_reported():
    extra = document()
    extra["groups"]["0000000a"] = group(None, "X", 1)
    assert item_groups_problems(extra) == ["groups no item links to: ['0000000a']"]


# Real client data (lol-knowledge/derived/item-groups.json).
REAL = load_item_groups(ROOT)


@pytest.mark.parametrize(
    ("items", "group"),
    [
        (("3006", "3047"), "Items/ItemGroups/Boots"),
        (("3036", "6694"), "Items/ItemGroups/LastWhisper"),
        (("3053", "6673"), "Items/ItemGroups/LifelineItems"),
        (("3074", "3748"), "Items/ItemGroups/CleaveItems"),
        (("3003", "3004"), "Items/ItemGroups/TearItems"),
        (("3135", "4630"), "Items/ItemGroups/VoidPen"),
        (("3057", "3078"), "{57352a0f}"),
        (("3031", "3031"), "3031"),
    ],
)
def test_real_groups_forbid_known_pairs(items, group):
    report = check_build(items, REAL, patch="16.23.1", champion="Zaahen")
    assert any(f"group {group} allows 1" in violation.message for violation in report.violations)


def test_a_real_six_item_build_with_boots_and_a_trinket_is_legal():
    build = ["3006", "3153", "3031", "3036", "3072", "3026", "3340"]
    report = check_build(build, REAL, patch="16.23.1", champion="Zaahen")
    assert report.legal and report.label is Label.DERIVED


def run(capsys, command, *args):
    code = main([command, "--root", str(ROOT), *args])
    return code, capsys.readouterr()


def test_stats_refuses_an_illegal_build_unless_allowed(capsys):
    args = ("--champion", "Ahri", "--level", "11", "--item", "3006", "--item", "3047")
    code, captured = run(capsys, "stats", *args)
    assert code == 2 and captured.out == ""
    assert captured.err.startswith("error: champion build is not legal [Derivado]: ")
    assert "--allow-illegal-build" in captured.err
    code, captured = run(capsys, "stats", *args, "--allow-illegal-build")
    assert code == 0
    assert captured.err.startswith("warning: champion build is not legal [Derivado]")
    assert "items: 3006 Grebas de berserker, 3047 Botas blindadas" in captured.out


def test_rotation_checks_the_attacker_and_the_target(capsys):
    base = ("--champion", "Zaahen", "--level", "16", "--learned", "Q=5",
            "--attacker-range", "melee", "--steps", "attack",
            "--target-champion", "Ahri", "--target-level", "16")  # fmt: skip
    code, captured = run(capsys, "rotation", *base, "--item", "3036", "--item", "6694")
    assert code == 2 and "attacker build is not legal" in captured.err
    code, captured = run(
        capsys, "rotation", *base, "--target-item", "3089", "--target-item", "3089"
    )
    assert code == 2 and "target build is not legal" in captured.err
    code, captured = run(capsys, "rotation", *base, "--item", "3153", "--target-item", "3089")
    assert code == 0 and captured.err == ""


def test_ability_refuses_an_illegal_attacker_build(capsys):
    code, captured = run(
        capsys, "ability", "--champion", "Zaahen", "--level", "16", "--ability", "Q", "--rank", "5",
        "--item", *("1036",), "--item", "1036", "--item", "1036", "--item", "1036",
        "--item", "1036", "--item", "1036", "--item", "1036",
        "--target-armor", "100", "--target-mr", "50",
    )  # fmt: skip
    assert code == 2 and "need 7 slots; the inventory has 6" in captured.err
