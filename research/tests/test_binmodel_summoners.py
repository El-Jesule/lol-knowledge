"""Unit tests for the client summoner spell extractor (binmodel.summoners)."""

from __future__ import annotations

from binmodel.summoners import _compile_calculation, _eval_breakpoints, _extract_spell_record


def test_eval_breakpoints_ignite_and_unleashed_tp() -> None:
    ignite_part = {
        "__type": "ByCharLevelBreakpointsCalculationPart",
        "mLevel1Value": 70.0,
        "mInitialBonusPerLevel": 20.0,
        "mBreakpoints": [{"mLevel": 6, "mBonusPerLevelAtAndAfter": 25.0}],
    }
    vals = _eval_breakpoints(ignite_part)
    assert len(vals) == 18
    assert vals[0] == 70
    assert vals[4] == 150
    assert vals[5] == 175
    assert vals[17] == 475

    tp_part = {
        "__type": "ByCharLevelBreakpointsCalculationPart",
        "mLevel1Value": 330.0,
        "mInitialBonusPerLevel": -10.0,
        "mBreakpoints": [{"mLevel": 10, "mAdditionalBonusAtThisLevel": -10.0}],
    }
    tp_vals = _eval_breakpoints(tp_part)
    assert tp_vals[0] == 330
    assert tp_vals[8] == 250
    assert tp_vals[9] == 230
    assert tp_vals[17] == 150


def test_compile_calculation_and_extract_record() -> None:
    lin = _compile_calculation(
        {
            "mFormulaParts": [
                {
                    "__type": "ByCharLevelInterpolationCalculationPart",
                    "mStartValue": 100.0,
                    "mEndValue": 460.0,
                }
            ]
        }
    )
    assert lin == {"op": "linear_by_level", "min": 100, "max": 460}

    rec = _extract_spell_record(
        {
            "mSpell": {
                "cooldownTime": [180.0],
                "castRange": [1200.0],
                "DataValues": [{"name": "ShieldDuration", "values": [2.5]}],
                "mSpellCalculations": {
                    "ShieldStrength": {
                        "mFormulaParts": [
                            {
                                "__type": "ByCharLevelInterpolationCalculationPart",
                                "mStartValue": 100.0,
                                "mEndValue": 460.0,
                            }
                        ]
                    }
                },
            }
        },
        spell_id="SummonerBarrier",
        alias="barrier",
        tooltip_prefix="spell_summonerbarrier",
        model_status="evaluable",
        tooltips={
            "spell_summonerbarrier_name": "Barrera",
            "spell_summonerbarrier_tooltip": "Escudo de @ShieldStrength@.",
        },
        content_version="16.23.test",
    )
    assert rec["id"] == "SummonerBarrier"
    assert rec["name"] == "Barrera"
    assert rec["cooldown_seconds"] == 180
    assert rec["data_values"] == {"ShieldDuration": 2.5}
    assert rec["calculations"]["ShieldStrength"] == {
        "op": "linear_by_level",
        "min": 100,
        "max": 460,
    }
