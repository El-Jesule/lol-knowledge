"""Tests for the object catalog validator and its project integration."""

from __future__ import annotations

from pathlib import Path

import pytest

from lol_knowledge.objects import (
    Snapshot,
    build_model,
    validate_catalog_document,
    validate_object_catalog,
)
from lol_knowledge.objects.schema import CATALOG_KIND
from lol_knowledge.stats import items_from_model
from lol_knowledge.validate import validate_project

DESCRIPTION = "10 de letalidad y 30% de daño adicional."


def _snapshot(
    *,
    description: str = DESCRIPTION,
    stats: dict | None = None,
    from_ids: list[str] | None = None,
    into_ids: list[str] | None = None,
    extra_items: dict | None = None,
) -> Snapshot:
    item = {
        "name": "Objeto de prueba",
        "description": description,
        "gold": {"base": 400, "total": 1000, "sell": 700, "purchasable": True},
        "maps": {"11": True, "22": False},
        "stats": stats if stats is not None else {"FlatPhysicalDamageMod": 10},
        "tags": ["Damage"],
    }
    if from_ids is not None:
        item["from"] = from_ids
    if into_ids is not None:
        item["into"] = into_ids
    items = {"9999": item}
    if extra_items:
        items.update(extra_items)
    return Snapshot(patch="16.20.1", locale="es_ES", items=items, items_sha256="0" * 64)


def _valid_stat() -> dict:
    return {"id": "lethality", "kind": "flat", "value": 10, "quote": "10 de letalidad"}


def _valid_effect() -> dict:
    return {
        "id": "test-effect",
        "kind": "passive",
        "name": "Prueba",
        "quote": "30% de daño adicional",
        "basis": "description_explicit",
        "trigger": {"event": "always"},
        "target": {"kind": "self"},
        "components": [
            {
                "kind": "stat_modifier",
                "stat": "ability_power",
                "scope": "total",
                "mode": "percent",
                "formula": {"op": "constant", "value": 30},
            }
        ],
        "cooldown_seconds": None,
        "stacks": None,
        "duration_seconds": None,
        "limits": [],
        "model_status": "evaluable",
    }


def _catalog(stat: dict | None = None, effect: dict | None = None) -> dict:
    entry = {"id": "9999", "effect_review": "complete", "stats": [], "effects": []}
    if stat is not None:
        entry["stats"].append(stat)
    if effect is not None:
        entry["effects"].append(effect)
    return {
        "schema_version": 1,
        "kind": CATALOG_KIND,
        "catalog_version": 1,
        "game_version": "16.20.1",
        "objects": [entry],
    }


def _messages(catalog: dict, snapshot: Snapshot | None = None) -> list[str]:
    report = validate_catalog_document(catalog, snapshot or _snapshot())
    return [violation.message for violation in report.violations]


def test_valid_synthetic_catalog_is_accepted() -> None:
    assert _messages(_catalog(_valid_stat(), _valid_effect())) == []


def test_header_mismatches_are_reported() -> None:
    catalog = _catalog(_valid_stat())
    catalog["schema_version"] = 2
    catalog["kind"] = "other"
    catalog["catalog_version"] = 0
    catalog["game_version"] = "16.19.1"
    messages = _messages(catalog)
    assert any("expected 1" in message for message in messages)
    assert any("lol-object-model-catalog" in message for message in messages)
    assert any("catalog_version" in message for message in messages)
    assert any("snapshot is '16.20.1'" in message for message in messages)


def test_unknown_item_is_reported() -> None:
    catalog = _catalog(_valid_stat())
    catalog["objects"][0]["id"] = "404"
    assert any("not in the snapshot" in message for message in _messages(catalog))


def test_duplicate_object_id_is_reported() -> None:
    catalog = _catalog(_valid_stat())
    catalog["objects"].append(dict(catalog["objects"][0]))
    assert any("duplicate object id" in message for message in _messages(catalog))


def test_unknown_stat_id_is_reported() -> None:
    stat = {"id": "magic_find", "kind": "flat", "value": 1, "quote": "10 de letalidad"}
    assert any("unknown stat id" in message for message in _messages(_catalog(stat)))


def test_derived_stat_cannot_be_declared_again() -> None:
    stat = {
        "id": "attack_damage",
        "kind": "flat",
        "value": 10,
        "quote": "10 de letalidad",
    }
    assert any("already derived" in message for message in _messages(_catalog(stat)))


def test_quote_must_exist_in_the_description() -> None:
    stat = {"id": "lethality", "kind": "flat", "value": 10, "quote": "10 de letalidad"}
    messages = _messages(_catalog(stat), _snapshot(description="Otra descripción."))
    assert any("not in the item description" in message for message in messages)


def test_declared_value_must_appear_in_the_quote() -> None:
    stat = {"id": "lethality", "kind": "flat", "value": 12, "quote": "10 de letalidad"}
    assert any("does not appear in the quote" in message for message in _messages(_catalog(stat)))


def test_zero_and_unknown_are_different() -> None:
    snapshot = _snapshot(description="0 de daño y 10 de letalidad")
    zero = {"id": "lethality", "kind": "flat", "value": 0, "quote": "0 de daño"}
    unknown = {
        "id": "lethality",
        "kind": "flat",
        "status": "unknown",
        "reason": "not published",
        "quote": "10 de letalidad",
    }
    assert _messages(_catalog(zero), snapshot) == []
    assert _messages(_catalog(unknown), snapshot) == []

    zero_model = build_model(_catalog(zero), snapshot)
    zero_stat = next(
        stat for stat in zero_model["objects"][0]["stats"] if stat["id"] == "lethality"
    )
    assert zero_stat["value"] == 0.0
    assert zero_stat["status"] == "declared"

    unknown_model = build_model(_catalog(unknown), snapshot)
    unknown_stat = next(
        stat for stat in unknown_model["objects"][0]["stats"] if stat["id"] == "lethality"
    )
    assert unknown_stat["value"] is None
    assert unknown_stat["status"] == "unknown"
    assert unknown_stat["reason"] == "not published"


def test_unknown_stat_needs_a_reason() -> None:
    stat = {"id": "lethality", "kind": "flat", "status": "unknown", "quote": "10 de letalidad"}
    assert any("non-empty reason" in message for message in _messages(_catalog(stat)))


def test_malformed_formula_is_reported() -> None:
    effect = _valid_effect()
    effect["components"][0]["formula"] = {"op": "divide", "operands": []}
    assert any(
        "unsupported formula op" in message for message in _messages(_catalog(effect=effect))
    )


def test_model_status_cannot_be_more_optimistic_than_the_formula() -> None:
    effect = _valid_effect()
    effect["components"][0]["formula"] = {"op": "unknown", "reason": "missing"}
    effect["model_status"] = "evaluable"
    messages = _messages(_catalog(effect=effect))
    assert any("more optimistic" in message for message in messages)

    effect["model_status"] = "partially_evaluable"
    effect["basis"] = "description_partial"
    assert _messages(_catalog(effect=effect)) == []


def test_excluded_effect_may_have_no_components() -> None:
    effect = _valid_effect()
    effect["components"] = []
    effect["model_status"] = "excluded"
    effect["basis"] = "description_silent"
    assert _messages(_catalog(effect=effect)) == []


def test_unmapped_snapshot_stat_is_reported() -> None:
    snapshot = _snapshot(stats={"FlatPhysicalDamageMod": 10, "NewStatMod": 1})
    messages = _messages(_catalog(), snapshot)
    assert any("no canonical mapping" in message for message in messages)


def test_basis_must_match_the_formula_state() -> None:
    effect = _valid_effect()
    effect["components"][0]["formula"] = {"op": "unknown", "reason": "missing"}
    effect["model_status"] = "partially_evaluable"
    messages = _messages(_catalog(effect=effect))
    assert any("description_explicit requires" in message for message in messages)

    effect = _valid_effect()
    effect["basis"] = "description_partial"
    messages = _messages(_catalog(effect=effect))
    assert any("description_partial needs" in message for message in messages)


def test_absolute_healing_component_is_accepted() -> None:
    snapshot = _snapshot(description="Cura 100 de vida y 30% de daño adicional.")
    effect = _valid_effect()
    effect["quote"] = "Cura 100 de vida"
    effect["components"] = [
        {
            "kind": "healing",
            "mode": "absolute",
            "target": {"kind": "ally_champion"},
            "formula": {"op": "constant", "value": 100},
        }
    ]
    assert _messages(_catalog(effect=effect), snapshot) == []


def test_unknown_keys_are_reported() -> None:
    catalog = _catalog(_valid_stat())
    catalog["unexpected"] = True
    catalog["objects"][0]["surprise"] = 1
    messages = _messages(catalog)
    assert any("unknown top-level keys" in message for message in messages)
    assert any("unknown object keys" in message for message in messages)


def test_recipe_reference_must_exist() -> None:
    snapshot = _snapshot(from_ids=["1234"])
    assert any("unknown item '1234'" in message for message in _messages(_catalog(), snapshot))


def test_recipe_reference_can_point_to_a_known_item() -> None:
    snapshot = _snapshot(
        from_ids=["1036"],
        extra_items={"1036": {"name": "Componente", "description": "x", "gold": {}, "maps": {}}},
    )
    assert _messages(_catalog(), snapshot) == []


def test_validation_is_deterministic() -> None:
    catalog = _catalog(_valid_stat())
    catalog["objects"][0]["stats"][0]["value"] = 99
    first = validate_catalog_document(catalog, _snapshot())
    second = validate_catalog_document(catalog, _snapshot())
    assert first.violations == second.violations


def test_real_project_catalog_is_valid(project_root: Path) -> None:
    report = validate_project(project_root)
    assert report.ok, [str(violation) for violation in report.violations]
    assert "lol-knowledge/objects" not in " ".join(report.skipped)


def test_missing_objects_directory_is_skipped(tmp_path: Path) -> None:
    report = validate_object_catalog(tmp_path)
    assert report.ok
    assert report.skipped


def test_missing_catalog_is_a_violation(tmp_path: Path) -> None:
    objects = tmp_path / "lol-knowledge" / "objects"
    objects.mkdir(parents=True)
    (objects / "README.md").write_text("# Modelo", encoding="utf-8")
    report = validate_object_catalog(tmp_path)
    assert not report.ok
    assert "catalog.json not found" in report.violations[0].message


def test_missing_readme_is_a_violation(tmp_path: Path) -> None:
    objects = tmp_path / "lol-knowledge" / "objects"
    objects.mkdir(parents=True)
    (objects / "catalog.json").write_text("{}", encoding="utf-8")
    report = validate_object_catalog(tmp_path)
    assert not report.ok
    assert "README.md not found" in report.violations[0].message


def _external_effect() -> dict:
    source = {
        "kind": "community_wiki",
        "reference": "https://wiki.leagueoflegends.com/en-us/Example?action=raw",
        "quote": "1% per 100 bonus health.",
        "retrieved_at": "2026-10-20",
        "confidence": "secondary",
    }
    effect = _valid_effect()
    effect["basis"] = "external_evidence_explicit"
    effect["components"] = [
        {
            "kind": "damage",
            "damage_type": "physical",
            "target": {"kind": "enemy_champion"},
            "formula": {
                "op": "percent_of",
                "percent": 1,
                "stat": "health",
                "scope": "bonus",
            },
        }
    ]
    effect["sources"] = [source]
    effect["evidence_confidence"] = "secondary"
    return effect


def test_external_evidence_with_a_cited_source_is_accepted() -> None:
    effect = _external_effect()
    assert _messages(_catalog(effect=effect)) == []


def test_external_evidence_needs_a_source() -> None:
    effect = _external_effect()
    del effect["sources"]
    messages = _messages(_catalog(effect=effect))
    assert any("needs at least one declared source" in message for message in messages)


def test_external_evidence_cannot_hide_a_non_evaluable_formula() -> None:
    effect = _external_effect()
    effect["components"][0]["formula"] = {"op": "unknown", "reason": "missing"}
    effect["model_status"] = "partially_evaluable"
    messages = _messages(_catalog(effect=effect))
    assert any("requires every formula to be evaluable" in message for message in messages)


def test_source_needs_reference_quote_and_date() -> None:
    effect = _external_effect()
    del effect["sources"][0]["quote"]
    messages = _messages(_catalog(effect=effect))
    assert any("source quote must be a non-empty string" in message for message in messages)


def test_source_kind_and_confidence_are_checked() -> None:
    effect = _external_effect()
    effect["sources"][0]["kind"] = "random_blog"
    effect["sources"][0]["confidence"] = "certain"
    messages = _messages(_catalog(effect=effect))
    assert any("source kind must be one of" in message for message in messages)
    assert any("source confidence must be one of" in message for message in messages)


def test_every_effect_number_needs_a_cited_quote() -> None:
    effect = _external_effect()
    effect["components"][0]["formula"]["percent"] = 99
    messages = _messages(_catalog(effect=effect))
    assert any("not present in any cited quote" in message for message in messages)


def test_sources_require_an_explicit_confidence() -> None:
    effect = _external_effect()
    del effect["evidence_confidence"]
    messages = _messages(_catalog(effect=effect))
    assert any("need an explicit evidence_confidence" in message for message in messages)


def test_secondary_confidence_without_sources_is_rejected() -> None:
    effect = _valid_effect()
    effect["evidence_confidence"] = "secondary"
    messages = _messages(_catalog(effect=effect))
    assert any("needs at least one source" in message for message in messages)


def test_flat_magic_penetration_is_a_canonical_stat() -> None:
    snapshot = _snapshot(description="12 de penetración mágica")
    stat = {
        "id": "magic_penetration_flat",
        "kind": "flat",
        "value": 12,
        "quote": "12 de penetración mágica",
    }
    assert _messages(_catalog(stat=stat), snapshot) == []


def test_omnivamp_can_be_declared_from_the_description() -> None:
    snapshot = _snapshot(description="2.5% de omnisucción")
    stat = {"id": "omnivamp", "kind": "percent", "value": 2.5, "quote": "2.5% de omnisucción"}
    assert _messages(_catalog(stat=stat), snapshot) == []
    stat["kind"] = "flat"
    assert any(
        "does not support kind 'flat'" in m for m in _messages(_catalog(stat=stat), snapshot)
    )


def test_community_source_cannot_be_official() -> None:
    effect = _external_effect()
    effect["sources"][0]["confidence"] = "official"
    effect["evidence_confidence"] = "official"
    messages = _messages(_catalog(effect=effect))
    assert any("cannot be 'official'" in message for message in messages)
    assert any("official evidence must come from" in message for message in messages)


def test_corroborated_evidence_needs_two_sources() -> None:
    effect = _external_effect()
    effect["evidence_confidence"] = "corroborated"
    messages = _messages(_catalog(effect=effect))
    assert any("needs at least two independent sources" in message for message in messages)


def test_uncited_stack_count_is_reported() -> None:
    effect = _valid_effect()
    effect["stacks"] = {"required": 7, "window_seconds": None, "max_stacks": None}
    messages = _messages(_catalog(effect=effect))
    assert any("not present in any cited quote" in message for message in messages)


def test_formula_key_typo_is_reported() -> None:
    effect = _valid_effect()
    effect["components"][0]["formula"] = {
        "op": "stat",
        "stat": "health",
        "scope": "bonus",
        "subjet": "target",
    }
    messages = _messages(_catalog(effect=effect))
    assert any("unknown keys" in message for message in messages)


def _client_effect(kind: str = "client_data") -> dict:
    effect = _external_effect()
    effect["components"][0]["formula"]["percent"] = 9
    effect["sources"] = [
        {
            "kind": kind,
            "reference": "Cliente 16.22: Global.wad.client → items → Items/3153.mDataValues",
            "quote": "MeleeValue = 0.09",
            "retrieved_at": "2026-11-15",
            "confidence": "secondary",
        }
    ]
    return effect


def test_client_data_quotes_count_fractions_as_percentages() -> None:
    assert _messages(_catalog(effect=_client_effect())) == []


def test_only_client_data_quotes_scale_fractions() -> None:
    messages = _messages(_catalog(effect=_client_effect("community_wiki")))
    assert any("number 9.0 is not present" in message for message in messages)


def test_client_data_cannot_be_official() -> None:
    effect = _client_effect()
    effect["sources"][0]["confidence"] = "official"
    messages = _messages(_catalog(effect=effect))
    assert any("'client_data' cannot be 'official'" in message for message in messages)


def _life_steal_source() -> dict:
    return {
        "kind": "community_wiki",
        "reference": "https://wiki.leagueoflegends.com/en-us/Example?oldid=1",
        "quote": "The bonus damage benefits from life steal.",
        "retrieved_at": "2026-11-15",
        "confidence": "secondary",
    }


@pytest.mark.parametrize("value", [True, False])
def test_damage_component_can_declare_whether_it_applies_life_steal(value) -> None:
    effect = _external_effect()
    effect["components"][0]["applies_life_steal"] = {"value": value, "source": _life_steal_source()}
    assert _messages(_catalog(effect=effect)) == []


@pytest.mark.parametrize(
    ("declaration", "message"),
    [
        (True, "must be an object with value and source"),
        ({"value": "yes", "source": None}, "value must be true or false"),
        ({"value": True}, "applies_life_steal needs a source"),
        ({"value": True, "source": None}, "applies_life_steal needs a source"),
        ({"value": True, "source": {}, "why": 1}, "unknown applies_life_steal keys: ['why']"),
        ({"value": True, "source": {"kind": "community_wiki"}}, "source quote must be"),
    ],
)
def test_invalid_life_steal_declarations(declaration, message) -> None:
    effect = _external_effect()
    effect["components"][0]["applies_life_steal"] = declaration
    messages = _messages(_catalog(effect=effect))
    assert any(message in item for item in messages), messages


def test_life_steal_source_confidence_follows_its_kind() -> None:
    effect = _external_effect()
    source = {**_life_steal_source(), "confidence": "official"}
    effect["components"][0]["applies_life_steal"] = {"value": True, "source": source}
    messages = _messages(_catalog(effect=effect))
    assert any("cannot be 'official'" in item for item in messages)
    assert any("applies_life_steal.source[0].confidence" in str(v) for v in _violations(effect))


def test_only_damage_components_declare_life_steal() -> None:
    effect = _valid_effect()
    effect["components"][0]["applies_life_steal"] = {
        "value": True,
        "source": _life_steal_source(),
    }
    messages = _messages(_catalog(effect=effect))
    assert "only damage components can declare applies_life_steal" in messages


def _violations(effect: dict) -> list:
    return list(validate_catalog_document(_catalog(effect=effect), _snapshot()).violations)


def test_tenacity_can_be_declared_from_the_description() -> None:
    snapshot = _snapshot(description="30% de tenacidad")
    stat = {"id": "tenacity", "kind": "percent", "value": 30, "quote": "30% de tenacidad"}
    assert _messages(_catalog(stat=stat), snapshot) == []
    stat["kind"] = "flat"
    assert any(
        "does not support kind 'flat'" in m for m in _messages(_catalog(stat=stat), snapshot)
    )


@pytest.mark.parametrize(
    ("stat_id", "kind", "value", "quote"),
    [
        ("health_regen", "percent", 100, "100% de regeneración de vida básica"),
        ("health_regen", "flat", 5, "5 de regeneración de vida cada 5 s"),
        ("mana_regen", "percent", 125, "125% de regeneración de maná básica"),
        ("mana_regen", "flat", 7, "7 de regeneración de maná cada 5 s"),
    ],
)
def test_regeneration_can_be_declared_flat_or_as_a_percent_of_base(
    stat_id, kind, value, quote
) -> None:
    snapshot = _snapshot(description=quote)
    stat = {"id": stat_id, "kind": kind, "value": value, "quote": quote}
    assert _messages(_catalog(stat=stat), snapshot) == []


def test_the_model_and_the_sheet_items_carry_a_partial_review() -> None:
    catalog = _catalog(_valid_stat())
    catalog["objects"][0]["effect_review"] = "partial"
    model = build_model(catalog, _snapshot())
    assert model["objects"][0]["effect_review"] == "partial"
    (item,) = items_from_model(model, ["9999"])
    assert item.effect_review == "partial"


@pytest.mark.parametrize(
    ("lines", "message"),
    [
        ([], "must be a non-empty list"),
        ("x", "must be a non-empty list"),
        ([{"quote": "10 de letalidad"}], "must be an object with quote and reason"),
        ([{"quote": "otra cosa", "reason": "r"}], "quote is not in the item description"),
        ([{"quote": "10 de letalidad", "reason": " "}], "reason must be a non-empty string"),
    ],
)
def test_unmodelled_stat_lines_need_a_quote_and_a_reason(lines, message) -> None:
    catalog = _catalog(_valid_stat())
    catalog["objects"][0]["unmodelled_stats"] = lines
    assert any(message in item for item in _messages(catalog))


def test_unmodelled_stat_lines_reach_the_model() -> None:
    catalog = _catalog(_valid_stat())
    lines = [{"quote": "10 de letalidad", "reason": "r"}]
    catalog["objects"][0]["unmodelled_stats"] = lines
    assert _messages(catalog) == []
    assert build_model(catalog, _snapshot())["objects"][0]["unmodelled_description_stats"] == lines


@pytest.mark.parametrize(("review", "valid"), [("pending", True), ("todo", False)])
def test_effect_reviews(review, valid) -> None:
    catalog = _catalog(_valid_stat())
    catalog["objects"][0]["effect_review"] = review
    found = any("effect_review must be one of" in item for item in _messages(catalog))
    assert found is not valid


# Scenarios and confirmed zeros


def _scenario_effect(**component) -> dict:
    effect = _valid_effect()
    effect["trigger"] = {"event": "on_attack"}
    effect["scenario"] = "max_stacks"
    effect["components"][0].update({"mode": "flat", **component})
    return effect


def test_a_flat_max_stacks_effect_on_attack_is_accepted() -> None:
    assert _messages(_catalog(effect=_scenario_effect())) == []


def test_an_unknown_scenario_is_reported() -> None:
    effect = _scenario_effect()
    effect["scenario"] = "half_stacks"
    assert "scenario must be one of ['max_stacks']" in _messages(_catalog(effect=effect))


def test_a_max_stacks_effect_needs_flat_stat_modifiers() -> None:
    found = _messages(_catalog(effect=_scenario_effect(mode="percent")))
    assert "a max_stacks effect may only have flat stat_modifier components" in found


def test_confirmed_zero_stats_are_checked() -> None:
    catalog = _catalog()
    entry = catalog["objects"][0]
    entry["confirmed_zero_stats"] = [
        {"id": "crit_chance", "kind": "flat", "reason": "x"},
        {"id": "crit_chance", "kind": "percent", "reason": " "},
        {"id": "crit_chance"},
    ]
    found = _messages(catalog)
    assert "unknown stat 'crit_chance' of kind 'flat'" in found
    assert "reason must be a non-empty string" in found
    assert "must be an object with id, kind and reason" in found
    entry["confirmed_zero_stats"] = []
    assert "confirmed_zero_stats must be a non-empty list" in _messages(catalog)


# Evidence read only from the client


def _derived_effect(kind: str = "client_data", confidence: str = "derived") -> dict:
    effect = _external_effect()
    effect["sources"] = [
        {
            "kind": kind,
            "reference": "lol-knowledge/derived/item-effects.json → items.9999",
            "quote": "Ratio = 0.01",
            "retrieved_at": "2026-11-16",
            "confidence": confidence,
        }
    ]
    effect["evidence_confidence"] = "derived"
    return effect


def test_derived_evidence_from_the_client_is_accepted() -> None:
    assert _messages(_catalog(effect=_derived_effect())) == []


def test_derived_evidence_needs_a_client_source() -> None:
    found = _messages(_catalog(effect=_derived_effect("community_wiki", "secondary")))
    assert "derived evidence needs a client_data source" in found


def test_only_client_sources_can_be_derived() -> None:
    found = _messages(_catalog(effect=_derived_effect("community_wiki")))
    assert "source kind 'community_wiki' cannot be 'derived'" in found


def test_derived_evidence_needs_sources() -> None:
    effect = _derived_effect()
    del effect["sources"]
    assert "evidence_confidence 'derived' needs at least one source" in _messages(
        _catalog(effect=effect)
    )
