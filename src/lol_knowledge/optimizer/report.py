"""Text and JSON reports for the build optimizer (OPT-01..OPT-03)."""

from __future__ import annotations

from typing import Any

from ..damage import format_number
from .models import BuildResult, OptimizeOutcome

RESULT_LABEL = "Calculado"


def _build_dict(build: BuildResult) -> dict[str, Any]:
    out: dict[str, Any] = {
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
    if build.ornn_upgraded_item is not None:
        out["ornn_upgraded_item"] = build.ornn_upgraded_item
    if build.elixir is not None:
        out["elixir"] = build.elixir
    return out


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
    extra_tags = []
    if build.ornn_upgraded_item is not None:
        extra_tags.append(f"ornn={build.ornn_upgraded_item}")
    if build.elixir is not None:
        extra_tags.append(f"elixir={build.elixir}")
    tag_str = f" | {', '.join(extra_tags)}" if extra_tags else ""
    lines = [
        f"  #{rank} [{build.label.value}] {objective}={score_str} | "
        f"gold={build.total_gold}{tag_str} | items: {item_desc}"
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
    if outcome.purchase_curve:
        lines.append("purchase curve (OPT-04):")
        for step in outcome.purchase_curve:
            lines.append(
                f"  step {step.order}: +{step.item_id} {step.item_name} ({step.item_gold} g, "
                f"cum {step.cumulative_gold} g) -> {outcome.objective}={format_number(step.score)} "
                f"(+{format_number(step.delta_score)}, "
                f"{format_number(step.score_per_1000g)}/1000g) "
                f"[{step.label.value}]"
            )
    if outcome.gold_checkpoints:
        lines.append("gold checkpoints (OPT-04):")
        for cp in outcome.gold_checkpoints:
            if cp.build is None:
                lines.append(f"  {cp.gold_budget} g: (no legal build within budget)")
            else:
                cp_items = ", ".join(
                    f"{i} {n}" for i, n in zip(cp.build.items, cp.build.item_names, strict=True)
                )
                lines.append(
                    f"  {cp.gold_budget} g: [{cp.build.label.value}] "
                    f"{outcome.objective}={format_number(cp.build.score)} | "
                    f"gold={cp.build.total_gold} | items: {cp_items}"
                )
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
            "elixir": cfg.elixir,
            "ornn_upgrade": cfg.ornn_upgrade,
            "purchase_curve": cfg.purchase_curve,
            "gold_checkpoints": list(cfg.gold_checkpoints),
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
        "purchase_curve": [
            {
                "order": s.order,
                "item_id": s.item_id,
                "item_name": s.item_name,
                "item_gold": s.item_gold,
                "cumulative_gold": s.cumulative_gold,
                "items_so_far": list(s.items_so_far),
                "score": float(s.score),
                "delta_score": float(s.delta_score),
                "score_per_1000g": float(s.score_per_1000g),
                "label": s.label.value,
                "metrics": dict(s.metrics),
            }
            for s in outcome.purchase_curve
        ],
        "gold_checkpoints": [
            {
                "gold_budget": cp.gold_budget,
                "build": None if cp.build is None else _build_dict(cp.build),
            }
            for cp in outcome.gold_checkpoints
        ],
        "auto_steps": list(outcome.auto_steps),
        "notes": list(outcome.notes),
    }
