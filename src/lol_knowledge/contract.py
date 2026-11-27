"""Versioned JSON contract between AI clients and the LoL-Knowledge engine (IA-01..IA-03).

Schema: ``lol-knowledge-contract/1``. Every calculation runs deterministically
through the existing pure engines (stats, ability, rotation, survive, optimize)
and returns a uniform envelope carrying ``result_label``, ``weakest_input_label``,
explicit ``inputs``, ``assumptions`` and ``not_modelled`` items.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from fractions import Fraction
from pathlib import Path
from typing import Any

from .damage import to_fraction
from .defense import evaluate_defense, hits_from_rotation, parse_incoming
from .defense_report import to_dict as defense_to_dict
from .duel import (
    DEFAULT_DUEL_MAX_DURATION,
    DEFAULT_DUEL_MODE,
    DEFAULT_DUEL_TIE_BREAK,
    DEFAULT_PRIORITY_SLOTS,
    DuelFighterSpec,
    evaluate_duel,
)
from .duel_report import to_dict as duel_to_dict
from .errors import DamageInputError, KitError, RotationError, StatsError
from .kit import load_kit, passive_contributions
from .loadout import LoadoutError, assemble_stat_sheet, resolve_crit_base
from .objects import load_model
from .optimizer import OptimizeConstraints, optimize_build
from .optimizer import to_dict as optimize_to_dict
from .rotation import CritBase, evaluate_rotation, parse_steps
from .rotation_report import to_dict as rotation_to_dict
from .runes import load_runes
from .scenario import evaluate_ability, target_from_sheet, target_from_values
from .scenario_report import to_dict as ability_to_dict
from .stats import (
    Label,
    load_champion,
    load_issues,
    load_items,
    load_records,
    weakest,
)
from .stats import to_dict as stats_to_dict
from .summoners import load_summoner_spells

CONTRACT_SCHEMA = "lol-knowledge-contract/1"
OPERATIONS = frozenset({"lookup", "stats", "ability", "rotation", "survive", "duel", "optimize"})

EXPLANATION_CONTRACT: dict[str, bool] = {
    "must_cite_labels": True,
    "must_report_not_modelled": True,
    "never_invent_or_round_away_uncertainty": True,
}


class ContractInputError(Exception):
    """Structured contract input validation failure (never hides missing parameters)."""

    def __init__(self, code: str, message: str, *, missing_fields: Sequence[str] = ()) -> None:
        super().__init__(message)
        self.code = code
        self.missing_fields = tuple(missing_fields)


def _require_str(params: Mapping[str, Any], key: str) -> str:
    val = params.get(key)
    if not isinstance(val, str) or not val.strip():
        raise ContractInputError(
            "missing_input",
            f"missing or empty string parameter {key!r}",
            missing_fields=(key,),
        )
    return val.strip()


def _require_int(params: Mapping[str, Any], key: str, *, minimum: int | None = None) -> int:
    val = params.get(key)
    if val is None:
        raise ContractInputError(
            "missing_input",
            f"missing required integer parameter {key!r}",
            missing_fields=(key,),
        )
    if isinstance(val, bool) or not isinstance(val, int):
        raise ContractInputError("invalid_input", f"parameter {key!r} must be an integer")
    if minimum is not None and val < minimum:
        raise ContractInputError("invalid_input", f"parameter {key!r} must be >= {minimum}")
    return val


def _optional_int(params: Mapping[str, Any], key: str, default: int | None = None) -> int | None:
    val = params.get(key)
    if val is None:
        return default
    if isinstance(val, bool) or not isinstance(val, int):
        raise ContractInputError("invalid_input", f"parameter {key!r} must be an integer")
    return val


def _optional_fraction(params: Mapping[str, Any], key: str) -> Fraction | None:
    val = params.get(key)
    if val is None:
        return None
    if isinstance(val, bool) or not isinstance(val, (int, float, str)):
        raise ContractInputError("invalid_input", f"parameter {key!r} must be a number")
    try:
        return to_fraction(str(val), key)
    except DamageInputError as exc:
        raise ContractInputError("invalid_input", str(exc)) from exc


def _str_list(params: Mapping[str, Any], key: str) -> list[str]:
    val = params.get(key)
    if val is None:
        return []
    if not isinstance(val, list) or not all(isinstance(x, (str, int)) for x in val):
        raise ContractInputError("invalid_input", f"parameter {key!r} must be a list of ids")
    return [str(x) for x in val]


def _int_list(params: Mapping[str, Any], key: str) -> list[int]:
    val = params.get(key)
    if val is None:
        return []
    if not isinstance(val, list) or not all(
        isinstance(x, int) and not isinstance(x, bool) for x in val
    ):
        raise ContractInputError("invalid_input", f"parameter {key!r} must be a list of integers")
    return list(val)


def _parse_ranks_dict(params: Mapping[str, Any], key: str = "learned") -> dict[str, int]:
    raw = params.get(key)
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise ContractInputError(
            "invalid_input", f"parameter {key!r} must be an object mapping slot to integer rank"
        )
    ranks: dict[str, int] = {}
    for slot, rank in raw.items():
        if isinstance(rank, bool) or not isinstance(rank, int):
            raise ContractInputError("invalid_input", f"{key}.{slot} must be an integer")
        ranks[str(slot).upper()] = rank
    return ranks


def _parse_inputs_dict(params: Mapping[str, Any], key: str = "inputs") -> dict[str, Fraction]:
    raw = params.get(key)
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise ContractInputError("invalid_input", f"parameter {key!r} must be a JSON object")
    out: dict[str, Fraction] = {}
    for k, v in raw.items():
        if isinstance(v, bool) or not isinstance(v, (int, float, str)):
            raise ContractInputError("invalid_input", f"{key}.{k} must be a number")
        try:
            out[str(k)] = to_fraction(str(v), f"{key}.{k}")
        except DamageInputError as exc:
            raise ContractInputError("invalid_input", str(exc)) from exc
    return out


def _parse_assumptions_dict(params: Mapping[str, Any]) -> dict[str, str]:
    raw = params.get("assume")
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise ContractInputError("invalid_input", "parameter 'assume' must be a JSON object")
    return {str(k): str(v) for k, v in raw.items()}


def _build_sheet_for_contract(
    root: Path,
    champion,
    level: int,
    item_ids: list[str],
    runes: list[int],
    shards: list[int],
    issues,
    assumptions: Mapping[str, str],
    derived,
    inputs: Mapping[str, Fraction],
    *,
    extra_contributions=(),
    combat_context: str = "stats",
    kit=None,
    allow_illegal: bool = False,
    summoners: Sequence[str] = (),
    elixir: str | None = None,
    ornn_item: str | None = None,
) -> tuple[Any, list[str]]:
    """Build a StatSheet with legality, passive, rune and summoner checks."""
    items = load_items(root, item_ids)
    try:
        res = assemble_stat_sheet(
            root,
            champion,
            level,
            items,
            runes,
            shards,
            issues,
            assumptions,
            derived,
            extras=extra_contributions,
            inputs=inputs,
            combat_context=combat_context,
            kit=kit,
            allow_illegal=allow_illegal,
            summoners=summoners,
            elixir=elixir,
            ornn_item=ornn_item,
            check_items_legality=bool(item_ids),
            who="build",
        )
    except LoadoutError as exc:
        raise ContractInputError(exc.code, str(exc)) from exc
    return res.sheet, [*res.notes, *res.warnings]


def _resolve_target(
    params: Mapping[str, Any],
    root: Path,
    issues,
    derived,
    *,
    inputs: Mapping[str, Fraction] | None = None,
    allow_illegal: bool = False,
):
    target_cfg = params.get("target")
    if not isinstance(target_cfg, Mapping):
        raise ContractInputError(
            "missing_input",
            "missing required 'target' object (manual armor/mr/max_health or champion/level)",
            missing_fields=("target",),
        )
    t_runes = _int_list(target_cfg, "runes")
    t_shards = _int_list(target_cfg, "shards")
    if target_cfg.get("champion"):
        t_champ = load_champion(root, _require_str(target_cfg, "champion"))
        t_level = _require_int(target_cfg, "level", minimum=1)
        t_items = _str_list(target_cfg, "items")
        t_inputs = {**(inputs or {}), **_parse_inputs_dict(target_cfg, "inputs")}
        t_kit = load_kit(root, t_champ.id)
        t_sheet, _ = _build_sheet_for_contract(
            root,
            t_champ,
            t_level,
            t_items,
            t_runes,
            t_shards,
            issues,
            {},
            derived,
            t_inputs,
            combat_context="stats",
            kit=t_kit,
            allow_illegal=allow_illegal,
        )
        return target_from_sheet(
            t_sheet,
            current_health=_optional_fraction(target_cfg, "current_health"),
            shield=_optional_fraction(target_cfg, "shield") or Fraction(0),
            shield_type=str(target_cfg.get("shield_type", "normal")),
            runes=t_runes,
        )
    if t_runes or t_shards:
        raise ContractInputError(
            "invalid_input", "target.runes and target.shards require target.champion"
        )
    armor = _optional_fraction(target_cfg, "armor")
    mr = _optional_fraction(target_cfg, "mr")
    if armor is None or mr is None:
        missing = [k for k, v in (("target.armor", armor), ("target.mr", mr)) if v is None]
        raise ContractInputError(
            "missing_input",
            "manual target requires 'armor' and 'mr'",
            missing_fields=missing,
        )
    return target_from_values(
        armor,
        mr,
        max_health=_optional_fraction(target_cfg, "max_health"),
        current_health=_optional_fraction(target_cfg, "current_health"),
        bonus_health=_optional_fraction(target_cfg, "bonus_health"),
        kind=target_cfg.get("kind"),
        shield=_optional_fraction(target_cfg, "shield") or Fraction(0),
        shield_type=str(target_cfg.get("shield_type", "normal")),
    )


def _crit_base(champion_id: str, patch: str, derived) -> CritBase | None:
    return resolve_crit_base(champion_id, patch, derived)


def _infer_holder_range(champion, explicit: str | None) -> tuple[str | None, list[str]]:
    if explicit is not None:
        return explicit, []
    atk_range = champion.stats.get("attackrange")
    if atk_range is None:
        return None, []
    inferred = "melee" if atk_range < 300 else "ranged"
    return inferred, [
        f"holder_range inferred as {inferred!r} from Data Dragon attackrange={atk_range}"
    ]


def _handle_lookup(params: Mapping[str, Any], root: Path) -> dict[str, Any]:
    """Resolve champions, kits/cases, items, or runes without guessing IDs (IA-02)."""
    entity = _require_str(params, "entity").lower()
    query = str(params.get("query", "")).strip().lower()
    limit = _optional_int(params, "limit", 20) or 20
    model, _ = load_model(root)
    patch = str(model.get("game_version", ""))

    if entity == "champion":
        name = _require_str(params, "champion")
        champ = load_champion(root, name)
        kit = load_kit(root, champ.id)
        kit_summary: dict[str, Any] | None = None
        if kit is not None:
            abilities_out: dict[str, Any] = {}
            passive_effects_ids: list[str] = []
            for slot, ab in kit.abilities.items():
                passive_effects_ids.extend(e.id for e in ab.passive_effects)
                abilities_out[slot] = {
                    "name": ab.name,
                    "max_rank": ab.max_rank,
                    "cases": [
                        {
                            "id": c.id,
                            "recast": c.recast,
                            "aoe": c.aoe,
                            "max_targets": c.max_targets,
                            "secondary_damage_ratio": None
                            if c.secondary_damage_ratio is None
                            else float(c.secondary_damage_ratio),
                        }
                        for c in ab.cases
                    ],
                    "active_effects": [
                        {"id": ae.id, "name": ae.name, "kind": ae.kind} for ae in ab.active_effects
                    ],
                    "not_modelled": list(ab.not_modelled),
                }
            kit_summary = {
                "game_version": kit.game_version,
                "abilities": abilities_out,
                "passive_effects": passive_effects_ids,
            }
        atk_range = champ.stats.get("attackrange")
        return {
            "patch": champ.patch,
            "result_label": "Oficial",
            "weakest_input_label": "Derivado" if kit_summary else "Oficial",
            "assumptions": [],
            "not_modelled": [],
            "result": {
                "id": champ.id,
                "name": champ.name,
                "resource": champ.resource,
                "attackrange": None if atk_range is None else float(atk_range),
                "inferred_range": None
                if atk_range is None
                else ("melee" if atk_range < 300 else "ranged"),
                "spells": [
                    {
                        "slot": s.slot,
                        "name": s.name,
                        "cooldowns": [float(c) for c in s.cooldowns],
                        "costs": [float(c) for c in s.costs],
                    }
                    for s in champ.spells
                ],
                "kit": kit_summary,
            },
        }

    if entity == "items":
        only_complete = bool(params.get("only_complete", False))
        matches = []
        for obj in model.get("objects") or ():
            if only_complete and obj.get("effect_review") != "complete":
                continue
            item_id = str(obj.get("id", ""))
            name = str(obj.get("name", ""))
            if query and query not in item_id.lower() and query not in name.lower():
                continue
            matches.append(
                {
                    "id": item_id,
                    "name": name,
                    "gold": (obj.get("gold") or {}).get("total"),
                    "effect_review": obj.get("effect_review"),
                    "effects": [
                        {
                            "id": e.get("id"),
                            "name": e.get("name"),
                            "model_status": e.get("model_status"),
                        }
                        for e in obj.get("effects") or ()
                    ],
                }
            )
        return {
            "patch": patch,
            "result_label": "Oficial",
            "weakest_input_label": "Derivado",
            "assumptions": [],
            "not_modelled": [],
            "result": {"total_matches": len(matches), "items": matches[:limit]},
        }

    if entity == "runes":
        rune_data = load_runes(root)
        if rune_data is None:
            raise ContractInputError("not_found", "lol-knowledge/derived/runes.json is missing")
        shard_ids = {sid for row in rune_data.shard_rows for sid in row}
        matches = []
        shards = []
        for rid, rune in sorted(rune_data.runes.items()):
            tree_info = rune_data.tree_of(rid)
            tree_name = tree_info[0].name if tree_info is not None else ""
            if (
                query
                and query not in str(rid)
                and query not in rune.name.lower()
                and query not in rune.key.lower()
                and query not in tree_name.lower()
            ):
                continue
            entry = {
                "id": rid,
                "key": rune.key,
                "name": rune.name,
                "tree": tree_name or None,
                "row": None if tree_info is None else tree_info[1],
            }
            if rid in shard_ids:
                shards.append(entry)
            else:
                matches.append(entry)
        return {
            "patch": patch,
            "result_label": "Derivado",
            "weakest_input_label": "Derivado",
            "assumptions": [],
            "not_modelled": [],
            "result": {
                "total_runes": len(matches),
                "runes": matches[:limit],
                "shards": shards[:limit],
            },
        }

    if entity == "summoners":
        summ_data = load_summoner_spells(root)
        if summ_data is None:
            raise ContractInputError(
                "not_found", "lol-knowledge/derived/summoner-spells.json is missing"
            )
        matches = []
        for sp in summ_data.spells.values():
            if (
                query
                and query not in sp.id.lower()
                and query not in sp.alias.lower()
                and query not in sp.name.lower()
            ):
                continue
            matches.append(
                {
                    "id": sp.id,
                    "alias": sp.alias,
                    "name": sp.name,
                    "cooldown_seconds": float(sp.cooldown_seconds),
                    "cast_range": None if sp.cast_range is None else float(sp.cast_range),
                    "model_status": sp.model_status,
                    "data_values": {k: float(v) for k, v in sp.data_values.items()},
                    "calculations": dict(sp.calculations),
                    "source": sp.source,
                }
            )
        return {
            "patch": patch,
            "result_label": "Derivado",
            "weakest_input_label": summ_data.label_for(patch).value,
            "assumptions": [],
            "not_modelled": [],
            "result": {"total_summoners": len(matches), "summoners": matches[:limit]},
        }

    raise ContractInputError(
        "invalid_input",
        f"entity must be 'champion', 'items', 'runes', or 'summoners', got {entity!r}",
    )


def _handle_stats(params: Mapping[str, Any], root: Path) -> dict[str, Any]:
    champ = load_champion(root, _require_str(params, "champion"))
    level = _require_int(params, "level", minimum=1)
    item_ids = _str_list(params, "items")
    runes = _int_list(params, "runes")
    shards = _int_list(params, "shards")
    summoners = _str_list(params, "summoners")
    ranks = _parse_ranks_dict(params)
    inputs = _parse_inputs_dict(params)
    assumptions_map = _parse_assumptions_dict(params)
    issues = load_issues(root)
    derived = load_records(root)
    kit = load_kit(root, champ.id)
    extras = passive_contributions(kit, ranks) if kit and ranks else ()
    sheet, warnings = _build_sheet_for_contract(
        root,
        champ,
        level,
        item_ids,
        runes,
        shards,
        issues,
        assumptions_map,
        derived,
        inputs,
        extra_contributions=extras,
        combat_context="stats",
        kit=kit,
        allow_illegal=bool(params.get("allow_illegal_build", False)),
        summoners=summoners,
        elixir=params.get("elixir") if isinstance(params.get("elixir"), str) else None,
        ornn_item=params.get("ornn_item") if isinstance(params.get("ornn_item"), str) else None,
    )
    payload = stats_to_dict(sheet)
    weakest_lbl = weakest(
        [*(v.label for v in sheet.values.values()), *(Label.PENDING for _ in sheet.pending_effects)]
    )
    return {
        "patch": champ.patch,
        "result_label": "Calculado",
        "weakest_input_label": weakest_lbl.value,
        "assumptions": [f"{k}={v}" for k, v in assumptions_map.items()],
        "not_modelled": [*sheet.pending_effects, *warnings],
        "result": payload,
    }


def _handle_ability(params: Mapping[str, Any], root: Path) -> dict[str, Any]:
    champ = load_champion(root, _require_str(params, "champion"))
    level = _require_int(params, "level", minimum=1)
    slot = _require_str(params, "ability").upper()
    rank = _require_int(params, "rank", minimum=1)
    case = params.get("case")
    item_ids = _str_list(params, "items")
    runes = _int_list(params, "runes")
    shards = _int_list(params, "shards")
    summoners = _str_list(params, "summoners")
    ranks = _parse_ranks_dict(params)
    ranks[slot] = rank
    inputs = _parse_inputs_dict(params)
    assumptions_map = _parse_assumptions_dict(params)
    target_count = _optional_int(params, "target_count", 1) or 1
    issues = load_issues(root)
    derived = load_records(root)
    kit = load_kit(root, champ.id)
    if kit is None:
        raise ContractInputError("not_found", f"{champ.id} has no kit.json")
    sheet, warnings = _build_sheet_for_contract(
        root,
        champ,
        level,
        item_ids,
        runes,
        shards,
        issues,
        assumptions_map,
        derived,
        inputs,
        extra_contributions=passive_contributions(kit, ranks),
        combat_context="ability",
        kit=kit,
        allow_illegal=bool(params.get("allow_illegal_build", False)),
        summoners=summoners,
        elixir=params.get("elixir") if isinstance(params.get("elixir"), str) else None,
        ornn_item=params.get("ornn_item") if isinstance(params.get("ornn_item"), str) else None,
    )
    target = _resolve_target(
        params,
        root,
        issues,
        derived,
        inputs=inputs,
        allow_illegal=bool(params.get("allow_illegal_build", False)),
    )
    outcome = evaluate_ability(
        kit,
        sheet,
        slot,
        rank,
        target,
        case=None if case is None else str(case),
        inputs=inputs,
        target_count=target_count,
    )
    payload = ability_to_dict(outcome, sheet, target)
    return {
        "patch": champ.patch,
        "result_label": "Calculado",
        "weakest_input_label": outcome.label.value,
        "assumptions": [f"{k}={v}" for k, v in assumptions_map.items()],
        "not_modelled": [*outcome.not_modelled, *warnings],
        "result": payload,
    }


def _handle_rotation(params: Mapping[str, Any], root: Path) -> dict[str, Any]:
    champ = load_champion(root, _require_str(params, "champion"))
    level = _require_int(params, "level", minimum=1)
    steps_text = _require_str(params, "steps")
    steps = parse_steps(steps_text)
    item_ids = _str_list(params, "items")
    runes = _int_list(params, "runes")
    shards = _int_list(params, "shards")
    summoners = _str_list(params, "summoners")
    ranks = _parse_ranks_dict(params)
    inputs = _parse_inputs_dict(params)
    assumptions_map = _parse_assumptions_dict(params)
    timeline = bool(params.get("timeline", False))
    target_count = _optional_int(params, "target_count", 1) or 1
    holder_range, inferred_assumptions = _infer_holder_range(champ, params.get("attacker_range"))
    issues = load_issues(root)
    derived = load_records(root)
    kit = load_kit(root, champ.id)
    if kit is None:
        raise ContractInputError("not_found", f"{champ.id} has no kit.json")
    sheet, warnings = _build_sheet_for_contract(
        root,
        champ,
        level,
        item_ids,
        runes,
        shards,
        issues,
        assumptions_map,
        derived,
        inputs,
        extra_contributions=passive_contributions(kit, ranks),
        combat_context="rotation",
        kit=kit,
        allow_illegal=bool(params.get("allow_illegal_build", False)),
        summoners=summoners,
        elixir=params.get("elixir") if isinstance(params.get("elixir"), str) else None,
        ornn_item=params.get("ornn_item") if isinstance(params.get("ornn_item"), str) else None,
    )
    target = _resolve_target(
        params,
        root,
        issues,
        derived,
        inputs=inputs,
        allow_illegal=bool(params.get("allow_illegal_build", False)),
    )
    crit_base = _crit_base(champ.id, champ.patch, derived)
    rune_data = load_runes(root) if (runes or target.runes) else None
    summoner_data = (
        load_summoner_spells(root)
        if (summoners or any(s.summoner_id is not None for s in steps))
        else None
    )
    ap_weight = derived.value(champ.id, "adaptiveforceapweight") if derived else None
    outcome = evaluate_rotation(
        kit,
        sheet,
        ranks,
        target,
        steps,
        crit_base,
        holder_range=holder_range,
        inputs=inputs,
        timeline=timeline,
        runes=runes,
        rune_data=rune_data,
        ap_weight=ap_weight,
        start_resource=_optional_fraction(params, "attacker_resource"),
        allow_insufficient_resource=bool(params.get("allow_insufficient_resource", False)),
        target_count=target_count,
        summoners=summoners,
        summoner_data=summoner_data,
    )
    raw_windows = params.get("windows")
    win_secs: list[Fraction] = []
    if raw_windows is not None:
        if not isinstance(raw_windows, list):
            raise ContractInputError(
                "invalid_input", "parameter 'windows' must be a list of numbers"
            )
        for w in raw_windows:
            if isinstance(w, bool) or not isinstance(w, (int, float, str)):
                raise ContractInputError("invalid_input", "window values must be positive numbers")
            val = to_fraction(str(w), "windows")
            if val <= 0:
                raise ContractInputError("invalid_input", "window values must be positive")
            win_secs.append(val)
    if win_secs and not timeline:
        raise ContractInputError("invalid_input", "parameter 'windows' requires timeline=true")
    payload = rotation_to_dict(outcome, sheet, target, crit_base, windows=win_secs)
    return {
        "patch": champ.patch,
        "result_label": "Calculado",
        "weakest_input_label": outcome.label.value,
        "assumptions": [*inferred_assumptions, *(f"{k}={v}" for k, v in assumptions_map.items())],
        "not_modelled": [*outcome.notes, *warnings],
        "result": payload,
    }


def _build_enemy_hits_context(
    enemy: Any,
    root: Path,
    issues,
    derived,
    assumptions_map: Mapping[str, str],
    inputs: Mapping[str, Fraction],
    *,
    timeline: bool,
    allow_illegal: bool,
):
    if not isinstance(enemy, Mapping):
        raise ContractInputError("invalid_input", "'enemy' must be an object")
    e_champ = load_champion(root, _require_str(enemy, "champion"))
    e_level = _require_int(enemy, "level", minimum=1)
    steps_text = _require_str(enemy, "steps")
    e_steps = parse_steps(steps_text)
    e_items = _str_list(enemy, "items")
    e_runes = _int_list(enemy, "runes")
    e_shards = _int_list(enemy, "shards")
    e_summoners = _str_list(enemy, "summoners")
    e_ranks = _parse_ranks_dict(enemy)
    e_inputs = {**inputs, **_parse_inputs_dict(enemy, "inputs")}
    e_kit = load_kit(root, e_champ.id)
    if e_kit is None:
        raise ContractInputError("not_found", f"enemy {e_champ.id} has no kit.json")
    e_sheet, e_warnings = _build_sheet_for_contract(
        root,
        e_champ,
        e_level,
        e_items,
        e_runes,
        e_shards,
        issues,
        assumptions_map,
        derived,
        e_inputs,
        extra_contributions=passive_contributions(e_kit, e_ranks),
        combat_context="rotation",
        kit=e_kit,
        allow_illegal=allow_illegal,
        summoners=e_summoners,
    )
    e_range, _ = _infer_holder_range(e_champ, enemy.get("range"))
    e_crit = _crit_base(e_champ.id, e_champ.patch, derived)
    e_rune_data = load_runes(root) if e_runes else None
    e_summoner_data = (
        load_summoner_spells(root)
        if (e_summoners or any(s.summoner_id is not None for s in e_steps))
        else None
    )
    e_ap_weight = derived.value(e_champ.id, "adaptiveforceapweight") if derived else None

    def _hits_for_sheet(def_sheet, current_health: Fraction | None = None):
        rot = evaluate_rotation(
            e_kit,
            e_sheet,
            e_ranks,
            target_from_sheet(def_sheet, current_health=current_health),
            e_steps,
            e_crit,
            holder_range=e_range,
            inputs=e_inputs,
            timeline=timeline,
            runes=e_runes,
            rune_data=e_rune_data,
            ap_weight=e_ap_weight,
            summoners=e_summoners,
            summoner_data=e_summoner_data,
        )
        return hits_from_rotation(rot)

    enemy_desc = f"{e_champ.name} level {e_level}: {steps_text}"
    return _hits_for_sheet, e_sheet, e_range, enemy_desc, e_warnings


def _handle_survive(params: Mapping[str, Any], root: Path) -> dict[str, Any]:
    champ = load_champion(root, _require_str(params, "champion"))
    level = _require_int(params, "level", minimum=1)
    item_ids = _str_list(params, "items")
    runes = _int_list(params, "runes")
    shards = _int_list(params, "shards")
    summoners = _str_list(params, "summoners")
    inputs = _parse_inputs_dict(params)
    assumptions_map = _parse_assumptions_dict(params)
    timeline = bool(params.get("timeline", False))
    allow_illegal = bool(params.get("allow_illegal_build", False))
    issues = load_issues(root)
    derived = load_records(root)
    kit = load_kit(root, champ.id)
    sheet, warnings = _build_sheet_for_contract(
        root,
        champ,
        level,
        item_ids,
        runes,
        shards,
        issues,
        assumptions_map,
        derived,
        inputs,
        combat_context="survive",
        kit=kit,
        allow_illegal=allow_illegal,
        summoners=summoners,
        elixir=params.get("elixir") if isinstance(params.get("elixir"), str) else None,
        ornn_item=params.get("ornn_item") if isinstance(params.get("ornn_item"), str) else None,
    )
    incoming = params.get("incoming")
    enemy = params.get("enemy")
    if bool(incoming) == bool(enemy):
        raise ContractInputError(
            "missing_input",
            "provide either 'incoming' string or 'enemy' object (not both)",
            missing_fields=("incoming",),
        )
    start_hp = _optional_fraction(params, "defender_health")
    start_sh = _optional_fraction(params, "defender_shield") or Fraction(0)
    sh_type = str(params.get("defender_shield_type", "normal"))
    enemy_desc = ""
    if incoming:
        hits = parse_incoming(str(incoming))
        enemy_desc = str(incoming)
    else:
        hits_for_sheet, e_sheet, e_range, enemy_desc, e_warnings = _build_enemy_hits_context(
            enemy,
            root,
            issues,
            derived,
            assumptions_map,
            inputs,
            timeline=timeline,
            allow_illegal=allow_illegal,
        )
        warnings.extend(e_warnings)
        hits = hits_for_sheet(sheet, start_hp)
        if any(it.id == "6695" for it in e_sheet.items) and "shield_reaver" not in inputs:
            inputs = {
                **inputs,
                "shield_reaver": Fraction(35, 100) if e_range == "ranged" else Fraction(50, 100),
            }
    rune_data = load_runes(root) if runes else None
    summoner_data = load_summoner_spells(root) if summoners else None
    defender_casts = _str_list(params, "defender_casts")
    defender_ranks = _parse_ranks_dict(params)
    outcome = evaluate_defense(
        sheet,
        hits,
        enemy_description=enemy_desc,
        start_health=start_hp,
        start_shield=start_sh,
        shield_type=sh_type,
        runes=runes,
        rune_data=rune_data,
        inputs=inputs,
        timeline=timeline,
        kit=kit,
        summoners=summoners,
        summoner_data=summoner_data,
        defender_casts=defender_casts,
        defender_ranks=defender_ranks,
    )
    payload = defense_to_dict(outcome, sheet)
    return {
        "patch": champ.patch,
        "result_label": "Calculado",
        "weakest_input_label": outcome.label.value,
        "assumptions": [f"{k}={v}" for k, v in assumptions_map.items()],
        "not_modelled": [*outcome.notes, *warnings],
        "result": payload,
    }


def _build_duel_fighter(
    fighter_params: Mapping[str, Any],
    root: Path,
    issues,
    derived,
    *,
    side_label: str,
    allow_illegal: bool,
) -> tuple[DuelFighterSpec, list[str], list[str]]:
    if not isinstance(fighter_params, Mapping):
        raise ContractInputError(
            "invalid_input",
            f"parameter {side_label!r} must be a fighter JSON object",
        )
    champ = load_champion(root, _require_str(fighter_params, "champion"))
    level = _require_int(fighter_params, "level", minimum=1)
    kit = load_kit(root, champ.id)
    if kit is None:
        raise KitError(f"{champ.id} has no kit yet (lol-knowledge/champions/{champ.id}/kit.json)")
    item_ids = _str_list(fighter_params, "items")
    runes = _int_list(fighter_params, "runes")
    shards = _int_list(fighter_params, "shards")
    summoners = _str_list(fighter_params, "summoners")
    ranks = _parse_ranks_dict(fighter_params)
    inputs = _parse_inputs_dict(fighter_params)
    assumptions_map = _parse_assumptions_dict(fighter_params)
    steps_raw = fighter_params.get("steps")
    steps = (
        parse_steps(str(steps_raw)) if (isinstance(steps_raw, str) and steps_raw.strip()) else ()
    )
    prio_raw = _str_list(fighter_params, "priority_slots")
    priority_slots = tuple(prio_raw) if prio_raw else DEFAULT_PRIORITY_SLOTS

    sheet, warnings = _build_sheet_for_contract(
        root,
        champ,
        level,
        item_ids,
        runes,
        shards,
        issues,
        assumptions_map,
        derived,
        inputs,
        extra_contributions=passive_contributions(kit, ranks),
        combat_context="rotation",
        kit=kit,
        allow_illegal=allow_illegal,
        summoners=summoners,
        elixir=fighter_params.get("elixir")
        if isinstance(fighter_params.get("elixir"), str)
        else None,
        ornn_item=fighter_params.get("ornn_item")
        if isinstance(fighter_params.get("ornn_item"), str)
        else None,
    )
    holder_range, inferred = _infer_holder_range(champ, fighter_params.get("range"))
    rune_data = load_runes(root) if (runes or shards) else None
    summoner_data = (
        load_summoner_spells(root)
        if (summoners or any(s.summoner_id is not None for s in steps))
        else None
    )
    ap_weight = derived.value(champ.id, "adaptiveforceapweight") if derived else None
    spec = DuelFighterSpec(
        sheet=sheet,
        kit=kit,
        ranks=ranks,
        crit_base=_crit_base(champ.id, champ.patch, derived),
        steps=steps,
        priority_slots=priority_slots,
        holder_range=holder_range,
        start_health=_optional_fraction(fighter_params, "health"),
        start_shield=_optional_fraction(fighter_params, "shield") or Fraction(0),
        shield_type=str(fighter_params.get("shield_type", "normal")),
        runes=runes,
        rune_data=rune_data,
        summoners=summoners,
        summoner_data=summoner_data,
        inputs=inputs,
        start_resource=_optional_fraction(fighter_params, "resource"),
        allow_insufficient_resource=bool(fighter_params.get("allow_insufficient_resource", False)),
        apply_passives=bool(fighter_params.get("apply_passives", True)),
        ap_weight=ap_weight,
    )
    assumptions = [
        *(f"{side_label}: {a}" for a in inferred),
        *(f"{side_label}.{k}={v}" for k, v in assumptions_map.items()),
    ]
    return spec, assumptions, [f"{side_label}: {w}" for w in warnings]


def _handle_duel(params: Mapping[str, Any], root: Path) -> dict[str, Any]:
    raw_a = params.get("fighter_a")
    raw_b = params.get("fighter_b")
    missing = [k for k, v in (("fighter_a", raw_a), ("fighter_b", raw_b)) if v is None]
    if missing:
        raise ContractInputError(
            "missing_input",
            "duel requires both 'fighter_a' and 'fighter_b' objects "
            f"(missing: {', '.join(missing)})",
            missing_fields=missing,
        )
    allow_illegal = bool(params.get("allow_illegal_build", False))
    mode = str(params.get("mode", DEFAULT_DUEL_MODE))
    tie_break = str(params.get("tie_break", DEFAULT_DUEL_TIE_BREAK))
    max_duration = _optional_fraction(params, "max_duration") or DEFAULT_DUEL_MAX_DURATION
    issues = load_issues(root)
    derived = load_records(root)
    spec_a, assump_a, warn_a = _build_duel_fighter(
        raw_a,
        root,
        issues,
        derived,
        side_label="fighter_a",
        allow_illegal=allow_illegal,
    )
    spec_b, assump_b, warn_b = _build_duel_fighter(
        raw_b,
        root,
        issues,
        derived,
        side_label="fighter_b",
        allow_illegal=allow_illegal,
    )
    outcome = evaluate_duel(
        spec_a,
        spec_b,
        mode=mode,
        tie_break=tie_break,
        max_duration=max_duration,
    )
    return {
        "patch": outcome.patch,
        "result_label": "Calculado",
        "weakest_input_label": outcome.label.value,
        "assumptions": [*assump_a, *assump_b],
        "not_modelled": [*outcome.notes, *warn_a, *warn_b],
        "result": duel_to_dict(outcome),
    }


def _handle_optimize(params: Mapping[str, Any], root: Path) -> dict[str, Any]:
    champ = load_champion(root, _require_str(params, "champion"))
    level = _require_int(params, "level", minimum=1)
    objective = _require_str(params, "objective")
    issues = load_issues(root)
    derived = load_records(root)
    assumptions_map = _parse_assumptions_dict(params)
    inputs = _parse_inputs_dict(params)
    allow_illegal = bool(params.get("allow_illegal_build", False))
    damage_mix = _optional_fraction(params, "damage_mix_physical")
    if damage_mix is None:
        damage_mix = Fraction(1, 2)
    constraints = OptimizeConstraints(
        budget=_optional_int(params, "budget"),
        slots=_optional_int(params, "slots", 6) or 6,
        required_items=tuple(_str_list(params, "required_items")),
        forbidden_items=tuple(_str_list(params, "forbidden_items")),
        require_boots=bool(params.get("require_boots", False)),
        tier=str(params.get("tier", "completed")),
        only_verified=bool(params.get("only_verified", False)),
        top=_optional_int(params, "top", 5) or 5,
        beam_width=_optional_int(params, "beam_width", 12) or 12,
        pool_limit=_optional_int(params, "pool_limit", 16) or 16,
        damage_mix_physical=damage_mix,
        use_item_actives=bool(params.get("use_item_actives", False)),
        elixir=params.get("elixir") if isinstance(params.get("elixir"), str) else None,
        ornn_upgrade=bool(params.get("ornn_upgrade", False)),
        purchase_curve=bool(params.get("purchase_curve", False)),
        gold_checkpoints=tuple(_int_list(params, "gold_checkpoints")),
    )
    runes = _int_list(params, "runes")
    shards = _int_list(params, "shards")
    summoners = _str_list(params, "summoners")
    rune_data = load_runes(root) if (runes or shards) else None
    kit = load_kit(root, champ.id)
    ranks = _parse_ranks_dict(params)
    holder_range, inferred_assumptions = _infer_holder_range(champ, params.get("attacker_range"))
    timeline = bool(params.get("timeline", False))
    target_count = _optional_int(params, "target_count", 1) or 1

    target = None
    steps = ()
    if objective in {"rotation_damage", "dps", "healing"}:
        steps_raw = params.get("steps")
        if isinstance(steps_raw, str) and steps_raw.strip():
            steps = parse_steps(steps_raw)
        target = _resolve_target(
            params,
            root,
            issues,
            derived,
            inputs=inputs,
            allow_illegal=allow_illegal,
        )
        if rune_data is None and target.runes:
            rune_data = load_runes(root)

    incoming_hits = ()
    incoming_hits_for_sheet = None
    extra_warnings: list[str] = []
    duel_enemy: DuelFighterSpec | None = None
    duel_mode = str(params.get("duel_mode", DEFAULT_DUEL_MODE))
    duel_tie_break = str(params.get("duel_tie_break", DEFAULT_DUEL_TIE_BREAK))
    duel_max_duration = _optional_fraction(params, "duel_max_duration") or DEFAULT_DUEL_MAX_DURATION
    prio_raw = _str_list(params, "priority_slots")
    duel_priority_slots = tuple(prio_raw) if prio_raw else DEFAULT_PRIORITY_SLOTS
    if objective == "duel":
        steps_raw = params.get("steps")
        if isinstance(steps_raw, str) and steps_raw.strip():
            steps = parse_steps(steps_raw)
        enemy = params.get("enemy")
        if enemy is None:
            raise ContractInputError(
                "missing_input",
                "objective 'duel' requires an 'enemy' fighter object",
                missing_fields=("enemy",),
            )
        duel_enemy, e_assump, e_warnings = _build_duel_fighter(
            enemy,
            root,
            issues,
            derived,
            side_label="enemy",
            allow_illegal=allow_illegal,
        )
        inferred_assumptions = [*inferred_assumptions, *e_assump]
        extra_warnings.extend(e_warnings)
    if objective == "time_to_die":
        incoming = params.get("incoming")
        enemy = params.get("enemy")
        if bool(incoming) == bool(enemy):
            raise ContractInputError(
                "missing_input",
                "objective 'time_to_die' requires either 'incoming' string or 'enemy' object",
                missing_fields=("incoming",),
            )
        if incoming:
            incoming_hits = parse_incoming(str(incoming))
        else:
            hits_for_sheet, e_sheet, e_range, _, e_warnings = _build_enemy_hits_context(
                enemy,
                root,
                issues,
                derived,
                assumptions_map,
                inputs,
                timeline=timeline,
                allow_illegal=allow_illegal,
            )
            extra_warnings.extend(e_warnings)
            if any(it.id == "6695" for it in e_sheet.items) and "shield_reaver" not in inputs:
                inputs = {
                    **inputs,
                    "shield_reaver": Fraction(35, 100)
                    if e_range == "ranged"
                    else Fraction(50, 100),
                }
            incoming_hits_for_sheet = hits_for_sheet

    outcome = optimize_build(
        root,
        champ,
        level,
        objective,
        constraints=constraints,
        issues=issues,
        derived=derived,
        assumptions=assumptions_map,
        inputs=inputs,
        kit=kit,
        ranks=ranks,
        target=target,
        steps=steps,
        crit_base=_crit_base(champ.id, champ.patch, derived),
        holder_range=holder_range,
        timeline=timeline,
        target_count=target_count,
        incoming_hits=incoming_hits,
        incoming_hits_for_sheet=incoming_hits_for_sheet,
        runes=runes,
        shards=shards,
        rune_data=rune_data,
        summoners=summoners,
        defender_casts=_str_list(params, "defender_casts"),
        duel_enemy=duel_enemy,
        duel_mode=duel_mode,
        duel_tie_break=duel_tie_break,
        duel_max_duration=duel_max_duration,
        duel_priority_slots=duel_priority_slots,
    )
    payload = optimize_to_dict(outcome)
    return {
        "patch": champ.patch,
        "result_label": "Calculado",
        "weakest_input_label": outcome.label.value,
        "assumptions": [*inferred_assumptions, *(f"{k}={v}" for k, v in assumptions_map.items())],
        "not_modelled": [*outcome.notes, *extra_warnings],
        "result": payload,
    }


def execute_request(request: Mapping[str, Any], root: Path) -> dict[str, Any]:
    """Execute one versioned ``lol-knowledge-contract/1`` request and return its envelope."""
    if not isinstance(request, Mapping):
        return {
            "schema": CONTRACT_SCHEMA,
            "ok": False,
            "operation": None,
            "error": {"code": "invalid_input", "message": "request must be a JSON object"},
        }
    schema = request.get("schema")
    if schema is not None and schema != CONTRACT_SCHEMA:
        return {
            "schema": CONTRACT_SCHEMA,
            "ok": False,
            "operation": request.get("operation"),
            "error": {
                "code": "invalid_input",
                "message": f"unsupported schema {schema!r}; expected {CONTRACT_SCHEMA!r}",
            },
        }
    operation = request.get("operation")
    if not isinstance(operation, str) or operation not in OPERATIONS:
        return {
            "schema": CONTRACT_SCHEMA,
            "ok": False,
            "operation": operation,
            "error": {
                "code": "invalid_input",
                "message": f"operation must be one of {sorted(OPERATIONS)}, got {operation!r}",
            },
        }
    params = request.get("params")
    if not isinstance(params, Mapping):
        return {
            "schema": CONTRACT_SCHEMA,
            "ok": False,
            "operation": operation,
            "error": {
                "code": "missing_input",
                "message": "request requires a 'params' JSON object",
                "missing_fields": ["params"],
            },
        }

    handlers = {
        "lookup": _handle_lookup,
        "stats": _handle_stats,
        "ability": _handle_ability,
        "rotation": _handle_rotation,
        "survive": _handle_survive,
        "duel": _handle_duel,
        "optimize": _handle_optimize,
    }
    try:
        data = handlers[operation](params, root)
    except ContractInputError as exc:
        err: dict[str, Any] = {"code": exc.code, "message": str(exc)}
        if exc.missing_fields:
            err["missing_fields"] = list(exc.missing_fields)
        return {
            "schema": CONTRACT_SCHEMA,
            "ok": False,
            "operation": operation,
            "error": err,
        }
    except (StatsError, KitError, RotationError, DamageInputError) as exc:
        return {
            "schema": CONTRACT_SCHEMA,
            "ok": False,
            "operation": operation,
            "error": {"code": "invalid_input", "message": str(exc)},
        }
    except OSError as exc:
        return {
            "schema": CONTRACT_SCHEMA,
            "ok": False,
            "operation": operation,
            "error": {"code": "not_found", "message": str(exc)},
        }

    return {
        "schema": CONTRACT_SCHEMA,
        "ok": True,
        "operation": operation,
        "patch": data["patch"],
        "result_label": data["result_label"],
        "weakest_input_label": data["weakest_input_label"],
        "inputs": dict(params),
        "assumptions": data["assumptions"],
        "not_modelled": data["not_modelled"],
        "result": data["result"],
        "explanation_contract": dict(EXPLANATION_CONTRACT),
    }
