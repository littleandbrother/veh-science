from __future__ import annotations

import numpy as np

from veh_scientist.discover.l3_comsol_driver import _build_stopband_pairs, _detect_stopband_intervals


def test_detect_stopband_intervals_finds_contiguous_suppressed_regions() -> None:
    freq = np.array([2600.0, 2800.0, 3000.0, 3200.0, 3400.0, 3600.0, 3800.0])
    transmission_db = np.array([-2.0, -8.0, -11.0, -12.0, -4.0, -9.0, -10.0])
    intervals = _detect_stopband_intervals(freq, transmission_db, threshold_db=-6.0)
    assert intervals == [[2800.0, 3200.0], [3600.0, 3800.0]]


def test_build_stopband_pairs_matches_anchor_to_detected_interval() -> None:
    data = {
        "anchor_targets": [
            {"label": "TR1", "band_index": 1, "frequency_hz": 3272.0},
            {"label": "TR2", "band_index": 2, "frequency_hz": 8259.0},
        ],
        "candidate_targets": [
            {"band_index": 1, "raw_stopband_hz": [16000.0, 17000.0]},
            {"band_index": 2, "raw_stopband_hz": [49000.0, 50000.0]},
        ],
    }
    alignments = [
        {"label": "TR1", "best_frequency_hz": 3300.0},
        {"label": "TR2", "best_frequency_hz": 8050.0},
    ]
    detected_stopbands = [[2600.0, 4300.0], [5600.0, 8600.0]]

    pairs = _build_stopband_pairs(data, alignments, detected_stopbands)

    assert pairs == [
        {
            "band_index": 1,
            "label": "TR1",
            "raw_stopband_hz": [16000.0, 17000.0],
            "l3_stopband_hz": [2600.0, 4300.0],
            "source": "comsol-mph",
        },
        {
            "band_index": 2,
            "label": "TR2",
            "raw_stopband_hz": [49000.0, 50000.0],
            "l3_stopband_hz": [5600.0, 8600.0],
            "source": "comsol-mph",
        },
    ]
