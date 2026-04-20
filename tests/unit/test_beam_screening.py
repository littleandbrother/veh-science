"""Tests for the continuous-beam screening path."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from veh_scientist.interfaces.schemas import (
    CandidateDesignFamily,
    ElectricalParams,
    StructuralParams,
)
from veh_scientist.mechanism.screening import MechanismScreener
from veh_scientist.taskcard.parser import parse_task_card


def test_mechanism_screener_uses_beam_path_when_task_is_available():
    task = parse_task_card("configs/tasks/tr_baseline.yaml")
    candidate = CandidateDesignFamily(
        structure=StructuralParams(alpha=1.0, beta=0.5, delta=1.8, N=12),
        electrical=ElectricalParams(kappa2=0.05, epsilon=None),
    )

    screener = MechanismScreener(task=task)
    result = screener.screen(candidate)

    assert result.gates
    assert result.gates[0].gate_name == "bandgap_existence"
    assert result.gates[0].passed
    assert "L2 beam" in result.gates[0].message
    assert result.gates[1].gate_name == "boundary_asymmetry"
    assert result.gates[1].passed
