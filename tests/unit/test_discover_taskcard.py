from __future__ import annotations

from veh_scientist.interfaces import DiscoverTaskCard
from veh_scientist.taskcard import parse_task_card, validate_task_card


def test_parse_discover_task_card_detects_source_corpus() -> None:
    task = parse_task_card(
        {
            "task_type": "discover",
            "task_id": "discover-001",
            "mechanism_focus": "truncation_resonance",
            "discovery_mode": "replay",
            "source_corpus": [
                {
                    "title": "Target paper",
                    "path": "truncation_resonance.pdf",
                    "role": "target_paper",
                    "source_type": "pdf",
                }
            ],
        }
    )
    assert isinstance(task, DiscoverTaskCard)
    assert task.source_corpus[0].role == "target_paper"
    assert validate_task_card(task) == []
