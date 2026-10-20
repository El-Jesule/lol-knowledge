"""High-level extraction of a champion bin document."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .model import Ability, ChampionExtract, Diagnostic
from .registry import Registry
from .stats import champion_stats, extract_base_stats
from .traverse import (
    TraversalContext,
    _vector,
    discover_abilities,
    extract_calculations,
    extract_cooldown,
    extract_data_values,
    extract_mode_overrides,
    extract_tooltip,
    find_champion_root,
    summarize_bot_data,
    tooltip_level_count,
)

DEFAULT_CONTENT_VERSION = "16.20.8248524+branch.releases-16-20.content.release"


class ExtractionError(Exception):
    """The document cannot be extracted without inventing data."""


def _spell(node: Mapping[str, Any], path: str) -> Mapping[str, Any]:
    spell = node.get("mSpell")
    if not isinstance(spell, Mapping):
        raise ExtractionError(f"missing {path}.mSpell")
    return spell


def _vector_by_candidates(
    spell: Mapping[str, Any],
    candidates: tuple[str, ...],
    *,
    spell_path: str,
    level_count: int | None,
    diagnostics: list[Diagnostic],
) -> dict[str, Any] | None:
    for key in candidates:
        if key in spell:
            return _vector(
                spell,
                key,
                spell_path=spell_path,
                level_count=level_count,
                diagnostics=diagnostics,
            )
    return None


def extract_champion(
    document: Mapping[str, Any],
    *,
    source: Mapping[str, Any] | None = None,
    registry: Registry | None = None,
    game_version: str = "16.20",
    content_version: str = DEFAULT_CONTENT_VERSION,
) -> ChampionExtract:
    """Extract a champion from a decoded CommunityDragon ``bin.json`` document.

    The function does not know Zaahen: every champion-specific name comes from
    ``CharacterRecords/Root`` and the spell objects it points to.
    """
    registry = registry or Registry()
    source_sha256 = str((source or {}).get("artifact_sha256") or (source or {}).get("sha256", ""))
    root_path, root = find_champion_root(document)
    diagnostics: list[Diagnostic] = []
    context = TraversalContext(
        document=document,
        registry=registry,
        source_sha256=source_sha256,
        content_version=content_version,
    )

    champion_name = root.get("mCharacterName")
    if not isinstance(champion_name, str):
        raise ExtractionError(f"{root_path}.mCharacterName is not a string")

    base_stats = extract_base_stats(root)
    stats_by_level = {}
    for level in range(1, 19):
        try:
            stats_by_level[str(level)] = champion_stats(base_stats, level)
        except KeyError as exc:
            diagnostics.append(
                Diagnostic(
                    "error",
                    "missing_champion_stat",
                    root_path,
                    str(exc),
                )
            )
            break

    abilities: list[Ability] = []
    for descriptor in discover_abilities(document, root, diagnostics):
        path = descriptor["path"]
        node = document.get(path)
        if not isinstance(node, Mapping):
            diagnostics.append(
                Diagnostic("error", "missing_spell_object", path, "Spell object not found.")
            )
            continue
        spell = _spell(node, path)
        context.spell_path = path
        level_count = tooltip_level_count(spell, path)
        level_count_source = "tooltip"
        if level_count is None:
            if descriptor["is_passive"]:
                level_count = 1
                level_count_source = "passive_default"
                diagnostics.append(
                    Diagnostic(
                        "info",
                        "passive_single_rank",
                        path,
                        "Passive has no level-up list; treated as a single-rank effect.",
                    )
                )
            else:
                level_count_source = "missing"
                diagnostics.append(
                    Diagnostic(
                        "warning",
                        "level_count_missing",
                        path,
                        "No LevelUp.levelCount; rank arrays are preserved but not sliced.",
                    )
                )

        data_values = extract_data_values(
            spell,
            spell_path=path,
            level_count=level_count,
            diagnostics=diagnostics,
            source_sha256=source_sha256,
            content_version=content_version,
        )
        data_values.extend(
            extract_mode_overrides(
                spell,
                spell_path=path,
                level_count=level_count,
                diagnostics=diagnostics,
                source_sha256=source_sha256,
                content_version=content_version,
            )
        )
        calculations = extract_calculations(spell, spell_path=path, context=context)
        cooldown = extract_cooldown(
            spell,
            spell_path=path,
            level_count=level_count,
            diagnostics=diagnostics,
        )
        if cooldown and isinstance(cooldown.get("legacy"), dict):
            legacy = cooldown["legacy"]
            if legacy.get("matches") is False:
                diagnostics.append(
                    Diagnostic(
                        "warning",
                        "cooldown_mismatch",
                        f"{path}.mSpell.cooldownTime",
                        "cooldownTime differs from Cooldown.values; "
                        "Cooldown.values is used as the effective cooldown.",
                        data={
                            "effective": cooldown.get("raw_values"),
                            "legacy": legacy.get("raw_values"),
                        },
                    )
                )
        mana = _vector_by_candidates(
            spell,
            ("manaValues", "mana"),
            spell_path=path,
            level_count=level_count,
            diagnostics=diagnostics,
        )
        cast_range = _vector_by_candidates(
            spell,
            ("castRangeValues", "castRange"),
            spell_path=path,
            level_count=level_count,
            diagnostics=diagnostics,
        )
        tooltip = extract_tooltip(spell, path)
        bot_data = summarize_bot_data(node, spell_path=path, context=context)
        child_spells: list[dict[str, Any]] = []
        for child_path in descriptor["children"]:
            child_node = document.get(child_path)
            if not isinstance(child_node, Mapping):
                diagnostics.append(
                    Diagnostic(
                        "warning",
                        "missing_child_spell",
                        str(child_path),
                        "Child spell object not found.",
                    )
                )
                continue
            context.spell_path = str(child_path)
            child_spell = child_node.get("mSpell")
            child_level = (
                tooltip_level_count(child_spell, str(child_path))
                if isinstance(child_spell, Mapping)
                else None
            )
            child_rank_count = child_level if child_level is not None else level_count
            child_data_values = []
            child_calculations = []
            if isinstance(child_spell, Mapping):
                child_data_values = extract_data_values(
                    child_spell,
                    spell_path=str(child_path),
                    level_count=child_rank_count,
                    diagnostics=diagnostics,
                    source_sha256=source_sha256,
                    content_version=content_version,
                )
                child_data_values.extend(
                    extract_mode_overrides(
                        child_spell,
                        spell_path=str(child_path),
                        level_count=child_rank_count,
                        diagnostics=diagnostics,
                        source_sha256=source_sha256,
                        content_version=content_version,
                    )
                )
                child_calculations = extract_calculations(
                    child_spell, spell_path=str(child_path), context=context
                )
            child_spells.append(
                {
                    "path": str(child_path),
                    "name": str(
                        child_node.get("mScriptName")
                        or child_node.get("ObjectName")
                        or str(child_path).rsplit("/", 1)[-1]
                    ),
                    "level_count": child_rank_count,
                    "level_count_source": "child" if child_level is not None else "parent",
                    "data_values": [item.to_dict() for item in child_data_values],
                    "calculations": [item.to_dict() for item in child_calculations],
                    "bot_data": summarize_bot_data(
                        child_node, spell_path=str(child_path), context=context
                    ),
                }
            )
        context.spell_path = path
        abilities.append(
            Ability(
                ability_id=descriptor["ability_id"],
                slot=descriptor["slot"],
                path=path,
                name=str(
                    node.get("mScriptName") or node.get("ObjectName") or path.rsplit("/", 1)[-1]
                ),
                root_spell=descriptor["root_spell"],
                level_count=level_count,
                source_level_count=level_count_source,
                data_values=data_values,
                calculations=calculations,
                cooldown=cooldown,
                mana=mana,
                cast_range=cast_range,
                tooltip=tooltip,
                children=[str(item) for item in descriptor["children"]],
                child_spells=child_spells,
                bot_data=bot_data,
                diagnostics=[],
            )
        )

    if not abilities:
        raise ExtractionError("no abilities extracted")

    champion = {
        "id": champion_name,
        "name": champion_name,
        "root_path": root_path,
        "base_stats": base_stats,
        "stats_by_level": stats_by_level,
        "spell_paths": list(root.get("spells") or []),
        "ability_paths": list(root.get("mAbilities") or []),
        "passive_spell": root.get("mCharacterPassiveSpell"),
        "passive_name_key": root.get("passiveName"),
        "passive_tooltip_key": root.get("passiveToolTip"),
    }
    return ChampionExtract(
        schema_version=registry.schema_version,
        game_version=game_version,
        content_version=content_version,
        source=dict(source or {}),
        champion=champion,
        abilities=abilities,
        unresolved=list(context.unresolved),
        diagnostics=diagnostics + context.diagnostics,
        registry={
            "schema_path": str(registry.path),
            "schema_version": registry.schema_version,
            "provenance": registry.provenance,
        },
    )
