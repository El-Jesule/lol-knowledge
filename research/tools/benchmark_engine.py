"""Measure cold and warm wall-clock baselines for the LoL-Knowledge engine.

Records ``wall_ms``, ``states_evaluated`` and ``ms/state`` across ``stats``,
``rotation`` (with ``--timeline`` and ``--window``), ``survive``, ``duel``,
and ``optimize`` (``rotation_damage``, ``effective_health_mixed``, ``duel``).

Usage::

    .\\.venv\\Scripts\\python.exe research\\tools\\benchmark_engine.py
    .\\.venv\\Scripts\\python.exe research\\tools\\benchmark_engine.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from lol_knowledge.defense import evaluate_defense, hits_from_rotation  # noqa: E402
from lol_knowledge.duel import DuelFighterSpec, evaluate_duel  # noqa: E402
from lol_knowledge.kit import load_kit  # noqa: E402
from lol_knowledge.objects.legality import load_item_groups  # noqa: E402
from lol_knowledge.optimizer import OptimizeConstraints, optimize_build  # noqa: E402
from lol_knowledge.passives import sheet_passive_effects  # noqa: E402
from lol_knowledge.rotation import CritBase, evaluate_rotation, parse_steps  # noqa: E402
from lol_knowledge.runes import load_runes  # noqa: E402
from lol_knowledge.scenario import target_from_sheet, target_from_values  # noqa: E402
from lol_knowledge.stats import (  # noqa: E402
    Label,
    build_stat_sheet,
    load_champion,
    load_issues,
    load_items,
    load_records,
)


@dataclass(frozen=True)
class BenchmarkRow:
    """Measured timing metrics for one scenario and mode."""

    scenario: str
    mode: str
    wall_ms: float
    states_evaluated: int
    ms_per_state: float


def _time_call(fn: Callable[[], int], *, repeats: int = 1) -> tuple[float, int]:
    t0 = time.perf_counter()
    states = 0
    for _ in range(repeats):
        states = fn()
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return elapsed_ms / repeats, states


def run_benchmarks(root: Path = ROOT, *, warm_repeats: int = 3) -> list[BenchmarkRow]:
    """Run cold (fresh data loading) and warm (in-memory inputs) benchmarks."""
    rows: list[BenchmarkRow] = []
    crit = CritBase(Fraction(2), Label.DERIVED, "client record")

    # 1. Cold & warm stats (with global conversion + passive)
    def cold_stats() -> int:
        ch = load_champion(root, "Vladimir")
        items = load_items(root, ["3089", "3152", "3065"])
        issues = load_issues(root)
        records = load_records(root)
        kit = load_kit(root, "Vladimir")
        pfx = sheet_passive_effects(kit, 11, None, include_stacking=True)
        build_stat_sheet(
            ch,
            11,
            items,
            issues,
            {},
            records,
            pfx.flats,
            pfx.percents,
            extra_amplifiers=pfx.amplifiers,
            extra_notes=pfx.notes,
        )
        return 1

    vlad_ch = load_champion(root, "Vladimir")
    vlad_items = load_items(root, ["3089", "3152", "3065"])
    issues = load_issues(root)
    records = load_records(root)
    vlad_kit = load_kit(root, "Vladimir")
    vlad_pfx = sheet_passive_effects(vlad_kit, 11, None, include_stacking=True)

    def warm_stats() -> int:
        build_stat_sheet(
            vlad_ch,
            11,
            vlad_items,
            issues,
            {},
            records,
            vlad_pfx.flats,
            vlad_pfx.percents,
            extra_amplifiers=vlad_pfx.amplifiers,
            extra_notes=vlad_pfx.notes,
        )
        return 1

    for mode, fn, rep in (("cold", cold_stats, 1), ("warm", warm_stats, warm_repeats)):
        ms, states = _time_call(fn, repeats=rep)
        rows.append(
            BenchmarkRow("stats_vladimir", mode, round(ms, 3), states, round(ms / states, 3))
        )

    # 2. Cold & warm rotation (--timeline --window)
    def cold_rotation() -> int:
        ch = load_champion(root, "Ahri")
        items = load_items(root, ["6653", "2503", "3020"])
        kit = load_kit(root, "Ahri")
        runes = load_runes(root)
        t_ch = load_champion(root, "Garen")
        t_items = load_items(root, ["3111"])
        sh = build_stat_sheet(ch, 11, items, issues, {}, records)
        t_sh = build_stat_sheet(t_ch, 11, t_items, issues, {}, records)
        out = evaluate_rotation(
            kit,
            sh,
            {"Q": 5, "W": 3, "E": 1, "R": 2},
            target_from_sheet(t_sh),
            parse_steps("E, Q.both, W.all, R.dash, wait:6, Q.both"),
            crit,
            holder_range="ranged",
            timeline=True,
            runes=[8112, 8143, 8137, 8106, 8226, 8210],
            rune_data=runes,
        )
        out.window(2)
        out.window(5)
        return 1

    ahri_ch = load_champion(root, "Ahri")
    ahri_kit = load_kit(root, "Ahri")
    rune_data = load_runes(root)
    ahri_sh = build_stat_sheet(
        ahri_ch, 11, load_items(root, ["6653", "2503", "3020"]), issues, {}, records
    )
    garen_ch = load_champion(root, "Garen")
    garen_kit = load_kit(root, "Garen")
    garen_sh = build_stat_sheet(garen_ch, 11, load_items(root, ["3111"]), issues, {}, records)
    ahri_target = target_from_sheet(garen_sh)
    ahri_steps = parse_steps("E, Q.both, W.all, R.dash, wait:6, Q.both")

    def warm_rotation() -> int:
        out = evaluate_rotation(
            ahri_kit,
            ahri_sh,
            {"Q": 5, "W": 3, "E": 1, "R": 2},
            ahri_target,
            ahri_steps,
            crit,
            holder_range="ranged",
            timeline=True,
            runes=[8112, 8143, 8137, 8106, 8226, 8210],
            rune_data=rune_data,
        )
        out.window(2)
        out.window(5)
        return 1

    for mode, fn, rep in (("cold", cold_rotation, 1), ("warm", warm_rotation, warm_repeats)):
        ms, states = _time_call(fn, repeats=rep)
        rows.append(
            BenchmarkRow(
                "rotation_timeline_window", mode, round(ms, 3), states, round(ms / states, 3)
            )
        )

    # 3. Cold & warm survive
    rot_for_surv = evaluate_rotation(
        ahri_kit,
        ahri_sh,
        {"Q": 5, "W": 3, "E": 1, "R": 2},
        ahri_target,
        ahri_steps,
        crit,
        holder_range="ranged",
        timeline=True,
    )
    surv_hits = hits_from_rotation(rot_for_surv)
    dar_ch = load_champion(root, "Darius")
    dar_kit = load_kit(root, "Darius")
    dar_sh = build_stat_sheet(
        dar_ch, 11, load_items(root, ["3053", "3075", "3111"]), issues, {}, records
    )
    dar_runes = [8010, 9111, 9105, 8299, 8473, 8444]

    def cold_survive() -> int:
        ch = load_champion(root, "Darius")
        kit = load_kit(root, "Darius")
        runes = load_runes(root)
        sh = build_stat_sheet(
            ch, 11, load_items(root, ["3053", "3075", "3111"]), issues, {}, records
        )
        evaluate_defense(sh, surv_hits, runes=dar_runes, rune_data=runes, timeline=True, kit=kit)
        return 1

    def warm_survive() -> int:
        evaluate_defense(
            dar_sh, surv_hits, runes=dar_runes, rune_data=rune_data, timeline=True, kit=dar_kit
        )
        return 1

    for mode, fn, rep in (("cold", cold_survive, 1), ("warm", warm_survive, warm_repeats)):
        ms, states = _time_call(fn, repeats=rep)
        rows.append(
            BenchmarkRow("survive_timeline", mode, round(ms, 3), states, round(ms / states, 3))
        )

    # 4. Cold & warm duel
    dar_duel_sh = build_stat_sheet(
        dar_ch, 11, load_items(root, ["3078", "3111"]), issues, {}, records
    )
    gar_duel_sh = build_stat_sheet(
        garen_ch, 11, load_items(root, ["3078", "3111"]), issues, {}, records
    )
    dar_steps = parse_steps("attack, W, Q.blade, R.base")
    gar_steps = parse_steps("Q, E.tick, R")

    def cold_duel() -> int:
        c_a = load_champion(root, "Darius")
        c_b = load_champion(root, "Garen")
        k_a = load_kit(root, "Darius")
        k_b = load_kit(root, "Garen")
        s_a = build_stat_sheet(c_a, 11, load_items(root, ["3078", "3111"]), issues, {}, records)
        s_b = build_stat_sheet(c_b, 11, load_items(root, ["3078", "3111"]), issues, {}, records)
        evaluate_duel(
            DuelFighterSpec(
                s_a, k_a, {"Q": 5, "W": 1, "E": 3, "R": 2}, crit, dar_steps, holder_range="melee"
            ),
            DuelFighterSpec(
                s_b, k_b, {"Q": 5, "W": 1, "E": 3, "R": 2}, crit, gar_steps, holder_range="melee"
            ),
        )
        return 1

    def warm_duel() -> int:
        evaluate_duel(
            DuelFighterSpec(
                dar_duel_sh,
                dar_kit,
                {"Q": 5, "W": 1, "E": 3, "R": 2},
                crit,
                dar_steps,
                holder_range="melee",
            ),
            DuelFighterSpec(
                gar_duel_sh,
                garen_kit,
                {"Q": 5, "W": 1, "E": 3, "R": 2},
                crit,
                gar_steps,
                holder_range="melee",
            ),
        )
        return 1

    for mode, fn, rep in (("cold", cold_duel, 1), ("warm", warm_duel, warm_repeats)):
        ms, states = _time_call(fn, repeats=rep)
        rows.append(BenchmarkRow("duel_1v1", mode, round(ms, 3), states, round(ms / states, 3)))

    # 5. Cold & warm optimize (rotation_damage, effective_health_mixed, duel)
    tgt_manual = target_from_values(
        Fraction(80),
        Fraction(60),
        max_health=Fraction(2000),
        kind="champion",
        bonus_health=Fraction(300),
    )
    opt_steps = parse_steps("E, Q.both, W.all, R.dash")
    _ = load_item_groups(root)

    def run_opt_rot() -> int:
        res = optimize_build(
            root,
            ahri_ch,
            11,
            "rotation_damage",
            constraints=OptimizeConstraints(slots=2, beam_width=4, pool_limit=8, top=3),
            issues=issues,
            derived=records,
            kit=ahri_kit,
            ranks={"Q": 5, "W": 3, "E": 1, "R": 2},
            target=tgt_manual,
            steps=opt_steps,
            crit_base=crit,
            holder_range="ranged",
        )
        return max(1, res.stats.states_evaluated)

    def run_opt_ehp() -> int:
        res = optimize_build(
            root,
            dar_ch,
            11,
            "effective_health_mixed",
            constraints=OptimizeConstraints(slots=2, beam_width=4, pool_limit=8, top=3),
            issues=issues,
            derived=records,
            kit=dar_kit,
            ranks={"Q": 5, "W": 1, "E": 3, "R": 2},
            target=tgt_manual,
            holder_range="melee",
        )
        return max(1, res.stats.states_evaluated)

    def run_opt_duel() -> int:
        res = optimize_build(
            root,
            dar_ch,
            11,
            "duel",
            constraints=OptimizeConstraints(slots=1, beam_width=4, pool_limit=8, top=3),
            issues=issues,
            derived=records,
            kit=dar_kit,
            ranks={"Q": 5, "W": 1, "E": 3, "R": 2},
            steps=dar_steps,
            crit_base=crit,
            holder_range="melee",
            duel_enemy=DuelFighterSpec(
                ahri_sh,
                ahri_kit,
                {"Q": 5, "W": 3, "E": 1, "R": 2},
                crit,
                parse_steps("E, Q.both, W.all"),
                holder_range="ranged",
            ),
            duel_max_duration=Fraction(15),
        )
        return max(1, res.stats.states_evaluated)

    for label, fn in (
        ("optimize_rotation_damage", run_opt_rot),
        ("optimize_effective_health", run_opt_ehp),
        ("optimize_duel", run_opt_duel),
    ):
        ms_c, states_c = _time_call(fn, repeats=1)
        rows.append(
            BenchmarkRow(label, "cold", round(ms_c, 3), states_c, round(ms_c / states_c, 4))
        )
        ms_w, states_w = _time_call(fn, repeats=1)
        rows.append(
            BenchmarkRow(label, "warm", round(ms_w, 3), states_w, round(ms_w / states_w, 4))
        )

    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark LoL-Knowledge engine baselines.")
    parser.add_argument("--json", action="store_true", help="Emit JSON rows instead of text table.")
    args = parser.parse_args(argv)
    rows = run_benchmarks()
    if args.json:
        payload = [
            {
                "scenario": r.scenario,
                "mode": r.mode,
                "wall_ms": r.wall_ms,
                "states_evaluated": r.states_evaluated,
                "ms_per_state": r.ms_per_state,
            }
            for r in rows
        ]
        print(json.dumps(payload, indent=2))
        return 0
    print(f"{'scenario':28s} {'mode':6s} {'wall_ms':>10s} {'states':>8s} {'ms/state':>10s}")
    print("-" * 68)
    for r in rows:
        print(
            f"{r.scenario:28s} {r.mode:6s} "
            f"{r.wall_ms:10.3f} {r.states_evaluated:8d} {r.ms_per_state:10.4f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
