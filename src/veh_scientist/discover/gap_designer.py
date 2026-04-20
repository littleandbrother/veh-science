"""Ranking helpers for choosing usable TR-enabled bandgaps."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from veh_scientist.interfaces import GapCandidate


@dataclass(frozen=True)
class GapRankingWeights:
    """Weights for multi-objective gap ranking."""

    suppression: float = 0.25
    localization: float = 0.25
    harvestability: float = 0.25
    robustness: float = 0.15
    realizability: float = 0.10


def score_gap_candidate(candidate: GapCandidate, weights: GapRankingWeights | None = None) -> float:
    """Score a gap candidate using a weighted sum of normalized criteria."""

    weights = weights or GapRankingWeights()
    score = (
        weights.suppression * candidate.suppression_margin
        + weights.localization * candidate.localization_score
        + weights.harvestability * candidate.harvestability_score
        + weights.robustness * candidate.robustness_score
        + weights.realizability * candidate.realizability_score
    )
    return round(float(score), 8)


def rank_gap_candidates(
    candidates: Iterable[GapCandidate],
    weights: GapRankingWeights | None = None,
) -> list[GapCandidate]:
    """Return gap candidates sorted by descending overall score."""

    weights = weights or GapRankingWeights()
    scored = [replace(candidate, overall_score=score_gap_candidate(candidate, weights)) for candidate in candidates]
    return sorted(scored, key=lambda cand: (-cand.overall_score, cand.band_index, cand.omega_min))


def _band_realizability(center_hz: float, band_of_interest: tuple[float, float] | None) -> float:
    if band_of_interest is None:
        return 0.5
    low, high = band_of_interest
    if low <= center_hz <= high:
        return 1.0
    distance = min(abs(center_hz - low), abs(center_hz - high))
    scale = max(high - low, 1.0)
    return float(max(0.0, 1.0 - distance / scale))


def build_gap_candidates(
    l1_summary: dict | None,
    l2_summary: dict | None,
    band_of_interest: tuple[float, float] | None = None,
) -> list[GapCandidate]:
    """Convert solver summaries into rankable :class:`GapCandidate` objects."""

    candidates: list[GapCandidate] = []

    if l2_summary is not None and l2_summary.get("candidates"):
        raw_candidates = list(l2_summary["candidates"])
        max_power = max((cand.get("power_proxy", 0.0) for cand in raw_candidates), default=1.0) or 1.0
        for raw in raw_candidates:
            center_hz = float(raw.get("gap_center_hz", raw.get("frequency_hz", 0.0)))
            candidates.append(
                GapCandidate(
                    band_index=int(raw["band_index"]),
                    omega_min=float(raw["omega_min"]),
                    omega_max=float(raw["omega_max"]),
                    tr_frequencies=(float(raw["omega_tr"]),),
                    suppression_margin=float(max(0.0, min(1.0, raw.get("suppression_margin", 0.0)))),
                    localization_score=float(max(0.0, min(1.0, raw.get("localization_score", 0.0)))),
                    harvestability_score=float(max(0.0, min(1.0, raw.get("power_proxy", 0.0) / max_power))),
                    robustness_score=float(max(0.0, min(1.0, raw.get("robustness_score", 0.0)))),
                    realizability_score=_band_realizability(center_hz, band_of_interest),
                )
            )

    if not candidates and l1_summary is not None:
        tr = l1_summary["tr_mode"]
        gap = l1_summary["bandgap"]
        candidates.append(
            GapCandidate(
                band_index=1,
                omega_min=float(gap["omega_min"]),
                omega_max=float(gap["omega_max"]),
                tr_frequencies=(float(tr["omega"]),),
                suppression_margin=float(max(0.0, min(1.0, -l1_summary["transmission_at_tr_power_peak_db"] / 120.0))),
                localization_score=float(max(0.0, min(1.0, tr["eta"]))),
                harvestability_score=1.0,
                robustness_score=float(max(0.0, min(1.0, l1_summary["q_factor"] / 150.0))),
                realizability_score=0.5,
            )
        )

    return candidates
