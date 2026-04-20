"""Canonical replay sequence for the truncation-resonance paper."""

from __future__ import annotations

from veh_scientist.interfaces import DiscoverTaskCard, DiscoveryStep


def build_tr_replay_steps(task: DiscoverTaskCard) -> list[DiscoveryStep]:
    """Return the ordered replay sequence for the TR discovery workflow."""

    return [
        DiscoveryStep(
            stage="corpus",
            title="Ingest prior papers and target paper",
            objective="Structure the closed corpus and identify the true research gap.",
            tools=("python",),
            deliverables=("corpus_manifest.json", "gap_statement.md"),
        ),
        DiscoveryStep(
            stage="claims",
            title="Build claim graph",
            objective="Convert papers into mechanism, limitation, and design-rule claims.",
            tools=("python",),
            deliverables=("claim_graph.json",),
        ),
        DiscoveryStep(
            stage="hypotheses",
            title="Assemble the hypothesis ladder",
            objective="Translate the research intuition into falsifiable intermediate targets.",
            tools=("python",),
            deliverables=("hypothesis_ladder.md",),
        ),
        DiscoveryStep(
            stage="derivations",
            title="Derive the analytical backbone",
            objective="Establish bandgap, TR criterion, localization, piezo coupling, and beam-transfer formulas.",
            tools=("python", "sympy"),
            deliverables=("derivation_report.md", "equations.tex"),
        ),
        DiscoveryStep(
            stage="experiments",
            title="Run L1 chain experiments",
            objective="Verify TR existence, localization, harvesting synergy, and parameter roles on the fast chain model.",
            tools=("python",),
            deliverables=("chain_parameter_atlas.json", "chain_figures/"),
        ),
        DiscoveryStep(
            stage="verification",
            title="Transfer to beam and L3 tools",
            objective="Map the best chain insights to the periodic beam, then run MATLAB/COMSOL call chains with anchor-aware manifests.",
            tools=tuple(task.allowed_tools),
            deliverables=("beam_validation.json", "l3_summary.json", "tool_run_log.json"),
        ),
        DiscoveryStep(
            stage="gap_design",
            title="Rank usable bandgaps",
            objective="Score every candidate gap for suppression, localization, harvestability, target-band fit, robustness, and L3 anchor agreement.",
            tools=("python",),
            deliverables=("gap_ranking.json", "design_rules.md"),
        ),
        DiscoveryStep(
            stage="reporting",
            title="Assemble evidence report",
            objective="Attach evidence to every claim and produce a replay-ready discovery report.",
            tools=("python",),
            deliverables=("discovery_report.md", "evidence_matrix.json", "artifact_manifest.json"),
        ),
        DiscoveryStep(
            stage="smoke",
            title="Run regression smoke",
            objective="Check that replay, reporting, toolchain manifests, and dashboard assets are all materially present.",
            tools=("python",),
            deliverables=("smoke_report.json", "smoke_report.md"),
        ),
    ]
