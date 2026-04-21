"""Discovery report assembly for executable replay."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from veh_scientist.discover.utils import write_json, write_text
from veh_scientist.interfaces import DiscoverTaskCard, DiscoveryProgramState



def artifact_manifest(program: DiscoveryProgramState) -> list[dict[str, Any]]:
    return [asdict(artifact) for artifact in program.artifacts]



def _section(title: str) -> list[str]:
    return ["", f"## {title}", ""]



def _format_gap(gap: Any) -> str:
    parts = [
        f"Gap {gap.band_index}",
        f"Ω∈[{gap.omega_min:.4f}, {gap.omega_max:.4f}]",
        f"score={gap.overall_score:.3f}",
        f"TR={list(gap.tr_frequencies)}",
    ]
    if gap.raw_frequency_hz is not None:
        parts.append(f"raw={gap.raw_frequency_hz:.3f} Hz")
    if gap.anchored_frequency_hz is not None:
        parts.append(f"anchored={gap.anchored_frequency_hz:.3f} Hz")
    if gap.calibrated_frequency_hz is not None:
        parts.append(f"calibrated={gap.calibrated_frequency_hz:.3f} Hz")
    if gap.uncertainty_sigma_hz is not None:
        parts.append(f"σ={gap.uncertainty_sigma_hz:.3f} Hz")
    if gap.confidence_interval_hz is not None:
        lo, hi = gap.confidence_interval_hz
        parts.append(f"CI=[{lo:.3f}, {hi:.3f}] Hz")
    if gap.stopband_error_hz is not None:
        parts.append(f"stopband_error={gap.stopband_error_hz:.3f} Hz")
    parts.append(f"uncertainty_score={gap.uncertainty_score:.3f}")
    parts.append(f"calibration_confidence={gap.calibration_confidence:.3f}")
    if gap.extrapolation_penalty:
        parts.append(f"extrapolation_penalty={gap.extrapolation_penalty:.3f}")
    if gap.matched_anchor_label:
        parts.append(f"anchor={gap.matched_anchor_label}")
        parts.append(f"anchor_score={gap.anchor_score:.3f}")
    return ", ".join(parts)



def build_report_markdown(task: DiscoverTaskCard, program: DiscoveryProgramState) -> str:
    lines: list[str] = [
        f"# Discovery replay report — {task.task_id}",
        "",
        task.description,
        "",
        f"Mode: **{task.discovery_mode}**  ",
        f"Mechanism: **{task.mechanism_focus}**",
        "",
        "## Summary metrics",
        "",
    ]
    if program.summary_metrics:
        for key, value in program.summary_metrics.items():
            lines.append(f"- **{key}**: {value}")
    else:
        lines.append("- No summary metrics were recorded.")

    lines.extend(_section("Corpus"))
    for doc in program.corpus_manifest:
        status = "available" if doc.exists else "missing"
        lines.append(f"- **{doc.title}** ({doc.role}, {status})")

    if task.l3_anchors:
        lines.extend(_section("L3 anchors"))
        for anchor in task.l3_anchors:
            stopband = f", stopband={anchor.stopband_hz}" if anchor.stopband_hz is not None else ""
            lines.append(f"- **{anchor.label}** — {anchor.frequency_hz} Hz{stopband}")

    lines.extend(_section("Claim graph"))
    for claim in program.claim_graph:
        lines.append(f"- [{claim.claim_type}] {claim.claim_text}")

    lines.extend(_section("Hypothesis ladder"))
    for hypothesis in program.hypotheses:
        lines.append(f"- **{hypothesis.label}** — {hypothesis.statement}")

    lines.extend(_section("Appendix-grade derivation package"))
    appendix = program.appendix_summary or {}
    if appendix:
        lines.append(f"- cards: **{appendix.get('n_cards', 0)}**")
        lines.append(f"- trace groups: **{appendix.get('n_trace_groups', 0)}**")
        lines.append(f"- limit cases: **{appendix.get('n_limit_cases', 0)}**")
        lines.append(f"- solver cross-checks: **{appendix.get('n_solver_cross_checks', 0)}**")
        lines.append(f"- all checks pass: **{appendix.get('all_checks_pass', False)}**")
        if appendix.get("appendix_package_path"):
            lines.append(f"- package path: `{appendix.get('appendix_package_path', '')}`")
        if appendix.get("appendix_bundle_path"):
            lines.append(f"- bundle path: `{appendix.get('appendix_bundle_path', '')}`")
    else:
        lines.append("- No appendix summary recorded.")

    lines.extend(_section("Ranked gap candidates"))
    if program.gap_candidates:
        for gap in program.gap_candidates:
            lines.append(f"- {_format_gap(gap)}")
    else:
        lines.append("- No ranked gap candidates.")

    lines.extend(_section("Uncertainty-aware L2–L3 calibration"))
    calibration = program.calibration_summary or {}
    if calibration:
        errors = calibration.get("errors", {})
        residual_model = calibration.get("residual_model", {})
        lines.append(f"- source: **{calibration.get('source', '')}**")
        lines.append(f"- confidence: **{float(calibration.get('confidence', 0.0) or 0.0):.3f}**")
        lines.append(f"- pre RMSE (Hz): **{float(errors.get('pre_rmse_hz', 0.0) or 0.0):.3f}**")
        lines.append(f"- post RMSE (Hz): **{float(errors.get('post_rmse_hz', 0.0) or 0.0):.3f}**")
        lines.append(f"- pre stopband MAE (Hz): **{float(errors.get('pre_stopband_mae_hz', 0.0) or 0.0):.3f}**")
        lines.append(f"- post stopband MAE (Hz): **{float(errors.get('post_stopband_mae_hz', 0.0) or 0.0):.3f}**")
        lines.append(f"- residual bias (Hz): **{float(residual_model.get('residual_bias_hz', 0.0) or 0.0):.3f}**")
        lines.append(f"- base σ (Hz): **{float(residual_model.get('base_sigma_hz', 0.0) or 0.0):.3f}**")
        lines.append(f"- leave-one-out RMSE (Hz): **{float(residual_model.get('leave_one_out_rmse_hz', 0.0) or 0.0):.3f}**")
        lines.append(f"- learned extrapolation slope: **{float(residual_model.get('penalty_slope_hz_per_span', 0.0) or 0.0):.3f}**")
        lines.append(f"- uncertainty rows: **{len(calibration.get('candidate_uncertainty', []))}**")
        lines.append(f"- protocol: `{calibration.get('protocol_version', '')}`")
    else:
        lines.append("- No calibration summary recorded.")

    if program.l3_validation:
        lines.extend(_section("L3 validation"))
        consensus = program.l3_validation.get("consensus_alignment", [])
        if consensus:
            lines.append("Consensus alignment:")
            for row in consensus:
                lines.append(
                    f"- Gap {row.get('band_index')}: raw={row.get('raw_frequency_hz')}, anchored={row.get('anchored_frequency_hz')}, matched={row.get('matched_anchor')}, score={row.get('score')}"
                )
        tool_results = program.l3_validation.get("tool_results", {})
        for tool, result in tool_results.items():
            lines.append(f"- **{tool}**: status={result.get('status')}, notes={result.get('notes', '')}")

    lines.extend(_section("Mechanism portfolio"))
    portfolio = program.mechanism_portfolio or {}
    if portfolio:
        rec = portfolio.get("recommended_path", {})
        lines.append(f"- primary: **{rec.get('primary', '')}**")
        secondary = rec.get("secondary", [])
        lines.append(f"- secondary: {', '.join(secondary) if secondary else '—'}")
        for rationale in rec.get("rationale", []):
            lines.append(f"- rationale: {rationale}")
        for entry in portfolio.get("entries", []):
            lines.append(
                f"- **{entry.get('display_name')}** ({entry.get('mechanism_key')}, maturity={entry.get('maturity')}, fit={entry.get('fit_score')}, calibration_confidence={entry.get('calibration_confidence')}, review_pass={entry.get('review_pass')})"
            )
    else:
        lines.append("- No mechanism portfolio recorded.")

    lines.extend(_section("Multi-mechanism solver library"))
    solver_library = program.solver_library or {}
    if solver_library:
        lines.append(f"- entries: **{len(solver_library.get('entries', []))}**")
        lines.append(f"- codegen root: `{solver_library.get('codegen_root', '')}`")
        lines.append(f"- calibration source: **{solver_library.get('calibration_source', '')}**")
        for row in solver_library.get("comparison", []):
            lines.append(
                f"- **{row.get('mechanism_key')}** — maturity={row.get('maturity')}, solver_status={row.get('solver_status')}, target_band={row.get('target_band_score')}, review_pass={row.get('review_pass')}"
            )
    else:
        lines.append("- No solver library recorded.")

    lines.extend(_section("Negative-result memory"))
    negative_memory = program.negative_memory or {}
    if negative_memory:
        summary = negative_memory.get("summary", {})
        for key, value in summary.items():
            lines.append(f"- {key}: **{value}**")
        for record in negative_memory.get("records", [])[:12]:
            lines.append(
                f"- **[{record.get('category')}] {record.get('label')}** ({record.get('severity')}) — {record.get('lesson')}"
            )
    else:
        lines.append("- No negative-result memory recorded.")

    lines.extend(_section("Publication bundle"))
    publication = program.publication_bundle or {}
    if publication:
        lines.append(f"- main figures: **{len(publication.get('main_figures', []))}**")
        ablation = publication.get("ablation_tables", {})
        lines.append(f"- ablation gap rows: **{ablation.get('counts', {}).get('gap_rows', 0)}**")
        lines.append(f"- ablation calibration rows: **{ablation.get('counts', {}).get('calibration_rows', 0)}**")
        lines.append(f"- ablation mechanism rows: **{ablation.get('counts', {}).get('mechanism_rows', 0)}**")
        lines.append(f"- reproducibility bundle: `{publication.get('reproducibility', {}).get('bundle_path', '')}`")
        lines.append(f"- reviewer manifest rows: **{publication.get('reviewer_manifest', {}).get('n_claim_rows', 0)}**")
    else:
        lines.append("- No publication bundle recorded.")

    lines.extend(_section("Discussion bundle / human-in-the-loop"))
    discussion = program.discussion_bundle or {}
    if discussion:
        lines.append(f"- primary mechanism: **{discussion.get('primary_mechanism', '')}**")
        lines.append(f"- best gap: **{discussion.get('best_gap', '')}**")
        lines.append(f"- generated discussion roles: **{len(discussion.get('generated_messages', []))}**")
        lines.append(f"- human notes: **{len(discussion.get('human_messages', []))}**")
        for message in discussion.get("generated_messages", [])[:6]:
            lines.append(f"- **{message.get('role')}** ({message.get('topic')}): {message.get('content')}")
        if discussion.get("human_messages"):
            lines.append("- Human notes:")
            for message in discussion.get("human_messages", [])[:8]:
                lines.append(f"  - **{message.get('author') or 'human'}** ({message.get('topic')}): {message.get('content')}")
    else:
        lines.append("- No discussion bundle recorded.")

    lines.extend(_section("Tool runs"))
    for run in program.tool_runs:
        lines.append(f"- **{run.tool}** — {run.purpose} ({run.status})")

    if program.smoke_summary:
        lines.extend(_section("Regression smoke"))
        lines.append(f"- overall_pass: **{program.smoke_summary.get('overall_pass')}**")
        for check in program.smoke_summary.get("checks", []):
            status = "PASS" if check.get("passed") else "FAIL"
            lines.append(f"- {status} — {check.get('name')}: {check.get('details')}")

    lines.extend(_section("Artifacts"))
    for artifact in program.artifacts:
        lines.append(f"- {artifact.label}: `{artifact.path}`")
    if program.warnings:
        lines.extend(_section("Warnings"))
        for warning in program.warnings:
            lines.append(f"- {warning}")
    return "\n".join(lines)



def write_report_bundle(output_dir: str | Path, task: DiscoverTaskCard, program: DiscoveryProgramState) -> dict[str, str]:
    output_dir = Path(output_dir)
    report_path = write_text(output_dir / "discovery_report.md", build_report_markdown(task, program))
    manifest_path = write_json(output_dir / "artifact_manifest.json", artifact_manifest(program))
    return {
        "report": str(report_path.resolve()),
        "artifact_manifest": str(manifest_path.resolve()),
    }
