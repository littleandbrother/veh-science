"""
Tests for L1 diatomic chain dispersion relation.

Verification strategy:
  1. Analytical edge cases (q=0, q=pi)
  2. Cross-check with MATLAB FindBandgaps.m parameterization
  3. Cross-check with Paper 1 Table 1 parameters
  4. Physical consistency checks
"""

from __future__ import annotations

import sys
import os

import numpy as np
import pytest

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from veh_scientist.verifiers.l1_chain.dispersion import (
    BandgapResult,
    compute_bandgap,
    dimensional_frequency,
    dispersion_relation,
)


# ---------------------------------------------------------------------------
# 1. Analytical edge cases
# ---------------------------------------------------------------------------

class TestDispersionAnalytical:
    """Test dispersion relation against known analytical values."""

    def test_acoustic_at_q_zero_is_zero(self):
        """At q=0, acoustic branch must be Omega=0."""
        alpha, beta = 0.75, 3.0
        q = np.array([0.0])
        acoustic, optical = dispersion_relation(alpha, beta, q)
        assert acoustic[0] == pytest.approx(0.0, abs=1e-14)

    def test_optical_at_q_zero(self):
        """At q=0, optical branch = sqrt((1+alpha)(1+1/beta))."""
        alpha, beta = 0.75, 3.0
        q = np.array([0.0])
        acoustic, optical = dispersion_relation(alpha, beta, q)
        expected = np.sqrt((1 + alpha) * (1 + 1.0 / beta))
        assert optical[0] == pytest.approx(expected, rel=1e-12)

    def test_branches_at_zone_boundary(self):
        """At q=pi, both branches are non-zero and distinct."""
        alpha, beta = 0.75, 3.0
        q = np.array([np.pi])
        acoustic, optical = dispersion_relation(alpha, beta, q)
        assert acoustic[0] > 0
        assert optical[0] > acoustic[0]

    def test_acoustic_monotonically_increases(self):
        """Acoustic branch should increase from q=0 to q=pi."""
        alpha, beta = 0.75, 3.0
        q = np.linspace(0, np.pi, 500)
        acoustic, _ = dispersion_relation(alpha, beta, q)
        # Allow tiny floating point non-monotonicity
        diffs = np.diff(acoustic)
        assert np.all(diffs >= -1e-14)

    def test_optical_monotonically_decreases(self):
        """Optical branch should decrease from q=0 to q=pi."""
        alpha, beta = 0.75, 3.0
        q = np.linspace(0, np.pi, 500)
        _, optical = dispersion_relation(alpha, beta, q)
        diffs = np.diff(optical)
        assert np.all(diffs <= 1e-14)

    def test_symmetric_mass_ratio_equal_to_1(self):
        """When alpha=1, beta=1, the gap should close (monatomic chain)."""
        result = compute_bandgap(1.0, 1.0)
        # For alpha=1, beta=1: b_neg = 2*2 = 4, c = 4*1/1 = 4
        # discriminant = 16 - 16 = 0 → gap width = 0
        assert result.width == pytest.approx(0.0, abs=1e-10)


# ---------------------------------------------------------------------------
# 2. Cross-check with MATLAB FindBandgaps.m
# ---------------------------------------------------------------------------

class TestCrossCheckMATLAB:
    """Cross-check against MATLAB FindBandgaps.m parameterization.

    MATLAB code uses a DIFFERENT parameterization than Paper 1.
    In para_test.m:
        alpha1 = 0.75  → m_b = m_avg * alpha1  → alpha (Paper 1) = m_b/m_a = 0.75
        alpha2 = 3     → k_b = k_a * alpha2    → beta (Paper 1)  = k_b/k_a = 3
        delta1 = 0.5   → m_{a+} = delta1*m_a   → delta (Paper 1) = 0.5

    In FindBandgaps.m, the parameterization uses (beta_matlab, mu, alpha_matlab)
    which maps differently. We bypass that and directly test the physical parameters.

    Physical parameters from para_test.m:
        m_a = 0.05 kg,  m_b = 0.0375 kg  (alpha = 0.75)
        k_a = 500 N/m,  k_b = 1500 N/m   (beta = 3.0)
    """

    def test_paper1_table1_parameters(self):
        """Test with Paper 1 Table 1 parameters.

        Table 1: m_a = 0.05 kg, k_a = 500 N/m
        With alpha=0.75, beta=3.0:
            m_b = 0.0375 kg, k_b = 1500 N/m
            omega_b = sqrt(1500/0.0375) = 200 rad/s

        Compute bandgap and verify it exists.
        """
        alpha = 0.75
        beta = 3.0
        gap = compute_bandgap(alpha, beta)
        assert gap.exists
        assert gap.lower > 0
        assert gap.upper > gap.lower
        assert gap.width > 0

    def test_para_test_bandgap_dimensional(self):
        """Verify dimensional bandgap frequencies match para_test.m.

        From para_test.m with alpha1=0.75, alpha2=3:
            m_a = 0.05, m_b = 0.0375, k_a = 500, k_b = 1500
            omega_b = sqrt(k_b/m_b) = sqrt(1500/0.0375) = 200 rad/s

        We compute non-dimensional bandgap, then convert to dimensional,
        and compare with MATLAB dispersion curve output.

        In MATLAB para_test.m line 180-181, the dimensional dispersion is computed
        directly. The bandgap_lower and bandgap_upper are in rad/s.
        """
        alpha = 0.75
        beta = 3.0
        k_a = 500.0  # N/m
        k_b = k_a * beta  # 1500 N/m
        m_a = 0.05  # kg
        m_b = m_a * alpha  # 0.0375 kg
        omega_b = np.sqrt(k_b / m_b)  # 200 rad/s

        gap = compute_bandgap(alpha, beta)

        # Convert to dimensional
        gap_lower_dim = gap.lower * omega_b  # rad/s
        gap_upper_dim = gap.upper * omega_b  # rad/s

        # MATLAB computes directly via:
        # Omega_acoustic = sqrt(...), Omega_optical = sqrt(...)
        # using dimensional masses and stiffnesses.
        # Let's verify by computing the MATLAB way:
        q_test = np.pi  # zone boundary
        sin2 = np.sin(q_test / 2) ** 2  # = 1

        # MATLAB formula (para_test.m line 180):
        # sqrt(((m_a+m_b)*(k_a+k_b) - sqrt(...))/2/m_a/m_b)
        inner = ((k_a + k_b) * (m_a + m_b)) ** 2 - 16 * k_a * k_b * m_a * m_b * sin2
        omega_ac_matlab = np.sqrt(
            ((m_a + m_b) * (k_a + k_b) - np.sqrt(inner)) / (2 * m_a * m_b)
        )
        omega_op_matlab = np.sqrt(
            ((m_a + m_b) * (k_a + k_b) + np.sqrt(inner)) / (2 * m_a * m_b)
        )

        assert gap_lower_dim == pytest.approx(omega_ac_matlab, rel=1e-10)
        assert gap_upper_dim == pytest.approx(omega_op_matlab, rel=1e-10)


# ---------------------------------------------------------------------------
# 3. Physical consistency
# ---------------------------------------------------------------------------

class TestPhysicalConsistency:
    """Physical consistency checks."""

    def test_wider_mass_contrast_gives_wider_gap(self):
        """Larger mass ratio contrast should give wider bandgap."""
        gap_small = compute_bandgap(alpha=0.9, beta=3.0)  # close to 1
        gap_large = compute_bandgap(alpha=0.3, beta=3.0)  # far from 1
        # Both should have gaps, larger contrast → wider gap
        assert gap_small.exists
        assert gap_large.exists
        assert gap_large.width > gap_small.width

    def test_bandgap_always_positive(self):
        """Bandgap boundaries should always be positive for valid parameters."""
        for alpha in [0.3, 0.5, 0.75, 1.5, 2.0, 3.0]:
            for beta in [0.3, 0.5, 1.0, 2.0, 3.0]:
                gap = compute_bandgap(alpha, beta)
                if gap.exists:
                    assert gap.lower > 0
                    assert gap.upper > gap.lower

    def test_invalid_parameters_raise(self):
        """Negative or zero parameters should raise ValueError."""
        with pytest.raises(ValueError):
            dispersion_relation(-1, 1, np.array([0.0]))
        with pytest.raises(ValueError):
            dispersion_relation(1, 0, np.array([0.0]))
        with pytest.raises(ValueError):
            compute_bandgap(0, 1)

    def test_dimensional_conversion_roundtrip(self):
        """dimensional_frequency should scale correctly."""
        k_b = 1500.0
        m_b = 0.0375
        omega_b = np.sqrt(k_b / m_b)
        omega_nd = 1.5  # non-dimensional
        omega_dim = dimensional_frequency(omega_nd, k_b, m_b)
        assert omega_dim == pytest.approx(omega_nd * omega_b, rel=1e-14)


# ---------------------------------------------------------------------------
# 4. Full dispersion curve shape
# ---------------------------------------------------------------------------

class TestFullDispersionCurve:
    """Test the full dispersion curve shape."""

    def test_no_crossing_between_branches(self):
        """Optical branch must be strictly above acoustic branch for all q > 0."""
        alpha, beta = 0.75, 3.0
        q = np.linspace(0.01, np.pi, 1000)
        acoustic, optical = dispersion_relation(alpha, beta, q)
        assert np.all(optical > acoustic)

    def test_bandgap_equals_branch_gap_at_zone_boundary(self):
        """Bandgap edges should match branch values at q=pi."""
        alpha, beta = 0.75, 3.0
        q = np.array([np.pi])
        acoustic, optical = dispersion_relation(alpha, beta, q)
        gap = compute_bandgap(alpha, beta)

        assert gap.lower == pytest.approx(acoustic[0], rel=1e-12)
        assert gap.upper == pytest.approx(optical[0], rel=1e-12)

    def test_dispersion_with_many_parameter_sets(self):
        """Smoke test: dispersion should not crash or produce NaN."""
        q = np.linspace(0, np.pi, 200)
        for alpha in [0.1, 0.5, 1.0, 2.0, 5.0]:
            for beta in [0.1, 0.5, 1.0, 2.0, 5.0]:
                acoustic, optical = dispersion_relation(alpha, beta, q)
                assert not np.any(np.isnan(acoustic))
                assert not np.any(np.isnan(optical))
                assert np.all(acoustic >= 0)
                assert np.all(optical >= 0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
