"""Structural and semantic validation of the curated object catalog."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .catalog import (
    ObjectModelError,
    Snapshot,
    derive_stats,
    derived_effect_status,
    description_text,
    load_catalog,
    load_snapshot,
    merge_generated,
)
from .formula import classify_formula, formula_issues
from .generate import dump_generated, generate_description_stats, load_generated
from .schema import (
    BASIS_STATES,
    CANONICAL_STAT_KINDS,
    CATALOG_KIND,
    CATALOG_RELATIVE_PATH,
    COMPONENT_KINDS,
    CONDITION_KINDS,
    DAMAGE_TYPES,
    EFFECT_KINDS,
    EFFECT_REVIEWS,
    EVIDENCE_CONFIDENCE,
    EVIDENCE_KINDS,
    GENERATED_STATS_RELATIVE_PATH,
    HEALING_MODES,
    LIMIT_KINDS,
    MODEL_STATUS_RANK,
    MODEL_STATUSES,
    OBJECT_SCHEMA_VERSION,
    RESTORE_RESOURCES,
    SCENARIOS,
    STAT_SCOPES_BY_STAT,
    TARGET_KINDS,
    TRIGGER_EVENTS,
)

REGENERATE = "regenerate it with python -m lol_knowledge.objects --generate-stats"
_NUMBER_PATTERN = re.compile(r"\d+(?:[.,]\d+)?")
_TOP_LEVEL_KEYS = {
    "schema_version",
    "kind",
    "catalog_version",
    "game_version",
    "notes",
    "objects",
}
_OBJECT_KEYS = {
    "id",
    "notes",
    "effect_review",
    "stats",
    "effects",
    "unmodelled_stats",
    "confirmed_zero_stats",
}
_CONFIRMED_ZERO_KEYS = {"id", "kind", "reason"}
_STAT_KEYS = {"id", "kind", "value", "status", "reason", "quote", "confirmed_zero"}
_EFFECT_KEYS = {
    "id",
    "kind",
    "name",
    "quote",
    "basis",
    "trigger",
    "target",
    "conditions",
    "components",
    "cooldown_seconds",
    "cooldown_reduced_by_attacks",
    "alternation",
    "stacks",
    "duration_seconds",
    "limits",
    "model_status",
    "note",
    "sources",
    "evidence_confidence",
    "scenario",
}
_COMPONENT_KEYS = {
    "damage_types",
    "kind",
    "formula",
    "damage_type",
    "target",
    "conditions",
    "stat",
    "scope",
    "mode",
    "direction",
    "source",
    "effect",
    "magnitude",
    "duration_seconds",
    "stacks",
    "note",
    "applies_life_steal",
    "resource",
}
_LIFE_STEAL_KEYS = {"value", "source"}
_LIMIT_KEYS = {"kind", "value", "unit", "condition"}
_SCALAR_KEYS = {"status", "reason"}
_STACK_KEYS = {"required", "window_seconds", "max_stacks"}
_REFUND_KEYS = {"seconds", "critical_seconds"}
_ALTERNATION_KEYS = {"group", "position", "of"}
_SOURCE_KEYS = {"kind", "reference", "quote", "retrieved_at", "confidence", "note"}
_SOURCE_CONFIDENCE = {
    "ddragon_description": {"official"},
    "community_wiki": {"secondary", "corroborated"},
    "community_dragon": {"secondary", "corroborated"},
    "in_game_measurement": {"secondary", "corroborated"},
    "client_data": {"secondary", "corroborated", "derived"},
    "patch_notes": {"official", "corroborated"},
}
# Client data values store percentages as fractions (0.09 for 9 %).
_FRACTION_SOURCES = frozenset({"client_data"})


@dataclass(frozen=True)
class ObjectViolation:
    """One concrete problem in the object catalog."""

    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


@dataclass(frozen=True)
class ObjectReport:
    """Result of validating the object catalog."""

    checked_files: int
    violations: tuple[ObjectViolation, ...]
    skipped: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.violations


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


# Spanish ordinals that stand for a count in descriptions ("Cada tercer ataque").
_ORDINALS = {"segundo": 2, "tercer": 3, "tercero": 3, "cuarto": 4, "quinto": 5, "sexto": 6}
_ORDINAL_PATTERN = re.compile(r"\b(" + "|".join(_ORDINALS) + r")\b", re.IGNORECASE)


def _quote_numbers(quote: str) -> set[float]:
    numbers: set[float] = {
        float(_ORDINALS[match.group(1).lower()]) for match in _ORDINAL_PATTERN.finditer(quote)
    }
    for match in _NUMBER_PATTERN.finditer(quote):
        try:
            numbers.add(float(match.group(0).replace(",", ".")))
        except ValueError:
            continue
    return numbers


def _quote_has_number(quote: str, value: float, *, fractions: bool = False) -> bool:
    target = abs(value)
    candidates = _quote_numbers(quote)
    if fractions:
        candidates |= {round(candidate * 100, 9) for candidate in candidates}
    return any(abs(candidate - target) < 1e-9 for candidate in candidates)


def _collect_constants(formula: Any, output: list[float]) -> None:
    if not isinstance(formula, Mapping):
        return
    operation = formula.get("op")
    if operation == "constant" and _is_number(formula.get("value")):
        output.append(float(formula["value"]))
        return
    if operation == "percent_of":
        if _is_number(formula.get("percent")):
            output.append(float(formula["percent"]))
        return
    if operation == "by_holder_range":
        for branch in ("melee", "ranged"):
            _collect_constants(formula.get(branch), output)
        return
    operands = formula.get("operands")
    if isinstance(operands, Sequence) and not isinstance(operands, (str, bytes)):
        for operand in operands:
            _collect_constants(operand, output)


def _effect_numbers(effect: Mapping[str, Any]) -> list[float]:
    numbers: list[float] = []
    for component in effect.get("components") or []:
        if not isinstance(component, Mapping):
            continue
        if "formula" in component:
            _collect_constants(component.get("formula"), numbers)
        if "magnitude" in component:
            _collect_constants(component.get("magnitude"), numbers)
        duration = component.get("duration_seconds")
        if _is_number(duration):
            numbers.append(float(duration))
    for key in ("cooldown_seconds", "duration_seconds"):
        value = effect.get(key)
        if _is_number(value):
            numbers.append(float(value))
    refund = effect.get("cooldown_reduced_by_attacks")
    if isinstance(refund, Mapping):
        numbers += [float(value) for value in refund.values() if _is_number(value)]
    for limit in effect.get("limits") or []:
        if isinstance(limit, Mapping) and _is_number(limit.get("value")):
            numbers.append(float(limit["value"]))
    stacks = effect.get("stacks")
    if isinstance(stacks, Mapping):
        for key in ("required", "max_stacks", "window_seconds"):
            value = stacks.get(key)
            # ``required: 1`` is "every attack", which a description says without a number.
            if _is_number(value) and not (key == "required" and value == 1):
                numbers.append(float(value))
    return numbers


class _CatalogChecker:
    def __init__(self, catalog: Mapping[str, Any], snapshot: Snapshot) -> None:
        self.catalog = catalog
        self.snapshot = snapshot
        self.violations: list[ObjectViolation] = []
        self.path = CATALOG_RELATIVE_PATH.as_posix()

    def fail(self, pointer: str, message: str) -> None:
        location = f"{self.path}:{pointer}" if pointer else self.path
        self.violations.append(ObjectViolation(location, message))

    def check(self) -> list[ObjectViolation]:
        self._check_header()
        objects = self.catalog.get("objects")
        if not isinstance(objects, Sequence) or isinstance(objects, (str, bytes)):
            self.fail("objects", "objects must be a list")
            return self.violations
        if not objects:
            self.fail("objects", "objects must not be empty")
            return self.violations
        seen_ids: set[str] = set()
        for index, entry in enumerate(objects):
            pointer = f"objects[{index}]"
            if not isinstance(entry, Mapping):
                self.fail(pointer, "object entry must be an object")
                continue
            item_id = entry.get("id")
            if not isinstance(item_id, str) or not item_id:
                self.fail(f"{pointer}.id", "id must be a non-empty string")
                continue
            if item_id in seen_ids:
                self.fail(f"{pointer}.id", f"duplicate object id {item_id!r}")
                continue
            seen_ids.add(item_id)
            if item_id not in self.snapshot.items:
                self.fail(f"{pointer}.id", f"item {item_id!r} is not in the snapshot")
                continue
            self._check_object(entry, self.snapshot.items[item_id], pointer)
        return self.violations

    def _check_header(self) -> None:
        unknown = set(self.catalog) - _TOP_LEVEL_KEYS
        if unknown:
            self.fail("", f"unknown top-level keys: {sorted(unknown)}")
        if self.catalog.get("schema_version") != OBJECT_SCHEMA_VERSION:
            self.fail(
                "schema_version",
                f"expected {OBJECT_SCHEMA_VERSION}, found {self.catalog.get('schema_version')!r}",
            )
        if self.catalog.get("kind") != CATALOG_KIND:
            self.fail("kind", f"expected {CATALOG_KIND!r}")
        version = self.catalog.get("catalog_version")
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            self.fail("catalog_version", "catalog_version must be a positive integer")
        notes = self.catalog.get("notes")
        if notes is not None and (not isinstance(notes, str) or not notes.strip()):
            self.fail("notes", "notes must be a non-empty string when present")
        if self.catalog.get("game_version") != self.snapshot.patch:
            self.fail(
                "game_version",
                (
                    f"catalog is for {self.catalog.get('game_version')!r} but the "
                    f"snapshot is {self.snapshot.patch!r}"
                ),
            )

    def _check_object(
        self,
        entry: Mapping[str, Any],
        item: Mapping[str, Any],
        pointer: str,
    ) -> None:
        unknown = set(entry) - _OBJECT_KEYS
        if unknown:
            self.fail(pointer, f"unknown object keys: {sorted(unknown)}")
        if entry.get("effect_review") not in EFFECT_REVIEWS:
            self.fail(
                f"{pointer}.effect_review",
                f"effect_review must be one of {sorted(EFFECT_REVIEWS)}",
            )
        description = item.get("description")
        if not isinstance(description, str):
            self.fail(f"{pointer}.id", f"item {entry.get('id')!r} has no description")
            return
        text = description_text(description)
        self._check_unmodelled(entry.get("unmodelled_stats"), text, f"{pointer}.unmodelled_stats")
        self._check_confirmed_zeros(
            entry.get("confirmed_zero_stats"), f"{pointer}.confirmed_zero_stats"
        )
        self._check_snapshot_references(entry, item, pointer)
        derived_stats, unmapped = derive_stats(item)
        for unknown_stat in unmapped:
            self.fail(
                f"{pointer}.id",
                f"snapshot stat {unknown_stat['key']!r} has no canonical mapping",
            )
        derived = {(stat["id"], stat["kind"]) for stat in derived_stats}
        seen_stats: set[tuple[str, str]] = set()
        stats = entry.get("stats")
        if stats is not None and (
            not isinstance(stats, Sequence) or isinstance(stats, (str, bytes))
        ):
            self.fail(f"{pointer}.stats", "stats must be a list")
            stats = []
        for index, stat in enumerate(stats or []):
            self._check_stat(stat, text, derived, seen_stats, f"{pointer}.stats[{index}]")
        seen_effects: set[str] = set()
        effects = entry.get("effects")
        if effects is not None and (
            not isinstance(effects, Sequence) or isinstance(effects, (str, bytes))
        ):
            self.fail(f"{pointer}.effects", "effects must be a list")
            effects = []
        for index, effect in enumerate(effects or []):
            self._check_effect(effect, text, seen_effects, f"{pointer}.effects[{index}]")

    def _check_unmodelled(self, lines: Any, text: str, pointer: str) -> None:
        """Description stat lines kept without a canonical stat, each with its reason."""
        if lines is None:
            return
        if not isinstance(lines, Sequence) or isinstance(lines, (str, bytes)) or not lines:
            self.fail(pointer, "unmodelled_stats must be a non-empty list")
            return
        for index, line in enumerate(lines):
            item_pointer = f"{pointer}[{index}]"
            if not isinstance(line, Mapping) or set(line) != {"quote", "reason"}:
                self.fail(item_pointer, "must be an object with quote and reason")
                continue
            if not isinstance(line["quote"], str) or line["quote"] not in text:
                self.fail(f"{item_pointer}.quote", "quote is not in the item description")
            if not isinstance(line["reason"], str) or not line["reason"].strip():
                self.fail(f"{item_pointer}.reason", "reason must be a non-empty string")

    def _check_snapshot_references(
        self,
        entry: Mapping[str, Any],
        item: Mapping[str, Any],
        pointer: str,
    ) -> None:
        for field in ("from", "into"):
            references = item.get(field)
            if references is None:
                continue
            if not isinstance(references, Sequence) or isinstance(references, (str, bytes)):
                self.fail(f"{pointer}.id", f"snapshot item field {field!r} is not a list")
                continue
            for index, reference in enumerate(references):
                if str(reference) not in self.snapshot.items:
                    self.fail(
                        f"{pointer}.id",
                        (
                            f"snapshot item field {field!r}[{index}] "
                            f"references unknown item {reference!r}"
                        ),
                    )
        maps = item.get("maps")
        if maps is not None:
            if not isinstance(maps, Mapping):
                self.fail(f"{pointer}.id", "snapshot item maps must be an object")
            else:
                for key in maps:
                    if not str(key).isdigit():
                        self.fail(
                            f"{pointer}.id",
                            f"snapshot item map key {key!r} is not a numeric id",
                        )

    def _check_stat(
        self,
        stat: Any,
        text: str,
        derived: set[tuple[str, str]],
        seen: set[tuple[str, str]],
        pointer: str,
    ) -> None:
        if not isinstance(stat, Mapping):
            self.fail(pointer, "stat entry must be an object")
            return
        unknown = set(stat) - _STAT_KEYS
        if unknown:
            self.fail(pointer, f"unknown stat keys: {sorted(unknown)}")
        stat_id = stat.get("id")
        kind = stat.get("kind")
        allowed_kinds = CANONICAL_STAT_KINDS.get(stat_id) if isinstance(stat_id, str) else None
        if allowed_kinds is None:
            self.fail(f"{pointer}.id", f"unknown stat id {stat_id!r}")
            return
        if kind not in allowed_kinds:
            self.fail(f"{pointer}.kind", f"stat {stat_id!r} does not support kind {kind!r}")
            return
        key = (stat_id, kind)
        if key in seen:
            self.fail(f"{pointer}.id", f"duplicate stat {stat_id!r}/{kind!r}")
        if key in derived:
            self.fail(
                f"{pointer}.id",
                f"stat {stat_id!r}/{kind!r} is already derived from the snapshot",
            )
        seen.add(key)
        quote = stat.get("quote")
        if not isinstance(quote, str) or not quote:
            self.fail(f"{pointer}.quote", "quote must be a non-empty string")
            return
        if quote not in text:
            self.fail(f"{pointer}.quote", "quote is not in the item description")
        if "value" in stat:
            value = stat["value"]
            if not _is_number(value):
                self.fail(f"{pointer}.value", "value must be a finite number")
            elif not _quote_has_number(quote, float(value)):
                self.fail(
                    f"{pointer}.value",
                    f"value {value!r} does not appear in the quote",
                )
            if stat.get("status") not in {None, "declared"}:
                self.fail(f"{pointer}.status", "status must be 'declared' when value is present")
            if "reason" in stat:
                self.fail(f"{pointer}.reason", "reason is only allowed for unknown values")
        else:
            if stat.get("status") != "unknown":
                self.fail(f"{pointer}.status", "stat needs a value or status 'unknown'")
            reason = stat.get("reason")
            if not isinstance(reason, str) or not reason.strip():
                self.fail(f"{pointer}.reason", "unknown stats need a non-empty reason")

    def _check_effect(
        self,
        effect: Any,
        text: str,
        seen: set[str],
        pointer: str,
    ) -> None:
        if not isinstance(effect, Mapping):
            self.fail(pointer, "effect entry must be an object")
            return
        unknown = set(effect) - _EFFECT_KEYS
        if unknown:
            self.fail(pointer, f"unknown effect keys: {sorted(unknown)}")
        effect_id = effect.get("id")
        if not isinstance(effect_id, str) or not effect_id:
            self.fail(f"{pointer}.id", "effect id must be a non-empty string")
        elif effect_id in seen:
            self.fail(f"{pointer}.id", f"duplicate effect id {effect_id!r}")
        else:
            seen.add(effect_id)
        if effect.get("kind") not in EFFECT_KINDS:
            self.fail(f"{pointer}.kind", f"effect kind must be one of {sorted(EFFECT_KINDS)}")
        if not isinstance(effect.get("name"), str) or not effect.get("name"):
            self.fail(f"{pointer}.name", "effect name must be a non-empty string")
        if effect.get("basis") not in BASIS_STATES:
            self.fail(f"{pointer}.basis", f"basis must be one of {sorted(BASIS_STATES)}")
        quote = effect.get("quote")
        if not isinstance(quote, str) or not quote:
            self.fail(f"{pointer}.quote", "quote must be a non-empty string")
            quote = ""
        elif quote not in text:
            self.fail(f"{pointer}.quote", "quote is not in the item description")
        self._check_trigger(effect.get("trigger"), f"{pointer}.trigger")
        self._check_target(effect.get("target"), f"{pointer}.target", required=True)
        self._check_conditions(effect.get("conditions"), f"{pointer}.conditions")
        components = effect.get("components")
        if not isinstance(components, Sequence) or isinstance(components, (str, bytes)):
            self.fail(f"{pointer}.components", "components must be a list")
        elif not components and effect.get("model_status") != "excluded":
            self.fail(f"{pointer}.components", "only excluded effects may have no components")
        else:
            for index, component in enumerate(components):
                self._check_component(component, f"{pointer}.components[{index}]")
        self._check_scalar(effect.get("cooldown_seconds"), f"{pointer}.cooldown_seconds")
        self._check_refund(effect, f"{pointer}.cooldown_reduced_by_attacks")
        self._check_alternation(effect.get("alternation"), f"{pointer}.alternation")
        self._check_stacking(effect, pointer)
        self._check_scalar(effect.get("duration_seconds"), f"{pointer}.duration_seconds")
        self._check_stacks(effect.get("stacks"), f"{pointer}.stacks")
        self._check_limits(effect.get("limits"), f"{pointer}.limits")
        self._check_scenario(effect, f"{pointer}.scenario")
        sources = self._check_sources(effect.get("sources"), f"{pointer}.sources")
        confidence = effect.get("evidence_confidence")
        if confidence is not None and confidence not in EVIDENCE_CONFIDENCE:
            self.fail(
                f"{pointer}.evidence_confidence",
                f"evidence_confidence must be one of {sorted(EVIDENCE_CONFIDENCE)}",
            )
        if sources and confidence is None:
            self.fail(
                f"{pointer}.evidence_confidence",
                "effects with sources need an explicit evidence_confidence",
            )
        if confidence in {"secondary", "corroborated", "derived", "unverified"} and not sources:
            self.fail(
                f"{pointer}.sources",
                f"evidence_confidence {confidence!r} needs at least one source",
            )
        if confidence == "official" and sources:
            self.fail(
                f"{pointer}.evidence_confidence",
                "official evidence must come from the Data Dragon description, not sources",
            )
        if confidence == "derived" and not any(
            source.get("kind") == "client_data" for source in sources
        ):
            self.fail(
                f"{pointer}.evidence_confidence",
                "derived evidence needs a client_data source",
            )
        if confidence == "corroborated" and len(sources) < 2:
            self.fail(
                f"{pointer}.sources",
                "corroborated evidence needs at least two independent sources",
            )
        status = effect.get("model_status")
        if status not in MODEL_STATUSES:
            self.fail(
                f"{pointer}.model_status", f"model_status must be one of {sorted(MODEL_STATUSES)}"
            )
            return
        cited_texts = [(quote, False)] + [
            (source["quote"], source.get("kind") in _FRACTION_SOURCES) for source in sources
        ]
        for number in _effect_numbers(effect):
            if not any(
                _quote_has_number(text, number, fractions=fractions)
                for text, fractions in cited_texts
            ):
                self.fail(
                    f"{pointer}.quote",
                    f"number {number!r} is not present in any cited quote",
                )
        derived = derived_effect_status(effect)
        if MODEL_STATUS_RANK[status] > MODEL_STATUS_RANK[derived]:
            self.fail(
                f"{pointer}.model_status",
                f"{status!r} is more optimistic than the formulas allow ({derived!r})",
            )
        basis = effect.get("basis")
        formula_states = [
            classify_formula(component.get("formula"))
            for component in components or []
            if isinstance(component, Mapping) and "formula" in component
        ]
        if basis == "description_explicit" and any(
            state != "evaluable" for state in formula_states
        ):
            self.fail(
                f"{pointer}.basis",
                "description_explicit requires every formula to be evaluable",
            )
        if basis == "description_partial" and not any(
            state != "evaluable" for state in formula_states
        ):
            self.fail(
                f"{pointer}.basis",
                "description_partial needs at least one non-evaluable formula",
            )
        if basis == "external_evidence_explicit":
            if not sources:
                self.fail(
                    f"{pointer}.basis",
                    "external_evidence_explicit needs at least one declared source",
                )
            if any(state != "evaluable" for state in formula_states):
                self.fail(
                    f"{pointer}.basis",
                    "external_evidence_explicit requires every formula to be evaluable",
                )

    def _check_scenario(self, effect: Mapping[str, Any], pointer: str) -> None:
        if "scenario" not in effect:
            return
        if effect["scenario"] not in SCENARIOS:
            self.fail(pointer, f"scenario must be one of {sorted(SCENARIOS)}")
            return
        components = effect.get("components")
        if not isinstance(components, Sequence) or isinstance(components, (str, bytes)):
            return
        for index, component in enumerate(components):
            if not isinstance(component, Mapping):
                continue
            stat = component.get("kind") == "stat_modifier" and component.get("mode") == "flat"
            dealt = (
                component.get("kind") == "damage_modifier" and component.get("direction") == "dealt"
            )
            if not (stat or dealt):
                self.fail(
                    f"{pointer[: -len('.scenario')]}.components[{index}]",
                    "a max_stacks effect may only have flat stat_modifier or dealt "
                    "damage_modifier components",
                )

    def _check_confirmed_zeros(self, entries: Any, pointer: str) -> None:
        if entries is None:
            return
        if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes)) or not entries:
            self.fail(pointer, "confirmed_zero_stats must be a non-empty list")
            return
        for index, entry in enumerate(entries):
            item_pointer = f"{pointer}[{index}]"
            if not isinstance(entry, Mapping) or set(entry) != _CONFIRMED_ZERO_KEYS:
                self.fail(item_pointer, "must be an object with id, kind and reason")
                continue
            stat, kind = entry["id"], entry["kind"]
            if stat not in CANONICAL_STAT_KINDS or kind not in CANONICAL_STAT_KINDS[stat]:
                self.fail(item_pointer, f"unknown stat {stat!r} of kind {kind!r}")
            if not isinstance(entry["reason"], str) or not entry["reason"].strip():
                self.fail(f"{item_pointer}.reason", "reason must be a non-empty string")

    def _check_sources(self, sources: Any, pointer: str) -> list[Mapping[str, Any]]:
        if sources is None:
            return []
        if not isinstance(sources, Sequence) or isinstance(sources, (str, bytes)):
            self.fail(pointer, "sources must be a list")
            return []
        if not sources:
            self.fail(pointer, "sources must not be empty when present")
            return []
        checked: list[Mapping[str, Any]] = []
        for index, source in enumerate(sources):
            item_pointer = f"{pointer}[{index}]"
            if not isinstance(source, Mapping):
                self.fail(item_pointer, "source must be an object")
                continue
            unknown = set(source) - _SOURCE_KEYS
            if unknown:
                self.fail(item_pointer, f"unknown source keys: {sorted(unknown)}")
            if source.get("kind") not in EVIDENCE_KINDS:
                self.fail(
                    f"{item_pointer}.kind",
                    f"source kind must be one of {sorted(EVIDENCE_KINDS)}",
                )
            if source.get("confidence") not in EVIDENCE_CONFIDENCE:
                self.fail(
                    f"{item_pointer}.confidence",
                    f"source confidence must be one of {sorted(EVIDENCE_CONFIDENCE)}",
                )
            allowed_confidence = _SOURCE_CONFIDENCE.get(source.get("kind"))
            if (
                allowed_confidence is not None
                and source.get("confidence") not in allowed_confidence
            ):
                self.fail(
                    f"{item_pointer}.confidence",
                    (f"source kind {source.get('kind')!r} cannot be {source.get('confidence')!r}"),
                )
            required_valid = True
            for field in ("reference", "quote", "retrieved_at"):
                value = source.get(field)
                if not isinstance(value, str) or not value.strip():
                    self.fail(
                        f"{item_pointer}.{field}",
                        f"source {field} must be a non-empty string",
                    )
                    required_valid = False
            note = source.get("note")
            if note is not None and (not isinstance(note, str) or not note.strip()):
                self.fail(f"{item_pointer}.note", "source note must be a non-empty string")
            if required_valid:
                checked.append(source)
        return checked

    def _check_trigger(self, trigger: Any, pointer: str) -> None:
        if not isinstance(trigger, Mapping):
            self.fail(pointer, "trigger must be an object")
            return
        if set(trigger) - {"event"}:
            self.fail(pointer, f"unknown trigger keys: {sorted(set(trigger) - {'event'})}")
        if trigger.get("event") not in TRIGGER_EVENTS:
            self.fail(f"{pointer}.event", f"event must be one of {sorted(TRIGGER_EVENTS)}")

    def _check_target(self, target: Any, pointer: str, *, required: bool = False) -> None:
        if target is None:
            if required:
                self.fail(pointer, "target must be an object")
            return
        if not isinstance(target, Mapping):
            self.fail(pointer, "target must be an object")
            return
        if set(target) - {"kind"}:
            self.fail(pointer, f"unknown target keys: {sorted(set(target) - {'kind'})}")
        if target.get("kind") not in TARGET_KINDS:
            self.fail(f"{pointer}.kind", f"target kind must be one of {sorted(TARGET_KINDS)}")

    def _check_conditions(self, conditions: Any, pointer: str) -> None:
        if conditions is None:
            return
        if not isinstance(conditions, Sequence) or isinstance(conditions, (str, bytes)):
            self.fail(pointer, "conditions must be a list")
            return
        for index, condition in enumerate(conditions):
            item_pointer = f"{pointer}[{index}]"
            if not isinstance(condition, Mapping):
                self.fail(item_pointer, "condition must be an object")
                continue
            if set(condition) - {"kind", "value"}:
                self.fail(
                    item_pointer,
                    f"unknown condition keys: {sorted(set(condition) - {'kind', 'value'})}",
                )
            if condition.get("kind") not in CONDITION_KINDS:
                self.fail(
                    f"{item_pointer}.kind",
                    f"condition kind must be one of {sorted(CONDITION_KINDS)}",
                )
            elif condition["kind"] == "stacks_full":
                value = condition.get("value")
                if not isinstance(value, str) or not value:
                    self.fail(
                        f"{item_pointer}.value", "stacks_full needs the id of a stacking effect"
                    )
            elif condition["kind"] in {"target_health_below", "target_health_above"}:
                value = condition.get("value")
                if not _is_number(value) or not 0 < value < 100:
                    self.fail(
                        f"{item_pointer}.value",
                        "a target health threshold needs a percentage between 0 and 100",
                    )

    def _check_component(self, component: Any, pointer: str) -> None:
        if not isinstance(component, Mapping):
            self.fail(pointer, "component must be an object")
            return
        unknown = set(component) - _COMPONENT_KEYS
        if unknown:
            self.fail(pointer, f"unknown component keys: {sorted(unknown)}")
        kind = component.get("kind")
        if kind not in COMPONENT_KINDS:
            self.fail(f"{pointer}.kind", f"component kind must be one of {sorted(COMPONENT_KINDS)}")
            return
        self._check_conditions(component.get("conditions"), f"{pointer}.conditions")
        self._check_target(component.get("target"), f"{pointer}.target")
        self._check_scalar(component.get("duration_seconds"), f"{pointer}.duration_seconds")
        self._check_stacks(component.get("stacks"), f"{pointer}.stacks")
        if "formula" in component:
            self._check_formula(component.get("formula"), f"{pointer}.formula")
        if "applies_life_steal" in component:
            self._check_life_steal(
                component["applies_life_steal"], kind, f"{pointer}.applies_life_steal"
            )
        if kind == "damage":
            if component.get("damage_type") not in DAMAGE_TYPES:
                self.fail(
                    f"{pointer}.damage_type", f"damage_type must be one of {sorted(DAMAGE_TYPES)}"
                )
            if "formula" not in component:
                self.fail(f"{pointer}.formula", "damage components need a formula")
        elif kind in {"healing", "shield"}:
            if "formula" not in component:
                self.fail(f"{pointer}.formula", f"{kind} components need a formula")
            if component.get("mode") not in HEALING_MODES:
                self.fail(
                    f"{pointer}.mode",
                    f"{kind} mode must be one of {sorted(HEALING_MODES)}",
                )
        elif kind == "resource_restore":
            if component.get("resource") not in RESTORE_RESOURCES:
                self.fail(
                    f"{pointer}.resource",
                    f"resource_restore resource must be one of {sorted(RESTORE_RESOURCES)}",
                )
            if "formula" not in component:
                self.fail(f"{pointer}.formula", "resource_restore components need a formula")
        elif kind == "stat_modifier":
            stat = component.get("stat")
            scope = component.get("scope")
            if stat not in STAT_SCOPES_BY_STAT:
                self.fail(f"{pointer}.stat", f"unknown stat_modifier stat {stat!r}")
            elif scope not in STAT_SCOPES_BY_STAT[stat]:
                self.fail(
                    f"{pointer}.scope",
                    f"stat {stat!r} does not support scope {scope!r}",
                )
            if component.get("mode") not in {"flat", "percent"}:
                self.fail(f"{pointer}.mode", "stat_modifier mode must be 'flat' or 'percent'")
            if "formula" not in component:
                self.fail(f"{pointer}.formula", "stat_modifier components need a formula")
        elif kind == "burn":
            if component.get("damage_type") not in DAMAGE_TYPES:
                self.fail(
                    f"{pointer}.damage_type", f"damage_type must be one of {sorted(DAMAGE_TYPES)}"
                )
            if "formula" not in component:
                self.fail(f"{pointer}.formula", "burn components need a per-second formula")
            duration = component.get("duration_seconds")
            if not _is_number(duration) or duration <= 0:
                self.fail(f"{pointer}.duration_seconds", "a burn needs a positive duration")
        elif kind == "execute":
            if "formula" not in component:
                self.fail(f"{pointer}.formula", "execute components need a threshold formula")
        elif kind == "damage_modifier":
            types = component.get("damage_types")
            if types is not None and (
                not isinstance(types, list) or not types or not set(types) <= DAMAGE_TYPES
            ):
                self.fail(
                    f"{pointer}.damage_types",
                    f"damage_types must be a non-empty list of {sorted(DAMAGE_TYPES)}",
                )
            if component.get("direction") not in {"dealt", "taken"}:
                self.fail(f"{pointer}.direction", "direction must be 'dealt' or 'taken'")
            if component.get("source") not in {"attack", "ability", "all"}:
                self.fail(f"{pointer}.source", "source must be 'attack', 'ability' or 'all'")
            if component.get("mode") != "percent":
                self.fail(f"{pointer}.mode", "damage_modifier mode must be 'percent'")
            if "formula" not in component:
                self.fail(f"{pointer}.formula", "damage_modifier components need a formula")
        elif kind in {"crowd_control", "status"}:
            if not isinstance(component.get("effect"), str) or not component.get("effect"):
                self.fail(f"{pointer}.effect", f"{kind} components need a non-empty effect name")
            if "magnitude" not in component:
                self.fail(f"{pointer}.magnitude", f"{kind} components need a magnitude")
            else:
                self._check_formula(component.get("magnitude"), f"{pointer}.magnitude")
        elif kind == "stasis":
            if component.get("duration_seconds") is None:
                self.fail(f"{pointer}.duration_seconds", "stasis needs a duration")

    def _check_life_steal(self, declaration: Any, kind: Any, pointer: str) -> None:
        """Whether a damage component heals through life steal, with its own source."""
        if kind != "damage":
            self.fail(pointer, "only damage components can declare applies_life_steal")
            return
        if not isinstance(declaration, Mapping):
            self.fail(pointer, "applies_life_steal must be an object with value and source")
            return
        unknown = set(declaration) - _LIFE_STEAL_KEYS
        if unknown:
            self.fail(pointer, f"unknown applies_life_steal keys: {sorted(unknown)}")
        if not isinstance(declaration.get("value"), bool):
            self.fail(f"{pointer}.value", "applies_life_steal value must be true or false")
        source = declaration.get("source")
        if source is None:
            self.fail(f"{pointer}.source", "applies_life_steal needs a source")
            return
        self._check_sources([source], f"{pointer}.source")

    def _check_formula(self, formula: Any, pointer: str) -> None:
        for message in formula_issues(formula):
            self.fail(pointer, message)

    def _check_scalar(self, value: Any, pointer: str) -> None:
        if value is None:
            return
        if isinstance(value, Mapping):
            if set(value) - _SCALAR_KEYS:
                self.fail(pointer, f"unknown scalar keys: {sorted(set(value) - _SCALAR_KEYS)}")
            if value.get("status") != "unknown":
                self.fail(pointer, "scalar object must have status 'unknown'")
            reason = value.get("reason")
            if not isinstance(reason, str) or not reason.strip():
                self.fail(f"{pointer}.reason", "unknown scalars need a non-empty reason")
            return
        if not _is_number(value) or value < 0:
            self.fail(pointer, "scalar must be null, a non-negative number or an unknown marker")

    def _check_alternation(self, alternation: Any, pointer: str) -> None:
        """Effects of one ``group`` take turns, attack by attack (Terminus, combat-stacks.md)."""
        if alternation is None:
            return
        if not isinstance(alternation, Mapping) or set(alternation) != _ALTERNATION_KEYS:
            self.fail(pointer, f"must be an object with exactly {sorted(_ALTERNATION_KEYS)}")
            return
        group, position, size = alternation["group"], alternation["position"], alternation["of"]
        if not isinstance(group, str) or not group:
            self.fail(f"{pointer}.group", "must be a non-empty string")
        whole = all(
            isinstance(value, int) and not isinstance(value, bool) for value in (position, size)
        )
        if not whole or size < 2 or not 1 <= position <= size:
            self.fail(pointer, "position and of must be integers with 1 <= position <= of, of >= 2")

    def _check_stacking(self, effect: Mapping[str, Any], pointer: str) -> None:
        """Stacks gained one per attack need a maximum; seconds in combat need a cap."""
        event = (
            (effect.get("trigger") or {}).get("event")
            if isinstance(effect.get("trigger"), Mapping)
            else None
        )
        stacks = effect.get("stacks")
        per_attack = isinstance(stacks, Mapping) and stacks.get("required") == 1
        if per_attack and event == "on_attack" and not isinstance(stacks.get("max_stacks"), int):
            self.fail(f"{pointer}.stacks.max_stacks", "stacks gained per attack need a maximum")
        if event == "in_combat" and not any(
            isinstance(limit, Mapping) and limit.get("kind") == "maximum"
            for limit in effect.get("limits") or ()
        ):
            self.fail(f"{pointer}.limits", "an in_combat effect needs a maximum limit")
        if "alternation" in effect and not (
            isinstance(stacks, Mapping) and stacks.get("required") == 1
        ):
            self.fail(f"{pointer}.alternation", "only effects with stacks per attack alternate")

    def _check_refund(self, effect: Mapping[str, Any], pointer: str) -> None:
        """Seconds each basic attack (and a critical one) takes off the cooldown."""
        if "cooldown_reduced_by_attacks" not in effect:
            return
        refund = effect["cooldown_reduced_by_attacks"]
        if not isinstance(refund, Mapping) or set(refund) != _REFUND_KEYS:
            self.fail(pointer, f"must be an object with exactly {sorted(_REFUND_KEYS)}")
            return
        for key in sorted(_REFUND_KEYS):
            value = refund[key]
            if not _is_number(value) or value <= 0:
                self.fail(f"{pointer}.{key}", "must be a positive number of seconds")
        if not _is_number(effect.get("cooldown_seconds")):
            self.fail(pointer, "needs a numeric cooldown_seconds")

    def _check_stacks(self, stacks: Any, pointer: str) -> None:
        if stacks is None:
            return
        if not isinstance(stacks, Mapping):
            self.fail(pointer, "stacks must be an object or null")
            return
        if set(stacks) - _STACK_KEYS:
            self.fail(pointer, f"unknown stacks keys: {sorted(set(stacks) - _STACK_KEYS)}")
        required = stacks.get("required")
        if not isinstance(required, int) or isinstance(required, bool) or required < 1:
            self.fail(f"{pointer}.required", "required must be a positive integer")
        max_stacks = stacks.get("max_stacks")
        if max_stacks is not None and (
            not isinstance(max_stacks, int) or isinstance(max_stacks, bool) or max_stacks < 1
        ):
            self.fail(f"{pointer}.max_stacks", "max_stacks must be a positive integer or null")
        self._check_scalar(stacks.get("window_seconds"), f"{pointer}.window_seconds")

    def _check_limits(self, limits: Any, pointer: str) -> None:
        if limits is None:
            return
        if not isinstance(limits, Sequence) or isinstance(limits, (str, bytes)):
            self.fail(pointer, "limits must be a list")
            return
        for index, limit in enumerate(limits):
            item_pointer = f"{pointer}[{index}]"
            if not isinstance(limit, Mapping):
                self.fail(item_pointer, "limit must be an object")
                continue
            if set(limit) - _LIMIT_KEYS:
                self.fail(item_pointer, f"unknown limit keys: {sorted(set(limit) - _LIMIT_KEYS)}")
            if limit.get("kind") not in LIMIT_KINDS:
                self.fail(
                    f"{item_pointer}.kind", f"limit kind must be one of {sorted(LIMIT_KINDS)}"
                )
            if not _is_number(limit.get("value")):
                self.fail(f"{item_pointer}.value", "limit value must be a finite number")
            if limit.get("unit") not in {"percent", "flat", "seconds"}:
                self.fail(
                    f"{item_pointer}.unit", "limit unit must be 'percent', 'flat' or 'seconds'"
                )
            condition = limit.get("condition")
            if condition is not None and (not isinstance(condition, str) or not condition):
                self.fail(f"{item_pointer}.condition", "condition must be a non-empty string")


def validate_catalog_document(
    catalog: Mapping[str, Any],
    snapshot: Snapshot,
) -> ObjectReport:
    """Validate a parsed catalog against a parsed snapshot (pure, deterministic)."""
    if not isinstance(catalog, Mapping):
        return ObjectReport(
            checked_files=1,
            violations=(
                ObjectViolation(CATALOG_RELATIVE_PATH.as_posix(), "catalog must be a JSON object"),
            ),
        )
    violations = _CatalogChecker(catalog, snapshot).check()
    violations.sort(key=lambda item: (item.path, item.message))
    return ObjectReport(checked_files=1, violations=tuple(violations))


def validate_object_catalog(root: Path) -> ObjectReport:
    """Validate ``lol-knowledge/objects`` for a project root."""
    catalog_path = root / CATALOG_RELATIVE_PATH
    objects_dir = catalog_path.parent
    if not objects_dir.is_dir():
        return ObjectReport(
            checked_files=0,
            violations=(),
            skipped=(
                "lol-knowledge/objects/ is not present; object catalog validation was skipped",
            ),
        )
    if not catalog_path.is_file():
        return ObjectReport(
            checked_files=0,
            violations=(ObjectViolation(catalog_path.as_posix(), "catalog.json not found"),),
        )
    if not (objects_dir / "README.md").is_file():
        return ObjectReport(
            checked_files=1,
            violations=(
                ObjectViolation((objects_dir / "README.md").as_posix(), "README.md not found"),
            ),
        )
    try:
        snapshot = load_snapshot(root)
        catalog = load_catalog(root)
        generated = load_generated(root)
    except ObjectModelError as exc:
        return ObjectReport(
            checked_files=1,
            violations=(ObjectViolation(catalog_path.as_posix(), str(exc)),),
        )
    generated_violations = _generated_violations(catalog, generated, snapshot)
    report = validate_catalog_document(merge_generated(catalog, generated), snapshot)
    return ObjectReport(
        checked_files=report.checked_files + (generated is not None),
        violations=(*generated_violations, *report.violations),
        skipped=report.skipped,
    )


def _generated_violations(
    catalog: Mapping[str, Any], generated: Mapping[str, Any] | None, snapshot: Snapshot
) -> tuple[ObjectViolation, ...]:
    """The generated stats must exist, be current and be the only source of their stats."""
    path = GENERATED_STATS_RELATIVE_PATH.as_posix()
    if generated is None:
        return (ObjectViolation(path, f"not found; {REGENERATE}"),)
    try:
        expected = generate_description_stats(snapshot)
    except ObjectModelError as exc:
        return (ObjectViolation(path, f"cannot be generated from the snapshot: {exc}"),)
    violations = []
    if dump_generated(generated) != dump_generated(expected):
        violations.append(ObjectViolation(path, f"does not match the snapshot; {REGENERATE}"))
    covered = {str(entry.get("id")) for entry in expected["objects"]}
    unknown = {
        (str(entry.get("id")), str(stat.get("id")), str(stat.get("kind")))
        for entry in expected["objects"]
        for stat in entry.get("stats") or []
        if stat.get("status") == "unknown"
    }
    for index, entry in enumerate(catalog.get("objects") or []):
        if str(entry.get("id")) in covered and entry.get("stats"):
            violations.append(
                ObjectViolation(
                    f"objects[{index}].stats",
                    f"item {entry.get('id')} takes its description stats from {path}",
                )
            )
        confirmed = entry.get("confirmed_zero_stats")
        if not isinstance(confirmed, Sequence) or isinstance(confirmed, (str, bytes)):
            continue
        for position, zero in enumerate(confirmed):
            if not isinstance(zero, Mapping):
                continue
            key = (str(entry.get("id")), str(zero.get("id")), str(zero.get("kind")))
            if key not in unknown:
                violations.append(
                    ObjectViolation(
                        f"objects[{index}].confirmed_zero_stats[{position}]",
                        f"{path} has no unknown {key[1]} ({key[2]}) for item {key[0]}",
                    )
                )
    return tuple(violations)
