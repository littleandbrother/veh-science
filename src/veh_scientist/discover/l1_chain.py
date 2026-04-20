"""Fast L1 diatomic-chain replay solver."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from scipy.linalg import eigh

from veh_scientist.discover.utils import ensure_dir, write_csv, write_json


@dataclass(frozen=True)
class ChainReplayParams:
    alpha: float = 2.0
    beta: float = 0.3
    delta: float = 0.25
    N: int = 20
    kappa2: float = 0.08
    epsilon: float = 1.7
    excitation_force: float = 1.0
    damping: float = 1.0e-7

    @property
    def ma(self) -> float:
        return 1.0 / self.alpha

    @property
    def mb(self) -> float:
        return 1.0

    @property
    def kb(self) -> float:
        return 1.0

    @property
    def ka(self) -> float:
        return 1.0 / self.beta

    @property
    def ma_plus(self) -> float:
        return self.delta * self.ma


def dispersion_branches(alpha: float, beta: float, q: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    coeff = (1.0 + alpha) * (1.0 + 1.0 / beta)
    disc = coeff**2 - (16.0 * alpha / beta) * np.sin(q / 2.0) ** 2
    disc = np.clip(disc, 0.0, None)
    omega_minus_sq = 0.5 * (coeff - np.sqrt(disc))
    omega_plus_sq = 0.5 * (coeff + np.sqrt(disc))
    return np.sqrt(omega_minus_sq), np.sqrt(omega_plus_sq)


def bandgap(alpha: float, beta: float, n_q: int = 2048) -> tuple[float, float]:
    q = np.linspace(0.0, np.pi, n_q)
    acoustic, optical = dispersion_branches(alpha, beta, q)
    return float(np.max(acoustic)), float(np.min(optical))


def _spring_edges(params: ChainReplayParams, omega: float | None = None, with_piezo: bool = False) -> list[tuple[int, int | None, complex]]:
    edges: list[tuple[int, int | None, complex]] = []
    edges.append((0, 1, params.kb))
    for cell in range(1, params.N + 1):
        b_idx = 2 * cell - 1
        a_idx = 2 * cell
        edges.append((b_idx, a_idx, params.ka))
        if cell < params.N:
            b_next = 2 * (cell + 1) - 1
            stiffness: complex = params.kb
            if with_piezo and cell == 1 and omega is not None:
                stiffness = params.kb * (1.0 - 1j * omega * params.kappa2 / (1j * omega + params.epsilon))
            edges.append((a_idx, b_next, stiffness))
        else:
            edges.append((a_idx, None, params.kb))
    return edges


def build_chain_matrices(params: ChainReplayParams, omega: float | None = None, with_piezo: bool = False) -> tuple[np.ndarray, np.ndarray]:
    n_dof = 2 * params.N + 1
    masses: list[float] = [params.ma_plus]
    for _ in range(params.N):
        masses.extend([params.mb, params.ma])
    mass_matrix = np.diag(masses)
    stiffness = np.zeros((n_dof, n_dof), dtype=complex if with_piezo else float)
    for i, j, k in _spring_edges(params, omega=omega, with_piezo=with_piezo):
        if j is None:
            stiffness[i, i] += k
        else:
            stiffness[i, i] += k
            stiffness[j, j] += k
            stiffness[i, j] -= k
            stiffness[j, i] -= k
    return mass_matrix, stiffness


def natural_modes(params: ChainReplayParams) -> tuple[np.ndarray, np.ndarray]:
    mass_matrix, stiffness = build_chain_matrices(params)
    omega_sq, modes = eigh(stiffness, mass_matrix)
    omega_sq = np.clip(np.real(omega_sq), 0.0, None)
    return np.sqrt(omega_sq), modes


def _cell_energy_distribution(params: ChainReplayParams, omega: float, mode_shape: np.ndarray) -> np.ndarray:
    masses = np.diag(build_chain_matrices(params)[0])
    kinetic = 0.5 * masses * omega**2 * np.abs(mode_shape) ** 2
    spring_energy = []
    for i, j, k in _spring_edges(params):
        if j is None:
            spring_energy.append(0.5 * np.real(k) * np.abs(mode_shape[i]) ** 2)
        else:
            spring_energy.append(0.5 * np.real(k) * np.abs(mode_shape[i] - mode_shape[j]) ** 2)
    spring_energy = np.array(spring_energy)

    energies = np.zeros(params.N)
    for cell in range(1, params.N + 1):
        b_idx = 2 * cell - 1
        a_idx = 2 * cell
        cell_energy = kinetic[b_idx] + kinetic[a_idx]
        if cell == 1:
            cell_energy += kinetic[0]
            cell_energy += np.sum(spring_energy[:3])
        else:
            # edges: [left boundary], then for each cell -> ka edge and inter-cell/ground edge
            ka_edge = 1 + 2 * (cell - 1)
            inter_edge = ka_edge + 1
            prev_inter_edge = ka_edge - 1
            cell_energy += spring_energy[ka_edge]
            if inter_edge < len(spring_energy):
                cell_energy += 0.5 * spring_energy[inter_edge]
            if prev_inter_edge >= 0:
                cell_energy += 0.5 * spring_energy[prev_inter_edge]
        energies[cell - 1] = cell_energy
    return energies


def localization_ratio(params: ChainReplayParams, omega: float, mode_shape: np.ndarray) -> float:
    energies = _cell_energy_distribution(params, omega, mode_shape)
    total = float(np.sum(energies))
    if total <= 0.0:
        return 0.0
    return float(energies[0] / total)


def identify_tr_modes(params: ChainReplayParams) -> list[dict[str, Any]]:
    gap_low, gap_high = bandgap(params.alpha, params.beta)
    omegas, modes = natural_modes(params)
    tr_modes: list[dict[str, Any]] = []
    for idx, omega in enumerate(omegas):
        if gap_low < omega < gap_high:
            mode = modes[:, idx]
            eta = localization_ratio(params, float(omega), mode)
            tr_modes.append(
                {
                    "mode_index": int(idx),
                    "omega": float(omega),
                    "eta": eta,
                    "mode_shape": np.real_if_close(mode).real.tolist(),
                }
            )
    tr_modes.sort(key=lambda item: (-item["eta"], item["omega"]))
    return tr_modes


def response_spectrum(params: ChainReplayParams, omegas: np.ndarray, with_piezo: bool = False) -> dict[str, np.ndarray]:
    mass_matrix, _ = build_chain_matrices(params)
    force = np.zeros(mass_matrix.shape[0], dtype=complex)
    force[0] = params.excitation_force

    transmission_db: list[float] = []
    gap_amplitude: list[float] = []
    voltage_mag: list[float] = []
    power_norm: list[float] = []
    boundary_amp: list[float] = []
    terminal_amp: list[float] = []

    for omega in omegas:
        _, stiffness = build_chain_matrices(params, omega=omega, with_piezo=with_piezo)
        dynamic = stiffness - omega**2 * mass_matrix + 1j * params.damping * np.eye(mass_matrix.shape[0])
        displacement = np.linalg.solve(dynamic, force)
        left_amp = max(np.abs(displacement[0]), 1.0e-15)
        right_amp = max(np.abs(displacement[-1]), 1.0e-15)
        gap = displacement[2] - displacement[3]
        voltage = -(1j * omega / (1j * omega + params.epsilon)) * gap if with_piezo else 0.0j
        power = 0.5 * params.epsilon * np.abs(voltage) ** 2 if with_piezo else 0.0

        transmission_db.append(float(20.0 * np.log10(right_amp / left_amp)))
        gap_amplitude.append(float(np.abs(gap)))
        voltage_mag.append(float(np.abs(voltage)))
        power_norm.append(float(np.real(power)))
        boundary_amp.append(float(left_amp))
        terminal_amp.append(float(right_amp))

    return {
        "omega": np.array(omegas, dtype=float),
        "transmission_db": np.array(transmission_db, dtype=float),
        "gap_amplitude": np.array(gap_amplitude, dtype=float),
        "voltage_mag": np.array(voltage_mag, dtype=float),
        "power_norm": np.array(power_norm, dtype=float),
        "boundary_amp": np.array(boundary_amp, dtype=float),
        "terminal_amp": np.array(terminal_amp, dtype=float),
    }


def _estimate_peak_quality(omega: np.ndarray, amplitude: np.ndarray, peak_index: int) -> float:
    peak = amplitude[peak_index]
    if peak <= 0.0:
        return 0.0
    half = peak / np.sqrt(2.0)
    left = peak_index
    right = peak_index
    while left > 0 and amplitude[left] > half:
        left -= 1
    while right < len(amplitude) - 1 and amplitude[right] > half:
        right += 1
    width = max(float(omega[right] - omega[left]), 1.0e-8)
    return float(omega[peak_index] / width)


def _plot_dispersion(output_dir: Path, q: np.ndarray, acoustic: np.ndarray, optical: np.ndarray, gap_low: float, gap_high: float) -> Path:
    path = output_dir / "dispersion_curve.png"
    fig = plt.figure(figsize=(7.2, 4.8))
    ax = fig.add_subplot(111)
    ax.plot(q, acoustic)
    ax.plot(q, optical)
    ax.axhspan(gap_low, gap_high, alpha=0.15)
    ax.set_xlabel("q")
    ax.set_ylabel(r"$\Omega$")
    ax.set_title("Infinite-chain dispersion and bandgap")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _plot_spectrum(output_dir: Path, spectrum: dict[str, np.ndarray], gap_low: float, gap_high: float) -> Path:
    path = output_dir / "chain_spectrum.png"
    omega = spectrum["omega"]
    fig = plt.figure(figsize=(7.2, 4.8))
    ax = fig.add_subplot(111)
    ax.plot(omega, spectrum["gap_amplitude"], label="gap amplitude")
    ax.plot(omega, spectrum["transmission_db"], label="transmission (dB)")
    ax.axvspan(gap_low, gap_high, alpha=0.15)
    ax.set_xlabel(r"$\Omega$")
    ax.set_title("Finite-chain response")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _plot_harvesting(output_dir: Path, spectrum: dict[str, np.ndarray], gap_low: float, gap_high: float) -> Path:
    path = output_dir / "harvesting_spectrum.png"
    omega = spectrum["omega"]
    fig = plt.figure(figsize=(7.2, 4.8))
    ax = fig.add_subplot(111)
    ax.plot(omega, spectrum["voltage_mag"], label="|V~|")
    ax.plot(omega, spectrum["power_norm"], label="P~")
    ax.plot(omega, spectrum["transmission_db"], label="transmission (dB)")
    ax.axvspan(gap_low, gap_high, alpha=0.15)
    ax.set_xlabel(r"$\Omega$")
    ax.set_title("Piezoelectric harvesting at TR")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _plot_mode_shape(output_dir: Path, mode_shape: np.ndarray, tr_omega: float) -> Path:
    path = output_dir / "tr_mode_shape.png"
    fig = plt.figure(figsize=(7.2, 4.8))
    ax = fig.add_subplot(111)
    ax.plot(np.arange(len(mode_shape)), np.abs(mode_shape))
    ax.set_xlabel("DOF index")
    ax.set_ylabel("|mode amplitude|")
    ax.set_title(f"TR mode shape at Ω={tr_omega:.4f}")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _plot_delta_scan(output_dir: Path, delta_rows: list[dict[str, Any]]) -> Path:
    path = output_dir / "delta_scan.png"
    fig = plt.figure(figsize=(7.2, 4.8))
    ax = fig.add_subplot(111)
    ax.plot([row["delta"] for row in delta_rows], [row["tr_count"] for row in delta_rows], label="TR count")
    ax.plot([row["delta"] for row in delta_rows], [row["peak_voltage"] for row in delta_rows], label="peak voltage")
    ax.set_xlabel(r"$\delta$")
    ax.set_title("Boundary asymmetry sweep")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _plot_heatmap(output_dir: Path, filename: str, x: np.ndarray, y: np.ndarray, values: np.ndarray, xlabel: str, ylabel: str, title: str) -> Path:
    path = output_dir / filename
    fig = plt.figure(figsize=(7.2, 4.8))
    ax = fig.add_subplot(111)
    mesh = ax.pcolormesh(x, y, values, shading="auto")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    fig.colorbar(mesh, ax=ax)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _first_passband_peak(params: ChainReplayParams, gap_low: float) -> tuple[float, float]:
    delta1 = ChainReplayParams(
        alpha=params.alpha,
        beta=params.beta,
        delta=1.0,
        N=params.N,
        kappa2=params.kappa2,
        epsilon=params.epsilon,
        excitation_force=params.excitation_force,
        damping=params.damping,
    )
    omega = np.linspace(0.08, max(0.12, 0.98 * gap_low), 800)
    spectrum = response_spectrum(delta1, omega, with_piezo=True)
    peak_idx = int(np.argmax(spectrum["power_norm"]))
    return float(omega[peak_idx]), float(spectrum["power_norm"][peak_idx])


def run_l1_chain_replay(output_dir: str | Path, params: ChainReplayParams | None = None) -> dict[str, Any]:
    params = params or ChainReplayParams()
    output_dir = ensure_dir(output_dir)

    gap_low, gap_high = bandgap(params.alpha, params.beta)
    tr_modes = identify_tr_modes(params)
    if not tr_modes:
        raise RuntimeError("No truncation-resonance mode found for the selected chain parameters.")
    tr_mode = tr_modes[0]
    tr_omega = float(tr_mode["omega"])

    q = np.linspace(0.0, np.pi, 400)
    acoustic, optical = dispersion_branches(params.alpha, params.beta, q)
    omega_grid = np.linspace(max(0.05, 0.4 * gap_low), min(3.2, 1.6 * gap_high), 1800)
    mechanical_spectrum = response_spectrum(params, omega_grid, with_piezo=False)
    electromech_spectrum = response_spectrum(params, omega_grid, with_piezo=True)

    tr_idx = int(np.argmin(np.abs(electromech_spectrum["omega"] - tr_omega)))
    q_factor = _estimate_peak_quality(
        electromech_spectrum["omega"],
        electromech_spectrum["gap_amplitude"],
        tr_idx,
    )
    baseline_omega, baseline_power = _first_passband_peak(params, gap_low)
    tr_power = float(np.max(electromech_spectrum["power_norm"]))
    pef = tr_power / baseline_power if baseline_power > 0.0 else float("inf")

    # Parameter sweeps.
    delta_values = np.array([0.25, 0.5, 0.75, 1.0, 1.5, 2.0])
    delta_rows: list[dict[str, Any]] = []
    for delta in delta_values:
        sweep_params = ChainReplayParams(
            alpha=params.alpha,
            beta=params.beta,
            delta=float(delta),
            N=params.N,
            kappa2=params.kappa2,
            epsilon=params.epsilon,
            excitation_force=params.excitation_force,
            damping=params.damping,
        )
        sweep_modes = identify_tr_modes(sweep_params)
        sweep_spectrum = response_spectrum(sweep_params, omega_grid, with_piezo=True)
        delta_rows.append(
            {
                "delta": float(delta),
                "tr_count": int(len(sweep_modes)),
                "tr_omega": float(sweep_modes[0]["omega"]) if sweep_modes else None,
                "peak_voltage": float(np.max(sweep_spectrum["voltage_mag"])),
            }
        )

    alpha_values = np.linspace(0.5, 2.0, 6)
    beta_values = np.linspace(0.4, 2.0, 6)
    alpha_beta_map = np.full((len(beta_values), len(alpha_values)), np.nan)
    for iy, beta in enumerate(beta_values):
        for ix, alpha in enumerate(alpha_values):
            sweep_params = ChainReplayParams(alpha=float(alpha), beta=float(beta), delta=params.delta, N=params.N)
            sweep_modes = identify_tr_modes(sweep_params)
            alpha_beta_map[iy, ix] = sweep_modes[0]["omega"] if sweep_modes else np.nan

    kappa_values = np.linspace(0.02, 0.20, 6)
    epsilon_values = np.linspace(0.5, 2.5, 6)
    matching_map = np.zeros((len(epsilon_values), len(kappa_values)))
    for iy, epsilon in enumerate(epsilon_values):
        for ix, kappa in enumerate(kappa_values):
            sweep_params = ChainReplayParams(
                alpha=params.alpha,
                beta=params.beta,
                delta=params.delta,
                N=params.N,
                kappa2=float(kappa),
                epsilon=float(epsilon),
            )
            sweep_spectrum = response_spectrum(sweep_params, omega_grid, with_piezo=True)
            matching_map[iy, ix] = float(np.max(sweep_spectrum["power_norm"]))

    n_values = np.array([10, 14, 18, 22])
    n_rows: list[dict[str, Any]] = []
    for n in n_values:
        sweep_params = ChainReplayParams(
            alpha=params.alpha,
            beta=params.beta,
            delta=params.delta,
            N=int(n),
            kappa2=params.kappa2,
            epsilon=params.epsilon,
        )
        sweep_modes = identify_tr_modes(sweep_params)
        if not sweep_modes:
            continue
        local_tr_omega = float(sweep_modes[0]["omega"])
        local_grid = np.linspace(max(0.05, local_tr_omega - 0.2), local_tr_omega + 0.2, 900)
        local_spectrum = response_spectrum(sweep_params, local_grid, with_piezo=False)
        peak_idx = int(np.argmax(local_spectrum["gap_amplitude"]))
        n_rows.append(
            {
                "N": int(n),
                "tr_omega": local_tr_omega,
                "peak_gap_amplitude": float(np.max(local_spectrum["gap_amplitude"])),
                "q_factor": _estimate_peak_quality(local_grid, local_spectrum["gap_amplitude"], peak_idx),
            }
        )

    # Save tabular outputs.
    write_csv(
        output_dir / "dispersion_curve.csv",
        [
            {"q": float(qi), "acoustic": float(a_val), "optical": float(o_val)}
            for qi, a_val, o_val in zip(q, acoustic, optical)
        ],
    )
    write_csv(
        output_dir / "chain_spectrum.csv",
        [
            {
                "omega": float(omega),
                "gap_amplitude": float(gap),
                "transmission_db": float(trans),
                "voltage_mag": float(voltage),
                "power_norm": float(power),
            }
            for omega, gap, trans, voltage, power in zip(
                electromech_spectrum["omega"],
                electromech_spectrum["gap_amplitude"],
                electromech_spectrum["transmission_db"],
                electromech_spectrum["voltage_mag"],
                electromech_spectrum["power_norm"],
            )
        ],
    )
    write_csv(output_dir / "delta_scan.csv", delta_rows)
    write_csv(
        output_dir / "N_sweep.csv",
        n_rows,
        fieldnames=["N", "tr_omega", "peak_gap_amplitude", "q_factor"],
    )
    write_json(
        output_dir / "alpha_beta_map.json",
        {
            "alpha_values": alpha_values.tolist(),
            "beta_values": beta_values.tolist(),
            "tr_frequency_map": alpha_beta_map.tolist(),
        },
    )
    write_json(
        output_dir / "matching_map.json",
        {
            "kappa2_values": kappa_values.tolist(),
            "epsilon_values": epsilon_values.tolist(),
            "peak_power_map": matching_map.tolist(),
        },
    )

    figures = {
        "dispersion_curve": str(_plot_dispersion(output_dir, q, acoustic, optical, gap_low, gap_high)),
        "chain_spectrum": str(_plot_spectrum(output_dir, mechanical_spectrum, gap_low, gap_high)),
        "harvesting_spectrum": str(_plot_harvesting(output_dir, electromech_spectrum, gap_low, gap_high)),
        "tr_mode_shape": str(_plot_mode_shape(output_dir, np.array(tr_mode["mode_shape"]), tr_omega)),
        "delta_scan": str(_plot_delta_scan(output_dir, delta_rows)),
        "alpha_beta_map": str(
            _plot_heatmap(
                output_dir,
                "alpha_beta_map.png",
                alpha_values,
                beta_values,
                alpha_beta_map,
                xlabel=r"$\alpha$",
                ylabel=r"$\beta$",
                title="TR frequency map over (alpha, beta)",
            )
        ),
        "matching_map": str(
            _plot_heatmap(
                output_dir,
                "matching_map.png",
                kappa_values,
                epsilon_values,
                matching_map,
                xlabel=r"$\kappa^2$",
                ylabel=r"$\epsilon$",
                title="Peak normalized power over (kappa^2, epsilon)",
            )
        ),
    }

    summary = {
        "params": params.__dict__,
        "bandgap": {"omega_min": gap_low, "omega_max": gap_high},
        "tr_mode": tr_mode,
        "tr_voltage_peak_omega": float(electromech_spectrum["omega"][int(np.argmax(electromech_spectrum["voltage_mag"]))]),
        "tr_power_peak_omega": float(electromech_spectrum["omega"][int(np.argmax(electromech_spectrum["power_norm"]))]),
        "transmission_at_tr_power_peak_db": float(electromech_spectrum["transmission_db"][int(np.argmax(electromech_spectrum["power_norm"]))]),
        "baseline_pb1_omega": baseline_omega,
        "baseline_pb1_power": baseline_power,
        "tr_peak_power": tr_power,
        "power_enhancement_factor": float(pef),
        "q_factor": float(q_factor),
        "figures": figures,
    }
    write_json(output_dir / "chain_summary.json", summary)
    return summary
