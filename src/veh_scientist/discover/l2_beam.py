"""Continuous L2 beam replay solver using a dimensionless Timoshenko transfer matrix."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from scipy.linalg import expm

from veh_scientist.discover.utils import ensure_dir, write_csv, write_json


@dataclass(frozen=True)
class BeamReplayParams:
    cell_pitch_m: float = 0.02
    layer_split: tuple[float, float] = (0.5, 0.5)
    E_a: float = 70.0e9
    G_a: float = 26.0e9
    rho_a: float = 2700.0
    E_b: float = 3.5e9
    G_b: float = 1.3e9
    rho_b: float = 1200.0
    kappa_a: float = 5.0 / 6.0
    kappa_b: float = 5.0 / 6.0
    area_a: float = 1.0e-4
    area_b: float = 1.0e-4
    inertia_a: float = 8.33e-10
    inertia_b: float = 8.33e-10
    n_cells: int = 12
    piezo_kappa2: float = 0.06
    piezo_epsilon: float = 9.0
    bloch_tol: float = 3.0e-3

    @property
    def omega_b(self) -> float:
        return float(np.sqrt(self.E_b * self.inertia_b / (self.rho_b * self.area_b * self.cell_pitch_m**4)))

    @property
    def alpha_a(self) -> float:
        return self.E_a * self.inertia_a / (self.E_b * self.inertia_b)

    @property
    def r_a(self) -> float:
        return self.rho_a * self.area_a / (self.rho_b * self.area_b)

    @property
    def eta_a(self) -> float:
        return self.rho_a * self.inertia_a / (self.rho_b * self.area_b * self.cell_pitch_m**2)

    @property
    def eta_b(self) -> float:
        return self.rho_b * self.inertia_b / (self.rho_b * self.area_b * self.cell_pitch_m**2)

    @property
    def beta_a(self) -> float:
        return self.kappa_a * self.G_a * self.area_a * self.cell_pitch_m**2 / (self.E_b * self.inertia_b)

    @property
    def beta_b(self) -> float:
        return self.kappa_b * self.G_b * self.area_b * self.cell_pitch_m**2 / (self.E_b * self.inertia_b)


def state_matrix(alpha: float, r: float, eta: float, beta: float, omega_nd: float) -> np.ndarray:
    return np.array(
        [
            [0.0, 1.0, 1.0 / beta, 0.0],
            [0.0, 0.0, 0.0, 1.0 / alpha],
            [-(omega_nd**2) * r, 0.0, 0.0, 0.0],
            [0.0, -(omega_nd**2) * eta, -1.0, 0.0],
        ],
        dtype=complex,
    )


def layer_transfer(alpha: float, r: float, eta: float, beta: float, length_ratio: float, omega_nd: float) -> np.ndarray:
    return expm(state_matrix(alpha, r, eta, beta, omega_nd) * length_ratio)


def cell_transfer(params: BeamReplayParams, omega_nd: float) -> np.ndarray:
    l_a, l_b = params.layer_split
    t_a = layer_transfer(params.alpha_a, params.r_a, params.eta_a, params.beta_a, l_a, omega_nd)
    t_b = layer_transfer(1.0, 1.0, params.eta_b, params.beta_b, l_b, omega_nd)
    return t_b @ t_a


def finite_boundary_matrix(params: BeamReplayParams, omega_nd: float) -> np.ndarray:
    t_n = np.linalg.matrix_power(cell_transfer(params, omega_nd), params.n_cells)
    b_l = np.array([[1.0, 0.0], [0.0, 1.0], [0.0, 0.0], [0.0, 0.0]], dtype=complex)
    c_r = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]], dtype=complex)
    return c_r @ t_n @ b_l


def bloch_passband_indicator(params: BeamReplayParams, omega_nd: float) -> tuple[bool, np.ndarray, np.ndarray]:
    evals = np.linalg.eigvals(cell_transfer(params, omega_nd))
    modulus_deviation = np.abs(np.abs(evals) - 1.0)
    on_unit_circle = np.any(modulus_deviation < params.bloch_tol)
    k_values = np.abs(np.angle(evals))
    return bool(on_unit_circle), evals, k_values


def stopbands(params: BeamReplayParams, omega_nd_grid: np.ndarray) -> list[tuple[float, float]]:
    flags = [bloch_passband_indicator(params, omega_nd)[0] for omega_nd in omega_nd_grid]
    intervals: list[tuple[float, float]] = []
    in_gap = False
    start = 0.0
    for omega_nd, is_passband in zip(omega_nd_grid, flags):
        if not is_passband and not in_gap:
            start = float(omega_nd)
            in_gap = True
        elif is_passband and in_gap:
            intervals.append((start, float(omega_nd)))
            in_gap = False
    if in_gap:
        intervals.append((start, float(omega_nd_grid[-1])))
    return intervals


def boundary_mode_states(params: BeamReplayParams, omega_nd: float) -> tuple[np.ndarray, float]:
    b_l = np.array([[1.0, 0.0], [0.0, 1.0], [0.0, 0.0], [0.0, 0.0]], dtype=complex)
    matrix = finite_boundary_matrix(params, omega_nd)
    _, singular_values, vh = np.linalg.svd(matrix)
    seed = vh[-1].conj()
    state = b_l @ seed
    states = [state]
    t_cell = cell_transfer(params, omega_nd)
    for _ in range(params.n_cells):
        state = t_cell @ state
        states.append(state)
    return np.array(states), float(singular_values[-1])


def localization_score(states: np.ndarray) -> float:
    displacement_energy = np.abs(states[:, 0]) ** 2 + 0.1 * np.abs(states[:, 1]) ** 2
    total = float(np.sum(displacement_energy))
    if total <= 0.0:
        return 0.0
    return float(np.sum(displacement_energy[:2]) / total)


def normalized_voltage_power(states: np.ndarray, omega_nd: float, kappa2: float, epsilon: float) -> tuple[float, float]:
    if len(states) < 2:
        return 0.0, 0.0
    gap = states[0, 0] - states[1, 0]
    voltage = -(1j * omega_nd / (1j * omega_nd + epsilon)) * gap
    power = 0.5 * epsilon * np.abs(voltage) ** 2 * (1.0 + kappa2)
    return float(np.abs(voltage)), float(np.real(power))


def attenuation_proxy(evals: np.ndarray) -> float:
    attenuation = np.max(np.abs(np.log(np.clip(np.abs(evals), 1.0e-12, None))))
    return float(1.0 - np.exp(-attenuation))


def beam_gap_candidates(params: BeamReplayParams, omega_nd_grid: np.ndarray) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    gaps = stopbands(params, omega_nd_grid)
    for band_index, (gap_low, gap_high) in enumerate(gaps, start=1):
        local_grid = np.linspace(gap_low, gap_high, 500)
        smins = []
        passband_cache: list[tuple[np.ndarray, np.ndarray]] = []
        state_cache: list[np.ndarray] = []
        for omega_nd in local_grid:
            states, smin = boundary_mode_states(params, omega_nd)
            _, evals, _ = bloch_passband_indicator(params, omega_nd)
            smins.append(smin)
            state_cache.append(states)
            passband_cache.append((evals, states))
        smins_arr = np.array(smins)
        start = max(1, int(0.08 * len(local_grid)))
        end = min(len(local_grid) - 1, int(0.92 * len(local_grid)))
        idx = start + int(np.argmin(smins_arr[start:end]))
        omega_tr = float(local_grid[idx])
        evals, states = passband_cache[idx]
        loc = localization_score(states)
        voltage, power = normalized_voltage_power(states, omega_tr, params.piezo_kappa2, params.piezo_epsilon)
        width = max(gap_high - gap_low, 1.0e-9)
        center = 0.5 * (gap_low + gap_high)
        edge_distance = min(omega_tr - gap_low, gap_high - omega_tr)
        gap_min_hz = float(gap_low * params.omega_b / (2.0 * np.pi))
        gap_max_hz = float(gap_high * params.omega_b / (2.0 * np.pi))
        freq_hz = float(omega_tr * params.omega_b / (2.0 * np.pi))
        candidates.append(
            {
                "band_index": band_index,
                "omega_min": float(gap_low),
                "omega_max": float(gap_high),
                "omega_tr": omega_tr,
                "frequency_hz": freq_hz,
                "raw_frequency_hz": freq_hz,
                "gap_center_hz": float(center * params.omega_b / (2.0 * np.pi)),
                "gap_width_nd": float(width),
                "raw_stopband_hz": [gap_min_hz, gap_max_hz],
                "smin": float(smins_arr[idx]),
                "suppression_margin": attenuation_proxy(evals) * max(0.0, min(1.0, 2.0 * edge_distance / width)),
                "localization_score": loc,
                "voltage_proxy": voltage,
                "power_proxy": power,
                "robustness_score": float(min(1.0, width / max(omega_nd_grid[-1], 1.0e-9) * 8.0)),
                "states": np.real_if_close(states).real.tolist(),
                "smin_curve": smins_arr.tolist(),
                "omega_curve": local_grid.tolist(),
            }
        )
    return candidates


def _plot_band_structure(output_dir: Path, band_points: list[dict[str, float]], gap_intervals: list[tuple[float, float]], params: BeamReplayParams) -> Path:
    path = output_dir / "beam_band_structure.png"
    fig = plt.figure(figsize=(7.2, 4.8))
    ax = fig.add_subplot(111)
    if band_points:
        ax.scatter([point["k"] for point in band_points], [point["frequency_hz"] for point in band_points], s=4)
    for gap_low, gap_high in gap_intervals:
        ax.axhspan(gap_low * params.omega_b / (2.0 * np.pi), gap_high * params.omega_b / (2.0 * np.pi), alpha=0.12)
    ax.set_xlabel("|ka|")
    ax.set_ylabel("Frequency (Hz)")
    ax.set_title("Bilayer Timoshenko beam band structure")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _plot_gap_candidates(output_dir: Path, candidates: list[dict[str, Any]]) -> Path:
    path = output_dir / "beam_gap_candidates.png"
    fig = plt.figure(figsize=(7.2, 4.8))
    ax = fig.add_subplot(111)
    ax.plot([cand["band_index"] for cand in candidates], [cand["frequency_hz"] for cand in candidates], marker="o")
    ax.set_xlabel("Bandgap index")
    ax.set_ylabel("Candidate TR frequency (Hz)")
    ax.set_title("Candidate TR locations across beam stopbands")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _plot_mode_shape(output_dir: Path, candidate: dict[str, Any]) -> Path:
    path = output_dir / f"beam_mode_shape_gap{candidate['band_index']}.png"
    states = np.array(candidate["states"])
    fig = plt.figure(figsize=(7.2, 4.8))
    ax = fig.add_subplot(111)
    ax.plot(np.arange(states.shape[0]), np.abs(states[:, 0]))
    ax.set_xlabel("Cell boundary index")
    ax.set_ylabel("|w| (normalized)")
    ax.set_title(f"Boundary-localized beam mode for gap {candidate['band_index']}")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def run_l2_beam_replay(output_dir: str | Path, params: BeamReplayParams | None = None) -> dict[str, Any]:
    params = params or BeamReplayParams()
    output_dir = ensure_dir(output_dir)

    omega_grid = np.linspace(0.2, 40.0, 1000)
    gap_intervals = stopbands(params, omega_grid)
    candidates = beam_gap_candidates(params, omega_grid)

    band_points: list[dict[str, float]] = []
    for omega_nd in np.linspace(0.2, 40.0, 450):
        is_passband, _, k_values = bloch_passband_indicator(params, omega_nd)
        if not is_passband:
            continue
        for kval in k_values:
            if 0.0 <= kval <= np.pi:
                band_points.append(
                    {
                        "omega_nd": float(omega_nd),
                        "k": float(kval),
                        "frequency_hz": float(omega_nd * params.omega_b / (2.0 * np.pi)),
                    }
                )

    figures = {
        "beam_band_structure": str(_plot_band_structure(output_dir, band_points, gap_intervals, params)),
        "beam_gap_candidates": str(_plot_gap_candidates(output_dir, candidates)),
    }
    if candidates:
        figures["beam_mode_shape"] = str(_plot_mode_shape(output_dir, candidates[0]))

    write_csv(output_dir / "beam_band_points.csv", band_points, fieldnames=["omega_nd", "k", "frequency_hz"])
    write_json(output_dir / "beam_gap_candidates.json", candidates)
    stopbands_hz = [
        {
            "frequency_min_hz": float(lo * params.omega_b / (2.0 * np.pi)),
            "frequency_max_hz": float(hi * params.omega_b / (2.0 * np.pi)),
        }
        for lo, hi in gap_intervals
    ]
    write_json(
        output_dir / "beam_summary.json",
        {
            "params": params.__dict__,
            "omega_b": params.omega_b,
            "stopbands_nd": [{"omega_min": lo, "omega_max": hi} for lo, hi in gap_intervals],
            "stopbands_hz": stopbands_hz,
            "candidates": candidates,
            "figures": figures,
        },
    )
    return {
        "params": params.__dict__,
        "omega_b": params.omega_b,
        "stopbands_nd": gap_intervals,
        "stopbands_hz": stopbands_hz,
        "candidates": candidates,
        "figures": figures,
    }
