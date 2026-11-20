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
    with pytest.raises(KitGenError, match="stat-progression"):
        synth.calculation("BadInterp")


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
