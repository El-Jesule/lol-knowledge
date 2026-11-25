"""Human-readable and JSON-contract formatting for 1v1 duel outcomes."""

from __future__ import annotations

from typing import Any

from .damage import format_number
from .duel import DuelEvent, DuelOutcome, FighterDuelSummary
from .resources import ResourceSummary


def _resource_to_dict(resource: ResourceSummary) -> dict[str, Any]:
    return {
        "kind": resource.kind,
        "name": resource.name,
        "maximum": float(resource.maximum),
        "start": float(resource.start),
        "spent": float(resource.spent),
        "exact_spent": str(resource.spent),
        "restored": float(resource.restored),
        "effective_restored": float(resource.effective_restored),
        "exact_effective_restored": str(resource.effective_restored),
        "regenerated": float(resource.regenerated),
        "exact_regenerated": str(resource.regenerated),
        "remaining": float(resource.remaining),
        "exact_remaining": str(resource.remaining),
        "health_cost_spent": float(resource.health_cost_spent),
        "insufficient_steps": list(resource.insufficient_steps),
        "uses_casting_pool": resource.uses_casting_pool,
        "label": resource.label.value,
        "notes": list(resource.notes),
    }


def _winner_text(outcome: DuelOutcome) -> str:
    if outcome.winner == "A":
        return f"A ({outcome.fighter_a.champion_name})"
    if outcome.winner == "B":
        return f"B ({outcome.fighter_b.champion_name})"
    if outcome.winner == "draw_mutual_kill":
        return "draw (mutual kill)"
    return "draw (timeout)"


def _fighter_line(summary: FighterDuelSummary) -> str:
    status = "alive" if summary.survived else "dead"
    pct = (
        format_number(summary.remaining_health * 100 / summary.max_health)
        if summary.max_health > 0
        else "0"
    )
    sh = (
        f" (+{format_number(summary.remaining_shield)} shield)"
        if summary.remaining_shield > 0
        else ""
    )
    return (
        f"{summary.side} {summary.champion_name} (lvl {summary.level}) — {status}: "
        f"HP {format_number(summary.remaining_health)}/{format_number(summary.max_health)} "
        f"({pct}%){sh} | dealt {format_number(summary.damage_dealt)} | "
        f"taken {format_number(summary.damage_taken)} | "
        f"healed {format_number(summary.healing_done)} | "
        f"shielded {format_number(summary.shield_granted)} | "
        f"actions {summary.actions_taken}"
    )


def format_text(outcome: DuelOutcome) -> str:
    """Format a ``DuelOutcome`` as concise, auditable plain text."""
    lines = [
        f"Duel 1v1 (patch {outcome.patch}, mode={outcome.mode}, tie_break={outcome.tie_break})",
        f"Winner: {_winner_text(outcome)} at {format_number(outcome.duration)} s "
        f"[{outcome.label.value}]",
        f"  {_fighter_line(outcome.fighter_a)}",
        f"  {_fighter_line(outcome.fighter_b)}",
        "",
        "Timeline:",
    ]
    for ev in outcome.events:
        parts = [f"dmg {format_number(ev.damage_dealt)}"]
        if ev.shield_absorbed > 0:
            parts.append(f"sh_abs {format_number(ev.shield_absorbed)}")
        if ev.healing_done > 0:
            parts.append(f"heal {format_number(ev.healing_done)}")
        if ev.shield_granted > 0:
            parts.append(f"sh +{format_number(ev.shield_granted)}")
        if ev.reactive_damage > 0:
            parts.append(f"reflect {format_number(ev.reactive_damage)}")
        lines.append(
            f"  #{ev.index:02d} t={format_number(ev.time)}s [{ev.actor}] {ev.action}: "
            f"{', '.join(parts)} -> A={format_number(ev.a_health_after)} HP, "
            f"B={format_number(ev.b_health_after)} HP [{ev.label.value}]"
        )
    if outcome.notes:
        lines.append("")
        lines.append("Notes:")
        for note in outcome.notes:
            lines.append(f"  - {note}")
    return "\n".join(lines)


def _fighter_to_dict(summary: FighterDuelSummary) -> dict[str, Any]:
    out: dict[str, Any] = {
        "side": summary.side,
        "champion_id": summary.champion_id,
        "champion_name": summary.champion_name,
        "level": summary.level,
        "start_health": float(summary.start_health),
        "max_health": float(summary.max_health),
        "remaining_health": float(summary.remaining_health),
        "remaining_health_pct": (
            float(summary.remaining_health * 100 / summary.max_health)
            if summary.max_health > 0
            else 0.0
        ),
        "remaining_shield": float(summary.remaining_shield),
        "damage_dealt": float(summary.damage_dealt),
        "damage_taken": float(summary.damage_taken),
        "healing_done": float(summary.healing_done),
        "shield_granted": float(summary.shield_granted),
        "shield_absorbed": float(summary.shield_absorbed),
        "actions_taken": summary.actions_taken,
        "survived": summary.survived,
    }
    if summary.resource is not None:
        out["resource"] = _resource_to_dict(summary.resource)
    return out


def _event_to_dict(ev: DuelEvent) -> dict[str, Any]:
    out: dict[str, Any] = {
        "index": ev.index,
        "time": float(ev.time),
        "actor": ev.actor,
        "action": ev.action,
        "damage_dealt": float(ev.damage_dealt),
        "shield_absorbed": float(ev.shield_absorbed),
        "health_damage": float(ev.health_damage),
        "healing_done": float(ev.healing_done),
        "shield_granted": float(ev.shield_granted),
        "reactive_damage": float(ev.reactive_damage),
        "a_health_after": float(ev.a_health_after),
        "a_shield_after": float(ev.a_shield_after),
        "b_health_after": float(ev.b_health_after),
        "b_shield_after": float(ev.b_shield_after),
        "label": ev.label.value,
    }
    if ev.notes:
        out["notes"] = list(ev.notes)
    return out


def to_dict(outcome: DuelOutcome) -> dict[str, Any]:
    """Serialize ``DuelOutcome`` for ``--json``, ``contract.py``, and ``mcp_server.py``."""
    return {
        "patch": outcome.patch,
        "mode": outcome.mode,
        "tie_break": outcome.tie_break,
        "max_duration": float(outcome.max_duration),
        "winner": outcome.winner,
        "duration": float(outcome.duration),
        "fighter_a": _fighter_to_dict(outcome.fighter_a),
        "fighter_b": _fighter_to_dict(outcome.fighter_b),
        "events": [_event_to_dict(ev) for ev in outcome.events],
        "label": outcome.label.value,
        "notes": list(outcome.notes),
    }
