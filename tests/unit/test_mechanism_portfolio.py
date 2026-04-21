from __future__ import annotations

from pathlib import Path

from veh_scientist.discover.gap_designer import rank_gap_candidates
from veh_scientist.discover.mechanisms import build_mechanism_portfolio
from veh_scientist.interfaces import GapCandidate
from veh_scientist.taskcard import parse_discover_task_card


def test_mechanism_portfolio_prioritizes_current_focus(tmp_path: Path) -> None:
    task = parse_discover_task_card("configs/tasks/tr_discover_replay.yaml")
    ranked = rank_gap_candidates(
        [
            GapCandidate(
                band_index=1,
                omega_min=1.0,
                omega_max=1.5,
                tr_frequencies=(1.2,),
                raw_frequency_hz=3200.0,
                anchored_frequency_hz=3272.0,
                calibrated_frequency_hz=3272.0,
                calibration_confidence=0.9,
                matched_anchor_label="TR1",
                suppression_margin=0.9,
                localization_score=0.95,
                harvestability_score=0.85,
                robustness_score=0.7,
                realizability_score=0.8,
                target_band_score=1.0,
                anchor_score=1.0,
                l3_alignment_score=0.9,
            )
        ]
    )
    portfolio = build_mechanism_portfolio(tmp_path, task, ranked, calibration_summary={"confidence": 0.9})
    assert portfolio["recommended_path"]["primary"] == "truncation_resonance"
    assert (tmp_path / "mechanism_portfolio.json").exists()
    assert (tmp_path / "mechanism_combo_roadmap.md").exists()
