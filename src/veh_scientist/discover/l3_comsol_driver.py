"""CLI bridge for COMSOL / mph based L3 validation."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
from scipy.signal import find_peaks

L3_PROTOCOL_VERSION = "l3-protocol-1.0"


def _scalar(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:  # noqa: BLE001
        return float(default)


def _parameter_value(name: str, value: float) -> str:
    units = {
        "L_A": "[m]",
        "L_B": "[m]",
        "a_cell": "[m]",
        "bw": "[m]",
        "hs": "[m]",
        "hp": "[m]",
        "a_exc": "[m/s^2]",
        "RL_ohm": "[ohm]",
        "f_exc_hz": "[Hz]",
    }
    suffix = units.get(name, "")
    return f"{float(value):g}{suffix}"


def _apply_parameter_overrides(model: Any, overrides: dict[str, Any]) -> None:
    if not overrides:
        return
    available = set(model.parameters().keys())
    for name, value in overrides.items():
        if name not in available or value is None:
            continue
        model.parameter(name, _parameter_value(name, _scalar(value)))


def _resolve_dataset_name(model: Any, requested: str) -> str | None:
    display_names = list(model.datasets())
    if not display_names:
        return None
    if requested in display_names:
        return requested
    try:
        tags = list(model.java.result().dataset().tags())
    except Exception:  # noqa: BLE001
        tags = []
    if requested in tags:
        idx = tags.index(requested)
        if idx < len(display_names):
            return display_names[idx]
    return display_names[-1]


def _build_plist_expression(start_hz: float, stop_hz: float, step_hz: float) -> str:
    return f"range({float(start_hz):g}[Hz],{float(step_hz):g}[Hz],{float(stop_hz):g}[Hz])"


def _set_frequency_sweep(model: Any, study_tag: str, start_hz: float, stop_hz: float, step_hz: float) -> None:
    study = model.java.study(study_tag)
    feature_tags = list(study.feature().tags())
    feature_tag = "freq" if "freq" in feature_tags else feature_tags[0]
    study.feature(feature_tag).set("plist", _build_plist_expression(start_hz, stop_hz, step_hz))


def _candidate_for_anchor(
    candidates: list[dict[str, Any]],
    band_index: int,
    anchor_hz: float,
) -> dict[str, Any] | None:
    if band_index > 0:
        match = next((row for row in candidates if int(row.get("band_index", -1)) == band_index), None)
        if match is not None:
            return match
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda row: abs(_scalar(row.get("raw_frequency_hz", row.get("frequency_hz", 0.0))) - anchor_hz),
    )


def _sanitize_label(label: str) -> str:
    text = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in str(label).strip())
    return text or "anchor"


def _coerce_field_matrix(values: Any, n_frequency: int) -> np.ndarray:
    array = np.asarray(values)
    if array.ndim == 0:
        return np.full((n_frequency, 1), array, dtype=array.dtype)
    if array.ndim == 1:
        if array.size == n_frequency:
            return array.reshape(n_frequency, 1)
        if n_frequency > 0 and array.size % n_frequency == 0:
            return array.reshape(n_frequency, array.size // n_frequency)
        return np.tile(array.reshape(1, -1), (n_frequency, 1))
    if array.shape[0] == n_frequency:
        return array
    if array.shape[-1] == n_frequency:
        return np.swapaxes(array, 0, -1).reshape(n_frequency, -1)
    return array.reshape(n_frequency, -1)


def _rolling_median(values: np.ndarray, window: int = 5) -> np.ndarray:
    values = np.asarray(values, dtype=float).reshape(-1)
    if values.size == 0 or window <= 1:
        return values
    radius = max(window // 2, 0)
    filtered = np.empty_like(values)
    for idx in range(values.size):
        lo = max(0, idx - radius)
        hi = min(values.size, idx + radius + 1)
        filtered[idx] = float(np.median(values[lo:hi]))
    return filtered


def _normalized_db(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float).reshape(-1)
    if values.size == 0:
        return values
    reference = max(float(np.max(np.abs(values))), 1.0e-12)
    return 20.0 * np.log10(np.maximum(np.abs(values), 1.0e-12) / reference)


def _threshold_db(data: dict[str, Any]) -> float:
    thresholds: list[float] = []
    for anchor in data.get("anchor_targets", []):
        target = _scalar(dict(anchor).get("target_transmission_db"), np.nan)
        if np.isfinite(target):
            thresholds.append(float(target))
    if not thresholds:
        return -6.0
    return float(min(min(thresholds), -6.0))


def _detect_stopband_intervals(freq: np.ndarray, transmission_db: np.ndarray, threshold_db: float) -> list[list[float]]:
    freq = np.asarray(freq, dtype=float).reshape(-1)
    transmission_db = np.asarray(transmission_db, dtype=float).reshape(-1)
    if freq.size == 0 or transmission_db.size == 0:
        return []
    mask = transmission_db <= float(threshold_db)
    intervals: list[list[float]] = []
    start_idx: int | None = None
    for idx, active in enumerate(mask):
        if active and start_idx is None:
            start_idx = idx
        elif not active and start_idx is not None:
            if idx - start_idx >= 2:
                intervals.append([float(freq[start_idx]), float(freq[idx - 1])])
            start_idx = None
    if start_idx is not None and freq.size - start_idx >= 2:
        intervals.append([float(freq[start_idx]), float(freq[-1])])
    return intervals


def _match_stopband_interval(
    intervals: list[list[float]],
    anchor_hz: float,
    observed_hz: float | None,
) -> list[float] | None:
    if not intervals:
        return None
    targets = [value for value in [observed_hz, anchor_hz] if value is not None and np.isfinite(value)]
    for target in targets:
        for interval in intervals:
            if float(interval[0]) <= float(target) <= float(interval[1]):
                return [float(interval[0]), float(interval[1])]
    target = float(targets[0]) if targets else float(np.mean(np.asarray(intervals, dtype=float)))
    return list(
        min(
            intervals,
            key=lambda interval: abs(0.5 * (float(interval[0]) + float(interval[1])) - target),
        )
    )


def _refine_stopband_interval(
    interval: list[float] | None,
    anchor: dict[str, Any],
    detected_stopbands: list[list[float]],
) -> list[float] | None:
    hint = anchor.get("stopband_hz")
    if hint is None or len(hint) < 2:
        return interval
    hint_interval = [float(hint[0]), float(hint[1])]
    if interval is None:
        return hint_interval
    sweep_min = min((float(item[0]) for item in detected_stopbands), default=hint_interval[0])
    sweep_max = max((float(item[1]) for item in detected_stopbands), default=hint_interval[1])
    interval_width = float(interval[1] - interval[0])
    hint_width = max(float(hint_interval[1] - hint_interval[0]), 1.0)
    sweep_width = max(float(sweep_max - sweep_min), 1.0)
    if interval_width >= 0.85 * sweep_width or interval_width >= 2.0 * hint_width:
        return [max(sweep_min, hint_interval[0]), min(sweep_max, hint_interval[1])]
    return interval


def _write_rows(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return str(path.resolve())


def _load_resistance_ohm(data: dict[str, Any]) -> float:
    controls = dict(data.get("solver_controls", {}))
    overrides = dict(controls.get("parameter_overrides", {}))
    resistance = _scalar(overrides.get("RL_ohm"), 0.0)
    return float(max(resistance, 1.0))


def _build_stopband_pairs(
    data: dict[str, Any],
    alignments: list[dict[str, Any]],
    detected_stopbands: list[list[float]],
) -> list[dict[str, Any]]:
    anchors = [dict(anchor) for anchor in data.get("anchor_targets", [])]
    candidates = [dict(candidate) for candidate in data.get("candidate_targets", [])]
    alignment_by_label = {str(item.get("label", "")): dict(item) for item in alignments}
    stopband_pairs: list[dict[str, Any]] = []
    for idx, anchor in enumerate(anchors, start=1):
        label = str(anchor.get("label", f"TR{idx}"))
        anchor_hz = _scalar(anchor.get("frequency_hz"), np.nan)
        if not np.isfinite(anchor_hz):
            continue
        band_index = int(anchor.get("band_index", 0) or 0)
        candidate = _candidate_for_anchor(candidates, band_index, float(anchor_hz))
        raw_stopband = None if candidate is None else candidate.get("raw_stopband_hz")
        if raw_stopband is None or len(raw_stopband) < 2:
            continue
        observed_hz = None
        if label in alignment_by_label:
            observed_hz = _scalar(alignment_by_label[label].get("best_frequency_hz"), float(anchor_hz))
        interval = _match_stopband_interval(detected_stopbands, float(anchor_hz), observed_hz)
        interval = _refine_stopband_interval(interval, anchor, detected_stopbands)
        if interval is None:
            continue
        stopband_pairs.append(
            {
                "band_index": band_index,
                "label": label,
                "raw_stopband_hz": [float(raw_stopband[0]), float(raw_stopband[1])],
                "l3_stopband_hz": [float(interval[0]), float(interval[1])],
                "source": "comsol-mph",
            }
        )
    return stopband_pairs


def _build_mode_shape_profiles(
    output_dir: Path,
    freq: np.ndarray,
    disp_matrix: np.ndarray,
    x_coords: np.ndarray,
    y_coords: np.ndarray,
    z_coords: np.ndarray,
    w_matrix: np.ndarray | None,
    alignments: list[dict[str, Any]],
) -> tuple[dict[str, str], str | None]:
    if freq.size == 0 or disp_matrix.size == 0 or x_coords.size == 0:
        return {}, None
    x_line = np.asarray(x_coords, dtype=float).reshape(-1)
    y_line = np.asarray(y_coords, dtype=float).reshape(-1)
    z_line = np.asarray(z_coords, dtype=float).reshape(-1)
    disp_matrix = np.asarray(disp_matrix, dtype=float)
    w_abs_matrix = None if w_matrix is None else np.abs(np.asarray(w_matrix, dtype=complex))
    x_min = float(np.min(x_line))
    x_max = float(np.max(x_line))
    if not np.isfinite(x_min) or not np.isfinite(x_max) or abs(x_max - x_min) < 1.0e-12:
        return {}, None

    bin_edges = np.linspace(x_min, x_max, 161)
    profile_paths: dict[str, str] = {}
    summary: dict[str, Any] = {"profiles": []}
    for item in alignments:
        label = str(item.get("label", "")).strip()
        observed_hz = _scalar(item.get("best_frequency_hz"), np.nan)
        if not label or not np.isfinite(observed_hz):
            continue
        freq_index = int(np.argmin(np.abs(freq - observed_hz)))
        disp_slice = np.asarray(disp_matrix[freq_index], dtype=float).reshape(-1)
        w_slice = None if w_abs_matrix is None else np.asarray(w_abs_matrix[freq_index], dtype=float).reshape(-1)
        rows: list[dict[str, Any]] = []
        for start, stop in zip(bin_edges[:-1], bin_edges[1:]):
            if stop == bin_edges[-1]:
                mask = (x_line >= start) & (x_line <= stop)
            else:
                mask = (x_line >= start) & (x_line < stop)
            if not np.any(mask):
                continue
            x_bin = x_line[mask]
            y_bin = y_line[mask]
            z_bin = z_line[mask]
            disp_bin = disp_slice[mask]
            row = {
                "x_m": float(np.mean(x_bin)),
                "y_m": float(np.mean(y_bin)),
                "z_m": float(np.mean(z_bin)),
                "disp_mean": float(np.mean(disp_bin)),
                "disp_max": float(np.max(disp_bin)),
                "point_count": int(np.count_nonzero(mask)),
            }
            if w_slice is not None:
                row["w_abs_mean"] = float(np.mean(w_slice[mask]))
                row["w_abs_max"] = float(np.max(w_slice[mask]))
            rows.append(row)
        if not rows:
            continue
        profile_path = output_dir / f"mode_shape_{_sanitize_label(label)}.csv"
        fieldnames = list(rows[0].keys())
        profile_paths[label] = _write_rows(profile_path, fieldnames, rows)
        summary["profiles"].append(
            {
                "label": label,
                "frequency_hz": float(freq[freq_index]),
                "profile_path": profile_paths[label],
                "max_disp": float(np.max(disp_slice)),
                "peak_x_m": float(x_line[int(np.argmax(disp_slice))]),
            }
        )
    if not summary["profiles"]:
        return profile_paths, None
    summary_path = output_dir / "mode_shape_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return profile_paths, str(summary_path.resolve())


def _build_curve_artifacts(
    data: dict[str, Any],
    output_json: Path,
    freq: np.ndarray,
    voltage: np.ndarray,
    disp_matrix: np.ndarray,
    x_coords: np.ndarray,
    y_coords: np.ndarray,
    z_coords: np.ndarray,
    w_matrix: np.ndarray | None,
    alignments: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    output_dir = output_json.parent
    amplitude = np.abs(np.asarray(voltage, dtype=complex).reshape(-1))
    resistance_ohm = _load_resistance_ohm(data)
    power_mw = ((amplitude**2) / (2.0 * resistance_ohm)) * 1.0e3

    x_line = np.asarray(x_coords, dtype=float).reshape(-1)
    disp_matrix = np.asarray(disp_matrix, dtype=float)
    output_threshold = float(np.quantile(x_line, 0.95)) if x_line.size else 0.0
    output_mask = x_line >= output_threshold if x_line.size else np.array([], dtype=bool)
    if output_mask.size == 0 or not np.any(output_mask):
        output_mask = np.ones(disp_matrix.shape[1], dtype=bool)
    transmission_disp = np.mean(disp_matrix[:, output_mask], axis=1)
    transmission_db = _normalized_db(transmission_disp)
    smoothed_db = _rolling_median(transmission_db, window=5)
    threshold_db = _threshold_db(data)
    detected_stopbands = _detect_stopband_intervals(freq, smoothed_db, threshold_db)

    transmission_rows = [
        {
            "frequency_hz": float(freq[idx]),
            "transmission_disp": float(transmission_disp[idx]),
            "transmission_db": float(transmission_db[idx]),
            "smoothed_transmission_db": float(smoothed_db[idx]),
        }
        for idx in range(freq.size)
    ]
    power_rows = [
        {
            "frequency_hz": float(freq[idx]),
            "terminal_voltage_real": float(np.real(voltage[idx])),
            "terminal_voltage_imag": float(np.imag(voltage[idx])),
            "terminal_voltage_abs": float(amplitude[idx]),
            "power_mw": float(power_mw[idx]),
        }
        for idx in range(freq.size)
    ]
    transmission_path = _write_rows(
        output_dir / "transmission_curve.csv",
        ["frequency_hz", "transmission_disp", "transmission_db", "smoothed_transmission_db"],
        transmission_rows,
    )
    power_path = _write_rows(
        output_dir / "power_curve.csv",
        ["frequency_hz", "terminal_voltage_real", "terminal_voltage_imag", "terminal_voltage_abs", "power_mw"],
        power_rows,
    )
    stopband_summary_path = output_dir / "stopband_summary.json"
    stopband_summary_path.write_text(
        json.dumps(
            {
                "threshold_transmission_db": threshold_db,
                "output_slice_quantile": 0.95,
                "detected_stopbands_hz": detected_stopbands,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    mode_shape_profiles, mode_shape_summary = _build_mode_shape_profiles(
        output_dir,
        freq=freq,
        disp_matrix=disp_matrix,
        x_coords=x_coords,
        y_coords=y_coords,
        z_coords=z_coords,
        w_matrix=w_matrix,
        alignments=alignments,
    )
    artifacts = {
        "transmission_curve": transmission_path,
        "power_curve": power_path,
        "mode_shape": mode_shape_summary or "",
        "mode_shape_profiles": mode_shape_profiles,
        "stopband_summary": str(stopband_summary_path.resolve()),
        "threshold_transmission_db": threshold_db,
        "detected_stopbands_hz": detected_stopbands,
        "transmission_definition": "mean solid.disp over the downstream x>=95th percentile slice",
        "power_definition": "abs(es.V0_1)^2 / (2*RL_ohm)",
    }
    return artifacts, _build_stopband_pairs(data, alignments, detected_stopbands)


def _extract_frequency_pairs(
    data: dict[str, Any],
    freq: np.ndarray,
    amplitude: np.ndarray,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[float]]:
    anchors = [dict(anchor) for anchor in data.get("anchor_targets", [])]
    candidates = [dict(candidate) for candidate in data.get("candidate_targets", [])]
    peak_indices, _ = find_peaks(amplitude)
    if peak_indices.size == 0 and amplitude.size:
        peak_indices = np.array([int(np.argmax(amplitude))], dtype=int)
    peak_freqs = freq[peak_indices]
    peak_values = amplitude[peak_indices]

    frequency_pairs: list[dict[str, Any]] = []
    alignments: list[dict[str, Any]] = []
    for idx, anchor in enumerate(anchors, start=1):
        anchor_hz = _scalar(anchor.get("frequency_hz"), np.nan)
        if not np.isfinite(anchor_hz) or peak_freqs.size == 0:
            continue
        label = str(anchor.get("label", f"TR{idx}"))
        band_index = int(anchor.get("band_index", 0) or 0)
        peak_idx = int(np.argmin(np.abs(peak_freqs - anchor_hz)))
        observed_hz = float(peak_freqs[peak_idx])
        observed_amp = float(peak_values[peak_idx])
        candidate = _candidate_for_anchor(candidates, band_index, anchor_hz)
        raw_frequency_hz = observed_hz
        if candidate is not None:
            raw_frequency_hz = _scalar(candidate.get("raw_frequency_hz", candidate.get("frequency_hz", observed_hz)), observed_hz)
            if band_index <= 0:
                band_index = int(candidate.get("band_index", 0) or 0)
        frequency_pairs.append(
            {
                "band_index": band_index,
                "label": label,
                "raw_frequency_hz": raw_frequency_hz,
                "l3_frequency_hz": observed_hz,
                "source": "comsol-mph",
            }
        )
        alignments.append(
            {
                "label": label,
                "anchor_frequency_hz": anchor_hz,
                "best_frequency_hz": observed_hz,
                "error_hz": abs(observed_hz - anchor_hz),
                "response_amplitude": observed_amp,
            }
        )
    return frequency_pairs, alignments, [float(value) for value in peak_freqs.tolist()]


def run(input_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    input_path = Path(input_path)
    output_path = Path(output_path)
    data = json.loads(input_path.read_text(encoding="utf-8"))
    result: dict[str, Any] = {
        "protocol_version": L3_PROTOCOL_VERSION,
        "status": "failed",
        "engine": "python-mph",
        "frequency_pairs": [],
        "stopband_pairs": [],
        "anchor_alignment": [],
        "curve_artifacts": {},
        "notes": "",
    }
    try:
        import mph  # type: ignore
    except Exception as exc:  # noqa: BLE001
        result["notes"] = f"mph/COMSOL unavailable: {exc}"
        output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result

    backend = dict(data.get("backend_config", {}))
    controls = dict(data.get("solver_controls", {}))
    model_path = backend.get("comsol_model_path") or data.get("model_path")
    if not model_path:
        result["notes"] = "mph is available, but no COMSOL model_path was provided in the request manifest."
        output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result

    study_tag = str(backend.get("comsol_study_tag") or "std_freq")
    dataset_tag = str(backend.get("comsol_dataset_tag") or "dset2")
    sweep = controls.get("frequency_sweep_hz") or []
    step_hz = _scalar(controls.get("frequency_step_hz"), 50.0)
    parameter_overrides = dict(controls.get("parameter_overrides", {}))

    client = None
    model = None
    try:
        client = mph.start(cores=1)
        model = client.load(str(model_path))
        _apply_parameter_overrides(model, parameter_overrides)
        if isinstance(sweep, list) and len(sweep) >= 2:
            _set_frequency_sweep(model, study_tag, _scalar(sweep[0]), _scalar(sweep[1]), step_hz)
        model.java.study(study_tag).run()
        dataset_name = _resolve_dataset_name(model, dataset_tag)
        if dataset_name is None:
            raise RuntimeError("No COMSOL solution dataset is available after solving the study.")
        freq = np.asarray(model.evaluate("freq", dataset=dataset_name), dtype=float).reshape(-1)
        voltage = np.asarray(model.evaluate("es.V0_1", dataset=dataset_name)).reshape(-1)
        amplitude = np.abs(voltage.astype(complex))
        frequency_pairs, alignments, peak_freqs = _extract_frequency_pairs(data, freq, amplitude)
        disp_matrix = _coerce_field_matrix(model.evaluate("solid.disp", dataset=dataset_name), freq.size).astype(float)
        x_coords = _coerce_field_matrix(model.evaluate("x", dataset=dataset_name), freq.size).astype(float)[0]
        y_coords = _coerce_field_matrix(model.evaluate("y", dataset=dataset_name), freq.size).astype(float)[0]
        z_coords = _coerce_field_matrix(model.evaluate("z", dataset=dataset_name), freq.size).astype(float)[0]
        try:
            w_matrix = _coerce_field_matrix(model.evaluate("w", dataset=dataset_name), freq.size)
        except Exception:  # noqa: BLE001
            w_matrix = None
        curve_artifacts, stopband_pairs = _build_curve_artifacts(
            data,
            output_path,
            freq=freq,
            voltage=voltage,
            disp_matrix=disp_matrix,
            x_coords=x_coords,
            y_coords=y_coords,
            z_coords=z_coords,
            w_matrix=w_matrix,
            alignments=alignments,
        )
        result["frequency_pairs"] = frequency_pairs
        result["stopband_pairs"] = stopband_pairs
        result["anchor_alignment"] = alignments
        result["curve_artifacts"] = {
            "study_tag": study_tag,
            "dataset_tag": dataset_tag,
            "dataset_name": dataset_name,
            "peak_count": len(peak_freqs),
            "peak_frequencies_hz": peak_freqs,
            "observed_frequency_span_hz": [float(freq[0]), float(freq[-1])] if freq.size else [],
            **curve_artifacts,
        }
        result["status"] = "passed" if frequency_pairs else "failed"
        result["notes"] = (
            f"Executed COMSOL model {model_path} over {freq.size} frequency points "
            f"and extracted {len(frequency_pairs)} anchor-aligned peaks plus {len(stopband_pairs)} stopband intervals."
        )
    except Exception as exc:  # noqa: BLE001
        result["status"] = "failed"
        result["notes"] = f"COMSOL execution failed: {exc}"
    finally:
        if client is not None and model is not None:
            try:
                client.remove(model)
            except Exception:  # noqa: BLE001
                pass
            try:
                client.disconnect()
            except Exception:  # noqa: BLE001
                pass
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if len(argv) != 2:
        raise SystemExit("Usage: python -m veh_scientist.discover.l3_comsol_driver <input_json> <output_json>")
    run(argv[0], argv[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
