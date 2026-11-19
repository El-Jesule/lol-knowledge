"""Runes from the client: data, page legality and stat shards (mechanics/runes.md)."""

from __future__ import annotations

import copy
import json
from fractions import Fraction as F
from pathlib import Path

import pytest

from lol_knowledge.cli import main
from lol_knowledge.errors import StatsError
from lol_knowledge.runes import (
    RUNES_PATH,
    adaptive_stat,
    check_page,
    load_runes,
    parse_runes,
    runes_problems,
    shard_contributions,
)
from lol_knowledge.stats import Label

ROOT = Path(__file__).resolve().parents[1]
DOCUMENT = json.loads((ROOT / RUNES_PATH).read_text(encoding="utf-8"))
OFFICIAL = json.loads((ROOT / "data" / "current" / "runes.json").read_text(encoding="utf-8"))
DATA = load_runes(ROOT)
PATCH = json.loads((ROOT / "data/current/manifest.json").read_text(encoding="utf-8"))["patch"]
# Electrocute, Sudden Impact, Sixth Sense, Ultimate Hunter | Manaflow Band, Transcendence
PAGE = [8112, 8143, 8137, 8106, 8226, 8210]
SHARDS = [5008, 5008, 5001]


def test_client_trees_match_data_dragon():
    assert runes_problems(DOCUMENT, patch=PATCH, official=OFFICIAL) == []
    assert sorted(DATA.trees) == [8000, 8100, 8200, 8300, 8400]
    assert DATA.trees[8100].rows[0] == (8112, 8128, 9923)
    assert DATA.shard_rows == ((5008, 5005, 5007), (5008, 5010, 5001), (5011, 5013, 5001))


def test_a_changed_tree_is_reported():
    changed = copy.deepcopy(DOCUMENT)
    changed["styles"]["8100"]["slots"][1]["perks"].reverse()
    problems = runes_problems(changed, official=OFFICIAL)
    assert problems == [
        "trees, rows or rune ids differ from Data Dragon's runes.json; regenerate it with "
        "python -m binmodel.perks (research/README.md)"
    ]


def test_the_document_shape_is_checked():
    broken = copy.deepcopy(DOCUMENT)
    broken["schema"] = "x"
    broken["shard_slots"] = broken["shard_slots"][:2]
    broken["styles"]["8000"]["slots"][0]["type"] = 3
    del broken["perks"]["8005"]
    problems = runes_problems(broken, patch="16.24.1")
    assert "schema must be 'lol-derived-runes/1'" in problems
    assert "shard_slots must be three rows of rune ids" in problems
    assert "styles.8000.slots[0].type must be 0" in problems
    assert "styles.8000.slots[0]: runes without data ['8005']" in problems
    assert any(problem.startswith("client 16.23 data for snapshot 16.24.1") for problem in problems)
    with pytest.raises(StatsError, match="schema must be"):
        parse_runes(broken)


def test_a_complete_page_is_legal():
    report = check_page(PAGE, SHARDS, DATA, patch=PATCH)
    assert report.legal and report.label is Label.DERIVED
    assert (report.page.primary, report.page.secondary) == (8100, 8200)


@pytest.mark.parametrize(
    ("runes", "shards", "message"),
    [
        ([8112, 8128, 8137, 8106, 8226, 8210], SHARDS, "exactly one keystone"),
        ([8112, 8126, 8143, 8106, 8226, 8210], SHARDS, "needs one rune from each row"),
        ([8112, 8143, 8137, 8106, 8226, 8275], SHARDS, "from different rows"),
        ([8112, 8143, 8137, 8106, 8226, 8009], SHARDS, "from one other tree"),
        ([8112, 8143, 8137, 8106, 8226], SHARDS, "a page has 6 tree runes"),
        ([8112, 8143, 8137, 8106, 8226, 8226], SHARDS, "8226 is repeated"),
        ([8112, 8143, 8137, 8106, 8226, 5008], SHARDS, "5008 is not a tree rune"),
        (PAGE, [5001, 5008, 5001], "shard 5001 is not in shard row 1"),
        (PAGE, [5008, 5008], "a page has 3 shards"),
    ],
)
def test_illegal_pages(runes, shards, message):
    report = check_page(runes, shards, DATA, patch=PATCH)
    assert not report.legal
    assert any(message in violation for violation in report.violations), report.violations


def test_a_tree_that_does_not_allow_the_secondary_is_illegal():
    data = copy.deepcopy(DOCUMENT)
    data["styles"]["8100"]["allowed_secondary"] = [8300]
    report = check_page(PAGE, SHARDS, parse_runes(data), patch=PATCH)
    assert "Sorcery cannot be the secondary tree of Domination" in report.violations


def test_shard_values_come_from_the_client():
    flats, percents = shard_contributions([5005, 5010, 5013], DATA, level=1, patch=PATCH)
    assert [(stat, part.value, part.label) for stat, part in flats] == [
        ("attack_speed_bonus", F(1, 10), Label.DERIVED),
        ("tenacity", F(15, 100), Label.DERIVED),
    ]
    assert flats[1][1].tenacity_group == "A"
    assert [(stat, part.value) for stat, part in percents] == [("move_speed", F(25, 1000))]
    flats, _ = shard_contributions([5007, 5001, 5011], DATA, level=18, patch=PATCH)
    assert [(stat, part.value) for stat, part in flats] == [
        ("ability_haste", 8),
        ("health", 180),
        ("health", 65),
    ]
    # The health curve between levels 1 and 18 is not published: linear, pending.
    ((_, scaling),) = shard_contributions([5001], DATA, level=10, patch=PATCH)[0]
    assert scaling.value == 100 and scaling.label is Label.PENDING


def test_adaptive_shards_need_and_follow_the_adaptive_stat():
    with pytest.raises(StatsError, match="need the adaptive stat"):
        shard_contributions([5008], DATA, level=1, patch=PATCH)
    flats, _ = shard_contributions([5008], DATA, level=1, patch=PATCH, adaptive="attack_damage")
    assert flats[0][0] == "attack_damage" and flats[0][1].value == F(27, 5)
    flats, _ = shard_contributions([5008], DATA, level=1, patch=PATCH, adaptive="ability_power")
    assert flats[0][1].value == 9


def test_adaptive_stat_takes_the_higher_bonus_and_the_champion_on_a_tie():
    assert adaptive_stat(F(10), F(0), None)[:2] == ("attack_damage", Label.DERIVED)
    assert adaptive_stat(F(0), F(1), None)[:2] == ("ability_power", Label.DERIVED)
    assert adaptive_stat(F(0), F(0), F(1))[:2] == ("ability_power", Label.PENDING)
    stat, label, note = adaptive_stat(F(0), F(0), None)
    assert (stat, label) == ("attack_damage", Label.PENDING)
    assert "adaptiveforceapweight (absent)" in note


def run(capsys, *args):
    code = main([*args[:1], "--root", str(ROOT), *args[1:]])
    return code, capsys.readouterr()


def page_args(runes=PAGE, shards=SHARDS):
    return [*(arg for rune in runes for arg in ("--rune", str(rune))),
            *(arg for shard in shards for arg in ("--shard", str(shard)))]  # fmt: skip


def test_stats_with_a_page_applies_the_shards_and_lists_the_runes(capsys):
    code, captured = run(
        capsys,
        "stats",
        "--champion",
        "Ahri",
        "--level",
        "11",
        "--item",
        "3089",
        *page_args(),
        "--json",
    )
    assert code == 0, captured.err
    report = json.loads(captured.out)
    power = report["stats"]["ability_power"]
    # (130 Rabadon + 2 × 9 adaptive) × 1.3: the shards are amplified with the items.
    assert power["exact"] == "962/5"
    sources = [part["source"] for part in power["contributions"]]
    assert sum(source.startswith("rune:5008 Adaptive") for source in sources) == 2
    assert report["stats"]["health"]["total"] == pytest.approx(1502.6 + 110)
    assert "rune 8112 Electrocutar: effects not modelled (RUN-04)" in report["notes"]


def test_adaptive_follows_the_items_and_ahri_takes_ap_on_a_tie(capsys):
    _, captured = run(capsys, "stats", "--champion", "Ahri", "--level", "1", *page_args(), "--json")
    stats = json.loads(captured.out)["stats"]
    assert stats["ability_power"]["total"] == 18
    assert stats["ability_power"]["label"] == "Pendiente de verificación"
    _, captured = run(
        capsys, "stats", "--champion", "Zaahen", "--level", "1", "--item", "1036",
        *page_args(), "--json",
    )  # fmt: skip
    stats = json.loads(captured.out)["stats"]
    assert stats["attack_damage"]["total"] == pytest.approx(63 + 10 + 2 * 5.4)


def test_an_illegal_page_is_refused_unless_allowed(capsys):
    args = ["stats", "--champion", "Ahri", "--level", "5", *page_args(shards=[5001, 5008, 5001])]
    code, captured = run(capsys, *args)
    assert code == 2 and "rune page is not legal" in captured.err
    code, captured = run(capsys, *args, "--allow-illegal-build")
    assert code == 0 and captured.err.startswith("warning: rune page is not legal")


def test_tree_runes_weaken_ability_and_rotation_damage(capsys):
    target = ["--target-armor", "60", "--target-mr", "40", "--target-max-health", "2000"]
    base = ["--champion", "Ahri", "--level", "11", "--learned", "Q=5", *target]
    code, captured = run(capsys, "ability", *base, "--ability", "Q", "--rank", "5", "--case", "out",
                         "--json")  # fmt: skip
    assert code == 0, captured.err
    assert json.loads(captured.out)["weakest_input_label"] == "Derivado"
    code, captured = run(capsys, "ability", *base, "--ability", "Q", "--rank", "5", "--case", "out",
                         *page_args(), "--json")  # fmt: skip
    assert code == 0, captured.err
    assert json.loads(captured.out)["weakest_input_label"] == "Pendiente de verificación"
    code, captured = run(
        capsys, "rotation", *base, "--steps", "Q.out", "--attacker-range", "ranged",
        "--target-current-health", "2000", *page_args(), "--json",
    )  # fmt: skip
    assert code == 0, captured.err
    report = json.loads(captured.out)
    assert report["weakest_input_label"] == "Pendiente de verificación"
    assert "rune 8112 Electrocutar: effects not modelled (RUN-04)" in report["not_applied"]
