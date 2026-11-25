"""Data structures for the build optimizer (OPT-01, OPT-02, OPT-03)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

from ..stats import ItemData, Label

OBJECTIVES = frozenset(
    {
        "rotation_damage",
        "dps",
        "effective_health_physical",
        "effective_health_magic",
        "effective_health_mixed",
        "time_to_die",
        "healing",
        "duel",
    }
)

ROTATION_OBJECTIVES = frozenset({"rotation_damage", "dps", "healing"})
EHP_OBJECTIVES = frozenset(
    {"effective_health_physical", "effective_health_magic", "effective_health_mixed"}
)
DEFENSE_OBJECTIVES = frozenset({"time_to_die"})
DUEL_OBJECTIVES = frozenset({"duel"})
TIERS = frozenset({"completed", "all"})


@dataclass(frozen=True)
class OptimizeConstraints:
    """User constraints on candidate builds (OPT-01)."""

    budget: int | None = None
    slots: int = 6
    required_items: tuple[str, ...] = ()
    forbidden_items: tuple[str, ...] = ()
    require_boots: bool = False
    tier: str = "completed"
    only_verified: bool = False
    top: int = 5
    beam_width: int = 12
    pool_limit: int = 16
    damage_mix_physical: Fraction = Fraction(1, 2)
    use_item_actives: bool = False


@dataclass(frozen=True)
class CandidateItem:
    """One purchasable item pre-indexed for fast legality and budget pruning."""

    item: ItemData
    gold: int
    is_boots: bool
    is_completed: bool
    verified_clean: bool
    has_spellblade: bool
    groups: tuple[str, ...]
    required_champion: str | None = None
    slot_pinned: bool = False


@dataclass(frozen=True)
class SearchStats:
    """Measured pruning and timing metrics of one optimizer run (OPT-02)."""

    candidate_pool_size: int
    verified_pool_size: int
    states_evaluated: int
    pruned_illegal: int
    pruned_budget: int
    pruned_beam: int
    elapsed_ms: float
    strategy: str


@dataclass(frozen=True)
class BuildResult:
    """One evaluated legal build, its exact score and weakest-input label (OPT-03)."""

    items: tuple[str, ...]
    item_names: tuple[str, ...]
    total_gold: int
    score: Fraction
    secondary_score: Fraction
    label: Label
    metrics: Mapping[str, Any] = field(default_factory=dict)
    notes: tuple[str, ...] = ()

    @property
    def verified(self) -> bool:
        return self.label is not Label.PENDING


@dataclass(frozen=True)
class OptimizeOutcome:
    """Complete deterministic output separating verified and pending builds (OPT-03)."""

    objective: str
    champion: str
    level: int
    patch: str
    constraints: OptimizeConstraints
    verified_builds: tuple[BuildResult, ...]
    pending_builds: tuple[BuildResult, ...]
    all_builds: tuple[BuildResult, ...]
    stats: SearchStats
    label: Label
    notes: tuple[str, ...] = ()
