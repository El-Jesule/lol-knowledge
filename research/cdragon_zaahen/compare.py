"""Compare extracted CDragon values against Data Dragon, RCP and the wiki.

Rules: never overwrite a source, never resolve a disagreement, never promote a
value to verified without independent corroboration.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .extract import (
    E_PATH,
    LEGACY_COOLDOWN_SPECS,
    Q_PATH,
    R_PATH,
    W_PATH,
    Formula,
    extract_formula,
    extract_zaahen,
    has_champion_stat_block,
)
from .provenance import Provenance, Status
from .wiki_evidence import WIKI_PATCH_HISTORY_AD_PER_STACK, WIKI_VALUES

TOLERANCE = 1e-6

R_DAMAGE_DEPENDENCIES = ("r.base_damage", "r.bonus_ad_ratio")

DIAGNOSTIC_PARAMETERS = frozenset(spec[2] for spec in LEGACY_COOLDOWN_SPECS)

COMPARISON_NOTES = {
    "champion.attack_damage_per_level": (
        "Data Dragon reports 0 while CharacterRecords/Root and the wiki report 4. "
        "Data Dragon is not overwritten."
    ),
    "passive.ad_per_stack": (
        "The wiki summary says 2.95%; its patch history says "
        f"{WIKI_PATCH_HISTORY_AD_PER_STACK[0]:g}%."
    ),
    "q.monster_damage_multiplier": (
        "The bin field is 1.0 and the wiki says 200%; the semantic "
        "normalisation between the two is not proven."
    ),
}


@dataclass(frozen=True)
class Comparison:
    parameter: str
    cdragon: tuple[float, ...] | None
    ddragon: tuple[float, ...] | None
    rcp: tuple[float, ...] | None
    wiki: tuple[float, ...] | None
    status: Status
    conclusion: str
    missing_evidence: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "parameter": self.parameter,
            "communitydragon": list(self.cdragon) if self.cdragon else None,
            "data_dragon": list(self.ddragon) if self.ddragon else None,
            "rcp": list(self.rcp) if self.rcp else None,
            "wiki": list(self.wiki) if self.wiki else None,
            "status": str(self.status),
            "conclusion": self.conclusion,
            "missing_evidence": self.missing_evidence,
        }


@dataclass(frozen=True)
class Calculation:
    name: str
    expression: str
    result: float
    depends_on: tuple[str, ...]
    status: Status
    blocked: bool
    notes: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "expression": self.expression,
            "result": self.result,
            "depends_on": list(self.depends_on),
            "status": str(self.status),
            "blocked": self.blocked,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class Report:
    content_version: str
    source_sha256: str
    source_url: str
    ddragon_patch: str
    values: tuple[Provenance, ...]
    formulas: tuple[Formula, ...]
    comparisons: tuple[Comparison, ...]
    calculations: tuple[Calculation, ...]
    blocked: tuple[str, ...]
    champion_stat_block_present: bool

    @property
    def conflicts(self) -> tuple[Comparison, ...]:
        return tuple(item for item in self.comparisons if item.status is Status.CONFLICT)

    def to_dict(self) -> dict[str, Any]:
        return {
            "content_version": self.content_version,
            "source_sha256": self.source_sha256,
            "source_url": self.source_url,
            "ddragon_patch": self.ddragon_patch,
            "champion_stat_block_present": self.champion_stat_block_present,
            "values": [value.to_dict() for value in self.values],
            "formulas": [
                {
                    "name": formula.name,
                    "ability": formula.ability,
                    "source_path": formula.source_path,
                    "supported": formula.supported,
                    "status": str(formula.status),
                    "notes": formula.notes,
                }
                for formula in self.formulas
            ],
            "comparisons": [item.to_dict() for item in self.comparisons],
            "calculations": [item.to_dict() for item in self.calculations],
            "blocked": list(self.blocked),
        }


def _matches(left: Sequence[float], right: Sequence[float]) -> bool:
    """Compare per-rank series, allowing a scalar to stand for a constant series."""
    if len(left) == len(right):
        return all(
            math.isclose(a, b, rel_tol=1e-6, abs_tol=TOLERANCE)
            for a, b in zip(left, right, strict=True)
        )
    if len(left) == 1:
        return all(math.isclose(left[0], value, rel_tol=1e-6, abs_tol=TOLERANCE) for value in right)
    if len(right) == 1:
        return all(math.isclose(right[0], value, rel_tol=1e-6, abs_tol=TOLERANCE) for value in left)
    return False


def _ddragon_series(document: Mapping[str, Any]) -> dict[str, tuple[float, ...]]:
    spells = document.get("spells")
    if not isinstance(spells, Sequence) or len(spells) < 4:
        raise ValueError("Data Dragon champion document has no spells")
    order = ("q", "w", "e", "r")
    series: dict[str, tuple[float, ...]] = {}
    for ability, spell in zip(order, spells, strict=False):
        ranks = 3 if ability == "r" else 5
        for field, parameter in (
            ("cooldown", f"{ability}.cooldown_seconds"),
            ("cost", f"{ability}.mana_cost"),
        ):
            values = spell.get(field)
            if isinstance(values, Sequence) and len(values) >= ranks:
                series[parameter] = tuple(float(value) for value in values[:ranks])
    growth = document.get("stats", {}).get("attackdamageperlevel")
    if isinstance(growth, (int, float)) and not isinstance(growth, bool):
        series["champion.attack_damage_per_level"] = (float(growth),)
    return series


def _rcp_series(document: Mapping[str, Any]) -> dict[str, tuple[float, ...]]:
    spells = document.get("spells")
    if not isinstance(spells, Mapping):
        raise ValueError("RCP fixture has no spells object")
    series: dict[str, tuple[float, ...]] = {}
    for ability in ("q", "w", "e", "r"):
        entry = spells.get(ability)
        if not isinstance(entry, Mapping):
            continue
        ranks = 3 if ability == "r" else 5
        cooldowns = entry.get("cooldownCoefficients")
        if isinstance(cooldowns, Sequence) and len(cooldowns) >= ranks:
            series[f"{ability}.cooldown_seconds"] = tuple(
                float(value) for value in cooldowns[:ranks]
            )
    return series


def classify(
    parameter: str,
    cdragon: tuple[float, ...] | None,
    ddragon: tuple[float, ...] | None,
    rcp: tuple[float, ...] | None,
    wiki: tuple[float, ...] | None,
    *,
    note: str = "",
) -> Comparison:
    named = (
        ("communitydragon", cdragon),
        ("data_dragon", ddragon),
        ("rcp", rcp),
        ("wiki", wiki),
    )
    present = [(name, values) for name, values in named if values is not None]

    disagreements = [
        f"{left[0]}={left[1]} vs {right[0]}={right[1]}"
        for index, left in enumerate(present)
        for right in present[index + 1 :]
        if not _matches(left[1], right[1])
    ]

    if disagreements:
        status = Status.CONFLICT
        conclusion = "Sources disagree: " + "; ".join(disagreements)
        missing = note or "Need a source proven to match the target patch."
    elif cdragon is None:
        status = Status.UNVERIFIED
        conclusion = "CommunityDragon has no value for this parameter."
        missing = note or "A source that publishes the parameter is still required."
    elif ddragon is not None and _matches(cdragon, ddragon):
        if wiki is not None and _matches(cdragon, wiki):
            status = Status.VERIFIED
            conclusion = "CommunityDragon, Data Dragon and wiki agree."
        else:
            status = Status.CORROBORATED
            conclusion = "CommunityDragon and Data Dragon agree (same origin, different export)."
        missing = ""
    elif wiki is not None and _matches(cdragon, wiki):
        status = Status.CORROBORATED
        conclusion = "CommunityDragon and wiki agree; Data Dragon does not publish it."
        missing = ""
    else:
        status = Status.SOURCE_EXPLICIT
        conclusion = "Only CommunityDragon publishes it."
        missing = note or "No independent corroboration yet."

    return Comparison(
        parameter=parameter,
        cdragon=cdragon,
        ddragon=ddragon,
        rcp=rcp,
        wiki=wiki,
        status=status,
        conclusion=conclusion,
        missing_evidence=missing,
    )


def build_report(
    document: Mapping[str, Any],
    *,
    url: str,
    content_version: str,
    sha256: str,
    ddragon: Mapping[str, Any],
    rcp: Mapping[str, Any],
    ddragon_patch: str,
) -> Report:
    values = extract_zaahen(document, url=url, content_version=content_version, sha256=sha256)
    by_parameter = {value.parameter: value.ranks for value in values}

    ddragon_values = _ddragon_series(ddragon)
    rcp_values = _rcp_series(rcp)

    comparisons: list[Comparison] = []
    for parameter in sorted(
        (set(by_parameter) | set(WIKI_VALUES) | set(ddragon_values)) - DIAGNOSTIC_PARAMETERS
    ):
        comparisons.append(
            classify(
                parameter,
                by_parameter.get(parameter),
                ddragon_values.get(parameter),
                rcp_values.get(parameter),
                WIKI_VALUES.get(parameter),
                note=COMPARISON_NOTES.get(parameter, ""),
            )
        )

    comparisons = sorted(comparisons, key=lambda item: item.parameter)

    formulas = (
        extract_formula(document, Q_PATH, "InitialDamage"),
        extract_formula(document, W_PATH, "InitialDamage"),
        extract_formula(document, W_PATH, "SecondaryDamage"),
        extract_formula(document, E_PATH, "BaseDamageCalc"),
        extract_formula(document, E_PATH, "BonusDamageCalc"),
        extract_formula(document, R_PATH, "DamageEndCalc"),
    )

    status_by_parameter = {item.parameter: item.status for item in comparisons}
    values = tuple(
        value.with_status(status_by_parameter.get(value.parameter, value.status))
        for value in values
    )
    blocked = tuple(
        sorted(
            parameter
            for parameter, status in status_by_parameter.items()
            if status in (Status.CONFLICT, Status.UNVERIFIED)
        )
    )

    base = by_parameter["r.base_damage"][0]
    ratio = by_parameter["r.bonus_ad_ratio"][0]
    bonus_ad = 100.0
    dependencies = tuple(
        f"{name}:{status_by_parameter.get(name, Status.UNVERIFIED)}"
        for name in R_DAMAGE_DEPENDENCIES
    )
    blocked_calc = any(parameter in blocked for parameter in R_DAMAGE_DEPENDENCIES)
    calculations = (
        Calculation(
            name="r.damage_rank1_bonus_ad_100",
            expression=f"{base:g} + {ratio:g} * {bonus_ad:g}",
            result=base + ratio * bonus_ad,
            depends_on=dependencies,
            status=Status.DERIVED if not blocked_calc else Status.UNVERIFIED,
            blocked=blocked_calc,
            notes=(
                "Operands are corroborated, but mStat=2 / mStatFormula=2 is an "
                "inferred semantic equivalent to bonus AD, not a documented enum."
            ),
        ),
    )

    return Report(
        content_version=content_version,
        source_sha256=sha256,
        source_url=url,
        ddragon_patch=ddragon_patch,
        values=tuple(values),
        formulas=formulas,
        comparisons=tuple(comparisons),
        calculations=calculations,
        blocked=blocked,
        champion_stat_block_present=has_champion_stat_block(document),
    )


def passive_history_note() -> str:
    """Expose the wiki's internal contradiction as evidence."""
    return (
        "Wiki summary: "
        f"{WIKI_VALUES['passive.ad_per_stack'][0]:g}% per stack; "
        f"wiki patch history: {WIKI_PATCH_HISTORY_AD_PER_STACK[0]:g}%."
    )
