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
    minor_rune_effects,
    needs_adaptive_stat,
    parse_runes,
    runes_problems,
    shard_contributions,
)
from lol_knowledge.stats import ItemData, ItemStat, Label

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


def test_transcendence_scales_at_levels_5_and_8():
    low = minor_rune_effects([8210], DATA, level=4, patch=PATCH)
    assert low.flats == () and low.pending == ()
    assert any("active from level 5" in note for note in low.notes)
    mid = minor_rune_effects([8210], DATA, level=5, patch=PATCH)
    assert [(s, c.value, c.label) for s, c in mid.flats] == [("ability_haste", 5, Label.DERIVED)]
    high = minor_rune_effects([8210], DATA, level=11, patch=PATCH)
    assert [(s, c.value, c.label) for s, c in high.flats] == [("ability_haste", 10, Label.DERIVED)]
    assert any("takedown" in note for note in high.notes)
    assert high.pending == ()


def test_legend_runes_default_to_max_stacks_and_accept_override():
    alacrity = minor_rune_effects([9104], DATA, level=11, patch=PATCH)
    assert [(s, c.value, c.label) for s, c in alacrity.flats] == [
        ("attack_speed_bonus", F(18, 100), Label.DERIVED)
    ]
    partial = minor_rune_effects(
        [9104], DATA, level=11, patch=PATCH, inputs={"legend_stacks": F(4)}
    )
    assert partial.flats[0][1].value == F(9, 100)  # 3% + 4 * 1.5%
    haste = minor_rune_effects([9105], DATA, level=11, patch=PATCH)
    assert [(s, c.value) for s, c in haste.flats] == [("basic_ability_haste", 15)]
    bloodline = minor_rune_effects([9103], DATA, level=11, patch=PATCH)
    assert [(s, c.value) for s, c in bloodline.flats] == [
        ("life_steal", F(27, 400)),  # 15 * 0.45% = 6.75%
        ("health", 85),
    ]
    partial_bl = minor_rune_effects(
        [9103], DATA, level=11, patch=PATCH, inputs={"legend_stacks": F(14)}
    )
    assert [(s, c.value) for s, c in partial_bl.flats] == [("life_steal", F(63, 1000))]
    with pytest.raises(StatsError, match="legend_stacks"):
        minor_rune_effects([9104], DATA, level=11, patch=PATCH, inputs={"legend_stacks": F(11)})


def test_manaflow_band_and_ultimate_hunter():
    mana = minor_rune_effects([8226], DATA, level=11, patch=PATCH, uses_mana=True)
    assert [(s, c.value) for s, c in mana.flats] == [("mana", 250)]
    assert mana.pending == ()
    manaless = minor_rune_effects([8226], DATA, level=11, patch=PATCH, uses_mana=False)
    assert manaless.flats == () and manaless.pending == ()
    assert any("does not use mana" in note for note in manaless.notes)
    ult = minor_rune_effects([8106], DATA, level=11, patch=PATCH)
    assert [(s, c.value) for s, c in ult.flats] == [("ultimate_haste", 31)]
    ult_zero = minor_rune_effects(
        [8106], DATA, level=11, patch=PATCH, inputs={"bounty_stacks": F(0)}
    )
    assert [(s, c.value) for s, c in ult_zero.flats] == [("ultimate_haste", 6)]
    with pytest.raises(StatsError, match="bounty_stacks"):
        minor_rune_effects([8106], DATA, level=11, patch=PATCH, inputs={"bounty_stacks": F(6)})


def test_magical_footwear_and_biscuit_delivery():
    with_boots = minor_rune_effects([8304], DATA, level=11, patch=PATCH, has_boots=True)
    assert [(s, c.value) for s, c in with_boots.flats] == [("move_speed", 10)]
    no_boots = minor_rune_effects([8304], DATA, level=11, patch=PATCH, has_boots=False)
    assert no_boots.flats == () and no_boots.pending == ()
    unknown = minor_rune_effects([8304], DATA, level=11, patch=PATCH, has_boots=None)
    assert unknown.flats == () and len(unknown.pending) == 1

    biscuits_max = minor_rune_effects([8345], DATA, level=11, patch=PATCH)
    assert [(s, c.value) for s, c in biscuits_max.flats] == [("health", 90)]
    biscuits_4m = minor_rune_effects(
        [8345], DATA, level=11, patch=PATCH, inputs={"game_minutes": F(4)}
    )
    assert [(s, c.value) for s, c in biscuits_4m.flats] == [("health", 60)]
    biscuits_1m = minor_rune_effects(
        [8345], DATA, level=11, patch=PATCH, inputs={"game_minutes": F(1)}
    )
    assert biscuits_1m.flats == ()


def test_jack_of_all_trades_counts_distinct_item_stats_and_adaptive():
    assert needs_adaptive_stat([8316], [], DATA)
    empty = minor_rune_effects([8316], DATA, level=11, patch=PATCH, items=())
    assert empty.flats == () and empty.pending == ()
    items = (
        ItemData(
            "1",
            "Item A",
            PATCH,
            (
                ItemStat("attack_damage", "flat", F(30), "ddragon_stat"),
                ItemStat("move_speed", "flat", F(45), "ddragon_stat"),
                ItemStat("move_speed", "percent", F(10), "ddragon_stat"),
                ItemStat("health", "flat", F(200), "ddragon_stat"),
                ItemStat("armor", "flat", F(20), "ddragon_stat"),
            ),
            unmodelled_stats=(
                "heal and shield power is not a stat of the engine",
                "gold income is not a champion stat",
            ),
        ),
    )
    # 6 distinct stats: AD, flat MS, % MS, health, armor, heal_shield_power (gold ignored)
    eff = minor_rune_effects(
        [8316], DATA, level=11, patch=PATCH, items=items, adaptive="attack_damage"
    )
    assert [(s, c.value, c.label) for s, c in eff.flats] == [
        ("ability_haste", 6, Label.DERIVED),
        ("attack_damage", F(24, 5), Label.DERIVED),  # 8 * 0.6 = 4.8 AD
    ]
    ten_stats = ItemData(
        "2",
        "Item B",
        PATCH,
        tuple(
            ItemStat(name, "flat", F(10), "ddragon_stat")
            for name in (
                "attack_damage",
                "ability_power",
                "health",
                "mana",
                "armor",
                "magic_resist",
                "ability_haste",
                "lethality",
                "move_speed",
                "health_regen",
            )
        ),
    )
    eff10 = minor_rune_effects(
        [8316], DATA, level=11, patch=PATCH, items=(ten_stats,), adaptive="ability_power"
    )
    assert [(s, c.value) for s, c in eff10.flats] == [
        ("ability_haste", 10),
        ("ability_power", 20),
    ]
    unknown_item = ItemData(
        "3",
        "Unknown",
        PATCH,
        (
            ItemStat("health", "flat", F(100), "ddragon_stat"),
            ItemStat("lethality", "flat", F(0), "ddragon_description", Label.PENDING),
        ),
    )
    eff_unk = minor_rune_effects([8316], DATA, level=11, patch=PATCH, items=(unknown_item,))
    assert eff_unk.flats[0][1].label is Label.PENDING


def test_time_and_conditional_minor_runes_require_inputs_and_apply_exact_formulas():
    for rune_id, expected_hint in (
        (8236, "game_minutes"),
        (8429, "game_minutes"),
        (8451, "overgrowth_units"),
        (8233, "attacker_health_percent"),
        (8232, "in_river"),
    ):
        missing = minor_rune_effects([rune_id], DATA, level=11, patch=PATCH)
        assert missing.flats == () and missing.amplifiers == ()
        assert any(expected_hint in item for item in missing.pending)

    # Gathering Storm: 0 at 9m, 8 AP at 10m, 24 AP at 20m, 48 AP (28.8 AD) at 30m
    gs9 = minor_rune_effects(
        [8236], DATA, level=11, patch=PATCH, inputs={"game_minutes": F(9)}, adaptive="ability_power"
    )
    assert gs9.flats == () and gs9.pending == ()
    gs30 = minor_rune_effects(
        [8236],
        DATA,
        level=11,
        patch=PATCH,
        inputs={"game_minutes": F(30)},
        adaptive="attack_damage",
    )
    assert [(s, c.value) for s, c in gs30.flats] == [("attack_damage", F(144, 5))]  # 48 * 0.6

    # Conditioning: inactive at 11m, +8 armor/MR and +3% amplifiers at 12m
    cond11 = minor_rune_effects([8429], DATA, level=11, patch=PATCH, inputs={"game_minutes": F(11)})
    assert cond11.flats == () and cond11.amplifiers == () and cond11.pending == ()
    cond12 = minor_rune_effects([8429], DATA, level=11, patch=PATCH, inputs={"game_minutes": F(12)})
    assert [(s, c.value) for s, c in cond12.flats] == [("armor", 8), ("magic_resist", 8)]
    assert [(a.stat, a.percent) for a in cond12.amplifiers] == [("armor", 3), ("magic_resist", 3)]

    # Overgrowth: 0 flat below 8, +45 flat + 3.5% amplifier at 120
    og7 = minor_rune_effects([8451], DATA, level=11, patch=PATCH, inputs={"overgrowth_units": F(7)})
    assert og7.flats == () and og7.amplifiers == () and og7.pending == ()
    og120 = minor_rune_effects(
        [8451], DATA, level=11, patch=PATCH, inputs={"overgrowth_units": F(120)}
    )
    assert [(s, c.value) for s, c in og120.flats] == [("health", 45)]
    assert [(a.stat, a.percent) for a in og120.amplifiers] == [("health", F(7, 2))]

    # Absolute Focus: linear 3..30 AP by level; exact 0.7 threshold is Pending
    af_low = minor_rune_effects(
        [8233],
        DATA,
        level=18,
        patch=PATCH,
        inputs={"attacker_health_percent": F(69, 100)},
        adaptive="ability_power",
    )
    assert af_low.flats == () and af_low.pending == ()
    af_high = minor_rune_effects(
        [8233],
        DATA,
        level=18,
        patch=PATCH,
        inputs={"attacker_health_percent": F(1)},
        adaptive="ability_power",
    )
    assert [(s, c.value, c.label) for s, c in af_high.flats] == [
        ("ability_power", 30, Label.DERIVED)
    ]
    af_edge = minor_rune_effects(
        [8233],
        DATA,
        level=1,
        patch=PATCH,
        inputs={"attacker_health_percent": F(7, 10)},
        adaptive="attack_damage",
    )
    assert [(s, c.value, c.label) for s, c in af_edge.flats] == [
        ("attack_damage", F(9, 5), Label.PENDING)  # 3 * 0.6 = 1.8
    ]

    # Waterwalking: 0 outside river, +10 MS and 13..30 adaptive in river
    ww0 = minor_rune_effects([8232], DATA, level=1, patch=PATCH, inputs={"in_river": F(0)})
    assert ww0.flats == () and ww0.pending == ()
    ww1 = minor_rune_effects(
        [8232], DATA, level=18, patch=PATCH, inputs={"in_river": F(1)}, adaptive="ability_power"
    )
    assert [(s, c.value) for s, c in ww1.flats] == [("move_speed", 10), ("ability_power", 30)]


@pytest.mark.parametrize(
    ("rune_id", "inputs", "message"),
    [
        (8236, {"game_minutes": F(-1)}, "must not be negative"),
        (8451, {"overgrowth_units": F(5, 2)}, "must be an integer"),
        (8233, {"attacker_health_percent": F(3, 2)}, "between 0 and 1"),
        (8232, {"in_river": F(2)}, "between 0 and 1"),
    ],
)
def test_invalid_rune_inputs_raise_stats_error(rune_id, inputs, message):
    with pytest.raises(StatsError, match=message):
        minor_rune_effects([rune_id], DATA, level=11, patch=PATCH, inputs=inputs)


def test_non_combat_utility_minor_runes_do_not_add_pending_effects():
    non_combat = [8137, 8140, 8141, 8135, 8105, 8306, 8321]
    eff = minor_rune_effects(non_combat, DATA, level=11, patch=PATCH)
    assert eff.flats == () and eff.percents == () and eff.pending == ()
    assert len(eff.notes) == len(non_combat)


def test_cli_stats_applies_minor_runes_cooldowns_amplifiers_and_celerity(capsys):
    # Ahri lvl 11 with Rabadon (3089) + Sorcerer's Shoes (3020) + PAGE (has Transcendence,
    # Manaflow Band, Ultimate Hunter, Sixth Sense)
    code, captured = run(
        capsys,
        "stats",
        "--champion",
        "Ahri",
        "--level",
        "11",
        "--item",
        "3089",
        "--item",
        "3020",
        *page_args(),
        "--json",
    )
    assert code == 0, captured.err
    report = json.loads(captured.out)
    # Transcendence (+10 AH at lvl 11), Manaflow Band (+250 mana), Ultimate Hunter (+31 R haste)
    assert report["stats"]["ability_haste"]["total"] == 10
    assert report["stats"]["ultimate_haste"]["total"] == 31
    assert report["stats"]["mana"]["bonus"] == 250
    cd = report["metrics"]["cooldowns"]
    assert cd["ability_haste"] == 10
    assert cd["ultimate_haste"] == 31
    # Ahri R rank 1 base cooldown (140 s in 16.23.1) with 10 + 31 = 41 haste
    assert cd["spells"][3]["base"][0] == 140
    assert cd["spells"][3]["effective"][0] == pytest.approx(140 * 100 / 141)

    # Conditioning + Overgrowth + Celerity + Gathering Storm via --input
    # Page: Sorcery (8229, 8226, 8234 Celerity, 8236 GatheringStorm) +
    #       Resolve (8429 Conditioning, 8451 Overgrowth)
    page2 = [8229, 8226, 8234, 8236, 8429, 8451]
    code, captured = run(
        capsys,
        "stats",
        "--champion",
        "Ahri",
        "--level",
        "11",
        "--item",
        "3089",
        "--item",
        "3020",
        *page_args(runes=page2, shards=[5008, 5010, 5011]),
        "--input",
        "game_minutes=20",
        "--input",
        "overgrowth_units=120",
        "--json",
    )
    assert code == 0, captured.err
    report2 = json.loads(captured.out)
    # AP: (130 Rabadon + 9 adaptive shard + 24 Gathering Storm) * 1.3 = 163 * 1.3 = 211.9
    assert report2["stats"]["ability_power"]["exact"] == "2119/10"
    # Armor: (base + 8 Conditioning) * 1.03
    armor = report2["stats"]["armor"]
    assert any(c["source"].startswith("rune:8429 Conditioning") for c in armor["contributions"])
    assert any(c["note"].endswith("3% of the total") for c in armor["contributions"])
    # Health: includes +65 shard + 45 Overgrowth + 3.5% Overgrowth amplifier
    health = report2["stats"]["health"]
    assert any(c["note"].endswith("3.5% of the total") for c in health["contributions"])
    # Celerity: Ahri base 330 + Boots 45 + 7% of 45 (3.15) = 378.15; % MS = 2.5% shard + 1%
    # Celerity + 7% of 2.5% (0.175%) = 3.675%; raw = 378.15 * 1.03675 = 392.0470125 (< 415)
    ms = report2["stats"]["move_speed"]
    assert ms["total"] == pytest.approx(378.15 * 1.03675)
    assert ms["label"] == "Pendiente de verificación"


def test_cli_stats_magical_footwear_checks_boots_and_rejects_bad_input(capsys):
    # Inspiration (8369, 8304 MagicalFootwear, 8345 BiscuitDelivery, 8316 JackOfAllTrades) +
    # Precision (9104 LegendAlacrity, 9105 LegendHaste — illegal same row? Use 9104 + 8014)
    page = [8369, 8304, 8345, 8316, 9104, 8014]
    code, captured = run(
        capsys,
        "stats",
        "--champion",
        "Ahri",
        "--level",
        "11",
        "--item",
        "3020",
        *page_args(runes=page),
        "--json",
    )
    assert code == 0, captured.err
    report = json.loads(captured.out)
    # Ahri base 330 + Sorcerer's Shoes 45 + Magical Footwear 10 = 385
    assert report["stats"]["move_speed"]["total"] == 385
    # Biscuit Delivery adds +90 HP (max stacks) on top of 110 from HealthScaling shard
    assert report["stats"]["health"]["total"] == pytest.approx(1502.6 + 110 + 90)
    # Sorcerer's Shoes has 2 stats (move_speed flat, magic_penetration_flat) -> +2 AH from Jack
    assert report["stats"]["ability_haste"]["total"] == 2
    assert report["stats"]["attack_speed_bonus"]["bonus"] == pytest.approx(0.18)

    code, captured = run(
        capsys,
        "stats",
        "--champion",
        "Ahri",
        "--level",
        "11",
        *page_args(runes=page),
        "--input",
        "game_minutes=-5",
    )
    assert code == 2 and "must not be negative" in captured.err


def test_celerity_alone_keeps_derived_label_and_ability_uses_rune_inputs(capsys):
    # Celerity without boots or MS shard: +1% MS only -> Derivado (330 * 1.01 = 333.3)
    page = [8229, 8226, 8234, 8236, 8137, 8106]
    code, captured = run(
        capsys,
        "stats",
        "--champion",
        "Ahri",
        "--level",
        "11",
        *page_args(runes=page, shards=[5008, 5008, 5011]),
        "--input",
        "game_minutes=20",
        "--json",
    )
    assert code == 0, captured.err
    report = json.loads(captured.out)
    assert report["stats"]["move_speed"]["exact"] == "3333/10"
    assert report["stats"]["move_speed"]["label"] == "Derivado"

    # Ability damage reflects Gathering Storm (+24 AP at 20 min vs 0 at 0 min)
    target = ["--target-armor", "60", "--target-mr", "40", "--target-max-health", "2000"]
    base = [
        "ability",
        "--champion",
        "Ahri",
        "--level",
        "11",
        "--ability",
        "Q",
        "--rank",
        "5",
        "--case",
        "out",
        *target,
        *page_args(runes=page, shards=[5008, 5008, 5011]),
        "--json",
    ]
    _, out0 = run(capsys, *base, "--input", "game_minutes=0")
    _, out20 = run(capsys, *base, "--input", "game_minutes=20")
    dmg0 = json.loads(out0.out)["cases"][0]["total"]
    dmg20 = json.loads(out20.out)["cases"][0]["total"]
    assert dmg20 > dmg0


def test_rotation_timeline_uses_basic_ability_haste_from_legend_haste(capsys):
    # Ahri Q base cooldown is 7s. With Transcendence (+10 AH at lvl 11) + Legend: Haste
    # (+15 basic AH), effective Q cooldown is 7 * 100 / 125 = 5.6s (so wait:6 allows second Q,
    # while without runes 6s fails the cooldown check).
    page = [8010, 9101, 9105, 8014, 8226, 8210]
    common = [
        "rotation",
        "--champion",
        "Ahri",
        "--level",
        "11",
        "--learned",
        "Q=5",
        "--attacker-range",
        "ranged",
        "--target-armor",
        "60",
        "--target-mr",
        "40",
        "--target-max-health",
        "2000",
        "--target-kind",
        "champion",
        "--steps",
        "Q.out, wait:6, Q.out",
        "--timeline",
    ]
    code_no_runes, captured_no_runes = run(capsys, *common)
    assert code_no_runes == 2 and "cooldown" in captured_no_runes.err
    code, captured = run(capsys, *common, *page_args(runes=page), "--json")
    assert code == 0, captured.err
    assert len(json.loads(captured.out)["steps"]) == 3
