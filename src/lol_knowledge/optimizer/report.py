"""Text and JSON reports for the build optimizer (OPT-01..OPT-03)."""

from __future__ import annotations

from typing import Any

from ..damage import format_number
from .models import BuildResult, OptimizeOutcome

RESULT_LABEL = "Calculado"


def _build_dict(build: BuildResult) -> dict[str, Any]:
    return {
        "items": list(build.items),
        "item_names": list(build.item_names),
        "total_gold": build.total_gold,
        "score": float(build.score),
        "exact_score": str(build.score),
        "label": build.label.value,
        "verified": build.verified,
        "metrics": dict(build.metrics),
        "notes": list(build.notes),
    }


def _format_build(rank: int, build: BuildResult, objective: str) -> list[str]:
    item_desc = (
        ", ".join(
            f"{item_id} {name}" for item_id, name in zip(build.items, build.item_names, strict=True)
        )
        or "none"
    )
    if objective == "time_to_die":
        if build.metrics.get("survived"):
            score_str = f"SURVIVED (remaining {format_number(build.score)} HP+shield)"
        elif build.metrics.get("time_to_die") is not None:
            score_str = f"died at {format_number(build.score)} s"
        else:
            score_str = f"died at step {format_number(build.score)}"
    elif objective == "duel":
        w = build.metrics.get("winner", "draw_timeout")
        dur = build.metrics.get("duration", 0.0)
        rem_a = build.metrics.get("remaining_health", 0.0)
        rem_b = build.metrics.get("enemy_remaining_health", 0.0)
        if w == "A":
            score_str = f"WIN ({rem_a:.1f} HP left at {dur:.2f} s)"
        elif w == "B":
            score_str = f"LOSS (survived {dur:.2f} s, enemy {rem_b:.1f} HP left)"
        else:
            score_str = f"{str(w).upper()} (A {rem_a:.1f} vs B {rem_b:.1f} HP at {dur:.2f} s)"
    else:
        score_str = format_number(build.score)
    lines = [
        f"  #{rank} [{build.label.value}] {objective}={score_str} | "
        f"gold={build.total_gold} | items: {item_desc}"
    ]
    if build.notes:
        lines.append(f"      notes: {'; '.join(build.notes[:3])}")
    return lines


def format_text(outcome: OptimizeOutcome) -> str:
    cfg = outcome.constraints
    budget_str = "unlimited" if cfg.budget is None else f"{cfg.budget} g"
    lines = [
        f"optimizer: {outcome.champion} level {outcome.level}, patch {outcome.patch}",
        f"objective: {outcome.objective}",
        f"constraints: slots={cfg.slots}, budget={budget_str}, tier={cfg.tier}, "
        f"require_boots={cfg.require_boots}, only_verified={cfg.only_verified}",
    ]
    if cfg.required_items:
        lines.append(f"required items: {', '.join(cfg.required_items)}")
    if cfg.forbidden_items:
        lines.append(f"forbidden items: {', '.join(cfg.forbidden_items)}")
    st = outcome.stats
    lines.append(
        f"search: strategy={st.strategy}, pool={st.candidate_pool_size} "
        f"(verified={st.verified_pool_size}), evaluated={st.states_evaluated}, "
        f"pruned(illegal={st.pruned_illegal}, budget={st.pruned_budget}, beam={st.pruned_beam}), "
        f"elapsed={st.elapsed_ms:.1f} ms"
    )
    lines.append("verified builds (Oficial/Derivado):")
    if outcome.verified_builds:
        for idx, b in enumerate(outcome.verified_builds, start=1):
            lines.extend(_format_build(idx, b, outcome.objective))
    else:
        lines.append("  (none)")
    if not cfg.only_verified:
        lines.append("pending builds (Pendiente de verificación):")
        if outcome.pending_builds:
            for idx, b in enumerate(outcome.pending_builds, start=1):
                lines.extend(_format_build(idx, b, outcome.objective))
        else:
            lines.append("  (none)")
    for note in outcome.notes:
        lines.append(f"note: {note}")
    lines.append(f"label: {RESULT_LABEL} (weakest verified input: {outcome.label.value})")
    return "\n".join(lines)


def to_dict(outcome: OptimizeOutcome) -> dict[str, Any]:
    cfg = outcome.constraints
    st = outcome.stats
    return {
        "label": RESULT_LABEL,
        "weakest_input_label": outcome.label.value,
        "champion": outcome.champion,
        "level": outcome.level,
        "patch": outcome.patch,
        "objective": outcome.objective,
        "constraints": {
            "budget": cfg.budget,
            "slots": cfg.slots,
            "required_items": list(cfg.required_items),
            "forbidden_items": list(cfg.forbidden_items),
            "require_boots": cfg.require_boots,
            "tier": cfg.tier,
            "only_verified": cfg.only_verified,
            "top": cfg.top,
            "beam_width": cfg.beam_width,
            "pool_limit": cfg.pool_limit,
            "damage_mix_physical": float(cfg.damage_mix_physical),
        },
        "search_stats": {
            "candidate_pool_size": st.candidate_pool_size,
            "verified_pool_size": st.verified_pool_size,
            "states_evaluated": st.states_evaluated,
            "pruned_illegal": st.pruned_illegal,
            "pruned_budget": st.pruned_budget,
            "pruned_beam": st.pruned_beam,
            "elapsed_ms": st.elapsed_ms,
            "strategy": st.strategy,
        },
        "verified_builds": [_build_dict(b) for b in outcome.verified_builds],
        "pending_builds": [_build_dict(b) for b in outcome.pending_builds],
        "all_builds": [_build_dict(b) for b in outcome.all_builds],
        "notes": list(outcome.notes),
    }
