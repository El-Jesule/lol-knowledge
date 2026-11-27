"""Tests for compiled formula caching, Ornn deduplication, and adaptive fast-path (PERF-03/04)."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import pytest

from lol_knowledge.formula import (
    ABILITY_OPS,
    OBJECT_OPS,
    CompiledFormula,
    FormulaError,
    compile_formula,
    evaluate_formula,
)
from lol_knowledge.kit import load_kit
from lol_knowledge.objects.legality import load_item_groups
from lol_knowledge.optimizer import OptimizeConstraints, optimize_build
from lol_knowledge.optimizer.search import _BuildEvaluator, load_candidate_pool
from lol_knowledge.rotation import CritBase, parse_steps
from lol_knowledge.runes import (
    adaptive_stat,
    load_runes,
    minor_rune_effects,
    shard_contributions,
)
from lol_knowledge.scenario import target_from_values
from lol_knowledge.stats import (
    Label,
    build_stat_sheet,
    load_champion,
    load_issues,
    load_items,
    load_records,
)
from lol_knowledge.stats.sheet import MANA_RESOURCE
from lol_knowledge.upgrades import ornn_upgrade_contributions

ROOT = Path(__file__).resolve().parents[1]


def test_compiled_formula_all_ops_exact_and_dependencies() -> None:
    formula = {
        "op": "add",
        "operands": [
            {"op": "constant", "value": 0.1},
            {"op": "by_rank", "values": [10, 20, 30]},
            {"op": "by_level", "values": [1, 2, 3]},
            {"op": "linear_by_level", "min": 10, "max": 27},
            {"op": "percent_of", "stat": "attack_damage", "scope": "bonus", "percent": 50},
            {
                "op": "min",
                "operands": [
                    {"op": "stat", "stat": "health", "scope": "max", "subject": "target"},
                    {"op": "input", "name": "stacks", "default": 5},
                ],
            },
            {
                "op": "by_holder_range",
                "melee": {"op": "constant", "value": 4},
                "ranged": {
                    "op": "mul",
                    "operands": [{"op": "constant", "value": 2}, {"op": "constant", "value": 3}],
                },
            },
        ],
    }
    compiled = compile_formula(formula, ops=ABILITY_OPS)
    assert isinstance(compiled, CompiledFormula)
    assert compile_formula(compiled, ops=ABILITY_OPS) is compiled

    res_compiled = evaluate_formula(
        compiled,
        {"bonus_attack_damage": Fraction(40)},
        holder_range="ranged",
        rank=2,
        level=2,
        target_stats={"max_health": Fraction(100)},
        ops=ABILITY_OPS,
    )
    res_raw = evaluate_formula(
        formula,
        {"bonus_attack_damage": Fraction(40)},
        holder_range="ranged",
        rank=2,
        level=2,
        target_stats={"max_health": Fraction(100)},
        ops=ABILITY_OPS,
    )
    # 1/10 + 20 + 2 + 11 + 20 + min(100, 5) + 6 = 64 + 1/10 = 641/10
    assert res_compiled.exact == Fraction(641, 10)
    assert res_compiled == res_raw
    assert res_compiled.dependencies == (
        "rank",
        "level",
        "bonus_attack_damage",
        "target:max_health",
        "input:stacks",
        "holder_range",
    )


def test_compiled_formula_preserves_error_codes_and_node() -> None:
    bad = {"op": "unknown_op"}
    with pytest.raises(FormulaError) as exc_info:
        evaluate_formula(bad, {}, ops=OBJECT_OPS)
    assert exc_info.value.code == "malformed_formula"
    assert exc_info.value.node is bad

    with pytest.raises(FormulaError) as exc_missing:
        evaluate_formula({"op": "stat", "stat": "armor", "scope": "total"}, {})
    assert exc_missing.value.code == "missing_stat"

    with pytest.raises(FormulaError) as exc_unk:
        evaluate_formula({"op": "unknown", "reason": "no data"}, {})
    assert exc_unk.value.code == "unknown_input"

    with pytest.raises(FormulaError) as exc_unsup:
        evaluate_formula({"op": "unsupported", "reason": "not modelled"}, {})
    assert exc_unsup.value.code == "unsupported_formula"


def test_ornn_upgrade_deduplication_matches_exhaustive_best() -> None:
    issues = load_issues(ROOT)
    derived = load_records(ROOT)
    ch = load_champion(ROOT, "Ahri")
    kit = load_kit(ROOT, "Ahri")
    groups = load_item_groups(ROOT)
    assert groups is not None and kit is not None

    # 3089 (Rabadon) and 3135 (Void Staff) both only have ability_power among Ornn stats.
    items = load_items(ROOT, ["3089", "3135"])
    fx_3089 = ornn_upgrade_contributions("3089", items, level=13, item_groups=groups)
    fx_3135 = ornn_upgrade_contributions("3135", items, level=13, item_groups=groups)
    assert [s for s, _ in fx_3089.flats] == [s for s, _ in fx_3135.flats]
    assert [c.value for _, c in fx_3089.flats] == [c.value for _, c in fx_3135.flats]

    tgt = target_from_values(Fraction(80), Fraction(60), max_health=Fraction(2000), kind="champion")
    res = optimize_build(
        ROOT,
        ch,
        11,
        "rotation_damage",
        constraints=OptimizeConstraints(
            slots=2,
            required_items=("3089", "3135"),
            ornn_upgrade=True,
            top=1,
        ),
        issues=issues,
        derived=derived,
        kit=kit,
        ranks={"Q": 5, "W": 3, "E": 1, "R": 2},
        target=tgt,
        steps=parse_steps("E, Q.both, W.all, R.dash"),
        crit_base=CritBase(Fraction(2), Label.DERIVED, "client"),
        holder_range="ranged",
    )
    top = res.verified_builds[0]
    assert top.items == ("3089", "3135")
    # Deterministic tie-break picks lowest item id ("3089") among identical Ornn stat sets.
    assert top.ornn_upgraded_item == "3089"
    assert res.stats.states_evaluated >= 1

    # Verify Ornn deduplication evaluates only 1 representative for ("3089", "3135").
    from lol_knowledge.optimizer import search as opt_search

    calls: list[str | None] = []
    orig_ornn = opt_search.ornn_upgrade_contributions

    def spy_ornn(ornn_item_id, items_arg, **kwargs):
        calls.append(ornn_item_id)
        return orig_ornn(ornn_item_id, items_arg, **kwargs)

    # Run evaluator directly on ("3089", "3135")
    pool = load_candidate_pool(ROOT, groups, champion_id="Ahri")
    ev = _BuildEvaluator(
        objective="rotation_damage",
        champion=ch,
        level=11,
        pool=pool,
        item_groups=groups,
        issues=issues,
        derived=derived,
        assumptions={},
        inputs={},
        kit=kit,
        ranks={"Q": 5, "W": 3, "E": 1, "R": 2},
        target=tgt,
        steps=parse_steps("E, Q.both, W.all, R.dash"),
        crit_base=CritBase(Fraction(2), Label.DERIVED, "client"),
        holder_range="ranged",
        timeline=False,
        target_count=1,
        incoming_hits=(),
        incoming_hits_for_sheet=None,
        runes=(),
        shards=(),
        rune_data=None,
        constraints=OptimizeConstraints(slots=2, ornn_upgrade=True),
    )
    monkeypatch_orig = opt_search.ornn_upgrade_contributions
    opt_search.ornn_upgrade_contributions = spy_ornn
    try:
        b_res = ev.evaluate(("3089", "3135"))
    finally:
        opt_search.ornn_upgrade_contributions = monkeypatch_orig
    assert b_res is not None
    assert calls == ["3089"]


def test_adaptive_fast_path_matches_full_sheet_assembly() -> None:
    issues = load_issues(ROOT)
    derived = load_records(ROOT)
    rune_data = load_runes(ROOT)
    groups = load_item_groups(ROOT)
    assert rune_data is not None and groups is not None
    tgt = target_from_values(Fraction(80), Fraction(60), max_health=Fraction(2000), kind="champion")

    runes = [8112, 8143, 8137, 8106, 8226, 8210]
    shards = [5008, 5008, 5001]

    for champ_id, item_ids in [
        ("Ahri", ["6653", "2503"]),
        ("Garen", ["3078", "3053"]),  # 3053 Sterak uses sheet_effects -> exercises fallback
        ("Vladimir", ["3089", "3152"]),  # Vladimir cross conversion -> exercises fallback
    ]:
        champ = load_champion(ROOT, champ_id)
        pool = load_candidate_pool(ROOT, groups, champion_id=champ.id)
        ev = _BuildEvaluator(
            objective="effective_health_mixed",
            champion=champ,
            level=11,
            pool=pool,
            item_groups=groups,
            issues=issues,
            derived=derived,
            assumptions={},
            inputs={},
            kit=None,
            ranks={},
            target=tgt,
            steps=(),
            crit_base=None,
            holder_range="ranged" if champ_id in {"Ahri", "Vladimir"} else "melee",
            timeline=False,
            target_count=1,
            incoming_hits=(),
            incoming_hits_for_sheet=None,
            runes=runes,
            shards=shards,
            rune_data=rune_data,
            constraints=OptimizeConstraints(slots=2),
        )
        items = load_items(ROOT, item_ids)
        fast_sheet = ev._make_sheet(items)

        # Reference full two-pass adaptive assembly
        before = build_stat_sheet(champ, 11, items, issues, {}, derived)
        bonus_ad = sum(
            (
                p.value
                for p in before["attack_damage"].contributions
                if p.scope == "bonus" and not p.adaptive
            ),
            start=Fraction(0),
        )
        power = sum(
            (p.value for p in before["ability_power"].contributions if not p.adaptive),
            start=Fraction(0),
        )
        weight = derived.value(champ.id, "adaptiveforceapweight") if derived else None
        adaptive, a_lbl, a_note = adaptive_stat(bonus_ad, power, weight)
        flats, percents = shard_contributions(
            shards,
            rune_data,
            level=11,
            patch=champ.patch,
            adaptive=adaptive,
            adaptive_label=a_lbl,
            adaptive_note=a_note,
        )
        uses_mana = champ.resource == MANA_RESOURCE.get(champ.locale)
        rfx = minor_rune_effects(
            runes,
            rune_data,
            level=11,
            patch=champ.patch,
            items=items,
            uses_mana=uses_mana,
            has_boots=False,
            adaptive=adaptive,
            adaptive_label=a_lbl,
            adaptive_note=a_note,
        )
        ref_sheet = build_stat_sheet(
            champ,
            11,
            items,
            issues,
            {},
            derived,
            (*flats, *rfx.flats),
            (*percents, *rfx.percents),
            tuple(rfx.pending),
            extra_amplifiers=rfx.amplifiers,
            move_speed_bonus_amp=rfx.move_speed_bonus_amp,
        )
        for stat_id in ("attack_damage", "ability_power", "health", "armor", "magic_resist"):
            assert fast_sheet[stat_id].total() == ref_sheet[stat_id].total()
            assert fast_sheet[stat_id].label is ref_sheet[stat_id].label
