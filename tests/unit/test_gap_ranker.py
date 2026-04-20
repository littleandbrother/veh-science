from __future__ import annotations

from veh_scientist.discover.gap_designer import rank_gap_candidates
from veh_scientist.interfaces import GapCandidate


def test_rank_gap_candidates_orders_by_weighted_score() -> None:
    candidates = [
        GapCandidate(band_index=1, omega_min=1.0, omega_max=1.5, suppression_margin=0.7, localization_score=0.6, harvestability_score=0.4, robustness_score=0.5, realizability_score=0.6),
        GapCandidate(band_index=2, omega_min=1.6, omega_max=2.0, suppression_margin=0.9, localization_score=0.9, harvestability_score=0.8, robustness_score=0.7, realizability_score=0.8),
        GapCandidate(band_index=3, omega_min=2.1, omega_max=2.6, suppression_margin=0.4, localization_score=0.3, harvestability_score=0.9, robustness_score=0.4, realizability_score=0.3),
    ]
    ranked = rank_gap_candidates(candidates)
    assert [gap.band_index for gap in ranked] == [2, 1, 3]
    assert ranked[0].overall_score > ranked[1].overall_score > ranked[2].overall_score
