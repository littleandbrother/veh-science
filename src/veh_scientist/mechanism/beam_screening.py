"""Continuous-beam screening path for mechanism gating.

This module upgrades the project's default screening flow from the legacy
lumped chain proxy to the finite continuous beam model used by L2.
"""

from __future__ import annotations

import numpy as np

from veh_scientist.codesign import CandidateToBeamTranslator
from veh_scientist.interfaces.schemas import (
    CandidateDesignFamily,
    GateResult,
    MechanismScreenResult,
    TaskCard,
)
from veh_scientist.verifiers.l2_beam import (
    beam_frequency_sweep,
    compute_beam_bandgaps,
)
from veh_scientist.verifiers.l2_beam.beam_analysis import (
    _build_fem_system,
    _compute_localization_ratio,
    _solve_frequency_response,
)


def screen_candidate_with_beam(
    candidate: CandidateDesignFamily,
    task: TaskCard,
    *,
    eta_threshold: float,
    max_transmission_dB: float,
    allow_tr_frequency_exception: bool = False,
) -> MechanismScreenResult:
    """Run the screening gates directly on the continuous beam model."""
    translator = CandidateToBeamTranslator(task)
    design = translator.translate(candidate)
    excitation_type, excitation_amplitude = _task_excitation_to_beam(task)
    target_band = task.frequency_target.band_of_interest
    f_min = max(1.0, target_band[0] * 0.2)
    f_max = max(target_band[1] * 2.0, 3000.0)
    screening_load = _screening_load(task, design.R_load)

    bg = compute_beam_bandgaps(
        design.mat_A,
        design.mat_B,
        design.geom,
        design.L_A,
        design.L_B,
        f_min,
        f_max,
        96,
    )

    g1 = GateResult(
        gate_id=1,
        gate_name="bandgap_existence",
        passed=bool(bg.gaps),
        value=float(bg.gaps[0][1] - bg.gaps[0][0]) if bg.gaps else 0.0,
        threshold=0.0,
        message=(
            f"L2 beam bandgap found in [{bg.gaps[0][0]:.1f}, {bg.gaps[0][1]:.1f}] Hz."
            if bg.gaps
            else "No L2 beam bandgap found in the task frequency envelope."
        ),
    )
    if not g1.passed:
        return MechanismScreenResult(
            candidate_id=candidate.candidate_id,
            verdict="reject",
            gates=[g1],
            revision_hints=[
                "Retune the beam contrast or cell pitch so the continuous beam opens a bandgap in the target band.",
            ],
        )

    g2 = GateResult(
        gate_id=2,
        gate_name="boundary_asymmetry",
        passed=abs(design.boundary_mass_factor - 1.0) > 0.01,
        value=float(design.boundary_mass_factor),
        threshold=1.0,
        message=(
            f"boundary_mass_factor={design.boundary_mass_factor:.3f} provides finite-boundary asymmetry."
            if abs(design.boundary_mass_factor - 1.0) > 0.01
            else "boundary_mass_factor is too close to 1.0; the finite beam is effectively periodic."
        ),
    )
    if not g2.passed:
        return MechanismScreenResult(
            candidate_id=candidate.candidate_id,
            verdict="reject",
            gates=[g1, g2],
            revision_hints=[
                "Increase the finite-boundary asymmetry so the continuous beam can support a truncation mode.",
            ],
        )

    active_gap = _select_relevant_gap(bg.gaps, target_band)
    f_tr, power_tr, transmission_tr_dB, eta_tr = _coarse_tr_metrics(
        mat_A=design.mat_A,
        mat_B=design.mat_B,
        geom=design.geom,
        piezo=design.piezo,
        L_A=design.L_A,
        L_B=design.L_B,
        n_cells=design.n_cells,
        R_load=screening_load,
        active_gap=active_gap,
        excitation_type=excitation_type,
        excitation_amplitude=excitation_amplitude,
        boundary_mass_factor=design.boundary_mass_factor,
    )

    tr_in_gap = (
        active_gap is not None
        and f_tr > 0
        and active_gap[0] <= f_tr <= active_gap[1]
        and power_tr > 0
    )
    g3 = GateResult(
        gate_id=3,
        gate_name="tr_in_bandgap",
        passed=tr_in_gap,
        value=float(f_tr) if f_tr > 0 else None,
        threshold=None,
        message=(
            f"L2 beam TR found at {f_tr:.1f} Hz inside [{active_gap[0]:.1f}, {active_gap[1]:.1f}] Hz."
            if tr_in_gap and active_gap is not None
            else "No usable beam TR peak was found inside the selected bandgap."
        ),
    )

    revision_hints: list[str] = []
    if not g3.passed:
        revision_hints.append(
            "Move the beam truncation resonance back into the selected bandgap by retuning contrast, cell count, or boundary asymmetry.",
        )
        return MechanismScreenResult(
            candidate_id=candidate.candidate_id,
            verdict="revise",
            gates=[g1, g2, g3],
            tr_frequency=float(f_tr) if f_tr > 0 else None,
            eta=float(eta_tr),
            revision_hints=revision_hints,
        )

    g4 = GateResult(
        gate_id=4,
        gate_name="energy_localization",
        passed=eta_tr >= eta_threshold,
        value=float(eta_tr),
        threshold=eta_threshold,
        message=(
            f"L2 beam localization eta={eta_tr:.3f}."
            if eta_tr >= eta_threshold
            else f"L2 beam localization eta={eta_tr:.3f} is below the {eta_threshold:.3f} threshold."
        ),
    )
    if not g4.passed:
        revision_hints.append(
            "Increase beam localization in the first cell by strengthening truncation asymmetry or increasing cell count.",
        )

    g5 = GateResult(
        gate_id=5,
        gate_name="topological_classification",
        passed=True,
        value=1.0,
        threshold=None,
        message=(
            "Continuum screening uses finite-beam localization plus bandgap overlap as the robustness proxy; explicit topological invariant calculation is not implemented."
        ),
    )

    g6 = GateResult(
        gate_id=6,
        gate_name="suppression_compatibility",
        passed=transmission_tr_dB <= max_transmission_dB or allow_tr_frequency_exception,
        value=float(transmission_tr_dB),
        threshold=max_transmission_dB,
        message=(
            f"L2 beam transmission at TR is {transmission_tr_dB:.2f} dB."
            if transmission_tr_dB <= max_transmission_dB
            else (
                f"L2 beam transmission at TR is {transmission_tr_dB:.2f} dB, but task card enables tr_frequency_exception so Gate 6 is advisory."
                if allow_tr_frequency_exception
                else f"L2 beam transmission at TR is {transmission_tr_dB:.2f} dB, above the {max_transmission_dB:.2f} dB limit."
            )
        ),
    )
    if not g6.passed:
        revision_hints.append(
            "Lower the beam transmission at TR, or shift the TR peak deeper into the bandgap.",
        )

    verdict = "pass" if g4.passed and g6.passed else "revise"
    return MechanismScreenResult(
        candidate_id=candidate.candidate_id,
        verdict=verdict,
        gates=[g1, g2, g3, g4, g5, g6],
        tr_frequency=float(f_tr),
        eta=float(eta_tr),
        revision_hints=revision_hints,
    )


def _task_excitation_to_beam(task: TaskCard) -> tuple[str, float]:
    exc = task.excitation
    if exc.type == "base_acceleration":
        amplitude = exc.amplitude
        if exc.amplitude_unit.lower() == "g":
            amplitude *= 9.81
        return "acceleration", amplitude

    amplitude = exc.amplitude
    if exc.amplitude_unit.lower() == "mm":
        amplitude /= 1000.0
    return "displacement", amplitude


def _screening_load(task: TaskCard, fallback_load: float) -> float:
    if task.harvesting_requirements.load_value is not None:
        return float(task.harvesting_requirements.load_value)
    return float(fallback_load)


def _select_relevant_gap(
    gaps: list[tuple[float, float]],
    target_band: tuple[float, float],
) -> tuple[float, float] | None:
    overlaps = [
        gap
        for gap in gaps
        if not (gap[1] < target_band[0] or gap[0] > target_band[1])
    ]
    if overlaps:
        overlaps.sort(key=lambda gap: gap[0])
        return overlaps[0]
    if gaps:
        return gaps[0]
    return None


def _coarse_tr_metrics(
    *,
    mat_A,
    mat_B,
    geom,
    piezo,
    L_A: float,
    L_B: float,
    n_cells: int,
    R_load: float,
    active_gap: tuple[float, float] | None,
    excitation_type: str,
    excitation_amplitude: float,
    boundary_mass_factor: float,
) -> tuple[float, float, float, float]:
    """Estimate TR metrics with a deliberately small sweep inside the target gap."""
    nel_A = 2
    nel_B = 1
    if active_gap is None:
        return 0.0, 0.0, 0.0, 0.0

    gap_lo, gap_hi = active_gap
    if gap_hi <= gap_lo:
        return 0.0, 0.0, 0.0, 0.0

    f_array = np.linspace(gap_lo, gap_hi, 4)
    resp = beam_frequency_sweep(
        mat_A,
        mat_B,
        geom,
        piezo,
        L_A,
        L_B,
        n_cells,
        R_load,
        f_array=f_array,
        excitation_type=excitation_type,
        excitation_amplitude=excitation_amplitude,
        boundary_mass_factor=boundary_mass_factor,
        nel_A=nel_A,
        nel_B=nel_B,
    )
    if len(resp.f) == 0 or np.max(resp.power) <= 0:
        return 0.0, 0.0, 0.0, 0.0

    i_tr = int(np.argmax(resp.power))
    f_tr = float(resp.f[i_tr])
    power_tr = float(resp.power[i_tr])
    transmission_tr_dB = float(resp.transmission_dB[i_tr])
    eta_tr = _beam_localization_at_frequency(
        mat_A=mat_A,
        mat_B=mat_B,
        geom=geom,
        piezo=piezo,
        L_A=L_A,
        L_B=L_B,
        n_cells=n_cells,
        R_load=R_load,
        frequency_hz=f_tr,
        excitation_type=excitation_type,
        excitation_amplitude=excitation_amplitude,
        boundary_mass_factor=boundary_mass_factor,
        reference_f_max=gap_hi,
        nel_A=nel_A,
        nel_B=nel_B,
    )
    return f_tr, power_tr, transmission_tr_dB, eta_tr


def _beam_localization_at_frequency(
    *,
    mat_A,
    mat_B,
    geom,
    piezo,
    L_A: float,
    L_B: float,
    n_cells: int,
    R_load: float,
    frequency_hz: float,
    excitation_type: str,
    excitation_amplitude: float,
    boundary_mass_factor: float,
    reference_f_max: float,
    nel_A: int,
    nel_B: int,
) -> float:
    if frequency_hz <= 0:
        return 0.0

    sys = _build_fem_system(
        mat_A,
        mat_B,
        geom,
        piezo,
        L_A,
        L_B,
        n_cells,
        boundary_mass_factor=boundary_mass_factor,
        nel_A=nel_A,
        nel_B=nel_B,
    )
    alpha_ray, beta_ray = _screening_damping(reference_f_max)
    solved = _solve_frequency_response(
        sys,
        R_load=R_load,
        frequency_hz=frequency_hz,
        excitation_type=excitation_type,
        excitation_amplitude=excitation_amplitude,
        alpha_ray=alpha_ray,
        beta_ray=beta_ray,
        tan_delta=0.02,
    )
    if solved is None:
        return 0.0
    return float(_compute_localization_ratio(solved.u_full, 2 * np.pi * frequency_hz, sys))


def _screening_damping(reference_f_max: float) -> tuple[float, float]:
    f1_d = max(0.25 * reference_f_max, 1.0)
    f2_d = max(0.80 * reference_f_max, f1_d + 1.0)
    w1_d = 2 * np.pi * f1_d
    w2_d = 2 * np.pi * f2_d
    zeta1 = 0.005
    zeta2 = 0.008
    Aab = np.array([[1 / (2 * w1_d), w1_d / 2], [1 / (2 * w2_d), w2_d / 2]])
    ab = np.linalg.solve(Aab, np.array([zeta1, zeta2]))
    return max(float(ab[0]), 0.0), max(float(ab[1]), 0.0)
