"""Extract runes (perks) from the local client: trees, rows, shards, values and texts.

The ``perks`` bin of ``DATA/FINAL/Global.wad.client`` holds:

- one ``PerkStyle`` record per rune tree (``Perks/Styles/<Tree>``): its id, the
  trees allowed as secondary (``mAllowedSubStyles``), its rows (``mSlots``: the
  keystone row has ``mType`` 0, the other rows 3), the bonus rune granted per
  secondary tree (``mSubStyleBonus``) and the links to the three shard rows
  (``mSlotlinks``);
- one ``PerkSlot`` record per shard row (``Perks/StatMods/Slots/<Row>``);
- one ``Perk`` record per rune and shard, whose script data keeps named values
  (``mEffectAmount``), per-mode overrides (``mEffectAmountGameMode``) and the
  calculation trees that tooltips show (``mCalculations``).

Names in those maps are FNV-1a hashes; they are named only when a placeholder of
the rune's localized texts (``@StatGain@``) has the same hash. Texts come from
the RST string table (``Localized/Global.<locale>.wad.client``), by the
localization keys the record gives.

Usage::

    python -m binmodel.perks --wad "<Game>/DATA/FINAL/Global.wad.client" \\
        --strings "<Game>/DATA/FINAL/Localized/Global.es_ES.wad.client" \\
        --rst-hashes hashes.rst.xxh3.txt --content-version <version> \\
        --retrieved-at 2026-11-19 --output lol-knowledge/derived/runes.json

Nothing is filled in: a value or a field the record lacks stays absent or
``null``, and a hash without a known name stays ``{xxxxxxxx}``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .hashes import fnv1a32
from .item_effects import _tree, expand_templates, load_strings, placeholder_names
from .items import ItemError, _mode
from .propbin import Entry, ListValue, MapValue, ObjectValue, PropError, Value, parse_prop
from .records import CONTENT_VERSION, f32_decimal
from .wad import WadError, read_entry

SCHEMA = "lol-derived-runes/1"
WAD_ENTRY = "perks"
PERK = fnv1a32("Perk")
STYLE = fnv1a32("PerkStyle")
SLOT = fnv1a32("PerkSlot")
F = {
    name: fnv1a32(name)
    for name in (
        "mPerkId",
        "mPerkName",
        "mEnabled",
        "mStackable",
        "mScript",
        "mSpellScriptName",
        "mSpellScriptData",
        "mEffectAmount",
        "mEffectAmountGameMode",
        "mEffectAmountPerMode",
        "mCalculations",
        "mPerkStyleId",
        "mPerkStyleName",
        "mAllowedSubStyles",
        "mSlots",
        "mSlotlinks",
        "mSubStyleBonus",
        "mStyleId",
        "mPerk",
        "mType",
        "mPerks",
        "mSlotLabelKey",
        "mDisplayNameLocalizationKey",
        "mTooltipNameLocalizationKey",
        "mShortDescLocalizationKey",
        "mLongDescLocalizationKey",
    )
}
TEXT_KEYS = {
    "name": "mDisplayNameLocalizationKey",
    "tooltip": "mTooltipNameLocalizationKey",
    "short_desc": "mShortDescLocalizationKey",
    "long_desc": "mLongDescLocalizationKey",
}
RUNTIME_PLACEHOLDER = re.compile(r"[fF]\d+")


class PerkError(ItemError):
    """The perks bin cannot be read without guessing."""


def _hex(value: int) -> str:
    return f"{{{value:08x}}}"


def _field(entry: Any, name: str) -> Any:
    fields = entry.fields
    return fields.get(F[name])


def _scalar(node: Any, kind: type, where: str, *, optional: bool = False) -> Any:
    if node is None and optional:
        return None
    if not isinstance(node, Value) or not isinstance(node.value, kind):
        raise PerkError(f"{where} is not a {kind.__name__}")
    return node.value


def _links(node: Any, where: str) -> list[int]:
    if not isinstance(node, ListValue) or not all(
        isinstance(item, Value) and isinstance(item.value, int) for item in node.items
    ):
        raise PerkError(f"{where} is not a list of links")
    return [int(item.value) for item in node.items]


def _amounts(node: Any, names: Mapping[int, str], where: str) -> dict[str, float]:
    if node is None:
        return {}
    if not isinstance(node, MapValue):
        raise PerkError(f"{where} is not a map")
    result: dict[str, float] = {}
    for key, value in node.items:
        if not isinstance(key, Value) or not isinstance(key.value, int):
            raise PerkError(f"{where}: key is not a hash")
        if not isinstance(value, Value) or not isinstance(value.value, float):
            raise PerkError(f"{where}: value is not a float")
        result[names.get(key.value, _hex(key.value))] = f32_decimal(value.value)
    return dict(sorted(result.items()))


def _texts(entry: Any, strings: Mapping[str, str], where: str) -> dict[str, str]:
    texts: dict[str, str] = {}
    for label, field in TEXT_KEYS.items():
        key = _scalar(_field(entry, field), str, f"{where}.{field}", optional=True)
        if key is None:
            continue
        text = strings.get(key.lower())
        if text:
            texts[label] = expand_templates(text, strings)
    return texts


def candidate_names(strings: Mapping[str, str]) -> dict[int, str]:
    """Placeholder names of every rune and buff text, by FNV-1a hash.

    A hash is the hash of the name itself, so a placeholder found in any rune text
    names that value wherever it appears (``StatGain1`` names the AD of the
    adaptive shard, whose own text only shows a runtime ``@f2@``).
    """
    texts = [text for key, text in strings.items() if key.startswith(("perk_", "buff_"))]
    return {fnv1a32(name.split(".")[0]): name.split(".")[0] for name in placeholder_names(texts)}


def _perk(entry: Any, strings: Mapping[str, str], known: Mapping[int, str]) -> dict[str, Any]:
    where = f"perk {_hex(entry.path_hash)}"
    perk_id = _scalar(_field(entry, "mPerkId"), int, f"{where}.mPerkId")
    perk_key = _scalar(_field(entry, "mPerkName"), str, f"{where}.mPerkName")
    texts = _texts(entry, strings, where)
    placeholders = placeholder_names([text for key, text in texts.items() if key != "name"])
    names = {**known, **{fnv1a32(name.split(".")[0]): name.split(".")[0] for name in placeholders}}
    script = _field(entry, "mScript")
    data = None
    script_name = None
    if script is not None:
        if not isinstance(script, ObjectValue):
            raise PerkError(f"{where}.mScript is not an object")
        script_name = _scalar(
            script.fields.get(F["mSpellScriptName"]), str, f"{where}.script", optional=True
        )
        data = script.fields.get(F["mSpellScriptData"])
    amounts: dict[str, float] = {}
    overrides: dict[str, dict[str, float]] = {}
    calculations: dict[str, Any] = {}
    if data is not None:
        if not isinstance(data, ObjectValue):
            raise PerkError(f"{where}.mSpellScriptData is not an object")
        amounts = _amounts(data.fields.get(F["mEffectAmount"]), names, f"{where}.mEffectAmount")
        modes = data.fields.get(F["mEffectAmountGameMode"])
        if modes is not None:
            if not isinstance(modes, MapValue):
                raise PerkError(f"{where}.mEffectAmountGameMode is not a map")
            for key, value in modes.items:
                if not isinstance(value, ObjectValue):
                    raise PerkError(f"{where}: mode override is not an object")
                overrides[_mode(key)] = _amounts(
                    value.fields.get(F["mEffectAmountPerMode"]), names, f"{where}[mode]"
                )
        node = data.fields.get(F["mCalculations"])
        if node is not None:
            if not isinstance(node, MapValue):
                raise PerkError(f"{where}.mCalculations is not a map")
            refs = {**names}
            for key, value in node.items:
                if not isinstance(key, Value) or not isinstance(key.value, int):
                    raise PerkError(f"{where}.mCalculations: key is not a hash")
                calculations[names.get(key.value, _hex(key.value))] = _tree(value, refs)
    kinds: dict[str, str | None] = {}
    for name in placeholders:
        base = name.split(".")[0]
        if base in amounts:
            kinds[name] = "effect_amount"
        elif base in calculations:
            kinds[name] = "calculation"
        elif RUNTIME_PLACEHOLDER.fullmatch(name):
            kinds[name] = "runtime"
        else:
            kinds[name] = None
    return {
        "id": perk_id,
        "key": perk_key,
        "enabled": _scalar(_field(entry, "mEnabled"), bool, f"{where}.mEnabled", optional=True),
        "stackable": _scalar(
            _field(entry, "mStackable"), bool, f"{where}.mStackable", optional=True
        ),
        "script": script_name,
        "effect_amounts": amounts,
        "mode_overrides": dict(sorted(overrides.items())),
        "calculations": dict(sorted(calculations.items())),
        "texts": texts,
        "placeholders": kinds,
    }


def _slot(node: Any, perks: Mapping[int, Any], strings: Mapping[str, str], where: str):
    # An embedded slot (a tree's rows) or a slot record (a shard row).
    if not isinstance(node, (ObjectValue, Entry)):
        raise PerkError(f"{where} is not a slot")
    label = _scalar(node.fields.get(F["mSlotLabelKey"]), str, f"{where}.label", optional=True)
    ids = []
    for link in _links(node.fields.get(F["mPerks"]), f"{where}.mPerks"):
        if link not in perks:
            raise PerkError(f"{where}: perk {_hex(link)} is not a readable Perk")
        ids.append(perks[link]["id"])
    return {
        "type": _scalar(node.fields.get(F["mType"]), int, f"{where}.mType"),
        "label": (strings.get(label.lower()) or None) if label else None,
        "perks": ids,
    }


def extract_runes(bin_data: bytes, strings: Mapping[str, str]) -> dict[str, Any]:
    """Trees, shard rows and every rune they reference, from the perks bin."""
    try:
        prop = parse_prop(bin_data)
    except PropError as exc:
        raise PerkError(f"bin: {exc}") from exc
    known = candidate_names(strings)
    perks = {
        entry.path_hash: _perk(entry, strings, known)
        for entry in prop.entries.values()
        if entry.class_hash == PERK
    }
    styles: dict[str, Any] = {}
    shard_links: list[int] | None = None
    for entry in prop.entries.values():
        if entry.class_hash != STYLE:
            continue
        style_id = _scalar(_field(entry, "mPerkStyleId"), int, "style.mPerkStyleId")
        where = f"style {style_id}"
        slots = _field(entry, "mSlots")
        if not isinstance(slots, ListValue):
            raise PerkError(f"{where}.mSlots is not a list")
        bonus: dict[str, int] = {}
        node = _field(entry, "mSubStyleBonus")
        for item in node.items if isinstance(node, ListValue) else ():
            if not isinstance(item, ObjectValue):
                raise PerkError(f"{where}.mSubStyleBonus is not a list of objects")
            sub = _scalar(item.fields.get(F["mStyleId"]), int, f"{where}.bonus.mStyleId")
            link = _scalar(item.fields.get(F["mPerk"]), int, f"{where}.bonus.mPerk")
            if link not in perks:
                raise PerkError(f"{where}: bonus perk {_hex(link)} is not a readable Perk")
            bonus[str(sub)] = perks[link]["id"]
        links = _links(_field(entry, "mSlotlinks"), f"{where}.mSlotlinks")
        if shard_links is None:
            shard_links = links
        elif links != shard_links:
            raise PerkError(f"{where}: shard rows differ from another tree's")
        name_key = _scalar(
            _field(entry, "mDisplayNameLocalizationKey"), str, f"{where}.name", optional=True
        )
        styles[str(style_id)] = {
            "key": _scalar(_field(entry, "mPerkStyleName"), str, f"{where}.mPerkStyleName"),
            "name": strings.get(name_key.lower()) if name_key else None,
            "allowed_secondary": _links(
                _field(entry, "mAllowedSubStyles"), f"{where}.mAllowedSubStyles"
            ),
            "slots": [
                _slot(slot, perks, strings, f"{where}.mSlots[{index}]")
                for index, slot in enumerate(slots.items)
            ],
            "secondary_bonus": dict(sorted(bonus.items())),
        }
    if not styles or shard_links is None:
        raise PerkError("the bin has no rune trees")
    shard_slots = []
    for link in shard_links:
        entry = prop.entries.get(link)
        if entry is None or entry.class_hash != SLOT:
            raise PerkError(f"shard row {_hex(link)} is not a readable PerkSlot")
        shard_slots.append(_slot(entry, perks, strings, f"shard row {_hex(link)}"))
    used = {
        perk_id
        for style in styles.values()
        for group in (style["slots"], [{"perks": list(style["secondary_bonus"].values())}])
        for slot in group
        for perk_id in slot["perks"]
    } | {perk_id for slot in shard_slots for perk_id in slot["perks"]}
    by_id: dict[str, Any] = {}
    for perk in perks.values():
        if perk["id"] in used:
            if str(perk["id"]) in by_id:
                raise PerkError(f"perk id {perk['id']} is repeated")
            by_id[str(perk["id"])] = {key: value for key, value in perk.items() if key != "id"}
    return {
        "styles": dict(sorted(styles.items())),
        "shard_slots": shard_slots,
        "perks": dict(sorted(by_id.items(), key=lambda pair: int(pair[0]))),
    }


def build_document(
    runes: Mapping[str, Any],
    *,
    bin_sha256: str,
    strings_sha256: str,
    locale: str,
    content_version: str,
    retrieved_at: str,
) -> dict[str, Any]:
    match = CONTENT_VERSION.fullmatch(content_version)
    if match is None:
        raise PerkError(f"content version {content_version!r} is not <major>.<minor>.<build>+…")
    return {
        "schema": SCHEMA,
        "label": "Derivado",
        "content_version": content_version,
        "game_version": f"{match.group(1)}.{match.group(2)}",
        "retrieved_at": retrieved_at,
        "locale": locale,
        "source": (
            "Cliente local: DATA/FINAL/Global.wad.client → perks → PerkStyle, PerkSlot, Perk; "
            f"DATA/FINAL/Localized/Global.{locale}.wad.client → claves de texto de cada runa"
        ),
        "bin_sha256": bin_sha256,
        "strings_sha256": strings_sha256,
        "method": (
            "research/binmodel/perks.py: lector PROP estricto; float32 escrito como el decimal "
            "más corto equivalente; nombres de valores y cálculos solo cuando su FNV-1a coincide "
            "con un marcador @…@ de los textos; claves RST con hashes.rst.xxh3.txt"
        ),
        **runes,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m binmodel.perks", description=__doc__)
    parser.add_argument("--wad", type=Path, required=True)
    parser.add_argument("--strings", type=Path, required=True)
    parser.add_argument("--rst-hashes", type=Path, required=True)
    parser.add_argument("--locale", default="es_ES")
    parser.add_argument("--content-version", required=True)
    parser.add_argument("--retrieved-at", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        data = read_entry(args.wad, WAD_ENTRY)
        strings = load_strings(args.strings, args.rst_hashes)
        document = build_document(
            extract_runes(data, strings),
            bin_sha256=hashlib.sha256(data).hexdigest(),
            strings_sha256=hashlib.sha256(args.strings.read_bytes()).hexdigest(),
            locale=args.locale,
            content_version=args.content_version,
            retrieved_at=args.retrieved_at,
        )
    except (ItemError, WadError, OSError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    args.output.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        f"styles: {len(document['styles'])}  shard rows: {len(document['shard_slots'])}  "
        f"perks: {len(document['perks'])} -> {args.output}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
