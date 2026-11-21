"""Canonical definitions for non-purchasable transformed Tear items.

Summoner's Rift Tear items (``3003``, ``3004``, ``3119``, ``2526``) transform at
360 Manaflow stacks into ``3040`` (Seraph's Embrace), ``3042`` (Muramana),
``3121`` (Fimbulwinter) and ``2530`` (Diadem of Songs). Because Data Dragon marks
them ``purchasable: false``, they stay outside the 218-item purchasable catalog
(``catalog-stats.json``), while still being resolvable here either directly by
item id or automatically when ``--input manaflow_stacks=360`` is supplied on
their base item.

Every numerical value below comes directly from Data Dragon 16.23.1
(``data/current/items.json``) and client 16.23 binary records
(``DATA/FINAL/Global.wad.client -> items -> Items/<id>``).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# Base Tear item id -> transformed Tear item id at 360 Manaflow stacks.
TEAR_BASE_TO_TRANSFORM: dict[str, str] = {
    "3003": "3040",
    "3004": "3042",
    "3119": "3121",
    "2526": "2530",
}
TEAR_TRANSFORM_TO_BASE: dict[str, str] = {v: k for k, v in TEAR_BASE_TO_TRANSFORM.items()}
TEAR_STACK_MAX = 360

_CLIENT_REF = (
    "Cliente 16.23.8399929+branch.releases-16-23.content.release: "
    "DATA/FINAL/Global.wad.client -> items -> Items/{id}"
)


def _client_source(item_id: str, quote: str) -> dict[str, Any]:
    return {
        "kind": "client_data",
        "reference": _CLIENT_REF.format(id=item_id),
        "quote": quote,
        "retrieved_at": "2026-11-21",
        "confidence": "derived",
    }


# Canonical stats (unit-converted) and effects for the 4 transformed Tear items.
# Stats match data/current/items.json (16.23.1) verbatim.
TRANSFORMED_TEAR_SPECS: dict[str, Mapping[str, Any]] = {
    "3040": {
        "id": "3040",
        "name": "Abrazo del serafín",
        "stats": (
            ("ability_power", "flat", 70, "ddragon_stat"),
            ("mana", "flat", 1000, "ddragon_stat"),
            ("ability_haste", "flat", 25, "ddragon_description"),
        ),
        "effects": (
            {
                "id": "awe",
                "kind": "passive",
                "name": "Asombro",
                "trigger": {"event": "always"},
                "target": {"kind": "self"},
                "components": [
                    {
                        "kind": "stat_modifier",
                        "stat": "ability_power",
                        "scope": "total",
                        "mode": "flat",
                        "formula": {
                            "op": "percent_of",
                            "percent": 2,
                            "stat": "mana",
                            "scope": "bonus",
                        },
                    }
                ],
                "cooldown_seconds": None,
                "duration_seconds": None,
                "sources": [
                    _client_source(
                        "3040",
                        "APFromMana = 0.02; BonusAPCalc ({a7070c3c}): 2% bonus mana",
                    )
                ],
                "evidence_confidence": "derived",
                "model_status": "evaluable",
                "note": "Seraph's Embrace Awe: +2% bonus mana as ability power.",
            },
            {
                "id": "lifeline",
                "kind": "passive",
                "name": "Salvavidas",
                "trigger": {"event": "taking_damage"},
                "target": {"kind": "self"},
                "conditions": [{"kind": "target_health_below", "value": 0.3}],
                "components": [
                    {
                        "kind": "shield",
                        "mode": "absolute",
                        "shield_type": "normal",
                        "formula": {
                            "op": "percent_of",
                            "percent": 18,
                            "stat": "mana",
                            "scope": "total",
                        },
                        "duration_seconds": 3,
                    }
                ],
                "cooldown_seconds": 90,
                "duration_seconds": 3,
                "limits": [{"kind": "threshold", "value": 30, "unit": "percent"}],
                "sources": [
                    _client_source(
                        "3040",
                        "HealthThreshold = 0.3; ShieldDuration = 3; LifelineCooldown = 90; "
                        "ShieldValue ({d72beee1}): 18% max mana",
                    )
                ],
                "evidence_confidence": "derived",
                "model_status": "evaluable",
                "note": "Lifeline below 30% HP: 18% max mana shield for 3 s (90 s CD).",
            },
        ),
    },
    "3042": {
        "id": "3042",
        "name": "Muramana",
        "stats": (
            ("attack_damage", "flat", 35, "ddragon_stat"),
            ("mana", "flat", 1000, "ddragon_stat"),
            ("ability_haste", "flat", 15, "ddragon_description"),
        ),
        "effects": (
            {
                "id": "awe",
                "kind": "passive",
                "name": "Asombro",
                "trigger": {"event": "always"},
                "target": {"kind": "self"},
                "components": [
                    {
                        "kind": "stat_modifier",
                        "stat": "attack_damage",
                        "scope": "bonus",
                        "mode": "flat",
                        "formula": {
                            "op": "percent_of",
                            "percent": 2,
                            "stat": "mana",
                            "scope": "total",
                        },
                    }
                ],
                "cooldown_seconds": None,
                "duration_seconds": None,
                "sources": [
                    _client_source(
                        "3042",
                        "BonusADManaRatioTOOLTIPONLY = 0.02; "
                        "BonusADFromMana ({e06e243e}): 2% max mana",
                    )
                ],
                "evidence_confidence": "derived",
                "model_status": "evaluable",
                "note": "Muramana Awe: +2% max mana as bonus attack damage.",
            },
            {
                "id": "shock-attack",
                "kind": "passive",
                "name": "Impacto (ataques)",
                "trigger": {"event": "on_hit"},
                "target": {"kind": "enemy_champion"},
                "conditions": [{"kind": "target_is_champion"}],
                "components": [
                    {
                        "kind": "damage",
                        "damage_type": "physical",
                        "formula": {
                            "op": "percent_of",
                            "percent": 1.2,
                            "stat": "mana",
                            "scope": "total",
                        },
                    }
                ],
                "cooldown_seconds": None,
                "duration_seconds": None,
                "sources": [
                    _client_source(
                        "3042",
                        "OnHitManaRatioTOOLTIPONLY = 0.012; "
                        "OnHitDamage ({cfaae860}): 1.2% max mana",
                    )
                ],
                "evidence_confidence": "derived",
                "model_status": "evaluable",
                "note": "Muramana Shock on-hit vs champions: 1.2% max mana physical damage.",
            },
            {
                "id": "shock-ability",
                "kind": "passive",
                "name": "Impacto (habilidades)",
                "trigger": {"event": "damaging_ability"},
                "target": {"kind": "enemy_champion"},
                "conditions": [{"kind": "target_is_champion"}],
                "components": [
                    {
                        "kind": "damage",
                        "damage_type": "physical",
                        "formula": {
                            "op": "by_holder_range",
                            "melee": {
                                "op": "percent_of",
                                "percent": 4,
                                "stat": "mana",
                                "scope": "total",
                            },
                            "ranged": {
                                "op": "percent_of",
                                "percent": 3,
                                "stat": "mana",
                                "scope": "total",
                            },
                        },
                    }
                ],
                "cooldown_seconds": 6.5,
                "duration_seconds": None,
                "sources": [
                    _client_source(
                        "3042",
                        "AbilityManaRatioMeleeTOOLTIPONLY = 0.04; "
                        "AbilityManaRatioRangedTOOLTIPONLY = 0.03; PerCastIDLockout = 6.5",
                    )
                ],
                "evidence_confidence": "derived",
                "model_status": "evaluable",
                "note": (
                    "Muramana Shock on damaging abilities vs champions: 4% melee / 3% ranged "
                    "max mana physical damage (6.5 s per-cast lockout)."
                ),
            },
        ),
    },
    "3121": {
        "id": "3121",
        "name": "El gran invierno",
        "stats": (
            ("health", "flat", 550, "ddragon_stat"),
            ("mana", "flat", 1000, "ddragon_stat"),
            ("ability_haste", "flat", 15, "ddragon_description"),
        ),
        "effects": (
            {
                "id": "awe",
                "kind": "passive",
                "name": "Asombro",
                "trigger": {"event": "always"},
                "target": {"kind": "self"},
                "components": [
                    {
                        "kind": "stat_modifier",
                        "stat": "health",
                        "scope": "bonus",
                        "mode": "flat",
                        "formula": {
                            "op": "percent_of",
                            "percent": 15,
                            "stat": "mana",
                            "scope": "bonus",
                        },
                    }
                ],
                "cooldown_seconds": None,
                "duration_seconds": None,
                "sources": [
                    _client_source(
                        "3121",
                        "BonusHPFromMana ({57bc9c23}): 15% bonus mana",
                    )
                ],
                "evidence_confidence": "derived",
                "model_status": "evaluable",
                "note": "Fimbulwinter Awe: +15% bonus mana as bonus health.",
            },
            {
                "id": "everlasting",
                "kind": "passive",
                "name": "Eterno",
                "trigger": {"event": "on_damage"},
                "target": {"kind": "self"},
                "conditions": [{"kind": "target_is_champion"}],
                "components": [
                    {
                        "kind": "shield",
                        "mode": "absolute",
                        "shield_type": "normal",
                        "formula": {
                            "op": "add",
                            "operands": [
                                {"op": "constant", "value": 100},
                                {
                                    "op": "percent_of",
                                    "percent": 4.5,
                                    "stat": "mana",
                                    "scope": "total",
                                },
                            ],
                        },
                        "duration_seconds": 3,
                    }
                ],
                "cooldown_seconds": 8,
                "duration_seconds": 3,
                "sources": [
                    _client_source(
                        "3121",
                        "Cooldown = 8; ShieldDuration = 3; ShieldBase ({0c2eb095}) = 100; "
                        "CurrentManaShieldRatio = 0.045; Multiplier = 0.8 (>1 enemy)",
                    )
                ],
                "evidence_confidence": "derived",
                "model_status": "evaluable",
                "note": (
                    "Fimbulwinter Everlasting: on immobilize/melee slow (target_impaired=1), "
                    "grants 100 + 4.5% current mana shield for 3 s (8 s CD; +80% if >1 enemy)."
                ),
            },
        ),
    },
    "2530": {
        "id": "2530",
        "name": "Diadema melodiosa",
        "stats": (
            ("health", "flat", 200, "ddragon_stat"),
            ("mana", "flat", 1000, "ddragon_stat"),
            ("heal_and_shield_power", "percent", 8, "ddragon_description"),
            ("mana_regen", "percent", 100, "ddragon_description"),
        ),
        "effects": (
            {
                "id": "harmony",
                "kind": "passive",
                "name": "Armonía",
                "trigger": {"event": "always"},
                "target": {"kind": "self"},
                "components": [
                    {
                        "kind": "stat_modifier",
                        "stat": "heal_and_shield_power",
                        "scope": "total",
                        "mode": "flat",
                        "formula": {
                            "op": "percent_of",
                            "percent": 0.5,
                            "stat": "mana",
                            "scope": "bonus",
                        },
                    }
                ],
                "cooldown_seconds": None,
                "duration_seconds": None,
                "sources": [
                    _client_source(
                        "2530",
                        "BonusHSPCalc ({9604c5ee}): 0.5% bonus mana as HSP",
                    )
                ],
                "evidence_confidence": "derived",
                "model_status": "evaluable",
                "note": "Diadem of Songs Harmony: +0.5% bonus mana as heal & shield power.",
            },
            {
                "id": "consonance",
                "kind": "passive",
                "name": "Consonancia",
                "trigger": {"event": "in_combat"},
                "target": {"kind": "ally_champion"},
                "components": [
                    {
                        "kind": "healing",
                        "mode": "absolute",
                        "formula": {
                            "op": "percent_of",
                            "percent": 0.8,
                            "stat": "mana",
                            "scope": "total",
                        },
                    }
                ],
                "cooldown_seconds": 1,
                "duration_seconds": None,
                "sources": [
                    _client_source(
                        "2530",
                        "AllyRangeCheck = 900; AllyCombatDuration = 3; "
                        "ManaToHeal ({eb3fdd2d}): 0.8% max mana/s",
                    )
                ],
                "evidence_confidence": "derived",
                "model_status": "evaluable",
                "note": (
                    "Diadem of Songs Consonance: heals lowest-HP ally for 0.8% max mana/s "
                    "in combat."
                ),
            },
        ),
    },
}
