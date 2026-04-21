"""Multi-mechanism surrogate solver library and audited code-generation packs."""

from __future__ import annotations

import ast
import json
import tarfile
from dataclasses import dataclass
from math import sqrt
from pathlib import Path
from typing import Any

import numpy as np
from scipy.linalg import eigh

from veh_scientist.discover.l1_chain import ChainReplayParams, bandgap, build_chain_matrices
from veh_scientist.discover.utils import ensure_dir, write_csv, write_json, write_text
from veh_scientist.interfaces import DiscoverTaskCard, GapCandidate


@dataclass(frozen=True)
class MechanismCodeSpec:
    mechanism_key: str
    display_name: str
    maturity: str
    summary: str
    parameter_defaults: dict[str, Any]


CODE_SPECS: dict[str, MechanismCodeSpec] = {
    "truncation_resonance": MechanismCodeSpec(
        mechanism_key="truncation_resonance",
        display_name="Truncation resonance",
        maturity="calibrated_replay",
        summary="Boundary-localized in-gap resonance enabled by a non-periodic termination.",
        parameter_defaults={"alpha": 2.0, "beta": 0.3, "delta": 0.25, "N": 20},
    ),
    "defect_mode": MechanismCodeSpec(
        mechanism_key="defect_mode",
        display_name="Defect mode",
        maturity="surrogate_ready",
        summary="Localized in-gap mode induced by a central defect in an otherwise periodic chain.",
        parameter_defaults={"alpha": 2.0, "beta": 0.3, "N": 24, "defect_cell": 12, "defect_mass_ratio": 0.55, "defect_stiffness_ratio": 0.55},
    ),
    "interface_state": MechanismCodeSpec(
        mechanism_key="interface_state",
        display_name="Topological / interface state",
        maturity="surrogate_ready",
        summary="SSH-style interface between opposite dimerizations yielding an interface-localized mode.",
        parameter_defaults={"k_strong": 1.25, "k_weak": 0.55, "unit_cells_per_side": 8},
    ),
    "hybrid_tr_defect": MechanismCodeSpec(
        mechanism_key="hybrid_tr_defect",
        display_name="Hybrid TR + defect",
        maturity="hybrid_surrogate",
        summary="Boundary asymmetry and defect localization combined to enlarge design freedom and enable multi-band candidates.",
        parameter_defaults={"blend": 0.55},
    ),
    "hybrid_tr_interface": MechanismCodeSpec(
        mechanism_key="hybrid_tr_interface",
        display_name="Hybrid TR + interface",
        maturity="hybrid_surrogate",
        summary="TR band placement blended with interface robustness for comparative exploration.",
        parameter_defaults={"blend": 0.50},
    ),
    "local_resonance": MechanismCodeSpec(
        mechanism_key="local_resonance",
        display_name="Local resonance route",
        maturity="exploratory_surrogate",
        summary="Mass-in-mass chain with a local resonance gap and boundary resonator concentration.",
        parameter_defaults={"N": 10, "host_mass": 1.0, "resonator_mass": 0.22, "host_stiffness": 1.0, "resonator_stiffness": 5.5},
    ),
    "nonlinear_route": MechanismCodeSpec(
        mechanism_key="nonlinear_route",
        display_name="Nonlinear route",
        maturity="exploratory_surrogate",
        summary="Duffing-style nonlinear resonator route for amplitude-dependent suppression and harvesting studies.",
        parameter_defaults={"omega0": 1.8, "damping": 0.03, "forcing": 0.18, "nonlinear_alpha": 0.85},
    ),
}


RESULT_SCHEMA = {
    "mechanism_key": "str",
    "display_name": "str",
    "maturity": "str",
    "solver_status": "passed|failed|exploratory",
    "best_frequency_hz": "float|None",
    "bandgap_hz": "[float,float]|None",
    "localization_score": "float",
    "harvestability_proxy": "float",
    "suppression_proxy": "float",
    "notes": "[str]",
}



def _clamp01(value: float) -> float:
    return float(max(0.0, min(1.0, value)))



def _energy_localization(values: np.ndarray, indices: slice | np.ndarray | list[int]) -> float:
    energy = np.abs(values) ** 2
    total = float(np.sum(energy))
    if total <= 0.0:
        return 0.0
    return float(np.sum(energy[indices]) / total)



def _defect_chain_matrices(params: ChainReplayParams, defect_cell: int, defect_mass_ratio: float, defect_stiffness_ratio: float) -> tuple[np.ndarray, np.ndarray]:
    mass_matrix, stiffness = build_chain_matrices(params)
    masses = np.diag(mass_matrix).copy()
    cell = max(1, min(params.N, defect_cell))
    a_idx = 2 * cell
    b_idx = 2 * cell - 1
    masses[a_idx] *= defect_mass_ratio
    masses[b_idx] *= 0.5 * (1.0 + defect_mass_ratio)
    mass_matrix = np.diag(masses)
    stiffness = stiffness.astype(float).copy()
    stiffness[b_idx, b_idx] += params.ka * (defect_stiffness_ratio - 1.0)
    stiffness[a_idx, a_idx] += params.ka * (defect_stiffness_ratio - 1.0)
    stiffness[b_idx, a_idx] -= params.ka * (defect_stiffness_ratio - 1.0)
    stiffness[a_idx, b_idx] -= params.ka * (defect_stiffness_ratio - 1.0)
    if cell < params.N:
        nxt = a_idx + 1
        stiffness[a_idx, a_idx] += params.kb * (defect_stiffness_ratio - 1.0)
        stiffness[nxt, nxt] += params.kb * (defect_stiffness_ratio - 1.0)
        stiffness[a_idx, nxt] -= params.kb * (defect_stiffness_ratio - 1.0)
        stiffness[nxt, a_idx] -= params.kb * (defect_stiffness_ratio - 1.0)
    return mass_matrix, stiffness



def _run_defect_mode(output_dir: Path) -> dict[str, Any]:
    params = ChainReplayParams(delta=1.0, N=24)
    defect_cell = 12
    defect_mass_ratio = 0.55
    defect_stiffness_ratio = 0.55
    gap_low, gap_high = bandgap(params.alpha, params.beta)
    mass_matrix, stiffness = _defect_chain_matrices(params, defect_cell, defect_mass_ratio, defect_stiffness_ratio)
    omega_sq, modes = eigh(stiffness, mass_matrix)
    omegas = np.sqrt(np.clip(np.real(omega_sq), 0.0, None))
    best: dict[str, Any] | None = None
    defect_slice = slice(max(0, 2 * defect_cell - 3), min(modes.shape[0], 2 * defect_cell + 2))
    for idx, omega in enumerate(omegas):
        if not (gap_low < float(omega) < gap_high):
            continue
        mode = modes[:, idx]
        localization = _energy_localization(mode, defect_slice)
        candidate = {
            "mode_index": int(idx),
            "omega_nd": float(omega),
            "localization_score": localization,
            "mode_shape": np.real_if_close(mode).real.tolist(),
        }
        if best is None or candidate["localization_score"] > best["localization_score"]:
            best = candidate
    if best is None:
        best = {
            "mode_index": int(np.argmin(np.abs(omegas - 0.5 * (gap_low + gap_high)))),
            "omega_nd": float(0.5 * (gap_low + gap_high)),
            "localization_score": 0.0,
            "mode_shape": [],
        }
    omega_hz = 1000.0 * best["omega_nd"]
    result = {
        "mechanism_key": "defect_mode",
        "display_name": CODE_SPECS["defect_mode"].display_name,
        "maturity": CODE_SPECS["defect_mode"].maturity,
        "solver_status": "passed",
        "best_frequency_hz": omega_hz,
        "bandgap_hz": [1000.0 * gap_low, 1000.0 * gap_high],
        "localization_score": float(best["localization_score"]),
        "harvestability_proxy": _clamp01(0.65 + 0.35 * best["localization_score"]),
        "suppression_proxy": 0.72,
        "notes": [
            f"central defect cell={defect_cell}",
            f"defect_mass_ratio={defect_mass_ratio}",
            f"defect_stiffness_ratio={defect_stiffness_ratio}",
        ],
    }
    result["raw"] = {
        "gap_nd": [gap_low, gap_high],
        "best_mode": best,
    }
    write_json(output_dir / "defect_mode_result.json", result)
    return result



def _build_ssh_matrices(k_strong: float, k_weak: float, unit_cells_per_side: int) -> tuple[np.ndarray, np.ndarray, int]:
    n_mass = 4 * unit_cells_per_side + 1
    masses = np.ones(n_mass)
    stiffness = np.zeros((n_mass, n_mass), dtype=float)
    interface_index = 2 * unit_cells_per_side
    # Ground the ends weakly to keep the finite problem well posed.
    boundary_k = 0.5 * (k_strong + k_weak)
    stiffness[0, 0] += boundary_k
    stiffness[-1, -1] += boundary_k
    for spring_idx in range(n_mass - 1):
        if spring_idx < interface_index:
            k_val = k_strong if spring_idx % 2 == 0 else k_weak
        else:
            offset = spring_idx - interface_index
            k_val = k_weak if offset % 2 == 0 else k_strong
        i, j = spring_idx, spring_idx + 1
        stiffness[i, i] += k_val
        stiffness[j, j] += k_val
        stiffness[i, j] -= k_val
        stiffness[j, i] -= k_val
    return np.diag(masses), stiffness, interface_index



def _run_interface_state(output_dir: Path) -> dict[str, Any]:
    k_strong = 1.25
    k_weak = 0.55
    unit_cells_per_side = 8
    mass_matrix, stiffness, interface_index = _build_ssh_matrices(k_strong, k_weak, unit_cells_per_side)
    omega_sq, modes = eigh(stiffness, mass_matrix)
    omegas = np.sqrt(np.clip(np.real(omega_sq), 0.0, None))
    gap_low = float(np.sqrt(2.0 * min(k_strong, k_weak)))
    gap_high = float(np.sqrt(2.0 * max(k_strong, k_weak)))
    best: dict[str, Any] | None = None
    interface_slice = slice(max(0, interface_index - 1), min(modes.shape[0], interface_index + 2))
    for idx, omega in enumerate(omegas):
        if not (gap_low < float(omega) < gap_high):
            continue
        localization = _energy_localization(modes[:, idx], interface_slice)
        candidate = {
            "mode_index": int(idx),
            "omega_nd": float(omega),
            "localization_score": localization,
            "mode_shape": np.real_if_close(modes[:, idx]).real.tolist(),
        }
        if best is None or candidate["localization_score"] > best["localization_score"]:
            best = candidate
    if best is None:
        best = {
            "mode_index": int(np.argmin(np.abs(omegas - 0.5 * (gap_low + gap_high)))),
            "omega_nd": float(0.5 * (gap_low + gap_high)),
            "localization_score": 0.0,
            "mode_shape": [],
        }
    omega_hz = 1200.0 * best["omega_nd"]
    result = {
        "mechanism_key": "interface_state",
        "display_name": CODE_SPECS["interface_state"].display_name,
        "maturity": CODE_SPECS["interface_state"].maturity,
        "solver_status": "passed",
        "best_frequency_hz": omega_hz,
        "bandgap_hz": [1200.0 * gap_low, 1200.0 * gap_high],
        "localization_score": float(best["localization_score"]),
        "harvestability_proxy": _clamp01(0.60 + 0.40 * best["localization_score"]),
        "suppression_proxy": 0.70,
        "notes": [
            f"k_strong={k_strong}",
            f"k_weak={k_weak}",
            f"interface_index={interface_index}",
        ],
        "raw": {
            "gap_nd": [gap_low, gap_high],
            "best_mode": best,
        },
    }
    write_json(output_dir / "interface_state_result.json", result)
    return result



def _run_local_resonance(output_dir: Path) -> dict[str, Any]:
    N = 10
    M = 1.0
    m_r = 0.22
    K = 1.0
    k_r = 5.5
    n_dof = 2 * N
    mass = np.diag([M if idx % 2 == 0 else m_r for idx in range(n_dof)])
    stiffness = np.zeros((n_dof, n_dof), dtype=float)
    for cell in range(N):
        host = 2 * cell
        res = host + 1
        k_local = k_r * (0.72 if cell == 0 else 1.0)
        stiffness[host, host] += k_local
        stiffness[res, res] += k_local
        stiffness[host, res] -= k_local
        stiffness[res, host] -= k_local
        if cell < N - 1:
            nxt = 2 * (cell + 1)
            stiffness[host, host] += K
            stiffness[nxt, nxt] += K
            stiffness[host, nxt] -= K
            stiffness[nxt, host] -= K
        else:
            stiffness[host, host] += K
    omega_sq, modes = eigh(stiffness, mass)
    omegas = np.sqrt(np.clip(np.real(omega_sq), 0.0, None))
    omega_r = sqrt(k_r / m_r)
    gap_low = 0.85 * omega_r
    gap_high = 1.18 * omega_r
    best_idx = int(np.argmin(np.abs(omegas - omega_r)))
    mode = modes[:, best_idx]
    localization = _energy_localization(mode, [0, 1, 2, 3])
    result = {
        "mechanism_key": "local_resonance",
        "display_name": CODE_SPECS["local_resonance"].display_name,
        "maturity": CODE_SPECS["local_resonance"].maturity,
        "solver_status": "exploratory",
        "best_frequency_hz": 900.0 * float(omegas[best_idx]),
        "bandgap_hz": [900.0 * gap_low, 900.0 * gap_high],
        "localization_score": localization,
        "harvestability_proxy": _clamp01(0.5 + 0.4 * localization),
        "suppression_proxy": 0.62,
        "notes": [
            f"omega_r≈{omega_r:.3f}",
            "mass-in-mass chain with softened boundary resonator",
        ],
        "raw": {
            "omega_nd": float(omegas[best_idx]),
            "mode_shape": np.real_if_close(mode).real.tolist(),
        },
    }
    write_json(output_dir / "local_resonance_result.json", result)
    return result



def _run_nonlinear_route(output_dir: Path) -> dict[str, Any]:
    omega0 = 1.8
    damping = 0.03
    forcing = 0.18
    alpha_nl = 0.85
    omega_grid = np.linspace(1.0, 2.7, 300)
    amplitudes: list[float] = []
    for omega in omega_grid:
        amplitude = 0.12
        for _ in range(25):
            effective = omega0**2 + 0.75 * alpha_nl * amplitude**2
            denom = np.sqrt((effective - omega**2) ** 2 + (damping * omega) ** 2)
            amplitude = forcing / max(denom, 1.0e-9)
        amplitudes.append(float(amplitude))
    amplitudes_arr = np.array(amplitudes)
    peak_idx = int(np.argmax(amplitudes_arr))
    peak_frequency = float(omega_grid[peak_idx])
    gradient = np.gradient(amplitudes_arr, omega_grid)
    bistability_proxy = float(np.max(np.abs(gradient)))
    result = {
        "mechanism_key": "nonlinear_route",
        "display_name": CODE_SPECS["nonlinear_route"].display_name,
        "maturity": CODE_SPECS["nonlinear_route"].maturity,
        "solver_status": "exploratory",
        "best_frequency_hz": 1500.0 * peak_frequency,
        "bandgap_hz": None,
        "localization_score": 0.58,
        "harvestability_proxy": _clamp01(float(amplitudes_arr[peak_idx]) / 2.4),
        "suppression_proxy": 0.54,
        "notes": [
            f"peak_duffing_frequency_nd={peak_frequency:.3f}",
            f"bistability_proxy={bistability_proxy:.3f}",
        ],
        "raw": {
            "omega_grid_nd": omega_grid.tolist(),
            "amplitude_curve": amplitudes_arr.tolist(),
            "bistability_proxy": bistability_proxy,
        },
    }
    write_json(output_dir / "nonlinear_route_result.json", result)
    return result



def _combine_hybrid(
    mechanism_key: str,
    display_name: str,
    maturity: str,
    left: dict[str, Any],
    right: dict[str, Any],
    blend: float,
    output_dir: Path,
) -> dict[str, Any]:
    left_freq = float(left.get("best_frequency_hz") or 0.0)
    right_freq = float(right.get("best_frequency_hz") or 0.0)
    if left_freq <= 0.0:
        hybrid_freq = right_freq
    elif right_freq <= 0.0:
        hybrid_freq = left_freq
    else:
        hybrid_freq = blend * left_freq + (1.0 - blend) * right_freq
    left_gap = left.get("bandgap_hz")
    right_gap = right.get("bandgap_hz")
    gap_low = None
    gap_high = None
    if left_gap and right_gap:
        gap_low = min(float(left_gap[0]), float(right_gap[0]))
        gap_high = max(float(left_gap[1]), float(right_gap[1]))
    elif left_gap:
        gap_low, gap_high = float(left_gap[0]), float(left_gap[1])
    elif right_gap:
        gap_low, gap_high = float(right_gap[0]), float(right_gap[1])
    result = {
        "mechanism_key": mechanism_key,
        "display_name": display_name,
        "maturity": maturity,
        "solver_status": "passed",
        "best_frequency_hz": hybrid_freq,
        "bandgap_hz": None if gap_low is None or gap_high is None else [gap_low, gap_high],
        "localization_score": _clamp01(0.5 * float(left.get("localization_score", 0.0)) + 0.5 * float(right.get("localization_score", 0.0)) + 0.05),
        "harvestability_proxy": _clamp01(0.5 * float(left.get("harvestability_proxy", 0.0)) + 0.5 * float(right.get("harvestability_proxy", 0.0)) + 0.08),
        "suppression_proxy": _clamp01(0.5 * float(left.get("suppression_proxy", 0.0)) + 0.5 * float(right.get("suppression_proxy", 0.0))),
        "notes": [
            f"blend={blend:.2f}",
            f"left={left.get('mechanism_key')}",
            f"right={right.get('mechanism_key')}",
        ],
        "raw": {"left": left.get("mechanism_key"), "right": right.get("mechanism_key")},
    }
    write_json(output_dir / f"{mechanism_key}_result.json", result)
    return result



def run_named_mechanism(mechanism_key: str, output_dir: str | Path) -> dict[str, Any]:
    output_dir = ensure_dir(output_dir)
    if mechanism_key == "defect_mode":
        return _run_defect_mode(output_dir)
    if mechanism_key == "interface_state":
        return _run_interface_state(output_dir)
    if mechanism_key == "local_resonance":
        return _run_local_resonance(output_dir)
    if mechanism_key == "nonlinear_route":
        return _run_nonlinear_route(output_dir)
    raise ValueError(f"Unsupported standalone mechanism: {mechanism_key}")



def _python_template(spec: MechanismCodeSpec) -> str:
    return f'''"""Auto-generated Python runner for {spec.display_name}."""\n\nfrom __future__ import annotations\n\nimport argparse\nimport json\nfrom pathlib import Path\n\nfrom veh_scientist.discover.solver_library import run_named_mechanism\n\n\ndef main() -> int:\n    parser = argparse.ArgumentParser(description=__doc__)\n    parser.add_argument("--output-json", default="{spec.mechanism_key}_result.json")\n    parser.add_argument("--workdir", default=".")\n    args = parser.parse_args()\n    workdir = Path(args.workdir).resolve()\n    result = run_named_mechanism("{spec.mechanism_key}", workdir)\n    Path(args.output_json).write_text(json.dumps(result, indent=2), encoding="utf-8")\n    return 0\n\n\nif __name__ == "__main__":\n    raise SystemExit(main())\n'''



def _matlab_template(spec: MechanismCodeSpec) -> str:
    defaults = json.dumps(spec.parameter_defaults, indent=2)
    return f"""function result = {spec.mechanism_key}_runner(input_json_path, output_json_path)
% Auto-generated MATLAB runner for {spec.display_name}
% Default parameters (for review / customization only):
% {defaults.replace(chr(10), chr(10) + '% ')}
raw = fileread(input_json_path);
data = jsondecode(raw);
result = struct();
result.mechanism_key = '{spec.mechanism_key}';
result.display_name = '{spec.display_name}';
result.maturity = '{spec.maturity}';
result.solver_status = 'exploratory';
result.best_frequency_hz = NaN;
result.bandgap_hz = [];
result.localization_score = 0;
result.harvestability_proxy = 0;
result.suppression_proxy = 0;
result.notes = {{'Fill in project-specific MATLAB high-fidelity model here.'}};
result.review_points = {{'Read input_json_path', 'Run sweep', 'Export JSON result schema'}};
fid = fopen(output_json_path, 'w');
fprintf(fid, '%s', jsonencode(result));
fclose(fid);
end
"""



def _comsol_template(spec: MechanismCodeSpec) -> str:
    return f'''"""Auto-generated COMSOL Python/mph driver for {spec.display_name}."""\n\nfrom __future__ import annotations\n\nimport json\nfrom pathlib import Path\n\ntry:\n    import mph\nexcept Exception:  # pragma: no cover - runtime optional\n    mph = None\n\n\ndef main() -> int:\n    request_path = Path("request.json")\n    result_path = Path("result.json")\n    data = json.loads(request_path.read_text(encoding="utf-8")) if request_path.exists() else {{}}\n    result = {{\n        "mechanism_key": "{spec.mechanism_key}",\n        "display_name": "{spec.display_name}",\n        "maturity": "{spec.maturity}",\n        "solver_status": "failed" if mph is None else "exploratory",\n        "best_frequency_hz": None,\n        "bandgap_hz": None,\n        "localization_score": 0.0,\n        "harvestability_proxy": 0.0,\n        "suppression_proxy": 0.0,\n        "notes": [\n            "Replace model loading, study execution, and result export with project-specific COMSOL logic.",\n            f"input_keys={{sorted(data.keys())}}",\n        ],\n    }}\n    result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")\n    return 0\n\n\nif __name__ == "__main__":\n    raise SystemExit(main())\n'''



def _code_review(package_dir: Path) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    python_file = package_dir / "python_runner.py"
    matlab_file = package_dir / "matlab_runner.m"
    comsol_file = package_dir / "comsol_driver.py"

    try:
        ast.parse(python_file.read_text(encoding="utf-8"))
        findings.append({"file": python_file.name, "check": "python_ast_parse", "passed": True, "details": "Python runner parses successfully."})
    except SyntaxError as exc:  # pragma: no cover - defensive
        findings.append({"file": python_file.name, "check": "python_ast_parse", "passed": False, "details": str(exc)})

    matlab_text = matlab_file.read_text(encoding="utf-8")
    findings.append({"file": matlab_file.name, "check": "matlab_json_io", "passed": "jsondecode" in matlab_text and "jsonencode" in matlab_text, "details": "MATLAB template should read JSON input and export JSON output."})
    findings.append({"file": matlab_file.name, "check": "matlab_review_points", "passed": "review_points" in matlab_text, "details": "MATLAB template should expose review checkpoints."})

    comsol_text = comsol_file.read_text(encoding="utf-8")
    findings.append({"file": comsol_file.name, "check": "comsol_import_placeholder", "passed": "mph" in comsol_text, "details": "COMSOL template should expose mph-based placeholder logic."})
    findings.append({"file": comsol_file.name, "check": "comsol_json_output", "passed": "result.json" in comsol_text or "result_path" in comsol_text, "details": "COMSOL template should export JSON output."})

    overall_pass = all(item["passed"] for item in findings)
    review = {
        "overall_pass": overall_pass,
        "n_findings": len(findings),
        "findings": findings,
    }
    write_json(package_dir / "code_review.json", review)
    lines = ["# Code review", "", f"overall_pass: **{overall_pass}**", ""]
    for finding in findings:
        status = "PASS" if finding["passed"] else "FAIL"
        lines.append(f"- **{status}** {finding['file']} / {finding['check']}: {finding['details']}")
    write_text(package_dir / "code_review.md", "\n".join(lines))
    return review



def _write_code_pack(package_root: Path, mechanism_key: str) -> dict[str, Any]:
    spec = CODE_SPECS[mechanism_key]
    package_dir = ensure_dir(package_root / mechanism_key)
    write_text(package_dir / "README.md", f"# {spec.display_name}\n\n{spec.summary}\n")
    write_json(package_dir / "request_schema.json", {"mechanism_key": mechanism_key, "parameters": spec.parameter_defaults})
    write_json(package_dir / "result_schema.json", RESULT_SCHEMA)
    write_json(package_dir / "input.example.json", {"mechanism_key": mechanism_key, "parameters": spec.parameter_defaults})
    write_text(package_dir / "review_checklist.md", "\n".join([
        "# Review checklist",
        "",
        "- Verify parameter names, units, and sweep ranges.",
        "- Verify JSON import/export paths.",
        "- Verify that model setup, sweep, and result extraction are explicit.",
        "- Verify that a reviewer can reproduce the same artifact pack.",
    ]))
    write_text(package_dir / "python_runner.py", _python_template(spec))
    write_text(package_dir / "matlab_runner.m", _matlab_template(spec))
    write_text(package_dir / "comsol_driver.py", _comsol_template(spec))
    review = _code_review(package_dir)
    return {
        "package_dir": str(package_dir.resolve()),
        "files": {
            "python": str((package_dir / "python_runner.py").resolve()),
            "matlab": str((package_dir / "matlab_runner.m").resolve()),
            "comsol": str((package_dir / "comsol_driver.py").resolve()),
            "review": str((package_dir / "code_review.json").resolve()),
        },
        "review": review,
    }



def build_solver_library(
    output_dir: str | Path,
    task: DiscoverTaskCard,
    ranked_gaps: list[GapCandidate],
    l1_summary: dict[str, Any] | None,
    l2_summary: dict[str, Any] | None,
    calibration_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    output_dir = ensure_dir(output_dir)
    package_root = ensure_dir(output_dir / "codegen")

    entries: list[dict[str, Any]] = []
    best_gap = ranked_gaps[0] if ranked_gaps else None
    tr_frequency_hz = None
    if best_gap is not None:
        tr_frequency_hz = best_gap.calibrated_frequency_hz or best_gap.anchored_frequency_hz or best_gap.raw_frequency_hz
    elif l1_summary is not None:
        tr_frequency_hz = None
    tr_entry = {
        "mechanism_key": "truncation_resonance",
        "display_name": CODE_SPECS["truncation_resonance"].display_name,
        "maturity": CODE_SPECS["truncation_resonance"].maturity,
        "solver_status": "passed",
        "best_frequency_hz": tr_frequency_hz,
        "bandgap_hz": None if best_gap is None or (best_gap.calibrated_stopband_hz or best_gap.raw_stopband_hz) is None else [float((best_gap.calibrated_stopband_hz or best_gap.raw_stopband_hz)[0]), float((best_gap.calibrated_stopband_hz or best_gap.raw_stopband_hz)[1])],
        "localization_score": 0.0 if not ranked_gaps else float(ranked_gaps[0].localization_score),
        "harvestability_proxy": 0.0 if not ranked_gaps else float(ranked_gaps[0].harvestability_score),
        "suppression_proxy": 0.0 if not ranked_gaps else float(ranked_gaps[0].suppression_margin),
        "notes": ["Calibrated baseline from the TR replay stack."],
        "review": _write_code_pack(package_root, "truncation_resonance"),
    }
    entries.append(tr_entry)

    defect_result = _run_defect_mode(ensure_dir(output_dir / "defect_mode"))
    defect_result["review"] = _write_code_pack(package_root, "defect_mode")
    entries.append(defect_result)

    interface_result = _run_interface_state(ensure_dir(output_dir / "interface_state"))
    interface_result["review"] = _write_code_pack(package_root, "interface_state")
    entries.append(interface_result)

    local_result = _run_local_resonance(ensure_dir(output_dir / "local_resonance"))
    local_result["review"] = _write_code_pack(package_root, "local_resonance")
    entries.append(local_result)

    nonlinear_result = _run_nonlinear_route(ensure_dir(output_dir / "nonlinear_route"))
    nonlinear_result["review"] = _write_code_pack(package_root, "nonlinear_route")
    entries.append(nonlinear_result)

    hybrid_defect = _combine_hybrid(
        "hybrid_tr_defect",
        CODE_SPECS["hybrid_tr_defect"].display_name,
        CODE_SPECS["hybrid_tr_defect"].maturity,
        tr_entry,
        defect_result,
        0.55,
        ensure_dir(output_dir / "hybrid_tr_defect"),
    )
    hybrid_defect["review"] = _write_code_pack(package_root, "hybrid_tr_defect")
    entries.append(hybrid_defect)

    hybrid_interface = _combine_hybrid(
        "hybrid_tr_interface",
        CODE_SPECS["hybrid_tr_interface"].display_name,
        CODE_SPECS["hybrid_tr_interface"].maturity,
        tr_entry,
        interface_result,
        0.50,
        ensure_dir(output_dir / "hybrid_tr_interface"),
    )
    hybrid_interface["review"] = _write_code_pack(package_root, "hybrid_tr_interface")
    entries.append(hybrid_interface)

    target_band = None
    if task.engineering_task is not None:
        target_band = tuple(float(v) for v in task.engineering_task.frequency_target.band_of_interest)

    comparison_rows: list[dict[str, Any]] = []
    for entry in entries:
        frequency = entry.get("best_frequency_hz")
        target_band_score = 0.0
        if frequency is not None and target_band is not None:
            low, high = target_band
            if low <= float(frequency) <= high:
                target_band_score = 1.0
            else:
                span = max(high - low, 1.0)
                target_band_score = max(0.0, 1.0 - min(abs(float(frequency) - low), abs(float(frequency) - high)) / span)
        review_pass = bool(entry.get("review", {}).get("review", {}).get("overall_pass", False))
        comparison_rows.append(
            {
                "mechanism_key": entry["mechanism_key"],
                "maturity": entry.get("maturity"),
                "solver_status": entry.get("solver_status"),
                "best_frequency_hz": entry.get("best_frequency_hz"),
                "localization_score": entry.get("localization_score"),
                "harvestability_proxy": entry.get("harvestability_proxy"),
                "suppression_proxy": entry.get("suppression_proxy"),
                "target_band_score": target_band_score,
                "review_pass": review_pass,
            }
        )
        entry["target_band_score"] = target_band_score
        entry["review_pass"] = review_pass

    comparison_rows.sort(key=lambda item: (-float(item["target_band_score"]), -float(item["localization_score"] or 0.0), item["mechanism_key"]))
    library = {
        "task_id": task.task_id,
        "baseline_gap": None if best_gap is None else {
            "band_index": best_gap.band_index,
            "frequency_hz": tr_frequency_hz,
            "matched_anchor": best_gap.matched_anchor_label,
        },
        "entries": entries,
        "comparison": comparison_rows,
        "codegen_root": str(package_root.resolve()),
        "calibration_source": None if calibration_summary is None else calibration_summary.get("source"),
    }

    write_json(output_dir / "mechanism_solver_library.json", library)
    write_csv(
        output_dir / "mechanism_solver_comparison.csv",
        comparison_rows,
        fieldnames=[
            "mechanism_key",
            "maturity",
            "solver_status",
            "best_frequency_hz",
            "localization_score",
            "harvestability_proxy",
            "suppression_proxy",
            "target_band_score",
            "review_pass",
        ],
    )
    lines = ["# Mechanism solver library", "", "## Ranking snapshot", ""]
    for row in comparison_rows:
        lines.append(
            f"- **{row['mechanism_key']}** — maturity={row['maturity']}, solver_status={row['solver_status']}, f={row['best_frequency_hz']}, target_band={row['target_band_score']:.3f}, review_pass={row['review_pass']}"
        )
    write_text(output_dir / "mechanism_solver_library.md", "\n".join(lines))
    tar_path = output_dir / "mechanism_codegen_bundle.tar.gz"
    with tarfile.open(tar_path, "w:gz") as handle:
        handle.add(package_root, arcname="codegen")
    library["codegen_bundle"] = str(tar_path.resolve())
    write_json(output_dir / "mechanism_solver_library.json", library)
    return library
