from __future__ import annotations

import numpy as np

from veh_scientist.discover.l2_beam import BeamReplayParams, beam_gap_candidates, stopbands


def test_l2_beam_replay_returns_rankable_gap_candidates() -> None:
    params = BeamReplayParams()
    omega_grid = np.linspace(0.2, 40.0, 300)
    gaps = stopbands(params, omega_grid)
    assert gaps, "Expected at least one stopband in the L2 beam oracle."
    candidates = beam_gap_candidates(params, omega_grid)
    assert candidates, "Expected at least one candidate gap from the beam replay."
    first = candidates[0]
    assert first["omega_min"] < first["omega_tr"] < first["omega_max"]
    assert first["localization_score"] > 0.0
    assert first["power_proxy"] >= 0.0
