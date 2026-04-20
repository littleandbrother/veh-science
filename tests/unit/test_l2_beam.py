"""
Tests for L2 Timoshenko beam TMM model.

Uses parameters from MATLAB new_bc.m:
    Material A: Al (E=68.9 GPa, rho=2700, nu=0.33)
    Material B: Epoxy/ABS (E=2.4 GPa, rho=1040, nu=0.35)
    Beam: b=25mm, h=5mm, ks=5/6
    Unit cell: L_A=80mm, L_B=20mm, N=20
"""

import sys
import os

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from veh_scientist.verifiers.l2_beam import (
    timo_layer_transfer_matrix,
    MaterialProperties,
    BeamGeometry,
    compute_beam_bandgaps,
    beam_frequency_sweep,
    compute_beam_harvesting_metrics,
)
from veh_scientist.verifiers.l2_beam.baseline_comparison import compute_conventional_beam_power
from veh_scientist.verifiers.l2_beam.tmm import PiezoProperties

# ═══ Reference parameters from new_bc.m ════════════════════════════════
MAT_A = MaterialProperties(E=68.9e9, rho=2700, nu=0.33)
MAT_B = MaterialProperties(E=2.4e9, rho=1040, nu=0.35)
GEOM = BeamGeometry(b=0.025, h=0.005, ks=5.0/6.0)
L_A = 0.08
L_B = 0.02
N_CELLS = 20
PIEZO = PiezoProperties(h=0.0005, rho=7500, d31=-274e-12, E=62e9, eps33T=3400*8.854e-12)
R_LOAD = 1e6
U0 = 0.01


class TestTMM:
    """Step 1a: Transfer matrix for a single layer."""

    def test_transfer_matrix_shape(self):
        """Transfer matrix should be 4x4."""
        T = timo_layer_transfer_matrix(MAT_A, GEOM, L_A, 2*np.pi*1000)
        assert T.shape == (4, 4)

    def test_transfer_matrix_identity_at_zero_length(self):
        """T(0, omega) should be identity."""
        T = timo_layer_transfer_matrix(MAT_A, GEOM, 0.0, 2*np.pi*1000)
        np.testing.assert_allclose(T, np.eye(4), atol=1e-12)

    def test_transfer_matrix_determinant(self):
        """det(T) should be 1 for symplectic system (lossless)."""
        T = timo_layer_transfer_matrix(MAT_A, GEOM, L_A, 2*np.pi*1000)
        det = np.linalg.det(T)
        assert abs(det - 1.0) < 1e-8, f"det(T) = {det}, expected 1"

    def test_transfer_matrix_composition(self):
        """T(L1+L2) should equal T(L2) @ T(L1) for same material."""
        omega = 2 * np.pi * 500
        T_full = timo_layer_transfer_matrix(MAT_A, GEOM, L_A, omega)
        T_half1 = timo_layer_transfer_matrix(MAT_A, GEOM, L_A/2, omega)
        T_half2 = timo_layer_transfer_matrix(MAT_A, GEOM, L_A/2, omega)
        T_composed = T_half2 @ T_half1
        np.testing.assert_allclose(T_full, T_composed, rtol=1e-10)


class TestDispersion:
    """Step 1b: Bloch dispersion and bandgap calculation."""

    def test_bandgaps_exist(self):
        """Al/Epoxy beam should have bandgaps in 0-10kHz range."""
        bg = compute_beam_bandgaps(MAT_A, MAT_B, GEOM, L_A, L_B, 0, 10000, 300)
        assert len(bg.gaps) >= 1, "Should find at least one bandgap"

    def test_dc_is_passband(self):
        """DC (f=0) should always be in the passband."""
        bg = compute_beam_bandgaps(MAT_A, MAT_B, GEOM, L_A, L_B, 0, 5000, 200)
        assert bg.is_passband[0], "DC should be passband"

    def test_bandgap_lower_less_than_upper(self):
        """Each bandgap should have lower < upper."""
        bg = compute_beam_bandgaps(MAT_A, MAT_B, GEOM, L_A, L_B, 0, 10000, 300)
        for lo, hi in bg.gaps:
            assert lo < hi, f"Invalid bandgap: [{lo}, {hi}]"

    def test_first_bandgap_reasonable(self):
        """First bandgap should be roughly in expected range for these params."""
        bg = compute_beam_bandgaps(MAT_A, MAT_B, GEOM, L_A, L_B, 0, 10000, 600)
        if bg.gaps:
            f_lo = bg.gaps[0][0]
            f_hi = bg.gaps[0][1]
            assert 100 < f_lo < 5000, f"First gap lower = {f_lo} Hz, unexpected"
            assert 500 < f_hi < 8000, f"First gap upper = {f_hi} Hz, unexpected"


class TestBeamFEM:
    """Step 1c-1d: Finite beam FEM + piezo coupling."""

    def test_frequency_sweep_runs(self):
        """Frequency sweep should complete without errors."""
        resp = beam_frequency_sweep(
            MAT_A, MAT_B, GEOM, PIEZO, L_A, L_B, N_CELLS, R_LOAD,
            f_min=100, f_max=5000, n_points=50, u0=U0,
        )
        assert len(resp.voltage) == 50
        assert np.all(resp.voltage >= 0)
        assert np.all(resp.power >= 0)

    def test_voltage_nonzero(self):
        """Voltage should be nonzero at resonance frequencies."""
        resp = beam_frequency_sweep(
            MAT_A, MAT_B, GEOM, PIEZO, L_A, L_B, N_CELLS, R_LOAD,
            f_min=100, f_max=5000, n_points=100, u0=U0,
        )
        assert np.max(resp.voltage) > 0, "Should have nonzero voltage"

    def test_transmission_negative_in_bandgap(self):
        """Transmission should be negative (< 0 dB) inside bandgap."""
        bg = compute_beam_bandgaps(MAT_A, MAT_B, GEOM, L_A, L_B, 0, 10000, 300)
        if not bg.gaps:
            pytest.skip("No bandgaps found")

        f_lo, f_hi = bg.gaps[0]
        f_mid = (f_lo + f_hi) / 2

        resp = beam_frequency_sweep(
            MAT_A, MAT_B, GEOM, PIEZO, L_A, L_B, N_CELLS, R_LOAD,
            f_array=np.array([f_mid]),
        )
        assert resp.transmission_dB[0] < 0, \
            f"Transmission at {f_mid:.0f} Hz = {resp.transmission_dB[0]:.1f} dB, expected < 0"

    def test_harvesting_metrics(self):
        """Harvesting metrics should be populated."""
        metrics = compute_beam_harvesting_metrics(
            MAT_A, MAT_B, GEOM, PIEZO, L_A, L_B, N_CELLS, R_LOAD,
            f_max=5000, n_points_bandgap=200, n_points_sweep=100,
        )
        assert metrics.f_pb1 > 0, "Should find PB1 frequency"
        assert metrics.current_tr >= 0
        assert metrics.rectified_current_tr >= 0
        assert 0.0 <= metrics.eta_tr <= 1.0

    def test_target_band_prefers_matching_gap(self):
        """When multiple gaps exist, TR selection should prefer the task-relevant gap."""
        metrics = compute_beam_harvesting_metrics(
            MAT_A, MAT_B, GEOM, PIEZO, L_A, L_B, N_CELLS, R_LOAD,
            f_min=100, f_max=5000, n_points_bandgap=300, n_points_sweep=200,
            target_band=(100, 1200),
        )
        assert metrics.f_tr <= 1200

    def test_conventional_beam_respects_patch_length(self):
        """A shorter equal-volume patch should not outperform a full-length patch."""
        power_short_patch = compute_conventional_beam_power(
            MAT_A, GEOM, PIEZO, total_length=N_CELLS * (L_A + L_B), patch_length=L_A + L_B,
            R_load=R_LOAD, f_target=500.0,
        )
        power_full_patch = compute_conventional_beam_power(
            MAT_A, GEOM, PIEZO, total_length=N_CELLS * (L_A + L_B), patch_length=N_CELLS * (L_A + L_B),
            R_load=R_LOAD, f_target=500.0,
        )
        assert power_short_patch < power_full_patch


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
