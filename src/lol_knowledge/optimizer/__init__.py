"""Build optimizer: deterministic pruned search over legal builds (OPT-01..OPT-03)."""

from .models import (
    OBJECTIVES,
    BuildResult,
    CandidateItem,
    OptimizeConstraints,
    OptimizeOutcome,
    SearchStats,
)
from .report import format_text, to_dict
from .search import load_candidate_pool, optimize_build

__all__ = [
    "OBJECTIVES",
    "BuildResult",
    "CandidateItem",
    "OptimizeConstraints",
    "OptimizeOutcome",
    "SearchStats",
    "format_text",
    "load_candidate_pool",
    "optimize_build",
    "to_dict",
]
