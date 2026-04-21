"""Publication-grade output assembly for discovery replay."""

from __future__ import annotations

import hashlib
import platform
import shutil
import tarfile
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import scipy

from veh_scientist.discover.gap_designer import rank_gap_candidates
from veh_scientist.discover.utils import ensure_dir, write_csv, write_json, write_text
from veh_scientist.interfaces import DiscoverTaskCard, DiscoveryProgramState, GapCandidate


FIGURE_RULES = [
    ("Infinite-chain dispersion", ("dispersion_curve.png",), "theory"),
    ("TR harvesting synergy", ("harvesting_spectrum.png", "chain_spectrum.png"), "chain-validation"),
    ("Beam band structure", ("beam_band_structure.png",), "beam-validation"),
    ("Beam localized mode", ("beam_mode_shape",), "beam-validation"),
    ("L2–L3 calibration", ("frequency_calibration.png",), "calibration"),
    ("Calibration uncertainty", ("uncertainty_calibration.png",), "calibration"),
]



def _artifact_lookup(program: DiscoveryProgramState) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for artifact in program.artifacts:
        path = Path(artifact.path)
        lookup[path.name] = artifact.path
    if program.output_dir:
        for path in Path(program.output_dir).rglob("*"):
            if path.is_file():
                lookup.setdefault(path.name, str(path.resolve()))
    return lookup



def _copy_main_figures(output_dir: Path, program: DiscoveryProgramState) -> list[dict[str, Any]]:
    lookup = _artifact_lookup(program)
    target_root = ensure_dir(output_dir / "main_figures")
    selected: list[dict[str, Any]] = []
    index = 1
    for caption, candidates, section in FIGURE_RULES:
        source_path = None
        source_name = None
        for candidate in candidates:
            if candidate in lookup:
                source_name = candidate
                source_path = Path(lookup[candidate])
                break
            for lookup_name, lookup_path in lookup.items():
                if candidate in lookup_name:
                    source_name = lookup_name
                    source_path = Path(lookup_path)
                    break
            if source_path is not None:
                break
        if source_path is None or not source_path.exists():
            continue
        ext = source_path.suffix or ".png"
        target = target_root / f"fig_{index:02d}{ext}"
        shutil.copy2(source_path, target)
        selected.append(
            {
                "figure_id": f"Fig.{index}",
                "caption": caption,
                "section": section,
                "source_artifact": str(source_path.resolve()),
                "path": str(target.resolve()),
            }
        )
        index += 1
    write_json(output_dir / "main_figures.json", selected)
    lines = ["# Main paper figures", ""]
    for row in selected:
        lines.append(f"- **{row['figure_id']}** — {row['caption']} ({row['section']})")
        lines.append(f"  - source: `{row['source_artifact']}`")
        lines.append(f"  - bundled: `{row['path']}`")
    write_text(output_dir / "main_figures.md", "\n".join(lines))
    return selected



def _deterministic_gap_view(gaps: list[GapCandidate]) -> list[GapCandidate]:
    downgraded = [
        replace(gap, uncertainty_score=0.5, extrapolation_penalty=0.0)
        for gap in gaps
    ]
    return rank_gap_candidates(downgraded)



def _ablation_tables(output_dir: Path, program: DiscoveryProgramState) -> dict[str, Any]:
    gap_rows: list[dict[str, Any]] = []
    deterministic = _deterministic_gap_view(program.gap_candidates)
    det_rank = {gap.gap_id: idx + 1 for idx, gap in enumerate(deterministic)}
    for idx, gap in enumerate(program.gap_candidates, start=1):
        gap_rows.append(
            {
                "gap_id": gap.gap_id,
                "band_index": gap.band_index,
                "uncertainty_aware_rank": idx,
                "deterministic_rank": det_rank.get(gap.gap_id, idx),
                "overall_score": gap.overall_score,
                "uncertainty_score": gap.uncertainty_score,
                "calibration_confidence": gap.calibration_confidence,
                "extrapolation_penalty": gap.extrapolation_penalty,
                "raw_frequency_hz": gap.raw_frequency_hz,
                "calibrated_frequency_hz": gap.calibrated_frequency_hz,
            }
        )

    calibration_rows: list[dict[str, Any]] = []
    for pair in (program.calibration_summary or {}).get("candidate_uncertainty", []):
        calibration_rows.append(dict(pair))

    mechanism_rows: list[dict[str, Any]] = []
    for row in (program.solver_library or {}).get("comparison", []):
        mechanism_rows.append(dict(row))

    write_csv(output_dir / "ablation_gap_ranking.csv", gap_rows)
    write_csv(output_dir / "ablation_calibration_uncertainty.csv", calibration_rows)
    write_csv(output_dir / "ablation_mechanisms.csv", mechanism_rows)
    lines = ["# Ablation tables", "", "## Gap ranking", ""]
    for row in gap_rows:
        lines.append(
            f"- gap {row['band_index']}: uncertainty-aware rank={row['uncertainty_aware_rank']}, deterministic rank={row['deterministic_rank']}, score={row['overall_score']:.4f}, uncertainty={row['uncertainty_score']:.4f}"
        )
    lines.extend(["", "## Calibration uncertainty", ""])
    for row in calibration_rows:
        lines.append(
            f"- gap {row.get('band_index')}: σ={row.get('uncertainty_sigma_hz')}, ci={row.get('confidence_interval_hz')}, cal_conf={row.get('calibration_confidence')}"
        )
    lines.extend(["", "## Mechanism comparison", ""])
    for row in mechanism_rows:
        lines.append(
            f"- {row.get('mechanism_key')}: maturity={row.get('maturity')}, status={row.get('solver_status')}, target_band={row.get('target_band_score')}, review_pass={row.get('review_pass')}"
        )
    write_text(output_dir / "ablation_tables.md", "\n".join(lines))
    return {
        "gap_rows": gap_rows,
        "calibration_rows": calibration_rows,
        "mechanism_rows": mechanism_rows,
    }



def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()



def _reproducibility_package(output_dir: Path, task: DiscoverTaskCard, program: DiscoveryProgramState) -> dict[str, Any]:
    package_dir = ensure_dir(output_dir / "reproducibility_package")
    artifact_entries: list[dict[str, Any]] = []
    for artifact in program.artifacts:
        path = Path(artifact.path)
        if not path.exists() or path.is_dir():
            continue
        artifact_entries.append(
            {
                "label": artifact.label,
                "path": str(path.resolve()),
                "sha256": _sha256(path),
                "size_bytes": path.stat().st_size,
            }
        )
    manifest = {
        "task_id": task.task_id,
        "task_card": task,
        "commands": [
            f"python scripts/run_replay_tr.py configs/tasks/tr_discover_replay.yaml --output-dir {Path(program.output_dir).parent}",
            f"python scripts/build_discovery_report.py --task-card configs/tasks/tr_discover_replay.yaml --output-dir {Path(program.output_dir).parent} --task-id {task.task_id}",
            "python scripts/serve_dashboard.py --host 127.0.0.1 --port 8000",
        ],
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
        },
        "artifacts": artifact_entries,
    }
    write_json(package_dir / "reproducibility_manifest.json", manifest)
    write_text(package_dir / "reproducibility_README.md", "\n".join([
        "# Reproducibility package",
        "",
        "This package records the task card, execution commands, and artifact checksums needed to replay the run.",
    ]))
    tar_path = output_dir / "reproducibility_package.tar.gz"
    with tarfile.open(tar_path, "w:gz") as handle:
        handle.add(package_dir, arcname="reproducibility_package")
    return {
        "manifest_path": str((package_dir / "reproducibility_manifest.json").resolve()),
        "readme_path": str((package_dir / "reproducibility_README.md").resolve()),
        "bundle_path": str(tar_path.resolve()),
        "n_artifacts": len(artifact_entries),
    }



def _reviewer_manifest(output_dir: Path, program: DiscoveryProgramState) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    artifacts_by_label = {artifact.label: artifact.path for artifact in program.artifacts}
    for evidence in program.evidence:
        claim = next((item for item in program.claim_graph if item.claim_id == evidence.claim_id), None)
        rows.append(
            {
                "claim_id": evidence.claim_id,
                "claim_type": None if claim is None else claim.claim_type,
                "claim_text": None if claim is None else claim.claim_text,
                "verdict": evidence.verdict,
                "supporting_artifacts": list(evidence.supporting_artifacts),
                "supporting_runs": list(evidence.supporting_runs),
            }
        )
    payload = {
        "n_claim_rows": len(rows),
        "rows": rows,
        "artifact_index": artifacts_by_label,
        "negative_memory_path": (program.negative_memory or {}).get("path"),
        "solver_library_keys": [row.get("mechanism_key") for row in (program.solver_library or {}).get("comparison", [])],
    }
    write_json(output_dir / "reviewer_artifact_manifest.json", payload)
    lines = ["# Reviewer-facing artifact manifest", "", f"n_claim_rows: **{len(rows)}**", ""]
    for row in rows:
        lines.append(f"- **{row['claim_id']}** [{row['claim_type']}] {row['claim_text']}")
        lines.append(f"  - verdict: {row['verdict']}")
        lines.append(f"  - artifacts: {', '.join(row['supporting_artifacts']) if row['supporting_artifacts'] else '—'}")
    write_text(output_dir / "reviewer_artifact_manifest.md", "\n".join(lines))
    return payload



def build_publication_bundle(
    output_dir: str | Path,
    task: DiscoverTaskCard,
    program: DiscoveryProgramState,
) -> dict[str, Any]:
    output_dir = ensure_dir(output_dir)
    figures = _copy_main_figures(output_dir, program)
    ablations = _ablation_tables(output_dir, program)
    repro = _reproducibility_package(output_dir, task, program)
    reviewer = _reviewer_manifest(output_dir, program)
    bundle = {
        "main_figures": figures,
        "ablation_tables": {
            "gap_ranking_csv": str((output_dir / "ablation_gap_ranking.csv").resolve()),
            "calibration_uncertainty_csv": str((output_dir / "ablation_calibration_uncertainty.csv").resolve()),
            "mechanisms_csv": str((output_dir / "ablation_mechanisms.csv").resolve()),
            "markdown": str((output_dir / "ablation_tables.md").resolve()),
            "counts": {
                "gap_rows": len(ablations["gap_rows"]),
                "calibration_rows": len(ablations["calibration_rows"]),
                "mechanism_rows": len(ablations["mechanism_rows"]),
            },
        },
        "reproducibility": repro,
        "reviewer_manifest": {
            "json": str((output_dir / "reviewer_artifact_manifest.json").resolve()),
            "markdown": str((output_dir / "reviewer_artifact_manifest.md").resolve()),
            "n_claim_rows": reviewer["n_claim_rows"],
        },
    }
    write_json(output_dir / "publication_bundle.json", bundle)
    write_text(output_dir / "publication_bundle.md", "\n".join([
        "# Publication bundle",
        "",
        f"- main figures: {len(figures)}",
        f"- gap ablations: {len(ablations['gap_rows'])}",
        f"- reproducibility artifacts: {repro['n_artifacts']}",
        f"- reviewer claim rows: {reviewer['n_claim_rows']}",
    ]))
    return bundle
