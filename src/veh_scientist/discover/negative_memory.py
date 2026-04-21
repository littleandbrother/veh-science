"""Negative-result memory and explicit experience ledger for discovery replay."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from veh_scientist.discover.utils import ensure_dir, write_csv, write_json, write_text
from veh_scientist.interfaces import GapCandidate



def _record(category: str, label: str, severity: str, details: dict[str, Any], lesson: str, action: str) -> dict[str, Any]:
    return {
        "category": category,
        "label": label,
        "severity": severity,
        "details": details,
        "lesson": lesson,
        "recommended_action": action,
    }



def _parameter_region_failures(chain_atlas: dict[str, Any] | None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not chain_atlas:
        return records
    delta_scan = [dict(row) for row in chain_atlas.get("delta_scan", [])]
    if delta_scan:
        near_periodic = [row for row in delta_scan if abs(float(row.get("delta", 0.0)) - 1.0) <= 0.18]
        if near_periodic:
            weak = [row for row in near_periodic if int(row.get("tr_count", 0)) == 0 or float(row.get("peak_voltage", 0.0)) <= 0.25 * max(float(item.get("peak_voltage", 0.0)) for item in delta_scan)]
            if weak:
                records.append(
                    _record(
                        "parameter_region_failure",
                        "Boundary asymmetry too close to periodic termination",
                        "high",
                        {
                            "delta_values": [float(row.get("delta", 0.0)) for row in weak],
                            "peak_voltage_values": [float(row.get("peak_voltage", 0.0)) for row in weak],
                            "tr_count_values": [int(row.get("tr_count", 0)) for row in weak],
                        },
                        "TR is effectively switched off when δ approaches 1, so this region should be treated as a no-go zone for boundary-localized harvesting.",
                        "Keep δ sufficiently separated from 1 before spending L2/L3 budget.",
                    )
                )

    matching_map = chain_atlas.get("matching_map", {})
    peak_power_map = matching_map.get("peak_power_map")
    if peak_power_map:
        flat = [float(value) for row in peak_power_map for value in row]
        if flat:
            max_power = max(flat)
            weak_fraction = sum(value < 0.25 * max_power for value in flat) / max(len(flat), 1)
            if weak_fraction >= 0.5:
                records.append(
                    _record(
                        "parameter_region_failure",
                        "Large electromechanical mismatch region",
                        "medium",
                        {
                            "weak_fraction": weak_fraction,
                            "map_shape": [len(peak_power_map), len(peak_power_map[0]) if peak_power_map and peak_power_map[0] else 0],
                        },
                        "A large portion of the (κ², ε) plane gives poor power extraction, so the matcher stage must be narrowed before beam validation.",
                        "Concentrate sweeps near the ridge of the matching map rather than exploring the full grid uniformly.",
                    )
                )
    return records



def _unsuitable_gaps(gap_candidates: list[GapCandidate]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for gap in gap_candidates:
        reasons: list[str] = []
        if gap.harvestability_score < 0.35:
            reasons.append("low harvestability")
        if gap.suppression_margin < 0.25:
            reasons.append("weak suppression")
        if gap.uncertainty_score < 0.45:
            reasons.append("high calibration uncertainty")
        if gap.extrapolation_penalty > 0.25:
            reasons.append("strong extrapolation penalty")
        if not reasons:
            continue
        records.append(
            _record(
                "unsuitable_gap",
                f"Gap {gap.band_index} is not publication-grade yet",
                "medium" if gap.band_index == 1 else "low",
                {
                    "band_index": gap.band_index,
                    "raw_frequency_hz": gap.raw_frequency_hz,
                    "calibrated_frequency_hz": gap.calibrated_frequency_hz,
                    "reasons": reasons,
                    "overall_score": gap.overall_score,
                },
                "Not every candidate gap that hosts a boundary mode is worth taking to high fidelity. Unsuitable gaps should be remembered explicitly so the system does not keep re-proposing them.",
                "Prune this gap from the shortlist unless a new mechanism or calibration update materially changes the ranking inputs.",
            )
        )
    return records



def _l3_refutations(calibration_summary: dict[str, Any] | None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not calibration_summary:
        return records
    passed_tools = [proto for proto in calibration_summary.get("normalized_tool_results", []) if str(proto.get("status", "")).lower() == "passed"]
    live_validation = bool(passed_tools)
    for pair in calibration_summary.get("frequency_pairs", []):
        raw_hz = float(pair.get("raw_frequency_hz", 0.0) or 0.0)
        l3_hz = float(pair.get("l3_frequency_hz", 0.0) or 0.0)
        if raw_hz <= 0.0 or l3_hz <= 0.0:
            continue
        error_hz = abs(raw_hz - l3_hz)
        relative = error_hz / max(l3_hz, 1.0)
        if relative < 0.15:
            continue
        records.append(
            _record(
                "l3_refutation" if live_validation else "l3_provisional_refutation",
                f"Beam candidate for {pair.get('label', 'unlabeled')} misses the L3 anchor",
                "high" if live_validation else "medium",
                {
                    "band_index": int(pair.get("band_index", 0)),
                    "raw_frequency_hz": raw_hz,
                    "l3_frequency_hz": l3_hz,
                    "error_hz": error_hz,
                    "relative_error": relative,
                    "source": calibration_summary.get("source"),
                },
                "Some beam candidates look promising in L2 but are overturned when they are aligned against L3 anchors. This failure mode has to stay visible in memory.",
                "Retune the surrogate or drop the candidate from the shortlist until the raw-vs-L3 disagreement is reduced.",
            )
        )
    return records



def _unstable_derivations(derivation_checks: dict[str, Any] | None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not derivation_checks:
        return records
    for card in derivation_checks.get("cards", []):
        failed = [check for check in card.get("checks", []) if not bool(check.get("passed", False))]
        if not failed:
            continue
        records.append(
            _record(
                "unstable_derivation",
                f"Derivation instability in {card.get('title', 'unnamed derivation')}",
                "high",
                {
                    "derivation_id": card.get("derivation_id"),
                    "failed_checks": failed,
                },
                "A derivation that loses a limit-case or solver cross-check must be remembered as unstable rather than silently overwritten.",
                "Do not move this formula into the appendix bundle until every failing check is explained or repaired.",
            )
        )
    return records



def _mechanism_deadends(solver_library: dict[str, Any] | None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not solver_library:
        return records
    for row in solver_library.get("comparison", []):
        if bool(row.get("review_pass")) and float(row.get("target_band_score", 0.0) or 0.0) >= 0.35:
            continue
        records.append(
            _record(
                "mechanism_deadend",
                f"{row.get('mechanism_key')} is not competitive in the current target band",
                "low",
                dict(row),
                "A mechanism can be scientifically interesting yet still be the wrong route for the current band and constraints.",
                "Keep the solver pack, but do not rank this route above the calibrated baseline until target-band fit or review status improves.",
            )
        )
    return records



def build_negative_result_memory(
    output_dir: str | Path,
    chain_atlas: dict[str, Any] | None,
    gap_candidates: list[GapCandidate],
    calibration_summary: dict[str, Any] | None,
    derivation_checks: dict[str, Any] | None,
    solver_library: dict[str, Any] | None,
) -> dict[str, Any]:
    output_dir = ensure_dir(output_dir)
    parameter_failures = _parameter_region_failures(chain_atlas)
    unsuitable_gaps = _unsuitable_gaps(gap_candidates)
    l3_refutations = _l3_refutations(calibration_summary)
    unstable_derivations = _unstable_derivations(derivation_checks)
    mechanism_deadends = _mechanism_deadends(solver_library)

    records = parameter_failures + unsuitable_gaps + l3_refutations + unstable_derivations + mechanism_deadends
    lessons = [record["lesson"] for record in records]
    actions = [record["recommended_action"] for record in records]
    summary = {
        "n_records": len(records),
        "n_parameter_failures": len(parameter_failures),
        "n_unsuitable_gaps": len(unsuitable_gaps),
        "n_l3_refutations": len(l3_refutations),
        "n_unstable_derivations": len(unstable_derivations),
        "n_mechanism_deadends": len(mechanism_deadends),
    }
    memory = {
        "summary": summary,
        "records": records,
        "lessons": lessons,
        "next_actions": actions,
    }

    write_json(output_dir / "negative_result_memory.json", memory)
    write_csv(
        output_dir / "negative_result_memory.csv",
        [
            {
                "category": record["category"],
                "label": record["label"],
                "severity": record["severity"],
                "lesson": record["lesson"],
                "recommended_action": record["recommended_action"],
            }
            for record in records
        ],
        fieldnames=["category", "label", "severity", "lesson", "recommended_action"],
    )
    lines = ["# Negative-result memory", "", f"n_records: **{len(records)}**", ""]
    for record in records:
        lines.append(f"- **[{record['category']}] {record['label']}** ({record['severity']})")
        lines.append(f"  - lesson: {record['lesson']}")
        lines.append(f"  - next: {record['recommended_action']}")
    write_text(output_dir / "negative_result_memory.md", "\n".join(lines))
    return memory
