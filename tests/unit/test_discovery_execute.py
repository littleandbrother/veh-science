from __future__ import annotations

from pathlib import Path

from veh_scientist.discover import DiscoveryRunner
from veh_scientist.taskcard import parse_discover_task_card


def test_discovery_runner_executes_and_writes_artifacts(tmp_path: Path) -> None:
    task = parse_discover_task_card("configs/tasks/tr_discover_replay.yaml")
    runner = DiscoveryRunner(task, task_card_path="configs/tasks/tr_discover_replay.yaml")
    program = runner.execute(output_dir=tmp_path)
    assert program.stage == "completed"
    assert program.gap_candidates
    assert program.artifacts
    assert program.l3_validation
    assert program.smoke_summary
    assert program.smoke_summary["overall_pass"] is True
    assert (tmp_path / task.task_id / "program_state.json").exists()
    assert any(artifact.label == "Discovery report" for artifact in program.artifacts)
