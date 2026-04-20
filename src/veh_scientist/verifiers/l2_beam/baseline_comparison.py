"""
Phase 2: Dual baseline comparison system.

Baseline A: Same periodic structure, no TR (compare mechanism advantage)
  - For L1 chain: delta=1 (periodic boundary, no asymmetry)
  - For L2 beam: same structure but compare TR peak vs PB1 peak

Baseline B: Conventional uniform cantilever beam
  - Same total mass, total length, total piezo volume
  - Single material, single resonance
  - Uses Erturk-Inman single-mode analytical model

Equal-constraint rules: total_mass, total_length, piezo_volume, excitation,
load_topology, target_frequency_window must be identical.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from veh_scientist.verifiers.l2_beam import (
    MaterialProperties, BeamGeometry,
    beam_frequency_sweep,
    compute_beam_bandgaps,
)
from veh_scientist.verifiers.l2_beam.tmm import PiezoProperties


@dataclass(frozen=True)
class DualBaselineResult:
    """Result of the dual baseline comparison."""

    # Baseline A: mechanism baseline (same structure, TR vs PB1)
    f_tr: float
    f_pb1: float
    power_tr: float
    power_pb1: float
    voltage_tr: float
    voltage_pb1: float
    current_tr: float
    current_pb1: float
    rectified_current_tr: float
    rectified_current_pb1: float
    pef_mechanism: float  # power_tr / power_pb1
    cef_mechanism: float  # current_tr / current_pb1

    # Baseline B: engineering baseline (TR beam vs conventional cantilever)
    power_conventional: float
    voltage_conventional: float
    current_conventional: float
    rectified_current_conventional: float
    pef_engineering: float  # power_tr / power_conventional
    cef_engineering: float  # current_tr / current_conventional

    # Locked constraint verification
    total_mass_tr: float
    total_mass_conv: float
    total_length_tr: float
    total_length_conv: float
    piezo_volume_tr: float
    piezo_volume_conv: float

    @property
    def passes_both_baselines(self) -> bool:
        return self.pef_mechanism >= 1.0 and self.pef_engineering >= 1.0


def compute_conventional_beam_power(
    mat: MaterialProperties,
    geom: BeamGeometry,
    piezo: PiezoProperties,
    total_length: float,
    patch_length: float,
    R_load: float,
    f_target: float,
    excitation_type: str = "acceleration",
    excitation_amplitude: float = 9.81,
    zeta_m: float = 0.01,
) -> float:
    """Estimate power from a conventional uniform cantilever at its first resonance.

    Uses a simplified single-mode Erturk-Inman model:
        P = (R * theta_eff^2 * omega^2 * U0^2) /
            ((R*Cp*omega)^2 * (2*zeta_m*omega_n)^2 + (1 + R*Cp*omega*2*zeta_m*omega_n)^2)

    This is an approximation. For the exact model, see the Erturk-Inman
    piezoelectric cantilever skill.

    Parameters
    ----------
    mat : MaterialProperties
        Uniform beam material.
    geom : BeamGeometry
        Cross-section geometry.
    piezo : PiezoProperties
        Piezo patch covering the full beam.
    total_length : float
        Total beam length [m].
    patch_length : float
        Effective piezo patch length [m]. This is locked by equal piezo volume.
    R_load : float
        Load resistance [Ohm].
    f_target : float
        Target frequency [Hz] (should be near first resonance).
    excitation_type : str
        "displacement" or "acceleration".
    excitation_amplitude : float
        Excitation amplitude.
    zeta_m : float
        Modal damping ratio.

    Returns
    -------
    power : float
        Estimated power output [W].
    """
    omega = 2 * np.pi * f_target

    # First natural frequency of cantilever
    EI = mat.E * geom.I
    rho_A = mat.rho * geom.A
    omega_n = (1.8751)**2 * np.sqrt(EI / (rho_A * total_length**4))

    # Piezo coupling coefficient (simplified)
    z_p = geom.h / 2 + piezo.h / 2
    theta_eff = piezo.E * piezo.d31 * geom.b * z_p / max(patch_length, 1e-12)

    # Piezo capacitance
    Cp = piezo.eps33T * geom.b * patch_length / piezo.h

    # Excitation displacement at target frequency
    if excitation_type == "acceleration":
        U0 = excitation_amplitude / omega**2
    else:
        U0 = excitation_amplitude

    # Single-mode power at resonance (omega = omega_n for max power)
    # Use omega_n as the operating frequency for resonance
    w = omega_n
    denominator = (R_load * Cp * w * 2 * zeta_m * w)**2 + \
                  (1 + R_load * Cp * w * 2 * zeta_m * w)**2

    if denominator < 1e-30:
        return 0.0

    # Resonance amplitude (simplified)
    U_tip = U0 * w**2 / (2 * zeta_m * w**2)  # at resonance

    # Voltage
    V = R_load * theta_eff * 1j * w * U_tip / (1 + 1j * w * R_load * Cp)
    power = np.abs(V)**2 / R_load

    return float(power)


def compute_dual_baseline(
    mat_A: MaterialProperties,
    mat_B: MaterialProperties,
    geom: BeamGeometry,
    piezo: PiezoProperties,
    L_A: float,
    L_B: float,
    n_cells: int,
    R_load: float,
    boundary_mass_factor: float = 1.0,
    f_max: float = 5000.0,
    n_points: int = 200,
    target_band: tuple[float, float] | None = None,
    excitation_type: str = "acceleration",
    excitation_amplitude: float = 9.81,
) -> DualBaselineResult:
    """Compute both Baseline A and Baseline B comparisons.

    Parameters
    ----------
    mat_A, mat_B : MaterialProperties
        Periodic beam materials.
    geom : BeamGeometry
        Cross-section geometry.
    piezo : PiezoProperties
        Piezo properties.
    L_A, L_B : float
        Layer lengths.
    n_cells : int
        Number of unit cells.
    R_load : float
        Load resistance [Ohm].

    Returns
    -------
    DualBaselineResult
    """
    a = L_A + L_B
    total_length = n_cells * a

    # ── Baseline A: TR vs PB1 in same structure ──────────────────────────
    bg = compute_beam_bandgaps(mat_A, mat_B, geom, L_A, L_B, 1.0, f_max, 400)

    resp = beam_frequency_sweep(
        mat_A, mat_B, geom, piezo, L_A, L_B, n_cells, R_load,
        f_min=1.0, f_max=f_max, n_points=n_points,
        excitation_type=excitation_type,
        excitation_amplitude=excitation_amplitude,
        boundary_mass_factor=boundary_mass_factor,
    )

    # Same finite beam with periodic boundary mass factor restored: delta -> 1
    resp_baseline = beam_frequency_sweep(
        mat_A, mat_B, geom, piezo, L_A, L_B, n_cells, R_load,
        f_min=1.0, f_max=f_max, n_points=n_points,
        excitation_type=excitation_type,
        excitation_amplitude=excitation_amplitude,
        boundary_mass_factor=1.0,
    )

    # Find TR peak
    f_arr = resp.f
    selected_gaps = _select_relevant_gaps(bg.gaps, target_band)
    gap_mask = np.zeros(len(f_arr), dtype=bool)
    for g_lo, g_hi in selected_gaps:
        gap_mask |= (f_arr >= g_lo) & (f_arr <= g_hi)

    if np.any(gap_mask):
        i_tr = np.argmax(resp.power * gap_mask)
        f_tr = float(f_arr[i_tr])
        power_tr = float(resp.power[i_tr])
        voltage_tr = float(resp.voltage[i_tr])
    else:
        f_tr = power_tr = voltage_tr = 0.0

    # Find PB1 peak
    if selected_gaps:
        pb_mask = f_arr < selected_gaps[0][0]
    elif bg.gaps:
        pb_mask = f_arr < bg.gaps[0][0]
    else:
        pb_mask = np.ones(len(f_arr), dtype=bool)

    if np.any(pb_mask):
        i_pb1 = np.argmax(resp_baseline.power * pb_mask)
        f_pb1 = float(resp_baseline.f[i_pb1])
        power_pb1 = float(resp_baseline.power[i_pb1])
        voltage_pb1 = float(resp_baseline.voltage[i_pb1])
    else:
        f_pb1 = power_pb1 = voltage_pb1 = 0.0

    pef_mechanism = power_tr / power_pb1 if power_pb1 > 0 else 0.0
    current_tr = voltage_tr / R_load if R_load > 0 else 0.0
    current_pb1 = voltage_pb1 / R_load if R_load > 0 else 0.0
    rectified_current_tr = current_tr * (2.0 / np.pi)
    rectified_current_pb1 = current_pb1 * (2.0 / np.pi)
    cef_mechanism = current_tr / current_pb1 if current_pb1 > 0 else 0.0

    # ── Baseline B: conventional cantilever ──────────────────────────────
    # Use weighted average material for the uniform beam
    frac_A = L_A / a
    frac_B = L_B / a
    rho_avg = mat_A.rho * frac_A + mat_B.rho * frac_B
    E_avg = mat_A.E * frac_A + mat_B.E * frac_B  # Voigt average
    nu_avg = mat_A.nu * frac_A + mat_B.nu * frac_B
    mat_conv = MaterialProperties(E=E_avg, rho=rho_avg, nu=nu_avg)

    # Equal constraints
    total_mass_tr = (mat_A.rho * L_A + mat_B.rho * L_B) * geom.A * n_cells
    total_mass_conv = rho_avg * geom.A * total_length
    piezo_vol = geom.b * a * piezo.h  # piezo on first cell
    patch_length = piezo_vol / max(geom.b * piezo.h, 1e-12)

    power_conventional = compute_conventional_beam_power(
        mat_conv, geom, piezo, total_length, patch_length, R_load,
        f_target=f_tr if f_tr > 0 else 500.0,
        excitation_type=excitation_type,
        excitation_amplitude=excitation_amplitude,
    )

    pef_engineering = power_tr / power_conventional if power_conventional > 0 else 0.0
    voltage_conventional = np.sqrt(power_conventional * R_load) if power_conventional > 0 else 0.0
    current_conventional = voltage_conventional / R_load if R_load > 0 else 0.0
    rectified_current_conventional = current_conventional * (2.0 / np.pi)
    cef_engineering = current_tr / current_conventional if current_conventional > 0 else 0.0

    return DualBaselineResult(
        f_tr=f_tr,
        f_pb1=f_pb1,
        power_tr=power_tr,
        power_pb1=power_pb1,
        voltage_tr=voltage_tr,
        voltage_pb1=voltage_pb1,
        current_tr=current_tr,
        current_pb1=current_pb1,
        rectified_current_tr=rectified_current_tr,
        rectified_current_pb1=rectified_current_pb1,
        pef_mechanism=pef_mechanism,
        cef_mechanism=cef_mechanism,
        power_conventional=power_conventional,
        voltage_conventional=voltage_conventional,
        current_conventional=current_conventional,
        rectified_current_conventional=rectified_current_conventional,
        pef_engineering=pef_engineering,
        cef_engineering=cef_engineering,
        total_mass_tr=total_mass_tr,
        total_mass_conv=total_mass_conv,
        total_length_tr=total_length,
        total_length_conv=total_length,
        piezo_volume_tr=piezo_vol,
        piezo_volume_conv=piezo_vol,
    )


def _select_relevant_gaps(
    gaps: list[tuple[float, float]],
    target_band: tuple[float, float] | None,
) -> list[tuple[float, float]]:
    if not gaps:
        return []
    if target_band is None:
        return [gaps[0]]

    band_lo, band_hi = target_band
    overlaps = [
        (g_lo, g_hi)
        for g_lo, g_hi in gaps
        if not (g_hi < band_lo or g_lo > band_hi)
    ]
    if overlaps:
        overlaps.sort(key=lambda gap: gap[0])
        return [overlaps[0]]
    return [gaps[0]]
