"""Structured MATLAB/COMSOL toolchain and L2↔L3 calibration loop."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from veh_scientist.discover.calibration import L3_PROTOCOL_VERSION, run_l2_l3_calibration
from veh_scientist.discover.utils import ensure_dir, repo_root, write_json, write_text
from veh_scientist.interfaces import DiscoverTaskCard, ToolRunRecord


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
        "backend_config": {
            "matlab_entrypoint": os.environ.get("VEHSCI_MATLAB_ENTRYPOINT", "veh_l3_validate"),
            "comsol_model_path": os.environ.get("VEHSCI_COMSOL_MODEL", ""),
            "comsol_study_tag": os.environ.get("VEHSCI_COMSOL_STUDY", ""),
            "comsol_dataset_tag": os.environ.get("VEHSCI_COMSOL_DATASET", ""),
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
    script = r"""function veh_l3_validate(input_json_path, output_json_path)
raw = fileread(input_json_path);
data = jsondecode(raw);
result = struct();
result.protocol_version = 'l3-protocol-1.0';
result.status = 'passed';
result.engine = 'matlab';
result.notes = 'Template driver executed. Replace nearest-anchor logic with project-specific high-fidelity MATLAB scripts when available.';
result.frequency_pairs = struct([]);
result.stopband_pairs = struct([]);
result.anchor_alignment = struct([]);
result.curve_artifacts = struct();
if isfield(data, 'candidate_targets')
    candidates = data.candidate_targets;
else
    candidates = struct([]);
end
if isfield(data, 'anchor_targets')
    anchors = data.anchor_targets;
else
    anchors = struct([]);
end
freq_pairs = repmat(struct('band_index', NaN, 'label', '', 'raw_frequency_hz', NaN, 'l3_frequency_hz', NaN, 'source', 'matlab-template'), numel(anchors), 1);
stop_pairs = repmat(struct('band_index', NaN, 'label', '', 'raw_stopband_hz', [], 'l3_stopband_hz', [], 'source', 'matlab-template'), numel(anchors), 1);
aligns = repmat(struct('label', '', 'anchor_frequency_hz', NaN, 'best_frequency_hz', NaN, 'error_hz', NaN), numel(anchors), 1);
for i = 1:numel(anchors)
    anchor_hz = anchors(i).frequency_hz;
    label = anchors(i).label;
    band_index = i;
    if isfield(anchors(i), 'band_index') && ~isempty(anchors(i).band_index)
        band_index = anchors(i).band_index;
    end
    best = NaN;
    best_idx = 0;
    err = NaN;
    for j = 1:numel(candidates)
        cand_hz = candidates(j).raw_frequency_hz;
        if isnan(best) || abs(cand_hz - anchor_hz) < err
            best = cand_hz;
            best_idx = j;
            err = abs(cand_hz - anchor_hz);
        end
    end
    aligns(i).label = label;
    aligns(i).anchor_frequency_hz = anchor_hz;
    aligns(i).best_frequency_hz = best;
    aligns(i).error_hz = err;
    freq_pairs(i).band_index = band_index;
    freq_pairs(i).label = label;
    freq_pairs(i).raw_frequency_hz = best;
    freq_pairs(i).l3_frequency_hz = anchor_hz;
    if best_idx > 0 && isfield(candidates(best_idx), 'raw_stopband_hz') && isfield(anchors(i), 'stopband_hz')
        stop_pairs(i).band_index = band_index;
        stop_pairs(i).label = label;
        stop_pairs(i).raw_stopband_hz = candidates(best_idx).raw_stopband_hz;
        stop_pairs(i).l3_stopband_hz = anchors(i).stopband_hz;
    end
end
result.frequency_pairs = freq_pairs;
result.stopband_pairs = stop_pairs;
result.anchor_alignment = aligns;
fid = fopen(output_json_path, 'w');
fprintf(fid, '%s', jsonencode(result));
fclose(fid);
end
"""
    return write_text(path, script)


def _resolve_matlab_command(script_path: Path, input_json: Path, output_json: Path) -> list[str] | None:
    env_command = os.environ.get("VEHSCI_MATLAB_CMD")
    if env_command:
        return shlex.split(
            env_command.format(script=script_path, input=input_json, output=output_json, workdir=script_path.parent)
        )

    matlab = shutil.which("matlab")
    if matlab:
        batch = f"addpath('{script_path.parent.as_posix()}');veh_l3_validate('{input_json.as_posix()}','{output_json.as_posix()}');"
        return [matlab, "-batch", batch]

    octave = shutil.which("octave")
    if octave:
        batch = f"addpath('{script_path.parent.as_posix()}');veh_l3_validate('{input_json.as_posix()}','{output_json.as_posix()}');"
        return [octave, "--quiet", "--eval", batch]
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
    command = _resolve_matlab_command(script_path, request_path, output_json)

    if command is None:
        result = _write_failure_output(output_json, "matlab", "No MATLAB or Octave executable was found. Set VEHSCI_MATLAB_CMD or install MATLAB/Octave.")
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

    process = subprocess.run(command, cwd=output_dir, capture_output=True, text=True, timeout=180, env=os.environ.copy(), check=False)
    write_text(stdout_path, process.stdout)
    write_text(stderr_path, process.stderr)
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
        artifact_paths=(str(request_path), str(script_path), str(output_json), str(stdout_path), str(stderr_path)),
        notes=result.get("notes", ""),
    )
    return result, run


def _resolve_comsol_command(input_json: Path, output_json: Path) -> list[str]:
    env_command = os.environ.get("VEHSCI_COMSOL_CMD")
    if env_command:
        return shlex.split(env_command.format(input=input_json, output=output_json, workdir=output_json.parent))
    return [sys.executable, "-m", "veh_scientist.discover.l3_comsol_driver", str(input_json), str(output_json)]


def run_comsol_validation(output_dir: str | Path, request: dict[str, Any]) -> tuple[dict[str, Any], ToolRunRecord]:
    output_dir = ensure_dir(output_dir)
    request_path = write_json(output_dir / "comsol_request.json", request)
    output_json = output_dir / "comsol_result.json"
    stdout_path = output_dir / "comsol_stdout.log"
    stderr_path = output_dir / "comsol_stderr.log"
    command = _resolve_comsol_command(request_path, output_json)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root() / "src") + os.pathsep + env.get("PYTHONPATH", "")
    process = subprocess.run(command, cwd=output_dir, capture_output=True, text=True, timeout=180, env=env, check=False)
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
