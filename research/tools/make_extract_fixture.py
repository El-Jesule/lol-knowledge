"""Build a compact champion fixture for the generic extractor tests.

The original bin export is not versioned. This generator keeps only the fields
the extractor reads, records the source hash, and can be used for any champion.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ZAAHEN_SHA256 = "76e32de67667917769cc6022a818b13e5024ea521a23c70436dc48eea533ed0b"
DEFAULT_VERSION = "16.20.8248524+branch.releases-16-20.content.release"
ROOT_KEYS = (
    "mCharacterName",
    "baseHPModifiable",
    "hpPerLevelModifiable",
    "baseStaticHPRegenModifiable",
    "hpRegenPerLevelModifiable",
    "baseDamageModifiable",
    "damagePerLevelModifiable",
    "baseArmorModifiable",
    "armorPerLevelModifiable",
    "baseMR",
    "mrPerLevel",
    "baseMoveSpeedModifiable",
    "attackRangeModifiable",
    "attackSpeedModifiable",
    "attackSpeedRatioModifiable",
    "attackSpeedPerLevelModifiable",
    "spells",
    "mAbilities",
    "mCharacterPassiveSpell",
    "passiveName",
    "passiveToolTip",
    "__type",
)
SPELL_KEYS = (
    "DataValues",
    "DataValuesModeOverride",
    "mSpellCalculations",
    "Cooldown",
    "cooldownTime",
    "mana",
    "manaValues",
    "castRange",
    "castRangeValues",
    "mClientData",
)
ABILITY_KEYS = ("mRootSpell", "mChildSpells", "mName", "__type")
SPELL_OBJECT_KEYS = ("ObjectName", "objectPath", "mScriptName", "__type")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _find_root(document: Mapping[str, Any]) -> tuple[str, Mapping[str, Any]]:
    candidates = [
        (path, node)
        for path, node in document.items()
        if isinstance(node, Mapping)
        and (node.get("__type") == "CharacterRecord" or "mCharacterName" in node)
    ]
    if len(candidates) != 1:
        raise SystemExit(f"expected one CharacterRecord, found {len(candidates)}")
    return candidates[0]


def _trim_tooltip(client: Mapping[str, Any]) -> dict[str, Any]:
    tooltip = client.get("mTooltipData")
    if not isinstance(tooltip, Mapping):
        return {"__type": client.get("__type")}
    return {
        "__type": client.get("__type"),
        "mTooltipData": {
            "mObjectName": tooltip.get("mObjectName"),
            "mFormat": tooltip.get("mFormat"),
            "mLocKeys": tooltip.get("mLocKeys"),
            "mLists": tooltip.get("mLists"),
            "__type": tooltip.get("__type"),
        },
    }


def _trim_spell(node: Mapping[str, Any]) -> dict[str, Any]:
    spell = node.get("mSpell")
    if not isinstance(spell, Mapping):
        return {key: node.get(key) for key in SPELL_OBJECT_KEYS}
    trimmed_spell: dict[str, Any] = {}
    for key in SPELL_KEYS:
        if key not in spell:
            continue
        if key == "mClientData":
            client = spell[key]
            trimmed_spell[key] = _trim_tooltip(client) if isinstance(client, Mapping) else client
        else:
            trimmed_spell[key] = spell[key]
    result: dict[str, Any] = {key: node.get(key) for key in SPELL_OBJECT_KEYS}
    result["mSpell"] = trimmed_spell
    return result


def build_fixture(
    document: Mapping[str, Any],
    *,
    source_url: str,
    content_version: str,
    source_sha256: str,
) -> dict[str, Any]:
    root_path, root = _find_root(document)
    passive_path = root.get("mCharacterPassiveSpell")
    objects: dict[str, Any] = {root_path: {key: root.get(key) for key in ROOT_KEYS}}
    spell_paths = [passive_path, *root.get("spells", [])]
    for path in spell_paths:
        if not isinstance(path, str):
            continue
        node = document.get(path)
        if not isinstance(node, Mapping):
            raise SystemExit(f"missing spell object {path}")
        objects[path] = _trim_spell(node)
    child_paths: list[str] = []
    for path in root.get("mAbilities", []):
        node = document.get(path)
        if not isinstance(node, Mapping):
            raise SystemExit(f"missing ability object {path}")
        objects[path] = {key: node.get(key) for key in ABILITY_KEYS}
        child_paths.extend(node.get("mChildSpells", []))
    for path in child_paths:
        node = document.get(path)
        if isinstance(node, Mapping):
            objects[path] = _trim_spell(node)
    return {
        "_provenance": {
            "source": "communitydragon",
            "url": source_url,
            "content_version": content_version,
            "source_sha256": source_sha256,
            "selection": (
                "Root stat fields and spell lists; passive/Q/W/E/R spell objects with "
                "DataValues, mode overrides, mSpellCalculations, cooldown/mana/range "
                "vectors and tooltip level lists; ability objects with root/child spells. "
                "BotData, buffs, animations and skins are omitted."
            ),
        },
        **objects,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--champion", default="zaahen")
    parser.add_argument("--source-url", default="")
    parser.add_argument("--content-version", default=DEFAULT_VERSION)
    parser.add_argument("--expect-sha256", default=None)
    args = parser.parse_args(argv)
    actual = _sha256(args.input)
    expected = args.expect_sha256
    if expected is None and args.champion.lower() == "zaahen":
        expected = ZAAHEN_SHA256
    if expected and actual.lower() != expected.lower():
        print(f"error: sha256 mismatch: {actual} != {expected}", file=sys.stderr)
        return 2
    source_url = args.source_url or (
        f"https://raw.communitydragon.org/16.20/game/data/characters/"
        f"{args.champion.lower()}/{args.champion.lower()}.bin.json"
    )
    document = json.loads(args.input.read_text(encoding="utf-8"))
    fixture = build_fixture(
        document,
        source_url=source_url,
        content_version=args.content_version,
        source_sha256=actual,
    )
    args.output.write_text(
        json.dumps(fixture, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"wrote {args.output} ({args.output.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
