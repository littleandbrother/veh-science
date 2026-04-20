from __future__ import annotations

import numpy as np

from veh_scientist.discover.l1_chain import ChainReplayParams, bandgap, identify_tr_modes, response_spectrum


def test_l1_chain_replay_detects_localized_in_gap_tr_mode() -> None:
    params = ChainReplayParams()
    gap_low, gap_high = bandgap(params.alpha, params.beta)
    tr_modes = identify_tr_modes(params)
    assert tr_modes, "Expected at least one truncation-resonance mode inside the bandgap."
    tr = tr_modes[0]
    assert gap_low < tr["omega"] < gap_high
    assert tr["eta"] > 0.8

    spectrum = response_spectrum(params, np.linspace(max(0.05, 0.4 * gap_low), min(3.4, 1.4 * gap_high), 300), with_piezo=True)
    peak_idx = int(np.argmax(spectrum["power_norm"]))
    assert spectrum["transmission_db"][peak_idx] < 0.0
    assert spectrum["voltage_mag"][peak_idx] > 0.0
