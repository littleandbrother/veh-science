from __future__ import annotations

from pathlib import Path

from veh_scientist.discover.negative_memory import build_negative_result_memory
from veh_scientist.interfaces import GapCandidate


def test_negative_result_memory_collects_failure_modes(tmp_path: Path) -> None:
    chain_atlas = {
        "delta_scan": [
            {"delta": 0.95, "tr_count": 0, "peak_voltage": 0.1},
            {"delta": 0.25, "tr_count": 1, "peak_voltage": 1.0},
        ],
        "matching_map": {
            "peak_power_map": [
                [0.1, 0.2],
                [0.15, 1.2],
            ]
        },
    }
    gaps = [
        GapCandidate(
            band_index=2,
            omega_min=2.0,
            omega_max=2.5,
            tr_frequencies=(2.2,),
            raw_frequency_hz=50000.0,
            calibrated_frequency_hz=8259.0,
            uncertainty_sigma_hz=2000.0,
            uncertainty_score=0.2,
            extrapolation_penalty=0.6,
            suppression_margin=0.1,
            localization_score=0.3,
            harvestability_score=0.2,
            overall_score=0.1,
        )
    ]
    calibration_summary = {
        "source": "paper-anchor-fallback",
        "normalized_tool_results": [],
        "frequency_pairs": [
            {"label": "TR2", "band_index": 2, "raw_frequency_hz": 50000.0, "l3_frequency_hz": 8259.0},
        ],
    }
    derivation_checks = {
        "cards": [
            {"derivation_id": "D1", "title": "dispersion", "checks": [{"name": "limit", "passed": False}]}
        ]
    }
    solver_library = {
        "comparison": [
            {"mechanism_key": "nonlinear_route", "review_pass": False, "target_band_score": 0.1}
        ]
    }
    memory = build_negative_result_memory(
        tmp_path,
        chain_atlas=chain_atlas,
        gap_candidates=gaps,
        calibration_summary=calibration_summary,
        derivation_checks=derivation_checks,
        solver_library=solver_library,
    )
    assert memory["summary"]["n_records"] >= 4
    assert (tmp_path / "negative_result_memory.json").exists()
    assert (tmp_path / "negative_result_memory.md").exists()
