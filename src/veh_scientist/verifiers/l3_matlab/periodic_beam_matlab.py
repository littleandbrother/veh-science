"""MATLAB reference wrapper for the continuous periodic beam model."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

import numpy as np


@dataclass(frozen=True)
class PeriodicBeamMatlabConfig:
    """Inputs for the MATLAB continuous-beam validation script."""

    beam_width: float = 0.025
    beam_height: float = 0.005
    L_A: float = 0.08
    L_B: float = 0.02
    n_cells: int = 20
    piezo_thickness: float = 0.0005
    load_resistance_ohm: float = 1.0e6
    f_min_hz: float = 1.0
    f_max_hz: float = 3000.0
    n_freq: int = 120
    excitation_type: str = "acceleration"
    excitation_amplitude: float = 9.81
    boundary_mass_factor: float = 1.0

    E_A: float = 68.9e9
    rho_A: float = 2700.0
    nu_A: float = 0.33
    E_B: float = 2.4e9
    rho_B: float = 1040.0
    nu_B: float = 0.35
    piezo_E: float = 62.0e9
    piezo_rho: float = 7500.0
    piezo_d31: float = -274e-12
    piezo_eps33T: float = 3400.0 * 8.854e-12
    zeta1: float = 0.005
    zeta2: float = 0.008
    tan_delta: float = 0.02


def run_periodic_beam_matlab(
    config: PeriodicBeamMatlabConfig,
    *,
    matlab_bin: str | None = None,
) -> dict:
    """Execute the MATLAB reference model and return JSON-decoded results."""
    script_dir = Path(__file__).resolve().parents[4] / "scripts"
    runner = script_dir / "veh_scientist_periodic_beam_runner.m"
    if not runner.exists():
        raise FileNotFoundError(f"MATLAB runner not found: {runner}")

    matlab_exe = _resolve_matlab_binary(matlab_bin)
    if matlab_exe is None:
        raise FileNotFoundError("MATLAB executable not found.")

    with tempfile.TemporaryDirectory(prefix="veh_matlab_") as tmpdir:
        input_path = Path(tmpdir) / "input.json"
        output_path = Path(tmpdir) / "output.json"
        input_path.write_text(json.dumps(asdict(config)), encoding="utf-8")

        batch_cmd = (
            f"addpath('{script_dir.as_posix()}'); "
            f"veh_scientist_periodic_beam_runner('{input_path.as_posix()}', '{output_path.as_posix()}');"
        )
        completed = subprocess.run(
            [matlab_exe, "-batch", batch_cmd],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "MATLAB beam reference failed.\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            )
        if not output_path.exists():
            raise RuntimeError("MATLAB beam reference finished without producing output JSON.")

        result = json.loads(output_path.read_text(encoding="utf-8"))

    for key in ("frequency_hz", "voltage_v", "power_w", "w_left_m", "w_right_m", "transmission_db"):
        if key in result:
            result[key] = np.asarray(result[key], dtype=float)
    return result


def _resolve_matlab_binary(matlab_bin: str | None) -> str | None:
    if matlab_bin:
        return matlab_bin

    bundled = Path("/Applications/MATLAB_R2024b.app/bin/matlab")
    if bundled.exists():
        return str(bundled)

    found = shutil.which("matlab")
    return found
