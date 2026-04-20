"""Tests for proposal generation and candidate-to-beam translation."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from veh_scientist.codesign import CandidateToBeamTranslator
from veh_scientist.proposals import ProposalGenerator
from veh_scientist.taskcard.parser import parse_task_card


def test_proposal_generator_returns_multiple_unique_candidates():
    task = parse_task_card("configs/tasks/tr_baseline.yaml")
    generator = ProposalGenerator(task, max_candidates=3)
    candidates = generator.generate(
        round_id=1,
        seed_params={
            "alpha": 1.0,
            "beta": 0.5,
            "delta": 1.5,
            "N": 10,
            "kappa2": 0.05,
            "epsilon": None,
        },
    )
    assert len(candidates) == 3
    assert len({candidate.candidate_id for candidate in candidates}) == 3


def test_candidate_to_beam_translation_preserves_delta_as_boundary_mass_factor():
    task = parse_task_card("configs/tasks/tr_baseline.yaml")
    generator = ProposalGenerator(task, max_candidates=1)
    candidate = generator.generate(
        round_id=1,
        seed_params={
            "alpha": 1.0,
            "beta": 0.5,
            "delta": 1.8,
            "N": 10,
            "kappa2": 0.05,
            "epsilon": None,
        },
    )[0]
    translator = CandidateToBeamTranslator(task)
    realization = translator.translate(candidate)

    assert realization.boundary_mass_factor == candidate.structure.delta
    assert realization.L_A + realization.L_B > 0
    assert realization.R_load > 0
    assert realization.geom.h > 0
    assert realization.mat_B.rho < realization.mat_A.rho
    assert realization.mat_B.E < realization.mat_A.E
