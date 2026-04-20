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
    lines.extend(["", "## Claim graph", ""])
    for claim in program.claim_graph:
        lines.append(f"- [{claim.claim_type}] {claim.claim_text}")
    lines.extend(["", "## Hypothesis ladder", ""])
    for hypothesis in program.hypotheses:
        lines.append(f"- **{hypothesis.label}** — {hypothesis.statement}")
    lines.extend(["", "## Ranked gap candidates", ""])
    if program.gap_candidates:
        for gap in program.gap_candidates:
            lines.append(
                f"- Gap {gap.band_index}: Ω∈[{gap.omega_min:.4f}, {gap.omega_max:.4f}], "
                f"score={gap.overall_score:.3f}, TR={list(gap.tr_frequencies)}"
            )
    else:
        lines.append("- No ranked gap candidates.")
    lines.extend(["", "## Tool runs", ""])
    for run in program.tool_runs:
        lines.append(f"- **{run.tool}** — {run.purpose} ({run.status})")
    lines.extend(["", "## Artifacts", ""])
    for artifact in program.artifacts:
        lines.append(f"- {artifact.label}: `{artifact.path}`")
    return "\n".join(lines)


def write_report_bundle(output_dir: str | Path, task: DiscoverTaskCard, program: DiscoveryProgramState) -> dict[str, str]:
    output_dir = Path(output_dir)
    report_path = write_text(output_dir / "discovery_report.md", build_report_markdown(task, program))
    manifest_path = write_json(output_dir / "artifact_manifest.json", artifact_manifest(program))
    return {
        "report": str(report_path.resolve()),
        "artifact_manifest": str(manifest_path.resolve()),
    }
