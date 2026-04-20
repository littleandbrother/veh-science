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
payload = {
    'status': 'passed',
    'engine': 'fake',
    'anchor_alignment': [
        {
            'label': anchor['label'],
            'anchor_frequency_hz': anchor['frequency_hz'],
            'best_frequency_hz': anchor['frequency_hz'],
            'error_hz': 0.0,
        }
        for anchor in data.get('anchors', [])
    ],
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
        "candidates": [
            {"band_index": 1, "frequency_hz": 16137.0},
            {"band_index": 2, "frequency_hz": 49649.0},
        ]
    }
    suite = run_l3_validation_suite(tmp_path, task, l1_summary=None, l2_summary=l2_summary)
    assert suite["tool_results"]["matlab"]["status"] == "passed"
    assert suite["tool_results"]["comsol"]["status"] == "passed"
    assert all(run.status == "passed" for run in suite["tool_runs"])
    assert Path(suite["artifacts"]["summary"]).exists()
