"""Extract Summoner's Rift summoner spells from the local League client.

Reads the ``shared`` bin inside ``DATA/FINAL/Global.wad.client`` and the
localized RST string table inside ``DATA/FINAL/Localized/Global.<locale>.wad.client``.
Nothing is invented: every cooldown, range, DataValue and level curve comes
directly from the client's ``Shared/Spells/Summoner*`` records.

Usage::

    PYTHONPATH=research python -m binmodel.summoners \\
        --game "<Game>" --hashes "<hashes>" --retrieved-at 2026-11-22 \\
        --output lol-knowledge/derived/summoner-spells.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from tools import extract_rst

from . import bin2json, propbin, wad
from .records import f32_decimal

SCHEMA = "lol-derived-summoner-spells/1"
WAD_ENTRY = "shared"
VERSION_PATTERN = re.compile(r"(\d+)\.(\d+)\.\d+\+.+")

# Canonical Summoner's Rift summoner spells (order preserved in output).
SR_SUMMONERS: tuple[tuple[str, str, str, str], ...] = (
    ("SummonerDot", "ignite", "spell_summonerdot", "evaluable"),
    ("SummonerBarrier", "barrier", "spell_summonerbarrier", "evaluable"),
    ("SummonerHeal", "heal", "spell_summonerheal", "evaluable"),
    ("SummonerExhaust", "exhaust", "spell_summonerexhaust", "evaluable"),
    ("SummonerSmite", "smite", "spell_summonersmite", "evaluable"),
    ("SummonerHaste", "ghost", "spell_summonerhaste", "evaluable"),
    ("SummonerBoost", "cleanse", "spell_summonerboost", "evaluable"),
    ("SummonerFlash", "flash", "spell_summonerflash", "excluded"),
    ("SummonerTeleport", "teleport", "spell_summonerteleport", "evaluable"),
)
TELEPORT_UPGRADE_ID = "S12_SummonerTeleportUpgrade"


class SummonerExtractError(Exception):
    """Raised when the client assets cannot be read without guessing."""


def _clean_number(value: Any) -> int | float:
    dec = f32_decimal(float(value))
    as_float = float(dec)
    if as_float.is_integer():
        return int(as_float)
    return as_float


def _eval_breakpoints(part: Mapping[str, Any]) -> list[int | float]:
    """Evaluate a Riot ``ByCharLevelBreakpointsCalculationPart`` for levels 1..18."""
    level1 = float(f32_decimal(float(part.get("mLevel1Value", 0.0))))
    step = float(f32_decimal(float(part.get("mInitialBonusPerLevel", 0.0))))
    by_level_step: dict[int, float] = {}
    by_level_flat: dict[int, float] = {}
    for bp in part.get("mBreakpoints") or ():
        lvl = int(bp.get("mLevel", 1))
        if "mBonusPerLevelAtAndAfter" in bp:
            by_level_step[lvl] = float(f32_decimal(float(bp["mBonusPerLevelAtAndAfter"])))
        if "mAdditionalBonusAtThisLevel" in bp:
            by_level_flat[lvl] = by_level_flat.get(lvl, 0.0) + float(
                f32_decimal(float(bp["mAdditionalBonusAtThisLevel"]))
            )
    values: list[int | float] = []
    cur = level1
    cur_step = step
    for lvl in range(1, 19):
        if lvl > 1:
            if lvl in by_level_step:
                cur_step = by_level_step[lvl]
            cur += cur_step
            if lvl in by_level_flat:
                cur += by_level_flat[lvl]
        values.append(_clean_number(cur))
    return values


def _compile_calculation(calc: Mapping[str, Any]) -> dict[str, Any] | None:
    """Convert one client GameCalculation into a clean formula descriptor."""
    parts = calc.get("mFormulaParts") or ()
    if len(parts) == 1 and isinstance(parts[0], Mapping):
        p0 = parts[0]
        ptype = p0.get("__type")
        if ptype == "ByCharLevelInterpolationCalculationPart":
            return {
                "op": "linear_by_level",
                "min": _clean_number(p0.get("mStartValue", 0.0)),
                "max": _clean_number(p0.get("mEndValue", 0.0)),
            }
        if ptype == "ByCharLevelBreakpointsCalculationPart":
            return {
                "op": "by_level",
                "values": _eval_breakpoints(p0),
            }
    # Unleashed Teleport cooldown has breakpoint part + buff reduction part; keep base level curve.
    for part in parts:
        if (
            isinstance(part, Mapping)
            and part.get("__type") == "ByCharLevelBreakpointsCalculationPart"
        ):
            return {
                "op": "by_level",
                "values": _eval_breakpoints(part),
            }
    return None


def _extract_spell_record(
    entry_json: Mapping[str, Any],
    *,
    spell_id: str,
    alias: str,
    tooltip_prefix: str,
    model_status: str,
    tooltips: Mapping[str, str],
    content_version: str,
) -> dict[str, Any]:
    spell = entry_json.get("mSpell") or {}
    cd_list = spell.get("cooldownTime") or ()
    range_list = spell.get("castRange") or ()
    cooldown = _clean_number(cd_list[0]) if cd_list else None
    cast_range = _clean_number(range_list[0]) if range_list else None

    data_values: dict[str, int | float] = {}
    for dv in spell.get("DataValues") or ():
        name = dv.get("name")
        vals = dv.get("values") or ()
        if isinstance(name, str) and vals:
            data_values[name] = _clean_number(vals[0])

    # Flash stores blink range in mEffectAmount[0].value[0] (400).
    effects = spell.get("mEffectAmount") or ()
    if spell_id == "SummonerFlash" and effects:
        first_vals = (effects[0] or {}).get("value") or ()
        if first_vals:
            data_values["FlashDistance"] = _clean_number(first_vals[0])

    calculations: dict[str, Any] = {}
    for cname, cbody in (spell.get("mSpellCalculations") or {}).items():
        if not isinstance(cbody, Mapping):
            continue
        compiled = _compile_calculation(cbody)
        if compiled is not None:
            calculations[str(cname)] = compiled

    name_es = tooltips.get(f"{tooltip_prefix}_name") or spell_id
    tooltip_es = tooltips.get(f"{tooltip_prefix}_tooltip") or ""
    return {
        "id": spell_id,
        "alias": alias,
        "name": name_es,
        "cooldown_seconds": cooldown,
        "cast_range": cast_range,
        "model_status": model_status,
        "source": f"Shared/Spells/{spell_id} ({content_version})",
        "data_values": data_values,
        "calculations": calculations,
        "tooltip": tooltip_es,
    }


def extract_summoner_spells(
    game: Path,
    hashes: Path,
    *,
    retrieved_at: str,
    locale: str = "es_ES",
) -> dict[str, Any]:
    """Extract all Summoner's Rift summoner spells from an installed client."""
    meta_path = game / "content-metadata.json"
    if not meta_path.is_file():
        raise SummonerExtractError(f"{meta_path} not found")
    content_version = json.loads(meta_path.read_text(encoding="utf-8")).get("version")
    match = VERSION_PATTERN.fullmatch(content_version) if isinstance(content_version, str) else None
    if match is None:
        raise SummonerExtractError(f"unexpected content version {content_version!r}")
    game_version = ".".join(match.groups())

    final = game / "DATA" / "FINAL"
    global_wad = final / "Global.wad.client"
    strings_wad = final / "Localized" / f"Global.{locale}.wad.client"
    if not global_wad.is_file():
        raise SummonerExtractError(f"{global_wad} not found")
    if not strings_wad.is_file():
        raise SummonerExtractError(f"{strings_wad} not found")

    strings_sha256 = hashlib.sha256(strings_wad.read_bytes()).hexdigest()
    rst_values: dict[int, str] = {}
    for _, chunk in extract_rst.read_wad_entries(strings_wad):
        if chunk.startswith(extract_rst.MAGIC):
            rst_values.update(extract_rst.parse_rst(chunk))
    rst_names = extract_rst.load_hash_table(hashes / "hashes.rst.xxh3.txt")
    tooltips = {
        rst_names[key].lower(): text for key, text in rst_values.items() if key in rst_names
    }

    # Gather placeholder tokens from SR summoner tooltips so hashed calc/DV names resolve.
    extra_tokens: set[str] = {"Cooldown"}
    for _, _, prefix, _ in (*SR_SUMMONERS, ("", "", "spell_upgradedsummonerteleport", "")):
        tip = tooltips.get(f"{prefix}_tooltip", "")
        extra_tokens.update(re.findall(r"@([A-Za-z0-9_]+)", tip))
    names = bin2json.load_names(hashes, extra=extra_tokens)

    raw_shared = wad.read_entry(global_wad, WAD_ENTRY)
    bin_sha256 = hashlib.sha256(raw_shared).hexdigest()
    prop = propbin.parse_prop(raw_shared, skip_unreadable=True)

    wanted_paths = {f"Shared/Spells/{sid}" for sid, _, _, _ in SR_SUMMONERS}
    wanted_paths.add(f"Shared/Spells/{TELEPORT_UPGRADE_ID}")
    sub = propbin.PropFile(
        prop.version,
        prop.linked,
        {ph: entry for ph, entry in prop.entries.items() if names.entry(ph) in wanted_paths},
        (),
        False,
        (),
    )
    converted = bin2json.to_json(sub, names)

    spells_out: dict[str, dict[str, Any]] = {}
    for spell_id, alias, prefix, status in SR_SUMMONERS:
        path = f"Shared/Spells/{spell_id}"
        entry_json = converted.get(path)
        if not isinstance(entry_json, Mapping):
            raise SummonerExtractError(f"missing {path} in {global_wad}:{WAD_ENTRY}")
        spells_out[spell_id] = _extract_spell_record(
            entry_json,
            spell_id=spell_id,
            alias=alias,
            tooltip_prefix=prefix,
            model_status=status,
            tooltips=tooltips,
            content_version=content_version,
        )

    # Attach Unleashed Teleport upgrade data directly onto SummonerTeleport.
    tp_upg = converted.get(f"Shared/Spells/{TELEPORT_UPGRADE_ID}")
    if isinstance(tp_upg, Mapping):
        upg_rec = _extract_spell_record(
            tp_upg,
            spell_id=TELEPORT_UPGRADE_ID,
            alias="unleashed_teleport",
            tooltip_prefix="spell_upgradedsummonerteleport",
            model_status="evaluable",
            tooltips=tooltips,
            content_version=content_version,
        )
        spells_out["SummonerTeleport"]["upgrade"] = {
            "id": TELEPORT_UPGRADE_ID,
            "name": upg_rec["name"],
            "source": upg_rec["source"],
            "data_values": upg_rec["data_values"],
            "calculations": upg_rec["calculations"],
            "tooltip": upg_rec["tooltip"],
        }

    return {
        "schema": SCHEMA,
        "label": "Derivado",
        "game_version": game_version,
        "content_version": content_version,
        "retrieved_at": retrieved_at,
        "locale": locale,
        "source": (
            f"DATA/FINAL/Global.wad.client:{WAD_ENTRY} + Localized/Global.{locale}.wad.client"
        ),
        "bin_sha256": bin_sha256,
        "strings_sha256": strings_sha256,
        "spells": spells_out,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract SR summoner spells from local client.")
    parser.add_argument("--game", type=Path, required=True)
    parser.add_argument("--hashes", type=Path, required=True)
    parser.add_argument("--retrieved-at", required=True)
    parser.add_argument("--locale", default="es_ES")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        doc = extract_summoner_spells(
            args.game, args.hashes, retrieved_at=args.retrieved_at, locale=args.locale
        )
    except (SummonerExtractError, wad.WadError, propbin.PropError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    args.output.write_bytes(text.encode("utf-8"))
    print(
        f"wrote {args.output} ({len(doc['spells'])} summoner spells, patch {doc['game_version']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
