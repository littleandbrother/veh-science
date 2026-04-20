"""Program builders for replay/discover mode."""

from __future__ import annotations

from datetime import datetime

from veh_scientist.discover.claims import build_claim_graph
from veh_scientist.discover.corpus import build_corpus_manifest
from veh_scientist.discover.derivations import build_tr_derivation_cards
from veh_scientist.discover.evidence import draft_evidence_records
from veh_scientist.discover.hypotheses import build_tr_hypothesis_ladder
from veh_scientist.discover.replay_tr import build_tr_replay_steps
from veh_scientist.interfaces import DiscoverTaskCard, DiscoveryProgramState


def build_initial_program(task: DiscoverTaskCard) -> DiscoveryProgramState:
    """Build the initial replay/discover program state."""

    corpus_manifest = build_corpus_manifest(task)
    claim_graph = build_claim_graph(task)
    hypotheses = build_tr_hypothesis_ladder(task)
    derivations = build_tr_derivation_cards(task)
    planned_steps = build_tr_replay_steps(task)
    evidence = draft_evidence_records(claim_graph, derivations, gap_candidates=[])
    now = datetime.now().isoformat()
    return DiscoveryProgramState(
        task_id=task.task_id,
        mode=task.discovery_mode,
        stage="planned",
        corpus_manifest=corpus_manifest,
        planned_steps=planned_steps,
        claim_graph=claim_graph,
        hypotheses=hypotheses,
        derivations=derivations,
        evidence=evidence,
        notes=[task.research_question] if task.research_question else [],
        current_focus=task.mechanism_focus,
        created_at=now,
        updated_at=now,
    )
