"""Exact equivalence golden snapshots across stats, rotation, survive, duel, and optimize.

Captured directly on unmodified v1.0.0 before modularization so any refactor
drift in exact ``Fraction`` arithmetic, labels, notes, or build rankings fails
immediately.
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

from lol_knowledge.defense import evaluate_defense, hits_from_rotation, parse_incoming
from lol_knowledge.duel import DuelFighterSpec, evaluate_duel
from lol_knowledge.kit import load_kit
from lol_knowledge.objects.legality import load_item_groups
from lol_knowledge.optimizer import OptimizeConstraints, optimize_build
from lol_knowledge.passives import sheet_passive_effects
from lol_knowledge.rotation import CritBase, evaluate_rotation, parse_steps
from lol_knowledge.runes import (
    adaptive_stat,
    load_runes,
    minor_rune_effects,
    needs_adaptive_stat,
    shard_contributions,
)
from lol_knowledge.scenario import target_from_sheet, target_from_values
from lol_knowledge.stats import (
    Label,
    StatBlocked,
    build_stat_sheet,
    load_champion,
    load_issues,
    load_items,
    load_records,
)
from lol_knowledge.stats.sheet import MANA_RESOURCE
from lol_knowledge.summoners import load_summoner_spells

ROOT = Path(__file__).resolve().parents[1]
ISSUES = load_issues(ROOT)
RECORDS = load_records(ROOT)
RUNE_DATA = load_runes(ROOT)
SUMMONER_DATA = load_summoner_spells(ROOT)
ITEM_GROUPS = load_item_groups(ROOT)
CRIT_BASE = CritBase(Fraction(2), Label.DERIVED, "client record")


def _build_sheet(
    champion_id: str,
    level: int,
    item_ids: list[str],
    *,
    inputs: dict[str, Fraction] | None = None,
    include_stacking: bool = True,
    runes: list[int] | tuple[int, ...] = (),
    shards: list[int] | tuple[int, ...] = (),
):
    champion = load_champion(ROOT, champion_id)
    items = load_items(ROOT, item_ids)
    kit = load_kit(ROOT, champion_id)
    pfx = sheet_passive_effects(kit, level, inputs, include_stacking=include_stacking)
    extras = list(pfx.flats)
    percents = list(pfx.percents)
    notes = list(pfx.notes)
    amps = list(pfx.amplifiers)
    ms_amp = None
    if runes or shards:
        assert RUNE_DATA is not None
        adaptive, a_label, a_note = None, Label.DERIVED, ""
        if needs_adaptive_stat(runes, shards, RUNE_DATA):
            before = build_stat_sheet(
                champion, level, items, ISSUES, {}, RECORDS, (), inputs=inputs
            )
            bonus_ad = sum(
                (
                    p.value
                    for p in before["attack_damage"].contributions
                    if p.scope == "bonus" and not p.adaptive
                ),
                Fraction(0),
            )
            power = sum(
                (p.value for p in before["ability_power"].contributions if not p.adaptive),
                Fraction(0),
            )
            weight = RECORDS.value(champion_id, "adaptiveforceapweight")
            adaptive, a_label, a_note = adaptive_stat(bonus_ad, power, weight)
        flats, shard_percents = shard_contributions(
            shards,
            RUNE_DATA,
            level=level,
            patch=champion.patch,
            adaptive=adaptive,
            adaptive_label=a_label,
            adaptive_note=a_note,
        )
        has_boots = ITEM_GROUPS.has_boots(item_ids) if (items and ITEM_GROUPS) else False
        uses_mana = champion.resource == MANA_RESOURCE.get(champion.locale)
        rune_fx = minor_rune_effects(
            runes,
            RUNE_DATA,
            level=level,
            patch=champion.patch,
            items=items,
            uses_mana=uses_mana,
            has_boots=has_boots,
            inputs=inputs,
            adaptive=adaptive,
            adaptive_label=a_label,
            adaptive_note=a_note,
        )
        extras.extend(flats)
        extras.extend(rune_fx.flats)
        percents = [*shard_percents, *percents, *rune_fx.percents]
        notes.extend(rune_fx.notes)
        amps.extend(rune_fx.amplifiers)
        ms_amp = rune_fx.move_speed_bonus_amp
    sheet = build_stat_sheet(
        champion,
        level,
        items,
        ISSUES,
        {},
        RECORDS,
        extras,
        percents,
        extra_amplifiers=amps,
        extra_notes=notes,
        move_speed_bonus_amp=ms_amp,
        inputs=inputs,
    )
    return kit, sheet


def test_stats_global_conversions_equivalence() -> None:
    expected: dict[
        str, tuple[int, list[str], dict[str, Fraction], dict[str, tuple[Fraction, Label]]]
    ] = {
        "Zeri": (
            11,
            ["3031", "3046", "3006"],
            {},
            {
                "health": (Fraction(6261, 4), Label.DERIVED),
                "attack_damage": (Fraction(2971, 20), Label.DERIVED),
                "attack_speed": (Fraction(21783, 16000), Label.DERIVED),
                "move_speed": (Fraction(825, 2), Label.OFFICIAL),
            },
        ),
        "Jhin": (
            11,
            ["3031", "3094", "3009"],
            {},
            {
                "health": (Fraction(63757, 40), Label.DERIVED),
                "attack_damage": (Fraction(157149, 625), Label.DERIVED),
                "attack_speed": (Fraction(5053, 6400), Label.DERIVED),
                "move_speed": (Fraction(2002, 5), Label.OFFICIAL),
            },
        ),
        "Vladimir": (
            11,
            ["3089", "3152", "3065"],
            {},
            {
                "health": (Fraction(54449, 20), Label.DERIVED),
                "ability_power": (Fraction(559, 2), Label.DERIVED),
                "magic_resist": (Fraction(36563, 400), Label.DERIVED),
            },
        ),
        "Pyke": (
            11,
            ["3142", "3814", "3009"],
            {},
            {
                "health": (Fraction(6541, 4), Label.DERIVED),
                "attack_damage": (Fraction(28337, 140), Label.DERIVED),
                "move_speed": (Fraction(2002, 5), Label.OFFICIAL),
            },
        ),
        "Ryze": (
            11,
            ["3089", "3040", "6657"],
            {},
            {
                "health": (Fraction(20581, 10), Label.DERIVED),
                "ability_power": (Fraction(715, 2), Label.DERIVED),
                "mana": (Fraction(5243751, 1600), Label.DERIVED),
            },
        ),
        "Ornn": (
            11,
            ["3068", "3075", "3111"],
            {"ornn_masterworks": Fraction(2)},
            {
                "health": (Fraction(88259, 40), Label.DERIVED),
                "armor": (Fraction(22613, 100), Label.DERIVED),
                "magic_resist": (Fraction(58871, 800), Label.DERIVED),
            },
        ),
        "Cassiopeia": (
            16,
            ["3040", "6653"],
            {},
            {
                "health": (Fraction(46571, 20), Label.DERIVED),
                "ability_power": (Fraction(150, 1), Label.DERIVED),
                "move_speed": (Fraction(335, 1), Label.OFFICIAL),
                "mana": (Fraction(2029, 1), Label.DERIVED),
            },
        ),
        "Hecarim": (
            11,
            ["3078", "3742", "3009"],
            {},
            {
                "attack_damage": (Fraction(294423, 2000), Label.DERIVED),
                "armor": (Fraction(107859, 800), Label.DERIVED),
                "move_speed": (Fraction(2079, 5), Label.DERIVED),
            },
        ),
    }
    for cid, (lvl, item_ids, inp, checks) in expected.items():
        _, sheet = _build_sheet(cid, lvl, item_ids, inputs=inp)
        for stat_id, (val, lbl) in checks.items():
            try:
                got = sheet[stat_id].total()
            except StatBlocked:  # pragma: no cover - defensive
                raise AssertionError(f"{cid}.{stat_id} unexpectedly blocked") from None
            assert got == val, f"{cid}.{stat_id}: {got!r} != {val!r}"
            assert sheet[stat_id].label is lbl, f"{cid}.{stat_id} label mismatch"


def test_rotation_timeline_windows_equivalence() -> None:
    _, tgt_sh = _build_sheet("Garen", 11, ["3111"])
    tgt = target_from_sheet(tgt_sh)

    ahri_runes = [8112, 8143, 8137, 8106, 8226, 8210]
    ahri_shards = [5008, 5008, 5001]
    ahri_kit, ahri_sh = _build_sheet(
        "Ahri",
        11,
        ["6653", "2503", "3020"],
        include_stacking=False,
        runes=ahri_runes,
        shards=ahri_shards,
    )
    rot_ahri = evaluate_rotation(
        ahri_kit,
        ahri_sh,
        {"Q": 5, "W": 3, "E": 1, "R": 2},
        tgt,
        parse_steps("E, Q.both, W.all, R.dash, wait:6, Q.both"),
        CRIT_BASE,
        holder_range="ranged",
        timeline=True,
        runes=ahri_runes,
        rune_data=RUNE_DATA,
    )
    assert rot_ahri.total == Fraction(4603333788, 3072025)
    assert rot_ahri.primary_total == Fraction(4603333788, 3072025)
    assert rot_ahri.secondary_total == Fraction(0, 1)
    assert rot_ahri.remaining_health == Fraction(632605443, 12288100)
    assert rot_ahri.healing == Fraction(0, 1)
    assert rot_ahri.label is Label.PENDING
    assert rot_ahri.notes == (
        "rune 8143 Impacto repentino: needs --input sudden_impact=0|1 "
        "(lol-knowledge/mechanics/runes.md)",
        "kit:Ahri W.w_movementspeed (W (VM)): move_speed buff active for 2 s",
        "timeline: abilities are instant and attacks land when they start; cast times, "
        "attack windups and projectile travel are not modelled (no data)",
        "timeline: a burn deals its damage per second continuously from the step that "
        "applies it until it ends; applying it again restarts its duration, and damage "
        "after the last step is counted (burns.md)",
        "timeline: a timed effect starts after the damage of the step that triggers it "
        "and lasts its duration; triggering it again restarts it (timeline.md)",
        "P: Ampliar la ventana de la R y sumar una reactivación al derribar a un campeón "
        "(PDurationExtension)",
    )
    w2 = rot_ahri.window(2)
    assert w2.total == Fraction(2852662469, 3072025)
    assert w2.damage_per_second == Fraction(2852662469, 6144050)
    assert w2.healing == Fraction(0, 1)
    assert w2.remaining_health == Fraction(7635290719, 12288100)
    w5 = rot_ahri.window(5)
    assert w5.total == Fraction(2967479549, 3072025)
    assert w5.damage_per_second == Fraction(2967479549, 15360125)
    assert w5.healing == Fraction(0, 1)
    assert w5.remaining_health == Fraction(7176022399, 12288100)

    zaa_runes = [8010, 9111, 9104, 8014, 8473, 8451]
    zaa_shards = [5005, 5008, 5001]
    zaa_kit, zaa_sh = _build_sheet(
        "Zaahen",
        16,
        ["3124", "6672", "3078"],
        include_stacking=False,
        runes=zaa_runes,
        shards=zaa_shards,
    )
    rot_zaa = evaluate_rotation(
        zaa_kit,
        zaa_sh,
        {"Q": 5, "W": 1, "E": 5, "R": 3},
        tgt,
        parse_steps("attack, Q.first_hit, attack, E.edge, attack, attack, R, attack"),
        CRIT_BASE,
        holder_range="melee",
        timeline=True,
        runes=zaa_runes,
        rune_data=RUNE_DATA,
    )
    assert rot_zaa.total == Fraction(5760802569663488347837, 2790261321767869155)
    assert rot_zaa.remaining_health == Fraction(0, 1)
    assert rot_zaa.healing == Fraction(59883087103943249, 105014509156000)
    assert rot_zaa.total_shield_granted == Fraction(0, 1)
    assert rot_zaa.label is Label.PENDING
    assert rot_zaa.notes == (
        "rune 9111 Triunfo: bonus gold is not modelled",
        "kit:Zaahen R.r_cast_dr (R (DR durante lanzamiento)): "
        "defensive damage reduction for 0.75 s (use survive)",
        "3124 phantom-hit: no stack window declared; its count does not expire",
        "timeline: a counter's stacks expire when an attack comes its window or later "
        "after the previous one; every attack renews them (timeline.md)",
        "timeline: the time to the next attack uses the attack speed just after each "
        "attack; whether the game recomputes it when the attack speed changes before "
        "the next attack is not verified",
        "timeline: abilities are instant and attacks land when they start; cast times, "
        "attack windups and projectile travel are not modelled (no data)",
        "timeline: a timed effect starts after the damage of the step that triggers it "
        "and lasts its duration; triggering it again restarts it (timeline.md)",
        "P: Revivir (RevivePercentCalc, ReviveCooldownCalc): faltan valores en el bin",
    )
    w3 = rot_zaa.window(3)
    assert w3.total == Fraction(5760802569663488347837, 2790261321767869155)
    assert w3.damage_per_second == Fraction(5760802569663488347837, 8370783965303607465)
    assert w3.healing == Fraction(59883087103943249, 105014509156000)
    assert w3.remaining_health == Fraction(0, 1)


def test_survive_and_duel_equivalence() -> None:
    zaa_runes = [8010, 9111, 9104, 8014, 8473, 8451]
    zaa_shards = [5005, 5008, 5001]
    zaa_kit, zaa_sh = _build_sheet(
        "Zaahen",
        16,
        ["3124", "6672", "3078"],
        include_stacking=False,
        runes=zaa_runes,
        shards=zaa_shards,
    )
    dar_runes = [8010, 9111, 9105, 8299, 8473, 8444]
    dar_shards = [5005, 5008, 5001]
    dar_kit, dar_sh = _build_sheet(
        "Darius",
        11,
        ["3053", "3075", "3111"],
        include_stacking=False,
        runes=dar_runes,
        shards=dar_shards,
    )
    rot_vs_dar = evaluate_rotation(
        zaa_kit,
        zaa_sh,
        {"Q": 5, "W": 1, "E": 5, "R": 3},
        target_from_sheet(dar_sh),
        parse_steps("attack, Q.first_hit, attack, E.edge, attack, R, attack, attack"),
        CRIT_BASE,
        holder_range="melee",
        timeline=True,
        runes=zaa_runes,
        rune_data=RUNE_DATA,
    )
    surv = evaluate_defense(
        dar_sh,
        hits_from_rotation(rot_vs_dar),
        start_health=Fraction(1200),
        runes=dar_runes,
        rune_data=RUNE_DATA,
        timeline=True,
        kit=dar_kit,
    )
    assert surv.total_damage_taken == Fraction(3115165835048220663835867, 2412761745661091840914)
    assert surv.total_shield_granted == Fraction(396, 1)
    assert surv.total_shield_absorbed == Fraction(396, 1)
    assert surv.total_healing == Fraction(
        42615830194430127423652387521631013194606147,
        452288675119772156057862445170541992187500,
    )
    assert surv.total_reactive_damage == Fraction(275, 2)
    assert surv.remaining_health == Fraction(
        180509434630188702690971719674442407237574897,
        452288675119772156057862445170541992187500,
    )
    assert surv.survived is True
    assert surv.label is Label.DERIVED

    ahri_kit, ahri_sh = _build_sheet("Ahri", 11, ["6653", "3157", "3020"], include_stacking=False)
    dar2_kit, dar2_sh = _build_sheet("Darius", 11, ["3078", "3026", "3111"], include_stacking=False)
    spec_a = DuelFighterSpec(
        dar2_sh,
        dar2_kit,
        {"Q": 5, "W": 1, "E": 3, "R": 2},
        CRIT_BASE,
        parse_steps("attack, summoner:cleanse, W, Q.blade, R.base"),
        holder_range="melee",
        summoners=["SummonerBoost"],
        summoner_data=SUMMONER_DATA,
    )
    spec_b = DuelFighterSpec(
        ahri_sh,
        ahri_kit,
        {"Q": 5, "W": 3, "E": 1, "R": 2},
        CRIT_BASE,
        parse_steps("E, Q.both, W.all, R.dash"),
        holder_range="ranged",
    )
    duel_out = evaluate_duel(spec_a, spec_b)
    assert duel_out.winner == "A"
    assert duel_out.duration == Fraction(51200, 5551)
    assert duel_out.fighter_a.remaining_health == Fraction(109658670110797, 115081533320)
    assert duel_out.fighter_b.remaining_health == Fraction(0, 1)
    assert duel_out.fighter_a.damage_dealt == Fraction(316317883, 166284)
    assert duel_out.fighter_b.damage_dealt == Fraction(32937138212543, 28770383330)
    assert duel_out.fighter_a.actions_taken == 13
    assert duel_out.fighter_b.actions_taken == 12
    assert duel_out.label is Label.DERIVED


def test_optimize_objectives_equivalence() -> None:
    ahri_ch = load_champion(ROOT, "Ahri")
    ahri_kit = load_kit(ROOT, "Ahri")
    _, ahri_sh = _build_sheet("Ahri", 11, ["6653", "3157", "3020"], include_stacking=False)
    dar_ch = load_champion(ROOT, "Darius")
    dar_kit = load_kit(ROOT, "Darius")
    tgt = target_from_values(
        Fraction(80),
        Fraction(60),
        max_health=Fraction(2000),
        kind="champion",
        bonus_health=Fraction(300),
    )

    res_rot = optimize_build(
        ROOT,
        ahri_ch,
        11,
        "rotation_damage",
        constraints=OptimizeConstraints(
            slots=2,
            beam_width=4,
            pool_limit=8,
            top=3,
            ornn_upgrade=True,
            purchase_curve=True,
            gold_checkpoints=(3500, 7000),
        ),
        issues=ISSUES,
        derived=RECORDS,
        kit=ahri_kit,
        ranks={"Q": 5, "W": 3, "E": 1, "R": 2},
        target=tgt,
        steps=parse_steps("E, Q.both, W.all, R.dash"),
        crit_base=CRIT_BASE,
        holder_range="ranged",
    )
    top_rot = res_rot.verified_builds[0]
    assert top_rot.items == ("3089", "4646")
    assert top_rot.score == Fraction(388749, 290)
    assert top_rot.ornn_upgraded_item == "3089"
    assert top_rot.label is Label.DERIVED
    assert [(s.item_id, s.score) for s in res_rot.purchase_curve] == [
        ("3089", Fraction(36337, 40)),
        ("4646", Fraction(388749, 290)),
    ]
    assert [
        (c.gold_budget, c.build.items if c.build else None, c.build.score if c.build else None)
        for c in res_rot.gold_checkpoints
    ] == [
        (3500, ("3089",), Fraction(36337, 40)),
        (7000, ("3089", "4646"), Fraction(388749, 290)),
    ]

    res_dps = optimize_build(
        ROOT,
        ahri_ch,
        11,
        "dps",
        constraints=OptimizeConstraints(slots=2, beam_width=4, pool_limit=8, top=3),
        issues=ISSUES,
        derived=RECORDS,
        kit=ahri_kit,
        ranks={"Q": 5, "W": 3, "E": 1, "R": 2},
        target=tgt,
        steps=parse_steps("E, Q.both, W.all, R.dash, attack, attack"),
        crit_base=CRIT_BASE,
        holder_range="ranged",
        timeline=True,
    )
    assert res_dps.verified_builds[0].items == ("3089", "3115")
    assert res_dps.verified_builds[0].score == Fraction(3631137613, 2880000)
    assert res_dps.all_builds[0].items == ("2512", "3115")
    assert res_dps.all_builds[0].score == Fraction(2516397931, 1920000)

    res_ehp = optimize_build(
        ROOT,
        dar_ch,
        11,
        "effective_health_mixed",
        constraints=OptimizeConstraints(slots=2, beam_width=4, pool_limit=8, top=3),
        issues=ISSUES,
        derived=RECORDS,
        kit=dar_kit,
        ranks={"Q": 5, "W": 1, "E": 3, "R": 2},
        target=tgt,
        holder_range="melee",
    )
    assert res_ehp.verified_builds[0].items == ("2504", "3083")
    assert res_ehp.verified_builds[0].score == Fraction(216422181158631, 33009500000)
    assert res_ehp.all_builds[0].items == ("3083", "6665")
    assert res_ehp.all_builds[0].score == Fraction(224720943618171, 33809500000)

    res_ttd = optimize_build(
        ROOT,
        dar_ch,
        11,
        "time_to_die",
        constraints=OptimizeConstraints(slots=2, beam_width=4, pool_limit=8, top=3),
        issues=ISSUES,
        derived=RECORDS,
        kit=dar_kit,
        ranks={"Q": 5, "W": 1, "E": 3, "R": 2},
        incoming_hits=parse_incoming("attack:300, magic:250, wait:1, attack:crit:400, true:150"),
        timeline=True,
        holder_range="melee",
    )
    assert res_ttd.verified_builds[0].items == ("3083", "3084")
    assert res_ttd.verified_builds[0].score == Fraction(19286674675033, 6261130380)

    res_duel = optimize_build(
        ROOT,
        dar_ch,
        11,
        "duel",
        constraints=OptimizeConstraints(slots=1, beam_width=4, pool_limit=8, top=3),
        issues=ISSUES,
        derived=RECORDS,
        kit=dar_kit,
        ranks={"Q": 5, "W": 1, "E": 3, "R": 2},
        steps=parse_steps("attack, W, Q.blade, R.base"),
        crit_base=CRIT_BASE,
        holder_range="melee",
        duel_enemy=DuelFighterSpec(
            ahri_sh,
            ahri_kit,
            {"Q": 5, "W": 3, "E": 1, "R": 2},
            CRIT_BASE,
            parse_steps("E, Q.both, W.all"),
            holder_range="ranged",
        ),
        duel_max_duration=Fraction(15),
    )
    assert res_duel.verified_builds[0].items == ("3073",)
    assert res_duel.verified_builds[0].score == Fraction(
        348126551504304198120724520, 346941794109139374439
    )
