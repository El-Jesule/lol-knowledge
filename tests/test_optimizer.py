"""Tests for the build optimizer: objectives, constraints, legality, pruning and labels."""

from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

import pytest

from lol_knowledge.cli import main as cli_main
from lol_knowledge.defense import parse_incoming
from lol_knowledge.errors import StatsError
from lol_knowledge.kit import load_kit
from lol_knowledge.objects.legality import check_build, load_item_groups
from lol_knowledge.optimizer import (
    OptimizeConstraints,
    format_text,
    optimize_build,
    to_dict,
)
from lol_knowledge.rotation import CritBase, parse_steps
from lol_knowledge.runes import load_runes
from lol_knowledge.scenario import Target
from lol_knowledge.stats import Label, load_champion, load_records

ROOT = Path(__file__).resolve().parents[1]
RECORDS = load_records(ROOT)
ITEM_GROUPS = load_item_groups(ROOT)
RUNE_DATA = load_runes(ROOT)
CRIT_BASE = CritBase(Fraction(2), Label.DERIVED, "patch 26.1")


def _target(hp: int = 2000, armor: int = 60, mr: int = 60, kind: str = "champion") -> Target:
    return Target(
        armor=Fraction(armor),
        magic_resist=Fraction(mr),
        stats={"max_health": Fraction(hp), "current_health": Fraction(hp)},
        label=Label.OFFICIAL,
        description=f"{kind} {hp}hp {armor}ar {mr}mr",
        kind=kind,
    )


def test_ehp_objectives_and_damage_mix_endpoints() -> None:
    champ = load_champion(ROOT, "Garen")
    cfg_base = OptimizeConstraints(
        slots=2, budget=7000, only_verified=True, top=3, beam_width=10, pool_limit=12
    )
    phys = optimize_build(
        ROOT, champ, 11, "effective_health_physical", constraints=cfg_base, derived=RECORDS
    )
    magic = optimize_build(
        ROOT, champ, 11, "effective_health_magic", constraints=cfg_base, derived=RECORDS
    )
    mix_phys = optimize_build(
        ROOT,
        champ,
        11,
        "effective_health_mixed",
        constraints=OptimizeConstraints(
            slots=2,
            budget=7000,
            only_verified=True,
            top=3,
            beam_width=10,
            pool_limit=12,
            damage_mix_physical=Fraction(1),
        ),
        derived=RECORDS,
    )
    mix_magic = optimize_build(
        ROOT,
        champ,
        11,
        "effective_health_mixed",
        constraints=OptimizeConstraints(
            slots=2,
            budget=7000,
            only_verified=True,
            top=3,
            beam_width=10,
            pool_limit=12,
            damage_mix_physical=Fraction(0),
        ),
        derived=RECORDS,
    )
    assert phys.verified_builds and magic.verified_builds
    assert phys.pending_builds == ()
    assert phys.verified_builds[0].score == mix_phys.verified_builds[0].score
    assert magic.verified_builds[0].score == mix_magic.verified_builds[0].score
    assert phys.verified_builds[0].items != magic.verified_builds[0].items


def test_opt03_separates_verified_and_pending_builds() -> None:
    champ = load_champion(ROOT, "Garen")
    outcome = optimize_build(
        ROOT,
        champ,
        11,
        "effective_health_mixed",
        constraints=OptimizeConstraints(
            slots=2,
            budget=7000,
            require_boots=True,
            only_verified=False,
            top=3,
            beam_width=10,
            pool_limit=12,
        ),
        derived=RECORDS,
    )
    assert outcome.verified_builds
    assert outcome.pending_builds
    assert all(b.verified and b.label is not Label.PENDING for b in outcome.verified_builds)
    assert all(not b.verified and b.label is Label.PENDING for b in outcome.pending_builds)
    assert outcome.label is Label.DERIVED
    assert ITEM_GROUPS is not None
    for build in (*outcome.verified_builds, *outcome.pending_builds):
        assert build.total_gold <= 7000
        assert len(build.items) <= 2
        assert ITEM_GROUPS.has_boots(build.items)
        assert check_build(build.items, ITEM_GROUPS, patch=champ.patch, champion=champ.id).legal


def test_rotation_damage_dps_and_healing_objectives() -> None:
    champ = load_champion(ROOT, "Ahri")
    kit = load_kit(ROOT, "Ahri")
    assert kit is not None
    ranks = {"Q": 5, "W": 3, "E": 1, "R": 2}
    res_dmg = optimize_build(
        ROOT,
        champ,
        11,
        "rotation_damage",
        constraints=OptimizeConstraints(
            slots=2,
            budget=7500,
            required_items=("3089",),
            forbidden_items=("6655",),
            only_verified=True,
            top=3,
            beam_width=8,
            pool_limit=10,
        ),
        derived=RECORDS,
        kit=kit,
        ranks=ranks,
        target=_target(),
        steps=parse_steps("E Q.both"),
        crit_base=CRIT_BASE,
        holder_range="ranged",
    )
    assert res_dmg.verified_builds
    for b in res_dmg.verified_builds:
        assert "3089" in b.items
        assert "6655" not in b.items
        assert b.total_gold <= 7500

    # DPS on Jinx basic attacks with timeline
    jinx = load_champion(ROOT, "Jinx")
    jinx_kit = load_kit(ROOT, "Jinx")
    assert jinx_kit is not None
    res_dps = optimize_build(
        ROOT,
        jinx,
        11,
        "dps",
        constraints=OptimizeConstraints(
            slots=1, budget=3600, only_verified=True, top=3, beam_width=8, pool_limit=10
        ),
        derived=RECORDS,
        kit=jinx_kit,
        ranks={"Q": 5, "W": 3, "E": 1, "R": 2},
        target=_target(hp=3000),
        steps=parse_steps("attack attack attack"),
        crit_base=CRIT_BASE,
        holder_range="ranged",
        timeline=True,
    )
    assert res_dps.verified_builds
    assert res_dps.verified_builds[0].score > 0
    assert "dps" in res_dps.verified_builds[0].metrics

    # Healing on Caitlyn attacks picks a life-steal / vamp item
    cait = load_champion(ROOT, "Caitlyn")
    cait_kit = load_kit(ROOT, "Caitlyn")
    assert cait_kit is not None
    res_heal = optimize_build(
        ROOT,
        cait,
        11,
        "healing",
        constraints=OptimizeConstraints(
            slots=1, budget=3600, only_verified=True, top=3, beam_width=8, pool_limit=10
        ),
        derived=RECORDS,
        kit=cait_kit,
        ranks={"Q": 5, "W": 3, "E": 1, "R": 2},
        target=_target(hp=3000),
        steps=parse_steps("attack attack"),
        crit_base=CRIT_BASE,
        holder_range="ranged",
    )
    assert res_heal.verified_builds
    assert res_heal.verified_builds[0].score > 0


def test_time_to_die_objective_with_incoming_hits_and_runes() -> None:
    champ = load_champion(ROOT, "Garen")
    hits = parse_incoming("attack:600, attack:600, attack:600, magic:500")
    # Legal Resolve/Precision page with modelled defensive runes (Bone Plating + Revitalize)
    runes = [8465, 8446, 8473, 8453, 9111, 8014]
    shards = [5005, 5008, 5001]
    res = optimize_build(
        ROOT,
        champ,
        9,
        "time_to_die",
        constraints=OptimizeConstraints(
            slots=2, budget=6500, only_verified=True, top=3, beam_width=8, pool_limit=10
        ),
        derived=RECORDS,
        inputs={"guardian_ally": 1},
        incoming_hits=hits,
        runes=runes,
        shards=shards,
        rune_data=RUNE_DATA,
    )
    assert res.verified_builds
    top = res.verified_builds[0]
    assert top.metrics["survived"] is True
    assert top.score > 0
    assert res.stats.states_evaluated > 0
    assert res.stats.elapsed_ms >= 0


def test_optimizer_determinism_and_constraint_validation() -> None:
    champ = load_champion(ROOT, "Garen")
    cfg = OptimizeConstraints(
        slots=2, budget=6500, only_verified=True, top=3, beam_width=8, pool_limit=10
    )
    first = optimize_build(
        ROOT, champ, 9, "effective_health_physical", constraints=cfg, derived=RECORDS
    )
    second = optimize_build(
        ROOT, champ, 9, "effective_health_physical", constraints=cfg, derived=RECORDS
    )
    assert [b.items for b in first.verified_builds] == [b.items for b in second.verified_builds]
    assert [b.score for b in first.verified_builds] == [b.score for b in second.verified_builds]
    assert first.stats.states_evaluated == second.stats.states_evaluated

    # Reject two pairs of required boots (OBJ-13)
    with pytest.raises(StatsError, match="not a legal build"):
        optimize_build(
            ROOT,
            champ,
            9,
            "effective_health_physical",
            constraints=OptimizeConstraints(slots=2, required_items=("3047", "3111")),
            derived=RECORDS,
        )

    # Reject two Spellblade items (client exclusive group)
    with pytest.raises(StatsError, match="not a legal build"):
        optimize_build(
            ROOT,
            champ,
            9,
            "effective_health_physical",
            constraints=OptimizeConstraints(slots=2, required_items=("3078", "3100")),
            derived=RECORDS,
        )

    # Reject required items exceeding budget
    with pytest.raises(StatsError, match="exceeding budget"):
        optimize_build(
            ROOT,
            champ,
            9,
            "effective_health_physical",
            constraints=OptimizeConstraints(slots=2, budget=1000, required_items=("3089",)),
            derived=RECORDS,
        )

    # Reject illegal rune page (RUN-04)
    with pytest.raises(StatsError, match="rune page is not legal"):
        optimize_build(
            ROOT,
            champ,
            9,
            "effective_health_physical",
            constraints=OptimizeConstraints(slots=1),
            derived=RECORDS,
            runes=[8437, 8437],
            shards=[5008, 5008, 5001],
            rune_data=RUNE_DATA,
        )


def test_optimizer_cli_json_and_text_reports(capsys) -> None:
    rc = cli_main(
        [
            "optimize",
            "--champion",
            "Garen",
            "--level",
            "9",
            "--objective",
            "effective_health_physical",
            "--slots",
            "1",
            "--budget",
            "3500",
            "--only-verified",
            "--top",
            "2",
            "--beam-width",
            "6",
            "--pool-limit",
            "8",
            "--root",
            str(ROOT),
            "--json",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["label"] == "Calculado"
    assert payload["objective"] == "effective_health_physical"
    assert len(payload["verified_builds"]) == 2
    assert payload["pending_builds"] == []
    assert payload["search_stats"]["states_evaluated"] > 0

    # Text formatting smoke check
    champ = load_champion(ROOT, "Garen")
    out = optimize_build(
        ROOT,
        champ,
        9,
        "effective_health_physical",
        constraints=OptimizeConstraints(
            slots=1, budget=3500, only_verified=True, top=2, beam_width=6, pool_limit=8
        ),
        derived=RECORDS,
    )
    txt = format_text(out)
    assert "verified builds (Oficial/Derivado):" in txt
    assert to_dict(out)["champion"] == "Garen"

    # Bad args return exit code 2
    rc_bad = cli_main(
        [
            "optimize",
            "--champion",
            "Garen",
            "--level",
            "9",
            "--objective",
            "rotation_damage",
            "--root",
            str(ROOT),
        ]
    )
    assert rc_bad == 2
