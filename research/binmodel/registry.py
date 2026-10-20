"""Load and query the compact bin class registry."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .hashes import is_hash_name, normalize_field, normalize_type

DEFAULT_SCHEMA = Path(__file__).with_name("schema") / "lol_classes.json"


@dataclass(frozen=True)
class PropertyDef:
    """One property of a bin class."""

    key: str
    name: str
    type: str
    key_type: str | None = None
    value_type: str | None = None
    class_ref: str | None = None
    provisional_name: str | None = None

    @property
    def resolved(self) -> bool:
        return not is_hash_name(self.name)


@dataclass(frozen=True)
class ClassDef:
    """One bin class, either officially named or identified by hash."""

    key: str
    name: str
    type_hash: str | None
    base: str | None
    properties: Mapping[str, PropertyDef]
    provisional_name: str | None = None

    @property
    def resolved(self) -> bool:
        return self.type_hash is None


class Registry:
    """Resolve type and field hashes against the compact registry."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DEFAULT_SCHEMA
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self.schema_version = int(raw["schema_version"])
        self.provenance = dict(raw.get("provenance", {}))
        self.field_hashes = {
            normalize_field(key): value for key, value in raw.get("field_hashes", {}).items()
        }
        self._classes: dict[str, ClassDef] = {}
        for key, entry in raw["classes"].items():
            properties: dict[str, PropertyDef] = {}
            for prop_key, prop in entry.get("properties", {}).items():
                prop_def = PropertyDef(
                    key=prop_key,
                    name=prop.get("name") or prop_key,
                    type=prop.get("type", "Unknown"),
                    key_type=prop.get("key_type"),
                    value_type=prop.get("value_type"),
                    class_ref=prop.get("class_ref"),
                    provisional_name=prop.get("provisional_name"),
                )
                properties[normalize_field(prop_key)] = prop_def
            type_hash = normalize_type(entry.get("hash"))
            self._classes[normalize_type(key) or key] = ClassDef(
                key=key,
                name=key if type_hash is None else (entry.get("provisional_name") or key),
                type_hash=type_hash,
                base=entry.get("base"),
                properties=properties,
                provisional_name=entry.get("provisional_name"),
            )

    def class_for(self, value: str | None) -> ClassDef | None:
        """Return the class definition for a ``__type`` value, or ``None``."""
        return self._classes.get(normalize_type(value) or "")

    def type_name(self, value: str | None) -> str | None:
        """Return the public or provisional name of a type."""
        entry = self.class_for(value)
        if entry is None:
            return None
        if entry.resolved:
            return entry.name
        return entry.provisional_name

    def provisional(self, value: str | None) -> bool:
        entry = self.class_for(value)
        return bool(entry and not entry.resolved)

    def property_for(self, class_value: str | None, field_key: str) -> PropertyDef | None:
        entry = self.class_for(class_value)
        if entry is None:
            return None
        return entry.properties.get(normalize_field(field_key))

    def field_name(self, class_value: str | None, field_key: str) -> str:
        """Return a public or provisional field name, or ``0x<key>``."""
        normalized = normalize_field(field_key)
        prop = self.property_for(class_value, normalized)
        if prop is not None:
            if prop.resolved:
                return prop.name
            if prop.provisional_name:
                return prop.provisional_name
        return self.field_hashes.get(normalized, f"0x{normalized}")

    def describe_type(self, value: str | None) -> dict[str, Any]:
        """Return a JSON-ready description of a type."""
        entry = self.class_for(value)
        normalized = normalize_type(value)
        if entry is None:
            return {
                "raw": value,
                "type_hash": normalized if normalized and normalized.startswith("0x") else None,
                "name": None,
                "provisional_name": None,
                "base": None,
                "resolved": False,
            }
        return {
            "raw": value,
            "type_hash": entry.type_hash,
            "name": entry.name if entry.resolved else None,
            "provisional_name": entry.provisional_name,
            "base": entry.base,
            "resolved": entry.resolved,
        }
