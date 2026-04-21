from __future__ import annotations

from pathlib import Path

from veh_scientist.discover.solver_library import build_solver_library
from veh_scientist.interfaces import GapCandidate
from veh_scientist.taskcard import parse_discover_task_card


def test_build_solver_library_emits_codegen_bundle(tmp_path: Path) -> None:
    task = parse_discover_task_card("configs/tasks/tr_discover_replay.yaml")
    ranked_gaps = [
        GapCandidate(
            band_index=1,
            omega_min=1.5,
            omega_max=2.0,
            tr_frequencies=(1.8,),
            raw_frequency_hz=3200.0,
            anchored_frequency_hz=3272.0,
            calibrated_frequency_hz=3272.0,
            raw_stopband_hz=(2600.0, 4300.0),
            calibrated_stopband_hz=(2600.0, 4300.0),
            uncertainty_sigma_hz=120.0,
            confidence_interval_hz=(3150.0, 3390.0),
            uncertainty_score=0.82,
            calibration_confidence=0.88,
            matched_anchor_label="TR1",
            suppression_margin=0.9,
            localization_score=0.85,
            harvestability_score=0.8,
            robustness_score=0.7,
            realizability_score=0.7,
            target_band_score=1.0,
            anchor_score=1.0,
            l3_alignment_score=1.0,
            overall_score=0.9,
        )
    ]
    library = build_solver_library(tmp_path, task, ranked_gaps, l1_summary=None, l2_summary=None)
    assert len(library["entries"]) >= 5
    assert len(library["comparison"]) >= 5
    assert Path(library["codegen_bundle"]).exists()
    assert (tmp_path / "mechanism_solver_library.json").exists()
