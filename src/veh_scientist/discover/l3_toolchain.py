"""Structured MATLAB/COMSOL toolchain and L2↔L3 calibration loop."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import socket
import subprocess
import sys
import time
from glob import glob
from pathlib import Path
from typing import Any, TextIO

from veh_scientist.discover.calibration import L3_PROTOCOL_VERSION, run_l2_l3_calibration
from veh_scientist.discover.utils import ensure_dir, repo_root, write_json, write_text
from veh_scientist.interfaces import DiscoverTaskCard, ToolRunRecord


def _first_existing(paths: list[str]) -> str | None:
    for path in paths:
        if path and Path(path).exists():
            return str(Path(path).resolve())
    return None


def _find_matlab_binary() -> str | None:
    env_path = os.environ.get("VEHSCI_MATLAB_BIN")
    if env_path:
        return env_path
    matlab = shutil.which("matlab")
    if matlab:
        return matlab
    matches = sorted(glob("/Applications/MATLAB_R*.app/bin/matlab"), reverse=True)
    return matches[0] if matches else None


def _find_comsol_binary() -> str | None:
    env_path = os.environ.get("VEHSCI_COMSOL_BIN")
    if env_path:
        return env_path
    comsol = shutil.which("comsol")
    if comsol:
        return comsol
    matches = sorted(glob("/Applications/COMSOL*/Multiphysics/bin/comsol"), reverse=True)
    return matches[0] if matches else None


def _python_supports_mph(python_binary: str) -> bool:
    try:
        process = subprocess.run(
            [python_binary, "-c", "import mph"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception:  # noqa: BLE001
        return False
    return process.returncode == 0


def _find_comsol_python() -> str | None:
    candidates: list[str] = []
    env_path = os.environ.get("VEHSCI_COMSOL_PYTHON")
    if env_path:
        candidates.append(env_path)
    root = repo_root()
    candidates.extend(
        [
            str(root / ".venv312" / "bin" / "python"),
            str(root / ".venv" / "bin" / "python"),
            sys.executable,
        ]
    )
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate:
            continue
        resolved = shutil.which(candidate) if Path(candidate).name == candidate else candidate
        if not resolved or resolved in seen or not Path(resolved).exists():
            continue
        seen.add(resolved)
        if _python_supports_mph(resolved):
            return resolved
    return None


def _find_comsol_model() -> str:
    env_path = os.environ.get("VEHSCI_COMSOL_MODEL")
    if env_path:
        return env_path
    root = repo_root()
    model = _first_existing(
        [
            str(root / "results" / "beam_oracle_validation" / "periodic_piezo_beam.mph"),
            str(root / "results" / "phase4" / "periodic_beam.mph"),
            str(root / "results" / "phase4" / "periodic_beam_struct.mph"),
        ]
    )
    return model or ""


def _derive_frequency_sweep(task: DiscoverTaskCard) -> tuple[float, float, float]:
    intervals = [
        tuple(float(v) for v in anchor.stopband_hz)
        for anchor in task.l3_anchors
        if anchor.stopband_hz is not None
    ]
    if intervals:
        start_hz = min(interval[0] for interval in intervals)
        stop_hz = max(interval[1] for interval in intervals)
    elif task.engineering_task is not None:
        start_hz, stop_hz = (float(v) for v in task.engineering_task.frequency_target.band_of_interest)
    else:
        start_hz, stop_hz = 100.0, 10000.0
    span_hz = max(stop_hz - start_hz, 100.0)
    step_hz = max(25.0, round((span_hz / 120.0) / 25.0) * 25.0)
    return float(start_hz), float(stop_hz), float(step_hz)


def _derive_parameter_overrides(task: DiscoverTaskCard) -> dict[str, float]:
    engineering = task.engineering_task
    if engineering is None:
        return {}
    load_value = engineering.harvesting_requirements.load_value
    acceleration = float(engineering.excitation.amplitude)
    if engineering.excitation.amplitude_unit.lower() == "g":
        acceleration *= 9.81
    overrides = {
        "a_exc": float(acceleration),
        "RL_ohm": float(load_value if load_value is not None else 1.0e6),
    }
    return overrides


def _derive_geometry_hints(
    task: DiscoverTaskCard,
    l2_summary: dict[str, Any] | None,
) -> dict[str, float]:
    params = {} if l2_summary is None else dict(l2_summary.get("params", {}))
    cell_pitch_m = params.get("cell_pitch_m")
    layer_split = params.get("layer_split")
    area_b = params.get("area_b")
    inertia_b = params.get("inertia_b")
    hints: dict[str, float] = {}
    if cell_pitch_m is not None:
        hints["cell_pitch_m"] = float(cell_pitch_m)
    if isinstance(layer_split, (list, tuple)) and len(layer_split) == 2 and cell_pitch_m is not None:
        hints["L_A_m"] = float(layer_split[0]) * float(cell_pitch_m)
        hints["L_B_m"] = float(layer_split[1]) * float(cell_pitch_m)
    if area_b is not None and inertia_b is not None and float(area_b) > 0.0 and float(inertia_b) > 0.0:
        height_m = (12.0 * float(inertia_b) / float(area_b)) ** 0.5
        width_m = float(area_b) / max(height_m, 1.0e-12)
        hints["beam_height_m"] = float(height_m)
        hints["beam_width_m"] = float(width_m)
        if task.engineering_task is not None:
            volume = task.engineering_task.envelope_constraints.piezo_volume_m3
            length = task.engineering_task.envelope_constraints.total_length_m
            if volume is not None and length is not None and width_m > 0.0 and length > 0.0:
                hints["piezo_height_m"] = float(volume / (length * width_m))
    return hints


def _reserve_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_tcp_port(host: str, port: int, timeout_s: float = 30.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1.0)
            if sock.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.25)
    return False


def _start_comsol_server(
    comsol_binary: str,
    output_dir: Path,
) -> tuple[subprocess.Popen[str], TextIO, TextIO, int, Path, Path]:
    host = "127.0.0.1"
    port = _reserve_tcp_port()
    stdout_path = output_dir / "comsol_server_stdout.log"
    stderr_path = output_dir / "comsol_server_stderr.log"
    stdout_handle = open(stdout_path, "w", encoding="utf-8", errors="replace")
    stderr_handle = open(stderr_path, "w", encoding="utf-8", errors="replace")
    process = subprocess.Popen(
        [comsol_binary, "mphserver", "-port", str(port)],
        cwd=output_dir,
        stdout=stdout_handle,
        stderr=stderr_handle,
        text=True,
    )
    if not _wait_for_tcp_port(host, port):
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
        stdout_handle.close()
        stderr_handle.close()
        raise RuntimeError(f"COMSOL server failed to bind to {host}:{port}.")
    return process, stdout_handle, stderr_handle, port, stdout_path, stderr_path


def _stop_process(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def _candidate_rows(l2_summary: dict[str, Any] | None) -> list[dict[str, Any]]:
    if l2_summary is None:
        return []
    candidates = [dict(row) for row in l2_summary.get("candidates", [])]
    stopbands_hz = l2_summary.get("stopbands_hz", [])
    for row in candidates:
        band_index = int(row.get("band_index", 0))
        if row.get("raw_frequency_hz") is None and row.get("frequency_hz") is not None:
            row["raw_frequency_hz"] = float(row["frequency_hz"])
        if row.get("raw_stopband_hz") is None and 0 < band_index <= len(stopbands_hz):
            stop = stopbands_hz[band_index - 1]
            row["raw_stopband_hz"] = (
                float(stop.get("frequency_min_hz", 0.0)),
                float(stop.get("frequency_max_hz", 0.0)),
            )
    return candidates


def _anchor_rows(task: DiscoverTaskCard) -> list[dict[str, Any]]:
    return [
        {
            "anchor_id": anchor.anchor_id,
            "label": anchor.label,
            "band_index": anchor.band_index,
            "frequency_hz": float(anchor.frequency_hz),
            "stopband_hz": None if anchor.stopband_hz is None else [float(v) for v in anchor.stopband_hz],
            "target_power_mw": anchor.target_power_mw,
            "target_transmission_db": anchor.target_transmission_db,
            "target_pef": anchor.target_pef,
            "note": anchor.note,
        }
        for anchor in task.l3_anchors
    ]


def build_l3_request(
    task: DiscoverTaskCard,
    l1_summary: dict[str, Any] | None,
    l2_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build the strict request manifest shared by MATLAB and COMSOL backends."""
    candidates = _candidate_rows(l2_summary)
    engineering = task.engineering_task
    sweep_start_hz, sweep_stop_hz, sweep_step_hz = _derive_frequency_sweep(task)
    matlab_binary = _find_matlab_binary() or ""
    comsol_binary = _find_comsol_binary() or ""
    comsol_python = _find_comsol_python() or sys.executable
    comsol_model_path = _find_comsol_model()
    request = {
        "protocol_version": L3_PROTOCOL_VERSION,
        "task_id": task.task_id,
        "mechanism_focus": task.mechanism_focus,
        "research_question": task.research_question,
        "requested_studies": [
            "stopbands",
            "tr_candidates",
            "mode_shapes",
            "harvesting_curves",
            "calibration_pairs",
        ],
        "allowed_tools": list(task.allowed_tools),
        "anchor_targets": _anchor_rows(task),
        "candidate_targets": candidates,
        "n_candidates": len(candidates),
        "l1_summary": l1_summary or {},
        "l2_summary": l2_summary or {},
        "beam_model": {
            "n_cells": None if l2_summary is None else l2_summary.get("params", {}).get("n_cells"),
            "cell_pitch_m": None if l2_summary is None else l2_summary.get("params", {}).get("cell_pitch_m"),
            "layer_split": None if l2_summary is None else l2_summary.get("params", {}).get("layer_split"),
            "boundary_condition": "free_clamped",
            "target_band_hz": None if engineering is None else [float(v) for v in engineering.frequency_target.band_of_interest],
        },
        "electromechanical_model": {
            "kappa2": None if l2_summary is None else l2_summary.get("params", {}).get("piezo_kappa2"),
            "epsilon": None if l2_summary is None else l2_summary.get("params", {}).get("piezo_epsilon"),
            "load_topology": None if engineering is None else engineering.harvesting_requirements.load_topology,
        },
        "expected_outputs": {
            "frequency_pairs": ["band_index", "label", "raw_frequency_hz", "l3_frequency_hz", "source"],
            "stopband_pairs": ["band_index", "label", "raw_stopband_hz", "l3_stopband_hz", "source"],
            "curve_artifacts": ["transmission_curve", "power_curve", "mode_shape"],
        },
        "solver_controls": {
            "frequency_sweep_hz": [sweep_start_hz, sweep_stop_hz],
            "frequency_step_hz": sweep_step_hz,
            "parameter_overrides": _derive_parameter_overrides(task),
            "geometry_hints": _derive_geometry_hints(task, l2_summary),
        },
        "backend_config": {
            "matlab_entrypoint": os.environ.get("VEHSCI_MATLAB_ENTRYPOINT", "veh_l3_validate"),
            "matlab_binary": matlab_binary,
            "comsol_binary": comsol_binary,
            "comsol_python": comsol_python,
            "comsol_model_path": comsol_model_path,
            "comsol_study_tag": os.environ.get("VEHSCI_COMSOL_STUDY", "std_freq"),
            "comsol_dataset_tag": os.environ.get("VEHSCI_COMSOL_DATASET", "dset2"),
        },
    }
    return request


def build_consensus_alignment(calibration_summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    post_rmse = float(calibration_summary.get("errors", {}).get("post_rmse_hz", 0.0) or 0.0)
    for pair in calibration_summary.get("frequency_pairs", []):
        target = float(pair.get("l3_frequency_hz", 0.0))
        rows.append(
            {
                "band_index": int(pair.get("band_index", 0)),
                "raw_frequency_hz": float(pair.get("raw_frequency_hz", 0.0)),
                "anchored_frequency_hz": target,
                "matched_anchor": str(pair.get("label", "")),
                "error_hz": abs(float(pair.get("raw_frequency_hz", 0.0)) - target),
                "score": max(0.0, 1.0 - post_rmse / max(target * 0.35, 500.0)),
            }
        )
    return rows


def write_matlab_driver_script(path: str | Path) -> Path:
    path = Path(path)
    template_path = Path(__file__).with_name("veh_l3_validate_template.m")
    return write_text(path, template_path.read_text(encoding="utf-8"))


def _resolve_matlab_command(
    script_path: Path,
    input_json: Path,
    output_json: Path,
    request: dict[str, Any],
) -> list[str] | None:
    script_path = script_path.resolve()
    input_json = input_json.resolve()
    output_json = output_json.resolve()
    env_command = os.environ.get("VEHSCI_MATLAB_CMD")
    if env_command:
        return shlex.split(
            env_command.format(script=script_path, input=input_json, output=output_json, workdir=script_path.parent)
        )

    matlab = str(request.get("backend_config", {}).get("matlab_binary", "") or _find_matlab_binary() or "")
    if matlab:
        batch = f"addpath('{script_path.parent.as_posix()}');veh_l3_validate('{input_json.as_posix()}','{output_json.as_posix()}');"
        return [matlab, "-batch", batch]
    return None


def _write_failure_output(output_json: Path, engine: str, notes: str) -> dict[str, Any]:
    payload = {
        "protocol_version": L3_PROTOCOL_VERSION,
        "status": "failed",
        "engine": engine,
        "notes": notes,
        "frequency_pairs": [],
        "stopband_pairs": [],
        "anchor_alignment": [],
        "curve_artifacts": {},
    }
    write_json(output_json, payload)
    return payload


def _validate_result_schema(result: dict[str, Any], engine: str) -> dict[str, Any]:
    result = dict(result)
    result.setdefault("protocol_version", L3_PROTOCOL_VERSION)
    result.setdefault("engine", engine)
    result.setdefault("status", "failed")
    result.setdefault("notes", "")
    result.setdefault("frequency_pairs", [])
    result.setdefault("stopband_pairs", [])
    result.setdefault("anchor_alignment", [])
    result.setdefault("curve_artifacts", {})
    return result


def run_matlab_validation(output_dir: str | Path, request: dict[str, Any]) -> tuple[dict[str, Any], ToolRunRecord]:
    output_dir = ensure_dir(output_dir)
    request_path = write_json(output_dir / "matlab_request.json", request)
    script_path = write_matlab_driver_script(output_dir / "veh_l3_validate.m")
    output_json = output_dir / "matlab_result.json"
    stdout_path = output_dir / "matlab_stdout.log"
    stderr_path = output_dir / "matlab_stderr.log"
    command = _resolve_matlab_command(script_path, request_path, output_json, request)

    if command is None:
        result = _write_failure_output(output_json, "matlab", "No MATLAB executable was found. Set VEHSCI_MATLAB_CMD or install MATLAB.")
        run = ToolRunRecord(
            tool="matlab",
            purpose="L3 MATLAB high-fidelity validation",
            status="failed",
            inputs={"request": str(request_path), "script": str(script_path)},
            outputs=result,
            artifact_paths=(str(request_path), str(script_path), str(output_json)),
            notes=result["notes"],
        )
        return result, run

    env = os.environ.copy()
    custom_command = os.environ.get("VEHSCI_MATLAB_CMD")
    comsol_server_process: subprocess.Popen[str] | None = None
    server_stdout_handle: TextIO | None = None
    server_stderr_handle: TextIO | None = None
    server_artifacts: tuple[str, ...] = ()
    try:
        if not env.get("VEHSCI_COMSOL_SERVER_HOST") or not env.get("VEHSCI_COMSOL_SERVER_PORT"):
            if custom_command is None:
                comsol_binary = str(request.get("backend_config", {}).get("comsol_binary", "") or _find_comsol_binary() or "")
                if comsol_binary:
                    (
                        comsol_server_process,
                        server_stdout_handle,
                        server_stderr_handle,
                        server_port,
                        server_stdout_path,
                        server_stderr_path,
                    ) = _start_comsol_server(comsol_binary, output_dir)
                    env["VEHSCI_COMSOL_SERVER_HOST"] = "localhost"
                    env["VEHSCI_COMSOL_SERVER_PORT"] = str(server_port)
                    server_artifacts = (str(server_stdout_path), str(server_stderr_path))
        process = subprocess.run(
            command,
            cwd=output_dir,
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001
        result = _write_failure_output(output_json, "matlab", f"MATLAB LiveLink setup failed: {exc}")
        run = ToolRunRecord(
            tool="matlab",
            purpose="L3 MATLAB high-fidelity validation",
            status="failed",
            inputs={"command": command, "request": str(request_path), "script": str(script_path)},
            outputs=result,
            artifact_paths=(str(request_path), str(script_path), str(output_json), *server_artifacts),
            notes=result["notes"],
        )
        if server_stdout_handle is not None:
            server_stdout_handle.close()
        if server_stderr_handle is not None:
            server_stderr_handle.close()
        _stop_process(comsol_server_process)
        return result, run
    finally:
        if server_stdout_handle is not None:
            server_stdout_handle.flush()
        if server_stderr_handle is not None:
            server_stderr_handle.flush()

    write_text(stdout_path, process.stdout)
    write_text(stderr_path, process.stderr)
    if server_stdout_handle is not None:
        server_stdout_handle.close()
    if server_stderr_handle is not None:
        server_stderr_handle.close()
    _stop_process(comsol_server_process)
    if output_json.exists():
        result = _validate_result_schema(json.loads(output_json.read_text(encoding="utf-8")), "matlab")
    else:
        result = _write_failure_output(output_json, "matlab", process.stderr.strip() or f"MATLAB command exited with code {process.returncode}.")
    status = "passed" if process.returncode == 0 and str(result.get("status", "")).lower() == "passed" else "failed"
    run = ToolRunRecord(
        tool="matlab",
        purpose="L3 MATLAB high-fidelity validation",
        status=status,
        inputs={"command": command, "request": str(request_path), "script": str(script_path)},
        outputs=result,
        artifact_paths=(str(request_path), str(script_path), str(output_json), str(stdout_path), str(stderr_path), *server_artifacts),
        notes=result.get("notes", ""),
    )
    return result, run


def _resolve_comsol_command(input_json: Path, output_json: Path, request: dict[str, Any]) -> list[str]:
    input_json = input_json.resolve()
    output_json = output_json.resolve()
    env_command = os.environ.get("VEHSCI_COMSOL_CMD")
    if env_command:
        return shlex.split(env_command.format(input=input_json, output=output_json, workdir=output_json.parent))
    python_binary = str(request.get("backend_config", {}).get("comsol_python", "") or _find_comsol_python() or sys.executable)
    driver_script = repo_root() / "src" / "veh_scientist" / "discover" / "l3_comsol_driver.py"
    return [python_binary, str(driver_script.resolve()), str(input_json), str(output_json)]


def run_comsol_validation(output_dir: str | Path, request: dict[str, Any]) -> tuple[dict[str, Any], ToolRunRecord]:
    output_dir = ensure_dir(output_dir)
    request_path = write_json(output_dir / "comsol_request.json", request)
    output_json = output_dir / "comsol_result.json"
    stdout_path = output_dir / "comsol_stdout.log"
    stderr_path = output_dir / "comsol_stderr.log"
    command = _resolve_comsol_command(request_path, output_json, request)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root() / "src") + os.pathsep + env.get("PYTHONPATH", "")
    process = subprocess.run(command, cwd=output_dir, capture_output=True, text=True, timeout=300, env=env, check=False)
    write_text(stdout_path, process.stdout)
    write_text(stderr_path, process.stderr)
    if output_json.exists():
        result = _validate_result_schema(json.loads(output_json.read_text(encoding="utf-8")), "comsol")
    else:
        result = _write_failure_output(output_json, "comsol", process.stderr.strip() or f"COMSOL command exited with code {process.returncode}.")
    status = "passed" if process.returncode == 0 and str(result.get("status", "")).lower() == "passed" else "failed"
    run = ToolRunRecord(
        tool="comsol",
        purpose="L3 COMSOL high-fidelity validation",
        status=status,
        inputs={"command": command, "request": str(request_path)},
        outputs=result,
        artifact_paths=(str(request_path), str(output_json), str(stdout_path), str(stderr_path)),
        notes=result.get("notes", ""),
    )
    return result, run


def run_l3_validation_suite(
    output_dir: str | Path,
    task: DiscoverTaskCard,
    l1_summary: dict[str, Any] | None,
    l2_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    output_dir = ensure_dir(output_dir)
    request = build_l3_request(task, l1_summary=l1_summary, l2_summary=l2_summary)
    request_path = write_json(output_dir / "l3_request.json", request)

    tool_results: dict[str, Any] = {}
    tool_runs: list[ToolRunRecord] = []
    if "matlab" in task.allowed_tools:
        result, run = run_matlab_validation(output_dir / "matlab", request)
        tool_results["matlab"] = result
        tool_runs.append(run)
    if "comsol" in task.allowed_tools:
        result, run = run_comsol_validation(output_dir / "comsol", request)
        tool_results["comsol"] = result
        tool_runs.append(run)

    calibration_summary = run_l2_l3_calibration(output_dir / "calibration", task, request, l2_summary or {}, tool_results)
    consensus = build_consensus_alignment(calibration_summary)
    consensus_path = write_json(output_dir / "l3_consensus_alignment.json", consensus)
    summary = {
        "protocol_version": L3_PROTOCOL_VERSION,
        "request_manifest": str(request_path.resolve()),
        "consensus_alignment": consensus,
        "tool_results": tool_results,
        "calibration_summary": calibration_summary,
    }
    summary_path = write_json(output_dir / "l3_summary.json", summary)
    return {
        "request": request,
        "request_manifest": str(request_path.resolve()),
        "consensus_alignment": consensus,
        "tool_results": tool_results,
        "calibration_summary": calibration_summary,
        "tool_runs": tool_runs,
        "artifacts": {
            "request_manifest": str(request_path.resolve()),
            "consensus_alignment": str(consensus_path.resolve()),
            "summary": str(summary_path.resolve()),
            "calibration_summary": str((output_dir / "calibration" / "calibration_summary.json").resolve()),
            "calibrated_l2_summary": str((output_dir / "calibration" / "calibrated_l2_summary.json").resolve()),
            "uncertainty_model": str((output_dir / "calibration" / "uncertainty_model.json").resolve()),
            "candidate_uncertainty": str((output_dir / "calibration" / "candidate_uncertainty.csv").resolve()),
            "frequency_calibration": str((output_dir / "calibration" / "frequency_calibration.png").resolve()),
            "stopband_calibration": str((output_dir / "calibration" / "stopband_calibration.png").resolve()),
            "uncertainty_calibration": str((output_dir / "calibration" / "uncertainty_calibration.png").resolve()),
        },
    }
