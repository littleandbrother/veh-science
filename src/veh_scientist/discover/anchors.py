"""Anchor utilities for retuning L2 candidates against paper and L3 references."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

import numpy as np

from veh_scientist.interfaces import L3Anchor


@dataclass(frozen=True)
class AnchorMap:
    """Monotone affine frequency map from raw L2 frequencies to anchor-aligned values."""

    slope: float = 1.0
    intercept: float = 0.0

    def apply(self, frequency_hz: float | None) -> float | None:
        if frequency_hz is None:
            return None
        return float(self.slope * frequency_hz + self.intercept)


def sorted_anchors(anchors: tuple[L3Anchor, ...] | list[L3Anchor]) -> list[L3Anchor]:
    return sorted(list(anchors), key=lambda anchor: (anchor.band_index or 10**9, anchor.frequency_hz, anchor.label))


def fit_anchor_map(raw_frequencies_hz: list[float], anchors: tuple[L3Anchor, ...] | list[L3Anchor]) -> AnchorMap:
    anchors_sorted = sorted_anchors(anchors)
    raw_sorted = sorted(float(freq) for freq in raw_frequencies_hz if isfinite(freq))
    if not raw_sorted or not anchors_sorted:
        return AnchorMap()
    if len(raw_sorted) == 1 or len(anchors_sorted) == 1:
        raw = raw_sorted[0]
        target = anchors_sorted[0].frequency_hz
        if abs(raw) < 1.0e-12:
            return AnchorMap()
        return AnchorMap(slope=float(target / raw), intercept=0.0)

    n = min(len(raw_sorted), len(anchors_sorted))
    x = np.array(raw_sorted[:n], dtype=float)
    y = np.array([anchor.frequency_hz for anchor in anchors_sorted[:n]], dtype=float)
    slope, intercept = np.polyfit(x, y, deg=1)
    if not np.isfinite(slope) or slope <= 0.0:
        return AnchorMap()
    return AnchorMap(slope=float(slope), intercept=float(intercept))


def closest_anchor(frequency_hz: float | None, anchors: tuple[L3Anchor, ...] | list[L3Anchor]) -> tuple[L3Anchor | None, float | None]:
    if frequency_hz is None:
        return None, None
    anchors_sorted = sorted_anchors(anchors)
    if not anchors_sorted:
        return None, None
    anchor = min(anchors_sorted, key=lambda item: abs(item.frequency_hz - frequency_hz))
    return anchor, float(abs(anchor.frequency_hz - frequency_hz))


def anchor_score(
    frequency_hz: float | None,
    anchors: tuple[L3Anchor, ...] | list[L3Anchor],
    scale_hz: float | None = None,
) -> tuple[float, str, float | None]:
    anchor, error_hz = closest_anchor(frequency_hz, anchors)
    if anchor is None:
        return 0.0, "", None
    if scale_hz is None:
        freqs = [item.frequency_hz for item in sorted_anchors(anchors)]
        if len(freqs) >= 2:
            diffs = [abs(b - a) for a, b in zip(freqs[:-1], freqs[1:])]
            scale_hz = max(min(diffs), 500.0)
        else:
            scale_hz = max(anchor.frequency_hz * 0.35, 500.0)
    score = max(0.0, 1.0 - (error_hz or 0.0) / max(scale_hz, 1.0))
    return float(score), anchor.label, error_hz
