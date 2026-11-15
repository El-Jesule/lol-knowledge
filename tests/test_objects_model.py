"""Tests for the canonical object model built from the real snapshot."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from lol_knowledge.objects import (
    build_model,
    dump_model,
    formula_stat_requirements,
    load_catalog,
    load_snapshot,
)


def _object(model: Mapping[str, Any], item_id: str) -> Mapping[str, Any]:
    return next(item for item in model["objects"] if item["id"] == item_id)


def _stat(obj: Mapping[str, Any], stat_id: str) -> Mapping[str, Any]:
    return next(stat for stat in obj["stats"] if stat["id"] == stat_id)


def _effect(obj: Mapping[str, Any], effect_id: str) -> Mapping[str, Any]:
    return next(effect for effect in obj["effects"] if effect["id"] == effect_id)


def _reverse_keys(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _reverse_keys(value[key]) for key in reversed(list(value))}
    if isinstance(value, list):
        return [_reverse_keys(item) for item in value]
    return value


def test_model_header_links_to_the_snapshot(object_model, object_snapshot) -> None:
    assert object_model["schema_version"] == 1
    assert object_model["kind"] == "lol-object-model"
    assert object_model["catalog_version"] == 2
    assert object_model["game_version"] == object_snapshot.patch
    assert object_model["source"]["items_sha256"] == object_snapshot.items_sha256
    assert object_model["source"]["catalog"] == "lol-knowledge/objects/catalog.json"


def test_sample_has_fifteen_objects(object_model) -> None:
    ids = [item["id"] for item in object_model["objects"]]
    assert len(ids) == 15
    assert ids == sorted(ids, key=lambda value: int(value))


def test_flat_and_percent_stats_are_derived(object_model) -> None:
    bork = _object(object_model, "3153")
    assert _stat(bork, "attack_damage")["value"] == 40.0
    assert _stat(bork, "attack_damage")["kind"] == "flat"
    assert _stat(bork, "attack_damage")["source"] == {
        "kind": "ddragon_stat",
        "key": "FlatPhysicalDamageMod",
    }
    speed = _stat(bork, "attack_speed")
    assert speed["kind"] == "percent"
    assert speed["value"] == 25.0
    assert speed["raw_value"] == 0.25
    assert _stat(bork, "life_steal")["value"] == 10.0


def test_description_stats_are_quoted(object_model) -> None:
    dirk = _object(object_model, "3134")
    lethality = _stat(dirk, "lethality")
    assert lethality["value"] == 10.0
    assert lethality["verification"] == "description_quote_verified"
    assert lethality["source"]["kind"] == "ddragon_description"
    assert lethality["source"]["quote"] == "10 de letalidad"


def test_flat_magic_penetration_is_declared_from_prose(object_model) -> None:
    shoes = _object(object_model, "3020")
    penetration = _stat(shoes, "magic_penetration_flat")
    assert penetration["kind"] == "flat"
    assert penetration["value"] == 12.0
    assert penetration["source"] == {
        "kind": "ddragon_description",
        "item_id": "3020",
        "quote": "12 de penetración mágica",
    }


def test_crit_damage_is_not_mixed_with_crit_chance(object_model) -> None:
    infinity = _object(object_model, "3031")
    assert _stat(infinity, "crit_chance")["value"] == 25.0
    assert _stat(infinity, "crit_damage_bonus")["value"] == 30.0
    assert _stat(infinity, "crit_damage_bonus")["kind"] == "percent"


def test_recipe_is_a_multiset(object_model) -> None:
    dirk = _object(object_model, "3134")
    assert dirk["recipe"]["builds_from"] == [
        {"id": "1036", "count": 2},
    ]
    deathcap = _object(object_model, "3089")
    assert deathcap["recipe"]["builds_from"] == [
        {"id": "1058", "count": 2},
    ]
    assert deathcap["recipe"]["depth"] == 2
    assert dirk["recipe"]["builds_into"] == sorted(
        dirk["recipe"]["builds_into"], key=lambda value: int(value)
    )


def test_availability_preserves_absence(object_model) -> None:
    bork = _object(object_model, "3153")
    availability = bork["availability"]
    assert availability["purchasable"] is True
    assert availability["in_store"] is None
    assert availability["hide_from_all"] is None
    assert availability["maps"]["22"] is False
    assert availability["map_ids"] == [11, 12, 453]
    assert availability["modes"]["status"] == "unknown"


def test_effect_statuses_match_the_formulas(object_model) -> None:
    deathcap = _effect(_object(object_model, "3089"), "magic-orb")
    assert deathcap["model_status"] == "evaluable"
    assert deathcap["derived_status"] == "evaluable"

    fogblade = _effect(_object(object_model, "3153"), "fogblade")
    assert fogblade["model_status"] == "evaluable"
    assert fogblade["derived_status"] == "evaluable"

    giant_slayer = _effect(_object(object_model, "3036"), "giant-slayer")
    assert giant_slayer["model_status"] == "evaluable"
    assert giant_slayer["derived_status"] == "evaluable"

    thorns = _effect(_object(object_model, "3075"), "thorns")
    assert thorns["model_status"] == "evaluable"
    assert thorns["derived_status"] == "evaluable"


def test_botrk_damage_records_the_range_variants(object_model) -> None:
    fogblade = _effect(_object(object_model, "3153"), "fogblade")
    formula = fogblade["components"][0]["formula"]
    assert formula["op"] == "by_holder_range"
    assert formula["melee"] == {
        "op": "percent_of",
        "percent": 9,
        "stat": "health",
        "scope": "current",
    }
    assert formula["ranged"]["percent"] == 6
    assert fogblade["limits"] == [
        {
            "kind": "maximum",
            "value": 100,
            "unit": "flat",
            "condition": "target is a minion or monster",
        }
    ]


def test_botrk_stacks_record_window_and_cooldown(object_model) -> None:
    night_claw = _effect(_object(object_model, "3153"), "night-claw")
    assert night_claw["stacks"] == {
        "required": 3,
        "window_seconds": 6,
        "max_stacks": 3,
    }
    assert night_claw["cooldown_seconds"] == 15
    assert night_claw["model_status"] == "partially_evaluable"


def test_lord_dominik_uses_the_capped_linear_curve(object_model) -> None:
    giant_slayer = _effect(_object(object_model, "3036"), "giant-slayer")
    formula = giant_slayer["components"][0]["formula"]
    assert formula == {
        "op": "min",
        "operands": [
            {
                "op": "percent_of",
                "percent": 1,
                "stat": "health",
                "scope": "bonus",
                "subject": "target",
            },
            {"op": "constant", "value": 15},
        ],
    }


def test_thornmail_records_base_and_bonus_armor_ratio(object_model) -> None:
    thorns = _effect(_object(object_model, "3075"), "thorns")
    damage = thorns["components"][0]
    assert damage["damage_type"] == "magic"
    assert damage["formula"] == {
        "op": "add",
        "operands": [
            {"op": "constant", "value": 20},
            {"op": "percent_of", "percent": 10, "stat": "armor", "scope": "bonus"},
        ],
    }


def test_randuin_models_crit_reduction_and_active_slow(object_model) -> None:
    randuin = _object(object_model, "3143")
    resilience = _effect(randuin, "resilience")
    assert resilience["components"][0]["formula"] == {"op": "constant", "value": -30}
    assert resilience["components"][0]["conditions"] == [{"kind": "critical_strike"}]

    humility = _effect(randuin, "humility")
    assert humility["cooldown_seconds"] == 90
    assert humility["components"][0]["magnitude"] == {"op": "constant", "value": 70}
    assert humility["components"][0]["duration_seconds"] == 2


def test_secondary_sources_are_explicit_and_preserved(object_model) -> None:
    for item_id, effect_id in (
        ("3153", "fogblade"),
        ("3153", "night-claw"),
        ("3036", "giant-slayer"),
        ("3157", "time-stop"),
        ("3075", "thorns"),
        ("3143", "humility"),
    ):
        effect = _effect(_object(object_model, item_id), effect_id)
        assert effect["evidence_confidence"] == "secondary"
        assert effect["sources"]
        for source in effect["sources"]:
            assert source["kind"] == "community_wiki"
            assert source["reference"].startswith("https://wiki.leagueoflegends.com/")
            assert source["retrieved_at"] == "2026-10-20"
            assert source["quote"]
    assert _object(object_model, "3153")["verification"] == "secondary_source_verified"
    assert _object(object_model, "3036")["verification"] == "secondary_source_verified"


def test_moonstone_models_healing_and_shield_percentages(object_model) -> None:
    moonstone = _object(object_model, "6617")
    assert _stat(moonstone, "mana_regen")["value"] == 125.0
    assert _stat(moonstone, "ability_haste")["value"] == 20.0
    stargrace = _effect(moonstone, "stargrace")
    assert stargrace["model_status"] == "evaluable"
    components = {component["kind"]: component for component in stargrace["components"]}
    assert components["healing"]["mode"] == "percent_of_trigger"
    assert components["healing"]["formula"] == {"op": "constant", "value": 30}
    assert components["shield"]["mode"] == "percent_of_trigger"
    assert components["shield"]["formula"] == {"op": "constant", "value": 35}


def test_unknown_component_values_make_the_effect_partial() -> None:
    from lol_knowledge.objects.catalog import derived_effect_status

    effect = {
        "components": [
            {
                "kind": "crowd_control",
                "effect": "slow",
                "magnitude": {"op": "unknown", "reason": "missing"},
            }
        ]
    }
    assert derived_effect_status(effect) == "partially_evaluable"

    effect = {
        "components": [
            {
                "kind": "stasis",
                "duration_seconds": {"status": "unknown", "reason": "missing"},
            }
        ]
    }
    assert derived_effect_status(effect) == "partially_evaluable"


def test_zhonya_records_the_active_cooldown_not_the_stasis_duration(object_model) -> None:
    time_stop = _effect(_object(object_model, "3157"), "time-stop")
    assert time_stop["cooldown_seconds"] == 120
    assert time_stop["duration_seconds"] == 2.5
    assert time_stop["model_status"] == "evaluable"


def test_no_snapshot_stats_are_unmapped(object_model) -> None:
    for item in object_model["objects"]:
        assert item["unmapped_source_stats"] == []


def test_formula_requirements_use_the_target_scope(object_model) -> None:
    requirements = formula_stat_requirements(object_model)
    assert requirements["champion"] == ("bonus_armor",)
    assert requirements["target"] == ("bonus_health", "current_health")


def test_model_is_deterministic(project_root, object_catalog, object_snapshot) -> None:
    first = dump_model(build_model(object_catalog, object_snapshot))
    second = dump_model(build_model(_reverse_keys(object_catalog), object_snapshot))
    assert first == second


def test_model_builder_does_not_mutate_the_catalog(object_catalog, object_snapshot) -> None:
    before = dump_model({"objects": list(object_catalog["objects"])})
    build_model(object_catalog, object_snapshot)
    after = dump_model({"objects": list(object_catalog["objects"])})
    assert before == after


def test_names_come_from_the_snapshot(object_model, object_snapshot) -> None:
    for item in object_model["objects"]:
        assert item["name"] == object_snapshot.items[item["id"]]["name"]


def test_catalog_can_be_rebuilt_from_disk(project_root, object_catalog, object_snapshot) -> None:
    assert load_catalog(project_root)["objects"] == object_catalog["objects"]
    assert load_snapshot(project_root).items_sha256 == object_snapshot.items_sha256
