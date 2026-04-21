from __future__ import annotations

from pathlib import Path

from veh_scientist.discover.calibration import run_l2_l3_calibration
from veh_scientist.discover.l2_beam import BeamReplayParams, run_l2_beam_replay
from veh_scientist.taskcard import parse_discover_task_card


def test_l2_l3_calibration_improves_frequency_alignment(tmp_path: Path) -> None:
    task = parse_discover_task_card("configs/tasks/tr_discover_replay.yaml")
    l2_summary = run_l2_beam_replay(tmp_path / "l2", BeamReplayParams())
    request = {
        "anchor_targets": [
            {
                "label": anchor.label,
                "band_index": anchor.band_index,
                "frequency_hz": anchor.frequency_hz,
                "stopband_hz": list(anchor.stopband_hz) if anchor.stopband_hz is not None else None,
            }
            for anchor in task.l3_anchors
        ],
        "candidate_targets": l2_summary["candidates"],
    }
    summary = run_l2_l3_calibration(tmp_path / "calibration", task, request, l2_summary, tool_results={})
    errors = summary["errors"]
    assert errors["post_rmse_hz"] <= errors["pre_rmse_hz"]
    assert (tmp_path / "calibration" / "calibration_summary.json").exists()
    assert (tmp_path / "calibration" / "calibrated_l2_summary.json").exists()
    assert summary["calibrated_l2_summary"]["candidates"][0]["calibrated_frequency_hz"] is not None
