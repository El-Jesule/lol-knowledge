"""Rune (perk) extraction tests on synthetic bins."""

from __future__ import annotations

import pytest
from binmodel.hashes import fnv1a32
from binmodel.perks import PerkError, build_document, candidate_names, extract_runes
from binmodel.propbin import BinType as T
from propbuild import encode_prop, lst, mapping, obj, prim


def amounts(**values):
    return mapping(
        T.HASH, T.F32, [(prim(T.HASH, fnv1a32(k)), prim(T.F32, v)) for k, v in values.items()]
    )


def perk(perk_id, key, values, *, tooltip=None, calculations=None, modes=None):
    data = {"mEffectAmount": amounts(**values)}
    if calculations is not None:
        data["mCalculations"] = calculations
    if modes is not None:
        per_mode = [
            (prim(T.HASH, fnv1a32(mode)), obj("Mode", {"mEffectAmountPerMode": amounts(**v)}))
            for mode, v in modes.items()
        ]
        data["mEffectAmountGameMode"] = mapping(T.HASH, T.EMBED, per_mode)
    fields = {
        "mPerkId": prim(T.U32, perk_id),
        "mPerkName": prim(T.STRING, key),
        "mDisplayNameLocalizationKey": prim(T.STRING, f"perk_displayname_{key}"),
        "mScript": obj("PerkScript", {
            "mSpellScriptName": prim(T.STRING, f"ASSETS/{key}.lua"),
            "mSpellScriptData": obj("PerkScriptData", data),
        }),
    }  # fmt: skip
    if tooltip is not None:
        fields["mTooltipNameLocalizationKey"] = prim(T.STRING, f"perk_tooltip_{key}")
    return ("Perk", fields)


def slot(kind, *paths, label=None):
    fields = {
        "mType": prim(T.U32, kind),
        "mPerks": lst(T.LINK, [prim(T.LINK, fnv1a32(p)) for p in paths]),
    }
    if label:
        fields["mSlotLabelKey"] = prim(T.STRING, label)
    return fields


def style(style_id, key, rows, *, shards, allowed=(), bonus=()):
    return ("PerkStyle", {
        "mPerkStyleId": prim(T.U32, style_id),
        "mPerkStyleName": prim(T.STRING, key),
        "mDisplayNameLocalizationKey": prim(T.STRING, f"perkstyle_{key}"),
        "mAllowedSubStyles": lst(T.U32, [prim(T.U32, item) for item in allowed]),
        "mSlots": lst(T.EMBED, [obj("PerkSlot", row) for row in rows]),
        "mSubStyleBonus": lst(T.EMBED, [
            obj("Bonus", {"mStyleId": prim(T.U32, sub), "mPerk": prim(T.LINK, fnv1a32(path))})
            for sub, path in bonus
        ]),
        "mSlotlinks": lst(T.LINK, [prim(T.LINK, fnv1a32(path)) for path in shards]),
    })  # fmt: skip


SHARDS = ("Perks/StatMods/Slots/Offense",)
STRINGS = {
    "perk_tooltip_electrocute": "Inflige @TotalDamage@ en @WindowDuration@ s; @f1@ en total",
    "perk_displayname_electrocute": "Electrocutar",
    "perk_displayname_adaptive": "Fuerza adaptable",
    "perk_substring_other": "@StatGain1@ de DA",
    "perkstyle_domination": "Dominación",
    "slot_offense": "Ataque",
}


def bin_data(**extra):
    calc = mapping(
        T.HASH, T.EMBED, [(prim(T.HASH, fnv1a32("TotalDamage")), obj("GameCalculation", {}))]
    )
    entries = {
        "Perks/Styles/Domination": style(
            8100, "Domination", [slot(0, "Perks/Electrocute")], shards=SHARDS,
            allowed=(8000,), bonus=((8000, "Perks/Bonus"),),
        ),
        "Perks/Electrocute": perk(
            8112, "Electrocute", {"WindowDuration": 3.0, "Hidden": 1.0},
            tooltip=True, calculations=calc, modes={"ARAM": {"WindowDuration": 2.0}},
        ),
        "Perks/Bonus": perk(8127, "Bonus", {}),
        "Perks/Adaptive": perk(5008, "Adaptive", {"StatGain1": 5.4}),
        "Perks/Unused": perk(9999, "Unused", {}),
        SHARDS[0]: ("PerkSlot", slot(5, "Perks/Adaptive", label="slot_offense")),
    }  # fmt: skip
    entries.update(extra)
    return encode_prop(entries)


def test_extracts_trees_shards_values_and_texts():
    runes = extract_runes(bin_data(), STRINGS)
    domination = runes["styles"]["8100"]
    assert domination["key"] == "Domination" and domination["name"] == "Dominación"
    assert domination["slots"] == [{"type": 0, "label": None, "perks": [8112]}]
    assert domination["allowed_secondary"] == [8000]
    assert domination["secondary_bonus"] == {"8000": 8127}
    assert runes["shard_slots"] == [{"type": 5, "label": "Ataque", "perks": [5008]}]
    assert sorted(runes["perks"]) == ["5008", "8112", "8127"]  # unused perks are left out
    electrocute = runes["perks"]["8112"]
    assert electrocute["effect_amounts"] == {
        "WindowDuration": 3.0,
        f"{{{fnv1a32('Hidden'):08x}}}": 1.0,
    }
    assert electrocute["mode_overrides"] == {"ARAM": {"WindowDuration": 2.0}}
    assert electrocute["calculations"] == {"TotalDamage": {"class": "GameCalculation"}}
    assert electrocute["placeholders"] == {
        "TotalDamage": "calculation", "WindowDuration": "effect_amount", "f1": "runtime",
    }  # fmt: skip
    # A placeholder of another rune's text names the value (the hash is the name).
    assert runes["perks"]["5008"]["effect_amounts"] == {"StatGain1": 5.4}
    assert candidate_names(STRINGS)[fnv1a32("StatGain1")] == "StatGain1"


def test_broken_references_stop_the_extraction():
    data = bin_data(
        **{
            "Perks/Styles/Domination": style(
                8100, "Domination", [slot(0, "Perks/None")], shards=SHARDS
            )
        }
    )
    with pytest.raises(PerkError, match="is not a readable Perk"):
        extract_runes(data, STRINGS)
    with pytest.raises(PerkError, match="no rune trees"):
        extract_runes(encode_prop({"Perks/Bonus": perk(1, "Bonus", {})}), STRINGS)


def test_document_header():
    document = build_document(
        {"styles": {}, "shard_slots": [], "perks": {}}, bin_sha256="0" * 64,
        strings_sha256="1" * 64, locale="es_ES", content_version="16.23.1+b", retrieved_at="d",
    )  # fmt: skip
    assert (document["schema"], document["game_version"], document["label"]) == (
        "lol-derived-runes/1", "16.23", "Derivado",
    )  # fmt: skip
