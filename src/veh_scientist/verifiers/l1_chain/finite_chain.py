"""
Finite diatomic chain: eigenfrequencies and TR identification.

Reference: Paper 1 Section 2.2, Eq. (5)-(7).
MATLAB reference: FindEigenFrequencies1.m, para_test.m

A finite chain of N unit cells with a non-periodic boundary mass
m_{a+} = delta * m_a at the left (free) end. Right end is fixed.

The chain layout (2N masses total):
    [m_{a+}] --k_a-- [m_b] --k_b-- [m_a] --k_a-- [m_b] --k_b-- ... --[m_b] (fixed)

Non-dimensional dynamic stiffness matrix A(Omega):
    det A(Omega) = 0  gives natural frequencies.
    If Omega_r is in the bandgap, it is a truncation resonance.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import brentq

from .dispersion import BandgapResult, compute_bandgap


@dataclass(frozen=True)
class FiniteChainResult:
    """Result of finite chain eigenfrequency analysis.

    All frequencies are non-dimensional Omega = omega / omega_b.
    """

    alpha: float
    beta: float
    delta: float
    n_cells: int
    eigenfrequencies: NDArray[np.floating]
    bandgap: BandgapResult
    tr_indices: list[int]  # indices into eigenfrequencies that are TRs
    tr_frequencies: NDArray[np.floating]
    passband_frequencies: NDArray[np.floating]


def build_dynamic_stiffness(
    alpha: float,
    beta: float,
    delta: float,
    n_cells: int,
    omega: float,
) -> NDArray[np.floating]:
    """Build the non-dimensional dynamic stiffness matrix A(Omega).

    Parameters
    ----------
    alpha : float
        Mass ratio m_b / m_a.
    beta : float
        Stiffness ratio k_b / k_a.
    delta : float
        Boundary asymmetry m_{a+} / m_a.
    n_cells : int
        Number of unit cells.
    omega : float
        Non-dimensional frequency Omega.

    Returns
    -------
    A : ndarray, shape (2*n_cells, 2*n_cells)
        Dynamic stiffness matrix.

    Notes
    -----
    Following MATLAB FindEigenFrequencies1.m / BuildCoefficientMatrix.
    The parameterization uses mu = sqrt(beta/alpha) internally:
        mu^2 * Omega^2 = (beta/alpha) * Omega^2

    The matrix rows correspond to equations of motion for each mass.
    Layout: masses are [m_{a+}, m_b, m_a, m_b, m_a, ..., m_b]
    Indices:           [1,      2,   3,   4,   5,  ..., 2N]

    Row i=1 (boundary m_{a+}):
        (1 + beta - delta * mu^2 * Omega^2) * U_1 - U_2 = 0

    Row i=2k (m_b, internal):
        -U_{2k-1} + (1 + beta - alpha * mu^2 * Omega^2) * U_{2k} - beta * U_{2k+1} = 0

    Row i=2k+1 (m_a, internal):
        -beta * U_{2k} + (1 + beta - mu^2 * Omega^2) * U_{2k+1} - U_{2k+2} = 0

    Row i=2N (last m_b, right boundary fixed):
        -U_{2N-1} + (1 + beta - alpha * mu^2 * Omega^2) * U_{2N} = 0
    """
    N = 2 * n_cells
    A = np.zeros((N, N))
    mu_sq = beta / alpha  # mu^2 = k_b * m_a / (k_a * m_b) = beta / alpha

    # Row 1: boundary mass m_{a+}
    A[0, 0] = 1.0 + beta - delta * mu_sq * omega**2
    A[0, 1] = -1.0

    # Internal rows
    for i in range(1, n_cells):
        # Row 2i (m_b): index = 2*i - 1 in 0-based
        r1 = 2 * i - 1
        A[r1, r1 - 1] = -1.0
        A[r1, r1] = 1.0 + beta - alpha * mu_sq * omega**2
        if r1 + 1 < N:
            A[r1, r1 + 1] = -beta

        # Row 2i+1 (m_a): index = 2*i in 0-based
        r2 = 2 * i
        A[r2, r2 - 1] = -beta
        A[r2, r2] = 1.0 + beta - mu_sq * omega**2
        if r2 + 1 < N:
            A[r2, r2 + 1] = -1.0

    # Row 2N (last m_b, right boundary fixed)
    A[N - 1, N - 2] = -1.0
    A[N - 1, N - 1] = 1.0 + beta - alpha * mu_sq * omega**2

    return A


def find_eigenfrequencies(
    alpha: float,
    beta: float,
    delta: float,
    n_cells: int,
    omega_max: float = 5 * np.pi,
    n_scan: int = 20000,
) -> NDArray[np.floating]:
    """Find all eigenfrequencies of the finite chain via det(A(Omega))=0.

    Uses sign-change detection on a coarse grid, then Brent refinement.

    Parameters
    ----------
    alpha, beta, delta, n_cells : float/int
        Chain parameters.
    omega_max : float
        Upper bound for frequency scan.
    n_scan : int
        Number of coarse scan points.

    Returns
    -------
    freqs : ndarray
        Sorted non-dimensional eigenfrequencies.
    """
    omega_scan = np.linspace(1e-6, omega_max, n_scan)
    det_vals = np.array([
        np.linalg.det(build_dynamic_stiffness(alpha, beta, delta, n_cells, w))
        for w in omega_scan
    ])

    # Find sign changes
    sign_changes = np.where(np.diff(np.sign(det_vals)) != 0)[0]

    freqs = []
    for idx in sign_changes:
        w_left = omega_scan[idx]
        w_right = omega_scan[idx + 1]
        try:
            root = brentq(
                lambda w: np.linalg.det(
                    build_dynamic_stiffness(alpha, beta, delta, n_cells, w)
                ),
                w_left,
                w_right,
                xtol=1e-12,
            )
            # Avoid duplicates
            if not freqs or abs(root - freqs[-1]) > 1e-8:
                freqs.append(root)
        except ValueError:
            pass

    return np.array(sorted(freqs))


def classify_frequencies(
    eigenfrequencies: NDArray[np.floating],
    bandgap: BandgapResult,
) -> tuple[list[int], NDArray[np.floating], NDArray[np.floating]]:
    """Classify eigenfrequencies as TR or passband.

    Parameters
    ----------
    eigenfrequencies : ndarray
        Sorted eigenfrequencies.
    bandgap : BandgapResult
        Bandgap boundaries.

    Returns
    -------
    tr_indices : list[int]
        Indices of TR frequencies.
    tr_freqs : ndarray
        TR frequencies.
    pb_freqs : ndarray
        Passband frequencies.
    """
    tr_indices = []
    tr_freqs = []
    pb_freqs = []

    # Use a small margin (1% of bandgap width) to avoid classifying
    # frequencies right at the bandgap edge as TR
    margin = 0.01 * bandgap.width if bandgap.exists else 0.0
    gap_lo = bandgap.lower + margin if bandgap.exists else 0.0
    gap_hi = bandgap.upper - margin if bandgap.exists else 0.0

    for i, freq in enumerate(eigenfrequencies):
        if bandgap.exists and gap_lo < freq < gap_hi:
            tr_indices.append(i)
            tr_freqs.append(freq)
        else:
            pb_freqs.append(freq)

    return tr_indices, np.array(tr_freqs), np.array(pb_freqs)


def analyze_finite_chain(
    alpha: float,
    beta: float,
    delta: float,
    n_cells: int,
) -> FiniteChainResult:
    """Complete analysis: eigenfrequencies + bandgap + TR classification.

    Parameters
    ----------
    alpha, beta, delta : float
        Non-dimensional chain parameters.
    n_cells : int
        Number of unit cells.

    Returns
    -------
    FiniteChainResult
    """
    bandgap = compute_bandgap(alpha, beta)
    eigenfreqs = find_eigenfrequencies(alpha, beta, delta, n_cells)
    tr_indices, tr_freqs, pb_freqs = classify_frequencies(eigenfreqs, bandgap)

    return FiniteChainResult(
        alpha=alpha,
        beta=beta,
        delta=delta,
        n_cells=n_cells,
        eigenfrequencies=eigenfreqs,
        bandgap=bandgap,
        tr_indices=tr_indices,
        tr_frequencies=tr_freqs,
        passband_frequencies=pb_freqs,
    )
