"""Tests for CH-02 kit spec draft generator and extended kitgen compiler."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from binmodel.cli import main as extract_main
from binmodel.kitgen import KitGenError, _Ability, compile_kit
from binmodel.specdraft import draft_spec, main

RESEARCH = Path(__file__).resolve().parents[1]
ROOT = RESEARCH.parent


@pytest.fixture(scope="module")
def zaahen_extract(tmp_path_factory):
    output = tmp_path_factory.mktemp("specdraft_z") / "extract.json"
    code = extract_main(
        ["--input", str(RESEARCH / "fixtures" / "zaahen_extract_min.json"), "--output", str(output)]
    )
    assert code == 0
    return json.loads(output.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def ahri_extract(tmp_path_factory):
    output = tmp_path_factory.mktemp("specdraft_a") / "extract.json"
    code = extract_main(
        [
            "--input",
            str(RESEARCH / "fixtures" / "ahri_extract_min.json"),
            "--output",
            str(output),
            "--game-version",
            "16.22",
            "--content-version",
            "16.22.8348910+branch.releases-16-22.content.release",
        ]
    )
    assert code == 0
    return json.loads(output.read_text(encoding="utf-8"))


def _tooltips(name: str) -> dict[str, str]:
    path = RESEARCH / "fixtures" / f"{name}_tooltips_es_es.json"
    return json.loads(path.read_text(encoding="utf-8"))["strings"]


def test_specdraft_ahri_detects_dual_damage_omitted_mstat_recast_and_heals(ahri_extract):
    dd = json.loads((ROOT / "data/current/champions/Ahri.json").read_text(encoding="utf-8"))
    tooltips = _tooltips("ahri")
    result = draft_spec(ahri_extract, tooltips, ddragon=dd)
    spec = result["spec"]
    findings = result["review"]["findings"]

    # 1. Dual damage type on Q TotalDamage (magic + true)
    dual = [f for f in findings if f["kind"] == "dual_damage_type"]
    assert len(dual) == 1
    assert dual[0]["slot"] == "Q" and dual[0]["reference"] == "TotalDamage"
    assert dual[0]["details"]["damage_types"] == ["magic", "true"]
    q_cases = spec["abilities"]["Q"]["cases"]
    assert {c["parts"][0]["damage_type"] for c in q_cases} == {"magic", "true"}

    # 2. Omitted mStat default (0 = ability_power) detected across AP spells
    omitted = [f for f in findings if f["kind"] == "omitted_mstat_default"]
    assert {"Q", "W", "E", "R"} <= {f["slot"] for f in omitted}

    # 3. Recast settings auto-detected on R
    r_spec = spec["abilities"]["R"]
    assert r_spec["recast_window_seconds"] == {"data_value": "RRecastWindow"}
    assert r_spec["recast_interval_seconds"] == {"data_value": "RDashCooldown"}

    # 4. Passive healing calculations detected and translatable
    heals = {
        f["reference"]: f["details"]["translatable"]
        for f in findings
        if f["kind"] == "healing_or_shield_calc" and f["slot"] == "P"
    }
    assert heals == {"ChampionHeal": True, "MinionHeal": True}

    # 5. The generated draft spec compiles immediately without manual edits!
    compiled = compile_kit(ahri_extract, tooltips, spec)
    assert compiled["champion"] == "Ahri"
    assert len(compiled["abilities"]["Q"]["cases"]) == 2


def test_specdraft_zaahen_detects_recast_pair_tooltip_dv_and_passive_candidates(zaahen_extract):
    dd = json.loads((ROOT / "data/current/champions/Zaahen.json").read_text(encoding="utf-8"))
    tooltips = _tooltips("zaahen")
    result = draft_spec(zaahen_extract, tooltips, ddragon=dd)
    spec = result["spec"]
    findings = result["review"]["findings"]

    # 1. Q SecondHitDamage detected as recast
    recasts = [f for f in findings if f["kind"] == "recast_detected" and f["slot"] == "Q"]
    assert any(f["reference"] == "SecondHitDamage" for f in recasts)
    q_cases = {c["id"]: c for c in spec["abilities"]["Q"]["cases"]}
    assert q_cases["second_hit_damage"].get("recast") is True

    # 2. E PercentHPDamage detected as tooltip-only DataValue damage
    dv_dmg = [f for f in findings if f["kind"] == "tooltip_data_value_damage"]
    assert any(f["slot"] == "E" and f["reference"] == "PercentHPDamage" for f in dv_dmg)

    # 3. Passive stat candidates detected on P and R
    candidates = {
        (f["slot"], f["reference"]) for f in findings if f["kind"] == "passive_stat_candidate"
    }
    assert ("R", "ArmorPen") in candidates
    assert ("P", "MaxStacks") in candidates
    assert ("P", "MaxStacksMultiplier") in candidates
    assert ("P", "FallOffDuration") in candidates

    # 4. PercentBonusADCalc ({ee18a47b}) and ReviveCooldownCalc (breakpoints) are now translatable!
    untranslatable_p = {
        f["reference"] for f in findings if f["kind"] == "untranslatable_node" and f["slot"] == "P"
    }
    assert "PercentBonusADCalc" not in untranslatable_p
    assert "ReviveCooldownCalc" not in untranslatable_p

    # 5. The generated draft spec compiles immediately without manual edits!
    compiled = compile_kit(zaahen_extract, tooltips, spec)
    assert compiled["champion"] == "Zaahen"
    assert len(compiled["abilities"]["Q"]["cases"]) == 2


def test_specdraft_detects_health_cost_and_uncorroborated_stat(zaahen_extract):
    # Modify a stat_scaled node to be inferred and supply DrMundo Data Dragon JSON
    modified = copy.deepcopy(zaahen_extract)
    for ability in modified["abilities"]:
        if ability["slot"] == "R":
            for calc in ability["calculations"]:
                for part in calc["tree"].get("parts", []):
                    if part.get("kind") == "stat_scaled":
                        part["stat"]["formula_confidence"] = "inferred"
    mundo_dd = json.loads(
        (ROOT / "data/current/champions/DrMundo.json").read_text(encoding="utf-8")
    )
    result = draft_spec(modified, _tooltips("zaahen"), ddragon=mundo_dd)
    findings = result["review"]["findings"]
    assert any(f["kind"] == "uncorroborated_stat" and f["slot"] == "R" for f in findings)
    assert any(f["kind"] == "health_cost_needed" and f["slot"] == "Q" for f in findings)


def test_kitgen_extended_nodes_linear_breakpoints_sum_product_and_passives(
    zaahen_extract, ahri_extract
):
    # Zaahen P: {ee18a47b} -> linear_by_level; breakpoints -> by_level (18 values)
    z_p = next(a for a in zaahen_extract["abilities"] if a["slot"] == "P")
    z_helper = _Ability(z_p)
    assert z_helper.calculation("PercentBonusADCalc") == {
        "op": "linear_by_level",
        "min": 0.015,
        "max": 0.028,
    }
    revive_cd = z_helper.calculation("ReviveCooldownCalc")
    assert revive_cd["op"] == "by_level" and len(revive_cd["values"]) == 18
    assert revive_cd["values"][0] == 300
    assert revive_cd["values"][5] == 240
    assert revive_cd["values"][10] == 180
    assert revive_cd["values"][15] == 120

    # Ahri P: ByCharLevelInterpolationCalculationPart + AP ratio
    a_p = next(a for a in ahri_extract["abilities"] if a["slot"] == "P")
    a_helper = _Ability(a_p)
    assert a_helper.calculation("ChampionHeal") == {
        "op": "add",
        "operands": [
            {"op": "linear_by_level", "min": 75, "max": 165},
            {
                "op": "mul",
                "operands": [
                    {"op": "constant", "value": 0.3},
                    {"op": "stat", "stat": "ability_power", "scope": "total"},
                ],
            },
        ],
    }

    # Synthetic sum, product, by_char_level_formula and game_calculation multiplier
    synth = _Ability(
        {
            "slot": "Q",
            "level_count": 5,
            "path": "Test/Q",
            "data_values": [],
            "calculations": [
                {
                    "name": "Combo",
                    "tree": {
                        "kind": "game_calculation",
                        "multiplier": {"kind": "number", "value": 1.5},
                        "parts": [
                            {
                                "kind": "sum",
                                "operands": [
                                    {"kind": "number", "value": 10},
                                    {
                                        "kind": "product",
                                        "operands": [
                                            {"kind": "number", "value": 2},
                                            {"kind": "number", "value": 3},
                                        ],
                                    },
                                ],
                            },
                            {"kind": "by_char_level_formula", "values": list(range(19))},
                        ],
                    },
                },
                {
                    "name": "BadInterp",
                    "tree": {
                        "kind": "by_char_level_interpolation",
                        "start_value": 10,
                        "end_value": 100,
                        "scale_by_stat_progression_multiplier": True,
                    },
                },
            ],
        }
    )
    combo = synth.calculation("Combo")
    assert combo["op"] == "mul" and combo["operands"][1] == {"op": "constant", "value": 1.5}
    assert combo["operands"][0]["operands"][1] == {"op": "by_level", "values": list(range(1, 19))}
    stat_prog = synth.calculation("BadInterp")
    assert stat_prog["op"] == "by_level"
    assert len(stat_prog["values"]) == 18
    assert stat_prog["values"][0] == 10
    assert stat_prog["values"][-1] == 100
    assert abs(stat_prog["values"][1] - (10 + 90 / 17 * 0.72)) < 1e-4


def test_specdraft_cli_writes_spec_and_review_and_rejects_missing_file(
    ahri_extract, tmp_path, capsys
):
    ext_path = tmp_path / "extract.json"
    ext_path.write_text(json.dumps(ahri_extract), encoding="utf-8")
    out_spec = tmp_path / "Ahri.draft.spec.json"
    out_review = tmp_path / "Ahri.review.json"
    code = main(
        [
            "--extract",
            str(ext_path),
            "--tooltips",
            str(RESEARCH / "fixtures" / "ahri_tooltips_es_es.json"),
            "--ddragon",
            str(ROOT / "data/current/champions/Ahri.json"),
            "--output",
            str(out_spec),
            "--review",
            str(out_review),
        ]
    )
    assert code == 0
    assert "specdraft: Ahri" in capsys.readouterr().out
    assert json.loads(out_spec.read_text(encoding="utf-8"))["champion"] == "Ahri"
    assert json.loads(out_review.read_text(encoding="utf-8"))["summary"]["total_findings"] > 0

    assert main(["--extract", str(tmp_path / "nope.json"), "--tooltips", str(ext_path)]) == 2
    assert capsys.readouterr().err.startswith("error:")


def test_find_champion_root_disambiguates_multiple_records():
    from binmodel.traverse import TraversalError, find_champion_root

    doc = {
        "Characters/Milio/CharacterRecords/Root": {
            "__type": "CharacterRecord",
            "mCharacterName": "Milio",
        },
        "Characters/Milio/CharacterRecords/Helper": {
            "__type": "CharacterRecord",
            "mCharacterName": "MilioHelper",
        },
    }
    path, root = find_champion_root(doc)
    assert path == "Characters/Milio/CharacterRecords/Root"
    assert root["mCharacterName"] == "Milio"

    ambiguous = {
        "Characters/A/Record1": {"__type": "CharacterRecord"},
        "Characters/A/Record2": {"__type": "CharacterRecord"},
    }
    with pytest.raises(TraversalError, match="found 2"):
        find_champion_root(ambiguous)


def test_kitgen_normalizes_bonus_ap_and_translates_named_breakpoints():
    ability = _Ability(
        {
            "slot": "E",
            "level_count": 5,
            "path": "Characters/Jax/Spells/JaxCounterStrike",
            "data_values": [
                {"name": "L1", "mode": "base", "ranks": [10, 10, 10, 10, 10]},
                {"name": "PerLvl", "mode": "base", "ranks": [2, 2, 2, 2, 2]},
                {"name": "Step6", "mode": "base", "ranks": [5, 5, 5, 5, 5]},
                {"name": "Rate11", "mode": "base", "ranks": [4, 4, 4, 4, 4]},
            ],
            "calculations": [
                {
                    "name": "BonusAPCalc",
                    "tree": {
                        "kind": "game_calculation",
                        "parts": [
                            {
                                "kind": "stat_scaled",
                                "stat": {
                                    "stat": "ability_power",
                                    "formula": "bonus",
                                    "resolved": True,
                                    "stat_confidence": "corroborated",
                                    "formula_confidence": "corroborated",
                                },
                                "factor": {"kind": "number", "value": 0.7},
                            }
                        ],
                    },
                },
                {
                    "name": "NamedBP",
                    "tree": {
                        "kind": "by_char_level_named_breakpoints",
                        "level1_data_value": "L1",
                        "bonus_per_level_data_value": "PerLvl",
                        "breakpoints": [
                            {"level": 6, "additional_bonus_data_value": "Step6"},
                            {"level": 11, "bonus_per_level_at_and_after_data_value": "Rate11"},
                        ],
                    },
                },
                {
                    "name": "MissingNumber",
                    "tree": {"kind": "number", "value": None},
                },
            ],
        }
    )
    assert ability.calculation("BonusAPCalc") == {
        "op": "mul",
        "operands": [
            {"op": "constant", "value": 0.7},
            {"op": "stat", "stat": "ability_power", "scope": "total"},
        ],
    }
    bp = ability.calculation("NamedBP")
    assert bp["op"] == "by_level" and len(bp["values"]) == 18
    assert bp["values"][0] == 10
    assert bp["values"][4] == 18  # level 5: 10 + 4*2
    assert bp["values"][5] == 25  # level 6: 18 + 2 + 5
    assert bp["values"][10] == 35  # level 11: 25 + 5*2, then rate becomes 4
    assert bp["values"][11] == 39  # level 12: 35 + 4
    with pytest.raises(KitGenError, match="missing numeric value"):
        ability.calculation("MissingNumber")


def test_specdraft_handles_missing_level_count_and_recast_coherence(ahri_extract):
    from lol_knowledge.kit.model import parse_kit

    tooltips = _tooltips("ahri")
    dd = json.loads((ROOT / "data/current/champions/Ahri.json").read_text(encoding="utf-8"))
    # Ahri R has recast settings and 1 calculation -> specdraft emits a draft recast case
    # so the compiled kit passes parse_kit without error!
    drafted = draft_spec(ahri_extract, {"strings": tooltips}, ddragon=dd)
    compiled = compile_kit(ahri_extract, {"strings": tooltips}, drafted["spec"])
    kit = parse_kit(compiled)
    assert any(case.recast for case in kit.abilities["R"].cases)

    # Missing level_count falls back to Data Dragon maxrank instead of crashing
    broken = copy.deepcopy(ahri_extract)
    for ability in broken["abilities"]:
        if ability["slot"] == "E":
            ability["level_count"] = None
    drafted2 = draft_spec(broken, tooltips, ddragon=dd)
    assert drafted2["spec"]["abilities"]["E"]["max_rank"] == 5
    assert any(
        f["kind"] == "missing_level_count" and f["slot"] == "E"
        for f in drafted2["review"]["findings"]
    )


def test_batch_kits_cli_rejects_bad_environment(tmp_path, capsys):
    from binmodel.batch_kits import main as batch_main

    code = batch_main(["--game", str(tmp_path), "--hashes", str(tmp_path), "--survey"])
    assert code == 2
    assert "content-metadata.json not found" in capsys.readouterr().err


def test_kitgen_custom_calculation_scaled_passive_stat_and_percent_guard(zaahen_extract):
    tooltips = _tooltips("zaahen")
    # Synthetic ability with display_as_percent=True damage calc and percentage-point passive stat
    extract_doc = {
        "champion": {"id": "TestChamp", "name": "TestChamp"},
        "game_version": "16.23",
        "content_version": "16.23.test",
        "abilities": [
            {
                "slot": "W",
                "name": "W",
                "path": "Characters/TestChamp/Spells/W",
                "level_count": 5,
                "tooltip": {"loc_keys": {"keyTooltip": "spell_test_w"}},
                "data_values": [
                    {"name": "PctPen", "mode": "base", "ranks": [20, 25, 30, 35, 40]},
                    {"name": "MaxHpPct", "mode": "base", "ranks": [0.04, 0.05, 0.06, 0.07, 0.08]},
                ],
                "calculations": [
                    {
                        "name": "PctDmg",
                        "tree": {
                            "kind": "game_calculation",
                            "display_as_percent": True,
                            "parts": [{"kind": "data_value", "name": "MaxHpPct"}],
                        },
                    }
                ],
            }
        ],
    }
    tt = {"spell_test_w": "Inflige <trueDamage>@PctDmg@ de vida máxima</trueDamage>."}
    drafted = draft_spec(extract_doc, tt)
    assert any(f["kind"] == "percent_damage_calc" for f in drafted["review"]["findings"])
    assert "cases" not in drafted["spec"]["abilities"]["W"]

    spec = {
        "champion": "TestChamp",
        "game_version": "16.23",
        "abilities": {
            "W": {
                "name": "W",
                "tooltip": "spell_test_w",
                "cases": [
                    {
                        "id": "proc",
                        "name": "Impacto",
                        "parts": [
                            {
                                "tooltip_reference": "PctDmg",
                                "source_note": "PctDmg × vida máxima del objetivo",
                                "formula": {
                                    "op": "mul",
                                    "operands": [
                                        {"op": "calculation", "name": "PctDmg"},
                                        {
                                            "op": "stat",
                                            "stat": "health",
                                            "scope": "max",
                                            "subject": "target",
                                        },
                                    ],
                                },
                            }
                        ],
                    }
                ],
                "passive_stats": [
                    {
                        "stat": "armor_penetration_percent",
                        "data_value": "PctPen",
                        "scale": 0.01,
                        "condition": "pasiva de W",
                    }
                ],
            }
        },
    }
    compiled = compile_kit(extract_doc, tt, spec)
    assert compiled["abilities"]["W"]["passive_stats"][0]["formula"] == {
        "op": "by_rank",
        "values": [0.2, 0.25, 0.3, 0.35, 0.4],
    }
    assert compiled["abilities"]["W"]["cases"][0]["parts"][0]["formula"]["operands"][0] == {
        "op": "by_rank",
        "values": [0.04, 0.05, 0.06, 0.07, 0.08],
    }
    assert zaahen_extract["champion"]["name"] == "Zaahen"
    assert isinstance(tooltips, dict)


def test_colon_scoped_tooltip_placeholders_resolve_in_bin2json_and_kitgen():
    from binmodel.bin2json import placeholders
    from binmodel.kitgen import tooltip_damage_types

    text = (
        "Inflige <magicDamage>@spell.VexR:RDamageCalc@</magicDamage> y "
        "<physicalDamage>@spell.X:Hit*100@</physicalDamage>."
    )
    assert placeholders([text]) == ["RDamageCalc", "Hit"]
    assert tooltip_damage_types(text, "RDamageCalc") == {"magic"}
    assert tooltip_damage_types(text, "Hit") == {"physical"}
