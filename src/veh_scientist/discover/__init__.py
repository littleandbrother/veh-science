"""Replay/discover orchestration for mechanism-grounded research programs."""

from .anchors import AnchorMap, anchor_score, fit_anchor_map
from .claims import build_claim_graph
from .corpus import build_corpus_manifest, target_documents
from .derivations import build_tr_derivation_cards, execute_tr_derivations
from .evidence import draft_evidence_records
from .gap_designer import GapRankingWeights, build_gap_candidates, rank_gap_candidates, score_gap_candidate
from .hypotheses import build_tr_hypothesis_ladder
from .l1_chain import ChainReplayParams, run_l1_chain_replay
from .l2_beam import BeamReplayParams, run_l2_beam_replay
from .l3_toolchain import run_l3_validation_suite
from .mechanisms import build_mechanism_portfolio
from .program import build_initial_program
from .replay_tr import build_tr_replay_steps
from .report import write_report_bundle
from .runner import DiscoveryRunner
from .smoke import run_regression_smoke

__all__ = [
    "AnchorMap",
    "BeamReplayParams",
    "ChainReplayParams",
    "DiscoveryRunner",
    "GapRankingWeights",
    "anchor_score",
    "build_claim_graph",
    "build_corpus_manifest",
    "build_gap_candidates",
    "build_initial_program",
    "build_mechanism_portfolio",
    "build_tr_derivation_cards",
    "build_tr_hypothesis_ladder",
    "build_tr_replay_steps",
    "draft_evidence_records",
    "execute_tr_derivations",
    "fit_anchor_map",
    "rank_gap_candidates",
    "run_l1_chain_replay",
    "run_l2_beam_replay",
    "run_l3_validation_suite",
    "run_regression_smoke",
    "score_gap_candidate",
    "target_documents",
    "write_report_bundle",
]
