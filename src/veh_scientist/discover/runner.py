"""Executable discovery runner for replay/discover mode."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from veh_scientist.discover.claims import build_claim_graph
from veh_scientist.discover.corpus import build_corpus_manifest, corpus_digests, gap_statement
from veh_scientist.discover.derivations import execute_tr_derivations
from veh_scientist.discover.discussion import build_discussion_bundle
from veh_scientist.discover.evidence import draft_evidence_records
from veh_scientist.discover.gap_designer import build_gap_candidates, rank_gap_candidates
from veh_scientist.discover.hypotheses import build_tr_hypothesis_ladder
from veh_scientist.discover.l1_chain import ChainReplayParams, run_l1_chain_replay
from veh_scientist.discover.l2_beam import BeamReplayParams, run_l2_beam_replay
from veh_scientist.discover.l3_toolchain import run_l3_validation_suite
from veh_scientist.discover.mechanisms import build_mechanism_portfolio
from veh_scientist.discover.negative_memory import build_negative_result_memory
from veh_scientist.discover.program import build_initial_program
from veh_scientist.discover.publication import build_publication_bundle
from veh_scientist.discover.report import write_report_bundle
from veh_scientist.discover.smoke import run_regression_smoke
from veh_scientist.discover.solver_library import build_solver_library
from veh_scientist.discover.utils import ensure_dir, now_iso, update_step_status, write_json, write_text
from veh_scientist.interfaces import (
    DiscoverTaskCard,
    DiscoveryProgramState,
    ExperimentArtifact,
    ToolRunRecord,
)


class DiscoveryRunner:
    """Build and execute a replay/discover program."""

    def __init__(self, task: DiscoverTaskCard, task_card_path: str | Path | None = None):
        self.task = task
        self.task_card_path = Path(task_card_path).resolve() if task_card_path is not None else None
        self.base_dir = self.task_card_path.parent if self.task_card_path is not None else Path.cwd()
        self._last_program: DiscoveryProgramState | None = None

    def plan(self) -> DiscoveryProgramState:
        return build_initial_program(self.task, base_dir=self.base_dir)

    def summary(self) -> dict[str, object]:
        program = self._last_program or self.plan()
        return {
            "task_id": program.task_id,
            "mode": program.mode,
            "stage": program.stage,
            "output_dir": program.output_dir,
            "n_documents": len(program.corpus_manifest),
            "n_steps": len(program.planned_steps),
            "n_claims": len(program.claim_graph),
            "n_hypotheses": len(program.hypotheses),
            "n_derivations": len(program.derivations),
            "n_gap_candidates": len(program.gap_candidates),
            "n_evidence_records": len(program.evidence),
            "current_focus": program.current_focus,
            "summary_metrics": program.summary_metrics,
            "steps": [asdict(step) for step in program.planned_steps],
            "artifacts": [asdict(artifact) for artifact in program.artifacts],
            "tool_runs": [asdict(run) for run in program.tool_runs],
            "warnings": list(program.warnings),
            "l3_validation": program.l3_validation,
            "calibration_summary": program.calibration_summary,
            "appendix_summary": program.appendix_summary,
            "mechanism_portfolio": program.mechanism_portfolio,
            "solver_library": program.solver_library,
            "negative_memory": program.negative_memory,
            "publication_bundle": program.publication_bundle,
            "discussion_bundle": program.discussion_bundle,
            "collaboration_log": [asdict(msg) for msg in program.collaboration_log],
            "smoke_summary": program.smoke_summary,
        }

    def execute(self, output_dir: str | Path = "results/discovery") -> DiscoveryProgramState:
        program = self.plan()
        root = ensure_dir(Path(output_dir) / self.task.task_id)
        program.output_dir = str(root.resolve())
        self._write_program(program, root / "program_state.json")

        # ------------------------------------------------------------------
        # corpus
        # ------------------------------------------------------------------
        self._start_stage(program, "corpus", root)
        manifest = build_corpus_manifest(self.task, base_dir=self.base_dir)
        program.corpus_manifest = manifest
        corpus_dir = ensure_dir(root / "01_corpus")
        digests = corpus_digests(manifest)
        write_json(corpus_dir / "corpus_manifest.json", manifest)
        write_json(corpus_dir / "corpus_digests.json", digests)
        write_text(corpus_dir / "gap_statement.md", gap_statement(self.task, manifest, digests))
        missing_docs = [doc.title for doc in manifest if not doc.exists]
        if missing_docs:
            program.warnings.append(f"Missing corpus documents: {', '.join(missing_docs)}")
        self._register_artifact(program, "Corpus manifest", "dataset", corpus_dir / "corpus_manifest.json", "Resolved discovery corpus.", "corpus")
        self._register_artifact(program, "Gap statement", "report", corpus_dir / "gap_statement.md", "Replay-oriented statement of the research gap.", "corpus")
        program.tool_runs.append(
            ToolRunRecord(
                tool="python",
                purpose="corpus ingestion",
                status="passed",
                outputs={"n_documents": len(manifest)},
                artifact_paths=(str(corpus_dir / "corpus_manifest.json"), str(corpus_dir / "gap_statement.md")),
            )
        )
        self._finish_stage(program, "corpus", root)

        # ------------------------------------------------------------------
        # claims
        # ------------------------------------------------------------------
        self._start_stage(program, "claims", root)
        claim_dir = ensure_dir(root / "02_claims")
        claims = build_claim_graph(self.task, base_dir=self.base_dir)
        program.claim_graph = claims
        write_json(claim_dir / "claim_graph.json", claims)
        write_text(claim_dir / "claim_graph.md", "# Claim graph\n\n" + "\n".join(f"- [{claim.claim_type}] {claim.claim_text}" for claim in claims))
        self._register_artifact(program, "Claim graph", "dataset", claim_dir / "claim_graph.json", "Mechanism, limitation, and design-rule claims extracted from the corpus.", "claims")
        self._register_artifact(program, "Claim graph (markdown)", "report", claim_dir / "claim_graph.md", "Human-readable claim graph.", "claims")
        program.tool_runs.append(
            ToolRunRecord(
                tool="python",
                purpose="claim graph construction",
                status="passed",
                outputs={"n_claims": len(claims)},
                artifact_paths=(str(claim_dir / "claim_graph.json"), str(claim_dir / "claim_graph.md")),
            )
        )
        self._finish_stage(program, "claims", root)

        # ------------------------------------------------------------------
        # hypotheses
        # ------------------------------------------------------------------
        self._start_stage(program, "hypotheses", root)
        hypothesis_dir = ensure_dir(root / "03_hypotheses")
        hypotheses = build_tr_hypothesis_ladder(self.task)
        program.hypotheses = hypotheses
        write_json(hypothesis_dir / "hypotheses.json", hypotheses)
        write_text(
            hypothesis_dir / "hypothesis_ladder.md",
            "# Hypothesis ladder\n\n" + "\n".join(f"- **{card.label}** — {card.statement}" for card in hypotheses),
        )
        self._register_artifact(program, "Hypothesis ladder", "report", hypothesis_dir / "hypothesis_ladder.md", "Five-step TR replay hypothesis ladder.", "hypotheses")
        self._register_artifact(program, "Hypothesis ladder (json)", "dataset", hypothesis_dir / "hypotheses.json", "Structured hypothesis cards.", "hypotheses")
        program.tool_runs.append(
            ToolRunRecord(
                tool="python",
                purpose="hypothesis ladder generation",
                status="passed",
                outputs={"n_hypotheses": len(hypotheses)},
                artifact_paths=(str(hypothesis_dir / "hypotheses.json"), str(hypothesis_dir / "hypothesis_ladder.md")),
            )
        )
        self._finish_stage(program, "hypotheses", root)

        # ------------------------------------------------------------------
        # derivations
        # ------------------------------------------------------------------
        self._start_stage(program, "derivations", root)
        derivation_dir = ensure_dir(root / "04_derivations")
        derivation_outputs = execute_tr_derivations(derivation_dir, self.task)
        derivation_checks = json.loads((derivation_dir / "derivation_checks.json").read_text(encoding="utf-8"))
        program.derivations = derivation_outputs["cards"]
        program.appendix_summary = derivation_outputs.get("appendix_summary", {})
        self._register_artifact(program, "Derivation report", "report", derivation_dir / "derivation_report.md", "Symbolic and numerical derivation ladder for TR replay.", "derivations")
        self._register_artifact(program, "Replay equations", "equation", derivation_dir / "equations.tex", "LaTeX equations emitted from the derivation stage.", "derivations")
        self._register_artifact(program, "Derivation checks", "dataset", derivation_dir / "derivation_checks.json", "Per-derivation limit-case and solver-check results.", "derivations")
        self._register_artifact(program, "Appendix package", "report", derivation_dir / "appendix_package.md", "Appendix-grade derivation package with traces, limits, and solver cross-checks.", "derivations")
        self._register_artifact(program, "Appendix bundle", "equation", derivation_dir / "appendix_bundle.tex", "LaTeX appendix bundle ready for manuscript integration.", "derivations")
        self._register_artifact(program, "Derivation traces", "dataset", derivation_dir / "derivation_traces.json", "Symbol-to-symbol traces for every key derivation card.", "derivations")
        self._register_artifact(program, "Symbol table", "dataset", derivation_dir / "symbol_table.json", "Normalized symbol table for appendix assembly.", "derivations")
        program.tool_runs.append(
            ToolRunRecord(
                tool="sympy",
                purpose="symbolic derivation execution",
                status="passed",
                outputs={
                    "n_cards": len(derivation_outputs["cards"]),
                    "n_trace_groups": program.appendix_summary.get("n_trace_groups", 0),
                    "solver_cross_checks": program.appendix_summary.get("n_solver_cross_checks", 0),
                    "all_checks_pass": program.appendix_summary.get("all_checks_pass", False),
                },
                artifact_paths=(
                    str(derivation_dir / "derivation_report.md"),
                    str(derivation_dir / "equations.tex"),
                    str(derivation_dir / "derivation_checks.json"),
                    str(derivation_dir / "appendix_package.md"),
                    str(derivation_dir / "appendix_bundle.tex"),
                    str(derivation_dir / "derivation_traces.json"),
                    str(derivation_dir / "symbol_table.json"),
                ),
            )
        )
        program.summary_metrics.update(
            {
                "appendix_cards": int(program.appendix_summary.get("n_cards", len(derivation_outputs["cards"]))),
                "appendix_symbol_traces": int(program.appendix_summary.get("n_trace_groups", 0)),
                "appendix_limit_cases": int(program.appendix_summary.get("n_limit_cases", 0)),
                "appendix_solver_cross_checks": int(program.appendix_summary.get("n_solver_cross_checks", 0)),
                "appendix_all_checks_pass": bool(program.appendix_summary.get("all_checks_pass", False)),
            }
        )
        self._finish_stage(program, "derivations", root)

        # ------------------------------------------------------------------
        # experiments / L1 chain
        # ------------------------------------------------------------------
        self._start_stage(program, "experiments", root)
        l1_dir = ensure_dir(root / "05_experiments" / "l1_chain")
        l1_summary = run_l1_chain_replay(l1_dir, ChainReplayParams())
        chain_atlas_path = l1_dir / "chain_parameter_atlas.json"
        chain_atlas = json.loads(chain_atlas_path.read_text(encoding="utf-8")) if chain_atlas_path.exists() else {}
        self._register_artifact(program, "L1 chain summary", "dataset", l1_dir / "chain_summary.json", "Executable L1 replay results for bandgap, TR, localization, and harvesting synergy.", "experiments")
        if chain_atlas_path.exists():
            self._register_artifact(program, "Chain parameter atlas", "dataset", chain_atlas_path, "Parameter atlas over delta, alpha-beta, matching, and N sweeps.", "experiments")
        for label, key, desc in (
            ("L1 harvesting spectrum", "harvesting_spectrum", "Voltage, power, and transmission across the TR spectrum."),
            ("L1 mode shape", "tr_mode_shape", "Boundary-localized TR mode shape from the chain replay."),
            ("L1 dispersion", "dispersion_curve", "Infinite-chain dispersion relation and bandgap."),
        ):
            figure_path = l1_summary.get("figures", {}).get(key)
            if figure_path:
                self._register_artifact(program, label, "figure", Path(figure_path), desc, "experiments")
        program.tool_runs.append(
            ToolRunRecord(
                tool="python",
                purpose="L1 chain replay",
                status="passed",
                outputs={
                    "tr_omega": l1_summary["tr_mode"]["omega"],
                    "pef": l1_summary["power_enhancement_factor"],
                    "q_factor": l1_summary["q_factor"],
                },
                artifact_paths=(str(l1_dir / "chain_summary.json"), str(chain_atlas_path)),
            )
        )
        program.summary_metrics.update(
            {
                "l1_tr_frequency": round(l1_summary["tr_mode"]["omega"], 6),
                "l1_eta": round(l1_summary["tr_mode"]["eta"], 6),
                "l1_pef": round(l1_summary["power_enhancement_factor"], 3),
                "l1_q_factor": round(l1_summary["q_factor"], 3),
            }
        )
        self._finish_stage(program, "experiments", root)

        # ------------------------------------------------------------------
        # verification / L2 + L3 calibration
        # ------------------------------------------------------------------
        self._start_stage(program, "verification", root)
        l2_dir = ensure_dir(root / "06_verification" / "l2_beam")
        l2_summary = run_l2_beam_replay(l2_dir, BeamReplayParams())
        self._register_artifact(program, "L2 beam summary", "dataset", l2_dir / "beam_summary.json", "Executable L2 beam replay with stopbands and candidate TR locations.", "verification")
        self._register_artifact(program, "Beam band structure", "figure", Path(l2_summary["figures"]["beam_band_structure"]), "Bilayer Timoshenko beam band structure and stopband map.", "verification")
        if "beam_mode_shape" in l2_summary.get("figures", {}):
            self._register_artifact(program, "Beam mode shape", "figure", Path(l2_summary["figures"]["beam_mode_shape"]), "Boundary-localized beam response candidate.", "verification")
        program.tool_runs.append(
            ToolRunRecord(
                tool="python",
                purpose="L2 beam replay",
                status="passed",
                outputs={"n_candidates": len(l2_summary.get("candidates", [])), "n_stopbands": len(l2_summary.get("stopbands_nd", []))},
                artifact_paths=(str(l2_dir / "beam_summary.json"), str(l2_dir / "beam_gap_candidates.json")),
            )
        )

        l3_dir = ensure_dir(root / "06_verification" / "l3_toolchain")
        l3_summary = run_l3_validation_suite(l3_dir, self.task, l1_summary=l1_summary, l2_summary=l2_summary)
        program.l3_validation = l3_summary
        program.calibration_summary = l3_summary.get("calibration_summary", {})
        calibration_summary = program.calibration_summary
        if calibration_summary.get("source") == "paper-anchor-fallback":
            program.warnings.append(
                "L2–L3 calibration used paper-anchor fallback because no passed MATLAB/COMSOL result was available."
            )
        self._register_artifact(program, "L3 request manifest", "dataset", Path(l3_summary["artifacts"]["request_manifest"]), "Shared request manifest for MATLAB and COMSOL L3 validation.", "verification")
        self._register_artifact(program, "L3 consensus alignment", "dataset", Path(l3_summary["artifacts"]["consensus_alignment"]), "Anchor-aware consensus alignment between raw L2 candidates and L3/paper targets.", "verification")
        self._register_artifact(program, "L3 summary", "dataset", Path(l3_summary["artifacts"]["summary"]), "MATLAB/COMSOL toolchain results and consensus alignment.", "verification")
        self._register_artifact(program, "Calibration summary", "dataset", Path(l3_summary["artifacts"]["calibration_summary"]), "Closed-loop L2↔L3 calibration metrics, maps, and provenance.", "verification")
        self._register_artifact(program, "Calibrated L2 summary", "dataset", Path(l3_summary["artifacts"]["calibrated_l2_summary"]), "Calibrated L2 summary after applying L3-derived frequency and stopband corrections.", "verification")
        self._register_artifact(program, "Uncertainty model", "dataset", Path(l3_summary["artifacts"]["uncertainty_model"]), "Residual-model parameters used for candidate-level uncertainty calibration.", "verification")
        self._register_artifact(program, "Candidate uncertainty", "dataset", Path(l3_summary["artifacts"]["candidate_uncertainty"]), "Candidate-level uncertainty, confidence interval, and extrapolation penalty table.", "verification")
        self._register_artifact(program, "Frequency calibration", "figure", Path(l3_summary["artifacts"]["frequency_calibration"]), "Raw-versus-calibrated L2 frequency map against L3 anchors.", "verification")
        self._register_artifact(program, "Stopband calibration", "figure", Path(l3_summary["artifacts"]["stopband_calibration"]), "Raw-versus-calibrated stopband alignment against L3 anchors.", "verification")
        self._register_artifact(program, "Uncertainty calibration", "figure", Path(l3_summary["artifacts"]["uncertainty_calibration"]), "Candidate-level uncertainty and extrapolation profile across the calibrated shortlist.", "verification")
        for run in l3_summary["tool_runs"]:
            program.tool_runs.append(run)
        cal_errors = calibration_summary.get("errors", {})
        residual_model = calibration_summary.get("residual_model", {})
        program.tool_runs.append(
            ToolRunRecord(
                tool="python",
                purpose="L2↔L3 calibration loop",
                status="passed",
                outputs={
                    **cal_errors,
                    "base_sigma_hz": residual_model.get("base_sigma_hz"),
                    "leave_one_out_rmse_hz": residual_model.get("leave_one_out_rmse_hz"),
                },
                artifact_paths=(
                    l3_summary["artifacts"]["calibration_summary"],
                    l3_summary["artifacts"]["calibrated_l2_summary"],
                    l3_summary["artifacts"]["uncertainty_model"],
                    l3_summary["artifacts"]["candidate_uncertainty"],
                    l3_summary["artifacts"]["frequency_calibration"],
                    l3_summary["artifacts"]["stopband_calibration"],
                    l3_summary["artifacts"]["uncertainty_calibration"],
                ),
                notes=f"source={calibration_summary.get('source', '')}, confidence={float(calibration_summary.get('confidence', 0.0) or 0.0):.3f}",
            )
        )
        matlab_result = l3_summary["tool_results"].get("matlab", {})
        comsol_result = l3_summary["tool_results"].get("comsol", {})
        l2_for_gaps = calibration_summary.get("calibrated_l2_summary", l2_summary)
        program.summary_metrics.update(
            {
                "l2_stopbands": len(l2_summary.get("stopbands_nd", [])),
                "l2_candidate_gaps": len(l2_summary.get("candidates", [])),
                "l3_consensus_pairs": len(l3_summary.get("consensus_alignment", [])),
                "matlab_status": matlab_result.get("status", "not-run") if "matlab" in self.task.allowed_tools else "not-requested",
                "comsol_status": comsol_result.get("status", "not-run") if "comsol" in self.task.allowed_tools else "not-requested",
                "calibration_source": calibration_summary.get("source", ""),
                "calibration_confidence": round(float(calibration_summary.get("confidence", 0.0) or 0.0), 4),
                "calibration_pre_rmse_hz": round(float(cal_errors.get("pre_rmse_hz", 0.0) or 0.0), 3),
                "calibration_post_rmse_hz": round(float(cal_errors.get("post_rmse_hz", 0.0) or 0.0), 3),
                "calibration_pre_stopband_mae_hz": round(float(cal_errors.get("pre_stopband_mae_hz", 0.0) or 0.0), 3),
                "calibration_post_stopband_mae_hz": round(float(cal_errors.get("post_stopband_mae_hz", 0.0) or 0.0), 3),
                "calibration_base_sigma_hz": round(float(residual_model.get("base_sigma_hz", 0.0) or 0.0), 3),
                "calibration_loo_rmse_hz": round(float(residual_model.get("leave_one_out_rmse_hz", 0.0) or 0.0), 3),
                "calibration_rmse_improved": float(cal_errors.get("post_rmse_hz", 0.0) or 0.0) <= float(cal_errors.get("pre_rmse_hz", 0.0) or 0.0),
            }
        )
        self._finish_stage(program, "verification", root)

        # ------------------------------------------------------------------
        # gap ranking + portfolio
        # ------------------------------------------------------------------
        self._start_stage(program, "gap_design", root)
        gap_dir = ensure_dir(root / "07_gap_design")
        band_of_interest = None
        if self.task.engineering_task is not None:
            band_of_interest = tuple(self.task.engineering_task.frequency_target.band_of_interest)
        raw_gap_candidates = build_gap_candidates(
            l1_summary,
            l2_for_gaps,
            band_of_interest=band_of_interest,
            anchors=self.task.l3_anchors,
            l3_summary=l3_summary,
        )
        ranked_gaps = rank_gap_candidates(raw_gap_candidates)
        program.gap_candidates = ranked_gaps
        write_json(gap_dir / "gap_ranking.json", ranked_gaps)
        design_rules_lines = [
            "# Gap ranking and design rules",
            "",
            "The final ranking combines suppression, localization, harvestability, target-band fit, calibration confidence, uncertainty, extrapolation penalty, and L3 anchor agreement.",
            "",
        ]
        for gap in ranked_gaps:
            freq_parts: list[str] = []
            if gap.raw_frequency_hz is not None:
                freq_parts.append(f"raw={gap.raw_frequency_hz:.3f} Hz")
            if gap.anchored_frequency_hz is not None:
                freq_parts.append(f"anchored={gap.anchored_frequency_hz:.3f} Hz")
            if gap.calibrated_frequency_hz is not None:
                freq_parts.append(f"calibrated={gap.calibrated_frequency_hz:.3f} Hz")
            if gap.uncertainty_sigma_hz is not None:
                freq_parts.append(f"σ={gap.uncertainty_sigma_hz:.3f} Hz")
            if gap.confidence_interval_hz is not None:
                lo, hi = gap.confidence_interval_hz
                freq_parts.append(f"CI=[{lo:.3f}, {hi:.3f}] Hz")
            freq_parts.append(f"uncertainty_score={gap.uncertainty_score:.3f}")
            freq_parts.append(f"extrapolation_penalty={gap.extrapolation_penalty:.3f}")
            if gap.matched_anchor_label:
                freq_parts.append(f"anchor={gap.matched_anchor_label}")
                freq_parts.append(f"anchor_score={gap.anchor_score:.3f}")
            design_rules_lines.append(
                f"- Gap {gap.band_index}: score={gap.overall_score:.3f}, Ω∈[{gap.omega_min:.4f}, {gap.omega_max:.4f}], TR={list(gap.tr_frequencies)}; "
                + "; ".join(freq_parts)
            )
        write_text(gap_dir / "design_rules.md", "\n".join(design_rules_lines))
        portfolio = build_mechanism_portfolio(
            gap_dir,
            self.task,
            ranked_gaps,
            calibration_summary=calibration_summary,
            solver_library=program.solver_library,
        )
        program.mechanism_portfolio = portfolio
        self._register_artifact(program, "Gap ranking", "dataset", gap_dir / "gap_ranking.json", "Ranked gap candidates combining L1, L2, and L3-anchor evidence.", "gap_design")
        self._register_artifact(program, "Design rules", "report", gap_dir / "design_rules.md", "Compact design rules distilled from replay evidence.", "gap_design")
        self._register_artifact(program, "Mechanism portfolio", "dataset", gap_dir / "mechanism_portfolio.json", "Portfolio-level mechanism comparison and recommended expansion path.", "gap_design")
        self._register_artifact(program, "Mechanism roadmap", "report", gap_dir / "mechanism_combo_roadmap.md", "Mechanism-combination roadmap for the next research layer.", "gap_design")
        program.tool_runs.append(
            ToolRunRecord(
                tool="python",
                purpose="gap ranking",
                status="passed",
                outputs={"n_ranked_gaps": len(ranked_gaps)},
                artifact_paths=(str(gap_dir / "gap_ranking.json"), str(gap_dir / "design_rules.md")),
            )
        )
        program.tool_runs.append(
            ToolRunRecord(
                tool="python",
                purpose="mechanism portfolio assembly",
                status="passed",
                outputs={"primary": portfolio.get("recommended_path", {}).get("primary", "")},
                artifact_paths=(str(gap_dir / "mechanism_portfolio.json"), str(gap_dir / "mechanism_combo_roadmap.md")),
            )
        )
        if ranked_gaps:
            best_gap = ranked_gaps[0]
            program.summary_metrics.update(
                {
                    "best_gap_index": best_gap.band_index,
                    "best_gap_score": round(best_gap.overall_score, 4),
                    "best_gap_tr": round(best_gap.tr_frequencies[0], 6) if best_gap.tr_frequencies else None,
                    "best_gap_anchor": best_gap.matched_anchor_label,
                    "best_gap_raw_hz": round(best_gap.raw_frequency_hz, 3) if best_gap.raw_frequency_hz is not None else None,
                    "best_gap_anchored_hz": round(best_gap.anchored_frequency_hz, 3) if best_gap.anchored_frequency_hz is not None else None,
                    "best_gap_calibrated_hz": round(best_gap.calibrated_frequency_hz, 3) if best_gap.calibrated_frequency_hz is not None else None,
                    "best_gap_uncertainty_sigma_hz": round(best_gap.uncertainty_sigma_hz, 3) if best_gap.uncertainty_sigma_hz is not None else None,
                    "best_gap_uncertainty_score": round(best_gap.uncertainty_score, 4),
                    "best_gap_calibration_confidence": round(best_gap.calibration_confidence, 4),
                }
            )
        recommended = portfolio.get("recommended_path", {})
        program.summary_metrics.update(
            {
                "mechanism_primary": recommended.get("primary", ""),
                "mechanism_secondary": ", ".join(recommended.get("secondary", [])),
            }
        )
        self._finish_stage(program, "gap_design", root)

        # ------------------------------------------------------------------
        # mechanisms / solver library + refreshed portfolio
        # ------------------------------------------------------------------
        self._start_stage(program, "mechanisms", root)
        mechanisms_dir = ensure_dir(root / "08_mechanisms")
        solver_library = build_solver_library(
            mechanisms_dir,
            self.task,
            ranked_gaps,
            l1_summary=l1_summary,
            l2_summary=l2_for_gaps,
            calibration_summary=calibration_summary,
        )
        program.solver_library = solver_library
        program.mechanism_portfolio = build_mechanism_portfolio(
            gap_dir,
            self.task,
            ranked_gaps,
            calibration_summary=calibration_summary,
            solver_library=solver_library,
        )
        self._register_artifact(program, "Mechanism solver library", "dataset", mechanisms_dir / "mechanism_solver_library.json", "Multi-mechanism surrogate solver library with audited code-generation packs.", "mechanisms")
        self._register_artifact(program, "Mechanism solver comparison", "dataset", mechanisms_dir / "mechanism_solver_comparison.csv", "Mechanism comparison table across target-band fit, localization, and review status.", "mechanisms")
        self._register_artifact(program, "Mechanism solver library (markdown)", "report", mechanisms_dir / "mechanism_solver_library.md", "Human-readable mechanism library summary.", "mechanisms")
        self._register_artifact(program, "Mechanism codegen bundle", "bundle", mechanisms_dir / "mechanism_codegen_bundle.tar.gz", "Auditable Python/MATLAB/COMSOL code-generation bundle for every mechanism route.", "mechanisms")
        program.tool_runs.append(
            ToolRunRecord(
                tool="python",
                purpose="multi-mechanism solver library",
                status="passed",
                outputs={
                    "n_entries": len(solver_library.get("entries", [])),
                    "n_codegen_routes": len(solver_library.get("comparison", [])),
                },
                artifact_paths=(
                    str(mechanisms_dir / "mechanism_solver_library.json"),
                    str(mechanisms_dir / "mechanism_solver_comparison.csv"),
                    str(mechanisms_dir / "mechanism_codegen_bundle.tar.gz"),
                ),
            )
        )
        program.summary_metrics.update(
            {
                "solver_library_entries": len(solver_library.get("entries", [])),
                "solver_library_review_pass": sum(1 for row in solver_library.get("comparison", []) if row.get("review_pass")),
            }
        )
        self._finish_stage(program, "mechanisms", root)

        # ------------------------------------------------------------------
        # memory
        # ------------------------------------------------------------------
        self._start_stage(program, "memory", root)
        memory_dir = ensure_dir(root / "09_memory")
        negative_memory = build_negative_result_memory(
            memory_dir,
            chain_atlas=chain_atlas,
            gap_candidates=ranked_gaps,
            calibration_summary=calibration_summary,
            derivation_checks=derivation_checks,
            solver_library=solver_library,
        )
        negative_memory["path"] = str((memory_dir / "negative_result_memory.json").resolve())
        program.negative_memory = negative_memory
        self._register_artifact(program, "Negative-result memory", "dataset", memory_dir / "negative_result_memory.json", "Explicit memory of failed parameter regions, unsuitable gaps, L3 refutations, and unstable derivations.", "memory")
        self._register_artifact(program, "Negative-result memory (csv)", "dataset", memory_dir / "negative_result_memory.csv", "Flattened memory ledger for filtering and review.", "memory")
        self._register_artifact(program, "Negative-result memory (markdown)", "report", memory_dir / "negative_result_memory.md", "Human-readable experience ledger.", "memory")
        program.tool_runs.append(
            ToolRunRecord(
                tool="python",
                purpose="negative-result memory assembly",
                status="passed",
                outputs=negative_memory.get("summary", {}),
                artifact_paths=(
                    str(memory_dir / "negative_result_memory.json"),
                    str(memory_dir / "negative_result_memory.csv"),
                    str(memory_dir / "negative_result_memory.md"),
                ),
            )
        )
        program.summary_metrics.update(
            {
                "negative_memory_records": int(negative_memory.get("summary", {}).get("n_records", 0)),
                "negative_memory_l3_refutations": int(negative_memory.get("summary", {}).get("n_l3_refutations", 0)),
            }
        )
        self._finish_stage(program, "memory", root)

        # ------------------------------------------------------------------
        # reporting
        # ------------------------------------------------------------------
        self._start_stage(program, "reporting", root)
        report_dir = ensure_dir(root / "10_reporting")
        validated_derivations = execute_tr_derivations(
            report_dir / "derivations_validated",
            self.task,
            l1_summary=l1_summary,
            l2_summary=l2_for_gaps,
        )
        program.appendix_summary = validated_derivations.get("appendix_summary", program.appendix_summary)
        self._register_artifact(program, "Validated appendix package", "report", report_dir / "derivations_validated" / "appendix_package.md", "Validated appendix package cross-checked against executable L1/L2 results.", "reporting")
        self._register_artifact(program, "Validated appendix bundle", "equation", report_dir / "derivations_validated" / "appendix_bundle.tex", "Validated LaTeX appendix bundle for manuscript assembly.", "reporting")
        program.evidence = draft_evidence_records(
            program.claim_graph,
            program.derivations,
            program.gap_candidates,
            artifacts=program.artifacts,
            tool_runs=program.tool_runs,
        )
        write_json(report_dir / "evidence_matrix.json", program.evidence)
        bundle = write_report_bundle(report_dir, self.task, program)
        self._register_artifact(program, "Evidence matrix", "dataset", report_dir / "evidence_matrix.json", "Claim-to-evidence matrix across derivations, solver outputs, and reports.", "reporting")
        self._register_artifact(program, "Discovery report", "report", Path(bundle["report"]), "Top-level executable replay report.", "reporting")
        self._register_artifact(program, "Artifact manifest", "dataset", Path(bundle["artifact_manifest"]), "Artifact manifest for report and dashboard browsing.", "reporting")
        program.tool_runs.append(
            ToolRunRecord(
                tool="python",
                purpose="report assembly",
                status="passed",
                outputs={"n_artifacts": len(program.artifacts), "n_evidence": len(program.evidence)},
                artifact_paths=(bundle["report"], bundle["artifact_manifest"], str(report_dir / "evidence_matrix.json")),
            )
        )
        self._finish_stage(program, "reporting", root)

        # ------------------------------------------------------------------
        # publication
        # ------------------------------------------------------------------
        self._start_stage(program, "publication", root)
        publication_dir = ensure_dir(root / "11_publication")
        publication_bundle = build_publication_bundle(publication_dir, self.task, program)
        program.publication_bundle = publication_bundle
        self._register_artifact(program, "Publication bundle", "dataset", publication_dir / "publication_bundle.json", "Top-level publication package bundle.", "publication")
        self._register_artifact(program, "Publication bundle (markdown)", "report", publication_dir / "publication_bundle.md", "Human-readable publication package summary.", "publication")
        self._register_artifact(program, "Main figures index", "dataset", publication_dir / "main_figures.json", "Selected main paper figure bundle.", "publication")
        self._register_artifact(program, "Main figures (markdown)", "report", publication_dir / "main_figures.md", "Main paper figure captions and paths.", "publication")
        self._register_artifact(program, "Ablation tables", "report", publication_dir / "ablation_tables.md", "Ablation summary over ranking, calibration uncertainty, and mechanisms.", "publication")
        self._register_artifact(program, "Reproducibility package", "bundle", publication_dir / "reproducibility_package.tar.gz", "Reproducibility bundle with commands, environment, and checksums.", "publication")
        self._register_artifact(program, "Reviewer artifact manifest", "dataset", publication_dir / "reviewer_artifact_manifest.json", "Reviewer-facing artifact manifest by claim.", "publication")
        program.tool_runs.append(
            ToolRunRecord(
                tool="python",
                purpose="publication package assembly",
                status="passed",
                outputs={
                    "n_main_figures": len(publication_bundle.get("main_figures", [])),
                    "reviewer_claim_rows": publication_bundle.get("reviewer_manifest", {}).get("n_claim_rows", 0),
                },
                artifact_paths=(
                    str(publication_dir / "publication_bundle.json"),
                    str(publication_dir / "main_figures.json"),
                    str(publication_dir / "ablation_tables.md"),
                    str(publication_dir / "reproducibility_package.tar.gz"),
                    str(publication_dir / "reviewer_artifact_manifest.json"),
                ),
            )
        )
        program.summary_metrics.update(
            {
                "publication_main_figures": len(publication_bundle.get("main_figures", [])),
                "publication_reviewer_claim_rows": int(publication_bundle.get("reviewer_manifest", {}).get("n_claim_rows", 0)),
            }
        )
        self._finish_stage(program, "publication", root)

        # ------------------------------------------------------------------
        # discussion / human-in-the-loop
        # ------------------------------------------------------------------
        self._start_stage(program, "discussion", root)
        discussion_dir = ensure_dir(root / "12_discussion")
        discussion_bundle = build_discussion_bundle(discussion_dir, self.task, program)
        program.discussion_bundle = discussion_bundle
        self._register_artifact(program, "Discussion bundle", "dataset", discussion_dir / "discussion_bundle.json", "Role-based discussion bundle for planner/theorist/numerics/skeptic/reviewer/editor/human collaboration.", "discussion")
        self._register_artifact(program, "Discussion bundle (markdown)", "report", discussion_dir / "discussion_bundle.md", "Human-readable discussion record.", "discussion")
        self._register_artifact(program, "Multi-LLM prompt pack", "prompt", discussion_dir / "multi_llm_prompt_pack.json", "Prompt pack for multi-agent or multi-LLM discussion runs.", "discussion")
        self._register_artifact(program, "Multi-LLM prompt pack (markdown)", "report", discussion_dir / "multi_llm_prompt_pack.md", "Human-readable prompt pack.", "discussion")
        program.tool_runs.append(
            ToolRunRecord(
                tool="python",
                purpose="discussion bundle assembly",
                status="passed",
                outputs={
                    "n_generated_roles": len(discussion_bundle.get("generated_messages", [])),
                    "n_human_messages": len(discussion_bundle.get("human_messages", [])),
                },
                artifact_paths=(
                    str(discussion_dir / "discussion_bundle.json"),
                    str(discussion_dir / "multi_llm_prompt_pack.json"),
                ),
            )
        )
        program.summary_metrics.update(
            {
                "discussion_generated_roles": len(discussion_bundle.get("generated_messages", [])),
                "discussion_human_messages": len(discussion_bundle.get("human_messages", [])),
            }
        )
        self._finish_stage(program, "discussion", root)

        # ------------------------------------------------------------------
        # smoke
        # ------------------------------------------------------------------
        self._start_stage(program, "smoke", root)
        smoke_dir = ensure_dir(root / "13_smoke")
        smoke_summary = run_regression_smoke(self.task, program, output_dir=smoke_dir)
        program.smoke_summary = smoke_summary
        self._register_artifact(program, "Smoke report", "dataset", smoke_dir / "smoke_report.json", "Regression smoke report over artifacts, metrics, toolchain manifests, and frontend assets.", "smoke")
        self._register_artifact(program, "Smoke report (markdown)", "report", smoke_dir / "smoke_report.md", "Human-readable regression smoke summary.", "smoke")
        program.tool_runs.append(
            ToolRunRecord(
                tool="python",
                purpose="regression smoke",
                status="passed" if smoke_summary.get("overall_pass") else "failed",
                outputs={"overall_pass": smoke_summary.get("overall_pass"), "n_checks": smoke_summary.get("n_checks")},
                artifact_paths=(str(smoke_dir / "smoke_report.json"), str(smoke_dir / "smoke_report.md")),
            )
        )
        program.summary_metrics.update(
            {
                "smoke_pass": bool(smoke_summary.get("overall_pass")),
                "smoke_checks": int(smoke_summary.get("n_checks", 0)),
            }
        )
        self._finish_stage(program, "smoke", root)

        program.stage = "completed"
        program.updated_at = now_iso()
        self._last_program = program
        self._write_program(program, root / "program_state.json")
        return program

    def _start_stage(self, program: DiscoveryProgramState, stage: str, root: Path) -> None:
        program.planned_steps = update_step_status(program.planned_steps, stage, "running")
        program.stage = stage
        program.updated_at = now_iso()
        self._write_program(program, root / "program_state.json")

    def _finish_stage(self, program: DiscoveryProgramState, stage: str, root: Path) -> None:
        program.planned_steps = update_step_status(program.planned_steps, stage, "completed")
        program.updated_at = now_iso()
        self._write_program(program, root / "program_state.json")

    def _register_artifact(
        self,
        program: DiscoveryProgramState,
        label: str,
        artifact_type: str,
        path: str | Path,
        description: str,
        generated_by: str,
    ) -> None:
        program.artifacts.append(
            ExperimentArtifact(
                label=label,
                artifact_type=artifact_type,
                path=str(Path(path).resolve()),
                description=description,
                generated_by=generated_by,
            )
        )

    def _write_program(self, program: DiscoveryProgramState, path: str | Path) -> None:
        write_json(path, program)
