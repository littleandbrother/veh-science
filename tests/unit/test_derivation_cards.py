from __future__ import annotations

from veh_scientist.discover.derivations import build_tr_derivation_cards
from veh_scientist.taskcard import parse_discover_task_card


def test_tr_derivation_ladder_contains_expected_cards() -> None:
    task = parse_discover_task_card("configs/tasks/tr_discover_replay.yaml")
    cards = build_tr_derivation_cards(task)
    titles = [card.title for card in cards]
    assert len(cards) == 6
    assert "Infinite-chain dispersion relation" in titles
    assert "Complex dynamic stiffness and electrical matching" in titles
    assert all(card.validation_checks for card in cards)
