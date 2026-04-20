"""Regression tests for task card parsing and screening glue code."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from veh_scientist.interfaces.schemas import (
    CandidateDesignFamily,
    ElectricalParams,
    StructuralParams,
)
from veh_scientist.mechanism.gates import gate_6_suppression_compatibility
from veh_scientist.mechanism.screening import MechanismScreener
from veh_scientist.taskcard.parser import parse_task_card
from veh_scientist.verifiers.l1_chain import compute_harvesting_metrics


def test_yaml_task_card_accepts_null_load_value():
    card = parse_task_card("configs/tasks/tr_baseline.yaml")
    assert card.harvesting_requirements.load_value is None
    assert card.harvesting_requirements.target_output == "current"
    assert card.frequency_target.primary_target_frequency is None


def test_screening_runs_with_candidate_electrical_params():
    candidate = CandidateDesignFamily(
        structure=StructuralParams(alpha=0.75, beta=3.0, delta=0.5, N=10),
        electrical=ElectricalParams(kappa2=0.0075, epsilon=6.25),
    )
    screener = MechanismScreener()
    result = screener.screen(candidate)

    assert result.verdict in {"pass", "revise", "reject"}
    assert len(result.gates) >= 4


def test_gate6_matches_l1_transmission_metric():
    epsilon = 1.973473
    gate = gate_6_suppression_compatibility(
        alpha=1.0,
        beta=0.5,
        delta=1.5,
        N=10,
        kappa2=0.05,
        epsilon=epsilon,
    )
    metrics = compute_harvesting_metrics(
        alpha=1.0,
        beta=0.5,
        delta=1.5,
        n_cells=10,
        kappa_sq=0.05,
        epsilon=epsilon,
        n_points=4000,
    )
    assert abs(gate.value - metrics.transmission_tr_dB) < 1e-6
