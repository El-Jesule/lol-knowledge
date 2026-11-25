"""Build optimizer: deterministic pruned search over legal builds (OPT-01..OPT-03)."""

from .models import (
    OBJECTIVES,
    BuildResult,
    CandidateItem,
    GoldCheckpointResult,
    OptimizeConstraints,
    OptimizeOutcome,
    PurchaseStep,
    SearchStats,
)
from .report import format_text, to_dict
from .search import default_champion_rotation, load_candidate_pool, optimize_build

__all__ = [
    "OBJECTIVES",
    "BuildResult",
    "CandidateItem",
    "GoldCheckpointResult",
    "OptimizeConstraints",
    "OptimizeOutcome",
    "PurchaseStep",
    "SearchStats",
    "default_champion_rotation",
    "format_text",
    "load_candidate_pool",
    "optimize_build",
    "to_dict",
]
