from __future__ import annotations

import sys
from pathlib import Path

from veh_scientist.discover.l3_toolchain import run_l3_validation_suite
from veh_scientist.taskcard import parse_discover_task_card


FAKE_TOOL = """
import json
import sys
from pathlib import Path
input_path = Path(sys.argv[1])
output_path = Path(sys.argv[2])
data = json.loads(input_path.read_text(encoding='utf-8'))
curve_dir = output_path.parent
transmission_curve = curve_dir / 'transmission_curve.csv'
power_curve = curve_dir / 'power_curve.csv'
mode_shape = curve_dir / 'mode_shape_summary.json'
stopband_summary = curve_dir / 'stopband_summary.json'
transmission_curve.write_text('frequency_hz,transmission_db\\n3272,-12\\n8259,-10\\n', encoding='utf-8')
power_curve.write_text('frequency_hz,power_mw\\n3272,2.32\\n8259,1.10\\n', encoding='utf-8')
mode_shape.write_text(json.dumps({'profiles': [{'label': 'TR1'}, {'label': 'TR2'}]}), encoding='utf-8')
stopband_summary.write_text(json.dumps({'detected_stopbands_hz': [[2600, 4300], [5600, 8600]]}), encoding='utf-8')
payload = {
    'status': 'passed',
    'engine': 'fake',
    'frequency_pairs': [
        {
            'band_index': anchor['band_index'],
            'label': anchor['label'],
            'raw_frequency_hz': next(
                candidate.get('raw_frequency_hz', candidate.get('frequency_hz'))
                for candidate in data.get('candidate_targets', [])
                if candidate.get('band_index') == anchor.get('band_index')
            ),
            'l3_frequency_hz': anchor['frequency_hz'],
            'source': 'fake',
        }
        for anchor in data.get('anchor_targets', [])
    ],
    'stopband_pairs': [
        {
            'band_index': anchor['band_index'],
            'label': anchor['label'],
            'raw_stopband_hz': next(
                candidate.get('raw_stopband_hz')
                for candidate in data.get('candidate_targets', [])
                if candidate.get('band_index') == anchor.get('band_index')
            ),
            'l3_stopband_hz': anchor['stopband_hz'],
            'source': 'fake',
        }
        for anchor in data.get('anchor_targets', [])
        if anchor.get('stopband_hz') is not None
    ],
    'anchor_alignment': [
        {
            'label': anchor['label'],
            'anchor_frequency_hz': anchor['frequency_hz'],
            'best_frequency_hz': anchor['frequency_hz'],
            'error_hz': 0.0,
        }
        for anchor in data.get('anchor_targets', [])
    ],
    'curve_artifacts': {
        'transmission_curve': str(transmission_curve),
        'power_curve': str(power_curve),
        'mode_shape': str(mode_shape),
        'stopband_summary': str(stopband_summary),
    },
}
output_path.write_text(json.dumps(payload), encoding='utf-8')
"""


def test_l3_validation_suite_executes_fake_commands(tmp_path: Path, monkeypatch) -> None:
    fake_script = tmp_path / "fake_tool.py"
    fake_script.write_text(FAKE_TOOL, encoding="utf-8")
    monkeypatch.setenv("VEHSCI_MATLAB_CMD", f"{sys.executable} {fake_script} {{input}} {{output}}")
    monkeypatch.setenv("VEHSCI_COMSOL_CMD", f"{sys.executable} {fake_script} {{input}} {{output}}")

    task = parse_discover_task_card("configs/tasks/tr_discover_replay.yaml")
    l2_summary = {
        "stopbands_hz": [
            {"frequency_min_hz": 16000.0, "frequency_max_hz": 17000.0},
            {"frequency_min_hz": 49000.0, "frequency_max_hz": 50000.0},
        ],
        "candidates": [
            {"band_index": 1, "frequency_hz": 16137.0},
            {"band_index": 2, "frequency_hz": 49649.0},
        ]
    }
    suite = run_l3_validation_suite(tmp_path, task, l1_summary=None, l2_summary=l2_summary)
    assert suite["tool_results"]["matlab"]["status"] == "passed"
    assert suite["tool_results"]["comsol"]["status"] == "passed"
    assert all(run.status == "passed" for run in suite["tool_runs"])
    assert len(suite["calibration_summary"]["stopband_pairs"]) == 2
    assert suite["tool_results"]["matlab"]["curve_artifacts"]["transmission_curve"].endswith("transmission_curve.csv")
    assert suite["tool_results"]["comsol"]["curve_artifacts"]["power_curve"].endswith("power_curve.csv")
    assert Path(suite["artifacts"]["summary"]).exists()
