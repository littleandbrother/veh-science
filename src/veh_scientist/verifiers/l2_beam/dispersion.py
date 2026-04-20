"""
Step 1b: Bloch dispersion and bandgap identification for periodic Timoshenko beam.

Reference: Paper 1 Section 4, new_bc.m Part 5.

Unit cell: Layer A (length L_A) + Layer B (length L_B).
Cell transfer matrix: T_cell(omega) = T_B(L_B, omega) * T_A(L_A, omega).
Bloch criterion: eigenvalues of T_cell on the unit circle → passband.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from .tmm import MaterialProperties, BeamGeometry, timo_layer_transfer_matrix


@dataclass(frozen=True)
class BeamBandgapResult:
    """Result of bandgap calculation for a periodic beam.

    All frequencies in Hz.
    """

    gaps: list[tuple[float, float]]  # list of (f_lower, f_upper) in Hz
    f_grid: NDArray[np.floating]     # frequency grid used
    is_passband: NDArray[np.bool_]   # True if passband at each grid point


def compute_beam_dispersion(
    mat_A: MaterialProperties,
    mat_B: MaterialProperties,
    geom: BeamGeometry,
    L_A: float,
    L_B: float,
    f_array: NDArray[np.floating],
) -> NDArray[np.bool_]:
    """Compute passband/bandgap classification at each frequency.

    For each frequency, compute the unit cell transfer matrix and check
    if any eigenvalue lies on the unit circle (|mu| ≈ 1 → passband).

    Parameters
    ----------
    mat_A, mat_B : MaterialProperties
        Materials for layers A and B.
    geom : BeamGeometry
        Beam cross-section geometry.
    L_A, L_B : float
        Lengths of layers A and B [m].
    f_array : ndarray
        Frequency array [Hz].

    Returns
    -------
    is_passband : ndarray of bool
        True where the frequency is in a passband.
    """
    is_passband = np.zeros(len(f_array), dtype=bool)

    for i, f in enumerate(f_array):
        omega = 2 * np.pi * f
        if omega < 1e-10:
            is_passband[i] = True  # DC is always passband
            continue

        TA = timo_layer_transfer_matrix(mat_A, geom, L_A, omega)
        TB = timo_layer_transfer_matrix(mat_B, geom, L_B, omega)
        T_cell = TB @ TA  # MATLAB: Tcell = TB * TA

        eigenvalues = np.linalg.eigvals(T_cell)

        # Passband if any eigenvalue has |mu| ≈ 1
        is_passband[i] = np.any(np.abs(np.abs(eigenvalues) - 1.0) < 1e-3)

    return is_passband


def compute_beam_bandgaps(
    mat_A: MaterialProperties,
    mat_B: MaterialProperties,
    geom: BeamGeometry,
    L_A: float,
    L_B: float,
    f_min: float = 0.0,
    f_max: float = 10000.0,
    n_points: int = 600,
) -> BeamBandgapResult:
    """Compute bandgaps for a periodic Timoshenko beam.

    Parameters
    ----------
    mat_A, mat_B : MaterialProperties
        Materials for layers A and B.
    geom : BeamGeometry
        Beam cross-section geometry.
    L_A, L_B : float
        Lengths of layers A and B [m].
    f_min, f_max : float
        Frequency range [Hz].
    n_points : int
        Number of frequency points.

    Returns
    -------
    BeamBandgapResult
    """
    f_grid = np.linspace(f_min, f_max, n_points)
    is_passband = compute_beam_dispersion(mat_A, mat_B, geom, L_A, L_B, f_grid)

    # Extract bandgap intervals from boolean mask
    is_gap = ~is_passband
    gaps = _boolean_to_intervals(is_gap, f_grid)

    return BeamBandgapResult(gaps=gaps, f_grid=f_grid, is_passband=is_passband)


def _boolean_to_intervals(
    mask: NDArray[np.bool_],
    f_grid: NDArray[np.floating],
) -> list[tuple[float, float]]:
    """Convert a boolean mask to a list of (start, end) intervals.

    Follows MATLAB boolean_to_intervals exactly.
    """
    # Pad with False at both ends to detect transitions
    padded = np.concatenate(([False], mask, [False]))
    diff = np.diff(padded.astype(int))

    starts = np.where(diff == 1)[0]
    ends = np.where(diff == -1)[0] - 1

    intervals = []
    for s, e in zip(starts, ends):
        intervals.append((float(f_grid[s]), float(f_grid[e])))

    return intervals
