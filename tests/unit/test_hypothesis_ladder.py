from __future__ import annotations

from veh_scientist.discover.hypotheses import build_tr_hypothesis_ladder
from veh_scientist.taskcard import parse_discover_task_card


def test_tr_hypothesis_ladder_has_five_core_steps() -> None:
    task = parse_discover_task_card("configs/tasks/tr_discover_replay.yaml")
    hypotheses = build_tr_hypothesis_ladder(task)
    assert [card.label for card in hypotheses] == ["H1", "H2", "H3", "H4", "H5"]
    assert "bandgap" in hypotheses[0].statement.lower()
    assert "piezo" in hypotheses[2].statement.lower()
