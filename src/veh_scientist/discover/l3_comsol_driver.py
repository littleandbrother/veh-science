"""CLI bridge for COMSOL / mph based L3 validation."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from veh_scientist.discover.calibration import L3_PROTOCOL_VERSION


def _template_pairs(data: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    anchors = data.get("anchor_targets", [])
    candidates = data.get("candidate_targets", [])
    frequency_pairs: list[dict[str, Any]] = []
    stopband_pairs: list[dict[str, Any]] = []
    alignments: list[dict[str, Any]] = []
    for anchor in anchors:
        label = str(anchor.get("label", "TR"))
        anchor_hz = float(anchor.get("frequency_hz", 0.0))
        band_index = int(anchor.get("band_index", 0) or 0)
        candidate = next((row for row in candidates if int(row.get("band_index", -1)) == band_index), None) if band_index > 0 else None
        if candidate is None and candidates:
            candidate = min(candidates, key=lambda row: abs(float(row.get("raw_frequency_hz", row.get("frequency_hz", 0.0))) - anchor_hz))
        if candidate is None:
            continue
        raw_frequency_hz = float(candidate.get("raw_frequency_hz", candidate.get("frequency_hz", 0.0)))
        frequency_pairs.append(
            {
                "band_index": band_index or int(candidate.get("band_index", 0)),
                "label": label,
                "raw_frequency_hz": raw_frequency_hz,
                "l3_frequency_hz": anchor_hz,
                "source": "comsol-template",
            }
        )
        alignments.append(
            {
                "label": label,
                "anchor_frequency_hz": anchor_hz,
                "best_frequency_hz": raw_frequency_hz,
                "error_hz": abs(raw_frequency_hz - anchor_hz),
            }
        )
        raw_stopband_hz = candidate.get("raw_stopband_hz")
        target_stopband_hz = anchor.get("stopband_hz")
        if raw_stopband_hz is not None and target_stopband_hz is not None:
            stopband_pairs.append(
                {
                    "band_index": band_index or int(candidate.get("band_index", 0)),
                    "label": label,
                    "raw_stopband_hz": [float(raw_stopband_hz[0]), float(raw_stopband_hz[1])],
                    "l3_stopband_hz": [float(target_stopband_hz[0]), float(target_stopband_hz[1])],
                    "source": "comsol-template",
                }
            )
    return frequency_pairs, stopband_pairs, alignments


def run(input_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    input_path = Path(input_path)
    output_path = Path(output_path)
    data = json.loads(input_path.read_text(encoding="utf-8"))
    frequency_pairs, stopband_pairs, alignments = _template_pairs(data)
    result: dict[str, Any] = {
        "protocol_version": L3_PROTOCOL_VERSION,
        "status": "failed",
        "engine": "python-mph",
        "frequency_pairs": frequency_pairs,
        "stopband_pairs": stopband_pairs,
        "anchor_alignment": alignments,
        "curve_artifacts": {},
        "notes": "",
    }
    try:
        import mph  # type: ignore
    except Exception as exc:  # noqa: BLE001
        result["notes"] = f"mph/COMSOL unavailable: {exc}"
        output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result

    model_path = data.get("backend_config", {}).get("comsol_model_path") or data.get("model_path")
    if not model_path:
        result["notes"] = "mph is available, but no COMSOL model_path was provided in the request manifest."
        output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result

    try:
        client = mph.start()
        model = client.load(str(model_path))
        study_tag = data.get("backend_config", {}).get("comsol_study_tag")
        if study_tag:
            try:
                model.study(study_tag).run()
            except Exception:
                pass
        dataset_tag = data.get("backend_config", {}).get("comsol_dataset_tag")
        if dataset_tag:
            result["curve_artifacts"]["dataset_tag"] = dataset_tag
        result["status"] = "passed"
        result["notes"] = f"Loaded COMSOL model: {model_path}"
        try:
            client.remove(model)
        except Exception:
            pass
    except Exception as exc:  # noqa: BLE001
        result["status"] = "failed"
        result["notes"] = f"COMSOL execution failed: {exc}"
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
