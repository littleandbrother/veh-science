"""L2↔L3 calibration utilities for executable replay."""

from __future__ import annotations

from dataclasses import dataclass
from math import exp, sqrt
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np

from veh_scientist.discover.utils import ensure_dir, write_csv, write_json
from veh_scientist.interfaces import DiscoverTaskCard

L3_PROTOCOL_VERSION = "l3-protocol-1.0"


@dataclass(frozen=True)
class AffineCalibrationMap:
    """Monotone affine frequency map used for L2→L3 retuning."""

    slope: float = 1.0
    intercept: float = 0.0

    def apply(self, value: float | None) -> float | None:
        if value is None:
            return None
        return float(self.slope * float(value) + self.intercept)

    def compose(self, after: "AffineCalibrationMap") -> "AffineCalibrationMap":
        """Return ``after(self(x))`` as a new map."""
        return AffineCalibrationMap(
            slope=float(after.slope * self.slope),
            intercept=float(after.slope * self.intercept + after.intercept),
        )


@dataclass(frozen=True)
class WidthCalibration:
    """Stopband width scaling after center-frequency calibration."""

    scale: float = 1.0

    def apply(self, width: float | None) -> float | None:
        if width is None:
            return None
        return float(max(0.0, self.scale * float(width)))


@dataclass(frozen=True)
class ResidualCalibrationModel:
    """Residual/error model wrapped around the affine frequency calibration."""

    residual_bias_hz: float = 0.0
    base_sigma_hz: float = 0.0
    leave_one_out_rmse_hz: float = 0.0
    anchor_min_hz: float | None = None
    anchor_max_hz: float | None = None
    anchor_span_hz: float = 1.0
    penalty_slope_hz_per_span: float = 0.0
    support: int = 0
    confidence_level: float = 0.95

    def normalized_distance(self, raw_frequency_hz: float | None) -> float:
        if raw_frequency_hz is None or self.anchor_min_hz is None or self.anchor_max_hz is None:
            return 0.0
        value = float(raw_frequency_hz)
        if self.anchor_min_hz <= value <= self.anchor_max_hz:
            return 0.0
        distance = self.anchor_min_hz - value if value < self.anchor_min_hz else value - self.anchor_max_hz
        return float(max(0.0, distance / max(self.anchor_span_hz, 1.0)))

    def extrapolation_penalty(self, raw_frequency_hz: float | None) -> float:
        return float(self.penalty_slope_hz_per_span * self.normalized_distance(raw_frequency_hz))

    def sigma(self, raw_frequency_hz: float | None) -> float:
        penalty = self.extrapolation_penalty(raw_frequency_hz)
        return float(max(1.0e-9, sqrt(max(self.base_sigma_hz, 0.0) ** 2 + penalty**2)))

    def confidence_interval(self, mapped_frequency_hz: float | None, raw_frequency_hz: float | None) -> tuple[float, float] | None:
        if mapped_frequency_hz is None:
            return None
        # z≈1.96 for 95% CI. We keep it fixed because the replay stack currently
        # does not require exact Student-t corrections for low support counts.
        z_value = 1.96
        sigma = self.sigma(raw_frequency_hz)
        return (float(mapped_frequency_hz - z_value * sigma), float(mapped_frequency_hz + z_value * sigma))

    def confidence_score(self, raw_frequency_hz: float | None) -> float:
        scale = max(0.2 * self.anchor_span_hz, 250.0)
        sigma = self.sigma(raw_frequency_hz)
        return float(max(0.1, min(1.0, exp(-sigma / scale))))



def _clamp01(value: float) -> float:
    return float(max(0.0, min(1.0, value)))



def _fit_affine(xs: list[float], ys: list[float]) -> AffineCalibrationMap:
    xs = [float(x) for x in xs if np.isfinite(float(x))]
    ys = [float(y) for y in ys if np.isfinite(float(y))]
    if not xs or not ys or len(xs) != len(ys):
        return AffineCalibrationMap()
    if len(xs) == 1:
        x = xs[0]
        y = ys[0]
        if abs(x) < 1.0e-12:
            return AffineCalibrationMap()
        slope = y / x
        return AffineCalibrationMap(slope=float(max(slope, 1.0e-9)), intercept=0.0)
    slope, intercept = np.polyfit(np.array(xs, dtype=float), np.array(ys, dtype=float), deg=1)
    if not np.isfinite(slope) or slope <= 0.0:
        return AffineCalibrationMap()
    if not np.isfinite(intercept):
        intercept = 0.0
    return AffineCalibrationMap(slope=float(slope), intercept=float(intercept))



def _rmse(pairs: list[tuple[float, float]]) -> float:
    if not pairs:
        return 0.0
    return float(sqrt(sum((a - b) ** 2 for a, b in pairs) / len(pairs)))



def _mae(values: list[float]) -> float:
    if not values:
        return 0.0
    return float(sum(abs(v) for v in values) / len(values))



def _candidate_rows(l2_summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [dict(row) for row in l2_summary.get("candidates", [])]
    stopbands_hz = l2_summary.get("stopbands_hz", [])
    for row in rows:
        band_index = int(row.get("band_index", 0))
        raw_stopband = row.get("raw_stopband_hz")
        if raw_stopband is None and 0 < band_index <= len(stopbands_hz):
            stopband_row = stopbands_hz[band_index - 1]
            row["raw_stopband_hz"] = (
                float(stopband_row.get("frequency_min_hz", 0.0)),
                float(stopband_row.get("frequency_max_hz", 0.0)),
            )
        if row.get("raw_frequency_hz") is None and row.get("frequency_hz") is not None:
            row["raw_frequency_hz"] = float(row["frequency_hz"])
    return rows



def _anchor_lookup(task: DiscoverTaskCard) -> dict[int, dict[str, Any]]:
    lookup: dict[int, dict[str, Any]] = {}
    for anchor in task.l3_anchors:
        if anchor.band_index is not None:
            lookup[int(anchor.band_index)] = {
                "label": anchor.label,
                "frequency_hz": float(anchor.frequency_hz),
                "stopband_hz": tuple(float(v) for v in anchor.stopband_hz) if anchor.stopband_hz is not None else None,
                "target_power_mw": anchor.target_power_mw,
                "target_transmission_db": anchor.target_transmission_db,
                "target_pef": anchor.target_pef,
            }
    return lookup



def _closest_candidate(anchor_frequency_hz: float, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    return min(rows, key=lambda row: abs(float(row.get("raw_frequency_hz", row.get("frequency_hz", 0.0))) - anchor_frequency_hz))



def normalize_tool_result(
    engine: str,
    result: dict[str, Any],
    request: dict[str, Any],
    task: DiscoverTaskCard,
) -> dict[str, Any]:
    """Normalize a MATLAB/COMSOL result into the strict L3 protocol."""

    candidates = [dict(row) for row in request.get("candidate_targets", [])]
    anchors = _anchor_lookup(task)
    normalized: dict[str, Any] = {
        "protocol_version": result.get("protocol_version", L3_PROTOCOL_VERSION),
        "engine": result.get("engine", engine),
        "status": result.get("status", "failed"),
        "notes": result.get("notes", ""),
        "frequency_pairs": [dict(item) for item in result.get("frequency_pairs", [])],
        "stopband_pairs": [dict(item) for item in result.get("stopband_pairs", [])],
        "anchor_alignment": [dict(item) for item in result.get("anchor_alignment", [])],
        "curve_artifacts": dict(result.get("curve_artifacts", {})),
    }

    if not normalized["frequency_pairs"]:
        for item in normalized["anchor_alignment"]:
            label = str(item.get("label", "")).strip()
            band_index = None
            for idx, anchor in anchors.items():
                if anchor["label"] == label:
                    band_index = idx
                    break
            if band_index is None:
                continue
            candidate = next((row for row in candidates if int(row.get("band_index", -1)) == band_index), None)
            raw_frequency_hz = float(item.get("best_frequency_hz", 0.0) or 0.0)
            if candidate is not None and raw_frequency_hz <= 0.0:
                raw_frequency_hz = float(candidate.get("raw_frequency_hz", candidate.get("frequency_hz", 0.0)))
            normalized["frequency_pairs"].append(
                {
                    "band_index": band_index,
                    "label": label,
                    "raw_frequency_hz": raw_frequency_hz,
                    "l3_frequency_hz": float(item.get("anchor_frequency_hz", anchors[band_index]["frequency_hz"])),
                    "source": "anchor_alignment",
                }
            )

    if not normalized["stopband_pairs"]:
        for row in normalized["frequency_pairs"]:
            band_index = int(row.get("band_index", 0))
            candidate = next((item for item in candidates if int(item.get("band_index", -1)) == band_index), None)
            anchor = anchors.get(band_index)
            raw_stopband_hz = None if candidate is None else candidate.get("raw_stopband_hz")
            target_stopband_hz = None if anchor is None else anchor.get("stopband_hz")
            if raw_stopband_hz is None or target_stopband_hz is None:
                continue
            normalized["stopband_pairs"].append(
                {
                    "band_index": band_index,
                    "label": anchor["label"],
                    "raw_stopband_hz": [float(raw_stopband_hz[0]), float(raw_stopband_hz[1])],
                    "l3_stopband_hz": [float(target_stopband_hz[0]), float(target_stopband_hz[1])],
                    "source": row.get("source", "anchor_alignment"),
                }
            )

    return normalized



def _fallback_protocol(task: DiscoverTaskCard, request: dict[str, Any]) -> dict[str, Any]:
    rows = [dict(row) for row in request.get("candidate_targets", [])]
    anchors = _anchor_lookup(task)
    frequency_pairs: list[dict[str, Any]] = []
    stopband_pairs: list[dict[str, Any]] = []
    for band_index, anchor in anchors.items():
        candidate = next((row for row in rows if int(row.get("band_index", -1)) == band_index), None)
        if candidate is None:
            candidate = _closest_candidate(anchor["frequency_hz"], rows)
        if candidate is None:
            continue
        raw_frequency_hz = float(candidate.get("raw_frequency_hz", candidate.get("frequency_hz", 0.0)))
        frequency_pairs.append(
            {
                "band_index": band_index,
                "label": anchor["label"],
                "raw_frequency_hz": raw_frequency_hz,
                "l3_frequency_hz": float(anchor["frequency_hz"]),
                "source": "paper_anchor_fallback",
            }
        )
        raw_stopband_hz = candidate.get("raw_stopband_hz")
        target_stopband_hz = anchor.get("stopband_hz")
        if raw_stopband_hz is not None and target_stopband_hz is not None:
            stopband_pairs.append(
                {
                    "band_index": band_index,
                    "label": anchor["label"],
                    "raw_stopband_hz": [float(raw_stopband_hz[0]), float(raw_stopband_hz[1])],
                    "l3_stopband_hz": [float(target_stopband_hz[0]), float(target_stopband_hz[1])],
                    "source": "paper_anchor_fallback",
                }
            )
    return {
        "protocol_version": L3_PROTOCOL_VERSION,
        "engine": "anchor-fallback",
        "status": "passed" if frequency_pairs else "failed",
        "notes": "No passed MATLAB/COMSOL result provided; used paper anchors as low-confidence calibration targets.",
        "frequency_pairs": frequency_pairs,
        "stopband_pairs": stopband_pairs,
        "anchor_alignment": [],
        "curve_artifacts": {},
    }



def _aggregate_protocols(
    task: DiscoverTaskCard,
    request: dict[str, Any],
    tool_results: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    protocols: list[dict[str, Any]] = []
    for engine, result in tool_results.items():
        protocols.append(normalize_tool_result(engine, result, request, task))
    passed_protocols = [proto for proto in protocols if str(proto.get("status", "")).lower() == "passed"]
    effective_protocols = passed_protocols or [_fallback_protocol(task, request)]

    freq_by_band: dict[int, list[dict[str, Any]]] = {}
    stop_by_band: dict[int, list[dict[str, Any]]] = {}
    for proto in effective_protocols:
        for pair in proto.get("frequency_pairs", []):
            freq_by_band.setdefault(int(pair.get("band_index", 0)), []).append(pair)
        for pair in proto.get("stopband_pairs", []):
            stop_by_band.setdefault(int(pair.get("band_index", 0)), []).append(pair)

    frequency_pairs: list[dict[str, Any]] = []
    for band_index, items in sorted(freq_by_band.items()):
        raw_freqs = [float(item.get("raw_frequency_hz", 0.0)) for item in items if item.get("raw_frequency_hz") is not None]
        target_freqs = [float(item.get("l3_frequency_hz", 0.0)) for item in items if item.get("l3_frequency_hz") is not None]
        labels = [str(item.get("label", "")) for item in items if item.get("label")]
        if not raw_freqs or not target_freqs:
            continue
        sources = sorted({str(item.get("source", proto.get("engine", "unknown"))) for item in items})
        frequency_pairs.append(
            {
                "band_index": band_index,
                "label": labels[0] if labels else "",
                "raw_frequency_hz": float(np.mean(raw_freqs)),
                "l3_frequency_hz": float(np.mean(target_freqs)),
                "n_support": len(items),
                "sources": sources,
            }
        )

    stopband_pairs: list[dict[str, Any]] = []
    for band_index, items in sorted(stop_by_band.items()):
        raw_intervals = [item.get("raw_stopband_hz") for item in items if item.get("raw_stopband_hz") is not None]
        target_intervals = [item.get("l3_stopband_hz") for item in items if item.get("l3_stopband_hz") is not None]
        labels = [str(item.get("label", "")) for item in items if item.get("label")]
        if not raw_intervals or not target_intervals:
            continue
        raw_mean = np.mean(np.array(raw_intervals, dtype=float), axis=0)
        target_mean = np.mean(np.array(target_intervals, dtype=float), axis=0)
        stopband_pairs.append(
            {
                "band_index": band_index,
                "label": labels[0] if labels else "",
                "raw_stopband_hz": [float(raw_mean[0]), float(raw_mean[1])],
                "l3_stopband_hz": [float(target_mean[0]), float(target_mean[1])],
                "n_support": len(items),
            }
        )

    return protocols, frequency_pairs, stopband_pairs



def _fit_width_scale(stopband_pairs: list[dict[str, Any]], freq_map: AffineCalibrationMap) -> WidthCalibration:
    ratios: list[float] = []
    for pair in stopband_pairs:
        raw_low, raw_high = (float(v) for v in pair["raw_stopband_hz"])
        target_low, target_high = (float(v) for v in pair["l3_stopband_hz"])
        mapped_width = max(float(freq_map.apply(raw_high)) - float(freq_map.apply(raw_low)), 1.0e-9)
        target_width = max(target_high - target_low, 1.0e-9)
        ratios.append(target_width / mapped_width)
    if not ratios:
        return WidthCalibration()
    scale = float(np.median(np.array(ratios, dtype=float)))
    if not np.isfinite(scale) or scale <= 0.0:
        scale = 1.0
    return WidthCalibration(scale=scale)



def _apply_stopband_map(
    interval: tuple[float, float] | list[float] | None,
    freq_map: AffineCalibrationMap,
    width_map: WidthCalibration,
) -> tuple[float, float] | None:
    if interval is None:
        return None
    low, high = (float(v) for v in interval)
    mapped_low = float(freq_map.apply(low))
    mapped_high = float(freq_map.apply(high))
    center = 0.5 * (mapped_low + mapped_high)
    width = width_map.apply(mapped_high - mapped_low) or 0.0
    return (float(center - 0.5 * width), float(center + 0.5 * width))



def _stopband_error(interval_a: tuple[float, float] | None, interval_b: tuple[float, float] | None) -> float | None:
    if interval_a is None or interval_b is None:
        return None
    return float(0.5 * (abs(interval_a[0] - interval_b[0]) + abs(interval_a[1] - interval_b[1])))



def _normalized_range_distance(value: float, anchors: list[float]) -> float:
    if not anchors:
        return 0.0
    low = min(anchors)
    high = max(anchors)
    span = max(high - low, 1.0)
    if low <= value <= high:
        return 0.0
    if value < low:
        return float((low - value) / span)
    return float((value - high) / span)



def _fit_residual_model(
    frequency_pairs: list[dict[str, Any]],
    frequency_map: AffineCalibrationMap,
) -> tuple[ResidualCalibrationModel, list[dict[str, Any]]]:
    raw_values = [float(pair["raw_frequency_hz"]) for pair in frequency_pairs if pair.get("raw_frequency_hz") is not None]
    target_values = [float(pair["l3_frequency_hz"]) for pair in frequency_pairs if pair.get("l3_frequency_hz") is not None]
    if not raw_values or not target_values or len(raw_values) != len(target_values):
        return ResidualCalibrationModel(), []

    mapped_values = [float(frequency_map.apply(value)) for value in raw_values]
    residuals = [mapped - target for mapped, target in zip(mapped_values, target_values)]
    absolute_residuals = [abs(value) for value in residuals]
    base_sigma = max(float(np.std(np.array(residuals, dtype=float), ddof=0)), _rmse(list(zip(mapped_values, target_values))), 1.0e-9)
    bias = float(np.mean(np.array(residuals, dtype=float))) if residuals else 0.0

    loo_records: list[dict[str, Any]] = []
    penalty_slope = 0.0
    if len(raw_values) >= 2:
        distances: list[float] = []
        errors: list[float] = []
        for idx, (raw_frequency, target_frequency) in enumerate(zip(raw_values, target_values)):
            other_raws = raw_values[:idx] + raw_values[idx + 1 :]
            other_targets = target_values[:idx] + target_values[idx + 1 :]
            loo_map = _fit_affine(other_raws, other_targets)
            predicted = float(loo_map.apply(raw_frequency))
            residual = float(predicted - target_frequency)
            distance = _normalized_range_distance(raw_frequency, other_raws)
            loo_records.append(
                {
                    "index": idx,
                    "raw_frequency_hz": raw_frequency,
                    "target_frequency_hz": target_frequency,
                    "predicted_frequency_hz": predicted,
                    "loo_residual_hz": residual,
                    "normalized_distance": distance,
                }
            )
            distances.append(distance)
            errors.append(abs(residual))
        if len(distances) >= 2 and np.max(np.abs(np.array(distances, dtype=float) - np.mean(distances))) > 1.0e-9:
            slope, intercept = np.polyfit(np.array(distances, dtype=float), np.array(errors, dtype=float), deg=1)
            if np.isfinite(slope) and slope > 0.0:
                penalty_slope = float(slope)
            if np.isfinite(intercept) and intercept > base_sigma:
                base_sigma = float(intercept)
        elif errors:
            penalty_slope = float(np.max(errors))
    loo_rmse = _rmse([(record["predicted_frequency_hz"], record["target_frequency_hz"]) for record in loo_records])
    base_sigma = max(base_sigma, 0.5 * loo_rmse)

    anchor_min = min(raw_values) if raw_values else None
    anchor_max = max(raw_values) if raw_values else None
    anchor_span = max((anchor_max or 0.0) - (anchor_min or 0.0), 1.0)
    model = ResidualCalibrationModel(
        residual_bias_hz=bias,
        base_sigma_hz=base_sigma,
        leave_one_out_rmse_hz=loo_rmse,
        anchor_min_hz=anchor_min,
        anchor_max_hz=anchor_max,
        anchor_span_hz=anchor_span,
        penalty_slope_hz_per_span=float(max(0.0, penalty_slope)),
        support=len(raw_values),
        confidence_level=0.95,
    )
    return model, loo_records



def _build_calibrated_l2_summary(
    l2_summary: dict[str, Any],
    frequency_map: AffineCalibrationMap,
    width_map: WidthCalibration,
    residual_model: ResidualCalibrationModel,
    frequency_pairs: list[dict[str, Any]],
    stopband_pairs: list[dict[str, Any]],
    confidence: float,
    source_label: str,
) -> dict[str, Any]:
    summary = {key: value for key, value in l2_summary.items()}
    pair_by_band = {int(pair["band_index"]): pair for pair in frequency_pairs}
    stop_by_band = {int(pair["band_index"]): pair for pair in stopband_pairs}
    rows = _candidate_rows(l2_summary)
    calibrated_rows: list[dict[str, Any]] = []
    for row in rows:
        band_index = int(row.get("band_index", 0))
        raw_frequency_hz = float(row.get("raw_frequency_hz", row.get("frequency_hz", 0.0)))
        calibrated_frequency_hz = float(frequency_map.apply(raw_frequency_hz))
        raw_center_hz = float(row.get("gap_center_hz", raw_frequency_hz))
        calibrated_center_hz = float(frequency_map.apply(raw_center_hz))
        raw_stopband_hz = row.get("raw_stopband_hz")
        calibrated_stopband_hz = _apply_stopband_map(raw_stopband_hz, frequency_map, width_map)
        matched_pair = pair_by_band.get(band_index)
        matched_stop = stop_by_band.get(band_index)
        target_stop = None if matched_stop is None else tuple(float(v) for v in matched_stop["l3_stopband_hz"])
        stopband_error_hz = _stopband_error(calibrated_stopband_hz, target_stop)
        sigma_hz = residual_model.sigma(raw_frequency_hz)
        ci_hz = residual_model.confidence_interval(calibrated_frequency_hz, raw_frequency_hz)
        extrapolation_penalty = residual_model.extrapolation_penalty(raw_frequency_hz)
        band_match_factor = 1.0 if matched_pair is not None else 0.55
        uncertainty_score = _clamp01(1.0 / (1.0 + sigma_hz / max(0.2 * residual_model.anchor_span_hz, 250.0)))
        candidate_confidence = float(max(0.1, min(1.0, confidence * residual_model.confidence_score(raw_frequency_hz) * band_match_factor)))
        calibrated_rows.append(
            {
                **row,
                "frequency_hz": calibrated_frequency_hz,
                "calibrated_frequency_hz": calibrated_frequency_hz,
                "gap_center_hz": calibrated_center_hz,
                "raw_frequency_hz": raw_frequency_hz,
                "raw_stopband_hz": None if raw_stopband_hz is None else list(raw_stopband_hz),
                "calibrated_stopband_hz": None if calibrated_stopband_hz is None else list(calibrated_stopband_hz),
                "matched_anchor_label": "" if matched_pair is None else str(matched_pair.get("label", "")),
                "stopband_error_hz": stopband_error_hz,
                "uncertainty_sigma_hz": sigma_hz,
                "confidence_interval_hz": None if ci_hz is None else [float(ci_hz[0]), float(ci_hz[1])],
                "extrapolation_penalty": extrapolation_penalty,
                "uncertainty_score": uncertainty_score,
                "calibration_confidence": candidate_confidence,
                "calibration_source": source_label,
            }
        )
    summary["raw_candidates"] = rows
    summary["candidates"] = calibrated_rows
    summary["frequency_map"] = {"slope": frequency_map.slope, "intercept": frequency_map.intercept}
    summary["width_map"] = {"scale": width_map.scale}
    summary["residual_model"] = {
        "residual_bias_hz": residual_model.residual_bias_hz,
        "base_sigma_hz": residual_model.base_sigma_hz,
        "leave_one_out_rmse_hz": residual_model.leave_one_out_rmse_hz,
        "anchor_min_hz": residual_model.anchor_min_hz,
        "anchor_max_hz": residual_model.anchor_max_hz,
        "anchor_span_hz": residual_model.anchor_span_hz,
        "penalty_slope_hz_per_span": residual_model.penalty_slope_hz_per_span,
        "support": residual_model.support,
        "confidence_level": residual_model.confidence_level,
    }
    calibrated_stopbands_hz: list[dict[str, Any]] = []
    for idx, stopband in enumerate(l2_summary.get("stopbands_hz", []), start=1):
        raw_interval = (float(stopband.get("frequency_min_hz", 0.0)), float(stopband.get("frequency_max_hz", 0.0)))
        calibrated_interval = _apply_stopband_map(raw_interval, frequency_map, width_map)
        calibrated_stopbands_hz.append(
            {
                "band_index": idx,
                "raw_frequency_min_hz": raw_interval[0],
                "raw_frequency_max_hz": raw_interval[1],
                "frequency_min_hz": None if calibrated_interval is None else calibrated_interval[0],
                "frequency_max_hz": None if calibrated_interval is None else calibrated_interval[1],
            }
        )
    summary["stopbands_hz"] = calibrated_stopbands_hz
    return summary



def _plot_calibration_frequencies(path: Path, frequency_pairs: list[dict[str, Any]], freq_map: AffineCalibrationMap) -> None:
    fig = plt.figure(figsize=(7.2, 4.8))
    ax = fig.add_subplot(111)
    raw = [float(item["raw_frequency_hz"]) for item in frequency_pairs]
    target = [float(item["l3_frequency_hz"]) for item in frequency_pairs]
    calibrated = [float(freq_map.apply(value)) for value in raw]
    if raw:
        ax.scatter(raw, target, label="L3 targets")
        ax.scatter(raw, calibrated, label="calibrated L2")
        x_grid = np.linspace(min(raw) * 0.9, max(raw) * 1.05, 100)
        y_grid = [float(freq_map.apply(x)) for x in x_grid]
        ax.plot(x_grid, y_grid, label="frequency map")
    ax.set_xlabel("Raw L2 frequency (Hz)")
    ax.set_ylabel("Target / calibrated frequency (Hz)")
    ax.set_title("L2→L3 frequency calibration")
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)



def _plot_calibration_stopbands(
    path: Path,
    stopband_pairs: list[dict[str, Any]],
    freq_map: AffineCalibrationMap,
    width_map: WidthCalibration,
) -> None:
    fig = plt.figure(figsize=(7.2, 4.8))
    ax = fig.add_subplot(111)
    if stopband_pairs:
        for idx, pair in enumerate(stopband_pairs, start=1):
            raw_interval = tuple(float(v) for v in pair["raw_stopband_hz"])
            target_interval = tuple(float(v) for v in pair["l3_stopband_hz"])
            calibrated_interval = _apply_stopband_map(raw_interval, freq_map, width_map)
            y_base = float(idx)
            ax.hlines(y_base + 0.2, raw_interval[0], raw_interval[1], linewidth=3, label="raw" if idx == 1 else None)
            if calibrated_interval is not None:
                ax.hlines(y_base, calibrated_interval[0], calibrated_interval[1], linewidth=3, label="calibrated" if idx == 1 else None)
            ax.hlines(y_base - 0.2, target_interval[0], target_interval[1], linewidth=3, label="target" if idx == 1 else None)
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel("Band index")
    ax.set_title("Raw vs calibrated stopbands")
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)



def _plot_uncertainty(path: Path, calibrated_summary: dict[str, Any]) -> None:
    rows = [dict(row) for row in calibrated_summary.get("candidates", [])]
    fig = plt.figure(figsize=(7.2, 4.8))
    ax = fig.add_subplot(111)
    if rows:
        x_values = [float(row.get("calibrated_frequency_hz", row.get("frequency_hz", 0.0))) for row in rows]
        y_values = [float(row.get("uncertainty_sigma_hz", 0.0) or 0.0) for row in rows]
        ax.scatter(x_values, y_values)
        for row, x_value, y_value in zip(rows, x_values, y_values):
            ax.annotate(f"gap {row.get('band_index')}", (x_value, y_value), fontsize=7)
    ax.set_xlabel("Calibrated frequency (Hz)")
    ax.set_ylabel("σ uncertainty (Hz)")
    ax.set_title("Candidate-level calibration uncertainty")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)



def run_l2_l3_calibration(
    output_dir: str | Path,
    task: DiscoverTaskCard,
    request: dict[str, Any],
    l2_summary: dict[str, Any],
    tool_results: dict[str, Any],
    max_iterations: int = 3,
) -> dict[str, Any]:
    """Run the L2→L3 calibration loop and emit calibrated L2 artifacts."""
    output_dir = ensure_dir(output_dir)
    protocols, frequency_pairs, stopband_pairs = _aggregate_protocols(task, request, tool_results)
    raw_pairs = [(float(pair["raw_frequency_hz"]), float(pair["l3_frequency_hz"])) for pair in frequency_pairs]
    pre_rmse = _rmse(raw_pairs)

    current_map = AffineCalibrationMap()
    iteration_records: list[dict[str, Any]] = []
    current_values = [float(pair["raw_frequency_hz"]) for pair in frequency_pairs]
    target_values = [float(pair["l3_frequency_hz"]) for pair in frequency_pairs]
    previous_rmse = pre_rmse
    for iteration in range(1, max_iterations + 1):
        delta_map = _fit_affine(current_values, target_values)
        current_map = current_map.compose(delta_map)
        current_values = [float(current_map.apply(pair["raw_frequency_hz"])) for pair in frequency_pairs]
        rmse = _rmse(list(zip(current_values, target_values)))
        iteration_records.append(
            {
                "iteration": iteration,
                "delta_map": {"slope": delta_map.slope, "intercept": delta_map.intercept},
                "composed_map": {"slope": current_map.slope, "intercept": current_map.intercept},
                "rmse_hz": rmse,
            }
        )
        if abs(previous_rmse - rmse) < 1.0e-6:
            break
        previous_rmse = rmse

    width_map = _fit_width_scale(stopband_pairs, current_map)
    residual_model, loo_records = _fit_residual_model(frequency_pairs, current_map)
    calibrated_stop_errors: list[float] = []
    raw_stop_errors: list[float] = []
    for pair in stopband_pairs:
        raw_interval = tuple(float(v) for v in pair["raw_stopband_hz"])
        target_interval = tuple(float(v) for v in pair["l3_stopband_hz"])
        raw_stop_errors.extend([raw_interval[0] - target_interval[0], raw_interval[1] - target_interval[1]])
        calibrated_interval = _apply_stopband_map(raw_interval, current_map, width_map)
        if calibrated_interval is not None:
            calibrated_stop_errors.extend([calibrated_interval[0] - target_interval[0], calibrated_interval[1] - target_interval[1]])

    post_rmse = _rmse([(float(current_map.apply(pair["raw_frequency_hz"])), float(pair["l3_frequency_hz"])) for pair in frequency_pairs])
    passed_tools = sum(1 for proto in protocols if str(proto.get("status", "")).lower() == "passed")
    base_confidence = 0.15 + 0.16 * len(frequency_pairs) + 0.08 * len(stopband_pairs) + 0.12 * passed_tools
    residual_scale = max(0.25 * residual_model.anchor_span_hz, 500.0)
    residual_factor = float(max(0.15, exp(-post_rmse / residual_scale))) if frequency_pairs else 0.1
    confidence = _clamp01(base_confidence * residual_factor)
    source_label = "tool-consensus" if passed_tools else "paper-anchor-fallback"
    if passed_tools == 0:
        confidence = max(0.1, confidence * 0.55)

    calibrated_l2_summary = _build_calibrated_l2_summary(
        l2_summary,
        frequency_map=current_map,
        width_map=width_map,
        residual_model=residual_model,
        frequency_pairs=frequency_pairs,
        stopband_pairs=stopband_pairs,
        confidence=confidence,
        source_label=source_label,
    )

    candidate_uncertainty_rows = [
        {
            "band_index": row.get("band_index"),
            "calibrated_frequency_hz": row.get("calibrated_frequency_hz", row.get("frequency_hz")),
            "uncertainty_sigma_hz": row.get("uncertainty_sigma_hz"),
            "confidence_interval_hz": row.get("confidence_interval_hz"),
            "extrapolation_penalty": row.get("extrapolation_penalty"),
            "uncertainty_score": row.get("uncertainty_score"),
            "calibration_confidence": row.get("calibration_confidence"),
        }
        for row in calibrated_l2_summary.get("candidates", [])
    ]

    summary = {
        "protocol_version": L3_PROTOCOL_VERSION,
        "frequency_map": {"slope": current_map.slope, "intercept": current_map.intercept},
        "width_map": {"scale": width_map.scale},
        "residual_model": {
            "residual_bias_hz": residual_model.residual_bias_hz,
            "base_sigma_hz": residual_model.base_sigma_hz,
            "leave_one_out_rmse_hz": residual_model.leave_one_out_rmse_hz,
            "anchor_min_hz": residual_model.anchor_min_hz,
            "anchor_max_hz": residual_model.anchor_max_hz,
            "anchor_span_hz": residual_model.anchor_span_hz,
            "penalty_slope_hz_per_span": residual_model.penalty_slope_hz_per_span,
            "support": residual_model.support,
            "confidence_level": residual_model.confidence_level,
            "leave_one_out_records": loo_records,
        },
        "iterations": iteration_records,
        "frequency_pairs": frequency_pairs,
        "stopband_pairs": stopband_pairs,
        "errors": {
            "pre_rmse_hz": pre_rmse,
            "post_rmse_hz": post_rmse,
            "pre_stopband_mae_hz": _mae(raw_stop_errors),
            "post_stopband_mae_hz": _mae(calibrated_stop_errors),
        },
        "confidence": confidence,
        "source": source_label,
        "normalized_tool_results": protocols,
        "candidate_uncertainty": candidate_uncertainty_rows,
        "calibrated_l2_summary": calibrated_l2_summary,
    }
    write_json(output_dir / "calibration_summary.json", summary)
    write_json(output_dir / "calibrated_l2_summary.json", calibrated_l2_summary)
    write_json(output_dir / "uncertainty_model.json", summary["residual_model"])
    write_csv(
        output_dir / "candidate_uncertainty.csv",
        candidate_uncertainty_rows,
        fieldnames=[
            "band_index",
            "calibrated_frequency_hz",
            "uncertainty_sigma_hz",
            "confidence_interval_hz",
            "extrapolation_penalty",
            "uncertainty_score",
            "calibration_confidence",
        ],
    )
    _plot_calibration_frequencies(output_dir / "frequency_calibration.png", frequency_pairs, current_map)
    _plot_calibration_stopbands(output_dir / "stopband_calibration.png", stopband_pairs, current_map, width_map)
    _plot_uncertainty(output_dir / "uncertainty_calibration.png", calibrated_l2_summary)
    return summary
