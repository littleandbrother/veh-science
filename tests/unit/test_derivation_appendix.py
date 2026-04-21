from __future__ import annotations

from pathlib import Path

from veh_scientist.discover.derivations import execute_tr_derivations
from veh_scientist.taskcard import parse_discover_task_card


def test_execute_tr_derivations_writes_appendix_grade_package(tmp_path: Path) -> None:
    task = parse_discover_task_card("configs/tasks/tr_discover_replay.yaml")
    result = execute_tr_derivations(tmp_path, task)
    summary = result["appendix_summary"]
    assert len(result["cards"]) == 6
    assert summary["n_trace_groups"] == 6
    assert summary["n_limit_cases"] >= 6
    assert summary["n_solver_cross_checks"] >= 6
    assert summary["all_checks_pass"] is True
    assert (tmp_path / "appendix_bundle.tex").exists()
    assert (tmp_path / "appendix_package.md").exists()
    assert (tmp_path / "derivation_traces.json").exists()
    assert (tmp_path / "symbol_table.json").exists()
