"""Real MATLAB / COMSOL invocation chain for L3 validation and anchor checks."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from veh_scientist.discover.anchors import anchor_score, fit_anchor_map
from veh_scientist.discover.utils import ensure_dir, repo_root, write_json, write_text
from veh_scientist.interfaces import DiscoverTaskCard, L3Anchor, ToolRunRecord


def _candidate_rows(l2_summary: dict[str, Any] | None) -> list[dict[str, Any]]:
    if l2_summary is None:
        return []
    return [dict(row) for row in l2_summary.get("candidates", [])]


def _anchor_rows(anchors: tuple[L3Anchor, ...] | list[L3Anchor]) -> list[dict[str, Any]]:
    return [
        {
            "anchor_id": anchor.anchor_id,
            "label": anchor.label,
            "band_index": anchor.band_index,
            "frequency_hz": anchor.frequency_hz,
            "stopband_hz": list(anchor.stopband_hz) if anchor.stopband_hz is not None else None,
            "target_power_mw": anchor.target_power_mw,
            "target_transmission_db": anchor.target_transmission_db,
            "target_pef": anchor.target_pef,
            "note": anchor.note,
        }
        for anchor in anchors
    ]


def build_l3_request(
    task: DiscoverTaskCard,
    l1_summary: dict[str, Any] | None,
    l2_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    candidates = _candidate_rows(l2_summary)
    frequencies = [float(row.get("frequency_hz", 0.0)) for row in candidates]
    return {
        "task_id": task.task_id,
        "mechanism_focus": task.mechanism_focus,
        "research_question": task.research_question,
        "allowed_tools": list(task.allowed_tools),
        "anchors": _anchor_rows(task.l3_anchors),
        "l1_summary": l1_summary or {},
        "l2_summary": l2_summary or {},
        "l2_candidate_frequencies_hz": frequencies,
        "n_candidates": len(candidates),
    }


def build_consensus_alignment(request: dict[str, Any]) -> list[dict[str, Any]]:
    anchors = request.get("anchors", [])
    candidates = request.get("l2_summary", {}).get("candidates", [])
    if not anchors or not candidates:
        return []
    anchor_objs = tuple(
        L3Anchor(
            anchor_id=str(item.get("anchor_id", "")) or L3Anchor().anchor_id,
            label=str(item.get("label", "TR")),
            frequency_hz=float(item.get("frequency_hz", 0.0)),
            band_index=int(item["band_index"]) if item.get("band_index") is not None else None,
            stopband_hz=tuple(float(v) for v in item["stopband_hz"]) if item.get("stopband_hz") is not None else None,
            target_power_mw=float(item["target_power_mw"]) if item.get("target_power_mw") is not None else None,
            target_transmission_db=float(item["target_transmission_db"]) if item.get("target_transmission_db") is not None else None,
            target_pef=float(item["target_pef"]) if item.get("target_pef") is not None else None,
            note=str(item.get("note", "")),
        )
        for item in anchors
    )
    raw_freqs = [float(cand.get("frequency_hz", 0.0)) for cand in candidates]
    anchor_map = fit_anchor_map(raw_freqs, anchor_objs)
    rows: list[dict[str, Any]] = []
    for cand in candidates:
        band_index = int(cand.get("band_index", 0))
        raw_hz = float(cand.get("frequency_hz", 0.0))
        anchored_hz = anchor_map.apply(raw_hz)
        score, label, error_hz = anchor_score(anchored_hz, anchor_objs)
        rows.append(
            {
                "band_index": band_index,
                "raw_frequency_hz": raw_hz,
                "anchored_frequency_hz": anchored_hz,
                "matched_anchor": label,
                "error_hz": error_hz,
                "score": score,
            }
        )
    return rows


def write_matlab_driver_script(path: str | Path) -> Path:
    path = Path(path)
    script = r"""function veh_l3_validate(input_json_path, output_json_path)
raw = fileread(input_json_path);
data = jsondecode(raw);
result = struct();
result.status = 'passed';
result.engine = 'matlab';
result.anchor_alignment = struct([]);
result.n_candidates = 0;
if isfield(data, 'l2_candidate_frequencies_hz')
    freqs = data.l2_candidate_frequencies_hz;
    result.n_candidates = numel(freqs);
else
    freqs = [];
end
if isfield(data, 'anchors')
    anchors = data.anchors;
else
    anchors = struct([]);
end
alignments = repmat(struct('label', '', 'anchor_frequency_hz', NaN, 'best_frequency_hz', NaN, 'error_hz', NaN), numel(anchors), 1);
for i = 1:numel(anchors)
    anchor_hz = anchors(i).frequency_hz;
    if isempty(freqs)
        best = NaN;
        err = NaN;
    else
        [err, idx] = min(abs(freqs - anchor_hz));
        best = freqs(idx);
    end
    alignments(i).label = anchors(i).label;
    alignments(i).anchor_frequency_hz = anchor_hz;
    alignments(i).best_frequency_hz = best;
    alignments(i).error_hz = err;
end
result.anchor_alignment = alignments;
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
            env_command.format(
                script=script_path,
                input=input_json,
                output=output_json,
                workdir=script_path.parent,
            )
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
    payload = {"status": "failed", "engine": engine, "notes": notes, "anchor_alignment": []}
    write_json(output_json, payload)
    return payload


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
            purpose="L3 MATLAB anchor validation",
            status="failed",
            inputs={"request": str(request_path), "script": str(script_path)},
            outputs=result,
            artifact_paths=(str(request_path), str(script_path), str(output_json)),
            notes=result["notes"],
        )
        return result, run

    env = os.environ.copy()
    process = subprocess.run(
        command,
        cwd=output_dir,
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
        check=False,
    )
    write_text(stdout_path, process.stdout)
    write_text(stderr_path, process.stderr)
    if output_json.exists():
        result = json.loads(output_json.read_text(encoding="utf-8"))
    else:
        result = _write_failure_output(output_json, "matlab", process.stderr.strip() or f"MATLAB command exited with code {process.returncode}.")
    status = "passed" if process.returncode == 0 and str(result.get("status", "")).lower() == "passed" else "failed"
    run = ToolRunRecord(
        tool="matlab",
        purpose="L3 MATLAB anchor validation",
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
        return shlex.split(
            env_command.format(
                input=input_json,
                output=output_json,
                workdir=output_json.parent,
            )
        )
    return [sys.executable, "-m", "veh_scientist.discover.l3_comsol_driver", str(input_json), str(output_json)]


def run_comsol_validation(output_dir: str | Path, request: dict[str, Any]) -> tuple[dict[str, Any], ToolRunRecord]:
    output_dir = ensure_dir(output_dir)
    request_path = write_json(output_dir / "comsol_request.json", request)
    output_json = output_dir / "comsol_result.json"
    stdout_path = output_dir / "comsol_stdout.log"
    stderr_path = output_dir / "comsol_stderr.log"
    command = _resolve_comsol_command(request_path, output_json)
    env = os.environ.copy()
    repo = repo_root()
    env["PYTHONPATH"] = str(repo / "src") + os.pathsep + env.get("PYTHONPATH", "")
    process = subprocess.run(
        command,
        cwd=output_dir,
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
        check=False,
    )
    write_text(stdout_path, process.stdout)
    write_text(stderr_path, process.stderr)
    if output_json.exists():
        result = json.loads(output_json.read_text(encoding="utf-8"))
    else:
        result = _write_failure_output(output_json, "comsol", process.stderr.strip() or f"COMSOL command exited with code {process.returncode}.")
    status = "passed" if process.returncode == 0 and str(result.get("status", "")).lower() == "passed" else "failed"
    run = ToolRunRecord(
        tool="comsol",
        purpose="L3 COMSOL anchor validation",
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
    consensus = build_consensus_alignment(request)
    consensus_path = write_json(output_dir / "l3_consensus_alignment.json", consensus)

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

    summary = {
        "request_manifest": str(request_path.resolve()),
        "consensus_alignment": consensus,
        "tool_results": tool_results,
    }
    summary_path = write_json(output_dir / "l3_summary.json", summary)
    return {
        "request": request,
        "request_manifest": str(request_path.resolve()),
        "consensus_alignment": consensus,
        "tool_results": tool_results,
        "tool_runs": tool_runs,
        "artifacts": {
            "request_manifest": str(request_path.resolve()),
            "consensus_alignment": str(consensus_path.resolve()),
            "summary": str(summary_path.resolve()),
        },
    }
