"""Ranking helpers for choosing usable TR-enabled bandgaps."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from veh_scientist.interfaces import GapCandidate


@dataclass(frozen=True)
class GapRankingWeights:
    """Weights for multi-objective gap ranking."""

    suppression: float = 0.25
    localization: float = 0.25
    harvestability: float = 0.25
    robustness: float = 0.15
    realizability: float = 0.10


def score_gap_candidate(candidate: GapCandidate, weights: GapRankingWeights | None = None) -> float:
    """Score a gap candidate using a weighted sum of normalized criteria."""

    weights = weights or GapRankingWeights()
    score = (
        weights.suppression * candidate.suppression_margin
        + weights.localization * candidate.localization_score
        + weights.harvestability * candidate.harvestability_score
        + weights.robustness * candidate.robustness_score
        + weights.realizability * candidate.realizability_score
    )
    return round(float(score), 8)


def rank_gap_candidates(
    candidates: Iterable[GapCandidate],
    weights: GapRankingWeights | None = None,
) -> list[GapCandidate]:
    """Return gap candidates sorted by descending overall score."""

    weights = weights or GapRankingWeights()
    scored = [replace(candidate, overall_score=score_gap_candidate(candidate, weights)) for candidate in candidates]
    return sorted(scored, key=lambda cand: (-cand.overall_score, cand.band_index, cand.omega_min))
