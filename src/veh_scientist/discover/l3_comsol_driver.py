"""CLI bridge for COMSOL / mph based L3 validation."""

from __future__ import annotations

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
        result["frequency_pairs"] = frequency_pairs
        result["anchor_alignment"] = alignments
        result["curve_artifacts"] = {
            "study_tag": study_tag,
            "dataset_tag": dataset_tag,
            "dataset_name": dataset_name,
            "peak_count": len(peak_freqs),
            "peak_frequencies_hz": peak_freqs,
            "observed_frequency_span_hz": [float(freq[0]), float(freq[-1])] if freq.size else [],
        }
        result["status"] = "passed" if frequency_pairs else "failed"
        result["notes"] = (
            f"Executed COMSOL model {model_path} over {freq.size} frequency points "
            f"and extracted {len(frequency_pairs)} anchor-aligned peaks."
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
