"""Ranking helpers for choosing usable TR-enabled bandgaps."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from veh_scientist.discover.anchors import anchor_score, fit_anchor_map
from veh_scientist.interfaces import GapCandidate, L3Anchor


@dataclass(frozen=True)
class GapRankingWeights:
    """Weights for multi-objective gap ranking."""

    suppression: float = 0.14
    localization: float = 0.16
    harvestability: float = 0.16
    robustness: float = 0.10
    realizability: float = 0.08
    target_band: float = 0.14
    anchor: float = 0.12
    l3_alignment: float = 0.10


def score_gap_candidate(candidate: GapCandidate, weights: GapRankingWeights | None = None) -> float:
    """Score a gap candidate using a weighted sum of normalized criteria."""

    weights = weights or GapRankingWeights()
    score = (
        weights.suppression * candidate.suppression_margin
        + weights.localization * candidate.localization_score
        + weights.harvestability * candidate.harvestability_score
        + weights.robustness * candidate.robustness_score
        + weights.realizability * candidate.realizability_score
        + weights.target_band * candidate.target_band_score
        + weights.anchor * candidate.anchor_score
        + weights.l3_alignment * candidate.l3_alignment_score
    )
    return round(float(score), 8)


def rank_gap_candidates(
    candidates: Iterable[GapCandidate],
    weights: GapRankingWeights | None = None,
) -> list[GapCandidate]:
    """Return gap candidates sorted by descending overall score."""

    weights = weights or GapRankingWeights()
    scored = [replace(candidate, overall_score=score_gap_candidate(candidate, weights)) for candidate in candidates]
    return sorted(
        scored,
        key=lambda cand: (
            -cand.overall_score,
            -(cand.anchor_score + cand.target_band_score + cand.localization_score),
            cand.band_index,
            cand.omega_min,
        ),
    )


def _clamp01(value: float) -> float:
    return float(max(0.0, min(1.0, value)))


def _band_score(center_hz: float | None, band_of_interest: tuple[float, float] | None) -> float:
    if center_hz is None or band_of_interest is None:
        return 0.5 if center_hz is not None else 0.0
    low, high = band_of_interest
    if low <= center_hz <= high:
        return 1.0
    distance = min(abs(center_hz - low), abs(center_hz - high))
    span = max(high - low, 1.0)
    return _clamp01(1.0 - distance / span)


def _band_realizability(center_hz: float | None, band_of_interest: tuple[float, float] | None) -> float:
    if center_hz is None:
        return 0.0
    if band_of_interest is None:
        return 0.5
    low, high = band_of_interest
    band_mid = 0.5 * (low + high)
    span = max(high - low, 1.0)
    return _clamp01(1.0 - abs(center_hz - band_mid) / (1.5 * span))


def _l3_alignment_score(
    band_index: int,
    matched_anchor_label: str,
    l3_summary: dict | None,
    fallback_anchor_score: float,
) -> float:
    if not l3_summary:
        return fallback_anchor_score * 0.85 if matched_anchor_label else 0.0
    consensus = l3_summary.get("consensus_alignment", [])
    for item in consensus:
        if int(item.get("band_index", -1)) == int(band_index):
            return _clamp01(float(item.get("score", fallback_anchor_score)))
    tool_results = l3_summary.get("tool_results", {})
    for result in tool_results.values():
        for alignment in result.get("anchor_alignment", []):
            if alignment.get("label") == matched_anchor_label:
                error_hz = abs(float(alignment.get("error_hz", 0.0)))
                scale = max(float(alignment.get("anchor_frequency_hz", 1.0)) * 0.3, 500.0)
                return _clamp01(1.0 - error_hz / scale)
    return fallback_anchor_score


def build_gap_candidates(
    l1_summary: dict | None,
    l2_summary: dict | None,
    band_of_interest: tuple[float, float] | None = None,
    anchors: tuple[L3Anchor, ...] | list[L3Anchor] = (),
    l3_summary: dict | None = None,
) -> list[GapCandidate]:
    """Convert solver summaries into rankable :class:`GapCandidate` objects."""

    candidates: list[GapCandidate] = []
    anchors = tuple(anchors)

    if l2_summary is not None and l2_summary.get("candidates"):
        raw_candidates = list(l2_summary["candidates"])
        max_power = max((cand.get("power_proxy", 0.0) for cand in raw_candidates), default=1.0) or 1.0
        anchor_map = fit_anchor_map(
            [float(cand.get("frequency_hz", 0.0)) for cand in raw_candidates],
            anchors,
        )
        for raw in raw_candidates:
            raw_frequency_hz = float(raw.get("frequency_hz", 0.0))
            anchored_frequency_hz = anchor_map.apply(raw_frequency_hz)
            raw_center_hz = float(raw.get("gap_center_hz", raw_frequency_hz))
            anchored_center_hz = anchor_map.apply(raw_center_hz)
            target_score = _band_score(anchored_frequency_hz, band_of_interest)
            realizability = _band_realizability(anchored_center_hz, band_of_interest)
            anchor_s, anchor_label, anchor_error_hz = anchor_score(anchored_frequency_hz, anchors)
            l3_align = _l3_alignment_score(int(raw["band_index"]), anchor_label, l3_summary, anchor_s)
            notes: list[str] = []
            if anchor_label:
                notes.append(f"matched_anchor={anchor_label}")
            if anchor_error_hz is not None:
                notes.append(f"anchor_error_hz={anchor_error_hz:.3f}")
            if anchored_frequency_hz is not None:
                notes.append(f"anchored_frequency_hz={anchored_frequency_hz:.3f}")
            candidates.append(
                GapCandidate(
                    band_index=int(raw["band_index"]),
                    omega_min=float(raw["omega_min"]),
                    omega_max=float(raw["omega_max"]),
                    tr_frequencies=(float(raw["omega_tr"]),),
                    source="l2",
                    center_frequency_hz=anchored_center_hz,
                    raw_frequency_hz=raw_frequency_hz,
                    anchored_frequency_hz=anchored_frequency_hz,
                    matched_anchor_label=anchor_label,
                    suppression_margin=_clamp01(float(raw.get("suppression_margin", 0.0))),
                    localization_score=_clamp01(float(raw.get("localization_score", 0.0))),
                    harvestability_score=_clamp01(float(raw.get("power_proxy", 0.0) / max_power)),
                    robustness_score=_clamp01(float(raw.get("robustness_score", 0.0))),
                    realizability_score=realizability,
                    target_band_score=target_score,
                    anchor_score=anchor_s,
                    l3_alignment_score=l3_align,
                    notes=tuple(notes),
                )
            )

    if not candidates and l1_summary is not None:
        tr = l1_summary["tr_mode"]
        gap = l1_summary["bandgap"]
        raw_frequency_hz = float(l1_summary.get("tr_frequency_hz", tr["omega"]))
        anchor_map = fit_anchor_map([raw_frequency_hz], anchors)
        anchored_frequency_hz = anchor_map.apply(raw_frequency_hz)
        target_score = _band_score(anchored_frequency_hz, band_of_interest)
        anchor_s, anchor_label, _ = anchor_score(anchored_frequency_hz, anchors)
        candidates.append(
            GapCandidate(
                band_index=1,
                omega_min=float(gap["omega_min"]),
                omega_max=float(gap["omega_max"]),
                tr_frequencies=(float(tr["omega"]),),
                source="l1",
                center_frequency_hz=anchored_frequency_hz,
                raw_frequency_hz=raw_frequency_hz,
                anchored_frequency_hz=anchored_frequency_hz,
                matched_anchor_label=anchor_label,
                suppression_margin=_clamp01(-float(l1_summary["transmission_at_tr_power_peak_db"]) / 120.0),
                localization_score=_clamp01(float(tr["eta"])),
                harvestability_score=1.0,
                robustness_score=_clamp01(float(l1_summary["q_factor"]) / 150.0),
                realizability_score=_band_realizability(anchored_frequency_hz, band_of_interest),
                target_band_score=target_score,
                anchor_score=anchor_s,
                l3_alignment_score=anchor_s,
                notes=("l1_fallback",),
            )
        )

    return candidates
