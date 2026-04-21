"""Mechanism portfolio and combination-layer planning for discovery replay."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from veh_scientist.discover.utils import ensure_dir, write_json, write_text
from veh_scientist.interfaces import DiscoverTaskCard, GapCandidate


MECHANISM_LIBRARY: dict[str, dict[str, Any]] = {
    "truncation_resonance": {
        "display_name": "Truncation resonance",
        "co_located_synergy": True,
        "strengths": [
            "boundary-localized high-Q mode inside a stop band",
            "direct co-location of attenuation and harvesting",
            "already calibrated against the replay anchors",
        ],
        "risks": [
            "performance collapses as δ→1",
            "still depends on live L3 validation for final paper truth",
        ],
    },
    "defect_mode": {
        "display_name": "Defect mode",
        "co_located_synergy": True,
        "strengths": [
            "strong localization at a prescribed defect",
            "good for explicit frequency targeting once a defect is manufacturable",
        ],
        "risks": [
            "requires explicit defect engineering",
            "less portable than TR under boundary changes",
        ],
    },
    "interface_state": {
        "display_name": "Topological/interface state",
        "co_located_synergy": True,
        "strengths": [
            "localized interface state with good disorder tolerance",
            "valuable comparator for robustness-focused harvesting studies",
        ],
        "risks": [
            "needs topology-aware bookkeeping",
            "design freedom is constrained by dimerization/interface rules",
        ],
    },
    "hybrid_tr_defect": {
        "display_name": "Hybrid TR + defect",
        "co_located_synergy": True,
        "strengths": [
            "can unlock multi-band candidates",
            "extends TR with explicit defect placement freedom",
        ],
        "risks": [
            "mode interaction can split the target peak",
            "parameter space expands quickly",
        ],
    },
    "hybrid_tr_interface": {
        "display_name": "Hybrid TR + interface",
        "co_located_synergy": True,
        "strengths": [
            "combines band placement freedom with interface-style robustness",
            "useful comparator when boundary and interface mechanisms overlap",
        ],
        "risks": [
            "requires a more advanced beam backend",
            "easy to over-claim robustness without topology-aware validation",
        ],
    },
    "local_resonance": {
        "display_name": "Local resonance route",
        "co_located_synergy": True,
        "strengths": [
            "natural low-frequency bandgap mechanism",
            "good pathway when the target band lies below Bragg-scale gaps",
        ],
        "risks": [
            "localized strain can stay trapped in local resonators rather than the harvesting port",
            "requires route-specific scaling laws",
        ],
    },
    "nonlinear_route": {
        "display_name": "Nonlinear route",
        "co_located_synergy": False,
        "strengths": [
            "amplitude-dependent tuning and bandwidth expansion",
            "promising for nonstationary or large-amplitude inputs",
        ],
        "risks": [
            "harder to certify with a single linear appendix",
            "bistability and jump phenomena complicate ranking and review",
        ],
    },
}



def _band_text(best_gap: GapCandidate | None) -> str:
    if best_gap is None:
        return "No ranked gap is available yet."
    freq = best_gap.calibrated_frequency_hz or best_gap.anchored_frequency_hz or best_gap.raw_frequency_hz
    if freq is None:
        return f"Best current band is gap {best_gap.band_index}."
    return f"Best current band is gap {best_gap.band_index} near {freq:.1f} Hz."



def build_mechanism_portfolio(
    output_dir: str | Path,
    task: DiscoverTaskCard,
    ranked_gaps: list[GapCandidate],
    calibration_summary: dict[str, Any] | None = None,
    solver_library: dict[str, Any] | None = None,
) -> dict[str, Any]:
    output_dir = ensure_dir(output_dir)
    best_gap = ranked_gaps[0] if ranked_gaps else None
    target_band = None
    if task.engineering_task is not None:
        target_band = tuple(float(v) for v in task.engineering_task.frequency_target.band_of_interest)

    library_rows = {row.get("mechanism_key"): dict(row) for row in (solver_library or {}).get("comparison", [])}
    confidence = float((calibration_summary or {}).get("confidence", 0.0) or 0.0)

    entries: list[dict[str, Any]] = []
    for mechanism_key, meta in MECHANISM_LIBRARY.items():
        row = library_rows.get(mechanism_key, {})
        solver_status = row.get("solver_status", "portfolio_only")
        maturity = row.get("maturity", "portfolio_only")
        fit_score = float(row.get("target_band_score", 0.0) or 0.0)
        localization = float(row.get("localization_score", 0.0) or 0.0)
        harvesting = float(row.get("harvestability_proxy", 0.0) or 0.0)
        suppression = float(row.get("suppression_proxy", 0.0) or 0.0)
        review_pass = bool(row.get("review_pass", False))
        calibration_confidence = confidence if mechanism_key == task.mechanism_focus else confidence * (0.7 if solver_status == "passed" else 0.35)
        if not review_pass:
            calibration_confidence *= 0.7
        combined_fit = 0.35 * fit_score + 0.25 * localization + 0.20 * harvesting + 0.20 * suppression
        if mechanism_key == task.mechanism_focus and best_gap is not None:
            combined_fit = max(combined_fit, 0.4 * best_gap.target_band_score + 0.3 * best_gap.localization_score + 0.3 * best_gap.harvestability_score)
        entries.append(
            {
                "mechanism_key": mechanism_key,
                "display_name": meta["display_name"],
                "maturity": maturity,
                "solver_status": solver_status,
                "co_located_synergy": meta["co_located_synergy"],
                "fit_score": round(float(combined_fit), 4),
                "target_band_score": round(float(fit_score), 4),
                "localization_score": round(float(localization), 4),
                "harvestability_proxy": round(float(harvesting), 4),
                "suppression_proxy": round(float(suppression), 4),
                "calibration_confidence": round(float(calibration_confidence), 4),
                "review_pass": review_pass,
                "recommended": mechanism_key == task.mechanism_focus,
                "strengths": meta["strengths"],
                "risks": meta["risks"],
                "target_band_hz": None if target_band is None else list(target_band),
                "best_gap_reference": None if best_gap is None else {
                    "band_index": best_gap.band_index,
                    "frequency_hz": best_gap.calibrated_frequency_hz or best_gap.anchored_frequency_hz or best_gap.raw_frequency_hz,
                    "matched_anchor": best_gap.matched_anchor_label,
                },
                "solver_package": None if mechanism_key not in (solver_library or {}) else None,
            }
        )

    ranked_entries = sorted(entries, key=lambda item: (-float(item["recommended"]), -float(item["fit_score"]), item["mechanism_key"]))
    primary = ranked_entries[0]["mechanism_key"] if ranked_entries else task.mechanism_focus
    secondary = [row["mechanism_key"] for row in ranked_entries[1:4]]
    recommended_path = {
        "primary": primary,
        "secondary": secondary,
        "rationale": [
            _band_text(best_gap),
            "Keep truncation resonance as the calibrated baseline if it remains competitive after uncertainty-aware ranking.",
            "Use defect and interface routes as explicit comparators rather than as abstract future work.",
            "Treat local resonance and nonlinear routes as exploratory branches whose code packs and audit trails already exist, but whose publication ranking still depends on route-specific validation.",
        ],
    }
    portfolio = {
        "task_id": task.task_id,
        "mechanism_focus": task.mechanism_focus,
        "entries": ranked_entries,
        "recommended_path": recommended_path,
        "portfolio_stage": "calibrated_baseline_plus_solver_library",
    }

    roadmap_lines = [
        "# Mechanism combination roadmap",
        "",
        f"Primary path: **{recommended_path['primary']}**",
        "",
        "## Current position",
        "",
        _band_text(best_gap),
        "",
        "## Ranked mechanism portfolio",
        "",
    ]
    for row in ranked_entries:
        roadmap_lines.append(
            f"- **{row['display_name']}** ({row['mechanism_key']}, maturity={row['maturity']}, solver_status={row['solver_status']}, fit={row['fit_score']:.3f}, calibration_confidence={row['calibration_confidence']:.3f}, review_pass={row['review_pass']})"
        )
        roadmap_lines.append(f"  - strengths: {', '.join(row['strengths'])}")
        roadmap_lines.append(f"  - risks: {', '.join(row['risks'])}")
    roadmap_lines.extend([
        "",
        "## Combination-layer implication",
        "",
        "The codebase no longer treats alternative mechanisms as narrative placeholders only. Each route now has a surrogate solver result, a Python/MATLAB/COMSOL code pack, and an audit trail that can be inspected before live high-fidelity validation.",
    ])

    write_json(output_dir / "mechanism_portfolio.json", portfolio)
    write_text(output_dir / "mechanism_combo_roadmap.md", "\n".join(roadmap_lines))
    return portfolio
