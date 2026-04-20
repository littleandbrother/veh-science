"""
Dispersion relation for an infinite diatomic spring-mass chain.

Reference: Paper 1 Section 2.1, Eq. (1)-(4).

Unit cell: masses (m_a, m_b) connected by alternating springs (k_a, k_b),
lattice pitch a.

Non-dimensional parameters (Eq. 1):
    alpha = m_b / m_a          (mass ratio)
    beta  = k_b / k_a          (stiffness ratio)
    omega_b = sqrt(k_b / m_b)  (reference frequency)
    Omega = omega / omega_b     (non-dimensional frequency)

Dispersion relation (Eq. 4):
    Omega^4 - (1+alpha)(1 + 1/beta) Omega^2 + (4*alpha/beta) sin^2(qa/2) = 0

This is a quadratic in Omega^2 with two solutions giving the acoustic
and optical branches.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class BandgapResult:
    """Result of a bandgap calculation.

    Attributes
    ----------
    exists : bool
        Whether a bandgap exists between acoustic and optical branches.
    lower : float
        Lower edge of the bandgap (max of acoustic branch), in non-dimensional Omega.
    upper : float
        Upper edge of the bandgap (min of optical branch), in non-dimensional Omega.
    width : float
        Width of the bandgap (upper - lower). Zero if no gap.
    center : float
        Center frequency of the bandgap. NaN if no gap.
    """

    exists: bool
    lower: float
    upper: float
    width: float
    center: float


def dispersion_relation(
    alpha: float,
    beta: float,
    q: NDArray[np.floating],
) -> tuple[NDArray[np.floating], NDArray[np.floating]]:
    """Compute acoustic and optical branches of the dispersion relation.

    Parameters
    ----------
    alpha : float
        Mass ratio m_b / m_a.  Must be > 0.
    beta : float
        Stiffness ratio k_b / k_a.  Must be > 0.
    q : ndarray, shape (N,)
        Non-dimensional wavenumber q*a (range [0, pi] for first Brillouin zone).

    Returns
    -------
    omega_acoustic : ndarray, shape (N,)
        Acoustic branch Omega(q).
    omega_optical : ndarray, shape (N,)
        Optical branch Omega(q).

    Notes
    -----
    From Paper 1 Eq. (4):
        Omega^4 - (1+alpha)(1+1/beta) Omega^2 + (4*alpha/beta) sin^2(qa/2) = 0

    Solving as quadratic in Omega^2:
        a_coeff = 1
        b_coeff = -(1+alpha)(1+1/beta)
        c_coeff = (4*alpha/beta) sin^2(qa/2)

        Omega^2 = [-b ± sqrt(b^2 - 4c)] / 2

    Acoustic branch = lower root (minus sign).
    Optical branch = upper root (plus sign).
    """
    if alpha <= 0:
        raise ValueError(f"alpha must be > 0, got {alpha}")
    if beta <= 0:
        raise ValueError(f"beta must be > 0, got {beta}")

    q = np.asarray(q, dtype=np.float64)

    # Coefficients of quadratic in Omega^2
    b_neg = (1.0 + alpha) * (1.0 + 1.0 / beta)  # this is -b_coeff
    c_coeff = (4.0 * alpha / beta) * np.sin(q / 2.0) ** 2

    # Discriminant
    discriminant = b_neg**2 - 4.0 * c_coeff

    # Protect against tiny negative values from floating point
    discriminant = np.maximum(discriminant, 0.0)
    sqrt_disc = np.sqrt(discriminant)

    # Omega^2 solutions
    omega_sq_optical = (b_neg + sqrt_disc) / 2.0  # upper branch
    omega_sq_acoustic = (b_neg - sqrt_disc) / 2.0  # lower branch

    # Protect against tiny negatives
    omega_sq_optical = np.maximum(omega_sq_optical, 0.0)
    omega_sq_acoustic = np.maximum(omega_sq_acoustic, 0.0)

    omega_acoustic = np.sqrt(omega_sq_acoustic)
    omega_optical = np.sqrt(omega_sq_optical)

    return omega_acoustic, omega_optical


def compute_bandgap(alpha: float, beta: float) -> BandgapResult:
    """Compute the first bandgap boundaries analytically.

    The bandgap lies between max(acoustic branch) and min(optical branch).

    At q*a = pi (Brillouin zone boundary):
        acoustic branch reaches its maximum
        optical branch reaches its minimum

    Parameters
    ----------
    alpha : float
        Mass ratio m_b / m_a.
    beta : float
        Stiffness ratio k_b / k_a.

    Returns
    -------
    BandgapResult
        Bandgap boundaries and properties.

    Notes
    -----
    At q*a = pi, sin^2(qa/2) = 1, so:
        Omega^4 - (1+alpha)(1+1/beta) Omega^2 + 4*alpha/beta = 0

    The two roots give the bandgap edges directly.
    """
    if alpha <= 0:
        raise ValueError(f"alpha must be > 0, got {alpha}")
    if beta <= 0:
        raise ValueError(f"beta must be > 0, got {beta}")

    b_neg = (1.0 + alpha) * (1.0 + 1.0 / beta)
    c_val = 4.0 * alpha / beta

    discriminant = b_neg**2 - 4.0 * c_val

    if discriminant < 0:
        # No real solution — shouldn't happen for physical parameters
        return BandgapResult(
            exists=False, lower=0.0, upper=0.0, width=0.0, center=float("nan")
        )

    sqrt_disc = np.sqrt(discriminant)

    # At q*a = pi: bandgap lower = sqrt of acoustic root, upper = sqrt of optical root
    omega_sq_lower = (b_neg - sqrt_disc) / 2.0  # max of acoustic = gap lower edge
    omega_sq_upper = (b_neg + sqrt_disc) / 2.0  # min of optical = gap upper edge

    # But we need to compare at q=0 and q=pi for both branches.
    # At q=0: sin^2(0)=0, so Omega^2 = 0 (acoustic) and Omega^2 = (1+alpha)(1+1/beta) (optical)
    # At q=pi: sin^2(pi/2)=1, giving the two roots above.
    #
    # For the acoustic branch: max is at q=pi → sqrt(omega_sq_lower)
    # For the optical branch: min is at q=pi → sqrt(omega_sq_upper)
    #
    # BUT: the optical branch at q=pi could be LOWER than at q=0.
    # At q=0: optical = sqrt((1+alpha)(1+1/beta))
    # At q=pi: optical = sqrt(omega_sq_upper)
    #
    # Actually for the standard diatomic chain, the optical branch minimum
    # is always at the zone boundary q=pi. So:

    gap_lower = np.sqrt(max(omega_sq_lower, 0.0))
    gap_upper = np.sqrt(max(omega_sq_upper, 0.0))

    # The bandgap exists if gap_lower < gap_upper
    # (which is always true when discriminant > 0 and alpha != 1 or beta != 1)
    width = gap_upper - gap_lower
    exists = width > 1e-12

    return BandgapResult(
        exists=exists,
        lower=float(gap_lower),
        upper=float(gap_upper),
        width=float(width) if exists else 0.0,
        center=float((gap_lower + gap_upper) / 2.0) if exists else float("nan"),
    )


def dimensional_frequency(
    omega_nd: float | NDArray[np.floating],
    k_b: float,
    m_b: float,
) -> float | NDArray[np.floating]:
    """Convert non-dimensional Omega to dimensional omega (rad/s).

    Parameters
    ----------
    omega_nd : float or ndarray
        Non-dimensional frequency Omega.
    k_b : float
        Spring stiffness k_b (N/m).
    m_b : float
        Mass m_b (kg).

    Returns
    -------
    omega : float or ndarray
        Dimensional angular frequency (rad/s).
    """
    omega_b = np.sqrt(k_b / m_b)
    return omega_nd * omega_b
