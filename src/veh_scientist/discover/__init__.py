"""Replay/discover orchestration for mechanism-grounded research programs."""

from .claims import build_claim_graph
from .corpus import build_corpus_manifest, target_documents
from .derivations import build_tr_derivation_cards, execute_tr_derivations
from .evidence import draft_evidence_records
from .gap_designer import GapRankingWeights, build_gap_candidates, rank_gap_candidates, score_gap_candidate
from .hypotheses import build_tr_hypothesis_ladder
from .l1_chain import ChainReplayParams, run_l1_chain_replay
from .l2_beam import BeamReplayParams, run_l2_beam_replay
from .program import build_initial_program
from .replay_tr import build_tr_replay_steps
from .runner import DiscoveryRunner

__all__ = [
    "BeamReplayParams",
    "ChainReplayParams",
    "DiscoveryRunner",
    "GapRankingWeights",
    "build_claim_graph",
    "build_corpus_manifest",
    "build_gap_candidates",
    "build_initial_program",
    "build_tr_derivation_cards",
    "build_tr_hypothesis_ladder",
    "build_tr_replay_steps",
    "draft_evidence_records",
    "execute_tr_derivations",
    "rank_gap_candidates",
    "run_l1_chain_replay",
    "run_l2_beam_replay",
    "score_gap_candidate",
    "target_documents",
]
