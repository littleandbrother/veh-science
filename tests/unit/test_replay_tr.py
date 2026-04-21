from __future__ import annotations

from veh_scientist.discover import DiscoveryRunner
from veh_scientist.taskcard import parse_discover_task_card


def test_discovery_runner_builds_replay_program() -> None:
    task = parse_discover_task_card("configs/tasks/tr_discover_replay.yaml")
    runner = DiscoveryRunner(task)
    program = runner.plan()
    assert program.mode == "replay"
    assert program.corpus_manifest[0].role == "target_paper"
    assert len(program.planned_steps) == 13
    assert len(program.claim_graph) >= 5
    assert len(program.hypotheses) == 5
    assert len(program.derivations) == 6
    assert len(program.evidence) == len(program.claim_graph)
    assert len(task.l3_anchors) == 2
