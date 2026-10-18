import math
from collections.abc import Iterable, Sequence
from typing import Final

from rhizo.models import Basis

DECLARED_CONFIDENCE: Final = 0.95
OBSERVED_CONFIDENCE: Final = 0.90
SHARED_RESOURCE_CONFIDENCE: Final = 0.70
INCIDENT_CONFIDENCE: Final = 0.60
CODE_CONFIDENCE: Final = 0.85

CONFIRM_STEP: Final = 0.15
REFUTE_STEP: Final = 0.20
REFUTE_FLOOR: Final = 0.05

TIER_WEIGHT: Final = {1: 3, 2: 2, 3: 1}
DEFAULT_TIER: Final = 2

_PROVENANCE_RANK: Final[dict[str, int]] = {"declared": 0, "code": 1, "observed": 2, "inferred": 3}


def cochange_confidence(jaccard: float) -> float:
    return min(0.80, 0.40 + 0.50 * jaccard)


def path_confidence(confidences: Iterable[float]) -> float:
    return math.prod(confidences)


def worst_basis(bases: Sequence[Basis]) -> Basis:
    if "connectivity_fallback" in bases:
        return "connectivity_fallback"
    ranked = [b for b in bases if b in _PROVENANCE_RANK]
    if not ranked:
        return "n/a"
    return max(ranked, key=lambda b: _PROVENANCE_RANK[b])


def risk_score(victims: Iterable[tuple[int | None, float]]) -> int:
    s = sum(TIER_WEIGHT.get(tier or DEFAULT_TIER, TIER_WEIGHT[DEFAULT_TIER]) * conf for tier, conf in victims)
    return round(100 * (1 - math.exp(-s / 3)))


def suspect_score(hops: int, recent_commits: int, path_conf: float) -> float:
    return (1 / hops) * (1 + math.log1p(recent_commits)) * path_conf
