"""Summoner's Rift summoner spells: loading, legality, cooldowns and combat math.

Reads ``lol-knowledge/derived/summoner-spells.json`` (extracted from the local
League client's ``Global.wad.client:shared`` bin and localized RST strings).
All calculations use exact ``Fraction`` arithmetic with explicit provenance
labels (``Derivado`` when matching the snapshot patch, ``Pendiente de verificación``
otherwise).
"""

from __future__ import annotations

import json
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from .cache import DEFAULT_CACHE
from .errors import StatsError
from .runes import RuneData
from .stats.data import ItemData
from .stats.sheet import Contribution, Label

SUMMONERS_PATH = Path("lol-knowledge/derived/summoner-spells.json")
SUMMONERS_SCHEMA = "lol-derived-summoner-spells/1"
MAX_SUMMONER_SPELLS = 2

# Summoner Spell Haste sources verified from 16.23 client item-effects.json and runes.json.
COSMIC_INSIGHT_RUNE_ID = 8347
IONIAN_BOOTS_HASTE: Mapping[str, Fraction] = {
    "3158": Fraction(10),  # Ionian Boots of Lucidity (SummonerHaste = 10)
    "3171": Fraction(20),  # Crimson Lucidity (SummonerHaste = 20)
}

EXTRA_ALIASES: Mapping[str, str] = {
    "tp": "SummonerTeleport",
    "dot": "SummonerDot",
    "prender": "SummonerDot",
    "barrera": "SummonerBarrier",
    "curar": "SummonerHeal",
    "extenuacion": "SummonerExhaust",
    "aplastar": "SummonerSmite",
    "fantasmal": "SummonerHaste",
    "limpiar": "SummonerBoost",
    "destello": "SummonerFlash",
    "teleportar": "SummonerTeleport",
}


def _norm(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.strip().lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _to_frac(value: Any) -> Fraction:
    return Fraction(str(value))


@dataclass(frozen=True)
class SummonerSpellSpec:
    """One Summoner's Rift summoner spell derived from client ``shared`` bin."""

    id: str
    alias: str
    name: str
    cooldown_seconds: Fraction
    cast_range: Fraction | None
    model_status: str
    source: str
    data_values: Mapping[str, Fraction]
    calculations: Mapping[str, Mapping[str, Any]]
    tooltip: str
    upgrade: Mapping[str, Any] | None = None

    def dv(self, key: str, default: Fraction = Fraction(0)) -> Fraction:
        return self.data_values.get(key, default)


@dataclass(frozen=True)
class SummonerSpellData:
    """Loaded ``lol-knowledge/derived/summoner-spells.json`` payload."""

    game_version: str
    content_version: str
    path: str
    spells: Mapping[str, SummonerSpellSpec]
    _lookup: Mapping[str, str]

    def matches_patch(self, patch: str) -> bool:
        parts = patch.split(".")
        return len(parts) >= 2 and f"{parts[0]}.{parts[1]}" == self.game_version

    def label_for(self, patch: str) -> Label:
        return Label.DERIVED if self.matches_patch(patch) else Label.PENDING

    def resolve(self, token: str) -> SummonerSpellSpec:
        key = _norm(token)
        canonical = self._lookup.get(key) or EXTRA_ALIASES.get(key)
        if canonical is None or canonical not in self.spells:
            known = ", ".join(f"{s.alias} ({s.id})" for s in self.spells.values())
            raise StatsError(f"unknown summoner spell {token!r} (known: {known})")
        return self.spells[canonical]


@dataclass(frozen=True)
class SummonerSheetEffects:
    """Stat-sheet modifiers and notes from active summoner spells."""

    flats: tuple[tuple[str, Contribution], ...] = ()
    percents: tuple[tuple[str, Contribution], ...] = ()
    notes: tuple[str, ...] = ()


def summoner_problems(document: Any, *, patch: str | None = None) -> list[str]:
    """Validate a ``lol-derived-summoner-spells/1`` JSON document."""
    problems: list[str] = []
    if not isinstance(document, Mapping):
        return ["document must be a JSON object"]
    if document.get("schema") != SUMMONERS_SCHEMA:
        problems.append(f"schema must be {SUMMONERS_SCHEMA!r}")
    game_version = document.get("game_version")
    if not isinstance(game_version, str) or not game_version.strip():
        problems.append("missing non-empty game_version")
    elif patch is not None:
        parts = patch.split(".")
        if len(parts) >= 2 and f"{parts[0]}.{parts[1]}" != game_version:
            problems.append(
                f"game_version {game_version!r} does not match snapshot patch {patch!r}"
            )
    content_version = document.get("content_version")
    if not isinstance(content_version, str) or not content_version.strip():
        problems.append("missing non-empty content_version")
    spells = document.get("spells")
    if not isinstance(spells, Mapping) or not spells:
        problems.append("spells must be a non-empty object")
        return problems
    required_ids = {
        "SummonerDot",
        "SummonerBarrier",
        "SummonerHeal",
        "SummonerExhaust",
        "SummonerSmite",
        "SummonerHaste",
        "SummonerBoost",
        "SummonerFlash",
        "SummonerTeleport",
    }
    missing = sorted(required_ids - set(spells))
    if missing:
        problems.append(f"missing core SR summoner spells: {missing}")
    for sid, body in spells.items():
        if not isinstance(body, Mapping):
            problems.append(f"spells.{sid}: must be an object")
            continue
        for field in ("id", "alias", "name", "source", "model_status"):
            val = body.get(field)
            if not isinstance(val, str) or not val.strip():
                problems.append(f"spells.{sid}.{field}: must be a non-empty string")
        cd = body.get("cooldown_seconds")
        if isinstance(cd, bool) or not isinstance(cd, (int, float)) or cd <= 0:
            problems.append(f"spells.{sid}.cooldown_seconds: must be a positive number")
    return problems


def _load_summoner_spells_uncached(root: Path) -> SummonerSpellData | None:
    path = root / SUMMONERS_PATH
    if not path.is_file():
        return None
    document = json.loads(path.read_text(encoding="utf-8"))
    issues = summoner_problems(document)
    if issues:
        raise StatsError(f"{path}: {'; '.join(issues)}")
    spells: dict[str, SummonerSpellSpec] = {}
    lookup: dict[str, str] = {}
    for sid, body in document["spells"].items():
        dvs = {k: _to_frac(v) for k, v in (body.get("data_values") or {}).items()}
        calcs = dict(body.get("calculations") or {})
        cast_range = None if body.get("cast_range") is None else _to_frac(body["cast_range"])
        spec = SummonerSpellSpec(
            id=str(body["id"]),
            alias=str(body["alias"]),
            name=str(body["name"]),
            cooldown_seconds=_to_frac(body["cooldown_seconds"]),
            cast_range=cast_range,
            model_status=str(body["model_status"]),
            source=str(body["source"]),
            data_values=dvs,
            calculations=calcs,
            tooltip=str(body.get("tooltip", "")),
            upgrade=body.get("upgrade"),
        )
        spells[sid] = spec
        lookup[_norm(spec.id)] = sid
        lookup[_norm(spec.alias)] = sid
        lookup[_norm(spec.name)] = sid
    return SummonerSpellData(
        game_version=str(document["game_version"]),
        content_version=str(document["content_version"]),
        path=SUMMONERS_PATH.as_posix(),
        spells=spells,
        _lookup=lookup,
    )


def load_summoner_spells(root: Path) -> SummonerSpellData | None:
    """Load ``lol-knowledge/derived/summoner-spells.json``, or ``None`` if absent."""
    return DEFAULT_CACHE.summoner_spells(root, lambda: _load_summoner_spells_uncached(root))


def resolve_loadout(
    tokens: Sequence[str],
    data: SummonerSpellData,
    *,
    allow_illegal: bool = False,
) -> tuple[tuple[SummonerSpellSpec, ...], list[str]]:
    """Resolve and validate a champion's summoner spell loadout (<= 2 unique spells)."""
    resolved = tuple(data.resolve(tok) for tok in tokens)
    violations: list[str] = []
    if len(resolved) > MAX_SUMMONER_SPELLS:
        violations.append(
            f"a champion can carry at most {MAX_SUMMONER_SPELLS} summoner spells "
            f"(got {len(resolved)})"
        )
    seen: set[str] = set()
    for sp in resolved:
        if sp.id in seen:
            violations.append(f"duplicate summoner spell {sp.id} ({sp.name})")
        seen.add(sp.id)
    if violations and not allow_illegal:
        raise StatsError(f"illegal summoner spell loadout: {'; '.join(violations)}")
    return resolved, violations


def eval_level_curve(calc: Mapping[str, Any], level: int) -> Fraction:
    """Evaluate a derived ``linear_by_level`` or ``by_level`` formula at ``level`` (1..18)."""
    clamped = max(1, min(18, level))
    op = calc.get("op")
    if op == "linear_by_level":
        low = _to_frac(calc["min"])
        high = _to_frac(calc["max"])
        return low + (high - low) * Fraction(clamped - 1, 17)
    if op == "by_level":
        values = calc["values"]
        return _to_frac(values[clamped - 1])
    raise StatsError(f"unsupported summoner spell curve op {op!r}")


def summoner_spell_haste(
    items: Sequence[ItemData] = (),
    runes: Sequence[int] = (),
    rune_data: RuneData | None = None,
) -> Fraction:
    """Total Summoner Spell Haste from equipped boots and Cosmic Insight (8347)."""
    total = Fraction(0)
    seen_boots: set[str] = set()
    for item in items:
        if item.id in IONIAN_BOOTS_HASTE and item.id not in seen_boots:
            total += IONIAN_BOOTS_HASTE[item.id]
            seen_boots.add(item.id)
    if COSMIC_INSIGHT_RUNE_ID in runes:
        sh = Fraction(18)
        if rune_data is not None and COSMIC_INSIGHT_RUNE_ID in rune_data.runes:
            raw = rune_data.runes[COSMIC_INSIGHT_RUNE_ID].values.get("SummonerHaste")
            if raw is not None:
                sh = _to_frac(raw)
        total += sh
    return total


def effective_cooldown(
    spell: SummonerSpellSpec,
    *,
    level: int,
    summoner_haste: Fraction = Fraction(0),
    unleashed: bool = False,
) -> Fraction:
    """Effective cooldown after Summoner Spell Haste: ``base * 100 / (100 + haste)``."""
    base = spell.cooldown_seconds
    if spell.id == "SummonerTeleport" and unleashed and spell.upgrade is not None:
        upg_calcs = spell.upgrade.get("calculations") or {}
        if upg_calcs:
            first_calc = next(iter(upg_calcs.values()))
            base = eval_level_curve(first_calc, level)
    if summoner_haste <= 0:
        return base
    return base * Fraction(100) / (Fraction(100) + summoner_haste)


def ignite_damage(spell: SummonerSpellSpec, level: int) -> Fraction:
    return eval_level_curve(spell.calculations["TooltipTrueDamageCalculation"], level)


def ignite_duration(spell: SummonerSpellSpec) -> Fraction:
    return spell.dv("DotDuration", Fraction(5))


def ignite_grievous(spell: SummonerSpellSpec) -> Fraction:
    return spell.dv("GrievousAmount", Fraction(2, 5))


def barrier_shield(spell: SummonerSpellSpec, level: int) -> Fraction:
    return eval_level_curve(spell.calculations["ShieldStrength"], level)


def barrier_duration(spell: SummonerSpellSpec) -> Fraction:
    return spell.dv("ShieldDuration", Fraction(5, 2))


def heal_amount(spell: SummonerSpellSpec, level: int, *, debuffed: bool = False) -> Fraction:
    base = eval_level_curve(spell.calculations["TotalHeal"], level)
    if debuffed:
        return base * spell.dv("StackingHealDebuff", Fraction(1, 2))
    return base


def heal_ms(spell: SummonerSpellSpec) -> tuple[Fraction, Fraction]:
    return (
        spell.dv("MoveSpeed", Fraction(3, 10)),
        spell.dv("MoveSpeedDuration", Fraction(1)),
    )


def exhaust_values(spell: SummonerSpellSpec) -> tuple[Fraction, Fraction, Fraction]:
    """Return ``(damage_reduction_fraction, slow_fraction, duration_seconds)``."""
    return (
        spell.dv("DamageReduction", Fraction(35)) / Fraction(100),
        spell.dv("Slow", Fraction(40)) / Fraction(100),
        spell.dv("DebuffDuration", Fraction(3)),
    )


def smite_damage(
    spell: SummonerSpellSpec,
    *,
    target_kind: str | None,
    tier: int = 0,
) -> tuple[Fraction, list[str]]:
    """True damage of Smite by target kind and jungle pet upgrade tier (0, 1, 2)."""
    if tier not in (0, 1, 2):
        raise StatsError(f"smite_tier must be 0, 1 or 2, got {tier}")
    if target_kind == "structure":
        raise StatsError("SummonerSmite cannot target structures")
    if target_kind == "champion":
        slow_pct = spell.dv("SmiteSlowAmount", Fraction(1, 5)) * 100
        slow_dur = spell.dv("SmiteSlowDuration", Fraction(2))
        notes = [f"unleashed Smite vs champion: {slow_pct:.0f}% slow for {slow_dur} s"]
        if tier == 0:
            notes.append(
                "smite_tier=0 assumed upgraded (tier>=1) to target champion; pass "
                "--input smite_tier=1|2 explicitly"
            )
        return spell.dv("FirstPVPDamage", Fraction(40)), notes
    if tier == 0:
        return spell.dv("SmiteBaseDamage", Fraction(600)), ["base Smite (tier 0)"]
    if tier == 1:
        return spell.dv("SmiteUpgradedDamage", Fraction(1000)), ["upgraded Smite (tier 1)"]
    return spell.dv("Smite2ndUpgradedDamage", Fraction(1400)), ["primal Smite (tier 2)"]


def ghost_ms(spell: SummonerSpellSpec, level: int) -> tuple[Fraction, Fraction]:
    return (
        eval_level_curve(spell.calculations["MovespeedMod"], level),
        spell.dv("Duration", Fraction(10)),
    )


def cleanse_tenacity(spell: SummonerSpellSpec) -> tuple[Fraction, Fraction]:
    return (
        spell.dv("TenacityValue", Fraction(3, 4)),
        spell.dv("TenacityDuration", Fraction(3)),
    )


def teleport_ms(spell: SummonerSpellSpec) -> tuple[Fraction, Fraction]:
    if spell.upgrade is not None:
        upg_dvs = spell.upgrade.get("data_values") or {}
        if "MSAmount" in upg_dvs and "MSDuration" in upg_dvs:
            return _to_frac(upg_dvs["MSAmount"]), _to_frac(upg_dvs["MSDuration"])
    return (
        spell.dv("MSAmount", Fraction(1, 2)),
        spell.dv("MSDuration", Fraction(3)),
    )


def summoner_sheet_effects(
    spells: Sequence[SummonerSpellSpec],
    data: SummonerSpellData,
    *,
    level: int,
    patch: str,
    inputs: Mapping[str, Fraction] | None = None,
    items: Sequence[ItemData] = (),
    runes: Sequence[int] = (),
    rune_data: RuneData | None = None,
) -> SummonerSheetEffects:
    """Resolve active stat buffs (Ghost, Heal MS, Teleport MS, Cleanse tenacity) and CD notes."""
    if not spells:
        return SummonerSheetEffects()
    scenario = inputs or {}
    label = data.label_for(patch)
    flats: list[tuple[str, Contribution]] = []
    percents: list[tuple[str, Contribution]] = []
    notes: list[str] = []
    haste = summoner_spell_haste(items, runes, rune_data)

    for sp in spells:
        unleashed = sp.id == "SummonerTeleport" and scenario.get("unleashed_teleport", 0) > 0
        eff_cd = effective_cooldown(sp, level=level, summoner_haste=haste, unleashed=unleashed)
        cd_text = f"{float(eff_cd):.1f}".rstrip("0").rstrip(".")
        haste_suffix = f" (with +{haste} summoner spell haste)" if haste > 0 else ""
        notes.append(f"summoner {sp.id} ({sp.name}): effective CD {cd_text} s{haste_suffix}")

        if sp.id == "SummonerHaste" and scenario.get("ghost_active", 0) > 0:
            ms_pct, dur = ghost_ms(sp, level)
            percents.append(
                (
                    "move_speed",
                    Contribution(
                        ms_pct,
                        "bonus",
                        f"summoner:{sp.id} ({sp.source})",
                        label,
                        f"{sp.name} active ({dur} s)",
                    ),
                )
            )
        elif sp.id == "SummonerHeal" and scenario.get("heal_ms_active", 0) > 0:
            ms_pct, dur = heal_ms(sp)
            percents.append(
                (
                    "move_speed",
                    Contribution(
                        ms_pct,
                        "bonus",
                        f"summoner:{sp.id} ({sp.source})",
                        label,
                        f"{sp.name} speed burst ({dur} s)",
                    ),
                )
            )
        elif sp.id == "SummonerTeleport" and scenario.get("teleport_haste", 0) > 0:
            ms_pct, dur = teleport_ms(sp)
            percents.append(
                (
                    "move_speed",
                    Contribution(
                        ms_pct,
                        "bonus",
                        f"summoner:{sp.id} ({sp.source})",
                        label,
                        f"Teleportar desatado ({dur} s)",
                    ),
                )
            )
        elif sp.id == "SummonerBoost" and scenario.get("cleanse_active", 0) > 0:
            ten, dur = cleanse_tenacity(sp)
            flats.append(
                (
                    "tenacity",
                    Contribution(
                        ten,
                        "bonus",
                        f"summoner:{sp.id} ({sp.source})",
                        label,
                        f"{sp.name} active ({dur} s)",
                    ),
                )
            )

    return SummonerSheetEffects(tuple(flats), tuple(percents), tuple(notes))
