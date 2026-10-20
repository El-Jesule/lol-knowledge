"""Tests for the object catalog validator and its project integration."""

from __future__ import annotations

from pathlib import Path

from lol_knowledge.objects import (
    Snapshot,
    build_model,
    validate_catalog_document,
    validate_object_catalog,
)
from lol_knowledge.objects.schema import CATALOG_KIND
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
