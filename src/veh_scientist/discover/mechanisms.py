"""Mechanism portfolio and combination-layer planning for discovery replay."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from veh_scientist.discover.utils import ensure_dir, write_json, write_text
from veh_scientist.interfaces import DiscoverTaskCard, GapCandidate


MECHANISM_LIBRARY: dict[str, dict[str, Any]] = {
    "truncation_resonance": {
        "display_name": "Truncation resonance",
        "maturity": "solver_ready",
        "co_located_synergy": True,
        "strengths": [
            "boundary-localized high-Q mode inside a stop band",
            "simultaneous attenuation and harvesting at the same frequency",
            "direct bandgap placement via internal cell tuning",
        ],
        "risks": [
            "sensitive to boundary realization as δ→1",
            "requires careful L2–L3 calibration for beam truth",
        ],
        "required_modules": ["l1_chain", "l2_beam", "l3_validation", "piezo_port"],
        "next_experiments": [
            "close L2–L3 calibration loop with COMSOL beam studies",
            "map fabrication tolerances into calibrated gap uncertainty",
        ],
    },
    "defect_mode": {
        "display_name": "Defect mode",
        "maturity": "portfolio_only",
        "co_located_synergy": True,
        "strengths": [
            "strong localization at engineered defects",
            "direct frequency targeting through defect placement and size",
        ],
        "risks": [
            "requires explicit defect engineering",
            "frequency placement is less portable than TR under boundary changes",
        ],
        "required_modules": ["supercell_solver", "defect_port_mapper", "l3_validation"],
        "next_experiments": [
            "add defect-supercell L1/L2 solver pair",
            "compare defect localization efficiency versus TR on matched envelopes",
        ],
    },
    "interface_state": {
        "display_name": "Topological/interface state",
        "maturity": "portfolio_only",
        "co_located_synergy": True,
        "strengths": [
            "robust interface localization when symmetry conditions are met",
            "promising robustness to disorder and tolerances",
        ],
        "risks": [
            "requires phase/topology bookkeeping beyond current replay stack",
            "not every engineering design admits a clean invariant-driven route",
        ],
        "required_modules": ["topological_invariants", "interface_solver", "l3_validation"],
        "next_experiments": [
            "add SSH-style beam and chain interfaces",
            "benchmark robustness versus TR after calibration",
        ],
    },
    "hybrid_tr_defect": {
        "display_name": "Hybrid TR + defect mode",
        "maturity": "conceptual",
        "co_located_synergy": True,
        "strengths": [
            "can widen design space for multi-band harvesting",
            "may sharpen localization while keeping bandgap attenuation",
        ],
        "risks": [
            "parameter space expands quickly",
            "mode interaction can split or suppress target peaks",
        ],
        "required_modules": ["tr_solver", "defect_solver", "multiport_calibration"],
        "next_experiments": [
            "introduce controlled defect into calibrated TR beam candidate",
            "measure peak splitting and bandwidth trade-off",
        ],
    },
    "hybrid_tr_interface": {
        "display_name": "Hybrid TR + interface state",
        "maturity": "conceptual",
        "co_located_synergy": True,
        "strengths": [
            "offers a path toward robust edge localization with tunable band placement",
            "could combine boundary asymmetry with topology-guided interface protection",
        ],
        "risks": [
            "needs topology-aware continuous beam backend",
            "boundary termination and interface state can interfere constructively or destructively",
        ],
        "required_modules": ["tr_solver", "interface_solver", "topological_invariants", "l3_validation"],
        "next_experiments": [
            "prototype dual-edge/interface unit-cell family",
            "study whether TR anchors survive interface perturbations",
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
) -> dict[str, Any]:
    output_dir = ensure_dir(output_dir)
    best_gap = ranked_gaps[0] if ranked_gaps else None
    target_band = None
    if task.engineering_task is not None:
        target_band = tuple(float(v) for v in task.engineering_task.frequency_target.band_of_interest)

    entries: list[dict[str, Any]] = []
    for mechanism_key, meta in MECHANISM_LIBRARY.items():
        solver_ready = meta["maturity"] == "solver_ready"
        recommended = mechanism_key == task.mechanism_focus
        fit_score = 0.0
        if best_gap is not None:
            fit_score = 0.35 * best_gap.target_band_score + 0.35 * best_gap.localization_score + 0.30 * best_gap.harvestability_score
            if mechanism_key != task.mechanism_focus:
                fit_score *= 0.82 if "hybrid" not in mechanism_key else 0.68
        confidence = float((calibration_summary or {}).get("confidence", 0.0) or 0.0)
        if mechanism_key != task.mechanism_focus:
            confidence *= 0.65 if solver_ready else 0.35
        entries.append(
            {
                "mechanism_key": mechanism_key,
                "display_name": meta["display_name"],
                "maturity": meta["maturity"],
                "co_located_synergy": meta["co_located_synergy"],
                "fit_score": round(float(fit_score), 4),
                "calibration_confidence": round(float(confidence), 4),
                "recommended": recommended,
                "strengths": meta["strengths"],
                "risks": meta["risks"],
                "required_modules": meta["required_modules"],
                "next_experiments": meta["next_experiments"],
                "target_band_hz": None if target_band is None else list(target_band),
                "best_gap_reference": None if best_gap is None else {
                    "band_index": best_gap.band_index,
                    "frequency_hz": best_gap.calibrated_frequency_hz or best_gap.anchored_frequency_hz or best_gap.raw_frequency_hz,
                    "matched_anchor": best_gap.matched_anchor_label,
                },
            }
        )

    ranked_entries = sorted(entries, key=lambda item: (-float(item["recommended"]), -float(item["fit_score"]), item["mechanism_key"]))
    recommended_path = {
        "primary": ranked_entries[0]["mechanism_key"] if ranked_entries else task.mechanism_focus,
        "secondary": [row["mechanism_key"] for row in ranked_entries[1:3]],
        "rationale": [
            _band_text(best_gap),
            "Use truncation resonance as the calibrated baseline because it is the only solver-ready mechanism in the current stack.",
            "Use defect/interface mechanisms as portfolio comparators and next-step expansion routes rather than replacing the calibrated TR core today.",
        ],
    }
    portfolio = {
        "task_id": task.task_id,
        "mechanism_focus": task.mechanism_focus,
        "entries": ranked_entries,
        "recommended_path": recommended_path,
        "portfolio_stage": "solver_ready_baseline_plus_portfolio_expansion",
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
            f"- **{row['display_name']}** ({row['mechanism_key']}, maturity={row['maturity']}, fit={row['fit_score']:.3f}, calibration_confidence={row['calibration_confidence']:.3f})"
        )
        roadmap_lines.append(f"  - strengths: {', '.join(row['strengths'])}")
        roadmap_lines.append(f"  - risks: {', '.join(row['risks'])}")
        roadmap_lines.append(f"  - next: {', '.join(row['next_experiments'])}")
    roadmap_lines.extend([
        "",
        "## Combination-layer implication",
        "",
        "The present codebase is calibrated enough to treat TR as the baseline mechanism. The next layer is not to discard TR, but to add comparable solvers for defect and interface routes so the system can choose mechanisms rather than replay a fixed one.",
    ])

    write_json(output_dir / "mechanism_portfolio.json", portfolio)
    write_text(output_dir / "mechanism_combo_roadmap.md", "\n".join(roadmap_lines))
    return portfolio
