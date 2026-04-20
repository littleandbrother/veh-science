"""Cross-validate the continuous beam model across Python, MATLAB, and COMSOL."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from veh_scientist.verifiers.l2_beam import (
    BeamGeometry,
    MaterialProperties,
    beam_frequency_sweep,
    compute_beam_harvesting_metrics,
)
from veh_scientist.verifiers.l2_beam.tmm import PiezoProperties
from veh_scientist.verifiers.l3_matlab import (
    PeriodicBeamMatlabConfig,
    run_periodic_beam_matlab,
)
from veh_scientist.verifiers.l3_comsol import (
    PeriodicBeamCOMSOLConfig,
    build_and_run_periodic_beam,
)

OUTDIR = Path("results/beam_oracle_validation")
OUTDIR.mkdir(parents=True, exist_ok=True)

MAT_A = MaterialProperties(E=68.9e9, rho=2700, nu=0.33)
MAT_B = MaterialProperties(E=2.4e9, rho=1040, nu=0.35)
GEOM = BeamGeometry(b=0.025, h=0.005, ks=5.0 / 6.0)
PIEZO = PiezoProperties(h=0.0005, rho=7500, d31=-274e-12, E=62e9, eps33T=3400 * 8.854e-12)
L_A = 0.08
L_B = 0.02
N_CELLS = 12
R_LOAD = 1.0e6
F_MIN = 1.0
F_MAX = 3000.0
N_FREQ = 96
EXCITATION_TYPE = "acceleration"
EXCITATION_AMPLITUDE = 9.81
COMSOL_FREQ_SAMPLES = 96
COMSOL_EIGENMODES = 24
TREND_F_MIN_HZ = 50.0


def run_validation(*, include_matlab: bool = True, include_comsol: bool = True) -> dict:
    freq = np.linspace(F_MIN, F_MAX, N_FREQ)
    python_resp = beam_frequency_sweep(
        MAT_A,
        MAT_B,
        GEOM,
        PIEZO,
        L_A,
        L_B,
        N_CELLS,
        R_LOAD,
        f_array=freq,
        excitation_type=EXCITATION_TYPE,
        excitation_amplitude=EXCITATION_AMPLITUDE,
    )
    python_metrics = compute_beam_harvesting_metrics(
        MAT_A,
        MAT_B,
        GEOM,
        PIEZO,
        L_A,
        L_B,
        N_CELLS,
        R_LOAD,
        f_min=F_MIN,
        f_max=F_MAX,
        n_points_bandgap=120,
        n_points_sweep=N_FREQ,
        excitation_type=EXCITATION_TYPE,
        excitation_amplitude=EXCITATION_AMPLITUDE,
    )
    report: dict[str, object] = {
        "artifacts": {
            "raw_plot": str(OUTDIR / "beam_oracle_validation_raw.png"),
            "trend_plot": str(OUTDIR / "beam_oracle_validation_trend.png"),
            "structure_plot": str(OUTDIR / "beam_oracle_validation_structure.png"),
            "legacy_plot": str(OUTDIR / "beam_oracle_validation.png"),
            "trend_min_hz": TREND_F_MIN_HZ,
            "trend_normalization": "|u_base| = a_exc/(2*pi*f)^2 under fixed acceleration input",
        },
        "python": {
            "output_definition": "terminal voltage amplitude |V| under shared fixed base acceleration input and mean resistive power |V|^2/(2R)",
            "f_tr_hz": python_metrics.f_tr,
            "f_pb1_hz": python_metrics.f_pb1,
            "power_tr_w": python_metrics.power_tr,
            "pef": python_metrics.pef,
            "eta_tr": python_metrics.eta_tr,
        }
    }

    matlab_data = None
    if include_matlab:
        try:
            matlab_data = run_periodic_beam_matlab(
                PeriodicBeamMatlabConfig(
                    beam_width=GEOM.b,
                    beam_height=GEOM.h,
                    L_A=L_A,
                    L_B=L_B,
                    n_cells=N_CELLS,
                    piezo_thickness=PIEZO.h,
                    load_resistance_ohm=R_LOAD,
                    f_min_hz=F_MIN,
                    f_max_hz=F_MAX,
                    n_freq=N_FREQ,
                    excitation_type=EXCITATION_TYPE,
                    excitation_amplitude=EXCITATION_AMPLITUDE,
                )
            )
            report["matlab"] = _compare_backend(
                python_resp.f,
                python_resp.voltage,
                python_resp.power,
                python_resp.transmission_dB,
                matlab_data["frequency_hz"],
                matlab_data["voltage_v"],
                matlab_data["power_w"],
                matlab_data["transmission_db"],
            )
            if "w_left_m" in matlab_data and "w_right_m" in matlab_data:
                report["matlab"].update(
                    _compare_structure(
                        python_resp.f,
                        python_resp.w_left,
                        python_resp.w_right,
                        matlab_data["frequency_hz"],
                        matlab_data["w_left_m"],
                        matlab_data["w_right_m"],
                    )
                )
            report["matlab"]["f_tr_hz"] = float(matlab_data.get("f_tr_hz", 0.0))
            report["matlab"]["pef"] = float(matlab_data.get("pef", 0.0))
            report["matlab"]["eta_tr"] = float(matlab_data.get("eta_tr", 0.0))
        except Exception as exc:  # pragma: no cover - environment dependent
            report["matlab"] = {"status": "unavailable", "error": str(exc)}

    comsol_data = None
    if include_comsol:
        try:
            comsol_data = build_and_run_periodic_beam(
                PeriodicBeamCOMSOLConfig(
                    n_cells=N_CELLS,
                    L_A=L_A,
                    L_B=L_B,
                    beam_width=GEOM.b,
                    beam_height=GEOM.h,
                    piezo_thickness=PIEZO.h,
                    load_resistance_ohm=R_LOAD,
                    a_exc=EXCITATION_AMPLITUDE,
                    f_min=F_MIN,
                    f_max=F_MAX,
                    n_freq=COMSOL_FREQ_SAMPLES,
                    n_eigs=COMSOL_EIGENMODES,
                ),
                save_path=str(OUTDIR / "periodic_piezo_beam.mph"),
            )
            report["comsol"] = _compare_backend(
                python_resp.f,
                python_resp.voltage,
                python_resp.power,
                python_resp.transmission_dB,
                comsol_data["frequency_hz"],
                comsol_data["voltage_v"],
                comsol_data["power_w"],
                comsol_data.get("transmission_db"),
            )
            if "w_left_m" in comsol_data and "w_right_m" in comsol_data:
                report["comsol"].update(
                    _compare_structure(
                        python_resp.f,
                        python_resp.w_left,
                        python_resp.w_right,
                        comsol_data["frequency_hz"],
                        comsol_data["w_left_m"],
                        comsol_data["w_right_m"],
                    )
                )
            report["comsol"].update({
                "status": "ok",
                "n_eigenfrequencies": int(len(comsol_data["eigenfrequencies_hz"])),
                "peak_voltage_v": float(np.max(comsol_data["voltage_v"])) if len(comsol_data["voltage_v"]) else 0.0,
                "peak_power_w": float(np.max(comsol_data["power_w"])) if len(comsol_data["power_w"]) else 0.0,
                "peak_disp_m": float(np.max(comsol_data["max_disp_m"])) if len(comsol_data["max_disp_m"]) else 0.0,
            })
        except Exception as exc:  # pragma: no cover - environment dependent
            report["comsol"] = {"status": "unavailable", "error": str(exc)}

    _plot_raw_results(python_resp, matlab_data, comsol_data)
    _plot_trend_results(python_resp, matlab_data, comsol_data)
    _plot_structure_results(python_resp, matlab_data, comsol_data)
    report_path = OUTDIR / "beam_oracle_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def _compare_backend(
    ref_f: np.ndarray,
    ref_v: np.ndarray,
    ref_p: np.ndarray,
    ref_t: np.ndarray | None,
    test_f: np.ndarray,
    test_v: np.ndarray,
    test_p: np.ndarray,
    test_t: np.ndarray | None,
) -> dict[str, float | str]:
    interp_v = np.interp(ref_f, test_f, test_v)
    interp_p = np.interp(ref_f, test_f, test_p)
    result: dict[str, float | str] = {
        "status": "ok",
        "max_voltage_rel_err": float(_safe_rel_err(ref_v, interp_v)),
        "median_voltage_rel_err": float(_median_rel_err(ref_v, interp_v)),
        "max_power_rel_err": float(_safe_rel_err(ref_p, interp_p)),
        "median_power_rel_err": float(_median_rel_err(ref_p, interp_p)),
    }
    if ref_t is not None and test_t is not None:
        interp_t = np.interp(ref_f, test_f, test_t)
        result["max_transmission_abs_err_db"] = float(np.max(np.abs(ref_t - interp_t)))
    return result


def _safe_rel_err(reference: np.ndarray, estimate: np.ndarray, *, floor_ratio: float = 1e-6) -> float:
    scale = max(float(np.max(np.abs(reference))), 1e-30)
    mask = np.abs(reference) > max(1e-12, floor_ratio * scale)
    if not np.any(mask):
        return 0.0
    return float(np.max(np.abs(reference[mask] - estimate[mask]) / np.abs(reference[mask])))


def _median_rel_err(reference: np.ndarray, estimate: np.ndarray, *, floor_ratio: float = 1e-6) -> float:
    scale = max(float(np.max(np.abs(reference))), 1e-30)
    mask = np.abs(reference) > max(1e-12, floor_ratio * scale)
    if not np.any(mask):
        return 0.0
    return float(np.median(np.abs(reference[mask] - estimate[mask]) / np.abs(reference[mask])))


def _compare_structure(
    ref_f: np.ndarray,
    ref_w_left: np.ndarray,
    ref_w_right: np.ndarray,
    test_f: np.ndarray,
    test_w_left: np.ndarray,
    test_w_right: np.ndarray,
) -> dict[str, float]:
    ref_base = _base_displacement_amplitude(ref_f)
    test_base = _base_displacement_amplitude(test_f)
    ref_left_norm = ref_w_left / np.maximum(ref_base, 1e-30)
    ref_right_norm = ref_w_right / np.maximum(ref_base, 1e-30)
    test_left_norm = test_w_left / np.maximum(test_base, 1e-30)
    test_right_norm = test_w_right / np.maximum(test_base, 1e-30)
    interp_left = np.interp(ref_f, test_f, test_left_norm)
    interp_right = np.interp(ref_f, test_f, test_right_norm)
    return {
        "max_left_endpoint_rel_err": float(_safe_rel_err(ref_left_norm, interp_left)),
        "median_left_endpoint_rel_err": float(_median_rel_err(ref_left_norm, interp_left)),
        "max_right_endpoint_rel_err": float(_safe_rel_err(ref_right_norm, interp_right)),
        "median_right_endpoint_rel_err": float(_median_rel_err(ref_right_norm, interp_right)),
    }


def _base_displacement_amplitude(frequency_hz: np.ndarray) -> np.ndarray:
    omega = 2.0 * np.pi * np.asarray(frequency_hz, dtype=float)
    if EXCITATION_TYPE == "acceleration":
        return EXCITATION_AMPLITUDE / np.maximum(omega**2, 1e-30)
    return np.full_like(omega, EXCITATION_AMPLITUDE, dtype=float)


def _plot_raw_results(python_resp, matlab_data, comsol_data) -> None:
    fig, axes = plt.subplots(3, 1, figsize=(10, 10), sharex=True)

    axes[0].plot(python_resp.f, python_resp.voltage, label="Python beam", lw=2)
    if matlab_data is not None:
        axes[0].plot(matlab_data["frequency_hz"], matlab_data["voltage_v"], "--", label="MATLAB beam", lw=1.5)
    if comsol_data is not None and "voltage_v" in comsol_data:
        axes[0].plot(comsol_data["frequency_hz"], comsol_data["voltage_v"], ":", label="COMSOL beam", lw=1.5)
    axes[0].set_ylabel("|V| [V]")
    axes[0].grid(alpha=0.3)
    axes[0].legend()

    axes[1].plot(python_resp.f, python_resp.power, label="Python beam", lw=2)
    if matlab_data is not None:
        axes[1].plot(matlab_data["frequency_hz"], matlab_data["power_w"], "--", label="MATLAB beam", lw=1.5)
    if comsol_data is not None and "power_w" in comsol_data:
        axes[1].plot(comsol_data["frequency_hz"], comsol_data["power_w"], ":", label="COMSOL beam", lw=1.5)
    axes[1].set_ylabel("P_avg [W]")
    axes[1].grid(alpha=0.3)
    axes[1].legend()

    axes[2].plot(python_resp.f, python_resp.transmission_dB, label="Python beam", lw=2)
    if matlab_data is not None:
        axes[2].plot(matlab_data["frequency_hz"], matlab_data["transmission_db"], "--", label="MATLAB beam", lw=1.5)
    if comsol_data is not None and "transmission_db" in comsol_data:
        axes[2].plot(comsol_data["frequency_hz"], comsol_data["transmission_db"], ":", label="COMSOL beam", lw=1.5)
    axes[2].set_ylabel("Transmission [dB]")
    axes[2].set_xlabel("Frequency [Hz]")
    axes[2].grid(alpha=0.3)
    axes[2].legend()

    fig.tight_layout()
    fig.savefig(OUTDIR / "beam_oracle_validation_raw.png", dpi=200)
    fig.savefig(OUTDIR / "beam_oracle_validation.png", dpi=200)


def _plot_trend_results(python_resp, matlab_data, comsol_data) -> None:
    fig, axes = plt.subplots(3, 1, figsize=(10, 10), sharex=True)

    py_mask = python_resp.f >= TREND_F_MIN_HZ
    py_base = _base_displacement_amplitude(python_resp.f[py_mask])
    axes[0].semilogy(python_resp.f[py_mask], np.maximum(python_resp.voltage[py_mask] / py_base, 1e-30), label="Python beam", lw=2)
    axes[1].semilogy(python_resp.f[py_mask], np.maximum(python_resp.power[py_mask] / np.maximum(py_base**2, 1e-30), 1e-30), label="Python beam", lw=2)
    axes[2].plot(python_resp.f[py_mask], python_resp.transmission_dB[py_mask], label="Python beam", lw=2)

    if matlab_data is not None:
        mt_mask = matlab_data["frequency_hz"] >= TREND_F_MIN_HZ
        mt_base = _base_displacement_amplitude(matlab_data["frequency_hz"][mt_mask])
        axes[0].semilogy(matlab_data["frequency_hz"][mt_mask], np.maximum(matlab_data["voltage_v"][mt_mask] / mt_base, 1e-30), "--", label="MATLAB beam", lw=1.5)
        axes[1].semilogy(matlab_data["frequency_hz"][mt_mask], np.maximum(matlab_data["power_w"][mt_mask] / np.maximum(mt_base**2, 1e-30), 1e-30), "--", label="MATLAB beam", lw=1.5)
        axes[2].plot(matlab_data["frequency_hz"][mt_mask], matlab_data["transmission_db"][mt_mask], "--", label="MATLAB beam", lw=1.5)
    if comsol_data is not None:
        cs_mask = comsol_data["frequency_hz"] >= TREND_F_MIN_HZ
        cs_base = _base_displacement_amplitude(comsol_data["frequency_hz"][cs_mask])
        axes[0].semilogy(comsol_data["frequency_hz"][cs_mask], np.maximum(comsol_data["voltage_v"][cs_mask] / cs_base, 1e-30), ":", label="COMSOL beam", lw=1.5)
        axes[1].semilogy(comsol_data["frequency_hz"][cs_mask], np.maximum(comsol_data["power_w"][cs_mask] / np.maximum(cs_base**2, 1e-30), 1e-30), ":", label="COMSOL beam", lw=1.5)
        if "transmission_db" in comsol_data:
            axes[2].plot(comsol_data["frequency_hz"][cs_mask], comsol_data["transmission_db"][cs_mask], ":", label="COMSOL beam", lw=1.5)

    axes[0].set_ylabel("|V| / |u_base| [V/m]")
    axes[1].set_ylabel("P_avg / |u_base|^2 [W/m^2]")
    axes[2].set_ylabel("Transmission [dB]")
    axes[2].set_xlabel("Frequency [Hz]")
    for axis in axes:
        axis.grid(alpha=0.3)
        axis.legend()

    fig.tight_layout()
    fig.savefig(OUTDIR / "beam_oracle_validation_trend.png", dpi=200)


def _plot_structure_results(python_resp, matlab_data, comsol_data) -> None:
    fig, axes = plt.subplots(3, 1, figsize=(10, 10), sharex=True)

    py_base = _base_displacement_amplitude(python_resp.f)
    axes[0].semilogy(python_resp.f, np.maximum(python_resp.w_left / py_base, 1e-30), label="Python beam", lw=2)
    axes[1].semilogy(python_resp.f, np.maximum(python_resp.w_right / py_base, 1e-30), label="Python beam", lw=2)
    axes[2].plot(python_resp.f, python_resp.transmission_dB, label="Python beam", lw=2)

    if matlab_data is not None and "w_left_m" in matlab_data and "w_right_m" in matlab_data:
        mt_base = _base_displacement_amplitude(matlab_data["frequency_hz"])
        axes[0].semilogy(matlab_data["frequency_hz"], np.maximum(matlab_data["w_left_m"] / mt_base, 1e-30), "--", label="MATLAB beam", lw=1.5)
        axes[1].semilogy(matlab_data["frequency_hz"], np.maximum(matlab_data["w_right_m"] / mt_base, 1e-30), "--", label="MATLAB beam", lw=1.5)
        axes[2].plot(matlab_data["frequency_hz"], matlab_data["transmission_db"], "--", label="MATLAB beam", lw=1.5)
    if comsol_data is not None and "w_left_m" in comsol_data and "w_right_m" in comsol_data:
        cs_base = _base_displacement_amplitude(comsol_data["frequency_hz"])
        axes[0].semilogy(comsol_data["frequency_hz"], np.maximum(comsol_data["w_left_m"] / cs_base, 1e-30), ":", label="COMSOL beam", lw=1.5)
        axes[1].semilogy(comsol_data["frequency_hz"], np.maximum(comsol_data["w_right_m"] / cs_base, 1e-30), ":", label="COMSOL beam", lw=1.5)
        axes[2].plot(comsol_data["frequency_hz"], comsol_data["transmission_db"], ":", label="COMSOL beam", lw=1.5)

    axes[0].set_ylabel("|w_L| / |u_base| [-]")
    axes[1].set_ylabel("|w_R| / |u_base| [-]")
    axes[2].set_ylabel("Transmission [dB]")
    axes[2].set_xlabel("Frequency [Hz]")
    for axis in axes:
        axis.grid(alpha=0.3)
        axis.legend()

    fig.tight_layout()
    fig.savefig(OUTDIR / "beam_oracle_validation_structure.png", dpi=200)


if __name__ == "__main__":
    summary = run_validation(include_matlab=True, include_comsol=True)
    print(json.dumps(summary, indent=2))
