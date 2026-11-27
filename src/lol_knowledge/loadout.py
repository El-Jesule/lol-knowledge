"""Unified StatSheet, build legality, passive, rune, summoner, elixir, and Ornn assembly."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from .errors import StatsError
from .kit import Kit
from .objects.legality import ITEM_GROUPS_PATH, ItemGroups, check_build, load_item_groups
from .passives import sheet_passive_effects
from .rotation import CritBase
from .runes import (
    adaptive_stat,
    check_page,
    combat_rune_notes,
    load_runes,
    minor_rune_effects,
    needs_adaptive_stat,
    shard_contributions,
)
from .stats import ChampionData, DerivedRecords, ItemData, Label, StatSheet, build_stat_sheet
from .stats.issues import DataIssue
from .stats.sheet import MANA_RESOURCE
from .summoners import load_summoner_spells, resolve_loadout, summoner_sheet_effects
from .upgrades import elixir_contributions, ornn_upgrade_contributions


class LoadoutError(StatsError):
    """Structured loadout validation failure shared by CLI and JSON contract."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class LoadoutResult:
    """Assembled StatSheet together with informational notes and legality warnings."""

    sheet: StatSheet
    notes: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def resolve_crit_base(
    champion_id: str, patch: str, derived: DerivedRecords | None
) -> CritBase | None:
    """Resolve base critical strike multiplier from client derived records."""
    value = derived.value(champion_id, "critdamagemultiplier") if derived else None
    if value is None:
        return None
    label = Label.DERIVED if derived is not None and derived.matches_patch(patch) else Label.PENDING
    assert derived is not None
    return CritBase(
        value,
        label,
        f"{derived.path} {champion_id}.critdamagemultiplier ({derived.content_version})",
    )


def check_item_legality(
    root: Path,
    item_ids: Sequence[str],
    champion: ChampionData,
    *,
    allow_illegal: bool = False,
    who: str = "attacker",
    groups: ItemGroups | None = None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Validate item inventory legality, returning ``(notes, warnings)``."""
    if not item_ids:
        return (), ()
    data = groups if groups is not None else load_item_groups(root)
    if data is None:
        return (
            (f"{who} build legality not checked: {ITEM_GROUPS_PATH.as_posix()} is missing",),
            (),
        )
    report = check_build(item_ids, data, patch=champion.patch, champion=champion.id)
    notes = tuple(f"{who} build: {note}" for note in report.notes)
    if report.legal:
        return notes, ()
    problems = "; ".join(violation.message for violation in report.violations)
    if not allow_illegal:
        raise LoadoutError(
            "illegal_build",
            f"{who} build is not legal [{report.label}]: {problems} "
            "(--allow-illegal-build calculates it anyway)",
        )
    return notes, (f"{who} build is not legal [{report.label}]: {problems}",)


def assemble_stat_sheet(
    root: Path,
    champion: ChampionData,
    level: int,
    items: Sequence[ItemData],
    runes: Sequence[int],
    shards: Sequence[int],
    issues: Sequence[DataIssue],
    assumptions: Mapping[str, Any],
    derived: DerivedRecords | None,
    *,
    extras: Sequence[Any] = (),
    inputs: Mapping[str, Fraction] | None = None,
    combat_context: str = "stats",
    kit: Kit | None = None,
    allow_illegal: bool = False,
    summoners: Sequence[str] = (),
    elixir: str | None = None,
    ornn_item: str | None = None,
    check_items_legality: bool = False,
    who: str = "attacker",
) -> LoadoutResult:
    """Build a validated StatSheet with passives, runes, summoners, elixir, and Ornn upgrade."""
    notes: list[str] = []
    warnings: list[str] = []
    groups = load_item_groups(root) if (items or ornn_item) else None
    if check_items_legality and items:
        leg_notes, leg_warnings = check_item_legality(
            root,
            [item.id for item in items],
            champion,
            allow_illegal=allow_illegal,
            who=who,
            groups=groups,
        )
        notes.extend(leg_notes)
        warnings.extend(leg_warnings)

    passive = sheet_passive_effects(
        kit, level, inputs, include_stacking=combat_context != "rotation"
    )
    uses_mana = champion.resource == MANA_RESOURCE.get(champion.locale)
    elx_fx = elixir_contributions(elixir, level=level, uses_mana=uses_mana)
    ornn_fx = ornn_upgrade_contributions(ornn_item, items, level=level, item_groups=groups)

    s_flats: tuple[Any, ...] = ()
    s_percents: tuple[Any, ...] = ()
    s_notes: tuple[str, ...] = ()
    if summoners:
        s_data = load_summoner_spells(root)
        if s_data is None:
            raise LoadoutError(
                "not_found",
                "lol-knowledge/derived/summoner-spells.json is missing; "
                "summoner spells unavailable",
            )
        try:
            resolved_s, s_violations = resolve_loadout(
                summoners, s_data, allow_illegal=allow_illegal
            )
        except StatsError as exc:
            raise LoadoutError("illegal_build", str(exc)) from exc
        warnings.extend(str(v) for v in s_violations)
        s_rune_data = load_runes(root) if runes else None
        s_fx = summoner_sheet_effects(
            resolved_s,
            s_data,
            level=level,
            patch=champion.patch,
            inputs=inputs,
            items=items,
            runes=runes,
            rune_data=s_rune_data,
        )
        s_flats, s_percents, s_notes = s_fx.flats, s_fx.percents, s_fx.notes

    base_extras = (*extras, *passive.flats, *s_flats, *elx_fx.flats, *ornn_fx.flats)
    base_percents = (*passive.percents, *s_percents, *elx_fx.percents)
    base_notes = (*passive.notes, *s_notes, *elx_fx.notes, *ornn_fx.notes)
    if not runes and not shards:
        sheet = build_stat_sheet(
            champion,
            level,
            items,
            issues,
            assumptions,
            derived,
            base_extras,
            base_percents,
            extra_amplifiers=passive.amplifiers,
            extra_notes=base_notes,
            inputs=inputs,
        )
        return LoadoutResult(sheet, tuple(notes), tuple(warnings))

    rune_data = load_runes(root)
    if rune_data is None:
        raise LoadoutError(
            "invalid_input",
            "lol-knowledge/derived/runes.json is missing; runes cannot be used",
        )
    report = check_page(runes, shards, rune_data, patch=champion.patch)
    if report.label is Label.PENDING:
        notes.append(
            f"runes are from client {rune_data.game_version}, the snapshot is {champion.patch}"
        )
    if not report.legal:
        problems = "; ".join(report.violations)
        if not allow_illegal:
            raise LoadoutError(
                "illegal_build",
                f"rune page is not legal [{report.label}]: {problems} "
                "(--allow-illegal-build calculates it anyway)",
            )
        warnings.append(f"rune page is not legal [{report.label}]: {problems}")

    adaptive, a_label, a_note = None, Label.DERIVED, ""
    if needs_adaptive_stat(runes, shards, rune_data):
        before = build_stat_sheet(
            champion, level, items, issues, assumptions, derived, extras, inputs=inputs
        )
        bonus_ad = sum(
            (
                part.value
                for part in before["attack_damage"].contributions
                if part.scope == "bonus" and not part.adaptive
            ),
            start=Fraction(0),
        )
        power = sum(
            (part.value for part in before["ability_power"].contributions if not part.adaptive),
            Fraction(0),
        )
        weight = derived.value(champion.id, "adaptiveforceapweight") if derived else None
        adaptive, a_label, a_note = adaptive_stat(bonus_ad, power, weight)

    flats, percents = shard_contributions(
        shards,
        rune_data,
        level=level,
        patch=champion.patch,
        adaptive=adaptive,
        adaptive_label=a_label,
        adaptive_note=a_note,
    )
    has_boots = (
        False
        if not items
        else (None if groups is None else groups.has_boots([i.id for i in items]))
    )
    rune_effects = minor_rune_effects(
        runes,
        rune_data,
        level=level,
        patch=champion.patch,
        items=items,
        uses_mana=uses_mana,
        has_boots=has_boots,
        inputs=inputs,
        adaptive=adaptive,
        adaptive_label=a_label,
        adaptive_note=a_note,
    )
    extra_notes = [*base_notes, *rune_effects.notes]
    pending = list(rune_effects.pending)
    if combat_context == "stats":
        extra_notes += combat_rune_notes(rune_effects.combat_runes, rune_data, in_ability=False)
    elif combat_context == "ability":
        pending += combat_rune_notes(rune_effects.combat_runes, rune_data, in_ability=True)

    sheet = build_stat_sheet(
        champion,
        level,
        items,
        issues,
        assumptions,
        derived,
        (*base_extras, *flats, *rune_effects.flats),
        (*percents, *base_percents, *rune_effects.percents),
        pending,
        extra_amplifiers=(*passive.amplifiers, *rune_effects.amplifiers),
        extra_notes=extra_notes,
        move_speed_bonus_amp=rune_effects.move_speed_bonus_amp,
        inputs=inputs,
    )
    return LoadoutResult(sheet, tuple(notes), tuple(warnings))
