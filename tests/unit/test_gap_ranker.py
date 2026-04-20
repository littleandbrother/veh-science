from __future__ import annotations

from veh_scientist.discover.gap_designer import build_gap_candidates, rank_gap_candidates
from veh_scientist.interfaces import GapCandidate
from veh_scientist.taskcard import parse_discover_task_card


def test_rank_gap_candidates_orders_by_weighted_score() -> None:
    candidates = [
        GapCandidate(band_index=1, omega_min=1.0, omega_max=1.5, suppression_margin=0.7, localization_score=0.6, harvestability_score=0.4, robustness_score=0.5, realizability_score=0.6, target_band_score=0.4, anchor_score=0.4, l3_alignment_score=0.4),
        GapCandidate(band_index=2, omega_min=1.6, omega_max=2.0, suppression_margin=0.9, localization_score=0.9, harvestability_score=0.8, robustness_score=0.7, realizability_score=0.8, target_band_score=0.8, anchor_score=0.8, l3_alignment_score=0.8),
        GapCandidate(band_index=3, omega_min=2.1, omega_max=2.6, suppression_margin=0.4, localization_score=0.3, harvestability_score=0.9, robustness_score=0.4, realizability_score=0.3, target_band_score=0.2, anchor_score=0.1, l3_alignment_score=0.1),
    ]
    ranked = rank_gap_candidates(candidates)
    assert [gap.band_index for gap in ranked] == [2, 1, 3]
    assert ranked[0].overall_score > ranked[1].overall_score > ranked[2].overall_score


def test_build_gap_candidates_retunes_to_l3_anchors() -> None:
    task = parse_discover_task_card("configs/tasks/tr_discover_replay.yaml")
    l2_summary = {
        "candidates": [
            {"band_index": 1, "omega_min": 8.0, "omega_max": 8.3, "omega_tr": 8.22, "frequency_hz": 16137.0, "gap_center_hz": 16000.0, "suppression_margin": 0.4, "localization_score": 0.8, "power_proxy": 1.0, "robustness_score": 0.5},
            {"band_index": 2, "omega_min": 18.0, "omega_max": 26.0, "omega_tr": 25.3, "frequency_hz": 49649.0, "gap_center_hz": 49000.0, "suppression_margin": 0.5, "localization_score": 0.7, "power_proxy": 0.8, "robustness_score": 0.6},
        ]
    }
    candidates = build_gap_candidates(None, l2_summary, band_of_interest=(3000.0, 9000.0), anchors=task.l3_anchors)
    assert candidates[0].matched_anchor_label == "TR1"
    assert candidates[1].matched_anchor_label == "TR2"
    assert abs(candidates[0].anchored_frequency_hz - 3272.0) < 5.0
    assert abs(candidates[1].anchored_frequency_hz - 8259.0) < 5.0
