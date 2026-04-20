"""Discovery runner for replay/discover mode."""

from __future__ import annotations

from dataclasses import asdict

from veh_scientist.discover.program import build_initial_program
from veh_scientist.interfaces import DiscoverTaskCard, DiscoveryProgramState


class DiscoveryRunner:
    """Build and summarize a replay/discover program.

    This initial implementation is intentionally planning-centric: it does not yet
    execute physics solvers. Instead it formalizes the full workflow as a single
    program state that later execution layers can consume.
    """

    def __init__(self, task: DiscoverTaskCard):
        self.task = task

    def plan(self) -> DiscoveryProgramState:
        return build_initial_program(self.task)

    def summary(self) -> dict[str, object]:
        program = self.plan()
        return {
            "task_id": program.task_id,
            "mode": program.mode,
            "n_documents": len(program.corpus_manifest),
            "n_steps": len(program.planned_steps),
            "n_claims": len(program.claim_graph),
            "n_hypotheses": len(program.hypotheses),
            "n_derivations": len(program.derivations),
            "n_evidence_records": len(program.evidence),
            "current_focus": program.current_focus,
            "steps": [asdict(step) for step in program.planned_steps],
        }
