"""Regression smoke checks for replay outputs, toolchain manifests, and UI assets."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from veh_scientist.discover.utils import repo_root, write_json, write_text
from veh_scientist.interfaces import DiscoverTaskCard, DiscoveryProgramState


def _artifact_exists(program: DiscoveryProgramState, basename: str) -> bool:
    for artifact in program.artifacts:
        if Path(artifact.path).name == basename and Path(artifact.path).exists():
            return True
    if program.output_dir:
        root = Path(program.output_dir)
        if root.exists():
            return any(path.name == basename for path in root.rglob(basename))
    return False


def _check(name: str, passed: bool, details: str, severity: str = "required") -> dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "details": details,
        "severity": severity,
    }


def run_regression_smoke(
    task: DiscoverTaskCard,
    program: DiscoveryProgramState,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(output_dir or program.output_dir)
    program_root = Path(program.output_dir) if program.output_dir else root
    checks: list[dict[str, Any]] = []

    checks.append(
        _check(
            "program_state_present",
            bool(program_root and (program_root / "program_state.json").exists()),
            f"Expected program state under {program_root / 'program_state.json'}.",
        )
    )

    for required in task.required_artifacts:
        checks.append(
            _check(
                f"artifact::{required}",
                _artifact_exists(program, required),
                f"Required artifact `{required}` should be present in the replay output.",
            )
        )

    for required in (
        "calibration_summary.json",
        "calibrated_l2_summary.json",
        "appendix_package.md",
        "appendix_bundle.tex",
        "derivation_traces.json",
        "symbol_table.json",
        "mechanism_portfolio.json",
        "mechanism_combo_roadmap.md",
    ):
        checks.append(
            _check(
                f"artifact::{required}",
                _artifact_exists(program, required),
                f"Expected replay artifact `{required}` should exist.",
            )
        )

    l1_eta = float(program.summary_metrics.get("l1_eta", 0.0) or 0.0)
    l1_pef = float(program.summary_metrics.get("l1_pef", 0.0) or 0.0)
    l2_stopbands = int(program.summary_metrics.get("l2_stopbands", 0) or 0)
    best_gap_score = float(program.summary_metrics.get("best_gap_score", 0.0) or 0.0)
    appendix_cards = int(program.summary_metrics.get("appendix_cards", 0) or 0)
    calibration_post_rmse = float(program.summary_metrics.get("calibration_post_rmse_hz", 0.0) or 0.0)
    calibration_pre_rmse = float(program.summary_metrics.get("calibration_pre_rmse_hz", 0.0) or 0.0)
    checks.extend(
        [
            _check("l1_eta_floor", l1_eta > 0.5, f"Observed l1_eta={l1_eta:.4f}; expected strong localization."),
            _check("l1_pef_floor", l1_pef > 5.0, f"Observed l1_pef={l1_pef:.4f}; expected meaningful TR gain."),
            _check("l2_stopbands_exist", l2_stopbands >= 1, f"Observed l2_stopbands={l2_stopbands}."),
            _check("gap_score_available", best_gap_score > 0.0, f"Observed best_gap_score={best_gap_score:.4f}."),
            _check("appendix_cards_available", appendix_cards >= 6, f"Observed appendix_cards={appendix_cards}."),
            _check(
                "calibration_rmse_improved",
                calibration_post_rmse <= calibration_pre_rmse,
                f"Observed calibration pre/post RMSE = {calibration_pre_rmse:.3f} / {calibration_post_rmse:.3f} Hz.",
            ),
        ]
    )

    appendix = program.appendix_summary or {}
    checks.append(
        _check(
            "appendix_traces_present",
            int(appendix.get("n_trace_groups", 0) or 0) >= 6,
            f"Observed trace groups={appendix.get('n_trace_groups', 0)}.",
        )
    )
    checks.append(
        _check(
            "appendix_solver_cross_checks_present",
            int(appendix.get("n_solver_cross_checks", 0) or 0) >= 4,
            f"Observed solver cross-checks={appendix.get('n_solver_cross_checks', 0)}.",
        )
    )

    calibration = program.calibration_summary or {}
    checks.append(
        _check(
            "calibration_summary_present",
            bool(calibration),
            "Calibration summary should be present after the L2↔L3 calibration loop.",
        )
    )
    checks.append(
        _check(
            "mechanism_portfolio_present",
            bool(program.mechanism_portfolio and program.mechanism_portfolio.get("entries")),
            "Mechanism portfolio should be assembled after gap ranking.",
        )
    )

    repo = repo_root()
    checks.append(
        _check(
            "frontend_assets_present",
            all((repo / "frontend" / name).exists() for name in ("index.html", "app.js", "styles.css")),
            "Dashboard frontend assets should be present.",
        )
    )

    if {run.tool for run in program.tool_runs} & {"matlab", "comsol"}:
        for tool in ("matlab", "comsol"):
            matching_runs = [run for run in program.tool_runs if run.tool == tool]
            checks.append(
                _check(
                    f"{tool}_call_chain_materialized",
                    bool(matching_runs) and any(Path(path).exists() for run in matching_runs for path in run.artifact_paths),
                    f"{tool} should emit request/result artifacts even if the external runtime is unavailable.",
                )
            )

    overall_pass = all(check["passed"] for check in checks if check["severity"] == "required")
    summary = {
        "overall_pass": overall_pass,
        "n_checks": len(checks),
        "checks": checks,
    }
    if root:
        write_json(root / "smoke_report.json", summary)
        lines = ["# Regression smoke report", "", f"overall_pass: **{overall_pass}**", ""]
        for check in checks:
            prefix = "PASS" if check["passed"] else "FAIL"
            lines.append(f"- **{prefix}** {check['name']}: {check['details']}")
        write_text(root / "smoke_report.md", "\n".join(lines))
    return summary
