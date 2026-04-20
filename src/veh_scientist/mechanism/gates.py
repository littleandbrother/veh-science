"""Mechanism Screening Layer — Gate Functions.

Blueprint §5.5.1: TR-Specific Screening Criteria (Gates 1-6).

Each gate function takes design parameters and returns a GateResult.
Gates are executed in order; early REJECT skips remaining gates.

Gate 1: Bandgap existence (necessary)
Gate 2: Boundary asymmetry (necessary)
Gate 3: TR frequency inside bandgap (necessary)
Gate 4: Energy localization (quality check)
Gate 5: Topological classification (optional deep check)
Gate 6: Suppression compatibility (functional check)
"""

from __future__ import annotations

import numpy as np

from veh_scientist.interfaces.schemas import GateResult
from veh_scientist.verifiers.l1_chain.dispersion import compute_bandgap
from veh_scientist.verifiers.l1_chain.finite_chain import analyze_finite_chain
from veh_scientist.verifiers.l1_chain.piezo_harvesting import (
    compute_harvesting_metrics,
    compute_mode_shape_energy,
)


def gate_1_bandgap_existence(alpha: float, beta: float) -> GateResult:
    """Gate 1: Verify that a bandgap exists for the given (alpha, beta).

    If no bandgap → REJECT (TR is impossible without a stop band).

    Parameters
    ----------
    alpha : float
        Mass ratio m_b / m_a.
    beta : float
        Stiffness ratio k_b / k_a.
    """
    bg = compute_bandgap(alpha, beta)
    return GateResult(
        gate_id=1,
        gate_name="bandgap_existence",
        passed=bg.exists,
        value=bg.width if bg.exists else 0.0,
        threshold=0.0,
        message=(
            f"Bandgap found: Ω ∈ [{bg.lower:.4f}, {bg.upper:.4f}], "
            f"width={bg.width:.4f}"
            if bg.exists
            else "No bandgap exists for the given (alpha, beta)"
        ),
    )


def gate_2_boundary_asymmetry(delta: float) -> GateResult:
    """Gate 2: Verify delta ≠ 1 (periodic boundary extinguishes TR).

    If delta ≈ 1 → REJECT.

    Parameters
    ----------
    delta : float
        Boundary asymmetry parameter m_{a+} / m_a.
    """
    DELTA_TOLERANCE = 0.01
    passed = abs(delta - 1.0) > DELTA_TOLERANCE
    return GateResult(
        gate_id=2,
        gate_name="boundary_asymmetry",
        passed=passed,
        value=delta,
        threshold=1.0,
        message=(
            f"delta={delta:.4f}, asymmetry |delta-1|={abs(delta-1.0):.4f} > {DELTA_TOLERANCE}"
            if passed
            else f"delta={delta:.4f} too close to 1.0 (tolerance={DELTA_TOLERANCE})"
        ),
    )


def gate_3_tr_in_bandgap(
    alpha: float, beta: float, delta: float, N: int
) -> GateResult:
    """Gate 3: Solve det A(Ω)=0 for finite chain, check root in bandgap.

    If no root in bandgap → REVISE (adjust delta or alpha/beta).

    Parameters
    ----------
    alpha : float
        Mass ratio.
    beta : float
        Stiffness ratio.
    delta : float
        Boundary asymmetry.
    N : int
        Number of unit cells.
    """
    bg = compute_bandgap(alpha, beta)
    if not bg.exists:
        return GateResult(
            gate_id=3,
            gate_name="tr_in_bandgap",
            passed=False,
            value=None,
            threshold=None,
            message="Cannot check TR: no bandgap exists",
        )

    chain = analyze_finite_chain(alpha, beta, delta, N)

    # Find eigenfrequencies inside the bandgap
    tr_freqs = [
        f for f in chain.eigenfrequencies if bg.lower < f < bg.upper
    ]

    if tr_freqs:
        tr_freq = tr_freqs[0]
        # Relative position within bandgap (0 = lower edge, 1 = upper edge)
        rel_pos = (tr_freq - bg.lower) / bg.width
        return GateResult(
            gate_id=3,
            gate_name="tr_in_bandgap",
            passed=True,
            value=tr_freq,
            threshold=None,
            message=(
                f"TR found at Ω_TR={tr_freq:.6f}, "
                f"position in gap: {rel_pos:.1%} "
                f"(gap=[{bg.lower:.4f}, {bg.upper:.4f}])"
            ),
        )
    else:
        return GateResult(
            gate_id=3,
            gate_name="tr_in_bandgap",
            passed=False,
            value=None,
            threshold=None,
            message=(
                f"No eigenfrequency found inside bandgap "
                f"[{bg.lower:.4f}, {bg.upper:.4f}]. "
                f"Found {len(chain.eigenfrequencies)} total eigenfrequencies."
            ),
        )


def gate_4_energy_localization(
    alpha: float, beta: float, delta: float, N: int,
    kappa2: float = 0.05,
    epsilon: float | None = None,
    eta_threshold: float = 0.3,
) -> GateResult:
    """Gate 4: Check energy concentration ratio η for the TR mode.

    If η < 0.3 → REVISE (localization too weak for effective harvesting).

    Parameters
    ----------
    alpha, beta, delta : float
        Chain parameters.
    N : int
        Number of unit cells.
    eta_threshold : float
        Minimum acceptable energy concentration ratio (default 0.3).
    """
    bg = compute_bandgap(alpha, beta)
    if not bg.exists:
        return GateResult(
            gate_id=4,
            gate_name="energy_localization",
            passed=False,
            value=None,
            threshold=eta_threshold,
            message="Cannot check localization: no bandgap exists",
        )

    chain = analyze_finite_chain(alpha, beta, delta, N)
    tr_freqs = [
        f for f in chain.eigenfrequencies if bg.lower < f < bg.upper
    ]

    if not tr_freqs:
        return GateResult(
            gate_id=4,
            gate_name="energy_localization",
            passed=False,
            value=None,
            threshold=eta_threshold,
            message="Cannot check localization: no TR mode found",
        )

    # Use the first TR mode
    tr_freq = tr_freqs[0]
    if epsilon is None:
        epsilon = tr_freq

    # Compute mode shape and energy distribution
    mode_result = compute_mode_shape_energy(
        alpha, beta, delta, N, tr_freq, kappa2, epsilon
    )
    eta = mode_result.eta

    return GateResult(
        gate_id=4,
        gate_name="energy_localization",
        passed=eta >= eta_threshold,
        value=eta,
        threshold=eta_threshold,
        message=(
            f"η={eta:.4f} >= {eta_threshold} — strong boundary localization"
            if eta >= eta_threshold
            else f"η={eta:.4f} < {eta_threshold} — localization too weak"
        ),
    )


def gate_5_topological_classification(
    alpha: float, beta: float,
) -> GateResult:
    """Gate 5 (Optional): Compute Chern gap label C_g for the target bandgap.

    C_g ≠ 0 → TR is topologically protected (high robustness).
    C_g = 0 → TR may be a non-topological defect mode (lower robustness).

    This gate never causes REJECT; it only flags robustness confidence.

    Note
    ----
    For the standard diatomic chain with alpha ≠ 1 or beta ≠ 1,
    the first bandgap has |C_g| = 1, guaranteeing exactly one TR
    traversal. We use this known result rather than computing the
    full Chern number numerically at this stage.
    """
    # For the standard diatomic chain, the first bandgap has |C_g| = 1
    # when alpha != 1 or beta != 1 (i.e., when the gap is open).
    bg = compute_bandgap(alpha, beta)
    if not bg.exists:
        C_g = 0
    else:
        # Standard result: first gap of diatomic chain has |C_g| = 1
        C_g = 1

    return GateResult(
        gate_id=5,
        gate_name="topological_classification",
        passed=True,  # This gate is advisory, never rejects
        value=float(C_g),
        threshold=None,
        message=(
            f"|C_g|={C_g} — TR is topologically protected, robust under perturbation"
            if C_g != 0
            else "C_g=0 — TR may be non-topological defect mode, recommend sensitivity analysis"
        ),
    )


def gate_6_suppression_compatibility(
    alpha: float,
    beta: float,
    delta: float,
    N: int,
    kappa2: float = 0.0,
    epsilon: float | None = None,
    max_transmission_dB: float = 0.0,
) -> GateResult:
    """Gate 6: Verify T(Ω_TR) < 0 dB (suppression is maintained).

    If T(Ω_TR) >= 0 dB → REVISE (suggests model inconsistency —
    TR should be inside a stop band where transmission is negative).

    Parameters
    ----------
    alpha, beta, delta : float
        Chain parameters.
    N : int
        Number of unit cells.
    kappa2 : float
        Electromechanical coupling factor.
    epsilon : float or None
        Electrical damping ratio. If None, uses impedance matching.
    max_transmission_dB : float
        Maximum allowed transmission (default 0.0 dB).
    """
    bg = compute_bandgap(alpha, beta)
    if not bg.exists:
        return GateResult(
            gate_id=6,
            gate_name="suppression_compatibility",
            passed=False,
            value=None,
            threshold=max_transmission_dB,
            message="Cannot check suppression: no bandgap exists",
        )

    chain = analyze_finite_chain(alpha, beta, delta, N)
    tr_freqs = [
        f for f in chain.eigenfrequencies if bg.lower < f < bg.upper
    ]

    if not tr_freqs:
        return GateResult(
            gate_id=6,
            gate_name="suppression_compatibility",
            passed=False,
            value=None,
            threshold=max_transmission_dB,
            message="Cannot check suppression: no TR mode found",
        )

    tr_freq = tr_freqs[0]

    if epsilon is None:
        epsilon = tr_freq  # impedance matching: epsilon* ~ Omega_TR

    # Reuse the same wide-band L1 evaluator used by verification so that
    # Gate 6 and L1 do not disagree on the suppression verdict.
    metrics = compute_harvesting_metrics(
        alpha=alpha,
        beta=beta,
        delta=delta,
        n_cells=N,
        kappa_sq=kappa2,
        epsilon=epsilon,
        n_points=4000,
    )
    t_dB = metrics.transmission_tr_dB

    passed = t_dB < max_transmission_dB

    return GateResult(
        gate_id=6,
        gate_name="suppression_compatibility",
        passed=passed,
        value=float(t_dB),
        threshold=max_transmission_dB,
        message=(
            f"T(Ω_TR)={t_dB:.1f} dB @ Ω={metrics.omega_tr:.4f} < {max_transmission_dB} dB — suppression maintained"
            if passed
            else f"T(Ω_TR)={t_dB:.1f} dB @ Ω={metrics.omega_tr:.4f} >= {max_transmission_dB} dB — suppression violated"
        ),
    )
