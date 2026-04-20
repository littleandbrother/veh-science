"""Discovery report assembly for executable replay."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from veh_scientist.discover.utils import write_json, write_text
from veh_scientist.interfaces import DiscoverTaskCard, DiscoveryProgramState


def artifact_manifest(program: DiscoveryProgramState) -> list[dict[str, Any]]:
    return [asdict(artifact) for artifact in program.artifacts]


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

    lines.extend(["", "## Corpus", ""])
    for doc in program.corpus_manifest:
        status = "available" if doc.exists else "missing"
        lines.append(f"- **{doc.title}** ({doc.role}, {status})")

    if task.l3_anchors:
        lines.extend(["", "## L3 anchors", ""])
        for anchor in task.l3_anchors:
            stopband = f", stopband={anchor.stopband_hz}" if anchor.stopband_hz is not None else ""
            lines.append(f"- **{anchor.label}** — {anchor.frequency_hz} Hz{stopband}")

    lines.extend(["", "## Claim graph", ""])
    for claim in program.claim_graph:
        lines.append(f"- [{claim.claim_type}] {claim.claim_text}")

    lines.extend(["", "## Hypothesis ladder", ""])
    for hypothesis in program.hypotheses:
        lines.append(f"- **{hypothesis.label}** — {hypothesis.statement}")

    lines.extend(["", "## Ranked gap candidates", ""])
    if program.gap_candidates:
        for gap in program.gap_candidates:
            freq_note = ""
            if gap.raw_frequency_hz is not None or gap.anchored_frequency_hz is not None:
                freq_note = f", raw={gap.raw_frequency_hz}, anchored={gap.anchored_frequency_hz}"
            anchor_note = f", anchor={gap.matched_anchor_label}, anchor_score={gap.anchor_score:.3f}" if gap.matched_anchor_label else ""
            lines.append(
                f"- Gap {gap.band_index}: Ω∈[{gap.omega_min:.4f}, {gap.omega_max:.4f}], "
                f"score={gap.overall_score:.3f}, TR={list(gap.tr_frequencies)}{freq_note}{anchor_note}"
            )
    else:
        lines.append("- No ranked gap candidates.")

    if program.l3_validation:
        lines.extend(["", "## L3 validation", ""])
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

    lines.extend(["", "## Tool runs", ""])
    for run in program.tool_runs:
        lines.append(f"- **{run.tool}** — {run.purpose} ({run.status})")

    if program.smoke_summary:
        lines.extend(["", "## Regression smoke", ""])
        lines.append(f"- overall_pass: **{program.smoke_summary.get('overall_pass')}**")
        for check in program.smoke_summary.get("checks", []):
            status = "PASS" if check.get("passed") else "FAIL"
            lines.append(f"- {status} — {check.get('name')}: {check.get('details')}")

    lines.extend(["", "## Artifacts", ""])
    for artifact in program.artifacts:
        lines.append(f"- {artifact.label}: `{artifact.path}`")
    if program.warnings:
        lines.extend(["", "## Warnings", ""])
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
