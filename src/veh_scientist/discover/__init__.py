"""Replay/discover orchestration for mechanism-grounded research programs."""

from .corpus import build_corpus_manifest, target_documents
from .claims import build_claim_graph
from .derivations import build_tr_derivation_cards
from .evidence import draft_evidence_records
from .gap_designer import GapRankingWeights, rank_gap_candidates, score_gap_candidate
from .hypotheses import build_tr_hypothesis_ladder
from .program import build_initial_program
from .replay_tr import build_tr_replay_steps
from .runner import DiscoveryRunner

__all__ = [
    "DiscoveryRunner",
    "GapRankingWeights",
    "build_claim_graph",
    "build_corpus_manifest",
    "build_initial_program",
    "build_tr_derivation_cards",
    "build_tr_hypothesis_ladder",
    "build_tr_replay_steps",
    "draft_evidence_records",
    "rank_gap_candidates",
    "score_gap_candidate",
    "target_documents",
]
