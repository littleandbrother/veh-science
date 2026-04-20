"""Executable discovery runner for replay/discover mode."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from veh_scientist.discover.claims import build_claim_graph
from veh_scientist.discover.corpus import build_corpus_manifest, corpus_digests, gap_statement
from veh_scientist.discover.derivations import execute_tr_derivations
from veh_scientist.discover.evidence import draft_evidence_records
from veh_scientist.discover.gap_designer import build_gap_candidates, rank_gap_candidates
from veh_scientist.discover.hypotheses import build_tr_hypothesis_ladder
from veh_scientist.discover.l1_chain import ChainReplayParams, run_l1_chain_replay
from veh_scientist.discover.l2_beam import BeamReplayParams, run_l2_beam_replay
from veh_scientist.discover.l3_toolchain import run_l3_validation_suite
from veh_scientist.discover.program import build_initial_program
from veh_scientist.discover.report import write_report_bundle
from veh_scientist.discover.smoke import run_regression_smoke
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
            "smoke_summary": program.smoke_summary,
        }

    def execute(self, output_dir: str | Path = "results/discovery") -> DiscoveryProgramState:
        program = self.plan()
        root = ensure_dir(Path(output_dir) / self.task.task_id)
        program.output_dir = str(root.resolve())
        self._write_program(program, root / "program_state.json")

        # Corpus.
        manifest = build_corpus_manifest(self.task, base_dir=self.base_dir)
        program.corpus_manifest = manifest
        program.planned_steps = update_step_status(program.planned_steps, "corpus", "running")
        program.stage = "corpus"
        program.updated_at = now_iso()
        self._write_program(program, root / "program_state.json")
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
        program.planned_steps = update_step_status(program.planned_steps, "corpus", "completed")

        # Claims.
        program.planned_steps = update_step_status(program.planned_steps, "claims", "running")
        program.stage = "claims"
        claim_dir = ensure_dir(root / "02_claims")
        claims = build_claim_graph(self.task, base_dir=self.base_dir)
        program.claim_graph = claims
        write_json(claim_dir / "claim_graph.json", claims)
        write_text(claim_dir / "claim_graph.md", "# Claim graph\n\n" + "\n".join(f"- [{claim.claim_type}] {claim.claim_text}" for claim in claims))
        self._register_artifact(program, "Claim graph", "dataset", claim_dir / "claim_graph.json", "Mechanism, workflow, and design-rule claims extracted from the corpus.", "claims")
        program.tool_runs.append(
            ToolRunRecord(
                tool="python",
                purpose="claim graph construction",
                status="passed",
                outputs={"n_claims": len(claims)},
                artifact_paths=(str(claim_dir / "claim_graph.json"), str(claim_dir / "claim_graph.md")),
            )
        )
        program.planned_steps = update_step_status(program.planned_steps, "claims", "completed")

        # Hypotheses.
        program.planned_steps = update_step_status(program.planned_steps, "hypotheses", "running")
        program.stage = "hypotheses"
        hypothesis_dir = ensure_dir(root / "03_hypotheses")
        hypotheses = build_tr_hypothesis_ladder(self.task)
        program.hypotheses = hypotheses
        write_json(hypothesis_dir / "hypotheses.json", hypotheses)
        write_text(hypothesis_dir / "hypothesis_ladder.md", "# Hypothesis ladder\n\n" + "\n".join(f"- **{card.label}** — {card.statement}" for card in hypotheses))
        self._register_artifact(program, "Hypothesis ladder", "report", hypothesis_dir / "hypothesis_ladder.md", "Five-step TR replay hypothesis ladder.", "hypotheses")
        program.tool_runs.append(
            ToolRunRecord(
                tool="python",
                purpose="hypothesis ladder generation",
                status="passed",
                outputs={"n_hypotheses": len(hypotheses)},
                artifact_paths=(str(hypothesis_dir / "hypothesis_ladder.md"), str(hypothesis_dir / "hypotheses.json")),
            )
        )
        program.planned_steps = update_step_status(program.planned_steps, "hypotheses", "completed")

        # Derivations.
        program.planned_steps = update_step_status(program.planned_steps, "derivations", "running")
        program.stage = "derivations"
        derivation_dir = ensure_dir(root / "04_derivations")
        derivation_outputs = execute_tr_derivations(derivation_dir, self.task)
        program.derivations = derivation_outputs["cards"]
        self._register_artifact(program, "Derivation report", "report", derivation_dir / "derivation_report.md", "Symbolic and numerical derivation ladder for TR replay.", "derivations")
        self._register_artifact(program, "Replay equations", "equation", derivation_dir / "equations.tex", "LaTeX equations emitted from the derivation stage.", "derivations")
        program.tool_runs.append(
            ToolRunRecord(
                tool="sympy",
                purpose="symbolic derivation execution",
                status="passed",
                outputs={"n_cards": len(derivation_outputs["cards"])},
                artifact_paths=(str(derivation_dir / "derivation_report.md"), str(derivation_dir / "equations.tex"), str(derivation_dir / "derivation_checks.json")),
            )
        )
        program.planned_steps = update_step_status(program.planned_steps, "derivations", "completed")

        # L1 experiments.
        program.planned_steps = update_step_status(program.planned_steps, "experiments", "running")
        program.stage = "experiments"
        l1_dir = ensure_dir(root / "05_experiments" / "l1_chain")
        l1_summary = run_l1_chain_replay(l1_dir, ChainReplayParams())
        self._register_artifact(program, "L1 chain summary", "dataset", l1_dir / "chain_summary.json", "Executable L1 replay results for bandgap, TR, localization, and harvesting synergy.", "experiments")
        if (l1_dir / "chain_parameter_atlas.json").exists():
            self._register_artifact(program, "Chain parameter atlas", "dataset", l1_dir / "chain_parameter_atlas.json", "Parameter atlas over delta, alpha-beta, matching, and N sweeps.", "experiments")
        self._register_artifact(program, "L1 harvesting spectrum", "figure", Path(l1_summary["figures"]["harvesting_spectrum"]), "Voltage, power, and transmission across the TR spectrum.", "experiments")
        self._register_artifact(program, "L1 mode shape", "figure", Path(l1_summary["figures"]["tr_mode_shape"]), "Boundary-localized TR mode shape from the chain replay.", "experiments")
        program.tool_runs.append(
            ToolRunRecord(
                tool="python",
                purpose="L1 chain replay",
                status="passed",
                outputs={"tr_omega": l1_summary["tr_mode"]["omega"], "pef": l1_summary["power_enhancement_factor"]},
                artifact_paths=(str(l1_dir / "chain_summary.json"),),
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
        program.planned_steps = update_step_status(program.planned_steps, "experiments", "completed")

        # L2 + L3 verification.
        program.planned_steps = update_step_status(program.planned_steps, "verification", "running")
        program.stage = "verification"
        l2_dir = ensure_dir(root / "06_verification" / "l2_beam")
        l2_summary = run_l2_beam_replay(l2_dir, BeamReplayParams())
        self._register_artifact(program, "L2 beam summary", "dataset", l2_dir / "beam_summary.json", "Executable L2 beam replay with stopbands and candidate TR locations.", "verification")
        self._register_artifact(program, "Beam band structure", "figure", Path(l2_summary["figures"]["beam_band_structure"]), "Bilayer Timoshenko beam band structure and stopband map.", "verification")
        if "beam_mode_shape" in l2_summary["figures"]:
            self._register_artifact(program, "Beam mode shape", "figure", Path(l2_summary["figures"]["beam_mode_shape"]), "Boundary-localized beam response candidate.", "verification")
        program.tool_runs.append(
            ToolRunRecord(
                tool="python",
                purpose="L2 beam replay",
                status="passed",
                outputs={"n_candidates": len(l2_summary.get("candidates", []))},
                artifact_paths=(str(l2_dir / "beam_summary.json"), str(l2_dir / "beam_gap_candidates.json")),
            )
        )
        l3_dir = ensure_dir(root / "06_verification" / "l3_toolchain")
        l3_summary = run_l3_validation_suite(l3_dir, self.task, l1_summary=l1_summary, l2_summary=l2_summary)
        program.l3_validation = {
            "request_manifest": l3_summary["request_manifest"],
            "consensus_alignment": l3_summary["consensus_alignment"],
            "tool_results": l3_summary["tool_results"],
        }
        self._register_artifact(program, "L3 request manifest", "dataset", Path(l3_summary["artifacts"]["request_manifest"]), "Shared request manifest for MATLAB and COMSOL L3 validation.", "verification")
        self._register_artifact(program, "L3 consensus alignment", "dataset", Path(l3_summary["artifacts"]["consensus_alignment"]), "Anchor-aware consensus alignment between raw L2 candidates and paper/L3 targets.", "verification")
        self._register_artifact(program, "L3 summary", "dataset", Path(l3_summary["artifacts"]["summary"]), "MATLAB/COMSOL toolchain results and consensus alignment.", "verification")
        for run in l3_summary["tool_runs"]:
            program.tool_runs.append(run)
        matlab_result = l3_summary["tool_results"].get("matlab", {})
        comsol_result = l3_summary["tool_results"].get("comsol", {})
        program.summary_metrics.update(
            {
                "l2_stopbands": len(l2_summary.get("stopbands_nd", [])),
                "l2_candidate_gaps": len(l2_summary.get("candidates", [])),
                "l3_consensus_pairs": len(l3_summary.get("consensus_alignment", [])),
                "matlab_status": matlab_result.get("status", "not-run") if "matlab" in self.task.allowed_tools else "not-requested",
                "comsol_status": comsol_result.get("status", "not-run") if "comsol" in self.task.allowed_tools else "not-requested",
            }
        )
        program.planned_steps = update_step_status(program.planned_steps, "verification", "completed")

        # Gap ranking.
        program.planned_steps = update_step_status(program.planned_steps, "gap_design", "running")
        program.stage = "gap_design"
        gap_dir = ensure_dir(root / "07_gap_design")
        band_of_interest = None
        if self.task.engineering_task is not None:
            band_of_interest = tuple(self.task.engineering_task.frequency_target.band_of_interest)
        raw_gap_candidates = build_gap_candidates(
            l1_summary,
            l2_summary,
            band_of_interest=band_of_interest,
            anchors=self.task.l3_anchors,
            l3_summary=program.l3_validation,
        )
        ranked_gaps = rank_gap_candidates(raw_gap_candidates)
        program.gap_candidates = ranked_gaps
        write_json(gap_dir / "gap_ranking.json", ranked_gaps)
        design_rules_lines = [
            "# Gap ranking and design rules",
            "",
            "The final ranking combines suppression, localization, harvestability, robustness, target-band fit, and L3 anchor agreement.",
            "",
        ]
        for gap in ranked_gaps:
            freq_note = f", raw={gap.raw_frequency_hz:.3f} Hz, anchored={gap.anchored_frequency_hz:.3f} Hz" if gap.raw_frequency_hz is not None and gap.anchored_frequency_hz is not None else ""
            anchor_note = f", anchor={gap.matched_anchor_label}, anchor_score={gap.anchor_score:.3f}" if gap.matched_anchor_label else ""
            design_rules_lines.append(
                f"- Gap {gap.band_index}: score={gap.overall_score:.3f}, Ω∈[{gap.omega_min:.4f}, {gap.omega_max:.4f}], TR={list(gap.tr_frequencies)}{freq_note}{anchor_note}"
            )
        write_text(gap_dir / "design_rules.md", "\n".join(design_rules_lines))
        self._register_artifact(program, "Gap ranking", "dataset", gap_dir / "gap_ranking.json", "Ranked gap candidates combining L1, L2, and L3-anchor evidence.", "gap_design")
        self._register_artifact(program, "Design rules", "report", gap_dir / "design_rules.md", "Compact design rules distilled from replay evidence.", "gap_design")
        program.tool_runs.append(
            ToolRunRecord(
                tool="python",
                purpose="gap ranking",
                status="passed",
                outputs={"n_ranked_gaps": len(ranked_gaps)},
                artifact_paths=(str(gap_dir / "gap_ranking.json"), str(gap_dir / "design_rules.md")),
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
                }
            )
        program.planned_steps = update_step_status(program.planned_steps, "gap_design", "completed")

        # Reporting.
        program.planned_steps = update_step_status(program.planned_steps, "reporting", "running")
        program.stage = "reporting"
        report_dir = ensure_dir(root / "08_reporting")
        execute_tr_derivations(report_dir / "derivations_validated", self.task, l1_summary=l1_summary, l2_summary=l2_summary)
        program.evidence = draft_evidence_records(program.claim_graph, program.derivations, program.gap_candidates, artifacts=program.artifacts, tool_runs=program.tool_runs)
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
        program.planned_steps = update_step_status(program.planned_steps, "reporting", "completed")

        # Smoke.
        program.planned_steps = update_step_status(program.planned_steps, "smoke", "running")
        program.stage = "smoke"
        smoke_dir = ensure_dir(root / "09_smoke")
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
        program.planned_steps = update_step_status(program.planned_steps, "smoke", "completed")

        program.stage = "completed"
        program.updated_at = now_iso()
        self._last_program = program
        self._write_program(program, root / "program_state.json")
        return program

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
