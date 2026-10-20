"""The extractor must not depend on Zaahen names."""

from __future__ import annotations

import json

import pytest
from binmodel.evaluate import EvaluationContext, evaluate
from binmodel.extract import extract_champion
from binmodel.stats import champion_stats


def _stat(value: float) -> dict[str, object]:
    return {"baseValue": value, "__type": "ModifiableFloat"}


def _synthetic_document() -> dict[str, object]:
    root_path = "Characters/TestChampion/CharacterRecords/Root"
    passive_path = "Characters/TestChampion/Spells/TestPassive"
    q_path = "Characters/TestChampion/Spells/TestQ"
    q_ability_path = "Characters/TestChampion/Spells/TestQAbility"
    return {
        root_path: {
            "__type": "CharacterRecord",
            "mCharacterName": "TestChampion",
            "baseDamageModifiable": _stat(50.0),
            "damagePerLevelModifiable": _stat(3.0),
            "baseHPModifiable": _stat(500.0),
            "hpPerLevelModifiable": _stat(100.0),
            "baseArmorModifiable": _stat(20.0),
            "armorPerLevelModifiable": _stat(4.0),
            "baseMR": _stat(30.0),
            "mrPerLevel": _stat(1.0),
            "baseMoveSpeedModifiable": _stat(330.0),
            "attackRangeModifiable": _stat(125.0),
            "attackSpeedModifiable": _stat(0.6),
            "attackSpeedRatioModifiable": _stat(0.6),
            "attackSpeedPerLevelModifiable": _stat(2.0),
            "spells": [q_path],
            "mAbilities": [q_ability_path],
            "mCharacterPassiveSpell": passive_path,
            "passiveName": "TestPassiveKey",
            "passiveToolTip": "TestPassiveTooltipKey",
        },
        q_ability_path: {
            "__type": "AbilityObject",
            "mRootSpell": q_path,
            "mChildSpells": [],
            "mName": "TestQAbility",
        },
        passive_path: {
            "__type": "SpellObject",
            "ObjectName": "TestPassive",
            "objectPath": passive_path,
            "mScriptName": "TestPassive",
            "mSpell": {
                "DataValues": [],
                "mSpellCalculations": {},
                "Cooldown": {"values": [1.0] * 6, "__type": "{0a0eddc9}"},
                "mClientData": {
                    "__type": "SpellDataResourceClient",
                    "mTooltipData": {
                        "__type": "TooltipInstanceSpell",
                        "mObjectName": "TestPassive",
                        "mLocKeys": {},
                        "mLists": {},
                    },
                },
            },
        },
        q_path: {
            "__type": "SpellObject",
            "ObjectName": "TestQ",
            "objectPath": q_path,
            "mScriptName": "TestQ",
            "mSpell": {
                "DataValues": [
                    {
                        "name": "TestBase",
                        "values": [0.0, 10.0, 20.0, 30.0, 40.0],
                        "__type": "SpellDataValue",
                    },
                    {
                        "name": "TestRatio",
                        "values": [0.0, 0.1, 0.2, 0.3, 0.4],
                        "__type": "SpellDataValue",
                    },
                ],
                "mSpellCalculations": {
                    "TestDamage": {
                        "__type": "GameCalculation",
                        "mFormulaParts": [
                            {
                                "__type": "NamedDataValueCalculationPart",
                                "mDataValue": "TestBase",
                            },
                            {
                                "__type": "StatByNamedDataValueCalculationPart",
                                "mStat": 2,
                                "mStatFormula": 2,
                                "mDataValue": "TestRatio",
                            },
                        ],
                    }
                },
                "Cooldown": {
                    "values": [9.0, 8.0, 7.0, 6.0, 5.0],
                    "__type": "{0a0eddc9}",
                },
                "mana": [30.0, 30.0, 30.0, 30.0],
                "mClientData": {
                    "__type": "SpellDataResourceClient",
                    "mTooltipData": {
                        "__type": "TooltipInstanceSpell",
                        "mObjectName": "TestQ",
                        "mLocKeys": {},
                        "mLists": {
                            "LevelUp": {
                                "levelCount": 4,
                                "Elements": [],
                                "__type": "TooltipInstanceList",
                            }
                        },
                    },
                },
            },
        },
    }


def test_synthetic_champion_is_discovered_without_name_changes():
    document = _synthetic_document()
    extract = extract_champion(document, source={"sha256": "synthetic"})
    assert extract.champion["id"] == "TestChampion"
    assert [ability.slot for ability in extract.abilities] == ["P", "Q"]
    q = next(ability for ability in extract.abilities if ability.ability_id == "q")
    assert q.level_count == 4
    assert [item.name for item in q.calculations] == ["TestDamage"]
    values = {value.name: value for value in q.data_values}
    assert values["TestBase"].ranks == [10.0, 20.0, 30.0, 40.0]
    assert values["TestRatio"].ranks == [0.1, 0.2, 0.3, 0.4]


def test_synthetic_formula_evaluates_with_the_same_engine():
    document = _synthetic_document()
    extract = extract_champion(document, source={"sha256": "synthetic"})
    q = next(ability for ability in extract.abilities if ability.ability_id == "q")
    stats = champion_stats(extract.champion["base_stats"], 18, bonus_attack_damage=100.0)
    context = EvaluationContext(abilities={"q": q}, stats=stats)
    result = evaluate(q, "TestDamage", context, level=18, rank=1)
    assert result.value == pytest.approx(20.0)
    assert result.complete is True


def test_real_darius_fixture_has_no_zaahen_dependency(darius_document):
    meta = darius_document["_provenance"]
    extract = extract_champion(
        darius_document,
        source={"artifact_sha256": meta["source_sha256"], "url": meta["url"]},
        content_version=meta["content_version"],
    )
    assert extract.champion["id"] == "Darius"
    abilities = {ability.ability_id: ability for ability in extract.abilities}
    assert tuple(abilities) == ("passive", "q", "w", "e", "r")
    assert [item.name for item in abilities["q"].calculations] == [
        "BladeDamage",
        "HandleDamage",
    ]
    assert abilities["q"].level_count == 5
    assert abilities["r"].level_count == 3
    assert "Zaahen" not in json.dumps(extract.to_dict())
    stats = champion_stats(extract.champion["base_stats"], 1)
    context = EvaluationContext(abilities=abilities, stats=stats)
    result = evaluate(abilities["q"], "BladeDamage", context, level=1, rank=1)
    assert result.complete is True
    assert result.value > 0
